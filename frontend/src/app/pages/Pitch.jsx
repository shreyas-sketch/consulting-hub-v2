// /app/pitch and /app/pitch/:id — Pitch Practice: the hub's pitch coach watches a video of your pitch and gives a
// senior-coach read (7-metric scorecard, strengths, weaknesses, top 5 changes, timestamped observations, a practice
// assignment). A later take in the same practice shows what changed. 30-minute pause between takes. English only.
// The video is analysed and deleted; nothing is kept. No PDF download on this report (same as the Leadership hub).
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Camera, Clock, Square, Upload, Video } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { BackLink, Gate, ScoreRing, UsageLine } from "../components/common";
import Markdown from "../components/Markdown";
import useRecorder, { clock, mediaDuration } from "../components/useRecorder";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Meter, Note, PageHeader, RowLink, Segmented, Textarea, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Pitch Practice" ai title="Say it out loud," accent="get better." />;
const MAX_MB = 100;
const MAX_MIN = 8;

// ---------------------------------------------------------------- shared recorder box (also used by Portfolio) ----
// Live camera preview while recording, playback after; `children(rec)` renders the actions for a finished recording.
export function RecorderBox({ rec, children, startLabel = "Start recording", testid = "rec" }) {
  const live = ["asking", "ready", "recording"].includes(rec.status);
  const recording = rec.status === "recording";
  return (
    <div>
      {!rec.supported ? <Note>This browser can't record video. Upload a file instead.</Note> : (
        <>
          <div className="relative rounded-bzcard overflow-hidden border border-bz-line bg-black aspect-[3/4] sm:aspect-video max-h-[60vh] w-full">
            {rec.url && !live ? (
              <video key="playback" src={rec.url} controls playsInline className="w-full h-full object-contain" data-testid={`${testid}-playback`} />
            ) : (
              <video key="preview" ref={rec.previewRef} muted playsInline autoPlay className={`w-full h-full object-cover -scale-x-100 ${live ? "" : "opacity-0"}`} data-testid={`${testid}-preview`} />
            )}
            {!live && !rec.url ? (
              <div className="absolute inset-0 grid place-items-center text-center p-4">
                <div><Camera className="w-8 h-8 mx-auto text-bz-gold" aria-hidden /><p className="mt-2 text-[14px] text-bz-muted">Your camera shows here. Look at the lens, not the screen.</p></div>
              </div>
            ) : null}
            {recording ? (
              <span className="absolute top-3 left-3 inline-flex items-center gap-2 rounded-full bg-black/70 px-3 py-1.5 text-[13px] font-bold text-bz-ink">
                <span className="w-2.5 h-2.5 rounded-full bg-bz-miss animate-pulse" aria-hidden />{clock(rec.seconds)} / {clock(rec.maxSeconds)}
              </span>
            ) : null}
          </div>
          <div className="mt-3 flex flex-col sm:flex-row gap-3">
            {recording ? (
              <Button variant="danger" onClick={rec.stop} data-testid={`${testid}-stop`}><Square className="w-4 h-4" aria-hidden />Stop</Button>
            ) : rec.status === "done" ? (
              <>
                {children?.(rec)}
                <Button variant="secondary" onClick={rec.reset} data-testid={`${testid}-again`}>Record again</Button>
              </>
            ) : (
              <>
                <Button onClick={rec.start} loading={rec.status === "asking"} data-testid={`${testid}-start`}><Video className="w-4 h-4" aria-hidden />{startLabel}</Button>
                {rec.status === "idle" || rec.status === "error" ? <Button variant="secondary" onClick={rec.open} data-testid={`${testid}-camera`}>Check my camera</Button> : null}
              </>
            )}
          </div>
          <ErrorLine>{rec.error}</ErrorLine>
        </>
      )}
    </div>
  );
}

// ---------------------------------------------------------------- the report ----
function Delta({ d }) {
  if (d === undefined || d === null) return null;
  const n = Number(d);
  if (n > 0) return <Chip tone="gold">▲ +{n}</Chip>;
  if (n < 0) return <Chip tone="miss">▼ −{Math.abs(n)}</Chip>;
  return <Chip>No change</Chip>;
}

