// /app/docs and /app/docs/:id — Doc Reader: upload a PDF, Word or text file, ask questions, and see the exact lines
// each answer came from. /:id opens one document with its summary. Only the text is kept, never the file.
// Dropzone and CitedAnswer are shared with the Research Notebook page.
import { useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { FileText, Printer, Trash2, Upload } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Label, Loadable, Meter, Note, OkLine, PageHeader, Textarea, Thinking } from "../components/ui";

export const ACCEPT = ".pdf,.docx,.txt,.md,.markdown";
const EXTS = ["pdf", "docx", "txt", "md", "markdown"];
const MAX_MB = 10;
const KIND = { pdf: "PDF", docx: "Word", txt: "Text", md: "Text" };
export const num = (v) => Number(v || 0).toLocaleString("en-IN");

// Check a file before sending it: type and size. Returns a plain sentence, or "" when it's fine.
export function fileProblem(file) {
  const ext = String(file?.name || "").toLowerCase().split(".").pop();
  if (!EXTS.includes(ext)) return ext === "doc" ? "Old .doc files need saving as .docx first." : "Upload a PDF, a Word file (.docx), or a .txt or .md file.";
  if (file.size > MAX_MB * 1024 * 1024) return `That file is bigger than ${MAX_MB} MB. Split it or save a smaller copy.`;
  return "";
}

function size(kb) {
  return kb >= 1024 ? `${(kb / 1024).toFixed(1)} MB` : `${kb} KB`;
}

function docMeta(d) {
  const pages = `${d.pages_estimated ? "about " : ""}${d.pages} page${d.pages === 1 ? "" : "s"}`;
  return `${KIND[d.kind] || "File"} · ${pages} · ${num(d.words)} words · ${size(d.size_kb)}`;
}

// Drag-and-drop area with a "Choose a file" button (phones can't drag).
export function Dropzone({ onFile, busy = false, disabled = false, hint, testid = "docs" }) {
  const input = useRef(null);
  const [over, setOver] = useState(false);
  const pick = (files) => {
    const f = files && files[0];
    if (f && !disabled && !busy) onFile(f);
  };
  return (
    <div
      onDragOver={(e) => { e.preventDefault(); if (!disabled) setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); pick(e.dataTransfer?.files); }}
      className={`rounded-bzcard border-2 border-dashed px-4 py-6 text-center transition-colors ${over ? "border-bz-gold bg-bz-gold-tint" : "border-bz-line bg-bz-panel"} ${disabled ? "opacity-60" : ""}`}
      data-testid={`${testid}-dropzone`}
    >
      <Upload className="w-6 h-6 mx-auto text-bz-gold" strokeWidth={1.75} aria-hidden />
      <p className="font-bold text-[15px] mt-2">{busy ? "Reading your file" : "Drop a file here"}</p>
      {hint && <p className="text-[13px] text-bz-muted mt-1">{hint}</p>}
      <input ref={input} type="file" accept={ACCEPT} className="hidden" tabIndex={-1}
        onChange={(e) => { pick(e.target.files); e.target.value = ""; }} data-testid={`${testid}-file-input`} />
      <Button variant="secondary" className="mt-4" loading={busy} disabled={disabled} onClick={() => input.current?.click()} data-testid={`${testid}-choose`}>
        Choose a file
      </Button>
    </div>
  );
}

