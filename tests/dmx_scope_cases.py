"""Finite DMX value/operator and clip hierarchy coverage with numeric outputs."""
import math
from dmx_dependency_cases import Document, log_fixture, POSITION_TOLERANCE


def connect(d, i, source, attr, target, target_attr):
    d.element(i, 'DmeConnectionOperator', 'connection'+str(i), f'"input" {d.ref(i+1)} '+d.elements('outputs',[i+2]))
    d.element(i+1,'DmeAttributeReference','from',f'"element" {d.ref(source)} "attribute" "string" "{attr}"')
    d.element(i+2,'DmeAttributeReference','to',f'"element" {d.ref(target)} "attribute" "string" "{target_attr}"')


def typed_fixture(kind, values, pack=False):
    d=Document()
    d.element(1,'DmElement','animation',f'"skeleton" {d.ref(2)} "animationList" {d.ref(6)}')
    d.element(2,'DmeModel','model',d.elements('children',[3]))
    d.element(3,'DmeJoint','root',f'"transform" {d.ref(4)} '+d.elements('children',[]))
    d.element(4,'DmeTransform','root','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    d.element(6,'DmeAnimationList','animations',d.elements('animations',[7]))
    d.element(7,'DmeChannelsClip','motion',f'"frameRate" "int" "4" "timeFrame" {d.ref(8)} '+d.elements('channels',[9]))
    d.element(8,'DmeTimeFrame','time','"start" "time" "0" "duration" "time" "1" "offset" "time" "0" "scale" "float" "1"')
    combined={'QAngle':'qangle','VMatrix':'vmatrix','Color':'color','String':'expr','Time':'value'}[kind]
    component={'QAngle':'y','VMatrix':'m23','Color':'red'}.get(kind)
    logkind='Float' if pack else kind
    d.element(9,'DmeChannel','channel',f'"toElement" {d.ref(21 if pack else 20)} "toAttribute" "string" "{component if pack else combined}" "log" {d.ref(10)}')
    d.element(10,'Dme'+logkind+'Log','log',d.elements('layers',[11]))
    valuetype='float' if pack else 'matrix' if kind=='VMatrix' else kind.lower()
    d.element(11,'Dme'+logkind+'LogLayer','layer',d.array('times','int',[0,10000])+d.array('values',valuetype,[' '.join(map(str,v)) if isinstance(v,(tuple,list)) else v for v in values]))
    d.element(30,'DmeTransformOperator','apply',f'"transform" {d.ref(4)} "positionX" "float" "0" "positionY" "float" "0" "positionZ" "float" "0" "orientationX" "float" "0" "orientationY" "float" "0" "orientationZ" "float" "0" "orientationW" "float" "1"')
    if kind in ('QAngle','VMatrix','Color'):
        default='0 0 0' if kind=='QAngle' else '0 0 0 0' if kind=='Color' else ' '.join(['0']*16)
        atype='matrix' if kind=='VMatrix' else kind.lower()
        d.element(20,'DmeUnpack'+kind+'Operator','unpack',f'"{combined}" "{atype}" "{default}"')
        if pack:
            d.element(21,'DmePack'+kind+'Operator','pack',f'"{component}" "float" "0" "{combined}" "{atype}" "{default}"')
            connect(d,100,21,combined,20,combined)
        if kind=='Color':
            d.element(40,'DmeExpressionOperator','amplify','"x" "float" "0" "expr" "string" "x*100"')
            connect(d,110,20,component,40,'x');connect(d,120,40,'result',30,'positionX')
        else:connect(d,110,20,component,30,'positionX')
    elif kind=='String':
        d.element(20,'DmeExpressionOperator','expression','"expr" "string" "0"')
        connect(d,110,20,'result',30,'positionX')
    else:
        d.element(20,'DmElement','clock','"value" "time" "0"');connect(d,110,20,'value',30,'positionX')
    return d.text()


def nested_fixture(*, reverse=False, film_root=False, overlap=False, cycle=False):
    # Root output runs at 4 fps for 2 seconds. The shot starts at .5 s;
    # its double speed traverses the channel clip's 0..1 s log in .5 s.
    d=Document()
    rootbody=f'"timeFrame" {d.ref(50)} "frameRate" "int" "4" "subClipTrackGroup" {d.ref(51)}'
    if film_root:d.element(1,'DmeFilmClip','motion',rootbody+f' "scene" {d.ref(2)}')
    else:
        d.element(1,'DmElement','animation',f'"skeleton" {d.ref(2)} "animationList" {d.ref(6)}')
        d.element(6,'DmeAnimationList','animations',d.elements('animations',[7]))
        d.element(7,'DmeFilmClip','motion',rootbody)
    d.element(2,'DmeModel','model',d.elements('children',[3])+d.elements('jointList',[3]))
    d.element(3,'DmeJoint','root',f'"transform" {d.ref(4)} '+d.elements('children',[]))
    d.element(4,'DmeTransform','root','"position" "vector3" "0 0 0" "orientation" "quaternion" "0 0 0 1"')
    d.element(50,'DmeTimeFrame','filmTime','"start" "time" "0" "duration" "time" "2" "scale" "float" "1"')
    d.element(51,'DmeTrackGroup','filmTracks',d.elements('tracks',[52]))
    d.element(52,'DmeTrack','shots',d.elements('children',[53,60] if overlap else [53]))
    d.element(53,'DmeFilmClip','shot',f'"timeFrame" {d.ref(54)} '+d.elements('trackGroups',[55]))
    d.element(54,'DmeTimeFrame','shotTime','"start" "time" "0.5" "duration" "time" "1" "scale" "float" "2"')
    d.element(55,'DmeTrackGroup','animationTracks',d.elements('tracks',[56]))
    d.element(56,'DmeTrack','bones',d.elements('children',[53 if cycle else 57]))
    d.element(57,'DmeChannelsClip','bones',f'"timeFrame" {d.ref(58)} '+d.elements('channels',[9]))
    d.element(58,'DmeTimeFrame','channelTime',f'"start" "time" "0" "duration" "time" "1" "offset" "time" "{1 if reverse else 0}" "scale" "float" "{-1 if reverse else 1}"')
    d.element(9,'DmeChannel','x',f'"toElement" {d.ref(4)} "toAttribute" "string" "position" "log" {d.ref(10)}')
    d.element(10,'DmeVector3Log','log',d.elements('layers',[11]))
    d.element(11,'DmeVector3LogLayer','layer',d.array('times','int',[0,10000])+d.array('values','vector3',['0 0 0','8 0 0']))
    if overlap:d.element(60,'DmeChannelsClip','overlap',f'"timeFrame" {d.ref(58)} '+d.elements('channels',[9]))
    return d.text()


class DmxScopeCases:
    def test_dmx_remaining_pack_unpack_types(self):
        for kind in ['QAngle','VMatrix','Color']:
            with self.subTest(kind=kind):
                self.dependency_compile(typed_fixture(kind,(0,1 if kind=='Color' else 8),pack=True))
                values=[p[0] for p in self.animation_poses('graph','motion')]
                expected=[int(f*255.999)*100/255.999 for f in [0,.25,.5,.75,1]] if kind=='Color' else [0,2,4,6,8]
                for actual,wanted in zip(values,expected):self.assertAlmostEqual(actual,wanted,delta=.008)

    def test_dmx_remaining_log_types_have_reference_interpolation(self):
        a=[0]*16;b=[0]*16;a[11]=3;b[11]=9
        cases=[('QAngle',[(0,350,0),(0,10,0)],[-10,-5,0,5,10]),
               ('VMatrix',[a,b],[3,3,3,3,9]),('Color',[(0,0,0,0),(255,255,255,255)],[v*100/255.999 for v in [0,63,127,191,255]]),
               ('String',['2+3','8*2'],[5,5,5,5,16]),('Time',[0,4],[0,1,2,3,4])]
        for kind,values,expected in cases:
            with self.subTest(kind=kind):
                self.dependency_compile(typed_fixture(kind,values))
                poses=self.animation_poses('graph','motion');self.assertEqual(len(poses),5)
                for actual,wanted in zip(poses,expected):self.assertAlmostEqual(actual[0],wanted,delta=.03)

    def test_dmx_reverse_clip_and_nested_film_time_mapping(self):
        text=log_fixture(kind='Float',values=(0,8)).replace('"offset" "time" "0"','"offset" "time" "1"').replace('"scale" "float" "1"','"scale" "float" "-1"')
        self.dependency_compile(text)
        for p,wanted in zip(self.animation_poses('graph','motion'),[8,6,4,2,0]):self.assertAlmostEqual(p[0],wanted,delta=.008)
        for reverse in [False,True]:
            self.dependency_compile(nested_fixture(reverse=reverse))
            actual=[p[0] for p in self.animation_poses('graph','motion')]
            expected=[0,0,8,4,0,0,0,0,0] if reverse else [0,0,0,4,8,0,0,0,0]
            self.assertEqual(len(actual),len(expected))
            for a,b in zip(actual,expected):self.assertAlmostEqual(a,b,delta=.008)

    def test_dmx_standalone_film_scene_skeleton(self):
        self.dependency_compile(nested_fixture(film_root=True))
        self.assertAlmostEqual(self.animation_poses('graph','motion')[3][0],4,delta=.008)

    def test_dmx_timeline_cycles_and_overlapping_writers_fail(self):
        self.assertIn('clip hierarchy',self.dependency_compile(nested_fixture(cycle=True),success=False))
        self.assertIn('writers',self.dependency_compile(nested_fixture(overlap=True),success=False))

    def test_dmx_adjacent_clips_choose_incoming_boundary(self):
        text=nested_fixture().replace(Document().elements('children',[53]),Document().elements('children',[57,60]))
        d=Document()
        d.element(60,'DmeChannelsClip','second',f'"timeFrame" {d.ref(61)} '+d.elements('channels',[9]))
        d.element(61,'DmeTimeFrame','secondTime','"start" "time" "1" "duration" "time" "1" "scale" "float" "1"')
        text+='\n'.join(d.rows)
        self.dependency_compile(text)
        expected=[0,2,4,6,0,2,4,6,8]
        for actual,wanted in zip(self.animation_poses('graph','motion'),expected):self.assertAlmostEqual(actual[0],wanted,delta=.008)

    def test_dmx_new_log_types_ignore_inapplicable_curve_metadata(self):
        text=typed_fixture('Color',[(0,0,0,0),(255,0,0,0)])
        d=Document();d.element(70,'DmeColorCurveInfo','curve','"defaultCurveType" "int" "3855"')
        text=text.replace(d.elements('layers',[11]),d.elements('layers',[11])+f' "curveinfo" {d.ref(70)}')+'\n'.join(d.rows)
        self.dependency_compile(text)
        self.assertAlmostEqual(self.animation_poses('graph','motion')[2][0],127*100/255.999,delta=.01)
