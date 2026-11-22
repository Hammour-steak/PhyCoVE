"""Merge RUN_DIR/results/*.json into RUN_DIR/all_results.json, or refresh it during the run with --watch."""
import argparse
import collections
import json
import os
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

def export(rows, paths, base):
    videos = []
    count = 0
    judges = collections.Counter()
    for row in rows:
        axes = {}
        for axis in ("PC", "EA"):
            key = "__".join((row["scene"], row["case"], row["model"], axis))
            if key in paths:
                axes[axis] = json.loads(paths[key].read_text())
                rec = axes[axis]
                judges[rec["judge"], rec["effort"]] += 1
                count += 1
        if axes:
            videos.append({**row, "ratings": axes})
    assert count == len(paths)
    report = dict(updated_at=datetime.now(timezone.utc).isoformat(), total_scores=2*len(rows),
                  completed_scores=count,
                  evaluators=[dict(judge=judge, effort=effort, scores=n)
                              for (judge,effort),n in sorted(judges.items())],
                  videos=videos)
    with tempfile.NamedTemporaryFile(mode="w", dir=base, delete=False) as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    os.replace(f.name, base/"all_results.json")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path, help="Folder with manifest.json and results/")
    parser.add_argument("--watch", action="store_true")
    args = parser.parse_args()
    base = args.run_dir.expanduser().resolve()
    rows = json.loads((base/"manifest.json").read_text())
    last = -1
    while True:
        paths = {p.stem:p for p in (base/"results").glob("*.json")}
        if len(paths) != last:
            export(rows, paths, base)
            last = len(paths)
        if not args.watch or last == 2*len(rows): break
        time.sleep(60)
