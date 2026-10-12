"""Native quad patch fixtures and independent extended-VTX topology checks."""
import math
import struct
import subprocess
import sys
from pathlib import Path


def grid_quads(n=3):
    points=[(x*8,y*8,0) for y in range(n+1) for x in range(n+1)]
    quads=[]
    for y in range(n):
        for x in range(n):
            a=y*(n+1)+x;quads.append((a,a+1,a+n+2,a+n+1))
    return points,quads


def subd_dmx(points,faces,*,auto=False,seams=False,normals=None,skin=False,morph=False):
    def uid(n):return f'dd190000-0000-0000-0000-{n:012x}'
    def ref(n):return f'"element" "{uid(n)}"'
    def elem(n,kind,name,body):return f'"{kind}" {{ "id" "elementid" "{uid(n)}" "name" "string" "{name}" {body} }}\n'
    def arr(name,kind,values):return f'"{name}" "{kind}_array" [ '+', '.join(f'"{v}"' for v in values)+' ]\n'
    corners=[v for f in faces for v in f];polygon=[];at=0
    for f in faces:polygon.extend(range(at,at+len(f)));polygon.append(-1);at+=len(f)
    out='<!-- dmx encoding keyvalues2 1 format model 18 -->\n'
    out+=elem(1,'DmElement','patches',f'"model" {ref(2)} "skeleton" {ref(2)} "subdivisionSurface" "bool" "{int(auto)}"')
    joints=', '+ref(20) if skin else '';transforms=', '+ref(21) if skin else ''
    out+=elem(2,'DmeModel','model',f'"upAxis" "string" "Z" "transform" {ref(3)} "children" "element_array" [ {ref(4)}, {ref(6)} ] "jointList" "element_array" [ {ref(4)}{joints} ] "jointTransforms" "element_array" [ {ref(5)}{transforms} ]')
    for n,name in [(3,'model'),(5,'root'),(7,'mesh')]:out+=elem(n,'DmeTransform',name,'"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    out+=elem(4,'DmeJoint','root',f'"transform" {ref(5)} "children" "element_array" [ {ref(20) if skin else ""} ]')
    if skin:
        out+=elem(20,'DmeJoint','extra',f'"transform" {ref(21)} "children" "element_array" []')
        out+=elem(21,'DmeTransform','extra','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    out+=elem(6,'DmeDag','mesh',f'"transform" {ref(7)} "shape" {ref(8)}')
    out+=elem(8,'DmeMesh','mesh',f'"currentState" {ref(9)} "baseStates" "element_array" [ {ref(9)} ] "faceSets" "element_array" [ {ref(10)} ]'+(f' "deltaStates" "element_array" [ {ref(30)} ]' if morph else ''))
    body=arr('vertexFormat','string',['positions','normals','textureCoordinates','jointWeights','jointIndices'])
    body+=arr('positions','vector3',[' '.join(map(str,p)) for p in points])+arr('positionsIndices','int',corners)
    if normals is None:normals=[(0,0,1)]*len(points)
    body+=arr('normals','vector3',[' '.join(map(str,p)) for p in normals])+arr('normalsIndices','int',corners)
    uvs=[(points[v][0]/64+i/100 if seams else points[v][0]/64,points[v][1]/64) for i,v in enumerate(corners)]
    body+=arr('textureCoordinates','vector2',[f'{u} {v}' for u,v in uvs])+arr('textureCoordinatesIndices','int',range(len(corners)))
    if skin:
        body+='"jointCount" "int" "2"\n'+arr('jointWeights','float',[w for p in points for w in [1-p[0]/8,p[0]/8]])+arr('jointIndices','int',[0,1]*len(points))
    else:body+='"jointCount" "int" "1"\n'+arr('jointWeights','float',[1]*len(points))+arr('jointIndices','int',[0]*len(points))
    out+=elem(9,'DmeVertexData','bind',body)
    out+=elem(10,'DmeFaceSet','surface',f'"material" {ref(11)} '+arr('faces','int',polygon))
    out+=elem(11,'DmeMaterial','surface','"mtlName" "string" "debug/debugwhite"')
    if morph:out+=elem(30,'DmeVertexDeltaData','raise',arr('vertexFormat','string',['positions'])+arr('positions','vector3',['0 0 2']*len(points))+arr('positionsIndices','int',range(len(points))))
    return out


def decode_subd(vtx):
    """Return strip-group records; offsets are checked without compiler helpers."""
    groups=[]
    def read(fmt,at):
        if at<0 or at+struct.calcsize(fmt)>len(vtx):raise AssertionError('VTX range')
        return struct.unpack_from(fmt,vtx,at)
    bodies,body_at=read('<2i',28)
    for b in range(bodies):
        bp=body_at+b*8;models,mo=read('<2i',bp)
        for m in range(models):
            model=bp+mo+m*8;lods,lo=read('<2i',model)
            for l in range(lods):
                lod=model+lo+l*12;meshes,me=read('<2i',lod)
                for mi in range(meshes):
                    mesh=lod+me+mi*9;count,go=read('<2i',mesh)
                    for g in range(count):
                        sg=mesh+go+g*33;nv,vo,ni,io,ns,so,flags,nt,to=read('<6iB2i',sg)
                        original=[read('<H',sg+vo+v*9+4)[0] for v in range(nv)]
                        indices=read('<'+'H'*ni,sg+io);topology=read('<'+'H'*nt,sg+to)
                        patches=[]
                        for st in range(ns):
                            strip=sg+so+st*35;count,first,verts,base,bones,sflags,bc,bo,tc,tf=read('<4ihB4i',strip)
                            assert sflags in (2,4) and count%4==0 and first+count<=ni
                            assert base==0 and verts==nv and tf+tc<=nt
                            cursor=tf
                            for i in range(first,first+count,4):
                                assert cursor+60<=tf+tc
                                head=topology[cursor:cursor+60];ring_count=sum(head[:4]);end=cursor+60+ring_count
                                assert end<=tf+tc
                                ring=topology[cursor+60:end];corners=indices[i:i+4]
                                assert max(corners)<nv and max(ring)<nv
                                patches.append((sflags,corners,head,ring));cursor=end
                            assert cursor==tf+tc
                        assert len(patches)*4==ni
                        groups.append(dict(lod=l,mesh=mi,vertices=original,patches=patches,flags=flags))
    return groups


class SubdCases:
    def subd_compile(self,points,quads,*,name='subd',prefix='$subd native\n',options='',tail='',auto=False,seams=False,normals=None,success=True):
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        self.write('patch.dmx',subd_dmx(points,quads,auto=auto,seams=seams,normals=normals))
        return self.scene_qc(f'$modelname {name}\n'+prefix+f'$model surface patch.dmx {options}\n'+tail,success=success)

    def subd_read(self,name='subd'):
        data=self.mdl(name);self.assertTrue(struct.unpack_from('<i',data,152)[0]&(1<<19))
        groups=decode_subd((self.root/f'models/{name}.dx90.vtx').read_bytes())
        vvd=(self.root/f'models/{name}.vvd').read_bytes();count=struct.unpack_from('<i',vvd,16)[0];at=struct.unpack_from('<i',vvd,56)[0]
        positions=[tuple(round(x,4) for x in struct.unpack_from('<3f',vvd,at+i*48+16)) for i in range(count)]
        # These fixtures have a single model/material, so mesh-relative == VVD-relative.
        for group in groups:
            verts=group['vertices']
            for flags,corners,head,rings in group['patches']:
                offset=0
                for k in range(4):
                    ring=rings[offset:offset+head[k]];offset+=head[k]
                    p=positions[verts[corners[k]]]
                    self.assertEqual(positions[verts[ring[0]]],p)
                    self.assertEqual(len(ring),2*head[8+k]+(0 if head[16+k] else 1))
                    self.assertLess(head[4+k],len(ring));self.assertLess(head[12+k],len(ring))
                    for uv in (44+k,48+k,52+k,56+k):
                        self.assertLess(head[uv],count);self.assertEqual(positions[head[uv]],p)
                if flags==2:
                    self.assertEqual(head[8:12],(4,)*4);self.assertEqual(head[16:24],(0,)*8)
        return groups

    def subd_baked_read(self,name='subd'):
        data=self.mdl(name);self.assertFalse(struct.unpack_from('<i',data,152)[0]&(1<<19))
        vtx=(self.root/f'models/{name}.dx90.vtx').read_bytes();triangles=0
        def read(fmt,at):return struct.unpack_from(fmt,vtx,at)
        bodies,body_at=read('<2i',28)
        for b in range(bodies):
            bp=body_at+b*8;models,mo=read('<2i',bp)
            for m in range(models):
                model=bp+mo+m*8;lods,lo=read('<2i',model)
                for l in range(lods):
                    lod=model+lo+l*12;meshes,me=read('<2i',lod)
                    for mi in range(meshes):
                        mesh=lod+me+mi*9;count,go=read('<2i',mesh)
                        for g in range(count):
                            sg=mesh+go+g*33;nv,vo,ni,io,ns,so,flags,nt,to=read('<6iB2i',sg)
                            self.assertEqual(nt,0);self.assertEqual(ni%3,0);triangles+=ni//3
                            for st in range(ns):self.assertEqual(read('<B',sg+so+st*35+18)[0],1)
        vvd=(self.root/f'models/{name}.vvd').read_bytes();count=struct.unpack_from('<i',vvd,16)[0];at=struct.unpack_from('<i',vvd,56)[0]
        vertices=[]
        for i in range(count):
            v=at+i*48;weights=struct.unpack_from('<3f',vvd,v);bones=struct.unpack_from('<3B',vvd,v+12);n=vvd[v+15]
            vertices.append(dict(position=struct.unpack_from('<3f',vvd,v+16),normal=struct.unpack_from('<3f',vvd,v+28),uv=struct.unpack_from('<2f',vvd,v+40),weights=dict(zip(bones[:n],weights[:n]))))
        return dict(triangles=triangles,vertices=vertices)

    def test_subd_default_and_levels_bake_smoothed_triangles(self):
        for prefix,triangles in [('$subd\n',32),('$subd levels 1\n',8),('$subd levels 3\n',128)]:
            self.subd_compile(*grid_quads(1),prefix=prefix)
            baked=self.subd_baked_read();self.assertEqual(baked['triangles'],triangles)
            self.assertTrue(any(all(abs(a-b)<1e-5 for a,b in zip(v['position'],(4,4,0))) for v in baked['vertices']))
            self.assertFalse(any(v['position']==(0,0,0) for v in baked['vertices']))
        self.subd_compile(*grid_quads(1),prefix='$subd levels 1\n')
        positions=[v['position'] for v in self.subd_baked_read()['vertices']]
        self.assertIn((1,1,0),positions);self.assertIn((4,0,0),positions)

    def test_subd_baked_cube_has_catmull_clark_corner_positions(self):
        points=[(-8,-8,-8),(8,-8,-8),(8,8,-8),(-8,8,-8),(-8,-8,8),(8,-8,8),(8,8,8),(-8,8,8)]
        quads=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)]
        self.subd_compile(points,quads,prefix='$subd levels 1\n')
        baked=self.subd_baked_read();self.assertEqual(baked['triangles'],48)
        self.assertTrue(any(all(abs(abs(x)-40/9)<1e-4 for x in v['position']) for v in baked['vertices']))
        self.assertFalse(any(all(abs(x)==8 for x in v['position']) for v in baked['vertices']))

    def test_subd_bake_preserves_uv_seams(self):
        self.subd_compile(*grid_quads(2),prefix='$subd levels 1\n',seams=True)
        baked=self.subd_baked_read();self.assertEqual(baked['triangles'],32)
        grouped={}
        for v in baked['vertices']:grouped.setdefault(tuple(round(x,5) for x in v['position']),set()).add(tuple(round(x,5) for x in v['uv']))
        self.assertTrue(any(len(uvs)>1 for uvs in grouped.values()))

    def test_subd_bake_keeps_shared_geometry_across_material_boundaries(self):
        points=[(0,0,0),(8,0,0),(16,0,0),(0,8,0),(8,8,0),(16,8,0)]
        quads=[(0,1,4,3),(1,2,5,4)]
        self.subd_compile(points,quads,name='joined',prefix='$subd levels 1\n')
        joined=self.subd_baked_read('joined')
        text=subd_dmx(points,quads)
        uid=lambda n:f'dd190000-0000-0000-0000-{n:012x}'
        ref=lambda n:f'"element" "{uid(n)}"'
        text=text.replace('"faceSets" "element_array" [ '+ref(10)+' ]',
                          '"faceSets" "element_array" [ '+ref(10)+', '+ref(12)+' ]')
        text=text.replace('"faces" "int_array" [ "0", "1", "2", "3", "-1", "4", "5", "6", "7", "-1" ]',
                          '"faces" "int_array" [ "0", "1", "2", "3", "-1" ]')
        text+=f'"DmeFaceSet" {{ "id" "elementid" "{uid(12)}" "name" "string" "second" "material" {ref(13)} "faces" "int_array" [ "4", "5", "6", "7", "-1" ] }}\n'
        text+=f'"DmeMaterial" {{ "id" "elementid" "{uid(13)}" "name" "string" "second" "mtlName" "string" "debug/subd_second" }}\n'
        self.write('split.dmx',text)
        self.scene_qc('$modelname split\n$subd levels 1\n$model surface split.dmx\n')
        split=self.subd_baked_read('split')
        self.assertEqual(joined['triangles'],16);self.assertEqual(split['triangles'],16)
        # A material change must not turn the shared edge into two independent
        # subdivision boundaries, which shrink its endpoints to x=7 and x=9.
        positions=lambda mesh:{tuple(round(x,5) for x in v['position']) for v in mesh['vertices']}
        self.assertEqual(positions(split),positions(joined))
        for endpoint in [(8,0,0),(8,8,0)]:self.assertIn(endpoint,positions(split))
        attributes=lambda mesh:{tuple(round(x,5) for field in ['position','normal','uv'] for x in v[field]) for v in mesh['vertices']}
        self.assertEqual(attributes(split),attributes(joined))

    def test_subd_bake_interpolates_skin_weights_and_morph_positions(self):
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        self.write('patch.dmx',subd_dmx(*grid_quads(1),skin=True,morph=True))
        self.scene_qc('$modelname subd\n$subd levels 1\n$bonemerge extra\n$model surface patch.dmx { flex raise\nflexcontroller test amount\n%raise = amount\n}\n')
        baked=self.subd_baked_read();self.assertEqual(baked['triangles'],8)
        center=next(v for v in baked['vertices'] if all(abs(a-b)<1e-5 for a,b in zip(v['position'],(4,4,0))))
        self.assertEqual(len(center['weights']),2)
        for weight in center['weights'].values():self.assertAlmostEqual(weight,.5,places=5)
        for vertex in baked['vertices']:self.assertAlmostEqual(sum(vertex['weights'].values()),1,places=5)
        d,flex=self.first_mesh_flex('subd');self.assertEqual(len(flex),len(baked['vertices']))
        for at in flex:
            self.assertEqual(struct.unpack_from('<3e',d,at+4),(0,0,2))

    def test_subd_bake_rejects_invalid_modes_topology_and_growth(self):
        points,quads=grid_quads(1);self.subd_compile(points,quads,prefix='$subd\n')
        paths=list((self.root/'models').glob('subd.*'));before={p:p.read_bytes() for p in paths}
        for prefix in ['$subd levels 0\n','$subd levels 4\n','$subd native levels 1\n']:
            self.subd_compile(points,quads,prefix=prefix,success=False)
            self.assertEqual(before,{p:p.read_bytes() for p in paths})
        self.subd_compile(points,[(0,1,2)],prefix='$subd\n',success=False)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})
        self.assertIn('262144',self.subd_compile(*grid_quads(65),prefix='$subd levels 3\n',success=False))
        self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_subd_single_quad_emits_boundary_patch(self):
        self.subd_compile(*grid_quads(1));groups=self.subd_read();self.assertEqual(len(groups),1)
        flags,corners,head,ring=groups[0]['patches'][0]
        self.assertEqual(flags,4);self.assertEqual(head[:4],(4,)*4)
        self.assertEqual(head[8:12],(2,)*4);self.assertEqual(head[16:24],(1,)*8)
        self.assertEqual(head[28:32],(16383,)*4);self.assertEqual(len(ring),16)

    def test_subd_grid_has_regular_and_extraordinary_strips(self):
        self.subd_compile(*grid_quads(3));groups=self.subd_read()
        patches=groups[0]['patches'];self.assertEqual(len(patches),9)
        self.assertEqual(sum(p[0]==2 for p in patches),1)
        self.assertEqual(sum(p[0]==4 for p in patches),8)

    def test_subd_renderer_patch_capacity_preserves_existing_outputs(self):
        points,quads=grid_quads(91)
        self.subd_compile(points,quads[:8192])
        groups=decode_subd((self.root/'models/subd.dx90.vtx').read_bytes())
        self.assertEqual(sum(len(g['patches']) for g in groups),8192)
        paths=list((self.root/'models').glob('subd.*'))
        before={p:p.read_bytes() for p in paths}
        text=self.subd_compile(points,quads[:8193],success=False)
        self.assertIn('renderer capacity of 8192 SubD patches',text)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_subd_closed_cube_preserves_extraordinary_valence(self):
        points=[(-8,-8,-8),(8,-8,-8),(8,8,-8),(-8,8,-8),(-8,-8,8),(8,-8,8),(8,8,8),(-8,8,8)]
        quads=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(3,7,6,2),(0,4,7,3),(1,2,6,5)]
        normals=[tuple(v/math.sqrt(192) for v in p) for p in points]
        self.subd_compile(points,quads,normals=normals);patches=self.subd_read()[0]['patches']
        self.assertEqual(len(patches),6)
        for flags,_,head,ring in patches:
            self.assertEqual(flags,4);self.assertEqual(head[:4],(7,)*4)
            self.assertEqual(head[8:12],(3,)*4);self.assertEqual(head[16:24],(0,)*8)

    def test_subd_uv_seams_keep_shared_geometric_neighbors(self):
        self.subd_compile(*grid_quads(3),seams=True)
        groups=self.subd_read();self.assertGreater(len(groups[0]['vertices']),16)
        self.assertEqual(sum(p[0]==2 for p in groups[0]['patches']),1)
        self.assertTrue(any(p[2][44:48]!=p[2][56:60] for p in groups[0]['patches']))

    def test_subd_authored_normal_crease_splits_vertex_sectors(self):
        points=[(0,0,0),(8,0,0),(8,8,0),(0,8,0),
                (8,0,0),(16,0,8),(16,8,8),(8,8,0)]
        normals=[(0,0,1)]*4+[(-math.sqrt(.5),0,math.sqrt(.5))]*4
        self.subd_compile(points,[(0,1,2,3),(4,5,6,7)],normals=normals)
        patches=self.subd_read()[0]['patches'];self.assertEqual(len(patches),2)
        for _,_,head,_ in patches:
            self.assertEqual(head[16:24],(1,)*8)
            self.assertEqual(head[8:12],(2,)*4)

    def test_subd_lod_uv_references_follow_sorted_vvd(self):
        points,quads=grid_quads(3)
        self.write('low.dmx',subd_dmx(points,[quads[-1]],seams=True))
        self.subd_compile(points,quads,seams=True,tail='$lod 20 { replacemodel patch.dmx low.dmx }\n')
        groups=self.subd_read();self.assertEqual([len(g['patches']) for g in groups],[9,1])

    def test_subd_model_option_and_dmx_attribute_enable_baked_triangles(self):
        for options,auto in [('subd',False),('',True)]:
            self.subd_compile(*grid_quads(1),prefix='',options=options,auto=auto)
            self.assertEqual(self.subd_baked_read()['triangles'],32)

    def test_subd_rejects_triangle_and_nonmanifold_preserving_outputs(self):
        points,quads=grid_quads(1);self.subd_compile(points,quads)
        paths=list((self.root/'models').glob('subd.*'));before={p:p.read_bytes() for p in paths}
        for bad in [[(0,1,2)],[quads[0],quads[0]],[(0,1,3,2),(0,4,6,5)]]:
            extra=points+[(16,0,0),(16,8,0),(24,8,0)]
            text=self.subd_compile(extra,bad,success=False);self.assertIn('SubD:',text)
            self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_subd_reverse_preserves_valid_quad_topology(self):
        self.subd_compile(*grid_quads(3),options='reverse')
        self.assertEqual(sum(len(g['patches']) for g in self.subd_read()),9)

    def test_subd_decompiler_preserves_control_quads_on_roundtrip(self):
        self.subd_decompiler_roundtrip('keyvalues2')

    def test_subd_decompiler_binary_dmx_preserves_control_quads_on_roundtrip(self):
        self.subd_decompiler_roundtrip('binary')

    def subd_decompiler_roundtrip(self,encoding):
        self.subd_compile(*grid_quads(3),seams=True)
        before=self.subd_read()
        def control_points():
            data=(self.root/'models/subd.vvd').read_bytes()
            count=struct.unpack_from('<i',data,16)[0];at=struct.unpack_from('<i',data,56)[0]
            # Vertex order can change across import; compare position, normal
            # and corner UV together so seams cannot disappear unnoticed.
            return sorted(set(tuple(round(v,4) for v in struct.unpack_from('<8f',data,at+i*48+16))
                              for i in range(count)))
        authored=control_points()
        compiler=Path(sys.modules[type(self).__module__].COMPILER)
        decompiler=compiler.with_name('NewPageMergeMDL-Decompiler'+compiler.suffix)
        output=self.root/'decompiled'
        result=subprocess.run([str(decompiler),str(self.root/'models/subd.mdl'),'-pulseqc',
            '-dmxencoding',encoding,'-outdir',str(output)],capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        meshes=list(output.rglob('meshes/*.dmx'));self.assertTrue(meshes)
        self.assertTrue(any(b'subdivisionSurface' in p.read_bytes() for p in meshes))
        qc=next(output.rglob('*.pulseqc'))
        qc.write_text('$subd native\n'+qc.read_text())
        result=subprocess.run([str(compiler),str(qc),'-game',str(self.root)],capture_output=True,text=True,errors='replace')
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        after=self.subd_read()
        self.assertEqual(control_points(),authored)
        self.assertEqual([len(g['patches']) for g in before],[len(g['patches']) for g in after])
        self.assertEqual(sum(p[0]==2 for g in after for p in g['patches']),1)
