// The client proposal from a framework activity, laid out like Akshat's Growth Compass proposal (Nov 2026):
// cover · contents · where we started · the real problem · the framework · your diagnosis (numbers, verdict, lever)
// · why nothing moved · where to focus · 90-day plan · what it's worth · next steps.
// The words and numbers come from the AI (backend/features/proposal_doc.py); the framework's own picture (compass,
// revenue bars, Venn) is drawn here from the case and the member's answers. Print / Save as PDF prints only this
// document, one page per sheet, in colour (index.css → .pd-*).
import { FileText, Lightbulb, Megaphone, MonitorSmartphone, Users } from "lucide-react";

const NAV = ["Situation", "Diagnosis", "Plan", "Impact", "Next steps"];
const ICONS = [FileText, Megaphone, MonitorSmartphone, Users, Lightbulb];
const ZONE_TITLES = { 1: "Scale", 2: "Fix the offer", 3: "Get discovered", 4: "Rebuild" };
const ZONE_LINES = {
  1: "Your business is scaling. Stay the course.",
  2: "Enough people know you exist. Your offer or your pitch needs work.",
  3: "Your product works. Not enough people know it exists.",
  4: "Both your visibility and your product need attention.",
};
const RISK = { green: "#34c38f", orange: "#f5a524", red: "#ff5a6a" };
const zoneFor = (p) => (p <= 20 ? "green" : p <= 40 ? "orange" : "red");

export const inrShort = (n) => {
  if (!n) return "";
  if (n >= 1e7) return `₹${(n / 1e7).toFixed(1).replace(/\.0$/, "")}Cr`;
  if (n >= 1e5) return `₹${(n / 1e5).toFixed(1).replace(/\.0$/, "")}L`;
  return `₹${Number(n).toLocaleString("en-IN")}`;
};

function splitName(name) {
  const w = (name || "").split(" ");
  return w.length > 1 ? [w.slice(0, -1).join(" "), w[w.length - 1]] : [name, ""];
}

// ------------------------------------------------------------------------------------------- shared pieces ----
function Head({ by, active, n, total, light }) {
  return (
    <div className={`flex items-center justify-between gap-3 text-[11px] ${light ? "text-[#2a2c38]" : "text-white/85"}`}>
      <span className="flex items-center gap-2 font-semibold">
        <span className="flex gap-[3px]" aria-hidden><i className={`block w-[22px] h-[9px] ${light ? "bg-[#2a2c38]" : "bg-white"}`} /><i className={`block w-[5px] h-[9px] ${light ? "bg-[#2a2c38]" : "bg-white"}`} /><i className={`block w-[5px] h-[9px] ${light ? "bg-[#2a2c38]" : "bg-white"}`} /></span>
        {by}
      </span>
      <span className="hidden sm:flex gap-5">
        {NAV.map((x) => <span key={x} className={x === active ? "font-semibold" : light ? "text-[#9a9db0]" : "text-white/45"}>{x}</span>)}
      </span>
      <span className="tabular">{String(n).padStart(2, "0")} / {String(total).padStart(2, "0")}</span>
    </div>
  );
}

function Title({ a, b, size = "text-[44px] sm:text-[64px]", indent = true }) {
  return (
    <h2 className={`pd-h ${size}`}>
      {a}
      {b && <><br /><span className={`${indent ? "pl-[0.9em]" : ""} pd-grad pd-accent`}>{b}</span></>}
    </h2>
  );
}

// ------------------------------------------------------------------------------------- framework pictures ----
function CompassGrid({ fw, here, dark }) {
  const byZone = Object.fromEntries((fw.zones || []).map((z) => [z.zone, z]));
  const cell = (n, tone) => {
    const z = byZone[n] || {};
    const on = here === n;
    const dim = here && !on;
    const tones = {
      3: "bg-[#2733c9] text-white", 1: "bg-[#4458ff] text-white", 4: dark ? "bg-white/[.06] text-white" : "bg-[#eef0f6] text-[#2a2c38]", 2: "bg-[#07080d] text-white",
    };
    return (
      <div key={n} className={`relative overflow-hidden p-4 sm:p-5 min-h-[150px] sm:min-h-[210px] ${dim ? (dark ? "bg-white/[.03] text-white/35 border border-white/10" : "opacity-35 " + tones[tone]) : tones[tone]} ${on ? "ring-2 ring-white/70 shadow-[0_0_40px_rgba(90,110,255,.6)]" : ""}`}>
        <p className="text-[11px] opacity-80">[Zone {n}]</p>
        <p className="pd-h text-[24px] sm:text-[30px] mt-1">{ZONE_TITLES[n]}</p>
        <p className="text-[12.5px] mt-1.5 max-w-[240px] opacity-85">{ZONE_LINES[n]}</p>
        <div className="absolute left-4 sm:left-5 bottom-4 flex gap-1.5 text-[10.5px]">
          <span className="pd-pill border border-current/60 opacity-90">{z.reach === "high" ? "High" : "Low"} reach</span>
          <span className="pd-pill border border-current/60 opacity-90">{z.conversion === "high" ? "High" : "Low"} conversion</span>
        </div>
        <span aria-hidden className="absolute right-3 -bottom-6 pd-h text-[120px] sm:text-[150px] opacity-[.12]">{n}</span>
        {on && <span className="absolute right-3 top-3 pd-pill bg-[#07080d] text-white text-[11px]" data-testid="pd-here">You are here</span>}
      </div>
    );
  };
  return (
    <div className="flex gap-3">
      <div className={`flex flex-col items-center justify-between text-[11px] font-semibold ${dark ? "text-white/70" : "text-[#2a2c38]"}`}>
        <span aria-hidden>↑</span><span className="[writing-mode:vertical-rl] rotate-180">Conversion</span><span />
      </div>
      <div className="flex-1">
        <div className="grid grid-cols-2 gap-2" role="img" aria-label={`Growth Compass${here ? `, you are in Zone ${here}` : ""}`}>
          {cell(3, 3)}{cell(1, 1)}{cell(4, 4)}{cell(2, 2)}
        </div>
        <p className={`text-right text-[11px] font-semibold mt-2 ${dark ? "text-white/70" : "text-[#2a2c38]"}`}>Reach →</p>
      </div>
    </div>
  );
}

