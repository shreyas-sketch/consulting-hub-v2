// Admin › Website domains: own domains members asked for. A member's domain is only a request until the team connects
// it here: add it in Railway (service › Settings › Domains) so it gets a certificate, check the record points to us,
// then press Connect. A domain can be connected to one site only. When a member's plan drops below L1 the site stops
// showing on the domain at once, and the domain is freed 30 days later.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip, ErrorLine, Note, OkLine } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

function RecordCell({ r }) {
  if (!r.check) return <span className="text-bz-muted">Not checked</span>;
  return (
    <span className="block">
      {r.check.ok ? <Chip tone="gold">Points to us</Chip> : <Chip tone="miss">Not yet</Chip>}
      <span className="block text-[12px] text-bz-muted mt-1">{dt(r.check.at)}</span>
    </span>
  );
}

function StatusCell({ r }) {
  if (r.domain_status === "connected") {
    return (
      <span className="block">
        <Chip tone="gold">Connected</Chip>
        {r.lapsed_at && <span className="block text-[12px] text-bz-miss mt-1">Plan ended. Freed on {dt(r.release_at)}</span>}
      </span>
    );
  }
  return (
    <span className="block">
      <Chip tone="muted">Request</Chip>
      {r.taken_by && <span className="block text-[12px] text-bz-miss mt-1">Connected to /s/{r.taken_by}</span>}
    </span>
  );
}

export default function AdminDomains() {
  const qc = useQueryClient();
  const q = useAdmin("website/domains");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const [ok, setOk] = useState("");
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "website/domains"] });
  const set = async (r, status) => {
    if (status === "pending" && !window.confirm(`Disconnect ${r.domain}? The member's site stops showing on it.`)) return;
    setBusy(r.site_id); setErr(""); setOk("");
    try {
      await api.post(`/admin/website/domains/${r.site_id}`, { status });
      setOk(status === "connected" ? `${r.domain} is connected.` : `${r.domain} is disconnected.`);
      refresh();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  const check = async (r) => {
    setBusy(`c-${r.site_id}`); setErr(""); setOk("");
    try {
      const { data } = await api.post(`/admin/website/domains/${r.site_id}/check`);
      setOk(data.ok ? `${r.domain} points to us.` : `${r.domain} doesn't point to us yet${data.found?.length ? ` (it points to ${data.found.join(", ")})` : ""}.`);
      refresh();
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  return (
    <AdminLoadable q={q} what="website domains">
      {(d) => (
        <div className="space-y-4">
          <Note>
            A member's domain is only a request until you connect it. Nothing shows on it before that. To connect one:
            check the record points to <b>{d.target || "the app's address"}</b>, add the domain in Railway (service ›
            Settings › Domains) so it gets a certificate, then press Connect. A domain can be connected to one site only.
          </Note>
          <ErrorLine>{err}</ErrorLine>
          <OkLine>{ok}</OkLine>
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} empty="No member has asked for a domain yet." cols={[
              { key: "domain", label: "Domain", wrap: true, render: (r) => <span className="block min-w-[180px]"><b className="break-all">{r.domain}</b><span className="block text-[12px] text-bz-muted">/s/{r.slug}</span></span> },
              { key: "name", label: "Member", wrap: true, render: (r) => <span className="block">{r.name || "—"}<span className="block text-[12px] text-bz-muted">{r.phone || ""}</span></span> },
              { key: "status", label: "Status", wrap: true, render: (r) => <StatusCell r={r} /> },
              { key: "check", label: "Record", render: (r) => <RecordCell r={r} /> },
              { key: "published", label: "Site", render: (r) => (r.published ? "Published" : "Draft") },
              { key: "at", label: "Asked", render: (r) => dt(r.at) },
              { key: "act", label: "", render: (r) => (
                <span className="flex flex-wrap gap-2">
                  <Button variant="small" onClick={() => check(r)} loading={busy === `c-${r.site_id}`} data-testid={`domain-check-${r.site_id}`}>Check record</Button>
                  {r.domain_status === "connected"
                    ? <Button variant="small" onClick={() => set(r, "pending")} loading={busy === r.site_id} data-testid={`domain-wait-${r.site_id}`}>Disconnect</Button>
                    : <Button variant="small" onClick={() => set(r, "connected")} loading={busy === r.site_id} disabled={!!r.taken_by} data-testid={`domain-ok-${r.site_id}`}>Connect</Button>}
                </span>
              ) },
            ]} />
          </Card>
        </div>
      )}
    </AdminLoadable>
  );
}
