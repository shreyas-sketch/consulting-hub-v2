// /app/akshat-ai and /app/akshat-ai/:id (thread) — ask a question, get an answer from Akshat's own sessions with the
// session titles underneath. When the sessions don't cover it, the question goes to the next group call; the team's
// answer comes back into the same chat and the inbox. Questions sent to the call are listed with their answers.
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, MessageSquare, Plus } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import Markdown from "../components/Markdown";
import { Gate, Para, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, ErrorCard, ErrorLine, Label, Note, PageHeader, Sheet, Skeleton, Textarea, Thinking } from "../components/ui";

const EXAMPLES = [
  "How do I price my first consulting project?",
  "What should I say in my first discovery call?",
  "How do I find my first client from my network?",
];

function Threads({ items, current, onPick, onNew }) {
  return (
    <div className="space-y-2">
      <Button variant="small" className="w-full" onClick={onNew} data-testid="akshat-new"><Plus className="w-4 h-4" aria-hidden /> New question</Button>
      {items.length ? (
        <ul className="space-y-1">
          {items.map((t) => (
            <li key={t.id}>
              <button type="button" onClick={() => onPick(t.id)} data-testid={`akshat-thread-${t.id}`}
                className={`w-full text-left rounded-bzbtn px-3 py-2.5 min-h-[48px] ${t.id === current ? "bg-bz-raised" : "hover:bg-bz-raised"}`}>
                <span className={`block text-[14px] font-bold truncate ${t.id === current ? "text-bz-gold" : ""}`}>{t.title}</span>
                <span className="block text-[12px] text-bz-muted">{ago(t.updated_at)}{t.queued ? " · sent to the call" : ""}</span>
              </button>
            </li>
          ))}
        </ul>
      ) : <p className="text-[13px] text-bz-muted px-1">No questions yet.</p>}
    </div>
  );
}

function Answer({ m, innerRef }) {
  if (m.role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[88%] rounded-bzcard rounded-br-md bg-bz-raised border border-bz-line px-4 py-3">
          <Para text={m.text} className="text-[15px]" />
        </div>
      </div>
    );
  }
  if (m.from_call) {
    return (
      <div ref={innerRef} className="scroll-mt-20">
        <Card className="border-bz-gold" data-testid="akshat-call-answer">
          <Label className="mb-1.5">Akshat's answer from the group call</Label>
          <Para text={m.text} className="text-[15px]" />
        </Card>
      </div>
    );
  }
  if (m.status === "queued") {
    return (
      <div ref={innerRef} className="scroll-mt-20">
        <Card inset className="border-bz-gold" data-testid="akshat-queued">
          <div className="flex items-center justify-between gap-2 mb-1.5">
            <Label className="mb-0">Sent to the next group call</Label>
            <Chip tone={m.question_status === "answered" ? "gold" : "muted"}>{m.question_status === "answered" ? "Answered" : "Waiting"}</Chip>
          </div>
          <p className="text-[15px] leading-relaxed">{m.text}</p>
        </Card>
      </div>
    );
  }
  if (m.status === "declined") {
    return (
      <div ref={innerRef} className="scroll-mt-20">
        <Card inset data-testid="akshat-declined"><p className="text-[15px] leading-relaxed">{m.text}</p></Card>
      </div>
    );
  }
  return (
    <div ref={innerRef} className="scroll-mt-20">
      <AiFrame title="Akshat AI">
        <div data-testid="akshat-answer"><Markdown text={m.text} /></div>
        {m.sources?.length > 0 && (
          <div className="mt-3 pt-3 border-t border-bz-line" data-testid="akshat-sources">
            <p className="text-[12.5px] font-semibold text-bz-muted mb-1.5">From these sessions</p>
            <ul className="space-y-1">
              {m.sources.map((s) => (
                <li key={s.title} className="flex items-start gap-2 text-[13.5px]"><BookOpen className="w-3.5 h-3.5 mt-1 text-bz-teal shrink-0" aria-hidden />{s.title}</li>
              ))}
            </ul>
          </div>
        )}
      </AiFrame>
    </div>
  );
}

