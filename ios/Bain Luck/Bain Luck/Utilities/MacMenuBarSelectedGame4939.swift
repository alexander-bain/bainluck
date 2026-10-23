import Combine
import Foundation

// MARK: - #4939 Mac Menu Bar Selected Game Snapshot & Store

/// Pure, portable snapshot of one game for the Mac menu bar extra (#4939).
///
/// Reuses the app's canonical truth and formatting rules:
/// - `TeamShortName` for recognizable competitor labels
/// - `DrawPricedWinner` and `duelPercents` so a draw-priced sport never prints
///   `1 - home` as the away win probability, and a two-way pair sums to 100
/// - `EventState` and `EventOutcome` so finished, venue-settled, and suspended
///   games show their settled state and never display a live win forecast
/// - `SourceAge` on producer observation timestamps (`scoreObservedAt` /
///   `probabilityObservedAt`), never client receipt time
nonisolated struct MacMenuBarGameSnapshot4939: Codable, Equatable, Identifiable, Sendable {
    /// Live readings older than two minutes (the live poll cadence) are marked stale.
    static let liveStaleThresholdSeconds: TimeInterval = 120

    let id: Int
    let sportKey: String?
    let sportLabel: String
    let awayTeam: String
    let homeTeam: String
    let awayAbbrev: String
    let homeAbbrev: String
    let status: String?
    let commenceTime: String?
    let startIsTbd: Bool?
    let awayScore: Int?
    let homeScore: Int?
    let liveClockText: String?
    /// `nil` when the sport prices a draw (#5271 / #5363) or when no probability is held.
    let awayWinPercent: Int?
    let homeWinPercent: Int?
    let winnerMarketPricesADraw: Bool
    let heroSettledResult: String?
    let venueSettled: Bool?
    let venueSettledResult: String?
    let venueClosedNoWinner: Bool?
    let scoreObservedAt: String?
    let probabilityObservedAt: String?

    var matchupTitle: String {
        "\(awayAbbrev) @ \(homeAbbrev)"
    }

    var fullMatchupTitle: String {
        "\(awayTeam) at \(homeTeam)"
    }

    /// Missing scores render as an em dash, never as zero (#4939).
    var awayScoreText: String {
        awayScore.map(String.init) ?? "\u{2014}"
    }

    /// Missing scores render as an em dash, never as zero (#4939).
    var homeScoreText: String {
        homeScore.map(String.init) ?? "\u{2014}"
    }

    var hasBothScores: Bool {
        awayScore != nil && homeScore != nil
    }

    var isLive: Bool {
        status == "live"
    }
}

// MARK: - Presentation & Truth Rules

@MainActor
extension MacMenuBarGameSnapshot4939 {
    var isFinished: Bool {
        EventState.isFinished(status)
    }

    func isSuspendedAndStarted(now: Date = Date()) -> Bool {
        EventState.isSuspendedAndStarted(status, commenceTime: commenceTime?.asDate, now: now)
    }

    func showsVenueSettled(now: Date = Date()) -> Bool {
        EventState.showsVenueSettledVerdict(
            status,
            venueSettled: venueSettled,
            commenceTime: commenceTime?.asDate,
            now: now
        )
    }

    func showsVenueClosedNoWinner(now: Date = Date()) -> Bool {
        EventState.showsVenueClosedNoWinner(
            status,
            venueSettled: venueSettled,
            venueClosedNoWinner: venueClosedNoWinner,
            commenceTime: commenceTime?.asDate,
            now: now
        )
    }

    /// Whether a live/pregame win probability may still be shown for this game.
    /// Finished, venue-settled, venue-closed-no-winner, and started-suspended
    /// games must not show a live win forecast.
    func canShowWinProbability(now: Date = Date()) -> Bool {
        EventState.canStillBeGraded(status, commenceTime: commenceTime?.asDate, now: now)
            && !showsVenueSettled(now: now)
            && !showsVenueClosedNoWinner(now: now)
    }

