// Admin › 4-3-2-1 program: cohorts (start date, days with session time, links and tasks, default coach) and
// enrolments (name, phone, plan, progress %). Move a member to another cohort or give them their own coach.
// Members are enrolled when they first open the program: the next active cohort (start ≥ today − 7 days), else the latest.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Trash2, X } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { PLAN_LABEL } from "@/lib/features";
import { hdate, istToday } from "@/lib/format";
import { Button, Card, Chip, Field, Input, Label, Meter, OkLine, Segmented, Select, Sheet, Skeleton } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

const PLAN_TONE = { free: "muted", member: "gold", l1: "solid", l2: "solid" };
const iconBtn = "w-11 h-11 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss shrink-0";
const newDay = (n) => ({ n, title: "", when: "", link: "", recording_url: "", workbook_url: "", tasks: [{ text: "" }] });

function toForm(c) {
  return {
    name: c?.name || "", start_date: c?.start_date || istToday(), active: c ? !!c.active : true,
    coach_name: c?.default_coach?.name || "", coach_whatsapp: c?.default_coach?.whatsapp || "",
    days: (c?.days || []).map((d) => ({ ...d, when: (d.when || "").slice(0, 16), tasks: d.tasks.length ? d.tasks : [{ text: "" }] })),
  };
}

function DayEditor({ d, i, onChange, onRemove }) {
  const set = (k) => (e) => onChange({ ...d, [k]: k === "n" ? Number(e.target.value) : e.target.value });
  const setTask = (j, text) => onChange({ ...d, tasks: d.tasks.map((t, k) => (k === j ? { ...t, text } : t)) });
  return (
    <Card inset className="space-y-3" data-testid={`admin-day-${i}`}>
      <div className="flex gap-2 items-end">
        <Field label="Day" className="w-20"><Input type="number" min="1" max="60" value={d.n} onChange={set("n")} /></Field>
        <Field label="Title" className="flex-1"><Input value={d.title} onChange={set("title")} maxLength={140} placeholder="e.g. Find your niche" /></Field>
        <button type="button" aria-label="Remove day" className={iconBtn} onClick={onRemove}><Trash2 className="w-4 h-4" aria-hidden /></button>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Session (IST)"><Input type="datetime-local" value={d.when} onChange={set("when")} /></Field>
        <Field label="Join link"><Input value={d.link} onChange={set("link")} placeholder="https://zoom.us/j/…" maxLength={500} /></Field>
        <Field label="Recording link"><Input value={d.recording_url} onChange={set("recording_url")} placeholder="https://…" maxLength={500} /></Field>
        <Field label="Workbook link"><Input value={d.workbook_url} onChange={set("workbook_url")} placeholder="https://…" maxLength={500} /></Field>
      </div>
      <div className="space-y-2">
        <span className="block text-[12px] font-semibold text-bz-muted">Tasks</span>
        {d.tasks.map((t, j) => (
          <div key={t.id || `new-${j}`} className="flex gap-2">
            <Input value={t.text} onChange={(e) => setTask(j, e.target.value)} maxLength={300} placeholder="e.g. Fill the EDE sheet" />
            <button type="button" aria-label="Remove task" className={iconBtn} onClick={() => onChange({ ...d, tasks: d.tasks.filter((_, k) => k !== j) })}><X className="w-4 h-4" aria-hidden /></button>
          </div>
        ))}
        <Button variant="small" onClick={() => onChange({ ...d, tasks: [...d.tasks, { text: "" }] })}><Plus className="w-4 h-4" aria-hidden /> Add a task</Button>
      </div>
    </Card>
  );
}

