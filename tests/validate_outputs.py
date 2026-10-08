"""Check serialized model table ranges and cross-file checksums independently.

Usage: python tests/validate_outputs.py path/to/model.mdl
This checks structural integrity, not complete engine compatibility.
"""
import argparse
import struct
from pathlib import Path


class Reader:
    def __init__(self, path):
        self.path = path
        self.data = path.read_bytes()

    def span(self, offset, count, size):
        if offset < 0 or count < 0 or size < 0 or offset + count * size > len(self.data):
            raise ValueError(f'{self.path.name}: table outside file at {offset}, count {count}, size {size}')
        return offset

    def integer(self, offset):
        self.span(offset, 1, 4)
        return struct.unpack_from('<i', self.data, offset)[0]

    def string(self, offset):
        self.span(offset, 1, 1)
        if self.data.find(b'\0', offset) < 0:
            raise ValueError(f'{self.path.name}: unterminated string')

    def table(self, offset, size, relative=0):
        count = self.integer(offset)
        start = self.integer(offset + 4) + relative
        self.span(start, count, size)
        return range(start, start + count * size, size)


def validate(path, vtx_format=None):
    path = Path(path)
    mdl = Reader(path)
    mdl.span(0, 1, 408)
    if mdl.data[:4] != b'IDST' or mdl.integer(4) != 49 or mdl.integer(76) != len(mdl.data):
        raise ValueError('Invalid MDL signature, version or declared length')
    checksum = mdl.integer(8)
    bones = list(mdl.table(156, 216))
    for i, bone in enumerate(bones):
        mdl.string(bone + mdl.integer(bone))
        parent = mdl.integer(bone + 4)
        visited = {i}
        while parent != -1:
            if parent < 0 or parent >= len(bones) or parent in visited:
                raise ValueError('Invalid or cyclic serialized bone hierarchy')
            visited.add(parent)
            parent = mdl.integer(bones[parent] + 4)
    controls=list(mdl.table(164,56))
    for control in controls:
        bone,kind,lo,hi,rest,index=struct.unpack_from('<2i2f2i',mdl.data,control)
        if bone<0 or bone>=len(bones) or kind&63 not in (1,2,4,8,16,32) or index not in range(5):
            raise ValueError('Invalid serialized bone controller')
        import math
        if not math.isfinite(lo) or not math.isfinite(hi):
            raise ValueError('Non-finite serialized bone controller bounds')
    for index,bone in enumerate(bones):
        for axis in range(6):
            linked=mdl.integer(bone+8+axis*4)
            if linked==-1:continue
            if linked<0 or linked>=len(controls) or mdl.integer(controls[linked])!=index or not mdl.integer(controls[linked]+4)&(1<<axis):
                raise ValueError('Invalid bone controller link')
    for offset, size in ((260, 4), (268, 20), (276, 12), (240, 92), (204, 64)):
        list(mdl.table(offset, size))
    for desc in mdl.table(260, 4):
        mdl.string(desc + mdl.integer(desc))
    for controller in mdl.table(268, 20):
        mdl.string(controller + mdl.integer(controller))
        mdl.string(controller + mdl.integer(controller + 4))
    mdl.span(mdl.integer(228), mdl.integer(220) * mdl.integer(224), 2)
    vertex_total = 0
    for body in mdl.table(232, 16):
        mdl.string(body + mdl.integer(body))
        # bodypart count is at +4, model offset at +12, not adjacent.
        start = body + mdl.integer(body + 12)
        count = mdl.integer(body + 4)
        mdl.span(start, count, 148)
        for model in range(start, start + count * 148, 148):
            vertex_total += mdl.integer(model + 80)
            for mesh in mdl.table(model + 72, 116, model):
                if mdl.integer(mesh + 8) < 0 or mdl.integer(mesh + 12) < 0:
                    raise ValueError('Invalid mesh vertex range')
    for rule in mdl.table(276, 12):
        if not 0 <= mdl.integer(rule) < mdl.integer(260):
            raise ValueError('Invalid flex target')
        for op in mdl.table(rule + 4, 8, rule):
            code, value = mdl.integer(op), mdl.integer(op + 4)
            if code in (2, 3) and not 0 <= value < mdl.integer(268 if code == 2 else 260):
                raise ValueError('Invalid serialized flex reference')
    vvd_path = path.with_suffix('.vvd')
    if vvd_path.exists():
        vvd = Reader(vvd_path)
        vvd.span(0, 1, 64)
        if vvd.data[:4] != b'IDSV' or vvd.integer(4) != 4 or vvd.integer(8) != checksum:
            raise ValueError('VVD signature/version/checksum mismatch')
        lods = vvd.integer(12)
        if not 1 <= lods <= 8 or vvd.integer(16) != vertex_total:
            raise ValueError('VVD LOD or vertex count mismatch')
        vvd.span(vvd.integer(52), vvd.integer(48), 12)
        vvd.span(vvd.integer(56), vertex_total, 48)
        vvd.span(vvd.integer(60), vertex_total, 16)
    for suffix in ('.dx80.vtx', '.dx90.vtx'):
        vtx_path = path.with_suffix(suffix)
        if not vtx_path.exists():
            continue
        vtx = Reader(vtx_path)
        vtx.span(0, 1, 36)
        if vtx.integer(0) != 7 or vtx.integer(16) != checksum:
            raise ValueError('VTX version/checksum mismatch')
        def check_layout(full):
            group_size,strip_size=(33,35) if full else (25,27)
            for body in vtx.table(28,8):
                for model in vtx.table(body,8,body):
                    for lod in vtx.table(model,12,model):
                        for mesh in vtx.table(lod,9,lod):
                            for group in vtx.table(mesh,group_size,mesh):
                                vertices=list(vtx.table(group,9,group));indices=list(vtx.table(group+8,2,group))
                                for at in indices:
                                    if struct.unpack_from('<H',vtx.data,at)[0]>=len(vertices):raise ValueError('Invalid VTX strip-group vertex index')
                                topology=list(vtx.table(group+25,2,group)) if full else []
                                for strip in vtx.table(group+16,strip_size,group):
                                    count,first,verts,base=struct.unpack_from('<4i',vtx.data,strip)
                                    if count<0 or first<0 or first+count>len(indices) or verts<0 or base<0 or base+verts>len(vertices):raise ValueError('Invalid VTX strip range')
                                    list(vtx.table(strip+19,8,strip))
                                    flags=vtx.data[strip+18]
                                    if full:
                                        nt,to=struct.unpack_from('<2i',vtx.data,strip+27)
                                        if nt<0 or to<0 or to+nt>len(topology):raise ValueError('Invalid VTX strip topology range')
                                        if flags in (2,4):
                                            if len(indices)>8192*4:raise ValueError('SubD strip group exceeds renderer patch capacity')
                                            if count%4 or not nt:raise ValueError('Invalid SubD control index count')
                                            cursor=to
                                            for patch in range(count//4):
                                                if cursor+60>to+nt:raise ValueError('Truncated SubD topology header')
                                                head=struct.unpack_from('<60H',vtx.data,topology[cursor])
                                                total=sum(head[:4]);end=cursor+60+total
                                                if end>to+nt or total>52:raise ValueError('Invalid SubD one-ring size')
                                                for corner in range(4):
                                                    if head[corner]<4 or head[4+corner]>=head[corner] or head[12+corner]>=head[corner]:raise ValueError('Invalid SubD one-ring metadata')
                                                if max(head[44:60])>=vertex_total:raise ValueError('Invalid SubD UV vertex')
                                                ring=struct.unpack_from('<'+'H'*total,vtx.data,topology[cursor+60])
                                                if max(ring)>=len(vertices):raise ValueError('Invalid SubD one-ring vertex')
                                                if flags==2 and (head[8:12]!=(4,)*4 or any(head[16:24])):raise ValueError('Irregular patch in regular SubD strip')
                                                cursor=end
                                            if cursor!=to+nt:raise ValueError('Extra SubD topology records')
                                    elif flags in (2,4):raise ValueError('SubD requires extended VTX')
        failures=[]
        for full in ([bool(vtx_format)] if vtx_format is not None else ([True] if mdl.integer(152)&(1<<19) else [False,True])):
            try:check_layout(full);break
            except (ValueError,struct.error) as error:failures.append(str(error))
        else:raise ValueError('No valid VTX layout: '+ '; '.join(failures))
    return {'model': path.name, 'bones': len(bones), 'vertices': vertex_total}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mdl', type=Path)
    print(validate(parser.parse_args().mdl))
