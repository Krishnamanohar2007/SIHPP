import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../api/client";
import { useAuth } from "../auth";
import { can } from "../permissions";
import { categorical, percent } from "../theme";
import { Banner, Card, ErrorNote, Figure, PageTitle, Skeleton, StatTile } from "../components/ui";

const metric = (value, digits = 3) => (value === null || value === undefined ? "—" : Number(value).toFixed(digits));

function StageMetrics({ metrics }) {
  const stages = Object.entries(metrics?.stages || {});
  const trained = stages.filter(([, report]) => report.trained);
  if (!trained.length) return null;
  return (
    <Figure
      title="Per-stage model quality"
      subtitle="Held-out ROC AUC per lifecycle stage. 0.5 is chance."
      height={300}
      data={[{
        type: "bar",
        x: trained.map(([stage]) => stage),
        y: trained.map(([, report]) => report.roc_auc),
        marker: { color: categorical[0] },
        text: trained.map(([, report]) => metric(report.roc_auc)),
        textposition: "outside",
        outsidetextfont: { color: "#102a43" },
        hovertemplate: "<b>%{x}</b><br>ROC AUC %{y:.3f}<extra></extra>",
      }]}
      layout={{
        margin: { l: 48, r: 16, t: 24, b: 70 },
        yaxis: { range: [0.4, 1], dtick: 0.1 },
        xaxis: { automargin: true, tickangle: -20 },
        showlegend: false,
        bargap: 0.35,
        shapes: [{ type: "line", xref: "paper", x0: 0, x1: 1, y0: 0.5, y1: 0.5, line: { color: "#b42318", width: 1, dash: "dot" } }],
      }}
      rows={stages.map(([stage, report]) => ({ stage, ...report }))}
      columns={[
        { key: "stage", label: "Stage" },
        { key: "roc_auc", label: "ROC AUC", render: (row) => (row.trained ? metric(row.roc_auc) : "not trained") },
        { key: "accuracy", label: "Accuracy", render: (row) => (row.trained ? metric(row.accuracy) : "—") },
        { key: "brier", label: "Brier", render: (row) => (row.trained ? metric(row.brier) : "—") },
        { key: "positive_rate", label: "Delay rate", render: (row) => (row.trained ? percent(row.positive_rate) : "—") },
        { key: "reason", label: "Note", render: (row) => (row.trained ? "" : row.reason) },
      ]}
      note="The dotted line marks chance. A stage without both outcomes in the training data is not trained, and the whole-project probability is served for it instead."
    />
  );
}

function Importance({ metrics }) {
  const rows = (metrics?.portfolio?.importance || []).slice(0, 12);
  if (!rows.length) return null;
  const label = (name) => name.replace("categorical__", "").replace("numeric__", "").replaceAll("_", " ");
  return (
    <Figure
      title="What the model relies on overall"
      subtitle="Gain-based importance, computed at training time"
      height={340}
      data={[{
        type: "bar",
        orientation: "h",
        x: rows.map((row) => row.share * 100),
        y: rows.map((row) => label(row.feature)),
        marker: { color: categorical[1] },
        hovertemplate: "<b>%{y}</b><br>%{x:.1f}% of total gain<extra></extra>",
      }]}
      layout={{ margin: { l: 210, r: 24, t: 8, b: 40 }, yaxis: { automargin: true, autorange: "reversed" }, xaxis: { ticksuffix: "%", rangemode: "tozero" }, showlegend: false, bargap: 0.3 }}
      rows={rows}
      columns={[
        { key: "feature", label: "Feature", render: (row) => label(row.feature) },
        { key: "share", label: "Share of gain", render: (row) => percent(row.share, 1) },
      ]}
      note="Global importance describes the model as a whole. For one project, open its explanation instead."
    />
  );
}

