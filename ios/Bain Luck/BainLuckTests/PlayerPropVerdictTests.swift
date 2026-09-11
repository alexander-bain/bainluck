import XCTest
@testable import Bain_Luck

/// #4959 — a finished game's player props must print the verdict the SERVER already
/// computed, instead of re-deriving it locally against an alias table of five
/// basketball stats.
///
/// Measured before the fix, on the served `/game-markets` payload of 14 finished MLB
/// games (2026-09-10): the app rendered 928 prop rungs, the server had graded 481 of
/// them, and the app drew a verdict on **none** — every rung showed a forward-looking
/// "chance of hitting" on a game the box score had already answered.
///
/// These pin the pure `PlayerPropsCardView.rungVerdict(...)`. The first test is the
/// case the issue calls unreachable today: a rung the server graded, with NO box
/// score present at all.
final class PlayerPropVerdictTests: XCTestCase {

    private func verdict(
        servedActual: Double? = nil,
        servedHit: Bool? = nil,
        threshold: Double = 2.0,
        boxActual: Double? = nil
    ) -> PlayerPropsCardView.RungVerdict {
        PlayerPropsCardView.rungVerdict(
            servedActual: servedActual,
            servedHit: servedHit,
            threshold: threshold,
            boxActual: boxActual
        )
    }

    // MARK: - THE DEFECT: a served grade, no box score

    func testServedHitGradesWithNoBoxScoreAtAll() {
        // The exact row the app dropped: MLB total bases, graded by the server,
        // with nothing in `box_score_data` the alias table can reach.
        let v = verdict(servedActual: 3.0, servedHit: true, threshold: 2.0)
        XCTAssertEqual(v.hit, true, "a rung the server graded must draw a verdict")
        XCTAssertEqual(v.actual, 3.0)
    }

    func testServedMissGradesWithNoBoxScoreAtAll() {
        // A "–" is a verdict too. Withholding it is the same bug as withholding "✓".
        let v = verdict(servedActual: 0.0, servedHit: false, threshold: 1.0)
        XCTAssertEqual(v.hit, false)
        XCTAssertEqual(v.actual, 0.0)
    }

    // MARK: - The served grade wins, because it knows the orientation

    func testServedHitBeatsTheLocalGreaterThanComparison() {
        // An UNDER rung: the server grades `total < threshold` → hit. The local
        // fallback only ever compares `>=`, so it would call this a miss. The
        // server must win outright, or the app prints a confident wrong verdict.
        let v = verdict(servedActual: 1.0, servedHit: true, threshold: 2.0, boxActual: 1.0)
        XCTAssertEqual(v.hit, true, "the orientation-aware server grade must win")
    }

    func testServedActualIsPreferredOverTheBoxScoreNumber() {
        let v = verdict(servedActual: 4.0, servedHit: true, threshold: 2.0, boxActual: 9.0)
        XCTAssertEqual(v.actual, 4.0)
    }

    // MARK: - Fail closed: an actual never manufactures a hit

    func testServedActualWithoutServedHitWithholdsTheVerdict() {
        // Orientation unknown (the server sends `hit: null` when the prop carries no
        // threshold). Show the number, make no claim — guessing `actual >= threshold`
        // would print a wrong verdict on every Under.
        let v = verdict(servedActual: 5.0, servedHit: nil, threshold: 2.0)
        XCTAssertNil(v.hit, "an ungraded rung must draw no mark")
        XCTAssertEqual(v.actual, 5.0, "…but the number it finished on is still known")
    }

    func testNothingServedAndNoBoxScoreGradesNothing() {
        let v = verdict()
        XCTAssertNil(v.hit)
        XCTAssertNil(v.actual)
    }

    // MARK: - The live path is untouched

    func testBoxScoreStillGradesWhenTheServerSendsNothing() {
        // Live and scheduled payloads carry neither key; the box-score derivation
        // must behave exactly as it did before this change.
        XCTAssertEqual(verdict(threshold: 2.0, boxActual: 3.0).hit, true)
        XCTAssertEqual(verdict(threshold: 2.0, boxActual: 1.0).hit, false)
        XCTAssertEqual(verdict(threshold: 2.0, boxActual: 2.0).hit, true, "the rung is 2+, so 2 hits")
        XCTAssertEqual(verdict(threshold: 2.0, boxActual: 3.0).actual, 3.0)
    }

    // MARK: - The number reads like a stat line

    func testWholeStatLinesDropTheDecimal() {
        XCTAssertEqual(PlayerPropsCardView.formatStatValue(2.0), "2")
        XCTAssertEqual(PlayerPropsCardView.formatStatValue(0.0), "0")
        XCTAssertEqual(PlayerPropsCardView.formatStatValue(12.0), "12")
    }

    func testFractionalStatLinesKeepTheirFraction() {
        // Never round a fraction away — that would state a different answer.
        XCTAssertEqual(PlayerPropsCardView.formatStatValue(0.5), "0.5")
        XCTAssertEqual(PlayerPropsCardView.formatStatValue(6.2), "6.2")
    }

    // MARK: - The decode, which is where the grade was actually lost

    func testPlayerPropDecodesTheServedGrade() throws {
        // A real row from `/api/events/15308638/game-markets`.
        let json = """
        {"market_name": "Texas vs Seattle: RBIs", "outcome_name": "Brandon Nimmo: 1+",
         "threshold": 1.0, "over_probability": 0.28, "source": "kalshi",
         "actual": 2.0, "hit": true}
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let prop = try dec.decode(GameMarketPlayerProp.self, from: Data(json.utf8))
        XCTAssertEqual(prop.actual, 2.0)
        XCTAssertEqual(prop.hit, true)
    }

    func testPlayerPropDecodesALiveRowThatCarriesNeitherKey() throws {
        // The server returns `{}` from `_grade_settled_prop` for an unfinished
        // event, so both keys are ABSENT — not null. Decoding must not throw.
        let json = """
        {"market_name": "Texas vs Seattle: RBIs", "outcome_name": "Brandon Nimmo: 1+",
         "threshold": 1.0, "over_probability": 0.28, "source": "kalshi"}
        """
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let prop = try dec.decode(GameMarketPlayerProp.self, from: Data(json.utf8))
        XCTAssertNil(prop.actual)
        XCTAssertNil(prop.hit)
    }
}
