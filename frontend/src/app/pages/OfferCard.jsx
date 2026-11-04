// /app/offer and /app/offer/:id — Offer Card: the member's consulting offer on one printable page.
// The AI writes it from what the app knows (niche, value proposition, stories) plus anything typed here;
// the member can edit every field and save for free, then print or save as PDF.
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate, inr } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, MoneyInput, Note, OkLine, PageHeader, RowLink, Textarea, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Offer Card" title="Your offer" accent="on one page." />;

function Block({ label, children }) {
  if (!children) return null;
  return (
    <div className="min-w-0">
      <p className="text-[11.5px] font-medium uppercase tracking-[0.14em] text-bz-muted mb-1">{label}</p>
      <div className="text-[15.5px] leading-relaxed">{children}</div>
    </div>
  );
}

export function OfferSheet({ c, name }) {
  return (
    <section className="print-plain rounded-bzframe border border-bz-rule bg-bz-card overflow-hidden shadow-goldglow" data-testid="offer-card">
      <div className="h-1.5 bg-gradient-to-r from-[#8F7635] via-[#F0D98A] to-[#8F7635]" aria-hidden />
      <div className="p-5 sm:p-7">
        <div className="flex items-start justify-between gap-3">
          <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">Consulting offer{name ? ` · ${name}` : ""}</p>
          {c.edited ? <Chip className="no-print">Edited by you</Chip> : null}
        </div>
        <h2 className="mt-2 text-[28px] sm:text-[34px] font-extrabold leading-[1.08] tracking-[-0.02em]">{c.offer_name}</h2>
        <p className="mt-2 text-[16px] text-bz-muted">For {c.ideal_client}</p>

        <div className="mt-6 grid gap-5 sm:grid-cols-2">
          <Block label="The problem">{c.problem}</Block>
          <Block label="The outcome">{c.outcome}</Block>
        </div>

        <div className="mt-6">
          <p className="text-[11.5px] font-medium uppercase tracking-[0.14em] text-bz-muted mb-2">What you get</p>
          <ul className="space-y-2">
            {(c.what_you_get || []).map((x) => (
              <li key={x} className="flex gap-2.5 text-[15.5px] leading-snug"><span className="text-bz-gold font-extrabold" aria-hidden>•</span><span className="min-w-0">{x}</span></li>
            ))}
          </ul>
        </div>

        <div className="mt-6 grid gap-4 sm:grid-cols-2">
          <div className="rounded-bzcard border border-bz-line bg-bz-raised px-4 py-3.5 min-w-0">
            <p className="text-[11.5px] font-medium uppercase tracking-[0.12em] text-bz-muted">Investment</p>
            <p className="text-[24px] sm:text-[28px] font-extrabold tracking-[-0.02em] text-bz-gold tabular mt-1 leading-tight" data-testid="offer-fee">
              {c.fee_from_inr === c.fee_to_inr ? inr(c.fee_from_inr) : `${inr(c.fee_from_inr)} – ${inr(c.fee_to_inr)}`}
            </p>
            {c.fee_basis ? <p className="text-[13px] text-bz-muted mt-0.5">{c.fee_basis}</p> : null}
          </div>
          <div className="rounded-bzcard border border-bz-line bg-bz-raised px-4 py-3.5 min-w-0">
            <p className="text-[11.5px] font-medium uppercase tracking-[0.12em] text-bz-muted">Engagement</p>
            <p className="text-[15.5px] font-bold mt-1 leading-snug">{c.engagement}</p>
          </div>
        </div>

        {c.proof ? (
          <blockquote className="mt-6 border-l-[3px] border-bz-gold pl-4 text-[15px] leading-relaxed">
            <p className="text-[11.5px] font-medium uppercase tracking-[0.14em] text-bz-muted mb-1 not-italic">Why me</p>
            {c.proof}
          </blockquote>
        ) : null}

        <div className="mt-6 rounded-bzcard bg-bz-gold-tint border border-bz-rule px-4 py-3.5">
          <p className="text-[16px] font-extrabold text-bz-gold leading-snug">{c.call_to_action}</p>
        </div>
      </div>
    </section>
  );
}

const lines = (t) => String(t || "").split("\n").map((x) => x.trim()).filter(Boolean);

