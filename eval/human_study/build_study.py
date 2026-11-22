#!/usr/bin/env python3
"""Build a blinded, full-pair-coverage PhyCoVE human-preference study."""
from __future__ import annotations

import argparse
import collections
import hashlib
import itertools
import json
import random
from pathlib import Path
from typing import Any

from common import (
    EDIT_TYPES,
    MODEL_NAMES,
    atomic_json,
    edit_type,
    metadata_specs_from_root,
    now_iso,
    parse_metadata_specs,
    read_json,
    task_id,
    task_key,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        description=(
            "Select a stratified task subset and create all pairwise comparisons "
            "for the seven common-coverage models, plus Void on Remove."
        )
    )
    result.add_argument("--manifest", type=Path, required=True)
    result.add_argument("--output", type=Path, required=True)
    result.add_argument("--data-root", type=Path, help="PhyCoVE data root")
    result.add_argument(
        "--metadata",
        action="append",
        default=[],
        metavar="SPLIT=PATH",
        help="Release metadata JSONL; repeat for sim/real",
    )
    result.add_argument("--main-model", action="append", default=[])
    result.add_argument("--limited-model", default="void")
    result.add_argument(
        "--limited-edit-type", default="Remove", choices=EDIT_TYPES
    )
    result.add_argument("--remove", type=int, default=20)
    result.add_argument("--add", type=int, default=10)
    result.add_argument("--modify", type=int, default=30)
    result.add_argument(
        "--all-common",
        action="store_true",
        help=(
            "Use every task shared by all main models instead of sampling; "
            "the per-edit-type quotas are ignored"
        ),
    )
    result.add_argument("--ratings-per-comparison", type=int, default=3)
    result.add_argument("--seed", type=int, default=4090)
    result.add_argument(
        "--verify-media",
        action="store_true",
        help="Require every source, GT and candidate under --data-root",
    )
    return result


def proportional_allocation(
    sizes: dict[str, int], total: int
) -> dict[str, int]:
    """Allocate a sample proportionally, preserving rare non-empty strata."""
    active = [name for name, size in sizes.items() if size > 0]
    if total > sum(sizes.values()):
        raise ValueError(f"Requested {total} items from only {sum(sizes.values())}")
    if total <= 0:
        return {name: 0 for name in sizes}

    allocation = {name: 0 for name in sizes}
    if total >= len(active):
        for name in active:
            allocation[name] = 1
        remaining = total - len(active)
    else:
        active = sorted(active, key=lambda name: (-sizes[name], name))[:total]
        for name in active:
            allocation[name] = 1
        return allocation

    capacity = {name: sizes[name] - allocation[name] for name in sizes}
    while remaining:
        available = [name for name in active if capacity[name] > 0]
        if not available:
            raise AssertionError("Stratified allocation exhausted unexpectedly")
        denominator = sum(capacity[name] for name in available)
        raw = {name: remaining * capacity[name] / denominator for name in available}
        base = {name: min(capacity[name], int(raw[name])) for name in available}
        assigned = sum(base.values())
        for name, count in base.items():
            allocation[name] += count
            capacity[name] -= count
        remaining -= assigned
        if not remaining:
            break
        order = sorted(
            (name for name in available if capacity[name] > 0),
            key=lambda name: (-(raw[name] - int(raw[name])), -capacity[name], name),
        )
        for name in order[:remaining]:
            allocation[name] += 1
            capacity[name] -= 1
        remaining -= min(remaining, len(order))
    return allocation


