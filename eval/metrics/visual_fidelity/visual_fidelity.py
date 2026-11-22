# -*- coding: utf-8 -*-
"""Standard video metrics against the ground-truth edited video, for every prediction of the 533 cases and for the
unedited source video (the "no edit" reference): PSNR, SSIM, LPIPS per video, and I3D features for FVD.
Comparison at the ground-truth resolution (1280x720), prediction resized bilinearly; PSNR from the squared error pooled
over all compared frames; SSIM (Gaussian 11x11, sigma 1.5, data range 1) and LPIPS (AlexNet) averaged over frames; FVD
features from the Kinetics-400 I3D TorchScript (StyleGAN-V). Time alignment as in CF: every video is read on the 24 fps clock by timestamp (Wan 3.0 is
30 fps), Seedance (whole 4 s in 89 frames) is stretched to 96 frames, a shorter clip (Kiwi, 81 frames) is compared on
the frames it covers.   -> WORK/quality_out<OUTSUF>/<case>.json, WORK/quality_feat<OUTSUF>/<case>.npz
usage: CUDA_VISIBLE_DEVICES=g visual_fidelity.py WORK SHARD NSHARDS
environment: PHYCOVE_ROOT, PRED_ROOT, PRED_ROOT_REAL, I3D_CKPT (I3D TorchScript); EXTRA_MODELS / ONLY / OUTSUF for an
additional model on a case subset (written to separate output folders)"""
import json, os, sys, time
from pathlib import Path
import cv2
import numpy as np
import torch
import torch.nn.functional as Fn

T = Path(sys.argv[1]); shard, nsh = int(sys.argv[2]), int(sys.argv[3])
import lpips
REL = Path(os.environ.get("PHYCOVE_ROOT", "releases/PhyCoVE"))
ROOT = {"sim": REL, "real": REL / "real"}
PREDS = {"sim": Path(os.environ.get("PRED_ROOT", "predictions/PhyCoVE/quantitative_en")),
         "real": Path(os.environ.get("PRED_ROOT_REAL", "predictions/PhyCoVE/real/quantitative_en"))}
MODELS = ["joyai_video_edit", "kiwi_edit", "omniweaving", "kling4_0_video", "seedance25", "wan3_0_video", "minimax_h3", "void"] + [m for m in os.environ.get("EXTRA_MODELS", "").split(",") if m]
OUTSUF = os.environ.get("OUTSUF", "")
ONLY = {s for s in os.environ.get("ONLY", "").split(",") if s}
STRETCH = {"seedance25"}
NT = 96
dev = torch.device("cuda")
LP = lpips.LPIPS(net="alex", verbose=False).to(dev).eval()
I3D = torch.jit.load(os.environ["I3D_CKPT"]).eval().to(dev)


def load(path, size=None):
    cap = cv2.VideoCapture(str(path)); fps = cap.get(cv2.CAP_PROP_FPS) or 24.0; fr = []
    while True:
        ok, f = cap.read()
        if not ok:
            break
        fr.append(f)
    idx = []
    for k in range(NT):
        i = int(round(k * fps / 24.0))
        if i >= len(fr):
            break
        idx.append(i)
    if size is None:
        size = (fr[0].shape[1], fr[0].shape[0])
    out = []
    for i in idx:
        f = fr[i]
        if (f.shape[1], f.shape[0]) != size:
            f = cv2.resize(f, size, interpolation=cv2.INTER_LINEAR)
        out.append(cv2.cvtColor(f, cv2.COLOR_BGR2RGB))
    return np.stack(out), fps, len(fr)


def gauss_win(n=11, s=1.5):
    x = torch.arange(n, dtype=torch.float32) - (n - 1) / 2
    g = torch.exp(-x ** 2 / (2 * s * s)); g = g / g.sum()
    return (g[:, None] * g[None, :]).to(dev)


WIN = gauss_win()[None, None].repeat(3, 1, 1, 1)