function parseChange(s) {
  const rows = String(s || "").split("\n").map((x) => x.trim()).filter(Boolean);
  const title = (rows.shift() || "").replace(/\*\*/g, "").trim();
  const items = rows.map((r) => {
    const t = r.replace(/^[•\-*]\s*/, "");
    const i = t.indexOf(":");
    return i > 0 && i < 30 ? { label: t.slice(0, i), text: t.slice(i + 1).trim() } : { label: "", text: t };
  });
  return { title, items };
}

function parseObs(s) {
  const m = /^\s*\[?(\d{1,2}:\d{2}(?:\s*[–-]\s*\d{1,2}:\d{2})?)\]?\s*[—–-]?\s*(.*)$/s.exec(String(s || ""));
  return m ? { ts: m[1], text: m[2] } : { ts: "", text: String(s || "") };
}

function Tile({ title, children, tone = "muted", className = "" }) {
  const color = { muted: "text-bz-muted", teal: "text-bz-teal", gold: "text-bz-gold", miss: "text-bz-miss" }[tone];
  return (
    <div className={`rounded-bzcard border border-bz-line bg-bz-panel p-4 min-w-0 ${className}`}>
      <p className={`text-[11.5px] font-medium uppercase tracking-[0.14em] mb-2 ${color}`}>{title}</p>
      {children}
    </div>
  );
}

function Bullets({ items, tone = "gold" }) {
  if (!items?.length) return <p className="text-[14px] text-bz-muted">None this time.</p>;
  const dot = tone === "miss" ? "text-bz-miss" : tone === "teal" ? "text-bz-teal" : "text-bz-gold";
  return (
    <ul className="space-y-2">
      {items.map((x) => <li key={x} className="flex gap-2 text-[14.5px] leading-relaxed"><span className={`${dot} font-extrabold`} aria-hidden>•</span><span className="min-w-0">{x}</span></li>)}
    </ul>
  );
}

export function Report({ take, metrics }) {
  const r = take.report;
  const cmp = r.kind === "comparison";
  return (
    <AiFrame title={`Take ${take.n} · ${cmp ? "what changed" : "first read"}`} className="rise-in" right={<span className="text-[12px] text-bz-muted">{hdate(take.at)}</span>}>
      <div className="grid gap-3 lg:grid-cols-3" data-testid="pitch-report">
        <div className="rounded-bzcard border border-bz-line bg-bz-panel p-4 flex flex-col items-center justify-center text-center">
          <ScoreRing value={r.overall} max={10} size={128} label="Overall" sub="overall, out of 10" />
          {cmp ? <div className="mt-2 flex items-center gap-2"><span className="text-[12px] text-bz-muted">Last take {r.previous_overall}</span><Delta d={r.overall_delta} /></div> : null}
        </div>
        <Tile title={cmp ? "Overall progress" : "How you come across"} className="lg:col-span-2">
          <p className="text-[15px] leading-relaxed whitespace-pre-line">{cmp ? r.overall_progress : r.overall_summary}</p>
        </Tile>
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3" data-testid="pitch-scorecard">
        {metrics.map(({ key, label }) => {
          const m = r.scorecard[key];
          return (
            <div key={key} className="rounded-bzcard border border-bz-line bg-bz-panel p-4 min-w-0">
              <div className="flex items-center justify-between gap-2">
                <p className="text-[13px] font-bold">{label}</p>
                <div className="flex items-center gap-1.5 shrink-0">
                  {cmp ? <Delta d={m.delta} /> : null}
                  <span className="text-[18px] font-extrabold tabular text-bz-gold">{m.score}<span className="text-[12px] text-bz-muted">/10</span></span>
                </div>
              </div>
              <Meter value={m.score * 10} className="mt-2" label={label} />
              <p className="text-[13.5px] text-bz-muted mt-2 leading-relaxed">{m.justification}</p>
            </div>
          );
        })}
      </div>

      <div className="mt-3 grid gap-3 sm:grid-cols-2">
        <Tile title="Delivery"><p className="text-[14.5px] leading-relaxed">{r.delivery_dynamics}</p></Tile>
        <Tile title="Voice"><p className="text-[14.5px] leading-relaxed">{r.vocal_profile}</p></Tile>
        <Tile title="Body language"><p className="text-[14.5px] leading-relaxed">{r.body_language_detail}</p></Tile>
        <Tile title="What the client takes away"><p className="text-[14.5px] leading-relaxed">{r.audience_simulation}</p></Tile>
      </div>

      {cmp ? (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Tile title="Got better" tone="gold"><Bullets items={r.improvements} /></Tile>
          <Tile title="Slipped" tone={r.regressions?.length ? "miss" : "muted"}><Bullets items={r.regressions} tone="miss" /></Tile>
          <Tile title="Still to fix"><Bullets items={r.persisting_issues} tone="teal" /></Tile>
          <Tile title="New strengths" tone="gold"><Bullets items={r.new_strengths} /></Tile>
        </div>
      ) : (
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          <Tile title="Strengths to keep" tone="gold"><Bullets items={r.strengths} /></Tile>
          <Tile title="What's holding you back"><Bullets items={r.weaknesses} tone="teal" /></Tile>
        </div>
      )}
      {cmp && r.weaknesses?.length ? <Tile title="Keep working on" className="mt-3"><Bullets items={r.weaknesses} tone="teal" /></Tile> : null}

      <div className="mt-5">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold mb-3">Your top 5 changes</p>
        <ol className="space-y-3" data-testid="pitch-top-changes">
          {r.top_changes.map((c, i) => {
            const { title, items } = parseChange(c);
            return (
              <li key={c} className="rounded-bzcard border border-bz-line bg-bz-panel p-4 flex gap-3">
                <span className="w-[30px] h-[30px] shrink-0 rounded-full border border-bz-gold text-bz-gold grid place-items-center text-[13px] font-extrabold">{i + 1}</span>
                <div className="min-w-0">
                  <p className="font-bold text-[15px] leading-snug">{title}</p>
                  {items.map((it) => (
                    <p key={it.label + it.text} className="text-[14px] text-bz-muted mt-1.5 leading-relaxed">
                      {it.label ? <b className="text-bz-ink">{it.label}: </b> : null}{it.text}
                    </p>
                  ))}
                </div>
              </li>
            );
          })}
        </ol>
      </div>

      <div className="mt-5">
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-2.5">Moments in your video</p>
        <ul className="space-y-2">
          {r.specific_observations.map((o) => {
            const { ts, text } = parseObs(o);
            return (
              <li key={o} className="flex gap-3 text-[14.5px] leading-relaxed">
                <span className="shrink-0 min-w-[52px]">{ts ? <Chip tone="teal">{ts}</Chip> : null}</span>
                <span className="min-w-0">{text}</span>
              </li>
            );
          })}
        </ul>
      </div>

      <div className="mt-5 rounded-bzcard border border-bz-rule bg-bz-gold-tint p-4">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold mb-1.5">Your practice this week</p>
        <p className="text-[15px] leading-relaxed whitespace-pre-line">{r.practice_assignment}</p>
      </div>
    </AiFrame>
  );
}

