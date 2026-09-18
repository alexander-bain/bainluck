import XCTest
@testable import Bain_Luck

/// #4838 — **the ladder card's "… 24H" tag stops printing SUP / CHA / STA.**
///
/// THE SPECIMENS, read off `/api/playoffs/{mlb,nfl,nba,nhl}` by native/097 on
/// 2026-09-10 and re-read unchanged by native/230 on 2026-09-18. Every league
/// serves four columns and the LAST one — the one the tag is fed, via
/// `ordered.last` in `LadderCardView.init(gridTeam:columns:)` — is `key ==
/// "championship"` in all four. Only its label differs:
///
///     league  order=4 key        order=4 label     tag printed
///     MLB     championship       World Series      WS  24H   <- the only match
///     NFL     championship       Super Bowl        SUP 24H
///     NBA     championship       Champion          CHA 24H
///     NHL     championship       Stanley Cup       STA 24H
///
/// The old map was keyed on `label.uppercased()` and knew `WORLD SERIES`,
/// `PLAYOFFS` and `DIVISION`. So one league matched, three fell through to a
/// `prefix(3)` truncation, and `PLAYOFFS` was dead on arrival — the served label
/// is `Make Playoffs` and never equalled it.
///
/// There were no tests on `LadderCardView` at all when this was filed, which is
/// how a map that worked for exactly one of four leagues shipped and stayed.
final class ALadderDeltaTagNamesTheRung4838Tests: XCTestCase {

    /// The four leagues' real last column, verbatim from the payload above.
    /// Driving the assertions off this table rather than off prose is the point:
    /// if the API renames a column, the fix is to re-measure and edit this table.
    private static let lastColumnByLeague: [(league: String, key: String, label: String)] = [
        ("MLB", "championship", "World Series"),
        ("NFL", "championship", "Super Bowl"),
        ("NBA", "championship", "Champion"),
        ("NHL", "championship", "Stanley Cup"),
    ]

    /// Every column all four leagues serve, in order — for the properties that must
    /// hold whichever column a future reorder puts last.
    private static let everyServedColumn: [(key: String, label: String)] = [
        ("make_playoffs", "Make Playoffs"),
        ("division", "Division"),
        ("conference", "Conference"),
        ("pennant", "AL / NL Champ"),
        ("championship", "World Series"),
        ("championship", "Super Bowl"),
        ("championship", "Champion"),
        ("championship", "Stanley Cup"),
    ]

    // MARK: - The defect

    /// The whole issue in one assertion: four leagues, one tag, no truncations.
    func testAllFourLeaguesNameTheChampionshipTheSameWay() {
        for spec in Self.lastColumnByLeague {
            XCTAssertEqual(
                shortDeltaLabel(key: spec.key, label: spec.label),
                "WIN 24H",
                "\(spec.league)'s ladder tag does not name its last rung (#4838)"
            )
        }
    }

    /// Named individually, because "three of four leagues" is the finding and a
    /// loop that silently iterated an empty table would assert nothing.
    func testTheThreeTruncationsAReaderActuallySawAreGone() {
        XCTAssertNotEqual(shortDeltaLabel(key: "championship", label: "Super Bowl"), "SUP 24H")
        XCTAssertNotEqual(shortDeltaLabel(key: "championship", label: "Champion"), "CHA 24H")
        XCTAssertNotEqual(shortDeltaLabel(key: "championship", label: "Stanley Cup"), "STA 24H")
        XCTAssertEqual(Self.lastColumnByLeague.count, 4, "the specimen table lost its rows")
    }

    // MARK: - Keyed on the key, which is the actual fix

    /// The mutant this kills is "go back to keying on the label". A label-keyed map
    /// can be made to pass `testAllFourLeaguesNameTheChampionshipTheSameWay` by
    /// listing the four spellings — and it would break again the next time a league
    /// words its trophy differently. Keying on the API's stable key cannot.
    func testAnUnseenChampionshipSpellingStillReadsAsTheChampionship() {
        XCTAssertEqual(
            shortDeltaLabel(key: "championship", label: "Larry O'Brien Trophy"),
            "WIN 24H",
            "the tag is keyed on the display label again, so a new trophy name breaks it (#4838)"
        )
        XCTAssertEqual(
            shortDeltaLabel(key: "championship", label: ""),
            "WIN 24H",
            "an absent label must not decide a column whose key is known"
        )
    }

    /// The converse: a non-championship column must NOT borrow the word. Without
    /// this, `deltaTagAbbreviation` returning a constant `"WIN"` would pass
    /// everything above.
    func testAColumnThatIsNotTheChampionshipDoesNotSayWin() {
        XCTAssertNotEqual(shortDeltaLabel(key: "make_playoffs", label: "Make Playoffs"), "WIN 24H")
        XCTAssertNotEqual(shortDeltaLabel(key: "conference", label: "Conference"), "WIN 24H")
        XCTAssertNotEqual(shortDeltaLabel(key: nil, label: "Anything"), "WIN 24H")
    }

