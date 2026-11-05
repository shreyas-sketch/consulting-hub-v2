// Member app shell: left sidebar on a computer; on a phone a top bar and a bottom bar
// (Home · Cases · Brief · My File · Menu). Dark only.
import { Suspense, useEffect, useState } from "react";
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Bell, BriefcaseBusiness, CreditCard, FileText, Gauge, Grid2x2, Home, IdCard, Lock, LogOut, Menu, Shield, Target, User, X,
  ClipboardList, LifeBuoy, ChevronRight, Sparkles,
} from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { captureAttribution, track } from "@/lib/attribution";
import { FEATURES, MENU_GROUPS, PLAN_RANK } from "@/lib/features";
import brand from "@/brand";
import ErrorBoundary from "./ErrorBoundary";
import Logo from "./Logo";
import { PlanChip } from "./common";
import { Spinner } from "./ui";

export const NAV_MAIN = [
  { to: "/app", key: "home", label: "Home", sub: "Where you are and what's next", icon: Home, end: true },
  { to: "/app/readiness", key: "readiness", label: "Readiness Score", sub: "Six skills, out of 60", icon: Gauge, feature: "readiness" },
  { to: "/app/start", key: "start", label: "Starting Point", sub: "Your niche and your numbers", icon: Target, feature: "start" },
  { to: "/app/cases", key: "cases", label: "Cases", sub: "Solve it, get a score", icon: ClipboardList, feature: "case" },
  { to: "/app/brief", key: "brief", label: "Meeting Brief", sub: "Prepare for any company", icon: BriefcaseBusiness, feature: "brief" },
  { to: "/app/linkedin", key: "linkedin", label: "LinkedIn Score", sub: "Fix your profile", icon: IdCard, feature: "linkedin" },
  { to: "/app/file", key: "file", label: "My Consulting File", sub: "Everything you've made", icon: FileText, feature: "file" },
];
const NAV_ACCOUNT = [
  { to: "/app/tools", key: "tools", label: "All tools", sub: "What each plan opens", icon: Grid2x2 },
  { to: "/app/plans", key: "plans", label: "Plans", sub: "₹1,999 plan and L1", icon: CreditCard },
  { to: "/app/support", key: "support", label: "Support", sub: "Ask the team", icon: LifeBuoy, feature: "support" },
  { to: "/app/inbox", key: "inbox", label: "Inbox", sub: "Messages from the team", icon: Bell },
  { to: "/app/account", key: "account", label: "Account", sub: "Profile, plan, usage", icon: User },
];
const BAR = [
  { ...NAV_MAIN[0] },
  { ...NAV_MAIN[3] },
  { ...NAV_MAIN[4], label: "Brief" },
  { ...NAV_MAIN[6], label: "My File" },
];

const iconBtn = "w-11 h-11 grid place-items-center rounded-full border border-bz-line text-bz-muted hover:text-bz-ink hover:bg-bz-raised";

function NavItem({ item, onGo, locked, badge }) {
  const { to, key, label, sub, icon: Icon, end } = item;
  return (
    <NavLink to={to} end={end} onClick={onGo} data-testid={`nav-${key}`}
      className={({ isActive }) => `relative flex items-center gap-3 px-3 py-2.5 rounded-[12px] min-h-[52px] ${isActive ? "bg-bz-raised" : "hover:bg-bz-raised"}`}>
      {({ isActive }) => (
        <>
          {isActive && <span aria-hidden className="absolute left-0 top-2.5 bottom-2.5 w-[3px] rounded-r-full bg-bz-gold shadow-goldglow" />}
          <Icon className={`w-5 h-5 shrink-0 ${isActive ? "text-bz-gold" : "text-bz-faint"}`} strokeWidth={1.75} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 text-[14px]">
              <span className={isActive ? "text-bz-gold font-extrabold" : "text-bz-ink font-bold"}>{label}</span>
              {locked && <Lock className="w-3 h-3 text-bz-faint" aria-label="Locked on your plan" />}
            </span>
            <span className="block text-[12px] text-bz-muted truncate">{sub}</span>
          </span>
          {badge ? <span className="min-w-[20px] h-5 px-1.5 rounded-full bg-bz-gold text-bz-on-accent text-[11px] font-extrabold grid place-items-center">{badge}</span> : null}
        </>
      )}
    </NavLink>
  );
}

