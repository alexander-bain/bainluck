import Combine
import Foundation

// MARK: - Ruling 295: A — My Stuff Worth Landing On (#11934)
//
// Section order:
// 1. Live now
// 2. Next for you
// 3. Moved since your last visit
// 4. From Discover (2–3 cards + link to all of Discover)
//
// Strictly zero model-written text in 1.0.8: every label, movement line, and card
// uses deterministic numbers and titles only.

nonisolated struct MyStuffMarketItem295A: Identifiable, Sendable {
    let id: String
    let marketId: Int
    let marketTitle: String
    let outcomeLabel: String
    let subjectName: String?
    let logoUrl: String?
    let primaryColor: String?
    let probability: Double
    let changePoints: Int?
    let movementNote: String?
    let sourceMark: SourceMark?
}

nonisolated struct MyStuffMovedEntry295A: Identifiable, Sendable {
    enum Payload: Sendable {
        case event(FeedEventData, awayVerified: Bool)
        case market(MyStuffMarketItem295A)
    }

    let id: String
    let movementSummary: String
    let magnitudePoints: Int
    var isFinishedResult: Bool = false
    let payload: Payload
}

/// On-device visit ledger so "Moved since your last visit" compares current numbers
/// against what the reader saw on their previous visit, formatted strictly in points.
enum MyStuffVisitLedger295A {
    static let previousVisitPrefName = "bainluck_mystuff_visit_previous"
    static let workingVisitPrefName = "bainluck_mystuff_visit_working"

    static func loadPreviousSnapshot(defaults: UserDefaults = .standard) -> [String: Double] {
        guard let data = defaults.data(forKey: previousVisitPrefName),
              let dict = try? JSONDecoder().decode([String: Double].self, from: data) else {
            return [:]
        }
        return dict
    }

    /// Promotes the prior session's working snapshot into `previousSnapshot` at the start of a new session.
    static func rotateSessionIfNeeded(defaults: UserDefaults = .standard) {
        if let working = defaults.data(forKey: workingVisitPrefName) {
            defaults.set(working, forKey: previousVisitPrefName)
        }
    }

    static func recordObservedReadings(_ readings: [String: Double], defaults: UserDefaults = .standard) {
        guard !readings.isEmpty else { return }
        var merged = loadWorkingSnapshot(defaults: defaults)
        for (k, v) in readings where v.isFinite {
            merged[k] = v
        }
        if let encoded = try? JSONEncoder().encode(merged) {
            defaults.set(encoded, forKey: workingVisitPrefName)
        }
    }

    private static func loadWorkingSnapshot(defaults: UserDefaults) -> [String: Double] {
        guard let data = defaults.data(forKey: workingVisitPrefName),
              let dict = try? JSONDecoder().decode([String: Double].self, from: data) else {
            return [:]
        }
        return dict
    }

    enum Timeframe: Sendable, Equatable {
        case sinceLastVisit
        case sincePregame
        case sinceLastUpdate
        case last24Hours

        var suffix: String {
            switch self {
            case .sinceLastVisit: return "since your last visit"
            case .sincePregame: return "since pregame"
            case .sinceLastUpdate: return "since last update"
            case .last24Hours: return "in the last 24 hours"
            }
        }
    }

    static func formatPointMove(
        deltaProbability: Double,
        timeframe: Timeframe
    ) -> (points: Int, text: String)? {
        let pts = Int((deltaProbability * 100.0).rounded())
        let absPts = abs(pts)
        guard absPts >= 2 else { return nil }
        let direction = pts > 0 ? "Up" : "Down"
        let noun = absPts == 1 ? "point" : "points"
        return (absPts, "\(direction) \(absPts) \(noun) \(timeframe.suffix)")
    }

    static func formatPointMove(deltaProbability: Double, sinceLastVisit: Bool) -> (points: Int, text: String)? {
        formatPointMove(deltaProbability: deltaProbability, timeframe: sinceLastVisit ? .sinceLastVisit : .sinceLastUpdate)
    }
}

private let myStuffLeagueSlugToSportKey295A: [String: String] = [
    "nba": "basketball_nba",
    "nfl": "americanfootball_nfl",
    "mlb": "baseball_mlb",
    "nhl": "icehockey_nhl",
    "wnba": "basketball_wnba",
    "ncaa-basketball": "basketball_ncaab",
    "ncaa-women-basketball": "basketball_wncaab",
    "ncaa-football": "americanfootball_ncaaf",
    "epl": "soccer_epl",
    "mls": "soccer_usa_mls",
    "la-liga": "soccer_spain_la_liga",
    "champions-league": "soccer_uefa_champs_league",
    "bundesliga": "soccer_germany_bundesliga",
    "golf": "golf",
]

@MainActor
final class MyStuffLandingViewModel295A: ObservableObject {
    /// Max concurrent team/league/set page requests per refresh so opening My Stuff
    /// never fires eight heavy `/api/teams/{slug}` reads onto the server at once (#13573).
    nonisolated static let maxConcurrentSubjectHydrations = 2

    struct PreloadedSnapshot: Sendable {
        var liveEvents: [(event: FeedEventData, awayVerified: Bool)] = []
        var nextEvents: [(event: FeedEventData, awayVerified: Bool)] = []
        var nextMarkets: [MyStuffMarketItem295A] = []
        var movedEntries: [MyStuffMovedEntry295A] = []
        var discoverItems: [FeedItem] = []
        var loadFailed: Bool = false
        var hydratingRemainingCount: Int = 0
        var teamFuturesFailed: Bool = false
        var teamFuturesRetrying: Bool = false
    }

