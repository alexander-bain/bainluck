Fable: needed (reader-visible)

Pillar: TRUTH. Ship: each Super Bowl page, its browser title and its share image
name the same favourite at the same probability.

After #12587, the Nov 11 9:44 AM PT reads of the three verified boards agreed on
all 32 current probabilities, contributors and observation clocks. The 390 px
body captures agreed on San Francisco at 13%. Two differences remained: metadata
and share-image routes still fetched the per-venue representation, and the
verified Kalshi board retained short city names. The capture-publication mistake
and corrected Nov 11 links remain recorded on #12530.

The metadata and share-image routes now request `verified_title`, as the page
already does. Existing missing-market, temporary-error, unpriced and settled
branches remain. If the server refuses composition, its source answer is kept.
Verified detail rows copy the same proven club name already used by canonical
search previews. Outcome IDs, source attribution, default/source responses and
stored names are unchanged; refused identity rows keep their original names.
No stored data, schema, index, historical point or source-history key changes.

Regression proof:

- Before the fix, all six metadata/image cases used Buffalo at 15% instead of
  the verified San Francisco 13%. They now pass for 86832, 129037 and 40533.
- The backend route test first fails on the Kalshi board's short labels, then
  passes with the same club labels across all three pages. It preserves every
  outcome ID, source response and original model name. Contradictory or ambiguous
  identities remain refused; Other stays unpriced.
- 114 title-route checks and four startup checks pass. The route suite passes
  all twelve clock points. 155 web metadata, share-image, error, settlement,
  rounding and verified-page checks pass. Build and typecheck pass (65 baseline,
  no new errors).

Pending: owned PR after #12597's CI completes, fresh CI, actual bot approval,
Fable ACCEPT, the serialized merge/deploy slot and served verification. The
served check must compare the three current boards, browser titles, share images
and 390 px body headlines. Source histories retain their own samples and keys;
this does not claim blended historical curves or resolve #12540's cold read.
