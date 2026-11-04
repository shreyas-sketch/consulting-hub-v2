// /app/account — plan and billing (cancel; L1 cancel shows the ₹1,999 offer once), usage, profile, log out.
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { useCheckout } from "@/lib/checkout";
import { hdate, inr } from "@/lib/format";
import { PLAN_LABEL } from "@/lib/features";
import { Button, Card, Field, Input, Label, LinkButton, Meter, OkLine, PageHeader, Sheet } from "../components/ui";
import { PlanChip } from "../components/common";

const USAGE_NAME = { readiness: "Readiness Scores", start: "Niche Snapshots", goal: "Goal Map saves", case: "Case answers", brief: "Meeting Briefs", linkedin: "LinkedIn checks" };
const SOURCE = { paid: "Paid subscription", grant: "Given by the team", free: "Free account" };

function Profile() {
  const { user, setUser } = useAuth();
  const [f, setF] = useState({ name: user?.name || "", email: user?.email || "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  useEffect(() => { setF({ name: user?.name || "", email: user?.email || "" }); }, [user?.name, user?.email]);
  const save = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    if (f.email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(f.email.trim())) { setErr("That email doesn't look right."); return; }
    setBusy(true);
    try {
      const { data } = await api.patch("/auth/profile", { name: f.name.trim(), email: f.email.trim() || null });
      if (data?.user) setUser(data.user);
      setOk("Saved.");
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <Card>
      <Label>Profile</Label>
      <form onSubmit={save} noValidate className="space-y-3">
        <Field label="Mobile"><Input value={user?.phone || ""} disabled readOnly className="opacity-70" /></Field>
        <Field label="Name" hint="Shown on your Consulting File."><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} autoComplete="name" maxLength={60} data-testid="profile-name" /></Field>
        <Field label="Email (optional)" hint="For receipts."><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} autoComplete="email" data-testid="profile-email" /></Field>
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <OkLine>{ok}</OkLine>
        <Button type="submit" variant="secondary" loading={busy} data-testid="profile-save">Save</Button>
      </form>
    </Card>
  );
}

function Offer({ offer, onClose }) {
  const { buy, busy, error, done } = useCheckout();
  const starts = done?.scheduled?.starts_at || offer.starts_at;
  return (
    <Sheet open onClose={onClose} title="Before you go">
      {done ? (
        <div>
          <OkLine>Done. Your L1 runs to the end of the month you paid for. The ₹1,999 plan starts {starts ? `on ${hdate(starts)}` : "when it ends"}, and the first payment is taken that day.</OkLine>
          <Button className="w-full mt-4" onClick={onClose}>Done</Button>
        </div>
      ) : (
        <div data-testid="downsell">
          <p className="text-[16px]">{offer.msg}</p>
          <div className="mt-4 grid gap-2">
            {offer.periods.map((p) => (
              <Button key={p.period} variant={p.period === "monthly" ? "primary" : "secondary"} loading={busy === `member:${p.period}`} onClick={() => buy("member", p.period)} data-testid={`downsell-${p.period}`}>
                {inr(p.price_inr)} + GST a {p.period === "yearly" ? "year" : "month"}
              </Button>
            ))}
          </div>
          {error && <p className="text-sm text-bz-miss mt-2" role="alert">{error}</p>}
          <button type="button" onClick={onClose} className="mt-3 w-full text-[14px] font-bold text-bz-muted min-h-[44px]">No thanks</button>
        </div>
      )}
    </Sheet>
  );
}

