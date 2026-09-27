import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useLocation } from "react-router-dom";
import { api } from "../api/client";
import RiskMap, { MapLegend } from "../components/RiskMap";
import ProjectDetail from "../components/ProjectDetail";
import ExplanationPanel from "../components/ExplanationPanel";
import { Card, ErrorNote, PageTitle, Skeleton, Toggle } from "../components/ui";

export default function MapPage() {
  const routed = useLocation().state?.focusProject;
  const [band, setBand] = useState("");
  const [threshold, setThreshold] = useState(0);
  const [project, setProject] = useState(routed || null);
  const [explain, setExplain] = useState(false);

  const query = useQuery({
    queryKey: ["geo", band, threshold],
    queryFn: () => api.geo({ risk_category: band || undefined, min_delay_probability: threshold || undefined }),
  });
  const model = useQuery({ queryKey: ["active-model"], queryFn: api.activeModel });
  const count = query.data?.features?.length || 0;

  return (
    <>
      <PageTitle eyebrow="Geospatial view" heading="Project risk map">
        High-risk projects on the map. Switch to the district layer to see where risk concentrates, or select a marker for the project.
      </PageTitle>
      <ErrorNote query={query} label="Map data unavailable." />

      <div className="mb-4 flex flex-wrap items-end justify-between gap-4">
        <div className="flex flex-wrap items-center gap-4">
          <div>
            <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Risk band</span>
            <Toggle label="Risk band" value={band} options={[["", "All"], ["High", "High"], ["Medium", "Medium"], ["Low", "Low"]]} onChange={setBand} />
          </div>
          <div>
            <span className="mb-1 block text-xs font-bold uppercase tracking-wider text-slate-500">Minimum delay risk</span>
            <Toggle label="Minimum delay risk" value={threshold} options={[[0, "Any"], [0.4, "40%+"], [0.6, "60%+"], [0.8, "80%+"]]} onChange={setThreshold} />
          </div>
        </div>
        <p className="text-sm text-slate-600">{count} projects shown{model.data?.version ? ` · model ${model.data.version}` : ""}</p>
      </div>

      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_400px]">
        <section className="gov-paper min-w-0 rounded-lg p-2">
          {query.isLoading ? <Skeleton className="h-[520px]" /> : (
            <RiskMap
              data={query.data}
              focusProject={project}
              onSelect={(selected) => { setProject(selected); setExplain(false); }}
              onSelectDistrict={() => {}}
            />
          )}
          <div className="px-3 py-3"><MapLegend /></div>
        </section>
        <div className="min-w-0 space-y-4">
          {project ? (
            <ProjectDetail project={project} onExplain={() => setExplain(true)} />
          ) : (
            <Card><p className="text-sm text-slate-500">Select a marker to see the project, its stage risks and its recorded history.</p></Card>
          )}
          <ExplanationPanel
            projectId={project?.project_id}
            open={explain}
            onClose={() => setExplain(false)}
            stages={model.data?.trained_stages || []}
          />
        </div>
      </div>
    </>
  );
}
