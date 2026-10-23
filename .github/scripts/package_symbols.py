#!/usr/bin/env python3
"""Package and verify native symbols against the exact distributed runtime ZIP."""
import argparse
import binascii
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import struct
import tempfile
import uuid
import zipfile

from upstream_release import ReproducibleZipFile, sha256, verified_package_manifest

ROOT = 'NewPageMergeMDL/'
SYMBOL_ROOT = 'NewPageMergeMDL-symbols/'
MANIFEST = SYMBOL_ROOT + 'symbols-manifest.json'
PROJECT_TOOLS = ('NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D',
                 'subtools/ag2proportions', 'subtools/l4d_animswap',
                 'subtools/meshtool', 'subtools/vmd2valvebiped')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def span(data, offset, size):
    if offset < 0 or size < 0 or offset + size > len(data):
        raise ValueError('Truncated native symbol data')
    return data[offset:offset + size]


def unpack(fmt, data, offset):
    return struct.unpack(fmt, span(data, offset, struct.calcsize(fmt)))


def pdb_identity(data):
    """Read the PDB info stream in an MSF 7 file (modern MSVC/LLVM PDB)."""
    if span(data, 0, 32) != b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0':
        raise ValueError('Expected a complete MSF 7 PDB')
    block_size, _, blocks, directory_size, _, block_map = unpack('<6I', data, 32)
    if block_size not in (512, 1024, 2048, 4096, 8192, 16384, 32768) or blocks * block_size != len(data):
        raise ValueError('Invalid PDB block geometry')

    def read_blocks(indices, size):
        if any(index >= blocks for index in indices):
            raise ValueError('Invalid PDB block index')
        return b''.join(span(data, index * block_size, block_size) for index in indices)[:size]

    count = (directory_size + block_size - 1) // block_size
    directory = read_blocks(unpack('<' + str(count) + 'I', data, block_map * block_size), directory_size)
    stream_count, = unpack('<I', directory, 0)
    if stream_count < 2 or stream_count > len(directory) // 4:
        raise ValueError('Missing PDB info stream')
    sizes = unpack('<' + str(stream_count) + 'I', directory, 4)
    cursor = 4 + stream_count * 4
    for index, size in enumerate(sizes):
        count = 0 if size == 0xffffffff else (size + block_size - 1) // block_size
        indices = unpack('<' + str(count) + 'I', directory, cursor)
        cursor += count * 4
        if index == 1:
            info = read_blocks(indices, size)
            _, _, age = unpack('<3I', info, 0)
            return {'format': 'pdb', 'guid': uuid.UUID(bytes_le=span(info, 12, 16)).hex, 'age': age}
    raise ValueError('Missing PDB identity')


def pe_identity(data):
    if span(data, 0, 2) != b'MZ':
        raise ValueError('Expected a PE executable')
    header, = unpack('<I', data, 0x3c)
    if span(data, header, 4) != b'PE\0\0':
        raise ValueError('Invalid PE header')
    sections, = unpack('<H', data, header + 6)
    optional_size, = unpack('<H', data, header + 20)
    optional = header + 24
    magic, = unpack('<H', data, optional)
    if magic not in (0x10b, 0x20b):
        raise ValueError('Unsupported PE optional header')
    directory = optional + (112 if magic == 0x20b else 96)
    debug_rva, debug_size = unpack('<II', data, directory + 6 * 8)
    for index in range(sections):
        entry = optional + optional_size + index * 40
        virtual_size, virtual_address, raw_size, raw_pointer = unpack('<4I', data, entry + 8)
        if virtual_address <= debug_rva < virtual_address + max(virtual_size, raw_size):
            debug_offset = raw_pointer + debug_rva - virtual_address
            if not debug_size or debug_size % 28:
                raise ValueError('Invalid PE debug directory')
            for offset in range(debug_offset, debug_offset + debug_size, 28):
                _, _, _, _, kind, size, _, pointer = unpack('<IIHHIIII', data, offset)
                if kind != 2:
                    continue
                record = span(data, pointer, size)
                if record[:4] == b'RSDS':
                    age, = unpack('<I', record, 20)
                    path = record[24:].split(b'\0', 1)[0].decode('utf-8')
                    return {'format': 'pdb', 'guid': uuid.UUID(bytes_le=span(record, 4, 16)).hex,
                            'age': age, 'pdb_name': path.replace('\\', '/').rsplit('/', 1)[-1]}
    raise ValueError('Executable has no RSDS PDB identity')


