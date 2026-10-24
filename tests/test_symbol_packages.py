"""Offline symbol packaging contracts, including rejection of stale native symbols."""
import binascii
import io
import json
from pathlib import Path
import struct
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '.github/scripts'))
import package_symbols as symbols
import upstream_release as upstream
from symbol_line_probe import linux_line, llvm_source_line


def pdb(guid=b'0123456789abcdef', age=1):
    data = bytearray(5 * 512)
    data[:32] = b'Microsoft C/C++ MSF 7.00\r\n\x1aDS\0\0\0'
    struct.pack_into('<6I', data, 32, 512, 1, 5, 16, 0, 2)
    struct.pack_into('<I', data, 1024, 3)
    struct.pack_into('<4I', data, 1536, 2, 0, 28, 4)
    struct.pack_into('<3I16s', data, 2048, 20000404, 0, age, guid)
    return bytes(data)


def pe(guid=b'0123456789abcdef', age=1, pdb_name='probe.pdb'):
    data = bytearray(1024)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 0x3c, 0x80)
    data[0x80:0x84] = b'PE\0\0'
    struct.pack_into('<HHIIIHH', data, 0x84, 0x8664, 1, 0, 0, 0, 240, 2)
    struct.pack_into('<H', data, 0x98, 0x20b)
    struct.pack_into('<II', data, 0x98 + 112 + 6 * 8, 0x1000, 28)
    struct.pack_into('<8s4I', data, 0x98 + 240, b'.rdata\0\0', 512, 0x1000, 512, 512)
    record = b'RSDS' + guid + struct.pack('<I', age) + pdb_name.encode() + b'\0'
    struct.pack_into('<IIHHIIII', data, 512, 0, 0, 0, 0, 2, len(record), 0x1040, 576)
    data[576:576 + len(record)] = record
    return bytes(data)


def elf(payload):
    """Small ELF64 fixture with an ordinary section table, not a real program."""
    names = b'\0.shstrtab\0' + b''.join(name.encode() + b'\0' for name in payload)
    entries = [('.shstrtab', names), *payload.items()]
    data = bytearray(64)
    headers = [bytes(64)]
    for name, value in entries:
        offset = len(data)
        data.extend(value)
        headers.append(struct.pack('<IIQQQQIIQQ', names.index(name.encode()), 1, 0, 0,
                                   offset, len(value), 0, 0, 1, 0))
    section_offset = len(data)
    data.extend(b''.join(headers))
    data[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', data, 16, 2, 62, 1, 0, 0, section_offset, 0,
                     64, 0, 0, 64, len(headers), 1)
    return bytes(data)


def elf_pair(name, build_id=b'0123456789abcdefghij'):
    note = struct.pack('<III', 4, len(build_id), 3) + b'GNU\0' + build_id
    debug = elf({'.note.gnu.build-id': note, '.debug_info': b'info', '.debug_line': b'lines'})
    link = name.encode() + b'\0'
    link += bytes((-len(link)) % 4) + struct.pack('<I', binascii.crc32(debug))
    binary = elf({'.note.gnu.build-id': note, '.gnu_debuglink': link})
    return binary, debug


def source_metadata():
    config = {'project_version': '1.2.38', 'pulsemodel': 'owner/pulse', 'pulse_base': 'b' * 40}
    patch = b'test source overlay\n'
    configuration = (json.dumps(config) + '\n').encode()
    state = {'schema': 1, 'controller_sha': 'a' * 40, 'project_version': '1.2.38',
             'pulsemodel': {'repo': config['pulsemodel'], 'sha': config['pulse_base']},
             'overlay_sha256': symbols.digest(patch), 'configuration_sha256': symbols.digest(configuration),
             'integration': {}}
    state['fingerprint'] = upstream.fingerprint(state)
    state['source_kind'] = 'maintained checkout'
    state['build'] = {'configuration': 'MinSizeRel', 'separate_symbols': True,
                      'compiler_id': 'MSVC', 'compiler_version': '19.51', 'reproducible': True}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w') as archive:
        archive.comment = state['controller_sha'].encode()
        archive.writestr(symbols.ROOT + 'CMakeLists.txt', 'project(NewPageMergeMDL VERSION 1.2.38 LANGUAGES CXX)')
        archive.writestr(symbols.ROOT + 'automation/upstreams.json', configuration)
        archive.writestr(symbols.ROOT + 'automation/compatibility.patch', patch)
    return state, buffer.getvalue()


