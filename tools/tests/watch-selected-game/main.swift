import Foundation

func event(_ id: Int = 1, extras: String = "") throws -> WatchSelectedGame {
    try JSONDecoder().decode(WatchSelectedGame.self, from: Data("{\"id\":\(id),\"home_team\":\"Home\",\"away_team\":\"Away\"\(extras)}".utf8))
}
actor Stub: WatchSelectedGameTransport {
    var calls: [Int: [CheckedContinuation<WatchSelectedGame, Error>]] = [:]
    private(set) var fetchCount = 0
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        fetchCount += 1
        return try await withCheckedThrowingContinuation { calls[eventID, default: []].append($0) }
    }
    func waitFor(_ id: Int, count: Int = 1) async { while (calls[id]?.count ?? 0) < count { await Task.yield() } }
    func finish(_ id: Int, result: Result<WatchSelectedGame, Error>) { let continuation = calls[id]?.removeFirst(); continuation?.resume(with: result) }
}

@main struct Checks {
    @MainActor static func main() async throws {
        try await runComplicationChecks()
        try runCircularComplicationChecks()
        try checkWatchProbabilityFormatting()
        let suite = "watch-selected-game-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let transport = Stub()
        let clock = Date(timeIntervalSince1970: 1_800_000_000)
        let ageCases: [(TimeInterval, String, String, Bool)] = [
            (0, "0s ago", "0 seconds ago", false),
            (59, "59s ago", "59 seconds ago", false),
            (60, "1m ago", "1 minute ago", false),
            (119, "1m ago", "1 minute ago", false),
            (120, "2m ago", "2 minutes ago", false),
            (121, "2m ago", "2 minutes ago", true),
            (3599, "59m ago", "59 minutes ago", true),
            (3600, "1h ago", "1 hour ago", true),
            (86399, "23h ago", "23 hours ago", true),
            (86400, "1d ago", "1 day ago", true),
            (1, "1s ago", "1 second ago", false),
            (7200, "2h ago", "2 hours ago", true),
            (172800, "2d ago", "2 days ago", true),
        ]
        for (seconds, compact, spoken, stale) in ageCases {
            let age = WatchObservationAge(observedAt: clock.addingTimeInterval(-seconds), now: clock)
            precondition(age.compactText == compact, "Compact observation age at \(seconds) seconds")
            precondition(age.spokenText == spoken, "Spoken observation age at \(seconds) seconds")
            precondition(age.isStale == stale, "Staleness starts strictly after 120 seconds")
        }
        let invalidObservationDates: [Date?] = [
            nil,
            clock.addingTimeInterval(1),
            Date(timeIntervalSinceReferenceDate: .nan),
            Date(timeIntervalSinceReferenceDate: .infinity),
            Date(timeIntervalSinceReferenceDate: -.infinity),
        ]
        for observedAt in invalidObservationDates {
            let age = WatchObservationAge(observedAt: observedAt, now: clock)
            precondition(age.compactText == nil && age.spokenText == nil && !age.isStale,
                         "Missing, future, or nonfinite observations cannot claim an age")
        }
        let store = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
        var telemetry: [(String, Int, Int)] = []
        store.telemetry = { outcome, ms, count in telemetry.append((outcome, ms, count)) }
        precondition(store.selectedEventID == nil && store.errorMessage == nil)
        await store.refresh()
        precondition(store.game == nil && !store.isRefreshing)
        precondition(telemetry.isEmpty, "No request means no refresh measurement")
        store.select(eventID: 1)
        precondition(WatchSelectedGameStore(defaults: defaults).selectedEventID == 1)
        let first = Task { await store.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .success(try event()))
        await first.value
        precondition(store.game?.id == 1 && store.fetchedAt == clock)
        precondition(telemetry.count == 1 && telemetry[0].0 == "success" && telemetry[0].2 == 1)
        precondition(telemetry[0].1 >= 0, "Duration uses monotonic time")
        precondition(store.game?.observationAge(at: clock) == nil)
        let restored = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
        precondition(restored.game?.id == 1 && restored.fetchedAt == clock && restored.isRestoredReading)
        let restoredFailure = Task { await restored.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .failure(URLError(.notConnectedToInternet)))
        await restoredFailure.value
        precondition(restored.game?.id == 1 && restored.isRestoredReading && restored.errorMessage != nil)
        let failed = Task { await store.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .failure(URLError(.notConnectedToInternet)))
        await failed.value
        precondition(store.game?.id == 1 && store.fetchedAt == clock && store.errorMessage != nil)
        precondition(telemetry.last?.0 == "offline" && telemetry.last?.2 == 0)
        let retainedError = store.errorMessage
        let interruptedRetry = Task { await store.refresh() }
        await transport.waitFor(1)
        precondition(store.errorMessage == retainedError && store.isRefreshing, "Retry is not recovery")
        interruptedRetry.cancel()
        await transport.finish(1, result: .failure(URLError(.cancelled)))
        await interruptedRetry.value
        precondition(telemetry.last?.0 == "cancelled", "Cancellation never becomes a success or network failure")
        precondition(store.errorMessage == retainedError && !store.isRefreshing)
        let old = Task { await store.refresh() }
        await transport.waitFor(1)
        store.select(eventID: 2)
        let fresh = Task { await store.refresh() }
        await transport.waitFor(2)
        await transport.finish(2, result: .success(try event(3))) // canonical alias resolution
        await fresh.value
        await transport.finish(1, result: .success(try event()))
        await old.value
        precondition(telemetry.suffix(2).map { $0.0 } == ["success", "cancelled"],
                     "A superseded result cannot claim a fresh reading")
        precondition(store.game?.id == 3 && store.selectedEventID == 3 && !store.isRefreshing)
        precondition(WatchSelectedGameStore(defaults: defaults).selectedEventID == 3)
        store.select(eventID: 4)
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
        let olderRefresh = Task { await store.refresh() }
        await transport.waitFor(4)
        let latestRefresh = Task { await store.refresh() }
        await transport.waitFor(4, count: 2)
        await transport.finish(4, result: .success(try event(4, extras: ",\"home_score\":1")))
        await olderRefresh.value
        precondition(store.game == nil && store.isRefreshing)
        await transport.finish(4, result: .success(try event(4, extras: ",\"home_score\":2")))
        await latestRefresh.value
        precondition(store.game?.homeScore == 2)
        let cancelled = Task { await store.refresh() }
        await transport.waitFor(4)
        cancelled.cancel()
        await transport.finish(4, result: .success(try event(4, extras: ",\"home_score\":3")))
        await cancelled.value
        precondition(store.game?.homeScore == 2 && store.errorMessage == nil && !store.isRefreshing)
        store.clearSelection()
        precondition(WatchSelectedGameStore(defaults: defaults).selectedEventID == nil)
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
        defaults.set(4, forKey: "bainluck_watch_selected_event_id")
        defaults.set(Data("corrupt".utf8), forKey: "bainluck_watch_selected_game_snapshot_v1")
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
        let live = try event(extras: ",\"status\":\"live\",\"home_score\":10,\"away_score\":0,\"commence_time\":\"2020-01-01T00:00:00Z\"")
        precondition(live.isLive && !live.isFinal)
        let liveAlias = try event(extras: ",\"status\":\"in_progress\"")
        precondition(liveAlias.isLive && liveAlias.stateLabel == "Live" && !liveAlias.isFinal,
                     "Supported in_progress alias has the same detail live semantics")
        precondition(WatchSelectedGame.stateLabel(for: "in_progress") == "Live",
                     "Picker and detail use the same live alias label")
        for status in ["scheduled", "closed", "unknown"] {
            let nonLive = try event(extras: ",\"status\":\"\(status)\"")
            precondition(!nonLive.isLive, "Only supported live states get live cadence and freshness treatment")
        }
        let final = try event(extras: ",\"status\":\"completed\"")
        precondition(final.isFinal && !final.showsForecast)
        let closed = try event(extras: ",\"status\":\"closed\",\"home_score\":3,\"away_score\":1,\"hero_probability\":0.9")
        precondition(closed.isClosed && !closed.isFinal && !closed.showsForecast)
        precondition(closed.stateLabel == "Closed · result unverified")
        precondition(WatchSelectedGame.stateLabel(for: "closed") == closed.stateLabel, "Picker and detail must agree")
        let restoredClosed = try JSONDecoder().decode(WatchSelectedGame.self, from: JSONEncoder().encode(closed))
        precondition(restoredClosed.isClosed && !restoredClosed.showsForecast && !restoredClosed.isFinal)
        precondition(live.showsForecast && !live.isClosed)
        let draw = try event(extras: ",\"current_odds\":{\"home_probability\":0.4,\"away_probability\":0.3,\"draw_probability\":0.3}")
        precondition(draw.homeProbability == 0.4 && draw.awayProbability == 0.3 && draw.drawProbability == 0.3)
        let homeOnly = try event(extras: ",\"current_odds\":{\"home_probability\":0.4,\"away_probability\":null}")
        precondition(homeOnly.awayProbability == nil && homeOnly.drawProbability == nil)
        let malformed = try event(extras: ",\"home_score\":\"unknown\",\"score_observed_at\":\"bad-date\",\"current_odds\":{\"home_probability\":2}")
        precondition(malformed.homeScore == nil && malformed.scoreObservedAt == nil && malformed.homeProbability == nil)
        let hero = try event(extras: ",\"hero_probability\":0.6,\"hero_probability_away\":0.4,\"hero_probability_observed_at\":\"2026-01-01T00:00:00Z\",\"score_observed_at\":\"2026-02-01T00:00:00Z\",\"espn\":{\"period\":\"Top 3rd\",\"game_clock\":\"1:23\",\"win_probability\":0.2}")
        precondition(hero.homeProbability == 0.6 && hero.awayProbability == 0.4)
        precondition(hero.probabilityAge(at: clock)! > hero.observationAge(at: clock)!)
        precondition(hero.period == "Top 3rd" && hero.gameClock == "1:23")
        let baseball = try event(extras: ",\"espn\":{\"period\":\"Bottom 3rd\",\"game_clock\":null}")
        precondition(baseball.liveClockText == "Bottom 3rd", "Keep the half inning; never turn it into a quarter")
        let football = try event(extras: ",\"espn\":{\"period\":\"3rd Quarter\",\"game_clock\":\"1:23\"}")
        precondition(football.liveClockText == "Q3 1:23")
        precondition(homeOnly.probabilityAge(at: clock) == nil)
        let invalidHero = try event(extras: ",\"hero_probability\":2,\"hero_probability_observed_at\":\"2026-01-01T00:00:00Z\",\"current_odds\":{\"home_probability\":0.4,\"away_probability\":0.6}")
        precondition(invalidHero.homeProbability == 0.4 && invalidHero.awayProbability == 0.6 && invalidHero.probabilityObservedAt == nil)
        let stamped = try event(extras: ",\"score_observed_at\":\"2026-01-01T00:00:00.123456Z\"")
        precondition(stamped.observationAge(at: clock) != nil)
        precondition(stamped.observationAge(at: Date(timeIntervalSince1970: 0)) == nil)
        let awayOnly = try event(extras: ",\"current_odds\":{\"away_probability\":0.7}")
        for reading in [hero, draw, homeOnly, invalidHero, awayOnly, stamped, final, baseball] {
            let data = try JSONEncoder().encode(reading)
            let copy = try JSONDecoder().decode(WatchSelectedGame.self, from: data)
            precondition(copy.id == reading.id && copy.status == reading.status)
            precondition(copy.homeProbability == reading.homeProbability && copy.awayProbability == reading.awayProbability && copy.drawProbability == reading.drawProbability)
            precondition(copy.probabilityObservedAt == reading.probabilityObservedAt)
            // ISO serialization preserves milliseconds; submillisecond precision is irrelevant to displayed ages.
            if let original = reading.scoreObservedAt { precondition(abs(copy.scoreObservedAt!.timeIntervalSince(original)) < 0.001) }
            precondition(copy.liveClockText == reading.liveClockText)
        }
        let cacheKey = "bainluck_watch_selected_game_snapshot_v1"
        func cache(_ reading: WatchSelectedGame, version: Int = 1) throws -> Data {
            let object = try JSONSerialization.jsonObject(with: JSONEncoder().encode(reading))
            return try JSONSerialization.data(withJSONObject: ["version": version, "game": object, "fetchedAt": clock.timeIntervalSinceReferenceDate])
        }
        defaults.set(1, forKey: "bainluck_watch_selected_event_id")
        defaults.set(try cache(hero), forKey: cacheKey)
        let savedHero = WatchSelectedGameStore(transport: transport, defaults: defaults)
        precondition(savedHero.game?.probabilityObservedAt == hero.probabilityObservedAt && savedHero.game?.scoreObservedAt == hero.scoreObservedAt && savedHero.isRestoredReading)
        let confirmation = Task { await savedHero.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .success(final))
        await confirmation.value
        precondition(savedHero.game?.isFinal == true && !savedHero.isRestoredReading)
        precondition(WatchSelectedGameStore(defaults: defaults).game?.isFinal == true)
        let correction = Task { await savedHero.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .success(try event(extras: ",\"status\":\"completed\",\"home_score\":0")))
        await correction.value
        precondition(savedHero.game?.homeScore == 0 && savedHero.game?.isFinal == true)
        let afterClear = Task { await savedHero.refresh() }
        await transport.waitFor(1)
        savedHero.clearSelection()
        await transport.finish(1, result: .success(hero))
        await afterClear.value
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil && defaults.data(forKey: cacheKey) == nil)
        defaults.set(1, forKey: "bainluck_watch_selected_event_id")
        defaults.set(try cache(hero, version: 2), forKey: cacheKey)
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
        defaults.set(try cache(try event(2)), forKey: cacheKey)
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
        savedHero.clearSelection()
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
        do {
            _ = try JSONDecoder().decode(WatchSelectedGame.self, from: Data("{}".utf8))
            fatalError("Empty success must fail decode")
        } catch is DecodingError {}
        let errorTransport = Stub()
        let errorStore = WatchSelectedGameStore(transport: errorTransport, defaults: defaults)
        errorStore.select(eventID: 20)
        for (failure, expected) in [(WatchSelectedGameRequestError.unavailable as Error, "Selected game is unavailable."),
                                    (WatchSelectedGameRequestError.serviceBusy as Error, "Service temporarily busy."),
                                    (WatchSelectedGameRequestError.invalidResponse as Error, "Couldn't read this game."),
                                    (URLError(.timedOut) as Error, "Connection timed out.")] {
            let request = Task { await errorStore.refresh() }
            await errorTransport.waitFor(20)
            await errorTransport.finish(20, result: .failure(failure))
            await request.value
            precondition(errorStore.errorMessage?.hasPrefix(expected) == true && errorStore.selectedEventID == 20)
        }
        let recovery = Task { await errorStore.refresh() }
        await errorTransport.waitFor(20)
        await errorTransport.finish(20, result: .success(try event(20)))
        await recovery.value
        precondition(errorStore.errorMessage == nil)
        errorStore.clearSelection()
        try await checkWatchHTTPTransport()
        checkWatchLaunchRoute()
        checkWatchContinuation()
        try await checkWatchGamePicker()
        try await checkWatchGameFlow()
        try await checkWatchSelectedIdentity()
        let lifecycleTransport = Stub()
        let lifecycle = WatchSelectedGameStore(transport: lifecycleTransport, defaults: defaults, now: { clock }, retryClock: { 1000 })
        lifecycle.select(eventID: 10)
        precondition(lifecycle.nextRefreshDelay == 300, "A game without a live reading uses the five-minute cadence")
        func refreshLifecycle(_ result: Result<WatchSelectedGame, Error>) async {
            let request = Task { await lifecycle.refresh() }
            await lifecycleTransport.waitFor(10)
            await lifecycleTransport.finish(10, result: result)
            await request.value
        }
        for delay in [30, 60, 120, 240, 300, 300] as [TimeInterval] {
            await refreshLifecycle(.failure(URLError(.notConnectedToInternet)))
            precondition(lifecycle.nextRefreshDelay == delay, "Repeated failures back off to a five-minute cap")
        }
        await refreshLifecycle(.success(try event(10, extras: ",\"status\":\"live\"")))
        precondition(lifecycle.nextRefreshDelay == 30, "Successful live refresh resets failure backoff")
        await refreshLifecycle(.failure(URLError(.notConnectedToInternet)))
        precondition(lifecycle.nextRefreshDelay == 30, "The next failure starts again at thirty seconds")
        await refreshLifecycle(.failure(URLError(.notConnectedToInternet)))
        precondition(lifecycle.nextRefreshDelay == 60)
        await refreshLifecycle(.success(try event(10, extras: ",\"status\":\"completed\"")))
        precondition(lifecycle.nextRefreshDelay == 300, "Successful final refresh returns to the nonlive cadence")
        await refreshLifecycle(.failure(URLError(.notConnectedToInternet)))
        lifecycle.clearSelection()
        precondition(lifecycle.nextRefreshDelay == 300, "Clearing selection resets the failure delay")
        lifecycle.select(eventID: 10)
        await refreshLifecycle(.failure(URLError(.notConnectedToInternet)))
        precondition(lifecycle.nextRefreshDelay == 30, "A new selection starts with the first failure delay")
        for (status, delay) in [("live", 30), ("in_progress", 30), ("scheduled", 300), ("closed", 300), ("unknown", 300)] as [(String, TimeInterval)] {
            var sleeps: [TimeInterval] = []
            lifecycle.allowManualRetry()
            let loop = Task {
                await lifecycle.runForegroundRefresh { interval in
                    sleeps.append(interval)
                    throw CancellationError()
                }
            }
            await lifecycleTransport.waitFor(10)
            await lifecycleTransport.finish(10, result: .success(try event(10, extras: ",\"status\":\"\(status)\"")))
            await loop.value
            precondition(sleeps == [delay], "Throwing sleep exits the loop after its immediate refresh")
        }
        lifecycle.allowManualRetry()
        let beforeSleepCancellation = await lifecycleTransport.fetchCount
        let cancelDuringSleep = Task {
            await lifecycle.runForegroundRefresh { _ in
                withUnsafeCurrentTask { $0?.cancel() }
                // Even a sleeper that returns normally after cancellation cannot start another request.
            }
        }
        await lifecycleTransport.waitFor(10)
        await lifecycleTransport.finish(10, result: .success(try event(10)))
        await cancelDuringSleep.value
        let afterSleepCancellation = await lifecycleTransport.fetchCount
        precondition(afterSleepCancellation == beforeSleepCancellation + 1)
        let beforeCancellation = await lifecycleTransport.fetchCount
        var cancelledSleeps = 0
        let cancelledLoop = Task {
            await lifecycle.runForegroundRefresh { _ in
                cancelledSleeps += 1
                throw CancellationError()
            }
        }
        cancelledLoop.cancel() // Main-actor task cannot enter until this actor yields.
        await cancelledLoop.value
        let afterCancellation = await lifecycleTransport.fetchCount
        precondition(afterCancellation == beforeCancellation && cancelledSleeps == 0, "Cancellation before entry performs neither fetch nor sleep")
        let uiSuite = "watch-ui-fixture-check-\(UUID().uuidString)"
        defer { UserDefaults(suiteName: uiSuite)?.removePersistentDomain(forName: uiSuite) }
        let uiFixture = WatchUIFixture(offline: false, suite: uiSuite)
        let uiBatch = try await uiFixture.fetchGames()
        precondition(uiBatch.games.map(\.id) == [101, 202] && uiBatch.omittedGameCount == 0)
        let uiStore = uiFixture.makeStore()
        uiStore.select(eventID: 101)
        await uiStore.refresh()
        precondition(uiStore.game?.homeTeam == "San Francisco Giants" && uiStore.game?.homeProbability == 0.64)
        let offlineFixture = WatchUIFixture(offline: true, suite: uiSuite)
        let uiRestored = offlineFixture.makeStore()
        await uiRestored.refresh()
        precondition(uiRestored.isRestoredReading && uiRestored.game?.id == 101 && uiRestored.errorMessage == "Offline. Try again.")
        let secondFixture = try await uiFixture.fetch(eventID: 202)
        precondition(secondFixture.homeTeam == "Buffalo Bills" && secondFixture.homeProbability == 0.55)
        print("PASS: UI fixture decodes both choices and restores the chosen reading offline in isolated defaults")
        print("PASS: cold offline snapshot restoration, cache integrity, observation-clock round trips, selection persistence, empty/error distinction, retained failure, race fencing, canonical alias, same-selection refresh ordering, cancellation, final status, draw semantics, tolerant optionals, distinct score/probability ages")
        print("PASS: foreground immediate refresh, live/nonlive cadence, capped failure backoff, success and selection reset, throwing-sleep exit, cancellation before entry")
        print("PASS: deterministic compact and spoken observation ages, unit boundaries, strict two-minute stale threshold, missing/future/nonfinite observations")
    }
}