def select_diverse(
    tasks: list[dict[str, Any]], count: int, rng: random.Random
) -> list[dict[str, Any]]:
    """Proportionally cover interaction categories, then diversify scenes/timing."""
    if count > len(tasks):
        raise ValueError(f"Requested {count} tasks from only {len(tasks)} eligible tasks")
    buckets: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for task in tasks:
        buckets[task.get("interaction_category") or "unknown"].append(task)
    allocation = proportional_allocation(
        {name: len(items) for name, items in buckets.items()}, count
    )
    chosen: list[dict[str, Any]] = []
    global_scene_counts: collections.Counter[str] = collections.Counter()
    global_timed_counts: collections.Counter[bool] = collections.Counter()
    global_split_counts: collections.Counter[str] = collections.Counter()

    for category in sorted(buckets):
        pool = list(buckets[category])
        rng.shuffle(pool)
        for _ in range(allocation[category]):
            pool.sort(
                key=lambda task: (
                    global_scene_counts[task["scene"]],
                    global_timed_counts[task["timed"]],
                    global_split_counts[task["split"]],
                )
            )
            best_key = (
                global_scene_counts[pool[0]["scene"]],
                global_timed_counts[pool[0]["timed"]],
                global_split_counts[pool[0]["split"]],
            )
            tied = [
                task
                for task in pool
                if (
                    global_scene_counts[task["scene"]],
                    global_timed_counts[task["timed"]],
                    global_split_counts[task["split"]],
                )
                == best_key
            ]
            selected = rng.choice(tied)
            pool.remove(selected)
            chosen.append(selected)
            global_scene_counts[selected["scene"]] += 1
            global_timed_counts[selected["timed"]] += 1
            global_split_counts[selected["split"]] += 1
    rng.shuffle(chosen)
    return chosen


def verify_path(data_root: Path, relative: str) -> None:
    path = (data_root / relative).resolve()
    try:
        path.relative_to(data_root.resolve())
    except ValueError as exc:
        raise ValueError(f"Media path escapes data root: {relative}") from exc
    if not path.is_file() or path.stat().st_size == 0:
        raise FileNotFoundError(path)


def make_comparison_id(task_identifier: str, model_1: str, model_2: str) -> str:
    digest = hashlib.sha256(
        f"{task_identifier}\0{model_1}\0{model_2}".encode("utf-8")
    ).hexdigest()[:16]
    return f"cmp_{digest}"


