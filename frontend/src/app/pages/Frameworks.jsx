// /app/frameworks and /app/frameworks/:id — Work along with Akshat. The three frameworks from the live workshop
// (1 Nov 2026) as hands-on cases: learn the framework, do the exercise yourself, Save (appears once the exercise is
// complete), see how Akshat read it, then Generate a Proposal for that client.
// "My own case" runs the same exercise on a client from the member's own niche (Starting Point): suggested by the AI or
// written by the member, editable, checked against the framework's rules, then a proposal.
import { useEffect, useMemo, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { Check, ChevronRight, ExternalLink, Plus, Trash2, X } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { apiError } from "@/lib/api";
import { inr } from "@/lib/format";
import { useFramework, useFrameworkProposal, useFrameworks, useSaveFramework, useSaveOwn, useSuggestCase } from "@/services/frameworks";
import Markdown, { CopyButton } from "../components/Markdown";
import { BackLink, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, LinkButton, Loadable, Note, PageHeader, Segmented, Textarea, Thinking } from "../components/ui";

const ZONE_TONE = { green: "text-[#0f7a3d] bg-[#e7f6ec]", orange: "text-[#a35200] bg-[#fdf0e1]", red: "text-bz-miss bg-bz-miss-tint" };
const zoneFor = (p) => (p <= 20 ? "green" : p <= 40 ? "orange" : "red");
const words = (s) => (s || "").trim().length;
// An answer counts once it has any real text (FILLED in backend/features/frameworks.py). Save shows as soon as every step
// is answered; until then the page lists exactly what is still empty.
const filled = (s) => words(s) >= 2;
const num = (x) => (x === "" || x == null ? NaN : Number(x));
const inRange = (x, lo, hi) => Number.isFinite(num(x)) && num(x) >= lo && num(x) <= hi;

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
                    {f.own_saved && <Chip tone="muted">Own case: {f.own_client}</Chip>}
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

function MarketFit({ fw, c, own, a, set }) {
  const circles = a.circles || {};
  const setC = (k, patch) => set({ ...a, circles: { ...circles, [k]: { ...circles[k], ...patch } } });
  const where = own ? `in ${c.new_region}` : "for Nokia";
  return (
    <div className="space-y-5">
      <Venn fw={fw} value={circles} />
      {fw.structure.map((s) => (
        <div key={s.key} className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5" data-testid={`fw-circle-${s.key}`}>
          <p className="font-bold text-[15px]">{s.name}</p>
          <p className="text-[13.5px] text-bz-muted">{s.ask}</p>
          <Segmented label={`${s.name}: works or fails`} className="mt-2" value={circles[s.key]?.verdict || ""} testid={`fw-${s.key}`}
            onChange={(v) => setC(s.key, { verdict: v })}
            options={[{ value: "works", label: `Works ${where}` }, { value: "fails", label: `Fails ${where}` }]} />
          <Textarea rows={2} className="mt-2" value={circles[s.key]?.why || ""} maxLength={400} placeholder="Why? One sentence."
            onChange={(e) => setC(s.key, { why: e.target.value })} aria-label={`${s.name}: why`} data-testid={`fw-${s.key}-why`} />
        </div>
      ))}
      <Field label={own ? `Your diagnosis: will ${c.product} succeed in ${c.new_region}?` : "Your diagnosis: why did Nokia fail in India?"}>
        <Textarea rows={3} value={a.summary || ""} maxLength={800} onChange={(e) => set({ ...a, summary: e.target.value })}
          placeholder="In a sentence or two, as you'd tell the client." data-testid="fw-summary" />
      </Field>
    </div>
  );
}
const CIRCLE_NAMES = { price: "Price", value: "Value", availability: "Availability" };
const marketFitMissing = (a) => {
  const out = [];
  for (const [k, n] of Object.entries(CIRCLE_NAMES)) {
    if (!a.circles?.[k]?.verdict) out.push(`${n}: works or fails`);
    if (!filled(a.circles?.[k]?.why)) out.push(`${n}: why`);
  }
  if (!filled(a.summary)) out.push("Your diagnosis");
  return out;
};

// ============================================================================ framework 2: concentration ====
const fitLen = (arr, n) => Array.from({ length: n }, (_, i) => (arr || [])[i] ?? "");
const caseTotal = (c) => (c.sources || []).reduce((t, x) => t + (Number(x.amount) || 0), 0);

function Concentration({ fw, c, own, a, set }) {
  const sources = c.sources || [];
  const total = caseTotal(c);
  const pc = fitLen(a.percents, sources.length);
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
                <tr key={i} className="border-t border-bz-line">
                  <td className="py-2.5 pr-2">{s.name || `Source ${i + 1}`}</td>
                  <td className="py-2.5 text-right tabular">{inr(Number(s.amount) || 0)}</td>
                  <td className="py-2.5 text-right">
                    <Input type="number" inputMode="decimal" min={0} max={100} step="0.1" value={pc[i]} onChange={(e) => setP(i, e.target.value)}
                      className="!min-h-[40px] text-right w-[100px] ml-auto" aria-label={`${s.name || `Source ${i + 1}`}: concentration %`} data-testid={`fw-pct-${i}`} />
                  </td>
                  <td className="py-2.5 text-right">{z ? <span className={`text-[12px] font-bold px-2 py-[3px] rounded-bztag ${ZONE_TONE[z]}`}>{z}</span> : <span className="text-bz-faint">–</span>}</td>
                </tr>
              );
            })}
            <tr className="border-t border-bz-line-strong font-semibold"><td className="py-2.5">Total revenue</td><td className="py-2.5 text-right tabular">{inr(total)}</td><td className="py-2.5 text-right tabular text-bz-muted">{Math.round(pc.reduce((t, x) => t + (parseFloat(x) || 0), 0) * 10) / 10}%</td><td /></tr>
          </tbody>
        </table>
      </div>
      <div className="flex flex-wrap gap-2 text-[12.5px]">
        {fw.zones.map((z) => <span key={z.key} className={`px-2 py-1 rounded-bztag ${ZONE_TONE[z.key]}`}><b className="capitalize">{z.key}</b> {z.range}</span>)}
      </div>
      <div>
        <p className="text-[14px] font-semibold mb-2">{own ? "Your recommendation to the owner" : "Your recommendation to the founder"}</p>
        <Segmented label="Expand now or wait" value={a.recommendation || ""} onChange={(v) => set({ ...a, recommendation: v })} testid="fw-rec"
          options={[{ value: "expand", label: own ? "Expand now" : "Expand to Mumbai now" }, { value: "wait", label: "Wait" }]} />
      </div>
      <Field label={own ? "Why? Tell the owner in a sentence or two." : "Why? Tell him in a sentence or two."}>
        <Textarea rows={3} value={a.reason || ""} maxLength={800} onChange={(e) => set({ ...a, reason: e.target.value })} data-testid="fw-reason" />
      </Field>
      <div className="grid grid-cols-2 gap-3">
        <Field label="Bring the biggest source down to (%)"><Input type="number" inputMode="numeric" min={5} max={60} value={a.target_pct ?? ""} onChange={(e) => set({ ...a, target_pct: e.target.value })} data-testid="fw-target" /></Field>
        <Field label="Within (months)"><Input type="number" inputMode="numeric" min={1} max={36} value={a.months ?? ""} onChange={(e) => set({ ...a, months: e.target.value })} data-testid="fw-months" /></Field>
      </div>
    </div>
  );
}
const concentrationMissing = (a, c) => {
  const out = [];
  fitLen(a.percents, (c.sources || []).length).forEach((x, i) => {
    if (!inRange(x, 0, 100)) out.push(`Your % for ${c.sources[i]?.name || `source ${i + 1}`} (0 to 100)`);
  });
  if (!a.recommendation) out.push("Your recommendation: expand or wait");
  if (!filled(a.reason)) out.push("Why you recommend it");
  if (!inRange(a.target_pct, 1, 100)) out.push("The target % for the biggest source (1 to 100)");
  if (!inRange(a.months, 1, 60) || !Number.isInteger(num(a.months))) out.push("Within how many months (1 to 60)");
  return out;
};

