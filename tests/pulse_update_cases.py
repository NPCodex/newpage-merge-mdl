"""Black-box regressions for the PulseModel 578e86e merge."""
import math
import struct

from dmx_dependency_cases import Document


def primitive_document(primitives):
    d = Document()
    d.element(1, 'DmElement', 'physics', f'"model" {d.ref(2)} "skeleton" {d.ref(2)} '
              f'"physicsPrimitiveList" {d.ref(6)}')
    d.element(2, 'DmeModel', 'model', '"upAxis" "string" "Z" ' +
              d.elements('children', [3]) + d.elements('jointList', [3]) +
              d.elements('jointTransforms', [4]))
    d.element(3, 'DmeJoint', 'root', f'"transform" {d.ref(4)} ' + d.elements('children', []))
    d.element(4, 'DmeTransform', 'root', '"position" "vector3" "0 0 0" '
              '"orientation" "quaternion" "0 0 0 1"')
    d.element(6, 'DmePhysicsPrimitiveList', 'primitives', d.elements('primitives', range(10, 10 + len(primitives))))
    for i, (kind, fields) in enumerate(primitives):
        d.element(10 + i, 'DmePhysics' + kind, 'primitive' + str(i),
                  '"boneName" "string" "root" ' + fields)
    return d.text()


