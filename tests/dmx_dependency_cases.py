"""Self-authored DMX rig and animation graphs; checks serialized output and baked poses."""
import math
import struct

# Final MDL animation positions use signed 16-bit values with a minimum
# +/-128 range. Truncation can lose one whole step before SMD decompilation.
POSITION_TOLERANCE=128/32767+2e-5


class Document:
    def __init__(self): self.rows=[]
    def ref(self,n): return f'"element" "dd200000-0000-0000-0000-{n:012x}"'
    def element(self,n,kind,name,body=''):
        self.rows.append(f'"{kind}" {{ "id" "elementid" "dd200000-0000-0000-0000-{n:012x}" "name" "string" "{name}" {body} }}')
    def array(self,name,kind,values): return f'"{name}" "{kind}_array" [ '+', '.join(f'"{v}"' for v in values)+' ]'
    def elements(self,name,ids): return f'"{name}" "element_array" [ '+', '.join(self.ref(n) for n in ids)+' ]'
    def text(self): return '<!-- dmx encoding keyvalues2 1 format model 18 -->\n'+'\n'.join(self.rows)+'\n'


def constraint_fixture(kinds=('Point','Orient','Aim','Parent')):
    d=Document();names=['root','driverA','driverB','up']+['slave'+kind for kind in kinds]
    d.element(1,'DmElement','rig',f'"skeleton" {d.ref(2)} '+d.elements('constraints',range(100,100+len(kinds))))
    d.element(2,'DmeModel','rig',d.elements('children',[10]))
    for i,name in enumerate(names):
        d.element(10+i,'DmeJoint',name,f'"transform" {d.ref(30+i)} '+d.elements('children',range(11,10+len(names)) if i==0 else []))
        d.element(30+i,'DmeTransform',name,'"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    for j,kind in enumerate(kinds):
        d.element(100+j,'DmeRig'+kind+'ConstraintOperator',kind,f'"slave" {d.ref(200+j)} '+d.elements('targets',[300+2*j,301+2*j])+
                  (f' "upSpaceTarget" {d.ref(13)} "upType" "int" "0" "upVector" "vector3" "0 0 1" "aimOffset" "quaternion" "0 0 0 1"' if kind=='Aim' else ''))
        d.element(200+j,'DmeConstraintSlave',kind+'Slave',f'"target" {d.ref(14+j)} "position" "vector3" "1 2 3" "orientation" "quaternion" "0 0 0 1"')
        for k,(bone,weight) in enumerate([(11,.25),(12,.75)]):
            d.element(300+2*j+k,'DmeConstraintTarget','target',f'"target" {d.ref(bone)} "targetWeight" "float" "{weight}" "vecOffset" "vector3" "{k+1} 2 3" "oOffset" "quaternion" "0 0 0 1"')
    nodes='\n'.join(f'{i} "{name}" {-1 if i==0 else 0}' for i,name in enumerate(names))
    poses='\n'.join(f'{i} 0 0 0 0 0 0' for i in range(len(names)))
    smd='version 1\nnodes\n'+nodes+'\nend\nskeleton\ntime 0\n'+poses+'\nend\ntriangles\nmaterial\n0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n'
    return d.text(),smd


def animation_fixture(*, quaternion=False, array=False):
    d=Document()
    d.element(1,'DmElement','animation',f'"skeleton" {d.ref(2)} "animationList" {d.ref(6)}')
    d.element(2,'DmeModel','model',d.elements('children',[3]))
    d.element(3,'DmeJoint','root',f'"transform" {d.ref(4)} '+d.elements('children',[]))
    d.element(4,'DmeTransform','root','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    d.element(6,'DmeAnimationList','animations',d.elements('animations',[7]))
    d.element(7,'DmeChannelsClip','motion',f'"frameRate" "int" "4" "timeFrame" {d.ref(8)} '+d.elements('channels',[9]))
    d.element(8,'DmeTimeFrame','time','"start" "time" "0" "duration" "time" "1" "offset" "time" "0" "scale" "float" "1"')
    if quaternion:
        d.element(9,'DmeChannel','rotation',f'"toElement" {d.ref(4)} "toAttribute" "string" "orientation" "log" {d.ref(10)}')
        d.element(10,'DmeQuaternionLog','rotlog',d.elements('layers',[11]))
        d.element(11,'DmeQuaternionLogLayer','rotlayer',d.array('times','int',[0,10000])+d.array('values','quaternion',['0 0 0 1','0 0 0.7071067811865476 0.7071067811865476']))
    else:
        d.element(9,'DmeChannel','control',f'"toElement" {d.ref(20)} "toAttribute" "string" "value" "toIndex" "int" "1" "log" {d.ref(10)}')
        d.element(10,'DmeFloatLog','valueLog',d.elements('layers',[11,12]))
        d.element(11,'DmeFloatLogLayer','base',d.array('times','int',[0,10000])+d.array('values','float',[0,4]))
        d.element(12,'DmeFloatLogLayer','override',d.array('times','int',[2500,7500])+d.array('values','float',[10,14])+d.array('noninterpolatedsegments','bool',['true','false']))
        d.element(20,'DmeElement','control',d.array('value','float',[99,0]) if array else '"value" "float" "0"')
        d.element(21,'DmeExpressionOperator','compute','"value" "float" "0" "result" "float" "0" "expr" "string" "max(value * 2, 1) + 3"')
        d.element(22,'DmePackVector3Operator','pack','"x" "float" "0" "y" "float" "2" "z" "float" "3" "vector" "vector3" "0 0 0"')
        d.element(23,'DmeUnpackVector3Operator','unpack','"x" "float" "0" "y" "float" "0" "z" "float" "0" "vector" "vector3" "0 0 0"')
        d.element(24,'DmeTransformOperator','apply',f'"transform" {d.ref(4)} "positionX" "float" "0" "positionY" "float" "0" "positionZ" "float" "0" "orientationX" "float" "0" "orientationY" "float" "0" "orientationZ" "float" "0" "orientationW" "float" "1"')
        links=[(20,'value',21,'value'),(21,'result',22,'x'),(22,'vector',23,'vector'),(23,'x',24,'positionX'),(23,'y',24,'positionY'),(23,'z',24,'positionZ')]
        for i,(a,aa,b,ba) in enumerate(links):
            d.element(100+i,'DmeConnectionOperator','connection'+str(i),f'"input" {d.ref(200+i*2)} '+d.elements('outputs',[201+i*2]))
            d.element(200+i*2,'DmeAttributeReference','input',f'"element" {d.ref(a)} "attribute" "string" "{aa}" "index" "int" "{1 if array and i==0 else 0}"')
            d.element(201+i*2,'DmeAttributeReference','output',f'"element" {d.ref(b)} "attribute" "string" "{ba}" "index" "int" "0"')
        d.element(400,'DmeAnimationSet','set',d.elements('operators',[21,22,23,24]+list(range(100,106))))
    return d.text()


def compressed_log_blob(samples, *, scale=(1, 1, 1), base=(0, 0, 0), runs=None):
    """Reference-format component RLE; samples contain signed quantized triples.

    Optional runs is three lists of (explicit_values, total_count) tuples, useful
    for constructing mixed literal/repeated runs and deliberately corrupt data.
    """
    streams=[]
    for axis in range(3):
        if runs is None:
            values=[sample[axis] for sample in samples];axis_runs=[];start=0
            while start<len(values):
                end=start+1
                while end<len(values) and end-start<255 and values[end]==values[start]:end+=1
                axis_runs.append(([values[start]],end-start));start=end
        else:axis_runs=runs[axis]
        streams.append(b''.join(struct.pack('<BB',len(values),total)+struct.pack('<'+'h'*len(values),*values) for values,total in axis_runs))
    return struct.pack('<6f2I',*scale,*base,32+len(streams[0]),32+len(streams[0])+len(streams[1]))+b''.join(streams)


def log_fixture(*, kind='Vector3', times=(0,10000), values=None, compressed=None,
                curve_types=None, curve_info=None, fps=4, duration=1):
    """A direct Float/Vector3/Quaternion log driving the root transform.

    times are 1/10000-second ticks; curve_info is a raw curve-info attribute body.
    Float logs drive positionX through a DmeTransformOperator.
    """
    d=Document()
    d.element(1,'DmElement','animation',f'"skeleton" {d.ref(2)} "animationList" {d.ref(6)}')
    d.element(2,'DmeModel','model',d.elements('children',[3]))
    d.element(3,'DmeJoint','root',f'"transform" {d.ref(4)} '+d.elements('children',[]))
    d.element(4,'DmeTransform','root','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    d.element(6,'DmeAnimationList','animations',d.elements('animations',[7]))
    d.element(7,'DmeChannelsClip','motion',f'"frameRate" "int" "{fps}" "timeFrame" {d.ref(8)} '+d.elements('channels',[9]))
    d.element(8,'DmeTimeFrame','time',f'"start" "time" "0" "duration" "time" "{duration}" "offset" "time" "0" "scale" "float" "1"')
    d.element(9,'DmeChannel','channel',f'"toElement" {d.ref(20 if kind=="Float" else 4)} "toAttribute" "string" "'+('positionX' if kind=='Float' else 'orientation' if kind=='Quaternion' else 'position')+f'" "log" {d.ref(10)}')
    d.element(10,'Dme'+kind+'Log','log',d.elements('layers',[11])+(f' "curveinfo" {d.ref(12)}' if curve_info is not None else ''))
    body=d.array('times','int',times)
    if values is not None:body+=d.array('values',kind.lower(),[' '.join(map(str,v)) if isinstance(v,(tuple,list)) else v for v in values])
    if compressed is not None:body+=f' "compressed" "binary" "{compressed.hex()}"'
    if curve_types is not None:body+=d.array('curvetypes','int',curve_types)
    d.element(11,'Dme'+kind+'LogLayer','layer',body)
    if curve_info is not None:d.element(12,'Dme'+kind+'CurveInfo','curve',curve_info)
    if kind=='Float':
        d.element(20,'DmeTransformOperator','apply',f'"transform" {d.ref(4)} "positionX" "float" "0" "positionY" "float" "0" "positionZ" "float" "0" "orientationX" "float" "0" "orientationY" "float" "0" "orientationZ" "float" "0" "orientationW" "float" "1"')
    return d.text()


class DmxDependencyCases:
    def constraint_compile(self,*,qc='',text=None,app=730,success=True):
        fixture,smd=constraint_fixture()
        self.write('rig.dmx',fixture if text is None else text);self.write('rig.smd',smd)
        self.write('gameinfo.txt',f'GameInfo {{ FileSystem {{ SteamAppId {app} }} }}')
        return self.scene_qc('$modelname constraints\n$origin 0 0 0 -90\n'+qc+'$body m rig.smd\n$datamodeljoints rig.dmx proceduralbones\n',success=success)

    def test_dmx_four_multi_target_constraint_records(self):
        self.constraint_compile()
        data,bones=self.csgo_bone_table('constraints')
        for kind,proc in [('Point',8),('Orient',9),('Aim',10),('Parent',12)]:
            index,bone=bones['slave'+kind];flags,typ,offset=struct.unpack_from('<3i',data,bone+160)
            self.assertFalse(flags&4);self.assertEqual(typ,proc);at=bone+offset
            self.assertEqual(struct.unpack_from('<i',data,at)[0],index)
            self.assertEqual(struct.unpack_from('<3f',data,at+4),(1,2,3))
            count,target=struct.unpack_from('<2i',data,at+32);self.assertEqual(count,2)
            self.assertEqual(target,72 if proc==10 else 40)
            for j,name in enumerate(['driverA','driverB']):
                t=at+target+j*36;self.assertEqual(struct.unpack_from('<i',data,t)[0],bones[name][0])
                self.assertEqual(struct.unpack_from('<f',data,t+4)[0],[.25,.75][j])
                self.assertEqual(struct.unpack_from('<3f',data,t+8),(j+1,2,3))
            if proc==10:
                self.assertEqual(struct.unpack_from('<hB',data,at+68),(bones['up'][0],0))
                self.assertEqual(struct.unpack_from('<3f',data,at+56),(0,0,1))

    def test_dmx_constraint_renames_preserve_unweighted_dependencies(self):
        self.constraint_compile(qc='$renamebone driverA first\n$renamebone first renamed\n$renamebone slavePoint solved\n')
        data,bones=self.csgo_bone_table('constraints');self.assertIn('renamed',bones);self.assertNotIn('driverA',bones)
        at=bones['solved'][1];at+=struct.unpack_from('<i',data,at+168)[0];target=struct.unpack_from('<i',data,at+36)[0]
        self.assertEqual(struct.unpack_from('<i',data,at+target)[0],bones['renamed'][0])

    def test_dmx_constraint_target_gate_and_unsupported_operator(self):
        self.assertIn('CSGO target',self.constraint_compile(app=4000,success=False))
        text,_=constraint_fixture();text=text.replace('DmeRigPointConstraintOperator','DmeRigUnknownConstraintOperator')
        self.assertIn('unsupported operator',self.constraint_compile(text=text,success=False))

    def test_dmx_constraint_centerbones_combination_fails(self):
        self.assertIn('does not support $centerbonesonverts',self.constraint_compile(qc='$centerbonesonverts\n',success=False))

    def test_dmx_constraint_cycle_and_missing_bone_fail(self):
        text,_=constraint_fixture();text=text.replace('"target" "element" "dd200000-0000-0000-0000-00000000000b"','"target" "element" "dd200000-0000-0000-0000-00000000000e"')
        self.assertIn('cyclic bone dependency',self.constraint_compile(text=text,success=False))
        text,_=constraint_fixture();text=text.replace('"name" "string" "driverA"','"name" "string" "absent"')
        self.assertIn('missing target bone',self.constraint_compile(text=text,success=False))

    def test_dmx_constraint_bake_moves_all_four_slave_types(self):
        text,smd=constraint_fixture()
        self.write('rig.dmx',text);self.write('rig.smd',smd)
        rows=smd.split('skeleton')[0].splitlines()+['skeleton']
        for frame,z in enumerate([4,12]):
            rows+=['time '+str(frame)]
            for bone in range(8):
                x=-4 if bone==1 else 4 if bone==2 else 0
                height=z if bone in [1,2] else 0
                yaw=frame*math.pi/(6 if bone==1 else 2) if bone in [1,2] else 0
                rows.append(f'{bone} {x} 0 {height} 0 0 {yaw}')
        self.write('motion.smd','\n'.join(rows+['end','']))
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        self.scene_qc('$modelname baked\n$body m rig.smd\n$datamodeljoints rig.dmx proceduralbones\n$sequence motion motion.smd\n')
        self.animation_poses('baked','motion')
        path=next(p for p in (self.root/'decompiled').rglob('motion.smd') if any(a.name=='baked' for a in p.parents))
        names={};poses=[];section=''
        for line in path.read_text().splitlines():
            if line.strip() in ['nodes','skeleton','end']:section=line.strip();continue
            if section=='nodes':
                fields=line.split('"');names[int(fields[0])]=fields[1]
            elif section=='skeleton':
                fields=line.split()
                if fields[0]=='time':poses.append({})
                elif len(fields)==7:poses[-1][names[int(fields[0])]]=tuple(map(float,fields[1:]))
        self.assertEqual(len(poses),2)
        for frame,expected in enumerate([(3.75,2,7),(3.75,2,15)]):
            for actual,wanted in zip(poses[frame]['slavePoint'][:3],expected):self.assertAlmostEqual(actual,wanted,delta=.02)
            self.assertAlmostEqual(poses[frame]['slaveOrient'][5],frame*5*math.pi/12,delta=.002)
        for frame,expected in enumerate([(3.75,2,7),(.25*(math.sqrt(3)/2-5)+1.5,.25*(.5+math.sqrt(3))+1.5,15)]):
            for actual,wanted in zip(poses[frame]['slaveParent'][:3],expected):self.assertAlmostEqual(actual,wanted,delta=.02)
            self.assertAlmostEqual(poses[frame]['slaveParent'][5],frame*5*math.pi/12,delta=.002)
        # Aim uses the actual slave translation in authored space, then the
        # complete pose is converted back through the model's root basis.
        for frame,direction in enumerate([(3.75,2,7),(3.75,2,15)]):
            rx,ry,rz=poses[frame]['slaveAim'][3:]
            sx,cx,sy,cy,sz,cz=math.sin(rx),math.cos(rx),math.sin(ry),math.cos(ry),math.sin(rz),math.cos(rz)
            forward=(cz*sy*sx-sz*cx,sz*sy*sx+cz*cx,cy*sx)
            norm=math.sqrt(sum(v*v for v in direction))
            for actual,wanted in zip(forward,direction):self.assertAlmostEqual(actual,wanted/norm,delta=.002)
        data,bones=self.csgo_bone_table('baked')
        for name in ['slavePoint','slaveOrient','slaveAim','slaveParent']:
            self.assertFalse(struct.unpack_from('<i',data,bones[name][1]+160)[0]&4)

    def dependency_compile(self,text,*,name='graph',success=True):
        self.write('motion.dmx',text)
        return self.scene_qc(f'$modelname {name}\n$body m mesh.smd\n$sequence motion motion.dmx\n',success=success)

    def test_dmx_dependency_graph_computes_expression_pack_unpack_and_layer_overrides(self):
        self.dependency_compile(animation_fixture())
        poses=self.animation_poses('graph','motion');self.assertEqual(len(poses),5)
        for p,x in zip(poses,[4,23,23,31,11]):
            for a,b in zip(p[:3],[x,2,3]):self.assertAlmostEqual(a,b,delta=.01)

    def test_dmx_dependency_array_refs_and_clip_time_scale(self):
        text=animation_fixture(array=True).replace('"scale" "float" "1"','"scale" "float" "0.5"')
        self.dependency_compile(text)
        poses=self.animation_poses('graph','motion')
        for p,x in zip(poses,[4,4,23,23,23]):self.assertAlmostEqual(p[0],x,delta=.01)

    def test_dmx_dependency_quaternion_log_uses_slerp(self):
        self.dependency_compile(animation_fixture(quaternion=True))
        poses=self.animation_poses('graph','motion');self.assertEqual(len(poses),5)
        self.assertAlmostEqual(poses[2][5],math.pi/4,places=3)
        self.assertAlmostEqual(poses[4][5],math.pi/2,places=3)

    def test_dmx_float_curve_modes_have_reference_numeric_semantics(self):
        # Interior sample of (1,4,-2,6) at uneven times (-1,0,1,3).
        # Includes tangent output and the reference's counterintuitive ease names.
        expected=[2.8984375,2.8984375,1.7038994058,3.5432771951,3.0625,
                  1.9036458333,2.5,3.0953289063,2.941534375,3.2491234375,
                  3.0625,2.8046875,3.0486882627,-7.34375,-.933032354,4]
        for mode,wanted in enumerate(expected):
            with self.subTest(mode=mode):
                text=log_fixture(kind='Float',times=(-10000,0,10000,30000),values=(1,4,-2,6),
                                 curve_types=[mode*257]*4,curve_info='"minvalue" "float" "-100" "maxvalue" "float" "100"')
                self.dependency_compile(text,name='curve'+str(mode))
                self.assertAlmostEqual(self.animation_poses('curve'+str(mode),'motion')[1][0],wanted,delta=POSITION_TOLERANCE)

    def test_dmx_curve_mixed_modes_defaults_holds_and_value_bounds(self):
        cases=[([2,3<<8],0,(.75*math.sin(math.pi/8)+.25*(1-math.cos(math.pi/8)))*8),
               ([15,15<<8],0,0),([6,15<<8],0,8),([0,0],2*257,8*math.sin(math.pi/8))]
        for i,(curves,default,wanted) in enumerate(cases):
            text=log_fixture(kind='Float',values=(0,8),curve_types=curves,
                             curve_info=f'"defaultCurveType" "int" "{default}" "minvalue" "float" "-100" "maxvalue" "float" "100"')
            # Curve info wins over a noninterpolated segment marker.
            text=text.replace('"curvetypes" "int_array"','"noninterpolatedsegments" "bool_array" [ "true", "false" ] "curvetypes" "int_array"')
            self.dependency_compile(text,name='mixed'+str(i))
            self.assertAlmostEqual(self.animation_poses('mixed'+str(i),'motion')[1][0],wanted,delta=POSITION_TOLERANCE)
        self.dependency_compile(log_fixture(kind='Float',values=(0,4),curve_info='"defaultCurveType" "int" "1542"'))
        poses=self.animation_poses('graph','motion')
        self.assertAlmostEqual(poses[2][0],1,delta=POSITION_TOLERANCE)
        # The exact final key bypasses curve clamping when there is no right edge.
        self.assertAlmostEqual(poses[4][0],4,delta=POSITION_TOLERANCE)

    def test_dmx_curve_edge_metadata_affects_neighbor_tangents_and_final_cutoff(self):
        info='"defaultCurveType" "int" "2827" "minvalue" "float" "-100" "maxvalue" "float" "100" "useEdgeInfo" "bool" "true" "leftEdgeActive" "bool" "true" "leftEdgeValue" "float" "-6" "rightEdgeActive" "bool" "true" "rightEdgeValue" "float" "10" "rightEdgeTime" "time" "2"'
        self.dependency_compile(log_fixture(kind='Float',values=(2,4),curve_info=info))
        self.assertAlmostEqual(self.animation_poses('graph','motion')[2][0],3.125,delta=POSITION_TOLERANCE)
        info='"defaultCurveType" "int" "1542" "maxvalue" "float" "100" "useEdgeInfo" "bool" "true" "defaultEdgeZeroValue" "float" "7" "rightEdgeTime" "time" "0.4"'
        self.dependency_compile(log_fixture(kind='Float',values=(0,4),curve_info=info),name='cutoff')
        self.assertAlmostEqual(self.animation_poses('cutoff','motion')[2][0],7,delta=POSITION_TOLERANCE)

    def test_dmx_vector_curves_use_time_normalization_only_for_normalizex(self):
        for mode,wanted in [(0,2.8046875),(1,2.8984375),(12,2.8046875),(13,2.8046875)]:
            text=log_fixture(times=(-10000,0,10000,30000),values=[(v,2*v,-v) for v in (1,4,-2,6)],
                             curve_types=[mode*257]*4,curve_info='')
            self.dependency_compile(text,name='vector'+str(mode))
            pose=self.animation_poses('vector'+str(mode),'motion')[1]
            for actual,expected in zip(pose[:3],(wanted,2*wanted,-wanted)):self.assertAlmostEqual(actual,expected,delta=POSITION_TOLERANCE)

    def test_dmx_curve_default_edge_preserves_float_second_time_precision(self):
        # The reference converts ticks to float seconds before differencing.
        # Its implicit right edge at 1.0001 seconds creates a large tangent;
        # exact double tick arithmetic incorrectly shifts this peak by 0.636.
        text=log_fixture(times=(0,2000,6500,10000),values=[(0,0,0),(10,-3,5),(-3,8,9),(15,2,-4)],
                         curve_types=[257]*4,curve_info='',fps=20)
        self.dependency_compile(text)
        pose=self.animation_poses('graph','motion')[18]
        for actual,wanted in zip(pose[:3],(3836.244141,513.820496,-1021.001953)):
            self.assertAlmostEqual(actual,wanted,delta=.01)

    def test_dmx_quaternion_curve_easing_and_spline_modes(self):
        for mode,wanted in [(2,math.sin(math.pi/8)*math.pi/2),(3,(1-math.cos(math.pi/8))*math.pi/2),(4,.15625*math.pi/2),(5,math.pi/8),(7,math.pi/8),(10,math.pi/8),(15,0)]:
            text=log_fixture(kind='Quaternion',values=[(0,0,0,1),(0,0,math.sqrt(.5),math.sqrt(.5))],
                             curve_types=[mode*257]*2,curve_info='')
            self.dependency_compile(text,name='quaternion'+str(mode))
            self.assertAlmostEqual(self.animation_poses('quaternion'+str(mode),'motion')[1][5],wanted,delta=.002)

    def test_dmx_compressed_vector_runs_scales_base_and_interpolation(self):
        runs=[ [([0,8],3),([-4,2],2)], [([2],5)], [([-1,3],3),([1,-3],2)] ]
        blob=compressed_log_blob([],scale=(.5,-2,.25),base=(1,4,-2),runs=runs)
        self.dependency_compile(log_fixture(times=(0,2500,5000,7500,10000),compressed=blob,fps=8))
        poses=self.animation_poses('graph','motion');self.assertEqual(len(poses),9)
        expected=[(1,0,-2.25),(3,0,-1.75),(5,0,-1.25),(5,0,-1.25),(5,0,-1.25),(2,0,-1.5),(-1,0,-1.75),(.5,0,-2.25),(2,0,-2.75)]
        for pose,target in zip(poses,expected):
            for actual,wanted in zip(pose[:3],target):self.assertAlmostEqual(actual,wanted,delta=POSITION_TOLERANCE)

    def test_dmx_compressed_quaternion_decodes_radian_euler_and_curves(self):
        blob=compressed_log_blob([(0,0,0),(0,0,2),(0,0,4)],scale=(.1,.1,math.pi/8),base=(0,0,-math.pi/4))
        self.dependency_compile(log_fixture(kind='Quaternion',times=(0,5000,10000),compressed=blob,
                                          curve_types=[514]*3,curve_info=''))
        poses=self.animation_poses('graph','motion')
        for actual,wanted in zip([p[5] for p in poses],[-math.pi/4,(-1+math.sqrt(.5))*math.pi/4,0,math.sqrt(.5)*math.pi/4,math.pi/4]):
            self.assertAlmostEqual(actual,wanted,delta=.002)

    def test_dmx_compressed_runs_cross_255_key_boundary(self):
        samples=[(3,-2,7)]*255+[(10,-4,0),(-10,4,1)]+[(5,0,-5)]*3
        self.dependency_compile(log_fixture(times=[i*100 for i in range(260)],compressed=compressed_log_blob(samples),fps=100,duration=2.59))
        poses=self.animation_poses('graph','motion');self.assertEqual(len(poses),260)
        for frame in [0,254,255,256,257,259]:
            for actual,wanted in zip(poses[frame][:3],samples[frame]):self.assertAlmostEqual(actual,wanted,delta=POSITION_TOLERANCE)

    def test_dmx_corrupt_compressed_logs_fail_and_keep_existing_output(self):
        valid=compressed_log_blob([(0,0,0),(2,3,4)])
        text=log_fixture(compressed=valid);self.dependency_compile(text);before=self.mdl('graph')
        corrupt=[(valid[:20],'header'),(valid[:-1],'offsets'),(valid+b'\0\0','trailing'),
                 (valid[:24]+struct.pack('<I',31)+valid[28:],'offsets'),
                 (valid[:32]+b'\0'+valid[33:],'run counts'),
                 (valid[:32]+b'\2\1'+valid[34:],'run counts'),
                 (valid[:32]+b'\1\3'+valid[34:],'run counts'),
                 (struct.pack('<f',float('nan'))+valid[4:],'non-finite'),
                 (valid[:12]+struct.pack('<f',float('inf'))+valid[16:],'non-finite')]
        for blob,message in corrupt:
            with self.subTest(message=message):
                self.assertIn(message,self.dependency_compile(log_fixture(compressed=blob),success=False))
                self.assertEqual(before,self.mdl('graph'))
        self.assertIn('require Vector3 or Quaternion',self.dependency_compile(log_fixture(kind='Float',compressed=valid),success=False))
        self.assertIn('also contains values',self.dependency_compile(log_fixture(values=[(0,0,0),(0,0,0)],compressed=valid),success=False))
        self.assertIn('attribute type',self.dependency_compile(text.replace('"compressed" "binary"','"compressed" "string"'),success=False))

    def test_dmx_corrupt_curve_metadata_fails(self):
        for info,curves,message in [('"defaultCurveType" "int" "16"',None,'unsupported DMX curve'),
                                   ('',[-1,0],'unsupported DMX curve'),('',[1542],'count mismatch'),
                                   ('"minvalue" "float" "2" "maxvalue" "float" "1"',None,'value bounds'),
                                   ('"defaultCurveType" "float" "6"',None,'invalid curve field'),
                                   ('"leftEdgeValue" "vector3" "1 2 3"',None,'edge value type mismatch')]:
            self.assertIn(message,self.dependency_compile(log_fixture(kind='Float',values=(0,1),curve_types=curves,curve_info=info),success=False))
        for kind,values in [('Vector3',[(0,0,0),(1,2,3)]),('Quaternion',[(0,0,0,1),(0,0,0,1)])]:
            self.assertIn('exponential-decay',self.dependency_compile(log_fixture(kind=kind,values=values,curve_info='"defaultCurveType" "int" "3598"'),success=False))

    def test_dmx_dependency_integer_step_and_order_independent_evaluation(self):
        text=animation_fixture().replace('DmeFloatLog','DmeIntLog').replace('"values" "float_array"','"values" "int_array"')
        text=text.replace(', "element" "dd200000-0000-0000-0000-00000000000c"','')
        text=text.replace('"values" "int_array" [ "0", "4" ]','"values" "int_array" [ "0", "8" ]')
        # Integer logs hold their previous value. Reverse element storage order
        # to ensure dependency ordering does not rely on textual operator order.
        lines=text.splitlines();text='\n'.join(lines[:2]+list(reversed(lines[2:])))+'\n'
        self.dependency_compile(text)
        poses=self.animation_poses('graph','motion')
        for p,x in zip(poses,[4,4,4,4,19]):self.assertAlmostEqual(p[0],x,delta=.01)

    def test_dmx_dependency_inactive_clip_operators_do_not_change_pose(self):
        d=Document();text=animation_fixture()
        text=text.replace(d.elements('animations',[7]),d.elements('animations',[500]))
        d.element(500,'DmeChannelsClip','rest',f'"frameRate" "int" "4" "timeFrame" {d.ref(8)} '+d.elements('channels',[]))
        text+='\n'.join(d.rows)
        self.dependency_compile(text)
        poses=self.animation_poses('graph','motion');self.assertEqual(len(poses),5)
        for pose in poses:
            for component in pose:self.assertAlmostEqual(component,0,delta=.01)

    def test_dmx_dependency_conflicting_active_writers_fail(self):
        d=Document();text=animation_fixture()
        text=text.replace(d.elements('channels',[9]),d.elements('channels',[9,501]))
        d.element(501,'DmeChannel','duplicate',f'"toElement" {d.ref(20)} "toAttribute" "string" "value" "log" {d.ref(10)}')
        self.assertIn('multiple animation writers',self.dependency_compile(text+'\n'.join(d.rows),success=False))

    def test_dmx_dependency_unknown_operator_reference_input_fails(self):
        d=Document();d.element(700,'DmeUnsupportedRigOperator','unsupported',f'"input" {d.ref(701)}')
        d.element(701,'DmeAttributeReference','reference',f'"element" {d.ref(20)} "attribute" "string" "value"')
        self.assertIn('unsupported connected operator',self.dependency_compile(animation_fixture()+'\n'.join(d.rows),success=False))

    def test_dmx_dependency_unknown_operator_cycle_and_bad_log_fail(self):
        text=animation_fixture()
        self.assertIn('unsupported',self.dependency_compile(text.replace('DmeExpressionOperator','DmeUnknownOperator'),success=False))
        # Feed expression.result back into expression.value through connection0.
        cycle=text.replace('"element" "element" "dd200000-0000-0000-0000-000000000014" "attribute" "string" "value"',
                           '"element" "element" "dd200000-0000-0000-0000-000000000015" "attribute" "string" "result"')
        cycle=cycle.replace('"toElement" "element" "dd200000-0000-0000-0000-000000000014" "toAttribute" "string" "value"',
                            '"toElement" "element" "dd200000-0000-0000-0000-000000000015" "toAttribute" "string" "seed"')
        cycle=cycle.replace('"result" "float" "0" "expr"','"result" "float" "0" "seed" "float" "0" "expr"')
        cycle=cycle.replace('max(value * 2, 1) + 3','max(value * 2, 1) + 3 + seed')
        self.assertIn('cyclic animation dependency',self.dependency_compile(cycle,success=False))
        self.assertIn('count mismatch',self.dependency_compile(text.replace('"values" "float_array" [ "0", "4" ]','"values" "float_array" [ "0" ]'),success=False))

    def test_dmx_dependency_error_keeps_previous_output(self):
        text=animation_fixture();self.dependency_compile(text);before=self.mdl('graph')
        self.dependency_compile(text.replace('max(value * 2, 1) + 3','unsupported(value)'),success=False)
        self.assertEqual(before,self.mdl('graph'))

    def test_dmx_dependency_extreme_times_and_frame_rate_are_bounded(self):
        text=animation_fixture()
        long_clip=text.replace('"frameRate" "int" "4"','"frameRate" "int" "10000"')
        long_clip=long_clip.replace('"duration" "time" "1"','"duration" "int" "2147483647"')
        self.assertIn('frame index out of range',self.dependency_compile(long_clip,success=False))
        long_clip=long_clip.replace('"duration" "int" "2147483647"','"duration" "int" "2147483646"')
        self.assertIn('exceeds 100000 frames',self.dependency_compile(long_clip,success=False))
        bad_rate=text.replace('"frameRate" "int" "4"','"frameRate" "float" "1e30"')
        self.assertIn('invalid animation frame rate',self.dependency_compile(bad_rate,success=False))
        # The valid interval spans the entire signed timestamp range. Its
        # difference must not overflow before interpolation near the midpoint.
        wide_keys=text.replace(', "element" "dd200000-0000-0000-0000-00000000000c"','')
        wide_keys=wide_keys.replace('"times" "int_array" [ "0", "10000" ]',
                                    '"times" "int_array" [ "-2147483648", "2147483647" ]')
        self.dependency_compile(wide_keys)
        for pose in self.animation_poses('graph','motion'):
            self.assertAlmostEqual(pose[0],7,delta=.01)
