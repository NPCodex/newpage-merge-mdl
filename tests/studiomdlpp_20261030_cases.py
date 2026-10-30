"""Authored regressions for the supplied StudioMDL++ screenshot gaps."""
import os
import struct

from procedural_cases import skeletal_smd


class StudioMdlPp20261030Cases:
    def test_spp_late_weightlist_error_retains_nested_macro_include_provenance(self):
        base = '$modelname provenance\n$body m mesh.smd\n$sequence idle mesh.smd\n'
        self.scene_qc(base)
        before = {p: p.read_bytes() for p in (self.root / 'models').glob('provenance.*')}
        self.write('outer/one.qci', '$include two.qci\n')
        self.write('outer/two.qci', '$definemacro emit\n$sequence idle mesh.smd {\n'
                   '  weightlist missing_mask\n}\n$endmacro\n$emit')
        result = self.scene_qc('$modelname provenance\n$body m mesh.smd\n$include outer/one.qci\n',
                               success=False).replace('\\', '/')
        self.assertIn('two.qci(3,14): unknown weightlist "missing_mask"', result)
        self.assertIn('      weightlist missing_mask\n                 ^', result)
        self.assertIn('expanded $emit at ' + (self.root / 'outer/two.qci').as_posix() + '(6)', result)
        self.assertIn('included from ' + (self.root / 'outer/one.qci').as_posix() + '(1)', result)
        self.assertIn('included from ' + (self.root / 'scene.qc').as_posix() + '(3)', result)
        self.assertEqual({p: p.read_bytes() for p in before}, before)

    def test_spp_weightlist_in_named_animation_and_cmdlist_keeps_definition_site(self):
        self.write('commands.qci', '$cmdlist mask {\n weightlist missing\n}\n')
        for animation in ('$animation clip mesh.smd { cmdlist mask }\n$sequence idle clip\n',
                          '$sequence idle mesh.smd\n$append idle { cmdlist mask }\n'):
            with self.subTest(animation=animation):
                result = self.scene_qc('$modelname missing\n$body m mesh.smd\n'
                                       '$include commands.qci\n' + animation, success=False)
                self.assertIn('commands.qci(2,13): unknown weightlist "missing"', result)
                self.assertIn('included from ', result)

    def test_spp_forward_declared_weightlist_still_resolves(self):
        self.scene_qc('$modelname forward_mask\n$body m mesh.smd\n'
                      '$sequence idle mesh.smd weightlist later\n$weightlist later { root .25 }\n')
        data = self.mdl('forward_mask')
        seq = struct.unpack_from('<i', data, 192)[0]
        weights = seq + struct.unpack_from('<i', data, seq + 156)[0]
        self.assertAlmostEqual(struct.unpack_from('<f', data, weights)[0], .25)

    def spp_ik_fixture(self, upper, lower):
        self.write('limb.smd', skeletal_smd(['root', 'knee', 'foot'], [-1, 0, 1],
                   [(0, 0, 0), upper, lower], [(0, 0, 0)] * 3))
        return self.scene_qc('$modelname limb\n$bonecullmethod none\n$body m limb.smd\n'
                             '$sequence idle limb.smd\n$ikchain leg foot\n')

    def test_spp_zero_and_near_zero_ik_segments_warn_without_rejecting(self):
        for upper, lower in (((0,0,0),(0,0,0)), ((0,0,0),(0,4,0)),
                             ((0,4,0),(0,0,0)), ((0,5e-7,0),(0,4,0))):
            with self.subTest(upper=upper, lower=lower):
                result = self.spp_ik_fixture(upper, lower)
                self.assertEqual(result.count("WARNING: degenerate IK chain 'leg'"), 1)
                self.assertIn("'root' -> 'knee' -> 'foot'", result)
                self.assertTrue(self.mdl('limb').startswith(b'IDST'))

    def test_spp_valid_straight_bent_and_short_ik_segments_do_not_warn(self):
        for upper, lower in (((0,4,0),(0,4,0)), ((0,4,0),(3,3,0)),
                             ((0,1e-5,0),(0,1e-5,0))):
            with self.subTest(upper=upper, lower=lower):
                self.assertNotIn('degenerate IK chain', self.spp_ik_fixture(upper, lower))

    def test_spp_case_mismatch_file_directory_and_include_warn_once(self):
        if os.name != 'nt':
            self.skipTest('Accepted case mismatch is a Windows filesystem diagnostic')
        self.write('Assets/Mesh.SMD', (self.root / 'mesh.smd').read_text())
        self.write('Commands.QCI', '$body m assets/mesh.smd\n')
        if not (self.root / 'assets/mesh.smd').exists():
            self.skipTest('Filesystem is case sensitive')
        result = self.scene_qc('$modelname caseprobe\n$include commands.qci\n'
                               '$sequence idle assets/mesh.smd\n')
        warnings = [line for line in result.splitlines() if 'WARNING: file case mismatch:' in line]
        self.assertEqual(len(warnings), 2, result)
        self.assertTrue(any('Commands.QCI' in line and 'commands.qci' in line for line in warnings))
        self.assertTrue(any('Assets' in line and 'Mesh.SMD' in line for line in warnings))
        self.assertIn('may fail on Linux', result)
        first = self.mdl('caseprobe')
        exact = self.scene_qc('$modelname caseprobe\n$body m Assets/Mesh.SMD\n'
                              '$sequence idle Assets/Mesh.SMD\n')
        self.assertNotIn('file case mismatch:', exact)
        self.assertEqual(self.mdl('caseprobe'), first)

    def test_spp_exact_case_unicode_spaces_and_missing_sources(self):
        self.write('模型 Files/Mesh.SMD', (self.root / 'mesh.smd').read_text())
        result = self.scene_qc('$modelname unicode_case\n$body m "模型 Files/Mesh.SMD"\n'
                               '$sequence idle "模型 Files/Mesh.SMD"\n')
        self.assertNotIn('file case mismatch:', result)
        before = self.mdl('unicode_case')
        result = self.scene_qc('$modelname unicode_case\n$body m nonexistent.smd\n', success=False)
        self.assertIn('cannot find', result)
        self.assertNotIn('file case mismatch:', result)
        self.assertEqual(self.mdl('unicode_case'), before)

    def test_spp_mounted_loose_file_case_mismatch_is_also_diagnosed(self):
        if os.name != 'nt':
            self.skipTest('Accepted case mismatch is a Windows filesystem diagnostic')
        self.write('ContentRoot/Models/Case.SMD', (self.root / 'mesh.smd').read_text())
        if not (self.root / 'ContentRoot/models/case.smd').exists():
            self.skipTest('Filesystem is case sensitive')
        self.write('gameinfo.txt', 'GameInfo { game fixture FileSystem { SteamAppId 220 '
                   'SearchPaths { Game "|gameinfo_path|ContentRoot" } } }')
        result = self.scene_qc('$modelname mounted_case\n$body m models/case.smd\n'
                               '$sequence idle models/case.smd\n')
        self.assertEqual(result.count('WARNING: file case mismatch:'), 1, result)
        self.assertIn('Case.SMD', result)

    def test_spp_short_parent_alias_does_not_hide_leaf_case_mismatch(self):
        if os.name != 'nt':
            self.skipTest('DOS short aliases are Windows-specific')
        import ctypes
        from pathlib import Path
        parent = self.root / 'Long parent directory for case diagnostic'
        parent.mkdir()
        self.write('Long parent directory for case diagnostic/Mesh.SMD',
                   (self.root / 'mesh.smd').read_text())
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetShortPathNameW(str(parent), buffer, len(buffer))
        if not length or length >= len(buffer) or '~' not in buffer.value:
            self.skipTest('DOS short aliases are unavailable on this filesystem')
        original = self.root
        try:
            self.root = Path(buffer.value)
            result = self.scene_qc('$modelname short_alias\n$body m mesh.smd\n'
                                   '$sequence idle mesh.smd\n')
            self.assertEqual(result.count('WARNING: file case mismatch:'), 1, result)
            self.assertIn('Mesh.SMD', result)
            result = self.scene_qc('$modelname short_alias\n$body m Mesh.SMD\n'
                                   '$sequence idle Mesh.SMD\n')
            self.assertNotIn('file case mismatch:', result)
        finally:
            self.root = original
