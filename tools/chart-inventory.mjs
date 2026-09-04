// Counts what a reader's DOM actually contains per surface: <svg> elements that
// are CHARTS (>=1 <path>/<polyline>/<rect> data mark and a viewport bigger than
// an icon), plus recharts containers, plus the vertex count of every polyline /
// path so "visible point density" is read off the render rather than the payload.
import { createRequire } from 'module';
import { existsSync, readdirSync } from 'fs';
function fp(){const n=`${process.env.HOME}/.npm/_npx`;if(existsSync(n))for(const d of readdirSync(n)){const p=`${n}/${d}/node_modules/`;if(existsSync(`${p}playwright`))return p;}return process.cwd()+'/';}
const { chromium } = createRequire(fp())('playwright');
const proxy = process.env.HTTPS_PROXY || process.env.HTTP_PROXY;
const args=['--no-sandbox','--single-process','--disable-gpu','--disable-crashpad','--disable-dev-shm-usage'];
if(proxy)args.push(`--proxy-server=${proxy}`,'--proxy-bypass-list=127.0.0.1;localhost');
const url=process.argv[2];
const browser=await chromium.launch({args});
try{
  const page=await browser.newPage({viewport:{width:1440,height:2400}});
  const { execFileSync } = await import('child_process');
  await page.route('**://api.bainluck.com/**', async (route)=>{
    const u=route.request().url();
    if(/\/stream|\/sse|event-stream/.test(u)){await route.abort();return;}
    try{const body=execFileSync('curl',['-sS','-L','--max-time','25',u],{maxBuffer:256*1024*1024,timeout:30000});
      await route.fulfill({status:200,contentType:'application/json',headers:{'access-control-allow-origin':'*'},body});}
    catch(e){await route.abort();}
  });
  await page.goto(url,{waitUntil:'domcontentloaded',timeout:60000});
  await page.waitForTimeout(11000);
  const out = await page.evaluate(()=>{
    const res=[];
    for(const svg of document.querySelectorAll('svg')){
      const r=svg.getBoundingClientRect();
      if(r.width<40||r.height<12) continue;             // icons
      const polys=[...svg.querySelectorAll('polyline')];
      const paths=[...svg.querySelectorAll('path')];
      const rects=[...svg.querySelectorAll('rect')];
      const circles=[...svg.querySelectorAll('circle')];
      const vertex=(d)=>((d||'').match(/[MLHV]/g)||[]).length;
      const marks=paths.filter(p=>vertex(p.getAttribute('d'))>=3);
      const polyPts=polys.map(p=>(p.getAttribute('points')||'').trim().split(/\s+/).filter(Boolean).length);
      if(marks.length===0&&polyPts.length===0&&rects.length<3) continue;
      // nearest labelled ancestor
      let n=svg, label='';
      for(let i=0;i<8&&n;i++){n=n.parentElement; if(!n)break;
        const t=(n.querySelector('h1,h2,h3,h4')||{}).textContent;
        if(t&&t.trim()){label=t.trim().slice(0,48);break;}}
      res.push({label, w:Math.round(r.width), h:Math.round(r.height),
        recharts: !!svg.closest('.recharts-wrapper'),
        dataPaths: marks.length, maxPathVertices: Math.max(0,...marks.map(p=>vertex(p.getAttribute('d')))),
        polylines: polyPts.length, maxPolyPoints: Math.max(0,...polyPts,0),
        rects: rects.length, circles: circles.length});
    }
    return res;
  });
  console.log(JSON.stringify({url,charts:out},null,1));
}catch(e){console.error('FAIL',e.message);}finally{await browser.close();}
