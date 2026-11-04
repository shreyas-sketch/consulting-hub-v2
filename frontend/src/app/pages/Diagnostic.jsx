// /app/diagnostic and /app/diagnostic/:id — Client Diagnostic: the AI drafts 8-12 questions for the member's niche
// (1-5 scales and short answers) with a scoring rule; the member edits and publishes it on a public link (/d/<id>).
// Each prospect's answers come back as a report (strengths, gaps, top 3 recommendations, next conversation).
// ?r=<response id> opens that report (the inbox alert links there).
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, ExternalLink, Trash2 } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, Gate, Para, ScoreRing, UsageLine } from "../components/common";
import { CopyButton } from "../components/Markdown";
import {
  AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Meter, Note, OkLine, PageHeader, RowLink,
  Segmented, Select, Step, Textarea, Thinking,
} from "../components/ui";

const H = ({ children }) => <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-2">{children}</p>;

function Report({ did, rid }) {
  const q = useQuery({ queryKey: ["diag-resp", did, rid], queryFn: async () => (await api.get(`/diagnostic/${did}/responses/${rid}`)).data });
  return (
    <Loadable q={q} what="this report" lines={8}>
      {(r) => {
        const ctx = `They took my diagnostic and scored ${r.pct}% (${r.band}). ${r.report.summary || ""}`.slice(0, 900);
        return (
          <div className="space-y-4" data-testid="diagnostic-report">
            <Card className="print-plain">
              <div className="flex flex-col sm:flex-row sm:items-center gap-5">
                <ScoreRing value={r.pct} max={100} size={120} label="Score" sub={r.band} />
                <div className="min-w-0 flex-1">
                  <p className="text-[22px] font-extrabold leading-tight">{r.name}</p>
                  <p className="text-[14px] text-bz-muted">{r.company || "Company not given"} · {hdate(r.at)}</p>
                  <div className="flex flex-wrap gap-x-4 gap-y-1 mt-2 text-[14px]">
                    {r.phone && <a href={`tel:${r.phone}`} className="text-bz-gold font-bold min-h-[32px] inline-flex items-center">{r.phone}</a>}
                    {r.email && <a href={`mailto:${r.email}`} className="text-bz-gold font-bold min-h-[32px] inline-flex items-center break-all">{r.email}</a>}
                  </div>
                </div>
              </div>
              {Object.keys(r.score.by_dimension || {}).length > 0 && (
                <div className="mt-5 space-y-2.5">
                  {Object.entries(r.score.by_dimension).map(([k, v]) => (
                    <div key={k}>
                      <div className="flex justify-between text-[13.5px] gap-3"><span>{k}</span><span className="font-extrabold text-bz-gold tabular">{v}%</span></div>
                      <Meter value={v} className="mt-1" label={k} />
                    </div>
                  ))}
                </div>
              )}
            </Card>
            <AiFrame title={r.report.auto ? "Quick read" : "Your report"} className="print-plain">
              {r.report.summary && <p className="text-[16px] font-bold mb-4">{r.report.summary}</p>}
              <div className="grid gap-4 sm:grid-cols-2">
                <div><H>Strengths</H><ul className="list-disc pl-5 space-y-1 text-[15px] marker:text-bz-gold">{r.report.strengths.map((x) => <li key={x}>{x}</li>)}</ul></div>
                <div><H>Gaps</H><ul className="list-disc pl-5 space-y-1 text-[15px] marker:text-bz-gold">{r.report.gaps.map((x) => <li key={x}>{x}</li>)}</ul></div>
              </div>
              <div className="mt-5"><H>Top 3 recommendations</H><div className="space-y-3">{r.report.recommendations.map((x, i) => <Step key={x} n={i + 1} ai title={x} />)}</div></div>
              <div className="mt-5 rounded-bzcard border border-bz-gold bg-bz-gold-tint p-3.5">
                <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-1">The next conversation</p>
                <p className="text-[15px]">{r.report.next_conversation}</p>
              </div>
              {r.report.auto && <Note className="mt-3">The AI was busy when this came in, so this read is worked out from the scores.</Note>}
            </AiFrame>
            <Card inset>
              <Label tone="muted">What they saw after answering</Label>
              <Para text={r.thank_you} className="text-[14.5px]" />
            </Card>
            <Card>
              <Label tone="muted">Their answers</Label>
              <ol className="space-y-2.5 text-[14.5px] list-decimal pl-5 marker:text-bz-gold">
                {r.qa.map((a) => <li key={a.id}><p>{a.text}</p><p className="font-bold mt-0.5">{a.kind === "scale" ? `${a.answer} of 5` : a.answer || "Skipped"}</p></li>)}
              </ol>
            </Card>
            <div className="flex flex-col sm:flex-row gap-2 no-print">
              <Link to={`/app/outreach?name=${encodeURIComponent(r.name)}&company=${encodeURIComponent(r.company || "")}&context=${encodeURIComponent(ctx)}`}
                className="inline-flex items-center justify-center min-h-[52px] px-6 rounded-full border border-bz-rule font-bold text-[15px] hover:border-bz-gold" data-testid="diagnostic-outreach">Draft a reply</Link>
              <Button variant="secondary" onClick={() => window.print()}>Print or save as PDF</Button>
            </div>
          </div>
        );
      }}
    </Loadable>
  );
}

