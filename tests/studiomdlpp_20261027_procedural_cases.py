"""Authored VRD regressions for the 2026-10-26 StudioMDL++ update.

The expected quaternions use independent Python composition, while the native
tests inspect the runtime tables written to MDL. No reference binary is needed.
Run standalone: python tests/studiomdlpp_20261027_procedural_cases.py <compiler>
"""
import math
import struct
from procedural_cases import skeletal_smd, euler, multiply, dot
from dmx_dependency_cases import Document


TRIGGER = '<trigger> 45 11 17 23 29 31 37 5 7 11\n'
HELPER = '<helper> helper root root driver\n'
BASE = '<basepos> 1 2 3\n'


def degrees_quaternion(value):
    return euler(tuple(math.radians(x) for x in value))


def dmx_scale_fixture(bind=None, samples=None, *, extra_material=False, bind_state=False, no_animation=False):
    d = Document()
    d.element(1, 'DmElement', 'animation', f'"skeleton" {d.ref(2)}'
              + ('' if no_animation else f' "animationList" {d.ref(6)}'))
    d.element(2, 'DmeModel', 'model', d.elements('children', [3]) + d.elements('jointList', [3])
              + (d.elements('baseStates', [20]) if bind_state else ''))
    d.element(3, 'DmeJoint', 'root', f'"transform" {d.ref(4)} ' + d.elements('children', []))
    base = '"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"'
    scale = '' if bind is None else ' "scale" "vector3" "' + ' '.join(map(str, bind)) + '"'
    d.element(4, 'DmeTransform', 'root', base + ('' if bind_state else scale))
    if bind_state:
        d.element(20, 'DmeTransformList', 'bind', d.elements('transforms', [21]))
        d.element(21, 'DmeTransform', 'root_bind', base + scale)
    d.element(6, 'DmeAnimationList', 'animations', d.elements('animations', [7]))
    d.element(7, 'DmeChannelsClip', 'motion', f'"frameRate" "int" "4" "timeFrame" {d.ref(8)} '
              + d.elements('channels', [9] if samples is not None else []))
    d.element(8, 'DmeTimeFrame', 'time', '"start" "time" "0" "duration" "time" "1" "scale" "float" "1"')
    if samples is not None:
        d.element(9, 'DmeChannel', 'scaling', f'"toElement" {d.ref(4)} "toAttribute" "string" "scale" "log" {d.ref(10)}')
        d.element(10, 'DmeVector3Log', 'scaleLog', d.elements('layers', [11]))
        d.element(11, 'DmeVector3LogLayer', 'scaleLayer', d.array('times', 'int', [0, 10000])
                  + d.array('values', 'vector3', [' '.join(map(str, v)) for v in samples]))
    if extra_material:
        d.element(90, 'DmeMaterial', 'unrelated_material', '"scale" "vector3" "2 3 4"')
    return d.text()


