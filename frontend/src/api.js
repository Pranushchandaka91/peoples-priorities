const BASE = "/api";

async function req(path, opts) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...opts,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status} ${path}: ${body}`);
  }
  return res.json();
}

export const api = {
  getRanking: (budgetLakh) => req(`/ranking?budget_lakh=${budgetLakh}`),
  getRationale: (workId) => req(`/works/${workId}/rationale`),
  postComplaint: (body) => req(`/complaints`, { method: "POST", body: JSON.stringify(body) }),
  getDisputes: (params = {}) => {
    const qs = new URLSearchParams(params).toString();
    return req(`/disputes${qs ? `?${qs}` : ""}`);
  },
  getVerificationTasks: (status = "pending") => req(`/verification-tasks?status=${status}`),
  closeVerificationTask: (taskId, body) =>
    req(`/verification-tasks/${taskId}/close`, { method: "POST", body: JSON.stringify(body) }),
  getWeights: () => req(`/weights`),
  postWeights: (body) => req(`/weights`, { method: "POST", body: JSON.stringify(body) }),

  getAssets: (wardId, sector) => req(`/assets?ward_id=${wardId}&sector=${sector}`),

  // §9 live demo mode
  getConfig: () => req(`/config`),
  parseComplaint: (rawText) => req(`/complaints/parse`, { method: "POST", body: JSON.stringify({ raw_text: rawText }) }),
  peekReality: (assetId) => req(`/admin/reality/${assetId}`),
  resetDemo: () => req(`/admin/reset`, { method: "POST" }),
};
