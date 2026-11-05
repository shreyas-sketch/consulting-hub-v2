// /app/website — Website Builder: pick a look, the AI writes the whole consulting site from what the hub knows
// (niche, Offer Card, career stories), then edit each section by prompt or by hand, reorder or hide sections,
// add a logo and photo, contact details, an own domain (L1/L2), publish, and read the messages visitors send.
// The live preview is the real page (/s/<slug>?preview=1) in an iframe, at phone or desktop width.
import { useEffect, useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowDown, ArrowUp, Check, Copy, ExternalLink, Eye, EyeOff, Globe, ImagePlus, Inbox, Lock, Mail, Pencil, Phone,
  Plus, Trash2, Undo2,
} from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { Gate, UsageLine } from "../components/common";
import {
  AiFrame, Button, Card, Chip, ErrorLine, Field, Input, Label, LinkButton, Loadable, Note, OkLine, PageHeader, Segmented,
  Select, Sheet, Step, Textarea, Thinking,
} from "../components/ui";

const BACKEND = process.env.REACT_APP_BACKEND_URL || "";

// The fields of each section, for the edit-by-hand sheet and the before / after view.
// [key, label, long?]
const SPEC = {
  hero: { fields: [["kicker", "Small line above the headline"], ["headline", "Headline"], ["sub", "Line under the headline", true], ["cta", "Button text"]] },
  problems: { fields: [["title", "Heading"], ["intro", "Intro", true]], list: { key: "items", label: "Problems", item: [["title", "Problem"], ["text", "One line about it", true]], max: 6 } },
  method: { fields: [["title", "Heading"], ["intro", "Intro", true]], list: { key: "steps", label: "Steps", item: [["title", "Step"], ["text", "What happens", true]], max: 8 } },
  services: { fields: [["title", "Heading"], ["intro", "Intro", true]], list: { key: "items", label: "Services", item: [["name", "Service name"], ["text", "What the client gets", true], ["fee", "Fee (optional), e.g. From ₹50,000"]], max: 6 } },
  about: { fields: [["title", "Heading"], ["text", "About you. Leave an empty line between paragraphs.", true]], strings: { key: "points", label: "Credibility points", max: 6 } },
  proof: { fields: [["title", "Heading"], ["intro", "Intro", true]], list: { key: "items", label: "Case studies", item: [["title", "The client and your role"], ["situation", "The situation", true], ["action", "What you did", true], ["result", "The result, with a real number", true]], max: 6 } },
  faq: { fields: [["title", "Heading"]], list: { key: "items", label: "Questions", item: [["q", "Question"], ["a", "Answer", true]], max: 10 } },
  contact: { fields: [["title", "Heading"], ["text", "A line inviting people to get in touch", true], ["cta", "Button text"]] },
};

const QUICK = ["Make it shorter", "Use simpler words", "Make it warmer", "Make it more specific to my clients"];

// One place for every editor call: the answer is the whole new state, written straight into the query cache.
function useSiteCall() {
  const qc = useQueryClient();
  const { refreshMe } = useAuth();
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const call = async (key, fn, { metered = false } = {}) => {
    setBusy(key); setErr("");
    try {
      const { data } = await fn();
      if (data && data.site !== undefined) qc.setQueryData(["website"], data);
      return data || {};
    } catch (e) {
      if (![402, 403].includes(e?.response?.status)) setErr(apiError(e));
      return null;
    } finally {
      setBusy("");
      if (metered) refreshMe();
    }
  };
  return { busy, err, setErr, call };
}

function Header({ ai = false }) {
  return (
    <PageHeader kicker="Website Builder" ai={ai} title="Your consulting site," accent="live on its own link."
      sub="The AI writes every section from your niche, your offer and your career stories. You check it, change what you like and publish." />
  );
}

export default function Website() {
  return (
    <Gate feature="website" header={<Header />}>
      <Builder />
    </Gate>
  );
}

function Builder() {
  const q = useQuery({ queryKey: ["website"], queryFn: async () => (await api.get("/website")).data });
  return (
    <Loadable q={q} what="your website" lines={6}>
      {(d) => (d.site ? <Editor d={d} /> : <StartScreen d={d} />)}
    </Loadable>
  );
}

// ───────────────────────── looks ─────────────────────────
function LookPicker({ looks, value, onPick, suggested, disabled }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2" role="radiogroup" aria-label="Look">
      {looks.map((lk) => {
        const on = value === lk.key;
        return (
          <button key={lk.key} type="button" role="radio" aria-checked={on} disabled={disabled}
            onClick={() => onPick(lk)} data-testid={`site-look-${lk.key}`}
            className={`text-left rounded-bzcard border p-3.5 min-h-[88px] flex gap-3 items-start transition-colors disabled:opacity-60 ${on ? "border-bz-gold bg-bz-gold-tint" : "border-bz-line bg-bz-panel hover:border-bz-line-strong"}`}>
            <span className="flex shrink-0 rounded-md overflow-hidden border border-bz-line" aria-hidden>
              {lk.colors.map((c) => <span key={c} className="w-4 h-11" style={{ background: c }} />)}
            </span>
            <span className="min-w-0 flex-1">
              <span className="flex items-center gap-2 flex-wrap">
                <span className="font-extrabold text-[15px]">{lk.name}</span>
                {lk.key === suggested && <Chip tone="gold">Suggested</Chip>}
                {lk.locked && <Chip tone="muted"><Lock className="w-3 h-3" aria-hidden />L2</Chip>}
              </span>
              <span className="block text-[13px] text-bz-muted mt-0.5 leading-snug">{lk.about}</span>
            </span>
          </button>
        );
      })}
    </div>
  );
}

