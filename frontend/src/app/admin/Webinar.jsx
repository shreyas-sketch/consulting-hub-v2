// Admin › Webinar: date range → report + "Download group-session list (CSV)" (accounts that haven't bought).
import { useState } from "react";
import { Download } from "lucide-react";
import { API_BASE } from "@/lib/api";
import { Card, Field, Input, Label } from "../components/ui";
import { AdminLoadable, Kpi, Table, useAdmin } from "./shared";

// Calendar date in India (the backend reads these dates as IST days).
const iso = (d) => new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata" }).format(d);

export default function Webinar() {
  const today = new Date();
  const [range, setRange] = useState({ start: iso(today), end: iso(today) });
  const ok = range.start && range.end && range.start <= range.end;
  const q = useAdmin("webinar", range, { enabled: !!ok });
  const csv = `${API_BASE}/admin/webinar/group-session.csv?start=${encodeURIComponent(range.start)}&end=${encodeURIComponent(range.end)}`;
  return (
    <div className="space-y-4">
      <Card>
        <div className="grid grid-cols-2 gap-3 max-w-[460px]">
          <Field label="From"><Input type="date" value={range.start} onChange={(e) => setRange({ ...range, start: e.target.value })} data-testid="webinar-start" /></Field>
          <Field label="To"><Input type="date" value={range.end} onChange={(e) => setRange({ ...range, end: e.target.value })} data-testid="webinar-end" /></Field>
        </div>
        {!ok && <p className="text-sm text-bz-miss mt-2">The start date must be on or before the end date.</p>}
        <p className="text-[13px] text-bz-muted mt-2">Accounts opened in this window (the webinar day).</p>
      </Card>
      {ok && (
        <AdminLoadable q={q} what="the webinar report">
          {(d) => (
            <div className="space-y-4">
              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <Kpi label="Accounts" value={d.accounts} />
                <Kpi label="Used a tool" value={d.used_a_tool} sub={d.accounts ? `${Math.round((d.used_a_tool / d.accounts) * 100)}%` : ""} />
                <Kpi label="Bought L1" value={d.bought?.l1 ?? 0} tone="gold" />
                <Kpi label="Bought ₹1,999" value={d.bought?.member ?? 0} />
                <Kpi label="Group session list" value={d.group_session_list} sub="have an account, not bought" />
              </div>
              <a href={csv} className="inline-flex items-center gap-2 min-h-[52px] px-6 rounded-full bg-bz-gold text-bz-on-accent font-extrabold text-[15px]" data-testid="webinar-csv">
                <Download className="w-4 h-4" aria-hidden /> Download group-session list (CSV)
              </a>
              <Card>
                <Label>Tool use</Label>
                <Table rows={d.tool_usage} cols={[
                  { key: "tool", label: "Tool" },
                  { key: "users", label: "People", right: true },
                  { key: "uses", label: "Uses", right: true },
                ]} empty="No tool use in this window." />
              </Card>
            </div>
          )}
        </AdminLoadable>
      )}
    </div>
  );
}