def elf_sections(data):
    if span(data, 0, 4) != b'\x7fELF' or data[4] not in (1, 2) or data[5] not in (1, 2):
        raise ValueError('Expected an ELF executable or debug file')
    endian = '<' if data[5] == 1 else '>'
    if data[4] == 2:
        offset, = unpack(endian + 'Q', data, 40)
        size, count, strings_index = unpack(endian + 'HHH', data, 58)
        fmt = endian + 'IIQQQQIIQQ'
    else:
        offset, = unpack(endian + 'I', data, 32)
        size, count, strings_index = unpack(endian + 'HHH', data, 46)
        fmt = endian + 'IIIIIIIIII'
    if size < struct.calcsize(fmt) or not count or strings_index >= count:
        raise ValueError('Unsupported ELF section table')
    headers = [unpack(fmt, data, offset + index * size) for index in range(count)]
    strings = span(data, headers[strings_index][4], headers[strings_index][5])
    sections = {}
    for entry in headers:
        name = strings[entry[0]:].split(b'\0', 1)[0].decode('ascii')
        if entry[1] != 8:  # SHT_NOBITS has no file contents in split debug files.
            sections[name] = span(data, entry[4], entry[5])
    return endian, sections


def elf_build_id(endian, sections):
    notes = sections.get('.note.gnu.build-id', b'')
    cursor = 0
    while cursor < len(notes):
        namesize, descsize, kind = unpack(endian + 'III', notes, cursor)
        name = span(notes, cursor + 12, namesize)
        desc = span(notes, cursor + 12 + ((namesize + 3) & ~3), descsize)
        if name == b'GNU\0' and kind == 3 and desc:
            return desc.hex()
        cursor += 12 + ((namesize + 3) & ~3) + ((descsize + 3) & ~3)
    raise ValueError('ELF file has no GNU build ID')


def match_symbols(binary, symbols, platform, symbol_name):
    if platform == 'win64':
        expected, actual = pe_identity(binary), pdb_identity(symbols)
        if expected['pdb_name'] != PurePosixPath(symbol_name).name:
            raise ValueError('Executable PDB filename does not match symbol file: ' + symbol_name)
        if {key: value for key, value in expected.items() if key != 'pdb_name'} != actual:
            raise ValueError('PDB GUID/age does not match executable: ' + symbol_name)
        return expected
    endian, sections = elf_sections(binary)
    debug_endian, debug_sections = elf_sections(symbols)
    expected = elf_build_id(endian, sections)
    if elf_build_id(debug_endian, debug_sections) != expected:
        raise ValueError('ELF build ID does not match executable: ' + symbol_name)
    if '.debug_info' in sections or '.debug_line' in sections:
        raise ValueError('Runtime ELF still contains debug information')
    if not debug_sections.get('.debug_info') or not debug_sections.get('.debug_line'):
        raise ValueError('Separate ELF symbols have no source/line debug information')
    link = sections.get('.gnu_debuglink', b'')
    end = link.find(b'\0')
    if end < 0 or link[:end].decode('utf-8') != PurePosixPath(symbol_name).name:
        raise ValueError('ELF debuglink filename does not match symbol file')
    crc, = unpack(endian + 'I', link, (end + 4) & ~3)
    if crc != binascii.crc32(symbols) & 0xffffffff:
        raise ValueError('ELF debuglink CRC does not match symbol file')
    return {'format': 'elf', 'build_id': expected, 'debuglink_crc32': f'{crc:08x}'}


def safe_members(archive, prefix):
    names = archive.namelist()
    if len(names) != len(set(names)):
        raise ValueError('Duplicate ZIP members')
    for name in names:
        path = PurePosixPath(name)
        if (not name.startswith(prefix) or path.is_absolute() or '..' in path.parts
                or '\\' in name or ':' in name):
            raise ValueError('Unsafe ZIP member: ' + name)
    return names


def runtime_metadata(runtime, platform):
    names = safe_members(runtime, ROOT)
    if any(PurePosixPath(name).suffix.lower() in ('.pdb', '.debug', '.ilk') for name in names):
        raise ValueError('Runtime ZIP contains development symbols')
    raw = runtime.read(ROOT + 'upstream-manifest.json')
    manifest = json.loads(raw)
    if not manifest.get('build', {}).get('separate_symbols'):
        raise ValueError('Runtime manifest must record separate_symbols=true')
    source_archive = runtime.read(ROOT + 'sources/NewPageMergeMDL-source.zip')
    verified = verified_package_manifest(runtime, manifest)
    source_fields = ('controller_sha', 'fingerprint', 'project_version', 'pulsemodel', 'overlay_sha256',
                     'configuration_sha256', 'build_overlay_sha256', 'source_kind', '_verified_source_tree_sha256')
    result = {'schema': 1, 'platform': platform, 'build': manifest['build'],
              'source': {name: verified[name] for name in source_fields if name in verified},
              'upstream_manifest_sha256': digest(raw), 'source_archive_sha256': digest(source_archive),
              'executables': [], 'excluded_runtime_executables': []}
    if platform == 'win64':
        result['excluded_runtime_executables'] = [
            {'path': 'NewPageMergeMDL-C4D.exe', 'reason': 'Pinned external helper; symbols not built from this source.'}]
    return result