// ───────────────────────── first screen ─────────────────────────
function StartScreen({ d }) {
  const { plan } = useAuth();
  const [look, setLook] = useState(d.suggested_look || "boardroom");
  const [about, setAbout] = useState("");
  const { busy, err, call } = useSiteCall();
  const k = d.known || {};
  const usage = plan?.limits?.site_ai;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const thin = !k.title && !k.niche;
  const build = () => call("build", () => api.post("/website/build", { look, about_me: about.trim() }), { metered: true });
  const pick = (lk) => { if (!lk.locked) setLook(lk.key); };

  return (
    <div className="space-y-5">
      <Header ai />
      {busy === "build" ? (
        <AiFrame title="Website Builder"><Thinking label="Writing your site. This takes about a minute." /></AiFrame>
      ) : (
        <>
          <Card>
            <Label>What the AI writes from</Label>
            <ul className="space-y-2 text-[15px]">
              <li><span className="text-bz-muted">Your title: </span>{k.title || "not set yet"}</li>
              <li><span className="text-bz-muted">Your niche: </span>{k.niche || "not set yet"}</li>
              <li><span className="text-bz-muted">Who you help: </span>{k.audience || "not set yet"}</li>
              <li><span className="text-bz-muted">Offer Card: </span>{k.offer ? "yes, its name and fee go on your Services" : "none yet"}</li>
              <li><span className="text-bz-muted">Career stories: </span>{k.stories ? `${k.stories}, they become your case studies` : "none yet"}</li>
            </ul>
            {thin && <Note className="mt-3">Your Starting Point isn't done yet. Do it first for a sharper site, or tell the AI about yourself below.</Note>}
            <Note className="mt-3">The AI never makes up clients or numbers. Where it needs one, it leaves a marked spot for you to fill in.</Note>
          </Card>
          <Card>
            <Label>Pick a look</Label>
            <LookPicker looks={d.looks} value={look} onPick={pick} suggested={d.suggested_look} />
            <p className="text-[13px] text-bz-muted mt-3">You can change the look any time. It doesn't change your words.</p>
          </Card>
          <Card>
            <Field label="Anything the site should say about you (optional)" hint="Your years in the industry, companies, results you are proud of. Only what is true.">
              <Textarea value={about} onChange={(e) => setAbout(e.target.value)} maxLength={800} rows={4}
                placeholder="e.g. 22 years in FMCG supply chain at two large companies. Cut stock-outs across 400 distributors." data-testid="site-about-me" />
            </Field>
            <ErrorLine>{err}</ErrorLine>
            <Button variant="ai" className="w-full mt-4" onClick={build} disabled={!canRun} data-testid="site-build">Build my site</Button>
            <UsageLine usage={usage} what="website AI edits" className="text-center mt-2" />
          </Card>
        </>
      )}
    </div>
  );
}

// ───────────────────────── editor ─────────────────────────
function Editor({ d }) {
  const site = d.site;
  const [pageKey, setPageKey] = useState("home");
  const page = site.pages.find((p) => p.key === pageKey) || site.pages[0];
  const src = `${BACKEND}${site.preview_path}&v=${encodeURIComponent(site.updated_at || "")}`;

  const goTo = (p, sid) => {
    setPageKey(p);
    setTimeout(() => document.getElementById(`sec-${sid}`)?.scrollIntoView({ behavior: "smooth", block: "center" }), 60);
  };

  return (
    <div className="space-y-5">
      <Header />
      <StatusCard d={d} onJump={goTo} />
      <div className="grid gap-5 grid-cols-[minmax(0,1fr)] lg:grid-cols-[minmax(0,1fr)_400px] items-start">
        <div className="space-y-4 min-w-0">
          <PagesBar d={d} page={page} onPick={setPageKey} />
          <SectionList d={d} page={page} />
        </div>
        <div className="lg:sticky lg:top-4 space-y-3" id="site-preview">
          <PreviewFrame src={src} />
          <a href={`${BACKEND}${site.preview_path}`} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 text-[13px] font-bold text-bz-gold min-h-[44px]">
            Open the preview in a new tab <ExternalLink className="w-3.5 h-3.5" aria-hidden />
          </a>
        </div>
      </div>
      <div className="grid gap-5 grid-cols-[minmax(0,1fr)] lg:grid-cols-2 items-start">
        <AddressCard d={d} />
        <ContactCard d={d} />
        <ImagesCard d={d} />
        <LookCard d={d} />
        <DomainCard d={d} />
        <SeoCard d={d} />
      </div>
      <LeadsCard d={d} />
      <RebuildCard d={d} />
    </div>
  );
}

function Switch({ on, onChange, label, disabled, testid }) {
  return (
    <button type="button" role="switch" aria-checked={on} aria-label={label} disabled={disabled} onClick={() => onChange(!on)} data-testid={testid}
      className={`relative shrink-0 w-14 h-8 rounded-full border transition-colors disabled:opacity-60 ${on ? "bg-bz-gold border-bz-gold" : "bg-bz-inset border-bz-line-strong"}`}>
      <span className={`absolute top-[3px] left-[3px] w-6 h-6 rounded-full bg-white shadow transition-transform ${on ? "translate-x-6" : ""}`} />
    </button>
  );
}

function CopyLink({ text }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" aria-label="Copy the link" className="inline-flex items-center gap-1 text-[13px] font-bold text-bz-gold min-h-[44px] px-2"
      onClick={async () => { try { await navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); } catch { /* blocked */ } }}>
      {ok ? <Check className="w-3.5 h-3.5" aria-hidden /> : <Copy className="w-3.5 h-3.5" aria-hidden />}{ok ? "Copied" : "Copy"}
    </button>
  );
}

