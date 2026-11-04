// Small primitives in the Akshat Dani design system: dark panels with 14px radius, Manrope only,
// gold = the signal (kickers, key phrase, ₹ figures, primary button), teal = AI only, red = errors only.
import { Link } from "react-router-dom";
import { AlertTriangle, Loader2, RotateCw, Sparkles } from "lucide-react";
import { apiError } from "@/lib/api";

export function Card({ className = "", inset = false, children, ...rest }) {
  return (
    <section
      className={`rounded-bzcard p-4 sm:p-5 border ${inset ? "bg-bz-raised border-bz-line" : "bg-bz-card border-bz-line"} ${className}`}
      {...rest}
    >
      {children}
    </section>
  );
}

// Kicker: caps, Medium, 0.18em, gold (teal on AI screens). One per screen as the page kicker; small labels reuse it.
export function Label({ children, className = "", tone = "gold", as: As = "div" }) {
  const color = { gold: "text-bz-gold", muted: "text-bz-muted", teal: "text-bz-teal", miss: "text-bz-miss" }[tone] || "text-bz-gold";
  return <As className={`text-[12px] font-medium uppercase tracking-kicker ${color} mb-2 ${className}`}>{children}</As>;
}

// Kicker + ExtraBold sentence-case headline with exactly one key phrase in gold (teal on AI screens) + Light sub-line.
//   <PageHeader kicker="Starting point" title="Find the niche" accent="that pays you" sub="…" />
export function PageHeader({ kicker, title, accent, ai = false, sub, right = null }) {
  return (
    <header className="mb-6 md:mb-8">
      <div className="flex items-center justify-between gap-4">
        {kicker ? <Label tone={ai ? "teal" : "gold"} className="mb-0">{kicker}</Label> : <span />}
        {right}
      </div>
      {title ? (
        <h1 className="mt-3 text-[28px] sm:text-[36px] lg:text-[40px] font-extrabold leading-[1.06] tracking-[-0.02em]">
          {title}{accent ? <> <span className={ai ? "text-bz-teal" : "text-bz-gold"}>{accent}</span></> : null}
        </h1>
      ) : null}
      {sub ? <p className="mt-3 text-[16px] font-light leading-relaxed text-bz-muted max-w-[640px]">{sub}</p> : null}
    </header>
  );
}

const BTN_BASE =
  "inline-flex items-center justify-center gap-2 rounded-full transition-[opacity,background-color,border-color] duration-150 disabled:opacity-50 disabled:cursor-not-allowed select-none text-center";
const BTN_STYLES = {
  primary: "min-h-[52px] px-6 py-3 bg-bz-gold text-bz-on-accent font-extrabold text-[16px] hover:opacity-90 shadow-goldglow",
  secondary: "min-h-[52px] px-6 py-3 bg-transparent border border-bz-rule text-bz-ink font-bold text-[15px] hover:border-bz-gold",
  ai: "min-h-[52px] px-6 py-3 bg-transparent border border-bz-teal text-bz-teal font-bold text-[15px] hover:bg-bz-teal-tint",
  quiet: "min-h-[44px] px-4 py-2 bg-bz-raised border border-bz-line text-bz-ink font-bold text-[14px] hover:border-bz-line-strong",
  danger: "min-h-[44px] px-5 py-2.5 bg-transparent border border-bz-miss text-bz-miss font-bold text-[14px] hover:bg-bz-miss-tint",
  small: "min-h-[40px] px-4 py-1.5 border border-bz-line bg-bz-raised text-bz-ink font-bold text-[13px] hover:border-bz-line-strong",
  link: "bg-transparent text-bz-gold font-bold text-[15px] px-0 py-1 rounded-none",
};

export function Button({ variant = "primary", loading = false, className = "", children, type = "button", ...rest }) {
  return (
    <button type={type} className={`${BTN_BASE} ${BTN_STYLES[variant]} ${className}`} disabled={loading || rest.disabled} {...rest}>
      {loading && <Loader2 className="w-4 h-4 animate-spin" aria-hidden />}
      {!loading && variant === "ai" && <Sparkles className="w-4 h-4" strokeWidth={1.9} aria-hidden />}
      {children}
    </button>
  );
}

