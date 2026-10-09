"""Optional real Lua 5.1 tests of the GMod adapter, using engine API test doubles.

Run with Python and lupa installed, or pass --lua-path <directory containing lupa>.
This verifies math and API calls; it does not claim live GMod rendering parity.
"""
from pathlib import Path
import sys
import unittest

if '--lua-path' in sys.argv:
    i=sys.argv.index('--lua-path');sys.path.insert(0,sys.argv[i+1]);del sys.argv[i:i+2]
try:
    from lupa.lua51 import LuaRuntime
except ImportError:
    LuaRuntime=None

ROOT=Path(__file__).resolve().parents[1]
STUBS=r'''
math.Clamp=function(x,a,b) return math.max(a,math.min(b,x)) end
local V={};V.__index=V
function Vector(x,y,z) return setmetatable({x=x or 0,y=y or 0,z=z or 0},V) end
function V.__add(a,b) return Vector(a.x+b.x,a.y+b.y,a.z+b.z) end
function V.__sub(a,b) return Vector(a.x-b.x,a.y-b.y,a.z-b.z) end
function V.__unm(a) return Vector(-a.x,-a.y,-a.z) end
function V.__mul(a,b) if type(a)=='number' then a,b=b,a end return Vector(a.x*b,a.y*b,a.z*b) end
function V:Dot(b) return self.x*b.x+self.y*b.y+self.z*b.z end
function V:Cross(b) return Vector(self.y*b.z-self.z*b.y,self.z*b.x-self.x*b.z,self.x*b.y-self.y*b.x) end
function V:LengthSqr() return self:Dot(self) end
function V:Length() return math.sqrt(self:LengthSqr()) end
function V:GetNormalized() local length=self:Length() return length>0 and self*(1/length) or Vector() end
function near(a,b,tolerance) assert(math.abs(a-b)<=(tolerance or 1e-8),tostring(a)..' != '..tostring(b)) end
function nearv(a,b,tolerance) near(a.x,b.x,tolerance);near(a.y,b.y,tolerance);near(a.z,b.z,tolerance) end
local MT={};MT.__index=MT
function Matrix(m)
  return setmetatable({c1=m and m.c1*1 or Vector(1,0,0),c2=m and m.c2*1 or Vector(0,1,0),
                      c3=m and m.c3*1 or Vector(0,0,1),p=m and m.p*1 or Vector()},MT)
end
function MT:TransformVector(v) return self.c1*v.x+self.c2*v.y+self.c3*v.z end
function MT.__mul(a,b)
  local m=Matrix();m.c1=a:TransformVector(b.c1);m.c2=a:TransformVector(b.c2);m.c3=a:TransformVector(b.c3)
  m.p=a.p+a:TransformVector(b.p);return m
end
function MT:GetInverse()
  local m=Matrix();m.c1=Vector(self.c1.x,self.c2.x,self.c3.x);m.c2=Vector(self.c1.y,self.c2.y,self.c3.y)
  m.c3=Vector(self.c1.z,self.c2.z,self.c3.z);m.p=m:TransformVector(-self.p);return m
end
function MT:GetTranslation() return self.p*1 end
function MT:SetTranslation(v) self.p=v*1 end
function MT:GetForward() return self.c1*1 end
-- Facepunch VMatrix:GetRight / SetRight use NEGATIVE column 2.
function MT:GetRight() return -self.c2 end
function MT:GetUp() return self.c3*1 end
function MT:SetForward(v) self.c1=v*1 end
function MT:SetRight(v) self.c2=-v end
function MT:SetUp(v) self.c3=v*1 end
function MT:GetField(r,c) return ({self.c1,self.c2,self.c3,self.p})[c][({'x','y','z'})[r]] end
function MT:SetField(r,c,v) ({self.c1,self.c2,self.c3,self.p})[c][({'x','y','z'})[r]]=v end
IsValid=function(e) return type(e)=='table' and not e.invalid end
function Entity()
 local e={matrices={},base={},parents={[-1]=-1,[0]=-1,[1]=0,[2]=1},flex={},overrides={}}
 for i=0,2 do local m=Matrix();m:SetTranslation(Vector(0,i,0));e.matrices[i]=m;e.base[i]=Matrix(m) end
 function e:LookupBone(n) return ({root=0,child=1,tip=2})[n] end
 function e:GetBoneCount() return 3 end
 function e:GetBoneParent(i) return self.parents[i] end
 function e:GetBoneMatrix(i) return self.matrices[i] end
 function e:SetBoneMatrix(i,m) self.matrices[i]=Matrix(m) end
 function e:GetModelScale() return 1 end
 function e:LocalToWorld(v) return self.transform and self.transform.p+self.transform:TransformVector(v) or v end
 function e:GetFlexIDByName(n) return ({smile=0,blink=1})[n] end
 function e:SetFlexWeight(i,v) self.flex[i]=v end
 function e:EntIndex() return 23 end
 function e:GetMaterials() return {'models/avatar/vrm_material_0'} end
 function e:GetSubMaterial(i) return self.overrides[i] or '' end
 function e:SetSubMaterial(i,v) self.overrides[i]=v end
 function e:Reset() for i,m in pairs(self.base) do self.matrices[i]=Matrix(m) end end
 return e
end
function Joint(name,gravity,dir)
 return {bone=name,tail={0,1,0},stiffness=0,gravity=gravity or 0,gravity_dir=dir or {1,0,0},drag=1,radius=0}
end
function Data(joints)
 return {schema=1,type='newpage_vrm',springs={{joints=joints or {Joint('root',20)},colliders={}}},colliders={},expressions={},materials={}}
end
'''