function Queue() {
  const q = useQuery({ queryKey: ["akshat-questions"], queryFn: async () => (await api.get("/akshat-ai/questions")).data });
  const items = q.data?.items || [];
  if (q.isLoading || !items.length) return null;
  return (
    <Card data-testid="akq-list">
      <Label>Questions you sent to the group call</Label>
      <ul className="divide-y divide-bz-line">
        {items.map((x) => (
          <li key={x.id} className="py-3">
            <div className="flex items-start justify-between gap-3">
              <p className="text-[15px] font-bold">{x.question}</p>
              <Chip tone={x.status === "answered" ? "gold" : "muted"}>{x.status === "answered" ? "Answered" : "Waiting"}</Chip>
            </div>
            <p className="text-[12px] text-bz-muted mt-0.5">Asked {hdate(x.at)}{x.answered_at ? ` · answered ${hdate(x.answered_at)}` : ""}</p>
            {x.answer && <Para text={x.answer} className="text-[14.5px] mt-2" />}
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Ask() {
  const { id } = useParams();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { plan, refreshMe } = useAuth();
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(null);
  const [err, setErr] = useState("");
  const [drawer, setDrawer] = useState(false);
  const lastRef = useRef(null);
  const scrollNext = useRef(false);
  const threads = useQuery({ queryKey: ["akshat-threads"], queryFn: async () => (await api.get("/akshat-ai/threads")).data });
  const thread = useQuery({ queryKey: ["akshat-thread", id], queryFn: async () => (await api.get(`/akshat-ai/threads/${id}`)).data, enabled: !!id });
  const messages = (id && thread.data?.messages) || [];

  useEffect(() => {
    if (scrollNext.current && messages.length) { scrollNext.current = false; lastRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }); }
  }, [messages.length]);

  const ask = async (raw) => {
    const t = (raw ?? draft).trim();
    if (t.length < 3 || pending) { if (t.length < 3) setErr("Type your question first."); return; }
    setErr(""); setPending(t); setDraft("");
    try {
      const { data } = await api.post("/akshat-ai/ask", { question: t, thread_id: id || null });
      scrollNext.current = true;
      if (id && data.thread_id === id) {
        qc.setQueryData(["akshat-thread", id], (old) => (old ? { ...old, messages: [...old.messages, data.user_message, data.message] } : old));
      } else {
        qc.setQueryData(["akshat-thread", data.thread_id], { id: data.thread_id, title: t, messages: [data.user_message, data.message] });
        nav(`/app/akshat-ai/${data.thread_id}`);
      }
      qc.invalidateQueries({ queryKey: ["akshat-threads"] });
      if (data.status === "queued") qc.invalidateQueries({ queryKey: ["akshat-questions"] });
      refreshMe();
    } catch (e) {
      setDraft(t);
      if (![402, 403].includes(e?.response?.status)) setErr(apiError(e));
    } finally { setPending(null); }
  };

  const list = threads.data?.items || [];
  const listEl = <Threads items={list} current={id} onPick={(t) => { setDrawer(false); nav(`/app/akshat-ai/${t}`); }} onNew={() => { setDrawer(false); nav("/app/akshat-ai"); }} />;
  const lastAnswer = messages.length - 1;

  return (
    <div className="lg:grid lg:grid-cols-[230px_minmax(0,1fr)] lg:gap-7">
      <aside className="hidden lg:block">
        <div className="sticky top-6 max-h-[calc(100vh-48px)] overflow-y-auto pr-1">
          <p className="text-[12px] font-semibold text-bz-muted mb-2">Your questions</p>
          {threads.isLoading ? <Skeleton lines={4} /> : listEl}
        </div>
      </aside>
      <div className="min-w-0 space-y-4">
        <div className="flex gap-2 lg:hidden">
          <Button variant="small" className="flex-1" onClick={() => setDrawer(true)}>
            <MessageSquare className="w-4 h-4" aria-hidden /> Your questions{list.length ? ` (${list.length})` : ""}
          </Button>
          {id && <Button variant="small" onClick={() => nav("/app/akshat-ai")}><Plus className="w-4 h-4" aria-hidden /> New</Button>}
        </div>
        <Sheet open={drawer} onClose={() => setDrawer(false)} title="Your questions">{listEl}</Sheet>

        {!id && !pending && (
          <Card data-testid="akshat-intro">
            <Label>Try asking</Label>
            <div className="flex flex-col gap-2">
              {EXAMPLES.map((x) => (
                <button key={x} type="button" onClick={() => ask(x)} className="text-left rounded-bzbtn border border-bz-line bg-bz-panel px-3.5 py-3 min-h-[48px] text-[15px] hover:border-bz-teal">{x}</button>
              ))}
            </div>
          </Card>
        )}
        {id && thread.isLoading && <Card><Skeleton lines={5} /></Card>}
        {id && thread.isError && <ErrorCard error={thread.error} what="this chat" onRetry={() => thread.refetch()} />}

        <div className="space-y-4" data-testid="akshat-messages">
          {messages.map((m, i) => <Answer key={i} m={m} innerRef={i === lastAnswer ? lastRef : null} />)}
          {pending && (
            <>
              <Answer m={{ role: "user", text: pending }} />
              <AiFrame title="Akshat AI"><Thinking label="Looking through Akshat's sessions" /></AiFrame>
            </>
          )}
        </div>

        <ErrorLine>{err}</ErrorLine>
        <div className="rounded-bzcard border border-bz-line bg-bz-card p-3">
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} maxLength={1000} aria-label="Your question"
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); ask(); } }}
            placeholder={id ? "Ask a follow-up question" : "Ask Akshat anything about consulting"} className="min-h-[60px]" data-testid="akshat-input" />
          <div className="flex items-center justify-between gap-3 mt-2">
            <UsageLine usage={plan?.limits?.akshat_ai} what="questions" />
            <Button variant="ai" className="ml-auto" onClick={() => ask()} loading={!!pending} disabled={draft.trim().length < 3} data-testid="akshat-send">
              Ask Akshat AI
            </Button>
          </div>
        </div>
        <Note>Answers come only from Akshat's recorded sessions and workbooks. Not for personal financial, tax or legal advice.</Note>
        <Queue />
      </div>
    </div>
  );
}

export default function AkshatAI() {
  const header = (
    <PageHeader kicker="Akshat AI" ai title="Ask Akshat," accent="any time."
      sub="Answers come from Akshat's own sessions, with the session names underneath. If the sessions don't cover your question, it goes to the next group call." />
  );
  return (
    <Gate feature="akshat_ai" header={header}>
      {header}
      <Ask />
    </Gate>
  );
}
