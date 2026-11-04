// /app/hub (program "action", L1 Action Hub tools) and /app/mentorship (program "mentorship", L2 tools):
// gallery of Akshat's tools with search. A card's starter button starts a conversation and opens it in /app/gpt/:slug;
// "Continue" reopens the latest one. Presentation Builder and the website builders open the app's own screens.
import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago } from "@/lib/format";
import { Gate, UsageLine } from "../components/common";
import { Button, Card, Chip, Empty, ErrorLine, Input, LinkButton, Loadable, PageHeader, Thinking } from "../components/ui";

const COPY = {
  action: {
    feature: "action_tools", kicker: "Action Hub", title: "Akshat's 4-3-2-1 tools,", accent: "ready when you are.",
    sub: "Each tool is one of Akshat's frameworks as a guided chat. Start with Define Your Niche: the LinkedIn Blueprint, Strategy Thinking and others build on it.",
  },
  mentorship: {
    feature: "mentorship_tools", kicker: "Mentorship tools", title: "Build your practice,", accent: "one tool at a time.",
    sub: "Book Builder, Credibility Code, Document Builder, pricing, proposals and more. Each one is a guided chat that knows your niche.",
  },
};

const NATIVE = { "/app/decks": "Presentation Builder", "/app/website": "Website Builder" };

function ToolCard({ g, busy, anyBusy, onStart }) {
  return (
    <Card className="flex flex-col" data-testid={`gpt-card-${g.slug}`}>
      <p className="text-[17px] font-extrabold leading-snug">{g.name}</p>
      <p className="text-[14px] text-bz-muted mt-1.5 leading-relaxed flex-1">{g.description}</p>
      {g.redirect ? (
        <div className="mt-4 space-y-2">
          <Chip tone="muted">Opens the app's {NATIVE[g.redirect] || "own screen"}</Chip>
          <LinkButton to={g.redirect} variant="secondary" className="w-full" data-testid={`gpt-open-${g.slug}`}>Open {NATIVE[g.redirect] || g.name}</LinkButton>
        </div>
      ) : busy ? (
        <Thinking label={`Starting ${g.name}`} />
      ) : (
        <div className="mt-4 flex flex-col sm:flex-row gap-2">
          <Button variant="ai" className="flex-1" disabled={anyBusy} onClick={() => onStart(g)} data-testid={`gpt-start-${g.slug}`}>{g.starter}</Button>
          {g.last_id && (
            <LinkButton to={`/app/gpt/${g.slug}?c=${g.last_id}`} variant="secondary" className="flex-1" data-testid={`gpt-continue-${g.slug}`}>Continue</LinkButton>
          )}
        </div>
      )}
      {!g.redirect && g.last_used && <p className="text-[12px] text-bz-muted mt-2">Last used {ago(g.last_used)} · <Link to={`/app/gpt/${g.slug}`} className="text-bz-gold font-bold">All chats</Link></p>}
    </Card>
  );
}

export default function Gpts({ program = "action" }) {
  const c = COPY[program] || COPY.action;
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const [find, setFind] = useState("");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const q = useQuery({ queryKey: ["gpts", program], queryFn: async () => (await api.get("/gpts", { params: { program } })).data });

  const start = async (g) => {
    setErr(""); setBusy(g.slug);
    try {
      const { data } = await api.post(`/gpts/${g.slug}/conversations`, {});
      if (data.redirect) { nav(data.redirect); return; }
      qc.setQueryData(["gpt-conv", data.id], data);
      qc.invalidateQueries({ queryKey: ["gpts"] }); qc.invalidateQueries({ queryKey: ["gpt-convs", g.slug] });
      refreshMe();
      nav(`/app/gpt/${g.slug}?c=${data.id}`);
    } catch (e) {
      if (![402, 403].includes(e?.response?.status)) setErr(apiError(e));
    } finally { setBusy(null); }
  };

  const header = <PageHeader kicker={c.kicker} ai title={c.title} accent={c.accent} sub={c.sub} />;
  return (
    <Gate feature={c.feature} header={header}>
      <div className="space-y-5">
        {header}
        <div className="relative">
          <Search className="w-4 h-4 text-bz-muted absolute left-3.5 top-1/2 -translate-y-1/2" aria-hidden />
          <Input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find a tool, e.g. pricing, LinkedIn, pitch"
            className="pl-10" aria-label="Find a tool" data-testid="gpt-search" />
        </div>
        <ErrorLine>{err}</ErrorLine>
        <Loadable q={q} what="the tools" lines={6}>
          {(d) => <Gallery items={d.items || []} find={find} busy={busy} onStart={start} />}
        </Loadable>
        <UsageLine usage={plan?.limits?.gpt} what="messages to the tools" className="text-center" />
      </div>
    </Gate>
  );
}

function Gallery({ items, find, busy, onStart }) {
  const shown = useMemo(() => {
    const s = find.trim().toLowerCase();
    if (!s) return items;
    return items.filter((g) => `${g.name} ${g.description}`.toLowerCase().includes(s));
  }, [items, find]);
  if (!shown.length) return <Empty title="No tool matches that" sub="Try a shorter word, like 'price' or 'client'." />;
  return (
    <div className="grid gap-4 sm:grid-cols-2" data-testid="gpt-gallery">
      {shown.map((g) => <ToolCard key={g.slug} g={g} busy={busy === g.slug} anyBusy={!!busy} onStart={onStart} />)}
    </div>
  );
}