function RevenueBars({ c, dark }) {
  const sources = c?.sources || [];
  const total = sources.reduce((t, s) => t + (Number(s.amount) || 0), 0) || 1;
  const rows = sources.map((s) => ({ ...s, pct: Math.round((Number(s.amount) * 1000) / total) / 10 }));
  const top = Math.max(...rows.map((r) => r.pct), 0);
  return (
    <div className="space-y-3" role="img" aria-label={`Revenue by source: ${rows.map((r) => `${r.name} ${r.pct}%`).join(", ")}`}>
      {rows.map((r) => (
        <div key={r.name}>
          <div className={`flex justify-between gap-3 text-[13px] ${dark ? "text-white/85" : ""}`}>
            <span className="min-w-0 truncate">{r.name}</span>
            <span className="tabular font-semibold shrink-0">{r.pct}% · {inrShort(r.amount)}</span>
          </div>
          <div className={`h-3 mt-1.5 rounded-full ${dark ? "bg-white/10" : "bg-[#eef0f6]"} relative`}>
            <div className="h-3 rounded-full" style={{ width: `${Math.max(r.pct, 1.5)}%`, background: RISK[zoneFor(r.pct)] }} />
            {[20, 40].map((x) => <i key={x} aria-hidden className={`absolute top-[-3px] h-[18px] w-px ${dark ? "bg-white/40" : "bg-[#2a2c38]/40"}`} style={{ left: `${x}%` }} />)}
          </div>
          {r.pct === top && top > 0 && <span className="pd-pill mt-1.5 text-[11px] text-white" style={{ background: RISK[zoneFor(r.pct)] }} data-testid="pd-here">You are here: {zoneFor(r.pct)} zone</span>}
        </div>
      ))}
      <div className={`flex flex-wrap gap-3 text-[11.5px] pt-1 ${dark ? "text-white/70" : "text-[#6b6f80]"}`}>
        <span><i className="inline-block w-2.5 h-2.5 rounded-full mr-1" style={{ background: RISK.green }} />20% or less: safe</span>
        <span><i className="inline-block w-2.5 h-2.5 rounded-full mr-1" style={{ background: RISK.orange }} />over 20% to 40%: watch</span>
        <span><i className="inline-block w-2.5 h-2.5 rounded-full mr-1" style={{ background: RISK.red }} />over 40%: danger</span>
      </div>
    </div>
  );
}

function VennPic({ circles, dark }) {
  const pos = { price: [118, 98], value: [202, 98], availability: [160, 170] };
  const names = { price: "Price", value: "Value", availability: "Availability" };
  const all = Object.keys(pos).every((k) => circles[k] === "works");
  return (
    <svg viewBox="0 0 320 262" className="w-full max-w-[380px] mx-auto" role="img"
      aria-label={`Market-Fit Venn: ${Object.keys(pos).map((k) => `${names[k]} ${circles[k] || "not marked"}`).join(", ")}`}>
      {Object.entries(pos).map(([k, [x, y]]) => {
        const v = circles[k];
        return (
          <g key={k}>
            <circle cx={x} cy={y} r="78" style={{ fill: v === "works" ? "rgb(68 88 255 / .28)" : "rgb(255 90 106 / .10)",
              stroke: v === "works" ? "#8b93ff" : "#ff5a6a", strokeWidth: 2, strokeDasharray: v === "fails" ? "6 5" : "none" }} />
            <text x={x + (k === "price" ? -30 : k === "value" ? 30 : 0)} y={y + (k === "availability" ? 40 : -22)} textAnchor="middle"
              style={{ fill: dark ? "#fff" : "#2a2c38", fontSize: 14, fontWeight: 700 }}>{names[k]}</text>
            {v && <text x={x + (k === "price" ? -30 : k === "value" ? 30 : 0)} y={y + (k === "availability" ? 58 : -4)} textAnchor="middle"
              style={{ fill: v === "works" ? "#7fe0d4" : "#ff5a6a", fontSize: 12, fontWeight: 700 }}>{v === "works" ? "holds" : "fails"}</text>}
          </g>
        );
      })}
      <text x="160" y="124" textAnchor="middle" style={{ fill: all ? "#7fe0d4" : "#ff8a96", fontSize: 12, fontWeight: 700 }}>{all ? "Fits" : "At risk"}</text>
    </svg>
  );
}