function PlanDetails() {
  const { plan, refreshMe } = useAuth();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");
  const [offer, setOffer] = useState(null);
  const p = plan || {};
  // POST /billing/cancel stops, in order: the running plan (at the end of the paid period), a plan that starts later,
  // or an L1 paused for L2. Each button below is shown only when that one is next in line.
  const running = p.source === "paid" && !p.cancelling;
  const scheduled = !running && p.scheduled;
  const pausedL1 = !running && !scheduled && p.paused_for_l2;
  const cancel = async () => {
    const ask = pausedL1 ? "Cancel your paused L1? It won't restart after L2, and you won't be charged for it again."
      : scheduled ? `Cancel the ${scheduled.label || "plan"} that starts on ${hdate(scheduled.starts_at)}? Nothing will be charged.`
        : "Cancel your subscription? You keep your plan until the end of the period you paid for.";
    if (!window.confirm(ask)) return;
    setErr(""); setMsg(""); setBusy(true);
    try {
      const { data } = await api.post("/billing/cancel");
      if (data?.kind === "paused") setMsg("Cancelled. Your L1 won't restart after L2 ends. You keep L2 until then.");
      else if (data?.kind === "scheduled") setMsg("Cancelled. That plan won't start and nothing will be charged.");
      else {
        const until = data?.access_until ? hdate(data.access_until) : null;
        setMsg(`Cancelled. You keep the ${p.label || "plan"}${until ? ` until ${until}` : " to the end of the paid period"} and won't be charged again.`);
      }
      if (data?.offer) setOffer(data.offer);
      refreshMe();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const limits = Object.entries(p.limits || {});
  return (
    <Card>
      <Label>Your plan</Label>
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-[24px] font-extrabold">{p.label || PLAN_LABEL[p.plan] || "Free account"}</span>
        {p.period === "yearly" && <PlanChip plan={{ ...p, label: "Yearly" }} />}
      </div>
      <p className="text-[14.5px] text-bz-muted mt-1">
        {SOURCE[p.source] || ""}
        {p.paid_until && p.source === "paid" ? (p.cancelling ? ` · cancelled, ends ${hdate(p.paid_until)}` : ` · renews ${hdate(p.paid_until)}`) : ""}
      </p>
      {p.l2?.active && <p className="text-[14.5px] mt-2">L2 runs until <b className="text-bz-gold">{hdate(p.l2.ends_at)}</b>.{p.paused_for_l2 ? " Your L1 is paused and restarts by itself after that." : " After that you can start L1 again from Plans."}</p>}
      {p.scheduled && <p className="text-[14.5px] mt-2" data-testid="plan-scheduled">Your <b>{p.scheduled.label || PLAN_LABEL[p.scheduled.plan]}</b>{p.scheduled.period === "yearly" ? " (yearly)" : ""} starts on <b className="text-bz-gold">{hdate(p.scheduled.starts_at)}</b>. The first payment is taken that day.</p>}
      {limits.length > 0 && (
        <div className="mt-5 space-y-3" data-testid="usage-meters">
          <Label className="mb-0">{p.plan === "free" ? "Your free goes" : "This month"}</Label>
          {limits.map(([k, u]) => {
            const used = Number(u?.used) || 0;
            const lim = u?.limit;
            return (
              <div key={k}>
                <div className="flex justify-between text-[14px]">
                  <span>{USAGE_NAME[k] || k}</span>
                  <span className="tabular text-bz-muted">{lim === 0 ? "Not on your plan" : lim == null ? `${used} used` : `${used} of ${lim}`}</span>
                </div>
                {lim ? <Meter value={(used / lim) * 100} className="mt-1 h-1.5" label={USAGE_NAME[k] || k} /> : null}
              </div>
            );
          })}
        </div>
      )}
      <div className="mt-5 flex flex-col sm:flex-row gap-2">
        {p.plan !== "l2" && <LinkButton to="/app/plans" variant="secondary" className="sm:flex-1">See plans</LinkButton>}
        {running && <Button variant="danger" onClick={cancel} loading={busy} data-testid="billing-cancel">Cancel subscription</Button>}
        {scheduled && <Button variant="danger" onClick={cancel} loading={busy} data-testid="billing-cancel-scheduled">Cancel the plan that starts later</Button>}
        {pausedL1 && <Button variant="danger" onClick={cancel} loading={busy} data-testid="billing-cancel-paused">Cancel my paused L1</Button>}
      </div>
      <OkLine>{msg}</OkLine>
      {err && <p className="text-sm text-bz-miss mt-2" role="alert">{err}</p>}
      {offer && <Offer offer={offer} onClose={() => setOffer(null)} />}
    </Card>
  );
}

export default function Account() {
  const { logout, user } = useAuth();
  const nav = useNavigate();
  return (
    <div className="space-y-4">
      <PageHeader kicker="Account" title="Your" accent="account." />
      <div className="grid gap-4 md:grid-cols-2 items-start">
        <PlanDetails />
        <Profile />
      </div>
      {user?.role === "admin" && <Link to="/admin" className="block text-[15px] font-bold text-bz-gold min-h-[44px]">Open the admin panel</Link>}
      <div className="flex flex-wrap gap-x-5 gap-y-2 text-[14px]">
        <Link to="/terms" className="text-bz-muted hover:text-bz-ink">Terms</Link>
        <Link to="/privacy" className="text-bz-muted hover:text-bz-ink">Privacy</Link>
      </div>
      <Button variant="secondary" className="w-full sm:w-auto" data-testid="account-logout" onClick={async () => { await logout(); nav("/login", { replace: true }); }}>Log out</Button>
    </div>
  );
}
