// /app/program — the 4-3-2-1 action program (L1, month 1): days with live sessions, tasks to tick, and the coach.
// After month 1 the coach card points to Support (L2 members keep the coach while L2 is on).
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, FileText, MessageCircle, PlayCircle, Video } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { dtime, hdate } from "@/lib/format";
import { Gate } from "../components/common";
import { Card, Chip, Empty, ErrorLine, Label, LinkButton, Loadable, Meter, Note, PageHeader } from "../components/ui";

const KEY = ["program"];

function ExtLink({ href, icon: Icon, children, testid }) {
  if (!href) return null;
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" data-testid={testid}
      className="inline-flex items-center gap-1.5 min-h-[44px] px-4 rounded-bzbtn border border-bz-line bg-bz-raised text-[14px] font-bold hover:border-bz-line-strong">
      <Icon className="w-4 h-4 text-bz-gold" aria-hidden /> {children}
    </a>
  );
}

function CoachCard({ p }) {
  if (p.coach_status === "ended") {
    return (
      <Card inset data-testid="program-coach-ended">
        <Label tone="muted">Your coach</Label>
        <p className="text-[16px] font-bold">{p.coach_note}</p>
        <LinkButton to={p.support_link || "/app/support"} variant="secondary" className="w-full sm:w-auto mt-3" data-testid="program-support-link">Open Support</LinkButton>
      </Card>
    );
  }
  if (!p.coach) {
    return (
      <Card inset data-testid="program-coach-pending">
        <Label tone="muted">Your coach</Label>
        <p className="text-[15px]">Your coach's name and WhatsApp number will show here soon.</p>
      </Card>
    );
  }
  return (
    <Card className="border-bz-rule" data-testid="program-coach">
      <Label>Your coach</Label>
      <p className="text-[22px] font-display font-[500] leading-tight">{p.coach.name}</p>
      <p className="text-[14px] text-bz-muted mt-1">
        {p.coach_until ? `With you until ${hdate(p.coach_until)}. Ask about your tasks, your niche or your next step.` : "With you while your L2 Mentorship runs."}
      </p>
      {p.coach.whatsapp_link && (
        <a href={p.coach.whatsapp_link} target="_blank" rel="noopener noreferrer" data-testid="program-coach-whatsapp"
          className="mt-4 inline-flex w-full sm:w-auto items-center justify-center gap-2 min-h-[52px] px-6 rounded-bzbtn bg-bz-gold text-bz-on-accent font-extrabold text-[16px] hover:opacity-90 shadow-goldglow">
          <MessageCircle className="w-5 h-5" aria-hidden /> Message {p.coach.name.split(" ")[0]} on WhatsApp
        </a>
      )}
    </Card>
  );
}

function Task({ t, onToggle, busy }) {
  return (
    <li>
      <button type="button" onClick={() => onToggle(t)} disabled={busy} aria-pressed={t.done} data-testid={`program-task-${t.id}`}
        className="w-full flex items-start gap-3 text-left min-h-[48px] py-2.5 px-1 rounded-bzbtn hover:bg-bz-raised disabled:opacity-60">
        <span className={`mt-0.5 w-6 h-6 shrink-0 rounded-md border grid place-items-center ${t.done ? "bg-bz-gold border-bz-gold text-bz-on-accent" : "border-bz-line-strong"}`}>
          {t.done && <Check className="w-4 h-4" strokeWidth={3} aria-hidden />}
        </span>
        <span className={`text-[15px] leading-snug ${t.done ? "text-bz-muted line-through" : ""}`}>{t.text}</span>
      </button>
    </li>
  );
}