function FrameworkPicture({ fkey, fw, c, here, circles, dark }) {
  if (fkey === "growth-compass") return <CompassGrid fw={fw} here={here} dark={dark} />;
  if (fkey === "concentration-risk") return <RevenueBars c={c} dark={dark} />;
  return <VennPic circles={circles} dark={dark} />;
}

function People({ total = 50, lit = 1 }) {
  const on = new Set(Array.from({ length: Math.min(lit, total) }, (_, i) => (i * 37 + 23) % total));
  return (
    <div className="grid grid-cols-10 gap-x-2 gap-y-3" aria-hidden>
      {Array.from({ length: total }, (_, i) => (
        <svg key={i} viewBox="0 0 20 30" className={`w-full max-w-[24px] ${on.has(i) ? "drop-shadow-[0_0_10px_rgba(160,190,255,.95)]" : ""}`}>
          <circle cx="10" cy="6" r="5" fill={on.has(i) ? "#fff" : "#5b5f70"} />
          <path d="M3 14 q7 -4 14 0 v9 h-3 v6 h-3 v-6 h-2 v6 h-3 v-6 h-3z" fill={on.has(i) ? "#fff" : "#5b5f70"} />
        </svg>
      ))}
    </div>
  );
}

function Dots({ total, lit }) {
  const on = new Set(Array.from({ length: lit }, (_, i) => (i * 53 + 31) % total));
  return (
    <div className="grid gap-2.5" style={{ gridTemplateColumns: "repeat(25, minmax(0, 1fr))" }} aria-hidden>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`block aspect-square rounded-full ${on.has(i) ? "pd-lit" : "bg-white/25"}`} style={{ maxWidth: 9 }} />
      ))}
    </div>
  );
}

