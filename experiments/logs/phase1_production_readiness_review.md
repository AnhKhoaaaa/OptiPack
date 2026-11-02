# Production Readiness Engineering Review — CV #6–#8

Date: 2026-11-01
Integrated into the Issue #21 branch `feat/m1-phase2a-cv-ai-integration` (based on stacked #8 PR). No standalone Production Readiness PR.

## Verified engineering improvements

1. `SegmentationPipeline()` now uses `YOLOESegmenter(tiled_inference=True)`
   by default, aligning the production facade with the tested 90% T01
   detection-recall configuration. Users can still inject an explicit
   untiled segmenter if they accept lower observed recall.
2. `CVMetrologyService.analyze_pair/process_pair` lazily **reuses one**
   `SegmentationPipeline` per service instance, preserving the
   loaded YOLOE model and prompt embeddings between requests.
3. `YOLOESegmenter._predict_patch` uses a reentrant lock around
   shared-model loading and `predict()`. Multiple concurrent calls on
   a shared segmenter serialize model prediction, avoiding unsafe
   concurrent mutation of Ultralytics state. This can increase
   queueing time under load.
4. New regression tests cover configuration, pipeline reuse and
   concurrent inference serialization. Whole cross-module suite:
   **111 passed** (excluding the legacy Phase0 latency-gate test file).

### Real-model inference smoke test

Using the same `CVMetrologyService` and identical T01 Trial03 pair
twice in one process, full automatic segmentation + 3D fitting:

| Run | Wall time | 3D measurements | Reused exact model | All measurements flagged for review |
| --- | ---: | ---: | --- | --- |
| First (cold) | 12.62 seconds | 4 | Yes | Yes |
| Second (warm) | 4.63 seconds | 4 | Yes | Yes |

Dimensions from both runs matched exactly; this is a **single-pair
smoke test, not a repeatable latency distribution or throughput SLA**.
Physical measurement coverage across all existing T01 trials was 80%
before these changes and is **not claimed improved** by model caching.

### Rejected experiment

Tested a separate 768px tile resolution while keeping 960px global
resolution. Trial02–03 detection recall was 16/20 compared to 17/20
for the prior 960px tile baseline. The experimental tile-size option
was **reverted**, not merged, because no recall-neutral benefit
was established. The old model backend remains PyTorch.

## Remaining gates — NOT production ready

- New independent images with physical ground truth are needed (#9):
  T01 was used for calibration, implementation and model choice.
- The T01 pipeline still reports 80% verified measurement coverage
  and one unverified stereo association; these are not acceptable
  for unattended downstream packing.
- Current estimated 1-sigma uncertainty is not calibrated; as a
  result, all measurements require human review.
- The end-to-end Track A service includes more work than CV:
  even the single warm CV run (4.63 seconds) is above the proposed
  #21 4.5-second whole request goal.
- Validate stable 95th-percentile latency and memory under repeated
  and concurrent requests; a lock prevents races but limits throughput.
- #21 API integration must **reuse** the CVMetrologyService instance;
  constructing a new service on each request discards this optimization.
- External checkpoint downloads, license review and checkpoint
  cache/prewarm policies still need production integration.
- The legacy Phase 0 latency test file remains excluded from this
  unit/integration result: do not claim full CI green.

No teammate solver, contract schemas or historical benchmark result
was modified.
