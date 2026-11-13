import Combine
import Foundation

nonisolated protocol WatchPinsTransport12640: Sendable {
    func fetchEvent(id: Int) async throws -> WatchSelectedGame
    func fetchFuture(id: Int) async throws -> WatchFutureDetail12640
}

nonisolated struct WatchPinsLiveTransport12640: WatchPinsTransport12640 {
    private static let session: URLSession = {
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 15
        config.timeoutIntervalForResource = 30
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        config.urlCache = nil
        return URLSession(configuration: config)
    }()

    func fetchEvent(id: Int) async throws -> WatchSelectedGame {
        guard id > 0, let url = URL(string: "https://api.bainluck.com/api/events/\(id)") else {
            throw WatchAPIError.invalidURL
        }
        let (data, response) = try await Self.session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
              data.count <= 256 * 1024 else {
            throw WatchAPIError.httpError
        }
        return try JSONDecoder().decode(WatchSelectedGame.self, from: data)
    }

    func fetchFuture(id: Int) async throws -> WatchFutureDetail12640 {
        guard id > 0, let url = URL(string: "https://api.bainluck.com/api/futures/\(id)") else {
            throw WatchAPIError.invalidURL
        }
        let (data, response) = try await Self.session.data(from: url)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode),
              data.count <= 512 * 1024 else {
            throw WatchAPIError.httpError
        }
        return try JSONDecoder().decode(WatchFutureDetail12640.self, from: data)
    }
}

extension WatchSelectedGame {
    nonisolated var pinSummary12640: WatchPinEventSummary12640 {
        WatchPinEventSummary12640(
            id: id,
            isLive: isLive,
            isFinal: isFinal,
            showsForecast: showsForecast,
            homeRenderedPercent: homeRenderedPercent,
            homeScore: homeScore,
            awayScore: awayScore,
            commenceTime: commenceTime,
            scoreObservedAt: scoreObservedAt
        )
    }
}

/// #12640 — Watch pins runtime store. Receives phone pin IDs over WatchConnectivity,
/// fetches public `/api/events/{id}` and `/api/futures/{id}` without Watch sign-in,
/// drops anything without a probability (except scored finals), orders into the 4-bucket
/// pin list, and publishes the single reader-chosen pin to the Watch face.
@MainActor
final class WatchPinsStore12640: ObservableObject {
    static let shared = WatchPinsStore12640()

    @Published private(set) var wireItems: [WatchPinWireItem12640] = []
    @Published private(set) var eventsByID: [Int: WatchSelectedGame] = [:]
    @Published private(set) var futuresByID: [Int: WatchFutureDetail12640] = [:]
    @Published private(set) var chosenOutcomes: [Int: Int] = [:]
    @Published private(set) var selectedTarget: WatchSelectedPinTarget12640?
    @Published private(set) var isRefreshing = false
    @Published private(set) var lastRefreshError: String?
    @Published private(set) var lastRefreshedAt: Date?

    private let defaults: UserDefaults
    private let transport: any WatchPinsTransport12640
    private let publishSnapshot: @Sendable (WatchComplicationSnapshot?) -> Void
    private var refreshTask: Task<Void, Never>?

    private static let wireKey = "bainluck_watch_pins_wire_v1"
    private static let eventsCacheKey = "bainluck_watch_pins_events_cache_v1"
    private static let futuresCacheKey = "bainluck_watch_pins_futures_cache_v1"
    private static let chosenOutcomesKey = "bainluck_watch_pins_chosen_outcomes_v1"
    private static let selectedTargetKey = "bainluck_watch_pins_selected_target_v1"

    init(
        defaults: UserDefaults = .standard,
        transport: any WatchPinsTransport12640 = WatchPinsLiveTransport12640(),
        publishSnapshot: @escaping @Sendable (WatchComplicationSnapshot?) -> Void = { WatchComplicationPublisher.publishSnapshot($0) }
    ) {
        self.defaults = defaults
        self.transport = transport
        self.publishSnapshot = publishSnapshot
        restoreFromDefaults()
        #if DEBUG
        applyDebugFixtureIfNeeded()
        #endif
    }

    var orderedEntries: [WatchPinnedOrderedEntry12640] {
        let summaries = eventsByID.mapValues(\.pinSummary12640)
        return WatchPinsOrdering12640.rank(
            wireItems: wireItems,
            events: summaries,
            futures: futuresByID,
            chosenOutcomes: chosenOutcomes
        )
    }

    var hasAnyPhonePins: Bool {
        !wireItems.isEmpty
    }

    func receiveWireData(_ data: Data) {
        guard let decoded = WatchPinsWire12640.decode(data) else { return }
        applyWireItems(decoded)
    }

