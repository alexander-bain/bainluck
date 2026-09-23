# #8237 — the card divides a field the page refuses to divide

discover/438 · 2026-09-23 · BEFORE measured on production **v4970 `9df3eaa0`** (the
release carrying #8224), 14:20–14:55Z.

## The mechanism is NOT the one the issue filed

#8237's body attributes the split to #8224's ceiling: "withheld legs pull the priced
sum under the ceiling, so the card divides and the page does not". That is a true
description of the card's arithmetic and a **wrong** account of the page's, and the
difference decides what gets built.

`normalize_display_probs` (`utils/outcome_display.py`) refuses a one-winner field for
**two independent reasons**:

| clause | issue | test |
|---|---|---|
| `field_complete=False` — any withheld member | **#7103** | `raw_sum` never reached |
| `raw_sum > _FIELD_SUM_MAX` (1.60) | #1200 | the ceiling #8224 copied |

#8224 copied the second and closed. The card never had the first.

**The ceiling cannot explain the specimens.** Both priced sums are BELOW 1.60:

```
52755536  26 legs, 7 withheld · priced sum 1.3800 · page .13    card .0942
2417016  225 legs,100 withheld · priced sum 1.2910 · page .1195  card .0926
```

A page obeying only the ceiling would have squeezed `52755536` to `.13/1.38 = .0942`
and **agreed with the card**. It prints `.13`. Only the withheld gate returns raw here,
so the withheld gate is the clause the card is missing.

## And #7632's drop is what puts the field in the band

Read from `db-query` on `52755536`:

```
stored     26 legs  sum 1.7900   <- ABOVE the ceiling; both surfaces already agree here
withheld    7 legs  sum 0.4100   <- #7632 removes these from the card
survivors  19 legs  sum 1.3800   <- INSIDE the squeeze band; the card divides by this
```

The page NULLS a refused leg in place and counts it (`prices_withheld`); the card
DROPS it. So the card reaches the divisor holding a field whose missing mass has
already been deleted from the evidence. **This is why the gate must be asked before
the drop**, and why "just sum the pre-drop list" is the wrong repair — it would agree
on this specimen by accident, still split on a field with few withheld legs and a low
sum, and reopen #7537's one-membership-one-divisor contract.

## BEFORE — the whole served class, not the two filed rows

`crossread_8237.py`, 7 categories, **376 futures cards cross-read** against their own
`/api/futures/{id}`. 28 split. Attributed by reading `mutually_exclusive` off the
payload rather than inferring it:

| class | n | expectation |
|---|---|---|
| **ME + withheld — #8237** | **13** | must be repaired |
| non-ME | 13 | unchanged **by design** (card divides gotcha #58's independent field; page keeps it raw under #199) |
| ME, nothing withheld | 2 | unchanged — a third residual class, see below |

Expected-repair ids (pre-registered in `expected-8237.json`):
`210 · 213 · 214 · 215 · 128718 · 2417016 · 7435308 · 11371643 · 12337998 · 12764689 ·
13785955 · 52755536 · 56775503`

🪤 **A sum-and-withheld heuristic overstated the class by one.** `20269743` (Bill
Cassidy) carries a withheld leg and a band sum but is **non-exclusive**, so it is the
by-design divergence and must NOT move. Both filed specimens were Kalshi and both
#8224 repairs Polymarket; venue was a coincidence then and the sum is a coincidence
now. The classifier reads the flag.

🪤 **The instrument's exit code was masked by a pipe.** The BEFORE run reported
"exit 0" with 28 splits on screen because the command ended `| tail -40` — that is
`tail`'s status (gotcha #124). Read the printed class line, or run it unpiped.

## Residual this fix does NOT close

Two ME cards split with nothing withheld: `231` (Miami FL, card .6238 / page .655) and
`15203997` (Harvard, card **.255** / page **.205** — the card prints HIGHER, implied
divisor 0.804 < 1, so it is not a squeeze at all). Different mechanism, left open and
named here rather than silently absorbed into this fix's numbers.

## After-check

```
source ~/.claude/.env && python3 artifacts-discover/d438/crossread_8237.py --tag AFTER
```
Payable only once a main-app release carries the fix. Exit 1 = the class is still
split · 0 = clear · 2 = UNPAYABLE (empty window — **not** a pass). Cards rotate out of
the feed within the hour, so the verdict is about the class; the pre-registered id
list in `expected-8237.json` says which rows to look for and which must not move.
