"""Black-box regressions from the v1.2.36 compiler input/timing audit."""
import os
import math
import struct
from dmx_dependency_cases import Document, log_fixture
from scene_integration_cases import fbx_bind_fixture, collada_curve_fixture


def animated_scale_fbx(dynamic=True):
    text=fbx_bind_fixture().replace('3,"Lcl Translation"','3,"Lcl Scaling"').replace('"AnimCurveNode::T"','"AnimCurveNode::S"')
    for start in (10,20):
        text=text.replace(f'"d|X", "Number", "", "A", {start}','"d|X", "Number", "", "A", 1').replace(f'Default: {start}','Default: 1')
    for axis in ('Y','Z'):text=text.replace(f'"d|{axis}", "Number", "", "A", 0',f'"d|{axis}", "Number", "", "A", 1')
    for old in ('10,14','20,22'):text=text.replace('a: '+old,'a: 1,'+('2' if dynamic else '1'))
    return text


def clip_collision(second='walk'):
    d=Document();text=log_fixture(values=[(1,0,0),(2,0,0)]).replace('"name" "string" "motion"','"name" "string" "Walk"')
    text=text.replace(d.elements('animations',[7]),d.elements('animations',[7,27]))
    d.element(27,'DmeChannelsClip',second,f'"frameRate" "int" "4" "timeFrame" {d.ref(8)} '+d.elements('channels',[29]))
    d.element(29,'DmeChannel','second',f'"toElement" {d.ref(4)} "toAttribute" "string" "position" "log" {d.ref(30)}')
    d.element(30,'DmeVector3Log','log2',d.elements('layers',[31]))
    d.element(31,'DmeVector3LogLayer','layer2',d.array('times','int',[0,10000])+d.array('values','vector3',['10 0 0','20 0 0']))
    return text+'\n'.join(d.rows)


