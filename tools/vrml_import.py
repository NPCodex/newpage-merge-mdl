"""Convert VRML in a separate GPL process, then optionally compile its geometry."""
from pathlib import Path
import argparse
import os
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--output',required=True,type=Path,help='X3D output (parent directory must exist)')
    parser.add_argument('--converter',type=Path,help='Path to separate NewPageVRMLtoX3D executable')
    parser.add_argument('--compiler',type=Path,help='Optionally compile a QC generated beside the X3D output')
    parser.add_argument('--game',type=Path)
    parser.add_argument('--modelname',default='vrml_import')
    parser.add_argument('--upaxis',choices=('y','z'),default='y')
    args=parser.parse_args()
    executable='NewPageVRMLtoX3D'+('.exe' if os.name=='nt' else '')
    converter=args.converter or Path(__file__).resolve().parents[1]/executable
    source=args.source.resolve();output=args.output.resolve()
    if source.suffix.lower() not in ('.wrl','.x3dv'):
        parser.error('source must be .wrl or .x3dv')
    if args.compiler and not args.game:parser.error('--compiler requires --game')
    if args.compiler:
        def quote(value):
            text=str(value).replace('\\','/')
            if any(x in text for x in ('"','\n','\r')):raise ValueError('QC argument contains unsupported quote/newline')
            return '"'+text+'"'
        qc=output.with_suffix('.qc')
        if qc.exists():raise FileExistsError(f'Refusing to replace existing QC: {qc}')
        qc_text=f'$modelname {quote(args.modelname)}\n$UpAxis {args.upaxis} assimp\n$body vrml {quote(output)}\n'
    result=subprocess.run([str(converter.resolve()),str(source),str(output)])
    if result.returncode:return result.returncode
    if args.compiler:
        with qc.open('x',encoding='utf-8',newline='\n') as stream:stream.write(qc_text)
        return subprocess.run([str(args.compiler.resolve()),str(qc),'-game',str(args.game.resolve())]).returncode
    return 0


if __name__=='__main__':
    try:sys.exit(main())
    except (OSError,ValueError) as error:print(error,file=sys.stderr);sys.exit(1)
