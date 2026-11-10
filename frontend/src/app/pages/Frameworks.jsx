// /app/frameworks and /app/frameworks/:id — Work along with Akshat. The three frameworks from the live workshop
// (1 Nov 2026) as hands-on cases: learn the framework, do the exercise yourself, Save (appears once the exercise is
// complete), see how Akshat read it, then Generate a Proposal for that client.
import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { Check, ChevronRight, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { inr } from "@/lib/format";
import { useFramework, useFrameworkProposal, useFrameworks, useSaveFramework } from "@/services/frameworks";
import Markdown, { CopyButton } from "../components/Markdown";
import { BackLink, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, Note, PageHeader, Segmented, Textarea, Thinking } from "../components/ui";

const ZONE_TONE = { green: "text-[#0f7a3d] bg-[#e7f6ec]", orange: "text-[#a35200] bg-[#fdf0e1]", red: "text-bz-miss bg-bz-miss-tint" };
const zoneFor = (p) => (p <= 20 ? "green" : p <= 40 ? "orange" : "red");
const words = (s) => (s || "").trim().length;

// ============================================================================ the list (also shown on Cases) ====
export function FrameworkList({ compact = false }) {
  const q = useFrameworks();
  return (
    <Loadable q={q} what="the frameworks" lines={3}>
      {(d) => (
        <ol className="divide-y divide-bz-line" data-testid="fw-list">
          {d.items.map((f) => (
            <li key={f.key}>
              <Link to={`/app/frameworks/${f.key}`} data-testid={`fw-${f.key}`}
                className="flex items-start gap-3 py-3.5 -mx-4 px-4 sm:-mx-5 sm:px-5 hover:bg-bz-raised">
                <span className="font-display w-9 h-9 shrink-0 rounded-full grid place-items-center text-[17px] border border-bz-rule text-bz-gold tabular">{f.n}</span>
                <span className="min-w-0 flex-1">
                  <span className="block text-[16px] font-bold">{f.name}</span>
                  <span className="block text-[13.5px] text-bz-muted">{compact ? f.question : `${f.question} · Case: ${f.case}`}</span>
                  <span className="flex flex-wrap gap-1.5 mt-1.5">
                    {f.saved ? <Chip tone={f.score === f.out_of ? "gold" : "muted"}>Saved · {f.score} of {f.out_of}</Chip> : <Chip>Not started</Chip>}
                    {f.proposal && <Chip tone="teal">Proposal ready</Chip>}
                  </span>
                </span>
                <ChevronRight className="w-4 h-4 mt-2 text-bz-faint shrink-0" aria-hidden />
              </Link>
            </li>
          ))}
        </ol>
      )}
    </Loadable>
  );
}

// ============================================================================ framework 1: the Venn ====
function Venn({ fw, value }) {
  const pos = { price: [118, 98], value: [202, 98], availability: [160, 170] };
  const all = fw.structure.every((c) => value[c.key]?.verdict === "works");
  return (
    <svg viewBox="0 0 320 262" className="w-full max-w-[360px] mx-auto" role="img"
      aria-label={`Venn diagram: ${fw.structure.map((c) => `${c.name} ${value[c.key]?.verdict || "not marked"}`).join(", ")}`}>
      {fw.structure.map((c) => {
        const v = value[c.key]?.verdict;
        const [x, y] = pos[c.key];
        return (
          <g key={c.key}>
            <circle cx={x} cy={y} r="78" style={{
              fill: v === "works" ? "rgb(var(--bz-gold-rgb) / 0.16)" : v === "fails" ? "rgb(var(--bz-miss-rgb) / 0.10)" : "rgb(var(--bz-line-rgb) / 0.25)",
              stroke: v === "works" ? "rgb(var(--bz-gold-rgb))" : v === "fails" ? "rgb(var(--bz-miss-rgb))" : "rgb(var(--bz-line-strong-rgb))",
              strokeWidth: 2, strokeDasharray: v === "fails" ? "6 5" : "none" }} />
            <text x={x + (c.key === "price" ? -30 : c.key === "value" ? 30 : 0)} y={y + (c.key === "availability" ? 40 : -22)}
              textAnchor="middle" style={{ fill: "rgb(var(--bz-ink-rgb))", fontSize: 14, fontWeight: 700 }}>{c.name}</text>
            {v && (
              <text x={x + (c.key === "price" ? -30 : c.key === "value" ? 30 : 0)} y={y + (c.key === "availability" ? 58 : -4)} textAnchor="middle"
                style={{ fill: v === "works" ? "rgb(var(--bz-gold-rgb))" : "rgb(var(--bz-miss-rgb))", fontSize: 12, fontWeight: 700 }}>
                {v === "works" ? "works" : "fails"}
              </text>
            )}
          </g>
        );
      })}
      <text x="160" y="124" textAnchor="middle" style={{ fill: all ? "rgb(var(--bz-gold-rgb))" : "rgb(var(--bz-faint-rgb, 135 148 168))", fontSize: 12, fontWeight: 700 }}>
        {all ? "Fits the region" : "Overlap?"}
      </text>
    </svg>
  );
}

function MarketFit({ fw, a, set }) {
  const circles = a.circles || {};
  const setC = (k, patch) => set({ ...a, circles: { ...circles, [k]: { ...circles[k], ...patch } } });
  return (
    <div className="space-y-5">
      <Venn fw={fw} value={circles} />
      {fw.structure.map((c) => (
        <div key={c.key} className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5" data-testid={`fw-circle-${c.key}`}>
          <p className="font-bold text-[15px]">{c.name}</p>
          <p className="text-[13.5px] text-bz-muted">{c.ask}</p>
          <Segmented label={`${c.name}: works or fails`} className="mt-2" value={circles[c.key]?.verdict || ""} testid={`fw-${c.key}`}
            onChange={(v) => setC(c.key, { verdict: v })}
            options={[{ value: "works", label: "Works for Nokia" }, { value: "fails", label: "Fails for Nokia" }]} />
          <Textarea rows={2} className="mt-2" value={circles[c.key]?.why || ""} maxLength={400} placeholder="Why? One sentence."
            onChange={(e) => setC(c.key, { why: e.target.value })} aria-label={`${c.name}: why`} data-testid={`fw-${c.key}-why`} />
        </div>
      ))}
      <Field label="Your diagnosis: why did Nokia fail in India?">
        <Textarea rows={3} value={a.summary || ""} maxLength={800} onChange={(e) => set({ ...a, summary: e.target.value })}
          placeholder="In a sentence or two, as you'd tell the client." data-testid="fw-summary" />
      </Field>
    </div>
  );
}
const marketFitDone = (a) => ["price", "value", "availability"].every((k) => a.circles?.[k]?.verdict && words(a.circles[k].why) >= 10)
  && words(a.summary) >= 20;

// ============================================================================ framework 2: concentration ====
function Concentration({ fw, a, set }) {
  const { sources, total } = fw.case;
  const pc = a.percents || ["", "", ""];
  const setP = (i, v) => set({ ...a, percents: pc.map((x, j) => (j === i ? v : x)) });
  return (
    <div className="space-y-5">
      <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5 text-[14px]">
        <span className="font-semibold">Formula: </span>{fw.formula}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-[14px] min-w-[460px]" data-testid="fw-table">
          <thead><tr className="text-left text-bz-muted text-[12.5px]"><th className="py-2 font-semibold">Revenue source</th><th className="py-2 font-semibold text-right">Revenue</th><th className="py-2 font-semibold text-right w-[120px]">Your %</th><th className="py-2 font-semibold text-right w-[90px]">Zone</th></tr></thead>
          <tbody>
            {sources.map((s, i) => {
              const v = parseFloat(pc[i]);
              const z = Number.isFinite(v) ? zoneFor(v) : null;
              return (
                <tr key={s.name} className="border-t border-bz-line">
                  <td className="py-2.5 pr-2">{s.name}</td>
                  <td className="py-2.5 text-right tabular">{inr(s.amount)}</td>
                  <td className="py-2.5 text-right">
                    <Input type="number" inputMode="decimal" min={0} max={100} step="0.1" value={pc[i]} onChange={(e) => setP(i, e.target.value)}
                      className="!min-h-[40px] text-right w-[100px] ml-auto" aria-label={`${s.name}: concentration %`} data-testid={`fw-pct-${i}`} />
                  </td>
                  <td className="py-2.5 text-right">{z ? <span className={`text-[12px] font-bold px-2 py-[3px] rounded-bztag ${ZONE_TONE[z]}`}>{z}</span> : <span className="text-bz-faint">–</span>}</td>
                </tr>
              );
            })}
            <tr className="border-t border-bz-line-strong font-semibold"><td className="py-2.5">Total revenue</td><td className="py-2.5 text-right tabular">{inr(total)}</td><td className="py-2.5 text-right tabular text-bz-muted">{pc.reduce((t, x) => t + (parseFloat(x) || 0), 0)}%</td><td /></tr>
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2 text-[12.5px]">
        {fw.zones.map((z) => <span key={z.key} className={`px-2 py-1 rounded-bztag ${ZONE_TONE[z.key]}`}><b className="capitalize">{z.key}</b> {z.range}</span>)}
      </div>
      <div>
        <p className="text-[14px] font-semibold mb-2">Your recommendation to the founder</p>
        <Segmented label="Expand now or wait" value={a.recommendation || ""} onChange={(v) => set({ ...a, recommendation: v })} testid="fw-rec"
          options={[{ value: "expand", label: "Expand to Mumbai now" }, { value: "wait", label: "Wait" }]} />
      </div>
      <Field label="Why? Tell him in a sentence or two.">
        <Textarea rows={3} value={a.reason || ""} maxLength={800} onChange={(e) => set({ ...a, reason: e.target.value })} data-testid="fw-reason" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Bring the biggest source down to (%)"><Input type="number" inputMode="numeric" min={5} max={60} value={a.target_pct ?? ""} onChange={(e) => set({ ...a, target_pct: e.target.value })} data-testid="fw-target" /></Field>
        <Field label="Within (months)"><Input type="number" inputMode="numeric" min={1} max={36} value={a.months ?? ""} onChange={(e) => set({ ...a, months: e.target.value })} data-testid="fw-months" /></Field>
      </div>
    </div>
  );
}
const concentrationDone = (a) => (a.percents || []).length === 3 && a.percents.every((x) => x !== "" && Number.isFinite(parseFloat(x)))
  && a.recommendation && words(a.reason) >= 20 && Number(a.target_pct) >= 5 && Number(a.months) >= 1;

// ============================================================================ framework 3: the compass ====
function Compass({ fw, a, set }) {
  const byZone = Object.fromEntries(fw.zones.map((z) => [z.zone, z]));
  const cell = (n) => {
    const z = byZone[n];
    const on = Number(a.zone) === n;
    return (
      <button type="button" onClick={() => set({ ...a, zone: n })} aria-pressed={on} data-testid={`fw-zone-${n}`}
        className={`min-h-[96px] p-3 text-left rounded-bzbtn border transition-colors ${on ? "bg-bz-gold text-bz-on-accent border-bz-gold" : "bg-bz-card border-bz-line hover:border-bz-gold"}`}>
        <span className="block font-display text-[20px] leading-none">Zone {n}</span>
        <span className={`block text-[12.5px] mt-1 ${on ? "text-bz-on-accent/85" : "text-bz-muted"}`}>{z.direction}: {z.reach} reach, {z.conversion} conversion</span>
      </button>
    );
  };
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3"><p className="text-[12.5px] text-bz-muted">Reach</p><p className="font-display text-[26px] tabular">{fw.case.reach_per_month}<span className="text-[13px] text-bz-muted"> a month</span></p></div>
        <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3"><p className="text-[12.5px] text-bz-muted">Conversion</p><p className="font-display text-[26px] tabular">{fw.case.conversion_pct}%<span className="text-[13px] text-bz-muted"> a month</span></p></div>
      </div>
      <div>
        <p className="text-[14px] font-semibold mb-2">Where is she on the compass? Tap a zone.</p>
        <div className="text-center text-[12px] font-semibold text-bz-muted">North · high reach</div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-bz-muted [writing-mode:vertical-rl] rotate-180">West · low conversion</span>
          <div className="grid grid-cols-2 gap-2 flex-1" data-testid="fw-compass">{cell(2)}{cell(1)}{cell(4)}{cell(3)}</div>
          <span className="text-[12px] font-semibold text-bz-muted [writing-mode:vertical-rl]">East · high conversion</span>
        </div>
        <div className="text-center text-[12px] font-semibold text-bz-muted mt-1">South · low reach</div>
      </div>
      <div>
        <p className="text-[14px] font-semibold mb-2">What should she work on?</p>
        <Segmented label="What to fix" value={a.fix || ""} onChange={(v) => set({ ...a, fix: v })} testid="fw-fix"
          options={[{ value: "scale", label: "Keep going, scale" }, { value: "offer", label: "Fix the offer" }, { value: "reach", label: "Fix the reach" }, { value: "both", label: "Both" }]} />
      </div>
      <div className="space-y-2">
        <p className="text-[14px] font-semibold">Three actions for her next 90 days</p>
        {[0, 1, 2].map((i) => (
          <Input key={i} value={(a.actions || [])[i] || ""} maxLength={240} placeholder={`Action ${i + 1}`} aria-label={`Action ${i + 1}`} data-testid={`fw-action-${i}`}
            onChange={(e) => { const acts = [...(a.actions || ["", "", ""])]; acts[i] = e.target.value; set({ ...a, actions: acts }); }} />
        ))}
      </div>
    </div>
  );
}
const compassDone = (a) => Number(a.zone) >= 1 && a.fix && [0, 1, 2].every((i) => words((a.actions || [])[i]) >= 8);

