// /app/decks and /app/decks/:id — Presentation Builder: build a client deck from your notes, a case you solved or a
// Meeting Brief. The AI writes the slides; the hub draws them (preview here, PowerPoint and PDF to download). Change any
// slide's text, switch Dark / Light and present full screen, all free; only making a new deck uses the plan.
import { useCallback, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, Pencil, Play, Presentation, Trash2 } from "lucide-react";
import { API_BASE, api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { ago, hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Empty, ErrorLine, Field, Input, Label, LinkButton, Loadable, Note, PageHeader, RowLink, Segmented, Select, Textarea, Thinking } from "../components/ui";
import { SlideCanvas, slideLabel } from "../components/decks/SlideCanvas";
import Present from "../components/decks/Present";
import SlideEditor, { layoutName } from "../components/decks/SlideEditor";

const HEADER = <PageHeader kicker="Presentation Builder" ai title="Turn your work into" accent="a client deck."
  sub="Start from your notes, a case you solved or a Meeting Brief. You get slides to present here, plus PowerPoint and PDF files." />;
const ORIGIN = API_BASE.replace(/\/api$/, "");
const SOURCE_LABEL = { text: "My notes", case: "A case I solved", brief: "A Meeting Brief" };
const LOOK_LABEL = { dark: "Dark", light: "Light" };
const DL_CLS = "inline-flex items-center justify-center gap-2 rounded-bzbtn min-h-[52px] px-5 py-3 border border-bz-rule text-bz-ink font-bold text-[15px] hover:border-bz-gold";

function sizeLabel(bytes) {
  if (!bytes) return "";
  return bytes >= 1024 * 1024 ? `${(bytes / (1024 * 1024)).toFixed(1)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

// ---- one deck: preview, present, edit, download ----------------------------------------------------------------------
function DeckView({ id }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const q = useQuery({ queryKey: ["deck", id], queryFn: async () => (await api.get(`/decks/${id}`)).data });
  const opts = useQuery({ queryKey: ["deck-options"], queryFn: async () => (await api.get("/decks/options")).data, staleTime: Infinity });
  const [present, setPresent] = useState(null);
  const [editing, setEditing] = useState(null);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState("");
  const [editErr, setEditErr] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);

  const save = useCallback(async (body) => {
    setSaving(true); setErr(""); setEditErr("");
    try {
      const { data } = await api.patch(`/decks/${id}`, body, { timeout: 60000 });
      qc.setQueryData(["deck", id], data);
      qc.invalidateQueries({ queryKey: ["decks"] });
      return true;
    } catch (e) {
      const msg = apiError(e);
      if (body.slides) setEditErr(msg); else setErr(msg);
      return false;
    } finally { setSaving(false); }
  }, [id, qc]);

  const saveSlide = async (i, slide) => {
    const slides = q.data.deck.slides.map((s, k) => (k === i ? slide : s));
    if (await save({ slides })) setEditing(null);
  };

  const remove = async () => {
    if (!confirmDelete) { setConfirmDelete(true); return; }
    setSaving(true);
    try {
      await api.delete(`/decks/${id}`);
      qc.removeQueries({ queryKey: ["deck", id] });
      qc.invalidateQueries({ queryKey: ["decks"] });
      nav("/app/decks");
    } catch (e) { setErr(apiError(e)); setSaving(false); }
  };

  return (
    <div className="space-y-4">
      <BackLink to="/app/decks">All decks</BackLink>
      <Loadable q={q} what="this deck" lines={5}>
        {(d) => (
          <>
            <PageHeader kicker="Presentation Builder" ai title={d.title}
              sub={`${d.slides} slides · ${SOURCE_LABEL[d.source] || "Deck"} · made ${ago(d.created_at)}${d.edited_at ? ` · changed ${ago(d.edited_at)}` : ""}`} />
            {!d.deck ? (
              <Card inset role="alert">
                <p className="font-bold">This deck can't be opened here.</p>
                <p className="text-[14px] text-bz-muted mt-1">It was made with an older version of the Presentation Builder. Make it again; it takes about a minute.</p>
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  <LinkButton to="/app/decks" variant="secondary">Make a new deck</LinkButton>
                  <Button variant="danger" onClick={remove} loading={saving} data-testid="deck-delete">{confirmDelete ? "Tap again to delete" : "Delete this deck"}</Button>
                </div>
              </Card>
            ) : (
              <>
                <Card className="border-bz-rule" data-testid="deck-ready">
                  <Button className="w-full" onClick={() => setPresent(0)} data-testid="deck-present">
                    <Play className="w-4 h-4" aria-hidden /> Present
                  </Button>
                  <div className="mt-3 grid gap-2 sm:grid-cols-2">
                    {d.files?.pptx && (
                      <a href={`${ORIGIN}${d.files.pptx.url}`} className={DL_CLS} data-testid="deck-download-pptx">
                        <Download className="w-4 h-4" aria-hidden /> Download PowerPoint
                      </a>
                    )}
                    {d.files?.pdf && (
                      <a href={`${ORIGIN}${d.files.pdf.url}`} className={DL_CLS} data-testid="deck-download-pdf">
                        <Download className="w-4 h-4" aria-hidden /> Download PDF
                      </a>
                    )}
                  </div>
                  <p className="text-[13px] text-bz-muted mt-2 text-center">
                    {[d.files?.pptx && `PowerPoint ${sizeLabel(d.files.pptx.size)}`, d.files?.pdf && `PDF ${sizeLabel(d.files.pdf.size)}`].filter(Boolean).join(" · ")}
                  </p>
                  <div className="mt-4">
                    <Label tone="muted">Look</Label>
                    <Segmented label="Look" value={d.theme} testid="deck-look"
                      onChange={(v) => { if (v !== d.theme && !saving) save({ theme: v }); }}
                      options={(opts.data?.themes || [{ key: "dark", name: "Dark" }, { key: "light", name: "Light" }]).map((t) => ({ value: t.key, label: t.name }))} />
                    <Note className="mt-1.5">
                      {saving && editing == null && !confirmDelete ? "Redrawing your slides…" : (opts.data?.themes || []).find((t) => t.key === d.theme)?.note}
                    </Note>
                  </div>
                  <ErrorLine>{err}</ErrorLine>
                  <Note className="mt-3">PowerPoint uses the Manrope font; on a computer without it, a similar font is used and line breaks may move a little.</Note>
                  <Note className="mt-1">Check every number and name before you send it. Changing text and the look is free.</Note>
                </Card>

                <section className="space-y-4" aria-label="Your slides">
                  {d.layout.map((sl, i) => (
                    <div key={i} data-testid={`slide-${i + 1}`}>
                      <div className="flex items-center justify-between gap-3 mb-1.5">
                        <span className="text-[12px] font-semibold text-bz-muted">
                          {i + 1} · {layoutName(d.deck.slides[i]?.layout)}
                        </span>
                        <Button variant="small" onClick={() => { setEditErr(""); setEditing(i); }} data-testid={`slide-edit-${i + 1}`}>
                          <Pencil className="w-3.5 h-3.5" aria-hidden /> Edit text
                        </Button>
                      </div>
                      <button type="button" onClick={() => setPresent(i)} className="block w-full rounded-[10px] overflow-hidden border border-bz-line hover:border-bz-line-strong text-left"
                        aria-label={`Present from slide ${i + 1}`}>
                        <SlideCanvas slide={sl} canvas={d.canvas} label={slideLabel(sl, i + 1)} />
                      </button>
                    </div>
                  ))}
                </section>

                <div className="pt-2">
                  <Button variant="danger" className="w-full sm:w-auto" onClick={remove} loading={saving && confirmDelete} data-testid="deck-delete">
                    <Trash2 className="w-4 h-4" aria-hidden /> {confirmDelete ? "Tap again to delete this deck" : "Delete this deck"}
                  </Button>
                </div>

                {present != null && <Present layout={d.layout} canvas={d.canvas} start={present} onClose={() => setPresent(null)} />}
                {editing != null && d.deck.slides[editing] && (
                  <SlideEditor key={`${editing}-${d.updated_at}`} slide={d.deck.slides[editing]} n={editing + 1} limits={opts.data?.limits}
                    saving={saving} error={editErr} onSave={(s) => saveSlide(editing, s)} onClose={() => setEditing(null)} />
                )}
              </>
            )}
          </>
        )}
      </Loadable>
    </div>
  );
}

// ---- make one --------------------------------------------------------------------------------------------------------
function DeckHome() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const opts = useQuery({ queryKey: ["deck-options"], queryFn: async () => (await api.get("/decks/options")).data, staleTime: Infinity });
  const src = useQuery({ queryKey: ["deck-sources"], queryFn: async () => (await api.get("/decks/sources")).data });
  const list = useQuery({ queryKey: ["decks"], queryFn: async () => (await api.get("/decks")).data });
  const [f, setF] = useState({ source: "text", id: "", title: "", audience: "", notes: "", slides: 8, tone: "clear", theme: "dark" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const set = (k) => (v) => setF((x) => ({ ...x, [k]: v }));
  const usage = plan?.limits?.presentation;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const answers = src.data?.answers || [];
  const briefs = src.data?.briefs || [];

  const run = async (e) => {
    e.preventDefault();
    if (f.source === "text" && f.title.trim().length < 3) { setErr("Give your deck a title."); return; }
    if (f.source === "text" && f.notes.trim().length < 20) { setErr("Add your notes: a few lines on what the deck should say."); return; }
    if (f.source !== "text" && !f.id) { setErr(f.source === "case" ? "Pick a case you solved." : "Pick a Meeting Brief."); return; }
    setErr(""); setBusy(true);
    try {
      const body = { ...f, id: f.source === "text" ? null : f.id, slides: Number(f.slides) };
      const { data } = await api.post("/decks", body, { timeout: 180000 });
      qc.setQueryData(["deck", data.id], data); qc.invalidateQueries({ queryKey: ["decks"] }); refreshMe();
      nav(`/app/decks/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {HEADER}
      {busy ? (
        <AiFrame title="Presentation Builder">
          <Thinking label="Writing and drawing your slides" />
          <p className="text-[14px] text-bz-muted">This takes about a minute. Keep this page open.</p>
        </AiFrame>
      ) : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-5">
            <div>
              <Label tone="muted">Build it from</Label>
              <Segmented label="Build it from" value={f.source} onChange={(v) => { setF((x) => ({ ...x, source: v, id: "" })); setErr(""); }} testid="deck-source"
                options={[{ value: "text", label: "My notes" }, { value: "case", label: "A case I solved" }, { value: "brief", label: "A Meeting Brief" }]} />
            </div>
            {f.source === "text" && (
              <>
                <Field label="Deck title"><Input value={f.title} onChange={(e) => set("title")(e.target.value)} maxLength={120} placeholder="e.g. Cutting wastage at Sharma Fresh Mart" data-testid="deck-title" /></Field>
                <Field label="Who it's for (optional)"><Input value={f.audience} onChange={(e) => set("audience")(e.target.value)} maxLength={160} placeholder="e.g. The owner and the store managers" data-testid="deck-audience" /></Field>
                <Field label="Your notes" hint="Write what the deck should say: the problem, what you found, what you recommend. Put in your own numbers; nothing is made up.">
                  <Textarea value={f.notes} onChange={(e) => set("notes")(e.target.value)} maxLength={6000} className="min-h-[160px]" data-testid="deck-notes" />
                </Field>
              </>
            )}
            {f.source === "case" && (answers.length ? (
              <>
                <Field label="Your case answer" hint="The deck follows the six steps of the Strategic Thinking Framework, using the case, your answer and the model answer.">
                  <Select value={f.id} onChange={(e) => set("id")(e.target.value)} data-testid="deck-pick">
                    <option value="">Pick a case</option>
                    {answers.map((a) => <option key={a.id} value={a.id}>{a.company}: {a.title} · {a.overall}/10 · {hdate(a.at)}</option>)}
                  </Select>
                </Field>
                <Field label="Who it's for (optional)"><Input value={f.audience} onChange={(e) => set("audience")(e.target.value)} maxLength={160} placeholder="The company's owner and leadership team" data-testid="deck-audience" /></Field>
              </>
            ) : <Note>Solve a case first, then turn your answer into a deck. <Link to="/app/cases" className="text-bz-gold font-bold">Go to cases</Link></Note>)}
            {f.source === "brief" && (briefs.length ? (
              <>
                <Field label="Your Meeting Brief" hint="A short deck for your first meeting with this company.">
                  <Select value={f.id} onChange={(e) => set("id")(e.target.value)} data-testid="deck-pick">
                    <option value="">Pick a brief</option>
                    {briefs.map((b) => <option key={b.id} value={b.id}>{b.company} · {hdate(b.at)}</option>)}
                  </Select>
                </Field>
                <Field label="Who it's for (optional)"><Input value={f.audience} onChange={(e) => set("audience")(e.target.value)} maxLength={160} placeholder="e.g. Head of Operations" data-testid="deck-audience" /></Field>
              </>
            ) : <Note>Make a Meeting Brief first. <Link to="/app/brief" className="text-bz-gold font-bold">Go to Meeting Brief</Link></Note>)}

            <Loadable q={opts} what="the deck options" lines={2}>
              {(o) => (
                <div className="space-y-4">
                  <Field label="Number of slides">
                    <Select value={f.slides} onChange={(e) => set("slides")(Number(e.target.value))} data-testid="deck-slides">
                      {Array.from({ length: (o.slides?.max || 14) - (o.slides?.min || 6) + 1 }, (_, i) => (o.slides?.min || 6) + i).map((n) => <option key={n} value={n}>{n} slides</option>)}
                    </Select>
                  </Field>
                  <div>
                    <Label tone="muted">Tone</Label>
                    <Segmented label="Tone" value={f.tone} onChange={set("tone")} testid="deck-tone" options={(o.tones || []).map((t) => ({ value: t.key, label: t.label }))} />
                  </div>
                  <div>
                    <Label tone="muted">Look</Label>
                    <Segmented label="Look" value={f.theme} onChange={set("theme")} testid="deck-theme" options={(o.themes || []).map((t) => ({ value: t.key, label: t.name }))} />
                    <Note className="mt-1.5">{(o.themes || []).find((t) => t.key === f.theme)?.note}. You can switch later for free.</Note>
                  </div>
                </div>
              )}
            </Loadable>
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="deck-run">Make my deck</Button>
            <UsageLine usage={usage} what="decks" className="text-center" />
          </form>
        </Card>
      )}
      <Loadable q={list} what="your decks">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your decks</Label>
            {d.items.map((x) => <RowLink key={x.id} to={`/app/decks/${x.id}`} title={x.title} icon={Presentation}
              sub={`${x.slides} slides · ${LOOK_LABEL[x.theme] || "Dark"} · ${hdate(x.created_at)}`} testid={`deck-${x.id}`} />)}
          </Card>
        ) : <Empty icon={Presentation} title="No decks yet" sub="Your first deck takes about a minute." />}
      </Loadable>
    </div>
  );
}

export default function Decks() {
  const { id } = useParams();
  return <Gate feature="presentation" header={HEADER}>{id ? <DeckView id={id} /> : <DeckHome />}</Gate>;
}
