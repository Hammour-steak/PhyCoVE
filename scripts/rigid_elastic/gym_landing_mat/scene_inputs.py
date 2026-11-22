"""Resolved paths for native replay and production on the pool."""
from pcve_assets import asset
from scene_paths import DELIVERY

SCENE = "gym_landing_mat"
CASES = ("source","mass_double","faster","young_modulus_rebound","add_path_obstacle","delete_actor")
ASSETS = asset(f"scenes/{SCENE}")
FOLDERS = {case: "production_source" if case == "source" else case for case in CASES}

def accepted_case(case):
    revision = "rebound" if case == "young_modulus_rebound" else "whole_clip"
    return DELIVERY / revision / "delivery/cases" / FOLDERS[case]

def reference_main(case):
    """Camera and environment reference of the accepted render (ground_truth_transforms.json, environment_manifest.json)."""
    if case == "young_modulus_rebound":
        # The accepted render of this case used an earlier render of it as its reference.
        return ASSETS / "reference/young_modulus_rebound"
    return DELIVERY / "whole_clip/delivery/cases" / FOLDERS[case] / "main"