function EditForm({ c, onSaved, onCancel }) {
  const [f, setF] = useState({ ...c, what_you_get: (c.what_you_get || []).join("\n") });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });

  const save = async () => {
    const items = lines(f.what_you_get);
    if (!f.offer_name.trim() || !f.ideal_client.trim() || !f.call_to_action.trim()) { setErr("Fill in the offer name, who it's for and the next step."); return; }
    if (!items.length) { setErr("Add at least one thing the client gets."); return; }
    if (!(Number(f.fee_from_inr) >= 5000) || !(Number(f.fee_to_inr) >= 5000)) { setErr("Fees start at ₹5,000."); return; }
    if (Number(f.fee_to_inr) < Number(f.fee_from_inr)) { setErr("The top of your fee range must be at least the bottom."); return; }
    setErr(""); setBusy(true);
    try {
      const body = { offer_name: f.offer_name, ideal_client: f.ideal_client, problem: f.problem, outcome: f.outcome,
        engagement: f.engagement, what_you_get: items, fee_from_inr: Number(f.fee_from_inr), fee_to_inr: Number(f.fee_to_inr),
        fee_basis: f.fee_basis || "", proof: f.proof || "", call_to_action: f.call_to_action };
      const { data } = await api.put(`/offer-card/${c.id}`, body);
      onSaved(data);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Card className="no-print" data-testid="offer-edit-form">
      <Label>Edit your card</Label>
      <div className="space-y-3">
        <Field label="Offer name"><Input value={f.offer_name} onChange={set("offer_name")} maxLength={80} data-testid="offer-edit-name" /></Field>
        <Field label="Who it's for"><Input value={f.ideal_client} onChange={set("ideal_client")} maxLength={240} /></Field>
        <Field label="The problem"><Textarea rows={3} value={f.problem} onChange={set("problem")} maxLength={300} /></Field>
        <Field label="The outcome"><Textarea rows={3} value={f.outcome} onChange={set("outcome")} maxLength={300} /></Field>
        <Field label="What the client gets" hint="One per line."><Textarea rows={5} value={f.what_you_get} onChange={set("what_you_get")} /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Fee from"><MoneyInput value={f.fee_from_inr} onChange={set("fee_from_inr")} /></Field>
          <Field label="Fee to"><MoneyInput value={f.fee_to_inr} onChange={set("fee_to_inr")} /></Field>
        </div>
        <Field label="Fee is" hint="For example: per month, or for the full engagement."><Input value={f.fee_basis || ""} onChange={set("fee_basis")} maxLength={60} /></Field>
        <Field label="Engagement"><Input value={f.engagement} onChange={set("engagement")} maxLength={200} /></Field>
        <Field label="Why me (proof)"><Textarea rows={3} value={f.proof || ""} onChange={set("proof")} maxLength={400} /></Field>
        <Field label="Next step for the client"><Input value={f.call_to_action} onChange={set("call_to_action")} maxLength={240} /></Field>
        <ErrorLine>{err}</ErrorLine>
        <div className="flex flex-col sm:flex-row gap-3">
          <Button onClick={save} loading={busy} data-testid="offer-save">Save my card</Button>
          <Button variant="secondary" onClick={onCancel}>Cancel</Button>
        </div>
      </div>
    </Card>
  );
}