function Editor({ x, onSaved }) {
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  useEffect(() => {
    setF({ title: x.title, intro: x.intro, questions: x.questions.map((q) => ({ ...q })), bands: x.bands.map((b) => ({ label: b.label, meaning: b.meaning })),
      brand_name: x.brand?.name || "", brand_title: x.brand?.title || "", cta: x.cta || "", cta_link: x.cta_link || "" });
  }, [x]);
  if (!f) return null;
  const setQ = (i, k, v) => setF({ ...f, questions: f.questions.map((q, j) => (j === i ? { ...q, [k]: v } : q)) });
  const move = (i, d) => { const qs = [...f.questions]; const j = i + d; if (j < 0 || j >= qs.length) return; [qs[i], qs[j]] = [qs[j], qs[i]]; setF({ ...f, questions: qs }); };
  const save = async (andPublish = false) => {
    setErr(""); setOk(""); setBusy(andPublish ? "publish" : "save");
    try {
      let d = (await api.put(`/diagnostic/${x.id}`, f)).data;
      if (andPublish) d = (await api.post(`/diagnostic/${x.id}/publish`)).data;
      onSaved(d); setOk(andPublish ? "Published. Share the link with prospects." : "Saved.");
    } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };
  return (
    <div className="space-y-4">
      <Card>
        <div className="space-y-3">
          <Field label="Title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={80} data-testid="diagnostic-title" /></Field>
          <Field label="Intro the prospect sees"><Textarea rows={3} value={f.intro} onChange={(e) => setF({ ...f, intro: e.target.value })} maxLength={400} className="min-h-[90px]" /></Field>
        </div>
      </Card>
      <Card>
        <Label>Questions ({f.questions.length})</Label>
        <ol className="space-y-3">
          {f.questions.map((q, i) => (
            <li key={q.id || i} className="rounded-bzcard border border-bz-line bg-bz-panel p-3" data-testid={`diagnostic-q-${i}`}>
              <div className="flex items-center justify-between gap-2 mb-2">
                <span className="text-[13px] font-extrabold text-bz-gold">Question {i + 1}</span>
                <span className="flex gap-1">
                  <button type="button" className="w-10 h-10 grid place-items-center rounded-full hover:bg-bz-raised disabled:opacity-40" onClick={() => move(i, -1)} disabled={i === 0} aria-label="Move up"><ArrowUp className="w-4 h-4" aria-hidden /></button>
                  <button type="button" className="w-10 h-10 grid place-items-center rounded-full hover:bg-bz-raised disabled:opacity-40" onClick={() => move(i, 1)} disabled={i === f.questions.length - 1} aria-label="Move down"><ArrowDown className="w-4 h-4" aria-hidden /></button>
                  <button type="button" className="w-10 h-10 grid place-items-center rounded-full text-bz-miss hover:bg-bz-miss-tint" onClick={() => setF({ ...f, questions: f.questions.filter((_, j) => j !== i) })} aria-label="Remove question"><Trash2 className="w-4 h-4" aria-hidden /></button>
                </span>
              </div>
              <Textarea rows={2} value={q.text} onChange={(e) => setQ(i, "text", e.target.value)} maxLength={240} className="min-h-[72px]" aria-label={`Question ${i + 1}`} />
              <div className="grid grid-cols-2 gap-2 mt-2">
                <Select value={q.kind} onChange={(e) => setQ(i, "kind", e.target.value)} aria-label="Answer type">
                  <option value="scale">1 to 5 scale</option><option value="short">Short answer</option>
                </Select>
                <Input value={q.dimension} onChange={(e) => setQ(i, "dimension", e.target.value)} maxLength={40} placeholder="Area, e.g. Sales" aria-label="Area" />
              </div>
              {q.kind === "scale" && (
                <div className="grid grid-cols-2 gap-2 mt-2">
                  <Input value={q.low || ""} onChange={(e) => setQ(i, "low", e.target.value)} maxLength={30} placeholder="1 means…" aria-label="Label for 1" />
                  <Input value={q.high || ""} onChange={(e) => setQ(i, "high", e.target.value)} maxLength={30} placeholder="5 means…" aria-label="Label for 5" />
                </div>
              )}
            </li>
          ))}
        </ol>
        {f.questions.length < 15 && (
          <Button variant="small" className="mt-3" data-testid="diagnostic-add-q"
            onClick={() => setF({ ...f, questions: [...f.questions, { text: "", kind: "scale", dimension: "General", low: "Not true", high: "Completely true" }] })}>Add a question</Button>
        )}
      </Card>
      <Card>
        <Label>How it's scored</Label>
        <Note>Each 1–5 answer counts from 0 to 100. The score is the average. Short answers aren't scored; they go into your report.</Note>
        <div className="space-y-3 mt-3">
          {f.bands.map((b, i) => (
            <div key={i} className="grid gap-2 sm:grid-cols-[120px_1fr_2fr] sm:items-center">
              <span className="text-[13px] font-extrabold text-bz-gold tabular">{x.bands[i].min}–{x.bands[i].max}</span>
              <Input value={b.label} onChange={(e) => setF({ ...f, bands: f.bands.map((y, j) => (j === i ? { ...y, label: e.target.value } : y)) })} maxLength={40} aria-label={`Band ${i + 1} name`} />
              <Input value={b.meaning} onChange={(e) => setF({ ...f, bands: f.bands.map((y, j) => (j === i ? { ...y, meaning: e.target.value } : y)) })} maxLength={240} aria-label={`Band ${i + 1} meaning`} />
            </div>
          ))}
        </div>
      </Card>
      <Card>
        <Label>Shown with the form and the result</Label>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Your name"><Input value={f.brand_name} onChange={(e) => setF({ ...f, brand_name: e.target.value })} maxLength={80} /></Field>
          <Field label="Your title"><Input value={f.brand_title} onChange={(e) => setF({ ...f, brand_title: e.target.value })} maxLength={120} /></Field>
        </div>
        <Field label="Next step after the result" className="mt-3"><Input value={f.cta} onChange={(e) => setF({ ...f, cta: e.target.value })} maxLength={300} placeholder="e.g. Book a free 20-minute call to go through your result." /></Field>
        <Field label="Booking link (optional)" hint="Starts with https://" className="mt-3"><Input value={f.cta_link} onChange={(e) => setF({ ...f, cta_link: e.target.value })} maxLength={300} placeholder="https://" data-testid="diagnostic-cta-link" /></Field>
      </Card>
      <ErrorLine>{err}</ErrorLine>
      <OkLine>{ok}</OkLine>
      <div className="flex flex-col sm:flex-row gap-2">
        {x.status !== "published" && <Button onClick={() => save(true)} loading={busy === "publish"} disabled={!!busy} data-testid="diagnostic-publish">Save and publish</Button>}
        <Button variant="secondary" onClick={() => save(false)} loading={busy === "save"} disabled={!!busy} data-testid="diagnostic-save">Save changes</Button>
      </div>
    </div>
  );
}

