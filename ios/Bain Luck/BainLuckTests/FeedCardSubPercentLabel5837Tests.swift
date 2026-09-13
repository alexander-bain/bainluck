import XCTest
@testable import Bain_Luck

/// #5837 — a feed card stops printing `0%` for an outcome that is merely small.
///
/// The specimen is on production and in `artifacts-native-020/n140-1b-discover.png`:
/// the Amgen Irish Open card drew `0% McKibbin` for a golfer `GET /api/feed` served
/// at `0.004`, while the NCAAF game card one scroll above drew `<1%` for the same
/// magnitude. The integer was right; the sentence was not.
///
/// These tests pin BOTH halves, because the fix is only correct if one of them does
/// NOT move: `wholePercent` is the rendered-percent contract integer (#1933) and the
/// server fingerprints a graded card at that resolution, so a change there would
/// have been a contract change wearing a display fix's clothes.
final class FeedCardSubPercentLabel5837Tests: XCTestCase {

    // MARK: - The specimen

    func testASubPercentContenderIsBarelyAliveNotImpossible() {
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.004), "<1%")
    }

    /// The half that must NOT move. `0.004 → 0` is still the contract integer; the
    /// string beside it is what changed.
    func testTheContractIntegerIsUnchangedForTheSameSpecimen() {
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0.004), 0)
    }

    /// The whole runner-up strip of the shot, decoded from the payload the feed
    /// actually served at 07:2xZ 2026-09-13 — leader plus the three chasers the card
    /// draws (`golfers.dropFirst().prefix(3)`).
    func testTheShotsOwnCardReadsThreeRealNumbersAndOneMarker() throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let tournament = try dec.decode(FeedTournamentData.self, from: Data("""
        { "key": "amgen_irish_open", "name": "Amgen Irish Open",
          "tour": "dp_world", "schedule_status": "in_progress",
          "end_date": "2026-09-13T00:00:00Z", "marquee_whathit": false,
          "golfers": [
            {"name": "Shane Lowry", "probability": 0.833, "rank": 1, "movement_24h": 0.3472},
            {"name": "Jacob Skov Olesen", "probability": 0.131, "rank": 2, "movement_24h": 0.025},
            {"name": "Joaquin Niemann", "probability": 0.03, "rank": 3, "movement_24h": -0.02},
            {"name": "Tom McKibbin", "probability": 0.004, "rank": 4, "movement_24h": -0.0248}
          ] }
        """.utf8))

        let golfers = try XCTUnwrap(tournament.golfers)
        let hero = FeedProbabilityScale.percentLabel(fromFraction: golfers[0].probability)
        let strip = golfers.dropFirst().prefix(3).map {
            FeedProbabilityScale.percentLabel(fromFraction: $0.probability)
        }

        XCTAssertEqual(hero, "83%")
        XCTAssertEqual(strip, ["13%", "3%", "<1%"])
        XCTAssertFalse(strip.contains("0%"), "the defect was a flat 0% on a live contender")
    }

    // MARK: - The other end, and the reason the clamp lives on the value

    func testANearCertaintyIsNotPrintedAsAHundred() {
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.996), ">99%")
    }

    /// gotcha #23: an independent-binary field sums past 100%, and a card must not
    /// print `104%`. The clamp and the marker agree because the fraction is clamped
    /// once, before both.
    func testAnOverSummingFieldPrintsTheMarkerNotAnImpossiblePercent() {
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 1.04), ">99%")
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: -0.2), "<1%")
    }

    /// A three-decimal wire `0.000` is everything below 0.0005, not a measured
    /// impossibility — so it reads the same as any other sub-percent price.
    func testAWireZeroIsSubPercentNotAVerdict() {
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0), "<1%")
    }

    // MARK: - Everything in range still prints exactly the contract integer

    func testTheLabelIsTheContractIntegerEverywhereTheMarkerDoesNotApply() {
        for percent in 1...99 {
            let fraction = Double(percent) / 100
            XCTAssertEqual(
                FeedProbabilityScale.percentLabel(fromFraction: fraction),
                "\(FeedProbabilityScale.wholePercent(fromFraction: fraction))%",
                "the label must not re-round: \(fraction)")
        }
    }

    /// The rounding seam #2888 fixed is still the one in force — the label reports
    /// the integer `wholePercent` computes, not a second rounding of its own.
    func testTheLabelDoesNotReRoundTheHalfCentGrid() {
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.625), "63%")
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.6249), "62%")
    }

    /// The one band where the label and the contract integer legitimately differ,
    /// pinned because it is a real change and not a rounding accident: `0.006`
    /// ROUNDS to the integer 1 and IS less than one percent, so the card reads
    /// `<1%` where it used to read `1%`. The marker is a claim about the value —
    /// 0.6% is not 1% — and this is what `formatProbability` has always done on the
    /// other 77 surfaces. Exactly `0.01` is not below the line and prints `1%`.
    func testTheMarkerBandRunsToOnePercentAndStopsThere() {
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0.006), 1)
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.006), "<1%")
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.0099), "<1%")
        XCTAssertEqual(FeedProbabilityScale.percentLabel(fromFraction: 0.01), "1%")
    }

    // MARK: - No feed card prints the bare integer again

    /// The value tests above are the real guard; this is the anti-regression one.
    /// It is a source scan and so it is only worth what its population is worth —
    /// it reads the two card files that HAD the defect and asserts neither
    /// interpolates the contract integer into a percent string again.
    func testNeitherFeedCardInterpolatesTheContractIntegerIntoAPercentString() throws {
        let root = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()      // BainLuckTests
            .deletingLastPathComponent()      // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck/Components")

        let cards = ["DiscoverTournamentCard.swift", "DiscoverConceptCard.swift"]
        for card in cards {
            let url = root.appendingPathComponent(card)
            let source = try String(contentsOf: url, encoding: .utf8)
            // The file must exist and be the card, or the scan is vacuous.
            XCTAssertTrue(source.contains("FeedProbabilityScale"),
                          "\(card) no longer reads the feed scale — re-aim this scan")
            XCTAssertFalse(
                source.contains("wholePercent(fromFraction:"),
                "\(card) prints the contract integer directly again — use percentLabel (#5837)")
        }
    }
}
