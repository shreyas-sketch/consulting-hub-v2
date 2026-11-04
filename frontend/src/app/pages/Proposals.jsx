// /app/proposals and /app/proposals/:id — Proposal Follow-through: call notes + fee range in, a proposal in Markdown
// (six framework stages, three ₹ options) and three follow-up messages (day 2, 5, 10) out. The member sends them;
// the status moves draft → sent → follow-up 1/2/3 → won or lost, and the inbox reminds them when a follow-up is due.
// Call Prep links in with ?prep=<id>&company=&person=&role=.
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate, inr } from "@/lib/format";
import { BackLink, Gate, Para, UsageLine } from "../components/common";
import Markdown, { CopyButton } from "../components/Markdown";
import {
  AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, MoneyInput, Note, PageHeader, RowLink, Stat,
  Textarea, Thinking,
} from "../components/ui";

const STATUS = { draft: "Draft", sent: "Sent", fu1: "Follow-up 1 done", fu2: "Follow-up 2 done", fu3: "Follow-up 3 done", won: "Won", lost: "Lost" };
const tone = (s) => (s === "won" ? "solid" : s === "lost" ? "miss" : s === "draft" ? "muted" : "gold");

function FollowUp({ p, f, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [t, setT] = useState(f.text);
  const [busy, setBusy] = useState(false);
  const isNext = p.next?.n === f.n;
  const save = async () => {
    setBusy(true);
    try { onSaved((await api.patch(`/proposals/${p.id}`, { followup: { n: f.n, text: t } })).data); setEdit(false); } catch { /* stays open */ } finally { setBusy(false); }
  };
  const done = async () => {
    setBusy(true);
    try { onSaved((await api.patch(`/proposals/${p.id}`, { status: `fu${f.n}` })).data); } catch { /* ignore */ } finally { setBusy(false); }
  };
  return (
    <div className={`rounded-bzcard border p-3.5 ${isNext ? (p.next.is_due ? "border-bz-gold bg-bz-gold-tint" : "border-bz-line-strong bg-bz-panel") : "border-bz-line bg-bz-panel"}`} data-testid={`proposal-followup-${f.n}`}>
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <p className="text-[13px] font-bold">Follow-up {f.n} · day {f.day}{f.due ? ` · ${hdate(f.due)}` : ""}</p>
        <div className="flex items-center gap-1">
          {f.done ? <Chip tone="gold">Done</Chip> : isNext && p.next.is_due ? <Chip tone="solid">Due today</Chip> : null}
          {!edit && <CopyButton text={f.text} />}
        </div>
      </div>
      {edit ? (
        <div className="space-y-2">
          <Textarea rows={4} value={t} onChange={(e) => setT(e.target.value)} maxLength={1200} />
          <div className="flex gap-2"><Button variant="small" onClick={save} loading={busy}>Save</Button><Button variant="small" onClick={() => { setEdit(false); setT(f.text); }}>Cancel</Button></div>
        </div>
      ) : (
        <>
          <Para text={f.text} className="text-[14.5px]" />
          <div className="flex flex-wrap gap-2 mt-2.5 no-print">
            <Button variant="small" onClick={() => setEdit(true)}>Edit</Button>
            {isNext && <Button variant="small" onClick={done} loading={busy} data-testid={`proposal-followup-done-${f.n}`}>I sent follow-up {f.n}</Button>}
          </div>
        </>
      )}
    </div>
  );
}

function Detail() {
  const { id } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["proposal", id], queryFn: async () => (await api.get(`/proposals/${id}`)).data });
  const [edit, setEdit] = useState(false);
  const [md, setMd] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const saved = (d) => { qc.setQueryData(["proposal", id], d); qc.invalidateQueries({ queryKey: ["proposals"] }); };
  const patch = async (body, key) => {
    setBusy(key); setErr("");
    try { saved((await api.patch(`/proposals/${id}`, body)).data); return true; } catch (e) { setErr(apiError(e)); return false; } finally { setBusy(""); }
  };
  return (
    <div className="space-y-4">
      <BackLink to="/app/proposals">All proposals</BackLink>
      <Loadable q={q} what="this proposal" lines={10}>
        {(p) => (
          <div className="space-y-4">
            <Card className="no-print">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[20px] font-extrabold leading-tight">{p.client.company}</p>
                  <p className="text-[13px] text-bz-muted">{[p.client.person, p.client.role].filter(Boolean).join(" · ")}{p.sent_at ? ` · sent ${hdate(p.sent_at)}` : ""}</p>
                </div>
                <Chip tone={tone(p.status)} className="shrink-0">{STATUS[p.status]}</Chip>
              </div>
              <div className="mt-4 flex flex-col sm:flex-row gap-2">
                {p.status === "draft" && <Button onClick={() => patch({ status: "sent" }, "sent")} loading={busy === "sent"} data-testid="proposal-sent">I've sent it to the client</Button>}
                {p.status !== "won" && p.status !== "draft" && <Button variant="secondary" onClick={() => patch({ status: "won" }, "won")} loading={busy === "won"} data-testid="proposal-won">They said yes</Button>}
                {p.status !== "lost" && p.status !== "draft" && <Button variant="quiet" onClick={() => patch({ status: "lost" }, "lost")} loading={busy === "lost"} data-testid="proposal-lost">They said no</Button>}
                {(p.status === "won" || p.status === "lost") && <Button variant="quiet" onClick={() => patch({ status: "sent" }, "sent")} loading={busy === "sent"}>Still open</Button>}
              </div>
              {p.status === "draft" && <Note className="mt-2">When you mark it sent, we set your follow-ups for day 2, 5 and 10 and remind you in your inbox.</Note>}
              <ErrorLine>{err}</ErrorLine>
            </Card>

            {p.status !== "draft" && (
              <Card className="no-print">
                <Label>Follow-up plan</Label>
                <div className="space-y-2.5">{p.followups.map((f) => <FollowUp key={f.n} p={p} f={f} onSaved={saved} />)}</div>
                <Note className="mt-2">You send each message yourself. We only remind you.</Note>
              </Card>
            )}

            <AiFrame title="Your proposal" className="print-plain" right={!edit && <CopyButton text={p.markdown} label="Copy all" />}>
              {edit ? (
                <div className="space-y-2 no-print">
                  <Textarea rows={20} value={md} onChange={(e) => setMd(e.target.value)} maxLength={30000} className="font-bzmono text-[14px]" data-testid="proposal-markdown" />
                  <div className="flex gap-2">
                    <Button variant="small" loading={busy === "md"} onClick={async () => { if (await patch({ markdown: md }, "md")) setEdit(false); }}>Save</Button>
                    <Button variant="small" onClick={() => setEdit(false)}>Cancel</Button>
                  </div>
                </div>
              ) : <Markdown text={p.markdown} />}
            </AiFrame>
            {!edit && (
              <div className="flex flex-col sm:flex-row gap-2 no-print">
                <Button variant="secondary" onClick={() => { setMd(p.markdown); setEdit(true); }} data-testid="proposal-edit">Edit the proposal</Button>
                <Button variant="secondary" onClick={() => window.print()} data-testid="proposal-print">Print or save as PDF</Button>
              </div>
            )}
            {p.status === "draft" && (
              <Card inset className="no-print">
                <Label tone="muted">Follow-ups ready for after you send it</Label>
                <div className="space-y-2">{p.followups.map((f) => <p key={f.n} className="text-[14px]"><span className="font-bold">Day {f.day}:</span> {f.text}</p>)}</div>
              </Card>
            )}
          </div>
        )}
      </Loadable>
    </div>
  );
}

