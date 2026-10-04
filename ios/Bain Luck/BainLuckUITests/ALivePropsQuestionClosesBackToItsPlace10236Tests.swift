import XCTest

/// #10236 clauses 2–5 on the mounted page: on a LIVE game whose server carries
/// `during_player_props`, a reader picks a statistic, browses the threshold
/// columns sideways, taps one exact question, reads its detail across a live
/// refresh, and Close puts the page back where it was — same statistic, same
/// row, same sideways offset, same page scroll.
///
/// It walks EVERY statistic the matrix offers, in picker order, so a run covers
/// both a non-default statistic surviving Close and a question in a lower row
/// (whichever statistic has more than one player).
///
/// The matrix exists only while a game is live, so the route is an argument:
///
///   `BL_10236_ROUTE`  default `bainluck://events/15323083` (ATL @ LAD, live
///                     2026-10-03 20:00Z, 2 stats / 47 questions served)
///   `BL_10236_SIZE`   a `UIContentSizeCategory` raw value, e.g.
///                     `UICTContentSizeCategoryAccessibilityL` (AX3)
///   `BL_10236_DWELL`  seconds on the FIRST detail (default 40), long enough to
///                     cross the page's live refresh
///
/// A game that is no longer live serves no matrix: that is NOT WALKED (skip),
/// never a pass. VoiceOver focus return is not readable from XCUITest — the
/// runner sees no accessibility-focus state — so this test does not claim it.
final class ALivePropsQuestionClosesBackToItsPlace10236Tests: XCTestCase {

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

    /// "<player>, N or more <unit>, …" — the cell's own spoken label.
    private static let cellPredicate = NSPredicate(
        format: "label MATCHES %@", ".+, [0-9]+ or (more|fewer) .*")

    /// Player + question, without the price: the price may move during the
    /// dwell, the question may not.
    private static func questionKey(_ label: String) -> String {
        label.components(separatedBy: ", ").prefix(2).joined(separator: ", ")
    }

    /// Every static text's label from ONE accessibility snapshot. Enumerating
    /// `app.staticTexts` element by element races a live refresh: an element
    /// redrawn mid-walk is "No matches found" and fails the test for the rig.
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

    /// The statistic picker's buttons — label and selected state, left to
    /// right — from ONE accessibility snapshot. `app.buttons.allElementsBoundByIndex`
    /// resolved every button on the event page one query at a time (574 lookups
    /// in the 16:28Z IND@WSH run) and raced a live refresh until the rig was
    /// killed (exit 143) before printing a stat. Same filter as before: centred
    /// in the band under the header, a non-empty label with no comma (question
    /// cells are "Player, line, …"). No identifier is assumed — the picker has none.
    private func pickerStats(_ app: XCUIApplication, in band: CGRect) -> (labels: [String], selected: String?) {
        guard let root = try? app.snapshot() else { return ([], nil) }
        var found: [(minX: CGFloat, label: String, selected: Bool)] = []
        func walk(_ node: XCUIElementSnapshot) {
            if node.elementType == .button, !node.label.isEmpty, !node.label.contains(","),
               band.contains(CGPoint(x: node.frame.midX, y: node.frame.midY)) {
                found.append((node.frame.minX, node.label, node.isSelected))
            }
            node.children.forEach(walk)
        }
        walk(root)
        let ordered = found.sorted { $0.minX < $1.minX }
        return (ordered.map(\.label), ordered.first(where: \.selected)?.label)
    }

    /// A question cell as one snapshot saw it.
    private struct SeenCell {
        let label: String
        let frame: CGRect
    }

