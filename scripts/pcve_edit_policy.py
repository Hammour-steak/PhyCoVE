"""Global PCVE edit policy: physical SET, genuinely new ADD, or DELETE.

The syntax parser keeps a separate read-only historical entry point. This
module is enforced by current parsing, override generation and packaging.
It does not reinterpret old files as compliant or certify solver correctness.
"""
from __future__ import annotations

import json
import re
from typing import Any

POLICY_ID = "pcve-physical-add-delete"
EFFECTIVE_DATE = "2026-10-15"

# New aliases must name one of these physical quantities explicitly through
# PropertySpec.physical_quantity; an unknown knob is never silently accepted.
QUANTITIES = {
    "mass", "density", "friction", "restitution", "young_modulus", "shear_modulus",
    "bulk_modulus", "poisson_ratio", "viscosity", "viscosity_scale", "damping",
    "stiffness", "bending_rigidity", "velocity", "angular_velocity", "force", "torque", "gravity",
    "pressure", "surface_tension",
}
_ALIASES = {
    "masses": "mass", "densities": "density", "frictions": "friction",
    "restitutions": "restitution", "viscosities": "viscosity",
    "velocities": "velocity", "speeds": "velocity", "stiffnesses": "stiffness",
    "elastic_modulus": "young_modulus", "youngs_modulus": "young_modulus",
    "coefficient_of_friction": "friction", "rolling_friction": "friction",
    "dynamic_friction": "friction", "static_friction": "friction",
    "coefficient_of_restitution": "restitution", "speed": "velocity",
    "initial_speed": "velocity", "initial_velocity": "velocity",
    "initial_linear_velocity": "velocity", "linear_velocity": "velocity",
    "initial_forward_velocity": "velocity", "initial_angular_velocity": "angular_velocity",
    "angular_speed": "angular_velocity", "initial_angular_speed": "angular_velocity",
    "spin_rate": "angular_velocity", "rotation_rate": "angular_velocity",
    "omega": "angular_velocity",
    "shear_viscosity": "viscosity", "bulk_viscosity": "viscosity",
    "kinematic_viscosity": "viscosity", "dynamic_viscosity": "viscosity",
    "damping_ratio": "damping", "damping_coefficient": "damping",
    "spring_stiffness": "stiffness", "tension": "force", "pretension": "force",
    # Thin-shell bending rigidity (N*m) differs from a linear spring (N/m).
    "bending_stiffness": "bending_rigidity",
}
_TRANSFORM_TOKENS = {
    "position", "positions", "pos", "location", "locations", "coordinate", "coordinates",
    "coord", "coords", "translation", "translate", "offset", "displacement", "depth",
    "height", "clearance", "placement", "pose", "orientation", "rotation", "rotate",
    "euler", "quaternion", "quat", "yaw", "pitch", "roll", "heading", "tilt", "angle",
    "azimuth", "elevation", "facing", "transform", "matrix", "worldmatrix", "mw",
    "scale", "scaling", "relocate", "reposition", "teleport", "xy", "xyz",
}
_CHINESE_TRANSFORMS = ("位置", "坐标", "位姿", "姿态", "朝向", "欧拉", "四元数", "平移", "旋转", "倾角", "角度", "释放高度", "落下高度", "缩放")


class EditPolicyError(ValueError):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(f"[{POLICY_ID}:{code}] {message}")


def normalized(value: Any) -> str:
    text = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", str(value))
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")


def forbidden_transform_name(value: Any) -> bool:
    text = str(value)
    name = normalized(value)
    # A genuine angular rate is a dynamic quantity, distinct from an angle.
    for rate in ("angular_velocity", "angular_speed", "rotation_rate", "spin_rate"):
        name = name.replace(rate, "physicalrate")
    # A multiplier of a constitutive coefficient is not an object transform.
    # Remove only this registered compound; any remaining pose alias rejects.
    name = name.replace("viscosity_scale", "physicalcoefficient")
    compact_alias = re.search(r"(?:position|location|orientation|quaternion|euler|matrixworld|dropheight|releaseheight|initialcompression|precompression)", name.replace("_", ""))
    short_alias = any(re.fullmatch(r"(?:pos|loc|rot|quat)[xyzw]", token) for token in name.split("_"))
    return bool(set(name.split("_")) & _TRANSFORM_TOKENS or compact_alias or short_alias or any(word in text for word in _CHINESE_TRANSFORMS))


