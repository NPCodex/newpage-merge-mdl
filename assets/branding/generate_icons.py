"""Rebuild NewPage tool icons from the supplied brand mark (requires Pillow).

Run from any directory. Output is deterministic; compilation does not require
Pillow because the PNG and multi-resolution ICO resources are checked in.
"""
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[2]
SOURCE = Path(__file__).with_name('NewPage-logo.png')
SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)
COLORS = {'compiler': (55, 222, 195), 'decompiler': (183, 154, 255)}


def icon(kind):
    original = Image.open(SOURCE).convert('RGB')
    background = original.getpixel((0, 0))
    # Extract coverage from the white brand mark; preserve the original shape.
    coverage = original.getchannel('R').point(
        lambda value: round(max(0, min(255, (value-background[0])*255/(255-background[0])))))
    mark = coverage.crop(coverage.getbbox())
    mark.thumbnail((780, 580), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', (1024, 1024))
    draw = ImageDraw.Draw(out)
    draw.rounded_rectangle((12, 12, 1012, 1012), radius=216, fill=background)
    out.paste((255, 255, 255, 255), (104, 176), mark)
    # Compact model badge: assembled cube for compile, separated layers for
    # decompile. Both shape and color distinguish the tools at smaller sizes.
    draw = ImageDraw.Draw(out)
    draw.rounded_rectangle((674, 674, 1020, 1020), radius=108, fill=background)
    draw.rounded_rectangle((704, 704, 992, 992), radius=86, fill=COLORS[kind])
    if kind == 'compiler':
        draw.polygon([(848, 752), (928, 796), (928, 892), (848, 940), (768, 892), (768, 796)], fill=background)
        draw.line([(768, 796), (848, 842), (928, 796)], fill=COLORS[kind], width=14, joint='curve')
        draw.line([(848, 842), (848, 940)], fill=COLORS[kind], width=14)
    else:
        for top in (752, 816, 880):
            draw.polygon([(848, top), (940, top+42), (848, top+84), (756, top+42)], fill=background)
            draw.line([(756, top+42), (848, top+84), (940, top+42)], fill=COLORS[kind], width=10)
    return out


def generate():
    for kind, folder in [('compiler', 'mdlcompiler'), ('decompiler', 'mdldecompiler')]:
        artwork = icon(kind)
        preview = ROOT / '.github/images' / ('newpage-' + kind + '.png')
        preview.parent.mkdir(parents=True, exist_ok=True)
        artwork.resize((256, 256), Image.Resampling.LANCZOS).save(preview, optimize=True)
        destination = ROOT / folder / 'app.ico'
        destination.parent.mkdir(parents=True, exist_ok=True)
        artwork.save(destination, sizes=[(s, s) for s in SIZES])


if __name__ == '__main__':
    generate()
