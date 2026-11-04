// Admin › Settings: the live case for the webinar, the group session invite, support WhatsApp number.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Button, Card, Field, Input, Label, OkLine, Select } from "../components/ui";
import { AdminLoadable, useAdmin } from "./shared";

function Editor({ s, cases }) {
  const qc = useQueryClient();
  const g = s.group_session || {};
  const [f, setF] = useState({ live_case_id: s.live_case_id, title: g.title || "", when: g.when || "", link: g.link || "", support: s.support_whatsapp || "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const save = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    if (f.link && !/^https?:\/\//.test(f.link.trim())) { setErr("The session link must start with https://"); return; }
    setBusy(true);
    try {
      const { data } = await api.post("/admin/settings", {
        live_case_id: f.live_case_id, support_whatsapp: f.support.trim(),
        group_session: { title: f.title.trim(), when: f.when.trim(), link: f.link.trim() },
      });
      if (data) qc.setQueryData(["admin", "settings", null], data);
      qc.invalidateQueries({ queryKey: ["admin", "cases"] });
      setOk("Saved.");
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <form onSubmit={save} className="space-y-4">
      <Card className="space-y-3">
        <Label>Live case on the webinar</Label>
        <p className="text-[13px] text-bz-muted -mt-1">Free accounts can answer this one case. Change it before each webinar if you like.</p>
        <Field label="Case" className="max-w-[520px]">
          <Select value={f.live_case_id} onChange={(e) => setF({ ...f, live_case_id: e.target.value })} data-testid="settings-live-case">
            {cases.map((c) => <option key={c.id} value={c.id}>{c.title} · {c.company} ({c.answers} answers)</option>)}
          </Select>
        </Field>
      </Card>
      <Card className="space-y-3">
        <Label>Group session with Akshat</Label>
        <p className="text-[13px] text-bz-muted -mt-1">Shown on the home screen of everyone on a free account or the ₹1,999 plan. Leave the link empty to hide it.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Title"><Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} maxLength={120} /></Field>
          <Field label="When" hint="e.g. Saturday 8 Nov, 11:00 am IST"><Input value={f.when} onChange={(e) => setF({ ...f, when: e.target.value })} maxLength={60} data-testid="settings-when" /></Field>
        </div>
        <Field label="Join link"><Input value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} placeholder="https://zoom.us/j/…" maxLength={300} data-testid="settings-link" /></Field>
      </Card>
      <Card className="space-y-3">
        <Label>Support</Label>
        <Field label="Support WhatsApp number" hint="Shown to members who need help." className="max-w-[320px]"><Input value={f.support} onChange={(e) => setF({ ...f, support: e.target.value })} placeholder="+91 98…" maxLength={20} /></Field>
      </Card>
      {err && <p className="text-sm text-bz-miss" role="alert">{err}</p>}
      <OkLine>{ok}</OkLine>
      <Button type="submit" loading={busy} data-testid="settings-save">Save settings</Button>
    </form>
  );
}

export default function AdminSettings() {
  const q = useAdmin("settings");
  const cases = useAdmin("cases");
  return (
    <AdminLoadable q={q} what="settings">
      {(d) => <AdminLoadable q={cases} what="cases">{(c) => <Editor s={d} cases={c.items || []} />}</AdminLoadable>}
    </AdminLoadable>
  );
}
