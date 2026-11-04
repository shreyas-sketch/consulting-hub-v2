// Recharts styling that follows the theme tokens (SVG attributes accept var()).
export const AXIS_TICK = { fontSize: 11, fill: "var(--bz-muted)" };
export const TOOLTIP = {
  contentStyle: {
    background: "var(--bz-raised)", border: "1px solid var(--bz-line)", borderRadius: 12,
    color: "var(--bz-ink)", fontSize: 13,
  },
  labelStyle: { color: "var(--bz-muted)", fontSize: 12, marginBottom: 4 },
  itemStyle: { color: "var(--bz-ink)" },
  cursor: { stroke: "var(--bz-line-strong)", strokeDasharray: "3 3" },
};
export const C = { gold: "var(--bz-gold)", teal: "var(--bz-teal)", miss: "var(--bz-miss)", muted: "var(--bz-muted)", line: "var(--bz-line)", ink: "var(--bz-ink)" };
