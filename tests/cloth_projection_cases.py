"""Render-to-proxy projection tested through final VVD skinning and FE controls."""
import re
import struct
from cloth_cases import cloth_dmx, render_smd, fe_resource
from cloth_advanced_cases import fe_names


def repeat_proxy(*, volume=False):
    text = cloth_dmx()
    base = [(-8, 0, 24), (8, 0, 24), (-8, 0, 16), (8, 0, 16), (-8, 0, 8), (8, 0, 8)]
    points = [(x, -2 if volume else y, z) for x, y, z in base] + [(x if volume else x+100, 2 if volume else y, z) for x, y, z in base]
    def replace(name, kind, values):
        nonlocal text
        text = re.sub(r'"'+name+r'" "'+kind+r'_array" \[[^\]]+\]', '"'+name+'" "'+kind+'_array" [ '+', '.join('"'+str(v)+'"' for v in values)+' ]', text)
    replace('positions', 'vector3', [' '.join(map(str,p)) for p in points])
    for name in ('positionsIndices', 'cloth_enableIndices'): replace(name, 'int', range(12))
    replace('jointWeights', 'float', [1]*12)
    replace('jointIndices', 'int', [0,0,1,1,1,1]*2)
    replace('cloth_enable', 'float', [0,0,1,1,1,1]*2)
    faces = ([2,3,1,0,-1,4,5,3,2,-1] if volume else [0,1,3,2,-1,2,3,5,4,-1]) + [6,7,9,8,-1,8,9,11,10,-1]
    replace('faces', 'int', faces)
    return text


