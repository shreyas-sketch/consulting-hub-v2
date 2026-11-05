// /app/brief and /app/brief/:id — Meeting Brief: company in, one-page brief out (news with real links, likely problems,
// questions to ask, an opening line). Past briefs listed under the form.
import { useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, PageHeader, RowLink, Step, Thinking } from "../components/ui";

export function BriefBody({ b }) {
  return (
    <AiFrame title="Meeting Brief" right={<span className="text-[12px] text-bz-muted">{hdate(b.at)}</span>} className="print-plain">
      <p className="text-[24px] font-display font-[500] tracking-[-0.01em] leading-tight">{b.input.company}</p>
      {(b.input.meeting_with || b.input.purpose) && <p className="text-[14px] text-bz-muted mt-1">{[b.input.meeting_with && `Meeting: ${b.input.meeting_with}`, b.input.purpose].filter(Boolean).join(" · ")}</p>}
      <p className="text-[15px] mt-3 leading-relaxed">{b.about}</p>

      <div className="mt-5">
        <p className="text-[12px] font-semibold text-bz-teal mb-2">Recent news</p>
        {b.news?.length ? (
          <ul className="space-y-3">
            {b.news.map((n) => (
              <li key={n.url} className="rounded-bzcard border border-bz-line bg-bz-panel p-3">
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="font-bold text-[15px] hover:text-bz-teal inline-flex gap-1.5 items-start">
                  {n.title}<ExternalLink className="w-3.5 h-3.5 mt-1 shrink-0 text-bz-teal" aria-hidden />
                </a>
                <p className="text-[12px] text-bz-muted mt-0.5">{n.source}{n.published ? ` · ${n.published}` : ""}</p>
                {n.why && <p className="text-[14px] mt-1.5">{n.why}</p>}
              </li>
            ))}
          </ul>
        ) : <p className="text-[14px] text-bz-muted">{b.live_news ? "No news worth flagging." : "Made without live news. Search the company before the meeting."}</p>}
        {b.test && <p className="text-[12px] text-bz-muted mt-2">Test mode: these are sample links, not real news.</p>}
      </div>

      <div className="mt-5">
        <p className="text-[12px] font-semibold text-bz-teal mb-2">Likely problems</p>
        <div className="space-y-3">{b.problems.map((p, i) => <Step key={p.problem} n={i + 1} ai title={p.problem}>{p.why}</Step>)}</div>
      </div>

      <div className="mt-5">
        <p className="text-[12px] font-semibold text-bz-teal mb-2">Questions to ask</p>
        <ol className="space-y-1.5 text-[15px] list-decimal pl-5">{b.questions.map((q) => <li key={q}>{q}</li>)}</ol>
      </div>

      {b.opening && (
        <div className="mt-5 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
          <p className="text-[12px] font-semibold text-bz-teal mb-1">Opening line</p>
          <p className="text-[15px] italic">“{b.opening}”</p>
        </div>
      )}
    </AiFrame>
  );
}

export function BriefView() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["brief", id], queryFn: async () => (await api.get(`/briefs/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/brief">All briefs</BackLink>
      <Loadable q={q} what="this brief" lines={8}>{(b) => <BriefBody b={b} />}</Loadable>
      <Button variant="secondary" className="no-print" onClick={() => window.print()}>Print or save as PDF</Button>
    </div>
  );
}

export default function Brief() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["briefs"], queryFn: async () => (await api.get("/briefs")).data });
  const [params] = useSearchParams();
  const [f, setF] = useState({ company: (params.get("company") || "").slice(0, 120), website: "", meeting_with: "", purpose: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.brief;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const run = async (e) => {
    e.preventDefault();
    if (f.company.trim().length < 2) { setErr("Type the company's name."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/briefs", f);
      qc.setQueryData(["brief", data.id], data);
      qc.invalidateQueries({ queryKey: ["briefs"] }); qc.invalidateQueries({ queryKey: ["file"] }); refreshMe();
      nav(`/app/brief/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <div className="space-y-5">
      <PageHeader kicker="Meeting Brief" ai title="Walk into any meeting" accent="already prepared."
        sub="Type the company you're meeting. In about a minute you get recent news with links, the problems they likely have, questions to ask and an opening line." />
      {busy ? <AiFrame title="Meeting Brief"><Thinking label={`Reading the news on ${f.company}`} /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-3">
            <Field label="Company"><Input value={f.company} onChange={(e) => setF({ ...f, company: e.target.value })} placeholder="e.g. Haldiram's" maxLength={120} data-testid="brief-company" /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Website (optional)"><Input value={f.website} onChange={(e) => setF({ ...f, website: e.target.value })} placeholder="haldirams.com" maxLength={200} /></Field>
              <Field label="Who you're meeting (optional)"><Input value={f.meeting_with} onChange={(e) => setF({ ...f, meeting_with: e.target.value })} placeholder="e.g. Head of Operations" maxLength={120} /></Field>
            </div>
            <Field label="What the meeting is about (optional)"><Input value={f.purpose} onChange={(e) => setF({ ...f, purpose: e.target.value })} placeholder="e.g. First conversation about their supply chain" maxLength={300} /></Field>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="brief-run">Make my brief</Button>
            <UsageLine usage={usage} what="briefs" className="text-center" />
          </form>
        </Card>
      )}
      <Loadable q={list} what="your briefs">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your briefs</Label>
            {d.items.map((b) => <RowLink key={b.id} to={`/app/brief/${b.id}`} title={b.company} sub={hdate(b.at)} testid={`brief-${b.id}`} right={<Chip tone="teal">Open</Chip>} />)}
          </Card>
        ) : null}
      </Loadable>
    </div>
  );
}
