// Admin › Recordings and workbooks: add videos (YouTube / Vimeo play inside the hub), links and workbooks.
// A workbook can be a link or an uploaded PDF (up to 15 MB, served to members after a plan check).
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { FileText, Pencil, Plus, Trash2 } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip, Field, Input, Select, Sheet, Textarea } from "../components/ui";
import { AdminLoadable, asList, Table, useAdmin } from "./shared";

const blank = { title: "", kind: "video", url: "", description: "", plan_min: "l1", section: "General", order: 0, published: true };
const MAX = 15 * 1024 * 1024;

function Editor({ edit, onClose, onSaved }) {
  const [v, setV] = useState(edit.value);
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (e) => setV({ ...v, [k]: k === "order" ? Number(e.target.value) : k === "published" ? e.target.value === "yes" : e.target.value });
  const save = async () => {
    setErr("");
    if (v.title.trim().length < 2) { setErr("Add a title."); return; }
    if (v.url.trim() && !/^https?:\/\//i.test(v.url.trim())) { setErr("The link must start with https://"); return; }
    if (v.kind !== "workbook" && !v.url.trim()) { setErr("Add the link for this video or page."); return; }
    if (v.kind === "workbook" && !v.url.trim() && !file && !edit.row?.file_url) { setErr("Add a link or choose a PDF."); return; }
    if (file && (!/\.pdf$/i.test(file.name) || file.size > MAX)) { setErr("Choose a PDF up to 15 MB."); return; }
    setBusy(true);
    try {
      const body = { ...v, title: v.title.trim(), url: v.url.trim(), section: v.section.trim() || "General", order: Number(v.order) || 0 };
      const { data } = edit.id ? await api.put(`/admin/library/${edit.id}`, body) : await api.post("/admin/library", body);
      if (file) {
        const fd = new FormData();
        fd.append("file", file);
        await api.post(`/admin/library/${data.id}/file`, fd, { headers: { "Content-Type": "multipart/form-data" }, timeout: 120000 });
      }
      onSaved();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const removeFile = async () => {
    if (!window.confirm("Remove the uploaded PDF?")) return;
    try { await api.delete(`/admin/library/${edit.id}/file`); onSaved(); } catch (e) { setErr(apiError(e)); }
  };
  return (
    <Sheet open onClose={onClose} title={edit.id ? "Edit item" : "Add item"}>
      <div className="space-y-3">
        <Field label="Title"><Input value={v.title} onChange={set("title")} maxLength={140} placeholder="e.g. Session 3: pricing" data-testid="library-title" /></Field>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Type">
            <Select value={v.kind} onChange={set("kind")} data-testid="library-kind">
              <option value="video">Recording (video)</option>
              <option value="workbook">Workbook</option>
              <option value="link">Link</option>
            </Select>
          </Field>
          <Field label="Who sees it">
            <Select value={v.plan_min} onChange={set("plan_min")}>
              <option value="l1">L1 and L2</option>
              <option value="l2">L2 only</option>
            </Select>
          </Field>
        </div>
        <Field label={v.kind === "workbook" ? "Link (optional if you upload a PDF)" : "Link"} hint={v.kind === "video" ? "YouTube and Vimeo links play inside the hub. Other links open in a new tab." : undefined}>
          <Input value={v.url} onChange={set("url")} maxLength={500} placeholder="https://…" data-testid="library-url" />
        </Field>
        {v.kind === "workbook" && (
          <Field label="Workbook PDF (up to 15 MB)" hint={edit.row?.file_name ? `Now: ${edit.row.file_name}. Choose a new file to replace it.` : undefined}>
            <input type="file" accept="application/pdf,.pdf" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="library-file"
              className="block w-full text-[14px] file:mr-3 file:min-h-[44px] file:px-4 file:rounded-bzbtn file:border file:border-bz-line file:bg-bz-inset file:text-bz-ink file:font-semibold" />
          </Field>
        )}
        {edit.row?.file_url && <Button variant="small" onClick={removeFile}>Remove the uploaded PDF</Button>}
        <Field label="Short description (optional)"><Textarea value={v.description} onChange={set("description")} maxLength={1000} rows={2} /></Field>
        <div className="grid gap-3 grid-cols-2 sm:grid-cols-3">
          <Field label="Section" className="col-span-2 sm:col-span-1"><Input value={v.section} onChange={set("section")} maxLength={60} placeholder="e.g. Week 1" /></Field>
          <Field label="Order"><Input type="number" min="0" value={v.order} onChange={set("order")} /></Field>
          <Field label="Show to members">
            <Select value={v.published ? "yes" : "no"} onChange={set("published")}><option value="yes">Yes</option><option value="no">Hidden</option></Select>
          </Field>
        </div>
        {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
        <div className="flex gap-2">
          <Button className="flex-1" onClick={save} loading={busy} data-testid="admin-save">Save</Button>
          <Button variant="secondary" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Sheet>
  );
}

export default function AdminLibrary() {
  const qc = useQueryClient();
  const q = useAdmin("library");
  const [edit, setEdit] = useState(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "library"] });
  const open = (r) => setEdit(r ? { id: r.id, row: r, value: { ...blank, ...r } } : { id: null, row: null, value: { ...blank } });
  const remove = async (r) => {
    if (!window.confirm(`Delete "${r.title}"? This cannot be undone.`)) return;
    try { await api.delete(`/admin/library/${r.id}`); refresh(); } catch (e) { window.alert(apiError(e)); }
  };
  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => open(null)} data-testid="admin-add-library"><Plus className="w-4 h-4" aria-hidden /> Add</Button>
      </div>
      <AdminLoadable q={q} what="the library">
        {(d) => (
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} onRow={open} empty="Nothing yet. Add the first recording or workbook." cols={[
              { key: "section", label: "Section" },
              { key: "order", label: "#", right: true },
              { key: "title", label: "Title", wrap: true, render: (r) => <b>{r.title}</b> },
              { key: "kind", label: "Type", render: (r) => (r.embed ? `${r.kind} · ${r.embed.provider}` : r.kind) },
              { key: "file", label: "PDF", render: (r) => (r.file_url ? <span className="inline-flex items-center gap-1"><FileText className="w-4 h-4 text-bz-gold" aria-hidden />{r.file_size ? `${(r.file_size / 1048576).toFixed(1)} MB` : "yes"}</span> : "—") },
              { key: "plan_min", label: "Who", render: (r) => (r.plan_min === "l2" ? <Chip tone="solid">L2 only</Chip> : "L1 + L2") },
              { key: "published", label: "Shown", render: (r) => (r.published ? <Chip tone="gold">Shown</Chip> : <Chip>Hidden</Chip>) },
              { key: "_a", label: "", render: (r) => (
                <span className="flex gap-1 justify-end">
                  <button type="button" className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-card" aria-label="Edit" onClick={(e) => { e.stopPropagation(); open(r); }}><Pencil className="w-4 h-4" aria-hidden /></button>
                  <button type="button" className="w-9 h-9 grid place-items-center rounded-bzbtn hover:bg-bz-miss-tint text-bz-miss" aria-label="Delete" onClick={(e) => { e.stopPropagation(); remove(r); }}><Trash2 className="w-4 h-4" aria-hidden /></button>
                </span>
              ) },
            ]} />
          </Card>
        )}
      </AdminLoadable>
      {edit && <Editor edit={edit} onClose={() => setEdit(null)} onSaved={() => { setEdit(null); refresh(); }} />}
    </div>
  );
}
