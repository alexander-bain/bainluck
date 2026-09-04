import XCTest
@testable import Bain_Luck

/// #2888 — every golf tournament card on Discover printed **0%**.
///
/// `DiscoverTournamentCard` rendered `Int(probability.rounded())%` on a payload
/// that is a 0–1 fraction. Measured on the live feed of 2026-09-03, the card
/// Alex would have seen on page one:
///
/// ```
/// {"name": "Angel Ayora",      "probability": 0.089, "rank": 1}
/// {"name": "Eugenio Chacarra", "probability": 0.069, "rank": 2}
/// {"name": "Harry Hall",       "probability": 0.066, "rank": 3}
/// ```
///
/// `Int(0.089.rounded())` is `0`. Not a bad payload — the backend passes
/// `outcome.current_probability` through untouched, and that column is a
/// fraction everywhere. A golf favourite would have to clear 50% to print even
/// `1%`, so the hero number on that card was **always** wrong.
///
/// The suite could not see it: `TournamentCardPresentationTests` and the card's
/// own `#Preview` both build fixtures with `"probability": 62` — whole percents,
/// a shape no server sends. Green on a payload that does not exist.
///
/// So these tests are written against the REAL numbers, and the conversion they
/// pin lives in one place for both cards that do it (gotcha #129 — the concept
/// card had quietly corrected the same rule, which is how the two came to
/// disagree in production).
final class FeedProbabilityScaleTests: XCTestCase {

    // MARK: - The reported defect

    /// The three golfers from the screenshot, at the numbers the API served.
    func testGolfFieldProbabilitiesDoNotAllCollapseToZero() {
        let served = [0.089, 0.069, 0.066]
        let rendered = served.map { FeedProbabilityScale.wholePercent(fromFraction: $0) }
        XCTAssertEqual(rendered, [9, 7, 7])
        XCTAssertFalse(rendered.contains(0), "the defect: every golf card printed 0%")
        // The old expression, kept as the thing that must never come back.
        XCTAssertEqual(served.map { Int($0.rounded()) }, [0, 0, 0])
    }

    func testWholePercentRoundsHalfAway() {
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0.625), 63)
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0.6249), 62)
    }

    func testEdgesAreExact() {
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0), 0)
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 1), 100)
    }

    /// An independent-binary field can sum past 100% (gotcha #23); a card must
    /// never print 104%, and a negative must never print at all.
    func testOutOfRangeIsClamped() {
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 1.04), 100)
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: -0.2), 0)
    }

    /// A sub-percent favourite is still a real reading, not a zero. Rounding is
    /// honest here — 0.4% genuinely is 0% at whole-percent resolution — but it
    /// must arrive there by rounding a percentage, not by truncating a fraction.
    func testSubPercentRoundsHonestly() {
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0.004), 0)
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: 0.006), 1)
    }

    // MARK: - Movement, the same bug one line down

    /// The card gated its mover line on `abs(move) >= 0.5` against a fraction —
    /// which is fifty percentage points, so the line was structurally dead.
    func testMovementIsReportedInPointsNotFractions() {
        XCTAssertEqual(
            try XCTUnwrap(FeedProbabilityScale.movementPoints(fromFraction: 0.023)),
            2.3, accuracy: 1e-9)
        XCTAssertEqual(
            try XCTUnwrap(FeedProbabilityScale.movementPoints(fromFraction: -0.011)),
            -1.1, accuracy: 1e-9)
    }

    func testAMaterialMoveIsNotGatedOutByTheOldFiftyPointThreshold() throws {
        // 2.3 points: material, and `abs(0.023) >= 0.5` was false.
        XCTAssertNotNil(FeedProbabilityScale.movementPoints(fromFraction: 0.023))
    }

    /// Sub-point noise is an ABSENCE, not a measured "+0" — the floor matches the
    /// backend's own materiality gate for the tournament reason line (0.01).
    func testSubPointNoiseIsSuppressedRatherThanRoundedToZero() {
        XCTAssertNil(FeedProbabilityScale.movementPoints(fromFraction: 0.004))
        XCTAssertNil(FeedProbabilityScale.movementPoints(fromFraction: -0.009))
        XCTAssertNotNil(FeedProbabilityScale.movementPoints(fromFraction: 0.01))
    }

    func testNoMovementIsNil() {
        XCTAssertNil(FeedProbabilityScale.movementPoints(fromFraction: nil))
        XCTAssertNil(FeedProbabilityScale.movementPoints(fromFraction: 0))
    }

    // MARK: - The two cards agree, by construction

    /// The concept card and the tournament card read the same field from the same
    /// endpoint and used to disagree about its scale. They now share the seam, so
    /// disagreement is unrepresentable rather than asserted against.
    func testBothCardsReadTheSameScaleForTheSameLiveTournamentPayload() throws {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let tournament = try dec.decode(FeedTournamentData.self, from: Data("""
        { "key": "omega_european_masters", "name": "Omega European Masters",
          "tour": "dp_world", "schedule_status": "upcoming",
          "end_date": "2026-09-06T00:00:00Z", "marquee_whathit": false,
          "golfers": [{"name": "Angel Ayora", "probability": 0.089, "rank": 1,
                       "movement_24h": null}] }
        """.utf8))
        let concept = try dec.decode(FeedConceptLeader.self, from: Data("""
        {"name": "Angel Ayora", "probability": 0.089, "movement_24h": null, "field_size": 30}
        """.utf8))

        let golfer = try XCTUnwrap(tournament.golfers?.first)
        XCTAssertEqual(
            FeedProbabilityScale.wholePercent(fromFraction: golfer.probability),
            FeedProbabilityScale.wholePercent(fromFraction: concept.probability))
        XCTAssertEqual(FeedProbabilityScale.wholePercent(fromFraction: golfer.probability), 9)
    }
}
