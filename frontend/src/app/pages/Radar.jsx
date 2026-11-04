// /app/radar — Opportunity Radar: industry (+ city) in, up to 5 companies a run showing a sign they may need help
// (expansion, new plant, funding, leadership change, losses, layoffs, new rules). Every link comes from the news
// search. Each company links to a Meeting Brief (/app/brief?company=) and the Outreach Drafter.
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { Gate, UsageLine } from "../components/common";
import {
  AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Note, OkLine, PageHeader, Segmented, Thinking,
} from "../components/ui";

const smallLink = "inline-flex items-center justify-center min-h-[40px] px-4 rounded-full border border-bz-line bg-bz-raised text-[13px] font-bold hover:border-bz-line-strong";

function CompanyCard({ c, onStatus }) {
  const ctx = [c.summary, c.news?.title ? `Saw this in the news: ${c.news.title}` : ""].filter(Boolean).join(" ");
  return (
    <li className="rounded-bzcard border border-bz-line bg-bz-card p-4" data-testid={`radar-company-${c.id}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[18px] font-extrabold leading-tight min-w-0">{c.company}</p>
        <Chip tone="gold" className="shrink-0">{c.signal_label}</Chip>
      </div>
      {c.summary && <p className="text-[14.5px] mt-1.5">{c.summary}</p>}
      {c.news?.url && (
        <a href={c.news.url} target="_blank" rel="noopener noreferrer" className="mt-2.5 block rounded-bzcard border border-bz-line bg-bz-panel p-3 hover:border-bz-line-strong">
          <span className="font-bold text-[14px] inline-flex gap-1.5 items-start">{c.news.title}<ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0 text-bz-teal" aria-hidden /></span>
          <span className="block text-[12px] text-bz-muted mt-0.5">{c.news.source}{c.news.published ? ` · ${c.news.published}` : ""}</span>
        </a>
      )}
      <div className="mt-3 space-y-1.5 text-[14px]">
        <p><span className="text-bz-muted">Why it matters: </span>{c.why}</p>
        {c.angle && <p className="text-bz-teal">Angle: {c.angle}</p>}
      </div>
      {c.test && <Note className="mt-2">Test mode: sample news, not a real company.</Note>}
      <div className="mt-3 flex flex-wrap gap-2">
        <Link to={`/app/brief?company=${encodeURIComponent(c.company)}`} className={smallLink} data-testid={`radar-brief-${c.id}`}>Meeting Brief</Link>
        <Link to={`/app/outreach?company=${encodeURIComponent(c.company)}&context=${encodeURIComponent(ctx.slice(0, 900))}`} className={smallLink} data-testid={`radar-outreach-${c.id}`}>Draft outreach</Link>
        {c.status !== "saved" && <Button variant="small" onClick={() => onStatus(c, "saved")}>Save</Button>}
        {c.status !== "dismissed" ? <Button variant="small" onClick={() => onStatus(c, "dismissed")}>Not relevant</Button>
          : <Button variant="small" onClick={() => onStatus(c, "new")}>Bring back</Button>}
      </div>
    </li>
  );
}

function Body() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const [view, setView] = useState("");
  const q = useQuery({ queryKey: ["radar", view], queryFn: async () => (await api.get("/radar", { params: { status: view || undefined } })).data });
  const [f, setF] = useState({ industry: "", city: "", niche: "" });
  const [seeded, setSeeded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const usage = plan?.limits?.radar;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  useEffect(() => {
    if (!seeded && q.data?.defaults) { setF((x) => ({ ...x, industry: x.industry || q.data.defaults.industry, niche: x.niche || q.data.defaults.niche })); setSeeded(true); }
  }, [q.data, seeded]);

  const run = async (e) => {
    e.preventDefault();
    if (f.industry.trim().length < 2) { setErr("Type the industry to watch, e.g. pharma or auto parts."); return; }
    setErr(""); setOk(""); setBusy(true);
    try {
      const { data } = await api.post("/radar/run", f);
      const n = data.found.length;
      setOk(n ? `Found ${n} new ${n === 1 ? "company" : "companies"}.` : "No new companies this time. Try another city or a nearby industry. Nothing was used up.");
      setView(""); qc.invalidateQueries({ queryKey: ["radar"] }); refreshMe();
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  const setStatus = async (c, status) => {
    try { await api.patch(`/radar/${c.id}`, { status }); qc.invalidateQueries({ queryKey: ["radar"] }); } catch { /* ignore */ }
  };

  return (
    <div className="space-y-4">
      {busy ? <AiFrame title="Opportunity Radar"><Thinking label={`Reading this month's news on ${f.industry}`} /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-3">
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Industry"><Input value={f.industry} onChange={(e) => setF({ ...f, industry: e.target.value })} maxLength={80} placeholder="e.g. Pharma" data-testid="radar-industry" /></Field>
              <Field label="City (optional)"><Input value={f.city} onChange={(e) => setF({ ...f, city: e.target.value })} maxLength={60} placeholder="e.g. Pune" data-testid="radar-city" /></Field>
            </div>
            <Field label="Your niche (optional)" hint="Helps pick the signals that matter for the work you do."><Input value={f.niche} onChange={(e) => setF({ ...f, niche: e.target.value })} maxLength={160} /></Field>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="radar-run">Find companies</Button>
            <UsageLine usage={usage} what="companies found" className="text-center" />
            <Note className="text-center">Up to 5 companies a run. You only use up the ones found.</Note>
          </form>
        </Card>
      )}
      <OkLine>{ok}</OkLine>
      <Loadable q={q} what="your companies" lines={4}>
        {(d) => (
          <div className="space-y-3">
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <Label className="mb-0">Companies to watch</Label>
              <Segmented label="Show" value={view} onChange={setView} testid="radar-view"
                options={[{ value: "", label: "All" }, { value: "saved", label: "Saved" }, { value: "dismissed", label: "Not relevant" }]} />
            </div>
            {(d.items || []).length ? (
              <ul className="space-y-3">{d.items.map((c) => <CompanyCard key={c.id} c={c} onStatus={setStatus} />)}</ul>
            ) : <Empty title={view ? "Nothing here yet" : "No companies yet"} sub={view ? "" : "Run the radar for your industry. Companies showing a change in the news appear here."} />}
            {(d.runs || []).length > 0 && (
              <Note>Last runs: {d.runs.slice(0, 3).map((r) => `${r.input.industry}${r.input.city ? `, ${r.input.city}` : ""} (${r.found} found, ${hdate(r.at)})`).join(" · ")}</Note>
            )}
          </div>
        )}
      </Loadable>
    </div>
  );
}

export default function Radar() {
  return (
    <div className="space-y-5">
      <PageHeader kicker="Opportunity Radar" ai title="Companies that may" accent="need you now."
        sub="We read recent news for signs of change: expansion, a new plant, funding, a new leader, losses, layoffs or new rules. You get the company, the link and a way to open the conversation." />
      <Gate feature="radar"><Body /></Gate>
    </div>
  );
}
