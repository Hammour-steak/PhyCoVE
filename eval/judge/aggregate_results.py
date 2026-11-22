"""Aggregate completed PC/EA records into benchmark and paper tables."""
from __future__ import annotations

import argparse
import collections
import datetime
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


MODEL_NAMES = {
    "seedance25": "Seedance 2.5",
    "minimax_h3": "MiniMax H3",
    "wan3_0_video": "Wan 3.0",
    "kling4_0_video": "Kling 4.0",
    "joyai_video_edit": "JoyAI",
    "kiwi_edit": "Kiwi",
    "omniweaving": "OmniWeaving",
    "void": "Void",
}


def atomic_json(path: Path, value: object) -> None:
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    os.replace(handle.name, path)


def edit_type(instruction: str) -> str:
    body = re.sub(r"^From frame \d+ onwards,\s*", "", instruction, flags=re.I).lower()
    if body.startswith(("remove ", "simultaneously remove ", "drain ")):
        return "Remove"
    if body.startswith(("add ", "place ")):
        return "Add"
    if body.startswith(("increase ", "reduce ", "change ", "set ", "leave ")):
        return "Modify"
    raise ValueError(f"Unclassified instruction: {instruction}")


def scores(rows: list[dict]) -> tuple[list[int], list[int]]:
    pc = [row["ratings"]["PC"]["answer"]["score"] for row in rows]
    ea = [row["ratings"]["EA"]["answer"]["score"] for row in rows]
    if not all(type(score) is int and 1 <= score <= 5 for score in pc + ea):
        raise ValueError("Every completed PC/EA record must contain an integer score in [1, 5]")
    return pc, ea


def detailed_metrics(rows: list[dict]) -> dict:
    pc, ea = scores(rows)
    n = len(rows)
    result = {"videos": n, "splits": dict(collections.Counter(r["split"] for r in rows))}
    for axis, values in (("PC", pc), ("EA", ea)):
        passed = sum(value >= 4 for value in values)
        result[axis] = {
            "mean": sum(values) / n,
            "distribution": {str(value): values.count(value) for value in range(1, 6)},
            "pass_count": passed,
            "pass_rate": passed / n,
        }
    joint = sum(p >= 4 and e >= 4 for p, e in zip(pc, ea))
    result["joint"] = {"pass_count": joint, "pass_rate": joint / n}
    configs = collections.Counter(
        (rating["judge"], rating["effort"])
        for row in rows for rating in row["ratings"].values()
    )
    result["evaluators"] = [
        {"judge": judge, "effort": effort, "scores": count}
        for (judge, effort), count in sorted(configs.items())
    ]
    return result


def compact_metrics(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0, "PC": None, "EA": None, "joint_count": None, "joint_percent": None}
    pc, ea = scores(rows)
    joint = sum(p >= 4 and e >= 4 for p, e in zip(pc, ea))
    return {
        "n": len(rows),
        "PC": sum(pc) / len(pc),
        "EA": sum(ea) / len(ea),
        "joint_count": joint,
        "joint_percent": 100 * joint / len(rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Folder with all_results.json")
    base = parser.parse_args().run_dir.expanduser().resolve()
    source_bytes = (base / "all_results.json").read_bytes()
    data = json.loads(source_bytes)
    videos = data["videos"]
    by_model: dict[str, dict[tuple[str, str, str], dict]] = collections.defaultdict(dict)
    for row in videos:
        key = row["split"], row["scene"], row["case"]
        if key in by_model[row["model"]]:
            raise ValueError(f"Duplicate model output: {row['model']} {key}")
        by_model[row["model"]][key] = row

    models = sorted(by_model)
    main_models = [model for model in models if model != "void"]
    common_main = set.intersection(*(set(by_model[model]) for model in main_models))
    common_all = set.intersection(*(set(by_model[model]) for model in models))
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    shared = {
        "source_sha256": source_sha,
        "evaluators": data.get("evaluators", []),
    }
    performance = {
        "created_at": datetime.datetime.now().astimezone().isoformat(),
        **shared,
        "aggregation": "Each generated video has equal weight; pass means score >=4; joint pass requires both PC and EA >=4.",
        "benchmark_cases": len(set.union(*(set(rows) for rows in by_model.values()))),
        "all_available": {
            model: detailed_metrics(list(by_model[model].values())) for model in models
        },
        "common_seven": {
            "cases": len(common_main),
            "models": {
                model: detailed_metrics([by_model[model][key] for key in sorted(common_main)])
                for model in main_models
            },
        },
        "common_eight": {
            "cases": len(common_all),
            "models": {
                model: detailed_metrics([by_model[model][key] for key in sorted(common_all)])
                for model in models
            },
        },
        "by_split": {
            split: {
                model: detailed_metrics([
                    row for row in by_model[model].values() if row["split"] == split
                ])
                for model in models
            }
            for split in ("sim", "real")
        },
    }

    cases = {}
    for row in videos:
        key = row["split"], row["scene"], row["case"]
        category = edit_type(row["instruction"])
        previous = cases.get(key)
        if previous and previous["edit_type"] != category:
            raise ValueError(f"Inconsistent edit type: {key}")
        cases[key] = {
            "split": key[0], "scene": key[1], "case": key[2],
            "edit_type": category, "instruction": row["instruction"],
        }
    counts = dict(collections.Counter(case["edit_type"] for case in cases.values()))
    by_edit_type = {
        **shared,
        "subset_definitions": {
            "Remove": "Remove entities, materials or standing liquid.",
            "Add": "Add or place an additional object or material.",
            "Modify": "Change physical parameters, initial states or environmental conditions.",
        },
        "benchmark_case_counts": counts,
        "aggregation": "Per-video arithmetic mean on available outputs. Joint pass requires PC >=4 and EA >=4.",
        "model_names": MODEL_NAMES,
        "overall": {
            model: compact_metrics([row for row in videos if row["model"] == model])
            for model in MODEL_NAMES
        },
        "by_edit_type": {
            model: {
                category: compact_metrics([
                    row for row in videos
                    if row["model"] == model and edit_type(row["instruction"]) == category
                ])
                for category in ("Remove", "Add", "Modify")
            }
            for model in MODEL_NAMES
        },
        "case_assignments": list(cases.values()),
    }
    if sum(counts.values()) != len(cases):
        raise AssertionError("Edit-type partition does not cover every benchmark case")

    atomic_json(base / "model_performance.json", performance)
    atomic_json(base / "model_performance_by_edit_type.json", by_edit_type)
    print(f"Aggregated {len(videos)} videos from {len(cases)} cases across {len(models)} models")


if __name__ == "__main__":
    main()
