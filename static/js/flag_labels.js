/** Plain-English descriptions for pipeline flags (operator-facing). */

export const CREDIBILITY_FLAG_LABELS = {
  low_ocr_confidence: "OCR confidence below threshold — text may be misread.",
  missing_required_fields: "One or more required BDN fields could not be extracted.",
  invalid_imo_format: "IMO number is not exactly 7 digits.",
  reversed_timestamps: "Pumping end time appears before start time.",
  suspicious_pumping_duration: "Claimed pumping duration is unusual for the quantity.",
  font_inconsistency: "Inconsistent fonts suggest possible tampering.",
  contains_correction_keywords: "Document contains correction or amendment language.",
  handwritten_document: "Document classified as handwritten — higher fraud risk.",
};

export const ANOMALY_FLAG_LABELS = {
  barge_ais_missing: "No AIS track for bunker barge during delivery window.",
  vessel_speed_anomaly: "Vessel moved faster than expected during claimed bunkering.",
  co_location_duration_mismatch: "Vessel and barge were not co-located for the claimed duration.",
  port_coordinate_mismatch: "AIS positions do not match the declared port.",
  quantity_infeasible: "Quantity is not achievable at typical pump rates for the duration.",
  ais_gap_exceeded: "AIS reporting gaps exceed the configured limit.",
  ais_unavailable: "AIS provider unavailable — geolocation could not be verified.",
  vessel_identity_unresolved: "BDN IMO and name point to different vessels.",
  pipeline_error: "An internal error occurred during validation.",
  synthetic_ais_demo: "AIS unavailable — demo tracks generated at declared port for ML scoring.",
};

export const IDENTITY_FLAG_LABELS = {
  vessel_name_fuzzy_match: "Vessel name matched registry via fuzzy string comparison.",
  vessel_name_embedding_match: "Vessel name matched registry via semantic similarity.",
  vessel_identity_unresolved: "Identity could not be resolved to a single vessel.",
};

export function describeFlags(flags, labelMap) {
  if (!flags || !flags.length) return [];
  return flags.map((f) => ({
    code: f,
    description: labelMap[f] || f.replace(/_/g, " "),
  }));
}
