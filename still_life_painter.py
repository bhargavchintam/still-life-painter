"""
Still Life Painter - a 3D art-studio painting minigame (Panda3D).

The screen is split: the left side shows a 3D studio (four walls, a floor, a
stool, a plate and a fruit), and the right side is a painting canvas with a
fruit selector, a colour palette and a brush-size slider. The player orbits the
camera around the fruit and paints what they see. Painting cannot be undone or
erased; the only way to start over is "Clear Canvas" in the pause menu.

Controls
  A / D        orbit the camera left / right around the pivot
  W / S        raise / lower the camera (stops at the floor and the top pole)
  UP / DOWN    zoom in / out
  Left mouse   hold and drag on the canvas to paint
  ESCAPE       pause menu (Resume / Clear Canvas / Exit)

Assets are CC0 models/textures from Poly Haven (polyhaven.com). Put the .glb
models and textures in an "assets" folder next to this file (or change ASSET_DIR
below). They are not bundled in this repo; download the CC0 originals from
Poly Haven.

Run:  python still_life_painter.py   (needs:  pip install panda3d panda3d-gltf)
"""

import os
import sys
from math import sin, cos, radians, hypot

from direct.showbase.ShowBase import ShowBase
from direct.task import Task
from direct.gui.DirectGui import (
    DirectFrame, DirectButton, DirectLabel, DirectSlider,
)
from direct.gui.DirectDialog import YesNoDialog
from direct.gui.OnscreenText import OnscreenText
from panda3d.core import (
    AmbientLight, DirectionalLight, CardMaker, Texture, TextureStage, PNMImage,
    TextNode, ClockObject, WindowProperties, loadPrcFileData, Vec3, Filename,
)

# ----------------------------------------------------------------------------
# Configuration (tune these after the first run if scale/placement looks off)
# ----------------------------------------------------------------------------
WIN_W, WIN_H = 1280, 720
loadPrcFileData("", f"win-size {WIN_W} {WIN_H}")
loadPrcFileData("", "window-title Still Life Painter")

# Asset folder, anchored to this script's location so the project stays
# self-contained no matter which directory it is launched from. Filename keeps
# the path in Panda's forward-slash form, which loadModel/loadTexture expect.
_HERE = Filename.fromOsSpecific(os.path.dirname(os.path.abspath(__file__)))
ASSET_DIR = f"{_HERE}/assets"        # folder holding the .glb files and textures
_ASSET_DIR_OS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
SPLIT = 0.6                          # left fraction of the window used by the 3D scene
A = WIN_W / float(WIN_H)             # aspect2d half-width (x runs from -A to +A)

ROOM_R = 3.0                         # half-size of the square room
WALL_H = 3.0                         # wall height

# Real-world target sizes (metres). The GLBs ship with inconsistent units and
# embedded scales, so every prop is normalised to these at load time instead of
# trusting a raw setScale. Stool/fruit are sized by height, the plate by diameter.
STOOL_H = 0.55                       # stool height (floor to seat)
PLATE_DIA = 0.34                     # plate diameter
FRUIT_DIM = 0.13                     # fruit largest dimension (keeps every fruit visible)
FRUIT_SINK = 0.7                     # how far the fruit settles into the dish (× plate thickness)
PIVOT_LIFT = 0.05                    # pivot sits just above the plate surface, where fruit rests

# Camera limits (these keep the camera inside the room and off the models)
EL_MIN, EL_MAX = -22.0, 80.0         # S stops above the floor, W stops near the pole
DIST_MIN, DIST_MAX = 0.9, 4.5        # zoom from close-up (painting) out to a room-wide view
FLOOR_CLEAR = 0.12                   # never let the camera drop below this height
ROT_SPEED, ELEV_SPEED, ZOOM_SPEED = 70.0, 55.0, 1.6

# Canvas (right panel) rectangle in aspect2d coordinates, and its pixel size
CANVAS_L, CANVAS_R = 0.45, 1.55
CANVAS_B, CANVAS_T = -0.48, 0.62
CANVAS_PX = 512
BRUSH_MIN, BRUSH_MAX = 3, 34

