import { useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

function FitBounds({ features }) { const map = useMap(); useEffect(() => { if (features.length) { const points = features.map((feature) => [feature.geometry.coordinates[1], feature.geometry.coordinates[0]]); map.fitBounds(points, { padding: [30, 30], maxZoom: 7 }); } }, [map, features]); return null; }
function FocusProject({ project }) { const map = useMap(); useEffect(() => { if (project) map.flyTo([project.latitude, project.longitude], 13, { duration: 0.7 }); }, [map, project?.project_id]); return null; }
const colors = { High: "#dc2626", Medium: "#d97706", Low: "#059669" };
export default function RiskMap({ data, onSelect, focusProject }) { const features = data?.features || []; return <MapContainer center={[22.6, 79.5]} zoom={5} className="h-full min-h-[430px] w-full rounded-xl"><TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><FitBounds features={features} /><FocusProject project={focusProject} />{features.map((feature) => { const project = feature.properties; const [lng, lat] = feature.geometry.coordinates; const focused = project.project_id === focusProject?.project_id; return <CircleMarker key={project.project_id} center={[lat, lng]} radius={focused ? 15 : 9} pathOptions={{ color: "#fff", weight: focused ? 5 : 2, fillColor: colors[project.risk_category], fillOpacity: 1 }} eventHandlers={{ click: () => onSelect(project) }} />; })}</MapContainer>; }
