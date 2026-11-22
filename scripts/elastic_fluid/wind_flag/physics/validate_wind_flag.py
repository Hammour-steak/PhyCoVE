"""Validate actual FEM inputs, aligned states, contact evidence and all videos."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
from pathlib import Path
import numpy as np
from wind_flag_config import ASSETS, SOURCE_ID, CASE_MAP, CASE_E, CASE_WIND_SPEED, SPEC, digest, read_json, write_json
from render_wind_flag import verify_video


def flatten(value, prefix=""):
    out={}
    if isinstance(value,dict):
        for key,item in value.items():
            out.update(flatten(item,f"{prefix}.{key}" if prefix else key))
    else:
        out[prefix]=value
    return out


def validate(out_root, assets=ASSETS, selected=None):
    ids=selected or list(CASE_MAP)
    manifest=read_json(assets/"asset_manifest.json")
    source=np.load(out_root/"cases"/SOURCE_ID/"simulation/genesis_flag_cache.npz")
    conf0=read_json(out_root/"cases"/SOURCE_ID/"simulation/resolved_config.json")
    approved_source=read_json(assets/"approved/source/simulation/resolved_config.json")
    assert conf0["physics"]==approved_source["physics"] and conf0["quality"]==approved_source["quality"]
    results={}
    imported=True
    appearances=set()
    for case_id in ids:
        native=CASE_MAP[case_id]
        case=out_root/"cases"/case_id
        data=np.load(case/"simulation/genesis_flag_cache.npz")
        conf=read_json(case/"simulation/resolved_config.json")
        report=read_json(case/"simulation/simulation_report.json")
        assert conf["case"]==native
        assert conf["quality"]==conf0["quality"]
        assert conf["quality"]["frames"]==96 and conf["quality"]["fps"]==24
        assert conf["quality"]["nx"]==61 and conf["quality"]["nz"]==41 and conf["quality"]["steps_per_frame"]==8
        assert conf["initial_state_sha256"]==conf0["initial_state_sha256"]
        assert conf["physics"]["material"]["E_Pa"]==CASE_E[native]
        assert conf["physics"]["flag_geometry"]=={"width_m":SPEC["physics"]["flag_width_m"],
            "height_m":SPEC["physics"]["flag_height_m"],"top_z_m":SPEC["physics"]["flag_top_z_m"]}
        pins=data["rest_positions"][data["pinned"]]
        assert np.isclose(pins[:,2].max(),3.63,atol=1e-9)
        assert np.isclose(pins[:,2].min(),2.63,atol=1e-9)
        for key in ("faces","physical_faces","uvs","pinned","rest_positions"):
            assert np.array_equal(data[key],source[key]),(case_id,key)
        for key in ("physical_positions","physical_velocities","vertices"):
            assert data[key].shape==(96,2501,3) and np.isfinite(data[key]).all(),(case_id,key)
            assert np.array_equal(data[key][0],source[key][0]),(case_id,key,"t0")
        assert report["max_all_step_pin_drift_m"]<1e-6
        assert report["min_all_step_triangle_pole_proxy_gap_m"]>0
        if native!="wind_drop_at_2s":
            assert report["native_force_callback_count"]>=760
        before,after=flatten(conf0["physics"]),flatten(conf["physics"])
        changes={k:{"before":before[k],"after":after[k]} for k in before if before[k]!=after[k]}
        expected=set()
        if native in ("flow_6mps","flow_0p5mps","flow_0mps"):
            expected={"air.reference_speed_m_s"}
            assert conf["physics"]["air"]["reference_speed_m_s"]==CASE_WIND_SPEED[native]
            if native in ("flow_0p5mps","flow_0mps"):
                assert len(report["measurements"])==96
                assert all(m["wind_reference_speed_m_s"]==CASE_WIND_SPEED[native] for m in report["measurements"])
        elif native=="young_stiff":
            expected={"material.E_Pa","material.bending_kappa_Nm_derived","material.native_mu_min_max_Pa",
                      "material.native_lambda_min_max_Pa","material.native_kappa_min_max_Nm"}
            m0,m1=conf0["physics"]["material"],conf["physics"]["material"]
            for k in ("bending_kappa_Nm_derived","native_mu_min_max_Pa","native_lambda_min_max_Pa","native_kappa_min_max_Nm"):
                assert np.allclose(np.asarray(m1[k])/np.asarray(m0[k]),100)
        elif native=="wind_drop_at_2s":
            expected={"air.event_at_2s_m_s"}
            assert conf["physics"]["air"]["event_at_2s_m_s"]==.5
            for key in ("physical_positions","physical_velocities","vertices"):
                assert np.array_equal(data[key][:49],source[key][:49]),(case_id,"timed prefix",key)
            assert "World.dump/recover" in report["continuation_method"]
        assert set(changes)==expected,(case_id,changes)
        contact=read_json(case/"contact_audit.json")
        item=contact["cases"].get(native,contact["cases"].get(case_id))
        assert contact["status"]==item["status"]=="accepted"
        assert len(item["samples"])==381 and item["minimum_evaluated_triangle_radial_gap_m"]>0
        assert item["maximum_inside_evaluated_vertices"]==item["maximum_intersecting_triangle_pairs"]==0
        receipt=read_json(case/"render_receipt.json")
        assert receipt["cache_sha256"]==digest(case/"simulation/genesis_flag_cache.npz")
        assert receipt["video_sha256"]==digest(case/"video.mp4")
        assert receipt["frame_range"]==[1,96] and receipt["resolution"]==[1280,720] and receipt["render_samples"]==64
        assert not receipt.get("diagnostic_partial_or_preview",False)
        probe=verify_video(case/"video.mp4")
        exact=bool((case/"import_receipt.json").is_file())
        imported &= exact
        if exact:
            accepted=manifest["approved_cases"][native]
            assert read_json(case/"import_receipt.json")["asset_manifest_sha256"]==digest(assets/"asset_manifest.json")
            for rel,expected_hash in accepted["files"].items():
                assert digest(case/rel)==expected_hash,(case_id,rel)
            appearances.add(accepted["appearance_sha256"])
        for name in ("prompts.json","scenario_overrides.json","scenario_metadata.json","ground_truth.json"):
            assert (case/name).is_file(),(case_id,name)
        write_json(case/"physics_edit.json",{"before":conf0["physics"],"after":conf["physics"],
            "actual_changes":changes,"quality_equal":True,"initial_state_bitwise_equal":True})
        results[case_id]={"status":"accepted_imported" if exact else "technical_checks_passed_visual_review_required",
            "video_sha256":digest(case/"video.mp4"),"physical_cache_sha256":receipt["cache_sha256"],
            "probe":probe,"minimum_visual_pole_gap_m":item["minimum_evaluated_triangle_radial_gap_m"],
            "actual_parameter_changes":changes}
    if imported:
        assert len(appearances)==1
    else:
        appearance=read_json(out_root/"cases/appearance_audit.json")
        assert appearance["nonanimated_scene_content_identical"]
    late={CASE_MAP[c]:read_json(out_root/"cases"/c/"simulation/simulation_report.json")["measurements"][-24:] for c in ids}
    mean=lambda c,k:float(np.mean([m[k] for m in late[c]]))
    effects={}
    if "flow_6mps" in late:
        effects["fast_wind_fly_edge_z_increase_m"]=mean("flow_6mps","fly_edge_mean_z_m")-mean("source","fly_edge_mean_z_m")
        assert effects["fast_wind_fly_edge_z_increase_m"]>.12
    if "young_stiff" in late:
        effects["stiff_fold_angle_ratio"]=mean("young_stiff","fold_angle_mean_rad")/mean("source","fold_angle_mean_rad")
        effects["stiff_late_rms_speed_m_s"]=mean("young_stiff","free_rms_speed_m_s")
        assert effects["stiff_fold_angle_ratio"]<.75 and effects["stiff_late_rms_speed_m_s"]>.15
    if "wind_drop_at_2s" in late:
        effects["wind_drop_fly_edge_z_decrease_m"]=mean("source","fly_edge_mean_z_m")-mean("wind_drop_at_2s","fly_edge_mean_z_m")
        assert effects["wind_drop_fly_edge_z_decrease_m"]>.12
    for native in ("flow_0p5mps","flow_0mps"):
        if native in late:
            effects[native+"_fly_edge_z_decrease_m"]=mean("source","fly_edge_mean_z_m")-mean(native,"fly_edge_mean_z_m")
            effects[native+"_late_rms_speed_m_s"]=mean(native,"free_rms_speed_m_s")
            assert effects[native+"_fly_edge_z_decrease_m"]>.12
    status="accepted_imported" if imported else "technical_checks_passed_visual_review_required"
    result={"status":status,"cases":results,"late_one_second_effects":effects,"limits":["Prescribed one-way airflow, not CFD/two-way FSI.",
        "Hypothetical isotropic shell, not experimentally calibrated woven fabric.","Finite contact samples do not prove continuous-time nonpenetration."]}
    write_json(out_root/"validation.json",result)
    return result


if __name__=="__main__":
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-root",type=Path,required=True)
    p.add_argument("--asset-dir",type=Path,default=ASSETS)
    args=p.parse_args()
    print(validate(args.out_root.resolve(),args.asset_dir.resolve())["status"])
