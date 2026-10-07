import Foundation

private func pickerEvent(_ id: Int, home: String? = "Home", away: String? = "Away") throws -> WatchFeedEvent {
    var object: [String: Any] = ["id": id]
    if let home { object["home_team"] = home }
    if let away { object["away_team"] = away }
    let decoder = JSONDecoder()
    decoder.keyDecodingStrategy = .convertFromSnakeCase
    return try decoder.decode(WatchFeedEvent.self, from: JSONSerialization.data(withJSONObject: object))
}

/// Controlled responses make ordering and cancellation independent of network timing.
private actor PickerTransportStub: WatchGamePickerTransport {
    private var nextRequest = 0
    private var pending: [Int: CheckedContinuation<WatchGamePickerBatch, Error>] = [:]

    func fetchGames() async throws -> WatchGamePickerBatch {
        nextRequest += 1
        let request = nextRequest
        return try await withCheckedThrowingContinuation { pending[request] = $0 }
    }

    func waitFor(_ request: Int) async {
        while pending[request] == nil { await Task.yield() }
    }

    func finish(_ request: Int, _ result: Result<[WatchFeedEvent], Error>) {
        finishBatch(request, result.map { WatchGamePickerBatch(games: $0) })
    }

    func finishBatch(_ request: Int, _ result: Result<WatchGamePickerBatch, Error>) {
        guard let continuation = pending.removeValue(forKey: request) else {
            preconditionFailure("Missing picker request \(request)")
        }
        continuation.resume(with: result)
    }
}

@MainActor func checkWatchGamePicker() async throws {
    try await checkPickerNetworkGuidance()
    let transport = PickerTransportStub()
    let store = WatchGamePickerStore(transport: transport)
    precondition(store.games.isEmpty && !store.isLoading && store.errorMessage == nil && store.omittedGameCount == 0)

    let first = Task { await store.refresh() }
    await transport.waitFor(1)
    precondition(store.isLoading)
    let input = try [
        pickerEvent(0), pickerEvent(-1),
        pickerEvent(3, home: nil), pickerEvent(4, away: nil),
        pickerEvent(5, home: " \n\t"), pickerEvent(6, away: ""),
        pickerEvent(3, home: "First valid"), pickerEvent(8),
        pickerEvent(3, home: "Duplicate"), pickerEvent(7),
    ]
    await transport.finish(1, .success(input))
    await first.value
    precondition(store.games.map(\.id) == [3, 8, 7], "Filter malformed games, deduplicate first valid IDs, and preserve server order")
    precondition(store.games.first?.homeTeam == "First valid", "An invalid row cannot reserve an ID")
    precondition(store.omittedGameCount == 6, "Only malformed rows count as omissions; duplicate valid IDs do not")
    precondition(!store.isLoading && store.errorMessage == nil)

    let failure = Task { await store.refresh() }
    await transport.waitFor(2)
    await transport.finish(2, .failure(URLError(.notConnectedToInternet)))
    await failure.value
    precondition(store.games.map(\.id) == [3, 8, 7] && store.omittedGameCount == 6)
    precondition(!store.isLoading && store.errorMessage != nil, "Failed refresh retains the usable list and explains failure")
    let retainedError = store.errorMessage

    let cancelledRetry = Task { await store.refresh() }
    await transport.waitFor(3)
    precondition(store.isLoading && store.errorMessage == retainedError, "Starting retry does not claim recovery")
    cancelledRetry.cancel()
    await transport.finish(3, .success(try [pickerEvent(99)]))
    await cancelledRetry.value
    precondition(store.games.map(\.id) == [3, 8, 7] && store.omittedGameCount == 6)
    precondition(!store.isLoading && store.errorMessage == retainedError, "A cancelled response cannot replace the list or clear the prior error")

    let cancellationError = Task { await store.refresh() }
    await transport.waitFor(4)
    await transport.finish(4, .failure(CancellationError()))
    await cancellationError.value
    precondition(!store.isLoading && store.errorMessage == retainedError && store.games.count == 3)

    let older = Task { await store.refresh() }
    await transport.waitFor(5)
    let latest = Task { await store.refresh() }
    await transport.waitFor(6)
    await transport.finish(5, .success(try [pickerEvent(50)]))
    await older.value
    precondition(store.isLoading && store.games.map(\.id) == [3, 8, 7] && store.errorMessage == retainedError,
                 "An older completion cannot end loading or replace the retained state while the latest request waits")
    await transport.finish(6, .success(try [pickerEvent(60)]))
    await latest.value
    precondition(store.games.map(\.id) == [60] && !store.isLoading && store.errorMessage == nil && store.omittedGameCount == 0)

    let staleFailure = Task { await store.refresh() }
    await transport.waitFor(7)
    let empty = Task { await store.refresh() }
    await transport.waitFor(8)
    await transport.finish(8, .success([]))
    await empty.value
    precondition(store.games.isEmpty && !store.isLoading && store.errorMessage == nil && store.omittedGameCount == 0,
                 "A successful empty response clears old games and remains distinct from failure")
    await transport.finish(7, .failure(URLError(.timedOut)))
    await staleFailure.value
    precondition(store.games.isEmpty && !store.isLoading && store.errorMessage == nil, "A late older failure cannot overwrite a newer success")

    let staleSuccess = Task { await store.refresh() }
    await transport.waitFor(9)
    let newerSuccess = Task { await store.refresh() }
    await transport.waitFor(10)
    await transport.finish(10, .success(try [pickerEvent(100)]))
    await newerSuccess.value
    await transport.finish(9, .success(try [pickerEvent(90)]))
    await staleSuccess.value
    precondition(store.games.map(\.id) == [100] && !store.isLoading && store.errorMessage == nil,
                 "Latest request wins even when an earlier successful request returns last")

    func decodedBatch(_ json: String) throws -> WatchGamePickerBatch {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return WatchGamePickerBatch(feed: try decoder.decode(WatchFeedResponse.self, from: Data(json.utf8)))
    }
    let malformedAndValid = try decodedBatch("""
        {"items":[
          {"type":"event","data":{"id":"bad","home_team":"Broken","away_team":"Away"}},
          {"type":"event","data":{"id":110,"home_team":"Home","away_team":"Away"}},
          {"type":"event","data":{"id":111,"home_team":"","away_team":"Away"}},
          {"type":"futures","data":{}}
        ]}
        """)
    precondition(malformedAndValid.omittedGameCount == 1 && malformedAndValid.games.map(\.id) == [110, 111],
                 "Event decode failures survive as omissions; unrelated feed types are not omitted games")
    let mixed = Task { await store.refresh() }
    await transport.waitFor(11)
    await transport.finishBatch(11, .success(malformedAndValid))
    await mixed.value
    precondition(store.games.map(\.id) == [110] && store.omittedGameCount == 2 && store.errorMessage == nil,
                 "Count transport decode omissions together with picker validation omissions")

    let allMalformed = try decodedBatch("""
        {"items":[
          {"type":"event","data":{}},
          {"type":"event","data":null},
          {"type":"event"}
        ]}
        """)
    precondition(allMalformed.games.isEmpty && allMalformed.omittedGameCount == 3)
    let malformed = Task { await store.refresh() }
    await transport.waitFor(12)
    await transport.finishBatch(12, .success(allMalformed))
    await malformed.value
    precondition(store.games.isEmpty && store.omittedGameCount == 3 && store.errorMessage == nil && !store.isLoading,
                 "All malformed event rows remain visibly distinguishable from a genuine empty feed")
    print("PASS: watch picker ordered valid games, first-valid deduplication, omission count, retained failure/retry, cancellation, empty success, and overlapping request fencing")
    print("PASS: malformed event decode omissions, combined decode/validation counts, and all-malformed feed distinction")
}