    /// The question cells wholly inside the reachable band, from ONE snapshot.
    /// `cells.allElementsBoundByIndex` + `isHittable` per cell was the run's
    /// second wall (14780551, 18:3xZ: stuck >7 min after `10236_STATS`). An
    /// element is rebound by its price-free key (`cell(_:key:)`) only when it
    /// is swiped, tapped or re-measured.
    private func reachableCells(_ app: XCUIApplication, in band: CGRect) -> [SeenCell] {
        guard let root = try? app.snapshot() else { return [] }
        var out: [SeenCell] = []
        func walk(_ node: XCUIElementSnapshot) {
            if node.elementType == .button, band.contains(node.frame),
               Self.cellPredicate.evaluate(with: ["label": node.label]) {
                out.append(SeenCell(label: node.label, frame: node.frame))
            }
            node.children.forEach(walk)
        }
        walk(root)
        return out
    }

    private func cell(_ app: XCUIApplication, key: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", key + ", ")).firstMatch
    }

    func testAQuestionDetailClosesBackToTheSameStatRowOffsetAndScroll() throws {
        let env = ProcessInfo.processInfo.environment
        let route = env["BL_10236_ROUTE"] ?? "bainluck://events/15323083"
        let size = env["BL_10236_SIZE"] ?? ""
        let dwell = TimeInterval(env["BL_10236_DWELL"] ?? "") ?? 40
        var extra = ["-launch_route", route]
        if !size.isEmpty { extra += ["-UIPreferredContentSizeCategoryName", size] }
        let app = UITestLaunch.launchApp(extra: extra)
        print("10236_PLAN route=\(route) size=\(size.isEmpty ? "default" : size) dwell=\(Int(dwell))s")

        // 1. Reach the matrix by scrolling the page, as a reader does: header in
        //    the upper part of the screen so the rows below it are reachable.
        let header = app.staticTexts["Live Player Props"]
        let page = app.scrollViews.firstMatch
        XCTAssertTrue(page.waitForExistence(timeout: UITestLaunch.contentTimeout), "The event page never drew.")
        let window = app.windows.firstMatch.frame
        var reached = false
        for _ in 0..<30 {
            let y = header.exists ? header.frame.minY : .infinity
            // Near the top (≤22% down): at AX5 two rows sit under a two-line
            // header and picker only from there.
            if y > window.minY + 110, y < window.minY + window.height * 0.22 { reached = true; break }
            if y <= window.minY + 110 {
                let from = page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45))
                from.press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.58)))
            } else if y < window.maxY {
                // Close: nudge rather than fling past it.
                let from = page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.7))
                from.press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.45)))
            } else {
                page.swipeUp(velocity: .slow)
            }
        }
        guard reached else {
            shot(app, "10236-00-no-matrix")
            throw XCTSkip("NOT WALKED: '\(route)' drew no 'Live Player Props' matrix after a bounded page walk — "
                          + "the game is not live or the server carried no typed props.")
        }
        let band = JourneyPrecondition.reachableBand(app)

        // 2. The statistics on offer, in picker order.
        let pickerBand = CGRect(x: 0, y: header.frame.maxY, width: window.width, height: 110)
        let (statLabels, defaultStat) = pickerStats(app, in: pickerBand)
        print("10236_STATS \(statLabels) default=\(defaultStat ?? "nil")")
        XCTAssertFalse(statLabels.isEmpty, "No statistic picker under the header (single-stat matrices draw none; this game served several).")

        // Non-default first, so the first (long-dwell) pass proves a choice the
        // reader made survives.
        let order = statLabels.filter { $0 != defaultStat } + statLabels.filter { $0 == defaultStat }
        var walkedLowerRow = false
        var walkedNonDefault = false
        var walkedSideways = false
        for (pass, stat) in order.enumerated() {
            let button = app.buttons[stat]
            if !button.isSelected { button.tap() }
            XCTAssertTrue(button.isSelected, "Tapping '\(stat)' did not select it.")

            // 3. Browse the threshold columns sideways.
            let cells = app.buttons.matching(Self.cellPredicate)
            XCTAssertTrue(cells.firstMatch.waitForExistence(timeout: 5), "'\(stat)' drew no question cells.")
            func visibleCells() -> [SeenCell] { reachableCells(app, in: band) }
            let leftBefore = visibleCells().min { ($0.frame.minY, $0.frame.minX) < ($1.frame.minY, $1.frame.minX) }
            let leftBeforeKey = leftBefore.map { Self.questionKey($0.label) } ?? ""
            leftBefore.map { cell(app, key: Self.questionKey($0.label)) }?.swipeLeft(velocity: .slow)
            sleep(1)
            let visible = visibleCells()
            let leftAfter = visible.min { ($0.frame.minY, $0.frame.minX) < ($1.frame.minY, $1.frame.minX) }
            let leftAfterKey = leftAfter.map { Self.questionKey($0.label) } ?? ""
            let browsed = !leftBeforeKey.isEmpty && leftAfterKey != leftBeforeKey
            walkedSideways = walkedSideways || browsed
            print("10236_SIDEWAYS stat=\(stat) firstColumnBefore='\(leftBeforeKey)' firstColumnAfter='\(leftAfterKey)' browsed=\(browsed)")
            shot(app, "10236-p\(pass)-01-\(stat)-browsed")

            // 4. The question to open: the LOWEST fully reachable row, its
            //    right-most reachable column.
            let rows = Dictionary(grouping: visible) { Int($0.frame.minY.rounded()) }
            let rowYs = rows.keys.sorted()
            guard let lastY = rowYs.last, let target = rows[lastY]?.max(by: { $0.frame.minX < $1.frame.minX }),
                  let firstY = rowYs.first, let reference = rows[firstY]?.min(by: { $0.frame.minX < $1.frame.minX }) else {
                XCTFail("'\(stat)': no reachable question cell after the sideways browse.")
                return
            }
            let targetLabel = target.label
            let key = Self.questionKey(targetLabel)
            let player = targetLabel.components(separatedBy: ", ").first ?? ""
            let referenceKey = Self.questionKey(reference.label)
            let rowIndex = rowYs.count - 1
            print("10236_BEFORE stat=\(stat) row=\(rowIndex) headerY=\(header.frame.minY) target='\(targetLabel)' frame=\(target.frame) reference='\(referenceKey)' frame=\(reference.frame)")

            // 4b. Control, first pass only: the same dwell with NO detail open.
            //     A live update that resizes content above the matrix moves the
            //     page by itself; if it does here, a move across the detail is
            //     the page's, not Close's — and the control line says so.
            var controlDrift: CGFloat = 0
            if pass == 0 {
                var ys: [CGFloat] = []
                let until = Date().addingTimeInterval(dwell)
                while Date() < until { ys.append(header.frame.minY); sleep(5) }
                controlDrift = (ys.max() ?? 0) - (ys.min() ?? 0)
                print("10236_CONTROL no-detail dwell=\(Int(dwell))s headerY=\(ys.map { Int($0) }) drift=\(controlDrift)")
            }
            let headerY = header.frame.minY
            // Re-measured live, after the control dwell, as before.
            let targetFrame = cell(app, key: key).frame
            let referenceFrame = cell(app, key: referenceKey).frame

            // 5. Open the exact question.
            cell(app, key: key).tap()
            let close = app.buttons["Close"]
            XCTAssertTrue(close.waitForExistence(timeout: 5), "Tapping '\(targetLabel)' opened no detail with a Close button.")
            XCTAssertTrue(app.navigationBars[player].waitForExistence(timeout: 3),
                          "The detail is not titled '\(player)'; bars: \(app.navigationBars.allElementsBoundByIndex.map(\.identifier)).")
            let spoken = targetLabel.components(separatedBy: ", ").dropFirst().first ?? ""
            let count = spoken.components(separatedBy: " ").first ?? ""
            let detailTexts = texts(app)
            XCTAssertTrue(detailTexts.contains { $0.hasPrefix(player) == false && $0.contains(count) },
                          "The detail names no question for '\(spoken)'; texts: \(detailTexts.prefix(12))")
            print("10236_DETAIL stat=\(stat) title='\(player)' texts=\(detailTexts.prefix(10))")
            shot(app, "10236-p\(pass)-02-detail")

            // 5b. Pull the sheet to full height: the other side, when the server
            //     paired one, reads as the UNDER question — never the same one.
            let navBar = app.navigationBars[player]
            navBar.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
                .press(forDuration: 0.05, thenDragTo: app.windows.firstMatch.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.08)))
            sleep(1)
            // At the largest sizes the section is below the sheet's fold: scroll
            // the sheet's own list to it before deciding it is absent.
            let otherHeader = app.staticTexts["Other side"]
            let sheetList = app.collectionViews.firstMatch
            for _ in 0..<4 where !(otherHeader.exists && otherHeader.isHittable) && sheetList.exists {
                sheetList.swipeUp(velocity: .slow)
            }
            if otherHeader.exists {
                let sides = texts(app)
                    .filter { $0.contains(" or fewer ") }
                print("10236_OTHER_SIDE stat=\(stat) \(sides)")
                XCTAssertFalse(sides.isEmpty, "'Other side' is drawn but names no 'or fewer' question.")
            } else {
                print("10236_OTHER_SIDE stat=\(stat) none drawn for '\(key)' after scrolling the sheet")
            }
            shot(app, "10236-p\(pass)-02b-detail-large")

            // 6. First pass stays across a live refresh: the sheet stays up, on
            //    the same player.
            if pass == 0 {
                let deadline = Date().addingTimeInterval(dwell)
                while Date() < deadline {
                    sleep(5)
                    XCTAssertTrue(close.exists, "The detail closed by itself during the dwell (a live refresh dismissed it).")
                    XCTAssertTrue(app.navigationBars[player].exists, "The detail moved off '\(player)' during the dwell.")
                }
                print("10236_DWELL seconds=\(Int(dwell)) textsAfter=\(texts(app).prefix(10))")
                shot(app, "10236-p\(pass)-03-detail-after-dwell")
            }

            // 7. Close, and read the page back.
            close.tap()
            expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: close)
            waitForExpectations(timeout: 5)
            sleep(1)
            shot(app, "10236-p\(pass)-04-after-close")

            XCTAssertTrue(header.exists, "The matrix header is gone after Close.")
            let headerYAfter = header.frame.minY
            let targetAfter = cell(app, key: key)
            let referenceAfter = cell(app, key: referenceKey)
            print("10236_AFTER stat=\(stat)\(app.buttons[stat].isSelected ? "*" : "") headerY=\(headerYAfter) target='\(targetAfter.label)' frame=\(targetAfter.frame) reference frame=\(referenceAfter.frame)")
            XCTAssertTrue(app.buttons[stat].isSelected, "Close dropped the chosen stat '\(stat)'.")
            XCTAssertTrue(targetAfter.exists, "The tapped question '\(key)' is no longer drawn after Close.")
            XCTAssertEqual(targetAfter.frame.minX, targetFrame.minX, accuracy: 2, "Sideways offset moved across the detail.")
            // The row inside the matrix (relative to its header), then the page.
            XCTAssertEqual(targetAfter.frame.minY - headerYAfter, targetFrame.minY - headerY, accuracy: 2,
                           "The tapped row moved inside the matrix across the detail.")
            XCTAssertEqual(referenceAfter.frame.minX, referenceFrame.minX, accuracy: 2, "The first row's sideways offset moved.")
            XCTAssertEqual(headerYAfter, headerY, accuracy: 2,
                           "Page scroll moved across the detail (no-detail control drift on pass 0: \(controlDrift)).")
            walkedLowerRow = walkedLowerRow || rowIndex >= 1
            walkedNonDefault = walkedNonDefault || stat != defaultStat
            print("10236_PASS stat=\(stat) row=\(rowIndex) question='\(key)' browsed=\(browsed)")
        }
        print("10236_RECEIPT PASS route=\(route) size=\(size.isEmpty ? "default" : size) stats=\(order) lowerRow=\(walkedLowerRow) nonDefaultStat=\(walkedNonDefault) sideways=\(walkedSideways) dwell=\(Int(dwell))s")
        XCTAssertTrue(walkedLowerRow, "No statistic had a second reachable row, so row retention was not exercised.")
    }
}
