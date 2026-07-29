import Foundation

/// Pure decision core for the Discover on-screen first-render milestone
/// (L2-206 / #1472, Item 3). Kept free of SwiftUI so the once-per-load and
/// ordering contract — a first-render time is emitted exactly once, only after a
/// load has started, and is a real elapsed measurement rather than a
/// model-assignment stamp — is unit-testable without a running view.
enum DiscoverFirstRender {
    /// The milliseconds from load start to `now` IF a first-render event should be
    /// emitted for this load; otherwise nil.
    ///
    /// Returns nil when it has already been emitted this load (`emitted == true`)
    /// or when no load-start is known (`loadStartedAt == nil`) — the latter guards
    /// against emitting a bogus "first render" that was never anchored to a load
    /// beginning (i.e. never conflating render with plain model assignment). The
    /// result is clamped at 0 so a clock skew can never report a negative latency.
    static func elapsedMsIfShouldEmit(emitted: Bool, loadStartedAt: Date?, now: Date) -> Double? {
        guard !emitted, let loadStartedAt else { return nil }
        return max(0, now.timeIntervalSince(loadStartedAt) * 1000)
    }
}
