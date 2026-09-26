const tones = { slate: "bg-[#102a43] text-white border-[#102a43]", High: "bg-red-50 text-red-900 border-red-700", Medium: "bg-amber-50 text-amber-900 border-amber-700", Low: "bg-emerald-50 text-emerald-900 border-emerald-700" };
export default function StatCard({ label, value, tone = "slate", loading }) {
  return <div className={`rounded-lg border-l-4 p-5 shadow-sm ${tones[tone]}`}><p className="text-xs font-bold uppercase tracking-wider opacity-75">{label}</p>{loading ? <div className="mt-3 h-9 w-20 animate-pulse rounded bg-current opacity-15" /> : <p className="mt-2 text-4xl font-bold tracking-tight">{value}</p>}</div>;
}
