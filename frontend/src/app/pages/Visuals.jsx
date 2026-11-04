// /app/visuals and /app/visuals/:id — Visual Builder: describe a framework, chart or mind map; the AI lays it out and
// the app draws it as a clean SVG. Edit the words (free), duplicate, download SVG or PNG, dark or light.
import { useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Shapes } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { hdate } from "@/lib/format";
import { BackLink, Gate, UsageLine } from "../components/common";
import { AiFrame, Button, Card, Chip, Empty, ErrorLine, Field, Input, Label, Loadable, Note, OkLine, PageHeader, RowLink, Segmented, Sheet, Textarea, Thinking } from "../components/ui";
import { KINDS, KIND_LABEL, VisualSvg, downloadPng, downloadSvg, fileName } from "../components/visuals";

const HEADER = <PageHeader kicker="Visual Builder" ai title="Show your thinking" accent="in one picture."
  sub="Describe a framework, a process or a chart. The AI lays it out and you get a clean picture for your slides and posts." />;

// ---- the words editor: every text (and, for charts, every number) in the spec, as plain fields --------------------
const NAMES = {
  title: "Title", note: "Note under the picture", x_axis: "Across", y_axis: "Up", label: "Name", low: "Low end", high: "High end",
  quadrants: "Box", items: "Item", steps: "Step", levels: "Level", stages: "Stage", detail: "Detail", value: "Number",
  centre: "Centre", branches: "Branch", leaves: "Leaf", columns: "Column", rows: "Row", cells: "Cell", labels: "Label",
  series: "Series", name: "Name", values: "Value", unit: "Unit", x: "Across (0–100)", y: "Up (0–100)",
};
const QUAD = ["Top left", "Top right", "Bottom left", "Bottom right"];

function fieldsOf(node, path = []) {
  if (typeof node === "string") return [{ path, kind: "text" }];
  if (typeof node === "number") return [{ path, kind: "number" }];
  if (Array.isArray(node)) return node.flatMap((x, i) => fieldsOf(x, [...path, i]));
  if (node && typeof node === "object") return Object.keys(node).filter((k) => k !== "chart").flatMap((k) => fieldsOf(node[k], [...path, k]));
  return [];
}

function nameOf(path) {
  const out = [];
  for (let i = 0; i < path.length; i += 1) {
    const p = path[i];
    if (typeof p === "number") continue;
    const idx = typeof path[i + 1] === "number" ? path[i + 1] : null;
    if (p === "quadrants" && idx != null) out.push(QUAD[idx] || `Box ${idx + 1}`);
    else out.push(`${NAMES[p] || p}${idx != null ? ` ${idx + 1}` : ""}`);
  }
  return out.join(" · ");
}

const getIn = (o, path) => path.reduce((a, k) => (a == null ? a : a[k]), o);
function setIn(o, path, v) {
  if (!path.length) return v;
  const [k, ...rest] = path;
  const copy = Array.isArray(o) ? [...o] : { ...o };
  copy[k] = setIn(o[k], rest, v);
  return copy;
}

function SpecEditor({ spec, onChange }) {
  const fields = fieldsOf(spec);
  return (
    <div className="space-y-3">
      {fields.map((f) => {
        const key = f.path.join(".");
        const v = getIn(spec, f.path);
        return (
          <Field key={key} label={nameOf(f.path)}>
            {f.kind === "number"
              ? <Input type="number" inputMode="decimal" step="any" value={v} onChange={(e) => onChange(setIn(spec, f.path, e.target.value === "" ? 0 : Number(e.target.value)))} data-testid={`edit-${key}`} />
              : <Input value={v} maxLength={key === "title" ? 80 : 140} onChange={(e) => onChange(setIn(spec, f.path, e.target.value))} data-testid={`edit-${key}`} />}
          </Field>
        );
      })}
    </div>
  );
}