    /// `division` keeps the word it already had, and it is the one case that proves
    /// the map has more than one entry.
    func testDivisionKeepsTheWordItAlreadyHad() {
        XCTAssertEqual(shortDeltaLabel(key: "division", label: "Division"), "DIV 24H")
    }

    // MARK: - The latent space bug, made unrepresentable

    /// MLB serves `AL / NL Champ`, whose `prefix(3)` is `"AL "`. That column is not
    /// last today, so the old code rendered `AL  24H` — a double space — only if a
    /// reorder made it last. Correctness that depends on ordering luck is not
    /// correctness, so it is asserted directly.
    func testThePennantColumnCannotRenderADoubleSpace() {
        let tag = shortDeltaLabel(key: "pennant", label: "AL / NL Champ")

        XCTAssertEqual(tag, "AL 24H")
        XCTAssertFalse(tag.contains("  "), "the tag rendered a double space (#4838)")
    }

    /// The property, over every column the API serves — not just the one that is
    /// last. A reorder must not be able to produce a malformed tag in any league.
    func testNoServedColumnCanProduceAMalformedTag() {
        for column in Self.everyServedColumn {
            let tag = shortDeltaLabel(key: column.key, label: column.label)

            XCTAssertFalse(tag.contains("  "), "double space from \(column.label) (#4838)")
            XCTAssertFalse(tag.hasPrefix(" "), "leading space from \(column.label) (#4838)")
            XCTAssertTrue(tag.hasSuffix(" 24H"), "\(column.label) lost the 24H suffix (#4838)")
            XCTAssertEqual(tag, tag.trimmingCharacters(in: .whitespaces),
                           "untrimmed tag from \(column.label) (#4838)")
        }
    }

    /// A label with nothing to abbreviate must drop the abbreviation entirely rather
    /// than emit a leading space. This is why `deltaTagAbbreviation` may return `""`.
    func testALabelWithNothingToAbbreviateDropsTheAbbreviation() {
        XCTAssertEqual(shortDeltaLabel(key: nil, label: "   "), "24H")
        XCTAssertEqual(shortDeltaLabel(key: nil, label: ""), "24H")
    }

    // MARK: - The dead cases the old map carried

    /// `PLAYOFFS` could never fire: the served label is `Make Playoffs`. Pinned so
    /// nobody re-adds a case for a string the API does not send.
    func testTheServedPlayoffsLabelIsNotTheStringTheOldMapWaitedFor() {
        let served = Self.everyServedColumn.first { $0.key == "make_playoffs" }

        XCTAssertEqual(served?.label, "Make Playoffs")
        XCTAssertNotEqual(served?.label.uppercased(), "PLAYOFFS",
                          "the old map's dead case would have been live after all")
    }

    // MARK: - The call site

    /// A source scan over the file that had the defect, positive and negative, so it
    /// fails both if the delegation goes away and if it is re-aimed at nothing.
    ///
    /// 🪤 COMMENT LINES ARE STRIPPED FIRST, and that is not tidiness. The first cut
    /// of this test scanned the raw file and went red on the fix — because the
    /// docstring explaining the bug quotes `case "PLAYOFFS"` while describing the
    /// dead case it removed. A scan that reads prose reports the defect it is
    /// standing on as still present, and the only way to satisfy it is to stop
    /// writing down what was wrong.
    func testTheLadderCardPassesTheColumnKeyAndNotJustTheLabel() throws {
        let project = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")

        let raw = try String(
            contentsOf: project.appendingPathComponent("Components/LadderCardView.swift"),
            encoding: .utf8
        )
        let code = raw
            .split(separator: "\n", omittingEmptySubsequences: false)
            .filter { !$0.trimmingCharacters(in: .whitespaces).hasPrefix("//") }
            .joined(separator: "\n")

        XCTAssertTrue(raw.contains("case \"PLAYOFFS\""),
                      "the docstring stopped recording the dead case, so the strip below proves nothing")
        XCTAssertFalse(code.contains("case \"PLAYOFFS\""),
                       "the dead case is back in CODE (#4838)")

        XCTAssertTrue(code.contains("func shortDeltaLabel(key: String?, label: String)"),
                      "this scan no longer aims at anything — re-aim it")
        XCTAssertTrue(code.contains("shortDeltaLabel(key: lastKey, label: $0)"),
                      "the ladder card stopped passing the column key (#4838)")
        XCTAssertFalse(code.contains("case \"WORLD SERIES\""),
                       "the label-keyed map is back (#4838)")
    }
}