// ============================================================================ framework 3: the compass ====
function Compass({ fw, c, own, a, set }) {
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
  const level = (l) => (l ? <span className="block text-[12px] text-bz-muted">Research says: <b>{l}</b></span> : null);
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 gap-3 text-center">
        <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3"><p className="text-[12.5px] text-bz-muted">Reach</p><p className="font-display text-[26px] tabular">{Number(c.reach_per_month || 0).toLocaleString("en-IN")}<span className="text-[13px] text-bz-muted"> a month</span></p>{own && level(c.reach_level)}</div>
        <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3"><p className="text-[12.5px] text-bz-muted">Conversion</p><p className="font-display text-[26px] tabular">{c.conversion_pct}%<span className="text-[13px] text-bz-muted"> a month</span></p>{own && level(c.conversion_level)}</div>
      </div>
      <div>
        <p className="text-[14px] font-semibold mb-2">{own ? "Where is the client on the compass? Tap a zone." : "Where is she on the compass? Tap a zone."}</p>
        <div className="text-center text-[12px] font-semibold text-bz-muted">North · high reach</div>
        <div className="flex items-center gap-2">
          <span className="text-[12px] font-semibold text-bz-muted [writing-mode:vertical-rl] rotate-180">West · low conversion</span>
          <div className="grid grid-cols-2 gap-2 flex-1" data-testid="fw-compass">{cell(2)}{cell(1)}{cell(4)}{cell(3)}</div>
          <span className="text-[12px] font-semibold text-bz-muted [writing-mode:vertical-rl]">East · high conversion</span>
        </div>
        <div className="text-center text-[12px] font-semibold text-bz-muted mt-1">South · low reach</div>
      </div>
      <div>
        <p className="text-[14px] font-semibold mb-2">{own ? "What should they work on?" : "What should she work on?"}</p>
        <Segmented label="What to fix" value={a.fix || ""} onChange={(v) => set({ ...a, fix: v })} testid="fw-fix"
          options={[{ value: "scale", label: "Keep going, scale" }, { value: "offer", label: "Fix the offer" }, { value: "reach", label: "Fix the reach" }, { value: "both", label: "Both" }]} />
      </div>
      <div className="space-y-2">
        <p className="text-[14px] font-semibold">{own ? "Three actions for the client's next 90 days" : "Three actions for her next 90 days"}</p>
        {[0, 1, 2].map((i) => (
          <Input key={i} value={(a.actions || [])[i] || ""} maxLength={240} placeholder={`Action ${i + 1}`} aria-label={`Action ${i + 1}`} data-testid={`fw-action-${i}`}
            onChange={(e) => { const acts = [...(a.actions || ["", "", ""])]; acts[i] = e.target.value; set({ ...a, actions: acts }); }} />
        ))}
      </div>
    </div>
  );
}
const compassMissing = (a) => {
  const out = [];
  if (!(Number(a.zone) >= 1)) out.push("A zone on the compass");
  if (!a.fix) out.push("What to work on");
  [0, 1, 2].forEach((i) => { if (!filled((a.actions || [])[i])) out.push(`Action ${i + 1}`); });
  return out;
};

