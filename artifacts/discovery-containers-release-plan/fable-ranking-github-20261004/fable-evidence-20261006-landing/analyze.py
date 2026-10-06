import json,glob,datetime as dt,statistics as st
IDS=[109596,108620,112902,15203993,56933330,2279147,63849278,199050,270,5869749,11415154,109946,8430022,30635376,52755900,113799,112827,25923984,27594646,109358,62239632]
def ts(s): return dt.datetime.fromisoformat(s.replace('Z','+00:00'))
out=[]
for i in IDS:
    d=json.load(open(f'raw/{i}_detail.json'))
    oc=sorted(d.get('outcomes',[]),key=lambda o:-(o.get('probability') or 0))
    rec={'id':i,'name':d.get('name'),'description':d.get('description'),'source':d.get('source'),'bookmakers':d.get('bookmakers'),'market_type':d.get('market_type'),'category':d.get('category'),'status':d.get('status'),'n_outcomes':d.get('outcome_count'),'resolution_date':d.get('resolution_date'),'created_at':d.get('created_at'),
         'extra_keys':[k for k in d if k not in('outcomes',)],
         'top':[{'name':o['name'],'p':o.get('probability'),'open':o.get('opening_probability'),'chg24':o.get('probability_change_24h'),'is_winner':o.get('is_winner'),'last_updated':o.get('last_updated'),'price_changed_at':o.get('price_changed_at'),'img':{k:v for k,v in o.items() if any(s in k for s in('image','logo','photo','icon','wiki'))}} for o in oc[:3]]}
    rec['sum_p']=round(sum((o.get('probability') or 0) for o in oc),3)
    for h in (168,720,8760):
        H=json.load(open(f'raw/{i}_hist{h}.json'))
        lead=oc[0]['name'] if oc else None
        ser=None
        for o in H.get('outcomes',[]):
            if o.get('name')==lead: ser=o
        if ser is None and H.get('outcomes'): ser=max(H['outcomes'],key=lambda o:len(o.get('history',[])))
        pts=[(ts(p['timestamp']),p['probability']) for p in (ser or {}).get('history',[]) if p.get('probability') is not None]
        pts.sort()
        r={'lead':(ser or {}).get('name'),'n':len(pts),'total_points':H.get('total_data_points'),'coverage_start':H.get('coverage_start'),'coverage_end':H.get('coverage_end'),'coverage_hours':H.get('coverage_hours'),'actual_hours':H.get('actual_hours'),'venue_history':bool(H.get('venue_history')),'round_boundaries':len(H.get('round_boundaries') or [])}
        if pts:
            vals=[v for _,v in pts]
            r.update(first=pts[0][0].isoformat()[:16],last=pts[-1][0].isoformat()[:16],span_h=round((pts[-1][0]-pts[0][0]).total_seconds()/3600,1),vmin=round(min(vals)*100,1),vmax=round(max(vals)*100,1),rng=round((max(vals)-min(vals))*100,1),net=round((vals[-1]-vals[0])*100,1))
            steps=[(abs(vals[k+1]-vals[k])*100,pts[k+1][0].isoformat()[:16],round(vals[k]*100,1),round(vals[k+1]*100,1)) for k in range(len(vals)-1)]
            gaps=[((pts[k+1][0]-pts[k][0]).total_seconds()/3600,pts[k][0].isoformat()[:16]) for k in range(len(pts)-1)]
            if steps:
                b=max(steps); r['max_step']=[round(b[0],1),b[1],b[2],b[3]]
                g=max(gaps); r['max_gap_h']=[round(g[0],1),g[1]]
                r['distinct_vals']=len(set(round(v,3) for v in vals))
            bk=set(p.get('bookmaker') for p in ser['history']); r['bookmaker_tags']=sorted(x for x in bk if x)
        rec[f'h{h}']=r
    out.append(rec)
json.dump(out,open('metrics.json','w'),indent=1,default=str)
for r in out:
    print(f"\n=== {r['id']} {r['name']} | src={r['source']} books={r['bookmakers']} type={r['market_type']} n_out={r['n_outcomes']} sumP={r['sum_p']} desc={'yes' if r['description'] else 'NONE'} resolves={str(r['resolution_date'])[:10]} created={str(r['created_at'])[:10]}")
    for t in r['top']: print('   ',t['name'][:40],round((t['p'] or 0)*100,1),'open',t['open'],'chg24',t['chg24'],'upd',str(t['last_updated'])[:16],'img',t['img'])
    for h in (168,720,8760):
        x=r[f'h{h}']; print(f"   h{h}: lead={x.get('lead')} n={x['n']} span_h={x.get('span_h')} first={x.get('first')} last={x.get('last')} range={x.get('rng')} net={x.get('net')} distinct={x.get('distinct_vals')} max_step={x.get('max_step')} max_gap_h={x.get('max_gap_h')} books={x.get('bookmaker_tags')} cov_h={x.get('coverage_hours')}")