def runtime_fixture(root, platform='win64'):
    dist = root / 'dist'
    dist.mkdir()
    runtime = root / 'runtime.zip'
    state, source = source_metadata()
    with upstream.ReproducibleZipFile(runtime, 'w') as archive:
        archive.writestr(symbols.ROOT + 'upstream-manifest.json', json.dumps(state))
        archive.writestr(symbols.ROOT + 'sources/NewPageMergeMDL-source.zip', source)
        for name in symbols.required_tools(platform):
            symbol = symbols.symbol_path(name, platform)
            binary, debug = ((pe(pdb_name=Path(symbol).name), pdb()) if platform == 'win64'
                             else elf_pair(Path(symbol).name))
            executable = dist / name
            executable.parent.mkdir(parents=True, exist_ok=True)
            executable.write_bytes(binary)
            (dist / symbol).write_bytes(debug)
            archive.writestr(symbols.ROOT + name, binary)
    return dist, runtime


def rewrite_zip(path, transform):
    with zipfile.ZipFile(path) as archive:
        members = {item.filename: archive.read(item) for item in archive.infolist()}
    transform(members)
    with zipfile.ZipFile(path, 'w') as archive:
        for name, value in members.items():
            archive.writestr(name, value)


class SymbolizerLocations(unittest.TestCase):
    def test_single_lookup_object_and_array_resolve_the_same_line(self):
        record = {'Address': '0x1000', 'Symbol': [{'FileName': 'src/probe.c', 'Line': 6}]}
        for output in (record, [record]):
            with self.subTest(output=output):
                self.assertEqual(llvm_source_line(json.dumps(output)), ('src/probe.c', 6))

    def test_empty_and_ambiguous_lookup_results_are_explicit_errors(self):
        record = {'Symbol': [{'FileName': 'src/probe.c', 'Line': 6}]}
        cases = (([], 'no lookup records'), ([record, record], 'ambiguous lookup records'),
                 ({'Symbol': []}, 'no source locations'),
                 ({'Symbol': record['Symbol'] * 2}, 'ambiguous source locations'))
        for output, message in cases:
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, message):
                llvm_source_line(json.dumps(output))

    def test_invalid_and_unresolved_locations_are_explicit_errors(self):
        for output in ('', 'not JSON'):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, 'invalid or empty JSON'):
                llvm_source_line(output)
        for output, message in ((None, 'record is not an object'),
                                ({'Error': {'Message': 'No symbols'}}, 'no source locations'),
                                ({'Symbol': [None]}, 'location is not an object')):
            with self.subTest(output=output), self.assertRaisesRegex(ValueError, message):
                llvm_source_line(json.dumps(output))
        for source, line in (('', 6), ('??', 0), ('src/probe.c', 0),
                             ('src/probe.c', True), ('src/probe.c', '6')):
            with self.subTest(source=source, line=line), self.assertRaisesRegex(ValueError, 'valid source file and line'):
                llvm_source_line(json.dumps({'Symbol': [{'FileName': source, 'Line': line}]}))


