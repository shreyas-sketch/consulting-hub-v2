// Route map — see README.md. Public: / (What's inside) /login /plans /terms /privacy.
// Member app (/app/*) inside AppShell, login required. Admin (/admin/*) role admin only. Dark only.
import { lazy, Suspense } from "react";
import { BrowserRouter, Navigate, Route, Routes } from "react-router-dom";
import { AuthProvider } from "@/context/AuthContext";
import AppShell, { RequireAuth } from "@/app/components/AppShell";
import GateSheet from "@/app/components/GateSheet";
import { Spinner } from "@/app/components/ui";
import Inside from "@/app/pages/Inside";
import Login from "@/app/pages/Login";
import PublicPlans from "@/app/pages/PublicPlans";
import { Privacy, Terms } from "@/app/pages/Legal";

const Home = lazy(() => import("@/app/pages/Home"));
const Readiness = lazy(() => import("@/app/pages/Readiness"));
const Start = lazy(() => import("@/app/pages/Start"));
const Cases = lazy(() => import("@/app/pages/Cases"));
const CaseView = lazy(() => import("@/app/pages/CaseView"));
const Brief = lazy(() => import("@/app/pages/Brief"));
const BriefView = lazy(() => import("@/app/pages/Brief").then((m) => ({ default: m.BriefView })));
const LinkedIn = lazy(() => import("@/app/pages/LinkedIn"));
const File = lazy(() => import("@/app/pages/File"));
const Tools = lazy(() => import("@/app/pages/Tools"));
const Inbox = lazy(() => import("@/app/pages/Inbox"));
const Account = lazy(() => import("@/app/pages/Account"));
const AppPlans = lazy(() => import("@/app/pages/AppPlans"));
// ₹1,999 plan, L1 and L2 tools (one file each; "x" and "x/:id" both go to the same screen)
const P = (name) => lazy(() => import(`./app/pages/${name}.jsx`));
const TOOL_ROUTES = [
  ["decks", "Decks"], ["visuals", "Visuals"], ["website", "Website"], ["listen", "Listen"], ["docs", "Docs"],
  ["progress", "Progress"], ["support", "Support"],
  ["program", "Program"], ["calls", "Calls"], ["library", "Library"], ["recaps", "Recaps"], ["gpt", "GptChat"],
  ["akshat-ai", "AkshatAI"], ["offer", "OfferCard"], ["stories", "Stories"], ["insights", "Insights"],
  ["portfolio", "Portfolio"], ["pitch", "Pitch"], ["research", "Research"],
  ["network", "Network"], ["outreach", "Outreach"], ["radar", "Radar"], ["call-prep", "CallPrep"],
  ["proposals", "Proposals"], ["diagnostic", "Diagnostic"], ["social", "Social"], ["bootcamps", "Bootcamps"],
].map(([path, name]) => [path, P(name)]);
const Gpts = P("Gpts");
const DiagnosticPublic = P("DiagnosticPublic");
const AdminApp = lazy(() => import("@/app/admin/AdminApp"));
const AdminLogin = lazy(() => import("@/app/admin/AdminLogin"));

const fallback = <div className="min-h-[40vh] grid place-items-center"><Spinner /></div>;

export default function App() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <GateSheet />
        <Suspense fallback={fallback}>
          <Routes>
            <Route path="/" element={<Inside />} />
            <Route path="/login" element={<Login />} />
            <Route path="/plans" element={<PublicPlans />} />
            <Route path="/terms" element={<Terms />} />
            <Route path="/privacy" element={<Privacy />} />
            <Route path="/d/:id" element={<DiagnosticPublic />} />

            <Route path="/app" element={<RequireAuth><AppShell /></RequireAuth>}>
              <Route index element={<Home />} />
              <Route path="readiness" element={<Readiness />} />
              <Route path="start" element={<Start />} />
              <Route path="cases" element={<Cases />} />
              <Route path="cases/:id" element={<CaseView />} />
              <Route path="brief" element={<Brief />} />
              <Route path="brief/:id" element={<BriefView />} />
              <Route path="linkedin" element={<LinkedIn />} />
              <Route path="file" element={<File />} />
              <Route path="tools" element={<Tools />} />
              <Route path="inbox" element={<Inbox />} />
              <Route path="account" element={<Account />} />
              <Route path="plans" element={<AppPlans />} />
              <Route path="hub" element={<Gpts program="action" />} />
              <Route path="mentorship" element={<Gpts program="mentorship" />} />
              {TOOL_ROUTES.map(([path, El]) => [
                <Route key={path} path={path} element={<El />} />,
                <Route key={`${path}-id`} path={`${path}/:id`} element={<El />} />,
              ])}
              <Route path="*" element={<Navigate to="/app" replace />} />
            </Route>

            <Route path="/admin/login" element={<AdminLogin />} />
            <Route path="/admin/*" element={<AdminApp />} />

            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </AuthProvider>
    </BrowserRouter>
  );
}
