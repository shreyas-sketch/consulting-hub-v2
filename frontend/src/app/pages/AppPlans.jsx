// /app/plans — plans inside the shell.
import PlansView from "../components/PlansView";
import { PageHeader } from "../components/ui";

export default function AppPlans() {
  return (
    <div>
      <PageHeader kicker="Plans" title="Keep going" accent="every week." sub="The ₹1,999 plan keeps the tools working for you. L1 adds the 4-3-2-1 action program and group calls with Akshat." />
      <PlansView inShell />
    </div>
  );
}
