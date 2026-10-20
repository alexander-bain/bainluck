# Discover culture comparisons — first local source slice

PILLARS: DISCOVER / FORMATTING / TRUTH.
SHIP: compare several films' Rotten Tomatoes forecasts at the same visible score thresholds, and open every original full question.

Alex's October10 direction prioritizes entertainment/culture grouping and explicitly asks to reuse the prior Issues exploration. No NFL dependency for this local source work.

## Existing decisions recovered from Issues

- #723: 3–4 movies' Rotten Tomatoes probability curves together; Netflix #1/#2/#3 questions as a leaderboard rather than isolated ordinal cards. These rank questions are distinct, never mutually exclusive outcomes to sum or average.
- #4463: group before the cut; the US/global Netflix pair is a comparison, not equivalent questions.
- #10353–#10357 October6 comments: four founder-graded slates, 98 cards. Same-question, deadline, movers and round-up formats; passive rows and original question access. The experiments are founder evidence, not live production acceptance.
- #10354 October7 ruling: new scalar sibling groups need positive equivalence on every fixed dimension and one common deadline. This slice does not construct that new family or infer equivalence from titles/deadlines.
- #2927/#9925/#9935: full collection identity/membership/page machinery already exists; do not build another grouping or container service.

Canonical exploration: #10353 comment6020513288; #10354 comment6020513685; #10357 comment6020514882; artifact `fable-ranking-github-20261004/11-COMPARISON-WORKSTREAM-HANDOFF.md`.

## Implemented

Existing `assemble_discover_comparison_bundles` already creates RT bundles before the cut. Existing `DiscoverCard` routes those to `GroupCard`. The new bounded presentation uses that path, requiring:

- All original members have explicit matching RT-score display grammar and the existing RT threshold archetype, with open state and no source-disagreement flag.
- At least two priced common coordinates across all members: exact label, threshold value, unit and direction. Strict `Above 70` never becomes inclusive `70+`; audience/critic declarations never merge.
- Columns are up to three adjacent common thresholds around the existing `answerRung` of the server's first-ranked member. Film order stays in server order. No new ranking weights or feed quotas.
- Full original names, each row's resolution copy/price-age disclosure and original detail destinations remain. This is several independent score curves, not a claim about which film wins or an aggregate probability.
- Unknown shapes, conflicting coordinates, duplicate rungs, missing prices or insufficient common columns fall back to existing member rows. Open-ladder zero follows `printsAPercent` rather than inventing an impossible forecast.

No backend/payload/native mutation, provider query, new candidate fetch, collection route, LLM, deployment or issue metadata change.

## Validation and remaining work

Focused frontend author check: 17 tests pass across new `rottenTomatoesComparison10357` and existing `comparisonBundleSharedQuestion4066`. Tests enter actual DiscoverCard and cover aligned numbers, original links, unchanged inventory, strict/inclusive and audience mismatches, invalid coordinates, unknown/old payload fallback, missing and zero prices, server order and immutability.

Historical #9803 names/prices are reconstructed as feed fixtures. Their synthetic outcome IDs and test dates are not provider provenance/current supply. Source independent review found zero-price handling; corrected using the existing price predicate. Full build/typecheck, carrying-browser 390px inspection, deployment and reader acceptance remain separate and unperformed under release-resource protection.

Next implementation: Netflix weekly ordinal boards using the existing bundle path, once exact supported week/region/rank identities can be bound from retained or authorized producer evidence. Equal closing dates or the words “this week” do not prove the same observation week. This missing evidence does not block the completed RT presentation slice or other ranking work.

## Phone-width component rendering

Actual DiscoverCard SSR with the existing RT fixture and repository Tailwind/global tokens was inspected at390px in the in-app browser. Both complete film questions, all three threshold columns, all six probabilities and original futures destinations are readable; document width390/table356, no page overflow. This is a local static component rendering with retained names/prices and synthetic dates, not a live feed, hydrated interaction check, provider specimen or installed-reader acceptance. The caption now says “Forecasts for each score threshold,” preserving strict Above and inclusive N+ distinctions without calling them exact-score chances. Contradictory direction coordinates refuse the comparison.18 focused guards pass; an additional temporary one-case render harness produced the HTML and was removed. Independent correction source review clear. Full build/typecheck and delivered-browser acceptance remain unpaid.

## Port onto current master (October 20)

The two reviewed RT commits above (`663492ef32`, `2c5f3b23a9`, base `a097efc4fe`) were ported selectively onto master `70ee2f53f4`; the culture branch's Netflix producer and membership commits were left out. `RottenTomatoesComparison.tsx`, `lib/discover/rottenTomatoesComparison.ts` and the 10357 jest suite are byte-identical to `2c5f3b23a9`. `GroupCard.tsx` carries the same four hunks; the only change around them is #10877's `bundleExpandLabel` import, which arrived on master in between and composed without conflict. One focused jest run (`rottenTomatoesComparison10357` + `comparisonBundleSharedQuestion4066`, one worker): 18 passed. This is source composition only. Build, typecheck, independent delta review, exact-source CI, merge, delivery and the 390px reader check are still owed.
