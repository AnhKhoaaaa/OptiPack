import { describe, it, expect } from "vitest";
import { OrderAnalysisResponse, DetectedItemMeasurement } from "../../types/contract";
import { convertItem } from "../../App";
import orderAnalysisSample from "../../mocks/orderAnalysisSample.json";

describe("Step 1 Frontend E2E Integration Verification", () => {
  it("should extract crop_url and mark AI-Extracted for items with visual evidence", () => {
    const analysis = orderAnalysisSample as unknown as OrderAnalysisResponse;
    const items = analysis.items.map(convertItem);

    expect(items).toHaveLength(4);
    expect(items[0].crop_url).toBe("/api/v1/assets/crops/ord_20261027_001_item_01.jpg");
    expect(items[0].provenance_source).toBe("AI-Extracted");
    expect(items[0].uncertainty_info?.requires_user_review).toBe(false);
  });

  it("should mark Default-Safe for generic items without explicit AI labels and unknown weight", () => {
    const mockItem: DetectedItemMeasurement = {
      item_id: "test_uncalibrated",
      display_name: "Generic Box",
      category: "unclassified",
      quantity: 1,
      dimensions_mm: { length_mm: 100, width_mm: 80, height_mm: 50 },
      uncertainty_mm: {
        length_sigma_mm: 2,
        width_sigma_mm: 2,
        height_sigma_mm: 2,
        safety_margin_mm: 5,
      },
      measurement_provenance: {
        xy_method: "aruco_plane_raycast",
        z_method: "dual_view_pnp_triangulation",
        confidence_score: 0.8,
        requires_user_review: false,
      },
      physical_attributes: {
        weight_g: null,
        weight_source: "unknown",
        fragility_class: "low",
        fragility_source: "default_safe",
        keep_upright: false,
        orientation_source: "default_unconstrained",
        stackable: true,
        max_top_load_g: 5000,
        visible_labels: [],
      },
      allowed_rotations: ["LWH", "WLH"],
      visual_evidence: {
        bbox_2d_px: [0, 0, 100, 80],
        crop_url: null,
        mask_rle: null,
        display_color_hex: "#3B82F6",
      },
    };

    const converted = convertItem(mockItem);
    expect(converted.provenance_source).toBe("Default-Safe");
    expect(converted.crop_url).toBeNull();
  });

  it("should mark AI-Extracted when Muse extracts a real brand/product display_name even with unknown weight", () => {
    const mockMuseNamedItem: DetectedItemMeasurement = {
      item_id: "item_01",
      display_name: "Top Gia Paper Tissue Pack",
      category: "general_box",
      quantity: 1,
      dimensions_mm: { length_mm: 148, width_mm: 83, height_mm: 55 },
      uncertainty_mm: {
        length_sigma_mm: 1.5,
        width_sigma_mm: 1.5,
        height_sigma_mm: 2.0,
        safety_margin_mm: 5,
      },
      measurement_provenance: {
        xy_method: "aruco_plane_raycast",
        z_method: "dual_view_pnp_triangulation",
        confidence_score: 0.92,
        requires_user_review: false,
      },
      physical_attributes: {
        weight_g: null,
        weight_source: "unknown",
        fragility_class: "low",
        fragility_source: "default_safe",
        keep_upright: false,
        orientation_source: "default_unconstrained",
        stackable: true,
        max_top_load_g: 3000,
        visible_labels: ["Top Gia"],
      },
      allowed_rotations: ["LWH", "WLH", "LHW", "HLW", "WHL", "HWL"],
      visual_evidence: {
        bbox_2d_px: [120, 140, 320, 280],
        crop_url: "/api/v1/assets/crops/item_01.jpg",
        mask_rle: null,
        display_color_hex: "#0071E3",
      },
    };

    const converted = convertItem(mockMuseNamedItem);
    expect(converted.provenance_source).toBe("AI-Extracted");
    expect(converted.crop_url).toBe("/api/v1/assets/crops/item_01.jpg");
  });

  it("should verify telemetry payload schema supports sam-3.1 and muse-spark-1.3", () => {
    const analysis = orderAnalysisSample as unknown as OrderAnalysisResponse;
    expect(analysis.ai_telemetry).toBeDefined();
    expect(analysis.ai_telemetry.sam_status).toBe("success");
    expect(analysis.ai_telemetry.muse_model).toBe("muse-spark-1.3");
    expect(analysis.ai_telemetry.fallback_activated).toBe(false);
  });
});
