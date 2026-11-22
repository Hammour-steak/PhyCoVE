#!/usr/bin/env python3
"""Edit DSL vocabulary and benchmark prompts for the egg/dough edits.

`pcve_edit_dsl.make_prompts(parse(dsl, VOCAB), VOCAB)` reproduces the published
edit prompts; `--case-dir` writes one case's prompts.json from its native outputs.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from dough_config import write_json


SOURCE_CASE_ID = "source"
VOCAB = dsl.Vocabulary(
    objects={"egg": {"zh": "鸡蛋", "en": "the egg"}, "dough": {"zh": "面团", "en": "the dough"}},
    properties={"mass": dsl.PropertySpec("scalar", "kg", "质量", "mass"),
                "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus")},
    sim_bindings={("egg", "mass"): dsl.SimBinding("physics.ball.mass_kg"),
                  ("dough", "young_modulus"): dsl.SimBinding("physics.dough.E_Pa")},
    delete_bindings={"egg": dsl.DeleteBinding("present_egg", 0, 0), "dough": dsl.DeleteBinding("present_dough", 0, 0)},
    baseline_physics={"physics.ball.mass_kg": 0.065, "physics.dough.E_Pa": 6000.0, "present_egg": [1], "present_dough": [1]},
    total_frames=96)
# (native case, published case, edit DSL); every edit starts at t=0 from the source's settled dough.
EDIT_CASES = (
    ("soft_dough_e5", "edit_soft_dough_e5", "SET dough.young_modulus TIMES 0.2"),
    ("light_ball", "edit_light_egg", "SET egg.mass TIMES 0.5"),
    ("heavy_ball", "edit_heavy_egg", "SET egg.mass TIMES 2"),
    ("delete_egg", "edit_delete_egg", "DELETE egg"),
)
SOURCE_PROMPTS = {
    "vague": {
        "zh": "一个完整的褐壳鸡蛋从上方偏离中心落到案板上的一团面团上，陷进面团，翻倒后停在压出的凹坑里。",
        "en": "A whole brown egg drops off-centre onto a piece of dough on a pastry board, sinks in, tips over and settles in the dent it makes.",
    },
    "quantitative": {
        "zh": "一个长 60 mm、质量 65 g 的鸡蛋从约 13 cm 高处落到杨氏模量 6000 Pa 的面团上，把面团压下约 16 mm，翻转约 80 度后停在凹坑里。",
        "en": "A 60 mm, 65 g egg drops from about 13 cm onto dough with a Young's modulus of 6000 Pa, presses it down by about 16 mm, turns over by about 80 degrees and settles in the dent.",
    },
}
# Configuration field that each edit changes (cache keys still say "ball" for the egg).
FIELDS = {("egg", "mass"): ("physics", "ball", "mass_kg"),
          ("dough", "young_modulus"): ("physics", "dough", "E_Pa"),
          ("egg", None): ("physics", "ball", "present")}


def edit_definition(native_case):
    for native, public, text in EDIT_CASES:
        if native == native_case:
            edit = dsl.parse(text, VOCAB)
            key = (edit.object_id, getattr(edit, "property_name", None))
            return {"case_id": public, "edit_dsl": dsl.serialize(edit), "object_id": edit.object_id,
                    "applies_from_frame": dsl.starts_at_frame(edit), "field": FIELDS[key],
                    "prompts": dsl.make_prompts(edit, VOCAB)}
    raise KeyError(native_case)


def value_at(document, field):
    value = document
    for part in field:
        value = value.get(part) if isinstance(value, dict) else None
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--source-config", type=Path, required=True)
    args = parser.parse_args()
    case_dir = args.case_dir.resolve()
    simulation = case_dir / "simulation"
    actual = json.loads((simulation / "actual_config.json").read_text())
    acceptance = json.loads((simulation / "acceptance.json").read_text())
    source = json.loads(args.source_config.read_text())
    case = actual["case"]
    definition = edit_definition(case)
    before = value_at(source, definition["field"])
    after = value_at(actual, definition["field"])
    record = {
        "schema_version": 2,
        "case_id": definition["case_id"],
        "native_case_id": case,
        "source_case_id": SOURCE_CASE_ID,
        "edit_dsl": definition["edit_dsl"],
        "object_id": definition["object_id"],
        "applies_from_frame": definition["applies_from_frame"],
        "timing": "At t=0 from the exact common source dough state; the edit is active from frame 1.",
        "physics_diff": {
            ".".join(definition["field"][1:]): {
                "from": before if before is not None else True,
                "to": after,
            }
        },
        "prompts": definition["prompts"],
        "simulation_based_outcome": acceptance["metrics"],
        "numerical_acceptance": acceptance["status"],
        "initialization": actual.get("initialization"),
    }
    write_json(case_dir / "prompts.json", record)


if __name__ == "__main__":
    main()
