import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { categorical, percent, risk } from "../theme";
import { Card, ErrorNote, Figure, PageTitle, Select, StatTile, Toggle } from "../components/ui";
import RiskBadge from "../components/RiskBadge";

const DIMENSIONS = {
  project_type: "Project type",
  lifecycle_stage: "Lifecycle stage",
  land_type: "Land type",
  compensation_status: "Compensation status",
  land_possession_status: "Possession status",
  rehabilitation_status: "Rehabilitation status",
};
const BAND_NOTE = "Bar colour follows the risk band: teal below 40%, gold 40–60%, red above 60%.";

/** Colour a bar by its risk band, reusing the reserved status palette. */
const bandColor = (probability) => (probability >= 0.6 ? risk.High : probability >= 0.4 ? risk.Medium : risk.Low);

function Geography({ filters }) {
  const [level, setLevel] = useState("state");
  const query = useQuery({
    queryKey: ["trends", level, filters],
    queryFn: () => api.trends({ level, state: filters.state || undefined, project_type: filters.project_type || undefined }),
  });
  const rows = (query.data || []).slice(0, 15);
  return (
    <Figure
      title="Delay exposure by geography"
      subtitle={level === "state" ? "Average modelled delay risk per state, worst first" : "Worst 15 districts in scope"}
      height={360}
      loading={query.isLoading}
      error={query}
      action={<Toggle label="Geography level" value={level} options={[["state", "State"], ["district", "District"]]} onChange={setLevel} />}
      data={[{
        type: "bar",
        x: rows.map((row) => (level === "district" ? row.district : row.state)),
        y: rows.map((row) => row.average_delay_probability * 100),
        marker: { color: rows.map((row) => bandColor(row.average_delay_probability)) },
        customdata: rows.map((row) => [row.projects, row.high_risk_projects, row.legal_disputes]),
        hovertemplate: "<b>%{x}</b><br>%{y:.1f}% average delay risk<br>%{customdata[0]} projects, %{customdata[1]} high risk<br>%{customdata[2]} disputes<extra></extra>",
      }]}
      layout={{ margin: { l: 52, r: 16, t: 8, b: 110 }, yaxis: { ticksuffix: "%", rangemode: "tozero" }, xaxis: { tickangle: -35, automargin: true }, showlegend: false, bargap: 0.3 }}
      rows={rows}
      columns={[
        { key: "state", label: "State" },
        ...(level === "district" ? [{ key: "district", label: "District" }] : []),
        { key: "projects", label: "Projects" },
        { key: "average_delay_probability", label: "Avg delay risk", render: (row) => percent(row.average_delay_probability, 1) },
        { key: "high_risk_projects", label: "High risk" },
        { key: "legal_disputes", label: "Disputes" },
      ]}
      note={BAND_NOTE}
    />
  );
}

function RiskMix({ kpis }) {
  const counts = [["Low", kpis?.low_risk_projects], ["Medium", kpis?.medium_risk_projects], ["High", kpis?.high_risk_projects]];
  const total = counts.reduce((sum, [, value]) => sum + (value || 0), 0);
  return (
    <Figure
      title="Risk distribution"
      subtitle={`${total} projects in scope`}
      height={360}
      data={[{
        type: "pie",
        hole: 0.6,
        sort: false,
        labels: counts.map(([label]) => label),
        values: counts.map(([, value]) => value || 0),
        marker: { colors: counts.map(([label]) => risk[label]), line: { color: "#fffdf8", width: 2 } },
        textinfo: "label+percent",
        textfont: { color: "#102a43", size: 13 },
        hovertemplate: "%{label}: %{value} projects (%{percent})<extra></extra>",
      }]}
      layout={{ margin: { l: 8, r: 8, t: 8, b: 8 }, showlegend: false }}
      rows={counts.map(([label, value]) => ({ label, value: value || 0 }))}
      columns={[
        { key: "label", label: "Risk", render: (row) => <RiskBadge category={row.label} /> },
        { key: "value", label: "Projects" },
      ]}
      note="Bands come from the published risk rule: 0–30 Low, 31–60 Medium, above 60 High."
    />
  );
}