const ACTIVITY = {
  "market-fit": { El: MarketFit, missing: marketFitMissing, blank: () => ({ circles: {}, summary: "" }) },
  "concentration-risk": { El: Concentration, missing: concentrationMissing,
    blank: (c) => ({ percents: fitLen([], (c?.sources || []).length || 3), recommendation: "", reason: "", target_pct: "", months: "" }) },
  "growth-compass": { El: Compass, missing: compassMissing, blank: () => ({ zone: 0, fix: "", actions: ["", "", ""] }) },
};
const toPayload = (key, a, c) => (key === "concentration-risk"
  ? { ...a, percents: fitLen(a.percents, (c?.sources || []).length).map((x) => parseFloat(x)), target_pct: Number(a.target_pct), months: Number(a.months) }
  : key === "growth-compass" ? { ...a, zone: Number(a.zone) } : a);

// ============================================================================ the member's own client case ====
const BLANK_CASE = {
  "market-fit": () => ({ client: "", product: "", new_region: "", situation: "" }),
  "concentration-risk": () => ({ client: "", situation: "", sources: [{ name: "", amount: "" }, { name: "", amount: "" }, { name: "", amount: "" }] }),
  "growth-compass": () => ({ client: "", situation: "", reach_per_month: "", conversion_pct: "", reach_level: "", conversion_level: "" }),
};
const CASE_FIELDS = ["client", "situation", "product", "new_region", "sources", "reach_per_month", "conversion_pct", "reach_level", "conversion_level",
  "company", "refs", "estimates"];
