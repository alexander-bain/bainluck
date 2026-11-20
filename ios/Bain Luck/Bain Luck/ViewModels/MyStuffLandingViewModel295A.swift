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

    static func formatPointMove(deltaProbability: Double, sinceLastVisit: Bool) -> (points: Int, text: String)? {
        let pts = Int((deltaProbability * 100.0).rounded())
        let absPts = abs(pts)
        guard absPts >= 2 else { return nil }
        let direction = pts > 0 ? "Up" : "Down"
        let noun = absPts == 1 ? "point" : "points"
        let suffix = sinceLastVisit ? "since your last visit" : "today"
        return (absPts, "\(direction) \(absPts) \(noun) \(suffix)")
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
    struct PreloadedSnapshot: Sendable {
        var liveEvents: [(event: FeedEventData, awayVerified: Bool)] = []
        var nextEvents: [(event: FeedEventData, awayVerified: Bool)] = []
        var nextMarkets: [MyStuffMarketItem295A] = []
        var movedEntries: [MyStuffMovedEntry295A] = []
        var discoverItems: [FeedItem] = []
    }

    @Published private(set) var liveEvents: [(event: FeedEventData, awayVerified: Bool)] = []
    @Published private(set) var nextEvents: [(event: FeedEventData, awayVerified: Bool)] = []
    @Published private(set) var nextMarkets: [MyStuffMarketItem295A] = []
    @Published private(set) var movedEntries: [MyStuffMovedEntry295A] = []
    @Published private(set) var discoverItems: [FeedItem] = []
    @Published private(set) var loading: Bool = false

    private let defaults: UserDefaults
    private let isPreloaded: Bool
    private var hasRotatedSession = false

    init(
        defaults: UserDefaults = .standard,
        preloaded: PreloadedSnapshot? = nil
    ) {
        self.defaults = defaults
        if let preloaded {
            self.isPreloaded = true
            self.liveEvents = preloaded.liveEvents
            self.nextEvents = preloaded.nextEvents
            self.nextMarkets = preloaded.nextMarkets
            self.movedEntries = preloaded.movedEntries
            self.discoverItems = Self.stripModelWrittenText(preloaded.discoverItems, limit: 3)
            self.loading = false
        } else {
            self.isPreloaded = false
        }
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

    func refresh(
        followedSubjects: [FollowedSubject295A],
        savedPins: [SavedPin],
        pinContent: [SavedPin: SavedPinContent],
        signedInItems: [FeedItem],
        signedInTeamFutures: TeamFuturesResponse?
    ) async {
        guard !isPreloaded else { return }

        if !hasRotatedSession {
            MyStuffVisitLedger295A.rotateSessionIfNeeded(defaults: defaults)
            hasRotatedSession = true
        }

        if liveEvents.isEmpty && nextEvents.isEmpty && nextMarkets.isEmpty && movedEntries.isEmpty {
            loading = true
        }

        let priorSnapshot = MyStuffVisitLedger295A.loadPreviousSnapshot(defaults: defaults)

        // Hydrate followed subjects in parallel (bounded to first 8 subjects for snappy launch).
        let subjectsToHydrate = Array(followedSubjects.prefix(8))

        async let hydratedSubjectsTask = Self.fetchFollowedSubjects(subjectsToHydrate)
        async let discoverFeedTask: FeedResponse? = try? await APIClient.shared.fetchFeed(limit: 12, mode: "discover")

        let hydrated = await hydratedSubjectsTask
        let discoverFeed = await discoverFeedTask

        var seenEventIds: Set<Int> = []
        var collectedEvents: [(event: FeedEventData, awayVerified: Bool)] = []
        var seenMarketKeys: Set<String> = []
        var collectedMarkets: [MyStuffMarketItem295A] = []
        var newReadings: [String: Double] = [:]

        func appendEvent(_ ev: FeedEventData, awayVerified: Bool = false) {
            guard seenEventIds.insert(ev.id).inserted else { return }
            let sanitized = Self.stripEventNarrative(ev)
            collectedEvents.append((sanitized, awayVerified))
            if EventState.canStillBeGraded(sanitized.status, commenceTime: sanitized.commenceTime?.asDate),
               let hp = sanitized.currentOdds?.homeProbability {
                newReadings["event:\(sanitized.id)"] = hp
            }
        }

        func appendMarket(_ m: MyStuffMarketItem295A) {
            guard seenMarketKeys.insert(m.id).inserted else { return }
            collectedMarkets.append(m)
            newReadings["market:\(m.id)"] = m.probability
        }

        // 1. Pinned items
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

        // 2. Hydrated followed subjects (teams, leagues, sets)
        for pack in hydrated {
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

        // 3. Signed-in team feed & futures fallback/merge
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
                        marketTitle: Self.cleanMarketTitle(item.marketName),
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

        MyStuffVisitLedger295A.recordObservedReadings(newReadings, defaults: defaults)

        // Partition into the 295: A order:
        // 1. Live now
        let live = collectedEvents.filter { pair in EventState.section(of: pair.event) == .live }

        // 2. Next for you (upcoming games chronologically ascending + top active followed markets)
        let upcomingSorted = collectedEvents
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
            let prior = priorSnapshot["event:\(ev.id)"]
            let baseline = prior ?? ev.prematchOdds?.homeProbability ?? ev.openingOdds?.homeProbability
            if let currentHome = ev.currentOdds?.homeProbability,
               let baseHome = baseline,
               let move = MyStuffVisitLedger295A.formatPointMove(
                   deltaProbability: currentHome - baseHome,
                   sinceLastVisit: prior != nil
               ),
               move.points >= 4 {
                let short = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: ev.sport)
                let movedTeam = (currentHome - baseHome) >= 0 ? short.home : short.away
                let summary = "\(movedTeam) \(move.text.lowercased())"
                moved.append(
                    MyStuffMovedEntry295A(
                        id: "moved-event-\(ev.id)",
                        movementSummary: summary,
                        magnitudePoints: move.points,
                        payload: .event(ev, awayVerified: pair.awayVerified)
                    )
                )
            }
        }

        let recentFinals = collectedEvents
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
                    magnitudePoints: 3,
                    payload: .event(pair.event, awayVerified: pair.awayVerified)
                )
            )
        }

        var unmovedMarkets: [MyStuffMarketItem295A] = []
        for market in collectedMarkets {
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

        moved.sort { $0.magnitudePoints > $1.magnitudePoints }
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

        liveEvents = live
        nextEvents = boundedNextEvents
        nextMarkets = boundedNextMarkets
        movedEntries = boundedMoved
        discoverItems = Self.stripModelWrittenText(rawDiscover, limit: 3)
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

    private struct HydratedSubjectPack: Sendable {
        var events: [(event: FeedEventData, awayVerified: Bool)] = []
        var markets: [MyStuffMarketItem295A] = []
    }

    nonisolated private static func fetchFollowedSubjects(
        _ subjects: [FollowedSubject295A]
    ) async -> [HydratedSubjectPack] {
        await withTaskGroup(of: (Int, HydratedSubjectPack).self) { group in
            for (idx, subject) in subjects.enumerated() {
                group.addTask {
                    (idx, await fetchOneSubject(subject))
                }
            }
            var ordered: [(Int, HydratedSubjectPack)] = []
            for await pair in group {
                ordered.append(pair)
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
            guard let page = try? await APIClient.shared.fetchTeamPage(slug: identifier) else {
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
            if let markets = try? await APIClient.shared.fetchLeagueMarkets(sportKey: sportKey) {
                for ev in markets.allGames.prefix(6) {
                    pack.events.append((ev, false))
                }
            }
            if let grid = try? await APIClient.shared.fetchChampionshipGrid(slug: subject.slug),
               let champMarketId = grid.championshipMarketId {
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

        case .set:
            switch subject.setKind ?? .container {
            case .container:
                guard let hub = try? await APIClient.shared.fetchContainerHub(slug: subject.slug),
                      hub.state == .published else {
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
                guard let detail = try? await APIClient.shared.fetchGolfTournament(slug: subject.slug),
                      let marketId = detail.evolutionMarketId,
                      let leader = detail.golfers.first,
                      leader.probability > 0 else {
                    return pack
                }
                let prob = leader.probability
                let move = leader.movement24h.flatMap {
                    MyStuffVisitLedger295A.formatPointMove(deltaProbability: $0, sinceLastVisit: false)
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
