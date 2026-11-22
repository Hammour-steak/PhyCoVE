"""Current physical edits and exact input/derived configuration differences."""

CASES = ["source", "soft_spring", "stiff_spring", "heavy_ball", "delete_spring"]
ELASTIC_FIELDS = {
    "case",
    "physics.spring.young_modulus_Pa",
    "physics.spring.shear_modulus_Pa",
    "physics.spring.axial_stiffness_N_m",
}
EDIT_FIELDS = {
    "source": set(),
    "soft_spring": ELASTIC_FIELDS,
    "stiff_spring": ELASTIC_FIELDS,
    "heavy_ball": {
        "case",
        "physics.pendulum.ball_mass_kg",
        "physics.pendulum.ball_density_kg_m3",
        "physics.pendulum.ball_inertia_cm_kg_m2",
        "physics.pendulum.hinge_inertia_kg_m2",
    },
    "delete_spring": {"case", "physics.spring.present"},
}


def apply_preset(config, case):
    """Edit independent inputs; scene_config recomputes all dependent values."""
    if case not in CASES:
        raise ValueError(case)
    config["case"] = case
    if case == "soft_spring":
        config["physics"]["spring"]["young_modulus_Pa"] /= 10
    if case == "stiff_spring":
        config["physics"]["spring"]["young_modulus_Pa"] *= 10
    if case == "heavy_ball":
        config["physics"]["pendulum"]["ball_mass_kg"] *= 2
        config["physics"]["pendulum"]["ball_density_kg_m3"] *= 2
    if case == "delete_spring":
        config["physics"]["spring"]["present"] = False


def diff(before, after, prefix=""):
    """Return nonempty before/after values for every changed dotted field."""
    result = {}
    if isinstance(before, dict) and isinstance(after, dict):
        for key in sorted(set(before) | set(after)):
            name = prefix + "." + key if prefix else key
            if key in before and key in after:
                result.update(diff(before[key], after[key], name))
            else:
                result[name] = {"before": before.get(key), "after": after.get(key)}
    elif before != after:
        result[prefix] = {"before": before, "after": after}
    return result
