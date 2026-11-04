// Edit one slide's text. The fields follow the slide's layout; every box has the same character limit the server uses,
// so what fits here always fits on the slide. Saving redraws the deck (free: it doesn't use a deck from your plan).
import { useState } from "react";
import { Button, ErrorLine, Field, Input, Note, Select, Sheet, Textarea } from "../ui";

const LAYOUT_NAME = {
  title: "Title", agenda: "Agenda", section: "Section", bullets: "Points", two_column: "Two columns",
  big_number: "Big numbers", quote: "Quote", steps: "Steps", grid_2x2: "Four boxes", table: "Table", closing: "Next step",
};
const CELL = ["Top-left", "Top-right", "Bottom-left", "Bottom-right"];

export function layoutName(key) {
  return LAYOUT_NAME[key] || "Slide";
}

// [{path, label, key (limit), multi, list}] for a slide, in reading order.
export function fieldsFor(s) {
  const f = [];
  const add = (path, label, key, multi = false, list = false) => f.push({ path, label, key, multi, list });
  const kicker = () => add(["kicker"], "Small label above the title", "kicker");
  const title = (key = "title") => {
    add(["title"], "Title", key, true);
    add(["accent"], "Words in gold (copy them from the title)", "accent");
  };
  switch (s.layout) {
    case "title":
      kicker(); title("cover_title");
      add(["subtitle"], "Line under the title", "subtitle", true);
      add(["presenter"], "Presented by", "presenter");
      break;
    case "agenda":
      kicker(); title();
      s.items.forEach((_, i) => add(["items", i], `Item ${i + 1}`, "agenda_item", false, true));
      break;
    case "section":
      kicker(); title("section_title");
      add(["subtitle"], "Line under the title", "section_sub", true);
      break;
    case "bullets":
      kicker(); title();
      s.bullets.forEach((_, i) => add(["bullets", i], `Point ${i + 1}`, "bullet", true, true));
      break;
    case "two_column":
      kicker(); title();
      ["left", "right"].forEach((side) => {
        const name = side === "left" ? "Left" : "Right";
        add([side, "heading"], `${name} heading`, "col_heading");
        s[side].points.forEach((_, i) => add([side, "points", i], `${name} point ${i + 1}`, "col_point", true, true));
      });
      break;
    case "big_number":
      kicker(); title();
      s.stats.forEach((_, i) => {
        add(["stats", i, "value"], `Number ${i + 1}`, "stat_value");
        add(["stats", i, "label"], `What number ${i + 1} means`, "stat_label", true);
      });
      add(["note"], "Small note under the numbers", "stat_note", true);
      break;
    case "quote":
      kicker();
      add(["quote"], "Quote", "quote", true);
      add(["by"], "Who said it", "quote_by");
      break;
    case "steps":
      kicker(); title();
      s.steps.forEach((_, i) => {
        add(["steps", i, "title"], `Step ${i + 1}`, "step_title");
        add(["steps", i, "text"], `Step ${i + 1} detail`, "step_text", true);
      });
      break;
    case "grid_2x2":
      kicker(); title();
      add(["y_axis"], "Label up the side (high at the top)", "axis");
      add(["x_axis"], "Label along the bottom (high on the right)", "axis");
      s.cells.forEach((_, i) => {
        add(["cells", i, "title"], `${CELL[i]} box title`, "cell_title");
        add(["cells", i, "text"], `${CELL[i]} box text`, "cell_text", true);
      });
      break;
    case "table":
      kicker(); title();
      s.columns.forEach((_, c) => add(["columns", c], `Column ${c + 1} heading`, "th"));
      s.rows.forEach((r, ri) => r.forEach((_, c) => add(["rows", ri, c], `Row ${ri + 1}, column ${c + 1}`, "td")));
      break;
    case "closing":
      kicker(); title("closing_title");
      add(["text"], "Line under the title", "closing_text", true);
      add(["action"], "The next step (in the gold box)", "action", true);
      break;
    default:
      break;
  }
  add(["notes"], "Speaker notes (in the PowerPoint file only)", "notes", true);
  return f;
}

const getAt = (o, path) => path.reduce((x, k) => (x == null ? x : x[k]), o);
function setAt(o, [k, ...rest], v) {
  const copy = Array.isArray(o) ? [...o] : { ...o };
  copy[k] = rest.length ? setAt(o[k], rest, v) : v;
  return copy;
}

export default function SlideEditor({ slide, n, limits, saving, error, onSave, onClose }) {
  const [draft, setDraft] = useState(slide);
  const fields = fieldsFor(slide);
  const hasList = fields.some((x) => x.list);
  const submit = (e) => { e.preventDefault(); onSave(draft); };
  return (
    <Sheet open onClose={onClose} title={`Slide ${n} · ${layoutName(slide.layout)}`}>
      <form onSubmit={submit} noValidate className="space-y-4" data-testid="slide-editor">
        {fields.map((fd) => {
          const id = fd.path.join("-");
          const value = getAt(draft, fd.path) ?? "";
          const max = limits?.[fd.key] || 200;
          const set = (e) => setDraft((d) => setAt(d, fd.path, e.target.value));
          const count = `${value.length} / ${max}`;
          return (
            <Field key={id} label={fd.label} hint={value.length > max * 0.8 ? count : null}>
              {fd.multi
                ? <Textarea value={value} onChange={set} maxLength={max} rows={2} className="min-h-[76px]" data-testid={`slide-field-${id}`} />
                : <Input value={value} onChange={set} maxLength={max} data-testid={`slide-field-${id}`} />}
            </Field>
          );
        })}
        {slide.layout === "grid_2x2" && (
          <Field label="Box in gold">
            <Select value={draft.highlight ?? ""} onChange={(e) => setDraft((d) => ({ ...d, highlight: e.target.value === "" ? null : Number(e.target.value) }))}
              data-testid="slide-field-highlight">
              <option value="">None</option>
              {CELL.map((c, i) => <option key={c} value={i}>{c}: {draft.cells[i]?.title}</option>)}
            </Select>
          </Field>
        )}
        {hasList && <Note>Leave a point empty to remove it.</Note>}
        <ErrorLine>{error}</ErrorLine>
        <div className="grid gap-2 sm:grid-cols-2 pt-1">
          <Button type="submit" loading={saving} data-testid="slide-save">Save and redraw</Button>
          <Button variant="secondary" onClick={onClose} disabled={saving}>Cancel</Button>
        </div>
        <Note>Changes are free. They don't use a deck from your plan.</Note>
      </form>
    </Sheet>
  );
}
