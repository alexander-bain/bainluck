import XCTest

/// #8651 — **an ordinary scroll on a game page does not rebuild the page.**
///
/// Alex's installed build 23 (2026-09-25 recording, Dallas–Washington 14781697)
/// scrolled choppily enough to "kill usability". Measured on build 23's own
/// source (a1bc4c6447) on a simulator: eight ordinary swipes that start OFF the
/// chart rebuilt the whole event page 105 times, one rebuild every ~0.25 s for
/// as long as the page moved (median gap 0.249 s, min 0.218 s) — the main
/// thread could produce about four pages a second, and a scroll waits for it.
///
/// The cause was #8320's bar title: the hero's bottom edge was held in page
/// `@State`, and that edge moves on every scrolled frame. The page now holds
/// only the decision (has the hero gone under the bar?), which changes when the
/// hero crosses the bar and never between.
///
/// XCUITest cannot time frames, so this counts the thing that made them slow:
/// the page publishes its own rebuild count under `-launch_count_page_builds`
/// (`LaunchRig.countsPageBuilds`), read before and after the swipes.
final class AnOrdinaryScrollDoesNotRebuildTheGamePage8651Tests: XCTestCase {

    /// Four swipe pairs may each carry the hero under the bar and back — eight
    /// crossings, each a legitimate rebuild or two. Build 23 spent 105.
    static let rebuildBudget = 24

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testEightOrdinarySwipesDoNotRebuildThePagePerFrame() throws {
        let route = ProcessInfo.processInfo.environment["BL_SCROLL_ROUTE"] ?? "bainluck://events/14781697"
        let app = XCUIApplication()
        app.launchArguments += UITestLaunch.arguments
            + ["-launch_route", route, "-launch_count_page_builds", "YES"]
        app.launch()
        let chart = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Win probability over time"))
            .firstMatch
        let wait = UITestLaunch.launchTimeout + UITestLaunch.contentTimeout
        // One relaunch, as in `ASidewaysDragOnAGameChartHoldsThePage925Tests`:
        // the first launch on a cold simulator has missed the budget. The rig.
        if !chart.waitForExistence(timeout: wait) {
            print("SCROLL-RELAUNCH the chart did not appear on the first launch")
            app.terminate()
            app.launch()
        }
        XCTAssertTrue(chart.waitForExistence(timeout: wait), "the game chart never appeared on \(route)")
        // Let history and the late sections arrive; their rebuilds are not the scroll's.
        Thread.sleep(forTimeInterval: 6)

        let counter = app.staticTexts["page-build-count"]
        XCTAssertTrue(counter.waitForExistence(timeout: 5),
                      "-launch_count_page_builds drew no counter — the rig flag is inert")
        let before = try XCTUnwrap(Int(counter.label), "counter label \(counter.label) is not a count")

        // Ordinary page swipes, started above and below the chart, never on it:
        // the chart's own gesture is #925's question, not this one.
        let low = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.85))
        let high = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.35))
        var moved: CGFloat = 0
        for _ in 0..<4 {
            let y0 = chart.frame.minY
            low.press(forDuration: 0.01, thenDragTo: high, withVelocity: 800, thenHoldForDuration: 0)
            Thread.sleep(forTimeInterval: 1.2)
            moved = max(moved, abs(chart.frame.minY - y0))
            high.press(forDuration: 0.01, thenDragTo: low, withVelocity: 800, thenHoldForDuration: 0)
            Thread.sleep(forTimeInterval: 1.2)
        }
        let after = try XCTUnwrap(Int(counter.label), "counter label \(counter.label) is not a count")
        print("SCROLL-REBUILDS before=\(before) after=\(after) spent=\(after - before) maxTravel=\(moved)")

        // A strawman guard: swipes that never moved the page cost nothing
        // whatever the page does per frame, and would pass vacuously.
        XCTAssertGreaterThan(moved, 100, "the swipes never scrolled the page (\(moved)pt)")
        XCTAssertLessThanOrEqual(after - before, Self.rebuildBudget,
                                 "eight ordinary swipes rebuilt the event page \(after - before) times — "
                                 + "something the page holds is changing on every scrolled frame")
    }

    /// #8651's scrub half: **a horizontal scrub on the chart does not rebuild the
    /// page.** The scrubbed moment used to be page state, so every scrub step
    /// rebuilt the whole event page and then the chart again — measured on this
    /// specimen with real callbacks, +2 page rebuilds per scrub and a 4–5 s
    /// freeze. The chart owns that moment now; the page has nothing to redo.
    func testAHorizontalScrubDoesNotRebuildThePage() throws {
        let route = ProcessInfo.processInfo.environment["BL_SCROLL_ROUTE"] ?? "bainluck://events/14781697"
        let app = XCUIApplication()
        app.launchArguments += UITestLaunch.arguments
            + ["-launch_route", route, "-launch_count_page_builds", "YES"]
        app.launch()
        let chart = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Win probability over time"))
            .firstMatch
        let wait = UITestLaunch.launchTimeout + UITestLaunch.contentTimeout
        if !chart.waitForExistence(timeout: wait) {
            print("SCRUB-RELAUNCH the chart did not appear on the first launch")
            app.terminate()
            app.launch()
        }
        XCTAssertTrue(chart.waitForExistence(timeout: wait), "the game chart never appeared on \(route)")
        Thread.sleep(forTimeInterval: 6)

        let counter = app.staticTexts["page-build-count"]
        XCTAssertTrue(counter.waitForExistence(timeout: 5),
                      "-launch_count_page_builds drew no counter — the rig flag is inert")
        let before = try XCTUnwrap(Int(counter.label), "counter label \(counter.label) is not a count")
        let y0 = chart.frame.minY

        // Two scrubs across the plot, level — a press that drags sideways.
        for _ in 0..<2 {
            chart.coordinate(withNormalizedOffset: CGVector(dx: 0.15, dy: 0.6))
                .press(forDuration: 0.05,
                       thenDragTo: chart.coordinate(withNormalizedOffset: CGVector(dx: 0.85, dy: 0.55)),
                       withVelocity: 300, thenHoldForDuration: 0.5)
            Thread.sleep(forTimeInterval: 1.5)
        }
        let after = try XCTUnwrap(Int(counter.label), "counter label \(counter.label) is not a count")
        let travel = abs(chart.frame.minY - y0)
        print("SCRUB-REBUILDS before=\(before) after=\(after) spent=\(after - before) travel=\(travel)")

        // The drags must have been scrubs, not scrolls: a scroll that carried the
        // hero under the bar legitimately rebuilds the page and would muddy this.
        XCTAssertLessThan(travel, 12, "the scrub scrolled the page \(travel)pt — #925's question, not this one")
        XCTAssertEqual(after - before, 0,
                       "two scrubs rebuilt the event page \(after - before) times — the scrubbed moment is page state again")
    }
}
