"""Locations and checks of the accepted football_goal_net data.

- renders/football_goal_net/accepted_physics/  solver snapshot of the accepted source and mass_double jobs
                                                (executed code, frozen inputs, receipt), used by the timed edit
- renders/football_goal_net/accepted_media/    accepted media delivery (per-case render reports, canonical 24 Hz
                                                states, one reference video per case)
- assets/scenes/football_goal_net/              registered inputs (packed scene, model, world, native 120 Hz caches, ...)
- renders/pcve_suites/pcve_football_goal_net_suite/  published suite (pointer in scene_manifest.json)

The accepted delivery's folder names and solver job tags are the constants below.
"""
from pathlib import Path
import ast
import hashlib
import json
import shutil
import struct
import sys
import zipfile

CASE = Path(__file__).resolve().parents[1]
SCRIPTS = CASE.parents[1]
REPO = SCRIPTS.parent
sys.path.insert(0, str(SCRIPTS))
from pcve_assets import asset  # noqa: E402
from pcve_media_contract import require_video  # noqa: E402

DATA = REPO / "renders/football_goal_net"
SUITE = DATA / "accepted_media/benchmark/package/increment/scenes/football_goal_net"
SOLVER_ARCHIVE = DATA / "accepted_physics"
CASES = ("source", "young_tenth", "mass_double", "speed_half", "remove_net")
# CPU solver jobs kept for the timed edit (physics/solve_timed.py), under <SOLVER_ARCHIVE>/.work/solver/cpu_jobs/<tag>/
JOB_TAGS = {"source": "source4s_response1103_02", "mass_double": "mass_double4s_response1103_02"}
# SHA-256 of the accepted reference videos accepted_media/videos/<case>.mp4
DELIVERY_VIDEO_SHA256 = {
    "source": "cc3d130d6cc4401e517be40a50d2a1ce6abbe74dd4db022412c7a9035bdbea40",
    "young_tenth": "77cd10e7c2984ce33194c1b91e529417c1ec0b02139dd6edf27f0a95c5871aee",
    "mass_double": "33ee4305b8662281e44947543874717252fba574abb6175ba69aec51554a27d6",
    "speed_half": "53d9351bee22d4e9574f5fe8daa952f3bf77ba2221ddcfd5d370ea8ef75d1c93",
    "remove_net": "6e73f030f501cb2c67f581d392cb618d83626564d2e7c549b35396ea8f0c29d2"}
ASSET_PREFIX = "scenes/football_goal_net"
MANIFEST = CASE / "scene_manifest.json"


def sha(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for part in iter(lambda: f.read(4 << 20), b""):
            h.update(part)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_bytes())


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


def require_clock(path, count, fps):
    values = load_times(path, "times")
    if len(values) != count or any(abs(t - i / fps) > 1e-6 for i, t in enumerate(values)):
        raise ValueError(f"Wrong native sample clock in {path}")
    return len(values)


def require_hash(path, expected):
    if sha(path) != expected:
        raise ValueError(f"Production binding changed: {path}")


def fresh(path):
    """An output path that does not exist yet (nothing is ever overwritten)."""
    target = Path(path).expanduser().resolve()
    if target.exists():
        raise ValueError(f"Choose a fresh output path: {target}")
    return target


