import XCTest

/// #10238's mounted change clause, read off the OPEN sheet: with one Game or
/// Series option's detail open on the real `EventQuestionMatrixSection10238`,
/// the DEBUG host (`EventQuestionMatrixCurrentnessActivation10238`) feeds
/// thirteen retained inputs — Game through the real `GameMarketsPriceDelivery`,
/// Series through a copy of the view model's response admission rule. After
/// each step this test reads what the reader sees on that same sheet (the
/// value printed under the option, or the unavailable sentence) and only then
/// compares it with the retained expectation. The host's phase label says WHEN
/// to read; it is never the thing read.
///
///   `BL10238_DIR`    simulator-readable directory holding the thirteen inputs.
///                    Absent ⇒ skip (a rig test, not part of any standing gate).
///   `BL10238_SCOPE`  `game` (opens "Game total 9.5 · Over") or `series`
///                    (opens "Series winner · Home"). One sheet per run.
///   `BL10238_RUN`    a name for the log lines and shots only.
///
/// Assertions are soft (`continueAfterFailure = true`) so a negative control
/// reports EVERY step it fails. freeze01 must fail every changed step;
/// hold-game09 must fail Game step 09; hold-series13 and empty-envelope13 must
/// fail Series step 13.
///
/// Not claimed: VoiceOver focus (XCUITest cannot read it), served or phone
/// behaviour (the inputs are synthetic), regressed/equal/missing-clock refusal
/// (the retained clocks only advance).
final class MountedGameSeriesQuestionFollowsEvidence10238Tests: XCTestCase {

    private static let phases = [
        "01-initial", "02-newer", "03-price-withdrawn", "04-price-restored",
        "05-option-removed", "06-option-restored", "07-question-removed",
        "08-question-restored", "09-game-matrix-absent", "10-series-matrix-absent",
        "11-both-restored", "12-game-final-series-open", "13-series-absent-game-final"
    ]
    private static let removedSentence = "This question is unavailable"

    private struct Subject {
        let sheetTitle: String
        let question: String
        let option: String
        let expected: [String]
    }

    /// EXPECTED.json's `actual_open_sheet_expected`, verbatim.
    private static let subjects: [String: Subject] = [
        "game": Subject(
            sheetTitle: "Game questions", question: "Game total 9.5", option: "Over",
            expected: ["48%", "55%", "Unavailable", "57%", removedSentence, "58%", removedSentence,
                       "59%", removedSentence, "60%", "61%", "Won", "Won"]),
        "series": Subject(
            sheetTitle: "Series questions", question: "Series winner", option: "Home",
            expected: ["62%", "67%", "Unavailable", "69%", removedSentence, "70%", removedSentence,
                       "71%", "72%", removedSentence, "73%", "74%", removedSentence]),
    ]
    /// The sibling question shares a market with the primary; a sheet that
    /// shows it has jumped to another question.
    private static let siblingLabels = ["Different question", "Separate option"]

    override func setUp() {
        super.setUp()
        continueAfterFailure = true
    }

    /// Attached, and also written beside the inputs (`<dir>/../shots-<run>/`).
    private func shot(_ app: XCUIApplication, _ name: String, into folder: URL?) {
        let screenshot = app.screenshot()
        let attachment = XCTAttachment(screenshot: screenshot)
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
        if let folder {
            try? FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
            try? screenshot.pngRepresentation.write(to: folder.appendingPathComponent(name + ".png"))
        }
    }

    /// Every label in ONE accessibility snapshot of the detail sheet, in
    /// order. The detail's List is the only collection view on screen (the
    /// host is a ScrollView), so the matrix behind it is excluded.
    private func detailLabels(_ app: XCUIApplication) -> [String] {
        let list = app.collectionViews.firstMatch
        guard list.exists, let root = try? list.snapshot() else { return [] }
        var out: [String] = []
        func walk(_ node: XCUIElementSnapshot) {
            if !node.label.isEmpty { out.append(node.label) }
            node.children.forEach(walk)
        }
        walk(root)
        return out
    }

    /// The headline value: the first label after the question and option
    /// labels (the summary section draws question, option, then value). The
    /// exact percent and source rows carry percentages too, so position is
    /// what identifies it.
    private static func headline(_ labels: [String], _ subject: Subject) -> String? {
        guard let q = labels.firstIndex(of: subject.question),
              let o = labels[(q + 1)...].firstIndex(of: subject.option),
              labels.indices.contains(o + 1) else { return nil }
        return labels[o + 1]
    }