// ---------------------------------------------------------------- take capture ----
function useCountdown(nextAt, onZero) {
  const [left, setLeft] = useState(0);
  const cb = useRef(onZero);
  cb.current = onZero;
  useEffect(() => {
    if (!nextAt) { setLeft(0); return undefined; }
    const tick = () => {
      const s = Math.max(0, Math.ceil((new Date(nextAt).getTime() - Date.now()) / 1000));
      setLeft(s);
      if (s === 0) { clearInterval(t); cb.current?.(); }
    };
    const t = setInterval(tick, 1000);
    tick();
    return () => clearInterval(t);
  }, [nextAt]);
  return left;
}

function Cooldown({ t, onReady }) {
  const left = useCountdown(t.next_upload_at, onReady);
  return (
    <Card className="border-bz-rule" data-testid="pitch-cooldown">
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-bz-gold-tint text-bz-gold grid place-items-center shrink-0"><Clock className="w-5 h-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="text-[13px] text-bz-muted">Next take in</p>
          <p className="text-[30px] font-extrabold tabular text-bz-gold leading-tight" data-testid="pitch-cooldown-time">{clock(left)}</p>
          <p className="text-[14.5px] mt-1.5">The pause is on purpose. Read your top 5 changes, do the first drill a few times, then record again.</p>
        </div>
      </div>
    </Card>
  );
}

