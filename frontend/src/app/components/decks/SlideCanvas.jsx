// One slide drawn from the server's layout (features/deck_layout.py): the same boxes, sizes and line breaks the PDF
// and PowerPoint files use, on a 960 x 540 canvas scaled to the width it is given. Kerning and ligatures are off so the
// browser measures text the way the PDF does.
import { memo, useLayoutEffect, useRef, useState } from "react";

const FONT = '"Manrope Variable", Manrope, sans-serif';
const WEIGHT = { regular: 400, semibold: 600, bold: 700, extrabold: 800 };
const TEXT_BASE = {
  fontFamily: FONT, fontKerning: "none", fontVariantLigatures: "none", fontFeatureSettings: '"kern" 0, "liga" 0',
  fontSynthesis: "none", whiteSpace: "pre", WebkitTextSizeAdjust: "100%", textSizeAdjust: "100%",
};

function bgStyle(bg) {
  if (!bg) return {};
  const g = bg.grad;
  if (!g) return { backgroundColor: bg.color };
  const stops = g.stops.map(([p, c]) => `${c} ${p * 100}%`).join(", ");
  return { backgroundColor: bg.color, backgroundImage: `radial-gradient(ellipse ${g.rx}px ${g.ry}px at ${g.cx}px ${g.cy}px, ${stops})` };
}

function Shape({ it }) {
  const paint = { fill: it.fill || "none", stroke: it.stroke && it.sw ? it.stroke : "none", strokeWidth: it.sw || 0 };
  if (it.t === "rect") return <rect x={it.x} y={it.y} width={it.w} height={it.h} rx={it.r} ry={it.r} {...paint} />;
  if (it.t === "oval") return <ellipse cx={it.x + it.w / 2} cy={it.y + it.h / 2} rx={it.w / 2} ry={it.h / 2} {...paint} />;
  if (it.t === "line") return <line x1={it.x1} y1={it.y1} x2={it.x2} y2={it.y2} stroke={it.stroke} strokeWidth={it.sw} />;
  if (it.t === "tri") {
    const { x, y, w, h } = it;
    const pts = it.dir === "up" ? [[x, y + h], [x + w, y + h], [x + w / 2, y]] : [[x, y], [x, y + h], [x + w, y + h / 2]];
    return <polygon points={pts.map((p) => p.join(",")).join(" ")} fill={it.fill} />;
  }
  return null;
}

function TextItem({ it }) {
  const box = {
    ...TEXT_BASE, position: "absolute", left: it.x, top: it.y, width: it.w, height: it.h,
    fontWeight: WEIGHT[it.font] || 400, fontSize: it.size, letterSpacing: it.cs, lineHeight: `${it.lh}px`,
  };
  if (it.rot) { box.transform = `rotate(${it.rot}deg)`; box.transformOrigin = "50% 50%"; }
  const avail = it.w - it.indent;
  const o = it.outline;
  return (
    <div style={box}>
      {it.paras.map((p, pi) => (
        <div key={pi}>
          {it.bullet && p.mark ? (
            <span aria-hidden style={{ position: "absolute", left: p.mark[0], top: p.mark[1], width: it.bullet.size, height: it.bullet.size, background: it.bullet.color }} />
          ) : null}
          {p.lines.map((segs, li) => {
            const lw = p.widths[li];
            const left = it.align === "c" ? it.indent + (avail - lw) / 2 : it.align === "r" ? it.w - lw : it.indent;
            return (
              <div key={li} style={{ position: "absolute", left, top: p.dy + li * it.lh, height: it.lh }}>
                {segs.map(([t, c], si) => (
                  <span key={si} style={o ? { color: "transparent", WebkitTextStroke: `${o.w}px ${o.color}` } : { color: c }}>{t}</span>
                ))}
              </div>
            );
          })}
        </div>
      ))}
    </div>
  );
}

function SlideCanvasInner({ slide, canvas = { w: 960, h: 540 }, label, className = "" }) {
  const ref = useRef(null);
  const [scale, setScale] = useState(0);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return undefined;
    const fit = () => setScale((el.clientWidth || 0) / canvas.w);
    fit();
    if (typeof ResizeObserver === "undefined") {
      window.addEventListener("resize", fit);
      return () => window.removeEventListener("resize", fit);
    }
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [canvas.w]);
  if (!slide) return null;
  const shapes = [];
  const texts = [];
  slide.items.forEach((it, i) => {
    if (it.t === "text") texts.push(<TextItem key={i} it={it} />);
    else if (it.t === "table") {
      it.rules.forEach((r, j) => shapes.push(<Shape key={`${i}-r${j}`} it={r} />));
      it.cells.forEach((cell, j) => texts.push(<TextItem key={`${i}-c${j}`} it={cell} />));
    } else shapes.push(<Shape key={i} it={it} />);
  });
  return (
    <div ref={ref} role="img" aria-label={label} className={`relative w-full overflow-hidden ${className}`}
      style={{ aspectRatio: `${canvas.w} / ${canvas.h}` }}>
      <div aria-hidden style={{
        position: "absolute", left: 0, top: 0, width: canvas.w, height: canvas.h, overflow: "hidden",
        transform: `scale(${scale})`, transformOrigin: "0 0", visibility: scale ? "visible" : "hidden", ...bgStyle(slide.bg),
      }}>
        <svg width={canvas.w} height={canvas.h} viewBox={`0 0 ${canvas.w} ${canvas.h}`} style={{ position: "absolute", left: 0, top: 0 }}>
          {shapes}
        </svg>
        {texts}
      </div>
    </div>
  );
}

export const SlideCanvas = memo(SlideCanvasInner);

// Plain words for the slide's screen-reader label.
export function slideLabel(slide, n) {
  const words = [];
  (slide?.items || []).forEach((it) => {
    const list = it.t === "table" ? it.cells : it.t === "text" && !it.deco ? [it] : [];
    list.forEach((t) => t.paras.forEach((p) => words.push(p.runs.map((r) => r[0]).join(""))));
  });
  return `Slide ${n}: ${words.join(". ").slice(0, 400)}`;
}
