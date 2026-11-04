import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, OptiPackClient } from "../../api/optipackClient";
import { needsMeasurementReview } from "../review";
import type { PackingRequest } from "../../types/contract";

const sampleRequest: PackingRequest = {
  contract_version: "1.0.0",
  analysis_id: "live-order",
  solver_config: {
    mode: "cpsat_with_heuristic_fallback",
    time_limit_ms: 3000,
    apply_uncertainty_margin: true,
    min_support_ratio: 0.6,
    allow_multi_carton_split: true,
  },
  items: [],
};

afterEach(() => { vi.unstubAllGlobals(); });

describe("Live API failures never become a fake packing result", () => {
  it("preserves HTTP 422 from the solver for the UI to report", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Invalid dimensions" }), { status: 422 })
    ));
    await expect(OptiPackClient.packOrder(sampleRequest)).rejects.toMatchObject({
      name: "ApiError",
      status: 422,
    });
  });

  it("preserves connectivity failures instead of silently loading a demo plan", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(OptiPackClient.packOrder(sampleRequest)).rejects.toThrow("Failed to fetch");
    await expect(OptiPackClient.analyzeOrder(new FormData())).rejects.toThrow("Failed to fetch");
  });

  it("keeps 500 HTTP errors as API errors (not mock fallback)", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    await expect(OptiPackClient.packOrder(sampleRequest)).rejects.toMatchObject({
      name: "ApiError",
      status: 500,
      message: "Backend Error (500): Request failed",
    });
  });

  it("formats API error message with fallback reason when statusText is empty", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 502, statusText: "" })));
    await expect(OptiPackClient.packOrder(sampleRequest)).rejects.toMatchObject({
      name: "ApiError",
      status: 502,
      message: "Backend Error (502): Request failed",
    });
  });
});

describe("Explicit measurement confirmation", () => {
  const flagged = { uncertainty_info: { requires_user_review: true, height_sigma_mm: 11 } };

  it("blocks unverified high-uncertainty measurements", () => {
    expect(needsMeasurementReview(flagged)).toBe(true);
    expect(needsMeasurementReview({ uncertainty_info: { requires_user_review: false, height_sigma_mm: 9 } })).toBe(true);
  });

  it("only clears the gate after explicit acknowledgement", () => {
    expect(needsMeasurementReview({ ...flagged, review_acknowledged: true })).toBe(false);
    expect(needsMeasurementReview({ uncertainty_info: { requires_user_review: false, height_sigma_mm: 2 } })).toBe(false);
  });
});