// ---- one visual -----------------------------------------------------------------------------------------------------
function VisualView({ id }) {
  const qc = useQueryClient();
  const nav = useNavigate();
  const [params, setParams] = useSearchParams();
  const box = useRef(null);
  const [theme, setTheme] = useState("dark");
  const [draft, setDraft] = useState(null);
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const q = useQuery({ queryKey: ["visual", id], queryFn: async () => (await api.get(`/visuals/${id}`)).data });
  const editing = draft || (params.get("edit") === "1" && q.data ? q.data.spec : null);
  const svg = () => box.current?.querySelector("svg");

  const closeEdit = () => { setDraft(null); if (params.get("edit")) setParams({}, { replace: true }); };
  const save = async () => {
    setErr(""); setBusy("save");
    try {
      const { data } = await api.put(`/visuals/${id}`, { spec: editing });
      qc.setQueryData(["visual", id], data); qc.invalidateQueries({ queryKey: ["visuals"] });
      closeEdit(); setOk("Saved.");
    } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };
  const duplicate = async () => {
    setErr(""); setBusy("dup");
    try {
      const { data } = await api.post(`/visuals/${id}/duplicate`);
      qc.setQueryData(["visual", data.id], data); qc.invalidateQueries({ queryKey: ["visuals"] });
      nav(`/app/visuals/${data.id}?edit=1`);
    } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };
  const remove = async () => {
    if (!window.confirm("Delete this visual? This cannot be undone.")) return;
    try { await api.delete(`/visuals/${id}`); qc.invalidateQueries({ queryKey: ["visuals"] }); nav("/app/visuals"); } catch (e) { setErr(apiError(e)); }
  };
  const png = async (title) => {
    setErr("");
    try { await downloadPng(svg(), fileName(title, "png"), 2); } catch { setErr("The PNG couldn't be made on this device. Try Download SVG."); }
  };

  return (
    <div className="space-y-4">
      <BackLink to="/app/visuals">All visuals</BackLink>
      <Loadable q={q} what="this visual" lines={8}>
        {(v) => (
          <>
            <div className="flex flex-wrap items-center gap-2">
              <Chip tone="teal">{KIND_LABEL[v.kind]}</Chip>
              <span className="text-[13px] text-bz-muted">{hdate(v.updated_at || v.at)}</span>
              {v.copied_from && <Chip>Copy</Chip>}
            </div>
            <div className="rounded-bzcard border border-bz-line overflow-x-auto" data-testid="visual-preview">
              <div ref={box} className="min-w-[720px] sm:min-w-0"><VisualSvg kind={v.kind} spec={v.spec} theme={theme} /></div>
            </div>
            <Card>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <Segmented label="Background" value={theme} onChange={setTheme} testid="visual-theme"
                  options={[{ value: "dark", label: "Dark" }, { value: "light", label: "Light" }]} />
                <Note>Light is for slides with a white background.</Note>
              </div>
              <div className="mt-4 grid gap-2 sm:grid-cols-2">
                <Button onClick={() => png(v.spec.title)} data-testid="visual-png">Download PNG</Button>
                <Button variant="secondary" onClick={() => downloadSvg(svg(), fileName(v.spec.title, "svg"))} data-testid="visual-svg">Download SVG</Button>
                <Button variant="secondary" onClick={() => { setOk(""); setDraft(v.spec); }} data-testid="visual-edit">Edit the words</Button>
                <Button variant="quiet" loading={busy === "dup"} onClick={duplicate} data-testid="visual-duplicate">Make a copy to edit</Button>
              </div>
              <ErrorLine>{err}</ErrorLine>
              <OkLine>{ok}</OkLine>
              <Note className="mt-3">Editing, copying and downloading are free. They don't use up a visual.</Note>
              <div className="mt-4 pt-4 border-t border-bz-line">
                <Button variant="danger" onClick={remove} data-testid="visual-delete">Delete</Button>
              </div>
            </Card>
            <Sheet open={!!editing} onClose={closeEdit} title="Edit the words" wide>
              {editing && (
                <div className="space-y-4">
                  <div className="rounded-bzcard border border-bz-line overflow-hidden"><VisualSvg kind={v.kind} spec={editing} theme={theme} /></div>
                  <SpecEditor spec={editing} onChange={setDraft} />
                  <ErrorLine>{err}</ErrorLine>
                  <div className="flex gap-2">
                    <Button className="flex-1" loading={busy === "save"} onClick={save} data-testid="visual-save">Save changes</Button>
                    <Button variant="secondary" onClick={closeEdit}>Cancel</Button>
                  </div>
                </div>
              )}
            </Sheet>
          </>
        )}
      </Loadable>
    </div>
  );
}

