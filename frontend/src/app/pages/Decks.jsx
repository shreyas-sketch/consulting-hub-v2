// /app/decks and /app/decks/:id — Presentation Builder: build a client deck from your notes, a case you solved or a
// Meeting Brief. Pick slides, tone, look and format; the deck is made in a few minutes and downloaded from the hub.
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, Presentation } from "lucide-react";
import { API_BASE, api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, LinkButton, Loadable, Meter, Note, PageHeader, RowLink, Segmented, Select, Textarea, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Presentation Builder" ai title="Turn your work into" accent="a client deck."
  sub="Start from your notes, a case you solved or a Meeting Brief. You get a PDF or PowerPoint in a few minutes." />;
const ORIGIN = API_BASE.replace(/\/api$/, "");
const SOURCE_LABEL = { text: "My notes", case: "A case I solved", brief: "A Meeting Brief" };
const STATUS = { pending: ["teal", "Being made"], ready: ["gold", "Ready"], failed: ["miss", "Didn't work"] };

function StatusChip({ s }) {
  const [tone, label] = STATUS[s] || STATUS.pending;
  return <Chip tone={tone}>{label}</Chip>;
}

// ---- one deck: waits while it's being made (the server checks every 5 seconds), then open / download ----------------
function Elapsed({ from }) {
  const [now, setNow] = useState(Date.now());
  useEffect(() => { const t = setInterval(() => setNow(Date.now()), 1000); return () => clearInterval(t); }, []);
  const s = Math.max(0, Math.round((now - new Date(from).getTime()) / 1000));
  return <>{Math.floor(s / 60)}:{String(s % 60).padStart(2, "0")}</>;
}

function DeckView({ id }) {
  const q = useQuery({
    queryKey: ["deck", id], queryFn: async () => (await api.get(`/decks/${id}`)).data,
    refetchInterval: (query) => (query.state.data?.status === "pending" ? 5000 : false),
  });
  const qc = useQueryClient();
  useEffect(() => { if (q.data?.status && q.data.status !== "pending") qc.invalidateQueries({ queryKey: ["decks"] }); }, [q.data?.status, qc]);
  return (
    <div className="space-y-4">
      <BackLink to="/app/decks">All decks</BackLink>
      <Loadable q={q} what="this deck" lines={5}>
        {(d) => (
          <>
            <PageHeader kicker="Presentation Builder" ai title={d.title} sub={`${d.slides} slides · ${SOURCE_LABEL[d.source]} · ${d.format === "pptx" ? "PowerPoint" : "PDF"}`} />
            {d.status === "pending" && (
              <AiFrame title="Making your deck">
                <Thinking label="Writing and designing your slides" />
                <Meter value={Math.min(92, ((Date.now() - new Date(d.created_at).getTime()) / 1800))} tone="teal" label="Progress" />
                <p className="text-[14px] text-bz-muted mt-3">Time so far: <span className="tabular"><Elapsed from={d.created_at} /></span>. It usually takes two to three minutes. You can leave this page; your deck keeps going and waits for you here.</p>
              </AiFrame>
            )}
            {d.status === "ready" && (
              <Card className="border-bz-rule" data-testid="deck-ready">
                <div className="flex items-start gap-3">
                  <span className="w-11 h-11 rounded-full bg-bz-gold-tint text-bz-gold grid place-items-center shrink-0"><Presentation className="w-5 h-5" aria-hidden /></span>
                  <div className="min-w-0">
                    <p className="text-[18px] font-extrabold leading-snug">Your deck is ready.</p>
                    <p className="text-[14px] text-bz-muted mt-0.5">{d.file_name} · made {ago(d.ready_at || d.created_at)}</p>
                  </div>
                </div>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <a href={`${ORIGIN}${d.download_url}`} className="inline-flex items-center justify-center gap-2 rounded-full min-h-[52px] px-6 py-3 bg-bz-gold text-bz-on-accent font-extrabold text-[16px] hover:opacity-90 shadow-goldglow" data-testid="deck-download">
                    <Download className="w-4 h-4" aria-hidden /> Download
                  </a>
                  {d.open_url && (
                    <a href={`${ORIGIN}${d.open_url}`} target="_blank" rel="noopener noreferrer" className="inline-flex items-center justify-center gap-2 rounded-full min-h-[52px] px-6 py-3 border border-bz-rule text-bz-ink font-bold text-[15px] hover:border-bz-gold" data-testid="deck-open">
                      <ExternalLink className="w-4 h-4" aria-hidden /> Open
                    </a>
                  )}
                </div>
                {d.test && <Note className="mt-3">Test mode: this is a sample file, not a real deck.</Note>}
                <Note className="mt-3">Check every number and name before you send it. Change anything you like once it's downloaded.</Note>
              </Card>
            )}
            {d.status === "failed" && (
              <Card inset role="alert">
                <p className="font-bold">This deck didn't work.</p>
                <p className="text-[14px] text-bz-muted mt-1">{d.error}</p>
                <LinkButton to="/app/decks" variant="secondary" className="mt-4">Try again</LinkButton>
              </Card>
            )}
          </>
        )}
      </Loadable>
    </div>
  );
}

// ---- make one --------------------------------------------------------------------------------------------------------
function DeckHome() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const opts = useQuery({ queryKey: ["deck-options"], queryFn: async () => (await api.get("/decks/options")).data, staleTime: Infinity });
  const src = useQuery({ queryKey: ["deck-sources"], queryFn: async () => (await api.get("/decks/sources")).data });
  const list = useQuery({ queryKey: ["decks"], queryFn: async () => (await api.get("/decks")).data });
  const [f, setF] = useState({ source: "text", id: "", title: "", audience: "", notes: "", slides: 8, tone: "clear", theme: "aurum", format: "pdf" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  const usage = plan?.limits?.presentation;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const answers = src.data?.answers || [];
  const briefs = src.data?.briefs || [];

  const run = async (e) => {
    e.preventDefault();
    if (f.source === "text" && f.title.trim().length < 3) { setErr("Give your deck a title."); return; }
    if (f.source === "text" && f.notes.trim().length < 20) { setErr("Add your notes: a few lines on what the deck should say."); return; }
    if (f.source !== "text" && !f.id) { setErr(f.source === "case" ? "Pick a case you solved." : "Pick a Meeting Brief."); return; }
    setErr(""); setBusy(true);
    try {
      const body = { ...f, id: f.source === "text" ? null : f.id, slides: Number(f.slides) };
      const { data } = await api.post("/decks", body, { timeout: 60000 });
      qc.setQueryData(["deck", data.id], data); qc.invalidateQueries({ queryKey: ["decks"] }); refreshMe();
      nav(`/app/decks/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {HEADER}
      {busy ? <AiFrame title="Presentation Builder"><Thinking label="Starting your deck" /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-5">
            <div>
              <Label tone="muted">Build it from</Label>
              <Segmented label="Build it from" value={f.source} onChange={(v) => { setF((x) => ({ ...x, source: v, id: "" })); setErr(""); }} testid="deck-source"
                options={[{ value: "text", label: "My notes" }, { value: "case", label: "A case I solved" }, { value: "brief", label: "A Meeting Brief" }]} />
            </div>
            {f.source === "text" && (
              <>
                <Field label="Deck title"><Input value={f.title} onChange={(e) => set("title")(e.target.value)} maxLength={120} placeholder="e.g. Cutting wastage at Sharma Fresh Mart" data-testid="deck-title" /></Field>
                <Field label="Who it's for (optional)"><Input value={f.audience} onChange={(e) => set("audience")(e.target.value)} maxLength={160} placeholder="e.g. The owner and the store managers" data-testid="deck-audience" /></Field>
                <Field label="Your notes" hint="Write what the deck should say: the problem, what you found, what you recommend. Put in your own numbers; nothing is made up.">
                  <Textarea value={f.notes} onChange={(e) => set("notes")(e.target.value)} maxLength={6000} className="min-h-[160px]" data-testid="deck-notes" />
                </Field>
              </>
            )}
            {f.source === "case" && (answers.length ? (
              <>
                <Field label="Your case answer" hint="The deck uses the case, your answer and the model answer.">
                  <Select value={f.id} onChange={(e) => set("id")(e.target.value)} data-testid="deck-pick">
                    <option value="">Pick a case</option>
                    {answers.map((a) => <option key={a.id} value={a.id}>{a.company}: {a.title} · {a.overall}/10 · {hdate(a.at)}</option>)}
                  </Select>
                </Field>
                <Field label="Who it's for (optional)"><Input value={f.audience} onChange={(e) => set("audience")(e.target.value)} maxLength={160} placeholder="The company's owner and leadership team" /></Field>
              </>
            ) : <Note>Solve a case first, then turn your answer into a deck. <Link to="/app/cases" className="text-bz-gold font-bold">Go to cases</Link></Note>)}
            {f.source === "brief" && (briefs.length ? (
              <>
                <Field label="Your Meeting Brief" hint="A short deck for your first meeting with this company.">
                  <Select value={f.id} onChange={(e) => set("id")(e.target.value)} data-testid="deck-pick">
                    <option value="">Pick a brief</option>
                    {briefs.map((b) => <option key={b.id} value={b.id}>{b.company} · {hdate(b.at)}</option>)}
                  </Select>
                </Field>
                <Field label="Who it's for (optional)"><Input value={f.audience} onChange={(e) => set("audience")(e.target.value)} maxLength={160} placeholder="e.g. Head of Operations" /></Field>
              </>
            ) : <Note>Make a Meeting Brief first. <Link to="/app/brief" className="text-bz-gold font-bold">Go to Meeting Brief</Link></Note>)}

            <Loadable q={opts} what="the deck options" lines={2}>
              {(o) => (
                <div className="space-y-4">
                  <Field label="Number of slides">
                    <Select value={f.slides} onChange={(e) => set("slides")(Number(e.target.value))} data-testid="deck-slides">
                      {Array.from({ length: (o.slides?.max || 12) - (o.slides?.min || 6) + 1 }, (_, i) => (o.slides?.min || 6) + i).map((n) => <option key={n} value={n}>{n} slides</option>)}
                    </Select>
                  </Field>
                  <div>
                    <Label tone="muted">Tone</Label>
                    <Segmented label="Tone" value={f.tone} onChange={set("tone")} testid="deck-tone" options={(o.tones || []).map((t) => ({ value: t.key, label: t.label }))} />
                  </div>
                  <div>
                    <Label tone="muted">Look</Label>
                    <Segmented label="Look" value={f.theme} onChange={set("theme")} testid="deck-theme" options={(o.themes || []).map((t) => ({ value: t.key, label: t.name }))} />
                    <Note className="mt-1.5">{(o.themes || []).find((t) => t.key === f.theme)?.note}</Note>
                  </div>
                  <div>
                    <Label tone="muted">File</Label>
                    <Segmented label="File" value={f.format} onChange={set("format")} testid="deck-format" options={(o.formats || []).map((t) => ({ value: t.key, label: t.label }))} />
                  </div>
                </div>
              )}
            </Loadable>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="deck-run">Make my deck</Button>
            <UsageLine usage={usage} what="decks" className="text-center" />
          </form>
        </Card>
      )}
      <Loadable q={list} what="your decks">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your decks</Label>
            {d.items.map((x) => <RowLink key={x.id} to={`/app/decks/${x.id}`} title={x.title} sub={`${x.slides} slides · ${x.format === "pptx" ? "PowerPoint" : "PDF"} · ${hdate(x.created_at)}`} testid={`deck-${x.id}`} right={<StatusChip s={x.status} />} />)}
          </Card>
        ) : <Empty icon={Presentation} title="No decks yet" sub="Your first deck takes a few minutes." />}
      </Loadable>
    </div>
  );
}

export default function Decks() {
  const { id } = useParams();
  return <Gate feature="presentation" header={HEADER}>{id ? <DeckView id={id} /> : <DeckHome />}</Gate>;
}
