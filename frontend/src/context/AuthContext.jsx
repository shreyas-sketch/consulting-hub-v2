// Auth: cookies set by the API; /auth/me → {user, plan: PlanInfo}.
import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api, apiError, UNAUTH_EVENT } from "@/lib/api";

const AuthCtx = createContext(null);

// /auth/me failing means "logged out" only for 401 (session gone after the refresh try) or 403 revoked.
// A network blip, a deploy restart or a 5xx keeps the member signed in; on first load we quietly try again.
function isLoggedOut(e) {
  const status = e?.response?.status;
  return status === 401 || (status === 403 && e?.response?.data?.detail?.code === "revoked");
}

export function AuthProvider({ children }) {
  const qc = useQueryClient();
  const [user, setUser] = useState(null);      // null = checking, false = logged out, object = user
  const [plan, setPlan] = useState(null);      // PlanInfo
  const [checking, setChecking] = useState(true);
  const known = useRef(false);                 // we've had a real answer (a user, or logged out)
  const retry = useRef({ timer: null, wait: 2000 });
  const self = useRef(null);

  const refreshMe = useCallback(async () => {
    try {
      const { data } = await api.get("/auth/me");
      known.current = true;
      retry.current.wait = 2000;
      setUser(data?.user || false);
      setPlan(data?.plan || null);
      return data;
    } catch (e) {
      if (isLoggedOut(e)) {
        known.current = true;
        setUser(false);
        setPlan(null);
      } else if (!known.current && !retry.current.timer) {
        // First load and the server didn't answer: keep the spinner and try again (2 s, 4 s … up to 30 s).
        const wait = retry.current.wait;
        retry.current.wait = Math.min(wait * 2, 30000);
        retry.current.timer = setTimeout(() => { retry.current.timer = null; self.current?.(); }, wait);
      }
      return null;
    } finally {
      setChecking(false);
    }
  }, []);

  useEffect(() => { self.current = refreshMe; }, [refreshMe]);
  useEffect(() => {
    refreshMe();
    const r = retry.current;
    return () => { if (r.timer) clearTimeout(r.timer); };
  }, [refreshMe]);

  // A request came back 401 even after a refresh: the session is gone.
  useEffect(() => {
    const onUnauth = () => { setUser(false); setPlan(null); };
    window.addEventListener(UNAUTH_EVENT, onUnauth);
    return () => window.removeEventListener(UNAUTH_EVENT, onUnauth);
  }, []);

  const requestOtp = useCallback(async (phone, channel = "auto") => {
    try {
      const { data } = await api.post("/auth/otp/request", { phone, channel });
      return { ok: true, ...data };
    } catch (e) {
      const d = e?.response?.data?.detail;
      return { ok: false, error: apiError(e), code: d?.code, retryIn: d?.retry_in };
    }
  }, []);

  const verifyOtp = useCallback(async ({ challengeId, phone, code, name, utm, deviceId }) => {
    try {
      const body = { challenge_id: challengeId, phone, code, utm: utm || {}, device_id: deviceId || null };
      if (name && name.trim()) body.name = name.trim();
      const { data } = await api.post("/auth/otp/verify", body);
      await refreshMe();
      return { ok: true, user: data?.user, isNew: data?.is_new };
    } catch (e) {
      const d = e?.response?.data?.detail;
      return { ok: false, error: apiError(e), code: d?.code, attemptsLeft: d?.attempts_left };
    }
  }, [refreshMe]);

  const staffLogin = useCallback(async (email, password) => {
    try {
      await api.post("/auth/staff/login", { email, password });
      const me = await refreshMe();
      return { ok: true, user: me?.user };
    } catch (e) {
      return { ok: false, error: apiError(e, "Email or password is wrong.") };
    }
  }, [refreshMe]);

  const logout = useCallback(async () => {
    try { await api.post("/auth/logout"); } catch { /* noop */ }
    setUser(false);
    setPlan(null);
    qc.clear();
  }, [qc]);

  return (
    <AuthCtx.Provider value={{ user, plan, checking, refreshMe, setPlan, setUser, requestOtp, verifyOtp, staffLogin, logout }}>
      {children}
    </AuthCtx.Provider>
  );
}

export function useAuth() {
  const ctx = useContext(AuthCtx);
  if (!ctx) throw new Error("useAuth must be used inside <AuthProvider>");
  return ctx;
}

// Feature access from PlanInfo.features (true/false). Admins see everything.
export function useFeature(key) {
  const { user, plan } = useAuth();
  if (!user) return false;
  if (user.role === "admin") return true;
  return !!plan?.features?.[key];
}
