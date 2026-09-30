import json, sys, collections, re
sys.path.insert(0,'.')
import logging; logging.disable(logging.CRITICAL)
from app.utils.feed_market_quality import _story_key
from app.utils import discover_bundles as db

def load(path):
    d=json.load(open(path)); cols=d['columns']
    return [dict(zip(cols,r)) for r in d['rows']]

def run(path, key, edition=None):
    rows=load(path)
    res=collections.OrderedDict(); kept=[]; nearmiss=collections.defaultdict(list)
    for r in rows:
        cat=r.get('cat') or r.get('cat0') or ''
        item={'type':'futures','data':{'id':r['id'],'name':r['name'],'source':r['source'],'llm_sport_category':cat,'canonical_market_key':r.get('canonical_market_key'),'group_id':r.get('group_id'),'resolution_date':str(r.get('res'))}}
        sk=_story_key(r['name'],cat)
        if sk!=key: nearmiss['story_key_routes_elsewhere:'+str(sk)].append(r); continue
        if key=='story:major_entertainment_events' and not db._is_entertainment(item):
            nearmiss['not_entertainment_category('+str(cat)+')'].append(r); continue
        season=db._member_season(item)
        if edition and season and season!=edition:
            nearmiss['other_season:'+season].append(r); continue
        if not db._member_answers_story_question(key,item):
            nearmiss['candidacy_not_victory'].append(r); continue
        kept.append(item)
    k2, folded = db._dedupe_same_question_members(kept)
    return rows, k2, folded, nearmiss

out={}
for path,key,ed in [('/tmp/d9925/q1all.out.json','story:major_entertainment_events','2027'),('/tmp/d9925/q4all.out.json','story:ai',None)]:
    rows,k2,folded,nm=run(path,key,ed)
    print('=====',key,'candidates',len(rows),'eligible_after_gates',len(k2)+len(folded),'distinct_after_same_question_fold',len(k2),'folded_dups',len(folded))
    for reason,rs in nm.items(): print('  near-miss',reason,len(rs),'e.g.',[ (x['id'],x['name'][:60]) for x in rs[:3]])
    print('  folded examples:',[(f['data']['id'],f['data']['name'][:60]) for f in folded[:8]])
    out[key]={'candidates':len(rows),'kept':[f['data'] for f in k2],'folded':[f['data'] for f in folded],'nearmiss':{k:[(x['id'],x['name'],x.get('cat') or x.get('cat0')) for x in v] for k,v in nm.items()}}
json.dump(out,open('/tmp/d9925/classified.json','w'),indent=1,default=str)