class LinuxSourceLines(unittest.TestCase):
    def lookup(self, locations, *, symbols='00001000 00000004 T main\n', expected='mdlcompiler/main.cpp'):
        queried = []

        def command(args, *, text, input=None):
            if args[0] == 'nm':
                return symbols
            self.assertEqual(args[:3], ['addr2line', '-e', 'compiler.debug'])
            addresses = [int(value, 16) for value in input.splitlines()]
            queried.extend(addresses)
            return ''.join(locations.get(address, '??:?') + '\n' for address in addresses)

        with mock.patch('symbol_line_probe.shutil.which', return_value='/usr/bin/tool'), \
                mock.patch('symbol_line_probe.subprocess.check_output', side_effect=command):
            result = linux_line(Path('compiler.debug'), 'main', expected)
        return result, queried

    def test_entry_address_remains_the_fast_path(self):
        result, queried = self.lookup({0x1000: 'src/mdlcompiler/main.cpp:123 (discriminator 2)'})
        self.assertEqual(result, ('src/mdlcompiler/main.cpp', 123))
        self.assertEqual(queried, [0x1000])

    def test_unknown_optimized_prologue_requires_a_real_line_inside_the_function(self):
        result, queried = self.lookup({0x1000: '??:?', 0x1001: 'src/mdlcompiler/main.cpp:0',
                                       0x1002: 'src/mdlcompiler/main.cpp:123'})
        self.assertEqual(result, ('src/mdlcompiler/main.cpp', 123))
        self.assertIn(0x1002, queried)
        self.assertTrue(all(0x1000 <= address < 0x1004 for address in queried))

    def test_inlined_header_line_does_not_replace_expected_entry_point_source(self):
        result, _ = self.lookup({0x1000: '/usr/include/c++/13/string:45',
                                 0x1001: 'src/mdlcompiler/main.cpp:123'})
        self.assertEqual(result, ('src/mdlcompiler/main.cpp', 123))
        with self.assertRaisesRegex(RuntimeError, 'valid source file and line in mdlcompiler/main.cpp'):
            self.lookup({0x1000: '/usr/include/c++/13/string:45'})

    def test_unknown_zero_and_adjacent_function_lines_cannot_pass(self):
        # The valid line is exactly outside main's half-open range and must not
        # be used as evidence for main, even if it is in the same source file.
        locations = {0x1000: '??:?', 0x1001: '??:23', 0x1002: 'src/mdlcompiler/main.cpp:0',
                     0x1003: 'src/mdlcompiler/main.cpp:?', 0x1004: 'src/mdlcompiler/main.cpp:124'}
        with self.assertRaisesRegex(RuntimeError, r"main.*within \[0x1000, 0x1004\)"):
            self.lookup(locations, symbols='00001000 00000004 T main\n00001004 00000008 T next\n')

    def test_missing_ambiguous_and_unsized_symbols_cannot_pass(self):
        for symbols in ('00001000 00000004 T other\n', '00001000 T main\n',
                        '00001000 00000004 D main\n',
                        '00001000 00000004 T main\n00002000 00000004 T main\n'):
            with self.subTest(symbols=symbols), self.assertRaisesRegex(RuntimeError, 'unique sized text symbol'):
                self.lookup({}, symbols=symbols)
        with self.assertRaisesRegex(RuntimeError, 'no address range'):
            self.lookup({}, symbols='00001000 00000000 T main\n')

    def test_empty_addr2line_output_cannot_pass(self):
        with mock.patch('symbol_line_probe.shutil.which', return_value='/usr/bin/tool'), \
                mock.patch('symbol_line_probe.subprocess.check_output',
                           side_effect=['00001000 00000004 T main\n', '']), \
                self.assertRaisesRegex(RuntimeError, 'unexpected number of locations'):
            linux_line(Path('compiler.debug'), 'main')


class NativeIdentities(unittest.TestCase):
    def test_stale_pdb_guid_and_age_are_rejected(self):
        self.assertEqual(symbols.match_symbols(pe(), pdb(), 'win64', 'probe.pdb')['age'], 1)
        for debug in (pdb(guid=b'x' * 16), pdb(age=2)):
            with self.subTest(debug=debug[2048:2076]), self.assertRaisesRegex(ValueError, 'GUID/age'):
                symbols.match_symbols(pe(), debug, 'win64', 'probe.pdb')

    def test_incorrect_embedded_pdb_name_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'PDB filename'):
            symbols.match_symbols(pe(pdb_name='%%%probe.pdb%%%'), pdb(), 'win64', 'probe.pdb')

    def test_split_elf_requires_matching_build_id_crc_and_lines(self):
        binary, debug = elf_pair('probe.debug')
        self.assertEqual(symbols.match_symbols(binary, debug, 'linux64', 'probe.debug')['format'], 'elf')
        _, wrong_build = elf_pair('probe.debug', b'x' * 20)
        for payload, message in ((wrong_build, 'build ID'), (debug.replace(b'lines', b'wrong'), 'CRC')):
            with self.subTest(message=message), self.assertRaisesRegex(ValueError, message):
                symbols.match_symbols(binary, payload, 'linux64', 'probe.debug')
        with self.assertRaisesRegex(ValueError, 'filename'):
            symbols.match_symbols(binary, debug, 'linux64', 'different.debug')
        _, sections = symbols.elf_sections(debug)
        no_lines = elf({'.note.gnu.build-id': sections['.note.gnu.build-id'], '.debug_info': b'info'})
        with self.assertRaisesRegex(ValueError, 'source/line'):
            symbols.match_symbols(binary, no_lines, 'linux64', 'probe.debug')
        _, sections = symbols.elf_sections(binary)
        unstripped = elf({'.note.gnu.build-id': sections['.note.gnu.build-id'],
                          '.gnu_debuglink': sections['.gnu_debuglink'], '.debug_line': b'lines'})
        with self.assertRaisesRegex(ValueError, 'Runtime ELF'):
            symbols.match_symbols(unstripped, debug, 'linux64', 'probe.debug')

    def test_truncated_symbol_data_is_rejected(self):
        for data in (pdb()[:100], pdb()[:-1]):
            with self.assertRaises(ValueError):
                symbols.pdb_identity(data)
        with self.assertRaises(ValueError):
            symbols.pe_identity(pe()[:100])


