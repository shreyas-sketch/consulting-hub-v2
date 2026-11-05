// /app/cases — the live case (from the webinar) first, then the practice cases. Free accounts: the live case, plus
// any case they answered before (read-only).
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useCases } from "@/services/cases";
import { useAuth } from "@/context/AuthContext";
import { Card, Chip, Label, LinkButton, Loadable, PageHeader } from "../components/ui";

function CaseRow({ c }) {
  const body = (
    <div className={`flex items-start gap-3 py-4 border-b border-bz-line last:border-0 ${c.locked ? "opacity-60" : ""}`}>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          {c.live && <Chip tone="solid">Live case</Chip>}
          {c.kind === "weekly" && <Chip tone="gold">This week</Chip>}
          {c.read_only && c.answered && <Chip>You answered this</Chip>}
          <span className="text-[12px] text-bz-muted">{c.industry}{c.city ? ` · ${c.city}` : ""}</span>
        </div>
        <p className="text-[16px] font-bold mt-1.5">{c.title}</p>
        <p className="text-[13px] text-bz-muted">{c.company}</p>
      </div>
      <div className="shrink-0 text-right">
        {c.locked ? <Lock className="w-4 h-4 text-bz-faint mt-1" aria-label="On the ₹1,999 plan" />
          : c.my_score != null ? <span className="text-[20px] font-extrabold text-bz-gold tabular">{c.my_score}<span className="text-[12px] text-bz-muted">/10</span></span>
            : <span className="text-[13px] font-bold text-bz-gold">Solve</span>}
      </div>
    </div>
  );
  return c.locked ? <div>{body}</div> : <Link to={`/app/cases/${c.id}`} className="block hover:bg-bz-raised -mx-4 px-4 sm:-mx-5 sm:px-5" data-testid={`case-${c.id}`}>{body}</Link>;
}

export default function Cases() {
  const { plan } = useAuth();
  const q = useCases();
  return (
    <div className="space-y-5">
      <PageHeader kicker="Cases" title="Think like a consultant," accent="one case at a time."
        sub="Read the situation, write what you'd do, and get a score out of 10 on four things clients care about. Then see the model answer." />
      <Loadable q={q} what="the cases" lines={6}>
        {(d) => {
          const live = (d.items || []).filter((c) => c.live);
          const rest = (d.items || []).filter((c) => !c.live);
          return (
            <>
              <Card>{live.map((c) => <CaseRow key={c.id} c={c} />)}</Card>
              <Card>
                <Label>Practice cases</Label>
                {rest.map((c) => <CaseRow key={c.id} c={c} />)}
              </Card>
              {plan?.plan === "free" && (
                <Card inset>
                  <p className="text-[15px] font-bold">A new case every week on the ₹1,999 plan.</p>
                  <p className="text-[14px] text-bz-muted mt-1">Every Monday, a real company from the news, with a score and a model answer.</p>
                  <LinkButton to="/app/plans?from=cases" variant="secondary" className="mt-3">See the plans</LinkButton>
                </Card>
              )}
            </>
          );
        }}
      </Loadable>
    </div>
  );
}
