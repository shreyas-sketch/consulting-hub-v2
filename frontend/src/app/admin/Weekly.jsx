// Admin › Weekly case: the cases made from real news each Monday 06:30 IST. Make one now, switch one off,
// see how many members answered. Older weeks stay on as practice cases.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip, Label, Note, OkLine } from "../components/ui";
import { AdminLoadable, Kpi, Table, asList, dt, useAdmin } from "./shared";

export default function AdminWeekly() {
  const qc = useQueryClient();
  const q = useAdmin("weekly");
  const [busy, setBusy] = useState("");
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const refresh = () => { qc.invalidateQueries({ queryKey: ["admin", "weekly"] }); qc.invalidateQueries({ queryKey: ["admin", "cases"] }); };

  const generate = async () => {
    if (!window.confirm("Make a new weekly case now? Paid members get an inbox alert (once a week).")) return;
    setErr(""); setOk(""); setBusy("gen");
    try {
      const { data } = await api.post("/admin/weekly/generate", null, { timeout: 120000 });
      setOk(`Published: ${data.item.company} — ${data.item.title}. Alerts sent: ${data.alerts}.`);
      refresh();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };
  const toggle = async (r) => {
    setErr(""); setBusy(r.id);
    try { await api.post(`/admin/weekly/${r.id}/active`, { active: !r.active }); refresh(); } catch (e) { setErr(apiError(e)); } finally { setBusy(""); }
  };

  return (
    <div className="space-y-4">
      <AdminLoadable q={q} what="the weekly cases">
        {(d) => {
          const rows = asList(d);
          const last = d.last_run;
          return (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Kpi label="Schedule" value={d.schedule || "—"} />
                <Kpi label="This week" value={d.this_week || "—"} />
                <Kpi label="Cases made" value={rows.length} tone="gold" />
                <Kpi label="Answers" value={rows.reduce((a, r) => a + (r.answers || 0), 0)} />
              </div>
              <Card>
                <Label>Make one now</Label>
                <p className="text-[14px] text-bz-muted">Searches Indian business news, picks one story and writes the case with a model answer. If the case fails the checks, nothing is published.</p>
                {last && <Note className="mt-2">Last scheduled run: {dt(last.at)} · {last.ok ? "ok" : "failed"}{last.result && typeof last.result === "object" ? ` · ${last.result.published ? `published ${last.result.company || ""}` : `skipped: ${last.result.skipped || ""}`}` : last.result ? ` · ${last.result}` : ""}</Note>}
                {err && <p className="text-sm text-bz-miss mt-2" role="alert">{err}</p>}
                <OkLine>{ok}</OkLine>
                <Button className="mt-3" loading={busy === "gen"} onClick={generate} data-testid="weekly-generate">Make a weekly case now</Button>
              </Card>
              <Card className="px-0 sm:px-5 py-2">
                <Table rows={rows} empty="No weekly cases yet. The first one is made on Monday at 06:30 IST, or press the button above." cols={[
                  { key: "week", label: "Week" },
                  { key: "title", label: "Case", wrap: true, render: (r) => (
                    <span className="block min-w-[220px]">
                      <b>{r.title}</b>
                      <span className="block text-bz-muted text-[13px]">{r.company} · {r.industry}{r.city ? ` · ${r.city}` : ""}</span>
                    </span>
                  ) },
                  { key: "source", label: "Source", wrap: true, render: (r) => r.source?.url ? (
                    <a href={r.source.url} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-1 text-bz-gold font-bold text-[13px] max-w-[260px]">
                      <span className="line-clamp-2">{r.source.title}</span><ExternalLink className="w-3.5 h-3.5 mt-0.5 shrink-0" aria-hidden />
                    </a>
                  ) : "—" },
                  { key: "answers", label: "Answers", right: true },
                  { key: "status", label: "Status", render: (r) => (
                    <span className="flex flex-wrap gap-1">
                      {r.current ? <Chip tone="solid">This week</Chip> : <Chip>Practice</Chip>}
                      {!r.active && <Chip tone="miss">Off</Chip>}
                      {r.test && <Chip tone="teal">Test</Chip>}
                    </span>
                  ) },
                  { key: "created_at", label: "Made", render: (r) => dt(r.created_at) },
                  { key: "_act", label: "", render: (r) => (
                    <Button variant={r.active ? "danger" : "small"} loading={busy === r.id} onClick={() => toggle(r)} data-testid={`weekly-toggle-${r.id}`}>
                      {r.active ? "Switch off" : "Switch on"}
                    </Button>
                  ) },
                ]} />
              </Card>
            </>
          );
        }}
      </AdminLoadable>
    </div>
  );
}
