// Markdown for AI replies (GPT tools, Akshat AI, recaps, packs, proposals). Dark theme, Manrope, gold/teal accents.
// Special fenced blocks (same as the current hub):
//   ```text  → copy card with a Copy button        ```ask  → "Your turn — I need this from you" card
//   ```banner → gold banner                         anything else → code block (JetBrains Mono) with Copy
// Strategy Thinking practice blocks:
//   ```steps → the six-step roadmap ("current: N" + "1. Name — what it means")
//   ```you   → script card: what the consultant says (first line = short label)
//   ```client → the client's reply card (first line = "First name — Title")
//   ```next  → a quick-reply button that sends its text (only when the page passes `onNext`)
// GFM task lists ("- [ ] task") become tickable boxes. Tables scroll sideways inside their own box on a phone.
import { createContext, useContext, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { ArrowRight, Check, Copy } from "lucide-react";

const Ctx = createContext({ onNext: null, busy: false });

export function CopyButton({ text, label = "Copy", className = "" }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" className={`no-print inline-flex items-center gap-1 text-[12px] font-bold text-bz-gold min-h-[36px] px-2 ${className}`}
      onClick={async () => { try { await navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); } catch { /* blocked */ } }}>
      {ok ? <Check className="w-3.5 h-3.5" aria-hidden /> : <Copy className="w-3.5 h-3.5" aria-hidden />}{ok ? "Copied" : label}
    </button>
  );
}

// "1. Discovery and diagnosis — Ask questions…" → {n, name, what}
function parseSteps(text) {
  let current = 0;
  const items = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    const cur = /^current\s*:\s*(\d+)/i.exec(line);
    if (cur) { current = Number(cur[1]); continue; }
    const m = /^(\d+)[.)]\s*(.+)$/.exec(line);
    if (!m) continue;
    const [name, ...rest] = m[2].split(/\s+[—–-]\s+/);
    items.push({ n: Number(m[1]), name: name.trim(), what: rest.join(" — ").trim() });
  }
  return { current, items };
}

