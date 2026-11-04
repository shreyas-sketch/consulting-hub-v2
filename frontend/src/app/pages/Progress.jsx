// /app/progress and /app/progress/:id — Progress Report: once a month, what moved in the last 30 days (numbers from
// your own work), a short note and three things to work on next. Print or save as PDF.
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Printer, TrendingUp } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate, inr, monthLabel } from "@/lib/format";
import Markdown from "../components/Markdown";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Label, Loadable, Note, PageHeader, RowLink, Stat, Step, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Progress Report" title="How far you've come" accent="this month."
  sub="Once a month: what moved in your last 30 days, in numbers from your own work, and the three things to work on next." />;

const signed = (v, unit = "") => (v == null ? null : `${v > 0 ? "+" : v < 0 ? "−" : ""}${Math.abs(v)}${unit}`);

export function ReportBody({ r }) {
  const s = r.stats || {};
  const rd = s.readiness;
  const c = s.cases || {};
  const li = s.linkedin;
  const m = s.made || {};
  const g = s.goal;
  const made = [["Decks", m.decks], ["Visuals", m.visuals], ["Audio", m.audio]].filter(([, n]) => n > 0);
  return (
    <div className="space-y-4 print-plain" data-testid="progress-report">
      <Card>
        <Label>{monthLabel(r.month)} · last 30 days to {hdate(s.window?.to)}</Label>
        <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
          <Stat label="Readiness Score" value={rd ? `${rd.now}/60` : "—"}
            sub={rd ? (rd.change != null ? `${signed(rd.change)} since last time · ${rd.band}` : rd.band) : "Not done yet"} />
          <Stat label="Cases solved" value={c.solved ?? 0} sub={`${c.prev_solved ?? 0} in the 30 days before`} />
          <Stat label="Average case score" value={c.avg != null ? `${c.avg}/10` : "—"}
            sub={c.avg_change != null ? `${signed(c.avg_change)} on the 30 days before` : c.prev_avg != null ? `${c.prev_avg}/10 before` : "Solve a case to see it"} />
          <Stat label="Meeting Briefs" value={s.briefs?.made ?? 0} sub={`${s.briefs?.prev ?? 0} in the 30 days before`} />
          <Stat label="LinkedIn Score" value={li ? `${li.now}/100` : "—"} sub={li ? (li.change != null ? `${signed(li.change)} since before` : "First check") : "Not checked yet"} />
          {made.map(([k, n]) => <Stat key={k} label={`${k} made`} value={n} />)}
        </div>
        {(s.tools || []).length > 0 && (
          <div className="mt-4">
            <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-muted mb-2">Tools you used</p>
            <div className="flex flex-wrap gap-2">{s.tools.map((t) => <Chip key={t.key} tone="gold">{t.label} · {t.uses}</Chip>)}</div>
          </div>
        )}
      </Card>
      {g && (
        <Card>
          <Label>Your Goal Map</Label>
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <Stat label="Monthly goal" value={inr(g.monthly_goal_inr)} />
            <Stat label="Clients a month" value={g.clients_per_month} sub={`at ${inr(g.fee_inr)} each`} />
            <Stat label="Discovery calls" value={g.discovery_calls_per_month} sub="a month" />
            <Stat label="Conversations" value={g.conversations_per_week} sub="a week" />
          </div>
          <Note className="mt-2">{g.label}</Note>
        </Card>
      )}
      <AiFrame title="Your month in words">
        <Markdown text={r.summary} />
      </AiFrame>
      <Card>
        <Label>Three things for next month</Label>
        <div className="space-y-4">{(r.focus || []).map((f, i) => <Step key={f.title} n={i + 1} title={f.title}>{f.why}</Step>)}</div>
      </Card>
    </div>
  );
}

function ReportView({ id }) {
  const q = useQuery({ queryKey: ["progress", id], queryFn: async () => (await api.get(`/progress/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/progress">All reports</BackLink>
      <PageHeader kicker="Progress Report" title="How far you've come" accent="this month."
        right={<Button variant="small" className="no-print" onClick={() => window.print()} data-testid="progress-print"><Printer className="w-4 h-4" aria-hidden />Print or PDF</Button>} />
      <Loadable q={q} what="this report" lines={8}>{(r) => <ReportBody r={r} />}</Loadable>
      <Button variant="secondary" className="no-print w-full sm:w-auto" onClick={() => window.print()}>Print or save as PDF</Button>
    </div>
  );
}

function ProgressHome() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["progress-list"], queryFn: async () => (await api.get("/progress")).data });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.progress;

  const make = async () => {
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/progress");
      qc.setQueryData(["progress", data.id], data); qc.invalidateQueries({ queryKey: ["progress-list"] }); refreshMe();
      nav(`/app/progress/${data.id}`);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {HEADER}
      <Loadable q={list} what="your reports" lines={4}>
        {(d) => (
          <>
            {busy ? <AiFrame title="Progress Report"><Thinking label="Reading your month" /></AiFrame> : d.made_this_month ? (
              <Card inset>
                <p className="font-bold text-[16px]">This month's report is ready.</p>
                <p className="text-[14px] text-bz-muted mt-1">The next one opens on the 1st.</p>
                {d.items?.[0] && <Button variant="secondary" className="mt-4" onClick={() => nav(`/app/progress/${d.items[0].id}`)} data-testid="progress-open">Open this month's report</Button>}
              </Card>
            ) : (
              <Card>
                <p className="text-[15px]">Your report looks at the last 30 days: Readiness Score, cases and scores, briefs, LinkedIn Score and the tools you used. Every number comes from your own work.</p>
                <ErrorLine>{err}</ErrorLine>
                <Button variant="ai" className="w-full mt-4" onClick={make} data-testid="progress-run">Make my report</Button>
                <UsageLine usage={usage} what="reports" className="text-center mt-2" />
              </Card>
            )}
            {(d.items || []).length ? (
              <Card>
                <Label>Your reports</Label>
                {d.items.map((r) => (
                  <RowLink key={r.id} to={`/app/progress/${r.id}`} title={monthLabel(r.month)} testid={`progress-${r.id}`}
                    sub={`${r.readiness != null ? `Readiness ${r.readiness}/60 · ` : ""}${r.cases_solved} cases solved · made ${hdate(r.at)}`} />
                ))}
              </Card>
            ) : <Empty icon={TrendingUp} title="No reports yet" sub="Make your first one now. It takes about a minute." />}
          </>
        )}
      </Loadable>
    </div>
  );
}

export default function Progress() {
  const { id } = useParams();
  return <Gate feature="progress" header={HEADER}>{id ? <ReportView id={id} /> : <ProgressHome />}</Gate>;
}
