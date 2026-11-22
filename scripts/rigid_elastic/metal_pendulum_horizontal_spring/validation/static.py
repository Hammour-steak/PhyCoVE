"""Record explicit visual acceptance after reviewing full-quality scene stills."""

import argparse
import json
import struct
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pipeline.build import source_config_signature
from scene_config import CASES, configuration
from scene_paths import render_signature, sha256


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--cases", nargs="+", choices=CASES, default=["source"])
    parser.add_argument(
        "--accept-reviewed",
        action="store_true",
        required=True,
        help="Operator confirms that the referenced stills have been visually inspected",
    )
    parser.add_argument(
        "--note",
        required=True,
        help="What was reviewed and the actual visual assessment",
    )
    args = parser.parse_args()
    if not args.note.strip() or "source" not in args.cases:
        parser.error("Review must include source and a nonempty assessment")
    root = args.root.resolve()
    signature = render_signature()
    images = []
    for case in args.cases:
        folder = root / "static_review" / case
        report = json.loads((folder / "render_report.json").read_text())
        config = configuration(case)
        if (
            report["config"] != config
            or report["actual_samples"] != config["render"]["samples"]
        ):
            raise RuntimeError("Static configuration or quality differs: " + case)
        if any(report.get(key) != value for key, value in signature.items()):
            raise RuntimeError("Static implementation is stale: " + case)
        if case == "source" and not {1, 9, 17}.issubset(report["completed_frames"]):
            raise RuntimeError(
                "Source release, compression and rebound stills are required"
            )
        for frame in report["completed_frames"]:
            path = folder / f"{frame:04d}.png"
            with path.open("rb") as stream:
                header = stream.read(24)
            if (
                header[:8] != b"\x89PNG\r\n\x1a\n"
                or list(struct.unpack(">II", header[16:24]))
                != config["render"]["resolution"]
            ):
                raise RuntimeError(
                    "Invalid or reduced-resolution static frame: " + str(path)
                )
            images.append(
                {
                    "case": case,
                    "frame": frame,
                    "path": str(path),
                    "sha256": sha256(path),
                }
            )
    result = {
        "accepted": True,
        "source_config_sha256": source_config_signature(),
        "asset_manifest_sha256": signature["asset_manifest_sha256"],
        "reviewed_images": images,
        "operator_assessment": args.note,
        "scope": "Explicit visual assessment plus technical still checks. The script does not infer visual realism from image dimensions or hashes.",
    }
    target = root / "static_acceptance/acceptance.json"
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps({"accepted": True, "reviewed_images": len(images)}, indent=2))


if __name__ == "__main__":
    main()
