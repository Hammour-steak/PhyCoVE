"""Read scene case IDs from Python syntax, without importing the implementation, and the provenance records a
rebuilt case keeps from the published one."""
from __future__ import annotations

import ast
import json
from pathlib import Path

# Records of a published case's provenance.json that a rebuilt case keeps: the standardization record (what the
# data normalization converted, with the tool and the new sha256) has no other source.
CARRIED_PROVENANCE = ("standardization",)


def carried_provenance(path) -> dict:
    """The CARRIED_PROVENANCE records of the provenance.json at path ({} when it is missing or has none)."""
    path = Path(path)
    if not path.is_file():
        return {}
    old = json.loads(path.read_text(encoding="utf-8"))
    return {key: old[key] for key in CARRIED_PROVENANCE if key in old}


def native_case_ids(folder: Path, scene: str) -> list[str]:
    """Extract SOURCE_CASE_ID and EDIT_CASES; fail rather than guess a case list."""
    values = {"SCENE_NAME": scene, "scene": scene}
    edits = None

    def literal(node):
        if isinstance(node, ast.Name) and node.id in values:
            return values[node.id]
        if isinstance(node, ast.JoinedStr):
            return "".join(str(literal(part.value)) if isinstance(part, ast.FormattedValue)
                           else part.value for part in node.values)
        return ast.literal_eval(node)

    for path in (folder / "scene_config.py", folder / "edit_vocab.py",
                 folder / f"build_pcve_{scene}.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if not isinstance(target, ast.Name):
                    continue
                if target.id in ("SCENE_NAME", "SOURCE_CASE_ID", "SOURCE"):
                    values["SOURCE_CASE_ID" if target.id == "SOURCE" else target.id] = literal(node.value)
                if target.id == "EDIT_CASES":
                    if (isinstance(node.value, ast.Attribute) and isinstance(node.value.value, ast.Name)
                            and node.value.value.id == "edit_vocab" and node.value.attr == "EDIT_CASES" and edits is not None):
                        continue
                    if not isinstance(node.value, (ast.List, ast.Tuple)):
                        raise ValueError(f"{path}: unsupported EDIT_CASES expression")
                    edits = []
                    for case in node.value.elts:
                        if isinstance(case, (ast.List, ast.Tuple)):
                            name = literal(case.elts[0])
                        elif isinstance(case, ast.Call) and isinstance(case.func, ast.Name) and case.func.id in ("EditCase", "_case"):
                            first = case.args[0] if case.args else next(k.value for k in case.keywords if k.arg == "case_id")
                            name = literal(first)
                        else:
                            raise ValueError(f"{path}: unsupported case expression")
                        if not isinstance(name, str):
                            raise ValueError(f"{path}: case ID must be a string")
                        edits.append(name)
    if "SOURCE_CASE_ID" not in values:
        sources = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Tuple) and len(node.elts) == 2
                    and isinstance(node.elts[1], ast.Constant) and node.elts[1].value is None
                    and isinstance(node.elts[0], ast.Constant) and isinstance(node.elts[0].value, str)):
                sources.add(node.elts[0].value)
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "source_id" for t in node.targets):
                sources.add(literal(node.value))
        if len(sources) == 1:
            values["SOURCE_CASE_ID"] = sources.pop()
    if "SOURCE_CASE_ID" not in values or edits is None:
        raise ValueError(f"{folder}: cannot locate SOURCE_CASE_ID / EDIT_CASES")
    result = [values["SOURCE_CASE_ID"], *edits]
    if len(set(result)) != len(result):
        raise ValueError(f"{folder}: duplicate case IDs")
    return result


def metadata_errors(root: Path, row: dict) -> list[str]:
    folder = root / row["directory"]
    entry = json.loads((folder / "entrypoints.json").read_text())
    manifest = json.loads((folder / "scene_manifest.json").read_text())
    expected = native_case_ids(folder, row["scene"])
    errors = []
    for label, actual in (("entrypoints.build_pcve.cases", entry["entrypoints"]["build_pcve"]["cases"]),
                          ("scene_manifest.supported_cases", manifest["supported_cases"])):
        if actual != expected:
            errors.append(f"{row['scene']}: {label} differs from native cases: {expected}")
    for case in expected:
        if f"`{case}`" not in (folder / "README.md").read_text():
            errors.append(f"{row['scene']}: README omits {case}")
    for role, spec in entry["entrypoints"].items():
        if manifest["entry_points"].get(role) != spec["file"]:
            errors.append(f"{row['scene']}: manifest entry mismatch: {role}")
    for path in entry.get("implementation_files", []):
        if not (folder / path).is_file():
            errors.append(f"{row['scene']}: missing implementation file {path}")
    for suite, data in manifest.get("canonical_suites", {}).items():
        if set(data.get("case_video_sha256", {})) != set(expected):
            errors.append(f"{row['scene']}: {suite} video case IDs differ from native cases")
        if Path(data["target"]).is_absolute():
            errors.append(f"{row['scene']}: suite target must be relative to repository root")
    return errors
