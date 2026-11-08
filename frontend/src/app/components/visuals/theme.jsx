// Visual Builder palette and SVG helpers. Hex values from the hub tokens (index.css, "graph paper"), because an exported
// SVG/PNG can't read CSS variables. "light" is only an export option for slides on a white background.
export const FONT = "Manrope, 'Manrope Variable', Inter, system-ui, sans-serif";

export const THEMES = {
  dark: {
    bg: "#0f2747", panel: "#15325a", ink: "#f2f6fc", muted: "#a9b9d3", faint: "#8296b8",
    line: "#24456f", lineStrong: "#33598a", gold: "#6fa0ff", goldLight: "#a9c6ff", goldDeep: "#3f74e0",
    onGold: "#0f2747", goldTint: "rgba(111,160,255,0.14)",
  },
  light: {
    bg: "#ffffff", panel: "#f3f6fb", ink: "#13213a", muted: "#56657d", faint: "#8794a8",
    line: "#d7e0ec", lineStrong: "#b7c5d9", gold: "#1d4ed8", goldLight: "#6f95f0", goldDeep: "#0f2747",
    onGold: "#ffffff", goldTint: "rgba(29,78,216,0.08)",
  },
};

// Categorical order for chart series and pie slices: fixed, never cycled. Identity is never colour alone:
// a legend for 2+ series, dash patterns on lines, names and % on every pie slice.
export function seriesColors(t) {
  return [t.gold, t.ink, t.goldDeep, t.goldLight, t.muted, t.lineStrong, t.faint, t.panel];
}
export const DASHES = [null, "12 7", "3 7"];

export const W = 1200;
export const PAD = 56;

// Rough Manrope width: good enough to wrap labels without measuring the DOM (exports render off-screen too).
export const textWidth = (s, size, bold = false) => String(s || "").length * size * (bold ? 0.6 : 0.55);

export function wrap(text, maxWidth, size, maxLines = 3, bold = false) {
  const words = String(text || "").split(/\s+/).filter(Boolean);
  const per = Math.max(4, Math.floor(maxWidth / (size * (bold ? 0.6 : 0.55))));
  const lines = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length > per && cur) {
      lines.push(cur);
      cur = w;
    } else cur = next;
    while (cur.length > per) { lines.push(cur.slice(0, per)); cur = cur.slice(per); }
  }
  if (cur) lines.push(cur);
  if (lines.length > maxLines) {
    const kept = lines.slice(0, maxLines);
    kept[maxLines - 1] = `${kept[maxLines - 1].slice(0, Math.max(1, per - 1))}…`;
    return kept;
  }
  return lines;
}

// Multi-line <text>: lines stacked from y (first baseline).
export function Lines({ lines, x, y, size, lh = 1.3, fill, weight = 400, anchor = "start" }) {
  return (
    <text x={x} y={y} fill={fill} fontSize={size} fontWeight={weight} textAnchor={anchor}>
      {lines.map((l, i) => <tspan key={i} x={x} dy={i === 0 ? 0 : size * lh}>{l}</tspan>)}
    </text>
  );
}

// Title block: wrapped title, short gold rule. Returns the y where the body can start.
export function headerHeight(title) {
  const n = wrap(title, W - PAD * 2, 34, 2, true).length;
  return 70 + (n - 1) * 42 + 48;
}

export function Frame({ t, title, note, height, children }) {
  const lines = wrap(title, W - PAD * 2, 34, 2, true);
  const ruleY = 70 + (lines.length - 1) * 42 + 22;
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox={`0 0 ${W} ${height}`} width="100%" role="img" aria-label={title}
      style={{ display: "block", height: "auto" }} fontFamily={FONT}>
      <rect width={W} height={height} rx="18" fill={t.bg} />
      <Lines lines={lines} x={PAD} y={70} size={34} lh={1.24} fill={t.ink} weight={800} />
      <rect x={PAD} y={ruleY} width={56} height={4} rx={2} fill={t.gold} />
      {children}
      {note ? <text x={PAD} y={height - 26} fill={t.muted} fontSize={16}>{note.slice(0, 140)}</text> : null}
    </svg>
  );
}

// Indian digit grouping for chart values (12,50,000; 12.5).
export const fmt = (v) => (Number.isFinite(Number(v)) ? Number(v).toLocaleString("en-IN", { maximumFractionDigits: 2 }) : "");

export function niceMax(v) {
  if (!(v > 0)) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  const step = n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10;
  return step * p;
}

// Blend two hex colours (t = 0 → a, 1 → b): a one-hue sequential ramp from the gold to the surface.
export function mix(a, b, k) {
  const p = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const [x, y] = [p(a), p(b)];
  return `#${x.map((v, i) => Math.round(v + (y[i] - v) * k).toString(16).padStart(2, "0")).join("")}`;
}

export function isLight(hex) {
  if (!hex || hex[0] !== "#" || hex.length !== 7) return false;
  const [r, g, b] = [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16) / 255);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b > 0.5;
}

// Text colour that reads on a filled shape, whatever the theme.
export const textOn = (fill) => (isLight(fill) ? "#14151a" : "#f7f4ee");
