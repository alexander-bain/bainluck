import Foundation

// MARK: - #9387 verified championship detail — the client's decisions
//
// The server (`/api/futures/{id}?representation=verified_title` and its
// `/probability-timeline` twin) decides WHICH venues ask the same title question
// and what the one current number is. Everything here is presentation: which
// labels a response earns, and whether the chart's current column agrees with
// the detail's hero. Nothing here blends, re-ranks or manufactures history.

/// The representation a request asks for, and the one a response says it IS.
nonisolated enum FuturesRepresentation: String, Sendable, Equatable {
    case source
    case verifiedTitle = "verified_title"

    /// A response's EFFECTIVE mode. Absent, malformed or unknown reads as
    /// `source`: the only thing that earns verified presentation is the server
    /// saying so in a value this build understands.
    static func effective(_ raw: String?) -> FuturesRepresentation {
        raw.flatMap(FuturesRepresentation.init(rawValue:)) ?? .source
    }
}

extension FuturesMarketDetail {
    nonisolated var effectiveRepresentation: FuturesRepresentation { .effective(representation) }
}

extension ProbabilityTimelineResponse {
    nonisolated var effectiveRepresentation: FuturesRepresentation { .effective(representation) }
}

/// Main-actor (the project default) because `SourceLabels` is.
enum VerifiedTitlePresentation {
    /// The only contributor keys the server may emit. A key outside this set is
    /// one this build cannot name, and the page falls back to its source header.
    static let sourceVocabulary: Set<String> = ["odds_api", "kalshi", "polymarket"]

    /// The hero outcome's actual contributor keys, in served order — or nil when
    /// the page must keep its source-mode header: a source response, no hero, an
    /// empty list, or any key outside the vocabulary.
    static func heroContributors(_ market: FuturesMarketDetail, hero: FuturesOutcome?) -> [String]? {
        guard market.effectiveRepresentation == .verifiedTitle, let hero else { return nil }
        return nameable(hero.contributingSources)
    }

    /// The market-wide union, for the metadata chips only — never the hero.
    static func marketContributors(_ market: FuturesMarketDetail) -> [String]? {
        guard market.effectiveRepresentation == .verifiedTitle else { return nil }
        return nameable(market.contributingSources)
    }

    /// Reader labels for a contributor list ("Sportsbooks", "Kalshi", …). One
    /// actual contributor is one label — never dressed up as a blend.
    static func labels(_ keys: [String]) -> [String] {
        keys.compactMap { SourceLabels.label(for: $0) }
    }

    /// The hero pill text: the hero outcome's contributors when verified,
    /// otherwise the market's own source exactly as before.
    static func heroSourcePill(_ market: FuturesMarketDetail, hero: FuturesOutcome?) -> String? {
        if let keys = heroContributors(market, hero: hero) {
            return labels(keys).joined(separator: " · ")
        }
        return market.source.flatMap { SourceLabels.label(for: $0) }
    }

    /// The share sentence. While the web destination stays in source mode a
    /// VERIFIED share carries no number — the link would open a page quoting a
    /// different estimator. Source-mode sharing is unchanged.
    static func shareOmitsQuote(_ market: FuturesMarketDetail) -> Bool {
        market.effectiveRepresentation == .verifiedTitle
    }

    /// The chart's history label, taken from the timeline response ITSELF.
    /// "Sportsbooks history" for odds_api; nil (no label) for a basis this build
    /// cannot name or a response that carries none.
    static func historyLabel(_ basis: TimelineHistoryBasis?) -> String? {
        guard let basis, basis.kind == "single_source",
              let name = SourceLabels.label(for: basis.source) else { return nil }
        return "\(name) history"
    }

    /// "Current blend" is earned only by a current outcome that really has more
    /// than one contributor.
    static func isCurrentBlend(_ meta: TimelineOutcomeMeta) -> Bool {
        (nameable(meta.contributingSources)?.count ?? 0) > 1
    }

