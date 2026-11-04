// /app/bootcamps and /app/bootcamps/:id — L2 bootcamps: tasks with a written answer and/or a link to the work
// (Google Drive and the like; no big uploads), sent for review; the team's feedback shows under each task.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLink, Flag } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { ago } from "@/lib/format";
import { BackLink, Gate, Para } from "../components/common";
import { Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Meter, OkLine, PageHeader, RowLink, Textarea } from "../components/ui";

const STATUS = {
  none: { tone: "muted", label: "Not started" },
  submitted: { tone: "gold", label: "Sent for review" },
  reviewed: { tone: "solid", label: "Reviewed" },
};

function Task({ bid, t, i }) {
  const qc = useQueryClient();
  const s = t.submission;
  const [f, setF] = useState({ text: s?.text || "", link: s?.link || "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const st = STATUS[s?.status || "none"];
  const send = async (e) => {
    e.preventDefault();
    setErr(""); setOk("");
    const text = f.text.trim();
    const link = f.link.trim();
    if (!text && !link) { setErr("Write your answer or add a link to your work."); return; }
    if (link && !/^https?:\/\//i.test(link)) { setErr("The link must start with https://"); return; }
    setBusy(true);
    try {
      const { data } = await api.post(`/bootcamps/${bid}/tasks/${t.id}`, { text, link });
      qc.setQueryData(["bootcamp", bid], data);
      qc.invalidateQueries({ queryKey: ["bootcamps"] });
      setOk("Sent. The team will review it.");
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };
  return (
    <Card data-testid={`bootcamp-task-${t.id}`}>
      <div className="flex items-start gap-3">
        <span className="w-[34px] h-[34px] shrink-0 rounded-full border border-bz-gold text-bz-gold grid place-items-center text-[14px] font-extrabold">{i + 1}</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-[17px] font-extrabold leading-snug">{t.title}</p>
            <Chip tone={st.tone}>{st.label}</Chip>
          </div>
          {t.detail && <Para text={t.detail} className="text-[14px] text-bz-muted mt-1" />}
        </div>
      </div>
      {s?.feedback && (
        <div className="mt-4 rounded-bzcard border border-bz-rule bg-bz-gold-tint p-3.5" data-testid={`bootcamp-feedback-${t.id}`}>
          <p className="text-[12px] font-medium uppercase tracking-[0.14em] text-bz-gold mb-1">Feedback from the team</p>
          <Para text={s.feedback} className="text-[15px]" />
        </div>
      )}
      <form onSubmit={send} noValidate className="mt-4 space-y-3">
        <Field label="Your answer">
          <Textarea value={f.text} onChange={(e) => setF({ ...f, text: e.target.value })} maxLength={4000} rows={4}
            placeholder="Write it here, or add a link below." data-testid={`bootcamp-text-${t.id}`} />
        </Field>
        <Field label="Link to your work (optional)" hint="Google Drive, Docs or any link the team can open. Set sharing to 'anyone with the link'.">
          <Input type="url" inputMode="url" value={f.link} onChange={(e) => setF({ ...f, link: e.target.value })} maxLength={500}
            placeholder="https://drive.google.com/…" data-testid={`bootcamp-link-${t.id}`} />
        </Field>
        <ErrorLine>{err}</ErrorLine>
        <OkLine>{ok}</OkLine>
        <div className="flex flex-col sm:flex-row sm:items-center gap-2">
          <Button type="submit" variant="secondary" loading={busy} data-testid={`bootcamp-send-${t.id}`}>
            {s ? "Send my update" : "Send for review"}
          </Button>
          {s?.at && <span className="text-[13px] text-bz-muted">Last sent {ago(s.at)}</span>}
        </div>
      </form>
    </Card>
  );
}

function Detail({ id }) {
  const q = useQuery({ queryKey: ["bootcamp", id], queryFn: async () => (await api.get(`/bootcamps/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/bootcamps">All bootcamps</BackLink>
      <Loadable q={q} what="this bootcamp" lines={6}>
        {(b) => (
          <div className="space-y-4">
            <PageHeader kicker={`Bootcamp ${b.n}`} title={b.title} sub={b.description} />
            <Card data-testid="bootcamp-progress">
              <div className="flex justify-between text-[14px]"><span>{b.progress.submitted} of {b.progress.total} tasks sent</span><span className="text-bz-muted">{b.progress.reviewed} reviewed</span></div>
              <Meter value={b.progress.pct} className="mt-2" label="Tasks sent" />
            </Card>
            {b.resources?.length > 0 && (
              <Card>
                <Label>Resources</Label>
                <ul className="space-y-1">
                  {b.resources.map((r, i) => (
                    <li key={i}>
                      <a href={r.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1.5 min-h-[44px] text-[15px] font-bold hover:text-bz-gold">
                        <ExternalLink className="w-4 h-4 text-bz-gold shrink-0" aria-hidden /> {r.title}
                      </a>
                    </li>
                  ))}
                </ul>
              </Card>
            )}
            {b.task_list.length ? b.task_list.map((t, i) => <Task key={t.id} bid={b.id} t={t} i={i} />)
              : <Empty title="Tasks are being added" sub="Check back soon." />}
          </div>
        )}
      </Loadable>
    </div>
  );
}

function List() {
  const q = useQuery({ queryKey: ["bootcamps"], queryFn: async () => (await api.get("/bootcamps")).data });
  return (
    <Loadable q={q} what="the bootcamps" lines={5}>
      {(d) => (d.items || []).length ? (
        <div className="space-y-3" data-testid="bootcamps-list">
          {d.items.map((b) => (
            <Card key={b.id} className="py-2">
              <RowLink to={`/app/bootcamps/${b.id}`} testid={`bootcamp-${b.id}`} title={`${b.n}. ${b.title}`}
                sub={`${b.progress.submitted} of ${b.progress.total} tasks sent · ${b.progress.reviewed} reviewed`}
                right={<span className="text-[18px] font-extrabold text-bz-gold tabular">{b.progress.pct}%</span>} />
              <Meter value={b.progress.pct} className="mb-3" label={`${b.title} progress`} />
            </Card>
          ))}
        </div>
      ) : <Empty icon={Flag} title="Bootcamps open soon" sub="The team is getting the first bootcamp ready. You'll see it here." />}
    </Loadable>
  );
}

export default function Bootcamps() {
  const { id } = useParams();
  const header = (
    <PageHeader kicker="Bootcamps" title="Build your practice," accent="step by step."
      sub="Each bootcamp has a few tasks. Write your answer here or share a link to your work. The team reviews it and replies." />
  );
  return (
    <Gate feature="bootcamps" header={header}>
      <div className="space-y-5">
        {id ? <Detail id={id} /> : <>{header}<List /></>}
      </div>
    </Gate>
  );
}
