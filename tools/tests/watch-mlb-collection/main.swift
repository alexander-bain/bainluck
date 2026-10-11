import Foundation

// This harness invokes the actual proposed WatchMLBCollectionStore. It does not
// reimplement validation, revision fencing, or selection policy. No HTTP runs.
actor SuspendedTransport: WatchMLBCollectionTransport {
    struct Request: Sendable {
        enum Kind: Equatable, Sendable { case collections(Int), membership(String) }
        let id: Int
        let kind: Kind
    }
    private enum Pending {
        case collections(CheckedContinuation<[WatchMLBCollection], Error>)
        case membership(CheckedContinuation<WatchMLBMembership, Error>)
    }
    private var pending: [Int: Pending] = [:]
    private var announced: [Request] = []
    private var waiter: CheckedContinuation<Request, Never>?
    private var issued = 0

    private func announce(_ kind: Request.Kind, pending value: Pending) {
        issued += 1
        pending[issued] = value
        let request = Request(id: issued, kind: kind)
        if let continuation = waiter { waiter = nil; continuation.resume(returning: request) }
        else { announced.append(request) }
    }
    func collections(season: Int) async throws -> [WatchMLBCollection] {
        try await withCheckedThrowingContinuation { announce(.collections(season), pending: .collections($0)) }
    }
    func membership(collection: WatchMLBCollection) async throws -> WatchMLBMembership {
        // Intentionally ignores cancellation until explicitly resolved. A late
        // server response must be harmless even if transport cancellation fails.
        try await withCheckedThrowingContinuation { announce(.membership(collection.slug), pending: .membership($0)) }
    }
    func next() async -> Request {
        if !announced.isEmpty { return announced.removeFirst() }
        precondition(waiter == nil, "one deterministic request waiter")
        return await withCheckedContinuation { waiter = $0 }
    }
    func resolve(_ request: Request, collections: [WatchMLBCollection]) {
        guard case .collections(let continuation)? = pending.removeValue(forKey: request.id) else {
            preconditionFailure("wrong/missing collections continuation")
        }
        continuation.resume(returning: collections)
    }
    func resolve(_ request: Request, membership: WatchMLBMembership) {
        guard case .membership(let continuation)? = pending.removeValue(forKey: request.id) else {
            preconditionFailure("wrong/missing membership continuation")
        }
        continuation.resume(returning: membership)
    }
    func fail(_ request: Request) {
        guard let value = pending.removeValue(forKey: request.id) else { preconditionFailure("missing request") }
        switch value {
        case .collections(let c): c.resume(throwing: URLError(.notConnectedToInternet))
        case .membership(let c): c.resume(throwing: URLError(.notConnectedToInternet))
        }
    }
    func count() -> Int { issued }
    func drained() -> Bool { pending.isEmpty && announced.isEmpty && waiter == nil }
}

@MainActor final class SelectionSink {
    // This is only the synchronous effect observer, not a selected-store clone.
    // Production supplies WatchSelectedGameStore.select(eventID:) at this seam.
    var priorOrSelectedID = 999
    var calls: [Int] = []
    var active = true
    func accept(_ id: Int) { calls.append(id); priorOrSelectedID = id }
}

@MainActor struct Fixtures {
    let collection: WatchMLBCollection
    private let hub: [String: Any]
    init(directory: URL) throws {
        func response(_ name: String) throws -> [String: Any] {
            let root = try JSONSerialization.jsonObject(with: Data(contentsOf: directory.appendingPathComponent(name))) as! [String: Any]
            precondition((root["_representative"] as! String).contains("NOT production"))
            return root["response"] as! [String: Any]
        }
        var index = try response("discovery.json")
        // Independent representative fixtures are intentionally different rows:
        // discovery id81 versus hub id80. Align only this test copy, never the
        // retained originals. DecoderChecks separately rejects the true mismatch.
        var rows = index["collections"] as! [[String: Any]]
        rows[0]["id"] = 80
        index["collections"] = rows
        collection = try WatchMLBCollectionDecoder.collections(JSONSerialization.data(withJSONObject: index), season: 2026)[0]
        hub = try response("postseason.json")
    }
    func membership(revision: Int = 11, published: Bool = true, removing id: Int? = nil, removingQuestion questionID: Int? = nil) throws -> WatchMLBMembership {
        var body = hub
        body["revision"] = revision
        body["state"] = published ? "published" : "withdrawn"
        if let id {
            body["sections"] = (body["sections"] as! [[String: Any]]).map { section in
                var result = section
                result["members"] = (section["members"] as! [[String: Any]]).filter {
                    !(($0["type"] as? String) == "event" && ($0["id"] as? Int) == id)
                }
                return result
            }
        }
        if let questionID {
            body["sections"] = (body["sections"] as! [[String: Any]]).map { section in
                var result = section
                result["members"] = (section["members"] as! [[String: Any]]).filter {
                    !(($0["type"] as? String) == "market" && ($0["id"] as? Int) == questionID)
                }
                return result
            }
        }
        return try WatchMLBCollectionDecoder.membership(JSONSerialization.data(withJSONObject: body), collection: collection)
    }
}