export function LinkButton({ to, variant = "primary", className = "", children, ...rest }) {
  return <Link to={to} className={`${BTN_BASE} ${BTN_STYLES[variant]} ${className}`} {...rest}>{children}</Link>;
}

export function Spinner({ label = "Loading" }) {
  return (
    <div className="flex items-center gap-2 text-bz-muted text-sm py-6 justify-center" role="status">
      <Loader2 className="w-4 h-4 animate-spin text-bz-gold" aria-hidden /> {label}
    </div>
  );
}

// "Thinking" state for AI work: three teal dots with a soft pulse.
export function Thinking({ label = "Working on it" }) {
  return (
    <div className="flex items-center gap-3 text-bz-teal text-[14px] font-medium py-4" role="status">
      <span className="flex gap-1" aria-hidden>
        {[0, 1, 2].map((i) => <span key={i} className="ai-dot w-2 h-2 rounded-full bg-bz-teal" style={{ animationDelay: `${i * 160}ms` }} />)}
      </span>
      {label}
    </div>
  );
}

// Frame for anything the AI wrote: 1px teal border, AI label.
export function AiFrame({ title = "AI", children, className = "", right = null }) {
  return (
    <section className={`rounded-bzframe border border-[rgba(46,211,183,0.55)] bg-bz-card p-4 sm:p-5 shadow-tealglow ${className}`}>
      <div className="flex items-center justify-between gap-3 mb-3">
        <span className="inline-flex items-center gap-1.5 text-[12px] font-medium uppercase tracking-kicker text-bz-teal">
          <Sparkles className="w-3.5 h-3.5" strokeWidth={1.9} aria-hidden /> {title}
        </span>
        {right}
      </div>
      {children}
    </section>
  );
}

export function Skeleton({ lines = 3, className = "" }) {
  return (
    <div className={`space-y-3 ${className}`} aria-busy="true" aria-label="Loading">
      {Array.from({ length: lines }).map((_, i) => (
        <div key={i} className="skeleton h-5" style={{ width: `${100 - (i % 3) * 18}%` }} />
      ))}
    </div>
  );
}

export function SkeletonCard({ lines = 3 }) {
  return <Card><Skeleton lines={lines} /></Card>;
}

export function ErrorCard({ error, onRetry, what = "this" }) {
  return (
    <Card inset className="flex items-start gap-3" role="alert">
      <AlertTriangle className="w-5 h-5 text-bz-miss shrink-0 mt-0.5" aria-hidden />
      <div className="min-w-0 flex-1">
        <p className="font-bold">Could not load {what}.</p>
        <p className="text-sm text-bz-muted mt-0.5">{apiError(error)}</p>
        {onRetry && (
          <button type="button" onClick={onRetry} className="mt-2 inline-flex items-center gap-1.5 text-sm font-bold text-bz-gold min-h-[40px]">
            <RotateCw className="w-3.5 h-3.5" aria-hidden /> Try again
          </button>
        )}
      </div>
    </Card>
  );
}

export function Empty({ title, sub, action = null, icon: Icon }) {
  return (
    <Card inset className="text-center py-8">
      {Icon && <Icon className="w-7 h-7 mx-auto text-bz-gold mb-2" strokeWidth={1.75} aria-hidden />}
      <p className="font-bold text-[16px]">{title}</p>
      {sub && <p className="text-sm text-bz-muted mt-1 max-w-[420px] mx-auto">{sub}</p>}
      {action && <div className="mt-4 flex justify-center">{action}</div>}
    </Card>
  );
}

// Render a react-query result: skeleton while loading, error card with retry, then children(data).
export function Loadable({ q, what, lines = 3, children }) {
  if (q.isLoading) return <SkeletonCard lines={lines} />;
  if (q.isError) return <ErrorCard error={q.error} onRetry={() => q.refetch()} what={what} />;
  return children(q.data || {});
}

