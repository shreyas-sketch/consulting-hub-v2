// Admin › Calls and events: group calls with Akshat (L1+) and events (L2 if "L2 only"). Times are IST.
// Members get inbox reminders 24 h and 1 h before (job "call_reminders"); changing the time sends fresh ones.
import { Chip, Field, Input, Select, Textarea } from "../components/ui";
import { CrudPage, dt } from "./shared";

const blank = { title: "", kind: "call", plan_min: "l1", when: "", duration_min: 60, link: "", recording_url: "", notes: "" };

function Form({ value: v, onChange }) {
  const set = (k) => (e) => onChange({ ...v, [k]: k === "duration_min" ? Number(e.target.value) : e.target.value });
  return (
    <div className="space-y-3">
      <Field label="Title"><Input value={v.title} onChange={set("title")} maxLength={140} placeholder="e.g. Group call: pricing your first project" data-testid="call-title" /></Field>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Type">
          <Select value={v.kind} onChange={set("kind")} data-testid="call-kind">
            <option value="call">Group call</option>
            <option value="event">Event</option>
          </Select>
        </Field>
        <Field label="Who can join">
          <Select value={v.plan_min} onChange={set("plan_min")} data-testid="call-plan">
            <option value="l1">L1 and L2</option>
            <option value="l2">L2 only</option>
          </Select>
        </Field>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Date and time (IST)"><Input type="datetime-local" value={v.when} onChange={set("when")} data-testid="call-when" /></Field>
        <Field label="Length (minutes)"><Input type="number" min="15" max="720" step="15" value={v.duration_min} onChange={set("duration_min")} /></Field>
      </div>
      <Field label="Join link" hint="Zoom, Meet or any https link. Members see it on the Calls screen."><Input value={v.link} onChange={set("link")} placeholder="https://zoom.us/j/…" maxLength={500} data-testid="call-link" /></Field>
      <Field label="Recording link" hint="Add after the call. YouTube or Vimeo links work best."><Input value={v.recording_url} onChange={set("recording_url")} placeholder="https://vimeo.com/…" maxLength={500} data-testid="call-recording" /></Field>
      <Field label="Notes for members (optional)"><Textarea value={v.notes} onChange={set("notes")} maxLength={2000} rows={3} placeholder="e.g. Bring one question about your niche." /></Field>
    </div>
  );
}

const isUrl = (s) => !s || /^https?:\/\//i.test(s.trim());

export default function AdminCalls() {
  return (
    <CrudPage path="calls" title="call" empty="No calls yet. Add the next group call." blank={blank} Form={Form}
      toForm={(r) => ({ ...blank, ...r, when: (r.when || "").slice(0, 16) })}
      toBody={(v) => ({ title: v.title.trim(), kind: v.kind, plan_min: v.plan_min, when: v.when, duration_min: Number(v.duration_min) || 60,
        link: v.link.trim(), recording_url: v.recording_url.trim(), notes: v.notes })}
      validate={(v) => {
        if (v.title.trim().length < 2) return "Add a title.";
        if (!v.when) return "Pick the date and time.";
        if (!isUrl(v.link) || !isUrl(v.recording_url)) return "Links must start with https://";
        return "";
      }}
      cols={[
        { key: "when", label: "When (IST)", render: (r) => <span className="font-bold">{dt(r.when)}</span> },
        { key: "title", label: "Title", wrap: true },
        { key: "kind", label: "Type", render: (r) => (r.kind === "event" ? <Chip tone="gold">Event</Chip> : "Group call") },
        { key: "plan_min", label: "Who", render: (r) => (r.plan_min === "l2" ? <Chip tone="solid">L2 only</Chip> : "L1 + L2") },
        { key: "duration_min", label: "Min", right: true },
        { key: "status", label: "Status", render: (r) => (r.live ? <Chip tone="solid">Live</Chip> : r.over ? (r.recording_url ? "Done · recorded" : <span className="text-bz-miss">Add recording</span>) : "Upcoming") },
        { key: "reminded", label: "Reminders", render: (r) => (r.reminded?.length ? r.reminded.map((x) => x.split(":")[0]).join(", ") : "—") },
      ]} />
  );
}
