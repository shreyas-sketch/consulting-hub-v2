// /app/stories and /app/stories/:id — Career Story Bank: a story question every week; record a voice note, upload one
// or type it; the AI turns it into a proof story (Situation / What I did / Result / What it proves), a LinkedIn post
// and a pitch line. We keep the text only, never the audio.
import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Mic, Square, Upload } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { Gate, Para, UsageLine } from "../components/common";
import { CopyButton } from "../components/Markdown";
import useRecorder, { clock, mediaDuration } from "../components/useRecorder";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Note, PageHeader, Segmented, Select, Textarea, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Career Story Bank" ai title="One story a week," accent="turned into proof." />;
const MAX_MB = 24;
const MAX_MIN = 10;
const PARTS = [["situation", "Situation"], ["what_i_did", "What I did"], ["result", "Result"], ["what_it_proves", "What it proves"]];

function Capture({ question, onMade }) {
  const { plan, refreshMe } = useAuth();
  const [mode, setMode] = useState("record");
  const [useQ, setUseQ] = useState("week");
  const [text, setText] = useState("");
  const [file, setFile] = useState(null);
  const [fileSecs, setFileSecs] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const fileRef = useRef(null);
  const rec = useRecorder({ video: false, maxSeconds: MAX_MIN * 60 });
  const usage = plan?.limits?.story;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const q = useQ === "week" ? question?.text || "" : "";

  const pick = async (e) => {
    const f = e.target.files?.[0];
    setErr(""); setFile(null); setFileSecs(null);
    if (!f) return;
    if (f.size > MAX_MB * 1024 * 1024) { setErr(`That file is larger than ${MAX_MB} MB. Keep it under ${MAX_MIN} minutes.`); return; }
    const secs = await mediaDuration(f);
    if (secs && secs > MAX_MIN * 60 + 5) { setErr(`Keep your voice note under ${MAX_MIN} minutes.`); return; }
    setFile(f); setFileSecs(secs);
  };

  const send = async (kind) => {
    setErr("");
    try {
      let data;
      if (kind === "text") {
        if (text.trim().length < 80) { setErr("Write a little more: at least a few sentences (80 characters)."); return; }
        setBusy("Writing your story");
        ({ data } = await api.post("/stories/text", { text, question: q }));
      } else {
        const blob = kind === "record" ? rec.blob : file;
        if (!blob) return;
        const fd = new FormData();
        fd.append("file", blob, kind === "record" ? `story.${rec.ext || "webm"}` : file.name);
        fd.append("question", q);
        const secs = kind === "record" ? rec.recordedSeconds : fileSecs;
        if (secs) fd.append("duration_s", String(Math.round(secs)));
        setBusy("Listening to your story");
        ({ data } = await api.post("/stories/voice", fd));
      }
      refreshMe();
      setText(""); setFile(null); setFileSecs(null); rec.reset();
      if (fileRef.current) fileRef.current.value = "";
      onMade(data);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(""); }
  };

  if (busy) return <AiFrame title="Career Story Bank"><Thinking label={busy} /><Note>This takes about a minute.</Note></AiFrame>;
  const recording = rec.status === "recording";
  return (
    <Card>
      <Label>Tell your story</Label>
      <Field label="Which story" className="mb-4">
        <Select value={useQ} onChange={(e) => setUseQ(e.target.value)} data-testid="story-question-pick">
          <option value="week">This week's question</option>
          <option value="own">A story of my own</option>
        </Select>
      </Field>
      <Segmented label="How" value={mode} onChange={(v) => { setMode(v); setErr(""); }} testid="story-mode"
        options={[{ value: "record", label: "Record" }, { value: "upload", label: "Upload" }, { value: "type", label: "Type" }]} />

      {mode === "record" ? (
        <div className="mt-4">
          {!rec.supported ? <Note>This browser can't record. Upload a voice note or type your story instead.</Note> : (
            <>
              <div className="rounded-bzcard border border-bz-line bg-bz-panel p-4 flex items-center gap-4">
                <span className={`w-12 h-12 rounded-full grid place-items-center shrink-0 ${recording ? "bg-bz-miss-tint text-bz-miss" : "bg-bz-gold-tint text-bz-gold"}`}>
                  <Mic className={`w-6 h-6 ${recording ? "animate-pulse" : ""}`} aria-hidden />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-[24px] font-extrabold tabular" data-testid="story-timer">{clock(rec.seconds)}<span className="text-[14px] text-bz-muted font-bold"> / {MAX_MIN}:00</span></p>
                  <p className="text-[13px] text-bz-muted">{recording ? "Recording. Speak as if you're telling a friend." : rec.status === "done" ? "Listen back, then turn it into your story." : "Two to five minutes is plenty."}</p>
                </div>
              </div>
              {rec.url ? <audio controls src={rec.url} className="w-full mt-3" data-testid="story-playback" /> : null}
              <div className="mt-3 flex flex-col sm:flex-row gap-3">
                {recording ? (
                  <Button variant="danger" onClick={rec.stop} data-testid="story-record-stop"><Square className="w-4 h-4" aria-hidden />Stop</Button>
                ) : rec.status === "done" ? (
                  <>
                    <Button variant="ai" onClick={() => send("record")} disabled={!canRun} data-testid="story-make">Turn it into my story</Button>
                    <Button variant="secondary" onClick={rec.reset}>Record again</Button>
                  </>
                ) : (
                  <Button onClick={rec.start} loading={rec.status === "asking"} data-testid="story-record-start"><Mic className="w-4 h-4" aria-hidden />Start recording</Button>
                )}
              </div>
              <ErrorLine>{rec.error}</ErrorLine>
            </>
          )}
        </div>
      ) : null}

      {mode === "upload" ? (
        <div className="mt-4 space-y-3">
          <label className="flex items-center gap-3 rounded-bzcard border border-dashed border-bz-line-strong bg-bz-panel p-4 min-h-[64px] cursor-pointer hover:border-bz-gold">
            <Upload className="w-5 h-5 text-bz-gold shrink-0" aria-hidden />
            <span className="min-w-0">
              <span className="block text-[15px] font-bold truncate">{file ? file.name : "Choose a voice note"}</span>
              <span className="block text-[13px] text-bz-muted">webm, ogg, m4a, mp3 or wav · up to {MAX_MIN} min · {MAX_MB} MB</span>
            </span>
            <input ref={fileRef} type="file" accept="audio/*,.webm,.ogg,.m4a,.mp3,.wav" className="sr-only" onChange={pick} data-testid="story-file" />
          </label>
          <Button variant="ai" className="w-full" onClick={() => send("upload")} disabled={!file || !canRun} data-testid="story-make-upload">Turn it into my story</Button>
        </div>
      ) : null}

      {mode === "type" ? (
        <div className="mt-4 space-y-3">
          <Textarea rows={8} value={text} onChange={(e) => setText(e.target.value)} maxLength={8000} data-testid="story-text"
            placeholder="What was the problem? What did you do? What changed, in numbers if you have them?" />
          <div className="flex justify-between text-[12px] text-bz-muted"><span>{text.trim().length < 80 ? "At least 80 characters" : " "}</span><span className="tabular">{text.length}/8000</span></div>
          <Button variant="ai" className="w-full" onClick={() => send("text")} disabled={!canRun} data-testid="story-make-text">Turn it into my story</Button>
        </div>
      ) : null}

      <ErrorLine>{err}</ErrorLine>
      <UsageLine usage={usage} what="stories" className="mt-3 text-center" />
      <Note className="mt-1 text-center">We keep the words, never the recording.</Note>
    </Card>
  );
}

