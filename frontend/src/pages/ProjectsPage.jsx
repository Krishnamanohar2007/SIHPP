import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import ProjectTable from "../components/ProjectTable";
import ProjectDetail from "../components/ProjectDetail";
import ExplanationPanel from "../components/ExplanationPanel";
import { Card, ErrorNote, PageTitle, Select, Skeleton, Toggle } from "../components/ui";

const PAGE = 10;

export default function ProjectsPage() {
  const navigate = useNavigate();
  const focusProjectId = useLocation().state?.focusProjectId;
  const [filters, setFilters] = useState({ country: "India", state: "", district: "", land_type: "", risk_category: "", project_type: "", lifecycle_stage: "" });
  const [threshold, setThreshold] = useState(0);
  const [sort, setSort] = useState({ key: "risk_score", order: "desc" });
  const [offset, setOffset] = useState(0);
  const [selected, setSelected] = useState(null);
  const [explain, setExplain] = useState(false);

  const options = useQuery({
    queryKey: ["filter-options", filters.country, filters.state],
    queryFn: () => api.filterOptions({ country: filters.country || undefined, state: filters.state || undefined }),
  });
  const query = useQuery({
    queryKey: ["projects", filters, threshold, sort, offset],
    queryFn: () => api.projects({
      ...Object.fromEntries(Object.entries(filters).filter(([, value]) => value)),
      min_delay_probability: threshold || undefined,
      sort: sort.key,
      order: sort.order,
      offset,
      limit: PAGE,
    }),
  });
  const model = useQuery({ queryKey: ["active-model"], queryFn: api.activeModel });

  // Opening a project from the dashboard queue: fetch that one record directly,
  // because it may not be on the current page of results.
  const focused = useQuery({ queryKey: ["project", focusProjectId], queryFn: () => api.project(focusProjectId), enabled: Boolean(focusProjectId) });
  useEffect(() => { if (focused.data) setSelected(focused.data); }, [focused.data]);

  const update = (key, value) => {
    const next = { ...filters, [key]: value };
    if (key === "country") Object.assign(next, { state: "", district: "" });
    if (key === "state") next.district = "";
    setFilters(next);
    setOffset(0);
  };
  const values = options.data || {};
  const total = query.data?.total || 0;
  const items = query.data?.items || [];

  return (
    <>
      <PageTitle eyebrow="Portfolio register" heading="Acquisition projects">
        Filter the register, sort by modelled risk, and open a project for its stage risks, attribution and recorded history.
      </PageTitle>
      <ErrorNote query={query} label="Projects unavailable." />
      <ErrorNote query={options} label="Filter values unavailable." />

      <div className="mb-4 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Select label="State" value={filters.state} values={values.states || []} onChange={(value) => update("state", value)} />
        <Select label="District" value={filters.district} values={values.districts || []} disabled={!filters.state} onChange={(value) => update("district", value)} />
        <Select label="Project type" value={filters.project_type} values={values.project_types || []} onChange={(value) => update("project_type", value)} />
        <Select label="Lifecycle stage" value={filters.lifecycle_stage} values={values.lifecycle_stages || []} onChange={(value) => update("lifecycle_stage", value)} />
        <Select label="Land type" value={filters.land_type} values={values.land_types || []} onChange={(value) => update("land_type", value)} />
        <Select label="Risk category" value={filters.risk_category} values={values.risk_categories || []} onChange={(value) => update("risk_category", value)} />
        <div>
          <span className="mb-1 block text-sm font-medium text-slate-700">Minimum delay risk</span>
          <Toggle label="Minimum delay risk" value={threshold} options={[[0, "Any"], [0.4, "40%+"], [0.6, "60%+"], [0.8, "80%+"]]} onChange={(value) => { setThreshold(value); setOffset(0); }} />
        </div>
        <div>
          <span className="mb-1 block text-sm font-medium text-slate-700">Sort</span>
          <select
            aria-label="Sort"
            value={`${sort.key}:${sort.order}`}
            onChange={(event) => { const [key, order] = event.target.value.split(":"); setSort({ key, order }); setOffset(0); }}
            className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-[#102a43] outline-none focus:border-[#0d9488]"
          >
            <option value="risk_score:desc">Highest risk score</option>
            <option value="delay_probability:desc">Highest delay risk</option>
            <option value="risk_score:asc">Lowest risk score</option>
            <option value="project_name:asc">Project name A–Z</option>
            <option value="project_id:asc">Project ID</option>
            <option value="state:asc">State</option>
          </select>
        </div>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <div className="min-w-0">
          {query.isLoading ? <Skeleton className="h-96" /> : items.length ? (
            <ProjectTable projects={items} onSelect={(project) => { setSelected(project); setExplain(false); }} />
          ) : (
            <Card><p className="text-sm text-slate-500">No projects match these filters.</p></Card>
          )}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm text-slate-600">
            <span>
              {total ? `${offset + 1}–${Math.min(offset + PAGE, total)} of ${total}` : "0"} projects
              {model.data?.version ? ` · scored by ${model.data.version}` : ""}
            </span>
            <div className="flex gap-2">
              <button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - PAGE))} className="rounded border border-slate-300 px-3 py-1.5 font-semibold text-[#102a43] disabled:opacity-40">Previous</button>
              <button disabled={offset + PAGE >= total} onClick={() => setOffset(offset + PAGE)} className="rounded border border-slate-300 px-3 py-1.5 font-semibold text-[#102a43] disabled:opacity-40">Next</button>
            </div>
          </div>
        </div>
        <div className="min-w-0 space-y-4">
          {selected ? (
            <ProjectDetail
              key={selected.project_id}
              project={selected}
              onExplain={() => setExplain(true)}
              onMap={() => navigate("/map", { state: { focusProject: selected } })}
            />
          ) : (
            <Card><p className="text-sm text-slate-500">Select a project to see its prediction, stage risks, recorded history and outcome entry.</p></Card>
          )}
          <ExplanationPanel
            projectId={selected?.project_id}
            open={explain}
            onClose={() => setExplain(false)}
            stages={model.data?.trained_stages || []}
          />
        </div>
      </div>
    </>
  );
}
