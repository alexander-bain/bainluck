import XCTest

/// #10238 acceptance, the interaction clause: on the mounted page a reader opens
/// one exact Game or Series option, reads its question, option and sources, and
/// Close puts the page back where it was — the same option still drawn at the
/// same place, the page at the same scroll — at the default size and at the
/// accessibility sizes (the renderer switches to a full-label list there).
///
/// The sections exist on any game whose server carries the typed matrices, so
/// the route is an argument:
///
///   `BL_10238_ROUTE`  default `bainluck://events/15322539` (NYY @ TB ALDS G1,
///                     finished, Game questions above an open Series)
///   `BL_10238_SIZE`   a `UIContentSizeCategory` raw value, e.g.
///                     `UICTContentSizeCategoryAccessibilityL` (AX3)
///
/// A section the page does not draw is NOT WALKED for that scope (logged), never
/// a pass; both absent is a skip. VoiceOver focus return is not readable from
/// XCUITest — the runner sees no accessibility-focus state — so this test does
/// not claim it.
final class AGameOrSeriesQuestionClosesBackToItsPlace10238Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// "<question>, <option>, <value>" — the option button's own spoken label.
    private static let optionPredicate = NSPredicate(
        format: "label MATCHES %@", ".+, .+, ([<>]?[0-9.]+%|Won|Lost|Unavailable)")

    private func texts(_ app: XCUIApplication) -> [String] {
        guard let root = try? app.snapshot() else { return [] }
        var out: [String] = []
        func walk(_ node: XCUIElementSnapshot) {
            if node.elementType == .staticText { out.append(node.label) }
            node.children.forEach(walk)
        }
        walk(root)
        return out
    }

    /// Scrolls the page until `header` sits in the upper fifth of the window.
    private func reach(_ header: XCUIElement, in app: XCUIApplication) -> Bool {
        let page = app.scrollViews.firstMatch
        let window = app.windows.firstMatch.frame
        for _ in 0..<40 {
            let y = header.exists ? header.frame.minY : .infinity
            if y > window.minY + 110, y < window.minY + window.height * 0.2 { return true }
            if y <= window.minY + 110 {
                page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
                    .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.58)))
            } else if y < window.maxY {
                page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.7))
                    .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)))
            } else {
                page.swipeUp(velocity: .slow)
            }
        }
        return false
    }

    func testAGameOrSeriesOptionDetailClosesBackToTheSameOptionAndScroll() throws {
        let env = ProcessInfo.processInfo.environment
        let route = env["BL_10238_ROUTE"] ?? "bainluck://events/15322539"
        let size = env["BL_10238_SIZE"] ?? ""
        var extra = ["-launch_route", route]
        if !size.isEmpty { extra += ["-UIPreferredContentSizeCategoryName", size] }
        let app = UITestLaunch.launchApp(extra: extra)
        let sizeName = size.isEmpty ? "default" : size
        print("10238_PLAN route=\(route) size=\(sizeName)")
        XCTAssertTrue(app.scrollViews.firstMatch.waitForExistence(timeout: UITestLaunch.contentTimeout),
                      "The event page never drew.")

        var walked: [String] = []
        for title in ["Game questions", "Series questions"] {
            let header = app.staticTexts[title]
            guard reach(header, in: app) else {
                print("10238_NOT_WALKED section='\(title)' — not drawn after a bounded page walk")
                continue
            }
            let band = JourneyPrecondition.reachableBand(app)
            let options = app.buttons.matching(Self.optionPredicate).allElementsBoundByIndex
                .filter { $0.isHittable && $0.frame.minY > header.frame.maxY && band.contains($0.frame) }
            // The lowest reachable option, so a later row is what must return.
            guard let target = options.max(by: { $0.frame.minY < $1.frame.minY }) else {
                XCTFail("'\(title)' is drawn but no option button is reachable under it.")
                return
            }
            let label = target.label
            let parts = label.components(separatedBy: ", ")
            let question = parts.dropLast(2).joined(separator: ", ")
            let option = parts[parts.count - 2]
            let headerY = header.frame.minY
            let targetFrame = target.frame
            print("10238_BEFORE section='\(title)' target='\(label)' frame=\(targetFrame) headerY=\(headerY) reachable=\(options.count)")
            shot(app, "10238-\(title)-01-before")

            target.tap()
            let close = app.buttons["Close"]
            XCTAssertTrue(close.waitForExistence(timeout: 5), "Tapping '\(label)' opened no detail with a Close button.")
            XCTAssertTrue(app.navigationBars[title].waitForExistence(timeout: 3),
                          "The detail is not titled '\(title)'; bars: \(app.navigationBars.allElementsBoundByIndex.map(\.identifier)).")
            let detail = texts(app)
            print("10238_DETAIL section='\(title)' texts=\(detail.prefix(14))")
            XCTAssertTrue(detail.contains(question), "The detail does not name the question '\(question)'.")
            XCTAssertTrue(detail.contains(option), "The detail does not name the option '\(option)'.")
            let sources = detail.contains("Sources") || detail.contains("SOURCES") || detail.contains("This question is unavailable")
            XCTAssertTrue(sources, "The detail shows neither its sources nor an honest unavailable state.")
            shot(app, "10238-\(title)-02-detail")

            close.tap()
            expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: close)
            waitForExpectations(timeout: 5)
            sleep(1)
            shot(app, "10238-\(title)-03-after-close")

            let after = app.buttons[label]
            print("10238_AFTER section='\(title)' exists=\(after.exists) frame=\(after.frame) headerY=\(header.frame.minY)")
            XCTAssertTrue(header.exists, "The '\(title)' header is gone after Close.")
            XCTAssertTrue(after.exists, "The opened option '\(label)' is no longer drawn after Close.")
            XCTAssertEqual(header.frame.minY, headerY, accuracy: 2, "Page scroll moved across the detail.")
            XCTAssertEqual(after.frame.minY, targetFrame.minY, accuracy: 2, "The opened option moved across the detail.")
            XCTAssertEqual(after.frame.minX, targetFrame.minX, accuracy: 2, "The opened option moved sideways across the detail.")
            walked.append(title)
            print("10238_PASS section='\(title)' option='\(label)'")
        }
        if walked.isEmpty {
            throw XCTSkip("NOT WALKED: '\(route)' drew neither Game nor Series questions.")
        }
        print("10238_RECEIPT PASS route=\(route) size=\(sizeName) sections=\(walked)")
    }
}
