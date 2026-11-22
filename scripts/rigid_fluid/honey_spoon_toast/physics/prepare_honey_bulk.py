"""Check the accepted bulk particles before copying their read-only surface cache."""
import argparse
from pathlib import Path
import shutil
import numpy as np


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--bulk-run", type=Path, required=True)
    a = p.parse_args()
    for frame in range(1, 97):
        with np.load(a.run / "particles" / f"frame_{frame:04d}.npz") as new, np.load(a.bulk_run / "particles" / f"frame_{frame:04d}.npz") as old:
            if not np.array_equal(new["honey_pos"], old["honey_pos"]):
                raise RuntimeError(f"Bulk state differs at frame {frame}; do not reuse these meshes")
    meshes = a.bulk_run / "meshes_smooth"
    if not all((meshes / f"honey_{frame:04d}.npz").is_file() for frame in range(1, 97)):
        raise FileNotFoundError(f"Incomplete 96-frame bulk surface cache: {meshes}")
    shutil.copytree(meshes, a.run / "meshes_smooth")
    shutil.copy2(a.bulk_run / "meshing_report_meshes_smooth.json", a.run)


if __name__ == "__main__":
    main()