    func testTheOpenGameOrSeriesSheetFollowsChangesRemovalAndRestoration() throws {
        let env = ProcessInfo.processInfo.environment
        guard let dir = env["BL10238_DIR"], !dir.isEmpty else {
            throw XCTSkip("BL10238_DIR not set — the mounted currentness exercise needs its input directory.")
        }
        let scope = env["BL10238_SCOPE"] ?? "game"
        let subject = try XCTUnwrap(Self.subjects[scope], "BL10238_SCOPE must be game or series, not '\(scope)'.")
        let run = env["BL10238_RUN"] ?? "unnamed"
        let shots = URL(fileURLWithPath: dir).deletingLastPathComponent()
            .appendingPathComponent("shots-\(run)-\(scope)")
        let app = UITestLaunch.launchApp(extra: ["-launch_question_matrix_10238_directory", dir])
        print("10238M_PLAN run=\(run) scope=\(scope) dir=\(dir)")

        let phase = app.staticTexts["BL10238Phase"]
        XCTAssertTrue(phase.waitForExistence(timeout: UITestLaunch.launchTimeout), "The DEBUG host never drew.")
        expectation(for: NSPredicate(format: "label == %@", Self.phases[0]), evaluatedWith: phase)
        waitForExpectations(timeout: UITestLaunch.contentTimeout)
        guard phase.label == Self.phases[0] else {
            shot(app, "10238M-\(run)-\(scope)-00-not-ready", into: shots)
            XCTFail("Host not ready: phase '\(phase.label)'.")
            return
        }

        // Run first: its 12-second allowance is for opening the option.
        let runButton = app.buttons["Run changes, then open a Game or Series option"]
        XCTAssertTrue(runButton.isEnabled, "Run is disabled on a ready host.")
        runButton.tap()
        let started = Date()

        let prefix = "\(subject.question), \(subject.option), "
        let cell = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", prefix)).firstMatch
        XCTAssertTrue(cell.waitForExistence(timeout: 5), "No '\(prefix)…' option in the \(scope) section.")
        for _ in 0..<4 where !cell.isHittable {
            app.scrollViews.firstMatch.swipeUp(velocity: .slow)
        }
        let cellLabel = cell.label
        cell.tap()
        let close = app.buttons["Close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5), "Tapping the option opened no detail.")
        let title = app.navigationBars[subject.sheetTitle]
        XCTAssertTrue(title.waitForExistence(timeout: 3), "The detail is not titled '\(subject.sheetTitle)'.")
        let openedAfter = Date().timeIntervalSince(started)
        print("10238M_OPEN run=\(run) scope=\(scope) cell='\(cellLabel)' openedAfter=\(String(format: "%.1f", openedAfter))s")
        XCTAssertLessThan(openedAfter, 11, "The detail opened after the host's first step could have fired.")

        var table: [String] = []
        for (index, name) in Self.phases.enumerated() {
            if index > 0 {
                let reached = NSPredicate(format: "label == %@", name)
                let wait = XCTNSPredicateExpectation(predicate: reached, object: phase)
                let result = XCTWaiter().wait(for: [wait], timeout: index == 1 ? 20 : 12)
                guard result == .completed else {
                    shot(app, "10238M-\(run)-\(scope)-\(index + 1)-phase-stuck", into: shots)
                    XCTFail("Phase never reached '\(name)'; host reads '\(phase.label)'.")
                    break
                }
                // The phase is set AFTER both payloads are adopted; let SwiftUI draw.
                usleep(700_000)
            }
            let labels = detailLabels(app)
            let removed = labels.contains(Self.removedSentence)
            let value = Self.headline(labels, subject)
            let sheetUp = close.exists
            let sameScope = title.exists
            let sibling = Self.siblingLabels.first(where: labels.contains)
            shot(app, "10238M-\(run)-\(scope)-\(String(format: "%02d", index + 1))-\(name)", into: shots)

            let want = subject.expected[index]
            var misses: [String] = []
            if !sheetUp { misses.append("sheet closed") }
            if !sameScope { misses.append("sheet title moved off '\(subject.sheetTitle)'") }
            if let sibling { misses.append("sheet shows the sibling's '\(sibling)'") }
            if want == Self.removedSentence {
                if !removed { misses.append("unavailable sentence missing; value '\(value ?? "nil")'") }
                if value != nil { misses.append("removed question still prints '\(value!)'") }
            } else {
                if removed { misses.append("unexpected unavailable sentence") }
                if value != want { misses.append("value '\(value ?? "nil")', want '\(want)'") }
            }
            let verdict = misses.isEmpty ? "PASS" : "FAIL"
            print("10238M_STEP run=\(run) scope=\(scope) \(name) \(verdict) value=\(value ?? "nil") unavailable=\(removed) sheet=\(sheetUp) labels=\(labels)\(misses.isEmpty ? "" : " misses=\(misses)")")
            table.append("\(name)=\(verdict)")
            XCTAssertTrue(misses.isEmpty, "\(name): \(misses.joined(separator: "; "))")
        }
        print("10238M_RECEIPT run=\(run) scope=\(scope) \(table.joined(separator: " ")) ui_read=sheet_labels voiceover=NOT_CLAIMED phone=NOT_CLAIMED")
    }
}
