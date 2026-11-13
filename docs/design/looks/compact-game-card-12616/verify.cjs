const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
(async()=>{
 const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
 const page=await browser.newPage({viewport:{width:390,height:844},deviceScaleFactor:1});
 const errors=[];page.on('pageerror',e=>errors.push(e.message));
 fs.mkdirSync(path.join(__dirname,'screenshots'),{recursive:true});
 const reports=[];
 for(const variant of ['A','B'])for(const sport of ['nba','nfl','soccer','tennis']){
  await page.goto(`file://${path.join(__dirname,'index.html')}?variant=${variant}&case=${sport}`);
  await page.evaluate(()=>document.fonts.ready);
  const audit=await page.evaluate(()=>{
   const tables=[...document.querySelectorAll('.table')];
   const issues=[];let edges=null;
   for(const table of tables){
    if(table.scrollWidth>table.clientWidth+1)issues.push('table overflow');
    const all=[...table.querySelectorAll('.cell')];
    const first=all.slice(0,5).map(x=>x.getBoundingClientRect().right);
    if(edges&&first.some((v,i)=>Math.abs(v-edges[i])>.1))issues.push('columns move by state');edges=first;
    for(const c of all){
     if(c.scrollWidth>c.clientWidth+1)issues.push(`cell overflow ${c.textContent}`);
     if(getComputedStyle(c).whiteSpace!=='nowrap')issues.push('wrap allowed');
     if(Math.abs(c.getBoundingClientRect().right-first[+c.dataset.col])>.1)issues.push('misaligned column');
     if(!c.classList.contains('head')&&!c.classList.contains('name')&&getComputedStyle(c).fontSize!=='16px')issues.push('numeric size');
    }
   }
   return {issues,tableCount:tables.length,edges,viewport:innerWidth,pageWidth:document.documentElement.scrollWidth};
  });
  assert.deepEqual(audit.issues,[]);assert.equal(audit.tableCount,4);assert.equal(audit.pageWidth,390);
  if(sport==='nba'){
   assert.equal(await page.locator('article[data-state="after"]').getByText('123',{exact:true}).count(),1);
   assert.equal(await page.locator('article[data-state="during-live"]').getByText('>99%',{exact:true}).count(),1);
   assert.equal(await page.locator('article[data-state="after"]').getByText('Now',{exact:true}).count(),0);
  }
  if(sport==='soccer'){
   const rows=page.locator('.row').filter({has:page.getByText('Draw',{exact:true})});
   assert.equal(await rows.count(),4);
   for(const row of await rows.all())for(const col of ['1','2'])assert.equal(await row.locator(`[data-col="${col}"]`).innerText(),'');
  }
  if(sport==='tennis')assert.equal(await page.locator('[data-col="2"]:not(.empty)').count(),0);
  await page.screenshot({path:path.join(__dirname,`screenshots/${variant.toLowerCase()}-${sport}-390.png`),fullPage:true});
  reports.push({variant,sport,...audit});
 }
 // Round two: each requested choice has its own capture, in both variants.
 const comparisons=[['large','nba','&text=large'],['near','nba','&compare=near'],['headers','nba','&compare=headers'],['slots','nba','&compare=slots'],['soccer','soccer','&compare=soccer']];
 for(const variant of ['A','B'])for(const [name,sport,query] of comparisons){
  await page.goto(`file://${path.join(__dirname,'index.html')}?variant=${variant}&case=${sport}${query}`);await page.evaluate(()=>document.fonts.ready);
  const audit=await page.evaluate(()=>{
   const issues=[];
   for(const e of document.querySelectorAll('.card,.table,.cell:not(.empty),.name-text')){
    if(e.scrollWidth>e.clientWidth+1)issues.push(`overflow: ${e.className} ${e.textContent}`);
    const r=e.getBoundingClientRect();if(r.right>390||r.left<0)issues.push('offscreen');
   }
   for(const e of document.querySelectorAll('article[data-state^="during"] .cell[data-col="4"]:not(.head)'))if(['100%','0%'].includes(e.textContent))issues.push('live certainty');
   return {issues,pageWidth:document.documentElement.scrollWidth};
  });assert.deepEqual(audit.issues,[]);assert.equal(audit.pageWidth,390);
  if(name==='large'){
   assert.equal(await page.locator('.cell:not(.head):not(.name)').first().evaluate(e=>getComputedStyle(e).fontSize),'24px');
   assert.equal(await page.locator('.card').first().evaluate(e=>e.scrollWidth>e.clientWidth),false);
   assert.equal(await page.getByText('123',{exact:true}).count(),1);
  }
  if(name==='near'){assert.equal(await page.getByText('>99%',{exact:true}).count(),2);assert.equal(await page.getByText('<1%',{exact:true}).count(),2);}
  if(name==='headers'){assert.equal(await page.getByText('Chance',{exact:true}).count(),1);assert.equal(await page.getByText('Pregame',{exact:true}).count(),1);}
  if(name==='slots'){
   const gap=await page.evaluate(()=>[...document.querySelectorAll('.card')].map(c=>c.getBoundingClientRect().right-c.querySelector('.head[data-col="3"]').getBoundingClientRect().right));
   assert(gap[0]>gap[1]+40);assert(gap[1]<15);
  }
  if(name==='soccer'){assert.equal(await page.getByText('1.6',{exact:true}).count(),2);assert.equal(await page.getByText('1.4',{exact:true}).count(),1);}
  await page.screenshot({path:path.join(__dirname,`screenshots/r2-${variant.toLowerCase()}-${name}-390.png`),fullPage:true});reports.push({variant,comparison:name,...audit});
 }
 // Replace the former large-text diagnostic with the corrected no-scroll form.
 fs.copyFileSync(path.join(__dirname,'screenshots/r2-a-large-390.png'),path.join(__dirname,'screenshots/large-text-390.png'));
 assert.deepEqual(errors,[]);
 fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify({passed:true,checks:['8 original views retained at 390px','10 round-two comparison views at 390px','fixed right edges in original normal-size states','no wrapped/overflowing cells','16px normal / 24px large numeric type','123 and >99% / <1%','draw has no score','no-projection slot blank','24px two-line teams keep four numeric columns onscreen without scrolling','Chance / Pregame labels','fixed / right-closed before slots','soccer decimal / whole projections'],reports},null,2)+'\n');
 console.log('PASS: 8 original views and 10 round-two captures; 24px four-column form fits without scrolling; no live 100% or 0%.');
 await browser.close();
})().catch(e=>{console.error(e);process.exit(1)});
