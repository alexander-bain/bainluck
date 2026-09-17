import XCTest
@testable import Bain_Luck

/// #6705 — **a reader can scroll the futures page with a finger on the chart.**
///
/// The evolution chart drew its crosshair from a full-bleed `Color.clear`
/// overlay carrying `.gesture(DragGesture(minimumDistance: 0))`, which starved
/// `FuturesDetailView`'s `ScrollView`. Measured by the finger-driven
/// `AReaderCanScrollPastTheChartTests`: an identical 160pt swipe travelled
/// ~330pt started off the chart and **0.0pt** started on it. The chart is 280pt
/// tall at full width, mid-page — about a third of the viewport on a 390×844
/// phone was a region where the page did not scroll.
///
/// ## Four SwiftUI fixes were measured and all four failed
///
/// | attachment                                                | travel |
/// |-----------------------------------------------------------|--------|
/// | `.gesture(DragGesture(minimumDistance: 0))` — shipped      | 0.0pt  |
/// | `.simultaneousGesture(DragGesture(minimumDistance: 0))`    | 0.0pt  |
/// | `.gesture(LongPress.sequenced(before: Drag))`              | 0.0pt  |
/// | `.simultaneousGesture(LongPress.sequenced(before: Drag))`  | 0.0pt  |
/// | *no gesture at all*                                         | scrolls |
///
/// `simultaneousGesture` composes a gesture with other SwiftUI gestures, and
/// the recognizer being starved is `UIScrollView`'s own pan, which is not in
/// that graph. It reads like the fix and is not one — which is exactly the
/// mistake this file's source scans exist to stop the next reader repeating,
/// because the first version of this ship shipped it with fifteen green unit
/// arms beside a chart that still swallowed every scroll.
///
/// The fix is a UIKit pan whose delegate answers
/// `shouldRecognizeSimultaneouslyWith: true` (`ChartScrubSurface`). That hands
/// the scroll back unconditionally — and it is what makes `ChartScrubState`
/// load-bearing rather than decorative: both recognizers now fire, so without
/// an axis decision a vertical scroll would drag a crosshair down the page.
final class AReaderCanScrollPastTheChart6705Tests: XCTestCase {

    // MARK: - The scroll is handed back (the half no unit test can observe)

    func testTheScrubRunsOnAPanThatSharesTheTouchWithTheScrollView() throws {
        let surface = try code(at: Self.scrubSurface)

        XCTAssertTrue(
            surface.contains("shouldRecognizeSimultaneouslyWith"),
            """
            ChartScrubSurface exists for exactly one line: the delegate callback that lets \
            UIScrollView's pan and this one both recognize. Without it this is a slower \
            DragGesture and #6705 is back.
            """
        )

        // ⚠️ THE ASSERTION ABOVE IS NOT ENOUGH, AND A MUTATION BATTERY PROVED IT.
        // Flipping the delegate's `true` to `false` reinstates the defect in
        // full and leaves the method — and therefore that scan — untouched. It
        // was the single survivor of 14 mutants. So the answer is a named
        // constant, and both halves of it are pinned: the value itself, and
        // the delegate actually returning it rather than a literal of its own.
        #if os(iOS)
        XCTAssertTrue(
            ChartScrubSurface.sharesTheTouchWithTheScrollView,
            """
            This constant IS #6705's fix. False means the chart's pan starves FuturesDetailView's \
            ScrollView again and a third of the viewport stops scrolling.
            """
        )
        #endif
        XCTAssertTrue(
            surface.contains("ChartScrubSurface.sharesTheTouchWithTheScrollView"),
            """
            The delegate must ANSWER with the constant. A literal in the body is invisible to \
            the assertion above — which is exactly how this line survived the first battery.
            """
        )
        XCTAssertTrue(
            surface.contains("pan.delegate = context.coordinator"),
            "the delegate must actually be attached, or the callback is never asked"
        )
        XCTAssertTrue(
            surface.contains("UIPanGestureRecognizer"),
            "a SwiftUI DragGesture cannot express simultaneous recognition with the scroll"
        )
    }

