/**
 * Client-side mirror of the server permission matrix (see docs/rbac.md).
 *
 * This only decides what the interface offers. The server enforces every
 * permission and every project scope independently, so a stale or tampered copy
 * here cannot grant access - it can only hide or show controls.
 */

const MATRIX = {
  ADMIN: ["projects.read", "projects.write", "projects.outcome", "analytics.read", "alerts.read",
          "alerts.write", "audit.read", "models.manage", "integration.manage", "users.review", "users.manage"],
  POLICY_MAKER: ["projects.read", "analytics.read", "alerts.read", "audit.read", "models.manage", "integration.manage"],
  STATE_GOVERNMENT: ["projects.read", "analytics.read", "alerts.read", "audit.read"],
  DISTRICT_ADMINISTRATION: ["projects.read", "projects.write", "projects.outcome", "analytics.read", "alerts.read", "alerts.write"],
  LAND_ACQUISITION_AUTHORITY: ["projects.read", "projects.write", "projects.outcome", "analytics.read", "alerts.read", "alerts.write"],
  PROJECT_IMPLEMENTING_AGENCY: ["projects.read", "analytics.read", "alerts.read", "alerts.write"],
};

export const ROLES = Object.keys(MATRIX);

export const ROLE_LABELS = {
  ADMIN: "Administrator",
  POLICY_MAKER: "Policy maker",
  STATE_GOVERNMENT: "State government",
  DISTRICT_ADMINISTRATION: "District administration",
  LAND_ACQUISITION_AUTHORITY: "Land acquisition authority",
  PROJECT_IMPLEMENTING_AGENCY: "Project implementing agency",
};

export function can(user, permission) {
  return Boolean(user && (MATRIX[user.role] || []).includes(permission));
}

/**
 * Only an administrator or a district user may create a project. An authority may
 * edit a project assigned to it but cannot create a new one, which matches the
 * server check in POST /projects.
 */
export function canCreateProject(user) {
  return Boolean(user && ["ADMIN", "DISTRICT_ADMINISTRATION"].includes(user.role));
}
