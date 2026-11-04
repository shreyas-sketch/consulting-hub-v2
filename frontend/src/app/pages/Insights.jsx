// /app/insights and /app/insights/:id — Industry Insight Pack: trends, opportunities for your niche, talking points,
// questions to ask clients and this month's news (real links only), with a "Listen" audio version.
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Headphones } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import { CopyButton } from "../components/Markdown";
import { AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, Loadable, PageHeader, RowLink, Step, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Industry Insight Pack" ai title="What's moving in" accent="your industry." />;

function Section({ title, children }) {
  return (
    <div className="mt-6">
      <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-2.5">{title}</p>
      {children}
    </div>
  );
}

function Listen({ p }) {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const [url, setUrl] = useState(p.audio_url);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  useEffect(() => { setUrl(p.audio_url); setErr(""); }, [p.id, p.audio_url]);
  const usage = plan?.limits?.audio;
  const canRun = !!url || !usage || usage.limit == null || usage.used < usage.limit;
  const make = async () => {
    setBusy(true); setErr("");
    try {
      const { data } = await api.post(`/insights/${p.id}/audio`);
      setUrl(data.audio_url);
      qc.setQueryData(["insight", p.id], (old) => (old ? { ...old, audio_url: data.audio_url } : old));
      if (!data.cached) refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <div className="no-print mt-4 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
      {url ? (
        <>
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-teal mb-2">Listen to this pack</p>
          <audio controls src={url} className="w-full" data-testid="insight-audio" />
        </>
      ) : (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3">
          <Button variant="ai" onClick={make} loading={busy} disabled={!canRun} data-testid="insight-listen">
            {!busy && <Headphones className="w-4 h-4" aria-hidden />}Listen
          </Button>
          <div className="min-w-0">
            <p className="text-[14px]">{busy ? "Making the audio. This takes about a minute." : "Hear this pack on your walk or drive, about five minutes."}</p>
            <UsageLine usage={usage} what="audio versions" />
          </div>
        </div>
      )}
      <ErrorLine>{err}</ErrorLine>
    </div>
  );
}

export function PackBody({ p }) {
  return (
    <AiFrame title="Industry Insight Pack" className="print-plain rise-in" right={<span className="text-[12px] text-bz-muted">{hdate(p.at)}</span>}>
      <p className="text-[13px] font-bold text-bz-muted">{p.industry}{p.niche ? ` · for ${p.niche}` : ""}</p>
      <h2 className="mt-1 text-[24px] sm:text-[28px] font-extrabold leading-tight tracking-[-0.01em]" data-testid="insight-headline">{p.headline}</h2>
      <Listen p={p} />

      <Section title="Three trends">
        <div className="space-y-3.5">{p.trends.map((t, i) => <Step key={t.trend} n={i + 1} ai title={t.trend}>{t.why_it_matters}</Step>)}</div>
      </Section>

      <Section title="Opportunities for you">
        <ul className="space-y-2">
          {p.opportunities.map((o) => <li key={o} className="flex gap-2.5 text-[15px] leading-snug"><span className="text-bz-gold font-extrabold" aria-hidden>•</span><span className="min-w-0">{o}</span></li>)}
        </ul>
      </Section>

      <Section title="Say this in your next client conversation">
        <ul className="space-y-2">
          {p.talking_points.map((t) => (
            <li key={t} className="rounded-bzcard border border-bz-line bg-bz-panel p-3 flex items-start gap-2">
              <span className="min-w-0 flex-1 text-[15px] leading-snug">{t}</span>
              <span className="no-print"><CopyButton text={t} /></span>
            </li>
          ))}
        </ul>
      </Section>

      <Section title="Questions to ask clients">
        <ol className="space-y-1.5 text-[15px] list-decimal pl-5 marker:text-bz-gold marker:font-bold">{p.questions_to_ask_clients.map((q) => <li key={q}>{q}</li>)}</ol>
      </Section>

      <Section title="In the news">
        {p.news?.length ? (
          <ul className="space-y-3" data-testid="insight-news">
            {p.news.map((n) => (
              <li key={n.url} className="rounded-bzcard border border-bz-line bg-bz-panel p-3">
                <a href={n.url} target="_blank" rel="noopener noreferrer" className="font-bold text-[15px] hover:text-bz-teal inline-flex gap-1.5 items-start">
                  {n.title}<ExternalLink className="w-3.5 h-3.5 mt-1 shrink-0 text-bz-teal" aria-hidden />
                </a>
                <p className="text-[12px] text-bz-muted mt-0.5">{n.source}{n.published ? ` · ${n.published}` : ""}</p>
                {n.why && <p className="text-[14px] mt-1.5">{n.why}</p>}
              </li>
            ))}
          </ul>
        ) : <p className="text-[14px] text-bz-muted">{p.live_news ? "No news worth flagging this time." : "Made without live news this time. Check the news before you quote anything."}</p>}
        {p.test && <p className="text-[12px] text-bz-muted mt-2">Test mode: these are sample links, not real news.</p>}
      </Section>
    </AiFrame>
  );
}

function PackView({ id }) {
  const q = useQuery({ queryKey: ["insight", id], queryFn: async () => (await api.get(`/insights/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/insights">All packs</BackLink>
      <Loadable q={q} what="this pack" lines={10}>{(p) => <PackBody p={p} />}</Loadable>
      <Button variant="secondary" className="no-print" onClick={() => window.print()} data-testid="insight-print">Print or save as PDF</Button>
    </div>
  );
}

export default function Insights() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { plan, refreshMe } = useAuth();
  const list = useQuery({ queryKey: ["insights"], queryFn: async () => (await api.get("/insights")).data });
  const [industry, setIndustry] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.insight;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const value = industry ?? list.data?.industry ?? "";

  const run = async (e) => {
    e.preventDefault();
    if (value.trim().length < 2) { setErr("Type the industry you work in."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/insights", { industry: value.trim() });
      qc.setQueryData(["insight", data.id], data);
      qc.invalidateQueries({ queryKey: ["insights"] }); refreshMe();
      nav(`/app/insights/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };

  return (
    <Gate feature="insight_pack" header={HEADER}>
      {id ? <PackView id={id} /> : (
        <div className="space-y-5">
          <PageHeader kicker="Industry Insight Pack" ai title="What's moving in" accent="your industry."
            sub="Three trends, three openings for a consultant like you, five things to say and three questions to ask. With this month's news and an audio version." />
          {busy ? <AiFrame title="Industry Insight Pack"><Thinking label={`Reading this month's news on ${value}`} /></AiFrame> : (
            <Card>
              <form onSubmit={run} noValidate className="space-y-3">
                <Field label="Industry" hint={list.data?.industry ? "From your Starting Point. Change it if you like." : "For example: FMCG, auto components, private hospitals."}>
                  <Input value={value} onChange={(e) => setIndustry(e.target.value)} maxLength={80} placeholder="e.g. FMCG distribution" data-testid="insight-industry" />
                </Field>
                <ErrorLine>{err}</ErrorLine>
                <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="insight-make">Make my Insight Pack</Button>
                <UsageLine usage={usage} what="Insight Packs" className="text-center" />
              </form>
            </Card>
          )}
          <Loadable q={list} what="your packs">
            {(d) => (d.items || []).length ? (
              <Card>
                <Label>Your packs</Label>
                {d.items.map((p) => (
                  <RowLink key={p.id} to={`/app/insights/${p.id}`} title={p.headline} sub={`${p.industry} · ${hdate(p.at)}`} testid={`insight-${p.id}`}
                    right={p.has_audio ? <Chip tone="teal">Audio</Chip> : <Chip tone="teal">Open</Chip>} />
                ))}
              </Card>
            ) : null}
          </Loadable>
        </div>
      )}
    </Gate>
  );
}
