// /app/tools — every tool by plan: open on your plan, part of a higher plan, or coming soon.
import { Link } from "react-router-dom";
import { Lock } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import { FEATURES, PLAN_LABEL, PLAN_RANK } from "@/lib/features";
import { Card, Chip, Label, PageHeader } from "../components/ui";

const GROUPS = [
  { plan: "free", title: "From the webinar" },
  { plan: "member", title: "₹1,999 plan" },
  { plan: "l1", title: "L1" },
  { plan: "l2", title: "L2 Mentorship" },
];

export default function Tools() {
  const { user, plan } = useAuth();
  const mine = user?.role === "admin" ? "l2" : plan?.plan || "free";
  return (
    <div className="space-y-5">
      <PageHeader kicker="All tools" title="What each plan" accent="opens." sub={`You're on the ${PLAN_LABEL[mine]}. Tap any tool on your plan to open it.`} />
      {GROUPS.map((g) => {
        const items = Object.entries(FEATURES).filter(([, f]) => f.plan === g.plan);
        const open = PLAN_RANK[mine] >= PLAN_RANK[g.plan];
        return (
          <Card key={g.plan}>
            <div className="flex items-center justify-between gap-3 mb-1">
              <Label className="mb-0">{g.title}</Label>
              {open ? <Chip tone="gold">On your plan</Chip> : <Link to={`/app/plans?plan=${g.plan === "l2" ? "l1" : g.plan}&from=tools`} className="text-[13px] font-bold text-bz-gold min-h-[36px] inline-flex items-center">See plan</Link>}
            </div>
            {items.map(([key, f]) => {
              const live = !!f.to;
              const body = (
                <div className="flex items-start gap-3 py-3 border-b border-bz-line last:border-0">
                  <div className="min-w-0 flex-1">
                    <p className={`text-[15px] font-bold ${open && live ? "" : "text-bz-muted"}`}>{f.name}</p>
                    <p className="text-[13px] text-bz-muted">{f.what}</p>
                  </div>
                  {!live ? <Chip>Coming soon</Chip> : !open ? <Lock className="w-4 h-4 text-bz-faint mt-1" aria-label="Locked" /> : <Chip tone="gold">Open</Chip>}
                </div>
              );
              return open && live && f.to ? <Link key={key} to={f.to} className="block hover:bg-bz-raised -mx-4 px-4 sm:-mx-5 sm:px-5" data-testid={`tool-${key}`}>{body}</Link> : <div key={key}>{body}</div>;
            })}
          </Card>
        );
      })}
    </div>
  );
}