// -------------------------------------------------------------------------------------------------- pages ----
export default function ProposalDoc({ p, fw, fkey, c, answers, grade }) {
  const by = (p.prepared_by || "").split(",")[0] || "Your consultant";
  const [nameA, nameB] = splitName(p.framework || fw.name);
  const marks = grade?.marks || [];
  const zoneHere = (() => {
    const m = String(marks.find((x) => x.label === "Zone")?.right || "").match(/Zone (\d)/);
    return m ? Number(m[1]) : Number(answers?.zone) || null;
  })();
  const circles = Object.fromEntries(["price", "value", "availability"].map((k) => {
    const m = marks.find((x) => x.label.toLowerCase() === k);
    const v = grade?.own ? answers?.circles?.[k]?.verdict : m?.right || answers?.circles?.[k]?.verdict;
    return [k, v];
  }));
  const d = p.diagnosis || {};
  const lv = p.lever || {};
  const why = p.why || {};
  const fc = p.focus || {};
  const pl = p.plan || {};
  const im = p.impact || {};
  const conv = Number(c?.conversion_pct) || 0;
  const reach = Number(c?.reach_per_month) || 0;

  const pages = [];
  const add = (id, nav, tone, body, section) => pages.push({ id, nav, tone, body, section });

  // 1. cover
  add("cover", "Situation", "dark", () => (
    <div className="pd-fill min-h-[640px] sm:min-h-[880px] flex flex-col">
      <span aria-hidden className="pd-burst w-[620px] h-[620px] -right-[200px] top-[300px]" />
      <div className="mt-14 flex gap-6 text-[11.5px] text-white/80"><span>[Business Diagnostic]</span><span>[Solution Proposal]</span></div>
      <h1 className="pd-h text-[56px] sm:text-[104px] mt-6 text-white">{nameA}<br /><span className="pl-[0.7em] pd-grad">{nameB}</span></h1>
      <p className="mt-8 text-[17px] sm:text-[19px] text-white/75 max-w-[340px]">{p.tagline}</p>
      <div className="mt-auto pd-card-dark max-w-[420px] -mb-8 -ml-[22px] sm:-ml-12 rounded-none rounded-tr-md p-5 sm:p-7 bg-[#0d1020]/80 backdrop-blur divide-y divide-white/10">
        {[["Prepared for", p.client, p.client_descriptor], ["Prepared by", by, (p.prepared_by || "").split(",").slice(1).join(",").trim()], ["Date", p.date, ""]].map(([k, v, sub]) => (
          <div key={k} className="grid grid-cols-[110px_1fr] gap-3 py-3.5 text-[13px]">
            <span className="text-white/45">{k}</span>
            <span><span className="block text-[15px] text-white" data-testid={k === "Prepared for" ? "pd-client" : undefined}>{v}</span>{sub && <span className="block text-white/55 text-[12px] mt-0.5">{sub}</span>}</span>
          </div>
        ))}
      </div>
    </div>
  ));

  // 2. contents is added after the others are known (needs their page numbers)
  // 3. where we started
  add("situation", "Situation", "light", () => (
    <>
      <h2 className="pd-h text-[38px] sm:text-[58px] mt-10 text-[#2a2c38]">“{p.hook?.quote_start}{p.hook?.quote_end && <><br /><span className="pl-[0.6em] pd-accent">{p.hook.quote_end}”</span></>}{!p.hook?.quote_end && "”"}</h2>
      <div className="grid sm:grid-cols-2 gap-8 mt-12">
        <p className="text-[14.5px] leading-relaxed whitespace-pre-line">{p.situation}</p>
        <div className="divide-y divide-[#e3e6ef] border-y border-[#e3e6ef]">
          {(p.key_facts || []).map((f, i) => (
            <div key={i} className="flex items-baseline gap-4 py-3">
              <span className={`pd-h text-[34px] min-w-[120px] ${i === 2 ? "pd-accent" : ""}`}>{f.value}</span>
              <span className="text-[12.5px] text-[#6b6f80]">{f.label}</span>
            </div>
          ))}
        </div>
      </div>
      {(p.tried || []).length > 0 && (
        <div className="pd-bottom pd-dark pd-grid relative -mx-[22px] sm:-mx-12 -mb-8 sm:-mb-12 mt-12 px-[22px] sm:px-12 py-10">
          <p className="text-[22px] pd-h text-white">What you had already tried</p>
          <div className="grid sm:grid-cols-3 gap-3 mt-6">
            {p.tried.map((t, i) => {
              const I = ICONS[i % ICONS.length];
              return (
                <div key={i} className="pd-card-dark p-5 min-h-[180px] flex flex-col">
                  <I className="w-7 h-7 text-white" strokeWidth={1.6} aria-hidden />
                  <p className="text-[17px] text-white mt-4 pd-h">{t.title}</p>
                  <p className="text-[12.5px] text-white/55 mt-2">{t.detail}</p>
                  {t.result && <p className="text-[12px] text-[#7fe0d4] mt-auto pt-4">{t.result}</p>}
                </div>
              );
            })}
          </div>
        </div>
      )}
    </>
  ), 1);

  // 4. the real problem
  add("problem", "Situation", "dark", () => (
    <>
      <span aria-hidden className="pd-burst w-[520px] h-[520px] left-[10%] -top-[330px] opacity-70" />
      <p className="pd-h text-[30px] sm:text-[44px] text-white/45 mt-20">{p.reframe?.muted}</p>
      <h2 className="pd-h text-[36px] sm:text-[54px] text-white mt-4">{p.reframe?.headline}{p.reframe?.accent && <><br /><span className="pl-[0.9em] pd-grad">{p.reframe.accent}</span></>}</h2>
      <p className="text-[14px] text-white/70 max-w-[380px] mt-10 leading-relaxed">{p.problem}</p>
      <div className={`grid gap-3 mt-10 ${(p.possibilities || []).length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {(p.possibilities || []).map((x, i) => (
          <div key={i} className="pd-card-dark p-5 min-h-[170px]">
            <div className="flex justify-between items-center text-[11.5px] text-white/60">
              <span>Possibility {["one", "two", "three"][i]}</span>
              <span className="pd-pill border border-white/40 text-white">{x.tag}</span>
            </div>
            <p className="pd-h text-[22px] text-white mt-6">{x.statement}</p>
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3 mt-12 text-[13px] text-white/80">
        <span>To find out which one, I used a diagnostic framework: {p.framework || fw.name}.</span>
        <span className="pd-pill bg-gradient-to-r from-[#3b49ff] to-[#7fe0d4] text-white">Next: the framework</span>
      </div>
    </>
  ), 2);

  // 5. the framework
  add("framework", "Diagnosis", "light", () => (
    <>
      <div className="grid sm:grid-cols-[1fr_300px] gap-8 mt-10">
        <Title a={nameA} b={nameB} size="text-[44px] sm:text-[62px]" />
        <div>
          <p className="text-[14px]">{fw.question}</p>
          <table className="w-full mt-5 text-[12.5px] border-t border-[#e3e6ef]">
            <tbody>
              {(fw.dimensions || fw.structure || fw.zones || []).slice(0, 3).map((x) => (
                <tr key={x.key || x.zone} className="border-b border-[#e3e6ef]">
                  <td className="py-2.5 pr-3 font-semibold align-top">{x.name || (x.key ? x.key[0].toUpperCase() + x.key.slice(1) : "")}</td>
                  <td className="py-2.5 text-[#6b6f80]">{x.meaning || x.ask || x.range}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      <div className="mt-10"><FrameworkPicture fkey={fkey} fw={fw} c={c} circles={{}} /></div>
      <div className="flex flex-wrap justify-between gap-3 mt-8 text-[12.5px] text-[#6b6f80]">
        <span>{fw.rule || "Where the business sits decides where your energy and budget should go."}</span>
        <span>There is no guessing involved.</span>
      </div>
    </>
  ), 3);

  // 6. your diagnosis: the numbers
  add("diagnosis", "Diagnosis", "cobalt", () => (
    <>
      <Title a={d.headline} b={d.accent} size="text-[44px] sm:text-[60px] text-white mt-10" />
      <div className="mt-12 space-y-10">
        {(d.questions || []).map((q, i) => (
          <div key={i} className="grid sm:grid-cols-[230px_1fr] gap-4 items-center">
            <div><p className="text-[12px] text-[#7fe0d4]">Question {["one", "two", "three"][i]}</p><p className="text-[13.5px] text-white/70 mt-1">{q.question}</p></div>
            <p className="flex items-end gap-3"><span className="pd-h text-[60px] sm:text-[96px] text-white leading-none">{q.value}</span><span className="text-[12.5px] text-white/60 pb-2 max-w-[120px]">{q.unit}</span></p>
          </div>
        ))}
      </div>
      <div className="pd-card-dark mt-12 p-5 sm:p-7 grid sm:grid-cols-[1.2fr_1fr] gap-6 items-center">
        {fkey === "growth-compass" ? <People total={50} lit={Math.max(1, Math.round(conv / 2))} /> : <FrameworkPicture fkey={fkey} fw={fw} c={c} circles={circles} dark here={zoneHere} />}
        <div>
          <p className="pd-h text-[28px] text-white">{d.verdict_line || d.verdict}</p>
          <p className="text-[13px] text-white/65 mt-2">{d.verdict_text}</p>
        </div>
      </div>
      {d.note && <div className="flex items-center gap-4 mt-8 text-[12.5px] text-white/70"><span className="pd-pill border border-white/40 text-white">Week one</span><span>{d.note}</span></div>}
    </>
  ), 4);

  // 7. the verdict
  add("verdict", "Diagnosis", "cobalt", () => (
    <>
      <div className="grid sm:grid-cols-[1fr_300px] gap-6 mt-10 items-start">
        <p className="pd-h pd-grad text-[64px] sm:text-[110px]" data-testid="pd-verdict">{d.verdict}</p>
        <div><p className="text-[20px] text-white pd-h">{d.verdict_line}</p><p className="text-[13px] text-white/70 mt-2">{d.verdict_text}</p></div>
      </div>
      <div className="mt-10"><FrameworkPicture fkey={fkey} fw={fw} c={c} circles={circles} here={zoneHere} dark /></div>
      <div className="grid sm:grid-cols-3 gap-6 mt-10">
        {(d.points || []).map((x, i) => (
          <div key={i} className="border-t border-white/30 pt-3"><p className="text-[14px] font-semibold text-white">{x.title}</p><p className="text-[12.5px] text-white/65 mt-1">{x.text}</p></div>
        ))}
      </div>
    </>
  ), 4);

  // 8. the lever
  if ((lv.chain || []).length) {
    add("lever", "Diagnosis", "light", () => (
      <>
        <div className="grid sm:grid-cols-[1fr_300px] gap-6 mt-10">
          <Title a={lv.headline} b={lv.accent} size="text-[44px] sm:text-[60px]" />
          <p className="text-[14px] text-[#2a2c38]">{lv.text}</p>
        </div>
        <div className={`grid gap-6 mt-14 grid-cols-2 ${lv.chain.length === 4 ? "sm:grid-cols-4" : "sm:grid-cols-3"}`}>
          {lv.chain.map((s, i) => (
            <div key={i} className={`border-t-2 pt-3 ${i === lv.chain.length - 1 ? "border-[#4458ff]" : "border-[#2a2c38]"}`}>
              <span className={`block pd-h whitespace-nowrap ${s.value.length > 6 ? "text-[30px]" : "text-[38px]"} ${i === lv.chain.length - 1 ? "pd-accent" : ""}`}>{s.value}</span>
              <p className="text-[12px] text-[#6b6f80] mt-1">{s.label}</p>
              {s.op && <span className="inline-block mt-2 rounded-[10px] px-2.5 py-1 bg-[#eef0ff] text-[#2f3fd9] text-[11px] leading-tight">{s.op} →</span>}
            </div>
          ))}
        </div>
        <div className="pd-bottom pd-dark relative -mx-[22px] sm:-mx-12 -mb-8 sm:-mb-12 mt-14 px-[22px] sm:px-12 py-10">
          {fkey === "growth-compass" && reach > 0 && (
            <>
              <p className="pd-h text-[22px] text-white">One month of your business, in dots.</p>
              <p className="text-[12.5px] text-white/60 mt-1 mb-6">Each dot is one person who saw your offer; the bright ones bought.</p>
              <Dots total={Math.min(250, Math.max(50, Math.round(reach / 25) * 25))} lit={Math.max(1, Math.round((Math.min(250, reach) * conv) / 100))} />
            </>
          )}
          <div className="grid sm:grid-cols-2 gap-3 mt-8">
            <div className="pd-card-dark p-5"><p className="text-[11.5px] text-white/55">The insight</p><p className="pd-h text-[22px] text-white mt-2">{lv.insight}</p></div>
            <div className="pd-card-dark p-5"><p className="text-[11.5px] text-white/55">How we got there</p><p className="text-[14px] text-white/85 mt-2">{lv.insight_basis}</p></div>
          </div>
        </div>
      </>
    ), 4);
  }

  // 9. why nothing moved
  if ((why.items || []).length) {
    add("why", "Diagnosis", "light", () => (
      <>
        <Title a="Why nothing" b="moved the number." size="text-[44px] sm:text-[60px] mt-10" />
        <p className="text-[14px] max-w-[520px] mt-6">{why.intro}</p>
        <div className={`grid gap-3 mt-10 ${why.items.length === 3 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
          {why.items.map((x, i) => {
            const I = ICONS[i % ICONS.length];
            return (
              <div key={i} className="bg-[#eef0f6] p-5 rounded-[4px] min-h-[300px]">
                <span className="w-11 h-11 rounded-full bg-[#07080d] grid place-items-center"><I className="w-5 h-5 text-white" strokeWidth={1.7} aria-hidden /></span>
                <p className="pd-h text-[24px] mt-6">{x.title}</p>
                {x.aimed_at && <span className="inline-block rounded-[12px] px-3 py-1 border border-[#4458ff] text-[#2f3fd9] text-[11px] leading-snug mt-2">Aimed at: {x.aimed_at}</span>}
                <p className="text-[12px] font-semibold mt-5">What it did</p><p className="text-[13px] text-[#6b6f80]">{x.what_it_did}</p>
                <p className="text-[12px] font-semibold mt-3">Why the number didn't move</p><p className="text-[13px] text-[#6b6f80]">{x.why_not}</p>
              </div>
            );
          })}
        </div>
        {why.bridge && <div className="mt-10 rounded-[2px] bg-gradient-to-r from-[#07080d] via-[#1b23a8] to-[#4458ff] text-white px-6 py-6 flex flex-wrap items-center justify-between gap-3"><span className="text-[17px] pd-h">{why.bridge}</span><span className="pd-pill border border-white/50 text-[12px]">Next: where to focus</span></div>}
      </>
    ), 5);
  }

  // 10. where to focus
  add("focus", "Plan", "light", () => (
    <>
      <div className="grid sm:grid-cols-[1fr_220px] gap-6 mt-10 items-end">
        <h2 className="pd-h text-[36px] sm:text-[52px]">{fc.headline}<br /><span className="pd-accent">{fc.accent}</span></h2>
        <p className="text-[13px] text-[#2a2c38]">{fc.text}</p>
      </div>
      <div className="grid sm:grid-cols-[1fr_1.15fr] gap-8 mt-12">
        <div>
          <p className="text-[12px] font-semibold">Leave as it is</p>
          <ul className="mt-3 divide-y divide-[#e3e6ef] border-y border-[#e3e6ef]">
            {(fc.leave || []).map((x) => <li key={x} className="flex items-center justify-between py-4"><span className="pd-h text-[22px]">{x}</span><span className="pd-pill bg-[#e3f7f1] text-[#0f7a5c] text-[11px]">Working</span></li>)}
          </ul>
        </div>
        <div className="pd-dark relative rounded-[2px] p-6 -mr-[22px] sm:-mr-12 sm:-mb-12">
          <p className="text-[12px] text-white/80">Invest here</p>
          <p className="pd-h pd-grad text-[64px] sm:text-[86px] mt-2" data-testid="pd-invest">{fc.invest}</p>
          <p className="text-[13px] text-white/70 mt-2">{fc.invest_text}</p>
          <div className="space-y-2.5 mt-6">
            {(fc.channels || []).map((ch, i) => (
              <div key={i} className="pd-card-dark p-4 grid grid-cols-[80px_1fr] gap-3"><span className="text-[11px] text-white/50 pt-1">Channel {i + 1}</span><span><span className="block text-[15px] text-white">{ch.name}</span><span className="block text-[12px] text-white/60 mt-0.5">{ch.text}</span></span></div>
            ))}
          </div>
        </div>
      </div>
    </>
  ), 6);

  // 11. the 90-day plan
  add("plan", "Plan", "cobalt", () => {
    const phases = pl.phases || [];
    return (
      <>
        <div className="grid sm:grid-cols-[1fr_300px] gap-6 mt-10">
          <Title a="Your 90-day" b="plan." size="text-[44px] sm:text-[60px] text-white" />
          <p className="text-[14px] text-white/75">{pl.intro}</p>
        </div>
        <div className="relative mt-10 h-[200px] sm:h-[260px]" aria-hidden>
          <div className="absolute inset-x-0 bottom-6 flex items-end gap-2 h-full">
            {Array.from({ length: 9 }, (_, i) => (
              <div key={i} className="flex-1 relative" style={{ height: `${28 + i * 8.5}%` }}>
                <div className="absolute inset-0 border border-white/60 skew-y-[-12deg] origin-bottom-left" style={{ background: `linear-gradient(180deg, rgba(255,255,255,${0.18 + i * 0.08}), rgba(255,255,255,${0.04 + i * 0.03}))` }} />
                {[2, 5, 8].includes(i) && phases[[2, 5, 8].indexOf(i)] && (
                  <span className="absolute -top-14 left-1/2 -translate-x-1/2 text-center whitespace-nowrap">
                    <span className="block pd-h text-[24px] sm:text-[32px] text-white whitespace-nowrap">{phases[[2, 5, 8].indexOf(i)].target}</span>
                    <span className="block text-[10.5px] text-white/70">{phases[[2, 5, 8].indexOf(i)].days}</span>
                  </span>
                )}
              </div>
            ))}
          </div>
          <div className="absolute inset-x-0 bottom-0 flex justify-between text-[11px] text-white/65"><span>{pl.baseline}</span><span>{pl.metric}</span></div>
        </div>
        <div className="grid sm:grid-cols-3 gap-3 mt-8">
          {phases.map((ph, i) => (
            <div key={i} className={`p-5 rounded-[4px] border min-h-[380px] flex flex-col ${i === phases.length - 1 ? "bg-[#2733c9]/80 border-[#8b93ff]" : "bg-[#07080d]/80 border-white/20"}`} data-testid={`pd-phase-${i}`}>
              <div className="flex justify-between items-center text-[11px] text-white/70"><span className={`pd-pill border ${i === phases.length - 1 ? "bg-[#4458ff] border-[#4458ff] text-white" : "border-white/40"}`}>{ph.days}</span><span>Phase {i + 1}</span></div>
              <p className="pd-h text-[28px] text-white mt-6">{ph.name}</p>
              <p className="text-[14px] font-semibold text-white mt-1">{ph.headline}</p>
              <p className="text-[12.5px] text-white/60 mt-3">{ph.detail}</p>
              {ph.why && <><p className="text-[11.5px] text-[#7fe0d4] font-semibold mt-4 pt-4 border-t border-white/15">Why it works</p><p className="text-[12.5px] text-white/70 mt-1">{ph.why}</p></>}
              {ph.target && <div className="mt-auto pt-4 border-t border-white/15 flex items-end justify-between gap-3"><span className="text-[11px] text-white/55 min-w-0">{pl.metric || "Target"}</span><span className={`pd-h text-white whitespace-nowrap ${ph.target.length > 6 ? "text-[22px]" : "text-[28px]"}`}>{ph.target}</span></div>}
            </div>
          ))}
        </div>
      </>
    );
  }, 7);

  // 12. what it's worth
  if ((im.scenarios || []).length) {
    add("impact", "Impact", "light", () => {
      const sc = im.scenarios;
      const max = Math.max(...sc.map((s) => Math.max(s.value || 0, s.cautious || 0)), 1);
      return (
        <>
          <div className="grid sm:grid-cols-[1fr_300px] gap-6 mt-10">
            <Title a={im.headline} b={im.accent} size="text-[44px] sm:text-[60px]" />
            <p className="text-[14px]">{im.text}</p>
          </div>
          <div className="mt-12 border-b-2 border-[#2a2c38] flex items-end gap-4 sm:gap-10 h-[300px] px-2" role="img"
            aria-label={sc.map((s) => `${s.label}: ${inrShort(s.value)}${s.cautious ? `, cautious ${inrShort(s.cautious)}` : ""}`).join("; ")} data-testid="pd-impact">
            {sc.map((s, i) => (
              <div key={i} className="flex-1 flex items-end justify-center gap-2 h-full">
                {[["value", i === 0 ? "bg-[#2a2c38]" : "pd-bar"], ["cautious", "pd-hatch"]].map(([k, cls]) => (s[k] ? (
                  <div key={k} className="flex flex-col items-center justify-end h-full w-1/2 max-w-[80px]">
                    <span className="pd-h text-[16px] sm:text-[22px] mb-1 whitespace-nowrap">{inrShort(s[k])}</span>
                    <div className={`w-full ${cls}`} style={{ height: `${(s[k] / max) * 78}%` }} />
                  </div>
                ) : null))}
              </div>
            ))}
          </div>
          <div className="flex gap-4 sm:gap-10 px-2 mt-3">
            {sc.map((s, i) => <div key={i} className="flex-1"><p className="pd-h text-[17px]">{s.label}</p><p className="text-[11.5px] text-[#6b6f80]">{s.sub}</p></div>)}
          </div>
          <div className="flex flex-wrap gap-5 mt-5 text-[12px] text-[#6b6f80]">
            <span><i className="inline-block w-3 h-3 bg-[#2a2c38] mr-1.5 align-[-2px]" />Today</span>
            {im.main_label && <span><i className="inline-block w-3 h-3 pd-bar mr-1.5 align-[-2px]" />{im.main_label}</span>}
            {im.cautious_label && <span><i className="inline-block w-3 h-3 pd-hatch mr-1.5 align-[-2px]" />{im.cautious_label}</span>}
          </div>
          <div className="pd-bottom pd-dark relative -mx-[22px] sm:-mx-12 -mb-8 sm:-mb-12 mt-12 px-[22px] sm:px-12 py-10">
            <div className="grid sm:grid-cols-3 gap-6">
              {(im.highlights || []).map((h, i) => <div key={i} className="border-t border-white/30 pt-3"><p className={`pd-h text-[36px] ${i === 0 ? "pd-grad" : "text-white"}`}>{h.value}</p><p className="text-[12px] text-white/60 mt-1">{h.label}</p></div>)}
            </div>
            {im.note && <p className="text-[11.5px] text-white/45 mt-10">{im.note}</p>}
          </div>
        </>
      );
    }, 8);
  }

  // 13. next steps
  add("next", "Next steps", "cobalt", () => (
    <>
      <p className="pd-h text-[28px] sm:text-[40px] text-white/50 mt-10">{p.close?.muted}</p>
      <h2 className="pd-h text-[38px] sm:text-[56px] text-white mt-3">{p.close?.headline}{p.close?.accent && <><br /><span className="pd-grad">{p.close.accent}</span></>}</h2>
      <p className="text-[12px] text-white/70 mt-12">Next steps</p>
      <ol className="mt-3 divide-y divide-white/15 border-y border-white/15">
        {(p.next_steps || []).map((s, i) => (
          <li key={i} className="grid grid-cols-[32px_1fr] sm:grid-cols-[48px_220px_1fr_auto] gap-x-4 gap-y-1 py-4 items-center">
            <span className="text-[11px] text-white/50">{String(i + 1).padStart(2, "0")}</span>
            <span className="pd-h text-[20px] text-white">{s.title}</span>
            <span className="text-[12.5px] text-white/65 col-start-2 sm:col-start-auto">{s.detail}</span>
            <span className={`pd-pill border text-[11.5px] col-start-2 sm:col-start-auto justify-self-start sm:justify-self-end ${i === 2 ? "bg-[#4458ff] border-[#4458ff] text-white" : "border-white/40 text-white"}`}>{s.when}</span>
          </li>
        ))}
      </ol>
      <div className="pd-card-dark mt-14 p-6 max-w-[380px] bg-[#0d1020]/70">
        <p className="text-[11.5px] text-white/55">Prepared by</p>
        <p className="pd-h text-[24px] text-white mt-3">{by}</p>
        <p className="text-[12.5px] text-white/60 mt-1">{(p.prepared_by || "").split(",").slice(1).join(",").trim()}</p>
      </div>
    </>
  ), 9);

  // contents goes second; its rows point at the page each section starts on
  const contents = pages.filter((x) => x.section).reduce((acc, x) => (acc.some((y) => y.section === x.section) ? acc : [...acc, x]), []);
  pages.splice(1, 0, { id: "contents", nav: "Situation", tone: "dark", body: () => (
    <>
      <div className="flex justify-between items-start mt-10">
        <div><p className="text-[12px] text-white/70">Inside this proposal</p><h2 className="pd-h text-[56px] sm:text-[76px] text-white mt-2">Contents</h2></div>
        <span aria-hidden className="relative w-[150px] h-[150px] hidden sm:block"><span className="pd-burst w-[220px] h-[220px] -left-[35px] -top-[35px]" /></span>
      </div>
      <ol className="mt-12 -mx-[22px] sm:-mx-12 divide-y divide-white/10 border-y border-white/10">
        {contents.map((x, i) => (
          <li key={x.id} className={`grid grid-cols-[60px_1fr_auto] items-center px-[22px] sm:px-12 py-4 ${i === 3 ? "bg-gradient-to-r from-[#1b23a8] via-[#3b49ff] to-[#7fe0d4]/60" : ""}`}>
            <span className="text-[11.5px] text-white/60">({String(i + 1).padStart(2, "0")})</span>
            <span className="pd-h text-[22px] sm:text-[26px] text-white">{SECTION_TITLES[x.id]}</span>
            <span className="text-[11.5px] text-white/60 tabular">p. {String(pages.indexOf(x) + 1).padStart(2, "0")}</span>
          </li>
        ))}
      </ol>
    </>
  ) });

  const total = pages.length;
  return (
    <div className="pd-doc" data-testid="pd-doc">
      {pages.map((pg, i) => (
        <section key={pg.id} className={`pd-page pd-${pg.tone} ${pg.tone !== "light" ? "pd-grid" : ""}`} data-testid={`pd-page-${pg.id}`} aria-label={SECTION_TITLES[pg.id] || pg.id}>
          {pg.tone === "cobalt" && <span aria-hidden className="absolute inset-0 -z-10 bg-[radial-gradient(50%_40%_at_90%_0%,rgba(127,224,212,.25),transparent_70%)]" />}
          <Head by={by} active={pg.nav} n={i + 1} total={total} light={pg.tone === "light"} />
          {pg.body()}
          {pg.tone === "light" && pg.id !== "situation" && pg.id !== "lever" && pg.id !== "impact" && pg.id !== "focus" && <p className="text-[11px] text-[#9a9db0] mt-10">Prepared for {p.client}</p>}
        </section>
      ))}
    </div>
  );
}

const SECTION_TITLES = {
  cover: "Cover", contents: "Contents", situation: "Where we started", problem: "The real problem", framework: "The framework",
  diagnosis: "Your diagnosis", verdict: "Your diagnosis", lever: "Your diagnosis", why: "Why nothing moved",
  focus: "Where to focus", plan: "Your 90-day plan", impact: "What it's worth", next: "Next steps",
};
