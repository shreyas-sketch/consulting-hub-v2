// /app/research and /app/research/:id — Research Notebook (L1): projects of sources (files, pasted text, web pages,
// Doc Reader documents). Each project has three areas — Sources · Chat · Notes — as tabs on a phone and three columns
// on a desktop. Chat answers cite the sources; Notes holds the member's notes, saved answers, generated outputs
// (briefing, FAQ, study guide, timeline) and the audio overview.
import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, ChevronRight, FileText, Globe, NotebookPen, Plus, Printer, Sparkles, Trash2, Type } from "lucide-react";
import { API_BASE, api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import Markdown, { CopyButton } from "../components/Markdown";
import {
  AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Note, OkLine, PageHeader, RowLink, Segmented, Select,
  Textarea, Thinking,
} from "../components/ui";
import { CitedAnswer, Dropzone, fileProblem, num } from "./Docs";

const SOURCE_KIND = { file: { label: "File", icon: FileText }, text: { label: "Pasted text", icon: Type }, url: { label: "Web page", icon: Globe }, doc: { label: "From Doc Reader", icon: BookOpen } };
const NOTE_KIND = { note: "Your note", answer: "Saved answer", briefing: "Briefing", faq: "FAQ", study: "Study guide", timeline: "Timeline" };
const GENERATE = [
  { kind: "briefing", label: "Briefing", what: "One page on what matters most", busy: "Writing your briefing" },
  { kind: "faq", label: "FAQ", what: "The questions a client would ask, answered", busy: "Writing your FAQ" },
  { kind: "study", label: "Study guide", what: "Key ideas and terms to learn", busy: "Writing your study guide" },
  { kind: "timeline", label: "Timeline", what: "The dates in your sources, in order", busy: "Putting the dates in order" },
];
const AI_KINDS = new Set(["briefing", "faq", "study", "timeline", "answer"]);
const blobSrc = (u) => (u ? `${API_BASE}${String(u).replace(/^\/api/, "")}` : "");
const gateOrError = (e, setErr) => { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); };
const canUse = (u) => !u || u.limit == null || u.used < u.limit;

function header(sub) {
  return (
    <PageHeader kicker="Research Notebook" ai title="Your sources," accent="your answers." sub={sub} />
  );
}

