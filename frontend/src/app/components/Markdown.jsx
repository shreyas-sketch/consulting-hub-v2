// Markdown for AI replies (GPT tools, Akshat AI, recaps, packs, proposals). Dark theme, Manrope, gold/teal accents.
// Special fenced blocks (same as the current hub):
//   ```text  → copy card with a Copy button        ```ask  → "Your turn — I need this from you" card
//   ```banner → gold banner                         anything else → code block (JetBrains Mono) with Copy
// Tables scroll sideways inside their own box on a phone; the page never does.
import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { Check, Copy } from "lucide-react";

export function CopyButton({ text, label = "Copy", className = "" }) {
  const [ok, setOk] = useState(false);
  return (
    <button type="button" className={`inline-flex items-center gap-1 text-[12px] font-bold text-bz-gold min-h-[36px] px-2 ${className}`}
      onClick={async () => { try { await navigator.clipboard.writeText(text); setOk(true); setTimeout(() => setOk(false), 1500); } catch { /* blocked */ } }}>
      {ok ? <Check className="w-3.5 h-3.5" aria-hidden /> : <Copy className="w-3.5 h-3.5" aria-hidden />}{ok ? "Copied" : label}
    </button>
  );
}

function Fence({ lang, text }) {
  if (lang === "ask") {
    return (
      <div className="my-4 rounded-bzcard border border-bz-gold bg-bz-gold-tint p-4">
        <p className="text-[12px] font-medium uppercase tracking-kicker text-bz-gold mb-1.5">Your turn — I need this from you</p>
        <p className="whitespace-pre-line text-[15px]">{text}</p>
      </div>
    );
  }
  if (lang === "banner") {
    return <div className="my-4 rounded-bzcard bg-bz-gold text-bz-on-accent font-extrabold px-4 py-3 text-[16px] whitespace-pre-line">{text}</div>;
  }
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

const components = {
  h1: ({ children }) => <h2 className="text-[22px] font-extrabold tracking-[-0.01em] mt-6 mb-2">{children}</h2>,
  h2: ({ children }) => <h3 className="text-[19px] font-extrabold mt-6 mb-2">{children}</h3>,
  h3: ({ children }) => <h4 className="text-[16px] font-bold mt-5 mb-1.5 text-bz-gold">{children}</h4>,
  h4: ({ children }) => <h5 className="text-[15px] font-bold mt-4 mb-1">{children}</h5>,
  p: ({ children }) => <p className="my-2.5 leading-relaxed">{children}</p>,
  ul: ({ children }) => <ul className="my-2.5 pl-5 list-disc space-y-1 marker:text-bz-gold">{children}</ul>,
  ol: ({ children }) => <ol className="my-2.5 pl-5 list-decimal space-y-1 marker:text-bz-gold marker:font-bold">{children}</ol>,
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
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

export default function Markdown({ text, className = "" }) {
  if (!text) return null;
  return (
    <div className={`text-[15px] text-bz-ink break-words ${className}`}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>{text}</ReactMarkdown>
    </div>
  );
}
