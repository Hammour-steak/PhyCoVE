"""Verify the accepted delivery, its native inputs and the published suite (no Blender, no solve)."""
import ast
import hashlib
import json
import struct
import zipfile
from pathlib import Path

from edit_vocab import VOCAB
from pcve_edit_policy import audit_suite_manifest
from pcve_media_contract import require_times, require_video
from scene_paths import CATALOG, DELIVERY, NATIVE, SUITE, current_suite, manifest


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def load_times(path, member):
    with zipfile.ZipFile(path) as z:
        raw = z.read(member + ".npy")
    if raw[:8] != b"\x93NUMPY\x01\x00":
        raise ValueError(f"Unsupported native sample clock: {path}")
    size, = struct.unpack_from("<H", raw, 8)
    header = ast.literal_eval(raw[10:10 + size].decode("latin1").strip())
    if header["descr"] not in {"<f8", "<f4"} or len(header["shape"]) != 1:
        raise ValueError(f"Expected a 1D floating-point clock: {path}")
    code = "d" if header["descr"] == "<f8" else "f"
    return struct.unpack(f"<{header['shape'][0]}{code}", raw[10 + size:])


def verify(cases):
    """Accepted delivery: native caches equal to the replay audit of each render, strict edit policy, clocks."""
    delivery_manifest = json.loads((DELIVERY / "suite_manifest.json").read_bytes())
    if not audit_suite_manifest(delivery_manifest, VOCAB, DELIVERY)["all_edits_compliant"]:
        raise ValueError("Strict edit policy failed")
    result = []
    for case in cases:
        video, state = DELIVERY / "cases" / case / "video.mp4", NATIVE / case / "simulation.npz"
        report = json.loads((DELIVERY / "cases" / case / "render_report.json").read_bytes())
        replay = json.loads((DELIVERY / "cases" / case / "native_replay_audit.json").read_bytes())
        state_sha256 = sha256(state)
        if replay["native_cache_sha256"] != state_sha256:
            raise ValueError(f"Accepted render does not replay this native cache: {case}")
        times = load_times(state, "times")
        require_times(times[:96])
        if len(times) != 97 or abs(times[-1] - 4.) > 1e-8:
            raise ValueError(f"Missing native four-second endpoint: {case}")
        require_times(report["physical_time_s"])
        result.append({"case_id": case, "video": str(video), "video_sha256": sha256(video),
                       "native_cache": str(state), "native_cache_sha256": state_sha256,
                       "native_samples": 96, "media": require_video(video)})
    return result


def verify_suite(cases):
    """Published suite: video SHA-256 as in scene_manifest.json, media contract, prompts and 96-frame GT."""
    suite = current_suite()
    pins = manifest()["canonical_suites"][SUITE]["case_video_sha256"]
    result = []
    for case in cases:
        folder = suite / "cases" / CATALOG[case]
        video = folder / "video.mp4"
        digest = sha256(video)
        if digest != pins[case]:
            raise ValueError(f"Published video differs from scene_manifest.json: {case}")
        gt = json.loads((folder / "ground_truth_transforms.json").read_text(encoding="utf-8"))
        if gt["fps"] != 24 or len(gt["frames"]) != 96 or gt["frame_end"] != 96:
            raise ValueError(f"Ground truth does not match the 96-frame video: {case}")
        provenance = json.loads((folder / "provenance.json").read_text(encoding="utf-8"))
        if provenance["video_sha256"] != digest:
            raise ValueError(f"provenance.json names another video: {case}")
        result.append({"case_id": case, "catalog_case_id": CATALOG[case], "video_sha256": digest,
                       "ground_truth_frames": len(gt["frames"]), "media": require_video(video)})
    return result
