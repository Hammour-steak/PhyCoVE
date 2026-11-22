#!/usr/bin/env python3
"""Build the balanced 10-reviewer, 150-assignments-per-reviewer panel."""
from __future__ import annotations

import argparse
import collections
import hashlib
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from common import EDIT_TYPES, atomic_json, now_iso, read_json


EDIT_TARGETS = {"Remove": 24, "Add": 15, "Modify": 32}
INTERACTION_TARGETS = {
    "Remove": {
        "elastic_elastic": 1,
        "elastic_fluid": 1,
        "rigid_elastic": 8,
        "rigid_fluid": 4,
        "rigid_rigid": 10,
    },
    "Add": {
        "elastic_elastic": 2,
        "elastic_fluid": 0,
        "rigid_elastic": 8,
        "rigid_fluid": 1,
        "rigid_rigid": 4,
    },
    "Modify": {
        "elastic_elastic": 1,
        "elastic_fluid": 2,
        "rigid_elastic": 9,
        "rigid_fluid": 5,
        "rigid_rigid": 15,
    },
}
REAL_TARGETS = {"Remove": 2, "Add": 2, "Modify": 1}
TIMED_TARGETS = {"Remove": 2, "Add": 0, "Modify": 6}
EDIT_LOADS = {
    "Remove": [51, 51, 51, 51, 50, 50, 50, 50, 50, 50],
    "Add": [31, 31, 31, 31, 32, 32, 32, 32, 32, 31],
    "Modify": [68, 68, 68, 68, 68, 68, 68, 68, 68, 69],
}
REAL_LOADS = [11, 11, 11, 11, 11, 10, 10, 10, 10, 10]
TIMED_LOADS = [17, 17, 17, 17, 17, 17, 17, 17, 16, 16]


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--source-study", type=Path, required=True)
    result.add_argument("--output-dir", type=Path, required=True)
    result.add_argument("--seed", type=int, default=20261117)
    return result


def stable_number(seed: int, value: str) -> float:
    digest = hashlib.sha256(f"{seed}|{value}".encode()).digest()
    return int.from_bytes(digest[:8], "big") / 2**64


def repository_path(path: Path) -> str:
    try:
        return path.relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return str(path)


def solve_binary(
    variable_count: int,
    rows: list[tuple[dict[int, float], float, float]],
    objective: np.ndarray,
) -> np.ndarray:
    matrix = lil_matrix((len(rows), variable_count))
    lower = np.empty(len(rows))
    upper = np.empty(len(rows))
    for row_index, (coefficients, low, high) in enumerate(rows):
        for column, value in coefficients.items():
            matrix[row_index, column] = value
        lower[row_index] = low
        upper[row_index] = high
    result = milp(
        objective,
        integrality=np.ones(variable_count),
        bounds=Bounds(np.zeros(variable_count), np.ones(variable_count)),
        constraints=LinearConstraint(matrix.tocsr(), lower, upper),
        options={"time_limit": 30},
    )
    if not result.success:
        raise RuntimeError(result.message)
    return result.x


def exact_row(indices: Iterable[int], target: int) -> tuple[dict[int, float], int, int]:
    return ({index: 1 for index in indices}, target, target)


def select_tasks(tasks: list[dict[str, Any]], seed: int) -> list[dict[str, Any]]:
    rows: list[tuple[dict[int, float], float, float]] = []
    for edit_type, target in EDIT_TARGETS.items():
        rows.append(
            exact_row(
                (i for i, task in enumerate(tasks) if task["edit_type"] == edit_type),
                target,
            )
        )
    for edit_type, targets in INTERACTION_TARGETS.items():
        for interaction, target in targets.items():
            rows.append(
                exact_row(
                    (
                        i
                        for i, task in enumerate(tasks)
                        if task["edit_type"] == edit_type
                        and task["interaction_category"] == interaction
                    ),
                    target,
                )
            )
    for edit_type, target in REAL_TARGETS.items():
        rows.append(
            exact_row(
                (
                    i
                    for i, task in enumerate(tasks)
                    if task["edit_type"] == edit_type and task["split"] == "real"
                ),
                target,
            )
        )
    for edit_type, target in TIMED_TARGETS.items():
        rows.append(
            exact_row(
                (
                    i
                    for i, task in enumerate(tasks)
                    if task["edit_type"] == edit_type and task["timed"]
                ),
                target,
            )
        )
    scene_groups: dict[tuple[str, str, str], list[int]] = collections.defaultdict(list)
    for index, task in enumerate(tasks):
        scene_groups[(task["edit_type"], task["split"], task["scene"])].append(index)
    for indices in scene_groups.values():
        rows.append(({index: 1 for index in indices}, 0, 1))
    objective = np.array([stable_number(seed, task["task_id"]) for task in tasks])
    selected = solve_binary(len(tasks), rows, objective)
    result = [task for task, value in zip(tasks, selected) if value > 0.5]
    result.sort(key=lambda task: (EDIT_TYPES.index(task["edit_type"]), task["task_id"]))
    return result


