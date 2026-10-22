"""Output identity, sidecar consistency and shared animation decoder regressions.

Usage: decompiler_roundtrip_test.py <compiler> <decompiler> <l4d_animswap>
All inputs are authored or mutated inside a temporary directory.
"""
from pathlib import Path
import re
import json
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import unittest

COMPILER, DECOMPILER, L4D = [str(Path(sys.argv.pop(1)).resolve()) for _ in range(3)]
HEADER = 'version 1\nnodes\n0 "root" -1\n1 "child" 0\nend\nskeleton\n'
POSE = 'time 0\n0 0 0 0 0 0 0\n1 0 0 0 0 0 0\nend\n'


def mesh(x=0, bone=0, tetra=False):
    points = [(x, 0, 0), (x+1, 0, 0), (x, 1, 0), (x, 0, 1)]
    faces = [(0, 1, 2), (0, 3, 1), (0, 2, 3), (1, 3, 2)] if tetra else [(0, 1, 2)]
    return HEADER + POSE + 'triangles\n' + ''.join(
        'mat\n' + ''.join(f'{bone} {points[i][0]} {points[i][1]} {points[i][2]} 0 0 1 0 0\n'
                         for i in face) for face in faces) + 'end\n'


def animation(distance=2):
    return HEADER + ''.join(f'time {i}\n0 {i*distance} 0 0 0 0 0\n1 0 0 0 0 0 0\n'
                            for i in range(4)) + 'end\n'


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob('*')
            if p.is_file() and '.newpage-output-locks' not in p.parts}