    func testTheChartUsesThatSurfaceAndNotASwiftUIDragGesture() throws {
        let view = try code(at: Self.chartView)

        XCTAssertTrue(
            view.contains("ChartScrubSurface("),
            "the iOS chart overlay must be the UIKit surface"
        )

        // The defect's signature, as a negative. Anchored on the OPENING
        // DELIMITER `.gesture(` immediately followed by the drag: `.gesture` is
        // a substring of `.simultaneousGesture`, so scanning for the bare word
        // is satisfied by the defect and the fix alike.
        let iOSBranch = view.components(separatedBy: "#else").first ?? view
        XCTAssertFalse(
            iOSBranch.contains("DragGesture(minimumDistance: 0)"),
            """
            A SwiftUI DragGesture is attached on the iOS path. All four compositions of that \
            were measured at 0.0pt of scroll (see this class's doc comment). The macOS branch \
            below `#else` legitimately keeps one — a trackpad scroll never contended for the \
            touch — which is why this scan reads only the iOS half.
            """
        )
    }

    /// A perfect state machine the view never asks is worth nothing.
    func testTheViewActuallyConsultsTheScrubStateAndClearsIt() throws {
        let view = try code(at: Self.chartView)

        XCTAssertTrue(
            view.contains("guard scrub.change("),
            """
            The scrub decision must GATE the crosshair update, not run beside it. The pan now \
            recognizes simultaneously with the scroll, so this view is called throughout a \
            plain scroll — everything below depends on it honouring the answer.
            """
        )
        XCTAssertTrue(
            view.contains("scrub.end()"),
            """
            The gesture's end must clear the latch. A latch that outlives its gesture is \
            #1773's defect one layer down: the first drag resolved would be the last one ever \
            treated as a scrub.
            """
        )
    }

    // MARK: - The crosshair does not chase the scroll

    func testAVerticalDragIsTheScrollAndNotAScrub() {
        var scrub = ChartScrubState()

        XCTAssertFalse(
            scrub.change(width: 2, height: -60),
            "a vertical flick is the reader scrolling the page, not a scrub"
        )
        XCTAssertTrue(scrub.axisLatched)
        XCTAssertFalse(scrub.isHorizontal)
        XCTAssertFalse(scrub.tracks)
    }

    func testAHorizontalDragIsAScrub() {
        var scrub = ChartScrubState()

        XCTAssertTrue(scrub.change(width: 40, height: 3), "scrubbing a time series is horizontal")
        XCTAssertTrue(scrub.isHorizontal)
        XCTAssertTrue(scrub.tracks)
    }

    func testAStationaryTouchStillTracksSoPressAndHoldInspectSurvives() {
        var scrub = ChartScrubState()

        // The first pan callback arrives at exactly (0, 0). If that latched,
        // `abs(0) > abs(0)` is false, the gesture would latch VERTICAL on a
        // finger that has not moved, and the chart's primary interaction would
        // be dead on arrival. This is the whole reason `axisThreshold` is not 0.
        XCTAssertTrue(scrub.change(width: 0, height: 0))
        XCTAssertFalse(scrub.axisLatched, "a touch that has not moved has not chosen an axis")
        XCTAssertTrue(scrub.change(width: 1, height: -2), "jitter is not a decision")
        XCTAssertFalse(scrub.axisLatched)
        XCTAssertTrue(scrub.tracks)
    }

    func testTheLatchSurvivesTheRestOfTheGestureEvenWhenItCrossesTheDiagonal() {
        var scrub = ChartScrubState()

        XCTAssertFalse(scrub.change(width: 0, height: -40))
        // A drag that later wanders 90pt sideways does NOT become a scrub. A
        // per-frame axis decision flips here, and flipping mid-gesture is how
        // DiscoverSwipeState's predecessor produced its silent dead cards.
        XCTAssertFalse(
            scrub.change(width: 90, height: -45),
            "one decision per gesture: a latched scroll stays a scroll"
        )
        XCTAssertFalse(scrub.isHorizontal)
    }