    func applyWireItems(_ items: [WatchPinWireItem12640]) {
        let sanitized = WatchPinsWire12640.sanitize(items)
        let changed = sanitized != wireItems
        wireItems = sanitized
        defaults.set(WatchPinsWire12640.encode(sanitized), forKey: Self.wireKey)

        // Prune cached items and choices that are no longer pinned on the phone (e.g., sign-out or unpin).
        let allowedEvents = Set(sanitized.filter { $0.kind == .event }.map(\.id))
        let allowedFutures = Set(sanitized.filter { $0.kind == .future }.map(\.id))
        eventsByID = eventsByID.filter { allowedEvents.contains($0.key) }
        futuresByID = futuresByID.filter { allowedFutures.contains($0.key) }
        chosenOutcomes = chosenOutcomes.filter { allowedFutures.contains($0.key) }

        for item in sanitized where item.kind == .future {
            if let wireOutcome = item.outcomeId, chosenOutcomes[item.id] == nil {
                chosenOutcomes[item.id] = wireOutcome
            }
        }

        if let target = selectedTarget {
            switch target {
            case .event(let id) where !allowedEvents.contains(id):
                selectedTarget = nil
            case .future(let marketID, _) where !allowedFutures.contains(marketID):
                selectedTarget = nil
            default:
                break
            }
        }

        saveCachesToDefaults()
        republishSelectedFaceSnapshot()

        if changed, !sanitized.isEmpty {
            triggerRefresh()
        }
    }

    func selectEvent(_ id: Int) {
        guard eventsByID[id]?.pinSummary12640.isAdmittedToWatchPins == true else { return }
        selectedTarget = .event(id: id)
        saveSelectedTarget()
        republishSelectedFaceSnapshot()
    }

    func selectFuture(_ marketID: Int, outcomeID: Int? = nil) {
        guard let market = futuresByID[marketID] else { return }
        let wireOutcome = wireItems.first { $0.kind == .future && $0.id == marketID }?.outcomeId
        guard let resolved = market.resolvedOutcome(
            chosenOutcomeID: outcomeID ?? chosenOutcomes[marketID],
            wireOutcomeID: wireOutcome
        ) else { return }
        chosenOutcomes[marketID] = resolved.id
        selectedTarget = .future(marketID: marketID, outcomeID: resolved.id)
        saveCachesToDefaults()
        saveSelectedTarget()
        republishSelectedFaceSnapshot()
    }

    func chooseFutureOutcome(marketID: Int, outcomeID: Int) {
        guard let market = futuresByID[marketID],
              market.pricedOutcomes.contains(where: { $0.id == outcomeID }) else { return }
        chosenOutcomes[marketID] = outcomeID
        if case .future(marketID, _) = selectedTarget {
            selectedTarget = .future(marketID: marketID, outcomeID: outcomeID)
            saveSelectedTarget()
        }
        saveCachesToDefaults()
        republishSelectedFaceSnapshot()
    }

    func clearSelection() {
        selectedTarget = nil
        saveSelectedTarget()
        publishSnapshot(nil)
    }

    func triggerRefresh() {
        refreshTask?.cancel()
        refreshTask = Task { await refreshAll() }
    }

    func refreshAll() async {
        #if DEBUG
        if ProcessInfo.processInfo.environment["BAINLUCK_WATCH_PINS_FIXTURE_12640"] != nil {
            republishSelectedFaceSnapshot()
            return
        }
        #endif
        let currentItems = wireItems
        guard !currentItems.isEmpty else {
            lastRefreshError = nil
            republishSelectedFaceSnapshot()
            return
        }
        isRefreshing = true
        defer { isRefreshing = false }

        let transport = self.transport
        var fetchedEvents: [Int: WatchSelectedGame] = [:]
        var fetchedFutures: [Int: WatchFutureDetail12640] = [:]
        var hadError = false

        await withTaskGroup(of: (WatchPinWireItem12640, WatchSelectedGame?, WatchFutureDetail12640?, Bool).self) { group in
            for item in currentItems {
                group.addTask {
                    switch item.kind {
                    case .event:
                        do {
                            let game = try await transport.fetchEvent(id: item.id)
                            return (item, game, nil, false)
                        } catch {
                            return (item, nil, nil, true)
                        }
                    case .future:
                        do {
                            let market = try await transport.fetchFuture(id: item.id)
                            return (item, nil, market, false)
                        } catch {
                            return (item, nil, nil, true)
                        }
                    }
                }
            }
            for await (item, game, market, failed) in group {
                if failed { hadError = true }
                if let game { fetchedEvents[item.id] = game }
                if let market { fetchedFutures[item.id] = market }
            }
        }

        guard !Task.isCancelled else { return }
        for (id, game) in fetchedEvents { eventsByID[id] = game }
        for (id, market) in fetchedFutures { futuresByID[id] = market }

        // Drop a selected target if a fresh read proves it no longer carries a probability (and isn't final).
        if let target = selectedTarget {
            switch target {
            case .event(let id):
                if let game = fetchedEvents[id], !game.pinSummary12640.isAdmittedToWatchPins {
                    selectedTarget = nil
                }
            case .future(let marketID, _):
                if let market = fetchedFutures[marketID], market.pricedOutcomes.isEmpty {
                    selectedTarget = nil
                }
            }
        }

        lastRefreshedAt = Date()
        lastRefreshError = hadError && eventsByID.isEmpty && futuresByID.isEmpty
            ? "Unable to load pins. Try Refresh."
            : nil
        saveCachesToDefaults()
        saveSelectedTarget()
        republishSelectedFaceSnapshot()
    }

