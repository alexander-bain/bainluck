# Final result plus a distinct open winner quote — #9544 / #9484
PILLAR: TRUTH / FORMATTING. SHIP: a finished game keeps its final result while a genuinely mapped, still-open winner contract updates in a separate Still trading section.

Only new helper/model/view/test files in the first commit; route and native integration are separate reviewed deltas. No production data writes or event/result mutation.

Backend builder seam, after its loaded data and before return:

```python
from app.utils.final_game_winner_quote import final_game_winner_quotes
from app.utils.outcome_display import normalize_display_probs
response.update(final_game_winner_quotes(
    event_id=event_id, event_is_finished=event_is_finished,
    mapped_event_ids=market_event_ids,
    home_name=event.home_team_name, away_name=event.away_team_name,
    markets=markets, outcomes=outcomes,
    observed_at=_observed_at_by_outcome,
    is_match_winner=_market_is_event_match_winner,
    winner_side=_match_winner_side,
    fold_winner_markets=_fold_duplicate_match_winner_markets,
    resolve_outcome_name=resolve_binary_matchup_outcome_name,
    normalize_probs=normalize_display_probs,
))
```

Empty-builder response adds `open_winner_quote: null`, `closed_winner_market_ids: []`; absence is not a terminal contract. Existing status/scores/buckets remain intact. Existing #9524 stream envelope subscribes every loaded candidate, including withheld quotes, and binds every quote outcome to its real market/revision. The ordinary settled `other` bucket is unchanged.

`open_winner_quote` contains event_id, market_id, market_name, source, status=open, nullable oldest actual observed_at, and outcomes[{outcome_id, side(home/away/draw), name, probability, nullable observed_at}]. `closed_winner_market_ids` contains only exact recognized mapped winner contracts with settlement evidence. Closed/resolved/graded/open-with-settled_at are terminal; unknown/missing/withdrawn are not.

Only loaded markets tied to the canonical or proven-fold event IDs qualify. Unlinked name/time fallback cannot. Every outcome participates in matching/settlement before price filtering. Unknown/missing/invalid/empty-book/refuted-book legs withhold the whole book; a known short venue field is also withheld. Existing whole-book fold selects one venue. Existing normalization policy is invoked only for the selected market's known mutually_exclusive=True metadata; its refusal bands remain unchanged. Where normalization derives sibling values, every resulting age uses the oldest actual contributor observation. No revision clock is a price age.

Native additive integration: optional `openWinnerQuote: FinalGameWinnerQuote?`, `closedWinnerMarketIds: [Int]?` on GameMarketsResponse; include quote outcome IDs in whole-projection reconciliation, keep missing-price withdrawal fences, and preserve closed IDs for the held page lifetime. Terminal evidence clears a held quote even if unrelated regressed fields reject the incoming body. A quote may never change sport status/result/score or become the hero probability. FinalGameWinnerQuoteView requires final event phase, exact identity and an open nonterminal valid quote. Its separate section uses existing source age and percentage formatting; existing renderedCardPercents only repairs actual complement-pair rounding and leaves nonunit raw vectors under its existing refusal policy.

Validation: 50 focused helper cases +4 startup (54 total); Ruff/diff clean. 8 native XCTest cases authored, Swift parse only. Native owns composed executable Xcode/XCTest/simulator gates; source review is not release or reader acceptance.
