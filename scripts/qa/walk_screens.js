const { chromium } = require('playwright');
const fs = require('fs');
const B = process.env.HUB_URL || 'http://127.0.0.1:8001', OUT = process.argv[2];
const APP = ['', 'readiness', 'start', 'cases', 'cases/retail-chain-margins', 'brief', 'linkedin', 'file', 'tools', 'inbox', 'account', 'plans',
  'decks', 'visuals', 'website', 'listen', 'docs', 'progress', 'support',
  'program', 'calls', 'library', 'recaps', 'hub', 'akshat-ai', 'offer', 'stories', 'insights', 'portfolio', 'pitch', 'research',
  'mentorship', 'network', 'outreach', 'radar', 'call-prep', 'proposals', 'diagnostic', 'social', 'bootcamps'];
const ADMIN = ['', 'live', 'webinar', 'users', 'support', 'questions', 'program', 'calls', 'recaps', 'library', 'bootcamps', 'settings',
  'weekly', 'kb', 'domains', 'features', 'vendors', 'whatsapp', 'jobs'];
const PUBLIC = ['/', '/login', '/plans', '/terms', '/privacy'];
const VIEWS = { phone: { width: 390, height: 844 }, desktop: { width: 1280, height: 860 } };

async function walk(browser, who, login, pages, view) {
  const ctx = await browser.newContext({ viewport: VIEWS[view] });
  const page = await ctx.newPage();
  const rows = [];
  let cur = null;
  page.on('console', (m) => { if (m.type() === 'error' && cur) cur.console.push(m.text().slice(0, 200)); });
  page.on('pageerror', (e) => { if (cur) cur.console.push('pageerror: ' + e.message.slice(0, 200)); });
  page.on('response', (r) => {
    const u = r.url();
    if (cur && u.includes('/api/') && r.status() >= 400) cur.api.push(`${r.status()} ${r.request().method()} ${u.replace(B, '')}`);
  });
  if (login) { const r = await page.request.post(B + '/api/qa/login', { data: login }); if (!r.ok()) throw new Error('login ' + r.status()); }
  for (const path of pages) {
    cur = { who, view, path, console: [], api: [] };
    const t = Date.now();
    try {
      await page.goto(B + path, { waitUntil: 'networkidle', timeout: 30000 });
    } catch (e) { cur.console.push('goto: ' + e.message.slice(0, 100)); }
    await page.waitForTimeout(250);
    const info = await page.evaluate(() => {
      const d = document.documentElement;
      const txt = document.body.innerText || '';
      return { overflow: d.scrollWidth - d.clientWidth, crash: /This screen didn't load|Something went wrong/.test(txt),
               lock: /is part of the|Upgrade|higher plan/i.test(txt), url: location.pathname, len: txt.length };
    });
    cur.ms = Date.now() - t;
    Object.assign(cur, info);
    const name = `${who}-${view}-${(path.replace(/\//g, '_') || 'root')}.png`;
    if (view === 'phone' || path.endsWith('/admin/')) await page.screenshot({ path: `${OUT}/${name}` });
    cur.shot = name;
    rows.push(cur);
    const bad = cur.console.length || cur.overflow > 1 || cur.crash || cur.api.some((a) => /^5/.test(a));
    console.log(`${bad ? 'ISSUE' : 'ok   '} ${who.padEnd(6)} ${view.padEnd(7)} ${path.padEnd(32)} ${String(cur.ms).padStart(5)}ms`
      + (cur.overflow > 1 ? ` overflow=${cur.overflow}` : '') + (cur.crash ? ' CRASH' : '') + (cur.lock ? ' (lock card)' : '')
      + (cur.console.length ? ' console=' + JSON.stringify(cur.console) : '') + (cur.api.length ? ' api=' + JSON.stringify(cur.api) : ''));
  }
  await ctx.close();
  return rows;
}

(async () => {
  const browser = await chromium.launch();
  let all = [];
  for (const view of ['phone', 'desktop']) {
    all = all.concat(await walk(browser, 'anon', null, PUBLIC, view));
    for (const plan of ['free', 'member', 'l1', 'l2']) all = all.concat(await walk(browser, plan, { plan }, APP.map((p) => '/app/' + p), view));
    all = all.concat(await walk(browser, 'admin', { role: 'admin' }, ADMIN.map((p) => '/admin/' + p), view));
  }
  fs.writeFileSync(`${OUT}/walk.json`, JSON.stringify(all, null, 1));
  const issues = all.filter((r) => r.console.length || r.overflow > 1 || r.crash || r.api.some((a) => /^5/.test(a)));
  console.log(`\n${all.length} screen visits, ${issues.length} with issues`);
  await browser.close();
})().catch((e) => { console.error('FAIL', e); process.exit(1); });
