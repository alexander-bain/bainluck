import Foundation

/// #10868 — THE SOCCER MATCH SCREEN'S PRODUCTION ADAPTER, PART TEN: THE
/// FULL-MATCH / FIRST-HALF EXACT-SCORE MAP.
///
/// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: before kickoff the soccer page
/// shows every listed exact score of the full match and of the first half on one
/// map — each original's own pre-match chance at its own time — and the same map
/// opens full size and comes back to the same scope and score.
///
/// The leaf is the accepted `ExactScoreMapPresentation10868` (package 26,
/// 0ce6b553), reused unchanged. This file only maps what the host already holds
/// onto that leaf's input:
///
///   - WHICH MARKETS   the owner's descriptor (`Descriptor`), passed through the
///     AND SCORES      host inside `SoccerPropReadingAdapter10868.Markets`, exactly
///                     as the story admission is. It names each scope's venue
///                     market id, whether that market is about one period (the
///                     first half), the goal axes, the pre-match scale bound, and
///                     for each listed original its served contributor outcome
///                     ids, its grid coordinate (or none) and a held label.
///                     Nothing here reads a title, a market or outcome name, or a
///                     fixture id to find a score or a scope: the 10238 matrix
///                     serves these markets as `named_options` with `period` and
///                     `predicate` null, and a typed row does not type a
///                     coordinate (Design, EXACT-SCORE-NATIVE-BINDING-MAP). A
///                     descriptor naming another event admits nothing, and so do
///                     another event's markets.
///   - identity        the served contributor outcome ids joined by "+" — part
///                     three's `Leg.id`, the identity every soccer story uses.
///                     Never a position, a label or a coordinate.
///   - membership      the descriptor's originals, in the descriptor's order. A
///                     listed original the payload no longer serves stays listed
///                     (the owner's held catalogue) with "Pre-match chance
///                     unavailable" — the payload's silence does not prove no
///                     price was ever recorded, so never "not recorded" and never
///                     an invented figure — and an unconfirmed result. After the
///                     final that is every first-half original, all nine, not
///                     only Other. A served row
///                     of the scope's market the descriptor does not name is still
///                     shown, off the grid, as a named choice: it is never dropped
///                     and never given a coordinate. When two descriptor entries,
///                     or two served rows, share one identity or one coordinate,
///                     every one is passed on and the leaf's own duplicate /
///                     ambiguous rule applies: nothing is chosen for it.
///   - pre-match       part three's `pregame`: before kickoff the row's own price
///                     on its own recent clock; once started the production pin
///                     helper's pin for the same original in an admitted
///                     10238.v1 game-scope matrix, before the listed start —
///                     never a settlement 0/1, never a last quote. Without one,
///                     part three's words: "not recorded" only on the producer's
///                     own `no_pregame_pin`, else "unavailable".
///   - current         during play only. The full match: part three's `current`.
///                     A period scope: part three's `periodCurrent` — a dated
///                     recorded quote under the in-play absence words, never the
///                     current chance (no decoded field proves the half is still
///                     being played).
///   - result          part three's `result` — the venue's own grade; a matrix
///                     grade that disagrees leaves it unconfirmed. Unknown is not
///                     loss, and an actual score never grades an original.
///   - actual          the full match's score from `EventDetail` once play has
///                     started, labelled and clocked on its own. No owner admits a
///                     first-half score, so that scope shows none.
///   - chances         never normalised, ranked, completed or complemented (the
///                     retained full-match pre-match sum is 1.0001 and stays so).
///   - selection       the host's held scope (else the descriptor's first scope)
///                     and its held score for that scope, passed through
///                     unchanged. A held score no longer listed stays selected and
///                     reads unavailable; nothing moves to a neighbour.
///
/// MISSING OWNER INPUT — named, not routed around; the path accepts each the
/// moment it is supplied:
///   - the descriptor itself: no owner types exact-score coordinates, scope or
///     axes yet (#10238 matrix producer typing, or a Native-owned descriptor
///     passed by `EventDetailView`'s adopter);
///   - a held pre-match pin for an original after its family leaves the payload
///     (the matrix question leaves with it, so no served channel carries it);
///   - a first-half score (no owner admits one; `EventDetailView.halfScores` is
///     private to Native).
enum SoccerExactScoreAdapter10868 {
    typealias R = SoccerPropReadingAdapter10868

