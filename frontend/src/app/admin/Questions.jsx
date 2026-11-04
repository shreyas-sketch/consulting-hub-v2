// Admin › Akshat AI questions: what the knowledge base couldn't answer, queued for the next group call.
// Type Akshat's answer: the question is marked answered, the answer goes into the member's chat and inbox.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Para } from "../components/common";
import { Button, Card, Chip, ErrorLine, Field, Label, OkLine, Segmented, Textarea } from "../components/ui";
import { AdminLoadable, dt, Kpi, useAdmin } from "./shared";

function Row({ x, onDone }) {
  const [text, setText] = useState(x.answer || "");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const send = async () => {
    if (text.trim().length < 5) { setErr("Write the answer first."); return; }
    setErr(""); setOk(""); setBusy(true);
    try {
      await api.post(`/admin/akshat-questions/${x.id}/answer`, { answer: text.trim() });
      setOk(x.status === "answered" ? "Answer updated." : "Sent. The member gets it in their chat and inbox.");
      onDone();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(false); }
  };
  return (
    <Card data-testid={`admin-akq-${x.id}`}>
      <div className="flex items-start justify-between gap-3">
        <p className="text-[17px] font-bold leading-snug">{x.question}</p>
        <Chip tone={x.status === "answered" ? "gold" : "muted"}>{x.status === "answered" ? "Answered" : "Waiting"}</Chip>
      </div>
      <p className="text-[13px] text-bz-muted mt-1">{x.name || "Member"} · {x.phone || "—"} · asked {dt(x.at)}{x.answered_at ? ` · answered ${dt(x.answered_at)}` : ""}</p>
      {x.status === "answered" && x.answer && !ok && <div className="mt-3 rounded-bzcard border border-bz-line bg-bz-panel p-3"><Para text={x.answer} className="text-[14.5px]" /></div>}
      <Field label={x.status === "answered" ? "Edit the answer" : "Akshat's answer"} className="mt-3">
        <Textarea value={text} onChange={(e) => setText(e.target.value)} maxLength={6000} placeholder="What Akshat said on the call, in plain words." data-testid={`admin-akq-text-${x.id}`} />
      </Field>
      <ErrorLine>{err}</ErrorLine>
      <OkLine>{ok}</OkLine>
      <Button className="mt-3 w-full sm:w-auto" variant={x.status === "answered" ? "secondary" : "primary"} onClick={send} loading={busy} data-testid={`admin-akq-send-${x.id}`}>
        {x.status === "answered" ? "Save the new answer" : "Send answer to the member"}
      </Button>
    </Card>
  );
}

export default function AdminQuestions() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("queued");
  const q = useAdmin("akshat-questions", { status });
  const counts = q.data?.counts || {};
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "akshat-questions"] });
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 max-w-[480px]">
        <Kpi label="Waiting for the call" value={counts.queued ?? "—"} tone="gold" />
        <Kpi label="Answered" value={counts.answered ?? "—"} />
      </div>
      <Segmented options={[{ value: "queued", label: "Waiting" }, { value: "answered", label: "Answered" }]} value={status} onChange={setStatus} label="Status" testid="admin-akq-filter" />
      <AdminLoadable q={q} what="the questions">
        {(d) => (d.items || []).length ? (
          <div className="space-y-3">
            <Label tone="muted">{status === "queued" ? "Oldest first. Take these to the next group call." : "Newest first."}</Label>
            {d.items.map((x) => <Row key={`${x.id}:${x.status}`} x={x} onDone={refresh} />)}
          </div>
        ) : <Card inset><p className="text-[15px] text-bz-muted">{status === "queued" ? "No questions waiting. Akshat AI answered everything from the sessions." : "No answered questions yet."}</p></Card>}
      </AdminLoadable>
    </div>
  );
}
