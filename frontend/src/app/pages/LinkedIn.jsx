// /app/linkedin — paste headline + About (+ experience), get a score out of 100 and the three fixes;
// paid plans can ask for rewrites (3 headlines by angle, About section, 3 post ideas) written around their niche.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { LockCard, Para, ScoreRing, UsageLine } from "../components/common";
import { AiFrame, Button, Card, ErrorLine, Field, Input, Label, Loadable, Meter, PageHeader, Step, Textarea, Thinking } from "../components/ui";

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
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-2">Headline options</p>
          <div className="space-y-2">
            {r.rewrites.headlines.map((h) => (
              <div key={h.text} className="rounded-bzcard border border-bz-line bg-bz-panel p-3 flex items-start gap-2">
                <div className="min-w-0 flex-1"><p className="text-[11px] font-bold text-bz-muted">{h.angle} angle</p><p className="text-[15px] font-bold">{h.text}</p></div>
                <CopyBtn text={h.text} />
              </div>
            ))}
          </div>
          <div className="flex items-center justify-between mt-5 mb-2">
            <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal">About section</p>
            <CopyBtn text={r.rewrites.about} />
          </div>
          <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5"><Para text={r.rewrites.about} className="text-[14.5px]" /></div>
          {r.rewrites.posts?.length > 0 && (
            <>
              <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mt-5 mb-2">Three posts to write next</p>
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

export default function LinkedIn() {
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
      <PageHeader kicker="LinkedIn Score" title="Does your profile say" accent="consultant?"
        sub="Paste your headline and About section. You get a score out of 100 and the three things to fix first. We never log in to your LinkedIn." />
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
