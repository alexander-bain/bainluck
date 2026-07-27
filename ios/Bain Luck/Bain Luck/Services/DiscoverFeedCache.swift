import Foundation

// MARK: - Cached payload

/// A last-good Discover feed payload recovered from disk (L2-197 / #1465).
///
/// The cache persists the **raw** `/api/feed` response bytes and re-decodes them
/// on load, so the server's card order and every probability are preserved
/// byte-for-byte — `FeedResponse`/`FeedItem` are `Decodable`-only, and
/// re-encoding a decoded model could reorder keys or drop fields. `storedAt` and
/// `ttlSeconds` are metadata only; the view's existing `now`-relative eligibility
/// gate (`DiscoverView.eligibleItems`) still runs at render, so nothing here
/// extends how long a settled/aged card may survive ("settled means settled").
nonisolated struct CachedDiscoverFeed: Sendable {
    let response: FeedResponse
    let storedAt: Date
    /// The server's own `cache.ttl_seconds` captured at store time, when present.
    /// Advisory metadata for telemetry/honesty — never a local freshness policy.
    let ttlSeconds: Double?
    /// The identity namespace this payload was stored under (defense-in-depth:
    /// a load only returns a payload whose stored identity matches the request).
    let identity: String

    func age(now: Date) -> TimeInterval { now.timeIntervalSince(storedAt) }
}

// MARK: - Read seam

/// Narrow read seam so `DiscoverViewModel` can seed last-good content without
/// depending on the `APIClient` actor directly (and so tests can inject a fake).
protocol DiscoverLastGoodReading: Sendable {
    func loadLastGoodFeed() async -> CachedDiscoverFeed?
}

// MARK: - Disk cache

