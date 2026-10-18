"""Verify and exercise the actual packaged binaries before publishing.

Usage: python tests/verify_package.py package.zip --manifest manifest.json
"""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET


def verify_inventory(package):
    inventory = 'NewPageMergeMDL/SHA256SUMS.txt'
    actual = {info.filename for info in package.infolist() if not info.is_dir()} - {inventory}
    listed = {}
    for line in package.read(inventory).decode('utf-8').splitlines():
        if not re.fullmatch(r'[0-9a-f]{64}  .+', line):
            raise ValueError('Invalid checksum inventory line')
        digest, relative = line.split('  ', 1)
        name = 'NewPageMergeMDL/' + relative
        if name in listed:
            raise ValueError('Duplicate checksum inventory entry')
        listed[name] = digest
    if set(listed) != actual:
        raise ValueError('Checksum inventory does not cover the package contents')
    for name, digest in listed.items():
        actual_digest = hashlib.sha256()
        with package.open(name) as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                actual_digest.update(chunk)
        if actual_digest.hexdigest() != digest:
            raise ValueError('Package checksum mismatch: ' + name)


def verify(archive, expected, destination):
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        if len(set(names)) != len(names):
            raise ValueError('Duplicate archive entries')
        for name in names:
            path = PurePosixPath(name.replace('\\', '/'))
            if path.is_absolute() or '..' in path.parts or ':' in name or not path.parts or path.parts[0] != 'NewPageMergeMDL':
                raise ValueError('Unsafe archive member: ' + name)
        manifest = json.loads(package.read('NewPageMergeMDL/upstream-manifest.json'))
        if manifest != expected:
            raise ValueError('Packaged source provenance does not match preparation manifest')
        for name in (
            'README.md', 'README.en.md', 'INSTALL.md', 'VALIDATION.md', 'IMPROVEMENTS.md',
            'FIVE_COMPILER_COMPLETION.md', 'O5_FORMAT_IMPORTS.md', 'MESH_STATE_WORKFLOW.md', 'VRM_RUNTIME.md',
            'integration/gmod/newpage_vertexanim.lua', 'integration/gmod/newpage_meshstates.lua',
            'integration/gmod/newpage_vrm.lua', 'integration/gmod/newpage_vrm_materials.lua',
            'tools/mesh_states.py', 'tools/vrm_runtime.py', 'tools/vrml_import.py',
            'tools/vrml_converter/CMakeLists.txt', 'tools/vrml_converter/main.cpp',
            'tools/vrml_converter/meshlab/Parser.cpp', 'tools/vrml_converter/meshlab/Parser.h',
            'tools/vrml_converter/meshlab/Scanner.cpp', 'tools/vrml_converter/meshlab/Scanner.h',
            'tools/vrml_converter/meshlab/LICENSE', 'tools/vrml_converter/meshlab/SOURCE.md',
            'libs/assimp/contrib/pugixml/src/pugixml.cpp', 'libs/assimp/contrib/pugixml/src/pugixml.hpp',
            'libs/assimp/contrib/pugixml/src/pugiconfig.hpp', 'libs/assimp/contrib/pugixml/LICENSE.md',
            'libs/tinyusdz/LICENSE', 'libs/tinyusdz/LICENSE-APACHE-2.0',
            'libs/tinyusdz/SOURCE.md', 'libs/tinyusdz/THIRD_PARTY_NOTICES.md',
            '.github/images/newpage-compiler.png', '.github/images/newpage-decompiler.png',
            'assets/branding/NewPage-logo.png', 'assets/branding/generate_icons.py',
            'assets/branding/README.md',
        ):
            try:
                info = package.getinfo('NewPageMergeMDL/' + name)
            except KeyError as exc:
                raise ValueError('Missing required package file: ' + name) from exc
            if info.is_dir() or info.file_size == 0:
                raise ValueError('Empty required package file: ' + name)
        # Content inspection also works when repacking a previously tested
        # Linux release on Windows. Execution tests still run on its native OS.
        suffix = '.exe' if 'NewPageMergeMDL/NewPageMergeMDL.exe' in names else ''
        required = ['NewPageMergeMDL', 'NewPageMergeMDL-Decompiler', 'NewPageVRMLtoX3D']
        if suffix:
            required.append('NewPageMergeMDL-C4D')
        required.extend('subtools/' + name for name in ('ag2proportions', 'l4d_animswap', 'meshtool', 'vmd2valvebiped'))
        for tool in required:
            binary = package.read('NewPageMergeMDL/' + tool + suffix)
            if not binary.startswith(b'MZ' if suffix else b'\x7fELF'):
                raise ValueError('Invalid native executable: ' + tool)
        for name in ('subtools/licenses/zstd.txt', 'subtools/licenses/ValveResourceFormat.txt'):
            member = 'NewPageMergeMDL/' + name
            if member not in names or package.getinfo(member).file_size == 0:
                raise ValueError('Missing or empty required ag2proportions license: ' + name)
        if expected.get('fingerprint'):
            package.getinfo('NewPageMergeMDL/sources/NewPageMergeMDL-source.zip')
        verify_inventory(package)
        package.extractall(destination)
    root = Path(destination) / 'NewPageMergeMDL'
    if os.name != 'nt':
        for tool in required:
            binary = root / (tool + suffix)
            with binary.open('rb') as stream:
                is_elf = stream.read(4) == b'\x7fELF'
            if is_elf:
                binary.chmod(0o755)
    return root / ('NewPageMergeMDL' + suffix)


