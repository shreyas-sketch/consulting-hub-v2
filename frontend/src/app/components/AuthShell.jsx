// Two-pane sign-in: brand rail on a computer (what's inside, in short), form on the right.
import { Link } from "react-router-dom";
import brand from "@/brand";
import Logo from "./Logo";
import { Step } from "./ui";

export default function AuthShell({ kicker, title, accent, subtitle, children, footer }) {
  return (
    <div className="min-h-screen w-full flex items-stretch text-bz-ink font-bz" data-testid="auth-shell">
      <aside className="hidden lg:flex lg:w-[46%] relative overflow-hidden border-r-2 border-bz-gold/80 bg-bz-spine">
        <div className="absolute inset-0 pointer-events-none" style={{ background: "radial-gradient(ellipse 900px 700px at 20% 85%, rgba(212,176,106,0.10), transparent 70%)" }} />
        <div className="relative z-10 flex flex-col justify-between p-14 w-full">
          <Link to="/"><Logo big /></Link>
          <div className="space-y-6 max-w-md">
            <p className="text-[12px] font-semibold text-bz-gold">From the webinar</p>
            <h2 className="font-display text-[48px] leading-[1.02] font-[450] tracking-[-0.018em]">Your years of experience, ready for clients.</h2>
            <div className="space-y-4">
              <Step n={1} title="Score your readiness">Six skills, out of 60.</Step>
              <Step n={2} title="Find your niche">Experience, demand, enjoyment.</Step>
              <Step n={3} title="Solve a live case">Get a score and a model answer.</Step>
            </div>
          </div>
          <p className="text-[12.5px] font-bold text-bz-rule">Akshat Dani and Siddharth Kapoor</p>
        </div>
      </aside>
      <main className="flex-1 flex flex-col">
        <div className="flex items-center justify-between px-5 sm:px-10 pt-5 lg:hidden">
          <Link to="/"><Logo /></Link>
        </div>
        <div className="flex-1 flex items-center justify-center p-5 sm:p-10">
          <div className="w-full max-w-[420px]">
            {kicker && <p className="text-[12px] font-semibold text-bz-gold mb-3">{kicker}</p>}
            <h1 className="font-display text-[36px] leading-[1.05] font-[450] tracking-[-0.016em]">{title}{accent ? <> {accent}</> : null}</h1>
            {subtitle && <p className="mt-3 text-[15.5px] text-bz-muted leading-relaxed">{subtitle}</p>}
            <div className="mt-8">{children}</div>
            {footer && <div className="mt-8 pt-5 border-t border-bz-line text-[12.5px] text-bz-muted leading-relaxed">{footer}</div>}
          </div>
        </div>
      </main>
    </div>
  );
}
