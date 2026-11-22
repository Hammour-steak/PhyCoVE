#!/usr/bin/env python3
"""Aggregate pairwise human judgments into Rao-Kupper model rankings."""
from __future__ import annotations

import argparse
import collections
import hashlib
import math
import random
import statistics
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from scipy.optimize import minimize

from common import EDIT_TYPES, atomic_json, now_iso, read_json, read_jsonl


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--study", type=Path, required=True)
    result.add_argument("--annotations", type=Path)
    result.add_argument("--output-dir", type=Path)
    result.add_argument("--bootstrap", type=int, default=1000)
    result.add_argument("--seed", type=int, default=4090)
    result.add_argument("--allow-incomplete", action="store_true")
    return result


def canonical_label(vote: dict[str, Any]) -> str:
    first, second = sorted((vote["model_a"], vote["model_b"]))
    winner = vote["winner_model"]
    if winner is None:
        return "tie"
    return "first" if winner == first else "second"


def load_votes(
    study_path: Path, annotations_path: Path
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], dict[str, int]]:
    study = read_json(study_path)
    digest = hashlib.sha256(study_path.read_bytes()).hexdigest()
    tasks = {task["task_id"]: task for task in study["tasks"]}
    comparisons = {
        row["comparison_id"]: row for row in study["comparisons"]
    }
    votes: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    counts: collections.Counter[str] = collections.Counter()

    for row in read_jsonl(annotations_path):
        if row.get("study_sha256") != digest:
            raise ValueError(
                f"Annotation {row.get('annotation_id')} belongs to another study"
            )
        comparison_id = row.get("comparison_id")
        rater_id = row.get("rater_id")
        if comparison_id not in comparisons:
            raise ValueError(f"Unknown comparison id: {comparison_id}")
        key = rater_id, comparison_id
        if key in seen:
            raise ValueError(f"Duplicate rater/comparison annotation: {key}")
        seen.add(key)
        comparison = comparisons[comparison_id]
        expected_models = {comparison["model_1"], comparison["model_2"]}
        if {row.get("model_a"), row.get("model_b")} != expected_models:
            raise ValueError(f"Model mismatch in annotation {row.get('annotation_id')}")
        if row.get("task_id") != comparison["task_id"]:
            raise ValueError(f"Task mismatch in annotation {row.get('annotation_id')}")
        if row.get("record_type") == "technical_issue":
            issues.append(row)
            continue
        if row.get("record_type") != "judgment":
            raise ValueError(f"Unknown annotation type: {row.get('record_type')}")
        choice = row.get("choice")
        expected_winner = (
            row["model_a"] if choice == "a" else row["model_b"] if choice == "b" else None
        )
        if choice not in {"a", "tie", "b"} or row.get("winner_model") != expected_winner:
            raise ValueError(f"Invalid winner in annotation {row.get('annotation_id')}")
        enriched = dict(row)
        task = tasks[comparison["task_id"]]
        enriched["edit_type"] = task["edit_type"]
        enriched["interaction_category"] = task.get("interaction_category", "unknown")
        votes.append(enriched)
        counts[comparison_id] += 1
    return study, votes, issues, dict(counts)


def connected(models: list[str], votes: list[dict[str, Any]]) -> bool:
    if not models:
        return False
    graph: dict[str, set[str]] = {model: set() for model in models}
    allowed = set(models)
    for vote in votes:
        a, b = vote["model_a"], vote["model_b"]
        if a in allowed and b in allowed:
            graph[a].add(b)
            graph[b].add(a)
    reached = {models[0]}
    frontier = [models[0]]
    while frontier:
        current = frontier.pop()
        for neighbor in graph[current] - reached:
            reached.add(neighbor)
            frontier.append(neighbor)
    return reached == allowed