function Timeline({ filters }) {
  const [days, setDays] = useState(30);
  const query = useQuery({
    queryKey: ["timeline", days, filters],
    queryFn: () => api.timeline({ days, bucket: days > 90 ? "week" : "day", state: filters.state || undefined, district: filters.district || undefined }),
  });
  const points = query.data || [];
  const series = [
    ["Average delay risk", (row) => row.average_delay_probability * 100, risk.High],
    ["Compensation disbursed", (row) => row.average_compensation_percentage, categorical[0]],
    ["Possession complete", (row) => row.average_possession_percentage, categorical[3]],
  ];
  const window = <Toggle label="Window" value={days} options={[[7, "7d"], [30, "30d"], [90, "90d"], [365, "1y"]]} onChange={setDays} />;

  if (!query.isLoading && points.length < 2) {
    return (
      <Card title="Portfolio trend" subtitle="Built from recorded metric snapshots" action={window}>
        <ErrorNote query={query} label="Timeline unavailable." />
        <p className="text-sm text-slate-500">
          {points.length ? "Only one snapshot period recorded so far." : "No snapshots in this window."} The scheduled risk scan adds a point on every run, so the trend fills in over time.
        </p>
      </Card>
    );
  }
  return (
    <Figure
      title="Portfolio trend"
      subtitle="Built from recorded metric snapshots"
      height={340}
      loading={query.isLoading}
      error={query}
      action={window}
      data={series.map(([name, pick, color]) => ({
        type: "scatter",
        mode: "lines+markers",
        name,
        x: points.map((point) => point.period),
        y: points.map(pick),
        line: { color, width: 2 },
        marker: { size: 8, color, line: { color: "#fffdf8", width: 2 } },
        hovertemplate: `${name}: %{y:.1f}%<extra></extra>`,
      }))}
      layout={{ margin: { l: 48, r: 16, t: 8, b: 56 }, yaxis: { ticksuffix: "%", range: [0, 100] }, hovermode: "x unified", legend: { y: -0.3 } }}
      rows={points}
      columns={[
        { key: "period", label: "Period", render: (row) => new Date(row.period).toLocaleDateString() },
        { key: "average_delay_probability", label: "Avg delay risk", render: (row) => percent(row.average_delay_probability, 1) },
        { key: "average_compensation_percentage", label: "Compensation" },
        { key: "high_risk_projects", label: "High risk" },
        { key: "snapshots", label: "Snapshots" },
      ]}
    />
  );
}

function StageExposure({ filters }) {
  const query = useQuery({
    queryKey: ["stage-exposure", filters],
    queryFn: () => api.stageExposure({ state: filters.state || undefined, district: filters.district || undefined }),
  });
  // Keep lifecycle order rather than sorting by value: the sequence is the point.
  const order = ["Notification", "Compensation", "Possession", "Rehabilitation", "Legal resolution"];
  const rows = order.map((stage) => (query.data || []).find((row) => row.stage === stage)).filter(Boolean);
  if (!query.isLoading && !rows.length) {
    return (
      <Card title="Where the portfolio is most exposed">
        <ErrorNote query={query} label="Stage exposure unavailable." />
        <p className="text-sm text-slate-500">No snapshots recorded yet. Run a risk scan from the Alerts page to populate stage exposure.</p>
      </Card>
    );
  }
  return (
    <Figure
      title="Where the portfolio is most exposed"
      subtitle="Average modelled delay risk per lifecycle stage"
      height={320}
      loading={query.isLoading}
      error={query}
      data={[{
        type: "bar",
        x: rows.map((row) => row.stage),
        y: rows.map((row) => row.average_delay_probability * 100),
        marker: { color: "#0d9488" },
        text: rows.map((row) => `${(row.average_delay_probability * 100).toFixed(0)}%`),
        textposition: "outside",
        outsidetextfont: { color: "#102a43" },
        customdata: rows.map((row) => [row.projects, row.high_risk_projects]),
        hovertemplate: "<b>%{x}</b><br>%{y:.1f}% average delay risk<br>%{customdata[1]} of %{customdata[0]} projects above 60%<extra></extra>",
      }]}
      layout={{ margin: { l: 48, r: 16, t: 24, b: 70 }, yaxis: { ticksuffix: "%", range: [0, 105] }, xaxis: { automargin: true, tickangle: -20 }, showlegend: false, bargap: 0.35 }}
      rows={rows}
      columns={[
        { key: "stage", label: "Stage" },
        { key: "average_delay_probability", label: "Avg delay risk", render: (row) => percent(row.average_delay_probability, 1) },
        { key: "high_risk_projects", label: "Above 60%" },
        { key: "projects", label: "Projects" },
      ]}
    />
  );
}