export function Sheet({ open, onClose, title, children, wide = false }) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center" role="dialog" aria-modal="true" aria-label={title}>
      <button type="button" className="absolute inset-0 bg-bz-scrim cursor-default" aria-label="Close" onClick={onClose} />
      <div className={`relative w-full ${wide ? "sm:max-w-[820px]" : "sm:max-w-[560px]"} max-h-[92vh] overflow-y-auto bg-bz-panel rounded-t-[18px] sm:rounded-bzframe border border-bz-line shadow-bzsheet pb-[env(safe-area-inset-bottom)]`}>
        <div className="sticky top-0 z-10 bg-bz-panel flex items-center justify-between px-5 pt-4 pb-3 border-b border-bz-line">
          <h2 className="text-[20px] font-extrabold tracking-[-0.01em]">{title}</h2>
          <button type="button" onClick={onClose} className="text-[13px] font-bold text-bz-muted px-3 min-h-[40px] rounded-full hover:bg-bz-raised">Close</button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  );
}

const CHIP_TONES = {
  muted: "bg-bz-raised text-bz-muted",
  gold: "bg-bz-gold-tint text-bz-gold",
  solid: "bg-bz-gold text-bz-on-accent font-extrabold",
  teal: "bg-bz-teal-tint text-bz-teal",
  miss: "bg-bz-miss-tint text-bz-miss",
};
export function Chip({ tone = "muted", children, className = "" }) {
  return (
    <span className={`inline-flex items-center gap-1 text-[11.5px] font-bold px-2.5 py-1 rounded-full whitespace-nowrap ${CHIP_TONES[tone] || CHIP_TONES.muted} ${className}`}>
      {children}
    </span>
  );
}

