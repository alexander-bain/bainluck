import json,time,urllib.request,sys,os
IDS=[109596,108620,112902,15203993,56933330,2279147,63849278,199050,270,5869749,11415154,109946,8430022,30635376,52755900,113799,112827,25923984,27594646,109358,62239632]
def get(u):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'fable-audit/1.0'}),timeout=40) as r:
                return r.status, r.read()
        except Exception as e:
            err=str(e); time.sleep(2)
    return 0, err.encode()
log=[]
for i in IDS:
    for name,u in [('detail',f'https://api.bainluck.com/api/futures/{i}?representation=verified_title')]+[(f'hist{h}',f'https://api.bainluck.com/api/futures/{i}/history?hours={h}') for h in (168,720,8760)]:
        fn=f'raw/{i}_{name}.json'
        t=time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())
        st,b=get(u)
        open(fn,'wb').write(b)
        log.append({'id':i,'what':name,'url':u,'status':st,'bytes':len(b),'fetched_utc':t})
        print(i,name,st,len(b),flush=True)
        time.sleep(0.4)
json.dump(log,open('raw/_fetchlog.json','w'),indent=1)
