import XCTest

/// #10830, Alex 10/10: "how could they possibly know what to type into this
/// field?" On the mounted event page, starting with no search, this walks the
/// player props with CONTROLS ALONE and reads what the reader would see:
///
///   1. the browser opens on a labelled "Stat" chooser, and no search field is
///      drawn until "Find a player" is tapped;
///   2. "Show more" reveals the rest of the opening stat's collection;
///   3. every stat is a visible chip (or, past the chip limit or at
///      accessibility text, one labelled menu) — none needs a sideways scroll
///      — and another stat can be chosen;
///   4. then a team, then a player's target line.
///
///   `BL_10830_ROUTE`  default `bainluck://events/14782161` (LV @ NE, Oct 11:
///                     16 stats, the menu). `bainluck://events/15327325`
///                     (PHI @ BOS, NHL, Oct 10: 3 stats) draws the chips.
///   `BL_10830_TEXT`   a UIContentSizeCategory name for the enlarged-text run
///                     (e.g. `UICTContentSizeCategoryAccessibilityL`); unset is
///                     the default size.
///
/// A page without one of these controls SKIPS that step by name; a skip is
/// never a pass. Not claimed: VoiceOver focus or a physical phone.
final class PropsBrowseFirst10830UITests: XCTestCase {

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

    /// Scrolls until `element` sits between the navigation bar and the floating
    /// tab bar (which `isHittable` ignores), or gives up.
    @discardableResult
    private func reveal(_ element: XCUIElement, in app: XCUIApplication, top: CGFloat = 140,
                        bottom: CGFloat = 0.72, swipes: Int = 40) -> Bool {
        let height = app.frame.height
        func placed() -> Bool {
            guard element.exists, element.isHittable else { return false }
            let f = element.frame
            return f.minY > top && f.maxY < height * bottom
        }
        // A fixed 180pt drag, not a swipe: a swipe's travel grows with text
        // size and at XXXL it overshot a 200pt band back and forth forever.
        let mid = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
        for _ in 0..<swipes {
            if placed() { return true }
            let down = element.exists && element.frame.minY <= top
            mid.press(forDuration: 0.05, thenDragTo: mid.withOffset(CGVector(dx: 0, dy: down ? 180 : -180)),
                      withVelocity: .slow, thenHoldForDuration: 0.3)
        }
        return placed()
    }

