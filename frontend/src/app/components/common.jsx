// Shared domain pieces: plan chip, lock / limit card, usage line, back link, score ring.
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useAuth, useFeature } from "@/context/AuthContext";
import { featureInfo, PLAN_LABEL } from "@/lib/features";
import { track } from "@/lib/attribution";
import { Card, Chip, LinkButton } from "./ui";

export function planNeededLabel(p) {
  return PLAN_LABEL[p] || PLAN_LABEL.member;
}

// "1 of 4 this month" / "Your free go: used" from PlanInfo.limits[key] = {used, limit, once}.
export function UsageLine({ usage, what = "uses", className = "" }) {
  if (!usage || usage.used == null) return null;
  let text;
  if (usage.once && (usage.limit || 1) > 1) text = `${usage.used} of ${usage.limit} free ${what} used`;
  else if (usage.once) text = usage.used >= (usage.limit || 1) ? "You've used your free go. Your result stays in My Consulting File." : "Free account: one go.";
  else if (usage.limit == null) text = `${usage.used} ${what} this month`;
  else text = `${usage.used} of ${usage.limit} ${what} used this month`;
  return <p className={`text-[13px] text-bz-muted ${className}`} data-testid="usage-line">{text}</p>;
}

// Shown on a locked page or after a 403/402 from the API.
// At a monthly limit the API sends plan_needed = the next plan that really gives more, or null when there is none
// (L1 and L2 members, or a plan above with the same limit). Then the card only says it resets on the 1st.
export function LockCard({ feature, planNeeded, kind = "locked", msg, once, onAction }) {
  const { user } = useAuth();
  const info = featureInfo(feature);
  const isLimit = kind === "limit";
  const need = isLimit ? planNeeded || null : planNeeded || (info.plan === "free" ? "member" : info.plan);
  const resets = "It resets on the 1st.";
  const limitText = need ? msg || "You've used this month's limit." : msg && /resets on the 1st/i.test(msg) ? msg : `${msg || "You've used this month's limit."} ${resets}`;
  return (
    <Card className="border-bz-rule/80 relative overflow-hidden" data-testid={isLimit ? "limit-card" : "lock-card"}>
      <span aria-hidden className="absolute inset-x-0 top-0 h-[3px] bg-gradient-to-r from-bz-gold via-bz-gold-light to-bz-rule" />
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-bzbtn border border-bz-rule text-bz-gold grid place-items-center shrink-0"><Lock className="w-[18px] h-[18px]" strokeWidth={1.75} aria-hidden /></span>
        <div className="min-w-0">
          <p className="font-display text-[24px] font-[500] leading-tight">{info.name}</p>
          {isLimit ? (
            <p className="text-[15px] mt-1.5">{limitText}</p>
          ) : (
            <>
              <p className="text-[15px] mt-1.5 text-bz-muted">{info.what}</p>
              <p className="text-[15px] mt-2 font-semibold">Part of the <span className="text-bz-gold">{planNeededLabel(need)}</span>.</p>
            </>
          )}
        </div>
      </div>
      {user && need ? (
        <LinkButton to={`/app/plans?plan=${need}&from=${feature || "gate"}`} className="w-full mt-4" data-testid="lock-upgrade"
          onClick={() => { track("upgrade_viewed", { feature, plan: need, kind, once: !!once }); onAction?.(); }}>
          See the {planNeededLabel(need)}
        </LinkButton>
      ) : null}
    </Card>
  );
}

// Wrap a page: show LockCard when PlanInfo.features[feature] is false.
export function Gate({ feature, children, header = null }) {
  const ok = useFeature(feature);
  if (ok) return children;
  return (
    <div className="space-y-4">
      {header}
      <LockCard feature={feature} />
    </div>
  );
}

export function PlanChip({ plan }) {
  if (!plan) return null;
  const tone = plan.plan === "free" ? "muted" : plan.plan === "member" ? "gold" : "solid";
  return <Chip tone={tone}>{plan.label || PLAN_LABEL[plan.plan] || "Free account"}{plan.period === "yearly" ? " · yearly" : ""}</Chip>;
}

export function BackLink({ to, children }) {
  return (
    <Link to={to} className="no-print inline-flex items-center gap-1.5 text-[14px] font-semibold text-bz-gold hover:text-bz-gold-light min-h-[40px] mb-2">
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M15 6l-6 6 6 6" /></svg>
      {children}
    </Link>
  );
}

// Score ring: a cobalt arc (teal for AI scores) on a pale track, the number in the serif. Colours follow the tokens.
export function ScoreRing({ value, max = 100, size = 132, label, sub, ai = false }) {
  const v = Math.max(0, Math.min(max, Number(value) || 0));
  const r = (size - 14) / 2;
  const c = 2 * Math.PI * r;
  const id = `g${size}${max}${ai ? "t" : ""}`;
  return (
    <div className="inline-flex flex-col items-center" role="img" aria-label={`${label || "Score"} ${v} out of ${max}`}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        <defs>
          <linearGradient id={id} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" style={{ stopColor: ai ? "rgb(var(--bz-teal-rgb) / 0.55)" : "rgb(var(--bz-gold-rgb) / 0.55)" }} /><stop offset="1" style={{ stopColor: ai ? "rgb(var(--bz-teal-rgb))" : "rgb(var(--bz-gold-rgb))" }} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" style={{ stroke: "var(--bz-raised)" }} strokeWidth="10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${id})`} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(v / max) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" style={{ fill: ai ? "rgb(var(--bz-teal-rgb))" : "rgb(var(--bz-spine-rgb))" }} fontWeight="500"
          fontFamily="'Newsreader Variable', Georgia, serif" fontSize={size * 0.32}>{v}</text>
      </svg>
      {sub && <span className="text-[12px] text-bz-muted -mt-1">{sub}</span>}
    </div>
  );
}

// Long text with line breaks kept.
export function Para({ text, className = "" }) {
  if (!text) return null;
  return <p className={`whitespace-pre-line leading-relaxed ${className}`}>{text}</p>;
}
