# Feed-trial correction: verification receipt

The three supplied correction files are preserved byte-for-byte. All five entries in `MANIFEST-corrected.json` match the retained files by byte count and SHA-256, including the populated CSV and recomputation script. Original result and manifest remain unchanged as historical evidence; the correction supersedes their affected claims.

Inspected the script before execution: standard-library CSV reading and descriptive calculations, with average ranks for tied values; no network or writes. Ran `python3 -I recompute_stats.py` from the retained result-bundle directory. Exit status: 0.

All five corrected correlations reproduce at the stated two-decimal precision. Counts and medians reproduce; the exact no-grade dwell median is 22.25 seconds (22 seconds rounded in the narrative). The zero-dwell defect still invalidates this run's timing as a ranking signal. These descriptive correlations are not reader estimates or causal effects.

```text
cards 26 | grades {'amazing': 6, 'fine': 17, 'no': 3} | liked 14 | would share 2 | details opened on 4
amazing: liked 5 of 6, shared 1, median reading time 4.00s, median chars 108.0
fine: liked 9 of 17, shared 1, median reading time 13.00s, median chars 252
no: liked 0 of 3, shared 0, median reading time 22.25s, median chars 301
Spearman reading time vs chars  +0.45
Spearman reading time vs grade  -0.51
Spearman reading time vs liked  -0.09
Spearman liked vs grade         +0.45
Spearman chars vs grade         -0.29
cards with a repeated row: 7 | amazing among them 0 | amazing among the rest 6 of 19
zero reading time: [('6', 'swing', 'amazing', '1'), ('18', 'swing', 'fine', '1'), ('22', 'checklist', 'amazing', '0')]
shared cards: [('15', 'roundup'), ('19', 'roundup')]
```

The seven prior issue comments were checked for the superseded figures. None quoted −0.64 or −0.30 (or the other superseded coefficients). The existing #5105 comment is updated in place to record the confirmed tie-ranking correction, corrected values and verified replacement manifest; the other comments need no numerical correction. File 19's discrepancy report remains a historical record, resolved by this receipt and Fable's correction. No dispatch or owner, milestone, label, scope or gate changes.