class CompilerInputCases:
    def source_timing(self,name):
        data=self.mdl(name);index=struct.unpack_from('<i',data,184)[0]
        return struct.unpack_from('<f',data,index+8)[0],struct.unpack_from('<i',data,index+16)[0]

    def test_smd_all_numeric_records_reject_corruption_and_preserve_output(self):
        base=(self.root/'mesh.smd').read_text();self.scene_qc('$modelname guarded\n$body m mesh.smd\n');before=self.mdl('guarded')
        pairs=[('time 0','time'),('time 0','time OOPS'),('time 0','time 0garbage'),('time 0','time -1'),
               ('0 0 0 0 0 0 0\n','0 0 0 0 0 0 0oops\n'),('"root" -1','"root" -1oops'),('version 1','version 1oops'),
               ('1 "unused_child"','2147483647 "unused_child"'),('0 0 0 0 0 0 0\n','0 0 0 0 0 0 0 trailing\n'),('time 0','time 0\ntime 2147483647')]
        for old,new in pairs:
            with self.subTest(new=new):
                self.write('bad.smd',base.replace(old,new));output=self.scene_qc('$modelname guarded\n$body m bad.smd\n',success=False)
                self.assertRegex(output,r'bad\.smd:\d+:');self.assertEqual(self.mdl('guarded'),before)
        self.write('comments.smd',base.replace('time 0','time 0 // bind').replace('"unused_child" 0','"unused_child" 0 // child'))
        self.scene_qc('$modelname comments\n$body m comments.smd\n');self.assertEqual(self.mdl_bones('comments'),self.mdl_bones('guarded'))

    def test_vta_numeric_records_are_strict(self):
        base='version 1\nvertexanimation\ntime 0 # basis\n0 0 0 0 0 0 1\n1 1 0 0 0 0 1\n2 0 1 0 0 0 1\ntime 1\n0 0 0 1 0 0 1\nend\n'
        qc='$modelname face\n$model m mesh.smd {\nflexfile face.vta {\ndefaultflex frame 0\nflex smile frame 1\n}\nflexcontroller test range 0 1 strength\n%smile = strength\n}\n'
        self.write('face.vta',base);self.scene_qc(qc);before=self.mdl('face')
        for old,new in [('version 1','version 1oops'),('time 1','time 1garbage'),('time 1','time OOPS'),('time 1','time -1'),('0 0 0 1 0 0 1','0 0 0 1 0 0 1oops'),('0 0 0 0 0 0 1','2147483647 0 0 0 0 0 1')]:
            with self.subTest(new=new):
                self.write('face.vta',base.replace(old,new));output=self.scene_qc(qc,success=False)
                self.assertRegex(output,r'face\.vta:\d+:');self.assertEqual(self.mdl('face'),before)

    def test_dmx_clip_names_follow_case_insensitive_selection(self):
        qc='$modelname clips\n$body m mesh.smd\n$origin 0 0 0 -90\n$animationcullmethod none\n$sequence first motion.dmx blockname Walk\n$sequence second motion.dmx blockname Run\n'
        self.write('motion.dmx',clip_collision('Run'));self.scene_qc(qc);before=self.mdl('clips')
        self.assertAlmostEqual(math.dist(self.animation_poses('clips','first')[0][:3],(0,0,0)),1,places=2);self.assertAlmostEqual(math.dist(self.animation_poses('clips','second')[0][:3],(0,0,0)),10,places=2)
        for name in ('walk','WALK','bindpose'):
            self.write('motion.dmx',clip_collision(name));output=self.scene_qc(qc,success=False)
            self.assertIn('duplicate or reserved animation name',output);self.assertEqual(self.mdl('clips'),before)

    def test_dmx_skeleton_and_mesh_dag_cycles_and_depth_are_diagnostic(self):
        for mesh in (False,True):
            for mode in ('valid','cycle','depth','duplicate'):
                with self.subTest(mesh=mesh,mode=mode):
                    d=Document();d.element(1,'DmElement','document',f'"skeleton" {d.ref(2)} "model" {d.ref(1000 if mesh else 2)}')
                    d.element(2,'DmeModel','skeleton',d.elements('children',[3]))
                    d.element(3,'DmeJoint','root',f'"transform" {d.ref(4)} '+d.elements('children',[] if mesh else [3] if mode=='cycle' else [10,10] if mode=='duplicate' else [10]))
                    d.element(4,'DmeTransform','root','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
                    if mesh:d.element(1000,'DmeModel','mesh containers',d.elements('children',[10,10] if mode=='duplicate' else [10]))
                    count=257 if mode=='depth' else 3
                    for i in range(count):d.element(10+i,'DmeDag','container'+str(i),d.elements('children',[10+i+1] if i+1<count else [10] if mode=='cycle' else []))
                    self.write('graph.dmx',d.text());output=self.scene_qc('$modelname graph\n$body m graph.dmx\n$sequence idle mesh.smd\n',success=mode=='valid')
                    if mode!='valid':self.assertIn('DMX DAG '+('multiple parents' if mode=='duplicate' else mode),output)

    def test_native_fbx_scale_animation_is_not_silently_discarded(self):
        qc='$modelname scaling\n$body m source.fbx\n$animationcullmethod none\n$animation move source.fbx Pick Walk SampleRate 2\n$sequence idle move\n'
        self.write('source.fbx',animated_scale_fbx(False));self.scene_qc(qc);before=self.mdl('scaling');self.write('source.fbx',animated_scale_fbx())
        for backend in ('','$fbxcompatibility neko\n'):
            output=self.scene_qc(backend+qc,success=False);self.assertIn('scaling',output);self.assertIn('bake',output);self.assertEqual(self.mdl('scaling'),before)

    def test_native_fbx_duration_rejected_before_integer_conversion(self):
        qc='$modelname duration\n$body m source.fbx\n';self.write('source.fbx',fbx_bind_fixture());self.scene_qc(qc);before=self.mdl('duration')
        for seconds in (1000,100000000):
            self.write('source.fbx',fbx_bind_fixture().replace('46186158000',str(46186158000*seconds)));output=self.scene_qc(qc,success=False)
            self.assertIn('exceeds frame limit',output);self.assertEqual(self.mdl('duration'),before)

    def test_imported_animation_default_playback_preserves_source_timing(self):
        for fps in (24,30,60):
            self.write('timing.fbx',fbx_bind_fixture(fps=fps));self.scene_qc('$modelname timing\n$body m timing.fbx\n$animationcullmethod none\n$animation move timing.fbx Pick Walk\n$sequence idle move\n')
            self.assertEqual(self.source_timing('timing'),(fps,fps+1))
        self.scene_fixture()
        for backend in ('','$NoFastGltf\n'):
            self.scene_qc('$modelname timing\n'+backend+'$body m scene.gltf\n$animationcullmethod none\n$animation move scene.gltf Pick Move SampleRate 4\n$sequence idle move\n');self.assertEqual(self.source_timing('timing'),(4,5))
        self.write('timing.dae',collada_curve_fixture('LINEAR'));self.scene_qc('$modelname timing\n$body m timing.dae\n$animationcullmethod none\n$animation move timing.dae Pick Move SampleRate 2\n$sequence idle move\n');self.assertEqual(self.source_timing('timing'),(2,3))
        self.write('timing.dmx',log_fixture(values=[(0,0,0),(1,0,0)],fps=4));self.scene_qc('$modelname timing\n$sequence idle timing.dmx\n');self.assertEqual(self.source_timing('timing'),(4,5))

    def test_authored_playback_overrides_survive_source_fps_inheritance(self):
        self.write('timing.fbx',fbx_bind_fixture(fps=60))
        for prefix,option,expected in [('', 'fps 15',(15,61)),('$defaultfps 12\n','',(12,13)),('$FPS 12\n','SampleRate 4',(12,5)),('', 'SampleRate 4 fps 10',(10,5))]:
            self.scene_qc('$modelname timing\n'+prefix+'$body m timing.fbx\n$animationcullmethod none\n$animation move timing.fbx Pick Walk '+option+'\n$sequence idle move\n');self.assertEqual(self.source_timing('timing'),expected)
        self.scene_qc('$modelname timing\n$sequence idle timing.fbx blockname Walk fps 20\n');self.assertEqual(self.source_timing('timing'),(20,61))
        self.scene_qc('$modelname timing\n$sequence idle mesh.smd\n');self.assertEqual(self.source_timing('timing'),(30,1))

    def test_resource_conditions_apply_platform_negation_and_boolean_operators(self):
        win=os.name=='nt'
        cases=[('[$WIN32]',win),('[!$WIN32]',not win),('[$LINUX]',not win),('[!$LINUX]',win),('[ !$WIN32 ]',not win),('[!($WIN32 || $LINUX)]',False),('[$WIN32 || $LINUX]',True),('[$WIN32 && !$LINUX]',win),('[$X360]',False)]
        for i,(condition,enabled) in enumerate(cases):
            self.write('first/pick.qci',f'$modelname first{i}\n');self.write('fallback/pick.qci',f'$modelname fallback{i}\n')
            self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { Game "|gameinfo_path|first" '+condition+' Game "|gameinfo_path|fallback" } } }')
            self.scene_qc('$include pick.qci\n$body m mesh.smd\n')
            self.assertTrue((self.root/f'models/{"first" if enabled else "fallback"}{i}.mdl').exists());self.assertFalse((self.root/f'models/{"fallback" if enabled else "first"}{i}.mdl').exists())
        for condition in ('[!$WIN32','[$WIN32 && ]','[$WIN32 junk]'):
            self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { Game "first" '+condition+' } } }')
            self.assertIn('KeyValues condition',self.scene_qc('$modelname malformed\n$body m mesh.smd\n',success=False))
