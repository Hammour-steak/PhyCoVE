"""Download the CC0 Poly Haven lawn texture, grass/dandelion models and garden HDRI used around the pool."""
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4] / "assets"
# Poly Haven refuses urllib's default user agent.
opener = urllib.request.build_opener()
opener.addheaders = [("User-Agent", "PhyCoVE asset fetch")]
urllib.request.install_opener(opener)


def files(slug):
    return json.load(urllib.request.urlopen(f"https://api.polyhaven.com/files/{slug}", timeout=60))


def get(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        urllib.request.urlretrieve(url, path)
    print(path)


texture = files("leafy_grass")
for kind in ("Diffuse", "nor_gl", "Rough", "Displacement"):
    item = texture[kind]["2k"]["jpg"]
    get(item["url"], ROOT / "polyhaven/leafy_grass" / os.path.basename(item["url"]))
hdri = files("sunny_rose_garden")["hdri"]
for res in ("8k", "1k"):
    get(hdri[res]["hdr"]["url"], ROOT / "polyhaven/sunny_rose_garden" / os.path.basename(hdri[res]["hdr"]["url"]))
for slug in ("grass_medium_01", "grass_bermuda_01", "dandelion_01"):
    gltf = files(slug)["gltf"]["1k"]["gltf"]
    get(gltf["url"], ROOT / "polyhaven_models" / slug / os.path.basename(gltf["url"]))
    for rel, inc in gltf["include"].items():
        get(inc["url"], ROOT / "polyhaven_models" / slug / rel)
