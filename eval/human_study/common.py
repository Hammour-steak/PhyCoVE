"""Shared helpers for the PhyCoVE human-preference study."""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Iterable


EDIT_TYPES = ("Remove", "Add", "Modify")
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


def now_iso() -> str:
    return dt.datetime.now().astimezone().isoformat(timespec="seconds")


def edit_type(instruction: str) -> str:
    """Map a quantitative PhyCoVE instruction to its headline edit subset."""
    body = re.sub(
        r"^From frame \d+ onwards,\s*", "", instruction.strip(), flags=re.I
    ).lower()
    if body.startswith(("remove ", "simultaneously remove ", "drain ")):
        return "Remove"
    if body.startswith(("add ", "place ")):
        return "Add"
    if body.startswith(("increase ", "reduce ", "change ", "set ", "leave ")):
        return "Modify"
    raise ValueError(f"Unclassified edit instruction: {instruction}")


def task_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return row["split"], row["scene"], row["case"]


def task_id(key: tuple[str, str, str]) -> str:
    return "__".join(key)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not path.exists():
        return rows
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSONL at {path}:{line_number}: {exc}") from exc
        if not isinstance(value, dict):
            raise ValueError(f"Expected an object at {path}:{line_number}")
        rows.append(value)
    return rows


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
        temporary = Path(handle.name)
    os.replace(temporary, path)


def parse_metadata_specs(specs: Iterable[str]) -> dict[tuple[str, str], dict[str, Any]]:
    """Read repeated ``SPLIT=metadata.jsonl`` arguments."""
    metadata: dict[tuple[str, str], dict[str, Any]] = {}
    for spec in specs:
        if "=" not in spec:
            raise ValueError(f"Metadata must use SPLIT=PATH syntax: {spec}")
        split, raw_path = spec.split("=", 1)
        split = split.strip()
        if split not in {"sim", "real"}:
            raise ValueError(f"Unsupported metadata split: {split}")
        path = Path(raw_path).expanduser().resolve()
        for row in read_jsonl(path):
            identifier = row.get("id")
            if not isinstance(identifier, str):
                raise ValueError(f"Metadata row without string id in {path}")
            key = split, identifier
            if key in metadata:
                raise ValueError(f"Duplicate metadata id: {key}")
            metadata[key] = row
    return metadata


def metadata_specs_from_root(data_root: Path) -> list[str]:
    release = data_root / "releases" / "PhyCoVE"
    candidates = (
        ("sim", release / "metadata.jsonl"),
        ("real", release / "real" / "metadata.jsonl"),
    )
    return [f"{split}={path}" for split, path in candidates if path.is_file()]