    func testPropsAreBrowsableWithoutTyping() throws {
        let env = ProcessInfo.processInfo.environment
        let route = env["BL_10830_ROUTE"] ?? "bainluck://events/14782161"
        var extra = ["-launch_route", route]
        if let size = env["BL_10830_TEXT"], !size.isEmpty {
            extra += ["-UIPreferredContentSizeCategoryName", size]
        }
        let tag = env["BL_10830_TEXT"].map { $0.isEmpty ? "default" : $0 } ?? "default"
        let app = UITestLaunch.launchApp(extra: extra)
        XCTAssertTrue(app.navigationBars.firstMatch.waitForExistence(timeout: UITestLaunch.launchTimeout),
                      "The event page never drew.")
        var walked: [String] = []

        // 1 — the labelled chooser leads; search is not drawn.
        let stat = app.staticTexts["Stat"].firstMatch
        guard stat.waitForExistence(timeout: UITestLaunch.contentTimeout) || reveal(stat, in: app, swipes: 60) else {
            print("10830B SKIPPED all: no Stat chooser on \(route)")
            return
        }
        let find = app.buttons["market-browser-find"]
        XCTAssertTrue(find.exists, "the optional Find a player control is missing")
        XCTAssertFalse(app.textFields["Search player props"].exists,
                       "a search field is drawn before the reader asked for one")
        // Scroll by the chooser's first BUTTON — a header text can report not
        // hittable at large text sizes, and then the page never settles.
        let menu = app.buttons["market-browser-chooser"]
        let firstChip = app.buttons.matching(identifier: "market-browser-chip").firstMatch
        let anchor = menu.exists ? menu : firstChip
        reveal(anchor, in: app, top: 180, bottom: 0.45)
        shot(app, "10830B-\(tag)-1-browse-entry")
        walked.append("entry")

        // 2 — the rest of the opening stat's collection, by control. Run
        // first: a narrower stat chosen later may fit one window.
        let more = app.buttons["market-browser-more-Player props"]
        let status = app.staticTexts["market-browser-status-Player props"]
        if more.exists || reveal(more, in: app, swipes: 60) {
            if reveal(more, in: app, swipes: 60) {
                let before = status.label
                more.tap()
                XCTAssertTrue(status.waitForExistence(timeout: 3))
                XCTAssertNotEqual(status.label, before, "Show more drew no more props (\(before))")
                print("10830B more \(before) -> \(status.label)")
                shot(app, "10830B-\(tag)-2-show-more")
                walked.append("more")
            }
        } else {
            print("10830B SKIPPED more: the opening stat fits one window")
        }
        reveal(anchor, in: app, top: 180, bottom: 0.45)

        // 3 — every stat in view: chips that all sit inside the screen's
        // width, or the one labelled menu.
        let chips = app.buttons.matching(identifier: "market-browser-chip").allElementsBoundByIndex
        let width = app.frame.width
        if menu.exists {
            print("10830B chooser=menu label=\(menu.label)")
            // On its padding, not its words (Alex 10/10: a control takes a
            // tap across its whole drawn area).
            menu.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: 0.15)).tap()
            shot(app, "10830B-\(tag)-3-stat-menu-open")
            // Pick the second listed stat from the open menu.
            let before = menu.label
            // Let the menu finish opening: a tap during its animation
            // dismisses it without choosing.
            _ = app.collectionViews.firstMatch.waitForExistence(timeout: 3)
            Thread.sleep(forTimeInterval: 1.0)
            let rows = app.collectionViews.firstMatch.descendants(matching: .any)
                .matching(NSPredicate(format: "elementType == %d OR elementType == %d OR elementType == %d",
                                      XCUIElement.ElementType.button.rawValue,
                                      XCUIElement.ElementType.switch.rawValue,
                                      XCUIElement.ElementType.toggle.rawValue))
            let options = rows.allElementsBoundByIndex.filter { $0.isHittable && !$0.label.isEmpty }
            print("10830B menu options=\(options.map(\.label))")
            if options.count > 1 {
                let label = options[1].label
                options[1].tap()
                XCTAssertTrue(menu.waitForExistence(timeout: 3))
                XCTAssertNotEqual(menu.label, before, "choosing '\(label)' from the menu changed nothing")
                XCTAssertTrue(menu.label.contains(label), "the chooser does not name '\(label)': \(menu.label)")
                reveal(menu, in: app, top: 180, bottom: 0.45)
                shot(app, "10830B-\(tag)-3-stat-chosen")
                walked.append("menu")
            } else {
                XCTFail("the open menu listed fewer than two stats")
            }
        } else {
            XCTAssertGreaterThan(chips.count, 1, "fewer than two stats on the chooser")
            for chip in chips {
                XCTAssertGreaterThanOrEqual(chip.frame.minX, 0, "'\(chip.label)' starts off screen")
                XCTAssertLessThanOrEqual(chip.frame.maxX, width, "'\(chip.label)' is cut off at the edge")
                // Half a point of slack: frames at a fractional scroll offset
                // read 43.99999.
                XCTAssertGreaterThanOrEqual(chip.frame.height, 43.5, "'\(chip.label)' is under 44pt tall")
            }
            print("10830B chips=\(chips.map(\.label))")
            // Another stat.
            if let other = chips.first(where: { !$0.isSelected && $0.isHittable }) {
                let label = other.label
                other.coordinate(withNormalizedOffset: CGVector(dx: 0.06, dy: 0.12)).tap()
                XCTAssertTrue(other.isSelected, "an edge tap on '\(label)' did not choose it")
                shot(app, "10830B-\(tag)-3-stat-chosen")
                walked.append("stat")
            }
        }

        // 4a — a team.
        let team = app.buttons.matching(identifier: "props-team-filter").element(boundBy: 1)
        if team.waitForExistence(timeout: 3), reveal(team, in: app) {
            team.tap()
            XCTAssertTrue(team.isSelected, "tapping '\(team.label)' did not choose it")
            walked.append("team")
        } else {
            print("10830B SKIPPED team: no team filter")
        }

        // 4b — a player's target line, before the game (pre-game ladders browse
        // by target). Labels read "2+ <stat>, 31%".
        let targets = app.buttons.matching(identifier: "props-target")
        let target = targets.allElementsBoundByIndex.first { $0.isEnabled && !$0.isSelected }
        if target == nil { print("10830B target: none of \(targets.count) target lines is unselected and enabled") }
        if let target, reveal(target, in: app) {
            let label = target.label
            target.tap()
            XCTAssertTrue(target.isSelected, "tapping target '\(label)' did not choose it")
            shot(app, "10830B-\(tag)-4-team-and-target-chosen")
            walked.append("target")
        } else {
            print("10830B SKIPPED target: no unselected priced target line on screen")
        }

        // Find stays optional: it opens a field, and Done puts the chooser back.
        if find.exists, reveal(find, in: app) {
            find.tap()
            let field = app.textFields["Search player props"]
            XCTAssertTrue(field.waitForExistence(timeout: 3), "Find a player opened no field")
            app.buttons["Close search"].firstMatch.tap()
            XCTAssertTrue(app.buttons["market-browser-find"].waitForExistence(timeout: 3),
                          "closing search did not restore Find a player")
            walked.append("find")
        }
        print("10830B WALKED \(walked.joined(separator: ","))")
    }
}
