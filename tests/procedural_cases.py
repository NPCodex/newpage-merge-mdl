"""Authored AxisInterp/Twist fixtures with independent quaternion/world-pose checks."""
import math
import struct
from dmx_dependency_cases import Document


def add(a,b): return tuple(x+y for x,y in zip(a,b))
def scale(a,s): return tuple(x*s for x in a)
def dot(a,b): return sum(x*y for x,y in zip(a,b))
def cross(a,b): return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
def unit(v): return scale(v,1/math.sqrt(dot(v,v)))
def inverse(q): return (-q[0],-q[1],-q[2],q[3])
def multiply(a,b):
    xyz=add(add(scale(a[:3],b[3]),scale(b[:3],a[3])),cross(a[:3],b[:3]))
    return (*xyz,a[3]*b[3]-dot(a[:3],b[:3]))
def rotate(q,v): return multiply(multiply(q,(*v,0)),inverse(q))[:3]
def euler(v):
    x,y,z=(a/2 for a in v)
    return multiply(multiply((0,0,math.sin(z),math.cos(z)),(0,math.sin(y),0,math.cos(y))),(math.sin(x),0,0,math.cos(x)))
def compose(a,b): return (add(a[0],rotate(a[1],b[0])),multiply(a[1],b[1]))
def inverse_pose(p):
    q=inverse(p[1]);return (rotate(q,scale(p[0],-1)),q)


def reference_twist(parent,child_position,child,base,up,weight,target,inverse_mode):
    if dot(child_position,child_position)<1e-12: return target
    axis=unit(child_position)
    relative=multiply(inverse(base),parent if inverse_mode else child)
    rotated_axis=rotate(relative if inverse_mode else inverse(base),axis)
    rotated_up=rotate(relative,up)
    if 1-abs(dot(rotated_axis,up))<1e-6 or 1-abs(dot(rotated_axis,rotated_up))<1e-6:return target
    a=unit(add(up,scale(rotated_axis,-dot(up,rotated_axis))))
    b=unit(add(rotated_up,scale(rotated_axis,-dot(rotated_up,rotated_axis))))
    angle=math.atan2(dot(cross(a,b),rotated_axis),dot(a,b))
    angle*=weight-(1 if inverse_mode else 0)
    return multiply((*scale(axis,math.sin(angle/2)),math.cos(angle/2)),target)


NAMES=['root','parent','child','twistA','twistB','other']
PARENTS=[-1,0,1,1,1,0]
POSITIONS=[(1,2,3),(2,-1,4),(6,2,3),(2,0,0),(4,0,0),(-2,5,1)]
ROTATIONS=[(.2,.1,-.3),(.1,.25,.05),(-.2,.1,.15),(.3,-.1,.2),(-.1,.2,.3),(-.15,.4,.2)]


def skeletal_smd(names,parents,positions,rotations,frames=None,triangles=True):
    rows=['version 1','nodes']+[f'{i} "{n}" {parents[i]}' for i,n in enumerate(names)]+['end','skeleton']
    for f,pose in enumerate(frames or [rotations]):
        rows+=['time '+str(f)]+[f'{i} '+ ' '.join(map(str,(*positions[i],*pose[i]))) for i in range(len(names))]
    rows+=['end']
    if triangles:rows+=['triangles','material','0 0 0 0 0 0 1 0 0','0 1 0 0 0 0 1 1 0','0 0 1 0 0 0 1 0 1','end']
    return '\n'.join(rows)+'\n'