    func statusBadgeText(now: Date = Date()) -> String {
        if isFinished {
            return "FINAL"
        }
        if showsVenueSettled(now: now) {
            return EventState.venueSettledLabel
        }
        if showsVenueClosedNoWinner(now: now) {
            return EventState.venueClosedNoWinnerLabel
        }
        if isSuspendedAndStarted(now: now) {
            return EventState.suspendedSummary(away: awayScore, home: homeScore)
        }
        if isLive {
            if let clock = liveClockText?.trimmingCharacters(in: .whitespacesAndNewlines),
               !clock.isEmpty {
                return clock
            }
            return "LIVE"
        }
        if startIsTbd == true {
            return "Start time TBD"
        }
        return "UPCOMING"
    }

    /// Settled verdict text for a finished or venue-settled game, or `nil` while unsettled.
    func settledVerdictText(now: Date = Date()) -> String? {
        if isFinished {
            let outcome = EventOutcome.resolve(
                status: status,
                homeScore: homeScore,
                awayScore: awayScore,
                servedResult: heroSettledResult
            )
            switch outcome {
            case .home:
                return "\(homeAbbrev) won"
            case .away:
                return "\(awayAbbrev) won"
            case .draw:
                return "Final \u{00B7} Draw"
            case .undecided:
                return "Final"
            }
        }
        if showsVenueSettled(now: now) {
            if let verbatim = venueSettledResult, !verbatim.isEmpty {
                return verbatim
            }
            return EventState.venueSettledLabel
        }
        if showsVenueClosedNoWinner(now: now) {
            return EventState.venueClosedNoWinnerLabel
        }
        return nil
    }

    /// Named probability line for the selected game card, or `nil` when settled/suspended.
    func namedProbabilityLine(now: Date = Date()) -> String? {
        guard canShowWinProbability(now: now) else { return nil }
        guard let homePct = homeWinPercent else {
            return "No win probability available"
        }
        if winnerMarketPricesADraw || awayWinPercent == nil {
            return "\(homeAbbrev) \(homePct)% win"
        }
        if let awayPct = awayWinPercent {
            return "\(awayAbbrev) \(awayPct)% \u{00B7} \(homeAbbrev) \(homePct)%"
        }
        return "\(homeAbbrev) \(homePct)% win"
    }

    /// The producer observation timestamp backing the displayed reading.
    /// When both score and probability timestamps exist on a live reading, uses the
    /// oldest of the two (`SourceAge.oldestStamp`) so the age never claims to be
    /// fresher than its oldest component.
    var primaryObservedAt: String? {
        if isLive, scoreObservedAt != nil, probabilityObservedAt != nil {
            return SourceAge.oldestStamp([scoreObservedAt, probabilityObservedAt])
        }
        if let scoreStamp = scoreObservedAt, ISO8601Stamp.date(scoreStamp) != nil || scoreStamp.asDate != nil {
            return scoreStamp
        }
        if let probStamp = probabilityObservedAt, ISO8601Stamp.date(probStamp) != nil || probStamp.asDate != nil {
            return probStamp
        }
        return nil
    }

    func isStaleLiveReading(now: Date = Date()) -> Bool {
        guard isLive, let seconds = SourceAge.ageSeconds(primaryObservedAt, now: now) else {
            return false
        }
        return seconds > Self.liveStaleThresholdSeconds
    }

    func freshnessSummaryText(now: Date = Date()) -> String {
        guard let seconds = SourceAge.ageSeconds(primaryObservedAt, now: now) else {
            return "Update time unavailable"
        }
        let age = SourceAge.formatAge(seconds: seconds)
        if isLive && seconds > Self.liveStaleThresholdSeconds {
            return "Stale \u{00B7} updated \(age)"
        }
        return "Updated \(age)"
    }

    func accessibilitySummary(now: Date = Date()) -> String {
        var parts: [String] = [
            fullMatchupTitle,
            statusBadgeText(now: now),
        ]
        if let awayScore, let homeScore {
            parts.append("\(awayAbbrev) \(awayScore), \(homeAbbrev) \(homeScore)")
        } else {
            parts.append("Score not yet reported")
        }
        if let settled = settledVerdictText(now: now) {
            parts.append(settled)
        } else if let prob = namedProbabilityLine(now: now) {
            parts.append(prob)
        }
        parts.append(freshnessSummaryText(now: now))
        return parts.joined(separator: ", ")
    }

