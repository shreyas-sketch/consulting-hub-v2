// /app/portfolio and /app/portfolio/:id — Portfolio Project: a practice client from your niche walks in (mock client
// meeting), you write your approach with the six steps, the AI scores it and writes a case study (projected outcome)
// and a 60–90 second video script. You record the video here and download it; nothing is uploaded.
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Lock } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, Gate, Para, ScoreRing, UsageLine } from "../components/common";
import { CopyButton } from "../components/Markdown";
import useRecorder from "../components/useRecorder";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Label, Loadable, Meter, Note, PageHeader, RowLink, Step, Textarea, Thinking } from "../components/ui";
import { RecorderBox } from "./Pitch";

const HEADER = <PageHeader kicker="Portfolio Project" title="Practise on a client," accent="show how you think." />;
const FIELDS = [
  ["scope", "1 · Scope", "Turn the client's words into one precise problem: where, which product or team, which channel, since when."],
  ["objective", "2 · Objective", "From → to → by when, with numbers. What counts as success, and as failure."],
  ["framework_options", "3–4 · Framework and options", "The lens you'd use and why it fits. Then your options: same industry, adjacent industry, customers, something bold."],
  ["do_first", "5 · Do first", "Which option first, and why: high benefit and easy to do."],
  ["owner_metrics", "6 · Owner and metrics", "Who owns it, the first action, one number to track every week and one every month."],
];
const SCRIPT = [["hook", "Hook"], ["problem", "Problem"], ["approach", "Approach"], ["result", "Projected result"], ["call_to_action", "Call to action"]];
const STATUS = { brief: "Write your approach", answered: "Get your feedback", done: "Done" };

function Brief({ p }) {
  const b = p.brief;
  return (
    <Card className="border-bz-rule" data-testid="portfolio-brief">
      <div className="flex items-center justify-between gap-3">
        <Label className="mb-0">A client walks in</Label>
        <Chip>Practice client</Chip>
      </div>
      <p className="mt-3 text-[22px] font-extrabold leading-tight">{b.company}</p>
      <p className="text-[14px] text-bz-muted mt-1">{b.company_type} · {b.size} · {b.city} · {b.years} years</p>
      <p className="text-[15px] mt-3"><b>{b.decision_maker_name}</b>, {b.decision_maker_title}</p>
      {b.how_found ? <p className="text-[14px] text-bz-muted mt-1">{b.how_found}</p> : null}
      <blockquote className="mt-4 border-l-[3px] border-bz-gold pl-4 text-[16px] leading-relaxed italic">“{b.client_words}”</blockquote>
    </Card>
  );
}

function AnswerForm({ p, onDone }) {
  const { refreshMe } = useAuth();
  const [f, setF] = useState(() => Object.fromEntries(FIELDS.map(([k]) => [k, p.answer?.[k] || ""])));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async () => {
    const short = FIELDS.find(([k]) => f[k].trim().length < 10);
    if (short) { setErr(`Write a little more under "${short[1].replace(/^[\d–\s·]+/, "")}" (at least 10 characters).`); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post(`/portfolio/${p.id}/answer`, f);
      refreshMe(); onDone(data);
    } catch (e) {
      if (e?.response?.status === 503) onDone(null);
      if (![402, 403].includes(e?.response?.status)) setErr(apiError(e));
    } finally { setBusy(false); }
  };
  if (busy) return <AiFrame title="Case coach"><Thinking label="Reading your approach and writing your case study" /><Note>About a minute.</Note></AiFrame>;
  return (
    <Card>
      <Label>Your approach</Label>
      <p className="text-[14px] text-bz-muted mb-4">Use the six steps of the Strategic Thinking Framework. Short and specific beats long.</p>
      <div className="space-y-4">
        {FIELDS.map(([k, label, hint]) => (
          <Field key={k} label={label} hint={hint}>
            <Textarea rows={3} value={f[k]} onChange={(e) => setF({ ...f, [k]: e.target.value })} maxLength={k === "framework_options" ? 2500 : 1500} data-testid={`portfolio-${k}`} />
          </Field>
        ))}
      </div>
      <ErrorLine>{err}</ErrorLine>
      <Button variant="ai" className="w-full mt-4" onClick={submit} data-testid="portfolio-submit">Get my feedback</Button>
    </Card>
  );
}