function GroupLabel({ children }) {
  return <div className="px-3 pt-4 pb-1 text-[11px] font-medium uppercase tracking-kicker text-bz-gold">{children}</div>;
}

// A plan's tools: open by default when the member's plan includes them, folded (with a lock) when not.
function PlanGroup({ g, mine, onGo, locked }) {
  const open = PLAN_RANK[mine] >= PLAN_RANK[g.plan];
  const { pathname } = useLocation();
  const here = g.keys.some((k) => FEATURES[k].to && pathname.startsWith(FEATURES[k].to));
  return (
    <details open={open || here} className="group">
      <summary className="list-none cursor-pointer flex items-center justify-between px-3 pt-4 pb-1 select-none">
        <span className="text-[11px] font-medium uppercase tracking-kicker text-bz-gold">{g.label}</span>
        <span className="flex items-center gap-1 text-bz-faint">
          {!open && <Lock className="w-3 h-3" aria-label="Not on your plan" />}
          <ChevronRight className="w-4 h-4 transition-transform group-open:rotate-90" aria-hidden />
        </span>
      </summary>
      {g.keys.map((k) => (
        <NavItem key={k} onGo={onGo} locked={locked({ feature: k })}
          item={{ to: FEATURES[k].to, key: k, label: FEATURES[k].name, sub: FEATURES[k].what, icon: Sparkles }} />
      ))}
    </details>
  );
}

function MenuBody({ onGo, user, plan, unread, onLogout }) {
  const feat = plan?.features || {};
  const admin = user?.role === "admin";
  const locked = (i) => i.feature && !admin && !feat[i.feature];
  const initial = (user?.name || user?.phone || "?").replace(/^\+91/, "").slice(0, 1).toUpperCase();
  return (
    <div className="flex flex-col h-full min-h-0">
      <Link to="/app" onClick={onGo} className={`px-2 ${onGo ? "mr-12" : ""}`} aria-label={`${brand.name} home`}><Logo /></Link>
      <div className="mt-4 px-2"><PlanChip plan={plan} /></div>
      <nav aria-label="Main" className="mt-2 flex flex-col gap-0.5 overflow-y-auto no-scrollbar -mx-1 px-1 pb-2 flex-1 min-h-0">
        <GroupLabel>Your tools</GroupLabel>
        {NAV_MAIN.map((i) => <NavItem key={i.to} item={i} onGo={onGo} locked={locked(i)} />)}
        {MENU_GROUPS.map((g) => <PlanGroup key={g.plan} g={g} mine={admin ? "l2" : plan?.plan || "free"} onGo={onGo} locked={locked} />)}
        <GroupLabel>You</GroupLabel>
        {NAV_ACCOUNT.map((i) => <NavItem key={i.to} item={i} onGo={onGo} badge={i.key === "inbox" ? unread : 0} />)}
        {admin && <NavItem item={{ to: "/admin", key: "admin", label: "Admin panel", sub: "Team only", icon: Shield }} onGo={onGo} />}
      </nav>
      <div className="pt-3 border-t border-bz-line flex items-center gap-3 px-2">
        <Link to="/app/account" onClick={onGo} className="flex items-center gap-3 min-w-0 flex-1 rounded-[12px] hover:bg-bz-raised -m-1 p-1">
          <span className="w-9 h-9 shrink-0 rounded-full grid place-items-center text-[14px] font-extrabold bg-bz-gold text-bz-on-accent">{initial}</span>
          <span className="min-w-0">
            <span className="block text-sm font-bold truncate">{user?.name || user?.phone}</span>
            <span className="block text-[11px] font-medium uppercase tracking-[0.14em] text-bz-muted">Account</span>
          </span>
        </Link>
        <button type="button" onClick={onLogout} title="Log out" aria-label="Log out" data-testid="logout" className="w-11 h-11 grid place-items-center text-bz-muted hover:text-bz-ink shrink-0">
          <LogOut className="w-4 h-4" strokeWidth={1.75} />
        </button>
      </div>
    </div>
  );
}