def twist_fixture(inverse_mode=False,positions=None,rotations=None,parents=None,parent_index=1):
    positions=positions or POSITIONS;rotations=rotations or ROTATIONS
    parents=parents or PARENTS
    d=Document()
    d.element(1,'DmElement','rig',f'"skeleton" {d.ref(2)} '+d.elements('constraints',[100]))
    d.element(2,'DmeModel','model',d.elements('children',[10]))
    for i,name in enumerate(NAMES):
        d.element(10+i,'DmeJoint',name,f'"transform" {d.ref(30+i)} '+d.elements('children',[10+j for j,p in enumerate(parents) if p==i]))
        d.element(30+i,'DmeTransform',name,'"position" "vector3" "'+' '.join(map(str,positions[i]))+'" "orientation" "quaternion" "'+' '.join(map(str,euler(rotations[i])))+'"')
    d.element(100,'DmeRigTwistConstraintOperator','twist',d.elements('targets',[101,102])+d.elements('twistJoints',[103,104])+
              f'"inverse" "bool" "{str(inverse_mode).lower()}" "upVector" "vector3" "0 1 0" '+
              '"parentBindRotation" "quaternion" "'+' '.join(map(str,euler(rotations[parent_index])))+'" '+
              '"childBindRotation" "quaternion" "'+' '.join(map(str,euler(rotations[2])))+'"')
    for i,bone in enumerate([10+parent_index,12]):d.element(101+i,'DmeConstraintTarget','target',f'"target" {d.ref(bone)} "targetWeight" "float" "1"')
    for i,(bone,weight) in enumerate([(13,.25),(14,.75)]):
        d.element(103+i,'DmeRigTwistSlave','slave',f'"target" {d.ref(bone)} "weight" "float" "{weight}" "orientation" "quaternion" "'+' '.join(map(str,euler(rotations[bone-10])))+'"')
    return d.text()


def axis_fixture():
    return ('version 1\nproceduralbones\nbone "helper" "root" "driver" "root" 1\nbasepos 1 2 3\n'+
            '\n'.join(f'axis {i} {i*2} {i*3} {i*4} {i*5} {i*7} {i*11}' for i in range(6))+'\nend\n')


