import XCTest
@testable import Bain_Luck

/// #3393 — the phone reads the server's `source_labels` vocabulary.
///
/// `/api/calibration` publishes a name for every source key it serves, owned in
/// one place (`backend/app/utils/calibration_source_labels.py`). Web reads it
/// (`makeSourceLabeller`: house style first, then the published label); the
/// phone kept only its own map plus a formatter, so a source key the app had
/// never seen would have been named from its spelling — the way `datagolf`
/// reached web readers as a raw key for three weeks before web read the block.
///
/// The fixture keys below (`novig`, `odds_api_h2h_lay`) are deliberately keys
/// production does NOT serve: the defect is about the NEXT key, and each was
/// chosen so the formatter's answer differs from the server's ("Novig" vs
/// "NoVig"), which is what lets these tests fail on the old code.
@MainActor
final class CalibrationServedSourceLabels3393Tests: XCTestCase {

    private static func payload(sourceLabels: String?) -> String {
        let version = CalibrationRenderSmokeTests.renderableVersion
        let labels = sourceLabels.map { #""source_labels": \#($0),"# } ?? ""
        return """
        {
          "population_version": "\(version)",
          "total_markets": 3, "total_outcomes": 1500, "total_winners": 600,
          "generated_at": "2026-09-25T06:00:00+00:00",
          \(labels)
          "buckets": [
            {"bucket_idx": 4, "source": "kalshi", "category": "baseball", "price_moved": true,
             "n": 800, "winners": 330, "sum_prob": 340.0, "sum_sq_err": 190.0},
            {"bucket_idx": 4, "source": "novig", "category": "baseball", "price_moved": true,
             "n": 400, "winners": 160, "sum_prob": 170.0, "sum_sq_err": 95.0},
            {"bucket_idx": 4, "source": "odds_api_bookmaker", "category": "baseball", "price_moved": null,
             "n": 200, "winners": 70, "sum_prob": 85.0, "sum_sq_err": 48.0},
            {"bucket_idx": 4, "source": "odds_api_h2h_lay", "category": "baseball", "price_moved": null,
             "n": 100, "winners": 40, "sum_prob": 42.0, "sum_sq_err": 24.0}
          ]
        }
        """
    }

    private static let servedVocabulary = """
    {
      "kalshi": {"label": "Kalshi", "declared": true},
      "odds_api_bookmaker": {"label": "Per-sportsbook (Odds API)", "declared": true},
      "novig": {"label": "NoVig", "declared": true},
      "odds_api_h2h_lay": {"label": "Lay (Odds API)", "declared": false}
    }
    """

    /// The app's own decoder configuration (`APIClient`), so the key strategy
    /// under test is the one production traffic goes through.
    private static func decode(_ json: String) throws -> CalibrationData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return try dec.decode(CalibrationData.self, from: Data(json.utf8))
    }

    // MARK: - The ship: a new key renders the server's name on the screen

    func testAKeyTheAppHasNeverSeenRendersTheServersName() throws {
        let vm = CalibrationViewModel(preloaded: try Self.decode(Self.payload(sourceLabels: Self.servedVocabulary)))
        let rows = vm.sourceRows
        let novig = try XCTUnwrap(rows.first { $0.source == "novig" }, "rows: \(rows.map(\.source))")
        XCTAssertEqual(novig.name, "NoVig", "the server's name, not one generated from the key's spelling")

        let family = try XCTUnwrap(rows.first { $0.source == "odds_api_family" })
        XCTAssertEqual(family.memberNames, ["Per-sportsbook", "Lay"],
                       "an unknown family member takes the served label, qualifier stripped like its siblings")
    }