const pickCase = (c) => Object.fromEntries(CASE_FIELDS.filter((f) => c && f in c).map((f) => [f, c[f]]));
// The same rules as the case schemas in backend/features/frameworks.py.
const caseMissing = (key, c) => {
  if (!c) return [];
  const out = [];
  if (!filled(c.client)) out.push("The client");
  if (key === "market-fit") {
    if (!filled(c.product)) out.push("The product or service");
    if (!filled(c.new_region)) out.push("Where it wants to launch");
  }
  if (words(c.situation) < 10) out.push("The situation (a sentence or more)");
  if (key === "concentration-risk") {
    (c.sources || []).forEach((x, i) => {
      if (!filled(x.name)) out.push(`Source ${i + 1}: name`);
      if (!(num(x.amount) > 0)) out.push(`Source ${i + 1}: revenue in ₹`);
    });
    if ((c.sources || []).length < 2) out.push("At least two revenue sources");
  }
  if (key === "growth-compass") {
    if (!(num(c.reach_per_month) >= 1)) out.push("Reach (people a month)");
    if (!inRange(c.conversion_pct, 0, 100)) out.push("Conversion (0 to 100%)");
    if (!c.reach_level) out.push("Research says reach is high or low");
    if (!c.conversion_level) out.push("Research says conversion is high or low");
  }
  return out;
};
const casePayload = (key, c) => {
  const p = { company: "", refs: [], estimates: "", ...pickCase(c) };     // the same shape the server keeps
  if (key === "concentration-risk") p.sources = (p.sources || []).map((s) => ({ name: s.name, amount: Math.round(Number(s.amount)) }));
  if (key === "growth-compass") { p.reach_per_month = Math.round(Number(p.reach_per_month)); p.conversion_pct = parseFloat(p.conversion_pct); }
  return p;
};
const ownTitle = (key, c) => {
  const who = (c.client || "").trim() || "Your client";
  if (key === "market-fit") return `Will ${(c.product || "").trim() || "the product"} succeed in ${(c.new_region || "").trim() || "the new region"}?`;
  if (key === "concentration-risk") return `Is it safe for ${who} to expand?`;
  return `${who}: revenue is flat. What should they fix?`;
};

// A suggested client is a real company: show where its facts come from and which numbers are estimates.
function RealCompany({ c }) {
  if (!c.company) return null;
  return (
    <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5 text-[13.5px] space-y-2" data-testid="fw-real">
      <p><Chip tone="gold">Real company</Chip> <b className="ml-1">{c.company}</b></p>
      {(c.refs || []).length > 0 && (
        <ul className="space-y-1" data-testid="fw-refs">
          {c.refs.map((r) => (
            <li key={r.url} className="min-w-0">
              <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1.5 text-bz-gold hover:underline break-words">
                <ExternalLink className="w-3.5 h-3.5 mt-[3px] shrink-0" aria-hidden /><span className="min-w-0">{r.title}{r.source ? ` · ${r.source}` : ""}</span>
              </a>
            </li>
          ))}
        </ul>
      )}
      {c.estimates && <p className="text-bz-muted" data-testid="fw-estimates"><b>Estimated for practice:</b> {c.estimates}</p>}
      <p className="text-bz-muted">Built on public information for practice. Check the facts before you talk to the company.</p>
    </div>
  );
}