class ProceduralCases:
    def all_animation_poses(self,model,animation):
        self.animation_poses(model,animation)
        path=next(p for p in (self.root/'decompiled').rglob(animation+'.smd') if any(a.name==model for a in p.parents))
        names={};parents={};poses=[];section=''
        for row in path.read_text().splitlines():
            if row.strip() in ['nodes','skeleton','end']:section=row.strip();continue
            if section=='nodes':
                f=row.split('"');names[int(f[0])]=f[1];parents[int(f[0])]=int(f[2])
            elif section=='skeleton':
                f=row.split()
                if f[0]=='time':poses.append({})
                elif len(f)==7:poses[-1][int(f[0])]=tuple(map(float,f[1:]))
        worlds=[]
        for frame in poses:
            result={}
            for i in sorted(frame):
                p=frame[i];local=(p[:3],euler(p[3:]))
                # The decompiler removes the default +90 model yaw even when
                # this fixture explicitly compiled with $origin ... -90.
                result[i]=compose(result[parents[i]],local) if parents[i]>=0 else compose(((0,0,0),euler((0,0,math.pi/2))),local)
            worlds.append({names[i]:p for i,p in result.items()})
        return worlds

    def axis_compile(self,text=None,qc='',success=True):
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        self.write('axis.smd',skeletal_smd(['root','driver','helper'],[-1,0,0],[(0,0,0)]*3,[(0,0,0)]*3))
        self.write('axis.bones',axis_fixture() if text is None else text)
        return self.scene_qc('$modelname axis\n$origin 0 0 0 -90\n'+qc+'$body m axis.smd\n$proceduralbones axis.bones\n',success=success)

    def test_axisinterp_native_six_poses_and_unweighted_retention(self):
        self.axis_compile()
        data,bones=self.csgo_bone_table('axis');self.assertEqual(set(bones),{'root','driver','helper'})
        b=bones['helper'][1];flags,kind,offset=struct.unpack_from('<3i',data,b+160)
        self.assertTrue(flags&4);self.assertEqual(kind,1)
        at=b+offset;self.assertEqual(struct.unpack_from('<2i',data,at),(bones['driver'][0],0))
        for i in range(6):
            self.assertEqual(struct.unpack_from('<3f',data,at+8+i*12),(1+i*2,2+i*3,3+i*4))
            q=struct.unpack_from('<4f',data,at+80+i*16)
            self.assertAlmostEqual(abs(dot(q,euler([math.radians(i*k) for k in (5,7,11)]))),1,places=5)

    def test_axisinterp_scale_and_rename(self):
        self.axis_compile(qc='$scale 2\n$renamebone driver control\n$renamebone helper corrective\n')
        data,bones=self.csgo_bone_table('axis');b=bones['corrective'][1];at=b+struct.unpack_from('<i',data,b+168)[0]
        self.assertEqual(struct.unpack_from('<i',data,at)[0],bones['control'][0])
        self.assertEqual(struct.unpack_from('<3f',data,at+8+5*12),(22,34,46))

    def test_axisinterp_invalid_slots_axis_and_dependency_fail(self):
        for text,wanted in [(axis_fixture().replace('axis 5 ','axis 4 '),'unique index'),
                            (axis_fixture().replace('"root" 1','"root" 4'),'axis 1..3'),
                            (axis_fixture().replace('axis 5 10 15 20 25 35 55\n',''),'six axis poses'),
                            (axis_fixture().replace('"driver" "root"','"absent" "root"'),'missing helper/control'),
                            (axis_fixture().replace('axis 0 0 0 0','axis 0 nan 0 0'),'six floats')]:
            with self.subTest(wanted=wanted):self.assertIn(wanted,self.axis_compile(text=text,success=False))

    def test_axisinterp_explicit_unsupported_hierarchy_fails(self):
        self.assertIn('authored parent differs',self.axis_compile(qc='$hierarchy helper driver\n',success=False))
        self.assertIn('$centerbonesonverts',self.axis_compile(qc='$centerbonesonverts\n',success=False))
        self.assertIn('control realignment cannot preserve',self.axis_compile(qc='$forcerealign driver rotate 0 0 31\n',success=False))
        self.assertIn('control-parent realignment',self.axis_compile(qc='$forcerealign root rotate 0 0 31\n',success=False))

    def test_axisinterp_cardinal_realign_and_animation_basis_override(self):
        self.axis_compile(qc='$forcerealign driver rotate 0 0 90\n')
        data,bones=self.csgo_bone_table('axis');b=bones['helper'][1];at=b+struct.unpack_from('<i',data,b+168)[0]
        self.assertEqual(struct.unpack_from('<i',data,at+4)[0],1)
        # Selecting final local Y negates the sampled source local X column;
        # the parent-space positive X/Y slots therefore use old negative X/Y.
        self.assertEqual(struct.unpack_from('<3f',data,at+8),(3,5,7))
        self.assertEqual(struct.unpack_from('<3f',data,at+8+2*12),(7,11,15))
        self.assertIn('animation bone-basis overrides',self.axis_compile(qc='$forcerealign driver rotate 0 0 90\n$sequence motion axis.smd nobonerealign\n',success=False))

    def test_axisinterp_compiled_root_control_marker_preserves_model_axes(self):
        authored=axis_fixture().replace('"driver" "root" 1','"root" "-" 1')
        for compiled,expected in [(False,(7,11,15)),(True,(1,2,3))]:
            text=authored.replace('basepos 1 2 3',('type compiled\n' if compiled else '')+'basepos 1 2 3')
            self.axis_compile(text=text,qc='$origin 0 0 0 0\n')
            data,bones=self.csgo_bone_table('axis');b=bones['helper'][1];at=b+struct.unpack_from('<i',data,b+168)[0]
            self.assertEqual(struct.unpack_from('<2i',data,at),(bones['root'][0],0))
            self.assertEqual(struct.unpack_from('<3f',data,at+8),expected)

    def twist_compile(self,inverse_mode=False,qc='',positions=None,rotations=None,text=None,success=True,before_rig='',after_rig='',seqopts=''):
        positions=positions or POSITIONS;rotations=rotations or ROTATIONS
        frames=[list(rotations),list(rotations)]
        frames[1][1]=(.8,-.3,.5);frames[1][2]=(.5,.6,-.4)
        self.write('twist.dmx',twist_fixture(inverse_mode,positions,rotations) if text is None else text)
        self.write('twist.smd',skeletal_smd(NAMES,PARENTS,positions,rotations))
        self.write('motion.smd',skeletal_smd(NAMES,PARENTS,positions,rotations,frames,False))
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        output=self.scene_qc('$modelname twist\n$origin 0 0 0 -90\n'+qc+'$body m twist.smd\n'+before_rig+'$datamodeljoints twist.dmx proceduralbones\n'+after_rig+'$sequence motion motion.smd '+seqopts+'\n',success=success)
        return frames,output

    def check_twist_reference(self,inverse_mode=False,qc='',factor=1,renamed=False,aligned=False,yaw=0,seqopts=''):
        frames,_=self.twist_compile(inverse_mode,qc,seqopts=seqopts)
        worlds=self.all_animation_poses('twist','motion')
        data,bones=self.csgo_bone_table('twist')
        final_bind={}
        for name,(index,b) in sorted(bones.items(),key=lambda pair:pair[1][0]):
            parent=struct.unpack_from('<i',data,b+4)[0]
            pose=(struct.unpack_from('<3f',data,b+32),struct.unpack_from('<4f',data,b+44))
            final_bind[index]=compose(final_bind[parent],pose) if parent>=0 else pose
        for f,rotations in enumerate(frames):
            parent_world=compose((scale(POSITIONS[0],factor),euler(rotations[0])),(scale(POSITIONS[1],factor),euler(rotations[1])))
            for i,weight in [(3,.25),(4,.75)]:
                expected=reference_twist(euler(rotations[1]),POSITIONS[2],euler(rotations[2]),euler(ROTATIONS[1 if inverse_mode else 2]),(0,1,0),weight,euler(ROTATIONS[i]),inverse_mode)
                wanted=compose(parent_world,(scale(POSITIONS[i],factor),expected))
                name='renamed' if renamed and i==3 else NAMES[i]
                if aligned:
                    original_bind=compose(compose((scale(POSITIONS[0],factor),euler(ROTATIONS[0])),(scale(POSITIONS[1],factor),euler(ROTATIONS[1]))),(scale(POSITIONS[i],factor),euler(ROTATIONS[i])))
                    correction=compose(inverse_pose(original_bind),final_bind[bones[name][0]])
                    wanted=compose(wanted,correction)
                wanted=compose(((0,0,0),euler((0,0,yaw))),wanted)
                actual=worlds[f][name]
                for a,b in zip(actual[0],wanted[0]):self.assertAlmostEqual(a,b,delta=.025)
                self.assertAlmostEqual(abs(dot(actual[1],wanted[1])),1,delta=.0002)
        self.assertLess(abs(dot(worlds[0]['twistB'][1],worlds[1]['twistB'][1])),.99)
        for name in ['renamed' if renamed else 'twistA','twistB']:
            flags,kind,offset=struct.unpack_from('<3i',data,bones[name][1]+160)
            self.assertFalse(flags&4);self.assertEqual((kind,offset),(0,0))

    def test_twist_forward_bakes_reference_nontrivial_rotations(self):self.check_twist_reference()
    def test_twist_inverse_bakes_reference_nontrivial_rotations(self):self.check_twist_reference(True)
    def test_twist_reparent_rename_and_scale_preserve_world_solution(self):
        self.check_twist_reference(True,'$scale 2\n$renamebone twistA renamed\n$hierarchy renamed other\n$bonealwayssetup other\n',2,True)

    def test_twist_reparent_driver_and_arbitrary_realign_preserve_skinning(self):
        self.check_twist_reference(True,'$hierarchy parent other\n$bonealwayssetup other\n$forcerealign parent rotate 17 23 29\n$forcerealign child rotate -11 8 22\n$forcerealign twistA rotate 5 -9 12\n',aligned=True)

    def test_twist_model_rotation_and_animation_realign_opt_out(self):
        self.check_twist_reference(True,'$origin 0 0 0 25\n',yaw=math.radians(115))
        self.check_twist_reference(False,'$forcerealign parent rotate 17 23 29\n$forcerealign twistA rotate 5 -9 12\n',seqopts='nobonerealign')

    def test_twist_root_parent_removes_only_model_rotation(self):
        parents=[-1,0,0,0,0,0]
        frames=[list(ROTATIONS),list(ROTATIONS)];frames[1][0]=(.8,-.3,.5);frames[1][2]=(.5,.6,-.4)
        for inv in [False,True]:
            self.write('root_twist.smd',skeletal_smd(NAMES,parents,POSITIONS,ROTATIONS))
            self.write('root_motion.smd',skeletal_smd(NAMES,parents,POSITIONS,ROTATIONS,frames,False))
            self.write('root_twist.dmx',twist_fixture(inv,parents=parents,parent_index=0))
            self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
            self.scene_qc('$modelname root_twist\n$origin 0 0 0 25\n$body m root_twist.smd\n$datamodeljoints root_twist.dmx proceduralbones\n$sequence motion root_motion.smd\n')
            worlds=self.all_animation_poses('root_twist','motion')
            for f,rots in enumerate(frames):
                result=reference_twist(euler(rots[0]),POSITIONS[2],euler(rots[2]),euler(ROTATIONS[0 if inv else 2]),(0,1,0),.25,euler(ROTATIONS[3]),inv)
                expected=compose(((0,0,0),euler((0,0,math.radians(115)))),compose((POSITIONS[0],euler(rots[0])),(POSITIONS[3],result)))
                for a,b in zip(worlds[f]['twistA'][0],expected[0]):self.assertAlmostEqual(a,b,delta=.025)
                self.assertAlmostEqual(abs(dot(worlds[f]['twistA'][1],expected[1])),1,delta=.0002)

    def test_twist_import_and_animation_scale_are_applied_once(self):
        for body_scale,rig_scale,anim_scale,option,expected_parent,expected_target in [
            (2,2,2,'scale 3',6,6),(2,3,4,'',4,3),(2,2,2,'ignorescale',1,1)]:
            with self.subTest(option=option,rig_scale=rig_scale):
                frames,_=self.twist_compile(qc=f'$scale {body_scale}\n',before_rig=f'$scale {rig_scale}\n',
                                            after_rig=f'$scale {anim_scale}\n',seqopts=option)
                worlds=self.all_animation_poses('twist','motion')
                for f,rots in enumerate(frames):
                    parent=compose((scale(POSITIONS[0],expected_parent),euler(rots[0])),(scale(POSITIONS[1],expected_parent),euler(rots[1])))
                    expected=compose(parent,(scale(POSITIONS[3],expected_target),(0,0,0,1)))[0]
                    for a,b in zip(worlds[f]['twistA'][0],expected):self.assertAlmostEqual(a,b,delta=.03)

    def test_twist_zero_axis_uses_base_pose(self):
        positions=list(POSITIONS);positions[2]=(0,0,0)
        frames,_=self.twist_compile(positions=positions)
        worlds=self.all_animation_poses('twist','motion')
        for f,rotations in enumerate(frames):
            expected=multiply(multiply(euler(rotations[0]),euler(rotations[1])),euler(ROTATIONS[3]))
            self.assertAlmostEqual(abs(dot(worlds[f]['twistA'][1],expected)),1,delta=.0002)
        positions=list(POSITIONS);positions[2]=(0,6,0)
        rotations=list(ROTATIONS);rotations[2]=(0,0,0)
        frames,_=self.twist_compile(positions=positions,rotations=rotations)
        worlds=self.all_animation_poses('twist','motion')
        for f,pose in enumerate(frames):
            expected=multiply(multiply(euler(pose[0]),euler(pose[1])),euler(rotations[3]))
            self.assertAlmostEqual(abs(dot(worlds[f]['twistA'][1],expected)),1,delta=.0002)

    def test_twist_malformed_cycle_and_runtime_dependency_fail(self):
        text=twist_fixture().replace('"weight" "float" "0.25"','"weight" "float" "nan"')
        self.assertIn('invalid Twist slave',self.twist_compile(text=text,success=False)[1])
        for field,original in [('childBindRotation',euler(ROTATIONS[2])),('orientation',euler(ROTATIONS[3]))]:
            with self.subTest(overflow=field):
                text=twist_fixture().replace(f'"{field}" "quaternion" "'+' '.join(map(str,original))+'"',f'"{field}" "quaternion" "1e30 0 0 1"')
                self.assertIn('invalid Twist',self.twist_compile(text=text,success=False)[1])
        with self.subTest(overflow='upVector'):
            text=twist_fixture().replace('"upVector" "vector3" "0 1 0"','"upVector" "vector3" "1e30 1 0"')
            self.assertIn('invalid Twist',self.twist_compile(text=text,success=False)[1])
        self.assertIn('cyclic bone dependency',self.twist_compile(qc='$hierarchy child twistA\n',success=False)[1])
        self.assertIn('$centerbonesonverts',self.twist_compile(qc='$centerbonesonverts\n',success=False)[1])