    /// The control for the test above: the same payload without the block is what
    /// the phone drew before #3393 — the formatter's guess. If this ever reads
    /// "NoVig", the fixture no longer discriminates and the test above proves nothing.
    func testWithoutTheBlockTheFormatterStillAnswersAndNeverARawKey() throws {
        let data = try Self.decode(Self.payload(sourceLabels: nil))
        XCTAssertNil(data.sourceLabels, "absent block = never looked, not an empty vocabulary")
        let rows = CalibrationViewModel(preloaded: data).sourceRows
        let novig = try XCTUnwrap(rows.first { $0.source == "novig" })
        XCTAssertEqual(novig.name, toTitleCaseAcronymSafe("novig"))
        XCTAssertNotEqual(novig.name, "NoVig", "control: the formatter's answer must differ from the server's")
        for row in rows {
            XCTAssertFalse(row.name.contains("_"), "raw key rendered: \(row.name)")
            for member in row.memberNames { XCTAssertFalse(member.contains("_"), "raw key rendered: \(member)") }
        }
    }

    // MARK: - Precedence (web's: house style, then served, then formatter)

    func testHouseStyleStillWinsOverTheServedLabel() {
        let served = ["kalshi": CalibrationSourceLabel(label: "KALSHI EXCHANGE", declared: true)]
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("kalshi", served: served), "Kalshi")
    }

    func testABlankServedLabelIsNoNameAndFallsThrough() {
        let served = [
            "novig": CalibrationSourceLabel(label: "   ", declared: true),
            "fedex": CalibrationSourceLabel(label: "", declared: nil),
        ]
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("novig", served: served), toTitleCaseAcronymSafe("novig"))
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("fedex", served: served), "FedEx")
    }

    func testAServedLabelIsTrimmed() {
        let served = ["novig": CalibrationSourceLabel(label: " NoVig\n", declared: true)]
        XCTAssertEqual(CalibrationViewModel.sourceDisplayName("novig", served: served), "NoVig")
    }

    // MARK: - Decode

    /// `convertFromSnakeCase` rewrites struct keys; if it ever rewrote the
    /// DICTIONARY keys too, `odds_api_h2h_lay` would arrive as `oddsApiH2hLay`
    /// and no lookup by the bucket's `source` would ever hit. Pinned on the
    /// runtime the tests run on.
    func testTheVocabularyKeepsTheServersKeysVerbatim() throws {
        let data = try Self.decode(Self.payload(sourceLabels: Self.servedVocabulary))
        let labels = try XCTUnwrap(data.sourceLabels)
        XCTAssertEqual(Set(labels.keys), ["kalshi", "odds_api_bookmaker", "novig", "odds_api_h2h_lay"])
        XCTAssertEqual(labels["odds_api_h2h_lay"]?.label, "Lay (Odds API)")
        XCTAssertEqual(labels["odds_api_h2h_lay"]?.declared, false)
    }

    /// A malformed block costs the names, never the page.
    func testAMalformedBlockDecodesAsAbsentAndTheCurveSurvives() throws {
        let data = try Self.decode(Self.payload(sourceLabels: #""oops""#))
        XCTAssertNil(data.sourceLabels)
        XCTAssertEqual(data.buckets.count, 4)
    }

    // MARK: - Web/app agreement on today's vocabulary

    /// Production's `source_labels`, read from `GET /api/calibration` on
    /// 2026-09-25T06:41Z (all seven keys it serves). For every one of them the
    /// phone already prints the server's string — house map or formatter — so
    /// this change moves no pixel today, and a future edit to either side that
    /// splits them fails here.
    func testThePhonePrintsTheServersNameForEveryKeyProductionServes() {
        let production: [String: String] = [
            "polymarket": "Polymarket",
            "kalshi": "Kalshi",
            "odds_api_bookmaker": "Per-sportsbook (Odds API)",
            "datagolf": "DataGolf",
            "odds_api": "Moneylines (Odds API)",
            "odds_api_totals": "Totals (Odds API)",
            "odds_api_spreads": "Spreads (Odds API)",
        ]
        for (key, label) in production {
            XCTAssertEqual(CalibrationViewModel.sourceDisplayName(key), label, "phone and server disagree on '\(key)'")
        }
    }
}
