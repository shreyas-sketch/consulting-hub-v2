// Member app shell: left sidebar on a computer; on a phone a top bar and a bottom bar
// (Home, Cases, Brief, My File, Menu). The sidebar is a file spine: the page you are on sticks out as a brass
// index tab that runs into the spine's brass edge, like a divider in a consultant's file.
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

const iconBtn = "w-11 h-11 grid place-items-center rounded-bzbtn border border-bz-line text-bz-muted hover:text-bz-ink hover:bg-bz-raised";

function NavItem({ item, onGo, locked, badge }) {
  const { to, key, label, sub, icon: Icon, end } = item;
  return (
    <NavLink to={to} end={end} onClick={onGo} data-testid={`nav-${key}`}
      className={({ isActive }) => `relative flex items-center gap-3 pl-3 py-2.5 min-h-[52px] transition-colors ${isActive
        ? "mr-0 pr-7 rounded-l-bzbtn bg-bz-gold text-bz-on-accent"
        : "mr-4 pr-3 rounded-bzbtn hover:bg-bz-raised/70"}`}>
      {({ isActive }) => (
        <>
          <Icon className={`w-5 h-5 shrink-0 ${isActive ? "text-bz-on-accent" : "text-bz-faint"}`} strokeWidth={1.6} aria-hidden />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5 text-[14px]">
              <span className={isActive ? "font-bold" : "text-bz-ink font-semibold"}>{label}</span>
              {locked && <Lock className={`w-3 h-3 ${isActive ? "text-bz-on-accent/70" : "text-bz-faint"}`} aria-label="Locked on your plan" />}
            </span>
            <span className={`block text-[12px] truncate ${isActive ? "text-bz-on-accent/75" : "text-bz-muted"}`}>{sub}</span>
          </span>
          {badge ? <span className={`min-w-[20px] h-5 px-1.5 rounded-bztag text-[11px] font-bold grid place-items-center ${isActive ? "bg-bz-on-accent text-bz-gold" : "bg-bz-gold text-bz-on-accent"}`}>{badge}</span> : null}
        </>
      )}
    </NavLink>
  );
}

function GroupLabel({ children }) {
  return <div className="px-3 pt-5 pb-1.5 mr-4 text-[12.5px] font-semibold text-bz-gold/90 border-b border-bz-line/70 mb-1">{children}</div>;
}