    struct HydratedSubjectPack: Sendable {
        var events: [(event: FeedEventData, awayVerified: Bool)] = []
        var markets: [MyStuffMarketItem295A] = []
        var didFail: Bool = false
    }

    typealias SubjectHydrator = @Sendable ([FollowedSubject295A]) async -> [HydratedSubjectPack]
    typealias SingleSubjectHydrator = @Sendable (FollowedSubject295A) async -> HydratedSubjectPack
    typealias DiscoverFetcher = @Sendable () async throws -> FeedResponse

    @Published private(set) var liveEvents: [(event: FeedEventData, awayVerified: Bool)] = []
    @Published private(set) var nextEvents: [(event: FeedEventData, awayVerified: Bool)] = []
    @Published private(set) var nextMarkets: [MyStuffMarketItem295A] = []
    @Published private(set) var movedEntries: [MyStuffMovedEntry295A] = []
    @Published private(set) var discoverItems: [FeedItem] = []
    @Published private(set) var loading: Bool = false
    @Published private(set) var loadFailed: Bool = false
    @Published private(set) var hydratingRemainingCount: Int = 0
    @Published private(set) var teamFuturesFailed: Bool = false
    @Published private(set) var teamFuturesRetrying: Bool = false

    private let defaults: UserDefaults
    private let isPreloaded: Bool
    private let customBatchHydrator: SubjectHydrator?
    private let singleSubjectHydrator: SingleSubjectHydrator
    private let discoverFetcher: DiscoverFetcher
    private var hasRotatedSession = false

    init(
        defaults: UserDefaults = .standard,
        preloaded: PreloadedSnapshot? = nil,
        subjectHydrator: SubjectHydrator? = nil,
        singleSubjectHydrator: SingleSubjectHydrator? = nil,
        discoverFetcher: DiscoverFetcher? = nil
    ) {
        self.defaults = defaults
        self.customBatchHydrator = subjectHydrator
        self.singleSubjectHydrator = singleSubjectHydrator ?? { subject in
            await Self.fetchOneSubject(subject)
        }
        self.discoverFetcher = discoverFetcher ?? {
            try await APIClient.shared.fetchFeed(limit: 12, mode: "discover")
        }
        if let preloaded {
            self.isPreloaded = true
            self.liveEvents = preloaded.liveEvents
            self.nextEvents = preloaded.nextEvents
            self.nextMarkets = preloaded.nextMarkets
            self.movedEntries = preloaded.movedEntries
            self.discoverItems = Self.stripModelWrittenText(preloaded.discoverItems, limit: 3)
            self.loading = false
            self.loadFailed = preloaded.loadFailed
            self.hydratingRemainingCount = preloaded.hydratingRemainingCount
            self.teamFuturesFailed = preloaded.teamFuturesFailed
            self.teamFuturesRetrying = preloaded.teamFuturesRetrying
        } else {
            self.isPreloaded = false
        }
    }

    /// Seeds sections for unit tests exercising refresh failure preservation.
    func seedSectionsForTesting(_ snapshot: PreloadedSnapshot) {
        self.liveEvents = snapshot.liveEvents
        self.nextEvents = snapshot.nextEvents
        self.nextMarkets = snapshot.nextMarkets
        self.movedEntries = snapshot.movedEntries
        self.discoverItems = Self.stripModelWrittenText(snapshot.discoverItems, limit: 3)
        self.loadFailed = snapshot.loadFailed
        self.hydratingRemainingCount = snapshot.hydratingRemainingCount
        self.teamFuturesFailed = snapshot.teamFuturesFailed
        self.teamFuturesRetrying = snapshot.teamFuturesRetrying
    }

    /// Computes the moved-game banner line from the exact `CompactGameCard12616.currentOddsForCard`
    /// reading shown on `EventCardView`:
    /// - Skips draw-capable sports (a negative home delta does not imply the away side rose).
    /// - Uses `.sinceLastVisit` when `priorHomeProbability` is recorded in the visit ledger,
    ///   and `.sincePregame` ONLY when `event.prematchOdds` carries a reading pinned at the
    ///   start of the game (`PREMATCH_PRIOR_SQL` along Kalshi → Polymarket → sportsbooks).
    /// - Never falls back to `event.openingOdds` (the first/running stored sportsbook column
    ///   before any pregame pin) — with neither a last-visit reading nor `prematchOdds`, returns nil.
    /// - Attributes a negative home delta to the away team ONLY when the away reading is
    ///   present on `currentOddsForCard` and verified (`!currentAwayIsWithheld`).
    nonisolated static func movedEventSummary(
        for event: FeedEventData,
        awayVerified: Bool,
        priorHomeProbability: Double?
    ) -> (points: Int, summary: String)? {
        guard !DrawPricedWinner.sportPricesADraw(event.sport) else { return nil }
        guard let cardOdds = CompactGameCard12616.currentOddsForCard(event),
              let currentHome = cardOdds.homeProbability else {
            return nil
        }

        let baseHome: Double
        let timeframe: MyStuffVisitLedger295A.Timeframe
        if let prior = priorHomeProbability {
            baseHome = prior
            timeframe = .sinceLastVisit
        } else if let prematchHome = event.prematchOdds?.homeProbability {
            baseHome = prematchHome
            timeframe = .sincePregame
        } else {
            return nil
        }

        let delta = currentHome - baseHome
        let short = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)

        if delta >= 0 {
            guard let move = MyStuffVisitLedger295A.formatPointMove(deltaProbability: delta, timeframe: timeframe),
                  move.points >= 4 else {
                return nil
            }
            return (move.points, "\(short.home) \(move.text.lowercased())")
        }

