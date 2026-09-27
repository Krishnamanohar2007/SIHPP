/**
 * Chart design tokens.
 *
 * The categorical slots are assigned in fixed order and never cycled. They were
 * validated against the paper chart surface (#fffdf8) for the lightness band,
 * chroma floor, all-pairs colour-vision separation, normal-vision separation and
 * contrast. Do not substitute a hue without re-validating: the brand ink
 * (#102a43) and the darker teal (#0f766e) both read as grey in a chart and fail
 * the chroma floor, which is why they are reserved for text and chrome only.
 */

export const ink = "#102a43";
export const paper = "#fffdf8";
export const line = "#d9d2c3";
export const muted = "#627d98";

// Fixed categorical order. A fifth series folds into "Other" rather than
// inventing a hue that would collide under colour-vision deficiency.
export const categorical = ["#0d9488", "#b7791f", "#b42318", "#2563eb"];

// Risk status is reserved. It is never reused as a general series colour.
export const risk = { Low: "#0d9488", Medium: "#b7791f", High: "#b42318" };

// Single-hue ramp for magnitude, light to dark.
export const sequential = ["#ccfbf1", "#99f6e4", "#5eead4", "#2dd4bf", "#14b8a6", "#0d9488", "#0f766e"];

export const chartConfig = {
  responsive: true,
  displaylogo: false,
  modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d", "toggleSpikelines"],
};

/** Shared Plotly layout: recessive grid and axes, ink text, paper surface. */
export function layout(overrides = {}) {
  const { xaxis = {}, yaxis = {}, legend = {}, margin = {}, ...rest } = overrides;
  return {
    autosize: true,
    height: null,
    paper_bgcolor: paper,
    plot_bgcolor: paper,
    font: { family: "Inter, ui-sans-serif, system-ui, sans-serif", size: 12, color: ink },
    margin: { l: 52, r: 16, t: 12, b: 48, ...margin },
    hoverlabel: { bgcolor: ink, bordercolor: ink, font: { color: "#fff", size: 12 } },
    hovermode: "closest",
    xaxis: { gridcolor: line, zerolinecolor: line, linecolor: line, tickfont: { color: muted }, ...xaxis },
    yaxis: { gridcolor: line, zerolinecolor: line, linecolor: line, tickfont: { color: muted }, ...yaxis },
    legend: { orientation: "h", y: -0.22, font: { color: muted }, ...legend },
    ...rest,
  };
}

export const percentAxis = { ticksuffix: "%", rangemode: "tozero" };

export const percent = (value, digits = 0) => `${(Number(value || 0) * 100).toFixed(digits)}%`;
export const inr = (value) => `₹${Number(value || 0).toLocaleString("en-IN")}`;
export const riskOf = (score) => (score <= 30 ? "Low" : score <= 60 ? "Medium" : "High");

/** Display band derived from a probability. A planning aid, not a prediction. */
export const delayBand = (probability) => {
  const value = Number(probability || 0);
  if (value < 0.2) return "0–3 months";
  if (value < 0.4) return "3–6 months";
  if (value < 0.6) return "6–12 months";
  if (value < 0.8) return "12–18 months";
  return "18+ months";
};
