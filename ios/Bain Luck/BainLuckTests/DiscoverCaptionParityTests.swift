import XCTest
@testable import Bain_Luck

/// #4265 — native's half of the futures caption chain, graded against the record.
///
/// Web resolves a futures card's caption in `feedContextSnippet`; native resolves
/// it in `DiscoverCaption.feedCaption`. The two cannot meet inside one process —
/// one needs Node, the other needs Swift — so they meet in
/// `fixtures/discover/caption-chain-record-2026-09-09.json`, and each asserts in
/// its own runner that it reproduces every row.
///
/// The rows below are a LITERAL COPY of that record, not a file read: an XCTest
/// resolving a `#filePath`-relative JSON is host-filesystem-dependent, and
/// trading a verifiable duplicate for an unverifiable load path is a bad trade.
/// `frontend/e2e/contract/discoverCaptionChainParity.contract.test.js` parses
/// this table back out of this file and asserts it equals the record, so a row
/// edited here without the record fails there and a row edited in the record
/// without this file fails here. Mirrored, not merely coincident — the same
/// construction `CalibrationParityTests` uses for CAL-P043.
///
/// Standing notice 10: CI compiles no Swift, so the pass line for this file is
/// stated on the exact sha in the PR body.
final class DiscoverCaptionParityTests: XCTestCase {

    private struct Row {
        let name: String
        let contextSummary: String?
        let headline: String?
        let reason: String?
        let hookDescription: String?
        let expected: String
    }

    // MARK: - The record. Rows named `prod-` are real 2026-09-09 production cards.

    private static let rows: [Row] = [
        Row(name: "prod-stanley-cup-blank-in-app",
            contextSummary: "", headline: "Well off its opening price", reason: "",
            hookDescription: nil, expected: "Well off its opening price"),
        Row(name: "prod-wti-blank-in-app",
            contextSummary: "", headline: "Well off its opening price", reason: "",
            hookDescription: nil, expected: "Well off its opening price"),
        Row(name: "prod-pantoja-blank-in-app",
            contextSummary: "", headline: "Off its opening price", reason: "",
            hookDescription: nil, expected: "Off its opening price"),
        Row(name: "prod-hasan-piker-hook-promoted",
            contextSummary: "", headline: "Well off its opening price", reason: "",
            hookDescription: "Hasan Piker's unexpected arrest in 2026 has sent shockwaves through the online political commentary community.",
            expected: "Well off its opening price"),
        Row(name: "prod-world-series-headline-beats-reason",
            contextSummary: "", headline: "Los Angeles Dodgers leads at 31%",
            reason: "Los Angeles Dodgers (31%) leads MLB World Series Winner",
            hookDescription: nil, expected: "Los Angeles Dodgers leads at 31%"),
        Row(name: "context-summary-wins-when-present",
            contextSummary: "Traders moved 12 points on this overnight.",
            headline: "Los Angeles Dodgers leads at 31%",
            reason: "Los Angeles Dodgers (31%) leads MLB World Series Winner",
            hookDescription: "A hook nobody should see here.",
            expected: "Traders moved 12 points on this overnight."),
        Row(name: "null-headline-falls-to-reason",
            contextSummary: "", headline: nil,
            reason: "Marine Le Pen (36%) leads Next French Presidential Election",
            hookDescription: "A hook nobody should see here.",
            expected: "Marine Le Pen (36%) leads Next French Presidential Election"),
        Row(name: "empty-headline-falls-to-reason",
            contextSummary: "", headline: "",
            reason: "Marine Le Pen (36%) leads Next French Presidential Election",
            hookDescription: "A hook nobody should see here.",
            expected: "Marine Le Pen (36%) leads Next French Presidential Election"),
        Row(name: "hook-is-the-last-resort-not-the-second",
            contextSummary: "", headline: "", reason: "",
            hookDescription: "As the Pokémon franchise continues to surge in popularity, collectors are watching the market.",
            expected: "As the Pokémon franchise continues to surge in popularity, collectors are watching the market."),
        Row(name: "all-null-is-the-empty-state",
            contextSummary: nil, headline: nil, reason: nil,
            hookDescription: nil, expected: ""),
        Row(name: "all-empty-is-the-empty-state",
            contextSummary: "", headline: "", reason: "",
            hookDescription: "", expected: ""),
        Row(name: "whitespace-only-is-not-a-caption",
            contextSummary: "   ", headline: "\n",
            reason: "Above 5 (48%) leads Israeli legislative election",
            hookDescription: nil,
            expected: "Above 5 (48%) leads Israeli legislative election"),
    ]

    // MARK: - Tests

    func testRecordIsPresentAndHasNotBeenSilentlyEmptied() {
        // A parity suite that iterates zero rows passes for the wrong reason.
        XCTAssertEqual(Self.rows.count, 12)
        XCTAssertEqual(Self.rows.filter { $0.name.hasPrefix("prod-") }.count, 5)
    }

    func testNativeReproducesEveryRowOfTheSharedRecord() {
        for row in Self.rows {
            XCTAssertEqual(
                DiscoverCaption.feedCaption(
                    contextSummary: row.contextSummary,
                    headline: row.headline,
                    reason: row.reason,
                    hookDescription: row.hookDescription
                ),
                row.expected,
                "row \(row.name)"
            )
        }
    }

    func testTheThreeCardsThatWereBlankInTheAppAreNowCaptioned() {
        // #4265's reader-visible claim, asserted on its own rather than inside
        // the loop. Before the fix each of these resolved to "" at the FIRST
        // rung — `context_summary` was an empty string and `??` is nil
        // coalescing, so it never reached `headline`.
        let blanks = Self.rows.filter { $0.name.hasSuffix("-blank-in-app") }
        XCTAssertEqual(blanks.count, 3)
        for row in blanks {
            let caption = DiscoverCaption.feedCaption(
                contextSummary: row.contextSummary,
                headline: row.headline,
                reason: row.reason,
                hookDescription: row.hookDescription
            )
            XCTAssertTrue(
                caption.lowercased().contains("off its opening price"),
                "row \(row.name) captioned \(caption)"
            )
        }
    }

    func testNilCoalescingWouldStillFailThisSuite() {
        // The control. This reproduces the OLD expression exactly; if someone
        // reverts `DiscoverCaption` to `??` this stays as the record of what
        // that operator does to an empty string, and the row above goes red.
        let old = "" as String? ?? "Well off its opening price" as String?
        XCTAssertEqual(old, "", "`??` treats an empty string as present — that was the bug")
        XCTAssertEqual(
            DiscoverCaption.feedCaption(
                contextSummary: "", headline: "Well off its opening price",
                reason: "", hookDescription: nil
            ),
            "Well off its opening price"
        )
    }
}
