"""Launch one job of this scene on a GPU through scripts/pcve_worker_run.py (GPU/process preflight, per-GPU
lease, UUID binding); job records and lease locks go under the folder passed as work."""
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(REPO / 'scripts'))
from pcve_worker_run import main  # noqa: E402

if __name__ == '__main__':
    main(__file__, case_id='picnic_ground_blanket', work=REPO / '.runtime/picnic_ground_blanket/jobs', runs='canonical_launches')
