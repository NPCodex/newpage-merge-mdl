"""Skin groups shared by models with different rendered material subsets."""
import struct


class IntegrationSkinCases:
    def skin_materials(self, name):
        data = self.mdl(name)
        count, start = struct.unpack_from('<2i', data, 204)
        names = []
        for i in range(count):
            at = start + i * 64
            offset = at + struct.unpack_from('<i', data, at)[0]
            names.append(data[offset:data.index(b'\0', offset)].decode())
        width, rows, start = struct.unpack_from('<3i', data, 220)
        self.assertEqual(width, count)
        skins = [struct.unpack_from('<' + 'h' * width, data, start + i * width * 2)
                 for i in range(rows)]
        return names, [[names[index] for index in row] for row in skins]

    def test_shared_skin_group_ignores_absent_columns_and_keeps_rows(self):
        output = self.run_qc('$modelname shared_skins\n$texturegroup family {\n'
                             '{ absent material }\n{ absent_variant alternate }\n'
                             '{ absent_other material }\n}\n')
        names, skins = self.skin_materials('shared_skins')
        self.assertEqual(names, ['material', 'alternate'])
        self.assertEqual(skins, [['material', 'alternate'],
                                ['alternate', 'alternate'],
                                ['material', 'alternate']])
        self.assertEqual(output.count('ignoring unused base material "absent"'), 1)

    def test_shared_skin_group_with_no_used_columns_keeps_all_skin_numbers(self):
        self.run_qc('$modelname absent_skins\n$texturegroup family {\n'
                    '{ absent }\n{ absent_variant }\n{ absent_other }\n}\n')
        names, skins = self.skin_materials('absent_skins')
        self.assertEqual(names, ['material'])
        self.assertEqual(skins, [['material']] * 3)

    def test_skin_replacement_does_not_create_a_rendered_base_column(self):
        self.run_qc('$modelname stable_skins\n$texturegroup family {\n'
                    '{ material alternate }\n{ alternate ignored }\n'
                    '{ material also_ignored }\n}\n')
        names, skins = self.skin_materials('stable_skins')
        self.assertEqual(names, ['material', 'alternate'])
        self.assertEqual(skins, [['material', 'alternate'],
                                ['alternate', 'alternate'],
                                ['material', 'alternate']])

    def test_shared_skin_group_uses_merged_material_and_culls_original_column(self):
        mesh = (self.root / 'mesh.smd').read_text()
        triangle = ('second\n0 2 0 0 0 0 1 0 0\n'
                    '0 3 0 0 0 0 1 1 0\n0 2 1 0 0 0 1 0 1\n')
        self.write('merged.smd', mesh[:-4] + triangle + 'end\n')
        output = self.scene_qc('$modelname merged_skins\n'
                              '$body m merged.smd RenameMat material shared RenameMat second shared\n'
                              '$texturegroup family { { material shared } { old_variant shared_variant } }\n'
                              '$lod 10 { }\n')
        names, skins = self.skin_materials('merged_skins')
        self.assertEqual(names, ['shared', 'shared_variant'])
        self.assertEqual(skins, [['shared', 'shared_variant'], ['shared_variant', 'shared_variant']])
        self.assertIn('ignoring unused base material "material"', output)
        data = self.mdl('merged_skins')
        body = struct.unpack_from('<i', data, 236)[0]
        model = body + struct.unpack_from('<i', data, body + 12)[0]
        self.assertEqual(struct.unpack_from('<i', data, model + 72)[0], 1)
        self.assertEqual(struct.unpack_from('<i', data, model + 80)[0], 6)

    def test_shared_skin_group_does_not_relax_row_or_rename_errors(self):
        output = self.run_qc('$modelname malformed_skins\n$texturegroup family {\n'
                             '{ absent material }\n{ only_one }\n}\n', success=False)
        self.assertIn('every material row must have 2 entries', output)
        self.assertFalse((self.root / 'models/malformed_skins.mdl').exists())
        output = self.scene_qc('$modelname bad_rename\n$body m mesh.smd\n'
                              '$renamematerial missing renamed\n', success=False)
        self.assertIn('$renamematerial: "missing" is not a material of this model', output)
        self.assertFalse((self.root / 'models/bad_rename.mdl').exists())
