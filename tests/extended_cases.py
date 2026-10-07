from pathlib import Path
import struct,json,base64,subprocess,sys,copy
class ExtendedCases:
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
