#!/usr/bin/env python3
"""Serve the blinded PhyCoVE pairwise annotation interface and record JSONL votes."""
from __future__ import annotations

import argparse
import collections
import fcntl
import hashlib
import json
import mimetypes
import os
import secrets
import threading
import time
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional

from common import now_iso, read_json, read_jsonl


HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--study", type=Path, required=True)
    result.add_argument("--data-root", type=Path, required=True)
    result.add_argument("--annotations", type=Path)
    result.add_argument(
        "--assignment-plan",
        type=Path,
        help="Optional fixed rater/comparison assignment plan",
    )
    result.add_argument("--host", default="127.0.0.1")
    result.add_argument("--port", type=int, default=8090)
    result.add_argument("--assignment-minutes", type=float, default=30.0)
    result.add_argument("--min-watch-fraction", type=float, default=0.9)
    result.add_argument(
        "--max-per-rater",
        type=int,
        default=500,
        help="Maximum assigned comparisons per rater; 0 disables the cap",
    )
    return result


def contained_path(root: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative:
        raise ValueError("Empty media path")
    path = (root / relative).resolve()
    try:
        path.relative_to(root.resolve())
    except ValueError as exc:
        raise ValueError(f"Media path escapes data root: {relative}") from exc
    return path


class StudyState:
    def __init__(
        self,
        study_path: Path,
        data_root: Path,
        annotations_path: Path,
        assignment_minutes: float,
        min_watch_fraction: float,
        max_per_rater: int,
        assignment_plan_path: Optional[Path] = None,
    ) -> None:
        self.study_path = study_path.resolve()
        self.study = read_json(self.study_path)
        if self.study.get("schema_version") != 1:
            raise ValueError("Unsupported study schema")
        self.data_root = data_root.resolve()
        self.annotations_path = annotations_path.resolve()
        self.annotations_path.parent.mkdir(parents=True, exist_ok=True)
        self.assignment_seconds = max(60.0, assignment_minutes * 60.0)
        self.min_watch_fraction = min(1.0, max(0.0, min_watch_fraction))
        self.max_per_rater = max(0, max_per_rater)
        self.tasks = {task["task_id"]: task for task in self.study["tasks"]}
        self.comparisons = {
            row["comparison_id"]: row for row in self.study["comparisons"]
        }
        if len(self.tasks) != len(self.study["tasks"]):
            raise ValueError("Duplicate task ids in study")
        if len(self.comparisons) != len(self.study["comparisons"]):
            raise ValueError("Duplicate comparison ids in study")

        digest = hashlib.sha256(self.study_path.read_bytes()).hexdigest()
        self.study_digest = digest
        self.lock = threading.RLock()
        self.pending_by_rater: dict[str, dict[str, Any]] = {}
        self.pending_by_token: dict[str, dict[str, Any]] = {}
        self.judgment_counts: collections.Counter[str] = collections.Counter()
        self.done_by_rater: dict[str, set[str]] = collections.defaultdict(set)
        self.annotation_ids: set[str] = set()
        self.assignment_plan_path = (
            assignment_plan_path.resolve() if assignment_plan_path else None
        )
        self.planned_by_rater: dict[str, list[dict[str, Any]]] = {}
        self._load_assignment_plan()
        self._load_annotations()

    def _load_assignment_plan(self) -> None:
        if not self.assignment_plan_path:
            return
        plan = read_json(self.assignment_plan_path)
        if plan.get("schema_version") != 1:
            raise ValueError("Unsupported assignment-plan schema")
        if plan.get("study_sha256") != self.study_digest:
            raise ValueError("Assignment plan belongs to another study")
        seen: set[tuple[str, str]] = set()
        counts: collections.Counter[str] = collections.Counter()
        for row in plan.get("assignments", []):
            rater = self.rater_hash(row.get("rater_code", ""))
            comparison_id = row.get("comparison_id")
            if comparison_id not in self.comparisons:
                raise ValueError(f"Unknown planned comparison: {comparison_id}")
            comparison = self.comparisons[comparison_id]
            expected_models = {comparison["model_1"], comparison["model_2"]}
            if {row.get("model_a"), row.get("model_b")} != expected_models:
                raise ValueError(f"Model mismatch in planned comparison {comparison_id}")
            key = rater, comparison_id
            if key in seen:
                raise ValueError(f"Duplicate planned rater/comparison: {key}")
            seen.add(key)
            counts[comparison_id] += 1
            self.planned_by_rater.setdefault(rater, []).append(
                {
                    "assignment_id": row.get("assignment_id"),
                    "comparison_id": comparison_id,
                    "model_a": row["model_a"],
                    "model_b": row["model_b"],
                }
            )
        if not self.planned_by_rater:
            raise ValueError("Assignment plan contains no assignments")
        for comparison_id, comparison in self.comparisons.items():
            if counts[comparison_id] != comparison["target_ratings"]:
                raise ValueError(
                    f"Planned comparison {comparison_id} has {counts[comparison_id]} "
                    f"assignments, expected {comparison['target_ratings']}"
                )
        for assignments in self.planned_by_rater.values():
            assignments.sort(
                key=lambda row: (row.get("assignment_id") or "", row["comparison_id"])
            )

    def _load_annotations(self) -> None:
        for row in read_jsonl(self.annotations_path):
            if row.get("study_sha256") != self.study_digest:
                raise ValueError(
                    "Annotation file contains rows from another study: "
                    f"{row.get('annotation_id', '<unknown>')}"
                )
            annotation_id = row.get("annotation_id")
            if annotation_id in self.annotation_ids:
                raise ValueError(f"Duplicate annotation id: {annotation_id}")
            self.annotation_ids.add(annotation_id)
            rater = row.get("rater_id")
            comparison_id = row.get("comparison_id")
            if rater and comparison_id:
                if comparison_id in self.done_by_rater[rater]:
                    raise ValueError(
                        f"Rater {rater} annotated {comparison_id} more than once"
                    )
                self.done_by_rater[rater].add(comparison_id)
            if row.get("record_type") == "judgment":
                self.judgment_counts[comparison_id] += 1

    def rater_hash(self, rater_name: str) -> str:
        normalized = " ".join(rater_name.strip().split())
        if not 2 <= len(normalized) <= 64:
            raise ValueError("Annotator code must be 2–64 characters long")
        return hashlib.sha256(
            f"{self.study_digest}:{normalized}".encode("utf-8")
        ).hexdigest()[:20]

    def _cleanup_pending(self) -> None:
        cutoff = time.monotonic() - self.assignment_seconds
        expired = [
            rater
            for rater, assignment in self.pending_by_rater.items()
            if assignment["monotonic_started"] < cutoff
        ]
        for rater in expired:
            assignment = self.pending_by_rater.pop(rater)
            self.pending_by_token.pop(assignment["token"], None)

    def _reserved_counts(self) -> collections.Counter[str]:
        return collections.Counter(
            assignment["comparison_id"]
            for assignment in self.pending_by_rater.values()
        )

    def progress(self, rater: Optional[str] = None) -> dict[str, Any]:
        total = sum(row["target_ratings"] for row in self.comparisons.values())
        completed = sum(
            min(self.judgment_counts[identifier], row["target_ratings"])
            for identifier, row in self.comparisons.items()
        )
        result: dict[str, Any] = {
            "completed_judgments": completed,
            "target_judgments": total,
            "completed_percent": round(100 * completed / total, 2) if total else 100,
        }
        if rater:
            result["rater_completed"] = len(self.done_by_rater[rater])
            if self.planned_by_rater:
                result["rater_total_available"] = len(
                    self.planned_by_rater.get(rater, [])
                )
            else:
                result["rater_total_available"] = (
                    min(self.max_per_rater, len(self.comparisons))
                    if self.max_per_rater
                    else len(self.comparisons)
                )
        return result

    def next_assignment(self, rater_name: str) -> dict[str, Any]:
        rater = self.rater_hash(rater_name)
        with self.lock:
            self._cleanup_pending()
            if rater in self.pending_by_rater:
                return self.public_assignment(self.pending_by_rater[rater])
            if self.planned_by_rater and rater not in self.planned_by_rater:
                raise ValueError("Annotator code is not in the fixed assignment plan")
            if (
                not self.planned_by_rater
                and self.max_per_rater
                and len(self.done_by_rater[rater]) >= self.max_per_rater
            ):
                return {
                    "done": True,
                    "waiting": False,
                    "rater_quota_reached": True,
                    "progress": self.progress(rater),
                }

            reserved = self._reserved_counts()
            available = []
            if self.planned_by_rater:
                candidate_rows = [
                    (
                        row["comparison_id"],
                        self.comparisons[row["comparison_id"]],
                        row,
                    )
                    for row in self.planned_by_rater[rater]
                ]
            else:
                candidate_rows = [
                    (comparison_id, comparison, None)
                    for comparison_id, comparison in self.comparisons.items()
                ]
            for comparison_id, comparison, planned in candidate_rows:
                if comparison_id in self.done_by_rater[rater]:
                    continue
                filled = self.judgment_counts[comparison_id] + reserved[comparison_id]
                if filled < comparison["target_ratings"]:
                    available.append((filled, comparison_id, comparison, planned))
            if not available:
                if self.planned_by_rater:
                    return {
                        "done": True,
                        "waiting": False,
                        "rater_quota_reached": True,
                        "progress": self.progress(rater),
                    }
                waiting = any(
                    self.judgment_counts[identifier] < row["target_ratings"]
                    for identifier, row in self.comparisons.items()
                )
                return {
                    "done": not waiting,
                    "waiting": waiting,
                    "progress": self.progress(rater),
                }

            minimum = min(item[0] for item in available)
            least_filled = [item for item in available if item[0] == minimum]
            least_filled.sort(key=lambda item: item[1])
            selector = hashlib.sha256(
                f"{self.study_digest}:{rater}:{len(self.done_by_rater[rater])}".encode()
            ).digest()
            selected = least_filled[
                int.from_bytes(selector[:8], "big") % len(least_filled)
            ]
            comparison = selected[2]
            planned = selected[3]
            if planned:
                models = [planned["model_a"], planned["model_b"]]
            else:
                models = [comparison["model_1"], comparison["model_2"]]
                if selector[8] % 2:
                    models.reverse()
            token = secrets.token_urlsafe(24)
            assignment = {
                "token": token,
                "rater_id": rater,
                "comparison_id": comparison["comparison_id"],
                "model_a": models[0],
                "model_b": models[1],
                "started_at": now_iso(),
                "started_epoch": time.time(),
                "monotonic_started": time.monotonic(),
            }
            self.pending_by_rater[rater] = assignment
            self.pending_by_token[token] = assignment
            return self.public_assignment(assignment)

    def public_assignment(self, assignment: dict[str, Any]) -> dict[str, Any]:
        comparison = self.comparisons[assignment["comparison_id"]]
        task = self.tasks[comparison["task_id"]]
        token = assignment["token"]
        return {
            "done": False,
            "waiting": False,
            "progress": self.progress(assignment["rater_id"]),
            "item": {
                "token": token,
                "task_id": task["task_id"],
                "edit_type": task["edit_type"],
                "event": task["event"],
                "timed": task["timed"],
                "instruction_en": task["instruction_en"],
                "media": {
                    role: f"/media/{token}/{role}"
                    for role in ("source", "gt", "a", "b")
                },
            },
        }

    def media_path(self, token: str, role: str) -> Path:
        if role not in {"source", "gt", "a", "b"}:
            raise KeyError(role)
        with self.lock:
            assignment = self.pending_by_token.get(token)
            if not assignment:
                raise KeyError(token)
            comparison = self.comparisons[assignment["comparison_id"]]
            task = self.tasks[comparison["task_id"]]
            if role == "source":
                relative = task["source"]
            elif role == "gt":
                relative = task["gt"]
            else:
                relative = task["candidates"][assignment[f"model_{role}"]]
        path = contained_path(self.data_root, relative)
        if not path.is_file() or path.stat().st_size == 0:
            raise FileNotFoundError(path)
        return path

    def _validate_watch(self, client: Any) -> None:
        if self.min_watch_fraction <= 0:
            return
        if not isinstance(client, dict) or not isinstance(client.get("watch"), dict):
            raise ValueError("Missing full playback record")
        for role in ("source", "gt", "a", "b"):
            watch = client["watch"].get(role)
            if not isinstance(watch, dict):
                raise ValueError(f"Please play {role} in full first")
            duration = float(watch.get("duration") or 0)
            maximum = float(watch.get("max_time") or 0)
            ended = bool(watch.get("ended"))
            if duration <= 0 or (not ended and maximum / duration < self.min_watch_fraction):
                raise ValueError(f"Please play {role} in full first")

    def submit(self, rater_name: str, token: str, choice: str, client: Any) -> dict[str, Any]:
        rater = self.rater_hash(rater_name)
        if choice not in {"a", "tie", "b", "technical"}:
            raise ValueError("Invalid preference choice")
        with self.lock:
            assignment = self.pending_by_token.get(token)
            if not assignment or assignment["rater_id"] != rater:
                raise ValueError("Assignment expired; please fetch a new one")
            comparison_id = assignment["comparison_id"]
            if comparison_id in self.done_by_rater[rater]:
                raise ValueError("This comparison has already been submitted")
            if choice != "technical":
                self._validate_watch(client)

            model_a = assignment["model_a"]
            model_b = assignment["model_b"]
            if choice == "a":
                winner, loser = model_a, model_b
            elif choice == "b":
                winner, loser = model_b, model_a
            else:
                winner = loser = None
            record_type = "technical_issue" if choice == "technical" else "judgment"
            annotation_id = "ann_" + secrets.token_hex(12)
            row = {
                "schema_version": 1,
                "record_type": record_type,
                "annotation_id": annotation_id,
                "study_sha256": self.study_digest,
                "submitted_at": now_iso(),
                "rater_id": rater,
                "comparison_id": comparison_id,
                "task_id": self.comparisons[comparison_id]["task_id"],
                "model_a": model_a,
                "model_b": model_b,
                "choice": choice,
                "winner_model": winner,
                "loser_model": loser,
                "elapsed_seconds": round(time.time() - assignment["started_epoch"], 3),
                "client": client if isinstance(client, dict) else {},
            }
            encoded = json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n"
            with self.annotations_path.open("a", encoding="utf-8") as handle:
                handle.write(encoded)
                handle.flush()
                os.fsync(handle.fileno())
            self.annotation_ids.add(annotation_id)
            self.done_by_rater[rater].add(comparison_id)
            if record_type == "judgment":
                self.judgment_counts[comparison_id] += 1
            self.pending_by_rater.pop(rater, None)
            self.pending_by_token.pop(token, None)
            return {"ok": True, "progress": self.progress(rater)}


class Handler(BaseHTTPRequestHandler):
    server_version = "PhyCoVEHumanPreference/1.0"

    @property
    def state(self) -> StudyState:
        return self.server.state  # type: ignore[attr-defined]

    def send_json(self, value: Any, status: int = 200) -> None:
        data = json.dumps(value, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def send_error_json(self, status: int, message: str) -> None:
        self.send_json({"error": message}, status)

    def send_disk_file(self, path: Path, allow_range: bool = False) -> None:
        size = path.stat().st_size
        start, end = 0, size - 1
        status = HTTPStatus.OK
        range_header = self.headers.get("Range") if allow_range else None
        if range_header:
            try:
                unit, values = range_header.strip().split("=", 1)
                if unit != "bytes" or "," in values:
                    raise ValueError
                first, last = values.split("-", 1)
                if first:
                    start = int(first)
                    end = int(last) if last else size - 1
                else:
                    suffix = int(last)
                    start = max(0, size - suffix)
                    end = size - 1
                if start < 0 or end < start or start >= size:
                    raise ValueError
                end = min(end, size - 1)
                status = HTTPStatus.PARTIAL_CONTENT
            except (ValueError, TypeError):
                self.send_response(HTTPStatus.REQUESTED_RANGE_NOT_SATISFIABLE)
                self.send_header("Content-Range", f"bytes */{size}")
                self.end_headers()
                return
        content_length = end - start + 1
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(content_length))
        self.send_header("Accept-Ranges", "bytes")
        if status == HTTPStatus.PARTIAL_CONTENT:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        self.send_header("Cache-Control", "private, max-age=300")
        self.end_headers()
        if self.command == "HEAD":
            return
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = content_length
            while remaining:
                chunk = handle.read(min(1024 * 1024, remaining))
                if not chunk:
                    break
                self.wfile.write(chunk)
                remaining -= len(chunk)

    def static_file(self, relative: str) -> None:
        candidate = (STATIC_DIR / relative).resolve()
        try:
            candidate.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        if not candidate.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        self.send_disk_file(candidate)

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        try:
            if parsed.path in {"/", "/index.html"}:
                self.static_file("index.html")
                return
            if parsed.path.startswith("/static/"):
                self.static_file(parsed.path[len("/static/") :])
                return
            if parsed.path == "/api/next":
                query = urllib.parse.parse_qs(parsed.query)
                rater = query.get("rater", [""])[0]
                self.send_json(self.state.next_assignment(rater))
                return
            if parsed.path == "/api/progress":
                query = urllib.parse.parse_qs(parsed.query)
                raw_rater = query.get("rater", [""])[0]
                rater = self.state.rater_hash(raw_rater) if raw_rater else None
                self.send_json(self.state.progress(rater))
                return
            if parsed.path.startswith("/media/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) != 3:
                    raise KeyError(parsed.path)
                _, token, role = parts
                self.send_disk_file(self.state.media_path(token, role), allow_range=True)
                return
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
        except (KeyError, FileNotFoundError) as exc:
            self.send_error_json(HTTPStatus.NOT_FOUND, str(exc))
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/api/submit":
            self.send_error_json(HTTPStatus.NOT_FOUND, "Not found")
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 256_000:
                raise ValueError("Invalid request size")
            payload = json.loads(self.rfile.read(length))
            if not isinstance(payload, dict):
                raise ValueError("Request body must be a JSON object")
            result = self.state.submit(
                payload.get("rater", ""),
                payload.get("token", ""),
                payload.get("choice", ""),
                payload.get("client", {}),
            )
            self.send_json(result)
        except (ValueError, json.JSONDecodeError) as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def log_message(self, format_string: str, *args: Any) -> None:
        # Suppress access logs because /api/next carries the temporary raw
        # rater code. Only its irreversible hash is persisted in JSONL.
        return


def main() -> None:
    args = parser().parse_args()
    study_path = args.study.expanduser().resolve()
    annotations = (
        args.annotations.expanduser().resolve()
        if args.annotations
        else study_path.with_name("annotations.jsonl")
    )
    state = StudyState(
        study_path=study_path,
        data_root=args.data_root.expanduser().resolve(),
        annotations_path=annotations,
        assignment_minutes=args.assignment_minutes,
        min_watch_fraction=args.min_watch_fraction,
        max_per_rater=args.max_per_rater,
        assignment_plan_path=(
            args.assignment_plan.expanduser().resolve()
            if args.assignment_plan
            else None
        ),
    )
    lock_path = annotations.with_suffix(annotations.suffix + ".lock")
    lock_handle = lock_path.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        raise RuntimeError(f"Another annotation server is using {annotations}") from exc
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    server.state = state  # type: ignore[attr-defined]
    print(f"Serving http://{args.host}:{args.port}")
    print(f"Study: {study_path}")
    if args.assignment_plan:
        print(f"Assignment plan: {args.assignment_plan.expanduser().resolve()}")
    print(f"Annotations: {annotations}")
    print(json.dumps(state.progress(), ensure_ascii=False))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()

