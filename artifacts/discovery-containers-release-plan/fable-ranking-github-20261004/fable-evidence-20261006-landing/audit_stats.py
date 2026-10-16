"""Prints every number quoted in FABLE-LANDING-PAGE-AUDIT-20261006.md from the files in this bundle only."""
import json,statistics as st,os,re
R='raw/'
IDS=[109596,108620,112902,15203993,56933330,2279147,63849278,199050,270,5869749,11415154,109946,8430022,30635376,52755900,113799,112827,25923984,27594646,109358,62239632]
obs=json.load(open('observed_pages.json'))
D={i:json.load(open(f'{R}{i}_detail.json')) for i in IDS}
def lead(d): return sorted(d['outcomes'],key=lambda o:-(o.get('probability') or 0))[0]
def series(i,h,name):
    H=json.load(open(f'{R}{i}_hist{h}.json'))
    for o in H['outcomes']:
        if o['name']==name: return H,[p for p in o['history'] if p.get('probability') is not None]
    return H,[]
print('A. pages:',len(IDS),'| rendered and read:',len(obs['pages']))
print('B. description empty:',sum(1 for d in D.values() if not d.get('description')),'of',len(IDS),'| hook_description empty:',sum(1 for d in D.values() if not d.get('hook_description')),'| hook_withheld true:',sum(1 for d in D.values() if d.get('hook_withheld')))
print('   image_url is a pexels.com stock photo:',sum(1 for d in D.values() if 'pexels' in (d.get('image_url') or '')),'| no image_url:',sum(1 for d in D.values() if not d.get('image_url')))
print('C. pages listing exactly one venue:',sum(1 for d in D.values() if len(d.get('bookmakers') or [])==1),'of',len(IDS),'| kalshi:',sum(1 for d in D.values() if d['source']=='kalshi'),'polymarket:',sum(1 for d in D.values() if d['source']=='polymarket'))
print('   twin pages (same question, two pages):')
for a,b in ((108620,112902),(15203993,56933330),(270,199050)):
    la,lb=lead(D[a]),lead(D[b])
    print(f"     {a} [{D[a]['source']}] {la['name']} {la['probability']*100:.1f}% caption={obs['pages'][str(a)]['caption']!r}  ||  {b} [{D[b]['source']}] {lb['name']} {lb['probability']*100:.1f}% caption={obs['pages'][str(b)]['caption']!r}")
print('D. first-request chart data, one-week view (the first response each page got in this audit):')
rows=[]
import datetime as dt
T=lambda s: dt.datetime.fromisoformat(s)
for i in IDS:
    d=D[i]; l=lead(d); H,pts=series(i,168,l['name'])
    vh=H.get('venue_history') or {}
    gaps=[(T(pts[k+1]['timestamp'])-T(pts[k]['timestamp'])).total_seconds()/3600 for k in range(len(pts)-1)]
    vals=[p['probability']*100 for p in pts]
    _,m=series(i,720,l['name']); mv=[p['probability']*100 for p in m]
    rows.append(dict(id=i,src=d['source'],state=vh.get('state'),n=len(pts),maxgap=round(max(gaps),1) if gaps else None,wk_range=round(max(vals)-min(vals),1),wk_net=round(vals[-1]-vals[0],1),mo_range=round(max(mv)-min(mv),1),mo_net=round(mv[-1]-mv[0],1),open=l.get('opening_probability'),p=l['probability']*100,name=l['name']))
for r in rows: print(f"     {r['id']:>9} {r['src']:<10} state={str(r['state']):<7} lead_points={r['n']:>3} longest_gap_h={r['maxgap']} week_range={r['wk_range']} week_net={r['wk_net']:+} month_range={r['mo_range']} month_net={r['mo_net']:+}")
ns=[r['n'] for r in rows]
print('   lead points in the week: min',min(ns),'median',st.median(ns),'max',max(ns),'| pages under 50 points:',sum(1 for n in ns if n<50),'| under 30:',sum(1 for n in ns if n<30),'| 100 or more:',sum(1 for n in ns if n>=100))
for s in ('kalshi','polymarket'):
    x=[r['n'] for r in rows if r['src']==s]; print('   ',s,'pages',len(x),'lead points sorted',sorted(x))
print('   states on first request:',{k:sum(1 for r in rows if r['state']==k) for k in sorted(set(r['state'] for r in rows))})
print('E. movement that exists in the data: pages whose leader moved 10+ points net over the month:',sum(1 for r in rows if abs(r['mo_net'])>=10),'of',len(rows),'| 15+:',sum(1 for r in rows if abs(r['mo_net'])>=15))
print('F. caption direction against the default view (net move of the captioned outcome itself):')
k=0;n=0
for r in rows:
    o=obs['pages'].get(str(r['id']))
    if not o or not o.get('caption'): continue
    cap=o['caption']; up=' up ' in cap; nm=re.split(r' (?:up|down) [0-9.]+ pts',cap)[0]
    h=168 if o['default_range']=='1W' else 720
    _,pp=series(r['id'],h,nm)
    if len(pp)<2: print('     (no series for',nm,'on',r['id'],')'); continue
    n+=1; net=round((pp[-1]['probability']-pp[0]['probability'])*100,1)
    if abs(net)>=3 and ((net>0)!=up):
        k+=1; print(f"     {r['id']} default {o['default_range']} net {net:+} but caption: {cap}")
