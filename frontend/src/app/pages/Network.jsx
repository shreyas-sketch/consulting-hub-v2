// /app/network — Warm Network Finder: upload LinkedIn's Connections.csv (or paste a list), see everyone ranked for
// the member's niche (free rule score), pick up to 10 at a time for an AI read (fit 1-10, why, angle),
// filter, mark contacted, keep notes. Nothing is sent from here.
import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Upload } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Gate, UsageLine } from "../components/common";
import {
  Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Note, OkLine, PageHeader, Segmented, Select, Stat,
  Step, Textarea, Thinking,
} from "../components/ui";

const PAGE = 50;

function ImportCard({ onDone, first }) {
  const fileRef = useRef(null);
  const [file, setFile] = useState(null);
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const [open, setOpen] = useState(first);

  const done = (d) => {
    const extra = [d.duplicates ? `${d.duplicates} were already in your list` : "", d.over_cap ? `${d.over_cap} didn't fit (limit ${d.cap.toLocaleString("en-IN")})` : ""].filter(Boolean).join(". ");
    setOk(`Added ${d.added.toLocaleString("en-IN")} ${d.added === 1 ? "person" : "people"}.${extra ? ` ${extra}.` : ""}`);
    setFile(null); setPaste(""); if (fileRef.current) fileRef.current.value = "";
    onDone();
  };
  const upload = async () => {
    if (!file) { setErr("Choose your Connections.csv file first."); return; }
    setErr(""); setOk(""); setBusy("file");
    try {
      const fd = new FormData(); fd.append("file", file);
      done((await api.post("/network/import", fd)).data);
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(""); }
  };
  const addPaste = async () => {
    if (paste.trim().length < 3) { setErr("Put one person on each line: Name, Role, Company."); return; }
    setErr(""); setOk(""); setBusy("paste");
    try { done((await api.post("/network/paste", { text: paste })).data); }
    catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(""); }
  };

  if (!open) {
    return (
      <div className="flex flex-col sm:flex-row sm:items-center gap-2">
        <Button variant="secondary" onClick={() => setOpen(true)} data-testid="network-add-more">Add more people</Button>
        <OkLine>{ok}</OkLine>
      </div>
    );
  }
  return (
    <Card>
      <Label>Bring in your network</Label>
      <div className="space-y-3">
        <Step n={1} title="Get the file from LinkedIn">Settings, then Data privacy, then Get a copy of your data. Tick Connections and request the archive. LinkedIn emails you a link in a few minutes.</Step>
        <Step n={2} title="Upload Connections.csv here">We read names, roles and companies. We never log in to your LinkedIn.</Step>
      </div>
      <div className="mt-4 space-y-3">
        <label className="flex items-center gap-3 rounded-bzcard border border-dashed border-bz-line-strong bg-bz-panel px-4 min-h-[56px] cursor-pointer hover:border-bz-gold">
          <Upload className="w-5 h-5 text-bz-gold shrink-0" aria-hidden />
          <span className="text-[15px] truncate">{file ? file.name : "Choose Connections.csv"}</span>
          <input ref={fileRef} type="file" accept=".csv,text/csv" className="sr-only" data-testid="network-file"
            onChange={(e) => { setFile(e.target.files?.[0] || null); setErr(""); }} />
        </label>
        <Button className="w-full" onClick={upload} loading={busy === "file"} disabled={!!busy} data-testid="network-upload">Upload my connections</Button>
      </div>
      <div className="mt-5 pt-4 border-t border-bz-line">
        <Field label="Or paste a list" hint="One person per line: Name, Role, Company. Or 'Name - Role at Company'.">
          <Textarea rows={4} value={paste} onChange={(e) => setPaste(e.target.value)} maxLength={200000}
            placeholder={"Neha Shah, Director, Bharat Forge\nAmit Joshi - VP Sales at Tata Motors"} data-testid="network-paste" />
        </Field>
        <Button variant="secondary" className="w-full mt-3" onClick={addPaste} loading={busy === "paste"} disabled={!!busy} data-testid="network-paste-add">Add these people</Button>
      </div>
      <ErrorLine>{err}</ErrorLine>
      <OkLine>{ok}</OkLine>
      {!first && <button type="button" onClick={() => setOpen(false)} className="mt-2 w-full text-[14px] font-bold text-bz-muted min-h-[44px]">Close</button>}
    </Card>
  );
}

