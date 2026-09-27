import { useState } from "react";
import Plot from "react-plotly.js";
import { chartConfig, layout } from "../theme";

/** Page heading used by every route, so titles stay consistent. */
export function PageTitle({ eyebrow, heading, children }) {
  return (
    <header className="gov-paper mb-7 rounded-lg px-5 py-5 sm:px-7">
      <p className="text-xs font-bold uppercase tracking-[.18em] text-[#0f766e]">{eyebrow}</p>
      <h1 className="mt-1 text-3xl font-bold tracking-tight text-[#102a43] sm:text-4xl">{heading}</h1>
      {children && <p className="mt-2 max-w-3xl text-slate-600">{children}</p>}
    </header>
  );
}

export function Card({ title, subtitle, action, children, className = "" }) {
  return (
    <section className={`gov-paper min-w-0 rounded-lg p-5 ${className}`}>
      {(title || action) && (
        <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0">
            {title && <h2 className="text-lg font-bold text-[#102a43]">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
          </div>
          {action}
        </div>
      )}
      {children}
    </section>
  );
}

export function ErrorNote({ query, label = "Data unavailable." }) {
  if (!query?.isError) return null;
  return (
    <div role="alert" className="mb-4 rounded border border-red-200 bg-red-50 p-3 text-sm text-red-800">
      {label} {query.error?.response?.data?.detail || query.error?.message}
    </div>
  );
}

export function Skeleton({ className = "h-64" }) {
  return <div className={`animate-pulse rounded bg-slate-200/70 ${className}`} />;
}

export function Empty({ children }) {
  return <p className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">{children}</p>;
}

/**
 * Chart with a built-in table view.
 *
 * Every chart ships an equivalent table, so the data is reachable without relying
 * on colour or on reading a plot. `rows` and `columns` describe that table.
 */
export function Figure({ title, subtitle, note, height = 340, data, layout: extra, rows, columns, loading, action, error, children }) {
  const [table, setTable] = useState(false);
  const toggle = rows?.length ? (
    <button
      type="button"
      onClick={() => setTable(!table)}
      aria-pressed={table}
      className="shrink-0 rounded border border-slate-300 px-2.5 py-1 text-xs font-semibold text-[#102a43] hover:bg-amber-50"
    >
      {table ? "View chart" : "View table"}
    </button>
  ) : null;

  return (
    <Card title={title} subtitle={subtitle} action={<div className="flex items-center gap-2">{action}{toggle}</div>}>
      <ErrorNote query={error} label="Data unavailable." />
      {loading ? (
        <Skeleton className={`h-[${height}px]`} />
      ) : table ? (
        <div className="max-h-[360px] overflow-auto">
          <table className="w-full text-left text-sm">
            <thead className="sticky top-0 bg-[#f4efe4] text-xs uppercase tracking-wider text-slate-500">
              <tr>{columns.map((column) => <th key={column.key} className="px-3 py-2 font-bold">{column.label}</th>)}</tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={index} className="border-b border-[#eee8db] last:border-0">
                  {columns.map((column) => <td key={column.key} className="px-3 py-2 text-slate-700">{column.render ? column.render(row) : row[column.key]}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : data ? (
        <div className="min-w-0" style={{ height }}>
          <Plot useResizeHandler data={data} layout={layout(extra)} config={chartConfig} style={{ width: "100%", height: "100%" }} />
        </div>
      ) : (
        children
      )}
      {note && <p className="mt-3 text-xs text-slate-500">{note}</p>}
    </Card>
  );
}

/** Headline number. Used where a single value beats a plot. */
export function StatTile({ label, value, hint, tone = "ink" }) {
  const tones = {
    ink: "border-[#102a43] bg-[#102a43] text-white",
    High: "border-red-200 bg-red-50 text-red-900",
    Medium: "border-amber-200 bg-amber-50 text-amber-900",
    Low: "border-teal-200 bg-teal-50 text-teal-900",
    plain: "border-[#d9d2c3] bg-[#fffdf8] text-[#102a43]",
  };
  return (
    <div className={`rounded-lg border p-4 shadow-sm ${tones[tone] || tones.plain}`}>
      <p className="text-[11px] font-bold uppercase tracking-wider opacity-75">{label}</p>
      <p className="mt-1.5 text-3xl font-bold tracking-tight">{value ?? "—"}</p>
      {hint && <p className="mt-1 text-xs opacity-70">{hint}</p>}
    </div>
  );
}

export function Select({ label, value, values, onChange, disabled, allowAll = true, labels, placeholder }) {
  return (
    <label className="text-sm font-medium text-slate-700">
      {label}
      <select
        aria-label={label}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        className="mt-1 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-[#0d9488] disabled:bg-slate-100"
      >
        {allowAll && <option value="">{placeholder || `All ${label.toLowerCase()}`}</option>}
        {(values || []).map((item) => <option key={item} value={item}>{labels?.[item] || item}</option>)}
      </select>
    </label>
  );
}

/** Segmented control for a small set of mutually exclusive options. */
export function Toggle({ label, value, options, onChange }) {
  return (
    <div role="group" aria-label={label} className="inline-flex overflow-hidden rounded-lg border border-slate-300">
      {options.map(([key, text]) => (
        <button
          key={key}
          type="button"
          aria-pressed={value === key}
          onClick={() => onChange(key)}
          className={`px-3 py-1.5 text-xs font-semibold ${value === key ? "bg-[#102a43] text-white" : "bg-white text-[#102a43] hover:bg-amber-50"}`}
        >
          {text}
        </button>
      ))}
    </div>
  );
}

export function Banner({ tone = "info", children, onDismiss }) {
  if (!children) return null;
  const tones = {
    info: "border-slate-300 bg-white text-slate-700",
    success: "border-teal-300 bg-teal-50 text-teal-900",
    error: "border-red-300 bg-red-50 text-red-900",
  };
  return (
    <div role="status" className={`mb-5 flex items-start justify-between gap-4 rounded border p-3 text-sm ${tones[tone]}`}>
      <span className="min-w-0 break-words">{children}</span>
      {onDismiss && <button onClick={onDismiss} aria-label="Dismiss" className="shrink-0 font-bold opacity-60 hover:opacity-100">×</button>}
    </div>
  );
}
