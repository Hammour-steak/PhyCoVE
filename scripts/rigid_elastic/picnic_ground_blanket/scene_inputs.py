"""Native inputs of every case: the accepted libuipc states, kept in the asset store.

assets/scenes/picnic_ground_blanket/native/<case>/ holds cache.npz (the 96 recorded native
samples), initial_state.npz (the common warm start the solve began from), simulation_config.json
and simulation_report.json. Render, GT export and verification read only these files.
native/add_path_obstacle/ holds a solved state outside the published cases; appearance/render_replay.py reads
its cloth track, because the static border-tuft layout of the published videos was derived from
all six accepted states.
"""
from pcve_assets import asset

SCENE = "picnic_ground_blanket"
CASES = ("source", "mass_double", "faster", "stiffer", "delete_actor")
# Timed edit: no accepted native folder in the asset store; its state is solved from the source state of frame 12
# (simulate --source-cache); the suite case keeps its solver and render records (cases/edit_mass_double_at_frame_12/native_metadata).
TIMED_CASES = ("mass_double_at_frame_12",)
ASSETS = asset(f"scenes/{SCENE}")
# Published suite case IDs.
CATALOG = {case: "source" if case == "source" else "edit_" + case for case in CASES + TIMED_CASES}


def native(case):
    """Directory with the accepted native state of one case."""
    if case not in CASES:
        raise ValueError(f"Unknown case {case!r}; choices: {', '.join(CASES)}")
    return ASSETS / "native" / case
