import { useState } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { Dashboard, MapPage, ProjectsPage, AlertsPage } from "./pages/pages";
import NewProjectPage from "./pages/NewProjectPage";

const links=[['/','Dashboard'],['/map','Risk map'],['/projects','Projects'],['/projects/new','New Project'],['/alerts','Alerts']];
const navLink=({isActive})=>`block rounded-lg px-3 py-2.5 text-sm font-medium transition ${isActive?'bg-emerald-600 text-white shadow-sm':'text-slate-300 hover:bg-slate-800 hover:text-white'}`;
function Navigation({onNavigate}) { return <nav className="space-y-1">{links.map(([to,label])=><NavLink onClick={onNavigate} end={to === '/' || to === '/projects' || to === '/projects/new'} key={to} to={to} className={navLink}>{label}</NavLink>)}</nav>; }

export default function App(){
  const [open,setOpen]=useState(false);
  return <div className="min-h-screen bg-[#f7f4ec] lg:grid lg:grid-cols-[17rem_minmax(0,1fr)]">
    <header className="gov-masthead sticky top-0 z-[1100] flex items-center justify-between px-5 py-4 text-white lg:hidden"><div><p className="text-[10px] font-bold uppercase tracking-[.18em] text-amber-200">Land acquisition intelligence</p><h1 className="text-lg font-bold">Bhoomi Setu</h1></div><button aria-label="Toggle navigation" onClick={()=>setOpen(!open)} className="rounded border border-slate-500 px-3 py-2 text-sm">{open?'Close':'Menu'}</button></header>
    {open&&<button aria-label="Close navigation" onClick={()=>setOpen(false)} className="fixed inset-0 z-[1100] bg-slate-950/50 lg:hidden"/>}
    <aside className={`gov-masthead fixed inset-y-0 left-0 z-[1110] w-72 p-5 text-slate-300 transition-transform lg:sticky lg:top-0 lg:block lg:h-screen lg:w-auto lg:translate-x-0 ${open?'translate-x-0':'-translate-x-full'}`}><div className="mb-8 border-b border-slate-600 pb-5"><p className="text-xs font-bold uppercase tracking-[.2em] text-amber-200">Land acquisition intelligence</p><h1 className="mt-2 text-2xl font-bold text-white">Bhoomi Setu</h1><p className="mt-2 text-xs text-slate-300">Risk monitoring & planning support</p></div><Navigation onNavigate={()=>setOpen(false)}/><p className="mt-8 text-xs leading-5 text-slate-300">Decision support for land acquisition risk and schedule exposure.</p></aside>
    <main className="min-w-0 p-4 sm:p-6 lg:p-8 xl:p-10"><div className="mx-auto max-w-[1600px]"><Routes><Route path="/" element={<Dashboard/>}/><Route path="/map" element={<MapPage/>}/><Route path="/projects" element={<ProjectsPage/>}/><Route path="/projects/new" element={<NewProjectPage/>}/><Route path="/alerts" element={<AlertsPage/>}/><Route path="*" element={<Navigate to="/" replace/>}/></Routes></div></main>
  </div>;
}
