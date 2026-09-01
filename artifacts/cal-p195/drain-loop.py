import asyncio,time
from app.tasks.precompute_calibration import _precompute_calibration_main as B
prev=-1
stalls=0
for i in range(1,25):
    t=time.time()
    try:
        s=asyncio.run(B()) or {}
    except Exception as e:
        print("ITER",i,int(time.time()-t),"RAISED",type(e).__name__,repr(e)[:180],flush=True)
        s={}
    p=s.get("phase_ledger") or {}
    g=p.get("stages") or {}
    b=int(g.get("staged:units_banked") or 0)
    print("ITER",i,int(time.time()-t),"terminal",p.get("terminal"),"banked",b,"of",g.get("staged:units_planned"),"this_beat",g.get("staged:units_this_beat"),"cancelled",g.get("staged:units_cancelled"),flush=True)
    if p.get("terminal") not in ("partial","cancelled",None):
        print("STOP terminal",p.get("terminal"),flush=True)
        break
    stalls=stalls+1 if b<=prev else 0
    prev=b
    if stalls>=2:
        print("STOP no progress in two iterations",flush=True)
        break
print("LOOP END",flush=True)
