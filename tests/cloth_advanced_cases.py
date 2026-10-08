"""Black-box advanced FE authoring checks against emitted runtime records."""
import math
import struct
from cloth_cases import fe_resource, render_smd


def fe_names(data, array):
    at, count = array(8, 4)
    names = {}
    for i in range(count):
        pos = at + i * 4 + struct.unpack_from('<i', data, at + i * 4)[0]
        names[data[pos:data.index(b'\0', pos)].decode()] = i
    return names


class ClothAdvancedCases:
    def test_cloth_advanced_dynamic_parent_realign_preserves_world_collision_shapes(self):
        def rotate(q, v):
            x, y, z, w = q
            cross = (y * v[2] - z * v[1], z * v[0] - x * v[2], x * v[1] - y * v[0])
            again = (y * cross[2] - z * cross[1], z * cross[0] - x * cross[2], x * cross[1] - y * cross[0])
            return tuple(v[i] + 2 * (w * cross[i] + again[i]) for i in range(3))

        def world_shapes(data):
            start, array = fe_resource(data); names = fe_names(data, array)
            parent = names['driven']
            self.assertGreaterEqual(parent, struct.unpack_from('<H', data, start + 34)[0])
            at, _ = array(120, 32, 16); pose = struct.unpack_from('<8f', data, at + parent * 32)
            def point(local):
                p = rotate(pose[4:], local)
                return tuple(p[i] + pose[i] for i in range(3))
            result = []
            at, count = array(272, 24); self.assertEqual(count, 1)
            self.assertEqual(struct.unpack_from('<H', data, at)[0], parent)
            result.extend(point(struct.unpack_from('<3f', data, at + 4)))
            at, count = array(264, 40); self.assertEqual(count, 1)
            self.assertEqual(struct.unpack_from('<H', data, at)[0], parent)
            result.extend(point(struct.unpack_from('<3f', data, at + 4)))
            result.extend(point(struct.unpack_from('<3f', data, at + 16)))
            # The descending authored radii must be reordered with their centers.
            self.assertEqual(struct.unpack_from('<2f', data, at + 28), (2, 5))
            at, count = array(176, 24); self.assertEqual(count, 1)
            self.assertEqual(struct.unpack_from('<H', data, at)[0], parent)
            result.extend(point(struct.unpack_from('<3f', data, at + 8)))
            at, count = array(184, 24); self.assertEqual(count, 1)
            normal = rotate(pose[4:], struct.unpack_from('<3f', data, at + 4))
            result.extend(normal)
            result.append(struct.unpack_from('<f', data, at + 16)[0] + sum(normal[i] * pose[i] for i in range(3)))
            return result

        mesh = render_smd().replace('0 0 0 0 0 0 0\n1 0 0 0 0 0 0',
                                    '0 3 4 5 .1 .2 .3\n1 2 0 1 .3 -.2 .1')
        settings = '''advanced {
            rigid_sphere flap 1 2 3 4 1 .2
            rigid_capsule flap 1 2 3 5 4 6 18 2 1 .4
            node_sphere flap "$cloth_p2" out 2 3 4 6
            node_plane flap "$cloth_p3" .2 .3 .9 5
        }'''
        self.cloth_model(mesh=mesh, settings=settings, transform='$renamebone flap driven\n')
        original = world_shapes(self.mdl('fecloth'))
        self.cloth_model(mesh=mesh, settings=settings,
                         transform='$renamebone flap driven\n$forcerealign driven rotate 17 23 29\n')
        realigned = world_shapes(self.mdl('fecloth'))
        for a, b in zip(original, realigned): self.assertAlmostEqual(a, b, places=4)

    def test_cloth_advanced_collision_records_and_masks(self):
        self.cloth_model(settings='''advanced {
            node "$cloth_p2" { collision_mask 1 }
            node_sphere root "$cloth_p2" in 1 2 3 4
            node_sphere root "$cloth_p3" out 1 2 3 5
            node_plane root "$cloth_p2" 0 0 2 6
            stretch_capsule root flap 2 3 1 .4
            rigid_sphere root 1 2 3 5 1 .6
            rigid_capsule root 0 0 0 1 0 0 4 2 1 .7
        }''')
        data = self.mdl('fecloth'); start, array = fe_resource(data)
        names = fe_names(data, array)
        at, count = array(176, 24); self.assertEqual(count, 2)
        inside = struct.unpack_from('<2H5f', data, at)
        outside = struct.unpack_from('<2H5f', data, at + 24)
        self.assertEqual(inside[:2], (names['root'], names['$cloth_p2']))
        self.assertAlmostEqual(inside[2], 1 / 16)
        self.assertEqual(inside[3:6], (1, 2, 3)); self.assertEqual(inside[6], 0)
        self.assertEqual(outside[:2], (names['root'], names['$cloth_p3']))
        self.assertAlmostEqual(outside[2], 5); self.assertEqual(outside[6], 0)
        self.assertEqual(struct.unpack_from('<H', data, start + 50)[0], 1)
        at, count = array(184, 24); self.assertEqual(count, 1)
        plane = struct.unpack_from('<2H5f', data, at)
        self.assertEqual(plane[:2], inside[:2]); self.assertEqual(plane[2:6], (0, 0, 1, 3))
        self.assertEqual(plane[6], 0)
        at, count = array(256, 20); self.assertEqual(count, 1)
        cap = struct.unpack_from('<4H3f', data, at)
        self.assertEqual(cap[:4], (names['root'], names['flap'], 1, 0))
        self.assertEqual(cap[4:6], (2, 3)); self.assertAlmostEqual(cap[6], .4)
        at, count = array(272, 24); self.assertEqual(count, 1)
        sphere = struct.unpack_from('<2H5f', data, at)
        self.assertEqual(sphere[:2], (names['root'], 1)); self.assertAlmostEqual(sphere[-1], .6)
        at, count = array(264, 40); self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('<2H', data, at), (names['root'], 1))
        self.assertAlmostEqual(struct.unpack_from('<f', data, at + 36)[0], .7)
        static = struct.unpack_from('<H', data, start + 34)[0]
        at, count = array(296, 2, 2)
        self.assertEqual(struct.unpack_from('<H', data, at + 2 * (names['$cloth_p2'] - static))[0], 1)
        self.assertNotEqual(struct.unpack_from('<H', data, at + 2 * (count - 1))[0] & 1, 0)

    def test_cloth_advanced_mass_rod_spring_and_element_weights(self):
        self.cloth_model(settings='''advanced {
            node "$cloth_p2" { mass 4 damping .2 }
            node "$cloth_p3" { mass 2 damping .3 }
            rod "$cloth_p2" "$cloth_p3" 10 .5 1 3 .8
            spring "$cloth_p2" "$cloth_p3" 20 3
        }''')
        data = self.mdl('fecloth'); start, array = fe_resource(data); names = fe_names(data, array)
        a, b = names['$cloth_p2'], names['$cloth_p3']
        at, count = array(144, 4)
        self.assertAlmostEqual(struct.unpack_from('<f', data, at + a * 4)[0], .25)
        self.assertAlmostEqual(struct.unpack_from('<f', data, at + b * 4)[0], .5)
        at, count = array(128, 20)
        rods = [struct.unpack_from('<2H4f', data, at + i * 20) for i in range(count)]
        rod = next(r for r in rods if r[:2] == (a, b))
        self.assertEqual(rod[2:4], (10, 5)); self.assertAlmostEqual(rod[4], 1 / 7)
        self.assertAlmostEqual(rod[5], .8)
        self.assertEqual(array(112, 80, 16)[1], count)
        at, count = array(200, 20); self.assertEqual(count, 1)
        spring = struct.unpack_from('<2H4f', data, at)
        factor = .25 * math.exp(-.2) + .5 * math.exp(-.3)
        self.assertEqual(spring[:2], (a, b)); self.assertAlmostEqual(spring[2], 16)
        self.assertAlmostEqual(spring[3], 20 * factor, places=5)
        self.assertAlmostEqual(spring[4], 3 * factor, places=5)
        self.assertAlmostEqual(spring[5], .25 * math.exp(-.2) / factor, places=5)
        at, count = array(208, 80, 16); self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('<4H', data, at), (a,) * 4)
        at, count = array(88, 76)
        for i in range(count):
            ids = struct.unpack_from('<4H', data, at + i * 76)
            if a in ids and b in ids:
                weights = [struct.unpack_from('<f', data, at + i * 76 + 24 + j * 16)[0] for j in range(4)]
                self.assertAlmostEqual(weights[ids.index(a)] / weights[ids.index(b)], 2)

    def test_cloth_advanced_follow_local_legacy_and_ftl(self):
        self.cloth_model(settings='''advanced {
            node "$cloth_p2" { mass 4 damping 8 legacy_stretch 2 local_position .3 local_rotation .4 collision_radius 1.25 }
            follow "$cloth_p2" "$cloth_p3" .75
            follow root "$cloth_p2" .25
            ftl true mass_damping true uninertial true
            volumetric .6 world_radius 3 add_world_radius .5 smoothing 2 3
        }''')
        data = self.mdl('fecloth'); start, array = fe_resource(data); names = fe_names(data, array)
        static = struct.unpack_from('<H', data, start + 34)[0]; a = names['$cloth_p2']
        at, count = array(168, 8); self.assertEqual(count, 2)
        self.assertEqual(struct.unpack_from('<2Hf', data, at), (names['root'], a, .25))
        self.assertEqual(struct.unpack_from('<2Hf', data, at + 8), (a, names['$cloth_p3'], .75))
        at, count = array(192, 16); self.assertAlmostEqual(struct.unpack_from('<f', data, at + a * 16)[0], 2)
        for field, expected in ((248, .3), (240, .4), (232, 1.25)):
            at, count = array(field, 4)
            self.assertAlmostEqual(struct.unpack_from('<f', data, at + 4 * (a - static))[0], expected)
        # Replay the Source1 SetAbsOrigin branch for a small ordinary movement.
        # max(author responses)==1 must not skip the heterogeneous per-node array.
        at, count = array(248, 4)
        responses = struct.unpack_from('<' + 'f' * count, data, at)
        gate = struct.unpack_from('<f', data, start + 24)[0]
        self.assertEqual(max(responses), 1)
        self.assertLess(gate, 1); self.assertGreater(gate, .999999)
        fraction = min(1, max(-1, 1 - gate))
        movement = [10 * min(1, max(-1, 1 - response)) for response in responses] if 0 < fraction < 1 else [10 * fraction] * count
        self.assertAlmostEqual(movement[a - static], 7, places=5)
        self.assertEqual(movement[responses.index(1)], 0)
        at, count = array(224, 4); self.assertAlmostEqual(struct.unpack_from('<f', data, at + a * 4)[0], 2)
        flags = struct.unpack_from('<I', data, start + 20)[0]
        self.assertEqual(flags & ((1 << 4) | (1 << 5) | (1 << 12)), (1 << 4) | (1 << 5) | (1 << 12))
        self.assertAlmostEqual(struct.unpack_from('<f', data, start + 524)[0], 3.5)
        self.assertAlmostEqual(struct.unpack_from('<f', data, start + 528)[0], .6)
        self.assertEqual(struct.unpack_from('<2H', data, start + 532), (2, 3))
        at, count = array(152, 16)
        children = {struct.unpack_from('<H', data, at + i * 16 + 2)[0] for i in range(count)}
        self.assertTrue({names[f'$cloth_p{i}'] for i in range(6)} <= children)

    def test_cloth_advanced_rope_without_proxy_faces(self):
        self.write('gameinfo.txt', 'GameInfo { FileSystem { SteamAppId 730 } }')
        mesh = render_smd().replace('1 "flap" 0', '1 "flap" 0\n2 "tip" 1')
        mesh = mesh.replace('1 0 0 0 0 0 0\nend', '1 0 0 10 0 0 0\n2 0 0 10 0 0 0\nend')
        self.write('rope_mesh.smd', mesh)
        self.scene_qc('''$modelname advancedrope
            $body m rope_mesh.smd
            $cloth advanced {
                node root { simulated false }
                node flap { mass 2 }
                node tip { mass 4 }
                rope { root flap tip }
            }
        ''')
        data = self.mdl('advancedrope'); start, array = fe_resource(data); names = fe_names(data, array)
        self.assertEqual(struct.unpack_from('<2H', data, start + 32), (3, 1))
        self.assertEqual(struct.unpack_from('<H', data, start + 62)[0], 1)
        at, count = array(64, 2, 2); self.assertEqual(count, 4)
        self.assertEqual(struct.unpack_from('<4H', data, at), (4, names['root'], names['flap'], names['tip']))
        at, count = array(128, 20); self.assertEqual(count, 2)
        for i in range(count): self.assertAlmostEqual(struct.unpack_from('<f', data, at + i * 20 + 4)[0], 10)
        self.assertEqual(array(88, 76)[1], 0); self.assertEqual(array(312, 2, 2)[1], 0)

    def test_cloth_advanced_os_offset_and_qc_scale_snapshot(self):
        self.cloth_model(settings='''advanced {
            node "$rope_offset" { position 1 2 3 parent root mass 2 }
            os_offset root "$rope_offset"
            rod root "$rope_offset" auto 1 1 1 1
        }''')
        data = self.mdl('fecloth'); start, array = fe_resource(data); names = fe_names(data, array)
        at, count = array(160, 4); self.assertEqual(count, 1)
        self.assertEqual(struct.unpack_from('<2H', data, at), (names['root'], names['$rope_offset']))
        at, count = array(152, 16)
        self.assertNotIn(names['$rope_offset'], [struct.unpack_from('<H', data, at + i * 16 + 2)[0] for i in range(count)])
        self.cloth_model(transform='$scale 2\n', settings='advanced { node_sphere root "$cloth_p2" out 1 2 3 4 }')
        data = self.mdl('fecloth'); start, array = fe_resource(data)
        at, count = array(176, 24); self.assertEqual(count, 1)
        record = struct.unpack_from('<2H5f', data, at)
        self.assertEqual(record[2:6], (8, 2, 4, 6)); self.assertEqual(record[6], 0)

    def test_cloth_advanced_rejects_invalid_graph_and_parameters(self):
        for settings, message in (
            ('advanced { node "$cloth_p2" { mass -1 } }', 'out of range'),
            ('advanced { node_plane root "$cloth_p2" 0 0 0 1 }', 'normal is zero'),
            ('advanced { node "$cloth_p2" { collision_mask 65536 } }', 'out of range'),
            ('advanced { follow "$cloth_p2" "$cloth_p3" 1 follow "$cloth_p3" "$cloth_p2" 1 }', 'cyclic follow'),
            ('advanced { rod "$cloth_p2" "$cloth_p2" 1 1 1 1 1 }', 'endpoints must differ'),
        ):
            with self.subTest(settings=settings):
                result = self.cloth_model(settings=settings, success=False)
                self.assertIn(message, result)
