import struct


class IntegrationPolicyCases:
    def test_neko_condition_mode_matches_fixed_reference_cases(self):
        cases = [
            ('$definevariable flag ON\n$if flag == ON', True),
            ('$definevariable flag ON\n$if flag == "ON"', True),
            ('$if absent != ON', False),
            ('$definevariable flag ON\n$if flag == "ON" || absent == "ON"', True),
            ('$if 1e2 == 100', False),
        ]
        for condition, expected in cases:
            with self.subTest(condition=condition):
                text = self.run_qc('$qccompatibility neko\n$modelname policy\n' + condition +
                    '\n$Msg POLICY_PASS\n$else\n$Msg POLICY_FALSE\n$endif\n')
                self.assertIn('POLICY_PASS' if expected else 'POLICY_FALSE', text)
                self.assertNotIn('POLICY_FALSE' if expected else 'POLICY_PASS', text)
        text = self.run_qc('$qccompatibility neko\n$modelname policy\n$if 1\n$Msg FIRST_WON\n'
                           '$elif $undefined$ == ON\n$Msg LATE_WON\n$endif\n')
        self.assertIn('FIRST_WON', text)
        self.assertNotIn('LATE_WON', text)

    def test_native_condition_mode_remains_strict(self):
        for prefix in ('', '$qccompatibility neko\n$qccompatibility native\n'):
            text = self.run_qc(prefix+'$modelname policy\n$if absent != ON\n$Msg BAD\n$endif\n', success=False)
            self.assertIn('unknown variable "absent"', text)

    def test_weight_policy_is_source_scoped_and_preserves_normalization(self):
        lines = (self.root/'mesh.smd').read_text().splitlines()
        for i in range(lines.index('triangles')+2, len(lines)-1):
            lines[i] += ' 2 0 .9995 1 .0005'
        self.write('mesh.smd', '\n'.join(lines)+'\n')
        self.scene_qc('$modelname weights\n$bonecullmethod none\n$boneweightpolicy ce\n'
                      '$body ce mesh.smd\n$boneweightpolicy native\n$body native mesh.smd\n')
        data = (self.root/'models/weights.vvd').read_bytes()
        start = struct.unpack_from('<i',data,56)[0]
        self.assertEqual([data[start+i*48+15] for i in range(6)], [1]*3+[2]*3)
        for i in range(6):
            weights=struct.unpack_from('<3f',data,start+i*48)
            self.assertAlmostEqual(sum(weights),1,places=6)
