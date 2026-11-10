// "Work along with Akshat": the three workshop frameworks in the browser, as a free member (phone and desktop).
// Runs against scripts/qa/ai_fault_server.py. Usage: HUB_URL=http://127.0.0.1:8002 node frameworks_ui.js <shots dir>
const { chromium } = require('playwright');
const B = process.env.HUB_URL || 'http://127.0.0.1:8002', OUT = process.argv[2] || '.';
const rows = [];
const check = (name, ok, detail = '') => { rows.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? '  [' + detail + ']' : ''}`); };
const scenario = (name) => fetch(`${B}/api/_qa/scenario`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }) });
const vis = async (p, id) => (await p.getByTestId(id).count()) > 0 && p.getByTestId(id).first().isVisible();

async function run(br, view, vp) {
  await scenario('ok');
  const ctx = await br.newContext({ viewport: vp, permissions: ['clipboard-read', 'clipboard-write'] });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error' && !/status of (4\d\d|503)/.test(m.text())) errs.push(m.text().slice(0, 120)); });
  await p.request.post(B + '/api/qa/login', { data: { plan: 'free', phone: `+9188${String(Date.now()).slice(-8)}` } });
  const V = (s) => `${view.padEnd(7)} ${s}`;

  // ---- Cases shows the three frameworks
  await p.goto(B + '/app/cases', { waitUntil: 'networkidle' });
  const items = await p.locator('[data-testid^="fw-"][href]').count();
  check(V('Cases lists the 3 workshop frameworks first'), items === 3 && (await vis(p, 'cases-frameworks')));

  // ---- 1. Market-Fit Venn: incomplete → no Save; wrong answer marked; proposal
  await p.getByTestId('fw-market-fit').click();
  await p.getByTestId('fw-activity').waitFor();
  check(V('F1: Akshat\'s Amul example is shown'), /Amul/.test(await p.locator('body').innerText()));
  check(V('F1: no Save before the activity is done'), !(await vis(p, 'fw-save')) && (await vis(p, 'fw-incomplete')));
  await p.getByTestId('fw-price-fails').click();                         // a wrong call on purpose
  await p.getByTestId('fw-price-why').fill('Smartphones from others were cheaper later.');
  await p.getByTestId('fw-value-fails').click();
  await p.getByTestId('fw-value-why').fill('Stayed on Symbian and was late to touchscreens.');
  check(V('F1: still no Save with one circle left'), !(await vis(p, 'fw-save')));
  await p.getByTestId('fw-availability-works').click();
  await p.getByTestId('fw-availability-why').fill('Sold everywhere, Tier 2 and Tier 3 towns too.');
  await p.getByTestId('fw-summary').fill('The value circle came apart when smartphones arrived; Nokia did not move in time.');
  check(V('F1: Save appears once every step is done'), await vis(p, 'fw-save'));
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  const s1 = await p.getByTestId('fw-score').innerText();
  check(V('F1: marked 2 of 3 with Akshat\'s read shown'), /2 of 3/.test(s1) && /Symbian/.test(await p.getByTestId('fw-marking').innerText()), s1);
  check(V('F1: Generate a Proposal appears after saving'), await vis(p, 'fw-proposal-go'));
  check(V('F1: Save is replaced by "saved"'), !(await vis(p, 'fw-save')) && (await vis(p, 'fw-saved-note')));
  await p.getByTestId('fw-proposal-go').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  const prop = await p.getByTestId('fw-proposal').innerText();
  check(V('F1: proposal has situation, objective, approach, next steps'), ['The situation', 'Objective', 'Approach', 'Next steps'].every((h) => prop.includes(h)));
  await p.getByTestId('fw-price-works').click();                         // change the answer
  check(V('F1: changing the answer brings back "Save changes"'), /Save changes/.test(await p.getByTestId('fw-save').innerText()));
  await p.getByTestId('fw-save').click();
  await p.waitForTimeout(800);
  check(V('F1: now 3 of 3, and the proposal says it is from the earlier answer'),
    /3 of 3/.test(await p.getByTestId('fw-score').innerText()) && /earlier answer/.test(await p.locator('body').innerText()));
  await p.screenshot({ path: `${OUT}/fw1-${view}.png`, fullPage: true });

  // ---- 2. Concentration Risk Rule
  await p.goto(B + '/app/frameworks/concentration-risk', { waitUntil: 'networkidle' });
  await p.getByTestId('fw-pct-0').fill('60');
  const z0 = await p.getByTestId('fw-table').locator('tr').nth(1).innerText();
  check(V('F2: typing 60% shows the red zone live'), /red/i.test(z0));
  await p.getByTestId('fw-pct-1').fill('30');
  await p.getByTestId('fw-pct-2').fill('10');
  await p.getByTestId('fw-rec-wait').click();
  await p.getByTestId('fw-reason').fill('60% of revenue is one developer; if they leave, the firm loses most of its income overnight.');
  await p.getByTestId('fw-target').fill('35');
  check(V('F2: no Save until months are filled'), !(await vis(p, 'fw-save')));
  await p.getByTestId('fw-months').fill('12');
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  check(V('F2: full marks (60/30/10, wait, target ≤40%)'), /5 of 5/.test(await p.getByTestId('fw-score').innerText()));
  const usedNow = async () => p.evaluate(async () => {
    const me = await (await fetch('/api/auth/me')).json();
    const find = (o) => (o && typeof o === 'object') ? ('limits' in o ? o.limits : Object.values(o).map(find).find(Boolean)) : null;
    return (find(me) || {}).fw_proposal?.used;
  });
  const before = await usedNow();
  await scenario('vendor_error');
  await p.getByTestId('fw-proposal-go').click();
  await p.getByText('The AI is busy right now').waitFor({ timeout: 30000 });
  const after = await usedNow();
  check(V('F2: AI failure shows the busy message and the go is kept'), before === 1 && after === 1, `used before=${before} after=${after}`);
  await scenario('ok');
  await p.getByTestId('fw-proposal-go').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  check(V('F2: once the AI is back, the proposal is made'), true);

  // ---- 3. Growth Compass
  await p.goto(B + '/app/frameworks/growth-compass', { waitUntil: 'networkidle' });
  await p.getByTestId('fw-zone-3').click();
  check(V('F3: tapping a zone selects it'), (await p.getByTestId('fw-zone-3').getAttribute('aria-pressed')) === 'true');
  await p.getByTestId('fw-fix-reach').click();
  await p.getByTestId('fw-action-0').fill('Run a free monthly career-switch webinar');
  await p.getByTestId('fw-action-1').fill('Partner with three HR communities');
  check(V('F3: no Save with two actions'), !(await vis(p, 'fw-save')));
  await p.getByTestId('fw-action-2').fill('Ask alumni for referrals with a small reward');
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  check(V('F3: Zone 3 + fix the reach = 2 of 2'), /2 of 2/.test(await p.getByTestId('fw-score').innerText()));
  await p.getByTestId('fw-proposal-go').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  check(V('F3: proposal made'), true);
  check(V('F3: free account after 3 proposals: no "Generate again"'), !(await vis(p, 'fw-proposal-again')));

  // ---- reload and list
  await p.reload({ waitUntil: 'networkidle' });
  check(V('Reload keeps the answer, the marking and the proposal'), (await vis(p, 'fw-marking')) && (await vis(p, 'fw-proposal')));
  await p.goto(B + '/app/cases', { waitUntil: 'networkidle' });
  const list = await p.getByTestId('cases-frameworks').innerText();
  check(V('Cases shows "Saved" and "Proposal ready" for all three'), (list.match(/Saved/g) || []).length === 3 && (list.match(/Proposal ready/g) || []).length === 3);
  check(V('No sideways scroll'), (await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) === 0);
  check(V('No browser errors'), errs.length === 0, errs.join(' | ').slice(0, 200));
  await ctx.close();
}

(async () => {
  const br = await chromium.launch();
  await run(br, 'phone', { width: 390, height: 844 });
  await run(br, 'desktop', { width: 1280, height: 900 });
  await br.close();
  await scenario('ok');
  console.log(`\n${rows.filter(Boolean).length} of ${rows.length} passed`);
})().catch((e) => { console.error('SCRIPT ERROR', e.message.split('\n')[0]); process.exit(1); });
