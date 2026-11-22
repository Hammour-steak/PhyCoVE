# PhyCoVE metrics: CF, Mask IoU, PSNR / SSIM / LPIPS / FVD

This folder holds the code that measures Counterfactual Fidelity (CF), Mask IoU
and the standard visual metrics of the generated videos. CF and Mask IoU share
one set of object tracks. Tracks are produced automatically (CoTracker3 point
tracks and SAM 2 masks, both seeded from the case annotations) and then checked
by hand against the videos; the hand verdicts and prompts of that verification
step are inputs to the scorer and are not included here (see "Inputs from the
verification step").

| Folder | Content |
|---|---|
| `common/` | Ground-truth reader and projection (`traj_lib.py`), shape and liquid quantities (`region_lib.py`), imported by the scripts below. |
| `cf/configs/` | Benchmark-side case configurations: liquid scenes/cases, later-frame execution times, real-video source/target prompts and regions, and edit-type labels. |
| `cf/tracking/` | Object tracks: seeds, CoTracker3 and SAM 2 runs, camera alignment, re-seeding, reference tracks, liquid regions, real-video tracks. |
| `cf/scoring/` | CF of the simulated and real-video cases, the later-frame step, and the pooling of both sets with Mask IoU. |
| `mask_iou/` | SAM 2 mask jobs along the verified CF tracks and the per-video Mask IoU. |
| `visual_fidelity/` | PSNR, SSIM, LPIPS per video and FVD per model. |

## Requirements

Python 3.9+ and `pip install -r requirements.txt`; a CUDA GPU for the tracking
and visual-fidelity scripts (the scoring scripts run on CPU). The following must
be obtained separately:

- SAM 2 (package `sam2`) and its hiera large checkpoint (`sam2_hiera_large.pt`,
  config `sam2_hiera_l.yaml`);
- CoTracker3 (package `cotracker`) and its offline checkpoint
  (`scaled_offline.pth`);
- the Kinetics-400 I3D TorchScript used for FVD (`i3d_torchscript.pt`, as
  distributed with StyleGAN-V);
- the LPIPS AlexNet weights (downloaded by the `lpips` package on first use).

## Data layout and environment

Run the scripts from the benchmark data root. Every script takes the working
directory `WORK` (where all intermediate files are written) as its first
argument. Locations are set by environment variables:

| Variable | Default | Content |
|---|---|---|
| `PHYCOVE_ROOT` | `releases/PhyCoVE` | `metadata.jsonl`, `scenes/<scene>/cases/{source,<case>}/{video.mp4,ground_truth_transforms.json}`, and the same under `real/` |
| `PRED_ROOT` | `predictions/PhyCoVE/quantitative_en` | generated videos `<model>/videos/<scene>/<case>.mp4` |
| `PRED_ROOT_REAL` | `predictions/PhyCoVE/real/quantitative_en` | the same for the real-video cases |
| `COTRACKER_REPO`, `COTRACKER_CKPT` | `co-tracker`, required | CoTracker3 code (added to the path) and checkpoint |
| `SAM2_CKPT`, `SAM2_CFG` | required, `sam2_hiera_l.yaml` | SAM 2 checkpoint and config |
| `I3D_CKPT` | required | I3D TorchScript for FVD |
| `NPROC` | 32 (`cf_real.py` 13, `ref_check.py` 40) | worker processes of the CPU scripts |

Conventions: cases are named `sim__<scene>__<case>` and `real__<scene>__<case>`;
the videos of a case are `source`, `gt` (the target video), the two re-encoded
reference copies `ref_gt_degraded` and `ref_source_degraded`, and one key per
model. All videos are read on a 24 fps clock by timestamp (at most 96 frames)
and tracked at 640x360; track coordinates are stored in 1280-px units. Scripts
with `SHARD NSHARDS` arguments process every NSHARDS-th case and are run once
per GPU. In the result files, `kq` is the CF of a video and `nkey` the number of
its scored quantities.

## Files

| File | Role |
|---|---|
| `common/traj_lib.py` | Reads the simulator ground truth and projects object origins into the image. |
| `common/region_lib.py` | Shape and liquid quantities, their thresholds and the per-quantity score. |
| `cf/tracking/seed_objects.py` | Seed points for every moving object of a simulated case, from the 3D ground truth. |
| `cf/tracking/track_seeds.py`, `track_refs_mild.py` | CoTracker3 tracks of the seeds in source, target and generated videos, and in the two re-encoded copies. |
| `cf/tracking/grid_tracks.py`, `cam_stats.py` | Grid tracks and per-video camera statistics (first-frame offset, background drift). |
| `cf/tracking/cam_retrack.py`, `cam_retrack2.py` | Alignment of generated videos whose first frame is shifted or zoomed (ECC; SIFT + ECC), and seed tracks in source-camera coordinates. |
| `cf/tracking/build_sam2_jobs.py`, `build_sam2_refs.py`, `build_sam2_extra.py` | SAM 2 prompts: main run, re-encoded copies, camera-aligned videos, hand prompts. |
| `cf/tracking/track_sam2.py` | SAM 2 video segmentation of a job file; stores centroids, areas, shape statistics and, for Mask IoU, the masks (`KEYS`). |
| `cf/tracking/validate_trackers.py` | Which tracker follows each object on the clean renders, checked against the projected 3D origin. |
| `cf/tracking/reseed.py`, `reseed2.py` | Re-finds objects that a generated video shows only later or elsewhere, and tracks them from there. |
| `cf/tracking/cut_detect.py` | Scene cuts inside generated videos (scored only up to the cut). |
| `cf/tracking/timed_prep.py`, `added_prep.py` | Objects removed at a later frame and objects added by an edit: frame and true position. |
| `cf/tracking/liquid_regions.py` | Liquid regions by change detection: amount, pool and stream per frame. |
| `cf/tracking/refman.py`, `ref_check.py`, `refman2.py` | Reference tracks from SAM 2 prompted at the true 3D position, for objects no tracker followed or whose reference track lost the object, with their validation. |
| `cf/tracking/real_blobs.py`, `real_jobs.py`, `real_pick.py` | Real-video cases: moving-region boxes for the hand annotation, SAM 2 jobs from the annotations, and the verified prediction tracks. |
| `cf/scoring/cf_sim.py` | CF of every generated video on the simulated cases. |
| `cf/scoring/cf_later_frames.py` | Time-graded CF for edits that take effect at a later frame. |
| `cf/scoring/cf_real.py` | CF on the real-video cases. |
| `cf/scoring/cf_pool.py` | Pools both sets: per-video CF and Mask IoU, model means overall and by edit type, reliability check, paired bootstrap. |
| `mask_iou/mask_jobs.py`, `mask_jobs_ref.py` | SAM 2 mask jobs along the verified CF tracks (generated and target videos; source video and re-encoded target as references). |
| `mask_iou/mask_iou.py` | Per-video Mask IoU against the target video, and the two references. |
| `visual_fidelity/visual_fidelity.py`, `visual_fidelity_agg.py` | PSNR, SSIM, LPIPS per video and FVD per model against the target video. |

## Order

`M` is the path of this folder (`eval/metrics`); the commands run from the
benchmark data root. Simulated cases (`i` = shard index, `N` = number of shards):

```bash
mkdir -p $WORK && cp $M/cf/configs/*.json $WORK/
python $M/cf/tracking/seed_objects.py $WORK
python $M/cf/tracking/track_seeds.py $WORK i N;  python $M/cf/tracking/track_refs_mild.py $WORK i N
python $M/cf/tracking/grid_tracks.py $WORK i N;  python $M/cf/tracking/cam_stats.py $WORK
python $M/cf/tracking/cam_retrack.py $WORK i N;  python $M/cf/tracking/cam_retrack2.py $WORK i N
python $M/cf/tracking/build_sam2_jobs.py $WORK;  python $M/cf/tracking/build_sam2_refs.py $WORK
python $M/cf/tracking/build_sam2_extra.py $WORK cam;  python $M/cf/tracking/build_sam2_extra.py $WORK man
for J in sam2_jobs.json sam2_jobs_ref.json sam2_jobs_cam.json sam2_jobs_man.json; do
  KEYS=ca  OUTDIR=sam2_tracks python $M/cf/tracking/track_sam2.py $WORK i N $J   # positions
  KEYS=cas OUTDIR=sam2_shape  python $M/cf/tracking/track_sam2.py $WORK i N $J   # + shape statistics
done
python $M/cf/tracking/validate_trackers.py $WORK;  python $M/cf/tracking/cut_detect.py $WORK
python $M/cf/tracking/timed_prep.py $WORK;  python $M/cf/tracking/added_prep.py $WORK
python $M/cf/tracking/liquid_regions.py $WORK liquid_cases.json
python $M/cf/tracking/refman.py $WORK jobs
KEYS=cas OUTDIR=sam2_refman python $M/cf/tracking/track_sam2.py $WORK i N sam2_jobs_refman.json
python $M/cf/tracking/refman.py $WORK validate
DUMPTRACK=1 python $M/cf/scoring/cf_sim.py $WORK _pass1          # first pass: absent_t0 flags, tracks_used/
python $M/cf/tracking/reseed.py $WORK cf_sim_detail_pass1.json i N > reseed_i.log
python $M/cf/tracking/reseed2.py $WORK i N reseed_*.log
python $M/cf/tracking/ref_check.py $WORK;  python $M/cf/tracking/refman2.py $WORK jobs
KEYS=cas OUTDIR=sam2_refman2 python $M/cf/tracking/track_sam2.py $WORK i N sam2_jobs_refman2.json
python $M/cf/tracking/refman2.py $WORK validate
# verification by hand (see below), then the final runs:
DUMPTRACK=1 python $M/cf/scoring/cf_sim.py $WORK _main
ONLY=<later-frame cases> DUMPREF=1 DUMPTRACK=1 DUMPTRACK_REFS=1 DUMPTRACK_DIR=tracks_pre \
  python $M/cf/scoring/cf_sim.py $WORK _later
python $M/cf/scoring/cf_later_frames.py $WORK _main _final _later
```

Real-video cases:

```bash
python $M/cf/tracking/real_blobs.py $WORK                # boxes referenced by the hand prompts
python $M/cf/tracking/real_jobs.py $WORK ref
KEYS=cas OUTDIR=sam2_real python $M/cf/tracking/track_sam2.py $WORK i N sam2_jobs_realref.json
python $M/cf/tracking/real_jobs.py $WORK pred
KEYS=cas OUTDIR=sam2_realpred python $M/cf/tracking/track_sam2.py $WORK i N sam2_jobs_realpred.json
python $M/cf/tracking/real_pick.py $WORK                 # verified prediction tracks
python $M/cf/scoring/cf_real.py $WORK _final
```

Mask IoU, pooling and visual fidelity:

```bash
python $M/mask_iou/mask_jobs.py $WORK _final _final
KEYS=casm OUTDIR=sam2_mask python $M/cf/tracking/track_sam2.py $WORK i N sam2_jobs_mask.json
python $M/mask_iou/mask_jobs_ref.py $WORK
KEYS=casm OUTDIR=sam2_mask_ref python $M/cf/tracking/track_sam2.py $WORK i N sam2_jobs_mask_ref.json
python $M/mask_iou/mask_iou.py $WORK cf_sim_detail_final.json cf_real_final.json
REFS=1 python $M/mask_iou/mask_iou.py $WORK cf_sim_detail_final.json cf_real_final.json
python $M/cf/scoring/cf_pool.py $WORK/cf_sim_final.json $WORK/cf_real_final.json edit_types.json \
  $WORK/mask_iou_videos.json $WORK/mask_iou_refs.json results
python $M/visual_fidelity/visual_fidelity.py $WORK i N
python $M/visual_fidelity/visual_fidelity_agg.py $WORK
```

## Outputs

- `cf_sim<SUFFIX>.json`, `cf_real<SUFFIX>.json`: per case, the CF (`kq`) and
  number of scored quantities (`nkey`) of every video, including the two
  re-encoded references, and whether the case is valid (at least one quantity
  passes the reference check). `cf_sim_detail<SUFFIX>.json` and the `detail`
  field of the real results list every scored object with its quantities,
  scores, trajectory source and penalties.
- `results/all_results.json`, `results/model_performance.json`,
  `results/unscored_cases.json` (`cf_pool.py`): per-video CF and Mask IoU,
  model means overall and by edit type, the reliability check, and the paired
  bootstrap on the cases common to the seven editing models.
- `mask_iou_videos.json`, `mask_iou_refs.json`: Mask IoU per video and of the
  two references per case.
- `quality_summary.json`: PSNR, SSIM, LPIPS per video and per case for the
  source video, and FVD per model.

## Benchmark configs and optional verification inputs

The benchmark-side static configs (`liquid_scenes.json`, `liquid_cases.json`,
`later_frames.json`, `real_prompts.json`, `real_valid.json`, `real_regions.json`,
and `edit_types.json`) are included in `cf/configs/` and copied into `$WORK`
before running. All other files below are optional prediction-side verification
records written when checking a model's tracks by hand against its videos:

- `manual_prompts.json`: SAM 2 prompts placed by hand,
  `{"<case>|<video>|<obj>": [{"t", "pos", "neg"}]}`.
- `manual_tracks.json`: verdict per (case, model, object),
  `{"<case>|<model>|<obj>": {"verdict": ...}}` with `absent` (the video does
  not show the object, -1), `exclude` (not measurable), `as_source` / `as_gt`
  (the object visibly moves as in the source / target video but no track holds),
  `ct` / `s2` (use this tracker), `sam2` (use the hand-prompted SAM 2 run).
- `sam2_tracks/<case>__man.npz`, `sam2_shape/<case>__man.npz`: SAM 2 runs from
  hand prompts, including the tracks picked among candidates.
- `reloc_W.json`: `{"<case>|<model>": {"W": 2x3}}`, the similarity (source to
  prediction, fitted at the first frames from hand-prompted masks) for generated
  videos with a changed viewpoint.
- `camera_manual.txt`: lines `CAM <case> <model>` (camera change seen by eye,
  not scored) and `UNRECOGNIZABLE <case> <model>` (scene not recognisable, every object
  scores -1).
- `presence_manual.json`: `{"<case>|<model>|<obj>": {"value": 0..1}}`, presence
  of an added object judged by eye.
- `liquid_scenes.json`: per scene `{"mode": "pour" | "body", "exclude": [[x0, y0,
  x1, y1], ...]}` (640x360 px), and `liquid_cases.json`, the list of cases with
  pouring or spilling liquid.
- Entries added by hand to `cuts.json` (scene cuts) and `timed_targets.json` (a
  removed object hidden from the first frame, `td` = 0); the object lists `C`
  and `BOXALL` in `cf/tracking/refman.py`.
- `later_frames.json`: `{case: execution frame (1-based)}` for the edits that
  take effect at a later frame; `later_frames_manual.json` with
  `absent_frames` (`{case: {model: frames before the execution frame in which a
  removed object is already gone}}`) and `liquid_gate` (`{case: models whose
  liquid departs from the source before the execution frame}`).
- Real-video cases: `real_prompts.json` (prompts per take and object: `["p", t,
  x, y]` point, `["b", t, i]` box `i` of `real_blobs/`, `["x", t, x0, y0, x1, y1]`
  box; `obj~k` adds a prompt segment to `obj`), `real_valid.json` (frame range per
  take and object), `real_regions.json` (fixed boxes for presence and water-flow
  keys), `real_manual.json` (`absent` / `exclude`, and `present_as_source` /
  `absent_as_gt` for removed or added objects and water streams),
  `real_pred_prompts.json`, `realcand_list.json`, `real_pred_picks.json` and
  the candidate runs they refer to (`sam2_realcand/`, `sam2_realmc/`,
  `sam2_realhand/`).
- `edit_types.json` for `cf_pool.py`: a list of `{"split", "scene", "case",
  "edit_type"}` with `edit_type` in Remove / Add / Modify.
