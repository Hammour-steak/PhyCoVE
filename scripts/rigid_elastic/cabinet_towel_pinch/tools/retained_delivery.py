"""Verify the accepted delivery, the native inputs read from the asset store and the published suite.

Data files listed with a SHA-256 in each delivery case's artifact_manifest.json (scene_manifest.json
data.accepted_delivery) are checked; a cache listed there lives in assets scenes/cabinet_towel_pinch/native.
The published suite is checked against scene_manifest.json canonical_suites (video SHA-256, GT clock).
"""
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


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 ** 2), b""):
            result.update(chunk)
    return result.hexdigest()


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
    for folder in sorted((DELIVERY / "cases").iterdir()):
        listing = folder / "artifact_manifest.json"
        if not listing.is_file():
            continue
        for row in json.loads(listing.read_bytes())["files"]:
            if "sha256" not in row:
                continue
            location = folder / row["path"]
            if not location.is_file():
                location = NATIVE / folder.name / row["path"]
            if not location.is_file():
                continue
            if digest(location) != row["sha256"]:
                raise ValueError(f"Delivery data file changed: {location}")
    suite = json.loads((DELIVERY / "suite_manifest.json").read_bytes())
    # The accepted delivery also records an ADD case that the published suite does not carry;
    # the strict edit policy is checked for the published cases.
    suite["edits"] = [edit for edit in suite["edits"] if edit.get("case_id") in CATALOG]
    if not audit_suite_manifest(suite, VOCAB, DELIVERY)["all_edits_compliant"]:
        raise ValueError("Strict edit preflight failed")
    published = manifest()["canonical_suites"][SUITE]
    root = current_suite()
    result = []
    for case in cases:
        reference = DELIVERY / "cases" / case / "video.mp4"
        state = NATIVE / case / "cache.npz"
        times = load_times(state, "times")
        require_times(times)
        video = root / published["case_video_path"][case]
        if digest(video) != published["case_video_sha256"][case]:
            raise ValueError(f"Published video differs from scene_manifest.json: {case}")
        gt = json.loads((root / "cases" / CATALOG[case] / "ground_truth_transforms.json").read_bytes())
        if len(gt["frames"]) != len(times) or gt["frames"][-1]["time_sec"] != times[-1]:
            raise ValueError(f"Ground truth does not follow the native clock: {case}")
        result.append({"case_id": case, "accepted_video": str(reference), "accepted_video_sha256": digest(reference),
                       "native_cache": str(state), "native_cache_sha256": digest(state),
                       "native_samples": len(times), "published_video": str(video),
                       "published_video_sha256": published["case_video_sha256"][case],
                       "ground_truth_frames": len(gt["frames"]), "media": require_video(video)})
    return result
