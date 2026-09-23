import XCTest

/// #925's RENDERED clause, driven by a finger: **a reader scrubbing a finished
/// game's chart sees the scrubbed moment's time, and a carried game state that
/// says how old it is.**
///
/// `ScrubReadoutDatesCarriedState925Tests` proves the readout's text for every
/// case. It cannot prove anyone ever SEES it: the readout exists only while a
/// finger is on the chart (`chartXSelection` clears on release), the shoot rig
/// cannot drag, and XCUITest cannot query mid-gesture. So this journey does the
/// one thing a still camera needs — it press-drags onto the chart and HOLDS —
/// and the camera is outside: `tools/native-925-scrub-shoot.sh` runs this test
/// while `simctl io screenshot` photographs the simulator during each hold.
/// This file asserts the journey ran (chart found, every stop held); the frames
/// are the evidence, read by a person.
///
/// Knobs, passed through `xcodebuild`'s `TEST_RUNNER_` environment:
///   `BL_SCRUB_ROUTE`  default `bainluck://events/14780544` (Chiefs 33–30 Colts,
///                     2026-09-21, 167 ESPN rows — a public finished page)
///   `BL_SCRUB_TZ`     the APP's time zone (`TZ`), for the midnight control:
///                     a game that crosses local midnight must print a dated
///                     `as of`, never a bare time that reads as the future.
///   `BL_SCRUB_HOLD`   seconds held at each stop (default 6)
///   `BL_SCRUB_STOPS`  comma-separated x fractions across the plot
///   `BL_SCRUB_SCROLL` `-launch_scroll` points so chart + readout share a frame
final class AReaderCanScrubAGameChart925Tests: XCTestCase {

    private var env: [String: String] { ProcessInfo.processInfo.environment }

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    func testAFingerHeldOnTheGameChartKeepsTheScrubReadoutUp() throws {
        let route = env["BL_SCRUB_ROUTE"] ?? "bainluck://events/14780544"
        let hold = TimeInterval(env["BL_SCRUB_HOLD"] ?? "") ?? 6
        let stops = (env["BL_SCRUB_STOPS"] ?? "0.12,0.3,0.5,0.7,0.88")
            .split(separator: ",").compactMap { Double($0) }
        XCTAssertFalse(stops.isEmpty, "no scrub stops parsed")

        let app = XCUIApplication()
        app.launchArguments += UITestLaunch.arguments + ["-launch_route", route]
        if let scroll = env["BL_SCRUB_SCROLL"] { app.launchArguments += ["-launch_scroll", scroll] }
        if let tz = env["BL_SCRUB_TZ"] { app.launchEnvironment["TZ"] = tz }
        app.launch()

        let chart = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == %@", "Win probability over time"))
            .firstMatch
        XCTAssertTrue(chart.waitForExistence(timeout: UITestLaunch.launchTimeout + UITestLaunch.contentTimeout),
                      "the game chart never appeared on \(route) — nothing to scrub")
        // `-launch_scroll` moves the page LaunchRig.scrollDelay (8 s) after the
        // route; a drag before then lands on a page still in motion.
        if env["BL_SCRUB_SCROLL"] != nil { Thread.sleep(forTimeInterval: 12) }
        XCTAssertTrue(chart.isHittable, "chart is on the page but not under a finger")

        for x in stops {
            // The camera script keys its frames off these lines.
            print("SCRUB-STOP x=\(x) hold=\(hold) at=\(ISO8601DateFormatter().string(from: Date()))")
            // A SHORT lead-in at default speed: `.slow` over 4% of the plot is
            // seconds of travel, and a frame taken mid-travel photographs some
            // other minute than the stop. The hold is where the camera works.
            let from = chart.coordinate(withNormalizedOffset: CGVector(dx: max(x - 0.015, 0.02), dy: 0.55))
            let to = chart.coordinate(withNormalizedOffset: CGVector(dx: x, dy: 0.55))
            from.press(forDuration: 0.5, thenDragTo: to, withVelocity: .default, thenHoldForDuration: hold)
        }
        XCTAssertTrue(chart.exists, "the page left the chart during the scrub")
    }
}