function CohortEditor({ edit, onClose, onSaved }) {
  const [v, setV] = useState(toForm(edit.row));
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const save = async () => {
    setErr("");
    if (!v.name.trim()) { setErr("Name the cohort."); return; }
    if (!v.start_date) { setErr("Pick the start date."); return; }
    const days = v.days.map((d) => ({ ...d, title: d.title.trim(), tasks: d.tasks.filter((t) => t.text.trim()).map((t) => ({ id: t.id, text: t.text.trim() })) }));
    if (days.some((d) => d.title.length < 2)) { setErr("Every day needs a title."); return; }
    if (new Set(days.map((d) => d.n)).size !== days.length) { setErr("Two days have the same number."); return; }
    setBusy(true);
    try {
      const body = { name: v.name.trim(), start_date: v.start_date, active: v.active,
        default_coach: { name: v.coach_name.trim(), whatsapp: v.coach_whatsapp.trim() },
        days: days.map((d) => ({ n: d.n, title: d.title, when: d.when || null, link: d.link.trim(), recording_url: d.recording_url.trim(), workbook_url: d.workbook_url.trim(), tasks: d.tasks })) };
      if (edit.id) await api.put(`/admin/program/cohorts/${edit.id}`, body); else await api.post("/admin/program/cohorts", body);
      onSaved();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    if (!window.confirm(`Delete the cohort "${v.name}"?`)) return;
    try { await api.delete(`/admin/program/cohorts/${edit.id}`); onSaved(); } catch (e) { setErr(apiError(e)); }
  };
  const setDay = (i, d) => setV({ ...v, days: v.days.map((x, k) => (k === i ? d : x)) });
  return (
    <Sheet open onClose={onClose} title={edit.id ? `Edit ${edit.row.name}` : "Add a cohort"} wide>
      <div className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-[1fr_180px_160px]">
          <Field label="Name"><Input value={v.name} onChange={(e) => setV({ ...v, name: e.target.value })} maxLength={80} placeholder="e.g. December 2026" data-testid="cohort-name" /></Field>
          <Field label="Start date (IST)"><Input type="date" value={v.start_date} onChange={(e) => setV({ ...v, start_date: e.target.value })} data-testid="cohort-start" /></Field>
          <Field label="New members">
            <Select value={v.active ? "yes" : "no"} onChange={(e) => setV({ ...v, active: e.target.value === "yes" })}>
              <option value="yes">Open</option><option value="no">Closed</option>
            </Select>
          </Field>
        </div>
        <Card inset className="space-y-3">
          <Label>Default coach</Label>
          <p className="text-[13px] text-bz-muted -mt-1">Shown to everyone in this cohort for month 1, unless you give a member their own coach.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Name"><Input value={v.coach_name} onChange={(e) => setV({ ...v, coach_name: e.target.value })} maxLength={80} data-testid="cohort-coach-name" /></Field>
            <Field label="WhatsApp number"><Input value={v.coach_whatsapp} onChange={(e) => setV({ ...v, coach_whatsapp: e.target.value })} maxLength={20} placeholder="98765 43210" inputMode="tel" data-testid="cohort-coach-wa" /></Field>
          </div>
        </Card>
        <div className="space-y-3">
          <Label>Days</Label>
          {v.days.map((d, i) => <DayEditor key={i} d={d} i={i} onChange={(x) => setDay(i, x)} onRemove={() => setV({ ...v, days: v.days.filter((_, k) => k !== i) })} />)}
          <Button variant="small" onClick={() => setV({ ...v, days: [...v.days, newDay((v.days.reduce((m, d) => Math.max(m, d.n || 0), 0) || 0) + 1)] })} data-testid="cohort-add-day">
            <Plus className="w-4 h-4" aria-hidden /> Add a day
          </Button>
        </div>
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <div className="flex flex-wrap gap-2">
          <Button className="flex-1" onClick={save} loading={busy} data-testid="admin-save">Save cohort</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
          {edit.id && <Button variant="danger" onClick={remove} disabled={edit.row.enrolled > 0}>Delete</Button>}
        </div>
        {edit.id && edit.row.enrolled > 0 && <p className="text-[13px] text-bz-muted">To delete this cohort, move its {edit.row.enrolled} member{edit.row.enrolled === 1 ? "" : "s"} first.</p>}
      </div>
    </Sheet>
  );
}

function Cohorts() {
  const qc = useQueryClient();
  const q = useAdmin("program/cohorts");
  const [edit, setEdit] = useState(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin", "program/cohorts"] }); qc.invalidateQueries({ queryKey: ["admin", "program/enrollments"] }); };
  return (
    <div className="space-y-4">
      <div className="flex justify-end"><Button onClick={() => setEdit({ id: null, row: null })} data-testid="admin-add-cohort"><Plus className="w-4 h-4" aria-hidden /> Add a cohort</Button></div>
      <AdminLoadable q={q} what="cohorts">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} onRow={(r) => setEdit({ id: r.id, row: r })} empty="No cohorts yet. Add the next one so new L1 members can start." cols={[
              { key: "name", label: "Cohort", render: (r) => <b>{r.name}</b> },
              { key: "start_date", label: "Starts", render: (r) => hdate(r.start_date) },
              { key: "active", label: "New members", render: (r) => (r.active ? <Chip tone="gold">Open</Chip> : <Chip>Closed</Chip>) },
              { key: "day_count", label: "Days", right: true },
              { key: "tasks", label: "Tasks", right: true },
              { key: "enrolled", label: "Members", right: true },
              { key: "coach", label: "Default coach", render: (r) => (r.default_coach ? `${r.default_coach.name}${r.default_coach.whatsapp ? ` · ${r.default_coach.whatsapp}` : ""}` : "—") },
            ]} />
          </Card>
        )}
      </AdminLoadable>
      {edit && <CohortEditor edit={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh(); }} />}
    </div>
  );
}

