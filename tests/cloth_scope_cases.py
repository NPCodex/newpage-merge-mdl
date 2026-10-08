"""CSGO cloth compatibility: axes, boundary fits and quad preprocessing."""
import re
import struct
from cloth_cases import cloth_dmx, render_smd, fe_resource
from cloth_advanced_cases import fe_names


def y_up_proxy(text):
    text = text.replace('"upAxis" "string" "Z"', '"upAxis" "string" "Y"')
    def convert(match):
        values = []
        for value in re.findall(r'"([^"]+)"', match.group(1)):
            x, y, z = map(float, value.split())
            values.append(f'"{x} {z} {-y}"')
        return '"positions" "vector3_array" [ ' + ', '.join(values) + ' ]'
    return re.sub(r'"positions"\s+"vector3_array"\s*\[([^\]]+)\]', convert, text)


def weak_joint_proxy():
    text = cloth_dmx()
    uid = lambda n: f'cc100000-0000-0000-0000-{n:012x}'
    ref = lambda n: f'"element" "{uid(n)}"'
    text = text.replace(f'"jointList" "element_array" [ {ref(4)}, {ref(8)} ]',
                        f'"jointList" "element_array" [ {ref(4)}, {ref(8)}, {ref(20)} ]')
    text = text.replace(f'"jointTransforms" "element_array" [ {ref(5)}, {ref(9)} ]',
                        f'"jointTransforms" "element_array" [ {ref(5)}, {ref(9)}, {ref(21)} ]')
    text = text.replace(f'"children" "element_array" [ {ref(8)} ]',
                        f'"children" "element_array" [ {ref(8)}, {ref(20)} ]')
    text = text.replace('"jointCount" "int" "1"', '"jointCount" "int" "2"')
    text = re.sub(r'"jointWeights" "float_array" \[[^\]]+\]',
                  '"jointWeights" "float_array" [ "1", "0", "1", "0", ".96", ".04", ".96", ".04", ".96", ".04", ".96", ".04" ]', text)
    text = re.sub(r'"jointIndices" "int_array" \[[^\]]+\]',
                  '"jointIndices" "int_array" [ "0", "0", "0", "0", "1", "2", "1", "2", "1", "2", "1", "2" ]', text)
    text += f'"DmeJoint" {{ "id" "elementid" "{uid(20)}" "name" "string" "minor" "transform" {ref(21)} "children" "element_array" [] }}\n'
    text += f'"DmeTransform" {{ "id" "elementid" "{uid(21)}" "name" "string" "minor" "position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1" }}\n'
    mesh = render_smd().replace('1 "flap" 0', '1 "flap" 0\n2 "minor" 0')
    mesh = mesh.replace('1 0 0 0 0 0 0\nend', '1 0 0 0 0 0 0\n2 0 0 0 0 0 0\nend')
    return text, mesh