@unittest.skipIf(LuaRuntime is None,'optional Lua 5.1 tests require lupa')
class VrmRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.lua=LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUBS)
        self.lua.globals().VRM=self.lua.execute((ROOT/'integration/gmod/newpage_vrm.lua').read_text())

    def test_matrix_right_sign_gravity_and_parent_propagation(self):
        self.lua.execute('''
local e=Entity();local data=Data();local s=assert(VRM.NewSpringState(e,data))
assert(VRM.StepSprings(e,s,1/60))
local expected=Vector(1/3,1,0):GetNormalized()
nearv(s.tails.root.now,expected);nearv(e.matrices[1]:GetTranslation(),expected)
nearv(e.matrices[2]:GetTranslation(),expected*2)
near(e.matrices[0]:GetForward():Dot(e.matrices[0]:GetRight()),0)
near(e.matrices[0]:GetRight():Length(),1)
local before=s.tails.root.now*1;local previous=s.tails.root.previous*1
e:Reset();assert(VRM.StepSprings(e,s,0));nearv(s.tails.root.now,before);nearv(s.tails.root.previous,previous)
nearv(e.matrices[1]:GetTranslation(),before)
''')

    def test_model_space_gravity_rotates_with_entity(self):
        self.lua.execute('''
local e=Entity();e.transform=Matrix();e.transform:SetForward(Vector(0,1,0));e.transform:SetRight(Vector(1,0,0))
for i,m in pairs(e.matrices) do e.matrices[i]=e.transform*m end
local s=assert(VRM.NewSpringState(e,Data()))
assert(VRM.StepSprings(e,s,1/60))
nearv(s.tails.root.now,Vector(-1,1/3,0):GetNormalized())
''')

    def test_center_translation_and_zero_step_are_stable(self):
        self.lua.execute('''
local e=Entity();e.parents[2]=-1;e.matrices[2]:SetTranslation(Vector(10,0,0))
local data=Data({Joint('root')});data.springs[1].center='tip'
local s=assert(VRM.NewSpringState(e,data));assert(VRM.StepSprings(e,s,0))
nearv(s.tails.root.now,Vector(-10,1,0))
e:Reset();e.matrices[0]:SetTranslation(Vector(5,0,0));e.matrices[1]:SetTranslation(Vector(5,1,0));e.matrices[2]:SetTranslation(Vector(15,0,0))
assert(VRM.StepSprings(e,s,0));nearv(s.tails.root.now,Vector(-10,1,0));nearv(e.matrices[1]:GetTranslation(),Vector(5,1,0))
''')

    def test_parent_order_across_spring_groups(self):
        self.lua.execute('''
local e=Entity();local data=Data()
data.springs={{joints={Joint('child',20,{0,0,1})},colliders={}},{joints={Joint('root',20)},colliders={}}}
local s=assert(VRM.NewSpringState(e,data));assert(s.joints[1].joint.bone=='root')
assert(VRM.StepSprings(e,s,1/60))
nearv(e.matrices[1]:GetTranslation(),s.tails.root.now)
nearv(e.matrices[2]:GetTranslation(),s.tails.child.now)
assert(s.tails.child.now.z>0)
near((s.tails.child.now-s.tails.root.now):Length(),1)
''')

    def test_capsule_projection_preserves_length_and_moves_outward(self):
        self.lua.execute('''
local e=Entity();e.parents[2]=-1;e.matrices[2]=Matrix()
local data=Data({Joint('root')});data.springs[1].colliders={0}
data.colliders={{bone='tip',shape='capsule',offset={.2,.6,-1},tail={.2,.6,1},radius=.5}}
local s=assert(VRM.NewSpringState(e,data));assert(VRM.StepSprings(e,s,1/60))
local tail=s.tails.root.now;near(tail:Length(),1)
assert((tail-Vector(.2,.6,0)):Length()>math.sqrt(.2*.2+.4*.4))
assert(tail.x<0)
-- Projection is bounded and may retain penetration; no exact collision solver parity is claimed.
''')

    def test_antiparallel_alignment_and_invalid_skeleton(self):
        self.lua.execute('''
local e=Entity();local data=Data({Joint('root')});local s=assert(VRM.NewSpringState(e,data))
s.tails.root={now=Vector(0,-1,0),previous=Vector(0,-1,0)}
assert(VRM.StepSprings(e,s,0));nearv(e.matrices[1]:GetTranslation(),Vector(0,-1,0))
near(e.matrices[0]:GetForward():Length(),1)
e=Entity();e.parents[0]=2;local invalid,err=VRM.NewSpringState(e,data)
assert(invalid==nil and err=='cyclic engine skeleton')
''')

    def test_expression_override_binary_clamping_and_adapter_failure(self):
        self.lua.execute('''
local data=Data();data.expressions={
 happy={binary=true,binds={{controller='smile',weight=.8}},material_binds={},overrides={overrideBlink='block'}},
 blink={binary=false,binds={{controller='blink',weight=1}},material_binds={},overrides={}}}
local controls=assert(VRM.ResolveExpressions(data,{happy=.5,blink=1}));near(controls.smile,0);near(controls.blink,1)
controls=assert(VRM.ResolveExpressions(data,{happy=.6,blink=2}));near(controls.smile,.8);near(controls.blink,0)
data.expressions.happy.material_binds={{kind='color',material=0,property='color',target={1,0,0,1}}}
local e=Entity();local ok,err=VRM.SetExpressions(e,data,{happy=1},function() return false,'unsupported' end)
assert(not ok and err=='unsupported' and e.flex[0]==nil)
assert(VRM.SetExpressions(e,data,{happy=1},function() return true end));near(e.flex[0],.8)
''')

    def test_sampled_expression_clip_partial_final_frame(self):
        self.lua.execute('''
local data=Data();data.expressions={happy={binds={{controller='smile',weight=1}},material_binds={},overrides={}}}
data.clip={fps=2,duration=.75,samples={{happy=0},{happy=2/3},{happy=1}}}
local e=Entity();assert(VRM.SampleClip(e,data,.6,false));near(e.flex[0],.8)
assert(VRM.SampleClip(e,data,.75,false));near(e.flex[0],1)
assert(VRM.SampleClip(e,data,5,false));near(e.flex[0],1)
assert(VRM.SampleClip(e,data,.75,true));near(e.flex[0],0)
''')

    def test_material_adapter_color_alpha_emission_uv_isolation_and_unsupported(self):
        self.lua.execute(r'''
materials={}
local function mat(name)
 local m={name=name,values={['$color2']=Vector(1,1,1),['$alpha']=1,['$selfillumtint']=Vector(0,0,0),['$basetexturetransform']=Matrix()}}
 function m:IsError() return false end
 function m:GetVector(k) return self.values[k] end
 function m:GetFloat(k) return self.values[k] end
 function m:GetMatrix(k) return self.values[k] end
 function m:GetKeyValues() return {['$alpha']=1} end
 function m:GetShader() return 'VertexLitGeneric' end
 function m:SetVector(k,v) self.values[k]=v end
 function m:SetFloat(k,v) self.values[k]=v end
 function m:SetMatrix(k,v) self.values[k]=v end
 return m
end
function Material(name) if not materials[name] then materials[name]=mat(name) end return materials[name] end
function CreateMaterial(name,shader,keys) materials[name]=mat(name);return materials[name] end
''')
        self.lua.globals().Materials=self.lua.execute((ROOT/'integration/gmod/newpage_vrm_materials.lua').read_text())
        self.lua.execute('''
local e=Entity();local data=Data();data.materials={{name='vrm_material_0',base_color={1,1,1,1}}}
local color={kind='color',material=0,property='color',target={1,0,0,.2}}
local emission={kind='color',material=0,property='emissionColor',target={0,.8,.4}}
local uv={kind='texture',material=0,scale={2,3},offset={.2,-.4}}
data.expressions.happy={binds={},material_binds={color,emission,uv},overrides={}}
local adapter,detach=Materials.New(e,data);assert(adapter,detach)
assert(adapter(e,{{binding=color,weight=.5},{binding=emission,weight=.5},{binding=uv,weight=.5}}))
local material=materials[e.overrides[0]:sub(2)]
nearv(material.values['$color2'],Vector(1,.5,.5));near(material.values['$alpha'],.6)
nearv(material.values['$selfillumtint'],Vector(0,.4,.2))
near(material.values['$basetexturetransform']:GetField(1,1),1.5)
near(material.values['$basetexturetransform']:GetField(2,2),2)
nearv(material.values['$basetexturetransform']:GetTranslation(),Vector(.1,-.2,0))
nearv(Material('models/avatar/vrm_material_0').values['$color2'],Vector(1,1,1))
local ok,message=adapter(e,{{binding={kind='legacy',material=0,property='_ShadeColor',target={1,0,0,1}},weight=1}})
assert(not ok and message:find('unsupported'));near(material.values['$alpha'],.6)
assert(adapter(e,{}));nearv(material.values['$color2'],Vector(1,1,1));near(material.values['$alpha'],1)
detach();assert(e.overrides[0]=='');assert(not adapter(e,{}))
local client=Entity();function client:EntIndex() return -1 end
function client:GetSubMaterial() return 'server_override' end
client.overrides[0]='!old_local'
local a2,d2,info=Materials.New(client,data,{previousOverrides={[0]='!old_local'}});assert(a2,d2)
assert(a2(client,{{binding=color,weight=1}}))
assert(client.overrides[0]=='!'..info.materials[0].name)
assert(info.materials[0].material==materials[info.materials[0].name])
d2();assert(client.overrides[0]=='!old_local')
''')


if __name__=='__main__':
    unittest.main()