print('   pages where caption direction opposes a 3+ point net move in the default view:',k,'of',n,'captioned pages checked')
print('G. fill timing test:')
for row in json.load(open(R+'_cold_warm_test.json')):
    print('    ',row['id'],row['source'],[(s['t_s'],s['state'],s['max_outcome_points']) for s in row['seq']])
for row in json.load(open(R+'_cold_warm_recheck.json'))[:4]:
    print('     recheck',row['id'],row['utc'],row['state'],'built_at',row['built_at'],'lead_pts',row['lead_pts'])
print('H. headline freshness:')
F=json.load(open(R+'_freshness.json'))['rows']; c=[r for r in F if r['diff'] is not None]
print('    outcome rows compared:',len(c),'| within 1 point:',sum(1 for r in c if abs(r['diff'])<=1),'| largest gap:',max(c,key=lambda r:abs(r['diff'])))
print('I. Taylor Swift wedding dress page:',D[52755900]['status'],'outcomes',D[52755900]['outcome_count'],'sum of probabilities',round(sum((o.get('probability') or 0) for o in D[52755900]['outcomes']),2),'Dior',lead(D[52755900])['probability'],'external id',D[52755900]['external_id'])
w=[o for o in D[113799]['outcomes'] if o.get('is_winner')]; print('   attendee page: outcomes marked winner',len(w),'of',D[113799]['outcome_count'],[o['name'] for o in w][:6])
g=obs['chart_geometry']; print('J. chart plot at',g['viewport_css_px'],'px viewport: width',g['plotted_x'][1]-g['plotted_x'][0],'of',g['svg'][0],'=',round((g['plotted_x'][1]-g['plotted_x'][0])/g['svg'][0]*100),'% | height for 0-100:',g['plotted_y'][1]-g['plotted_y'][0],'px')
print('K. resolution dates served: Best Actor',D[5869749]['resolution_date'][:10],'| Senate',D[108620]['resolution_date'][:10],'/',D[112902]['resolution_date'][:10])
z=json.load(open(R+'62239632_hist168_warm.json'))
for o in z['outcomes']:
    if o['name']=='Kansas City Chiefs':
        seg=[round(p['probability']*100,1) for p in o['history'] if '2026-10-06T11:28'<=p['timestamp']<'2026-10-06T11:53']
        print('L. Last Unbeaten Team, Chiefs, venue points 11:28-11:52 UTC Oct 6:',seg)
print('G2. first history request in this audit -> time the fuller venue history was built:')
log={r['id']:r['fetched_utc'] for r in json.load(open(R+'_fetchlog.json')) if r['what']=='hist168'}
fin=json.load(open(R+'_final_state_recheck.json'))
ds=[]
for r in fin:
    if r['id'] in log and r['state']=='warm' and r['built_at']:
        a=dt.datetime.fromisoformat(log[r['id']].replace('Z','+00:00')); b=dt.datetime.fromisoformat('2026-10-06T'+r['built_at']+'+00:00')
        first=[x for x in rows if x['id']==r['id']][0]
        if first['state']=='cold':
            ds.append((b-a).total_seconds()); print(f"     {r['id']} first request {log[r['id']][11:19]} built {r['built_at']} = {int((b-a).total_seconds())} s | lead points {first['n']} -> {r['lead_pts']}")
print('   pages cold on first request that later filled:',len(ds),'| seconds to fill: min',int(min(ds)),'median',int(st.median(ds)),'max',int(max(ds)))
for row in json.load(open(R+'_cold_warm_test.json')):
    f=([x for x in fin if x['id']==row['id']]+[x for x in json.load(open(R+'_cold_warm_recheck.json')) if x['id']==row['id'] and x['built_at']])[0]; a=dt.datetime.fromisoformat('2026-10-06T'+row['seq'][0]['utc']+'+00:00'); b=dt.datetime.fromisoformat('2026-10-06T'+f['built_at']+'+00:00')
    print('     timing test',row['id'],'first request',row['seq'][0]['utc'],'built',f['built_at'],'=',int((b-a).total_seconds()),'s')
c=[(r['source'],r['state'],r['lead_pts']) for r in fin if r['id'] in log]
print('   end state of the 21 pages:',{s:sum(1 for x in c if x[1]==s) for s in sorted(set(x[1] for x in c))})
print('   pages still not filled (state refused) and their lead points:',sorted((r['id'],r['lead_pts']) for r in fin if r['id'] in log and r['state']=='refused'))
print('   of those, under 100 lead points for the week:',sum(1 for r in fin if r['id'] in log and r['state']=='refused' and r['lead_pts']<100))

print('M. props pages (data only):')
for i in (63849252,64211384):
    d=json.load(open(f'{R}{i}_detail.json')); H=json.load(open(f'{R}{i}_hist168.json'))
    print('    ',i,d['name'][:60],'| total points in week',H.get('total_data_points'),'| description',d.get('description'),'| hook',d.get('hook_description'))
print('N. filled pages: lead points before -> after:',sorted((x['n'],[f['lead_pts'] for f in fin if f['id']==x['id']][0]) for x in rows if x['state']=='cold' and [f for f in fin if f['id']==x['id']][0]['state']=='warm'))