    /// The one caption a verified-context chart earns, or nil (every source-mode
    /// chart, every golf/field/settled board the server answers in source mode).
    ///
    /// Verified context = the response is verified, OR the detail is and the
    /// chart could not agree with it (then the lines keep their own label and
    /// the current column is withheld). The label comes from THIS response's
    /// `history_basis`; "current blend" is added only while the current column
    /// is shown and a drawn row really has more than one contributor.
    static func chartCaption(_ response: ProbabilityTimelineResponse,
                             expected: VerifiedTitleChartExpectation?,
                             displayed: [TimelineOutcomeMeta],
                             withholdsCurrent: Bool) -> String? {
        let verifiedContext = response.effectiveRepresentation == .verifiedTitle
            || expected?.representation == .verifiedTitle
        guard verifiedContext, let history = historyLabel(response.historyBasis) else { return nil }
        guard !withholdsCurrent, response.effectiveRepresentation == .verifiedTitle,
              displayed.contains(where: isCurrentBlend) else { return history }
        return "\(history) · Prob: current blend"
    }

    private static func nameable(_ keys: [String]?) -> [String]? {
        guard let keys, !keys.isEmpty,
              keys.allSatisfy({ sourceVocabulary.contains($0) && SourceLabels.label(for: $0) != nil })
        else { return nil }
        var seen = Set<String>()
        return keys.filter { seen.insert($0).inserted }
    }
}

// MARK: - Detail ↔ chart agreement

/// What the detail's hero says now, handed to the chart so the chart can tell
/// whether its own current column answers the same question with the same value.
nonisolated struct VerifiedTitleChartExpectation: Equatable, Sendable {
    let representation: FuturesRepresentation
    let heroOutcomeId: Int?
    let heroProbability: Double?
    let heroContributors: [String]

    init(representation: FuturesRepresentation, heroOutcomeId: Int?,
         heroProbability: Double?, heroContributors: [String]) {
        self.representation = representation
        self.heroOutcomeId = heroOutcomeId
        self.heroProbability = heroProbability
        self.heroContributors = heroContributors
    }

    init(market: FuturesMarketDetail, hero: FuturesOutcome?) {
        self.init(representation: market.effectiveRepresentation,
                  heroOutcomeId: hero?.id,
                  heroProbability: hero?.probability,
                  heroContributors: hero?.contributingSources ?? [])
    }

    /// Whether a timeline response's CURRENT column agrees with this detail.
    /// Mode first; then, in verified mode, the hero outcome's value and its
    /// contributor set, matched by outcome id. History is never compared — it
    /// is the source's own and is allowed to differ from any current number.
    func agrees(with response: ProbabilityTimelineResponse) -> Bool {
        guard response.effectiveRepresentation == representation else { return false }
        guard representation == .verifiedTitle, let heroOutcomeId else { return true }
        guard let meta = response.outcomes.first(where: { $0.id == heroOutcomeId }) else {
            // The hero is outside the returned list: nothing to contradict.
            return true
        }
        return meta.currentProbability == heroProbability
            && Set(meta.contributingSources ?? []) == Set(heroContributors)
    }
}

/// The bounded disagreement policy: ONE refetch per detail/range generation,
/// then keep the authentic history and withhold the current column. Never a loop.
nonisolated struct VerifiedTitleChartPolicy: Sendable {
    /// What opens a new generation: a detail refresh, a range change, or a new
    /// hero reading from the detail.
    struct Generation: Equatable, Sendable {
        let refreshToken: Int
        let range: String
        let expectation: VerifiedTitleChartExpectation?
    }

    enum Step: Equatable, Sendable {
        /// Draw the response. `withholdsCurrent`: omit its current-column numbers.
        case adopt(withholdsCurrent: Bool)
        /// Discard the response and ask once more.
        case refetch
    }

    private(set) var generation: Generation?
    private(set) var refetched = false

    mutating func step(_ response: ProbabilityTimelineResponse, generation: Generation) -> Step {
        if generation != self.generation {
            self.generation = generation
            refetched = false
        }
        // No expectation = a caller that is not the verified detail: unchanged.
        guard let expectation = generation.expectation else { return .adopt(withholdsCurrent: false) }
        if expectation.agrees(with: response) { return .adopt(withholdsCurrent: false) }
        if !refetched {
            refetched = true
            return .refetch
        }
        return .adopt(withholdsCurrent: true)
    }

    /// The current-column copy of a response whose current numbers cannot be
    /// reconciled: same names, ids, order and history keys; no current value and
    /// no movement, so nothing on screen contradicts the hero.
    static func withholdingCurrent(_ outcomes: [TimelineOutcomeMeta]) -> [TimelineOutcomeMeta] {
        outcomes.map { $0.withholdingCurrent() }
    }
}
