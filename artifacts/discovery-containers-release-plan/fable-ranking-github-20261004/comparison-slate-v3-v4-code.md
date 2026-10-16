# Comparison Slates v3 and v4: generator code, checker prompts and the price-history check

Saved by Fable, Tue 2026-10-06. Working code from the session workspace, unedited. Offline experiment code, not product code. `t4.py` is `t3.py` pointed at a later pull. Depends on `pull.py` and `props.py` in `claude/comparison-slate-v1-code.md`.

## v3/t3.py

````python
import json,re,collections,datetime,sys
sys.path.insert(0,'..')
from props import toks
A=json.load(open('../pull2/props_all.json'))
W=json.load(open('../props_wide_labeled.json'))
key=lambda r:(r['src'],r['ev'],r['name'])
lab={key(r):r for r in W}
T=[]
for a in A:
    l=lab.get(key(a))
    if not l: continue
    r=dict(a); 
    for k in ('plain','gotcha','subject','domain','recog','appeal','weight','tone','naive'): r[k]=l[k]
    r['p_old']=l['p']; r['wid']=l['id']; r['plain']=r['plain'].strip().rstrip('.')
    T.append(r)
print('wide rows',len(W),'still listed',len(T))
def issport(p): return 'Sports' in (p['cat'] or '')
def liquid(p):
    sp=p['spread']
    if p['kind']=='date':
        return p['evvol']>=(300000 if issport(p) else 75000) and p['vol']>=10000 and (sp is None or sp<=0.08)
    mv,ev=(50000,300000) if issport(p) else (20000,75000)
    if p['vol']<mv or p['evvol']<ev: return False
    if sp is not None and sp>0.06: return False
    if sp is None and (p['v24'] or 0)<=0: return False
    return True
for r in T: r['liquid']=liquid(r)
L=[r for r in T if r['liquid']]
print('liquid',len(L),collections.Counter(r['kind'] for r in L))
# cross-venue twins
SCOPE=set('us usa global world women womens men mens nfc afc al nl east west eastern western house senate party football basketball baseball hockey republican democratic run primary'.split())
def nm(s):
    s=re.sub(r'\((d|r|i)\)','',(s or '').lower()).replace('j.d.','jd').replace('u.s.','us'); return toks(s)
def jac(a,b): return len(a&b)/max(1,len(a|b))
def days(a,b):
    try: return abs((datetime.date.fromisoformat(a)-datetime.date.fromisoformat(b)).days)
    except: return 9999
for i,p in enumerate(L): p['tt']=nm(p['title']); p['nt']=nm(p['name']); p['i']=i
ks=[p for p in L if p['src']=='K']; ps=[p for p in L if p['src']=='P']; pairs=[]
for a in ks:
    best=None
    for b in ps:
        if a['kind']!=b['kind'] and not ({a['kind'],b['kind']}<={'binary','date'}): continue
        tj=jac(a['tt'],b['tt'])
        if tj<0.6 or (a['tt']^b['tt'])&SCOPE: continue
        if a['kind']=='named' and b['kind']=='named':
            if not a['nt'] or not b['nt']: continue
            if not (a['nt']<=b['nt'] or b['nt']<=a['nt'] or jac(a['nt'],b['nt'])>=0.6): continue
            sc=tj+0.5
        else:
            d=days(a['deadline'],b['deadline'])
            lim=45 if (a['kind']=='binary' and b['kind']=='binary') else 3
            if d>lim: continue
            sc=tj+0.5-d/1000
        if best is None or sc>best[0]: best=(sc,b)
    if best: pairs.append((a,best[1],best[0]))
used=set(); ok=[]; dis=[]
for a,b,sc in sorted(pairs,key=lambda x:-x[2]):
    if a['i'] in used or b['i'] in used: continue
    used.add(a['i']); used.add(b['i']); (ok if abs(a['p']-b['p'])<=0.06 else dis).append((a,b))
print('twins agree',len(ok),'disagree',len(dis))
drop=set(); 
for a,b in ok:
    a['venues']=['K','P']; a['pK']=a['p']; a['pP']=b['p']; a['p']=(a['p']+b['p'])/2; a['p_old']=(a['p_old']+b['p_old'])/2; a['chg']=b.get('chg'); drop.add(b['i'])
for a,b in dis: drop.add(a['i']); drop.add(b['i'])
M=[]
for p in L:
    if p['i'] in drop: continue
    p.setdefault('venues',[p['src']]); p.setdefault('pK',p['p'] if p['src']=='K' else None); p.setdefault('pP',p['p'] if p['src']=='P' else None)
    q={k:v for k,v in p.items() if k not in('tt','nt','i')}; q['id']='t%04d'%len(M); q['fam']=q['src']+':'+q['ev']; M.append(q)
json.dump(M,open('table.json','w'))
print('table',len(M),collections.Counter(q['kind'] for q in M),collections.Counter(q['domain'] for q in M).most_common(6))
mv=sorted(M,key=lambda q:-abs(q['p']-q['p_old']))[:8]
for q in mv: print('  overnight %+.0f -> %d  %s'%((q['p']-q['p_old'])*100,q['p']*100,q['plain'][:70]))
for a,b in dis[:8]: print('  DIS %d/%d %s'%(a['p']*100,b['p']*100,a['plain'][:60]))
````

## v3/gen3.py

````python
import json,re,collections,datetime,itertools,statistics as st
M=json.load(open('table.json'))
def d(s):
    try: return datetime.date.fromisoformat(s)
    except: return None
def pct(p):
    x=round(p*1000); return (x+5)//10
EXC={}
for l in open('../pull2/k.jsonl'):
    e=json.loads(l); EXC['K:'+str(e['t'])]=bool(e.get('mx'))
for l in open('../pull2/p.jsonl'):
    e=json.loads(l); EXC['P:'+str(e['id'])]=bool(e.get('neg'))
def nsubj(s):
    s=(s or '').lower().strip(); s=re.sub(r"^(the|president|us|u\.s\.) ",'',s)
    return {'trump':'donald trump','fed':'federal reserve','the fed':'federal reserve','gta 6':'gta vi','grand theft auto vi':'gta vi'}.get(s,s)
for q in M:
    q['pp']=pct(q['p']); q['dl']=d(q['deadline']) if q['deadline'] else None
    q['rn']=q['recog']/3; q['an']=q['appeal']/3; q['wn']=q['weight']/3
    q['Q']=q['rn']*(0.5*q['an']+0.3*q['wn']+0.2); q['subj']=nsubj(q['subject'])
OK=lambda q: q['tone'] in('light','neutral')
def foreign_election(q): return q['domain']=='world_politics' and re.search(r'election|ballot|referendum',q['plain']+' '+q['text'],re.I) is not None
E=[q for q in M if q['recog']>=2 and OK(q) and not foreign_election(q)]
BUCK=(('By the end of October','2026-10-28','2026-11-01'),('By the end of November','2026-11-28','2026-12-01'),('By the end of 2026','2026-12-25','2027-01-05'),('By spring 2027','2027-03-28','2027-04-02'),('By mid-2027','2027-06-25','2027-07-05'),('By the end of 2027','2027-12-25','2028-01-05'),("Before Trump's term ends",'2029-01-15','2029-01-25'),('By 2030','2029-12-25','2030-01-05'))
def bucket(q):
    x=q['dl']
    if not x: return None
    for name,lo,hi in BUCK:
        if d(lo)<=x<=d(hi): return name
C=[]
def add(t,members,score,**kw): C.append(dict(type=t,ids=[m['id'] for m in members],score=round(score,4),**kw))
# ---------- boards
byb=collections.defaultdict(list)
for q in E:
    if q['kind'] in('date','binary') and 2<=q['pp']<=98 and bucket(q): byb[bucket(q)].append(q)
def pick(pool,maxdom,n=5,gap=4,ban=()):
    out=[]
    for q in pool:
        if q['id'] in ban or any(q['subj']==o['subj'] or q['fam']==o['fam'] for o in out): continue
        if sum(1 for o in out if o['domain']==q['domain'])>=maxdom: continue
        if any(abs(q['pp']-o['pp'])<gap for o in out): continue
        out.append(q)
        if len(out)==n: break
    return sorted(out,key=lambda q:-q['p'])
for b,pool in byb.items():
    pool=sorted(pool,key=lambda q:-q['Q']); ban=set()
    for k in range(6):
        mem=pick(pool,2,ban=ban)
        if len(mem)<5: break
        add('board',mem,st.mean(q['Q'] for q in mem)-0.05*k,title=b); ban|={q['id'] for q in mem[:5]}
# ---------- same-odds groups
BANDS=((0.05,'About 1 in 20'),(0.10,'About 1 in 10'),(0.20,'About 1 in 5'),(0.25,'About 1 in 4'),(0.33,'About 1 in 3'),(0.50,'A coin flip'),(0.67,'About 2 in 3'),(0.75,'About 3 in 4'),(0.90,'About 9 in 10'))
def anchored(q): return q['kind']!='date' or bucket(q) is not None
for c,name in BANDS:
    pool=sorted([q for q in E if abs(q['p']-c)<=0.016 and anchored(q) and q['appeal']>=2],key=lambda q:-q['Q']); out=[]
    for q in pool:
        if any(q['subj']==o['subj'] or q['fam']==o['fam'] for o in out) or sum(1 for o in out if o['domain']==q['domain'])>=2: continue
        out.append(q)
        if len(out)==4: break
    if len(out)==4 and any(o['tone']=='light' for o in out) and any(o['weight']>=2 for o in out):
        add('band',sorted(out,key=lambda q:-q['p']),st.mean(q['Q'] for q in out),title=name)
