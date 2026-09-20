import XCTest

/// #6705, driven by a finger: **a reader whose thumb lands on the probability
/// chart can still scroll the page.**
///
/// ## Why this cannot be a unit test
///
/// The defect is a view modifier. `EvolutionChartView`'s crosshair overlay used
/// `.gesture(DragGesture(minimumDistance: 0))`, and an attached gesture COMPETES
/// with the enclosing `ScrollView`'s pan rather than running beside it — at
/// minimumDistance 0 it claims the touch at touch-down, so the scroll view never
/// sees the pan. Nothing about that is observable from a state machine, from a
/// rendered snapshot, or from the served payload. Only a real finger on a real
/// scroll view can tell you whether the page moved.
///
/// The sibling `AReaderCanScrollPastTheChart6705Tests` guards the modifier with
/// a source scan and owns the axis-latch half. This file is the reader.
///
/// ## The control is the point
///
/// A swipe that fails to scroll is not by itself evidence of anything — the rig
/// could be swiping wrong, the page could be at its bottom, the simulator could
/// be wedged. So the scroll test performs the SAME swipe, of the SAME length,
/// from two start points and compares:
///
///   * one starting on the chart   — the region under test
///   * one starting off it         — the control, on ordinary page content
///
/// Under the defect the control scrolls and the chart swipe does not, and that
/// asymmetry is the finding. If neither scrolls, the rig is broken and this
/// test says so instead of blaming the chart.
///
/// ⚠️ **THE FIRST VERSION OF THIS FILE PROVED NOTHING AND LOOKED LIKE A DEFECT.**
/// Its helper built the drag destination as `normalized(0.5, 0.12) + (0, -220)`,
/// which is y = −118: off the top of the screen. XCUITest synthesised the
/// gesture, the page did not move, and the control assertion failed reading
/// "the CONTROL swipe did not scroll the page (0.0pt)". That was the rig, and
/// the only reason it was not mistaken for the app is that the control existed
/// to catch it. Every coordinate below is therefore clamped INSIDE the window
/// and the two drags are asserted to have travelled the same distance.
final class AReaderCanScrollPastTheChartTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    /// NFL Super Bowl Winner. Chosen because it is marquee, in season, and
    /// measured on production 2026-09-17 to serve 42 timeline points across 11
    /// outcomes on `/api/futures/86832/probability-timeline?hours=168` — the
    /// chart only renders at `chartEntries.count >= 2`, so a market with a thin
    /// history would make this test green by drawing no chart at all.
    private static let route = "bainluck://futures/86832"

    /// Points of travel below which we call it "did not scroll". Generous on
    /// purpose: the question is dead-vs-alive, not how far.
    private static let scrolledThreshold: CGFloat = 40

    /// The page's own title, used to tell "still here" from "navigated away".
    private static let pageTitle = "Market Details"

    // MARK: - The scroll

    func testASwipeStartingOnTheChartScrollsThePage() throws {
        let app = try Self.openTheChart()
        let chart = app.otherElements[Self.chartIdentifier]
        let window = app.frame

        add(Self.shot(app, "1-chart-on-screen"))

        // ONE travel distance for both drags. A control and a subject that
        // travel different distances are not a comparison.
        let travel = Self.travel

        // ── THE CONTROL: ordinary page content ──
        //
        // The start point has to clear the chart's OWN control bar, which sits
        // immediately above the plot and carries the range chips (Season/7d/
        // 24h/Today) and the Top 5/10/20 chips. The first version of this test
        // started the control drag 40pt above the plot — squarely on the Top-N
        // row — and the chart vanished from the hierarchy mid-test, because a
        // range change puts the view back into its `loading` branch where there
        // is no chart to find. A control that perturbs its own subject is not a
        // control.
        let controlStart = Self.aControlPoint(chart: chart.frame, window: window)
        XCTAssertLessThan(
            controlStart.y, chart.frame.minY - 100,
            "the control start must clear the chart's control bar, not press its chips"
        )

        let beforeControl = chart.frame.origin.y
        Self.dragUp(app, from: controlStart, by: travel)
        let controlTravel = beforeControl - chart.frame.origin.y

        XCTAssertGreaterThan(
            controlTravel, Self.scrolledThreshold,
            """
            The CONTROL swipe moved the page \(controlTravel)pt from \(controlStart), travel \
            \(travel)pt. This test can say nothing about the chart until an ordinary swipe on \
            this page works — the rig, the page position or the simulator is the problem, not \
            #6705. (If the page was already at its bottom, the control has no room: that is a \
            rig fault too.)
            """
        )

        // ── THE SUBJECT: the identical swipe, started on the chart ──
        //
        // RE-READ the frame. The control drag just scrolled the page, so the
        // chart is 160-odd points higher than it was when this test opened, and
        // a subject point computed before that scroll would land on whatever
        // moved into its place — which on this page is the leaderboard.
        let movedRect = chart.frame
        let tabBar = Self.tabBarRect(app)
        let subjectStart = Self.aScrubPoint(chart: movedRect, tabBar: tabBar)
        assertPosable(subjectStart, chart: movedRect, tabBar: tabBar, "the scroll subject")
        XCTAssertGreaterThan(
            subjectStart.y - travel, window.minY + 40,
            "the subject drag would end off the top of the window — the rig cannot pose it"
        )

        let beforeChart = chart.frame.origin.y
        Self.dragUp(app, from: subjectStart, by: travel)
        let chartTravel = beforeChart - chart.frame.origin.y

        add(Self.shot(app, "2-after-the-swipe-that-started-on-the-chart"))

        XCTAssertGreaterThan(
            chartTravel, Self.scrolledThreshold,
            """
            A swipe starting ON the chart moved the page \(chartTravel)pt, while the identical \
            \(travel)pt swipe starting off it moved \(controlTravel)pt. That asymmetry IS \
            #6705: the crosshair overlay is attached with `.gesture` instead of \
            `.simultaneousGesture`, so at minimumDistance 0 it claims the touch at touch-down \
            and FuturesDetailView's ScrollView never receives the pan.

            The chart is 280pt tall at full width, mid-page — about a third of the viewport on \
            a 390x844 phone is a region where the page does not scroll.
            """
        )
    }

    // MARK: - The negative half

    /// A fix that handed the scroll back by DELETING the gesture would pass the
    /// test above and silently remove the chart's only interaction. So the
    /// scrub is asserted to still be consumed by the chart.
    ///
    /// Dragged right-to-left deliberately: left-to-right is the interactive-pop
    /// direction and confounds "the chart consumed it" with "the navigation
    /// stack did". That case is its own test below, because it is a real
    /// question about this fix and not a detail to route around quietly.
    func testAHorizontalScrubIsConsumedByTheChartAndNotByThePage() throws {
        let app = try Self.openTheChart()
        let chart = app.otherElements[Self.chartIdentifier]

        let before = chart.frame.origin.y
        let chartRect = chart.frame
        let tabBar = Self.tabBarRect(app)

        // `dy: 0.5` is the chart's vertical midpoint, which at this scroll
        // offset is BEHIND the floating tab bar (see `aScrubPoint`). This test
        // passed while posed there, but a drag the tab bar intercepts cannot
        // show that the CHART consumed anything — it was green without
        // measuring its own subject.
        let scrubY = Self.aScrubPoint(chart: chartRect, tabBar: tabBar).y
        let startPoint = CGPoint(x: chartRect.minX + chartRect.width * 0.80, y: scrubY)
        let endPoint = CGPoint(x: chartRect.minX + chartRect.width * 0.20, y: scrubY)
        assertPosable(startPoint, chart: chartRect, tabBar: tabBar, "the scrub start")
        assertPosable(endPoint, chart: chartRect, tabBar: tabBar, "the scrub end")

        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: startPoint.x, dy: startPoint.y))
        let end = origin.withOffset(CGVector(dx: endPoint.x, dy: endPoint.y))
        start.press(forDuration: 0.4, thenDragTo: end)

        add(Self.shot(app, "3-after-a-right-to-left-scrub"))

        XCTAssertTrue(
            app.staticTexts[Self.pageTitle].exists,
            "a horizontal scrub must not leave the page (title \(Self.pageTitle) is gone)"
        )
        XCTAssertTrue(chart.exists, "the chart must survive its own gesture")
        XCTAssertLessThan(
            abs(chart.frame.origin.y - before), Self.scrolledThreshold,
            """
            A horizontal drag scrolled the page \(abs(chart.frame.origin.y - before))pt \
            vertically. `simultaneousGesture` means the ScrollView sees the pan too, which is \
            correct for a vertical drag and must be very nearly inert for a horizontal one.
            """
        )
    }

    /// **A reader can still swipe back from the screen edge.**
    ///
    /// ## What this test used to be, and why it is not that any more
    ///
    /// It compared a left-to-right drag MID-PAGE on ordinary content against
    /// the same drag mid-page on the chart, and asserted they agreed. Measured
    /// 2026-09-17, that comparison cannot decide anything, for two reasons
    /// found in that order:
    ///
    /// 1. **The subject was not on the chart.** `chart.midY` is behind the
    ///    floating tab bar at this page's initial offset, so the drag swept the
    ///    tab bar Sports → My Stuff and the vanished title read as "the chart
    ///    went back". Three different `UIGestureRecognizerDelegate` answers
    ///    failed it identically, because the touch never reached the chart.
    ///    Fixed for every test in this file by `aScrubPoint` + `assertPosable`.
    /// 2. **The CONTROL arm is nondeterministic.** With the pose corrected, the
    ///    same mid-page drag on inert content popped the page on one run and
    ///    not on the next — the scroll view and the interactive pop race for it.
    ///    A parity assertion whose control flips between runs cannot fail
    ///    honestly: it reported "page stayed, chart went back" and then, on the
    ///    next build, "page went back, chart stayed".
    ///
    /// A mid-page left-to-right drag is also not a gesture a reader performs.
    /// The gesture a reader performs starts at the SCREEN EDGE, and that is
    /// what this now measures — deterministic, real, and the thing actually at
    /// risk from a full-bleed recognizer in the middle of the page.
    ///
    /// The chart is inset 32pt from the left edge, so an edge swipe never
    /// begins on it. This test's job is to prove that stays true: that #6705's
    /// UIKit pan did not reach out and swallow the system back gesture.
    func testAReaderCanStillSwipeBackFromTheEdge() throws {
        let app = try Self.openTheChart()
        let chart = app.otherElements[Self.chartIdentifier]
        let chartRect = chart.frame

        // The premise. If the chart ever spans the left edge, an edge swipe
        // WOULD start on it and this test would be measuring something else.
        XCTAssertGreaterThan(
            chartRect.minX, app.frame.minX + 8,
            """
            The chart now reaches the left screen edge (\(chartRect)), so a back-swipe starts on \
            it. That is a different question from the one this test answers — re-derive it rather \
            than trusting this pass.
            """
        )

        // Vertically level with the chart, so the swipe travels ACROSS it: the
        // touch begins off the chart and ends on it, which is the arrangement
        // most likely to expose a recognizer that grabs mid-gesture.
        let tabBar = Self.tabBarRect(app)
        let y = Self.aScrubPoint(chart: chartRect, tabBar: tabBar).y
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: app.frame.minX + 2, dy: y))
        let finish = origin.withOffset(CGVector(dx: app.frame.minX + 260, dy: y))
        start.press(forDuration: 0.05, thenDragTo: finish)

        add(Self.shot(app, "4-after-an-edge-back-swipe-level-with-the-chart"))

        XCTAssertTrue(
            app.staticTexts[Self.pageTitle].waitForNonExistence(timeout: 3),
            """
            An edge back-swipe level with the chart did not leave \(Self.pageTitle). #6705 put a \
            UIKit pan across the middle of this page; if it is claiming touches that begin off \
            the chart, the reader has lost the back gesture on every futures page.
            """
        )
    }

    // MARK: - Helpers

    private static let chartIdentifier = "evolution-chart-surface"

    /// Launch, deep-link to the market, and leave the chart on screen.
    private static func openTheChart() throws -> XCUIApplication {
        let app = UITestLaunch.launchApp(extra: ["-launch_route", route])
        _ = JourneyPrecondition.tabBar(of: app)

        let chart = app.otherElements[chartIdentifier]
        guard chart.waitForExistence(timeout: 40) else {
            throw XCTSkip(
                """
                The evolution chart never appeared on \(route). Nothing in this file is about \
                #6705 unless it does. Check the market still serves >= 2 timeline points in the \
                CHOSEN window — a thin window renders the range chips over a counted sentence \
                and no plot at all (#7350), which is a supply fact and not this page's bug.
                """
            )
        }

        var approach = 0
        while approach < 20, !chart.isHittable {
            app.swipeUp()
            approach += 1
        }
        XCTAssertTrue(chart.isHittable, "the chart never came on screen in \(approach) swipes")
        return app
    }

    /// How far each drag travels. Fixed rather than derived, so the control and
    /// the subject are the same gesture and the only variable is where it began.
    private static let travel: CGFloat = 160

    /// A start point on ordinary, INERT page content, well clear of the chart's
    /// own control bar (see the call site for what that cost the first time).
    ///
    /// Biased to the upper third of the window: on this page that is the hero
    /// image and the metadata card, neither of which responds to a drag.
    private static func aControlPoint(chart: CGRect, window: CGRect) -> CGPoint {
        let clearOfTheControlBar = chart.minY - 130
        let upperThird = window.minY + window.height * 0.35
        let y = max(min(clearOfTheControlBar, upperThird), window.minY + 100)
        return CGPoint(x: chart.midX, y: y)
    }

    /// The floating tab bar's rect, or `.null` if this platform has none.
    private static func tabBarRect(_ app: XCUIApplication) -> CGRect {
        let bar = app.tabBars.firstMatch
        return bar.exists ? bar.frame : .null
    }

    /// A point ON the chart that the floating tab bar cannot intercept.
    ///
    /// ⚠️ **`chart.midY` IS NOT A POINT ON THE CHART, AND THAT COST THIS FILE A
    /// FALSE POSITIVE.** MainTabView's tab bar FLOATS over the scroll content,
    /// and at the page's initial offset the chart's lower half is behind it.
    /// Measured 2026-09-17 on iPhone 17 Pro, window 402×874:
    ///
    ///     chart  = (32, 656, 338, 280)   → midY 796
    ///     tabBar = (0, 791, 402,  83)    → top  791
    ///     the element under (201, 796)   → the "Browse" tab button
    ///
    /// So a left-to-right drag posed at the chart's own midpoint started on the
    /// tab bar and swept it Sports → Browse → Search → My Stuff. The test read
    /// the vanished page title as "the chart went back" and reported a
    /// navigation defect that did not exist: the touch never reached the chart,
    /// which is why three different `UIGestureRecognizerDelegate` answers all
    /// failed it identically.
    ///
    /// `XCUIElement.isHittable` does not protect against this — it was `true`
    /// for the chart throughout, so `openTheChart`'s approach loop swiped zero
    /// times. An element can be hittable and still have the point you chose
    /// owned by something drawn on top of it.
    private static func aScrubPoint(chart: CGRect, tabBar: CGRect) -> CGPoint {
        let ceiling = tabBar.isNull ? chart.maxY : min(chart.maxY, tabBar.minY)
        let y = max(min(chart.midY, ceiling - 24), chart.minY + 24)
        return CGPoint(x: chart.midX, y: y)
    }

    /// Refuse to draw a conclusion from a drag that did not start where we meant.
    ///
    /// A rig fault and a product defect are indistinguishable in the result —
    /// both read as "the chart did something the page did not" — so the pose is
    /// asserted before the gesture, in its own message.
    private func assertPosable(
        _ point: CGPoint,
        chart: CGRect,
        tabBar: CGRect,
        _ what: String,
        file: StaticString = #filePath,
        line: UInt = #line
    ) {
        XCTAssertTrue(
            chart.contains(point),
            "\(what): \(point) is not inside the chart \(chart) — the rig cannot pose it",
            file: file, line: line
        )
        if !tabBar.isNull {
            XCTAssertFalse(
                tabBar.contains(point),
                """
                \(what): \(point) is under the floating tab bar \(tabBar), which draws OVER the \
                chart \(chart). A drag from here is delivered to a tab button and whatever it \
                proves is about the tab bar. See `aScrubPoint`.
                """,
                file: file, line: line
            )
        }
    }

    /// Drag straight up by `distance` points from an ABSOLUTE window point.
    ///
    /// Absolute rather than normalized-plus-offset: the normalized form is what
    /// produced the off-screen destination described in this class's header.
    private static func dragUp(_ app: XCUIApplication, from point: CGPoint, by distance: CGFloat) {
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: point.x, dy: point.y))
        let finish = origin.withOffset(CGVector(dx: point.x, dy: point.y - distance))
        start.press(forDuration: 0.05, thenDragTo: finish)
    }

    /// Drag left-to-right — the interactive-pop direction — from an ABSOLUTE
    /// window point, staying inside the window at both ends.
    private static func dragRight(_ app: XCUIApplication, from point: CGPoint) {
        let origin = app.coordinate(withNormalizedOffset: .zero)
        let start = origin.withOffset(CGVector(dx: point.x, dy: point.y))
        let finish = origin.withOffset(
            CGVector(dx: min(point.x + travel, app.frame.maxX - 20), dy: point.y))
        start.press(forDuration: 0.05, thenDragTo: finish)
    }

    private static func shot(_ app: XCUIApplication, _ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
