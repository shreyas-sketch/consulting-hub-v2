// /app/cases/:id — the case, your answer, the AI score on four criteria, then the model answer.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { apiError } from "@/lib/api";
import { useAnswerCase, useCase } from "@/services/cases";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, LockCard, Para, ScoreRing, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, ErrorLine, Label, Loadable, Meter, Note, PageHeader, Textarea, Thinking } from "../components/ui";

function Score({ a, criteria }) {
  return (
    <AiFrame title="Your score" className="rise-in" right={<span className="text-[12px] text-bz-muted">{hdate(a.at)}</span>}>
      <div className="flex flex-col sm:flex-row gap-5 sm:items-center">
        <div className="shrink-0 self-center"><ScoreRing value={a.overall} max={10} size={120} label="Case score" sub="out of 10" ai /></div>
        <div className="flex-1 space-y-2.5">
          {criteria.map((c) => (
            <div key={c.key}>
              <div className="flex justify-between text-[13.5px]"><span>{c.label}</span><span className="font-extrabold tabular text-bz-teal">{a.scores[c.key]}/10</span></div>
              <Meter value={a.scores[c.key] * 10} tone="teal" className="mt-1" label={c.label} />
            </div>
          ))}
        </div>
      </div>
      {a.summary && <p className="mt-4 text-[15px]">{a.summary}</p>}
      <div className="mt-4 grid gap-4 sm:grid-cols-2">
        <div><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-1.5">What worked</p><ul className="space-y-1 text-[14px] list-disc pl-5">{a.good.map((x) => <li key={x}>{x}</li>)}</ul></div>
        <div><p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-1.5">To improve</p><ul className="space-y-1 text-[14px] list-disc pl-5">{a.improve.map((x) => <li key={x}>{x}</li>)}</ul></div>
      </div>
      <details className="mt-4">
        <summary className="cursor-pointer text-[13px] font-bold text-bz-muted min-h-[40px] flex items-center">Your answer</summary>
        <Para text={a.answer} className="text-[14px] text-bz-muted" />
      </details>
    </AiFrame>
  );
}

function Phase({ n, name, children }) {
  return (
    <div className="pt-5 mt-5 border-t border-bz-line first:mt-0 first:pt-0 first:border-0">
      <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">Phase {n} · {name}</p>
      <div className="mt-3 space-y-3">{children}</div>
    </div>
  );
}

function ModelAnswer({ m }) {
  const o = m.objective || {};
  return (
    <Card className="border-bz-rule" data-testid="model-answer">
      <Label>Model answer · Strategic Thinking Framework</Label>
      <Phase n={1} name="Define the problem">
        <p className="text-[14px] text-bz-muted"><b className="text-bz-ink">Before scope:</b> “{m.scope_before}”</p>
        <p className="text-[15px]"><b className="text-bz-gold">After scope:</b> {m.scope_after}</p>
        <div className="grid grid-cols-3 gap-2">
          {[["From", o.from], ["To", o.to], ["In", o.by]].map(([k, v]) => (
            <div key={k} className="rounded-bzcard bg-bz-raised border border-bz-line p-3 min-w-0">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-bz-muted">{k}</p>
              <p className="text-[14px] font-extrabold text-bz-gold mt-1 leading-snug">{v}</p>
            </div>
          ))}
        </div>
        <p className="text-[14px]"><b>Success:</b> {m.success}</p>
        <p className="text-[14px]"><b>Failure:</b> {m.failure}</p>
      </Phase>
      <Phase n={2} name="Craft the strategy">
        <p className="text-[15px]"><b className="text-bz-gold">Framework:</b> {m.framework}</p>
        <p className="text-[14px] text-bz-muted">{m.framework_why}</p>
        <p className="text-[14px]">{m.finding}</p>
        <div className="space-y-2">
          {(m.options || []).map((x) => (
            <div key={x.option} className="flex gap-3 text-[14px]">
              <span className="shrink-0 w-[118px] text-[12px] font-bold text-bz-muted pt-0.5">{x.source}</span>
              <span className="min-w-0">{x.option}</span>
            </div>
          ))}
        </div>
        <p className="text-[15px]"><b className="text-bz-gold">Do first:</b> {m.do_first}</p>
      </Phase>
      <Phase n={3} name="Execute the strategy">
        <div className="grid gap-2 sm:grid-cols-3">
          {[["Owner", m.charter?.owner], ["Leading metric", m.charter?.leading], ["Lagging metric", m.charter?.lagging]].map(([k, v]) => (
            <div key={k} className="rounded-bzcard bg-bz-raised border border-bz-line p-3">
              <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-bz-muted">{k}</p>
              <p className="text-[14px] font-bold mt-1">{v}</p>
            </div>
          ))}
        </div>
      </Phase>
      <p className="mt-5 text-[14px] font-bold text-bz-gold">Same six steps. Every problem. Every time.</p>
    </Card>
  );
}

