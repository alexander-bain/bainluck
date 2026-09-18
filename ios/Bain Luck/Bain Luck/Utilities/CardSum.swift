import Foundation

/// Why a card's two numbers do not add up to 100 — native's arm of the
/// `card_sum` half of `contracts/rendered_percent.json` (#2088).
///
/// ## Why this file exists at all
///
/// `renderedCardPercents` (RenderedPercent.swift) fixed the pair that SHOULD
/// total 100: a complement pair is normalized, rounded once and derived, so
/// `93 / 8` became `93 / 7`. It deliberately left alone the pair that should
/// not total 100, and it was right to — normalizing a pair summing to 0.97
/// would invent three points of probability rather than round one.
///
/// But that leaves a card printing `57 / 40` with nothing saying why, and a
/// reader cannot tell "these are two real numbers that genuinely do not add up"
/// from "the renderer is buggy again". The two look identical, and one of them
/// is a bug we had just fixed. **An UNEXPLAINED non-100 is the defect; a
/// labelled one is a fact.**
///
/// ## Why NATIVE is late to it, and what a reader saw
///
/// The contract has carried `card_sum_rule` and its twelve rows since version 4,
/// and `card_sum_implementations` listed **two** runtimes where the scalar and
/// duel arms list three. Python decides it, web draws it in `FeedCard.tsx`, and
/// the iOS tree contained no reference to `card_sum_reason` in any file. So the
/// same card explained itself on the web and stood bare on the phone.
///
/// MEASURED on production 2026-09-18, `GET /api/feed?limit=200`: 98 objects carry
/// `card_sum_reason` and **2 read `independent_prices`** — "Crude Oil all time
/// high?" printing `13% / 1%` and "Will any country join the Mecca Agreement?"
/// printing `26% / 6%`. Web prints a sentence under both. The phone printed the
/// bare pair.
///
/// ## The served reason is the ONLY reason, and why native differs from web here
///
/// Web keys its local fallback on the KEY BEING ABSENT rather than on the value
/// being falsy (`"card_sum_reason" in data`), because `?? derive()` re-derives on
/// every correct card and makes the server's answer decorative. Swift cannot
/// express that distinction cheaply: a synthesized `decodeIfPresent` returns the
/// same `nil` for an absent key and a served `null`, so the only way to tell them
/// apart is a hand-written `init(from:)` over all thirty fields of
/// `FeedFuturesData`. An earlier draft of this file tried a wrapper type with a
/// `decodeNil()` check; it does not work, because `decodeIfPresent` never calls
/// the wrapper's initializer for a null, and the test below caught it.
///
/// So native takes the server's answer VERBATIM and derives nothing. MEASURED on
/// production 2026-09-18 over `GET /api/feed?limit=200`: of 98 objects carrying
/// the field, **98 agree with the local derivation and 0 disagree, and the key is
/// absent on 0 of them** — so the fallback would be dead code whose only
/// reachable behaviour is overriding a server `null` it disagrees with. A card
/// from a cached body old enough to predate the field simply draws no sentence,
/// which is exactly what the phone did before this shipped.
///
/// `cardSumReason` below is still native's arm of the contract rule and is driven
/// through all twelve rows by `CardSumContractTests`: the rule has to exist in
/// this runtime for the drift check to have something to pin, and for the
/// not-firing direction to be asserted here rather than assumed from web.

/// A served outcome has no number at all, so there is no total to check.
let sumUnpricedOutcome = "unpriced_outcome"
/// Both sides are numbered and the pair is outside the complement band — the
/// venue is quoting two independent questions, so the total is whatever the two
/// answers say.
let sumIndependentPrices = "independent_prices"

/// The integer total this surface prints for one card, or nil when it prints
/// nothing.
///
/// An unnumbered outcome contributes nothing rather than a zero — "no number"
/// and "0%" are different cards, the same distinction `renderedPercent` draws —
/// so `[57, nil]` totals 57 and is explained by `cardSumReason` rather than
/// reported as a 43-point miss.
nonisolated func cardSum(_ probabilities: [Double?]) -> Int? {
    let percents = renderedCardPercents(probabilities).compactMap { $0 }
    guard !percents.isEmpty else { return nil }
    return percents.reduce(0, +)
}

/// Why this card's printed percents do not total 100, or nil if they do.
///
/// Taken over `renderedCardPercents` rather than over the raw doubles, so it
/// answers for **the picture**. A complement pair is normalized, rounded once
/// and derived, so it totals 100 by construction and can never earn a reason —
/// that direction is pinned by the contract table as hard as the firing one,
/// because a guard that only proves it fires is how the Sports tab got emptied
/// (gotcha #43).
///
/// nil for any arity other than two. It means "no claim about a total is made
/// here", never "checked and fine", and a surface must not render it as a clean
/// bill of health: three outcomes totalling 97 is the independent-binary class
/// (gotcha #23), which has its own machinery and a different answer.
nonisolated func cardSumReason(_ probabilities: [Double?]) -> String? {
    guard probabilities.count == 2 else { return nil }
    let percents = renderedCardPercents(probabilities)
    if percents.contains(where: { $0 == nil }) { return sumUnpricedOutcome }
    return percents.compactMap { $0 }.reduce(0, +) == 100 ? nil : sumIndependentPrices
}

/// The sentence a card carries when its numbers do not total 100.
///
/// One per reason and no default: an unrecognised reason draws NOTHING rather
/// than an empty or invented explanation, which would be worse than the
/// unexplained card this exists to replace. A future server reason this build
/// has never heard of is exactly that case — the phone ships for months against
/// a moving server.
///
/// The words are web's, verbatim (`frontend/lib/cardSum.ts`). A second
/// vocabulary for one fact is how two surfaces start disagreeing in front of a
/// reader who opens both. Ruling 138 bans the `price` stem from reader copy —
/// the word is PROBABILITY — so neither sentence says "priced" or "prices"; the
/// machine-readable reasons carry that stem and are never rendered.
nonisolated func cardSumExplanation(_ reason: String?) -> String? {
    switch reason {
    case sumIndependentPrices:
        return "These two sides are quoted separately, so they do not add up to 100."
    case sumUnpricedOutcome:
        return "One side has no number, so there is nothing to add up."
    default:
        return nil
    }
}

