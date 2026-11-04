// Admin › Bootcamps (L2): bootcamps with tasks and resource links; members' submissions (text and/or a link),
// review with feedback (the member gets an inbox message), completion % per member.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Pencil, Plus, Trash2, X } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip, Field, Input, Label, Meter, Segmented, Select, Sheet, Skeleton, Textarea } from "../components/ui";
import { AdminLoadable, asList, dt, Kpi, Table, useAdmin } from "./shared";

const blank = { n: 1, title: "", description: "", published: false, tasks: [{ title: "", detail: "" }], resources: [] };
const iconBtn = "w-11 h-11 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss shrink-0";

function Editor({ edit, onClose, onSaved }) {
  const [v, setV] = useState(edit.value);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const setList = (k, i, patch) => setV({ ...v, [k]: v[k].map((x, j) => (j === i ? { ...x, ...patch } : x)) });
  const drop = (k, i) => setV({ ...v, [k]: v[k].filter((_, j) => j !== i) });
  const save = async () => {
    setErr("");
    const tasks = v.tasks.filter((t) => t.title.trim());
    const resources = v.resources.filter((r) => r.title.trim() || r.url.trim());
    if (v.title.trim().length < 2) { setErr("Add a title."); return; }
    if (tasks.some((t) => t.title.trim().length < 2)) { setErr("Each task needs a title."); return; }
    if (resources.some((r) => !r.title.trim() || !/^https?:\/\//i.test(r.url.trim()))) { setErr("Each resource needs a title and an https:// link."); return; }
    setBusy(true);
    try {
      const body = { n: Number(v.n) || 1, title: v.title.trim(), description: v.description.trim(), published: !!v.published,
        tasks: tasks.map((t) => ({ id: t.id, title: t.title.trim(), detail: (t.detail || "").trim() })),
        resources: resources.map((r) => ({ title: r.title.trim(), url: r.url.trim() })) };
      if (edit.id) await api.put(`/admin/bootcamps/${edit.id}`, body); else await api.post("/admin/bootcamps", body);
      onSaved();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Sheet open onClose={onClose} title={edit.id ? "Edit bootcamp" : "Add bootcamp"} wide>
      <div className="space-y-4">
        <div className="grid gap-3 grid-cols-[96px_1fr]">
          <Field label="Number"><Input type="number" min="1" max="50" value={v.n} onChange={(e) => setV({ ...v, n: e.target.value })} /></Field>
          <Field label="Title"><Input value={v.title} onChange={(e) => setV({ ...v, title: e.target.value })} maxLength={140} placeholder="e.g. Your offer" data-testid="bootcamp-title" /></Field>
        </div>
        <Field label="What it's about"><Textarea value={v.description} onChange={(e) => setV({ ...v, description: e.target.value })} maxLength={2000} rows={3} /></Field>
        <Field label="Show to L2 members" className="max-w-[240px]">
          <Select value={v.published ? "yes" : "no"} onChange={(e) => setV({ ...v, published: e.target.value === "yes" })} data-testid="bootcamp-published">
            <option value="no">Hidden (draft)</option><option value="yes">Shown</option>
          </Select>
        </Field>
        <Card inset className="space-y-3">
          <Label>Tasks</Label>
          {v.tasks.map((t, i) => (
            <div key={t.id || `new-${i}`} className="flex gap-2 items-start">
              <span className="w-8 pt-3 text-[14px] font-extrabold text-bz-gold tabular">{i + 1}</span>
              <div className="flex-1 space-y-2 min-w-0">
                <Input value={t.title} onChange={(e) => setList("tasks", i, { title: e.target.value })} maxLength={160} placeholder="Task title" data-testid={`bootcamp-task-title-${i}`} />
                <Textarea value={t.detail || ""} onChange={(e) => setList("tasks", i, { detail: e.target.value })} maxLength={2000} rows={2} className="min-h-[72px]" placeholder="What to do, what good looks like (optional)" />
              </div>
              <button type="button" aria-label="Remove task" className={iconBtn} onClick={() => drop("tasks", i)}><X className="w-4 h-4" aria-hidden /></button>
            </div>
          ))}
          <Button variant="small" onClick={() => setV({ ...v, tasks: [...v.tasks, { title: "", detail: "" }] })}><Plus className="w-4 h-4" aria-hidden /> Add a task</Button>
        </Card>
        <Card inset className="space-y-3">
          <Label>Resources</Label>
          {v.resources.map((r, i) => (
            <div key={i} className="flex gap-2 items-start flex-wrap sm:flex-nowrap">
              <Input value={r.title} onChange={(e) => setList("resources", i, { title: e.target.value })} maxLength={140} placeholder="Title" className="sm:w-56" />
              <Input value={r.url} onChange={(e) => setList("resources", i, { url: e.target.value })} maxLength={500} placeholder="https://drive.google.com/…" className="flex-1" />
              <button type="button" aria-label="Remove resource" className={iconBtn} onClick={() => drop("resources", i)}><X className="w-4 h-4" aria-hidden /></button>
            </div>
          ))}
          <Button variant="small" onClick={() => setV({ ...v, resources: [...v.resources, { title: "", url: "" }] })}><Plus className="w-4 h-4" aria-hidden /> Add a resource link</Button>
        </Card>
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <div className="flex gap-2">
          <Button className="flex-1" onClick={save} loading={busy} data-testid="admin-save">Save</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Sheet>
  );
}

function Review({ s, onDone }) {
  const [fb, setFb] = useState(s.feedback || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const send = async () => {
    setErr("");
    if (fb.trim().length < 2) { setErr("Write the feedback first."); return; }
    setBusy(true);
    try { await api.post(`/admin/bootcamps/submissions/${s.id}/review`, { feedback: fb.trim() }); onDone(); } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <li className="py-4 border-b border-bz-line last:border-0" data-testid={`admin-sub-${s.id}`}>
      <div className="flex flex-wrap items-center gap-2">
        <b>{s.name || s.phone}</b><span className="text-[13px] text-bz-muted">{s.phone}</span>
        <Chip tone={s.status === "reviewed" ? "solid" : "gold"}>{s.status === "reviewed" ? "Reviewed" : "To review"}</Chip>
        <span className="text-[12px] text-bz-muted ml-auto">{dt(s.at)}</span>
      </div>
      <p className="text-[13px] text-bz-muted mt-1">Task: {s.task_title}</p>
      {s.text && <p className="text-[14px] mt-2 whitespace-pre-line">{s.text}</p>}
      {s.link && <a href={s.link} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 text-[14px] font-bold text-bz-gold mt-2 break-all min-h-[40px]"><ExternalLink className="w-4 h-4 shrink-0" aria-hidden />{s.link}</a>}
      <div className="mt-2 space-y-2">
        <Textarea value={fb} onChange={(e) => setFb(e.target.value)} rows={3} maxLength={3000} placeholder="Feedback for the member" className="min-h-[88px]" data-testid={`admin-feedback-${s.id}`} />
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <Button variant="small" onClick={send} loading={busy} data-testid={`admin-review-${s.id}`}>{s.status === "reviewed" ? "Update feedback" : "Send feedback"}</Button>
      </div>
    </li>
  );
}

function Submissions({ id, onClose }) {
  const qc = useQueryClient();
  const [tab, setTab] = useState("to_review");
  const q = useQuery({ queryKey: ["admin", "bootcamp-subs", id], queryFn: async () => (await api.get(`/admin/bootcamps/${id}/submissions`)).data });
  const d = q.data || {};
  const items = (d.items || []).filter((s) => (tab === "all" ? true : tab === "to_review" ? s.status !== "reviewed" : false));
  const refresh = () => { q.refetch(); qc.invalidateQueries({ queryKey: ["admin", "bootcamps"] }); };
  return (
    <Sheet open onClose={onClose} title={d.bootcamp ? `${d.bootcamp.n}. ${d.bootcamp.title}` : "Submissions"} wide>
      {q.isLoading ? <Skeleton lines={6} /> : (
        <div className="space-y-4">
          <div className="grid grid-cols-3 gap-2">
            <Kpi label="Members" value={d.bootcamp?.members ?? 0} />
            <Kpi label="Submitted" value={d.bootcamp?.submissions ?? 0} />
            <Kpi label="To review" value={d.bootcamp?.to_review ?? 0} tone="gold" />
          </div>
          <Segmented value={tab} onChange={setTab} label="Show" testid="admin-subs-tab"
            options={[{ value: "to_review", label: "To review" }, { value: "all", label: "All submissions" }, { value: "members", label: "Completion" }]} />
          {tab === "members" ? (
            <Table rows={(d.members || []).map((m) => ({ ...m, id: m.user_id }))} empty="No one has started yet." cols={[
              { key: "name", label: "Member", render: (m) => <span><b>{m.name || "—"}</b> <span className="text-bz-muted">{m.phone}</span></span> },
              { key: "pct", label: "Done", render: (m) => <span className="flex items-center gap-2 min-w-[140px]"><Meter value={m.pct} className="flex-1" label="Done" /><span className="tabular">{m.pct}%</span></span> },
              { key: "submitted", label: "Sent", right: true, render: (m) => `${m.submitted}/${m.total}` },
              { key: "reviewed", label: "Reviewed", right: true },
              { key: "last_at", label: "Last", render: (m) => dt(m.last_at) },
            ]} />
          ) : items.length ? <ul>{items.map((s) => <Review key={`${s.id}-${s.at}`} s={s} onDone={refresh} />)}</ul>
            : <p className="text-sm text-bz-muted py-4">{tab === "to_review" ? "Nothing to review." : "No submissions yet."}</p>}
        </div>
      )}
    </Sheet>
  );
}

export default function AdminBootcamps() {
  const qc = useQueryClient();
  const q = useAdmin("bootcamps");
  const [edit, setEdit] = useState(null);
  const [subs, setSubs] = useState(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "bootcamps"] });
  const open = (r) => setEdit(r ? { id: r.id, value: { ...blank, ...r, tasks: r.tasks.length ? r.tasks : blank.tasks } }
    : { id: null, value: { ...blank, n: asList(q.data).length + 1 } });
  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}" and all its submissions? This cannot be undone.`)) return;
    try { await api.delete(`/admin/bootcamps/${r.id}`); refresh(); } catch (e) { window.alert(apiError(e)); }
  };
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => open(null)} data-testid="admin-add-bootcamps"><Plus className="w-4 h-4" aria-hidden /> Add</Button>
      </div>
      <AdminLoadable q={q} what="bootcamps">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} onRow={(r) => setSubs(r.id)} empty="No bootcamps yet. Add the first one." cols={[
              { key: "n", label: "#", right: true },
              { key: "title", label: "Title", wrap: true, render: (r) => <b>{r.title}</b> },
              { key: "published", label: "Shown", render: (r) => (r.published ? <Chip tone="gold">Shown</Chip> : <Chip>Draft</Chip>) },
              { key: "tasks", label: "Tasks", right: true, render: (r) => r.tasks.length },
              { key: "members", label: "Members", right: true },
              { key: "to_review", label: "To review", right: true, render: (r) => (r.to_review ? <b className="text-bz-gold">{r.to_review}</b> : 0) },
              { key: "_a", label: "", render: (r) => (
                <span className="flex gap-1 justify-end">
                  <button type="button" className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-card" aria-label="Edit" data-testid={`admin-edit-bootcamp-${r.id}`} onClick={(e) => { e.stopPropagation(); open(r); }}><Pencil className="w-4 h-4" aria-hidden /></button>
                  <button type="button" className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss" aria-label="Delete" onClick={(e) => { e.stopPropagation(); remove(r); }}><Trash2 className="w-4 h-4" aria-hidden /></button>
                </span>
              ) },
            ]} />
            <p className="text-[13px] text-bz-muted px-4 sm:px-0 py-2">Tap a bootcamp to see submissions and completion.</p>
          </Card>
        )}
      </AdminLoadable>
      {edit && <Editor edit={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh(); }} />}
      {subs && <Submissions id={subs} onClose={() => setSubs(null)} />}
    </div>
  );
}
