import asyncio
from playwright.async_api import async_playwright
FAKE="""window.claude={use:async n=>({doc:p=>({set:async d=>{}}),collection:c=>({onSnapshot:(f)=>{setTimeout(()=>f({docs:[]}),30)}})})}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch()
        for scheme in ('light','dark'):
            for (w,h) in ((390,800),(950,1028)):
                ctx=await b.new_context(viewport={'width':w,'height':h},device_scale_factor=2,color_scheme=scheme)
                pg=await ctx.new_page(); errs=[]; pg.on('pageerror',lambda e:errs.append(str(e))); await pg.add_init_script(FAKE)
                await pg.goto('file:///home/claude/ref/context.html'); await pg.wait_for_timeout(400)
                await pg.screenshot(path=f'context_{w}x{h}_{scheme}.png')
                await pg.click('.acts .more'); await pg.wait_for_timeout(200)
                await pg.screenshot(path=f'context_{w}x{h}_{scheme}_details.png',full_page=True)
                g=await pg.evaluate("(()=>{const c=document.querySelector('.card').getBoundingClientRect(),a=document.querySelector('.acts').getBoundingClientRect();return {card:[c.left,c.top,c.width,c.height].map(x=>+x.toFixed(1)),acts:[a.left,a.top,a.width,a.height].map(x=>+x.toFixed(1)),gap:+(a.top-c.bottom).toFixed(1)}})()")
                print(scheme,w,h,g,errs); await ctx.close()
        await b.close()
asyncio.run(main())