    func testTheLatchIsClearedSoTheNextDragDecidesForItself() {
        var scrub = ChartScrubState()

        scrub.change(width: 0, height: -40)
        XCTAssertFalse(scrub.tracks)

        scrub.end()
        XCTAssertFalse(scrub.axisLatched, "the latch must not outlive its gesture")
        XCTAssertTrue(scrub.tracks, "a fresh chart is inspectable again")

        XCTAssertTrue(scrub.change(width: 40, height: 2))
        XCTAssertTrue(scrub.isHorizontal)
    }

    func testATieGoesToTheScroll() {
        var scrub = ChartScrubState()

        // `>` and not `>=`: on a scrolling page the scroll is the behaviour the
        // reader is entitled to, and a perfectly diagonal drag is likelier a
        // sloppy scroll than a deliberate scrub.
        XCTAssertFalse(scrub.change(width: 30, height: -30))
        XCTAssertFalse(scrub.isHorizontal)
    }

    func testTheThresholdIsMeasuredOnTheLargerAxisNotTheDiagonal() {
        var scrub = ChartScrubState()

        // 9 and 9 is a diagonal of 12.7 — over the threshold if you measure
        // `hypot`, under it on either axis. Measuring the diagonal would latch
        // on jitter that has not committed to a direction, which is the only
        // moment the decision is genuinely unreliable.
        XCTAssertTrue(scrub.change(width: 9, height: 9), "still undecided, so still inspectable")
        XCTAssertFalse(scrub.axisLatched, "neither axis has cleared the threshold yet")

        // Exactly at the threshold it latches, so the boundary is pinned in
        // both directions rather than left to a `<` / `<=` typo.
        XCTAssertFalse(scrub.change(width: 0, height: -ChartScrubState.axisThreshold))
        XCTAssertTrue(scrub.axisLatched)
    }

    // MARK: - The shipped behaviour, pinned

    /// Verbatim reference copy of what the shipped overlay decided — which was
    /// that it decided nothing. Every drag callback updated the crosshair,
    /// whatever direction it went in.
    ///
    /// Kept as a literal so the defect is provable against a control rather
    /// than argued from a diff (ruling 067). Deliberately NOT a call into
    /// `ChartScrubState` with a flag: a control that shares code with its
    /// subject stops being a control the first time the subject is refactored.
    private struct LegacyScrub {
        func tracks(width: CGFloat, height: CGFloat) -> Bool { true }
    }

    func testLegacyOverlayDraggedTheCrosshairThroughEveryScroll() {
        let legacy = LegacyScrub()
        var fixed = ChartScrubState()
        let flick = (width: CGFloat(2), height: CGFloat(-60))

        XCTAssertTrue(
            legacy.tracks(width: flick.width, height: flick.height),
            "the shipped overlay tracked a pure vertical scroll — pinned, so the fix is "
            + "measured against it and not against a description of it"
        )
        XCTAssertFalse(
            fixed.change(width: flick.width, height: flick.height),
            "the fix must not"
        )

        // Both agree on the interaction that is supposed to work, which is what
        // makes this a defect fix and not a feature removal.
        XCTAssertTrue(legacy.tracks(width: 40, height: 3))
        var scrubbing = ChartScrubState()
        XCTAssertTrue(scrubbing.change(width: 40, height: 3))
    }

    // MARK: - Helpers

    private static var projectRoot: URL {
        URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
    }

    private static var chartView: URL {
        projectRoot.appendingPathComponent("Bain Luck/Components/EvolutionChartView.swift")
    }

    private static var scrubSurface: URL {
        projectRoot.appendingPathComponent("Bain Luck/Components/ChartScrubSurface.swift")
    }

    /// Source with its comment lines removed, plus the check that the strip left
    /// real code standing: both scanned files quote `.gesture(`, `DragGesture`
    /// and `simultaneousGesture` in their doc comments — on purpose, to record
    /// the dead ends — and a scan that reads those grades prose. The non-empty
    /// assertion is there because an over-eager filter makes every `contains`
    /// pass against an empty string.
    private func code(at url: URL) throws -> String {
        let source = try String(contentsOf: url, encoding: .utf8)
        let stripped = source
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(
            stripped.contains("struct "),
            "the comment strip left nothing to scan in \(url.lastPathComponent)")
        return stripped
    }
}