function CaseEditor({ fkey, c, set }) {
  const up = (patch) => set({ ...c, ...patch });
  const src = c.sources || [];
  const setS = (i, patch) => up({ sources: src.map((s, j) => (j === i ? { ...s, ...patch } : s)) });
  return (
    <div className="space-y-3" data-testid="fw-case-editor">
      <RealCompany c={c} />
      <Field label="The client" hint="A short description, like “a family-run sweet shop chain in Pune”.">
        <Input value={c.client || ""} maxLength={120} onChange={(e) => up({ client: e.target.value })} data-testid="fw-case-client" />
      </Field>
      {fkey === "market-fit" && (
        <div className="grid sm:grid-cols-2 gap-3">
          <Field label="The product or service"><Input value={c.product || ""} maxLength={160} onChange={(e) => up({ product: e.target.value })} data-testid="fw-case-product" /></Field>
          <Field label="Where it wants to launch"><Input value={c.new_region || ""} maxLength={80} onChange={(e) => up({ new_region: e.target.value })} data-testid="fw-case-region" /></Field>
        </div>
      )}
      <Field label="The situation" hint="What you know about the client: 2 to 5 sentences.">
        <Textarea rows={4} value={c.situation || ""} maxLength={1500} onChange={(e) => up({ situation: e.target.value })} data-testid="fw-case-situation" />
      </Field>
      {fkey === "concentration-risk" && (
        <div className="space-y-2">
          <p className="text-[14px] font-semibold">Revenue sources (a year, in ₹)</p>
          {src.map((s, i) => (
            <div key={i} className="flex gap-2 items-center">
              <Input value={s.name} maxLength={100} placeholder={`Source ${i + 1}`} aria-label={`Source ${i + 1}: name`} className="flex-1 min-w-0"
                onChange={(e) => setS(i, { name: e.target.value })} data-testid={`fw-case-src-name-${i}`} />
              <Input type="number" inputMode="numeric" min={1} value={s.amount} placeholder="₹" aria-label={`Source ${i + 1}: revenue in rupees`}
                className="w-[130px] sm:w-[160px] text-right" onChange={(e) => setS(i, { amount: e.target.value })} data-testid={`fw-case-src-amt-${i}`} />
              <button type="button" onClick={() => up({ sources: src.filter((_, j) => j !== i) })} disabled={src.length <= 2}
                className="w-10 h-10 shrink-0 grid place-items-center rounded-bzbtn text-bz-muted hover:text-bz-miss disabled:opacity-30" aria-label={`Remove source ${i + 1}`}>
                <Trash2 className="w-4 h-4" aria-hidden />
              </button>
            </div>
          ))}
          {src.length < 6 && (
            <Button variant="secondary" onClick={() => up({ sources: [...src, { name: "", amount: "" }] })} data-testid="fw-case-src-add">
              <Plus className="w-4 h-4" aria-hidden /> Add a source
            </Button>
          )}
          <p className="text-[13px] text-bz-muted">Total: <b className="tabular">{inr(caseTotal(c))}</b></p>
        </div>
      )}
      {fkey === "growth-compass" && (
        <div className="grid grid-cols-2 gap-3">
          <Field label="Reach (people a month)"><Input type="number" inputMode="numeric" min={1} value={c.reach_per_month ?? ""} onChange={(e) => up({ reach_per_month: e.target.value })} data-testid="fw-case-reach" /></Field>
          <Field label="Conversion (% who pay)"><Input type="number" inputMode="decimal" min={0} max={100} step="0.1" value={c.conversion_pct ?? ""} onChange={(e) => up({ conversion_pct: e.target.value })} data-testid="fw-case-conv" /></Field>
          <div><p className="text-[14px] font-semibold mb-1.5">Research says reach is</p>
            <Segmented label="Reach level" value={c.reach_level || ""} onChange={(v) => up({ reach_level: v })} testid="fw-case-reach-level" options={["high", "low"]} /></div>
          <div><p className="text-[14px] font-semibold mb-1.5">Research says conversion is</p>
            <Segmented label="Conversion level" value={c.conversion_level || ""} onChange={(v) => up({ conversion_level: v })} testid="fw-case-conv-level" options={["high", "low"]} /></div>
        </div>
      )}
    </div>
  );
}

