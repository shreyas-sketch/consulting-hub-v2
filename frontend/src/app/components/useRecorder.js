// MediaRecorder hook for in-browser recording: audio only (Career Story Bank voice notes) or video + audio with a live
// camera preview (Pitch Practice, Portfolio video). Nothing leaves the phone until the page uploads the blob itself.
//
//   const rec = useRecorder({ video: true, maxSeconds: 480 });
//   <video ref={rec.previewRef} muted playsInline autoPlay />        live preview while the camera is on
//   rec.open()  → asks for the camera/mic and shows the preview (video only; start() also opens it)
//   rec.start() → records; rec.stop() → rec.blob, rec.url, rec.seconds, rec.mimeType, rec.ext
//   rec.reset() → back to idle (frees the camera and the recording)
// status: idle | asking | ready | recording | done | error  (error: rec.error is a plain sentence)
import { useCallback, useEffect, useRef, useState } from "react";

const VIDEO_TYPES = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4;codecs=avc1,mp4a", "video/mp4"];
const AUDIO_TYPES = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg;codecs=opus", "audio/mp4", "audio/mpeg"];

export function recorderSupported() {
  return typeof window !== "undefined" && !!window.MediaRecorder && !!navigator?.mediaDevices?.getUserMedia;
}

function pickType(video) {
  if (!recorderSupported()) return "";
  const list = video ? VIDEO_TYPES : AUDIO_TYPES;
  return list.find((t) => { try { return window.MediaRecorder.isTypeSupported(t); } catch { return false; } }) || "";
}

export function extFor(mime) {
  const m = String(mime || "").toLowerCase();
  if (m.includes("mp4")) return m.startsWith("audio") ? "m4a" : "mp4";
  if (m.includes("ogg")) return "ogg";
  if (m.includes("mpeg")) return "mp3";
  if (m.includes("quicktime")) return "mov";
  return "webm";
}

// Duration of a picked file in seconds (null when the browser can't tell, e.g. some recordings report Infinity).
export function mediaDuration(file) {
  return new Promise((resolve) => {
    try {
      const isVideo = String(file?.type || "").startsWith("video") || /\.(mp4|mov|webm|mkv|m4v)$/i.test(file?.name || "");
      const el = document.createElement(isVideo ? "video" : "audio");
      const url = URL.createObjectURL(file);
      const done = (v) => { URL.revokeObjectURL(url); resolve(Number.isFinite(v) && v > 0 ? v : null); };
      el.preload = "metadata";
      el.onloadedmetadata = () => done(el.duration);
      el.onerror = () => done(null);
      setTimeout(() => done(null), 8000);
      el.src = url;
    } catch { resolve(null); }
  });
}

function plainError(e, video) {
  const n = e?.name || "";
  if (n === "NotAllowedError" || n === "SecurityError") return `Allow ${video ? "camera and microphone" : "microphone"} access in your browser, then try again.`;
  if (n === "NotFoundError" || n === "OverconstrainedError") return `We couldn't find a ${video ? "camera or microphone" : "microphone"} on this device.`;
  if (n === "NotReadableError") return `Another app is using your ${video ? "camera" : "microphone"}. Close it and try again.`;
  return "Recording didn't start. You can upload a file instead.";
}

