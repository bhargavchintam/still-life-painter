# Contributing

Thanks for helping with Still Life Painter. Small, focused pull requests are
the easiest to review. For a bigger change, please open an issue first so we
can agree on the idea.

## Run the game and the tests

```bash
pip install -r requirements.txt
python still_life_painter.py
```

The game needs the CC0 Poly Haven models and textures in an `assets/` folder
next to `still_life_painter.py`. They are not in this repo: run
`python scripts/fetch_assets.py` to download them (95.7 MB). `README.md` lists
the exact file names, and the game prints any missing file and exits.

Run the unit tests with `pip install pytest` and `python -m pytest`. They test
`scripts/fetch_assets.py` without the network. Name new test files `test_*.py`.

The game has no headless flag, and CI does not download the assets, so CI
(`.github/workflows/tests.yml`) cannot open the studio. It installs the
dependencies, runs `python -m pytest` and checks that the game module imports. It runs on every
push to `main` and on every pull request.

## Add a fruit (the game's "levels")

1. Put the fruit's `.glb` file in `assets/`. If the fruit is on Poly Haven,
   name it `<Poly Haven id>_4k.glb` (like `food_apple_01_4k.glb`) and
   `scripts/fetch_assets.py` downloads it for everyone.
2. Add the file name to `FRUITS` and the name to show to `FRUIT_NAMES`, at the
   same position in both lists.

`REQUIRED_ASSETS` includes every entry in `FRUITS`, so the start-up check finds
the new file. Each fruit is scaled to `FRUIT_DIM` when it loads, so its size
in the file does not matter.

## Add a feature

- The brush colours are `PALETTE_HEX`. Camera limits and canvas size are the
  constants at the top of the file.
- The room is built in `_setup_scene()`, the right-hand panel in
  `_setup_right_ui()`, and painting happens in `_stamp()` and `_paint_at_mouse()`.

## Add an asset

- Put new models and textures in `assets/` and add each file name to
  `REQUIRED_ASSETS` (fruit are added for you through `FRUITS`). Poly Haven
  files named like the others (`<id>_4k.glb`, `<id>_diff_4k.jpg`) are then
  downloaded by `scripts/fetch_assets.py`.
- Please do not commit the large Poly Haven files.

## Licence and assets

- Assets must be CC0 (like the Poly Haven ones) or your own work. Please say
  where each asset comes from in your pull request.
- The code is MIT licensed (see `LICENSE`). By sending a contribution, you
  agree that it is released under the same MIT licence.
