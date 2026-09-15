import XCTest

/// #6343's INTERACTION, driven by a finger: **a reader taps the age chip on a
/// Discover card, sees the precise stamp, and taps again to put it away.**
///
/// `PriceAgeMarkTests` proves the decision — when the mark draws, what it says,
/// what the tap hands back. It cannot prove the tap REACHES anything: the
/// closure it exercises is one the test supplies itself, so a card that never
/// wired `onReveal`, a chip too small to hit, or a caption that appears and will
/// not go away are all invisible to it and all fully user-visible.
///
/// That gap is the whole reason this file exists. The phone has no hover, so the
/// tap IS the disclosure — if it does not land there is no way to see the precise
/// time at all, and the ship is the precise time.
final class AReaderCanRevealWhenAPriceWasLastSeenTests: XCTestCase {

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
    }

    // MARK: - Finding a specimen

    /// The age chip, wherever it is: `PriceAgeMarkView`'s accessibility label is
    /// `"Price 3d ago. Last number: 12 Sep, 3:51 AM"`, and the stem is fixed
    /// while everything after it is data.
    private static func markQuery(in app: XCUIApplication) -> XCUIElementQuery {
        app.descendants(matching: .any)
            .matching(NSPredicate(format: "label BEGINSWITH %@", "Price "))
    }

    /// Scroll Discover until an age chip is on screen, or say it was not there.
    ///
    /// THE SPECIMEN IS DATA AND THE DATA IS USUALLY SILENT — that is #6343's
    /// design, not a rig problem: the mark draws only for a futures card whose
    /// price is over six hours old, and a measured `/api/feed` read this morning
    /// had ONE such card in the top forty. So "no chip" is a precondition miss
    /// (a skip naming what was absent), never a pass and never a failure of the
    /// tap path. A run that skips here has NOT walked the journey and the script
    /// prints the skip count for exactly that reason.
    private func huntForAMark(in app: XCUIApplication) throws -> XCUIElement {
        let scrollView = app.scrollViews.firstMatch
        XCTAssertTrue(
            scrollView.waitForExistence(timeout: UITestLaunch.contentTimeout),
            "Discover has no scroll view, so there is nothing to hunt through."
        )

        // Bounded. Twelve swipes is well past the forty cards the feed serves at
        // phone width, and an unbounded hunt on an infinite feed never returns.
        for swipe in 0...12 {
            let mark = Self.markQuery(in: app).firstMatch
            if mark.waitForExistence(timeout: swipe == 0 ? 8 : 1.5) {
                XCTContext.runActivity(named: "found an age chip after \(swipe) swipe(s): \(mark.label)") { _ in }
                return mark
            }
            scrollView.swipeUp()
        }

        throw XCTSkip(
            "NOT WALKED: no price-age chip anywhere in the first 12 screens of Discover, so there was nothing to tap. "
            + "The mark draws only on an OPEN futures card whose price is over six hours old "
            + "(`FeedFuturesData.discoverPriceAgeMark`), and on a healthy feed most cards are inside their cadence — "
            + "so this is usually 'every price is fresh', which is good news about the data and no news about the tap path. "
            + "Check /api/feed for a card with `price_observed_at` older than six hours before reading this as a defect."
        )
    }

    /// The nearest thing BELOW the chip that a tap must push down.
    ///
    /// The reveal caption is `accessibilityHidden` — deliberately, because the
    /// chip's own label already speaks the sentence — so the caption cannot be
    /// asserted on directly. What a reader sees instead is the card GROWING to
    /// make room for it, and that is observable: every element below the chip
    /// moves down by the caption's height.
    ///
    /// Recorded by LABEL rather than by holding the element, because the feed is
    /// lazy and an `XCUIElement` captured before a relayout can resolve to a
    /// different row afterwards.
    private func witnessBelow(_ mark: XCUIElement, in app: XCUIApplication) -> (label: String, y: CGFloat)? {
        let floor = mark.frame.maxY
        let candidates = app.staticTexts.allElementsBoundByIndex
            .filter { $0.exists && !$0.label.isEmpty && $0.frame.minY > floor + 2 }
            .sorted { $0.frame.minY < $1.frame.minY }

        // Unique labels only: a duplicate ("Kalshi" appears on every card) would
        // re-resolve to whichever one the query answers with next time.
        for candidate in candidates {
            let sameLabel = candidates.filter { $0.label == candidate.label }
            if sameLabel.count == 1 { return (candidate.label, candidate.frame.minY) }
        }
        return nil
    }

    // MARK: - The journey

    func testTappingTheAgeChipRevealsThePreciseStampAndTappingAgainPutsItAway() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)

        let mark = try huntForAMark(in: app)

        XCTAssertTrue(
            mark.isHittable,
            "The age chip is in the tree at \(mark.frame) and reports `isHittable == false`. "
            + "A reader cannot open the precise stamp at all — and on a phone the tap is the ONLY route to it."
        )

        attach(app.screenshot(), named: "1-before-the-tap")
        XCTContext.runActivity(named: "chip label: \(mark.label)") { _ in }

        // The chip's label carries the sentence the tap is supposed to reveal, so
        // a chip that says only "Price 3d ago" would reveal nothing to a sighted
        // reader no matter how well the gesture lands.
        XCTAssertTrue(
            mark.label.contains("Last number"),
            "The chip's label is '\(mark.label)' — it carries no precise stamp, so there is nothing for the tap to show."
        )

        guard let before = witnessBelow(mark, in: app) else {
            throw XCTSkip(
                "NOT WALKED: found the chip at \(mark.frame) but nothing with a unique label sits below it on screen, "
                + "so there is no witness for the caption pushing the page down. Re-run — the chip was probably the "
                + "last thing on screen."
            )
        }
        XCTContext.runActivity(named: "witness below the chip: '\(before.label)' at y=\(before.y)") { _ in }

        mark.tap()

        let opened = waitForY(ofLabel: before.label, in: app, toDifferFrom: before.y, byAtLeast: 12)
        attach(app.screenshot(), named: "2-after-the-tap-caption-open")
        XCTAssertNotNil(
            opened,
            "Tapped the age chip and NOTHING below it moved: '\(before.label)' stayed at y=\(before.y). "
            + "The caption is inserted under the card's footer, so a reveal that happened would have pushed it down. "
            + "This is the card not wiring `onReveal`, or the chip's tap target not accepting the gesture."
        )
        if let opened {
            XCTAssertGreaterThan(
                opened, before.y,
                "The reveal moved '\(before.label)' UP, from y=\(before.y) to y=\(opened). A caption added below the "
                + "footer can only push content down; upward means the feed scrolled under the tap instead of revealing."
            )
        }

        // THE HALF A FORWARD-ONLY TEST CANNOT SEE. A caption that opens and will
        // not close is a reader stuck with a grey sentence covering the card
        // below — the same shape as check 6's trapped reader.
        mark.tap()

        let closed = waitForY(ofLabel: before.label, in: app, toReturnTo: before.y, within: 2)
        attach(app.screenshot(), named: "3-after-the-second-tap-caption-dismissed")
        XCTAssertTrue(
            closed,
            "Tapped the chip a second time and '\(before.label)' did not return to y=\(before.y) "
            + "(it is at \(currentY(ofLabel: before.label, in: app).map(String.init(describing:)) ?? "gone")). "
            + "The caption did not dismiss: `revealedPriceAge = revealedPriceAge == $0 ? nil : $0` is the toggle, "
            + "so a reveal that cannot be put away means that comparison is not matching."
        )
    }

    // MARK: - Rig

    private func currentY(ofLabel label: String, in app: XCUIApplication) -> CGFloat? {
        let element = app.staticTexts[label]
        guard element.exists else { return nil }
        return element.frame.minY
    }

    /// Poll for the witness to move. A bare read right after `tap()` races the
    /// relayout and would red on a working app.
    private func waitForY(
        ofLabel label: String,
        in app: XCUIApplication,
        toDifferFrom origin: CGFloat,
        byAtLeast delta: CGFloat
    ) -> CGFloat? {
        for _ in 0..<24 {
            if let y = currentY(ofLabel: label, in: app), abs(y - origin) >= delta { return y }
            usleep(250_000)
        }
        return nil
    }

    private func waitForY(
        ofLabel label: String,
        in app: XCUIApplication,
        toReturnTo origin: CGFloat,
        within tolerance: CGFloat
    ) -> Bool {
        for _ in 0..<24 {
            if let y = currentY(ofLabel: label, in: app), abs(y - origin) <= tolerance { return true }
            usleep(250_000)
        }
        return false
    }

    private func attach(_ screenshot: XCUIScreenshot, named name: String) {
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
