"""Validate the accepted gym_landing_mat delivery: audit records, videos, edit parameters and media contract."""
from __future__ import annotations

import hashlib
import json

from edit_vocab import EDIT_CASES, VOCAB
import pcve_edit_dsl as dsl
from scene_paths import DELIVERY

REBOUND = DELIVERY / "rebound"
WHOLE_CLIP = DELIVERY / "whole_clip"
CASES = ("source", "mass_double", "faster", "young_modulus_rebound", "add_path_obstacle", "delete_actor")
FOLDERS = dict(zip(CASES, ("production_source", "mass_double", "faster", "young_modulus_rebound", "add_path_obstacle", "delete_actor")))

def validate_delivery() -> None:
    audit = json.loads((REBOUND / "delivery/delivery_verification.json").read_text(encoding="utf-8"))
    if audit.get("status") != "passed" or len(audit.get("rows", [])) != 6:
        raise RuntimeError("Delivery audit did not pass")
    for case_id, folder in FOLDERS.items():
        revision = REBOUND if case_id == "young_modulus_rebound" else WHOLE_CLIP
        main = revision / "delivery/cases" / folder / "main"
        video = main / "video.mp4"
        expected = next(row for row in audit["rows"] if row["case"] == folder)
        if not video.is_file() or hashlib.sha256(video.read_bytes()).hexdigest() != expected["video_sha256"]:
            raise RuntimeError(f"Video missing or differs from accepted delivery: {case_id}")
        config = json.loads((main / "simulation_config.json").read_text(encoding="utf-8"))
        prompt = EDIT_CASES[case_id]
        override = dsl.to_physics_override(dsl.parse(prompt, VOCAB), VOCAB) if prompt else {}
        if config["edit"].get("override", {}) != override:
            raise RuntimeError(f"Edit vocabulary differs from the delivered simulation: {case_id}")
        if any(config["physics"].get(key) != value for key, value in override.items()):
            raise RuntimeError(f"Resolved physical parameters differ from the prompt: {case_id}")
        probe = json.loads((main / "video_probe.json").read_text(encoding="utf-8"))
        stream = probe["streams"][0]
        if [stream["width"], stream["height"]] != [1280, 720] or stream["avg_frame_rate"] != "24/1" or int(stream["nb_read_frames"]) != 96 or abs(float(probe["format"]["duration"]) - 4.0) > 1e-6:
            raise RuntimeError(f"Video contract failed: {case_id}")
    rebound = json.loads((REBOUND / "delivery/rebound_audit.json").read_text(encoding="utf-8"))
    if rebound["status"] != "passed" or rebound["young_modulus_multiplier"] != 10 or set(rebound["only_active_physical_change"]) != {"solid_young_modulus"}:
        raise RuntimeError("E-only rebound audit failed")
