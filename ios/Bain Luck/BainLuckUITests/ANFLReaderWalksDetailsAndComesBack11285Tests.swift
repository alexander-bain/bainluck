import XCTest

/// #11285 — the NFL full-size reader, walked through its real controls only:
/// Open story from the page's opener, Next card and a sideways swipe with the
/// pager agreeing, the selected line moved with Next line, a vertical scroll to
/// that line's readout at the largest text size, Details showing that card's own
/// original row, Done keeping the card and the line, and Back landing on the
/// same game at the same place in the page.
///
/// `ANFLReaderKeepsItsCardThroughARotation11060Tests` already walks Open story,
/// Previous card, rotation and Back. This covers what it never touches:
/// Next card, a swipe, Details, Done, and reaching the readout by scrolling.
/// Nothing here sets state directly; every step is a tap or a swipe.
///
/// Needs a real NFL game page with at least two story cards, passed in:
///
///     TEST_RUNNER_BL_UITEST_NFL_EVENT=14780563 xcodebuild … -scheme BainLuckUITests \
///       -only-testing:BainLuckUITests/ANFLReaderWalksDetailsAndComesBack11285Tests test
///
/// Without it the tests SKIP and say so; a skip is not a pass.
final class ANFLReaderWalksDetailsAndComesBack11285Tests: XCTestCase {

    private func eventID() throws -> String {
        guard let id = ProcessInfo.processInfo.environment["BL_UITEST_NFL_EVENT"], !id.isEmpty else {
            throw XCTSkip("set BL_UITEST_NFL_EVENT to an NFL game with two or more story cards")
        }
        return id
    }

    private func rail(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Game story cards'")).firstMatch
    }

    /// Is the card named `name` fully inside the screen's width, judged from the
    /// rail's own elements (only the selected card is in that tree)?
    private func cardIsOnScreen(_ app: XCUIApplication, _ name: String) -> (Bool, String) {
        let rail = rail(app)
        guard rail.exists, let snap = try? rail.snapshot() else { return (false, "no reader rail") }
        var frames: [CGRect] = []
        func visit(_ node: XCUIElementSnapshot) {
            if node.label.contains(name), node.frame.width > 0 { frames.append(node.frame) }
            node.children.forEach(visit)
        }
        visit(snap)
        let width = app.frame.width
        guard let frame = frames.min(by: { $0.width < $1.width }) else { return (false, "'\(name)' not in the rail") }
        return (frame.minX >= -1 && frame.maxX <= width + 1, "\(frame) on a \(width)-wide screen")
    }

    /// The selected line's readout on the card on screen: the button whose
    /// verdict ends "details" (expanded cards only).
    private func readout(_ app: XCUIApplication) -> XCUIElement {
        rail(app).buttons.matching(NSPredicate(format: "label CONTAINS[c] 'details'")).firstMatch
    }

    /// A screenshot written where the operator can open it (the simulator
    /// shares the host's /tmp), named for the step.
    private func shot(_ name: String, large: Bool) {
        let dir = URL(fileURLWithPath: "/tmp/native-reader-walk-shots")
        try? FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        let url = dir.appendingPathComponent("\(large ? "axxxxl" : "large")-\(name).png")
        try? XCUIScreen.main.screenshot().pngRepresentation.write(to: url)
    }

    private func threshold(_ label: String) -> String {
        label.components(separatedBy: " · ").first ?? label
    }

