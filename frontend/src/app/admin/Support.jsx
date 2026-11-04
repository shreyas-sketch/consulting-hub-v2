// Admin › Support inbox: members' questions by status (open first, oldest first), search, the thread with the
// member's name / phone / plan, a reply box (marks it answered and sends the member an inbox alert) and close.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Para } from "../components/common";
import { Button, Card, Chip, ErrorCard, ErrorLine, Field, Input, Label, OkLine, Segmented, Skeleton, Textarea } from "../components/ui";
import { AdminLoadable, dt, useAdmin } from "./shared";

const CAT = { billing: "Payments", tools: "Tools", program: "Program", other: "Other" };
const TONE = { open: "gold", answered: "teal", closed: "muted" };

function Thread({ id, onBack, onChanged }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["admin", "support", id], queryFn: async () => (await api.get(`/admin/support/${id}`)).data });
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const done = (data, msg) => { qc.setQueryData(["admin", "support", id], data); setOk(msg); onChanged(); };
  const reply = async () => {
    if (!text.trim()) return;
    setErr(""); setOk(""); setBusy(true);
    try { done((await api.post(`/admin/support/${id}/reply`, { text })).data, "Sent. The member gets an inbox message."); setText(""); }
    catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  const close = async () => {
    setErr(""); setOk("");
    try { done((await api.post(`/admin/support/${id}/close`)).data, "Closed."); } catch (e) { setErr(apiError(e)); }
  };
  if (q.isLoading) return <Card><Skeleton lines={6} /></Card>;
  if (q.isError) return <ErrorCard error={q.error} what="this ticket" onRetry={() => q.refetch()} />;
  const t = q.data;
  return (
    <div className="space-y-4" data-testid="admin-support-thread">
      <button type="button" onClick={onBack} className="lg:hidden text-[13px] font-bold text-bz-gold min-h-[40px]">Back to the inbox</button>
      <Card>
        <div className="flex flex-wrap items-center gap-2"><Chip tone={TONE[t.status]}>{t.status}</Chip><Chip>{CAT[t.category] || t.category}</Chip></div>
        <p className="text-[22px] font-extrabold leading-tight mt-2">{t.subject}</p>
        <div className="mt-2 text-[14px] text-bz-muted space-y-0.5">
          <p><b className="text-bz-ink">{t.member?.name || "Member"}</b> · {t.member?.phone || t.member?.email || "—"}</p>
          <p>{t.member?.plan_label} · opened {dt(t.created_at)}</p>
        </div>
      </Card>
      <div className="space-y-3">
        {t.messages.map((m, i) => (
          <Card key={i} inset={m.from === "member"} className={m.from === "team" ? "border-bz-gold" : ""}>
            <div className="flex items-center justify-between gap-2 mb-1.5">
              <Label tone={m.from === "team" ? "gold" : "muted"} className="mb-0">{m.from === "team" ? `Team · ${m.by_name || "Admin"}` : "Member"}</Label>
              <span className="text-[12px] text-bz-muted">{dt(m.at)}</span>
            </div>
            <Para text={m.text} className="text-[15px]" />
          </Card>
        ))}
      </div>
      <Card>
        <Field label="Reply to the member" hint="Plain, short sentences. The member sees it as 'Support team'.">
          <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={4000} data-testid="admin-support-reply" />
        </Field>
        <ErrorLine>{err}</ErrorLine>
        <OkLine>{ok}</OkLine>
        <div className="flex flex-col sm:flex-row gap-2 mt-3">
          <Button className="flex-1" onClick={reply} loading={busy} disabled={!text.trim()} data-testid="admin-support-send">Send reply</Button>
          {t.status !== "closed" && <Button variant="secondary" onClick={close} data-testid="admin-support-close">Close</Button>}
        </div>
      </Card>
    </div>
  );
}

export default function AdminSupport() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("open");
  const [find, setFind] = useState("");
  const [sel, setSel] = useState(null);
  const params = { ...(status === "all" ? {} : { status }), ...(find.trim() ? { q: find.trim() } : {}) };
  const q = useAdmin("support", params);
  const counts = q.data?.counts || {};
  const opts = [
    { value: "open", label: `Open${counts.open != null ? ` (${counts.open})` : ""}` },
    { value: "answered", label: `Answered${counts.answered != null ? ` (${counts.answered})` : ""}` },
    { value: "closed", label: "Closed" }, { value: "all", label: "All" },
  ];
  const changed = () => qc.invalidateQueries({ queryKey: ["admin", "support"] });
  return (
    <div className="lg:grid lg:grid-cols-[380px_minmax(0,1fr)] lg:gap-6 space-y-4 lg:space-y-0">
      <div className={`space-y-3 ${sel ? "hidden lg:block" : ""}`}>
        <Segmented options={opts} value={status} onChange={(v) => { setStatus(v); setSel(null); }} label="Status" testid="admin-support-filter" />
        <Input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Search subject, name or phone" aria-label="Search" />
        <AdminLoadable q={q} what="the support inbox">
          {(d) => (d.items || []).length ? (
            <Card className="p-0 sm:p-0 overflow-hidden" data-testid="admin-support-list">
              {d.items.map((t) => (
                <button key={t.id} type="button" onClick={() => setSel(t.id)} data-testid={`admin-ticket-${t.id}`}
                  className={`w-full text-left px-4 py-3 border-b border-bz-line last:border-0 min-h-[56px] ${sel === t.id ? "bg-bz-raised" : "hover:bg-bz-raised"}`}>
                  <div className="flex items-start justify-between gap-2">
                    <span className="text-[15px] font-bold leading-snug">{t.subject}</span>
                    <Chip tone={TONE[t.status]}>{t.last_from === "member" && t.status === "open" ? "needs reply" : t.status}</Chip>
                  </div>
                  <span className="block text-[13px] text-bz-muted mt-0.5">{t.member?.name || "Member"} · {t.member?.plan_label} · {CAT[t.category] || t.category}</span>
                  <span className="block text-[13px] text-bz-muted truncate">{t.preview}</span>
                  <span className="block text-[12px] text-bz-faint mt-0.5">{dt(t.updated_at)}</span>
                </button>
              ))}
            </Card>
          ) : <p className="text-sm text-bz-muted py-4">Nothing here.</p>}
        </AdminLoadable>
      </div>
      <div className="min-w-0">
        {sel ? <Thread key={sel} id={sel} onBack={() => setSel(null)} onChanged={changed} />
          : <Card inset className="hidden lg:block"><p className="text-[15px] text-bz-muted">Pick a question on the left to read and reply.</p></Card>}
      </div>
    </div>
  );
}
