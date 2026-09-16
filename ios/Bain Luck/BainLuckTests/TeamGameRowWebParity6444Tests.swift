import XCTest
@testable import Bain_Luck

/// #6444 — the two sentences a finished team-page row can say exist on two
/// runtimes, so this test READS the other one.
///
/// Notice 35: a game card is one family everywhere. The phone's Recent row now
/// prints the same grade-our-call line the web card has printed since L2-158 —
/// "we had them at 72%", or "Upset — beat 78% odds" when the team won from a
/// price web treats as against them. **A phrase living in TypeScript and Swift is
/// the #1620 shape** (twelve instances and counting), and the repair that worked
/// for `SettledQuote` is the one used here: the test reads
/// `frontend/components/TeamGameCards.tsx` and asserts the Swift matches it,
/// rather than restating the constant on trust and calling that parity.
///
/// The upset threshold is read the same way. A number agreed by hand across two
/// files is a number that drifts: the web card could move to 0.30 and every
/// native test would still pass while the same game read "Upset" on one screen
/// and "we had them at 32%" on the other.
///
/// SCOPE: this test only READS the web file. `frontend/**` is ux's (notice 41).
/// If this ever fails because the web card changed, the finding goes to ux — the
/// fix is a conversation, not an edit to their file from here.
final class TeamGameRowWebParity6444Tests: XCTestCase {

    private var webCardSource: String {
        get throws {
            let url = URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()   // BainLuckTests
                .deletingLastPathComponent()   // Bain Luck (project dir)
                .deletingLastPathComponent()   // ios
                .deletingLastPathComponent()   // repo root
                .appendingPathComponent("frontend/components/TeamGameCards.tsx")
            return try String(contentsOf: url, encoding: .utf8)
        }
    }

    /// The repo-relative read resolves. Stated as its own assertion so a moved
    /// file reads as "the path is wrong", not as a parity failure.
    func testTheWebCardIsWhereWeThinkItIs() throws {
        XCTAssertTrue(try webCardSource.contains("export function RecentGameCard"))
    }

    /// Both sentences, character for character.
    func testTheTwoSentencesMatchTheWebCard() throws {
        let source = try webCardSource
        for phrase in ["we had them at ", "Upset — beat "] {
            XCTAssertTrue(
                source.contains(phrase),
                "web no longer says \"\(phrase)\" — the phone still does; route to ux"
            )
        }
        // And the phone's copy of each, read out of the view rather than retyped
        // in this test.
        let viewSource = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()
                .deletingLastPathComponent()
                .appendingPathComponent("Bain Luck/Views/TeamDetailView.swift"),
            encoding: .utf8
        )
        XCTAssertTrue(viewSource.contains("we had them at \\(formatPct(pre))"))
        XCTAssertTrue(viewSource.contains("Upset — beat \\(formatPct(1 - pre)) odds"))
    }

    /// The upset threshold, parsed out of the web card's own condition
    /// (`teamWon && pre < 0.35`).
    func testTheUpsetThresholdIsTheWebCardsNumber() throws {
        let source = try webCardSource
        let pattern = try NSRegularExpression(pattern: #"pre\s*<\s*([0-9.]+)"#)
        let range = NSRange(source.startIndex..<source.endIndex, in: source)
        let matches = pattern.matches(in: source, range: range)
        XCTAssertEqual(matches.count, 1, "exactly one upset threshold is expected in the web card")
        let match = try XCTUnwrap(matches.first)
        let captured = try XCTUnwrap(Range(match.range(at: 1), in: source))
        let webThreshold = try XCTUnwrap(Double(source[captured]))

        XCTAssertEqual(
            TeamGameRow.upsetThreshold, webThreshold, accuracy: 0.0001,
            "web calls an upset below \(webThreshold); the phone says "
            + "\(TeamGameRow.upsetThreshold), so one game would read two ways"
        )
    }

    /// Web refuses to print the line without a stateable result, and so do we.
    /// Asserted against its source so the reason cannot quietly leave web alone.
    func testWebAlsoGatesTheLineOnAResult() throws {
        let source = try webCardSource
        XCTAssertTrue(
            source.contains("{result && pre !== null"),
            "web ungated its grade-our-call line; the phone's gate would then be "
            + "the odd one out, which is the disagreement notice 35 forbids"
        )
    }
}
