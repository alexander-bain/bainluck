import Foundation

private actor FlowPickerTransport: WatchGamePickerTransport {
    let batch: WatchGamePickerBatch
    init(batch: WatchGamePickerBatch) { self.batch = batch }
    func fetchGames() async throws -> WatchGamePickerBatch { batch }
}

private actor FlowDetailTransport: WatchSelectedGameTransport {
    private var script: [(Int, Result<WatchSelectedGame, Error>)]
    private(set) var fetchCount = 0
    init(_ script: [(Int, Result<WatchSelectedGame, Error>)]) { self.script = script }
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        fetchCount += 1
        precondition(!script.isEmpty, "The flow must never make an unplanned request")
        let (expectedID, result) = script.removeFirst()
        precondition(eventID == expectedID, "Detail must follow the selected or resolved canonical ID")
        return try result.get()
    }
    func assertConsumed() { precondition(script.isEmpty, "Every planned flow response must be consumed") }
}

/// A deterministic store journey; rendering and physical Watch acceptance are separate gates.
@MainActor func checkWatchGameFlow() async throws {
    let suite = "watch-game-flow-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let clock = ISO8601DateFormatter().date(from: "2026-10-03T18:00:00Z")!
    let feedJSON = """
    {"items":[
      {"type":"futures","score":95,"headline":"An election","data":{"id":900,"name":"Election winner","top_outcomes":[]}},
      {"type":"event","score":90,"headline":"Dodgers at Giants","data":{"id":101,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"live","home_score":3,"away_score":2,"sport":"baseball_mlb","sport_name":"MLB","current_odds":{"home_probability":0.61},"espn":{"period":"Bottom 7th","game_clock":null}}},
      {"type":"event","score":85,"headline":"Chiefs at Bills","data":{"id":202,"home_team":"Buffalo Bills","away_team":"Kansas City Chiefs","status":"scheduled","commence_time":"2026-10-04T17:00:00Z","sport":"americanfootball_nfl"}}
    ],"has_more":true,"next_cursor":"bounded-discover-page"}
    """
    let feedDecoder = JSONDecoder()
    feedDecoder.keyDecodingStrategy = .convertFromSnakeCase
    let feed = try feedDecoder.decode(WatchFeedResponse.self, from: Data(feedJSON.utf8))
    let pickerTransport = FlowPickerTransport(batch: WatchGamePickerBatch(feed: feed))
    let picker = WatchGamePickerStore(transport: pickerTransport)
    await picker.refresh()
    precondition(picker.games.map(\.id) == [101, 202] && picker.errorMessage == nil)
    let choice = picker.games[0]
    precondition(choice.homeTeam == "San Francisco Giants" && choice.awayTeam == "Los Angeles Dodgers")

    func detail(_ json: String) throws -> WatchSelectedGame {
        try JSONDecoder().decode(WatchSelectedGame.self, from: Data(json.utf8))
    }
    let live = try detail("""
    {"id":111,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"live","home_score":3,"away_score":2,"sport_key":"baseball_mlb","hero_probability":0.64,"hero_probability_away":0.36,"hero_probability_observed_at":"2026-10-03T17:57:00Z","score_observed_at":"2026-10-03T17:59:30Z","espn":{"period":"Bottom 7th","game_clock":null}}
    """)
    // A final payload deliberately retains a probability: terminal authority, rather
    // than the presence of a price, is the view's gate for hiding the live reading.
    let final = try detail("""
    {"id":111,"home_team":"San Francisco Giants","away_team":"Los Angeles Dodgers","status":"completed","home_score":4,"away_score":2,"hero_probability":0.99,"hero_probability_away":0.01,"hero_probability_observed_at":"2026-10-03T17:58:00Z","score_observed_at":"2026-10-03T18:00:00Z"}
    """)
    let second = try detail("""
    {"id":202,"home_team":"Buffalo Bills","away_team":"Kansas City Chiefs","status":"scheduled","hero_probability":0.55,"hero_probability_away":0.45}
    """)
    let transport = FlowDetailTransport([
        (101, .success(live)),
        (111, .failure(URLError(.notConnectedToInternet))),
        (111, .success(final)),
        (202, .success(second)),
    ])
    let selected = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
    selected.select(eventID: choice.id)
    await selected.refresh()
    precondition(selected.selectedEventID == 111 && selected.game?.id == 111,
                 "Discover selection follows a canonical alias returned by detail")
    precondition(selected.game?.homeTeam == choice.homeTeam && selected.game?.homeProbability == 0.64,
                 "The live home probability belongs to the named selected side")
    precondition(selected.game?.isLive == true && selected.game?.liveClockText == "Bottom 7th")
    precondition(selected.game?.observationAge(at: clock) == 30 && selected.game?.probabilityAge(at: clock) == 180,
                 "Score and probability retain independent producer ages")

    let restored = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
    precondition(restored.selectedEventID == 111 && restored.game?.homeProbability == 0.64 && restored.isRestoredReading)
    await restored.refresh()
    precondition(restored.errorMessage?.hasPrefix("Offline.") == true && restored.isRestoredReading)
    precondition(restored.game?.id == 111 && restored.fetchedAt == clock)
    precondition(restored.game?.observationAge(at: clock) == 30 && restored.game?.probabilityAge(at: clock) == 180,
                 "Offline restoration never replaces observation ages with fetch age")
    await restored.refresh()
    precondition(restored.game?.isFinal == true && restored.game?.showsForecast == false && restored.game?.homeScore == 4 && restored.game?.awayScore == 2)
    precondition(restored.selectedEventID == 111 && restored.errorMessage == nil && !restored.isRestoredReading)
    precondition(restored.game?.homeProbability == 0.99,
                 "Final authority survives even when the producer still supplies a price")
    let finalSnapshot = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
    precondition(finalSnapshot.game?.isFinal == true && finalSnapshot.selectedEventID == 111)

    restored.select(eventID: picker.games[1].id)
    precondition(restored.selectedEventID == 202 && restored.game == nil && restored.fetchedAt == nil)
    let changedSnapshot = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
    precondition(changedSnapshot.selectedEventID == 202 && changedSnapshot.game == nil,
                 "Changing the picker selection removes the prior game's persisted reading")
    await restored.refresh()
    precondition(restored.game?.id == 202 && restored.game?.homeTeam == "Buffalo Bills")
    restored.clearSelection()
    let cleared = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
    precondition(restored.selectedEventID == nil && restored.game == nil && restored.fetchedAt == nil)
    precondition(cleared.selectedEventID == nil && cleared.game == nil && !cleared.isRestoredReading)
    precondition(defaults.data(forKey: "bainluck_watch_selected_game_snapshot_v1") == nil,
                 "Clear selection removes the snapshot itself")
    await transport.assertConsumed()
    print("PASS: Discover picker to canonical live detail, named home probability, independent ages, offline restoration, retained final, changed selection, and cleared snapshot")
    try await checkWatchRetryDeadline()
}

