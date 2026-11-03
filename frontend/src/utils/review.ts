// Preserve the model's uncertainty and its original review flag for audit.
export interface ReviewableMeasurement {
  uncertainty_info?: {
    height_sigma_mm: number;
    requires_user_review: boolean;
  };
  review_acknowledged?: boolean;
}

export function needsMeasurementReview(item: ReviewableMeasurement): boolean {
  return !item.review_acknowledged &&
    (Boolean(item.uncertainty_info?.requires_user_review) ||
      (item.uncertainty_info?.height_sigma_mm ?? 0) > 8);
}
