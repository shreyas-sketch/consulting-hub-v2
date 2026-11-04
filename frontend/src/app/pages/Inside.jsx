// "/" — What's inside, for logged-out visitors (webinar QR lands here or on /login).
// Shows the six webinar tools, what each plan adds, and one button: open your account.
import { Link } from "react-router-dom";
import { BriefcaseBusiness, ClipboardList, FileText, Gauge, IdCard, Target } from "lucide-react";
import { FEATURES } from "@/lib/features";
import { useAuth } from "@/context/AuthContext";
import PublicLayout from "../components/PublicLayout";
import { ScoreRing } from "../components/common";
import { Card, Chip, LinkButton } from "../components/ui";

const WEBINAR = [
  { key: "readiness", icon: Gauge },
  { key: "start", icon: Target },
  { key: "case", icon: ClipboardList },
  { key: "brief", icon: BriefcaseBusiness },
  { key: "linkedin", icon: IdCard },
  { key: "file", icon: FileText },
];
const TIERS = [
  { plan: "member", name: "₹1,999 plan", price: "₹1,999 + GST a month, or ₹20,000 + GST a year",
    keys: ["case", "brief", "linkedin_improve", "presentation", "visuals", "website", "listen", "doc_reader", "progress"] },
  { plan: "l1", name: "L1", price: "₹5,000 + GST a month, with the 4-3-2-1 action program",
    keys: ["action_tools", "calls", "recordings", "offer_card", "story_bank", "insight_pack", "portfolio", "akshat_ai", "pitch", "research", "recaps"] },
  { plan: "l2", name: "L2 Mentorship", price: "Six months with Akshat, by invitation",
    keys: ["network_finder", "outreach", "radar", "call_prep", "proposal", "client_diagnostic", "social_builder"] },
];

function SkillBars() {
  const rows = [["Problem diagnosis", 8], ["Offer clarity", 5], ["Client acquisition", 3], ["Pricing confidence", 6], ["Delivery & frameworks", 7], ["Visibility & authority", 4]];
  return (
    <div className="space-y-2.5 w-full">
      {rows.map(([n, v]) => (
        <div key={n}>
          <div className="flex justify-between text-[12.5px]"><span className="text-bz-muted">{n}</span><span className="font-extrabold text-bz-gold tabular">{v}</span></div>
          <div className="h-2 rounded-full bg-bz-line mt-1 overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-[#8F7635] to-[#F0D98A]" style={{ width: `${v * 10}%` }} /></div>
        </div>
      ))}
    </div>
  );
}

export default function Inside() {
  const { user } = useAuth();
  const cta = user ? { to: "/app", label: "Open the hub" } : { to: "/login?src=inside", label: "Open your free account" };
  return (
    <PublicLayout wide>
      <section className="px-4 md:px-8 pt-10 sm:pt-16 pb-12 max-w-[1120px] mx-auto grid gap-10 lg:grid-cols-[1.15fr_0.85fr] items-center">
        <div className="rise-in">
          <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">What's inside</p>
          <h1 className="mt-4 text-[36px] sm:text-[52px] leading-[1.03] font-extrabold tracking-[-0.02em]">
            Your years of experience, <span className="text-bz-gold">ready for clients.</span>
          </h1>
          <p className="mt-5 text-[17px] font-light leading-relaxed text-bz-muted max-w-[560px]">
            The tools you use live on Akshat's webinar: score your readiness, find your niche, solve a real case and prepare for a client meeting. Everything you make is saved in your Consulting File.
          </p>
          <div className="mt-8 flex flex-col sm:flex-row gap-3">
            <LinkButton to={cta.to} data-testid="inside-cta">{cta.label}</LinkButton>
            <LinkButton to="/plans" variant="secondary">See the plans</LinkButton>
          </div>
          <p className="mt-4 text-[13px] text-bz-muted">Log in with your mobile number. No card needed for the free account.</p>
        </div>
        <Card className="shadow-float rounded-bzframe p-6" aria-label="Example Readiness Score">
          <div className="flex items-center justify-between">
            <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">Readiness Score</p>
            <Chip>Example</Chip>
          </div>
          <div className="mt-4 flex items-center gap-6">
            <ScoreRing value={33} max={60} size={128} label="Readiness Score" sub="out of 60" />
            <SkillBars />
          </div>
          <p className="mt-5 text-[14px] text-bz-muted">Start with <b className="text-bz-ink">client acquisition</b>: list 20 people in your network who run or manage a business.</p>
        </Card>
      </section>

      <section className="px-4 md:px-8 pb-14 max-w-[1120px] mx-auto">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">On the webinar</p>
        <h2 className="mt-3 text-[28px] sm:text-[34px] font-extrabold tracking-[-0.02em] leading-tight">Six tools you <span className="text-bz-gold">use live.</span></h2>
        <div className="mt-6 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {WEBINAR.map(({ key, icon: Icon }, i) => (
            <Card key={key} className="flex gap-3.5">
              <span className="w-[34px] h-[34px] shrink-0 rounded-full border border-bz-gold text-bz-gold grid place-items-center text-[14px] font-extrabold">{i + 1}</span>
              <div className="min-w-0">
                <p className="font-bold text-[16px] flex items-center gap-2"><Icon className="w-4 h-4 text-bz-gold" strokeWidth={1.9} aria-hidden />{FEATURES[key].name}</p>
                <p className="text-[14px] text-bz-muted mt-1 leading-relaxed">{FEATURES[key].what}</p>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <section className="px-4 md:px-8 pb-16 max-w-[1120px] mx-auto">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">After the webinar</p>
        <h2 className="mt-3 text-[28px] sm:text-[34px] font-extrabold tracking-[-0.02em] leading-tight">Keep going, <span className="text-bz-gold">every week.</span></h2>
        <div className="mt-6 grid gap-3 lg:grid-cols-3">
          {TIERS.map((t) => (
            <Card key={t.plan} className={t.plan === "l1" ? "border-bz-gold" : ""}>
              <p className="text-[20px] font-extrabold">{t.name}</p>
              <p className="text-[14px] text-bz-gold font-bold mt-1">{t.price}</p>
              <ul className="mt-4 space-y-2">
                {t.keys.map((k) => (
                  <li key={k} className="text-[14px] leading-snug">
                    <span className="font-bold">{FEATURES[k].name}</span>
                  </li>
                ))}
              </ul>
            </Card>
          ))}
        </div>
        <div className="mt-8 flex flex-col sm:flex-row gap-3">
          <LinkButton to={cta.to}>{cta.label}</LinkButton>
          <Link to="/plans" className="inline-flex items-center justify-center min-h-[52px] px-2 font-bold text-bz-gold">Compare plans</Link>
        </div>
      </section>
    </PublicLayout>
  );
}