class SymbolArchives(unittest.TestCase):
    def test_each_platform_has_exact_symbol_coverage_and_reproducible_bytes(self):
        for platform in ('win64', 'linux64'):
            with self.subTest(platform=platform), tempfile.TemporaryDirectory() as folder:
                root = Path(folder)
                dist, runtime = runtime_fixture(root, platform)
                outputs = [root / name for name in ('first.zip', 'second.zip')]
                for output in outputs:
                    manifest = symbols.package(dist, runtime, platform, output)
                    self.assertEqual(manifest['source']['controller_sha'], 'a' * 40)
                    self.assertEqual(manifest['runtime_archive_sha256'], upstream.sha256(runtime))
                    self.assertEqual(len(manifest['executables']), 7)
                    symbols.verify(runtime, output)
                self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())
                with zipfile.ZipFile(outputs[0]) as archive:
                    self.assertEqual(len(archive.namelist()), 8)
                    self.assertFalse(any(name.endswith('.exe') for name in archive.namelist()))
                with zipfile.ZipFile(runtime) as archive:
                    self.assertFalse(any(name.endswith(('.pdb', '.debug')) for name in archive.namelist()))

    def test_changed_staged_executable_cannot_claim_runtime_association(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, runtime = runtime_fixture(root)
            with (dist / 'NewPageMergeMDL.exe').open('ab') as stream:
                stream.write(b'changed')
            with self.assertRaisesRegex(ValueError, 'differs from runtime'):
                symbols.package(dist, runtime, 'win64', root / 'symbols.zip')
            self.assertFalse((root / 'symbols.zip').exists())
            self.assertFalse(list(root.glob('*.tmp')))

    def test_stale_symbols_do_not_replace_previous_archive(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, runtime = runtime_fixture(root)
            output = root / 'symbols.zip'
            output.write_bytes(b'previous good package')
            (dist / 'NewPageMergeMDL.pdb').write_bytes(pdb(age=5))
            with self.assertRaisesRegex(ValueError, 'GUID/age'):
                symbols.package(dist, runtime, 'win64', output)
            self.assertEqual(output.read_bytes(), b'previous good package')

    def test_tampered_symbol_payload_and_manifest_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, runtime = runtime_fixture(root)
            output = root / 'symbols.zip'
            symbols.package(dist, runtime, 'win64', output)
            rewrite_zip(output, lambda members: members.__setitem__(
                symbols.SYMBOL_ROOT + 'NewPageMergeMDL.pdb', pdb(age=4)))
            with self.assertRaisesRegex(ValueError, 'checksum'):
                symbols.verify(runtime, output)
            symbols.package(dist, runtime, 'win64', output)
            def change_source(members):
                manifest = json.loads(members[symbols.MANIFEST])
                manifest['source']['controller_sha'] = 'c' * 40
                members[symbols.MANIFEST] = json.dumps(manifest).encode()
            rewrite_zip(output, change_source)
            with self.assertRaisesRegex(ValueError, 'provenance'):
                symbols.verify(runtime, output)

    def test_symbols_and_runtime_archives_cannot_be_interchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, runtime = runtime_fixture(root)
            output = root / 'symbols.zip'
            symbols.package(dist, runtime, 'win64', output)
            with zipfile.ZipFile(runtime, 'a') as archive:
                archive.writestr(symbols.ROOT + 'README.md', 'changed runtime packaging')
            with self.assertRaisesRegex(ValueError, 'different runtime ZIP'):
                symbols.verify(runtime, output)
            with zipfile.ZipFile(runtime, 'a') as archive:
                archive.writestr(symbols.ROOT + 'accidental.pdb', pdb())
            with self.assertRaisesRegex(ValueError, 'Runtime ZIP contains'):
                symbols.package(dist, runtime, 'win64', output)

    def test_missing_symbols_are_a_hard_failure(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            dist, runtime = runtime_fixture(root)
            (dist / 'subtools/meshtool.pdb').unlink()
            with self.assertRaises(FileNotFoundError):
                symbols.package(dist, runtime, 'win64', root / 'symbols.zip')


if __name__ == '__main__':
    unittest.main()