    // MARK: - Mapping from Canonical API Models

    /// Resolves the printed win-probability pair for a menu bar game using
    /// `DrawPricedWinner.printablePair` and `duelPercents`.
    static func resolvePrintedPercentages(
        sportKey: String?,
        currentOdds: CurrentOdds?,
        heroProbability: Double?,
        openingOdds: OpeningOdds?
    ) -> (awayPercent: Int?, homePercent: Int?, pricesADraw: Bool) {
        let pricesADraw = DrawPricedWinner.sportPricesADraw(sportKey)
        let fromCurrentOdds = currentOdds?.homeProbability != nil
        guard let homeProbability = currentOdds?.homeProbability
            ?? heroProbability
            ?? openingOdds?.homeProbability
        else {
            return (nil, nil, pricesADraw)
        }
        let rawAway = (fromCurrentOdds ? currentOdds?.awayProbability : nil)
            ?? (1.0 - homeProbability)
        let printable = DrawPricedWinner.printablePair(
            away: rawAway,
            home: homeProbability,
            sport: sportKey
        )
        let duel = duelPercents(
            away: rawAway,
            home: homeProbability,
            servedAway: fromCurrentOdds ? currentOdds?.awayRenderedPercent : nil,
            servedHome: fromCurrentOdds ? currentOdds?.homeRenderedPercent : nil
        )
        guard let homePct = duel[1] else {
            return (nil, nil, pricesADraw)
        }
        let printableAwayPct: Int? = printable?.away == nil ? nil : duel[0]
        return (printableAwayPct, homePct, pricesADraw)
    }

    /// Builds a snapshot from `GET /api/events/{id}` (`EventDetail`).
    static func from(
        detail: EventDetail,
        liveClockText: String?
    ) -> MacMenuBarGameSnapshot4939 {
        let sides = TeamShortName.shortPair(
            away: detail.awayTeam,
            home: detail.homeTeam,
            awayServed: detail.awayTeamData?.abbreviation,
            homeServed: detail.homeTeamData?.abbreviation,
            sportKey: detail.sport
        )
        let probs = resolvePrintedPercentages(
            sportKey: detail.sport,
            currentOdds: detail.currentOdds,
            heroProbability: detail.heroProbability,
            openingOdds: detail.openingOdds
        )
        let sportLabel = detail.metadata?.league
            ?? detail.sport.map(toTitleCaseAcronymSafe)
            ?? "Sports"
        return MacMenuBarGameSnapshot4939(
            id: detail.id,
            sportKey: detail.sport,
            sportLabel: sportLabel,
            awayTeam: detail.awayTeam,
            homeTeam: detail.homeTeam,
            awayAbbrev: sides.away,
            homeAbbrev: sides.home,
            status: detail.status,
            commenceTime: detail.commenceTime,
            startIsTbd: detail.startIsTbd,
            awayScore: detail.awayScore,
            homeScore: detail.homeScore,
            liveClockText: liveClockText,
            awayWinPercent: probs.awayPercent,
            homeWinPercent: probs.homePercent,
            winnerMarketPricesADraw: probs.pricesADraw,
            heroSettledResult: detail.heroSettledResult,
            venueSettled: detail.venueSettled,
            venueSettledResult: detail.venueSettledResult,
            venueClosedNoWinner: detail.venueClosedNoWinner,
            scoreObservedAt: detail.scoreObservedAt,
            probabilityObservedAt: detail.heroProbabilityObservedAt ?? detail.currentOdds?.capturedAt
        )
    }

