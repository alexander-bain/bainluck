import subprocess, hashlib, pathlib
F=pathlib.Path('/tmp/wt-d10346/frontend')
LIB=F/'lib/eventHighlightsPreview.ts'; CMP=F/'components/event/EventHighlightsPreview.tsx'
M=[
 ('M1-when-not-Pregame', LIB, 'when: "Pregame",\n        question: "10+ strikeouts"', 'when: "Before" as "Pregame",\n        question: "10+ strikeouts"'),
 ('M2-min-before-first-pitch', LIB, 'detail: "6⅓ scoreless innings, two hits allowed",\n      visual', 'detail: "6⅓ scoreless innings, two hits allowed",\n      headlineNote: "23 min before first pitch",\n      visual'),
 ('M3-final-out', CMP, '{formatRecordedAt(quote.observedAt)}\n', '{formatRecordedAt(quote.observedAt)}{quote.when === "After Game 1" ? " (after the final out)" : ""}\n'),
 ('M4-present-tense-lead', LIB, 'detail: "Yankees led the best-of-three 1–0 after Game 1"', 'detail: "Best-of-three Wild Card Series, Yankees lead 1–0"'),
 ('M5-bid-asking-caveat', LIB, 'whole: true,\n', 'whole: true,\n        caveat: "No one was bidding; 2% was the asking price",\n'),
 ('M6-rice-raw-row-not-admitted', LIB, 'probability: 0.0155,\n        whole: true,\n        observedAt: "2026-09-29T23:50:23.519Z"', 'probability: 0.02,\n        whole: true,\n        observedAt: "2026-09-29T23:52:03.774Z"'),
 ('M7-schlittler-not-served', LIB, 'question: "10+ strikeouts",\n        probability: 0.185', 'question: "10+ strikeouts",\n        probability: 0.19'),
 ('M8-grey-panel-back', CMP, '<div className="flex flex-col gap-2" data-visual', '<div className="flex flex-col gap-2 rounded-lg bg-surface-elevated p-3" data-visual'),
 ('M9-count-visual-dropped', CMP, '{visual && <CountMarks visual={visual} />}', '{null}'),
 ('M10-whole-ignored', LIB, 'if (whole) return `${Math.round(probability * 100)}%`;', ''),
 ('M11-recorded-time-dropped', CMP, '{formatRecordedAt(quote.observedAt)}\n', '{quote.when}\n'),
]
res=[]
for name,f,a,b in M:
    orig=f.read_bytes(); h=hashlib.sha256(orig).hexdigest(); s=orig.decode()
    assert s.count(a)==1,(name,s.count(a))
    f.write_text(s.replace(a,b))
    out=pathlib.Path(f'/tmp/d10346/mut-r1/{name}.txt')
    with open(out,'w') as o: rc=subprocess.call(['npx','jest','--testPathPatterns=eventHighlightsPreview10346'],cwd=F,stdout=o,stderr=subprocess.STDOUT)
    f.write_bytes(orig); assert hashlib.sha256(f.read_bytes()).hexdigest()==h
    fails=[l.strip() for l in out.read_text().splitlines() if l.strip().startswith('✕')]
    res.append(f'{name}: EXIT {rc} red={len(fails)} {fails[:3]}'); print(res[-1], flush=True)
pathlib.Path('/tmp/d10346/mut-r1/SUMMARY.txt').write_text('\n'.join(res)+'\n')