function OwnStart({ fkey, niche, onWrite, hasCase }) {
  const { plan, refreshMe } = useAuth();
  const usage = plan?.limits?.fw_case;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const [hint, setHint] = useState("");
  const [err, setErr] = useState("");
  const suggest = useSuggestCase(fkey, { onDone: () => refreshMe() });
  const run = () => { setErr(""); suggest.mutate(hint, { onError: (e) => { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } }); };
  if (suggest.isPending) return <AiFrame title="Finding a real company in your niche"><Thinking label="Searching the web for a company in your niche and reading what's public about it. This can take up to a minute." /></AiFrame>;
  return (
    <Card data-testid="fw-own-start">
      <Label>Your own client</Label>
      {niche ? (
        <>
          <p className="text-[15px]">Practise on a real company you could pitch to, found on the web for your niche: <b data-testid="fw-own-niche">{niche.niche}</b>.</p>
          <Field label="Have a company in mind? (optional)" hint="Its name, or what kind of company, e.g. “an auto parts maker in Chennai”." className="mt-3">
            <Input value={hint} maxLength={300} onChange={(e) => setHint(e.target.value)} placeholder="e.g. Sundram Fasteners" data-testid="fw-own-hint" />
          </Field>
          <ErrorLine>{err}</ErrorLine>
          <div className="flex flex-col sm:flex-row gap-2 mt-3">
            <Button variant="ai" onClick={run} disabled={!canRun} data-testid="fw-own-suggest">{hasCase ? "Suggest another company" : "Suggest a real company from my niche"}</Button>
            {!hasCase && <Button variant="secondary" onClick={onWrite} data-testid="fw-own-write">Write my own client</Button>}
          </div>
          <UsageLine usage={usage} what="company suggestions" className="mt-2" />
        </>
      ) : (
        <>
          <p className="text-[15px]">Choose your niche in Starting Point and we'll find a real company in it for you. Or write your own client now.</p>
          <div className="flex flex-col sm:flex-row gap-2 mt-3">
            <LinkButton to="/app/start" variant="secondary" data-testid="fw-own-start-link">Go to Starting Point</LinkButton>
            {!hasCase && <Button variant="secondary" onClick={onWrite} data-testid="fw-own-write">Write my own client</Button>}
          </div>
        </>
      )}
    </Card>
  );
}

function OwnCase({ d }) {
  const fw = d.framework;
  const key = fw.key;
  const { El, missing, blank } = ACTIVITY[key];
  const own = d.own || {};
  const savedCase = own.case ? pickCase(own.case) : null;
  const saved = own.mine?.answers;
  const draft = own.draft_case ? pickCase(own.draft_case) : null;
  const [c, setC] = useState(draft || savedCase);
  const [a, setA] = useState(saved || blank(draft || savedCase));
  const [editing, setEditing] = useState(!savedCase || !!draft);
  const [err, setErr] = useState("");
  const draftSig = JSON.stringify(draft);
  // A new suggestion replaces the case being edited and starts the exercise afresh.
  useEffect(() => {
    if (draft) { setC(draft); setA(blank(draft)); setEditing(true); }
  }, [draftSig]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSaveOwn(key);
  const caseTodo = caseMissing(key, c);
  const okCase = !!c && caseTodo.length === 0;
  const todo = okCase ? missing(a, c) : [];
  const payload = useMemo(() => (c ? { case: casePayload(key, c), answers: toPayload(key, a, c) } : null), [c, a, key]);
  const dirty = JSON.stringify(payload) !== JSON.stringify(savedCase && saved ? { case: casePayload(key, savedCase), answers: toPayload(key, saved, savedCase) } : null);
  const onSave = () => { setErr(""); save.mutate(payload, { onSuccess: () => setEditing(false), onError: (e) => setErr(apiError(e)) }); };
  // the case on screen is not the saved one (a new suggestion, or edits): what's below belongs to the saved client
  const caseChanged = !!(savedCase && c && JSON.stringify(casePayload(key, c)) !== JSON.stringify(casePayload(key, savedCase)));
  const setCase = (v) => {
    setErr("");
    // the table follows the sources: one % per source
    if (key === "concentration-risk") setA((x) => ({ ...x, percents: fitLen(x.percents, (v.sources || []).length) }));
    setC(v);
  };
  return (
    <>
      <OwnStart fkey={key} niche={d.niche} hasCase={!!c} onWrite={() => { const b = BLANK_CASE[key](); setC(b); setA(blank(b)); setEditing(true); }} />
      {c && (
        <Card data-testid="fw-activity">
          <Label>Your client: {ownTitle(key, c)}</Label>
          {editing ? (
            <CaseEditor fkey={key} c={c} set={setCase} />
          ) : (
            <>
              <RealCompany c={c} />
              <p className="text-[15px] mt-3" data-testid="fw-own-situation">{c.situation}</p>
              <Button variant="secondary" className="mt-2" onClick={() => setEditing(true)} data-testid="fw-case-edit">Edit the case</Button>
            </>
          )}
          {okCase ? (
            <>
              <p className="text-[14px] font-semibold mt-5">{own.case?.task || own.draft_case?.task || "Now do the exercise on your client."}</p>
              <div className="mt-4"><El fw={fw} c={c} own a={a} set={(v) => { setA(v); setErr(""); }} /></div>
            </>
          ) : (
            <ToDo items={caseTodo} title="Fill in the case and the exercise appears. Still empty:" testid="fw-case-incomplete" />
          )}
          <ErrorLine>{err}</ErrorLine>
          {okCase && <SaveRow todo={todo} dirty={dirty} saved={!!saved} pending={save.isPending} onSave={onSave} />}
        </Card>
      )}
      {own.mine && caseChanged && (
        <div className="rounded-bzcard border border-bz-line-strong bg-bz-raised p-3.5 text-[14px]" data-testid="fw-own-old">
          <b>Below: your saved client, {savedCase.client}.</b> The marking and proposal are for that client. Save the
          new client above to replace them.
        </div>
      )}
      {own.mine && <Marking mine={own.mine} />}
      {own.mine && <Proposal fkey={key} mine={own.mine} own noAgain={caseChanged} />}
    </>
  );
}

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
  const holds = g.mode === "holds";
  return (
    <Card className="rise-in" data-testid="fw-marking">
      <div className="flex items-baseline justify-between gap-3">
        <Label className="mb-0">{g.title || "Your reading against Akshat's"}</Label>
        <span className="font-display text-[22px] tabular text-bz-gold" data-testid="fw-score">{g.score} of {g.out_of}</span>
      </div>
      <ul className="mt-3 divide-y divide-bz-line">
        {g.marks.map((m) => (
          <li key={m.label} className="py-2.5 flex items-start gap-2.5 text-[14px]">
            {m.ok ? <Check className="w-4 h-4 mt-0.5 text-bz-gold shrink-0" aria-label={holds ? "Holds" : "Matches"} />
              : <X className="w-4 h-4 mt-0.5 text-bz-miss shrink-0" aria-label={holds ? "Comes apart" : "Doesn't match"} />}
            <span className="min-w-0">
              {holds ? <><b>{m.label}.</b> {m.ok ? "Holds" : "Comes apart"}</>
                : <><b>{m.label}.</b> You: {m.yours}{!m.ok && m.right && <> · {g.own ? "The rule says" : "Akshat"}: <b>{m.right}</b></>}</>}
            </span>
          </li>
        ))}
      </ul>
      <div className="mt-3 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
        <p className="text-[13px] font-semibold text-bz-gold">{g.read_title || "How Akshat read this case"}</p>
        <p className="text-[14.5px] mt-1" data-testid="fw-read">{akshat?.read || g.read}</p>
      </div>
    </Card>
  );
}

