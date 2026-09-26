import XCTest
import SwiftUI
@testable import Bain_Luck

/// #8691: the iPhone Championship Path printed `<1%` for a stage the payload
/// carried NO number for.
///
/// Specimen, as production served it (`/api/events/15318410/team-progression`,
/// read 2026-09-25 ~19:40Z): the Dodgers at 97-62 with three games left, whose
/// card read "Make Playoffs <1% · Division <1%" directly above "AL / NL Champ
/// 42% · World Series 29%". Both of those first rows are `probability: null`
/// on the wire; the row coerced `stage.probability ?? 0` and `formatProb(0)` is
/// `<1%`, over a 2 pt bar. The grid behind the card (`/api/playoffs/mlb`, same
/// minute) had graded both cells `state: "won"` — the stage the app called a
/// long shot was already clinched.
///
/// Web fixed the identical coercion on its twin in #8203; this is the app's.
final class ChampionshipPathUnpricedStage8691Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    /// The Dodgers card, byte-for-byte the served stage list (sources elided —
    /// the model does not decode them).
    private static let dodgersPayload = #"""
    {"event_id": 15318410, "league": "mlb", "league_name": "MLB Playoffs 2026",
     "home_team": null,
     "away_team": {"name": "Los Angeles Dodgers", "short_name": "LAD",
       "record": "97-62", "conference": "National League",
       "stages": [
         {"key": "make_playoffs", "label": "Make Playoffs", "probability": null, "trend_24h": null},
         {"key": "division", "label": "Division", "probability": null, "trend_24h": null},
         {"key": "pennant", "label": "AL / NL Champ", "probability": 0.415, "trend_24h": 0.005},
         {"key": "championship", "label": "World Series", "probability": 0.302, "trend_24h": 0.0206}
       ]}}
    """#

    private func dodgersStages() throws -> [ProgressionStageData] {
        let response = try decoder().decode(
            TeamProgressionResponse.self, from: Data(Self.dodgersPayload.utf8))
        return try XCTUnwrap(response.awayTeam).stages
    }

    private func stage(probability: String, state: String? = nil) throws -> ProgressionStageData {
        let statePart = state.map { #", "state": "\#($0)""# } ?? ""
        let json = #"{"key": "division", "label": "Division", "probability": \#(probability), "trend_24h": 0.02\#(statePart)}"#
        return try decoder().decode(ProgressionStageData.self, from: Data(json.utf8))
    }

    // MARK: The specimen

    func testTheDodgersUnpricedStagesAreWithheldNotUnderOnePercent() throws {
        let stages = try dodgersStages()
        XCTAssertEqual(
            stages.map { ChampionshipRowLayout.display(for: $0) },
            [.withheld, .withheld, .priced(0.415), .priced(0.302)],
            "a stage served with no number must not be drawn as a price")
    }

    // MARK: The served state decides before the number

    func testAWonStageIsClinchedWithoutANumber() throws {
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "null", state: "won")), .clinched)
        // The display word is accepted as the register word, as on the grid (#7557).
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "null", state: "clinched")), .clinched)
    }

    func testAGradedOrUnvouchedStageNeverPrintsItsLastPrice() throws {
        // A terminal/unknown state carries a result or nothing — never the stale quote.
        for state in ["eliminated", "missing", "unavailable", "some-future-state"] {
            XCTAssertEqual(
                ChampionshipRowLayout.display(for: try stage(probability: "0.3", state: state)),
                .withheld, "state \(state) printed a price")
        }
    }

    func testALiveStageWithNoNumberIsWithheld() throws {
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "null", state: "live")), .withheld)
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "0.4", state: "live")), .priced(0.4))
    }

    /// No state at all is every payload `/team-progression` serves today: the
    /// number decides, exactly as before this change — including a genuine
    /// long shot, which still reads `<1%`.
    func testWithNoStateTheNumberDecidesAsBefore() throws {
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "0.995")), .clinched)
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "0.003")), .priced(0.003))
        XCTAssertEqual(ChampionshipStageBadges.formatProb(0.003), "<1%")
        XCTAssertEqual(ChampionshipRowLayout.display(for: try stage(probability: "1.4")), .withheld)
    }

    // MARK: What the row draws

    func testAWithheldRowDrawsNoBar() {
        XCTAssertNil(ChampionshipStageDisplay.withheld.barFraction)
        XCTAssertEqual(ChampionshipStageDisplay.clinched.barFraction, 1)
        XCTAssertEqual(ChampionshipStageDisplay.priced(0.415).barFraction, 0.415)
    }

    /// Measured on the rendered badge, not asserted on the enum: the defect was
    /// a string on screen. A withheld badge wants no width at all — no `<1%`,
    /// no trend arrow — while its priced sibling on the same card still does.
    @MainActor
    func testTheRenderedBadgeOfAnUnpricedStageIsEmpty() throws {
        let stages = try dodgersStages()
        let withheldWidth = naturalWidth(of: ChampionshipStageBadges(stage: stages[0]))
        let pricedWidth = naturalWidth(of: ChampionshipStageBadges(stage: stages[2]))
        XCTAssertEqual(withheldWidth, 0, accuracy: 0.5, "the unpriced Make Playoffs row drew a badge")
        // An unpriced stage that still carries a 24h move draws no arrow either.
        let movedButUnpriced = try stage(probability: "null")
        XCTAssertEqual(movedButUnpriced.trend24h, 0.02)
        XCTAssertEqual(naturalWidth(of: ChampionshipStageBadges(stage: movedButUnpriced)), 0, accuracy: 0.5,
                       "an unpriced row drew a trend badge")
        XCTAssertGreaterThan(pricedWidth, 20, "control: the priced pennant row must still draw its number")
    }

    /// A card that mixes clinched and unpriced rows keeps the wide column, so a
    /// priced row added later never truncates (#3574's direction).
    func testWithheldRowsDoNotNarrowTheColumn() throws {
        let won = try stage(probability: "null", state: "won")
        let blank = try stage(probability: "null")
        XCTAssertEqual(ChampionshipRowLayout.badgeWidth(for: [won, won]), ChampionshipRowLayout.allClinchedBadgeWidth)
        XCTAssertEqual(ChampionshipRowLayout.badgeWidth(for: [won, blank]), ChampionshipRowLayout.valueBadgeWidth)
    }

    @MainActor
    private func naturalWidth<V: View>(of view: V) -> CGFloat {
        let host = hostForMeasurement(view, at: .large)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(
            in: CGSize(width: CGFloat.greatestFiniteMagnitude,
                       height: CGFloat.greatestFiniteMagnitude)).width
    }
}
