"""Apply the frozen accumulation gates to Genesis mass and output geometry."""
import argparse
import json
from pathlib import Path

from summarize_accumulation import summarize

parser=argparse.ArgumentParser()
parser.add_argument("case",type=Path)
parser.add_argument("--plan",type=Path,required=True)
args=parser.parse_args()
case=args.case.resolve()
plan=json.loads(args.plan.read_text())
limits=plan["numeric_acceptance"]
mass=json.loads((case/"genesis_audit.json").read_text())
mesh=json.loads((case/"surface_audit.json").read_text())
simulation=json.loads((case/"simulation_result.json").read_text())
experiment=json.loads((case/"experiment.json").read_text())
actual_cup=mass.get("method","").startswith("Exact actual-cup")
reports={}
for name,data,field in (("fixed_mass_in_actual_cavity",mass,"cup_particle_rest_volume_ml"),
                        ("independent_reconstructed_mesh",mesh,"cup_mesh_volume_ml")):
    compatible={"frames":{f:{"cup_mesh_volume_ml":v[field]} for f,v in data["frames"].items()}}
    complete=all(str(f) in compatible["frames"] for f in range(1,97))
    windows={str(s):summarize(compatible,s,84) for s in (20,24)} if complete else {}
    checks={"all96frames":complete}
    if complete:
        for start,stats in windows.items():
            checks[f"monotonic_{start}_84"]=stats["negative_frame_increments"]==0
            checks[f"uniform_{start}_84"]=stats["linear_fit_r_squared"]>=limits["minimum_linear_fit_r_squared"] and stats["window_rate_cv"]<=limits["maximum_half_second_rate_coefficient_of_variation"]
        stats=windows["20"]
        checks["final_dose"]=limits["final_settled_volume_range_ml"][0]<=stats["final_settled_volume_ml"]<=limits["final_settled_volume_range_ml"][1]
        checks["retention_after84"]=stats["final_settled_volume_ml"]>=limits["minimum_after_pour_retention_ratio"]*stats["final_pour_volume_ml"]
        checks["settled_tail_stability"]=abs(stats["settle_90_to_96_relative_change"])<=limits["maximum_post_pour_relative_volume_change"]
    reports[name]={"passed":all(checks.values()),"checks":checks,"statistics":windows}
result={"solver":"Genesis1.4.3 DFSPH","case":str(case),"plan":str(args.plan),
        "completed_simulation":simulation["completed"],"native_emission_mass_checks":mass["checks"],
        "reports":reports,
        "passed_numeric_gate":simulation["completed"] and all(mass["checks"].values()) and all(r["passed"] for r in reports.values()),
        "small_exterior_rest_volume_ml":max(r["outside_mass_ml"] for r in mass["frames"].values()),
        "boundary_limitation":("Actual visible-cup triangles audited separately. Exterior-ID history and all-frame mesh connectivity are in actual_cup_audit.json; 24fps samples are not a mathematical continuous-time impermeability proof." if actual_cup else "Tiny early exterior droplets; 6 sampled trajectories cannot resolve over-rim flight versus contact between24fps snapshots. Not a claim of mathematically exact wall impermeability."),
        "capillary_limitation":f"Native Genesis cohesion gamma={experiment['after']['gamma']} and physical water viscosity used. Gamma is a native solver coefficient, not a measured SI surface-tension coefficient. Surface tension, wetting and air coupling are not experimentally calibrated.",
        "independent_field_note":"Genesis fixed particle masses replace Mantaflow marker/SDF accounting. Reconstructed geometry is independently checked; no target height or amount is supplied to reconstruction.",
        "visual_reviewed":False,"video_validated":False}
(case/"numeric_acceptance_genesis.json").write_text(json.dumps(result,indent=2)+"\n")
print("GENESIS_NUMERIC="+json.dumps({k:v for k,v in result.items() if k!="reports"}),flush=True)
if not result["passed_numeric_gate"]:
    raise SystemExit(2)