def ssim_frames(a, b):
    """a, b (n,3,H,W) in [0,1] -> per-frame SSIM (torchmetrics default: Gaussian 11, sigma 1.5, valid region)"""
    C1, C2 = 0.01 ** 2, 0.03 ** 2
    conv = lambda x: Fn.conv2d(x, WIN, groups=3)
    mu_a, mu_b = conv(a), conv(b)
    saa = conv(a * a) - mu_a ** 2; sbb = conv(b * b) - mu_b ** 2; sab = conv(a * b) - mu_a * mu_b
    m = ((2 * mu_a * mu_b + C1) * (2 * sab + C2)) / ((mu_a ** 2 + mu_b ** 2 + C1) * (saa + sbb + C2))
    return m.flatten(1).mean(1)


@torch.no_grad()
def frame_metrics(p, g):
    n = min(len(p), len(g)); se, ss, lp = 0.0, [], []
    for i in range(0, n, 8):
        a = torch.from_numpy(p[i:min(i + 8, n)]).to(dev).permute(0, 3, 1, 2).float() / 255.0
        b = torch.from_numpy(g[i:min(i + 8, n)]).to(dev).permute(0, 3, 1, 2).float() / 255.0
        se += float(((a - b) ** 2).sum()); ss.append(ssim_frames(a, b)); lp.append(LP(a * 2 - 1, b * 2 - 1).flatten())
    mse = se / (n * p.shape[1] * p.shape[2] * 3)
    return {"psnr": float("inf") if mse == 0 else float(-10 * np.log10(mse)), "ssim": float(torch.cat(ss).mean()),
            "lpips": float(torch.cat(lp).mean()), "frames": int(n)}


@torch.no_grad()
def i3d(v):
    x = torch.from_numpy(v).to(dev).float().permute(3, 0, 1, 2).unsqueeze(0).contiguous()
    return I3D(x, rescale=True, resize=True, return_features=True).squeeze(0).double().cpu().numpy()


cases = []
for st, root in ROOT.items():
    for l in open(root / "metadata.jsonl", encoding="utf-8"):
        r = json.loads(l)
        if r.get("source_case_id"):
            cases.append((st, r))
if ONLY:
    cases = [(st, r) for st, r in cases if "__".join([st] + r["id"].split("/")) in ONLY]
cases = cases[shard::nsh]
(T / f"quality_out{OUTSUF}").mkdir(exist_ok=True); (T / f"quality_feat{OUTSUF}").mkdir(exist_ok=True)
for st, r in cases:
    s, k = r["id"].split("/"); name = f"{st}__{s}__{k}"
    if (T / f"quality_out{OUTSUF}" / f"{name}.json").exists():
        continue
    t0 = time.time()
    gt, _, _ = load(ROOT[st] / f"scenes/{s}/cases/{k}/video.mp4"); size = (gt.shape[2], gt.shape[1])
    src, _, _ = load(ROOT[st] / f"scenes/{s}/cases/source/video.mp4", size)
    res, feats = {}, {}
    res["source"] = frame_metrics(src, gt); feats["source"] = i3d(src[:len(gt)])
    feats[f"gt_{len(gt)}"] = i3d(gt)
    for m in MODELS:
        p = PREDS[st] / m / "videos" / s / f"{k}.mp4"
        if not p.exists():
            continue
        v, fps, nf = load(p, size)
        if m in STRETCH and 0 < len(v) < NT:
            L = len(v); v = v[np.round(np.arange(NT) * (L - 1) / (NT - 1)).astype(int)]
        res[m] = frame_metrics(v, gt); res[m].update(fps=fps, raw_frames=nf)
        n = res[m]["frames"]; feats[m] = i3d(v[:n])
        if f"gt_{n}" not in feats:
            feats[f"gt_{n}"] = i3d(gt[:n])
    np.savez_compressed(T / f"quality_feat{OUTSUF}" / f"{name}.npz", **feats)
    json.dump(res, open(T / f"quality_out{OUTSUF}" / f"{name}.json", "w"), indent=1)
    print(name, f"{time.time() - t0:.1f}s", flush=True)
