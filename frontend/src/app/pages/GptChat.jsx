// /app/gpt/:id — one of Akshat's tools (id = slug) as a chat. ?c=<conversation id> opens a conversation.
// Conversations sit in a side column on a computer and in a drawer on a phone. Replies are Markdown (copy cards,
// "Your turn" cards, Strategy Thinking practice cards and quick-reply buttons). Each reply can be copied or printed.
import { useEffect, useRef, useState } from "react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowRight, MessageSquare, Plus, Printer, Trash2 } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import Markdown, { CopyButton } from "../components/Markdown";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, ErrorCard, ErrorLine, Loadable, Note, PageHeader, Sheet, Skeleton, Textarea, Thinking } from "../components/ui";

const STRATEGY = "strategy-thinking-framework";
const BACK = { action: ["/app/hub", "Action Hub"], mentorship: ["/app/mentorship", "Mentorship tools"] };

// Strategy Thinking: the moments where the current hub shows a quick-reply button without a ```next block.
function quickReplies(slug, text) {
  if (slug !== STRATEGY || !text || text.includes("```next")) return [];
  if (/Practice complete/i.test(text)) return ["Bring me a different client"];
  if (/Same six steps\. Every problem\. Every time\./i.test(text)) return ["PRACTICE THE CLIENT CONVERSATION", "Bring me a different client"];
  if (/LET['’]S SOLVE/.test(text) && !/Phase 1/.test(text)) return ["LET'S SOLVE"];
  return [];
}

function ConvList({ items, current, onPick, onNew, onDelete }) {
  return (
    <div className="space-y-2">
      <Button variant="small" className="w-full" onClick={onNew} data-testid="gpt-new"><Plus className="w-4 h-4" aria-hidden /> New chat</Button>
      {items.length ? (
        <ul className="space-y-1" data-testid="gpt-conv-list">
          {items.map((c) => (
            <li key={c.id} className={`flex items-center rounded-bzbtn ${c.id === current ? "bg-bz-raised" : "hover:bg-bz-raised"}`}>
              <button type="button" onClick={() => onPick(c.id)} className="flex-1 min-w-0 text-left px-3 py-2.5 min-h-[48px]" data-testid={`gpt-conv-${c.id}`}>
                <span className={`block text-[14px] font-bold truncate ${c.id === current ? "text-bz-gold" : ""}`}>{c.title}</span>
                <span className="block text-[12px] text-bz-muted">{ago(c.updated_at)}</span>
              </button>
              <button type="button" onClick={() => onDelete(c)} aria-label="Delete this chat" className="w-10 h-10 grid place-items-center text-bz-muted hover:text-bz-miss shrink-0">
                <Trash2 className="w-4 h-4" aria-hidden />
              </button>
            </li>
          ))}
        </ul>
      ) : <p className="text-[13px] text-bz-muted px-1">No chats yet.</p>}
    </div>
  );
}

function UserBubble({ text, hide }) {
  const [open, setOpen] = useState(false);
  const long = text.length > 600;
  return (
    <div className={`flex justify-end ${hide ? "no-print" : ""}`}>
      <div className="max-w-[88%] rounded-bzcard rounded-br-md bg-bz-raised border border-bz-line px-4 py-3">
        <p className="whitespace-pre-line text-[15px] leading-relaxed">{long && !open ? `${text.slice(0, 280).trim()}…` : text}</p>
        {long && <button type="button" onClick={() => setOpen(!open)} className="no-print text-[12px] font-bold text-bz-gold mt-1 min-h-[32px]">{open ? "Show less" : "Show all"}</button>}
      </div>
    </div>
  );
}

function QuickReply({ text, onSend, busy, i }) {
  return (
    <button type="button" disabled={busy} onClick={() => onSend(text)} data-testid={`gpt-quick-${i}`}
      className="no-print inline-flex items-center gap-2 min-h-[48px] px-5 rounded-full border border-bz-teal text-bz-teal font-bold text-[15px] hover:bg-bz-teal-tint disabled:opacity-50">
      {text}<ArrowRight className="w-4 h-4" aria-hidden />
    </button>
  );
}

function Chat({ g }) {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const [sp, setSp] = useSearchParams();
  const cid = sp.get("c");
  const [draft, setDraft] = useState("");
  const [pending, setPending] = useState(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [printIdx, setPrintIdx] = useState(null);
  const lastRef = useRef(null);
  const thinkRef = useRef(null);
  const scrollNext = useRef(false);

  const convs = useQuery({ queryKey: ["gpt-convs", g.slug], queryFn: async () => (await api.get(`/gpts/${g.slug}/conversations`)).data });
  const conv = useQuery({ queryKey: ["gpt-conv", cid], queryFn: async () => (await api.get(`/gpts/conversations/${cid}`)).data, enabled: !!cid });
  const messages = (cid && conv.data?.messages) || [];
  const lastIdx = messages.length - 1;
  const printing = printIdx !== null;

  useEffect(() => {
    const after = () => setPrintIdx(null);
    window.addEventListener("afterprint", after);
    return () => window.removeEventListener("afterprint", after);
  }, []);
  useEffect(() => {
    if (scrollNext.current && messages.length) {
      scrollNext.current = false;
      lastRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [messages.length]);
  useEffect(() => { if (pending) thinkRef.current?.scrollIntoView({ behavior: "smooth", block: "center" }); }, [pending]);

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["gpt-convs", g.slug] });
    qc.invalidateQueries({ queryKey: ["gpts"] });
    refreshMe();
  };

  const fail = (e) => { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); };

  const start = async (typed) => {
    if (busy) return;
    setErr(""); setBusy(true);
    setPending(typed || (g.uses_blueprint && g.has_blueprint ? "Here is my finalized Niche Blueprint from Define Your Niche." : g.starter));
    try {
      const { data } = await api.post(`/gpts/${g.slug}/conversations`, typed ? { text: typed } : {});
      qc.setQueryData(["gpt-conv", data.id], data);
      scrollNext.current = true;
      setSp({ c: data.id });
      refresh();
      return true;
    } catch (e) { fail(e); return false; } finally { setBusy(false); setPending(null); }
  };

  const send = async (raw) => {
    const fromBox = raw == null;
    const t = (fromBox ? draft : raw).trim();
    if (!t || busy) return;
    if (fromBox) setDraft("");
    if (!cid) { const ok = await start(t); if (!ok && fromBox) setDraft(t); return; }
    setErr(""); setBusy(true); setPending(t);
    try {
      const { data } = await api.post(`/gpts/conversations/${cid}/messages`, { text: t });
      scrollNext.current = true;
      qc.setQueryData(["gpt-conv", cid], (old) => (old ? { ...old, title: data.title, updated_at: data.updated_at,
        messages: [...old.messages, data.user_message, data.message] } : old));
      refresh();
    } catch (e) { if (fromBox) setDraft(t); fail(e); } finally { setBusy(false); setPending(null); }
  };

  const pick = (id) => { setDrawer(false); setErr(""); setSp({ c: id }); };
  const fresh = () => { setDrawer(false); setErr(""); setSp({}); };
  const remove = async (c) => {
    if (!window.confirm(`Delete "${c.title}"? You won't see this chat again.`)) return;
    try {
      await api.delete(`/gpts/conversations/${c.id}`);
      qc.invalidateQueries({ queryKey: ["gpt-convs", g.slug] }); qc.invalidateQueries({ queryKey: ["gpts"] });
      if (c.id === cid) fresh();
    } catch (e) { window.alert(apiError(e)); }
  };
  const printOne = (i) => { setPrintIdx(i); setTimeout(() => window.print(), 80); };

  const list = convs.data?.items || [];
  const listEl = <ConvList items={list} current={cid} onPick={pick} onNew={fresh} onDelete={remove} />;
  const quick = !busy && lastIdx >= 0 && messages[lastIdx].role === "assistant" ? quickReplies(g.slug, messages[lastIdx].text) : [];

  return (
    <div className="lg:grid lg:grid-cols-[230px_minmax(0,1fr)] lg:gap-7">
      <aside className="no-print hidden lg:block">
        <div className="sticky top-6 max-h-[calc(100vh-48px)] overflow-y-auto pr-1">
          <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-muted mb-2">Your chats</p>
          {convs.isLoading ? <Skeleton lines={4} /> : listEl}
        </div>
      </aside>

      <div className="min-w-0 space-y-4">
        <div className="no-print flex gap-2 lg:hidden">
          <Button variant="small" className="flex-1" onClick={() => setDrawer(true)} data-testid="gpt-chats">
            <MessageSquare className="w-4 h-4" aria-hidden /> Your chats{list.length ? ` (${list.length})` : ""}
          </Button>
          {cid && <Button variant="small" onClick={fresh}><Plus className="w-4 h-4" aria-hidden /> New chat</Button>}
        </div>
        <Sheet open={drawer} onClose={() => setDrawer(false)} title="Your chats">{listEl}</Sheet>

        {!cid && !pending && (
          <Card className="no-print" data-testid="gpt-intro">
            <p className="text-[15px] leading-relaxed">{g.description}</p>
            {g.uses_blueprint && (
              <Note className="mt-2">{g.has_blueprint
                ? "This tool starts from your Niche Blueprint (your chosen niche in Starting Point), so you don't need to paste it."
                : "Tip: choose your niche in Starting Point first. Then this tool starts from it and you don't need to paste anything."}</Note>
            )}
            <Button variant="ai" className="w-full sm:w-auto mt-4" onClick={() => start()} disabled={busy} data-testid="gpt-starter">{g.starter}</Button>
            <Note className="mt-3">Or type your own first message below.</Note>
          </Card>
        )}

        {cid && conv.isLoading && <Card><Skeleton lines={6} /></Card>}
        {cid && conv.isError && (
          <div className="space-y-3">
            <ErrorCard error={conv.error} what="this chat" onRetry={() => conv.refetch()} />
            <Button variant="secondary" onClick={fresh}>Start a new chat</Button>
          </div>
        )}
        {cid && conv.data && (
          <p className={`text-[13px] text-bz-muted ${printing ? "no-print" : ""}`}>{conv.data.title} · started {hdate(conv.data.created_at)}</p>
        )}

        <div className="space-y-4" data-testid="gpt-messages">
          {messages.map((m, i) => (m.role === "user" ? (
            <UserBubble key={i} text={m.text} hide={printing} />
          ) : (
            <div key={i} ref={i === lastIdx ? lastRef : null} className={`scroll-mt-20 ${printing && printIdx !== i ? "no-print" : ""}`}>
              <AiFrame title={g.name} className={printIdx === i ? "print-plain" : ""}>
                <div data-testid={i === lastIdx ? "gpt-reply" : undefined}>
                  <Markdown text={m.text} onNext={i === lastIdx ? send : null} busy={busy} />
                </div>
                <div className="no-print flex flex-wrap items-center gap-1 mt-3 pt-2 border-t border-bz-line">
                  <CopyButton text={m.text} label="Copy reply" />
                  <button type="button" onClick={() => printOne(i)} data-testid={i === lastIdx ? "gpt-print" : undefined}
                    className="inline-flex items-center gap-1 text-[12px] font-bold text-bz-gold min-h-[36px] px-2">
                    <Printer className="w-3.5 h-3.5" aria-hidden /> Print or save as PDF
                  </button>
                </div>
              </AiFrame>
            </div>
          )))}
          {pending && (
            <>
              <UserBubble text={pending} />
              <div ref={thinkRef}><AiFrame title={g.name}><Thinking label={`${g.name} is thinking`} /></AiFrame></div>
            </>
          )}
          {quick.length > 0 && <div className="flex flex-wrap gap-2">{quick.map((t, i) => <QuickReply key={t} text={t} i={i} busy={busy} onSend={send} />)}</div>}
        </div>

        <ErrorLine>{err}</ErrorLine>
        <div className="no-print rounded-bzcard border border-bz-line bg-bz-card p-3">
          <Textarea value={draft} onChange={(e) => setDraft(e.target.value)} rows={2} maxLength={12000}
            onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); send(); } }}
            placeholder={cid ? "Type your reply" : "Type your first message"} aria-label="Your message"
            className="min-h-[60px] max-h-[40vh]" data-testid="gpt-input" />
          <div className="flex items-center justify-between gap-3 mt-2">
            <span className="text-[12px] text-bz-muted hidden sm:inline">Enter sends · Shift+Enter for a new line</span>
            <Button variant="ai" className="ml-auto" onClick={() => send()} loading={busy} disabled={!draft.trim()} data-testid="gpt-send">Send</Button>
          </div>
        </div>
        <UsageLine usage={plan?.limits?.gpt} what="messages to the tools" className="no-print text-center" />
      </div>
    </div>
  );
}

export default function GptChat() {
  const { id: slug } = useParams();
  const tool = useQuery({ queryKey: ["gpt", slug], queryFn: async () => (await api.get(`/gpts/${slug}`)).data, enabled: !!slug });
  if (!slug) return <Navigate to="/app/hub" replace />;
  return (
    <Loadable q={tool} what="this tool" lines={5}>
      {(g) => {
        if (g.redirect) return <Navigate to={g.redirect} replace />;
        const [back, backLabel] = BACK[g.program] || BACK.action;
        const header = (
          <div className="no-print">
            <BackLink to={back}>{backLabel}</BackLink>
            <PageHeader kicker={backLabel} ai title={g.name} />
          </div>
        );
        return (
          <Gate feature={g.feature} header={header}>
            {header}
            <Chat key={g.slug} g={g} />
          </Gate>
        );
      }}
    </Loadable>
  );
}