function MemberSheet({ row, cohorts, onClose, onSaved }) {
  const [to, setTo] = useState(row.cohort_id);
  const [c, setC] = useState({ name: row.own_coach ? row.coach?.name || "" : "", whatsapp: row.own_coach ? row.coach?.whatsapp || "" : "", until: "" });
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const run = async (kind, fn, msg) => {
    setErr(""); setOk(""); setBusy(kind);
    try { await fn(); setOk(msg); onSaved(); } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };
  return (
    <Sheet open onClose={onClose} title={row.name || row.phone}>
      <div className="space-y-4" data-testid="admin-enrolment">
        <div className="text-[14px] space-y-1">
          <div><span className="text-bz-muted">Phone</span> <b>{row.phone}</b> · <Chip tone={PLAN_TONE[row.plan]}>{PLAN_LABEL[row.plan] || row.plan}</Chip></div>
          <div><span className="text-bz-muted">Cohort</span> {row.cohort_name} · <span className="text-bz-muted">joined</span> {dt(row.enrolled_at)}</div>
          <div><span className="text-bz-muted">Progress</span> {row.progress.done} of {row.progress.total} tasks ({row.progress.pct}%)</div>
          <div><span className="text-bz-muted">Coach</span> {row.coach ? `${row.coach.name}${row.own_coach ? " (own)" : " (cohort default)"}` : "—"} · {row.coach_on ? (row.plan === "l2" ? "on while L2 runs" : `until ${hdate(row.coach_until)}`) : "month 1 is over"}</div>
        </div>
        <Card inset className="space-y-3">
          <Label>Move to another cohort</Label>
          <p className="text-[13px] text-bz-muted -mt-1">Month 1 with the coach restarts from the new cohort's start date.</p>
          <div className="flex gap-2 items-end flex-wrap">
            <Field label="Cohort" className="flex-1 min-w-[200px]">
              <Select value={to} onChange={(e) => setTo(e.target.value)} data-testid="enrolment-cohort">
                {cohorts.map((x) => <option key={x.id} value={x.id}>{x.name} · {hdate(x.start_date)}</option>)}
              </Select>
            </Field>
            <Button variant="secondary" disabled={to === row.cohort_id} loading={busy === "move"} data-testid="enrolment-move"
              onClick={() => run("move", () => api.post(`/admin/program/enrollments/${row.id}/move`, { cohort_id: to }), "Moved.")}>Move</Button>
          </div>
        </Card>
        <Card inset className="space-y-3">
          <Label>Own coach</Label>
          <p className="text-[13px] text-bz-muted -mt-1">Leave the name empty to use the cohort's default coach.</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Coach name"><Input value={c.name} onChange={(e) => setC({ ...c, name: e.target.value })} maxLength={80} data-testid="enrolment-coach-name" /></Field>
            <Field label="WhatsApp number"><Input value={c.whatsapp} onChange={(e) => setC({ ...c, whatsapp: e.target.value })} maxLength={20} inputMode="tel" placeholder="98765 43210" data-testid="enrolment-coach-wa" /></Field>
          </div>
          <Field label="Coach until (optional)" hint="Last day with the coach. Empty keeps month 1." className="max-w-[240px]">
            <Input type="date" value={c.until} onChange={(e) => setC({ ...c, until: e.target.value })} />
          </Field>
          <Button variant="secondary" loading={busy === "coach"} data-testid="enrolment-coach-save"
            onClick={() => run("coach", () => api.put(`/admin/program/enrollments/${row.id}/coach`, { name: c.name.trim(), whatsapp: c.whatsapp.trim(), until: c.until || null }), "Coach saved.")}>Save coach</Button>
        </Card>
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <OkLine>{ok}</OkLine>
      </div>
    </Sheet>
  );
}

