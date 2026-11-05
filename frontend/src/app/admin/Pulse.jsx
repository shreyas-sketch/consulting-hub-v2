// Admin › Pulse: accounts, plan mix (free / ₹1,999 / L1 / L2), MRR, signups by day and source, tool use (7 days).
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import { inr, sdate } from "@/lib/format";
import { AXIS_TICK, C, TOOLTIP } from "../components/chart";
import { Card, Label, Note } from "../components/ui";
import { AdminLoadable, Kpi, useAdmin } from "./shared";

export function Bars({ rows, labelKey, valueKey = "count", label }) {
  const list = rows || [];
  const max = Math.max(1, ...list.map((r) => Number(r[valueKey]) || 0));
  if (!list.length) return <p className="text-sm text-bz-muted">No data yet.</p>;
  return (
    <ul className="space-y-2.5" aria-label={label}>
      {list.map((r) => (
        <li key={r[labelKey]}>
          <div className="flex justify-between text-[13.5px]"><span className="truncate pr-2">{r.__label || r[labelKey] || "—"}</span><span className="tabular font-bold text-bz-gold">{Number(r[valueKey] || 0).toLocaleString("en-IN")}</span></div>
          <div className="h-2 rounded-full bg-bz-line mt-1 overflow-hidden"><div className="h-full rounded-full bg-gradient-to-r from-bz-rule to-bz-gold-light" style={{ width: `${((Number(r[valueKey]) || 0) / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}

export default function Pulse() {
  const q = useAdmin("pulse");
  return (
    <AdminLoadable q={q} what="the pulse">
      {(d) => {
        const k = d.kpis || {};
        return (
          <div className="space-y-5">
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <Kpi label="Accounts" value={Number(k.users_total ?? 0).toLocaleString("en-IN")} sub={`${k.signups_today ?? 0} today · ${k.signups_7d ?? 0} in 7 days`} />
              <Kpi label="MRR (before GST)" value={inr(k.mrr_inr)} tone="gold" />
              <Kpi label="Paying" value={k.paid_conversion_pct != null ? `${k.paid_conversion_pct}%` : "—"} sub="of all accounts" />
              <Kpi label="Given by the team" value={k.granted_active} />
              <Kpi label="₹1,999 plan" value={k.member_active} sub={`${k.member_yearly ?? 0} yearly`} />
              <Kpi label="L1" value={k.l1_active} />
              <Kpi label="L2" value={k.l2_active} sub={`${k.l1_paused_for_l2 ?? 0} L1 paused`} />
              <Kpi label="Signups · 7 days" value={k.signups_7d} />
            </div>
            <Note>{d.mrr_note}</Note>
            <Card>
              <Label>Accounts by day</Label>
              {(d.signups_by_day || []).length ? (
                <div className="h-60 -mx-2">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={d.signups_by_day} margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
                      <CartesianGrid stroke={C.line} vertical={false} />
                      <XAxis dataKey="date" tick={AXIS_TICK} tickLine={false} axisLine={false} tickFormatter={sdate} minTickGap={20} />
                      <YAxis tick={AXIS_TICK} tickLine={false} axisLine={false} width={36} allowDecimals={false} />
                      <Tooltip {...TOOLTIP} cursor={{ fill: "var(--bz-raised)" }} labelFormatter={sdate} formatter={(v) => [v, "Accounts"]} />
                      <Bar dataKey="count" fill={C.gold} radius={[4, 4, 0, 0]} isAnimationActive={false} />
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              ) : <p className="text-sm text-bz-muted">No accounts yet.</p>}
            </Card>
            <div className="grid gap-4 md:grid-cols-3">
              <Card><Label>By source</Label><Bars rows={d.by_source} labelKey="source" label="Accounts by source" /></Card>
              <Card><Label>Plan mix</Label><Bars rows={(d.plan_mix || []).map((r) => ({ ...r, __label: r.label }))} labelKey="plan" label="Plan mix" /></Card>
              <Card><Label>Tool use · 7 days</Label><Bars rows={(d.tool_usage_7d || []).map((r) => ({ ...r, __label: `${r.tool} · ${r.users} people` }))} labelKey="tool" valueKey="uses" label="Tool use" /></Card>
            </div>
          </div>
        );
      }}
    </AdminLoadable>
  );
}