    func currentComplicationSnapshot(savedAt: Date = Date()) -> WatchComplicationSnapshot? {
        guard let target = selectedTarget else { return nil }
        switch target {
        case .event(let id):
            guard let game = eventsByID[id], game.pinSummary12640.isAdmittedToWatchPins else { return nil }
            return WatchComplicationProjection.snapshot(game: game, savedAt: savedAt)
        case .future(let marketID, let explicitOutcomeID):
            guard let market = futuresByID[marketID] else { return nil }
            let wireOutcome = wireItems.first { $0.kind == .future && $0.id == marketID }?.outcomeId
            guard let outcome = market.resolvedOutcome(
                chosenOutcomeID: explicitOutcomeID ?? chosenOutcomes[marketID],
                wireOutcomeID: wireOutcome
            ),
                  let prob = outcome.probability else { return nil }
            let rawObs = outcome.effectiveObservedAt ?? market.updatedAt ?? savedAt
            let observed = min(rawObs, savedAt)
            return WatchComplicationProjection.futureSnapshot(
                marketID: market.id,
                marketTitle: market.name,
                outcomeName: outcome.name,
                probability: prob,
                observedAt: observed,
                savedAt: savedAt
            )
        }
    }

    private func republishSelectedFaceSnapshot() {
        publishSnapshot(currentComplicationSnapshot(savedAt: Date()))
    }

    private func restoreFromDefaults() {
        if let rawWire = defaults.data(forKey: Self.wireKey),
           let decoded = WatchPinsWire12640.decode(rawWire) {
            wireItems = decoded
        }
        if let rawEvents = defaults.data(forKey: Self.eventsCacheKey), rawEvents.count <= 256 * 1024,
           let decoded = try? JSONDecoder().decode([Int: WatchSelectedGame].self, from: rawEvents) {
            eventsByID = decoded
        }
        if let rawFutures = defaults.data(forKey: Self.futuresCacheKey), rawFutures.count <= 512 * 1024,
           let decoded = try? JSONDecoder().decode([Int: WatchFutureDetail12640].self, from: rawFutures) {
            futuresByID = decoded
        }
        if let rawChosen = defaults.data(forKey: Self.chosenOutcomesKey), rawChosen.count <= 16 * 1024,
           let decoded = try? JSONDecoder().decode([Int: Int].self, from: rawChosen) {
            chosenOutcomes = decoded
        }
        if let rawTarget = defaults.data(forKey: Self.selectedTargetKey), rawTarget.count <= 4 * 1024,
           let decoded = try? JSONDecoder().decode(WatchSelectedPinTarget12640.self, from: rawTarget) {
            selectedTarget = decoded
        }
    }

    private func saveCachesToDefaults() {
        if let encodedEvents = try? JSONEncoder().encode(eventsByID) {
            defaults.set(encodedEvents, forKey: Self.eventsCacheKey)
        }
        if let encodedFutures = try? JSONEncoder().encode(futuresByID) {
            defaults.set(encodedFutures, forKey: Self.futuresCacheKey)
        }
        if let encodedChosen = try? JSONEncoder().encode(chosenOutcomes) {
            defaults.set(encodedChosen, forKey: Self.chosenOutcomesKey)
        }
    }

    private func saveSelectedTarget() {
        if let selectedTarget, let encoded = try? JSONEncoder().encode(selectedTarget) {
            defaults.set(encoded, forKey: Self.selectedTargetKey)
        } else {
            defaults.removeObject(forKey: Self.selectedTargetKey)
        }
    }

    #if DEBUG
    private func applyDebugFixtureIfNeeded() {
        guard let mode = ProcessInfo.processInfo.environment["BAINLUCK_WATCH_PINS_FIXTURE_12640"] else { return }
        if mode == "empty" {
            wireItems = []
            eventsByID = [:]
            futuresByID = [:]
            chosenOutcomes = [:]
            selectedTarget = nil
            return
        }
        let now = Date()
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]

