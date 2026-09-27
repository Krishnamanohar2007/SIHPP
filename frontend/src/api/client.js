import axios from "axios";

const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000" });

client.interceptors.request.use((config) => {
  const token = sessionStorage.getItem("bhoomi_setu_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

const get = (path, params) => client.get(path, params ? { params } : undefined).then((response) => response.data);
const post = (path, body) => client.post(path, body).then((response) => response.data);

/** Extract a readable message from a FastAPI error body. */
export function errorMessage(error, fallback = "Request failed.") {
  const detail = error?.response?.data?.detail;
  if (Array.isArray(detail)) return detail.map((item) => item.msg || item.detail || "").filter(Boolean).join(". ");
  return detail || error?.message || fallback;
}

export const api = {
  // authentication and accounts
  login: (payload) => post("/auth/login", payload),
  me: () => get("/auth/me"),
  locations: (state) => get("/auth/locations", state ? { state } : {}),
  register: (payload) => post("/auth/register", payload),
  assignableUsers: () => get("/auth/assignable-users"),

  // administration
  pendingRegistrations: () => get("/auth/admin/registrations"),
  approveRegistration: (id, payload) => post(`/auth/admin/registrations/${id}/approve`, payload),
  rejectRegistration: (id, payload) => post(`/auth/admin/registrations/${id}/reject`, payload),
  registrationDocument: (id) => client.get(`/auth/admin/registrations/${id}/document`, { responseType: "blob" }).then((r) => r.data),
  users: () => get("/auth/admin/users"),
  assignRole: (id, role) => post(`/auth/admin/users/${id}/role`, { role }),
  assignProject: (userId, projectId) => post(`/auth/admin/users/${userId}/projects/${projectId}`),
  audit: (params) => get("/auth/admin/audit", params),
  auditActions: () => get("/auth/admin/audit/actions"),

  // projects
  projects: (params) => get("/projects", params),
  project: (id) => get(`/projects/${id}`),
  geo: (params) => get("/projects/geo", params),
  filterOptions: (params) => get("/projects/filter-options", params),
  reverseLocation: (params) => get("/locations/reverse", params),
  createProject: (payload) => post("/projects", payload),
  updateProject: (id, payload) => client.put(`/projects/${id}`, payload).then((r) => r.data),
  predict: (id) => post(`/projects/${id}/predict`),
  explain: (id, stage) => get(`/projects/${id}/explain`, stage ? { stage } : undefined),
  projectTimeline: (id, days = 365) => get(`/projects/${id}/timeline`, { days }),
  recordOutcome: (id, payload) => post(`/projects/${id}/outcome`, payload),
  predictPreview: (payload) => post("/projects/predict-preview", payload),

  // analytics
  kpis: (params) => get("/analytics/kpis", params),
  trends: (params) => get("/analytics/trends", params),
  timeline: (params) => get("/analytics/timeline", params),
  comparative: (params) => get("/analytics/comparative", params),
  drivers: (params) => get("/analytics/drivers", params),
  priority: (params) => get("/analytics/priority", params),
  stageExposure: (params) => get("/analytics/stage-exposure", params),
  summary: () => get("/stats/summary"),

  // alerts
  alerts: (params) => get("/alerts", params),
  alertInbox: (params) => get("/alerts/inbox", params),
  scanNow: () => post("/alerts/scan-now"),
  acknowledgeAlert: (id, payload) => post(`/alerts/${id}/acknowledge`, payload),
  assignAlert: (id, userId) => post(`/alerts/${id}/assign`, { user_id: userId }),
  resolveAlert: (id, payload) => post(`/alerts/${id}/resolve`, payload),

  // model registry
  activeModel: () => get("/models/active"),
  modelVersions: () => get("/models"),
  retrain: (payload) => post("/models/retrain", payload),
  activateModel: (version) => post(`/models/${version}/activate`),
  reloadModel: () => post("/models/reload"),
  rescore: (snapshot = true) => client.post("/models/rescore", null, { params: { snapshot } }).then((r) => r.data),

  // integration keys
  integrationScopes: () => get("/integration/scopes"),
  apiKeys: () => get("/integration/api-keys"),
  createApiKey: (payload) => post("/integration/api-keys", payload),
  revokeApiKey: (id) => client.delete(`/integration/api-keys/${id}`).then((r) => r.data),
};

export default client;
