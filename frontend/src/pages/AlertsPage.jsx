import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth";
import { can } from "../permissions";
import { percent, risk } from "../theme";
import RiskBadge from "../components/RiskBadge";
import { Recommendations } from "../components/ExplanationPanel";
import { Banner, Card, ErrorNote, PageTitle, Skeleton, StatTile, Toggle } from "../components/ui";

const STATUS_LABEL = { open: "Open", acknowledged: "Acknowledged", resolved: "Resolved" };

function Workflow({ alert, onDone, onError }) {
  const { user } = useAuth();
  const client = useQueryClient();
  const [note, setNote] = useState("");
  const [assignee, setAssignee] = useState("");
  const people = useQuery({ queryKey: ["assignable-users"], queryFn: api.assignableUsers, enabled: can(user, "alerts.write") });

  const refresh = (message) => {
    client.invalidateQueries({ queryKey: ["alerts"] });
    client.invalidateQueries({ queryKey: ["alert-inbox"] });
    client.invalidateQueries({ queryKey: ["kpis"] });
    onDone(message);
  };
  const acknowledge = useMutation({
    mutationFn: () => api.acknowledgeAlert(alert.id, { note: note || null }),
    onSuccess: () => refresh(`Alert ${alert.id} acknowledged.`),
    onError: (error) => onError(errorMessage(error, "Could not acknowledge the alert.")),
  });
  const resolve = useMutation({
    mutationFn: () => api.resolveAlert(alert.id, { resolution_note: note }),
    onSuccess: () => refresh(`Alert ${alert.id} resolved.`),
    onError: (error) => onError(errorMessage(error, "Could not resolve the alert.")),
  });
  const assign = useMutation({
    mutationFn: () => api.assignAlert(alert.id, Number(assignee)),
    onSuccess: () => refresh(`Alert ${alert.id} assigned.`),
    onError: (error) => onError(errorMessage(error, "Could not assign the alert.")),
  });

  if (!can(user, "alerts.write") || alert.status === "resolved") return null;
  return (
    <div className="mt-4 border-t border-[#eee8db] pt-4">
      <label className="block text-sm font-medium text-slate-700">
        Note
        <input
          value={note}
          onChange={(event) => setNote(event.target.value)}
          placeholder="Required to resolve, optional to acknowledge"
          className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#0d9488]"
        />
      </label>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {alert.status === "open" && (
          <button onClick={() => acknowledge.mutate()} disabled={acknowledge.isPending} className="rounded-lg bg-[#102a43] px-3 py-2 text-sm font-semibold text-white disabled:opacity-60">
            {acknowledge.isPending ? "Working…" : "Acknowledge"}
          </button>
        )}
        <button onClick={() => resolve.mutate()} disabled={resolve.isPending || note.trim().length < 3} className="rounded-lg bg-[#0f766e] px-3 py-2 text-sm font-semibold text-white disabled:opacity-60">
          {resolve.isPending ? "Working…" : "Resolve"}
        </button>
        <select
          aria-label="Assign to"
          value={assignee}
          onChange={(event) => setAssignee(event.target.value)}
          className="rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-[#102a43]"
        >
          <option value="">Assign to…</option>
          {(people.data || []).map((person) => <option key={person.id} value={person.id}>{person.official_name}</option>)}
        </select>
        <button onClick={() => assign.mutate()} disabled={!assignee || assign.isPending} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-[#102a43] disabled:opacity-40">
          Assign
        </button>
      </div>
      {note.trim().length > 0 && note.trim().length < 3 && <p className="mt-2 text-xs text-amber-800">A resolution note needs at least 3 characters.</p>}
    </div>
  );
}

function AlertCard({ alert, onDone, onError }) {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  return (
    <article className="gov-paper rounded-lg p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <RiskBadge category={alert.severity} />
            <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-700">{STATUS_LABEL[alert.status] || alert.status}</span>
            <span className="text-xs text-slate-500">{alert.category}</span>
          </div>
          <h2 className="mt-2 font-bold text-[#102a43]">{alert.project_name || alert.project_id}</h2>
          <p className="text-sm text-slate-600">{alert.district}, {alert.state} · score {Math.round(alert.risk_score_at_trigger)} of 100</p>
          <p className="mt-1 text-xs text-slate-500">Raised {new Date(alert.created_at).toLocaleString()}</p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button onClick={() => navigate("/projects", { state: { focusProjectId: alert.project_id } })} className="rounded border border-slate-300 px-3 py-1.5 text-xs font-semibold text-[#102a43] hover:bg-amber-50">
            Open project
          </button>
          <button onClick={() => setOpen(!open)} aria-expanded={open} className="rounded border border-slate-300 px-3 py-1.5 text-xs font-semibold text-[#102a43] hover:bg-amber-50">
            {open ? "Hide detail" : "Detail"}
          </button>
        </div>
      </div>

      {alert.drivers?.length > 0 && (
        <ul className="mt-3 flex flex-wrap gap-2">
          {alert.drivers.map((driver) => (
            <li key={driver.driver} className="rounded bg-[#f4efe4] px-2 py-1 text-xs font-semibold text-[#102a43]">
              {driver.driver} <span className="font-normal text-slate-500">{percent(driver.share)}</span>
            </li>
          ))}
        </ul>
      )}

      {open && (
        <div className="mt-4 space-y-4">
          <p className="text-sm text-slate-700">{alert.message}</p>
          {alert.recommendations?.length > 0 && (
            <div>
              <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Recommended actions</p>
              <div className="mt-2"><Recommendations recommendations={alert.recommendations} compact /></div>
            </div>
          )}
          <div className="flex flex-wrap gap-2 text-xs text-slate-600">
            {(alert.deliveries || []).map((delivery, index) => (
              <span key={`${delivery.channel}-${index}`} className="rounded bg-slate-100 px-2 py-1">{delivery.channel}: {delivery.status}</span>
            ))}
          </div>
          {alert.acknowledged_at && <p className="text-xs text-slate-500">Acknowledged {new Date(alert.acknowledged_at).toLocaleString()}</p>}
          {alert.resolved_at && <p className="text-xs text-slate-500">Resolved {new Date(alert.resolved_at).toLocaleString()} · {alert.resolution_note}</p>}
          <Workflow alert={alert} onDone={onDone} onError={onError} />
        </div>
      )}
    </article>
  );
}

export default function AlertsPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [status, setStatus] = useState("open");
  const [severity, setSeverity] = useState("");
  const [mine, setMine] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const query = useQuery({
    queryKey: ["alerts", status, severity, mine],
    queryFn: () => api.alerts({ status: status || undefined, severity: severity || undefined, assigned_to_me: mine, limit: 200 }),
  });
  const scan = useMutation({
    mutationFn: api.scanNow,
    onSuccess: (result) => {
      setError("");
      setMessage(`Scan complete: ${result.scored} projects re-scored, ${result.snapshots} snapshots recorded, ${result.triggered} new alerts.`);
      client.invalidateQueries({ queryKey: ["alerts"] });
      client.invalidateQueries({ queryKey: ["kpis"] });
    },
    onError: (failure) => setError(errorMessage(failure, "Scan failed.")),
  });

  const alerts = query.data || [];
  const counts = alerts.reduce((totals, alert) => ({ ...totals, [alert.severity]: (totals[alert.severity] || 0) + 1 }), {});

  return (
    <>
      <PageTitle eyebrow="Operational signals" heading="Risk alerts">
        Each alert carries the delay drivers that raised it and the corrective actions ranked by their modelled effect.
      </PageTitle>
      <Banner tone="success" onDismiss={() => setMessage("")}>{message}</Banner>
      <Banner tone="error" onDismiss={() => setError("")}>{error}</Banner>
      <ErrorNote query={query} label="Alerts unavailable." />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Shown" value={alerts.length} hint={status ? STATUS_LABEL[status] : "All statuses"} />
        <StatTile label="High severity" value={counts.High || 0} tone="High" />
        <StatTile label="Medium severity" value={counts.Medium || 0} tone="Medium" />
        <StatTile label="Low severity" value={counts.Low || 0} tone="Low" />
      </div>

      <div className="my-5 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-end gap-4">
          <div>
            <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Status</span>
            <Toggle label="Status" value={status} options={[["open", "Open"], ["acknowledged", "Acknowledged"], ["resolved", "Resolved"], ["", "All"]]} onChange={setStatus} />
          </div>
          <div>
            <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Severity</span>
            <Toggle label="Severity" value={severity} options={[["", "All"], ["High", "High"], ["Medium", "Medium"], ["Low", "Low"]]} onChange={setSeverity} />
          </div>
          <label className="flex items-center gap-2 pb-1.5 text-sm font-medium text-slate-700">
            <input type="checkbox" checked={mine} onChange={(event) => setMine(event.target.checked)} className="h-4 w-4 rounded border-slate-400" />
            Assigned to me
          </label>
        </div>
        {can(user, "alerts.read") && (
          <button onClick={() => scan.mutate()} disabled={scan.isPending} className="rounded-lg bg-[#b7791f] px-4 py-2 text-sm font-bold text-white disabled:opacity-60">
            {scan.isPending ? "Scanning…" : "Run risk scan now"}
          </button>
        )}
      </div>

      <div className="space-y-3">
        {query.isLoading && [1, 2, 3].map((row) => <Skeleton key={row} className="h-32" />)}
        {alerts.map((alert) => (
          <AlertCard key={alert.id} alert={alert} onDone={setMessage} onError={setError} />
        ))}
        {!query.isLoading && !alerts.length && (
          <Card><p className="text-sm text-slate-500">No alerts match these filters. A scan raises an alert for every project above the configured risk threshold.</p></Card>
        )}
      </div>
    </>
  );
}
