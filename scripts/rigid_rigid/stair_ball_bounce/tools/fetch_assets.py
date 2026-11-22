"""Fetch the CC0 Poly Haven props and sunny HDRI used by the stairwell look, with manifests."""
from __future__ import annotations
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
MODELS = ["potted_plant_04", "hanging_picture_frame_02"]
HDRIS = {"sunny_rose_garden": "8k"}
RES = "2k"
UA = {"User-Agent": "PhyCoVE asset fetch (research; CC0 assets)"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return json.load(r)


def fetch(url, folder, rel, md5=None):
    dest = folder/rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.is_file() or (md5 and hashlib.md5(dest.read_bytes()).hexdigest() != md5):
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=300) as r:
            dest.write_bytes(r.read())
    data = dest.read_bytes()
    if md5 and hashlib.md5(data).hexdigest() != md5:
        raise RuntimeError(f"md5 mismatch for {url}")
    return {"path": str(rel),
            "url": url, "bytes": len(data), "md5": hashlib.md5(data).hexdigest(), "sha256": hashlib.sha256(data).hexdigest()}


def manifest(asset, files, use):
    info = get_json(f"https://api.polyhaven.com/info/{asset}")
    folder = ROOT/"assets/polyhaven"/asset
    (folder/"api_info.json").write_text(json.dumps(info, indent=2)+"\n")
    out = {"asset_id": asset, "name": info["name"], "authors": info["authors"], "source": f"https://polyhaven.com/a/{asset}",
           "license": "CC0", "license_reference": "https://polyhaven.com/license", "use": use, "files": files}
    (folder/"asset_manifest.json").write_text(json.dumps(out, indent=2, ensure_ascii=False)+"\n")
    (folder/"ATTRIBUTION.txt").write_text(f"{info['name']} by {', '.join(info['authors'])}, Poly Haven, CC0. https://polyhaven.com/a/{asset}\n")


def main():
    for asset in MODELS:
        api = get_json(f"https://api.polyhaven.com/files/{asset}")["blend"][RES]["blend"]
        folder = ROOT/"assets/polyhaven"/asset
        files = [dict(fetch(api["url"], folder, Path(api["url"]).name, api["md5"]), channel="blend", resolution=RES)]
        for rel, item in api.get("include", {}).items():
            files.append(dict(fetch(item["url"], folder, rel, item["md5"]), channel="texture", resolution=RES))
        manifest(asset, files, "Static household prop outside the solved ball corridor.")
    for asset, res in HDRIS.items():
        api = get_json(f"https://api.polyhaven.com/files/{asset}")["hdri"][res]["hdr"]
        folder = ROOT/"assets/polyhaven"/asset
        files = [dict(fetch(api["url"], folder, Path(api["url"]).name, api["md5"]), channel="hdri", resolution=res)]
        manifest(asset, files, "Sunlit exterior and incident daylight beyond actual 3D window geometry.")
    print("ok", file=sys.stderr)


if __name__ == "__main__":
    main()