        let currentAwayIsWithheld = cardOdds.awayProbability == nil
            || (DrawPricedWinner.sportPricesADraw(event.sport) && !awayVerified)
        guard !currentAwayIsWithheld, cardOdds.awayProbability != nil else {
            return nil
        }
        guard let awayMove = MyStuffVisitLedger295A.formatPointMove(deltaProbability: -delta, timeframe: timeframe),
              awayMove.points >= 4 else {
            return nil
        }
        return (awayMove.points, "\(short.away) \(awayMove.text.lowercased())")
    }

    /// Removes all model-written narrative fields (`reason`, `headline`, `contextSummary`, `hookDescription`)
    /// and bounds "From Discover" to 2–3 cards.
    static func stripModelWrittenText(_ items: [FeedItem], limit: Int = 3) -> [FeedItem] {
        var cleaned: [FeedItem] = []
        for raw in items {
            if cleaned.count >= limit { break }
            var futures = raw.futures
            futures?.hookDescription = nil
            var event = raw.event
            if event != nil {
                // Keep structured game data only; omit LLM/editorial narrative sentences.
                event = FeedEventData(
                    id: event!.id,
                    externalId: event!.externalId,
                    sport: event!.sport,
                    sportName: event!.sportName,
                    homeTeam: event!.homeTeam,
                    awayTeam: event!.awayTeam,
                    commenceTime: event!.commenceTime,
                    startIsTbd: event!.startIsTbd,
                    status: event!.status,
                    homeScore: event!.homeScore,
                    awayScore: event!.awayScore,
                    scoreSourceUnavailable: event!.scoreSourceUnavailable,
                    blendFoldRevision: event!.blendFoldRevision,
                    heroProbabilitySource: event!.heroProbabilitySource,
                    heroProbabilityObservedAt: event!.heroProbabilityObservedAt,
                    currentOdds: event!.currentOdds,
                    openingOdds: event!.openingOdds,
                    prematchOdds: event!.prematchOdds,
                    pregameProjection: event!.pregameProjection,
                    finalScorePeriod: event!.finalScorePeriod,
                    highlight: nil,
                    homeTeamData: event!.homeTeamData,
                    awayTeamData: event!.awayTeamData,
                    metadata: event!.metadata,
                    espn: event!.espn,
                    ei: nil,
                    pulse: nil,
                    winProbabilitySources: event!.winProbabilitySources,
                    confidenceTier: event!.confidenceTier,
                    confidenceScore: event!.confidenceScore,
                    homeImageUrl: event!.homeImageUrl,
                    awayImageUrl: event!.awayImageUrl,
                    homeFlagUrl: event!.homeFlagUrl,
                    awayFlagUrl: event!.awayFlagUrl,
                    endedAt: event!.endedAt,
                    discoverMarqueeFinal: event!.discoverMarqueeFinal,
                    venueClosedNoWinner: event!.venueClosedNoWinner,
                    sourceMark: event!.sourceMark,
                    awaySourceMark: event!.awaySourceMark,
                    pregameSourceMark: event!.pregameSourceMark,
                    awayPregameSourceMark: event!.awayPregameSourceMark
                )
            }
            guard event != nil || futures != nil else { continue }
            cleaned.append(
                FeedItem(
                    type: raw.type,
                    score: raw.score,
                    reason: nil,
                    headline: nil,
                    contextSummary: nil,
                    event: event,
                    futures: futures,
                    tournament: nil,
                    concept: nil,
                    bundle: nil,
                    personalized: raw.personalized,
                    baseScore: raw.baseScore,
                    multiplier: raw.multiplier,
                    personalizationReasons: nil
                )
            )
        }
        return cleaned
    }

    private struct RefreshAccumulator295A {
        let priorSnapshot: [String: Double]
        var seenEventIds: Set<Int> = []
        var collectedEvents: [(event: FeedEventData, awayVerified: Bool)] = []
        var seenMarketKeys: Set<String> = []
        var collectedMarkets: [MyStuffMarketItem295A] = []
        var newReadings: [String: Double] = [:]

        mutating func appendEvent(_ ev: FeedEventData, awayVerified: Bool = false) {
            guard seenEventIds.insert(ev.id).inserted else { return }
            let sanitized = MyStuffLandingViewModel295A.stripEventNarrative(ev)
            collectedEvents.append((sanitized, awayVerified))
            if EventState.canStillBeGraded(sanitized.status, commenceTime: sanitized.commenceTime?.asDate),
               let hp = CompactGameCard12616.currentOddsForCard(sanitized)?.homeProbability {
                newReadings["event:\(sanitized.id)"] = hp
            }
        }

        mutating func appendMarket(_ m: MyStuffMarketItem295A) {
            guard seenMarketKeys.insert(m.id).inserted else { return }
            collectedMarkets.append(m)
            newReadings["market:\(m.id)"] = m.probability
        }

        mutating func mergePack(_ pack: HydratedSubjectPack) {
            for (ev, verified) in pack.events {
                appendEvent(ev, awayVerified: verified)
            }
            for rawMarket in pack.markets {
                let prior = priorSnapshot["market:\(rawMarket.id)"]
                var item = rawMarket
                if let prior,
                   let move = MyStuffVisitLedger295A.formatPointMove(
                       deltaProbability: rawMarket.probability - prior,
                       sinceLastVisit: true
                   ) {
                    item = MyStuffMarketItem295A(
                        id: rawMarket.id,
                        marketId: rawMarket.marketId,
                        marketTitle: rawMarket.marketTitle,
                        outcomeLabel: rawMarket.outcomeLabel,
                        subjectName: rawMarket.subjectName,
                        logoUrl: rawMarket.logoUrl,
                        primaryColor: rawMarket.primaryColor,
                        probability: rawMarket.probability,
                        changePoints: move.points,
                        movementNote: move.text,
                        sourceMark: rawMarket.sourceMark
                    )
                }
                appendMarket(item)
            }
        }

        mutating func mergeBaseline(
            savedPins: [SavedPin],
            pinContent: [SavedPin: SavedPinContent],
            signedInItems: [FeedItem],
            signedInTeamFutures: TeamFuturesResponse?
        ) {
            for pin in savedPins {
                switch pinContent[pin] {
                case .event(let e) where pin.type == "event":
                    appendEvent(e)
                case .market(let f) where pin.type == "future":
                    if let top = f.topOutcomes?.first, let prob = top.probability {
                        let key = "\(f.id):\(top.name.lowercased())"
                        let delta24 = top.movement
                        let prior = priorSnapshot["market:\(key)"]
                        let moveInfo: (points: Int, text: String)? = {
                            if let prior {
                                return MyStuffVisitLedger295A.formatPointMove(deltaProbability: prob - prior, sinceLastVisit: true)
                            }
                            if let delta24 {
                                return MyStuffVisitLedger295A.formatPointMove(deltaProbability: delta24, sinceLastVisit: false)
                            }
                            return nil
                        }()
                        appendMarket(
                            MyStuffMarketItem295A(
                                id: key,
                                marketId: f.id,
                                marketTitle: f.name,
                                outcomeLabel: top.name,
                                subjectName: nil,
                                logoUrl: nil,
                                primaryColor: nil,
                                probability: prob,
                                changePoints: moveInfo?.points,
                                movementNote: moveInfo?.text,
                                sourceMark: top.sourceMark ?? f.sourceMark
                            )
                        )
                    }
                default:
                    break
                }
            }

            for item in signedInItems {
                if item.type == "event", let ev = item.event {
                    appendEvent(ev)
                } else if item.type == "futures", let f = item.futures,
                          let top = (f.matchedOutcomes?.first.map { ($0.name, $0.probability, $0.movement) })
                            ?? (f.topOutcomes?.first.map { ($0.name, $0.probability, $0.movement) }),
                          let prob = top.1 {
                    let key = "\(f.id):\(top.0.lowercased())"
                    let prior = priorSnapshot["market:\(key)"]
                    let move = prior != nil
                        ? MyStuffVisitLedger295A.formatPointMove(deltaProbability: prob - prior!, sinceLastVisit: true)
                        : top.2.flatMap { MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, sinceLastVisit: false) }
                    appendMarket(
                        MyStuffMarketItem295A(
                            id: key,
                            marketId: f.id,
                            marketTitle: f.name,
                            outcomeLabel: top.0,
                            subjectName: nil,
                            logoUrl: nil,
                            primaryColor: nil,
                            probability: prob,
                            changePoints: move?.points,
                            movementNote: move?.text,
                            sourceMark: f.sourceMark
                        )
                    )
                }
            }

            if let tf = signedInTeamFutures {
                for item in tf.items.prefix(12) {
                    guard let prob = item.probability, prob > 0 else { continue }
                    let key = "\(item.marketId):\(item.outcomeName.lowercased())"
                    let prior = priorSnapshot["market:\(key)"]
                    let move = prior != nil
                        ? MyStuffVisitLedger295A.formatPointMove(deltaProbability: prob - prior!, sinceLastVisit: true)
                        : item.probabilityChange24h.flatMap {
                            MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, sinceLastVisit: false)
                        }
                    appendMarket(
                        MyStuffMarketItem295A(
                            id: key,
                            marketId: item.marketId,
                            marketTitle: MyStuffLandingViewModel295A.cleanMarketTitle(item.marketName),
                            outcomeLabel: item.outcomeName,
                            subjectName: item.matchedTeam?.name,
                            logoUrl: item.matchedTeam?.logoSmall,
                            primaryColor: item.matchedTeam?.primaryColor,
                            probability: prob,
                            changePoints: move?.points,
                            movementNote: move?.text,
                            sourceMark: item.sourceMark
                        )
                    )
                }
            }
        }
    }

    private struct PartitionedSections295A {
        let live: [(event: FeedEventData, awayVerified: Bool)]
        let nextEvents: [(event: FeedEventData, awayVerified: Bool)]
        let nextMarkets: [MyStuffMarketItem295A]
        let moved: [MyStuffMovedEntry295A]
        let discover: [FeedItem]

        var hasFollowedContent: Bool {
            !live.isEmpty || !nextEvents.isEmpty || !nextMarkets.isEmpty || !moved.isEmpty
        }

        var hasAnyContent: Bool {
            hasFollowedContent || !discover.isEmpty
        }
    }

    private static func buildPartitionedSections(
        from acc: RefreshAccumulator295A,
        discoverFeed: FeedResponse?
    ) -> PartitionedSections295A {
        // 1. Live now
        let live = acc.collectedEvents.filter { pair in EventState.section(of: pair.event) == .live }

        // 2. Next for you (upcoming games chronologically ascending + top active followed markets)
        let upcomingSorted = acc.collectedEvents
            .filter { pair in EventState.section(of: pair.event) == .upcoming }
            .sorted { lhs, rhs in
                switch (lhs.event.commenceTime?.asDate, rhs.event.commenceTime?.asDate) {
                case let (l?, r?): return l < r
                case (_?, nil): return true
                case (nil, _?): return false
                case (nil, nil): return lhs.event.id < rhs.event.id
                }
            }

        // 3. Moved since your last visit (events & markets with notable movement + recent finals)
        var moved: [MyStuffMovedEntry295A] = []

        for pair in upcomingSorted {
            let ev = pair.event
            let prior = acc.priorSnapshot["event:\(ev.id)"]
            if let eventMove = Self.movedEventSummary(
                for: ev,
                awayVerified: pair.awayVerified,
                priorHomeProbability: prior
            ) {
                moved.append(
                    MyStuffMovedEntry295A(
                        id: "moved-event-\(ev.id)",
                        movementSummary: eventMove.summary,
                        magnitudePoints: eventMove.points,
                        payload: .event(ev, awayVerified: pair.awayVerified)
                    )
                )
            }
        }

        let recentFinals = acc.collectedEvents
            .filter { pair in EventState.section(of: pair.event) == .finished }
            .sorted { lhs, rhs in
                (lhs.event.commenceTime?.asDate ?? .distantPast) > (rhs.event.commenceTime?.asDate ?? .distantPast)
            }
            .prefix(2)

        for pair in recentFinals {
            moved.append(
                MyStuffMovedEntry295A(
                    id: "moved-final-\(pair.event.id)",
                    movementSummary: "Finished",
                    magnitudePoints: 0,
                    isFinishedResult: true,
                    payload: .event(pair.event, awayVerified: pair.awayVerified)
                )
            )
        }

        var unmovedMarkets: [MyStuffMarketItem295A] = []
        for market in acc.collectedMarkets {
            if let note = market.movementNote, let pts = market.changePoints, pts >= 2 {
                moved.append(
                    MyStuffMovedEntry295A(
                        id: "moved-market-\(market.id)",
                        movementSummary: note,
                        magnitudePoints: pts,
                        payload: .market(market)
                    )
                )
            } else {
                unmovedMarkets.append(market)
            }
        }

        moved.sort { lhs, rhs in
            if lhs.isFinishedResult != rhs.isFinishedResult {
                return !lhs.isFinishedResult
            }
            return lhs.magnitudePoints > rhs.magnitudePoints
        }
        let boundedMoved = Array(moved.prefix(6))

        let movedEventIds = Set(boundedMoved.compactMap { entry -> Int? in
            if case .event(let ev, _) = entry.payload { return ev.id }
            return nil
        })

        let nextFilteredEvents = upcomingSorted.filter { !movedEventIds.contains($0.event.id) }
        let boundedNextEvents = Array(nextFilteredEvents.prefix(8))
        let boundedNextMarkets = Array(unmovedMarkets.prefix(6))

        // 4. From Discover (2–3 cards not already shown above, zero model-written text)
        let shownEventIds = Set(live.map(\.event.id) + boundedNextEvents.map(\.event.id)).union(movedEventIds)
        let shownMarketIds = Set(boundedNextMarkets.map(\.marketId) + boundedMoved.compactMap { entry -> Int? in
            if case .market(let m) = entry.payload { return m.marketId }
            return nil
        })

        let rawDiscover = (discoverFeed?.items ?? []).filter { item in
            if let ev = item.event {
                return !shownEventIds.contains(ev.id)
            }
            if let f = item.futures {
                return !shownMarketIds.contains(f.id)
            }
            return false
        }

        let cleanedDiscover = Self.stripModelWrittenText(rawDiscover, limit: 3)
        return PartitionedSections295A(
            live: live,
            nextEvents: boundedNextEvents,
            nextMarkets: boundedNextMarkets,
            moved: boundedMoved,
            discover: cleanedDiscover
        )
    }

    private func applyStreamingPartition(
        _ partition: PartitionedSections295A,
        discoverFailed: Bool,
        discoverSettled: Bool,
        preserveExistingFollowedIfEmpty: Bool
    ) {
        if partition.hasFollowedContent || !partition.discover.isEmpty {
            loadFailed = false
            loading = false
        }
        if !preserveExistingFollowedIfEmpty || partition.hasFollowedContent {
            liveEvents = partition.live
            nextEvents = partition.nextEvents
            nextMarkets = partition.nextMarkets
            movedEntries = partition.moved
        }
        if discoverSettled && (!discoverFailed || discoverItems.isEmpty) {
            discoverItems = partition.discover
        }
    }

    func refresh(
        followedSubjects: [FollowedSubject295A],
        savedPins: [SavedPin],
        pinContent: [SavedPin: SavedPinContent],
        signedInItems: [FeedItem],
        signedInTeamFutures: TeamFuturesResponse?,
        signedInTeamFeedFailed: Bool = false,
        signedInTeamFuturesFailed: Bool = false,
        signedInTeamFuturesLoading: Bool = false
    ) async {
        guard !isPreloaded else { return }

        teamFuturesRetrying = signedInTeamFuturesLoading && signedInTeamFutures == nil
        if signedInTeamFutures != nil {
            teamFuturesFailed = false
        } else if signedInTeamFuturesFailed {
            teamFuturesFailed = true
        }

        if !hasRotatedSession {
            MyStuffVisitLedger295A.rotateSessionIfNeeded(defaults: defaults)
            hasRotatedSession = true
        }

        if liveEvents.isEmpty && nextEvents.isEmpty && nextMarkets.isEmpty && movedEntries.isEmpty {
            loading = true
        }

        let hadExistingSections = !liveEvents.isEmpty
            || !nextEvents.isEmpty
            || !nextMarkets.isEmpty
            || !movedEntries.isEmpty
            || !discoverItems.isEmpty

        let priorSnapshot = MyStuffVisitLedger295A.loadPreviousSnapshot(defaults: defaults)
        let subjectsToHydrate = Array(followedSubjects.prefix(8))
        hydratingRemainingCount = subjectsToHydrate.count

        // Publish locally available pins and already-loaded signed-in items immediately
        // so slow `/api/teams/{slug}` responses never hold up what is already on hand.
        var baselineAcc = RefreshAccumulator295A(priorSnapshot: priorSnapshot)
        baselineAcc.mergeBaseline(
            savedPins: savedPins,
            pinContent: pinContent,
            signedInItems: signedInItems,
            signedInTeamFutures: signedInTeamFutures
        )
        let baselinePartition = Self.buildPartitionedSections(from: baselineAcc, discoverFeed: nil)
        if baselinePartition.hasFollowedContent {
            applyStreamingPartition(
                baselinePartition,
                discoverFailed: false,
                discoverSettled: false,
                preserveExistingFollowedIfEmpty: hadExistingSections
            )
        }

        let feedFetcher = self.discoverFetcher
        var discoverFeed: FeedResponse?
        var discoverFailed = false
        var completedPacks: [Int: HydratedSubjectPack] = [:]

        if let customBatchHydrator {
            async let hydratedSubjectsTask = customBatchHydrator(subjectsToHydrate)
            async let discoverFeedResultTask: (FeedResponse?, Bool) = {
                do {
                    return (try await feedFetcher(), false)
                } catch {
                    return (nil, true)
                }
            }()
            let hydrated = await hydratedSubjectsTask
            for (idx, pack) in hydrated.enumerated() {
                completedPacks[idx] = pack
            }
            (discoverFeed, discoverFailed) = await discoverFeedResultTask
        } else {
            enum StreamEvent: Sendable {
                case subject(Int, HydratedSubjectPack)
                case discover(FeedResponse?, Bool)
            }
            let singleHydrator = self.singleSubjectHydrator
            var remainingSubjects = subjectsToHydrate.count
            var nextSubjectIndex = 0
            let maxInFlight = Self.maxConcurrentSubjectHydrations

            await withTaskGroup(of: StreamEvent.self) { group in
                group.addTask {
                    do {
                        return .discover(try await feedFetcher(), false)
                    } catch {
                        return .discover(nil, true)
                    }
                }

                let initialBatch = min(maxInFlight, subjectsToHydrate.count)
                while nextSubjectIndex < initialBatch {
                    let idx = nextSubjectIndex
                    let subject = subjectsToHydrate[idx]
                    nextSubjectIndex += 1
                    group.addTask {
                        .subject(idx, await singleHydrator(subject))
                    }
                }

                for await event in group {
                    switch event {
                    case .discover(let feed, let didFail):
                        discoverFeed = feed
                        discoverFailed = didFail
                    case .subject(let idx, let pack):
                        completedPacks[idx] = pack
                        remainingSubjects = max(0, remainingSubjects - 1)
                        hydratingRemainingCount = remainingSubjects
                        if nextSubjectIndex < subjectsToHydrate.count {
                            let nextIdx = nextSubjectIndex
                            let nextSubject = subjectsToHydrate[nextIdx]
                            nextSubjectIndex += 1
                            group.addTask {
                                .subject(nextIdx, await singleHydrator(nextSubject))
                            }
                        }
                    }

                    var stepAcc = baselineAcc
                    for idx in completedPacks.keys.sorted() {
                        if let pack = completedPacks[idx] {
                            stepAcc.mergePack(pack)
                        }
                    }
                    let stepPartition = Self.buildPartitionedSections(from: stepAcc, discoverFeed: discoverFeed)
                    if stepPartition.hasAnyContent {
                        applyStreamingPartition(
                            stepPartition,
                            discoverFailed: discoverFailed,
                            discoverSettled: discoverFeed != nil || discoverFailed,
                            preserveExistingFollowedIfEmpty: hadExistingSections
                        )
                    }
                }
            }
        }

        hydratingRemainingCount = 0

        var finalAcc = baselineAcc
        var anyHydrationFailed = false
        for idx in 0..<subjectsToHydrate.count {
            if let pack = completedPacks[idx] {
                if pack.didFail { anyHydrationFailed = true }
                finalAcc.mergePack(pack)
            }
        }

        MyStuffVisitLedger295A.recordObservedReadings(finalAcc.newReadings, defaults: defaults)
        let finalPartition = Self.buildPartitionedSections(from: finalAcc, discoverFeed: discoverFeed)
        let newFollowedSectionsEmpty = !finalPartition.hasFollowedContent
        let teamFuturesDidFail = signedInTeamFuturesFailed && signedInTeamFutures == nil
        teamFuturesFailed = teamFuturesDidFail
        teamFuturesRetrying = signedInTeamFuturesLoading && signedInTeamFutures == nil

        if (anyHydrationFailed || discoverFailed || signedInTeamFeedFailed)
            && newFollowedSectionsEmpty
            && finalPartition.discover.isEmpty {
            loadFailed = true
            loading = false
            return
        }

        if (anyHydrationFailed || signedInTeamFeedFailed)
            && newFollowedSectionsEmpty
            && (!subjectsToHydrate.isEmpty || signedInTeamFeedFailed) {
            loadFailed = true
            if !hadExistingSections {
                discoverItems = finalPartition.discover
            }
            loading = false
            return
        }

        loadFailed = false
        liveEvents = finalPartition.live
        nextEvents = finalPartition.nextEvents
        nextMarkets = finalPartition.nextMarkets
        movedEntries = finalPartition.moved
        if !discoverFailed || discoverItems.isEmpty {
            discoverItems = finalPartition.discover
        }
        loading = false
    }

    private static func stripEventNarrative(_ ev: FeedEventData) -> FeedEventData {
        FeedEventData(
            id: ev.id,
            externalId: ev.externalId,
            sport: ev.sport,
            sportName: ev.sportName,
            homeTeam: ev.homeTeam,
            awayTeam: ev.awayTeam,
            commenceTime: ev.commenceTime,
            startIsTbd: ev.startIsTbd,
            status: ev.status,
            homeScore: ev.homeScore,
            awayScore: ev.awayScore,
            scoreSourceUnavailable: ev.scoreSourceUnavailable,
            blendFoldRevision: ev.blendFoldRevision,
            heroProbabilitySource: ev.heroProbabilitySource,
            heroProbabilityObservedAt: ev.heroProbabilityObservedAt,
            currentOdds: ev.currentOdds,
            openingOdds: ev.openingOdds,
            prematchOdds: ev.prematchOdds,
            pregameProjection: ev.pregameProjection,
            finalScorePeriod: ev.finalScorePeriod,
            highlight: nil,
            homeTeamData: ev.homeTeamData,
            awayTeamData: ev.awayTeamData,
            metadata: ev.metadata,
            espn: ev.espn,
            ei: nil,
            pulse: nil,
            winProbabilitySources: ev.winProbabilitySources,
            confidenceTier: ev.confidenceTier,
            confidenceScore: ev.confidenceScore,
            homeImageUrl: ev.homeImageUrl,
            awayImageUrl: ev.awayImageUrl,
            homeFlagUrl: ev.homeFlagUrl,
            awayFlagUrl: ev.awayFlagUrl,
            endedAt: ev.endedAt,
            discoverMarqueeFinal: ev.discoverMarqueeFinal,
            venueClosedNoWinner: ev.venueClosedNoWinner,
            sourceMark: ev.sourceMark,
            awaySourceMark: ev.awaySourceMark,
            pregameSourceMark: ev.pregameSourceMark,
            awayPregameSourceMark: ev.awayPregameSourceMark
        )
    }

    nonisolated private static func fetchFollowedSubjects(
        _ subjects: [FollowedSubject295A]
    ) async -> [HydratedSubjectPack] {
        await withTaskGroup(of: (Int, HydratedSubjectPack).self) { group in
            var nextIdx = 0
            let initial = min(maxConcurrentSubjectHydrations, subjects.count)
            while nextIdx < initial {
                let idx = nextIdx
                let subject = subjects[idx]
                nextIdx += 1
                group.addTask {
                    (idx, await fetchOneSubject(subject))
                }
            }
            var ordered: [(Int, HydratedSubjectPack)] = []
            for await pair in group {
                ordered.append(pair)
                if nextIdx < subjects.count {
                    let idx = nextIdx
                    let subject = subjects[idx]
                    nextIdx += 1
                    group.addTask {
                        (idx, await fetchOneSubject(subject))
                    }
                }
            }
            return ordered.sorted { $0.0 < $1.0 }.map(\.1)
        }
    }

    nonisolated private static func fetchOneSubject(_ subject: FollowedSubject295A) async -> HydratedSubjectPack {
        var pack = HydratedSubjectPack()
        switch subject.kind {
        case .team:
            let identifier: String
            if !subject.slug.isEmpty {
                identifier = subject.slug
            } else if let tid = subject.teamId {
                identifier = "\(tid)"
            } else {
                return pack
            }
            let page: TeamPageResponse
            do {
                page = try await APIClient.shared.fetchTeamPage(slug: identifier)
            } catch {
                pack.didFail = true
                return pack
            }
            for ev in page.upcomingEvents {
                let converted = SearchEventCardAdapter183A.fromTeamScheduleBrief(ev, team: page.team)
                pack.events.append((converted.feedEvent, converted.awayReadingIsServerVerified))
            }
            for ev in page.recentEvents.prefix(2) {
                let converted = SearchEventCardAdapter183A.fromTeamScheduleBrief(ev, team: page.team)
                pack.events.append((converted.feedEvent, converted.awayReadingIsServerVerified))
            }
            for entry in page.championshipPath.prefix(3) {
                guard let prob = entry.probability, prob > 0, entry.state == nil else { continue }
                let move = entry.movement.flatMap {
                    MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, sinceLastVisit: false)
                }
                pack.markets.append(
                    MyStuffMarketItem295A(
                        id: "\(entry.marketId):\(page.team.slug)",
                        marketId: entry.marketId,
                        marketTitle: entry.label,
                        outcomeLabel: page.team.name,
                        subjectName: page.team.name,
                        logoUrl: page.team.logoSmall ?? page.team.logoLarge,
                        primaryColor: page.team.primaryColor,
                        probability: prob,
                        changePoints: move?.points,
                        movementNote: move?.text,
                        sourceMark: entry.sourceMark
                    )
                )
            }
            for f in page.futures.prefix(4) {
                guard let prob = f.probability, prob > 0 else { continue }
                let move = f.probabilityChange24h.flatMap {
                    MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, sinceLastVisit: false)
                }
                pack.markets.append(
                    MyStuffMarketItem295A(
                        id: "\(f.marketId):\(f.outcomeName.lowercased())",
                        marketId: f.marketId,
                        marketTitle: cleanMarketTitle(f.marketName),
                        outcomeLabel: f.outcomeName,
                        subjectName: page.team.name,
                        logoUrl: page.team.logoSmall ?? page.team.logoLarge,
                        primaryColor: page.team.primaryColor,
                        probability: prob,
                        changePoints: move?.points,
                        movementNote: move?.text,
                        sourceMark: f.sourceMark
                    )
                )
            }

        case .league:
            let sportKey = subject.sportKey.flatMap { $0.isEmpty ? nil : $0 }
                ?? myStuffLeagueSlugToSportKey295A[subject.slug]
                ?? subject.slug
            var leagueCallSucceeded = false
            if let markets = try? await APIClient.shared.fetchLeagueMarkets(sportKey: sportKey) {
                leagueCallSucceeded = true
                for ev in markets.allGames.prefix(6) {
                    pack.events.append((ev, false))
                }
            }
            if let grid = try? await APIClient.shared.fetchChampionshipGrid(slug: subject.slug) {
                leagueCallSucceeded = true
                if let champMarketId = grid.championshipMarketId {
                    for mover in grid.movers.prefix(3) {
                        guard let move = MyStuffVisitLedger295A.formatPointMove(
                            deltaProbability: mover.change24H,
                            sinceLastVisit: false
                        ) else { continue }
                        let matchingTeam = grid.teams.first { $0.name == mover.name }
                        let cellProb = matchingTeam?.cells[mover.column]?.mergedProbability
                        guard let prob = cellProb, prob > 0 else { continue }
                        pack.markets.append(
                            MyStuffMarketItem295A(
                                id: "\(champMarketId):\(mover.name.lowercased()):\(mover.column)",
                                marketId: champMarketId,
                                marketTitle: "\(grid.name) · \(mover.column.replacingOccurrences(of: "_", with: " ").capitalized)",
                                outcomeLabel: mover.name,
                                subjectName: grid.name,
                                logoUrl: mover.logoUrl,
                                primaryColor: mover.primaryColor,
                                probability: prob,
                                changePoints: move.points,
                                movementNote: move.text,
                                sourceMark: nil
                            )
                        )
                    }
                }
            }
            if !leagueCallSucceeded {
                pack.didFail = true
            }

        case .set:
            switch subject.setKind ?? .container {
            case .container:
                let hub: ContainerHubResponse
                do {
                    hub = try await APIClient.shared.fetchContainerHub(slug: subject.slug)
                } catch {
                    pack.didFail = true
                    return pack
                }
                guard hub.state == .published else {
                    return pack
                }
                for section in hub.sections {
                    for member in section.members.prefix(4) {
                        switch member.card {
                        case .event(let ev):
                            pack.events.append((ev, false))
                        case .question(let feed, _):
                            guard let top = feed.topOutcomes?.first, let prob = top.probability else { continue }
                            let move = top.movement.flatMap {
                                MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, sinceLastVisit: false)
                            }
                            pack.markets.append(
                                MyStuffMarketItem295A(
                                    id: "\(feed.id):\(top.name.lowercased())",
                                    marketId: feed.id,
                                    marketTitle: feed.name,
                                    outcomeLabel: top.name,
                                    subjectName: subject.name,
                                    logoUrl: nil,
                                    primaryColor: nil,
                                    probability: prob,
                                    changePoints: move?.points,
                                    movementNote: move?.text,
                                    sourceMark: top.sourceMark ?? feed.sourceMark
                                )
                            )
                        case .unsupported:
                            break
                        }
                    }
                }
            case .golfTournament:
                let detail: GolfTournamentDetailResponse
                do {
                    detail = try await APIClient.shared.fetchGolfTournament(slug: subject.slug)
                } catch {
                    pack.didFail = true
                    return pack
                }
                guard let marketId = detail.evolutionMarketId,
                      let leader = detail.golfers.first,
                      leader.probability > 0 else {
                    return pack
                }
                let prob = leader.probability
                let timeframe: MyStuffVisitLedger295A.Timeframe = (leader.movementIsDated == true) ? .last24Hours : .sinceLastUpdate
                let move = leader.movement24h.flatMap {
                    MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, timeframe: timeframe)
                }
                pack.markets.append(
                    MyStuffMarketItem295A(
                        id: "\(marketId):\(leader.name.lowercased())",
                        marketId: marketId,
                        marketTitle: subject.name,
                        outcomeLabel: leader.name,
                        subjectName: subject.name,
                        logoUrl: nil,
                        primaryColor: nil,
                        probability: prob,
                        changePoints: move?.points,
                        movementNote: move?.text,
                        sourceMark: leader.sourceMark
                    )
                )
            case .tournament, .concept:
                break
            }
        }
        return pack
    }

    nonisolated static func cleanMarketTitle(_ raw: String) -> String {
        var result = raw
        if let range = result.range(of: #"\s*Winner\s*$"#, options: .regularExpression) {
            result.removeSubrange(range)
        }
        if let range = result.range(of: #"\s*20\d{2}(-\d{2})?\s*$"#, options: .regularExpression) {
            result.removeSubrange(range)
        }
        return result.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}

extension NavigationCoordinator {
    /// Ruling 295: A — A reader who follows or pins at least one thing opens on My Stuff;
    /// a reader with nothing followed or pinned opens on Discover. Never overrides an
    /// explicit deep link (`pendingRoute` / `pendingSearchQuery`) or non-default tab.
    func applyLaunchLanding295A(
        followedCount: Int,
        pinnedCount: Int,
        hasPersistedServerFollows: Bool = false
    ) {
        guard selectedTab == .discover, pendingRoute == nil, pendingSearchQuery == nil else { return }
        selectedTab = MyStuffLandingRule295A.initialTab(
            followedCount: followedCount,
            pinnedCount: pinnedCount,
            hasPersistedServerFollows: hasPersistedServerFollows
        )
    }
}
