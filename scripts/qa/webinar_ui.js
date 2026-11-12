// The six webinar tools in the browser, as a free member: Readiness Score, Starting Point, Cases, Meeting Brief,
// LinkedIn Review (quick path; the full page has scripts/qa/linkedin_ui.js) and My Consulting File.
// Runs against scripts/qa/ai_fault_server.py. Usage: HUB_URL=http://127.0.0.1:8002 node webinar_ui.js <shots dir>
const { chromium } = require('playwright');
const B = process.env.HUB_URL || 'http://127.0.0.1:8002', OUT = process.argv[2] || '.';
const rows = [];
const check = (name, ok, detail = '') => { rows.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? '  [' + detail + ']' : ''}`); };
const alertText = (p) => p.locator('[role="alert"]').first().innerText().catch(() => '');
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const go = (p, path) => p.goto(B + path, { waitUntil: 'networkidle' });

async function run(br, view, vp) {
  const ctx = await br.newContext({ viewport: vp });
  const p = await ctx.newPage();
  const errs = [];
  p.on('pageerror', (e) => errs.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error' && !/status of (4\d\d)/.test(m.text())) errs.push(m.text().slice(0, 120)); });
  await p.request.post(B + '/api/qa/login', { data: { plan: 'free', phone: `+9187${String(Date.now()).slice(-8)}` } });
  const V = (s) => `${view.padEnd(7)} ${s}`;

  // ---- My Consulting File, empty
  await go(p, '/app/file');
  const empty = await p.locator('body').innerText();
  check(V('File: a new member sees a helpful empty state'), /nothing|start|yet|empty/i.test(empty) && !/didn't load/.test(empty));

  // ---- 1. Readiness Score
  await go(p, '/app/readiness');
  const dia = p.getByTestId('slider-diagnosis');
  await dia.focus();
  for (let i = 0; i < 3; i++) await p.keyboard.press('ArrowLeft');           // 5 → 2
  await p.getByTestId('slider-pricing').focus();
  await p.keyboard.press('ArrowLeft');                                         // 5 → 4
  await p.getByTestId('readiness-submit').click();
  await p.getByTestId('readiness-result').waitFor();
  const rtext = await p.getByTestId('readiness-result').innerText();
  check(V('Readiness: total 26/60 and band shown'), /26/.test(rtext) && /60/.test(rtext) && /Building/.test(rtext), rtext.slice(0, 60).replace(/\n/g, ' '));
  check(V('Readiness: the two lowest skills are the focus'), /Problem diagnosis/.test(rtext) && /Pricing confidence/.test(rtext));
  check(V('Readiness: the tip names LinkedIn Review'), !/LinkedIn Score/.test(await p.locator('body').innerText()));
  await p.reload({ waitUntil: 'networkidle' });
  check(V('Readiness: result still there after reload'), (await p.getByTestId('readiness-result').count()) === 1);
  check(V('Readiness: free account is not offered a retake'), (await p.getByTestId('readiness-retake').count()) === 0);

  // ---- 2. Starting Point: niche
  await go(p, '/app/start');
  await p.getByTestId('exp-0').fill('Plant operations in auto components');
  await p.getByText('Add another').click();
  await p.getByTestId('exp-1').fill('Vendor development and cost reduction');
  await p.getByTestId('exp-1').locator('xpath=following-sibling::button[1]').click();     // enjoy
  await p.getByLabel('Industry you know best').fill('Auto components');
  await p.getByLabel('Years of experience').fill('60');
  await p.getByTestId('snapshot-run').click();
  await p.waitForTimeout(800);
  const yrs = await alertText(p);
  check(V('Starting Point: 60 years is refused with a plain message'), yrs.length > 0 && !/value_error|less than or equal|\[|\{/.test(yrs), yrs.slice(0, 90));
  await p.getByLabel('Years of experience').fill('19');
  await p.getByTestId('snapshot-run').click();
  await p.getByTestId('niche-0').waitFor({ timeout: 30000 });
  const n = await p.locator('[data-testid^="niche-"]').count();
  check(V('Starting Point: three niche options'), n === 3, `options=${n}`);
  await p.getByTestId('choose-1').click();
  await p.waitForTimeout(500);
  await p.reload({ waitUntil: 'networkidle' });
  const chosen = await p.getByTestId('niche-1').innerText();
  check(V('Starting Point: the chosen option is kept after reload'), /chosen|your niche|selected/i.test(chosen), chosen.slice(0, 50).replace(/\n/g, ' '));
  check(V('Starting Point: a free account is not offered a second snapshot'), (await p.getByTestId('snapshot-again').count()) === 0);

  // ---- 2b. Goal Map
  await p.getByTestId('start-tab-goal').click();
  await p.getByTestId('goal-income').fill('300000');
  await p.getByTestId('goal-fee').fill('50000');
  await p.waitForTimeout(900);
  const live = await p.getByTestId('goal-result').innerText();
  check(V('Goal Map: live numbers while typing (6 clients, 24 calls)'), /\b6\b/.test(live) && /\b24\b/.test(live), live.slice(0, 80).replace(/\n/g, ' '));
  await p.getByTestId('goal-save').click();
  await p.waitForTimeout(600);
  await p.reload({ waitUntil: 'networkidle' });
  await p.getByTestId('start-tab-goal').click();
  check(V('Goal Map: saved goal comes back after reload'), /300,000|3,00,000/.test(await p.locator('body').innerText()));

  // ---- 3. Cases
  await go(p, '/app/cases');
  const cards = p.locator('[data-testid^="case-"]');
  const first = await cards.first().innerText();
  check(V('Cases: the live case is first'), /live/i.test(first), first.slice(0, 50).replace(/\n/g, ' '));
  const lockedCount = await p.locator('text=/₹1,999 plan|Locked|Unlock/').count();
  check(V('Cases: the other cases show as locked'), lockedCount >= 1, `locked markers=${lockedCount}`);
  await go(p, '/app/cases/hospital-claims');
  const lock = await p.locator('body').innerText();
  check(V('Cases: opening a locked case shows the plan, not an error'), /₹1,999 plan|Part of/.test(lock) && !/didn't load/.test(lock));
  await go(p, '/app/cases');
  await cards.first().click();
  await p.getByTestId('case-answer').waitFor();
  check(V('Cases: the model answer is hidden before answering'), (await p.getByTestId('model-answer').count()) === 0);
  await p.getByTestId('case-answer').fill('Too short.');
  await p.getByTestId('case-submit').click();
  await p.waitForTimeout(500);
  check(V('Cases: a too-short answer gets a message'), /40|at least|more/i.test(await alertText(p)), (await alertText(p)).slice(0, 80));
  await p.getByTestId('case-answer').fill('The real problem is margin leakage: profit fell from 4% to 1.5% as stores opened. Objective: 3% in 90 days. Framework: margin leak check. Do first: fresh ordering. Owner: ops head, wastage % weekly.');
  await p.getByTestId('case-submit').click();
  await p.getByTestId('model-answer').waitFor({ timeout: 30000 });
  const sc = await p.locator('body').innerText();
  check(V('Cases: scores out of 10 and the model answer shown'), /\/\s?10|out of 10/.test(sc));
  await p.reload({ waitUntil: 'networkidle' });
  check(V('Cases: the score and model answer stay after reload'), (await p.getByTestId('model-answer').count()) === 1);
  check(V('Cases: a free account is not offered another try'), (await p.getByTestId('case-again').count()) === 0);

  // ---- 4. Meeting Brief
  await go(p, '/app/brief');
  await p.getByTestId('brief-run').click();
  await p.waitForTimeout(400);
  check(V('Brief: no company → asked for one'), /company/i.test(await alertText(p)), (await alertText(p)).slice(0, 60));
  await p.getByTestId('brief-company').fill('Tata Motors');
  await p.getByTestId('brief-website').fill('not a website');
  await p.getByTestId('brief-run').click();
  await p.waitForTimeout(800);
  check(V('Brief: a website that is not an address → said so, no go used'), /doesn't look like a website/.test(await alertText(p)) && (await p.getByTestId('brief-run').isEnabled()));
  await p.getByTestId('brief-website').fill('tatamotors.com');
  await p.getByTestId('brief-run').click();
  await p.getByText('Likely problems').waitFor({ timeout: 30000 });
  const bt = await p.locator('body').innerText();
  check(V('Brief: about, news, problems, questions and opening'), /Recent news/.test(bt) && /Likely problems/.test(bt) && /\?/.test(bt));
  const site = await p.getByTestId('brief-site').innerText();
  check(V('Brief: with a website, "From their website" says what they do, what they sell, who they sell to and their niche'),
    /From their website/.test(site) && /tatamotors\.com/.test(site) && /Their niche/.test(site) && /What they sell/.test(site) && /Who they sell to/.test(site)
      && (await p.getByTestId('brief-site-summary').innerText()).length > 100);
  await go(p, '/app/brief');
  const listed = await p.locator('[data-testid^="brief-"]').filter({ hasText: 'Tata Motors' }).count();
  check(V('Brief: listed under past briefs'), listed >= 1);

  // ---- 5. LinkedIn (quick path; the screenshot review has its own 35 checks)
  await go(p, '/app/linkedin');
  check(V('LinkedIn: page opens on the review form'), (await p.getByTestId('li-review-form').count()) === 1);
  await p.getByTestId('li-quick').locator('summary').click();
  await p.getByTestId('li-headline').fill('General Manager - Operations at ABC Ltd');
  await p.getByTestId('li-score').click();
  await p.getByTestId('linkedin-result').waitFor({ timeout: 20000 });
  check(V('LinkedIn: quick score works'), true);

  // ---- 6. My Consulting File, full
  await go(p, '/app/file');
  const f = await p.locator('body').innerText();
  const parts = { readiness: /26/.test(f), niche: /niche/i.test(f), goal: /300,000|3,00,000/.test(f), case: /\/\s?10|out of 10/.test(f),
                  brief: /Tata Motors/.test(f), linkedin: /LinkedIn/.test(f) };
  check(V('File: every tool appears'), Object.values(parts).every(Boolean), JSON.stringify(parts));
  check(V('File: print / save as PDF offered'), (await p.getByTestId('file-print').count()) === 1);
  await p.screenshot({ path: `${OUT}/file-${view}.png`, fullPage: true });
  check(V('No sideways scroll on the File page'), (await overflow(p)) === 0);
  check(V('No browser errors through the whole run'), errs.length === 0, errs.join(' | ').slice(0, 200));
  await ctx.close();
}

(async () => {
  const br = await chromium.launch();
  await run(br, 'phone', { width: 390, height: 844 });
  await run(br, 'desktop', { width: 1280, height: 900 });
  await br.close();
  console.log(`\n${rows.filter(Boolean).length} of ${rows.length} passed`);
})().catch((e) => { console.error('SCRIPT ERROR', e.message.split('\n')[0]); process.exit(1); });