// Redirects to /login?next=… when logged out.
export function RequireAuth({ children }) {
  const { user, checking } = useAuth();
  const { pathname, search } = useLocation();
  if (checking || user === null) return <div className="min-h-screen grid place-items-center"><Spinner /></div>;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(pathname + search)}`} replace />;
  return children;
}

export default function AppShell() {
  const { user, plan, logout } = useAuth();
  const { pathname, search } = useLocation();
  const navigate = useNavigate();
  const [drawer, setDrawer] = useState(false);

  useEffect(() => { captureAttribution(search); }, [search]);
  useEffect(() => { track("page_view", { path: pathname }); setDrawer(false); window.scrollTo(0, 0); }, [pathname]);

  const inbox = useQuery({ queryKey: ["inbox"], queryFn: async () => (await api.get("/inbox")).data, enabled: !!user, staleTime: 60_000 });
  const unread = inbox.data?.unread || 0;
  const menu = { user, plan, unread, onLogout: async () => { await logout(); navigate("/login", { replace: true }); } };

  return (
    <div className="min-h-screen flex font-bz text-bz-ink antialiased">
      <aside className="no-print hidden lg:flex flex-col w-[280px] shrink-0 px-4 py-6 sticky top-0 h-screen border-r border-bz-line bg-bz-panel">
        <MenuBody {...menu} />
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="no-print sticky top-0 z-30 lg:hidden border-b border-bz-line" style={{ backgroundColor: "rgba(20,21,26,0.94)" }}>
          <div className="flex items-center justify-between gap-3 px-4 h-16">
            <Link to="/app" aria-label={`${brand.name} home`}><Logo word="hidden min-[380px]:flex" /></Link>
            <Link to="/app/inbox" aria-label={`Inbox${unread ? `, ${unread} unread` : ""}`} className={`${iconBtn} relative`} data-testid="topbar-inbox">
              <Bell className="w-5 h-5" strokeWidth={1.75} aria-hidden />
              {unread > 0 && <span className="absolute -top-0.5 -right-0.5 min-w-[18px] h-[18px] px-1 rounded-full bg-bz-gold text-bz-on-accent text-[10px] font-extrabold grid place-items-center">{unread > 9 ? "9+" : unread}</span>}
            </Link>
          </div>
        </header>

        {drawer && (
          <div className="lg:hidden fixed inset-0 z-50">
            <button type="button" aria-label="Close menu" className="absolute inset-0 bg-bz-scrim" onClick={() => setDrawer(false)} />
            <div className="absolute left-0 top-0 bottom-0 w-[320px] max-w-[88vw] bg-bz-panel border-r border-bz-line px-4 pt-5 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-float flex flex-col">
              <button type="button" aria-label="Close menu" onClick={() => setDrawer(false)} className={`${iconBtn} absolute right-3 top-4`}>
                <X className="w-5 h-5" strokeWidth={1.75} aria-hidden />
              </button>
              <MenuBody {...menu} onGo={() => setDrawer(false)} />
            </div>
          </div>
        )}

        <main className="flex-1 px-5 md:px-10 lg:px-14 pt-6 md:pt-10 pb-28 lg:pb-16">
          <div className="max-w-[960px] mx-auto">
            {/* The menu stays usable when a screen is loading its code or has crashed. */}
            <ErrorBoundary resetKey={pathname}>
              <Suspense fallback={<div className="min-h-[40vh] grid place-items-center"><Spinner /></div>}>
                <Outlet />
              </Suspense>
            </ErrorBoundary>
          </div>
        </main>

        <nav aria-label="Quick" className="no-print lg:hidden fixed bottom-0 inset-x-0 z-30 bg-bz-panel border-t border-bz-line pb-[env(safe-area-inset-bottom)]">
          <ul className="max-w-[600px] mx-auto grid grid-cols-5">
            {BAR.map(({ to, key, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} data-testid={`bar-${key}`}
                  className={({ isActive }) => `flex flex-col items-center gap-1 pt-2.5 pb-3 text-[11.5px] font-medium ${isActive ? "text-bz-gold" : "text-bz-faint hover:text-bz-ink"}`}>
                  <Icon className="w-5 h-5" strokeWidth={1.75} aria-hidden />{label}
                </NavLink>
              </li>
            ))}
            <li>
              <button type="button" onClick={() => setDrawer(true)} data-testid="bar-menu"
                className="w-full flex flex-col items-center gap-1 pt-2.5 pb-3 text-[11.5px] font-medium text-bz-faint hover:text-bz-ink relative">
                <Menu className="w-5 h-5" strokeWidth={1.75} aria-hidden />Menu
                {unread > 0 && <span className="absolute top-1.5 right-[calc(50%-18px)] w-2 h-2 rounded-full bg-bz-gold" aria-hidden />}
              </button>
            </li>
          </ul>
        </nav>
      </div>
    </div>
  );
}
