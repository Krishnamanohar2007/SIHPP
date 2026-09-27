import { useState } from "react";
import { Link, Navigate, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../auth";

export default function LoginPage() {
  const { user, signIn } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  if (user) return <Navigate to="/dashboard" replace />;

  async function submit(event) {
    event.preventDefault(); setError(""); setBusy(true);
    try { await signIn(email, password); navigate(location.state?.from?.pathname || "/dashboard", { replace: true }); }
    catch (cause) { setError(cause.response?.data?.detail || "Sign in failed. Check official email and password."); }
    finally { setBusy(false); }
  }

  return <main className="grid min-h-[calc(100vh-75px)] place-items-center px-4 py-12"><form onSubmit={submit} className="gov-paper w-full max-w-md p-7 sm:p-9"><p className="text-xs font-bold uppercase tracking-[.16em] text-[#0f766e]">Secure workspace</p><h1 className="mt-2 text-3xl font-bold text-[#102a43]">Sign in</h1><p className="mt-3 text-sm leading-6 text-slate-600">Use approved official account to access project data and risk intelligence.</p><label className="mt-7 block text-sm font-semibold text-slate-700">Official email<input required type="email" value={email} onChange={(event) => setEmail(event.target.value)} className="mt-2 w-full rounded border border-slate-300 bg-white px-3 py-2.5" autoComplete="username" /></label><label className="mt-4 block text-sm font-semibold text-slate-700">Password<input required type="password" minLength="12" value={password} onChange={(event) => setPassword(event.target.value)} className="mt-2 w-full rounded border border-slate-300 bg-white px-3 py-2.5" autoComplete="current-password" /></label>{error && <p role="alert" className="mt-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">{error}</p>}<button disabled={busy} className="mt-6 w-full rounded bg-[#0f766e] px-4 py-3 font-bold text-white disabled:opacity-60">{busy ? "Signing in…" : "Sign in"}</button><p className="mt-5 text-center text-sm text-slate-600">Need access? <Link className="font-semibold text-[#0f766e]" to="/register">Submit registration request</Link></p></form></main>;
}