# ---------- dead heats
fam=collections.defaultdict(list)
for q in M:
    if q['kind']=='named': fam[q['fam']].append(q)
def common_suffix(a,b):
    A,B=a.split(),b.split(); k=0
    while k<min(len(A),len(B)) and A[-1-k]==B[-1-k]: k+=1
    return ' '.join(A[len(A)-k:]),' '.join(A[:len(A)-k]),' '.join(B[:len(B)-k])
for f,ms in fam.items():
    if not EXC.get(f): continue
    ms=sorted(ms,key=lambda q:-q['p'])
    if len(ms)<2: continue
    a,b=ms[0],ms[1]
    if a['p']-b['p']>0.035 or b['p']<0.2 or not(OK(a) and OK(b)) or min(a['recog'],b['recog'])<2 or foreign_election(a): continue
    suf,na,nb=common_suffix(a['plain'],b['plain'])
    if len(suf.split())<3 or not na or not nb or len(na.split())>4 or len(nb.split())>4 or any(c['type']=='deadheat' and c['title']=='____ '+suf for c in C): continue
    add('deadheat',[a,b],(a['Q']+b['Q'])/2*(1.1 if a['appeal']>=2 else 1),title='____ '+suf,names=[na,nb],rest=pct(max(0,1-a['p']-b['p'])))
# ---------- peer tables and head-to-heads (events whose venue titles differ only in one short span)
def ttoks(t): return re.sub(r"[^A-Za-z0-9&'.\- ]"," ",t).split()
evs={}
for q in M:
    if q['kind']!='named' and OK(q): evs.setdefault(q['fam'],[]).append(q)
keys=collections.defaultdict(dict)
for f,ms in evs.items():
    tk=ttoks(ms[0]['title'])
    for i in range(len(tk)):
        for L in (1,2,3):
            if i+L>len(tk) or len(tk)-L<2: continue
            keys[(tuple(x.lower() for x in tk[:i]),tuple(x.lower() for x in tk[i+L:]))].setdefault(' '.join(tk[i:i+L]),f)
groups={}
for k,spans in keys.items():
    if len(spans)<2: continue
    fs=frozenset(spans.values())
    if len(fs)<2: continue
    if fs not in groups or len(k[0])+len(k[1])>groups[fs][0]: groups[fs]=(len(k[0])+len(k[1]),spans)
def blank(q,name):
    pl=re.sub(r"^[A-Z][\w-]+ maker ","",q['plain']); pl=re.sub(r", the [^,]+ maker,","",pl)
    for cand in (q['subject'].strip(),name):
        i=pl.lower().find(cand.lower())
        if cand and i>=0: return (pl[:i]+'____'+pl[i+len(cand):]).strip()
    return None
pair=collections.defaultdict(list)
for fs,(n,spans) in groups.items():
    bydl=collections.defaultdict(dict)
    for name,f in spans.items():
        for q in evs[f]: bydl[q['deadline'] if q['kind']=='date' else 'x'][name]=q
    best=None
    for dl,mm in bydl.items():
        ms=sorted(mm.items(),key=lambda kv:-kv[1]['p'])
        if len(ms)>=2:
            for (na,a),(nb,b2) in itertools.combinations(ms,2): pair[tuple(sorted((na,nb)))].append((a if na<nb else b2,b2 if na<nb else a,dl))
        if len(ms)<3 or max(q['recog'] for _,q in ms)<2 or ms[0][1]['p']-ms[-1][1]['p']<0.05 or ms[0][1]['p']<0.08: continue
        mid=sum(1 for _,q in ms if 0.05<=q['p']<=0.95)
        sc=st.mean(sorted([q['Q'] for _,q in ms],reverse=True)[:3])*(0.6+0.1*min(len(ms),5))*(0.5+0.1*min(mid,5))
        bl=collections.Counter(blank(q,n) for n,q in ms if blank(q,n)); 
        if not bl: continue
        t,cnt=bl.most_common(1)[0]; ms=[(n,q) for n,q in ms if blank(q,n)==t]
        if len(ms)<3 or ms[0][1]['p']-ms[-1][1]['p']<0.05: continue
        if best is None or sc>best[0]: best=(sc,ms[:5],t)
    if best: add('peer',[q for _,q in best[1]],best[0],title=best[2],names=[n for n,_ in best[1]])
for (na,nb),lst in pair.items():
    seen=set(); rows=[]
    for a,b2,dl in sorted(lst,key=lambda x:-(x[0]['Q']+x[1]['Q'])*(1-abs(x[0]['p']+x[1]['p']-1)*0.3)):
        if a['fam'] in seen: continue
        seen.add(a['fam']); t=blank(a,na)
        if t: rows.append((t,a,b2))
    if len(rows)>=2 and min(rows[0][1]['recog'],rows[0][2]['recog'])>=2:
        rows=rows[:4]; mem=[x for r in rows for x in r[1:]]
        add('h2h',mem,st.mean(q['Q'] for q in mem)*(1+0.1*len(rows)),title=na+' vs '+nb,labels=[r[0].replace('____','').strip() for r in rows],names=[na,nb])
# ---------- funnels
STAGE=((1,r'\b(make|makes|reach|reaches|qualif\w+ for) the (\w+ )*playoffs?\b'),(2,r'\bwins? the (\w+ )*(division|AL East|AL West|AL Central|NL East|NL West|NL Central|(AFC|NFC) (North|South|East|West))\b'),(3,r'\bwins? the (\w+ )*(AFC|NFC|American League|National League|Eastern Conference|Western Conference)( Championship| pennant| title)?\b|\b(reach|reaches|plays? in|makes?) the (\w+ )*(Super Bowl|World Series|NBA Finals|Stanley Cup Final|national championship|championship game)'),(4,r'\bwins? the (\w+ )*(Super Bowl|World Series|NBA Finals|NBA championship|Stanley Cup|national championship|College Football Playoff)\b'))
def stage(q):
    best=None
    for k,rx in STAGE:
        if re.search(rx,q['plain'],re.I): best=k
    return best
bys=collections.defaultdict(dict)
for q in M:
    if q['domain']!='sports' or q['kind']!='named': continue
    s=stage(q)
    if s and (s not in bys[q['subj']] or q['vol']>bys[q['subj']][s]['vol']): bys[q['subj']][s]=q
for s,stg in bys.items():
    ks=sorted(stg)
    if len(ks)<3: continue
    mem=[stg[k] for k in ks]
    if any(mem[i+1]['p']>mem[i]['p']+0.02 for i in range(len(mem)-1)) or mem[0]['p']<0.25 or mem[-1]['p']<0.03: continue
    add('funnel',mem,max(q['rn'] for q in mem)*(0.5+mem[0]['p'])*(len(mem)/4),title=mem[0]['subject'])
# ---------- movers (Polymarket's one-week change)
mv=[q for q in E if q.get('chg') and q['chg'].get('w1') is not None and abs(q['chg']['w1'])>=0.08 and 3<=q['pp']<=97 and 0<=q['p']-q['chg']['w1']<=1 and anchored(q)]
THEMES={'':None,'Washington':('us_politics',),'Tech and business':('tech_ai','business','economy'),'The world':('world_politics','war_security'),'Culture and sport':('entertainment','celebrity','sports')}
for th,doms in THEMES.items():
    pool=sorted([q for q in mv if doms is None or q['domain'] in doms],key=lambda q:-abs(q['chg']['w1'])*q['Q']); out=[]
    for q in pool:
        if any(q['subj']==o['subj'] or q['fam']==o['fam'] for o in out): continue
        if doms is None and sum(1 for o in out if o['domain']==q['domain'])>=2: continue
        out.append(q)
        if len(out)==4: break
    if len(out)>=3: add('movers',sorted(out,key=lambda q:-abs(q['chg']['w1'])),st.mean(abs(q['chg']['w1'])*q['Q'] for q in out)*(1.1 if doms is None else 1),title='Biggest moves this week',tag=th or None,prev=[pct(q['p']-q['chg']['w1']) for q in sorted(out,key=lambda q:-abs(q['chg']['w1']))])
# ---------- coin-flip date
lad=collections.defaultdict(list)
for q in M:
    if q['kind']=='date' and q['dl'] and OK(q): lad[q['fam']].append(q)
for f,ms in lad.items():
    ms=sorted({q['deadline']:q for q in ms}.values(),key=lambda q:q['dl'])
    if len(ms)<3 or max(q['recog'] for q in ms)<2: continue
    ps=[q['p'] for q in ms]
    if any(ps[i+1]<ps[i]-0.03 for i in range(len(ps)-1)): continue
    k=next((i for i,p in enumerate(ps) if p>=0.5),None)
    if k is None or k==0 or ps[k-1]>0.45 or ps[k]>0.80: continue
    if len(ms)>5: 
        keep=sorted(set([0,k-1,k,len(ms)-1]+[min(len(ms)-1,k+1)])); ms2=[ms[i] for i in keep]; k=[m['id'] for m in ms2].index(ms[k]['id']); ms=ms2
    add('when',ms,max(q['Q'] for q in ms)*(1-abs(ms[k]['p']-0.55)),title=ms[k]['title'],flip=k)
