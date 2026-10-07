# Renders the revision 3 states and measures them. Also checks the reference page at phone width.
import asyncio, json
from playwright.async_api import async_playwright
STATES = ['all8', 'three3', 'partial', 'old', 'mixed']
JS = '''(el)=>{const r=x=>{const b=x.getBoundingClientRect();return {x:+b.x.toFixed(1),y:+b.y.toFixed(1),w:+b.width.toFixed(1),h:+b.height.toFixed(1)}};
const c=r(el);const src=el.querySelector('.src');const s=r(src);const lh=parseFloat(getComputedStyle(src).lineHeight)||0;
const rows=[...el.querySelectorAll('.row')].map(x=>r(x).h);
const ages=[...el.querySelectorAll('.age')].map(a=>{const b=r(a);return {text:a.innerText.trim(),right_inset:+(c.x+c.w-(b.x+b.w)).toFixed(1),top:+(b.y-c.y).toFixed(1),w:b.w,h:b.h,in_footer:!!a.closest('.src')}});
const srcText=src.querySelector('span')||src;const range=document.createRange();range.selectNodeContents(srcText);const lines=new Set([...range.getClientRects()].map(q=>Math.round(q.top))).size;
return {card_h:c.h,card_w:c.w,footer_h:s.h,footer_lines:lines,row_h:rows,ages}}'''
async def main():
    out = {}
    async with async_playwright() as p:
        b = await p.chromium.launch()
        ctx = await b.new_context(viewport={'width': 600, 'height': 900}, device_scale_factor=2, color_scheme='light')
        pg = await ctx.new_page(); errs = []; pg.on('pageerror', lambda e: errs.append(str(e)))
        await pg.goto('file:///home/claude/ref3/r3_render.html'); await pg.wait_for_timeout(300)
        for s in STATES:
            for w in (340, 358, 448):
                loc = pg.locator(f'.sp[data-state={s}][style*="{w}px"] .card').first
                await loc.screenshot(path=f'reference-images-r3/r3_{s}_light_{w}.png')
                out[f'{s}_{w}'] = await loc.evaluate(JS)
        await ctx.close()
        for scheme in ('light', 'dark'):
            for vw, vh in ((390, 800), (1100, 1000)):
                ctx = await b.new_context(viewport={'width': vw, 'height': vh}, device_scale_factor=2, color_scheme=scheme)
                pg = await ctx.new_page(); pg.on('pageerror', lambda e: errs.append(str(e)))
                await pg.goto('file:///home/claude/ref3/roundup-card-reference-standalone.html'); await pg.wait_for_timeout(300)
                out[f'page_{scheme}_{vw}'] = dict(scrollWidth=await pg.evaluate('document.documentElement.scrollWidth'), viewport=vw)
                await pg.screenshot(path=f'page_{scheme}_{vw}.png', full_page=True)
                await ctx.close()
        await b.close()
    out['page_errors'] = errs
    json.dump(out, open('r3_measure.json', 'w'), indent=1)
    for k, v in out.items():
        if k.startswith('page'): print(k, v)
        else: print(k, 'card_h', v['card_h'], 'footer_lines', v['footer_lines'], 'rows', v['row_h'], 'ages', v['ages'])
asyncio.run(main())