def quantity_for_name(value: Any) -> str | None:
    name = normalized(value)
    if name in QUANTITIES:
        return name
    if name in _ALIASES:
        return _ALIASES[name]
    for alias in sorted((*QUANTITIES, *_ALIASES), key=len, reverse=True):
        if re.search(r"(?:^|_)" + re.escape(alias) + r"(?:_|$)", name):
            return _ALIASES.get(alias, alias)
    # Common formula notation is accepted only for the physical coefficient.
    if name in ("eta", "zeta", "mu_viscous"):
        return "viscosity"
    return None


def _same(first, second):
    return json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)


def _components(binding):
    return list(binding.components) if hasattr(binding, "components") else [binding]


def _slot(key, index=None):
    return str(key), index


def _overlap(first, second):
    return first[0] == second[0] and (first[1] is None or second[1] is None or first[1] == second[1])


def _object_slots(vocab, obj):
    slots = []
    slots.extend(_slot(item.key, item.index) for item in getattr(vocab, "object_parameters", {}).get(obj, ()))
    for (owner, _), binding in vocab.sim_bindings.items():
        if owner == obj:
            slots.extend(_slot(item.key, item.index) for item in _components(binding))
    if obj in vocab.geometry:
        geo = vocab.geometry[obj]
        slots.extend((_slot(geo.location_key, geo.location_index), _slot(geo.radius_key, geo.radius_index)))
    if obj in vocab.delete_bindings:
        item = vocab.delete_bindings[obj]
        slots.append(_slot(item.key, item.index))
    if obj in vocab.add_bindings:
        item = vocab.add_bindings[obj]
        slots.extend((_slot(item.presence_key, item.presence_index), _slot(item.location_key, item.location_index)))
        slots.extend(_slot(owner.key, owner.index) for owner in getattr(item, "owned_parameters", ()))
    return slots


def _presence_key(key):
    return bool(set(normalized(key).split("_")) & {"active", "present", "presence", "exists", "enabled"})


def _value_at(vocab, key, index):
    value = vocab.baseline_physics[key]
    return value[index] if index is not None else value


def _check_units(quantity, spec):
    unit = str(spec.unit).lower().replace(" ", "").replace("·", "*").replace("²", "2").replace("³", "3").replace("^", "")
    angular_unit = unit in ("deg", "degree", "degrees", "rad", "radian", "radians")
    if angular_unit:
        raise EditPolicyError("angle_is_pose", "An angle unit is a pose edit; angular velocity must use a rate such as rad/s.")
    if quantity == "velocity" and unit not in ("m/s", "cm/s", "mm/s", "km/h"):
        raise EditPolicyError("velocity_unit", "Linear velocity needs an explicit speed unit, not a position or direction angle.")
    if quantity == "angular_velocity" and unit not in ("rad/s", "deg/s", "rpm", "s-1", "1/s"):
        raise EditPolicyError("angular_velocity_unit", "Angular velocity needs an explicit angular-rate unit.")
    units = {
        "mass": {"kg", "g", "mg"}, "density": {"kg/m3", "g/cm3"},
        "friction": {"", "1", "dimensionless"}, "restitution": {"", "1", "dimensionless"},
        "poisson_ratio": {"", "1", "dimensionless"}, "viscosity_scale": {"", "1", "dimensionless"},
        "young_modulus": {"pa", "kpa", "mpa", "gpa"}, "shear_modulus": {"pa", "kpa", "mpa", "gpa"},
        "bulk_modulus": {"pa", "kpa", "mpa", "gpa"}, "pressure": {"pa", "kpa", "mpa", "gpa"},
        "viscosity": {"pa*s", "pas", "mpa*s", "kg/(m*s)", "m2/s", "mm2/s"},
        "stiffness": {"n/m", "kn/m"}, "damping": {"", "1", "dimensionless", "n*s/m", "kg/s", "1/s", "s-1"},
        "force": {"n", "kn"}, "torque": {"n*m", "nm"}, "gravity": {"m/s2"},
        "surface_tension": {"n/m", "mn/m"},
        "bending_rigidity": {"n*m", "nm"},
    }
    if quantity in units and unit not in units[quantity]:
        raise EditPolicyError("physical_unit_mismatch", f"{quantity!r} has incompatible/unregistered unit {spec.unit!r}.")