def export(path, out, expected):
    require_hash(path, expected)
    out = fresh(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("xb") as stream, Path(path).open("rb") as source:
        shutil.copyfileobj(source, stream)
    require_hash(out, expected)


def full_input(case):
    return asset(ASSET_PREFIX + "/native/" + case)


def solver_receipt(case):
    return SOLVER_ARCHIVE / ".work/solver/cpu_jobs" / JOB_TAGS[case] / "worker_receipt.json"


def native_sha256(case):
    """SHA-256 of the native 120 Hz cache, as recorded by the canonical export of the accepted delivery."""
    return read(SUITE / "cases" / case / "canonical_export_manifest.json")["source_native_sha256"]


def delivery_video(case):
    return DATA / "accepted_media/videos" / (case + ".mp4")


def verify(cases=CASES):
    """The accepted media delivery: videos, canonical 24 Hz states and the native 120 Hz caches still bind."""
    result = {}
    cases = [case for case in cases if case in CASES]
    plan = read(CASE / "physics/strict_edit_plan.json")
    baseline = plan["baseline_physics"]
    for case in cases:
        branch = SUITE / "cases" / case
        video = delivery_video(case)
        canonical = branch / "simulation.npz"
        raw = full_input(case) / "simulation.npz"
        bind = read(branch / "canonical_export_manifest.json")
        gate = read(branch / "render_gate.json")
        render = read(branch / "render_01_render_report.json")
        report = read(branch / "physics_report.json")
        raw_sha256 = bind["source_native_sha256"]
        assert raw_sha256 == gate["simulation_sha256"] == render["cache_sha256"] == report["simulation_sha256"]
        assert bind["source_native_indices"] == list(range(0, 480, 5)) and report["native_samples"] == 481
        assert report["seconds_completed"] == 4 and gate["render_candidate_allowed"]
        scenario = read(branch / "scenario_overrides.json")["physics"]
        for key in ("ball_initial_center_m", "ball_initial_quaternion_wxyz", "ball_initial_omega_radps"):
            assert scenario[key] == baseline[key]
        require_hash(video, DELIVERY_VIDEO_SHA256[case])
        require_hash(canonical, bind["canonical_state_sha256"])
        require_hash(raw, raw_sha256)
        result[case] = {"video": str(video.relative_to(REPO)), "video_sha256": DELIVERY_VIDEO_SHA256[case],
                        "canonical_sha256": bind["canonical_state_sha256"], "raw_sha256": raw_sha256,
                        "media": require_video(video), "canonical_samples": require_clock(canonical, 96, 24),
                        "native_samples": require_clock(raw, 481, 120)}
    return {"accepted_media_delivery": result}


def catalog_id(case):
    return "source" if case == "source" else "edit_" + case


def verify_published(cases=CASES):
    """The published suite named in scene_manifest.json: videos, prompts (pcve_prompts/1), provenance and
    ground truth (pcve_ground_truth/1) bound to the native state each video replays.

    case_video_sha256 is keyed by native case id; a timed edit's native state is the merged solve kept in
    the suite's inputs/native_timed/<case>/ (physics/solve_timed.py)."""
    manifest = read(MANIFEST)
    name, pointer = next(iter(manifest["canonical_suites"].items()))
    suite = REPO / pointer["target"]
    result = {}
    for case in cases:
        cid = catalog_id(case)
        folder = suite / "cases" / cid
        video = folder / "video.mp4"
        digest = pointer["case_video_sha256"][case]
        require_hash(video, digest)
        assert pointer.get("public_case_ids", {}).get(case, cid) == cid
        prompts = read(folder / "prompts.json")
        assert prompts["format_version"] == "pcve_prompts/1" and prompts["case_id"] == cid
        assert prompts["availability"] == "available"
        provenance = read(folder / "provenance.json")
        assert provenance["case_id"] == cid and provenance["video_sha256"] == digest
        validation = read(folder / "video_validation.json")
        assert validation["sha256"] == digest and validation["full_decode_verified"]
        gt = read(folder / "ground_truth_transforms.json")
        assert gt["format_version"] == "pcve_ground_truth/1" and gt["case_id"] == cid
        assert gt["fps"] == 24 and gt["frame_start"] == 1 and gt["frame_end"] == 96 and len(gt["frames"]) == 96
        if case in CASES:
            native = native_sha256(case)
        else:
            native = sha(suite / "inputs/native_timed" / case / "simulation.npz")
        assert native in gt["source"]["sha256"].values()
        result[cid] = {"native_case_id": case, "video_sha256": digest, "native_state_sha256": native,
                       "media": require_video(video), "ground_truth_frames": len(gt["frames"])}
    return {"published_suite": name, "suite": pointer["target"], "cases": result}