// A plan's tools: open by default when the member's plan includes them, folded (with a lock) when not.
function PlanGroup({ g, mine, onGo, locked }) {
  const open = PLAN_RANK[mine] >= PLAN_RANK[g.plan];
  const { pathname } = useLocation();
  const here = g.keys.some((k) => FEATURES[k].to && pathname.startsWith(FEATURES[k].to));
  return (
    <details open={open || here} className="group">
      <summary className="list-none cursor-pointer flex items-center justify-between px-3 pt-5 pb-1.5 mr-4 mb-1 select-none border-b border-bz-line/70">
        <span className="text-[12.5px] font-semibold text-bz-gold/90">{g.label}</span>
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
      <Link to="/app" onClick={onGo} className={`px-2 ${onGo ? "mr-16" : "mr-4"}`} aria-label={`${brand.name} home`}><Logo /></Link>
      <div className="mt-4 px-2"><PlanChip plan={plan} /></div>
      <nav aria-label="Main" className="mt-2 flex flex-col gap-0.5 overflow-y-auto no-scrollbar pb-2 flex-1 min-h-0">
        <GroupLabel>Your tools</GroupLabel>
        {NAV_MAIN.map((i) => <NavItem key={i.to} item={i} onGo={onGo} locked={locked(i)} />)}
        {MENU_GROUPS.map((g) => <PlanGroup key={g.plan} g={g} mine={admin ? "l2" : plan?.plan || "free"} onGo={onGo} locked={locked} />)}
        <GroupLabel>You</GroupLabel>
        {NAV_ACCOUNT.map((i) => <NavItem key={i.to} item={i} onGo={onGo} badge={i.key === "inbox" ? unread : 0} />)}
        {admin && <NavItem item={{ to: "/admin", key: "admin", label: "Admin panel", sub: "Team only", icon: Shield }} onGo={onGo} />}
      </nav>
      <div className="pt-3 mr-4 border-t border-bz-line flex items-center gap-3 px-2">
        <Link to="/app/account" onClick={onGo} className="flex items-center gap-3 min-w-0 flex-1 rounded-bzbtn hover:bg-bz-raised/70 -m-1 p-1">
          <span className="font-display w-9 h-9 shrink-0 rounded-full grid place-items-center text-[17px] font-[500] border border-bz-rule text-bz-gold">{initial}</span>
          <span className="min-w-0">
            <span className="block text-sm font-semibold truncate">{user?.name || user?.phone}</span>
            <span className="block text-[12px] text-bz-muted">Your account</span>
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
      <aside className="chrome grid-ground no-print hidden lg:flex flex-col w-[288px] shrink-0 pl-4 pr-0 py-6 sticky top-0 h-screen bg-bz-spine">
        <MenuBody {...menu} />
      </aside>

      <div className="flex-1 min-w-0 flex flex-col">
        <header className="chrome no-print sticky top-0 z-30 lg:hidden border-b border-bz-line bg-bz-spine/95 backdrop-blur">
          <div className="flex items-center justify-between gap-3 px-4 h-16">
            <Link to="/app" aria-label={`${brand.name} home`}><Logo word="hidden min-[380px]:flex" /></Link>
            <Link to="/app/inbox" aria-label={`Inbox${unread ? `, ${unread} unread` : ""}`} className={`${iconBtn} relative`} data-testid="topbar-inbox">
              <Bell className="w-5 h-5" strokeWidth={1.75} aria-hidden />
              {unread > 0 && <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 rounded-bztag bg-bz-gold text-bz-on-accent text-[10px] font-bold grid place-items-center">{unread > 9 ? "9+" : unread}</span>}
            </Link>
          </div>
        </header>

        {drawer && (
          <div className="lg:hidden fixed inset-0 z-50">
            <button type="button" aria-label="Close menu" className="absolute inset-0 bg-bz-scrim" onClick={() => setDrawer(false)} />
            <div className="chrome grid-ground absolute left-0 top-0 bottom-0 w-[320px] max-w-[88vw] bg-bz-spine pl-4 pr-0 pt-5 pb-[max(1rem,env(safe-area-inset-bottom))] shadow-float flex flex-col">
              <button type="button" aria-label="Close menu" onClick={() => setDrawer(false)} className={`${iconBtn} absolute right-4 top-4 bg-bz-spine`}>
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

        <nav aria-label="Quick" className="chrome no-print lg:hidden fixed bottom-0 inset-x-0 z-30 bg-bz-spine/95 backdrop-blur border-t border-bz-line pb-[env(safe-area-inset-bottom)]">
          <ul className="max-w-[600px] mx-auto grid grid-cols-5">
            {BAR.map(({ to, key, label, icon: Icon, end }) => (
              <li key={to}>
                <NavLink to={to} end={end} data-testid={`bar-${key}`}
                  className={({ isActive }) => `relative flex flex-col items-center gap-1 pt-2.5 pb-3 text-[12px] font-semibold ${isActive ? "text-bz-gold" : "text-bz-faint hover:text-bz-ink"}`}>
                  {({ isActive }) => (<>
                    {isActive && <span aria-hidden className="absolute top-0 left-1/2 -translate-x-1/2 w-10 h-[5px] rounded-b-[4px] bg-bz-gold" />}
                    <Icon className="w-5 h-5" strokeWidth={1.6} aria-hidden />{label}
                  </>)}
                </NavLink>
              </li>
            ))}
            <li>
              <button type="button" onClick={() => setDrawer(true)} data-testid="bar-menu"
                className="w-full flex flex-col items-center gap-1 pt-2.5 pb-3 text-[12px] font-semibold text-bz-faint hover:text-bz-ink relative">
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
