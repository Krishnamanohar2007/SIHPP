import RiskBadge from "./RiskBadge";
import { delayBand, percent, risk } from "../theme";

/**
 * Project register table. Ordering is server-side, so the rows are rendered in the
 * order they arrive rather than re-sorted here - re-sorting one page of results
 * would silently disagree with the pager.
 */
export default function ProjectTable({ projects, onSelect }) {
  const head = ["Project", "Location", "Stage", "Risk", "Delay likelihood"];
  return (
    <>
      <div className="space-y-3 md:hidden">
        {projects.map((project) => (
          <button key={project.project_id} onClick={() => onSelect(project)} className="gov-paper w-full rounded-lg p-4 text-left">
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0">
                <p className="text-xs font-bold uppercase tracking-wider text-[#0f766e]">{project.project_id}</p>
                <p className="mt-1 truncate font-semibold text-[#102a43]">{project.project_name}</p>
              </div>
              <RiskBadge category={project.risk_category} />
            </div>
            <div className="mt-3 grid grid-cols-2 gap-x-3 gap-y-1 text-sm">
              <p className="text-slate-600">{project.district}, {project.state}</p>
              <p className="text-right font-semibold tabular-nums text-[#102a43]">{percent(project.delay_probability)}</p>
              <p className="text-slate-500">{project.lifecycle_stage}</p>
              <p className="text-right text-xs text-slate-500">{delayBand(project.delay_probability)}</p>
            </div>
          </button>
        ))}
      </div>

      <div className="gov-paper hidden overflow-x-auto rounded-lg md:block">
        <table className="w-full min-w-[780px]">
          <thead className="border-b border-[#d9d2c3] bg-[#f4efe4]">
            <tr>{head.map((label) => <th key={label} className="px-4 py-3 text-left text-xs font-bold uppercase tracking-wider text-slate-500">{label}</th>)}</tr>
          </thead>
          <tbody>
            {projects.map((project) => (
              <tr key={project.project_id} onClick={() => onSelect(project)} className="cursor-pointer border-b border-[#eee8db] last:border-0 hover:bg-amber-50">
                <td className="px-4 py-3.5">
                  <span className="font-semibold text-[#102a43]">{project.project_name}</span>
                  <span className="block text-xs text-slate-500">{project.project_id} · {project.project_type}</span>
                </td>
                <td className="px-4 py-3.5 text-sm text-slate-600">{project.district}<span className="block text-xs text-slate-500">{project.state}</span></td>
                <td className="px-4 py-3.5 text-sm text-slate-600">{project.lifecycle_stage}</td>
                <td className="px-4 py-3.5">
                  <RiskBadge category={project.risk_category} />
                  <span className="mt-1 block text-xs tabular-nums text-slate-500">Score {project.risk_score}</span>
                </td>
                <td className="px-4 py-3.5">
                  <span className="font-semibold tabular-nums" style={{ color: risk[project.risk_category] }}>{percent(project.delay_probability)}</span>
                  <span className="block text-xs text-slate-500">{delayBand(project.delay_probability)}</span>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}
