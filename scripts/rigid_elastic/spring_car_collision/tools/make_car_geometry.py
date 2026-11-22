"""Write the solver inputs of the toy car: body geometry (Blender) and the shared at-rest initial state (MuJoCo).

    # 1. body geometry from appearance/car_model.py (Blender 4.3.2)
    blender -b --factory-startup --python tools/make_car_geometry.py -- geometry --out DIR
    # 2. source at-rest initial state on that geometry (MuJoCo 3.3.7 runtime)
    PYTHONPATH=.runtime/spring_car_collision/deps .venv-rigid-elastic/bin/python tools/make_car_geometry.py initial --out DIR

Step 2 writes the frozen source_initial_state.json: the source case is
built without an initial state, the car is supported on its wheels by a zero-velocity static
solve, placed against the pusher at the exact first contact of its collision hull with the
pusher rectangle, held by the latch and the spring/contact balance is solved; no time step is
taken. Every case starts from this pose (simulate_spring_car_collision.py checks its hash).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CASE = HERE.parent
sys.path[:0] = [str(CASE / "appearance"), str(CASE / "physics"), str(CASE), str(CASE.parents[1])]
sys.dont_write_bytecode = True


def geometry(out):
    import bpy
    from car_model import build_car
    bpy.ops.wm.read_factory_settings(use_empty=True)
    car = build_car(bpy, None, export_dir=out)
    print(json.dumps({k: car["metadata"][k] for k in ("body_length_m", "body_width_m", "total_height_m",
                                                       "body_bbox_chassis_m", "body_vertices")}), flush=True)


def initial(out):
    from physics_model import Simulation, json_save, params_for_case
    import edit_vocab
    spec = edit_vocab.SPEC
    c = params_for_case("source", overrides={"simulation_dt_s": spec["production_dt_s_by_case"]["source"]},
                        geometry_contract=Path(out) / "car_geometry.json")
    sim = Simulation(c, None)
    json_save(Path(out) / "source_initial_state.json", sim.reference_initial_state)
    print(json.dumps({"car_x_m": sim.reference_initial_state["car"][0],
                      "contact": sim.nominal_contact_geometry,
                      "initial_spring_energy_j": sim.initial_spring_energy_j}, indent=1), flush=True)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    step, out = argv[0], Path(argv[argv.index("--out") + 1])
    {"geometry": geometry, "initial": initial}[step](out)


if __name__ == "__main__":
    main()
