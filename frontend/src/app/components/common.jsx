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
  if (usage.once) text = usage.used >= (usage.limit || 1) ? "You've used your free go. Your result stays in My Consulting File." : "Free account: one go.";
  else if (usage.limit == null) text = `${usage.used} ${what} this month`;
  else text = `${usage.used} of ${usage.limit} ${what} used this month`;
  return <p className={`text-[13px] text-bz-muted ${className}`} data-testid="usage-line">{text}</p>;
}

// Shown on a locked page or after a 403/402 from the API.
export function LockCard({ feature, planNeeded, kind = "locked", msg, once, onAction }) {
  const { user } = useAuth();
  const info = featureInfo(feature);
  const need = planNeeded || (info.plan === "free" ? "member" : info.plan);
  const isLimit = kind === "limit";
  return (
    <Card className="border-bz-rule" data-testid={isLimit ? "limit-card" : "lock-card"}>
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-bz-gold-tint text-bz-gold grid place-items-center shrink-0"><Lock className="w-5 h-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="text-[20px] font-extrabold leading-tight">{info.name}</p>
          {isLimit ? (
            <p className="text-[15px] mt-1.5">{msg || "You've used this month's limit."}</p>
          ) : (
            <>
              <p className="text-[15px] mt-1.5 text-bz-muted">{info.what}</p>
              <p className="text-[15px] mt-2 font-bold">Part of the <span className="text-bz-gold">{planNeededLabel(need)}</span>.</p>
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
    <Link to={to} className="no-print inline-flex items-center gap-1.5 text-[13px] font-bold text-bz-gold hover:text-bz-gold-light min-h-[40px] mb-2">
      <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M15 6l-6 6 6 6" /></svg>
      {children}
    </Link>
  );
}

// Gauge-style score ring: gold arc on a hairline track, number in the middle.
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
            <stop offset="0" stopColor={ai ? "#7FF0DC" : "#F0D98A"} /><stop offset="1" stopColor={ai ? "#1E9C87" : "#8F7635"} />
          </linearGradient>
        </defs>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#2A2D36" strokeWidth="10" />
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke={`url(#${id})`} strokeWidth="10" strokeLinecap="round"
          strokeDasharray={`${(v / max) * c} ${c}`} transform={`rotate(-90 ${size / 2} ${size / 2})`} style={{ filter: `drop-shadow(0 0 8px ${ai ? "rgba(46,211,183,0.35)" : "rgba(201,168,76,0.35)"})` }} />
        <text x="50%" y="50%" dominantBaseline="central" textAnchor="middle" fill={ai ? "#2ED3B7" : "#C9A84C"} fontWeight="800" fontSize={size * 0.27} letterSpacing="-1">{v}</text>
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
