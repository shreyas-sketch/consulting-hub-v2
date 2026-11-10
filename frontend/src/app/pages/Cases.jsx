// /app/cases — "Work along with Akshat" (the three workshop frameworks, on Akshat's case or the member's own client),
// then the live case from the webinar.
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useCases } from "@/services/cases";
import { Card, Chip, Label, Loadable, PageHeader } from "../components/ui";
import { FrameworkList } from "./Frameworks";

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
  const q = useCases();
  return (
    <div className="space-y-5">
      <PageHeader kicker="Cases" title="Think like a consultant," accent="one case at a time."
        sub="Read the situation, write what you'd do, and get a score out of 10 on four things clients care about. Then see the model answer." />
      <Card data-testid="cases-frameworks">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <Label className="mb-0">Work along with Akshat</Label>
          <span className="text-[12.5px] text-bz-muted">The 3 frameworks from the live workshop</span>
        </div>
        <p className="text-[14px] text-bz-muted mt-1">Do each exercise on Akshat's case or on a client from your own niche, save it, then turn it into a client proposal.</p>
        <div className="mt-2"><FrameworkList /></div>
      </Card>
      <Loadable q={q} what="the cases" lines={3}>
        {(d) => {
          const live = (d.items || []).filter((c) => c.live);
          return live.length ? <Card data-testid="cases-live">{live.map((c) => <CaseRow key={c.id} c={c} />)}</Card> : null;
        }}
      </Loadable>
    </div>
  );
}
