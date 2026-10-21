"""Run with Cinema 4D's licensed c4dpy, not CPython or the Cineware SDK.

Creates only self-authored scenes in a new directory. Reference meshes come from
Cinema 4D's Current State to Object command, independently of our importer.
Usage: c4dpy.exe author_fixtures.py <new-output-directory>
"""
import json
import math
import pathlib
import sys

import c4d


def vector(v):
    return [v.x, v.y, v.z]


def matrix(m):
    return [vector(m.v1), vector(m.v2), vector(m.v3), vector(m.off)]


def walk(first):
    while first:
        yield first
        yield from walk(first.GetDown())
        first = first.GetNext()


def snapshot(first):
    result = []
    for op in walk(first):
        item = dict(name=op.GetName(), type=op.GetType(), local=matrix(op.GetMl()),
                    world=matrix(op.GetMg()), parent=op.GetUp().GetName() if op.GetUp() else None)
        if isinstance(op, c4d.PolygonObject):
            item['points'] = [vector(p) for p in op.GetAllPoints()]
            item['polygons'] = [[p.a, p.b, p.c, p.d] for p in op.GetAllPolygons()]
            uv = op.GetTag(c4d.Tuvw)
            if uv:
                item['uv'] = [{k: vector(v) for k, v in uv.GetSlow(i).items()}
                              for i in range(op.GetPolygonCount())]
            # Cinema 4D computes the reference corner normals from Phong tags.
            normals = op.CreatePhongNormals()
            if normals:
                item['normals'] = [vector(v) for v in normals]
            item['materials'] = []
            for tag in op.GetTags():
                if tag.CheckType(c4d.Ttexture):
                    mat = tag[c4d.TEXTURETAG_MATERIAL]
                    item['materials'].append(dict(material=mat.GetName() if mat else None,
                        restriction=tag[c4d.TEXTURETAG_RESTRICTION]))
        result.append(item)
    return result


def reference(doc):
    result = []
    for source in list(iter_roots(doc)):
        objects = c4d.utils.SendModelingCommand(command=c4d.MCOMMAND_CURRENTSTATETOOBJECT,
            list=[source], mode=c4d.MODELINGCOMMANDMODE_ALL, doc=doc)
        if not isinstance(objects, list):
            raise RuntimeError('Cinema 4D Current State to Object failed')
        for op in objects:
            result.extend(snapshot(op))
    return result


def iter_roots(doc):
    op = doc.GetFirstObject()
    while op:
        yield op
        op = op.GetNext()


def material(doc, name, color):
    mat = c4d.BaseMaterial(c4d.Mmaterial)
    mat.SetName(name)
    mat[c4d.MATERIAL_COLOR_COLOR] = c4d.Vector(*color)
    mat[c4d.MATERIAL_USE_COLOR] = True
    doc.InsertMaterial(mat)
    return mat


def texture(op, mat):
    tag = c4d.TextureTag()
    tag[c4d.TEXTURETAG_MATERIAL] = mat
    tag[c4d.TEXTURETAG_PROJECTION] = c4d.TEXTURETAG_PROJECTION_UVW
    op.InsertTag(tag)


def save(doc, path):
    doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
    flags = c4d.SAVEDOCUMENTFLAGS_DONTADDTORECENTLIST | c4d.SAVEDOCUMENTFLAGS_SAVECACHES
    if not c4d.documents.SaveDocument(doc, str(path), flags, c4d.FORMAT_C4DEXPORT):
        raise RuntimeError('Could not save Cineware cache: ' + str(path))


def caches(root):
    doc = c4d.documents.BaseDocument()
    parent = c4d.BaseObject(c4d.Onull)
    parent.SetName('CacheParent')
    parent.SetRelPos(c4d.Vector(220, 130, -75))
    parent.SetRelRot(c4d.Vector(.2, -.1, .15))
    doc.InsertObject(parent)
    mat = material(doc, 'CacheBlue', (.2, .4, .8))
    for index, bend in enumerate((False, True)):
        cube = c4d.BaseObject(c4d.Ocube)
        cube.SetName('BentGenerator' if bend else 'PlainGenerator')
        cube[c4d.PRIM_CUBE_LEN] = c4d.Vector(120, 180, 80)
        cube[c4d.PRIM_CUBE_SUBX] = 2
        cube[c4d.PRIM_CUBE_SUBY] = 6
        cube[c4d.PRIM_CUBE_SUBZ] = 2
        cube.SetRelPos(c4d.Vector(index * 300, 15, 20))
        cube.InsertUnderLast(parent)
        texture(cube, mat)
        cube.MakeTag(c4d.Tphong)
        if bend:
            modifier = c4d.BaseObject(c4d.Obend)
            modifier.SetName('SavedBend')
            modifier[c4d.DEFORMOBJECT_SIZE] = c4d.Vector(120, 180, 80)
            modifier[c4d.DEFORMOBJECT_STRENGTH] = math.radians(35)
            modifier.InsertUnder(cube)
    save(doc, root / 'generator-deformer.c4d')
    (root / 'generator-deformer-reference.json').write_text(json.dumps(dict(
        schema=1, author='Cinema 4D', version=c4d.GetC4DVersion(),
        hierarchy=snapshot(doc.GetFirstObject()), reference=reference(doc)), indent=2), encoding='utf-8')


