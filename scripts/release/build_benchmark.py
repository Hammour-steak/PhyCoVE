"""Build the PhyCoVE release (the Hugging Face dataset ccmoony/PhyCoVE) from the published suites.

Reads <repo>/renders/pcve_suites/pcve_*_suite and writes <repo>/renders/phycove_release/
(or --out DIR) with:

    README.md                     dataset card, copied from scripts/release/dataset_card.md
    LICENSE                       copied from <repo>/LICENSE
    .gitattributes, .gitignore    Hugging Face repository settings
    assets.json                   copied from <repo>/assets.json
    benchmark_manifest.json       sources, edits, counts and scene metadata
    metadata.jsonl                one row per edit, bilingual prompts
    metadata_viewer.jsonl         the English-only projection read by the Dataset Viewer
    scenes/<scene>/cases/<case_id>/{video.mp4, prompts.json, ground_truth_transforms.json}
    splits/all.txt and splits/by_{category,kind,property,timing}/*.txt
    real/                         the PhyCoVE-Real subset, copied verbatim from --real DIR

Edits are listed in the order of each suite's suite_manifest.json. Case prompts.json files are
written in the release's compact form (no format_version, availability, application_time_sec,
physics_override, physics_diff or prompt_provenance; an empty object_id is filled from the edit
DSL). Videos and ground truth are copied byte for byte.

--checksums also writes verify.py (copied from scripts/release/verify.py) and SHA256SUMS
("<sha256>  <path>" for every other file, sorted by path), as in the local release snapshot.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import re
import shutil
from collections import defaultdict
from fractions import Fraction
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[2]
RENDERS = WORKSPACE / "renders" / "pcve_suites"
SCRIPTS = WORKSPACE / "scripts"
OUT = WORKSPACE / "renders" / "phycove_release"
BENCHMARK_NAME = "PhyCoVE"
INTERACTION_CATEGORIES = ("rigid_rigid", "rigid_fluid", "elastic_fluid", "rigid_elastic", "elastic_elastic")
CASE_FILES = ("video.mp4", "ground_truth_transforms.json")
PROMPTS_SCHEMA = {
    "flavors": ["vague", "quantitative"],
    "languages": ["zh", "en"],
    "notes": "Original text is preserved. Quantitative versions specify numerical values or multipliers.",
}
GITATTRIBUTES = "*.mp4 filter=lfs diff=lfs merge=lfs -text\n"
GITIGNORE = ".DS_Store\n__pycache__/\n*.pyc\n.cache/\n.venv/\n*.blend1\n*.blend2\n"
# The Dataset Viewer index is English-only; these DSL hints are written in Chinese in the suites.
VIEWER_HINTS = {"向左偏": "offset left", "向右偏": "offset right"}
# Keys of a case prompts.json kept in the release, in order (edit cases also keep the last three).
PROMPT_KEYS = ("schema_version", "scene", "case_id", "kind", "source_case_id", "prompts")
EDIT_PROMPT_KEYS = ("edit_dsl", "object_id", "applies_from_frame")


DSL_SET_RE = re.compile(
    r"^SET\s+(\w+)\.(\w+)\s+(?:TIMES\s+(\d+\s*/\s*\d+|[-\d.eE+]+)"
    r"|TO\s+(\S.*?))\s*(?:HINT.*)?$"
)
DSL_DEL_RE = re.compile(r"^DELETE\s+(\w+)\s*(?:HINT.*)?$")
# "AT FRAME n" says the edit lands partway through the clip instead of holding
# from the first frame. It is lifted off before the statement is matched, the
# same way the DSL module parses it.
DSL_TIMING_RE = re.compile(
    r"^(?P<body>.*?)\s+AT\s+FRAME\s+(?P<frame>\d+)"
    r"(?P<hint>(?:\s+HINT\s+\"[^\"]*\")?)\s*$"
)
DSL_ADD_RE = re.compile(
    r"^ADD\s+(\w+)\s+BETWEEN\s+(\w+)\s+AND\s+(\w+)"
    r"\s+AT\s+(?:(MIDPOINT)|(\d+)\s*/\s*(\d+)\s+FROM\s+(\w+))\s*(?:HINT.*)?$"
)


def parse_dsl(dsl: str) -> dict:
    dsl = dsl.strip()
    at_frame = None
    m = DSL_TIMING_RE.match(dsl)
    if m:
        dsl = (m.group("body") + m.group("hint")).strip()
        at_frame = int(m.group("frame"))
    m = DSL_SET_RE.match(dsl)
    if m:
        parsed = {"kind": "SET", "object": m.group(1), "property": m.group(2), "factor": m.group(3)}
    elif DSL_DEL_RE.match(dsl):
        parsed = {"kind": "DELETE", "object": DSL_DEL_RE.match(dsl).group(1), "property": None}
    elif DSL_ADD_RE.match(dsl):
        # ADD carries no property: like DELETE it moves an object along the presence axis.
        parsed = {"kind": "ADD", "object": DSL_ADD_RE.match(dsl).group(1), "property": None}
    else:
        raise ValueError(f"Cannot parse DSL: {dsl!r}")
    parsed["at_frame"] = at_frame
    return parsed


def classify_outcome(parsed: dict) -> str:
    """Coarse label from the DSL alone: the direction of a TIMES factor, else "change"."""
    if parsed["kind"] == "DELETE":
        return "object_removed"
    if parsed["kind"] == "ADD":
        return "object_added"
    factor = parsed.get("factor")
    if factor is None:
        return f"{parsed['property']}_change"
    value = float(Fraction(factor.replace(" ", "")))
    delta = "increase" if value > 1 else "decrease" if value < 1 else "change"
    return f"{parsed['property']}_{delta}"


def scene_category(scene: str) -> str:
    matches = [c for c in INTERACTION_CATEGORIES if (SCRIPTS / c / scene).is_dir()]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one scripts/<interaction_category>/{scene} directory; found {matches}")
    return matches[0]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, data) -> None:
    write_text(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def sha256sums(root: Path) -> str:
    """SHA256SUMS text for every file under root except SHA256SUMS itself, sorted by path."""
    sums = {}
    for path in root.rglob("*"):
        rel = path.relative_to(root).as_posix()
        if path.is_file() and rel != "SHA256SUMS":
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for block in iter(lambda: stream.read(4 << 20), b""):
                    digest.update(block)
            sums[rel] = digest.hexdigest()
    return "".join(f"{h}  {p}\n" for p, h in sorted(sums.items()))


def compact_prompts(record: dict, parsed: dict | None) -> dict:
    out = {k: record[k] for k in PROMPT_KEYS if k in record}
    if parsed is not None:
        out["edit_dsl"] = record["edit_dsl"]
        out["object_id"] = record.get("object_id") or parsed["object"]
        out["applies_from_frame"] = record.get("applies_from_frame") or parsed["at_frame"] or 1
    return out


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description="Build the PhyCoVE release from renders/pcve_suites.")
    parser.add_argument("--out", type=Path, default=OUT, help="release directory (default: <repo>/renders/phycove_release)")
    parser.add_argument("--checksums", action="store_true", help="also write verify.py and SHA256SUMS, then run verify.py")
    parser.add_argument("--real", type=Path, help="PhyCoVE-Real directory, copied verbatim to <out>/real")
    args = parser.parse_args(argv)
    out = args.out.expanduser().resolve()
    suite_dirs = sorted(RENDERS.glob("pcve_*_suite"))
    if not suite_dirs:
        raise SystemExit(f"No suites found in {RENDERS}")
    if out == RENDERS.resolve() or RENDERS.resolve() in out.parents:
        raise SystemExit("Write the release outside renders/pcve_suites")

    scenes, sources, edits, scene_metadata, rows = [], [], [], [], []
    splits = {axis: defaultdict(list) for axis in ("by_category", "by_kind", "by_property", "by_timing")}
    for suite_dir in suite_dirs:
        scene = suite_dir.name[len("pcve_"):-len("_suite")]
        category = scene_category(scene)
        manifest = read_json(suite_dir / "suite_manifest.json")
        source_rec = manifest.get("source") or {}
        src_case = source_rec.get("case_id") or "source"
        cases = suite_dir / "cases"

        def case_info(case_id):
            prompts = read_json(cases / case_id / "prompts.json")
            validation = read_json(cases / case_id / "video_validation.json")
            return prompts, validation

        def copy_case(case_id, prompts, parsed):
            dst = out / "scenes" / scene / "cases" / case_id
            dst.mkdir(parents=True, exist_ok=True)
            for name in CASE_FILES:
                shutil.copyfile(cases / case_id / name, dst / name)
            write_json(dst / "prompts.json", compact_prompts(prompts, parsed))

        scenes.append(scene)
        scene_metadata.append({"scene": scene, "title": manifest.get("title"), "interaction_category": category})
        src_prompts, src_validation = case_info(src_case)
        copy_case(src_case, src_prompts, None)
        src_video = f"scenes/{scene}/cases/{src_case}/video.mp4"
        sources.append({
            "global_id": f"{scene}/{src_case}", "scene": scene, "case_id": src_case,
            "interaction_category": category, "duration_sec": src_validation["duration_sec"],
            "prompts": src_prompts["prompts"],
            "ground_truth": f"scenes/{scene}/cases/{src_case}/ground_truth_transforms.json",
            "video_sha256": src_validation["sha256"],
            "original_validation_status": source_rec.get("status", "not_recorded"),
            "video": src_video, "editable_objects": [],
        })
        for rec in manifest.get("edits") or []:
            case_id = rec["case_id"]
            prompts, validation = case_info(case_id)
            parsed = parse_dsl(prompts["edit_dsl"])
            copy_case(case_id, prompts, parsed)
            global_id = f"{scene}/{case_id}"
            source_case = prompts.get("source_case_id") or src_case
            frame = prompts.get("applies_from_frame") or parsed["at_frame"] or 1
            timing = "partway" if frame > 1 else "whole_clip"
            physics_diff = prompts.get("physics_diff") or {}
            object_id = prompts.get("object_id") or parsed["object"]
            edit = {
                "global_id": global_id, "scene": scene, "case_id": case_id, "interaction_category": category,
                "duration_sec": validation["duration_sec"], "prompts": prompts["prompts"],
                "ground_truth": f"scenes/{scene}/cases/{case_id}/ground_truth_transforms.json",
                "video_sha256": validation["sha256"],
                "original_validation_status": rec.get("status", "not_recorded"),
                "source_case_id": source_case,
                "source_video": f"scenes/{scene}/cases/{source_case}/video.mp4",
                "edited_video": f"scenes/{scene}/cases/{case_id}/video.mp4",
                "edit_dsl": prompts["edit_dsl"], "edit_kind": parsed["kind"], "object_id": object_id,
                "property": parsed["property"], "outcome_type": classify_outcome(parsed),
                "applies_from_frame": frame, "timing": timing, "physics_diff": physics_diff,
                "edit_summary": rec.get("edit_summary") or "",
            }
            edits.append(edit)
            p, s = prompts["prompts"], src_prompts["prompts"]
            width, height = validation["resolution"]
            rows.append({
                "scene": scene, "scene_title": manifest.get("title"), "interaction_category": category,
                "id": global_id, "case_id": case_id, "file_name": edit["edited_video"],
                "prompt_vague_zh": p["vague"]["zh"], "prompt_vague_en": p["vague"]["en"],
                "prompt_quantitative_zh": p["quantitative"]["zh"], "prompt_quantitative_en": p["quantitative"]["en"],
                "width": width, "height": height, "fps": validation["fps"], "frames": validation["frames"],
                "duration_sec": validation["duration_sec"], "codec": "h264", "video_sha256": validation["sha256"],
                "original_validation_status": edit["original_validation_status"],
                "source_case_id": source_case, "source_file_name": edit["source_video"],
                "source_video_sha256": src_validation["sha256"] if source_case == src_case
                else read_json(cases / source_case / "video_validation.json")["sha256"],
                "edit_dsl": prompts["edit_dsl"], "object_id": prompts.get("object_id"), "applies_from_frame": frame,
                "application_time_sec": (frame - 1) / 24,
                "source_prompt_vague_zh": s["vague"]["zh"], "source_prompt_vague_en": s["vague"]["en"],
                "source_prompt_quantitative_zh": s["quantitative"]["zh"],
                "source_prompt_quantitative_en": s["quantitative"]["en"],
                "ground_truth": edit["ground_truth"],
            })
            splits["by_category"][category].append(global_id)
            splits["by_kind"][parsed["kind"]].append(global_id)
            splits["by_property"][parsed["property"] or "presence"].append(global_id)
            splits["by_timing"][timing].append(global_id)
        print(f"[ok] {scene}: 1 source + {len(manifest.get('edits') or [])} edits")

    counts = {"scenes": len(scenes), "sources": len(sources), "edits": len(edits),
              **{axis: {k: len(v) for k, v in splits[axis].items()}
                 for axis in ("by_property", "by_timing", "by_kind", "by_category")}}
    write_json(out / "benchmark_manifest.json", {
        "schema_version": 1, "benchmark_name": BENCHMARK_NAME, "prompts_schema": PROMPTS_SCHEMA,
        "properties_vocab": sorted(k for k in splits["by_property"] if k != "presence"),
        "scenes": scenes, "counts": counts, "sources": sources, "edits": edits,
        "scene_metadata": scene_metadata,
    })
    write_text(out / "metadata.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in rows))
    viewer = []
    for r in rows:
        v = {k: x for k, x in r.items() if not k.endswith("_zh") and k != "scene_title"}
        for zh, en in VIEWER_HINTS.items():
            v["edit_dsl"] = v["edit_dsl"].replace(f'HINT "{zh}"', f'HINT "{en}"')
        viewer.append(v)
    write_text(out / "metadata_viewer.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in viewer))
    write_text(out / "splits" / "all.txt", "".join(e["global_id"] + "\n" for e in edits))
    for axis, groups in splits.items():
        for key, ids in groups.items():
            write_text(out / "splits" / axis / f"{key}.txt", "".join(i + "\n" for i in ids))
    shutil.copyfile(SCRIPTS / "release" / "dataset_card.md", out / "README.md")
    shutil.copyfile(WORKSPACE / "LICENSE", out / "LICENSE")
    shutil.copyfile(WORKSPACE / "assets.json", out / "assets.json")
    write_text(out / ".gitattributes", GITATTRIBUTES)
    write_text(out / ".gitignore", GITIGNORE)
    if args.real:
        real = args.real.expanduser().resolve()
        if not (real / "benchmark_manifest.json").is_file():
            raise SystemExit(f"{real} has no benchmark_manifest.json")
        shutil.copytree(real, out / "real", dirs_exist_ok=True)
        print(f"[release] PhyCoVE-Real copied from {real}")
    else:
        print("[release] no --real given: PhyCoVE-Real is not included")
    if args.checksums:
        shutil.copyfile(SCRIPTS / "release" / "verify.py", out / "verify.py")
        write_text(out / "SHA256SUMS", sha256sums(out))
        subprocess.run([sys.executable, str(out / "verify.py"), "--root", str(out)], check=True)
    print(f"[release] {len(scenes)} scenes, {len(sources)} sources, {len(edits)} edits -> {out}")


if __name__ == "__main__":
    main()
