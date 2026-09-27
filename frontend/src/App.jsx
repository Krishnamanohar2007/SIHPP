import { useState } from "react";
import { Link, NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import DashboardPage from "./pages/DashboardPage";
import MapPage from "./pages/MapPage";
import ProjectsPage from "./pages/ProjectsPage";
import AlertsPage from "./pages/AlertsPage";
import ModelsPage from "./pages/ModelsPage";
import AuditPage from "./pages/AuditPage";
import IntegrationPage from "./pages/IntegrationPage";
import NewProjectPage from "./pages/NewProjectPage";
import HomePage from "./pages/HomePage";
import LoginPage from "./pages/LoginPage";
import RegisterPage from "./pages/RegisterPage";
import AdminPage from "./pages/AdminPage";
import { useAuth } from "./auth";
import { ROLE_LABELS, can, canCreateProject } from "./permissions";

/** Navigation entries, each gated by the permission the page needs. */
const LINKS = [
  { to: "/dashboard", label: "Dashboard", allow: (user) => can(user, "analytics.read") },
  { to: "/map", label: "Risk map", allow: (user) => can(user, "projects.read") },
  { to: "/projects", label: "Projects", allow: (user) => can(user, "projects.read") },
  { to: "/projects/new", label: "New project", allow: canCreateProject },
  { to: "/alerts", label: "Alerts", allow: (user) => can(user, "alerts.read") },
  { to: "/models", label: "Models", allow: (user) => can(user, "analytics.read") },
  { to: "/audit", label: "Audit", allow: (user) => can(user, "audit.read") },
  { to: "/integration", label: "Integration", allow: (user) => can(user, "integration.manage") },
  { to: "/admin", label: "Admin", allow: (user) => can(user, "users.review") },
];

const linkClass = ({ isActive }) =>
  `block rounded px-3 py-2 text-sm font-semibold transition ${isActive ? "bg-white/15 text-white" : "text-slate-200 hover:bg-white/10 hover:text-white"}`;

function Mark() {
  return (
    <div aria-hidden="true" className="grid h-9 w-9 place-items-center rounded-lg bg-[#0f766e]">
      <svg viewBox="0 0 48 48" className="h-6 w-6 fill-none stroke-white" strokeWidth="3">
        <path d="M5 35c9-17 27-21 38-22-4 14-14 25-38 22Z" />
        <path d="M7 35c12-4 19-10 28-20" />
        <path d="M27 12V6m-7 8V8m14 1v7" />
      </svg>
    </div>
  );
}

/**
 * Route guard. `permission` mirrors the server check for that page; the server
 * still enforces it, so this only avoids showing a page that would fail.
 */
function Protected({ children, permission }) {
  const { user } = useAuth();
  const location = useLocation();
  if (!user) return <Navigate to="/login" replace state={{ from: location }} />;
  if (permission && !can(user, permission)) return <Navigate to="/dashboard" replace />;
  return children;
}

export default function App() {
  const [open, setOpen] = useState(false);
  const location = useLocation();
  const { user, signOut } = useAuth();
  const bare = location.pathname === "/home" || ["/login", "/register"].includes(location.pathname);
  const visible = LINKS.filter((link) => link.allow(user));

  const nav = (
    <nav className="flex flex-col gap-1 md:flex-row md:items-center md:gap-0.5">
      {visible.map((link) => (
        <NavLink key={link.to} to={link.to} end onClick={() => setOpen(false)} className={linkClass}>
          {link.label}
        </NavLink>
      ))}
    </nav>
  );

  return (
    <div className="min-h-screen bg-[#f7f4ec]">
      <header className="gov-masthead sticky top-0 z-[1100]">
        <div className="mx-auto flex max-w-[1600px] items-center justify-between gap-4 px-4 py-3 sm:px-6">
          <Link to={user ? "/dashboard" : "/login"} className="flex shrink-0 items-center gap-3 text-white">
            <Mark />
            <span>
              <span className="block text-lg font-bold leading-tight">Bhoomi Setu</span>
              <span className="hidden text-[10px] font-bold uppercase tracking-[.14em] text-amber-200 sm:block">Land acquisition intelligence</span>
            </span>
          </Link>

          <div className="hidden min-w-0 items-center gap-3 lg:flex">
            {user && nav}
            {user ? (
              <div className="flex shrink-0 items-center gap-3 border-l border-white/20 pl-3">
                <span className="text-right text-xs leading-tight text-slate-200">
                  <span className="block font-semibold text-white">{user.name}</span>
                  <span>{ROLE_LABELS[user.role] || user.role}</span>
                </span>
                <button onClick={signOut} className="rounded border border-white/30 px-3 py-2 text-sm font-semibold text-white hover:bg-white/10">Sign out</button>
              </div>
            ) : (
              <Link to="/login" className="rounded bg-[#b7791f] px-3 py-2 text-sm font-bold text-white">Sign in</Link>
            )}
          </div>

          <button aria-label="Toggle navigation" aria-expanded={open} onClick={() => setOpen(!open)} className="rounded border border-white/30 px-3 py-2 text-sm font-semibold text-white lg:hidden">
            {open ? "Close" : "Menu"}
          </button>
        </div>

        {open && (
          <div className="border-t border-white/15 px-4 py-3 lg:hidden">
            {user && nav}
            <div className="mt-2">
              {user ? (
                <button onClick={signOut} className="rounded border border-white/30 px-3 py-2 text-sm font-semibold text-white">Sign out</button>
              ) : (
                <Link onClick={() => setOpen(false)} to="/login" className="block rounded bg-[#b7791f] px-3 py-2 text-sm font-bold text-white">Sign in</Link>
              )}
            </div>
          </div>
        )}
      </header>

      <main className={bare ? "" : "mx-auto max-w-[1600px] p-4 sm:p-6 lg:p-8"}>
        <Routes>
          <Route path="/" element={<Navigate to="/login" replace />} />
          <Route path="/home" element={<HomePage />} />
          <Route path="/login" element={<LoginPage />} />
          <Route path="/register" element={<RegisterPage />} />
          <Route path="/dashboard" element={<Protected permission="analytics.read"><DashboardPage /></Protected>} />
          <Route path="/map" element={<Protected permission="projects.read"><MapPage /></Protected>} />
          <Route path="/projects" element={<Protected permission="projects.read"><ProjectsPage /></Protected>} />
          <Route path="/projects/new" element={<Protected permission="projects.write"><NewProjectPage /></Protected>} />
          <Route path="/alerts" element={<Protected permission="alerts.read"><AlertsPage /></Protected>} />
          <Route path="/models" element={<Protected permission="analytics.read"><ModelsPage /></Protected>} />
          <Route path="/audit" element={<Protected permission="audit.read"><AuditPage /></Protected>} />
          <Route path="/integration" element={<Protected permission="integration.manage"><IntegrationPage /></Protected>} />
          <Route path="/admin" element={<Protected permission="users.review"><AdminPage /></Protected>} />
          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </main>
    </div>
  );
}
