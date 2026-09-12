import XCTest
@testable import Bain_Luck

/// #4577 — the app had no pregame baseline on any prop rung.
///
/// THE DEFECT. `GET /api/events/{id}/game-markets` has served `pregame_mark` per
/// prop since #195. `GameMarketPlayerProp` did not decode it, so every rung on
/// the phone printed the live number alone and "THE SCRIPT vs THE DIVERGENCE"
/// — product priority 3 — was absent from the app rather than merely unfolded.
///
/// THE FIX is Alex's own ruled shape for The Open 2026, already on web: the mark
/// is a tick on the rung's track, the live price is the fill, and the gap is the
/// story. See ``PlayerPropsScript`` for why the web's "More props (N)" fold does
/// NOT come with it (measured: it would hide 66 priced rungs and hole 11
/// ladders) and why neither `current` nor `opening_over_probability` may stand
/// in for a missing mark.
///
/// WHAT THESE TESTS ARE WORTH. The rule and the geometry are pure functions and
/// are tested directly. The last three are a source scan, whose failure mode is
/// passing because it read nothing — `testTheScanCanSeeTheFileItIsAbout` is the
/// guard on that, and without it the wiring assertions would pass on an empty
/// string.
final class PropsScriptPregameTickTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    // MARK: - The decode, which is where the baseline was lost

    func testPregameMarkDecodesFromTheServedKey() throws {
        // A real row from `/api/events/15310365/game-markets` (Cubs–Pirates,
        // 2026-09-12): the market opened at 45% and is trading at 43%.
        let json = """
        {"market_name": "Pittsburgh vs Chicago C: Outs Recorded",
         "outcome_name": "Clay Holmes: 17+", "threshold": 17.0,
         "over_probability": 0.43, "opening_over_probability": 0.45,
         "pregame_mark": 0.45, "source": "kalshi"}
        """
        let prop = try decoder().decode(GameMarketPlayerProp.self, from: Data(json.utf8))
        XCTAssertEqual(prop.pregameMark, 0.45)
        XCTAssertEqual(prop.overProbability, 0.43)
    }

    func testAnAbsentPregameMarkDecodesAsNilRatherThanThrowing() throws {
        // The endpoint's two "rescue" prop builders omit the key entirely. This
        // is the shape 55 of 141 measured rungs arrive in.
        let json = """
        {"market_name": "Pittsburgh vs Chicago C: Total Bases",
         "outcome_name": "Pete Crow-Armstrong: 2+", "threshold": 2.0,
         "over_probability": 0.51, "opening_over_probability": 0.46,
         "source": "kalshi"}
        """
        let prop = try decoder().decode(GameMarketPlayerProp.self, from: Data(json.utf8))
        XCTAssertNil(prop.pregameMark)
    }

    func testAnExplicitNullPregameMarkDecodesAsNil() throws {
        // The two MAIN builders send an explicit null when the resolver declines.
        // Absent and null must land in the same place, because the web compares
        // `pregame_mark == null`, which catches undefined too.
        let json = """
        {"market_name": "Pittsburgh vs Chicago C: Strikeouts",
         "outcome_name": "Clay Holmes: 8+", "threshold": 8.0,
         "over_probability": 0.12, "pregame_mark": null, "source": "kalshi"}
        """
        let prop = try decoder().decode(GameMarketPlayerProp.self, from: Data(json.utf8))
        XCTAssertNil(prop.pregameMark)
    }

    /// The three shapes arrive in ONE array in production. Decoding them
    /// together is the thing the app actually does.
    func testAServedPropArrayCarriesAllThreeShapesAtOnce() throws {
        let json = """
        [{"market_name": "M", "outcome_name": "A: 1+", "over_probability": 0.7, "pregame_mark": 0.62},
         {"market_name": "M", "outcome_name": "B: 1+", "over_probability": 0.5, "pregame_mark": null},
         {"market_name": "M", "outcome_name": "C: 1+", "over_probability": 0.3}]
        """
        let props = try decoder().decode([GameMarketPlayerProp].self, from: Data(json.utf8))
        XCTAssertEqual(props.count, 3)
        XCTAssertEqual(props.compactMap(\.pregameMark), [0.62])
        // …and every row still carries its live price: a missing mark never
        // costs a rung its number. This is the assertion the web's fold would
        // have broken on the app.
        XCTAssertEqual(props.compactMap(\.overProbability).count, 3)
    }

    // MARK: - When a tick is drawn at all

    func testNoTickWhenTheServerSentNoMark() {
        XCTAssertNil(PlayerPropsScript.tickFraction(pregameMark: nil, isFinished: false))
    }

    func testNoTickOnAFinishedGame() {
        // WHAT HIT owns the settled row (#4959's ✓/– and final value). A pregame
        // tick there is history competing with a result.
        XCTAssertNil(PlayerPropsScript.tickFraction(pregameMark: 0.45, isFinished: true))
    }

    func testALiveGameStillDrawsItsTick() {
        // The gap between tick and fill IS THE DIVERGENCE, which is precisely
        // what a reader wants while play is on.
        XCTAssertEqual(PlayerPropsScript.tickFraction(pregameMark: 0.45, isFinished: false), 0.45)
    }

    func testTheTickSitsAtTheMarkAndNowhereElse() {
        // Not the live price, not the opening line, not a blend: the mark.
        XCTAssertEqual(PlayerPropsScript.tickFraction(pregameMark: 0.0, isFinished: false), 0.0)
        XCTAssertEqual(PlayerPropsScript.tickFraction(pregameMark: 1.0, isFinished: false), 1.0)
        XCTAssertEqual(PlayerPropsScript.tickFraction(pregameMark: 0.625, isFinished: false), 0.625)
    }

    func testAMarkOutsideTheUnitRangeIsClampedOntoTheTrack() {
        // The value comes off the network; the view cannot assume its range.
        XCTAssertEqual(PlayerPropsScript.tickFraction(pregameMark: 1.4, isFinished: false), 1.0)
        XCTAssertEqual(PlayerPropsScript.tickFraction(pregameMark: -0.2, isFinished: false), 0.0)
    }

    func testANonFiniteMarkDrawsNoTick() {
        // NaN survives a clamp (every comparison is false) and would place the
        // tick nowhere at all, so it is refused before the clamp sees it.
        XCTAssertNil(PlayerPropsScript.tickFraction(pregameMark: .nan, isFinished: false))
        XCTAssertNil(PlayerPropsScript.tickFraction(pregameMark: .infinity, isFinished: false))
    }

    // MARK: - Where the tick lands on the track

    func testTheTickIsCentredOnItsFraction() {
        // 50% of a 200pt track is 100pt; a 2pt tick centred there starts at 99.
        XCTAssertEqual(
            PlayerPropsScript.tickOffset(fraction: 0.5, trackWidth: 200, tickWidth: 2),
            99,
            accuracy: 0.0001
        )
    }

    func testTheTickCannotHangOffTheRightEnd() {
        // Centring a tick at 100% would put half of it past the track.
        XCTAssertEqual(
            PlayerPropsScript.tickOffset(fraction: 1.0, trackWidth: 200, tickWidth: 2),
            198,
            accuracy: 0.0001
        )
    }

    func testTheTickCannotHangOffTheLeftEnd() {
        XCTAssertEqual(
            PlayerPropsScript.tickOffset(fraction: 0.0, trackWidth: 200, tickWidth: 2),
            0,
            accuracy: 0.0001
        )
    }

    func testATrackNarrowerThanItsOwnTickStillYieldsARealOffset() {
        // `GeometryReader` hands out a zero or tiny width for a layout pass
        // before the real one. A negative offset would draw the tick outside the
        // row entirely.
        XCTAssertEqual(PlayerPropsScript.tickOffset(fraction: 0.5, trackWidth: 0, tickWidth: 2), 0)
        XCTAssertEqual(PlayerPropsScript.tickOffset(fraction: 1.0, trackWidth: 1, tickWidth: 2), 0)
    }

    func testTheTickMovesWhenTheMarkMoves() {
        // The whole feature in one assertion: two different marks must not land
        // in the same place, or the tick is decoration.
        let low = PlayerPropsScript.tickOffset(fraction: 0.25, trackWidth: 200, tickWidth: 2)
        let high = PlayerPropsScript.tickOffset(fraction: 0.75, trackWidth: 200, tickWidth: 2)
        XCTAssertEqual(high - low, 100, accuracy: 0.0001)
    }

    // MARK: - The view actually draws it (source scan)

    /// The shipping source of the view under test, walked from this test's own
    /// location — the idiom `MarketMapColumnHeaders5656Tests` established.
    private func cardSource() throws -> String {
        let here = URL(fileURLWithPath: #filePath)
        let url = here
            .deletingLastPathComponent()   // BainLuckTests
            .deletingLastPathComponent()   // Bain Luck (project dir)
            .appendingPathComponent("Bain Luck")
            .appendingPathComponent("Components")
            .appendingPathComponent("PlayerPropsCardView.swift")
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// If this fails, the two scans below are asserting about an empty string
    /// and mean nothing.
    func testTheScanCanSeeTheFileItIsAbout() throws {
        let source = try cardSource()
        XCTAssertGreaterThan(source.count, 5_000, "the scan read a file far too short to be PlayerPropsCardView")
        XCTAssertTrue(source.contains("struct PlayerPropsCardView"), "scan did not find the view's own declaration")
        XCTAssertTrue(source.contains("private func rungRow"), "scan did not find the row the tick is drawn on")
    }

    func testTheRungTrackDrawsTheTickThroughTheSharedRule() throws {
        // A decoded field nothing renders is an inert ship. Both halves are
        // named, so re-implementing the maths inside the view — the way this
        // would drift out of test — also fails.
        let source = try cardSource()
        XCTAssertTrue(
            source.contains("PlayerPropsScript.tickFraction"),
            "the rung no longer asks PlayerPropsScript whether to draw a tick — #4577"
        )
        XCTAssertTrue(
            source.contains("PlayerPropsScript.tickOffset"),
            "the rung no longer places its tick through PlayerPropsScript — #4577"
        )
    }

    func testTheRungNeverSubstitutesAnotherNumberForAMissingMark() throws {
        // The two fallbacks that look available and both fabricate: the live
        // price (forbidden by #4530's measurement) and the opening line (the
        // server already tried it and declined). Neither may appear in the
        // tick's own call.
        let source = try cardSource()
        XCTAssertFalse(
            source.contains("pregameMark: rung.probability"),
            "the tick fell back to the LIVE price — #4530 measured that gap at up to 22.5pt"
        )
        XCTAssertFalse(
            source.contains("openingOverProbability"),
            "the tick fell back to the opening line, which the server already declined to use"
        )
        XCTAssertTrue(
            source.contains("pregameMark: rung.pregameMark"),
            "the tick is no longer fed by the served mark — #4577"
        )
    }
}