def skin_animation(root):
    doc = c4d.documents.BaseDocument()
    doc.SetFps(30)
    doc.SetMinTime(c4d.BaseTime(0))
    doc.SetMaxTime(c4d.BaseTime(1))
    mesh = c4d.PolygonObject(6, 2)
    mesh.SetName('AnimatedSkin')
    mesh.SetAllPoints([c4d.Vector(x, y, 0) for y in (0, 100, 200) for x in (-40, 40)])
    mesh.SetPolygon(0, c4d.CPolygon(0, 1, 3, 2))
    mesh.SetPolygon(1, c4d.CPolygon(2, 3, 5, 4))
    doc.InsertObject(mesh)
    mesh.MakeTag(c4d.Tphong)
    uv = c4d.UVWTag(2)
    mesh.InsertTag(uv)
    for i in range(2):
        uv.SetSlow(i, c4d.Vector(0, i/2, 0), c4d.Vector(1, i/2, 0),
                   c4d.Vector(1, (i+1)/2, 0), c4d.Vector(0, (i+1)/2, 0))
    texture(mesh, material(doc, 'SkinRed', (.8, .2, .1)))
    base = c4d.BaseObject(c4d.Ojoint); base.SetName('SkinRoot'); doc.InsertObject(base)
    tip = c4d.BaseObject(c4d.Ojoint); tip.SetName('SkinTip'); tip.InsertUnder(base)
    tip.SetRelPos(c4d.Vector(0, 100, 0))
    weight = c4d.modules.character.CAWeightTag()
    mesh.InsertTag(weight)
    weight.AddJoint(base); weight.AddJoint(tip)
    for point in range(6):
        upper = 0.0 if point < 2 else (.5 if point < 4 else 1.0)
        weight.SetWeight(0, point, 1-upper); weight.SetWeight(1, point, upper)
    weight.SetGeomMg(mesh.GetMg())
    weight.CalculateBoneStates(c4d.NOTOK)
    skin = c4d.BaseObject(c4d.Oskin); skin.SetName('SkinModifier'); skin.InsertUnder(mesh)
    track = c4d.CTrack(tip, c4d.DescID(c4d.DescLevel(c4d.ID_BASEOBJECT_REL_ROTATION,
        c4d.DTYPE_VECTOR, 0), c4d.DescLevel(c4d.VECTOR_Z, c4d.DTYPE_REAL, 0)))
    tip.InsertTrackSorted(track)
    curve = track.GetCurve()
    for frame, angle in ((0, 0), (15, .4), (30, -.2)):
        result = curve.AddKey(c4d.BaseTime(frame, 30))
        result['key'].SetValue(curve, angle)
        result['key'].SetInterpolation(curve, c4d.CINTERPOLATION_LINEAR)
    mesh.Message(c4d.MSG_UPDATE)
    samples = []
    for frame in (0, 15, 30):
        doc.SetTime(c4d.BaseTime(frame, 30))
        doc.ExecutePasses(None, True, True, True, c4d.BUILDFLAGS_NONE)
        samples.append(dict(frame=frame, hierarchy=snapshot(doc.GetFirstObject()), reference=reference(doc)))
    doc.SetTime(c4d.BaseTime(0))
    save(doc, root / 'skinned-animated.c4d')
    (root / 'skinned-animated-reference.json').write_text(json.dumps(dict(
        schema=1, author='Cinema 4D', version=c4d.GetC4DVersion(), fps=30, samples=samples), indent=2), encoding='utf-8')


if __name__ == '__main__':
    target = pathlib.Path(sys.argv[-1]).resolve()
    target.mkdir(parents=True, exist_ok=False)
    caches(target)
    skin_animation(target)
    print('Self-authored Cinema 4D fixtures written to', target)