// ---- project list -----------------------------------------------------------------------------------
function Projects() {
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["notebook"], queryFn: async () => (await api.get("/notebook")).data });
  const [f, setF] = useState({ title: "", description: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");

  const create = async (e) => {
    e.preventDefault();
    if (f.title.trim().length < 2) { setErr("Give the project a name."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/notebook", { title: f.title.trim(), description: f.description.trim() });
      qc.invalidateQueries({ queryKey: ["notebook"] });
      nav(`/app/research/${data.id}`);
    } catch (e2) { gateOrError(e2, setErr); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {header("Put the reports, articles and notes on one topic in a project. Ask questions with answers that point to the source, make a briefing or an FAQ, or listen to a short overview.")}
      <Loadable q={q} what="your projects" lines={4}>
        {(d) => {
          const full = d.count >= d.cap;
          return (
            <>
              <Card>
                <div className="flex items-baseline justify-between gap-3">
                  <Label className="mb-0">Start a project</Label>
                  <span className="text-[13px] text-bz-muted tabular" data-testid="nb-count">{d.count} of {d.cap} projects</span>
                </div>
                {full ? (
                  <Note className="mt-3">You can keep {d.cap} projects at a time. Delete one to start another.</Note>
                ) : (
                  <form onSubmit={create} noValidate className="space-y-3 mt-3">
                    <Field label="What is it about">
                      <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={120} placeholder="e.g. Cold chain in western India" data-testid="nb-title" />
                    </Field>
                    <Field label="Why you need it (optional)">
                      <Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} maxLength={600} placeholder="e.g. Prep for my pitch to a food processor" data-testid="nb-description" />
                    </Field>
                    <ErrorLine>{err}</ErrorLine>
                    <Button type="submit" className="w-full" loading={busy} data-testid="nb-create">Start the project</Button>
                  </form>
                )}
              </Card>
              {(d.items || []).length ? (
                <Card>
                  <Label>Your projects</Label>
                  {d.items.map((p) => (
                    <RowLink key={p.id} to={`/app/research/${p.id}`} icon={NotebookPen} title={p.title} testid={`nb-project-${p.id}`}
                      sub={`${p.sources} source${p.sources === 1 ? "" : "s"} · ${p.notes} note${p.notes === 1 ? "" : "s"} · ${ago(p.updated_at)}`} />
                  ))}
                </Card>
              ) : (
                <Empty icon={NotebookPen} title="No projects yet" sub="Start one for each topic you're researching: an industry, a client, a problem." />
              )}
            </>
          );
        }}
      </Loadable>
    </div>
  );
}

// ---- sources ----------------------------------------------------------------------------------------
function AddSource({ id, refresh, startOpen }) {
  const [open, setOpen] = useState(startOpen);
  const [kind, setKind] = useState("file");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [t, setT] = useState({ title: "", text: "" });
  const [url, setUrl] = useState("");
  const [docId, setDocId] = useState("");
  const docs = useQuery({ queryKey: ["docs"], queryFn: async () => (await api.get("/docs/list")).data, enabled: kind === "doc" });

  const send = async (fn, done) => {
    setErr(""); setOk(""); setBusy(true);
    try {
      const { data } = await fn();
      setOk(`Added “${data.title}”.`);
      done?.();
      refresh();
    } catch (e) { gateOrError(e, setErr); } finally { setBusy(false); }
  };
  const addFile = (file) => {
    const p = fileProblem(file);
    if (p) { setErr(p); setOk(""); return; }
    const fd = new FormData();
    fd.append("file", file);
    send(() => api.post(`/notebook/${id}/sources/file`, fd));
  };
  const addText = (e) => {
    e.preventDefault();
    if (t.text.trim().length < 20) { setErr("Paste a bit more text (at least a few sentences)."); return; }
    send(() => api.post(`/notebook/${id}/sources/text`, { title: t.title.trim(), text: t.text }), () => setT({ title: "", text: "" }));
  };
  const addUrl = (e) => {
    e.preventDefault();
    if (url.trim().length < 8) { setErr("Paste the full link to the page."); return; }
    send(() => api.post(`/notebook/${id}/sources/url`, { url: url.trim() }), () => setUrl(""));
  };
  const addDoc = (e) => {
    e.preventDefault();
    if (!docId) { setErr("Pick one of your documents."); return; }
    send(() => api.post(`/notebook/${id}/sources/doc`, { doc_id: docId }), () => setDocId(""));
  };

  if (!open) {
    return (
      <div className="mt-3">
        <Button variant="secondary" className="w-full" onClick={() => setOpen(true)} data-testid="nb-source-new"><Plus className="w-4 h-4" aria-hidden />Add a source</Button>
        <OkLine>{ok}</OkLine>
      </div>
    );
  }
  return (
    <div className="mt-4 pt-4 border-t border-bz-line">
      <div className="flex items-center justify-between gap-2 mb-2">
        <p className="text-[13px] font-semibold">Add a source</p>
        <button type="button" onClick={() => { setOpen(false); setErr(""); }} className="text-[13px] font-bold text-bz-muted min-h-[36px] px-1">Close</button>
      </div>
      <Segmented value={kind} onChange={(v) => { setKind(v); setErr(""); setOk(""); }} label="Kind of source" testid="nb-source-kind"
        options={[{ value: "file", label: "File" }, { value: "text", label: "Text" }, { value: "url", label: "Web page" }, { value: "doc", label: "My docs" }]} />
      <div className="mt-3">
        {kind === "file" && <Dropzone onFile={addFile} busy={busy} testid="nb" hint="PDF, Word (.docx), .txt or .md · up to 10 MB. We keep the text only." />}
        {kind === "text" && (
          <form onSubmit={addText} noValidate className="space-y-3">
            <Field label="Name (optional)"><Input value={t.title} onChange={(e) => setT({ ...t, title: e.target.value })} maxLength={120} placeholder="e.g. Notes from the plant visit" data-testid="nb-text-title" /></Field>
            <Field label="Text"><Textarea value={t.text} onChange={(e) => setT({ ...t, text: e.target.value })} maxLength={200000} placeholder="Paste an article, an email or your notes" data-testid="nb-text-body" /></Field>
            <Button type="submit" variant="secondary" className="w-full" loading={busy} data-testid="nb-text-add">Add this text</Button>
          </form>
        )}
        {kind === "url" && (
          <form onSubmit={addUrl} noValidate className="space-y-3">
            <Field label="Link to the page" hint="We read the page's text once. Some sites block this; then paste the text instead.">
              <Input type="url" inputMode="url" value={url} onChange={(e) => setUrl(e.target.value)} maxLength={500} placeholder="https://" data-testid="nb-url" />
            </Field>
            <Button type="submit" variant="secondary" className="w-full" loading={busy} data-testid="nb-url-add">Add this page</Button>
          </form>
        )}
        {kind === "doc" && (
          docs.isLoading ? <Note>Loading your documents</Note> : (docs.data?.items || []).length ? (
            <form onSubmit={addDoc} noValidate className="space-y-3">
              <Field label="Your Doc Reader documents">
                <Select value={docId} onChange={(e) => setDocId(e.target.value)} data-testid="nb-doc-select">
                  <option value="">Pick a document</option>
                  {docs.data.items.map((x) => <option key={x.id} value={x.id}>{x.title}</option>)}
                </Select>
              </Field>
              <Button type="submit" variant="secondary" className="w-full" loading={busy} data-testid="nb-doc-add">Add this document</Button>
            </form>
          ) : <Note>No documents yet. Upload them in <Link to="/app/docs" className="text-bz-gold font-bold">Doc Reader</Link>, or add a file here.</Note>
        )}
      </div>
      <ErrorLine>{err}</ErrorLine>
      <OkLine>{ok}</OkLine>
    </div>
  );
}

function SourcesPane({ d, id, refresh }) {
  const [err, setErr] = useState("");
  const remove = async (s) => {
    if (!window.confirm(`Remove “${s.title}” from this project?`)) return;
    setErr("");
    try { await api.delete(`/notebook/${id}/sources/${s.id}`); refresh(); } catch (e) { setErr(apiError(e)); }
  };
  const full = d.sources.length >= d.max_sources;
  return (
    <Card>
      <div className="flex items-baseline justify-between gap-3 mb-1">
        <Label className="mb-0">Sources</Label>
        <span className="text-[13px] text-bz-muted tabular" data-testid="nb-source-count">{d.sources.length} of {d.max_sources}</span>
      </div>
      {d.sources.length === 0 && <Note className="mt-2">Add the reports, articles and notes this project is about. Answers come only from these.</Note>}
      <div className="mt-1">
        {d.sources.map((s) => {
          const K = SOURCE_KIND[s.kind] || SOURCE_KIND.text;
          const Icon = K.icon;
          return (
            <div key={s.id} className="flex items-center gap-2.5 py-2.5 border-b border-bz-line last:border-0" data-testid={`nb-source-${s.id}`}>
              <Icon className="w-5 h-5 text-bz-gold shrink-0" strokeWidth={1.75} aria-hidden />
              <div className="min-w-0 flex-1">
                {s.url ? (
                  <a href={s.url} target="_blank" rel="noopener noreferrer" className="block font-bold text-[14.5px] truncate hover:text-bz-gold">{s.title}</a>
                ) : <p className="font-bold text-[14.5px] truncate">{s.title}</p>}
                <p className="text-[12.5px] text-bz-muted truncate">{K.label} · {num(s.words)} words{s.pages && s.kind !== "text" && s.kind !== "url" ? ` · ${s.pages} page${s.pages === 1 ? "" : "s"}` : ""}</p>
              </div>
              {s.test && <Chip tone="muted">Test mode</Chip>}
              <button type="button" onClick={() => remove(s)} aria-label={`Remove “${s.title}”`} data-testid={`nb-source-remove-${s.id}`}
                className="w-11 h-11 grid place-items-center shrink-0 rounded-full text-bz-muted hover:text-bz-miss hover:bg-bz-miss-tint">
                <Trash2 className="w-[18px] h-[18px]" aria-hidden />
              </button>
            </div>
          );
        })}
      </div>
      <ErrorLine>{err}</ErrorLine>
      {full ? <Note className="mt-3">This project holds {d.max_sources} sources, the most it can. Remove one to add another.</Note> : <AddSource id={id} refresh={refresh} startOpen={d.sources.length === 0} />}
    </Card>
  );
}

// ---- chat -------------------------------------------------------------------------------------------
function answerAsNote(m) {
  const refs = (m.citations || []).map((c) => `- [${c.n}] ${c.doc_title}${c.page ? `, page ${c.page}` : ""}: “${c.excerpt}”`).join("\n");
  return `${m.answer}${refs ? `\n\n**Sources**\n${refs}` : ""}`.slice(0, 20000);
}

function Message({ m, id, refresh }) {
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try {
      await api.post(`/notebook/${id}/notes`, { title: m.question.slice(0, 120), body: answerAsNote(m), kind: "answer" });
      setSaved(true);
      refresh();
    } catch { /* the note is optional */ } finally { setBusy(false); }
  };
  return (
    <div className="space-y-2">
      <div className="ml-auto max-w-[88%] w-fit rounded-bzcard bg-bz-raised border border-bz-line px-3.5 py-2.5 text-[15px]">{m.question}</div>
      <div className="border-l-[3px] border-bz-teal pl-3.5">
        <div className="flex items-center justify-between gap-2 mb-1.5">
          <span className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-bz-teal"><Sparkles className="w-3.5 h-3.5" aria-hidden />Answer</span>
          <span className="text-[12px] text-bz-muted">{ago(m.at)}</span>
        </div>
        {!m.covered && <Chip tone="muted" className="mb-2">Not in your sources</Chip>}
        <CitedAnswer a={m} testid="nb-answer" />
        {m.covered && (
          <div className="mt-2 flex justify-end">
            <Button variant="small" onClick={save} loading={busy} disabled={saved} data-testid="nb-save-answer">{saved ? "Saved to notes" : "Save to notes"}</Button>
          </div>
        )}
      </div>
    </div>
  );
}

function ChatPane({ d, id, refresh }) {
  const { plan, refreshMe } = useAuth();
  const [question, setQuestion] = useState("");
  const [pending, setPending] = useState("");
  const [err, setErr] = useState("");
  const usage = plan?.limits?.doc_q;
  const none = d.sources.length === 0;
  const ask = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (q.length < 3) { setErr("Type your question."); return; }
    setErr(""); setPending(q); setQuestion("");
    try {
      await api.post(`/notebook/${id}/ask`, { question: q });
      refreshMe();
      await refresh();
    } catch (e2) { setQuestion(q); gateOrError(e2, setErr); } finally { setPending(""); }
  };
  return (
    <Card>
      <Label tone="teal">Ask your sources</Label>
      {none && <Note>Add a source first. Then ask anything about it.</Note>}
      {!none && d.messages.length === 0 && !pending && <Note>Answers come only from this project's sources, with numbers you can tap to see the exact lines.</Note>}
      <div className="space-y-6 mt-2">
        {d.messages.map((m) => <Message key={m.id} m={m} id={id} refresh={refresh} />)}
        {pending && (
          <div className="space-y-2">
            <div className="ml-auto max-w-[88%] w-fit rounded-bzcard bg-bz-raised border border-bz-line px-3.5 py-2.5 text-[15px]">{pending}</div>
            <Thinking label="Reading your sources" />
          </div>
        )}
      </div>
      <form onSubmit={ask} noValidate className="space-y-3 mt-4 pt-4 border-t border-bz-line">
        <Textarea value={question} onChange={(e) => setQuestion(e.target.value)} rows={2} maxLength={1000} className="min-h-[72px]" aria-label="Your question"
          placeholder="Ask a question, e.g. What are the biggest costs for small processors?" disabled={none} data-testid="nb-question" />
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" variant="ai" className="w-full" disabled={none || !!pending || !canUse(usage)} data-testid="nb-ask">Ask my sources</Button>
        <UsageLine usage={usage} what="document questions" className="text-center" />
      </form>
    </Card>
  );
}

// ---- notes and outputs ------------------------------------------------------------------------------
function NoteCard({ n, id, refresh }) {
  const [open, setOpen] = useState(false);
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const ai = AI_KINDS.has(n.kind);
  const save = async () => {
    if (!edit.title.trim() || !edit.body.trim()) { setErr("A note needs a title and some text."); return; }
    try { await api.patch(`/notebook/${id}/notes/${n.id}`, { title: edit.title.trim(), body: edit.body }); setEdit(null); setErr(""); refresh(); } catch (e) { setErr(apiError(e)); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete “${n.title}”?`)) return;
    try { await api.delete(`/notebook/${id}/notes/${n.id}`); refresh(); } catch (e) { setErr(apiError(e)); }
  };
  const body = edit ? (
    <div className="space-y-3 mt-3">
      <Input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} maxLength={120} aria-label="Note title" />
      <Textarea value={edit.body} onChange={(e) => setEdit({ ...edit, body: e.target.value })} maxLength={20000} aria-label="Note text" className="min-h-[200px]" />
      <div className="flex gap-2"><Button variant="small" onClick={save}>Save changes</Button><Button variant="small" onClick={() => setEdit(null)}>Cancel</Button></div>
    </div>
  ) : open ? (
    <div className="mt-2">
      <Markdown text={n.body} />
      <div className="flex flex-wrap items-center gap-2 mt-3 no-print">
        <CopyButton text={n.body} />
        <Button variant="small" onClick={() => setEdit({ title: n.title, body: n.body })}>Edit</Button>
        <Button variant="small" className="text-bz-miss" onClick={remove}>Delete</Button>
      </div>
    </div>
  ) : null;
  const head = (
    <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="w-full text-left min-h-[44px] flex items-start gap-3" data-testid={`nb-note-${n.id}`}>
      <span className="min-w-0 flex-1">
        <span className="block font-bold text-[15px] break-words">{n.title}</span>
        <span className="block text-[12.5px] text-bz-muted mt-0.5">{NOTE_KIND[n.kind] || "Note"} · {hdate(n.updated_at || n.at)}</span>
      </span>
      <Chip tone={open ? "gold" : "muted"}>{open ? "Close" : "Open"}</Chip>
    </button>
  );
  const inner = <>{head}{body}<ErrorLine>{err}</ErrorLine></>;
  return ai
    ? <section className="rounded-bzcard border border-bz-teal/40 bg-bz-card p-3.5 sm:p-4">{inner}</section>
    : <Card inset className="!p-3.5 sm:!p-4">{inner}</Card>;
}

function AudioCard({ d, id, refresh }) {
  const { plan, refreshMe } = useAuth();
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [script, setScript] = useState(false);
  const a = d.audio;
  const usage = plan?.limits?.audio;
  const make = async () => {
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post(`/notebook/${id}/audio`);
      if (!data.cached) refreshMe();
      await refresh();
    } catch (e) { gateOrError(e, setErr); } finally { setBusy(false); }
  };
  return (
    <AiFrame title="Audio overview">
      {a ? (
        <>
          <p className="font-bold text-[15px]">{a.title}</p>
          <p className="text-[12.5px] text-bz-muted mb-2">About {Math.round(a.minutes)} min · made {hdate(a.at)}</p>
          <audio controls preload="none" src={blobSrc(a.url)} className="w-full" data-testid="nb-audio">Your browser can't play this audio.</audio>
          <button type="button" className="text-[13px] font-bold text-bz-teal min-h-[44px]" onClick={() => setScript((s) => !s)}>{script ? "Hide the script" : "Read the script"}</button>
          {script && <p className="text-[14px] leading-relaxed text-bz-muted whitespace-pre-line">{a.script}</p>}
          {!a.fresh && <Note className="mt-2">Your sources changed since this was made.</Note>}
        </>
      ) : <p className="text-[14px] text-bz-muted">A 3 to 5 minute spoken overview of your sources, to listen to on a walk or a drive.</p>}
      <ErrorLine>{err}</ErrorLine>
      {busy ? <Thinking label="Writing and recording your overview" /> : (!a || !a.fresh) && (
        <>
          <Button variant="ai" className="w-full mt-3" onClick={make} disabled={d.sources.length === 0 || !canUse(usage)} data-testid="nb-audio-run">
            {a ? "Make a new audio overview" : "Make an audio overview"}
          </Button>
          <UsageLine usage={usage} what="audio versions" className="text-center mt-2" />
        </>
      )}
    </AiFrame>
  );
}

function NotesPane({ d, id, refresh }) {
  const { plan, refreshMe } = useAuth();
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [f, setF] = useState({ title: "", body: "" });
  const [noteErr, setNoteErr] = useState("");
  const [saving, setSaving] = useState(false);
  const [writing, setWriting] = useState(false);
  const usage = plan?.limits?.doc_q;
  const none = d.sources.length === 0;

  const generate = async (kind) => {
    setErr(""); setBusy(kind);
    try {
      await api.post(`/notebook/${id}/generate`, { kind });
      refreshMe();
      await refresh();
    } catch (e) { gateOrError(e, setErr); } finally { setBusy(""); }
  };
  const addNote = async (e) => {
    e.preventDefault();
    if (!f.title.trim() || !f.body.trim()) { setNoteErr("A note needs a title and some text."); return; }
    setNoteErr(""); setSaving(true);
    try { await api.post(`/notebook/${id}/notes`, { title: f.title.trim(), body: f.body }); setF({ title: "", body: "" }); setWriting(false); refresh(); } catch (e2) { setNoteErr(apiError(e2)); } finally { setSaving(false); }
  };
  const going = GENERATE.find((g) => g.kind === busy);

  return (
    <div className="space-y-4">
      <Card className="no-print">
        <Label tone="teal">Make from your sources</Label>
        {busy ? <Thinking label={going?.busy} /> : (
          <ul className="divide-y divide-bz-line -my-1">
            {GENERATE.map((g) => (
              <li key={g.kind}>
                <button type="button" onClick={() => generate(g.kind)} disabled={none || !canUse(usage)} data-testid={`nb-gen-${g.kind}`}
                  className="w-full min-h-[52px] py-2 flex items-center gap-3 text-left rounded-bzbtn hover:bg-bz-panel disabled:opacity-50 disabled:cursor-not-allowed">
                  <Sparkles className="w-4 h-4 text-bz-teal shrink-0" aria-hidden />
                  <span className="min-w-0 flex-1"><span className="block font-semibold text-[14.5px]">{g.label}</span><span className="block text-[12.5px] text-bz-muted">{g.what}</span></span>
                  <ChevronRight className="w-4 h-4 text-bz-muted shrink-0" aria-hidden />
                </button>
              </li>
            ))}
          </ul>
        )}
        <ErrorLine>{err}</ErrorLine>
        <p className="text-[12px] text-bz-muted mt-2">{none ? "Add a source first." : "Each counts as one document question. It's saved in your notes below."}</p>
      </Card>

      <AudioCard d={d} id={id} refresh={refresh} />

      <Card>
        <div className="flex items-baseline justify-between gap-3 mb-2">
          <Label className="mb-0">Your notes</Label>
          <span className="text-[13px] text-bz-muted tabular">{d.notes.length}</span>
        </div>
        {d.notes.length === 0 && !writing && <p className="text-[14px] text-bz-muted">Saved answers, briefings and your own notes appear here.</p>}
        <div className="space-y-2.5" data-testid="nb-notes">
          {d.notes.map((n) => <NoteCard key={n.id} n={n} id={id} refresh={refresh} />)}
        </div>
        <div className="no-print mt-3">
          {writing ? (
            <form onSubmit={addNote} noValidate className="space-y-3 pt-3 border-t border-bz-line">
              <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={120} placeholder="Title" aria-label="Note title" data-testid="nb-note-title" />
              <Textarea value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} maxLength={20000} placeholder="Your thinking, questions for the client, next steps" aria-label="Note text" data-testid="nb-note-body" />
              <ErrorLine>{noteErr}</ErrorLine>
              <div className="flex gap-2">
                <Button type="submit" variant="secondary" className="flex-1" loading={saving} data-testid="nb-note-save">Save note</Button>
                <Button variant="small" onClick={() => { setWriting(false); setNoteErr(""); }}>Cancel</Button>
              </div>
            </form>
          ) : <Button variant="secondary" className="w-full" onClick={() => setWriting(true)} data-testid="nb-note-new"><Plus className="w-4 h-4" aria-hidden />Write a note</Button>}
        </div>
      </Card>
    </div>
  );
}

// ---- one project ------------------------------------------------------------------------------------
function ProjectHead({ p, id, refresh }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [edit, setEdit] = useState(null);
  const [err, setErr] = useState("");
  const save = async (e) => {
    e.preventDefault();
    if (edit.title.trim().length < 2) { setErr("Give the project a name."); return; }
    try { await api.patch(`/notebook/${id}`, { title: edit.title.trim(), description: edit.description.trim() }); setEdit(null); setErr(""); refresh(); qc.invalidateQueries({ queryKey: ["notebook"] }); } catch (e2) { setErr(apiError(e2)); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete “${p.title}”? Its sources, notes and audio go too.`)) return;
    try { await api.delete(`/notebook/${id}`); qc.invalidateQueries({ queryKey: ["notebook"] }); nav("/app/research"); } catch (e) { setErr(apiError(e)); }
  };
  if (edit) {
    return (
      <Card>
        <form onSubmit={save} noValidate className="space-y-3">
          <Field label="Name"><Input value={edit.title} onChange={(e) => setEdit({ ...edit, title: e.target.value })} maxLength={120} /></Field>
          <Field label="Why you need it"><Input value={edit.description} onChange={(e) => setEdit({ ...edit, description: e.target.value })} maxLength={600} /></Field>
          <ErrorLine>{err}</ErrorLine>
          <div className="flex gap-2"><Button type="submit" variant="small">Save changes</Button><Button variant="small" onClick={() => setEdit(null)}>Cancel</Button></div>
        </form>
      </Card>
    );
  }
  return (
    <header>
      <Label tone="teal">Research Notebook</Label>
      <h1 className="font-display text-[26px] sm:text-[34px] font-[450] leading-[1.08] tracking-[-0.02em] break-words">{p.title}</h1>
      {p.description && <p className="text-[15px] font-light text-bz-muted mt-2">{p.description}</p>}
      <div className="flex flex-wrap gap-2 mt-3 no-print">
        <Button variant="small" onClick={() => setEdit({ title: p.title, description: p.description || "" })} data-testid="nb-rename">Rename</Button>
        <Button variant="small" onClick={() => window.print()}><Printer className="w-4 h-4" aria-hidden />Print</Button>
        <Button variant="small" className="text-bz-miss" onClick={remove} data-testid="nb-delete">Delete project</Button>
      </div>
      <ErrorLine>{err}</ErrorLine>
    </header>
  );
}

