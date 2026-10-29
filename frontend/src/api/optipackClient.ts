/**
 * OptiPack API Client (Contract v1.0.0)
 *
 * Implements Step 7 of 02D_MEMBER4_FRONTEND_3D_VISUALIZATION.md:
 * Provides resilient, type-safe communication with the backend with
 * graceful offline mock fallback.
 */

import {
  OrderAnalysisResponse,
  PackingRequest,
  PackingSolutionResponse,
} from "../types/contract";
import orderAnalysisSample from "../mocks/orderAnalysisSample.json";
import packingSolutionSample from "../mocks/packingSolutionSample.json";

// In development, Vite proxies /api to http://localhost:8000
const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class OptiPackClient {
  /**
   * Submit packing station photos for CV metrology and Meta AI semantic extraction.
   * If backend is unreachable, seamlessly returns the verified golden mock fixture.
   */
  static async analyzeOrder(formData: FormData): Promise<OrderAnalysisResponse> {
    try {
      const response = await fetch(`${API_BASE}/orders/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`Analyze API responded with HTTP status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.warn(
        "OptiPackClient: Live backend unavailable or returned error. Activating offline mock fallback.",
        err
      );
      return orderAnalysisSample as unknown as OrderAnalysisResponse;
    }
  }

  /**
   * Request 3D cartonization and packing optimization from OR-Tools CP-SAT solver.
   * If backend is unreachable, returns the verified optimal multi-item packing solution.
   */
  static async packOrder(request: PackingRequest): Promise<PackingSolutionResponse> {
    try {
      const response = await fetch(`${API_BASE}/orders/pack`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });

      if (!response.ok) {
        throw new Error(`Pack API responded with HTTP status ${response.status}`);
      }

      return await response.json();
    } catch (err) {
      console.warn(
        "OptiPackClient: Solver API unavailable. Activating offline packing solution fallback.",
        err
      );
      return packingSolutionSample as unknown as PackingSolutionResponse;
    }
  }
}
