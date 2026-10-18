#!/usr/bin/env python3
"""VMD/L4D batch publication and packaged-compiler invocation regressions.

Use an isolated --work directory, the built --bin-dir, and the separately built
tests/subtool_transaction_test.cpp executable as --probe. Original tools and
models are never edited. The probe is a fake compiler only for argv/status tests;
the success case also runs the actual packaged compiler.
"""
import argparse
import contextlib
import ctypes
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
import wave

from subtools_integrity_test import target_mdl, survivor, vmd, integer


def snapshot(paths):
    return {str(path): path.read_bytes() for path in paths}


def decode_arguments(path):
    data = path.read_bytes()
    result = []
    offset = 0
    while offset < len(data):
        size, = struct.unpack_from('<I', data, offset)
        offset += 4
        result.append(data[offset:offset+size].decode('utf-8'))
        offset += size
    return result


@contextlib.contextmanager
def lock_destination(path):
    # Deny delete sharing so the actual second/later rename fails after earlier
    # outputs have already been installed. This needs no hook in the tool.
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.CreateFileW.argtypes = [ctypes.c_wchar_p, ctypes.c_ulong, ctypes.c_ulong,
                                  ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong, ctypes.c_void_p]
    kernel.CreateFileW.restype = ctypes.c_void_p
    kernel.CloseHandle.argtypes = [ctypes.c_void_p]
    handle = kernel.CreateFileW(str(path), 0x80000000, 1, None, 3, 0x80, None)
    assert handle != ctypes.c_void_p(-1).value, ctypes.get_last_error()
    try:
        yield
    finally:
        kernel.CloseHandle(handle)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bin-dir', required=True, type=Path)
    parser.add_argument('--probe', required=True, type=Path)
    parser.add_argument('--work', required=True, type=Path)
    args = parser.parse_args()
    binary, root, probe = args.bin_dir.resolve(), args.work.resolve(), args.probe.resolve()
    root.mkdir(parents=True, exist_ok=False)
    suffix = '.exe' if os.name == 'nt' else ''
    tools = binary / 'subtools' if (binary / 'subtools').is_dir() else binary
    compiler = binary / ('NewPageMergeMDL' + suffix)
    records = []

    def run(name, executable, argv, *, code=0, protected=(), env=None, message=None):
        before = snapshot(protected)
        result = subprocess.run([str(executable), *map(str, argv)], cwd=root,
                                env=env, capture_output=True, timeout=120)
        log = root / (name + '.log')
        log.write_bytes(result.stdout + result.stderr)
        entry = dict(name=name, argv=[str(executable), *map(str, argv)], returncode=result.returncode,
                     log=str(log), protected=list(before))
        records.append(entry)
        (root / 'report.json').write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding='utf-8')
        assert result.returncode == code, (entry, log.read_text(encoding='utf-8', errors='replace'))
        assert before == snapshot(protected), (name, 'protected outputs changed')
        if message:
            assert message.lower() in (result.stdout + result.stderr).decode('utf-8', errors='replace').lower(), entry
        print(name, 'passed', flush=True)

    # Later camera output errors preserve bodies and auxiliary output from the
    # first clip as well as existing files belonging to the second clip.
    motions = root / 'motion outputs'
    motions.mkdir()
    target = root / 'target.mdl'
    target_mdl(target)
    for name in ('dance', 'jump'):
        vmd(motions / (name + '.vmd'))
    vmd_tool = tools / ('vmd2valvebiped' + suffix)
    conversion = ['-mdl', target, '-vmd', motions/'dance.vmd', '-vmd', motions/'jump.vmd', '-camerafov', 'dmx']
    run('vmd_valid_body_camera_batch', vmd_tool, conversion)
    outputs = sorted(motions.glob('*.dmx')) + sorted(motions.glob('*.smd'))
    assert len(outputs) == 6, outputs
    for path in outputs:
        path.write_bytes(b'previous:' + path.name.encode())
    if os.name == 'nt':
        with lock_destination(motions/'jump_camera.dmx'):
            run('vmd_real_later_commit_failure_rolls_back',vmd_tool,conversion,code=1,protected=outputs)
    blocked = motions / 'jump_camera.dmx'
    original = blocked.read_bytes()
    blocked.unlink()
    blocked.mkdir()
    protected = [p for p in outputs if p != blocked]
    run('vmd_later_camera_failure_preserves_all', vmd_tool, conversion, code=1, protected=protected,
        message='not a regular file')
    blocked.rmdir()
    blocked.write_bytes(original)

    # Packaged-name detection is checked in a copied Unicode/space directory;
    # mdlcompiler is deliberately another probe with a failure exit code.
    package = root / '发行 & packaged tools'
    (package/'subtools').mkdir(parents=True)
    packaged = package/'subtools'/vmd_tool.name
    shutil.copy2(vmd_tool, packaged)
    renamed_compiler = package/('NewPageMergeMDL'+suffix)
    shutil.copy2(probe, renamed_compiler)
    source = root/'源 输入 & literal%PATH%'
    game = root/'游戏 & output'
    source.mkdir(); game.mkdir()
    (game/'gameinfo.txt').write_text('GameInfo { game "fixture" FileSystem { SteamAppId 220 SearchPaths { Game "|gameinfo_path|." } } }')
    with wave.open(str(motions/'dance.wav'), 'wb') as audio:
        audio.setparams((1,2,22050,0,'NONE','not compressed'))
        audio.writeframes(bytes(22050*2))
    compiling = ['-mdl',target,'-vmd',motions/'dance.vmd','-compile','nested/result',
                 '-srcdir',source,'-game',game,'-sound','-camerafov','dmx']
    invocation = root/'compiler-arguments.bin'
    env = dict(os.environ, NEWPAGE_TEST_CHILD_RECORD=str(invocation), NEWPAGE_TEST_CHILD_MODEL='nested/result.mdl')
    run('vmd_packaged_compiler_name_and_argv', packaged, compiling, env=env)
    child = decode_arguments(invocation)
    assert Path(child[0]) == renamed_compiler and child[1:3] == ['-game',str(game)], child
    assert child[3] == '-OutDir' and Path(child[4]) != game and Path(child[5]).name == 'result.qc', child
    assert len(child) == 6, child
    generated = sorted(p for base in (source,game) for p in base.rglob('*') if p.is_file() and p.name!='gameinfo.txt')
    assert len(generated) == 7, generated
    assert (game/'models/nested/result.mdl').read_bytes() == b'compiled fixture'
    for path in generated:
        path.write_bytes(b'previous:' + path.name.encode())
    stale = game/'models/nested/result.vertexanim.json'
    stale.write_bytes(b'previous vertex animation')
    generated.append(stale)
    run('vmd_compiler_nonzero_preserves_every_output', packaged, compiling, code=23,
        protected=generated, env=dict(env,NEWPAGE_TEST_CHILD_EXIT='23'), message='status 23')
    if os.name == 'nt':
        with lock_destination(game/'models/nested/result.mdl'):
            run('vmd_compile_real_commit_failure_rolls_back_auxiliary_outputs',packaged,compiling,
                code=1,protected=generated,env=env)
    # Missing dependencies are detected before any output is published.
    renamed_compiler.rename(package/('mdlcompiler'+suffix))
    run('vmd_legacy_compiler_name_not_used', packaged, compiling, code=1,
        protected=generated, message='cannot find NewPageMergeMDL')
    shutil.copy2(probe, renamed_compiler)
    late = game/'sound/mmd/dance.wav'
    old = late.read_bytes(); late.unlink(); late.mkdir()
    run('vmd_late_audio_destination_failure_preserves_batch', packaged, compiling, code=1,
        protected=[p for p in generated if p!=late], env=env, message='not a regular file')
    late.rmdir(); late.write_bytes(old)
    # Actual NewPage compiler invocation, including relative QC clip lookup.
    shutil.copy2(compiler, renamed_compiler)
    run('vmd_actual_packaged_compile', packaged, compiling)
    assert (game/'models/nested/result.mdl').read_bytes()[:4] == b'IDST'
    assert not stale.exists(), 'obsolete model companion was not removed on success'

    # Ordinary -all failure at a later QCI must preserve every earlier result.
    vanilla = root/'vanilla'; vanilla.mkdir()
    for code in ('namvet','teenangst','biker','manager','coach','gambler','mechanic','producer'):
        survivor(vanilla/f'survivor_{code}.mdl')
    all_output = root/'all_qci'
    l4d_tool = tools/('l4d_animswap'+suffix)
    all_args = ['-vanilla',vanilla,'-all','-outdir',all_output]
    run('l4d_all_success', l4d_tool, all_args)
    qcis = sorted(all_output.glob('*.qci'))
    assert len(qcis)==56, len(qcis)
    for path in qcis:path.write_bytes(b'previous:'+path.name.encode())
    late = all_output/'Anims_RigToRochelle_ReplaceEllis.qci'
    assert late in qcis, qcis
    if os.name == 'nt':
        with lock_destination(late):
            run('l4d_real_later_commit_failure_rolls_back_all',l4d_tool,all_args,code=1,protected=qcis)
    old = late.read_bytes();late.unlink();late.mkdir()
    run('l4d_later_qci_failure_preserves_entire_all_batch', l4d_tool, all_args,
        code=1, protected=[p for p in qcis if p!=late],message='not a regular file')
    late.rmdir();late.write_bytes(old)

    # Real MDL fixture for retarget output: required intro animation comes from
    # the target's include and the optional Light model supplies local clips.
    fixture = root/'retarget-source';fixture.mkdir()
    header='version 1\nnodes\n0 "root" -1\nend\nskeleton\n'
    (fixture/'mesh.smd').write_text(header+'time 0\n0 0 0 0 0 0 0\nend\ntriangles\nmaterial\n0 0 0 0 0 0 1 0 0\n0 1 0 0 0 0 1 1 0\n0 0 1 0 0 0 1 0 1\nend\n')
    (fixture/'anim.smd').write_text(header+''.join(f'time {i}\n0 {i} 0 0 0 0 0\n' for i in range(4))+'end\n')
    for name,last in [('rig','run'),('target','c1m1_intro')]:
        qc=fixture/(name+'.qc')
        qc.write_text(f'$modelname {name}\n$definebone root "" 0 0 0 0 0 0 0 0 0 0 0 0\n$body m mesh.smd\n$sequence idle anim.smd\n$sequence walk anim.smd\n$sequence {last} anim.smd\n')
        run('fixture_compile_'+name,compiler,['-game',fixture,qc])
    retarget = root/'retarget-vanilla';retarget.mkdir()
    (retarget/'survivor_teenangst.mdl').write_bytes((fixture/'models/rig.mdl').read_bytes())
    target_bytes=bytearray((fixture/'models/target.mdl').read_bytes())
    (retarget/'targetanim.mdl').write_bytes(target_bytes)
    (retarget/'survivor_producer_light.mdl').write_bytes(target_bytes)
    integer(target_bytes,336,1,len(target_bytes))
    target_bytes.extend(struct.pack('<ii',0,8)+b'targetanim.mdl\0')
    integer(target_bytes,76,len(target_bytes))
    (retarget/'survivor_producer.mdl').write_bytes(target_bytes)
    retout=root/'retarget-output';retout.mkdir()
    retargs=['-vanilla',retarget,'-rig','zoey','-replace','rochelle','-retarget','-o',retout/'swap.qci']
    run('l4d_retarget_body_light_success',l4d_tool,retargs)
    retfiles=sorted(p for p in retout.rglob('*') if p.is_file())
    assert len(list(retout.glob('anims/*.dmx')))>=2,retfiles
    for path in retfiles:path.write_bytes(b'previous:'+path.name.encode())
    late=retout/'swap_Light.qci';old=late.read_bytes();late.unlink();late.mkdir()
    run('l4d_light_qci_failure_preserves_retarget_clips',l4d_tool,retargs,code=1,
        protected=[p for p in retfiles if p!=late],message='not a regular file')
    late.rmdir();late.write_bytes(old)
    late=next(p for p in retfiles if p.suffix=='.dmx' and 'c1m1_intro' in p.stem and '_light' in p.stem)
    old=late.read_bytes();late.unlink();late.mkdir()
    run('l4d_late_dmx_failure_preserves_qci_and_clips',l4d_tool,retargs,code=1,
        protected=[p for p in retfiles if p!=late],message='not a regular file')
    late.rmdir();late.write_bytes(old)
    # Absence is optional, but an existing corrupt Light file must not turn a
    # partially generated batch into success. Keep all existing outputs intact.
    light=retarget/'survivor_producer_light.mdl'
    valid_light=light.read_bytes()
    for label, offset, value in [('out_of_bounds_sequences',192,len(valid_light)+4096),
                                 ('negative_sequence_count',188,-1),
                                 ('invalid_sequence_label',struct.unpack_from('<i',valid_light,192)[0]+4,len(valid_light)+4096)]:
        malformed=bytearray(valid_light)
        integer(malformed,offset,value)
        light.write_bytes(malformed)
        run('l4d_light_'+label+'_preserves_batch',l4d_tool,retargs,code=1,
            protected=retfiles,message='invalid Light model')
    # A valid model with no local sequences remains an intentional omission.
    empty=bytearray(valid_light)
    integer(empty,188,0,0)
    light.write_bytes(empty)
    run('l4d_light_zero_sequences_is_optional',l4d_tool,retargs)
    light.write_bytes(valid_light)
    print(f'{len(records)} integration checks passed')


if __name__ == '__main__':
    main()
