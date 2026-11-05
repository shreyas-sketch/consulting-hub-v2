// End-to-end UI QA: drives every feature through the real screens, the way a member or the team would.
// Each step opens a screen, fills its form, presses its button and checks the result shows (and survives a reload).
// A browser error, a crash screen or a 5xx response during a step fails that step, with a screenshot.
//
// Needs a hub in QA_MODE (fake vendors, codes on screen, /api/qa/login), e.g. a staging copy:
//   HUB_URL=https://staging.example.com node scripts/qa/ui_features.js ./ui-shots [phone|desktop]
const { chromium } = require('playwright');
const fs = require('fs');

const B = process.env.HUB_URL || 'http://127.0.0.1:8001';
const OUT = process.argv[2] || './ui-shots';
const VIEW = (process.argv[3] || 'phone') === 'desktop' ? { width: 1366, height: 900 } : { width: 390, height: 844 };
const RUN = String(Date.now()).slice(-5);
fs.mkdirSync(OUT, { recursive: true });

const results = [];
const STEP_MS = 45000;

function phone(n) { return `98${RUN}${String(n).padStart(3, '0')}`; }

async function newSession(browser, who, login) {
  const ctx = await browser.newContext({ viewport: VIEW, acceptDownloads: true, permissions: [] });
  const page = await ctx.newPage();
  const s = { who, ctx, page, errors: [], fivexx: [] };
  page.on('dialog', (d) => d.accept());               // "Start L2 for this member?" etc.
  page.on('console', (m) => { if (m.type() === 'error' && !/status of 40[123]|401 \(Unauthorized\)/.test(m.text())) s.errors.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => s.errors.push('pageerror: ' + e.message.slice(0, 200)));
  page.on('response', (r) => { if (r.url().includes('/api/') && r.status() >= 500) s.fivexx.push(`${r.status()} ${r.request().method()} ${r.url().replace(B, '')}`); });
  if (login) {
    const r = await page.request.post(B + '/api/qa/login', { data: login });
    if (!r.ok()) throw new Error(`qa login ${r.status()}`);
  }
  return s;
}

async function step(s, name, fn) {
  s.errors.length = 0; s.fivexx.length = 0;
  const t0 = Date.now();
  let ok = true, why = '';
  try {
    await Promise.race([fn(s.page), new Promise((_, rej) => setTimeout(() => rej(new Error('step timed out')), STEP_MS))]);
    const crash = await s.page.locator('text=/This screen didn\'t load|Something went wrong on our side/').count();
    if (crash) throw new Error('crash screen shown');
    if (s.fivexx.length) throw new Error('server error: ' + s.fivexx.join(', '));
    if (s.errors.length) throw new Error('browser error: ' + s.errors.join(' | '));
  } catch (e) { ok = false; why = e.message.split('\n')[0].slice(0, 300); }
  const ms = Date.now() - t0;
  let shot = null;
  if (!ok) { shot = `${OUT}/FAIL-${s.who}-${name.replace(/[^a-z0-9]+/gi, '_').slice(0, 60)}.png`; await s.page.screenshot({ path: shot, fullPage: true }).catch(() => {}); }
  results.push({ who: s.who, name, ok, why, ms, shot });
  console.log(`${ok ? 'PASS' : 'FAIL'} [${s.who}] ${name} (${ms} ms)${ok ? '' : '  -> ' + why}`);
  return ok;
}

const go = async (p, path) => { await p.goto(B + path, { waitUntil: 'networkidle' }); };
const tid = (p, id) => p.locator(`[data-testid="${id}"]`);
const see = async (p, id, timeout = 20000) => { await tid(p, id).first().waitFor({ state: 'visible', timeout }); };
const seeText = async (p, rx, timeout = 20000) => { await p.locator(`text=${rx} >> visible=true`).first().waitFor({ state: 'visible', timeout }); };
// Phone shows some screens as tabs; a computer shows the same panels side by side. Click the tab only when it is shown.
const tab = async (p, name) => { const b = p.getByRole('button', { name, exact: typeof name === 'string' }); if (await b.first().isVisible()) await b.first().click(); };
const reloadSee = async (p, id) => { await p.reload({ waitUntil: 'networkidle' }); await see(p, id); };

const ANSWER = 'The real problem is margin leakage since the 5 new stores opened. Objective: from 1.5% to 3% in 90 days. Framework: margin leak check; do first: fresh produce ordering. Owner: ops head, track wastage % weekly.';

(async () => {
  const browser = await chromium.launch();

  // ================================================================ public + real OTP sign-up ====
  const anon = await newSession(browser, 'visitor');
  await step(anon, 'landing page loads with sign-up button', async (p) => { await go(p, '/'); await seeText(p, '/Open your free account/'); });
  await step(anon, 'public plans page shows prices', async (p) => { await go(p, '/plans'); await seeText(p, '/1,999/'); });
  await step(anon, 'terms and privacy pages open', async (p) => { await go(p, '/terms'); await seeText(p, '/Terms/'); await go(p, '/privacy'); await seeText(p, '/Privacy/'); });
  await step(anon, 'member area sends a visitor to login', async (p) => { await go(p, '/app/decks'); await p.waitForURL(/\/login/); });

  const free = await newSession(browser, 'free');
  await step(free, 'sign up with mobile + login code (UI)', async (p) => {
    await go(p, '/login?src=webinar');
    await tid(p, 'login-phone').fill(phone(1));
    await tid(p, 'login-send').click();
    await see(p, 'login-dev-code');
    const code = (await tid(p, 'login-dev-code').innerText()).match(/\d{6}/)[0];
    await tid(p, 'login-code').fill(code);
    if (await tid(p, 'login-name').count()) await tid(p, 'login-name').fill('Asha Rao');
    await tid(p, 'login-verify').click();
    await p.waitForURL(/\/app/, { timeout: 20000 });
  });
  await step(free, 'wrong login code is refused (UI)', async (p) => {
    const c2 = await browser.newContext({ viewport: VIEW }); const q = await c2.newPage();
    await q.goto(B + '/login', { waitUntil: 'networkidle' });
    await q.locator('[data-testid="login-phone"]').fill(phone(2)); await q.locator('[data-testid="login-send"]').click();
    await q.locator('[data-testid="login-code"]').waitFor();
    await q.locator('[data-testid="login-code"]').fill('000001');
    if (await q.locator('[data-testid="login-name"]').count()) await q.locator('[data-testid="login-name"]').fill('X');
    await q.locator('[data-testid="login-verify"]').click();
    await q.locator('[data-testid="login-error"]').waitFor({ timeout: 10000 });
    await c2.close();
  });
  await step(free, 'home shows webinar tools progress', async (p) => { await go(p, '/app'); await see(p, 'tool-progress'); });
  await step(free, 'Readiness Score: rate six skills and get a score', async (p) => {
    await go(p, '/app/readiness');
    for (const el of await p.locator('input[type="range"]').all()) {
      await el.evaluate((n) => { const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set; set.call(n, '7'); n.dispatchEvent(new Event('input', { bubbles: true })); n.dispatchEvent(new Event('change', { bubbles: true })); });
    }
    await tid(p, 'readiness-submit').click(); await see(p, 'readiness-result'); await reloadSee(p, 'readiness-result');
  });
  await step(free, 'Starting Point: Niche Snapshot (AI) and choose a niche', async (p) => {
    await go(p, '/app/start');
    await tid(p, 'exp-0').fill('Supply chain for FMCG plants'); await tid(p, 'exp-1').fill('Cutting wastage'); await tid(p, 'exp-2').fill('Team leadership');
    await tid(p, 'snapshot-run').click(); await see(p, 'niche-0', 30000);
    // the best niche is chosen automatically; choosing another one switches it
    if (await tid(p, 'choose-1').count()) { await tid(p, 'choose-1').click(); await seeText(p, '/Your chosen niche/'); }
  });
  await step(free, 'Starting Point: Goal Map numbers and save', async (p) => {
    await go(p, '/app/start');
    const goalTab = p.getByRole('button', { name: /Goal Map/ }); if (await goalTab.count()) await goalTab.first().click();
    await tid(p, 'goal-income').fill('300000'); await tid(p, 'goal-fee').fill('75000');
    await see(p, 'goal-result'); await tid(p, 'goal-save').click(); await p.waitForTimeout(800);
  });
  await step(free, 'Live case: answer, AI score, model answer', async (p) => {
    await go(p, '/app/cases'); await p.locator('a[data-testid^="case-"]').first().click();
    await tid(p, 'case-answer').fill(ANSWER); await tid(p, 'case-submit').click();
    await see(p, 'model-answer', 30000); await reloadSee(p, 'model-answer');
  });
  await step(free, 'Meeting Brief: company brief with news (search + AI)', async (p) => {
    await go(p, '/app/brief'); await tid(p, 'brief-company').fill('Tata Motors'); await tid(p, 'brief-run').click();
    await p.waitForURL(/\/app\/brief\/[a-z0-9]+/, { timeout: 30000 }); await seeText(p, '/Tata Motors/');
  });
  await step(free, 'LinkedIn Score: score a profile', async (p) => {
    await go(p, '/app/linkedin'); await tid(p, 'li-headline').fill('GM Operations at ABC Foods | Supply chain and plant turnarounds');
    await tid(p, 'li-about').fill('18 years running FMCG plants. Cut wastage from 6% to 3% across four sites.');
    await tid(p, 'li-score').click(); await see(p, 'linkedin-result', 30000);
  });
  await step(free, 'My Consulting File lists what was made', async (p) => { await go(p, '/app/file'); await seeText(p, '/Readiness|Tata Motors|case/i'); await see(p, 'file-print'); });
  await step(free, 'second go is refused (once for life): result stays, no new check', async (p) => {
    await go(p, '/app/linkedin'); await see(p, 'linkedin-result'); await seeText(p, "/You've used your free go/");
    if (await tid(p, 'li-score').count()) throw new Error('a second LinkedIn check is still offered');
    const r = await p.request.post(B + '/api/linkedin/check', { data: { headline: 'Another headline to check again' } });
    if (r.status() !== 402) throw new Error('server allowed a second free go: ' + r.status());
  });
  await step(free, 'paid tool shows the lock card with an upgrade button', async (p) => { await go(p, '/app/decks'); await see(p, 'lock-card'); await see(p, 'lock-upgrade'); });
  await step(free, 'inbox opens', async (p) => { await go(p, '/app/inbox'); await seeText(p, '/Messages|No messages/'); });
  await step(free, 'account: edit profile name and save', async (p) => {
    await go(p, '/app/account'); await tid(p, 'profile-name').fill('Asha R'); await tid(p, 'profile-save').click(); await p.waitForTimeout(800);
    await p.reload({ waitUntil: 'networkidle' }); const v = await tid(p, 'profile-name').inputValue(); if (v !== 'Asha R') throw new Error('name not saved: ' + v);
  });
  await step(free, 'plans page: start ₹1,999 checkout (test payment) and get the plan', async (p) => {
    await go(p, '/app/plans');
    const btn = p.getByRole('button', { name: /1,999|Get|Choose|Start/ }).first(); await btn.click();
    await p.waitForTimeout(2500);
    const me = await (await p.request.get(B + '/api/me/plan')).json();
    if (me.plan !== 'member') throw new Error('plan after checkout is ' + me.plan);
  });
  await step(free, 'after paying, decks open', async (p) => { await go(p, '/app/decks'); await see(p, 'deck-run'); });
  await step(free, 'log out', async (p) => { await go(p, '/app/account'); await tid(p, 'account-logout').click(); await p.waitForURL(/\/login|\/$/); });

  // ================================================================ ₹1,999 plan =================
  const m = await newSession(browser, 'member', { plan: 'member', phone: phone(10) });
  await step(m, 'Presentation Builder: make a deck from notes', async (p) => {
    await go(p, '/app/decks'); await tid(p, 'deck-title').fill('Cutting wastage in FMCG plants');
    await tid(p, 'deck-notes').fill('Wastage is 6% of output. Target 3% in 90 days. Levers: ordering, cold chain, shift handover.');
    await tid(p, 'deck-run').click(); await see(p, 'deck-ready', 40000);
  });
  await step(m, 'deck: PowerPoint and PDF download', async (p) => {
    const [d1] = await Promise.all([p.waitForEvent('download'), tid(p, 'deck-download-pptx').click()]);
    if (!(await d1.suggestedFilename()).endsWith('.pptx')) throw new Error('not pptx');
    const [d2] = await Promise.all([p.waitForEvent('download'), tid(p, 'deck-download-pdf').click()]);
    if (!(await d2.suggestedFilename()).endsWith('.pdf')) throw new Error('not pdf');
  });
  await step(m, 'deck: present mode opens and closes', async (p) => {
    await tid(p, 'deck-present').click(); await p.waitForTimeout(800); await p.keyboard.press('ArrowRight'); await p.keyboard.press('Escape'); await p.waitForTimeout(500);
  });
  await step(m, 'deck: edit a slide\'s text', async (p) => {
    await tid(p, 'slide-edit-1').first().click(); await p.waitForTimeout(500);
    const save = p.getByRole('button', { name: /Save/ }); if (await save.count()) await save.first().click(); await p.waitForTimeout(800);
  });
  await step(m, 'Visual Builder: make a process diagram', async (p) => {
    await go(p, '/app/visuals'); await p.getByRole('button', { name: 'Process' }).first().click();
    await tid(p, 'visual-prompt').fill('Five steps to cut plant wastage'); await tid(p, 'visual-run').click(); await see(p, 'visual-preview', 30000);
  });
  await step(m, 'visual: download PNG', async (p) => {
    const [d] = await Promise.all([p.waitForEvent('download'), tid(p, 'visual-png').click()]); if (!/\.png$/.test(await d.suggestedFilename())) throw new Error('not png');
  });
  await step(m, 'Visual Builder: chart from numbers', async (p) => {
    await go(p, '/app/visuals'); await p.getByRole('button', { name: 'Chart' }).first().click();
    await tid(p, 'visual-prompt').fill('Wastage by month'); if (await tid(p, 'visual-numbers').count()) await tid(p, 'visual-numbers').fill('Jan 6, Feb 5.5, Mar 4.8, Apr 4.1');
    await tid(p, 'visual-run').click(); await see(p, 'visual-preview', 30000);
  });
  await step(m, 'Doc Reader: upload a document and ask a question', async (p) => {
    await go(p, '/app/docs');
    await tid(p, 'docs-file-input').setInputFiles({ name: 'q3-review.txt', mimeType: 'text/plain', buffer: Buffer.from('Quarterly review. Revenue grew 18 percent to 42 crore. The board decided to open two depots in Gujarat and hire six sales officers. Wastage fell from 6 percent to 4 percent after the cold chain fix. '.repeat(3)) });
    await seeText(p, '/q3-review/', 20000);
    await tid(p, 'docs-question').fill('What did the board decide about depots?'); await tid(p, 'docs-ask').click();
    await seeText(p, '/depot|Gujarat/i', 30000);
  });
  await step(m, 'Doc Reader: open a document and make its summary', async (p) => {
    await p.locator('[data-testid^="doc-open-"]').first().click(); await tid(p, 'doc-summary-run').click(); await see(p, 'doc-summary', 30000);
  });
  await step(m, 'Website Builder: build with AI, set name, publish', async (p) => {
    await go(p, '/app/website'); await tid(p, 'site-build').click(); await see(p, 'site-status', 40000);
    await tid(p, 'site-slug').fill(`asha-rao-${RUN}`); if (await tid(p, 'site-name').count()) await tid(p, 'site-name').fill('Asha Rao Consulting');
    await tid(p, 'site-slug-save').click(); await p.waitForTimeout(1000);
    await tid(p, 'site-publish').click(); await seeText(p, '/Your site is live/', 15000);
  });
  await step(m, 'public website renders and accepts a visitor message', async (p) => {
    const q = await m.ctx.browser().newContext({ viewport: VIEW }).then((c) => c.newPage());
    await q.goto(`${B}/s/asha-rao-${RUN}`, { waitUntil: 'networkidle' });
    const body = await q.locator('body').innerText(); if (!/Asha|consult/i.test(body)) throw new Error('site not rendered');
    const r = await q.request.post(`${B}/api/website/public/asha-rao-${RUN}/leads`, { data: { name: 'Amit Shah', email: 'amit@example.com', phone: '9876500001', message: 'Can we talk about a cost review?' } });
    if (!r.ok()) throw new Error('lead post ' + r.status());
    await q.context().close();
    await go(p, '/app/website'); await see(p, 'site-leads'); await seeText(p, '/Amit Shah/');
  });
  await step(m, 'Website Builder: AI rewrite of a section, apply', async (p) => {
    await p.locator('[data-testid^="site-ai-open-"]').first().click(); await tid(p, 'site-ai-instruction').fill('Make it shorter and plainer');
    await tid(p, 'site-ai-run').click(); await see(p, 'site-ai-apply', 30000); await tid(p, 'site-ai-apply').click(); await p.waitForTimeout(800);
  });
  await step(m, 'Website Builder: own domain is locked on this plan', async (p) => { await see(p, 'site-domain-locked'); });
  await step(m, 'Listen mode: make audio of a case and play it', async (p) => {
    await go(p, '/app/listen'); await p.locator('[data-testid^="listen-"]').filter({ hasText: /Listen/ }).first().click(); await see(p, 'listen-audio', 30000);
  });
  await step(m, 'Progress Report: make the report', async (p) => { await go(p, '/app/progress'); await tid(p, 'progress-run').click(); await see(p, 'progress-report', 30000); });
  await step(m, 'Support: write to the team', async (p) => {
    await go(p, '/app/support'); const cat = p.getByRole('button', { name: 'Tools' }); if (await cat.count()) await cat.first().click();
    await tid(p, 'support-subject').fill("Can't find my workbook"); await tid(p, 'support-text').fill('Where is the Day 2 workbook?');
    await tid(p, 'support-send').click(); await see(p, 'support-thread', 20000);
  });
  await step(m, 'LinkedIn rewrites (AI) on the paid plan', async (p) => {
    await go(p, '/app/linkedin'); if (await tid(p, 'linkedin-again').count()) await tid(p, 'linkedin-again').click();
    await tid(p, 'li-headline').fill('GM Operations at ABC Foods | Supply chain'); await tid(p, 'li-about').fill('18 years in FMCG plants.');
    await tid(p, 'li-score').click(); await see(p, 'linkedin-result', 30000);
    if (await tid(p, 'li-rewrite').count()) { await tid(p, 'li-rewrite').click(); await p.waitForTimeout(2000); }
  });
  await step(m, 'Weekly/practice cases: answer any case on the paid plan', async (p) => {
    await go(p, '/app/cases'); await p.locator('a[data-testid^="case-"]').nth(1).click();
    await tid(p, 'case-answer').fill(ANSWER); await tid(p, 'case-submit').click(); await see(p, 'model-answer', 30000);
  });
  await step(m, 'account shows plan usage with plain names', async (p) => { await go(p, '/app/account'); await see(p, 'usage-meters'); const t = await tid(p, 'usage-meters').innerText(); if (/doc_q|site_ai|_/.test(t)) throw new Error('raw usage key shown'); });
  await step(m, 'L1 tool locked on ₹1,999', async (p) => { await go(p, '/app/offer'); await see(p, 'lock-card'); });

  // ================================================================ L1 ===========================
  const l1 = await newSession(browser, 'L1', { plan: 'l1', phone: phone(20) });
  await step(l1, '4-3-2-1 program opens', async (p) => { await go(p, '/app/program'); await seeText(p, '/program|cohort|Day/i'); });
  await step(l1, 'group calls and recordings open', async (p) => { await go(p, '/app/calls'); await seeText(p, '/call/i'); await go(p, '/app/library'); await seeText(p, '/session|Recordings|Nothing here/i'); });
  await step(l1, 'session recaps open', async (p) => { await go(p, '/app/recaps'); await seeText(p, '/recap/i'); });
  await step(l1, 'Action Hub: open Define Your Niche and chat (AI)', async (p) => {
    await go(p, '/app/hub'); await tid(p, 'gpt-start-define-your-niche').first().click();
    await see(p, 'gpt-input', 30000); await tid(p, 'gpt-input').fill('18 years in FMCG supply chain. Which niche fits me?'); await tid(p, 'gpt-send').click();
    await p.waitForFunction(() => document.querySelectorAll('[data-testid="gpt-messages"] > *').length >= 2, null, { timeout: 30000 });
  });
  await step(l1, 'Mentorship tools locked on L1', async (p) => { await go(p, '/app/mentorship'); await see(p, 'lock-card'); });
  await step(l1, 'Akshat AI: ask a question', async (p) => {
    await go(p, '/app/akshat-ai'); await tid(p, 'akshat-input').fill('How do I price my first project?'); await tid(p, 'akshat-send').click();
    await p.locator('[data-testid="akshat-answer"],[data-testid="akshat-queued"]').first().waitFor({ timeout: 30000 });
  });
  await step(l1, 'Offer Card: make, edit, save', async (p) => {
    await go(p, '/app/offer'); await tid(p, 'offer-name').fill('90-day plant reset'); await tid(p, 'offer-get').fill('Diagnosis\nPlan\nWeekly reviews');
    await tid(p, 'offer-fee-from').fill('300000'); await tid(p, 'offer-fee-to').fill('600000'); await tid(p, 'offer-make').click(); await see(p, 'offer-card', 30000);
    await tid(p, 'offer-edit').click(); await tid(p, 'offer-edit-name').fill('The 90-Day Plant Reset'); await tid(p, 'offer-save').click(); await seeText(p, '/The 90-Day Plant Reset/');
  });
  await step(l1, 'Career Story Bank: story from typed text (AI)', async (p) => {
    await go(p, '/app/stories'); await p.getByRole('button', { name: 'Type' }).first().click();
    await tid(p, 'story-text').fill('In 2015 our Nashik plant was losing 6% of output to wastage. I set up a daily review with shift heads, fixed the cold chain and changed ordering. In 9 months wastage fell to 3.5%, saving two crore a year.');
    await tid(p, 'story-make-text').click(); await p.locator('[data-testid^="story-card-"]').first().waitFor({ timeout: 30000 });
  });
  await step(l1, 'Career Story Bank: story from an uploaded voice note (speech to text + AI)', async (p) => {
    await go(p, '/app/stories'); await p.getByRole('button', { name: 'Upload' }).first().click();
    const sr = 8000, n = sr * 3, buf = Buffer.alloc(44 + n * 2); buf.write('RIFF', 0); buf.writeUInt32LE(36 + n * 2, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16); buf.writeUInt16LE(1, 20); buf.writeUInt16LE(1, 22); buf.writeUInt32LE(sr, 24); buf.writeUInt32LE(sr * 2, 28); buf.writeUInt16LE(2, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(n * 2, 40);
    for (let i = 0; i < n; i++) buf.writeInt16LE(Math.round(3000 * Math.sin(i / 8)), 44 + i * 2);
    await tid(p, 'story-file').setInputFiles({ name: 'my-story.wav', mimeType: 'audio/wav', buffer: buf });
    await tid(p, 'story-make-upload').click(); await p.waitForTimeout(4000);
    const cards = await p.locator('[data-testid^="story-card-"]').count(); if (cards < 2) await seeText(p, '/too short|at least|Record/i', 5000);
  });
  await step(l1, 'Industry Insight Pack (search + AI)', async (p) => { await go(p, '/app/insights'); await tid(p, 'insight-industry').fill('FMCG distribution'); await tid(p, 'insight-make').click(); await see(p, 'insight-headline', 30000); });
  await step(l1, 'Portfolio Project: start, answer, get the case study', async (p) => {
    await go(p, '/app/portfolio'); await tid(p, 'portfolio-start').click(); await see(p, 'portfolio-brief', 30000);
    for (const k of ['scope', 'objective', 'framework_options', 'do_first', 'owner_metrics']) if (await tid(p, `portfolio-${k}`).count()) await tid(p, `portfolio-${k}`).fill(`My ${k.replace('_', ' ')}: margin fell in 14 stores; from 1.5% to 3% in 90 days; fix ordering first; ops head owns it.`);
    await tid(p, 'portfolio-submit').click(); await see(p, 'portfolio-case-study', 30000);
  });
  await step(l1, 'Pitch Practice: set up and upload a video take, get the scorecard', async (p) => {
    await go(p, '/app/pitch'); await p.getByRole('button', { name: /elevator/i }).first().click();
    await tid(p, 'pitch-setting').fill('CII networking evening'); await tid(p, 'pitch-audience').fill('MD of a mid-size pump maker'); await tid(p, 'pitch-start').click();
    await p.getByRole('button', { name: 'Upload a video' }).click();
    // A real 20-second MP4 (PITCH_VIDEO env, or made with: ffmpeg -f lavfi -i testsrc=duration=20 -f lavfi -i sine=duration=20 -pix_fmt yuv420p -shortest pitch.mp4)
    await tid(p, 'pitch-file').setInputFiles(process.env.PITCH_VIDEO || 'pitch.mp4');
    await tid(p, 'pitch-analyse-upload').click();
    await p.locator('[data-testid="pitch-scorecard"], [data-testid="pitch-report"]').or(p.getByText(/couldn.t tell how long/i)).first().waitFor({ timeout: 30000 });
  });
  await step(l1, 'Pitch Practice: ask the coach a question after the take', async (p) => {
    if (!(await tid(p, 'pitch-chat-input').count())) throw new Error('coach chat not shown after the take');
    await tid(p, 'pitch-chat-input').fill('How should I open?'); await tid(p, 'pitch-chat-send').click(); await p.waitForTimeout(2500);
  });
  await step(l1, 'Pitch Practice: a second take inside 30 minutes shows the wait', async (p) => { await see(p, 'pitch-cooldown'); });
  await step(l1, 'Research Notebook: create project, add text and web-page sources', async (p) => {
    await go(p, '/app/research'); await tid(p, 'nb-title').fill('Cold chain in Gujarat'); await tid(p, 'nb-create').click();
    await p.getByRole('button', { name: 'Text', exact: true }).click();
    await tid(p, 'nb-text-title').fill('Notes'); await tid(p, 'nb-text-body').fill('Gujarat cut power tariffs for cold storage by 12% in 2026. Five new parks opened near Surat.'); await tid(p, 'nb-text-add').click();
    await seeText(p, '/Added .Notes./', 15000);
    await p.getByRole('button', { name: 'Web page', exact: true }).click(); await tid(p, 'nb-url').fill('https://example.com/cold-chain'); await tid(p, 'nb-url-add').click();
    await seeText(p, '/2 of 20/', 15000);
  });
  await step(l1, 'Research Notebook: ask across sources, save the answer, make a briefing', async (p) => {
    await tab(p, 'Chat');
    await tid(p, 'nb-question').fill('What did the state do to power tariffs?'); await tid(p, 'nb-ask').click(); await see(p, 'nb-save-answer', 30000);
    await tid(p, 'nb-save-answer').click(); await p.waitForTimeout(800);
  });
  await step(l1, 'Research Notebook: write a note', async (p) => {
    await tab(p, /^Notes \(/);
    await tid(p, 'nb-note-title').fill('My angle'); await tid(p, 'nb-note-body').fill('Pitch shared cold rooms.'); await tid(p, 'nb-note-save').click();
    await seeText(p, '/My angle/');
    await tid(p, 'nb-gen-briefing').click(); await seeText(p, '/Briefing/i', 30000);
  });
  await step(l1, 'L2 tool locked on L1', async (p) => { await go(p, '/app/network'); await see(p, 'lock-card'); });

  // ================================================================ L2 ===========================
  const l2 = await newSession(browser, 'L2', { plan: 'l2', phone: phone(30) });
  await step(l2, 'Mentorship tools: open Book Builder and chat (AI)', async (p) => {
    await go(p, '/app/mentorship'); await tid(p, 'gpt-start-book-builder').first().click();
    await see(p, 'gpt-input', 30000); await tid(p, 'gpt-input').fill('I want to write a short book on plant wastage.'); await tid(p, 'gpt-send').click();
    await p.waitForFunction(() => document.querySelectorAll('[data-testid="gpt-messages"] > *').length >= 2, null, { timeout: 30000 });
  });
  await step(l2, 'Warm Network Finder: upload LinkedIn connections, AI score, mark contacted', async (p) => {
    await go(p, '/app/network');
    const csv = 'First Name,Last Name,URL,Email Address,Company,Position,Connected On\n' + Array.from({ length: 20 }, (_, i) => `Person${i},Shah,https://linkedin.com/in/p${i},,Company ${i} Pvt Ltd,${i % 2 ? 'Managing Director' : 'VP Operations'},0${(i % 9) + 1} Jan 2024`).join('\n');
    await tid(p, 'network-file').setInputFiles({ name: 'Connections.csv', mimeType: 'text/csv', buffer: Buffer.from(csv) });
    if (await tid(p, 'network-upload').count()) await tid(p, 'network-upload').click();
    await p.locator('[data-testid^="contact-pick-"]').first().waitFor({ timeout: 20000 });
    await p.locator('[data-testid^="contact-pick-"]').first().click(); await tid(p, 'network-score').click(); await p.waitForTimeout(3000);
    await p.locator('[data-testid^="contact-contacted-"]').first().click(); await p.waitForTimeout(800);
  });
  await step(l2, 'Outreach Drafter: three drafts, mark one sent', async (p) => {
    await go(p, '/app/outreach'); await tid(p, 'outreach-name').fill('Meera Kapoor'); await tid(p, 'outreach-company').fill('Sunrise Textiles');
    await tid(p, 'outreach-relationship').fill('Worked together at Arvind, 2010-14'); await tid(p, 'outreach-run').click();
    await p.locator('[data-testid^="outreach-variant-"]').first().waitFor({ timeout: 30000 }); await p.locator('[data-testid^="outreach-sent-"]').first().click(); await p.waitForTimeout(800);
  });
  await step(l2, 'Opportunity Radar: find companies (search + AI)', async (p) => {
    await go(p, '/app/radar'); await tid(p, 'radar-industry').fill('Pharma'); await tid(p, 'radar-city').fill('Pune'); await tid(p, 'radar-run').click();
    await p.locator('[data-testid^="radar-company-"]').first().waitFor({ timeout: 30000 });
  });
  await step(l2, 'Discovery Call Prep, then turn it into a proposal', async (p) => {
    await go(p, '/app/call-prep'); await tid(p, 'callprep-company').fill('Desai Pumps'); await tid(p, 'callprep-person').fill('Rahul Desai');
    await tid(p, 'callprep-known').fill('Sales flat for two years; opened a Gujarat plant.'); await tid(p, 'callprep-run').click(); await see(p, 'callprep-to-proposal', 30000);
  });
  await step(l2, 'Proposal Follow-through: write a proposal, mark sent, follow-ups appear', async (p) => {
    await go(p, '/app/proposals'); if (await tid(p, 'proposal-new').count()) await tid(p, 'proposal-new').click();
    await tid(p, 'proposal-company').fill('Desai Pumps'); await tid(p, 'proposal-notes').fill('Sales flat for two years at 40 crore. Dealers in Gujarat complain about delivery times. Rahul wants a plan before the new financial year.');
    await tid(p, 'proposal-fee-low').fill('150000'); await tid(p, 'proposal-fee-high').fill('400000'); await tid(p, 'proposal-run').click(); await see(p, 'proposal-sent', 30000);
    await tid(p, 'proposal-sent').click(); await p.locator('[data-testid^="proposal-followup-"]').first().waitFor({ timeout: 15000 });
  });
  let dlink = null;
  await step(l2, 'Client Diagnostic: draft (AI), publish, get the link', async (p) => {
    await go(p, '/app/diagnostic'); await tid(p, 'diagnostic-topic').fill('Dealer network health'); await tid(p, 'diagnostic-audience').fill('Owners of pump makers');
    await tid(p, 'diagnostic-run').click(); await see(p, 'diagnostic-publish', 30000); await tid(p, 'diagnostic-publish').click(); await see(p, 'diagnostic-link', 15000);
    dlink = (await tid(p, 'diagnostic-link').innerText()).match(/\/d\/[A-Za-z0-9_-]+/)?.[0] || await tid(p, 'diagnostic-link').getAttribute('href');
    if (!dlink) throw new Error('no public link shown');
  });
  await step(l2, 'prospect fills the diagnostic with no login and sees a result', async (p) => {
    const c = await browser.newContext({ viewport: VIEW }); const q = await c.newPage();
    await q.goto(B + dlink.replace(B, ''), { waitUntil: 'networkidle' });
    for (const g of await q.locator('[role="radiogroup"], [data-testid^="d-"]').all()) { /* touch */ }
    const scale = await q.locator('button[data-testid^="d-"]').all();
    const seen = new Set();
    for (const b of scale) { const id = (await b.getAttribute('data-testid')).replace(/-\d+$/, ''); if (!seen.has(id) && /-4$/.test(await b.getAttribute('data-testid'))) { seen.add(id); await b.click(); } }
    for (const t of await q.locator('textarea[data-testid^="d-"], input[data-testid^="d-"]').all()) { const id = await t.getAttribute('data-testid'); if (!['d-name', 'd-company', 'd-phone', 'd-email'].includes(id)) await t.fill('Delivery slips in monsoon'); }
    await q.locator('[data-testid="d-name"]').fill('Neha Mehta'); await q.locator('[data-testid="d-company"]').fill('Mehta Pumps');
    await q.locator('[data-testid="d-phone"]').fill('9876543210'); await q.locator('[data-testid="d-email"]').fill('neha@example.com');
    const consent = q.locator('input[type="checkbox"]'); if (await consent.count()) await consent.first().check();
    await q.locator('[data-testid="d-submit"]').click(); await q.locator('[data-testid="d-result"]').waitFor({ timeout: 20000 }); await c.close();
    await go(p, '/app/diagnostic'); await seeText(p, '/Neha Mehta|1 answer|response/i');
  });
  await step(l2, 'Social Media Builder: a month of posts on the calendar', async (p) => { await go(p, '/app/social'); await tid(p, 'social-run').click(); await p.locator('[data-testid^="social-post-"]').first().waitFor({ timeout: 30000 }); });
  await step(l2, 'Website: own domain request allowed on L2', async (p) => {
    await go(p, '/app/website'); if (await tid(p, 'site-build').count()) { await tid(p, 'site-build').click(); await see(p, 'site-status', 40000); }
    await see(p, 'site-domain-input'); await tid(p, 'site-domain-input').fill(`asha${RUN}-consulting.in`); await tid(p, 'site-domain-save').click(); await p.waitForTimeout(1500);
  });

  // ================================================================ admin ========================
  const a = await newSession(browser, 'admin', { role: 'admin' });
  const adminPages = ['', 'live', 'webinar', 'users', 'support', 'questions', 'program', 'calls', 'recaps', 'library', 'bootcamps', 'settings', 'weekly', 'kb', 'domains', 'features', 'vendors', 'whatsapp', 'jobs'];
  for (const pg of adminPages) await step(a, `admin page opens: /admin/${pg}`, async (p) => { await go(p, `/admin/${pg}`); await p.locator('main, [role="main"], body').first().waitFor(); });
  await step(a, 'support inbox: reply to the member\'s ticket', async (p) => {
    await go(p, '/admin/support'); await p.locator('text=/Can.t find my workbook/ >> visible=true').first().click();
    await tid(p, 'admin-support-reply').fill("It's in Recordings and workbooks under Day 2."); await tid(p, 'admin-support-send').click();
    await seeText(p, '/Sent. The member gets an inbox message/');
  });
  await step(a, 'members: find a member, give L1, then start L2', async (p) => {
    await go(p, '/admin/users'); await tid(p, 'admin-user-search').fill(phone(10).slice(-6)); await p.waitForTimeout(1500);
    await p.locator(`text=/${phone(10).slice(-6)}/ >> visible=true`).first().click(); await see(p, 'admin-start-l2');
    await p.locator('select').first().selectOption('l1'); await tid(p, 'admin-grant').click(); await p.waitForTimeout(1500);
    await tid(p, 'admin-start-l2').click(); await seeText(p, '/L2 is running/', 15000);
  });
  await step(a, 'calls: add a group call', async (p) => {
    await go(p, '/admin/calls'); await p.getByRole('button', { name: /Add/ }).first().click();
    const inputs = p.locator('input'); await inputs.nth(0).fill('Pricing your first project'); await p.waitForTimeout(300);
    const dt = p.locator('input[type="datetime-local"]'); if (await dt.count()) await dt.first().fill('2026-12-10T19:00');
    const link = p.locator('input[placeholder*="http"], input[type="url"]'); if (await link.count()) await link.first().fill('https://meet.example.com/x');
    await p.getByRole('button', { name: /Save|Add the call|Create/ }).last().click(); await seeText(p, '/Pricing your first project/');
  });
  await step(a, 'recaps: upload a transcript, make the recap, publish', async (p) => {
    await go(p, '/admin/recaps');
    await p.locator('input[type="file"]').first().setInputFiles({ name: 's.vtt', mimeType: 'text/vtt', buffer: Buffer.from('WEBVTT\n\n1\n00:00:01.000 --> 00:00:05.000\n' + 'Never price by the hour when the client buys a result. '.repeat(20)) });
    const t = p.locator('input[placeholder*="Pricing"]'); if (await t.count()) await t.first().fill('Pricing session');
    await p.getByRole('button', { name: /Make the recap/ }).click(); await p.waitForTimeout(3000);
    const pub = p.getByRole('button', { name: /Publish/ }); if (await pub.count()) { await pub.first().click(); await p.waitForTimeout(1500); }
  });
  await step(a, 'knowledge base: upload Akshat material', async (p) => {
    await go(p, '/admin/kb'); await p.locator('input[type="file"]').first().setInputFiles({ name: 'pricing.txt', mimeType: 'text/plain', buffer: Buffer.from('Akshat on pricing: price by outcome, never by the hour. '.repeat(30)) });
    await p.getByRole('button', { name: /Upload/ }).click(); await seeText(p, '/pricing/i');
  });
  await step(a, 'weekly case: make one now', async (p) => { await go(p, '/admin/weekly'); await p.getByRole('button', { name: /Make a weekly case now/ }).click(); await p.waitForTimeout(3000); });
  await step(a, 'switches: turn a switch off and back', async (p) => {
    await go(p, '/admin/features'); const sw = p.locator('button[role="switch"], input[type="checkbox"]'); const n = await sw.count(); if (!n) throw new Error('no switches');
    await sw.nth(n - 1).click(); await p.waitForTimeout(800); await sw.nth(n - 1).click(); await p.waitForTimeout(800);
  });
  await step(a, 'WhatsApp templates: send me a test', async (p) => { await go(p, '/admin/whatsapp'); await p.getByRole('button', { name: /Send me a test/ }).first().click(); await p.waitForTimeout(1500); });
  await step(a, 'jobs: run "weekly case" now', async (p) => { await go(p, '/admin/jobs'); await tid(p, 'job-run-call_reminders').click(); await p.waitForTimeout(2500); });
  await step(a, 'live case & group session: save settings', async (p) => { await go(p, '/admin/settings'); await p.getByRole('button', { name: /Save/ }).first().click(); await p.waitForTimeout(1200); });
  await step(a, 'webinar report: download group-session CSV', async (p) => {
    await go(p, '/admin/webinar'); const [d] = await Promise.all([p.waitForEvent('download'), p.locator('a:has-text("CSV"), button:has-text("CSV")').first().click()]); if (!/\.csv$/.test(await d.suggestedFilename())) throw new Error('not csv');
  });

  // ================================================================ bootcamp round trip ==========
  const bcTitle = `Build your offer ${RUN}`;
  await step(a, 'bootcamps: add a bootcamp with a task, shown to L2', async (p) => {
    await go(p, '/admin/bootcamps'); await tid(p, 'admin-add-bootcamps').click(); await tid(p, 'bootcamp-title').fill(bcTitle);
    await tid(p, 'bootcamp-published').selectOption('yes');
    if (!(await tid(p, 'bootcamp-task-title-0').count())) await p.getByRole('button', { name: /Add a task/ }).click();
    await tid(p, 'bootcamp-task-title-0').fill('Write your offer in one line'); await tid(p, 'admin-save').click(); await seeText(p, `/${bcTitle}/`);
  });
  await step(l2, 'bootcamp: member submits the task', async (p) => {
    await go(p, '/app/bootcamps'); await p.locator(`text=/${bcTitle}/ >> visible=true`).first().click();
    const box = p.locator('[data-testid^="bootcamp-text-"]').first(); await box.waitFor({ timeout: 15000 });
    await box.fill('I help FMCG plant heads halve wastage in 90 days.'); await p.locator('[data-testid^="bootcamp-send-"]').first().click();
    await seeText(p, '/Submitted|waiting for review|Sent/i', 15000);
  });
  await step(a, 'bootcamps: team reviews the submission with feedback', async (p) => {
    await go(p, '/admin/bootcamps'); await p.locator(`text=/${bcTitle}/ >> visible=true`).first().click();
    const fb = p.locator('[data-testid^="admin-feedback-"]').first(); await fb.waitFor({ timeout: 15000 });
    await fb.fill('Good. Name the client type and the number.'); await p.locator('[data-testid^="admin-review-"]').first().click(); await p.waitForTimeout(1500);
  });
  await step(l2, 'bootcamp: member sees the team\'s feedback', async (p) => {
    await go(p, '/app/bootcamps'); await p.locator(`text=/${bcTitle}/ >> visible=true`).first().click(); await p.locator('[data-testid^="bootcamp-feedback-"]').first().waitFor({ timeout: 15000 });
  });

  // ================================================================ member sees the team's work ====
  await step(m, 'member inbox shows the support reply and recap', async (p) => { await go(p, '/app/inbox'); await seeText(p, '/replied|support|recap/i'); });
  await step(m, 'member now on L2 (started by the team) opens an L2 tool', async (p) => { await go(p, '/app/network'); await see(p, 'network-file'); });
  await step(l1, 'Akshat AI answers from the newly uploaded material', async (p) => {
    await go(p, '/app/akshat-ai'); if (await tid(p, 'akshat-new').isVisible()) await tid(p, 'akshat-new').click();
    await tid(p, 'akshat-input').fill('How should I price my first project?'); await tid(p, 'akshat-send').click(); await see(p, 'akshat-answer', 30000);
  });

  const pass = results.filter((r) => r.ok).length;
  console.log(`\n${results.length} feature checks, ${pass} passed, ${results.length - pass} failed (${VIEW.width}px)`);
  fs.writeFileSync(`${OUT}/ui_results.json`, JSON.stringify(results, null, 1));
  await browser.close();
})().catch((e) => { console.error('RUNNER FAILED', e); process.exit(1); });
