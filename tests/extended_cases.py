from scene_fixtures import scene_bytes
from pathlib import Path
import struct,json,base64,subprocess,sys,copy
class ExtendedCases:
 def test_output_validator_rejects_truncation_offsets_and_checksum_mismatch(self):
  from validate_outputs import validate
  self.scene_qc('$modelname integrity\n$body m mesh.smd\n')
  path=self.root/'models/integrity.mdl';original=path.read_bytes()
  for field,value in [(76,len(original)+1),(160,len(original)-1),(236,-1)]:
   broken=bytearray(original);struct.pack_into('<i',broken,field,value);path.write_bytes(broken)
   with self.assertRaises(ValueError):validate(path)
  path.write_bytes(original);vvd=self.root/'models/integrity.vvd';data=bytearray(vvd.read_bytes());data[8]^=1;vvd.write_bytes(data)
  with self.assertRaisesRegex(ValueError,'checksum'):validate(path)

 def test_dmx_reference_profiles_preserve_distinct_rules_and_controllers(self):
  self.write('face.dmx',(Path(__file__).parent/'fixtures/ce-facial.dmx').read_text())
  for mode,controllers,rules in [('native',1,1),('ce',2,0),('neko',2,2)]:
   self.scene_qc('$modelname face\n$dmxcompatibility '+mode+'\n$model a face.dmx\n$model b face.dmx\n')
   data=self.ce_data();self.assertEqual(len(data[0]),controllers);self.assertEqual(len(data[3]),rules)
  self.scene_qc('$modelname face\n$dmxcompatibility neko\n$model a face.dmx {\n%smile = smile\n}\n')
  self.assertEqual(len(self.ce_data()[3]),2)

 def test_dmx_profile_rejects_typo_and_preserves_output(self):
  self.scene_qc('$modelname face\n$body m mesh.smd\n');old=self.mdl('face')
  self.assertIn('expects native, ce or neko',self.scene_qc('$modelname face\n$dmxcompatibility unknown\n',success=False))
  self.assertEqual(self.mdl('face'),old)

 def test_nested_macro_errors_report_definition_and_invocation(self):
  self.write('defs.qci','$definemacro inner\n$scale invalid\n$endmacro\n$definemacro outer\n$inner\n$endmacro\n')
  text=self.scene_qc('$include defs.qci\n$outer\n',success=False)
  self.assertIn('defs.qci(2)',text);self.assertIn('expanded $inner',text)
  self.assertIn('expanded $outer',text);self.assertIn('scene.qc(2)',text)

 def test_gltf_negative_skin_weight_is_rejected_before_output(self):
  from scene_fixtures import skinned_scene_bytes
  doc=json.loads(skinned_scene_bytes());weights=doc['meshes'][0]['primitives'][0]['attributes']['WEIGHTS_0']
  view=doc['bufferViews'][doc['accessors'][weights]['bufferView']]
  blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]));struct.pack_into('<f',blob,view['byteOffset'],-.1)
  doc['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode();self.write('scene.gltf',json.dumps(doc))
  text=self.scene_qc('$modelname negative\n$body m scene.gltf\n',success=False)
  self.assertIn('invalid glTF skin weight',text);self.assertFalse((self.root/'models/negative.mdl').exists())

 def test_repeated_joint_streams_are_merged_before_skin_culling(self):
  from scene_fixtures import skinned_scene_bytes
  doc=json.loads(skinned_scene_bytes());attrs=doc['meshes'][0]['primitives'][0]['attributes']
  attrs['JOINTS_1']=attrs['JOINTS_0'];attrs['WEIGHTS_1']=attrs['WEIGHTS_0']
  self.write('scene.gltf',json.dumps(doc));self.scene_qc('$modelname repeated\n$body m scene.gltf InNode MeshA\n')
  data=(self.root/'models/repeated.vvd').read_bytes();start=struct.unpack_from('<i',data,56)[0]
  for i in range(3):
   self.assertEqual(data[start+i*48+15],1);self.assertAlmostEqual(struct.unpack_from('<f',data,start+i*48)[0],1)

 def test_baked_defaults_respect_node_override_on_shared_morph_mesh(self):
  doc=json.loads(self.scene_fixture().read_text());doc['meshes'][0]['weights']=[1];doc['nodes'][1]['weights']=[.5]
  for kind in ('gltf','glb','vrm'):
   variant=copy.deepcopy(doc)
   if kind=='gltf':self.write('scene.gltf',json.dumps(variant))
   else:
    binary=base64.b64decode(variant['buffers'][0].pop('uri').split(',')[1]);binary+=b'\0'*((-len(binary))%4)
    if kind=='vrm':variant['extensionsUsed']=['VRM'];variant['extensions']={'VRM':{'specVersion':'0.0','meta':{'title':'Self-authored fixture'}}}
    text=json.dumps(variant).encode();text+=b' '*((-len(text))%4)
    chunks=struct.pack('<II',len(text),0x4e4f534a)+text+struct.pack('<II',len(binary),0x004e4942)+binary
    (self.root/('scene.'+kind)).write_bytes(struct.pack('<III',0x46546c67,2,len(chunks)+12)+chunks)
   for node,expected in [('MeshA',.125),('MeshB',.25)]:
    self.scene_qc('$modelname baked\n$UpAxis z gltf\n$body m scene.'+kind+' InNode '+node+' BakeSceneAnimation Move SceneSampleRate 1\n')
    d,flex=self.first_mesh_flex('baked');self.assertTrue(any(abs(struct.unpack_from('<3e',d,v+4)[2]-expected)<1e-4 for v in flex))

 def test_ce_profile_keeps_baked_scene_playback_rules(self):
  self.scene_fixture();self.scene_qc('$modelname baked\n$dmxcompatibility ce\n$body m scene.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 2\n')
  self.assertGreater(len(self.ce_data('baked')[3]),0)

 def test_mount_search_order_preserves_script_and_explicit_paths(self):
  mesh=(self.root/'mesh.smd').read_text();self.write('mount/mounted.smd',mesh)
  self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { game "|gameinfo_path|mount" } } }')
  self.scene_qc('$modelname mount\n$body m mounted.smd\n')
  self.assertTrue(self.mdl('mount').startswith(b'IDST'))
  self.write('mounted.smd',mesh.replace('"root"','"local_root"'))
  self.scene_qc('$modelname mount\n$body m mounted.smd\n');self.assertIn(b'local_root\0',self.mdl('mount'))

 def test_appid_mount_uses_secondary_steam_library_and_include(self):
  steam=self.root/'steam';library=self.root/'library'
  self.write('steam/steamapps/libraryfolders.vdf','libraryfolders { "1" { path "'+library.as_posix()+'" } }')
  self.write('library/steamapps/appmanifest_550.acf','AppState { installdir "FixtureGame" }')
  prefix='library/steamapps/common/FixtureGame/content/'
  self.write(prefix+'mounted.smd',(self.root/'mesh.smd').read_text())
  self.write(prefix+'mounted.qci','$body m mounted.smd\n')
  self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { game "|appid_550|/content" } } }')
  self.scene_qc('$modelname mounted\n$include mounted.qci\n','-steamdir',str(steam))
  self.assertTrue(self.mdl('mounted').startswith(b'IDST'))

 def write_vpk(self,version=1,external=False):
  data=(self.root/'mesh.smd').read_bytes();preload=data[:11];body=data[11:]
  entry=struct.pack('<IHHIIH',0,len(preload),0 if external else 0x7fff,0,len(body),0xffff)+preload
  tree=b'smd\0 \0mounted\0'+entry+b'\0\0\0'
  header=struct.pack('<III',0x55aa1234,version,len(tree))
  if version==2:header+=struct.pack('<4I',0 if external else len(body),0,0,0)
  path=self.root/'pack_dir.vpk';path.write_bytes(header+tree+(b'' if external else body))
  if external:(self.root/'pack_000.vpk').write_bytes(body)
  self.write('gameinfo.txt','GameInfo { FileSystem { SearchPaths { game "|gameinfo_path|pack.vpk" } } }')
  return path

 def test_vpk_versions_preload_and_external_archive(self):
  for version,external in [(1,False),(2,False),(2,True)]:
   self.write_vpk(version,external)
   self.scene_qc('$modelname archived\n$body m mounted.smd\n')
   self.assertEqual(struct.unpack_from('<i',self.mdl('archived'),156)[0],1)

 def test_truncated_vpk_fails_without_replacing_model(self):
  self.scene_qc('$modelname archived\n$body m mesh.smd\n');old=self.mdl('archived')
  archive=self.write_vpk();archive.write_bytes(archive.read_bytes()[:-40])
  output=self.scene_qc('$modelname archived\n$body m mounted.smd\n',success=False)
  self.assertIn('VPK',output);self.assertEqual(self.mdl('archived'),old)

 def test_draco_unique_attribute_ids_uv_and_flex(self):
  fixture=Path(__file__).parent/'fixtures/draco-triangle.gltf';self.write('scene.gltf',fixture.read_text())
  self.scene_qc('$modelname draco\n$body m scene.gltf { flex Smile\nflexcontroller test strength\n%Smile = strength\n}\n$sequence idle scene.gltf\n')
  d,flex=self.first_mesh_flex('draco');self.assertEqual(len(flex),3)
  vvd=(self.root/'models/draco.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
  uv=sorted(tuple(round(x,4) for x in struct.unpack_from('<2f',vvd,start+i*48+40)) for i in range(3))
  self.assertEqual(uv,[(.1,.2),(.4,.9),(.7,.3)])
  points=sorted(round(struct.unpack_from('<f',vvd,start+i*48+16)[0],4) for i in range(3));self.assertEqual(points,[1,2,3])

 def test_corrupt_draco_does_not_use_fallback_or_replace_output(self):
  fixture=Path(__file__).parent/'fixtures/draco-triangle.gltf';doc=json.loads(fixture.read_text())
  self.write('scene.gltf',json.dumps(doc));self.scene_qc('$modelname draco\n$body m scene.gltf\n');old=self.mdl('draco')
  payload=bytearray(base64.b64decode(doc['buffers'][1]['uri'].split(',')[1]));payload[0]=0
  doc['buffers'][1]['uri']='data:application/octet-stream;base64,'+base64.b64encode(payload).decode();self.write('scene.gltf',json.dumps(doc))
  self.assertIn('invalid Draco',self.scene_qc('$modelname draco\n$body m scene.gltf\n',success=False));self.assertEqual(self.mdl('draco'),old)

 def test_baked_scene_translation_and_playback_metadata(self):
  self.scene_fixture()
  self.scene_qc('$modelname baked\n$body m scene.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 2\n')
  meta=json.loads((self.root/'models/baked.vertexanim.json').read_text());self.assertEqual(meta['clips'][0]['times'],[0,.5,1])
  self.assertEqual(meta['clips'][0]['controller'],'bake_Move');self.assertIn(b'multi_bake_Move\0',self.mdl('baked'))
  d,flex=self.first_mesh_flex('baked');deltas=[struct.unpack_from('<3e',d,v+4)[0] for v in flex]
  self.assertTrue(any(abs(v-2)<1e-4 for v in deltas))

 def test_baked_animated_scale_and_morph_weight(self):
  doc=json.loads(self.scene_fixture().read_text());doc['nodes'][0]['children']=[1]
  output=doc['animations'][0]['samplers'][0]['output'];accessor=doc['accessors'][output]
  offset=doc['bufferViews'][accessor['bufferView']]['byteOffset'];blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]))
  struct.pack_into('<6f',blob,offset,1,1,1,2,1,1);doc['animations'][0]['channels'][0]['target']['path']='scale'
  at=len(blob);blob.extend(struct.pack('<2f',0,1));doc['bufferViews'].append({'buffer':0,'byteOffset':at,'byteLength':8});doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':2,'type':'SCALAR'})
  doc['animations'][0]['samplers'].append({'input':doc['animations'][0]['samplers'][0]['input'],'output':len(doc['accessors'])-1})
  doc['animations'][0]['channels'].append({'sampler':1,'target':{'node':1,'path':'weights'}})
  doc['buffers'][0]={'byteLength':len(blob),'uri':'data:application/octet-stream;base64,'+base64.b64encode(blob).decode()};self.write('scene.gltf',json.dumps(doc))
  self.scene_qc('$modelname baked\n$body m scene.gltf BakeSceneAnimation Move SceneSampleRate 2\n')
  d,flex=self.first_mesh_flex('baked');self.assertTrue(any(abs(struct.unpack_from('<3e',d,v+4)[0]-.5)<1e-4 for v in flex))
  self.assertTrue(any(abs(struct.unpack_from('<3e',d,v+4)[1]+.125)<1e-4 for v in flex))

 def test_invalid_bake_clip_preserves_previous_output(self):
  self.scene_fixture();self.scene_qc('$modelname baked\n$body m scene.gltf\n');old=self.mdl('baked')
  self.assertIn('animation not found',self.scene_qc('$modelname baked\n$body m scene.gltf BakeSceneAnimation absent\n',success=False))
  self.assertEqual(self.mdl('baked'),old)

 def test_baked_clip_render_bounds_include_far_samples(self):
  self.scene_fixture()
  self.write('idle.smd','version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\n')
  self.scene_qc('$modelname baked\n$body m scene.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 2\n$sequence idle idle.smd\n')
  # The bind mesh ends at X=3, while the final baked sample ends at X=7.
  sequence=self.sequences('baked')[0][2]
  self.assertGreaterEqual(max(struct.unpack_from('<3f',self.mdl('baked'),sequence+44)),7)

 def test_baked_skinned_clip_respects_joint_scale(self):
  from scene_fixtures import skinned_scene_bytes
  doc=json.loads(skinned_scene_bytes());doc['nodes'][0]['children']=[1,3]
  doc['animations'][0]['channels'][0]['target']={'node':3,'path':'scale'}
  output=doc['animations'][0]['samplers'][0]['output'];view=doc['bufferViews'][doc['accessors'][output]['bufferView']]
  blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]));struct.pack_into('<6f',blob,view['byteOffset'],1,1,1,2,1,1)
  doc['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode();self.write('scene.gltf',json.dumps(doc))
  self.scene_qc('$modelname baked\n$body m scene.gltf BakeSceneAnimation Move SceneSampleRate 2\n')
  d,flex=self.first_mesh_flex('baked');self.assertTrue(any(abs(struct.unpack_from('<3e',d,v+4)[0]+3)<1e-4 for v in flex))

 def test_two_frame_bake_has_interpolated_nway_ramp(self):
  self.scene_fixture();self.scene_qc('$modelname baked\n$body m scene.gltf InNode MeshA BakeSceneAnimation Move SceneSampleRate 1\n')
  rules=self.ce_data('baked')[3]
  constants=[struct.unpack('<f',struct.pack('<i',value))[0] for op,value in rules[0][1] if op==1]
  self.assertEqual(constants,[-1,1,10,11,1])

 def test_performance_json_reports_phase_and_memory(self):
  self.scene_qc('$modelname metrics\n$body m mesh.smd\n','-perfjson',str(self.root/'metrics.json'))
  metrics=json.loads((self.root/'metrics.json').read_text());self.assertEqual(metrics['schema'],1)
  self.assertGreater(metrics['peak_working_set_bytes'],0);self.assertEqual(metrics['vertices'],3)
  self.assertAlmostEqual(metrics['total_ms'],metrics['load_ms']+metrics['compile_ms']+metrics['write_ms'],delta=.01)
  self.assertTrue(metrics['stages']);self.assertTrue(any(s['tag']=='pass' for s in metrics['stages']))
  self.assertTrue(all(s['ms']>=0 and s['calls']>0 for s in metrics['stages']))

 def test_vta_eyelid_does_not_leave_unbound_pose_descriptors(self):
  self.ce_fixture()
  self.ce_compile(options='eyeball eye root 0 0 0 material 2 0 iris .5\neyelid upper face.vta lowerer 1 -.2 neutral 0 0 raiser 2 .2 split 0 eyeball eye\nflexcontroller eyelid range -1 1 lid\n%upper = lid\n')
  self.assertEqual(struct.unpack_from('<i',self.mdl('face'),260)[0],5)
  self.assertNotIn(b'upper_lid_lowerer\0',self.mdl('face'))

 def test_ragdoll_decomposition_retains_mass_parent_and_constraints(self):
  import re
  outline=[(0,0),(2,0),(2,1),(1,1),(1,2),(0,2)]
  vertices=[(x,y,z) for z in (0,1) for x,y in outline];cap=[(0,1,3),(1,2,3),(0,3,5),(3,4,5)]
  faces=[tuple(reversed(f)) for f in cap]+[tuple(v+6 for v in f) for f in cap]
  for a in range(6):b=(a+1)%6;faces.extend([(a,b,b+6),(a,b+6,a+6)])
  text='version 1\nnodes\n0 "root" -1\n1 "child" 0\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\n1 5 0 0 0 0 0\nend\ntriangles\n'
  for bone in (0,1):
   for face in faces:text+='models/debug/debugwhite\n'+''.join(f'{bone} {vertices[v][0]+5*bone} {vertices[v][1]} {vertices[v][2]} 0 0 1 0 0\n' for v in face)
  self.write('ragdoll.smd',text+'end\n')
  qc='$modelname ragdoll\n$bonecullmethod none\n$body m ragdoll.smd\n$collisionjoints ragdoll.smd { $mass 10 $rootbone root $maxconvexpieces 4 $decomposeconcave }\n'
  output=self.scene_qc(qc);self.assertEqual(len(re.findall(r'Decomposed ragdoll .*: [2-4] convex pieces',output)),2)
  phy=(self.root/'models/ragdoll.phy').read_bytes();self.assertEqual(struct.unpack_from('<i',phy,8)[0],2)
  self.assertIn(b'"parent" "root"',phy);self.assertIn(b'ragdollconstraint',phy)
  masses=[float(v) for v in re.findall(rb'"mass" "([^"]+)"',phy)];self.assertAlmostEqual(sum(masses),10,places=3)

 def test_scene_shared_skin_instances_and_vrm_path(self):
  from scene_fixtures import skinned_scene_bytes
  doc=json.loads(skinned_scene_bytes());doc['nodes'][2]['skin']=0
  for suffix in ('gltf','vrm'):
   self.write('skin.'+suffix,json.dumps(doc))
   self.scene_qc('$modelname instances\n$CEBoneRules\n$body m skin.'+suffix+'\n')
   d=self.mdl('instances');self.assertIn(b'Joint\0',d)
   vvd=(self.root/'models/instances.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
   count=struct.unpack_from('<i',vvd,16)[0];points=[struct.unpack_from('<3f',vvd,start+i*48+16) for i in range(count)]
   self.assertAlmostEqual(min(x[0] for x in points),-1);self.assertAlmostEqual(max(x[0] for x in points),1)

 def test_conflicting_shared_skin_bind_and_singular_matrix_are_rejected(self):
  from scene_fixtures import skinned_scene_bytes
  doc=json.loads(skinned_scene_bytes());doc['nodes'][2]['skin']=1;doc['skins'].append(copy.deepcopy(doc['skins'][0]))
  binary=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]));off=len(binary)
  binary.extend(struct.pack('<16f',1,0,0,0,0,1,0,0,0,0,1,0,-10,0,0,1))
  doc['bufferViews'].append({'buffer':0,'byteOffset':off,'byteLength':64});doc['accessors'].append({'bufferView':len(doc['bufferViews'])-1,'componentType':5126,'count':1,'type':'MAT4'})
  doc['skins'][1]['inverseBindMatrices']=len(doc['accessors'])-1
  def emit():
   doc['buffers'][0]={'byteLength':len(binary),'uri':'data:application/octet-stream;base64,'+base64.b64encode(binary).decode()};self.write('skin.gltf',json.dumps(doc))
  emit();text=self.scene_qc('$modelname badskin\n$body m skin.gltf\n',success=False);self.assertIn('conflicting bind poses',text)
  struct.pack_into('<16f',binary,off,*([0]*16));emit()
  self.assertIn('singular inverse bind',self.scene_qc('$modelname badskin\n$body m skin.gltf\n',success=False))

 def test_invalid_scene_animation_times_preserve_existing_output(self):
  self.scene_fixture();self.scene_qc('$modelname times\n$body m scene.gltf\n');old=self.mdl('times')
  doc=json.loads(scene_bytes());time=doc['animations'][0]['samplers'][0]['input'];view=doc['bufferViews'][doc['accessors'][time]['bufferView']]
  for values in [(1,0),(0,0),(-1,1),(0,float('nan'))]:
   blob=bytearray(base64.b64decode(doc['buffers'][0]['uri'].split(',')[1]));struct.pack_into('<2f',blob,view['byteOffset'],*values)
   doc['buffers'][0]['uri']='data:application/octet-stream;base64,'+base64.b64encode(blob).decode();self.write('scene.gltf',json.dumps(doc))
   text=self.scene_qc('$modelname times\n$body m scene.gltf\n',success=False);self.assertIn('strictly increasing',text);self.assertEqual(self.mdl('times'),old)

 def test_nested_include_error_reports_ancestry(self):
  self.write('outer.qci','$include inner.qci\n');self.write('inner.qci','$body broken missing.smd\n')
  text=self.run_qc('$modelname bad\n$include outer.qci\n',success=False)
  self.assertIn('inner.qci(1)',text);self.assertIn('included from',text);self.assertIn('outer.qci',text)

 def test_compile_bodygroup_error_retains_include_location(self):
  self.write('groups.qci',''.join(f'$bodygroup b{i} {{ blank\nblank\n}}\n' for i in range(32)))
  text=self.run_qc('$modelname bad\n$include groups.qci\n',success=False)
  self.assertIn('groups.qci(94)',text);self.assertIn("'b31'",text)

 def test_copy_explicit_weightlist_uses_positive_mask_without_changing_duration(self):
  self.animation_fixture()
  for value,expected in [(0,0),(.5,10),(1,10)]:
   self.run_qc('$modelname mask\n$weightlist mask { root '+str(value)+' }\n$animation source moving.smd\n$animation dest mesh.smd { numframes 4 copy source mask }\n$sequence original source\n$sequence idle dest\n')
   frames=self.animation_poses('mask','dest');self.assertEqual(len(frames),4)
   self.assertAlmostEqual(frames[0][0],expected,delta=.01)
   self.assertAlmostEqual(frames[-1][0],20 if value else 0,delta=.01)

 def test_ragdoll_procedural_joint_geometry_merges_into_physical_parent(self):
  header='version 1\nnodes\n0 "root" -1\n1 "hair" 0\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\n1 3 0 0 0 0 0\nend\ntriangles\n'
  points=[(0,0,0),(1,0,0),(0,1,0),(0,0,1)];mesh=header
  for bone in (0,1):
   for face in [(0,2,1),(0,1,3),(0,3,2),(1,2,3)]:
    mesh+='material\n'+''.join(f'{bone} {points[v][0]+bone*3} {points[v][1]} {points[v][2]} 0 0 1 0 0\n' for v in face)
  self.write('rig.smd',mesh+'end\n')
  base='$modelname ragmask\n$bonecullmethod none\n$body m rig.smd\n$sequence idle rig.smd\n'
  self.scene_qc(base+'$collisionjoints rig.smd { $mass 10 }\n')
  self.assertEqual(struct.unpack_from('<i',(self.root/'models/ragmask.phy').read_bytes(),8)[0],2)
  self.scene_qc(base+'$jigglebone hair { is_flexible { length 3 tip_mass 1 } }\n$collisionjoints rig.smd { $mass 10 }\n')
  phy=(self.root/'models/ragmask.phy').read_bytes();self.assertEqual(struct.unpack_from('<i',phy,8)[0],1)
  self.assertIn(b'"name" "root"',phy);self.assertNotIn(b'"name" "hair"',phy)
  self.assertIn(b'hair\0',self.mdl('ragmask'))
  old=self.mdl('ragmask')
  text=self.scene_qc(base+'$collisionjoints rig.smd { $jointmerge root hair $jointmerge hair root }\n',success=False)
  self.assertIn('cyclic collision joint merge',text);self.assertEqual(self.mdl('ragmask'),old)

 def test_fbx_hierarchy_bakes_nonuniform_scale_and_generates_normals(self):
  self.write('hierarchy.fbx',(Path(__file__).parent/'fixtures/hierarchy.fbx').read_text())
  self.scene_qc('$modelname hierarchy\n$body m hierarchy.fbx\n')
  vvd=(self.root/'models/hierarchy.vvd').read_bytes();start=struct.unpack_from('<i',vvd,56)[0]
  points=[struct.unpack_from('<3f',vvd,start+i*48+16) for i in range(3)]
  self.assertEqual(sorted(round(p[0],3) for p in points),[12,12,14])
  self.assertEqual(sorted(round(p[1],3) for p in points),[3,3,4])
  self.assertEqual({round(p[2],3) for p in points},{4})
  for i in range(3):self.assertAlmostEqual(sum(v*v for v in struct.unpack_from('<3f',vvd,start+i*48+28)),1,places=4)

 def test_generated_production_mesh_splits_without_losing_lods_or_skin_families(self):
  header='version 1\nnodes\n0 "root" -1\nend\nskeleton\ntime 0\n0 0 0 0 0 0 0\nend\ntriangles\n'
  pieces=[]
  for i in range(30000):
   x,y=(i%300)*2,(i//300)*2
   pieces.append(f'material\n0 {x} {y} 0 0 0 1 0 0\n0 {x+1} {y} 0 0 0 1 1 0\n0 {x} {y+1} 0 0 0 1 0 1\n')
  self.write('production.smd',header+''.join(pieces)+'end\n')
  groups=''.join(f'$bodygroup choice{i} {{ blank\nblank\n}}\n' for i in range(20))
  skins='$texturegroup family {\n'+''.join('{ '+('material' if i==0 else 'material'+str(i))+' }\n' for i in range(20))+'}\n'
  self.scene_qc('$modelname production\n$MaxVerts 60000\n$body m production.smd\n$lod 10 { }\n$lod 30 { }\n'+groups+skins)
  d=self.mdl('production');self.assertEqual(struct.unpack_from('<i',d,224)[0],20)
  vvd=(self.root/'models/production.vvd').read_bytes();self.assertEqual(struct.unpack_from('<i',vvd,12)[0],3)
  self.assertEqual(struct.unpack_from('<3i',vvd,16),(90000,90000,90000))
  bp=struct.unpack_from('<i',d,236)[0];model=bp+struct.unpack_from('<i',d,bp+12)[0]
  count,offset=struct.unpack_from('<2i',d,model+72);self.assertGreater(count,1)
  sizes=[struct.unpack_from('<i',d,model+offset+i*116+8)[0] for i in range(count)]
  self.assertEqual(sum(sizes),90000);self.assertLessEqual(max(sizes),60000)

 def test_copy_channel_keywords_remain_unambiguous_with_named_weightlists(self):
  self.animation_fixture()
  base='$modelname keywords\n$weightlist pos { root 0 }\n$animation source moving.smd\n'
  self.run_qc(base+'$animation dest mesh.smd { copy source pos }\n$sequence original source\n$sequence result dest\n')
  pose=self.animation_poses('keywords','dest')[0];self.assertAlmostEqual(pose[0],10,delta=.01);self.assertAlmostEqual(pose[5],0,delta=.01)
  self.run_qc(base+'$animation dest mesh.smd { copy source "pos" }\n$sequence original source\n$sequence result dest\n')
  pose=self.animation_poses('keywords','dest')[0];self.assertAlmostEqual(pose[0],0,delta=.01);self.assertAlmostEqual(pose[5],0,delta=.01)
