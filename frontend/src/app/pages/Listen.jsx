// /app/listen — Listen mode: hear this week's case, the practice cases and your Meeting Briefs as audio.
// Each one is made once; playing it again is free. This week's case is shared, so it's often ready already.
import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Headphones, Play } from "lucide-react";
import { API_BASE, api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { Gate, Para, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Label, Loadable, Note, PageHeader, Thinking } from "../components/ui";

const HEADER = <PageHeader kicker="Listen mode" ai title="Hear your cases and briefs" accent="on the go."
  sub="Tap Listen and the case or brief is read out to you, in a few minutes. Good for a walk or the drive to a meeting." />;
const ORIGIN = API_BASE.replace(/\/api$/, "");

function Player({ track }) {
  if (!track) return null;
  return (
    <AiFrame title="Now playing" className="sticky top-2 z-10" right={track.shared ? <Chip tone="teal">Shared</Chip> : null}>
      <p className="text-[17px] font-extrabold leading-snug">{track.title}</p>
      {track.sub && <p className="text-[13px] text-bz-muted mt-0.5">{track.sub}</p>}
      <audio key={track.url} src={`${ORIGIN}${track.url}`} controls autoPlay preload="auto" className="w-full mt-3" data-testid="listen-audio" />
      {track.script && (
        <details className="mt-2">
          <summary className="cursor-pointer text-[13px] font-bold text-bz-muted min-h-[40px] flex items-center">Read along</summary>
          <Para text={track.script} className="text-[14px] text-bz-muted" />
        </details>
      )}
    </AiFrame>
  );
}

function Row({ item, busy, onListen, onPlay, canRun }) {
  const ready = !!item.track;
  return (
    <div className="flex items-center gap-3 py-3 border-b border-bz-line last:border-0 min-h-[64px]">
      <div className="min-w-0 flex-1">
        <p className="text-[15px] font-bold truncate">{item.title}</p>
        <p className="text-[13px] text-bz-muted truncate">{item.source === "brief" ? `Brief · ${hdate(item.sub)}` : item.sub}</p>
      </div>
      {busy ? <span className="shrink-0"><Thinking label="Making audio" /></span> : ready ? (
        <Button variant="small" onClick={() => onPlay(item.track)} data-testid={`listen-play-${item.id}`} className="shrink-0 !min-h-[44px]">
          <Play className="w-4 h-4" aria-hidden /> Play
        </Button>
      ) : (
        <Button variant="ai" onClick={() => onListen(item)} disabled={!canRun && !item.free} data-testid={`listen-${item.id}`}
          className="shrink-0 !min-h-[44px] !px-4 !py-2 !text-[14px]">
          {item.free ? "Listen · free" : "Listen"}
        </Button>
      )}
    </div>
  );
}

function ListenHome() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["listen-sources"], queryFn: async () => (await api.get("/listen/sources")).data });
  const [playing, setPlaying] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const usage = plan?.limits?.audio;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const listen = async (item) => {
    setErr(""); setBusy(`${item.source}:${item.id}`);
    try {
      const { data } = await api.post("/listen", { source: item.source, id: item.id }, { timeout: 120000 });
      setPlaying(data);
      qc.invalidateQueries({ queryKey: ["listen-sources"] });
      if (!data.cached) refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(""); }
  };
  const section = (title, items, empty) => (
    <Card>
      <Label>{title}</Label>
      {items.length ? items.map((it) => (
        <Row key={`${it.source}:${it.id}`} item={it} canRun={canRun} busy={busy === `${it.source}:${it.id}`} onListen={listen} onPlay={setPlaying} />
      )) : <Note>{empty}</Note>}
    </Card>
  );

  return (
    <div className="space-y-5">
      {HEADER}
      <Player track={playing} />
      <ErrorLine>{err}</ErrorLine>
      <UsageLine usage={usage} what="audio versions" />
      <Note>Playing something again is free. Only a new audio version counts.</Note>
      <Loadable q={q} what="what you can listen to" lines={6}>
        {(d) => {
          const all = [...(d.weekly || []), ...(d.cases || []), ...(d.briefs || [])];
          if (!all.length) return <Empty icon={Headphones} title="Nothing to listen to yet" sub="Cases and your Meeting Briefs show up here." />;
          return (
            <>
              {section("This week's case", d.weekly || [], "This week's case comes out on Monday morning.")}
              {section("Practice cases", d.cases || [], "No practice cases right now.")}
              {section("Your Meeting Briefs", d.briefs || [], "Make a Meeting Brief and you can listen to it on the way to the meeting.")}
            </>
          );
        }}
      </Loadable>
    </div>
  );
}

export default function Listen() {
  return <Gate feature="listen" header={HEADER}><ListenHome /></Gate>;
}