class StudioMdlppProceduralCases:
    def spp_dmx_scale_compile(self, text, *, success=True):
        self.write('scale_mesh.smd', skeletal_smd(['root'], [-1], [(0, 0, 0)], [(0, 0, 0)]))
        self.write('scale_motion.dmx', text)
        return self.scene_qc('$modelname spp_scale\n$body body scale_mesh.smd\n'
                             '$sequence motion scale_motion.dmx\n', success=success)

    def test_spp_dmx_nonunit_bind_scale_rejects_and_preserves_outputs(self):
        self.spp_dmx_scale_compile(dmx_scale_fixture())
        before = {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_scale.*')}
        for bind_state in (False, True):
            for scale in ((2, 2, 2), (1, .5, 1), (-1, 1, 1), (0, 1, 1)):
                with self.subTest(bind_state=bind_state, scale=scale):
                    log = self.spp_dmx_scale_compile(dmx_scale_fixture(scale, bind_state=bind_state), success=False)
                    self.assertIn('unsupported non-unit bind scale', log)
                    self.assertIn('scale-capable engine', log)
                    self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_scale.*')})

    def test_spp_dmx_nonunit_animated_scale_rejects_and_preserves_outputs(self):
        self.spp_dmx_scale_compile(dmx_scale_fixture())
        before = {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_scale.*')}
        for bind in (None, (1, 1, 1)):
            for final in ((2, 2, 2), (1, 3, 4)):
                with self.subTest(bind=bind, final=final):
                    log = self.spp_dmx_scale_compile(dmx_scale_fixture(bind, [(1, 1, 1), final]), success=False)
                    self.assertIn('unsupported non-unit animated scale at frame 1', log)
                    self.assertIn('vertex-animation baking', log)
                    self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_scale.*')})

    def test_spp_dmx_bind_only_nonfinite_scale_rejects_without_animation_graph(self):
        self.spp_dmx_scale_compile(dmx_scale_fixture(no_animation=True))
        before = {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_scale.*')}
        for axis in range(3):
            for value in ('nan', 'inf', '-inf'):
                with self.subTest(axis=axis, value=value):
                    scale = [1, 1, 1]
                    scale[axis] = value
                    log = self.spp_dmx_scale_compile(dmx_scale_fixture(scale, no_animation=True), success=False)
                    self.assertIn('non-finite bind scale', log)
                    self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_scale.*')})

    def test_spp_dmx_unit_scale_and_unrelated_material_scale_are_accepted(self):
        baseline = None
        for bind, samples, material in ((None, None, False), ((1, 1, 1), None, True),
                                       ((1, 1, 1), [(1, 1, 1)] * 2, False), (None, [(1, 1, 1)] * 2, True)):
            with self.subTest(bind=bind, samples=samples, material=material):
                self.spp_dmx_scale_compile(dmx_scale_fixture(bind, samples, extra_material=material))
                output = self.mdl('spp_scale')
                if baseline is None:
                    baseline = output
                else:
                    self.assertEqual(output, baseline)

    def spp_procedural_fixture(self):
        self.write('proc_mesh.smd', skeletal_smd(
            ['root', 'driver', 'helper', 'helper2'], [-1, 0, 0, 0],
            [(0, 0, 0), (0, 0, 0), (1, 0, 0), (0, 1, 0)], [(0, 0, 0)] * 4))

    def spp_procedural_compile(self, text, *, before='', after='', success=True):
        self.spp_procedural_fixture()
        self.write('proc.vrd', text)
        return self.scene_qc('$modelname spp_proc\n$origin 0 0 0 -90\n'
                             '$body body proc_mesh.smd\n$sequence idle proc_mesh.smd\n'
                             + before + '$proceduralbones proc.vrd\n' + after, success=success)

    def spp_procedural_table(self, name='helper'):
        data, bones = self.csgo_bone_table('spp_proc')
        at = bones[name][1]
        kind, offset = struct.unpack_from('<2i', data, at + 164)
        return data, at + offset, kind

    def spp_procedural_triggers(self, name='helper'):
        data, at, kind = self.spp_procedural_table(name)
        self.assertEqual(kind, 2)
        _, count, offset = struct.unpack_from('<3i', data, at)
        return [struct.unpack_from('<12f', data, at + offset + i * 48) for i in range(count)]

    def spp_assert_quaternion(self, actual, expected):
        self.assertAlmostEqual(sum(x*x for x in actual), 1, delta=2e-6)
        self.assertAlmostEqual(abs(dot(actual, expected)), 1, delta=2e-6)

    def test_spp_vrd_baseang_composes_outside_axis_pose_and_orient(self):
        self.spp_procedural_compile(HELPER + BASE + '<baseang> 13 19 41\n'
                                    '<rotateaxis> 7 9 21\n<jointorient> 4 8 16\n' + TRIGGER,
                                    before='$scale 2\n', after='$scale 7\n')
        trigger = self.spp_procedural_triggers()[0]
        expected = degrees_quaternion((13, 19, 41))
        for angles in ((7, 9, 21), (29, 31, 37), (4, 8, 16)):
            expected = multiply(expected, degrees_quaternion(angles))
        self.spp_assert_quaternion(trigger[8:12], expected)
        self.spp_assert_quaternion(trigger[1:5], degrees_quaternion((11, 17, 23)))
        self.assertEqual(trigger[5:8], (12, 18, 28))

    def test_spp_vrd_baseang_is_forward_scoped_across_helpers_and_resets_per_file(self):
        self.spp_procedural_fixture()
        self.write('proc2.vrd', '<helper> helper2 root root driver\n' + TRIGGER)
        self.spp_procedural_compile(HELPER + TRIGGER + '<baseang> 0 0 90\n' + TRIGGER
                                    + '<baseang> 0 0 0\n' + TRIGGER,
                                    after='$proceduralbones proc2.vrd\n')
        plain = degrees_quaternion((29, 31, 37))
        turned = multiply(degrees_quaternion((0, 0, 90)), plain)
        for actual, expected in zip(self.spp_procedural_triggers(), (plain, turned, plain)):
            self.spp_assert_quaternion(actual[8:12], expected)
        self.spp_assert_quaternion(self.spp_procedural_triggers('helper2')[0][8:12], plain)
        self.spp_procedural_compile(HELPER + '<baseang> 13 19 41\n' + TRIGGER
                                    + '<helper> helper2 root root driver\n' + TRIGGER)
        for name in ('helper', 'helper2'):
            self.spp_assert_quaternion(self.spp_procedural_triggers(name)[0][8:12],
                                      multiply(degrees_quaternion((13, 19, 41)), plain))

    def test_spp_vrd_aim_basepos_scales_at_import_without_scaling_directions(self):
        text = ('<aimconstraint> helper root driver\n<aimvector> 1 0 0\n'
                '<upvector> 0 0 1\n<basepos> 1 2 3\n')
        for scale in (1, 2, .5):
            with self.subTest(scale=scale):
                self.spp_procedural_compile(text, before=f'$scale {scale}\n', after='$scale 7\n')
                data, at, kind = self.spp_procedural_table()
                self.assertEqual(kind, 3)
                values = struct.unpack_from('<9f', data, at + 8)
                for a, b in zip(values[:6], (1, 0, 0, 0, 0, 1)):
                    self.assertAlmostEqual(a, b, delta=2e-6)
                self.assertEqual(values[6:], tuple(scale*x for x in (1, 2, 3)))

    def test_spp_vrd_aim_scaled_position_overflow_preserves_output(self):
        aim = '<aimconstraint> helper root driver\n<aimvector> 1 0 0\n<upvector> 0 0 1\n'
        self.spp_procedural_compile(aim + '<basepos> 1 2 3\n')
        before = {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_proc.*')}
        for axis in range(3):
            with self.subTest(axis=axis):
                position = ['1', '1', '1']
                position[axis] = '1e30'
                log = self.spp_procedural_compile(aim + '<basepos> ' + ' '.join(position) + '\n',
                                                  before='$scale 1e30\n', after='$scale 1\n', success=False)
                self.assertIn('<basepos> overflows after $scale', log)
                self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_proc.*')})

    def test_spp_vrd_trigger_addition_and_scaling_overflow_preserve_output(self):
        self.spp_procedural_compile(HELPER + BASE + TRIGGER)
        before = {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_proc.*')}
        for axis in range(3):
            for mode in ('addition', 'scaling'):
                with self.subTest(axis=axis, mode=mode):
                    base = ['0', '0', '0']
                    position = ['0', '0', '0']
                    if mode == 'addition':
                        base[axis] = position[axis] = '3e38'
                        scale = '1'
                    else:
                        position[axis] = scale = '1e30'
                    text = (HELPER + '<basepos> ' + ' '.join(base) + '\n'
                            + '<trigger> 45 0 0 0 0 0 0 ' + ' '.join(position) + '\n')
                    log = self.spp_procedural_compile(text, before=f'$scale {scale}\n',
                                                      after='$scale 1\n', success=False)
                    self.assertIn('procedural trigger position is non-finite after basepos/$scale', log)
                    self.assertEqual(before, {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_proc.*')})

    def test_spp_vrd_pushd_and_cd_match_reference_with_explicit_ce_option(self):
        self.spp_procedural_fixture()
        self.write('proc.vrd', HELPER + '<basepos> 20 30 40\n' + TRIGGER)
        self.write('sub/proc.vrd', HELPER + BASE + TRIGGER)
        prefix = ('$modelname spp_proc\n$origin 0 0 0 -90\n'
                  '$body body proc_mesh.smd\n$sequence idle proc_mesh.smd\n')
        for directory in ('$pushd sub', '$cd sub'):
            for option, expected in (('', (25, 37, 51)), ('$PUSHDProcedural 0\n', (25, 37, 51)),
                                     ('$PUSHDProcedural 1\n', (6, 9, 14))):
                with self.subTest(directory=directory, option=option):
                    self.scene_qc(prefix + option + directory + '\n$proceduralbones proc.vrd\n')
                    self.assertEqual(self.spp_procedural_triggers()[0][5:8], expected)

    def test_spp_vrd_addsearchdir_and_relative_filename_resolve(self):
        self.spp_procedural_fixture()
        self.write('sub/proc.vrd', HELPER + BASE + TRIGGER)
        prefix = ('$modelname spp_proc\n$origin 0 0 0 -90\n'
                  '$body body proc_mesh.smd\n$sequence idle proc_mesh.smd\n')
        for commands in ('$addsearchdir sub\n$proceduralbones proc.vrd\n',
                         '$proceduralbones sub/proc.vrd\n'):
            with self.subTest(commands=commands):
                self.scene_qc(prefix + commands)
                self.assertEqual(self.spp_procedural_triggers()[0][5:8], (6, 9, 14))

    def test_spp_vrd_malformed_baseang_preserves_previous_model_family(self):
        self.spp_procedural_compile(HELPER + BASE + TRIGGER)
        old = {p.name: p.read_bytes() for p in (self.root/'models').glob('spp_proc.*')}
        for values in ('', '1 2', '1 nope 3', 'nan 0 0', 'inf 0 0', '1e100 0 0'):
            with self.subTest(values=values):
                output = self.spp_procedural_compile(HELPER + '<baseang> ' + values + '\n' + TRIGGER,
                                                     success=False)
                self.assertIn('<baseang> expects finite x y z degrees', output)
                self.assertEqual(old, {p.name:p.read_bytes() for p in (self.root/'models').glob('spp_proc.*')})

    def test_spp_vrd_trigger_cap_does_not_reapply_base_rotation(self):
        for base in (False, True):
            with self.subTest(baseang=base):
                self.spp_procedural_compile(HELPER + ('<baseang> 13 19 41\n' if base else '')
                                            + '<rotateaxis> 7 9 21\n<jointorient> 4 8 16\n' + TRIGGER * 40)
                triggers = self.spp_procedural_triggers()
                self.assertEqual(len(triggers), 32)
                expected = multiply(multiply(degrees_quaternion((7, 9, 21)),
                                             degrees_quaternion((29, 31, 37))), degrees_quaternion((4, 8, 16)))
                if base:
                    expected = multiply(degrees_quaternion((13, 19, 41)), expected)
                for trigger in triggers:
                    self.spp_assert_quaternion(trigger[8:12], expected)


if __name__ == '__main__':
    import unittest
    from compatibility import Compatibility
    class ProceduralUpdate(StudioMdlppProceduralCases, Compatibility):
        pass
    suite = unittest.TestSuite(ProceduralUpdate(name) for name in sorted(dir(StudioMdlppProceduralCases))
                              if name.startswith('test_'))
    raise SystemExit(not unittest.TextTestRunner(verbosity=2).run(suite).wasSuccessful())