function Feedback({ p }) {
  const r = p.review;
  return (
    <AiFrame title="Your score" className="rise-in">
      <div className="flex flex-col sm:flex-row gap-5 sm:items-center">
        <div className="shrink-0 self-center"><ScoreRing value={r.overall} max={10} size={120} label="Project score" sub="out of 10" ai /></div>
        <div className="flex-1 space-y-2.5">
          {p.criteria.map((c) => (
            <div key={c.key}>
              <div className="flex justify-between text-[13.5px]"><span>{c.label}</span><span className="font-extrabold tabular text-bz-teal">{r.scores[c.key]}/10</span></div>
              <Meter value={r.scores[c.key] * 10} tone="teal" className="mt-1" label={c.label} />
            </div>
          ))}
        </div>
      </div>
      {r.summary ? <p className="mt-4 text-[15px]">{r.summary}</p> : null}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-1.5">What worked</p><ul className="space-y-1 text-[14px] list-disc pl-5">{r.good.map((x) => <li key={x}>{x}</li>)}</ul></div>
        <div><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-1.5">To improve</p><ul className="space-y-1 text-[14px] list-disc pl-5">{r.improve.map((x) => <li key={x}>{x}</li>)}</ul></div>
      </div>
    </AiFrame>
  );
}

function CaseStudy({ p }) {
  const c = p.review.case_study;
  return (
    <Card className="print-plain border-bz-rule" data-testid="portfolio-case-study">
      <Label>Case study · sample engagement</Label>
      <h2 className="text-[24px] sm:text-[28px] font-extrabold leading-tight tracking-[-0.01em]">{c.title}</h2>
      <p className="text-[15px] text-bz-muted mt-2 leading-relaxed">{c.client_context}</p>
      <div className="mt-5">
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-1.5">The challenge</p>
        <p className="text-[15.5px] leading-relaxed">{c.challenge}</p>
      </div>
      <div className="mt-5">
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-3">The approach</p>
        <div className="space-y-3.5">{c.approach.map((s) => <Step key={s.step} n={s.step} title={s.name}>{s.text}</Step>)}</div>
      </div>
      <div className="mt-5 rounded-bzcard border border-bz-line bg-bz-raised p-4">
        <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-1">Projected outcome</p>
        <p className="text-[15.5px] leading-relaxed">{c.expected_outcome}</p>
        <p className="text-[12.5px] text-bz-muted mt-2">{p.outcome_label}</p>
      </div>
      {c.lessons?.length ? (
        <div className="mt-5">
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-1.5">Lessons</p>
          <ul className="space-y-1.5 text-[15px]">{c.lessons.map((x) => <li key={x} className="flex gap-2"><span className="text-bz-gold" aria-hidden>•</span>{x}</li>)}</ul>
        </div>
      ) : null}
      <p className="mt-5 text-[13px] text-bz-muted">{p.practice_note}</p>
    </Card>
  );
}

function ScriptAndVideo({ p }) {
  const s = p.review.video_script;
  const rec = useRecorder({ video: true, maxSeconds: 120 });
  const full = SCRIPT.map(([k]) => s[k]).join("\n\n");
  return (
    <>
      <AiFrame title="Your 60–90 second video script" className="no-print" right={<CopyButton text={full} label="Copy script" />}>
        <p className="text-[13px] text-bz-muted mb-3">About {p.review.script_seconds} seconds spoken. Read it twice, then say it in your own words.</p>
        <div className="space-y-3" data-testid="portfolio-script">
          {SCRIPT.map(([k, label]) => (
            <div key={k}>
              <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal">{label}</p>
              <Para text={s[k]} className="text-[15.5px] mt-0.5" />
            </div>
          ))}
        </div>
      </AiFrame>
      <Card className="no-print">
        <Label>Record your video</Label>
        <p className="text-[14px] text-bz-muted mb-3">Look at the lens, keep it under 90 seconds, then download it and post it on LinkedIn.</p>
        <RecorderBox rec={rec} testid="portfolio-rec">
          {(r) => (
            <a href={r.url} download={`portfolio-video.${r.ext || "webm"}`} data-testid="portfolio-download"
              className="inline-flex items-center justify-center gap-2 rounded-full min-h-[52px] px-6 py-3 bg-bz-gold text-bz-on-accent font-extrabold text-[16px] hover:opacity-90 shadow-goldglow">
              <Download className="w-4 h-4" aria-hidden />Download my video
            </a>
          )}
        </RecorderBox>
        <p className="mt-3 text-[13px] text-bz-muted inline-flex items-center gap-1.5"><Lock className="w-3.5 h-3.5" aria-hidden />Nothing is uploaded. The video stays on your device.</p>
      </Card>
    </>
  );
}

