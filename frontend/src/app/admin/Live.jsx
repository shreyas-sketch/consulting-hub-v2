// Admin › Live: for the team during the webinar. Refreshes every 30 seconds.
import { Card, Label } from "../components/ui";
import { AdminLoadable, Kpi, useAdmin } from "./shared";
import { Bars } from "./Pulse";

export default function Live() {
  const q = useAdmin("live", null, { refetchInterval: 30_000 });
  return (
    <AdminLoadable q={q} what="live numbers">
      {(d) => (
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3 max-w-[520px]">
            <Kpi label="New accounts · 15 min" value={d.accounts_15m} tone="gold" />
            <Kpi label="New accounts · today" value={d.accounts_today} />
          </div>
          <div className="grid gap-4 md:grid-cols-2">
            <Card><Label>Tools · last 15 min</Label><Bars rows={(d.tools_15m || []).map((r) => ({ ...r, __label: r.tool }))} labelKey="tool" valueKey="users" label="People per tool, last 15 minutes" /></Card>
            <Card><Label>Tools · today</Label><Bars rows={(d.tools_today || []).map((r) => ({ ...r, __label: r.tool }))} labelKey="tool" valueKey="users" label="People per tool, today" /></Card>
          </div>
          <p className="text-[13px] text-bz-muted">Counts people, not clicks. Updates every 30 seconds.</p>
        </div>
      )}
    </AdminLoadable>
  );
}
