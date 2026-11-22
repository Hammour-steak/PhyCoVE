"""Where scene code finds assets and external tools, without machine-specific paths.

Every asset lives in <repo>/assets/<name>, where <name> is its key in <repo>/assets.json
(for example "polyhaven/rough_linen" or "blenderkit/cozy_living_room/cozy_living_room.blend").
`python3 scripts/download_assets.py --scene <scene>` fills that directory. Set PCVE_ASSETS_DIR
to keep the assets somewhere else.
"""
from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ASSETS = Path(os.environ.get("PCVE_ASSETS_DIR", REPO / "assets"))


def asset(name) -> Path:
    """Path of an asset, or of a file inside one, from its registry name.

    Frozen configurations may hold absolute paths ending in .../assets/<name>; those resolve to the
    same <name> under ASSETS.
    """
    path = Path(name)
    parts = path.parts
    if path.is_absolute():
        if "assets" not in parts:
            return path
        parts = parts[len(parts) - parts[::-1].index("assets"):]
    return ASSETS.joinpath(*parts)


def scene_asset(scene_dir, rel) -> Path:
    """`scene_dir / rel`, except that a scene's own "assets/..." files live in ASSETS/scenes/<scene>/....

    Scene code and frozen configurations name these files relative to the scene directory; only that
    one subtree lives in the shared asset directory.
    """
    rel = Path(rel)
    if rel.parts[:1] == ("assets",):
        return ASSETS.joinpath("scenes", Path(scene_dir).name, *rel.parts[1:])
    return Path(scene_dir) / rel


def _blender_version(path):
    """Sort key of .../blender-<version>-<platform>/blender: the numeric version (5.1.10 after 5.1.2), then the path."""
    match = re.match(r"blender-(\d+(?:\.\d+)*)", Path(path).parent.name)
    return (tuple(int(part) for part in match.group(1).split(".")) if match else (), str(path))


def blender(version=None) -> Path:
    """Blender executable: $BLENDER, else `blender` on PATH, else the ~/.local/opt/blender-*/blender
    with the highest version number.

    With a version such as "5.1.2", a scene that needs that release gets $BLENDER, else
    blender-<version>-*/blender from tools/ of the repository or from ~/.local/opt (never another
    version), else `blender`.
    """
    if os.environ.get("BLENDER"):
        return Path(os.environ["BLENDER"])
    if version is not None:
        installs = [path for root in (REPO / "tools", Path.home() / ".local/opt")
                    for path in sorted(root.glob(f"blender-{version}-*/blender"))]
        return installs[0] if installs else Path("blender")
    found = shutil.which("blender")
    if found:
        return Path(found)
    installs = sorted(Path.home().glob(".local/opt/blender-*/blender"), key=_blender_version)
    return installs[-1] if installs else Path("blender")
