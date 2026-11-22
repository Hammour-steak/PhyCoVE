"""Report accumulation uniformity from independently measured cached geometry."""

import argparse
import json
from pathlib import Path

import numpy as np


def summarize(report, start=24, end=84, fps=24):
    data = report["frames"]
    frames = np.array([f for f in range(start, end + 1) if str(f) in data])
    volumes = np.array([data[str(f)]["cup_mesh_volume_ml"] for f in frames])
    if len(frames) < 3:
        raise ValueError("Insufficient samples")
    times = frames / fps
    slope, intercept = np.polyfit(times, volumes, 1)
    prediction = times * slope + intercept
    r_squared = 1 - float(((volumes - prediction) ** 2).sum() / ((volumes - volumes.mean()) ** 2).sum())
    windows = []
    for a in range(start, end, 12):
        b = min(a + 12, end)
        if str(a) in data and str(b) in data:
            gain = data[str(b)]["cup_mesh_volume_ml"] - data[str(a)]["cup_mesh_volume_ml"]
            windows.append({"frames": [a, b], "gain_ml": gain, "rate_ml_s": gain / ((b - a) / fps)})
    rates = np.array([w["rate_ml_s"] for w in windows])
    increments = np.diff(volumes)
    result = {
        "range": [int(frames.min()), int(frames.max())], "slope_ml_s": float(slope),
        "linear_fit_r_squared": r_squared,
        "minimum_frame_increment_ml": float(increments.min()),
        "negative_frame_increments": int((increments < 0).sum()),
        "maximum_residual_ml": float(np.abs(volumes - prediction).max()),
        "windows": windows,
        "window_rate_cv": float(rates.std() / rates.mean()) if len(rates) else None,
        "final_pour_volume_ml": data.get("84", {}).get("cup_mesh_volume_ml"),
        "final_settled_volume_ml": data.get("96", {}).get("cup_mesh_volume_ml"),
    }
    if "90" in data and "96" in data:
        result["settle_90_to_96_relative_change"] = (data["96"]["cup_mesh_volume_ml"] - data["90"]["cup_mesh_volume_ml"]) / data["90"]["cup_mesh_volume_ml"]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--start", type=int, default=24)
    parser.add_argument("--end", type=int, default=84)
    args = parser.parse_args()
    print(json.dumps(summarize(json.loads(args.report.read_text()), args.start, args.end), indent=2))
