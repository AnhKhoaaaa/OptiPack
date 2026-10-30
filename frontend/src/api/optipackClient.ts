/**
 * OptiPack API Client (Contract v1.0.0)
 *
 * Implements Step 7 of 02D_MEMBER4_FRONTEND_3D_VISUALIZATION.md:
 * Provides resilient, type-safe communication with the backend.
 * Distinguishes genuine HTTP 4xx/5xx errors (for transparent fullstack debugging)
 * from server-down network failures (which trigger offline mock fallback for pitching).
 */

import {
  OrderAnalysisResponse,
  PackingRequest,
  PackingSolutionResponse,
} from "../types/contract";
import orderAnalysisSample from "../mocks/orderAnalysisSample.json";
import packingSolutionSample from "../mocks/packingSolutionSample.json";
import preset2PackingSolution from "../mocks/preset2PackingSolution.json";
import preset3MultiCartonSplit from "../mocks/preset3MultiCartonSplit.json";

// In development, Vite proxies /api to http://localhost:8000
const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  status: number;
  data: unknown;

  constructor(status: number, message: string, data?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.data = data;
  }
}

async function handleResponseError(response: Response): Promise<never> {
  let errorDetail = `HTTP ${response.status} ${response.statusText}`;
  let errorData: unknown = null;

  try {
    const text = await response.text();
    if (text && text.trim().length > 0) {
      try {
        errorData = JSON.parse(text);
        if (typeof errorData === "object" && errorData !== null && "detail" in errorData) {
          const detail = (errorData as { detail: unknown }).detail;
          errorDetail = `Backend Error (${response.status}): ${
            typeof detail === "string" ? detail : JSON.stringify(detail)
          }`;
        } else {
          errorDetail = `Backend Error (${response.status}): ${text}`;
        }
      } catch {
        errorDetail = `Backend Error (${response.status}): ${text}`;
      }
    }
  } catch {
    // text() failed or empty
  }

  // If response is HTTP 500 with empty body, Vite proxy returned this because backend is offline
  if (response.status >= 500 && !errorData && (!errorDetail || errorDetail.includes("500 Internal Server Error"))) {
    throw new TypeError("Failed to fetch: backend proxy target unreachable");
  }

  console.error(`[OptiPackClient] API Error [${response.status}]:`, errorDetail, errorData);
  throw new ApiError(response.status, errorDetail, errorData);
}

export class OptiPackClient {
  /**
   * Submit packing station photos for CV metrology and Meta AI semantic extraction.
   * If backend is offline/unreachable, gracefully returns the verified golden mock fixture.
   * If backend is live and returns HTTP 4xx/5xx, re-throws ApiError for debugging.
   */
  static async analyzeOrder(formData: FormData): Promise<OrderAnalysisResponse> {
    try {
      const response = await fetch(`${API_BASE}/orders/analyze`, {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        await handleResponseError(response);
      }

      return await response.json();
    } catch (err) {
      // Genuine HTTP 4xx/5xx from running server should NOT be masked
      if (err instanceof ApiError) {
        throw err;
      }

      console.warn(
        "OptiPackClient: Live backend unavailable (server offline). Activating offline mock fallback.",
        err
      );
      return orderAnalysisSample as unknown as OrderAnalysisResponse;
    }
  }

  /**
   * Request 3D cartonization and packing optimization from OR-Tools CP-SAT solver.
   * If backend is offline/unreachable, gracefully returns the matching preset mock solution.
   * If backend is live and returns HTTP 4xx/5xx, re-throws ApiError for debugging.
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
        await handleResponseError(response);
      }

      return await response.json();
    } catch (err) {
      // Genuine HTTP 4xx/5xx from running server should NOT be masked
      if (err instanceof ApiError) {
        throw err;
      }

      console.warn(
        "OptiPackClient: Solver API unavailable (server offline). Activating offline packing solution fallback.",
        err
      );
      if (request.analysis_id === "ord_20261027_002_review") {
        return preset2PackingSolution as unknown as PackingSolutionResponse;
      }
      if (request.analysis_id === "ord_20261027_003_split") {
        return preset3MultiCartonSplit as unknown as PackingSolutionResponse;
      }
      return packingSolutionSample as unknown as PackingSolutionResponse;
    }
  }
}
