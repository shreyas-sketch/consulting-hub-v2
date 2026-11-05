const { chromium } = require('playwright');
const B = process.env.HUB_URL || 'http://127.0.0.1:8001';
const TOOLS = { member: ['decks', 'visuals', 'website', 'listen', 'docs', 'progress', 'support'],
  l1: ['program', 'calls', 'library', 'recaps', 'hub', 'akshat-ai', 'offer', 'stories', 'insights', 'portfolio', 'pitch', 'research'],
  l2: ['mentorship', 'network', 'outreach', 'radar', 'call-prep', 'proposals', 'diagnostic', 'social', 'bootcamps'] };
const RANK = { free: 0, member: 1, l1: 2, l2: 3 };
(async () => {
  const browser = await chromium.launch(); let wrong = 0, n = 0;
  for (const plan of ['free', 'member', 'l1', 'l2']) {
    const ctx = await browser.newContext({ viewport: { width: 390, height: 844 } }); const page = await ctx.newPage();
    await page.request.post(B + '/api/qa/login', { data: { plan } });
    for (const [need, list] of Object.entries(TOOLS)) for (const t of list) {
      await page.goto(`${B}/app/${t}`, { waitUntil: 'networkidle' }); await page.waitForTimeout(150);
      const locked = await page.evaluate(() => /Part of the (₹1,999 plan|L1|L2 Mentorship)/.test(document.body.innerText));
      const should = RANK[plan] < RANK[need]; n++;
      if (locked !== should) { wrong++; console.log(`WRONG ${plan} /app/${t}: locked=${locked} expected=${should}`); }
    }
    await ctx.close();
  }
  console.log(`${n} plan/screen combinations checked, ${wrong} wrong`); await browser.close();
})();