function Project({ id }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["nb", id], queryFn: async () => (await api.get(`/notebook/${id}`)).data });
  const [tab, setTab] = useState("sources");
  const refresh = () => qc.invalidateQueries({ queryKey: ["nb", id] });
  // phone: three tabs. Desktop: chat always on the right (it's where the work happens); the left column switches
  // between Sources and Notes & outputs, so there are never three narrow columns side by side.
  const left = tab === "notes" ? "notes" : "sources";
  return (
    <div className="space-y-4">
      <BackLink to="/app/research">All projects</BackLink>
      <Loadable q={q} what="this project" lines={6}>
        {(d) => (
          <div className="space-y-4">
            <ProjectHead p={d.project} id={id} refresh={refresh} />
            <Segmented className="lg:hidden no-print" value={tab} onChange={setTab} label="Project area" testid="nb-tab"
              options={[{ value: "sources", label: `Sources (${d.sources.length})` }, { value: "chat", label: "Chat" }, { value: "notes", label: `Notes (${d.notes.length})` }]} />
            <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.4fr)] items-start">
              <div className={`${tab === "chat" ? "hidden" : ""} lg:block min-w-0 space-y-3`}>
                <Segmented className="hidden lg:flex no-print" value={left} onChange={setTab} label="Show" testid="nb-side"
                  options={[{ value: "sources", label: `Sources (${d.sources.length})` }, { value: "notes", label: `Notes & outputs (${d.notes.length})` }]} />
                <section className={left === "sources" ? "" : "hidden"} aria-label="Sources"><SourcesPane d={d} id={id} refresh={refresh} /></section>
                <section className={left === "notes" ? "" : "hidden"} aria-label="Notes and outputs"><NotesPane d={d} id={id} refresh={refresh} /></section>
              </div>
              <section className={`${tab === "chat" ? "" : "hidden"} lg:block min-w-0`} aria-label="Chat"><ChatPane d={d} id={id} refresh={refresh} /></section>
            </div>
          </div>
        )}
      </Loadable>
    </div>
  );
}

export default function Research() {
  const { id } = useParams();
  return (
    <Gate feature="research" header={header("Collect sources on a topic and get summaries and answers from them.")}>
      {id ? <Project id={id} /> : <Projects />}
    </Gate>
  );
}