@MainActor private func checkPickerNetworkGuidance() async throws {
    let failures: [(Error, String)] = [
        (URLError(.notConnectedToInternet), "Offline. Connect to the internet, then refresh games."),
        (URLError(.networkConnectionLost), "Connection interrupted. Refresh games to try again."),
        (URLError(.timedOut), "Connection timed out. Refresh games to try again."),
        (URLError(.badServerResponse), "Couldn't refresh available games. Try again."),
        (WatchSelectedGameRequestError.serviceBusy, "Couldn't refresh available games. Try again."),
    ]
    for (error, expected) in failures {
        let transport = PickerTransportStub()
        let store = WatchGamePickerStore(transport: transport)
        let initial = Task { await store.refresh() }
        await transport.waitFor(1)
        await transport.finishBatch(1, .success(WatchGamePickerBatch(games: try [pickerEvent(101)], omittedGameCount: 2)))
        await initial.value
        let failed = Task { await store.refresh() }
        await transport.waitFor(2)
        await transport.finish(2, .failure(error))
        await failed.value
        precondition(store.errorMessage == expected && !store.isLoading)
        precondition(store.games.map(\.id) == [101] && store.omittedGameCount == 2,
                     "Network guidance must keep prior usable options and omission truth")
        let cancelled = Task { await store.refresh() }
        await transport.waitFor(3)
        await transport.finish(3, .failure(URLError(.cancelled)))
        await cancelled.value
        precondition(store.errorMessage == expected && store.games.map(\.id) == [101])
        let recovered = Task { await store.refresh() }
        await transport.waitFor(4)
        await transport.finish(4, .success(try [pickerEvent(202)]))
        await recovered.value
        precondition(store.errorMessage == nil && !store.isLoading && store.games.map(\.id) == [202] && store.omittedGameCount == 0,
                     "Only completed successful refresh clears failure guidance and updates choices")
    }
    print("PASS: picker offline, interrupted, timeout and generic guidance retain choices, ignore cancellation and clear only on recovery")
}
