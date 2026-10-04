import XCTest

/// #10236's mounted change clause, read off the OPEN sheet: with Aaron Judge's
/// "2 or more hits" detail open on the real matrix, the DEBUG host
/// (`EventPropsMatrixCurrentnessActivation10236`) feeds ten retained inputs
/// through the real `GameMarketsPriceDelivery` and reconciler. After each step
/// this test reads what the reader sees on that same sheet — the chance, the
/// "Updated …" age, or the unavailable sentence — and only then compares it
/// with the retained expectation. The host's phase label says WHEN to read; it
/// is never the thing read.
///
///   `BL10236_DIR`  simulator-readable directory holding the ten inputs. Absent
///                  ⇒ skip (this is a rig test, not part of any standing gate).
///   `BL10236_RUN`  a name for the log lines only (`retained`, `freeze01`, …).
///
/// Assertions are soft (`continueAfterFailure = true`) so a negative control
/// reports EVERY step it fails, not just the first. A freeze01 copy must fail
/// steps 02–10's expectations; a hold09 copy must fail step 10 only.
///
/// Not claimed: VoiceOver focus (XCUITest cannot read it), served or phone
/// behaviour (the inputs are synthetic), and the time-only move of step 05 —
/// "Updated" is wall-clock, and 20:10 vs 20:20 render the same hour bucket.
final class MountedQuestionDetailFollowsEvidence10236Tests: XCTestCase {

    private static let phases = [
        "01-initial", "02-newer-changed", "03-older-refused",
        "04-repeated-heartbeat-no-restamp", "05-equal-value-new-observation",
        "06-equal-revision-conflict-refused", "07-explicit-withdrawal",
        "08-withdrawn-old-quote-no-resurrection", "09-new-evidence-restoration",
        "10-selected-question-removed"
    ]
    private static let unavailable = "This question isn't being offered right now."

    /// What the reader must see after each step. `chance` nil = no percentage
    /// anywhere on the sheet; `removed` = the unavailable sentence; `sameAgeAs`
    /// = the "Updated" text must equal that earlier step's (a refused input
    /// keeps the prior quote time; a heartbeat never restamps it).
    private struct Expect { let chance: String?; let removed: Bool; let sameAgeAs: Int? }
    private static let expected: [Expect] = [
        Expect(chance: "48%", removed: false, sameAgeAs: nil),
        Expect(chance: "55%", removed: false, sameAgeAs: nil),
        Expect(chance: "55%", removed: false, sameAgeAs: 1),
        Expect(chance: "55%", removed: false, sameAgeAs: 1),
        Expect(chance: "55%", removed: false, sameAgeAs: nil),
        Expect(chance: "55%", removed: false, sameAgeAs: 4),
        Expect(chance: nil, removed: false, sameAgeAs: nil),
        Expect(chance: nil, removed: false, sameAgeAs: nil),
        Expect(chance: "57%", removed: false, sameAgeAs: nil),
        Expect(chance: nil, removed: true, sameAgeAs: nil),
    ]

    override func setUp() {
        super.setUp()
        continueAfterFailure = true
    }

    /// Attached, and also written beside the inputs (`<dir>/../shots-<run>/`):
    /// the simulator's data area is host-readable, so the PNGs survive a
    /// result bundle that xcodebuild never finalises.
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

    /// Every label in ONE accessibility snapshot of the detail sheet, any
    /// element type: the summary is a combined element, so its chance and age
    /// arrive in one label. The detail's List is the only collection view on
    /// screen (the host is a ScrollView), so the matrix behind it is excluded.
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

    /// The chance the summary prints: the second part of its combined label
    /// ("2+ hits, 55%, 55.0%, …" → "55%", "2+ hits, —" → "—"). Read from the
    /// summary alone — scroll bars and source rows carry percentages too.
    private static func summaryChance(_ labels: [String]) -> String? {
        guard let summary = labels.first(where: { $0.hasPrefix("2+ hits, ") }) else { return nil }
        let parts = summary.components(separatedBy: ", ")
        return parts.count > 1 ? parts[1] : nil
    }

    /// The comparison row's current chance ("Pregame 38.0%, now 55.0%" → "55.0%").
    private static func comparisonNow(_ labels: [String]) -> String? {
        guard let row = labels.first(where: { $0.hasPrefix("Pregame ") && $0.contains(", now ") }),
              let r = row.range(of: ", now ") else { return nil }
        return String(row[r.upperBound...])
    }

    private static func age(_ labels: [String]) -> String? {
        for label in labels {
            if let r = label.range(of: "Updated [^,.]+ ago|Updated just now|Updated yesterday",
                                   options: .regularExpression) {
                return String(label[r])
            }
        }
        return nil
    }

