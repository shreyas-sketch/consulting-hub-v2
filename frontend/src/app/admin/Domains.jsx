// Admin › Website domains: members who connected their own domain. The team adds each one to the host
// (Railway › service › Settings › Domains) so it gets a certificate, then marks it connected here.
import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError } from "@/lib/api";
import { Button, Card, Chip, ErrorLine, Note } from "../components/ui";
import { AdminLoadable, asList, dt, Table, useAdmin } from "./shared";

export default function AdminDomains() {
  const qc = useQueryClient();
  const q = useAdmin("website/domains");
  const [busy, setBusy] = useState(null);
  const [err, setErr] = useState("");
  const set = async (r, status) => {
    setBusy(r.site_id); setErr("");
    try {
      await api.post(`/admin/website/domains/${r.site_id}`, { status });
      qc.invalidateQueries({ queryKey: ["admin", "website/domains"] });
    } catch (e) { setErr(apiError(e)); } finally { setBusy(null); }
  };
  return (
    <AdminLoadable q={q} what="website domains">
      {(d) => (
        <div className="space-y-4">
          <Note>
            When a member adds their own domain, add it in Railway too (service › Settings › Domains) so it gets a
            certificate. Their CNAME should point to <b>{d.target || "the app's address"}</b>. Then mark it connected.
          </Note>
          <ErrorLine>{err}</ErrorLine>
          <Card className="px-0 sm:px-5 py-2">
            <Table rows={asList(d)} empty="No member has added a domain yet." cols={[
              { key: "domain", label: "Domain", wrap: true, render: (r) => <span><b>{r.domain}</b><span className="block text-[12px] text-bz-muted">/s/{r.slug}</span></span> },
              { key: "status", label: "Status", render: (r) => <Chip tone={r.domain_status === "connected" ? "gold" : "muted"}>{r.domain_status || "waiting"}</Chip> },
              { key: "published", label: "Site", render: (r) => (r.published ? "Published" : "Draft") },
              { key: "at", label: "Added", render: (r) => dt(r.at) },
              { key: "act", label: "", render: (r) => (r.domain_status === "connected"
                ? <Button variant="small" onClick={() => set(r, "waiting")} loading={busy === r.site_id} data-testid={`domain-wait-${r.site_id}`}>Mark waiting</Button>
                : <Button variant="small" onClick={() => set(r, "connected")} loading={busy === r.site_id} data-testid={`domain-ok-${r.site_id}`}>Mark connected</Button>) },
            ]} />
          </Card>
        </div>
      )}
    </AdminLoadable>
  );
}
