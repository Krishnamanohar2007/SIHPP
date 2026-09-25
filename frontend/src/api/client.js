import axios from "axios";

const client = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || "http://localhost:8000" });

export const api = {
  summary: () => client.get("/stats/summary").then((r) => r.data),
  projects: (params) => client.get("/projects", { params }).then((r) => r.data),
  project: (id) => client.get(`/projects/${id}`).then((r) => r.data),
  filterOptions: (params) => client.get("/projects/filter-options", { params }).then((r) => r.data),
  reverseLocation: (params) => client.get("/locations/reverse", { params }).then((r) => r.data),
  geo: () => client.get("/projects/geo").then((r) => r.data),
  alerts: () => client.get("/alerts").then((r) => r.data),
  explain: (id) => client.get(`/projects/${id}/explain`).then((r) => r.data),
  predict: (id) => client.post(`/projects/${id}/predict`).then((r) => r.data),
  predictPreview: (payload) => client.post("/projects/predict-preview", payload).then((r) => r.data),
  createProject: (payload) => client.post("/projects", payload).then((r) => r.data),
};

export default client;
