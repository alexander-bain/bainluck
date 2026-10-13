import SwiftUI

/// #10973 — AN OPEN QUESTION SHEET'S AGE HAS TO KEEP COUNTING.
///
/// Build 50 source, MNF BUF@LAR, 2026-10-13: a Live Player Props sheet
/// (Blake Corum · 1+ reception) opened at 02:06Z and held without refreshing
/// read "Kalshi · Updated 4m ago" in every frame through 02:28Z
/// (`artifacts/native-9483/build50-live/hold/`). The leg had left
/// `/game-markets`, so the held row never changed again, and a body that reads
/// only `observedAt` is never redrawn. That is `MinuteClock`'s #7019 freeze on a
/// different string: the age must be a function of an instant the view
/// observes, not of the minute the row last rendered.
///
/// Sixty seconds is enough. `SourceAge.formatAge` has no rung finer than a
/// minute ("just now" below one).
struct SourceAgeText: View {
    let observedAt: String?
    /// "Updated" in the summary, nothing beside a source row.
    var prefix: String? = nil
    var font: Font = .caption
    @ObservedObject var clock = MinuteClock.shared

    var body: some View {
        if let age = SourceAge.format(observedAt, now: clock.now) {
            Text(prefix.map { "\($0) \(age)" } ?? age)
                .font(font)
                .foregroundStyle(.secondary)
        }
    }
}
