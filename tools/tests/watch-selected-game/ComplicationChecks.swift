import Foundation

private actor ComplicationTransport: WatchSelectedGameTransport {
    var results: [Result<WatchSelectedGame, Error>]
    init(_ results: [Result<WatchSelectedGame, Error>]) { self.results = results }
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        precondition(!results.isEmpty)
        return try results.removeFirst().get()
    }
}

private actor ComplicationRaceTransport: WatchSelectedGameTransport {
    private var pending: CheckedContinuation<WatchSelectedGame, Error>?
    func fetch(eventID: Int) async throws -> WatchSelectedGame {
        try await withCheckedThrowingContinuation { pending = $0 }
    }
    func waitForRequest() async { while pending == nil { await Task.yield() } }
    func finish(_ game: WatchSelectedGame) { pending?.resume(returning: game); pending = nil }
}

/// Public saved-reading projection and publication lifecycle; no entitled container or WidgetKit calls.
@MainActor func runComplicationChecks() async throws {
    let clock = ISO8601DateFormatter().date(from: "2026-10-04T18:00:00Z")!
    let observed = clock.addingTimeInterval(-120)
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("watch-complication-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent(WatchComplicationSnapshot.filename)
    func detail(_ extras: String) throws -> WatchSelectedGame {
        try JSONDecoder().decode(WatchSelectedGame.self, from: Data("{\"id\":101,\"home_team\":\"San Francisco Giants\",\"away_team\":\"Los Angeles Dodgers\",\(extras)}".utf8))
    }
    let live = try detail("\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.455,\"hero_probability_away\":0.545,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\"")
    let projected = WatchComplicationProjection.snapshot(game: live, savedAt: clock)!
    precondition(projected.title == "San Francisco Giants win")
    precondition(projected.detail == "\(live.homeProbabilityText!) · Live" && live.homeRenderedPercent == 45,
                 "Complication must reuse the app's complementary-pair rounding")
    precondition(projected.observedAt == observed && projected.savedAt == clock,
                 "Publication cannot replace producer observation time with fetch time")
    precondition(WatchComplicationPublisher.write(projected, to: directory, now: clock))
    let shared = WatchComplicationSnapshot.read(from: directory, now: clock)!
    precondition(shared.eventID == 101 && shared.title == projected.title && shared.detail == projected.detail)
    precondition(shared.observedAt == observed)
    let originalBytes = try Data(contentsOf: file)
    let laterFetch = WatchComplicationSnapshot(eventID: projected.eventID, title: projected.title,
                                               detail: projected.detail, observedAt: observed,
                                               savedAt: clock.addingTimeInterval(60))
    precondition(!WatchComplicationPublisher.write(laterFetch, to: directory, now: clock.addingTimeInterval(60)),
                 "A repeated producer observation must not trigger rewrite or reload")
    let repeatedBytes = try Data(contentsOf: file)
    precondition(repeatedBytes == originalBytes)
    precondition(WatchComplicationSnapshot.read(from: directory, now: clock.addingTimeInterval(60))?.savedAt == clock)

    let final = try detail("\"status\":\"completed\",\"home_score\":4,\"away_score\":2,\"hero_probability\":0.99,\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
    let finalProjection = WatchComplicationProjection.snapshot(game: final, savedAt: clock)!
    precondition(finalProjection.title == "San Francisco Giants won" && finalProjection.detail == "Final · 4–2")
    precondition(!finalProjection.detail.contains("%") && finalProjection.observedAt == observed)
    let missingLiveTimestamp = try detail("\"status\":\"live\",\"hero_probability\":0.6")
    precondition(WatchComplicationProjection.snapshot(game: missingLiveTimestamp, savedAt: clock) == nil,
                 "Missing producer timestamp falls back to no saved complication")
    let missingFinalTimestamp = try detail("\"status\":\"completed\",\"home_score\":4,\"away_score\":2")
    precondition(WatchComplicationProjection.snapshot(game: missingFinalTimestamp, savedAt: clock) == nil)
    precondition(WatchComplicationSnapshot.read(from: nil, now: clock) == nil)
    precondition(!WatchComplicationPublisher.write(projected, to: nil, now: clock))
    try Data("not JSON".utf8).write(to: file)
    precondition(WatchComplicationSnapshot.read(from: directory, now: clock) == nil)
    try Data(repeating: 32, count: WatchComplicationSnapshot.maximumBytes + 1).write(to: file)
    precondition(WatchComplicationSnapshot.read(from: directory, now: clock) == nil)
    for invalid in [
        WatchComplicationSnapshot(version: 2, eventID: 101, title: "Giants", detail: "45%", observedAt: observed, savedAt: clock),
        WatchComplicationSnapshot(eventID: 0, title: "Giants", detail: "45%", observedAt: observed, savedAt: clock),
        WatchComplicationSnapshot(eventID: 101, title: " ", detail: "45%", observedAt: observed, savedAt: clock),
        WatchComplicationSnapshot(eventID: 101, title: "Giants", detail: " ", observedAt: observed, savedAt: clock),
        WatchComplicationSnapshot(eventID: 101, title: "Giants", detail: "45%", observedAt: clock.addingTimeInterval(1), savedAt: clock),
        WatchComplicationSnapshot(eventID: 101, title: "Giants", detail: "45%", observedAt: observed, savedAt: clock.addingTimeInterval(1)),
    ] {
        _ = WatchComplicationPublisher.write(projected, to: directory, now: clock)
        precondition(WatchComplicationPublisher.write(invalid, to: directory, now: clock))
        precondition(WatchComplicationSnapshot.read(from: directory, now: clock) == nil)
    }
    precondition(WatchComplicationPublisher.write(projected, to: directory, now: clock))
    precondition(WatchComplicationPublisher.write(nil, to: directory, now: clock))
    precondition(!WatchComplicationPublisher.write(nil, to: directory, now: clock), "Repeated tombstone is a no-op")
    precondition(WatchComplicationSnapshot.read(from: directory, now: clock) == nil,
                 "Atomic tombstone invalidates the old reading")

    let suite = "watch-complication-store-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    var published: [(WatchSelectedGame?, Date?)] = []
    let transport = ComplicationTransport([.success(live), .failure(URLError(.notConnectedToInternet))])
    let store = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock }, publish: { published.append(($0, $1)) })
    precondition(published.count == 1 && published[0].0 == nil && published[0].1 == nil)
    store.select(eventID: 101)
    precondition(published.count == 2 && published.last!.0 == nil)
    await store.refresh()
    precondition(published.count == 3 && published.last!.0?.id == 101 && published.last!.1 == clock)
    await store.refresh()
    precondition(published.count == 3, "Failed refresh must not publish a new observation")
    var restoredPublications: [(WatchSelectedGame?, Date?)] = []
    let restored = WatchSelectedGameStore(transport: transport, defaults: defaults, now: { clock.addingTimeInterval(60) }, publish: { restoredPublications.append(($0, $1)) })
    precondition(restored.isRestoredReading && restoredPublications.count == 1)
    precondition(restoredPublications[0].0?.id == 101 && restoredPublications[0].1 == clock,
                 "Restore republishes the original saved time, not the restoration clock")
    store.select(eventID: 202)
    precondition(published.count == 4 && published.last!.0 == nil && published.last!.1 == nil)
    store.clearSelection()
    precondition(published.count == 5 && published.last!.0 == nil)

    let race = ComplicationRaceTransport()
    let raced = WatchSelectedGameStore(transport: race, defaults: defaults, now: { clock }, publish: { published.append(($0, $1)) })
    raced.select(eventID: 101)
    let request = Task { await raced.refresh() }
    await race.waitForRequest()
    raced.select(eventID: 202)
    let countAfterInvalidation = published.count
    await race.finish(live)
    await request.value
    precondition(published.count == countAfterInvalidation && raced.game == nil,
                 "Late response for the old selection cannot republish its complication")
    print("PASS: complication shared projection, producer age, final winner, fail-closed reads, tombstone, store publication and stale-response suppression")
}
