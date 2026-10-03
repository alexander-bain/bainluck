import Foundation

func event(_ id: Int = 1, extras: String = "") throws -> WatchSelectedGame {
    try JSONDecoder().decode(WatchSelectedGame.self, from: Data("{\"id\":\(id),\"home_team\":\"Home\",\"away_team\":\"Away\"\(extras)}".utf8))
}
actor Stub: WatchSelectedGameTransport {
    var calls: [Int: [CheckedContinuation<WatchSelectedGame, Error>]] = [:]
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        try await withCheckedThrowingContinuation { calls[eventID, default: []].append($0) }
    }
    func waitFor(_ id: Int, count: Int = 1) async { while (calls[id]?.count ?? 0) < count { await Task.yield() } }
    func finish(_ id: Int, result: Result<WatchSelectedGame, Error>) { let continuation = calls[id]?.removeFirst(); continuation?.resume(with: result) }
}

@main struct Checks {
    @MainActor static func main() async throws {
        let suite = "watch-selected-game-tests-\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suite)!
        defer { defaults.removePersistentDomain(forName: suite) }
        let transport = Stub()
        let clock = Date(timeIntervalSince1970: 1_800_000_000)
        let store = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock })
        precondition(store.selectedEventID == nil && store.errorMessage == nil)
        await store.refresh()
        precondition(store.game == nil && !store.isRefreshing)
        store.select(eventID: 1)
        precondition(WatchSelectedGameStore(defaults: defaults).selectedEventID == 1)
        let first = Task { await store.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .success(try event()))
        await first.value
        precondition(store.game?.id == 1 && store.fetchedAt == clock)
        precondition(store.game?.observationAge(at: clock) == nil)
        let failed = Task { await store.refresh() }
        await transport.waitFor(1)
        await transport.finish(1, result: .failure(URLError(.notConnectedToInternet)))
        await failed.value
        precondition(store.game?.id == 1 && store.fetchedAt == clock && store.errorMessage != nil)
        let old = Task { await store.refresh() }
        await transport.waitFor(1)
        store.select(eventID: 2)
        let fresh = Task { await store.refresh() }
        await transport.waitFor(2)
        await transport.finish(2, result: .success(try event(3))) // canonical alias resolution
        await fresh.value
        await transport.finish(1, result: .success(try event()))
        await old.value
        precondition(store.game?.id == 3 && store.selectedEventID == 3 && !store.isRefreshing)
        precondition(WatchSelectedGameStore(defaults: defaults).selectedEventID == 3)
        store.select(eventID: 4)
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
        let live = try event(extras: ",\"status\":\"live\",\"home_score\":10,\"away_score\":0,\"commence_time\":\"2020-01-01T00:00:00Z\"")
        precondition(live.isLive && !live.isFinal)
        let final = try event(extras: ",\"status\":\"completed\"")
        precondition(final.isFinal)
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
        do {
            _ = try JSONDecoder().decode(WatchSelectedGame.self, from: Data("{}".utf8))
            fatalError("Empty success must fail decode")
        } catch is DecodingError {}
        print("PASS: selection persistence, empty/error distinction, retained failure, race fencing, canonical alias, same-selection refresh ordering, cancellation, final status, draw semantics, tolerant optionals, distinct score/probability ages")
    }
}