class DecompilerRoundtrip(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='npmdl-roundtrip-')
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def run_tool(self, exe, *args, success=True):
        proc = subprocess.run([exe, *map(str, args)], capture_output=True, timeout=60)
        log = (proc.stdout+proc.stderr).decode('utf-8', 'replace')
        if success:
            self.assertEqual(proc.returncode, 0, log)
        else:
            self.assertIn(proc.returncode, (1, 2), log)  # a handled failure, never a native crash
        return log

    def fixture(self, name='input', qc=None, files=None, app=4000):
        root = self.root/name
        root.mkdir()
        (root/'gameinfo.txt').write_text(f'GameInfo {{ FileSystem {{ SteamAppId {app} }} }}')
        for path, text in (files or {'mesh.smd': mesh(), 'anim.smd': animation()}).items():
            dst = root/path
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_text(text, encoding='utf-8')
        script = root/'model.qc'
        script.write_text('$modelname shared\n$bonealwayssetup child\n' + (qc or
            '$body body mesh.smd\n$sequence idle anim.smd\n$sequence walk anim.smd\n'
            '$sequence c1m1_intro anim.smd\n$attachment mount root 0 0 0\n'
            '$hbox 0 root -1 -1 -1 1 1 1\n'), encoding='utf-8')
        self.run_tool(COMPILER, '-nodefaultargs', '-game', root, script)
        return root/'models/shared.mdl'

    def decompile(self, source, output='out', success=True, *extra):
        dest = self.root/output
        log = self.run_tool(DECOMPILER, source, '-outdir', dest, '-smdanimation',
                            '-dmxencoding', 'keyvalues2', *extra, success=success)
        return dest, log

    def test_long_export_paths_preserve_complete_output_on_failure(self):
        source = self.fixture()
        original = source.read_bytes()
        # The final paths already exceed MAX_PATH. Transaction staging adds
        # further components, as happens with production retargeted clip names.
        parent = self.root/'long-export'/('a'*90)/('b'*90)
        for mode in ('dmx', 'smd'):
            dest = parent/mode
            arguments = [source, '-outdir', dest]
            if mode == 'smd':
                arguments += ['-smdanimation', '-dmxencoding', 'keyvalues2']
            self.run_tool(DECOMPILER, *arguments)
            files = list(dest.rglob('*.'+mode))
            self.assertTrue(files)
            self.assertTrue(all(len(str(p)) > 260 for p in files))
            before = snapshot(dest)
            self.run_tool(DECOMPILER, *arguments)
            self.assertEqual(snapshot(dest), before)
            source.write_bytes(original[:80])
            try:
                self.run_tool(DECOMPILER, *arguments, success=False)
                self.assertEqual(snapshot(dest), before)
            finally:
                source.write_bytes(original)

    def decoder_failure_check(self, source, original, *, l4d=True):
        """Prime valid output, then require handled failure and atomic preservation."""
        dest, _ = self.decompile(source)
        before = snapshot(dest)
        if l4d:
            vanilla = self.root/'decoder-vanilla'
            vanilla.mkdir()
            for code in ('teenangst','producer','namvet','biker','manager','coach','gambler','mechanic'):
                (vanilla/f'survivor_{code}.mdl').write_bytes(original)
            def target(data):
                (vanilla/'anim_producer.mdl').write_bytes(data)
                model=bytearray(data)
                struct.pack_into('<2i',model,336,1,len(model))
                model.extend(struct.pack('<2i',0,8)+b'anim_producer.mdl\0')
                struct.pack_into('<i',model,76,len(model))
                (vanilla/'survivor_producer.mdl').write_bytes(model)
            args=('-vanilla',vanilla,'-rig','zoey','-replace','rochelle','-retarget','-keepintro',
                  '-o',self.root/'decoder-l4d/swap.qci')
            target(original);self.run_tool(L4D,*args)
            l4d_before=snapshot(self.root/'decoder-l4d')
        def check(data, message):
            source.write_bytes(data)
            _,log=self.decompile(source,success=False)
            self.assertIn(message,log);self.assertEqual(snapshot(dest),before)
            if l4d:
                target(data);log=self.run_tool(L4D,*args,success=False)
                self.assertIn(message,log);self.assertEqual(snapshot(self.root/'decoder-l4d'),l4d_before)
        return check

    def test_shared_rle_rotation_conflicts_and_negative_stream_offsets(self):
        source=self.fixture();original=source.read_bytes();check=self.decoder_failure_check(source,original)
        count,table=struct.unpack_from('<2i',original,180)
        for mode in ('raw-rot-conflict','animated-rot-conflict','negative-offset'):
            with self.subTest(mode=mode):
                data=bytearray(original)
                for i in range(count):
                    anim=table+i*100;record=anim+struct.unpack_from('<i',original,anim+56)[0]
                    flags=original[record+1]
                    if mode=='negative-offset':
                        self.assertTrue(flags&4)
                        ptr=record+4+(8 if flags&32 else 6 if flags&(2|8) else 0)
                        axis=next(k for k in range(3) if struct.unpack_from('<h',original,ptr+2*k)[0])
                        struct.pack_into('<h',data,ptr+2*axis,-2)
                    else:data[record+1]=flags|(2|32 if mode=='raw-rot-conflict' else 2|8)
                check(data,'invalid RLE')

    def test_shared_frame_animation_flags_and_stride_reject_corruption(self):
        source=self.fixture();data=bytearray(source.read_bytes())
        count,table=struct.unpack_from('<2i',data,180)
        bones=struct.unpack_from('<i',data,156)[0]
        # Author a legal, unsectioned external-format FrameAnim payload directly;
        # this keeps the decoder test independent of the compiler's encoding choice.
        for i in range(count):
            anim=table+i*100;self.assertEqual(struct.unpack_from('<i',data,anim+84)[0],0)
            frame=len(data);start=24+bones
            data.extend(struct.pack('<6i',start,start,12,0,0,0)+bytes([0x10])+bytes(bones-1))
            data.extend(b''.join(struct.pack('<3f',10.0*f,20.0,30.0) for f in range(4)))
            struct.pack_into('<i',data,anim+12,0x40)
            struct.pack_into('<2i',data,anim+52,0,frame-anim)
        struct.pack_into('<i',data,76,len(data));source.write_bytes(data)
        original=bytes(data)
        dest,_=self.decompile(source,'frame-control')
        clips=list(dest.rglob('anims/*.smd'));self.assertEqual(len(clips),count)
        for clip in clips:
            poses=re.findall(r'(?m)^time (\d+)\n0 ([^\n]+)',clip.read_text())
            self.assertEqual(len(poses),4)
            for frame,pose in poses:
                # SMD export rotates the MDL root into the QC source basis.
                for actual,expected in zip(map(float,pose.split()[:3]),(20.0,-10.0*int(frame),30.0)):
                    self.assertAlmostEqual(actual,expected,places=4)
        check=self.decoder_failure_check(source,original)
        for mode in ('rotation-representation','constant-and-animated','short-stride','negative-stride'):
            with self.subTest(mode=mode):
                data=bytearray(original)
                for i in range(count):
                    anim=table+i*100;self.assertTrue(struct.unpack_from('<i',original,anim+12)[0]&0x40)
                    frame=anim+struct.unpack_from('<i',original,anim+56)[0]
                    if mode=='rotation-representation':data[frame+24]|=2|64
                    elif mode=='constant-and-animated':data[frame+24]|=1|4
                    else:
                        length=struct.unpack_from('<i',original,frame+8)[0]
                        self.assertGreater(length,0)
                        struct.pack_into('<i',data,frame+8,length-1 if mode=='short-stride' else -1)
                check(data,'frame-animation')

    def test_long_external_allzeros_animation_and_decoder_memory_budget(self):
        source=self.fixture(qc='$body m mesh.smd\n$animationcullmethod none\n'
            '$sequence idle mesh.smd\n$sequence walk mesh.smd\n$sequence c1m1_intro mesh.smd\n',
            files={'mesh.smd':mesh()})
        original=source.read_bytes();data=bytearray(original)
        count,table=struct.unpack_from('<2i',original,180)
        for i in range(count):
            anim=table+i*100
            # ALLZEROS has no payload and decodes to the skeleton's bind pose.
            struct.pack_into('<i',data,anim+12,0x20)
            struct.pack_into('<i',data,anim+16,6001)
            struct.pack_into('<2i',data,anim+52,0,0)
        source.write_bytes(data)
        dest,_=self.decompile(source,'long-control')
        clips=list(dest.rglob('anims/*.smd'));self.assertEqual(len(clips),count)
        for clip in clips:self.assertEqual(len(re.findall(r'(?m)^time ',clip.read_text())),6001)
        # L4D also decodes this legal long clip as the successful baseline.
        check=self.decoder_failure_check(source,bytes(data))
        huge=bytearray(data)
        for i in range(count):struct.pack_into('<i',huge,table+i*100+16,2147483647)
        check(huge,'decoded animation exceeds the memory budget')

    def test_ik_base_recovery_rejects_bad_chain_bone_and_unrepresentable_phase(self):
        nodes='0 "root" -1\n1 "child" 0\n2 "foot" 1\n'
        bind='0 0 0 0 0 0 0\n1 1 0 0 0 0 0\n2 1 .1 0 0 0 0\n'
        head='version 1\nnodes\n'+nodes+'end\nskeleton\n'
        base=head+'time 0\n'+bind+'end\n'
        moving=head+''.join(f'time {i}\n0 {i*.25} 0 0 0 0 0\n1 1 0 0 0 0 0\n2 1 .1 0 0 0 0\n' for i in range(4))+'end\n'
        source=self.fixture(qc='$body m mesh.smd\n$ikchain leg foot\n$animationcullmethod none\n'
            '$animation base base.smd\n$animation move anim.smd { subtract base 0 ikrule leg touch root usesource }\n'
            '$sequence idle base\n$sequence walk move\n',files={'mesh.smd':base+'triangles\n'+mesh().split('triangles\n',1)[1],
            'base.smd':base,'anim.smd':moving})
        original=source.read_bytes();check=self.decoder_failure_check(source,original,l4d=False)
        count,table=struct.unpack_from('<2i',original,180)
        anim=next(table+i*100 for i in range(count) if struct.unpack_from('<i',original,table+i*100+12)[0]&4)
        self.assertGreater(struct.unpack_from('<i',original,anim+60)[0],0)
        rule=anim+struct.unpack_from('<i',original,anim+64)[0]
        self.assertGreater(struct.unpack_from('<i',original,rule+60)[0],0)
        chain=struct.unpack_from('<i',original,288)[0]
        links=chain+struct.unpack_from('<i',original,chain+12)[0]
        for mode in ('chain-end','nan-start','overflow-end'):
            with self.subTest(mode=mode):
                data=bytearray(original)
                if mode=='chain-end':struct.pack_into('<i',data,links+2*28,2147483647)
                elif mode=='nan-start':struct.pack_into('<f',data,rule+76,float('nan'))
                else:struct.pack_into('<f',data,rule+88,1e30)
                check(data,'IK chain end bone' if mode=='chain-end' else 'IK phase')

    def test_vvd_vertex_payload_rejection_preserves_old_output(self):
        source = self.fixture()
        vvd = source.with_suffix('.vvd')
        original = vvd.read_bytes()
        vertex = struct.unpack_from('<i', original, 56)[0]
        dest, _ = self.decompile(source)
        before = snapshot(dest)
        cases = [('count-zero', 15, 'B', 0), ('count-four', 15, 'B', 4),
                 ('bone-index', 12, 'B', 255), ('weight-nan', 0, 'f', float('nan')),
                 ('weight-negative', 0, 'f', -1), ('weight-sum', 0, 'f', 0.5),
                 ('weight-over-one', 0, 'f', 1.0001),
                 ('weight-beyond-roundoff', 0, 'f', 1 + 5 * 2**-23),
                 ('position-nan', 16, 'f', float('nan')),
                 ('normal-infinity', 28, 'f', float('inf')),
                 ('uv-infinity', 40, 'f', -float('inf'))]
        for label, offset, fmt, value in cases:
            with self.subTest(label=label):
                data = bytearray(original)
                struct.pack_into('<' + fmt, data, vertex + offset, value)
                vvd.write_bytes(data)
                _, log = self.decompile(source, success=False)
                self.assertIn('invalid VVD vertex', log)
                self.assertEqual(snapshot(dest), before)
        vvd.write_bytes(original)
        self.decompile(source)

    def test_shipped_vvd_weight_roundoff_is_normalized(self):
        source = self.fixture()
        vvd = source.with_suffix('.vvd')
        original = vvd.read_bytes()
        vertex = struct.unpack_from('<i', original, 56)[0]
        dest, _ = self.decompile(source)
        # Unchanged unit-weight output is the independent reference. Exporting
        # the official survivor's one-ULP overshoot must produce the same mesh.
        reference = {p.relative_to(dest): p.read_bytes() for p in dest.rglob('*.dmx')}
        self.assertTrue(reference)
        for ulps in (1, 4):
            with self.subTest(ulps=ulps):
                data = bytearray(original)
                struct.pack_into('<f', data, vertex, 1 + ulps * 2**-23)
                vvd.write_bytes(data)
                self.decompile(source)
                self.assertEqual(reference, {p.relative_to(dest): p.read_bytes()
                                            for p in dest.rglob('*.dmx')})

    def test_sidecar_checksum_rejection_preserves_old_output(self):
        source = self.fixture()
        dest, _ = self.decompile(source)
        before = snapshot(dest)
        for ext, offset in (('.vvd', 8), ('.dx90.vtx', 16)):
            with self.subTest(sidecar=ext):
                path = source.with_suffix(ext)
                old = path.read_bytes()
                data = bytearray(old)
                struct.pack_into('<I', data, offset, struct.unpack_from('<I', data, offset)[0] ^ 1)
                path.write_bytes(data)
                _, log = self.decompile(source, success=False)
                self.assertIn('checksum does not match MDL', log)
                self.assertEqual(snapshot(dest), before)
                path.write_bytes(old)

    def test_attachment_hitbox_ranges_and_references_are_not_empty_tables(self):
        source = self.fixture()
        old = source.read_bytes()
        dest, _ = self.decompile(source)
        before = snapshot(dest)
        at = struct.unpack_from('<i', old, 244)[0]
        hs = struct.unpack_from('<i', old, 176)[0]
        hb = hs + struct.unpack_from('<i', old, hs+8)[0]
        for label, offset, value in [('attachment',244,len(old)+512), ('hitbox',176,len(old)+512),
                ('hitbox',hs+8,len(old)+512), ('attachment',240,-1), ('hitbox',hs+4,-1),
                ('attachment',at+8,999), ('hitbox',hb,999)]:
            with self.subTest(label=label, offset=offset):
                data = bytearray(old)
                struct.pack_into('<i',data,offset,value)
                source.write_bytes(data)
                _, log = self.decompile(source, success=False)
                self.assertIn(label, log.lower())
                self.assertEqual(snapshot(dest), before)
        source.write_bytes(old)

    def test_skinned_lods_survive_roundtrip(self):
        for app in (4000, 730):
            with self.subTest(app=app):
                source = self.fixture(str(app), '$body m mesh.smd\n$sequence idle mesh.smd\n'
                    '$skinnedlods\n$lod 10 { replacemodel mesh.smd lower.smd }\n',
                    {'mesh.smd':mesh(), 'lower.smd':mesh(bone=1)}, app)
                dest, _ = self.decompile(source, 'out'+str(app))
                qc = next(dest.rglob('shared.qc'))
                self.assertRegex(qc.read_text(), r'(?m)^\$skinnedlods\b')
                rebuilt = self.root/('rebuilt'+str(app))
                self.run_tool(COMPILER,'-nodefaultargs','-game',source.parent.parent,'-OutDir',rebuilt,qc)
                def weights(path):
                    b = path.read_bytes()
                    n, off = struct.unpack_from('<i',b,16)[0], struct.unpack_from('<i',b,56)[0]
                    return sorted(tuple((b[off+i*48+12+j],round(struct.unpack_from('<f',b,off+i*48+j*4)[0],6))
                                        for j in range(b[off+i*48+15])) for i in range(n))
                self.assertEqual(weights(next(rebuilt.rglob('shared.vvd'))), weights(source.with_suffix('.vvd')))

    def test_internal_mesh_case_lod_physics_and_joints_names(self):
        cases = [
            ('case', '$body Mesh a.smd\n$body mesh b.smd\n', 2),
            ('lod', '$body first a.smd\n$body first_lod1 b.smd\n'
                    '$lod 10 { replacemodel a.smd c.smd replacemodel b.smd d.smd }\n', 4),
            ('physics', '$body shared_physics a.smd\n$collisionmodel hull.smd { $mass 1 }\n', 2),
            ('joints', '$body shared_joints a.smd\n$hbox 0 root -1 -1 -1 1 1 1\n', 2),
        ]
        for name, qc, count in cases:
            with self.subTest(name=name):
                source = self.fixture(name, qc, {'a.smd':mesh(0),'b.smd':mesh(10),
                    'c.smd':mesh(20),'d.smd':mesh(30),'hull.smd':mesh(40,tetra=True)})
                extra = ('-datamodeljoints',) if name == 'joints' else ()
                dest, _ = self.decompile(source, name+'-out', True, *extra)
                paths = list(dest.rglob('meshes/*.dmx'))
                self.assertEqual(len(paths), count)
                self.assertEqual(len({p.name.casefold() for p in paths}), count)
                script = next(dest.rglob('shared.qc'))
                for ref in re.findall(r'"(meshes/[^"\n]+\.dmx)"', script.read_text(encoding='utf-8')):
                    self.assertTrue((script.parent/ref).is_file(), ref)
                if name in ('case', 'lod'):
                    # Different geometry remains different, rather than just differently named.
                    positions = [re.search(r'"positions" "vector3_array"\s*\[(.*?)\]',
                                 p.read_text(encoding='utf-8'), re.S).group(1) for p in paths]
                    self.assertEqual(len(set(positions)), count)

    def test_animation_case_aliases_keep_distinct_motion(self):
        source = self.fixture(qc='$body m mesh.smd\n$animationcullmethod none\n'
            '$animation Walk a.smd\n$animation Other b.smd\n$sequence s1 Walk\n$sequence s2 Other\n',
            files={'mesh.smd':mesh(),'a.smd':animation(1),'b.smd':animation(7)})
        data = bytearray(source.read_bytes())
        n, at = struct.unpack_from('<2i',data,180)
        for i in range(n):
            a = at+i*100
            s = a+struct.unpack_from('<i',data,a+4)[0]
            if data[s:data.index(0,s)] == b'Other': data[s:s+6] = b'walk\0\0'
        source.write_bytes(data)
        dest, _ = self.decompile(source)
        paths = list(dest.rglob('anims/*.smd'))
        self.assertEqual(len(paths), 2)
        self.assertEqual(len({p.read_bytes() for p in paths}), 2)
        self.run_tool(COMPILER,'-nodefaultargs','-game',source.parent.parent,'-OutDir',self.root/'rebuilt',
                      next(dest.rglob('shared.qc')))

    def test_phy_bad_header_checksum_and_truncation_fail_missing_is_diagnosed(self):
        source = self.fixture(qc='$body m mesh.smd\n$collisionmodel mesh.smd { $mass 1 }\n',
                              files={'mesh.smd':mesh(tetra=True)})
        phy = source.with_suffix('.phy')
        old = phy.read_bytes()
        dest, _ = self.decompile(source)
        before = snapshot(dest)
        bad_checksum = bytearray(old)
        bad_checksum[12] ^= 1
        for broken in (b'truncated', old[:20], old[:-10], bytes(bad_checksum)):
            phy.write_bytes(broken)
            _, log = self.decompile(source, success=False)
            self.assertIn('PHY',log)
            self.assertEqual(snapshot(dest),before)
        phy.unlink()
        _, log = self.decompile(source,'missing-phy')
        self.assertIn('collision completeness cannot be verified',log)

    def test_invalid_animation_records_fail_in_decompiler_and_l4d(self):
        source = self.fixture()
        original = source.read_bytes()
        n, at = struct.unpack_from('<2i',original,180)
        vanilla = self.root/'vanilla'
        vanilla.mkdir()
        for code in ('teenangst','producer','namvet','biker','manager','coach','gambler','mechanic'):
            (vanilla/f'survivor_{code}.mdl').write_bytes(original)
        def target(data):
            (vanilla/'anim_producer.mdl').write_bytes(data)
            m = bytearray(data)
            struct.pack_into('<2i',m,336,1,len(m))
            m.extend(struct.pack('<2i',0,8)+b'anim_producer.mdl\0')
            struct.pack_into('<i',m,76,len(m))
            (vanilla/'survivor_producer.mdl').write_bytes(m)
        args = ('-vanilla',vanilla,'-rig','zoey','-replace','rochelle','-retarget','-keepintro',
                '-o',self.root/'l4d-out/swap.qci')
        target(original)
        self.run_tool(L4D,*args)
        l4d_before = snapshot(self.root/'l4d-out')
        dest, _ = self.decompile(source)
        before = snapshot(dest)
        for mode in ('movement-negative','movement-past-end','data-past-end','rle-total-zero','rle-valid-past-total'):
            with self.subTest(mode=mode):
                m = bytearray(original)
                for i in range(n):
                    a = at+i*100
                    if mode.startswith('movement'):
                        end = -2 if mode == 'movement-negative' else 100
                        struct.pack_into('<2i',m,a+20,1,len(m)-a)
                        m.extend(struct.pack('<ii9f',end,64,6,6,0,1,0,0,6,0,0))
                    elif mode == 'data-past-end':
                        struct.pack_into('<i',m,a+56,len(m)-1-a)
                    else:
                        data = a+struct.unpack_from('<i',m,a+56)[0]
                        # The first record's position channel follows its raw rotation.
                        flags = m[data+1]
                        self.assertTrue(flags & 4)
                        posptr = data+4+(8 if flags & 32 else 6 if flags & (2|8) else 0)
                        rel = next(struct.unpack_from('<h',m,posptr+k*2)[0] for k in range(3)
                                   if struct.unpack_from('<h',m,posptr+k*2)[0])
                        stream = posptr+rel
                        if mode == 'rle-total-zero': m[stream+1] = 0
                        else: m[stream] = m[stream+1]+1
                struct.pack_into('<i',m,76,len(m))
                source.write_bytes(m)
                _, log = self.decompile(source, success=False)
                self.assertIn('animation',log.lower())
                self.assertEqual(snapshot(dest),before)
                target(m)
                log = self.run_tool(L4D,*args,success=False)
                self.assertIn('animation',log.lower())
                self.assertEqual(snapshot(self.root/'l4d-out'),l4d_before)

    def quality_record(self, log):
        return json.loads(next(line[len('@quality '):] for line in log.splitlines() if line.startswith('@quality ')))

    def test_quality_report_matches_published_files_and_failed_exit(self):
        source = self.fixture()
        data = bytearray(source.read_bytes())
        table = struct.unpack_from('<i', data, 160)[0]
        # Deliberately invalid name bytes must remain representable in valid UTF-8 JSON.
        at = table + 216
        struct.pack_into('<i', data, at, len(data)-at)
        data.extend(b'bad\xffname\0')
        struct.pack_into('<i', data, 76, len(data))
        source.write_bytes(data)
        dest, log = self.decompile(source, 'quality', True, '-qualityreport')
        report = self.quality_record(log)
        self.assertTrue(report['success']); self.assertEqual(report['exit_code'], 0)
        self.assertEqual(len(report['renamed_bones']), 1)
        self.assertEqual(bytes.fromhex(report['renamed_bones'][0]['original_bytes_hex']), b'bad\xffname')
        saved = next(dest.rglob('export-report.json'))
        self.assertEqual(json.loads(saved.read_text()), report)
        actual = {str(p.relative_to(saved.parent)).replace('\\','/') for p in saved.parent.rglob('*') if p.is_file()}
        self.assertEqual(set(report['written_files']), actual)
        before = snapshot(dest)
        source.with_suffix('.vvd').unlink()
        _, log = self.decompile(source, 'quality', False, '-qualityreport')
        failure = self.quality_record(log)
        self.assertFalse(failure['success']); self.assertNotEqual(failure['exit_code'], 0)
        self.assertTrue(failure['errors']); self.assertTrue(failure['missing_dependencies'])
        self.assertEqual(failure['written_files'], [])
        self.assertEqual(snapshot(dest), before)

    def test_selected_assets_preserve_paths_and_animation_dependency_closure(self):
        source = self.fixture(qc='$body body mesh.smd\n$body extra lower.smd\n'
            '$skinnedlods\n$lod 10 { replacemodel mesh.smd lower.smd }\n'
            '$animation base mesh.smd\n$animation a_delta anim.smd { subtract base 0 }\n'
            '$sequence layer { a_delta hidden }\n$sequence chosen { anim.smd addlayer layer }\n'
            '$sequence unused anim.smd\n',
            files={'mesh.smd':mesh(),'lower.smd':mesh(3),'anim.smd':animation()})
        library = self.root/'library'
        for folder in ('one','two'):
            target = library/folder
            target.mkdir(parents=True)
            for path in source.parent.glob('shared.*'): shutil.copy2(path, target/path.name)
        args = [library/'one/shared.mdl',library/'two/shared.mdl','-outdir',self.root/'selected',
                '-preservepaths',library,'-sequence','chosen','-bodygroup','0','-lod','1',
                '-dmxencoding','keyvalues2']
        log = self.run_tool(DECOMPILER,*args)
        reports = list((self.root/'selected').rglob('export-report.json'))
        self.assertEqual(len(reports),2)
        for report in reports:
            result=json.loads(report.read_text());self.assertEqual(result['export_kind'],'assets_only')
            self.assertIn(report.parent.parent.name,('one','two'))
            self.assertFalse(list(report.parent.glob('*.qc')))
            clips={p.stem for p in (report.parent/'anims').glob('*.dmx')}
            self.assertIn('chosen',clips);self.assertIn('a_delta',clips);self.assertIn('base',clips)
            self.assertNotIn('unused',clips)
            meshes=list((report.parent/'meshes').glob('*.dmx'))
            self.assertEqual(len(meshes),1);self.assertTrue(meshes[0].stem.endswith('_lod1'))
        before=snapshot(self.root/'selected')
        self.run_tool(DECOMPILER,*args,'-lod','7',success=False)
        self.assertEqual(snapshot(self.root/'selected'),before)
        self.run_tool(DECOMPILER,source,'-preservepaths',library,'-outdir',self.root/'escape',success=False)
        self.assertFalse((self.root/'escape').exists())

    def test_l4d_blend_grid_pose_layer_roundtrip(self):
        source=self.fixture(qc='$body body mesh.smd\n$animation reference mesh.smd\n'
            '$sequence idle reference\n'
            '$poseparameter move_x -1 1\n$poseparameter move_y -1 1\n'
            '$animation a0 anim.smd { fps 23.7 }\n$animation a1 other.smd { fps 30 }\n'
            '$weightlist upper { root 0 child 1 }\n$sequence layer { other.smd hidden weightlist upper }\n'
            '$sequence c1m1_intro { a0 a1 a1 a0 blendwidth 2 blend move_x -1 1 blend move_y -1 1 '
            'blendlayer layer -1 -0.5 0.5 1 poseparameter move_x { event 1004 2 "test" } }\n',
            files={'mesh.smd':mesh(),'anim.smd':animation(),'other.smd':animation(4)})
        vanilla=self.root/'blend-vanilla';vanilla.mkdir()
        for code in ('teenangst','producer'):
            shutil.copy2(source,vanilla/f'survivor_{code}.mdl')
        shutil.copy2(source,vanilla/'survivor_producer_light.mdl')
        out=self.root/'blend-out/swap.qci'
        self.run_tool(L4D,'-vanilla',vanilla,'-rig','zoey','-replace','rochelle','-retarget','-keepintro','-o',out)
        light=out.with_name('swap_Light.qci')
        text=light.read_text()
        self.assertIn('blendwidth 2',text);self.assertIn('blend "move_x" -1 1',text)
        self.assertIn('poseparameter "move_x"',text)
        self.assertIn('$weightlist "__weights_layer_light_',text)
        self.assertRegex(text,r'blendlayer "layer" -1 -0.5 0.5 1 poseparameter "move_x"')
        self.assertNotIn('REPLACE ME',text)
        self.assertEqual(len(list((out.parent/'anims').glob('*c1m1_intro*blend*.dmx'))),4)
        qc=out.parent/'rebuild.qc'
        qc.write_text('$modelname rebuilt_blend\n$bonealwayssetup child\n$body body "'+str(source.parent.parent/'mesh.smd').replace('\\','/')+'"\n'
                      '$animation a_reference "'+str(source.parent.parent/'mesh.smd').replace('\\','/')+'"\n'
                      '$include "swap_Light.qci"\n')
        self.run_tool(COMPILER,'-nodefaultargs','-game',source.parent.parent,'-OutDir',self.root/'blend-rebuilt',qc)
        rebuilt=next((self.root/'blend-rebuilt').rglob('rebuilt_blend.mdl'))
        dest,_=self.decompile(rebuilt,'blend-decompiled')
        regenerated=next(dest.rglob('*.qc')).read_text()
        self.assertIn('blendwidth 2',regenerated)
        self.assertIn('poseparameter "move_x"',regenerated)
        self.assertIn('23.7',regenerated)
        self.assertIn('$weightlist',regenerated)
        # Also inspect compiled weights independently of the QC reconstruction.
        def layer_weights(path):
            data=path.read_bytes();bones=struct.unpack_from('<i',data,156)[0]
            count,table=struct.unpack_from('<2i',data,188)
            for index in range(count):
                seq=table+index*212;label=seq+struct.unpack_from('<i',data,seq+4)[0]
                if data[label:data.index(b'\0',label)]==b'layer':
                    start=seq+struct.unpack_from('<i',data,seq+156)[0]
                    return struct.unpack_from('<'+str(bones)+'f',data,start)
            self.fail('missing layer sequence')
        self.assertEqual(layer_weights(source),(0.0,1.0))
        self.assertEqual(layer_weights(rebuilt),layer_weights(source))

    def test_reduced_dmx_keeps_loop_event_boundaries_and_preserves_sampled_motion(self):
        from dmx_keys import channels, sample, error
        anim=HEADER+''.join(f'time {i}\n0 {i*.25} 0 0 0 0 {i*.01}\n1 0 0 0 0 0 0\n' for i in range(21))+'end\n'
        source=self.fixture(qc='$body body mesh.smd\n$sequence motion { anim.smd fps 30 loop { event 1004 10 "x" } }\n',
                            files={'mesh.smd':mesh(),'anim.smd':anim})
        def export(folder,*extra):
            root=self.root/folder
            self.run_tool(DECOMPILER,source,'-outdir',root,'-dmxencoding','keyvalues2',*extra)
            return channels(next(root.rglob('anims/motion.dmx')))
        exact=export('exact-keys')
        reduced=export('reduced-keys','-reducepos','.01','-reduceangle','.02')
        self.assertLess(sum(len(c[1]) for c in reduced.values()),sum(len(c[1]) for c in exact.values()))
        for name,channel in exact.items():
            kind,times,values=channel
            for boundary in (0,.3,.3333,.3667,.6667):
                self.assertLess(min(abs(t-boundary) for t in reduced[name][1]),1e-6)
            probes=set(times)
            for a,b in zip(times,times[1:]):probes.update(a+(b-a)*i/8 for i in range(1,8))
            for time in probes:
                self.assertLessEqual(error(sample(channel,time),sample(reduced[name],time),kind=='quaternion'),
                                     (.02 if kind=='quaternion' else .01)+2e-4,name)


if __name__ == '__main__':
    unittest.main()