@MainActor private final class RetryClock {
    var date = Date(timeIntervalSince1970: 1_800_000_000)
    var elapsed: TimeInterval = 1000
}

@MainActor private func checkWatchRetryDeadline() async throws {
    let suite = "watch-retry-deadline-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let clock = RetryClock()
    let live = try event(4932, extras: ",\"status\":\"live\"")
    let transport = FlowDetailTransport([
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(180))),
        (4932, .success(live)),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(600))),
        (4932, .failure(WatchSelectedGameRequestError.serviceBusy)),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(900))),
        (4933, .failure(WatchSelectedGameRequestError.retryAfter(900))),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(7200))),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(0))),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(-1))),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(.infinity))),
        (4932, .failure(WatchSelectedGameRequestError.retryAfter(.nan))),
    ])
    let store = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock.date }, retryClock: { clock.elapsed })
    store.select(eventID: 4932)
    await store.refresh()
    precondition(store.nextRefreshDelay == 180, "Server delay dominates the first failure backoff")
    clock.date += 7200
    precondition(store.nextRefreshDelay == 180, "A wall-clock correction cannot shorten the server retry deadline")
    clock.date -= 14400
    precondition(store.nextRefreshDelay == 180, "A backward wall-clock correction cannot extend the server retry deadline")
    clock.elapsed += 20
    precondition(store.nextRefreshDelay == 160, "Server delay is a remaining deadline, not a repeated duration")
    var interruptedSleeps: [TimeInterval] = []
    await store.runForegroundRefresh { delay in
        interruptedSleeps.append(delay)
        throw CancellationError()
    }
    let interruptedFetchCount = await transport.fetchCount
    precondition(interruptedSleeps == [160] && interruptedFetchCount == 1,
                 "Foreground restart waits before requesting, and interrupted sleep cannot fetch")
    clock.elapsed += 10
    precondition(store.nextRefreshDelay == 150, "Interrupted foreground wait preserves the deadline")
    var resumedSleeps: [TimeInterval] = []
    await store.runForegroundRefresh { delay in
        resumedSleeps.append(delay)
        if resumedSleeps.count == 1 {
            precondition(delay == 150)
            clock.elapsed += delay
        } else {
            throw CancellationError()
        }
    }
    let resumedFetchCount = await transport.fetchCount
    precondition(resumedFetchCount == 2 && resumedSleeps == [150, 30],
                 "Elapsed deadline permits exactly one request, then the successful live cadence without a second server sleep")
    precondition(store.nextRefreshDelay == 30, "Success clears the server deadline and failure backoff")
    await store.refresh()
    precondition(store.nextRefreshDelay == 600)
    store.allowManualRetry()
    precondition(store.nextRefreshDelay == 30, "Explicit manual retry clears the server deadline")
    await store.refresh()
    precondition(store.nextRefreshDelay == 60, "Manual retry preserves the existing failure backoff")
    await store.refresh()
    precondition(store.nextRefreshDelay == 900)
    store.select(eventID: 4933)
    precondition(store.nextRefreshDelay == 300, "Changing selection clears the prior game's server deadline")
    await store.refresh()
    precondition(store.nextRefreshDelay == 900)
    store.clearSelection()
    precondition(store.nextRefreshDelay == 300, "Clearing selection clears its server deadline")
    store.select(eventID: 4932)
    await store.refresh()
    precondition(store.nextRefreshDelay == 3600, "Server hints are capped at one hour")
    clock.elapsed += 3590
    precondition(store.nextRefreshDelay == 30, "Remaining server deadline cannot shorten ordinary backoff")
    store.allowManualRetry()
    for expected in [60, 120, 240, 300] as [TimeInterval] {
        await store.refresh()
        precondition(store.nextRefreshDelay == expected, "Nonpositive or nonfinite hints use ordinary capped backoff")
    }
    await transport.assertConsumed()
    print("PASS: server retry deadline, interrupted foreground preservation, remaining-delay wait, no double sleep, success/selection/clear reset, explicit manual retry, finite positive validation and one-hour cap")
}
