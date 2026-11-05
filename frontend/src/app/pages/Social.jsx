// /app/social — Social Media Builder: 1-10 LinkedIn posts a run from the member's niche, chosen pillars and formats,
// and (when there are any) their Career Story Bank stories. Posts land on posting days in a month calendar;
// edit, copy, move the date, mark posted. The member posts them.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ChevronLeft, ChevronRight } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate, istToday, monthLabel } from "@/lib/format";
import { Gate, Para, UsageLine } from "../components/common";
import { CopyButton } from "../components/Markdown";
import {
  AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Note, OkLine, PageHeader, Segmented, Select,
  Textarea, Thinking,
} from "../components/ui";

const PILLARS = [["expertise", "Expertise"], ["story", "Story"], ["opinion", "Opinion"], ["value", "Value"]];
const FORMATS = [["story", "Story"], ["insight", "Insight"], ["framework", "Framework"], ["myth_fact", "Myth vs fact"], ["mini_case", "Mini case"]];
const PILLAR_LABEL = Object.fromEntries(PILLARS);
const DAYS = ["M", "T", "W", "T", "F", "S", "S"];

function Toggles({ items, value, onChange, testid, label }) {
  return (
    <div className="flex flex-wrap gap-2" role="group" aria-label={label}>
      {items.map(([k, l]) => {
        const on = value.includes(k);
        return (
          <button key={k} type="button" aria-pressed={on} data-testid={`${testid}-${k}`}
            onClick={() => onChange(on ? (value.length > 1 ? value.filter((x) => x !== k) : value) : [...value, k])}
            className={`min-h-[44px] px-4 rounded-bzbtn text-[14px] font-bold border inline-flex items-center gap-1.5 ${on ? "bg-bz-gold text-bz-on-accent border-bz-gold" : "bg-bz-panel border-bz-line hover:border-bz-line-strong"}`}>
            {on && <Check className="w-4 h-4" strokeWidth={3} aria-hidden />}{l}
          </button>
        );
      })}
    </div>
  );
}

function shiftMonth(m, d) {
  const [y, mo] = m.split("-").map(Number);
  const t = new Date(Date.UTC(y, mo - 1 + d, 1));
  return `${t.getUTCFullYear()}-${String(t.getUTCMonth() + 1).padStart(2, "0")}`;
}

