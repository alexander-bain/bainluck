import XCTest

/// #925's installed-phone GESTURE clause, driven by a finger: **a reader who
/// presses on a game's chart and drags sideways is scrubbing, not scrolling —
/// even when the thumb drifts vertically on the way — while a vertical swipe
/// that starts on the same chart still scrolls the page.**
///
/// Alex's build-20 recording (2026-09-24, Dallas–Washington 14781697, 01:19–01:22)
/// shows a brief crosshair that disappears as the page moves under his thumb.
/// A thumb never drags perfectly level; the page's scroll view took the touch
/// from `chartXSelection` as soon as the drag had any vertical component.
///
/// XCUITest cannot look mid-gesture, so this measures the one thing it can: how
/// far the chart moved on screen across the gesture. A scrub leaves the page
/// where it was; a stolen touch scrolls it. The drift is UPWARD on purpose — a
/// downward drag at the top of the page rubber-bands and springs back on
/// release, which would read as "held" whatever happened.
///
/// Knobs (`TEST_RUNNER_` environment): `BL_DRAG_ROUTE` (default the recorded
/// specimen) and `BL_DRAG_SCROLL` (`-launch_scroll` points).
final class ASidewaysDragOnAGameChartHoldsThePage925Tests: XCTestCase {

    private var env: [String: String] { ProcessInfo.processInfo.environment }

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    private func launchOnTheChart() -> (XCUIApplication, XCUIElement) {
        let route = env["BL_DRAG_ROUTE"] ?? "bainluck://events/14781697"
        let app = XCUIApplication()
        app.launchArguments += UITestLaunch.arguments + ["-launch_route", route]
        if let scroll = env["BL_DRAG_SCROLL"] { app.launchArguments += ["-launch_scroll", scroll] }
        app.launch()
        let chart = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Win probability over time"))
            .firstMatch
        // One relaunch: the FIRST launch of a run on a cold simulator has been
        // measured never drawing the page inside the budget (twice, one per run,
        // whichever test went first). That is the rig, not the gesture.
        if !chart.waitForExistence(timeout: UITestLaunch.launchTimeout + UITestLaunch.contentTimeout) {
            print("DRAG-RELAUNCH the chart did not appear on the first launch")
            app.terminate()
            app.launch()
        }
        XCTAssertTrue(chart.waitForExistence(timeout: UITestLaunch.launchTimeout + UITestLaunch.contentTimeout),
                      "the game chart never appeared on \(route)")
        // Let the page finish arriving (history + late sections) before measuring;
        // a layout shift during the gesture would read as travel.
        Thread.sleep(forTimeInterval: env["BL_DRAG_SCROLL"] == nil ? 4 : 12)
        XCTAssertTrue(chart.isHittable, "chart is on the page but not under a finger")
        return (app, chart)
    }

    /// A sideways drag that drifts ~15% of the chart's height upward.
    func testASidewaysDragThatDriftsDoesNotScrollThePage() {
        let (_, chart) = launchOnTheChart()
        let before = chart.frame.minY
        // Knobs for exploring the shape of a real thumb; the defaults are the
        // quick, un-held, drifting drag the recording shows.
        let press = TimeInterval(env["BL_DRAG_PRESS"] ?? "") ?? 0.05
        let drift = Double(env["BL_DRAG_DRIFT"] ?? "") ?? 0.25
        let velocity = XCUIGestureVelocity(CGFloat(Double(env["BL_DRAG_VELOCITY"] ?? "") ?? 600))
        let from = chart.coordinate(withNormalizedOffset: CGVector(dx: 0.15, dy: 0.7))
        let to = chart.coordinate(withNormalizedOffset: CGVector(dx: 0.85, dy: 0.7 - drift))
        print("DRAG-SHAPE press=\(press) drift=\(drift) velocity=\(velocity.rawValue)")
        from.press(forDuration: press, thenDragTo: to, withVelocity: velocity, thenHoldForDuration: 1)
        Thread.sleep(forTimeInterval: 1)
        let travel = abs(chart.frame.minY - before)
        print("DRAG-TRAVEL sideways=\(travel) before=\(before) after=\(chart.frame.minY)")
        XCTAssertLessThan(travel, 12,
                          "a sideways drag on the chart scrolled the page \(travel)pt — the scroll took the scrub")
    }

    /// The control: the same chart must not become a dead zone for scrolling.
    func testAVerticalSwipeStartedOnTheChartStillScrollsThePage() {
        let (_, chart) = launchOnTheChart()
        let before = chart.frame.minY
        let from = chart.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.9))
        let to = chart.coordinate(withNormalizedOffset: CGVector(dx: 0.52, dy: 0.1))
        from.press(forDuration: 0.01, thenDragTo: to, withVelocity: .fast, thenHoldForDuration: 0)
        Thread.sleep(forTimeInterval: 1.5)
        let travel = before - chart.frame.minY
        print("DRAG-TRAVEL vertical=\(travel) before=\(before) after=\(chart.frame.minY)")
        XCTAssertGreaterThan(travel, 60,
                             "a vertical swipe started on the chart moved the page only \(travel)pt")
    }
}
