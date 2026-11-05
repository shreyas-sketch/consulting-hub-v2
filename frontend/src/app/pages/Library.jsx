// /app/library and /app/library/:id — session recordings and workbooks, grouped by section.
// YouTube (youtube-nocookie) and Vimeo links play in an embedded player; workbooks open as PDFs; other links open in a new tab.
import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ExternalLink, FileText, Library as LibraryIcon, PlayCircle, X } from "lucide-react";
import { api, API_BASE } from "@/lib/api";
import { Gate } from "../components/common";
import { Card, Chip, Empty, Label, Loadable, Note, PageHeader, Segmented } from "../components/ui";

const apiHref = (path) => (path ? `${API_BASE}${path.replace(/^\/api/, "")}` : null);
const KIND = { video: "Recording", workbook: "Workbook", link: "Link" };

function Player({ item }) {
  return (
    <div className="mt-3 rounded-bzcard overflow-hidden border border-bz-line bg-black aspect-video" data-testid={`library-player-${item.id}`}>
      <iframe src={item.embed.src} title={item.title} className="w-full h-full" loading="lazy" referrerPolicy="strict-origin-when-cross-origin"
        allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture; fullscreen" allowFullScreen />
    </div>
  );
}

const pill = "inline-flex items-center justify-center gap-1.5 min-h-[44px] px-4 rounded-bzbtn border border-bz-line bg-bz-raised text-[14px] font-bold hover:border-bz-line-strong";

function Item({ it, open, onOpen }) {
  return (
    <li className="py-4 border-b border-bz-line last:border-0" id={`item-${it.id}`}>
      <div className="flex items-center gap-2 flex-wrap">
        <Chip tone={it.kind === "video" ? "gold" : "muted"}>{KIND[it.kind] || "Item"}</Chip>
        {it.plan_min === "l2" && <Chip tone="gold">L2</Chip>}
      </div>
      <p className="text-[16px] font-bold mt-1.5 leading-snug">{it.title}</p>
      {it.description && <p className="text-[14px] text-bz-muted mt-1 leading-relaxed">{it.description}</p>}
      <div className="flex flex-wrap gap-2 mt-3">
        {it.embed && (
          <button type="button" className={pill} onClick={() => onOpen(open ? null : it.id)} aria-expanded={open} data-testid={`library-play-${it.id}`}>
            {open ? <X className="w-4 h-4 text-bz-gold" aria-hidden /> : <PlayCircle className="w-4 h-4 text-bz-gold" aria-hidden />}
            {open ? "Close the player" : "Play here"}
          </button>
        )}
        {it.file_url && (
          <a href={apiHref(it.file_url)} target="_blank" rel="noopener noreferrer" className={pill} data-testid={`library-file-${it.id}`}>
            <FileText className="w-4 h-4 text-bz-gold" aria-hidden /> Open the workbook
          </a>
        )}
        {it.url && !it.embed && (
          <a href={it.url} target="_blank" rel="noopener noreferrer" className={pill} data-testid={`library-link-${it.id}`}>
            <ExternalLink className="w-4 h-4 text-bz-gold" aria-hidden /> {it.kind === "workbook" ? "Open the workbook" : "Open"}
          </a>
        )}
      </div>
      {open && it.embed && <Player item={it} />}
    </li>
  );
}

function Body({ d }) {
  const { id } = useParams();
  const [open, setOpen] = useState(id || null);
  const [section, setSection] = useState("all");
  const sections = d.sections || [];
  useEffect(() => {
    if (id) document.getElementById(`item-${id}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [id]);
  const shown = section === "all" ? sections : sections.filter((s) => s.name === section);
  if (!sections.length) {
    return <Empty icon={LibraryIcon} title="Nothing here yet" sub="Recordings and workbooks show here after each session." />;
  }
  return (
    <div className="space-y-4">
      {sections.length > 1 && (
        <Segmented label="Section" value={section} onChange={setSection} testid="library-section"
          options={[{ value: "all", label: "All" }, ...sections.map((s) => ({ value: s.name, label: s.name }))]} />
      )}
      {shown.map((s) => (
        <Card key={s.name} data-testid="library-section-card">
          <Label>{s.name}</Label>
          <ul>{s.items.map((it) => <Item key={it.id} it={it} open={open === it.id} onOpen={setOpen} />)}</ul>
        </Card>
      ))}
      {d.l2_hidden > 0 && <Note>L2 Mentorship members also get {d.l2_hidden} more recording{d.l2_hidden === 1 ? "" : "s"} and workbook{d.l2_hidden === 1 ? "" : "s"}.</Note>}
    </div>
  );
}

function Inner() {
  const q = useQuery({ queryKey: ["library"], queryFn: async () => (await api.get("/library")).data });
  return <Loadable q={q} what="the library" lines={6}>{(d) => <Body d={d} />}</Loadable>;
}

export default function Library() {
  const header = (
    <PageHeader kicker="Recordings and workbooks" title="Every session," accent="in one place."
      sub="Watch a session again, open its workbook, and catch up on anything you missed." />
  );
  return (
    <Gate feature="recordings" header={header}>
      <div className="space-y-5">
        {header}
        <Inner />
      </div>
    </Gate>
  );
}

