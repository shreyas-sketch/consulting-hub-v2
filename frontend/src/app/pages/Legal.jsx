// /terms, /privacy — short placeholder legal pages (to be replaced by counsel-reviewed text before launch).
import brand from "@/brand";
import PublicLayout from "../components/PublicLayout";
import { Card, PageHeader } from "../components/ui";

function LegalPage({ kicker, title, accent, children }) {
  return (
    <PublicLayout>
      <div className="px-4 md:px-8 py-8 sm:py-12 max-w-[760px] mx-auto">
        <PageHeader kicker={kicker} title={title} accent={accent} />
        <Card inset className="mb-6"><p className="text-[14px]">Placeholder text. The final version will be published before launch.</p></Card>
        <div className="space-y-5 text-[16px] leading-relaxed [&_h2]:text-[20px] [&_h2]:font-extrabold [&_h2]:mt-8 [&_ul]:list-disc [&_ul]:pl-5 [&_ul]:space-y-1.5">
          {children}
        </div>
      </div>
    </PublicLayout>
  );
}

export function Terms() {
  return (
    <LegalPage kicker="Legal" title="Terms of" accent="use">
      <h2>What {brand.name} is</h2>
      <p>{brand.name} is a set of learning and practice tools for professionals getting ready to work as consultants. The AI tools give suggestions and practice feedback; you decide what to use.</p>
      <h2>No promise of results</h2>
      <p>Scores, niche suggestions, goal maps and briefs are estimates to help you think. They are not a promise of clients or income. Results depend on your own work.</p>
      <h2>Plans and payments</h2>
      <ul>
        <li>Paid plans renew automatically through Razorpay until you cancel. Prices are shown before 18% GST.</li>
        <li>When you cancel, your plan runs to the end of the period you have paid for.</li>
        <li>L2 Mentorship is sold separately by the team. While L2 runs, your L1 billing pauses and restarts when L2 ends.</li>
      </ul>
      <h2>Your account</h2>
      <p>One account per mobile number. Keep your login code private.</p>
    </LegalPage>
  );
}

export function Privacy() {
  return (
    <LegalPage kicker="Legal" title="Privacy" accent="policy">
      <h2>What we keep</h2>
      <ul>
        <li>Your mobile number, name and (if you add it) email.</li>
        <li>What you make in the tools: scores, niche options, goal numbers, case answers, briefs and LinkedIn text you paste.</li>
        <li>Which tools you use and when, so the team can improve them and invite you to the right sessions.</li>
      </ul>
      <h2>Who sees it</h2>
      <p>The {brand.name} team. Text you send to an AI tool is processed by our AI provider to produce your result. We do not sell your data.</p>
      <h2>Your choices</h2>
      <p>Ask the team to correct or delete your data at any time.</p>
    </LegalPage>
  );
}
