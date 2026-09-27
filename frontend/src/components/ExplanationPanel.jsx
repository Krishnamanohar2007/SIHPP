import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { categorical, percent } from "../theme";
import { Card, Empty, Skeleton } from "./ui";

const up = "#b42318";
const down = "#0d9488";

/** Feature values may be numeric or categorical, so only format the numbers. */
function formatValue(value) {
  if (value === null || value === undefined || value === "") return "";
  const number = Number(value);
  return `${Number.isFinite(number) ? number.toLocaleString("en-IN") : value} · `;
}

function FactorBars({ factors }) {
  // Bars are scaled against the largest absolute contribution in this
  // explanation, so the widths compare within one project rather than against an
  // arbitrary fixed maximum.
  const largest = Math.max(...factors.map((factor) => Math.abs(factor.shap_value)), 0.0001);
  return (
    <ul className="space-y-2.5">
      {factors.map((factor) => {
        const increases = factor.shap_value > 0;
        return (
          <li key={factor.feature}>
            <div className="flex items-baseline justify-between gap-3 text-xs">
              <span className="min-w-0 truncate font-semibold text-[#102a43]" title={factor.feature_label}>{factor.feature_label}</span>
              <span className="shrink-0 tabular-nums text-slate-500">
                {formatValue(factor.value)}
                {increases ? "+" : ""}{factor.shap_value.toFixed(3)}
              </span>
            </div>
            <div className="mt-1 flex items-center gap-2">
              <div className="h-2.5 min-w-0 flex-1 overflow-hidden rounded-[4px] bg-slate-200/70">
                <div
                  className="h-2.5 rounded-[4px]"
                  style={{ width: `${Math.max((Math.abs(factor.shap_value) / largest) * 100, 3)}%`, background: increases ? up : down }}
                />
              </div>
              <span className="w-[92px] shrink-0 text-[11px] font-semibold" style={{ color: increases ? up : down }}>
                {increases ? "Raises risk" : "Lowers risk"}
              </span>
            </div>
            <p className="mt-0.5 text-[11px] text-slate-500">{factor.driver}</p>
          </li>
        );
      })}
    </ul>
  );
}

function Drivers({ drivers }) {
  if (!drivers?.length) return null;
  return (
    <div>
      <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Share of upward pressure</p>
      <ul className="mt-2 space-y-1.5">
        {drivers.map((driver, index) => (
          <li key={driver.driver} className="flex items-center gap-2 text-xs">
            <span aria-hidden="true" className="h-2.5 w-2.5 shrink-0 rounded-[2px]" style={{ background: categorical[index % categorical.length] }} />
            <span className="min-w-0 flex-1 truncate text-[#102a43]">{driver.driver}</span>
            <span className="shrink-0 font-semibold tabular-nums text-slate-600">{percent(driver.share)}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function Recommendations({ recommendations, compact }) {
  if (!recommendations?.length) return null;
  const tones = { High: "border-red-200 bg-red-50", Medium: "border-amber-200 bg-amber-50", Low: "border-teal-200 bg-teal-50" };
  return (
    <ol className="space-y-2">
      {recommendations.map((item) => (
        <li key={item.action} className={`rounded border p-3 ${tones[item.priority] || "border-slate-200 bg-slate-50"}`}>
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="font-semibold text-[#102a43]">
              {item.action}
              <span className="ml-2 align-middle text-[11px] font-bold uppercase tracking-wider text-slate-500">{item.priority}</span>
            </p>
            {item.expected_reduction > 0 && (
              <span className="shrink-0 rounded bg-white px-2 py-0.5 text-xs font-bold tabular-nums text-[#0d9488] ring-1 ring-teal-200">
                −{percent(item.expected_reduction, 1)} delay risk
              </span>
            )}
          </div>
          {!compact && <p className="mt-1 text-xs text-slate-600">{item.detail}</p>}
          {item.feature && (
            <p className="mt-1 text-[11px] text-slate-500">
              {item.feature_label}: {Number(item.current_value).toLocaleString("en-IN")} → {Number(item.target_value).toLocaleString("en-IN")}
              {" · "}modelled delay {percent(item.projected_delay_probability, 1)}
            </p>
          )}
        </li>
      ))}
    </ol>
  );
}

/**
 * Explainability panel.
 *
 * `preview` renders an unsaved project's explanation from the preview response;
 * otherwise the panel fetches the saved project's explanation and offers the
 * per-stage models.
 */
export default function ExplanationPanel({ projectId, open, onClose, preview, stages = [] }) {
  const [stage, setStage] = useState("");
  const query = useQuery({
    queryKey: ["explanation", projectId, stage],
    queryFn: () => api.explain(projectId, stage || undefined),
    enabled: Boolean(open && projectId && !preview),
  });
  if (!open) return null;

  const data = preview || query.data;
  const action = (
    <div className="flex items-center gap-2">
      {!preview && stages.length > 0 && (
        <select
          aria-label="Explain stage"
          value={stage}
          onChange={(event) => setStage(event.target.value)}
          className="rounded border border-slate-300 bg-white px-2 py-1 text-xs text-[#102a43]"
        >
          <option value="">Whole project</option>
          {stages.map((name) => <option key={name} value={name}>{name}</option>)}
        </select>
      )}
      {onClose && <button onClick={onClose} aria-label="Close explanation" className="px-1 text-lg font-bold text-slate-400 hover:text-slate-700">×</button>}
    </div>
  );

  return (
    <Card title="Why this prediction" subtitle={data?.model_version ? `Model ${data.model_version}${data.stage ? ` · ${data.stage} stage` : ""}` : undefined} action={action}>
      {query.isLoading && <div className="space-y-2">{[1, 2, 3, 4].map((row) => <Skeleton key={row} className="h-8" />)}</div>}
      {query.isError && <p className="text-sm text-red-700">Explanation unavailable. {query.error?.response?.data?.detail || query.error?.message}</p>}
      {data && (
        <div className="space-y-5">
          {data.base_value !== undefined && (
            <p className="text-xs text-slate-600">
              Baseline delay risk for an average project is {percent(data.base_value, 1)}. This project is at{" "}
              <strong className="text-[#102a43]">{percent(data.delay_probability, 1)}</strong>. Each factor below is its measured contribution to that gap.
            </p>
          )}
          {data.top_contributing_factors?.length ? <FactorBars factors={data.top_contributing_factors} /> : <Empty>No attribution returned.</Empty>}
          <Drivers drivers={data.delay_drivers} />
          <div>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-500">Recommended actions, highest modelled effect first</p>
            <div className="mt-2"><Recommendations recommendations={data.recommendations} /></div>
          </div>
        </div>
      )}
    </Card>
  );
}