function Project({ id }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["portfolio", id], queryFn: async () => (await api.get(`/portfolio/${id}`)).data });
  const [busyMsg, setBusyMsg] = useState("");
  useEffect(() => { setBusyMsg(""); }, [id]);
  const onDone = (data) => {
    if (data) { qc.setQueryData(["portfolio", id], data); setBusyMsg(""); } else { q.refetch(); setBusyMsg("Your approach is saved. Press Get my feedback to try again."); }
    qc.invalidateQueries({ queryKey: ["portfolio-list"] }); qc.invalidateQueries({ queryKey: ["file"] });
  };
  return (
    <div className="space-y-5">
      <BackLink to="/app/portfolio">All projects</BackLink>
      <Loadable q={q} what="this project" lines={8}>
        {(p) => (
          <>
            <div className="no-print">
              <PageHeader kicker="Portfolio Project" title={p.review?.case_study?.title || p.brief.company} sub={`Started ${hdate(p.at)}`} />
            </div>
            <div className="no-print flex flex-wrap gap-2">
              {["Meet the client", "Your approach", "Feedback and case study", "Your video"].map((x, i) => {
                const doneUpTo = p.status === "done" ? 4 : p.status === "answered" ? 2 : 1;
                return <Chip key={x} tone={i < doneUpTo ? "gold" : "muted"}>{i + 1} · {x}</Chip>;
              })}
            </div>
            <div className="no-print"><Brief p={p} /></div>
            {p.status !== "done" ? (
              <>
                {busyMsg ? <Note>{busyMsg}</Note> : null}
                <AnswerForm key={p.status} p={p} onDone={onDone} />
              </>
            ) : (
              <>
                <div className="no-print"><Feedback p={p} /></div>
                <CaseStudy p={p} />
                <Button variant="secondary" className="no-print" onClick={() => window.print()} data-testid="portfolio-print">Print or save the case study</Button>
                <ScriptAndVideo p={p} />
                <details className="no-print">
                  <summary className="cursor-pointer text-[13px] font-bold text-bz-muted min-h-[40px] flex items-center">Your approach as you wrote it</summary>
                  <div className="space-y-2 mt-2">{FIELDS.map(([k, label]) => <p key={k} className="text-[14px]"><b>{label}:</b> <span className="text-bz-muted">{p.answer?.[k]}</span></p>)}</div>
                </details>
              </>
            )}
          </>
        )}
      </Loadable>
    </div>
  );
}

function List() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const { plan, refreshMe } = useAuth();
  const q = useQuery({ queryKey: ["portfolio-list"], queryFn: async () => (await api.get("/portfolio")).data });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.portfolio;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const start = async () => {
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/portfolio");
      qc.setQueryData(["portfolio", data.id], data); qc.invalidateQueries({ queryKey: ["portfolio-list"] }); refreshMe();
      nav(`/app/portfolio/${data.id}`);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-5">
      <PageHeader kicker="Portfolio Project" title="Practise on a client," accent="show how you think."
        sub="A practice client from your niche tells you their problem. You write your approach. You get a score, a case study you can show, and a short video script to record." />
      {busy ? <AiFrame title="Portfolio Project"><Thinking label="Finding a client from your niche" /></AiFrame> : (
        <Card>
          <div className="space-y-3">
            <Step n={1} title="Meet the client">A made-up company from your niche, in their own vague words.</Step>
            <Step n={2} title="Write your approach">The six steps: scope, objective, framework and options, do first, owner and metrics.</Step>
            <Step n={3} title="Get feedback and a case study">Scored out of 10, plus a case study and a 60–90 second video script.</Step>
            <Step n={4} title="Record your video">On this screen. Download it and post it. Nothing is uploaded.</Step>
          </div>
          <ErrorLine>{err}</ErrorLine>
          <Button variant="ai" className="w-full mt-4" onClick={start} disabled={!canRun} data-testid="portfolio-start">Bring me a client</Button>
          <UsageLine usage={usage} what="portfolio projects" className="mt-2 text-center" />
        </Card>
      )}
      <Loadable q={q} what="your projects">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your projects</Label>
            {d.items.map((x) => (
              <RowLink key={x.id} to={`/app/portfolio/${x.id}`} title={x.title} testid={`portfolio-${x.id}`}
                sub={`${x.city ? `${x.city} · ` : ""}${hdate(x.at)}`}
                right={x.status === "done" ? <Chip tone="gold">{x.overall}/10</Chip> : <Chip>{STATUS[x.status]}</Chip>} />
            ))}
          </Card>
        ) : <Empty title="No projects yet" sub="Your first one takes about twenty minutes." />}
      </Loadable>
    </div>
  );
}

export default function Portfolio() {
  const { id } = useParams();
  return <Gate feature="portfolio" header={HEADER}>{id ? <Project id={id} /> : <List />}</Gate>;
}
