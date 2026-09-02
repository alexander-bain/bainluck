#!/usr/bin/env python3
"""Archive terminal cert blocks out of CERT-QUEUE.md and old rows out of CODEX-CERT-LOG.md.
Keeps: every non-terminal block, every block numbered >= KEEP_FROM, the last LOG_KEEP log rows.
Never run while CERT-QUEUE.md.claims.json is non-empty (a grader is mid-session).
Usage: archive-cert-queue.py [--write]   (default is a dry run)"""
import re,sys,os,json,datetime
H=os.path.expanduser('~/bainluck/.claude/handoff'); H=H if os.path.isdir(H) else os.path.expanduser('~/mnt/bainluck/.claude/handoff')
Q=f'{H}/CERT-QUEUE.md'; L=f'{H}/CODEX-CERT-LOG.md'
TERMINAL={'done','superseded','withdrawn','withdrawn-by-author','parked-mismatch'}
KEEP_FROM=755; LOG_KEEP=150; write='--write' in sys.argv
claims=json.load(open(Q+'.claims.json')) if os.path.exists(Q+'.claims.json') else {}
if claims and write: sys.exit('refusing: grader claims active: '+','.join(claims))
lines=open(Q).read().split('\n')
starts=[]
for i,l in enumerate(lines):
    if l.startswith('queue_id:'):
        s=i
        for k in range(1,4):
            if i-k>=0 and re.match(r'^#{1,3} .*CERT-\d+',lines[i-k]): s=i-k
        starts.append(s)
segs=[]; prev=0
for s in starts:
    if s<prev: continue
    segs.append((prev,s)); prev=s
segs.append((prev,len(lines)))
pre=lines[segs[0][0]:segs[0][1]]; blocks=segs[1:]
keep=[];arch=[]
for a,b in blocks:
    seg=lines[a:b]; st=''
    for l in seg:
        if l.startswith('status:'): st=l.split()[1] if len(l.split())>1 else ''; break
    m=re.search(r'CERT-(\d+)',' '.join(seg[:3])); n=int(m.group(1)) if m else 0
    (keep if (st not in TERMINAL or n>=KEEP_FROM) else arch).append(seg)
maxid=max([int(x) for x in re.findall(r'CERT-(\d+)',open(Q).read()+open(L).read())]+[0])
stamp=datetime.date.today().isoformat()
print(f'blocks: {len(blocks)} keep {len(keep)} archive {len(arch)}; preamble {len(pre)} lines; max id CERT-{maxid}')
print('kept:', [re.search(r"CERT-\d+",' '.join(s[:3])).group(0) if re.search(r"CERT-\d+",' '.join(s[:3])) else s[0][:40] for s in keep])
log=open(L).read().split('\n'); rows=[i for i,l in enumerate(log) if l.startswith('| CERT-')]
cut=rows[-LOG_KEEP] if len(rows)>LOG_KEEP else None
print(f'log rows {len(rows)}, archive {0 if cut is None else len([r for r in rows if r<cut])}')
if write:
    open(f'{H}/CERT-QUEUE-ARCHIVE-{stamp}.md','a').write('\n'.join(pre)+'\n'+'\n'.join('\n'.join(s) for s in arch)+'\n')
    head=[f'# CERT-QUEUE (active blocks only). Archived {stamp} by tools/archive-cert-queue.py -> CERT-QUEUE-ARCHIVE-{stamp}.md',
          f'id watermark: CERT-{maxid} (highest id ever issued; stage-cert.sh reads this)','',
          '---','']
    open(Q,'w').write('\n'.join(head)+'\n'.join('\n'.join(s) for s in keep)+'\n')
    if cut is not None:
        hdr_end=rows[0]
        open(f'{H}/CODEX-CERT-LOG-ARCHIVE-{stamp}.md','a').write('\n'.join(log[hdr_end:cut])+'\n')
        open(L,'w').write('\n'.join(log[:hdr_end])+f'\n| ARCHIVE | {stamp} | fable | rows before this line live in CODEX-CERT-LOG-ARCHIVE-{stamp}.md |\n'+'\n'.join(log[cut:]))
    print('written')
