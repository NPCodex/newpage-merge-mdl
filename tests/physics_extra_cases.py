"""Geometry regressions for the historical CSGO $addconvexsrc source contract."""
import math
import struct


class PhysicsExtraCases:
    def test_collision_tolerance_chain_preserves_island(self):
        # Three closed boxes have a corresponding vertex at 0, .75 and 1.5.
        # With epsilon 1, the last cube first matches the middle cube, whose
        # vertices already weld to the first. The distant cube keeps the old
        # all-geometry fallback from hiding a lost connected component.
        self.extra_boxes('chain.smd', [(0, 0, 0, 10, 10, 10),
                                      (.75, 0, 0, 10.75, 10, 10),
                                      (1.5, 0, 0, 21.5, 20, 20),
                                      (50, 0, 0, 60, 10, 10)])
        self.scene_qc('$modelname chain\n$origin 0 0 0 -90\n$body m chain.smd\n'
                      '$collisionmodel chain.smd { $mass 10 $concave $weldposition 1 }\n')
        _, hulls, volumes = self.extra_phy_hulls('chain')
        self.assertEqual(len(hulls), 2)
        bounds = sorted((round(min(p[0] for p in h), 3),
                         round(max(p[0] for p in h), 3)) for h in hulls)
        self.assertEqual(bounds, [(0, 21.5), (50, 60)])
        # Independently author the intended first-representative geometry:
        # remove the fully redundant middle box and move the third origin to 0.
        self.extra_boxes('expected.smd', [(0, 0, 0, 10, 10, 10),
                                         (1.5, 0, 0, 21.5, 20, 20),
                                         (50, 0, 0, 60, 10, 10)])
        self.write('expected.smd', (self.root / 'expected.smd').read_text().replace(
            '0 1.5 0 0 0 0 1 0 0', '0 0 0 0 0 0 1 0 0'))
        self.scene_qc('$modelname expected\n$origin 0 0 0 -90\n$body m expected.smd\n'
                      '$collisionmodel expected.smd { $mass 10 $concave }\n')
        _, reference, reference_volumes = self.extra_phy_hulls('expected')
        self.assertEqual(len(reference), len(hulls))
        self.extra_points_equal([p for h in hulls for p in h], [p for h in reference for p in h])
        self.assertAlmostEqual(sum(abs(v) for v in volumes),
                               sum(abs(v) for v in reference_volumes), places=3)

    def test_collision_normal_chain_preserves_extended_hull(self):
        self.extra_boxes('normal.smd', [(0, 0, 0, 10, 10, 10),
                                       (0, 0, 0, 10, 10, 10),
                                       (0, 0, 0, 20, 20, 20),
                                       (50, 0, 0, 60, 10, 10)],
                         normals=[(math.sin(math.radians(a)), 0, math.cos(math.radians(a)))
                                  for a in (0, 20, 40, 0)])
        self.scene_qc('$modelname normal\n$origin 0 0 0 -90\n$body m normal.smd\n'
                      '$collisionmodel normal.smd { $mass 10 $concave $weldnormal .9 }\n')
        _, hulls, volumes = self.extra_phy_hulls('normal')
        self.assertEqual(len(hulls), 2)
        self.assertAlmostEqual(sum(abs(v) for v in volumes), 9000, places=2)
        self.assertEqual(sorted(round(max(p[0] for p in h), 3) for h in hulls), [20, 60])

    def test_collision_weld_chooses_first_match_across_grid_cells(self):
        self.extra_boxes('first.smd', [(.6, 0, 0, 10.6, 10, 10),
                                      (-.6, 0, 0, 9.4, 10, 10),
                                      (.1, 0, 0, 20.1, 20, 20)])
        self.scene_qc('$modelname first\n$origin 0 0 0 -90\n$body m first.smd\n'
                      '$collisionmodel first.smd { $mass 10 $concave $weldposition .75 }\n')
        _, hulls, _ = self.extra_phy_hulls('first')
        self.assertEqual(len(hulls), 2)
        bounds = sorted((round(min(p[0] for p in h), 3),
                         round(max(p[0] for p in h), 3)) for h in hulls)
        # The later large box is closer to the first box (.5 versus .7), but
        # reverse those distances below: FIRST source occurrence still wins.
        self.assertEqual(bounds, [(-.6, 9.4), (.1, 20.1)])
        text = (self.root / 'first.smd').read_text().replace('0 0.1 ', '0 -0.1 ')
        self.write('first.smd', text)
        self.scene_qc('$modelname first\n$origin 0 0 0 -90\n$body m first.smd\n'
                      '$collisionmodel first.smd { $mass 10 $concave $weldposition .75 }\n')
        _, hulls, _ = self.extra_phy_hulls('first')
        bounds = sorted((round(min(p[0] for p in h), 3),
                         round(max(p[0] for p in h), 3)) for h in hulls)
        self.assertEqual(bounds, [(-.6, 9.4), (-.1, 20.1)])

    def test_collision_chain_ragdoll_keeps_per_bone_islands(self):
        self.extra_boxes('ragchain.smd', [(0, 0, 0, 10, 10, 10),
                                         (.75, 0, 0, 10.75, 10, 10),
                                         (1.5, 0, 0, 21.5, 20, 20),
                                         (50, 0, 0, 60, 10, 10)])
        text = (self.root / 'ragchain.smd').read_text().replace(
            '0 "root" -1\n', '0 "root" -1\n1 "limb" 0\n').replace(
            'time 0\n0 0 0 0 0 0 0\n', 'time 0\n0 0 0 0 0 0 0\n1 0 0 0 0 0 0\n')
        lines = text.splitlines()
        for i, line in enumerate(lines):
            fields = line.split()
            if len(fields) == 9 and float(fields[1]) >= 50:
                fields[0] = '1'
                lines[i] = ' '.join(fields)
        self.write('ragchain.smd', '\n'.join(lines) + '\n')
        self.scene_qc('$modelname ragchain\n$origin 0 0 0 -90\n$bonecullmethod none\n'
                      '$body m ragchain.smd\n$collisionjoints ragchain.smd '
                      '{ $mass 10 $rootbone root $concaveperjoint $weldposition 1 }\n')
        _, root_hulls, _ = self.extra_phy_hulls('ragchain', expected_solids=2)
        _, limb_hulls, _ = self.extra_phy_hulls('ragchain', solid=1, expected_solids=2)
        self.assertEqual(len(root_hulls), 1)
        self.assertEqual(len(limb_hulls), 1)
        self.assertAlmostEqual(max(p[0] for p in root_hulls[0]), 21.5, places=3)
        self.assertAlmostEqual(min(p[0] for p in limb_hulls[0]), 50, places=3)

    def test_collision_weld_zero_and_exact_tolerance_boundaries(self):
        self.extra_boxes('boundary.smd', [(0, 0, 0, 10, 10, 10),
                                         (1, 0, 0, 11, 10, 10)])
        for epsilon, normal, expected in [(0, .999, 2), (.999, .999, 2),
                                          (1, .999, 1), (1, 1, 2), (1, 1.01, 2)]:
            with self.subTest(epsilon=epsilon, normal=normal):
                self.scene_qc('$modelname boundary\n$origin 0 0 0 -90\n$body m boundary.smd\n'
                              '$collisionmodel boundary.smd { $mass 10 $concave '
                              f'$weldposition {epsilon} $weldnormal {normal} }}\n')
                _, hulls, _ = self.extra_phy_hulls('boundary')
                self.assertEqual(len(hulls), expected)

    def extra_boxes(self, name, boxes, normals=None):
        text = ('version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n'
                '0 0 0 0 0 0 0\nend\ntriangles\n')
        corners = []
        # A shared normal deliberately makes touching authored parts weld.
        triangles = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
                     (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
                     (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
        for box_index, (x0, y0, z0, x1, y1, z1) in enumerate(boxes):
            nx, ny, nz = (0, 0, 1) if normals is None else normals[box_index]
            vertices = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            corners.extend(vertices)
            for triangle in triangles:
                text += 'material\n'
                for index in triangle:
                    x, y, z = vertices[index]
                    text += f'0 {x} {y} {z} {nx} {ny} {nz} 0 0\n'
        self.write(name, text + 'end\n')
        return corners

    def extra_phy_hulls(self, name, solid=0, expected_solids=1):
        data = (self.root / f'models/{name}.phy').read_bytes()
        self.assertEqual(struct.unpack_from('<i', data, 8)[0], expected_solids)
        cursor = struct.unpack_from('<i', data, 0)[0]
        for _ in range(solid):
            cursor += 4 + struct.unpack_from('<i', data, cursor)[0]
        surface = cursor + 4 + 28
        ledge = surface + 48
        tree = surface + struct.unpack_from('<i', data, surface + 32)[0]
        hulls, volumes = [], []
        while ledge < tree:
            offset, _, bits, triangles = struct.unpack_from('<iiIh', data, ledge)
            count = (bits >> 8) - triangles - 1
            points = []
            for i in range(count):
                x, y, z = struct.unpack_from('<3f', data, ledge + offset + i * 16)
                points.append((x / .0254, z / .0254, -y / .0254))
            volume = 0.0
            for t in range(triangles):
                ids = [struct.unpack_from('<I', data, ledge + 16 + t * 16 + 4 + e * 4)[0] & 0xffff
                       for e in range(3)]
                a, b, c = (points[i] for i in ids)
                volume += (a[0] * (b[1] * c[2] - b[2] * c[1]) +
                           a[1] * (b[2] * c[0] - b[0] * c[2]) +
                           a[2] * (b[0] * c[1] - b[1] * c[0])) / 6
            hulls.append(points)
            volumes.append(volume)
            ledge += (bits >> 8) * 16
        self.assertEqual(ledge, tree)
        return data, hulls, volumes

    def extra_points_equal(self, actual, expected):
        self.assertEqual(len(actual), len(expected))
        for point in expected:
            self.assertTrue(any(sum((a - b) ** 2 for a, b in zip(point, candidate)) < 1e-7
                                for candidate in actual), (point, actual))

    @staticmethod
    def extra_offset_point(point, position, angles, scale):
        # Independent composition: source -> authored axes, roll/pitch/yaw,
        # authored translation, then back to SMD physics axes.
        x, y, z = point[1] * scale, -point[0] * scale, point[2] * scale
        pitch, yaw, roll = (math.radians(a) for a in angles)
        y, z = y * math.cos(roll) - z * math.sin(roll), y * math.sin(roll) + z * math.cos(roll)
        x, z = x * math.cos(pitch) + z * math.sin(pitch), -x * math.sin(pitch) + z * math.cos(pitch)
        x, y = x * math.cos(yaw) - y * math.sin(yaw), x * math.sin(yaw) + y * math.cos(yaw)
        x, y, z = x + position[0], y + position[1], z + position[2]
        return -y, x, z

    def test_addconvexsrc_offset_geometry_scale_axes_and_cache_isolation(self):
        points = self.extra_boxes('box.smd', [(0, 0, 0, 2, 4, 6)])
        prefix = '$modelname extra\n$origin 0 0 0 -90\n$scale 3\n$body m box.smd\n'
        self.scene_qc(prefix + '$collisionmodel box.smd { $mass 20 }\n')
        vvd = (self.root / 'models/extra.vvd').read_bytes()
        start = struct.unpack_from('<i', vvd, 56)[0]
        render = vvd[start:]
        self.scene_qc(prefix + '$collisionmodel box.smd {\n$mass 20\n$concave\n'
                      '$addconvexsrc box.smd "offset pos[ 30 20 10 ] angle[ 20 35 15 ] scale[ 2 ]"\n'
                      '$addconvexsrc box.smd "offset pos[ -30 0 0 ] angle[ 0 0 0 ] scale[ 1 ]"\n}\n')
        data, hulls, volumes = self.extra_phy_hulls('extra')
        self.assertEqual(len(hulls), 3)
        expected = [tuple(v * 3 for v in p) for p in points]
        expected += [self.extra_offset_point(p, (30, 20, 10), (20, 35, 15), 2) for p in points]
        expected += [self.extra_offset_point(p, (-30, 0, 0), (0, 0, 0), 1) for p in points]
        self.extra_points_equal([p for hull in hulls for p in hull], expected)
        self.assertAlmostEqual(sum(abs(v) for v in volumes), 48 * (27 + 8 + 1), delta=.02)
        current = (self.root / 'models/extra.vvd').read_bytes()
        self.assertEqual(current[struct.unpack_from('<i', current, 56)[0]:], render)

    def test_addconvexsrc_concave_marker_and_global_gate(self):
        self.extra_boxes('root.smd', [(0, 0, 0, 2, 2, 2)])
        self.extra_boxes('islands.smd', [(10, 0, 0, 12, 2, 2), (20, 0, 0, 22, 2, 2)])
        prefix = '$modelname parts\n$origin 0 0 0 -90\n$body m root.smd\n'
        for global_flag, marker, count, volume in [('', '', 1, 88), ('', 'concave', 1, 88),
                                                   ('$concave', '', 2, 56), ('$concave', 'concave', 3, 24)]:
            self.scene_qc(prefix + f'$collisionmodel root.smd {{\n$mass 10\n{global_flag}\n'
                          f'$addconvexsrc islands.smd {marker}\n}}\n')
            _, hulls, volumes = self.extra_phy_hulls('parts')
            self.assertEqual(len(hulls), count)
            self.assertAlmostEqual(sum(abs(v) for v in volumes), volume, places=3)

    def test_addconvexsrc_concave_welds_after_offset_between_files(self):
        self.extra_boxes('root.smd', [(0, 0, 0, 2, 2, 2)])
        self.extra_boxes('extra.smd', [(0, 0, 0, 2, 2, 2), (10, 0, 0, 12, 2, 2)])
        # Authored Y=-2 becomes source X=+2; first extra box touches root.
        prefix = '$modelname welded\n$origin 0 0 0 -90\n$body m root.smd\n'
        for marker, count, volume in [('', 2, 56), ('concave', 2, 24)]:
            self.scene_qc(prefix + '$collisionmodel root.smd {\n$mass 10\n$concave\n$weldposition .001\n'
                          '$addconvexsrc extra.smd "offset pos[ 0 -2 0 ] angle[ 0 0 0 ] scale[ 1 ]" '
                          + marker + '\n}\n')
            _, hulls, volumes = self.extra_phy_hulls('welded')
            self.assertEqual(len(hulls), count)
            self.assertAlmostEqual(sum(abs(v) for v in volumes), volume, places=3)
            if marker:
                self.assertAlmostEqual(max(max(p[0] for p in hull) - min(p[0] for p in hull)
                                           for hull in hulls), 4, places=3)

    def test_addconvexsrc_negative_scale_keeps_closed_hull_winding(self):
        points = self.extra_boxes('box.smd', [(0, 0, 0, 2, 4, 6)])
        self.scene_qc('$modelname mirrored\n$origin 0 0 0 -90\n$body m box.smd\n'
                      '$collisionmodel box.smd {\n$mass 20\n$concave\n'
                      '$addconvexsrc box.smd "offset pos[ 30 0 0 ] angle[ 0 0 0 ] scale[ -1 ]"\n}\n')
        _, hulls, volumes = self.extra_phy_hulls('mirrored')
        self.assertEqual(len(hulls), 2)
        self.extra_points_equal([p for hull in hulls for p in hull], points +
            [self.extra_offset_point(p, (30, 0, 0), (0, 0, 0), -1) for p in points])
        self.assertTrue(volumes[0] * volumes[1] > 0)
        for volume in volumes:
            self.assertAlmostEqual(abs(volume), 48, places=3)

    def test_addconvexsrc_offset_precedes_bind_remapping(self):
        self.extra_boxes('box.smd', [(0, 0, 0, 2, 4, 6)])
        original = (self.root / 'box.smd').read_text().replace(
            '0 0 0 0 0 0 0\n', '0 3 4 5 0.1 0.2 0.3\n')
        self.write('box.smd', original)
        manual = []
        in_triangles = False
        for line in original.splitlines():
            if line == 'triangles':
                in_triangles = True
            fields = line.split()
            if in_triangles and len(fields) == 9:
                point = self.extra_offset_point(tuple(map(float, fields[1:4])),
                                                (30, 20, 10), (20, 35, 15), 2)
                fields[1:4] = [str(value) for value in point]
                line = ' '.join(fields)
            manual.append(line)
        self.write('manual.smd', '\n'.join(manual) + '\n')
        # A nonidentity bind pose and model transform exercise remapping after
        # the source-space edit. Compare against independently authored points.
        prefix = '$modelname remapped\n$origin 4 5 6 30\n$body m box.smd\n'
        body = '$collisionmodel box.smd {\n$mass 20\n$concave\n$addconvexsrc '
        self.scene_qc(prefix + body + 'manual.smd\n}\n')
        _, expected, expected_volumes = self.extra_phy_hulls('remapped')
        self.scene_qc(prefix + body + 'box.smd "offset pos[ 30 20 10 ] angle[ 20 35 15 ] scale[ 2 ]"\n}\n')
        _, actual, actual_volumes = self.extra_phy_hulls('remapped')
        self.extra_points_equal([p for hull in actual for p in hull],
                                [p for hull in expected for p in hull])
        self.assertAlmostEqual(sum(actual_volumes), sum(expected_volumes), places=3)

    def test_addconvexsrc_malformed_options_preserve_outputs(self):
        self.extra_boxes('box.smd', [(0, 0, 0, 2, 4, 6)])
        prefix = '$modelname preserved\n$body m box.smd\n'
        self.scene_qc(prefix + '$collisionmodel box.smd { $mass 20 }\n')
        saved = {p.name: p.read_bytes() for p in (self.root / 'models').iterdir() if p.is_file()}
        options = ['"offset pos[ 1 2 3 ] angle[ 0 0 0 ] scale[ 1"',
                   '"offset pos[ 1 2 3 ] angle[ 0 0 0 ] scale[ 1 ] junk"',
                   '"offset pos[ nan 2 3 ] angle[ 0 0 0 ] scale[ 1 ]"',
                   '"offset pos[ 1 2 3 ] angle[ 0 inf 0 ] scale[ 1 ]"',
                   '"offset pos[ 1 2 3 ] angle[ 0 0 0 ] scale[ 0 ]"',
                   '"offset pos[ 1 2 3 ] angle[ 0 0 0 ] scale[ 1e100 ]"',
                   '"offset pos[ 1 2 3 ] angle[ 0 0 0 ] scale[ 1e38 ]"',
                   'offset pos[ 1 2 3 ] angle[ 0 0 0 ] scale[ 1 ]', 'concavity']
        for option in options:
            output = self.scene_qc(prefix + '$collisionmodel box.smd {\n$mass 20\n'
                                  f'$addconvexsrc box.smd {option}\n}}\n', success=False)
            self.assertTrue('addconvexsrc' in output or 'invalid syntax' in output or
                            'non-finite transformed geometry' in output, output)
            self.assertEqual({p.name: p.read_bytes() for p in (self.root / 'models').iterdir() if p.is_file()}, saved)
