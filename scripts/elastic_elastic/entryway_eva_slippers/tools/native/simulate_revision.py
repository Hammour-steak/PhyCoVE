"""Run the same native solver with the production edit vocabulary (vocab_revised.py)."""

from pathlib import Path

from common import save, sha
import vocab_revised as vocab
import simulate as solver


def record(path, value):
    if Path(path).name == "simulation_config.json":
        value["production_edit_binding"] = {
            "scene_spec_sha256": sha(vocab.SPEC_PATH),
        }
    save(path, value)


if __name__ == "__main__":
    solver.SPEC = vocab.SPEC
    solver.SPEC_PATH = vocab.SPEC_PATH
    solver.CASE_DSL = vocab.CASE_DSL
    solver.parameters = vocab.parameters
    solver.save = record
    solver.main()
