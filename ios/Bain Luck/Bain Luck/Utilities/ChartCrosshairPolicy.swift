import Foundation

/// One retained reading a scrub can land on: an outcome's probability at an
/// instant the venue actually observed.
nonisolated struct ScrubCandidate: Equatable, Sendable {
    let date: Date
    let name: String
    let probability: Double

    init(date: Date, name: String, probability: Double) {
        self.date = date
        self.name = name
        self.probability = probability
    }
}

/// Where a crosshair dropped at some time on the axis comes to rest, and what it
/// is allowed to say when it gets there.
///
/// ## 🔴 #7547 — THE CROSSHAIR CHOSE ITS INSTANT FROM ONE POPULATION AND SPOKE FOR
/// ## ANOTHER, SO HALF THE SCRUB DID NOTHING AT ALL
///
/// `EvolutionChartView.updateCrosshair` picked the nearest instant over every
/// DISPLAYED outcome (the `Top N` chip — ten lines by default, eight of them drawn
/// at opacity 0.1), then reported only the SELECTED ones (three by default). When
/// the instant it snapped to carried no selected reading the tooltip came out
/// empty, and the code's response to an empty tooltip was to leave `crosshair`
/// exactly as it was.
///
/// Leaving it as it was is the defect. The `RuleMark` stays parked at the previous
/// date while the finger keeps travelling, so the dashed line stops following the
/// touch and the tooltip goes on printing a timestamp and a price from wherever it
/// last succeeded. A reader dragging across the chart gets a crosshair that sticks,
/// then jumps — and while it is stuck it is pointing at one moment and reading out
/// another.
///
/// ### Why this is a #7547 defect and not a cosmetic one
///
/// It is *caused* by the retained intraday detail this issue exists to preserve.
/// Minute-level capture records the outcome that MOVED at the minute it moved, so a
/// dense window is mostly single-outcome instants. Measured on production market
/// **56775596** (Las Vegas: Team Specials, 12 Kalshi props, `source: kalshi`,
/// `bucket_seconds: 3600` but real 60s gaps), in the default state the app ships —
/// `topFilter` 10, `selectedNames` the served first three:
///
/// | range | instants a scrub can snap to | instants that move the crosshair | stuck |
/// |-------|------------------------------|----------------------------------|-------|
/// | `24h` | 157                          | 82                               | **75 (47.8%)** |
/// | `7d`  | 477                          | 299                              | **178 (37.3%)** |
///
/// 156 of that payload's 203 instants carry exactly ONE outcome; 201 of 203 do not
/// carry all twelve. So the denser the retained history gets, the more of the scrub
/// stops working — the failure grows with the fix it is attached to.
///
/// ### The fix is to make it one population, not to widen the tooltip
///
/// Snap and report are now the same set: the reader's selected lines. Every
/// position the crosshair can reach therefore has something true to say when it
/// arrives, and `resolve` returning nil means only "this reader has selected
/// nothing that was ever observed" — a state in which the old code drew no
/// crosshair either, so there is no window that regresses.
///
/// Reporting the faint unselected lines instead would have been the other way to
/// close the gap, and it is rejected: those lines are drawn at 0.1 opacity
/// precisely because the reader deselected them, and a tooltip that lists ten props
/// when three are selected answers a question nobody asked.
///
/// ### 🪤 Why the guard for this is a unit test and not a finger
///
/// A real-finger XCUITest was built for this and then DELETED, because it was
/// measured not to work. Against the defect deliberately restored it passed in
/// 36.7s with 0 failures — the same verdict as against the fix.
///
/// The reason is structural. `crosshair` is cleared in `onEnd`, so it lives only
/// for one gesture, and the defect is stickiness *within* a gesture. Every
/// separate press-and-hold starts from nil and resolves fresh, so a drag long
/// enough to pose reliably has already crossed enough reachable instants to come
/// to rest near the right place under either rule. Catching it needs two reads
/// inside ONE continuous drag, and XCUITest has no multi-leg gesture:
/// `press(forDuration:thenDragTo:withVelocity:thenHoldForDuration:)` returns
/// after the lift.
///
/// **The discriminating experiment, if someone wants the finger anyway:** confine
/// a SHORT drag to a stretch of axis where the selected outcomes have no readings
/// at all. Under the defect no crosshair is ever assigned and none appears; under
/// this rule one appears at once. Present/absent, not equal/unequal. It needs the
/// served payload mapped onto plot x for the market under test. Two rig facts
/// already paid for: the gesture must run on the MAIN thread (a background one
/// dies `Must be called on the main thread`) while the read goes on a background
/// queue during the hold; and both drags must be RIGHT-to-left, because a
/// left-to-right drag mid-page is the interactive-pop direction and takes the page
/// off the navigation stack under the finger.
///
/// ### Nothing here interpolates
///
/// `resolve` returns a candidate's OWN `date` and its OWN `probability`. There is no
/// synthesised midpoint between two readings and no snapping to a bucket boundary:
/// the crosshair reports an observation or it reports nothing, which is the whole
/// of #7547's "preserve true timestamps, extrema and gaps without interpolation
/// masquerading as observations".
enum ChartCrosshairPolicy {

    /// The reading a crosshair dropped at `date` comes to rest on.
    ///
    /// - Parameters:
    ///   - date: where on the time axis the touch landed.
    ///   - candidates: every reading the crosshair may both SNAP TO and SPEAK FOR.
    ///     One list, deliberately — see the type's note. Callers pass the selected
    ///     outcomes' real readings and nothing else: no combined/synthetic line,
    ///     which is computed from the others and is not an observation.
    /// - Returns: the resting instant and the readings observed at it, richest
    ///   first, or `nil` when there is no reading to rest on.
    static func resolve(
        at date: Date,
        among candidates: [ScrubCandidate]
    ) -> (date: Date, entries: [ScrubCandidate])? {
        // Ties broken by the earlier reading, not by list order. A touch exactly
        // between two observations is ordinary — the gaps here are 60s wide — and
        // `min(by:)` alone would answer it from wherever the candidate list
        // happened to be built, so the same pixel could report two different
        // moments across a reload.
        guard let nearest = candidates.min(by: { lhs, rhs in
            let l = abs(lhs.date.timeIntervalSince(date))
            let r = abs(rhs.date.timeIntervalSince(date))
            return l == r ? lhs.date < rhs.date : l < r
        }) else { return nil }

        let restingDate = nearest.date
        let entries = candidates
            .filter { $0.date == restingDate }
            .sorted { $0.probability > $1.probability }

        // `nearest` is itself in `candidates` at `restingDate`, so this cannot be
        // empty — but returning the tuple rather than the array keeps the caller
        // from having to re-derive the date the entries belong to.
        return (date: restingDate, entries: entries)
    }
}
