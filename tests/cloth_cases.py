"""Self-authored FE proxy fixtures and independent resource checks."""
import struct
import math


def cloth_dmx(*, plane=False, triangles=False):
    def uid(n): return f'cc100000-0000-0000-0000-{n:012x}'
    def ref(n): return f'"element" "{uid(n)}"'
    def elem(n, cls, name, body):
        return f'"{cls}" {{ "id" "elementid" "{uid(n)}" "name" "string" "{name}" {body} }}\n'
    def arr(name, kind, values):
        return f'"{name}" "{kind}_array" [ '+', '.join(f'"{v}"' for v in values)+' ]\n'
    points = [(-8,0,24),(8,0,24),(-8,0,16),(8,0,16),(-8,0,8),(8,0,8)]
    faces = [0,1,3,2,-1,2,3,5,4,-1]
    if triangles: faces=[0,1,3,-1,0,3,2,-1,2,3,5,-1,2,5,4,-1]
    if plane:
        points=[(-20,-4,0),(20,-4,0),(20,-4,32),(-20,-4,32)]
        faces=[3,2,1,0,-1]
    count=len(points)
    result='<!-- dmx encoding keyvalues2 1 format model 15 -->\n'
    result+=elem(1,'DmElement','cloth',f'"model" {ref(2)} "skeleton" {ref(2)}')
    result+=elem(2,'DmeModel','cloth',f'"upAxis" "string" "Z" "transform" {ref(3)} "children" "element_array" [ {ref(4)}, {ref(6)} ] "jointList" "element_array" [ {ref(4)}, {ref(8)} ] "jointTransforms" "element_array" [ {ref(5)}, {ref(9)} ]')
    for n,name in [(3,'cloth'),(5,'root'),(7,'proxy'),(9,'flap')]:
        result+=elem(n,'DmeTransform',name,'"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    result+=elem(4,'DmeJoint','root',f'"transform" {ref(5)} "children" "element_array" [ {ref(8)} ]')
    result+=elem(8,'DmeJoint','flap',f'"transform" {ref(9)} "children" "element_array" []')
    result+=elem(6,'DmeDag','proxy',f'"transform" {ref(7)} "shape" {ref(10)}')
    result+=elem(10,'DmeMesh','proxy',f'"currentState" {ref(11)} "baseStates" "element_array" [ {ref(11)} ] "faceSets" "element_array" [ {ref(12)} ]')
    body=arr('vertexFormat','string',['positions','normals','textureCoordinates','jointWeights','jointIndices']+([] if plane else ['cloth_enable']))
    body+=arr('positions','vector3',[' '.join(map(str,p)) for p in points])+arr('positionsIndices','int',range(count))
    body+=arr('normals','vector3',['0 -1 0'])+arr('normalsIndices','int',[0]*count)
    body+=arr('textureCoordinates','vector2',['0 0']*count)+arr('textureCoordinatesIndices','int',range(count))
    body+='"jointCount" "int" "1"\n'+arr('jointWeights','float',[1]*count)+arr('jointIndices','int',[0]*count if plane else [0,0,1,1,1,1])
    if not plane:body+=arr('cloth_enable','float',[0,0,1,1,1,1])+arr('cloth_enableIndices','int',range(count))
    result+=elem(11,'DmeVertexData','bind',body)
    result+=elem(12,'DmeFaceSet','cloth',f'"material" {ref(13)} '+arr('faces','int',faces))
    result+=elem(13,'DmeMaterial','cloth','"mtlName" "string" "debug/debugwhite"')
    return result


def render_smd():
    rows=['version 1','nodes','0 "root" -1','1 "flap" 0','end','skeleton','time 0','0 0 0 0 0 0 0','1 0 0 0 0 0 0','end','triangles']
    points=[(-8,0,24),(8,0,24),(-8,0,16),(8,0,16),(-8,0,8),(8,0,8)]
    for tri in [(0,1,3),(0,3,2),(2,3,5),(2,5,4)]:
        rows.append('debug/debugwhite')
        for n in tri:
            x,y,z=points[n];bone=int(n>=2)
            rows.append(f'{bone} {x} {y} {z} 0 -1 0 0 0')
    return '\n'.join(rows+['end',''])


def sparse_cloth_dmx():
    """Four separate one-point controls; neighboring proxy faces supply orientation."""
    text=cloth_dmx()
    uid=lambda n:f'cc100000-0000-0000-0000-{n:012x}'
    ref=lambda n:f'"element" "{uid(n)}"'
    joints=', '.join(ref(20+2*i) for i in range(4))
    transforms=', '.join(ref(21+2*i) for i in range(4))
    text=text.replace(f'"jointList" "element_array" [ {ref(4)}, {ref(8)} ]',f'"jointList" "element_array" [ {ref(4)}, {joints} ]')
    text=text.replace(f'"jointTransforms" "element_array" [ {ref(5)}, {ref(9)} ]',f'"jointTransforms" "element_array" [ {ref(5)}, {transforms} ]')
    text=text.replace(f'"children" "element_array" [ {ref(8)} ]',f'"children" "element_array" [ {joints} ]')
    text=text.replace('"jointIndices" "int_array" [ "0", "0", "1", "1", "1", "1" ]','"jointIndices" "int_array" [ "0", "0", "1", "2", "3", "4" ]')
    for i in range(4):
        text+=f'"DmeJoint" {{ "id" "elementid" "{uid(20+2*i)}" "name" "string" "flap{i}" "transform" {ref(21+2*i)} "children" "element_array" [] }}\n'
        text+=f'"DmeTransform" {{ "id" "elementid" "{uid(21+2*i)}" "name" "string" "flap{i}" "position" "vector3" "1 2 3" "orientation" "quaternion" "0 0 {math.sin(.15)} {math.cos(.15)}" }}\n'
    return text


def sparse_render_smd():
    text=render_smd().replace('1 "flap" 0','\n'.join(f'{i+1} "flap{i}" 0' for i in range(4)))
    text=text.replace('1 0 0 0 0 0 0','\n'.join(f'{i+1} 1 2 3 0 0 .3' for i in range(4)))
    for i,(x,z) in enumerate([(-8,16),(8,16),(-8,8),(8,8)]):text=text.replace(f'1 {x} 0 {z} 0 -1 0',f'{i+1} {x} 0 {z} 0 -1 0')
    return text


def cloth_maps(text, **maps):
    fields=''
    for name,values in maps.items():
        if not isinstance(values,(list,tuple)):values=[values]*6
        fields+=f'"{name}" "float_array" [ '+', '.join(f'"{value}"' for value in values)+' ]\n'
    return text.replace('"cloth_enableIndices"',fields+'"cloth_enableIndices"')


def fe_resource(data):
    header=struct.unpack_from('<i',data,400)[0]
    field=header+32
    offset=struct.unpack_from('<i',data,field)[0]
    if not offset: raise AssertionError('missing FE resource')
    start=field+offset
    if start%32: raise AssertionError('FE resource must be 32-byte aligned')
    if start+536>len(data): raise AssertionError('truncated FE descriptor')
    def array(field,size,alignment=4):
        delta,count=struct.unpack_from('<iI',data,start+field)
        if count==0:
            if delta:raise AssertionError('empty resource array has a nonzero offset')
            return 0,0
        at=start+field+delta
        if not delta or at<start+536 or at%alignment or at+count*size>len(data):
            raise AssertionError(f'invalid FE array at descriptor offset {field}')
        return at,count
    return start,array


class ClothCases:
    def cloth_model(self, *, triangles=False, plane=False, transform='', proxy=None, collision_proxy=None, settings='', success=True, mesh=None):
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        self.write('cloth_mesh.smd',render_smd() if mesh is None else mesh)
        self.write('cloth_proxy.dmx',cloth_dmx(triangles=triangles) if proxy is None else proxy)
        self.write('cloth_plane.dmx',cloth_dmx(plane=True) if collision_proxy is None else collision_proxy)
        return self.scene_qc('$modelname fecloth\n'+transform+'$body m cloth_mesh.smd\n'+
            (f'$cloth {{ {settings} }}\n' if settings else '')+'$cloth cloth_proxy.dmx\n'+('$clothplanecollision cloth_plane.dmx\n' if plane else ''),success=success)

    def test_cloth_emits_real_constraints_controls_and_planes(self):
        self.cloth_model(plane=True)
        data=self.mdl('fecloth');start,array=fe_resource(data)
        nodes,static,locked=struct.unpack_from('<3H',data,start+32)
        self.assertEqual((nodes,static,locked),(8,3,3))
        at,count=array(120,32,16);self.assertEqual(count,nodes)
        poses=[struct.unpack_from('<3f',data,at+i*32) for i in range(count)]
        name_at,count=array(8,4);names=[]
        for i in range(count):
            p=name_at+i*4+struct.unpack_from('<i',data,name_at+i*4)[0]
            names.append(data[p:data.index(b'\0',p)].decode())
        self.assertEqual(names[0],'root');self.assertEqual(names[-1],'flap')
        at,count=array(152,16);self.assertEqual(count,2)
        for i in range(count):
            parent,child=struct.unpack_from('<2H',data,at+i*16)
            self.assertEqual(parent,0);self.assertLess(child,static)
        at,count=array(88,76);self.assertEqual(count,2)
        for i in range(count):
            ids=struct.unpack_from('<4H',data,at+i*76)
            self.assertEqual(len(set(ids)),4);self.assertLess(max(ids),nodes)
            shape=[struct.unpack_from('<3f',data,at+i*76+12+j*16) for j in range(4)]
            # An orthonormal rest frame must preserve every edge and diagonal.
            for a in range(4):
                for b in range(a):
                    rest=sum((shape[a][k]-shape[b][k])**2 for k in range(3))
                    world=sum((poses[ids[a]][k]-poses[ids[b]][k])**2 for k in range(3))
                    self.assertAlmostEqual(rest,world,places=3)
            weights=[struct.unpack_from('<f',data,at+i*76+12+j*16+12)[0] for j in range(4)]
            self.assertAlmostEqual(sum(weights),1)
        self.assertEqual(array(96,304,16)[1],2)
        fit_at,count=array(320,64,16);self.assertEqual(count,1)
        weight_at,count=array(336,8);self.assertEqual(count,4)
        center=struct.unpack_from('<3f',data,fit_at+32)
        end,node,ctrl,begin=struct.unpack_from('<4H',data,fit_at+44)
        self.assertEqual((begin,end,node,ctrl),(0,4,7,7))
        weights=[struct.unpack_from('<fH',data,weight_at+i*8) for i in range(count)]
        for axis in range(3):
            expected=sum(w*poses[n][axis] for w,n in weights)/sum(w for w,n in weights)
            self.assertAlmostEqual(center[axis],expected,places=4)
            offset=struct.unpack_from('<f',data,fit_at+axis*4)[0]
            self.assertAlmostEqual(offset+center[axis],poses[node][axis],places=4)
        at,count=array(184,24);self.assertEqual(count,4)
        for i in range(count):
            parent,child,*plane=struct.unpack_from('<2H5f',data,at+i*24)
            self.assertEqual(parent,0);self.assertGreaterEqual(child,static)
            distance=sum(plane[k]*poses[child][k] for k in range(3))-plane[3]
            self.assertAlmostEqual(distance,4,places=4)
        at,count=array(288,2,2);self.assertEqual(count,2*(nodes-static)-1)
        parents=struct.unpack_from('<'+'H'*count,data,at)
        self.assertEqual(parents[-1],65535)
        self.assertTrue(all(i<p<count for i,p in enumerate(parents[:-1])))
        self.assertEqual(array(304,4,2)[1],nodes-static-1)

    def test_cloth_triangle_packets_have_valid_rest_shapes(self):
        self.cloth_model(triangles=True)
        data=self.mdl('fecloth');start,array=fe_resource(data)
        pose_at,node_count=array(120,32,16)
        poses=[struct.unpack_from('<3f',data,pose_at+i*32) for i in range(node_count)]
        at,count=array(104,128,16);self.assertEqual(count,4)
        self.assertEqual(array(96,304,16)[1],0)
        for i in range(count):
            ids=struct.unpack_from('<12I',data,at+i*128)
            self.assertEqual(ids[0:4],(ids[0],)*4)
            self.assertEqual(len(set((ids[0],ids[4],ids[8]))),3)
            self.assertGreater(struct.unpack_from('<f',data,at+i*128+80)[0],0)
            self.assertGreater(struct.unpack_from('<f',data,at+i*128+112)[0],0)
            x=struct.unpack_from('<f',data,at+i*128+80)[0]
            u=struct.unpack_from('<f',data,at+i*128+96)[0]
            v=struct.unpack_from('<f',data,at+i*128+112)[0]
            for a,b,expected in [(0,4,x*x),(0,8,u*u+v*v),(4,8,(u-x)**2+v*v)]:
                self.assertAlmostEqual(sum((poses[ids[a]][k]-poses[ids[b]][k])**2 for k in range(3)),expected,places=3)

    def test_cloth_rejects_missing_enable_and_unsupported_maps(self):
        text=cloth_dmx()
        self.assertIn('cloth_enable',self.cloth_model(proxy=text.replace('"cloth_enable"','"enable_wrong"'),success=False))
        self.assertIn('unsupported proxy attribute',self.cloth_model(proxy=text.replace('"cloth_enable"','"cloth_mystery"'),success=False))

    def test_cloth_locks_mixed_bone_without_flex_borders_and_rejects_unbound(self):
        text=cloth_dmx().replace('"jointIndices" "int_array" [ "0", "0", "1", "1", "1", "1" ]','"jointIndices" "int_array" [ "0", "0", "0", "0", "0", "0" ]')
        self.cloth_model(proxy=text)
        _,array=fe_resource(self.mdl('fecloth'))
        self.assertEqual(array(320,64,16)[1],0)
        text=cloth_dmx().replace('"jointWeights" "float_array" [ "1", "1", "1", "1", "1", "1" ]','"jointWeights" "float_array" [ "0", "1", "1", "1", "1", "1" ]')
        self.assertIn('unbound proxy point',self.cloth_model(proxy=text,success=False))

    def test_cloth_rejects_invalid_indices_and_no_anchors(self):
        text=cloth_dmx().replace('"positionsIndices" "int_array" [ "0", "1", "2", "3", "4", "5" ]','"positionsIndices" "int_array" [ "0", "1", "2", "3", "4", "99" ]')
        self.assertIn('index out of range',self.cloth_model(proxy=text,success=False))
        text=cloth_dmx().replace('"cloth_enable" "float_array" [ "0", "0", "1", "1", "1", "1" ]','"cloth_enable" "float_array" [ "1", "1", "1", "1", "1", "1" ]')
        self.assertIn('fixed points',self.cloth_model(proxy=text,success=False))

    def test_cloth_proxy_and_render_geometry_share_scale_origin_and_rotation(self):
        self.cloth_model(transform='$scale 2\n$origin 3 4 5\n')
        data=self.mdl('fecloth');start,array=fe_resource(data)
        at,count=array(120,32,16)
        proxy=sorted(tuple(round(v,4) for v in struct.unpack_from('<3f',data,at+i*32)) for i in range(1,7))
        vvd=(self.root/'models/fecloth.vvd').read_bytes()
        count=struct.unpack_from('<i',vvd,16)[0];at=struct.unpack_from('<i',vvd,56)[0]
        rendered=sorted(tuple(round(v,4) for v in struct.unpack_from('<3f',vvd,at+i*48+16)) for i in range(count))
        self.assertEqual(proxy,rendered)
        # A later $scale applies only to subsequently imported files.
        self.scene_qc('$modelname fecloth\n$scale 2\n$body m cloth_mesh.smd\n'
            '$cloth cloth_proxy.dmx\n$clothplanecollision cloth_plane.dmx\n$scale 3\n')
        data=self.mdl('fecloth');_,array=fe_resource(data);at,_=array(120,32,16)
        reloaded=sorted(tuple(round(v,4) for v in struct.unpack_from('<3f',data,at+i*32)) for i in range(1,7))
        self.assertEqual(reloaded,proxy)
        at,count=array(184,24)
        self.assertEqual(count,4)
        self.assertTrue(all(abs(struct.unpack_from('<f',data,at+i*24+16)[0]+8)<1e-4 for i in range(count)))

    def test_cloth_control_names_follow_chained_bone_renames(self):
        self.cloth_model(transform='$renamebone flap intermediate\n$renamebone intermediate final\n')
        data=self.mdl('fecloth');start,array=fe_resource(data);at,count=array(8,4)
        names=[]
        for i in range(count):
            ptr=at+i*4+struct.unpack_from('<i',data,at+i*4)[0]
            names.append(data[ptr:data.index(b'\0',ptr)].decode())
        self.assertIn('final',names);self.assertNotIn('flap',names);self.assertNotIn('intermediate',names)
        _,bones=self.csgo_bone_table('fecloth');self.assertIn('final',bones)

    def test_cloth_failure_keeps_previous_model_files(self):
        self.cloth_model()
        paths=list((self.root/'models').glob('fecloth.*'));before={p:p.read_bytes() for p in paths}
        text=cloth_dmx().replace('"cloth_enable" "float_array" [ "0", "0", "1", "1", "1", "1" ]','"cloth_enable" "float_array" [ "1", "1", "1", "1", "1", "1" ]')
        self.cloth_model(proxy=text,success=False)
        self.assertEqual(before,{p:p.read_bytes() for p in paths})

    def test_cloth_mass_bias_drag_and_gravity_follow_attribute_semantics(self):
        text=cloth_dmx().replace('"cloth_enable" ]','"cloth_enable", "cloth_mass", "cloth_drag", "cloth_gravity" ]')
        maps=''
        for name,value in [('cloth_mass',0),('cloth_drag',.5),('cloth_gravity',120)]:
            maps+=f'"{name}" "float_array" [ '+', '.join(f'"{value}"' for _ in range(6))+' ]\n'
        text=text.replace('"cloth_enableIndices"',maps+'"cloth_enableIndices"')
        self.cloth_model(proxy=text)
        data=self.mdl('fecloth');start,array=fe_resource(data)
        at,count=array(144,4);masses=struct.unpack_from('<'+'f'*count,data,at)
        # The middle row receives area from two quads; exp(cloth_mass=0) adds 1.
        for i,base_mass in [(3,64),(4,64),(5,32),(6,32)]:self.assertAlmostEqual(masses[i],1/(base_mass+1),places=6)
        at,count=array(192,16)
        for i in range(3,7):
            damping,force,attract,gravity=struct.unpack_from('<4f',data,at+i*16)
            self.assertAlmostEqual(damping,15);self.assertEqual((force,attract,gravity),(0,0,120))

    def test_cloth_collision_keeps_independent_meshes_and_rejects_warped_faces(self):
        uid=lambda n:f'cc100000-0000-0000-0000-{n:012x}'
        text=cloth_dmx(plane=True)
        children=f'"children" "element_array" [ "element" "{uid(4)}", "element" "{uid(6)}" ]'
        text=text.replace(children,children[:-2]+f', "element" "{uid(20)}" ]')
        text+=f'"DmeDag" {{ "id" "elementid" "{uid(20)}" "name" "string" "second_plane" "transform" "element" "{uid(21)}" "shape" "element" "{uid(10)}" }}\n'
        text+=f'"DmeTransform" {{ "id" "elementid" "{uid(21)}" "name" "string" "second_plane" "position" "vector3" "0 -4 0" "orientation" "quaternion" "0 0 0 1" }}\n'
        self.cloth_model(plane=True,collision_proxy=text)
        data=self.mdl('fecloth');start,array=fe_resource(data);at,count=array(184,24)
        self.assertEqual(count,8)
        self.assertEqual(sorted(round(struct.unpack_from('<f',data,at+i*24+16)[0],4) for i in range(count)),[-8]*4+[-4]*4)
        warped=cloth_dmx(plane=True).replace('"20 -4 32"','"20 -2 32"')
        self.assertIn('not planar',self.cloth_model(plane=True,collision_proxy=warped,success=False))

    def test_cloth_settings_write_runtime_parameters_and_reject_unknown_values(self):
        settings='local_position .4 local_rotation .3 surface_stretch .2 thread_stretch .1 gravity_scale .5 '+\
            'vel_air_drag 2 exp_air_drag 3 vel_quad_air_drag 4 exp_quad_air_drag 5 vel_rod_air_drag 6 exp_rod_air_drag 7 '+\
            'rod_vel_smooth_rate .25 quad_velocity_smooth_rate .5 windage .75 wind_drag .125 world_collision true'
        self.cloth_model(settings=settings)
        data=self.mdl('fecloth');start,array=fe_resource(data)
        self.assertAlmostEqual(struct.unpack_from('<f',data,start+24)[0],.4)
        self.assertAlmostEqual(struct.unpack_from('<f',data,start+28)[0],.3)
        values=struct.unpack_from('<13f',data,start+472)
        for actual,expected in zip(values,[.75,.125,.2,.1,.5,2,3,4,5,6,7,.25,.5]):self.assertAlmostEqual(actual,expected)
        self.assertEqual(struct.unpack_from('<2H',data,start+532),(1,1))
        self.assertEqual(struct.unpack_from('<I',data,start+20)[0]&(3<<16),3<<16)
        for value in ['mystery 1','prerotate 0','world_collision maybe','curvature 2','gravity_scale nan','vel_air_drag -1','local_position 1oops']:
            with self.subTest(setting=value):self.assertIn('cloth',self.cloth_model(settings=value,success=False).lower())

    def test_cloth_attraction_keeps_animated_target_offsets_and_integrator_flags(self):
        proxy=cloth_maps(cloth_dmx(),cloth_animation_attract=[0,0,.2,.2,.2,.2],cloth_animation_force_attract=[0,0,.5,.5,.5,.5])
        self.cloth_model(proxy=proxy)
        data=self.mdl('fecloth');start,array=fe_resource(data)
        self.assertEqual(struct.unpack_from('<I',data,start+20)[0]&((1<<9)|(1<<10)),(1<<9)|(1<<10))
        at,count=array(192,16)
        for node in range(3,7):self.assertEqual(struct.unpack_from('<2f',data,at+node*16+4),(15,6))
        at,count=array(152,16);self.assertEqual(count,6)
        pose_at,_=array(120,32,16)
        for i in range(count):
            parent,child,x,y,z=struct.unpack_from('<2H3f',data,at+i*16)
            if child>=3:
                self.assertEqual(parent,7)
                self.assertEqual((x,y,z),struct.unpack_from('<3f',data,pose_at+child*32))

    def test_cloth_zero_gravity_scale_survives_engine_legacy_default_fallback(self):
        self.cloth_model(settings='gravity_scale 0',proxy=cloth_maps(cloth_dmx(),cloth_gravity=120))
        data=self.mdl('fecloth');start,array=fe_resource(data)
        # The engine replaces a zero descriptor scale with 1 during initialization.
        self.assertEqual(struct.unpack_from('<f',data,start+488)[0],1)
        self.assertTrue(struct.unpack_from('<I',data,start+20)[0]&(1<<11))
        at,count=array(192,16)
        self.assertGreater(count,0)
        for i in range(count):self.assertEqual(struct.unpack_from('<f',data,at+i*16+12)[0],0)

    def test_cloth_hinge_rods_and_rigid_bends_encode_rest_geometry(self):
        for curvature in [0,.5,1]:
            self.cloth_model(settings=f'curvature {curvature}')
            data=self.mdl('fecloth');start,array=fe_resource(data)
            at,count=array(128,20);self.assertEqual(count,2)
            packet_at,packet_count=array(112,80,16);self.assertEqual(packet_count,count)
            for i in range(count):
                n0,n1,maximum,minimum,weight,relaxation=struct.unpack_from('<2H4f',data,at+i*20)
                self.assertLess(n0,3);self.assertIn(n1,[5,6]);self.assertAlmostEqual(maximum,16)
                self.assertAlmostEqual(minimum,16*math.sin(curvature*math.pi/2),places=5)
                self.assertEqual((weight,relaxation),(0,1))
                self.assertEqual(struct.unpack_from('<8H',data,packet_at+i*80),(n0,)*4+(n1,)*4)
        self.cloth_model(settings='rigid_edge_hinges true')
        data=self.mdl('fecloth');_,array=fe_resource(data);at,count=array(136,40)
        self.assertEqual(count,1)
        te,tv,distance,*weights=struct.unpack_from('<7f',data,at)
        self.assertAlmostEqual(te,.5);self.assertAlmostEqual(tv,.5);self.assertEqual(distance,0)
        self.assertTrue(all(math.isfinite(w) for w in weights));self.assertGreater(sum(abs(w) for w in weights),0)
        at,count=array(128,20)
        for i in range(count):self.assertEqual(struct.unpack_from('<2f',data,at+i*20+4),(16,16))
        self.cloth_model(settings='add_stiffness_rods false')
        _,array=fe_resource(self.mdl('fecloth'));self.assertEqual(array(128,20)[1],0);self.assertEqual(array(112,80,16)[1],0)
        self.cloth_model(triangles=True,settings='rigid_edge_hinges true')
        data=self.mdl('fecloth');_,array=fe_resource(data);self.assertGreater(array(128,20)[1],0);self.assertGreater(array(136,40)[1],0)

    def test_cloth_ground_collision_groups_radii_and_tree_masks(self):
        proxy=cloth_maps(cloth_dmx(),cloth_ground_collision=[0,0,.25,.25,.8,0],cloth_ground_friction=.3,cloth_collision_radius=2)
        self.cloth_model(proxy=proxy,settings='world_collision true',transform='$scale 2\n')
        data=self.mdl('fecloth');start,array=fe_resource(data)
        at,count=array(280,2,2);self.assertEqual(count,3)
        self.assertEqual(struct.unpack_from('<3H',data,at),(5,3,4))
        at,count=array(216,12);self.assertEqual(count,2)
        for i,(friction,begin,end) in enumerate([(.2,0,1),(.75,1,3)]):
            world,ground,b,e=struct.unpack_from('<2f2H',data,at+i*12)
            self.assertAlmostEqual(world,friction);self.assertAlmostEqual(ground,.3);self.assertEqual((b,e),(begin,end))
        at,count=array(232,4);self.assertEqual(count,5)
        self.assertEqual(struct.unpack_from('<5f',data,at),(4,4,4,4,0))
        at,count=array(296,2,2);masks=struct.unpack_from('<'+'H'*count,data,at)
        self.assertEqual(masks[:5],(65535,65535,65535,65535,0));self.assertEqual(masks[-1],65535)
        invalid=cloth_maps(cloth_dmx(),cloth_ground_collision=1.1)
        self.assertIn('invalid cloth',self.cloth_model(proxy=invalid,success=False))

    def test_cloth_rejects_nonmanifold_topology_and_invalid_rotation_maps(self):
        proxy=cloth_dmx().replace('"0", "1", "3", "2", "-1", "2", "3", "5", "4", "-1"','"0", "1", "3", "2", "-1", "0", "1", "3", "2", "-1", "2", "3", "5", "4", "-1"')
        self.assertIn('non-manifold',self.cloth_model(proxy=proxy,success=False))
        for name in ['cloth_use_rods','cloth_anchor_free_rotate']:
            self.assertIn('invalid cloth rod or anchor rotation map',self.cloth_model(proxy=cloth_maps(cloth_dmx(),**{name:1.1}),success=False))

    def test_cloth_rigid_colliders_preserve_bone_local_coordinates_and_scale_once(self):
        self.cloth_model(settings='sphere root 1 2 3 4 capsule root 2 3 4 5 2 3 24 2',transform='$scale 2\n$origin 3 4 5\n')
        data=self.mdl('fecloth');_,array=fe_resource(data)
        at,count=array(272,24);self.assertEqual(count,1)
        self.assertEqual(struct.unpack_from('<2H5f',data,at),(0,65535,2,4,6,8,0))
        at,count=array(264,40);self.assertEqual(count,1)
        self.assertEqual(struct.unpack_from('<2H9f',data,at),(0,65535,4,6,48,4,6,8,4,10,0))
        # The later scale is unrelated to colliders declared at the earlier scale.
        self.scene_qc('$modelname fecloth\n$scale 2\n$body m cloth_mesh.smd\n$cloth cloth_proxy.dmx\n'
            '$cloth { sphere root 1 2 3 4 }\n$scale 3\n')
        data=self.mdl('fecloth');_,array=fe_resource(data);at,_=array(272,24)
        self.assertEqual(struct.unpack_from('<4f',data,at+4),(2,4,6,8))

    def test_cloth_rejects_invalid_rigid_colliders(self):
        for settings in ['sphere root 0 0 0 0','sphere root 0 0 0 -1','sphere root nan 0 0 1',
                'sphere missing 0 0 0 1','sphere flap 0 0 0 1','capsule root 0 0 0 1 0 0 0 1',
                'capsule root 0 0 0 10 0 0 2 1']:
            with self.subTest(settings=settings):self.assertIn('cloth',self.cloth_model(settings=settings,success=False).lower())

    def test_cloth_sparse_controls_reconstruct_bind_and_rigidly_transformed_pose(self):
        self.cloth_model(proxy=sparse_cloth_dmx(),mesh=sparse_render_smd())
        data=self.mdl('fecloth');start,array=fe_resource(data)
        pose_at,node_count=array(120,32,16)
        poses=[struct.unpack_from('<8f',data,pose_at+i*32) for i in range(node_count)]
        bases_at,base_count=array(72,32);reverse_at,reverse_count=array(344,16)
        self.assertEqual((base_count,reverse_count,array(320,64,16)[1]),(4,4,0))
        free_at,free_count=array(312,2,2);free_nodes=struct.unpack_from('<'+'H'*free_count,data,free_at)
        def sub(a,b):return tuple(x-y for x,y in zip(a,b))
        def dot(a,b):return sum(x*y for x,y in zip(a,b))
        def unit(v):return tuple(x/math.sqrt(dot(v,v)) for x in v)
        def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
        def qrotate(q,v):
            x,y,z,w=q;u=(x,y,z);uv=cross(u,v);uuv=cross(u,uv)
            return tuple(v[i]+2*(w*uv[i]+uuv[i]) for i in range(3))
        # Independently evaluate the retail basis + reverse-offset equations.
        for angle in [0,.73]:
            q=(0,math.sin(angle/2),0,math.cos(angle/2));shift=(4,-7,2) if angle else (0,0,0)
            transformed=[tuple(qrotate(q,p[:3])[i]+shift[i] for i in range(3)) for p in poses]
            rotations={}
            for i in range(base_count):
                node,_,_,_,x0,x1,y0,y1=struct.unpack_from('<8H',data,bases_at+i*32)
                adjust=struct.unpack_from('<4f',data,bases_at+i*32+16)
                self.assertNotIn(node,free_nodes)
                y=unit(sub(transformed[y1],transformed[y0]));raw=sub(transformed[x1],transformed[x0])
                x=unit(tuple(raw[k]-dot(raw,y)*y[k] for k in range(3)));z=cross(x,y)
                def rotate(v,x=x,y=y,z=z,adjust=adjust):
                    local=qrotate(adjust,v);return tuple(x[k]*local[0]+y[k]*local[1]+z[k]*local[2] for k in range(3))
                rotations[node]=rotate
                for axis in [(1,0,0),(0,1,0),(0,0,1)]:
                    expected=qrotate(q,qrotate(poses[node][4:8],axis))
                    for actual,want in zip(rotate(axis),expected):self.assertAlmostEqual(actual,want,places=5)
            for i in range(reverse_count):
                ctrl,target,*offset=struct.unpack_from('<2H3f',data,reverse_at+i*16)
                reconstructed=sub(transformed[target],rotations[ctrl](offset))
                for actual,want in zip(reconstructed,transformed[ctrl]):self.assertAlmostEqual(actual,want,places=4)

    def test_cloth_free_anchors_are_partitioned_and_keep_position_offsets(self):
        self.cloth_model(proxy=cloth_maps(cloth_dmx(),cloth_anchor_free_rotate=[1,0,0,0,0,0]))
        data=self.mdl('fecloth');start,array=fe_resource(data)
        self.assertEqual(struct.unpack_from('<3H',data,start+32),(8,3,2))
        at,count=array(72,32);self.assertEqual(count,1);self.assertEqual(struct.unpack_from('<H',data,at)[0],2)
        at,count=array(152,16);self.assertEqual(count,2)
        self.assertEqual(sorted(struct.unpack_from('<2H',data,at+i*16)[1] for i in range(count)),[1,2])

    def test_cloth_rod_maps_replace_faces_deduplicate_pairs_and_preserve_mass_weights(self):
        self.cloth_model(proxy=cloth_maps(cloth_dmx(),cloth_use_rods=1),settings='add_stiffness_rods false')
        data=self.mdl('fecloth');_,array=fe_resource(data)
        self.assertEqual(array(88,76)[1],0);self.assertEqual(array(96,304,16)[1],0);self.assertEqual(array(104,128,16)[1],0)
        poses_at,_=array(120,32,16);mass_at,_=array(144,4)
        at,count=array(128,20);self.assertEqual(count,10);self.assertEqual(array(112,80,16)[1],count)
        pairs=[]
        for i in range(count):
            a,b,maximum,minimum,weight,relaxation=struct.unpack_from('<2H4f',data,at+i*20)
            pairs.append((a,b));self.assertLess(a,b);self.assertEqual(minimum,maximum);self.assertEqual(relaxation,1)
            pa=struct.unpack_from('<3f',data,poses_at+a*32);pb=struct.unpack_from('<3f',data,poses_at+b*32)
            self.assertAlmostEqual(maximum,math.dist(pa,pb),places=5)
            wa=struct.unpack_from('<f',data,mass_at+a*4)[0];wb=struct.unpack_from('<f',data,mass_at+b*4)[0]
            self.assertAlmostEqual(weight,wa/(wa+wb),places=6)
        self.assertEqual(len(set(pairs)),count)
        # A flag on one corner replaces only the incident top quad.
        self.cloth_model(proxy=cloth_maps(cloth_dmx(),cloth_use_rods=[1,0,0,0,0,0]),settings='add_stiffness_rods false')
        _,array=fe_resource(self.mdl('fecloth'));self.assertEqual(array(88,76)[1],1);self.assertEqual(array(128,20)[1],5)

    def test_cloth_sparse_rejects_basis_below_runtime_axis_threshold(self):
        # A valid but tiny neighboring face would select the engine's arbitrary
        # fallback axis instead of the compiler's bind-space adjustment.
        proxy=sparse_cloth_dmx()
        for before,after in [('-8 0 24','-.008 0 .024'),('8 0 24','.008 0 .024'),('-8 0 16','-.008 0 .016'),('8 0 16','.008 0 .016'),('-8 0 8','-.008 0 .008'),('8 0 8','.008 0 .008')]:proxy=proxy.replace('"'+before+'"','"'+after+'"')
        self.assertIn('0.05-unit threshold',self.cloth_model(proxy=proxy,mesh=sparse_render_smd(),success=False))
