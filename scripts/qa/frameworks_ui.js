// "Work along with Akshat": the three workshop frameworks in the browser, as a free member (phone and desktop):
// Akshat's case for each, then "My own client" (written by hand, and suggested from the member's niche).
// Runs against scripts/qa/ai_fault_server.py. Usage: HUB_URL=http://127.0.0.1:8002 node frameworks_ui.js <shots dir>
const { chromium } = require('playwright');
const B = process.env.HUB_URL || 'http://127.0.0.1:8002', OUT = process.argv[2] || '.';
const rows = [];
const check = (name, ok, detail = '') => { rows.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? '  [' + detail + ']' : ''}`); };
const scenario = (name, env) => fetch(`${B}/api/_qa/scenario`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name, env }) });
const vis = async (p, id) => (await p.getByTestId(id).count()) > 0 && p.getByTestId(id).first().isVisible();

async function run(br, view, vp) {
  await scenario('ok');
  const ctx = await br.newContext({ viewport: vp, permissions: ['clipboard-read', 'clipboard-write'], acceptDownloads: true });
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
  check(V('Cases: no "Practice cases" card and no weekly-case upsell, the live case stays'),
    !/Practice cases|A new case every week/.test(await p.locator('main').innerText()) && (await vis(p, 'cases-live')));

  // ---- 1. Market-Fit Venn: incomplete → no Save; wrong answer marked; proposal
  await p.getByTestId('fw-market-fit').click();
  await p.getByTestId('fw-activity').waitFor();
  check(V('F1: Akshat\'s Amul example is shown'), /Amul/.test(await p.locator('body').innerText()));
  check(V('F1: no Save before the activity is done'), !(await vis(p, 'fw-save')) && (await vis(p, 'fw-incomplete')));
  // short, ordinary answers, as members type them (a hidden minimum length once kept Save from ever appearing)
  await p.getByTestId('fw-price-fails').click();                         // a wrong call on purpose
  await p.getByTestId('fw-price-why').fill('Cheaper rivals');
  await p.getByTestId('fw-value-fails').click();
  await p.getByTestId('fw-value-why').fill('Symbian');
  check(V('F1: still no Save with one circle left, and the list says what is missing'), !(await vis(p, 'fw-save'))
    && /Availability: works or fails/.test(await p.getByTestId('fw-incomplete').innerText()) && /Your diagnosis/.test(await p.getByTestId('fw-incomplete').innerText())
    && !/Price/.test(await p.getByTestId('fw-incomplete').innerText()));
  await p.getByTestId('fw-availability-works').click();
  await p.getByTestId('fw-availability-why').fill('Everywhere');
  await p.getByTestId('fw-summary').fill('Value failed');
  check(V('F1: Save appears once every step is done'), await vis(p, 'fw-save'));
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  const s1 = await p.getByTestId('fw-score').innerText();
  check(V('F1: marked 2 of 3 with Akshat\'s read shown'), /2 of 3/.test(s1) && /Symbian/.test(await p.getByTestId('fw-marking').innerText()), s1);
  check(V('F1: Generate a Proposal appears after saving'), await vis(p, 'fw-proposal-go'));
  check(V('F1: Save is replaced by "saved"'), !(await vis(p, 'fw-save')) && (await vis(p, 'fw-saved-note')));
  await p.getByTestId('fw-proposal-go').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  check(V('F1: after generating, a "Proposal created" card with Download, and the pages are not dumped on the page'),
    /Your proposal is ready/.test(await p.getByTestId('fw-proposal').innerText()) && /Proposal created/.test(await p.getByTestId('fw-proposal').innerText())
      && (await vis(p, 'fw-download')) && !(await p.getByTestId('fw-proposal-doc').isVisible()));
  await p.getByTestId('fw-preview').click();
  check(V('F1: "Preview the pages" opens the designed pages'), await p.getByTestId('fw-proposal-doc').isVisible());
  const prop = await p.getByTestId('fw-proposal-doc').innerText();
  check(V('F1: proposal follows the house structure (contents, situation, problem, diagnosis, focus, 90-day plan, next steps)'),
    ['Contents', 'Where we started', 'The real problem', 'Your diagnosis', 'Where to focus', 'Your 90-day', 'Next steps'].every((h) => prop.includes(h)), `${await p.locator('.pd-page').count()} pages`);
  check(V('F1: the cover names the client and the framework'), /Nokia/.test(await p.getByTestId('pd-client').innerText()) && /Market-Fit/.test(await p.getByTestId('pd-page-cover').innerText()));
  check(V('F1: no fee section in the proposal'), !/Investment|fee_from/.test(prop));
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
  await p.getByTestId('fw-reason').fill('Too risky');
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
  await p.getByTestId('fw-action-0').fill('Webinars');
  await p.getByTestId('fw-action-1').fill('HR groups');
  check(V('F3: no Save with two actions, the list asks for Action 3'), !(await vis(p, 'fw-save')) && /Action 3/.test(await p.getByTestId('fw-incomplete').innerText()));
  await p.getByTestId('fw-action-2').fill('Referrals');
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  check(V('F3: Zone 3 + fix the reach = 2 of 2'), /2 of 2/.test(await p.getByTestId('fw-score').innerText()));
  await p.getByTestId('fw-proposal-go').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  await p.getByTestId('fw-preview').click();
  check(V('F3: the verdict page marks "You are here" on Zone 3'), /Zone 3/.test(await p.getByTestId('pd-page-verdict').locator('[data-testid="pd-here"]').locator('xpath=..').innerText()));
  check(V('F3: the 90-day plan has 3 phases and the impact chart is drawn'), (await p.locator('[data-testid^="pd-phase-"]').count()) === 3 && (await vis(p, 'pd-impact')));
  const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 90000 }), p.getByTestId('fw-download').click()]);
  const pdfPath = `${OUT}/proposal-${view}.pdf`; await dl.saveAs(pdfPath);
  const head = require('fs').readFileSync(pdfPath).subarray(0, 5).toString();
  const pagesIn = (require('fs').readFileSync(pdfPath).toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  check(V('F3: "Download proposal (PDF)" saves a PDF of the proposal only, one page per designed page'),
    head === '%PDF-' && /^Proposal - .*\.pdf$/.test(dl.suggestedFilename()) && pagesIn === (await p.locator('.pd-page').count()), `${pagesIn} pages · ${dl.suggestedFilename()}`);
  check(V('F3: after the download the card says it was downloaded'), /Downloaded: Proposal - /.test(await p.getByTestId('fw-downloaded').innerText()));
  check(V('F3: the proposal pages fit the screen (no sideways scroll)'), (await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) === 0);
  check(V('F3: free account, 3 of 6 proposals used: says so'), /3 of 6 free framework proposals used/.test(await p.locator('body').innerText()));
  // change the answer WITHOUT saving, then Generate again: it must save the change and write from the new answer
  await p.getByTestId('fw-zone-2').click();
  await p.getByTestId('fw-fix-offer').click();
  check(V('F3: unsaved changes: the proposal says it uses the saved answer, the button offers to save first'),
    (await vis(p, 'fw-proposal-unsaved')) && /Save changes and generate again/.test(await p.getByTestId('fw-proposal-again').innerText()));
  await p.getByTestId('fw-action-2').fill('');
  await p.getByTestId('fw-proposal-again').click();
  check(V('F3: incomplete changes: it says what is missing and makes nothing'),
    /Finish your changes above first: Action 3/.test(await p.locator('body').innerText()) && /3 of 6 free/.test(await p.locator('body').innerText()));
  await p.getByTestId('fw-action-2').fill('Referrals');
  await p.getByTestId('fw-proposal-again').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  await p.getByText('4 of 6 free framework proposals used').first().waitFor({ timeout: 30000 });
  check(V('F3: "Save changes and generate again" saved the new answer and made a fresh proposal from it'),
    /0 of 2/.test(await p.getByTestId('fw-score').innerText()) && !(await vis(p, 'fw-proposal-unsaved'))
      && !/earlier answer/.test(await p.getByTestId('fw-proposal').innerText()) && (await vis(p, 'fw-saved-note')));

  // ---- reload and list
  await p.reload({ waitUntil: 'networkidle' });
  check(V('Reload keeps the answer, the marking and the proposal'), (await vis(p, 'fw-marking')) && (await vis(p, 'fw-proposal')));
  await p.goto(B + '/app/cases', { waitUntil: 'networkidle' });
  const list = await p.getByTestId('cases-frameworks').innerText();
  check(V('Cases shows "Saved" and "Proposal ready" for all three'), (list.match(/Saved/g) || []).length === 3 && (list.match(/Proposal ready/g) || []).length === 3);
  const noSideways = async () => (await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)) === 0;
  check(V('No sideways scroll'), await noSideways());

  // ---- 4. My own client: no niche yet → Starting Point link; write your own (Market-Fit)
  await p.goto(B + '/app/frameworks/market-fit', { waitUntil: 'networkidle' });
  await p.getByTestId('fw-tab-own').click();
  await p.getByTestId('fw-own-start').waitFor();
  check(V('Own: the tab is in the address (?case=own)'), /case=own/.test(p.url()));
  check(V('Own: no niche → link to Starting Point, and "Write my own client"'), (await vis(p, 'fw-own-start-link')) && (await vis(p, 'fw-own-write')));
  await p.getByTestId('fw-own-write').click();
  check(V('Own: the exercise waits until the case is filled'), (await vis(p, 'fw-case-incomplete')) && !(await vis(p, 'fw-save')));
  await p.getByTestId('fw-case-client').fill('a family-run sweet shop chain in Pune');
  await p.getByTestId('fw-case-product').fill('dry-fruit mithai gift boxes');
  await p.getByTestId('fw-case-region').fill('Hyderabad');
  await p.getByTestId('fw-case-situation').fill('Four shops in Pune, 20 years old, loved for Diwali gift boxes. The owner wants to sell the boxes in Hyderabad.');
  check(V('Own: the Venn talks about the new region'), /Works in Hyderabad/.test(await p.getByTestId('fw-activity').innerText()) && !/Nokia/.test(await p.getByTestId('fw-activity').innerText()));
  await p.getByTestId('fw-price-works').click();
  await p.getByTestId('fw-price-why').fill('Priced like the local mithai shops there.');
  await p.getByTestId('fw-value-works').click();
  await p.getByTestId('fw-value-why').fill('Dry-fruit boxes are a gifting staple there too.');
  await p.getByTestId('fw-availability-fails').click();
  await p.getByTestId('fw-availability-why').fill('No shop or delivery partner in Hyderabad yet.');
  await p.getByTestId('fw-summary').fill('Price and value hold; availability is the gap to close before launching.');
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  check(V('Own F1: saved and read by the rule (2 of 3 circles hold, availability)'),
    /2 of 3/.test(await p.getByTestId('fw-score').innerText()) && /availability/i.test(await p.getByTestId('fw-read').innerText()));
  await p.getByTestId('fw-proposal-go').click();
  await p.getByTestId('fw-proposal').waitFor({ timeout: 30000 });
  check(V('Own F1: proposal made for my client'), /sweet shop/.test(await p.getByTestId('fw-proposal').innerText()) && /sweet shop/.test(await p.getByTestId('fw-proposal-doc').textContent()));
  await p.reload({ waitUntil: 'networkidle' });
  check(V('Own F1: reload keeps the own tab, case, marking and proposal'),
    (await vis(p, 'fw-own-situation')) && (await vis(p, 'fw-marking')) && (await vis(p, 'fw-proposal')));
  await p.getByTestId('fw-tab-akshat').click();
  await p.getByTestId('fw-own-start').waitFor({ state: 'detached' });
  check(V('Own F1: Akshat\'s case and answer are still there on its tab'),
    /Nokia/.test(await p.getByTestId('fw-activity').innerText()) && /3 of 3/.test(await p.getByTestId('fw-score').innerText()));

  // ---- 5. With a niche: suggest a client (Concentration), the table follows the sources
  const snap = await (await p.request.post(B + '/api/start/snapshot', { data: { experiences: ['Retail operations', 'Franchise growth', 'Pricing'], enjoy: [0], industry: 'Retail', years: 18 } })).json();
  await p.request.post(`${B}/api/start/snapshot/${snap.id}/choose`, { data: { index: 0 } });
  await p.goto(B + '/app/frameworks/concentration-risk?case=own', { waitUntil: 'networkidle' });
  check(V('Own F2: my niche is named'), await vis(p, 'fw-own-niche'));
  await scenario('ok', { SEARCH_MODE: 'off' });          // the web search can't run → no real company → busy, go kept
  await p.getByTestId('fw-own-suggest').click();
  await p.getByText('The AI is busy right now').waitFor({ timeout: 30000 });
  check(V('Own F2: search failure on suggest shows the busy message, no case'), !(await vis(p, 'fw-case-editor')));
  await scenario('ok', { SEARCH_MODE: 'fake' });
  await p.getByTestId('fw-own-suggest').click();
  await p.getByTestId('fw-case-editor').waitFor({ timeout: 30000 });
  const n0 = await p.locator('[data-testid^="fw-pct-"]').count();
  check(V('Own F2: suggested client fills the editor, one % box per source'), n0 === 3 && (await p.getByTestId('fw-case-client').inputValue()).length > 3, `rows=${n0}`);
  check(V('Own F2: the suggestion is shown as a real company, with its sources and estimates'),
    (await vis(p, 'fw-real')) && (await p.locator('[data-testid="fw-refs"] a[href^="http"]').count()) >= 1 && (await vis(p, 'fw-estimates')));
  await p.getByTestId('fw-pct-0').fill('45'); await p.getByTestId('fw-pct-1').fill('30'); await p.getByTestId('fw-pct-2').fill('25');
  await p.getByTestId('fw-rec-wait').click();
  await p.getByTestId('fw-reason').fill('45% comes from one corporate client; losing it would take almost half the revenue.');
  await p.getByTestId('fw-target').fill('35'); await p.getByTestId('fw-months').fill('12');
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  check(V('Own F2: checked by the rules, 5 of 5'), /5 of 5/.test(await p.getByTestId('fw-score').innerText()));
  await p.getByTestId('fw-case-edit').click();
  await p.getByTestId('fw-case-src-add').click();
  check(V('Own F2: a blank new source pauses the exercise (no Save)'), (await vis(p, 'fw-case-incomplete')) && !(await vis(p, 'fw-save')));
  check(V('Own F2: while the case differs from the saved one, the marking is labelled as the saved client\'s'), await vis(p, 'fw-own-old'));
  await p.getByTestId('fw-case-src-name-3').fill('Festive pop-up stalls');
  await p.getByTestId('fw-case-src-amt-3').fill('1000000');
  check(V('Own F2: once named, the table has 4 rows and waits for the new %'),
    (await p.locator('[data-testid^="fw-pct-"]').count()) === 4 && !(await vis(p, 'fw-save')));
  await p.getByTestId('fw-pct-0').fill('40.9'); await p.getByTestId('fw-pct-1').fill('27.3'); await p.getByTestId('fw-pct-2').fill('22.7'); await p.getByTestId('fw-pct-3').fill('9.1');
  check(V('Own F2: filled again → "Save changes"'), /Save changes/.test(await p.getByTestId('fw-save').innerText()));
  await p.getByTestId('fw-save').click();
  await p.waitForTimeout(800);
  check(V('Own F2: re-marked on 4 sources (6 checks)'), /of 6/.test(await p.getByTestId('fw-score').innerText()));
  check(V('Own F2: after saving, the "saved client" label is gone'), !(await vis(p, 'fw-own-old')));

  // ---- 6. Compass on a suggested client
  await p.goto(B + '/app/frameworks/growth-compass?case=own', { waitUntil: 'networkidle' });
  await p.getByTestId('fw-own-hint').fill('a yoga studio in Kochi');
  await p.getByTestId('fw-own-suggest').click();
  await p.getByTestId('fw-case-editor').waitFor({ timeout: 30000 });
  check(V('Own F3: the compass shows the client\'s numbers and research'), /Research says/.test(await p.getByTestId('fw-activity').innerText()));
  await p.getByTestId('fw-zone-2').click();
  await p.getByTestId('fw-fix-offer').click();
  await p.getByTestId('fw-action-0').fill('Add a free first class with a follow-up call');
  await p.getByTestId('fw-action-1').fill('Package a 3-month plan with a clear outcome');
  await p.getByTestId('fw-action-2').fill('Call every trial guest within a day');
  await p.getByTestId('fw-save').click();
  await p.getByTestId('fw-marking').waitFor();
  check(V('Own F3: high reach + low conversion = Zone 2, fix the offer: 2 of 2'), /2 of 2/.test(await p.getByTestId('fw-score').innerText()));
  check(V('Own F3: no sideways scroll on the case editor'), await noSideways());
  await p.screenshot({ path: `${OUT}/fw-own-${view}.png`, fullPage: true });
  await p.goto(B + '/app/cases', { waitUntil: 'networkidle' });
  check(V('Cases shows the own client for all three'), ((await p.getByTestId('cases-frameworks').innerText()).match(/Own case:/g) || []).length === 3);
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
