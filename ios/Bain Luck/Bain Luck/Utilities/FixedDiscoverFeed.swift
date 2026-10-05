#if DEBUG
import CryptoKit
import Foundation

/// A Discover feed served from ONE fixed file in the app's own container, for
/// the #9648 controlled acceptance (two unrelated sports swipes keep the other
/// sports stories, through a cold relaunch).
///
/// 🔴 WHY THIS EXISTS. The journey `UnrelatedMLBSwipesKeepTheRedSoxStory9648Tests`
/// ran on a signed-in simulator on Oct 1 and SKIPPED: the live feed held no Red
/// Sox card and too few MLB games, so the treatment never happened. Live supply
/// is seasonal; a test that waits for it is a calendar, not a gate. This serves
/// the reviewed 36-card deck (`fixed-feed.json`, pinned by SHA-256) through the
/// SAME `DiscoverViewModel` load/publication path, so everything downstream —
/// real sign-in, swipe, `recordInteraction`, the profile and dismiss stores,
/// `personalize`, the SwiftUI cards — is the production code.
///
/// What it deliberately does NOT do:
///  * **No fallback.** Flag present + file missing or malformed is a named
///    harness failure on every fetch. A silent fallback to the network or the
///    disk cache would hand the journey live supply and report it as the fixture.
///  * **No prices.** It does not conform to `DiscoverPriceCardsProviding`, so the
///    view model's `priceClient` is nil and its existing guards start no REST
///    price poll and no socket.
///  * **No last-good by default.** The caller passes `lastGood: nil`, so the
///    September 23 disk deck (#10094) never seeds, and nothing here writes
///    `DiscoverFeedCache`. The one exception is #10399's restored-deck runtime
///    (`FixedDiscoverRestoredDeck`, armed by its own flag): it serves a FIXTURE
///    seed through the same injection and still never touches the real cache.
///  * **Not a principal-free fake.** The protocol's DEFAULT principal methods
///    report an empty identity and publish always. This forwards the real
///    `APIClient` identity and binds each offset-0 page to the principal and
///    credential that were current when it was "fetched", so the publication
///    gate refuses a mismatch exactly as it does for `/api/feed`.
///
/// DEBUG-only at the implementation AND at its one call site
/// (`DiscoverView.makeViewModel`): a Release/TestFlight binary does not contain
/// it, so no reader can reach it by passing the argument.
nonisolated struct FixedDiscoverFeed: DiscoverFeedProviding {

    /// Why a fixed-feed launch cannot serve. Every fetch throws this, so the
    /// screen shows Discover's ordinary error state and the receipt names it.
    nonisolated enum HarnessFailure: Error, Equatable, Sendable, CustomStringConvertible {
        case missing(path: String)
        case malformed(path: String, reason: String)
        /// #10399: the held first response was never released inside its bound.
        case latchTimedOut(seconds: TimeInterval)

        var description: String {
            switch self {
            case .missing(let path): return "fixture missing at \(path)"
            case .malformed(let path, let reason): return "fixture malformed at \(path): \(reason)"
            case .latchTimedOut(let seconds): return "held first response not released within \(Int(seconds)) s"
            }
        }
    }

    /// The principal a page is bound to, read at dispatch.
    nonisolated struct Principal: Sendable, Equatable {
        let identity: String
        let expectedSignedIn: Bool
        let authenticated: Bool
    }

    /// The fixture as loaded: exact bytes plus what the receipt reports.
    nonisolated struct Fixture: Sendable {
        let bytes: Data
        let sha256: String
        let cards: Int
        /// Stable for the life of the file: the reconcile path (#4110) then sees
        /// one ordered list across load, refresh and pagination.
        var edition: String { "fixture-" + sha256.prefix(16) }
    }

    let path: String
    let fixture: Result<Fixture, HarnessFailure>
    /// #10399's restored-deck runtime, or `nil` (the #9648 default: no last-good,
    /// no latch). Present only when `-launch_fixed_feed_restored_seed` was passed.
    let restored: FixedDiscoverRestoredDeck?
    private let principal: @Sendable () async -> Principal
    private let identityNow: @Sendable () async -> String
    private let seedContext: @Sendable () async -> DiscoverOptimisticSeedContext

    init(
        path: String,
        bytes: Data?,
        restored: FixedDiscoverRestoredDeck? = nil,
        principal: @escaping @Sendable () async -> Principal = { await APIClient.shared.fixedFeedPrincipal() },
        identityNow: @escaping @Sendable () async -> String = { await APIClient.shared.resolvedFeedIdentity() },
        seedContext: @escaping @Sendable () async -> DiscoverOptimisticSeedContext = {
            await APIClient.shared.resolvedOptimisticSeedContext()
        }
    ) {
        self.path = path
        self.fixture = Self.validate(bytes, path: path)
        self.restored = restored
        self.principal = principal
        self.identityNow = identityNow
        self.seedContext = seedContext
    }

    // MARK: - DiscoverFeedProviding

    nonisolated func fetchDiscoverFeed(
        limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        // #10399: under the restored-deck runtime every offset-0 page is counted
        // and the first is held, whichever entry point asked. Default: unchanged.
        if offset == 0, restored != nil {
            return try await fetchDiscoverFeedResolvingPrincipal(
                limit: limit, offset: offset, eventPct: eventPct, cacheTTL: cacheTTL).response
        }
        try restored?.refuseIfMalformed()
        return try page(limit: limit, offset: offset)
    }

    /// Mirrors `APIClient.fetchFeedPersistingLastGood`: offset 0 carries the real
    /// dispatch principal; pagination pages are transient and report the neutral
    /// pair under the current identity.
    nonisolated func fetchDiscoverFeedResolvingPrincipal(
        limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
    ) async throws -> DiscoverFeedFetchResult {
        guard offset == 0 else {
            try restored?.refuseIfMalformed()
            let response = try page(limit: limit, offset: offset)
            return DiscoverFeedFetchResult(
                response: response, identityAtFetch: await identityNow(),
                wasAuthenticated: false, expectedSignedIn: false)
        }
        let atFetch = await principal()
        // #10399: the principal is bound at dispatch, BEFORE the hold, exactly as
        // a real request binds it when it leaves the client.
        try await restored?.holdInitialResponse()
        let response = try page(limit: limit, offset: offset)
        return DiscoverFeedFetchResult(
            response: response, identityAtFetch: atFetch.identity,
            wasAuthenticated: atFetch.authenticated, expectedSignedIn: atFetch.expectedSignedIn)
    }

    nonisolated func currentFeedPrincipal() async -> String { await identityNow() }

    nonisolated func optimisticSeedContext() async -> DiscoverOptimisticSeedContext { await seedContext() }

    // MARK: - Paging

    /// One deterministic `limit`/`offset` window of the fixture, with a truthful
    /// `total` and `has_more`. Items are sliced from the parsed file and decoded
    /// by the app's own `FeedResponse` decoder, never re-modelled here.
    nonisolated func page(limit: Int, offset: Int) throws -> FeedResponse {
        let fixture = try fixture.get()
        guard
            let body = try? JSONSerialization.jsonObject(with: fixture.bytes) as? [String: Any],
            let items = body["items"] as? [Any]
        else { throw HarnessFailure.malformed(path: path, reason: "body is not an object with items") }
        let start = min(max(0, offset), items.count)
        let end = min(items.count, start + max(0, limit))
        var window: [String: Any] = [
            "items": Array(items[start..<end]),
            "total": items.count,
            "limit": limit,
            "offset": start,
            "has_more": end < items.count,
            "edition": fixture.edition,
        ]
        if let cache = body["cache"] { window["cache"] = cache }
        let data = try JSONSerialization.data(withJSONObject: window)
        return try Self.decoder.decode(FeedResponse.self, from: data)
    }

    nonisolated(unsafe) private static let decoder: JSONDecoder = {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }()

    /// The whole file must parse, carry `total == items.count`, and decode as a
    /// `FeedResponse` with every item kept, before any page is served.
    static func validate(_ bytes: Data?, path: String) -> Result<Fixture, HarnessFailure> {
        guard let bytes else { return .failure(.missing(path: path)) }
        guard
            let body = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
            let items = body["items"] as? [Any]
        else { return .failure(.malformed(path: path, reason: "body is not an object with items")) }
        guard !items.isEmpty else { return .failure(.malformed(path: path, reason: "no items")) }
        if let total = body["total"] as? Int, total != items.count {
            return .failure(.malformed(path: path, reason: "total \(total) != \(items.count) items"))
        }
        let decoded: FeedResponse
        do { decoded = try decoder.decode(FeedResponse.self, from: bytes) } catch {
            return .failure(.malformed(path: path, reason: "FeedResponse decode: \(error)"))
        }
        guard decoded.items.count == items.count else {
            return .failure(.malformed(
                path: path, reason: "decoded \(decoded.items.count) of \(items.count) items"))
        }
        let sha = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        return .success(Fixture(bytes: bytes, sha256: sha, cards: items.count))
    }

    // MARK: - Launch

    /// The client for this launch, or `nil` when `-launch_fixed_feed` was not
    /// passed (the ordinary production client then runs). Seeds the profile and
    /// dismiss stores first when `-launch_fixed_feed_seed` asks — once per
    /// process, before Discover's first store read.
    @MainActor
    static func launchClient(
        defaults: UserDefaults = .standard,
        home: URL = URL(fileURLWithPath: NSHomeDirectory())
    ) -> FixedDiscoverFeed? {
        guard let url = LaunchRig.fixedFeedURL(defaults: defaults, home: home) else { return nil }
        let bytes = try? Data(contentsOf: url)
        let restored = FixedDiscoverRestoredDeck.launch(
            defaults: defaults, home: home, fresh: validate(bytes, path: url.path))
        FixedDiscoverRestoredDeck.active = restored
        let client = FixedDiscoverFeed(path: url.path, bytes: bytes, restored: restored)
        let seed = FixedDiscoverFeedSeed.applyIfRequested(defaults: defaults, home: home)
        FixedDiscoverFeedReceipt.launch = .init(
            fixture: client.fixture, path: url.path, seed: seed, launchedAt: Date())
        return client
    }
}

