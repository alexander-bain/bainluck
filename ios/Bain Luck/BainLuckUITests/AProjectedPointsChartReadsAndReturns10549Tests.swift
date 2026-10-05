import XCTest

/// #10549 on the mounted page: a finished NFL game shows ONE projected
/// final-points chart in place of the Score Differential card, with no
/// inspection slider; its sportsbook is explained under "How to read this";
/// the chart speaks its game-state markers; and full screen returns to the
/// same place with Done.
///
/// The assertions are necessary, not sufficient: whether the plot reads at a
/// glance (marker chips clear of the lines, two teams told apart) is in the
/// saved frames, which a person reads.
///
///   `BL_10549_ROUTE`  default `bainluck://events/14781135` (BUF 26 – NE 29,
///                     final, five observed game-state markers)
///   `BL_10549_SIZE`   a `UIContentSizeCategory` raw value, e.g.
///                     `UICTContentSizeCategoryAccessibilityXXXL`
///   `BL_10549_OUT`    directory for the frames (default /tmp/n10549-shots)
///
/// A page that mounts no projected chart is NOT WALKED (skip), never a pass.
final class AProjectedPointsChartReadsAndReturns10549Tests: XCTestCase {

    private var outDir = ""
    private var mode = "default"
    private var frameNo = 0

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        outDir = env["BL_10549_OUT"] ?? "/tmp/n10549-shots"
        mode = (env["BL_10549_SIZE"] ?? "").isEmpty ? "default" : "sized"
        try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        frameNo += 1
        let shot = app.screenshot()
        let file = String(format: "%@/%@-%02d-%@.png", outDir, mode, frameNo, name)
        try? shot.pngRepresentation.write(to: URL(fileURLWithPath: file))
        print("N10549_FRAME \(file)")
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// Drag the page until `element`'s top sits between `low` and `high` of the window.
    private func bring(_ element: XCUIElement, in page: XCUIElement, window: CGRect,
                       low: CGFloat, high: CGFloat) -> Bool {
        for _ in 0..<40 {
            let y = element.exists ? element.frame.minY : .infinity
            if y > window.minY + window.height * low, y < window.minY + window.height * high { return true }
            if y <= window.minY + window.height * low {
                page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
                    .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.6)))
            } else if y < window.maxY {
                page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.7))
                    .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)))
            } else {
                page.swipeUp(velocity: .slow)
            }
        }
        return false
    }

    func testOneChartNoSliderExplainedSourceAndFullScreenReturns() throws {
        let env = ProcessInfo.processInfo.environment
        let route = env["BL_10549_ROUTE"] ?? "bainluck://events/14781135"
        let size = env["BL_10549_SIZE"] ?? ""
        var extra = ["-launch_route", route]
        if !size.isEmpty { extra += ["-UIPreferredContentSizeCategoryName", size] }
        let app = UITestLaunch.launchApp(extra: extra)
        let window = app.windows.firstMatch.frame
        print("N10549_PLAN size=\(size.isEmpty ? "default" : size) route=\(route) window=\(window)")

        let page = app.scrollViews.firstMatch
        XCTAssertTrue(page.waitForExistence(timeout: UITestLaunch.contentTimeout), "The event page never drew.")
        sleep(3)

        // 1. The heading, as a reader scrolls to it.
        let heading = app.staticTexts["Projected final points"]
        var sawDifferential = false
        for _ in 0..<40 where !heading.exists {
            sawDifferential = sawDifferential || app.staticTexts["Score Differential"].exists
            page.swipeUp(velocity: .slow)
        }
        guard heading.exists else { throw XCTSkip("NOT WALKED: \(route) mounts no projected chart.") }
        XCTAssertTrue(bring(heading, in: page, window: window, low: 0.12, high: 0.2),
                      "The projected heading never reached the top of the screen.")
        sleep(1)
        sawDifferential = sawDifferential || app.staticTexts["Score Differential"].exists
        XCTAssertFalse(sawDifferential, "The Score Differential card drew beside the projection it should give way to.")
        XCTAssertFalse(app.sliders["Inspect recorded projections and scores"].exists, "The inspection slider is back.")
        shot(app, "inline")

        // 2. The chart speaks its markers.
        let chart = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label BEGINSWITH %@", "Projected final points chart")).firstMatch
        XCTAssertTrue(chart.waitForExistence(timeout: 5), "The plot has no spoken element.")
        let spoken = (chart.value as? String) ?? ""
        print("N10549_SPOKEN label='\(chart.label)' value='\(spoken)'")
        XCTAssertTrue(spoken.hasPrefix("Game state marked on the chart: "), "The plot does not speak its markers: '\(spoken)'.")

        // 3. How to read this names the one sportsbook.
        let details = app.buttons["How to read this"]
        XCTAssertTrue(bring(details, in: page, window: window, low: 0.35, high: 0.6), "No 'How to read this' in reach.")
        details.tap()
        let source = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", "Projection source: ")).firstMatch
        XCTAssertTrue(source.waitForExistence(timeout: 5), "'How to read this' opened no source explanation.")
        print("N10549_SOURCE '\(source.label)'")
        sleep(1)
        shot(app, "how-to-read-this")

        // 4. Full screen, then Done returns to the same place.
        XCTAssertTrue(bring(heading, in: page, window: window, low: 0.12, high: 0.2))
        sleep(1)
        let headingY = heading.frame.minY
        let expand = app.buttons["Expand projected final points"]
        XCTAssertTrue(expand.waitForExistence(timeout: 5), "No expand control.")
        expand.tap()
        let done = app.buttons["Done"]
        XCTAssertTrue(done.waitForExistence(timeout: 5), "Expand opened nothing with Done.")
        sleep(2)
        shot(app, "expanded")
        app.scrollViews.firstMatch.swipeUp(velocity: .slow)
        sleep(1)
        shot(app, "expanded-lower")
        done.tap()
        XCTAssertTrue(done.waitForNonExistence(timeout: 5), "Done did not close full screen.")
        sleep(2)
        print("N10549_RETURN headingY=\(heading.frame.minY) (before \(headingY))")
        XCTAssertEqual(heading.frame.minY, headingY, accuracy: 1, "Done returned to a different place on the page.")
        shot(app, "after-done")
    }
}
