# NewPage application icons

The project owner supplied `NewPage-logo.png` on 2026-10-13 as the source
brand mark. The tool icons preserve its navy background and white NP shape.
The compiler uses a mint cube badge; the decompiler uses violet separated
layers. The distinction uses shape as well as color.

Run `python assets/branding/generate_icons.py` with Pillow installed to rebuild
the checked-in PNG previews and 16/20/24/32/40/48/64/128/256-pixel ICO files.
Normal CMake builds use these files directly and do not require Pillow.
`mdlcompiler/app.ico` and `mdldecompiler/app.ico` are the NewPage variants;
upstream artwork is retained only for the historical `UPSTREAM_README.md`.