function Drivers({ filters }) {
  const query = useQuery({
    queryKey: ["drivers", filters],
    queryFn: () => api.drivers({ state: filters.state || undefined, district: filters.district || undefined }),
  });
  const rows = query.data || [];
  return (
    <Figure
      title="How widespread each delay driver is"
      subtitle="Projects breaching each operational threshold"
      height={320}
      loading={query.isLoading}
      error={query}
      data={[{
        type: "bar",
        orientation: "h",
        x: rows.map((row) => row.affected_projects),
        y: rows.map((row) => row.driver),
        marker: { color: "#b7791f" },
        customdata: rows.map((row) => [row.criterion, row.share * 100, row.average_delay_probability * 100]),
        hovertemplate: "<b>%{y}</b><br>%{x} projects, %{customdata[1]:.0f}% of scope<br>%{customdata[0]}<br>Average delay risk %{customdata[2]:.0f}%<extra></extra>",
      }]}
      layout={{ margin: { l: 178, r: 24, t: 8, b: 40 }, yaxis: { automargin: true, autorange: "reversed" }, xaxis: { rangemode: "tozero" }, showlegend: false, bargap: 0.3 }}
      rows={rows}
      columns={[
        { key: "driver", label: "Driver" },
        { key: "criterion", label: "Threshold" },
        { key: "affected_projects", label: "Projects" },
        { key: "share", label: "Share", render: (row) => percent(row.share) },
        { key: "average_delay_probability", label: "Avg delay risk", render: (row) => percent(row.average_delay_probability, 1) },
      ]}
      note="A prevalence count, not a model output. It complements the per-project attribution."
    />
  );
}

