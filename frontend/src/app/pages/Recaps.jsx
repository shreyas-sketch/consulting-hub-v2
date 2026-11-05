// /app/recaps and /app/recaps/:id — Session Recap Pack: after every session a summary, key ideas, frameworks,
// action points, questions answered and an audio version of the summary and action points.
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Headphones, PlayCircle } from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import { hdate } from "@/lib/format";
import { BackLink, Gate } from "../components/common";
import { AiFrame, Button, Card, Chip, Empty, Label, Loadable, PageHeader, RowLink, Step } from "../components/ui";

const apiHref = (path) => (path ? `${API_BASE}${path.replace(/^\/api/, "")}` : null);

function Section({ title, children }) {
  return (
    <div className="mt-6 first:mt-0">
      <p className="text-[12px] font-semibold text-bz-teal mb-2.5">{title}</p>
      {children}
    </div>
  );
}

function RecapBody({ r }) {
  return (
    <AiFrame title="Session recap" right={<span className="text-[12px] text-bz-muted">{hdate(r.date)}</span>} className="print-plain">
      <p className="text-[24px] font-display font-[500] tracking-[-0.01em] leading-tight" data-testid="recap-title">{r.title}</p>
      {r.audio_url && (
        <div className="mt-4 rounded-bzcard border border-bz-line bg-bz-panel p-3.5 no-print" data-testid="recap-audio">
          <p className="text-[13px] font-bold flex items-center gap-1.5 mb-2"><Headphones className="w-4 h-4 text-bz-teal" aria-hidden /> Listen: summary and action points</p>
          <audio controls preload="none" src={apiHref(r.audio_url)} className="w-full" />
        </div>
      )}
      <div className="mt-5">
        <Section title="Summary"><p className="text-[16px] leading-relaxed" data-testid="recap-summary">{r.summary}</p></Section>
        {r.key_ideas?.length > 0 && (
          <Section title="Key ideas">
            <ul className="space-y-2 text-[15px] list-disc pl-5">{r.key_ideas.map((x, i) => <li key={i}>{x}</li>)}</ul>
          </Section>
        )}
        {r.frameworks?.length > 0 && (
          <Section title="Frameworks">
            <div className="space-y-3">
              {r.frameworks.map((f, i) => (
                <div key={i} className="rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
                  <p className="font-bold text-[15px]">{f.name}</p>
                  {f.how_to_use && <p className="text-[14px] text-bz-muted mt-1 leading-relaxed">{f.how_to_use}</p>}
                </div>
              ))}
            </div>
          </Section>
        )}
        {r.action_points?.length > 0 && (
          <Section title="Do this week">
            <div className="space-y-3" data-testid="recap-actions">{r.action_points.map((a, i) => <Step key={i} n={i + 1} ai title={a} />)}</div>
          </Section>
        )}
        {r.questions_answered?.length > 0 && (
          <Section title="Questions answered">
            <div className="space-y-2">
              {r.questions_answered.map((x, i) => (
                <details key={i} className="rounded-bzcard border border-bz-line bg-bz-panel px-3.5">
                  <summary className="cursor-pointer font-bold text-[15px] min-h-[48px] flex items-center">{x.q}</summary>
                  <p className="text-[14px] text-bz-muted pb-3.5 leading-relaxed">{x.a}</p>
                </details>
              ))}
            </div>
          </Section>
        )}
      </div>
    </AiFrame>
  );
}

function One({ id }) {
  const q = useQuery({ queryKey: ["recap", id], queryFn: async () => (await api.get(`/recaps/${id}`)).data });
  return (
    <div className="space-y-4">
      <BackLink to="/app/recaps">All recaps</BackLink>
      <Loadable q={q} what="this recap" lines={8}>
        {(r) => (
          <>
            <RecapBody r={r} />
            <div className="flex flex-col sm:flex-row gap-2 no-print">
              {r.call?.recording_url && (
                <a href={r.call.recording_url} target="_blank" rel="noopener noreferrer" data-testid="recap-recording"
                  className="inline-flex items-center justify-center gap-2 min-h-[52px] px-6 rounded-bzbtn border border-bz-rule text-bz-ink font-bold text-[15px] hover:border-bz-gold">
                  <PlayCircle className="w-5 h-5 text-bz-gold" aria-hidden /> Watch the session
                </a>
              )}
              <Button variant="secondary" onClick={() => window.print()}>Print or save as PDF</Button>
            </div>
          </>
        )}
      </Loadable>
    </div>
  );
}

function List() {
  const q = useQuery({ queryKey: ["recaps"], queryFn: async () => (await api.get("/recaps")).data });
  return (
    <Loadable q={q} what="your recaps" lines={5}>
      {(d) => (d.items || []).length ? (
        <Card data-testid="recaps-list">
          <Label>All sessions</Label>
          {d.items.map((r) => (
            <RowLink key={r.id} to={`/app/recaps/${r.id}`} title={r.title} sub={hdate(r.date)} testid={`recap-${r.id}`}
              right={r.has_audio ? <Chip tone="teal"><Headphones className="w-3.5 h-3.5" aria-hidden /> Audio</Chip> : <Chip tone="teal">Read</Chip>} />
          ))}
        </Card>
      ) : <Empty icon={Headphones} title="No recaps yet" sub="After each group call, its recap shows here. You'll get a message in your inbox when it's ready." />}
    </Loadable>
  );
}

export default function Recaps() {
  const { id } = useParams();
  const header = (
    <PageHeader kicker="Session Recap Pack" ai title="Every session," accent="in five minutes."
      sub="After each session: a short summary, the key ideas, the frameworks, what to do this week, and an audio version." />
  );
  return (
    <Gate feature="recaps" header={header}>
      <div className="space-y-5">
        {!id && header}
        {id ? <One id={id} /> : <List />}
      </div>
    </Gate>
  );
}