    private func walk(extra: [String], large: Bool) throws {
        let id = try eventID()
        XCUIDevice.shared.orientation = .portrait
        let app = UITestLaunch.launchApp(extra: ["-launch_route", "bainluck://events/\(id)"] + extra)
        let opens = app.buttons.matching(identifier: "story-card-open")
        var swipes = 0
        while !(opens.firstMatch.exists && opens.firstMatch.isHittable) && swipes < 25 {
            app.swipeUp(velocity: .slow); swipes += 1
        }
        // A live page adds its story cards as their rows arrive: wait for the
        // deck to hold two before reading it.
        let deadline = Date().addingTimeInterval(20)
        while opens.count < 2 && Date() < deadline { sleep(1) }
        // Keep the openers out of the floating tab bar's band (`isHittable`
        // ignores it), with short drags, so the page position measured below is
        // the one the tap starts from — XCUITest scrolls a non-hittable target
        // into view on its own, which would move the page under the baseline.
        var nudges = 0
        while opens.firstMatch.frame.minY > app.frame.height * 0.55 && nudges < 8 {
            let x = app.frame.width * 0.5
            let origin = app.coordinate(withNormalizedOffset: .zero)
            origin.withOffset(CGVector(dx: x, dy: app.frame.height * 0.5))
                .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(dx: x, dy: app.frame.height * 0.3)))
            sleep(1); nudges += 1
        }
        sleep(1)
        let ordered = opens.allElementsBoundByIndex.sorted { $0.frame.minX < $1.frame.minX }.map(\.label)
        guard ordered.count >= 2 else {
            throw XCTSkip("event \(id) shows \(ordered.count) story card(s); this needs two")
        }
        let names = ordered.map {
            $0.replacingOccurrences(of: "Open ", with: "").components(separatedBy: " · ").first ?? ""
        }
        XCTAssertNotEqual(names[0], names[1], "control: the first two cards are distinct cards")
        print("READER11285 cards=\(ordered)")

        // 1. Open story from the first card's own opener — nudged by its OWN
        // frame out of the tab bar's band first, so the page position measured
        // here is the one the tap starts from (r1/r5: a tap on a non-hittable
        // opener let XCUITest scroll the page before the baseline was used).
        let opener = app.buttons[ordered[0]]
        var lifts = 0
        while (!opener.isHittable || opener.frame.maxY > app.frame.height * 0.8) && lifts < 8 {
            let x = app.frame.width * 0.5
            let origin = app.coordinate(withNormalizedOffset: .zero)
            origin.withOffset(CGVector(dx: x, dy: app.frame.height * 0.5))
                .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(dx: x, dy: app.frame.height * 0.35)))
            sleep(1); lifts += 1
        }
        XCTAssertTrue(opener.isHittable && opener.frame.maxY <= app.frame.height * 0.8,
                      "the first card's opener is on screen, clear of the tab bar — \(opener.frame)")
        let pageY = opener.frame.minY
        opener.tap()
        let back = app.buttons["Back to the game"]
        XCTAssertTrue(back.waitForExistence(timeout: 10), "Open story opens the reader")
        sleep(1); shot("1-opened", large: large)
        let position = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Card '")).firstMatch
        let count = ordered.count
        XCTAssertEqual(position.label, "Card 1 of \(count)", "the reader opens on the card tapped")
        let first = cardIsOnScreen(app, names[0])
        XCTAssertTrue(first.0, "the opened card is on screen — \(first.1)")

        // 2. Next card: the pager and the card on screen move together.
        app.buttons["Next card"].tap()
        sleep(1)
        XCTAssertEqual(position.label, "Card 2 of \(count)", "Next card advances the pager")
        let second = cardIsOnScreen(app, names[1])
        XCTAssertTrue(second.0, "Next card shows the second card — \(second.1)")
        XCTAssertFalse(cardIsOnScreen(app, names[0]).0, "the first card has left the rail's selection")

        // 3. A sideways swipe on the rail, back and forth; the pager follows.
        rail(app).swipeRight()
        sleep(2)
        XCTAssertEqual(position.label, "Card 1 of \(count)", "a swipe right moves the pager back")
        let swipedBack = cardIsOnScreen(app, names[0])
        XCTAssertTrue(swipedBack.0, "a swipe right shows the first card — \(swipedBack.1)")
        rail(app).swipeLeft()
        sleep(2)
        XCTAssertEqual(position.label, "Card 2 of \(count)", "a swipe left moves the pager on")
        let swipedOn = cardIsOnScreen(app, names[1])
        XCTAssertTrue(swipedOn.0, "a swipe left shows the second card — \(swipedOn.1)")
        shot("3-swiped-on", large: large)

        // 4. Reach the selected readout by scrolling the card itself.
        let line = readout(app)
        let hittableBeforeScroll = line.exists && line.isHittable
        var scrolls = 0
        while !(line.exists && line.isHittable) && scrolls < 8 {
            rail(app).swipeUp(velocity: .slow); scrolls += 1
        }
        print("READER11285 readout large=\(large) hittableBeforeScroll=\(hittableBeforeScroll) scrolls=\(scrolls) frame=\(line.frame)")
        XCTAssertTrue(line.exists && line.isHittable,
                      "the second card's selected readout is reachable by scrolling the card (\(names[1]))")
        shot("4-readout-reached", large: large)

        // 5. Move the line, so Done has a non-default threshold to keep.
        let before = line.label
        let nextLine = rail(app).buttons["Next line"]
        let previousLine = rail(app).buttons["Previous line"]
        (nextLine.isEnabled ? nextLine : previousLine).tap()
        sleep(1)
        let moved = readout(app).label
        XCTAssertNotEqual(threshold(moved), threshold(before), "Next/Previous line moves the selected threshold")
        XCTAssertEqual(position.label, "Card 2 of \(count)", "moving the line keeps the card")
        shot("5-line-moved", large: large)
        print("READER11285 before-details large=\(large) card2 \(cardIsOnScreen(app, names[1]).1)")

        // 6. Details: the original row behind THIS card's selected line.
        readout(app).tap()
        let title = app.navigationBars["Line details"]
        XCTAssertTrue(title.waitForExistence(timeout: 5), "tapping the readout opens Details")
        sleep(1); shot("6-details", large: large)
        // The headline is the original row's outcome: "<player>: <line>".
        let sheet = app.collectionViews.allElementsBoundByIndex.first {
            $0.staticTexts.matching(NSPredicate(format: "label BEGINSWITH %@", names[1])).firstMatch.exists
        }
        print("READER11285 details large=\(large) tree:\n\(app.debugDescription.suffix(9000))")
        XCTAssertNotNil(sheet, "Details names the selected card's player (\(names[1]))")
        if let sheet {
            let wanted = threshold(moved)
            let shown = sheet.descendants(matching: .any).matching(NSPredicate(
                format: "label == %@ OR value == %@ OR label ENDSWITH %@", wanted, wanted, ", \(wanted)")).firstMatch
            XCTAssertTrue(shown.exists, "Details shows the moved line \(wanted)")
            XCTAssertFalse(sheet.staticTexts["This line is no longer offered."].exists, "Details found its original row")
        }

        // 7. Done returns to the same card with the same line selected.
        app.buttons["Done"].tap()
        XCTAssertTrue(title.waitForNonExistence(timeout: 5), "Done closes Details")
        XCTAssertTrue(back.exists, "Done leaves the reader open")
        sleep(1); shot("7-after-done", large: large)
        print("READER11285 after-done large=\(large) card2 \(cardIsOnScreen(app, names[1]).1)")
        XCTAssertEqual(position.label, "Card 2 of \(count)", "Done keeps the card")
        let kept = cardIsOnScreen(app, names[1])
        XCTAssertTrue(kept.0, "Done keeps the second card on screen — \(kept.1)")
        XCTAssertEqual(threshold(readout(app).label), threshold(moved), "Done keeps the moved threshold")

        // 8. Back: the same game, the deck where the reader left it.
        back.tap()
        XCTAssertTrue(back.waitForNonExistence(timeout: 5), "Back closes the reader")
        sleep(1); shot("8-after-back", large: large)
        let returned = app.buttons[ordered[0]]
        XCTAssertTrue(returned.exists && returned.frame.minX >= -1 && returned.frame.maxX <= app.frame.width + 1,
                      "Back lands on the card the reader was opened from — \(returned.frame)")
        XCTAssertEqual(returned.frame.minY, pageY, accuracy: 24,
                       "Back keeps the page where it was (opener at \(pageY), now \(returned.frame.minY))")
    }

    func testTheReaderWalksNextSwipeDetailsDoneAndBack() throws {
        try walk(extra: [], large: false)
    }

    func testTheSameAtTheLargestTextSizeReachesTheReadoutByScrolling() throws {
        try walk(extra: ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"], large: true)
    }
}
