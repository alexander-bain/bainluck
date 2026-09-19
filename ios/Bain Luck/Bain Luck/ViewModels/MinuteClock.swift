// `Combine` is not decorative and the compiler will not infer it: the target
// builds with `SWIFT_UPCOMING_FEATURE_MEMBER_IMPORT_VISIBILITY`, under which
// `@Published`'s own `init(wrappedValue:)` and `ObservableObject`'s synthesised
// `objectWillChange` are unavailable without it — "type 'MinuteClock' does not
// conform to protocol 'ObservableObject'", which reads as a conformance mistake
// rather than a missing import.
import Combine
import Foundation

/// #7019 — A CHIP WHOSE ENTIRE CONTENT IS A CLOCK HAS TO READ ONE.
///
/// `StatusBadge`'s scheduled arm draws "In 1d 3h" from `commenceTime` and the
/// current instant. The instant used to arrive implicitly, inside
/// `formatCountdown`, which meant the string was fixed at whatever minute the
/// row last rendered: a My Stuff Upcoming row on a session open since 09:57
/// read `In 1d 3h` at 11:57 beside its own `Tomorrow 1:10 PM`, two hours stale,
/// and a cold relaunch of the same build corrected it
/// (`artifacts/native-233b/asis-signedin-115704.png`). SwiftUI re-renders a view
/// when the body read something that changed; a body that reads only
/// `commenceTime` never changes, so nothing ever re-rendered it.
///
/// ## Why this is shared and not a `TimelineView` per call site
///
/// #6544 solved the same freeze on the event hero by wrapping *that one* badge
/// in `TimelineView(.periodic(from: .now, by: 60))`. It worked, and it left the
/// other four `StatusBadge` call sites — `EventCardView` (Discover, Sports and
/// My Stuff rows), `SearchView` twice, `TeamDetailView` — frozen, which is
/// #7019. A per-call-site wrapper is a fix the next call site does not inherit.
/// Publishing the instant the chip reads puts the tick on the chip instead, so
/// a surface that adopts `StatusBadge` tomorrow gets it without knowing it.
///
/// ## Why the badge keeps its `if let` instead of the timeline closure
///
/// The countdown's *absence* is time-dependent too: `formatCountdown` returns
/// nil once the kickoff passes. Publishing into `@Published now` re-evaluates
/// `StatusBadge.body`, so that `if let` re-runs and an expired chip collapses to
/// a true `EmptyView`. A `TimelineView` re-runs only its own closure, so the
/// badge would stay a real (if empty) element and could leave a 6pt hole in
/// `EventCardView.topBar`'s `HStack(spacing: 6)`, which has no `Spacer` to
/// absorb it. The hero's meta row does, which is why #6544 never met this.
///
/// ## Sixty seconds, and `.common` mode
///
/// Sixty is `formatCountdown`'s own resolution — it resolves to the minute all
/// the way down to `<1m` (#6544's `testTheCountdownChangesWithinOneMinute…`), so
/// a coarser interval shows a stale minute in the hour when the number matters
/// most. `.common` rather than `Timer.scheduledTimer`'s default mode because a
/// feed being scrolled is precisely when the reader is looking at these rows,
/// and `.default` is suspended for the duration of the drag.
final class MinuteClock: ObservableObject {
    /// The one every chip observes. A second instance is a test's.
    static let shared = MinuteClock()

    /// The instant the countdown chips are currently drawn against.
    @Published private(set) var now: Date

    private var timer: Timer?

    /// `interval` is injectable so a test can prove the value actually
    /// republishes rather than asserting that a `Timer` was constructed — the
    /// recomputation is the claim, and a frozen `now` is invisible to any test
    /// that only exercises the formatter.
    init(interval: TimeInterval = 60, now: Date = Date()) {
        self.now = now
        let timer = Timer(timeInterval: interval, repeats: true) { [weak self] _ in
            self?.now = Date()
        }
        timer.tolerance = interval / 12
        RunLoop.main.add(timer, forMode: .common)
        self.timer = timer
    }

    /// Only a test needs this. `shared` lives as long as the process, and a
    /// leaked repeating timer in the suite keeps firing after its owner is gone.
    func stop() {
        timer?.invalidate()
        timer = nil
    }
}
