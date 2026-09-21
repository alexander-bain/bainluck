# ux/1408 — #7716: a pasted link stops printing a number the page does not

pillar: **TRUTH** · ship: **the sentence and the picture under a pasted link print the number
the page prints**

## The defect, measured on production 2026-09-21 (both ends live in the same minute)

| surface | before |
|---|---|
| `/sport/baseball/mlb/team/baltimore-orioles-mlb` `og:description` | `Baltimore Orioles: 0% to win the championship.` (served `0.004`; the page reads `<1%` since #7710) |
| same route `og:image` | a 92px `0%` beside a bar drawn at its 3% floor — `BEFORE-orioles-unfurl.png` |
| `/futures/400` `og:title` | `Barcelona 100% - La Liga Winner` (served `0.995`, `status: open`) |
| same route `og:image` | a 96px `100%` above a bar clamped to 97 — `BEFORE-futures400-unfurl.png` |

Both BEFORE shots are production reads (`og:image` URLs from the live `<head>`), not local renders.

## Reach — single db-query over open markets, 2026-09-21

| band | outcomes | of which rank-1 leader (the row a share NAMES) |
|---|---:|---:|
| `(0, 0.005)` → printed `0%`, now `<1%` | 6,799 | 120 |
| `[0.995, 1)` → printed `100%`, now `>99%` | 1,904 | 891 |
| the four #3867 wire values (0.145 / 0.285 / 0.565 / 0.575) | 1,715 | 388 |
| exact `0` → unchanged (`null`, no number in the sentence) | 4,178 | 19 |
| exact `1` → unchanged (`100%`) | 1,655 | 1,217 |

## The change — 7 lines of code

`formatShareProbability` was a bare `Math.round(p * 100)`: a second, older copy of two rules the
site already owns one import away. It now defers to `formatProbabilityPercent`, which composes
UX-P046's boundary rule with #3867's rounding contract. `pairedDuel` in `eventConceptShareMeta`
built its percent by hand — the one share path the shared formatter cannot reach — so it takes the
same rule through the `rendered` option, which overrides the integer and leaves the rule on the
probability.

Precedent, not a new judgement: #6849 already took this exact trade for the two-competitor case —
*"leaving the formatter's here would trade a sum defect for an unfurl that disagrees with the page
it depicts."* This is that sentence applied to the whole helper.

**What deliberately did not move:** exact `0` still returns `null` (load-bearing — it is how
`pricedCompetitors`, `boardLeader` and `futuresBoardPrice` drop the number rather than print a
zero), exact `1` still prints `100%`, and the `PRINTS_AS_CERTAIN` withholding on tournaments and
event concepts is byte-identical.

## AFTER

`AFTER-orioles-unfurl.png` — a real 1200×630 render through the real route, same framing as the
BEFORE: `<1%` in 92px, right-aligned to the same padding edge, now agreeing with the bar beside it.
Rendered against a local stub serving the captured production payload, because node cannot egress
to `api.bainluck.com` from this sandbox.

**The `/futures/400` AFTER picture is not payable here.** That route's card draws the 🍀 through
Satori's `loadAdditionalAsset`, which fetches the glyph from a third-party CDN at render time; this
sandbox cannot reach it, so the route answers HTTP 000 locally. That is the limitation `UnfurlCard`'s
own docstring records, it fails identically without this change, and it is why the BEFORE for that
card is a production read. Its AFTER is an after-merge check. The rendered element tree IS asserted
(`shareBoundaryPercent7716.test.tsx` drives the real route and reads the drawn strings).

## The fixed box

`<1%` is three glyphs against `0%`'s two; `>99%` is four against `100%`'s four. The longest string
the rule can now produce is one both slots already drew, which the guard asserts against what each
card actually drew rather than against a glyph-width argument.

## Guards

`__tests__/shareBoundaryPercent7716.test.tsx` — 15 tests, both directions (gotcha #43), driven
through the real routes. Mutation-checked four ways, all killed:

| mutation | tests failed |
|---|---:|
| restore `Math.round(p * 100)` | 6 |
| drop the `probability === 0` clause | 2 |
| narrow `!Number.isFinite` back to `Number.isNaN` | 1 |
| revert `pairedDuel` to its hand-built `${second}%` | 1 |

### One existing guard went vacuous and was re-armed rather than renumbered

`unfurlPillAndPair6849`'s *"a FIELD with two priced survivors is NOT normalized as a pair"*
discriminated on 56-vs-57 for its measured `0.565 / 0.425` specimen. Under the new rounding the
honest read is 57 **and** the normalized read is 57 — identical — so a renumbered assertion would
pass just as happily against the defect it exists to catch. The production fixture is kept and a
derived control at `0.55 / 0.44` carries the discrimination (passthrough 55/44, normalized 56/44).

Proof it matters: mutating the predicate to survivor-counting (`priced.length === 2`) is killed by
the new test and **not** by the old one.

## Named residue, not oversight

The marker makes *"leads at >99% over a live final"* a TRUE sentence, so whether #6029/#6149 should
still withhold that band at all is now a live question. It is theirs to re-open; this ship does not
answer it in passing, and their withheld sets are unchanged.

## The guard's own reader was wrong, and CodeQL caught it

The first pushed sha (`bae79b7b4`) took a CodeQL `js/double-escaping` **high** on this file's own
`drawn()` helper. It was not a nit — it was a hole in the assertion the file exists to make. The
helper un-escaped `&amp;` → `&` and then `&lt;` → `<`, so a card drawing the literal text
`&amp;lt;1%` reached these assertions as `<1%` and passed them:

```
input      &amp;lt;1%
chained -> <1%        the marker, from a card that drew no marker
one pass-> &lt;1%     honest
```

A suite whose whole subject is whether the `<` and `>` markers reach a reader cannot have a reader
that can invent them. Repaired in `151896bc5` with one regex over an entity map —
`teamUnfurlCard.test.tsx`'s existing idiom, which this file should have taken whole the first time.
The raw-markup assertion that proves the marker is not escaped away never went through the helper
and is unaffected.

Notice 32 worked exactly as written: CI and the runs API both read green on that sha while the
CHECK-RUN carried the alert. The sha was never offered.

## Gates

On `151896bc5`: `npm run build` exit 0 · `npm run typecheck` exit 0 (70, baseline 70) · `npx jest`
exit 0 (958 suites, 14,865 tests).
