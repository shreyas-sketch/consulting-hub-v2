// /app/start — Starting Point: Niche Snapshot (EDE, AI) and Goal Map (plain arithmetic). Two tabs, one mode each.
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, X } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { inr } from "@/lib/format";
import { UsageLine } from "../components/common";
import {
  AiFrame, Button, Card, ErrorLine, Field, Input, Label, Loadable, Meter, MoneyInput, Note, PageHeader, Segmented, Stat, Thinking,
} from "../components/ui";

function NicheOption({ o, i, chosen, onChoose, busy }) {
  const bars = [["Experience", o.experience], ["Demand", o.demand], ["Enjoyment", o.enjoyment]];
  return (
    <div className={`rounded-bzcard border p-4 ${chosen ? "border-bz-teal bg-bz-teal-tint" : "border-bz-line bg-bz-panel"}`} data-testid={`niche-${i}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[17px] font-extrabold leading-snug">{o.niche}</p>
        <span className="text-[22px] font-extrabold text-bz-teal tabular shrink-0">{o.total}<span className="text-[13px] text-bz-muted">/30</span></span>
      </div>
      {o.title && <p className="text-[13px] font-bold text-bz-teal mt-0.5">{o.title}</p>}
      {o.value_prop && <p className="text-[14px] mt-2 italic">“{o.value_prop}”</p>}
      <dl className="mt-2 space-y-1 text-[14px]">
        <div><dt className="inline text-bz-muted">Who: </dt><dd className="inline">{o.who}</dd></div>
        <div><dt className="inline text-bz-muted">Problem: </dt><dd className="inline">{o.problem}</dd></div>
        <div><dt className="inline text-bz-muted">Result: </dt><dd className="inline">{o.result}</dd></div>
      </dl>
      <div className="mt-3 grid grid-cols-3 gap-2">
        {bars.map(([n, v]) => (
          <div key={n}>
            <div className="flex justify-between text-[11.5px]"><span className="text-bz-muted">{n}</span><span className="font-bold tabular">{v}</span></div>
            <Meter value={v * 10} tone="teal" className="mt-1 h-1.5" label={n} />
          </div>
        ))}
      </div>
      {o.why && <p className="text-[13px] text-bz-muted mt-3">{o.why}</p>}
      {o.fee_low ? (
        <p className="text-[13px] mt-2"><span className="text-bz-muted">Typical fee: </span><b className="tabular">{inr(o.fee_low)} – {inr(o.fee_high)}</b> per client
          <span className="text-bz-muted"> · 4 clients a month ≈ {inr(o.yearly_low)} – {inr(o.yearly_high)} a year</span></p>
      ) : null}
      {chosen ? <p className="mt-3 text-[13px] font-bold text-bz-teal">Your chosen niche</p>
        : <Button variant="small" className="mt-3" onClick={onChoose} loading={busy} data-testid={`choose-${i}`}>Choose this niche</Button>}
    </div>
  );
}

function Snapshot({ data }) {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const last = data.snapshot;
  const [items, setItems] = useState([{ t: "", e: false }, { t: "", e: false }, { t: "", e: false }]);
  const [industry, setIndustry] = useState("");
  const [years, setYears] = useState(15);
  const [proof, setProof] = useState("");
  const [busy, setBusy] = useState(false);
  const [choosing, setChoosing] = useState(null);
  const [err, setErr] = useState("");
  const [form, setForm] = useState(!last);
  const usage = plan?.limits?.start;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const run = async () => {
    const experiences = items.map((x) => x.t.trim()).filter(Boolean);
    if (!experiences.length) { setErr("Add at least one thing you're experienced in."); return; }
    const enjoy = items.filter((x) => x.t.trim()).map((x, i) => (x.e ? i : -1)).filter((i) => i >= 0);
    setErr(""); setBusy(true);
    try {
      const { data: d } = await api.post("/start/snapshot", { experiences, enjoy, industry, years: Number(years) || 0, proof });
      qc.setQueryData(["start"], (old) => ({ ...(old || {}), snapshot: d }));
      qc.invalidateQueries({ queryKey: ["file"] }); refreshMe(); setForm(false);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  const choose = async (i) => {
    setChoosing(i);
    try {
      const { data: d } = await api.post(`/start/snapshot/${last.id}/choose`, { index: i });
      qc.setQueryData(["start"], (old) => ({ ...(old || {}), snapshot: d })); qc.invalidateQueries({ queryKey: ["file"] });
    } catch (e) { setErr(apiError(e)); } finally { setChoosing(null); }
  };

  if (busy) return <AiFrame title="Niche Snapshot"><Thinking label="Checking your experience against what businesses pay for" /></AiFrame>;
  if (!form && last) {
    return (
      <div className="space-y-3">
        <AiFrame title="Your Niche Snapshot" right={<span className="text-[12px] text-bz-muted">Scored on EDE</span>}>
          <div className="space-y-3">
            {last.options.map((o, i) => <NicheOption key={i} o={o} i={i} chosen={last.chosen === i} onChoose={() => choose(i)} busy={choosing === i} />)}
          </div>
          {last.note && <p className="text-[14px] text-bz-muted mt-4">{last.note}</p>}
          {last.income_note && <p className="text-[12px] text-bz-faint mt-2">Estimates only. {last.income_note}</p>}
        </AiFrame>
        <ErrorLine>{err}</ErrorLine>
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          {canRun && <Button variant="ai" onClick={() => setForm(true)} data-testid="snapshot-again">Try different experience</Button>}
          <UsageLine usage={usage} what="snapshots" />
        </div>
      </div>
    );
  }
  return (
    <Card>
      <p className="text-[15px] text-bz-muted">List up to five things you're experienced in: skills, domains, problems you've solved. Not your job title. Tick the ones you enjoy.</p>
      <div className="mt-4 space-y-2.5">
        {items.map((x, i) => (
          <div key={i} className="flex items-center gap-2">
            <Input value={x.t} placeholder={["e.g. Supply chain for FMCG", "e.g. Building sales teams", "e.g. Cutting costs in plants", "Another strength", "One more"][i]}
              maxLength={80} onChange={(e) => setItems(items.map((y, j) => (j === i ? { ...y, t: e.target.value } : y)))} aria-label={`Experience ${i + 1}`} data-testid={`exp-${i}`} />
            <button type="button" aria-pressed={x.e} onClick={() => setItems(items.map((y, j) => (j === i ? { ...y, e: !y.e } : y)))}
              className={`shrink-0 min-h-[48px] px-3.5 rounded-full border text-[13px] font-bold ${x.e ? "border-bz-teal text-bz-teal bg-bz-teal-tint" : "border-bz-line text-bz-muted"}`}>
              {x.e ? "Enjoy ✓" : "Enjoy?"}
            </button>
            {items.length > 1 && (
              <button type="button" aria-label="Remove" onClick={() => setItems(items.filter((_, j) => j !== i))} className="shrink-0 w-11 h-11 grid place-items-center text-bz-faint hover:text-bz-ink"><X className="w-4 h-4" aria-hidden /></button>
            )}
          </div>
        ))}
        {items.length < 5 && (
          <button type="button" onClick={() => setItems([...items, { t: "", e: false }])} className="inline-flex items-center gap-1.5 text-[14px] font-bold text-bz-teal min-h-[44px]"><Plus className="w-4 h-4" aria-hidden />Add another</button>
        )}
      </div>
      <div className="mt-3 grid gap-3 sm:grid-cols-[1fr_140px]">
        <Field label="Industry you know best"><Input value={industry} onChange={(e) => setIndustry(e.target.value)} placeholder="e.g. Manufacturing" maxLength={80} /></Field>
        <Field label="Years of experience"><Input type="number" inputMode="numeric" value={years} onChange={(e) => setYears(e.target.value)} min={0} max={50} /></Field>
      </div>
      <Field label="Your biggest results (optional)" className="mt-3" hint="Numbers help: revenue grown, costs cut, teams built, projects delivered.">
        <Input value={proof} onChange={(e) => setProof(e.target.value)} placeholder="e.g. Cut plant downtime 30%, led a team of 120" maxLength={300} />
      </Field>
      <ErrorLine>{err}</ErrorLine>
      <Button variant="ai" className="w-full mt-5" onClick={run} disabled={!canRun} data-testid="snapshot-run">Find my niche options</Button>
      <UsageLine usage={usage} what="snapshots" className="mt-2 text-center" />
      {last && <button type="button" onClick={() => setForm(false)} className="mt-2 w-full text-[14px] font-bold text-bz-muted min-h-[44px]">Back to my snapshot</button>}
    </Card>
  );
}

function GoalMap({ data }) {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const g = data.goal;
  const [v, setV] = useState({ monthly_goal_inr: g?.monthly_goal_inr || 300000, fee_inr: g?.fee_inr || 50000, close_rate_pct: 25, calls_per_lead: 3, months: g?.months || 6 });
  const [preview, setPreview] = useState(g || null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState(false);
  const usage = plan?.limits?.goal;
  const canSave = !usage || usage.limit == null || usage.used < usage.limit;
  const valid = Number(v.monthly_goal_inr) >= 10000 && Number(v.fee_inr) >= 5000;

  useEffect(() => {
    if (!valid) return undefined;
    const t = setTimeout(async () => {
      try { setPreview((await api.post("/start/goal/preview", v)).data); } catch { /* keep last */ }
    }, 250);
    return () => clearTimeout(t);
  }, [v, valid]);

  const save = async () => {
    if (!valid) { setErr("Goal must be at least ₹10,000 and fee at least ₹5,000."); return; }
    setErr(""); setOk(false); setBusy(true);
    try {
      await api.put("/start/goal", v);
      setOk(true); qc.invalidateQueries({ queryKey: ["start"] }); qc.invalidateQueries({ queryKey: ["file"] }); refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  const set = (k) => (x) => setV({ ...v, [k]: x });
  return (
    <div className="space-y-4">
      <Card>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Monthly income goal"><MoneyInput value={v.monthly_goal_inr} onChange={set("monthly_goal_inr")} data-testid="goal-income" /></Field>
          <Field label="Fee per client, per month"><MoneyInput value={v.fee_inr} onChange={set("fee_inr")} data-testid="goal-fee" /></Field>
        </div>
        <details className="mt-3">
          <summary className="cursor-pointer text-[14px] font-bold text-bz-gold min-h-[40px] flex items-center">Change the assumptions</summary>
          <div className="grid gap-3 sm:grid-cols-2 mt-2">
            <Field label="Discovery calls that become clients (%)"><Input type="number" inputMode="numeric" value={v.close_rate_pct} onChange={(e) => set("close_rate_pct")(Number(e.target.value))} /></Field>
            <Field label="Conversations for every discovery call"><Input type="number" inputMode="numeric" value={v.calls_per_lead} onChange={(e) => set("calls_per_lead")(Number(e.target.value))} /></Field>
          </div>
        </details>
      </Card>
      {preview && valid && (
        <Card className="rise-in" data-testid="goal-result">
          <Label>Your numbers</Label>
          <p className="text-[15px]">To make <b className="text-bz-gold">{inr(preview.monthly_goal_inr)}</b> a month at <b className="text-bz-gold">{inr(preview.fee_inr)}</b> per client:</p>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4">
            <Stat label="Clients" value={preview.clients_per_month} sub="a month" />
            <Stat label="Discovery calls" value={preview.discovery_calls_per_month} sub="a month" />
            <Stat label="Conversations" value={preview.conversations_per_month} sub="a month" />
            <Stat label="Conversations" value={preview.conversations_per_week} sub="a week" />
          </div>
          <ul className="mt-4 text-[13px] text-bz-muted list-disc pl-5 space-y-0.5">{preview.assumptions.map((a) => <li key={a}>{a}</li>)}</ul>
          <Note className="mt-2">{preview.label}</Note>
        </Card>
      )}
      <ErrorLine>{err}</ErrorLine>
      {ok && <p className="text-sm text-bz-gold font-bold" role="status">Saved to your Consulting File.</p>}
      <Button className="w-full sm:w-auto" onClick={save} loading={busy} disabled={!canSave || busy} data-testid="goal-save">Save my goal</Button>
      <UsageLine usage={usage} what="goal changes" />
    </div>
  );
}

export default function Start() {
  const [params, setParams] = useSearchParams();
  const tab = params.get("tab") === "goal" ? "goal" : "niche";
  const q = useQuery({ queryKey: ["start"], queryFn: async () => (await api.get("/start")).data });
  return (
    <div className="space-y-5">
      <PageHeader kicker="Starting point" ai={tab === "niche"} title={tab === "niche" ? "Find the niche" : "Turn your goal"} accent={tab === "niche" ? "that pays you." : "into weekly numbers."}
        sub={tab === "niche" ? "Your niche sits where your experience, market demand and what you enjoy meet. That's the EDE framework from the webinar." : "How many clients, calls and conversations it takes to reach your income goal."} />
      <Segmented label="Starting point" value={tab} onChange={(t) => setParams(t === "goal" ? { tab: "goal" } : {})} testid="start-tab"
        options={[{ value: "niche", label: "Niche Snapshot" }, { value: "goal", label: "Goal Map" }]} />
      <Loadable q={q} what="your starting point" lines={5}>
        {(d) => (tab === "niche" ? <Snapshot data={d} /> : <GoalMap data={d} />)}
      </Loadable>
    </div>
  );
}
