// /login — mobile OTP. New numbers get a free account. After login: ?next= or /app.
import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import { captureAttribution } from "@/lib/attribution";
import AuthShell from "../components/AuthShell";
import OtpLogin from "../components/OtpLogin";

function safeNext(n) {
  return n && n.startsWith("/") && !n.startsWith("//") ? n : "/app";
}

export default function Login() {
  const { user } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const next = safeNext(new URLSearchParams(loc.search).get("next"));
  const [step, setStep] = useState({ s: "phone", ch: null });

  useEffect(() => { captureAttribution(loc.search); }, [loc.search]);
  useEffect(() => { if (user) nav(next, { replace: true }); }, [user]); // eslint-disable-line react-hooks/exhaustive-deps

  const legal = (
    <span>By continuing you agree to the <Link to="/terms" className="text-bz-gold">Terms</Link> and <Link to="/privacy" className="text-bz-gold">Privacy policy</Link>.</span>
  );
  const code = step.s === "code";
  return (
    <AuthShell
      kicker={code ? "Verify" : "Log in or sign up"}
      title={code ? "Enter the" : "Open your"}
      accent={code ? "code." : "account."}
      subtitle={code ? `Sent by ${step.ch?.channel === "whatsapp" ? "WhatsApp" : "SMS"} to ${step.ch?.sent_to || "your number"}.` : "Type your mobile number. We'll send a 6-digit code."}
      footer={legal}
    >
      <OtpLogin onStep={(s, ch) => setStep({ s, ch })} onDone={() => nav(next, { replace: true })} />
    </AuthShell>
  );
}
