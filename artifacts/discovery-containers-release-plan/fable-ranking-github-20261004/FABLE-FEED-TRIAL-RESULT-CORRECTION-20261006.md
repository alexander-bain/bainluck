# Correction to the feed trial result

Prepared by Fable for Alex, Tue 2026-10-06, 1:35pm PT. Root flagged two discrepancies in `FABLE-FEED-TRIAL-RESULT-20261006.md` and its bundle. Both are my errors and both are confirmed. The original files are left as preserved.

## 1. The correlations were wrong

I ranked values without handling ties. Grades have three levels and likes have two, so most values tie, and the result depended on the order of the rows. Corrected figures use Spearman rank correlation with average ranks for ties.

| Pair | I reported | Correct |
|---|---|---|
| Reading time and card length (characters) | +0.44 | +0.45 |
| Reading time and grade | minus 0.64 | minus 0.51 |
| Reading time and liked | minus 0.30 | minus 0.09 |
| Liked and grade | +0.47 | +0.45 |
| Card length and grade | minus 0.31 | minus 0.29 |

What changes: the negative link between reading time and grade is weaker than I said, and there is no meaningful link between reading time and liking. What does not change: reading time rose with card length, did not rise with interest, and three seen cards recorded zero seconds. The conclusion that this run's reading times should not be used stands.

Every count and median in the result file reproduces: 6 amazing, 17 fine, 3 no; liked 5 of 6, 9 of 17, 0 of 3; both shares on round-up cards; medians of 4, 13 and 22 seconds; 0 of 7 repeated-row cards amazing against 6 of 19.

## 2. The manifest entry for the CSV was wrong

The manifest recorded the CSV as empty. I computed the manifest before the CSV had been written to disk. The CSV itself is complete (2,549 bytes, 26 rows). `MANIFEST-corrected.json` was verified against the files after writing.

## 3. Added so this cannot recur

`recompute_stats.py` in the bundle recomputes every statistic quoted from the trial using only the exported CSV. From now on a result file quotes only numbers its bundled script prints, and each manifest is verified after it is written.
