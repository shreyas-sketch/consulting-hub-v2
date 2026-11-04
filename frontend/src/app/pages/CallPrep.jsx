// /app/call-prep and /app/call-prep/:id — Discovery Call Prep: who you're meeting in, a printable page out:
// 30-minute agenda, opening line, questions mapped to the six framework steps, likely problems, objections with
// answers, what not to say, and the next step to propose. Optional news (links only from search).
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import {
  AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, PageHeader, RowLink, Step, Textarea, Thinking,
} from "../components/ui";

const H = ({ children }) => <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-2">{children}</p>;

export function PrepBody({ p }) {
  const byStep = {};
  (p.questions || []).forEach((q) => { (byStep[q.step] = byStep[q.step] || []).push(q); });
  const total = (p.agenda || []).reduce((a, x) => a + (x.minutes || 0), 0);
  return (
    <AiFrame title="Discovery Call Prep" right={<span className="text-[12px] text-bz-muted">{hdate(p.at)}</span>} className="print-plain">
      <p className="text-[24px] font-extrabold tracking-[-0.01em] leading-tight">{p.input.company}</p>
      {(p.input.person || p.input.role) && <p className="text-[14px] text-bz-muted mt-1">{[p.input.person, p.input.role].filter(Boolean).join(" · ")}</p>}

      <div className="mt-5">
        <H>Agenda · {total} minutes</H>
        <ol className="space-y-1.5">
          {p.agenda.map((a, i) => (
            <li key={i} className="flex gap-3 text-[15px]"><span className="w-12 shrink-0 font-extrabold text-bz-gold tabular">{a.minutes} min</span><span>{a.item}</span></li>
          ))}
        </ol>
      </div>

      <div className="mt-5 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
        <H>Opening line</H>
        <p className="text-[15px] italic">“{p.opening}”</p>
      </div>

      <div className="mt-5">
        <H>Questions, step by step</H>
        <div className="space-y-4">
          {Object.keys(byStep).sort().map((s) => (
            <div key={s}>
              <p className="font-bold text-[14px] text-bz-gold">Step {s} · {p.steps?.[s]}</p>
              <ul className="mt-1.5 space-y-2">
                {byStep[s].map((q) => (
                  <li key={q.question} className="text-[15px]">
                    <p>{q.question}</p>
                    {q.why && <p className="text-[13px] text-bz-muted mt-0.5">{q.why}</p>}
                  </li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </div>

      {p.problems?.length > 0 && (
        <div className="mt-5">
          <H>Likely problems</H>
          <div className="space-y-3">{p.problems.map((x, i) => <Step key={x.problem} n={i + 1} ai title={x.problem}>{x.why}</Step>)}</div>
        </div>
      )}

      {p.objections?.length > 0 && (
        <div className="mt-5">
          <H>Likely objections</H>
          <ul className="space-y-2.5">
            {p.objections.map((o) => (
              <li key={o.objection} className="rounded-bzcard border border-bz-line bg-bz-panel p-3">
                <p className="font-bold text-[15px]">“{o.objection}”</p>
                <p className="text-[14px] mt-1">{o.answer}</p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {p.avoid?.length > 0 && (
        <div className="mt-5">
          <H>What not to say</H>
          <ul className="list-disc pl-5 space-y-1 text-[15px] marker:text-bz-miss">{p.avoid.map((a) => <li key={a}>{a}</li>)}</ul>
        </div>
      )}

      <div className="mt-5 rounded-bzcard border border-bz-gold bg-bz-gold-tint p-3.5">
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-1">The next step to propose</p>
        <p className="text-[15px]">{p.next_step}</p>
      </div>

      {p.news?.length > 0 && (
        <div className="mt-5">
          <H>In the news</H>
          <ul className="space-y-2">
            {p.news.map((n) => (
              <li key={n.url} className="rounded-bzcard border border-bz-line bg-bz-panel p-3">
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="font-bold text-[14px] hover:text-bz-teal inline-flex gap-1.5 items-start">
                  {n.title}<ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0 text-bz-teal" aria-hidden />
                </a>
                <p className="text-[12px] text-bz-muted mt-0.5">{n.source}{n.published ? ` · ${n.published}` : ""}</p>
                {n.why && <p className="text-[14px] mt-1">{n.why}</p>}
              </li>
            ))}
          </ul>
          {p.test && <p className="text-[12px] text-bz-muted mt-2">Test mode: these are sample links, not real news.</p>}
        </div>
      )}
    </AiFrame>
  );
}

function View() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["call-prep", id], queryFn: async () => (await api.get(`/call-prep/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/call-prep">All call preps</BackLink>
      <Loadable q={q} what="this call prep" lines={10}>
        {(p) => (
          <div className="space-y-3">
            <PrepBody p={p} />
            <div className="flex flex-col sm:flex-row gap-2 no-print">
              <Button variant="secondary" onClick={() => window.print()} data-testid="callprep-print">Print or save as PDF</Button>
              <Link to={`/app/proposals?prep=${p.id}&company=${encodeURIComponent(p.input.company)}&person=${encodeURIComponent(p.input.person || "")}&role=${encodeURIComponent(p.input.role || "")}`}
                className="inline-flex items-center justify-center min-h-[52px] px-6 rounded-full border border-bz-rule font-bold text-[15px] hover:border-bz-gold" data-testid="callprep-to-proposal">
                After the call: write the proposal
              </Link>
            </div>
          </div>
        )}
      </Loadable>
    </div>
  );
}

function Form() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["call-preps"], queryFn: async () => (await api.get("/call-prep")).data });
  const [f, setF] = useState({ company: "", person: "", role: "", how_met: "", known: "", search: true });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.call_prep;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const run = async (e) => {
    e.preventDefault();
    if (f.company.trim().length < 2) { setErr("Type the company's name."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/call-prep", f);
      qc.setQueryData(["call-prep", data.id], data); qc.invalidateQueries({ queryKey: ["call-preps"] }); refreshMe();
      nav(`/app/call-prep/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      {busy ? <AiFrame title="Discovery Call Prep"><Thinking label={`Preparing your call with ${f.company}`} /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-3">
            <Field label="Company"><Input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} maxLength={120} placeholder="e.g. Desai Pumps" data-testid="callprep-company" /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Who you're meeting (optional)"><Input value={f.person} onChange={(e) => setF({ ...f, person: e.target.value })} maxLength={120} placeholder="e.g. Rahul Desai" data-testid="callprep-person" /></Field>
              <Field label="Their role (optional)"><Input value={f.role} onChange={(e) => setF({ ...f, role: e.target.value })} maxLength={120} placeholder="e.g. Managing Director" /></Field>
            </div>
            <Field label="How you met (optional)"><Input value={f.how_met} onChange={(e) => setF({ ...f, how_met: e.target.value })} maxLength={300} placeholder="e.g. Ex-colleague, replied to my LinkedIn post" /></Field>
            <Field label="What you know so far (optional)"><Textarea rows={4} value={f.known} onChange={(e) => setF({ ...f, known: e.target.value })} maxLength={2000} placeholder="What they told you, what you've read, numbers you know." data-testid="callprep-known" /></Field>
            <label className="flex items-center gap-3 min-h-[44px] cursor-pointer">
              <input type="checkbox" checked={f.search} onChange={(e) => setF({ ...f, search: e.target.checked })} className="w-5 h-5 accent-[#c9a84c]" data-testid="callprep-search" />
              <span className="text-[15px]">Look up recent news on the company</span>
            </label>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="callprep-run">Prepare my call</Button>
            <UsageLine usage={usage} what="call preps" className="text-center" />
          </form>
        </Card>
      )}
      <Loadable q={list} what="your call preps">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your call preps</Label>
            {d.items.map((p) => <RowLink key={p.id} to={`/app/call-prep/${p.id}`} title={p.company} sub={[p.person, hdate(p.at)].filter(Boolean).join(" · ")} testid={`callprep-${p.id}`} right={<Chip tone="teal">Open</Chip>} />)}
          </Card>
        ) : null}
      </Loadable>
    </div>
  );
}

export default function CallPrep() {
  const { id } = useParams();
  return (
    <div className="space-y-5">
      {!id && <PageHeader kicker="Discovery Call Prep" ai title="Walk into the first call" accent="knowing what to ask."
        sub="Tell us who you're meeting. You get a 30-minute agenda, questions that follow the six steps, likely objections and the next step to propose." />}
      <Gate feature="call_prep">{id ? <View /> : <Form />}</Gate>
    </div>
  );
}
