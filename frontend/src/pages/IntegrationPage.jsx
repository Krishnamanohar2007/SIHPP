import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../api/client";
import { Banner, Card, ErrorNote, PageTitle, Select, Skeleton } from "../components/ui";

export default function IntegrationPage() {
  const client = useQueryClient();
  const [form, setForm] = useState({ name: "", scopes: [], state: "", district: "" });
  const [issued, setIssued] = useState(null);
  const [copied, setCopied] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const scopes = useQuery({ queryKey: ["integration-scopes"], queryFn: api.integrationScopes });
  const keys = useQuery({ queryKey: ["api-keys"], queryFn: api.apiKeys });
  const options = useQuery({ queryKey: ["filter-options", form.state], queryFn: () => api.filterOptions({ country: "India", state: form.state || undefined }) });

  const create = useMutation({
    mutationFn: () => api.createApiKey({
      name: form.name,
      scopes: form.scopes,
      state: form.state || null,
      district: form.district || null,
    }),
    onSuccess: (created) => {
      setError("");
      setIssued(created);
      setCopied(false);
      setForm({ name: "", scopes: [], state: "", district: "" });
      client.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (failure) => setError(errorMessage(failure, "Could not issue the key.")),
  });
  const revoke = useMutation({
    mutationFn: (id) => api.revokeApiKey(id),
    onSuccess: (revoked) => { setError(""); setMessage(`Key ${revoked.key_prefix} revoked. It stops working immediately.`); client.invalidateQueries({ queryKey: ["api-keys"] }); },
    onError: (failure) => setError(errorMessage(failure, "Could not revoke the key.")),
  });

  const toggleScope = (scope) => setForm((previous) => ({
    ...previous,
    scopes: previous.scopes.includes(scope) ? previous.scopes.filter((item) => item !== scope) : [...previous.scopes, scope],
  }));

  return (
    <>
      <PageTitle eyebrow="Interoperability" heading="Integration keys">
        Keys let external land-record systems push records in and read scored records back. Each key carries explicit scopes and optional geographic limits.
      </PageTitle>
      <Banner tone="success" onDismiss={() => setMessage("")}>{message}</Banner>
      <Banner tone="error" onDismiss={() => setError("")}>{error}</Banner>

      {issued && (
        <div className="mb-5 rounded border border-amber-300 bg-amber-50 p-4">
          <p className="text-sm font-bold text-amber-900">Copy this key now. It is shown once and cannot be retrieved again.</p>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <code className="min-w-0 flex-1 break-all rounded bg-white px-3 py-2 font-mono text-xs text-[#102a43] ring-1 ring-amber-200">{issued.api_key}</code>
            <button
              onClick={() => { navigator.clipboard?.writeText(issued.api_key); setCopied(true); }}
              className="rounded bg-[#102a43] px-3 py-2 text-xs font-bold text-white"
            >
              {copied ? "Copied" : "Copy"}
            </button>
            <button onClick={() => setIssued(null)} className="rounded border border-amber-300 px-3 py-2 text-xs font-semibold text-amber-900">Done</button>
          </div>
          <p className="mt-2 text-xs text-amber-900">
            Key {issued.key_prefix} for {issued.name}. Send it as the <code className="font-mono">X-API-Key</code> header. To rotate, issue a new key, move the system over, then revoke this one.
          </p>
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-[400px_minmax(0,1fr)]">
        <Card title="Issue a key" subtitle="One key per integrating system">
          <form onSubmit={(event) => { event.preventDefault(); create.mutate(); }} className="space-y-4">
            <label className="block text-sm font-medium text-slate-700">
              System name
              <input
                required
                minLength={3}
                value={form.name}
                onChange={(event) => setForm({ ...form, name: event.target.value })}
                placeholder="Odisha Land Records Bridge"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#0d9488]"
              />
            </label>

            <fieldset>
              <legend className="text-sm font-medium text-slate-700">Scopes</legend>
              <div className="mt-2 space-y-2">
                {(scopes.data || []).map((item) => (
                  <label key={item.scope} className="flex items-start gap-2 text-sm text-slate-700">
                    <input
                      type="checkbox"
                      checked={form.scopes.includes(item.scope)}
                      onChange={() => toggleScope(item.scope)}
                      className="mt-0.5 h-4 w-4 rounded border-slate-400"
                    />
                    <span><code className="font-mono text-xs text-[#102a43]">{item.scope}</code><span className="block text-xs text-slate-500">{item.description}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>

            <Select label="State limit" placeholder="No state limit" value={form.state} values={options.data?.states || []} onChange={(value) => setForm({ ...form, state: value, district: "" })} />
            <Select label="District limit" placeholder="No district limit" value={form.district} values={options.data?.districts || []} disabled={!form.state} onChange={(value) => setForm({ ...form, district: value })} />
            <p className="text-xs text-slate-500">
              A limited key cannot read or write outside its area even if the feed is misconfigured. Records outside the limit are rejected individually, so the rest of a batch still applies.
            </p>

            <button disabled={create.isPending || !form.name || !form.scopes.length} className="w-full rounded-lg bg-[#0f766e] px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">
              {create.isPending ? "Issuing…" : "Issue key"}
            </button>
          </form>
        </Card>

        <Card title="Issued keys" subtitle="Secrets are stored only as hashes and never shown again">
          <ErrorNote query={keys} label="Keys unavailable." />
          {keys.isLoading ? <Skeleton className="h-64" /> : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[720px] text-left text-sm">
                <thead className="border-b border-[#d9d2c3] bg-[#f4efe4] text-xs uppercase tracking-wider text-slate-500">
                  <tr>{["System", "Prefix", "Scopes", "Limit", "Last used", ""].map((label) => <th key={label} className="px-3 py-2 font-bold">{label}</th>)}</tr>
                </thead>
                <tbody>
                  {(keys.data || []).map((row) => (
                    <tr key={row.id} className="border-b border-[#eee8db] align-top last:border-0">
                      <td className="px-3 py-2.5">
                        <span className="font-semibold text-[#102a43]">{row.name}</span>
                        <span className={`ml-2 rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${row.status === "ACTIVE" ? "bg-teal-100 text-teal-900" : "bg-slate-200 text-slate-600"}`}>{row.status}</span>
                      </td>
                      <td className="px-3 py-2.5 font-mono text-xs text-slate-600">{row.key_prefix}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-600">{(row.scopes || []).join(", ")}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-600">{row.district || row.state || "None"}</td>
                      <td className="px-3 py-2.5 text-xs text-slate-600">{row.last_used_at ? new Date(row.last_used_at).toLocaleString() : "Never"}</td>
                      <td className="px-3 py-2.5">
                        {row.status === "ACTIVE" && (
                          <button onClick={() => revoke.mutate(row.id)} disabled={revoke.isPending} className="rounded border border-red-300 px-2.5 py-1 text-xs font-semibold text-red-700 hover:bg-red-50 disabled:opacity-40">
                            Revoke
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!(keys.data || []).length && <tr><td colSpan="6" className="p-5 text-center text-slate-500">No keys issued yet.</td></tr>}
                </tbody>
              </table>
            </div>
          )}
          <p className="mt-3 text-xs text-slate-500">
            Machine endpoints live under <code className="font-mono">/integration/v1</code>. A key never gains access it was not granted: scopes and limits are enforced server-side on every call, and every sync is audited.
          </p>
        </Card>
      </div>
    </>
  );
}
