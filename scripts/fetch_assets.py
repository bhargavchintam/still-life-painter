"""Download the CC0 Poly Haven assets Still Life Painter needs into assets/.

The game loads the textures and models named in REQUIRED_ASSETS in
still_life_painter.py. Poly Haven serves each model as a .gltf file with a
separate .bin buffer and .jpg textures, but the game loads .glb, so this script
downloads the glTF files and packs them into one .glb per model. Every download
is checked against the MD5 that the Poly Haven API lists for it.

Assets: CC0, from Poly Haven (https://polyhaven.com). Powered by Poly Haven.

Usage:
    python scripts/fetch_assets.py            # download the files that are missing
    python scripts/fetch_assets.py --dry-run  # list the files and sizes only
    python scripts/fetch_assets.py --force    # download every file again

Standard library only, so it runs before Panda3D is installed.
"""

import argparse
import ast
import base64
import hashlib
import json
import re
import struct
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://api.polyhaven.com/files/"
# Poly Haven's API terms ask every caller to send a user-agent that names the app.
USER_AGENT = "still-life-painter-fetch-assets/1.0 (+https://github.com/bhargavchintam/still-life-painter)"
ROOT = Path(__file__).resolve().parent.parent
GAME = ROOT / "still_life_painter.py"

# <poly haven id>_<res>.glb for models, <poly haven id>_diff_<res>.jpg for textures.
NAME = re.compile(r"^(?P<id>[a-z0-9_]+?)(?P<diff>_diff)?_(?P<res>\d+k)\.(?P<ext>glb|jpg|png)$")
MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
GLB_JSON, GLB_BIN = 0x4E4F534A, 0x004E4942


def required_assets(game=GAME):
    """REQUIRED_ASSETS from the game's source, read with ast so Panda3D is not imported."""
    lists = {}
    for node in ast.parse(Path(game).read_text(encoding="utf-8")).body:
        if not (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and isinstance(node.value, ast.List)):
            continue
        items = []
        try:
            for elt in node.value.elts:
                if isinstance(elt, ast.Starred) and isinstance(elt.value, ast.Name):
                    items.extend(lists[elt.value.id])
                else:
                    items.append(ast.literal_eval(elt))
        except (KeyError, ValueError):
            continue
        lists[node.targets[0].id] = items
    return lists["REQUIRED_ASSETS"]


def parse_name(name):
    """'food_apple_01_4k.glb' -> ('food_apple_01', 'model', '4k', 'glb');
    'brick_wall_10_diff_4k.jpg' -> ('brick_wall_10', 'Diffuse', '4k', 'jpg')."""
    m = NAME.match(name)
    if not m:
        raise ValueError(f"not a Poly Haven file name this script knows: {name}")
    if m["ext"] == "glb":
        if m["diff"]:
            raise ValueError(f"a model name has no map part: {name}")
        return m["id"], "model", m["res"], "glb"
    if not m["diff"]:
        raise ValueError(f"only diffuse textures are supported: {name}")
    return m["id"], "Diffuse", m["res"], m["ext"]


def model_files(info, res):
    """The .gltf file and every file it includes, from a files/<id> API answer:
    {relative path: {"url", "md5", "size"}}."""
    entry = info["gltf"][res]["gltf"]
    files = {Path(urllib.parse.urlparse(entry["url"]).path).name: entry}
    files.update(entry.get("include", {}))
    return files


def texture_file(info, map_name, res, ext):
    """One texture map from a files/<id> API answer: {"url", "md5", "size"}."""
    return info[map_name][res][ext]


def safe_path(base, rel):
    """base/rel, refusing anything that would land outside base."""
    base = Path(base).resolve()
    path = (base / rel).resolve()
    if base not in path.parents:
        raise ValueError(f"refusing a path outside {base}: {rel}")
    return path


def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.load(resp)