def fit_rao_kupper(
    models: list[str],
    votes: list[dict[str, Any]],
    vote_weight: Callable[[dict[str, Any]], float],
    task_multipliers: Optional[collections.Counter[str]] = None,
) -> dict[str, Any]:
    """Maximum-likelihood Rao-Kupper fit, including explicit ties."""
    models = sorted(models)
    allowed = set(models)
    filtered = [
        vote
        for vote in votes
        if vote["model_a"] in allowed
        and vote["model_b"] in allowed
        and (not task_multipliers or task_multipliers[vote["task_id"]] > 0)
    ]
    if len(models) < 2 or not connected(models, filtered):
        raise ValueError("The observed comparison graph is not connected")
    index = {model: position for position, model in enumerate(models)}
    aggregated: dict[tuple[int, int], np.ndarray] = collections.defaultdict(
        lambda: np.zeros(3, dtype=float)
    )
    for vote in filtered:
        first, second = sorted((vote["model_a"], vote["model_b"]))
        multiplier = task_multipliers[vote["task_id"]] if task_multipliers else 1
        weight = float(vote_weight(vote)) * multiplier
        if weight <= 0:
            continue
        outcome = canonical_label(vote)
        bucket = 0 if outcome == "first" else 1 if outcome == "second" else 2
        aggregated[(index[first], index[second])][bucket] += weight

    def objective(parameters: np.ndarray) -> float:
        merits = np.concatenate((parameters[:-1], np.zeros(1)))
        log_tolerance = float(np.clip(parameters[-1], -7.0, 2.0))
        tolerance = math.exp(log_tolerance)
        loss = 0.0
        for (i, j), outcomes in aggregated.items():
            delta = float(merits[i] - merits[j])
            p_i = 1.0 / (1.0 + math.exp(np.clip(tolerance - delta, -60, 60)))
            p_j = 1.0 / (1.0 + math.exp(np.clip(tolerance + delta, -60, 60)))
            p_tie = max(1e-15, 1.0 - p_i - p_j)
            probabilities = np.maximum(np.array([p_i, p_j, p_tie]), 1e-15)
            loss -= float(np.dot(outcomes, np.log(probabilities)))
        return loss

    initial = np.zeros(len(models), dtype=float)
    initial[-1] = math.log(0.25)
    bounds = [(-12.0, 12.0)] * (len(models) - 1) + [(-7.0, 2.0)]
    result = minimize(objective, initial, method="L-BFGS-B", bounds=bounds)
    if not result.success:
        raise RuntimeError(f"Rao-Kupper optimization failed: {result.message}")
    merits = np.concatenate((result.x[:-1], np.zeros(1)))
    merits -= merits.mean()
    normalized = 100.0 * np.exp(merits - merits.max())
    order = sorted(range(len(models)), key=lambda position: (-merits[position], models[position]))
    ranks = {models[position]: rank + 1 for rank, position in enumerate(order)}

    wins = collections.Counter()
    ties = collections.Counter()
    appearances = collections.Counter()
    pair_counts: dict[tuple[str, str], collections.Counter[str]] = collections.defaultdict(
        collections.Counter
    )
    for vote in filtered:
        multiplier = task_multipliers[vote["task_id"]] if task_multipliers else 1
        weight = float(vote_weight(vote)) * multiplier
        a, b = vote["model_a"], vote["model_b"]
        first, second = sorted((a, b))
        appearances[a] += weight
        appearances[b] += weight
        if vote["winner_model"] is None:
            ties[a] += weight
            ties[b] += weight
            pair_counts[(first, second)]["tie"] += weight
        else:
            wins[vote["winner_model"]] += weight
            pair_counts[(first, second)][vote["winner_model"]] += weight

    rows = []
    for position, model in enumerate(models):
        preference_fraction = (
            wins[model] + 0.5 * ties[model]
        ) / appearances[model]
        preference = 100.0 * preference_fraction
        net_win_rate = 2.0 * preference_fraction - 1.0
        rows.append(
            {
                "model": model,
                "rank": ranks[model],
                # Rao-Kupper is the Bradley-Terry paired-comparison model with
                # an explicit tie region.
                "bradley_terry_with_ties_score": float(normalized[position]),
                "rao_kupper_score": float(normalized[position]),
                "log_merit": float(merits[position]),
                "human_preference_win_rate_percent": float(preference),
                "human_preference_percent": float(preference),
                "net_win_rate": float(net_win_rate),
                "net_win_rate_percent": float(100.0 * net_win_rate),
                "weighted_appearances": float(appearances[model]),
            }
        )
    rows.sort(key=lambda row: row["rank"])

    matrix = {}
    for model_i in models:
        matrix[model_i] = {}
        for model_j in models:
            if model_i == model_j:
                matrix[model_i][model_j] = None
                continue
            first, second = sorted((model_i, model_j))
            counts = pair_counts[(first, second)]
            total = counts[first] + counts[second] + counts["tie"]
            matrix[model_i][model_j] = (
                100.0 * (counts[model_i] + 0.5 * counts["tie"]) / total
                if total
                else None
            )
    return {
        "models": rows,
        "pairwise_preference_percent": matrix,
        "tie_tolerance": float(math.exp(result.x[-1])),
        "negative_log_likelihood": float(result.fun),
        "optimizer_iterations": int(result.nit),
    }


