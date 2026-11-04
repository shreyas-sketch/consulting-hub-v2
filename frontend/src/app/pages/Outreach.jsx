// /app/outreach and /app/outreach/:id — Outreach Drafter: pick a contact from the Warm Network Finder (?contact=<id>)
// or type one (Opportunity Radar links in with ?company=&context=), choose the channel and goal, get three drafts
// (short, warm, direct). The member copies one and sends it themselves, then marks it sent.
import { useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { BackLink, Gate, Para, UsageLine } from "../components/common";
import { CopyButton } from "../components/Markdown";
import {
  AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, Note, PageHeader, RowLink, Segmented,
  Textarea, Thinking,
} from "../components/ui";

const CHANNELS = [{ value: "linkedin", label: "LinkedIn" }, { value: "whatsapp", label: "WhatsApp" }, { value: "email", label: "Email" }];
const GOALS = [{ value: "reconnect", label: "Reconnect" }, { value: "intro", label: "Ask for an introduction" },
  { value: "diagnostic_call", label: "Offer a short diagnostic call" }];
const STYLE = { short: "Short", warm: "Warm", direct: "Direct" };
const label = (list, v) => (list.find((x) => x.value === v) || {}).label || v;

function Variant({ o, v, onSaved }) {
  const [edit, setEdit] = useState(false);
  const [t, setT] = useState(v.text);
  const [s, setS] = useState(v.subject || "");
  const [busy, setBusy] = useState("");
  const full = o.channel === "email" && v.subject ? `Subject: ${v.subject}\n\n${v.text}` : v.text;
  const save = async () => {
    setBusy("save");
    try { onSaved((await api.patch(`/outreach/${o.id}`, { variants: [{ style: v.style, subject: s, text: t }] })).data); setEdit(false); }
    catch { /* stays open */ } finally { setBusy(""); }
  };
  const sent = async () => {
    setBusy("sent");
    try { onSaved((await api.patch(`/outreach/${o.id}`, { chosen: v.style, status: "sent" })).data); } catch { /* ignore */ } finally { setBusy(""); }
  };
  const chosen = o.status === "sent" && o.chosen === v.style;
  return (
    <div className={`rounded-bzcard border bg-bz-panel p-3.5 ${chosen ? "border-bz-gold" : "border-bz-line"}`} data-testid={`outreach-variant-${v.style}`}>
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal">{STYLE[v.style]}</span>
        <div className="flex items-center gap-1">
          {chosen && <Chip tone="gold">Sent</Chip>}
          {!edit && <CopyButton text={full} />}
        </div>
      </div>
      {edit ? (
        <div className="space-y-2">
          {o.channel === "email" && <Input value={s} onChange={(e) => setS(e.target.value)} maxLength={120} aria-label="Subject" />}
          <Textarea rows={7} value={t} onChange={(e) => setT(e.target.value)} maxLength={2000} />
          <div className="flex gap-2">
            <Button variant="small" onClick={save} loading={busy === "save"}>Save</Button>
            <Button variant="small" onClick={() => { setEdit(false); setT(v.text); setS(v.subject || ""); }}>Cancel</Button>
          </div>
        </div>
      ) : (
        <>
          {o.channel === "email" && v.subject && <p className="text-[14px] font-bold mb-1.5">Subject: {v.subject}</p>}
          <Para text={v.text} className="text-[15px]" />
          <div className="flex flex-wrap gap-2 mt-3 no-print">
            <Button variant="small" onClick={() => setEdit(true)}>Edit</Button>
            {o.status !== "sent" && <Button variant="small" onClick={sent} loading={busy === "sent"} data-testid={`outreach-sent-${v.style}`}>I sent this one</Button>}
          </div>
        </>
      )}
    </div>
  );
}

function Draft({ o, onSaved }) {
  const c = o.contact;
  return (
    <AiFrame title="Three drafts" right={<span className="text-[12px] text-bz-muted">{hdate(o.at)}</span>}>
      <p className="text-[20px] font-extrabold leading-tight">{c.name}</p>
      <p className="text-[13px] text-bz-muted mt-0.5">{[c.role, c.company].filter(Boolean).join(" · ")}</p>
      <div className="flex flex-wrap gap-1.5 mt-2"><Chip>{label(CHANNELS, o.channel)}</Chip><Chip>{label(GOALS, o.goal)}</Chip>
        {o.status === "sent" && <Chip tone="gold">Sent {ago(o.sent_at)}</Chip>}</div>
      <div className="space-y-3 mt-4">{o.variants.map((v) => <Variant key={v.style} o={o} v={v} onSaved={onSaved} />)}</div>
      <Note className="mt-3">We never send anything for you. Copy the one you like, send it yourself, then tap "I sent this one".</Note>
    </AiFrame>
  );
}

function DraftView() {
  const { id } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["outreach", id], queryFn: async () => (await api.get(`/outreach/${id}`)).data });
  const saved = (d) => { qc.setQueryData(["outreach", id], d); qc.invalidateQueries({ queryKey: ["outreach-list"] }); qc.invalidateQueries({ queryKey: ["network"] }); };
  return (
    <div className="space-y-4">
      <BackLink to="/app/outreach">All drafts</BackLink>
      <Loadable q={q} what="this draft" lines={8}>{(o) => <Draft o={o} onSaved={saved} />}</Loadable>
    </div>
  );
}