export default function ModelsPage() {
  const { user } = useAuth();
  const client = useQueryClient();
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const [notes, setNotes] = useState("");
  const [force, setForce] = useState(false);

  const active = useQuery({ queryKey: ["active-model"], queryFn: api.activeModel });
  const versions = useQuery({ queryKey: ["model-versions"], queryFn: api.modelVersions });
  const manage = can(user, "models.manage");

  const invalidate = () => {
    client.invalidateQueries({ queryKey: ["active-model"] });
    client.invalidateQueries({ queryKey: ["model-versions"] });
  };
  const retrain = useMutation({
    mutationFn: () => api.retrain({ force_activate: force, notes: notes || null }),
    onSuccess: (result) => {
      setError("");
      setMessage(
        result.activated
          ? `Trained ${result.version} on ${result.training_rows} rows and activated it. ROC AUC ${metric(result.roc_auc)} against ${metric(result.previous_roc_auc)} before.`
          : `Trained ${result.version} but kept the current model: ROC AUC ${metric(result.roc_auc)} did not beat ${metric(result.previous_roc_auc)}.`
      );
      setNotes("");
      invalidate();
    },
    onError: (failure) => setError(errorMessage(failure, "Retraining failed.")),
  });
  const activate = useMutation({
    mutationFn: (version) => api.activateModel(version),
    onSuccess: (result) => { setError(""); setMessage(`Serving model ${result.version}.`); invalidate(); },
    onError: (failure) => setError(errorMessage(failure, "Activation failed.")),
  });
  const rescore = useMutation({
    mutationFn: () => api.rescore(true),
    onSuccess: (result) => { setError(""); setMessage(`Re-scored ${result.scored} projects; ${result.changed} changed.`); client.invalidateQueries({ queryKey: ["kpis"] }); },
    onError: (failure) => setError(errorMessage(failure, "Re-scoring failed.")),
  });

  const card = active.data;
  const portfolio = card?.metrics?.portfolio;

  return (
    <>
      <PageTitle eyebrow="Model governance" heading="Prediction models">
        The served model, its measured quality, and continuous learning from recorded project outcomes.
      </PageTitle>
      <Banner tone="success" onDismiss={() => setMessage("")}>{message}</Banner>
      <Banner tone="error" onDismiss={() => setError("")}>{error}</Banner>
      <ErrorNote query={active} label="Model card unavailable." />

      {active.isLoading ? <Skeleton className="h-28" /> : card && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            <StatTile label="Serving version" value={card.version} hint={card.trained_at ? new Date(card.trained_at).toLocaleString() : ""} />
            <StatTile label="Portfolio ROC AUC" value={metric(portfolio?.roc_auc)} hint={portfolio?.reference_roc_auc ? `Achievable ceiling ${metric(portfolio.reference_roc_auc)}` : "0.5 is chance"} tone="Low" />
            <StatTile label="Accuracy" value={metric(portfolio?.accuracy)} hint={`Brier ${metric(portfolio?.brier)}`} tone="plain" />
            <StatTile label="Training rows" value={card.training_rows} hint={`${card.trained_stages?.length || 0} of ${card.stages?.length || 0} stage models`} tone="plain" />
          </div>
          <p className="mt-3 text-xs text-slate-500">
            Trained on {card.training_source}. Algorithm {card.algorithm}. The risk score itself is a published rule, not a model output, so it can be recomputed by hand from the project fields.
          </p>
        </>
      )}

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <StageMetrics metrics={card?.metrics} />
        <Importance metrics={card?.metrics} />
      </div>

      {manage && (
        <div className="mt-6 grid gap-6 xl:grid-cols-2">
          <Card title="Retrain from recorded outcomes" subtitle="Merges the seed history with every outcome officials have recorded">
            <label className="block text-sm font-medium text-slate-700">
              Notes
              <input
                value={notes}
                onChange={(event) => setNotes(event.target.value)}
                placeholder="Why this run"
                className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#0d9488]"
              />
            </label>
            <label className="mt-3 flex items-start gap-2 text-sm text-slate-700">
              <input type="checkbox" checked={force} onChange={(event) => setForce(event.target.checked)} className="mt-0.5 h-4 w-4 rounded border-slate-400" />
              <span>Activate even if it scores worse. Leave unchecked to keep the current model unless the new one is at least as good.</span>
            </label>
            <div className="mt-4 flex flex-wrap gap-2">
              <button onClick={() => retrain.mutate()} disabled={retrain.isPending} className="rounded-lg bg-[#0f766e] px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">
                {retrain.isPending ? "Training…" : "Retrain now"}
              </button>
              <button onClick={() => rescore.mutate()} disabled={rescore.isPending} className="rounded-lg border border-slate-300 px-4 py-2.5 text-sm font-semibold text-[#102a43] disabled:opacity-60">
                {rescore.isPending ? "Re-scoring…" : "Re-score portfolio"}
              </button>
            </div>
            <p className="mt-3 text-xs text-slate-500">
              Retraining needs at least 40 labelled rows per target. Re-scoring refreshes the stored risk fields for every project with the serving model and records a snapshot.
            </p>
          </Card>

          <Card title="Version registry" subtitle="Activate any earlier version to roll back">
            <ErrorNote query={versions} label="Registry unavailable." />
            <div className="max-h-[360px] overflow-auto">
              <table className="w-full text-left text-sm">
                <thead className="sticky top-0 bg-[#f4efe4] text-xs uppercase tracking-wider text-slate-500">
                  <tr>{["Version", "Trained", "Rows", "ROC AUC", ""].map((label) => <th key={label} className="px-3 py-2 font-bold">{label}</th>)}</tr>
                </thead>
                <tbody>
                  {(versions.data || []).map((row) => (
                    <tr key={row.id} className="border-b border-[#eee8db] last:border-0">
                      <td className="px-3 py-2.5 font-semibold text-[#102a43]">
                        {row.version}
                        {row.is_active && <span className="ml-2 rounded bg-teal-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-teal-900">Serving</span>}
                        {row.notes && <span className="block text-xs font-normal text-slate-500">{row.notes}</span>}
                      </td>
                      <td className="px-3 py-2.5 text-xs text-slate-600">{new Date(row.trained_at).toLocaleString()}</td>
                      <td className="px-3 py-2.5 tabular-nums text-slate-700">{row.training_rows}</td>
                      <td className="px-3 py-2.5 tabular-nums text-slate-700">{metric(row.metrics?.portfolio?.roc_auc)}</td>
                      <td className="px-3 py-2.5">
                        {!row.is_active && (
                          <button onClick={() => activate.mutate(row.version)} disabled={activate.isPending} className="rounded border border-slate-300 px-2.5 py-1 text-xs font-semibold text-[#102a43] hover:bg-amber-50 disabled:opacity-40">
                            Activate
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                  {!versions.isLoading && !(versions.data || []).length && <tr><td colSpan="5" className="p-5 text-center text-slate-500">No versions registered.</td></tr>}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      )}
    </>
  );
}
