// Visual Builder diagrams: 2x2 matrix, process, pyramid, funnel, mind map (logic tree), comparison table.
// Each takes the stored spec `s` and a palette `t` (theme.jsx) and draws one self-contained SVG.
import { Frame, Lines, PAD, W, headerHeight, mix, textOn, wrap } from "./theme";

export function Matrix({ s, t }) {
  const top = headerHeight(s.title);
  const size = 620;
  const x0 = (W - size) / 2 + 40;
  const y0 = top + 10;
  const half = size / 2;
  const g = 3;
  const H = y0 + size + 130;
  const quads = [[0, 0], [1, 0], [0, 1], [1, 1]];
  const placed = [];
  const items = (s.items || []).map((it) => {
    const cx = x0 + (it.x / 100) * size;
    const cy = y0 + ((100 - it.y) / 100) * size;
    const right = it.x < 66;
    let ly = cy + 6;
    for (const p of placed) if (p.right === right && Math.abs(p.ly - ly) < 22 && Math.abs(p.cx - cx) < 220) ly = p.ly + 22;
    placed.push({ cx, ly, right });
    return { ...it, cx, cy, ly, right };
  });
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {quads.map(([c, r], i) => (
        <g key={i}>
          <rect x={x0 + c * (half + g)} y={y0 + r * (half + g)} width={half - g} height={half - g} rx={12}
            fill={i === 1 ? t.goldTint : t.panel} />
          <text x={x0 + c * (half + g) + 18} y={y0 + r * (half + g) + 32} fill={i === 1 ? t.gold : t.muted} fontSize={14}
            fontWeight={700} letterSpacing="1.6">{String(s.quadrants?.[i] || "").toUpperCase()}</text>
        </g>
      ))}
      <text x={x0} y={y0 + size + 34} fill={t.muted} fontSize={15}>{s.x_axis?.low}</text>
      <text x={x0 + size} y={y0 + size + 34} fill={t.muted} fontSize={15} textAnchor="end">{s.x_axis?.high} →</text>
      <text x={x0 + size / 2} y={y0 + size + 70} fill={t.ink} fontSize={18} fontWeight={700} textAnchor="middle">{s.x_axis?.label}</text>
      <text x={x0 - 16} y={y0 + size} fill={t.muted} fontSize={15} textAnchor="end">{s.y_axis?.low}</text>
      <text x={x0 - 16} y={y0 + 16} fill={t.muted} fontSize={15} textAnchor="end">↑ {s.y_axis?.high}</text>
      <text transform={`translate(${x0 - 120} ${y0 + size / 2}) rotate(-90)`} fill={t.ink} fontSize={18} fontWeight={700}
        textAnchor="middle">{s.y_axis?.label}</text>
      {items.map((it, i) => (
        <g key={i}>
          <title>{`${it.label}: ${s.x_axis?.label} ${it.x}, ${s.y_axis?.label} ${it.y}`}</title>
          <circle cx={it.cx} cy={it.cy} r={9} fill={t.gold} stroke={t.bg} strokeWidth={3} />
          <text x={it.right ? it.cx + 16 : it.cx - 16} y={it.ly} fill={t.ink} fontSize={17} fontWeight={600}
            textAnchor={it.right ? "start" : "end"}>{it.label}</text>
        </g>
      ))}
    </Frame>
  );
}

export function Process({ s, t }) {
  const steps = s.steps || [];
  const n = steps.length || 1;
  const top = headerHeight(s.title);
  const colW = (W - PAD * 2) / n;
  const r = 30;
  const cy = top + 46;
  const lay = steps.map((st) => ({
    label: wrap(st.label, colW - 22, 19, 2, true),
    detail: wrap(st.detail, colW - 22, 15, 4),
  }));
  const maxL = Math.max(1, ...lay.map((l) => l.label.length));
  const maxD = Math.max(0, ...lay.map((l) => l.detail.length));
  const ly = cy + r + 38;
  const dy = ly + maxL * 24 + 8;
  const H = dy + maxD * 20 + 70;
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {steps.map((st, i) => {
        const cx = PAD + colW * i + colW / 2;
        return (
          <g key={i}>
            <title>{`${i + 1}. ${st.label}${st.detail ? ` — ${st.detail}` : ""}`}</title>
            {i < n - 1 && (
              <>
                <line x1={cx + r + 10} y1={cy} x2={cx + colW - r - 16} y2={cy} stroke={t.lineStrong} strokeWidth={2.5} strokeLinecap="round" />
                <path d={`M ${cx + colW - r - 22} ${cy - 6} L ${cx + colW - r - 13} ${cy} L ${cx + colW - r - 22} ${cy + 6}`}
                  fill="none" stroke={t.lineStrong} strokeWidth={2.5} strokeLinecap="round" strokeLinejoin="round" />
              </>
            )}
            <circle cx={cx} cy={cy} r={r} fill={i === 0 ? t.gold : t.bg} stroke={t.gold} strokeWidth={2.5} />
            <text x={cx} y={cy + 8} fill={i === 0 ? textOn(t.gold) : t.gold} fontSize={22} fontWeight={800} textAnchor="middle">{i + 1}</text>
            <Lines lines={lay[i].label} x={cx} y={ly} size={19} fill={t.ink} weight={700} anchor="middle" />
            <Lines lines={lay[i].detail} x={cx} y={dy} size={15} fill={t.muted} anchor="middle" />
          </g>
        );
      })}
    </Frame>
  );
}

