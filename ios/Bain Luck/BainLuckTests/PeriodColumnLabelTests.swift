import XCTest
@testable import Bain_Luck

/// #3273 — "Score by period" headed a football game `Q14 · Q8 · Q5 · Q1`.
///
/// ESPN writes the game clock as a PREFIX (`"14:54 - 1st Quarter"`). Game Segments
/// had its own private parser that took the first number in the string, so three
/// of Alex's four columns were clock readings; the fourth (`Q1`) came from
/// `"End of 1st Quarter"`, which carries no clock, and was right by accident.
///
/// These tests call the real `PeriodLabel.columnLabel` on real production strings.
/// The specimen fixture below is the complete set of distinct `period` values the
/// API served for event 14793398 (Ball State @ Ohio State), in wire order.
final class PeriodColumnLabelTests: XCTestCase {

    /// Every distinct `espn_history[].period` served for 14793398, wire order.
    /// Fetched 2026-09-05 from `GET /api/events/14793398/history`.
    private static let specimenPeriods = [
        "14:54 - 1st Quarter", "8:47 - 1st Quarter", "5:52 - 1st Quarter",
        "1:23 - 1st Quarter", "End of 1st Quarter",
        "14:49 - 2nd Quarter", "12:08 - 2nd Quarter", "7:42 - 2nd Quarter",
        "3:59 - 2nd Quarter", "1:15 - 2nd Quarter",
        "15:00 - 3rd Quarter", "13:26 - 3rd Quarter", "11:29 - 3rd Quarter",
        "9:55 - 3rd Quarter", "8:20 - 3rd Quarter", "7:17 - 3rd Quarter",
        "6:17 - 3rd Quarter", "4:39 - 3rd Quarter", "End of 3rd Quarter",
        "15:00 - 4th Quarter", "14:16 - 4th Quarter", "9:47 - 4th Quarter",
        "8:05 - 4th Quarter", "5:52 - 4th Quarter", "1:55 - 4th Quarter",
        "Final",
    ]

    // MARK: - The defect

    func testTheSpecimenCollapsesToFourQuartersInOrder() {
        // The card keys its columns by label, first appearance wins. Twenty-six
        // distinct strings must yield the four quarters a football game has —
        // this is the exact computation that produced `Q14 · Q8 · Q5 · Q1 … Q4`.
        var columns: [String] = []
        for period in Self.specimenPeriods {
            let label = PeriodLabel.columnLabel(period)
            if !label.isEmpty, !columns.contains(label) { columns.append(label) }
        }

        XCTAssertEqual(columns, ["Q1", "Q2", "Q3", "Q4"])
    }

    func testNoClockReadingEverReachesAColumnHeader() {
        // The defect's signature: a label naming a quarter that does not exist.
        // 15:00 and 14:54 are clock values, and a football game has four periods.
        for period in Self.specimenPeriods {
            let label = PeriodLabel.columnLabel(period)
            XCTAssertFalse(
                ["Q5", "Q8", "Q12", "Q13", "Q14", "Q15", "Q0"].contains(label),
                "\(period) produced \(label), which is a clock reading"
            )
        }
    }

    func testTheClockIsStrippedEvenWhenItIsSubMinute() {
        // NBA/WNBA switch to a decimal clock inside the last minute ("5.4"),
        // which is a second numeric shape ahead of the separator.
        XCTAssertEqual(PeriodLabel.columnLabel("5.4 - 1st Quarter"), "Q1")
        XCTAssertEqual(PeriodLabel.columnLabel("0:00 - 3rd Quarter"), "Q3")
    }

    // MARK: - The noun comes from the data, not the sport key

    func testCollegeBasketballHalvesAndQuartersAreBothLabelledCorrectly() {
        // `basketball_ncaab` plays HALVES, `basketball_wncaab` plays QUARTERS, and
        // both share the `basketball_` prefix — so no sport-keyed branch can be
        // right for both. `columnLabel` takes no sport key at all.
        XCTAssertEqual(PeriodLabel.columnLabel("7:56 - 1st Half"), "1H")
        XCTAssertEqual(PeriodLabel.columnLabel("End of 2nd Half"), "2H")
        XCTAssertEqual(PeriodLabel.columnLabel("3:32 - 4th Quarter"), "Q4")
    }

    func testOvertimeIsNotConfusedWithItsClock() {
        // "7:12 - OT" used to render OT7, because "ot" was found by substring and
        // the number by scanning the whole string.
        XCTAssertEqual(PeriodLabel.columnLabel("7:12 - OT"), "OT")
        XCTAssertEqual(PeriodLabel.columnLabel("End of OT"), "OT")
        XCTAssertEqual(PeriodLabel.columnLabel("2:30 - 2OT"), "2OT")
    }

    // MARK: - The inning ladder's contract (#1831 / native/028)

    func testInningsStayParseableAsIntegers() {
        // `SegmentBreakdown` builds baseball's 1…N ladder with
        // `orderedLabels.compactMap(Int.init)`. An ordinal ("9th") would silently
        // empty that ladder, so the column vocabulary must stay bare digits —
        // this is why `columnLabel` exists rather than reusing `normalize`.
        for (raw, expected) in [
            ("Top 9th", 9), ("Bottom 3rd", 3), ("Middle 7th", 7),
            ("End 8th", 8), ("Top 11th", 11), ("Bottom 13th", 13),
        ] {
            let label = PeriodLabel.columnLabel(raw)
            XCTAssertEqual(Int(label), expected, "\(raw) -> \(label) is not an inning number")
        }
    }