// MARK: - Seeding the isolated initial state

/// Materializes the reviewed initial profile/dismiss state ONCE, against one
/// recorded run anchor, before Discover loads either store.
///
/// The seed file's timestamps are relative to its own `clock`; each lands at
/// `anchor + (t - clock)`, so the profile's decay and the dismiss store's TTL
/// both run on the app's real clock at the same relative ages the reviewer
/// pinned. Ambient `Date()` is NOT frozen. A launch without
/// `-launch_fixed_feed_seed` (the cold relaunch) writes nothing.
enum FixedDiscoverFeedSeed {
    static let profileKey = DiscoverInteractionProfile.storageKey
    static let legacyProfileKey = DiscoverInteractionProfile.legacyStorageKey
    static let dismissKey = "discover_dismissed_v2"
    static let legacyDismissKey = "discover_dismissed"

    nonisolated struct Outcome: Sendable, Equatable {
        nonisolated enum State: Sendable, Equatable { case notRequested, seeded, failed(String) }
        let state: State
        let anchor: TimeInterval?
        let seedSHA256: String?
    }

    private static let lock = NSLock()
    nonisolated(unsafe) private static var applied: Outcome?

    static func applyIfRequested(defaults: UserDefaults, home: URL) -> Outcome {
        lock.withLock {
            if let applied { return applied }
            let outcome = apply(defaults: defaults, home: home)
            applied = outcome
            return outcome
        }
    }