export function Pyramid({ s, t }) {
  const levels = s.levels || [];
  const n = levels.length || 1;
  const top = headerHeight(s.title);
  const lvH = 86;
  const gap = 6;
  const pyrW = 500;
  const apexX = PAD + pyrW / 2;
  const y0 = top + 12;
  const Hp = n * lvH + (n - 1) * gap;
  const wAt = (y) => (pyrW * (y - y0)) / Hp;
  const colX = PAD + pyrW + 70;
  const colW = W - PAD - colX;
  const H = y0 + Hp + 80;
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {levels.map((lv, i) => {
        const yt = y0 + i * (lvH + gap);
        const yb = yt + lvH;
        const [wt, wb] = [wAt(yt), wAt(yb)];
        const fill = i === 0 ? t.gold : mix(t.gold, t.bg, 0.3 + (0.5 * i) / Math.max(1, n - 1));
        const ym = (yt + yb) / 2;
        const edge = apexX + (wAt(ym) / 2);
        const detail = wrap(lv.detail, colW, 16, 2);
        return (
          <g key={i}>
            <title>{`${lv.label}${lv.detail ? ` — ${lv.detail}` : ""}`}</title>
            <polygon points={`${apexX - wt / 2},${yt} ${apexX + wt / 2},${yt} ${apexX + wb / 2},${yb} ${apexX - wb / 2},${yb}`} fill={fill} />
            {i > 0 && <text x={apexX} y={ym + 8} fill={textOn(fill)} fontSize={20} fontWeight={800}
              textAnchor="middle">{i + 1}</text>}
            <line x1={edge + 10} y1={ym} x2={colX - 14} y2={ym} stroke={t.lineStrong} strokeWidth={1.5} />
            <text x={colX} y={ym - (detail.length ? 6 : -6)} fill={t.ink} fontSize={21} fontWeight={700}>{lv.label}</text>
            <Lines lines={detail} x={colX} y={ym + 20} size={16} fill={t.muted} />
          </g>
        );
      })}
    </Frame>
  );
}

export function Funnel({ s, t }) {
  const st = s.stages || [];
  const n = st.length || 1;
  const top = headerHeight(s.title);
  const barH = 70;
  const gap = 8;
  const areaW = 680;
  const cx = PAD + areaW / 2;
  const y0 = top + 12;
  const colX = PAD + areaW + 48;
  const colW = W - PAD - colX;
  const H = y0 + n * (barH + gap) + 64;
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {st.map((x, i) => {
        const w = areaW * (1 - (0.55 * i) / Math.max(1, n - 1));
        const y = y0 + i * (barH + gap);
        const fill = mix(t.gold, t.bg, (0.62 * i) / Math.max(1, n - 1));
        const ym = y + barH / 2;
        const detail = wrap(x.detail, colW, 16, 2);
        return (
          <g key={i}>
            <title>{`${x.label}${x.value ? `: ${x.value}` : ""}${x.detail ? ` — ${x.detail}` : ""}`}</title>
            <rect x={cx - w / 2} y={y} width={w} height={barH} rx={10} fill={fill} />
            <text x={cx} y={ym + 7} fill={textOn(fill)} fontSize={19} fontWeight={700} textAnchor="middle">
              {wrap(x.label, w - 28, 19, 1, true)[0]}
            </text>
            {x.value ? <text x={colX} y={ym + (detail.length ? -4 : 9)} fill={t.gold} fontSize={26} fontWeight={800}>{x.value}</text> : null}
            <Lines lines={detail} x={colX} y={x.value ? ym + 20 : ym + 6 - (detail.length - 1) * 10} size={16} fill={t.muted} />
          </g>
        );
      })}
    </Frame>
  );
}