function Form() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [sp] = useSearchParams();
  const contactId = sp.get("contact") || "";
  const contact = useQuery({ queryKey: ["contact", contactId], enabled: !!contactId, queryFn: async () => (await api.get(`/network/${contactId}`)).data });
  const [f, setF] = useState({ name: sp.get("name") || "", role: "", company: sp.get("company") || "", relationship: "", context: sp.get("context") || "" });
  const [channel, setChannel] = useState("linkedin");
  const [goal, setGoal] = useState(sp.get("company") ? "diagnostic_call" : "reconnect");
  const [useContact, setUseContact] = useState(!!contactId);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.outreach;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  useEffect(() => { setUseContact(!!contactId); }, [contactId]);
  const c = useContact ? contact.data : null;

  const run = async (e) => {
    e.preventDefault();
    if (!c && f.name.trim().length < 2) { setErr("Type the person's name."); return; }
    setErr(""); setBusy(true);
    try {
      const body = { ...f, channel, goal, ...(c ? { contact_id: c.id } : {}) };
      const { data } = await api.post("/outreach", body);
      qc.setQueryData(["outreach", data.id], data); qc.invalidateQueries({ queryKey: ["outreach-list"] }); refreshMe();
      nav(`/app/outreach/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  if (busy) return <AiFrame title="Outreach"><Thinking label={`Writing three drafts to ${c?.name || f.name}`} /></AiFrame>;
  return (
    <Card>
      <form onSubmit={run} noValidate className="space-y-4">
        {c ? (
          <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
            <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-muted">Writing to</p>
            <p className="font-bold text-[16px] mt-1">{c.name}</p>
            <p className="text-[13px] text-bz-muted">{[c.position, c.company].filter(Boolean).join(" · ")}</p>
            {c.angle && <p className="text-[13px] text-bz-teal mt-1.5">Angle: {c.angle}</p>}
            <button type="button" className="text-[13px] font-bold text-bz-gold min-h-[40px]" onClick={() => setUseContact(false)}>Write to someone else</button>
          </div>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Their name"><Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} maxLength={120} placeholder="e.g. Meera Kapoor" data-testid="outreach-name" /></Field>
            <Field label="Their role (optional)"><Input value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} maxLength={160} placeholder="e.g. COO" /></Field>
            <Field label="Company (optional)" className="sm:col-span-2"><Input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} maxLength={160} placeholder="e.g. Sunrise Textiles" data-testid="outreach-company" /></Field>
          </div>
        )}
        <Field label="How you know each other (optional)"><Input value={f.relationship} onChange={(e) => setF({ ...f, relationship: e.target.value })} maxLength={200} placeholder="e.g. Worked together at Arvind, 2010–14" data-testid="outreach-relationship" /></Field>
        <Field label="Anything else worth mentioning (optional)" hint="Recent news, the last time you spoke, a shared friend.">
          <Textarea rows={3} value={f.context} onChange={(e) => setF({ ...f, context: e.target.value })} maxLength={1000} data-testid="outreach-context" />
        </Field>
        <div><Label tone="muted" className="mb-2">Channel</Label><Segmented label="Channel" options={CHANNELS} value={channel} onChange={setChannel} testid="outreach-channel" /></div>
        <div><Label tone="muted" className="mb-2">What you want</Label><Segmented label="Goal" options={GOALS} value={goal} onChange={setGoal} testid="outreach-goal" /></div>
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="outreach-run">Write three drafts</Button>
        <UsageLine usage={usage} what="drafts" className="text-center" />
      </form>
    </Card>
  );
}

function List() {
  const q = useQuery({ queryKey: ["outreach-list"], queryFn: async () => (await api.get("/outreach")).data });
  return (
    <Loadable q={q} what="your drafts">
      {(d) => (d.items || []).length ? (
        <Card>
          <Label>Your drafts</Label>
          {d.items.map((o) => (
            <RowLink key={o.id} to={`/app/outreach/${o.id}`} title={o.contact.name} testid={`outreach-${o.id}`}
              sub={`${label(CHANNELS, o.channel)} · ${label(GOALS, o.goal)} · ${hdate(o.at)}`}
              right={<Chip tone={o.status === "sent" ? "gold" : "muted"}>{o.status === "sent" ? "Sent" : "Draft"}</Chip>} />
          ))}
        </Card>
      ) : null}
    </Loadable>
  );
}

export default function Outreach() {
  const { id } = useParams();
  return (
    <div className="space-y-5">
      {!id && <PageHeader kicker="Outreach Drafter" ai title="Write to people you know," accent="without selling."
        sub="Pick a person, the channel and what you want. You get three short drafts in your voice. You send the one you like." />}
      <Gate feature="outreach">
        {id ? <DraftView /> : (<><Form /><List /></>)}
      </Gate>
    </div>
  );
}