function Comparative({ filters }) {
  const [dimension, setDimension] = useState("project_type");
  const query = useQuery({
    queryKey: ["comparative", dimension, filters],
    queryFn: () => api.comparative({ dimension, state: filters.state || undefined, district: filters.district || undefined }),
  });
  const rows = query.data || [];
  return (
    <Figure
      title="Comparative analysis"
      subtitle="Average delay risk across a chosen dimension"
      height={340}
      loading={query.isLoading}
      error={query}
      action={(
        <select
          aria-label="Comparison dimension"
          value={dimension}
          onChange={(event) => setDimension(event.target.value)}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-xs font-semibold text-[#102a43]"
        >
          {Object.entries(DIMENSIONS).map(([key, label]) => <option key={key} value={key}>{label}</option>)}
        </select>
      )}
      data={[{
        type: "bar",
        x: rows.map((row) => row.value),
        y: rows.map((row) => row.average_delay_probability * 100),
        marker: { color: rows.map((row) => bandColor(row.average_delay_probability)) },
        customdata: rows.map((row) => [row.projects, row.high_risk_projects, row.affected_families]),
        hovertemplate: "<b>%{x}</b><br>%{y:.1f}% average delay risk<br>%{customdata[0]} projects, %{customdata[1]} high risk<br>%{customdata[2]} affected families<extra></extra>",
      }]}
      layout={{ margin: { l: 48, r: 16, t: 8, b: 120 }, yaxis: { ticksuffix: "%", rangemode: "tozero" }, xaxis: { tickangle: -30, automargin: true }, showlegend: false, bargap: 0.3 }}
      rows={rows}
      columns={[
        { key: "value", label: DIMENSIONS[dimension] },
        { key: "projects", label: "Projects" },
        { key: "average_delay_probability", label: "Avg delay risk", render: (row) => percent(row.average_delay_probability, 1) },
        { key: "high_risk_projects", label: "High risk" },
        { key: "affected_families", label: "Families" },
      ]}
      note={BAND_NOTE}
    />
  );
}

function Priority({ filters }) {
  const navigate = useNavigate();
  const query = useQuery({
    queryKey: ["priority", filters],
    queryFn: () => api.priority({ limit: 10, state: filters.state || undefined, district: filters.district || undefined }),
  });
  const rows = query.data || [];
  return (
    <Card title="Intervention queue" subtitle="Ranked by exposure weighted by delay likelihood">
      <ErrorNote query={query} label="Queue unavailable." />
      <div className="overflow-x-auto">
        <table className="w-full min-w-[760px] text-left text-sm">
          <thead className="border-b border-[#d9d2c3] bg-[#f4efe4] text-xs uppercase tracking-wider text-slate-500">
            <tr>
              {["#", "Project", "Location", "Stage", "Risk", "Delay", "Exposure"].map((label) => (
                <th key={label} className="px-3 py-2 font-bold">{label}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={row.project_id}
                onClick={() => navigate("/projects", { state: { focusProjectId: row.project_id } })}
                className="cursor-pointer border-b border-[#eee8db] last:border-0 hover:bg-amber-50"
              >
                <td className="px-3 py-2.5 font-bold tabular-nums text-slate-500">{row.rank}</td>
                <td className="px-3 py-2.5">
                  <span className="font-semibold text-[#102a43]">{row.project_name}</span>
                  <span className="block text-xs text-slate-500">{row.project_id} · {row.project_type}</span>
                </td>
                <td className="px-3 py-2.5 text-slate-600">{row.district}, {row.state}</td>
                <td className="px-3 py-2.5 text-slate-600">{row.lifecycle_stage}</td>
                <td className="px-3 py-2.5"><RiskBadge category={row.risk_category} /></td>
                <td className="px-3 py-2.5 font-semibold tabular-nums">{percent(row.delay_probability)}</td>
                <td className="px-3 py-2.5 tabular-nums text-slate-700">
                  ₹{row.exposure_crore} cr
                  <span className="block text-xs text-slate-500">{row.affected_families} families</span>
                </td>
              </tr>
            ))}
            {!rows.length && !query.isLoading && <tr><td colSpan="7" className="p-5 text-center text-slate-500">No projects in scope.</td></tr>}
          </tbody>
        </table>
      </div>
      <p className="mt-3 text-xs text-slate-500">Exposure is the land value at stake in crore. Priority combines it with affected families and the delay likelihood. Select a row to open the project.</p>
    </Card>
  );
}

export default function DashboardPage() {
  const [filters, setFilters] = useState({ state: "", district: "", project_type: "" });
  const scoped = { state: filters.state || undefined, district: filters.district || undefined, project_type: filters.project_type || undefined };
  const options = useQuery({ queryKey: ["filter-options", filters.state], queryFn: () => api.filterOptions({ country: "India", state: filters.state || undefined }) });
  const kpis = useQuery({ queryKey: ["kpis", filters], queryFn: () => api.kpis(scoped) });
  const model = useQuery({ queryKey: ["active-model"], queryFn: api.activeModel });
  const data = kpis.data;
  const update = (key, value) => setFilters({ ...filters, [key]: value, ...(key === "state" ? { district: "" } : {}) });

  return (
    <>
      <PageTitle eyebrow="National portfolio" heading="Land acquisition risk dashboard">
        Modelled delay exposure across the projects in your scope
        {model.data?.version ? `, scored by model ${model.data.version}.` : "."}
      </PageTitle>
      <ErrorNote query={kpis} label="Indicators unavailable." />

      <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Select label="State" value={filters.state} values={options.data?.states || []} onChange={(value) => update("state", value)} />
        <Select label="District" value={filters.district} values={options.data?.districts || []} disabled={!filters.state} onChange={(value) => update("district", value)} />
        <Select label="Project type" value={filters.project_type} values={options.data?.project_types || []} onChange={(value) => update("project_type", value)} />
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Projects in scope" value={data?.total_projects} hint={`${data?.total_land_area?.toLocaleString("en-IN") || 0} acres`} />
        <StatTile label="High risk" value={data?.high_risk_projects} hint={`${percent(data?.high_risk_share)} of scope`} tone="High" />
        <StatTile label="Average delay risk" value={data ? percent(data.average_delay_probability, 1) : "—"} hint={`Average score ${data?.average_risk_score ?? "—"} of 100`} tone="Medium" />
        <StatTile label="Open alerts" value={data?.open_alerts} hint="Unresolved risk signals" tone="plain" />
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Compensation disbursed" value={data ? `${data.average_compensation_percentage}%` : "—"} hint="Portfolio average" tone="plain" />
        <StatTile label="Possession complete" value={data ? `${data.average_possession_percentage}%` : "—"} hint="Portfolio average" tone="plain" />
        <StatTile label="Pending disputes" value={data?.total_legal_disputes} hint={`${data?.total_affected_families?.toLocaleString("en-IN") || 0} affected families`} tone="plain" />
        <StatTile
          label="Outcome agreement"
          value={data?.projects_with_outcome ? percent(data.outcome_agreement) : "No outcomes yet"}
          hint={data?.projects_with_outcome ? `${data.projects_with_outcome} recorded outcomes` : "Record outcomes to measure accuracy"}
          tone="plain"
        />
      </div>

      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Geography filters={filters} />
        <RiskMix kpis={data} />
      </div>
      <div className="mt-6"><Timeline filters={filters} /></div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <StageExposure filters={filters} />
        <Drivers filters={filters} />
      </div>
      <div className="mt-6"><Comparative filters={filters} /></div>
      <div className="mt-6"><Priority filters={filters} /></div>
    </>
  );
}
