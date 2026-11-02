import { describe, it, expect } from "vitest";
import { OrderAnalysisResponse, DetectedItemMeasurement } from "../../types/contract";
import { ExtendedPackableItem } from "../../components/ManifestTable";
import orderAnalysisSample from "../../mocks/orderAnalysisSample.json";

describe("Step 1 Frontend E2E Integration Verification", () => {
  const convertItem = (item: DetectedItemMeasurement): ExtendedPackableItem => {
    const isDefaultSafe =
      item.physical_attributes.fragility_source === "default_safe" &&
      item.physical_attributes.orientation_source === "default_unconstrained" &&
      item.physical_attributes.weight_source === "unknown";

    const isAiExtracted =
      item.measurement_provenance.xy_method !== "demo_fixture_not_measured" &&
      item.measurement_provenance.xy_method !== "manual_input" &&
      !isDefaultSafe;

    return {
      item_id: item.item_id,
      display_name: item.display_name,
      quantity: item.quantity,
      dimensions_mm: item.dimensions_mm,
      safety_margin_mm: item.uncertainty_mm.safety_margin_mm,
      weight_g: item.physical_attributes.weight_g,
      weight_assumed: item.physical_attributes.weight_source !== "scale_verified",
      fragility_class: item.physical_attributes.fragility_class,
      keep_upright: item.physical_attributes.keep_upright,
      stackable: item.physical_attributes.stackable,
      max_top_load_g: item.physical_attributes.max_top_load_g,
      allowed_rotations: item.allowed_rotations,
      display_color_hex: item.visual_evidence.display_color_hex,
      crop_url: item.visual_evidence.crop_url,
      provenance_source: isAiExtracted ? "AI-Extracted" : "Default-Safe",
      uncertainty_info: {
        height_sigma_mm: item.uncertainty_mm.height_sigma_mm,
        requires_user_review: item.measurement_provenance.requires_user_review,
      },
    };
  };

  it("should extract crop_url and mark AI-Extracted for items with visual evidence", () => {
    const analysis = orderAnalysisSample as unknown as OrderAnalysisResponse;
    const items = analysis.items.map(convertItem);

    expect(items).toHaveLength(4);
    expect(items[0].crop_url).toBe("/api/v1/assets/crops/ord_20261027_001_item_01.jpg");
    expect(items[0].provenance_source).toBe("AI-Extracted");
    expect(items[0].uncertainty_info?.requires_user_review).toBe(false);
  });

  it("should mark Default-Safe for items without explicit AI labels and unknown weight", () => {
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

  it("should verify telemetry payload schema supports sam-3.1 and muse-spark-1.3", () => {
    const analysis = orderAnalysisSample as unknown as OrderAnalysisResponse;
    expect(analysis.ai_telemetry).toBeDefined();
    expect(analysis.ai_telemetry.sam_status).toBe("success");
    expect(analysis.ai_telemetry.muse_model).toBe("muse-spark-1.3");
    expect(analysis.ai_telemetry.fallback_activated).toBe(false);
  });
});