export default function CaseView() {
  const { id } = useParams();
  const { plan, refreshMe } = useAuth();
  const q = useCase(id);
  const send = useAnswerCase(id, { onDone: refreshMe });
  const busy = send.isPending;
  const [answer, setAnswer] = useState("");
  const [err, setErr] = useState("");
  const [writing, setWriting] = useState(false);
  const usage = plan?.limits?.case;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const submit = async () => {
    if (answer.trim().length < 40) { setErr("Write a little more: at least a few sentences (40 characters)."); return; }
    setErr("");
    try {
      await send.mutateAsync(answer);
      setAnswer(""); setWriting(false);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); }
  };

  if (q.isError && q.error?.response?.status === 403) {
    return <div className="space-y-4"><BackLink to="/app/cases">All cases</BackLink><LockCard feature="case" planNeeded="member" /></div>;
  }
  return (
    <div className="space-y-5">
      <BackLink to="/app/cases">All cases</BackLink>
      <Loadable q={q} what="this case" lines={8}>
        {({ case: c, answers }) => {
          const last = answers?.[0];
          // Free account, case no longer live: read-only (their score and the model answer stay theirs to read).
          const readOnly = !!c.read_only;
          const showForm = !readOnly && (!last || writing);
          return (
            <>
              <PageHeader kicker={c.live ? "Live case" : "Practice case"} title={c.title} sub={`${c.company} · ${c.industry}${c.city ? ` · ${c.city}` : ""}`} />
              <Card>
                <p className="text-[16px] leading-relaxed">{c.situation}</p>
                {c.facts?.length > 0 && (
                  <>
                    <Label className="mt-5">The facts</Label>
                    <ul className="space-y-1.5 text-[15px]">{c.facts.map((f) => <li key={f} className="flex gap-2"><span className="text-bz-gold">•</span>{f}</li>)}</ul>
                  </>
                )}
                <div className="mt-5 rounded-bzcard bg-bz-raised border border-bz-line p-4">
                  <Label className="mb-1">The question</Label>
                  <p className="text-[16px] font-bold leading-relaxed">{c.question}</p>
                </div>
                {c.framework_hint && <p className="mt-3 text-[14px] text-bz-muted"><b className="text-bz-gold">Hint: </b>{c.framework_hint}</p>}
                {c.source?.url && <a href={c.source.url} target="_blank" rel="noopener noreferrer" className="mt-3 inline-block text-[13px] font-bold text-bz-gold">Source: {c.source.title}</a>}
              </Card>

              {busy ? <AiFrame title="Scoring"><Thinking label="Reading your answer" /></AiFrame> : showForm ? (
                <Card>
                  <Label>Your answer</Label>
                  <p className="text-[14px] text-bz-muted mb-3">Use the framework: turn the client's words into one precise problem, set the objective (from → to → by when), pick a framework and options, say what you'd do first, and who owns it and what you'd measure.</p>
                  <Textarea rows={8} value={answer} onChange={(e) => setAnswer(e.target.value)} maxLength={4000} placeholder="The real problem is…" data-testid="case-answer" />
                  <div className="flex justify-between text-[12px] text-bz-muted mt-1"><span>{answer.trim().length < 40 ? "At least 40 characters" : " "}</span><span className="tabular">{answer.length}/4000</span></div>
                  <ErrorLine>{err}</ErrorLine>
                  <Button variant="ai" className="w-full mt-3" onClick={submit} disabled={!canRun} data-testid="case-submit">Score my answer</Button>
                  <UsageLine usage={usage} what="case answers" className="mt-2 text-center" />
                  {last && <button type="button" onClick={() => setWriting(false)} className="mt-1 w-full text-[14px] font-bold text-bz-muted min-h-[44px]">Back to my score</button>}
                </Card>
              ) : !last ? null : (
                <>
                  {readOnly && <Note>The live case has changed. Your score and the model answer stay here for you to read.</Note>}
                  <Score a={last} criteria={c.criteria} />
                  {c.model_answer && <ModelAnswer m={c.model_answer} />}
                  <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                    {canRun && !readOnly && <Button variant="secondary" onClick={() => setWriting(true)} data-testid="case-again">Answer again</Button>}
                    {!readOnly && <UsageLine usage={usage} what="case answers" />}
                    {answers.length > 1 && <Chip>{answers.length} answers so far</Chip>}
                  </div>
                </>
              )}
            </>
          );
        }}
      </Loadable>
    </div>
  );
}
