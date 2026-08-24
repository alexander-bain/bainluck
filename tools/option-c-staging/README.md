# Option C, as ruled — staging for `program/ux-108`

UX-P122 item C. Alex ruled **Option C** on UX-P120's three rendered mocks
(`tools/pooled-label-options/one-pager-2026-08-23.md`), with five amendments.
This directory holds the wording those amendments produce, **generated from the
live payload**, plus the functions that produce it.

```bash
tools/option-c-staging/run.sh              # curl production, then generate
tools/option-c-staging/run.sh --no-fetch   # generate from the saved payload
```

Outputs land under `/tmp/option-c-staging/` (never `/tmp/cal.json` — see below).
The dated copies committed here are `option-c-wording-YYYY-MM-DD.{md,json}`.

## The ruling, and where each amendment lives

| # | amendment | where it is implemented |
|---|---|---|
| 1 | pooled number KEPT (axis D, unchanged) | nothing recomputes; the generator reads axis D only to print it |
| 2 | the fold is NAMED | `describeCategoryPopulationOptionC` |
| 3 | members split published vs unpublished | same, `publishedMembers` / `unpublishedMembers` |
| 4 | FULL expandable member list. Refined by Alex 2026-08-24 to **cap-collapsed + FULL expansion** | the collapsed sentence caps inline names at `MEMBER_NAME_CAP`; the row expander renders `publishedMembers` / `unpublishedMembers` via uncapped `nameAll()`. The sweep asserts the pairing: a cap marker is legal **iff** the expansion carries the complete list |
| 5 | anchor sentence quotes the API's `by_category` figure | `anchorSentence` |
| 6 | section numerator = RENDERED pooled rows, never the normalized keys | `describeCategoryTablePopulationOptionC`, and the generator prints both populations side by side |

Amendment 4 was the one that collided with held work: `2108-disclosure-fix.patch`
introduced `MEMBER_NAME_CAP = 4`, which produced "and 50 more" for soccer, and
UX-P122 read the ruling as forbidding the cap outright. **Alex resolved it
2026-08-24: cap-collapsed, FULL expansion.** Both halves of the held patch
survive. What was wrong was never the cap — it was a cap with nowhere to finish
reading it. Applied on `program/ux-108` (UX-P125).

## The one judgment call — RULED

"Fold NAMED" and "FULL expandable list" pull apart for `soccer`, whose fold is 55
identifiers. Inline-all-55 is the wall of text the ruling's own tradeoff line
warned about. Alex's 2026-08-24 refinement:

- the **sentence** names the counts and the **published** members inline, capped
  at `MEMBER_NAME_CAP` with the tail collapsed to "and N more"
- the **expander** carries the full list of both sets, uncapped
- the **tooltip** (`title`) is counts only — never the member wall

The cap and the expansion are one mechanism, not two decisions: deleting the
expander re-creates #2108, and the sweep asserts that pairing rather than
trusting it.

## Every path is private, deliberately

`/tmp/cal.json` was the default of **three** tools in this repo — one frozen
baseline, two `curl -o` targets. UX-P121 watched that collision report
`calibration: FAIL — keys DISAPPEARED` on a payload that had not changed; the
tell was an mtime, not a value. This tool owns `/tmp/option-c-staging/` and every
path under it is env-overridable. `#2120` (UX-P125) made the other three
private too.

## What an implementation must not copy

The committed `.md` / `.json` are **evidence, stamped with the payload they came
from**, not a contract. The census moves without code:

- tennis went 3 → 4 published members overnight (08-22 → 08-23), because the
  payload gained a `by_category` row
- the prior one-pager regenerated **108 diff lines seven hours** after it was
  committed
- inside UX-P122's own session, soccer's published figure moved 3.02pp/117,692
  → 2.86pp/122,604

So: **derive the counts.** A test asserting "soccer folds 55" is #2108
reintroduced as a fixture — a census restated as a constant, which is the defect
the whole ruling exists to correct.

"Copy the functions" is no longer the instruction either: as of UX-P125 the sweep
**imports** `describeCategoryPopulation` / `describeCategoryTablePopulation` /
`nameAll` from `frontend/lib/calibrationPopulation.ts`. Two copies of a derived
sentence are two objects that can disagree, and only one of them ships.