@main struct MLBStoreChecks {
    @MainActor static func check(_ condition: Bool, _ message: String) { precondition(condition, message) }
    @MainActor static func makeStore(_ transport: SuspendedTransport) -> WatchMLBCollectionStore {
        WatchMLBCollectionStore(transport: transport, now: ISO8601DateFormatter().date(from: "2026-10-09T12:00:00Z")!)
    }
    @MainActor static func display(_ store: WatchMLBCollectionStore, _ transport: SuspendedTransport, _ f: Fixtures, revision: Int = 11) async throws {
        let opening = Task { await store.open(f.collection) }
        let request = await transport.next()
        check(request.kind == .membership(f.collection.slug), "opens exact collection")
        await transport.resolve(request, membership: try f.membership(revision: revision))
        await opening.value
        check(store.membership?.games.map(\.id) == [801, 802], "real decoded fixture displayed")
    }
    @MainActor static func tap(_ store: WatchMLBCollectionStore, _ sink: SelectionSink, id: Int = 801) -> Task<Bool, Never> {
        Task { await store.selectGame(id, isActive: { sink.active }, select: { sink.accept($0) }) }
    }
    @MainActor static func unchanged(_ sink: SelectionSink) {
        check(sink.calls.isEmpty && sink.priorOrSelectedID == 999, "denied validation must retain prior selection")
    }
    @MainActor static func finish(_ transport: SuspendedTransport) async {
        let drained = await transport.drained()
        check(drained, "all suspended requests explicitly resolved; no leaked task")
    }
    @MainActor static func olderRefreshLoses(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport)
        try await display(store, transport, f)
        let old = Task { await store.refresh() }
        let oldRequest = await transport.next()
        let newer = Task { await store.refresh() }
        let newRequest = await transport.next()
        await transport.resolve(newRequest, membership: try f.membership(revision: 13))
        await newer.value
        await transport.resolve(oldRequest, membership: try f.membership(revision: 12))
        await old.value
        check(store.membership?.revision == 13 && !store.isLoading, "late older refresh cannot overwrite newer result")
        await finish(transport)
    }
    @MainActor static func browseSupersedesCollection(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport)
        try await display(store, transport, f)
        let old = Task { await store.refresh() }; let oldRequest = await transport.next()
        let browse = Task { await store.browse() }; let browseRequest = await transport.next()
        check(browseRequest.kind == .collections(2026), "browse requests selected season")
        await transport.resolve(browseRequest, collections: [f.collection]); await browse.value
        await transport.resolve(oldRequest, membership: try f.membership()); await old.value
        check(store.collection == nil && store.membership == nil && store.collections == [f.collection], "old collection cannot replace newer Browse")
        await finish(transport)
    }
    @MainActor static func denied(_ f: Fixtures, mode: String) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport), sink = SelectionSink()
        try await display(store, transport, f, revision: mode == "rollback" ? 12 : 11)
        let selection = tap(store, sink)
        let request = await transport.next()
        check(request.kind == .membership(f.collection.slug), "tap validates same exact collection")
        switch mode {
        case "cancel-task": selection.cancel()
        case "cancel-surface": store.cancel()
        case "inactive": sink.active = false
        default: break
        }
        if mode == "failure" { await transport.fail(request) }
        else {
            await transport.resolve(request, membership: try f.membership(
                revision: 11, published: mode != "withdrawal", removing: mode == "removed-member" ? 801 : nil))
        }
        let selected = await selection.value
        check(!selected, "\(mode) must deny selection")
        unchanged(sink)
        if mode == "cancel-surface" { check(store.membership == nil, "inactive cancellation clears membership") }
        if mode == "rollback" || mode == "failure" { check(store.errorMessage != nil, "failure is visible") }
        if mode == "removed-member" {
            check(store.errorMessage == "Boston Red Sox at New York Yankees is no longer available in this collection. Choose another game or refresh.", "removed game explains the exact tapped pairing")
            check(store.membership?.games.map(\.id) == [802], "healthy current sibling stays available")
        }
        if mode == "withdrawal" { check(store.errorMessage == nil, "withdrawal keeps the existing collection-unavailable presentation") }
        await finish(transport)
    }
    @MainActor static func newerOperationDeniesPendingTap(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport), sink = SelectionSink()
        try await display(store, transport, f)
        let selection = tap(store, sink); let tapRequest = await transport.next()
        let newer = Task { await store.refresh() }; let newerRequest = await transport.next()
        await transport.resolve(newerRequest, membership: try f.membership(revision: 13)); await newer.value
        await transport.resolve(tapRequest, membership: try f.membership(revision: 12, removing: 801))
        let selected = await selection.value
        check(!selected && store.membership?.revision == 13, "superseded tap cannot borrow newer validation")
        check(store.errorMessage == nil, "late missing-member response cannot add a stale removal notice")
        unchanged(sink); await finish(transport)
    }
    @MainActor static func validSelectsOnce(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport), sink = SelectionSink()
        try await display(store, transport, f)
        // Unknown ID must neither request nor select.
        let unknown = await store.selectGame(9201, isActive: { true }, select: { sink.accept($0) })
        check(!unknown, "market identity cannot select a game")
        let selection = tap(store, sink); let request = await transport.next()
        // A duplicate tap while validation is in flight cannot initiate a second request.
        let duplicate = await store.selectGame(801, isActive: { true }, select: { sink.accept($0) })
        check(!duplicate, "in-flight duplicate denied")
        await transport.resolve(request, membership: try f.membership(revision: 12))
        let selected = await selection.value
        let count = await transport.count()
        check(selected && sink.calls == [801] && sink.priorOrSelectedID == 801, "one exact validated selection effect")
        check(count == 2, "one initial display and exactly one fresh tap request")
        await finish(transport)
    }
    @MainActor static func inactiveBeforeTap(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport), sink = SelectionSink()
        try await display(store, transport, f)
        sink.active = false
        let selected = await store.selectGame(801, isActive: { sink.active }, select: { sink.accept($0) })
        let count = await transport.count()
        check(!selected && count == 1, "inactive tap cannot request or select")
        unchanged(sink); await finish(transport)
    }
    @MainActor static func removedGameRecovers(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport), sink = SelectionSink()
        try await display(store, transport, f)
        let selection = tap(store, sink); let missing = await transport.next()
        await transport.resolve(missing, membership: try f.membership(revision: 12, removing: 801))
        let refused = await selection.value
        check(!refused && store.errorMessage != nil, "current removal is explained")
        unchanged(sink)
        let refresh = Task { await store.refresh() }; let retry = await transport.next()
        check(store.errorMessage == nil && store.isLoading, "explicit refresh clears old removal notice")
        await transport.resolve(retry, membership: try f.membership(revision: 13)); await refresh.value
        let next = tap(store, sink); let validation = await transport.next()
        await transport.resolve(validation, membership: try f.membership(revision: 14))
        let accepted = await next.value
        check(accepted && sink.calls == [801] && store.errorMessage == nil, "returned game needs fresh validation and selects once")
        let count = await transport.count()
        check(count == 4, "display, denied tap, explicit refresh and valid tap only; no automatic retry")
        await finish(transport)
    }
    @MainActor static func questionNavigation(_ f: Fixtures, mode: String) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport)
        try await display(store, transport, f, revision: mode == "rollback" ? 12 : 11)
        var opened: [WatchMLBQuestion] = []
        var active = true
        let wrongType = await store.openQuestion(801, isActive: { true }, open: { opened.append($0) })
        let inactive = await store.openQuestion(9201, isActive: { false }, open: { opened.append($0) })
        check(!wrongType && !inactive, "game identity and inactive surface cannot open a question")
        let navigation = Task { await store.openQuestion(9201, isActive: { active }, open: { opened.append($0) }) }
        let request = await transport.next()
        let duplicate = await store.openQuestion(9201, isActive: { true }, open: { opened.append($0) })
        check(!duplicate && store.membership == nil, "in-flight validation removes stale destinations and coalesces taps")
        switch mode {
        case "cancel-task": navigation.cancel()
        case "cancel-surface": store.cancel()
        case "inactive": active = false
        default: break
        }
        if mode == "failure" { await transport.fail(request) }
        else {
            await transport.resolve(request, membership: try f.membership(
                revision: mode == "rollback" ? 11 : 12,
                published: mode != "withdrawal", removingQuestion: mode == "removed" ? 9201 : nil))
        }
        let accepted = await navigation.value
        check(accepted == (mode == "valid"), "question navigation follows fresh membership and lifecycle checks")
        check(opened.map(\.id) == (mode == "valid" ? [9201] : []), "one exact question opens only after successful validation")
        if mode == "valid" { check(opened[0].name == "Padres at Dodgers: winner", "fresh full title passed to reader") }
        if mode == "removed" {
            check(store.errorMessage == "Padres at Dodgers: winner is no longer available in this collection. Choose another question or refresh.",
                  "removed question retains its heading in a useful recovery message")
            check(store.membership?.questions.map(\.id) == [9202], "healthy sibling survives removal")
            let refresh = Task { await store.refresh() }; let recovery = await transport.next()
            await transport.resolve(recovery, membership: try f.membership(revision: 13)); await refresh.value
            let retry = Task { await store.openQuestion(9201, isActive: { true }, open: { opened.append($0) }) }
            let validation = await transport.next()
            await transport.resolve(validation, membership: try f.membership(revision: 14))
            let recovered = await retry.value
            check(recovered && opened.map(\.id) == [9201] && store.errorMessage == nil,
                  "returned question requires a fresh tap validation and opens once")
        }
        let count = await transport.count()
        check(count == (mode == "removed" ? 4 : 2), "no request for unknown, inactive or duplicate tap")
        await finish(transport)
    }
    @MainActor static func supersededQuestionDoesNotOpen(_ f: Fixtures) async throws {
        let transport = SuspendedTransport(), store = makeStore(transport)
        try await display(store, transport, f)
        var opened: [Int] = []
        let navigation = Task { await store.openQuestion(9201, isActive: { true }, open: { opened.append($0.id) }) }
        let old = await transport.next()
        let refresh = Task { await store.refresh() }; let current = await transport.next()
        await transport.resolve(current, membership: try f.membership(revision: 13)); await refresh.value
        await transport.resolve(old, membership: try f.membership(revision: 12, removingQuestion: 9201))
        let accepted = await navigation.value
        check(!accepted && opened.isEmpty && store.membership?.revision == 13 && store.errorMessage == nil,
              "superseded question tap cannot navigate or add a stale removal error")
        await finish(transport)
    }
    @MainActor static func main() async throws {
        let directory = URL(fileURLWithPath: CommandLine.arguments[1])
        try DecoderChecks.run(directory)
        let f = try Fixtures(directory: directory)
        try await olderRefreshLoses(f)
        try await browseSupersedesCollection(f)
        for mode in ["cancel-task", "cancel-surface", "inactive", "withdrawal", "removed-member", "rollback", "failure"] {
            try await denied(f, mode: mode)
        }
        try await newerOperationDeniesPendingTap(f)
        try await validSelectsOnce(f)
        try await inactiveBeforeTap(f)
        try await removedGameRecovers(f)
        for mode in ["valid", "failure", "withdrawal", "removed", "rollback", "cancel-task", "cancel-surface", "inactive"] {
            try await questionNavigation(f, mode: mode)
        }
        try await supersededQuestionDoesNotOpen(f)
        print("MLB decoder, original game controls and added question navigation controls PASS")
    }
}