function Detail() {
  const { id } = useParams();
  const [sp, setSp] = useSearchParams();
  const rid = sp.get("r");
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["diagnostic", id], queryFn: async () => (await api.get(`/diagnostic/${id}`)).data });
  const [tab, setTab] = useState(rid ? "answers" : "questions");
  const [busy, setBusy] = useState(false);
  const saved = (d) => { qc.setQueryData(["diagnostic", id], (old) => ({ ...(old || {}), diagnostic: d })); qc.invalidateQueries({ queryKey: ["diagnostics"] }); };
  const unpublish = async () => {
    setBusy(true);
    try { saved((await api.post(`/diagnostic/${id}/unpublish`)).data); } catch { /* ignore */ } finally { setBusy(false); }
  };
  if (rid) {
    return (
      <div className="space-y-4">
        <button type="button" onClick={() => setSp({})} className="no-print inline-flex items-center gap-1.5 text-[13px] font-bold text-bz-gold min-h-[40px]">All answers</button>
        <Report did={id} rid={rid} />
      </div>
    );
  }
  return (
    <div className="space-y-4">
      <BackLink to="/app/diagnostic">All diagnostics</BackLink>
      <Loadable q={q} what="this diagnostic" lines={8}>
        {({ diagnostic: x, responses = [] }) => {
          const url = x.public_path ? `${window.location.origin}${x.public_path}` : "";
          return (
            <div className="space-y-4">
              <Card>
                <div className="flex items-start justify-between gap-3">
                  <p className="text-[20px] font-extrabold leading-tight min-w-0">{x.title}</p>
                  <Chip tone={x.status === "published" ? "gold" : "muted"} className="shrink-0">{x.status === "published" ? "Live" : "Draft"}</Chip>
                </div>
                {url ? (
                  <div className="mt-3">
                    <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3 flex items-center gap-2">
                      <span className="text-[14px] font-bold break-all flex-1 min-w-0" data-testid="diagnostic-link">{url}</span>
                      <CopyButton text={url} label="Copy link" />
                    </div>
                    <div className="flex flex-wrap gap-2 mt-2">
                      <a href={x.public_path} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 min-h-[40px] px-4 rounded-full border border-bz-line bg-bz-raised text-[13px] font-bold">Open the form<ExternalLink className="w-3.5 h-3.5" aria-hidden /></a>
                      <Button variant="small" onClick={unpublish} loading={busy} data-testid="diagnostic-unpublish">Take it offline</Button>
                    </div>
                    <Note className="mt-2">Share this link in your outreach, on LinkedIn or on WhatsApp. Anyone with it can answer; no login.</Note>
                  </div>
                ) : <Note className="mt-2">Check the questions, then publish to get your link.</Note>}
              </Card>
              <Segmented label="View" value={tab} onChange={setTab} testid="diagnostic-tab"
                options={[{ value: "questions", label: "Questions" }, { value: "answers", label: `Answers (${responses.length})` }]} />
              {tab === "questions" ? <Editor x={x} onSaved={saved} /> : responses.length ? (
                <Card>
                  {responses.map((r) => (
                    <RowLink key={r.id} onClick={() => setSp({ r: r.id })} title={r.name} sub={`${r.company || "Company not given"} · ${hdate(r.at)}`}
                      testid={`diagnostic-response-${r.id}`} right={<Chip tone="gold">{r.pct}% · {r.band}</Chip>} />
                  ))}
                </Card>
              ) : <Empty title="No answers yet" sub={url ? "Share your link. Each answer lands here with a report, and in your inbox." : "Publish the diagnostic to start collecting answers."} />}
            </div>
          );
        }}
      </Loadable>
    </div>
  );
}