// One tappable row: title, one-line subtitle, something on the right.
export function RowLink({ to, href, onClick, title, sub, right, testid, icon: Icon }) {
  const inner = (
    <>
      {Icon && <Icon className="w-5 h-5 text-bz-gold shrink-0" strokeWidth={1.75} aria-hidden />}
      <span className="flex flex-col gap-0.5 min-w-0 flex-1">
        <span className="text-[15px] font-bold truncate">{title}</span>
        {sub && <span className="text-[13px] text-bz-muted truncate">{sub}</span>}
      </span>
      {right ?? <svg className="w-5 h-5 text-bz-gold shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden><path d="M9 6l6 6-6 6" /></svg>}
    </>
  );
  const cls = "w-full flex items-center gap-3 py-3.5 border-b border-bz-line last:border-0 text-left text-bz-ink hover:bg-bz-raised min-h-[56px]";
  if (to) return <Link to={to} className={cls} data-testid={testid}>{inner}</Link>;
  if (href) return <a href={href} className={cls} data-testid={testid}>{inner}</a>;
  return <button type="button" onClick={onClick} className={cls} data-testid={testid}>{inner}</button>;
}

// ---- form controls -------------------------------------------------------
export const inputCls =
  "w-full min-h-[48px] rounded-bzbtn border border-bz-line bg-bz-panel text-bz-ink px-3.5 py-2.5 text-[16px] " +
  "outline-none focus:border-bz-gold";
export const textareaCls = `${inputCls} min-h-[120px] leading-relaxed resize-y`;

export function Field({ label, hint, children, className = "" }) {
  return (
    <label className={`block ${className}`}>
      <span className="block text-[12px] font-medium uppercase tracking-[0.14em] text-bz-muted mb-1.5">{label}</span>
      {children}
      {hint && <span className="block text-[13px] text-bz-muted mt-1.5">{hint}</span>}
    </label>
  );
}

export function Input({ className = "", ...rest }) {
  return <input className={`${inputCls} ${className}`} {...rest} />;
}

export function Textarea({ className = "", ...rest }) {
  return <textarea className={`${textareaCls} ${className}`} {...rest} />;
}

// Rupee amount input with a ₹ prefix. Screens check the amount themselves; the API answers with a plain sentence.
export function MoneyInput({ value, onChange, className = "", ...rest }) {
  return (
    <div className={`relative ${className}`}>
      <span className="absolute left-3.5 top-1/2 -translate-y-1/2 text-bz-gold text-[16px] font-bold" aria-hidden>₹</span>
      <input type="number" inputMode="numeric" min="0" step="any" value={value} onChange={(e) => onChange(e.target.value === "" ? "" : Number(e.target.value))}
        className={`${inputCls} pl-8 tabular`} {...rest} />
    </div>
  );
}

export function Select({ className = "", children, ...rest }) {
  return <select className={`${inputCls} ${className}`} {...rest}>{children}</select>;
}

// Row of pill options.
export function Segmented({ options, value, onChange, label, testid, className = "" }) {
  return (
    <div className={`flex flex-wrap gap-2 ${className}`} role="group" aria-label={label}>
      {options.map((o) => {
        const v = typeof o === "object" ? o.value : o;
        const l = typeof o === "object" ? o.label : o;
        const on = value === v;
        return (
          <button key={String(v)} type="button" onClick={() => onChange(v)} aria-pressed={on}
            data-testid={testid ? `${testid}-${v}` : undefined}
            className={`min-h-[44px] px-4 rounded-full text-[14px] font-bold border ${on ? "bg-bz-gold text-bz-on-accent border-bz-gold" : "bg-bz-panel text-bz-ink border-bz-line hover:border-bz-line-strong"}`}>
            {l}
          </button>
        );
      })}
    </div>
  );
}

// Thin meter 0–100: gold gradient fill (teal while AI is working).
export function Meter({ value = 0, tone = "gold", className = "", label }) {
  const v = Math.max(0, Math.min(100, Number(value) || 0));
  const fill = tone === "teal" ? "bg-bz-teal" : tone === "miss" ? "bg-bz-miss" : "bg-gradient-to-r from-[#8F7635] to-[#F0D98A]";
  return (
    <div className={`h-2.5 rounded-full bg-bz-line overflow-hidden ${className}`} role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={v} aria-label={label}>
      <div className={`h-full rounded-full ${fill}`} style={{ width: `${v}%` }} />
    </div>
  );
}

// Stat tile: kicker label + gold hero number + one-line context.
export function Stat({ label, value, sub, big = false }) {
  return (
    <div className="rounded-bzcard border border-bz-line bg-bz-card px-4 py-3.5 min-w-0">
      <div className="text-[11.5px] font-medium uppercase tracking-[0.12em] text-bz-muted leading-snug">{label}</div>
      <div className={`${big ? "text-[34px]" : "text-[24px]"} font-extrabold tracking-[-0.03em] text-bz-gold mt-1 tabular truncate`}>{value}</div>
      {sub && <div className="text-[13px] text-bz-muted mt-0.5 leading-snug">{sub}</div>}
    </div>
  );
}

export function Note({ children, className = "" }) {
  if (!children) return null;
  return <p className={`text-[13px] leading-relaxed text-bz-muted ${className}`}>{children}</p>;
}

export function ErrorLine({ children }) {
  if (!children) return null;
  return <p className="text-sm text-bz-miss mt-2" role="alert">{children}</p>;
}

export function OkLine({ children }) {
  if (!children) return null;
  return <p className="text-sm text-bz-gold font-bold mt-2" role="status">{children}</p>;
}

// Numbered step: 34px outlined circle, bold title, muted description.
export function Step({ n, title, children, ai = false }) {
  return (
    <div className="flex gap-3">
      <span className={`w-[34px] h-[34px] shrink-0 rounded-full border grid place-items-center text-[14px] font-extrabold ${ai ? "border-bz-teal text-bz-teal" : "border-bz-gold text-bz-gold"}`}>{n}</span>
      <div className="min-w-0 pt-1">
        <p className="font-bold text-[15px]">{title}</p>
        {children && <div className="text-[14px] text-bz-muted mt-0.5 leading-relaxed">{children}</div>}
      </div>
    </div>
  );
}
