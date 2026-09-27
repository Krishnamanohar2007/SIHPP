import { useEffect, useMemo } from "react";
import { MapContainer, TileLayer, CircleMarker, Tooltip, LayersControl, LayerGroup, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";
import { percent, risk } from "../theme";

function FitBounds({ features, enabled }) {
  const map = useMap();
  useEffect(() => {
    if (!enabled || !features.length) return;
    const points = features.map((feature) => [feature.geometry.coordinates[1], feature.geometry.coordinates[0]]);
    map.fitBounds(points, { padding: [30, 30], maxZoom: 7 });
  }, [map, features, enabled]);
  return null;
}

function FocusProject({ project }) {
  const map = useMap();
  useEffect(() => {
    if (project) map.flyTo([project.latitude, project.longitude], 12, { duration: 0.7 });
  }, [map, project?.project_id]);
  return null;
}

/**
 * District aggregation layer.
 *
 * At national zoom 750 individual markers say little, so districts are summarised
 * into one bubble each: area scales with project count, colour with the district's
 * average delay risk. The project markers stay available as their own layer.
 */
function DistrictBubbles({ features, onSelectDistrict }) {
  const districts = useMemo(() => {
    const groups = new Map();
    features.forEach((feature) => {
      const project = feature.properties;
      const key = `${project.state}|${project.district}`;
      const entry = groups.get(key) || { state: project.state, district: project.district, count: 0, delay: 0, high: 0, lat: 0, lng: 0 };
      entry.count += 1;
      entry.delay += Number(project.delay_probability);
      entry.high += project.risk_category === "High" ? 1 : 0;
      entry.lat += feature.geometry.coordinates[1];
      entry.lng += feature.geometry.coordinates[0];
      groups.set(key, entry);
    });
    return [...groups.values()].map((entry) => ({
      ...entry,
      averageDelay: entry.delay / entry.count,
      latitude: entry.lat / entry.count,
      longitude: entry.lng / entry.count,
    }));
  }, [features]);

  const largest = Math.max(...districts.map((entry) => entry.count), 1);
  return (
    <LayerGroup>
      {districts.map((entry) => {
        const band = entry.averageDelay >= 0.6 ? "High" : entry.averageDelay >= 0.4 ? "Medium" : "Low";
        return (
          <CircleMarker
            key={`${entry.state}-${entry.district}`}
            center={[entry.latitude, entry.longitude]}
            radius={10 + Math.sqrt(entry.count / largest) * 22}
            pathOptions={{ color: "#fffdf8", weight: 2, fillColor: risk[band], fillOpacity: 0.62 }}
            eventHandlers={{ click: () => onSelectDistrict?.(entry) }}
          >
            <Tooltip direction="top" offset={[0, -6]}>
              <span className="text-xs">
                <strong>{entry.district}, {entry.state}</strong><br />
                {entry.count} projects · {entry.high} high risk<br />
                Average delay risk {percent(entry.averageDelay, 1)}
              </span>
            </Tooltip>
          </CircleMarker>
        );
      })}
    </LayerGroup>
  );
}

export default function RiskMap({ data, onSelect, onSelectDistrict, focusProject, autoFit = true }) {
  const features = data?.features || [];
  return (
    <MapContainer preferCanvas center={[22.6, 79.5]} zoom={5} className="h-full min-h-[520px] w-full rounded-lg">
      <TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
      <FitBounds features={features} enabled={autoFit && !focusProject} />
      <FocusProject project={focusProject} />
      <LayersControl position="topright">
        <LayersControl.BaseLayer checked name={`Projects (${features.length})`}>
          <LayerGroup>
            {features.map((feature) => {
              const project = feature.properties;
              const [longitude, latitude] = feature.geometry.coordinates;
              const focused = project.project_id === focusProject?.project_id;
              return (
                <CircleMarker
                  key={project.project_id}
                  center={[latitude, longitude]}
                  radius={focused ? 14 : 7}
                  pathOptions={{ color: "#fffdf8", weight: focused ? 4 : 2, fillColor: risk[project.risk_category], fillOpacity: 0.95 }}
                  eventHandlers={{ click: () => onSelect?.(project) }}
                >
                  <Tooltip direction="top" offset={[0, -4]}>
                    <span className="text-xs">
                      <strong>{project.project_name}</strong><br />
                      {project.district}, {project.state}<br />
                      {project.risk_category} risk · {percent(project.delay_probability, 1)} delay · {project.lifecycle_stage}
                    </span>
                  </Tooltip>
                </CircleMarker>
              );
            })}
          </LayerGroup>
        </LayersControl.BaseLayer>
        <LayersControl.BaseLayer name="District concentration">
          <DistrictBubbles features={features} onSelectDistrict={onSelectDistrict} />
        </LayersControl.BaseLayer>
      </LayersControl>
    </MapContainer>
  );
}

/** Shared legend. Identity is never carried by colour alone. */
export function MapLegend() {
  return (
    <ul className="flex flex-wrap items-center gap-4 text-xs text-slate-600">
      {["High", "Medium", "Low"].map((band) => (
        <li key={band} className="flex items-center gap-1.5">
          <span aria-hidden="true" className="h-3 w-3 rounded-full ring-2 ring-[#fffdf8]" style={{ background: risk[band] }} />
          {band} risk
        </li>
      ))}
      <li className="text-slate-500">Bubble size on the district layer shows the project count.</li>
    </ul>
  );
}
