"""Read and export per-scene source/edit declarations without loading a solver.

``export_prompts`` updates the ``pcve_prompts/1`` files of an existing suite in
place (by default the build copy ``renders/<scene>/suite_build/pcve_<scene>_suite``;
the published suite only when its path is given): it reads each case's existing prompts.json and rewrites only the fields
the builder declares (prompts, edit_dsl, applies_from_frame,
application_time_sec, physics_override, physics_diff, availability and
prompt_provenance); every other field is kept as it is. The matching
suite_manifest.json record gets the same values for the keys it already
carries. Every file is copied to the archive before it is replaced.
"""
from __future__ import annotations

import argparse
import ast
import copy
import hashlib
import json
from pathlib import Path
import datetime

ROOT = Path(__file__).resolve().parents[1]
CONSTANTS = ("PCVE_SCENE", "PCVE_SOURCE", "PCVE_EDITS", "PCVE_EXECUTION")
FORMAT_VERSION = "pcve_prompts/1"
# Backups of replaced published files: <ARCHIVE_ROOT>/<scene>/<path inside the suite>.
ARCHIVE_ROOT = (ROOT / "renders/pcve_suites").resolve().parent / "pcve_suites_archive" / "prompt_export"
# Manifest record keys that mirror prompts.json; only keys a record already has are updated.
MANIFEST_MIRRORED = ("prompts", "edit_dsl", "applies_from_frame", "application_time_sec",
                     "physics_override", "physics_diff")