def required_tools(platform):
    return [name + ('.exe' if platform == 'win64' else '') for name in PROJECT_TOOLS]


def symbol_path(executable, platform):
    return str(PurePosixPath(executable).with_suffix('.pdb')) if platform == 'win64' else executable + '.debug'


def verify(runtime_path, symbols_path):
    with zipfile.ZipFile(runtime_path) as runtime, zipfile.ZipFile(symbols_path) as symbols:
        names = safe_members(symbols, SYMBOL_ROOT)
        manifest = json.loads(symbols.read(MANIFEST))
        platform = manifest.get('platform')
        if platform not in ('win64', 'linux64'):
            raise ValueError('Invalid symbols platform')
        expected = runtime_metadata(runtime, platform)
        for key in expected.keys() - {'executables'}:
            if manifest.get(key) != expected[key]:
                raise ValueError('Symbol provenance does not match runtime: ' + key)
        if manifest.get('runtime_archive_sha256') != sha256(runtime_path):
            raise ValueError('Symbol archive is associated with a different runtime ZIP')
        entries = manifest.get('executables', [])
        if sorted(entry['path'] for entry in entries) != sorted(required_tools(platform)):
            raise ValueError('Symbol manifest must cover every project-built executable exactly once')
        expected_members = {MANIFEST}
        for entry in entries:
            path = symbol_path(entry['path'], platform)
            expected_members.add(SYMBOL_ROOT + path)
            binary = runtime.read(ROOT + entry['path'])
            debug = symbols.read(SYMBOL_ROOT + path)
            if entry.get('symbol_path') != path or entry.get('executable_sha256') != digest(binary):
                raise ValueError('Executable association does not match: ' + entry['path'])
            if entry.get('symbol_sha256') != digest(debug):
                raise ValueError('Symbol checksum does not match: ' + path)
            if entry.get('native_identity') != match_symbols(binary, debug, platform, path):
                raise ValueError('Recorded native identity does not match: ' + path)
        if set(names) != expected_members:
            raise ValueError('Unexpected symbol archive contents')
    return manifest


def package(dist, runtime_path, platform, output):
    dist, output = Path(dist), Path(output)
    if output.resolve() == Path(runtime_path).resolve():
        raise ValueError('Symbols output must differ from runtime ZIP')
    # Stage atomically so failed validation never leaves a publishable partial ZIP.
    descriptor, pending = tempfile.mkstemp(prefix=output.name + '.', suffix='.tmp', dir=output.parent)
    os.close(descriptor)
    try:
        with zipfile.ZipFile(runtime_path) as runtime, ReproducibleZipFile(
                pending, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as symbols:
            manifest = runtime_metadata(runtime, platform)
            manifest['runtime_archive_sha256'] = sha256(runtime_path)
            for executable in required_tools(platform):
                binary = runtime.read(ROOT + executable)
                if sha256(dist / executable) != digest(binary):
                    raise ValueError('Staged executable differs from runtime ZIP: ' + executable)
                name = symbol_path(executable, platform)
                debug = (dist / name).read_bytes()
                identity = match_symbols(binary, debug, platform, name)
                manifest['executables'].append({'path': executable, 'symbol_path': name,
                                                'executable_sha256': digest(binary),
                                                'symbol_sha256': digest(debug), 'native_identity': identity})
                symbols.writestr(SYMBOL_ROOT + name, debug)
            symbols.writestr(MANIFEST, json.dumps(manifest, indent=2, sort_keys=True) + '\n')
        verify(runtime_path, pending)
        os.replace(pending, output)
    finally:
        if os.path.exists(pending):
            os.unlink(pending)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('package')
    create.add_argument('--dist', type=Path, required=True)
    create.add_argument('--runtime', type=Path, required=True)
    create.add_argument('--platform', choices=('win64', 'linux64'), required=True)
    create.add_argument('--output', type=Path, required=True)
    check = commands.add_parser('verify')
    check.add_argument('--runtime', type=Path, required=True)
    check.add_argument('--symbols', type=Path, required=True)
    args = parser.parse_args()
    manifest = (package(args.dist, args.runtime, args.platform, args.output) if args.command == 'package'
                else verify(args.runtime, args.symbols))
    print(json.dumps({'platform': manifest['platform'], 'executables': len(manifest['executables']),
                      'runtime_archive_sha256': manifest['runtime_archive_sha256']}))


if __name__ == '__main__':
    main()