def add_bootstrap_intervals(
    ranking: dict[str, Any],
    models: list[str],
    votes: list[dict[str, Any]],
    vote_weight: Callable[[dict[str, Any]], float],
    repetitions: int,
    seed: int,
) -> None:
    if repetitions <= 0:
        return
    task_ids = sorted({vote["task_id"] for vote in votes})
    if len(task_ids) < 2:
        return
    rng = random.Random(seed)
    scores: dict[str, list[float]] = collections.defaultdict(list)
    hpwr_values: dict[str, list[float]] = collections.defaultdict(list)
    ranks: dict[str, list[int]] = collections.defaultdict(list)
    completed = 0
    for _ in range(repetitions):
        sampled = collections.Counter(rng.choice(task_ids) for _ in task_ids)
        try:
            result = fit_rao_kupper(models, votes, vote_weight, sampled)
        except (ValueError, RuntimeError):
            continue
        completed += 1
        for row in result["models"]:
            scores[row["model"]].append(row["rao_kupper_score"])
            hpwr_values[row["model"]].append(
                row["human_preference_win_rate_percent"]
            )
            ranks[row["model"]].append(row["rank"])
    if completed < max(1, math.ceil(repetitions / 2)):
        raise RuntimeError(
            f"Only {completed}/{repetitions} bootstrap fits converged"
        )
    for row in ranking["models"]:
        model = row["model"]
        row["score_ci95"] = [
            float(np.percentile(scores[model], 2.5)),
            float(np.percentile(scores[model], 97.5)),
        ]
        row["hpwr_ci95"] = [
            float(np.percentile(hpwr_values[model], 2.5)),
            float(np.percentile(hpwr_values[model], 97.5)),
        ]
        row["net_win_rate_ci95"] = [
            float(2.0 * np.percentile(hpwr_values[model], 2.5) / 100.0 - 1.0),
            float(2.0 * np.percentile(hpwr_values[model], 97.5) / 100.0 - 1.0),
        ]
        row["rank_ci95"] = [
            int(math.floor(np.percentile(ranks[model], 2.5))),
            int(math.ceil(np.percentile(ranks[model], 97.5))),
        ]
    ranking["bootstrap_repetitions"] = completed