function Proposal({ fkey, mine, own = false, noAgain = false }) {
  const { plan, refreshMe } = useAuth();
  const usage = plan?.limits?.fw_proposal;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const [err, setErr] = useState("");
  const gen = useFrameworkProposal(fkey, { own, onDone: () => refreshMe() });
  const p = mine.proposal;
  const run = () => { setErr(""); gen.mutate(undefined, { onError: (e) => { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } }); };
  if (gen.isPending) return <AiFrame title="Writing your proposal"><Thinking label="Turning your analysis into a client proposal. This takes about half a minute." /></AiFrame>;
  if (!p) {
    return (
      <Card className="rise-in" data-testid="fw-proposal-cta">
        <Label>Your proposal</Label>
        <p className="text-[15px]">Turn your analysis into a proposal this client could say yes to: the situation, what the framework shows, the objective, a phased plan, deliverables, fee and next steps.</p>
        <ErrorLine>{err}</ErrorLine>
        {noAgain ? <Note className="mt-3">Save the new client first, then generate its proposal.</Note>
          : <Button variant="ai" className="w-full mt-4" onClick={run} disabled={!canRun} data-testid="fw-proposal-go">Generate a Proposal</Button>}
        <UsageLine usage={usage} what="framework proposals" className="mt-2 text-center" />
      </Card>
    );
  }
  return (
    <div className="space-y-3">
      <AiFrame title="Your proposal" className="print-plain rise-in" right={<CopyButton text={p.markdown} />}>
        <div data-testid="fw-proposal"><Markdown text={p.markdown} /></div>
        {p.stale && <Note className="mt-3">Made from your earlier answer. Generate again to use what you saved last.</Note>}
        <p className="text-[12px] text-bz-muted mt-3">{own ? "A draft proposal for your own client, built on public information." : "A practice proposal for a workshop case."} Check the numbers and fill in anything in [brackets] before you use it with a real client.</p>
      </AiFrame>
      <div className="flex flex-col sm:flex-row gap-2 no-print">
        <Button variant="secondary" onClick={() => window.print()} data-testid="fw-print">Print or save as PDF</Button>
        {canRun && !noAgain && <Button variant="secondary" onClick={run} data-testid="fw-proposal-again">Generate again</Button>}
        <UsageLine usage={usage} what="framework proposals" className="sm:ml-auto self-center" />
      </div>
      <ErrorLine>{err}</ErrorLine>
    </div>
  );
}

