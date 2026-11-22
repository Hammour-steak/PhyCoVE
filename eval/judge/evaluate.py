"""Evaluate PhyCoVE videos with full-frame PC and EA judgments.

Usage: python3 evaluate.py MANIFEST DATA_ROOT RESULT_DIR [--workers 3]
Requires ffprobe, OpenCV, Pillow, the official `openai` package, and an
`OPENAI_API_KEY` (with optional `OPENAI_BASE_URL`) having access to the
configured judge model.
"""
import argparse
import base64
import concurrent.futures
import json
import os
import pathlib
import subprocess
import tempfile

import cv2
from openai import OpenAI
from PIL import Image, ImageDraw

MODEL = os.environ.get("PHYCOVE_JUDGE_MODEL", "gpt-6-astra")
EFFORT = os.environ.get("PHYCOVE_JUDGE_EFFORT", "medium")
REQUEST_TIMEOUT = 900 if EFFORT == "max" else 420
COMMON = """Inspect only the supplied timestamped video frames, read each sheet left to right then top to bottom. Use no tools. Output JSON only, with score (integer 1 to 5), evidence (short explanation citing visible objects and times), and limitation (short note on any ambiguity, or empty). Assign a numerical score from the visible evidence in every readable clip. Describe uncertainty in limitation. Every original frame in the indicated time window is provided. For a 24 fps, 96-frame clip, the final frame at 3.958 seconds is the normal end of the full 4-second clip. Distinguish unobserved inter-frame behavior from visible events. Visual aesthetics are irrelevant."""
PC = """You see only the candidate. Judge intrinsic visible physical plausibility: motion continuity, contact, deformation, flow, static support and causal consequences. Ignore any possible editing intent. 5: visible content has no clear physical anomaly, including a static or empty scene with plausible support and stable objects; 4: small localized anomaly; 3: clear anomaly but main process plausible; 2: major contradiction in a key interaction; 1: principal event physically incoherent. A stationary scene or absent interaction qualifies as physically plausible when no clear physical contradiction is visible. Cite observable support even for high scores.
Assess object identity through time. When an object has identifiable surface markings, track one across successive visible frames around its interaction, citing times or frame numbers, its location and direction of travel. Consider rotation, deformation, lighting and occlusion. If a visible marking is replaced or disappears on a continuously visible surface without a supported physical explanation, count it as an anomaly under the same severity scale. Ground deductions in clear visible anomalies. Record ambiguity about a marking, occlusion or sub-frame behavior in limitation and still assign a score based on what is visible."""
EA = """Judge the candidate's visible response to the instruction relative to SOURCE, using EDITED GT as the reference and CANDIDATE as the evaluated output. First identify the visible change from source to GT, then compare candidate to source for the same target, direction, onset, magnitude and direct downstream effect. Allow physically equivalent trajectories and splash details. Judge latent physical parameter changes through visible outcomes.
When the reference change is clearly visible, use this scale: 5: all observable requested changes and consequences match; 4: minor timing or magnitude deviation; 3: correct direction but one substantial mismatch; 2: weak or transient response; 1: unchanged when a clear change is required, wrong target or reversed.
When the source-to-GT target change is visually indistinguishable, treat the expected visible target response as unchanged. Compare the candidate to source and GT: 5: the candidate also preserves the relevant object's visible state, motion and consequences; 4: only minor deviations; 3: one substantial visible mismatch; 2: major mismatches with some matching aspects; 1: the main visible response contradicts the reference, such as removal of a retained target, object replacement, large deformation or changed motion outcome. Explicitly state the expected unchanged response and the candidate's observed response. An unresolvable reference change still receives a numerical score under this rule. Instruction: """
SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["score", "evidence", "limitation"],
    "properties": {
        "score": {"type": "integer", "minimum": 1, "maximum": 5},
        "evidence": {"type": "string"},
        "limitation": {"type": "string"},
    },
}


def make_client() -> OpenAI:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set.")
    base_url = os.environ.get("OPENAI_BASE_URL") or None
    return OpenAI(api_key=api_key, base_url=base_url, timeout=REQUEST_TIMEOUT)


