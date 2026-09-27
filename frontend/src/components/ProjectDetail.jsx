import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, errorMessage } from "../api/client";
import { can } from "../permissions";
import { useAuth } from "../auth";
import { delayBand, inr, percent, risk } from "../theme";
import RiskBadge from "./RiskBadge";
import { Banner, Card, Figure } from "./ui";

/** Per-stage delay probabilities. One measure across stages, so one hue. */
export function StageRisks({ risks, sources }) {
  const stages = Object.keys(risks || {});
  if (!stages.length) return null;
  const values = stages.map((stage) => Number(risks[stage]) * 100);
  const fallback = stages.filter((stage) => sources?.[stage] && sources[stage] !== "modelled");
  return (
    <Figure
      title="Delay risk by lifecycle stage"
      subtitle="Each stage has its own trained model"
      height={260}
      data={[{
        type: "bar",
        orientation: "h",
        x: values,
        y: stages,
        marker: { color: "#0d9488" },
        text: values.map((value) => `${value.toFixed(0)}%`),
        textposition: "auto",
        insidetextfont: { color: "#fff" },
        outsidetextfont: { color: "#102a43" },
        hovertemplate: "%{y}: %{x:.1f}% delay risk<extra></extra>",
      }]}
      layout={{
        margin: { l: 118, r: 24, t: 8, b: 32 },
        xaxis: { ticksuffix: "%", range: [0, 100] },
        yaxis: { automargin: true, autorange: "reversed" },
        showlegend: false,
        bargap: 0.35,
      }}
      rows={stages.map((stage) => ({ stage, value: risks[stage], source: sources?.[stage] || "modelled" }))}
      columns={[
        { key: "stage", label: "Stage" },
        { key: "value", label: "Delay risk", render: (row) => percent(row.value, 1) },
        { key: "source", label: "Source" },
      ]}
      note={fallback.length ? `No stage model for: ${fallback.join(", ")}. The whole-project probability is shown for those stages.` : undefined}
    />
  );
}

function OutcomeForm({ project, onDone }) {
  const client = useQueryClient();
  const [form, setForm] = useState({ expected_completion_days: "", actual_completion_days: "", notes: "" });
  const mutation = useMutation({
    mutationFn: () => api.recordOutcome(project.project_id, {
      expected_completion_days: Number(form.expected_completion_days),
      actual_completion_days: Number(form.actual_completion_days),
      notes: form.notes || null,
    }),
    onSuccess: (saved) => {
      client.invalidateQueries({ queryKey: ["projects"] });
      client.invalidateQueries({ queryKey: ["kpis"] });
      onDone?.(saved);
    },
  });
  const field = (name, label) => (
    <label className="text-sm font-medium text-slate-700">
      {label}
      <input
        required
        type="number"
        min="1"
        value={form[name]}
        onChange={(event) => setForm({ ...form, [name]: event.target.value })}
        className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#0d9488]"
      />
    </label>
  );
  if (project.delayed !== null && project.delayed !== undefined) {
    return (
      <Card title="Recorded outcome">
        <dl className="grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-slate-500">Sanctioned</dt><dd className="font-semibold">{project.expected_completion_days} days</dd></div>
          <div><dt className="text-slate-500">Actual</dt><dd className="font-semibold">{project.actual_completion_days} days</dd></div>
          <div><dt className="text-slate-500">Outcome</dt><dd className="font-semibold">{project.delayed ? "Delayed" : "On schedule"}</dd></div>
          <div><dt className="text-slate-500">Recorded</dt><dd className="font-semibold">{project.outcome_recorded_at ? new Date(project.outcome_recorded_at).toLocaleDateString() : "—"}</dd></div>
        </dl>
        {project.outcome_notes && <p className="mt-3 text-xs text-slate-600">{project.outcome_notes}</p>}
        <p className="mt-3 text-xs text-slate-500">This outcome is training data. It is used the next time the models are retrained.</p>
      </Card>
    );
  }
  return (
    <Card title="Record realised outcome" subtitle="Used as ground truth when models retrain">
      <form
        onSubmit={(event) => { event.preventDefault(); mutation.mutate(); }}
        className="space-y-3"
      >
        <div className="grid gap-3 sm:grid-cols-2">
          {field("expected_completion_days", "Sanctioned days")}
          {field("actual_completion_days", "Actual days")}
        </div>
        <label className="block text-sm font-medium text-slate-700">
          Notes
          <textarea
            rows="2"
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
            className="mt-1 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm outline-none focus:border-[#0d9488]"
          />
        </label>
        <p className="text-xs text-slate-500">Marked delayed when actual days exceed sanctioned days by more than 10%.</p>
        {mutation.isError && <Banner tone="error">{errorMessage(mutation.error, "Could not record the outcome.")}</Banner>}
        <button disabled={mutation.isPending} className="w-full rounded-lg bg-[#0f766e] px-4 py-2.5 text-sm font-bold text-white disabled:opacity-60">
          {mutation.isPending ? "Saving…" : "Record outcome"}
        </button>
      </form>
    </Card>
  );
}

