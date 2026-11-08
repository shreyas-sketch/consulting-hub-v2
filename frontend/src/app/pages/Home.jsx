// /app — Home: your progress on the six tools, the group session invite, your numbers so far, and what's next.
import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Check } from "lucide-react";
import { api } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { track } from "@/lib/attribution";
import { FEATURES, WEBINAR_TOOLS } from "@/lib/features";
import { inr } from "@/lib/format";
import { useConsultingFile } from "@/services/file";
import { qk } from "@/services/queryKeys";
import { Card, Chip, Label, LinkButton, Loadable, Meter, PageHeader, RowLink, Stat } from "../components/ui";

function greeting() {
  const h = Number(new Date().toLocaleString("en-IN", { hour: "numeric", hour12: false, timeZone: "Asia/Kolkata" }));
  return h < 12 ? "Good morning," : h < 17 ? "Good afternoon," : "Good evening,";
}

function doneMap(f) {
  return {
    readiness: !!f.readiness, start: !!f.snapshot || !!f.goal, case: (f.cases || []).length > 0,
    brief: (f.briefs || []).length > 0, linkedin: !!f.linkedin, file: !!(f.readiness || f.snapshot || (f.cases || []).length),
  };
}

function GroupSession({ s }) {
  if (!s?.link) return null;
  return (
    <Card className="border-bz-gold shadow-goldglow" data-testid="group-session">
      <div className="flex items-start gap-3">
        <span className="w-10 h-10 rounded-full bg-bz-gold-tint text-bz-gold grid place-items-center shrink-0"><CalendarCheck className="w-5 h-5" strokeWidth={1.9} aria-hidden /></span>
        <div className="min-w-0 flex-1">
          <Label className="mb-1">You're invited</Label>
          <p className="text-[19px] font-extrabold leading-tight">{s.title}</p>
          {s.when && <p className="text-[15px] text-bz-gold font-bold mt-1">{s.when}</p>}
          <p className="text-[14px] text-bz-muted mt-1.5">A live group session with Akshat for everyone who opened an account on the webinar. Bring your questions.</p>
        </div>
      </div>
      <a href={s.link} target="_blank" rel="noopener noreferrer" onClick={() => track("group_session_clicked", {})}
        className="mt-4 w-full inline-flex items-center justify-center min-h-[52px] px-6 rounded-bzbtn bg-bz-gold text-bz-on-accent font-extrabold text-[16px]">
        Join the session
      </a>
    </Card>
  );
}

export default function Home() {
  const { user, plan } = useAuth();
  const file = useConsultingFile();
  const home = useQuery({ queryKey: qk.home, queryFn: async () => (await api.get("/me/home")).data, staleTime: 5 * 60_000 });
  const p = plan?.plan || "free";
  const first = (user?.name || "").split(" ")[0];
  return (
    <div className="space-y-5">
      <PageHeader kicker="Home" title={greeting()} accent={first || "welcome."}
        sub={p === "free" ? "These are the tools from the webinar. Each one is yours to use once, and what you make stays in your Consulting File." : "Pick up where you left off."} />

      {(p === "free" || p === "member") && <GroupSession s={home.data?.group_session} />}

      <Loadable q={file} what="your progress" lines={6}>
        {(f) => {
          const done = doneMap(f);
          const n = WEBINAR_TOOLS.filter((k) => done[k]).length;
          const niche = f.niche;
          const lastCase = (f.cases || [])[0];
          return (
            <>
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                <Stat label="Readiness" value={f.readiness ? `${f.readiness.total}/60` : "—"} sub={f.readiness?.band || "Not scored yet"} />
                <Stat label="Clients a month" value={f.goal ? f.goal.clients_per_month : "—"} sub={f.goal ? `for ${inr(f.goal.monthly_goal_inr)} a month` : "Set your goal"} />
                <Stat label="Last case" value={lastCase ? `${lastCase.overall}/10` : "—"} sub={lastCase ? lastCase.title : "Solve the live case"} />
                <Stat label="LinkedIn" value={f.linkedin ? `${f.linkedin.score}/100` : "—"} sub={f.linkedin ? (f.linkedin.kind === "review" ? "Client fit" : "Latest score") : "Not checked yet"} />
              </div>

              {niche && (
                <Card>
                  <Label>Your niche</Label>
                  <p className="text-[20px] font-extrabold leading-tight">{niche.niche}</p>
                  <p className="text-[14px] text-bz-muted mt-1">{niche.who} · {niche.problem}</p>
                </Card>
              )}

              <Card data-testid="tool-progress">
                <div className="flex items-center justify-between gap-3">
                  <Label className="mb-0">Your webinar tools</Label>
                  <span className="text-[13px] font-bold text-bz-gold tabular">{n} of {WEBINAR_TOOLS.length} done</span>
                </div>
                <Meter value={(n / WEBINAR_TOOLS.length) * 100} className="mt-3 mb-1" label="Tools done" />
                <div>
                  {WEBINAR_TOOLS.map((k) => (
                    <RowLink key={k} to={FEATURES[k].to} title={FEATURES[k].name} sub={FEATURES[k].what} testid={`home-${k}`}
                      right={done[k] ? <Chip tone="gold"><Check className="w-3 h-3" aria-hidden />Done</Chip> : <Chip>Start</Chip>} />
                  ))}
                </div>
              </Card>
            </>
          );
        }}
      </Loadable>

      {p === "free" && (
        <Card>
          <Label>Keep going after the webinar</Label>
          <p className="text-[17px] font-bold">A new case every week, 4 Meeting Briefs a month, LinkedIn rewrites and more.</p>
          <p className="text-[14px] text-bz-muted mt-1">₹1,999 + GST a month, or L1 at ₹5,000 + GST a month with the 4-3-2-1 action program.</p>
          <LinkButton to="/app/plans?from=home" variant="secondary" className="mt-4 w-full sm:w-auto">See the plans</LinkButton>
        </Card>
      )}
      {p === "member" && (
        <Card>
          <Label>Ready for more?</Label>
          <p className="text-[17px] font-bold">L1 adds the 4-3-2-1 action program, two group calls a month with Akshat, and Akshat AI.</p>
          <LinkButton to="/app/plans?plan=l1&from=home" variant="secondary" className="mt-4 w-full sm:w-auto">See L1</LinkButton>
        </Card>
      )}
    </div>
  );
}
