import asyncio,json
from playwright.async_api import async_playwright
JS="""()=>{const g=(sel,props)=>{const e=document.querySelector(sel); if(!e) return null; const c=getComputedStyle(e), r=e.getBoundingClientRect(); const o={w:+r.width.toFixed(1),h:+r.height.toFixed(1)}; props.forEach(p=>o[p]=c.getPropertyValue(p)); return o};
const T=['font-size','line-height','font-weight','letter-spacing','color','font-family','text-transform'];
const B='#ex-canonical ';
const out={card:g(B+'.card',['padding-top','padding-right','padding-bottom','padding-left','border-top-width','border-top-color','border-radius','background-color','row-gap']),
 khead:g(B+'.khead',['column-gap']),kicker:g(B+'.kicker',T),tag:g(B+'.tag',T.concat(['background-color','padding-top','padding-left','border-radius'])),
 headline:g(B+'.headline',T.concat(['margin-top'])),rows:g(B+'.rows',['row-gap']),row:g(B+'.row',['grid-template-columns','column-gap']),
 num:g(B+'.row .n',T.concat(['text-align'])),pct:g(B+'.row .n small',T.concat(['margin-left'])),text:g(B+'.row .t',T),
 meter:g(B+'.row .meter',['height','border-radius','background-color','margin-top']),fill:g(B+'.row .meter i',['background-color','border-top-right-radius','min-width']),
 src:g(B+'.src',T.concat(['border-top-width','border-top-color','padding-top'])),body:g('body',['background-color']),
 longHeadline:g('#ex-long .headline',T),
 geom:(()=>{const c=document.querySelector(B+'.card').getBoundingClientRect(); const q=s=>[...document.querySelectorAll(B+s)].map(e=>{const r=e.getBoundingClientRect(); return [+(r.left-c.left).toFixed(1),+(r.top-c.top).toFixed(1),+r.width.toFixed(1),+r.height.toFixed(1)]}); return {card:[c.width,c.height],kicker:q('.kicker'),tag:q('.tag'),headline:q('.headline'),rows:q('.row'),nums:q('.row .n'),texts:q('.row .t'),meters:q('.row .meter'),fills:q('.row .meter i'),src:q('.src')}})(),
 heights:Object.fromEntries([...document.querySelectorAll('.slot')].map(s=>[s.id,+s.firstChild.getBoundingClientRect().height.toFixed(1)])),
 markup:document.querySelector(B+'.card').outerHTML};
return out}"""
async def main():
    async with async_playwright() as p:
        b=await p.chromium.launch(); res={}
        for scheme in ('light','dark'):
            for w in (358,340,448):
                ctx=await b.new_context(viewport={'width':max(w+32,390),'height':900},device_scale_factor=2,color_scheme=scheme)
                pg=await ctx.new_page(); await pg.goto(f'file:///home/claude/ref/proto_render.html?w={w}'); await pg.wait_for_timeout(300)
                res[f'{scheme}_{w}']=await pg.evaluate(JS)
                for cid in ('canonical','three','long','extremes'):
                    await pg.locator(f'#ex-{cid} .card').screenshot(path=f'proto_{cid}_{scheme}_{w}.png')
                await ctx.close()
        json.dump(res,open('measure.json','w'),indent=1)
        m=res['light_358']
        for k,v in m.items():
            if k not in('markup','geom'): print(k,v)
        print(json.dumps(m['geom'])); print(m['markup'])
        d=res['dark_358']; print('DARK',{k:{p:v for p,v in d[k].items() if 'color' in p} for k in ('card','kicker','tag','headline','num','pct','text','meter','fill','src','body')})
        print('heights',{k:v['heights'] for k,v in res.items()})
        await b.close()
asyncio.run(main())
