import XCTest

/// #10528 (child of #10237) on the mounted page: on a FINISHED game whose
/// server carries `after_player_props`, a reader picks Home Runs, taps one
/// exact saved-chance question, reads its detail and closes it — and at the
/// largest text sizes the selected pill, the statistic's name and every
/// player's name stay whole on screen.
///
/// It is the build-37 acceptance path (#10237, Home Runs → Brice Turang →
/// detail → Close) promoted from scratch, plus the geometry the readability
/// fix promises. The geometry is necessary, not sufficient: XCUITest reads a
/// truncated label's FULL text, so "Home…" and "Yeli…" are only visible in
/// the saved frames, which a person reads.
///
///   `BL_10528_ROUTE`  default `bainluck://events/15323985` (SD 3 – MIL 4,
///                     final, Home Runs carries Turang and Yelich)
///   `BL_10528_SIZE`   a `UIContentSizeCategory` raw value, e.g.
///                     `UICTContentSizeCategoryAccessibilityXXXL` (AX5)
///   `BL_10528_OUT`    directory for the frames (default /tmp/n10528-shots)
///
/// A page that serves no Home Runs pill is NOT WALKED (skip), never a pass.
final class AfterPropsReadableAtLargestText10528Tests: XCTestCase {

    private var outDir = ""
    private var mode = "default"
    private var frameNo = 0

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        let env = ProcessInfo.processInfo.environment
        outDir = env["BL_10528_OUT"] ?? "/tmp/n10528-shots"
        mode = (env["BL_10528_SIZE"] ?? "").isEmpty ? "default" : "sized"
        try? FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)
    }

    private func shot(_ app: XCUIApplication, _ name: String) {
        frameNo += 1
        let shot = app.screenshot()
        let file = String(format: "%@/%@-%02d-%@.png", outDir, mode, frameNo, name)
        try? shot.pngRepresentation.write(to: URL(fileURLWithPath: file))
        print("N10528_FRAME \(file)")
        let attachment = XCTAttachment(screenshot: shot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    /// Static texts from ONE snapshot, optionally inside a band.
    private func texts(_ app: XCUIApplication, in band: CGRect? = nil) -> [(String, CGRect)] {
        guard let root = try? app.snapshot() else { return [] }
        var out: [(String, CGRect)] = []
        func walk(_ node: XCUIElementSnapshot) {
            if node.elementType == .staticText, band.map({ $0.intersects(node.frame) }) ?? true {
                out.append((node.label, node.frame))
            }
            node.children.forEach(walk)
        }
        walk(root)
        return out
    }

    private static func describe(_ items: [(String, CGRect)]) -> String {
        items.map { "\($0.0)@\(Int($0.1.minX)),\(Int($0.1.minY)),\(Int($0.1.width))x\(Int($0.1.height))" }
            .joined(separator: " | ")
    }

    private static let turangPredicate = NSPredicate(format: "label BEGINSWITH %@", "Brice Turang, ")

    func testHomeRunsStayWholeThroughDetailAndClose() throws {
        let env = ProcessInfo.processInfo.environment
        let route = env["BL_10528_ROUTE"] ?? "bainluck://events/15323985"
        let size = env["BL_10528_SIZE"] ?? ""
        var extra = ["-launch_route", route]
        if !size.isEmpty { extra += ["-UIPreferredContentSizeCategoryName", size] }
        let app = UITestLaunch.launchApp(extra: extra)
        let window = app.windows.firstMatch.frame
        print("N10528_PLAN size=\(size.isEmpty ? "default" : size) route=\(route) window=\(window)")

        let page = app.scrollViews.firstMatch
        XCTAssertTrue(page.waitForExistence(timeout: UITestLaunch.contentTimeout), "The event page never drew.")
        sleep(3)

        // 1. Scroll as a reader until "Player Props" sits in the upper part.
        let header = app.staticTexts["Player Props"]
        var reached = false
        for _ in 0..<40 {
            let y = header.exists ? header.frame.minY : .infinity
            if y > window.minY + 110, y < window.minY + window.height * 0.22 { reached = true; break }
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
        sleep(1)
        XCTAssertTrue(reached, "No 'Player Props' header reached on \(route).")
        shot(app, "matrix-default-stat")

        // 2. The Home Runs pill is whole inside the card WITHOUT any sideways
        //    drag: the card's content runs from header.minX to the mirrored
        //    right inset.
        let hr = app.buttons["Home Runs"]
        guard hr.waitForExistence(timeout: 5) else {
            throw XCTSkip("NOT WALKED: \(route) serves no Home Runs pill.")
        }
        let content = CGRect(x: header.frame.minX, y: window.minY,
                             width: window.width - 2 * header.frame.minX, height: window.height)
        print("N10528_HR_PILL frame=\(hr.frame) content=\(content)")
        XCTAssertTrue(content.insetBy(dx: -0.5, dy: 0).contains(hr.frame),
                      "The Home Runs pill \(hr.frame) is cut at the card edge \(content).")
        hr.tap()
        XCTAssertTrue(hr.waitForSelected(timeout: 5), "Tapping 'Home Runs' did not select it.")
        XCTAssertTrue(content.insetBy(dx: -0.5, dy: 0).contains(hr.frame),
                      "The selected Home Runs pill \(hr.frame) is cut at the card edge \(content).")
        sleep(1)
        shot(app, "home-runs-selected")

        // 3. Turang's cell: one whole threshold column on screen, the
        //    player column beside it never overlapping it.
        let turang = app.buttons.matching(Self.turangPredicate).firstMatch
        XCTAssertTrue(turang.waitForExistence(timeout: 5), "No 'Brice Turang' Home Runs cell.")
        let band = JourneyPrecondition.reachableBand(app)
        var lifts = 0
        while !band.contains(turang.frame), lifts < 12 {
            let from: CGFloat = turang.frame.minY > band.midY ? 0.7 : 0.45
            page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: from))
                .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55)))
            lifts += 1
            sleep(1)
        }
        let cellFrame = turang.frame
        let headerY = header.frame.minY
        XCTAssertTrue(content.insetBy(dx: -0.5, dy: 0).contains(
            CGRect(x: cellFrame.minX, y: content.minY, width: cellFrame.width, height: 1)),
                      "Turang's threshold cell \(cellFrame) is not a whole column inside \(content).")
        let row = texts(app, in: CGRect(x: 0, y: cellFrame.minY, width: cellFrame.minX, height: cellFrame.height))
        print("N10528_TURANG label='\(turang.label)' frame=\(cellFrame) lifts=\(lifts) row=\(Self.describe(row))")
        for (label, frame) in row where ["Brice Turang", "0 home runs"].contains(label) {
            XCTAssertLessThanOrEqual(frame.maxX, cellFrame.minX + 0.5,
                                     "'\(label)' \(frame) runs into the threshold column \(cellFrame).")
            XCTAssertTrue(frame.minY >= cellFrame.minY - 0.5 && frame.maxY <= cellFrame.maxY + 0.5,
                          "'\(label)' \(frame) is not aligned with its row \(cellFrame).")
        }
        let visible = texts(app, in: band)
        print("N10528_MATRIX_VISIBLE \(Self.describe(visible))")
        shot(app, "turang-before-tap")

        // 4. Open the exact cell, read it, Close.
        let label = turang.label
        turang.tap()
        let close = app.buttons["Close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5), "Tapping Turang's cell opened no detail with Close.")
        sleep(1)
        print("N10528_DETAIL \(Self.describe(texts(app)))")
        shot(app, "detail")
        close.tap()
        XCTAssertTrue(close.waitForNonExistence(timeout: 5), "Close did not dismiss the detail.")
        sleep(2)

        // 5. Same place, same statistic, same question.
        let after = app.buttons.matching(Self.turangPredicate).firstMatch
        print("N10528_AFTER_CLOSE headerY=\(header.frame.minY) (before \(headerY)) frame=\(after.exists ? after.frame : .null) (before \(cellFrame)) hrSelected=\(hr.isSelected)")
        XCTAssertTrue(hr.isSelected, "Close lost the Home Runs selection.")
        XCTAssertTrue(after.exists, "Close lost Turang's cell.")
        XCTAssertEqual(after.label, label, "Close returned to a different question.")
        XCTAssertEqual(header.frame.minY, headerY, accuracy: 1, "Close moved the page.")
        XCTAssertEqual(after.frame.minY, cellFrame.minY, accuracy: 1, "Close moved Turang's row.")
        shot(app, "after-close")

        // 6. After the Close checks, lift Christian Yelich's row into view: the
        //    build-37 frame read "Christ-/ian Yeli…" here.
        let yelich = app.staticTexts["Christian Yelich"]
        guard yelich.waitForExistence(timeout: 5) else {
            print("N10528_YELICH absent on \(route)")
            return
        }
        var yelichLifts = 0
        while !band.contains(yelich.frame), yelichLifts < 12 {
            page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.7))
                .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.55)))
            yelichLifts += 1
            sleep(1)
        }
        let yelichCell = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Christian Yelich, ")).firstMatch
        print("N10528_YELICH name=\(yelich.frame) cell=\(yelichCell.exists ? yelichCell.frame : .null) lifts=\(yelichLifts)")
        XCTAssertTrue(band.contains(yelich.frame), "Christian Yelich's name \(yelich.frame) never came into view.")
        if yelichCell.exists {
            XCTAssertLessThanOrEqual(yelich.frame.maxX, yelichCell.frame.minX + 0.5,
                                     "Christian Yelich's name \(yelich.frame) runs into the threshold column \(yelichCell.frame).")
        }
        shot(app, "yelich-row")

        // 7. The rest of the column, for the person reading the frames: every
        //    player name beside its own row, none running into a cell.
        for step in 1...6 {
            page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
                .press(forDuration: 0.05, thenDragTo: page.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.35)))
            sleep(1)
            let cells = app.buttons.matching(Self.cellPredicate).allElementsBoundByIndex.filter { band.contains($0.frame) }
            for cell in cells {
                let name = String(cell.label.split(separator: ",").first ?? "")
                let text = app.staticTexts[name]
                guard text.exists, band.contains(text.frame) else { continue }
                print("N10528_ROW \(name) name=\(text.frame) cell=\(cell.frame)")
                XCTAssertLessThanOrEqual(text.frame.maxX, cell.frame.minX + 0.5,
                                         "'\(name)' \(text.frame) runs into the threshold column \(cell.frame).")
            }
            shot(app, "more-rows-\(step)")
        }
    }

    /// "<player>, N or more <unit>, …" — a threshold cell's spoken label.
    private static let cellPredicate = NSPredicate(format: "label MATCHES %@", ".+, [0-9]+ or more .*")
}
