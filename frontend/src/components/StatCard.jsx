const tones = { slate: "bg-slate-900 text-white", High: "bg-red-50 text-red-800", Medium: "bg-amber-50 text-amber-800", Low: "bg-emerald-50 text-emerald-800" };
export default function StatCard({ label, value, tone = "slate", loading }) {
  return <div className={`rounded-xl p-5 shadow-sm ring-1 ring-black/5 ${tones[tone]}`}><p className="text-sm font-medium opacity-75">{label}</p>{loading ? <div className="mt-3 h-9 w-20 animate-pulse rounded bg-current opacity-15" /> : <p className="mt-2 text-3xl font-bold tracking-tight">{value}</p>}</div>;
}