bt=collections.defaultdict(list)
for c in C: bt[c['type']].append(c)
R={q['id']:q for q in M}
for t,l in bt.items():
    l.sort(key=lambda c:-c['score'])
    for r,c in enumerate(l): c['rank']=r+1
    print('=====',t,len(l))
    for c in l[:9]: print('  %.2f %s | %s | %s'%(c['score'],c['title'],c.get('tag') or '',' / '.join('%d %s'%(R[i]['pp'],(R[i]['plain'])[:38]) for i in c['ids'])), c.get('prev') or c.get('names') or c.get('labels') or '')
json.dump(C,open('cands3.json','w'))
````

## v3/select3.py

````python
import json,collections,re
M={q['id']:q for q in json.load(open('table.json'))}
C=json.load(open('cands3.json'))
def pct(p):
    x=round(p*1000); return (x+5)//10
def nsubj(s):
    s=(s or '').lower().strip(); s=re.sub(r"^(the|president|us|u\.s\.) ",'',s)
    return {'trump':'donald trump','fed':'federal reserve','the fed':'federal reserve'}.get(s,s)
key=lambda q:(q['src'],q['ev'],q['name'])
OLD={q['id']:q for q in json.load(open('../props_labeled.json'))}
gboards=[]; gclockfams=set()
for c in json.load(open('../final30.json')):
    ks={key(OLD[m['id']]) for m in c['members']}
    if c['type']=='board': gboards.append(ks)
    if c['type']=='clock': gclockfams|={(k[0],k[1]) for k in ks}
for c in json.load(open('../slate2/final.json'))['cards']:
    ks={key(OLD[i]) for i in c['ids']}
    if c['type']=='board': gboards.append(ks)
    if c['type']=='clock': gclockfams|={(k[0],k[1]) for k in ks}
WANT=collections.OrderedDict(board=8,band=4,deadheat=4,peer=3,h2h=1,funnel=3,movers=2,when=3)
fam=collections.Counter(); subj=collections.Counter(); chosen=[]; reserve=[]
def ok(c):
    qs=[M[i] for i in c['ids']]; t=c['type']
    if any(fam[q['fam']]>=3 for q in qs) or any(subj[s]>=4 for s in {nsubj(q['subject']) for q in qs}): return False
    same=[x for x in chosen if x['type']==t]
    if t=='board':
        ks={key(q) for q in qs}
        if any(len(ks&g)>=3 for g in gboards): return False
        if sum(1 for x in same if x['title']==c['title'])>=2 or any(len(set(x['ids'])&set(c['ids']))>=3 for x in same): return False
    if t=='when' and any((q['src'],q['ev']) in gclockfams for q in qs): return False
    if t in('band','movers') and any(len(set(x['ids'])&set(c['ids']))>=2 for x in same): return False
    if t in('deadheat','funnel','peer','when') and any({nsubj(M[i]['subject']) for i in x['ids']}&{nsubj(q['subject']) for q in qs} for x in same): return False
    if t=='deadheat' and sum(1 for x in same if M[x['ids'][0]]['domain']=='sports')>=3 and qs[0]['domain']=='sports': return False
    return True
def take(c):
    chosen.append(c)
    for f in {M[i]['fam'] for i in c['ids']}: fam[f]+=1
    for s in {nsubj(M[i]['subject']) for i in c['ids']}: subj[s]+=1
# types with the thinnest supply choose first, so the caps do not starve them
for t in ('h2h','peer','funnel','deadheat','when','band','board','movers'):
    n=0
    for c in sorted([c for c in C if c['type']==t],key=lambda c:c['rank']):
        if n<WANT[t] and ok(c): take(c); n+=1
        elif len([r for r in reserve if r['type']==t])<2: reserve.append(c)
    print(t,n,'of',WANT[t])