// Mind map drawn as a logic tree: centre idea → branches → leaves, left to right (reads well on a slide and a phone).
export function MindMap({ s, t }) {
  const br = s.branches || [];
  const top = headerHeight(s.title);
  const slot = (b) => Math.max(96, (b.leaves?.length || 0) * 32 + 32);
  const bodyH = Math.max(280, br.reduce((a, b) => a + slot(b), 0));
  const y0 = top + 8;
  const cy = y0 + bodyH / 2;
  const cW = 250;
  const cH = 96;
  const bX = PAD + cW + 70;
  const bW = 250;
  const bH = 60;
  const leafX = bX + bW + 56;
  const leafW = W - PAD - leafX;
  const centre = wrap(s.centre, cW - 32, 22, 2, true);
  let acc = y0;
  const rows = br.map((b) => {
    const h = slot(b);
    const by = acc + h / 2;
    acc += h;
    return { ...b, by };
  });
  const curve = (x1, y1, x2, y2) => `M ${x1} ${y1} C ${(x1 + x2) / 2} ${y1}, ${(x1 + x2) / 2} ${y2}, ${x2} ${y2}`;
  const H = y0 + bodyH + 70;
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {rows.map((b, i) => (
        <g key={i}>
          <path d={curve(PAD + cW, cy, bX, b.by)} fill="none" stroke={t.goldDeep} strokeWidth={2.5} />
          {(b.leaves || []).map((lf, j) => {
            const ly = b.by + (j - ((b.leaves.length - 1) / 2)) * 32;
            return (
              <g key={j}>
                <path d={curve(bX + bW, b.by, leafX - 10, ly)} fill="none" stroke={t.lineStrong} strokeWidth={1.5} />
                <circle cx={leafX - 6} cy={ly} r={3.5} fill={t.gold} />
                <text x={leafX + 4} y={ly + 6} fill={t.ink} fontSize={16}>{wrap(lf, leafW, 16, 1)[0]}</text>
              </g>
            );
          })}
          <title>{`${b.label}: ${(b.leaves || []).join(", ")}`}</title>
          <rect x={bX} y={b.by - bH / 2} width={bW} height={bH} rx={14} fill={t.panel} stroke={t.gold} strokeWidth={1.5} />
          <Lines lines={wrap(b.label, bW - 28, 18, 2, true)} x={bX + bW / 2}
            y={b.by + 6 - (wrap(b.label, bW - 28, 18, 2, true).length - 1) * 11} size={18} fill={t.ink} weight={700} anchor="middle" />
        </g>
      ))}
      <rect x={PAD} y={cy - cH / 2} width={cW} height={cH} rx={18} fill={t.gold} />
      <Lines lines={centre} x={PAD + cW / 2} y={cy + 8 - (centre.length - 1) * 13} size={22} fill={textOn(t.gold)} weight={800} anchor="middle" />
    </Frame>
  );
}

export function Comparison({ s, t }) {
  const cols = s.columns || [];
  const rows = s.rows || [];
  const top = headerHeight(s.title);
  const labelW = 270;
  const colW = (W - PAD * 2 - labelW) / Math.max(1, cols.length);
  const heads = cols.map((c) => wrap(c, colW - 24, 19, 2, true));
  const headH = Math.max(1, ...heads.map((h) => h.length)) * 24 + 30;
  let y = top + 8 + headH;
  const lay = rows.map((r) => {
    const label = wrap(r.label, labelW - 24, 18, 3, true);
    const cells = (r.cells || []).map((c) => wrap(c, colW - 28, 17, 3));
    const lines = Math.max(label.length, ...cells.map((c) => c.length), 1);
    const h = Math.max(60, lines * 23 + 30);
    const row = { label, cells, y, h };
    y += h;
    return row;
  });
  const H = y + 70;
  const hy = top + 8;
  return (
    <Frame t={t} title={s.title} note={s.note} height={H}>
      {heads.map((h, j) => (
        <Lines key={j} lines={h} x={PAD + labelW + colW * j + colW / 2} y={hy + 30} size={19} fill={t.ink} weight={800} anchor="middle" />
      ))}
      <rect x={PAD} y={hy + headH - 3} width={W - PAD * 2} height={3} rx={1.5} fill={t.gold} />
      {lay.map((r, i) => (
        <g key={i}>
          {i % 2 === 0 && <rect x={PAD} y={r.y} width={W - PAD * 2} height={r.h} fill={t.panel} />}
          <Lines lines={r.label} x={PAD + 16} y={r.y + 36} size={18} fill={t.ink} weight={700} />
          {r.cells.map((c, j) => (
            <g key={j}>
              <title>{`${rows[i].label} · ${cols[j]}: ${rows[i].cells[j]}`}</title>
              <Lines lines={c} x={PAD + labelW + colW * j + colW / 2} y={r.y + 36} size={17} fill={t.ink} anchor="middle" />
            </g>
          ))}
          <line x1={PAD} y1={r.y + r.h} x2={W - PAD} y2={r.y + r.h} stroke={t.line} strokeWidth={1} />
        </g>
      ))}
    </Frame>
  );
}