        func decodeGame(_ dict: [String: Any]) -> WatchSelectedGame? {
            guard let data = try? JSONSerialization.data(withJSONObject: dict) else { return nil }
            return try? JSONDecoder().decode(WatchSelectedGame.self, from: data)
        }

        let livePayload: [String: Any] = [
            "id": 9101,
            "home_team": "San Francisco Giants",
            "away_team": "Los Angeles Dodgers",
            "home_team_data": ["team_id": 1, "abbreviation": "SF"],
            "away_team_data": ["team_id": 2, "abbreviation": "LA"],
            "status": "live",
            "sport": "baseball_mlb",
            "home_score": 4,
            "away_score": 2,
            "hero_probability": 0.64,
            "hero_probability_away": 0.36,
            "hero_probability_observed_at": iso.string(from: now.addingTimeInterval(-60)),
            "score_observed_at": iso.string(from: now.addingTimeInterval(-45)),
            "espn": [
                "period": "Bot 7th"
            ]
        ]

        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .current
        // Next Sunday 1:25 PM local
        var sundayComps = calendar.dateComponents([.yearForWeekOfYear, .weekOfYear], from: now.addingTimeInterval(3 * 86400))
        sundayComps.weekday = 1
        sundayComps.hour = 13
        sundayComps.minute = 25
        let sundayStart = calendar.date(from: sundayComps) ?? now.addingTimeInterval(3 * 86400)

        let upcomingPayload: [String: Any] = [
            "id": 9202,
            "home_team": "Kansas City Chiefs",
            "away_team": "Buffalo Bills",
            "home_team_data": ["team_id": 11, "abbreviation": "KC"],
            "away_team_data": ["team_id": 12, "abbreviation": "BUF"],
            "status": "scheduled",
            "sport": "americanfootball_nfl",
            "commence_time": iso.string(from: sundayStart),
            "hero_probability": 0.58,
            "hero_probability_away": 0.42,
            "hero_probability_observed_at": iso.string(from: now.addingTimeInterval(-300))
        ]

        let finalPayload: [String: Any] = [
            "id": 9404,
            "home_team": "Boston Celtics",
            "away_team": "New York Knicks",
            "home_team_data": ["team_id": 21, "abbreviation": "BOS"],
            "away_team_data": ["team_id": 22, "abbreviation": "NYK"],
            "status": "completed",
            "sport": "basketball_nba",
            "home_score": 114,
            "away_score": 108,
            "commence_time": iso.string(from: now.addingTimeInterval(-7200)),
            "score_observed_at": iso.string(from: now.addingTimeInterval(-1800))
        ]

        let market = WatchFutureDetail12640(
            id: 9303,
            name: "2028 Democratic Nominee",
            status: "open",
            pricesWithheld: 0,
            leadOutcomeId: 301,
            updatedAt: now.addingTimeInterval(-3600),
            outcomes: [
                WatchFutureOutcome12640(id: 301, name: "Newsom", probability: 0.23, lastUpdated: now.addingTimeInterval(-3600)),
                WatchFutureOutcome12640(id: 302, name: "Shapiro", probability: 0.19, lastUpdated: now.addingTimeInterval(-3600)),
                WatchFutureOutcome12640(id: 303, name: "Buttigieg", probability: 0.12, lastUpdated: now.addingTimeInterval(-3600)),
                WatchFutureOutcome12640(id: 304, name: "Whitmer", probability: 0.09, lastUpdated: now.addingTimeInterval(-3600))
            ]
        )

        var evs: [Int: WatchSelectedGame] = [:]
        if let g = decodeGame(livePayload) { evs[g.id] = g }
        if let g = decodeGame(upcomingPayload) { evs[g.id] = g }
        if let g = decodeGame(finalPayload) { evs[g.id] = g }
        eventsByID = evs
        futuresByID = [market.id: market]
        wireItems = [
            WatchPinWireItem12640(kind: .future, id: 9303),
            WatchPinWireItem12640(kind: .event, id: 9404),
            WatchPinWireItem12640(kind: .event, id: 9202),
            WatchPinWireItem12640(kind: .event, id: 9101)
        ]
        chosenOutcomes = [9303: 301]

        switch mode {
        case "selected-future", "outcome-picker":
            selectedTarget = .future(marketID: 9303, outcomeID: 301)
        case "selected-live":
            selectedTarget = .event(id: 9101)
        case "selected-upcoming":
            selectedTarget = .event(id: 9202)
        case "selected-final":
            selectedTarget = .event(id: 9404)
        default:
            selectedTarget = nil
        }
        republishSelectedFaceSnapshot()
    }
    #endif
}
