"""Reject malformed Lua sidecars before mutation (real Lua 5.1, engine doubles)."""
from pathlib import Path
import argparse
import sys
import unittest

parser = argparse.ArgumentParser()
parser.add_argument('--lua-path')
parser.add_argument('--lua-source', type=Path)
args, rest = parser.parse_known_args()
sys.argv = [sys.argv[0], *rest]
if args.lua_path:
    sys.path.insert(0, args.lua_path)
from lupa.lua51 import LuaRuntime
from vrm_runtime_lua_test import STUBS

SOURCE = args.lua_source or Path(__file__).resolve().parents[1]/'integration/gmod'


class RuntimeMetadata(unittest.TestCase):
    def setUp(self):
        self.lua = LuaRuntime(unpack_returned_tuples=True)
        self.lua.execute(STUBS)
        for key, name in [('VRM','newpage_vrm.lua'), ('Vertex','newpage_vertexanim.lua')]:
            self.lua.globals()[key] = self.lua.execute((SOURCE/name).read_text())
        self.lua.execute('''
file={Read=function() return "test metadata" end}
document={schema=1,type="newpage_vrm",model="models/a.mdl",expressions={},springs={},colliders={},materials={}}
util={JSONToTable=function() return document end}
''')

    def test_vrm_load_rejects_missing_fields_and_invalid_nested_data(self):
        self.lua.execute('''
assert(VRM.Load("models/a.mdl"))
for _,bad in ipairs({{}, {schema=1,type="newpage_vrm"}, "text", 42}) do document=bad;assert(VRM.Load("models/a.mdl")==nil) end
document={schema=1,type="newpage_vrm",model="models/a.mdl",expressions={},springs={},colliders={},materials={}}
document.colliders={{bone="root",shape="capsule",offset={0,0,0},radius=1,tail={0/0,0,0}}}
assert(VRM.Load("models/a.mdl")==nil)
document.colliders={};document.clip={fps=0,duration=1,samples={{}}};assert(VRM.Load("models/a.mdl")==nil)
''')

    def test_vrm_rejects_mismatched_models_and_bad_direct_expression_calls(self):
        self.lua.execute('''
local entity=Entity();function entity:GetModel() return "models/b.mdl" end
assert(VRM.Load("models/b.mdl")==nil)
assert(not VRM.SetExpressions(entity,document,{}))
assert(not VRM.SetExpressions(entity,{expressions=false},{}))
assert(VRM.ResolveExpressions({expressions={happy={}}},{})==nil)
assert(VRM.SampleClip(entity,{},0)==false)
assert(VRM.NewSpringState(entity,{springs={{joints={},colliders={9}}},colliders={}})==nil)
assert(next(entity.flex)==nil)
''')

    def test_vertex_metadata_checks_all_clips_and_links_model_identity(self):
        self.lua.execute('''
document={schema=1,clips={{controller="smile",position_controller="blink",times={0,.5,1}}}}
local loaded=assert(Vertex.Load("models/a.mdl"));assert(loaded.clips[1].model=="models/a.mdl")
local entity=Entity();function entity:GetModel() return "models/b.mdl" end
assert(not Vertex.Sample(entity,loaded.clips[1],.5));assert(next(entity.flex)==nil)
for _,times in ipairs({{"bad"},{0,0},{0,0/0},{0,math.huge}}) do
 document.clips[1].times=times;assert(Vertex.Load("models/a.mdl")==nil)
end
document={schema=1};assert(Vertex.Load("models/a.mdl")==nil)
document={schema=1,clips={[1]={controller="a",position_controller="b",times={0}},[3]={controller="a",position_controller="b",times={0}}}}
assert(Vertex.Load("models/a.mdl")==nil)
''')

    def test_vertex_direct_calls_reject_bad_times_and_preserve_valid_sampling(self):
        self.lua.execute('''
local entity=Entity();local clip={controller="smile",position_controller="blink",times={0,.5,1}}
assert(not Vertex.Sample(entity,clip,0/0));assert(next(entity.flex)==nil)
assert(Vertex.Sample(entity,clip,.75));near(entity.flex[0],1);near(entity.flex[1],.5)
clip.model=42;assert(not Vertex.Sample(entity,clip,0));clip.model=nil
clip.times={"bad"};assert(not Vertex.Sample(entity,clip,0))
assert(not Vertex.Sample(entity,false,0));assert(Vertex.Load(false)==nil)
''')


if __name__ == '__main__':
    unittest.main()
