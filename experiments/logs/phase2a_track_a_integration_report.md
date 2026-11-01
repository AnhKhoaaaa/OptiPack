# Phase 2 Track A — CV + Meta AI Order Analysis (Issue #21)

Date: 2026-11-01
Branch: `feat/m1-phase2a-cv-ai-integration`, stacked on `feat/m1-production-readiness`.

## Implemented

`POST /api/v1/orders/analyze` now accepts JPEG/PNG multipart uploads
(`top_image` and `oblique_image`), decodes and validates them, and invokes
the existing calibrated `CVMetrologyService.process_pair()` through a
threadpool. The CV service is **reused** between requests to preserve
the loaded YOLOE checkpoint.

Measured items are associated by immutable CV `item_id` and bbox with
their real RGB crop bytes; semantics go through Member 2's batched
`analyze_items_with_muse_spark()`, its SHA-256 cache and its post-sanitizer.
The existing `extract_item_semantics_muse()` single-item method remains
available but is not called by default: batching saves network round-trips.
Handling constraints and `allowed_rotations` are derived from sanitized
attributes; unknown weight stays `None`, never an invented measurement.

Crop URLs use the actual FastAPI mount
`/api/v1/assets/crops/<item_id>.jpg`, even when Muse is disabled.
Response is validated against frozen `OrderAnalysisResponse` Contract
v1.0.0, without modifying any Pydantic contract class.

## Runtime camera profile

The server **does not invent camera intrinsics**. Provide a genuine
intrinsic calibration for the capture device via:

```powershell
$env:OPTIPACK_CAMERA_PROFILE_PATH = 'C:\\camera_profiles\\capture_camera.json'
python -m uvicorn backend.app.api.main:app --host 127.0.0.1 --port 8000
```

Example file structure:

```json
{
  "camera_matrix": [[1500,0,800],[0,1500,525],[0,0,1]],
  "dist_coeffs": [0,0,0,0,0],
  "image_size_wh": [1600,1050]
}
```

The numbers above only illustrate JSON structure; DO NOT copy these
intrinsics for a real camera. The T01 development set additionally has an
in-sample profile (not independently calibrated). It can be selected by
setting `OPTIPACK_CAMERA_PROFILE_PATH` to
`experiments/real_t01/calibration_model_variants.json` and
`OPTIPACK_CAMERA_PROFILE_NAME=free_tangent`, **only for T01 testing**.
Both supplied images must be normalized to the corresponding profile
orientation and size. Restart the server after changing the profile.

## API modes and fail-closed policy

- `capture_mode=dual_photo` (default): real CV. If the oblique
  image is absent, returns zero measurements and a warning.
- `capture_mode=zenith_only`: single-image request accepted but yields
  zero metric 3D measurements with `fallback_zenith_only` warning.
- `capture_mode=demo_fixture`: **explicit opt-in** fixture for existing
  frontend/solver demos. Every item is marked
  `demo_fixture_not_measured`, confidence 0, `requires_user_review=True`.
- Missing ArUco or camera profile: empty `items`, invalid calibration
  status and actionable warnings; **never** assert fictional dimensions.
  The contract's required positive scale field uses `1.0` as a
  **non-metric placeholder**, with calibration status invalid and clear
  warnings; consumers must ignore scale unless calibrated.
- Unsupported/corrupt uploads: HTTP 415/422; uploads above 18 MiB:
  HTTP 413. Invalid server camera profile configuration: HTTP 503.
- `enable_muse_semantics=false`: safe semantic defaults (unknown
  weight); when true, Meta API uses cached data or conservative fallback.
- `enable_cloud_sam=true` currently adds a warning rather than
  claiming cloud SAM was executed. Actual instance masks come from YOLOE.
- One or more uncertain measurements: user-review warning; unpaired
  detections are reported rather than assigned fabricated dimensions.

## Verification

- `tests/test_phase2a_analysis_api.py`: **17 passed**.
  HTTP upload validation, missing image/ArUco/profile, explicit demo,
  CV/AI metadata mapping, sanitizer rotations, mocked AI failures,
  static crop URLs and a real blank-ArUco failure.
- Cross-module suite (excluding the existing Phase0 V3 latency-gate
  test file): **128 passed**, 1 test-dependency deprecation warning.
- Real HTTP smoke test on **T01 Trial03** with actual YOLOE + calibrated
  CV and **offline Muse fallback (no network calls)**:
  HTTP 200, 5 3D measurement records, all user-review required,
  cropped preview URLs served via GET, and ~12.05s cold wall time.
  A prior image recompression produced 5 detected objects whereas
  an uncompressed development run produced 4; this **is not
  held-out accuracy evidence**.
- Real Meta Model API credentials were **not used** in this run. Live
  provider latency/success therefore remains unverified.

## Remaining acceptance blockers

1. **End-to-end latency <= 4.5s not achieved** (cold CV+offline AI
   request ~12.05s; actual AI network cost not included).
2. Production independent 6–8-item photo kits and ground truth (#9)
   are not available. Current T01 benchmark remains a development set.
3. Current CV: 80% verified stereo measurement coverage and one
   unverified stereo pair on historical T01 captures. No improvement
   is claimed here.
4. Uncertainty is an engineering proxy rather than validated sigma;
   human review stays mandatory.
5. Need operating policy for crop retention, deployment licenses,
   Meta API credentials/cache prewarm and monitoring under concurrent
   requests.
6. Legacy Phase0 V3 latency gate is excluded from the fast regression
   suite and needs review on a controlled CI environment.

No solver or Pydantic contract code was changed.