function History({ projectId }) {
  const query = useQuery({ queryKey: ["project-timeline", projectId], queryFn: () => api.projectTimeline(projectId) });
  const points = query.data || [];
  if (query.isLoading) return <Figure title="Recorded history" loading height={260} />;
  if (points.length < 2) {
    return (
      <Card title="Recorded history">
        <p className="text-sm text-slate-500">
          {points.length ? "One snapshot recorded so far." : "No snapshots recorded yet."} A point is added on every edit and on each scheduled risk scan.
        </p>
      </Card>
    );
  }
  const at = points.map((point) => point.captured_at);
  const series = [
    ["Delay risk", "delay_probability", "#b42318", 100],
    ["Compensation", "compensation_percentage", "#0d9488", 1],
    ["Possession", "land_possession_percentage", "#2563eb", 1],
    ["Rehabilitation", "rehabilitation_percentage", "#b7791f", 1],
  ];
  return (
    <Figure
      title="Recorded history"
      subtitle="Snapshots captured on edits and scheduled scans"
      height={280}
      data={series.map(([name, key, color, scale]) => ({
        type: "scatter",
        mode: "lines+markers",
        name,
        x: at,
        y: points.map((point) => Number(point[key]) * scale),
        line: { color, width: 2 },
        marker: { size: 8, color, line: { color: "#fffdf8", width: 2 } },
        hovertemplate: `${name}: %{y:.1f}%<extra></extra>`,
      }))}
      layout={{ margin: { l: 48, r: 16, t: 8, b: 40 }, yaxis: { ticksuffix: "%", range: [0, 100] }, hovermode: "x unified", legend: { y: -0.25 } }}
      rows={points}
      columns={[
        { key: "captured_at", label: "Captured", render: (row) => new Date(row.captured_at).toLocaleString() },
        { key: "delay_probability", label: "Delay risk", render: (row) => percent(row.delay_probability, 1) },
        { key: "risk_score", label: "Risk score" },
        { key: "lifecycle_stage", label: "Stage" },
        { key: "source", label: "Source" },
      ]}
    />
  );
}

/**
 * Project detail: stored values, a fresh prediction, stage risks, recorded
 * history and the outcome entry form.
 */
export default function ProjectDetail({ project, onExplain, onMap }) {
  const { user } = useAuth();
  const [saved, setSaved] = useState(project);
  const prediction = useMutation({ mutationFn: () => api.predict(project.project_id) });
  const current = prediction.data;
  return (
    <div className="space-y-4">
      <Card>
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            <p className="text-xs font-bold uppercase tracking-wider text-[#0f766e]">{project.project_id}</p>
            <h2 className="truncate text-lg font-bold text-[#102a43]">{project.project_name}</h2>
            <p className="text-sm text-slate-600">{project.district}, {project.state} · {project.project_type}</p>
          </div>
          <RiskBadge category={project.risk_category} />
        </div>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm">
          <div><dt className="text-slate-500">Risk score</dt><dd className="font-semibold tabular-nums" style={{ color: risk[project.risk_category] }}>{project.risk_score} / 100</dd></div>
          <div><dt className="text-slate-500">Delay likelihood</dt><dd className="font-semibold tabular-nums">{percent(project.delay_probability, 1)}</dd><dd className="text-xs text-slate-500">{delayBand(project.delay_probability)}</dd></div>
          <div><dt className="text-slate-500">Lifecycle stage</dt><dd className="font-semibold">{project.lifecycle_stage}</dd></div>
          <div><dt className="text-slate-500">Affected families</dt><dd className="font-semibold tabular-nums">{project.affected_families}</dd></div>
          <div><dt className="text-slate-500">Compensation</dt><dd className="font-semibold tabular-nums">{project.compensation_percentage}%</dd></div>
          <div><dt className="text-slate-500">Possession</dt><dd className="font-semibold tabular-nums">{project.land_possession_percentage}%</dd></div>
          <div><dt className="text-slate-500">Rehabilitation</dt><dd className="font-semibold tabular-nums">{project.rehabilitation_percentage}%</dd></div>
          <div><dt className="text-slate-500">Legal disputes</dt><dd className="font-semibold tabular-nums">{project.legal_disputes}</dd></div>
          <div><dt className="text-slate-500">Approval wait</dt><dd className="font-semibold tabular-nums">{project.approval_timeline_days} days</dd></div>
          <div><dt className="text-slate-500">Price / acre</dt><dd className="font-semibold tabular-nums">{inr(project.land_price_per_acre)}</dd></div>
        </dl>
        <p className="mt-3 text-xs text-slate-500">The planning band is a display guide derived from the likelihood, not a separate prediction.</p>
        <div className="mt-4 grid gap-2 sm:grid-cols-2">
          <button onClick={onExplain} className="rounded-lg bg-[#102a43] px-3 py-2 text-sm font-semibold text-white">Why this prediction</button>
          <button onClick={() => prediction.mutate()} className="rounded-lg border border-slate-300 px-3 py-2 text-sm font-semibold text-[#102a43]">
            {prediction.isPending ? "Re-scoring…" : "Re-score now"}
          </button>
          {onMap && <button onClick={onMap} className="rounded-lg bg-[#0f766e] px-3 py-2 text-sm font-semibold text-white sm:col-span-2">Show on map</button>}
        </div>
        {current && (
          <p className="mt-3 rounded bg-teal-50 p-3 text-sm text-teal-900">
            Model {current.model_version}: {percent(current.delay_probability, 1)} delay risk, score {current.risk_score}, {current.risk_category}.
          </p>
        )}
        {prediction.isError && <p className="mt-3 text-sm text-red-700">{errorMessage(prediction.error, "Prediction unavailable.")}</p>}
      </Card>

      {current?.lifecycle_risks && <StageRisks risks={current.lifecycle_risks} sources={current.lifecycle_risk_sources} />}
      <History projectId={project.project_id} />
      {can(user, "projects.outcome") && <OutcomeForm project={saved} onDone={setSaved} />}
    </div>
  );
}
