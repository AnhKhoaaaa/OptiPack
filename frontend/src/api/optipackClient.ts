/**
 * OptiPack API client. Live requests never silently produce demo measurements
 * or a fabricated successful packing plan.
 */
import type {
  OrderAnalysisResponse,
  PackingRequest,
  PackingSolutionResponse,
} from "../types/contract";

const API_BASE = import.meta.env.VITE_API_BASE_URL || "/api/v1";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly data: unknown = null
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function parseResponse<T>(response: Response): Promise<T> {
  if (response.ok) {
    return (await response.json()) as T;
  }
  let detail: unknown = null;
  try {
    detail = await response.json();
  } catch {
    // An empty/invalid error response is still an HTTP failure.
  }
  const extractedReason =
    detail && typeof detail === "object" && "detail" in detail
      ? (detail as { detail: unknown }).detail
      : null;
  const reason =
    (typeof extractedReason === "string" && extractedReason.trim()
      ? extractedReason.trim()
      : typeof extractedReason === "object" && extractedReason !== null
      ? JSON.stringify(extractedReason)
      : null) ||
    response.statusText?.trim() ||
    "Request failed";
  throw new ApiError(
    response.status,
    `Backend Error (${response.status}): ${reason}`,
    detail
  );
}

export class OptiPackClient {
  static async analyzeOrder(formData: FormData): Promise<OrderAnalysisResponse> {
    const response = await fetch(`${API_BASE}/orders/analyze`, {
      method: "POST",
      body: formData,
    });
    return parseResponse<OrderAnalysisResponse>(response);
  }

  static async packOrder(request: PackingRequest): Promise<PackingSolutionResponse> {
    const response = await fetch(`${API_BASE}/orders/pack`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    });
    return parseResponse<PackingSolutionResponse>(response);
  }
}