function Calendar({ month, items, selected, onSelect }) {
  const [y, mo] = month.split("-").map(Number);
  const first = new Date(Date.UTC(y, mo - 1, 1));
  const lead = (first.getUTCDay() + 6) % 7;
  const days = new Date(Date.UTC(y, mo, 0)).getUTCDate();
  const byDay = {};
  items.forEach((p) => { (byDay[p.date] = byDay[p.date] || []).push(p); });
  const today = istToday();
  const cells = [...Array(lead).fill(null), ...Array.from({ length: days }, (_, i) => `${month}-${String(i + 1).padStart(2, "0")}`)];
  return (
    <div>
      <div className="grid grid-cols-7 gap-1 text-center text-[11px] font-bold text-bz-muted mb-1">{DAYS.map((d, i) => <span key={i}>{d}</span>)}</div>
      <div className="grid grid-cols-7 gap-1">
        {cells.map((iso, i) => {
          if (!iso) return <span key={`x${i}`} />;
          const ps = byDay[iso] || [];
          const on = selected === iso;
          const allPosted = ps.length > 0 && ps.every((p) => p.status === "posted");
          return (
            <button key={iso} type="button" onClick={() => onSelect(on ? "" : iso)} aria-pressed={on} aria-label={`${hdate(iso)}: ${ps.length} post${ps.length === 1 ? "" : "s"}`}
              data-testid={`social-day-${iso}`}
              className={`min-h-[48px] rounded-bzbtn border flex flex-col items-center justify-center gap-1 text-[13px] font-bold tabular
                ${on ? "border-bz-gold bg-bz-gold-tint" : ps.length ? "border-bz-line-strong bg-bz-panel" : "border-transparent"} ${iso === today ? "text-bz-gold" : ""}`}>
              {Number(iso.slice(8))}
              {ps.length > 0 && (
                <span className="flex gap-0.5" aria-hidden>
                  {ps.slice(0, 3).map((p) => <span key={p.id} className={`w-1.5 h-1.5 rounded-full ${allPosted ? "bg-bz-muted" : "bg-bz-gold"}`} />)}
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Post({ p, onChanged }) {
  const [edit, setEdit] = useState(false);
  const [t, setT] = useState(p.text);
  const [date, setDate] = useState(p.date);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const patch = async (body, key) => {
    setBusy(key); setErr("");
    try { await api.patch(`/social/${p.id}`, body); onChanged(); return true; } catch (e) { setErr(apiError(e)); return false; } finally { setBusy(""); }
  };
  const remove = async () => {
    if (!window.confirm("Delete this post?")) return;
    setBusy("del");
    try { await api.delete(`/social/${p.id}`); onChanged(); } catch { /* ignore */ } finally { setBusy(""); }
  };
  return (
    <li className={`rounded-bzcard border bg-bz-card p-4 ${p.status === "posted" ? "border-bz-line" : "border-bz-line-strong"}`} data-testid={`social-post-${p.id}`}>
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[14px] font-extrabold text-bz-gold">{hdate(p.date)}</span>
          <Chip>{PILLAR_LABEL[p.pillar] || p.pillar}</Chip><Chip>{p.format_label}</Chip>
          {p.status === "posted" && <Chip tone="gold">Posted</Chip>}
        </div>
        {!edit && <CopyButton text={p.text} />}
      </div>
      {p.story_title && <p className="text-[12px] text-bz-muted mt-1">From your story: {p.story_title}</p>}
      {edit ? (
        <div className="space-y-2 mt-3">
          <Textarea rows={10} value={t} onChange={(e) => setT(e.target.value)} maxLength={3000} data-testid={`social-edit-${p.id}`} />
          <Field label="Post on"><Input type="date" value={date} onChange={(e) => setDate(e.target.value)} /></Field>
          <div className="flex gap-2">
            <Button variant="small" loading={busy === "save"} onClick={async () => { if (await patch({ text: t, date }, "save")) setEdit(false); }}>Save</Button>
            <Button variant="small" onClick={() => { setEdit(false); setT(p.text); setDate(p.date); }}>Cancel</Button>
          </div>
        </div>
      ) : (
        <>
          <Para text={p.text} className="text-[15px] mt-3" />
          <div className="flex flex-wrap gap-2 mt-3">
            <Button variant="small" onClick={() => setEdit(true)}>Edit</Button>
            <Button variant="small" loading={busy === "post"} onClick={() => patch({ status: p.status === "posted" ? "draft" : "posted" }, "post")} data-testid={`social-posted-${p.id}`}>
              {p.status === "posted" ? "Not posted yet" : "Mark posted"}
            </Button>
            <Button variant="danger" loading={busy === "del"} onClick={remove}>Delete</Button>
          </div>
        </>
      )}
      <ErrorLine>{err}</ErrorLine>
    </li>
  );
}

function Body() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const [month, setMonth] = useState(istToday().slice(0, 7));
  const [day, setDay] = useState("");
  const q = useQuery({ queryKey: ["social", month], queryFn: async () => (await api.get("/social", { params: { month } })).data, placeholderData: (p) => p });
  const [f, setF] = useState({ count: 5, pillars: PILLARS.map((x) => x[0]), formats: FORMATS.map((x) => x[0]), per_week: 3, start_date: "", topic: "", use_stories: true });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const usage = plan?.limits?.posts;
  const left = usage?.limit == null ? 10 : Math.max(0, usage.limit - usage.used);
  const refresh = () => qc.invalidateQueries({ queryKey: ["social"] });

  const run = async (e) => {
    e.preventDefault();
    setErr(""); setOk(""); setBusy(true);
    try {
      const { data } = await api.post("/social/generate", { ...f, start_date: f.start_date || null });
      const n = data.items.length;
      setOk(`${n} post${n === 1 ? "" : "s"} added to your calendar${data.stories_used ? `, ${data.stories_used} from your career stories` : ""}.`);
      if (n) { setMonth(data.items[0].date.slice(0, 7)); setDay(""); }
      refresh(); refreshMe();
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-4">
      {busy ? <AiFrame title="Social Media Builder"><Thinking label={`Writing ${f.count} posts for your niche`} /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-4">
            <div><Label tone="muted">Content pillars</Label><Toggles items={PILLARS} value={f.pillars} onChange={(v) => setF({ ...f, pillars: v })} testid="social-pillar" label="Pillars" /></div>
            <div><Label tone="muted">Formats</Label><Toggles items={FORMATS} value={f.formats} onChange={(v) => setF({ ...f, formats: v })} testid="social-format" label="Formats" /></div>
            <div className="grid gap-3 sm:grid-cols-3">
              <Field label="How many posts">
                <Select value={f.count} onChange={(e) => setF({ ...f, count: Number(e.target.value) })} data-testid="social-count">
                  {Array.from({ length: 10 }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                </Select>
              </Field>
              <Field label="Posts a week"><Segmented label="Posts a week" value={f.per_week} onChange={(v) => setF({ ...f, per_week: v })} testid="social-perweek" options={[3, 4, 5]} /></Field>
              <Field label="Start from (optional)"><Input type="date" value={f.start_date} min={istToday()} onChange={(e) => setF({ ...f, start_date: e.target.value })} data-testid="social-start" /></Field>
            </div>
            <Field label="A topic for this batch (optional)"><Input value={f.topic} onChange={(e) => setF({ ...f, topic: e.target.value })} maxLength={200} placeholder="e.g. Why dealers stop ordering" /></Field>
            <label className="flex items-center gap-3 min-h-[44px] cursor-pointer">
              <input type="checkbox" checked={f.use_stories} onChange={(e) => setF({ ...f, use_stories: e.target.checked })} className="w-5 h-5 accent-bz-gold" data-testid="social-stories" />
              <span className="text-[15px]">Use my career stories{q.data ? ` (${q.data.stories} saved)` : ""}</span>
            </label>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={left < 1} data-testid="social-run">Write {f.count} post{f.count === 1 ? "" : "s"}</Button>
            <UsageLine usage={usage} what="posts" className="text-center" />
            {f.count > left && left > 0 && <Note className="text-center">You have {left} posts left this month.</Note>}
          </form>
        </Card>
      )}
      <OkLine>{ok}</OkLine>
      <Loadable q={q} what="your calendar" lines={6}>
        {(d) => {
          const shown = day ? d.items.filter((p) => p.date === day) : d.items;
          return (
            <div className="space-y-3">
              <Card>
                <div className="flex items-center justify-between gap-2 mb-3">
                  <button type="button" onClick={() => { setMonth(shiftMonth(month, -1)); setDay(""); }} className="w-11 h-11 grid place-items-center rounded-full hover:bg-bz-raised" aria-label="Previous month" data-testid="social-prev"><ChevronLeft className="w-5 h-5" aria-hidden /></button>
                  <div className="text-center">
                    <p className="text-[17px] font-extrabold">{monthLabel(month)}</p>
                    <p className="text-[12px] text-bz-muted">{d.items.length} post{d.items.length === 1 ? "" : "s"}{d.next_date ? ` · next ${hdate(d.next_date)}` : ""}</p>
                  </div>
                  <button type="button" onClick={() => { setMonth(shiftMonth(month, 1)); setDay(""); }} className="w-11 h-11 grid place-items-center rounded-full hover:bg-bz-raised" aria-label="Next month" data-testid="social-next"><ChevronRight className="w-5 h-5" aria-hidden /></button>
                </div>
                <Calendar month={month} items={d.items} selected={day} onSelect={setDay} />
              </Card>
              {day && <button type="button" onClick={() => setDay("")} className="text-[13px] font-bold text-bz-gold min-h-[40px]">Show the whole month</button>}
              {shown.length ? <ul className="space-y-3">{shown.map((p) => <Post key={p.id} p={p} onChanged={refresh} />)}</ul>
                : <Empty title={day ? "Nothing on this day" : "No posts this month"} sub={day ? "" : d.upcoming ? `${d.upcoming} post${d.upcoming === 1 ? "" : "s"} waiting in other months.` : "Write your first batch above."} />}
            </div>
          );
        }}
      </Loadable>
    </div>
  );
}

export default function Social() {
  return (
    <div className="space-y-5">
      <PageHeader kicker="Social Media Builder" ai title="Posts that sound like you," accent="on a calendar."
        sub="Pick your pillars and formats. We write LinkedIn posts for your niche, using your career stories where you have them, and place them on posting days. You post them." />
      <Gate feature="social_builder"><Body /></Gate>
    </div>
  );
}
