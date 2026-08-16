import Foundation

/// The single Discover card classifier (#1883).
///
/// Before this existed the rule lived in two hand-maintained copies —
/// `DiscoverView.itemCategory` and `DiscoverViewModel.category(for:)` — which is
/// gotcha #129 (a rule that lives in two consumers has two verdicts). They had
/// already drifted **four** ways, and the drift was live, not latent: measured
/// against 83 real production cards on 2026-08-14, **14 of 83 (17%) classified
/// differently** between the two copies.
///
/// | type         | view said                      | view model said | count |
/// |--------------|--------------------------------|-----------------|-------|
/// | `tournament` | `"golf"` (via a fall-through)  | `"other"`       | 8     |
/// | `bundle`     | the child's real category      | `"other"`       | 6     |
///
/// The four divergences, all present on master, none of them about concepts:
///   1. `itemCategory` ended in a bare `return "golf"`. Nothing handled
///      `tournament`, so every tournament card fell through to it.
///   2. Bundles: the view recursed into the first eligible child; the view model
///      had no bundle branch at all.
///   3. Futures: the view model lowercased `llmSportCategory`, the view did not.
///   4. Nil-sport events: the view fell back to `"sports"` — which is **not** in
///      the sports set — and the view model to `"other"`.
///
/// Adding a fifth rule to two functions that already disagreed four ways is how
/// gotcha #129 keeps recurring, so the copies are gone rather than tested for
/// agreement: divergence is now unrepresentable, not merely asserted against.
enum DiscoverCategory {

    /// The one sports-category set. Previously duplicated as `DiscoverView.sportsCats`
    /// and `DiscoverViewModel.sportsCategories` (byte-identical at the time of
    /// unification — verified, not assumed).
    static let sportsCategories: Set<String> = [
        "basketball", "football", "baseball", "hockey", "soccer",
        "golf", "mma", "boxing", "tennis", "cricket", "motorsports",
        "americanfootball", "icehockey", "olympics",
    ]

    /// Concept cards carry a raw *domain* (`"ufc"`, `"f1"`, `"cycling"`), not one of
    /// the sport tokens the interleave understands. `"ufc" != "mma"` and
    /// `"f1" != "motorsports"`, so every concept fell into the non-sports partition
    /// — which had no adjacency guard — and drained in raw server order (#1883).
    ///
    /// Mapped here, once, so both consumers agree by construction. Domains with no
    /// entry pass through unchanged: `"cycling"` is deliberately absent because it
    /// is not in `sportsCategories` either, and inventing a token for it would move
    /// cycling cards between partitions on no evidence.
    static let domainTokens: [String: String] = [
        "ufc": "mma",
        "bellator": "mma",
        "pfl": "mma",
        "one": "mma",
        "f1": "motorsports",
        "formula1": "motorsports",
        "motogp": "motorsports",
        "nascar": "motorsports",
        "indycar": "motorsports",
    ]

    /// Tournament cards carry **no sport field** — `FeedTournamentData` has `tour`
    /// (`"pga"`, `"dp_world"`) and nothing else that names a sport. Every tournament
    /// card the feed served in the 83-card production sample was a golf tournament,
    /// and the pre-unification view classified all of them `"golf"` through its
    /// fall-through default, so `"golf"` is preserved here **explicitly** rather than
    /// accidentally: same verdict for every card measured, but now derived and
    /// legible instead of being whatever the last `return` happened to say.
    ///
    /// This is correct-by-measurement, not correct-by-construction. Revisit the
    /// moment the feed serves a non-golf tournament; `testTournamentClassification_
    /// isGolfByMeasurementNotByConstruction` records the reasoning next to the rule.
    static let tournamentFallbackCategory = "golf"

    /// Classify one feed item.
    ///
    /// - Parameter bundleChild: resolves which child a bundle takes its category
    ///   from. Injected because the view admits children through its lifecycle
    ///   stale gate first (C29 P2 — never a stale raw first child), and that gate
    ///   is time-dependent view state that does not belong in a pure classifier.
    ///   The default (first child) matches the view whenever bundles have been
    ///   sanitized upstream, which `filteredItems` / `sanitizedFeedItems` already
    ///   guarantee for every production path.
    static func of(
        _ item: FeedItem,
        bundleChild: (FeedBundle) -> FeedItem? = { $0.items.first }
    ) -> String {
        if let event = item.event {
            // Nil sport falls back to "other", not the old view's "sports" — which
            // was not in `sportsCategories`, so it was a sports-looking token that
            // routed the card to the non-sports partition anyway.
            return event.sport?.split(separator: "_").first.map { $0.lowercased() } ?? "other"
        }
        if let futures = item.futures {
            return futures.llmSportCategory?.lowercased() ?? "other"
        }
        if let concept = item.concept {
            return token(forDomain: concept.domain)
        }
        if item.tournament != nil {
            return tournamentFallbackCategory
        }
        if let bundle = item.bundle {
            guard let child = bundleChild(bundle) else { return "other" }
            return of(child, bundleChild: bundleChild)
        }
        return "other"
    }

    /// Map a concept's raw domain onto the sport token the interleave understands.
    static func token(forDomain domain: String?) -> String {
        guard let lowered = domain?.lowercased(), !lowered.isEmpty else { return "other" }
        return domainTokens[lowered] ?? lowered
    }

    /// True when this item belongs in the interleave's sports partition.
    static func isSports(_ item: FeedItem, bundleChild: (FeedBundle) -> FeedItem? = { $0.items.first }) -> Bool {
        sportsCategories.contains(of(item, bundleChild: bundleChild))
    }
}