function Members() {
  const qc = useQueryClient();
  const cohorts = useAdmin("program/cohorts");
  const [cid, setCid] = useState("");
  const [term, setTerm] = useState("");
  const [sel, setSel] = useState(null);
  const q = useQuery({ queryKey: ["admin", "program/enrollments", cid || null],
    queryFn: async () => (await api.get("/admin/program/enrollments", { params: { cohort_id: cid || undefined } })).data });
  const list = asList(cohorts.data);
  const t = term.trim().toLowerCase();
  const rows = asList(q.data).filter((r) => !t || `${r.name} ${r.phone}`.toLowerCase().includes(t));
  const current = sel && asList(q.data).find((r) => r.id === sel);
  return (
    <div className="space-y-4">
      <div className="flex flex-col sm:flex-row gap-2">
        <Select value={cid} onChange={(e) => setCid(e.target.value)} className="sm:w-64" data-testid="enrolments-cohort">
          <option value="">All cohorts</option>
          {list.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </Select>
        <Input value={term} onChange={(e) => setTerm(e.target.value)} placeholder="Search name or phone" className="sm:max-w-xs" data-testid="enrolments-search" />
      </div>
      {q.isLoading ? <Card><Skeleton lines={5} /></Card> : (
        <Card className="px-0 sm:px-5 py-2">
          <p className="text-sm text-bz-muted px-4 sm:px-0 py-2">{rows.length.toLocaleString("en-IN")} members</p>
          <Table rows={rows} onRow={(r) => setSel(r.id)} empty="No one enrolled yet. L1 members are enrolled when they first open the program." cols={[
            { key: "name", label: "Name", render: (r) => <b>{r.name || "—"}</b> },
            { key: "phone", label: "Phone", render: (r) => <span className="text-bz-gold font-bold">{r.phone}</span> },
            { key: "plan", label: "Plan", render: (r) => <Chip tone={PLAN_TONE[r.plan] || "muted"}>{PLAN_LABEL[r.plan] || r.plan}</Chip> },
            { key: "cohort_name", label: "Cohort" },
            { key: "progress", label: "Progress", render: (r) => <span className="flex items-center gap-2 min-w-[130px]"><Meter value={r.progress.pct} className="flex-1" label="Progress" /><span className="tabular">{r.progress.pct}%</span></span> },
            { key: "coach", label: "Coach", render: (r) => (r.coach ? `${r.coach.name}${r.own_coach ? " (own)" : ""}` : "—") },
            { key: "coach_until", label: "Coach until", render: (r) => (r.plan === "l2" ? "L2" : r.coach_on ? hdate(r.coach_until) : <span className="text-bz-muted">over</span>) },
            { key: "enrolled_at", label: "Joined", render: (r) => dt(r.enrolled_at) },
          ]} />
        </Card>
      )}
      {current && <MemberSheet key={current.id + current.cohort_id} row={current} cohorts={list} onClose={() => setSel(null)}
        onSaved={() => { qc.invalidateQueries({ queryKey: ["admin", "program/enrollments"] }); qc.invalidateQueries({ queryKey: ["admin", "program/cohorts"] }); }} />}
    </div>
  );
}

export default function AdminProgram() {
  const [tab, setTab] = useState("cohorts");
  return (
    <div className="space-y-4">
      <Segmented value={tab} onChange={setTab} label="View" testid="admin-program-tab"
        options={[{ value: "cohorts", label: "Cohorts" }, { value: "members", label: "Members" }]} />
      {tab === "cohorts" ? <Cohorts /> : <Members />}
    </div>
  );
}

