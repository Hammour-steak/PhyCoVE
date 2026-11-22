"""Optional GPU allocation checks for scene launchers. Metadata queries only; never starts a job.

Prefers 24 GB GPUs when available and allows explicitly selected 48 GB GPUs
(named via CUDA_VISIBLE_DEVICES or --gpu/--gpu-uuid) unless excluded in
PCVE_GPU_RESERVED (comma-separated GPU indices or UUIDs; empty by default).
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys

POLICY_ID = "pcve-gpu-policy"
LARGE_CARD_MIB = 45 * 1024  # A 48 GB A6000 typically reports about 49140 MiB.
SMALL_CARD_CAPACITY_MIB = 24 * 1024
RTX_4090 = re.compile(r"\bRTX\s+4090\b", re.I)
DEFAULT_RESERVED = ""


class GpuPolicyError(RuntimeError):
    pass


def inventory():
    raw = subprocess.check_output([
        "nvidia-smi", "--query-gpu=uuid,name,memory.total,index",
        "--format=csv,noheader,nounits",
    ], text=True, timeout=15)
    result = []
    for row in csv.reader(io.StringIO(raw), skipinitialspace=True):
        if len(row) != 4 or not row[0].startswith("GPU-"):
            raise GpuPolicyError("GPU model/memory query is incomplete; preserve the queue and retry")
        result.append({"uuid": row[0].strip(), "name": row[1].strip(), "total_mib": int(row[2].strip()),
                       "index": row[3].strip()})
    if not result:
        raise GpuPolicyError("No GPU model/memory evidence; preserve the queue and retry")
    return result


def _names(gpu, tokens):
    """Whether one of the tokens (index, full UUID or UUID prefix) names this GPU."""
    return any(token and (token == gpu.get("index") or token == gpu["uuid"]
                          or (token.startswith("GPU-") and gpu["uuid"].startswith(token))) for token in tokens)


def _explicit(gpu):
    """The run named this GPU: CUDA_VISIBLE_DEVICES, or a --gpu/--gpu-uuid value of this process."""
    tokens = [token.strip() for token in os.environ.get("CUDA_VISIBLE_DEVICES", "").split(",")]
    argv = sys.argv[1:]
    for flag in ("--gpu", "--gpu-uuid"):
        tokens += [argv[i + 1] for i, value in enumerate(argv[:-1]) if value == flag]
        tokens += [value.split("=", 1)[1] for value in argv if value.startswith(flag + "=")]
    return _names(gpu, [token for token in tokens if token != "auto"])


def _explicit_large_4090(gpu):
    reserved = [token.strip() for token in os.environ.get("PCVE_GPU_RESERVED", DEFAULT_RESERVED).split(",")]
    return bool(RTX_4090.search(gpu["name"])) and _explicit(gpu) and not _names(gpu, reserved)


def _exception(gpu, case_id, record):
    if not record:
        return None
    data = json.loads(Path(record).read_text(encoding="utf-8"))
    if data.get("case_id") != case_id or data.get("gpu_uuid") != gpu["uuid"]:
        raise GpuPolicyError("Large-GPU memory evidence does not match this case and GPU UUID")
    required = float(data.get("required_memory_mib", 0))
    if not SMALL_CARD_CAPACITY_MIB < required < gpu["total_mib"] or not data.get("reason", "").strip():
        raise GpuPolicyError("A 48 GB GPU requires documented memory needs above a 24 GB card")
    proof = Path(data["evidence_path"]).resolve()
    if not any(parent.name == "_case_data" for parent in proof.parents) or case_id not in proof.parts:
        raise GpuPolicyError("Memory evidence must be retained in this case's _case_data directory")
    actual = hashlib.sha256(proof.read_bytes()).hexdigest()
    if actual != data.get("evidence_sha256"):
        raise GpuPolicyError("Memory evidence SHA-256 does not match")
    return {"record": str(Path(record).resolve()), "required_memory_mib": required,
            "reason": data["reason"], "evidence_sha256": actual}


def decision(gpu, case_id=None, exception_record=None):
    large = int(gpu["total_mib"]) >= LARGE_CARD_MIB
    if large and _explicit_large_4090(gpu):
        return {"policy_id": POLICY_ID, "gpu_uuid": gpu["uuid"], "gpu_name": gpu["name"],
                "total_mib": int(gpu["total_mib"]), "allowed": True, "priority": 2,
                "case_id": case_id, "memory_exception": None, "explicit_48gb_rtx_4090": True}
    evidence = _exception(gpu, case_id, exception_record) if large else None
    preferred = bool(re.search(r"\bRTX\s+3090\b", gpu["name"], re.I))
    return {"policy_id": POLICY_ID, "gpu_uuid": gpu["uuid"], "gpu_name": gpu["name"],
            "total_mib": int(gpu["total_mib"]), "allowed": not large or evidence is not None,
            "priority": 0 if preferred and not large else 2 if large else 1,
            "case_id": case_id, "memory_exception": evidence}


def rank_inventory(candidate_uuids, gpu_rows, case_id=None, exception_record=None):
    """Order already-idle candidates, without weakening the caller's idle checks."""
    by_uuid = {row["uuid"]: row for row in gpu_rows}
    ranked = []
    for position, uuid in enumerate(dict.fromkeys(candidate_uuids)):
        if uuid not in by_uuid:
            continue
        try:
            result = decision(by_uuid[uuid], case_id, exception_record)
        except GpuPolicyError:
            # Evidence for another large GPU must not prevent choosing a 3090.
            if int(by_uuid[uuid]["total_mib"]) < LARGE_CARD_MIB:
                raise
            continue
        if result["allowed"]:
            ranked.append((result["priority"], position, uuid))
    return [uuid for _, _, uuid in sorted(ranked)]