function NewForm() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const [f, setF] = useState({ company: sp.get("company") || "", person: sp.get("person") || "", role: sp.get("role") || "", notes: "", fee_low_inr: 100000, fee_high_inr: 300000 });
  const prep = sp.get("prep") || null;
  const list = useQuery({ queryKey: ["proposals"], queryFn: async () => (await api.get("/proposals")).data });
  const [opened, setOpen] = useState(!!sp.get("company"));
  const open = opened || (list.isSuccess && !(list.data.items || []).length);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.proposal;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const run = async (e) => {
    e.preventDefault();
    if (f.company.trim().length < 2) { setErr("Type the client's company."); return; }
    if (f.notes.trim().length < 40) { setErr("Add your call notes: what they said, the problem, what they want. A few lines is enough."); return; }
    if (!f.fee_low_inr || !f.fee_high_inr || f.fee_low_inr < 5000) { setErr("Add your fee range. The lowest is ₹5,000."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/proposals", { ...f, call_prep_id: prep });
      qc.setQueryData(["proposal", data.id], data); qc.invalidateQueries({ queryKey: ["proposals"] }); refreshMe();
      nav(`/app/proposals/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  if (busy) return <AiFrame title="Proposal"><Thinking label={`Writing the proposal for ${f.company}`} /></AiFrame>;
  if (!open) return <Button className="w-full" onClick={() => setOpen(true)} data-testid="proposal-new">Write a new proposal</Button>;
  return (
    <Card>
      <form onSubmit={run} noValidate className="space-y-3">
        <Field label="Client company"><Input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} maxLength={120} placeholder="e.g. Desai Pumps" data-testid="proposal-company" /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Person (optional)"><Input value={f.person} onChange={(e) => setF({ ...f, person: e.target.value })} maxLength={120} placeholder="e.g. Rahul Desai" /></Field>
          <Field label="Their role (optional)"><Input value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} maxLength={120} placeholder="e.g. MD" /></Field>
        </div>
        <Field label="Your call notes" hint="What they said, the problem in their words, numbers they shared, what they want and by when.">
          <Textarea rows={6} value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} maxLength={6000} data-testid="proposal-notes" />
        </Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Fee from"><MoneyInput value={f.fee_low_inr} onChange={(v) => setF({ ...f, fee_low_inr: v })} data-testid="proposal-fee-low" /></Field>
          <Field label="Fee up to"><MoneyInput value={f.fee_high_inr} onChange={(v) => setF({ ...f, fee_high_inr: v })} data-testid="proposal-fee-high" /></Field>
        </div>
        {prep && <Note>Using your call prep for this client too.</Note>}
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="proposal-run">Write my proposal</Button>
        <UsageLine usage={usage} what="proposals" className="text-center" />
      </form>
    </Card>
  );
}

function List() {
  const q = useQuery({ queryKey: ["proposals"], queryFn: async () => (await api.get("/proposals")).data });
  return (
    <Loadable q={q} what="your proposals" lines={4}>
      {(d) => {
        const c = d.counts || {};
        const open = (c.sent || 0) + (c.fu1 || 0) + (c.fu2 || 0) + (c.fu3 || 0);
        return (d.items || []).length ? (
          <div className="space-y-3">
            <div className="grid grid-cols-3 gap-2">
              <Stat label="Open" value={open} sub={d.due ? `${d.due} follow-up${d.due > 1 ? "s" : ""} due` : "Nothing due"} />
              <Stat label="Won" value={c.won || 0} />
              <Stat label="Drafts" value={c.draft || 0} />
            </div>
            <Card>
              <Label>Your proposals</Label>
              {d.items.map((p) => (
                <RowLink key={p.id} to={`/app/proposals/${p.id}`} title={p.client.company} testid={`proposal-${p.id}`}
                  sub={p.next ? `Follow-up ${p.next.n}${p.next.is_due ? " due now" : ` on ${hdate(p.next.due)}`}` : [p.top_option_inr ? `Up to ${inr(p.top_option_inr)}` : "", hdate(p.at)].filter(Boolean).join(" · ")}
                  right={<Chip tone={p.next?.is_due ? "solid" : tone(p.status)}>{p.next?.is_due ? "Follow up" : STATUS[p.status]}</Chip>} />
              ))}
            </Card>
          </div>
        ) : null;
      }}
    </Loadable>
  );
}

export default function Proposals() {
  const { id } = useParams();
  return (
    <div className="space-y-5">
      {!id && <PageHeader kicker="Proposal Follow-through" ai title="From a good call" accent="to a signed client."
        sub="Paste your call notes and your fee range. You get a proposal built on the six steps, three price options and three follow-up messages. You send them; we remind you when." />}
      <Gate feature="proposal">{id ? <Detail /> : (<><NewForm /><List /></>)}</Gate>
    </div>
  );
}
