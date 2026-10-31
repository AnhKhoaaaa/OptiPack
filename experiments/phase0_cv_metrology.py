"""Member 1 Phase 0 entrypoint — synthetic regression and real-photo audit.

Synthetic PASS is never a physical T01 GO. Real mode always reports incomplete
requirements plainly; use --require-go to signal non-passing real gates as a
nonzero process exit code for acceptance review.
"""
from pathlib import Path
import argparse
import json
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from experiments.synthetic_t01.benchmark import evaluate as synthetic_evaluate

def main(argv=None):
    ap=argparse.ArgumentParser()
    ap.add_argument("--dataset",choices=("synthetic","real","both"),default="both")
    ap.add_argument("--require-go",action="store_true",help="Nonzero exit if any requested gate does not pass")
    args=ap.parse_args(argv)
    fail=False
    if args.dataset in ("synthetic","both"):
        outcome=synthetic_evaluate()
        p=ROOT/"experiments"/"synthetic_t01"/"synthetic_results.json"
        p.write_text(json.dumps(outcome,indent=2)+"\n")
        ok=outcome["synthetic_regression_pass"]
        print("SYNTHETIC REGRESSION:", "PASS" if ok else "FAIL")
        print("SYNTHETIC IS NOT PHYSICAL VALIDATION")
        fail=fail or not ok
    if args.dataset in ("real","both"):
        from experiments.real_t01.real_baseline import evaluate as real_evaluate
        outcome=real_evaluate()
        print("REAL PHYSICAL T01 GATE:",outcome["real_world_t01_gate"])
        print("REAL XY BASELINE MAE:",outcome["observed_xy_mae_mm"],"mm")
        print("REAL HEIGHT MAE:",outcome["height_mae_mm"])
        fail=fail or outcome["real_world_t01_gate"]!="PASS"
    if fail and args.require_go:
        raise SystemExit(1)
if __name__=="__main__":main()