def hamiltonian_cycles(models: list[str]) -> list[list[tuple[str, str]]]:
    if len(models) != 7:
        raise ValueError("The panel design requires exactly seven main models")
    orders = [
        [6, 0, 5, 1, 4, 2, 3, 6],
        [6, 1, 0, 2, 5, 3, 4, 6],
        [6, 2, 1, 3, 0, 4, 5, 6],
    ]
    return [
        [(models[first], models[second]) for first, second in zip(order, order[1:])]
        for order in orders
    ]


def select_comparisons(
    source: dict[str, Any], selected_tasks: list[dict[str, Any]], seed: int
) -> list[dict[str, Any]]:
    models = list(source["main_models"])
    cycles = hamiltonian_cycles(models)
    source_rows = {
        (row["task_id"], frozenset((row["model_1"], row["model_2"]))): row
        for row in source["comparisons"]
    }
    result: list[dict[str, Any]] = []
    by_edit: dict[str, list[dict[str, Any]]] = {}
    for edit_type in EDIT_TYPES:
        tasks = [task for task in selected_tasks if task["edit_type"] == edit_type]
        tasks.sort(key=lambda task: stable_number(seed, "cycle|" + task["task_id"]))
        by_edit[edit_type] = tasks
        for task_index, task in enumerate(tasks):
            for model_1, model_2 in cycles[task_index % 3]:
                row = source_rows[(task["task_id"], frozenset((model_1, model_2)))]
                result.append({**row, "target_ratings": 3})
    extra_task = by_edit["Modify"][-1]
    for position in (0, 2, 4):
        model_1, model_2 = cycles[2][position]
        row = source_rows[(extra_task["task_id"], frozenset((model_1, model_2)))]
        result.append({**row, "target_ratings": 3})
    return result


def allocate_reviewers(
    comparisons: list[dict[str, Any]],
    selected_tasks: list[dict[str, Any]],
    seed: int,
) -> list[dict[str, Any]]:
    reviewer_count = 10
    task_by_id = {task["task_id"]: task for task in selected_tasks}
    ordered = sorted(
        comparisons,
        key=lambda row: stable_number(seed, "assignment|" + row["comparison_id"]),
    )
    rows: list[tuple[dict[int, float], float, float]] = []
    for comparison_index in range(len(ordered)):
        rows.append(
            exact_row(
                (
                    comparison_index * reviewer_count + reviewer
                    for reviewer in range(reviewer_count)
                ),
                3,
            )
        )
    for reviewer in range(reviewer_count):
        rows.append(
            exact_row(
                (
                    comparison_index * reviewer_count + reviewer
                    for comparison_index in range(len(ordered))
                ),
                150,
            )
        )
        for edit_type, targets in EDIT_LOADS.items():
            rows.append(
                exact_row(
                    (
                        comparison_index * reviewer_count + reviewer
                        for comparison_index, comparison in enumerate(ordered)
                        if task_by_id[comparison["task_id"]]["edit_type"] == edit_type
                    ),
                    targets[reviewer],
                )
            )
        rows.append(
            exact_row(
                (
                    comparison_index * reviewer_count + reviewer
                    for comparison_index, comparison in enumerate(ordered)
                    if task_by_id[comparison["task_id"]]["split"] == "real"
                ),
                REAL_LOADS[reviewer],
            )
        )
        rows.append(
            exact_row(
                (
                    comparison_index * reviewer_count + reviewer
                    for comparison_index, comparison in enumerate(ordered)
                    if task_by_id[comparison["task_id"]]["timed"]
                ),
                TIMED_LOADS[reviewer],
            )
        )
    variable_count = len(ordered) * reviewer_count
    objective = np.array(
        [
            stable_number(seed, f"reviewer|{comparison['comparison_id']}|{reviewer}")
            for comparison in ordered
            for reviewer in range(reviewer_count)
        ]
    )
    allocation = solve_binary(variable_count, rows, objective)
    assignments: list[dict[str, Any]] = []
    for comparison_index, comparison in enumerate(ordered):
        reviewers = [
            reviewer
            for reviewer in range(reviewer_count)
            if allocation[comparison_index * reviewer_count + reviewer] > 0.5
        ]
        if len(reviewers) != 3:
            raise AssertionError("Every comparison must have three reviewers")
        for slot, reviewer in enumerate(reviewers):
            normal_order = (comparison_index + slot) % 2 == 0
            model_a, model_b = (
                (comparison["model_1"], comparison["model_2"])
                if normal_order
                else (comparison["model_2"], comparison["model_1"])
            )
            assignments.append(
                {
                    "assignment_id": f"asg_{comparison_index + 1:04d}_{slot + 1}",
                    "rater_code": f"R{reviewer + 1:02d}",
                    "comparison_id": comparison["comparison_id"],
                    "model_a": model_a,
                    "model_b": model_b,
                }
            )
    assignments.sort(key=lambda row: (row["rater_code"], row["assignment_id"]))
    return assignments


