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
    try await runSmartStackRefreshChecks()
}


/// Compact identities and optional storage cannot manufacture or erase a public reading.
@MainActor func runCircularComplicationChecks() throws {
    let now = ISO8601DateFormatter().date(from: "2026-10-04T18:00:00Z")!
    let home = "\"home_team_data\":{\"team_id\":1,\"abbreviation\":\"SF\"}"
    let away = "\"away_team_data\":{\"team_id\":2,\"abbreviation\":\"LA\"}"
    let clock = "\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"score_observed_at\":\"2026-10-04T17:59:00Z\""
    func project(_ fields: String) throws -> WatchComplicationSnapshot? {
        let data = Data("{\"id\":101,\"home_team\":\"San Francisco Giants\",\"away_team\":\"Los Angeles Dodgers\",\(fields)}".utf8)
        let game = try JSONDecoder().decode(WatchSelectedGame.self, from: data)
        let restored = try JSONDecoder().decode(WatchSelectedGame.self, from: JSONEncoder().encode(game))
        precondition(restored.homeCompactIdentity == game.homeCompactIdentity && restored.awayCompactIdentity == game.awayCompactIdentity)
        return WatchComplicationProjection.snapshot(game: restored, savedAt: now)
    }
    let fields = "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.455,\"hero_probability_away\":0.545,\(clock)"
    let live = try project("\(fields),\(home),\(away)")!
    let compact = live.validatedCircularReading(now: now)!
    precondition(live.validatedCornerForecast(showsWidgetLabel: true, now: now)?.value == "45%")
    precondition(live.validatedCornerForecast(showsWidgetLabel: false, now: now) == nil,
                 "A numeric corner cannot discard its Saved + named win label")
    precondition(live.validatedCornerForecast(showsWidgetLabel: true, now: now.addingTimeInterval(-1)) == nil)
    let longCorner = try project("\(fields),\(home.replacingOccurrences(of: "SF", with: "SFG")),\(away)")!
    precondition(longCorner.circularReading != nil && longCorner.validatedCornerForecast(showsWidgetLabel: true, now: now) == nil,
                 "Corner bound does not erase valid circular/rectangular content")
    precondition(compact.subject == "SF win" && compact.value == "45%")
    precondition(compact.observedAt == live.observedAt && live.observedAt < live.savedAt)
    let projectionCheck1 = try project("\(fields),\(home)")
    precondition(projectionCheck1?.validatedCircularReading(now: now)?.value == "45%", "Home forecast does not require fabricated away identity")
    let draw = try project("\(fields.replacingOccurrences(of: "baseball_mlb", with: "soccer_epl")),\(home),\(away)")!
    precondition(draw.validatedCornerForecast(showsWidgetLabel: true, now: now)?.value == "46%")
    precondition(draw.validatedCircularReading(now: now)?.value == "46%", "Draw-priced rounding remains scalar")
    for identity in [home.replacingOccurrences(of: "1", with: "0"), home.replacingOccurrences(of: "SF", with: "FCNAME"), home.replacingOccurrences(of: "SF", with: ""), home.replacingOccurrences(of: "SF", with: "sf")] {
        let reading = try project("\(fields),\(identity),\(away)")!
        precondition(reading.validatedCircularReading(now: now) == nil && reading.detail.contains("45%"))
    }
    let projectionCheck2 = try project(fields)
    precondition(projectionCheck2?.validatedCircularReading(now: now) == nil)
    let projectionCheck3 = try project("\(fields),\(home),\(away.replacingOccurrences(of: "2", with: "1"))")
    precondition(projectionCheck3?.validatedCircularReading(now: now) == nil)
    for (scores, subject) in [("\"home_score\":4,\"away_score\":2", "SF won"), ("\"home_score\":2,\"away_score\":4", "LA won"), ("\"home_score\":2,\"away_score\":2", "LA·SF")] {
        let final = try project("\"status\":\"final\",\"hero_probability\":0.99,\(scores),\(clock),\(home),\(away)")!
        precondition(final.validatedCornerForecast(showsWidgetLabel: true, now: now) == nil)
        precondition(final.validatedCircularReading(now: now)?.subject == subject)
        precondition(final.validatedCircularReading(now: now)?.value.hasPrefix("Final") == true && final.circularReading?.percent == nil)
        precondition(final.observedAt == now.addingTimeInterval(-60), "Final uses score clock independently of hero")
    }
    let score = try project("\"status\":\"live\",\"home_score\":4,\"away_score\":2,\(clock),\(home),\(away)")!
    precondition(score.validatedCornerForecast(showsWidgetLabel: true, now: now) == nil)
    precondition(score.validatedCircularReading(now: now)?.subject == "LA·SF" && score.validatedCircularReading(now: now)?.value == "Score 2–4")
    precondition(score.observedAt == now.addingTimeInterval(-60))
    let projectionCheck4 = try project("\"status\":\"live\",\"home_score\":4,\"away_score\":2,\(clock),\(home)")
    precondition(projectionCheck4?.validatedCircularReading(now: now) == nil)
    let projectionCheck5 = try project("\"status\":\"final\",\"hero_probability\":0.99,\(clock),\(home),\(away)")
    precondition(projectionCheck5 == nil)
    for status in ["unknown", "closed", "delayed"] {
        let projectionCheck6 = try project("\(fields.replacingOccurrences(of: "live", with: status)),\(home),\(away)")
        precondition(projectionCheck6 == nil)
    }
    let encoded = try JSONEncoder().encode(live)
    var object = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent(WatchComplicationSnapshot.filename)
    // Old snapshots and malformed/unknown optional payloads preserve the rectangular reading.
    for payload in [NSNull(), "invalid", ["kind": "future-schema"]] as [Any] {
        object["circularReading"] = payload
        try JSONSerialization.data(withJSONObject: object).write(to: file)
        let restored = WatchComplicationSnapshot.read(from: directory, now: now)!
        precondition(restored.title == live.title && restored.detail == live.detail && restored.circularReading == nil)
    }
    object.removeValue(forKey: "circularReading")
    try JSONSerialization.data(withJSONObject: object).write(to: file)
    precondition(WatchComplicationSnapshot.read(from: directory, now: now)?.circularReading == nil)
    precondition(WatchComplicationPublisher.write(live, to: directory, now: now), "One-time canonical enrichment must publish without resetting original clock")
    let offline = WatchComplicationSnapshot.read(from: directory, now: now.addingTimeInterval(86400))!
    precondition(offline.circularReading == compact && offline.observedAt == live.observedAt && offline.savedAt == now)
    precondition(!WatchComplicationPublisher.write(live, to: directory, now: now.addingTimeInterval(86400)), "Unchanged compact reading remains unchanged offline")
    let original = try JSONSerialization.jsonObject(with: encoded) as! [String: Any]
    for (key, wrong) in [("version", 2.0), ("eventID", 202.0), ("observedAt", now.timeIntervalSinceReferenceDate)] {
        var wrongObject = original
        var wrongCompact = wrongObject["circularReading"] as! [String: Any]
        wrongCompact[key] = wrong
        wrongObject["circularReading"] = wrongCompact
        try JSONSerialization.data(withJSONObject: wrongObject).write(to: file)
        let restored = WatchComplicationSnapshot.read(from: directory, now: now)!
        precondition(restored.validatedCircularReading(now: now) == nil && restored.title == live.title, "Wrong compact identity/version/clock must not erase the parent")
    }
    print("PASS: corner forecast-only, capability fallback, bounded canonical identity, original clock and independent circular/rectangular contracts")
    print("PASS: circular canonical identity, original clocks, rounding/draw, final/score, old/malformed/wrong compact payload, offline and one-time enrichment")
    try runRectangularComplicationChecks()
    try runSmartStackRelevanceChecks()
}

