"""No-edit control: returns the source video unchanged as the "prediction".

This is a control, not a method. Two things it is for:

1. The zero point of Counterfactual Fidelity. CF measures the share of the
   source-to-target change a prediction reproduces, so a video that keeps the
   source scores 0 by definition.
2. The bound on what frame-level metrics can tell us. An edit changes a small
   part of the frame, so a video that changes nothing scores better on PSNR,
   SSIM, LPIPS and CLIP than any real editing method -- which is the reason
   those metrics cannot stand in for edit quality.

It also doubles as an end-to-end smoke test: it needs no GPU and no weights,
so it verifies run_baseline.py and the scorer without loading a model.
"""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from typing import Any

from .base import BaselineModel, BaselineResult


class NoEditBaseline(BaselineModel):
    name = "no_edit"

    def edit_video(
        self,
        source_video: Path,
        prompt: str,
        output_path: Path,
        *,
        edit_info: dict[str, Any],
    ) -> BaselineResult:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        t0 = time.perf_counter()
        shutil.copy2(source_video, output_path)
        return BaselineResult(
            output_video=output_path,
            elapsed_sec=time.perf_counter() - t0,
            extra={"note": "source copied verbatim; no editing performed"},
        )
