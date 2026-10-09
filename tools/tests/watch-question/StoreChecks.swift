import Foundation

actor QuestionSuspendedTransport: WatchQuestionDetailTransport {
    struct Request: Sendable { let sequence: Int; let marketID: Int }
    private var sequence = 0
    private var pending: [Int: CheckedContinuation<WatchQuestionDetail, Error>] = [:]
    private var announced: [Request] = []
    private var waiter: CheckedContinuation<Request, Never>?

    func load(id: Int) async throws -> WatchQuestionDetail {
        // Ignores cancellation until the test resolves it, like a late network reply.
        try await withCheckedThrowingContinuation { continuation in
            sequence += 1
            pending[sequence] = continuation
            let request = Request(sequence: sequence, marketID: id)
            if let waiter { self.waiter = nil; waiter.resume(returning: request) }
            else { announced.append(request) }
        }
    }
    func next() async -> Request {
        if !announced.isEmpty { return announced.removeFirst() }
        precondition(waiter == nil)
        return await withCheckedContinuation { waiter = $0 }
    }
    func resolve(_ request: Request, _ value: WatchQuestionDetail) {
        pending.removeValue(forKey: request.sequence)!.resume(returning: value)
    }
    func fail(_ request: Request, error: Error = URLError(.notConnectedToInternet)) {
        pending.removeValue(forKey: request.sequence)!.resume(throwing: error)
    }
    func count() -> Int { sequence }
    func drained() -> Bool { pending.isEmpty && announced.isEmpty && waiter == nil }
}

@MainActor enum StoreChecks {
    static func fixture(_ id: Int, _ text: String) throws -> WatchQuestionDetail {
        let bytes = try JSONSerialization.data(withJSONObject: ["id": id, "name": text,
            "status": "open", "outcomes": [["id": 7, "name": "Supplied name", "probability": 0.3]]])
        return try WatchQuestionDetailDecoder.decode(bytes, expectedID: id)
    }
    static func drained(_ transport: QuestionSuspendedTransport) async {
        let result = await transport.drained()
        precondition(result, "every continuation resolved; no orphan task")
    }
    static func run() async throws {
        let old = try fixture(42, "Old question"), fresh = try fixture(42, "Current question")
        // Exercise the production HTTP classification through the actual store.
        try WatchQuestionDetailServiceError.validate(status: 200)
        for (status, expected) in [
            (404, "This question is currently unavailable."),
            (429, "Service is busy. Try again shortly."),
            (503, "Service is busy. Try again shortly."),
            (500, "Couldn't read this question. Try again.")
        ] {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let loading = Task { await store.load(id: 42) }; let request = await transport.next()
            do {
                try WatchQuestionDetailServiceError.validate(status: status)
                preconditionFailure("non-200 classified as a readable question")
            } catch { await transport.fail(request, error: error) }
            await loading.value
            precondition(store.error == expected && store.detail == nil && !store.loading)
            await drained(transport)
        }
        for (code, expected) in [
            (URLError.notConnectedToInternet, "Offline. Reconnect and try again."),
            (URLError.networkConnectionLost, "Offline. Reconnect and try again."),
            (URLError.timedOut, "Connection timed out. Try again.")
        ] {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let loading = Task { await store.load(id: 42) }; let request = await transport.next()
            await transport.fail(request, error: URLError(code)); await loading.value
            precondition(store.error == expected && store.detail == nil && !store.loading)
            await drained(transport)
        }
        // An older success OR failure cannot replace a newer completed request.
        for failOld in [false, true] {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let first = Task { await store.load(id: 42) }; let a = await transport.next()
            let second = Task { await store.load(id: 42) }; let b = await transport.next()
            await transport.resolve(b, fresh); await second.value
            if failOld { await transport.fail(a) } else { await transport.resolve(a, old) }
            await first.value
            precondition(store.detail == fresh && store.error == nil && !store.loading)
            await drained(transport)
        }
        // Both Swift task cancellation and surface cancellation refuse late bytes.
        for cancelSurface in [false, true] {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let loading = Task { await store.load(id: 42) }; let a = await transport.next()
            if cancelSurface { store.cancel() } else { loading.cancel() }
            await transport.resolve(a, fresh); await loading.value
            precondition(store.detail == nil && store.error == nil && !store.loading)
            await drained(transport)
        }
        // Even an injected transport returning the wrong decoded market is refused.
        do {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let loading = Task { await store.load(id: 42) }; let a = await transport.next()
            await transport.resolve(a, try fixture(43, "Wrong question")); await loading.value
            precondition(store.detail == nil && store.error != nil && !store.loading)
            await drained(transport)
        }
        // Failed request has an explicit state; a user retry clears it and succeeds.
        do {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let first = Task { await store.load(id: 42) }; let a = await transport.next()
            await transport.fail(a); await first.value
            precondition(store.detail == nil && store.error != nil && !store.loading)
            let retry = Task { await store.load(id: 42) }; let b = await transport.next()
            precondition(store.error == nil && store.loading)
            await transport.resolve(b, fresh); await retry.value
            precondition(store.detail == fresh && store.error == nil && !store.loading)
            let count = await transport.count(); precondition(count == 2, "no automatic retry")
            await drained(transport)
        }
        // Invalid route identity cannot cause any transport request.
        do {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            await store.load(id: 0)
            let count = await transport.count()
            precondition(count == 0 && store.detail == nil && store.error != nil)
            await drained(transport)
        }
        // A destination changes before its new task starts: old error/spinner must not leak.
        for failFirst in [false, true] {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let first = Task { await store.load(id: 42) }; let a = await transport.next()
            precondition(store.requestStatus(for: 42).loading)
            precondition(!store.requestStatus(for: 43).loading && store.requestStatus(for: 43).error == nil)
            if failFirst {
                await transport.fail(a); await first.value
                precondition(store.requestStatus(for: 42).error != nil)
                precondition(store.requestStatus(for: 43).error == nil)
            }
            let next = Task { await store.load(id: 43) }; let b = await transport.next()
            precondition(store.requestStatus(for: 43).loading && store.requestStatus(for: 43).error == nil)
            precondition(!store.requestStatus(for: 42).loading && store.requestStatus(for: 42).error == nil)
            if !failFirst { await transport.fail(a); await first.value }
            precondition(store.requestStatus(for: 43).loading && store.requestStatus(for: 43).error == nil)
            await transport.resolve(b, try fixture(43, "Different exact question")); await next.value
            store.cancel()
            precondition(!store.requestStatus(for: 43).loading && store.requestStatus(for: 43).error == nil)
            await drained(transport)
        }
        // Reusing a view/store for a different exact ID clears the old question.
        do {
            let transport = QuestionSuspendedTransport(), store = WatchQuestionDetailStore(transport: transport)
            let first = Task { await store.load(id: 42) }; let a = await transport.next()
            await transport.resolve(a, old); await first.value
            let other = try fixture(43, "Different exact question")
            let next = Task { await store.load(id: 43) }; let b = await transport.next()
            precondition(b.marketID == 43 && store.detail == nil && store.loading)
            await transport.resolve(b, other); await next.value
            precondition(store.detail == other)
            store.cancel(); precondition(store.detail == nil)
            await drained(transport)
        }
    }
}
