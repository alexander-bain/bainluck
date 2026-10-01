import XCTest

/// #9408, driven by a finger at the text size on Alex's phone: **tapping Win
/// Probability opens a confidence popup a reader can read top to bottom.**
///
/// Build 30 on Alex's iPhone (IMG2365, CHC vs SD, enlarged text) opened the
/// popup ABOVE the hero, where only ~130pt fit under the navigation bar. The
/// content was pinned to its full height, so it overflowed both edges: the
/// first visible line began mid-sentence, the last was cut in half, and
/// nothing scrolled. A unit render cannot see this — the clip is the
/// presentation's, not the view's — so the guard is a real tap on a real page.
///
/// Knobs (`TEST_RUNNER_` environment):
///   `BL_9408_ROUTE` default `bainluck://events/15320240` (CHC @ SD, Alex's game;
///                   final since 9/30, so the default SKIPS — pass a live game)
///   `BL_9408_SIZE`  default `UICTContentSizeCategoryXXXL` (measured: renders
///                   pixel-identical to Alex's IMG2365 on an iPhone 17 Pro Max)
///   `BL_9408_ALLOW_SCROLL=1` for sizes where the popup cannot fit on screen
final class TheConfidencePopupReadsTopToBottom9408Tests: XCTestCase {
    private var env: [String: String] { ProcessInfo.processInfo.environment }

    /// Always the popup's LAST line: the one build 30 cut in half.
    private static let lastLine = "Signal strength: sources + liquidity + freshness"

    func testEveryLineOfTheConfidencePopupCanBeRead() throws {
        continueAfterFailure = false
        let route = env["BL_9408_ROUTE"] ?? "bainluck://events/15320240"
        let size = env["BL_9408_SIZE"] ?? "UICTContentSizeCategoryXXXL"
        let app = UITestLaunch.launchApp(extra: ["-launch_route", route,
                                                  "-UIPreferredContentSizeCategoryName", size])
        let opener = app.buttons.matching(NSPredicate(
            format: "label BEGINSWITH %@", "Probability confidence and update details")).firstMatch
        guard opener.waitForExistence(timeout: UITestLaunch.launchTimeout + UITestLaunch.contentTimeout) else {
            // The default route rots: Alex's game went final, and a finished
            // game (or a pre-game opening line, #9470) correctly has no Win
            // Probability button. That is a missing precondition, not the
            // defect, so it skips by name (JourneyPreconditions.swift).
            for marker in ["Final", "Opening line"] where app.staticTexts[marker].exists {
                throw XCTSkip("NOT WALKED: \(route) reads '\(marker)', which correctly has no Win "
                    + "Probability button. Set TEST_RUNNER_BL_9408_ROUTE to a game in progress and re-run.")
            }
            return XCTFail("no Win Probability details button on \(route), and the page is neither final nor an opening line")
        }
        opener.tap()

        let last = app.staticTexts[Self.lastLine]
        guard last.waitForExistence(timeout: 10) else {
            throw XCTSkip("NOT WALKED: \(route) opened a popup with no confidence tier, so its last line is absent")
        }
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("popup9408")
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try app.screenshot().pngRepresentation.write(to: dir.appendingPathComponent(size + "-open.png"))
        try app.debugDescription.write(to: dir.appendingPathComponent(size + ".txt"), atomically: true, encoding: .utf8)
        let popover = app.popovers.firstMatch
        XCTAssertTrue(popover.exists, "the details opened, but not as a popover")
        let lines = popover.staticTexts.allElementsBoundByIndex
        print("POPUP9408 size=\(size) popover=\(popover.frame) lines=\(lines.map { "\($0.label)@\($0.frame)" }) evidence=\(dir.path)")
        XCTAssertGreaterThanOrEqual(lines.count, 3, "the popup lost its lines: \(lines.map(\.label))")

        // Build 30's shape exactly: popover (70,100,300,144) around text spanning
        // y 74–257 — the first line began above the popover, the last ran below.
        let box = popover.frame.insetBy(dx: -0.5, dy: -0.5)
        let first = lines[0], lastLabel = lines[lines.count - 1].label
        XCTAssertGreaterThanOrEqual(first.frame.minY, box.minY,
            "the popup opens mid-sentence: '\(first.label)' starts at \(first.frame.minY), above the popover at \(popover.frame)")

        // Where the popup has room it shows every line without scrolling (a
        // 144pt popup that scrolls was the half-fix). `BL_9408_ALLOW_SCROLL=1` is
        // for sizes that cannot fit — at AX5 ONE line is taller than the popover —
        // and there the bottom of the last line must be reachable by swiping.
        guard env["BL_9408_ALLOW_SCROLL"] == "1" else {
            for line in lines {
                XCTAssertTrue(box.contains(line.frame), "'\(line.label)' at \(line.frame) is cut off by the popover at \(popover.frame)")
            }
            return
        }
        for _ in 0..<8 where popover.staticTexts[lastLabel].frame.maxY > box.maxY {
            popover.swipeUp()
        }
        let end = popover.staticTexts[lastLabel]
        try app.screenshot().pngRepresentation.write(to: dir.appendingPathComponent(size + "-scrolled.png"))
        XCTAssertTrue(end.exists && end.frame.maxY <= box.maxY,
                      "'\(lastLabel)' ends at \(end.frame.maxY), below the popover at \(popover.frame), and eight swipes do not reach it")
    }
}
