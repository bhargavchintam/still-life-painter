# Still Life Painter

A 3D art-studio painting minigame built with **Panda3D**. The screen is split: a
3D studio (walls, floor, a stool with a plate and a piece of fruit) on the left,
and a painting canvas with a fruit selector, colour palette and brush-size slider
on the right. Orbit the camera around the fruit and paint what you see.

![gameplay](media/still_life_gameplay.gif)

## Features
- Split-screen: live 3D studio + a paintable 2D canvas.
- Orbit / raise / zoom the camera around the still-life pivot.
- Colour palette + brush-size slider; paint strokes on the canvas.
- Fruit reference selector (Previous / Next).
- Pause menu (Resume / Clear Canvas / Exit) — painting can't be undone, only cleared.

## Controls
| Input | Action |
|-------|--------|
| A / D | orbit the camera left / right |
| W / S | raise / lower the camera |
| ↑ / ↓ | zoom in / out |
| Left mouse (drag on canvas) | paint |
| Esc | pause menu |

## Run
```bash
pip install panda3d panda3d-gltf
python scripts/fetch_assets.py
python still_life_painter.py
```
`scripts/fetch_assets.py` downloads the 10 Poly Haven files listed below
(95.7 MB) into an `assets/` folder next to `still_life_painter.py`. It skips
files you already have; `--dry-run` lists the files and sizes, and `--force`
downloads them again. If a file is missing, the game lists it and exits.

## A note on assets
The studio models and textures are **CC0** from [Poly Haven](https://polyhaven.com)
(fruit models, wood/brick textures). They are **not bundled** in this repo.
`scripts/fetch_assets.py` gets them through the Poly Haven API (Powered by Poly
Haven) and checks each file against the MD5 the API lists for it. Poly Haven
serves the models as glTF (a `.gltf` file, a `.bin` buffer and `.jpg`
textures), and the game loads `.glb`, so the script packs each model's files
into one `.glb`. It needs only the Python standard library.

The game looks for these files in `assets/` (each name starts with the asset's
Poly Haven ID):
- Textures: `plank_flooring_04_diff_4k.jpg`, `brick_wall_10_diff_4k.jpg`
- Models: `wooden_stool_01_4k.glb`, `carved_wooden_plate_4k.glb`,
  `food_lychee_01_4k.glb`, `food_pomegranate_01_4k.glb`,
  `food_pears_asian_01_4k.glb`, `food_lime_01_4k.glb`, `food_kiwi_01_4k.glb`,
  `food_apple_01_4k.glb`

## Tech
Panda3D · `panda3d-gltf` (glTF/GLB model loading) · DirectGUI · render-to-texture
canvas · orbit camera.

## Contributing
See [CONTRIBUTING.md](CONTRIBUTING.md), including how to add a fruit. On every
push and pull request, CI runs the unit tests (offline tests of the asset
script) and checks that the game and its dependencies install and import. It
does not download the assets, so it cannot open the studio.