function MakeForm({ onMade, first, onCancel }) {
  const { plan, refreshMe } = useAuth();
  const [f, setF] = useState({ offer_name: "", engagement: "", what_you_get: "", fee_from_inr: "", fee_to_inr: "", notes: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.offer_card;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const set = (k) => (e) => setF({ ...f, [k]: e?.target ? e.target.value : e });

  const run = async (e) => {
    e.preventDefault();
    const lo = f.fee_from_inr === "" ? null : Number(f.fee_from_inr);
    const hi = f.fee_to_inr === "" ? null : Number(f.fee_to_inr);
    if ((lo !== null && lo < 5000) || (hi !== null && hi < 5000)) { setErr("Fees start at ₹5,000."); return; }
    if (lo !== null && hi !== null && hi < lo) { setErr("The top of your fee range must be at least the bottom."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/offer-card", { ...f, fee_from_inr: lo, fee_to_inr: hi });
      refreshMe();
      onMade(data);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  if (busy) return <AiFrame title="Offer Card"><Thinking label="Writing your offer" /></AiFrame>;
  return (
    <Card className="no-print">
      <form onSubmit={run} noValidate className="space-y-3">
        <Label>{first ? "Make your card" : "Make a new card"}</Label>
        <Note>We start from your niche and value proposition in Starting Point, and the stories in your Story Bank. Fill in anything you already know. Leave the rest empty.</Note>
        <Field label="Offer name (optional)"><Input value={f.offer_name} onChange={set("offer_name")} maxLength={80} placeholder="e.g. The 90-Day Margin Reset" data-testid="offer-name" /></Field>
        <Field label="How long, how often (optional)"><Input value={f.engagement} onChange={set("engagement")} maxLength={160} placeholder="e.g. 3 months, one visit a week" data-testid="offer-engagement" /></Field>
        <Field label="What the client gets (optional)" hint="One per line."><Textarea rows={4} value={f.what_you_get} onChange={set("what_you_get")} maxLength={800} placeholder={"A two-week diagnosis\nA weekly working session"} data-testid="offer-get" /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Fee from (optional)"><MoneyInput value={f.fee_from_inr} onChange={set("fee_from_inr")} placeholder="25000" data-testid="offer-fee-from" /></Field>
          <Field label="Fee to (optional)"><MoneyInput value={f.fee_to_inr} onChange={set("fee_to_inr")} placeholder="75000" data-testid="offer-fee-to" /></Field>
        </div>
        <Field label="Anything else (optional)"><Textarea rows={3} value={f.notes} onChange={set("notes")} maxLength={800} placeholder="A result you're proud of, or who this is really for" /></Field>
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="offer-make">Make my Offer Card</Button>
        <UsageLine usage={usage} what="Offer Cards" className="text-center" />
        {!first && onCancel ? <Button variant="quiet" className="w-full" onClick={onCancel}>Keep my current card</Button> : null}
      </form>
    </Card>
  );
}

export default function OfferCard() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { user } = useAuth();
  const list = useQuery({ queryKey: ["offer-cards"], queryFn: async () => (await api.get("/offer-card")).data });
  const one = useQuery({ queryKey: ["offer-card", id], enabled: !!id, queryFn: async () => (await api.get(`/offer-card/${id}`)).data });
  const [mode, setMode] = useState("view");          // view | edit | new
  const [ok, setOk] = useState("");
  useEffect(() => { setMode("view"); setOk(""); }, [id]);

  const current = id ? one.data : list.data?.latest;
  const refresh = (card) => {
    qc.setQueryData(["offer-card", card.id], card);
    qc.invalidateQueries({ queryKey: ["offer-cards"] }); qc.invalidateQueries({ queryKey: ["file"] });
  };

  return (
    <Gate feature="offer_card" header={HEADER}>
      <div className="space-y-5">
        {id ? <BackLink to="/app/offer">Latest card</BackLink> : null}
        <div className="no-print">
          <PageHeader kicker="Offer Card" title="Your offer" accent="on one page."
            sub="Who you help, the problem, the result, what they get and the fee. One page you can print, send or keep beside you on a call." />
        </div>
        <Loadable q={id ? one : list} what="your Offer Card" lines={8}>
          {() => (
            <>
              {!current || mode === "new" ? (
                <MakeForm first={!current} onCancel={() => setMode("view")} onMade={(card) => { refresh(card); setMode("view"); setOk(""); nav(`/app/offer/${card.id}`); }} />
              ) : null}
              {current && mode === "edit" ? (
                <EditForm c={current} onCancel={() => setMode("view")}
                  onSaved={(card) => { refresh(card); setMode("view"); setOk("Saved."); }} />
              ) : null}
              {current && mode !== "edit" ? (
                <>
                  <OfferSheet c={current} name={user?.name} />
                  <p className="text-[12px] text-bz-muted no-print">Made {hdate(current.at)}{current.edited ? ` · edited ${hdate(current.updated_at)}` : ""}. Fees are a guide for your market, not a promise of income.</p>
                  <OkLine>{ok}</OkLine>
                  {mode === "view" ? (
                    <div className="no-print flex flex-col sm:flex-row gap-3">
                      <Button onClick={() => window.print()} data-testid="offer-print">Print or save as PDF</Button>
                      <Button variant="secondary" onClick={() => { setOk(""); setMode("edit"); }} data-testid="offer-edit">Edit</Button>
                      <Button variant="ai" onClick={() => { setOk(""); setMode("new"); }} data-testid="offer-new">Make a new card</Button>
                    </div>
                  ) : null}
                </>
              ) : null}
            </>
          )}
        </Loadable>
        <Loadable q={list} what="your cards">
          {(d) => (d.history || []).length > 1 ? (
            <Card className="no-print">
              <Label>Your cards</Label>
              {d.history.map((h) => (
                <RowLink key={h.id} to={`/app/offer/${h.id}`} title={h.offer_name} sub={`${hdate(h.at)}${h.edited ? " · edited" : ""}`}
                  testid={`offer-${h.id}`} right={h.id === current?.id ? <Chip tone="gold">Showing</Chip> : undefined} />
              ))}
            </Card>
          ) : null}
        </Loadable>
      </div>
    </Gate>
  );
}
