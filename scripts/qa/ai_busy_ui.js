// AI-failure QA in the browser (phone size), against scripts/qa/ai_fault_server.py.
// For each tool: (1) AI keeps failing → the page tries once more by itself, then shows the busy message next to the
// button and the member keeps their go; (2) AI fails once → the page's own retry recovers with no message;
// (3) AI healthy → the result shows. Usage: HUB_URL=http://127.0.0.1:8002 node ai_busy_ui.js <shots dir>
const { chromium } = require('playwright');
const B = process.env.HUB_URL || 'http://127.0.0.1:8002', OUT = process.argv[2] || '.';
const BUSY = "The AI is busy right now";

const TOOLS = [
  { name: 'Weekly case scoring', path: '/app/cases/retail-chain-margins', api: '/answer', button: 'case-submit',
    fill: async (p) => p.getByTestId('case-answer').fill('The real problem is margin leakage: profit fell from 4% to 1.5% as the new stores opened. Objective: 3% in 90 days. Framework: margin leak check. Do first: fresh produce ordering. Owner: ops head, wastage % weekly.'),
    done: async (p) => (await p.getByText(/model answer|out of 10|\/ 10/i).count()) > 0 },
  { name: 'Offer Card', path: '/app/offer', api: '/api/offer-card', button: 'offer-make',
    fill: async (p) => p.getByTestId('offer-name').fill('90-day plant reset'),
    done: async (p) => (await p.getByTestId('offer-card').count()) > 0 },
];

async function scenario(name) { await fetch(`${B}/api/_qa/scenario`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }) }); }

(async () => {
  const br = await chromium.launch();
  const rows = [];
  let n = 0;
  for (const t of TOOLS) {
    for (const sc of ['vendor_error', 'busy_once', 'ok']) {
      n += 1;
      const ctx = await br.newContext({ viewport: { width: 390, height: 844 } });
      const p = await ctx.newPage();
      const r = await p.request.post(B + '/api/qa/login', { data: { plan: 'l2', phone: `+9182${String(Date.now()).slice(-5)}${n}` } });
      if (!r.ok()) throw new Error('login ' + r.status());
      const calls = [];
      p.on('response', (res) => { if (res.request().method() === 'POST' && res.url().includes(t.api)) calls.push(res.status()); });
      await p.goto(B + t.path, { waitUntil: 'networkidle' });
      await scenario('ok');
      const usedBefore = await p.evaluate(async () => (await (await fetch('/api/auth/me')).json()));
      await t.fill(p);
      await scenario(sc);
      const t0 = Date.now();
      await p.getByTestId(t.button).click();
      // wait for either the busy message or the result (the page retries after 2-6 s)
      await p.waitForFunction((busy) => document.body.innerText.includes(busy) ||
        !!document.querySelector('[data-testid="offer-card"]') || /model answer|out of 10|\/ 10/i.test(document.body.innerText), BUSY, { timeout: 30000 }).catch(() => {});
      await p.waitForTimeout(400);
      const secs = ((Date.now() - t0) / 1000).toFixed(1);
      const busyShown = (await p.getByText(BUSY).count()) > 0;
      const result = await t.done(p);
      let gap = null;
      if (busyShown) {
        const b = await p.getByTestId(t.button).boundingBox();
        const m = await p.getByText(BUSY).first().boundingBox();
        if (b && m) gap = Math.round(Math.abs(m.y - (b.y + b.height)));
      }
      const me = await p.evaluate(async () => (await (await fetch('/api/auth/me')).json()));
      const find = (o, k) => (o && typeof o === 'object') ? (k in o ? o[k] : Object.values(o).map((v) => find(v, k)).find((x) => x !== undefined)) : undefined;
      const lb = find(usedBefore, 'limits') || {}, la = find(me, 'limits') || {};
      const spent = Object.keys(la).filter((k) => (la[k]?.used || 0) !== (lb[k]?.used || 0)).map((k) => `${k}+${la[k].used - (lb[k]?.used || 0)}`);
      await p.screenshot({ path: `${OUT}/busy-${t.name.replace(/\W+/g, '_')}-${sc}.png` });
      const expect = sc === 'vendor_error' ? (busyShown && !result && calls.length === 2 && spent.length === 0)
        : (result && !busyShown && spent.length === 1);
      rows.push({ tool: t.name, scenario: sc, requests: calls.join(','), busyShown, result, secs, gap, spent: spent.join(' ') || '-', pass: expect });
      console.log(`${expect ? 'PASS' : 'FAIL'} ${t.name.padEnd(20)} ${sc.padEnd(12)} requests=[${calls}] busy=${busyShown} result=${result} ${secs}s msgGapPx=${gap} spent=${spent.join(' ') || '-'}`);
      await ctx.close();
    }
  }
  await scenario('ok');
  await br.close();
  console.log(`\n${rows.filter((r) => r.pass).length} of ${rows.length} passed`);
})();
