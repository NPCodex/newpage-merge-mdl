"""Rotation/IK and mixed DMX rig graphs, checked in decompiled world space."""
import math
import struct
from dmx_dependency_cases import Document
from procedural_cases import skeletal_smd, rotate, dot


RIG_NAMES=['root','upper','middle','end','target','pole','rot','follow']
RIG_PARENTS=[-1,0,1,2,0,0,0,0]
RIG_POSITIONS=[(0,0,0),(0,0,0),(2,0,0),(2,0,0),(2,2,0),(0,0,1),(0,0,0),(0,0,0)]


def complete_rig(*, animated=False, bad_axis=False, bad_chain=False, cycle=False):
    d=Document()
    d.element(1,'DmElement','rig',f'"skeleton" {d.ref(2)} '+d.elements('constraints',[100,110,120])+(f' "animationList" {d.ref(200)}' if animated else ''))
    d.element(2,'DmeModel','model',d.elements('children',[10])+d.elements('jointList',range(10,18)))
    for i,name in enumerate(RIG_NAMES):
        d.element(10+i,'DmeJoint',name,f'"transform" {d.ref(30+i)} '+d.elements('children',[10+j for j,p in enumerate(RIG_PARENTS) if p==i]))
        d.element(30+i,'DmeTransform',name,'"position" "vector3" "'+' '.join(map(str,RIG_POSITIONS[i]))+'" "orientation" "quaternion" "0 0 0 1"')
    # Point is intentionally declared before the IK that produces its input.
    d.element(100,'DmeRigPointConstraintOperator','follow',f'"slave" {d.ref(101)} '+d.elements('targets',[102]))
    d.element(101,'DmeConstraintSlave','followSlave',f'"target" {d.ref(17)} "position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    d.element(102,'DmeConstraintTarget','endTarget',f'"target" {d.ref(13)} "targetWeight" "float" "1"')
    d.element(110,'DmeRigRotationConstraintOperator','rotation',f'"slave" {d.ref(111)} '+d.array('axies','vector3',['0 0 0' if bad_axis else '0 0 1'])+d.array('rotations','float',[90]))
    d.element(111,'DmeConstraintSlave','rotationSlave',f'"target" {d.ref(16)} "orientation" "quaternion" "0 0 0 1"')
    d.element(120,'DmeRigIKConstraintOperator','ik',f'"startJoint" {d.ref(121)} "midJoint" {d.ref(122)} "endJoint" {d.ref(123)} "pvTarget" {d.ref(15)} '+d.elements('targets',[124])+' "startOffset" "quaternion" "0 0 0 1" "midOffset" "quaternion" "0 0 0 1"')
    for i,target in enumerate([11,16 if bad_chain else 12,13]):d.element(121+i,'DmeConstraintSlave','ikJoint',f'"target" {d.ref(target)} "orientation" "quaternion" "0 0 0 1"')
    d.element(124,'DmeConstraintTarget','ikTarget',f'"target" {d.ref(17 if cycle else 14)} "targetWeight" "float" "1"')
    if animated:
        d.element(200,'DmeAnimationList','animations',d.elements('animations',[201]))
        d.element(201,'DmeChannelsClip','motion',f'"frameRate" "int" "4" "timeFrame" {d.ref(202)} '+d.elements('channels',[203,206]))
        d.element(202,'DmeTimeFrame','time','"start" "time" "0" "duration" "time" "1" "scale" "float" "1"')
        d.element(203,'DmeChannel','turn',f'"toElement" {d.ref(110)} "toAttribute" "string" "rotations" "toIndex" "int" "0" "log" {d.ref(204)}')
        d.element(204,'DmeFloatLog','turnLog',d.elements('layers',[205]))
        d.element(205,'DmeFloatLogLayer','turnLayer',d.array('times','int',[0,10000])+d.array('values','float',[0,90]))
        d.element(206,'DmeChannel','targetPosition',f'"toElement" {d.ref(34)} "toAttribute" "string" "position" "log" {d.ref(207)}')
        d.element(207,'DmeVector3Log','targetLog',d.elements('layers',[208]))
        d.element(208,'DmeVector3LogLayer','targetLayer',d.array('times','int',[0,10000])+d.array('values','vector3',['2 0 0','2 2 0']))
    return d.text()


class ProceduralScopeCases:
    def scope_rig_compile(self,text=None,*,animated=False,qc='',success=True,positions=None):
        self.write('gameinfo.txt','GameInfo { FileSystem { SteamAppId 730 } }')
        self.write('scope.smd',skeletal_smd(RIG_NAMES,RIG_PARENTS,positions or RIG_POSITIONS,[(0,0,0)]*8))
        self.write('scope.dmx',complete_rig(animated=animated) if text is None else text)
        return self.scene_qc('$modelname rigscope\n$origin 0 0 0 -90\n'+qc+'$body m scope.smd\n$datamodeljoints scope.dmx proceduralbones\n$sequence motion '+('scope.dmx' if animated else 'scope.smd')+'\n',success=success)

    def test_dmx_rotation_and_ik_external_rig_bake(self):
        self.scope_rig_compile()
        world=self.all_animation_poses('rigscope','motion')[0]
        for a,b in zip(world['end'][0],(2,2,0)):self.assertAlmostEqual(a,b,delta=.015)
        for a,b in zip(world['follow'][0],world['end'][0]):self.assertAlmostEqual(a,b,delta=.015)
        for a,b in zip(rotate(world['rot'][1],(1,0,0)),(0,1,0)):self.assertAlmostEqual(a,b,delta=.002)
        data,bones=self.csgo_bone_table('rigscope')
        for name in ['upper','middle','rot']:
            flags,kind=struct.unpack_from('<2i',data,bones[name][1]+160)
            self.assertFalse(flags&4);self.assertEqual(kind,0)

    def test_dmx_dynamic_rotation_and_ik_share_constraint_graph(self):
        self.scope_rig_compile(animated=True)
        frames=self.all_animation_poses('rigscope','motion');self.assertEqual(len(frames),5)
        for i,world in enumerate(frames):
            for a,b in zip(world['end'][0],(2,i*.5,0)):self.assertAlmostEqual(a,b,delta=.025)
            for a,b in zip(world['follow'][0],world['end'][0]):self.assertAlmostEqual(a,b,delta=.02)
            angle=math.pi*i/8
            for a,b in zip(rotate(world['rot'][1],(1,0,0)),(math.cos(angle),math.sin(angle),0)):self.assertAlmostEqual(a,b,delta=.003)

    def test_dmx_animated_weight_and_disjoint_writers_share_one_bone(self):
        d=Document();text=complete_rig(animated=True)
        text=text.replace(d.elements('channels',[203,206]),d.elements('channels',[203,206,209]))
        # Rotation owns follow.orientation, while Point owns follow.position.
        text=text.replace('"target" '+d.ref(16),'"target" '+d.ref(17))
        d.element(209,'DmeChannel','weight',f'"toElement" {d.ref(102)} "toAttribute" "string" "targetWeight" "log" {d.ref(210)}')
        d.element(210,'DmeFloatLog','weights',d.elements('layers',[211]))
        d.element(211,'DmeFloatLogLayer','weightLayer',d.array('times','int',[0,10000])+d.array('values','float',[0,1]))
        self.scope_rig_compile(text+'\n'.join(d.rows),animated=True)
        for i,world in enumerate(self.all_animation_poses('rigscope','motion')):
            weight=i/4
            for a,b in zip(world['follow'][0],(2*weight,i*.5*weight,0)):self.assertAlmostEqual(a,b,delta=.02)
            angle=math.pi*i/8
            for a,b in zip(rotate(world['follow'][1],(1,0,0)),(math.cos(angle),math.sin(angle),0)):self.assertAlmostEqual(a,b,delta=.003)

    def test_dmx_rig_authored_basis_survives_scale_realign_and_renames(self):
        self.scope_rig_compile(qc='$scale 2\n$realignbones\n$renamebone upper shoulder\n$renamebone rot twistdriver\n')
        world=self.all_animation_poses('rigscope','motion')[0]
        for a,b in zip(world['end'][0],(4,4,0)):self.assertAlmostEqual(a,b,delta=.025)
        self.assertIn('shoulder',world);self.assertIn('twistdriver',world)

    def test_dmx_rig_invalid_axes_chain_and_feedback_fail(self):
        for kwargs,wanted in [({'bad_axis':True},'rotation axis'),({'bad_chain':True},'two-bone chain'),({'cycle':True},'cyclic')]:
            with self.subTest(kwargs=kwargs):self.assertIn(wanted,self.scope_rig_compile(complete_rig(**kwargs),success=False))

    def test_dmx_ik_unreachable_targets_clamp_to_chain_length(self):
        text=complete_rig().replace('"position" "vector3" "2 2 0"','"position" "vector3" "20 0 0"')
        positions=list(RIG_POSITIONS);positions[4]=(20,0,0)
        self.scope_rig_compile(text,positions=positions)
        world=self.all_animation_poses('rigscope','motion')[0]
        for a,b in zip(world['end'][0],(4,0,0)):self.assertAlmostEqual(a,b,delta=.02)
