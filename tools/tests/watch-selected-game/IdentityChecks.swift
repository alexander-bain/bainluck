import Foundation

/// Provider-proven identity belongs to one saved reading, never to names or feed order.
@MainActor func checkWatchSelectedIdentity() async throws {
    let suite = "watch-selected-identity-\(UUID().uuidString)"
    let defaults = UserDefaults(suiteName: suite)!
    defer { defaults.removePersistentDomain(forName: suite) }
    let selectionKey = "bainluck_watch_selected_event_id"
    let snapshotKey = "bainluck_watch_selected_game_snapshot_v1"
    let transport = Stub()
    var wall = ISO8601DateFormatter().date(from: "2026-10-03T18:00:00Z")!
    var elapsed: TimeInterval = 1000
    var publications: [(Int?, Date?)] = []
    var telemetry: [(String, Int)] = []
    let store = WatchSelectedGameStore(transport: transport, defaults: defaults,
        now: { wall }, retryClock: { elapsed },
        publish: { game, date in publications.append((game?.id, date)) })
    store.telemetry = { outcome, _, count in telemetry.append((outcome, count)) }
    func reading(_ id: Int, live: Bool = true) throws -> WatchSelectedGame {
        try event(id, extras: ",\"status\":\"\(live ? "live" : "scheduled")\",\"home_score\":3,\"away_score\":2,\"hero_probability\":0.64,\"hero_probability_observed_at\":\"2026-10-03T17:57:00Z\",\"score_observed_at\":\"2026-10-03T17:59:30Z\"")
    }
    func respond(_ result: Result<WatchSelectedGame, Error>) async {
        let id = store.selectedEventID!
        let task = Task { await store.refresh() }
        await transport.waitFor(id)
        await transport.finish(id, result: result)
        await task.value
    }
    func identity() throws -> [Int] {
        let object = try JSONSerialization.jsonObject(with: defaults.data(forKey: snapshotKey)!) as! [String: Any]
        return object["selectedIdentityIDs"] as! [Int]
    }
    func expectIdentity(_ expected: [Int]) throws {
        let actual = try identity()
        precondition(actual == expected, "Identity order must remain bounded and deterministic")
    }
    func reselect(_ id: Int) async {
        let bytes = defaults.data(forKey: snapshotKey)
        let selected = store.selectedEventID
        let game = store.game?.id
        let fetched = store.fetchedAt
        let error = store.errorMessage
        let refreshing = store.isRefreshing
        let restored = store.isRestoredReading
        let delay = store.nextRefreshDelay
        let count = publications.count
        let requests = await transport.fetchCount
        store.select(eventID: id)
        precondition(store.selectedEventID == selected && store.game?.id == game && store.fetchedAt == fetched,
            "Proven reselection preserves the reading immediately")
        precondition(store.errorMessage == error && store.isRefreshing == refreshing && store.isRestoredReading == restored)
        precondition(store.nextRefreshDelay == delay && publications.count == count)
        precondition(defaults.data(forKey: snapshotKey) == bytes && defaults.integer(forKey: selectionKey) == selected)
        let after = await transport.fetchCount
        precondition(after == requests, "Reselection cannot add a network request")
    }
    func foregroundWait(_ expected: TimeInterval) async {
        let before = await transport.fetchCount
        var waits: [TimeInterval] = []
        await store.runForegroundRefresh { delay in
            waits.append(delay)
            throw CancellationError()
        }
        let after = await transport.fetchCount
        precondition(waits == [expected] && after == before, "Reselection preserves the completion deadline")
    }

    precondition(!store.isSelected(eventID: 0) && !store.isSelected(eventID: -1))
    store.select(eventID: 101)
    precondition(store.isSelected(eventID: 101) && !store.isSelected(eventID: 111), "Pending selection matches only its own ID")
    await respond(.success(try reading(101)))
    await reselect(101)
    try expectIdentity([101])
    await respond(.success(try reading(111)))
    precondition(store.isSelected(eventID: 101) && store.isSelected(eventID: 111) && !store.isSelected(eventID: 202))
    await reselect(101)
    await reselect(111)
    precondition(store.game?.observationAge(at: wall) == 30 && store.game?.probabilityAge(at: wall) == 180)
    elapsed += 5
    wall += 7200
    await reselect(101)
    await foregroundWait(25)
    precondition(store.fetchedAt == wall.addingTimeInterval(-7200), "Reuse never stamps a newer fetch time")
    await respond(.failure(URLError(.notConnectedToInternet))) // Requests canonical111.
    await reselect(101)
    precondition(store.game?.id == 111 && store.nextRefreshDelay == 30 && telemetry.last?.0 == "offline")
    await respond(.failure(URLError(.notConnectedToInternet)))
    await reselect(101)
    await foregroundWait(60)
    await respond(.failure(WatchSelectedGameRequestError.retryAfter(180)))
    elapsed += 10
    await reselect(101)
    await foregroundWait(170)
    store.allowManualRetry()
    precondition(store.nextRefreshDelay == 120, "Explicit manual retry clears server pause but keeps failure backoff")
    await respond(.success(try reading(111, live: false)))
    elapsed += 5
    await reselect(101)
    await foregroundWait(295)

    let snapshot = defaults.data(forKey: snapshotKey)!
    var restoredPublications = 0
    let restored = WatchSelectedGameStore(transport: transport, defaults: defaults,
        now: { wall }, publish: { _, _ in restoredPublications += 1 })
    precondition(restored.isSelected(eventID: 101) && restored.isSelected(eventID: 111) && restored.isRestoredReading)
    let restoredFetch = restored.fetchedAt
    restored.select(eventID: 101)
    precondition(restored.game?.id == 111 && restored.isRestoredReading && restored.fetchedAt == restoredFetch)
    precondition(defaults.data(forKey: snapshotKey) == snapshot && restoredPublications == 1)
    let offline = Task { await restored.refresh() }
    await transport.waitFor(111)
    await transport.finish(111, result: .failure(URLError(.notConnectedToInternet)))
    await offline.value
    restored.select(eventID: 101)
    precondition(restored.game?.id == 111 && restored.isRestoredReading && defaults.data(forKey: snapshotKey) == snapshot)

    await respond(.success(try reading(121)))
    try expectIdentity([101, 111, 121])
    let chained = WatchSelectedGameStore(defaults: defaults)
    precondition([101, 111, 121].allSatisfy { chained.isSelected(eventID: $0) })
    await respond(.success(try reading(101)))
    try expectIdentity([101, 111, 121])
    for id in 131...140 { await respond(.success(try reading(id))) }
    try expectIdentity([101, 134, 135, 136, 137, 138, 139, 140])
    precondition(store.isSelected(eventID: 101) && store.isSelected(eventID: 140) && !store.isSelected(eventID: 133))
    await reselect(101)

    // A known alias while a canonical request is pending must not invalidate that request.
    let pending = Task { await store.refresh() }
    await transport.waitFor(140)
    await reselect(101)
    precondition(store.isRefreshing)
    await transport.finish(140, result: .success(try reading(141)))
    await pending.value
    precondition(store.game?.id == 141 && store.isSelected(eventID: 101) && store.isSelected(eventID: 140))

    let stableBytes = defaults.data(forKey: snapshotKey)
    let stableCount = publications.count
    let cancelled = Task { await store.refresh() }
    await transport.waitFor(141)
    cancelled.cancel()
    await transport.finish(141, result: .success(try reading(999)))
    await cancelled.value
    precondition(!store.isSelected(eventID: 999) && store.game?.id == 141 && publications.count == stableCount)
    precondition(defaults.data(forKey: snapshotKey) == stableBytes && telemetry.last?.0 == "cancelled")

    let older = Task { await store.refresh() }
    await transport.waitFor(141)
    let newer = Task { await store.refresh() }
    await transport.waitFor(141, count: 2)
    await transport.finishNewest(141, result: .success(try reading(142)))
    await newer.value
    let newestBytes = defaults.data(forKey: snapshotKey)
    let newestPublications = publications.count
    await transport.finish(141, result: .success(try reading(998)))
    await older.value
    precondition(store.game?.id == 142 && !store.isSelected(eventID: 998))
    precondition(defaults.data(forKey: snapshotKey) == newestBytes && publications.count == newestPublications,
        "An older response arriving after canonicalization cannot learn or publish identity")

    let stale = Task { await store.refresh() }
    await transport.waitFor(142)
    store.select(eventID: 202) // Same names/scores, but never proven equivalent.
    precondition(store.game == nil && !store.isSelected(eventID: 101) && defaults.data(forKey: snapshotKey) == nil)
    await transport.finish(142, result: .success(try reading(997)))
    await stale.value
    precondition(!store.isSelected(eventID: 997) && store.game == nil)
    await respond(.failure(URLError(.notConnectedToInternet)))
    precondition(store.game == nil, "Another game's saved reading must not leak into an unverified selection")
    await respond(.success(try reading(222)))
    try expectIdentity([202, 222])
    let clearing = Task { await store.refresh() }
    await transport.waitFor(222)
    store.clearSelection()
    await transport.finish(222, result: .success(try reading(996)))
    await clearing.value
    precondition(!store.isSelected(eventID: 202) && !store.isSelected(eventID: 222) && !store.isSelected(eventID: 996))
    precondition(defaults.data(forKey: snapshotKey) == nil && store.selectedEventID == nil)

    // Reject optional metadata as a whole without dropping otherwise valid legacy readings.
    let gameObject = try JSONSerialization.jsonObject(with: JSONEncoder().encode(reading(111)))
    let expectedReading = try reading(111)
    let invalidMetadata: [Any?] = [nil, NSNull(), "101,111", ["101", "111"], [], [0, 111], [-1, 111],
        [101, 111, 111], Array(103...111), [101, 121], [101, 111.5]]
    for metadata in invalidMetadata {
        var object: [String: Any] = ["version": 1, "game": gameObject, "fetchedAt": wall.timeIntervalSinceReferenceDate]
        object["selectedIdentityIDs"] = metadata
        let bytes = try JSONSerialization.data(withJSONObject: object)
        defaults.set(111, forKey: selectionKey)
        defaults.set(bytes, forKey: snapshotKey)
        let legacy = WatchSelectedGameStore(defaults: defaults)
        precondition(legacy.game?.id == 111 && legacy.fetchedAt == wall && legacy.isRestoredReading)
        precondition(legacy.isSelected(eventID: 111) && !legacy.isSelected(eventID: 101))
        legacy.select(eventID: 111)
        precondition(defaults.data(forKey: snapshotKey) == bytes, "Init/canonical reselection never rewrites legacy metadata")
        precondition(legacy.game?.scoreObservedAt == expectedReading.scoreObservedAt)
        precondition(legacy.game?.probabilityObservedAt == expectedReading.probabilityObservedAt)
    }
    // Required snapshot fields and canonical selection match remain fail-closed.
    for bad: [String: Any] in [
        ["version": 2, "game": gameObject, "fetchedAt": wall.timeIntervalSinceReferenceDate],
        ["version": 1, "game": [:], "fetchedAt": wall.timeIntervalSinceReferenceDate],
        ["version": 1, "game": gameObject, "fetchedAt": "bad"],
        ["version": 1, "game": gameObject],
    ] {
        defaults.set(try JSONSerialization.data(withJSONObject: bad), forKey: snapshotKey)
        precondition(WatchSelectedGameStore(defaults: defaults).game == nil)
    }
    defaults.set(snapshot, forKey: snapshotKey)
    defaults.set(202, forKey: selectionKey)
    let mismatch = WatchSelectedGameStore(defaults: defaults)
    precondition(mismatch.game == nil && !mismatch.isSelected(eventID: 101) && !mismatch.isSelected(eventID: 111))
    print("PASS: selected identity direct/alias no-op, clocks, restart/offline, bounded chains/cycles, cadence/backoff/server pause, pending/canceled/stale fences, unrelated selection/clear and tolerant legacy metadata")
}

private extension Stub {
    func finishNewest(_ id: Int, result: Result<WatchSelectedGame, Error>) {
        let continuation = calls[id]?.popLast()
        continuation?.resume(with: result)
    }
}
