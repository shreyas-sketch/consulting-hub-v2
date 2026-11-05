// /app/readiness — rate yourself 1–10 on six skills, plus your potential; see your score out of 60 and where to start.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { ScoreRing, UsageLine } from "../components/common";
import { Button, Card, ErrorLine, Label, Loadable, Meter, PageHeader, Step } from "../components/ui";

function Slider({ id, label, ask, value, onChange, min = 1, max = 10 }) {
  return (
    <div className="py-3 border-b border-bz-line last:border-0">
      <div className="flex items-baseline justify-between gap-3">
        <label htmlFor={id} className="font-bold text-[15px]">{label}</label>
        <span className="text-[22px] font-display font-[500] text-bz-gold tabular w-8 text-right">{value}</span>
      </div>
      {ask && <p className="text-[13px] text-bz-muted">{ask}</p>}
      <input id={id} type="range" min={min} max={max} step={1} value={value} onChange={(e) => onChange(Number(e.target.value))}
        className="w-full mt-2 h-8 cursor-pointer" data-testid={`slider-${id}`} />
      <div className="flex justify-between text-[11px] text-bz-faint"><span>{min === 0 ? "0" : "1 · never done it"}</span><span>10 · do it for paying clients</span></div>
    </div>
  );
}

function Result({ r }) {
  return (
    <Card className="rise-in" data-testid="readiness-result">
      <div className="flex flex-col sm:flex-row sm:items-center gap-6">
        <ScoreRing value={r.total} max={60} size={150} label="Readiness Score" sub="out of 60" />
        <div className="min-w-0 flex-1">
          <Label className="mb-1">Your readiness</Label>
          <p className="text-[26px] font-display font-[500] leading-tight">{r.band}</p>
          <p className="text-[15px] text-bz-muted mt-1">{r.band_note}</p>
          {r.change != null && <p className="text-[14px] mt-2 font-bold text-bz-gold">{r.change >= 0 ? `Up ${r.change}` : `Down ${-r.change}`} since last time</p>}
          <p className="text-[13px] text-bz-muted mt-2">Your gut check on potential: <b className="text-bz-ink">{r.potential}/10</b>{r.at ? ` · ${hdate(r.at)}` : ""}</p>
        </div>
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        {Object.entries(r.scores).map(([k, v]) => (
          <div key={k}>
            <div className="flex justify-between text-[13.5px]"><span>{SKILL_NAME[k] || k}</span><span className="font-extrabold text-bz-gold tabular">{v}/10</span></div>
            <Meter value={v * 10} className="mt-1" label={SKILL_NAME[k] || k} />
          </div>
        ))}
      </div>
      <div className="mt-6 space-y-4">
        <Label className="mb-0">Start here</Label>
        {r.focus.map((f, i) => <Step key={f.key} n={i + 1} title={`${f.name} (${f.score}/10)`}>{f.next}</Step>)}
      </div>
    </Card>
  );
}

const SKILL_NAME = { diagnosis: "Problem diagnosis", offer: "Offer clarity", acquisition: "Client acquisition", pricing: "Pricing confidence", delivery: "Delivery & frameworks", visibility: "Visibility & authority" };

export default function Readiness() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const skills = useQuery({ queryKey: ["readiness-skills"], queryFn: async () => (await api.get("/readiness/skills")).data, staleTime: Infinity });
  const mine = useQuery({ queryKey: ["readiness"], queryFn: async () => (await api.get("/readiness")).data });
  const [scores, setScores] = useState({ diagnosis: 5, offer: 5, acquisition: 5, pricing: 5, delivery: 5, visibility: 5 });
  const [potential, setPotential] = useState(7);
  const [fresh, setFresh] = useState(null);
  const [retake, setRetake] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.readiness;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const submit = async () => {
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/readiness", { scores, potential });
      setFresh(data); setRetake(false);
      qc.invalidateQueries({ queryKey: ["readiness"] }); qc.invalidateQueries({ queryKey: ["file"] }); refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      <PageHeader kicker="Readiness Score" title="How ready are you" accent="to consult?"
        sub="Rate yourself honestly on the six skills every consultant needs. 1 means you've never done it; 10 means you do it every week for paying clients." />
      <Loadable q={mine} what="your score">
        {(d) => {
          const latest = fresh || d.latest;
          if (latest && !retake) {
            return (
              <div className="space-y-3">
                <Result r={latest} />
                <div className="flex flex-col sm:flex-row sm:items-center gap-3">
                  {canRun && <Button variant="secondary" onClick={() => setRetake(true)} data-testid="readiness-retake">Score again</Button>}
                  <UsageLine usage={usage} what="scores" />
                </div>
              </div>
            );
          }
          return (
            <Card>
              {(skills.data?.skills || []).map((s) => (
                <Slider key={s.key} id={s.key} label={s.name} ask={s.ask} value={scores[s.key]} onChange={(v) => setScores({ ...scores, [s.key]: v })} />
              ))}
              <div className="mt-2 pt-2 border-t border-bz-rule">
                <Slider id="potential" label="Your potential" ask="Gut check: with the right help, how good a consultant could you be?" min={0} value={potential} onChange={setPotential} />
              </div>
              <ErrorLine>{err}</ErrorLine>
              <Button className="w-full mt-4" onClick={submit} loading={busy} disabled={!canRun || busy} data-testid="readiness-submit">See my score</Button>
              <UsageLine usage={usage} what="scores" className="mt-2 text-center" />
            </Card>
          );
        }}
      </Loadable>
    </div>
  );
}
