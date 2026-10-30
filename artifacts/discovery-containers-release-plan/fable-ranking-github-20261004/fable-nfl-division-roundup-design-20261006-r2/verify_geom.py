import asyncio,json
from playwright.async_api import async_playwright
JS="""(card)=>{const c=card.getBoundingClientRect(); return [card,...card.querySelectorAll('*')].map(e=>{const r=e.getBoundingClientRect(), s=getComputedStyle(e); return {k:e.tagName+'.'+e.className.trim(),x:+(r.left-c.left).toFixed(2),y:+(r.top-c.top).toFixed(2),w:+r.width.toFixed(2),h:+r.height.toFixed(2),fs:s.fontSize,lh:s.lineHeight,fw:s.fontWeight,ls:s.letterSpacing,col:s.color,bg:s.backgroundColor,ff:s.fontFamily.replace(/["']/g,''),br:s.borderTopRightRadius,bc:s.borderTopColor,bw:s.borderTopWidth,tt:s.textTransform,ta:s.textAlign}})}"""
CASES=(('canonical','light',358),('canonical','dark',358),('three','light',358),('long','light',358),('extremes','dark',358),('canonical','light',340))
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); bad=0; n=0
        for cid,th,w in CASES:
            ctx=await b.new_context(viewport={'width':1100,'height':1000},device_scale_factor=2,color_scheme=th)
            a=await ctx.new_page(); await a.goto(f'file:///home/claude/ref/proto_render.html?w={w}'); await a.wait_for_timeout(200)
            pa=await a.locator(f'#ex-{cid} .card').evaluate(JS)
            for viewer in ('light','dark'):
                c2=await b.new_context(viewport={'width':1100,'height':1000},device_scale_factor=2,color_scheme=viewer)
                r=await c2.new_page(); await r.goto('file:///home/claude/ref/roundup-card-reference-standalone.html'); await r.wait_for_timeout(200)
                pr=await r.locator(f'.sp-{th}[data-ex={cid}][style*="{w}px"] .card').first.evaluate(JS)
                diffs=[]
                if len(pa)!=len(pr): diffs.append(('count',len(pa),len(pr)))
                for x,y in zip(pa,pr):
                    for k in x:
                        if isinstance(x[k],float) or isinstance(x[k],int):
                            if abs(x[k]-y[k])>0.11: diffs.append((x['k'],k,x[k],y[k]))
                        elif x[k]!=y[k]: diffs.append((x['k'],k,x[k],y[k]))
                n+=len(pa); bad+=len(diffs)
                print(cid,th,w,'viewer',viewer,'elements',len(pa),'differences',len(diffs),diffs[:4])
                await c2.close()
            await ctx.close()
        print('TOTAL elements compared',n,'differences',bad)
        await b.close()
asyncio.run(main())