function Notes({ c, onSaved }) {
  const [open, setOpen] = useState(false);
  const [v, setV] = useState(c.notes || "");
  const [busy, setBusy] = useState(false);
  const save = async () => {
    setBusy(true);
    try { await api.patch(`/network/${c.id}`, { notes: v }); onSaved(); setOpen(false); } catch { /* kept open */ } finally { setBusy(false); }
  };
  if (!open) {
    return (
      <button type="button" onClick={() => setOpen(true)} className="text-left text-[13px] text-bz-muted min-h-[40px] hover:text-bz-ink" data-testid={`contact-notes-${c.id}`}>
        {c.notes ? <>Notes: <span className="text-bz-ink">{c.notes}</span></> : "Add a note"}
      </button>
    );
  }
  return (
    <div className="mt-2 space-y-2">
      <Textarea rows={2} value={v} onChange={(e) => setV(e.target.value)} maxLength={2000} placeholder="e.g. Met at the CII summit. Call after Diwali." className="min-h-[80px]" />
      <div className="flex gap-2">
        <Button variant="small" onClick={save} loading={busy}>Save note</Button>
        <Button variant="small" onClick={() => { setOpen(false); setV(c.notes || ""); }}>Cancel</Button>
      </div>
    </div>
  );
}

function ContactRow({ c, picked, onPick, onChanged }) {
  const [busy, setBusy] = useState(false);
  const toggleContacted = async () => {
    setBusy(true);
    try { await api.patch(`/network/${c.id}`, { status: c.status === "contacted" ? "new" : "contacted" }); onChanged(); } catch { /* ignore */ } finally { setBusy(false); }
  };
  return (
    <li className={`rounded-bzcard border bg-bz-card p-3.5 ${picked ? "border-bz-teal" : "border-bz-line"}`} data-testid={`contact-${c.id}`}>
      <div className="flex items-start gap-3">
        <button type="button" onClick={() => onPick(c.id)} aria-pressed={picked} aria-label={`Pick ${c.name}`}
          className="shrink-0 w-11 h-11 -m-1 grid place-items-center" data-testid={`contact-pick-${c.id}`}>
          <span className={`w-6 h-6 rounded-md border grid place-items-center ${picked ? "bg-bz-teal border-bz-teal text-bz-teal-ink" : "border-bz-line-strong"}`}>
            {picked && <Check className="w-4 h-4" strokeWidth={3} aria-hidden />}
          </span>
        </button>
        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <p className="font-bold text-[15px] truncate">
                {c.url ? <a href={c.url} target="_blank" rel="noopener noreferrer" className="hover:text-bz-gold inline-flex items-center gap-1">{c.name}<ExternalLink className="w-3.5 h-3.5 text-bz-muted" aria-hidden /></a> : c.name}
              </p>
              <p className="text-[13px] text-bz-muted truncate">{[c.position, c.company].filter(Boolean).join(" · ") || "Role not given"}</p>
            </div>
            <div className="flex flex-col items-end gap-1 shrink-0">
              {c.fit != null ? <Chip tone="teal">Fit {c.fit}/10</Chip> : <Chip tone="gold">Match {c.pre_score}</Chip>}
              {c.status === "contacted" && <Chip>Contacted</Chip>}
            </div>
          </div>
          {c.pre_why?.length > 0 && <div className="flex flex-wrap gap-1.5 mt-2">{c.pre_why.map((w) => <Chip key={w}>{w}</Chip>)}</div>}
          {c.fit != null && (
            <div className="mt-2.5 rounded-bzcard border border-[rgba(46,211,183,0.4)] bg-bz-panel p-2.5 text-[14px] space-y-1">
              <p>{c.why}</p>
              {c.angle && <p className="text-bz-teal">Angle: {c.angle}</p>}
            </div>
          )}
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <Link to={`/app/outreach?contact=${c.id}`} className="inline-flex items-center min-h-[40px] px-4 rounded-full border border-bz-line bg-bz-raised text-[13px] font-bold hover:border-bz-line-strong" data-testid={`contact-draft-${c.id}`}>Draft a message</Link>
            <Button variant="small" onClick={toggleContacted} loading={busy} data-testid={`contact-contacted-${c.id}`}>{c.status === "contacted" ? "Not contacted yet" : "Mark contacted"}</Button>
          </div>
          <Notes c={c} onSaved={onChanged} />
        </div>
      </div>
    </li>
  );
}

