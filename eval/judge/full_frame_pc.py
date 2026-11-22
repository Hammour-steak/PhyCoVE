"""Evaluate one candidate video's physical plausibility using all frames."""
import argparse
import json
import subprocess
import tempfile
from pathlib import Path

import cv2
from PIL import Image, ImageDraw
from evaluate import COMMON, PC, MODEL, EFFORT, call_judge

PROMPT = COMMON + "\n" + PC + """
All decoded frames are supplied in time order as numbered sheets, with one
frame of overlap. For the main physical interaction, inspect the frames before,
during, and after it. Cite frame numbers and timestamps. Consider plausible
occlusion and viewpoint effects. Report uncertainty if the evidence is ambiguous."""


def evaluate_video(video, output, start_sec=0):
    meta = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(video),
    ])
    times = [float(f["best_effort_timestamp_time"]) for f in json.loads(meta)["frames"]]
    first = next((i for i, t in enumerate(times) if t - times[0] >= start_sec - 1e-6), len(times))
    prompt = PROMPT
    if start_sec > 0:
        prompt += "\nTreat the first supplied frame as the initial state. Assess only the visible evolution from that frame onward."
    cap = cv2.VideoCapture(str(video))
    with tempfile.TemporaryDirectory() as dirname:
        wd = Path(dirname)
        sheet_names = []
        frames = []
        try:
            for idx, t in enumerate(times):
                ok, f = cap.read()
                if not ok:
                    raise ValueError(f"Missing frame {idx + 1}")
                if idx < first:
                    continue
                im = Image.fromarray(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
                im.thumbnail((480, 270))
                frames.append((idx + 1, t - times[0], im))
                if len(frames) == 9 or idx == len(times) - 1:
                    board = Image.new("RGB", (1440, 882), "#202020")
                    draw = ImageDraw.Draw(board)
                    for j, (n, sec, frame) in enumerate(frames):
                        x, y = j % 3 * 480, j // 3 * 294
                        board.paste(frame, (x, y))
                        draw.text((x + 6, y + 272), f"Frame {n:03} / {len(times)}    {sec:.3f}s", fill="white")
                    name = f"frames-{frames[0][0]:03}-{frames[-1][0]:03}.jpg"
                    board.save(wd / name, quality=94)
                    sheet_names.append(name)
                    frames = frames[-1:]
            if cap.read()[0]:
                raise ValueError("Decoded frame count exceeds timestamp count")
        finally:
            cap.release()
        if not sheet_names:
            raise ValueError("No video frames at or after the start time")
        answer, usage = call_judge([wd / name for name in sheet_names], prompt)
        result = dict(
            judge=MODEL,
            effort=EFFORT,
            frame_count=len(times) - first,
            start_sec=start_sec,
            first_frame=first + 1,
            first_pts_sec=times[first] - times[0],
            sheets=sheet_names,
            prompt=prompt,
            answer=answer,
            usage=usage,
        )
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--start-sec", type=float, default=0, help="Inclusive PC window start in source-timeline seconds")
    args = parser.parse_args()
    evaluate_video(args.video, args.output, args.start_sec)