def validate_edit(edit, vocab=None):
    """Raise before a new edit can be constructed; return a small audit record."""
    kind = type(edit).__name__
    obj = edit.object_id
    if kind == "SetEdit":
        prop = edit.property_name
        if forbidden_transform_name(prop):
            raise EditPolicyError("existing_object_transform", f"SET {obj}.{prop} changes an existing object's position/pose or a transform alias.")
        spec = vocab.properties[prop] if vocab is not None else None
        declared = getattr(spec, "physical_quantity", None) if spec else None
        quantity = normalized(declared) if declared else quantity_for_name(prop)
        if quantity not in QUANTITIES:
            raise EditPolicyError("unclassified_parameter", f"SET {obj}.{prop} is not a registered physical quantity; classify a genuine physical quantity explicitly.")
        if spec:
            _check_units(quantity, spec)
            binding = vocab.sim_bindings[(obj, prop)]
            for item in _components(binding):
                if forbidden_transform_name(item.key):
                    raise EditPolicyError("transform_binding_alias", f"Physical label {prop!r} writes transform key {item.key!r}.")
                actual_quantity = quantity_for_name(item.key)
                if actual_quantity is None:
                    raise EditPolicyError("unclassified_binding", f"Physical label {prop!r} writes unclassified key {item.key!r}; use a physically named binding.")
                if actual_quantity != quantity and not (quantity == "viscosity_scale" and actual_quantity == "viscosity"):
                    raise EditPolicyError("physical_binding_mismatch", f"Physical label {prop!r} ({quantity}) writes {item.key!r} ({actual_quantity}).")
        return {"operation": "SET", "object_id": obj, "physical_quantity": quantity, "compliant": True}
    if vocab is None:
        raise EditPolicyError("presence_evidence_required", "ADD/DELETE needs a vocabulary proving source presence and parameter ownership.")
    if kind == "DeleteEdit":
        binding = vocab.delete_bindings[obj]
        if not _presence_key(binding.key) or binding.value_when_removed not in (0, False):
            raise EditPolicyError("delete_not_presence", "DELETE must deactivate an object's presence, not rename a mass or transform adjustment.")
        if not bool(_value_at(vocab, binding.key, binding.index)):
            raise EditPolicyError("delete_absent_object", f"DELETE target {obj!r} is absent in the source.")
        return {"operation": "DELETE", "object_id": obj, "compliant": True}
    if kind != "AddEdit":
        raise EditPolicyError("unsupported_operation", "Only physical SET, ADD and DELETE are permitted.")
    binding = vocab.add_bindings[obj]
    if not _presence_key(binding.presence_key) or binding.value_when_present not in (1, True):
        raise EditPolicyError("add_not_presence", "ADD must activate a previously absent body.")
    if bool(_value_at(vocab, binding.presence_key, binding.presence_index)):
        raise EditPolicyError("add_existing_object", f"ADD target {obj!r} already exists; it cannot be relocated under an ADD label.")
    if getattr(edit, "preset_name", None) is not None:
        if edit.endpoint_a is not None or edit.endpoint_b is not None or edit.anchor_id is not None:
            raise EditPolicyError("mixed_add_placement", "A baseline preset cannot carry caller-supplied endpoints or placement.")
        import pcve_edit_dsl as dsl
        try:
            parameters = dsl.add_preset_parameters(edit, vocab)
            signature = dsl.add_preset_signature(edit, vocab)
        except (ValueError, KeyError, TypeError) as error:
            raise EditPolicyError("add_preset_declaration", str(error)) from error
        if edit.preset_signature != signature:
            raise EditPolicyError("add_preset_changed", "The preset declaration changed after parsing or lacks its source signature.")
        if binding.location_index is not None or binding.location_key not in parameters:
            raise EditPolicyError("add_preset_location", "The preset must declare its exclusively owned whole location field.")
        protected = [slot for owner in vocab.objects if owner != obj for slot in _object_slots(vocab, owner)]
        owned = _object_slots(vocab, obj)
        writes = [_slot(binding.presence_key, binding.presence_index), *(_slot(key) for key in parameters)]
        for slot in writes:
            if any(_overlap(slot, old) for old in protected):
                raise EditPolicyError("add_mutates_existing_object", f"ADD preset claims existing-object slot {slot!r}.")
            if not any(_overlap(slot, own) for own in owned):
                raise EditPolicyError("add_preset_ownership", f"ADD preset field {slot!r} lacks explicit new-object ownership.")
        if binding.presence_key in parameters:
            raise EditPolicyError("add_preset_presence", "The pose preset must not override its separate activation slot.")
        if any(not _same(value, vocab.baseline_physics.get(key)) for key, value in binding.defaults):
            raise EditPolicyError("add_preset_defaults", "A preset activation changes presence only; all new-body defaults must already be baseline-declared.")
        try:
            dsl.add_location(edit, vocab)
        except (ValueError, KeyError, TypeError) as error:
            raise EditPolicyError("add_preset_location", str(error)) from error
        return {"operation": "ADD", "object_id": obj, "compliant": True,
                "placement_scope": "Immutable baseline preset of a new absent body; activation changes presence only",
                "preset": edit.preset_name, "preset_signature": signature}
    for endpoint in (edit.endpoint_a, edit.endpoint_b):
        presence = vocab.delete_bindings.get(endpoint)
        if presence is not None and not bool(_value_at(vocab, presence.key, presence.index)):
            raise EditPolicyError("add_absent_endpoint", f"ADD endpoint {endpoint!r} is absent in the source.")
        pending = vocab.add_bindings.get(endpoint)
        if pending is not None and not bool(_value_at(vocab, pending.presence_key, pending.presence_index)):
            raise EditPolicyError("add_absent_endpoint", f"ADD endpoint {endpoint!r} is absent in the source.")
    geo = vocab.geometry[obj]
    if _slot(binding.location_key, binding.location_index) != _slot(geo.location_key, geo.location_index):
        raise EditPolicyError("add_location_ownership", "ADD's location must belong to its new object's geometry anchor.")
    protected = [slot for owner in vocab.objects if owner != obj for slot in _object_slots(vocab, owner)]
    writes = [_slot(binding.presence_key, binding.presence_index), _slot(binding.location_key, binding.location_index)]
    for slot in writes:
        if any(_overlap(slot, old) for old in protected):
            raise EditPolicyError("add_mutates_existing_object", f"ADD writes existing-object slot {slot!r}.")
    owners = _object_slots(vocab, obj)
    for key, value in binding.defaults:
        baseline = vocab.baseline_physics.get(key)
        if _same(value, baseline):
            continue
        changed = [_slot(key, i) for i, (a, b) in enumerate(zip(baseline, value)) if not _same(a, b)] if isinstance(baseline, (list, tuple)) and isinstance(value, (list, tuple)) and len(baseline) == len(value) else [_slot(key)]
        for slot in changed:
            if any(_overlap(slot, old) for old in protected) or not any(_overlap(slot, own) for own in owners):
                raise EditPolicyError("add_default_ownership", f"ADD default {key!r} changes a source object or lacks explicit new-object ownership.")
    return {"operation": "ADD", "object_id": obj, "compliant": True,
            "placement_scope": "Initial placement of a new, baseline-absent body only"}