    func testTheChartKeepsItsSelfExplainingOrdinal() {
        // The two vocabularies differ on purpose: the 22pt column holds digits,
        // the chart chip has room to say what the number means (ruling 5).
        XCTAssertEqual(PeriodLabel.normalize("Top 9th"), "9th")
        XCTAssertEqual(PeriodLabel.columnLabel("Top 9th"), "9")
    }

    // MARK: - Non-periods get no column

    func testStatusesAreNotPeriods() {
        // "Delayed" reached production as a column header on a card captioned
        // "Score by period". Halftime is a real state but not a scoring segment.
        for status in ["Halftime", "Delayed", "Postponed", "Final", "Pregame"] {
            XCTAssertEqual(
                PeriodLabel.columnLabel(status), "",
                "\(status) must not head a column"
            )
        }
    }

    func testAnUnreadableStringIsDroppedRatherThanPrinted() {
        // Fail closed: a header row is a claim about how the game is divided.
        XCTAssertEqual(PeriodLabel.columnLabel("Weather Delay - Lightning"), "")
        XCTAssertEqual(PeriodLabel.columnLabel(""), "")
    }

    // MARK: - The play card below the chart (same root cause)

    /// `GamePlayCardView` held a FOURTH copy of period formatting whose first
    /// branch (`p.count > 2`) returned ESPN's string untouched — and that string
    /// embeds the clock, which `timeDisplay` then appends again.
    ///
    /// These pin the rendered text exactly. The card sits below a full-height
    /// chart, so it is not in this session's screenshot; the string is the thing
    /// that was wrong, and it is asserted here rather than described.
    func testThePlayCardDoesNotPrintTheClockTwice() {
        // Live NCAAF, read from production 2026-09-05: Texas Tech @ Abilene
        // Christian carried period "5:10 - 2nd Quarter" with game_clock "5:10".
        // Measured: 144,376 of 175,274 rows with both (82.4%) have this shape.
        let point = GamePlayPoint(
            timestamp: "2026-09-06T00:01:23Z",
            homeProb: 0.94,
            awayProb: 0.06,
            period: "5:10 - 2nd Quarter",
            clock: "5:10"
        )

        XCTAssertEqual(point.timeDisplay, "Q2 · 5:10")
        XCTAssertFalse(
            point.timeDisplay.contains("- 2nd Quarter"),
            "the raw ESPN string reached the badge"
        )
    }

    func testThePlayCardStillShowsAClockWhenThePeriodIsUnreadable() {
        // The period drops out, the clock survives — the badge degrades to the
        // half it can still stand behind rather than disappearing.
        let point = GamePlayPoint(
            timestamp: "", homeProb: 0.5, awayProb: 0.5,
            period: "Halftime", clock: "0:00"
        )
        XCTAssertEqual(point.timeDisplay, "HT · 0:00")
    }

    // MARK: - The live status badge (hero + every sports feed card)

    func testTheLiveBadgeDoesNotPrintTheClockTwice() {
        // Photographed on Michigan @ Western Michigan, 2026-09-05: the hero
        // capsule read "5:11 - 1st Quarter 5:11".
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("5:11 - 1st Quarter"), "Q1")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("12:43 - 2nd Quarter"), "Q2")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("7:56 - 1st Half"), "1H")
    }

    func testTheLiveBadgeKeepsBaseballsHalfInning() {
        // "Bottom 7th" says which half; "7th" does not, and the capsule has the
        // room the 22pt scoreboard column does not. This is the one place the
        // badge vocabulary deliberately differs from the column's.
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("Bottom 7th"), "Bottom 7th")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("Top 9th"), "Top 9th")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("End 8th"), "End 8th")
    }

    func testTheLiveBadgeStillShortensEndOfQuarter() {
        // "End of 1st Quarter" must NOT be caught by the half-inning branch —
        // the digit requirement is what separates it from "End 8th".
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("End of 1st Quarter"), "Q1")
        XCTAssertEqual(PeriodLabel.liveBadgeLabel("Halftime"), "HT")
    }

    // MARK: - The closed vocabulary

    func testEveryLabelComesFromTheLegalSet() {
        // Measured over all 10,665 distinct (sport, period) pairs in production
        // on 2026-09-05, the output vocabulary is closed: football Q1-Q4;
        // basketball Q1-Q4, 1H, 2H, OT-4OT; baseball 1-13. Representatives of
        // every shape found there are replayed here.
        let realShapes = [
            "14:54 - 1st Quarter", "0:01 - 2nd Quarter", "5.4 - 3rd Quarter",
            "End of 4th Quarter", "7:56 - 1st Half", "0:00 - 2nd Half",
            "End of 2nd Half", "7:12 - OT", "0.0 - 2OT", "End of 3OT",
            "Top 1st", "Bottom 9th", "Middle 7th", "End 11th",
            "Halftime", "Delayed",
        ]
        let legal = try! NSRegularExpression(pattern: "^(Q[1-4]|1H|2H|OT|[2-9]OT|[0-9]{1,2})$")

        for raw in realShapes {
            let label = PeriodLabel.columnLabel(raw)
            if label.isEmpty { continue }
            let range = NSRange(label.startIndex..., in: label)
            XCTAssertNotNil(
                legal.firstMatch(in: label, range: range),
                "\(raw) produced \(label), which is outside the legal column vocabulary"
            )
        }
    }
}