const ACTIVITY = {
  "market-fit": { El: MarketFit, done: marketFitDone, blank: { circles: {}, summary: "" } },
  "concentration-risk": { El: Concentration, done: concentrationDone, blank: { percents: ["", "", ""], recommendation: "", reason: "", target_pct: "", months: "" } },
  "growth-compass": { El: Compass, done: compassDone, blank: { zone: 0, fix: "", actions: ["", "", ""] } },
};
const toPayload = (key, a) => (key === "concentration-risk"
  ? { ...a, percents: a.percents.map((x) => parseFloat(x)), target_pct: Number(a.target_pct), months: Number(a.months) }
  : key === "growth-compass" ? { ...a, zone: Number(a.zone) } : a);

// ============================================================================ the framework itself ====
function Learn({ fw }) {
  return (
    <Card>
      <Label>How the framework works</Label>
      <p className="text-[15px]">{fw.when}</p>
      {fw.structure && (
        <ul className="mt-3 space-y-2">{fw.structure.map((c) => <li key={c.key} className="text-[14.5px]"><b>{c.name}.</b> {c.ask}</li>)}</ul>
      )}
      {fw.dimensions && (
        <ul className="mt-3 space-y-2">{fw.dimensions.map((d) => <li key={d.key} className="text-[14.5px]"><b>{d.name}.</b> {d.meaning}</li>)}</ul>
      )}
      {fw.key === "concentration-risk" && (
        <ul className="mt-3 space-y-2">{fw.zones.map((z) => <li key={z.key} className="text-[14.5px]"><span className={`text-[12px] font-bold px-2 py-[3px] rounded-bztag mr-1.5 ${ZONE_TONE[z.key]}`}>{z.key}</span><b>{z.range}.</b> {z.meaning}</li>)}</ul>
      )}
      {fw.key === "growth-compass" && (
        <ul className="mt-3 space-y-2">{fw.zones.map((z) => <li key={z.zone} className="text-[14.5px]"><b>Zone {z.zone} ({z.direction}).</b> {z.meaning}</li>)}</ul>
      )}
      {fw.rule && <p className="mt-3 text-[14.5px] text-bz-muted">{fw.rule}</p>}
      {fw.example && (
        <div className="mt-4 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
          <p className="text-[13px] font-semibold text-bz-gold">Akshat's example: {fw.example.title}</p>
          <ul className="mt-2 space-y-1.5 text-[14px]">{fw.example.points.map(([k, v]) => <li key={k}><b>{k}:</b> {v}</li>)}</ul>
          <p className="mt-2 text-[14px] font-semibold">{fw.example.verdict}</p>
        </div>
      )}
    </Card>
  );
}

