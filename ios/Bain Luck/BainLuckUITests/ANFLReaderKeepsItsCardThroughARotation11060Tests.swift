import XCTest

/// #11060 — the NFL full-size reader keeps the card the reader is on when the
/// phone rotates, and Back lands on the card it was opened from.
///
/// Seen on build 55 (SEA@DEN 14780559): on card 2, rotate — the pager still said
/// "2 of 2" while the rail showed card 1; and after a rotation under the reader,
/// Back left the page deck on a neighbour of the card it was opened from. The pager LABEL stayed right throughout, so
/// this asserts where the named card actually IS on screen, read from one
/// snapshot of the reader's own rail (the page behind the cover carries the same
/// names in its props list).
///
/// Needs a real NFL game page with at least two story cards. Fixtures change
/// weekly, so the event is passed in, never hardcoded:
///
///     TEST_RUNNER_BL_UITEST_NFL_EVENT=14780559 xcodebuild … -scheme BainLuckUITests \
///       -only-testing:BainLuckUITests/ANFLReaderKeepsItsCardThroughARotation11060Tests test
///
/// (`TEST_RUNNER_` is xcodebuild's channel into the runner's environment.) Without
/// it the tests SKIP and say so; a skip is not a pass.
final class ANFLReaderKeepsItsCardThroughARotation11060Tests: XCTestCase {

    override func tearDown() {
        XCUIDevice.shared.orientation = .portrait
        super.tearDown()
    }

    private func eventID() throws -> String {
        guard let id = ProcessInfo.processInfo.environment["BL_UITEST_NFL_EVENT"], !id.isEmpty else {
            throw XCTSkip("set BL_UITEST_NFL_EVENT to an NFL game with two or more story cards")
        }
        return id
    }

    /// Is the card named `name` fully inside the screen's width, judged from the
    /// reader rail's own elements (only the selected card is in that tree)?
    private func cardIsOnScreen(_ app: XCUIApplication, _ name: String) -> (Bool, String) {
        let rail = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label == 'Game story cards'")).firstMatch
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

    private func walk(extra: [String]) throws {
        let id = try eventID()
        XCUIDevice.shared.orientation = .portrait
        let app = UITestLaunch.launchApp(extra: ["-launch_route", "bainluck://events/\(id)"] + extra)
        // #11285 — the opener reads "Open story"; VoiceOver says "Open <title>".
        let opens = app.buttons.matching(identifier: "story-card-open")
        var swipes = 0
        while !(opens.firstMatch.exists && opens.firstMatch.isHittable) && swipes < 25 {
            app.swipeUp(velocity: .slow); swipes += 1
        }
        // Keep the deck out of the floating tab bar's band.
        if opens.firstMatch.frame.minY > app.frame.height * 0.6 { app.swipeUp(velocity: .slow) }
        let ordered = opens.allElementsBoundByIndex.sorted { $0.frame.minX < $1.frame.minX }.map(\.label)
        guard ordered.count >= 2 else {
            throw XCTSkip("event \(id) shows \(ordered.count) story card(s); this needs two")
        }
        let names = ordered.map {
            $0.replacingOccurrences(of: "Open ", with: "").components(separatedBy: " · ").first ?? ""
        }

        // Open the SECOND card, so Back has a neighbour to land on by mistake.
        let opened = app.buttons[ordered[1]]
        var drags = 0
        while !(opened.frame.minX >= 0 && opened.frame.minX < app.frame.width * 0.3) && drags < 4 {
            let y = opened.frame.minY - 120
            let origin = app.coordinate(withNormalizedOffset: .zero)
            origin.withOffset(CGVector(dx: app.frame.width * 0.85, dy: y))
                .press(forDuration: 0.05, thenDragTo: origin.withOffset(CGVector(dx: app.frame.width * 0.1, dy: y)))
            sleep(2); drags += 1
        }
        opened.tap()
        let back = app.buttons["Back to the game"]
        XCTAssertTrue(back.waitForExistence(timeout: 10), "the reader opens")

        // Rotate while on card 2: card 1 sits at offset zero and stays in view by
        // accident, so only a later card can show the rail losing its place.
        let position = app.staticTexts.matching(NSPredicate(format: "label BEGINSWITH 'Card '")).firstMatch
        XCTAssertEqual(position.label, "Card 2 of \(ordered.count)", "the reader opens on the card tapped")
        let control = cardIsOnScreen(app, names[1])
        XCTAssertTrue(control.0, "control: the opened card is on screen before rotating — \(control.1)")

        XCUIDevice.shared.orientation = .landscapeLeft
        sleep(3)
        let landscape = cardIsOnScreen(app, names[1])
        XCTAssertTrue(landscape.0, "#11060: the card the pager names is on screen in landscape — \(landscape.1)")
        XCUIDevice.shared.orientation = .portrait
        sleep(3)
        let portrait = cardIsOnScreen(app, names[1])
        XCTAssertTrue(portrait.0, "#11060: the card the pager names is on screen after rotating back — \(portrait.1)")
        XCTAssertEqual(position.label, "Card 2 of \(ordered.count)", "rotation keeps the selection")

        // Step to the neighbour, so Back has to come home to card 2 on the page.
        app.buttons["Previous card"].tap()
        sleep(1)
        XCTAssertEqual(position.label, "Card 1 of \(ordered.count)")
        let stepped = cardIsOnScreen(app, names[0])
        XCTAssertTrue(stepped.0, "the stepped-to card is on screen — \(stepped.1)")

        back.tap()
        sleep(2)
        XCTAssertFalse(back.exists, "Back closes the reader")
        let returned = app.buttons[ordered[1]]
        XCTAssertTrue(returned.exists && returned.frame.minX >= -1 && returned.frame.maxX <= app.frame.width + 1,
                      "#11060: Back lands on the card it was opened from — \(returned.frame)")
    }

    func testTheReaderKeepsItsCardThroughARotationAndBackReturnsToIt() throws {
        try walk(extra: [])
    }

    func testTheSameAtTheLargestTextSize() throws {
        try walk(extra: ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
    }
}