/// File-backed, identity-partitioned store for the last successful Discover feed
/// payload. Every operation is best-effort and fails closed: a caching fault
/// must never crash the feed, and a corrupt/foreign entry is discarded rather
/// than served. Storage lives under `<caches>/DiscoverFeedCache/`, one file per
/// identity namespace, so a signed-in user's personalized feed can never surface
/// for another account or for signed-out mode.
nonisolated struct DiscoverFeedCache: Sendable {
    let directory: URL

    init(directory: URL? = nil) {
        if let directory {
            self.directory = directory
        } else {
            let base = FileManager.default.urls(for: .cachesDirectory, in: .userDomainMask).first
                ?? URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true)
            self.directory = base.appendingPathComponent("DiscoverFeedCache", isDirectory: true)
        }
    }

    // MARK: Identity

    /// The cache namespace for the current session. Signed-in users are keyed by
    /// backend user id; signed-out mode is keyed by the anonymous session id. The
    /// two never collide, so a logout/account switch reads a different file.
    static func identity(userId: String?, sessionId: String) -> String {
        if let userId, !userId.isEmpty { return "user:\(userId)" }
        return "anon:\(sessionId)"
    }

    // MARK: Persistence

    /// Persist the raw response body for `identity`. Only the public feed bytes,
    /// `storedAt`, and the identity string are written — never auth headers or
    /// tokens. Best-effort: any I/O error is swallowed (caching is optional).
    func store(rawBody: Data, identity: String, storedAt: Date) {
        let envelope = Envelope(identity: identity, storedAt: storedAt, body: rawBody)
        guard let encoded = try? JSONEncoder().encode(envelope) else { return }
        do {
            try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
            try encoded.write(to: fileURL(for: identity), options: .atomic)
        } catch {
            // Non-fatal: a failed write just means the next launch has no last-good.
        }
    }

    /// Load and decode the last-good payload for `identity`, or nil when absent /
    /// unreadable / foreign / corrupt. A corrupt or identity-mismatched file is
    /// deleted so it can never be served and never wastes space.
    func load(identity: String) -> CachedDiscoverFeed? {
        let url = fileURL(for: identity)
        guard let data = try? Data(contentsOf: url) else { return nil }

        guard let envelope = try? JSONDecoder().decode(Envelope.self, from: data),
              envelope.identity == identity else {
            // Corrupt entry or a filename/identity mismatch — fail closed.
            try? FileManager.default.removeItem(at: url)
            return nil
        }

        let decoder = Self.feedDecoder()
        guard let response = try? decoder.decode(FeedResponse.self, from: envelope.body) else {
            try? FileManager.default.removeItem(at: url)
            return nil
        }

        let ttl = (try? Self.metaDecoder().decode(FeedCacheMeta.self, from: envelope.body))?.cache?.ttlSeconds
        return CachedDiscoverFeed(
            response: response,
            storedAt: envelope.storedAt,
            ttlSeconds: ttl,
            identity: identity
        )
    }

    /// Drop every stored namespace except `identity` (pass nil to drop all). Used
    /// on logout/account switch so no prior user's — or signed-out — last-good can
    /// surface under the new identity.
    func evict(keepingOnly identity: String?) {
        let keep = identity.map(Self.fileName)
        guard let entries = try? FileManager.default.contentsOfDirectory(
            at: directory, includingPropertiesForKeys: nil
        ) else { return }
        for url in entries where url.pathExtension == "json" {
            if let keep, url.lastPathComponent == keep { continue }
            try? FileManager.default.removeItem(at: url)
        }
    }

    // MARK: Internals

    private func fileURL(for identity: String) -> URL {
        directory.appendingPathComponent(Self.fileName(identity), isDirectory: false)
    }

    /// A stable, filesystem-safe filename derived from the identity. Hex-encoding
    /// the UTF-8 bytes is deterministic across launches (unlike `Hasher`, which is
    /// per-process seeded) and reversible, so no collision or run-to-run drift.
    private static func fileName(_ identity: String) -> String {
        let hex = Data(identity.utf8).map { String(format: "%02x", $0) }.joined()
        return "feed-\(hex).json"
    }

    private static func feedDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    private static func metaDecoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// On-disk envelope. `body` is the verbatim server response (base64-encoded by
    /// `JSONEncoder`), giving an exact byte round-trip.
    private struct Envelope: Codable {
        let identity: String
        let storedAt: Date
        let body: Data
    }

    /// Minimal shape used only to lift `cache.ttl_seconds` out of the raw body.
    private struct FeedCacheMeta: Decodable {
        struct CacheInfo: Decodable { let ttlSeconds: Double? }
        let cache: CacheInfo?
    }
}

// MARK: - Cache telemetry

/// A single stale-while-revalidate observation, emitted by `DiscoverViewModel`.
/// Timings isolate perceived time-to-first-card (cache decode/render) from the
/// server round-trip so the client win is measurable without claiming the
/// backend cold miss (#1459) is fixed. No PII and no card content is carried.
nonisolated struct DiscoverFeedTelemetry: Sendable {
    enum Outcome: String, Sendable {
        /// Last-good served immediately; a first card rendered without the miss.
        case cacheHitServed = "cache_hit_served"
        /// No usable cached payload existed; the honest loading state was shown.
        case cacheMiss = "cache_miss"
        /// A background revalidation replaced the payload with a fresh one.
        case revalidateSuccess = "revalidate_success"
        /// Revalidation failed but last-good was preserved (not blanked).
        case revalidateFailedKeptCache = "revalidate_failed_kept_cache"
        /// Revalidation failed with nothing to fall back to (honest error state).
        case revalidateFailedNoCache = "revalidate_failed_no_cache"
    }

    let outcome: Outcome
    /// Milliseconds to load+decode the cached payload (cache-render cost).
    let cacheDecodeMs: Double?
    /// Milliseconds for the server round-trip (network + payload decode).
    let networkMs: Double?
    let itemCount: Int
    /// Age of the served/kept cached payload, when one was involved.
    let cacheAgeSeconds: Double?
}