# Fruit order for Previous / Next (from fruitOrderRef.png)
FRUITS = [
    "food_lychee_01_4k.glb",
    "food_pomegranate_01_4k.glb",
    "food_pears_asian_01_4k.glb",
    "food_lime_01_4k.glb",
    "food_kiwi_01_4k.glb",
    "food_apple_01_4k.glb",
]
FRUIT_NAMES = ["Lychee", "Pomegranate", "Asian Pears", "Lime", "Kiwi", "Apple"]

# PICO-8 palette from colorPalette.png (hex -> used as brush colours)
PALETTE_HEX = [
    "000000", "1D2B53", "7E2553", "008751", "AB5236", "5F574F", "C2C3C7", "FFF1E8",
    "FF004D", "FFA300", "FFEC27", "00E436", "29ADFF", "83769C", "FF77A8", "FFCCAA",
]

# CC0 Poly Haven assets the README asks the player to download separately
# (not bundled in the repo). Mirrors every loadModel/loadTexture path below.
REQUIRED_ASSETS = [
    "plank_flooring_04_diff_4k.jpg",
    "brick_wall_10_diff_4k.jpg",
    "wooden_stool_01_4k.glb",
    "carved_wooden_plate_4k.glb",
    *FRUITS,
]


def _check_required_assets():
    missing = [p for p in REQUIRED_ASSETS if not os.path.isfile(os.path.join(_ASSET_DIR_OS, p))]
    if missing:
        print("Still Life Painter can't start: required asset file(s) are missing:")
        for p in missing:
            print(f"  - {p} (expected at {os.path.join(_ASSET_DIR_OS, p)})")
        print('\nThese CC0 Poly Haven assets aren\'t bundled with this repo. See the '
              '"Assets" note at the top of this file for where to get them.')
        sys.exit(1)


def hex_to_rgb(h):
    """'FF004D' -> (1.0, 0.0, 0.302)."""
    return tuple(int(h[i:i + 2], 16) / 255.0 for i in (0, 2, 4))


