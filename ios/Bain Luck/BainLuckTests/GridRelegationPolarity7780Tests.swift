import XCTest
@testable import Bain_Luck

/// #7780 — the championship grid congratulated a club in green for becoming
/// more likely to be relegated.
///
/// `ChampionshipStageBadges` painted every 24h move `trend > 0 ? .green : .red`.
/// That is right for every column that is a rung toward something a club wants
/// and exactly backwards for `relegation`: a rising relegation probability is
/// the bad outcome, so the grid read a club's risk going UP as good news and its
/// risk coming DOWN as bad. Web shipped and fixed the identical assumption
/// (#7745 / PR #7769).
///
/// ## What these tests are about
///
/// `Color` cannot be compared in an XCTest, so the assertions are on the
/// PREDICATE the colour is now a function of — `isGoodNews` — and the thing that
/// makes it trustworthy is that the relegation cases are asserted in BOTH
/// directions. A one-directional test ("a rising relegation trend is not good
/// news") passes against an implementation that simply returns `false` for
/// relegation always, which would paint a falling risk red too — the other half
/// of the same bug.
///
/// That the view is wired to this at all, and that the arrow was NOT flipped
/// with the colour, is pinned in
/// `frontend/__tests__/ios/gridColumnPolarityParity7780.test.ts` — jest is a
/// deploy gate here and the Swift target is not reachable from CI (notice 10's
/// iOS clause). That file also holds this key set against web's.
final class GridRelegationPolarity7780Tests: XCTestCase {

    /// Every column key `league_configs.py` publishes, measured for this fix:
    /// 26 distinct key/label pairs, of which exactly one is adverse.
    private static let benignKeys = [
        "championship", "top_4", "make_playoffs", "conference", "division",
        "final_four", "make_cut", "playoffs", "top_6", "wildcard",
    ]

    // MARK: - The ship

    /// The specimen, in both directions.
    func testARelegationRiskRisingIsBadNewsAndFallingIsGood() {
        XCTAssertFalse(
            GridColumnPolarity.isGoodNews(trend: 0.003, columnKey: "relegation"),
            "a club getting MORE likely to be relegated was read as good news"
        )
        XCTAssertTrue(
            GridColumnPolarity.isGoodNews(trend: -0.004, columnKey: "relegation"),
            "a club getting LESS likely to be relegated was read as bad news"
        )
    }

    /// Every other column keeps the reading it always had.
    ///
    /// The repair must not be "relegation is special AND everything else moved":
    /// a fix that inverted the default would turn the whole grid the wrong way
    /// round while making the specimen above pass.
    func testEveryOtherColumnStillReadsRisingAsGood() {
        for key in Self.benignKeys {
            XCTAssertTrue(GridColumnPolarity.isGoodNews(trend: 0.01, columnKey: key), key)
            XCTAssertFalse(GridColumnPolarity.isGoodNews(trend: -0.01, columnKey: key), key)
        }
    }

    /// `relegation` is the only adverse key.
    func testRelegationIsTheOnlyAdverseKey() {
        XCTAssertEqual(GridColumnPolarity.adverseColumnKeys, ["relegation"])
        XCTAssertFalse(GridColumnPolarity.risingIsGood("relegation"))
        for key in Self.benignKeys {
            XCTAssertTrue(GridColumnPolarity.risingIsGood(key), key)
        }
    }

    // MARK: - The key, never the label

    /// A display label is not a key.
    ///
    /// `label` re-words — "Relegated" today, "Drop Zone" or a translation
    /// tomorrow — so a classifier reading it misfiles the day it changes. The
    /// structured key is the contract; these are the strings a label-reading
    /// implementation would wrongly claim.
    func testTheLabelIsNotConsultedAsAKey() {
        for label in ["Relegated", "relegated", "Drop Zone", "Relegation Zone"] {
            XCTAssertTrue(
                GridColumnPolarity.risingIsGood(label),
                "\(label) was treated as the structured key `relegation`"
            )
        }
    }

    // MARK: - Absences

    /// No key, no opinion: the majority reading.
    ///
    /// There is no third colour to draw an unknown in, and every key in the
    /// vocabulary bar one rises toward something good — and the callers with no
    /// structured key are precisely the ones with no relegation rung to get
    /// wrong.
    func testAnAbsentOrUnknownKeyReadsRisingAsGood() {
        for key: String? in [nil, "", "a_key_nobody_has_shipped_yet"] {
            XCTAssertTrue(GridColumnPolarity.risingIsGood(key))
            XCTAssertTrue(GridColumnPolarity.isGoodNews(trend: 0.02, columnKey: key))
            XCTAssertFalse(GridColumnPolarity.isGoodNews(trend: -0.02, columnKey: key))
        }
    }

    /// The badge the grid actually builds carries the key this reads.
    ///
    /// `isGoodNews` being right is worth nothing if the renderer has no key to
    /// hand it. This decodes the payload shape the grid is fed and asserts the
    /// key survives onto the model the view holds.
    func testTheStageModelCarriesTheKeyTheRenderNeeds() throws {
        let json = Data("""
        {"key": "relegation", "label": "Relegated", "probability": 0.041, "trend24H": 0.003}
        """.utf8)
        let stage = try JSONDecoder().decode(ProgressionStageData.self, from: json)

        XCTAssertEqual(stage.key, "relegation")
        let trend = try XCTUnwrap(stage.trend24h)
        XCTAssertFalse(GridColumnPolarity.isGoodNews(trend: trend, columnKey: stage.key))
    }
}
