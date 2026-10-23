import subprocess, hashlib, pathlib
F=pathlib.Path('/tmp/wt-d10346/frontend')
LIB=F/'lib/eventHighlightsPreview.ts'; CMP=F/'components/event/EventHighlightsPreview.tsx'
M=[
 # carried R1 mutants, retargeted where the target moved
 ('M1-when-not-Pregame', LIB, 'when: "Pregame",\n        question: "10+ strikeouts"', 'when: "Before" as "Pregame",\n        question: "10+ strikeouts"'),
 ('M2-min-before-first-pitch', LIB, 'detail: "6⅓ scoreless innings, two hits allowed",\n      visual', 'detail: "6⅓ scoreless innings, two hits allowed",\n      headlineNote: "23 min before first pitch",\n      visual'),
 ('M3-final-out', CMP, '{formatRecordedAt(iso)}\n', '{formatRecordedAt(iso)} (after the final out)\n'),
 ('M4-present-tense-lead', LIB, 'detail: "Yankees led 1–0 after Game 1"', 'detail: "Yankees lead 1–0"'),
 ('M5-bid-asking-caveat', LIB, 'whole: true,\n', 'whole: true,\n        caveat: "No one was bidding; 2% was the asking price",\n'),
 ('M6-rice-raw-row-not-admitted', LIB, 'probability: 0.0155,\n        whole: true,\n        observedAt: "2026-09-29T23:50:23.519Z"', 'probability: 0.02,\n        whole: true,\n        observedAt: "2026-09-29T23:52:03.774Z"'),
 ('M7-schlittler-not-served', LIB, 'question: "10+ strikeouts",\n        probability: 0.185', 'question: "10+ strikeouts",\n        probability: 0.19'),
 ('M8-grey-panel-back', CMP, '<div className="flex flex-col gap-2 [container-type:inline-size]" data-visual', '<div className="flex flex-col gap-2 rounded-lg bg-surface-elevated p-3 [container-type:inline-size]" data-visual'),
 ('M9-count-visual-dropped', CMP, '{visual && <CountMarks visual={visual} />}', '{null}'),
 ('M10-whole-ignored', LIB, 'if (whole) return `${Math.round(probability * 100)}%`;', ''),
 ('M11-recorded-time-dropped', CMP, '{formatRecordedAt(iso)}\n', '{"recorded"}\n'),
 # this delta
 ('C1-series-leads-with-score', LIB, 'headline: "Series win chance rose"', 'headline: "Yankees won Game 1, 9–0"'),
 ('C2-provider-row-on-closed-card', CMP, '{pct}</span>\n    </div>\n  );', '{pct}</span>\n      <span className="text-[11px]">{sourceMark(quote)} · <Recorded iso={quote.observedAt} /></span>\n    </div>\n  );'),
 ('C3-sources-only-when-combined', CMP, 'function Sources({ quotes, note }: { quotes: readonly HighlightQuote[]; note?: string }) {\n', 'function Sources({ quotes, note }: { quotes: readonly HighlightQuote[]; note?: string }) {\n  if (quotes.every((q) => q.contributors.length < 2)) return null;\n'),
 ('C4-ballpark-ET-forced', LIB, 'new Intl.DateTimeFormat("en-US", { timeZoneName: "short" })', 'new Intl.DateTimeFormat("en-US", { timeZoneName: "short", timeZone: "America/New_York" })'),
 ('C5-series-day-cue-dropped', CMP, '        {after && (\n', '        {false && after && (\n'),
 ('C6-phone-rail-items-start', CMP, '<ol className="-mx-4 mt-3 flex items-stretch', '<ol className="-mx-4 mt-3 flex items-start'),
 ('C7-mark-label-truncated', CMP, 'mt-1 break-words text-[11px]', 'mt-1 truncate text-[11px]'),
 ('C8-grand-slam-repeated', LIB, 'headline: "Rice homered twice",', 'headline: "Rice homered twice, the second a grand slam",'),
 ('C9-game-2-in-fold', LIB, 'sourceNote: "Game 1 of the best-of-three: Yankees 9, Red Sox 0",', 'sourceNote: "Game 1 of the best-of-three: Yankees 9, Red Sox 0; Game 2 next",'),
 ('C10-fold-not-at-foot', CMP, '<details className="mt-auto text-[11px]', '<details className="text-[11px]'),
 ('C11-borrowed-clock', LIB, 'probability: 0.011, observedAt: "2026-09-29T23:50:22.756Z"', 'probability: 0.011, observedAt: "2026-09-29T23:50:23.519Z"'),
 ('C12-contributors-hidden', CMP, '                {q.contributors.map((c) => (', '                {q.contributors.slice(0, 1).map((c) => ('),
 ('C13-per-row-fixed-grid', CMP, '<div data-when={quote.when} className="contents">', '<div data-when={quote.when} className="grid grid-cols-[5.5rem_minmax(0,1fr)_3.75rem] items-center gap-2">'),
 ('C14-bar-may-collapse', CMP, 'grid-cols-[minmax(min-content,5.5rem)_minmax(2.5rem,1fr)_auto]', 'grid-cols-[minmax(min-content,5.5rem)_minmax(0,1fr)_auto]'),
 ('C15-label-splits-words', CMP, 'grid-cols-[minmax(min-content,5.5rem)_', 'grid-cols-[minmax(0,5.5rem)_'),
 ('C16-no-size-container', CMP, ' [container-type:inline-size]"', '"'),
 ('C17-label-never-takes-own-line', CMP, ' [@container(max-width:14rem)]:col-span-2', ''),
]
res=[]
for name,f,a,b in M:
    orig=f.read_bytes(); h=hashlib.sha256(orig).hexdigest(); s=orig.decode()
    assert s.count(a)==1,(name,s.count(a))
    f.write_text(s.replace(a,b))
    out=pathlib.Path(f'/tmp/d10346/mut-c1/{name}.txt')
    with open(out,'w') as o: rc=subprocess.call(['npx','jest','--testPathPatterns=eventHighlightsPreview10346'],cwd=F,stdout=o,stderr=subprocess.STDOUT)
    f.write_bytes(orig); assert hashlib.sha256(f.read_bytes()).hexdigest()==h
    txt=out.read_text()
    fails=[l.strip() for l in txt.splitlines() if l.strip().startswith('●') and '›' in l]
    tl=[l.strip() for l in txt.splitlines() if l.strip().startswith('Tests:')]
    compile_err='error TS' in txt or 'SyntaxError' in txt
    res.append(f'{name}: EXIT {rc} · {tl[0] if tl else "?"} · compile_error={compile_err} · {"; ".join(dict.fromkeys(fails))}'); print(res[-1], flush=True)
pathlib.Path('/tmp/d10346/mut-c1/SUMMARY.txt').write_text('\n'.join(res)+'\n')
