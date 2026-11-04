// Admin panel (/admin/*), role admin only: left menu groups on a computer, drawer on a phone.
import { useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Logo from "../components/Logo";
import { Button, Card, Spinner } from "../components/ui";
import Pulse from "./Pulse";
import Webinar from "./Webinar";
import Users from "./Users";
import Live from "./Live";
import AdminSupport from "./Support";
import AdminQuestions from "./Questions";
import AdminWeekly from "./Weekly";
import AdminProgram from "./Program";
import AdminCalls from "./Calls";
import AdminLibrary from "./Library";
import AdminRecaps from "./Recaps";
import AdminBootcamps from "./Bootcamps";
import AdminDomains from "./Domains";
import AdminWhatsApp from "./WhatsApp";
import AdminKnowledge from "./Knowledge";
import AdminFeatures from "./Features";
import AdminSettings from "./Settings";
import AdminVendors from "./Vendors";
import AdminJobs from "./Jobs";

export const GROUPS = [
  { name: "Overview", pages: [{ path: "", label: "Pulse", el: Pulse }, { path: "live", label: "Live now", el: Live }, { path: "webinar", label: "Webinar", el: Webinar }] },
  { name: "People", pages: [
    { path: "users", label: "Members", el: Users },
    { path: "support", label: "Support inbox", el: AdminSupport },
    { path: "questions", label: "Akshat AI questions", el: AdminQuestions },
  ] },
  { name: "Program", pages: [
    { path: "program", label: "4-3-2-1 program", el: AdminProgram },
    { path: "calls", label: "Calls and events", el: AdminCalls },
    { path: "recaps", label: "Session recaps", el: AdminRecaps },
    { path: "library", label: "Recordings and workbooks", el: AdminLibrary },
    { path: "bootcamps", label: "Bootcamps", el: AdminBootcamps },
  ] },
  { name: "Content", pages: [
    { path: "settings", label: "Live case & group session", el: AdminSettings },
    { path: "weekly", label: "Weekly case", el: AdminWeekly },
    { path: "kb", label: "Knowledge base", el: AdminKnowledge },
    { path: "domains", label: "Website domains", el: AdminDomains },
  ] },
  { name: "Control", pages: [
    { path: "features", label: "Switches", el: AdminFeatures },
    { path: "vendors", label: "Vendors", el: AdminVendors },
    { path: "whatsapp", label: "WhatsApp templates", el: AdminWhatsApp },
    { path: "jobs", label: "Jobs", el: AdminJobs },
  ] },
];
const ALL = GROUPS.flatMap((g) => g.pages);

function SideNav({ onGo }) {
  return (
    <div className="flex flex-col gap-4 h-full">
      <div className="px-2 flex flex-col gap-2">
        <Link to="/admin" onClick={onGo}><Logo /></Link>
        <span className="text-[11px] font-medium uppercase tracking-kicker text-bz-gold">Admin</span>
      </div>
      <nav aria-label="Admin" className="flex flex-col gap-3 overflow-y-auto">
        {GROUPS.map((g) => (
          <div key={g.name}>
            <div className="px-3 pb-1 text-[11px] font-medium uppercase tracking-[0.16em] text-bz-muted">{g.name}</div>
            {g.pages.map((p) => (
              <NavLink key={p.path} to={`/admin${p.path ? `/${p.path}` : ""}`} end onClick={onGo} data-testid={`admin-nav-${p.path || "pulse"}`}
                className={({ isActive }) => `relative block h-11 leading-[44px] px-3 rounded-bzbtn text-[14px] ${isActive ? "bg-bz-raised text-bz-gold font-extrabold" : "text-bz-muted font-bold hover:bg-bz-raised hover:text-bz-ink"}`}>
                {({ isActive }) => (<>{isActive && <span aria-hidden className="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-bz-gold" />}{p.label}</>)}
              </NavLink>
            ))}
          </div>
        ))}
      </nav>
      <div className="mt-auto px-2 pt-3 border-t border-bz-line flex items-center justify-between gap-2">
        <Link to="/app" className="text-[13px] font-bold text-bz-gold min-h-[40px] inline-flex items-center">Open the hub</Link>
      </div>
    </div>
  );
}

function Shell() {
  const { pathname } = useLocation();
  const [drawer, setDrawer] = useState(false);
  const sub = pathname.replace(/^\/admin\/?/, "").split("/")[0];
  const page = ALL.find((p) => p.path === sub) || ALL[0];
  return (
    <div className="min-h-screen font-bz text-bz-ink antialiased lg:flex">
      <aside className="hidden lg:flex flex-col w-[248px] shrink-0 border-r border-bz-line bg-bz-panel px-4 py-6 h-screen sticky top-0">
        <SideNav />
      </aside>
      <header className="lg:hidden sticky top-0 z-30 bg-bz-panel border-b border-bz-line h-14 px-4 flex items-center justify-between">
        <button aria-label="Menu" onClick={() => setDrawer(true)} className="w-11 h-11 grid place-items-center rounded-full bg-bz-raised" data-testid="admin-menu">
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M4 7h16M4 12h16M4 17h16" /></svg>
        </button>
        <div className="text-[17px] font-extrabold">{page.label}</div>
        <Link to="/admin/users" aria-label="Find a user" className="w-11 h-11 grid place-items-center rounded-full bg-bz-raised">
          <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden><circle cx="11" cy="11" r="7" /><path d="M20 20l-3.5-3.5" /></svg>
        </Link>
      </header>
      {drawer && (
        <div className="lg:hidden fixed inset-0 z-40">
          <button aria-label="Close menu" className="absolute inset-0 bg-bz-scrim" onClick={() => setDrawer(false)} />
          <div className="absolute left-0 top-0 bottom-0 w-[280px] bg-bz-panel border-r border-bz-line px-4 py-5 overflow-y-auto shadow-bzsheet flex flex-col">
            <SideNav onGo={() => setDrawer(false)} />
          </div>
        </div>
      )}
      <main className="flex-1 min-w-0 px-4 lg:px-9 py-5 lg:py-7 max-w-[1240px]">
        <h1 className="hidden lg:block text-[32px] font-extrabold tracking-[-0.02em] leading-[1.05] mb-6">{page.label}</h1>
        <Routes>
          {ALL.map((p) => {
            const El = p.el;
            return p.path ? <Route key={p.path} path={p.path} element={<El />} /> : <Route key="index" index element={<El />} />;
          })}
          <Route path="*" element={<Navigate to="/admin" replace />} />
        </Routes>
      </main>
    </div>
  );
}

export default function AdminApp() {
  const { user, checking, logout } = useAuth();
  const nav = useNavigate();
  const { pathname } = useLocation();
  if (checking || user === null) return <div className="min-h-screen bg-bz-bg grid place-items-center"><Spinner /></div>;
  if (!user) return <Navigate to={`/admin/login?next=${encodeURIComponent(pathname)}`} replace />;
  if (user.role !== "admin") {
    return (
      <div className="min-h-screen font-bz text-bz-ink grid place-items-center p-5">
        <Card className="max-w-[440px] w-full text-center" data-testid="admin-denied">
          <p className="text-[24px] font-extrabold">Team only</p>
          <p className="text-[15px] text-bz-muted mt-2">This account ({user.phone || user.email}) doesn't have admin access. Ask the team to add your number, or log in with a staff account.</p>
          <div className="flex flex-col gap-2 mt-5">
            <Button onClick={async () => { await logout(); nav("/admin/login", { replace: true }); }}>Log in as staff</Button>
            <Link to="/app" className="text-sm font-semibold text-bz-gold py-2">Back to the app</Link>
          </div>
        </Card>
      </div>
    );
  }
  return <Shell />;
}
