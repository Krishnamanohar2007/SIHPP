import { useEffect } from "react";
import { MapContainer, TileLayer, CircleMarker, useMap } from "react-leaflet";
import "leaflet/dist/leaflet.css";

function FitBounds({ features }) { const map = useMap(); if (features.length) { const points = features.map((f) => [f.geometry.coordinates[1], f.geometry.coordinates[0]]); map.fitBounds(points, { padding: [30, 30], maxZoom: 7 }); } return null; }
function FocusProject({ project }) { const map = useMap(); useEffect(() => { if (project) map.setView([project.latitude, project.longitude], 12); }, [map, project]); return null; }
const colors = { High: "#dc2626", Medium: "#d97706", Low: "#059669" };
export default function RiskMap({ data, onSelect, focusProject }) { const features = data?.features || []; return <MapContainer center={[22.6, 79.5]} zoom={5} className="h-full min-h-[430px] w-full rounded-xl"><TileLayer attribution="© OpenStreetMap contributors" url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" /><FitBounds features={features} /><FocusProject project={focusProject} />{features.map((feature) => { const project = feature.properties; const [lng, lat] = feature.geometry.coordinates; const focused = project.project_id === focusProject?.project_id; return <CircleMarker key={project.project_id} center={[lat, lng]} radius={focused ? 15 : 9} pathOptions={{ color: "#fff", weight: focused ? 5 : 2, fillColor: colors[project.risk_category], fillOpacity: 1, className: focused ? "animate-pulse" : "" }} eventHandlers={{ click: () => onSelect(project) }} />; })}</MapContainer>; }