function Capture({ t, onDone }) {
  const { plan, refreshMe } = useAuth();
  const [mode, setMode] = useState("record");
  const [file, setFile] = useState(null);
  const [fileSecs, setFileSecs] = useState(null);
  const [phase, setPhase] = useState(null);             // null | "upload" | "analyse"
  const [pct, setPct] = useState(0);
  const [err, setErr] = useState("");
  const rec = useRecorder({ video: true, maxSeconds: MAX_MIN * 60 });
  const fileRef = useRef(null);
  const usage = plan?.limits?.pitch;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const pick = async (e) => {
    const f = e.target.files?.[0];
    setErr(""); setFile(null); setFileSecs(null);
    if (!f) return;
    if (!/\.(mp4|mov|webm|mkv|m4v)$/i.test(f.name) && !/^video\//.test(f.type)) { setErr("Use a video file: MP4, MOV, WEBM or MKV."); return; }
    if (f.size > MAX_MB * 1024 * 1024) { setErr(`That video is larger than ${MAX_MB} MB. Trim it or record a shorter take.`); return; }
    const secs = await mediaDuration(f);
    if (secs && secs > MAX_MIN * 60 + 2) { setErr(`Keep your video under ${MAX_MIN} minutes.`); return; }
    setFile(f); setFileSecs(secs);
  };

  const send = async (blob, name, secs) => {
    setErr(""); setPct(0); setPhase("upload");
    try {
      const params = { filename: name };
      if (secs && Number.isFinite(secs)) params.duration_s = Math.round(secs * 10) / 10;
      const { data } = await api.post(`/pitch/${t.id}/take`, blob, {
        params, timeout: 0, headers: { "Content-Type": blob.type || "application/octet-stream" },
        onUploadProgress: (ev) => {
          const v = ev.total ? Math.min(1, ev.loaded / ev.total) : 0;
          setPct(v);
          if (v >= 1) setPhase("analyse");
        },
      });
      rec.reset(); setFile(null); setFileSecs(null);
      if (fileRef.current) fileRef.current.value = "";
      refreshMe();
      onDone(data);
    } catch (e) {
      if (e?.response?.status === 429) onDone(null);
      else if (![402, 403].includes(e?.response?.status)) setErr(apiError(e));
    } finally { setPhase(null); }
  };

  if (phase) {
    return (
      <AiFrame title="Pitch Coach">
        {phase === "upload" ? (
          <div role="status">
            <p className="text-[15px] font-bold">Uploading your take{pct ? ` · ${Math.round(pct * 100)}%` : ""}</p>
            <Meter value={pct * 100} tone="teal" className="mt-2" label="Upload" />
            <Note className="mt-2">Keep this screen open.</Note>
          </div>
        ) : (
          <>
            <Thinking label="Watching your take" />
            <Note>This usually takes one to three minutes. Keep this screen open.</Note>
          </>
        )}
      </AiFrame>
    );
  }
  return (
    <Card>
      <Label>{t.takes.length ? `Record take ${t.takes.length + 1}` : "Record your first take"}</Label>
      <Segmented label="How" value={mode} onChange={(v) => { setMode(v); setErr(""); }} testid="pitch-mode"
        options={[{ value: "record", label: "Record here" }, { value: "upload", label: "Upload a video" }]} />
      <div className="mt-4">
        {mode === "record" ? (
          <RecorderBox rec={rec} testid="pitch-rec">
            {(r) => <Button variant="ai" onClick={() => send(r.blob, `take.${r.ext || "webm"}`, r.recordedSeconds)} disabled={!canRun} data-testid="pitch-analyse">Analyse my take</Button>}
          </RecorderBox>
        ) : (
          <div className="space-y-3">
            <label className="flex items-center gap-3 rounded-bzcard border border-dashed border-bz-line-strong bg-bz-panel p-4 min-h-[64px] cursor-pointer hover:border-bz-gold">
              <Upload className="w-5 h-5 text-bz-gold shrink-0" aria-hidden />
              <span className="min-w-0">
                <span className="block text-[15px] font-bold truncate">{file ? file.name : "Choose a video"}</span>
                <span className="block text-[13px] text-bz-muted">MP4, MOV, WEBM or MKV · up to {MAX_MIN} min · {MAX_MB} MB</span>
              </span>
              <input ref={fileRef} type="file" accept="video/mp4,video/quicktime,video/webm,video/x-matroska,.mp4,.mov,.webm,.mkv,.m4v" className="sr-only" onChange={pick} data-testid="pitch-file" />
            </label>
            <Button variant="ai" className="w-full" disabled={!file || !canRun} onClick={() => send(file, file.name, fileSecs)} data-testid="pitch-analyse-upload">Analyse my take</Button>
          </div>
        )}
      </div>
      <ErrorLine>{err}</ErrorLine>
      <UsageLine usage={usage} what="pitch practices" className="mt-3 text-center" />
      <Note className="mt-1 text-center">English only. Your video is analysed, then deleted. We never keep it.</Note>
    </Card>
  );
}

// ---------------------------------------------------------------- follow-up chat ----
function Chat({ t, onUpdate }) {
  const [msg, setMsg] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const chat = t.messages.filter((m) => m.kind !== "intro");
  const endRef = useRef(null);
  useEffect(() => { if (busy && endRef.current?.scrollIntoView) endRef.current.scrollIntoView({ block: "nearest" }); }, [busy]);
  const ask = async (e) => {
    e.preventDefault();
    const text = msg.trim();
    if (!text) return;
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post(`/pitch/${t.id}/chat`, { message: text });
      setMsg(""); onUpdate(data);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <Card>
      <Label tone="teal">Ask your coach</Label>
      {chat.length ? (
        <div className="space-y-3 mb-4" data-testid="pitch-chat">
          {chat.map((m) => m.role === "user" ? (
            <div key={m.id} className="flex justify-end"><p className="max-w-[85%] rounded-bzcard bg-bz-raised border border-bz-line px-3.5 py-2.5 text-[15px] whitespace-pre-line">{m.content}</p></div>
          ) : (
            <div key={m.id} className="rounded-bzcard border border-[rgba(46,211,183,0.4)] bg-bz-panel px-3.5 py-1"><Markdown text={m.content} /></div>
          ))}
        </div>
      ) : <Note className="mb-3">Ask about any score, any moment in your video, or how to say a line better.</Note>}
      {busy ? <Thinking label="Your coach is writing" /> : null}
      <div ref={endRef} />
      <form onSubmit={ask} className="space-y-2">
        <Textarea rows={3} value={msg} onChange={(e) => setMsg(e.target.value)} maxLength={2000} placeholder="e.g. How do I stop my voice dropping at the end?" disabled={busy || t.chat_left <= 0} data-testid="pitch-chat-input" />
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" variant="ai" className="w-full" disabled={busy || !msg.trim() || t.chat_left <= 0} data-testid="pitch-chat-send">Ask the coach</Button>
        {t.chat_left <= 5 ? <Note className="text-center">{t.chat_left > 0 ? `${t.chat_left} questions left in this practice.` : "Start a new practice to keep asking."}</Note> : null}
      </form>
    </Card>
  );
}

// ---------------------------------------------------------------- a practice thread ----
function Thread({ id }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["pitch", id], queryFn: async () => (await api.get(`/pitch/${id}`)).data });
  const [shown, setShown] = useState(null);
  const [confirm, setConfirm] = useState(false);
  const takes = q.data?.takes || [];
  const current = takes.find((x) => x.n === shown) || takes[takes.length - 1];
  const update = (data) => {
    if (data) { qc.setQueryData(["pitch", id], data); setShown(null); } else q.refetch();
    qc.invalidateQueries({ queryKey: ["pitch-list"] });
  };
  const remove = async () => {
    try { await api.delete(`/pitch/${id}`); } catch { /* already gone */ }
    qc.invalidateQueries({ queryKey: ["pitch-list"] }); nav("/app/pitch");
  };

  return (
    <div className="space-y-5">
      <BackLink to="/app/pitch">All practices</BackLink>
      <Loadable q={q} what="this practice" lines={8}>
        {(t) => (
          <>
            <PageHeader kicker={t.type_label} ai title={t.title} sub={[t.setting, t.audience && `Audience: ${t.audience}`].filter(Boolean).join(" ")} />
            {!t.takes.length ? <AiFrame title="Pitch Coach"><Markdown text={t.messages.find((m) => m.kind === "intro")?.content} /></AiFrame> : null}
            {t.takes.length > 1 ? (
              <div className="flex flex-wrap gap-2" role="group" aria-label="Takes">
                {t.takes.map((x) => (
                  <button key={x.n} type="button" onClick={() => setShown(x.n)} aria-pressed={current?.n === x.n} data-testid={`pitch-take-${x.n}`}
                    className={`min-h-[44px] px-4 rounded-full text-[14px] font-bold border ${current?.n === x.n ? "bg-bz-gold text-bz-on-accent border-bz-gold" : "bg-bz-panel text-bz-ink border-bz-line"}`}>
                    Take {x.n} · {x.overall}
                  </button>
                ))}
              </div>
            ) : null}
            {current ? <Report take={current} metrics={t.metrics} /> : null}
            {t.can_upload ? <Capture t={t} onDone={update} /> : <Cooldown t={t} onReady={() => q.refetch()} />}
            {t.takes.length ? <Chat t={t} onUpdate={update} /> : null}
            <div className="flex flex-wrap items-center gap-2 pt-2">
              {confirm ? (
                <>
                  <Button variant="danger" onClick={remove} data-testid="pitch-delete-confirm">Delete this practice</Button>
                  <Button variant="small" onClick={() => setConfirm(false)}>Keep it</Button>
                </>
              ) : <Button variant="small" onClick={() => setConfirm(true)} data-testid="pitch-delete">Delete practice</Button>}
            </div>
          </>
        )}
      </Loadable>
    </div>
  );
}

