// Visual Builder charts (bar | line | pie) drawn from the member's own numbers only.
// Thin marks, rounded data-ends, hairline grid, one axis, a legend for 2+ series, dashes as a second cue on lines,
// names and % on every pie slice, and a hover title on every mark.
import { DASHES, Frame, Lines, PAD, W, fmt, headerHeight, niceMax, seriesColors, textOn, wrap } from "./theme";

function colPath(x, y, w, h, r, up) {
  // Column with rounded data-end, square at the baseline (y = baseline when up=false).
  const rr = Math.min(r, w / 2, Math.abs(h));
  if (up) {
    return `M ${x} ${y + h} L ${x} ${y + rr} Q ${x} ${y} ${x + rr} ${y} L ${x + w - rr} ${y} Q ${x + w} ${y} ${x + w} ${y + rr} L ${x + w} ${y + h} Z`;
  }
  return `M ${x} ${y} L ${x + w} ${y} L ${x + w} ${y + h - rr} Q ${x + w} ${y + h} ${x + w - rr} ${y + h} L ${x + rr} ${y + h} Q ${x} ${y + h} ${x} ${y + h - rr} Z`;
}

function Legend({ series, colors, x1, y, line, t }) {
  const widths = series.map((s) => 34 + s.name.length * 8.5);
  let x = x1 - widths.reduce((a, w) => a + w + 18, 0);
  const items = series.map((s, i) => {
    const out = { ...s, i, x };
    x += widths[i] + 18;
    return out;
  });
  return (
    <g>
      {items.map((s) => (
        <g key={s.i}>
          {line
            ? <line x1={s.x} y1={y - 5} x2={s.x + 24} y2={y - 5} stroke={colors[s.i]} strokeWidth={3} strokeDasharray={DASHES[s.i] || undefined} strokeLinecap="round" />
            : <rect x={s.x + 4} y={y - 13} width={16} height={16} rx={4} fill={colors[s.i]} />}
          <text x={s.x + 32} y={y} fill={t.ink} fontSize={15}>{s.name}</text>
        </g>
      ))}
    </g>
  );
}

function XY({ s, t }) {
  const line = s.chart === "line";
  const series = s.series || [];
  const labels = s.labels || [];
  const colors = seriesColors(t);
  const top = headerHeight(s.title);
  const H = 700;
  const legend = series.length > 1;
  const x0 = PAD + 78;
  const x1 = W - PAD - (line ? 70 : 0);
  const y0 = top + (legend ? 46 : 20);
  const y1 = H - 120;
  const all = series.flatMap((x) => x.values);
  const span = Math.max(0, ...all) - Math.min(0, ...all);
  const step = niceMax(span / 4 || 1);
  const lo = Math.floor(Math.min(0, ...all) / step) * step;
  const hi = Math.max(lo + step, Math.ceil(Math.max(0, ...all) / step) * step);
  const Y = (v) => y1 - ((v - lo) / (hi - lo || 1)) * (y1 - y0);
  const ticks = Array.from({ length: Math.round((hi - lo) / step) + 1 }, (_, i) => lo + step * i);
  const band = (x1 - x0) / Math.max(1, labels.length);
  const cxAt = (i) => x0 + band * i + band / 2;
  const nS = Math.max(1, series.length);
  const barW = Math.min(56, (band * 0.7 - (nS - 1) * 4) / nS);
  const showTips = !line && nS === 1 && labels.length <= 10;
  // End labels on lines: nudge apart when two series end close together.
  const endShift = series.map(() => 0);
  if (line) {
    const ends = series.map((ser, si) => ({ si, y: Y(ser.values[ser.values.length - 1]) })).sort((a, b) => a.y - b.y);
    for (let k = 1; k < ends.length; k += 1) {
      const prev = ends[k - 1].y + endShift[ends[k - 1].si];
      if (ends[k].y - prev < 20) endShift[ends[k].si] = prev + 20 - ends[k].y;
    }
  }
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {s.unit ? <text x={PAD} y={y0 - 16} fill={t.muted} fontSize={14}>{s.unit}</text> : null}
      {legend && <Legend series={series} colors={colors} x1={W - PAD} y={top + 6} line={line} t={t} />}
      {ticks.map((v, i) => (
        <g key={i}>
          <line x1={x0} y1={Y(v)} x2={x1} y2={Y(v)} stroke={t.line} strokeWidth={1} />
          <text x={x0 - 12} y={Y(v) + 5} fill={t.muted} fontSize={14} textAnchor="end">{fmt(Math.round(v * 100) / 100)}</text>
        </g>
      ))}
      <line x1={x0} y1={Y(0)} x2={x1} y2={Y(0)} stroke={t.lineStrong} strokeWidth={1.5} />
      {labels.map((l, i) => (
        <Lines key={i} lines={wrap(l, band - 8, 15, 2)} x={cxAt(i)} y={y1 + 30} size={15} fill={t.muted} anchor="middle" />
      ))}
      {!line && series.map((ser, si) => ser.values.map((v, i) => {
        const x = cxAt(i) - (nS * barW + (nS - 1) * 4) / 2 + si * (barW + 4);
        const up = v >= 0;
        const yv = Y(v);
        const yb = Y(0);
        return (
          <g key={`${si}-${i}`}>
            <title>{`${labels[i]}${nS > 1 ? ` · ${ser.name}` : ""}: ${fmt(v)}${s.unit ? ` ${s.unit}` : ""}`}</title>
            <path d={up ? colPath(x, yv, barW, yb - yv, 6, true) : colPath(x, yb, barW, yv - yb, 6, false)} fill={colors[si]} />
            {showTips && <text x={x + barW / 2} y={up ? yv - 10 : yv + 22} fill={t.ink} fontSize={15} fontWeight={700} textAnchor="middle">{fmt(v)}</text>}
          </g>
        );
      }))}
      {line && series.map((ser, si) => {
        const pts = ser.values.map((v, i) => [cxAt(i), Y(v)]);
        const last = pts[pts.length - 1];
        const endY = last ? last[1] + 5 + endShift[si] : 0;
        return (
          <g key={si}>
            <path d={pts.map((p, i) => `${i ? "L" : "M"} ${p[0]} ${p[1]}`).join(" ")} fill="none" stroke={colors[si]}
              strokeWidth={3} strokeLinejoin="round" strokeLinecap="round" strokeDasharray={DASHES[si] || undefined} />
            {pts.map((p, i) => (
              <g key={i}>
                <title>{`${labels[i]}${nS > 1 ? ` · ${ser.name}` : ""}: ${fmt(ser.values[i])}${s.unit ? ` ${s.unit}` : ""}`}</title>
                <circle cx={p[0]} cy={p[1]} r={6} fill={colors[si]} stroke={t.bg} strokeWidth={3} />
              </g>
            ))}
            {last && <text x={last[0] + 14} y={endY} fill={t.ink} fontSize={15} fontWeight={700}>{fmt(ser.values[ser.values.length - 1])}</text>}
          </g>
        );
      })}
    </Frame>
  );
}