// ---- make one + the list ----------------------------------------------------------------------------------------------
function VisualHome() {
  const { plan, refreshMe } = useAuth();
  const qc = useQueryClient();
  const nav = useNavigate();
  const list = useQuery({ queryKey: ["visuals"], queryFn: async () => (await api.get("/visuals")).data });
  const [kind, setKind] = useState("process");
  const [prompt, setPrompt] = useState("");
  const [numbers, setNumbers] = useState("");
  const [chart, setChart] = useState("bar");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const usage = plan?.limits?.visuals;
  const canRun = !usage || usage.limit == null || usage.used < usage.limit;
  const k = KINDS.find((x) => x.key === kind);

  const run = async (e) => {
    e.preventDefault();
    if (prompt.trim().length < 5) { setErr("Describe what you want in a sentence or two."); return; }
    if (kind === "chart" && !/\d/.test(`${prompt} ${numbers}`)) { setErr("Paste the numbers for your chart. The chart uses only the numbers you give."); return; }
    setErr(""); setBusy(true);
    try {
      const { data } = await api.post("/visuals", { kind, prompt, numbers: kind === "chart" || kind === "funnel" ? numbers : "", chart });
      qc.setQueryData(["visual", data.id], data); qc.invalidateQueries({ queryKey: ["visuals"] }); refreshMe();
      nav(`/app/visuals/${data.id}`);
    } catch (e2) { if (![402, 403].includes(e2?.response?.status)) setErr(apiError(e2)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5">
      {HEADER}
      {busy ? <AiFrame title="Visual Builder"><Thinking label={`Laying out your ${k.label.toLowerCase()}`} /></AiFrame> : (
        <Card>
          <form onSubmit={run} noValidate className="space-y-4">
            <div>
              <Label tone="muted">What kind of picture</Label>
              <Segmented label="Kind of visual" value={kind} onChange={(v) => { setKind(v); setErr(""); }} testid="visual-kind"
                options={KINDS.map((x) => ({ value: x.key, label: x.label }))} />
              <Note className="mt-2">{k.what}</Note>
            </div>
            <Field label="Describe it" hint={`Example: ${k.example}`}>
              <Textarea value={prompt} onChange={(e) => setPrompt(e.target.value)} maxLength={2000} placeholder="Say what it should show, in your own words." data-testid="visual-prompt" />
            </Field>
            {kind === "chart" && (
              <div>
                <Label tone="muted">Chart type</Label>
                <Segmented label="Chart type" value={chart} onChange={setChart} testid="visual-chart"
                  options={[{ value: "bar", label: "Bars" }, { value: "line", label: "Line" }, { value: "pie", label: "Pie" }]} />
              </div>
            )}
            {(kind === "chart" || kind === "funnel") && (
              <Field label={kind === "chart" ? "Your numbers" : "Your numbers (optional)"} hint="One per line, with its label. The picture uses only the numbers you give.">
                <Textarea value={numbers} onChange={(e) => setNumbers(e.target.value)} maxLength={3000} placeholder={"Apr 12\nMay 15\nJun 19"} data-testid="visual-numbers" />
              </Field>
            )}
            <ErrorLine>{err}</ErrorLine>
            <Button type="submit" variant="ai" className="w-full" disabled={!canRun} data-testid="visual-run">Make my visual</Button>
            <UsageLine usage={usage} what="visuals" className="text-center" />
          </form>
        </Card>
      )}
      <Loadable q={list} what="your visuals">
        {(d) => (d.items || []).length ? (
          <Card>
            <Label>Your visuals</Label>
            {d.items.map((v) => <RowLink key={v.id} to={`/app/visuals/${v.id}`} title={v.title} sub={`${KIND_LABEL[v.kind]} · ${hdate(v.updated_at || v.at)}`} testid={`visual-${v.id}`} right={<Chip tone="teal">Open</Chip>} />)}
          </Card>
        ) : <Empty icon={Shapes} title="No visuals yet" sub="Your first one takes about twenty seconds." />}
      </Loadable>
    </div>
  );
}

export default function Visuals() {
  const { id } = useParams();
  return <Gate feature="visuals" header={HEADER}>{id ? <VisualView id={id} /> : <VisualHome />}</Gate>;
}
