"""Output-level physics mass regressions, mixed into compatibility.py."""

import math
import re
import struct
import zlib


class PhysicsMassCases:
    def mass_fixture(self, edge=10, ragdoll=False):
        nodes = '0 "root" -1\n'
        poses = '0 0 0 0 0 0 0\n'
        if ragdoll:
            nodes += '1 "helper" 0\n2 "limb" 1\n'
            poses += '1 0 0 0 0 0 0\n2 0 0 0 0 0 0\n'
        text = f'version 1\nnodes\n{nodes}end\nskeleton\ntime 0\n{poses}end\ntriangles\n'
        for bone, size, shift in ([(0, edge, 0), (2, edge * 2, edge * 3)] if ragdoll else [(0, edge, 0)]):
            points = [(shift, 0, 0), (shift + size, 0, 0), (shift, size, 0), (shift, 0, size)]
            for face in [(0, 2, 1), (0, 1, 3), (0, 3, 2), (1, 2, 3)]:
                text += 'material\n'
                for vertex in face:
                    x, y, z = points[vertex]
                    text += f'{bone} {x} {y} {z} 0 0 1 0 0\n'
        self.write('mass.smd', text + 'end\n')

    def mass_surfaces(self, definitions, additional=''):
        self.write('gameinfo.txt', 'GameInfo { FileSystem { SearchPaths { Game "|gameinfo_path|." } } }')
        files = 'file "scripts/surfaceproperties.txt"'
        if additional:
            files += '\nFiLe "scripts/surfaceproperties_extra.txt"'
            self.write('scripts/surfaceproperties_extra.txt', additional)
        self.write('scripts/surfaceproperties_manifest.txt', 'surfaceproperties_manifest {\n' + files + '\n}')
        self.write('scripts/surfaceproperties.txt', definitions)

    def mass_qc(self, name='mass', options='$automass', surface='default', ragdoll=False, extra='', success=True):
        collision = '$collisionjoints' if ragdoll else '$collisionmodel'
        qc = (f'$modelname {name}\n$bonecullmethod none\n$surfaceprop "{surface}"\n'
              f'{extra}\n$body m mass.smd\n{collision} mass.smd {{ {options} }}\n')
        return self.scene_qc(qc, success=success)

    def mass_output(self, name='mass'):
        data = (self.root / 'models' / f'{name}.phy').read_bytes()
        header_size, _, count, _ = struct.unpack_from('<4i', data)
        cursor = header_size
        for _ in range(count):
            length = struct.unpack_from('<i', data, cursor)[0]
            cursor += 4 + length
        text = data[cursor:].decode('utf-8').rstrip('\0')
        solids = [dict(re.findall(r'"([^"\n]+)"\s+"([^"\n]*)"', block))
                  for block in re.findall(r'(?m)^solid\s*\{([^}]*)\}', text)]
        total = float(re.search(r'"totalmass"\s+"([^"]+)"', text).group(1))
        # studiohdr_t::mass must agree with the .phy editparams total.
        self.assertAlmostEqual(struct.unpack_from('<f', self.mdl(name), 328)[0], total, places=4)
        return solids, total

    def test_automass_uses_density_and_cubic_size_scaling(self):
        self.mass_surfaces('"default" { "density" "2000" "thickness" "-1" }',
                           '"DEFAULT" { "density" "1000" }')
        masses = []
        for edge in (10, 20):
            self.mass_fixture(edge)
            self.mass_qc()
            solids, total = self.mass_output()
            expected = edge ** 3 / 6 * .0254 ** 3 * 1000
            self.assertAlmostEqual(total, expected, places=4)
            self.assertAlmostEqual(float(solids[0]['mass']), expected, places=4)
            masses.append(total)
        self.assertAlmostEqual(masses[1] / masses[0], 8, places=4)
        self.mass_qc(options='$automass $mass 20')
        solids, total = self.mass_output()
        self.assertEqual(total, 20)
        self.assertEqual(float(solids[0]['mass']), 20)
        self.mass_fixture(1)
        self.mass_qc()
        solids, total = self.mass_output()
        self.assertLess(total, 1)
        self.assertEqual(float(solids[0]['mass']), 1)

    def test_automass_joint_surface_inheritance_and_massbias_distribution(self):
        self.mass_surfaces('default { density 1000 thickness -1 }\nSteel { density 4000 }',
                           'Alloy { BaSe STEEL }')
        self.mass_fixture(ragdoll=True)
        self.mass_qc(ragdoll=True, options='$automass $rootbone root $jointmassbias limb 2',
                     extra='$jointsurfaceprop helper aLLoY')
        solids, total = self.mass_output()
        by_name = {solid['name']: solid for solid in solids}
        self.assertEqual(set(by_name), {'root', 'limb'})
        self.assertEqual(by_name['limb']['surfaceprop'], 'aLLoY')
        self.assertEqual(by_name['root']['surfaceprop'], 'default')
        expected_total = (10 ** 3 / 6 * 1000 + 20 ** 3 / 6 * 4000) * .0254 ** 3
        self.assertAlmostEqual(total, expected_total, places=4)
        # CSGO computes material-based TOTAL mass, then distributes that total
        # using volume * massbias. It does not assign each material's mass directly.
        self.assertAlmostEqual(float(by_name['root']['mass']), expected_total / 17, places=4)
        self.assertAlmostEqual(float(by_name['limb']['mass']), expected_total * 16 / 17, places=4)

    def test_automass_shell_thickness_uses_surface_area(self):
        self.mass_surfaces('default { DeNsItY 1000 thickness -1 }\nShell { base DEFAULT ThIcKnEsS 2 }',
                           'SHELL { density 2000 }')
        masses = []
        for edge in (10, 20):
            self.mass_fixture(edge)
            self.mass_qc(surface='shell')
            solids, total = self.mass_output()
            area = (3 + math.sqrt(3)) * edge ** 2 / 2
            expected = area * 2 * .0254 ** 3 * 2000
            self.assertAlmostEqual(total, expected, places=4)
            self.assertAlmostEqual(float(solids[0]['mass']), expected, places=4)
            masses.append(total)
        self.assertAlmostEqual(masses[1] / masses[0], 4, places=4)

    def test_automass_reads_manifest_and_surface_data_from_external_vpk(self):
        self.mass_fixture()
        contents = {
            'surfaceproperties_manifest': b'surfaceproperties_manifest { file "scripts/custom.txt" }',
            'custom': b'default { density 3000 thickness -1 }',
        }
        tree = b'txt\0scripts\0'
        payload = b''
        for name, data in contents.items():
            preload, body = data[:7], data[7:]
            tree += name.encode() + b'\0' + struct.pack('<IHHIIH', zlib.crc32(data), len(preload), 0,
                                                       len(payload), len(body), 0xffff) + preload
            payload += body
        tree += b'\0\0\0'
        (self.root / 'massprops_dir.vpk').write_bytes(struct.pack('<III', 0x55aa1234, 1, len(tree)) + tree)
        (self.root / 'massprops_000.vpk').write_bytes(payload)
        self.write('gameinfo.txt', 'GameInfo { FileSystem { SearchPaths { Game "|gameinfo_path|massprops.vpk" } } }')
        self.mass_qc()
        solids, total = self.mass_output()
        self.assertAlmostEqual(total, 10 ** 3 / 6 * .0254 ** 3 * 3000, places=4)
        self.assertAlmostEqual(float(solids[0]['mass']), total, places=4)

    def test_automass_unknown_surface_and_missing_manifest_have_defined_fallbacks(self):
        self.mass_fixture()
        self.mass_surfaces('default { density 1500 thickness 0 }')
        output = self.mass_qc(surface='missing_surface')
        self.assertIn("unknown surface 'missing_surface'", output)
        _, total = self.mass_output()
        self.assertAlmostEqual(total, 10 ** 3 / 6 * .0254 ** 3 * 1500, places=4)
        (self.root / 'scripts/surfaceproperties_manifest.txt').unlink()
        output = self.mass_qc()
        self.assertIn('using default density 2000', output)
        _, total = self.mass_output()
        self.assertAlmostEqual(total, 10 ** 3 / 6 * .0254 ** 3 * 2000, places=4)

    def test_invalid_automass_materials_fail_before_existing_outputs_are_replaced(self):
        self.mass_fixture()
        self.mass_qc(options='$mass 20')
        old_mdl = self.mdl('mass')
        phy_path = self.root / 'models/mass.phy'
        old_phy = phy_path.read_bytes()
        for definitions, surface, diagnostic in [
            ('default { density nan }', 'default', 'invalid density'),
            ('default { density -10 }', 'default', 'invalid density'),
            ('default { density 1000 thickness inf }', 'default', 'invalid thickness'),
            ('first { base second } second { base first }', 'first', 'inheritance cycle'),
        ]:
            self.mass_surfaces(definitions)
            output = self.mass_qc(surface=surface, success=False)
            self.assertIn(diagnostic, output)
            self.assertEqual(self.mdl('mass'), old_mdl)
            self.assertEqual(phy_path.read_bytes(), old_phy)
        # Explicit mass never needs surface physics data, so unavailable or bad
        # density definitions cannot break its existing behavior.
        self.mass_qc(options='$mass 20')
        _, total = self.mass_output()
        self.assertEqual(total, 20)