function Pie({ s, t }) {
  const vals = (s.series?.[0]?.values || []).map((v) => Math.max(0, v));
  const labels = s.labels || [];
  const total = vals.reduce((a, b) => a + b, 0) || 1;
  const colors = seriesColors(t);
  const top = headerHeight(s.title);
  const r = 200;
  const cx = PAD + r + 20;
  const cy = top + 20 + r;
  const H = cy + r + 90;
  let a0 = -Math.PI / 2;
  const slices = vals.map((v, i) => {
    const a1 = a0 + (v / total) * Math.PI * 2;
    const out = { v, i, a0, a1, pct: (v * 100) / total };
    a0 = a1;
    return out;
  });
  const pt = (a, rr = r) => [cx + rr * Math.cos(a), cy + rr * Math.sin(a)];
  const lx = cx + r + 80;
  const rowH = Math.min(52, (2 * r) / Math.max(1, labels.length));
  const ly0 = cy - (rowH * labels.length) / 2 + rowH / 2;
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {slices.map((sl) => {
        const [x1, y1] = pt(sl.a0);
        const [x2, y2] = pt(sl.a1);
        const large = sl.a1 - sl.a0 > Math.PI ? 1 : 0;
        const mid = (sl.a0 + sl.a1) / 2;
        const [tx, ty] = pt(mid, r * 0.64);
        const fill = colors[sl.i];
        const tip = `${labels[sl.i]}: ${fmt(sl.v)}${s.unit ? ` ${s.unit}` : ""} (${Math.round(sl.pct)}%)`;
        return (
          <g key={sl.i}>
            <title>{tip}</title>
            {sl.pct >= 99.99
              ? <circle cx={cx} cy={cy} r={r} fill={fill} />
              : sl.v > 0 && <path d={`M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2} Z`} fill={fill} stroke={t.bg} strokeWidth={3} strokeLinejoin="round" />}
            {sl.pct >= 7 && <text x={tx} y={ty + 6} fill={textOn(fill)} fontSize={17} fontWeight={800} textAnchor="middle">{Math.round(sl.pct)}%</text>}
          </g>
        );
      })}
      {labels.map((l, i) => {
        const y = ly0 + i * rowH;
        return (
          <g key={i}>
            <rect x={lx} y={y - 12} width={18} height={18} rx={4} fill={colors[i]} stroke={t.lineStrong} strokeWidth={colors[i] === t.panel ? 1 : 0} />
            <text x={lx + 30} y={y + 3} fill={t.ink} fontSize={18} fontWeight={700}>{wrap(l, 300, 18, 1, true)[0]}</text>
            <text x={W - PAD} y={y + 3} fill={t.muted} fontSize={17} textAnchor="end">{fmt(vals[i])}{s.unit ? ` ${s.unit}` : ""} · {Math.round(slices[i]?.pct || 0)}%</text>
          </g>
        );
      })}
    </Frame>
  );
}

export default function Chart({ s, t }) {
  return s.chart === "pie" ? <Pie s={s} t={t} /> : <XY s={s} t={t} />;
}
