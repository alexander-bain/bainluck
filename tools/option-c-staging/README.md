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
| 4 | FULL expandable member list — **a capped list is not checkable** | `nameAll()` has no `cap` parameter, and the generator asserts the output never matches `/and \d+ more/` |
| 5 | anchor sentence quotes the API's `by_category` figure | `anchorSentence` |
| 6 | section numerator = RENDERED pooled rows, never the normalized keys | `describeCategoryTablePopulationOptionC`, and the generator prints both populations side by side |

Amendment 4 is the one that supersedes held work: `2108-disclosure-fix.patch`
introduced `MEMBER_NAME_CAP = 4`, which produced "and 50 more" for soccer. That
cap is **deleted** by the ruling, not tuned. Whoever applies the patch on
`program/ux-108` must reconcile the two — the patch's published/unpublished
split survives, its cap does not.

## The one judgment call

"Fold NAMED" and "FULL expandable list" pull apart for `soccer`, whose fold is 55
identifiers. Inline-all-55 is the wall of text the ruling's own tradeoff line
warned about; capping is forbidden. Resolved as:

- the **sentence** names the counts and the **published** members inline — the
  few a reader can actually look up (at most 7 today)
- the **expander** carries the full list of both sets, uncapped

Both forms are emitted (`sentence` and `sentenceCountsOnly`) so flipping the
choice is one line rather than a rewrite.

## Every path is private, deliberately

`/tmp/cal.json` is the default of **three** tools in this repo — one frozen
baseline, two `curl -o` targets. UX-P121 watched that collision report
`calibration: FAIL — keys DISAPPEARED` on a payload that had not changed; the
tell was an mtime, not a value. This tool owns `/tmp/option-c-staging/` and every
path under it is env-overridable. `#2120` owns making the *other* three safe.

## What an implementation must not copy

The committed `.md` / `.json` are **evidence, stamped with the payload they came
from**, not a contract. The census moves without code:

- tennis went 3 → 4 published members overnight (08-22 → 08-23), because the
  payload gained a `by_category` row
- the prior one-pager regenerated **108 diff lines seven hours** after it was
  committed
- inside UX-P122's own session, soccer's published figure moved 3.02pp/117,692
  → 2.86pp/122,604

So: **copy the functions, derive the counts.** A test asserting "soccer folds 55"
is #2108 reintroduced as a fixture — a census restated as a constant, which is
the defect the whole ruling exists to correct.
