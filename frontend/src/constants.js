// core.py's Sector literal, verbatim — the frozen scoring engine's sector set.
export const SECTORS = [
  "water", "roads", "health", "education", "electricity",
  "sanitation", "drainage", "transport", "livelihood", "other",
];

// §1 schema's asset sector enum — a subset assets/works actually live in.
export const ASSET_SECTORS = ["water", "health", "education", "roads", "sanitation", "drainage"];

export const WARDS = ["W07", "W11", "W14", "W19", "W22", "W26"];

export const REPORTED_STATUSES = [
  { value: "", label: "(no status)" },
  { value: "not_working", label: "Not working" },
  { value: "degraded", label: "Degraded" },
];
