import Foundation

/// Pure display logic for the grouped search answer (#3124).
///
/// The native mirror of `frontend/components/searchFamilyDisplay.ts`. The server
/// composes the families; both surfaces only decide what to DRAW from them, and
/// they must decide it the same way — a query that reads as one tournament on the
/// web and as ten sibling rows on the phone is the same defect twice.
///
/// Kept free of SwiftUI so the decisions below are unit-testable. Every one of
/// them is a decision that was previously made by not decoding the payload at
/// all: `SearchResponse` dropped `futures_families` and `event_concepts` on the
/// floor, so the phone flattened a structured answer into an undifferentiated
/// list and drew "US Open Men's Singles Winner" beside "2026 Men's US Open Winner
/// (Tennis)" with nothing saying they are the same question.
enum SearchGrouping {

    /// Market ids drawn INSIDE a family card (headline + its shown members).
    ///
    /// These are removed from the flat list so nothing renders twice. Note the
    /// members counted by `moreCount` are deliberately NOT in here: those stay in
    /// the flat list, which is exactly what "+N more markets below" promises.
    static func shownIds(_ families: [SearchFuturesFamily]) -> Set<Int> {
        var ids = Set<Int>()
        for family in families {
            ids.insert(family.headline.id)
            for member in family.members { ids.insert(member.id) }
        }
        return ids
    }

    /// The flat futures rows left once the families have taken theirs.
    ///
    /// Order is preserved: the server already reranked this list and the phone has
    /// no better opinion about it.
    static func flatFutures(
        _ futures: [SearchFuturesMarket],
        families: [SearchFuturesFamily]
    ) -> [SearchFuturesMarket] {
        let taken = shownIds(families)
        return futures.filter { !taken.contains($0.id) }
    }

    /// Concepts worth drawing as their own row — those NOT already on the page.
    ///
    /// ── WHY THIS FILTER EXISTS, AND WHY IT USUALLY EMPTIES THE SECTION ────────
    ///
    /// An `event_concept` is derived FROM a futures market and carries that
    /// market's id; it is not an independent record. So for "US Open" the server
    /// sends four concepts — Men's Singles and Women's Singles, once per source —
    /// whose `market_id`s are the same four markets the family card above already
    /// collapses. Drawing them unfiltered would put the duplicate pair back on the
    /// page one section higher, which is the precise bug #3124 is about.
    ///
    /// Measured against production on 2026-09-05 over eight queries (US Open,
    /// Alcaraz, Super Bowl, Grammys, Djokovic, Tour de France, UFC, Sabalenka):
    /// **zero** concepts were novel. So today this returns nothing on every query
    /// tried, and that is the correct answer rather than a missing feature — the
    /// section appears if and when the server surfaces a concept whose market the
    /// page does not otherwise show.
    ///
    /// A concept with no `marketId` is dropped: iOS has no concept screen (the
    /// web's `/event/<domain>/<slug>` has no native route), so a market is the
    /// only honest destination, and a row that goes nowhere is worse than no row.
    static func novelConcepts(
        _ concepts: [SearchEventConcept],
        families: [SearchFuturesFamily],
        flatFutures: [SearchFuturesMarket]
    ) -> [SearchEventConcept] {
        var drawn = shownIds(families)
        for market in flatFutures { drawn.insert(market.id) }

        var seen = Set<Int>()
        return concepts.filter { concept in
            guard let marketId = concept.marketId else { return false }
            guard !drawn.contains(marketId) else { return false }
            // Two sources can derive the same concept; one row per destination.
            return seen.insert(marketId).inserted
        }
    }

    /// The outcome a row leads with — the first with a probability.
    ///
    /// The server has already applied leader-pick and independent-binary
    /// normalisation, so this takes `topOutcomes` as given rather than re-ranking.
    static func leaderOutcome(_ market: SearchFuturesMarket) -> SearchFuturesOutcome? {
        market.topOutcomes?.first { $0.probability != nil }
    }

    /// "+4 more markets below" — nil when the family promises nothing further.
    ///
    /// Phrased as "below" because that is what the count measures (#2646): rows
    /// this response also ships in the flat list. It is never `memberCount`, which
    /// counts members the payload does not contain and the page cannot show.
    static func moreBelowLabel(_ family: SearchFuturesFamily) -> String? {
        guard let count = family.moreCount, count > 0 else { return nil }
        return "+\(count) more market\(count == 1 ? "" : "s") below"
    }
}
