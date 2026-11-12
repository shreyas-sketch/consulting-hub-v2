// LinkedIn Profile Review in the browser, rigorous pass. Runs against scripts/qa/ai_fault_server.py (AI answers from
// the tools' samples; failures switchable). Usage: HUB_URL=http://127.0.0.1:8002 node linkedin_ui.js <files dir> <shots dir>
const { chromium } = require('playwright');
const B = process.env.HUB_URL || 'http://127.0.0.1:8002', F = process.argv[2], OUT = process.argv[3] || '.';
const rows = [];
const check = (name, ok, detail = '') => { rows.push({ name, ok }); console.log(`${ok ? 'PASS' : 'FAIL'} ${name}${detail ? '  ' + detail : ''}`); };
const scenario = (name) => fetch(`${B}/api/_qa/scenario`, { method: 'POST', headers: { 'content-type': 'application/json' }, body: JSON.stringify({ name }) });
let n = 0;

async function member(br, plan, vp, extra = {}) {
  const ctx = await br.newContext({ viewport: vp, ...extra });
  const p = await ctx.newPage();
  p._errors = [];
  p.on('pageerror', (e) => p._errors.push(e.message));
  p.on('console', (m) => { if (m.type() === 'error' && !/status of 4\d\d/.test(m.text())) p._errors.push(m.text()); });
  n += 1;
  await p.request.post(B + '/api/qa/login', { data: { plan, phone: `+9185${String(Date.now()).slice(-7)}${n}` } });
  await p.goto(B + '/app/linkedin', { waitUntil: 'networkidle' });
  return { ctx, p };
}
const overflow = (p) => p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
const err = (p) => p.locator('[role="alert"]').first().innerText().catch(() => '');

