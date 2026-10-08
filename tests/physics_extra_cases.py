"""Geometry regressions for the historical CSGO $addconvexsrc source contract."""
import math
import struct


class PhysicsExtraCases:
    def extra_boxes(self, name, boxes):
        text = ('version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n'
                '0 0 0 0 0 0 0\nend\ntriangles\n')
        corners = []
        # A shared normal deliberately makes touching authored parts weld.
        triangles = [(0, 2, 1), (0, 3, 2), (4, 5, 6), (4, 6, 7),
                     (0, 1, 5), (0, 5, 4), (3, 7, 6), (3, 6, 2),
                     (0, 4, 7), (0, 7, 3), (1, 2, 6), (1, 6, 5)]
        for x0, y0, z0, x1, y1, z1 in boxes:
            vertices = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
                        (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
            corners.extend(vertices)
            for triangle in triangles:
                text += 'material\n'
                for index in triangle:
                    x, y, z = vertices[index]
                    text += f'0 {x} {y} {z} 0 0 1 0 0\n'
        self.write(name, text + 'end\n')
        return corners

    def extra_phy_hulls(self, name):
        data = (self.root / f'models/{name}.phy').read_bytes()
        self.assertEqual(struct.unpack_from('<i', data, 8)[0], 1)
        surface = 20 + 28
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
