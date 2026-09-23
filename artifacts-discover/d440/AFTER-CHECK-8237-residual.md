# #8237 residual — after-check, PRE-REGISTERED before the merge

Written 2026-09-23 ~11:05 AM PDT / 18:05Z, on the unmerged branch. Banked here so the
arms cannot be chosen once the answer is visible.

## Instrument

`python3 artifacts-discover/d438/crossread_8237.py --tag AFTER2`

Unchanged from the shipped one. It takes `--tag <T>` **and nothing else** — it
validates env before argparse, so an unknown flag prints no usage and runs the full
~7-minute pass, overwriting the banked json (d439 trap N-F).

Exit 0 = no split in the withheld class · 1 = splits found · **2 = UNPAYABLE (empty
window), which is not a pass.**

## Payable only after the RELEASE, not the merge

`heroku releases -a bainluck -n 1` must carry a sha containing this commit, AND
`gh api repos/alexander-bain/bainluck/compare/<sha>...<live>` must show live not
behind it. The gap was 23 minutes on the last ship (d439 trap N-D); paying earlier
measures the BEFORE and banks it as an AFTER.

Notice 48: **not heavy** (reason named in the PR), so no `bainluck-heavy` release is
owed and the ordinary main-app release is the whole gate.

## The five residual carriers — must REPAIR

Pre-registered from `crossread-AFTER.json` (the shipped ship's own output) plus a
server-side read of the stored rows at 17:20Z. `implied_div == priced_sum` to 4dp on
all five is the signature that identified the missing term.

| id | board | card | page | priced_sum | implied_div | page_wh | storedNULL |
|---|---|---|---|---|---|---|---|
| 128718 | MLS Cup Winner 2026 | .1998 | .2115 | 1.0585 | 1.0586 | 1 | 1 |
| 7435308 | MLB AL Comeback POY | .8225 | .8850 | 1.0760 | 1.0760 | 1 | 1 |
| 9962834 | NCAA FB 2027 Champion | .1378 | .1450 | 1.0525 | 1.0522 | 67 | 93 |
| 12764689 | DWTS S35 Winner | .2087 | .2700 | 1.2935 | 1.2937 | 37 | 37 |
| 16634605 | Next PM of Romania | .3839 | .4135 | 1.0770 | 1.0771 | 1 | 13 |

PASS = each of these five, **if still served**, reports `class: agree` with
`implied_div == 1.0000`.

🪤 The instrument recomputes class membership each run and these boards rotate, so
**"5 → 0" is not the test.** Three of the five were original #8237 members and two
were new entrants at the last run. The test is per-id on the ids that are still
served, plus the control arms below. A run in which none of the five is served is
**INCONCLUSIVE on the repair arm**, not a pass — say so rather than banking it.

## Control arms — must NOT move (this is what makes the repair falsifiable)

The fix widens `field_complete=False`, so the failure direction is a BLANKET
widening that takes boards it should not. Measured on `crossread-AFTER.json`
(375 served cards) before the change:

1. **`non-ME (by design)` = 16 splits.** Must stay 16 and stay split. The card
   divides an independent-binary field on purpose (gotcha #58) while the page keeps
   it raw under #199. The gate is scoped to `mutually_exclusive`; if this count
   moves, the scoping broke.
2. **`other (ME, nothing withheld)` = 10 splits.** Must stay split and must NOT
   become `agree` — these have `prices_withheld = 0`, so neither term of the page's
   union fires and this fix must be inert on them. A drop here means the gate is
   answering True without either term, i.e. the blanket widening.
3. **The 14 already-agreeing ME cards with withholding in band** (incl. `2417016`,
   `210`, `213`, `214`, `215`, `11371643`, `12337998`, `13785950`, `13785953`,
   `13785955`) must stay `agree`. They agree *because the shipped arms gate already
   fires on them*; the stale term must be a no-op there.
4. **`agree` total = 344.** Must not FALL. It may rise by up to 5 (the repairs).

## Accounting that must hold

Of 54 served ME cards with page withholding: 35 are out of band (already raw,
unchanged) and 19 are in band = **5 split + 14 agreeing**. That accounting is why
the blast radius is exactly the five and not a wider set. If the AFTER run shows a
different split of that 19, the sizing was wrong and the result needs re-reading
before anyone calls it a repair.

## LOOK

Discover at 390px on the released sha, read as a first-time reader (notice 4 / D48),
banked beside this file. A saved PNG is not an inspection — it is opened and judged.