function Body() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const [f, setF] = useState({ q: "", status: "", view: "all", sort: "pre" });
  const [page, setPage] = useState(0);
  const [picked, setPicked] = useState([]);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const params = { q: f.q.trim() || undefined, status: f.status || undefined, sort: f.sort, page,
    senior: f.view === "senior" || undefined, scored: f.view === "scored" ? "yes" : undefined };
  const q = useQuery({ queryKey: ["network", params], queryFn: async () => (await api.get("/network", { params })).data, placeholderData: (p) => p });
  const usage = plan?.limits?.contacts;
  const left = usage?.limit == null ? 10 : Math.max(0, usage.limit - usage.used);
  const refresh = () => qc.invalidateQueries({ queryKey: ["network"] });
  const set = (k, v) => { setF({ ...f, [k]: v }); setPage(0); };
  const pick = (id) => setPicked((p) => (p.includes(id) ? p.filter((x) => x !== id) : p.length >= 10 ? p : [...p, id]));

  const score = async () => {
    if (!picked.length) return;
    setErr(""); setBusy(true);
    try {
      await api.post("/network/score", { ids: picked });
      setPicked([]); refresh(); refreshMe();
    } catch (e) { if (![402, 403].includes(e?.response?.status)) setErr(apiError(e)); } finally { setBusy(false); }
  };

  return (
    <Loadable q={q} what="your network" lines={6}>
      {(d) => {
        const total = d.counts?.all || 0;
        return (
          <div className="space-y-4">
            <ImportCard first={total === 0} onDone={() => { refresh(); setPage(0); }} />
            {total === 0 ? null : (
              <>
                <div className="grid grid-cols-3 gap-2">
                  <Stat label="In your list" value={total.toLocaleString("en-IN")} sub={`of ${d.cap.toLocaleString("en-IN")}`} />
                  <Stat label="AI scored" value={d.counts.scored} />
                  <Stat label="Contacted" value={d.counts.contacted} />
                </div>
                <Card>
                  <div className="space-y-3">
                    <Input value={f.q} onChange={(e) => set("q", e.target.value)} placeholder="Search name, company or role" maxLength={80} data-testid="network-search" />
                    <Segmented label="Show" value={f.view} onChange={(v) => set("view", v)} testid="network-view"
                      options={[{ value: "all", label: "Everyone" }, { value: "senior", label: "Decision-makers" }, { value: "scored", label: "AI scored" }]} />
                    <div className="grid grid-cols-2 gap-2">
                      <Select value={f.status} onChange={(e) => set("status", e.target.value)} aria-label="Status" data-testid="network-status">
                        <option value="">Any status</option><option value="new">Not contacted</option><option value="contacted">Contacted</option>
                      </Select>
                      <Select value={f.sort} onChange={(e) => set("sort", e.target.value)} aria-label="Sort" data-testid="network-sort">
                        <option value="pre">Best match first</option><option value="fit">AI fit first</option><option value="name">Name A–Z</option>
                      </Select>
                    </div>
                  </div>
                </Card>

                <div className="sticky top-2 z-20 rounded-bzcard border border-bz-line backdrop-blur p-3 flex flex-col sm:flex-row sm:items-center gap-2" style={{ backgroundColor: "rgba(30,32,39,0.96)" }}>
                  <div className="flex-1 min-w-0">
                    <p className="text-[14px] font-bold">{picked.length ? `${picked.length} picked` : "Pick up to 10 people"}</p>
                    <UsageLine usage={usage} what="contacts scored" />
                  </div>
                  {picked.length > 0 && <Button variant="small" onClick={() => setPicked([])}>Clear</Button>}
                  <Button variant="ai" onClick={score} disabled={!picked.length || busy || left < 1} loading={busy} data-testid="network-score">
                    Score {picked.length || ""} with AI
                  </Button>
                </div>
                {busy && <Thinking label="Reading roles and companies against your niche" />}
                <ErrorLine>{err}</ErrorLine>
                {picked.length > left && left > 0 && <Note>You have {left} left this month. Pick {left} or fewer.</Note>}

                {d.items.length ? (
                  <ul className="space-y-2.5">
                    {d.items.map((c) => <ContactRow key={c.id} c={c} picked={picked.includes(c.id)} onPick={pick} onChanged={refresh} />)}
                  </ul>
                ) : <Empty title="No one matches" sub="Try a different search or filter." />}

                {d.total > PAGE && (
                  <div className="flex items-center justify-between gap-2">
                    <Button variant="small" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button>
                    <span className="text-[13px] text-bz-muted">{page * PAGE + 1}–{Math.min(d.total, (page + 1) * PAGE)} of {d.total.toLocaleString("en-IN")}</span>
                    <Button variant="small" disabled={(page + 1) * PAGE >= d.total} onClick={() => setPage(page + 1)}>Next</Button>
                  </div>
                )}
                <Note>The match score is free and uses only role and company. AI scoring uses one of your monthly contacts per person.</Note>
              </>
            )}
          </div>
        );
      }}
    </Loadable>
  );
}

export default function Network() {
  const header = <PageHeader kicker="Warm Network Finder" title="The people you know" accent="who could need you."
    sub="Upload your LinkedIn connections. We rank them for your niche. Pick the best ones for an AI read and a way to start the conversation." />;
  return (
    <div className="space-y-5">
      {header}
      <Gate feature="network_finder"><Body /></Gate>
    </div>
  );
}