for k,c in enumerate(chosen+reserve): c['vid']='v%02d'%k; c['role']='slate' if k<len(chosen) else 'reserve'
json.dump(chosen+reserve,open('cand_slate3.json','w'),indent=1)
print(len(chosen),len(reserve))
allc=chosen+reserve; NB=3; per=-(-len(allc)//NB)
def block(c,rules=True):
    s=f"\n## {c['vid']} — type: {c['type']} — headline: {c['title']}"+(f" — tag: {c['tag']}" if c.get('tag') else '')+"\n"
    for k,i in enumerate(c['ids']):
        q=M[i]; extra=''
        if c['type']=='movers': extra=f" | shown as: was {c['prev'][k]}% a week ago"
        if c['type']=='when' and k==c['flip']: extra=' | shown as: the first date the market rates it likelier than not'
        if c['type']=='h2h': extra=f" | row: {c['labels'][k//2]} | side: {c['names'][k%2]}"
        if c['type'] in('peer','deadheat'): extra=f" | row name: {c['names'][k]}"
        s+=f"- id {i} | {pct(q['p'])}% | kind {q['kind']} | deadline {q['deadline']} | venue {'/'.join(q['venues'])}{extra}\n  SENTENCE: {q['plain']}\n  VENUE WORDING: {q['text'].strip()}\n"+(f"  RULES EXCERPT: {(q.get('rules') or '')[:300]}\n" if rules else '')
    return s
for b in range(NB):
    open(f'check_in_{b}.md','w').write(''.join(block(c) for c in allc[b*per:(b+1)*per]))
open('slatecheck_in.md','w').write('# Cards that may be shown together on one page\n'+''.join(block(c,False) for c in allc))
for c in chosen: print(c['vid'],c['type'],c['title'],'|',c.get('tag') or '','|',' / '.join('%d %s'%(pct(M[i]['p']),M[i]['plain'][:34]) for i in c['ids']))
````

## v3/final3.py

````python
import json,collections,re
M={q['id']:q for q in json.load(open('table.json'))}
C=json.load(open('cands3.json'))
def pct(p):
    x=round(p*1000); return (x+5)//10
def nsubj(s):
    s=(s or '').lower().strip(); s=re.sub(r"^(the|president|us|u\.s\.) ",'',s)
    return {'trump':'donald trump','fed':'federal reserve','the fed':'federal reserve'}.get(s,s)
key=lambda q:(q['src'],q['ev'],q['name'])
OLD={q['id']:q for q in json.load(open('../props_labeled.json'))}
gboards=[]; gclockfams=set()
for c in json.load(open('../final30.json')):
    ks={key(OLD[m['id']]) for m in c['members']}
    if c['type']=='board': gboards.append(ks)
    if c['type']=='clock': gclockfams|={(k[0],k[1]) for k in ks}
for c in json.load(open('../slate2/final.json'))['cards']:
    ks={key(OLD[i]) for i in c['ids']}
    if c['type']=='board': gboards.append(ks)
    if c['type']=='clock': gclockfams|={(k[0],k[1]) for k in ks}
prev={(c['type'],c['rank']):c['vid'] for c in json.load(open('cand_slate3.json'))}
BLOCKV={'v06','v20'}; BLOCKT={'t1043','t1298'}
C=[dict(c,vid=prev[(c['type'],c['rank'])]) for c in C if (c['type'],c['rank']) in prev and prev[(c['type'],c['rank'])] not in BLOCKV and not set(c['ids'])&BLOCKT]
WANT=collections.OrderedDict(board=8,band=4,deadheat=4,peer=3,h2h=1,funnel=3,movers=2,when=3)
fam=collections.Counter(); subj=collections.Counter(); chosen=[]; reserve=[]
def ok(c):
    qs=[M[i] for i in c['ids']]; t=c['type']
    if any(fam[q['fam']]>=3 for q in qs) or any(subj[s]>=4 for s in {nsubj(q['subject']) for q in qs}): return False
    same=[x for x in chosen if x['type']==t]
    if t=='board':
        ks={key(q) for q in qs}
        if any(len(ks&g)>=3 for g in gboards): return False
        if sum(1 for x in same if x['title']==c['title'])>=2 or any(len(set(x['ids'])&set(c['ids']))>=3 for x in same): return False
    if t=='when' and any((q['src'],q['ev']) in gclockfams for q in qs): return False
    if t in('band','movers') and any(len(set(x['ids'])&set(c['ids']))>=2 for x in same): return False
    if t in('deadheat','funnel','peer','when') and any({nsubj(M[i]['subject']) for i in x['ids']}&{nsubj(q['subject']) for q in qs} for x in same): return False
    if t=='deadheat' and sum(1 for x in same if M[x['ids'][0]]['domain']=='sports')>=3 and qs[0]['domain']=='sports': return False
    return True
def take(c):
    chosen.append(c)
    for f in {M[i]['fam'] for i in c['ids']}: fam[f]+=1
    for s in {nsubj(M[i]['subject']) for i in c['ids']}: subj[s]+=1
# types with the thinnest supply choose first, so the caps do not starve them
for t in ('h2h','peer','funnel','deadheat','when','band','board','movers'):
    n=0
    for c in sorted([c for c in C if c['type']==t],key=lambda c:c['rank']):
        if n<WANT[t] and ok(c): take(c); n+=1
        elif len([r for r in reserve if r['type']==t])<2: reserve.append(c)
    print(t,n,'of',WANT[t])

V={}
for k in range(3):
    for v in json.load(open(f'check_out_{k}.json')): V[v['vid']]=v
order=[];bt=collections.defaultdict(list)
import random; random.seed(5)
for c in chosen: bt[c['type']].append(c)
for t in bt: random.shuffle(bt[t])
while any(bt.values()):
    for t in ('board','band','deadheat','peer','funnel','when','movers','h2h'):
        if bt[t]: order.append(bt[t].pop(0))
for n,c in enumerate(order): c['n']=n+1; c['check']=V[c['vid']]
json.dump(order,open('final3.json','w'),indent=1)
print(len(order),collections.Counter(c['type'] for c in order))
for c in order: print(c['n'],c['vid'],c['type'],c['title'],c['check']['verdict'],c['check'].get('fixes'),c['check'].get('drop_members'))
````

## v3/page_data3.py

````python
import json,re
M={q['id']:q for q in json.load(open('table.json'))}
F=json.load(open('final3.json'))
MON='January|February|March|April|May|June|July|August|September|October|November|December'
DATE=re.compile(r'\s+((?:before|by)\s+(?:the end of\s+)?(?:(?:%s)\.?\s+)?(?:\d{1,2},\s+)?\d{4})$'%MON)
def split(s):
    m=DATE.search(s); return (s[:m.start()].rstrip(' ,'),m.group(1)) if m else (s,None)
def pct(p):
    x=round(p*1000); return (x+5)//10
KICK={'board':'Same deadline','band':'Same odds','deadheat':'Dead heat','peer':'Same question','h2h':'Head to head','funnel':'The path','movers':'Movers','when':'The tipping point'}
VEN={'K':'Kalshi','P':'Polymarket'}
out=[]
for c in F:
    t=c['type']; fx={x['id']:x['plain'].strip().rstrip('.') for x in (c['check'].get('fixes') or [])}
    ids=[i for i in c['ids'] if i not in set(c['check'].get('drop_members') or [])]
    d=dict(cid=c['vid'],type=t,kicker=KICK[t],n=c['n'],headline=c['title'],tag=c.get('tag'),notes=c['check'].get('reasons') or [])
    rows=[]
    for k,i in enumerate(ids):
        q=M[i]; s=fx.get(i,q['plain']); r=dict(text=s)
        if t=='board': r['text']=split(s)[0]
        if t in('peer','deadheat'): r['text']=re.sub(r'^The ','',c['names'][k])
        if t=='funnel':
            for pre in ('The '+c['title']+' ',c['title']+' '):
                if s.startswith(pre): r['text']=s[len(pre):]; r['cont']=True
        if t=='when': r['text']=split(s)[1] or q['name']
        if t=='movers': r['prev']=c['prev'][k]; r['delta']=pct(q['p'])-c['prev'][k]
        if t=='h2h': r['label']=c['labels'][k//2]; r['side']=k%2
        r.update(id=i,num='<1' if q['p']<0.005 else str(pct(q['p'])),p=round(q['p'],4),deadline=q['deadline'],venues=[VEN[v] for v in q['venues']],
                 pK=None if q.get('pK') is None else round(q['pK']*100,1),pP=None if q.get('pP') is None else round(q['pP']*100,1),raw=q['text'].strip(),plain=s,gotcha=q.get('gotcha') or '')
        rows.append(r)
    if t=='when':
        stem,dt=split(M[ids[c['flip']]]['plain']); d['headline']=stem; d['flip']=c['flip']; d['callout']='Likelier than not '+(dt or '')
    if t=='deadheat': d['rest']=c['rest']
    if t=='h2h': d['names']=c['names']
    d['rows']=rows; d['venues']=sorted({v for r in rows for v in r['venues']}); out.append(d)
json.dump(out,open('cards3.json','w'),indent=1)
for c in out: print(c['n'],c['type'],'|',c['headline'],'|',c.get('callout') or '','|',[r['text'][:40] for r in c['rows']][:5])
````

## v3/fitb.py

````python
import json,glob,collections,statistics as st,itertools
import numpy as np
P={q['id']:q for q in json.load(open('../props_labeled.json'))}
G1={"c00":"amazing","c01":"fine","c02":"amazing","c03":"fine","c04":"amazing","c05":"amazing","c08":"amazing","c09":"fine","c10":"amazing","c11":"amazing","c12":"no","c13":"amazing","c17":"amazing","c18":"fine","c19":"amazing","c20":"fine","c21":"amazing","c22":"amazing","c26":"no","c27":"fine","c28":"no","c29":"fine","c30":"no","c31":"no","c35":"fine","c36":"fine","c38":"fine","c39":"fine","c42":"fine","c43":"fine"}
rows=[]
for c in json.load(open('../final30.json')): rows.append((c['type'],[m['id'] for m in c['members']],G1[c['cid']],'v1'))
for c in json.load(open('../slate2/final.json'))['cards']:
    f='../grades2/grades/%s.json'%c['jid']
    try: d=json.load(open(f)); g=d.get('data',d).get('grade')
    except Exception: g=None
    if g: rows.append((c['type'],c['ids'],g,'v2'))
print(len(rows),collections.Counter((t,g) for t,_,g,_ in rows))
FUN=('entertainment','celebrity','sports'); POL=('us_politics','world_politics','war_security')
KEYS=['appeal','maxappeal','minappeal','recog','minrecog','weight','light','fun','pol','ndom','naivegap','mid','spread','n']
def feats(ms):
    ps=[m['p'] for m in ms]; nv=[m['naive']/100 for m in ms]
    return dict(appeal=st.mean(m['appeal'] for m in ms),maxappeal=max(m['appeal'] for m in ms),minappeal=min(m['appeal'] for m in ms),recog=st.mean(m['recog'] for m in ms),minrecog=min(m['recog'] for m in ms),
        weight=st.mean(m['weight'] for m in ms),light=sum(m['tone']=='light' for m in ms)/len(ms),fun=sum(m['domain'] in FUN for m in ms)/len(ms),pol=sum(m['domain'] in POL for m in ms)/len(ms),
        ndom=len(set(m['domain'] for m in ms)),naivegap=st.mean(abs(a-b) for a,b in zip(nv,ps)),mid=st.mean(1-2*abs(p-0.5) for p in ps),spread=max(ps)-min(ps),n=len(ms))
TY=['board','clock','yardstick','reversal','dossier']
def auc(pos,neg): return sum((1 if a>b else .5 if a==b else 0) for a in pos for b in neg)/(len(pos)*len(neg))
y=np.array([1.0 if g=='amazing' else 0.0 for _,_,g,_ in rows])
Xf=np.array([[feats([P[i] for i in ids])[k] for k in KEYS] for _,ids,_,_ in rows]); Xt=np.array([[1.0 if t==k else 0 for k in TY] for t,_,_,_ in rows])
def loo(X,a):
    out=[]
    for i in range(len(y)):
        m=np.ones(len(y),bool); m[i]=False; mu,sd=X[m].mean(0),X[m].std(0); sd[sd==0]=1
        A=np.c_[np.ones(m.sum()),(X[m]-mu)/sd]; R=a*np.eye(A.shape[1]); R[0,0]=0; w=np.linalg.solve(A.T@A+R,A.T@y[m]); out.append(float(np.r_[1,(X[i]-mu)/sd]@w))
    return np.array(out)
for name,X,a in (('type only',Xt,1.0),('labels only',Xf,10.0),('type + labels',np.c_[Xt,Xf],10.0)):
    pr=loo(X,a); print('%-14s held-out: amazing outranks other %.2f'%(name,auc(pr[y==1],pr[y==0])))
    tot=con=0
    for t in TY:
        idx=[i for i,r in enumerate(rows) if r[0]==t]
        for i,j in itertools.combinations(idx,2):
            if y[i]!=y[j]: tot+=1; con+=1 if (pr[i]-pr[j])*(y[i]-y[j])>0 else .5 if pr[i]==pr[j] else 0
    print('               within-type pairs %.1f of %d'%(con,tot))
# final model on labels within the three live types, residual to type
X=np.c_[Xt,Xf]; mu,sd=X.mean(0),X.std(0); sd[sd==0]=1; A=np.c_[np.ones(len(y)),(X-mu)/sd]; R=10*np.eye(A.shape[1]); R[0,0]=0; w=np.linalg.solve(A.T@A+R,A.T@y)
print('weights:',', '.join('%s %+.3f'%kv for kv in sorted(zip(TY+KEYS,w[1:]),key=lambda kv:-abs(kv[1]))))
json.dump(dict(keys=KEYS,mu=mu[len(TY):].tolist(),sd=sd[len(TY):].tolist(),w=w[1+len(TY):].tolist()),open('bscore.json','w'))
print('amazing rate by type:',{t:'%d/%d'%(sum(1 for r in rows if r[0]==t and r[2]=='amazing'),sum(1 for r in rows if r[0]==t)) for t in TY})
for v in ('v1','v2'):
  for t in ('board','clock','yardstick'):
    xs=[(feats([P[i] for i in ids]),g) for ty,ids,g,vv in rows if ty==t and vv==v]
    print(v,t,'amazing: recog %.2f appeal %.2f weight %.2f | other: recog %.2f appeal %.2f weight %.2f'%tuple([st.mean(f[k] for f,g in xs if g=='amazing') if any(g=='amazing' for f,g in xs) else 0 for k in('recog','appeal','weight')]+[st.mean(f[k] for f,g in xs if g!='amazing') if any(g!='amazing' for f,g in xs) else 0 for k in('recog','appeal','weight')]))
````

## v3/VERIFY3.md

````text
You are an independent checker of machine-generated "comparison cards" built from prediction-market questions. Correctness only. Do NOT judge whether a card is interesting and do not reorder anything. No web search or network; work only from the one input file named in your task and general knowledge. Open no other file. Keep your reasoning brief and write the output in two Write steps if it is long.

Each card has a type, a headline, and members. Each member shows: probability, kind, deadline, venue, the SENTENCE shown to readers, the VENUE WORDING and a RULES EXCERPT (may be cut off or empty), and sometimes how it is shown on the card.

Types:
- board: unrelated yes/no claims that share ONE deadline (the headline), listed by probability.
- band: unrelated claims shown together because they sit at about the same probability; the headline names that probability ("About 1 in 4").
- deadheat: the two leading outcomes of ONE question, nearly level. The headline is the question with a blank; each row is one outcome's name.
- peer: the SAME question asked about several different subjects. The headline is the question with a blank; rows are the subjects. The headline must be true of every row.
- h2h: two subjects compared on several questions. Each row label must be true of both sides.
- funnel: one team's nested stages (playoffs, division, conference, title), most likely first. Each later stage should be no likelier than an earlier one it depends on.
- movers: claims whose probability moved most in a week, shown "was X% a week ago".
- when: ONE question at several increasing deadlines; one rung is marked as the first date the market rates it likelier than not.

For every card check:
1. FAITHFULNESS of each SENTENCE to the venue wording and rules: subject, polarity, deadline, scope, nothing invented. If wrong or misleading write a corrected sentence (max 18 words).
2. STRUCTURE for the type as described above; for deadheat, that the two outcomes really are rivals for one prize and cannot both happen; for peer and h2h, that the headline or row label fits every member; for board, that deadlines match the headline within a few days; for band, nothing (just the sentences).
3. MEANING: the rules make a claim mean something a casual reader would not expect.
4. TONE: a member about a named person's death, health, pregnancy, crime, arrest or conviction, a disaster with casualties, or war and military strikes.
5. DUPLICATES within a card.

Write the output file as a JSON array, one object per card:
{"vid":"v03","verdict":"pass"|"fix"|"fail","reasons":["short"],"fixes":[{"id":"t0123","plain":"corrected sentence"}],"drop_members":["t0123"],"headline_fix":"corrected headline or empty"}
"fix" = valid once corrections are applied and/or listed members dropped (drop only on board, band, peer or movers cards, and only if at least 3 members remain). "fail" = should not be shown. Be strict on faithfulness and polarity; keep reasons short. Check the file is valid JSON, then reply with only a one-line count of pass / fix / fail.
````

## v3/CHECK3.md

````text
You are checking a SET of comparison cards that may be shown together on one page of a consumer app that shows market-implied probabilities. Correctness and consistency only. Do NOT judge whether cards are interesting, and do not rank them. No web search or network; use only the input file named in your task message and general knowledge. Open no other file.

Each card lists its claims with: claim id, probability, deadline, venue, the sentence shown to readers, and the venue's own wording.

Look ACROSS the whole set (and within cards) for three things:

1. CONTRADICTIONS. Two claims about the same underlying event whose numbers cannot both be right. Examples: the same event by a LATER deadline shown as LESS likely than by an earlier deadline; a broader claim shown as less likely than a narrower claim it contains; the same claim listed from two sources with numbers 2 or more points apart (a 1-point difference is rounding: ignore it). Report each pair once, with both claim ids.

2. DUPLICATE STORIES. Two cards OF THE SAME TYPE that a reader would experience as the same card twice: two clocks about the same negotiation or the same underlying event; two boards, bands or movers cards that share three or more claims; two dead heats, peer tables, funnels or "when" cards about the same question or subject. Report each pair once, giving the two card ids in the order they appear in the file. Cards of different types never count as duplicates of each other.

3. MISLEADING IN CONTEXT (use sparingly). A card that would mislead a reader because of something another card in the set shows, and that is not already covered by 1 or 2.

Write the output file as one JSON object:
{"contradictions":[{"ids":["q0001","q0002"],"why":"short reason"}],
 "duplicates":[{"first":"j001","second":"j002","why":"short reason"}],
 "misleading":[{"jid":"j003","why":"short reason"}]}
Use empty lists where you find nothing. Be thorough on 1 and 2: read every card and compare claims that concern the same person, organisation or event. Check the file parses as JSON, then reply with only the three counts.
````

## v4/gen4.py

````python
import json,re,collections,datetime,itertools,statistics as st
M=json.load(open('table.json')); R={q['id']:q for q in M}
def pct(p):
    x=round(p*1000); return (x+5)//10
def nsubj(s):
    s=(s or '').lower().strip(); s=re.sub(r"^(the|president|us|u\.s\.) ",'',s)
    return {'trump':'donald trump','fed':'federal reserve','the fed':'federal reserve'}.get(s,s)
TODAY=datetime.date(2026,10,6)
_h=json.load(open('histall.json')); HH=_h['h']; HT=_h['t']; THRS={'w1':.08,'m1':.15}; STAT=collections.Counter()
for q in M:
    q['pp']=pct(q['p']); q['rn']=q['recog']/3; q['an']=q['appeal']/3; q['wn']=q['weight']/3
    q['Q']=q['rn']*(0.5*q['an']+0.3*q['wn']+0.2); q['subj']=nsubj(q['subject'])
    try: q['days']=(datetime.date.fromisoformat(q['deadline'])-TODAY).days
    except Exception: q['days']=9999
    c=q.get('chg') or {}
    q['w1']=q['m1']=None; q['on']=q['p']-q['p_old']
    o=HH.get(q['id'])
    for f,d in (('w1',7),('m1',30)):
        v=c.get(f)
        if v is None or q.get('pP') is None: continue
        if abs(v)>=THRS[f]: STAT['claimed',f]+=1
        if not o or not o['h']: STAT['nohist',f]+=(abs(v)>=THRS[f]); continue
        h=o['h']
        if (HT-h[0]['t'])/86400<d+3: STAT['young',f]+=(abs(v)>=THRS[f]); continue
        hv=[x for x in h if x['t']<=HT-d*86400][-1]['p']; mv=q['pP']-hv
        if abs(v)>=THRS[f]:
            STAT['checked',f]+=1; STAT['off>5',f]+=abs(mv-v)>0.05; STAT['below_bar',f]+=abs(mv)<THRS[f]
        q[f]=mv
OKT=lambda q:q['tone'] in('light','neutral')
def fe(q): return q['domain']=='world_politics' and re.search(r'election|ballot|referendum',q['plain']+' '+q['text'],re.I) is not None
key=lambda q:(q['src'],q['ev'],q['name'])
seen_v3=set()
T3={q['id']:q for q in json.load(open('../v3/table.json'))}
for c in json.load(open('../v3/final3.json')):
    if c['type']=='movers': seen_v3|={key(T3[i]) for i in c['ids']}
E=[q for q in M if q['recog']>=2 and OKT(q) and not fe(q)]
C=[]
def add(t,mem,score,**kw): C.append(dict(type=t,ids=[m['id'] for m in mem],score=round(score,4),**kw))
def jac(a,b):
    A=set(re.findall(r'[a-z0-9]+',a['plain'].lower())); B=set(re.findall(r'[a-z0-9]+',b['plain'].lower())); return len(A&B)/max(1,len(A|B))
def valid(q,f):
    v=q[f]
    if v is None or not (0<=q['p']-v<=1) or not (2<=q['pp']<=98) or key(q) in seen_v3: return False
    if v<0 and q['kind']=='date' and q['days']<=30: return False      # a deadline running out is not news
    return True
THEMES={'':None,'Washington':('us_politics',),'Tech and business':('tech_ai','business','economy'),'The world':('world_politics','war_security'),'Culture and sport':('entertainment','celebrity','sports'),'Science and space':('science_space',)}
def movers(f,thr,title,spanword,sign=0,themes=THEMES):
    pool0=[q for q in E if valid(q,f) and abs(q[f])>=thr and (sign==0 or q[f]*sign>0)]
    for th,doms in themes.items():
        pool=sorted([q for q in pool0 if doms is None or q['domain'] in doms],key=lambda q:-abs(q[f])*q['Q']); out=[]
        for q in pool:
            if any(q['subj']==o['subj'] or q['fam']==o['fam'] or jac(q,o)>=0.6 for o in out): continue
            if doms is None and sum(1 for o in out if o['domain']==q['domain'])>=2: continue
            out.append(q)
            if len(out)==4: break
        if len(out)>=3:
            out=sorted(out,key=lambda q:-abs(q[f]))
            add('movers',out,st.mean(abs(q[f])*q['Q'] for q in out)*(1.1 if doms is None else 1),title=title,tag=th or None,prev=[pct(q['p']-q[f]) for q in out],span=spanword,field=f,sign=sign)
movers('w1',0.08,'Biggest moves this week','a week')
movers('w1',0.08,'Biggest climbers this week','a week',+1,{'':None})
movers('w1',0.08,'Biggest fallers this week','a week',-1,{'':None})
movers('m1',0.15,'Biggest moves this month','a month')
movers('on',0.04,'Biggest moves since Monday night','since Monday night',0,{'':None})
# ---------- the swing and new favorite: inside one question
fam=collections.defaultdict(list)
for q in M:
    if q['kind']=='named': fam[q['fam']].append(q)
def frame(plains):
    A=[p.split() for p in plains]; n=min(map(len,A)); i=0
    while i<n and len({a[i] for a in A})==1: i+=1
    j=0
    while j<n-i and len({a[-1-j] for a in A})==1: j+=1
    pre=' '.join(A[0][:i]); suf=' '.join(A[0][len(A[0])-j:]) if j else ''
    return (pre+' ____ '+suf).strip(), [' '.join(a[i:len(a)-j] if j else a[i:]) for a in A]
for f,ms in fam.items():
    ms=[q for q in ms if OKT(q) and not fe(q)]
    for fld,span in (('w1','a week'),('m1','a month')):
        xs=[q for q in ms if q[fld] is not None and 0<=q['p']-q[fld]<=1]
        if len(xs)<2 or max(q['recog'] for q in xs)<2: continue
        up=max(xs,key=lambda q:q[fld]); dn=min(xs,key=lambda q:q[fld])
        if up[fld]>=0.06 and dn[fld]<=-0.06 and psum<=1.15 if (psum:=sum(q['p'] for q in ms)) else False:
            t,names=frame([up['plain'],dn['plain']])
            if len(t.split())>=4 and all(names) and max(len(n.split()) for n in names)<=5:
                add('swing',[up,dn],(up[fld]-dn[fld])*max(up['Q'],dn['Q']),title=t,names=names,prev=[pct(up['p']-up[fld]),pct(dn['p']-dn[fld])],span=span,field=fld)
        now=max(xs,key=lambda q:q['p']); then=max(xs,key=lambda q:q['p']-q[fld])
        if now is not then and now['p']-then['p']>=0.03 and psum<=1.15:
            t,names=frame([now['plain'],then['plain']])
            if len(t.split())>=4 and all(names) and max(len(n.split()) for n in names)<=5:
                add('newfav',[now,then],(now[fld]-then[fld])*max(now['Q'],then['Q'])*1.2,title=t,names=names,prev=[pct(now['p']-now[fld]),pct(then['p']-then[fld])],span=span,field=fld)
# ---------- trading places: two unrelated famous claims that swapped order
for fld,span in (('w1','a week'),('m1','a month')):
    xs=[q for q in E if valid(q,fld) and q['recog']==3 and abs(q[fld])>=0.05]
    for a,b in itertools.permutations(xs,2):
        if a['fam']==b['fam'] or a['subj']==b['subj'] or a['domain']==b['domain']: continue
        pa,pb=a['p']-a[fld],b['p']-b[fld]
        if a[fld]>0 and b[fld]<0 and pa<pb-0.03 and a['p']>b['p']+0.03:
            add('trading',[a,b],min(a[fld],-b[fld])*a['Q']*b['Q']*(1.2 if fld=='w1' else 1),title='',prev=[pct(pa),pct(pb)],span=span,field=fld)
# ---------- the checklist: several outcomes of one question can all happen
for f,ms in fam.items():
    ms=sorted([q for q in ms if OKT(q) and not fe(q)],key=lambda q:-q['p'])
    if len(ms)<3 or sum(q['p'] for q in ms)<1.25 or max(q['recog'] for q in ms)<2: continue
    t,names=frame([q['plain'] for q in ms])
    if len(t.replace('____','').split())<2 or not all(names): continue
    add('checklist',ms[:5],st.mean(q['Q'] for q in ms[:5])*(1+0.1*len(ms[:5]))*(0.6+(ms[0]['p']-ms[-1]['p'])),title=t,names=names[:5])
# ---------- same odds
BANDS=((0.10,'About 1 in 10'),(0.15,'About 1 in 7'),(0.20,'About 1 in 5'),(0.40,'About 2 in 5'),(0.50,'A coin flip'),(0.60,'About 3 in 5'),(0.75,'About 3 in 4'),(0.80,'About 4 in 5'),(0.90,'About 9 in 10'))
shown=set()
for c in json.load(open('../v3/final3.json')):
    if c['type']=='band': shown|={key(T3[i]) for i in c['ids']}
for cc,name in BANDS:
    pool=sorted([q for q in E if abs(q['p']-cc)<=0.016 and q['appeal']>=2 and key(q) not in shown and (q['kind']!='date' or q['days']>20)],key=lambda q:-q['Q']); out=[]
    for q in pool:
        if any(q['subj']==o['subj'] or q['fam']==o['fam'] for o in out) or sum(1 for o in out if o['domain']==q['domain'])>=2: continue
        out.append(q)
        if len(out)==4: break
    if len(out)==4 and len({o['domain'] for o in out})>=3: add('band',sorted(out,key=lambda q:-q['p']),st.mean(q['Q'] for q in out),title=name)
bt=collections.defaultdict(list)
for c in C: bt[c['type']].append(c)
for t,l in bt.items():
    l.sort(key=lambda c:-c['score'])
    for r,c in enumerate(l): c['rank']=r+1
    print('=====',t,len(l))
    for c in l[:8]: print('  %.3f %s | %s | %s'%(c['score'],c['title'],c.get('tag') or '',' / '.join('%d %s'%(R[i]['pp'],R[i]['plain'][:34]) for i in c['ids'])),c.get('prev') or '',c.get('names') or '')
json.dump(C,open('cands4.json','w'))

print(dict(STAT))
````

## v4/histall.py

````python
import json,urllib.request,time,collections,concurrent.futures as cf
M=json.load(open('table.json'))
P=[json.loads(l) for l in open('../pull3/p.jsonl')]
bykey={}; bysig=collections.defaultdict(list)
for e in P:
    for m in e['m']:
        bykey[(str(e['id']),m[1])]=m[0]
        try: bysig[(round(m[3][0],4),m[12],m[13])].append(m[0])
        except Exception: pass
big=lambda q:q.get('chg') and q.get('pP') is not None and ((q['chg'].get('w1') is not None and abs(q['chg']['w1'])>=.04) or (q['chg'].get('m1') is not None and abs(q['chg']['m1'])>=.08))
fams={q['fam'] for q in M if big(q)}
want=[q for q in M if q.get('pP') is not None and q.get('chg') and (big(q) or q['fam'] in fams)]
mk={}
for q in want:
    mid=bykey.get((q['ev'],q['name'])) if q['src']=='P' else None
    if not mid:
        c=bysig.get((round(q['pP'],4),q['chg'].get('w1'),q['chg'].get('m1')),[])
        if len(c)==1: mid=c[0]
    if mid: mk[q['id']]=mid
print(len(want),len(mk))
try: out=json.load(open('histall.json'))
except Exception: out={}
def get(u):
    return json.loads(urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=30).read())
def one(it):
    i,mid=it
    for a in range(3):
        try:
            g=get(f'https://gamma-api.polymarket.com/markets/{mid}')
            tok=json.loads(g['clobTokenIds'])[0]
            h=get(f'https://clob.polymarket.com/prices-history?market={tok}&interval=max&fidelity=720')['history']
            return i,{'mid':mid,'h':h}
        except Exception as ex: err=str(ex)[:100]; time.sleep(1+a)
    return i,{'mid':mid,'err':err}
todo=[(i,m) for i,m in mk.items() if i not in out or 'err' in out[i]]
with cf.ThreadPoolExecutor(6) as ex:
    for i,o in ex.map(one,todo): out[i]=o
json.dump({'t':time.time(),'h':out},open('histall.json','w'))
print(len(out),sum('err' in o for o in out.values()))
````

## v4/select4.py

````python
import json,collections,re,sys,os,random
M={q['id']:q for q in json.load(open('table.json'))}
C=json.load(open('cands4.json'))
FINAL=len(sys.argv)>1
def pct(p):
    x=round(p*1000); return (x+5)//10
def nsubj(s):
    s=(s or '').lower().strip(); s=re.sub(r"^(the|president|us|u\.s\.) ",'',s); return {'trump':'donald trump'}.get(s,s)
BLOCKV=set(); BLOCKT=set(); DUP=set()
if FINAL:
    prev={(c['type'],c['rank']):c['vid'] for c in json.load(open('cand_slate4.json'))}
    V={}
    for k in range(2):
        for v in json.load(open(f'check_out_{k}.json')): V[v['vid']]=v
    BLOCKV={k for k,v in V.items() if v['verdict']=='fail'}
    sc=json.load(open('slatecheck_out.json'))
    for x in sc['contradictions']:
        ids=[i for i in x['ids'] if i in M]
        if len(ids)>=2: BLOCKT.add(sorted(ids,key=lambda i:(M[i]['vol'],M[i]['evvol']))[0])
    DUP={frozenset((x['first'],x['second'])) for x in sc['duplicates']}; BLOCKV|={x['jid'] for x in sc['misleading']}
    C=[dict(c,vid=prev[(c['type'],c['rank'])]) for c in C if (c['type'],c['rank']) in prev]
    C=[c for c in C if c['vid'] not in BLOCKV and not set(c['ids'])&BLOCKT]
    import time
    HN=[]
    def hprev(i,f):
        q=M[i]; o=H.get(i); d={'w1':7,'m1':30}[f]
        if not o or 'err' in o or not o['h']: return None,'no history'
        h=o['h']
        if (now-h[0]['t'])/86400<d+3: return None,'market younger than the span'
        hv=[x for x in h if x['t']<=now-d*86400][-1]['p']
        return q['p']-(q['pP']-hv),None
    C2=[]
    for c in C:
        drop=set(V[c['vid']].get('drop_members') or [])
        f=c.get('field'); keep=[]; prev=[]
        for k,i in enumerate(c['ids']):
            if i in drop: continue
            if False:
                pv,why=hprev(i,f)
                if pv is None: HN.append((c['vid'],i,why)); continue
                mv=M[i]['p']-pv; thr={'movers':{'w1':.08,'m1':.15}[f],'swing':.06}.get(c['type'],0)
                if abs(mv)<thr or (c.get('sign') and mv*c['sign']<=0): HN.append((c['vid'],i,'history move %.0f pts, under the bar'%(mv*100))); continue
                prev.append(pct(max(0,min(1,pv))))
            elif c.get('prev'): prev.append(c['prev'][k])
            keep.append(k)
        n=len(keep); t=c['type']
        if n<{'movers':3,'band':3,'checklist':3}.get(t,2): HN.append((c['vid'],'card','too few members left')); continue
        c=dict(c,ids=[c['ids'][k] for k in keep]); 
        if c.get('prev'): c['prev']=prev
        if c.get('names'): c['names']=[c['names'][k] for k in keep]
        if False:
            a,b=c['ids']
            if not (M[a]['p']>M[b]['p'] and prev[0]<prev[1]): HN.append((c['vid'],'card','order did not flip on history')); continue
        if False:
            a,b=c['ids']
            if (M[a]['p']-prev[0]/100)*(M[b]['p']-prev[1]/100)>=0: HN.append((c['vid'],'card','not opposite directions on history')); continue
        C2.append(c)
    C=C2; json.dump(HN,open('hist_drops.json','w'),indent=1); print('history gate:',HN)
def caps(i): return set(re.findall(r'\b[A-Z][a-z]+',M[i]['plain']))-{'The','A','An','US','United','States'}
for c in C:
    if c['type']=='movers':
        keep=[]
        for k,i in enumerate(c['ids']):
            if all(len(caps(i)&caps(c['ids'][j]))<3 for j in keep): keep.append(k)
        if len(keep)<len(c['ids']):
            c['ids']=[c['ids'][k] for k in keep]; c['prev']=[c['prev'][k] for k in keep]
C=[c for c in C if len(c['ids'])>=(3 if c['type']=='movers' else 2)]
WANT=collections.OrderedDict(movers=7,newfav=3,swing=3,trading=2,checklist=4,band=3)
MOVE=('movers','swing','newfav','trading')
fam=collections.Counter(); subj=collections.Counter(); used=set(); chosen=[]; reserve=[]
def ok(c):
    qs=[M[i] for i in c['ids']]; t=c['type']; same=[x for x in chosen if x['type']==t]
    if FINAL and any(frozenset((c['vid'],x['vid'])) in DUP for x in chosen): return False
    if any(fam[q['fam']]>=3 for q in qs) or any(subj[s]>=4 for s in {nsubj(q['subject']) for q in qs}): return False
    if t in MOVE and t!='movers' and set(c['ids'])&used: return False
    if t=='movers' and any(len(set(x['ids'])&set(c['ids']))>=2 for x in same): return False
    tk=lambda s_:set(re.findall(r'[a-z0-9]+',s_.lower()))-{'the','a','of','in','win','____'}
    if t in('swing','newfav') and any(x['type'] in('swing','newfav') and len(tk(x['title'])&tk(c['title']))>=0.5*min(len(tk(x['title'])),len(tk(c['title']))) for x in chosen): return False
    if t in('swing','newfav') and any(x['type'] in('swing','newfav') and (x['title']==c['title'] or {M[i]['fam'] for i in x['ids']}&{q['fam'] for q in qs}) for x in chosen): return False
    if t=='movers' and sum(1 for x in same if x['title']==c['title'])>=2: return False
    if t=='trading' and any({nsubj(M[i]['subject']) for i in x['ids']}&{nsubj(q['subject']) for q in qs} for x in same): return False
    if t=='checklist' and (qs[0]['domain']=='sports' and sum(1 for x in same if M[x['ids'][0]]['domain']=='sports')>=1): return False
    if t=='band' and any(len(set(x['ids'])&set(c['ids']))>=2 for x in same): return False
    return True
def take(c):
    chosen.append(c)
    for f in {M[i]['fam'] for i in c['ids']}: fam[f]+=1
    for s in {nsubj(M[i]['subject']) for i in c['ids']}: subj[s]+=1
    if c['type'] in MOVE and c['type']!='movers': used.update(c['ids'])
for t in WANT:
    n=0
    for c in sorted([c for c in C if c['type']==t],key=lambda c:c['rank']):
        if n<WANT[t] and ok(c): take(c); n+=1
        elif not FINAL and len([r for r in reserve if r['type']==t])<3: reserve.append(c)
    print(t,n,'of',WANT[t])
if not FINAL:
    allc=chosen+reserve
    for k,c in enumerate(allc): c['vid']='x%02d'%k
    json.dump(allc,open('cand_slate4.json','w'),indent=1)
    def block(c,rules=True):
        s=f"\n## {c['vid']} — type: {c['type']} — headline: {c['title'] or '(none)'}"+(f" — tag: {c['tag']}" if c.get('tag') else '')+"\n"
        for k,i in enumerate(c['ids']):
            q=M[i]; extra=''
            if c.get('prev'): extra+=f" | shown as: was {c['prev'][k]}% {'on Monday night' if c['span'].startswith('since') else c['span']+' ago'}"
            if c.get('names'): extra+=f" | row name: {c['names'][k]}"
            s+=f"- id {i} | {pct(q['p'])}% | kind {q['kind']} | deadline {q['deadline']} | venue {'/'.join(q['venues'])}{extra}\n  SENTENCE: {q['plain']}\n  VENUE WORDING: {q['text'].strip()}\n"+(f"  RULES EXCERPT: {(q.get('rules') or '')[:300]}\n" if rules else '')
        return s
    per=-(-len(allc)//2)
    for b in range(2): open(f'check_in_{b}.md','w').write(''.join(block(c) for c in allc[b*per:(b+1)*per]))
    open('slatecheck_in.md','w').write('# Cards that may be shown together on one page\n'+''.join(block(c,False) for c in allc))
    print(len(chosen),len(reserve))
else:
    random.seed(9); bt=collections.defaultdict(list)
    for c in chosen: bt[c['type']].append(c)
    for t in bt: random.shuffle(bt[t])
    order=[]
    while any(bt.values()):
        for t in ('movers','checklist','swing','band','newfav','movers','trading'):
            if bt[t]: order.append(bt[t].pop(0))
    for n,c in enumerate(order): c['n']=n+1; c['check']=V[c['vid']]
    json.dump(order,open('final4.json','w'),indent=1); print(len(order),collections.Counter(c['type'] for c in order))
for c in chosen: print(c['vid'],c['type'],c['title'],'|',c.get('tag') or '','|',' / '.join('%d %s'%(pct(M[i]['p']),M[i]['plain'][:30]) for i in c['ids']),c.get('prev') or '')
````

## v4/page_data4.py

````python
import json,re,collections
M={q['id']:q for q in json.load(open('table.json'))}
F=json.load(open('final4.json'))
def pct(p):
    x=round(p*1000); return (x+5)//10
def frame(plains):
    A=[p.split() for p in plains]; n=min(map(len,A)); i=0
    while i<n and len({a[i] for a in A})==1: i+=1
    j=0
    while j<n-i and len({a[-1-j] for a in A})==1: j+=1
    pre=' '.join(A[0][:i]); suf=' '.join(A[0][len(A[0])-j:]) if j else ''
    return (pre+' ____ '+suf).strip(), [' '.join(a[i:len(a)-j] if j else a[i:]) for a in A]
# claim-level wording fixes apply everywhere the claim appears (most common fix wins)
FX=collections.defaultdict(collections.Counter)
for k in range(2):
    for v in json.load(open(f'check_out_{k}.json')):
        for x in v.get('fixes') or []: FX[x['id']][x['plain'].strip().rstrip('.')]+=1
FX={i:c.most_common(1)[0][0] for i,c in FX.items()}
KICK={'movers':'Movers','swing':'The swing','newfav':'New favorite','trading':'Trading places','checklist':'Checklist','band':'Same odds'}
VEN={'K':'Kalshi','P':'Polymarket'}
SPAN={'a week':'in a week','a month':'in a month','since Monday night':'since Monday night'}
out=[]
for c in F:
    t=c['type']; ids=c['ids']; plains=[FX.get(i,M[i]['plain']) for i in ids]
    title=c['title']; names=c.get('names'); tag=c.get('tag')
    if t in('swing','newfav','checklist'):
        title,names=frame(plains)
    if t=='movers' and tag=='Washington' and any('Washington' in r for r in c['check'].get('reasons') or []): tag='US politics'
    d=dict(cid=c['vid'],type=t,kicker=KICK[t],n=c['n'],headline=title,tag=tag,notes=c['check'].get('reasons') or [],span=SPAN.get(c.get('span')),conn={'newfav':'has overtaken','trading':'is now likelier than'}.get(t))
    rows=[]
    for k,i in enumerate(ids):
        q=M[i]; s=plains[k]; r=dict(text=s)
        if names: r['text']=re.sub(r'^The ','',names[k])
        if c.get('prev'): r['prev']=c['prev'][k]; r['delta']=pct(q['p'])-c['prev'][k]
        r.update(id=i,num='<1' if q['p']<0.005 else str(pct(q['p'])),p=round(q['p'],4),deadline=q['deadline'],venues=[VEN[v] for v in q['venues']],
                 pK=None if q.get('pK') is None else round(q['pK']*100,1),pP=None if q.get('pP') is None else round(q['pP']*100,1),raw=q['text'].strip(),plain=s,gotcha=q.get('gotcha') or '')
        rows.append(r)
    d['rows']=rows; d['venues']=sorted({v for r in rows for v in r['venues']}); out.append(d)
json.dump(out,open('cards4.json','w'),indent=1)
for c in out: print(c['n'],c['type'],'|',c['headline'],'|',c['tag'] or '','|',[(r['text'][:38],r['num'],r.get('prev')) for r in c['rows']])
````

## v4/build4.py

````python
import json,re
s=open('../v3/comparison-slate-v3.html').read()
cards=json.load(open('cards4.json'))
s=re.sub(r'const CARDS\s*=\s*\[.*?\];\n',lambda m:'const CARDS = '+json.dumps(cards,ensure_ascii=False).replace('</','<\\/')+';\n',s,count=1,flags=re.S)
def rep(a,b,n=1):
    global s
    assert s.count(a)>=1,a[:60]
    s=s.replace(a,b) if n==0 else s.replace(a,b,n)
rep("const ASOF = Date.UTC(2026, 9, 6, 13, 28); // Tue Oct 6, 2026, 6:28am PT","const ASOF = Date.UTC(2026, 9, 6, 13, 46);")
rep("const TYPE_NAME = {board:'Same deadline', band:'Same odds', deadheat:'Dead heat', peer:'Same question', h2h:'Head to head', funnel:'The path', movers:'Movers', when:'The tipping point'};","const TYPE_NAME = {movers:'Movers', swing:'The swing', newfav:'New favorite', trading:'Trading places', checklist:'Checklist', band:'Same odds'};")
rep("'comparison-slate-v3'","'comparison-slate-v4'")
rep("<title>Comparison Slate v3</title>","<title>Comparison Slate v4</title>") if '<title>Comparison Slate v3</title>' in s else None
rep("<h1>Comparison Slate v3</h1>","<h1>Comparison Slate v4</h1>")
# mover rows: span-aware, optional connector between two rows
rep("""function moverRows(c){
  const box = el('div', 'rows');
  c.rows.forEach(r => {""","""function moverRows(c){
  const box = el('div', 'rows');
  c.rows.forEach((r, idx) => {
    if(idx === 1 && c.conn) box.append(el('div', 'conn', c.conn));""")
rep("(r.delta > 0 ? 'Up ' : 'Down ') + Math.abs(r.delta) + ' in a week, from ' + r.prev + '%'","(r.delta === 0 ? 'Unchanged ' : (r.delta > 0 ? 'Up ' : 'Down ') + Math.abs(r.delta) + ' ') + (c.span || 'in a week') + ', from ' + r.prev + '%'")
rep("if(c.type === 'board' || c.type === 'band' || c.type === 'peer' || c.type === 'funnel') card.append(rowList(c));","if(c.type === 'band' || c.type === 'checklist') card.append(rowList(c));")
rep("else if(c.type === 'movers') card.append(moverRows(c));","else if(c.type === 'movers' || c.type === 'swing' || c.type === 'newfav' || c.type === 'trading') card.append(moverRows(c));")
a=s.index('<header class="intro">'); b=s.index('</header>',a)
s=s[:a]+'''<header class="intro">
    <h1>Comparison Slate v4</h1>
    <p>Nineteen cards. More movers, cut five ways (this week, this month, since Monday night, by theme), and three card types you have not seen: the swing and the new favorite (two outcomes of one question moving in opposite directions), trading places (two unrelated claims that swapped order), and the checklist (outcomes of one question that can all happen). Same-odds groups are back for variety. Team paths are left out on purpose: you said they belong on team pages.</p>
    <p>Built by a program from this morning's Kalshi and Polymarket prices, each card checked against the venue's wording. None was picked by hand.</p>
    <ul class="key">
      <li><b>Amazing</b><span>You would forward it.</span></li>
      <li><b>Fine</b><span>You would not mind seeing it.</span></li>
      <li><b>No</b><span>It should not ship.</span></li>
    </ul>
    <div class="asof">Prices pulled Tue Oct 6, 2026, 6:45 to 6:48am PT. These are venue prices, not the Bain Luck blend. Week and month moves are computed from Polymarket's price history; "since Monday night" compares this pull with the one at 10:15pm PT on Mon Oct 5.</div>
  '''+s[b:]
rep("const order = ['board','band','deadheat','peer','h2h','funnel','when','movers'].filter(k => size[k]);","const order = Object.keys(TYPE_NAME).filter(k => size[k]); Object.keys(size).forEach(k => { if(order.indexOf(k) < 0) order.push(k); });")
rep("function setGrade(cid, grade){ G[cid] = Object.assign({}, G[cid], {grade}); paint(cid); summary(); queue(cid); }","function setGrade(cid, grade){ G[cid] = Object.assign({}, G[cid], {grade}); queue(cid); try{ paint(cid); summary(); }catch(e){} }")
rep("order.forEach(k => { const r = t[k]; tb.append(el('div', '', TYPE_NAME[k]));","order.forEach(k => { const r = t[k]; tb.append(el('div', '', TYPE_NAME[k] || k));")
open('comparison-slate-v4.html','w').write(s); print(len(s))
````

## v4/VERIFY4.md

````text
You are an independent checker of machine-generated "comparison cards" built from prediction-market questions. Correctness only. Do NOT judge whether a card is interesting and do not reorder anything. No web search or network; work only from the one input file named in your task and general knowledge. Open no other file. Keep your reasoning brief and write the output in two Write steps if it is long.

Each card has a type, a headline, and members. Each member shows: probability, kind, deadline, venue, the SENTENCE shown to readers, the VENUE WORDING and a RULES EXCERPT (may be cut off or empty), and sometimes how it is shown on the card.

Types:
- movers: claims whose probability moved most over a stated span; each row shows "was X% a week ago / a month ago / on Monday night". The headline may say "climbers" (every row must have risen) or "fallers" (every row must have fallen). A tag such as "Washington" or "The world" must fit every row.
- swing: TWO outcomes of ONE question; one rose and one fell over the span. The headline is the question with a blank (____); each "row name" fills the blank. The headline with each row name substituted must be a true, grammatical statement of that member's claim.
- newfav: TWO outcomes of ONE question where the one now leading was behind at the start of the span ("new favorite"). Same headline rule as swing. The two outcomes must be rivals for one prize (they cannot both happen), and the first must now be strictly ahead and have been strictly behind before.
- trading: TWO unrelated claims that swapped order over the span (the one now likelier was less likely before). No headline.
- checklist: several outcomes of ONE question that can ALL happen (not rivals), e.g. cast members of a film. Headline is the question with a blank; each row name fills it. Fail the card if the outcomes are in fact mutually exclusive, or if the headline does not fit every row.
- band: unrelated claims shown together because they sit at about the same probability; the headline names that probability ("About 1 in 7").

For every card check:
1. FAITHFULNESS of each SENTENCE to the venue wording and rules: subject, polarity, deadline, scope, nothing invented. If wrong or misleading write a corrected sentence (max 18 words).
2. STRUCTURE for the type as described above. For movers, also fail or drop a member whose fall is explained simply by its deadline running out, and flag a 'was' figure that looks impossible for the claim.
3. MEANING: the rules make a claim mean something a casual reader would not expect.
4. TONE: a member about a named person's death, health, pregnancy, crime, arrest or conviction, a disaster with casualties, or war and military strikes.
5. DUPLICATES within a card.

Write the output file as a JSON array, one object per card:
{"vid":"x03","verdict":"pass"|"fix"|"fail","reasons":["short"],"fixes":[{"id":"t0123","plain":"corrected sentence"}],"drop_members":["t0123"],"headline_fix":"corrected headline or empty","name_fixes":[{"id":"t0123","name":"corrected row name"}]}
"fix" = valid once corrections are applied and/or listed members dropped (drop only on movers, checklist or band cards, and only if at least 3 members remain). "fail" = should not be shown. Be strict on faithfulness and polarity; keep reasons short. Check the file is valid JSON, then reply with only a one-line count of pass / fix / fail.
````

## v4/CHECK4.md

````text
You are checking a SET of comparison cards that may be shown together on one page of a consumer app that shows market-implied probabilities. Correctness and consistency only. Do NOT judge whether cards are interesting, and do not rank them. No web search or network; use only the input file named in your task message and general knowledge. Open no other file.

Card types: movers (biggest moves over a span), swing and newfav (two outcomes of one question, one up one down), trading (two claims that swapped order), checklist (non-rival outcomes of one question), band (same probability).

Each card lists its claims with: claim id, probability, deadline, venue, the sentence shown to readers, and the venue's own wording.

Look ACROSS the whole set (and within cards) for three things:

1. CONTRADICTIONS. Two claims about the same underlying event whose numbers cannot both be right. Examples: the same event by a LATER deadline shown as LESS likely than by an earlier deadline; a broader claim shown as less likely than a narrower claim it contains; the same claim listed from two sources with numbers 2 or more points apart (a 1-point difference is rounding: ignore it). Report each pair once, with both claim ids.

2. DUPLICATE STORIES. Two cards OF THE SAME TYPE that a reader would experience as the same card twice: two movers cards or two bands that share three or more claims; two swing, newfav or checklist cards about the same question. A swing card and a newfav card about the same question also count as duplicates. Report each pair once, giving the two card ids in the order they appear in the file. Otherwise cards of different types never count as duplicates of each other.

3. MISLEADING IN CONTEXT (use sparingly). A card that would mislead a reader because of something another card in the set shows, and that is not already covered by 1 or 2.

Write the output file as one JSON object:
{"contradictions":[{"ids":["t0001","t0002"],"why":"short reason"}],
 "duplicates":[{"first":"x01","second":"x02","why":"short reason"}],
 "misleading":[{"jid":"x03","why":"short reason"}]}
Use empty lists where you find nothing. Be thorough on 1 and 2: read every card and compare claims that concern the same person, organisation or event. Check the file parses as JSON, then reply with only the three counts.
````
