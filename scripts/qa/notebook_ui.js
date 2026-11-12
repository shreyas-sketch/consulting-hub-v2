// Research Notebook layout in the browser (desktop and phone): two columns on a desktop with chat always visible,
// forms behind buttons, the "Make" list. Runs against scripts/qa/ai_fault_server.py.
// Usage: HUB_URL=http://127.0.0.1:8002 node notebook_ui.js <shots dir>
const { chromium } = require('playwright');
const B=process.env.HUB_URL || 'http://127.0.0.1:8002', S=process.argv[2] || '.'; let fails=0;
const check=(n,ok,d='')=>{ if(!ok) fails++; console.log(`${ok?'PASS':'FAIL'} ${n} ${d}`); };
(async()=>{const br=await chromium.launch();
for (const [name,vp] of [['desktop',{width:1440,height:1000}],['phone',{width:390,height:844}]]){
 const ctx=await br.newContext({viewport:vp}); const p=await ctx.newPage(); const tid=(x)=>p.getByTestId(x);
 await p.request.post(B+'/api/qa/login',{data:{plan:'l1',phone:`+9196${String(Date.now()).slice(-8)}`}});
 await p.goto(B+'/app/research',{waitUntil:'networkidle'}); await tid('nb-title').fill('Sahyadri Foods wastage project'); await tid('nb-create').click();
 await tid('nb-source-kind-file').waitFor();
 check(`${name}: new project opens "Add a source" straight away`, await tid('nb-source-kind-file').isVisible());
 for (const [t,b] of [['Q3 Board pack','Wastage at Nashik is 6% against a 3% target. The CFO Anita Rao signs off. Decision due by 10 November. Board cap is Rs 18 lakh. '.repeat(3)],['Discovery call notes','Vikram Shetty hinted Rs 15 to 17 lakh would be easy to approve. Cold room failures cause most wastage. '.repeat(3)]]){
   if (!(await tid('nb-text-title').isVisible())) { if (await tid('nb-source-new').isVisible()) await tid('nb-source-new').click(); await p.getByRole('button',{name:'Text',exact:true}).click(); }
   await tid('nb-text-title').fill(t); await tid('nb-text-body').fill(b); await tid('nb-text-add').click(); await p.getByText(`Added “${t}”`).waitFor({timeout:15000});
 }
 await p.reload({waitUntil:'networkidle'});
 check(`${name}: with sources, the add form is behind "Add a source"`, (await tid('nb-source-new').isVisible()) && !(await tid('nb-source-kind-file').isVisible()));
 if (name==='desktop'){
   check('desktop: two columns, chat always visible next to the sources', (await tid('nb-question').isVisible()) && (await tid('nb-source-count').isVisible()) && !(await tid('nb-gen-briefing').isVisible()));
   const [l,r]=await Promise.all([p.locator('section[aria-label="Sources"]').boundingBox(), p.locator('section[aria-label="Chat"]').boundingBox()]);
   check('desktop: chat column is wider than the left column', r.width > l.width*1.25, `${Math.round(l.width)} / ${Math.round(r.width)}`);
 } else {
   await p.getByRole('button',{name:'Chat',exact:true}).click();
 }
 await tid('nb-question').fill('Who has to sign the decision, by when, and what fee range would be easy to approve?'); await tid('nb-ask').click();
 await tid('nb-save-answer').waitFor({timeout:30000}); await tid('nb-save-answer').click(); await p.waitForTimeout(800);
 if (name==='desktop') await tid('nb-side-notes').click(); else await p.getByRole('button',{name:/^Notes \(/}).click();
 check(`${name}: notes side shows the four "Make" options with what each makes`, (await tid('nb-gen-timeline').innerText()).includes('dates'));
 check(`${name}: "Write a note" is a button until clicked`, (await tid('nb-note-new').isVisible()) && (await tid('nb-note-title').count())===0);
 await tid('nb-note-new').click(); await tid('nb-note-title').fill('My angle'); await tid('nb-note-body').fill('Pitch shared cold rooms.'); await tid('nb-note-save').click();
 await p.getByText('My angle').first().waitFor();
 check(`${name}: the note is saved and the form closes`, (await tid('nb-note-new').isVisible()));
 if (name==='desktop'){ await tid('nb-side-sources').click(); }
 else await p.getByRole('button',{name:/^Sources \(/}).click();
 check(`${name}: no sideways scroll`, (await p.evaluate(()=>document.documentElement.scrollWidth-document.documentElement.clientWidth))===0);
 await p.screenshot({path:`${S}/nb-${name}.png`, fullPage: name==='desktop'});
 if (name==='desktop'){ await tid('nb-side-notes').click(); await p.screenshot({path:`${S}/nb-${name}-notes.png`, fullPage:true}); }
 await ctx.close();}
await br.close(); console.log(fails?`${fails} FAILED`:"all passed"); process.exitCode = fails ? 1 : 0;})();
