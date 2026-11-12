// /app/linkedin — LinkedIn Profile Review. The member uploads screenshots of their own profile; the AI reads it the way
// their ideal client would (niche from Starting Point) and says what each section costs them and what to write instead.
// Then a 30-day post plan for the same client, ticked off day by day. The old paste-your-headline score stays at the
// bottom as a quick check without screenshots.
import { useEffect, useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, ImagePlus, Quote, X } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { LockCard, Para, ScoreRing, UsageLine } from "../components/common";
import { Link } from "react-router-dom";
import { AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, Meter, Note, PageHeader, Segmented, Step, Textarea, Thinking } from "../components/ui";

function CopyBtn({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" onClick={async () => { try { await navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); } catch { /* blocked */ } }}
      className="shrink-0 inline-flex items-center gap-1 text-[12px] font-bold text-bz-teal min-h-[36px] px-2" aria-label="Copy">
      {ok ? <Check className="w-3.5 h-3.5" aria-hidden /> : <Copy className="w-3.5 h-3.5" aria-hidden />}{ok ? "Copied" : "Copy"}
    </button>
  );
}

function Result({ r }) {
  return (
    <div className="space-y-4">
      <Card className="rise-in" data-testid="linkedin-result">
        <div className="flex flex-col sm:flex-row sm:items-center gap-6">
          <ScoreRing value={r.score} max={100} size={140} label="LinkedIn Score" sub="out of 100" />
          <div className="flex-1 space-y-3">
            {r.parts.map((p) => (
              <div key={p.key}>
                <div className="flex justify-between text-[13.5px] gap-3"><span>{p.label}</span><span className="font-extrabold text-bz-gold tabular shrink-0">{p.score}/{p.max}</span></div>
                <Meter value={(p.score / p.max) * 100} className="mt-1" label={p.label} />
              </div>
            ))}
            {!r.experience_checked && <p className="text-[12px] text-bz-muted">Paste a role from your Experience section too, to check it.</p>}
          </div>
        </div>
        {r.problems.length > 0 && (
          <div className="mt-6 space-y-3">
            <Label className="mb-0">Fix these first</Label>
            {r.problems.map((p, i) => <Step key={p.key} n={i + 1} title={p.label}>{p.tip}</Step>)}
          </div>
        )}
        <p className="text-[12px] text-bz-muted mt-4">Checked {hdate(r.at)}</p>
      </Card>
      {r.rewrites && (
        <AiFrame title="Rewritten around your niche" className="rise-in">
          <p className="text-[12px] font-semibold text-bz-teal mb-2">Headline options</p>
          <div className="space-y-2">
            {r.rewrites.headlines.map((h) => (
              <div key={h.text} className="rounded-bzcard border border-bz-line bg-bz-panel p-3 flex items-start gap-2">
                <div className="min-w-0 flex-1"><p className="text-[11px] font-bold text-bz-muted">{h.angle} angle</p><p className="text-[15px] font-bold">{h.text}</p></div>
                <CopyBtn text={h.text} />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between mt-5 mb-2">
            <p className="text-[12px] font-semibold text-bz-teal">About section</p>
            <CopyBtn text={r.rewrites.about} />
          </div>
          <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5"><Para text={r.rewrites.about} className="text-[14.5px]" /></div>
          {r.rewrites.posts?.length > 0 && (
            <>
              <p className="text-[12px] font-semibold text-bz-teal mt-5 mb-2">Three posts to write next</p>
              <div className="space-y-3">{r.rewrites.posts.map((p, i) => <Step key={p.hook} n={i + 1} ai title={p.hook}>{p.summary}</Step>)}</div>
            </>
          )}
          <p className="text-[12px] text-bz-muted mt-4">Where you see [number], put your own figure. We never invent your results.</p>
        </AiFrame>
      )}
      {r.rewrites_locked && <LockCard feature="linkedin_improve" planNeeded="member" />}
    </div>
  );
}


// ============================================================================ screenshot review ======
const STATUS = { strong: ["Working", "gold"], improve: ["Change this", "teal"], missing: ["Missing", "miss"], not_shown: ["Not in your screenshots", "muted"] };
const CAPTURE = [
  ["The top of your profile", "Photo, banner, name and headline, in one screenshot."],
  ["About", "Tap “see more” first so the whole section shows."],
  ["Experience", "Your current role and one or two before it."],
  ["Featured, if you have it", "Anything pinned near the top."],
];

function Shots({ files, setFiles, max, maxMb, onError }) {
  const urls = useMemo(() => files.map((f) => URL.createObjectURL(f)), [files]);
  useEffect(() => () => urls.forEach((u) => URL.revokeObjectURL(u)), [urls]);
  const add = (list) => {
    // setFiles clears any old message, so the new message (if any) is set after it
    const picked = [...list].filter((f) => /^image\//.test(f.type));
    const big = picked.find((f) => f.size > maxMb * 1024 * 1024);
    if (big) { onError(`“${big.name}” is over ${maxMb} MB. Take a normal screenshot and try again.`); return; }
    setFiles([...files, ...picked].slice(0, max));
    if (picked.length < list.length) onError("Only images can be used: PNG or JPG screenshots.");
    else if (files.length + picked.length > max) onError(`Up to ${max} screenshots. We kept the first ${max}.`);
  };
  return (
    <div>
      <label className="flex flex-col items-center justify-center gap-2 rounded-bzcard border-2 border-dashed border-bz-line-strong bg-bz-panel px-4 py-7 text-center cursor-pointer hover:border-bz-gold focus-within:border-bz-gold focus-within:ring-2 focus-within:ring-bz-gold focus-within:ring-offset-2"
        onDragOver={(e) => e.preventDefault()} onDrop={(e) => { e.preventDefault(); add(e.dataTransfer.files); }} data-testid="li-drop">
        <ImagePlus className="w-7 h-7 text-bz-gold" strokeWidth={1.6} aria-hidden />
        <span className="text-[15px] font-bold">{files.length ? "Add more screenshots" : "Choose your LinkedIn screenshots"}</span>
        <span className="text-[13px] text-bz-muted">Up to {max} images, PNG or JPG. From your phone's gallery or your computer.</span>
        <input type="file" accept="image/*" multiple className="sr-only" data-testid="li-files"
          onChange={(e) => { add(e.target.files); e.target.value = ""; }} />
      </label>
      {files.length > 0 && (
        <ul className="mt-3 grid grid-cols-3 sm:grid-cols-5 gap-2" data-testid="li-thumbs">
          {files.map((f, i) => (
            <li key={`${f.name}-${i}`} className="relative rounded-bzbtn overflow-hidden border border-bz-line bg-bz-card aspect-[3/4]">
              <img src={urls[i]} alt={`Screenshot ${i + 1}`} className="w-full h-full object-cover object-top" />
              <button type="button" onClick={() => setFiles(files.filter((_, j) => j !== i))} aria-label={`Remove screenshot ${i + 1}`}
                className="absolute top-1 right-1 w-8 h-8 grid place-items-center rounded-full bg-bz-card/95 border border-bz-line text-bz-ink">
                <X className="w-4 h-4" aria-hidden />
              </button>
              <span className="absolute bottom-0 inset-x-0 bg-bz-card/90 text-[11px] font-semibold text-center py-0.5 tabular">{i + 1}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function ReviewForm({ d, usage, onDone, onCancel }) {
  const { refreshMe } = useAuth();
  const [files, setFiles] = useState([]);
  const [target, setTarget] = useState(d.target || "");
  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const send = async () => {
    if (!files.length) { setErr("Add at least one screenshot of your profile."); return; }
    if (target.trim().length < 3) { setErr("Say who you want as clients, for example “owners of auto component makers in Pune”."); return; }
    setErr(""); setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      fd.append("target", target.trim());
      if (notes.trim()) fd.append("notes", notes.trim());
      const { data } = await api.post("/linkedin-review", fd);
      refreshMe(); onDone(data);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  if (busy) return <AiFrame title="Reviewing your profile"><Thinking label="Reading your profile the way your client would. This takes about a minute." /></AiFrame>;
  return (
    <Card data-testid="li-review-form">
      <Label>Review my profile</Label>
      <div className="space-y-5">
        <Field label="Who do you want as clients?"
          hint={d.niche ? `From your niche: ${d.niche}. Change it if you like.` : null}>
          <Input value={target} onChange={(e) => setTarget(e.target.value)} maxLength={200} placeholder="e.g. Owners of mid-size auto component makers in Pune" data-testid="li-target" />
        </Field>
        {!d.niche && <Note>No niche chosen yet. <Link to="/app/start" className="text-bz-gold font-bold">Choose your niche in Starting Point</Link> for a sharper review.</Note>}
        <div>
          <p className="text-[14px] font-semibold mb-2">Your screenshots</p>
          <ol className="grid sm:grid-cols-2 gap-x-4 gap-y-2 mb-3">
            {CAPTURE.map(([t, s], i) => <li key={t}><Step n={i + 1} title={t}>{s}</Step></li>)}
          </ol>
          <Shots files={files} setFiles={(f) => { setFiles(f); setErr(""); }} max={d.max_files || 5} maxMb={d.max_mb || 8} onError={setErr} />
        </div>
        <Field label="Anything we should know? (optional)">
          <Textarea rows={2} value={notes} onChange={(e) => setNotes(e.target.value)} maxLength={500} placeholder="e.g. I'm still employed, so I can't say I'm a consultant yet" />
        </Field>
      </div>
      <ErrorLine>{err}</ErrorLine>
      <Button variant="ai" className="w-full mt-4" onClick={send} disabled={!canRun} data-testid="li-review-go">Review my profile</Button>
      <UsageLine usage={usage} what="profile reviews" className="mt-2 text-center" />
      <Note className="mt-1 text-center">We never log in to your LinkedIn. Your screenshots are read once and not kept.</Note>
      {onCancel && <button type="button" onClick={onCancel} className="mt-1 w-full text-[14px] font-bold text-bz-muted min-h-[44px]">Back to my review</button>}
    </Card>
  );
}

function Copyable({ label, text: t, children }) {
  return (
    <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">{label && <p className="text-[12px] font-semibold text-bz-muted mb-0.5">{label}</p>}{children}</div>
        <CopyBtn text={t} />
      </div>
    </div>
  );
}

// The order a member works through the changes: the text they can paste first, then the rest.
const ORDER = ["headline", "about", "banner", "experience", "featured", "skills", "photo", "contact", "activity"];
// the one-line "what to do" when the AI wrote the text for a section but no note on it
const DEFAULT_FIX = { headline: "Replace your headline with one of the options.", about: "Replace your About section with the new one.", banner: "Put this line on your banner.", experience: "Rewrite your roles as results, not duties.", featured: "Pin these near the top of your profile.", skills: "Put these skills at the top, in this order." };
const LABELS = { headline: "Headline", about: "About", banner: "Banner", experience: "Experience", featured: "Featured", skills: "Skills", photo: "Profile photo", contact: "How to contact you", activity: "Posts and activity" };

// The ready-to-paste text for a section, shown inside that change (so nothing appears twice on the page).
function ReadyText({ k, rv }) {
  if (k === "headline" && rv.headlines?.length) {
    return (
      <div className="space-y-2">
        <p className="text-[12.5px] font-semibold text-bz-teal">Pick one and paste it as your headline</p>
        {rv.headlines.map((h, i) => (
          <Copyable key={h.text} label={`Option ${i + 1}${h.angle ? ` · ${h.angle}` : ""}`} text={h.text}>
            <p className="text-[15px] font-bold">{h.text}</p>
            {h.why && <p className="text-[13px] text-bz-muted mt-0.5">{h.why}</p>}
          </Copyable>
        ))}
      </div>
    );
  }
  if (k === "about" && rv.about) return <AboutText text={rv.about} />;
  if (k === "banner" && rv.banner) {
    return <div><p className="text-[12.5px] font-semibold text-bz-teal mb-2">Text for your banner</p><Copyable text={rv.banner}><p className="font-bold">{rv.banner}</p></Copyable></div>;
  }
  if (k === "experience" && rv.experience?.length) {
    return (
      <div className="space-y-2">
        <p className="text-[12.5px] font-semibold text-bz-teal">Replace each role's description with these results</p>
        {rv.experience.map((e) => (
          <Copyable key={e.role} label={e.role} text={e.bullets.map((b) => `• ${b}`).join("\n")}>
            <ul className="mt-1 space-y-1 text-[14.5px] list-disc pl-5">{e.bullets.map((b) => <li key={b}>{b}</li>)}</ul>
          </Copyable>
        ))}
      </div>
    );
  }
  if (k === "featured" && rv.featured?.length) {
    return (
      <div><p className="text-[12.5px] font-semibold text-bz-teal mb-2">Pin these, in this order</p>
        <ol className="space-y-1.5 text-[14.5px] list-decimal pl-5">{rv.featured.map((x) => <li key={x}>{x}</li>)}</ol></div>
    );
  }
  if (k === "skills" && rv.skills?.length) {
    return (
      <div>
        <div className="flex items-center justify-between gap-2 mb-2"><p className="text-[12.5px] font-semibold text-bz-teal">Your top skills, in this order</p><CopyBtn text={rv.skills.join(", ")} /></div>
        <div className="flex flex-wrap gap-1.5">{rv.skills.map((x) => <Chip key={x}>{x}</Chip>)}</div>
      </div>
    );
  }
  return null;
}

function AboutText({ text: t }) {
  const [open, setOpen] = useState(false);
  return (
    <div>
      <div className="flex items-center justify-between gap-2 mb-2"><p className="text-[12.5px] font-semibold text-bz-teal">Your new About section</p><CopyBtn text={t} /></div>
      <div className={`relative rounded-bzcard border border-bz-line bg-bz-panel p-3.5 ${open ? "" : "max-h-[168px] overflow-hidden"}`}>
        <Para text={t} className="text-[14.5px]" />
        {!open && <span aria-hidden className="absolute inset-x-0 bottom-0 h-14 bg-gradient-to-t from-bz-panel to-transparent" />}
      </div>
      <button type="button" onClick={() => setOpen((o) => !o)} aria-expanded={open} className="text-[13px] font-bold text-bz-gold min-h-[36px]" data-testid="li-about-more">{open ? "Show less" : "Read the whole About section"}</button>
      <p className="text-[12px] text-bz-muted">Put your own figures where you see [number] or [result]. We never invent your results.</p>
    </div>
  );
}

const doneKey = (r) => `li-done:${r.id || r.at}`;
function useDone(r) {
  const [done, setDone] = useState(() => { try { return JSON.parse(localStorage.getItem(doneKey(r)) || "[]"); } catch { return []; } });
  const toggle = (k) => setDone((d) => {
    const next = d.includes(k) ? d.filter((x) => x !== k) : [...d, k];
    try { localStorage.setItem(doneKey(r), JSON.stringify(next)); } catch { /* private window: ticks last for this visit */ }
    return next;
  });
  return [done, toggle];
}

function ChangeItem({ n, s, rv, done, onToggle, open, onOpen }) {
  const [word, tone] = STATUS[s.status] || STATUS.improve;
  const why = s.why || (s.key === "headline" ? rv.headline_problem : "");
  const now = s.now || (s.key === "headline" ? rv.read?.headline : "");
  return (
    <li className={`rounded-bzcard border ${open ? "border-bz-line-strong bg-bz-card" : "border-bz-line bg-bz-card"}`} data-testid={`li-sec-${s.key}`}>
      <div className="flex items-start gap-3 p-3.5 sm:p-4">
        <input type="checkbox" checked={done} onChange={onToggle} aria-label={`${s.label}: done`} className="mt-1 w-5 h-5 shrink-0 accent-[rgb(29_78_216)]" data-testid={`li-done-${s.key}`} />
        <button type="button" onClick={onOpen} aria-expanded={open} className="min-w-0 flex-1 text-left">
          <span className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <span className="text-[12.5px] font-semibold text-bz-muted tabular">{n}.</span>
            <span className={`font-bold text-[15.5px] ${done ? "line-through text-bz-muted decoration-1" : ""}`}>{s.label}</span>
            <Chip tone={done ? "gold" : tone}>{done ? "Done" : word}</Chip>
          </span>
          {(s.fix || DEFAULT_FIX[s.key]) && <span className={`block mt-1 text-[14.5px] ${done ? "text-bz-muted" : ""}`}>{s.fix || DEFAULT_FIX[s.key]}</span>}
          <span className="block mt-1 text-[13px] font-bold text-bz-gold">{open ? "Hide details" : "Show what to change"}</span>
        </button>
      </div>
      {open && (
        <div className="px-3.5 sm:px-4 pb-4 sm:pl-12 space-y-3" data-testid={`li-sec-${s.key}-detail`}>
          {(now || why) && (
            <div className="rounded-bzcard bg-bz-panel border border-bz-line p-3 text-[14px] space-y-1">
              {now && <p><span className="font-semibold">Now: </span><span className="text-bz-muted">“{now}”</span></p>}
              {why && <p><span className="font-semibold">Why it costs you: </span>{why}</p>}
            </div>
          )}
          <ReadyText k={s.key} rv={rv} />
        </div>
      )}
    </li>
  );
}

function ReviewResult({ r, canAgain, onAgain }) {
  const rv = r;
  const byKey = Object.fromEntries((rv.sections || []).map((s) => [s.key, s]));
  const hasText = { headline: rv.headlines?.length, about: rv.about, banner: rv.banner, experience: rv.experience?.length, featured: rv.featured?.length, skills: rv.skills?.length };
  // a change: a section that needs work, or one not in the screenshots that still comes with ready text to use
  const changes = ORDER.map((k) => byKey[k] || (hasText[k] ? { key: k, label: LABELS[k], status: "improve", now: "", why: "", fix: DEFAULT_FIX[k] } : null))
    .filter((s) => s && (s.status === "improve" || s.status === "missing" || (s.status === "not_shown" && hasText[s.key])));
  const working = (rv.sections || []).filter((s) => s.status === "strong");
  const unseen = (rv.sections || []).filter((s) => s.status === "not_shown" && !hasText[s.key]);
  const [done, toggle] = useDone(r);
  const doneN = changes.filter((s) => done.includes(s.key)).length;
  const [open, setOpen] = useState(() => changes.find((s) => !done.includes(s.key))?.key || null);
  return (
    <div className="space-y-4" data-testid="li-review">
      <AiFrame title="Through your client's eyes" className="rise-in">
        <div className="flex flex-col sm:flex-row gap-5 sm:items-center">
          <ScoreRing value={rv.score} max={100} size={112} label="Client fit" sub="client fit, out of 100" ai />
          <div className="min-w-0 flex-1">
            <p className="text-[12.5px] text-bz-muted mb-1">How {rv.target} would see you</p>
            <blockquote className="font-display text-[18px] sm:text-[20px] leading-snug text-bz-ink">
              <Quote className="inline w-4 h-4 text-bz-teal -mt-2 mr-1" aria-hidden />{rv.client_view}
            </blockquote>
            {rv.verdict && <p className="mt-3 text-[15px] font-semibold">{rv.verdict}</p>}
          </div>
        </div>
        {rv.read?.open_to_work && <p className="mt-4 text-[14px] text-bz-miss font-semibold">Your profile shows “Open to work”. To a client that reads as job hunting, not consulting. Turn it off or set it to recruiters only.</p>}
        {rv.quick_wins?.length > 0 && (
          <div className="mt-5 pt-4 border-t border-bz-line" data-testid="li-quick-wins">
            <p className="text-[13px] font-semibold mb-2">If you only have ten minutes, do these</p>
            <ol className="space-y-1.5 text-[14.5px] list-decimal pl-5">{rv.quick_wins.map((w) => <li key={w}>{w}</li>)}</ol>
          </div>
        )}
      </AiFrame>

      <Card data-testid="li-changes">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label className="mb-0">Your changes, one by one</Label>
          {changes.length > 0 && <span className="text-[13px] text-bz-muted tabular" data-testid="li-changes-progress">{doneN} of {changes.length} done</span>}
        </div>
        {changes.length > 0 ? (
          <>
            <p className="text-[13.5px] text-bz-muted mt-1">Open a change to see what your profile says now and the text to paste. Tick it when it's done on LinkedIn.</p>
            <Meter value={(doneN / changes.length) * 100} className="mt-3" label="Changes done" />
            <ol className="mt-4 space-y-2.5">
              {changes.map((s, i) => (
                <ChangeItem key={s.key} n={i + 1} s={s} rv={rv} done={done.includes(s.key)} onToggle={() => toggle(s.key)}
                  open={open === s.key} onOpen={() => setOpen(open === s.key ? null : s.key)} />
              ))}
            </ol>
          </>
        ) : <p className="text-[14.5px] mt-2">Nothing to change. Your profile already speaks to this client.</p>}
        {(working.length > 0 || unseen.length > 0) && (
          <div className="mt-5 pt-4 border-t border-bz-line grid sm:grid-cols-2 gap-4 text-[14px]">
            {working.length > 0 && (
              <div data-testid="li-working">
                <p className="font-semibold mb-1.5">Already working: leave these</p>
                <ul className="space-y-1">{working.map((s) => <li key={s.key} className="flex gap-1.5"><Check className="w-4 h-4 text-bz-gold shrink-0 mt-0.5" aria-hidden /><span><b className="font-semibold">{s.label}</b>{s.why ? <span className="text-bz-muted">: {s.why}</span> : null}</span></li>)}</ul>
              </div>
            )}
            {unseen.length > 0 && (
              <div data-testid="li-unseen">
                <p className="font-semibold mb-1.5">Not in your screenshots: check these yourself</p>
                <ul className="space-y-1">{unseen.map((s) => <li key={s.key}><b className="font-semibold">{s.label}</b>{s.fix ? <span className="text-bz-muted">: {s.fix}</span> : null}</li>)}</ul>
              </div>
            )}
          </div>
        )}
      </Card>

      <div className="flex flex-col sm:flex-row sm:items-center gap-3">
        {canAgain && <Button variant="secondary" onClick={onAgain} data-testid="li-review-again">Review again with new screenshots</Button>}
        <span className="text-[12.5px] text-bz-muted">Reviewed {hdate(r.at)} from {r.images} screenshot{r.images === 1 ? "" : "s"}</span>
      </div>
    </div>
  );
}

// ============================================================================ 30-day post plan =====
const FORMAT = { text: "Text post", carousel: "Carousel", poll: "Poll", story: "Story", document: "Document", image: "Image post", video: "Short video" };
const WEEKS = [[1, 7], [8, 14], [15, 21], [22, 30]];

function dayLabel(iso) {
  try { return new Date(`${iso}T00:00:00+05:30`).toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short", timeZone: "Asia/Kolkata" }); }
  catch { return iso; }
}

function PostCard({ p, planId, onSaved, today }) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const full = `${p.text}${p.cta ? `\n\n${p.cta}` : ""}`;
  const toggle = async () => {
    setBusy(true);
    try { onSaved((await api.patch(`/linkedin-review/plan/${planId}/posts/${p.day}`, { posted: !p.posted })).data); } catch { /* stays as it was */ } finally { setBusy(false); }
  };
  return (
    <li className={`rounded-bzcard border bg-bz-card p-4 ${p.date === today ? "border-bz-gold ring-1 ring-bz-gold/40" : "border-bz-line"}`} data-testid={`li-post-${p.day}`}>
      <div className="flex items-center justify-between gap-3">
        <p className="text-[13px] font-semibold text-bz-muted tabular">Day {p.day} · {dayLabel(p.date)}{p.date === today ? " · today" : ""}</p>
        <label className="inline-flex items-center gap-2 text-[13.5px] font-semibold cursor-pointer min-h-[36px]">
          <input type="checkbox" checked={!!p.posted} onChange={toggle} disabled={busy} className="w-5 h-5 accent-[rgb(29_78_216)]" data-testid={`li-posted-${p.day}`} />
          Posted
        </label>
      </div>
      <div className="flex flex-wrap gap-1.5 mt-1.5">{p.pillar && <Chip tone="gold">{p.pillar}</Chip>}<Chip>{FORMAT[p.format] || p.format}</Chip></div>
      <p className={`mt-2 text-[15.5px] font-bold ${p.posted ? "text-bz-muted line-through decoration-1" : ""}`}>{p.hook}</p>
      {open ? <div className="mt-2"><Para text={full} className="text-[14.5px]" /></div>
        : <p className="mt-1 text-[14px] text-bz-muted line-clamp-2">{p.text}</p>}
      <div className="mt-2 flex items-center gap-1">
        <button type="button" onClick={() => setOpen((o) => !o)} className="text-[13px] font-bold text-bz-gold min-h-[36px] px-1" aria-expanded={open}>{open ? "Show less" : "Read the post"}</button>
        <span className="flex-1" />
        <CopyBtn text={`${p.hook}\n\n${full}`} />
      </div>
    </li>
  );
}

function PostPlan({ d, usage, review }) {
  const { refreshMe } = useAuth();
  const qc = useQueryClient();
  const [plan, setPlan] = useState(d.plan);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const today = new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
  const firstOpen = plan ? Math.max(0, WEEKS.findIndex(([a, b]) => plan.posts.some((p) => p.day >= a && p.day <= b && p.date >= today))) : 0;
  const [week, setWeek] = useState(String(firstOpen));
  useEffect(() => { setPlan(d.plan); }, [d.plan]);
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const make = async () => {
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/linkedin-review/plan", { review_id: review?.id || null });
      setPlan(data); setWeek("0"); refreshMe(); qc.invalidateQueries({ queryKey: ["li-review"] });
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  if (busy) return <AiFrame title="Planning your month"><Thinking label="Writing 30 posts for your client. This takes one to two minutes." /></AiFrame>;
  if (!plan) {
    return (
      <Card data-testid="li-plan-empty">
        <Label>Your 30-day post plan</Label>
        <p className="text-[15px]">One post a day for 30 days, written for {review?.target || d.target || "your ideal client"}: who you help, how you think, proof from your career, then invitations to talk. Each post is ready to edit and copy.</p>
        <ErrorLine>{err}</ErrorLine>
        <Button variant="ai" className="w-full mt-4" onClick={make} disabled={!canRun} data-testid="li-plan-go">Make my 30-day post plan</Button>
        <UsageLine usage={usage} what="30-day plans" className="mt-2 text-center" />
      </Card>
    );
  }
  const [a, b] = WEEKS[Number(week)] || WEEKS[0];
  const posts = plan.posts.filter((p) => p.day >= a && p.day <= b);
  const done = plan.posts.filter((p) => p.posted).length;
  return (
    <div className="space-y-4" data-testid="li-plan">
      <Card>
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label className="mb-0">Your 30-day post plan</Label>
          <span className="text-[13px] text-bz-muted tabular" data-testid="li-plan-progress">{done} of 30 posted</span>
        </div>
        <Meter value={(done / 30) * 100} className="mt-2" label="Posts done" />
        <div className="mt-4 grid sm:grid-cols-2 gap-3">
          {plan.pillars.map((pl) => (
            <div key={pl.name} className="rounded-bzcard border border-bz-line bg-bz-panel p-3">
              <p className="font-bold text-[14.5px]">{pl.name}</p>{pl.why && <p className="text-[13px] text-bz-muted mt-0.5">{pl.why}</p>}
            </div>
          ))}
        </div>
        {plan.rhythm && <p className="mt-3 text-[14px]"><span className="font-semibold">Your rhythm: </span>{plan.rhythm}</p>}
      </Card>
      <Segmented label="Week" value={week} onChange={setWeek} testid="li-plan-week"
        options={WEEKS.map(([x, y], i) => ({ value: String(i), label: `Week ${i + 1}` }))} />
      <ul className="space-y-3">{posts.map((p) => <PostCard key={p.day} p={p} planId={plan.id} today={today} onSaved={setPlan} />)}</ul>
      <Note>Put your own figures where you see [number]. At most three hashtags. Reply to every comment in the first hour.</Note>
      {canRun && <Button variant="secondary" onClick={make} data-testid="li-plan-again">Make a new plan</Button>}
      <ErrorLine>{err}</ErrorLine>
    </div>
  );
}

export default function LinkedIn() {
  const { plan } = useAuth();
  const q = useQuery({ queryKey: ["li-review"], queryFn: async () => (await api.get("/linkedin-review")).data });
  const [fresh, setFresh] = useState(null);
  const [again, setAgain] = useState(false);
  const [tab, setTab] = useState("review");
  const usage = plan?.limits?.li_review;
  const planUsage = plan?.limits?.li_plan;
  const canAgain = !usage || usage.limit == null || usage.used < usage.limit;
  return (
    <div className="space-y-5">
      <PageHeader kicker="LinkedIn Profile Review" ai title="Make your ideal client think," accent="“this is my person.”"
        sub="Upload screenshots of your LinkedIn profile. We read it the way your ideal client would, show what each section costs you, write what to put instead, and plan 30 days of posts." />
      <Loadable q={q} what="your LinkedIn review">
        {(d) => {
          const review = fresh || d.review;
          return (
            <>
              <Segmented label="Show" value={tab} onChange={setTab} testid="li-tab"
                options={[{ value: "review", label: "Profile review" }, { value: "plan", label: "30-day post plan" }]} />
              {tab === "review" && (
                review && !again
                  ? <ReviewResult r={review} canAgain={canAgain} onAgain={() => setAgain(true)} />
                  : <ReviewForm d={d} usage={usage} onDone={(r) => { setFresh(r); setAgain(false); q.refetch(); }} onCancel={review ? () => setAgain(false) : null} />
              )}
              {tab === "plan" && <PostPlan d={d} usage={planUsage} review={review} />}
            </>
          );
        }}
      </Loadable>
      <details className="group rounded-bzcard border border-bz-line bg-bz-card" data-testid="li-quick">
        <summary className="list-none cursor-pointer px-4 sm:px-5 py-4 flex items-center justify-between gap-3">
          <span><span className="font-bold text-[15px]">No screenshots to hand?</span><span className="block text-[13.5px] text-bz-muted">Paste your headline for a quick score out of 100.</span></span>
          <span className="text-[13px] font-bold text-bz-gold group-open:hidden">Open</span>
        </summary>
        <div className="px-4 sm:px-5 pb-5"><QuickCheck /></div>
      </details>
    </div>
  );
}

function QuickCheck() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["linkedin"], queryFn: async () => (await api.get("/linkedin")).data });
  const [f, setF] = useState({ headline: "", about: "", experience: "" });
  const [fresh, setFresh] = useState(null);
  const [form, setForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.linkedin;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const canRewrite = !!plan?.features?.linkedin_improve;

  const run = async (rewrite) => {
    if (f.headline.trim().length < 5) { setErr("Paste your LinkedIn headline (the line under your name)."); return; }
    setErr(""); setBusy(rewrite ? "rewrite" : "score");
    try {
      const { data } = await api.post("/linkedin/check", { ...f, rewrite });
      setFresh(data); setForm(false);
      qc.invalidateQueries({ queryKey: ["linkedin"] }); qc.invalidateQueries({ queryKey: ["file"] }); refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {busy === "rewrite" ? <AiFrame title="Rewriting"><Thinking label="Writing headlines and an About section around your niche" /></AiFrame> : (
        <Loadable q={q} what="your LinkedIn score">
          {(d) => {
            const latest = fresh || d.latest;
            if (latest && !form) {
              return (
                <div className="space-y-3">
                  <Result r={latest} />
                  <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    {canRun && <Button variant="secondary" onClick={() => { setForm(true); setF(latest.input || f); }} data-testid="linkedin-again">Check again</Button>}
                    <UsageLine usage={usage} what="checks" />
                  </div>
                </div>
              );
            }
            return (
              <Card>
                <div className="space-y-3">
                  <Field label="Headline"><Input value={f.headline} onChange={(e) => setF({ ...f, headline: e.target.value })} placeholder="e.g. General Manager – Operations at ABC Ltd" maxLength={300} data-testid="li-headline" /></Field>
                  <Field label="About section"><Textarea rows={6} value={f.about} onChange={(e) => setF({ ...f, about: e.target.value })} maxLength={3000} placeholder="Paste your About section" data-testid="li-about" /></Field>
                  <Field label="One role from Experience (optional)"><Textarea rows={4} value={f.experience} onChange={(e) => setF({ ...f, experience: e.target.value })} maxLength={3000} placeholder="Paste your latest role and what you did there" /></Field>
                </div>
                <ErrorLine>{err}</ErrorLine>
                <div className="mt-5 flex flex-col sm:flex-row gap-2">
                  <Button className="sm:flex-1" onClick={() => run(false)} loading={busy === "score"} disabled={!canRun || !!busy} data-testid="li-score">Score my profile</Button>
                  {canRewrite && <Button variant="ai" className="sm:flex-1" onClick={() => run(true)} disabled={!canRun || !!busy} data-testid="li-rewrite">Score and rewrite</Button>}
                </div>
                <UsageLine usage={usage} what="checks" className="mt-2 text-center" />
                {latest && <button type="button" onClick={() => setForm(false)} className="mt-1 w-full text-[14px] font-bold text-bz-muted min-h-[44px]">Back to my score</button>}
              </Card>
            );
          }}
        </Loadable>
      )}
    </div>
  );
}
