"""Exercise real CONTENT wildcard, archive extraction and search precedence.

Build resource_lookup.cpp with mdlcompiler/resources.cpp, include libs and
mdlcompiler, then pass the executable to this script.
"""
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest

LOOKUP = None

def vpk(path, name, payload, preload=b'', chunk=False):
    tree = (b'txt\0 \0' + name.encode() + b'\0' +
            struct.pack('<IHHIIH', 0, len(preload), 0 if chunk else 0x7fff,
                        0, len(payload), 0xffff) + preload + b'\0\0\0')
    path.write_bytes(struct.pack('<III', 0x55aa1234, 1, len(tree)) + tree +
                     (b'' if chunk else payload))
    if chunk:
        path.with_name(path.stem.removesuffix('_dir') + '_000.vpk').write_bytes(payload)

def raw_vpk(path, entries):
    """Byte-key fixtures model legacy VPK names without decoding them on the host."""
    tree = bytearray()
    for directory, name, extension, payload in entries:
        tree.extend(extension + b'\0' + directory + b'\0' + name + b'\0')
        tree.extend(struct.pack('<IHHIIH', 0, len(payload), 0x7fff, 0, 0, 0xffff))
        tree.extend(payload + b'\0\0')
    tree.extend(b'\0')
    path.write_bytes(struct.pack('<III', 0x55aa1234, 1, len(tree)) + tree)

class ContentMounts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.game = self.root/'game'
        self.game.mkdir()
    def config(self, entries):
        paths='\n'.join(f'{kind} "{value}"' for kind,value in entries)
        (self.game/'gameinfo.txt').write_text('GameInfo { FileSystem { SteamAppId 730 SearchPaths { '+paths+' } } }')
    def lookup(self, name, content=True):
        return subprocess.run([LOOKUP,str(self.game),'content' if content else 'game',name],capture_output=True)
    def test_content_is_opt_in_and_wildcard_order_is_stable(self):
        for directory,value in [('b','second'),('a','first')]:
            p=self.root/'content'/directory;p.mkdir(parents=True)
            (p/'source.txt').write_text(value)
        self.config([('CONTENT','content/*')])
        self.assertEqual(self.lookup('source.txt',False).returncode,4)
        self.assertEqual(self.lookup('source.txt').stdout,b'first')
    def test_nested_patterns_and_unrelated_files(self):
        p=self.root/'content'/'author1'/'models';p.mkdir(parents=True)
        (p/'source.txt').write_text('nested')
        (self.root/'content'/'authorX.txt').write_text('ignored')
        self.config([('CONTENT','content/author?/models')])
        self.assertEqual(self.lookup('source.txt').stdout,b'nested')
    def test_vpk_pattern_preload_and_external_chunk(self):
        p=self.root/'content';p.mkdir()
        vpk(p/'sources_dir.vpk','source',b'payload',b'pre-',True)
        self.config([('CONTENT','content/*.vpk')])
        self.assertEqual(self.lookup('source.txt').stdout,b'pre-payload')
    def test_direct_archive_alias(self):
        vpk(self.root/'sources_dir.vpk','source',b'archive')
        self.config([('CONTENT','sources.vpk')])
        self.assertEqual(self.lookup('source.txt').stdout,b'archive')
    def test_non_utf8_vpk_names_do_not_block_other_resources(self):
        raw_vpk(self.root/'sources_dir.vpk', [
            (b'materials/dons_decals', b'serviet bug\xe9', b'vmt', b'legacy-name'),
            (b'materials/dons_decals', b'serviet bug\xe9', b'vtf', b'legacy-texture'),
            (b' ', b'source', b'txt', b'valid-resource')])
        self.config([('CONTENT','sources.vpk')])
        result = self.lookup('source.txt')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, b'valid-resource')
        self.assertEqual(self.lookup('missing.txt').returncode, 4)
    def test_vpk_byte_path_normalizes_separators_and_parent_segments(self):
        raw_vpk(self.root/'sources_dir.vpk', [
            (b'Folder\\ignored/..//.', b'SoUrCe', b'txt', b'normalized')])
        self.config([('CONTENT','sources.vpk')])
        self.assertEqual(self.lookup('folder/source.txt').stdout, b'normalized')
    def test_vpk_byte_paths_reject_escape_absolute_and_drive_names(self):
        self.config([('CONTENT','sources.vpk')])
        for directory in (b'../outside', b'/absolute', b'C:/drive', b'\\\\server\\share', b'safe/../../outside', b'safe:stream'):
            with self.subTest(directory=directory):
                raw_vpk(self.root/'sources_dir.vpk', [(directory, b'source', b'txt', b'unsafe')])
                result = self.lookup('source.txt')
                self.assertNotEqual(result.returncode, 0)
                self.assertIn(b'unsafe VPK path', result.stderr)
    def test_loose_precedes_directory_archive(self):
        p=self.root/'content';p.mkdir()
        (p/'source.txt').write_text('loose')
        vpk(p/'sources_dir.vpk','source',b'archive')
        self.config([('CONTENT','content')])
        self.assertEqual(self.lookup('source.txt').stdout,b'loose')
    def test_game_precedes_content_and_parent_paths_are_rejected(self):
        (self.game/'source.txt').write_text('game')
        p=self.root/'content';p.mkdir();(p/'source.txt').write_text('content')
        self.config([('GAME','|gameinfo_path|.'),('CONTENT','content')])
        self.assertEqual(self.lookup('source.txt').stdout,b'game')
        self.assertEqual(self.lookup('../content/source.txt').returncode,4)

if __name__=='__main__':
    LOOKUP = str(Path(sys.argv.pop(1)).resolve())
    unittest.main()
