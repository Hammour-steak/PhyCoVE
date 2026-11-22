"""Fetch the assets a scene needs into assets/<name>, as listed in assets.json.

    python3 scripts/download_assets.py --scene rigid_rigid/ramp_car_ball_collision
    python3 scripts/download_assets.py --all
    python3 scripts/download_assets.py --scene ramp_car_ball_collision --check   # report only

Files with a "url" are downloaded from their original provider and checked against sha256.
"manual" files need a provider login (BlenderKit, Sketchfab): the script prints the page and the
file to save; once saved, run again to verify. "derived" files were made by this project from
registered sources and are listed with what they are. Set PCVE_ASSETS_DIR or pass --dest to use
another asset directory. Exit status is 1 while anything is missing or does not match.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from pcve_assets import ASSETS, REPO

USER_AGENT = "pcve-asset-downloader/1.0"


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fetch(url, target, want):
    target.parent.mkdir(parents=True, exist_ok=True)
    part = target.with_name(target.name + ".part")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=120) as response, open(part, "wb") as out:
        while block := response.read(1 << 20):
            out.write(block)
    got = sha256(part)
    if got != want:
        part.unlink()
        return f"sha256 mismatch (got {got[:12]})"
    part.replace(target)
    return "downloaded"


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scene", nargs="+", default=[], help="scene directory under scripts/ (or just its name)")
    p.add_argument("--all", action="store_true", help="every asset in the registry")
    p.add_argument("--check", action="store_true", help="only report, do not download")
    p.add_argument("--dest", type=Path, default=ASSETS, help="asset directory (default: %(default)s)")
    a = p.parse_args()
    if not a.scene and not a.all:
        p.error("give --scene or --all")
    registry = json.loads((REPO / "assets.json").read_text())["assets"]
    wanted = {name: entry for name, entry in registry.items()
              if a.all or any(s == q or s.endswith("/" + q) for s in entry.get("scenes", []) for q in a.scene)}
    if not wanted:
        p.error(f"no registry entries for {a.scene}")
    problems, manual, derived = 0, {}, []
    for name, entry in wanted.items():
        for rel, f in entry["files"].items():
            target = a.dest / name / rel
            if target.is_file() and sha256(target) == f["sha256"]:
                status = "ok"
            elif "url" in f and not a.check:
                try:
                    status = fetch(f["url"], target, f["sha256"])
                except OSError as e:
                    status = f"download failed: {e}"
            elif target.is_file():
                status = "present, sha256 differs"
            else:
                status = "missing" + (" (manual)" if f.get("manual") else " (derived)" if "derived" in f else "")
            if status not in ("ok", "downloaded"):
                problems += 1
                if f.get("manual"):
                    manual.setdefault(name, []).append(rel)
                if "derived" in f:
                    derived.append((f"{name}/{rel}", f["derived"]))
            print(f"{status:24} {name}/{rel}")
    for name, rels in manual.items():
        entry = wanted[name]
        print(f"\nmanual: {name}  [{entry.get('license')}]")
        if entry.get("instructions"):
            print(f"  {entry['instructions']}")
        else:
            # Entries without a shared instruction describe their manual files one by one.
            for rel in rels:
                f = entry["files"][rel]
                print(f"  {rel}: {f.get('instructions') or f.get('source') or 'see assets.json'}")
    if derived:
        print("\nderived (made by this project, not downloadable):")
        for path, note in derived:
            print(f"  {path}: {note}")
    print(f"\n{len(wanted)} assets, {problems} file(s) missing or not matching")
    raise SystemExit(1 if problems else 0)


if __name__ == "__main__":
    main()
