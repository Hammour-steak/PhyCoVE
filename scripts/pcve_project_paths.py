"""Repository-relative path helpers shared by scene folders."""
from functools import lru_cache
from pathlib import Path
import os
import sys


def project_root(anchor):
    anchor = Path(anchor).resolve()
    candidates = (anchor, *anchor.parents)
    for candidate in candidates:
        if (candidate / "scripts" / "scene_registry.json").is_file():
            return candidate
    raise FileNotFoundError(f"Cannot locate project root above {anchor}; expected scripts/scene_registry.json")


def suite_output_root(scene, parent=None):
    """Directory a builder writes a source/edit suite to: <parent>/pcve_<scene>_suite.

    Every caller writes there, so the default is never a published suite in renders/pcve_suites/:
    it is renders/<scene>/suite_build/, beside the scene's native data on the volume that holds
    renders/pcve_suites.
    """
    if parent is None:
        renders = project_root(__file__) / "renders"
        parent = (renders / "pcve_suites").resolve().parent / scene / "suite_build"
    return Path(parent).expanduser() / f"pcve_{scene}_suite"


def scene_root(anchor):
    """Find the scene folder from argv first, then from the helper's parents."""
    candidates = []
    if sys.argv and sys.argv[0] not in {"-", ""}:
        argv_path = Path(sys.argv[0]).expanduser()
        if not argv_path.is_absolute():
            argv_path = Path.cwd() / argv_path
        candidates.append(argv_path.resolve().parent)
    anchor = Path(anchor).resolve()
    candidates.extend(anchor.parents)
    seen = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if any(candidate.glob("simulate_*.py")) and any(candidate.glob("render_*.py")):
            return candidate
    raise FileNotFoundError(f"Cannot locate scene entrypoints above {anchor}")


@lru_cache(maxsize=None)
def _asset_links(assets):
    """(link path relative to the asset directory, resolved target) for every symlink under it.

    The most specific target comes first. Symlinked directories are not descended into.
    """
    links = []
    for top, dirs, files in os.walk(assets):
        for name in dirs + files:
            link = Path(top) / name
            if link.is_symlink():
                links.append((link.relative_to(assets), link.resolve()))
    return tuple(sorted(links, key=lambda item: (-len(item[1].parts), str(item[0]))))


def project_relative(path):
    """Stable fingerprint key for repository files and relocated shared assets.

    Asset keys stay assets/<name> whether the asset directory is a real directory, a
    PCVE_ASSETS_DIR overlay, or holds symlinks to storage elsewhere.
    """
    from pcve_assets import ASSETS, REPO
    assets = Path(os.path.normpath(ASSETS.absolute()))
    # The path as given, inside the asset directory (symlinks not followed).
    try:
        return Path("assets") / Path(os.path.normpath(Path(path).absolute())).relative_to(assets)
    except ValueError:
        pass
    path = Path(path).resolve()
    try:
        return Path("assets") / path.relative_to(ASSETS.resolve())
    except ValueError:
        pass
    # An already resolved path inside the target of a symlink under the asset directory.
    for link, target in _asset_links(str(assets)):
        try:
            return Path("assets") / link / path.relative_to(target)
        except ValueError:
            continue
    return path.relative_to(REPO.resolve())