function Day({ d, next, onToggle, busyId }) {
  const all = d.total > 0 && d.done === d.total;
  return (
    <Card className={next ? "border-bz-rule" : ""} data-testid={`program-day-${d.n}`}>
      <div className="flex items-start gap-3">
        <span className={`w-[38px] h-[38px] shrink-0 rounded-full border grid place-items-center text-[15px] font-extrabold ${all ? "bg-bz-gold border-bz-gold text-bz-on-accent" : "border-bz-gold text-bz-gold"}`}>
          {all ? <Check className="w-5 h-5" strokeWidth={3} aria-hidden /> : d.n}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-[12px] font-semibold text-bz-muted">Day {d.n}</span>
            {next && <Chip tone="gold">Next</Chip>}
            {d.total > 0 && <span className="text-[12px] text-bz-muted tabular">{d.done} of {d.total} done</span>}
          </div>
          <p className="text-[18px] font-extrabold leading-snug mt-0.5">{d.title}</p>
          {d.when && <p className="text-[14px] text-bz-muted mt-0.5">{dtime(d.when)} IST</p>}
        </div>
      </div>
      {(d.link || d.recording_url || d.workbook_url) && (
        <div className="flex flex-wrap gap-2 mt-3">
          <ExtLink href={d.link} icon={Video} testid={`program-join-${d.n}`}>Join the session</ExtLink>
          <ExtLink href={d.recording_url} icon={PlayCircle}>Recording</ExtLink>
          <ExtLink href={d.workbook_url} icon={FileText}>Workbook</ExtLink>
        </div>
      )}
      {d.tasks.length > 0 && (
        <ul className="mt-3 border-t border-bz-line pt-2">
          {d.tasks.map((t) => <Task key={t.id} t={t} onToggle={onToggle} busy={busyId === t.id} />)}
        </ul>
      )}
    </Card>
  );
}

function Body({ p }) {
  const qc = useQueryClient();
  const [busyId, setBusyId] = useState(null);
  const [err, setErr] = useState("");
  const toggle = async (t) => {
    setErr(""); setBusyId(t.id);
    const done = !t.done;
    try {
      const { data } = await api.post(`/program/tasks/${t.id}`, { done });
      qc.setQueryData(KEY, (old) => old && ({
        ...old, progress: data.progress,
        days: old.days.map((d) => {
          const tasks = d.tasks.map((x) => (x.id === t.id ? { ...x, done } : x));
          return { ...d, tasks, done: tasks.filter((x) => x.done).length };
        }),
      }));
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusyId(null); }
  };

  if (!p.enrolled) {
    return <Empty title="Your cohort is being set up" sub={p.msg || "The team will add you soon. Check back in a day or two."} />;
  }
  const pr = p.progress || {};
  return (
    <div className="space-y-4">
      <Card data-testid="program-progress">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            <Label>{p.cohort.name}</Label>
            <p className="text-[15px] text-bz-muted -mt-1">
              {p.cohort.starts_in_days > 0 ? `Starts ${hdate(p.cohort.start_date)}, in ${p.cohort.starts_in_days} day${p.cohort.starts_in_days === 1 ? "" : "s"}.` : `Started ${hdate(p.cohort.start_date)}.`}
            </p>
          </div>
          <span className="text-[34px] font-display font-[500] tracking-[-0.03em] text-bz-gold tabular leading-none">{pr.pct || 0}%</span>
        </div>
        <Meter value={pr.pct} className="mt-3" label="Tasks done" />
        <p className="text-[13px] text-bz-muted mt-2 tabular">{pr.done || 0} of {pr.total || 0} tasks done</p>
      </Card>
      <CoachCard p={p} />
      <ErrorLine>{err}</ErrorLine>
      {p.days.length ? (
        <div className="space-y-3">
          {p.days.map((d) => <Day key={d.n} d={d} next={d.n === p.next_day} onToggle={toggle} busyId={busyId} />)}
        </div>
      ) : <Empty title="Days are being added" sub="Your sessions and tasks will show here before the program starts." />}
      <Note>Tick a task when it's done. Only you and the team see your progress.</Note>
    </div>
  );
}

function Inner() {
  const q = useQuery({ queryKey: KEY, queryFn: async () => (await api.get("/program")).data });
  return <Loadable q={q} what="your program" lines={6}>{(p) => <Body p={p} />}</Loadable>;
}

export default function Program() {
  const header = (
    <PageHeader kicker="4-3-2-1 program" title="Your first month," accent="one day at a time."
      sub="Each day has a live session and a few tasks. Tick them off as you go. Your coach helps you through month 1." />
  );
  return (
    <Gate feature="program" header={header}>
      <div className="space-y-5">
        {header}
        <Inner />
      </div>
    </Gate>
  );
}

