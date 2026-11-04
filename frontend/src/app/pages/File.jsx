// /app/file — My Consulting File: everything the member has made, on one page. Print or save as PDF from the browser.
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Check, Copy, FileText, Printer } from "lucide-react";
import { Link } from "react-router-dom";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate, inr } from "@/lib/format";
import { Button, Card, Empty, Label, LinkButton, Loadable, Meter, PageHeader } from "../components/ui";

const SKILL_NAME = { diagnosis: "Problem diagnosis", offer: "Offer clarity", acquisition: "Client acquisition", pricing: "Pricing confidence", delivery: "Delivery & frameworks", visibility: "Visibility & authority" };

function Row({ k, v }) {
  if (!v) return null;
  return (
    <div className="py-2.5 border-b border-bz-line last:border-0 grid sm:grid-cols-[180px_1fr] gap-1 sm:gap-4">
      <dt className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-muted pt-0.5">{k}</dt>
      <dd className="text-[15px]">{v}</dd>
    </div>
  );
}

function CopyBlueprint({ text }) {
  const [ok, setOk] = useState(false);
  if (!text) return null;
  return (
    <Button variant="secondary" className="no-print" onClick={async () => { try { await navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1800); } catch { /* blocked */ } }}>
      {ok ? <Check className="w-4 h-4" aria-hidden /> : <Copy className="w-4 h-4" aria-hidden />}{ok ? "Copied" : "Copy my Niche Blueprint"}
    </Button>
  );
}

export default function File() {
  const { user } = useAuth();
  const q = useQuery({ queryKey: ["file"], queryFn: async () => (await api.get("/file")).data });
  return (
    <div className="space-y-5">
      <PageHeader kicker="My Consulting File" title="Everything you've made," accent="in one place."
        right={<Button variant="small" className="no-print" onClick={() => window.print()} data-testid="file-print"><Printer className="w-4 h-4" aria-hidden />Print or PDF</Button>} />
      <Loadable q={q} what="your file" lines={8}>
        {(f) => {
          const k = f.knowledge || {};
          const empty = !f.readiness && !f.snapshot && !f.goal && !(f.cases || []).length && !(f.briefs || []).length && !f.linkedin;
          if (empty) {
            return <Empty icon={FileText} title="Nothing here yet" sub="Start with your Readiness Score. Everything you make in the tools is saved here."
              action={<LinkButton to="/app/readiness">Score my readiness</LinkButton>} />;
          }
          return (
            <div className="space-y-4 print-plain">
              <Card>
                <Label>{user?.name || "Consultant"} · {hdate(new Date().toISOString())}</Label>
                {k.consultant_title ? <p className="text-[24px] font-extrabold leading-tight">{k.consultant_title}</p> : <p className="text-[18px] font-bold">Pick a niche in Starting Point to complete your profile.</p>}
                <dl className="mt-3">
                  <Row k="Niche" v={k.niche} />
                  <Row k="Value proposition" v={k.value_proposition} />
                  <Row k="Who you help" v={k.target_audience} />
                  <Row k="Industry" v={k.target_industry} />
                  <Row k="Income goal" v={k.consulting_goal} />
                </dl>
                <div className="mt-4"><CopyBlueprint text={k.blueprint} /></div>
                {k.blueprint && <p className="text-[12px] text-bz-muted mt-2 no-print">Paste it into any of Akshat's GPTs that ask for your Niche Blueprint.</p>}
              </Card>

              {f.readiness && (
                <Card>
                  <div className="flex items-baseline justify-between gap-3">
                    <Label className="mb-0">Readiness Score</Label>
                    <span className="text-[24px] font-extrabold text-bz-gold tabular">{f.readiness.total}<span className="text-[13px] text-bz-muted">/60</span></span>
                  </div>
                  <p className="text-[15px] font-bold mt-1">{f.readiness.band}</p>
                  <div className="mt-3 grid gap-2.5 sm:grid-cols-2">
                    {Object.entries(f.readiness.scores).map(([s, v]) => (
                      <div key={s}><div className="flex justify-between text-[13px]"><span>{SKILL_NAME[s] || s}</span><span className="font-bold tabular">{v}/10</span></div><Meter value={v * 10} className="mt-1 h-1.5" /></div>
                    ))}
                  </div>
                </Card>
              )}

              {f.goal && (
                <Card>
                  <Label>Goal Map</Label>
                  <p className="text-[15px]"><b className="text-bz-gold">{inr(f.goal.monthly_goal_inr)}</b> a month at <b className="text-bz-gold">{inr(f.goal.fee_inr)}</b> per client means
                    <b> {f.goal.clients_per_month} clients</b>, <b>{f.goal.discovery_calls_per_month} discovery calls</b> and <b>{f.goal.conversations_per_week} conversations a week</b>.</p>
                  <p className="text-[12px] text-bz-muted mt-1">{f.goal.label}</p>
                </Card>
              )}

              {(f.cases || []).length > 0 && (
                <Card>
                  <Label>Cases solved</Label>
                  {f.cases.map((c) => (
                    <div key={c.case_id + c.at} className="flex justify-between gap-3 py-2 border-b border-bz-line last:border-0">
                      <Link to={`/app/cases/${c.case_id}`} className="text-[15px] font-bold hover:text-bz-gold">{c.title}</Link>
                      <span className="text-[16px] font-extrabold text-bz-gold tabular shrink-0">{c.overall}/10</span>
                    </div>
                  ))}
                </Card>
              )}

              {f.linkedin && (
                <Card>
                  <div className="flex items-baseline justify-between gap-3">
                    <Label className="mb-0">LinkedIn Score</Label>
                    <span className="text-[24px] font-extrabold text-bz-gold tabular">{f.linkedin.score}<span className="text-[13px] text-bz-muted">/100</span></span>
                  </div>
                  <ul className="mt-2 space-y-1 text-[14px] list-disc pl-5">{f.linkedin.problems.map((p) => <li key={p.key}>{p.tip}</li>)}</ul>
                </Card>
              )}

              {(f.briefs || []).length > 0 && (
                <Card>
                  <Label>Meeting Briefs</Label>
                  {f.briefs.map((b) => (
                    <div key={b.id} className="py-2 border-b border-bz-line last:border-0">
                      <Link to={`/app/brief/${b.id}`} className="text-[15px] font-bold hover:text-bz-gold">{b.input.company}</Link>
                      <p className="text-[13px] text-bz-muted">{hdate(b.at)} · {b.questions.length} questions · {b.news.length} news links</p>
                    </div>
                  ))}
                </Card>
              )}
            </div>
          );
        }}
      </Loadable>
    </div>
  );
}
