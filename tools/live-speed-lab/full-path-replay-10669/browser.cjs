const fs=require('fs'),{chromium}=require('/Users/bain/.npm/_npx/a768ee75f5007c28/node_modules/playwright');
const port=process.argv[2],out=process.argv[3],id=process.argv[4];
const dump=(name,x)=>fs.writeFileSync(out+'/'+name,JSON.stringify(x,null,2)+'\n');
(async()=>{const browser=await chromium.launch({headless:true,executablePath:'/Users/bain/Library/Caches/ms-playwright/chromium_headless_shell-1193/chrome-mac/headless_shell',args:['--no-sandbox','--single-process','--disable-gpu','--disable-crashpad','--disable-dev-shm-usage','--no-proxy-server']});
const page=await browser.newPage({viewport:{width:390,height:844}}),receipt={errors:[],responses:[],frames:[],requests:[]};
page.on('pageerror',e=>receipt.errors.push(e.message));page.on('console',m=>{if(m.type()==='error')receipt.errors.push(m.text())});
page.on('response',async r=>{if(r.url().includes('/api/events/')&&!r.url().includes('/stream')){try{receipt.responses.push({at:Date.now(),url:r.url(),status:r.status(),data:await r.json()})}catch{}}});
page.on('request',r=>receipt.requests.push({at:Date.now(),url:r.url()}));
await page.route('**/*',async r=>{const u=new URL(r.request().url());if(u.hostname==='127.0.0.1'&&u.port===port)await r.continue();else{receipt.errors.push('external browser request refused '+u.origin);await r.abort();}});
await page.addInitScript(()=>{window.__events=[];window.__visibleTiming=null;const Native=window.EventSource;window.EventSource=class extends Native{constructor(...args){super(...args);this.addEventListener('open',()=>window.__events.push({kind:'open',url:this.url,at:Date.now()}));this.addEventListener('probability',e=>window.__events.push({kind:'probability',at:Date.now(),performance_ms:performance.now(),frame:JSON.parse(e.data)}));}};const sample=()=>{const h=document.querySelector('[data-testid="event-hero-probability"]'),c=document.querySelector('[data-testid="win-probability-card"]');if(!window.__visibleTiming&&Number(h?.getAttribute('data-probability'))===.74&&c?.querySelector('.recharts-line path')&&c.innerText.includes('74%'))window.__visibleTiming={at:Date.now(),performance_ms:performance.now(),sampling:'first requestAnimationFrame with hero .74, plotted line and chart 74% readout; sampling upper bound, not painted-pixel timestamp'};requestAnimationFrame(sample)};requestAnimationFrame(sample);});
const view=()=>page.evaluate(()=>{const h=document.querySelector('[data-testid="event-hero-probability"]');const c=document.querySelector('[data-testid="win-probability-card"]');return {at:Date.now(),hero:h?.getAttribute('data-probability'),heroText:h?.innerText,chartText:c?.innerText,chartSvgCount:c?.querySelectorAll('svg').length,lines:c?.querySelectorAll('.recharts-line path').length,events:window.__events,visibleTiming:window.__visibleTiming,body:document.body.innerText}});
try{
await page.goto('http://127.0.0.1:'+port+'/',{waitUntil:'domcontentloaded',timeout:45000});
await page.waitForFunction(()=>document.querySelector('[data-testid="event-hero-probability"]')&&document.querySelector('[data-testid="win-probability-card"] svg')&&window.__events.some(x=>x.kind==='open'&&x.url.includes('/events/')),{timeout:45000});
dump('browser-ready.json',await view());await page.screenshot({path:out+'/initial-390.png',fullPage:true});
await page.waitForFunction(()=>window.__visibleTiming!==null,{timeout:15000});
const normal=await view();if(!normal.events.some(x=>x.kind==='probability'&&x.frame.p===.74&&x.frame.event_id===Number(id)))throw Error('hero changed without matching native probability frame');
// Same backend observer clock brackets input send and this post-render return.
// Includes network/coordination overhead; upper bound, not exact pixel paint.
await page.evaluate(async view=>{const r=await fetch('/lab/visible',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(view)});if(!r.ok)throw Error('render acknowledgement failed');},normal);
await page.screenshot({path:out+'/normal-390.png',fullPage:true});dump('normal-render.json',normal);
// Poll filesystem only for control coordination; page remains native and does not refetch.
const deadline=Date.now()+15000;while(!fs.existsSync(out+'/missing-ready.json')){if(Date.now()>deadline)throw Error('missing control not ready');await new Promise(r=>setTimeout(r,50));}
await page.waitForTimeout(1500);const missing=await view();
if(Number(missing.hero)!==.74)throw Error('missing publication control unexpectedly moved hero');
if(!missing.lines||!missing.chartText.includes('74%'))throw Error('missing publication control changed or lost chart');
if(missing.events.some(x=>x.kind==='probability'&&x.frame.p===.59&&x.frame.event_id===Number(id)))throw Error('missing publication control leaked probability frame');
await page.screenshot({path:out+'/missing-publication-390.png',fullPage:true});dump('missing-render.json',missing);receipt.result='PASS';receipt.frames=missing.events;
}catch(e){receipt.result='FAIL';receipt.failure=String(e);receipt.lastView=await view().catch(()=>null);await page.screenshot({path:out+'/failure-390.png',fullPage:true}).catch(()=>{});process.exitCode=1;}
finally{dump('browser-receipt.json',receipt);await browser.close();}})().catch(e=>{console.error(e);process.exitCode=1;});