function ToDo({ items, title, testid }) {
  return (
    <div className="mt-5 rounded-bzcard border border-dashed border-bz-line-strong p-3.5" data-testid={testid}>
      <p className="text-[13.5px] font-semibold">{title}</p>
      <ul className="mt-1.5 grid sm:grid-cols-2 gap-x-4 gap-y-1 text-[13.5px] text-bz-muted list-disc pl-5">
        {items.map((m) => <li key={m}>{m}</li>)}
      </ul>
    </div>
  );
}

function SaveRow({ todo, dirty, saved, pending, onSave }) {
  if (todo.length) return <ToDo items={todo} title="Answer these and the Save button appears:" testid="fw-incomplete" />;
  if (dirty || !saved) {
    return <Button className="w-full mt-5 rise-in" onClick={onSave} loading={pending} data-testid="fw-save">{saved ? "Save changes" : "Save my answer"}</Button>;
  }
  return <p className="mt-4 text-center text-[13px] text-bz-muted" data-testid="fw-saved-note"><Check className="inline w-4 h-4 -mt-0.5 text-bz-gold" aria-hidden /> Saved. Your marking and the proposal are below. Change anything above to save again.</p>;
}

function Activity({ d }) {
  const fw = d.framework;
  const c = fw.case;
  const { El, missing, blank } = ACTIVITY[fw.key];
  const saved = d.mine?.answers;
  const [a, setA] = useState(saved || blank(c));
  const [err, setErr] = useState("");
  useEffect(() => { setA(saved || blank(c)); }, [fw.key]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useSaveFramework(fw.key);
  const todo = missing(a, c);
  const dirty = useMemo(() => JSON.stringify(toPayload(fw.key, a, c)) !== JSON.stringify(saved ? toPayload(fw.key, saved, c) : null), [a, saved, fw.key, c]);
  const onSave = () => { setErr(""); save.mutate(toPayload(fw.key, a, c), { onError: (e) => setErr(apiError(e)) }); };
  return (
    <>
      <Card data-testid="fw-activity">
        <Label>Your turn: {c.title}</Label>
        <p className="text-[15px]">{c.situation}</p>
        <p className="text-[14px] font-semibold mt-2">{c.task}</p>
        <div className="mt-5"><El fw={fw} c={c} own={false} a={a} set={(v) => { setA(v); setErr(""); }} /></div>
        <ErrorLine>{err}</ErrorLine>
        <SaveRow todo={todo} dirty={dirty} saved={!!saved} pending={save.isPending} onSave={onSave} />
      </Card>
      {d.mine && d.akshat && <Marking mine={d.mine} akshat={d.akshat} />}
      {d.mine && <Proposal fkey={fw.key} mine={d.mine} />}
    </>
  );
}

function CaseTabs({ d }) {
  const [sp, setSp] = useSearchParams();
  const tab = sp.get("case") === "own" ? "own" : "akshat";
  return (
    <>
      <div data-testid="fw-tabs">
        <Segmented label="Which case" value={tab} testid="fw-tab"
          onChange={(v) => setSp(v === "own" ? { case: "own" } : {}, { replace: true })}
          options={[{ value: "akshat", label: "Akshat's case" }, { value: "own", label: "My own client" }]} />
      </div>
      {tab === "own" ? <OwnCase key={`own-${d.framework.key}`} d={d} /> : <Activity key={`ak-${d.framework.key}`} d={d} />}
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
            <CaseTabs d={d} />
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
      <PageHeader kicker="Cases" title="Work along with Akshat" sub="The three frameworks from the live workshop. Do each one on Akshat's case or on a client from your own niche, save it, then turn it into a proposal." />
      <Card><FrameworkList /></Card>
    </div>
  );
}