def download(entry, dest):
    """Download entry["url"] to dest and check entry["md5"]; nothing is left behind on a mismatch."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    md5 = hashlib.md5()
    req = urllib.request.Request(entry["url"], headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=120) as resp, open(part, "wb") as out:
        for chunk in iter(lambda: resp.read(1 << 16), b""):
            md5.update(chunk)
            out.write(chunk)
    if md5.hexdigest() != entry["md5"]:
        part.unlink()
        raise RuntimeError(f"MD5 mismatch for {entry['url']}")
    part.replace(dest)


def _read_uri(base, uri):
    if uri.startswith("data:"):
        return base64.b64decode(uri.split(",", 1)[1])
    return safe_path(base, urllib.parse.unquote(uri)).read_bytes()


def _image_mime(uri):
    if uri.startswith("data:"):
        return uri[5:].split(";", 1)[0]
    return MIME[Path(urllib.parse.unquote(uri)).suffix.lower()]


def pack_glb(gltf_path, glb_path):
    """Pack a .gltf with external buffers and images into one binary .glb (glTF 2.0)."""
    gltf_path = Path(gltf_path)
    base = gltf_path.parent
    doc = json.loads(gltf_path.read_text(encoding="utf-8"))
    blob = bytearray()

    def append(data):
        blob.extend(b"\0" * (-len(blob) % 4))
        offset = len(blob)
        blob.extend(data)
        return offset

    offsets = [append(_read_uri(base, buf["uri"])) for buf in doc.get("buffers", [])]
    views = doc.setdefault("bufferViews", [])
    for view in views:
        view["byteOffset"] = view.get("byteOffset", 0) + offsets[view["buffer"]]
        view["buffer"] = 0
    for image in doc.get("images", []):
        uri = image.pop("uri", None)
        if uri is None:
            continue
        data = _read_uri(base, uri)
        views.append({"buffer": 0, "byteOffset": append(data), "byteLength": len(data)})
        image["bufferView"] = len(views) - 1
        image.setdefault("mimeType", _image_mime(uri))
    blob.extend(b"\0" * (-len(blob) % 4))
    doc["buffers"] = [{"byteLength": len(blob)}]

    text = json.dumps(doc, separators=(",", ":")).encode("utf-8")
    text += b" " * (-len(text) % 4)
    with open(glb_path, "wb") as out:
        out.write(struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(text) + 8 + len(blob)))
        out.write(struct.pack("<II", len(text), GLB_JSON))
        out.write(text)
        out.write(struct.pack("<II", len(blob), GLB_BIN))
        out.write(blob)


def fetch_model(files, dest):
    """Download a model's glTF files into a temporary folder and pack them into dest."""
    with tempfile.TemporaryDirectory() as tmp:
        for rel, entry in files.items():
            download(entry, safe_path(tmp, rel))
        gltf = next(rel for rel in files if rel.endswith(".gltf"))
        part = dest.with_name(dest.name + ".part")
        pack_glb(Path(tmp) / gltf, part)
        part.replace(dest)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Download the CC0 Poly Haven assets the game needs.")
    ap.add_argument("--assets-dir", type=Path, default=ROOT / "assets",
                    help="where the game looks for its files (default: assets/ next to the game)")
    ap.add_argument("--force", action="store_true", help="download files that are already there")
    ap.add_argument("--dry-run", action="store_true", help="list the files and sizes, download nothing")
    args = ap.parse_args(argv)

    print("Assets: CC0, from Poly Haven (https://polyhaven.com). Powered by Poly Haven.")
    names = required_assets()
    todo = [n for n in names if args.force or not (args.assets_dir / n).is_file()]
    for name in names:
        if name not in todo:
            print(f"  have      {name}")
    total = 0
    try:
        for name in todo:
            asset_id, kind, res, ext = parse_name(name)
            info = fetch_json(API + asset_id)
            dest = args.assets_dir / name
            if kind == "model":
                files = model_files(info, res)
                size = sum(f["size"] for f in files.values())
                print(f"  {'list' if args.dry_run else 'get'}  {size / 1e6:5.1f} MB  {name}  "
                      f"({len(files)} glTF files, packed into .glb)")
                if not args.dry_run:
                    args.assets_dir.mkdir(parents=True, exist_ok=True)
                    fetch_model(files, dest)
            else:
                entry = texture_file(info, kind, res, ext)
                size = entry["size"]
                print(f"  {'list' if args.dry_run else 'get'}  {size / 1e6:5.1f} MB  {name}")
                if not args.dry_run:
                    download(entry, dest)
            total += size
    except (urllib.error.URLError, RuntimeError, KeyError, ValueError) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 1
    verb = "would download" if args.dry_run else "downloaded"
    print(f"{len(todo)} of {len(names)} files {verb} ({total / 1e6:.1f} MB) into {args.assets_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
