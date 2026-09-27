import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Card, ErrorNote, PageTitle, Select, Skeleton } from "../components/ui";

const PAGE = 50;

/** Render an audit detail object compactly, including before/after diffs. */
function Details({ details }) {
  const entries = Object.entries(details || {});
  if (!entries.length) return <span className="text-slate-400">—</span>;
  return (
    <dl className="space-y-0.5 text-xs">
      {entries.map(([key, value]) => {
        if (key === "changes" && value && typeof value === "object") {
          const changes = Object.entries(value);
          if (!changes.length) return null;
          return (
            <div key={key}>
              {changes.map(([field, change]) => (
                <div key={field} className="flex flex-wrap gap-1">
                  <dt className="font-semibold text-slate-600">{field.replaceAll("_", " ")}:</dt>
                  <dd className="text-slate-500"><s>{String(change.from)}</s> → {String(change.to)}</dd>
                </div>
              ))}
            </div>
          );
        }
        return (
          <div key={key} className="flex flex-wrap gap-1">
            <dt className="font-semibold text-slate-600">{key.replaceAll("_", " ")}:</dt>
            <dd className="min-w-0 break-all text-slate-500">{typeof value === "object" ? JSON.stringify(value) : String(value)}</dd>
          </div>
        );
      })}
    </dl>
  );
}

export default function AuditPage() {
  const [filters, setFilters] = useState({ action: "", target_type: "", target_id: "" });
  const [offset, setOffset] = useState(0);
  const choices = useQuery({ queryKey: ["audit-actions"], queryFn: api.auditActions });
  const query = useQuery({
    queryKey: ["audit", filters, offset],
    queryFn: () => api.audit({
      action: filters.action || undefined,
      target_type: filters.target_type || undefined,
      target_id: filters.target_id || undefined,
      limit: PAGE,
      offset,
    }),
  });
  const update = (key, value) => { setFilters({ ...filters, [key]: value }); setOffset(0); };
  const items = query.data?.items || [];
  const total = query.data?.total || 0;

  return (
    <>
      <PageTitle eyebrow="Accountability" heading="Audit trail">
        Every state change: account review, project edits, recorded outcomes, alert workflow, model activation and integration keys.
      </PageTitle>
      <ErrorNote query={query} label="Audit trail unavailable." />

      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <Select label="Action" value={filters.action} values={choices.data?.actions || []} onChange={(value) => update("action", value)} />
        <Select label="Target type" value={filters.target_type} values={choices.data?.target_types || []} onChange={(value) => update("target_type", value)} />
        <label className="text-sm font-medium text-slate-700">
          Target ID
          <input
            value={filters.target_id}
            onChange={(event) => update("target_id", event.target.value)}
            placeholder="Exact match, for example LAP-0014"
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#0d9488]"
          />
        </label>
      </div>

      <Card title={`${total} recorded actions`} subtitle="Newest first">
        {query.isLoading ? <Skeleton className="h-96" /> : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[820px] text-left text-sm">
              <thead className="border-b border-[#d9d2c3] bg-[#f4efe4] text-xs uppercase tracking-wider text-slate-500">
                <tr>{["When", "Actor", "Action", "Target", "Detail"].map((label) => <th key={label} className="px-3 py-2 font-bold">{label}</th>)}</tr>
              </thead>
              <tbody>
                {items.map((row) => (
                  <tr key={row.id} className="border-b border-[#eee8db] align-top last:border-0">
                    <td className="whitespace-nowrap px-3 py-2.5 text-xs text-slate-600">{new Date(row.created_at).toLocaleString()}</td>
                    <td className="px-3 py-2.5 text-slate-700">{row.actor_name || "—"}</td>
                    <td className="px-3 py-2.5"><span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-bold text-[#102a43]">{row.action}</span></td>
                    <td className="px-3 py-2.5 text-xs text-slate-600">{row.target_type}<span className="block font-semibold text-[#102a43]">{row.target_id}</span></td>
                    <td className="max-w-[420px] px-3 py-2.5"><Details details={row.details} /></td>
                  </tr>
                ))}
                {!items.length && <tr><td colSpan="5" className="p-5 text-center text-slate-500">No entries match these filters.</td></tr>}
              </tbody>
            </table>
          </div>
        )}
        <div className="mt-4 flex items-center justify-between text-sm text-slate-600">
          <span>{total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0"}</span>
          <div className="flex gap-2">
            <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded border border-slate-300 px-3 py-1.5 font-semibold text-[#102a43] disabled:opacity-40">Previous</button>
            <button disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)} className="rounded border border-slate-300 px-3 py-1.5 font-semibold text-[#102a43] disabled:opacity-40">Next</button>
          </div>
        </div>
      </Card>
    </>
  );
}