    /// The owner's explicit exact-score metadata for one event. Supplied by the
    /// host; never found here from a title.
    struct Descriptor: Equatable {
        /// One listed original.
        struct Original: Equatable {
            /// The served `contributor_outcome_ids` — the identity. Empty names
            /// no original and is not shown.
            let outcomeIDs: [Int]
            /// The owner's grid coordinate, or `.nonGrid` ("Any Other Score").
            let placement: ExactScoreMapPlacement10868
            /// The owner's held label, shown only while the payload does not
            /// serve the row; a served row shows its own served outcome name.
            let label: String
        }

        /// One exact-score market ("Full match", "First half").
        struct Scope: Equatable {
            /// Opaque owner identity, passed back exactly.
            let id: String
            let label: String
            /// The venue market id.
            let marketID: Int
            /// The owner's period identity for a market about one period of the
            /// match ("first"); nil for the full match.
            let periodID: String?
            /// Home goals, top to bottom; away goals, left to right.
            let homeGoals: [Int]
            let awayGoals: [Int]
            /// The upper bound of the pre-match shading scale (lower is 0).
            let scaleUpper: Double
            /// In the owner's order.
            let originals: [Original]
        }

        let eventID: Int
        /// In the owner's order.
        let scopes: [Scope]

        func admits(_ event: EventDetail) -> Bool { eventID == event.id }

        /// The scopes' markets that are about one period, for All props to keep
        /// their in-play quotes historical. Nothing for another event.
        func periodMarketIDs(for event: EventDetail) -> Set<Int> {
            guard admits(event) else { return [] }
            return Set(scopes.filter { $0.periodID != nil }.map(\.marketID))
        }
    }

    /// Reader words. Plain chance, score and availability language only.
    enum Words {
        static let title = "How might it finish?"
        static let beforeIntro = "Each listed score’s pre-match chance, recorded at its own time. The chances are not adjusted to add up to 100%."
        static let liveIntro = "Each listed score’s pre-match chance beside its own current chance."
        static let finalIntro = "Each listed score’s pre-match chance beside its own result."
        static let scoreSoFar = "Score so far"
        static let finalScore = SoccerMatchPageAdapter10868.Words.finalScore
        static let observed = "observed"

        static func rows(_ team: String) -> String { "Rows: \(team) goals" }
        static func columns(_ team: String) -> String { "Columns: \(team) goals" }

        static let map = ExactScoreMapWords10868(
            pregameTitle: "Pre-match chance",
            currentTitle: "Current chance",
            liveResultTitle: "Half result",
            finalResultTitle: "Final result",
            scopeUnavailable: "Selected market unavailable.",
            noSelection: "Choose a score to compare.",
            selectionUnavailable: "Selected score unavailable.",
            recoverSelection: "View first listed score",
            mapUnavailable: "Score map unavailable. Every listed score is below.",
            scaleUnavailable: "Pre-match scale unavailable. Cells are not shaded.",
            panHint: "Swipe the map sideways to see every column.",
            notListed: "Not separately listed",
            unavailableMark: "—",
            otherChoicesTitle: "Other listed outcomes",
            previous: "Previous score",
            next: "Next score",
            details: "Details",
            selectedSpoken: "Selected",
            selectScopeHint: "Shows this market’s scores",
            selectHint: "Shows this score’s chances",
            detailsHint: "Opens the original market")

        static let legend = ExactScoreMapLegend10868(
            scaleTitle: "Pre-match chance · darker is higher",
            offScale: "Hatched: outside the pre-match scale",
            notListed: "Dashed: not separately listed",
            unavailable: "—: no pre-match chance",
            result: "Dark outline: confirmed result",
            selection: "Corner marks: selected score")
    }