function Marking({ mine, akshat }) {
  const g = mine.grade;
  return (
    <Card className="rise-in" data-testid="fw-marking">
      <div className="flex items-baseline justify-between gap-3">
        <Label className="mb-0">Your reading against Akshat's</Label>
        <span className="font-display text-[22px] tabular text-bz-gold" data-testid="fw-score">{g.score} of {g.out_of}</span>
      </div>
      <ul className="mt-3 divide-y divide-bz-line">
        {g.marks.map((m) => (
          <li key={m.label} className="py-2.5 flex items-start gap-2.5 text-[14px]">
            {m.ok ? <Check className="w-4 h-4 mt-0.5 text-bz-gold shrink-0" aria-label="Matches" /> : <X className="w-4 h-4 mt-0.5 text-bz-miss shrink-0" aria-label="Doesn't match" />}
            <span className="min-w-0"><b>{m.label}.</b> You: {m.yours}{!m.ok && <> · Akshat: <b>{m.right}</b></>}</span>
          </li>
        ))}
      </ul>
      <div className="mt-3 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
        <p className="text-[13px] font-semibold text-bz-gold">How Akshat read this case</p>
        <p className="text-[14.5px] mt-1">{akshat.read}</p>
      </div>
    </Card>
  );
}

function Proposal({ fkey, mine }) {
  const { plan, refreshMe } = useAuth();
  const usage = plan?.limits?.fw_proposal;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const [err, setErr] = useState("");
  const gen = useFrameworkProposal(fkey, { onDone: () => refreshMe() });
  const p = mine.proposal;
  const run = () => { setErr(""); gen.mutate(undefined, { onError: (e) => { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } }); };
  if (gen.isPending) return <AiFrame title="Writing your proposal"><Thinking label="Turning your analysis into a client proposal. This takes about half a minute." /></AiFrame>;
  if (!p) {
    return (
      <Card className="rise-in" data-testid="fw-proposal-cta">
        <Label>Your proposal</Label>
        <p className="text-[15px]">Turn your analysis into a proposal this client could say yes to: the situation, what the framework shows, the objective, a phased plan, deliverables, fee and next steps.</p>
        <ErrorLine>{err}</ErrorLine>
        <Button variant="ai" className="w-full mt-4" onClick={run} disabled={!canRun} data-testid="fw-proposal-go">Generate a Proposal</Button>
        <UsageLine usage={usage} what="framework proposals" className="mt-2 text-center" />
      </Card>
    );
  }
  return (
    <div className="space-y-3">
      <AiFrame title="Your proposal" className="print-plain rise-in" right={<CopyButton text={p.markdown} />}>
        <div data-testid="fw-proposal"><Markdown text={p.markdown} /></div>
        {p.stale && <Note className="mt-3">Made from your earlier answer. Generate again to use what you saved last.</Note>}
        <p className="text-[12px] text-bz-muted mt-3">A practice proposal for a workshop case. Check the numbers and fill in anything in [brackets] before you use it with a real client.</p>
      </AiFrame>
      <div className="flex flex-col sm:flex-row gap-2 no-print">
        <Button variant="secondary" onClick={() => window.print()} data-testid="fw-print">Print or save as PDF</Button>
        {canRun && <Button variant="secondary" onClick={run} data-testid="fw-proposal-again">Generate again</Button>}
        <UsageLine usage={usage} what="framework proposals" className="sm:ml-auto self-center" />
      </div>
      <ErrorLine>{err}</ErrorLine>
    </div>
  );
}

