"""Offline tests for scripts/fetch_assets.py (no network, no Poly Haven files)."""

import hashlib
import io
import json
import struct
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import fetch_assets as fa  # noqa: E402


def test_required_assets_are_read_from_the_game():
    names = fa.required_assets()
    assert len(names) == 10
    assert "brick_wall_10_diff_4k.jpg" in names
    assert "food_apple_01_4k.glb" in names
    for name in names:
        fa.parse_name(name)


def test_required_assets_match_the_imported_game():
    pytest.importorskip("panda3d")
    sys.path.insert(0, str(ROOT))
    import still_life_painter

    assert fa.required_assets() == still_life_painter.REQUIRED_ASSETS


@pytest.mark.parametrize("name, expected", [
    ("food_apple_01_4k.glb", ("food_apple_01", "model", "4k", "glb")),
    ("carved_wooden_plate_4k.glb", ("carved_wooden_plate", "model", "4k", "glb")),
    ("plank_flooring_04_diff_4k.jpg", ("plank_flooring_04", "Diffuse", "4k", "jpg")),
])
def test_parse_name(name, expected):
    assert fa.parse_name(name) == expected


@pytest.mark.parametrize("name", [
    "wooden_stool_01.glb",
    "brick_wall_10_nor_gl_4k.jpg",
    "food_apple_01_diff_4k.glb",
])
def test_parse_name_rejects(name):
    with pytest.raises(ValueError):
        fa.parse_name(name)


API_MODEL = {
    "gltf": {"4k": {"gltf": {
        "url": "https://dl.polyhaven.org/file/ph-assets/Models/gltf/4k/food_apple_01/food_apple_01_4k.gltf",
        "md5": "a", "size": 2705,
        "include": {
            "food_apple_01.bin": {"url": "https://dl.polyhaven.org/b.bin", "md5": "b", "size": 170680},
            "textures/food_apple_01_diff_4k.jpg": {"url": "https://dl.polyhaven.org/d.jpg", "md5": "c",
                                                   "size": 2236886},
        },
    }}},
}
API_TEXTURE = {"Diffuse": {"4k": {"jpg": {"url": "https://dl.polyhaven.org/p.jpg", "md5": "d", "size": 9185621}}}}


def test_model_files_lists_the_gltf_and_its_includes():
    files = fa.model_files(API_MODEL, "4k")
    assert sorted(files) == ["food_apple_01.bin", "food_apple_01_4k.gltf", "textures/food_apple_01_diff_4k.jpg"]
    assert files["food_apple_01_4k.gltf"]["size"] == 2705


def test_texture_file():
    assert fa.texture_file(API_TEXTURE, "Diffuse", "4k", "jpg")["size"] == 9185621


def read_glb(path):
    data = Path(path).read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    json_len, json_type = struct.unpack_from("<II", data, 12)
    doc = json.loads(data[20:20 + json_len])
    bin_len, bin_type = struct.unpack_from("<II", data, 20 + json_len)
    blob = data[28 + json_len:28 + json_len + bin_len]
    return {"magic": magic, "version": version, "length": length, "size": len(data),
            "json_len": json_len, "json_type": json_type, "bin_len": bin_len, "bin_type": bin_type,
            "doc": doc, "blob": blob}


def test_pack_glb_embeds_the_buffer_and_images(tmp_path):
    buffer = bytes(range(12))
    image = b"\xff\xd8\xff\xe0 not a real jpeg"
    (tmp_path / "textures").mkdir()
    (tmp_path / "m.bin").write_bytes(buffer)
    (tmp_path / "textures" / "a.jpg").write_bytes(image)
    (tmp_path / "m.gltf").write_text(json.dumps({
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "m.bin", "byteLength": len(buffer)}],
        "bufferViews": [{"buffer": 0, "byteOffset": 4, "byteLength": 8}],
        "images": [{"uri": "textures/a.jpg"}],
    }))

    fa.pack_glb(tmp_path / "m.gltf", tmp_path / "m.glb")
    glb = read_glb(tmp_path / "m.glb")

    assert (glb["magic"], glb["version"]) == (b"glTF", 2)
    assert glb["length"] == glb["size"]
    assert (glb["json_type"], glb["bin_type"]) == (fa.GLB_JSON, fa.GLB_BIN)
    assert glb["json_len"] % 4 == 0 and glb["bin_len"] % 4 == 0
    doc, blob = glb["doc"], glb["blob"]
    assert doc["buffers"] == [{"byteLength": len(blob)}]
    first = doc["bufferViews"][0]
    assert blob[first["byteOffset"]:first["byteOffset"] + first["byteLength"]] == buffer[4:12]
    img = doc["images"][0]
    assert "uri" not in img and img["mimeType"] == "image/jpeg"
    view = doc["bufferViews"][img["bufferView"]]
    assert view["byteOffset"] % 4 == 0
    assert blob[view["byteOffset"]:view["byteOffset"] + view["byteLength"]] == image


def test_pack_glb_refuses_files_outside_the_model_folder(tmp_path):
    (tmp_path / "model").mkdir()
    (tmp_path / "outside.bin").write_bytes(b"1234")
    (tmp_path / "model" / "m.gltf").write_text(json.dumps({
        "asset": {"version": "2.0"},
        "buffers": [{"uri": "../outside.bin", "byteLength": 4}],
    }))
    with pytest.raises(ValueError):
        fa.pack_glb(tmp_path / "model" / "m.gltf", tmp_path / "m.glb")


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_download_checks_the_md5(tmp_path, monkeypatch):
    payload = b"texture bytes"
    monkeypatch.setattr(fa.urllib.request, "urlopen", lambda req, timeout: FakeResponse(payload))

    good = {"url": "https://dl.polyhaven.org/x.jpg", "md5": hashlib.md5(payload).hexdigest()}
    fa.download(good, tmp_path / "x.jpg")
    assert (tmp_path / "x.jpg").read_bytes() == payload

    bad = {"url": "https://dl.polyhaven.org/y.jpg", "md5": "0" * 32}
    with pytest.raises(RuntimeError):
        fa.download(bad, tmp_path / "y.jpg")
    assert not (tmp_path / "y.jpg").exists()
    assert not (tmp_path / "y.jpg.part").exists()


def test_download_sends_the_user_agent(tmp_path, monkeypatch):
    seen = {}

    def fake_urlopen(req, timeout):
        seen["agent"] = req.get_header("User-agent")
        return FakeResponse(b"x")

    monkeypatch.setattr(fa.urllib.request, "urlopen", fake_urlopen)
    fa.download({"url": "https://dl.polyhaven.org/z.jpg", "md5": hashlib.md5(b"x").hexdigest()}, tmp_path / "z.jpg")
    assert seen["agent"] == fa.USER_AGENT
