// /app/support and /app/support/:id — write to the team (billing, tools, program, other), see their replies,
// reply back or close the question. A reply on a closed question opens it again.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { dtime, hdate } from "@/lib/format";
import { BackLink, Gate, Para } from "../components/common";
import { Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, Note, PageHeader, RowLink, Segmented, Textarea } from "../components/ui";

const CATEGORIES = [
  { value: "billing", label: "Payments" }, { value: "tools", label: "Tools" },
  { value: "program", label: "Program" }, { value: "other", label: "Something else" },
];
const CAT = Object.fromEntries(CATEGORIES.map((c) => [c.value, c.label]));
const STATUS = { open: ["Waiting for the team", "muted"], answered: ["Team replied", "gold"], closed: ["Closed", "muted"] };

export function StatusChip({ status }) {
  const [label, tone] = STATUS[status] || STATUS.open;
  return <Chip tone={tone}>{label}</Chip>;
}

function NewTicket() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [f, setF] = useState({ subject: "", category: "tools", text: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    if (f.subject.trim().length < 3) { setErr("Add a short subject, like 'Payment taken twice'."); return; }
    if (f.text.trim().length < 5) { setErr("Tell us a little more, so the team can help."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/support/tickets", f);
      qc.setQueryData(["ticket", data.id], data);
      qc.invalidateQueries({ queryKey: ["tickets"] });
      nav(`/app/support/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <Card>
      <Label>Write to the team</Label>
      <form onSubmit={submit} noValidate className="space-y-3">
        <Field label="What is it about?">
          <Segmented options={CATEGORIES} value={f.category} onChange={(v) => setF({ ...f, category: v })} label="Topic" testid="support-cat" />
        </Field>
        <Field label="Subject"><Input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} maxLength={140} placeholder="e.g. My deck didn't download" data-testid="support-subject" /></Field>
        <Field label="Your message" hint="Add what you tried and what you saw. For payments, add the date and amount.">
          <Textarea value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} maxLength={4000} data-testid="support-text" />
        </Field>
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" className="w-full" loading={busy} data-testid="support-send">Send to the team</Button>
      </form>
    </Card>
  );
}

function Thread({ id }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["ticket", id], queryFn: async () => (await api.get(`/support/tickets/${id}`)).data });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const done = (data) => { qc.setQueryData(["ticket", id], data); qc.invalidateQueries({ queryKey: ["tickets"] }); };
  const reply = async () => {
    if (!text.trim()) return;
    setErr(""); setBusy(true);
    try { done((await api.post(`/support/tickets/${id}/reply`, { text })).data); setText(""); }
    catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  const close = async () => {
    setErr("");
    try { done((await api.post(`/support/tickets/${id}/close`)).data); } catch (e) { setErr(apiError(e)); }
  };
  return (
    <div className="space-y-4">
      <BackLink to="/app/support">All your questions</BackLink>
      <Loadable q={q} what="this question" lines={5}>
        {(t) => (
          <>
            <div>
              <div className="flex flex-wrap items-center gap-2"><StatusChip status={t.status} /><Chip>{CAT[t.category] || t.category}</Chip></div>
              <h1 className="font-display text-[24px] sm:text-[30px] font-[450] tracking-[-0.02em] leading-tight mt-3">{t.subject}</h1>
              <p className="text-[13px] text-bz-muted mt-1">Started {hdate(t.created_at)}</p>
            </div>
            <div className="space-y-3" data-testid="support-thread">
              {t.messages.map((m, i) => (m.from === "team" ? (
                <Card key={i} className="border-bz-gold" data-testid="support-team-msg">
                  <div className="flex items-center justify-between gap-2 mb-1.5"><Label className="mb-0">Support team</Label><span className="text-[12px] text-bz-muted">{dtime(m.at)}</span></div>
                  <Para text={m.text} className="text-[15px]" />
                </Card>
              ) : (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[88%] rounded-bzcard rounded-br-md bg-bz-raised border border-bz-line px-4 py-3">
                    <Para text={m.text} className="text-[15px]" />
                    <p className="text-[12px] text-bz-muted mt-1 text-right">You · {dtime(m.at)}</p>
                  </div>
                </div>
              )))}
            </div>
            <Card>
              <Field label={t.status === "closed" ? "Write again to open this question" : "Add a reply"}>
                <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} placeholder="Type your reply" data-testid="support-reply" />
              </Field>
              <ErrorLine>{err}</ErrorLine>
              <div className="flex flex-col sm:flex-row gap-2 mt-3">
                <Button className="flex-1" onClick={reply} loading={busy} disabled={!text.trim()} data-testid="support-reply-send">Send reply</Button>
                {t.status !== "closed" && <Button variant="secondary" onClick={close} data-testid="support-close">My question is solved</Button>}
              </div>
              {t.status === "open" && <Note className="mt-2">The team usually replies within one working day. You'll get a message in your inbox.</Note>}
            </Card>
          </>
        )}
      </Loadable>
    </div>
  );
}

function List() {
  const q = useQuery({ queryKey: ["tickets"], queryFn: async () => (await api.get("/support/tickets")).data });
  return (
    <div className="space-y-5">
      <PageHeader kicker="Support" title="Ask the team," accent="get an answer."
        sub="Write to us about the tools, your plan or a payment. The team replies here, and you get a message in your inbox." />
      <NewTicket />
      <Loadable q={q} what="your questions">
        {(d) => (d.items || []).length ? (
          <Card data-testid="support-list">
            <Label>Your questions</Label>
            {d.items.map((t) => (
              <RowLink key={t.id} to={`/app/support/${t.id}`} title={t.subject} testid={`ticket-${t.id}`}
                sub={`${CAT[t.category] || t.category} · ${hdate(t.updated_at)}`} right={<StatusChip status={t.status} />} />
            ))}
          </Card>
        ) : null}
      </Loadable>
    </div>
  );
}

export default function Support() {
  const { id } = useParams();
  const header = <PageHeader kicker="Support" title="Ask the team," accent="get an answer." />;
  return <Gate feature="support" header={header}>{id ? <Thread id={id} /> : <List />}</Gate>;
}