def allowed_override_keys(edit, vocab):
    kind = type(edit).__name__
    if kind == "SetEdit":
        return {item.key for item in _components(vocab.sim_bindings[(edit.object_id, edit.property_name)])}
    if kind == "DeleteEdit":
        return {vocab.delete_bindings[edit.object_id].key}
    item = vocab.add_bindings[edit.object_id]
    if getattr(edit, "preset_name", None) is not None:
        return {item.presence_key}
    return {item.presence_key, item.location_key, *(key for key, _ in item.defaults)}


def audit_scenario_override(edit, vocab, payload, source_payload=None):
    """Reject undeclared overrides and a transform hidden behind a legal DSL."""
    validate_edit(edit, vocab)
    source_payload = source_payload or {}
    if "physics" in payload:
        for key, value in payload.items():
            if key != "physics" and not _same(value, source_payload.get(key)):
                raise EditPolicyError("nonphysical_case_override", f"Case-specific nonphysics override {key!r} is not a physical/add/delete edit.")
        payload = payload["physics"]
    baseline = dict(vocab.baseline_physics)
    source_physics = source_payload.get("physics", source_payload)
    baseline.update(source_physics)
    # Generate the expected values, including unedited array slots. Checking
    # only top-level names would let SET A.mass also change B in the same list,
    # or ADD relocate an existing body through a shared locations array.
    import pcve_edit_dsl as dsl
    expected_values = dsl.to_physics_override(edit, vocab)
    expected = allowed_override_keys(edit, vocab)
    schedules = payload.get("timed_edits")
    blocks = [payload] if schedules is None else [item["params"] for item in schedules]
    declared_frame = getattr(edit, "at_frame", None)
    if declared_frame is not None and schedules is None:
        raise EditPolicyError("missing_schedule", "A declared timed edit must retain its actual schedule.")
    if schedules is not None:
        if declared_frame is None or set(payload) != {"timed_edits"} or len(schedules) != 1 or schedules[0].get("frame") != declared_frame:
            raise EditPolicyError("unexpected_schedule", "Timed overrides must describe the declared physical edit and its original frame.")

    def matches(key, actual, wanted):
        # Some scene adapters serialize a single presence slot as a bool;
        # that representation is equivalent only for that one presence slot.
        if _presence_key(key) and isinstance(actual, (bool, int)) and isinstance(wanted, (list, tuple)) and len(wanted) == 1:
            return actual == wanted[0]
        if isinstance(actual, (list, tuple)) and isinstance(wanted, (list, tuple)):
            return len(actual) == len(wanted) and all(matches(key, a, b) for a, b in zip(actual, wanted))
        if isinstance(actual, (int, float)) and not isinstance(actual, bool) and isinstance(wanted, (int, float)) and not isinstance(wanted, bool):
            # Numerically identical JSON numbers (1 versus 1.0) are equivalent;
            # no tolerance permits a second, undeclared intervention.
            return actual == wanted
        return _same(actual, wanted)

    for block in blocks:
        for key, value in block.items():
            if key in baseline and matches(key, value, baseline[key]):
                continue
            if key not in expected:
                raise EditPolicyError("undeclared_override", f"Declared {type(edit).__name__} also changes {key!r}; hidden placement/pose or unrelated changes are forbidden.")
            if not matches(key, value, expected_values[key]):
                raise EditPolicyError("override_value_mismatch", f"Actual {key!r} does not match the declared edit; unedited array slots and ADD ownership must remain unchanged.")
        for key, wanted in expected_values.items():
            if not matches(key, block.get(key, baseline.get(key)), wanted):
                raise EditPolicyError("declared_edit_not_applied", f"Actual override does not apply the declared value for {key!r}.")
    return {"scenario_override_checked": True, "allowed_parameter_keys": sorted(expected)}