(async () => {
  await scenario('ok');
  const br = await chromium.launch();

  // ---- A. the upload form refuses what it should, on a phone -----------------------------------------------
  {
    const { ctx, p } = await member(br, 'l1', { width: 390, height: 844 });
    await p.getByTestId('li-files').setInputFiles(`${F}/notes.txt`);
    check('A1 a text file is refused with a message', /Only images can be used/.test(await err(p)) && (await p.getByTestId('li-thumbs').count()) === 0);
    await p.getByTestId('li-files').setInputFiles(`${F}/big.png`);
    check('A2 a file over 8 MB is refused before upload', /over 8 MB/.test(await err(p)));
    await p.getByTestId('li-files').setInputFiles([0, 1, 2, 3, 4, 5, 6].map((i) => `${F}/s${i}.png`));
    const thumbs = await p.getByTestId('li-thumbs').locator('li').count();
    check('A3 seven screenshots: the first five are kept, with a message', thumbs === 5 && /Up to 5/.test(await err(p)), `thumbs=${thumbs}`);
    await p.getByRole('button', { name: 'Remove screenshot 2' }).click();
    check('A4 a screenshot can be removed', (await p.getByTestId('li-thumbs').locator('li').count()) === 4);
    await p.getByTestId('li-target').fill('');
    await p.getByTestId('li-review-go').click();
    check('A5 no client typed: asked to say who they want', /Say who you want as clients/.test(await err(p)));
    for (let i = 0; i < 4; i++) await p.getByRole('button', { name: /Remove screenshot/ }).first().click();
    await p.getByTestId('li-target').fill('Owners of mid-size auto component makers in Pune');
    await p.getByTestId('li-review-go').click();
    check('A6 no screenshots: asked to add one', /Add at least one screenshot/.test(await err(p)));
    check('A7 no sideways scroll on a phone', (await overflow(p)) === 0);
    await p.screenshot({ path: `${OUT}/A-form-phone.png` });
    check('A8 no browser errors', p._errors.length === 0, p._errors.join(' | '));
    await ctx.close();
  }

  // ---- B. keyboard: the drop area shows focus ---------------------------------------------------------------
  {
    const { ctx, p } = await member(br, 'l1', { width: 1280, height: 900 });
    await p.getByTestId('li-target').focus();
    let found = false;
    for (let i = 0; i < 12 && !found; i++) {
      await p.keyboard.press('Tab');
      found = await p.evaluate(() => document.activeElement?.getAttribute('data-testid') === 'li-files');
    }
    const ring = found ? await p.getByTestId('li-drop').evaluate((el) => {
      const s = getComputedStyle(el); return s.boxShadow !== 'none' || s.outlineStyle !== 'none';
    }) : false;
    check('B1 the screenshot picker can be reached with Tab', found);
    check('B2 the picker shows a visible focus ring', ring);
    await ctx.close();
  }

  // ---- C. a full review on a phone, then reload, again, back ----------------------------------------------
  {
    const { ctx, p } = await member(br, 'l1', { width: 390, height: 844 }, { permissions: ['clipboard-read', 'clipboard-write'] });
    await p.getByTestId('li-target').fill('Owners of mid-size auto component makers in Pune');
    await p.getByTestId('li-files').setInputFiles([`${F}/s0.png`, `${F}/s1.png`]);
    await p.getByTestId('li-review-go').click();
    await p.getByTestId('li-review').waitFor({ timeout: 30000 });
    check('C1 the review shows', true);
    const secs = await p.locator('[data-testid^="li-sec-"]').count();
    check('C2 section by section is listed', secs >= 3, `sections=${secs}`);
    // one clear list of changes: each section once, the first open with its text to paste, the rest closed
    const order = await p.locator('[data-testid^="li-sec-"]:not([data-testid$="-detail"])').evaluateAll((els) => els.map((e) => e.dataset.testid.slice(7)));
    check('C2a the changes are one list, headline first, each section once, the working photo not in it',
      order[0] === 'headline' && new Set(order).size === order.length && !order.includes('photo') && order.includes('skills'), order.join(','));
    check('C2b only the first change is open, with its headline options to paste',
      (await p.locator('[data-testid$="-detail"]').count()) === 1 && (await p.getByTestId('li-sec-headline-detail').getByRole('button', { name: 'Copy' }).count()) >= 2);
    check('C2b2 what the profile says now is its own marked block ("On your profile now"), apart from why and the new text',
      /On your profile now/i.test(await p.getByTestId('li-sec-headline-now').innerText()) && /General Manager/.test(await p.getByTestId('li-sec-headline-now').innerText()));
    check('C2c "Already working" lists the photo, apart from the changes', /Profile photo/.test(await p.getByTestId('li-working').innerText()));
    check('C2d no section is repeated in separate cards (no "Section by section", no second headline card)',
      !/Section by section|Your new headline|About section, rewritten/.test(await p.getByTestId('li-review').innerText()));
    await p.getByTestId('li-sec-about').getByRole('button', { name: /Show what to change/ }).click();
    check('C2e opening About closes the headline and shows the new About, shortened with "Read the whole"',
      (await p.getByTestId('li-sec-about-detail').count()) === 1 && (await p.getByTestId('li-sec-headline-detail').count()) === 0 && (await p.getByTestId('li-about-more').isVisible()));
    await p.getByTestId('li-done-banner').check();
    check('C2f ticking a change marks it done and counts it', /1 of \d+ done/.test(await p.getByTestId('li-changes-progress').innerText())
      && /Done/.test(await p.getByTestId('li-sec-banner').innerText()));
    await p.reload({ waitUntil: 'networkidle' });
    check('C3 the review is still there after a reload', (await p.getByTestId('li-review').count()) === 1);
    check('C3a the ticks stay after a reload, and the first change not yet done opens', (await p.getByTestId('li-done-banner').isChecked())
      && /1 of \d+ done/.test(await p.getByTestId('li-changes-progress').innerText()) && (await p.getByTestId('li-sec-headline-detail').count()) === 1);
    const head = (await (await p.request.get(B + '/api/linkedin-review')).json()).review.headlines[0].text;
    await p.locator('[data-testid="li-review"]').getByRole('button', { name: 'Copy' }).nth(0).click();
    const clip = await p.evaluate(() => navigator.clipboard.readText()).catch(() => '');
    check('C4 Copy puts the headline on the clipboard', clip.trim() === head, `clip=${clip.slice(0, 40)}`);
    await p.getByTestId('li-review-again').click();
    check('C5 Review again opens the form', (await p.getByTestId('li-review-form').count()) === 1);
    await p.getByRole('button', { name: 'Back to my review' }).click();
    check('C6 Back to my review returns to it', (await p.getByTestId('li-review').count()) === 1);
    check('C7 no sideways scroll', (await overflow(p)) === 0);
    check('C8 no browser errors', p._errors.length === 0, p._errors.join(' | '));
    await ctx.close();
  }

  // ---- D. AI fails mid-review: message, nothing lost, retry works -------------------------------------------
  {
    const { ctx, p } = await member(br, 'l1', { width: 390, height: 844 });
    await p.getByTestId('li-target').fill('Hospital owners in Indore');
    await p.getByTestId('li-files').setInputFiles([`${F}/s0.png`, `${F}/s1.png`, `${F}/s2.png`]);
    await scenario('vendor_error');
    await p.getByTestId('li-review-go').click();
    await p.getByText('The AI is busy right now').waitFor({ timeout: 30000 });
    await p.waitForTimeout(1200);
    const inView = await p.getByText('The AI is busy right now').evaluate((el) => { const r = el.getBoundingClientRect(); return r.top >= 0 && r.bottom <= innerHeight; });
    check('D1 the busy message shows on screen', inView);
    check('D2 the screenshots are still picked', (await p.getByTestId('li-thumbs').locator('li').count()) === 3);
    check('D3 the client typed is kept', (await p.getByTestId('li-target').inputValue()) === 'Hospital owners in Indore');
    check('D4 the go was not used', /0 of 6/.test(await p.locator('text=/of 6 profile reviews/').first().innerText().catch(() => '')));
    await scenario('ok');
    await p.getByTestId('li-review-go').click();
    await p.getByTestId('li-review').waitFor({ timeout: 30000 });
    check('D5 pressing again once the AI is back works', true);
    await ctx.close();
  }

  // ---- E. the 30-day plan: weeks, posted, reload ------------------------------------------------------------
  {
    const { ctx, p } = await member(br, 'l2', { width: 1280, height: 900 });
    await p.getByTestId('li-tab-plan').click();
    const needTarget = await p.getByTestId('li-plan-go').isVisible();
    await p.getByTestId('li-plan-go').click();
    const msg = await err(p);
    check('E1 no review and no niche: plan asks who the clients are', needTarget && /who you want as clients/i.test(msg), msg.slice(0, 60));
    await p.getByTestId('li-tab-review').click();
    await p.getByTestId('li-target').fill('Owners of pump makers in Coimbatore');
    await p.getByTestId('li-files').setInputFiles(`${F}/s0.png`);
    await p.getByTestId('li-review-go').click();
    await p.getByTestId('li-review').waitFor({ timeout: 30000 });
    await p.getByTestId('li-tab-plan').click();
    await p.getByTestId('li-plan-go').click();
    await p.getByTestId('li-plan').waitFor({ timeout: 30000 });
    const wk1 = await p.locator('[data-testid^="li-post-"]').count();
    await p.getByTestId('li-plan-week-3').click();
    const wk4 = await p.locator('[data-testid^="li-post-"]').count();
    check('E2 weeks split 7 / 9 posts', wk1 === 7 && wk4 === 9, `w1=${wk1} w4=${wk4}`);
    await p.getByTestId('li-posted-30').click();
    await p.getByTestId('li-plan-week-0').click();
    await p.getByTestId('li-posted-1').click();
    await p.waitForTimeout(400);
    await p.reload({ waitUntil: 'networkidle' });
    await p.getByTestId('li-tab-plan').click();
    const prog = await p.getByTestId('li-plan-progress').innerText();
    check('E3 two posts ticked survive a reload', /2 of 30/.test(prog), prog);
    await p.getByTestId('li-posted-1').click();
    await p.waitForTimeout(400);
    check('E4 a tick can be undone', /1 of 30/.test(await p.getByTestId('li-plan-progress').innerText()));
    await p.screenshot({ path: `${OUT}/E-plan-desktop.png`, fullPage: true });
    check('E5 no browser errors', p._errors.length === 0, p._errors.join(' | '));
    await ctx.close();
  }

  // ---- F. free account: one go each, then the buttons go away -----------------------------------------------
  {
    const { ctx, p } = await member(br, 'free', { width: 390, height: 844 });
    await p.getByTestId('li-target').fill('Owners of textile mills in Surat');
    await p.getByTestId('li-files').setInputFiles(`${F}/s0.png`);
    await p.getByTestId('li-review-go').click();
    await p.getByTestId('li-review').waitFor({ timeout: 30000 });
    check('F1 after the free review, "Review again" is not offered', (await p.getByTestId('li-review-again').count()) === 0);
    await p.getByTestId('li-tab-plan').click();
    await p.getByTestId('li-plan-go').click();
    await p.getByTestId('li-plan').waitFor({ timeout: 30000 });
    check('F2 after the free plan, "Make a new plan" is not offered', (await p.getByTestId('li-plan-again').count()) === 0);
    await p.goto(B + '/app', { waitUntil: 'networkidle' });
    const home = await p.locator('body').innerText();
    check('F3 Home shows LinkedIn as done with the client-fit score', /Client fit/.test(home) && !/Not checked yet/.test(home));
    await p.goto(B + '/app/file', { waitUntil: 'networkidle' });
    check('F4 My Consulting File shows the review', /LinkedIn client fit/.test(await p.locator('body').innerText()));
    await ctx.close();
  }

  // ---- G. smallest phone (320 px) and the quick check still works --------------------------------------------
  {
    const { ctx, p } = await member(br, 'member', { width: 320, height: 640 });
    check('G1 no sideways scroll at 320 px', (await overflow(p)) === 0);
    await p.getByTestId('li-quick').locator('summary').click();
    await p.getByTestId('li-headline').fill('General Manager - Operations at ABC Ltd');
    await p.getByTestId('li-score').click();
    await p.getByTestId('linkedin-result').waitFor({ timeout: 20000 });
    check('G2 the quick text check still scores', true);
    check('G3 no sideways scroll after the quick check', (await overflow(p)) === 0);
    await p.screenshot({ path: `${OUT}/G-320.png`, fullPage: true });
    await ctx.close();
  }

  await scenario('ok');
  await br.close();
  console.log(`\n${rows.filter((r) => r.ok).length} of ${rows.length} passed`);
})().catch((e) => { console.error('SCRIPT ERROR', e.message); process.exit(1); });