    /// Test seam: forget the once-per-process latch.
    static func resetLatchForTesting() { lock.withLock { applied = nil } }

    static func apply(defaults: UserDefaults, home: URL, store: UserDefaults? = nil) -> Outcome {
        let store = store ?? defaults
        guard let url = LaunchRig.fixedFeedSeedURL(defaults: defaults, home: home) else {
            return Outcome(state: .notRequested, anchor: nil, seedSHA256: nil)
        }
        guard let anchor = LaunchRig.fixedFeedAnchor(defaults: defaults) else {
            return Outcome(state: .failed("seed requested without -\(LaunchRig.fixedFeedAnchorKey)"), anchor: nil, seedSHA256: nil)
        }
        guard let bytes = try? Data(contentsOf: url) else {
            return Outcome(state: .failed("seed missing at \(url.path)"), anchor: anchor, seedSHA256: nil)
        }
        let sha = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        guard
            let body = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
            let clockText = body["clock"] as? String,
            let clock = ISO8601DateFormatter().date(from: clockText)?.timeIntervalSince1970,
            let values = body["defaults"] as? [String: Any],
            let profile = values[profileKey] as? [String: [String: Double]],
            let dismissed = values[dismissKey] as? [String: Double]
        else {
            return Outcome(state: .failed("seed malformed at \(url.path)"), anchor: anchor, seedSHA256: sha)
        }
        let shift = anchor - clock
        let materializedProfile = profile.mapValues { entry -> [String: Double] in
            var e = entry
            if let at = e["at"] { e["at"] = at + shift }
            return e
        }
        store.set(materializedProfile, forKey: profileKey)
        store.set(dismissed.mapValues { $0 + shift }, forKey: dismissKey)
        // The reviewed seed nulls both legacy stores: a leftover v1 profile or
        // timestamp-less dismiss list would migrate on load and change the state.
        for key in [legacyProfileKey, legacyDismissKey] where values[key] == nil || values[key] is NSNull {
            store.removeObject(forKey: key)
        }
        return Outcome(state: .seeded, anchor: anchor, seedSHA256: sha)
    }
}