    /// Builds a snapshot from a feed event card (`FeedEventData`).
    static func from(
        feedEvent: FeedEventData,
        awayAbbrev: String,
        homeAbbrev: String,
        awayWinPercent: Int?,
        homeWinPercent: Int?,
        liveClockText: String?
    ) -> MacMenuBarGameSnapshot4939 {
        let sportLabel = feedEvent.sportName
            ?? feedEvent.metadata?.league
            ?? feedEvent.sport.map(toTitleCaseAcronymSafe)
            ?? "Sports"
        return MacMenuBarGameSnapshot4939(
            id: feedEvent.id,
            sportKey: feedEvent.sport,
            sportLabel: sportLabel,
            awayTeam: feedEvent.awayTeam,
            homeTeam: feedEvent.homeTeam,
            awayAbbrev: awayAbbrev,
            homeAbbrev: homeAbbrev,
            status: feedEvent.status,
            commenceTime: feedEvent.commenceTime,
            startIsTbd: feedEvent.startIsTbd,
            awayScore: feedEvent.awayScore,
            homeScore: feedEvent.homeScore,
            liveClockText: liveClockText,
            awayWinPercent: awayWinPercent,
            homeWinPercent: homeWinPercent,
            winnerMarketPricesADraw: DrawPricedWinner.sportPricesADraw(feedEvent.sport),
            heroSettledResult: nil,
            venueSettled: nil,
            venueSettledResult: nil,
            venueClosedNoWinner: feedEvent.venueClosedNoWinner,
            scoreObservedAt: feedEvent.scoreObservedAt,
            probabilityObservedAt: feedEvent.heroProbabilityObservedAt ?? feedEvent.currentOdds?.capturedAt
        )
    }
}

// MARK: - Data Source Protocol & Errors

nonisolated enum MacMenuBarDataSourceError4939: Error, LocalizedError, Equatable, Sendable {
    case eventUnavailable(eventID: Int)
    case message(String)

    var errorDescription: String? {
        switch self {
        case .eventUnavailable:
            return "Selected game is no longer available."
        case .message(let text):
            return text
        }
    }
}

@MainActor
protocol MacMenuBarGameDataSource4939 {
    func fetchSelectedGame(eventID: Int) async throws -> MacMenuBarGameSnapshot4939
    func fetchCandidateGames() async throws -> [MacMenuBarGameSnapshot4939]
}

// MARK: - Store Phase & Persisted Selection Store

nonisolated enum MacMenuBarStorePhase4939: Equatable, Sendable {
    case idle
    case loading
    case loaded
    case unavailable(String)
    case failed(String)
}

@MainActor
final class MacMenuBarSelectedGameStore4939: ObservableObject {
    static let selectedEventIDKey = "bainluck_mac_menubar_selected_event_id_4939"
    static let selectedSnapshotKey = "bainluck_mac_menubar_selected_game_snapshot_4939"
    static let selectedOwnerKey = "bainluck_mac_menubar_selected_owner_id_4939"

    @Published private(set) var selectedEventID: Int?
    @Published private(set) var selectedGame: MacMenuBarGameSnapshot4939?
    @Published private(set) var candidateGames: [MacMenuBarGameSnapshot4939] = []
    @Published private(set) var phase: MacMenuBarStorePhase4939 = .idle
    @Published private(set) var isChoosingGame = false
    /// True when showing a persisted snapshot restored from `UserDefaults` before
    /// the current session has confirmed it over the network.
    @Published private(set) var isShowingPersistedSnapshot = false
    @Published private(set) var debugFixtureBanner: String?

    private let dataSource: any MacMenuBarGameDataSource4939
    private let defaults: UserDefaults
    private let now: () -> Date
    private var inFlightRefreshTask: Task<Void, Never>?

    init(
        dataSource: any MacMenuBarGameDataSource4939,
        defaults: UserDefaults = .standard,
        now: @escaping () -> Date = Date.init,
        debugFixtureBanner: String? = nil
    ) {
        self.dataSource = dataSource
        self.defaults = defaults
        self.now = now
        self.debugFixtureBanner = debugFixtureBanner
        restorePersistedSelection()
    }

    private func restorePersistedSelection() {
        let rawID = defaults.object(forKey: Self.selectedEventIDKey) as? Int
        guard let eventID = rawID, eventID > 0 else {
            selectedEventID = nil
            selectedGame = nil
            isShowingPersistedSnapshot = false
            return
        }
        selectedEventID = eventID
        if let data = defaults.data(forKey: Self.selectedSnapshotKey),
           let decoded = try? JSONDecoder().decode(MacMenuBarGameSnapshot4939.self, from: data),
           decoded.id == eventID {
            selectedGame = decoded
            isShowingPersistedSnapshot = true
            phase = .loaded
        } else {
            selectedGame = nil
            isShowingPersistedSnapshot = false
        }
    }

