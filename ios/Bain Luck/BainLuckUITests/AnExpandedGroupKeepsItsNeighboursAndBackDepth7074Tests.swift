import XCTest

/// #7074 expanded-group arms: an expanded Discover group draws its members
/// without overlapping the card after it, a true tap on a member opens it, and
/// Back returns to the same expanded group at the same scroll depth.
///
/// Adapted from Sol's prepared method. Expanded members are full cards and carry
/// `discover-card` themselves, so "the card at index+1" is a member nested inside
/// the group, not its neighbour. The group is found by its header (label + value)
/// and the neighbour is the first card that is not inside the group's frame.
final class AnExpandedGroupKeepsItsNeighboursAndBackDepth7074Tests: XCTestCase {

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

    func testExpandedGroupKeepsAdjacentFramesAndBackDepth() throws {
        let app = UITestLaunch.launchApp()
        JourneyPrecondition.tabBar(of: app)
        _ = try JourneyPrecondition.firstCard(in: app)
        let scroll = app.scrollViews.firstMatch
        let cards = JourneyPrecondition.cards(in: app)
        let window = app.windows.firstMatch
        let band = JourneyPrecondition.reachableBand(app)

        // Back depth must start below the top, not on the stationary first page.
        scroll.swipeUp()
        scroll.swipeUp()
        let collapsedHeaders = app.buttons.matching(NSPredicate(format: "value == %@", "Collapsed"))
        var header: XCUIElement?
        for _ in 0..<25 {
            header = collapsedHeaders.allElementsBoundByIndex.first { $0.isHittable && band.contains($0.frame) }
            if header != nil { break }
            scroll.swipeUp()
        }
        guard let header else {
            throw XCTSkip("NOT WALKED: no expandable group header was touchable after the bounded below-top walk.")
        }
        let headerLabel = header.label
        let expandedHeader = app.buttons.matching(
            NSPredicate(format: "label == %@ AND value == %@", headerLabel, "Expanded")).firstMatch
        let group = cards.containing(
            NSPredicate(format: "label == %@ AND value IN %@", headerLabel, ["Collapsed", "Expanded"])).firstMatch
        XCTAssertTrue(group.exists, "The header is not inside a discover-card.")
        let beforeHeight = group.frame.height
        print("7074_COLLAPSED header='\(headerLabel)' headerY=\(header.frame.minY) group=\(group.frame)")
        shot(app, "7074-01-collapsed-below-top")
        header.tap()

        XCTAssertTrue(expandedHeader.waitForExistence(timeout: 5), "The group did not expand after the header tap.")
        XCTAssertGreaterThan(group.frame.height, beforeHeight + 20, "Expanded state drew no additional height.")

        // Keep the first member's tap point above the floating tab bar.
        let wantedY = expandedHeader.frame.maxY + 100
        if wantedY > band.maxY - 20 {
            JourneyPrecondition.liftContent(app, by: wantedY - (band.maxY - 20) + 40)
        }
        let beforeY = expandedHeader.frame.minY
        let targetY = expandedHeader.frame.maxY + 100
        XCTAssertLessThan(targetY, band.maxY,
            "NOT WALKED: the first expanded member's tap point is outside the usable viewport.")
        let groupFrameBefore = group.frame
        let members = cards.allElementsBoundByIndex.filter {
            $0.frame.minY > expandedHeader.frame.maxY && groupFrameBefore.contains($0.frame)
        }
        print("7074_EXPANDED header='\(headerLabel)' headerY=\(beforeY) group=\(groupFrameBefore) "
            + "height \(beforeHeight)->\(groupFrameBefore.height) members=\(members.map { $0.frame })")
        shot(app, "7074-02-expanded-before-member-open")

        // A true tap inside the first full member card, below the expansion header.
        app.coordinate(withNormalizedOffset: .zero)
            .withOffset(CGVector(dx: window.frame.midX, dy: targetY)).tap()
        XCTAssertTrue(app.navigationBars["Discover"].waitForNonExistence(timeout: UITestLaunch.contentTimeout),
            "The true tap on an expanded member did not push its destination.")
        let destinationTitle = app.navigationBars.firstMatch.identifier
        print("7074_DESTINATION nav='\(destinationTitle)'")
        shot(app, "7074-03-expanded-member-detail")
        let back = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(back.waitForExistence(timeout: 5), "The destination has no Back control.")
        back.tap()
        XCTAssertTrue(app.navigationBars["Discover"].waitForExistence(timeout: UITestLaunch.contentTimeout))
        XCTAssertTrue(expandedHeader.waitForExistence(timeout: 5), "Back lost the expanded group.")
        let returnedY = expandedHeader.frame.minY
        print("7074_BACK headerY \(beforeY)->\(returnedY)")
        shot(app, "7074-04-back-same-depth-expanded")
        XCTAssertEqual(returnedY, beforeY, accuracy: 24, "Back lost the reader's below-top scroll depth.")

        // Bring the group's bottom edge and the outer card after it into view.
        func neighbour() -> XCUIElement? {
            let g = group.frame
            return cards.allElementsBoundByIndex
                .filter { !g.contains($0.frame) && $0.frame.minY > g.minY && $0.frame.height > 0 }
                .min { $0.frame.minY < $1.frame.minY }
        }
        var next: XCUIElement?
        for _ in 0..<25 {
            next = neighbour()
            if let next, next.isHittable, group.frame.maxY < band.maxY { break }
            scroll.swipeUp()
        }
        guard let next, next.isHittable else {
            throw XCTSkip("Back-depth walked; overlap arm NOT WALKED: no following card reached the viewport.")
        }
        let groupFrame = group.frame
        let nextFrame = next.frame
        print("7074_RENDERED_FRAMES group=\(groupFrame) next=\(nextFrame) backY=\(beforeY)->\(returnedY)")
        shot(app, "7074-05-expanded-bottom-and-adjacent-card")
        XCTAssertGreaterThan(groupFrame.height, 0)
        XCTAssertGreaterThanOrEqual(nextFrame.minY, groupFrame.maxY - 1,
            "The following card begins inside the expanded group's frame.")
    }
}
