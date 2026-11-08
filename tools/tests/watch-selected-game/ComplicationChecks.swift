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
