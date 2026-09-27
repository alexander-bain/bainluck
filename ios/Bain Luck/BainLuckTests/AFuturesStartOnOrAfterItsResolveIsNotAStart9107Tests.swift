import XCTest
@testable import Bain_Luck

/// #9107 — the iPhone Market Details card read "Starts Oct 25, 2027" over
/// "Resolves Oct 25, 2026" (futures 109952, Kalshi `KXBRPRES-26`).
///
/// The wire values below are the specimen's served values, verbatim. The
/// controls are the reason the rule is "strictly before the resolve INSTANT"
/// and not something blunter: a real start (DataGolf) keeps its row, a same-day
/// game-shaped start keeps its row, and a market with no resolve date keeps the
/// pre-#9107 behaviour.
final class AFuturesStartOnOrAfterItsResolveIsNotAStart9107Tests: XCTestCase {

    // Specimen: futures 109952, served 2026-09-27.
    private let specimenCommence = "2027-10-25T14:00:00+00:00"
    private let specimenResolves = "2026-10-25T14:00:00+00:00"

    func test_the_specimen_was_printable_before_the_fix() {
        // Strawman: the pre-#9107 condition was `commenceTime.asDate != nil`.
        // If this parse failed, the tests below would pass for the wrong reason.
        XCTAssertNotNil(specimenCommence.asDate)
        XCTAssertNotNil(specimenResolves.asDate)
    }

    func test_a_start_after_the_resolve_is_not_shown() {
        XCTAssertNil(FuturesStartDate.shown(commenceTime: specimenCommence,
                                            resolutionDate: specimenResolves))
    }

    func test_a_start_equal_to_the_resolve_is_not_shown() {
        // 4,939 open Kalshi markets carry commence == resolution.
        XCTAssertNil(FuturesStartDate.shown(commenceTime: specimenResolves,
                                            resolutionDate: specimenResolves))
    }

    func test_a_real_start_keeps_its_row_and_its_value() {
        // Control, DataGolf shape: Starts Sep 30 / Resolves Oct 4.
        let commence = "2026-09-30T00:00:00+00:00"
        let shown = FuturesStartDate.shown(commenceTime: commence,
                                           resolutionDate: "2026-10-04T00:00:00+00:00")
        XCTAssertEqual(shown, commence.asDate)
    }

    func test_a_same_day_start_before_the_resolve_instant_keeps_its_row() {
        // Instants, not days: a day-level compare would drop this true row.
        let commence = "2026-10-25T19:00:00+00:00"
        let shown = FuturesStartDate.shown(commenceTime: commence,
                                           resolutionDate: "2026-10-25T23:00:00+00:00")
        XCTAssertEqual(shown, commence.asDate)
    }

    func test_one_second_before_the_resolve_is_still_a_start() {
        let commence = "2026-10-25T13:59:59+00:00"
        XCTAssertEqual(FuturesStartDate.shown(commenceTime: commence,
                                              resolutionDate: specimenResolves),
                       commence.asDate)
    }

    func test_no_resolve_date_keeps_the_start() {
        let commence = "2026-09-30T00:00:00+00:00"
        XCTAssertEqual(FuturesStartDate.shown(commenceTime: commence, resolutionDate: nil),
                       commence.asDate)
        XCTAssertEqual(FuturesStartDate.shown(commenceTime: commence, resolutionDate: "soon"),
                       commence.asDate)
    }

    func test_fractional_seconds_on_either_side_are_compared() {
        XCTAssertNil(FuturesStartDate.shown(commenceTime: "2027-10-25T14:00:00.123+00:00",
                                            resolutionDate: "2026-10-25T14:00:00.000+00:00"))
    }

    func test_no_start_is_no_row() {
        XCTAssertNil(FuturesStartDate.shown(commenceTime: nil, resolutionDate: specimenResolves))
        XCTAssertNil(FuturesStartDate.shown(commenceTime: "", resolutionDate: specimenResolves))
    }

    func test_the_view_routes_its_starts_row_through_the_rule() {
        // The helper is inert if the card still reads `commenceTime.asDate` itself.
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Views/FuturesDetailView.swift")
        guard let src = try? String(contentsOf: url, encoding: .utf8) else {
            return XCTFail("could not read \(url.path)")
        }
        XCTAssertTrue(src.contains("FuturesStartDate.shown("))
        XCTAssertFalse(src.contains("if let commence = market.commenceTime, let date = commence.asDate"))
    }
}
