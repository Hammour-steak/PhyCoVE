"""Verify or restore pinned CC0 assets at their original provenance paths."""

import argparse
import json
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


from scene_paths import SCENE_DIR, sha256


def pinned_files():
    manifest = json.loads((SCENE_DIR / "asset_manifest.json").read_text())
    for source in manifest["source_catalogs"]:
        catalog_path = SCENE_DIR / source["file"]
        if sha256(catalog_path) != source["sha256"]:
            raise RuntimeError("Pinned source catalog changed: " + str(catalog_path))
        catalog = json.loads(catalog_path.read_text())
        groups = catalog.get("assets", [catalog])
        for asset in groups:
            for entry in asset["files"]:
                relative = entry.get("relative_path", entry.get("path"))
                yield {
                    "path": str(Path(source["asset_root"]) / relative),
                    "url": entry["url"],
                    "sha256": entry["sha256"],
                    "bytes": entry.get("size", entry.get("bytes")),
                }


def prepare(verify_only=False):
    entries = list(pinned_files())

    def restore(entry):
        path = scene_asset(SCENE_DIR, entry["path"])
        valid = (
            path.is_file()
            and path.stat().st_size == entry["bytes"]
            and sha256(path) == entry["sha256"]
        )
        if not valid:
            if verify_only:
                raise RuntimeError("Missing or changed asset: " + str(path))
            request = urllib.request.Request(
                entry["url"],
                headers={"User-Agent": "PhyCoVE; Powered by Poly Haven"},
            )
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = path.with_name(path.name + ".download")
            try:
                with (
                    urllib.request.urlopen(request, timeout=90) as response,
                    temporary.open("wb") as output,
                ):
                    for chunk in iter(lambda: response.read(2**20), b""):
                        output.write(chunk)
                if (
                    temporary.stat().st_size != entry["bytes"]
                    or sha256(temporary) != entry["sha256"]
                ):
                    raise RuntimeError("Asset download checksum mismatch: " + str(path))
                temporary.replace(path)
            finally:
                temporary.unlink(missing_ok=True)
        return {**entry, "verified": True, "reused": valid}

    with ThreadPoolExecutor(max_workers=4) as pool:
        files = list(pool.map(restore, entries))
    return {
        "accepted": True,
        "verify_only": verify_only,
        "files": files,
        "scope": "Pinned render payload only. Catalogs, asset paths and accepted outputs are never rewritten.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = prepare(args.verify_only)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2) + "\n")
    print(
        json.dumps({"accepted": True, "files_verified": len(result["files"])}, indent=2)
    )


if __name__ == "__main__":
    main()