function Activity({ d }) {
  const fw = d.framework;
  const { El, done, blank } = ACTIVITY[fw.key];
  const saved = d.mine?.answers;
  const [a, setA] = useState(saved || blank);
  const [err, setErr] = useState("");
  useEffect(() => { setA(saved || blank); }, [fw.key]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSaveFramework(fw.key);
  const complete = done(a);
  const dirty = useMemo(() => JSON.stringify(toPayload(fw.key, a)) !== JSON.stringify(saved ? toPayload(fw.key, saved) : null), [a, saved, fw.key]);
  const onSave = () => { setErr(""); save.mutate(toPayload(fw.key, a), { onError: (e) => setErr(apiError(e)) }); };
  return (
    <>
      <Card data-testid="fw-activity">
        <Label>Your turn: {fw.case.title}</Label>
        <p className="text-[15px]">{fw.case.situation}</p>
        <p className="text-[14px] font-semibold mt-2">{fw.case.task}</p>
        <div className="mt-5"><El fw={fw} a={a} set={(v) => { setA(v); setErr(""); }} /></div>
        <ErrorLine>{err}</ErrorLine>
        {complete && (dirty || !saved) ? (
          <Button className="w-full mt-5 rise-in" onClick={onSave} loading={save.isPending} data-testid="fw-save">{saved ? "Save changes" : "Save my answer"}</Button>
        ) : !complete ? (
          <p className="mt-4 text-center text-[13px] text-bz-muted" data-testid="fw-incomplete">Finish every step above and a Save button appears.</p>
        ) : (
          <p className="mt-4 text-center text-[13px] text-bz-muted" data-testid="fw-saved-note">Saved. Change anything above to save again.</p>
        )}
      </Card>
      {d.mine && d.akshat && <Marking mine={d.mine} akshat={d.akshat} />}
      {d.mine && <Proposal fkey={fw.key} mine={d.mine} />}
    </>
  );
}

export function FrameworkView() {
  const { id } = useParams();
  const q = useFramework(id);
  return (
    <div className="space-y-5">
      <BackLink to="/app/cases">All cases</BackLink>
      <Loadable q={q} what="this framework" lines={8}>
        {(d) => (
          <>
            <PageHeader kicker={`Framework ${d.framework.n} of 3 · from Akshat's live workshop`} title={d.framework.name}
              sub={d.framework.question} />
            <Learn fw={d.framework} />
            <Activity d={d} />
          </>
        )}
      </Loadable>
    </div>
  );
}

export default function Frameworks() {
  const { id } = useParams();
  if (id) return <FrameworkView />;
  return (
    <div className="space-y-5">
      <PageHeader kicker="Cases" title="Work along with Akshat" sub="The three frameworks from the live workshop. Do each one yourself, save it, see how Akshat read it, then turn it into a proposal." />
      <Card><FrameworkList /></Card>
    </div>
  );
}