def call_judge(image_paths: list[pathlib.Path], prompt: str) -> tuple[dict, dict]:
    content = []
    for img_path in image_paths:
        encoded = base64.b64encode(img_path.read_bytes()).decode("ascii")
        content.append({
            "type": "input_image",
            "image_url": f"data:image/jpeg;base64,{encoded}",
        })
    content.append({"type": "input_text", "text": prompt})

    client = make_client()
    response = client.responses.create(
        model=MODEL,
        reasoning={"effort": EFFORT},
        input=[{"role": "user", "content": content}],
        text={
            "format": {
                "type": "json_schema",
                "name": "phycove_judge_score",
                "strict": True,
                "schema": SCHEMA,
            }
        },
    )
    answer = json.loads(response.output_text)
    usage = response.usage.model_dump() if getattr(response, "usage", None) else {}
    return answer, usage


def full_ea_sheets(path, label, directory):
    probe = subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "frame=best_effort_timestamp_time", "-of", "json", str(path),
    ])
    stamps = [float(f["best_effort_timestamp_time"]) for f in json.loads(probe)["frames"]]
    if not stamps:
        raise ValueError(f"No frames in {path}")
    names = []
    video = cv2.VideoCapture(str(path))
    try:
        for i, t in enumerate(stamps):
            slot = i % 16
            if slot == 0:
                board = Image.new("RGB", (1280, 816), "#202020")
                draw = ImageDraw.Draw(board)
            ok, frame = video.read()
            if not ok:
                raise ValueError(f"Missing frame {i + 1} in {path}")
            im = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            im.thumbnail((320, 180))
            x, y = (slot % 4) * 320, (slot // 4) * 204
            board.paste(im, (x, y))
            draw.text((x + 4, y + 182), f"{label}  #{i + 1}/{len(stamps)}  {t - stamps[0]:.3f}s", fill="white")
            if slot == 15 or i + 1 == len(stamps):
                name = f"{label}-{len(names) + 1:03}.jpg"
                board.save(directory / name, quality=94)
                names.append(name)
        if video.read()[0]:
            raise ValueError(f"Frame count exceeds timestamp count for {path}")
    finally:
        video.release()
    return names, len(stamps)


def judge(task):
    row, axis, root, out = task
    key = "__".join([row["scene"], row["case"], row["model"], axis])
    dest = out / (key + ".json")
    if axis == "PC":
        from full_frame_pc import evaluate_video
        evaluate_video(root / row["candidate"], dest, row.get("event") or 0)
        record = json.loads(dest.read_text(encoding="utf-8"))
        record.update(key=key, axis=axis)
        dest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return
    with tempfile.TemporaryDirectory() as tmp:
        wd = pathlib.Path(tmp)
        roles = ["source", "gt", "candidate"]
        counts = {}
        image_paths = []
        for role in roles:
            names, counts[role] = full_ea_sheets(root / row[role], role.upper(), wd)
            image_paths.extend(wd / filename for filename in names)
        timing = (
            "Compare by displayed seconds across roles. A frame number in the instruction refers to "
            "the reference timeline. Inspect before and after the requested onset; early, late or "
            "transient changes count as timing errors. Cite evidence from all three clips. Evaluate "
            "only visible times and state any missing tail."
        )
        if row.get("event") is not None:
            timing += f" Requested onset in seconds: {row['event']:.6f}."
        prompt = "\n".join([COMMON, timing, EA + row["instruction"]])
        answer, usage = call_judge(image_paths, prompt)
        record = dict(
            key=key,
            axis=axis,
            judge=MODEL,
            effort=EFFORT,
            frame_counts=counts,
            prompt=prompt,
            answer=answer,
            usage=usage,
        )
        dest.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(key, answer["score"], usage, flush=True)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for name in ("manifest", "root", "out"):
        p.add_argument(name, type=pathlib.Path)
    p.add_argument("--workers", type=int, default=3)
    args = p.parse_args()
    args.out.mkdir(exist_ok=True, parents=True)
    rows = json.loads(args.manifest.read_text(encoding="utf-8"))
    tasks = [(r, a, args.root.resolve(), args.out.resolve()) for r in rows for a in ("PC", "EA")]
    with concurrent.futures.ThreadPoolExecutor(args.workers) as pool:
        list(pool.map(judge, tasks))
