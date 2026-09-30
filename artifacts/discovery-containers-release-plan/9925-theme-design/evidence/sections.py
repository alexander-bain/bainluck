import json,re,collections
C=json.load(open('/tmp/d9925/classified.json'))
inv={r[0]:r for r in json.load(open('/tmp/d9925/q1all.out.json'))['rows']}
cols=json.load(open('/tmp/d9925/q1all.out.json'))['columns']
invai={r[0]:dict(zip(json.load(open('/tmp/d9925/q4all.out.json'))['columns'],r)) for r in json.load(open('/tmp/d9925/q4all.out.json'))['rows']}
def row(i): return dict(zip(cols,inv[i]))
def cer(n):
    l=n.lower()
    if 'latin grammy' in l: return 'Latin Grammys'
    if 'daytime emmy' in l: return 'Daytime Emmys'
    if 'gramm' in l: return 'Grammys'
    if re.search(r'\b(oscars?|academy awards?)\b',l): return 'Oscars'
    return 'other'
def stage(n):
    l=n.lower()
    if 'attend' in l or re.search(r'most .*nominations',l): return 'around'
    if re.search(r'nominat|nominees',l): return 'nominations'
    return 'winners'
def label(n):
    s=re.sub(r'^(Oscars?|Grammys?)( 2027)?\s*(Winner|winner|nominees|Nominees)?\s*[:·]\s*','',n)
    s=re.sub(r'^(Oscar|Grammy) (Winner|winner|nominees)\s*[:·]\s*','',s)
    s=re.sub(r'^(Daytime Emmy Awards|Latin Grammy Awards):\s*','',s)
    s=re.sub(r'\s*(Winner|Nominations)\s*$','',s).strip()
    return s
def key(n): return (cer(n),stage(n),label(n).lower().replace('achievement in','best').replace('best music (original score)','best original score').strip())
kept=C['story:major_entertainment_events']['kept']
# 1) group_id collapse (existing _dedupe_futures_by_group_id): polymarket group children -> one row (prefer the multi-outcome parent)
bygroup=collections.OrderedDict()
for m in kept:
    r=row(m['id']); g=r['group_id'] or f"solo:{m['id']}"
    bygroup.setdefault(g,[]).append(r)
parents=[]
for g,rs in bygroup.items():
    rs.sort(key=lambda r:(-(r['n_out'] or 0), -(r['volume_24h'] or 0)))
    p=dict(rs[0]); p['children']=len(rs)-1; parents.append(p)
# 2) proposed cross-venue fold on (ceremony, stage, category) — NOT current behaviour
folded=collections.OrderedDict()
for p in parents:
    k=key(p['name'])
    if p['name'].lower().startswith('will '): k=k+(p['id'],)
    folded.setdefault(k,[]).append(p)
secs=collections.OrderedDict()
for k,ps in folded.items():
    ps.sort(key=lambda r:(-(r['volume_24h'] or 0), 0 if r['source']=='kalshi' else 1))
    lead=ps[0]
    secs.setdefault(k[0],collections.OrderedDict()).setdefault(k[1],[]).append({
        'id':lead['id'],'name':lead['name'],'label':label(lead['name']),'leader':lead['leader'],'sources':sorted({x['source'] for x in ps}),
        'twin_ids':[x['id'] for x in ps[1:]],'twin_leaders':[x['leader'] for x in ps[1:]],'img':lead['img'],'vol24':lead['volume_24h'],'res':str(lead['res']),'n_out':lead['n_out'],'children':lead['children']})
tot=0
for c,st in secs.items():
    for s,rows in st.items():
        rows.sort(key=lambda r:-(r['vol24'] or 0)); tot+=len(rows)
        print(c,s,len(rows),'first dates',min(r['res'] for r in rows))
print('awards distinct questions after group collapse + proposed fold:',tot,'| parents before fold',len(parents),'| rows before group collapse',len(kept))
# AI
ai=C['story:ai']['kept']; g2=collections.OrderedDict()
for m in ai:
    r=invai[m['id']]; g=r['group_id'] or f"solo:{m['id']}"; g2.setdefault(g,[]).append(r)
aip=[]
for g,rs in g2.items():
    rs.sort(key=lambda r:(-(r['volume_24h'] or 0)))
    p=dict(rs[0]); p['children']=len(rs)-1; aip.append(p)
import datetime
def horizon(res):
    if not res or res=='None': return 'No stated date'
    d=datetime.date.fromisoformat(str(res))
    if d<=datetime.date(2026,10,31): return 'Decided in October'
    if d<=datetime.date(2027,1,5): return 'Decided by the new year'
    return 'Later'
hz=collections.OrderedDict((h,[]) for h in ['Decided in October','Decided by the new year','Later','No stated date'])
for p in aip: hz[horizon(p['res'])].append({'id':p['id'],'name':p['name'],'leader':p['leader'],'source':p['source'],'vol24':p['volume_24h'],'res':str(p['res']),'img':p['img'],'children':p['children']})
for h,v in hz.items(): v.sort(key=lambda r:-(r['vol24'] or 0)); print('AI',h,len(v))
print('AI distinct questions after group collapse:',len(aip),'rows before',len(ai))
json.dump({'awards':secs,'ai':hz,'awards_nearmiss':C['story:major_entertainment_events']['nearmiss'],'ai_nearmiss':C['story:ai']['nearmiss'],'counts':{'awards_candidates':216,'awards_rows':len(kept),'awards_groups':len(parents),'awards_questions':tot,'ai_candidates':375,'ai_rows':len(ai),'ai_questions':len(aip)}},open('/tmp/d9925/sections.json','w'),indent=1,default=str)
