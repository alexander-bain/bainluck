import XCTest

/// #10830, Alex's October 10 report: "top clickable headers … hard to tap
/// outside the words". On the mounted event page this test taps each control
/// NEAR ITS EDGE — inside the drawn control, away from its word — and reads
/// what the reader would see change:
///
///   1. a player-props team filter third ("Patriots") becomes selected;
///   2. a family pill becomes selected;
///   3. a game-odds ladder line opens its detail sheet ("Game odds");
///   4. the protected-touchdown "Rule" control opens "Participation rule".
///
///   `BL_10830_ROUTE`  default `bainluck://events/14782161` (LV @ NE, Oct 11),
///                     whose served page carries all four. A page without one
///                     of them SKIPS that step by name; a skip is never a pass.
///
/// Not claimed: VoiceOver focus (XCUITest cannot read it) or a physical phone.
final class PaddingEdgeTapsLand10830Tests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = true
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// Scrolls the page until `element` sits in the screen's middle band —
    /// clear of the navigation bar and of the floating tab bar, which
    /// `isHittable` does not account for (the first run's "Patriots" edge tap
    /// at y≈793 landed on the tab bar and left the page) — or gives up.
    @discardableResult
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, swipes: Int = 14) -> Bool {
        let height = app.frame.height
        func placed() -> Bool {
            guard element.exists, element.isHittable else { return false }
            let f = element.frame
            return f.minY > 140 && f.maxY < height * 0.72
        }
        for _ in 0..<swipes {
            if placed() { return true }
            if element.exists, element.frame.minY <= 140 {
                app.swipeDown(velocity: .slow)
            } else {
                app.swipeUp(velocity: .slow)
            }
        }
        return placed()
    }

    /// A point inside `element` near its leading edge (x) and top (y): on the
    /// padding, not the word.
    private func edgeTap(_ element: XCUIElement, x: CGFloat = 0.06, y: CGFloat = 0.15) {
        element.coordinate(withNormalizedOffset: CGVector(dx: x, dy: y)).tap()
    }

    private func closeSheet(_ app: XCUIApplication) {
        let close = app.buttons["Close"]
        if close.waitForExistence(timeout: 3) { close.tap() }
    }

    func testEdgeTapsOnTheCompactMarketControlsLand() throws {
        let route = ProcessInfo.processInfo.environment["BL_10830_ROUTE"] ?? "bainluck://events/14782161"
        let app = UITestLaunch.launchApp(extra: ["-launch_route", route])
        XCTAssertTrue(app.staticTexts["LV vs NE"].waitForExistence(timeout: UITestLaunch.launchTimeout)
                      || app.navigationBars.firstMatch.waitForExistence(timeout: 5), "The event page never drew.")
        var walked: [String] = []

        // 1 — the team filter third, tapped 6% in from its leading edge.
        let team = app.buttons.matching(identifier: "props-team-filter").element(boundBy: 1)
        if team.waitForExistence(timeout: UITestLaunch.contentTimeout), reveal(team, in: app) {
            let label = team.label
            XCTAssertFalse(team.isSelected, "control: '\(label)' starts unselected")
            print("10830E team frame=\(team.frame) label=\(label)")
            edgeTap(team)
            XCTAssertTrue(team.isSelected, "an edge tap on the '\(label)' filter did not select it")
            shot(app, "10830E-1-team-filter-edge")
            // Put it back so step 2 sees every family.
            let all = app.buttons.matching(identifier: "props-team-filter").element(boundBy: 0)
            edgeTap(all)
            XCTAssertTrue(all.isSelected, "an edge tap on 'All' did not select it")
            walked.append("team-filter")
        } else {
            print("10830E SKIPPED team-filter: no props team filter on \(route)")
        }

        // 2 — a family pill that is not the active one.
        let pills = app.buttons.matching(identifier: "market-browser-pill")
        if pills.firstMatch.waitForExistence(timeout: 5) {
            let pill = pills.allElementsBoundByIndex.first { $0.isHittable && !$0.isSelected }
            if let pill, reveal(pill, in: app) {
                let label = pill.label
                print("10830E pill frame=\(pill.frame) label=\(label)")
                edgeTap(pill, x: 0.08, y: 0.12)
                XCTAssertTrue(pill.isSelected, "an edge tap on the '\(label)' pill did not select it")
                shot(app, "10830E-2-pill-edge")
                walked.append("pill")
            } else {
                print("10830E SKIPPED pill: no unselected hittable pill on screen")
            }
        }

        // 3 — a game-odds ladder line, tapped at its far trailing edge.
        let line = app.buttons.matching(NSPredicate(format: "label MATCHES %@", "[0-9]+\\+ points, .+")).firstMatch
        if line.waitForExistence(timeout: 5), reveal(line, in: app, swipes: 30) {
            print("10830E line frame=\(line.frame) label=\(line.label)")
            edgeTap(line, x: 0.97, y: 0.12)
            let title = app.navigationBars["Game odds"]
            XCTAssertTrue(title.waitForExistence(timeout: 5), "an edge tap on '\(line.label)' opened no Game odds detail")
            shot(app, "10830E-3-ladder-line-edge-detail")
            closeSheet(app)
            walked.append("ladder-line")
        } else {
            print("10830E SKIPPED ladder-line: no 'N+ points' game-odds line on \(route)")
        }

        // 4 — the protected-touchdown rule control. Step 2 may have left the
        // browser on another family, so the protected one is chosen first.
        let protectedPill = app.buttons.matching(identifier: "market-browser-chip")
            .matching(NSPredicate(format: "label == %@", "Touchdowns scored, Participation rule")).firstMatch
        if protectedPill.waitForExistence(timeout: 3) || reveal(protectedPill, in: app, swipes: 20) {
            if reveal(protectedPill, in: app, swipes: 20) { protectedPill.tap() }
        }
        let rule = app.buttons["Participation rule"].firstMatch
        if rule.exists || rule.waitForExistence(timeout: 3) {
            app.swipeDown(velocity: .fast); app.swipeDown(velocity: .fast); app.swipeDown(velocity: .fast)
            if reveal(rule, in: app, swipes: 30) {
                print("10830E rule frame=\(rule.frame)")
                edgeTap(rule, x: 0.1, y: 0.15)
                XCTAssertTrue(app.navigationBars["Participation rule"].waitForExistence(timeout: 5),
                              "an edge tap on the rule control opened no rule sheet")
                shot(app, "10830E-4-rule-sheet")
                closeSheet(app)
                walked.append("rule")
            }
        } else {
            print("10830E SKIPPED rule: no protected-touchdown rule control on \(route)")
        }
        print("10830E WALKED \(walked.joined(separator: ","))")
    }
}