    /// The map, or nil when the descriptor is absent or names another event, or
    /// when none of its scopes' markets serves a row in this event's own
    /// `/game-markets`. `selectedOriginals` is the host's held score per scope id.
    static func input(_ event: EventDetail, markets: GameMarketsResponse?, descriptor: Descriptor?, host: R.Host,
                      selectedScopeID: String? = nil,
                      selectedOriginals: [String: String] = [:]) -> ExactScoreMapInput10868? {
        guard let descriptor, descriptor.admits(event),
              let markets, markets.eventId == event.id else { return nil }
        let phase = SoccerMatchPageAdapter10868.phase(event, now: host.now)
        let built = descriptor.scopes.map {
            scope($0, event: event, markets: markets, phase: phase, host: host)
        }
        guard built.contains(where: { $0.served }) else { return nil }
        let names = SoccerMatchPageAdapter10868.names(event)
        let scopeID = selectedScopeID ?? descriptor.scopes.first?.id
        return ExactScoreMapInput10868(
            phase: phase.exactPhase,
            title: Words.title,
            intro: intro(phase),
            homeLabel: names.home,
            awayLabel: names.away,
            rowsTitle: Words.rows(names.home),
            columnsTitle: Words.columns(names.away),
            scopes: built.map { $0.scope },
            selectedScopeID: scopeID,
            selectedOriginalID: scopeID.flatMap { selectedOriginals[$0] },
            legend: Words.legend,
            words: Words.map)
    }

    static func intro(_ phase: SoccerEventPagePhase10868) -> String {
        switch phase {
        case .before: Words.beforeIntro
        case .live: Words.liveIntro
        case .final: Words.finalIntro
        }
    }

    // MARK: - One scope

    /// The scope, and whether its market serves at least one row here.
    static func scope(_ described: Descriptor.Scope, event: EventDetail, markets: GameMarketsResponse,
                      phase: SoccerEventPagePhase10868,
                      host: R.Host) -> (scope: ExactScoreMapScope10868, served: Bool) {
        let legs = R.legs(described.marketID, in: markets)
        let period = described.periodID != nil
        var claimed = Set<Int>()
        var originals: [ExactScoreMapOriginal10868] = []
        for listed in described.originals where !listed.outcomeIDs.isEmpty {
            let wanted = Set(listed.outcomeIDs)
            let hits = legs.indices.filter { !legs[$0].contributors.isEmpty && Set(legs[$0].contributors) == wanted }
            guard !hits.isEmpty else {
                originals.append(held(listed))
                continue
            }
            for index in hits {
                claimed.insert(index)
                originals.append(original(legs[index], placement: listed.placement, event: event, phase: phase,
                                          period: period, host: host))
            }
        }
        // A served row the owner did not describe stays reachable, off the grid.
        for index in legs.indices where !claimed.contains(index) {
            originals.append(original(legs[index], placement: .nonGrid, event: event, phase: phase,
                                      period: period, host: host))
        }
        let scope = ExactScoreMapScope10868(
            id: described.id,
            label: described.label,
            rows: described.homeGoals.map { ExactScoreMapGoal10868(value: $0, text: String($0)) },
            columns: described.awayGoals.map { ExactScoreMapGoal10868(value: $0, text: String($0)) },
            originals: originals,
            scale: scale(described.scaleUpper),
            actual: period ? nil : actual(event, phase: phase, host: host))
        return (scope, !legs.isEmpty)
    }

    // MARK: - One original

    static func original(_ leg: R.Leg, placement: ExactScoreMapPlacement10868, event: EventDetail,
                         phase: SoccerEventPagePhase10868, period: Bool, host: R.Host) -> ExactScoreMapOriginal10868 {
        let current: ExactScoreMapCurrent10868
        if phase == .live {
            current = Self.current(period ? R.periodCurrent(leg, event: event, host: host)
                                          : R.current(leg, event: event, host: host))
        } else {
            current = .unavailable(R.Words.inPlayUnavailable)
        }
        return ExactScoreMapOriginal10868(
            id: leg.id,
            label: leg.label,
            placement: placement,
            pregame: pregame(R.pregame(leg, event: event, host: host)),
            current: current,
            result: phase == .before ? .unconfirmed(R.Words.resultUnavailable) : result(R.result(leg)))
    }

