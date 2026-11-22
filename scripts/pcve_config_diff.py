#!/usr/bin/env python3
"""Read-only audit of a report's before/after snapshots against exact declarations."""

import argparse
import json
import sys
from pathlib import Path


def reject_constant(value):
    raise ValueError(f"Non-finite JSON value: {value}")


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def same_value(before, after):
    # bool is an int subclass in Python, but true must not equal the number 1.
    if isinstance(before, bool) or isinstance(after, bool):
        return type(before) is type(after) and before == after
    if isinstance(before, list) and isinstance(after, list):
        return len(before) == len(after) and all(
            same_value(a, b) for a, b in zip(before, after)
        )
    if isinstance(before, dict) and isinstance(after, dict):
        return before.keys() == after.keys() and all(
            same_value(before[key], after[key]) for key in before
        )
    return before == after


def validate_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str) or not key or "." in key:
                raise ValueError("Snapshot field names must be nonempty strings without dots")
            validate_keys(child)
    elif isinstance(value, list):
        for child in value:
            validate_keys(child)


def config_changes(before, after, prefix=""):
    changes = []
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(before.keys() | after.keys()):
            field = f"{prefix}.{key}" if prefix else key
            if key not in before or key not in after:
                changes.append({
                    "field": field,
                    "before_present": key in before,
                    "after_present": key in after,
                    "before": before.get(key),
                    "after": after.get(key),
                })
            else:
                changes.extend(config_changes(before[key], after[key], field))
    elif not same_value(before, after):
        changes.append({
            "field": prefix, "before_present": True, "after_present": True,
            "before": before, "after": after,
        })
    return changes


def audit_report(report, allowed):
    if not isinstance(report, dict):
        raise ValueError("Report must be a JSON object")
    before, after = report.get("before"), report.get("after")
    if not isinstance(before, dict) or not before or not isinstance(after, dict) or not after:
        raise ValueError("Report needs nonempty before and after configuration objects")
    validate_keys(before)
    validate_keys(after)
    if len(allowed) != len(set(allowed)) or any(not field for field in allowed):
        raise ValueError("Declared fields must be unique and nonempty")
    changes = config_changes(before, after)
    actual = {change["field"] for change in changes}
    expected = set(allowed)
    unexpected = sorted(actual - expected)
    unchanged = sorted(expected - actual)
    return {
        "config_diff_status": "matched_declared_changes" if not unexpected and not unchanged else "mismatch",
        "changed_fields": sorted(actual),
        "unexpected_changes": unexpected,
        "declared_but_unchanged": unchanged,
        "changes": changes,
        "scope": "Recorded configuration fields only. Does not verify Blender geometry, trajectories, cache isolation, video quality or physical correctness.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report", type=Path, help="JSON report containing before and after snapshots")
    parser.add_argument("--allow", action="append", default=[], metavar="SECTION.FIELD",
                        help="Exact field expected to change; repeat for a declared group, no wildcards")
    args = parser.parse_args()
    try:
        report = json.loads(args.report.read_text(encoding="utf-8"),
                            parse_constant=reject_constant, object_pairs_hook=unique_object)
        result = audit_report(report, args.allow)
    except (OSError, ValueError) as exc:
        print(f"Configuration audit error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, ensure_ascii=False, allow_nan=False))
    return 0 if result["config_diff_status"] == "matched_declared_changes" else 1


if __name__ == "__main__":
    raise SystemExit(main())
