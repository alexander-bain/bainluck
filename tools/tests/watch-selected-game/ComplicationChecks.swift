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
    let soccer = try detail("\"status\":\"live\",\"sport\":\"soccer_epl\",\"hero_probability\":0.455,\"hero_probability_away\":0.545,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\"")
    let soccerProjection = WatchComplicationProjection.snapshot(game: soccer, savedAt: clock)!
    precondition(soccerProjection.detail == "46% · Live" && soccerProjection.observedAt == observed,
                 "Draw-priced soccer keeps scalar 46 percent instead of complementary 45")
    let homeOnly = try detail("\"status\":\"scheduled\",\"hero_probability\":0.455,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\"")
    precondition(homeOnly.awayProbability == nil)
    precondition(WatchComplicationProjection.snapshot(game: homeOnly, savedAt: clock)?.detail == "46% · Scheduled",
                 "Missing away stays missing and uses scalar home rounding")
    let zero = try detail("\"status\":\"live\",\"hero_probability\":0,\"hero_probability_away\":1,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\"")
    precondition(WatchComplicationProjection.snapshot(game: zero, savedAt: clock)?.detail == "0% · Live",
                 "A valid zero forecast is not missing data")
    for status in ["closed", "unknown", "delayed"] {
        let unsupported = try detail("\"status\":\"\(status)\",\"hero_probability\":0.6,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
        precondition(WatchComplicationProjection.snapshot(game: unsupported, savedAt: clock) == nil,
                     "Closed or unknown states fall back rather than publish a forecast")
    }
    let awayWin = try detail("\"status\":\"final\",\"home_score\":2,\"away_score\":4,\"hero_probability\":0.8,\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
    let awayProjection = WatchComplicationProjection.snapshot(game: awayWin, savedAt: clock)!
    precondition(awayProjection.title == "Los Angeles Dodgers won" && awayProjection.detail == "Final · 4–2")
    precondition(!awayProjection.detail.contains("%") && awayProjection.observedAt == observed)
    let tie = try detail("\"status\":\"completed\",\"home_score\":2,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
    let tieProjection = WatchComplicationProjection.snapshot(game: tie, savedAt: clock)!
    precondition(tieProjection.title == "Los Angeles Dodgers at San Francisco Giants" && tieProjection.detail == "Final · tied 2–2")
    precondition(!tieProjection.title.contains("won") && tieProjection.observedAt == observed)
    for scores in ["", "\"home_score\":4,", "\"away_score\":2,"] {
        let incompleteFinal = try detail("\"status\":\"completed\",\(scores)\"hero_probability\":0.9,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
        precondition(WatchComplicationProjection.snapshot(game: incompleteFinal, savedAt: clock) == nil,
                     "A final missing either score cannot fall back to a forecast or invent a winner")
    }

    let scoreFields = "\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\""
    let scoreClock = clock.addingTimeInterval(-60)
    for status in ["live", "in_progress"] {
        for probabilityFields in ["", ",\"hero_probability\":0.6",
                                  ",\"hero_probability\":0.6,\"hero_probability_observed_at\":\"invalid\"",
                                  ",\"hero_probability\":0.6,\"hero_probability_observed_at\":\"2026-10-04T18:01:00Z\""] {
            let scoreGame = try detail("\"status\":\"\(status)\",\(scoreFields)\(probabilityFields)")
            let scoreProjection = WatchComplicationProjection.snapshot(game: scoreGame, savedAt: clock)!
            precondition(scoreProjection.title == "Los Angeles Dodgers at San Francisco Giants")
            precondition(scoreProjection.detail == "Score 2–3 · Live",
                         "Score order follows the named away-at-home matchup")
            precondition(scoreProjection.observedAt == scoreClock && scoreProjection.savedAt == clock,
                         "Score fallback retains score observation time independently of probability/fetch clocks")
            precondition(!scoreProjection.detail.contains("%"))
            if probabilityFields.isEmpty {
                let laterSavedScore = WatchComplicationProjection.snapshot(game: scoreGame, savedAt: clock.addingTimeInterval(3600))!
                precondition(laterSavedScore.observedAt == scoreClock && laterSavedScore.savedAt == clock.addingTimeInterval(3600),
                             "Advancing only fetch/save time never refreshes score observation time")
            }
        }
    }
    let liveZero = try detail("\"status\":\"live\",\"home_score\":0,\"away_score\":0,\"score_observed_at\":\"2026-10-04T17:59:00Z\"")
    precondition(WatchComplicationProjection.snapshot(game: liveZero, savedAt: clock)?.detail == "Score 0–0 · Live",
                 "Valid observed live zero scores are real readings")
    let preferredGame = try detail("\"status\":\"live\",\(scoreFields),\"hero_probability\":0.6,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\"")
    let preferred = WatchComplicationProjection.snapshot(game: preferredGame, savedAt: clock)!
    precondition(preferred.title == "San Francisco Giants win" && preferred.detail == "60% · Live")
    precondition(preferred.observedAt == observed, "Valid probability remains preferred even with a newer score")
    for rejectedFields in [
        "\"home_score\":3,\"away_score\":2",
        "\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"invalid\"",
        "\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T18:01:00Z\"",
        "\"home_score\":3,\"score_observed_at\":\"2026-10-04T17:59:00Z\"",
        "\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\"",
        "\"home_score\":-1,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\"",
        "\"home_score\":3,\"away_score\":-1,\"score_observed_at\":\"2026-10-04T17:59:00Z\"",
    ] {
        let rejectedGame = try detail("\"status\":\"live\",\(rejectedFields)")
        precondition(WatchComplicationProjection.snapshot(game: rejectedGame, savedAt: clock) == nil,
                     "Unverified score/timestamp cannot become a saved complication")
    }
    for status in ["scheduled", "upcoming", "pregame", "closed"] {
        let notLive = try detail("\"status\":\"\(status)\",\"home_score\":0,\"away_score\":0,\"score_observed_at\":\"2026-10-04T17:59:00Z\"")
        precondition(WatchComplicationProjection.snapshot(game: notLive, savedAt: clock) == nil,
                     "Pregame zero scores and closed rows cannot masquerade as a live score")
    }

    for scores in ["\"home_score\":-1,\"away_score\":2", "\"home_score\":3,\"away_score\":-1"] {
        let negativeFinal = try detail("\"status\":\"final\",\(scores),\"score_observed_at\":\"2026-10-04T17:59:00Z\"")
        precondition(WatchComplicationProjection.snapshot(game: negativeFinal, savedAt: clock) == nil,
                     "Negative final scores cannot establish a winner")
    }
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
    // Drive the real publication hook into ordinary temporary shared bytes.
    // This checks the transition, not merely the projection of isolated payloads.
    defaults.removePersistentDomain(forName: suite)
    let finalReading = try detail("\"status\":\"completed\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\"")
    // Same producer timestamp is intentional: corrections are authoritative even
    // without a newer clock, and must replace the already displayed winner.
    let correctedFinal = try detail("\"status\":\"completed\",\"home_score\":1,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\"")
    var publicationCount = 0
    let writeShared: (WatchSelectedGame?, Date?) -> Void = { game, savedAt in
        publicationCount += 1
        let snapshot = game.flatMap { game in savedAt.flatMap { WatchComplicationProjection.snapshot(game: game, savedAt: $0) } }
        WatchComplicationPublisher.write(snapshot, to: directory, now: clock.addingTimeInterval(60))
    }
    let transitions = ComplicationTransport([.success(live), .success(finalReading), .success(correctedFinal)])
    let seeded = WatchSelectedGameStore(transport: transitions, defaults: defaults, now: { clock }, publish: writeShared)
    seeded.select(eventID: 101)
    await seeded.refresh()
    let restoredFresh = WatchSelectedGameStore(transport: transitions, defaults: defaults,
                                               now: { clock.addingTimeInterval(60) }, publish: writeShared)
    precondition(restoredFresh.isRestoredReading)
    precondition(WatchComplicationSnapshot.read(from: directory, now: clock.addingTimeInterval(60))?.observedAt == observed)
    await restoredFresh.refresh()
    precondition(!restoredFresh.isRestoredReading && restoredFresh.game?.isFinal == true)
    precondition(restoredFresh.fetchedAt == clock.addingTimeInterval(60))
    let freshShared = WatchComplicationSnapshot.read(from: directory, now: clock.addingTimeInterval(60))!
    precondition(freshShared.title == "San Francisco Giants won" && freshShared.detail == "Final · 4–2")
    await restoredFresh.refresh()
    let correctedShared = WatchComplicationSnapshot.read(from: directory, now: clock.addingTimeInterval(60))!
    precondition(correctedShared.title == "Los Angeles Dodgers won" && correctedShared.detail == "Final · 2–1")
    precondition(correctedShared.observedAt == freshShared.observedAt,
                 "Corrected final replaces both cached and shared winner at the same producer clock")
    precondition(WatchSelectedGameStore(defaults: defaults).game?.homeScore == 1)

    let clearRace = ComplicationRaceTransport()
    let clearing = WatchSelectedGameStore(transport: clearRace, defaults: defaults, now: { clock }, publish: writeShared)
    let late = Task { await clearing.refresh() }
    await clearRace.waitForRequest()
    clearing.clearSelection()
    let countAfterClear = publicationCount
    await clearRace.finish(finalReading)
    await late.value
    precondition(publicationCount == countAfterClear && clearing.game == nil && clearing.selectedEventID == nil)
    precondition(WatchComplicationSnapshot.read(from: directory, now: clock.addingTimeInterval(60)) == nil,
                 "Late successful response after clear cannot resurrect the shared complication")
    precondition(WatchSelectedGameStore(defaults: defaults).game == nil)

    // Rejected app caches must also tombstone a formerly valid shared reading.
    let cacheKey = "bainluck_watch_selected_game_snapshot_v1"
    let encodedGame = try JSONSerialization.jsonObject(with: JSONEncoder().encode(live))
    for (version, selectedID) in [(2, 101), (1, 202)] {
        defaults.set(selectedID, forKey: "bainluck_watch_selected_event_id")
        let badCache = try JSONSerialization.data(withJSONObject: ["version": version, "game": encodedGame,
                                                                 "fetchedAt": clock.timeIntervalSinceReferenceDate])
        defaults.set(badCache, forKey: cacheKey)
        WatchComplicationPublisher.write(projected, to: directory, now: clock)
        let rejected = WatchSelectedGameStore(defaults: defaults, now: { clock }, publish: writeShared)
        precondition(rejected.game == nil && !rejected.isRestoredReading)
        precondition(defaults.data(forKey: cacheKey) == nil)
        precondition(WatchComplicationSnapshot.read(from: directory, now: clock) == nil,
                     "Unsupported version or wrong selected ID must invalidate shared cached content")
    }
    print("PASS: restored-to-fresh shared final, same-clock corrected winner replacement, clear-race tombstone, wrong-ID/version app-cache rejection and shared invalidation")
    print("PASS: complication shared projection, producer age, final winner, fail-closed reads, tombstone, store publication and stale-response suppression")
}
