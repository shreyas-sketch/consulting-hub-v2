// Plan cards from GET /plans/catalog: ₹1,999 plan (monthly or yearly) and L1 (monthly), plus L2 as information.
// No free trial: the webinar is the trial.
import { useEffect, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Check } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCheckout } from "@/lib/checkout";
import { track } from "@/lib/attribution";
import { hdate, inr } from "@/lib/format";
import { PLAN_LABEL, PLAN_RANK } from "@/lib/features";
import { Button, Card, Chip, ErrorCard, Note, OkLine, Segmented, SkeletonCard } from "./ui";

export function usePlansCatalog() {
  return useQuery({ queryKey: ["plans-catalog"], queryFn: async () => (await api.get("/plans/catalog")).data, staleTime: 10 * 60_000 });
}

function Price({ per }) {
  if (!per) return null;
  const yearly = per.period === "yearly";
  return (
    <div className="mt-2">
      <span className="text-[34px] font-extrabold tracking-[-0.03em] text-bz-gold tabular">{inr(per.price_inr)}</span>
      <span className="text-bz-muted text-[14px]"> + GST / {yearly ? "year" : "month"}</span>
      <div className="text-[13px] text-bz-muted tabular">{inr(per.total_inr)} {yearly ? "a year" : "a month"} with 18% GST{yearly ? ` · works out to ${inr(Math.round(per.price_inr / 12))} a month` : ""}</div>
    </div>
  );
}

function PlanCard({ p, current, highlight, onBuy, busy }) {
  const [period, setPeriod] = useState("monthly");
  const per = (p.periods || []).find((x) => x.period === period) || (p.periods || [])[0];
  const isCur = current === p.id;
  const lower = current && PLAN_RANK[p.id] < PLAN_RANK[current];
  const sellable = (p.periods || []).length > 0;
  return (
    <Card className={`flex flex-col ${highlight ? "border-bz-gold shadow-goldglow" : ""}`} data-testid={`plan-${p.id}`}>
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[22px] font-extrabold tracking-[-0.01em] leading-tight">{p.name || PLAN_LABEL[p.id]}</h3>
        {isCur ? <Chip tone="solid">Your plan</Chip> : p.id === "l1" ? <Chip tone="gold">With 4-3-2-1</Chip> : null}
      </div>
      {(p.periods || []).length > 1 && (
        <Segmented className="mt-3" label="Billing" value={period} onChange={setPeriod} testid={`period-${p.id}`}
          options={[{ value: "monthly", label: "Monthly" }, { value: "yearly", label: "Yearly" }]} />
      )}
      <Price per={per} />
      {p.id === "l2" && <p className="mt-2 text-[15px] text-bz-muted">Six months with Akshat. The team switches it on after you join; your L1 pauses during L2 and continues after.</p>}
      <ul className="mt-4 space-y-2.5 text-[14.5px] flex-1">
        {(p.features || []).map((f) => <li key={f} className="flex gap-2.5"><Check className="w-4 h-4 text-bz-gold shrink-0 mt-1" aria-hidden />{f}</li>)}
      </ul>
      {onBuy && sellable && !isCur && !lower && (
        <Button variant={highlight ? "primary" : "secondary"} className="w-full mt-5" loading={busy === `${p.id}:${per.period}`} onClick={() => onBuy(p.id, per.period)} data-testid={`buy-${p.id}`}>
          Start the {p.name || PLAN_LABEL[p.id]}{per.period === "yearly" ? " (yearly)" : ""}
        </Button>
      )}
    </Card>
  );
}

export default function PlansView({ inShell = false }) {
  const { user, plan } = useAuth();
  const nav = useNavigate();
  const [params] = useSearchParams();
  const cat = usePlansCatalog();
  const { buy, busy, error, done } = useCheckout();
  const want = params.get("plan");

  useEffect(() => { track("upgrade_viewed", { from: params.get("from") || (inShell ? "app" : "public"), plan: want }); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const onBuy = (id, period) => {
    if (!user) { nav(`/login?next=${encodeURIComponent(`/app/plans?plan=${id}`)}`); return; }
    buy(id, period);
  };

  if (cat.isLoading) return <div className="grid gap-3 md:grid-cols-2"><SkeletonCard lines={6} /><SkeletonCard lines={6} /></div>;
  if (cat.isError) return <ErrorCard error={cat.error} onRetry={() => cat.refetch()} what="the plans" />;
  const plans = (cat.data?.plans || []).filter((p) => p.id !== "free");
  const current = user ? plan?.plan || "free" : null;
  const l2End = plan?.l2?.ends_at ? ` on ${hdate(plan.l2.ends_at)}` : "";
  return (
    <div className="space-y-4">
      {done && (
        <Card className="border-bz-gold" role="status">
          {done.scheduled ? (
            <OkLine>Done. Your {done.scheduled.label || PLAN_LABEL[done.scheduled.plan]} starts on {hdate(done.scheduled.starts_at)}, when your current plan ends. The first payment is taken that day.</OkLine>
          ) : (
            <OkLine>Payment received. You're on the {done.label || PLAN_LABEL[done.plan] || "new plan"}{done.paid_until ? ` until ${hdate(done.paid_until)}` : ""}.</OkLine>
          )}
          <Link to="/app" className="text-sm font-bold text-bz-gold">Back to home</Link>
        </Card>
      )}
      {current === "l2" && (
        <Card inset>
          <p className="text-[15px]">
            You're on <b>L2 Mentorship</b>. Everything is open.{" "}
            {plan?.paused_for_l2 ? `Your L1 is paused. It restarts by itself when L2 ends${l2End}.` : `When L2 ends${l2End}, you can start L1 again here.`}
          </p>
        </Card>
      )}
      {current !== "l2" && plan?.scheduled && !done && (
        <Card inset><p className="text-[15px]">Your <b>{plan.scheduled.label || PLAN_LABEL[plan.scheduled.plan]}</b> starts on <b className="text-bz-gold">{hdate(plan.scheduled.starts_at)}</b>.</p></Card>
      )}
      <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
        {plans.map((p) => <PlanCard key={p.id} p={p} current={current} highlight={want ? want === p.id : p.id === "l1"} onBuy={current === "l2" ? null : onBuy} busy={busy} />)}
      </div>
      {error && <p className="text-sm text-bz-miss" role="alert">{error}</p>}
      <Note>Plans renew automatically through Razorpay. Cancel any time from Account; your plan runs to the end of the period you paid for. Prices are before 18% GST.</Note>
    </div>
  );
}