    private func persist(game: MacMenuBarGameSnapshot4939) {
        defaults.set(game.id, forKey: Self.selectedEventIDKey)
        if let data = try? JSONEncoder().encode(game) {
            defaults.set(data, forKey: Self.selectedSnapshotKey)
        }
    }

    /// Scopes persisted selection to the active account identity so signing out or
    /// switching accounts clears the prior account's selection rather than leaking it.
    func syncAccount(ownerID: String?) {
        let normalized = Self.normalizeOwner(ownerID)
        let previous = defaults.string(forKey: Self.selectedOwnerKey)
        defaults.set(normalized, forKey: Self.selectedOwnerKey)
        if let previous, previous != normalized {
            clearSelection()
        }
    }

    nonisolated static func normalizeOwner(_ ownerID: String?) -> String {
        guard let trimmed = ownerID?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else {
            return "anonymous"
        }
        return "user:\(trimmed)"
    }

    func selectGame(_ game: MacMenuBarGameSnapshot4939) {
        inFlightRefreshTask?.cancel()
        inFlightRefreshTask = nil
        selectedEventID = game.id
        selectedGame = game
        isChoosingGame = false
        isShowingPersistedSnapshot = false
        phase = .loaded
        persist(game: game)
        Task {
            await refresh()
        }
    }

    func beginChangingGame() {
        isChoosingGame = true
        Task {
            await refreshCandidatesOnly()
        }
    }

    func cancelChangingGame() {
        guard selectedEventID != nil else { return }
        isChoosingGame = false
    }

    func clearSelection() {
        inFlightRefreshTask?.cancel()
        inFlightRefreshTask = nil
        defaults.removeObject(forKey: Self.selectedEventIDKey)
        defaults.removeObject(forKey: Self.selectedSnapshotKey)
        selectedEventID = nil
        selectedGame = nil
        isChoosingGame = false
        isShowingPersistedSnapshot = false
        phase = .idle
        Task {
            await refresh()
        }
    }

    /// Single-flight refresh: concurrent callers await the same in-flight task
    /// instead of starting duplicate per-game or feed requests (#4939).
    func refresh() async {
        if let existing = inFlightRefreshTask {
            await existing.value
            return
        }
        let task = Task { @MainActor in
            await performRefresh()
        }
        inFlightRefreshTask = task
        await task.value
        inFlightRefreshTask = nil
    }

    private func performRefresh() async {
        if let eventID = selectedEventID {
            if selectedGame == nil {
                phase = .loading
            }
            do {
                let fresh = try await dataSource.fetchSelectedGame(eventID: eventID)
                guard !Task.isCancelled, selectedEventID == eventID else { return }
                selectedGame = fresh
                isShowingPersistedSnapshot = false
                phase = .loaded
                persist(game: fresh)
            } catch let error as MacMenuBarDataSourceError4939 {
                guard !Task.isCancelled, selectedEventID == eventID else { return }
                switch error {
                case .eventUnavailable:
                    selectedGame = nil
                    isShowingPersistedSnapshot = false
                    defaults.removeObject(forKey: Self.selectedSnapshotKey)
                    phase = .unavailable(error.localizedDescription)
                case .message(let text):
                    phase = .failed(text)
                }
            } catch {
                guard !Task.isCancelled, selectedEventID == eventID else { return }
                if (error as? APIError)?.isCancellation == true { return }
                phase = .failed(error.localizedDescription)
            }

            if isChoosingGame {
                await refreshCandidatesOnly()
            }
            return
        }

        await refreshCandidatesOnly()
    }

    private func refreshCandidatesOnly() async {
        if candidateGames.isEmpty && selectedGame == nil {
            phase = .loading
        }
        do {
            let games = try await dataSource.fetchCandidateGames()
            guard !Task.isCancelled else { return }
            candidateGames = games
            if selectedEventID == nil {
                phase = .loaded
            }
        } catch {
            guard !Task.isCancelled else { return }
            if (error as? APIError)?.isCancellation == true { return }
            if selectedEventID == nil {
                phase = .failed(error.localizedDescription)
            }
        }
    }