def agreement_metrics(votes: list[dict[str, Any]]) -> dict[str, Any]:
    grouped: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for vote in votes:
        grouped[vote["comparison_id"]].append(vote)
    categories = ("first", "tie", "second")
    category_totals = collections.Counter(canonical_label(vote) for vote in votes)
    agreeing_pairs = 0
    total_pairs = 0
    majority_items = 0
    comparable_items = 0
    for rows in grouped.values():
        if len(rows) < 2:
            continue
        comparable_items += 1
        counts = collections.Counter(canonical_label(row) for row in rows)
        agreeing_pairs += sum(count * (count - 1) // 2 for count in counts.values())
        total_pairs += len(rows) * (len(rows) - 1) // 2
        majority_items += int(max(counts.values()) > len(rows) / 2)
    observed = agreeing_pairs / total_pairs if total_pairs else None
    total_votes = len(votes)
    expected = (
        sum((category_totals[category] / total_votes) ** 2 for category in categories)
        if total_votes
        else None
    )
    kappa = (
        (observed - expected) / (1 - expected)
        if observed is not None and expected is not None and expected < 1
        else None
    )
    non_ties = [vote for vote in votes if vote["choice"] != "tie"]
    left_choices = sum(vote["choice"] == "a" for vote in non_ties)
    elapsed = [
        float(vote["elapsed_seconds"])
        for vote in votes
        if isinstance(vote.get("elapsed_seconds"), (int, float))
    ]
    rater_counts = collections.Counter(vote["rater_id"] for vote in votes)
    return {
        "judgments": len(votes),
        "raters": len(rater_counts),
        "judgments_per_rater": dict(sorted(rater_counts.items())),
        "tie_rate": category_totals["tie"] / total_votes if total_votes else None,
        "left_choice_rate_excluding_ties": left_choices / len(non_ties) if non_ties else None,
        "pairwise_observed_agreement": observed,
        "chance_expected_agreement": expected,
        "fleiss_kappa": kappa,
        "items_with_majority_rate": (
            majority_items / comparable_items if comparable_items else None
        ),
        "median_elapsed_seconds": statistics.median(elapsed) if elapsed else None,
    }


def markdown_report(summary: dict[str, Any], display_names: dict[str, str]) -> str:
    lines = [
        "# PhyCoVE Human Preference Results",
        "",
        f"Generated: {summary['created_at']}",
        "",
    ]
    lines.extend(
        [
            "## Annotation coverage",
            "",
            f"- Valid judgments: {summary['coverage']['valid_judgments']}",
            f"- Technical issues: {summary['coverage']['technical_issues']}",
            f"- Completed comparisons: {summary['coverage']['complete_comparisons']} / {summary['coverage']['comparisons']}",
            "",
        ]
    )
    for name, ranking in summary["rankings"].items():
        lines.extend(
            [
                f"## {name}",
                "",
                "| Rank | Model | HPWR (%) ↑ | NWR [-1, 1] ↑ | BTT score ↑ | HPWR 95% CI |",
                "|---:|---|---:|---:|---:|---:|",
            ]
        )
        for row in ranking["models"]:
            ci = row.get("hpwr_ci95")
            ci_text = f"[{ci[0]:.1f}, {ci[1]:.1f}]" if ci else "—"
            lines.append(
                f"| {row['rank']} | {display_names.get(row['model'], row['model'])} "
                f"| {row['human_preference_win_rate_percent']:.1f} "
                f"| {row['net_win_rate']:+.3f} "
                f"| {row['bradley_terry_with_ties_score']:.1f} | {ci_text} |"
            )
        lines.append("")
    lines.extend(
        [
            "HPWR counts a win as 1, a tie as 0.5, and a loss as 0. "
            "NWR = 2 × HPWR / 100 − 1. BTT score is the normalized "
            "Rao–Kupper (Bradley–Terry-with-ties) strength with the subset leader set to 100.",
            "",
        ]
    )
    quality = summary["quality_control"]
    lines.extend(
        [
            "## Quality control",
            "",
            f"- Raters: {quality['raters']}",
            f"- Tie rate: {100 * quality['tie_rate']:.1f}%" if quality["tie_rate"] is not None else "- Tie rate: —",
            (
                f"- Fleiss’ κ: {quality['fleiss_kappa']:.3f}"
                if quality["fleiss_kappa"] is not None
                else "- Fleiss’ κ: —"
            ),
            (
                f"- Left-choice rate excluding ties: {100 * quality['left_choice_rate_excluding_ties']:.1f}%"
                if quality["left_choice_rate_excluding_ties"] is not None
                else "- Left-choice rate excluding ties: —"
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    args = parser().parse_args()
    study_path = args.study.expanduser().resolve()
    annotations_path = (
        args.annotations.expanduser().resolve()
        if args.annotations
        else study_path.with_name("annotations.jsonl")
    )
    output_dir = (
        args.output_dir.expanduser().resolve()
        if args.output_dir
        else study_path.parent / "results"
    )
    study, votes, issues, counts = load_votes(study_path, annotations_path)
    comparisons = {row["comparison_id"]: row for row in study["comparisons"]}
    incomplete = [
        identifier
        for identifier, row in comparisons.items()
        if counts.get(identifier, 0) < row["target_ratings"]
    ]
    if incomplete and not args.allow_incomplete:
        raise RuntimeError(
            f"Study is incomplete: {len(incomplete)} comparisons still need judgments; "
            "use --allow-incomplete only for interim analysis"
        )
    if not votes:
        raise RuntimeError("No valid human judgments found")
    data_statuses = {vote.get("data_status", "human") for vote in votes}
    if data_statuses != {"human"}:
        raise RuntimeError(
            "Only collected human judgments are accepted; "
            f"found data statuses: {sorted(data_statuses)}"
        )
    data_status = "human"

    selected_counts = collections.Counter(task["edit_type"] for task in study["tasks"])
    population_counts = study["population_case_counts"]
    population_total = sum(population_counts.values())
    selected_total = sum(selected_counts.values())
    type_weights = {
        category: (population_counts[category] / population_total)
        / (selected_counts[category] / selected_total)
        for category in EDIT_TYPES
        if selected_counts[category]
    }
    main_models = study["main_models"]
    limited_model = study.get("limited_model")

    rankings: dict[str, dict[str, Any]] = {}
    overall_votes = [
        vote
        for vote in votes
        if vote["model_a"] in main_models and vote["model_b"] in main_models
    ]
    overall_weight = lambda vote: type_weights[vote["edit_type"]]
    rankings["Overall"] = fit_rao_kupper(main_models, overall_votes, overall_weight)
    add_bootstrap_intervals(
        rankings["Overall"], main_models, overall_votes, overall_weight,
        args.bootstrap, args.seed,
    )

    for offset, category in enumerate(EDIT_TYPES, 1):
        subset_votes = [vote for vote in votes if vote["edit_type"] == category]
        subset_models = list(main_models)
        if category == study.get("limited_edit_type") and limited_model:
            subset_models.append(limited_model)
        subset_models = sorted(set(subset_models))
        rankings[category] = fit_rao_kupper(subset_models, subset_votes, lambda _: 1.0)
        add_bootstrap_intervals(
            rankings[category], subset_models, subset_votes, lambda _: 1.0,
            args.bootstrap, args.seed + offset,
        )

    complete_comparisons = sum(
        counts.get(identifier, 0) >= row["target_ratings"]
        for identifier, row in comparisons.items()
    )
    summary = {
        "schema_version": 1,
        "data_status": data_status,
        "created_at": now_iso(),
        "study_sha256": hashlib.sha256(study_path.read_bytes()).hexdigest(),
        "aggregation": (
            "Individual A/tie/B judgments are fit with the Rao-Kupper paired-comparison "
            "model. Overall results are post-stratified to full-benchmark edit-type "
            "frequencies. Confidence intervals use task-cluster bootstrap."
        ),
        "coverage": {
            "comparisons": len(comparisons),
            "complete_comparisons": complete_comparisons,
            "incomplete_comparisons": len(incomplete),
            "valid_judgments": len(votes),
            "technical_issues": len(issues),
        },
        "poststratification_weights": type_weights,
        "rankings": rankings,
        "quality_control": agreement_metrics(votes),
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    atomic_json(output_dir / "human_preference_results.json", summary)
    report = markdown_report(summary, study.get("model_display_names", {}))
    (output_dir / "human_preference_results.md").write_text(
        report + "\n", encoding="utf-8"
    )
    print(
        f"Aggregated {len(votes)} judgments from "
        f"{summary['quality_control']['raters']} raters"
    )
    for name, ranking in rankings.items():
        order = ", ".join(row["model"] for row in ranking["models"])
        print(f"{name}: {order}")
    print(f"Wrote {output_dir}")


if __name__ == "__main__":
    main()