class StillLifePainter(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        self.clock = ClockObject.getGlobalClock()
        self.setBackgroundColor(0.10, 0.10, 0.12)

        # glTF support for the .glb assets. Recent Panda3D builds load .glb
        # natively (panda3d-gltf registers itself as a file-type plugin), so a
        # manual patch is only needed on older versions that still expose it.
        try:
            import gltf
            if hasattr(gltf, "patch_loader"):
                gltf.patch_loader(self.loader)
        except Exception as exc:                       # pragma: no cover
            print("Note: panda3d-gltf not active (", exc, ") - install panda3d-gltf")

        self.paused = False
        self.painting = False
        self.last_px = None
        self.brush_color = hex_to_rgb(PALETTE_HEX[0])  # black
        self.brush_radius = (BRUSH_MIN + BRUSH_MAX) // 2
        self.fruit_index = 0
        self.fruit_np = None

        # glTF is Y-up, Panda is Z-up. Whether the loader auto-converts differs
        # by panda3d / panda3d-gltf version, so detect it instead of hard-coding
        # a rotation (otherwise models are upright on one OS and tipped on another).
        self.up_fix = self._detect_up_fix()

        self._setup_split_screen()
        self._setup_lights()
        self._setup_scene()
        self._setup_pivot_and_camera()
        self._setup_canvas()
        self._setup_right_ui()
        self._setup_pause_menu()
        self._setup_controls()

        self.taskMgr.add(self.update, "update")

    # ------------------------------------------------------------------ setup
    def _setup_split_screen(self):
        """3D camera fills only the left part; the right part is for UI."""
        region = self.cam.node().getDisplayRegion(0)
        region.setDimensions(0.0, SPLIT, 0.0, 1.0)
        self.camLens.setAspectRatio((SPLIT * WIN_W) / WIN_H)
        # The default near plane (1.0) is larger than this tabletop scene, so a
        # close zoom would clip through the fruit/plate. Pull it in so the player
        # can get right up to the fruit to paint it.
        self.camLens.setNear(0.05)
        # opaque backboard for the right UI strip (does not cover the 3D region)
        DirectFrame(parent=self.aspect2d, frameColor=(0.16, 0.16, 0.19, 1),
                    frameSize=(0.36, A, -1.0, 1.0), pos=(0, 0, 0))

    def _setup_lights(self):
        amb = AmbientLight("amb")
        amb.setColor((0.62, 0.62, 0.66, 1))
        self.render.setLight(self.render.attachNewNode(amb))
        sun = DirectionalLight("sun")
        sun.setColor((0.95, 0.92, 0.85, 1))
        sun_np = self.render.attachNewNode(sun)
        sun_np.setHpr(-50, -55, 0)
        self.render.setLight(sun_np)
        # gentle fill from the opposite side so the far wall is not in shadow
        fill = DirectionalLight("fill")
        fill.setColor((0.35, 0.35, 0.4, 1))
        fill_np = self.render.attachNewNode(fill)
        fill_np.setHpr(130, -20, 0)
        self.render.setLight(fill_np)

    def _make_quad(self, w_half, h_half, tex_path, tex_repeat):
        cm = CardMaker("quad")
        cm.setFrame(-w_half, w_half, 0, 2 * h_half)
        np = self.render.attachNewNode(cm.generate())
        np.setTwoSided(True)
        tex = self.loader.loadTexture(f"{ASSET_DIR}/{tex_path}")
        tex.setWrapU(Texture.WMRepeat)
        tex.setWrapV(Texture.WMRepeat)
        np.setTexture(tex)
        np.setTexScale(TextureStage.getDefault(), tex_repeat[0], tex_repeat[1])
        return np

    def _setup_scene(self):
        """Floor + four walls built from scratch (CardMaker), plus the props."""
        # Floor (laid flat)
        cm = CardMaker("floor")
        cm.setFrame(-ROOM_R, ROOM_R, -ROOM_R, ROOM_R)
        floor = self.render.attachNewNode(cm.generate())
        floor.setP(-90)
        ftex = self.loader.loadTexture(f"{ASSET_DIR}/plank_flooring_04_diff_4k.jpg")
        ftex.setWrapU(Texture.WMRepeat)
        ftex.setWrapV(Texture.WMRepeat)
        floor.setTexture(ftex)
        floor.setTexScale(TextureStage.getDefault(), 4, 4)

        # Four walls
        n = self._make_quad(ROOM_R, WALL_H / 2, "brick_wall_10_diff_4k.jpg", (4, 2))
        n.setPos(0, ROOM_R, 0); n.setH(180)
        s = self._make_quad(ROOM_R, WALL_H / 2, "brick_wall_10_diff_4k.jpg", (4, 2))
        s.setPos(0, -ROOM_R, 0)
        e = self._make_quad(ROOM_R, WALL_H / 2, "brick_wall_10_diff_4k.jpg", (4, 2))
        e.setPos(ROOM_R, 0, 0); e.setH(-90)
        w = self._make_quad(ROOM_R, WALL_H / 2, "brick_wall_10_diff_4k.jpg", (4, 2))
        w.setPos(-ROOM_R, 0, 0); w.setH(90)

        # Stool. up_fix stands it upright (detected per-system); it is scaled by
        # its true height after that rotation, so its size is identical everywhere.
        stool = self._load_prop("wooden_stool_01_4k.glb", STOOL_H,
                                by_height=True, pitch=self.up_fix)
        stool_top = self._seat_on(stool, 0.0)

        # Plate, laid flat with the dish facing up, then seated on the stool.
        plate = self._load_prop("carved_wooden_plate_4k.glb", PLATE_DIA,
                                pitch=self.up_fix)
        self.plate_top = self._seat_on(plate, stool_top)

        # The fruit must rest in the dish, not on the rim, or it looks levitated.
        # Sink it most of the way down the plate's thickness into the hollow.
        plate_thickness = self.plate_top - stool_top
        self.fruit_rest_z = self.plate_top - FRUIT_SINK * plate_thickness

        self._load_fruit(0)

    # --- prop loading helpers ---------------------------------------------
    def _detect_up_fix(self):
        """Return the pitch (deg) needed to stand props upright on this system.

        Probes the plate, which is a flat disc: its thinnest axis is its normal
        (the 'up' direction). If that axis is already Z, the loader converted the
        glTF to Panda's Z-up and no fix is needed; if it is Y, the models are
        still glTF Y-up and need a +90 pitch. This keeps orientation correct
        regardless of the installed panda3d / panda3d-gltf version.
        """
        probe = self.loader.loadModel(f"{ASSET_DIR}/carved_wooden_plate_4k.glb")
        lo, hi = probe.getTightBounds()
        dims = [hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2]]
        probe.removeNode()
        thin = dims.index(min(dims))            # 0=X, 1=Y, 2=Z
        fix = 90.0 if thin == 1 else 0.0        # Y-up -> rotate; Z-up -> leave
        print(f"[orientation] plate dims={['%.3f'%d for d in dims]} "
              f"thin-axis={'XYZ'[thin]} -> up_fix={fix}")
        return fix

    def _load_prop(self, fname, target, by_height=False, pitch=0.0):
        """Load a model, stand it upright, and scale it to a real-world target.

        The up-axis rotation (pitch) is applied *before* measuring, so by_height
        measures the true vertical extent on every system regardless of whether
        the loader left the model Y-up or Z-up. Measured in render space (after a
        scale reset) so any embedded unit scale in the GLB is cancelled out and
        the final size is deterministic and identical across platforms.
        """
        np_ = self.loader.loadModel(f"{ASSET_DIR}/{fname}")
        np_.reparentTo(self.render)
        np_.setScale(1.0)
        np_.setHpr(0, pitch, 0)
        np_.setPos(0, 0, 0)
        lo, hi = np_.getTightBounds(self.render)
        extent = (hi[2] - lo[2]) if by_height else max(hi[0] - lo[0],
                                                       hi[1] - lo[1], hi[2] - lo[2])
        if extent > 1e-6:
            np_.setScale(target / extent)
        return np_

    def _seat_on(self, np_, top_z, x=0.0, y=0.0):
        """Centre the model over (x, y) and rest its lowest point at top_z.

        Some GLBs (the stool) put their origin at an edge rather than the centre,
        so we align by the geometric centre of the bounds, not the origin, to
        keep the plate and fruit centred on the seat.
        """
        np_.setPos(0, 0, 0)
        lo, hi = np_.getTightBounds(self.render)
        cx = (lo[0] + hi[0]) * 0.5
        cy = (lo[1] + hi[1]) * 0.5
        np_.setPos(x - cx, y - cy, top_z - lo[2])
        _, hi2 = np_.getTightBounds(self.render)
        return hi2[2]

    def _setup_pivot_and_camera(self):
        """Pivot is an empty node at the plate centre - never the fruit model."""
        self.pivot = self.render.attachNewNode("camPivot")
        self.pivot.setPos(0, 0, self.plate_top + PIVOT_LIFT)
        # Default to a low, pulled-back establishing shot (like the reference);
        # the player can zoom in with the arrow keys to paint the fruit close up.
        self.az, self.el, self.dist = 20.0, 9.0, 3.0
        self.disableMouse()                 # we drive the camera ourselves
        self._place_camera()

    def _place_camera(self):
        self.el = max(EL_MIN, min(EL_MAX, self.el))
        self.dist = max(DIST_MIN, min(DIST_MAX, self.dist))
        ra, re = radians(self.az), radians(self.el)
        off = Vec3(self.dist * cos(re) * sin(ra),
                   -self.dist * cos(re) * cos(ra),
                   self.dist * sin(re))
        pos = self.pivot.getPos() + off
        # keep inside the room and above the floor (no clipping)
        lim = ROOM_R - 0.25
        pos.setX(max(-lim, min(lim, pos.getX())))
        pos.setY(max(-lim, min(lim, pos.getY())))
        pos.setZ(max(FLOOR_CLEAR, pos.getZ()))
        self.camera.setPos(pos)
        self.camera.lookAt(self.pivot)

    # ------------------------------------------------------------- canvas / UI
    def _setup_canvas(self):
        self.canvas_img = PNMImage(CANVAS_PX, CANVAS_PX)
        self.canvas_img.fill(1, 1, 1)
        self.canvas_tex = Texture("canvas")
        self.canvas_tex.load(self.canvas_img)
        cm = CardMaker("canvas")
        cm.setFrame(CANVAS_L, CANVAS_R, CANVAS_B, CANVAS_T)
        self.canvas_np = self.aspect2d.attachNewNode(cm.generate())
        self.canvas_np.setTexture(self.canvas_tex)

    def _setup_right_ui(self):
        cx = (CANVAS_L + CANVAS_R) / 2.0
        DirectLabel(parent=self.aspect2d, text="Fruit Reference", scale=0.06,
                    text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(cx, 0, 0.93))
        DirectButton(parent=self.aspect2d, text="Previous", scale=0.055,
                     pos=(cx - 0.30, 0, 0.81), command=self.prev_fruit)
        DirectButton(parent=self.aspect2d, text="Next", scale=0.055,
                     pos=(cx + 0.30, 0, 0.81), command=self.next_fruit)
        # live name of the fruit currently shown (updates on Previous / Next)
        self.fruit_label = DirectLabel(
            parent=self.aspect2d, text=FRUIT_NAMES[self.fruit_index], scale=0.05,
            text_fg=(0.9, 0.9, 0.6, 1), frameColor=(0, 0, 0, 0), pos=(cx, 0, 0.70))

        # colour palette: 16 swatches in two rows of eight
        for i, h in enumerate(PALETTE_HEX):
            col = hex_to_rgb(h)
            row, c = divmod(i, 8)
            x = CANVAS_L + 0.07 + c * ((CANVAS_R - CANVAS_L - 0.1) / 7.0)
            y = -0.56 - row * 0.12
            DirectButton(parent=self.aspect2d, frameColor=(*col, 1),
                         frameSize=(-0.055, 0.055, -0.05, 0.05), pos=(x, 0, y),
                         relief="flat", command=self.set_color, extraArgs=[col])

        DirectLabel(parent=self.aspect2d, text="Brush Size", scale=0.045,
                    text_fg=(1, 1, 1, 1), frameColor=(0, 0, 0, 0), pos=(cx, 0, -0.82))
        self.brush_slider = DirectSlider(
            parent=self.aspect2d, pos=(cx, 0, -0.9), scale=0.45,
            range=(BRUSH_MIN, BRUSH_MAX), value=self.brush_radius,
            command=self.set_brush_size)

    def _setup_pause_menu(self):
        self.pause_frame = DirectFrame(
            parent=self.aspect2d, frameColor=(0.9, 0.9, 0.9, 1),
            frameSize=(-0.5, 0.5, -0.6, 0.6), pos=(0, 0, 0))
        DirectLabel(parent=self.pause_frame, text="Pause", scale=0.12,
                    text_fg=(0.25, 0.25, 0.25, 1), frameColor=(0, 0, 0, 0),
                    pos=(0, 0, 0.38))
        DirectButton(parent=self.pause_frame, text="Resume", scale=0.07,
                     pos=(0, 0, 0.12), command=self.resume,
                     relief="flat", frameColor=(0.9, 0.9, 0.9, 1))
        DirectButton(parent=self.pause_frame, text="Clear Canvas", scale=0.07,
                     pos=(0, 0, -0.06), command=self.confirm_clear,
                     relief="flat", frameColor=(0.9, 0.9, 0.9, 1),
                     text_fg=(0.85, 0.15, 0.1, 1))      # red, irreversible
        DirectButton(parent=self.pause_frame, text="Exit", scale=0.07,
                     pos=(0, 0, -0.24), command=sys.exit,
                     relief="flat", frameColor=(0.9, 0.9, 0.9, 1))
        self.pause_frame.hide()

    def _setup_controls(self):
        self.keys = {"a": False, "d": False, "w": False, "s": False,
                     "arrow_up": False, "arrow_down": False}
        for k in self.keys:
            self.accept(k, self._set_key, [k, True])
            self.accept(k + "-up", self._set_key, [k, False])
        self.accept("mouse1", self._mouse_down)
        self.accept("mouse1-up", self._mouse_up)
        self.accept("escape", self.toggle_pause)

    # --------------------------------------------------------------- handlers
    def _set_key(self, key, value):
        self.keys[key] = value

    def _mouse_down(self):
        if not self.paused:
            self.painting = True
            self.last_px = None

    def _mouse_up(self):
        self.painting = False
        self.last_px = None

    def set_color(self, col):
        self.brush_color = col

    def set_brush_size(self):
        self.brush_radius = int(self.brush_slider["value"])

    def _load_fruit(self, index):
        if self.fruit_np is not None:
            self.fruit_np.removeNode()
        self.fruit_index = index % len(FRUITS)
        self.fruit_np = self._load_prop(FRUITS[self.fruit_index], FRUIT_DIM,
                                        pitch=self.up_fix)
        self._seat_on(self.fruit_np, self.fruit_rest_z)
        if hasattr(self, "fruit_label"):
            self.fruit_label["text"] = FRUIT_NAMES[self.fruit_index]
        # NOTE: fruit is parented to render, not to the pivot, so the camera
        # pivot never moves when the fruit changes.

    def next_fruit(self):
        self._load_fruit(self.fruit_index + 1)

    def prev_fruit(self):
        self._load_fruit(self.fruit_index - 1)

    # ------------------------------------------------------------- pause/clear
    def toggle_pause(self):
        self.paused = not self.paused
        if self.paused:
            self.painting = False
            self.pause_frame.show()
        else:
            self.pause_frame.hide()

    def resume(self):
        self.paused = False
        self.pause_frame.hide()

    def confirm_clear(self):
        self.confirm = YesNoDialog(
            text="Clear the canvas?\nThis cannot be undone.",
            command=self._clear_cb)

    def _clear_cb(self, value):
        self.confirm.cleanup()
        if value == 1:
            self.canvas_img.fill(1, 1, 1)
            self.canvas_tex.load(self.canvas_img)

    # ------------------------------------------------------------------ paint
    def _stamp(self, px, py):
        r = self.brush_radius
        cr, cg, cb = self.brush_color
        img = self.canvas_img
        r2 = r * r
        x0, x1 = max(0, px - r), min(CANVAS_PX - 1, px + r)
        y0, y1 = max(0, py - r), min(CANVAS_PX - 1, py + r)
        for yy in range(y0, y1 + 1):
            dy = yy - py
            for xx in range(x0, x1 + 1):
                dx = xx - px
                if dx * dx + dy * dy <= r2:
                    img.setXel(xx, yy, cr, cg, cb)

    def _paint_at_mouse(self):
        if not self.mouseWatcherNode.hasMouse():
            return
        mx = self.mouseWatcherNode.getMouseX() * A   # to aspect2d x
        my = self.mouseWatcherNode.getMouseY()
        if not (CANVAS_L <= mx <= CANVAS_R and CANVAS_B <= my <= CANVAS_T):
            return
        u = (mx - CANVAS_L) / (CANVAS_R - CANVAS_L)
        v = 1.0 - (my - CANVAS_B) / (CANVAS_T - CANVAS_B)   # flip rows
        px, py = int(u * (CANVAS_PX - 1)), int(v * (CANVAS_PX - 1))
        if self.last_px is None:
            self._stamp(px, py)
        else:
            steps = max(1, int(hypot(px - self.last_px, py - self.last_py)))
            for i in range(steps + 1):
                t = i / steps
                self._stamp(int(self.last_px + (px - self.last_px) * t),
                            int(self.last_py + (py - self.last_py) * t))
        self.last_px, self.last_py = px, py
        self.canvas_tex.load(self.canvas_img)

    # ------------------------------------------------------------- main loop
    def update(self, task):
        if self.paused:
            return Task.cont
        dt = self.clock.getDt()
        if self.keys["a"]:
            self.az -= ROT_SPEED * dt
        if self.keys["d"]:
            self.az += ROT_SPEED * dt
        if self.keys["w"]:
            self.el += ELEV_SPEED * dt
        if self.keys["s"]:
            self.el -= ELEV_SPEED * dt
        if self.keys["arrow_up"]:
            self.dist -= ZOOM_SPEED * dt
        if self.keys["arrow_down"]:
            self.dist += ZOOM_SPEED * dt
        self._place_camera()

        if self.painting:
            self._paint_at_mouse()
        return Task.cont


if __name__ == "__main__":
    _check_required_assets()
    StillLifePainter().run()
