"""PCVE edit vocabulary for honey_spoon_toast (standard library only).

`pcve_edit_dsl.make_prompts(parse(EDIT_DSL[case], VOCAB), VOCAB)` gives each edit's published prompts;
SOURCE_PROMPTS is the published description of the source video. The builder's case ids are the keys;
the published suite stores each edit as `edit_<case>`.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl  # noqa: E402

FPS = 24
FRAMES = 96
# Honey of the spoon reservoir (simulate_honey_reservoir.py --viscosity) and the two removable objects.
BASELINE_PHYSICS = {
    "honey_kinematic_viscosity_m2_s": 0.008,
    "honey_presence": [1],
    "bread_presence": [1],
}

OBJECTS = {
    "honey": {"zh": "勺子里的蜂蜜", "en": "the honey on the spoon"},
    "bread": {"zh": "吐司", "en": "the toast"},
}

PROPERTIES = {
    "viscosity": dsl.PropertySpec("scalar", "m^2/s", "运动黏度", "kinematic viscosity"),
}

VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties=PROPERTIES,
    sim_bindings={("honey", "viscosity"): dsl.SimBinding("honey_kinematic_viscosity_m2_s")},
    delete_bindings={"honey": dsl.DeleteBinding("honey_presence", 0), "bread": dsl.DeleteBinding("bread_presence", 0)},
    baseline_physics=BASELINE_PHYSICS,
    total_frames=FRAMES,
)

TIMED_REMOVAL_FRAME = 51

# Builder case id -> edit DSL.
EDIT_DSL = {
    "remove_bread": "DELETE bread",
    "remove_honey": "DELETE honey",
    "lower_viscosity": "SET honey.viscosity TIMES 0.0125",
    "remove_honey_at_frame_51": f"DELETE honey AT FRAME {TIMED_REMOVAL_FRAME}",
}

SOURCE_PROMPTS = {
    "vague": {
        "zh": "蜂蜜从固定的勺子前沿慢慢流出,先挂成一滴并被拉长,落到盘子里的吐司上,随后一条连续的细丝不断落下,在吐司上堆成一小摊并慢慢铺开。",
        "en": "Honey slowly runs over the front lip of a fixed spoon, hangs as a drop that stretches and falls onto a "
              "slice of toast on a plate, then a continuous thin thread keeps falling and builds a small mound that "
              "slowly spreads on the toast.",
    },
    "quantitative": {
        "zh": "勺子里约 14 mL、密度 1420 kg/m³、运动黏度 0.008 m²/s 的蜂蜜从倾斜 15° 的勺子前沿流出,拉成细丝落到吐司上,"
              "到结尾在吐司上堆成约 1.5 mL、高约 7 mm、半径约 12 mm 的一小摊。",
        "en": "About 14 mL of honey (1420 kg/m³, kinematic viscosity 0.008 m²/s) runs over the lip of a spoon tilted "
              "15°, stretches into a thread that lands on the toast, and by the end forms a mound of about 1.5 mL, "
              "about 7 mm high and 12 mm in radius.",
    },
}