class ClothScopeCases:
    def test_cloth_scope_y_main_accepts_y_or_z_proxy_in_render_bind_space(self):
        self.write('gameinfo.txt', 'GameInfo { FileSystem { SteamAppId 730 } }')
        self.write('render_y.dmx', y_up_proxy(cloth_dmx()))
        poses = []
        for proxy in (cloth_dmx(), y_up_proxy(cloth_dmx())):
            self.write('axis_proxy.dmx', proxy)
            self.scene_qc('$modelname clothy\n$body m render_y.dmx\n$cloth axis_proxy.dmx\n')
            data = self.mdl('clothy'); _, array = fe_resource(data); names = fe_names(data, array)
            at, _ = array(120, 32, 16)
            points = sorted(tuple(round(x, 4) for x in struct.unpack_from('<3f', data, at + node * 32))
                            for name, node in names.items() if name.startswith('$cloth_p'))
            poses.append(points)
            vvd = (self.root / 'models/clothy.vvd').read_bytes()
            count = struct.unpack_from('<I', vvd, 16)[0]; start = struct.unpack_from('<I', vvd, 56)[0]
            rendered = {tuple(round(x, 4) for x in struct.unpack_from('<3f', vvd, start + i * 48 + 16)) for i in range(count)}
            self.assertEqual(set(points), rendered)
        self.assertEqual(poses[0], poses[1])

    def test_cloth_scope_proxy_and_plane_use_own_axis(self):
        self.cloth_model(plane=True)
        baseline = self.mdl('fecloth'); _, original = fe_resource(baseline)
        self.cloth_model(plane=True, proxy=y_up_proxy(cloth_dmx()), collision_proxy=y_up_proxy(cloth_dmx(plane=True)))
        changed = self.mdl('fecloth'); _, converted = fe_resource(changed)
        for field, size, alignment in ((120, 32, 16), (88, 76, 4), (184, 24, 4)):
            a, na = original(field, size, alignment); b, nb = converted(field, size, alignment)
            self.assertEqual(na, nb)
            for i in range(na):
                if field == 120:
                    for x, y in zip(struct.unpack_from('<8f', baseline, a + i * size), struct.unpack_from('<8f', changed, b + i * size)):
                        self.assertAlmostEqual(x, y, places=5)
                else:
                    self.assertEqual(baseline[a:a + na * size], changed[b:b + nb * size])

    def test_cloth_scope_prerotate_changes_only_final_init_pose(self):
        self.cloth_model(); before = self.mdl('fecloth'); _, before_array = fe_resource(before)
        self.cloth_model(settings='prerotate 0 90 0'); after = self.mdl('fecloth'); _, after_array = fe_resource(after)
        a, count = before_array(120, 32, 16); b, count2 = after_array(120, 32, 16); self.assertEqual(count, count2)
        for i in range(count):
            x, y, z = struct.unpack_from('<3f', before, a + 32 * i)
            actual = struct.unpack_from('<3f', after, b + 32 * i)
            for left, right in zip(actual, (-y, x, z)): self.assertAlmostEqual(left, right, places=4)
        for field, size, alignment in ((88, 76, 4), (96, 304, 16), (128, 20, 4), (152, 16, 4), (320, 64, 16)):
            p, n = before_array(field, size, alignment); q, m = after_array(field, size, alignment)
            self.assertEqual(n, m); self.assertEqual(before[p:p + n * size], after[q:q + m * size])

    def test_cloth_scope_flex_borders_emits_static_and_dynamic_fit_weights(self):
        proxy = cloth_dmx().replace('"jointIndices" "int_array" [ "0", "0", "1", "1", "1", "1" ]',
                                    '"jointIndices" "int_array" [ "1", "0", "1", "1", "1", "1" ]')
        self.cloth_model(proxy=proxy, settings='flex_borders true')
        data = self.mdl('fecloth'); start, array = fe_resource(data); names = fe_names(data, array)
        at, count = array(320, 64, 16); self.assertGreater(count, 0)
        matches = [struct.unpack_from('<4H', data, at + i * 64 + 44) for i in range(count)]
        end, _, _, begin = next(row for row in matches if row[2] == names['flap'])
        self.assertGreater(begin, 0); self.assertGreater(end, begin)
        weights, count = array(336, 8)
        ids = [struct.unpack_from('<H', data, weights + i * 8 + 4)[0] for i in range(end)]
        static = struct.unpack_from('<H', data, start + 34)[0]
        self.assertTrue(all(n < static for n in ids[:begin]))
        self.assertTrue(all(n >= static for n in ids[begin:]))
        self.assertIn(names['$cloth_p0'], ids[:begin])
        self.assertGreater(array(72, 32)[1], 0)

    def test_cloth_scope_two_static_fit_uses_runtime_midpoint(self):
        proxy = cloth_dmx().replace('"jointCount" "int" "1"', '"jointCount" "int" "2"')
        proxy = re.sub(r'"jointWeights" "float_array" \[[^\]]+\]',
                       '"jointWeights" "float_array" [ ".8", ".2", ".4", ".6", "0", "1", "0", "1", "0", "1", "0", "1" ]', proxy)
        proxy = re.sub(r'"jointIndices" "int_array" \[[^\]]+\]',
                       '"jointIndices" "int_array" [ "0", "1", "0", "1", "0", "1", "0", "1", "0", "1", "0", "1" ]', proxy)
        self.cloth_model(proxy=proxy, settings='flex_borders true')
        data = self.mdl('fecloth'); start, array = fe_resource(data)
        self.assertEqual(struct.unpack_from('<2H', data, start + 54), (1, 1))
        at, count = array(320, 64, 16); self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('<H', data, at + 50)[0], 2)
        center = struct.unpack_from('<3f', data, at + 32)
        for actual, expected in zip(center, (0, 0, 24)): self.assertAlmostEqual(actual, expected, places=4)
        at, _ = array(336, 8)
        self.assertAlmostEqual(struct.unpack_from('<f', data, at)[0], .2)
        self.assertAlmostEqual(struct.unpack_from('<f', data, at + 8)[0], .6)

    def test_cloth_scope_fit_threshold_and_small_cloud_policy(self):
        proxy, mesh = weak_joint_proxy()
        self.cloth_model(proxy=proxy, mesh=mesh, settings='fit_influence_threshold .05')
        data = self.mdl('fecloth'); _, array = fe_resource(data)
        self.assertNotIn('minor', fe_names(data, array))
        self.cloth_model(proxy=proxy, mesh=mesh, settings='fit_influence_threshold .01')
        data = self.mdl('fecloth'); _, array = fe_resource(data)
        self.assertIn('minor', fe_names(data, array)); self.assertEqual(array(320, 64, 16)[1], 2)
        self.cloth_model(settings='fit_min_influences 8')
        data = self.mdl('fecloth'); _, array = fe_resource(data)
        self.assertEqual(array(320, 64, 16)[1], 0)
        self.assertGreater(array(72, 32)[1], 0); self.assertGreater(array(344, 16)[1], 0)

    def test_cloth_scope_bent_quad_uses_short_diagonal_and_crossing_is_repaired(self):
        proxy = cloth_dmx().replace('"8 0 8"', '"8 6 8"')
        self.cloth_model(proxy=proxy, settings='quad_bend_tolerance .05')
        data = self.mdl('fecloth'); _, array = fe_resource(data); names = fe_names(data, array)
        self.assertEqual(array(88, 76)[1], 1)
        at, count = array(104, 128, 16); self.assertEqual(count, 2)
        triangles = [{struct.unpack_from('<I', data, at + i * 128 + j * 16)[0] for j in range(3)} for i in range(2)]
        self.assertEqual(triangles[0] & triangles[1], {names['$cloth_p3'], names['$cloth_p4']})
        self.cloth_model(proxy=proxy, settings='quad_bend_tolerance 1')
        data = self.mdl('fecloth'); _, array = fe_resource(data)
        self.assertEqual(array(88, 76)[1], 2); self.assertEqual(array(104, 128, 16)[1], 0)
        crossed = cloth_dmx().replace('"0", "1", "3", "2", "-1"', '"0", "1", "2", "3", "-1"')
        self.cloth_model(proxy=crossed)
        data = self.mdl('fecloth'); _, array = fe_resource(data); names = fe_names(data, array)
        at, count = array(88, 76)
        first = struct.unpack_from('<4H', data, at)
        self.assertEqual(first, tuple(names[f'$cloth_p{i}'] for i in (0, 1, 3, 2)))