// ---------------------------------------------------------------- list + new practice ----
function NewPractice({ types }) {
  const nav = useNavigate();
  const qc = useQueryClient();
  const [type, setType] = useState("elevator");
  const [setting, setSetting] = useState("");
  const [audience, setAudience] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const preset = types.find((x) => x.key === type) || {};
  const start = async () => {
    if (type === "other" && setting.trim().length < 3) { setErr("Tell us where you'll use this pitch."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/pitch", { pitch_type: type, setting, audience });
      qc.setQueryData(["pitch", data.id], data); qc.invalidateQueries({ queryKey: ["pitch-list"] });
      nav(`/app/pitch/${data.id}`);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Card>
      <Label>New practice</Label>
      <p className="text-[14px] text-bz-muted mb-3">What are you practising?</p>
      <Segmented label="Pitch type" value={type} onChange={(v) => { setType(v); setErr(""); }} testid="pitch-type"
        options={types.map((x) => ({ value: x.key, label: x.label }))} />
      <div className="mt-4 space-y-3">
        <Field label={type === "other" ? "Where you'll use it" : "Where you'll use it (optional)"}>
          <Input value={setting} onChange={(e) => setSetting(e.target.value)} maxLength={300} placeholder={preset.setting || "e.g. A board update to a family business"} data-testid="pitch-setting" />
        </Field>
        <Field label="Who will hear it (optional)">
          <Input value={audience} onChange={(e) => setAudience(e.target.value)} maxLength={300} placeholder={preset.audience || "e.g. The owner and two directors"} data-testid="pitch-audience" />
        </Field>
        <ErrorLine>{err}</ErrorLine>
        <Button className="w-full" onClick={start} loading={busy} data-testid="pitch-start">Start this practice</Button>
      </div>
    </Card>
  );
}

function List() {
  const { plan } = useAuth();
  const q = useQuery({ queryKey: ["pitch-list"], queryFn: async () => (await api.get("/pitch")).data });
  return (
    <div className="space-y-5">
      <PageHeader kicker="Pitch Practice" ai title="Say it out loud," accent="get better."
        sub="Record your pitch on video. Your coach scores seven things clients notice, shows the exact moments, and gives you the five changes that matter most. Then record again and see what moved." />
      <Loadable q={q} what="your practices" lines={4}>
        {(d) => (
          <>
            {d.available === false ? <Card inset><p className="text-[15px]">Pitch Practice is paused right now. Your past reports are still here.</p></Card> : <NewPractice types={d.types || []} />}
            <UsageLine usage={plan?.limits?.pitch} what="pitch practices" className="text-center" />
            {(d.items || []).length ? (
              <Card>
                <Label>Your practices</Label>
                {d.items.map((x) => (
                  <RowLink key={x.id} to={`/app/pitch/${x.id}`} title={x.title} testid={`pitch-thread-${x.id}`}
                    sub={`${x.type_label} · ${x.takes ? `${x.takes} take${x.takes > 1 ? "s" : ""} · last ${x.last_score}/10` : "no take yet"} · ${ago(x.updated_at)}`}
                    right={x.can_upload ? <Chip tone="gold">Ready</Chip> : <Chip>Pause</Chip>} />
                ))}
              </Card>
            ) : <Empty title="No practices yet" sub="Start with the 60-second elevator pitch. It's the one you'll use most." />}
          </>
        )}
      </Loadable>
    </div>
  );
}

export default function Pitch() {
  const { id } = useParams();
  return <Gate feature="pitch" header={HEADER}>{id ? <Thread id={id} /> : <List />}</Gate>;
}
