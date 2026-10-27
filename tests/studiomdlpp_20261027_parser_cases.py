"""Regression cases for the October 2026 StudioMDL++ parser update.

All inputs are authored here; reference executables are not test dependencies.
"""
import struct

from compiler_input_cases import clip_collision


class StudioMdlPp20261027ParserCases:
    def spp_sequence_grid(self, name):
        data = self.mdl(name)
        count, offset = struct.unpack_from('<2i', data, 188)
        self.assertEqual(count, 1)
        numblends = struct.unpack_from('<i', data, offset + 56)[0]
        groups = struct.unpack_from('<2i', data, offset + 68)
        index = offset + struct.unpack_from('<i', data, offset + 60)[0]
        return groups, struct.unpack_from('<' + 'h' * numblends, data, index)

    def test_spp_single_blend_parameter_infers_the_complete_row(self):
        for count in (4, 5, 6, 9):
            with self.subTest(count=count):
                inputs = ' '.join('mesh.smd' for _ in range(count))
                qc = '$modelname row\n$body m mesh.smd\n$sequence row {\n' + inputs + '\nblend move_x -1 1\n'
                self.scene_qc(qc + '}\n')
                inferred = self.spp_sequence_grid('row')
                self.assertEqual(inferred[0], (count, 1))
                self.scene_qc(qc + f'blendwidth {count}\n}}\n')
                self.assertEqual(self.spp_sequence_grid('row'), inferred)

    def test_spp_two_dimensional_and_explicit_blend_grids_remain_valid(self):
        for count, width, expected in ((4, None, (2, 2)), (9, None, (3, 3)), (6, 3, (3, 2))):
            with self.subTest(count=count, width=width):
                inputs = ' '.join('mesh.smd' for _ in range(count))
                qc = '$modelname grid\n$body m mesh.smd\n$sequence grid {\n' + inputs + '\nblend move_x -1 1\nblend move_y -1 1\n'
                if width is not None:
                    qc += f'blendwidth {width}\n'
                self.scene_qc(qc + '}\n')
                self.assertEqual(self.spp_sequence_grid('grid')[0], expected)
        # An authored width retains precedence even for a single parameter.
        self.scene_qc('$modelname grid\n$body m mesh.smd\n$sequence grid {\n' +
                      ' '.join('mesh.smd' for _ in range(6)) + '\nblend move_x -1 1\nblendwidth 3\n}\n')
        self.assertEqual(self.spp_sequence_grid('grid')[0], (3, 2))

    def test_spp_invalid_explicit_blendwidth_preserves_existing_output(self):
        self.scene_qc('$modelname grid\n$body m mesh.smd\n$sequence idle mesh.smd\n')
        before = self.mdl('grid')
        result = self.scene_qc('$modelname grid\n$body m mesh.smd\n$sequence grid {\n' +
                              ' '.join('mesh.smd' for _ in range(5)) + '\nblend move_x -1 1\nblendwidth 2\n}\n', success=False)
        self.assertIn('blends not a multiple of blendwidth', result)
        self.assertEqual(self.mdl('grid'), before)

    def test_spp_missing_animation_block_warns_and_uses_default_clip(self):
        self.write('motion.dmx', clip_collision('Run'))
        qc = '$modelname blocks\n$body m mesh.smd\n$origin 0 0 0 -90\n$animationcullmethod none\n$sequence idle motion.dmx'
        self.scene_qc(qc + '\n')
        default = self.animation_poses('blocks', 'idle')
        result = self.scene_qc(qc + ' blockname missing_clip\n')
        self.assertIn('WARNING: Requested unknown animation block name missing_clip', result)
        self.assertEqual(self.animation_poses('blocks', 'idle'), default)
        self.scene_qc(qc + ' blockname Run\n')
        self.assertNotEqual(self.animation_poses('blocks', 'idle'), default)

    def test_spp_unknown_animation_options_still_fail(self):
        for body in ('$animation clip mesh.smd { unknown_token 0 }\n$sequence idle clip\n',
                     '$sequence idle mesh.smd\n$append missing fps 12\n'):
            with self.subTest(body=body):
                self.scene_qc('$modelname strict\n$body m mesh.smd\n' + body, success=False)
                self.assertFalse((self.root / 'models/strict.mdl').exists())

    def test_spp_unknown_block_after_valid_selection_keeps_selected_clip(self):
        self.write('motion.dmx', clip_collision('Run'))
        prefix = '$modelname blocks\n$body m mesh.smd\n$animationcullmethod none\n'
        for mode in ('animation', 'sequence'):
            with self.subTest(mode=mode):
                command = ('$animation clip motion.dmx' if mode == 'animation' else '$sequence idle motion.dmx')
                suffix = '\n$sequence idle clip\n' if mode == 'animation' else '\n'
                self.scene_qc(prefix + command + ' blockname Run' + suffix)
                expected = self.animation_poses('blocks', 'clip' if mode == 'animation' else 'idle')
                result = self.scene_qc(prefix + command + ' blockname Run blockname missing_clip' + suffix)
                self.assertIn('Requested unknown animation block name missing_clip', result)
                self.assertEqual(self.animation_poses('blocks', 'clip' if mode == 'animation' else 'idle'), expected)

    def test_spp_unknown_block_in_append_preserves_selection_and_frame_trim(self):
        self.write('motion.dmx', clip_collision('Run'))
        qc = ('$modelname trim\n$body m mesh.smd\n$animationcullmethod none\n'
              '$animation clip motion.dmx blockname Run frame 1 1\n$sequence idle clip\n')
        self.scene_qc(qc)
        expected = self.animation_poses('trim', 'clip')
        self.assertEqual(len(expected), 1)
        result = self.scene_qc(qc + '$append clip blockname missing_clip\n')
        self.assertIn('Requested unknown animation block name missing_clip', result)
        self.assertEqual(self.animation_poses('trim', 'clip'), expected)

    def test_spp_more_than_256_weightlists_resolve_the_final_mask(self):
        lists = ''.join(f'$weightlist mask{i} {{ root 1 }}\n' for i in range(256))
        self.scene_qc('$modelname weighted\n$body m mesh.smd\n' + lists +
                      '$weightlist last { root .25 }\n$sequence idle mesh.smd weightlist last\n')
        data = self.mdl('weighted')
        seq = struct.unpack_from('<i', data, 192)[0]
        weights = seq + struct.unpack_from('<i', data, seq + 156)[0]
        self.assertAlmostEqual(struct.unpack_from('<f', data, weights)[0], .25)

    def test_spp_macro_invocations_accept_eof_without_a_newline(self):
        for definition, invocation in (
            ('$definemacro emit model \\\\\n$modelname $model$\n', '$emit eof'),
            ('$definemacro emit \\\\\n$modelname eof\n', '$emit'),
            ('$definemacro emit model\n$modelname $model$\n$endmacro\n', '$emit eof'),
            ('$definemacro emit model=eof\n$modelname $model$\n$endmacro\n', '$emit'),
        ):
            with self.subTest(definition=definition):
                self.scene_qc('$body m mesh.smd\n$sequence idle mesh.smd\n' + definition + invocation)
                self.mdl('eof')

    def test_spp_macro_error_at_include_eof_retains_source_and_entire_chain(self):
        self.write('outer/one.qci', '$include two.qci\n')
        self.write('outer/two.qci', '$definemacro emit value\n$scale $value$\n$endmacro\n$emit nope')
        result = self.scene_qc('$include outer/one.qci\n', success=False).replace('\\', '/')
        self.assertIn((self.root / 'outer/two.qci').as_posix() + '(2)', result)
        self.assertIn('    $scale $value$\n           ^', result)
        self.assertIn('expanded $emit at ' + (self.root / 'outer/two.qci').as_posix() + '(4)', result)
        self.assertIn('included from ' + (self.root / 'outer/one.qci').as_posix() + '(1)', result)
        self.assertIn('included from ' + (self.root / 'scene.qc').as_posix() + '(1)', result)

    def test_spp_multiline_numeric_error_points_to_the_actual_value_line(self):
        result = self.scene_qc('$scale\n  nope\n', success=False)
        self.assertIn('scene.qc(2)', result)
        self.assertIn('      nope\n      ^', result)

    def test_spp_unexpanded_variable_error_keeps_authored_context(self):
        self.write('variables.qci', '$modelname $missing$\n')
        result = self.scene_qc('$include variables.qci\n', success=False).replace('\\', '/')
        self.assertIn('variables.qci(1)', result)
        self.assertIn('unknown variable "$missing$"', result)
        self.assertIn('    $modelname $missing$\n               ^', result)
        self.assertIn('included from ' + (self.root / 'scene.qc').as_posix() + '(1)', result)

    def test_spp_tokenization_error_in_include_keeps_source_and_parents(self):
        self.write('outer.qci', '$include broken.qci\n')
        self.write('broken.qci', '$modelname "unterminated')
        result = self.scene_qc('$include outer.qci\n', success=False).replace('\\', '/')
        self.assertIn('broken.qci(1): unterminated string', result)
        self.assertIn('    $modelname "unterminated\n               ^', result)
        self.assertIn('included from ' + (self.root / 'outer.qci').as_posix() + '(1)', result)
        self.assertIn('included from ' + (self.root / 'scene.qc').as_posix() + '(1)', result)

    def test_spp_mvz_retarget_reports_target_limit_and_preserves_outputs(self):
        qc = '$modelname retarget\n$body m mesh.smd\n$sequence idle mesh.smd\n'
        self.scene_qc(qc)
        before = {path: path.read_bytes() for path in (self.root / 'models').glob('retarget.*')}
        result = self.scene_qc(qc + '$retarget { source.smd target.smd }\n', success=False)
        self.assertIn('$retarget requires the Mann Versus Zombies engine branch', result)
        self.assertIn('target/output format is not supported', result)
        self.assertNotIn('unknown command "$retarget"', result)
        self.assertEqual({path: path.read_bytes() for path in before}, before)
