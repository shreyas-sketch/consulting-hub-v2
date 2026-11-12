// Live browser walk of the frameworks (phone + desktop), reusing the QA member's saved session (cookies-001.json,
// written by session.py). Usage: node frameworks_walk.js <shots dir>
const { chromium } = require('playwright');
const fs = require('fs');
const U = 'https://consulting-hub-v2-production.up.railway.app', OUT = process.argv[2] || '.';
const jar = JSON.parse(fs.readFileSync(__dirname + '/cookies-001.json', 'utf8'));
const rows = [];
const check = (n, ok, d = '') => { rows.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'} ${n}${d ? '  [' + d + ']' : ''}`); };
const vis = async (p, id) => { try { await p.getByTestId(id).first().waitFor({ timeout: 4000 }); return true; } catch { return false; } };

async function run(br, view, vp, suggest) {
  const ctx = await br.newContext({ viewport: vp, ignoreHTTPSErrors: true,
    proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined });
  await ctx.addCookies(Object.entries(jar).map(([name, value]) => ({ name, value, url: U })));
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error' && !/status of (4\d\d)/.test(m.text())) errs.push(m.text().slice(0, 120)); });
  const V = (s) => `${view.padEnd(7)} ${s}`;
  const side = async () => (await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) === 0;

  await p.goto(U + '/app/cases', { waitUntil: 'networkidle' });
  const main = await p.locator('main').innerText();
  check(V('Cases: 3 frameworks, no Practice cases card'), (await p.locator('[data-testid^="fw-"][href]').count()) === 3 && !/Practice cases/.test(main));
  check(V('Cases: own clients listed'), (main.match(/Own case:/g) || []).length === 3);
  await p.screenshot({ path: `${OUT}/cases-${view}.png`, fullPage: true });

  for (const key of ['market-fit', 'concentration-risk', 'growth-compass']) {
    await p.goto(`${U}/app/frameworks/${key}`, { waitUntil: 'networkidle' });
    check(V(`${key}: Akshat's case shows the saved marking + read`), (await vis(p, 'fw-marking')) && /of/.test(await p.getByTestId('fw-score').innerText()));
    await p.getByTestId('fw-tab-own').click();
    await p.getByTestId('fw-own-start').waitFor();
    check(V(`${key}: own tab names the niche`), /Vendor cost reduction/i.test(await p.getByTestId('fw-own-niche').innerText()));
    // a suggestion not saved yet opens in the editor, with the saved client's marking labelled as such
    check(V(`${key}: own client, marking and proposal shown`), ((await vis(p, 'fw-own-situation')) || (await vis(p, 'fw-own-old')))
      && (await vis(p, 'fw-marking')) && (await vis(p, 'fw-proposal')));
    check(V(`${key}: no sideways scroll`), await side());
    await p.screenshot({ path: `${OUT}/${key}-own-${view}.png`, fullPage: true });
  }
  if (suggest) {   // one real suggestion through the page
    await p.goto(`${U}/app/frameworks/concentration-risk?case=own`, { waitUntil: 'networkidle' });
    await p.getByTestId('fw-own-hint').fill('a sheet-metal stamping unit in Chennai');
    await p.getByTestId('fw-own-suggest').click();
    await p.getByTestId('fw-case-editor').waitFor({ timeout: 90000 });
    const cl = await p.getByTestId('fw-case-client').inputValue();
    const rowsN = await p.locator('[data-testid^="fw-pct-"]').count();
    check(V('Suggest in the page: new client in the editor, one % box per source'), cl.length > 3 && rowsN >= 2, `${cl} · ${rowsN} sources`);
    check(V('Suggest: the old saved answer is not shown as Save-able until redone'), !(await p.getByTestId('fw-save').count()));
    await p.screenshot({ path: `${OUT}/suggest-${view}.png`, fullPage: true });
  }
  check(V('No browser errors'), errs.length === 0, errs.join(' | ').slice(0, 200));
  await ctx.close();
}

(async () => {
  const br = await chromium.launch();
  await run(br, 'phone', { width: 390, height: 844 }, true);
  await run(br, 'desktop', { width: 1280, height: 900 }, false);
  await br.close();
  console.log(`\n${rows.filter(Boolean).length} of ${rows.length} passed`);
})().catch((e) => { console.error('SCRIPT ERROR', e.message.split('\n')[0]); process.exit(1); });