def exercise_packaged_vrml(compiler, destination):
    """Exercise the shipped script/helper rather than the checkout copies."""
    work=Path(destination)/'vrml-smoke';work.mkdir()
    source=work/'source 场景.wrl';output=work/'converted 场景.x3d'
    source.write_text('''#VRML V2.0 utf8
Transform { translation 2 3 4 children [ Shape { geometry IndexedFaceSet {
  coord Coordinate { point [0 0 0, 1 0 0, 0 1 0] }
  coordIndex [0 1 2 -1]
} } ] }
''',encoding='utf-8')
    script=compiler.parent/'tools/vrml_import.py'
    converter=compiler.with_name('NewPageVRMLtoX3D'+compiler.suffix)
    subprocess.run([sys.executable,str(script),str(source),'--output',str(output),
                    '--compiler',str(compiler),'--game',str(work),'--modelname','vrml_package','--upaxis','z'],check=True)
    tree=ET.parse(output)
    if tree.find('.//IndexedFaceSet') is None or tree.find('.//Transform').get('translation')!='2 3 4':
        raise ValueError('Packaged VRML converter lost geometry/hierarchy')
    from validate_outputs import validate
    validate(work/'models/vrml_package.mdl')
    if struct.unpack_from('<i',(work/'models/vrml_package.vvd').read_bytes(),16)[0]!=3:
        raise ValueError('Packaged VRML bridge did not compile its triangle')
    old=output.read_bytes();source.write_text('#VRML V2.0 utf8\nShape { geometry IndexedFaceSet {\n')
    failed=subprocess.run([str(converter),str(source),str(output)],capture_output=True)
    if failed.returncode==0 or output.read_bytes()!=old:
        raise ValueError('Packaged VRML converter replaced output for an invalid source')


def exercise_packaged_ag2proportions(compiler, expected_version):
    """Check that the separately shipped experimental CS2 helper starts."""
    tool = compiler.parent / 'subtools' / ('ag2proportions' + compiler.suffix)
    help_result = subprocess.run([str(tool), '--help'], capture_output=True, text=True,
                                 errors='replace', check=True)
    if 'Usage:' not in help_result.stdout or 'CS2 AnimGraph2 proportion wrapper' not in help_result.stdout:
        raise ValueError('Packaged ag2proportions help output is incomplete')
    version_result = subprocess.run([str(tool), '--version'], capture_output=True, text=True,
                                     errors='replace', check=True)
    versions = re.findall(r'^ag2proportions (\d+\.\d+\.\d+)\r?$', version_result.stdout, re.MULTILINE)
    if versions != [expected_version]:
        raise ValueError('Packaged ag2proportions version does not match packaged source version')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive')
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    expected = json.loads(Path(args.manifest).read_text(encoding='utf-8'))
    with tempfile.TemporaryDirectory(prefix='newpage-package-') as folder:
        compiler = verify(args.archive, expected, folder)
        banner = subprocess.run([str(compiler), '-version'], capture_output=True, text=True, errors='replace')
        if 'v' + expected['project_version'] not in banner.stdout:
            raise ValueError('Executable version does not match packaged source version')
        exercise_packaged_ag2proportions(compiler, expected['project_version'])
        exercise_packaged_vrml(compiler,folder)
        c4d=compiler.with_name('NewPageMergeMDL-C4D.exe')
        if os.name=='nt' and c4d.is_file():
            if c4d.read_bytes()[:2]!=b'MZ':raise ValueError('Invalid native C4D helper')
            subprocess.run([sys.executable,str(Path(__file__).with_name('c4d_bridge_test.py')),str(compiler)],check=True)
        else:
            print('Linux package uses C4D-to-GLB conversion on Windows; native C4D checks do not apply.',flush=True)
        for script, arguments in (
            ('compiler_integrity_test.py', [str(compiler)]),
            ('decompiler_integrity_test.py', [str(compiler), str(compiler.with_name('NewPageMergeMDL-Decompiler'+compiler.suffix))]),
            ('subtools_integrity_test.py', ['--bin-dir', str(compiler.parent)]),
        ):
            subprocess.run([sys.executable, str(Path(__file__).with_name(script)), *arguments], check=True)
        subprocess.run([sys.executable, str(Path(__file__).with_name('compatibility.py')), str(compiler)], check=True)
    print('Packaged binaries, version, provenance, runtime files and compatibility suite verified.')


if __name__ == '__main__':
    main()
