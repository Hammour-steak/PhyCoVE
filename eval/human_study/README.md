# PhyCoVE human preference study

Blinded pairwise comparison of edited videos. An annotator sees the source
video, the edited ground truth and two anonymous candidates (A and B), and
answers one question: which candidate better completes the physical editing
task (A is better, about the same, B is better). The annotator votes (the
`annotations.jsonl` file) are not included in this release.

Requirements: Python 3.9+ and `pip install -r requirements.txt` (NumPy and
SciPy, used by `build_panel.py` and `aggregate.py`). `serve.py` uses only the
standard library and needs a Unix system (`fcntl`).

## 1. Case pool: `build_study.py`

Input is a manifest with one row per generated video (the format written by
`../judge/inventory.py`; media paths are relative to the data root).
`--all-common` keeps every case covered by all seven main models and creates
every pair of main models for it; the limited model (VOID) is paired only on
Remove cases. The interaction category of each case is read from the release
metadata under `--data-root`.

```bash
python build_study.py --manifest manifest.json --data-root /path/to/data_root \
  --output pool/study.json --all-common --verify-media
```

## 2. Panel: `build_panel.py`

Selects the 71 cases of the study (24 Remove, 15 Add, 32 Modify, with fixed
quotas per interaction category, real videos and timed edits, at most one case
per scene within an edit type and split) with a seeded integer program. Each
case gets the seven model pairs of one of three Hamiltonian cycles over the
seven models, so the 21 pairs are covered evenly; three extra pairs on one
Modify case bring the total to 500 comparisons. Each comparison goes to 3 of 10 raters (`R01` to `R10`), 150 per
rater, balanced by edit type, real videos and timed edits; the A/B sides
alternate. The default seed is `20261117`.

```bash
python build_panel.py --source-study pool/study.json --output-dir panel --seed 20261117
```

This writes `panel/study.json` and `panel/assignment_plan.json`.

## 3. Interface: `serve.py`

```bash
python serve.py --study panel/study.json --assignment-plan panel/assignment_plan.json \
  --data-root /path/to/data_root --annotations panel/annotations.jsonl
```

Open the printed address (port 8090 by default) in a browser and enter a rater code. The page (`static/`)
shows the four videos and the instruction, and enables the vote only after
each video has been played to the end or to at least 90% of its length. Model
names never reach the browser. Only a study-specific hash of the rater code is
stored, and "Media cannot be played" is recorded as a technical issue, not as a
vote.

## 4. Aggregation: `aggregate.py`

```bash
python aggregate.py --study panel/study.json --annotations panel/annotations.jsonl \
  --output-dir panel/results --bootstrap 1000 --seed 4090
```

With W, T and L the weighted wins, ties and losses of a model,

- HPWR = (W + 0.5 T) / (W + T + L) x 100,
- NWR = 2 HPWR / 100 - 1,
- BTT is the Rao-Kupper (Bradley-Terry with ties) strength, scaled so that the
  leader of each subset has 100.

In the overall ranking every vote is weighted by its edit type so that Remove,
Add and Modify count in proportion to their share of the full benchmark. The
per-edit-type rankings are unweighted. The 95% intervals come from 1000
bootstrap resamples of cases (all comparisons of a case stay together), with
seed 4090 for the overall ranking and 4091, 4092 and 4093 for Remove, Add and
Modify. The output also reports tie rate, left-choice rate and Fleiss' kappa.

## 5. Agreement with the metrics: `agreement.py`

```bash
python agreement.py values.json
```

Prints Kendall tau-b and Spearman rho between each metric and HPWR across the
models; the input format is described at the top of the script.