/// Deterministic #4933 checks for all six large-rectangular (`accessoryRectangular`) states and line/character budgets.
@MainActor func runRectangularComplicationChecks() throws {
    let now = ISO8601DateFormatter().date(from: "2026-10-04T18:00:00Z")!
    let home = "\"home_team_data\":{\"team_id\":1,\"abbreviation\":\"SF\"}"
    let away = "\"away_team_data\":{\"team_id\":2,\"abbreviation\":\"LA\"}"
    func decodeGame(_ fields: String) throws -> WatchSelectedGame {
        let data = Data("{\"id\":101,\"home_team\":\"San Francisco Giants\",\"away_team\":\"Los Angeles Dodgers\",\(fields)}".utf8)
        return try JSONDecoder().decode(WatchSelectedGame.self, from: data)
    }

    // 1. Live probability state (with and without verified live score)
    let liveWithScore = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    let snapLiveScore = WatchComplicationProjection.snapshot(game: liveWithScore, savedAt: now)!
    let rectLiveScore = snapLiveScore.validatedRectangularReading(now: now)!
    precondition(rectLiveScore.kind == .liveForecast)
    precondition(rectLiveScore.headerLine() == "LA at SF · 2–3",
                 "Long matchup automatically uses canonical abbreviations + verified live score within the 26-char header budget")
    precondition(rectLiveScore.primaryLine(at: now) == "San Francisco Giants win 64%")
    precondition(rectLiveScore.primaryLine(preferCompact: true, at: now) == "SF win 64%")
    precondition(rectLiveScore.metadataLine(at: now) == "Saved · Live · 2m ago" && !rectLiveScore.isStale(at: now))
    precondition(rectLiveScore.accessibilityDescription(at: now).contains("Score Los Angeles Dodgers 2, San Francisco Giants 3.")
                 && rectLiveScore.accessibilityDescription(at: now).contains("San Francisco Giants win probability 64%."))
    let liveDates = WatchRectangularReading.timelineDates(for: snapLiveScore, now: now)
    let staleBoundary = rectLiveScore.observedAt.addingTimeInterval(121)
    precondition(liveDates.first == now && liveDates == liveDates.sorted())
    precondition(liveDates.contains(staleBoundary) && rectLiveScore.metadataLine(at: staleBoundary) == "Saved · Stale · 2m ago")
    precondition(rectLiveScore.metadataLine(at: rectLiveScore.observedAt.addingTimeInterval(59 * 60)) == "Saved · Stale · 59m ago")
    precondition(rectLiveScore.accessibilityDescription(at: staleBoundary).contains("Stale reading."))

    // A changed score under the same probability clock must replace shared bytes and request a reload.
    let changedScore = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    let changedSnapshot = WatchComplicationProjection.snapshot(game: changedScore, savedAt: now)!
    precondition(changedSnapshot.title == snapLiveScore.title && changedSnapshot.detail == snapLiveScore.detail)
    precondition(changedSnapshot.observedAt == snapLiveScore.observedAt && changedSnapshot.rectangularReading != snapLiveScore.rectangularReading)
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    precondition(WatchComplicationPublisher.write(snapLiveScore, to: directory, now: now))
    precondition(WatchComplicationPublisher.write(changedSnapshot, to: directory, now: now))
    precondition(WatchComplicationSnapshot.read(from: directory, now: now)?.rectangularReading?.homeScore == 4)
    precondition(!WatchComplicationPublisher.write(changedSnapshot, to: directory, now: now))

    // A structured percent must agree with the parent title/detail; tampered display data falls back.
    var tampered = try JSONSerialization.jsonObject(with: JSONEncoder().encode(snapLiveScore)) as! [String: Any]
    var tamperedRectangular = tampered["rectangularReading"] as! [String: Any]
    tamperedRectangular["homePercent"] = 90
    tampered["rectangularReading"] = tamperedRectangular
    let tamperedFile = directory.appendingPathComponent(WatchComplicationSnapshot.filename)
    try JSONSerialization.data(withJSONObject: tampered).write(to: tamperedFile)
    let restoredTampered = WatchComplicationSnapshot.read(from: directory, now: now)!
    precondition(restoredTampered.title == snapLiveScore.title && restoredTampered.detail == snapLiveScore.detail)
    precondition(restoredTampered.validatedRectangularReading(now: now) == nil)

    // Unverified live score (missing score_observed_at) is omitted from the live forecast header rather than shown untruthfully.
    let liveUnverifiedScore = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"home_score\":3,\"away_score\":2,\(home),\(away)"
    )
    let rectLiveNoScore = WatchComplicationProjection.snapshot(game: liveUnverifiedScore, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectLiveNoScore.kind == .liveForecast && rectLiveNoScore.homeScore == nil && rectLiveNoScore.awayScore == nil)
    precondition(rectLiveNoScore.headerLine() == "LA at SF")
    let laggedScore = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:59:50Z\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:34:50Z\",\(home),\(away)"
    )
    let rectLagged = WatchComplicationProjection.snapshot(game: laggedScore, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectLagged.kind == .liveForecast && rectLagged.homeScore == nil && rectLagged.awayScore == nil)
    precondition(rectLagged.headerLine() == "LA at SF" && rectLagged.metadataLine(at: now) == "Saved · Live · <1m ago")

    // Exact 120s score lag is kept (`<=`); 121s lag is omitted (`A3`/`D15` guard); forged lagged score in stored JSON is rejected by validation (`A1`/`D7` guard).
    let exactBoundaryScore = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:59:50Z\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:57:50Z\",\(home),\(away)"
    )
    let rectBoundaryKept = WatchComplicationProjection.snapshot(game: exactBoundaryScore, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectBoundaryKept.homeScore == 3 && rectBoundaryKept.awayScore == 2 && rectBoundaryKept.headerLine() == "LA at SF · 2–3")
    let overBoundaryScore = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:59:50Z\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:57:49Z\",\(home),\(away)"
    )
    let rectBoundaryDropped = WatchComplicationProjection.snapshot(game: overBoundaryScore, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectBoundaryDropped.homeScore == nil && rectBoundaryDropped.awayScore == nil && rectBoundaryDropped.headerLine() == "LA at SF")
    var forgedLagObject = try JSONSerialization.jsonObject(with: JSONEncoder().encode(snapLiveScore)) as! [String: Any]
    var forgedLagRect = forgedLagObject["rectangularReading"] as! [String: Any]
    forgedLagRect["scoreObservedAt"] = rectLiveScore.observedAt.addingTimeInterval(-1500).timeIntervalSinceReferenceDate
    forgedLagObject["rectangularReading"] = forgedLagRect
    let forgedLagSnapshot = try JSONDecoder().decode(WatchComplicationSnapshot.self, from: JSONSerialization.data(withJSONObject: forgedLagObject))
    precondition(forgedLagSnapshot.rectangularReading?.scoreObservedAt != nil && forgedLagSnapshot.validatedRectangularReading(now: now) == nil,
                 "Forged lagged scoreObservedAt in stored JSON must be refused by validatedRectangularReading")

    // 2. Live score-only state (missing probability shows honest copy without fabricated numbers)
    let liveScoreOnly = try decodeGame(
        "\"status\":\"live\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    let snapScoreOnly = WatchComplicationProjection.snapshot(game: liveScoreOnly, savedAt: now)!
    let rectScoreOnly = snapScoreOnly.validatedRectangularReading(now: now)!
    precondition(rectScoreOnly.kind == .liveScoreOnly && rectScoreOnly.homePercent == nil)
    precondition(rectScoreOnly.headerLine() == "LA at SF")
    precondition(rectScoreOnly.primaryLine(at: now) == "Score 2–3 · No win prob" && !rectScoreOnly.primaryLine(at: now).contains("%"))
    precondition(rectScoreOnly.metadataLine(at: now) == "Saved · Live · 1m ago")
    precondition(rectScoreOnly.accessibilityDescription(at: now).contains("Win probability unavailable."))
    precondition(rectScoreOnly.primaryLine(preferCompact: true, at: now) == "2–3 · No win prob")
    // lane1b A7: on a 41 mm face the compact card cut "Score 112–108 · No win prob" at the
    // right edge. Its compact copy keeps both scores and the whole missing-chance cue.
    let tripleScoreOnly = try decodeGame(
        "\"status\":\"live\",\"home_score\":108,\"away_score\":112,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    let rectTriple = WatchComplicationProjection.snapshot(game: tripleScoreOnly, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectTriple.kind == .liveScoreOnly && rectTriple.primaryLine(at: now) == "Score 112–108 · No win prob")
    let compactTriple = rectTriple.primaryLine(preferCompact: true, at: now)
    precondition(compactTriple == "112–108 · No win prob"
                 && compactTriple.count <= WatchRectangularReading.maxCompactScheduledPrimaryCharacters,
                 "Compact three-digit score-only line must keep its cue within the compact budget: \(compactTriple)")
    precondition(rectTriple.accessibilityDescription(at: now).contains(
        "Los Angeles Dodgers, score 112. San Francisco Giants, score 108. Win probability unavailable."))

    // 3a. Scheduled state with pregame probability (never shows fake 0–0 even if payload has 0–0 scores)
    let scheduledForecast = try decodeGame(
        "\"status\":\"scheduled\",\"commence_time\":\"2026-10-04T23:00:00Z\",\"home_score\":0,\"away_score\":0,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\"hero_probability\":0.55,\"hero_probability_away\":0.45,\"hero_probability_observed_at\":\"2026-10-04T17:57:00Z\",\(home),\(away)"
    )
    let snapSchedForecast = WatchComplicationProjection.snapshot(game: scheduledForecast, savedAt: now)!
    let rectSchedForecast = snapSchedForecast.validatedRectangularReading(now: now)!
    precondition(rectSchedForecast.kind == .scheduledForecast && rectSchedForecast.homeScore == nil && rectSchedForecast.awayScore == nil)
    precondition(rectSchedForecast.headerLine() == "LA at SF" && !rectSchedForecast.headerLine().contains("0–0"))
    precondition(rectSchedForecast.primaryLine(at: now) == "San Francisco Giants win 55%")
    precondition(rectSchedForecast.metadataLine(at: now) == "Saved · Scheduled · 3m ago" && !rectSchedForecast.isStale(at: now))
    let forecastStart = rectSchedForecast.commenceTime!
    precondition(WatchRectangularReading.timelineDates(for: snapSchedForecast, now: now).contains(forecastStart))
    precondition(rectSchedForecast.metadataLine(at: forecastStart) == "Saved · Past start · 5h ago")
    precondition(rectSchedForecast.metadataLine(at: rectSchedForecast.observedAt.addingTimeInterval(23 * 3600)) == "Saved · Past start · 23h ago")
    precondition(rectSchedForecast.accessibilityDescription(at: forecastStart).contains("game status unconfirmed"))

    // 3b. Scheduled state without pregame probability (shows scheduled start without fake 0–0)
    let scheduledStartOnly = try decodeGame(
        "\"status\":\"scheduled\",\"commence_time\":\"2026-10-04T23:00:00Z\",\"home_score\":0,\"away_score\":0,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    let snapSchedStart = WatchComplicationProjection.snapshot(game: scheduledStartOnly, savedAt: now)!
    let rectSchedStart = snapSchedStart.validatedRectangularReading(now: now)!
    precondition(rectSchedStart.kind == .scheduledStart && rectSchedStart.homeScore == nil && rectSchedStart.awayScore == nil && rectSchedStart.homePercent == nil)
    precondition(snapSchedStart.validatedCircularReading(now: now) == nil, "Scheduled-start-only reading does not invent a circular percentage")
    precondition(rectSchedStart.headerLine() == "LA at SF" && !rectSchedStart.headerLine().contains("0–0"))
    precondition(rectSchedStart.primaryLine(at: now).hasPrefix("Scheduled · ") && !rectSchedStart.primaryLine(at: now).contains("0–0"))
    let compactPreStartPrimary = rectSchedStart.primaryLine(preferCompact: true, at: now)
    precondition(compactPreStartPrimary.hasPrefix("Start ") && !compactPreStartPrimary.hasPrefix("Scheduled · ") && !compactPreStartPrimary.contains("0–0"))
    precondition(compactPreStartPrimary.count <= WatchRectangularReading.maxCompactScheduledPrimaryCharacters,
                 "Compact pre-start scheduled primary must fit narrow 41mm single-line budget (\(compactPreStartPrimary.count)): \(compactPreStartPrimary)")
    // lane1b P2: both cards keep the whole start (day, hour and minute), not just the prefix.
    let wholeStart = rectSchedStart.commenceTime!.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    precondition(compactPreStartPrimary == "Start " + wholeStart,
                 "Compact pre-start primary must keep the whole start time: \(compactPreStartPrimary)")
    precondition(rectSchedStart.primaryLine(at: now) == "Scheduled · " + wholeStart,
                 "Full pre-start primary must keep the whole start time: \(rectSchedStart.primaryLine(at: now))")
    precondition(rectSchedStart.metadataLine(at: now) == "Saved · No win prob")
    precondition(rectSchedStart.accessibilityDescription(at: now).contains("Win probability unavailable."))
    let start = rectSchedStart.commenceTime!
    let scheduledDates = WatchRectangularReading.timelineDates(for: snapSchedStart, now: now)
    precondition(scheduledDates.contains(start))
    precondition(rectSchedStart.primaryLine(at: start) == "Start time passed · check app")
    let compactPastStartPrimary = rectSchedStart.primaryLine(preferCompact: true, at: start)
    precondition(compactPastStartPrimary == "Past start · check app"
                 && compactPastStartPrimary.count <= WatchRectangularReading.maxCompactScheduledPrimaryCharacters)
    let missingTimeStart = WatchRectangularReading(
        version: 1,
        eventID: 101,
        kind: .scheduledStart,
        homeName: "San Francisco Giants",
        awayName: "Los Angeles Dodgers",
        home: rectSchedStart.home,
        away: rectSchedStart.away,
        homePercent: nil,
        homeScore: nil,
        awayScore: nil,
        commenceTime: nil,
        stateLabel: "Scheduled",
        observedAt: now,
        scoreObservedAt: nil
    )
    precondition(missingTimeStart.primaryLine(preferCompact: false, at: now) == "Scheduled · time unavailable")
    precondition(missingTimeStart.primaryLine(preferCompact: true, at: now) == "Time unavailable"
                 && missingTimeStart.primaryLine(preferCompact: true, at: now).count <= WatchRectangularReading.maxCompactScheduledPrimaryCharacters)
    precondition(rectSchedStart.metadataLine(at: start) == "Saved · Past start · 5h ago")
    precondition(rectSchedStart.metadataLine(at: rectSchedStart.observedAt.addingTimeInterval(23 * 3600)) == "Saved · Past start · 23h ago")
    precondition(rectSchedStart.accessibilityDescription(at: start).contains("game status unconfirmed"))
    precondition(!rectSchedStart.accessibilityDescription(at: start).contains("Observed"), "Saved time is not a producer observation")

    // 4. Final state (matchup + final score/winner without stale pre-final probability)
    let finalGame = try decodeGame(
        "\"status\":\"completed\",\"home_score\":4,\"away_score\":2,\"hero_probability\":0.99,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"score_observed_at\":\"2026-10-04T17:58:00Z\",\(home),\(away)"
    )
    let snapFinal = WatchComplicationProjection.snapshot(game: finalGame, savedAt: now)!
    let rectFinal = snapFinal.validatedRectangularReading(now: now)!
    precondition(rectFinal.kind == .finalResult && rectFinal.homePercent == nil)
    precondition(rectFinal.headerLine() == "LA at SF")
    precondition(rectFinal.primaryLine(at: now) == "San Francisco Giants won · 4–2" && !rectFinal.primaryLine(at: now).contains("%"))
    precondition(rectFinal.primaryLine(preferCompact: true, at: now) == "SF won · 4–2")
    precondition(rectFinal.metadataLine(at: now) == "Saved · Final · 2m ago" && !rectFinal.isStale(at: now.addingTimeInterval(3600)))
    let finalDates = WatchRectangularReading.timelineDates(for: snapFinal, now: now)
    let oneHour = rectFinal.observedAt.addingTimeInterval(3600)
    let oneDay = rectFinal.observedAt.addingTimeInterval(86400)
    precondition(finalDates.contains(oneHour) && finalDates.contains(oneDay))
    precondition(rectFinal.metadataLine(at: oneHour) == "Saved · Final · 1h ago")
    precondition(rectFinal.metadataLine(at: oneDay) == "Saved · Final · 1d ago")

    // 5. Stale/restored live state (explicitly flags stale when observation age > 120s)
    let staleClock = now.addingTimeInterval(180) // 5 minutes after 17:58:00Z observation
    precondition(rectLiveScore.isStale(at: staleClock))
    precondition(rectLiveScore.metadataLine(at: staleClock) == "Saved · Stale · 5m ago")
    precondition(rectLiveScore.accessibilityDescription(at: staleClock).contains("Stale reading."))
    precondition(rectScoreOnly.isStale(at: staleClock))
    precondition(rectScoreOnly.metadataLine(at: staleClock) == "Saved · Stale · 4m ago")

    // 6. Narrow-face metadata character-budget & cue-preservation guard across all timeline entries and worst-case ages
    for snap in [snapLiveScore, snapScoreOnly, snapSchedForecast, snapSchedStart, snapFinal] {
        let reading = snap.validatedRectangularReading(now: now)!
        for date in WatchRectangularReading.timelineDates(for: snap, now: now) + [
            reading.observedAt.addingTimeInterval(30),
            reading.observedAt.addingTimeInterval(59 * 60),
            reading.observedAt.addingTimeInterval(23 * 3600),
            reading.observedAt.addingTimeInterval(7 * 86400),
        ] {
            let meta = reading.metadataLine(at: date)
            precondition(meta.hasPrefix("Saved · "), "Metadata must always retain Saved provenance: \(meta)")
            precondition(meta.count <= WatchRectangularReading.maxSingleLineMetadataCharacters,
                         "Metadata exceeds \(WatchRectangularReading.maxSingleLineMetadataCharacters)-char narrow-face budget (\(meta.count)): \(meta)")
            if reading.isStale(at: date) {
                precondition(meta.contains("Stale") && meta.hasSuffix("ago"),
                             "Stale live reading must retain both Stale and elapsed age: \(meta)")
            }
            if (reading.kind == .scheduledStart || reading.kind == .scheduledForecast),
               let kickoff = reading.commenceTime, date >= kickoff {
                precondition(meta.contains("Past start") && meta.hasSuffix("ago"),
                             "Passed scheduled start must retain both Past start and elapsed age: \(meta)")
            }
            if reading.kind == .scheduledStart {
                let compactPrimary = reading.primaryLine(preferCompact: true, at: date)
                precondition(compactPrimary.count <= WatchRectangularReading.maxCompactScheduledPrimaryCharacters,
                             "Compact scheduled-start primary exceeds \(WatchRectangularReading.maxCompactScheduledPrimaryCharacters)-char narrow-face budget (\(compactPrimary.count)): \(compactPrimary)")
            }
        }
    }
    print("PASS: rectangular complication live probability+score, live score-only, scheduled forecast/start without fake 0–0, final winner without stale probability, and explicit saved/stale age")
}

/// #12316: the Smart Stack window, files saved before it, the publisher's new fields and the
/// card's counting-age words. No WidgetKit here; watch-build compiles the relevance provider.
@MainActor func runSmartStackRelevanceChecks() throws {
    let iso = ISO8601DateFormatter()
    let now = iso.date(from: "2026-10-04T18:00:00Z")!
    let minute: TimeInterval = 60
    let hour: TimeInterval = 3600
    let teams = "\"home_team_data\":{\"team_id\":1,\"abbreviation\":\"SF\"},\"away_team_data\":{\"team_id\":2,\"abbreviation\":\"LA\"}"
    func project(_ fields: String) throws -> WatchComplicationSnapshot {
        let data = Data("{\"id\":101,\"home_team\":\"San Francisco Giants\",\"away_team\":\"Los Angeles Dodgers\",\(fields),\(teams)}".utf8)
        return WatchComplicationProjection.snapshot(game: try JSONDecoder().decode(WatchSelectedGame.self, from: data), savedAt: now)!
    }

    // The brief's simulator case: a game chosen 20 minutes before it starts, with no chance yet.
    let start = iso.date(from: "2026-10-04T18:20:00Z")!
    let scheduled = try project("\"status\":\"scheduled\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-04T18:20:00Z\"")
    precondition(scheduled.rectangularReading?.kind == .scheduledStart)
    precondition(scheduled.commenceTime == start && scheduled.sportKey == "baseball_mlb" && scheduled.status == "scheduled",
                 "A scheduled game's file carries its start, sport and status")
    let window = scheduled.relevanceWindow!
    precondition(window.start == start.addingTimeInterval(-15 * minute) && window.end == start.addingTimeInterval(4 * hour),
                 "Suggested from 15 minutes before the start until start + 4 h")
    precondition(!window.contains(now) && !window.contains(window.start.addingTimeInterval(-1)),
                 "Twenty minutes out, the card is not suggested yet")
    precondition(window.contains(window.start) && window.contains(start.addingTimeInterval(2 * hour)))
    precondition(!window.contains(window.end.addingTimeInterval(1)), "The cap ends a game whose final the watch never saw")

    // Per-sport cap: soccer is shorter; other and unknown sports take the default.
    let caps: [(String?, TimeInterval)] = [
        ("soccer_epl", 2.5 * hour), ("SOCCER_usa_mls", 2.5 * hour), ("basketball_nba", 4 * hour),
        ("americanfootball_nfl", 4 * hour), (nil, 4 * hour),
    ]
    for (sport, cap) in caps {
        precondition(WatchComplicationSnapshot.relevanceCapSeconds(sportKey: sport) == cap, "Window cap for \(sport ?? "no sport")")
    }
    let soccer = try project("\"status\":\"scheduled\",\"sport\":\"soccer_epl\",\"commence_time\":\"2026-10-04T18:20:00Z\"")
    precondition(soccer.relevanceWindow?.end == start.addingTimeInterval(2.5 * hour))

    // Live: the window runs to the cap, because the watch cannot know the game has ended.
    let liveStart = iso.date(from: "2026-10-04T17:00:00Z")!
    let liveFields = "\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\""
    let live = try project("\"status\":\"live\",\"commence_time\":\"2026-10-04T17:00:00Z\",\(liveFields)")
    precondition(live.rectangularReading?.kind == .liveForecast && live.status == "live")
    precondition(live.relevanceWindow == DateInterval(start: liveStart.addingTimeInterval(-15 * minute),
                                                      end: liveStart.addingTimeInterval(4 * hour)))
    precondition(live.relevanceWindow!.contains(now))
    let noStart = try project("\"status\":\"live\",\(liveFields)")
    precondition(noStart.commenceTime == nil && noStart.relevanceWindow == nil, "No start time, no suggestion")

    // Final: leaves 30 minutes after the final was seen, never later than the cap.
    let final = try project("\"status\":\"completed\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-04T15:00:00Z\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
    precondition(final.rectangularReading?.kind == .finalResult)
    precondition(final.relevanceWindow?.end == final.observedAt.addingTimeInterval(30 * minute) && final.relevanceWindow!.contains(now),
                 "A final seen at 17:58 leaves at 18:28")
    let lateFinal = try project("\"status\":\"Final\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-04T13:00:00Z\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\"")
    precondition(lateFinal.relevanceWindow?.end == iso.date(from: "2026-10-04T17:00:00Z")! && !lateFinal.relevanceWindow!.contains(now),
                 "A final seen after the cap never extends the window past start + 4 h")

    // Files saved before #12316 still decode and draw; they are simply never suggested.
    let directory = FileManager.default.temporaryDirectory.appendingPathComponent("watch-relevance-\(UUID().uuidString)")
    try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
    defer { try? FileManager.default.removeItem(at: directory) }
    let file = directory.appendingPathComponent(WatchComplicationSnapshot.filename)
    var old = try JSONSerialization.jsonObject(with: JSONEncoder().encode(live)) as! [String: Any]
    precondition(old["commenceTime"] != nil && old["sportKey"] != nil && old["status"] != nil)
    for key in ["commenceTime", "sportKey", "status"] { old.removeValue(forKey: key) }
    try JSONSerialization.data(withJSONObject: old).write(to: file)
    let restoredOld = WatchComplicationSnapshot.read(from: directory, now: now)!
    precondition(restoredOld.validatedRectangularReading(now: now) == live.validatedRectangularReading(now: now),
                 "An old file keeps its face reading")
    precondition(restoredOld.commenceTime == nil && restoredOld.sportKey == nil && restoredOld.status == nil
                 && restoredOld.relevanceWindow == nil)
    var malformed = try JSONSerialization.jsonObject(with: JSONEncoder().encode(live)) as! [String: Any]
    malformed["commenceTime"] = "tonight"
    malformed["sportKey"] = 7
    malformed["status"] = ["live"]
    try JSONSerialization.data(withJSONObject: malformed).write(to: file)
    let tolerated = WatchComplicationSnapshot.read(from: directory, now: now)!
    precondition(tolerated.validatedRectangularReading(now: now) != nil && tolerated.relevanceWindow == nil
                 && tolerated.sportKey == nil && tolerated.status == nil,
                 "Malformed game-day fields drop only themselves, never the reading")

    // The publisher writes the fields, and any change to them rewrites the file (reload + new relevance).
    try FileManager.default.removeItem(at: file)
    precondition(WatchComplicationPublisher.write(live, to: directory, now: now))
    let written = WatchComplicationSnapshot.read(from: directory, now: now)!
    precondition(written.commenceTime == liveStart && written.sportKey == "baseball_mlb" && written.status == "live"
                 && written.relevanceWindow == live.relevanceWindow)
    precondition(!WatchComplicationPublisher.write(live, to: directory, now: now), "Unchanged fields do not rewrite")
    let moved = try project("\"status\":\"live\",\"commence_time\":\"2026-10-04T17:10:00Z\",\(liveFields)")
    let inProgress = try project("\"status\":\"in_progress\",\"commence_time\":\"2026-10-04T17:10:00Z\",\(liveFields)")
    let resported = try project("\"status\":\"in_progress\",\"commence_time\":\"2026-10-04T17:10:00Z\",\(liveFields.replacingOccurrences(of: "baseball_mlb", with: "soccer_epl"))")
    for (label, next) in [("start", moved), ("status", inProgress), ("sport", resported)] {
        let current = WatchComplicationSnapshot.read(from: directory, now: now)!
        precondition(next.title == current.title && next.detail == current.detail && next.observedAt == current.observedAt
                     && next.rectangularReading == current.rectangularReading,
                     "Only the \(label) changed")
        precondition(WatchComplicationPublisher.write(next, to: directory, now: now),
                     "A changed \(label) rewrites the file so the Smart Stack asks again")
    }
    precondition(WatchComplicationSnapshot.read(from: directory, now: now)?.relevanceWindow?.end
                 == iso.date(from: "2026-10-04T17:10:00Z")!.addingTimeInterval(2.5 * hour))

    // The card says the face's words, with a counting clock in place of the age, and a spoken
    // observation time that cannot go out of date.
    let specimens = [
        live, noStart, scheduled, final,
        try project("\"status\":\"live\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\""),
        try project("\"status\":\"scheduled\",\"commence_time\":\"2026-10-04T23:00:00Z\",\"hero_probability\":0.55,\"hero_probability_away\":0.45,\"hero_probability_observed_at\":\"2026-10-04T17:57:00Z\""),
    ]
    var kinds = Set<String>()
    for snapshot in specimens {
        let reading = snapshot.validatedRectangularReading(now: now)!
        kinds.insert("\(reading.kind)")
        let clock = WatchRectangularReading.spokenClock(observedAt: reading.observedAt)
        precondition(clock == "at \(reading.observedAt.formatted(.dateTime.month(.abbreviated).day().hour().minute()))")
        for date in WatchRectangularReading.timelineDates(for: snapshot, now: now) + [
            reading.observedAt.addingTimeInterval(30), reading.observedAt.addingTimeInterval(121),
            reading.observedAt.addingTimeInterval(59 * minute), start.addingTimeInterval(1),
            reading.observedAt.addingTimeInterval(23 * hour), reading.observedAt.addingTimeInterval(7 * 24 * hour),
        ] {
            let leadIn = reading.metadataLeadIn(at: date)
            let age = WatchRectangularReading.compactAge(observedAt: reading.observedAt, now: date) ?? "no time"
            precondition(reading.metadataLine(at: date) == (leadIn.map { $0 + age } ?? "Saved · No win prob"),
                         "Card words differ from the face: \(reading.metadataLine(at: date)) vs \(leadIn ?? "nil")")
            if let leadIn { precondition(leadIn.hasPrefix("Saved · ") && leadIn.hasSuffix(" · ")) }
            let face = reading.accessibilityDescription(at: date)
            let card = reading.accessibilityDescription(at: date, observedClock: clock)
            if let spoken = WatchRectangularReading.spokenAge(observedAt: reading.observedAt, now: date), face.contains(spoken) {
                precondition(card == face.replacingOccurrences(of: spoken, with: clock) && !card.contains(" ago."),
                             "The card's spoken age must be a time of day: \(card)")
            } else {
                precondition(card == face, "A spoken label without an age stays unchanged")
            }
        }
    }
    precondition(kinds == ["liveForecast", "liveScoreOnly", "scheduledForecast", "scheduledStart", "finalResult"], "\(kinds)")
    print("PASS: Smart Stack window (15 min lead, sport cap, 30 min after a final), old and malformed files, publisher fields and rewrite, and the card's counting-age words")
}

/// Every request is intercepted; the Smart Stack refresh checks never contact the public API.
private final class SmartStackHTTPProtocol: URLProtocol, @unchecked Sendable {
    private static let lock = NSLock()
    private static var requests: [URLRequest] = []

    static func reset() { lock.lock(); requests = []; lock.unlock() }
    static var seen: [URLRequest] { lock.lock(); defer { lock.unlock() }; return requests }

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        Self.lock.lock()
        Self.requests.append(request)
        Self.lock.unlock()
        if let error = request.value(forHTTPHeaderField: "X-Watch-Test-Network-Error") {
            client?.urlProtocol(self, didFailWithError: URLError(URLError.Code(rawValue: Int(error)!)))
            return
        }
        let status = Int(request.value(forHTTPHeaderField: "X-Watch-Test-Status")!)!
        let body = request.value(forHTTPHeaderField: "X-Watch-Test-Body")!
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: "HTTP/1.1", headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

/// #12316 step 4: the Smart Stack card's one bounded refresh of the chosen game.
@MainActor func runSmartStackRefreshChecks() async throws {
    let iso = ISO8601DateFormatter()
    let savedAt = iso.date(from: "2026-10-04T18:00:00Z")!
    let teams = "\"home_team_data\":{\"team_id\":1,\"abbreviation\":\"SF\"},\"away_team_data\":{\"team_id\":2,\"abbreviation\":\"LA\"}"
    func body(_ fields: String, id: Int = 101) -> String {
        "{\"id\":\(id),\"home_team\":\"San Francisco Giants\",\"away_team\":\"Los Angeles Dodgers\",\(fields),\(teams)}"
    }
    func project(_ json: String) throws -> WatchComplicationSnapshot {
        let game = try JSONDecoder().decode(WatchSelectedGame.self, from: Data(json.utf8))
        return WatchComplicationProjection.snapshot(game: game, savedAt: savedAt)!
    }
    func live(observed: String, home: Int, start: String = "\"commence_time\":\"2026-10-04T17:00:00Z\",") -> String {
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\(start)\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"\(observed)\",\"home_score\":\(home),\"away_score\":2,\"score_observed_at\":\"\(observed)\""
    }
    func session(status: Int = 200, json: String = "{}", networkError: URLError.Code? = nil) -> URLSession {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SmartStackHTTPProtocol.self]
        var headers = ["X-Watch-Test-Status": String(status), "X-Watch-Test-Body": json]
        if let networkError { headers["X-Watch-Test-Network-Error"] = String(networkError.rawValue) }
        configuration.httpAdditionalHeaders = headers
        return URLSession(configuration: configuration)
    }

    // When: mid-game (started by its schedule, not final, window open) and past two minutes.
    let saved = try project(body(live(observed: "2026-10-04T17:58:00Z", home: 3)))
    let later = iso.date(from: "2026-10-04T18:20:00Z")!
    precondition(WatchYourGameRefresh.wantsRefresh(saved, now: later))
    precondition(!WatchYourGameRefresh.wantsRefresh(saved, now: saved.observedAt.addingTimeInterval(120)),
                 "Within two minutes the saved reading is shown as it is")
    precondition(WatchYourGameRefresh.wantsRefresh(saved, now: saved.observedAt.addingTimeInterval(121)))
    precondition(!WatchYourGameRefresh.wantsRefresh(saved, now: iso.date(from: "2026-10-04T21:00:01Z")!),
                 "After the window closes the card is gone, so nothing is fetched")
    let scheduled = try project(body("\"status\":\"scheduled\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-04T18:20:00Z\""))
    precondition(!WatchYourGameRefresh.wantsRefresh(scheduled, now: iso.date(from: "2026-10-04T18:10:00Z")!),
                 "In the 15 minutes before the start, the saved reading is shown")
    precondition(WatchYourGameRefresh.wantsRefresh(scheduled, now: iso.date(from: "2026-10-04T18:25:00Z")!),
                 "A game saved before it started is refreshed once it has started")
    let final = try project(body("\"status\":\"completed\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-04T15:00:00Z\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\""))
    precondition(!WatchYourGameRefresh.wantsRefresh(final, now: later), "A final is never refreshed")
    let noStart = try project(body(live(observed: "2026-10-04T17:58:00Z", home: 3, start: "")))
    precondition(!WatchYourGameRefresh.wantsRefresh(noStart, now: later), "No start time, no window, no fetch")

    // With the app closed, the face slot asks again while the game is under way; each ask whose
    // saved reading wants a refresh asks the card, which has no timeline of its own.
    precondition(WatchYourGameRefresh.faceRecheck(saved, now: later) == later.addingTimeInterval(120),
                 "Mid-game the face asks again two minutes on")
    let freshNow = saved.observedAt.addingTimeInterval(60)
    precondition(WatchYourGameRefresh.faceRecheck(saved, now: freshNow) == freshNow.addingTimeInterval(120)
                 && !WatchYourGameRefresh.wantsRefresh(saved, now: freshNow),
                 "A fresh reading asks nothing yet, but the face asks again, so the card is asked once it is not")
    precondition(WatchYourGameRefresh.faceRecheck(nil, now: later) == nil, "No game: the face keeps its own end")
    precondition(WatchYourGameRefresh.faceRecheck(final, now: later) == nil, "A final: the face keeps its own end")
    let finalLaterStart = try project(body("\"status\":\"final\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-05T17:00:00Z\",\"home_score\":4,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\""))
    precondition(WatchYourGameRefresh.faceRecheck(finalLaterStart, now: later) == nil,
                 "A final never brings the face back, even with a later start on file")
    let start = iso.date(from: "2026-10-04T18:20:00Z")!
    precondition(WatchYourGameRefresh.faceRecheck(scheduled, now: iso.date(from: "2026-10-04T18:10:00Z")!) == start
                 && WatchYourGameRefresh.faceRecheck(scheduled, now: iso.date(from: "2026-10-03T18:10:00Z")!) == start,
                 "A game chosen before its start is asked about at the start, the day before too")
    precondition(WatchYourGameRefresh.faceRecheck(scheduled, now: iso.date(from: "2026-10-04T18:25:00Z")!)
                 == iso.date(from: "2026-10-04T18:27:00Z")!,
                 "Once it has started, the face asks every two minutes")
    precondition(WatchYourGameRefresh.faceRecheck(saved, now: iso.date(from: "2026-10-04T21:00:01Z")!) == nil,
                 "After the window closes the card is gone, so the face stops asking")
    precondition(WatchYourGameRefresh.faceRecheck(noStart, now: later) == nil, "No start time, no recheck")

    // What: the same public endpoint, bounded and uncached.
    let request = WatchYourGameRefresh.request(eventID: 101)
    precondition(request.url?.absoluteString == "https://api.bainluck.com/api/events/101"
                 && request.timeoutInterval == 8 && request.cachePolicy == .reloadIgnoringLocalCacheData)
    precondition(WatchYourGameRefresh.session.configuration.timeoutIntervalForResource == 8)

    // A newer reading of the same game replaces the saved one on the card.
    let fetchedAt = later.addingTimeInterval(1)
    SmartStackHTTPProtocol.reset()
    let newer = await WatchYourGameRefresh.reading(saved: saved, now: later,
        session: session(json: body(live(observed: "2026-10-04T18:19:30Z", home: 5))), clock: { fetchedAt })
    precondition(SmartStackHTTPProtocol.seen.count == 1 && SmartStackHTTPProtocol.seen[0].url?.path == "/api/events/101"
                 && SmartStackHTTPProtocol.seen[0].timeoutInterval == 8, "One bounded request for the chosen game")
    precondition(newer.observedAt == iso.date(from: "2026-10-04T18:19:30Z")! && newer.savedAt == fetchedAt
                 && newer.rectangularReading?.homeScore == 5 && newer.commenceTime == saved.commenceTime)
    precondition(newer.validatedRectangularReading(now: fetchedAt)?.metadataLine(at: fetchedAt) == "Saved · Live · <1m ago")
    let wentFinal = await WatchYourGameRefresh.reading(saved: saved, now: later,
        session: session(json: body("\"status\":\"completed\",\"sport\":\"baseball_mlb\",\"commence_time\":\"2026-10-04T17:00:00Z\",\"home_score\":5,\"away_score\":2,\"score_observed_at\":\"2026-10-04T18:15:00Z\"")),
        clock: { fetchedAt })
    precondition(wentFinal.rectangularReading?.kind == .finalResult && wentFinal.title == "San Francisco Giants won",
                 "A game that ended while the app was closed shows its final")

    // Every failure, and anything not newer for the same game, shows the saved reading.
    let failures: [(String, URLSession)] = [
        ("not found", session(status: 404)), ("busy", session(status: 503)),
        ("offline", session(networkError: .notConnectedToInternet)), ("timeout", session(networkError: .timedOut)),
        ("malformed", session(json: "{\"id\":")),
        ("another game", session(json: body(live(observed: "2026-10-04T18:19:30Z", home: 5), id: 202))),
        ("older reading", session(json: body(live(observed: "2026-10-04T17:50:00Z", home: 5)))),
        ("same reading", session(json: body(live(observed: "2026-10-04T17:58:00Z", home: 3)))),
        ("no reading", session(json: body("\"status\":\"delayed\",\"commence_time\":\"2026-10-04T17:00:00Z\""))),
    ]
    for (label, failing) in failures {
        let shown = await WatchYourGameRefresh.reading(saved: saved, now: later, session: failing, clock: { fetchedAt })
        precondition(shown.savedAt == saved.savedAt && shown.observedAt == saved.observedAt
                     && shown.rectangularReading == saved.rectangularReading, "\(label) keeps the saved reading")
        failing.invalidateAndCancel()
    }
    SmartStackHTTPProtocol.reset()
    let stillFresh = await WatchYourGameRefresh.reading(saved: saved, now: saved.observedAt.addingTimeInterval(60),
        session: session(json: body(live(observed: "2026-10-04T17:58:30Z", home: 5))), clock: { fetchedAt })
    precondition(SmartStackHTTPProtocol.seen.isEmpty && stillFresh.savedAt == saved.savedAt,
                 "No request while the saved reading is fresh")
    print("PASS: Smart Stack card refresh only mid-game past two minutes, one bounded uncached GET of the same game, newer readings and finals only, saved reading on every failure; the face asks again at the start and then every two minutes only while the game is under way")
}
