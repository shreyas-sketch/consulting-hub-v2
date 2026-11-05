// /d/:id — the public diagnostic a prospect fills in. No login, no app shell, same dark look.
// 1-5 scale questions as five buttons, short answers as text, then name + phone or email. The prospect sees their
// score and a short read; the consultant gets the full report in their hub.
import { useState } from "react";
import { useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Para, ScoreRing } from "../components/common";
import { Button, Card, ErrorLine, Field, Input, Label, Note, Spinner, Textarea } from "../components/ui";

function Shell({ brand, children }) {
  return (
    <div className="min-h-screen font-bz text-bz-ink antialiased">
      <header className="border-b border-bz-line">
        <div className="mx-auto max-w-[680px] px-4 h-16 flex items-center">
          {brand?.name ? (
            <div className="min-w-0">
              <p className="text-[15px] font-extrabold truncate">{brand.name}</p>
              {brand.title && <p className="text-[12px] text-bz-muted truncate">{brand.title}</p>}
            </div>
          ) : <span />}
        </div>
      </header>
      <main className="mx-auto max-w-[680px] px-4 py-8">{children}</main>
    </div>
  );
}

function Scale({ q, value, onChange }) {
  return (
    <div>
      <div className="grid grid-cols-5 gap-2" role="radiogroup" aria-label={q.text}>
        {[1, 2, 3, 4, 5].map((n) => (
          <button key={n} type="button" role="radio" aria-checked={value === n} onClick={() => onChange(n)} data-testid={`d-${q.id}-${n}`}
            className={`min-h-[52px] rounded-bzbtn border text-[18px] font-extrabold tabular ${value === n ? "bg-bz-gold text-bz-on-accent border-bz-gold" : "bg-bz-panel border-bz-line hover:border-bz-line-strong"}`}>
            {n}
          </button>
        ))}
      </div>
      {(q.low || q.high) && (
        <div className="flex justify-between gap-3 mt-1.5 text-[12px] text-bz-muted"><span>1 = {q.low}</span><span className="text-right">5 = {q.high}</span></div>
      )}
    </div>
  );
}

export default function DiagnosticPublic() {
  const { id } = useParams();
  const q = useQuery({ queryKey: ["public-diag", id], retry: false, queryFn: async () => (await api.get(`/diagnostic/public/${id}`)).data });
  const [answers, setAnswers] = useState({});
  const [who, setWho] = useState({ name: "", company: "", phone: "", email: "" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [result, setResult] = useState(null);

  if (q.isLoading) return <Shell><Spinner /></Shell>;
  if (q.isError) {
    return (
      <Shell>
        <Card className="text-center py-10">
          <p className="text-[20px] font-extrabold">This check isn't open right now.</p>
          <p className="text-[15px] text-bz-muted mt-2">{q.error?.response?.status === 429 ? apiError(q.error) : "Please ask the person who shared it for a new link."}</p>
        </Card>
      </Shell>
    );
  }
  const d = q.data;
  const scale = d.questions.filter((x) => x.kind === "scale");
  const answered = scale.filter((x) => answers[x.id]).length;

  const submit = async (e) => {
    e.preventDefault();
    if (answered < scale.length) { setErr(`Please answer every 1–5 question (${scale.length - answered} left).`); return; }
    if (who.name.trim().length < 2) { setErr("Please add your name."); return; }
    if (!who.phone.trim() && !who.email.trim()) { setErr("Add your phone number or email so you can get your result."); return; }
    setErr(""); setBusy(true);
    try {
      setResult((await api.post(`/diagnostic/public/${id}/responses`, { ...who, answers })).data);
      window.scrollTo({ top: 0, behavior: "smooth" });
    } catch (e2) { setErr(apiError(e2)); } finally { setBusy(false); }
  };

  if (result) {
    return (
      <Shell brand={d.brand}>
        <Card className="rise-in text-center" data-testid="d-result">
          <Label className="text-center">{d.title}</Label>
          <ScoreRing value={result.pct} max={100} size={150} label="Your score" sub={result.band} />
          <Para text={result.thank_you} className="text-[16px] mt-5 text-left" />
          {(result.cta || result.cta_link) && (
            <div className="mt-6 pt-5 border-t border-bz-line text-left">
              {result.cta && <p className="text-[15px] font-bold">{result.cta}</p>}
              {result.cta_link && (
                <a href={result.cta_link} target="_blank" rel="noopener noreferrer" data-testid="d-cta"
                  className="mt-3 inline-flex w-full items-center justify-center min-h-[52px] px-6 rounded-bzbtn bg-bz-gold text-bz-on-accent font-extrabold text-[16px] shadow-goldglow">
                  {result.brand?.name ? `Talk to ${result.brand.name.split(" ")[0]}` : "Book a conversation"}
                </a>
              )}
            </div>
          )}
        </Card>
        <Note className="text-center mt-4">Your answers go only to {d.brand?.name || "the consultant who shared this"}.</Note>
      </Shell>
    );
  }

  return (
    <Shell brand={d.brand}>
      <h1 className="font-display text-[28px] sm:text-[36px] font-[450] leading-[1.08] tracking-[-0.02em]">{d.title}</h1>
      {d.intro && <p className="mt-3 text-[16px] font-light leading-relaxed text-bz-muted">{d.intro}</p>}
      <form onSubmit={submit} noValidate className="mt-6 space-y-3">
        {d.questions.map((x, i) => (
          <Card key={x.id}>
            <p className="text-[13px] font-extrabold text-bz-gold">{i + 1} of {d.questions.length}</p>
            <p className="text-[17px] font-bold mt-1 mb-3 leading-snug">{x.text}</p>
            {x.kind === "scale"
              ? <Scale q={x} value={answers[x.id]} onChange={(n) => setAnswers({ ...answers, [x.id]: n })} />
              : <Textarea rows={3} value={answers[x.id] || ""} onChange={(e) => setAnswers({ ...answers, [x.id]: e.target.value })} maxLength={500} className="min-h-[90px]" placeholder="A line or two is enough" data-testid={`d-${x.id}`} />}
          </Card>
        ))}
        <Card>
          <Label>Where should your result go?</Label>
          <div className="space-y-3">
            <Field label="Your name"><Input value={who.name} onChange={(e) => setWho({ ...who, name: e.target.value })} maxLength={80} autoComplete="name" data-testid="d-name" /></Field>
            <Field label="Company (optional)"><Input value={who.company} onChange={(e) => setWho({ ...who, company: e.target.value })} maxLength={120} autoComplete="organization" data-testid="d-company" /></Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="Phone"><Input type="tel" inputMode="tel" value={who.phone} onChange={(e) => setWho({ ...who, phone: e.target.value })} maxLength={20} autoComplete="tel" data-testid="d-phone" /></Field>
              <Field label="Or email"><Input type="email" inputMode="email" value={who.email} onChange={(e) => setWho({ ...who, email: e.target.value })} maxLength={160} autoComplete="email" data-testid="d-email" /></Field>
            </div>
          </div>
        </Card>
        <ErrorLine>{err}</ErrorLine>
        <Button type="submit" className="w-full" loading={busy} data-testid="d-submit">See my result</Button>
        <Note className="text-center">{answered} of {scale.length} rated. Takes about three minutes.</Note>
      </form>
    </Shell>
  );
}