    /// A listed original the payload no longer serves: its identity and the
    /// owner's held label, no chance, no current reading, no result. Its
    /// pre-match chance is unavailable — the payload's silence is not the
    /// producer's statement that none was recorded.
    static func held(_ listed: Descriptor.Original) -> ExactScoreMapOriginal10868 {
        ExactScoreMapOriginal10868(
            id: listed.outcomeIDs.map(String.init).joined(separator: "+"),
            label: listed.label,
            placement: listed.placement,
            pregame: .unavailable(R.Words.preMatchUnavailable),
            current: .unavailable(R.Words.inPlayUnavailable),
            result: .unconfirmed(R.Words.resultUnavailable))
    }

    static func observation(_ o: R.Observation) -> ExactScoreMapObservation10868 {
        ExactScoreMapObservation10868(probability: o.probability, text: o.text, detail: o.detail)
    }

    static func pregame(_ pregame: R.Pregame) -> ExactScoreMapPregame10868 {
        switch pregame {
        case .value(let o): .recorded(observation(o))
        case .missing(let words): .unavailable(words)
        }
    }

    static func current(_ current: R.Current) -> ExactScoreMapCurrent10868 {
        switch current {
        case .recorded(let o): .recorded(observation(o))
        case .withheld(let words): .withheld(words)
        case .unavailable(let words): .unavailable(words)
        }
    }

    static func result(_ result: R.Result) -> ExactScoreMapResult10868 {
        switch result {
        case .won(let words): .won(words)
        case .lost(let words): .lost(words)
        case .unconfirmed(let words): .unconfirmed(words)
        }
    }

    // MARK: - Scale and actual

    /// The owner's bound with ticks at 0, half and the bound. A bound the leaf
    /// cannot use gets no ticks, and the leaf shades nothing.
    static func scale(_ upper: Double) -> ExactScoreMapScale10868 {
        guard upper.isFinite, upper > 0, upper <= 1 else {
            return ExactScoreMapScale10868(lower: 0, upper: upper, ticks: [])
        }
        let ticks = [0, upper / 2, upper].map { ExactScoreMapTick10868(value: $0, text: scaleWords($0)) }
        return ExactScoreMapScale10868(lower: 0, upper: upper, ticks: ticks)
    }

    /// Scale words, not chances — so not through `formatProbability`, whose
    /// "<1%" would misname the 0 tick. "0%", "5%", "7.5%".
    static func scaleWords(_ value: Double) -> String {
        let percent = value * 100
        let whole = percent.rounded()
        if abs(percent - whole) < 0.000_001 { return "\(Int(whole))%" }
        return "\((percent * 10).rounded() / 10)%"
    }

    /// The full match's score once play has started, dated by the producer's own
    /// clock during play; nil before kickoff or without both scores.
    static func actual(_ event: EventDetail, phase: SoccerEventPagePhase10868, host: R.Host) -> ExactScoreMapActual10868? {
        guard phase != .before, let goals = R.goals(event) else { return nil }
        let names = SoccerMatchPageAdapter10868.names(event)
        let pair = "\(names.home) \(goals.home)–\(goals.away) \(names.away)"
        if phase == .final { return ExactScoreMapActual10868(title: Words.finalScore, text: pair) }
        let clock = goals.observedAt.map { "\(Words.observed) \(SoccerMatchPageAdapter10868.clockWords($0, host: host.words))" }
        return ExactScoreMapActual10868(title: Words.scoreSoFar,
                                        text: SoccerMatchPageAdapter10868.joined([pair, clock]) ?? pair)
    }
}
