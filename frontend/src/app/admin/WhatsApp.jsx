// Admin › WhatsApp templates: the exact wording to submit to Meta through AiSensy, one per message type, with
// copy buttons and a "Send me a test" that goes to the admin's own mobile (checks the AiSensy campaign works).
import { useState } from "react";
import { api, apiError } from "@/lib/api";
import { CopyButton } from "../components/Markdown";
import { Button, Card, Chip, ErrorLine, Note, OkLine } from "../components/ui";
import { AdminLoadable, useAdmin } from "./shared";

function Row({ label, value, mono }) {
  if (!value) return null;
  return (
    <div className="py-2 border-t border-bz-line first:border-t-0">
      <div className="flex items-center justify-between gap-2">
        <span className="text-[12.5px] font-semibold text-bz-muted">{label}</span>
        <CopyButton text={value} />
      </div>
      <p className={`whitespace-pre-line break-words text-[14px] mt-0.5 ${mono ? "font-bzmono text-[13px]" : ""}`}>{value}</p>
    </div>
  );
}

function Template({ t }) {
  const [busy, setBusy] = useState(false);
  const [ok, setOk] = useState("");
  const [err, setErr] = useState("");
  const test = async () => {
    setBusy(true); setOk(""); setErr("");
    try {
      const { data } = await api.post("/admin/whatsapp-templates/test", { kind: t.kind });
      if (data.ok) setOk(`Sent to your mobile through campaign ${data.campaign}.`);
      else setErr(`Not sent: ${data.error || "no reply"}. Check the campaign ${data.campaign} exists and is live.`);
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Card data-testid={`wa-${t.kind}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[17px] font-extrabold break-all">{t.template}</p>
          <p className="text-[13px] text-bz-muted mt-0.5">{t.when}</p>
        </div>
        <span className="flex gap-1.5 flex-wrap"><Chip tone="gold">{t.category}</Chip><Chip tone="muted">{t.language}</Chip></span>
      </div>
      <div className="mt-3">
        <Row label="Template name" value={t.template} mono />
        <Row label="API campaign (in AiSensy)" value={t.campaign} mono />
        <Row label="Body" value={t.body} />
        <Row label="Button text" value={t.button} />
        <Row label="Button URL (dynamic)" value={t.button_url} mono />
        <Row label="Sample for {{1}} in the body" value={t.sample} />
        <Row label="Sample for {{1}} in the button" value={t.sample_path} mono />
        {t.notes && <p className="text-[13px] text-bz-muted pt-2 border-t border-bz-line">{t.notes}</p>}
      </div>
      {t.kind !== "otp" && (
        <div className="mt-3">
          <Button variant="small" onClick={test} loading={busy} data-testid={`wa-test-${t.kind}`}>Send me a test</Button>
          <OkLine>{ok}</OkLine>
          <ErrorLine>{err}</ErrorLine>
        </div>
      )}
    </Card>
  );
}

export default function AdminWhatsApp() {
  const q = useAdmin("whatsapp-templates");
  return (
    <AdminLoadable q={q} what="WhatsApp templates">
      {(d) => (
        <div className="space-y-4">
          <Note>
            <ol className="list-decimal pl-5 space-y-1">{(d.steps || []).map((s) => <li key={s}>{s}</li>)}</ol>
          </Note>
          {(d.items || []).map((t) => <Template key={t.kind} t={t} />)}
          {d.not_sent_yet?.length > 0 && (
            <p className="text-[13px] text-bz-muted">No template needed yet for: {d.not_sent_yet.join(", ")} (the app doesn't send these on WhatsApp today).</p>
          )}
        </div>
      )}
    </AdminLoadable>
  );
}
