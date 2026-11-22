# PhyCoVE evaluation

This folder holds the code that produced the edited videos of the models in the
paper and the code that scores them. Each folder has its own README and
requirements.

| Folder | Content |
| --- | --- |
| [`models/`](models/README.md) | Model runners: one runner and one resumable parallel queue per model, the generic runner used for VOID and the no-edit control, and the model adapters in `models/baselines/`. |
| [`metrics/`](metrics/README.md) | Counterfactual Fidelity (CF) and Mask IoU on shared verified object tracks (`metrics/cf/`, `metrics/mask_iou/`, `metrics/common/`), and visual fidelity (PSNR, SSIM, LPIPS, FVD; `metrics/visual_fidelity/`). |
| [`judge/`](judge/README.md) | Multimodal judge for edit adherence (EA), physical commonsense (PC) and Joint. |
| [`human_study/`](human_study/README.md) | Pairwise human preference study: case panel, annotation interface, aggregation (HPWR, NWR, BTT) and agreement with the metrics. |

The models write their videos to `predictions/` next to the release (see
`models/README.md`); the scoring scripts read the release and these
predictions. The paper's reported results are summarized in the root
[`README.md`](../README.md).