function Home() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["diagnostics"], queryFn: async () => (await api.get("/diagnostic")).data });
  const [f, setF] = useState({ topic: "", audience: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.diagnostic;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const run = async (e) => {
    e.preventDefault();
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/diagnostic", f);
      qc.setQueryData(["diagnostic", data.id], { diagnostic: data, responses: [] }); qc.invalidateQueries({ queryKey: ["diagnostics"] }); refreshMe();
      nav(`/app/diagnostic/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-4">
      {busy ? <AiFrame title="Client Diagnostic"><Thinking label="Drafting questions for your niche" /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-3">
            <Field label="What should it check? (optional)" hint="Leave empty to use your niche."><Input value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })} maxLength={200} placeholder="e.g. How healthy is your dealer network" data-testid="diagnostic-topic" /></Field>
            <Field label="Who fills it in? (optional)"><Input value={f.audience} onChange={(e) => setF({ ...f, audience: e.target.value })} maxLength={200} placeholder="e.g. Owners of engineering MSMEs" data-testid="diagnostic-audience" /></Field>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="diagnostic-run">Draft my diagnostic</Button>
            <UsageLine usage={usage} what="diagnostics" className="text-center" />
          </form>
        </Card>
      )}
      <Loadable q={list} what="your diagnostics">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your diagnostics</Label>
            {d.items.map((x) => (
              <RowLink key={x.id} to={`/app/diagnostic/${x.id}`} title={x.title} testid={`diagnostic-${x.id}`}
                sub={`${x.responses} answer${x.responses === 1 ? "" : "s"} · ${hdate(x.at)}`}
                right={<Chip tone={x.status === "published" ? "gold" : "muted"}>{x.status === "published" ? "Live" : "Draft"}</Chip>} />
            ))}
          </Card>
        ) : null}
      </Loadable>
    </div>
  );
}

export default function Diagnostic() {
  const { id } = useParams();
  return (
    <div className="space-y-5">
      {!id && <PageHeader kicker="Client Diagnostic" ai title="A short check your prospects take," accent="a report you keep."
        sub="We draft 8 to 12 questions for your niche. You edit them and share a link. Every answer comes back to you with a score, the gaps and the conversation to have next." />}
      <Gate feature="client_diagnostic">{id ? <Detail /> : <Home />}</Gate>
    </div>
  );
}
