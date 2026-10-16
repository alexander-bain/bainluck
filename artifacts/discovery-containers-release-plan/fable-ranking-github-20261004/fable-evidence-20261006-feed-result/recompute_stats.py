"""Recomputes every statistic quoted from the feed trial, from the exported CSV only.
Run: python3 -I recompute_stats.py   (in the folder holding feed-trial-signals-and-grades.csv)
Spearman rank correlation with average ranks for ties."""
import csv, math, statistics as st
R = list(csv.DictReader(open('feed-trial-signals-and-grades.csv')))
def avgrank(v):
    s = sorted(range(len(v)), key=lambda i: v[i]); r = [0.0] * len(v); i = 0
    while i < len(s):
        j = i
        while j + 1 < len(s) and v[s[j + 1]] == v[s[i]]: j += 1
        for k in range(i, j + 1): r[s[k]] = (i + j) / 2 + 1
        i = j + 1
    return r
def pearson(x, y):
    mx, my = st.mean(x), st.mean(y)
    return sum((a - mx) * (b - my) for a, b in zip(x, y)) / math.sqrt(sum((a - mx) ** 2 for a in x) * sum((b - my) ** 2 for b in y))
def spearman(x, y): return pearson(avgrank(x), avgrank(y))
dw = [float(r['reading_time_s']) for r in R]; ch = [int(r['chars']) for r in R]
lk = [int(r['liked']) for r in R]; sh = [int(r['would_share']) for r in R]
gr = [{'no': 0, 'fine': 1, 'amazing': 2}[r['grade']] for r in R]
rep = [int(r['rows_already_seen_earlier_in_feed']) > 0 for r in R]
print('cards', len(R), '| grades', {g: sum(r['grade'] == g for r in R) for g in ('amazing', 'fine', 'no')}, '| liked', sum(lk), '| would share', sum(sh), '| details opened on', sum(int(r['details_opens']) > 0 for r in R))
for g in ('amazing', 'fine', 'no'):
    idx = [i for i, r in enumerate(R) if r['grade'] == g]
    print(f"{g}: liked {sum(lk[i] for i in idx)} of {len(idx)}, shared {sum(sh[i] for i in idx)}, median reading time {st.median(dw[i] for i in idx):.2f}s, median chars {st.median(ch[i] for i in idx)}")
print(f"Spearman reading time vs chars  {spearman(dw, ch):+.2f}")
print(f"Spearman reading time vs grade  {spearman(dw, gr):+.2f}")
print(f"Spearman reading time vs liked  {spearman(dw, lk):+.2f}")
print(f"Spearman liked vs grade         {spearman(lk, gr):+.2f}")
print(f"Spearman chars vs grade         {spearman(ch, gr):+.2f}")
print('cards with a repeated row:', sum(rep), '| amazing among them', sum(1 for i, r in enumerate(R) if rep[i] and r['grade'] == 'amazing'), '| amazing among the rest', sum(1 for i, r in enumerate(R) if not rep[i] and r['grade'] == 'amazing'), 'of', len(R) - sum(rep))
print('zero reading time:', [(r['position'], r['card_type'], r['grade'], r['liked']) for r in R if float(r['reading_time_s']) == 0])
print('shared cards:', [(r['position'], r['card_type']) for r in R if r['would_share'] == '1'])
