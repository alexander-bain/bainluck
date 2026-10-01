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
///  * **No last-good.** The caller passes `lastGood: nil`, so the September 23
///    disk deck (#10094) never seeds, and nothing here writes `DiscoverFeedCache`.
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

        var description: String {
            switch self {
            case .missing(let path): return "fixture missing at \(path)"
            case .malformed(let path, let reason): return "fixture malformed at \(path): \(reason)"
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
    private let principal: @Sendable () async -> Principal
    private let identityNow: @Sendable () async -> String
    private let seedContext: @Sendable () async -> DiscoverOptimisticSeedContext

    init(
        path: String,
        bytes: Data?,
        principal: @escaping @Sendable () async -> Principal = { await APIClient.shared.fixedFeedPrincipal() },
        identityNow: @escaping @Sendable () async -> String = { await APIClient.shared.resolvedFeedIdentity() },
        seedContext: @escaping @Sendable () async -> DiscoverOptimisticSeedContext = {
            await APIClient.shared.resolvedOptimisticSeedContext()
        }
    ) {
        self.path = path
        self.fixture = Self.validate(bytes, path: path)
        self.principal = principal
        self.identityNow = identityNow
        self.seedContext = seedContext
    }

    // MARK: - DiscoverFeedProviding

    nonisolated func fetchDiscoverFeed(
        limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
    ) async throws -> FeedResponse {
        try page(limit: limit, offset: offset)
    }

    /// Mirrors `APIClient.fetchFeedPersistingLastGood`: offset 0 carries the real
    /// dispatch principal; pagination pages are transient and report the neutral
    /// pair under the current identity.
    nonisolated func fetchDiscoverFeedResolvingPrincipal(
        limit: Int, offset: Int, eventPct: Double?, cacheTTL: TimeInterval?
    ) async throws -> DiscoverFeedFetchResult {
        guard offset == 0 else {
            let response = try page(limit: limit, offset: offset)
            return DiscoverFeedFetchResult(
                response: response, identityAtFetch: await identityNow(),
                wasAuthenticated: false, expectedSignedIn: false)
        }
        let atFetch = await principal()
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
        let client = FixedDiscoverFeed(path: url.path, bytes: try? Data(contentsOf: url))
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
        now: Date = Date()
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
        ]
        guard let data = try? JSONSerialization.data(withJSONObject: body, options: [.sortedKeys]),
              let text = String(data: data, encoding: .utf8)
        else { return "{}" }
        return text
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
