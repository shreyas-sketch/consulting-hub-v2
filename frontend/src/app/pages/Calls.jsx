// /app/calls and /app/calls/:id — group calls with Akshat (group only) and events: the next call with a join button
// and "add to calendar", other upcoming calls, past calls with recordings and recaps. Times are IST.
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { CalendarPlus, FileText, PlayCircle, Video } from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import { hdate } from "@/lib/format";
import { BackLink, Gate, Para } from "../components/common";
import { Card, Chip, Empty, Label, LinkButton, Loadable, Note, PageHeader } from "../components/ui";

const apiHref = (path) => (path ? `${API_BASE}${path.replace(/^\/api/, "")}` : null);

function Pill({ href, icon: Icon, children, testid, newTab = true }) {
  if (!href) return null;
  return (
    <a href={href} {...(newTab ? { target: "_blank", rel: "noopener noreferrer" } : {})} data-testid={testid}
      className="inline-flex items-center justify-center gap-1.5 min-h-[44px] px-4 rounded-full border border-bz-line bg-bz-raised text-[14px] font-bold hover:border-bz-line-strong">
      <Icon className="w-4 h-4 text-bz-gold" aria-hidden /> {children}
    </a>
  );
}

function kindLabel(c) {
  return c.kind === "event" ? "Event" : "Group call";
}

function NextCall({ c, title = "Next call" }) {
  return (
    <Card className="border-bz-rule" data-testid="calls-next">
      <div className="flex items-center gap-2 flex-wrap">
        <Label className="mb-0">{c.live ? "On now" : title}</Label>
        {c.live && <Chip tone="solid">Live</Chip>}
        {c.plan_min === "l2" && <Chip tone="gold">L2</Chip>}
      </div>
      <p className="text-[24px] sm:text-[28px] font-extrabold leading-tight tracking-[-0.01em] mt-2">{c.title}</p>
      <p className="text-[17px] font-bold text-bz-gold mt-1.5" data-testid="calls-next-when">{c.when_label}</p>
      <p className="text-[14px] text-bz-muted mt-0.5">{kindLabel(c)} · {c.duration_min} min · group only</p>
      {c.notes && <Para text={c.notes} className="text-[15px] mt-3" />}
      <div className="flex flex-col sm:flex-row gap-2 mt-4">
        {c.link ? (
          <a href={c.link} target="_blank" rel="noopener noreferrer" data-testid="calls-join"
            className="inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-full bg-bz-gold text-bz-on-accent font-extrabold text-[16px] hover:opacity-90 shadow-goldglow">
            <Video className="w-5 h-5" aria-hidden /> Join the call
          </a>
        ) : <Note className="self-center">The join link shows here before the call.</Note>}
        <a href={apiHref(c.ics_url)} data-testid="calls-calendar"
          className="inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-full border border-bz-rule text-bz-ink font-bold text-[15px] hover:border-bz-gold">
          <CalendarPlus className="w-5 h-5 text-bz-gold" aria-hidden /> Add to calendar
        </a>
      </div>
    </Card>
  );
}

function UpcomingRow({ c }) {
  return (
    <li className="py-3.5 border-b border-bz-line last:border-0 flex flex-col sm:flex-row sm:items-center gap-2">
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-bold">{c.title} {c.plan_min === "l2" && <Chip tone="gold" className="ml-1">L2</Chip>}</p>
        <p className="text-[13px] text-bz-muted">{c.when_label} · {kindLabel(c)} · {c.duration_min} min</p>
      </div>
      <Pill href={apiHref(c.ics_url)} icon={CalendarPlus} newTab={false} testid={`calls-calendar-${c.id}`}>Add to calendar</Pill>
    </li>
  );
}

function PastRow({ c }) {
  return (
    <li className="py-3.5 border-b border-bz-line last:border-0" data-testid={`calls-past-${c.id}`}>
      <p className="text-[15px] font-bold">{c.title}</p>
      <p className="text-[13px] text-bz-muted">{hdate(c.when)} · {kindLabel(c)}</p>
      {(c.recording_url || c.recap_id) ? (
        <div className="flex flex-wrap gap-2 mt-2">
          <Pill href={c.recording_url} icon={PlayCircle} testid={`calls-recording-${c.id}`}>Watch the recording</Pill>
          {c.recap_id && (
            <LinkButton to={`/app/recaps/${c.recap_id}`} variant="small" className="min-h-[44px]">
              <FileText className="w-4 h-4 text-bz-gold" aria-hidden /> Read the recap
            </LinkButton>
          )}
        </div>
      ) : <p className="text-[13px] text-bz-muted mt-1">Recording coming soon.</p>}
    </li>
  );
}

function List({ d }) {
  const rest = (d.upcoming || []).slice(1);
  return (
    <div className="space-y-4">
      {d.next ? <NextCall c={d.next} /> : (
        <Empty icon={Video} title="No call booked yet" sub="The next group call will show here with its date, time and join link. You'll also get a reminder a day before and an hour before." />
      )}
      {rest.length > 0 && (
        <Card>
          <Label>Coming up</Label>
          <ul>{rest.map((c) => <UpcomingRow key={c.id} c={c} />)}</ul>
        </Card>
      )}
      {d.l2_events_hidden > 0 && <Note>There's also an event for L2 Mentorship members coming up.</Note>}
      <Card>
        <Label>Past calls</Label>
        {(d.past || []).length ? <ul>{d.past.map((c) => <PastRow key={c.id} c={c} />)}</ul>
          : <p className="text-[14px] text-bz-muted">Recordings of past calls will show here.</p>}
      </Card>
    </div>
  );
}

function One({ id }) {
  const q = useQuery({ queryKey: ["call", id], queryFn: async () => (await api.get(`/calls/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/calls">All calls</BackLink>
      <Loadable q={q} what="this call" lines={5}>
        {(c) => (c.over ? <Card><ul><PastRow c={c} /></ul></Card> : <NextCall c={c} title={kindLabel(c)} />)}
      </Loadable>
    </div>
  );
}

function Inner() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["calls"], queryFn: async () => (await api.get("/calls")).data, enabled: !id, refetchInterval: 60000 });
  if (id) return <One id={id} />;
  return <Loadable q={q} what="your calls" lines={5}>{(d) => <List d={d} />}</Loadable>;
}

export default function Calls() {
  const header = (
    <PageHeader kicker="Group calls" title="Live with Akshat," accent="twice a month."
      sub="Group calls only. Join from here, add them to your calendar, and watch the recording later." />
  );
  return (
    <Gate feature="calls" header={header}>
      <div className="space-y-5">
        {header}
        <Inner />
      </div>
    </Gate>
  );
}
