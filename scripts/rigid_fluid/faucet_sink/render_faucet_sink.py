"""Render the accepted four-second sink clip and emit only video + prompts."""

from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

import bpy


HERE = Path(__file__).resolve().parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--case-id",
        choices=("source", "edit_low_flow", "edit_high_flow", "edit_high_viscosity", "edit_stop_flow_at_2s"),
        default="source",
    )
    parser.add_argument("--scene", type=Path)
    parser.add_argument("--output-dir", type=Path)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def prompts(case_id: str, high_viscosity_m2_s: float | None = None) -> dict:
    cases = {
        "source": {
            "edit_dsl": None,
            "vague_zh": "一股细细的水流从水龙头持续流进排水口被堵住的白色洗手盆,水在盆底铺开,盆里的水慢慢积起来。",
            "vague_en": "A thin stream of water runs steadily from the faucet into a white sink whose drain is closed; the water spreads over the basin floor and slowly collects.",
            "quant_zh": "水龙头以 0.6 m/s 的速度持续出水 4 s,水(运动黏度 1e-6 m²/s)落进排水口被堵住的洗手盆,在盆底铺开并逐渐积起来。",
            "quant_en": "The faucet runs at an inflow speed of 0.6 m/s for 4 s; the water (kinematic viscosity 1e-6 m²/s) falls into the sink with its drain closed, spreads over the basin and slowly collects.",
        },
        "edit_low_flow": {
            "edit_dsl": "SET faucet.inflow_velocity TIMES 0.333333",
            "vague_zh": "从视频一开始,把洗手台水龙头的入流速度调小一些。",
            "vague_en": "From the start of the clip, decrease the sink faucet's inflow velocity.",
            "quant_zh": "从第 1 帧开始,把洗手台水龙头的入流速度减少到原来的 0.333333 倍。",
            "quant_en": "From frame 1 onwards, reduce the sink faucet's inflow velocity to 0.333333 times its original value.",
        },
        "edit_high_flow": {
            "edit_dsl": "SET faucet.inflow_velocity TIMES 2.5",
            "vague_zh": "从视频一开始,把洗手台水龙头的入流速度调大一些。",
            "vague_en": "From the start of the clip, increase the sink faucet's inflow velocity.",
            "quant_zh": "从第 1 帧开始,把洗手台水龙头的入流速度增加到原来的 2.5 倍。",
            "quant_en": "From frame 1 onwards, increase the sink faucet's inflow velocity to 2.5 times its original value.",
        },
        "edit_high_viscosity": {
            "edit_dsl": None,
            "vague_zh": "从视频一开始,把水龙头流出的液体的运动黏度调大一些。",
            "vague_en": "From the start of the clip, increase the liquid flowing from the faucet's kinematic viscosity.",
            "quant_zh": None,
            "quant_en": None,
        },
        "edit_stop_flow_at_2s": {
            "edit_dsl": "SET faucet.inflow_velocity TIMES 0 AT FRAME 49",
            "vague_zh": "在视频进行到一半左右时,把洗手台水龙头的入流速度清零。",
            "vague_en": "About halfway through the clip, set the sink faucet's inflow velocity to zero.",
            "quant_zh": "从第 49 帧开始,把洗手台水龙头的入流速度清零。",
            "quant_en": "From frame 49 onwards, set the sink faucet's inflow velocity to zero.",
        },
    }
    if case_id not in cases:
        raise RuntimeError(f"Unsupported PCVE case: {case_id}")
    case = cases[case_id]
    if case_id == "edit_high_viscosity":
        if high_viscosity_m2_s is None or high_viscosity_m2_s <= 0.0:
            raise RuntimeError("Missing positive SI kinematic viscosity for high-viscosity edit")
        multiplier = int(round(high_viscosity_m2_s / 1.0e-6))
        case["edit_dsl"] = f"SET water.viscosity TIMES {multiplier}"
        case["quant_zh"] = f"从第 1 帧开始,把水龙头流出的液体的运动黏度增加到原来的 {multiplier} 倍。"
        case["quant_en"] = (
            "From frame 1 onwards, increase the liquid flowing from the faucet's kinematic viscosity "
            f"to {multiplier} times its original value."
        )
    payload = {
        "case_id": case_id,
        "source_case_id": None if case_id == "source" else "source",
        "interaction_category": "rigid_fluid",
        "edit_dsl": case["edit_dsl"],
        "prompts": {
            "vague": {
                "zh": case["vague_zh"],
                "en": case["vague_en"],
            },
            "quantitative": {
                "zh": case["quant_zh"],
                "en": case["quant_en"],
            },
        },
    }
    if case_id == "edit_stop_flow_at_2s":
        payload["timed_edits"] = [{"frame": 49, "time_s": 2.0,
            "params": {"faucet_inflow_velocity_m_s": 0.0}, "mantaflow_use_inflow": False}]
        payload["time_convention"] = "t=(frame-1)/24"
        payload["existing_liquid"] = "retained; the liquid solver remains active"
    return payload


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> None:
    args = parse_args()
    case_dir = HERE / "cases" / args.case_id
    source = (args.scene or (case_dir / "work" / "scene_baked.blend")).expanduser().resolve()
    output = (args.output_dir or (case_dir / "output")).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    output.mkdir(parents=True, exist_ok=True)
    unexpected = [path.name for path in output.iterdir() if path.name not in {"video.mp4", "prompts.json"}]
    if unexpected:
        raise RuntimeError(f"Output directory must contain only video and prompts: {unexpected}")

    bpy.ops.wm.open_mainfile(filepath=str(source))
    scene = bpy.context.scene
    case_id = scene.get("pcve_case_id")
    if case_id not in {"source", "edit_low_flow", "edit_high_flow", "edit_high_viscosity", "edit_stop_flow_at_2s"}:
        raise RuntimeError(f"Missing or unsupported pcve_case_id: {case_id}")
    if case_id != args.case_id:
        raise RuntimeError("Baked scene and requested case differ")
    if (scene.frame_start, scene.frame_end, scene.render.fps) != (1, 96, 24):
        raise RuntimeError("Expected 96 frames at 24 fps")
    if bpy.data.objects.get("SinkDrainOutflow") is not None:
        raise RuntimeError("Central drain outflow must remain disabled")
    flows = [
        obj.name
        for obj in scene.objects
        if any(mod.type == "FLUID" and mod.fluid_type == "FLOW" for mod in obj.modifiers)
    ]
    if flows != ["FaucetWaterInflow"]:
        raise RuntimeError(f"Unexpected liquid flows: {flows}")

    scene.render.engine = "BLENDER_EEVEE_NEXT"
    scene.eevee.taa_render_samples = 128
    scene.render.resolution_x = 1280
    scene.render.resolution_y = 720
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "MEDIUM"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    video = output / "video.mp4"
    scene.render.filepath = str(video)
    started = time.monotonic()
    bpy.ops.render.render(animation=True)

    prompt_path = output / "prompts.json"
    prompt_path.write_text(
        json.dumps(
            prompts(case_id, scene.get("pcve_high_viscosity_value")),
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    probe = json.loads(
        subprocess.check_output(
            [
                "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
                "-show_entries", "stream=width,height,r_frame_rate,nb_read_frames:format=duration",
                "-of", "json", str(video),
            ],
            text=True,
        )
    )
    stream = probe["streams"][0]
    if (
        (stream["width"], stream["height"]) != (1280, 720)
        or stream["r_frame_rate"] != "24/1"
        or int(stream["nb_read_frames"]) != 96
        or abs(float(probe["format"]["duration"]) - 4.0) > 0.001
    ):
        raise RuntimeError(f"Video verification failed: {probe}")
    subprocess.run(["ffmpeg", "-nostdin", "-v", "error", "-xerror", "-i", str(video), "-f", "null", "-"], check=True)
    print(f"PCVE_RENDER_SECONDS={time.monotonic() - started:.3f}", flush=True)
    print(f"PCVE_VIDEO_SHA256={digest(video)}", flush=True)
    print(f"PCVE_OUTPUT={output}", flush=True)


if __name__ == "__main__":
    main()