    func testTheOpenDetailAdoptsNewerEvidenceRefusesStaleAndShowsWithdrawal() throws {
        let env = ProcessInfo.processInfo.environment
        guard let dir = env["BL10236_DIR"], !dir.isEmpty else {
            throw XCTSkip("BL10236_DIR not set — the mounted currentness exercise needs its input directory.")
        }
        let run = env["BL10236_RUN"] ?? "unnamed"
        let shots = URL(fileURLWithPath: dir).deletingLastPathComponent().appendingPathComponent("shots-\(run)")
        let app = UITestLaunch.launchApp(extra: ["-launch_during_matrix_10236_directory", dir])
        print("10236M_PLAN run=\(run) dir=\(dir)")

        let phase = app.staticTexts["BL10236Phase"]
        XCTAssertTrue(phase.waitForExistence(timeout: UITestLaunch.launchTimeout), "The DEBUG host never drew.")
        let ready = NSPredicate(format: "label == %@", Self.phases[0])
        expectation(for: ready, evaluatedWith: phase)
        waitForExpectations(timeout: UITestLaunch.contentTimeout)
        guard phase.label == Self.phases[0] else {
            shot(app, "10236M-\(run)-00-not-ready", into: shots)
            XCTFail("Host not ready: phase '\(phase.label)'.")
            return
        }

        // Run first: its 12-second allowance is for opening the question.
        let runButton = app.buttons["Run changes, then open Judge 2+ hits"]
        XCTAssertTrue(runButton.isEnabled, "Run is disabled on a ready host.")
        runButton.tap()
        let started = Date()

        let cell = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "Aaron Judge, 2 or more hits")).firstMatch
        XCTAssertTrue(cell.waitForExistence(timeout: 5), "No 'Aaron Judge, 2 or more hits' cell in the matrix.")
        for _ in 0..<4 where !cell.isHittable {
            app.scrollViews.firstMatch.swipeUp(velocity: .slow)
        }
        let cellLabel = cell.label
        cell.tap()
        let close = app.buttons["Close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5), "Tapping the cell opened no detail.")
        let title = app.navigationBars["Aaron Judge"]
        XCTAssertTrue(title.waitForExistence(timeout: 3), "The detail is not titled 'Aaron Judge'.")
        let openedAfter = Date().timeIntervalSince(started)
        print("10236M_OPEN run=\(run) cell='\(cellLabel)' openedAfter=\(String(format: "%.1f", openedAfter))s")
        XCTAssertLessThan(openedAfter, 11, "The detail opened after the host's first step could have fired.")

        var ages: [String?] = []
        var table: [String] = []
        for (index, name) in Self.phases.enumerated() {
            if index > 0 {
                let reached = NSPredicate(format: "label == %@", name)
                let wait = XCTNSPredicateExpectation(predicate: reached, object: phase)
                let result = XCTWaiter().wait(for: [wait], timeout: index == 1 ? 20 : 12)
                guard result == .completed else {
                    shot(app, "10236M-\(run)-\(index + 1)-phase-stuck", into: shots)
                    XCTFail("Phase never reached '\(name)'; host reads '\(phase.label)'.")
                    break
                }
                // The phase is set AFTER delivery publishes; let SwiftUI draw it.
                usleep(700_000)
            }
            let labels = detailLabels(app)
            let chanceShown = Self.summaryChance(labels)
            let nowShown = Self.comparisonNow(labels)
            let age = Self.age(labels)
            let removed = labels.contains(Self.unavailable)
            let sheetUp = close.exists
            let sameSubject = title.exists || removed
            ages.append(age)
            shot(app, "10236M-\(run)-\(String(format: "%02d", index + 1))-\(name)", into: shots)

            let want = Self.expected[index]
            var misses: [String] = []
            if !sheetUp { misses.append("sheet closed") }
            if !sameSubject { misses.append("title moved off Aaron Judge") }
            if let chance = want.chance {
                let exact = chance.replacingOccurrences(of: "%", with: ".0%")
                if chanceShown != chance { misses.append("summary shows '\(chanceShown ?? "nil")', want '\(chance)'") }
                if nowShown != exact { misses.append("comparison 'now' is '\(nowShown ?? "nil")', want '\(exact)'") }
                if removed { misses.append("reads unavailable") }
            } else if !want.removed {
                // Withdrawn: the SAME question stays open and prints no chance.
                if chanceShown != "\u{2014}" { misses.append("summary shows '\(chanceShown ?? "nil")', want '\u{2014}'") }
                if nowShown != nil { misses.append("comparison still prints 'now \(nowShown!)'") }
            } else if chanceShown != nil || nowShown != nil {
                misses.append("removed question still prints a chance")
            }
            if want.removed != removed {
                misses.append(want.removed ? "unavailable sentence missing" : "unexpected unavailable sentence")
            }
            if let earlier = want.sameAgeAs, ages.indices.contains(earlier), ages[earlier] != age {
                misses.append("age '\(age ?? "nil")' != step \(earlier + 1)'s '\(ages[earlier] ?? "nil")'")
            }
            if age == "Updated just now" { misses.append("age restamped to now") }
            let verdict = misses.isEmpty ? "PASS" : "FAIL"
            let line = "10236M_STEP run=\(run) \(name) \(verdict) summary=\(chanceShown ?? "nil") now=\(nowShown ?? "nil") age=\(age ?? "nil") unavailable=\(removed) sheet=\(sheetUp) labels=\(labels)\(misses.isEmpty ? "" : " misses=\(misses)")"
            print(line)
            table.append("\(name)=\(verdict)")
            XCTAssertTrue(misses.isEmpty, "\(name): \(misses.joined(separator: "; "))")
        }
        print("10236M_RECEIPT run=\(run) \(table.joined(separator: " ")) ui_read=sheet_labels voiceover=NOT_CLAIMED phone=NOT_CLAIMED")
    }
}