export default function useRecorder({ video = false, maxSeconds = 600 } = {}) {
  const [status, setStatus] = useState("idle");
  const [error, setError] = useState("");
  const [seconds, setSeconds] = useState(0);
  const [result, setResult] = useState(null);          // {blob, url, mimeType, ext, seconds}
  const streamRef = useRef(null);
  const recRef = useRef(null);
  const chunksRef = useRef([]);
  const timerRef = useRef(null);
  const startedRef = useRef(0);
  const previewEl = useRef(null);
  const urlRef = useRef(null);

  const attach = useCallback(() => {
    const el = previewEl.current;
    if (el && streamRef.current && el.srcObject !== streamRef.current) {
      el.srcObject = streamRef.current;
      el.muted = true;
      el.play?.().catch(() => {});
    }
  }, []);

  // Callback ref: the <video> may mount after the stream exists.
  const previewRef = useCallback((el) => { previewEl.current = el; if (el) attach(); }, [attach]);

  const stopStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
    if (previewEl.current) previewEl.current.srcObject = null;
  }, []);

  const clearTimer = () => { if (timerRef.current) { clearInterval(timerRef.current); timerRef.current = null; } };

  const open = useCallback(async () => {
    if (streamRef.current) { attach(); return true; }
    if (!recorderSupported()) { setError("This browser can't record. Upload a file instead."); setStatus("error"); return false; }
    setError(""); setStatus("asking");
    try {
      const constraints = video
        ? { audio: { echoCancellation: true, noiseSuppression: true }, video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } } }
        : { audio: { echoCancellation: true, noiseSuppression: true } };
      streamRef.current = await navigator.mediaDevices.getUserMedia(constraints);
      attach();
      setStatus("ready");
      return true;
    } catch (e) {
      setError(plainError(e, video)); setStatus("error");
      return false;
    }
  }, [video, attach]);

  const stop = useCallback(() => {
    const r = recRef.current;
    if (r && r.state !== "inactive") r.stop();
  }, []);

  const start = useCallback(async () => {
    if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
    setResult(null);
    const ok = await open();
    if (!ok || !streamRef.current) return;
    const mimeType = pickType(video);
    let r;
    try {
      r = mimeType ? new window.MediaRecorder(streamRef.current, { mimeType }) : new window.MediaRecorder(streamRef.current);
    } catch (e) {
      setError(plainError(e, video)); setStatus("error"); return;
    }
    chunksRef.current = [];
    r.ondataavailable = (ev) => { if (ev.data && ev.data.size) chunksRef.current.push(ev.data); };
    r.onstop = () => {
      clearTimer();
      const type = (r.mimeType || mimeType || (video ? "video/webm" : "audio/webm")).split(";")[0];
      const blob = new Blob(chunksRef.current, { type });
      const secs = Math.max(1, Math.round((Date.now() - startedRef.current) / 1000));
      const url = URL.createObjectURL(blob);
      urlRef.current = url;
      setResult({ blob, url, mimeType: type, ext: extFor(type), seconds: secs });
      setSeconds(secs);
      stopStream();
      setStatus("done");
    };
    recRef.current = r;
    startedRef.current = Date.now();
    setSeconds(0);
    r.start(1000);
    setStatus("recording");
    clearTimer();
    timerRef.current = setInterval(() => {
      const s = Math.floor((Date.now() - startedRef.current) / 1000);
      setSeconds(s);
      if (s >= maxSeconds) stop();
    }, 250);
  }, [open, video, maxSeconds, stop, stopStream]);

  const reset = useCallback(() => {
    clearTimer();
    const r = recRef.current;
    if (r && r.state !== "inactive") { r.onstop = null; try { r.stop(); } catch { /* already stopped */ } }
    recRef.current = null;
    stopStream();
    if (urlRef.current) { URL.revokeObjectURL(urlRef.current); urlRef.current = null; }
    setResult(null); setSeconds(0); setError(""); setStatus("idle");
  }, [stopStream]);

  // Free the camera/mic and the recording when the screen closes.
  useEffect(() => () => {
    clearTimer();
    const r = recRef.current;
    if (r && r.state !== "inactive") { r.onstop = null; try { r.stop(); } catch { /* noop */ } }
    streamRef.current?.getTracks().forEach((t) => t.stop());
    if (urlRef.current) URL.revokeObjectURL(urlRef.current);
  }, []);

  return {
    status, error, seconds, maxSeconds, supported: recorderSupported(),
    blob: result?.blob || null, url: result?.url || null, mimeType: result?.mimeType || "", ext: result?.ext || "",
    recordedSeconds: result?.seconds || 0,
    previewRef, open, start, stop, reset,
  };
}

export function clock(s) {
  const n = Math.max(0, Math.floor(Number(s) || 0));
  return `${Math.floor(n / 60)}:${String(n % 60).padStart(2, "0")}`;
}
