# PhyCoVE MLLM judge (EA, PC, Joint)

The judge is GPT-6 Astra at medium reasoning effort, called through the OpenAI
Responses API without tools. Each call receives contact sheets with every
decoded frame (labelled with frame number and time) and returns JSON with an
integer `score` from 1 to 5, `evidence`, and `limitation`.

- **EA** (edit adherence) sees the source, the edited ground truth, and the
  candidate, together with the English edit instruction and the onset time.
- **PC** (physical commonsense) sees only the candidate; for timed edits it
  starts at the onset frame.
- **Joint** counts a video as passing when both PC and EA are at least 4.

## Files

| File | Role |
|---|---|
| `inventory.py` | Lists every generated video with its source, ground truth, instruction, and onset (the manifest). |
| `evaluate.py` | EA prompt, output schema, EA frame sheets, OpenAI Responses API call, and the parallel loop over the manifest (PC and EA per video). |
| `full_frame_pc.py` | PC prompt and PC frame sheets; also runs on a single video. |
| `merge_results.py` | Merges the per-video records into `all_results.json`. |
| `aggregate_results.py` | Per-model PC and EA means, score distributions, pass rates, and Joint, overall, by split, and by edit type. |

The prompts are the constants `COMMON`, `PC`, and `EA` and the timing paragraph
built in `judge()` in `evaluate.py`, and `PROMPT` in `full_frame_pc.py`.

## Inputs

Run the scripts from the benchmark data root, which holds

- `releases/PhyCoVE/metadata.jsonl` and `releases/PhyCoVE/real/metadata.jsonl`,
  with the source and ground-truth videos they name;
- the generated videos as
  `predictions/PhyCoVE/quantitative_en/<model>/videos/<scene>/<case>.mp4`
  (real-video subset: `predictions/PhyCoVE/real/quantitative_en/...`).

Requirements: Python 3.9+, `pip install -r requirements.txt`, `ffprobe` (FFmpeg)
on the path, and `OPENAI_API_KEY` (with optional `OPENAI_BASE_URL`).
`PHYCOVE_JUDGE_MODEL` (default `gpt-6-astra`) and `PHYCOVE_JUDGE_EFFORT`
(default `medium`) select the judge.

## Order

```bash
cd /path/to/data_root
mkdir -p run
python /path/to/judge/inventory.py > run/manifest.json
python /path/to/judge/evaluate.py run/manifest.json . run/results --workers 3
python /path/to/judge/merge_results.py run
python /path/to/judge/aggregate_results.py run
```

## Outputs

- `run/results/<scene>__<case>__<model>__{PC,EA}.json`: judge, effort, prompt,
  answer (`score`, `evidence`, `limitation`), token usage, and frame counts.
- `run/all_results.json`: all records grouped by video.
- `run/model_performance.json`: per model, PC and EA means, score
  distributions, pass rates (score at least 4), and Joint pass rate, on all
  available outputs, on the cases common to all models, and per split.
- `run/model_performance_by_edit_type.json`: the same means and Joint for the
  Remove, Add, and Modify subsets.
