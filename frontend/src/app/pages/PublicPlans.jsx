// /plans — public pricing.
import PublicLayout from "../components/PublicLayout";
import PlansView from "../components/PlansView";
import { PageHeader } from "../components/ui";

export default function PublicPlans() {
  return (
    <PublicLayout wide>
      <div className="px-4 md:px-8 py-8 sm:py-12 max-w-[1120px] mx-auto">
        <PageHeader kicker="Plans" title="Two ways to" accent="keep going." sub="Open a free account on the webinar. Then pick the plan that fits. Cancel any time." />
        <PlansView />
      </div>
    </PublicLayout>
  );
}