def has_catalog(builder):
    """Whether the builder assigns all four PCVE_* declarations at top level (parsed, not imported).

    Scenes that keep their cases in edit_vocab.EDIT_CASES have none; the shared entry point then
    does not offer --list-edits, --show-prompts or --export-prompts.
    """
    names = set()
    for node in ast.parse(Path(builder).read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            names.update(target.id for target in node.targets if isinstance(target, ast.Name))
    return set(CONSTANTS) <= names


def load_catalog(builder):
    builder = Path(builder).resolve()
    values = {}
    for node in ast.parse(builder.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in CONSTANTS:
                    values[target.id] = ast.literal_eval(node.value)
    missing = set(CONSTANTS) - values.keys()
    if missing:
        raise ValueError(f"Missing edit declarations in {builder}: {sorted(missing)}")
    catalog = {"scene": values["PCVE_SCENE"], "source": values["PCVE_SOURCE"],
               "edits": values["PCVE_EDITS"], "execution": values["PCVE_EXECUTION"]}
    validate_catalog(catalog)
    return catalog


def validate_catalog(catalog):
    # The number of edits is per scene; a scene declares at least one.
    assert len(catalog["edits"]) >= 1, "A scene declares at least one edit"
    catalog_ids = set()
    for kind, native_id, item in [("source", "source", catalog["source"]),
                                  *[("edit", key, value) for key, value in catalog["edits"].items()]]:
        assert item["case_id"] == native_id
        assert item["kind"] == kind
        catalog_id = item["catalog_case_id"]
        assert catalog_id not in catalog_ids
        catalog_ids.add(catalog_id)
        assert catalog_id == "source" if kind == "source" else catalog_id.startswith("edit_")
        for flavor in ("vague", "quantitative"):
            for language in ("zh", "en"):
                assert isinstance(item["prompts"][flavor][language], str)
                assert item["prompts"][flavor][language].strip()
        if kind == "edit":
            assert item["edit_dsl"].startswith(("SET ", "ADD ", "DELETE "))
            assert item["physics_override"]
            assert set(item["physics_override"]) == set(item["physics_diff"])
            for key, value in item["physics_override"].items():
                assert item["physics_diff"][key]["to"] == value
    return True


def edit_info(edits, case_id):
    """Return one explicit edit, accepting its native, CLI or catalog case ID."""
    for native, record in edits.items():
        if case_id in (native, record["catalog_case_id"], record["native_cli_case_id"]):
            return copy.deepcopy(record)
    raise ValueError(f"Unknown edit {case_id!r}; choices: {', '.join(edits)}")


def _records(catalog, selected=None):
    records = [catalog["source"], *catalog["edits"].values()]
    if selected is None:
        return records
    result = []
    for name in selected:
        item = catalog["source"] if name == "source" else edit_info(catalog["edits"], name)
        if item["catalog_case_id"] not in [x["catalog_case_id"] for x in result]:
            result.append(item)
    return result


def _hash(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(",", ":")).encode()).hexdigest()


def _dump(value):
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def _fps():
    contract = json.loads((ROOT / "scripts/benchmark_media_contract.json").read_text(encoding="utf-8"))
    return int(contract["fps"])


def _applies_from_frame(record):
    """The first edited frame, from the DSL's AT FRAME clause (1 without one)."""
    from pcve_edit_dsl import parse, starts_at_frame
    try:
        frame = starts_at_frame(parse(record["edit_dsl"]))
    except ValueError as error:
        raise ValueError(f"{record['catalog_case_id']}: edit_dsl does not parse: {error}") from error
    declared = record.get("applies_from_frame")
    if declared is not None and declared != frame:
        raise ValueError(f"{record['catalog_case_id']}: applies_from_frame {declared} disagrees with "
                         f"the edit_dsl, which starts at frame {frame}")
    return frame


def _backup(path, suite_root, archive, stamp):
    """Copy a file into the archive at its suite-relative path, keeping any earlier copy."""
    target = archive / path.relative_to(suite_root)
    data = path.read_bytes()
    if target.exists():
        if target.read_bytes() == data:
            return str(target)
        target = target.with_name(f"{target.name}.{stamp}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return str(target)


def _replace(path, text):
    temporary = path.with_name("." + path.name + ".writing")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)


def _published_root(scene):
    return (ROOT / "renders/pcve_suites" / f"pcve_{scene}_suite").expanduser().resolve()


def export_prompts(builder, root=None, selected=None, dry_run=False, archive_root=None):
    """Write the builder's declared prompts into the suite's existing pcve_prompts/1 files."""
    builder = Path(builder).resolve()
    catalog = load_catalog(builder)
    scene = catalog["scene"]
    if root is None:
        from pcve_project_paths import suite_output_root
        root = suite_output_root(scene)
    root = Path(root).expanduser().resolve()
    scripts = (ROOT / "scripts").resolve()
    if root == scripts or scripts in root.parents:
        raise ValueError("Export prompt sidecars under renders/, outside scripts/")
    if archive_root is not None:
        archive = Path(archive_root).expanduser().resolve() / scene
    elif root == _published_root(scene):
        archive = ARCHIVE_ROOT / scene
    else:
        archive = root.parent / f"{root.name}_prompt_export_backup"
    try:
        builder_name = builder.relative_to(ROOT).as_posix()
    except ValueError:
        builder_name = builder.as_posix()
    origin = "generated:" + builder_name
    fps = _fps()
    records = _records(catalog, selected)

    manifest_path = root / "suite_manifest.json"
    manifest_bytes = manifest_path.read_bytes() if manifest_path.is_file() else None
    manifest = json.loads(manifest_bytes) if manifest_bytes is not None else None
    if manifest is not None and manifest.get("scene") not in (None, scene):
        raise ValueError("Output suite belongs to another scene")
    manifest_entries = {}
    if manifest is not None:
        for entry in [manifest.get("source") or {}, *(manifest.get("edits") or [])]:
            if entry.get("case_id"):
                manifest_entries[entry["case_id"]] = entry

    plans, warnings = [], []
    manifest_changed = False
    for record in records:
        case = record["catalog_case_id"]
        case_dir = root / "cases" / case
        path = case_dir / "prompts.json"
        if not path.is_file():
            raise ValueError(f"{case}: no published prompts.json at {path}; "
                             "export updates existing pcve_prompts/1 files only")
        old_bytes = path.read_bytes()
        old = json.loads(old_bytes)
        if old.get("scene") not in (None, scene) or old.get("case_id") not in (None, case):
            raise ValueError(f"{path} belongs to {old.get('scene')}/{old.get('case_id')}, not {scene}/{case}")
        if old.get("kind") not in (None, record["kind"]):
            raise ValueError(f"{path} is a {old.get('kind')} case, the builder declares {record['kind']}")
        new = copy.deepcopy(old)
        for key, value in (("schema_version", 1), ("format_version", FORMAT_VERSION), ("scene", scene),
                           ("case_id", case), ("kind", record["kind"]), ("source_case_id", "source")):
            new.setdefault(key, value)
        new["availability"] = "available"
        new["prompts"] = copy.deepcopy(record["prompts"])
        if record["kind"] == "edit":
            frame = _applies_from_frame(record)
            new["edit_dsl"] = record["edit_dsl"]
            new["applies_from_frame"] = frame
            new["application_time_sec"] = (frame - 1) / fps
            new["physics_override"] = copy.deepcopy(record["physics_override"])
            new["physics_diff"] = copy.deepcopy(record["physics_diff"])
        else:
            new["edit_dsl"] = None
        text_changed = old.get("prompts") != new["prompts"]
        dsl_changed = (old.get("edit_dsl") or None) != (new.get("edit_dsl") or None)
        old_provenance = old.get("prompt_provenance") if isinstance(old.get("prompt_provenance"), dict) else {}
        provenance = dict(old_provenance)
        provenance["origin"] = origin
        provenance["text_modified"] = True if text_changed else bool(old_provenance.get("text_modified", False))
        new["prompt_provenance"] = provenance
        changed = sorted(key for key in set(old) | set(new) if old.get(key) != new.get(key))

        entry = manifest_entries.get(case)
        if manifest is not None and entry is None:
            warnings.append(f"{case}: no record in suite_manifest.json")
        elif entry is not None:
            if entry.get("native_case_id") not in (None, record["case_id"]):
                raise ValueError(f"{case}: suite_manifest native_case_id {entry.get('native_case_id')} "
                                 f"is not the builder's {record['case_id']}")
            for key in MANIFEST_MIRRORED:
                if key in entry and entry[key] != new.get(key):
                    entry[key] = copy.deepcopy(new.get(key))
                    manifest_changed = True

        plans.append({"case": case, "record": record, "path": path, "old_bytes": old_bytes,
                      "new": new, "changed": changed, "text_changed": text_changed,
                      "dsl_changed": dsl_changed})

    summary = [{"case_id": p["case"], "native_case_id": p["record"]["case_id"], "file": str(p["path"]),
                "status": "updated" if p["changed"] else "unchanged", "changed_fields": p["changed"],
                "text_modified": p["text_changed"], "edit_dsl_modified": p["dsl_changed"]} for p in plans]
    result = {"scene": scene, "out_root": str(root), "origin": origin, "archive": str(archive),
              "exported": summary, "manifest_updated": manifest_changed, "warnings": warnings}
    if dry_run:
        return {**result, "dry_run": True, "files": [str(p["path"]) for p in plans]}

    # Nothing is written if another writer changed any input after it was read.
    for p in plans:
        if p["changed"] and p["path"].read_bytes() != p["old_bytes"]:
            raise RuntimeError(f"{p['path']} changed while exporting; nothing written")
    if manifest_changed and manifest_path.read_bytes() != manifest_bytes:
        raise RuntimeError(f"{manifest_path} changed while exporting; nothing written")
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    backups = []
    for p in plans:
        if p["changed"]:
            backups.append(_backup(p["path"], root, archive, stamp))
            _replace(p["path"], _dump(p["new"]))
    if manifest_changed:
        backups.append(_backup(manifest_path, root, archive, stamp))
        _replace(manifest_path, _dump(manifest))
    return {**result, "backups": backups}


def catalog_cli(builder, values):
    parser = argparse.ArgumentParser(description="Inspect scene edits and bilingual prompts without importing a solver")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--list-edits", action="store_true")
    group.add_argument("--show-prompts", nargs="?", const="all", metavar="CASE")
    group.add_argument("--export-prompts", action="store_true")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--out-root", type=Path, help="Suite to update (default: renders/<scene>/suite_build/pcve_<scene>_suite; pass renders/pcve_suites/pcve_<scene>_suite to update the published suite)")
    output.add_argument("--out-parent", type=Path, help="Update pcve_<scene>_suite under this parent")
    parser.add_argument("--archive-root", type=Path, help=f"Backup root for replaced files (default for the published suite: {ARCHIVE_ROOT})")
    parser.add_argument("--cases", nargs="+")
    parser.add_argument("--dry-run", action="store_true")
    options = parser.parse_args(values)
    try:
        catalog = load_catalog(builder)
        if options.list_edits:
            result = {"scene": catalog["scene"], "edits": list(catalog["edits"].values()),
                      "execution": catalog["execution"]}
        elif options.show_prompts:
            selected = options.cases
            if options.show_prompts != "all":
                selected = [options.show_prompts]
            result = {"scene": catalog["scene"], "cases": _records(catalog, selected)}
        else:
            root = options.out_root
            if options.out_parent is not None:
                root = options.out_parent / f"pcve_{catalog['scene']}_suite"
            result = export_prompts(builder, root, options.cases, options.dry_run, options.archive_root)
    except (ValueError, AssertionError) as error:
        parser.error(str(error))
    print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
    raise SystemExit(0)

if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        print("usage: pcve_edit_catalog.py BUILDER.py (--list-edits | --show-prompts [CASE] | --export-prompts) "
              "[--out-root DIR | --out-parent DIR] [--archive-root DIR] [--cases ...] [--dry-run]")
        print("Validates PCVE_SCENE/PCVE_SOURCE/PCVE_EDITS/PCVE_EXECUTION in a scene builder without importing it.")
        raise SystemExit(0)
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    catalog_cli(sys.argv[1], sys.argv[2:])
