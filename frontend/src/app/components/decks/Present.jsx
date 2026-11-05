// Full-screen Present mode: one slide at a time, as big as the screen allows. Tap the right side (or swipe left, or press
// → / Space / Page Down) for the next slide; tap the left side (or swipe right, or press ← / Page Up) to go back. Esc closes.
import { useCallback, useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import { SlideCanvas, slideLabel } from "./SlideCanvas";

function useViewport() {
  const read = () => ({ w: window.innerWidth, h: window.innerHeight });
  const [vp, setVp] = useState(read);
  useEffect(() => {
    const on = () => setVp(read());
    window.addEventListener("resize", on);
    window.addEventListener("orientationchange", on);
    return () => { window.removeEventListener("resize", on); window.removeEventListener("orientationchange", on); };
  }, []);
  return vp;
}

export default function Present({ layout, canvas, start = 0, onClose }) {
  const [i, setI] = useState(Math.min(start, layout.length - 1));
  const n = layout.length;
  const vp = useViewport();
  const touch = useRef(null);
  const next = useCallback(() => setI((x) => Math.min(n - 1, x + 1)), [n]);
  const prev = useCallback(() => setI((x) => Math.max(0, x - 1)), []);

  useEffect(() => {
    const onKey = (e) => {
      if (["ArrowRight", "ArrowDown", "PageDown", " ", "Enter"].includes(e.key)) { e.preventDefault(); next(); }
      else if (["ArrowLeft", "ArrowUp", "PageUp", "Backspace"].includes(e.key)) { e.preventDefault(); prev(); }
      else if (e.key === "Home") setI(0);
      else if (e.key === "End") setI(n - 1);
      else if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [next, prev, n, onClose]);

  useEffect(() => {
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const el = document.documentElement;
    try { if (el.requestFullscreen && !document.fullscreenElement) el.requestFullscreen().catch(() => {}); } catch { /* not allowed */ }
    return () => {
      document.body.style.overflow = prevOverflow;
      try { if (document.fullscreenElement && document.exitFullscreen) document.exitFullscreen().catch(() => {}); } catch { /* ignore */ }
    };
  }, []);

  const width = Math.min(vp.w, (vp.h * canvas.w) / canvas.h);
  const portrait = vp.h > vp.w;
  const onTap = (e) => {
    if (e.clientX < vp.w / 3) prev(); else next();
  };
  const onTouchStart = (e) => { touch.current = e.touches[0]?.clientX ?? null; };
  const onTouchEnd = (e) => {
    const x0 = touch.current;
    touch.current = null;
    const x1 = e.changedTouches[0]?.clientX;
    if (x0 == null || x1 == null || Math.abs(x1 - x0) < 50) return;
    e.preventDefault();
    if (x1 < x0) next(); else prev();
  };

  return (
    <div className="fixed inset-0 z-[70] bg-black flex items-center justify-center select-none" role="dialog" aria-modal="true"
      aria-label="Present your deck" data-testid="deck-present-mode">
      <button type="button" className="absolute inset-0 w-full h-full cursor-pointer" aria-label="Next slide (tap the left side to go back)"
        onClick={onTap} onTouchStart={onTouchStart} onTouchEnd={onTouchEnd} />
      <div className="relative pointer-events-none" style={{ width }}>
        <SlideCanvas slide={layout[i]} canvas={canvas} label={slideLabel(layout[i], i + 1)} />
      </div>
      <div className="absolute top-0 right-0 left-0 flex items-center justify-between gap-3 p-2 pt-[max(8px,env(safe-area-inset-top))] pointer-events-none">
        <span className="text-[13px] font-bold text-white/60 tabular px-3" aria-live="polite">{i + 1} / {n}</span>
        <button type="button" onClick={onClose} className="pointer-events-auto inline-flex items-center gap-1.5 min-h-[44px] px-4 rounded-bzbtn bg-white/10 text-white/80 text-[14px] font-bold hover:bg-white/20" data-testid="deck-present-close">
          <X className="w-4 h-4" aria-hidden /> Close
        </button>
      </div>
      {portrait && (
        <p className="absolute bottom-0 inset-x-0 text-center text-[13px] text-white/50 px-4 pb-[max(16px,env(safe-area-inset-bottom))] pointer-events-none">
          Turn your phone sideways for a bigger slide.
        </p>
      )}
    </div>
  );
}
