#!/usr/bin/env python3
"""Build a tiny authored probe and resolve its separate symbols to a source line.

Windows uses the installed Windows DbgHelp API; Linux uses nm and addr2line.
This validates the configured compiler's debug format, not every production frame.
"""
import argparse
import contextlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '.github/scripts'))
from package_symbols import match_symbols, required_tools, symbol_path

PROBE = '''#if defined(_WIN32)
#define EXPORTED __declspec(dllexport) __declspec(noinline)
#else
#define EXPORTED __attribute__((noinline))
#endif
EXPORTED int newpage_symbol_line_probe(int value) {
    volatile int adjusted = value + 13;
    return adjusted;
}
int main(void) { return newpage_symbol_line_probe(5) == 18 ? 0 : 1; }
'''


def windows_line(binary, symbol='newpage_symbol_line_probe'):
    import ctypes
    from ctypes import wintypes
    dbghelp = ctypes.WinDLL('dbghelp', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    process = kernel.GetCurrentProcess()
    dbghelp.SymSetOptions.argtypes = [wintypes.DWORD]
    dbghelp.SymSetOptions.restype = wintypes.DWORD
    dbghelp.SymSetOptions(0x10 | 0x4 | 0x200)  # LOAD_LINES, DEFERRED_LOADS, FAIL_CRITICAL_ERRORS.
    dbghelp.SymInitialize.argtypes = [wintypes.HANDLE, wintypes.LPCSTR, wintypes.BOOL]
    dbghelp.SymInitialize.restype = wintypes.BOOL
    dbghelp.SymLoadModuleEx.argtypes = [wintypes.HANDLE, wintypes.HANDLE, wintypes.LPCSTR,
                                      wintypes.LPCSTR, ctypes.c_ulonglong, wintypes.DWORD,
                                      ctypes.c_void_p, wintypes.DWORD]
    dbghelp.SymLoadModuleEx.restype = ctypes.c_ulonglong

    class SymbolInfo(ctypes.Structure):
        _fields_ = [('SizeOfStruct', wintypes.ULONG), ('TypeIndex', wintypes.ULONG),
                    ('Reserved', ctypes.c_ulonglong * 2), ('Index', wintypes.ULONG),
                    ('Size', wintypes.ULONG), ('ModBase', ctypes.c_ulonglong), ('Flags', wintypes.ULONG),
                    ('Value', ctypes.c_ulonglong), ('Address', ctypes.c_ulonglong), ('Register', wintypes.ULONG),
                    ('Scope', wintypes.ULONG), ('Tag', wintypes.ULONG), ('NameLen', wintypes.ULONG),
                    ('MaxNameLen', wintypes.ULONG), ('Name', ctypes.c_char * 1)]

    class ImageLine(ctypes.Structure):
        _fields_ = [('SizeOfStruct', wintypes.DWORD), ('Key', ctypes.c_void_p),
                    ('LineNumber', wintypes.DWORD), ('FileName', wintypes.LPSTR),
                    ('Address', ctypes.c_ulonglong)]

    dbghelp.SymFromName.argtypes = [wintypes.HANDLE, wintypes.LPCSTR, ctypes.POINTER(SymbolInfo)]
    dbghelp.SymFromName.restype = wintypes.BOOL
    dbghelp.SymGetLineFromAddr64.argtypes = [wintypes.HANDLE, ctypes.c_ulonglong,
                                          ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(ImageLine)]
    dbghelp.SymGetLineFromAddr64.restype = wintypes.BOOL
    dbghelp.SymCleanup.argtypes = [wintypes.HANDLE]
    dbghelp.SymCleanup.restype = wintypes.BOOL
    if not dbghelp.SymInitialize(process, os.fsencode(binary.parent), False):
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        if not dbghelp.SymLoadModuleEx(process, None, os.fsencode(binary), b'probe', 0, 0, None, 0):
            raise ctypes.WinError(ctypes.get_last_error())
        buffer = ctypes.create_string_buffer(ctypes.sizeof(SymbolInfo) + 1024)
        info = ctypes.cast(buffer, ctypes.POINTER(SymbolInfo))
        info.contents.SizeOfStruct = ctypes.sizeof(SymbolInfo)
        info.contents.MaxNameLen = 1024
        if not dbghelp.SymFromName(process, ('probe!' + symbol).encode('utf-8'), info):
            raise ctypes.WinError(ctypes.get_last_error())
        line = ImageLine()
        line.SizeOfStruct = ctypes.sizeof(ImageLine)
        displacement = wintypes.DWORD()
        if not dbghelp.SymGetLineFromAddr64(process, info.contents.Address,
                                          ctypes.byref(displacement), ctypes.byref(line)):
            raise ctypes.WinError(ctypes.get_last_error())
        return os.fsdecode(line.FileName), line.LineNumber
    finally:
        dbghelp.SymCleanup(process)


def linux_line(debug, symbol='newpage_symbol_line_probe'):
    for tool in ('nm', 'addr2line'):
        if not shutil.which(tool):
            raise RuntimeError(tool + ' is required for the native line probe')
    lines = subprocess.check_output(['nm', '--defined-only', str(debug)], text=True).splitlines()
    address = next(line.split()[0] for line in lines if line.split()[-1] == symbol)
    result = subprocess.check_output(['addr2line', '-e', str(debug), address], text=True).strip()
    source, line = result.rsplit(':', 1)
    return source, int(line.split()[0])


def llvm_windows_line(binary, symbolizer):
    # The probe explicitly exports its function, so its RVA is available without
    # relying on a platform debugger's PDB loading configuration.
    data = binary.read_bytes()
    header, = struct.unpack_from('<I', data, 0x3c)
    sections, = struct.unpack_from('<H', data, header + 6)
    optional_size, = struct.unpack_from('<H', data, header + 20)
    optional = header + 24
    export_rva, = struct.unpack_from('<I', data, optional + 112)

    def offset(rva):
        for index in range(sections):
            size, address, raw_size, raw = struct.unpack_from('<4I', data, optional + optional_size + index * 40 + 8)
            if address <= rva < address + max(size, raw_size):
                return raw + rva - address
        raise ValueError('Probe export is outside executable sections')

    exports = offset(export_rva)
    count, functions, names, ordinals = struct.unpack_from('<4I', data, exports + 24)
    for index in range(count):
        name_rva, = struct.unpack_from('<I', data, offset(names) + index * 4)
        name = data[offset(name_rva):].split(b'\0', 1)[0]
        if name == b'newpage_symbol_line_probe':
            ordinal, = struct.unpack_from('<H', data, offset(ordinals) + index * 2)
            address, = struct.unpack_from('<I', data, offset(functions) + ordinal * 4)
            result = subprocess.check_output([symbolizer, '--obj=' + str(binary), '--relative-address',
                                               '--output-style=JSON', hex(address)], text=True)
            record = json.loads(result)['Symbol'][0]
            return record['FileName'], record['Line']
    raise ValueError('Probe export is missing')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cmake', default='cmake')
    parser.add_argument('--symbolizer', help='Optional llvm-symbolizer for Windows PDB line lookup')
    parser.add_argument('--work-dir', type=Path, help='Retain the tiny probe build for diagnosis')
    parser.add_argument('--output', type=Path, help='Optional JSON evidence report')
    parser.add_argument('--dist', type=Path,
                        help='Resolve main/wmain in each actual built executable instead of building the tiny probe')
    args = parser.parse_args()
    if args.dist:
        platform = 'win64' if os.name == 'nt' else 'linux64'
        source_names = {'NewPageMergeMDL': 'mdlcompiler/main.cpp',
                        'NewPageMergeMDL-Decompiler': 'mdldecompiler/main.cpp',
                        'NewPageVRMLtoX3D': 'tools/vrml_converter/main.cpp'}
        entries = []
        for name in required_tools(platform):
            binary = args.dist.resolve() / name
            debug = args.dist.resolve() / symbol_path(name, platform)
            base = name.removesuffix('.exe')
            symbol = 'wmain' if os.name == 'nt' and base in ('NewPageVRMLtoX3D', 'subtools/ag2proportions') else 'main'
            identity = match_symbols(binary.read_bytes(), debug.read_bytes(), platform, debug.name)
            source, line = windows_line(binary, symbol) if os.name == 'nt' else linux_line(debug, symbol)
            expected = source_names.get(base, base + '/main.cpp')
            if not source.replace('\\', '/').endswith(expected) or line < 1:
                raise RuntimeError(f'{name}: entry point did not resolve to its source: {source}:{line}')
            entries.append({'binary': name, 'symbol': symbol, 'source': source, 'line': line, 'native_identity': identity})
        report = {'platform': platform, 'executables': entries,
                  'scope': 'Actual native executable entry points; not a claim that every optimized stack frame is recoverable.'}
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))
        return
    work = (contextlib.nullcontext(str(args.work_dir.resolve())) if args.work_dir
            else tempfile.TemporaryDirectory(prefix='newpage-symbol-lines-'))
    with work as directory:
        root = Path(directory)
        root.mkdir(parents=True, exist_ok=True)
        (root / 'probe.c').write_text(PROBE, encoding='utf-8')
        (root / 'CMakeLists.txt').write_text('''cmake_minimum_required(VERSION 3.22)
project(SymbolLineProbe LANGUAGES C CXX)
set(NEWPAGE_REPRODUCIBLE ON)
set(NEWPAGE_SEPARATE_SYMBOLS ON)
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")
set(CMAKE_RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/bin")
include("''' + (ROOT / 'cmake/BuildQuality.cmake').as_posix() + '''")
add_executable(probe probe.c)
newpage_separate_symbols(probe)
''', encoding='utf-8')
        build = root / 'build'
        subprocess.run([args.cmake, '-S', str(root), '-B', str(build), '-DCMAKE_BUILD_TYPE=Release'], check=True)
        subprocess.run([args.cmake, '--build', str(build), '--config', 'Release', '--parallel', '2'], check=True)
        platform = 'win64' if os.name == 'nt' else 'linux64'
        binary = build / 'bin' / ('probe.exe' if os.name == 'nt' else 'probe')
        debug = binary.with_suffix('.pdb') if os.name == 'nt' else Path(str(binary) + '.debug')
        identity = match_symbols(binary.read_bytes(), debug.read_bytes(), platform, debug.name)
        if os.name == 'nt':
            symbolizer = args.symbolizer or shutil.which('llvm-symbolizer')
            source, line = llvm_windows_line(binary, symbolizer) if symbolizer else windows_line(binary)
        else:
            source, line = linux_line(debug)
        if Path(source).name != 'probe.c' or line not in (6, 7, 8):
            raise RuntimeError(f'Probe did not resolve to its authored body: {source}:{line}')
        report = {'platform': platform, 'function': 'newpage_symbol_line_probe',
                  'source': source, 'line': line, 'native_identity': identity,
                  'scope': 'Tiny authored probe; production executable package identities are checked separately.'}
        if args.output:
            args.output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(report))


if __name__ == '__main__':
    main()
