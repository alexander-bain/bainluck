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
}

/// Deterministic #4933 checks for the large-rectangular (`accessoryRectangular`) probability/final states,
/// omitted odds-less states, and Alex's wording contract (never "Saved", never "stale").
@MainActor func runRectangularComplicationChecks() throws {
    let now = ISO8601DateFormatter().date(from: "2026-10-04T18:00:00Z")!
    let pacific = TimeZone(identifier: "America/Los_Angeles")!
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
    precondition(rectLiveScore.primaryLine(at: now) == "SF 64%")
    precondition(rectLiveScore.primaryLine(preferCompact: true, at: now) == "SF 64%")
    let oneMinuteAfter = rectLiveScore.observedAt.addingTimeInterval(60)
    precondition(rectLiveScore.metadataLine(at: oneMinuteAfter, timeZone: pacific) == "Live · 1m ago")
    precondition(rectLiveScore.metadataLine(at: now, timeZone: pacific) == "Live · 2m ago" && !rectLiveScore.isAgedLive(at: now))
    let liveSpoken = rectLiveScore.accessibilityDescription(at: oneMinuteAfter, timeZone: pacific)
    precondition(liveSpoken == "Los Angeles Dodgers at San Francisco Giants. Score Los Angeles Dodgers 2, San Francisco Giants 3. San Francisco Giants 64%. Live, 1 minute ago. Open your game in Bain Luck.",
                 "Unexpected live spoken copy: \(liveSpoken)")
    let liveDates = WatchRectangularReading.timelineDates(for: snapLiveScore, now: now)
    let ageSwitch = rectLiveScore.observedAt.addingTimeInterval(121)
    precondition(liveDates.first == now && liveDates == liveDates.sorted())
    precondition(liveDates.contains(ageSwitch) && rectLiveScore.isAgedLive(at: ageSwitch))
    precondition(rectLiveScore.metadataLine(at: ageSwitch, timeZone: pacific) == "As of 10:58 AM")
    precondition(rectLiveScore.metadataLine(at: rectLiveScore.observedAt.addingTimeInterval(59 * 60), timeZone: pacific) == "As of 10:58 AM")
    precondition(rectLiveScore.accessibilityDescription(at: ageSwitch, timeZone: pacific).contains("As of 10:58 AM."))

    // Verify exact "As of 1:29 PM" specimen in Pacific time (20:29Z in PDT = 1:29 PM).
    let specimenClock = ISO8601DateFormatter().date(from: "2026-10-04T21:28:00Z")!
    let specimenGame = try decodeGame(
        "\"status\":\"live\",\"sport\":\"baseball_mlb\",\"hero_probability\":0.64,\"hero_probability_away\":0.36,\"hero_probability_observed_at\":\"2026-10-04T20:29:00Z\",\(home),\(away)"
    )
    let rectSpecimen = WatchComplicationProjection.snapshot(game: specimenGame, savedAt: specimenClock)!.validatedRectangularReading(now: specimenClock)!
    precondition(rectSpecimen.metadataLine(at: specimenClock, timeZone: pacific) == "As of 1:29 PM")
    precondition(rectSpecimen.accessibilityDescription(at: specimenClock, timeZone: pacific).contains("As of 1:29 PM."))

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
    precondition(rectLagged.headerLine() == "LA at SF" && rectLagged.metadataLine(at: now, timeZone: pacific) == "Live · <1m ago")

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

    // 2. Live score-only state: omitted from the rectangular face (falls back to launcher; parent/circular score retained).
    let liveScoreOnly = try decodeGame(
        "\"status\":\"live\",\"home_score\":3,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    let snapScoreOnly = WatchComplicationProjection.snapshot(game: liveScoreOnly, savedAt: now)!
    precondition(snapScoreOnly.validatedCircularReading(now: now)?.value == "Score 2–3")
    precondition(snapScoreOnly.rectangularReading == nil && snapScoreOnly.validatedRectangularReading(now: now) == nil,
                 "Live score without probability must not appear on the rectangular face")
    for retiredKind in ["liveScoreOnly", "scheduledStart"] {
        var retiredObj = try JSONSerialization.jsonObject(with: JSONEncoder().encode(snapLiveScore)) as! [String: Any]
        var retiredRect = retiredObj["rectangularReading"] as! [String: Any]
        retiredRect["kind"] = retiredKind
        retiredObj["rectangularReading"] = retiredRect
        let decodedRetired = try JSONDecoder().decode(WatchComplicationSnapshot.self, from: JSONSerialization.data(withJSONObject: retiredObj))
        precondition(decodedRetired.rectangularReading == nil && decodedRetired.validatedRectangularReading(now: now) == nil,
                     "Retired odds-less kind \(retiredKind) must decode nil and fall back to launcher")
    }

    // 3a. Scheduled state with pregame probability (never shows fake 0–0; shows "Open to update" once start passes)
    let scheduledForecast = try decodeGame(
        "\"status\":\"scheduled\",\"commence_time\":\"2026-10-04T23:00:00Z\",\"home_score\":0,\"away_score\":0,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\"hero_probability\":0.55,\"hero_probability_away\":0.45,\"hero_probability_observed_at\":\"2026-10-04T17:57:00Z\",\(home),\(away)"
    )
    let snapSchedForecast = WatchComplicationProjection.snapshot(game: scheduledForecast, savedAt: now)!
    let rectSchedForecast = snapSchedForecast.validatedRectangularReading(now: now)!
    precondition(rectSchedForecast.kind == .scheduledForecast && rectSchedForecast.homeScore == nil && rectSchedForecast.awayScore == nil)
    precondition(rectSchedForecast.headerLine() == "LA at SF" && !rectSchedForecast.headerLine().contains("0–0"))
    precondition(rectSchedForecast.primaryLine(at: now) == "SF 55%")
    precondition(rectSchedForecast.metadataLine(at: now, timeZone: pacific) == "Today 4:00 PM" && !rectSchedForecast.isAgedLive(at: now))
    let daysAwayForecast = try decodeGame(
        "\"status\":\"scheduled\",\"commence_time\":\"2026-10-06T20:25:00Z\",\"hero_probability\":0.55,\"hero_probability_away\":0.45,\"hero_probability_observed_at\":\"2026-10-04T17:57:00Z\",\(home),\(away)"
    )
    let rectDaysAway = WatchComplicationProjection.snapshot(game: daysAwayForecast, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectDaysAway.metadataLine(at: now, timeZone: pacific) == "Tue 1:25 PM")
    let scheduledNoTime = try decodeGame(
        "\"status\":\"scheduled\",\"hero_probability\":0.55,\"hero_probability_away\":0.45,\"hero_probability_observed_at\":\"2026-10-04T17:57:00Z\",\(home),\(away)"
    )
    let rectSchedNoTime = WatchComplicationProjection.snapshot(game: scheduledNoTime, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectSchedNoTime.metadataLine(at: now, timeZone: pacific) == "Scheduled · 3m ago")
    let forecastStart = rectSchedForecast.commenceTime!
    precondition(WatchRectangularReading.timelineDates(for: snapSchedForecast, now: now).contains(forecastStart))
    precondition(rectSchedForecast.metadataLine(at: forecastStart, timeZone: pacific) == "Open to update")
    precondition(rectSchedForecast.metadataLine(at: rectSchedForecast.observedAt.addingTimeInterval(23 * 3600), timeZone: pacific) == "Open to update")
    precondition(rectSchedForecast.accessibilityDescription(at: forecastStart, timeZone: pacific).contains("Open to update."))

    // 3b. Scheduled state without pregame probability: omitted completely (falls back to launcher)
    let scheduledStartOnly = try decodeGame(
        "\"status\":\"scheduled\",\"commence_time\":\"2026-10-04T23:00:00Z\",\"home_score\":0,\"away_score\":0,\"score_observed_at\":\"2026-10-04T17:59:00Z\",\(home),\(away)"
    )
    precondition(WatchComplicationProjection.snapshot(game: scheduledStartOnly, savedAt: now) == nil,
                 "Scheduled game without probability must not publish a snapshot")

    // 4. Final state ("Final · SF 4, LA 2", winner first, without stale pre-final probability)
    let finalGame = try decodeGame(
        "\"status\":\"completed\",\"home_score\":4,\"away_score\":2,\"hero_probability\":0.99,\"hero_probability_observed_at\":\"2026-10-04T17:58:00Z\",\"score_observed_at\":\"2026-10-04T17:58:00Z\",\(home),\(away)"
    )
    let snapFinal = WatchComplicationProjection.snapshot(game: finalGame, savedAt: now)!
    let rectFinal = snapFinal.validatedRectangularReading(now: now)!
    precondition(rectFinal.kind == .finalResult && rectFinal.homePercent == nil)
    precondition(rectFinal.headerLine() == "LA at SF")
    precondition(rectFinal.primaryLine(at: now) == "Final · SF 4, LA 2" && !rectFinal.primaryLine(at: now).contains("%"))
    precondition(rectFinal.primaryLine(preferCompact: true, at: now) == "Final · SF 4, LA 2")
    precondition(rectFinal.metadataLine(at: now, timeZone: pacific) == "2m ago" && !rectFinal.isAgedLive(at: now.addingTimeInterval(3600)))
    let finalDates = WatchRectangularReading.timelineDates(for: snapFinal, now: now)
    let oneHour = rectFinal.observedAt.addingTimeInterval(3600)
    let oneDay = rectFinal.observedAt.addingTimeInterval(86400)
    precondition(finalDates.contains(oneHour) && finalDates.contains(oneDay))
    precondition(rectFinal.metadataLine(at: oneHour, timeZone: pacific) == "1h ago")
    precondition(rectFinal.metadataLine(at: oneDay, timeZone: pacific) == "1d ago")

    let awayFinalGame = try decodeGame(
        "\"status\":\"completed\",\"home_score\":2,\"away_score\":4,\"score_observed_at\":\"2026-10-04T17:58:00Z\",\(home),\(away)"
    )
    let rectAwayFinal = WatchComplicationProjection.snapshot(game: awayFinalGame, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectAwayFinal.primaryLine(at: now) == "Final · LA 4, SF 2")

    let tieFinalGame = try decodeGame(
        "\"status\":\"completed\",\"home_score\":2,\"away_score\":2,\"score_observed_at\":\"2026-10-04T17:58:00Z\",\(home),\(away)"
    )
    let rectTieFinal = WatchComplicationProjection.snapshot(game: tieFinalGame, savedAt: now)!.validatedRectangularReading(now: now)!
    precondition(rectTieFinal.primaryLine(at: now) == "Final · LA 2, SF 2")

    // 5. Standing-rule guard across all timeline entries and worst-case ages: never "Saved", never "Stale", and fits budget.
    for snap in [snapLiveScore, snapSchedForecast, snapFinal] {
        let reading = snap.validatedRectangularReading(now: now)!
        for date in WatchRectangularReading.timelineDates(for: snap, now: now) + [
            reading.observedAt.addingTimeInterval(30),
            reading.observedAt.addingTimeInterval(59 * 60),
            reading.observedAt.addingTimeInterval(23 * 3600),
            reading.observedAt.addingTimeInterval(7 * 86400),
        ] {
            let primary = reading.primaryLine(at: date)
            let meta = reading.metadataLine(at: date, timeZone: pacific)
            let spoken = reading.accessibilityDescription(at: date, timeZone: pacific)
            for text in [primary, meta, spoken] {
                precondition(!text.localizedCaseInsensitiveContains("stale"), "Standing rule: never say stale anywhere: \(text)")
                precondition(!text.localizedCaseInsensitiveContains("saved"), "Standing rule: never say saved on rectangular face: \(text)")
            }
            precondition(meta.count <= WatchRectangularReading.maxSingleLineMetadataCharacters,
                         "Metadata exceeds \(WatchRectangularReading.maxSingleLineMetadataCharacters)-char narrow-face budget (\(meta.count)): \(meta)")
            if reading.isAgedLive(at: date) {
                precondition(meta.hasPrefix("As of "), "Aged live reading must show As of clock time: \(meta)")
            }
            if reading.kind == .scheduledForecast, let kickoff = reading.commenceTime, date >= kickoff {
                precondition(meta == "Open to update", "Passed scheduled start must show Open to update: \(meta)")
            }
        }
    }
    print("PASS: rectangular complication probability/final wording, As of clock, Open to update, Final · SF 4 LA 2, omitted odds-less states, and zero Saved/stale strings")
}