def validate(
    selected_tasks: list[dict[str, Any]],
    comparisons: list[dict[str, Any]],
    assignments: list[dict[str, Any]],
) -> None:
    if collections.Counter(task["edit_type"] for task in selected_tasks) != collections.Counter(EDIT_TARGETS):
        raise AssertionError("Task quotas are unbalanced")
    if len(selected_tasks) != 71 or len(comparisons) != 500 or len(assignments) != 1500:
        raise AssertionError("Panel dimensions are incorrect")
    pair_counts = collections.Counter(
        tuple(sorted((row["model_1"], row["model_2"]))) for row in comparisons
    )
    if len(pair_counts) != 21 or set(pair_counts.values()) != {23, 24}:
        raise AssertionError("Model-pair coverage is unbalanced")
    reviewer_counts = collections.Counter(row["rater_code"] for row in assignments)
    if set(reviewer_counts.values()) != {150} or len(reviewer_counts) != 10:
        raise AssertionError("Reviewer loads are unbalanced")
    assignment_counts = collections.Counter(row["comparison_id"] for row in assignments)
    if set(assignment_counts.values()) != {3}:
        raise AssertionError("Every comparison must have three assignments")


def main() -> None:
    args = parser().parse_args()
    source_path = args.source_study.expanduser().resolve()
    output_dir = args.output_dir.expanduser().resolve()
    source_raw = source_path.read_bytes()
    source = read_json(source_path)
    selected_tasks = select_tasks(source["tasks"], args.seed)
    main_models = list(source["main_models"])
    for task in selected_tasks:
        task["candidates"] = {
            model: task["candidates"][model] for model in main_models
        }
    comparisons = select_comparisons(source, selected_tasks, args.seed)
    assignments = allocate_reviewers(comparisons, selected_tasks, args.seed)
    validate(selected_tasks, comparisons, assignments)

    selected_counts = collections.Counter(task["edit_type"] for task in selected_tasks)
    study = {
        "schema_version": 1,
        "study_type": "phycove_pairwise_human_preference",
        "created_at": now_iso(),
        "seed": args.seed,
        "source_study": repository_path(source_path),
        "source_study_sha256": hashlib.sha256(source_raw).hexdigest(),
        "source_manifest": source.get("source_manifest"),
        "source_manifest_sha256": source.get("source_manifest_sha256"),
        "main_models": main_models,
        "limited_model": None,
        "limited_edit_type": None,
        "model_display_names": {
            model: source["model_display_names"].get(model, model)
            for model in main_models
        },
        "sampling_mode": "balanced_incomplete_block_panel_10x150",
        "task_quotas": dict(selected_counts),
        "requested_task_quotas": EDIT_TARGETS,
        "population_case_counts": source["population_case_counts"],
        "ratings_per_comparison": 3,
        "tasks": selected_tasks,
        "comparisons": comparisons,
        "summary": {
            "tasks": len(selected_tasks),
            "tasks_by_edit_type": dict(selected_counts),
            "tasks_by_interaction": dict(
                collections.Counter(
                    task["interaction_category"] for task in selected_tasks
                )
            ),
            "real_tasks": sum(task["split"] == "real" for task in selected_tasks),
            "timed_tasks": sum(task["timed"] for task in selected_tasks),
            "comparisons": len(comparisons),
            "target_judgments": len(assignments),
            "raters": 10,
            "assignments_per_rater": 150,
        },
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    study_path = output_dir / "study.json"
    atomic_json(study_path, study)
    study_digest = hashlib.sha256(study_path.read_bytes()).hexdigest()
    plan = {
        "schema_version": 1,
        "plan_type": "fixed_human_annotation_assignments",
        "created_at": now_iso(),
        "study_sha256": study_digest,
        "seed": args.seed,
        "rater_codes": [f"R{index:02d}" for index in range(1, 11)],
        "assignments": assignments,
        "summary": study["summary"],
    }
    plan_path = output_dir / "assignment_plan.json"
    atomic_json(plan_path, plan)
    print(f"Wrote {study_path}")
    print(f"Wrote {plan_path}")
    print(study["summary"])


if __name__ == "__main__":
    main()