def repository_path(path: Path) -> str:
    """Use a portable path relative to the working directory when possible."""
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def main() -> None:
    args = parser().parse_args()
    if min(args.remove, args.add, args.modify) < 0:
        raise ValueError("Task quotas must be non-negative")
    if args.ratings_per_comparison < 1:
        raise ValueError("--ratings-per-comparison must be positive")

    manifest_path = args.manifest.expanduser().resolve()
    manifest = read_json(manifest_path)
    if not isinstance(manifest, list) or not manifest:
        raise ValueError("Manifest must be a non-empty JSON list")

    model_rows: dict[str, dict[tuple[str, str, str], dict[str, Any]]] = collections.defaultdict(dict)
    case_rows: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in manifest:
        key = task_key(row)
        model = row["model"]
        if key in model_rows[model]:
            raise ValueError(f"Duplicate candidate for {model}: {key}")
        model_rows[model][key] = row
        previous = case_rows.get(key)
        if previous and (
            previous["source"] != row["source"]
            or previous["gt"] != row["gt"]
            or previous["instruction"] != row["instruction"]
            or float(previous["event"]) != float(row["event"])
        ):
            raise ValueError(f"Inconsistent task metadata across models: {key}")
        case_rows[key] = row

    models = sorted(model_rows)
    if args.main_model:
        main_models = sorted(set(args.main_model))
    else:
        main_models = [model for model in models if model != args.limited_model]
    if len(main_models) < 2:
        raise ValueError("At least two main models are required")
    missing_models = set(main_models) - set(models)
    if missing_models:
        raise ValueError(f"Models absent from manifest: {sorted(missing_models)}")
    limited_model = args.limited_model if args.limited_model in model_rows else None

    metadata_specs = list(args.metadata)
    data_root = args.data_root.expanduser().resolve() if args.data_root else None
    if data_root:
        metadata_specs = metadata_specs_from_root(data_root) + metadata_specs
    metadata = parse_metadata_specs(metadata_specs)

    common_main = set.intersection(*(set(model_rows[model]) for model in main_models))
    limited_keys = set(model_rows[limited_model]) if limited_model else set()
    population_counts = collections.Counter(
        edit_type(row["instruction"]) for row in case_rows.values()
    )

    tasks: dict[tuple[str, str, str], dict[str, Any]] = {}
    for key in sorted(common_main):
        base = case_rows[key]
        category = edit_type(base["instruction"])
        identifier = f"{key[1]}/{key[2]}"
        meta = metadata.get((key[0], identifier), {})
        tasks[key] = {
            "task_id": task_id(key),
            "split": key[0],
            "scene": key[1],
            "case": key[2],
            "edit_type": category,
            "interaction_category": meta.get("interaction_category", "unknown"),
            "timed": float(base["event"]) > 0,
            "event": float(base["event"]),
            "instruction_en": base["instruction"],
            "source": base["source"],
            "gt": base["gt"],
            "candidates": {
                model: model_rows[model][key]["candidate"] for model in main_models
            },
        }
        if limited_model and key in limited_keys:
            tasks[key]["candidates"][limited_model] = model_rows[limited_model][key]["candidate"]

    requested_quotas = {"Remove": args.remove, "Add": args.add, "Modify": args.modify}
    rng = random.Random(args.seed)
    if args.all_common:
        selected = list(tasks.values())
        sampling_mode = "all_common_main_model_tasks"
    else:
        selected = []
        sampling_mode = "stratified_sample"
        for category in EDIT_TYPES:
            eligible = [task for task in tasks.values() if task["edit_type"] == category]
            if category == args.limited_edit_type and limited_model:
                eligible = [task for task in eligible if limited_model in task["candidates"]]
            selected.extend(select_diverse(eligible, requested_quotas[category], rng))
    selected.sort(key=lambda task: (EDIT_TYPES.index(task["edit_type"]), task["task_id"]))
    selected_counts = collections.Counter(task["edit_type"] for task in selected)

    comparisons: list[dict[str, Any]] = []
    for task in selected:
        for model_1, model_2 in itertools.combinations(main_models, 2):
            comparisons.append(
                {
                    "comparison_id": make_comparison_id(task["task_id"], model_1, model_2),
                    "task_id": task["task_id"],
                    "model_1": model_1,
                    "model_2": model_2,
                    "target_ratings": args.ratings_per_comparison,
                }
            )
        if (
            limited_model
            and task["edit_type"] == args.limited_edit_type
            and limited_model in task["candidates"]
        ):
            for model in main_models:
                model_1, model_2 = sorted((limited_model, model))
                comparisons.append(
                    {
                        "comparison_id": make_comparison_id(
                            task["task_id"], model_1, model_2
                        ),
                        "task_id": task["task_id"],
                        "model_1": model_1,
                        "model_2": model_2,
                        "target_ratings": args.ratings_per_comparison,
                    }
                )
    comparison_ids = [row["comparison_id"] for row in comparisons]
    if len(comparison_ids) != len(set(comparison_ids)):
        raise AssertionError("Comparison ids are not unique")

    if args.verify_media:
        if not data_root:
            raise ValueError("--verify-media requires --data-root")
        paths = {
            path
            for task in selected
            for path in (task["source"], task["gt"], *task["candidates"].values())
        }
        for relative in sorted(paths):
            verify_path(data_root, relative)

    study = {
        "schema_version": 1,
        "study_type": "phycove_pairwise_human_preference",
        "created_at": now_iso(),
        "seed": args.seed,
        "source_manifest": repository_path(manifest_path),
        "source_manifest_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "main_models": main_models,
        "limited_model": limited_model,
        "limited_edit_type": args.limited_edit_type if limited_model else None,
        "model_display_names": {model: MODEL_NAMES.get(model, model) for model in models},
        "sampling_mode": sampling_mode,
        "task_quotas": {
            category: selected_counts[category] for category in EDIT_TYPES
        },
        "requested_task_quotas": None if args.all_common else requested_quotas,
        "population_case_counts": {
            category: population_counts[category] for category in EDIT_TYPES
        },
        "ratings_per_comparison": args.ratings_per_comparison,
        "tasks": selected,
        "comparisons": comparisons,
        "summary": {
            "tasks": len(selected),
            "tasks_by_edit_type": dict(selected_counts),
            "tasks_by_interaction": dict(
                collections.Counter(task["interaction_category"] for task in selected)
            ),
            "timed_tasks": sum(task["timed"] for task in selected),
            "comparisons": len(comparisons),
            "target_judgments": sum(row["target_ratings"] for row in comparisons),
        },
    }
    output = args.output.expanduser().resolve()
    atomic_json(output, study)
    print(json.dumps(study["summary"], ensure_ascii=False, indent=2))
    print(f"Wrote {output}")


if __name__ == "__main__":
    main()