def audit_suite_manifest(manifest, vocab, suite_root=None, historical=False):
    """Read existing metadata without producing new edits or changing old files."""
    from pathlib import Path
    import pcve_edit_dsl as dsl
    records = []
    source = {}
    if suite_root is not None:
        suite_root = Path(suite_root)
        path = suite_root / "cases" / manifest["source"]["case_id"] / "scenario_overrides.json"
        if path.is_file():
            source = json.loads(path.read_text(encoding="utf-8"))
    for record in manifest.get("edits", []):
        result = {"case_id": record["case_id"], "edit_dsl": record["edit_dsl"], "compliant": False}
        try:
            edit = (dsl.parse_for_historical_audit if historical else dsl.parse)(record["edit_dsl"], vocab)
            result.update(validate_edit(edit, vocab))
            if suite_root is not None:
                path = suite_root / "cases" / record["case_id"] / "scenario_overrides.json"
                if not path.is_file():
                    raise EditPolicyError("missing_override_evidence", f"New construction requires actual scenario overrides: {path}")
                result.update(audit_scenario_override(edit, vocab, json.loads(path.read_text(encoding="utf-8")), source))
        except (ValueError, KeyError, IndexError, TypeError) as error:
            result.update(compliant=False, violation=getattr(error, "code", "invalid_edit_metadata"), explanation=str(error))
        result["historical_current_policy_status"] = "historical_compliant_edit_category" if result["compliant"] else "historical_noncompliant"
        records.append(result)
    return {"policy_id": POLICY_ID, "effective_date": EFFECTIVE_DATE,
            "scene_id": manifest.get("scene_id"), "all_edits_compliant": all(item["compliant"] for item in records),
            "historical_files_changed": False, "edits": records,
            "parser_mode": "read_only_historical_parse" if historical else "current_normal_parse",
            "scope": "Metadata/binding/override policy audit only; actual source/edit state and shared-camera checks remain necessary."}
