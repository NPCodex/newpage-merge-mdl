"""Black-box NekoMDL 2.4 compatibility probes using self-authored inputs."""
import re
import struct


class Neko24Cases:
    def neko24_outputs(self, name):
        return {path.name: path.read_bytes()
                for path in (self.root / 'models').glob(name + '.*')}

    def neko24_body_points(self, name):
        """Read each body's vertex range from the MDL and positions from VVD."""
        mdl = self.mdl(name)
        vvd = (self.root / 'models' / (name + '.vvd')).read_bytes()
        vertex_start = struct.unpack_from('<i', vvd, 56)[0]
        count, start = struct.unpack_from('<2i', mdl, 232)
        result = {}
        for index in range(count):
            body = start + index * 16
            name_start = body + struct.unpack_from('<i', mdl, body)[0]
            body_name = mdl[name_start:mdl.index(b'\0', name_start)].decode()
            self.assertEqual(struct.unpack_from('<i', mdl, body + 4)[0], 1)
            model = body + struct.unpack_from('<i', mdl, body + 12)[0]
            vertices, offset = struct.unpack_from('<2i', mdl, model + 80)
            result[body_name] = sorted(struct.unpack_from('<3f', vvd,
                vertex_start + offset + vertex * 48 + 16) for vertex in range(vertices))
        return result

    def neko24_keyvalues(self, name):
        """Parse the serialized model KeyValues, independent of compiler code."""
        data = self.mdl(name)
        start, size = struct.unpack_from('<2i', data, 312)
        if not size:
            return {}
        self.assertGreater(size, 1)
        self.assertLessEqual(start + size, len(data))
        self.assertEqual(data[start + size - 1], 0)
        text = data[start:start + size - 1].decode('utf-8')
        tokens = re.findall(r'"[^"\n]*"|[{}]|[^\s{}"]+', text)
        at = 0

        def word(token):
            return token[1:-1] if token.startswith('"') else token

        def block():
            nonlocal at
            result = {}
            while at < len(tokens) and tokens[at] != '}':
                key = word(tokens[at])
                at += 1
                self.assertNotIn(key, result, 'duplicate serialized KeyValues key')
                self.assertLess(at, len(tokens))
                if tokens[at] == '{':
                    at += 1
                    result[key] = block()
                    self.assertLess(at, len(tokens))
                    self.assertEqual(tokens[at], '}')
                    at += 1
                else:
                    self.assertNotEqual(tokens[at], '}')
                    result[key] = word(tokens[at])
                    at += 1
            return result

        result = block()
        self.assertEqual(at, len(tokens))
        self.assertEqual(list(result), ['mdlkeyvalue'])
        return result['mdlkeyvalue']

    def neko24_two_materials(self):
        mesh = (self.root / 'mesh.smd').read_text()
        triangle = ('second\n0 2 0 0 0 0 1 0 0\n'
                    '0 3 0 0 0 0 1 1 0\n0 2 1 0 0 0 1 0 1\n')
        self.write('two_materials.smd', mesh[:-4] + triangle + 'end\n')

    @staticmethod
    def neko24_groups(first='group_alpha', second='group_beta'):
        return (f'$texturegroup "{first}" {{ {{ material }} {{ red }} }}\n'
                f'$texturegroup "{second}" {{ {{ second }} {{ blue }} }}\n')

    def test_neko24_disable_cache_reloads_animation_sources_without_mutating_earlier_clips(self):
        self.animation_fixture()
        before = ('$body mesh mesh.smd\n$animationcullmethod none\n'
                  '$scale 1\n$animation first moving.smd\n'
                  '$scale 2\n$animation reused moving.smd\n')
        output = self.scene_qc('$modelname cached\n' + before + '$sequence idle first\n')
        self.assertEqual(output.count('loading animation:'), 1)
        original = self.animation_poses('cached', 'first')
        self.assertEqual(original, self.animation_poses('cached', 'reused'))
        self.assertEqual(len(original), 2)
        for frame, expected in zip(original, (10, 20)):
            self.assertAlmostEqual(frame[0], expected, delta=.02)
        for directive in ('$DisableCache', '$dIsAbLeCaChE'):
            with self.subTest(directive=directive):
                output = self.scene_qc('$modelname refreshed\n' + before + directive + '\n'
                    '$animation second moving.smd\n$scale 3\n$animation third moving.smd\n'
                    '$sequence idle first\n')
                self.assertEqual(output.count('loading animation:'), 3)
                self.assertEqual(self.animation_poses('refreshed', 'first'), original)
                self.assertEqual(self.animation_poses('refreshed', 'reused'), original)
                for clip, scale in (('second', 2), ('third', 3)):
                    poses = self.animation_poses('refreshed', clip)
                    self.assertEqual(len(poses), 2)
                    for actual, base in zip(poses, original):
                        # Each emitted animation is quantized independently.
                        for value, expected in zip(actual[:3], base[:3]):
                            self.assertAlmostEqual(value, expected * scale, delta=.02)
                        for value, expected in zip(actual[3:], base[3:]):
                            self.assertAlmostEqual(value, expected, places=5)

    def test_neko24_disable_cache_preserves_private_body_scale_behavior(self):
        # Body imports are already private in NewPage: the reference's stale
        # body reuse must not become the default merely to match its cache test.
        self.scene_qc('$modelname private_bodies\n$scale 1\n$body first mesh.smd\n'
                      '$scale 2\n$body second mesh.smd\n'
                      '$DisableCache\n$scale 3\n$body third mesh.smd\n')
        points = self.neko24_body_points('private_bodies')
        self.assertEqual(len(points['first']), 3)
        self.assertGreater(max(sum(x*x for x in point)
                               for point in points['first']), .9)
        for body, scale in (('second', 2), ('third', 3)):
            self.assertEqual(len(points[body]), 3)
            for actual, base in zip(points[body], points['first']):
                for value, expected in zip(actual, base):
                    self.assertAlmostEqual(value, expected * scale, places=5)

    def test_neko24_disable_cache_rejects_boolean_arguments_before_replacing_outputs(self):
        self.scene_qc('$modelname cache_arg\n$body first mesh.smd\n')
        previous = self.neko24_outputs('cache_arg')
        for argument in ('0', '1'):
            with self.subTest(argument=argument):
                self.scene_qc('$modelname cache_arg\n$body first mesh.smd\n'
                              '$DisableCache ' + argument + '\n', success=False)
                self.assertEqual(self.neko24_outputs('cache_arg'), previous)

    def test_neko24_material_group_metadata_and_identity_row_are_opt_in(self):
        self.neko24_two_materials()
        for prefix, suffix, neko in (
                ('', '', False),
                ('$qccompatibility neko\n', '$qccompatibility native\n', False),
                ('', '$qccompatibility neko\n', True)):
            with self.subTest(prefix=prefix, suffix=suffix):
                self.scene_qc(prefix + '$modelname grouped\n$body m two_materials.smd\n' +
                              self.neko24_groups() + suffix)
                names, rows = self.skin_materials('grouped')
                self.assertEqual(names, ['material', 'second', 'red', 'blue'])
                expected = [names, ['red', 'second', 'red', 'blue'],
                            ['material', 'blue', 'red', 'blue']]
                self.assertEqual(rows, expected + ([names] if neko else []))
                keyvalues = self.neko24_keyvalues('grouped')
                if neko:
                    self.assertEqual(keyvalues['neko_material_group'], {
                        'group_alpha': {'i': '1', 'c': '1'},
                        'group_beta': {'i': '2', 'c': '1'}})
                else:
                    self.assertNotIn('neko_material_group', keyvalues)

    def test_neko24_single_texturegroup_keeps_original_skin_count_and_keyvalues(self):
        self.run_qc('$qccompatibility neko\n$modelname single_group\n'
                    '$texturegroup only { { material } { alternate } }\n'
                    '$keyvalues { custom { value preserved } }\n')
        names, rows = self.skin_materials('single_group')
        self.assertEqual(names, ['material', 'alternate'])
        self.assertEqual(rows, [names, ['alternate', 'alternate']])
        self.assertEqual(self.neko24_keyvalues('single_group'),
                         {'custom': {'value': 'preserved'}})

    def test_neko24_material_group_indices_include_each_alternative_and_preserve_user_keys(self):
        self.neko24_two_materials()
        self.scene_qc('$qccompatibility neko\n$modelname named_groups\n'
                      '$body m two_materials.smd\n'
                      '$keyvalues { custom { note neko_material_group '
                      'neko_material_group { value preserved } } }\n'
                      '$texturegroup alpha { { material } { red } { orange } }\n'
                      '$texturegroup beta { { second } { blue } }\n'
                      '$texturegroup "gamma { swatch }" { { material } }\n'
                      '$keyvalues { another retained }\n')
        names, rows = self.skin_materials('named_groups')
        self.assertEqual(names, ['material', 'second', 'red', 'orange', 'blue'])
        self.assertEqual(rows, [names, ['red', 'second', 'red', 'orange', 'blue'],
                               ['orange', 'second', 'red', 'orange', 'blue'],
                               ['material', 'blue', 'red', 'orange', 'blue'], names])
        self.assertEqual(self.neko24_keyvalues('named_groups'), {
            'custom': {'note': 'neko_material_group',
                       'neko_material_group': {'value': 'preserved'}},
            'another': 'retained',
            'neko_material_group': {'alpha': {'i': '1', 'c': '2'},
                                    'beta': {'i': '3', 'c': '1'},
                                    'gamma { swatch }': {'i': '4', 'c': '0'}}})

    def test_neko24_material_group_metadata_rejects_ambiguous_names_without_overwrite(self):
        self.neko24_two_materials()
        base = '$qccompatibility neko\n$modelname safe_groups\n$body m two_materials.smd\n'
        self.scene_qc(base + self.neko24_groups())
        previous = self.neko24_outputs('safe_groups')
        for first, second in (('same', 'SAME'), ('', 'other'),
                              ('bad\\name', 'other'), ('bad\tname', 'other')):
            with self.subTest(first=first, second=second):
                output = self.scene_qc(base + self.neko24_groups(first, second), success=False)
                self.assertIn('texturegroup', output.lower())
                self.assertEqual(self.neko24_outputs('safe_groups'), previous)
        output = self.scene_qc(base + self.neko24_groups() +
                              '$keyvalues { NeKo_MaTeRiAl_GrOuP { fake value } }\n',
                              success=False)
        self.assertIn('neko_material_group', output.lower())
        self.assertEqual(self.neko24_outputs('safe_groups'), previous)

    def test_neko24_material_group_counts_include_explicit_sets_and_absent_columns(self):
        self.run_qc('$qccompatibility neko\n$modelname mixed_groups\n'
                    '$texturegroup explicit { $set { material material red } $set { } }\n'
                    '$texturegroup absent { { unused } { unused_variant } }\n')
        names, rows = self.skin_materials('mixed_groups')
        self.assertEqual(names, ['material', 'red'])
        self.assertEqual(rows, [names, ['red', 'red'], names, names, names])
        self.assertEqual(self.neko24_keyvalues('mixed_groups'), {
            'neko_material_group': {'explicit': {'i': '1', 'c': '2'},
                                    'absent': {'i': '3', 'c': '1'}}})

    def test_neko24_final_identity_skin_row_is_counted_in_capacity_check(self):
        self.neko24_two_materials()
        base = '$modelname skin_capacity\n$body m two_materials.smd\n' + self.neko24_groups()
        self.scene_qc('$qccompatibility neko\n' + base)
        previous = self.neko24_outputs('skin_capacity')
        # Four materials give 24 bytes for three rows, 32 with the Neko tail.
        # The full MDL cannot fit either budget; its skin-specific diagnostic
        # distinguishes the early table check from the later whole-file check.
        for profile, limit, skin_failure in (('native', 24, False),
                                             ('neko', 24, True), ('neko', 32, False)):
            with self.subTest(profile=profile, limit=limit):
                output = self.scene_qc(f'$qccompatibility {profile}\n'
                    f'$MDLOutputBufferSize {limit / (1024 * 1024):.20f}\n' + base,
                    success=False)
                if skin_failure:
                    self.assertIn('skin table exceeds output capacity (32 bytes)', output)
                else:
                    self.assertNotIn('skin table exceeds output capacity', output)
                self.assertEqual(self.neko24_outputs('skin_capacity'), previous)

    def test_neko24_bodygroup_state_limit_is_strict_only_in_neko_profile(self):
        def groups(count):
            return ''.join(f'$bodygroup choice{i} {{ blank\nblank\n}}\n'
                           for i in range(count))

        base = '$modelname neko_states\n$body mesh mesh.smd\n'
        self.scene_qc('$qccompatibility neko\n' + base + groups(30))
        mdl = self.mdl('neko_states')
        count, start = struct.unpack_from('<2i', mdl, 232)
        self.assertEqual(count, 31)
        self.assertEqual(struct.unpack_from('<i', mdl, start + 30 * 16 + 8)[0], 1 << 29)
        previous = self.neko24_outputs('neko_states')
        output = self.scene_qc('$qccompatibility neko\n' + base + groups(31), success=False)
        self.assertIn('bodygroup', output.lower())
        self.assertEqual(self.neko24_outputs('neko_states'), previous)
        for prefix in ('', '$qccompatibility neko\n$qccompatibility native\n'):
            with self.subTest(prefix=prefix):
                self.scene_qc(prefix + base + groups(31))
                mdl = self.mdl('neko_states')
                count, start = struct.unpack_from('<2i', mdl, 232)
                self.assertEqual(count, 32)
                self.assertEqual(struct.unpack_from('<i', mdl, start + 31 * 16 + 8)[0], 1 << 30)