function EditStory({ s, onDone }) {
  const [f, setF] = useState({ ...s, numbers: (s.numbers || []).join("\n") });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  const save = async () => {
    if (!f.title.trim() || !f.situation.trim() || !f.what_i_did.trim() || !f.result.trim()) { setErr("Keep a title, the situation, what you did and the result."); return; }
    setBusy(true); setErr("");
    try {
      const body = { title: f.title, situation: f.situation, what_i_did: f.what_i_did, result: f.result, what_it_proves: f.what_it_proves || "",
        numbers: String(f.numbers || "").split("\n").map((x) => x.trim()).filter(Boolean), linkedin_post: f.linkedin_post || "", pitch_line: f.pitch_line || "" };
      const { data } = await api.put(`/stories/${s.id}`, body);
      onDone(data);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-3 mt-4" data-testid="story-edit-form">
      <Field label="Title"><Input value={f.title} onChange={set("title")} maxLength={80} /></Field>
      {PARTS.map(([k, l]) => <Field key={k} label={l}><Textarea rows={3} value={f[k] || ""} onChange={set(k)} maxLength={1000} /></Field>)}
      <Field label="Numbers" hint="One per line. Only numbers you can stand behind."><Textarea rows={3} value={f.numbers} onChange={set("numbers")} /></Field>
      <Field label="Pitch line"><Input value={f.pitch_line || ""} onChange={set("pitch_line")} maxLength={300} /></Field>
      <Field label="LinkedIn post"><Textarea rows={8} value={f.linkedin_post || ""} onChange={set("linkedin_post")} maxLength={3000} /></Field>
      <ErrorLine>{err}</ErrorLine>
      <div className="flex flex-col sm:flex-row gap-3">
        <Button onClick={save} loading={busy} data-testid="story-save">Save my story</Button>
        <Button variant="secondary" onClick={() => onDone(null)}>Cancel</Button>
      </div>
    </div>
  );
}

function StoryCard({ s, open, onToggle, onChanged, onDeleted }) {
  const [editing, setEditing] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [err, setErr] = useState("");
  const ref = useRef(null);
  useEffect(() => { if (open && ref.current?.scrollIntoView) ref.current.scrollIntoView({ block: "nearest" }); }, [open]);
  const remove = async () => {
    try { await api.delete(`/stories/${s.id}`); onDeleted(s.id); } catch (e) { setErr(apiError(e)); }
  };
  return (
    <div ref={ref} className="border-b border-bz-line last:border-0" data-testid={`story-card-${s.id}`}>
      <button type="button" onClick={onToggle} aria-expanded={open} className="w-full flex items-center gap-3 py-3.5 text-left min-h-[56px]">
        <span className="min-w-0 flex-1">
          <span className="block text-[15px] font-bold truncate">{s.title}</span>
          <span className="block text-[13px] text-bz-muted truncate">{hdate(s.at)}{s.question ? ` · ${s.question}` : ""}</span>
        </span>
        <Chip tone={s.source === "voice" ? "teal" : "muted"}>{s.source === "voice" ? "Voice" : "Typed"}</Chip>
      </button>
      {open ? (
        <div className="pb-5">
          {editing ? <EditStory s={s} onDone={(d) => { setEditing(false); if (d) onChanged(d); }} /> : (
            <AiFrame title="Your proof story" right={s.edited ? <Chip>Edited</Chip> : null}>
              <div className="space-y-3">
                {PARTS.map(([k, l]) => s[k] ? (
                  <div key={k}><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal">{l}</p><p className="text-[15px] leading-relaxed mt-0.5">{s[k]}</p></div>
                ) : null)}
              </div>
              {s.numbers?.length ? <div className="mt-4 flex flex-wrap gap-2">{s.numbers.map((n) => <Chip key={n} tone="gold">{n}</Chip>)}</div> : null}
              {s.pitch_line ? (
                <div className="mt-4 rounded-bzcard border border-bz-line bg-bz-panel p-3.5 flex items-start gap-2">
                  <div className="min-w-0 flex-1"><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-1">Say it in a pitch</p><p className="text-[15px] italic">“{s.pitch_line}”</p></div>
                  <CopyButton text={s.pitch_line} />
                </div>
              ) : null}
              {s.linkedin_post ? (
                <div className="mt-4 rounded-bzcard border border-bz-line bg-bz-panel overflow-hidden">
                  <div className="flex items-center justify-between px-3.5 py-1.5 border-b border-bz-line">
                    <span className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal">LinkedIn post</span>
                    <span data-testid="story-copy-post"><CopyButton text={s.linkedin_post} label="Copy post" /></span>
                  </div>
                  <Para text={s.linkedin_post} className="p-3.5 text-[15px]" />
                </div>
              ) : null}
              {s.transcript && s.source === "voice" ? (
                <details className="mt-4">
                  <summary className="cursor-pointer text-[13px] font-bold text-bz-muted min-h-[40px] flex items-center">What you said</summary>
                  <Para text={s.transcript} className="text-[14px] text-bz-muted" />
                </details>
              ) : null}
              <div className="mt-4 flex flex-wrap gap-2">
                <Button variant="small" onClick={() => setEditing(true)} data-testid="story-edit">Edit</Button>
                {confirm ? (
                  <>
                    <Button variant="danger" onClick={remove} data-testid="story-delete-confirm">Delete for good</Button>
                    <Button variant="small" onClick={() => setConfirm(false)}>Keep it</Button>
                  </>
                ) : <Button variant="small" onClick={() => setConfirm(true)} data-testid="story-delete">Delete</Button>}
              </div>
              <ErrorLine>{err}</ErrorLine>
            </AiFrame>
          )}
        </div>
      ) : null}
    </div>
  );
}

export default function Stories() {
  const { id } = useParams();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["stories"], queryFn: async () => (await api.get("/stories")).data });
  const [openId, setOpenId] = useState(id || null);
  useEffect(() => { if (id) setOpenId(id); }, [id]);

  const patch = (fn) => qc.setQueryData(["stories"], (d) => (d ? { ...d, items: fn(d.items || []) } : d));
  return (
    <Gate feature="story_bank" header={HEADER}>
      <div className="space-y-5">
        <PageHeader kicker="Career Story Bank" ai title="One story a week," accent="turned into proof."
          sub="Answer one question a week out loud. The AI turns your words into a proof story for clients, a LinkedIn post and a line for your pitch." />
        <Loadable q={q} what="your stories" lines={5}>
          {(d) => (
            <>
              {d.question ? (
                <Card className="border-bz-rule">
                  <div className="flex items-center justify-between gap-3">
                    <Label className="mb-0">Story question of the week</Label>
                    {d.answered_this_week ? <Chip tone="gold">Done this week</Chip> : null}
                  </div>
                  <p className="mt-3 text-[20px] sm:text-[22px] font-extrabold leading-snug" data-testid="story-question">{d.question.text}</p>
                </Card>
              ) : null}
              <Capture question={d.question} onMade={(s) => {
                patch((items) => [s, ...items]); setOpenId(s.id);
                qc.invalidateQueries({ queryKey: ["stories"] }); qc.invalidateQueries({ queryKey: ["file"] });
              }} />
              {(d.items || []).length ? (
                <Card>
                  <Label>Your stories · {d.items.length}</Label>
                  {d.items.map((s) => (
                    <StoryCard key={s.id} s={s} open={openId === s.id} onToggle={() => setOpenId(openId === s.id ? null : s.id)}
                      onChanged={(n) => patch((items) => items.map((x) => (x.id === n.id ? n : x)))}
                      onDeleted={(sid) => { patch((items) => items.filter((x) => x.id !== sid)); qc.invalidateQueries({ queryKey: ["stories"] }); }} />
                  ))}
                </Card>
              ) : <Empty title="No stories yet" sub="Your first story takes about five minutes. Start with this week's question." />}
            </>
          )}
        </Loadable>
      </div>
    </Gate>
  );
}
