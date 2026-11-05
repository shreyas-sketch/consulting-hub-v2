// Header + footer for public pages (/ "What's inside", /plans, legal).
import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { captureAttribution, track } from "@/lib/attribution";
import brand from "@/brand";
import Logo from "./Logo";

export default function PublicLayout({ children, wide = false }) {
  const { user } = useAuth();
  const { pathname, search } = useLocation();
  useEffect(() => { captureAttribution(search); }, [search]);
  useEffect(() => { track("page_view", { path: pathname }); }, [pathname]);
  const w = wide ? "max-w-[1120px]" : "max-w-[980px]";
  return (
    <div className="min-h-screen flex flex-col font-bz text-bz-ink antialiased">
      <header className="sticky top-0 z-30 bg-bz-spine/95 backdrop-blur border-b border-bz-gold/50">
        <div className={`mx-auto ${w} px-4 md:px-8 h-16 flex items-center justify-between gap-3`}>
          <Link to="/" aria-label={`${brand.name} home`}><Logo word="hidden min-[360px]:flex" /></Link>
          {user ? (
            <Link to="/app" data-testid="open-app" className="inline-flex items-center min-h-[44px] px-5 rounded-bzbtn bg-bz-gold text-bz-on-accent font-extrabold text-[14px]">Open the hub</Link>
          ) : (
            <Link to="/login" data-testid="header-login" className="inline-flex items-center min-h-[44px] px-5 rounded-bzbtn border border-bz-rule font-bold text-[14px] hover:border-bz-gold">Log in</Link>
          )}
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="border-t border-bz-rule">
        <div className={`mx-auto ${w} px-4 md:px-8 py-8 space-y-3`}>
          <div className="flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
            <Link to="/plans" className="text-bz-muted hover:text-bz-ink min-h-[32px]">Plans</Link>
            <Link to="/terms" className="text-bz-muted hover:text-bz-ink min-h-[32px]">Terms</Link>
            <Link to="/privacy" className="text-bz-muted hover:text-bz-ink min-h-[32px]">Privacy</Link>
          </div>
          <p className="text-[12.5px] leading-relaxed text-bz-muted max-w-[760px]">
            {brand.name} helps experienced professionals get ready to launch as consultants. Results depend on your own work; nothing here is a promise of income.
          </p>
          <p className="text-[12.5px] font-bold text-bz-rule">AD × SK · © {new Date().getFullYear()}</p>
        </div>
      </footer>
    </div>
  );
}