// MARK: - Read-only receipt

/// What the fixed-feed launch was given and what the four local stores hold,
/// as one JSON document the journey reads off the screen. Read-only: it never
/// writes a store, and it carries no credential — the principal is reported as
/// booleans only.
enum FixedDiscoverFeedReceipt {
    nonisolated struct Launch: Sendable {
        let fixture: Result<FixedDiscoverFeed.Fixture, FixedDiscoverFeed.HarnessFailure>
        let path: String
        let seed: FixedDiscoverFeedSeed.Outcome
        let launchedAt: Date
    }

    nonisolated(unsafe) static var launch: Launch?

    nonisolated struct RenderedCard {
        let id: String
        let category: String
        let score: Int
        let adjustment: Double
    }

    /// Canonical (sorted-key) JSON of one store, `null` when absent.
    static func canonical(_ value: Any?) -> String {
        guard let value, JSONSerialization.isValidJSONObject(["v": value]),
              let data = try? JSONSerialization.data(withJSONObject: ["v": value], options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else { return "null" }
        // Strip the {"v":…} wrapper that lets scalars and arrays serialize too.
        return String(text.dropFirst(5).dropLast())
    }

    static func json(
        launch: Launch?,
        signedIn: Bool,
        served: Int,
        eligible: Int,
        rendered: [RenderedCard],
        defaults: UserDefaults = .standard,
        now: Date = Date(),
        restored: FixedDiscoverRestoredDeck? = FixedDiscoverRestoredDeck.active
    ) -> String {
        var fixture: [String: Any] = [:]
        if let launch {
            fixture["path"] = launch.path
            switch launch.fixture {
            case .success(let f):
                fixture["sha256"] = f.sha256
                fixture["cards"] = f.cards
                fixture["edition"] = f.edition
            case .failure(let failure):
                fixture["failure"] = failure.description
            }
        }
        var seed: [String: Any] = [:]
        switch launch?.seed.state {
        case .seeded?: seed["state"] = "seeded"
        case .failed(let why)?: seed["state"] = "failed"; seed["failure"] = why
        case .notRequested?, nil: seed["state"] = "not_requested"
        }
        if let anchor = launch?.seed.anchor { seed["anchor"] = anchor }
        if let sha = launch?.seed.seedSHA256 { seed["sha256"] = sha }

        let keys = [
            FixedDiscoverFeedSeed.profileKey, FixedDiscoverFeedSeed.legacyProfileKey,
            FixedDiscoverFeedSeed.dismissKey, FixedDiscoverFeedSeed.legacyDismissKey,
        ]
        var stores: [String: String] = [:]
        var storeHashes: [String: String] = [:]
        for key in keys {
            let text = canonical(defaults.object(forKey: key))
            stores[key] = text
            storeHashes[key] = SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        let body: [String: Any] = [
            "label": "CONTROLLED fixed-feed DEBUG launch; not network inventory",
            "fixture": fixture,
            "seed": seed,
            "launched_at": launch?.launchedAt.timeIntervalSince1970 ?? 0,
            "wall_clock": now.timeIntervalSince1970,
            "signed_in": signedIn,
            "served": served,
            "eligible": eligible,
            "drawn": rendered.count,
            "rendered": rendered.map {
                ["id": $0.id, "category": $0.category, "score": $0.score, "adjustment": $0.adjustment] as [String: Any]
            },
            "stores": stores,
            "store_sha256": storeHashes,
            "restored_deck": restored?.snapshot() ?? NSNull(),
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else { return "{}" }
        return text
    }
}

// MARK: - #10399 restored-deck runtime

/// The controlled runtime for #10399: a reader whose Discover first paints an
/// OLD restored deck, leaves the tab while the first response is still in
/// flight, and comes back. The fresh response must replace the old deck even
/// though SwiftUI cancelled the appearance task that started the load.
///
/// 🔴 WHY THE #9648 CLIENT ALONE COULD NOT EXERCISE IT. That client answers its
/// first page immediately and its factory passes `lastGood: nil`, so the old
/// deck never painted and nothing was ever in flight when the reader left: the
/// October 3 simulator check saw the fresh feed before its first frame (4.7 s)
/// and was rightly called inconclusive. This adds the two missing inputs and
/// nothing else:
///
///  * **An aged, principal-bound seed** served through the view model's EXISTING
///    `DiscoverLastGoodReading` injection. It is a fixture file in the app's own
///    container; the real `DiscoverFeedCache` is never read or written.
///  * **A held first response.** The first offset-0 fetch waits on a latch the
///    journey releases explicitly (`discover-restored-deck-release`). The latch
///    is cancellation-COOPERATIVE: if the task awaiting it is cancelled, the
///    fetch throws `CancellationError` at once — so the pre-#10399 appearance
///    path (which let cancellation reach the fetch) still loses its response
///    here, and cannot pass by courtesy of an inert fake. It is also finite:
///    unreleased after ``latchBound`` it fails by name, never succeeds.
///
/// What it records is an ordered event log (seed served/painted, fetch held,
/// the mounted appearance task's own cancellation, release, return, publish),
/// read by the journey from the fixed-feed receipt. Nothing here decides an
/// outcome; the production view model does.
///
/// DEBUG-only, armed only by `-launch_fixed_feed_restored_seed` alongside
/// `-launch_fixed_feed`. Absent from Release binaries.
nonisolated final class FixedDiscoverRestoredDeck: @unchecked Sendable {

    /// Which appearance path the mounted Discover task runs.
    nonisolated enum Arm: String, Sendable {
        /// Today's `DiscoverView.loadForInitialAppearance` (the #10399 fix).
        case current = "current_appearance_load"
        /// The NEGATIVE comparison: the appearance task awaits `load()` directly,
        /// as before #10399, so its cancellation reaches the fetch.
        case oldDirectLoad = "old_direct_load"
    }

    /// Which namespace the restored deck was stored under.
    nonisolated enum PrincipalKind: String, Sendable {
        case anonymous
        case signedIn = "signed_in"

        /// A seed is served only to the namespace it was stored under — the
        /// real cache's identity partition, restated for a fixture.
        func admits(identity: String) -> Bool {
            switch self {
            case .anonymous: return identity.hasPrefix("anon:")
            case .signedIn: return identity.hasPrefix("user:")
            }
        }
    }

    nonisolated struct Seed: Sendable {
        let sha256: String
        let ageSeconds: TimeInterval
        let principal: PrincipalKind
        let response: FeedResponse
        let ids: [String]
    }

    nonisolated struct Event: Sendable {
        let seq: Int
        let name: String
        let detail: String
        let uptime: TimeInterval
    }

    /// How long the held first response may wait for its release.
    ///
    /// Longer than the view model's own seeded budget (20 s) on purpose: inside
    /// a run the PRODUCTION deadline is what ends an unreleased hold, and the log
    /// then shows the fetch cancelled at ~20 s rather than this bound firing.
    static let latchBound: TimeInterval = 45

    /// The runtime this launch armed, for the view's DEBUG hooks and receipt.
    nonisolated(unsafe) static var active: FixedDiscoverRestoredDeck?

    let path: String
    let seed: Result<Seed, FixedDiscoverFeed.HarnessFailure>
    let arm: Result<Arm, FixedDiscoverFeed.HarnessFailure>
    let bound: TimeInterval
    private let identityNow: @Sendable () async -> String

    private let lock = NSLock()
    private var events: [Event] = []
    private var initialFetches = 0
    private var latchState = "armed"
    private var latchTerminal: Result<Void, Error>?
    private var latchContinuation: CheckedContinuation<Void, Error>?

    init(
        path: String,
        seed: Result<Seed, FixedDiscoverFeed.HarnessFailure>,
        arm: Result<Arm, FixedDiscoverFeed.HarnessFailure>,
        bound: TimeInterval = FixedDiscoverRestoredDeck.latchBound,
        identityNow: @escaping @Sendable () async -> String = { await APIClient.shared.resolvedFeedIdentity() }
    ) {
        self.path = path
        self.seed = seed
        self.arm = arm
        self.bound = bound
        self.identityNow = identityNow
    }

    // MARK: Launch

    /// The runtime for this launch, or `nil` when the seed flag was not passed.
    @MainActor
    static func launch(
        defaults: UserDefaults,
        home: URL,
        fresh: Result<FixedDiscoverFeed.Fixture, FixedDiscoverFeed.HarnessFailure>
    ) -> FixedDiscoverRestoredDeck? {
        guard let url = LaunchRig.fixedFeedRestoredSeedURL(defaults: defaults, home: home) else { return nil }
        let arm: Result<Arm, FixedDiscoverFeed.HarnessFailure>
        switch LaunchRig.fixedFeedAppearanceControl(defaults: defaults) {
        case nil: arm = .success(.current)
        case let word?:
            arm = Arm(rawValue: word).map { .success($0) }
                ?? .failure(.malformed(path: url.path, reason: "unknown appearance control '\(word)'"))
        }
        let freshIds = (try? fresh.get()).map { ids(in: $0.bytes) } ?? []
        return FixedDiscoverRestoredDeck(
            path: url.path,
            seed: validateSeed(try? Data(contentsOf: url), path: url.path, freshIds: freshIds),
            arm: arm)
    }

    /// `type-id` of every item, in order — the same id the receipt renders.
    static func ids(in bytes: Data) -> [String] {
        guard let body = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any],
              let items = body["items"] as? [[String: Any]]
        else { return [] }
        return items.compactMap { item in
            guard let type = item["type"] as? String,
                  let data = item["data"] as? [String: Any], let id = data["id"]
            else { return nil }
            return "\(type)-\(id)"
        }
    }

    /// `{"age_seconds": >0, "principal": "anonymous"|"signed_in", "response": <feed>}`,
    /// every item decoded, and no item shared with the fresh deck — an overlap
    /// would let the old deck "pass" as the fresh one on screen.
    static func validateSeed(
        _ bytes: Data?, path: String, freshIds: [String]
    ) -> Result<Seed, FixedDiscoverFeed.HarnessFailure> {
        guard let bytes else { return .failure(.missing(path: path)) }
        func malformed(_ reason: String) -> Result<Seed, FixedDiscoverFeed.HarnessFailure> {
            .failure(.malformed(path: path, reason: reason))
        }
        guard let body = try? JSONSerialization.jsonObject(with: bytes) as? [String: Any] else {
            return malformed("seed is not an object")
        }
        guard let age = (body["age_seconds"] as? NSNumber)?.doubleValue, age.isFinite, age > 0 else {
            return malformed("age_seconds must be a positive number")
        }
        guard let word = body["principal"] as? String, let principal = PrincipalKind(rawValue: word) else {
            return malformed("principal must be anonymous or signed_in")
        }
        guard let raw = body["response"] as? [String: Any],
              let items = raw["items"] as? [Any], !items.isEmpty,
              let responseBytes = try? JSONSerialization.data(withJSONObject: raw)
        else { return malformed("response is not a feed with items") }
        let response: FeedResponse
        do {
            let decoder = JSONDecoder()
            decoder.keyDecodingStrategy = .convertFromSnakeCase
            response = try decoder.decode(FeedResponse.self, from: responseBytes)
        } catch { return malformed("response FeedResponse decode: \(error)") }
        guard response.items.count == items.count else {
            return malformed("response decoded \(response.items.count) of \(items.count) items")
        }
        let seedIds = ids(in: responseBytes)
        let shared = Set(seedIds).intersection(freshIds)
        guard shared.isEmpty else { return malformed("seed shares \(shared.count) ids with the fresh deck") }
        let sha = SHA256.hash(data: bytes).map { String(format: "%02x", $0) }.joined()
        return .success(Seed(sha256: sha, ageSeconds: age, principal: principal, response: response, ids: seedIds))
    }

    // MARK: The client side

    /// A seed or arm failure is a named harness failure on EVERY fetch, like a
    /// malformed fixed feed — never a silent run without the treatment.
    func refuseIfMalformed() throws {
        if case .failure(let failure) = seed { throw failure }
        if case .failure(let failure) = arm { throw failure }
    }

    /// Counts every offset-0 fetch and holds ONLY the first on the latch.
    func holdInitialResponse() async throws {
        try refuseIfMalformed()
        let number = lock.withLock { () -> Int in initialFetches += 1; return initialFetches }
        record("fetch_started", "n=\(number)")
        guard number == 1 else { return }
        do {
            try await waitForRelease()
            record("fetch_returned", "n=1")
        } catch is CancellationError {
            record("fetch_cancelled", "n=1")
            throw CancellationError()
        } catch {
            record("fetch_failed", "n=1 \(error)")
            throw error
        }
    }

    /// Waits for ``release()``, throwing at once when the waiting task is
    /// cancelled and by name after ``bound``. Structured: both arms are child
    /// tasks of the caller, nothing is detached, and cancellation is not caught.
    func waitForRelease() async throws {
        let bound = self.bound
        try await withThrowingTaskGroup(of: Bool.self) { group in
            group.addTask {
                try await withTaskCancellationHandler {
                    try await withCheckedThrowingContinuation { (pending: CheckedContinuation<Void, Error>) in
                        let ready = self.lock.withLock { () -> Result<Void, Error>? in
                            if let terminal = self.latchTerminal { return terminal }
                            self.latchContinuation = pending
                            self.latchState = "waiting"
                            return nil
                        }
                        if let ready { pending.resume(with: ready) } else { self.record("fetch_waiting_on_latch", "n=1") }
                    }
                } onCancel: {
                    self.finish(.failure(CancellationError()), state: "cancelled")
                }
                return true
            }
            group.addTask {
                do { try await Task.sleep(nanoseconds: UInt64(bound * 1_000_000_000)) } catch { return false }
                self.finish(.failure(FixedDiscoverFeed.HarnessFailure.latchTimedOut(seconds: bound)), state: "timed_out")
                return false
            }
            while let released = try await group.next() {
                if released { group.cancelAll() }
            }
        }
    }

    /// Releases the held first response. Idempotent; a release after the hold
    /// was cancelled or timed out changes nothing (and the log says so).
    func release() {
        record("latch_release_requested", "state=\(lock.withLock { latchState })")
        finish(.success(()), state: "released")
    }

    private func finish(_ result: Result<Void, Error>, state: String) {
        let pending = lock.withLock { () -> CheckedContinuation<Void, Error>? in
            guard latchTerminal == nil else { return nil }
            latchTerminal = result
            latchState = state
            let pending = latchContinuation
            latchContinuation = nil
            return pending
        }
        pending?.resume(with: result)
    }

    // MARK: The last-good side

    /// The `DiscoverLastGoodReading` the factory injects: the fixture seed,
    /// stored `ageSeconds` ago, offered only to its own namespace.
    var lastGood: DiscoverLastGoodReading { Reader(owner: self) }

    nonisolated struct Reader: DiscoverLastGoodReading {
        let owner: FixedDiscoverRestoredDeck
        func loadLastGoodFeed() async -> CachedDiscoverFeed? { await owner.serveSeed() }
    }

    func serveSeed() async -> CachedDiscoverFeed? {
        guard case .success(let seed) = seed else {
            record("seed_refused", "invalid seed")
            return nil
        }
        let identity = await identityNow()
        guard seed.principal.admits(identity: identity) else {
            record("seed_refused", "principal \(seed.principal.rawValue) does not admit \(identity.prefix(5))")
            return nil
        }
        record("seed_served", "cards=\(seed.ids.count) age_s=\(Int(seed.ageSeconds)) principal=\(seed.principal.rawValue)")
        return CachedDiscoverFeed(
            response: seed.response, storedAt: Date().addingTimeInterval(-seed.ageSeconds),
            ttlSeconds: nil, identity: identity)
    }

    // MARK: The log

    func record(_ name: String, _ detail: String = "") {
        let now = ProcessInfo.processInfo.systemUptime
        lock.withLock { events.append(Event(seq: events.count + 1, name: name, detail: detail, uptime: now)) }
    }

    var orderedEvents: [Event] { lock.withLock { events } }
    var initialFetchCount: Int { lock.withLock { initialFetches } }

    /// The receipt section: identity, inputs and the ordered log.
    func snapshot() -> [String: Any] {
        let (log, fetches, state) = lock.withLock { (events, initialFetches, latchState) }
        var seedBody: [String: Any] = ["path": path]
        switch seed {
        case .success(let s):
            seedBody["sha256"] = s.sha256
            seedBody["age_seconds"] = s.ageSeconds
            seedBody["principal"] = s.principal.rawValue
            seedBody["ids"] = s.ids
        case .failure(let failure):
            seedBody["failure"] = failure.description
        }
        var body: [String: Any] = [
            "label": "CONTROLLED restored-deck DEBUG runtime (#10399); fixture seed, not the real cache",
            "seed": seedBody,
            "latch": ["state": state, "bound_seconds": bound],
            "initial_fetches": fetches,
            "events": log.map { ["seq": $0.seq, "name": $0.name, "detail": $0.detail, "uptime": $0.uptime] as [String: Any] },
        ]
        switch arm {
        case .success(let a): body["arm"] = a.rawValue
        case .failure(let failure): body["arm_failure"] = failure.description
        }
        return body
    }
}

// MARK: - Principal context without a request

extension APIClient {
    /// The principal `fetchFeedPersistingLastGood` would bind an offset-0 page
    /// to, read WITHOUT sending `/api/feed` or touching the feed cache: the
    /// identity first, then whether a token would be attached — the same order
    /// the real request takes. Returns booleans and the opaque namespace only;
    /// the token itself never leaves this method.
    func fixedFeedPrincipal() async -> FixedDiscoverFeed.Principal {
        let identity = resolvedFeedIdentity()
        let expectedSignedIn = resolvedOptimisticSeedContext().signedInNamespace
        var authenticated = false
        if let provider = authTokenProvider { authenticated = await provider() != nil }
        return FixedDiscoverFeed.Principal(
            identity: identity, expectedSignedIn: expectedSignedIn, authenticated: authenticated)
    }
}
#endif
