const { chromium } = require('playwright');
const U = 'https://consulting-hub-v2-production.up.railway.app', OUT = process.argv[2];
(async () => {
  const br = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY || process.env.https_proxy } });
  let pass = 0, total = 0;
  for (const [view, vp] of [['phone', { width: 390, height: 844 }], ['desktop', { width: 1280, height: 860 }]]) {
    const ctx = await br.newContext({ viewport: vp, ignoreHTTPSErrors: true });
    const p = await ctx.newPage();
    for (const path of ['/', '/login', '/plans', '/terms', '/privacy']) {
      const errs = [];
      p.removeAllListeners('console'); p.removeAllListeners('pageerror');
      p.on('console', (m) => { if (m.type() === 'error' && !/status of 401/.test(m.text())) errs.push(m.text().slice(0, 120)); });
      p.on('pageerror', (e) => errs.push('pageerror ' + e.message.slice(0, 120)));
      const t = Date.now();
      await p.goto(U + path, { waitUntil: 'networkidle', timeout: 45000 });
      const ms = Date.now() - t;
      const info = await p.evaluate(() => ({ ov: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        crash: /didn't load|Something went wrong/.test(document.body.innerText), len: document.body.innerText.length }));
      const ok = !info.crash && info.ov === 0 && errs.length === 0 && info.len > 50;
      total++; if (ok) pass++;
      console.log(`${ok ? 'PASS' : 'FAIL'} ${view.padEnd(7)} ${path.padEnd(9)} ${ms} ms  overflow=${info.ov} errors=${errs.length ? errs.join(' | ') : 'none'}`);
      await p.screenshot({ path: `${OUT}/pub-${view}${path.replace(/\//g, '_') || '_root'}.png` });
    }
    // login form: a wrong number shows a clear message, nothing is sent
    await p.goto(U + '/login', { waitUntil: 'networkidle' });
    const phone = p.locator('input[type="tel"], input[inputmode="numeric"], input[name="phone"]').first();
    await phone.fill('12345');
    await p.getByRole('button', { name: /send code|continue|get code/i }).first().click();
    await p.waitForTimeout(1500);
    const msg = await p.locator('[role="alert"]').first().innerText().catch(() => '');
    total++; if (/10-digit|valid|mobile/i.test(msg)) pass++;
    console.log(`${/10-digit|valid|mobile/i.test(msg) ? 'PASS' : 'FAIL'} ${view.padEnd(7)} login: a short number is refused with "${msg.slice(0, 70)}"`);
    // a member page while logged out goes to login
    await p.goto(U + '/app/linkedin', { waitUntil: 'networkidle' });
    const atLogin = /\/login/.test(p.url());
    total++; if (atLogin) pass++;
    console.log(`${atLogin ? 'PASS' : 'FAIL'} ${view.padEnd(7)} /app/linkedin logged out → ${p.url().replace(U, '')}`);
    await ctx.close();
  }
  await br.close();
  console.log(`\n${pass} of ${total} passed`);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
