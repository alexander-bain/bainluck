import json, math, sys

def slope(bk):
    xs=[];ys=[];ns=[]
    for b,v in bk.items():
        n=v['n']
        if n==0: continue
        p=min(max(v['sp']/n,1e-4),1-1e-4)
        xs.append(math.log(p/(1-p))); ys.append(v['w']); ns.append(n)
    a,bq=0.0,1.0
    for _ in range(500):
        g=[0.0,0.0]; H=[[1e-9,0],[0,1e-9]]
        for x,w,n in zip(xs,ys,ns):
            mu=1/(1+math.exp(-(a+bq*x)))
            g[0]+=(w-n*mu); g[1]+=(w-n*mu)*x
            wt=n*mu*(1-mu)
            H[0][0]+=wt; H[0][1]+=wt*x; H[1][0]+=wt*x; H[1][1]+=wt*x*x
        det=H[0][0]*H[1][1]-H[0][1]*H[1][0]
        if abs(det)<1e-12: break
        da=( H[1][1]*g[0]-H[0][1]*g[1])/det
        db=(-H[1][0]*g[0]+H[0][0]*g[1])/det
        a+=da; bq+=db
        if abs(da)<1e-10 and abs(db)<1e-10: break
    return a,bq,sum(ns)

def ece(bk):
    tot=sum(v['n'] for v in bk.values())
    if not tot: return None
    return round(100*sum(abs(v['w']/v['n']-v['sp']/v['n'])*v['n'] for v in bk.values() if v['n'])/tot,2)

def recal(bk,a,b):
    """re-bucket rows using the corrected price. bucket-grain: apply to the bucket mean."""
    out={}
    for k,v in bk.items():
        n=v['n']
        if not n: continue
        p=min(max(v['sp']/n,1e-4),1-1e-4)
        q=1/(1+math.exp(-(a+b*math.log(p/(1-p)))))
        nb=str(min(int(q*10),9))
        d=out.setdefault(nb,{'n':0,'w':0,'sp':0.0})
        d['n']+=n; d['w']+=v['w']; d['sp']+=q*n
    return out

for path,dim in ((sys.argv[1],sys.argv[2]),):
    d=json.load(open(path))
    print(f"=== {dim} ===")
    for arm,bk in sorted(d['by_key'].items(), key=lambda kv:-sum(v['n'] for v in kv[1].values())):
        a,b,n=slope(bk)
        if n<50: continue
        print(f"  {arm:<28} n={n:<5} ECE={ece(bk):<6} logit-slope b={b:.3f}  a={a:+.3f}")
    h=d.get('halves')
    if h and 'OLD' in h and 'NEW' in h:
        print("  -- holdout recalibration: FIT ON OLD, APPLY TO NEW --")
        for arm in d['by_key']:
            o=h['OLD'].get(arm); nw=h['NEW'].get(arm)
            if not o or not nw: continue
            if sum(v['n'] for v in nw.values())<50: continue
            a,b,_=slope(o)
            print(f"  {arm:<28} NEW ECE {ece(nw)} -> {ece(recal(nw,a,b))}   (a={a:+.3f} b={b:.3f} fitted on OLD)")
