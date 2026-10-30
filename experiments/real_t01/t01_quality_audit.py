"""Conservative T01 evidence audit; never upgrades experimental results to GO.

Reads *existing* benchmark JSON, not new measurements. It catches
measurement aggregation sensitivity to questionable cross-trial labels.
"""
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent
UNCERTAIN_CASE=("Trial01","black")

def evaluate(baseline,experimental,pose_variants=None):
    vals=[]
    subset=[]
    per_trial={}
    for trial, entry in experimental["trials"].items():
        rows=entry["items"]
        per_trial[trial]={"xy_mae_mm":float(entry["xy_mae_mm"]),
                          "h_mae_mm":float(entry["h_mae_mm"]),
                          "wall_ms_five_objects":float(entry["runtime_ms_five_objects"])}
        for row in rows:
            errors=np.asarray(row["absolute_errors_mm"],float)
            sample={"trial":trial,"item":row["item_id"],
                    "xy_abs_error_mean_mm":float(np.mean(errors[:2])),
                    "h_abs_error_mm":float(errors[2])}
            vals.append(sample)
            if (trial,row["item_id"])!=UNCERTAIN_CASE:
                subset.append(sample)
    if len(vals)!=15 or len(subset)!=14:
        raise ValueError("Unexpected source data; refuse automatic T01 verdict")
    xy=float(np.mean([r["xy_abs_error_mean_mm"] for r in vals]))
    h=float(np.mean([r["h_abs_error_mm"] for r in vals]))
    xy_excl=float(np.mean([r["xy_abs_error_mean_mm"] for r in subset]))
    pose_rate=float(baseline["pose_quality_threshold_rate"])
    marker_rate=float(baseline["marker_detection_rate"])
    result={
        "status":"NOT_PASSED",
        "reason":"Research/development-set benchmark, NOT production T01 acceptance",
        "criteria":{
            "marker_detected":{"rate":marker_rate,"threshold":0.9,"meets_numeric_threshold":marker_rate>=.9},
            "pose_reprojection":{"rate":pose_rate,"threshold":.9,"meets_numeric_threshold":pose_rate>=.9},
            "xy_mae":{"mm":xy,"threshold_mm":8.,"meets_development_mean":xy<=8},
            "h_mae":{"mm":h,"threshold_mm":12.,"meets_development_mean":h<=12},
            "cpu_pair":{"threshold_ms":800,
                         "meets":all(v["wall_ms_five_objects"]<=800 for v in per_trial.values()),
                         "observed_wall_ms_by_pair":{k:v["wall_ms_five_objects"] for k,v in per_trial.items()}},
            "fully_automatic_multiobject":{"meets":False,"evidence":"Manually supplied ROIs + GrabCut"},
            "independent_camera_calibration":{"meets":False},
            "independent_holdout_session":{"meets":False},
            "production_backend_integration":{"meets":False},
        },
        "uncertain_label_sensitivity":{
            "unverified_case":{"trial":UNCERTAIN_CASE[0],"item_id":UNCERTAIN_CASE[1]},
            "xy_mae_mm_excluding_case":xy_excl,
            "remaining_cases":len(subset),
            "note":"Diagnostic only: exclusion does not correct ground truth. Confirm actual object identity/dimensions.",
        },
        "per_trial":per_trial,
        "worst_five_xy_errors":sorted(vals,key=lambda r:r["xy_abs_error_mean_mm"],reverse=True)[:5],
        "limitations":["manual ROIs","same-session intrinsic calibration","uncertain 'black' identity and GT units",
                       "unvalidated marker printed size","wall-time not controlled benchmark",
                       "absence of held-out captures"],
        "experimental_fast_pose":{
            "available":pose_variants is not None,
            "best_tested_conservative_variant":"scale0.5_iterative",
            "does_not_resolve_current_pose_failure":None,
        }
    }
    if pose_variants is not None:
        variant=pose_variants["summary"]["scale0.5_iterative"]
        result["experimental_fast_pose"]["stats"]=variant
        result["experimental_fast_pose"]["does_not_resolve_current_pose_failure"]=(
            variant["pose_pass_count"]/len(pose_variants["images"]) < .9)
    return result

def main():
    b=json.loads((HERE/"real_results.json").read_text(encoding="utf-8"))
    e=json.loads((HERE/"silhouette_experiment.json").read_text(encoding="utf-8"))
    f=HERE/"fast_pose_ablation.json"
    p=json.loads(f.read_text(encoding="utf-8")) if f.is_file() else None
    audit=evaluate(b,e,p)
    (HERE/"t01_quality_audit.json").write_text(json.dumps(audit,indent=2)+"\n",encoding="utf-8")
    print("VERDICT",audit["status"],
          "XY",round(audit["criteria"]["xy_mae"]["mm"],3),
          "SENSITIVITY_14",round(audit["uncertain_label_sensitivity"]["xy_mae_mm_excluding_case"],3))
    return audit

if __name__=="__main__":main()
