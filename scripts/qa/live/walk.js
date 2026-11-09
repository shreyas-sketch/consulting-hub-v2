const { chromium } = require('playwright');
const fs = require('fs');
const U = 'https://consulting-hub-v2-production.up.railway.app', L = process.argv[2];
const APP = ['', 'readiness', 'start', 'cases', 'cases/retail-chain-margins', 'brief', 'linkedin', 'file', 'tools', 'inbox', 'account', 'plans',
  'decks', 'visuals', 'website', 'listen', 'docs', 'progress', 'support', 'program', 'calls', 'library', 'recaps', 'hub', 'akshat-ai',
  'offer', 'stories', 'insights', 'portfolio', 'pitch', 'research', 'mentorship', 'network', 'outreach', 'radar', 'call-prep',
  'proposals', 'diagnostic', 'social', 'bootcamps'];
const ADMIN = ['', 'live', 'webinar', 'users', 'support', 'questions', 'program', 'calls', 'recaps', 'library', 'bootcamps', 'settings',
  'weekly', 'kb', 'domains', 'features', 'vendors', 'whatsapp', 'jobs'];
(async () => {
  const jar = JSON.parse(fs.readFileSync(`${L}/cookies-002.json`, 'utf8'));
  const br = await chromium.launch({ proxy: { server: process.env.HTTPS_PROXY } });
  const rows = [];
  for (const [view, vp] of [['phone', { width: 390, height: 844 }], ['desktop', { width: 1280, height: 860 }]]) {
    const ctx = await br.newContext({ viewport: vp, ignoreHTTPSErrors: true });
    await ctx.addCookies(Object.entries(jar).map(([name, value]) => ({ name, value, url: U })));
    const p = await ctx.newPage();
    let cur = null;
    p.on('console', (m) => { if (cur && m.type() === 'error') cur.err.push(m.text().slice(0, 140)); });
    p.on('pageerror', (e) => { if (cur) cur.err.push('pageerror ' + e.message.slice(0, 140)); });
    p.on('response', (r) => { if (cur && r.url().includes('/api/') && r.status() >= 400) cur.api.push(`${r.status()} ${r.url().replace(U, '')}`); });
    for (const path of [...APP.map((x) => '/app/' + x), ...ADMIN.map((x) => '/admin/' + x)]) {
      cur = { view, path, err: [], api: [] };
      const t = Date.now();
      try { await p.goto(U + path, { waitUntil: 'networkidle', timeout: 45000 }); } catch (e) { cur.err.push('goto ' + e.message.slice(0, 80)); }
      cur.ms = Date.now() - t;
      Object.assign(cur, await p.evaluate(() => ({ ov: document.documentElement.scrollWidth - document.documentElement.clientWidth,
        crash: /This screen didn't load|Something went wrong/.test(document.body.innerText), at: location.pathname })));
      cur.ok = !cur.crash && cur.ov === 0 && !cur.err.length && !cur.api.length && !/\/login/.test(cur.at);
      rows.push(cur);
      if (!cur.ok) console.log(`FAIL ${view} ${path} ms=${cur.ms} at=${cur.at} ov=${cur.ov} crash=${cur.crash} err=${cur.err.join(' | ')} api=${cur.api.join(', ')}`);
      if (['/app/', '/app/linkedin', '/admin/'].includes(path)) await p.screenshot({ path: `${L}/walk-${view}${path.replace(/\//g, '_')}.png` });
    }
    await ctx.close();
  }
  await br.close();
  const ms = rows.map((r) => r.ms).sort((a, b) => a - b);
  fs.writeFileSync(`${L}/walk.json`, JSON.stringify(rows, null, 1));
  console.log(`\n${rows.filter((r) => r.ok).length} of ${rows.length} screen visits clean · median ${ms[Math.floor(ms.length / 2)]} ms · slowest ${ms[ms.length - 1]} ms (${rows.find((r) => r.ms === ms[ms.length - 1]).path})`);
})().catch((e) => { console.error('ERR', e.message); process.exit(1); });