// ---- answers with clickable citations -------------------------------------------------------------
function Inline({ text, onCite, open }) {
  const parts = String(text).split(/(\[\d{1,2}\]|\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((p, i) => {
    const m = /^\[(\d{1,2})\]$/.exec(p);
    if (m) {
      const k = Number(m[1]);
      const on = open === k;
      return (
        <button key={i} type="button" onClick={() => onCite(k)} aria-pressed={on} aria-label={`Show source ${k}`} data-testid={`cite-${k}`}
          className={`inline-flex items-center justify-center min-w-[24px] h-[24px] px-1 mx-0.5 rounded-full text-[11.5px] font-extrabold align-[1px] border border-bz-teal ${on ? "bg-bz-teal text-bz-on-accent" : "text-bz-teal hover:bg-bz-teal-tint"}`}>
          {k}
        </button>
      );
    }
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={i} className="font-bold">{p.slice(2, -2)}</strong>;
    return <span key={i}>{p}</span>;
  });
}

const LIST_LINE = /^\s*(?:[-*•]|\d+[.)])\s+/;

export function CitedAnswer({ a, testid = "docs-answer" }) {
  const [open, setOpen] = useState(null);
  const cites = a.citations || [];
  const toggle = (k) => setOpen((o) => (o === k ? null : k));
  const shown = cites.find((c) => c.n === open);
  const blocks = String(a.answer || "").split(/\n{2,}/).filter((b) => b.trim());
  return (
    <div data-testid={testid}>
      <div className="text-[15px] leading-relaxed space-y-2.5 break-words">
        {blocks.map((b, i) => {
          const lines = b.split("\n").filter((l) => l.trim());
          if (lines.length && lines.every((l) => LIST_LINE.test(l))) {
            return (
              <ul key={i} className="pl-5 list-disc space-y-1 marker:text-bz-teal">
                {lines.map((l, j) => <li key={j}><Inline text={l.replace(LIST_LINE, "")} onCite={toggle} open={open} /></li>)}
              </ul>
            );
          }
          return <p key={i} className="whitespace-pre-line"><Inline text={b} onCite={toggle} open={open} /></p>;
        })}
      </div>
      {shown && (
        <blockquote className="mt-3 rounded-bzcard border border-bz-line border-l-[3px] border-l-bz-gold bg-bz-panel p-3.5" data-testid={`cite-excerpt-${shown.n}`}>
          <p className="text-[12px] font-semibold text-bz-muted">
            [{shown.n}] {shown.doc_title}{shown.page ? `, page ${shown.page}` : ""}
          </p>
          <p className="text-[14.5px] mt-1.5 leading-relaxed">“{shown.excerpt}”</p>
        </blockquote>
      )}
      {cites.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-2">
          {cites.map((c) => (
            <button key={c.n} type="button" onClick={() => toggle(c.n)} aria-pressed={open === c.n} data-testid={`cite-chip-${c.n}`}
              className={`min-h-[44px] max-w-full px-3 rounded-bzbtn border text-[13px] font-bold text-left truncate ${open === c.n ? "border-bz-gold text-bz-gold" : "border-bz-line text-bz-muted hover:border-bz-line-strong"}`}>
              [{c.n}] {c.doc_title}{c.page ? ` · p. ${c.page}` : ""}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function AnswerCard({ a }) {
  return (
    <AiFrame title="Answer" className="rise-in" right={<span className="text-[12px] text-bz-muted">{ago(a.at)}</span>}>
      <p className="text-[16px] font-bold mb-2.5">{a.question}</p>
      {!a.covered && <Chip tone="muted" className="mb-2">Not in your documents</Chip>}
      <CitedAnswer a={a} />
    </AiFrame>
  );
}

// ---- ask box ----------------------------------------------------------------------------------------
function AskBox({ docIds, disabled, disabledNote, onAnswer, label = "Ask my documents" }) {
  const { plan, refreshMe } = useAuth();
  const [question, setQuestion] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.doc_q;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const ask = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 3) { setErr("Type your question."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/docs/ask", { question: q, doc_ids: docIds || null });
      setQuestion("");
      onAnswer(data);
      refreshMe();
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <Card>
      <form onSubmit={ask} noValidate className="space-y-3">
        <Field label="Your question">
          <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} maxLength={1000} rows={3} className="min-h-[96px]"
            placeholder="e.g. What did they decide about the new depots?" data-testid="docs-question" />
        </Field>
        <ErrorLine>{err}</ErrorLine>
        {disabled && disabledNote ? <Note>{disabledNote}</Note> : null}
        {busy ? <Thinking label="Reading your documents" /> : (
          <Button type="submit" variant="ai" className="w-full" disabled={disabled || !canRun} data-testid="docs-ask">{label}</Button>
        )}
        <UsageLine usage={usage} what="document questions" className="text-center" />
      </form>
    </Card>
  );
}

// ---- list page --------------------------------------------------------------------------------------
function DocsHome() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["docs"], queryFn: async () => (await api.get("/docs/list")).data });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [skip, setSkip] = useState(() => new Set());

  const upload = async (file) => {
    setErr(""); setOk("");
    const problem = fileProblem(file);
    if (problem) { setErr(problem); return; }
    const fd = new FormData();
    fd.append("file", file);
    setBusy(true);
    try {
      const { data } = await api.post("/docs", fd);
      qc.invalidateQueries({ queryKey: ["docs"] });
      setOk(`Added “${data.title}”. Ask it anything below.`);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };

  const remove = async (d) => {
    if (!window.confirm(`Delete “${d.title}”? Its text and summary go too.`)) return;
    setErr(""); setOk("");
    try {
      await api.delete(`/docs/${d.id}`);
      setSkip((s) => { const n = new Set(s); n.delete(d.id); return n; });
      qc.invalidateQueries({ queryKey: ["docs"] });
    } catch (e) { setErr(apiError(e)); }
  };

  const toggle = (id) => setSkip((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });

  return (
    <Loadable q={q} what="your documents" lines={5}>
      {(d) => {
        const items = d.items || [];
        const full = d.count >= d.cap;
        const picked = items.filter((x) => !skip.has(x.id));
        const docIds = skip.size ? picked.map((x) => x.id) : null;
        const onAnswer = (a) => qc.setQueryData(["docs"], (old) => ({ ...(old || {}), questions: [a, ...((old && old.questions) || [])].slice(0, 10) }));
        return (
          <div className="space-y-5">
            <Card>
              <div className="flex items-baseline justify-between gap-3 mb-2">
                <Label className="mb-0">Your documents</Label>
                <span className="text-[13px] text-bz-muted tabular" data-testid="docs-count">{d.count} of {d.cap} kept</span>
              </div>
              <Meter value={d.cap ? (d.count / d.cap) * 100 : 0} label="Documents kept" className="mb-4" />
              {full ? (
                <Note className="mb-1">You can keep {d.cap} documents at a time. Delete one to add another.</Note>
              ) : (
                <Dropzone onFile={upload} busy={busy} hint={`PDF, Word (.docx), .txt or .md · up to ${d.max_mb || MAX_MB} MB. We keep the text only, not your file.`} />
              )}
              <ErrorLine>{err}</ErrorLine>
              <OkLine>{ok}</OkLine>
              {items.length > 0 && (
                <div className="mt-4">
                  {items.map((x) => (
                    <div key={x.id} className="flex items-center gap-1.5 py-2 border-b border-bz-line last:border-0" data-testid={`doc-row-${x.id}`}>
                      <label className="w-11 h-11 grid place-items-center shrink-0 cursor-pointer" title="Use in questions">
                        <input type="checkbox" checked={!skip.has(x.id)} onChange={() => toggle(x.id)} className="w-5 h-5 accent-bz-gold"
                          aria-label={`Use “${x.title}” in questions`} data-testid={`doc-include-${x.id}`} />
                      </label>
                      <Link to={`/app/docs/${x.id}`} className="min-w-0 flex-1 min-h-[48px] flex flex-col justify-center hover:text-bz-gold" data-testid={`doc-open-${x.id}`}>
                        <span className="font-bold text-[15px] truncate">{x.title}</span>
                        <span className="text-[13px] text-bz-muted truncate">{docMeta(x)}</span>
                      </Link>
                      {x.truncated && <Chip tone="muted" className="hidden sm:inline-flex">Long: first part read</Chip>}
                      <button type="button" onClick={() => remove(x)} aria-label={`Delete “${x.title}”`} data-testid={`doc-delete-${x.id}`}
                        className="w-11 h-11 grid place-items-center shrink-0 rounded-full text-bz-muted hover:text-bz-miss hover:bg-bz-miss-tint">
                        <Trash2 className="w-[18px] h-[18px]" aria-hidden />
                      </button>
                    </div>
                  ))}
                  {items.length > 1 && <Note className="mt-2">Ticked documents are used for your questions. Untick one to leave it out.</Note>}
                </div>
              )}
            </Card>

            {items.length === 0 ? (
              <Empty icon={FileText} title="No documents yet" sub="Add a report, a proposal or meeting notes. Then ask it questions in plain words." />
            ) : (
              <AskBox docIds={docIds} disabled={picked.length === 0} disabledNote="Tick at least one document to ask about." onAnswer={onAnswer} />
            )}

            {(d.questions || []).length > 0 && (
              <div className="space-y-4">
                <Label>Your recent questions</Label>
                {d.questions.map((a) => <AnswerCard key={a.id} a={a} />)}
              </div>
            )}
          </div>
        );
      }}
    </Loadable>
  );
}

// ---- one document -----------------------------------------------------------------------------------
function List({ items }) {
  return <ul className="pl-5 list-disc space-y-1.5 marker:text-bz-teal text-[15px] leading-relaxed">{items.map((x) => <li key={x}>{x}</li>)}</ul>;
}

function Head({ children }) {
  return <p className="text-[12px] font-semibold text-bz-teal mt-5 mb-2">{children}</p>;
}

function SummaryBody({ s }) {
  return (
    <AiFrame title="Summary" className="rise-in print-plain" right={<span className="text-[12px] text-bz-muted">{hdate(s.at)}</span>}>
      <div data-testid="doc-summary">
        <p className="text-[15.5px] leading-relaxed">{s.overview}</p>
        <Head>Key points</Head>
        <List items={s.key_points || []} />
        {(s.numbers || []).length > 0 && (
          <>
            <Head>Numbers that matter</Head>
            <div className="grid gap-2.5 sm:grid-cols-2">
              {s.numbers.map((x) => (
                <div key={x.figure + x.meaning} className="rounded-bzcard border border-bz-line bg-bz-panel px-3.5 py-3 min-w-0">
                  <p className="text-[20px] font-extrabold text-bz-gold tabular break-words">{x.figure}</p>
                  <p className="text-[13.5px] text-bz-muted mt-0.5">{x.meaning}</p>
                </div>
              ))}
            </div>
          </>
        )}
        {(s.decisions || []).length > 0 && <><Head>Decisions</Head><List items={s.decisions} /></>}
        {(s.risks || []).length > 0 && <><Head>Risks and open issues</Head><List items={s.risks} /></>}
      </div>
    </AiFrame>
  );
}

function DocView({ id }) {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["doc", id], queryFn: async () => (await api.get(`/docs/${id}`)).data });
  const [answers, setAnswers] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.doc_q;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const summarise = async () => {
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post(`/docs/${id}/summary`, {});
      qc.setQueryData(["doc", id], (old) => ({ ...(old || {}), summary: data.summary, has_summary: true }));
      qc.invalidateQueries({ queryKey: ["docs"] });
      if (!data.cached) refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  const remove = async (d) => {
    if (!window.confirm(`Delete “${d.title}”? Its text and summary go too.`)) return;
    try { await api.delete(`/docs/${id}`); qc.invalidateQueries({ queryKey: ["docs"] }); nav("/app/docs"); } catch (e) { setErr(apiError(e)); }
  };

  return (
    <div className="space-y-5">
      <BackLink to="/app/docs">All documents</BackLink>
      <Loadable q={q} what="this document" lines={6}>
        {(d) => (
          <div className="space-y-5">
            <Card>
              <Label>Document</Label>
              <h1 className="font-display text-[24px] sm:text-[30px] font-[450] leading-tight tracking-[-0.01em] break-words">{d.title}</h1>
              <p className="text-[13px] text-bz-muted mt-1.5">{docMeta(d)} · added {hdate(d.at)}</p>
              {d.truncated && <Note className="mt-2">This document is very long. We read the first part of it.</Note>}
              {d.preview && <p className="text-[14px] text-bz-muted mt-3 leading-relaxed line-clamp-4">Starts: “{d.preview}…”</p>}
              <div className="mt-4 flex flex-wrap gap-2 no-print">
                {d.summary && <Button variant="small" onClick={() => window.print()}><Printer className="w-4 h-4" aria-hidden />Print or PDF</Button>}
                <Button variant="small" className="text-bz-miss" onClick={() => remove(d)} data-testid="doc-delete">Delete this document</Button>
              </div>
            </Card>

            {d.summary ? <SummaryBody s={d.summary} /> : busy ? (
              <AiFrame title="Summary"><Thinking label="Reading the whole document" /></AiFrame>
            ) : (
              <Card className="no-print">
                <p className="font-bold text-[16px]">Get the short version</p>
                <p className="text-[14px] text-bz-muted mt-1">Key points, the numbers that matter, decisions and risks. Counts as one document question.</p>
                <ErrorLine>{err}</ErrorLine>
                <Button variant="ai" className="w-full mt-3" onClick={summarise} disabled={!canRun} data-testid="doc-summary-run">Summarise this document</Button>
              </Card>
            )}

            <div className="no-print space-y-4">
              <AskBox docIds={[id]} onAnswer={(a) => setAnswers((x) => [a, ...x])} label="Ask this document" />
              {answers.map((a) => <AnswerCard key={a.id} a={a} />)}
            </div>
          </div>
        )}
      </Loadable>
    </div>
  );
}

export default function Docs() {
  const { id } = useParams();
  const header = (
    <PageHeader kicker="Doc Reader" ai title="Ask your documents" accent="anything."
      sub="Upload a report, a proposal or meeting notes. Ask questions in plain words and see the exact lines each answer comes from." />
  );
  return (
    <Gate feature="doc_reader" header={header}>
      {id ? <DocView id={id} /> : <div className="space-y-5">{header}<DocsHome /></div>}
    </Gate>
  );
}
