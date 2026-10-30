"""Generate the T01 evidence report from machine-readable benchmark output."""
import csv
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
def main():
    r=json.loads((HERE/"real_results.json").read_text(encoding="utf-8"))
    profile=json.loads((HERE/"camera_profile_estimated.json").read_text(encoding="utf-8"))
    if r["real_world_t01_gate"]=="PASS":
        raise ValueError("Do not generate a GO report from an unverified baseline")
    rows=r["object_baseline_diagnostics"]
    lines=[
        "# OptiPack T01 — Real capture evidence report",
        "",
        "**Verdict: NOT PASSED / needs further CV metrology work.**",
        "",
        "## Dataset & provenance",
        "",
        "- Eight **pixel-identical, GPS/EXIF-sanitized RGB JPEG copies** from the user-shared Drive folder. The source originals remain on Drive; `source_manifest.json` records Drive IDs and source/sanitized SHA-256 hashes.",
        "- Three named top-down/oblique trial pairs; two additional left/right side views for Trial 02.",
        "- Five object *labels* per capture; physical identity across trials, especially 'black' in Trial01, remains to be verified. Input dimensions interpreted as **centimetres** and converted to millimetres in `ground_truth.csv`; user has not explicitly confirmed measurement units.",
        "- **40 manually seeded ROIs/crops** (five items per photo), with provenance in `roi_annotations.json` and `crop_annotations.json`. These are NOT automatic detections or pixel-perfect masks.",
        "",
        "## Measured results on real pixels",
        "",
        "| Gate / metric | Observed | Threshold | Verdict |",
        "|---|---:|---:|---|",
        f"| Marker IDs 0–3 detected | {int(r['marker_detection_rate']*r['images_analyzed'])}/{r['images_analyzed']} (100%) | >=90% | Meets marker visibility only |",
        f"| Pose reprojection <=2.5 px (estimated K) | {int(round(r['pose_quality_threshold_rate']*r['images_analyzed']))}/{r['images_analyzed']} ({100*r['pose_quality_threshold_rate']:.1f}%) | >=90% | Does not meet threshold |",
        f"| Self-calibration in-sample RMS | {profile['in_sample_rms_px']:.2f} px | <=2.5 px | Diagnostic ONLY — estimated K fitted on these same images |",
        f"| Crude L/W baseline MAE | {r['observed_xy_mae_mm']:.2f} mm across {len(rows)} object/trial cases | <=8.0 mm | Does not meet threshold |",
        "| Height H MAE | NOT EVALUATED | <=12.0 mm | Not passed |",
        "| Full pipeline CPU latency per two-image pair | NOT EVALUATED | <=800 ms | Not passed |",
        "",
        "The L/W estimate uses a real segmentation from a manually seeded ROI and projects",
        "a 2D object silhouette to a plane using an aspect-ratio height prior. The true",
        "top-face corners and height are NOT recovered; silhouette inflation can cause",
        "large errors. **Ground truth is read only for evaluation; it is not passed to the estimator.**",
        "",
        "## Detailed exploratory L/W results",
        "",
        "| Trial | Item | GT L/W (mm) | Estimated L/W (mm) | Abs error L/W (mm) |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        gt=row["ground_truth_mm"]
        lines.append(f"| {row['trial']} | {row['item_id']} | {gt['length_mm']:.0f}/{gt['width_mm']:.0f} | {row['length_mm']:.1f}/{row['width_mm']:.1f} | {row['absolute_error_length_mm']:.1f}/{row['absolute_error_width_mm']:.1f} |")
    experiment=HERE/"experimental_3d_results.json"
    if experiment.is_file():
        exp=json.loads(experiment.read_text(encoding="utf-8"))
        fits=exp["metrics_exploratory_only"]
        if fits:
            xy=sum((r["abs_errors_mm"][0]+r["abs_errors_mm"][1])/2 for r in fits)/len(fits)
            h=sum(r["abs_errors_mm"][2] for r in fits)/len(fits)
            lines += [
                "",
                "## Experimental multi-view cuboid fit — research only, NOT T01 gate",
                "",
                "The experimental least-squares cuboid silhouette fit uses FOUR views of **Trial 02**",
                "(top, oblique, left and right), 5 manually seeded segmentation ROIs and a",
                "self-calibrated camera profile. It does **not** consume L/W/H ground truth",
                "while fitting. It is NOT a tested fully automatic two-view T01 estimator.",
                "",
                f"**Diagnostic XY MAE: {xy:.2f} mm; diagnostic H MAE: {h:.2f} mm**.",
                "Both exceed T01 thresholds (8 / 12 mm); these are not acceptance metrics",
                "because only one trial and four views were used, manual ROIs were provided,",
                "and intrinsic calibration is provisional. Pixel silhouette residuals are high.",
                "",
                "| Item | Estimated L/W/H (mm) | GT L/W/H (mm) | Abs error L/W/H (mm) | Pixel bbox RMS |",
                "|---|---|---|---|---:|",
            ]
            for e in fits:
                pred="/".join(f"{x:.1f}" for x in e["fitted_LWH_mm"])
                actual="/".join(f"{x:.0f}" for x in e["ground_truth_LWH_mm"])
                err="/".join(f"{x:.1f}" for x in e["abs_errors_mm"])
                lines.append(f"| {e['item_id']} | {pred} | {actual} | {err} | {e['pixel_bbox_rms_error_px']:.1f} |")
    four_file=HERE/"paper_edge_experiment.json"
    pair_file=HERE/"paper_two_view_results.json"
    if four_file.is_file() and pair_file.is_file():
        four=json.loads(four_file.read_text(encoding="utf-8"))
        pair=json.loads(pair_file.read_text(encoding="utf-8"))
        pairs=pair["pair_results"]
        lines += [
            "",
            "## Paper-inspired edge-constrained cuboid results (research only)",
            "",
            "- Method basis: Yang & Scherer (2019), CubeSLAM, cuboid proposals",
            "  and Canny/edge-distance scoring; independent Python/OpenCV/NumPy",
            "  geometric adaptation, not a verbatim reproduction of the ROS/C++ code.",
            "- Source: https://github.com/shichaoy/cube_slam (BSD-3-Clause).",
            "- 3D cuboid parameters (center XY, dimensions L/W/H, yaw) are",
            "  projected through ArUco-derived camera poses and refined against",
            "  observed bounding boxes and Canny distance transforms.",
            "- All real-photo variants still require manually initialized ROIs",
            "  and intrinsics estimated from the same capture set.",
            "",
            "| Condition | Mean L/W error | Mean H error | Time for 5 objects |",
            "|---|---:|---:|---:|",
            f"| Trial 02, **4 views** | {four['xy_mae_mm']:.2f} mm | {four['h_mae_mm']:.2f} mm | {four['runtime_ms_total']/1000:.2f} s |",
        ]
        for trial,datum in sorted(pairs.items()):
            lines.append(
                f"| {trial}, **2 views** | {datum['xy_mae_mm']:.2f} mm | "
                f"{datum['h_mae_mm']:.2f} mm | {datum['time_ms_five_objects']/1000:.2f} s |")
        lines += [
            f"| **2-view mean across trials** | **{pair['all_pairs_xy_mae_mm']:.2f} mm** | "
            f"**{pair['all_pairs_h_mae_mm']:.2f} mm** | — |",
            "",
            "Four-view exploratory errors can be below 8/12 mm on this one trial,",
            "but the actual **two-view** average L/W error remains above the 8 mm",
            "gate and processing time far exceeds 800 ms. None of these results",
            "is an independently calibrated, autonomous acceptance benchmark.",
            "Source capture repeats served as both development and evaluation;",
            "a held-out physical test set is needed to support generalization.",
            "",
        ]
    ablation=HERE/"calibration_ablation.json"
    if ablation.is_file():
        a=json.loads(ablation.read_text(encoding="utf-8"))
        lines += [
            "## Marker corner refinement ablation",
            "",
            "Leave-one-image-out calibration (other seven images fit intrinsics; test",
            "image estimates its pose and reprojection error). This is still the",
            "same capture session, not an independent device calibration.",
            "",
            "| Corner refinement | In-sample RMS | LOO mean | LOO max |",
            "|---|---:|---:|---:|",
        ]
        for name,entry in a.items():
            lines.append(f"| {name} | {entry['in_sample_RMS_px']:.2f} px | "
                         f"{entry['mean_leave_one_out_px']:.2f} px | {entry['max_leave_one_out_px']:.2f} px |")
        lines += ["", "Subpixel refinement was retained because it gave the lowest",
                  "LOO mean and maximum error among these three methods.", ""]
    lines += [
        "",
        "## Camera and annotation constraints",
        "",
        "- Intrinsics obtained by `cv2.calibrateCamera` from these same eight frames (assumed printed A4 board 40 mm marker size). This is NOT an independent camera calibration; held-out generalization and printed size must be validated.",
        "- Original Trial 01 JPGs are portrait; they are rotated clockwise **in-memory** for consistent 4032×3024 camera calibration. The raw originals remain on Drive; the repo copies have private metadata removed.",
        "- Each photo is a different camera pose; ArUco marker detection is independent of this intrinsics fit, but pose quality is not.",
        "- No supervised neural-network training was performed. OpenCV ArUco and GrabCut need no pretrained weights.",
        "- Trial 01 oblique angle is visually close to top-down, reducing useful parallax; this is an observation, not a quantified elevation angle.",
        "- Human ROIs and unknown physical resting orientation of each box can bias measurements. A segmentation crop alone does not establish a top-face quadrilateral.",
        "",
        "## Decision / next technical steps",
        "",
        "1. **Do not close GitHub Issue #1 or claim T01 GO.** The exploratory v2 L/W aggregate is <=8 mm on this development set but the strict gate still fails for pose, manual ROI/unknown intrinsics, latency and missing held-out validation; several individual errors remain high.",
        "2. Obtain **independent camera intrinsics** (camera calibration profile for the same smartphone mode) and verify printed 40 mm ArUco marker size.",
        "3. Build reliable multi-object tabletop top-face segmentation and correspondence between top/oblique views; do not use bounding-box silhouette as a precise top-face measurement.",
        "4. Independently validate two-view H and L/W measurement (including uncertainty), evaluate a held-out capture session and optimize runtime. If H fails, activate the documented height-review fallback; if L/W remains >15 mm, escalate to the team as specified by T01.",
        "5. Expose only measurements validated by the CV module to `/orders/analyze`; the current router/production segmenter and metrology modules still contain placeholders.",
        "",
        "## Reproduction",
        "",
        "```powershell",
        ".\\.venv\\Scripts\\python.exe experiments\\real_t01\\download_images.py",
        ".\\.venv\\Scripts\\python.exe experiments\\real_t01\\inspect_captures.py",
        ".\\.venv\\Scripts\\python.exe experiments\\real_t01\\calibrate_dataset.py",
        ".\\.venv\\Scripts\\python.exe experiments\\real_t01\\prepare_dataset.py",
        ".\\.venv\\Scripts\\python.exe experiments\\phase0_cv_metrology.py --dataset both",
        ".\\.venv\\Scripts\\python.exe -m experiments.real_t01.exploratory_fit  # optional; ~35 s",
        ".\\.venv\\Scripts\\python.exe -m experiments.real_t01.paper_two_view",
        ".\\.venv\\Scripts\\python.exe -m experiments.real_t01.silhouette_fit",
        ".\\.venv\\Scripts\\python.exe experiments\\real_t01\\generate_report.py",
        ".\\.venv\\Scripts\\python.exe -m pytest -q tests",
        "```",
        "",
        "No commits, pushes or merges are performed by these scripts.",
        "",
    ]
    # Latest research comparison belongs ABOVE the original baseline gate table.
    # The gate table below still measures the non-production baseline and must
    # not be silently replaced by exploratory, manually seeded benchmarks.
    newer=HERE/"silhouette_experiment.json"
    older=HERE/"paper_two_view_results.json"
    if newer.is_file() and older.is_file():
        latest=json.loads(newer.read_text(encoding="utf-8"))
        previous=json.loads(older.read_text(encoding="utf-8"))
        if latest["status"]=="EXPLORATORY_NOT_T01_GATE":
            summary=[
                "## Latest research — before / after (NOT an autonomous T01 pass)",
                "",
                "| Approach | L/W MAE | H MAE | Evidence |",
                "|---|---:|---:|---|",
                f"| Baseline silhouette/raycast | {r['observed_xy_mae_mm']:.2f} mm | Not measured | 3 top-down views; untrusted H prior |",
                f"| CubeSLAM-inspired edge fit (v1) | {previous['all_pairs_xy_mae_mm']:.2f} mm | {previous['all_pairs_h_mae_mm']:.2f} mm | 3 pairs, manual ROIs |",
                f"| **Silhouette-constrained cuboid (v2)** | **{latest['overall_xy_mae_mm']:.2f} mm** | **{latest['overall_h_mae_mm']:.2f} mm** | 3 pairs, manual ROIs + GrabCut, provisional K |",
                "",
                "V2 adds bidirectional silhouette-boundary distance (a shape-consistency",
                "constraint) to cuboid fitting, reducing misleading matches to",
                "floor grout/text/texture in global Canny maps. It is a custom",
                "experiment motivated by geometric cuboid fitting (CubeSLAM)",
                "and silhouette-consistency/visual-hull principles, **not an exact",
                "reproduction** of either paper. No ground-truth dimensions enter",
                "the optimizer; all errors are computed after fitting.",
                "",
                "| Pair | V1 L/W MAE | V2 L/W MAE | V2 H MAE | V2 wall time for 5 items |",
                "|---|---:|---:|---:|---:|",
            ]
            for trial,datum in latest["trials"].items():
                prior=previous["pair_results"][trial]
                summary.append(
                    f"| {trial} | {prior['xy_mae_mm']:.2f} mm | {datum['xy_mae_mm']:.2f} mm | "
                    f"{datum['h_mae_mm']:.2f} mm | {datum['runtime_ms_five_objects']/1000:.2f} s |")
            summary += [
                "",
                "**Status:** L/W and H means fall below 8/12 mm in this",
                "**development-set ablation only**; **T01 is still NOT PASSED**",
                "because pose is 7/8 <=2.5 px (<90%), processing time exceeds",
                "800 ms per pair, camera intrinsics were fit in-sample, and",
                "manual object ROIs are required. Several item errors still",
                "exceed 12–20 mm; a 7.91 mm aggregate mean is not evidence",
                "of robust generalization on new captures.",
                "",
                "**Dataset consistency warning:** Trial01 'black' appears to be",
                "a two-driver black speaker, while Trials 02–03 show a plain",
                "black box. Verify whether these are the same physical item",
                "and its actual dimensions before trusting aggregated MAE.",
                "The user-provided units (assumed cm) and box resting orientations",
                "also need independent confirmation.",
                "",
            ]
            lines[4:4]=summary
    # Supplemental ablations are evidence, not new T01 acceptance criteria.
    audit_file=HERE/"t01_quality_audit.json"
    faster_file=HERE/"fast_pose_ablation.json"
    if audit_file.is_file() and faster_file.is_file():
        audit=json.loads(audit_file.read_text(encoding="utf-8"))
        fast=json.loads(faster_file.read_text(encoding="utf-8"))
        a=fast["summary"]["scale1.0_iterative"]
        b=fast["summary"]["scale0.5_iterative"]
        limit=audit["uncertain_label_sensitivity"]
        lines.extend([
            "",
            "## 2026-10-30 research iteration — measured improvements and rejected ideas",
            "",
            "**Accepted as optional experiment only:** downsample ArUco detection",
            "to half-resolution, refine corners at original resolution, retain",
            "ITERATIVE PnP. Source: `fast_pose_ablation.py`,",
            "results: `fast_pose_ablation.json`.",
            "",
            "| Diagnostic metric | Full-res original | 0.5x + full-res subpixel |",
            "|---|---:|---:|",
            f"| Median detect+PnP per photo | {a['median_ms_per_image']:.2f} ms | {b['median_ms_per_image']:.2f} ms |",
            f"| Marker count 4/4 | {a['marker_4_count']}/8 | {b['marker_4_count']}/8 |",
            f"| Pose reprojection <=2.5 px | {a['pose_pass_count']}/8 | {b['pose_pass_count']}/8 |",
            f"| Max camera-center drift vs original | 0 mm (reference) | {b['max_camera_center_drift_mm']:.4f} mm |",
            "",
            "No new camera calibration, no new physical accuracy measurement,",
            "and **no improvement in pose pass rate**. IPPE and EPnP planar",
            "alternatives were tested; both retained the same 7/8 threshold count.",
            "These are controlled *algorithm comparisons*, NOT production T01",
            "wall-time measurements. Default backend remains unchanged.",
            "",
            "**Rejected/undone:** LSD top-face lines (von Gioi et al.,",
            "TPAMI 2010) changed L/W MAE only 7.909 to 7.858 mm, regressed",
            "Trial01, and did not resolve runtime. Graph-based segmentation",
            "was not runnable in this OpenCV build; no new dependencies",
            "or pretrained weights were added. Prior shortcut GrabCut",
            "variants reduced latency but changed L/W/H fits unacceptably.",
            "",
            "## GT sensitivity and T01 readiness audit",
            "",
            f"- V2 L/W MAE, all 15 labeled cases: **{audit['criteria']['xy_mae']['mm']:.3f} mm**.",
            f"- Excluding unverified Trial01 black: **{limit['xy_mae_mm_excluding_case']:.3f} mm** across {limit['remaining_cases']} cases; this is a sensitivity check, NOT repaired GT.",
            "- **Verdict remains NOT PASSED:** marker pose 7/8, manual",
            "  object ROIs, camera intrinsics fit on the same photographs,",
            "  full-pair CPU much slower than 800 ms, and no held-out",
            "  generalization or production backend integration.",
            "- See `t01_quality_audit.json` for machine-readable evidence,",
            "  `RESEARCH_DECISION.md` for paper sources and full caveats.",
        ])
    (HERE/"REPORT.md").write_text("\n".join(lines),encoding="utf-8")
    print("REPORT.md generated:",len(rows),"real item trials")
if __name__=="__main__":main()
