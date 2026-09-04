import Foundation

/// The local Discover interaction profile: one score per card category, fed by
/// swipes/opens/likes/shares, read for two things — a ranking `adjustment` and a
/// category `suppresses` cooldown.
///
/// Lifted out of `DiscoverView` (where it was a `private struct`, so no test could
/// reach it) as the second half of #1221. The first half floored and expired the
/// DISMISS store; this store had neither guard and is the one that actually
/// starves the feed:
///
///   • **It never decayed.** Three left-swipes put a category at `-3.0` and
///     `suppresses` hid it, permanently. The only inputs that raise a score are
///     open/like/share — all of which require seeing a card in that category, and
///     the suppression is exactly what stops that from happening. A cooldown you
///     cannot come back from is a blacklist, and it was written by a gesture the
///     onboarding hint calls "less like this".
///   • **Nothing floored what it removed.** Measured against the live
///     `GET /api/feed?limit=50` page of 2026-09-03 (50 cards over 14 categories):
///     suppressing the 11 largest categories leaves exactly **3 cards**, which is
///     what Alex saw on his phone while the API was handing the client 50.
///
/// So a cooldown now expires — the score decays linearly to zero over
/// `cooldownTTL`, the same 14-day window the dismiss store uses — and
/// `DiscoverView.filteredItems` floors what it may remove.
///
/// `now` is injected everywhere for deterministic tests (gotcha #44).
struct DiscoverInteractionProfile {
    /// One recorded action's effect on a category's score.
    enum Action {
        case detailOpen
        case like
        case unlike
        case share
        case contextExpand
        case contextCollapse

        var weight: Double {
            switch self {
            case .detailOpen: return 1.5
            case .like: return 2.0
            case .unlike: return -1.0
            case .share: return 3.0
            case .contextExpand: return 0.35
            case .contextCollapse: return 0.0
            }
        }
    }

    /// A category is on cooldown at or below this score.
    static let categoryCooldownScore = -3.0
    /// Comparison tolerance for the threshold above.
    ///
    /// Three left-swipes cool a category down — that is the pre-existing product
    /// rule and adding decay must not quietly repeal it. But decay starts the
    /// instant a score is written, so three swipes seconds apart sum to
    /// -2.9999975, and an exact `<= -3.0` would leave the rule reachable in
    /// theory and unreachable in practice. The tolerance is three orders of
    /// magnitude smaller than the smallest weight any action carries, so it can
    /// only ever absorb decay noise, never a real interaction.
    static let cooldownEpsilon = 1e-3
    /// How long a score takes to decay back to neutral. Matches the dismiss
    /// store's `dismissTTL` and web's 14-day story-key suppression: after two
    /// silent weeks the profile holds no opinion it has not re-earned.
    static let cooldownTTL: TimeInterval = 14 * 24 * 3600

    static let storageKey = "discover_interaction_profile_native_v2"
    /// The un-timestamped `[String: Double]` predecessor, migrated once on load.
    static let legacyStorageKey = "discover_interaction_profile_native_v1"

    private struct Entry {
        var score: Double
        var updatedAt: TimeInterval
    }

    private var entries: [String: Entry]

    private init(entries: [String: Entry]) {
        self.entries = entries
    }

    // MARK: - Reading

    /// The category's score as of `now`, decayed. Returns 0 for an unknown
    /// category and for any entry whose window has fully elapsed.
    func score(for category: String, now: Date = Date()) -> Double {
        guard let entry = entries[category.lowercased()] else { return 0 }
        return Self.decayed(entry, now: now)
    }

    /// Ranking nudge. Unchanged from the pre-#1221 rule apart from reading the
    /// decayed score: a small or stale score is no opinion at all.
    func adjustment(for category: String, now: Date = Date()) -> Double {
        let score = score(for: category, now: now)
        guard abs(score) >= 2 else { return 0 }
        return min(12, max(-8, score))
    }

    /// Whether the category is on cooldown. A cooldown is a *downrank the view
    /// may honour above its feed floor*, never a guarantee the card is gone —
    /// see `DiscoverView.filteredItems`.
    func suppresses(category: String, now: Date = Date()) -> Bool {
        score(for: category, now: now) <= Self.categoryCooldownScore + Self.cooldownEpsilon
    }

    func topAffinities(limit: Int = 3, now: Date = Date()) -> [(String, Double)] {
        entries.keys
            .map { ($0, score(for: $0, now: now)) }
            .filter { abs($0.1) >= 2 }
            .sorted { abs($0.1) > abs($1.1) }
            .prefix(limit)
            .map { ($0.0, $0.1) }
    }

    // MARK: - Writing

    mutating func record(category: String, action: Action, now: Date = Date()) {
        let key = category.lowercased()
        // Decay first, then apply — otherwise a score that should have expired
        // gets a fresh timestamp at its old magnitude and never ages out.
        let base = score(for: key, now: now)
        let updated = min(30, max(-10, base + action.weight))
        entries[key] = Entry(score: updated, updatedAt: now.timeIntervalSince1970)
        save()
    }

    mutating func reset() {
        entries = [:]
        save()
    }

    // MARK: - Decay

    /// Linear decay of the score's MAGNITUDE toward zero across `cooldownTTL`.
    /// Linear rather than exponential so the expiry is a date a test can name and
    /// a reader can predict, exactly like the dismiss store's hard TTL.
    private static func decayed(_ entry: Entry, now: Date) -> Double {
        let age = now.timeIntervalSince1970 - entry.updatedAt
        // A clock that moved backwards (timezone/NTP correction) must not
        // AMPLIFY a score; treat any non-positive age as "just recorded".
        guard age > 0 else { return entry.score }
        guard age < cooldownTTL else { return 0 }
        return entry.score * (1 - age / cooldownTTL)
    }

    // MARK: - Persistence

    static func load(now: Date = Date()) -> DiscoverInteractionProfile {
        if let raw = UserDefaults.standard.dictionary(forKey: storageKey) as? [String: [String: Double]] {
            var entries: [String: Entry] = [:]
            for (key, value) in raw {
                guard let score = value["score"], let at = value["at"] else { continue }
                let entry = Entry(score: score, updatedAt: at)
                // Drop entries that have already decayed to nothing rather than
                // carrying dead weight forward forever.
                if decayed(entry, now: now) != 0 { entries[key] = entry }
            }
            return DiscoverInteractionProfile(entries: entries)
        }
        // One-time migration of the timestamp-less predecessor. Survivors are
        // stamped `now` so they decay out over the next 14 days instead of
        // suppressing their category for the life of the install.
        if let legacy = UserDefaults.standard.dictionary(forKey: legacyStorageKey) as? [String: Double] {
            let stamp = now.timeIntervalSince1970
            let entries = legacy.mapValues { Entry(score: $0, updatedAt: stamp) }
            UserDefaults.standard.removeObject(forKey: legacyStorageKey)
            var migrated = DiscoverInteractionProfile(entries: entries)
            migrated.save()
            return migrated
        }
        return DiscoverInteractionProfile(entries: [:])
    }

    private func save() {
        let raw = entries.mapValues { ["score": $0.score, "at": $0.updatedAt] }
        UserDefaults.standard.set(raw, forKey: Self.storageKey)
    }

    // MARK: - Test seam

    /// Build a profile in memory without touching `UserDefaults`.
    static func forTesting(scores: [String: Double], recordedAt: Date) -> DiscoverInteractionProfile {
        DiscoverInteractionProfile(
            entries: scores.mapValues { Entry(score: $0, updatedAt: recordedAt.timeIntervalSince1970) }
        )
    }
}