function StepsCard({ text }) {
  const { current, items } = parseSteps(text);
  if (!items.length) return null;
  return (
    <div className="my-4 rounded-bzcard border border-bz-line bg-bz-panel p-3.5" data-testid="md-steps">
      <p className="text-[11px] font-medium uppercase tracking-[0.14em] text-bz-muted mb-2.5">The six steps{current ? ` · step ${current} of ${items.length}` : ""}</p>
      <ol className="space-y-2">
        {items.map((s) => {
          const done = current && s.n < current;
          const on = s.n === current;
          return (
            <li key={s.n} className="flex gap-2.5 items-start">
              <span className={`w-7 h-7 shrink-0 rounded-full grid place-items-center text-[12px] font-extrabold border ${on ? "bg-bz-gold border-bz-gold text-bz-on-accent" : done ? "border-bz-gold text-bz-gold" : "border-bz-line text-bz-muted"}`}>
                {done ? <Check className="w-3.5 h-3.5" aria-hidden /> : s.n}
              </span>
              <span className="min-w-0 pt-0.5">
                <span className={`block text-[14px] font-bold ${on ? "text-bz-ink" : "text-bz-muted"}`}>{s.name}</span>
                {on && s.what && <span className="block text-[13px] text-bz-muted leading-snug mt-0.5">{s.what}</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function splitLabel(text) {
  const lines = text.split("\n");
  const first = (lines[0] || "").trim();
  const rest = lines.slice(1).join("\n").trim();
  return rest ? { label: first, body: rest } : { label: "", body: first };
}

function YouCard({ text }) {
  const { label, body } = splitLabel(text);
  return (
    <div className="my-4 rounded-bzcard border border-bz-gold bg-bz-gold-tint p-4" data-testid="md-you">
      <div className="flex items-center justify-between gap-2 mb-1.5">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold">{label || "You say"}</p>
        <CopyButton text={body.replace(/^"|"$/g, "")} />
      </div>
      <p className="whitespace-pre-line text-[15.5px] leading-relaxed">{body}</p>
    </div>
  );
}

function ClientCard({ text }) {
  const { label, body } = splitLabel(text);
  return (
    <div className="my-4 rounded-bzcard border border-bz-line-strong bg-bz-raised p-4 sm:mr-8" data-testid="md-client">
      <p className="text-[12px] font-bold text-bz-muted mb-1.5">{label || "Client"}</p>
      <p className="whitespace-pre-line text-[15px] leading-relaxed italic">{body}</p>
    </div>
  );
}

function NextButton({ text }) {
  const { onNext, busy } = useContext(Ctx);
  const label = text.trim().split("\n")[0].trim();
  if (!onNext || !label) return null;
  return (
    <div className="my-4 no-print">
      <button type="button" disabled={busy} onClick={() => onNext(label)} data-testid="md-next"
        className="inline-flex items-center gap-2 min-h-[48px] px-5 rounded-full border border-bz-teal text-bz-teal font-bold text-[15px] hover:bg-bz-teal-tint disabled:opacity-50 text-left">
        {label}<ArrowRight className="w-4 h-4 shrink-0" aria-hidden />
      </button>
    </div>
  );
}

function Fence({ lang, text }) {
  if (lang === "ask") {
    return (
      <div className="my-4 rounded-bzcard border border-bz-gold bg-bz-gold-tint p-4">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold mb-1.5">Your turn — I need this from you</p>
        <div className="text-[15px]"><Markdown text={text} /></div>
      </div>
    );
  }
  if (lang === "banner") {
    return <div className="my-4 rounded-bzcard bg-bz-gold text-bz-on-accent font-extrabold px-4 py-3 text-[16px] whitespace-pre-line">{text}</div>;
  }
  if (lang === "steps") return <StepsCard text={text} />;
  if (lang === "you") return <YouCard text={text} />;
  if (lang === "client") return <ClientCard text={text} />;
  if (lang === "next") return <NextButton text={text} />;
  const isText = lang === "text" || !lang;
  return (
    <div className="my-4 rounded-bzcard border border-bz-line bg-bz-panel overflow-hidden">
      <div className="flex items-center justify-between px-3 py-1 border-b border-bz-line">
        <span className="text-[11px] font-medium uppercase tracking-[0.14em] text-bz-muted">{isText ? "Ready to copy" : lang}</span>
        <CopyButton text={text} />
      </div>
      <pre className={`p-3.5 overflow-x-auto text-[14px] leading-relaxed whitespace-pre-wrap ${isText ? "font-bz" : "font-bzmono text-[13px]"}`}>{text}</pre>
    </div>
  );
}

function TaskBox({ checked }) {
  const [on, setOn] = useState(!!checked);
  return (
    <input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)}
      className="mr-2 w-[18px] h-[18px] align-[-3px] accent-[var(--bz-gold)] cursor-pointer" aria-label="Done" />
  );
}

const components = {
  h1: ({ children }) => <h2 className="text-[22px] font-extrabold tracking-[-0.01em] mt-6 mb-2">{children}</h2>,
  h2: ({ children }) => <h3 className="text-[19px] font-extrabold mt-6 mb-2">{children}</h3>,
  h3: ({ children }) => <h4 className="text-[16px] font-bold mt-5 mb-1.5 text-bz-gold">{children}</h4>,
  h4: ({ children }) => <h5 className="text-[15px] font-bold mt-4 mb-1">{children}</h5>,
  p: ({ children }) => <p className="my-2.5 leading-relaxed">{children}</p>,
  ul: ({ className, children }) => (String(className || "").includes("contains-task-list")
    ? <ul className="my-2.5 space-y-1.5">{children}</ul>
    : <ul className="my-2.5 pl-5 list-disc space-y-1 marker:text-bz-gold">{children}</ul>),
  ol: ({ children }) => <ol className="my-2.5 pl-5 list-decimal space-y-1 marker:text-bz-gold marker:font-bold">{children}</ol>,
  li: ({ className, children }) => <li className={`leading-relaxed ${String(className || "").includes("task-list-item") ? "list-none" : ""}`}>{children}</li>,
  input: ({ type, checked }) => (type === "checkbox" ? <TaskBox checked={checked} /> : null),
  strong: ({ children }) => <strong className="font-bold text-bz-ink">{children}</strong>,
  a: ({ href, children }) => <a href={href} target="_blank" rel="noopener noreferrer" className="text-bz-gold underline underline-offset-2">{children}</a>,
  blockquote: ({ children }) => <blockquote className="my-3 border-l-[3px] border-bz-gold pl-4 text-bz-muted italic">{children}</blockquote>,
  hr: () => <hr className="my-5 border-bz-line" />,
  table: ({ children }) => <div className="my-4 overflow-x-auto rounded-bzcard border border-bz-line"><table className="min-w-full text-[14px]">{children}</table></div>,
  thead: ({ children }) => <thead className="bg-bz-raised">{children}</thead>,
  th: ({ children }) => <th className="text-left font-bold px-3 py-2 border-b border-bz-line align-top">{children}</th>,
  td: ({ children }) => <td className="px-3 py-2 border-b border-bz-line align-top">{children}</td>,
  code: ({ className, children }) => {
    const m = /language-(\w+)/.exec(className || "");
    const text = String(children || "").replace(/\n$/, "");
    if (m || text.includes("\n")) return <Fence lang={m ? m[1] : ""} text={text} />;
    return <code className="font-bzmono text-[13px] bg-bz-raised rounded px-1.5 py-0.5">{children}</code>;
  },
  pre: ({ children }) => <>{children}</>,
};

// onNext(text): makes ```next blocks into buttons that send `text` (pass it only for the latest reply).
export default function Markdown({ text, className = "", onNext = null, busy = false }) {
  const outer = useContext(Ctx);
  if (!text) return null;
  const value = onNext ? { onNext, busy } : outer;
  return (
    <Ctx.Provider value={value}>
      <div className={`text-[15px] text-bz-ink break-words ${className}`}>
        <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>
      </div>
    </Ctx.Provider>
  );
}