def rank_uuids(candidate_uuids, case_id=None):
    return rank_inventory(candidate_uuids, inventory(), case_id,
                          os.environ.get("PCVE_GPU_MEMORY_EXCEPTION"))


def require_gpu(uuid, case_id=None):
    if not uuid.startswith("GPU-") or "," in uuid:
        raise GpuPolicyError("Bind one inspected, stable GPU UUID before launch")
    rows = [row for row in inventory() if row["uuid"] == uuid]
    if len(rows) != 1:
        raise GpuPolicyError("Selected GPU UUID is absent from the current hardware query")
    result = decision(rows[0], case_id, os.environ.get("PCVE_GPU_MEMORY_EXCEPTION"))
    if not result["allowed"]:
        raise GpuPolicyError("Selected GPU is a 48 GB card; name it explicitly in CUDA_VISIBLE_DEVICES or --gpu (and ensure it is not in PCVE_GPU_RESERVED), or select a 24 GB GPU.")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("check", "rank", "eligible"))
    parser.add_argument("--gpu", nargs="+", default=[])
    parser.add_argument("--case-id")
    args = parser.parse_args()
    try:
        if args.action == "eligible":
            rows = inventory()
            result = rank_inventory([r["uuid"] for r in rows], rows, args.case_id,
                                    os.environ.get("PCVE_GPU_MEMORY_EXCEPTION"))
            print("PCVE_ALLOWED_GPU_UUIDS=" + json.dumps(result))
            return
        if args.action == "check":
            if len(args.gpu) != 1:
                raise GpuPolicyError("check requires exactly one GPU UUID")
            result = require_gpu(args.gpu[0], args.case_id)
        else:
            result = {"policy_id": POLICY_ID, "candidates": rank_uuids(args.gpu, args.case_id)}
        print(json.dumps(result, ensure_ascii=False))
    except GpuPolicyError as error:
        print(json.dumps({"policy_id": POLICY_ID, "refused": True, "reason": str(error),
                          "host": socket.gethostname()}))
        raise SystemExit(75)


if __name__ == "__main__":
    main()
