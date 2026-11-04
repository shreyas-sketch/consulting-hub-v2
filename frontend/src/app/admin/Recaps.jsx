// Admin › Session recaps: upload a session transcript → the AI writes the recap and the audio → check, fix, publish.
// Publishing adds the transcript to Akshat AI's knowledge base and sends an inbox message to every L1 and L2 member.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, API_BASE, apiError } from "@/lib/api";
import { hdate, istToday } from "@/lib/format";
import { Button, Card, Chip, Field, Input, Label, OkLine, Select, Sheet, Skeleton, Textarea, Thinking } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

const lines = (s) => String(s || "").split("\n").map((x) => x.trim()).filter(Boolean);
const pairs = (s, a, b) => lines(s).map((l) => { const [x, ...y] = l.split("::"); return { [a]: x.trim(), [b]: y.join("::").trim() }; }).filter((p) => p[a]);

function UploadCard({ onDone }) {
  const calls = useAdmin("calls");
  const [file, setFile] = useState(null);
  const [f, setF] = useState({ title: "", date: istToday(), call_id: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const submit = async (e) => {
    e.preventDefault();
    setErr("");
    if (!file) { setErr("Choose the transcript file."); return; }
    if (!/\.(txt|vtt|srt|md)$/i.test(file.name)) { setErr("Upload a .txt, .vtt, .srt or .md file."); return; }
    if (file.size > 8 * 1024 * 1024) { setErr("Transcripts up to 8 MB."); return; }
    if (f.title.trim().length < 2) { setErr("Add the session title."); return; }
    setBusy(true);
    try {
      const fd = new FormData();
      fd.append("file", file);
      fd.append("title", f.title.trim());
      fd.append("date", f.date);
      if (f.call_id) fd.append("call_id", f.call_id);
      const { data } = await api.post("/admin/recaps", fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 240000 });
      setFile(null); setF({ title: "", date: istToday(), call_id: "" }); e.target.reset();
      onDone(data);
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  const pick = (id) => {
    const c = asList(calls.data).find((x) => x.id === id);
    setF((v) => ({ ...v, call_id: id, title: v.title || c?.title || "", date: c ? c.when.slice(0, 10) : v.date }));
  };
  return (
    <Card>
      <Label>New recap from a transcript</Label>
      {busy ? <Thinking label="Writing the recap and the audio. This takes about a minute." /> : (
        <form onSubmit={submit} className="space-y-3">
          <Field label="Transcript" hint=".txt, .vtt (Zoom), .srt or .md, up to 8 MB. Timecodes are removed.">
            <input type="file" accept=".txt,.vtt,.srt,.md,text/plain,text/vtt,text/markdown" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="recap-file"
              className="block w-full text-[14px] file:mr-3 file:min-h-[44px] file:px-4 file:rounded-bzbtn file:border file:border-bz-line file:bg-bz-inset file:text-bz-ink file:font-semibold" />
          </Field>
          <Field label="Which call (optional)">
            <Select value={f.call_id} onChange={(e) => pick(e.target.value)} data-testid="recap-call">
              <option value="">Not linked to a call</option>
              {asList(calls.data).filter((c) => c.over).map((c) => <option key={c.id} value={c.id}>{dt(c.when)} · {c.title}</option>)}
            </Select>
          </Field>
          <div className="grid gap-3 sm:grid-cols-[1fr_200px]">
            <Field label="Session title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={140} placeholder="e.g. Pricing your first project" data-testid="recap-title-input" /></Field>
            <Field label="Session date"><Input type="date" value={f.date} onChange={(e) => setF({ ...f, date: e.target.value })} /></Field>
          </div>
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <Button type="submit" variant="ai" disabled={!file} data-testid="recap-make">Make the recap</Button>
        </form>
      )}
    </Card>
  );
}

function toForm(r) {
  return {
    title: r.title, date: r.date || "", summary: r.summary || "",
    key_ideas: (r.key_ideas || []).join("\n"), action_points: (r.action_points || []).join("\n"),
    frameworks: (r.frameworks || []).map((x) => `${x.name} :: ${x.how_to_use}`).join("\n"),
    questions: (r.questions_answered || []).map((x) => `${x.q} :: ${x.a}`).join("\n"),
  };
}

function Detail({ id, onClose }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "recap", id], queryFn: async () => (await api.get(`/admin/recaps/${id}`)).data });
  const [f, setF] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const r = q.data;
  const v = f || (r ? toForm(r) : null);
  const after = (data, msg) => {
    qc.setQueryData(["admin", "recap", id], data);
    qc.invalidateQueries({ queryKey: ["admin", "recaps"] });
    setF(null); setOk(msg);
  };
  const act = async (kind, fn, msg) => {
    setErr(""); setOk(""); setBusy(kind);
    try { const { data } = await fn(); after(data, typeof msg === "function" ? msg(data) : msg); } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };
  const save = () => act("save", () => api.put(`/admin/recaps/${id}`, {
    title: v.title.trim(), date: v.date, call_id: r.call_id, summary: v.summary.trim(), key_ideas: lines(v.key_ideas).slice(0, 8),
    action_points: lines(v.action_points).slice(0, 8), frameworks: pairs(v.frameworks, "name", "how_to_use").slice(0, 6),
    questions_answered: pairs(v.questions, "q", "a").filter((x) => x.a).slice(0, 10),
  }, { timeout: 120000 }), "Saved.");
  const publish = () => {
    if (!window.confirm("Publish this recap? Every L1 and L2 member gets a message in their inbox.")) return;
    act("publish", () => api.post(`/admin/recaps/${id}/publish`), (d) => `Published. ${d.alerted} member${d.alerted === 1 ? "" : "s"} told.`);
  };
  const remove = async () => {
    if (!window.confirm("Delete this recap, its audio and its transcript in the knowledge base?")) return;
    try { await api.delete(`/admin/recaps/${id}`); qc.invalidateQueries({ queryKey: ["admin", "recaps"] }); onClose(); } catch (e) { setErr(apiError(e)); }
  };
  const set = (k) => (e) => setF({ ...v, [k]: e.target.value });
  return (
    <Sheet open onClose={onClose} title={r?.title || "Recap"} wide>
      {q.isLoading || !v ? <Skeleton lines={8} /> : (
        <div className="space-y-4" data-testid="admin-recap-detail">
          <div className="flex flex-wrap items-center gap-2 text-[14px]">
            <Chip tone={r.status === "published" ? "solid" : "muted"}>{r.status === "published" ? "Published" : "Draft"}</Chip>
            <span className="text-bz-muted">{r.words?.toLocaleString("en-IN")} words · made {dt(r.created_at)}{r.published_at ? ` · published ${dt(r.published_at)}` : ""}</span>
          </div>
          {r.audio_url ? <audio controls preload="none" src={`${API_BASE}${r.audio_url.replace(/^\/api/, "")}`} className="w-full" />
            : <p className="text-sm text-bz-miss">{r.audio_error || "No audio yet."}</p>}
          <div className="grid gap-3 sm:grid-cols-[1fr_200px]">
            <Field label="Title"><Input value={v.title} onChange={set("title")} maxLength={140} /></Field>
            <Field label="Date"><Input type="date" value={v.date} onChange={set("date")} /></Field>
          </div>
          <Field label="Summary"><Textarea value={v.summary} onChange={set("summary")} maxLength={1600} rows={5} data-testid="recap-summary-edit" /></Field>
          <Field label="Key ideas" hint="One per line (2–8)."><Textarea value={v.key_ideas} onChange={set("key_ideas")} rows={5} /></Field>
          <Field label="Frameworks" hint="One per line: Name :: how to use it."><Textarea value={v.frameworks} onChange={set("frameworks")} rows={3} /></Field>
          <Field label="Action points" hint="One per line (2–8). Read out in the audio."><Textarea value={v.action_points} onChange={set("action_points")} rows={4} /></Field>
          <Field label="Questions answered" hint="One per line: Question :: answer."><Textarea value={v.questions} onChange={set("questions")} rows={4} /></Field>
          {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
          <OkLine>{ok}</OkLine>
          <div className="flex flex-wrap gap-2">
            {r.status !== "published"
              ? <Button onClick={publish} loading={busy === "publish"} data-testid="recap-publish">Publish and tell members</Button>
              : <Button variant="secondary" onClick={() => act("unpub", () => api.post(`/admin/recaps/${id}/unpublish`), "Hidden from members.")} loading={busy === "unpub"}>Hide from members</Button>}
            <Button variant="secondary" onClick={save} loading={busy === "save"} disabled={!f} data-testid="recap-save">Save changes</Button>
            {!r.audio_url && <Button variant="secondary" onClick={() => act("audio", () => api.post(`/admin/recaps/${id}/audio`, null, { timeout: 120000 }), "Audio made.")} loading={busy === "audio"}>Make the audio again</Button>}
            <Button variant="danger" onClick={remove}>Delete</Button>
          </div>
        </div>
      )}
    </Sheet>
  );
}

export default function AdminRecaps() {
  const qc = useQueryClient();
  const q = useAdmin("recaps");
  const [sel, setSel] = useState(null);
  const [ok, setOk] = useState("");
  return (
    <div className="space-y-4">
      <UploadCard onDone={(r) => { qc.invalidateQueries({ queryKey: ["admin", "recaps"] }); setOk(`Draft ready: "${r.title}". Check it, then publish.`); setSel(r.id); }} />
      <OkLine>{ok}</OkLine>
      <AdminLoadable q={q} what="recaps">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} onRow={(r) => setSel(r.id)} empty="No recaps yet. Upload the transcript of the last session." cols={[
              { key: "date", label: "Session", render: (r) => hdate(r.date) },
              { key: "title", label: "Title", wrap: true, render: (r) => <b>{r.title}</b> },
              { key: "status", label: "Status", render: (r) => (r.status === "published" ? <Chip tone="solid">Published</Chip> : <Chip>Draft</Chip>) },
              { key: "has_audio", label: "Audio", render: (r) => (r.has_audio ? "Yes" : <span className="text-bz-miss">{r.audio_error ? "Failed" : "No"}</span>) },
              { key: "published_at", label: "Published", render: (r) => dt(r.published_at) },
            ]} />
          </Card>
        )}
      </AdminLoadable>
      {sel && <Detail id={sel} onClose={() => setSel(null)} />}
    </div>
  );
}