class ClothProjectionCases:
    def projected_vertices(self):
        data = self.mdl('fecloth')
        count, at = struct.unpack_from('<2i', data, 156)
        names = []
        for i in range(count):
            bone = at+i*216
            name = bone+struct.unpack_from('<i', data, bone)[0]
            names.append(data[name:data.index(b'\0', name)].decode())
        vvd = (self.root/'models/fecloth.vvd').read_bytes()
        count = struct.unpack_from('<i', vvd, 16)[0]
        at = struct.unpack_from('<i', vvd, 56)[0]
        out = []
        for i in range(count):
            row = at+i*48
            n = vvd[row+15]
            weights = struct.unpack_from('<3f', vvd, row)
            out.append((struct.unpack_from('<3f', vvd, row+16), {names[vvd[row+12+j]]: weights[j] for j in range(n)}))
        return names, out

    def test_cloth_projection_generates_independent_vertex_controls(self):
        self.cloth_model(settings='project_render true projection_root root')
        names, vertices = self.projected_vertices()
        self.assertNotIn('$cloth_root', names)
        expected = {(-8,0,16): '$cloth_v2', (8,0,16): '$cloth_v3', (-8,0,8): '$cloth_v4', (8,0,8): '$cloth_v5'}
        for position, weights in vertices:
            if position in expected: self.assertEqual(weights, {expected[position]: 1})
            else: self.assertEqual(weights, {'root': 1})
        data = self.mdl('fecloth'); _, array = fe_resource(data)
        self.assertEqual(array(344,16)[1],4)
        self.assertTrue(set(expected.values()) <= set(fe_names(data,array)))

    def test_cloth_projection_unskinned_proxy_creates_root(self):
        proxy = cloth_dmx()
        proxy = re.sub(r'"jointCount" "int" "1"', '', proxy)
        for name, kind in (('jointIndices','int'),('jointWeights','float')):
            proxy = re.sub(r'"'+name+r'" "'+kind+r'_array" \[[^\]]+\]', '', proxy)
        self.cloth_model(proxy=proxy, settings='projection true')
        names, vertices = self.projected_vertices()
        self.assertIn('$cloth_root', names)
        self.assertTrue(any('$cloth_root' in w for _,w in vertices))
        self.assertTrue(any('$cloth_v2' in w for _,w in vertices))
        empty = proxy.replace('"cloth_enableIndices"', '"jointCount" "int" "0" "jointIndices" "int_array" [] "jointWeights" "float_array" [] "cloth_enableIndices"')
        self.cloth_model(proxy=empty, settings='projection true')
        self.assertIn('$cloth_root', self.projected_vertices()[0])

    def test_cloth_projection_envelope_misses_keep_original_weights(self):
        mesh = re.sub(r'(?m)^([01]) (-?8) 0 (8|16|24) 0 -1 0', r'\1 \2 10 \3 0 -1 0', render_smd())
        self.cloth_model(mesh=mesh, settings='projection true projection_envelope 1')
        _, vertices = self.projected_vertices()
        self.assertTrue(all(set(w) <= {'root','flap'} for _,w in vertices))
        self.cloth_model(mesh=mesh, settings='projection true projection_envelope 11')
        _, vertices = self.projected_vertices()
        self.assertTrue(any(any(n.startswith('$cloth_v') for n in w) for _,w in vertices))

    def test_cloth_projection_connected_island_filter(self):
        mesh = re.sub(r'(?m)^([01]) (-?8) 0 (8|16|24) 0 -1 0', lambda m:f'{m[1]} {int(m[2])+100} 0 {m[3]} 0 -1 0',render_smd())
        proxy = repeat_proxy()
        self.cloth_model(mesh=mesh, proxy=proxy, settings='projection true projection_island 1 projection_envelope 1')
        _, vertices = self.projected_vertices()
        generated = {n for _,w in vertices for n in w if n.startswith('$cloth_v')}
        self.assertEqual(generated, {'$cloth_v8','$cloth_v9','$cloth_v10','$cloth_v11'})
        self.cloth_model(mesh=mesh, proxy=proxy, settings='projection true projection_island 0 projection_envelope 1')
        _, vertices = self.projected_vertices()
        self.assertTrue(all(set(w) <= {'root','flap'} for _,w in vertices))

    def test_cloth_projection_two_sided_volume_uses_both_surfaces(self):
        mesh = render_smd().split('triangles')[0]+'triangles\ndebug/debugwhite\n'+''.join(f'1 {x} 0 {z} 0 -1 0 0 0\n' for x,z in ((0,12),(1,12),(0,11)))+'end\n'
        proxy = repeat_proxy(volume=True)
        self.cloth_model(mesh=mesh, proxy=proxy, settings='projection true projection_two_sided true')
        _, vertices = self.projected_vertices()
        for _,weights in vertices:
            ids = [int(name[len('$cloth_v'):]) for name in weights]
            self.assertTrue(any(i<6 for i in ids) and any(i>=6 for i in ids))
            self.assertAlmostEqual(sum(weights.values()),1)
            self.assertAlmostEqual(sum(weight for name,weight in weights.items() if int(name[len('$cloth_v'):])<6),.5,places=5)
        self.cloth_model(mesh=mesh, proxy=proxy, settings='projection true projection_two_sided false')
        _, vertices = self.projected_vertices()
        for _,weights in vertices:
            ids = [int(name[len('$cloth_v'):]) for name in weights]
            self.assertTrue(all(i<6 for i in ids) or all(i>=6 for i in ids))

    def test_cloth_projection_bone_limit_applies_after_unused_bone_collapse(self):
        mesh = render_smd().replace('1 "flap" 0', '1 "flap" 0\n'+'\n'.join(f'{i} "unused{i}" 0' for i in range(2,300)))
        mesh = mesh.replace('1 0 0 0 0 0 0\nend', '1 0 0 0 0 0 0\n'+'\n'.join(f'{i} 0 0 0 0 0 0' for i in range(2,300))+'\nend')
        self.cloth_model(mesh=mesh,settings='projection true')
        names,_ = self.projected_vertices()
        self.assertLess(len(names),256)
        result = self.cloth_model(mesh=mesh,settings='projection true',transform='$bonecullmethod none\n',success=False)
        self.assertIn('too many bones',result)