class PulseUpdateCases:
    def test_pulse_fast_and_legacy_bounds_enclose_weighted_animation(self):
        nodes = '0 "root" -1\n1 "tip" 0\n'
        pose = '0 0 0 0 0 0 0\n1 10 0 0 0 0 0\n'
        vertices = [(2, 0, 0), (3, 0, 0), (2, 1, 0)]
        triangles = ''.join(f'0 {x} {y} {z} 0 0 1 0 0 2 0 .6 1 .4\n' for x, y, z in vertices)
        self.write('weighted.smd', 'version 1\nnodes\n' + nodes + 'end\nskeleton\ntime 0\n' + pose +
                   'end\ntriangles\nmaterial\n' + triangles + 'end\n')
        self.write('motion.smd', 'version 1\nnodes\n' + nodes + 'end\nskeleton\ntime 0\n' + pose +
                   'time 1\n0 0 0 0 0 0 0\n1 10 0 0 0 0 1.5707963267948966\nend\n')
        boxes = []
        for args in [(), ('-legacysequencebounds',)]:
            self.scene_qc('$modelname weighted\n$origin 0 0 0 -90\n$body m weighted.smd\n'
                          '$sequence turn motion.smd\n', *args)
            data = self.mdl('weighted')
            seq = self.sequences('weighted')[0][2]
            lo, hi = struct.unpack_from('<3f', data, seq + 32), struct.unpack_from('<3f', data, seq + 44)
            boxes.append((lo, hi))
            # Independent rigid transformation about tip's bind pivot followed
            # by the two authored weights. Include both animation samples.
            positions = vertices + [(x * .6 + (10 - y) * .4, y * .6 + (x - 10) * .4, z)
                                    for x, y, z in vertices]
            for point in positions:
                for a, v, b in zip(lo, point, hi):
                    self.assertTrue(math.isfinite(a) and math.isfinite(b))
                    self.assertLessEqual(a, v + 1e-4)
                    self.assertGreaterEqual(b, v - 1e-4)
        for fast, legacy in zip(boxes[0][0], boxes[1][0]):
            self.assertLessEqual(fast, legacy + 1e-4)
        for fast, legacy in zip(boxes[0][1], boxes[1][1]):
            self.assertGreaterEqual(fast, legacy - 1e-4)

    def test_pulse_bboxonlyverts_matches_legacy_and_excludes_hitboxes(self):
        boxes = []
        for args in [(), ('-legacysequencebounds',)]:
            self.run_qc('$modelname vertices\n$origin 0 0 0 -90\n$bboxonlyverts\n'
                        '$hbox 0 root -100 -100 -100 100 100 100\n', *args)
            seq = self.sequences('vertices')[0][2]
            boxes.append(struct.unpack_from('<6f', self.mdl('vertices'), seq + 32))
        self.assertEqual(boxes[0], boxes[1])
        for actual, expected in zip(boxes[0], (0, 0, 0, 1, 1, 0)):
            self.assertAlmostEqual(actual, expected, places=5)

    def pulse_physics(self, primitives):
        self.write('physics.dmx', primitive_document(primitives))
        return self.scene_qc('$modelname primitives\n$origin 0 0 0 -90\n$body m mesh.smd\n'
                             '$datamodelphysics physics.dmx\n$physicsmodel { $mass 10 }\n')

    def test_pulse_dmx_physics_merge_groups_remain_separate_hulls(self):
        for merge, expected_hulls, volume in [('true', 1, 48), ('false', 2, 16)]:
            with self.subTest(merge=merge):
                self.pulse_physics([('Box', f'"merge" "bool" "{merge}" '
                                    f'"minBounds" "vector3" "{x} 0 0" '
                                    f'"maxBounds" "vector3" "{x + 2} 2 2"') for x in (0, 10)])
                _, hulls, volumes = self.extra_phy_hulls('primitives')
                self.assertEqual(len(hulls), expected_hulls)
                self.assertAlmostEqual(sum(abs(v) for v in volumes), volume, places=3)

    def test_pulse_dmx_sphere_capsule_and_rotated_box_extents(self):
        for kind, fields, widths in [
            ('Sphere', '"position" "vector3" "20 30 40" "radius" "float" "3" "segments" "int" "8"', (6, 6, 6)),
            ('Capsule', '"point0" "vector3" "0 0 0" "point1" "vector3" "0 0 10" '
             '"radius0" "float" "2" "radius1" "float" "3" "segments" "int" "8"', (6, 6, 15)),
            ('Box', '"minBounds" "vector3" "0 0 0" "maxBounds" "vector3" "2 4 6" '
             '"orientation" "vector3" "0 0 90"', (4, 2, 6)),
        ]:
            with self.subTest(kind=kind):
                self.pulse_physics([(kind, fields)])
                _, hulls, volumes = self.extra_phy_hulls('primitives')
                self.assertEqual(len(hulls), 1)
                self.assertGreater(abs(volumes[0]), 0)
                actual = [max(p[axis] for p in hulls[0]) - min(p[axis] for p in hulls[0])
                          for axis in range(3)]
                for a, b in zip(actual, widths):
                    self.assertAlmostEqual(a, b, places=3)

    def test_pulse_qc_primitives_match_dmx_in_bone_space_under_scale_and_origin(self):
        cases = [
            ('Sphere', '"position" "vector3" "2 3 4" "radius" "float" "3" "segments" "int" "8"',
             'sphere root 2 3 4 3 8'),
            ('Capsule', '"point0" "vector3" "1 2 3" "point1" "vector3" "4 6 10" '
             '"radius0" "float" "2" "radius1" "float" "3" "segments" "int" "8"',
             'capsule root 1 2 3 4 6 10 2 3 8'),
            ('Box', '"minBounds" "vector3" "0 0 0" "maxBounds" "vector3" "2 4 6" '
             '"orientation" "vector3" "10 20 30"', 'box root 0 0 0 2 4 6 10 20 30'),
        ]
        for kind, fields, qc in cases:
            for transform in ['', '$scale 2\n$origin 3 4 5 30\n']:
                with self.subTest(kind=kind, transform=transform):
                    self.write('physics.dmx', primitive_document([(kind, fields)]))
                    prefix = '$modelname primitives\n' + transform + '$body m mesh.smd\n'
                    # A joint makes PHY vertices bone-local. A single-body QC
                    # primitive instead bakes the model transform into PHY.
                    physics = '$physicsmodel {\n$mass 10\n$physicsjoint root { x fixed }\n'
                    self.scene_qc(prefix + '$datamodelphysics physics.dmx\n' + physics + '}\n')
                    _, expected, volumes = self.extra_phy_hulls('primitives')
                    self.scene_qc(prefix + physics + '$physicsshape primitive ' + qc + '\n}\n')
                    _, actual, current_volumes = self.extra_phy_hulls('primitives')
                    self.assertEqual(len(actual), 1)
                    self.extra_points_equal(actual[0], expected[0])
                    self.assertAlmostEqual(abs(current_volumes[0]), abs(volumes[0]), places=3)

    def test_pulse_qc_single_body_primitive_bakes_scale_and_origin(self):
        self.scene_qc('$modelname primitives\n$body m mesh.smd\n$scale 2\n$origin 3 4 5 30\n'
                      '$physicsmodel {\n$mass 10\n$physicsshape primitive box root 0 0 0 2 4 6\n}\n')
        _, hulls, volumes = self.extra_phy_hulls('primitives')
        # QC's yaw adds to the default SMD +90 degrees. Scale the authored
        # shape, subtract $origin, then rotate into model space.
        expected = []
        angle = math.radians(120)
        for x in (0, 2):
            for y in (0, 4):
                for z in (0, 6):
                    x1, y1, z1 = x * 2 - 3, y * 2 - 4, z * 2 - 5
                    expected.append((x1 * math.cos(angle) - y1 * math.sin(angle),
                                     x1 * math.sin(angle) + y1 * math.cos(angle), z1))
        self.assertEqual(len(hulls), 1)
        self.extra_points_equal(hulls[0], expected)
        self.assertAlmostEqual(abs(volumes[0]), 2 * 4 * 6 * 8, places=3)

    def test_pulse_dmx_attachment_uses_joint_ancestor_and_locator_chain(self):
        d = Document()
        d.element(1, 'DmElement', 'rig', f'"skeleton" {d.ref(2)}')
        d.element(2, 'DmeModel', 'model', d.elements('children', [3]))
        d.element(3, 'DmeJoint', 'root', f'"transform" {d.ref(4)} "shape" {d.ref(10)} ' + d.elements('children', [5]))
        d.element(4, 'DmeTransform', 'root', '"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
        d.element(5, 'DmeDag', 'locator_parent', f'"transform" {d.ref(6)} ' + d.elements('children', [7]))
        d.element(6, 'DmeTransform', 'parent', '"position" "vector3" "1 2 3" '
                  '"orientation" "quaternion" "0 0 .7071067811865476 .7071067811865476"')
        d.element(7, 'DmeDag', 'locator_child', f'"transform" {d.ref(8)} "shape" {d.ref(9)}')
        d.element(8, 'DmeTransform', 'child', '"position" "vector3" "4 0 0" "orientation" "quaternion" "0 0 0 1"')
        d.element(9, 'DmeAttachment', 'locator', '"isWorldAligned" "bool" "true"')
        d.element(10, 'DmeAttachment', 'direct')
        self.write('attachments.dmx', d.text())
        self.scene_qc('$modelname attachments\n$scale 2\n$body m mesh.smd\n'
                      '$datamodeljoints attachments.dmx attachments\n')
        data, bones = self.csgo_bone_table('attachments')
        count, start = struct.unpack_from('<2i', data, 240)
        self.assertEqual(count, 2)
        found = {}
        for i in range(count):
            at = start + i * 92
            name_at = at + struct.unpack_from('<i', data, at)[0]
            name = data[name_at:data.index(b'\0', name_at)].decode()
            flags, bone = struct.unpack_from('<2i', data, at + 4)
            self.assertEqual(bone, bones['root'][0])
            position = tuple(struct.unpack_from('<f', data, at + 24 + axis * 16)[0] for axis in range(3))
            found[name] = (flags, position)
        self.assertEqual(found['direct'], (0, (0, 0, 0)))
        self.assertEqual(found['locator'][0] & 0x10000, 0x10000)
        for actual, expected in zip(found['locator'][1], (2, 12, 6)):
            self.assertAlmostEqual(actual, expected, places=4)