function StatusCard({ d, onJump }) {
  const site = d.site;
  const { busy, err, call } = useSiteCall();
  const toFill = site.placeholders.reduce((n, p) => n + p.count, 0);
  const publish = (on) => call("publish", () => api.post("/website/publish", { on }));
  const pageLabel = (k) => d.page_names.find((p) => p.key === k)?.label || k;
  return (
    <Card data-testid="site-status">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="text-[18px] font-extrabold">{site.published ? "Your site is live" : "Your site is a draft"}</p>
            <Chip tone={site.published ? "solid" : "muted"}>{site.published ? "Live" : "Draft"}</Chip>
          </div>
          {site.published ? (
            <div className="flex items-center gap-1 flex-wrap mt-1">
              <a href={site.url} target="_blank" rel="noopener noreferrer" className="text-[15px] font-bold text-bz-gold break-all inline-flex items-center gap-1.5 min-h-[44px]" data-testid="site-live-link">
                {site.url.replace(/^https?:\/\//, "")} <ExternalLink className="w-3.5 h-3.5 shrink-0" aria-hidden />
              </a>
              <CopyLink text={site.url} />
            </div>
          ) : (
            <p className="text-[14px] text-bz-muted mt-1">Only you can see it. Turn it on when you're happy with it.</p>
          )}
        </div>
        <div className="flex flex-col items-center gap-1">
          <Switch on={site.published} onChange={publish} label="Publish my site" disabled={busy === "publish"} testid="site-publish" />
          <span className="text-[12px] text-bz-muted">{site.published ? "Live" : "Off"}</span>
        </div>
      </div>
      <div className="flex gap-4 mt-3 text-[13px] text-bz-muted flex-wrap">
        <span><b className="text-bz-ink tabular">{site.views}</b> visits</span>
        <a href="#site-leads" className="hover:text-bz-ink"><b className="text-bz-gold tabular">{site.leads_unread}</b> new message{site.leads_unread === 1 ? "" : "s"}</a>
        {site.published_at && <span>Live since {hdate(site.published_at)}</span>}
      </div>
      {toFill > 0 && (
        <div className="mt-4 rounded-bzcard border border-bz-rule bg-bz-gold-tint p-3.5" data-testid="site-placeholders">
          <p className="text-[14px] font-bold">{toFill} spot{toFill === 1 ? "" : "s"} still need{toFill === 1 ? "s" : ""} your real details.</p>
          <p className="text-[13px] text-bz-muted mt-0.5">They show in yellow in the preview. Your live site leaves those lines out until you fill them.</p>
          <div className="flex flex-wrap gap-2 mt-2.5">
            {site.placeholders.map((p) => (
              <button key={p.section_id} type="button" onClick={() => onJump(p.page, p.section_id)}
                className="min-h-[40px] px-3 rounded-bzbtn border border-bz-line bg-bz-panel text-[13px] font-bold hover:border-bz-gold">
                {pageLabel(p.page)}: {d.section_types.find((t) => t.type === p.type)?.label} ({p.count})
              </button>
            ))}
          </div>
        </div>
      )}
      <ErrorLine>{err}</ErrorLine>
    </Card>
  );
}

function PagesBar({ d, page, onPick }) {
  const site = d.site;
  const { busy, err, call } = useSiteCall();
  const missing = d.page_names.filter((p) => !site.pages.some((x) => x.key === p.key));
  const [add, setAdd] = useState("");
  const addKey = add || missing[0]?.key || "";
  const addPage = async () => {
    const r = await call("add", () => api.post("/website/pages", { key: addKey }));
    if (r?.site) { onPick(addKey); setAdd(""); }
  };
  const removePage = async () => {
    if (!window.confirm(`Remove the ${page.label} page? Its sections go too.`)) return;
    const r = await call("remove", () => api.delete(`/website/pages/${page.key}`));
    if (r?.site) onPick("home");
  };
  return (
    <Card>
      <Label>Pages</Label>
      <Segmented options={site.pages.map((p) => ({ value: p.key, label: p.label }))} value={page.key} onChange={onPick} label="Pages" testid="site-page" />
      {site.pages.some((p) => !p.live) && <Note className="mt-2">Pages beyond your plan's {d.caps.pages} stay saved but don't show on your live site.</Note>}
      <div className="flex flex-wrap gap-2 mt-3 items-center">
        {missing.length > 0 && (
          <>
            {d.caps.pages > 1 && missing.length > 1 && (
              <Select value={addKey} onChange={(e) => setAdd(e.target.value)} className="!w-auto !min-h-[44px]" aria-label="Page to add">
                {missing.map((p) => <option key={p.key} value={p.key}>{p.label}</option>)}
              </Select>
            )}
            <Button variant="quiet" onClick={addPage} loading={busy === "add"} data-testid="site-add-page">
              <Plus className="w-4 h-4" aria-hidden />{d.caps.pages > 1 ? `Add ${missing.length === 1 ? `the ${missing[0].label} page` : "this page"}` : "Add a page"}
            </Button>
            {d.caps.pages <= 1 && <Chip tone="muted"><Lock className="w-3 h-3" aria-hidden />L1 gets 5 pages</Chip>}
          </>
        )}
        {page.key !== "home" && (
          <Button variant="danger" onClick={removePage} loading={busy === "remove"}>Remove this page</Button>
        )}
      </div>
      <ErrorLine>{err}</ErrorLine>
    </Card>
  );
}

function SectionList({ d, page }) {
  const site = d.site;
  const { busy, err, call } = useSiteCall();
  const [addType, setAddType] = useState("faq");
  const ids = page.sections.map((s) => s.id);
  const move = (i, dir) => {
    const next = [...ids];
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    call(`move-${ids[i]}`, () => api.put(`/website/pages/${page.key}/order`, { ids: next }));
  };
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <Label className="mb-0">Sections on {page.label}</Label>
        {site.can_undo && (
          <Button variant="small" onClick={() => call("undo", () => api.post("/website/undo"))} loading={busy === "undo"} data-testid="site-undo">
            <Undo2 className="w-4 h-4" aria-hidden />Undo last change
          </Button>
        )}
      </div>
      {page.sections.map((s, i) => (
        <SectionCard key={s.id} s={s} page={page.key} first={i === 0} last={i === page.sections.length - 1}
          proposal={site.proposal && site.proposal.section_id === s.id ? site.proposal : null}
          onMove={(dir) => move(i, dir)} moving={busy === `move-${s.id}`} />
      ))}
      {!page.sections.length && <Card inset><p className="text-[14px] text-bz-muted">No sections on this page yet. Add one below.</p></Card>}
      <Card inset>
        <div className="flex flex-wrap gap-2 items-end">
          <Field label="Add a section" className="flex-1 min-w-[180px]">
            <Select value={addType} onChange={(e) => setAddType(e.target.value)} data-testid="site-add-section-type">
              {d.section_types.map((t) => <option key={t.type} value={t.type}>{t.label}</option>)}
            </Select>
          </Field>
          <Button variant="quiet" className="min-h-[48px]" loading={busy === "addsec"} data-testid="site-add-section"
            onClick={() => call("addsec", () => api.post(`/website/pages/${page.key}/sections`, { type: addType }))}>
            <Plus className="w-4 h-4" aria-hidden />Add
          </Button>
        </div>
      </Card>
      <ErrorLine>{err}</ErrorLine>
    </div>
  );
}

function IconBtn({ label, onClick, disabled, children, testid }) {
  return (
    <button type="button" aria-label={label} title={label} onClick={onClick} disabled={disabled} data-testid={testid}
      className="w-11 h-11 grid place-items-center rounded-full border border-bz-line bg-bz-raised text-bz-ink hover:border-bz-line-strong disabled:opacity-40 disabled:cursor-not-allowed">
      {children}
    </button>
  );
}

function SectionCard({ s, page, first, last, proposal, onMove, moving }) {
  const { plan } = useAuth();
  const { busy, err, call } = useSiteCall();
  const [mode, setMode] = useState(null);       // null | "ai" | "hand"
  const [ask, setAsk] = useState("");
  const [note, setNote] = useState("");
  const usage = plan?.limits?.site_ai;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;

  const runAi = async () => {
    setNote("");
    const r = await call("ai", () => api.post(`/website/sections/${s.id}/ai`, { page, instruction: ask.trim() }), { metered: true });
    if (!r) return;
    if (r.changed === false) setNote(`${r.note} This didn't use up an AI edit.`);
    else { setAsk(""); setMode(null); }
  };
  const apply = () => call("apply", () => api.post("/website/proposal/apply"));
  const discard = () => call("discard", () => api.post("/website/proposal/discard"));
  const toggleHide = () => call("hide", () => api.put(`/website/sections/${s.id}`, { page, hidden: !s.hidden }));
  const remove = () => {
    if (!window.confirm(`Delete the ${s.label} section from this page?`)) return;
    call("del", () => api.delete(`/website/sections/${s.id}`, { params: { page } }));
  };

  return (
    <Card id={`sec-${s.id}`} className={s.hidden ? "opacity-70" : ""} data-testid={`site-section-${s.type}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <p className="font-extrabold text-[16px]">{s.label}</p>
            {s.hidden && <Chip>Hidden</Chip>}
            {s.placeholders > 0 && <Chip tone="gold">{s.placeholders} to fill</Chip>}
          </div>
          <p className="text-[14px] text-bz-muted mt-0.5 line-clamp-2">{s.summary}</p>
        </div>
      </div>
      <div className="flex flex-wrap gap-2 mt-3">
        <Button variant="ai" className="!min-h-[44px] !px-4 !text-[14px]" onClick={() => setMode(mode === "ai" ? null : "ai")} data-testid={`site-ai-open-${s.type}`}>Change with AI</Button>
        <Button variant="quiet" onClick={() => setMode("hand")} data-testid={`site-edit-${s.type}`}><Pencil className="w-4 h-4" aria-hidden />Edit by hand</Button>
        <IconBtn label="Move up" onClick={() => onMove(-1)} disabled={first || moving}><ArrowUp className="w-4 h-4" aria-hidden /></IconBtn>
        <IconBtn label="Move down" onClick={() => onMove(1)} disabled={last || moving}><ArrowDown className="w-4 h-4" aria-hidden /></IconBtn>
        <IconBtn label={s.hidden ? "Show on the site" : "Hide from the site"} onClick={toggleHide} disabled={busy === "hide"} testid={`site-hide-${s.type}`}>
          {s.hidden ? <Eye className="w-4 h-4" aria-hidden /> : <EyeOff className="w-4 h-4" aria-hidden />}
        </IconBtn>
        <IconBtn label="Delete this section" onClick={remove} disabled={busy === "del"}><Trash2 className="w-4 h-4 text-bz-miss" aria-hidden /></IconBtn>
      </div>

      {mode === "ai" && !proposal && (
        <div className="mt-4 rounded-bzcard border border-bz-line bg-bz-panel p-3.5">
          {busy === "ai" ? <Thinking label="Rewriting this section" /> : (
            <>
              <Field label="What should change?" hint="Only this section changes. Nothing goes on your site until you press Use this.">
                <Textarea value={ask} onChange={(e) => setAsk(e.target.value)} maxLength={500} rows={2} className="!min-h-[72px]"
                  placeholder="e.g. Make it shorter and talk about distributors" data-testid="site-ai-instruction" />
              </Field>
              <div className="flex flex-wrap gap-2 mt-2">
                {QUICK.map((qk) => (
                  <button key={qk} type="button" onClick={() => setAsk(qk)} className="min-h-[40px] px-3 rounded-bzbtn border border-bz-line text-[13px] font-bold text-bz-teal hover:border-bz-teal">{qk}</button>
                ))}
              </div>
              <Button variant="ai" className="w-full mt-3" onClick={runAi} disabled={ask.trim().length < 3 || !canRun} data-testid="site-ai-run">Show me the change</Button>
              <UsageLine usage={usage} what="website AI edits" className="text-center mt-2" />
            </>
          )}
          {note && <p className="text-[14px] mt-2" role="status">{note}</p>}
        </div>
      )}

      {proposal && (
        <AiFrame title="Suggested change" className="mt-4" right={<span className="text-[12px] text-bz-muted">{ago(proposal.at)}</span>}>
          <p className="text-[13px] text-bz-muted mb-3">You asked: “{proposal.instruction}”</p>
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-bzcard border border-bz-line bg-bz-panel p-3"><p className="text-[12px] font-bold text-bz-muted mb-2">Now</p><SectionText type={s.type} data={proposal.before} /></div>
            <div className="rounded-bzcard border border-bz-teal bg-bz-teal-tint p-3"><p className="text-[12px] font-bold text-bz-teal mb-2">After</p><SectionText type={s.type} data={proposal.after} /></div>
          </div>
          {proposal.note && <p className="text-[13px] text-bz-muted mt-3">{proposal.note}</p>}
          <div className="flex flex-wrap gap-2 mt-4">
            <Button variant="secondary" onClick={apply} loading={busy === "apply"} data-testid="site-ai-apply">Use this</Button>
            <Button variant="quiet" onClick={discard} loading={busy === "discard"} data-testid="site-ai-discard">Keep mine</Button>
          </div>
        </AiFrame>
      )}
      <ErrorLine>{err}</ErrorLine>
      {mode === "hand" && <HandEditor s={s} page={page} onClose={() => setMode(null)} />}
    </Card>
  );
}

function SectionText({ type, data }) {
  const spec = SPEC[type] || { fields: [] };
  return (
    <div className="space-y-2 text-[14px] leading-relaxed">
      {spec.fields.map(([k, label]) => data[k] ? (
        <div key={k}><p className="text-[11.5px] text-bz-muted">{label}</p><p className="whitespace-pre-line">{data[k]}</p></div>
      ) : null)}
      {spec.list && (data[spec.list.key] || []).length > 0 && (
        <ul className="list-disc pl-5 space-y-1">
          {data[spec.list.key].map((x, i) => <li key={i}>{spec.list.item.map(([f]) => x[f]).filter(Boolean).join(" · ")}</li>)}
        </ul>
      )}
      {spec.strings && (data[spec.strings.key] || []).length > 0 && (
        <ul className="list-disc pl-5 space-y-1">{data[spec.strings.key].map((x, i) => <li key={i}>{x}</li>)}</ul>
      )}
    </div>
  );
}

function HandEditor({ s, page, onClose }) {
  const spec = SPEC[s.type];
  const [f, setF] = useState(() => JSON.parse(JSON.stringify(s.data || {})));
  const { busy, err, call } = useSiteCall();
  const set = (k, v) => setF((x) => ({ ...x, [k]: v }));
  const list = spec.list;
  const rows = list ? f[list.key] || [] : [];
  const setRow = (i, k, v) => set(list.key, rows.map((r, j) => (j === i ? { ...r, [k]: v } : r)));
  const strs = spec.strings ? f[spec.strings.key] || [] : [];
  const save = async () => {
    const r = await call("save", () => api.put(`/website/sections/${s.id}`, { page, data: f }));
    if (r?.site) onClose();
  };
  return (
    <Sheet open onClose={onClose} title={`Edit: ${s.label}`} wide>
      <div className="space-y-4">
        <Note>Words in [square brackets] are spots for your real details. Replace them, or delete the line.</Note>
        {spec.fields.map(([k, label, long]) => (
          <Field key={k} label={label}>
            {long ? <Textarea value={f[k] || ""} onChange={(e) => set(k, e.target.value)} rows={k === "text" && s.type === "about" ? 8 : 3} />
              : <Input value={f[k] || ""} onChange={(e) => set(k, e.target.value)} data-testid={`site-field-${k}`} />}
          </Field>
        ))}
        {list && (
          <div className="space-y-3">
            <Label className="mb-0">{list.label}</Label>
            {rows.map((r, i) => (
              <div key={i} className="rounded-bzcard border border-bz-line bg-bz-panel p-3 space-y-2.5">
                {list.item.map(([k, label, long]) => (
                  <Field key={k} label={label}>
                    {long ? <Textarea value={r[k] || ""} onChange={(e) => setRow(i, k, e.target.value)} rows={2} className="!min-h-[72px]" />
                      : <Input value={r[k] || ""} onChange={(e) => setRow(i, k, e.target.value)} />}
                  </Field>
                ))}
                <Button variant="small" onClick={() => set(list.key, rows.filter((_, j) => j !== i))}>Remove</Button>
              </div>
            ))}
            {rows.length < list.max && (
              <Button variant="quiet" onClick={() => set(list.key, [...rows, Object.fromEntries(list.item.map(([k]) => [k, ""]))])}>
                <Plus className="w-4 h-4" aria-hidden />Add one
              </Button>
            )}
          </div>
        )}
        {spec.strings && (
          <div className="space-y-2">
            <Label className="mb-0">{spec.strings.label}</Label>
            {strs.map((x, i) => (
              <div key={i} className="flex gap-2">
                <Input value={x} onChange={(e) => set(spec.strings.key, strs.map((y, j) => (j === i ? e.target.value : y)))} aria-label={`Point ${i + 1}`} />
                <IconBtn label="Remove this point" onClick={() => set(spec.strings.key, strs.filter((_, j) => j !== i))}><Trash2 className="w-4 h-4" aria-hidden /></IconBtn>
              </div>
            ))}
            {strs.length < spec.strings.max && <Button variant="quiet" onClick={() => set(spec.strings.key, [...strs, ""])}><Plus className="w-4 h-4" aria-hidden />Add a point</Button>}
          </div>
        )}
        <ErrorLine>{err}</ErrorLine>
        <div className="flex flex-wrap gap-2 pt-1">
          <Button variant="secondary" onClick={save} loading={busy === "save"} data-testid="site-section-save">Save this section</Button>
          <Button variant="quiet" onClick={onClose}>Cancel</Button>
        </div>
      </div>
    </Sheet>
  );
}

function PreviewFrame({ src }) {
  const box = useRef(null);
  const [w, setW] = useState(360);
  const [mode, setMode] = useState("phone");
  useEffect(() => {
    const el = box.current;
    if (!el) return undefined;
    const fit = () => setW(el.clientWidth || 360);
    fit();
    if (typeof ResizeObserver === "undefined") return undefined;
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const base = mode === "phone" ? 390 : 1280;
  const h = mode === "phone" ? 780 : 860;
  const scale = Math.min(1, w / base);
  return (
    <Card>
      <div className="flex items-center justify-between gap-3 mb-3">
        <Label className="mb-0">Preview</Label>
        <Segmented options={[{ value: "phone", label: "Phone" }, { value: "desktop", label: "Desktop" }]} value={mode} onChange={setMode}
          label="Preview size" testid="site-preview-size" />
      </div>
      <div ref={box} className="w-full">
        <div className="mx-auto overflow-hidden rounded-bzcard border border-bz-line bg-bz-panel" style={{ width: base * scale, height: h * scale }}>
          <iframe title="Preview of your website" src={src} data-testid="site-preview"
            style={{ width: base, height: h, border: 0, transform: `scale(${scale})`, transformOrigin: "top left" }} />
        </div>
      </div>
    </Card>
  );
}

// ───────────────────────── settings cards ─────────────────────────
function AddressCard({ d }) {
  const site = d.site;
  const [slug, setSlug] = useState(site.slug);
  const [name, setName] = useState(site.profile.name || "");
  const [title, setTitle] = useState(site.profile.title || "");
  const [ok, setOk] = useState("");
  const { busy, err, call } = useSiteCall();
  const prefix = d.sites_domain ? null : `${site.hub_url.replace(/\/s\/[^/]+$/, "").replace(/^https?:\/\//, "")}/s/`;
  const save = async () => {
    setOk("");
    const r = await call("save", () => api.put("/website/settings", { slug: slug.trim().toLowerCase(), name: name.trim(), title: title.trim() }));
    if (r?.site) { setOk("Saved."); setSlug(r.site.slug); }
  };
  return (
    <Card>
      <Label>Address and name</Label>
      <div className="space-y-3">
        <Field label="Web address" hint={d.sites_domain ? `Your site: ${slug || "your-name"}.${d.sites_domain}` : "Small letters, numbers and dashes."}>
          <div className="flex items-center gap-2 min-w-0">
            {prefix && <span className="text-[14px] text-bz-muted shrink-0 max-w-[45%] truncate">{prefix}</span>}
            <Input value={slug} onChange={(e) => setSlug(e.target.value.toLowerCase().replace(/[^a-z0-9-]/g, ""))} maxLength={40} data-testid="site-slug" />
            {d.sites_domain && <span className="text-[14px] text-bz-muted shrink-0">.{d.sites_domain}</span>}
          </div>
        </Field>
        <Field label="Name on the site"><Input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} data-testid="site-name" /></Field>
        <Field label="Title under your name"><Input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={120} placeholder="e.g. Supply Chain Consultant for FMCG" /></Field>
      </div>
      <ErrorLine>{err}</ErrorLine><OkLine>{ok}</OkLine>
      <Button variant="secondary" className="mt-3" onClick={save} loading={busy === "save"} data-testid="site-slug-save">Save address and name</Button>
    </Card>
  );
}

function ContactCard({ d }) {
  const c = d.site.contact || {};
  const [f, setF] = useState({ email: c.email || "", whatsapp: c.whatsapp || "", calendly: c.calendly || "" });
  const [ok, setOk] = useState("");
  const { busy, err, call } = useSiteCall();
  const save = async () => {
    setOk("");
    const r = await call("save", () => api.put("/website/settings", { contact: f }));
    if (r?.site) setOk("Saved. Your site shows these now.");
  };
  return (
    <Card>
      <Label>Contact details</Label>
      <Note className="mb-3">These show on your site. Leave one empty to hide it. Messages from the form on your site always reach your Inbox.</Note>
      <div className="space-y-3">
        <Field label="Email"><Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} maxLength={160} autoComplete="email" data-testid="site-email" /></Field>
        <Field label="WhatsApp number"><Input type="tel" inputMode="tel" value={f.whatsapp} onChange={(e) => setF({ ...f, whatsapp: e.target.value })} maxLength={20} placeholder="98765 43210" data-testid="site-whatsapp" /></Field>
        <Field label="Booking link (optional)" hint="Your Calendly or other booking page. The main button on your site opens it.">
          <Input type="url" value={f.calendly} onChange={(e) => setF({ ...f, calendly: e.target.value })} maxLength={300} placeholder="https://calendly.com/your-name/intro" data-testid="site-calendly" />
        </Field>
      </div>
      <ErrorLine>{err}</ErrorLine><OkLine>{ok}</OkLine>
      <Button variant="secondary" className="mt-3" onClick={save} loading={busy === "save"} data-testid="site-contact-save">Save contact details</Button>
    </Card>
  );
}

const IMG_TYPES = ["image/png", "image/jpeg", "image/webp"];

function ImageSlot({ kind, label, hint, url }) {
  const input = useRef(null);
  const { busy, err, setErr, call } = useSiteCall();
  const pick = (file) => {
    if (!file) return;
    if (!IMG_TYPES.includes(file.type)) { setErr("Use a PNG, JPG or WebP image."); return; }
    if (file.size > 2 * 1024 * 1024) { setErr("Pick an image under 2 MB."); return; }
    const fd = new FormData();
    fd.append("file", file);
    call("up", () => api.post(`/website/images/${kind}`, fd));
  };
  return (
    <div className="flex gap-3 items-start">
      <div className="w-20 h-20 shrink-0 rounded-bzcard border border-bz-line bg-bz-panel overflow-hidden grid place-items-center">
        {url ? <img src={`${BACKEND}${url}`} alt={label} className="w-full h-full object-cover" /> : <ImagePlus className="w-6 h-6 text-bz-muted" aria-hidden />}
      </div>
      <div className="min-w-0 flex-1">
        <p className="font-bold text-[15px]">{label}</p>
        <p className="text-[13px] text-bz-muted">{hint}</p>
        <input ref={input} type="file" accept={IMG_TYPES.join(",")} className="hidden" tabIndex={-1}
          onChange={(e) => { pick(e.target.files?.[0]); e.target.value = ""; }} data-testid={`site-${kind}-input`} />
        <div className="flex flex-wrap gap-2 mt-2">
          <Button variant="quiet" onClick={() => input.current?.click()} loading={busy === "up"} data-testid={`site-${kind}-choose`}>{url ? "Change" : "Upload"}</Button>
          {url && <Button variant="small" className="!min-h-[44px]" onClick={() => call("rm", () => api.delete(`/website/images/${kind}`))} loading={busy === "rm"}>Remove</Button>}
        </div>
        <ErrorLine>{err}</ErrorLine>
      </div>
    </div>
  );
}

function ImagesCard({ d }) {
  return (
    <Card>
      <Label>Logo and photo</Label>
      <div className="space-y-4">
        <ImageSlot kind="logo" label="Logo" hint="Shows at the top of every page. Without one, your initials show." url={d.site.logo_url} />
        <ImageSlot kind="photo" label="Your photo" hint="A clear, recent photo of you. Shows at the top of Home." url={d.site.photo_url} />
      </div>
      <Note className="mt-3">PNG, JPG or WebP, up to 2 MB each.</Note>
    </Card>
  );
}

function LookCard({ d }) {
  const { busy, err, call } = useSiteCall();
  const pick = (lk) => {
    if (lk.key === d.site.look) return;
    call("look", () => api.put("/website/settings", { look: lk.key }));   // a locked look opens the upgrade sheet
  };
  return (
    <Card>
      <Label>Look</Label>
      <LookPicker looks={d.looks} value={d.site.look} onPick={pick} disabled={busy === "look"} />
      <ErrorLine>{err}</ErrorLine>
    </Card>
  );
}

function DomainCard({ d }) {
  const site = d.site;
  const [dom, setDom] = useState(site.domain || "");
  const [msg, setMsg] = useState("");
  const { busy, err, call } = useSiteCall();
  if (!d.caps.custom_domain) {
    return (
      <Card data-testid="site-domain-locked">
        <Label>Your own domain</Label>
        <div className="flex items-start gap-3">
          <span className="w-10 h-10 rounded-full bg-bz-gold-tint text-bz-gold grid place-items-center shrink-0"><Lock className="w-5 h-5" aria-hidden /></span>
          <div>
            <p className="text-[15px]">Put your site on your own address, like www.yourname.in.</p>
            <p className="text-[15px] font-bold mt-1">Part of <span className="text-bz-gold">L1</span>.</p>
          </div>
        </div>
        <LinkButton to="/app/plans?plan=l1&from=website" variant="secondary" className="w-full mt-4" data-testid="site-domain-upgrade">See L1</LinkButton>
      </Card>
    );
  }
  const save = async () => {
    setMsg("");
    const r = await call("save", () => api.put("/website/domain", { domain: dom.trim() }));
    if (r?.site) setDom(r.site.domain || "");
  };
  const check = async () => {
    setMsg("");
    const r = await call("check", () => api.post("/website/domain/check"));
    if (!r?.check) return;
    if (r.check.connected) setMsg("Connected. Your domain shows your site.");
    else if (r.check.ok) setMsg("Your record is right. Our team will now connect your domain. You'll see Connected here when it's done.");
    else setMsg("We can't see the record yet. It can take a few hours after you save it. Check again later.");
  };
  const remove = async () => {
    if (!window.confirm("Disconnect this domain? Your site stays on its own link.")) return;
    const r = await call("rm", () => api.delete("/website/domain"));
    if (r?.site) setDom("");
  };
  const dns = site.dns;
  return (
    <Card data-testid="site-domain">
      <Label>Your own domain</Label>
      <Field label="Domain you own" hint="Type it like www.yourname.in. Buy one from any domain provider first.">
        <div className="flex gap-2">
          <Input value={dom} onChange={(e) => setDom(e.target.value)} placeholder="www.yourname.in" maxLength={253} autoCapitalize="none" data-testid="site-domain-input" />
          <Button variant="quiet" className="min-h-[48px]" onClick={save} loading={busy === "save"} data-testid="site-domain-save">Save</Button>
        </div>
      </Field>
      {dns && (
        <div className="mt-4 space-y-3">
          <div className="flex items-center gap-2 flex-wrap">
            <Globe className="w-4 h-4 text-bz-gold" aria-hidden />
            <span className="font-bold break-all">{site.domain}</span>
            <Chip tone={site.domain_status === "connected" ? "solid" : "muted"}>{site.domain_status === "connected" ? "Connected" : "Not connected yet"}</Chip>
          </div>
          {site.domain_status !== "connected" && (
            <p className="text-[14px] text-bz-muted">Your site isn't on this domain yet. Add the record below. Then our team checks it and connects your domain.</p>
          )}
          <Step n={1} title="Open your domain's DNS settings">Log in where you bought the domain (GoDaddy, Hostinger, BigRock or any other) and open DNS settings.</Step>
          <Step n={2} title="Add one CNAME record">
            <dl className="mt-1.5 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-[14px]">
              <dt className="text-bz-muted">Type</dt><dd className="font-bzmono text-bz-ink">{dns.type}</dd>
              <dt className="text-bz-muted">Name</dt><dd className="font-bzmono text-bz-ink">{dns.name}</dd>
              <dt className="text-bz-muted">Points to</dt><dd className="font-bzmono text-bz-ink break-all">{dns.value}<CopyLink text={dns.value} /></dd>
            </dl>
          </Step>
          <Step n={3} title="Save, then check it here">Records can take a few hours to show. Once your record is right, our team connects your domain. Then this card says Connected.</Step>
          <div className="flex flex-wrap gap-2">
            <Button variant="secondary" onClick={check} loading={busy === "check"} data-testid="site-domain-check">Check my record</Button>
            <Button variant="danger" onClick={remove} loading={busy === "rm"}>Disconnect</Button>
          </div>
          {msg && <p className="text-[14px]" role="status">{msg}</p>}
        </div>
      )}
      <ErrorLine>{err}</ErrorLine>
    </Card>
  );
}

function SeoCard({ d }) {
  const seo = d.site.seo || {};
  const [t, setT] = useState(seo.title || "");
  const [desc, setDesc] = useState(seo.description || "");
  const [ok, setOk] = useState("");
  const { busy, err, call } = useSiteCall();
  const save = async () => {
    setOk("");
    const r = await call("save", () => api.put("/website/settings", { seo_title: t, seo_description: desc }));
    if (r?.site) setOk("Saved.");
  };
  return (
    <Card>
      <Label>Search and sharing</Label>
      <Note className="mb-3">What Google shows, and what people see when you share your link on WhatsApp or LinkedIn.</Note>
      <div className="space-y-3">
        <Field label={`Page title (${t.length}/60)`}><Input value={t} onChange={(e) => setT(e.target.value)} maxLength={70} data-testid="site-seo-title" /></Field>
        <Field label={`Description (${desc.length}/155)`}><Textarea value={desc} onChange={(e) => setDesc(e.target.value)} maxLength={160} rows={3} className="!min-h-[88px]" /></Field>
      </div>
      <ErrorLine>{err}</ErrorLine><OkLine>{ok}</OkLine>
      <Button variant="secondary" className="mt-3" onClick={save} loading={busy === "save"}>Save</Button>
    </Card>
  );
}

function LeadsCard({ d }) {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["website-leads", d.site.leads_unread], queryFn: async () => (await api.get("/website/leads")).data,
    placeholderData: (prev) => prev });
  useEffect(() => {
    if (q.isSuccess && d.site.leads_unread > 0) {
      qc.setQueryData(["website"], (old) => (old?.site ? { ...old, site: { ...old.site, leads_unread: 0 } } : old));
    }
  }, [q.isSuccess, d.site.leads_unread, qc]);
  return (
    <div id="site-leads">
      <Loadable q={q} what="your messages" lines={3}>
        {(r) => (
          <Card data-testid="site-leads">
            <Label>Messages from your site</Label>
            {!(r.items || []).length ? (
              <div className="flex items-start gap-3 py-2">
                <Inbox className="w-5 h-5 text-bz-muted shrink-0 mt-0.5" aria-hidden />
                <p className="text-[14px] text-bz-muted">No messages yet. When someone fills the form on your site, it shows here and in your Inbox.</p>
              </div>
            ) : (
              <ul className="divide-y divide-bz-line">
                {r.items.map((m) => (
                  <li key={m.id} className="py-3.5">
                    <div className="flex items-start justify-between gap-3">
                      <p className="font-bold text-[15px]">{m.name}{m.company ? <span className="text-bz-muted font-normal"> · {m.company}</span> : null}</p>
                      <span className="text-[12px] text-bz-muted shrink-0">{ago(m.at)}</span>
                    </div>
                    {m.message && <p className="text-[14px] mt-1 whitespace-pre-line">{m.message}</p>}
                    <div className="flex flex-wrap gap-x-4 mt-1">
                      {m.email && <a href={`mailto:${m.email}`} className="inline-flex items-center gap-1.5 text-[13px] font-bold text-bz-gold min-h-[40px] break-all"><Mail className="w-3.5 h-3.5 shrink-0" aria-hidden />{m.email}</a>}
                      {m.phone && <a href={`tel:${m.phone}`} className="inline-flex items-center gap-1.5 text-[13px] font-bold text-bz-gold min-h-[40px]"><Phone className="w-3.5 h-3.5" aria-hidden />{m.phone}</a>}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        )}
      </Loadable>
    </div>
  );
}

function RebuildCard({ d }) {
  const { plan } = useAuth();
  const { busy, err, call } = useSiteCall();
  const usage = plan?.limits?.site_ai;
  const rebuild = () => {
    if (!window.confirm("Write the whole site again? Every section is replaced with new writing. Your address, look, contact details and images stay.")) return;
    call("rebuild", () => api.post("/website/build", { replace: true, look: d.site.look }), { metered: true });
  };
  return (
    <Card inset>
      {busy === "rebuild" ? <Thinking label="Writing your site again" /> : (
        <div className="flex flex-col sm:flex-row sm:items-center gap-3 justify-between">
          <div>
            <p className="font-bold text-[15px]">Start the writing again</p>
            <p className="text-[13px] text-bz-muted">Useful after you update your Starting Point, Offer Card or career stories. Uses one AI edit.</p>
            <UsageLine usage={usage} what="website AI edits" className="mt-1" />
          </div>
          <Button variant="ai" onClick={rebuild} data-testid="site-rebuild">Write it again</Button>
        </div>
      )}
      <ErrorLine>{err}</ErrorLine>
    </Card>
  );
}