    var currentInstant: Date {
        now()
    }
}

// MARK: - Clearly Labeled Deterministic Debug Fixtures (#if DEBUG)

#if DEBUG
nonisolated enum MacMenuBarDebugFixtures4939 {
    static let envKey = "BAINLUCK_MAC_MENUBAR_DEBUG_FIXTURE"

    static let referenceNow = ISO8601Stamp.date("2026-10-22T20:00:00Z") ?? Date()

    static let liveTwoWayGame = MacMenuBarGameSnapshot4939(
        id: 9049391,
        sportKey: "basketball_nba",
        sportLabel: "NBA",
        awayTeam: "Boston Celtics",
        homeTeam: "New York Knicks",
        awayAbbrev: "Celtics",
        homeAbbrev: "Knicks",
        status: "live",
        commenceTime: "2026-10-22T19:00:00Z",
        startIsTbd: false,
        awayScore: 84,
        homeScore: 79,
        liveClockText: "Q3 4:12",
        awayWinPercent: 64,
        homeWinPercent: 36,
        winnerMarketPricesADraw: false,
        heroSettledResult: nil,
        venueSettled: nil,
        venueSettledResult: nil,
        venueClosedNoWinner: nil,
        scoreObservedAt: "2026-10-22T19:59:30Z",
        probabilityObservedAt: "2026-10-22T19:59:30Z"
    )

    static let liveSoccerThreeWayGame = MacMenuBarGameSnapshot4939(
        id: 9049392,
        sportKey: "soccer_epl",
        sportLabel: "EPL",
        awayTeam: "Arsenal FC",
        homeTeam: "Liverpool FC",
        awayAbbrev: "Arsenal FC",
        homeAbbrev: "Liverpool FC",
        status: "live",
        commenceTime: "2026-10-22T19:00:00Z",
        startIsTbd: false,
        awayScore: 1,
        homeScore: 1,
        liveClockText: "67'",
        awayWinPercent: nil,
        homeWinPercent: 48,
        winnerMarketPricesADraw: true,
        heroSettledResult: nil,
        venueSettled: nil,
        venueSettledResult: nil,
        venueClosedNoWinner: nil,
        scoreObservedAt: "2026-10-22T19:59:00Z",
        probabilityObservedAt: "2026-10-22T19:59:00Z"
    )

    static let scheduledMissingScoresGame = MacMenuBarGameSnapshot4939(
        id: 9049393,
        sportKey: "baseball_mlb",
        sportLabel: "MLB",
        awayTeam: "Los Angeles Dodgers",
        homeTeam: "New York Yankees",
        awayAbbrev: "Dodgers",
        homeAbbrev: "Yankees",
        status: "scheduled",
        commenceTime: "2026-10-23T00:08:00Z",
        startIsTbd: false,
        awayScore: nil,
        homeScore: nil,
        liveClockText: nil,
        awayWinPercent: 54,
        homeWinPercent: 46,
        winnerMarketPricesADraw: false,
        heroSettledResult: nil,
        venueSettled: nil,
        venueSettledResult: nil,
        venueClosedNoWinner: nil,
        scoreObservedAt: nil,
        probabilityObservedAt: "2026-10-22T19:55:00Z"
    )

    static let finalCompletedGame = MacMenuBarGameSnapshot4939(
        id: 9049394,
        sportKey: "baseball_mlb",
        sportLabel: "MLB",
        awayTeam: "Milwaukee Brewers",
        homeTeam: "Los Angeles Dodgers",
        awayAbbrev: "Brewers",
        homeAbbrev: "Dodgers",
        status: "completed",
        commenceTime: "2026-10-15T20:00:00Z",
        startIsTbd: false,
        awayScore: 1,
        homeScore: 5,
        liveClockText: nil,
        awayWinPercent: 18,
        homeWinPercent: 82,
        winnerMarketPricesADraw: false,
        heroSettledResult: "home",
        venueSettled: nil,
        venueSettledResult: nil,
        venueClosedNoWinner: nil,
        scoreObservedAt: "2026-10-15T23:10:00Z",
        probabilityObservedAt: "2026-10-15T23:10:00Z"
    )
}
#endif
