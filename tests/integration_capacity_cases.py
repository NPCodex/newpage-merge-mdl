"""Fixed five-compiler capacity acceptance fixtures (all self-authored)."""
from array import array
import json
import struct


def large_morph_fixture(root, counts):
    """Disconnected nondegenerate triangles, with an exact moved vertex count."""
    binary = bytearray()
    views, accessors, primitives = [], [], []
    def add(values, kind, count):
        binary.extend(b'\0' * (-len(binary) % 4))
        offset = len(binary)
        binary.extend(values.tobytes())
        views.append(dict(buffer=0, byteOffset=offset, byteLength=len(binary)-offset))
        accessors.append(dict(bufferView=len(views)-1, componentType=5125 if values.typecode=='I' else 5126,
                              count=count, type=kind))
        return len(accessors)-1
    base = 0
    for material, count in enumerate(counts):
        positions = array('f')
        for i in range(count):
            triangle, corner = divmod(base+i, 3)
            positions.extend((2*(triangle%512)+(corner==1), 2*(triangle//512)+(corner==2), 0))
        # Primitive boundaries need their own valid triangles, independent of
        # the material's position in the source's combined vertex array.
        indices = array('I', range(count-count%3))
        for i in range(count-count%3, count):
            indices.extend((i-2, i-1, i))
        p = add(positions, 'VEC3', count)
        n = add(array('f', (0,0,1))*count, 'VEC3', count)
        delta = add(array('f', (0,0,.25))*count, 'VEC3', count)
        ix = add(indices, 'SCALAR', len(indices))
        primitives.append(dict(attributes=dict(POSITION=p,NORMAL=n), indices=ix,
                               material=material, targets=[dict(POSITION=delta)]))
        base += count
    doc = dict(asset=dict(version='2.0'), scene=0, scenes=[dict(nodes=[0])],
               nodes=[dict(name='mesh',mesh=0)], materials=[dict(name=f'mat{i}') for i in range(len(counts))],
               meshes=[dict(name='capacity',extras=dict(targetNames=['Move']),primitives=primitives)],
               buffers=[dict(uri='capacity.bin',byteLength=len(binary))],bufferViews=views,accessors=accessors)
    (root/'capacity.bin').write_bytes(binary)
    (root/'capacity.gltf').write_text(json.dumps(doc))


class IntegrationCapacityCases:
    def capacity_output(self, expected, lods, minimum_meshes):
        data=self.mdl('capacity')
        body=struct.unpack_from('<i',data,236)[0]
        model=body+struct.unpack_from('<i',data,body+12)[0]
        count,offset=struct.unpack_from('<2i',data,model+72)
        self.assertGreaterEqual(count,minimum_meshes)
        self.assertEqual(struct.unpack_from('<i',data,model+80)[0],expected)
        moved=0
        for i in range(count):
            mesh=model+offset+i*116
            vertices=struct.unpack_from('<i',data,mesh+8)[0]
            self.assertLessEqual(vertices,65536)
            nf,fo=struct.unpack_from('<2i',data,mesh+16)
            self.assertEqual(nf,1)
            flex=mesh+fo
            nv,vo=struct.unpack_from('<2i',data,flex+20)
            self.assertEqual(nv,vertices)
            ids=set()
            for j in range(nv):
                at=flex+vo+j*16
                index=struct.unpack_from('<H',data,at)[0]
                self.assertLess(index,vertices)
                ids.add(index)
                self.assertAlmostEqual(struct.unpack_from('<3e',data,at+4)[2],.25,places=5)
            self.assertEqual(len(ids),vertices)
            moved+=nv
        self.assertEqual(moved,expected)
        for suffix in ('dx80','dx90'):
            vtx=(self.root/f'models/capacity.{suffix}.vtx').read_bytes()
            bp=struct.unpack_from('<i',vtx,32)[0]
            mdl=bp+struct.unpack_from('<i',vtx,bp+4)[0]
            self.assertEqual(struct.unpack_from('<i',vtx,mdl)[0],lods)

    def capacity_compile(self,counts,lods=1):
        large_morph_fixture(self.root,counts)
        self.scene_qc('$modelname capacity\n$UpAxis z gltf\n$origin 0 0 0 -90\n'
                      '$body m capacity.gltf { flex Move\nflexcontroller test strength\n%Move = strength\n}\n'+
                      ('$lod 20 { }\n' if lods==2 else ''))
        expected_faces=sum(count//3+count%3 for count in counts)
        for lod in range(lods):
            for suffix in ('dx80','dx90'):
                self.assertEqual(sum(self.vtx_triangles('capacity',suffix,lod=lod).values()),expected_faces)

    def test_integration_flex_capacity_32769_moving_vertices(self):
        self.capacity_compile([32769])
        self.capacity_output(32769,1,1)

    def test_integration_flex_capacity_65537_materials_and_lod(self):
        self.capacity_compile([32769,32768],2)
        self.capacity_output(65537,2,2)
        self.assertEqual(struct.unpack_from('<i',self.mdl('capacity'),204)[0],2)

    def test_integration_flex_capacity_511451_split_mesh_vertices(self):
        self.capacity_compile([511451])
        self.capacity_output(511451,1,8)
