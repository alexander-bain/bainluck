import XCTest
@testable import Bain_Luck

/// #888, the defect UNDER the dead section keys: **the league page could not
/// read the payload it downloaded, so it drew no market sections at all.**
///
/// `LeagueGridSectionKeysMatchTheAPI888Tests` pins the section vocabulary. It is
/// green whether or not a single market ever reaches the screen, because a
/// string list knows nothing about decoding. This file is the other half, and it
/// is the half that decides whether the fix is worth anything: with the keys
/// repaired and the decode still broken, `viewModel.leagueMarkets` is nil and
/// the page renders exactly what it rendered before — nothing.
///
/// ## How it was found, and why no unit test could have found it
///
/// An XCUITest (`AReaderCanReachTheLeagueMarketSections888Tests`) swiped to the
/// bottom of the NBA league page and photographed rank 30 of the championship
/// ladder with **no section under it**. The section-key repair predicted four
/// sections and 64 markets there. The screen is the only place those two claims
/// could be compared.
///
/// ## The two shapes, measured on the real payload
///
///   * `/api/politics` and `/api/entertainment` serve `{"name", "prob"}`;
///   * `/api/leagues/{sport_key}` serves
///     `{"name", "probability", "opening_probability", "rank", …}`.
///
/// Both decode into `CategoryOutcome`. `probability` has no underscore, so
/// `.convertFromSnakeCase` leaves it alone and it never matched `prob`:
///
///     DecodingError.keyNotFound: Key 'prob' not found
///     Path: sections.awards[0].topOutcomes[0]
///
/// One throw, at the first outcome of the first market, failed the whole
/// response — and `LeagueGridViewModel.loadLeagueMarkets` catches into a
/// `logger.debug`, so nothing anywhere said so.
final class LeagueMarketsDecodeAgainstProduction888Tests: XCTestCase {

    /// The app's decoder, configured as `APIClient` configures it. A test that
    /// decodes with a default `JSONDecoder` is testing a decoder the app does
    /// not use, and `.convertFromSnakeCase` is the entire mechanism here.
    private func appDecoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    private func decodeFixture() throws -> LeagueMarketsResponse {
        let data = Data(LeagueMarketsNBAFixture.json.utf8)
        return try appDecoder().decode(LeagueMarketsResponse.self, from: data)
    }

    // MARK: - The shipped defect

    func testTheRealNBAPayloadDecodesAtAll() throws {
        let response = try decodeFixture()
        XCTAssertEqual(response.sportKey, "basketball_nba")
        XCTAssertFalse(
            response.sections.isEmpty,
            "The league payload decoded to zero sections. Every market the page downloaded is gone "
            + "before any rendering decision is reached."
        )
    }

    func testAnOutcomeServedAsProbabilityIsRead() throws {
        let response = try decodeFixture()
        let outcomes = response.sections.values.flatMap { $0 }.compactMap(\.topOutcomes).flatMap { $0 }
        XCTAssertFalse(outcomes.isEmpty, "No outcome survived the decode — this is the #888 throw.")
        XCTAssertTrue(
            outcomes.contains { $0.prob > 0 },
            "Every outcome decoded to a zero probability, which the payload does not contain. "
            + "A fallback is silently substituting a number rather than reading the served one."
        )
    }

    /// The politics/entertainment vocabulary must keep working — it is the one
    /// this type was written for, and the whole hazard of the repair is
    /// trading one endpoint for the other.
    func testTheTerseProbSpellingStillDecodes() throws {
        let json = #"[{"name": "Yes", "prob": 0.62}, {"name": "No", "prob": 0.38}]"#
        let outcomes = try appDecoder().decode([CategoryOutcome].self, from: Data(json.utf8))
        XCTAssertEqual(outcomes.map(\.name), ["Yes", "No"])
        XCTAssertEqual(outcomes.map(\.prob), [0.62, 0.38])
    }

    func testTheVerboseProbabilitySpellingDecodes() throws {
        let json = #"[{"name": "Oklahoma City Thunder", "probability": 0.41, "rank": 1}]"#
        let outcomes = try appDecoder().decode([CategoryOutcome].self, from: Data(json.utf8))
        XCTAssertEqual(outcomes.first?.prob, 41.0)
    }

    // MARK: - Two spellings, two scales

    /// **THE THIRD #888 DEFECT, and the one the repaired page photographed.**
    /// With the sections rendering and the decode succeeding, every market on the
    /// NBA page still read **0%**: `prob` is a percent (politics serves 0–98),
    /// `probability` is a fraction (leagues serve 0.0095–0.99), every reader
    /// prints `Int(o.prob)%`, and `Int(0.43) == 0`.
    ///
    /// The KEY decides the scale, never the magnitude — 36 of the 198 politics
    /// values measured on 2026-09-17 are ≤ 1.0, so a "looks like a fraction"
    /// heuristic would divide genuine sub-1% candidates by a hundred.
    func testTheFractionSpellingIsConvertedToPercentAndTheTerseOneIsNot() throws {
        let leagues = #"[{"name": "Fraction", "probability": 0.43}]"#
        let politics = #"[{"name": "Percent", "prob": 0.43}]"#
        XCTAssertEqual(
            try appDecoder().decode([CategoryOutcome].self, from: Data(leagues.utf8)).first?.prob, 43.0,
            "a league outcome served as 0.43 must read 43%, not 0%."
        )
        XCTAssertEqual(
            try appDecoder().decode([CategoryOutcome].self, from: Data(politics.utf8)).first?.prob, 0.43,
            "a politics outcome served as 0.43 IS 0.43% — sub-1% candidates are real and must not be scaled."
        )
    }

    /// The real payload, at the scale a reader sees. A probability the page can
    /// print as a whole-number percent is the entire product of this row.
    func testTheRealPayloadDecodesToReadablePercentages() throws {
        let outcomes = try decodeFixture().sections.values.flatMap { $0 }
            .compactMap(\.topOutcomes).flatMap { $0 }
        let top = try XCTUnwrap(outcomes.map(\.prob).max())
        XCTAssertGreaterThan(
            top, 1.0,
            "The largest probability in the whole payload is \(top). Every market on the page would "
            + "print Int(\(top))% — the sections render, the markets render, and every line reads 0%."
        )
        XCTAssertLessThanOrEqual(top, 100.0, "a probability over 100% is not a scale, it is a bug.")
    }

    /// `prob` wins when a payload somehow carries both, and the test says which
    /// so a later reader does not have to guess at the precedence.
    func testProbWinsWhenBothSpellingsArePresent() throws {
        let json = #"[{"name": "Both", "prob": 0.7, "probability": 0.2}]"#
        let outcomes = try appDecoder().decode([CategoryOutcome].self, from: Data(json.utf8))
        XCTAssertEqual(outcomes.first?.prob, 0.7)
    }

    /// An outcome with NEITHER spelling is not a 0% outcome. It must fail to
    /// decode so the lossy container drops that one line — rendering it as zero
    /// would be a fabricated number on a page whose job is honest ones.
    func testAnOutcomeWithNoProbabilityAtAllRefusesToDecode() {
        let json = #"{"name": "Nothing served"}"#
        XCTAssertThrowsError(
            try appDecoder().decode(CategoryOutcome.self, from: Data(json.utf8)),
            "An outcome with no probability decoded anyway. Whatever number it produced is invented."
        )
    }

    // MARK: - One bad row must not cost the page (gotcha #42, client side)

    /// The production payload really does serve `"probability": null` — eight of
    /// them survive in this fixture slice, in the draft-lottery and single-game
    /// specials markets. Those outcomes drop; their markets do not.
    func testNullProbabilityOutcomesDropTheirOwnLineAndNothingElse() throws {
        let response = try decodeFixture()
        let markets = response.sections.values.flatMap { $0 }
        XCTAssertEqual(
            response.droppedMarkets, 0,
            "A market row was dropped by the fixture decode. The null probabilities in this payload "
            + "live on OUTCOMES; if a whole row went with them the tolerance is at the wrong level."
        )
        let lottery = try XCTUnwrap(
            markets.first { $0.name.contains("Draft Lottery") },
            "The market carrying the null-probability outcomes is not in the result."
        )
        let decodedOutcomes = try XCTUnwrap(lottery.topOutcomes).count
        XCTAssertGreaterThan(decodedOutcomes, 0, "Every outcome of the draft-lottery market was dropped.")

        // Counted from the fixture's own bytes rather than from a field the
        // server computes: `outcome_count` is the market's total, which is
        // larger than `top_outcomes` for reasons that have nothing to do with
        // dropping, so comparing against it would pass whether or not the lossy
        // decode ran at all.
        let served = try Self.servedOutcomeCount(forMarketNameContaining: "Draft Lottery")
        XCTAssertLessThan(
            decodedOutcomes, served,
            "The payload serves \(served) outcomes for this market, \(decodedOutcomes) of them "
            + "decoded, and nothing was dropped — either the fixture has been tidied of its null "
            + "probabilities or the lossy decode is not running."
        )
    }

    /// Reads the fixture as raw JSON, so the count is the SERVER's and not a
    /// restatement of what the model under test managed to read.
    private static func servedOutcomeCount(forMarketNameContaining needle: String) throws -> Int {
        let raw = try JSONSerialization.jsonObject(with: Data(LeagueMarketsNBAFixture.json.utf8))
        let sections = (raw as? [String: Any])?["sections"] as? [String: Any] ?? [:]
        for value in sections.values {
            for case let market as [String: Any] in (value as? [Any] ?? []) {
                guard let name = market["name"] as? String, name.contains(needle) else { continue }
                return (market["top_outcomes"] as? [Any])?.count ?? 0
            }
        }
        return 0
    }

    func testOneUnreadableMarketCostsOneRowNotTheSection() throws {
        let json = #"""
        {
          "sport_key": "basketball_nba",
          "total_markets": 2,
          "sections": {
            "more_markets": [
              {"id": 1, "name": "Readable", "source": "kalshi",
               "top_outcomes": [{"name": "Yes", "probability": 0.5}]},
              {"id": null, "name": "No id at all", "source": "kalshi"}
            ]
          }
        }
        """#
        let response = try appDecoder().decode(LeagueMarketsResponse.self, from: Data(json.utf8))
        XCTAssertEqual(response.sections["more_markets"]?.map(\.name), ["Readable"])
        XCTAssertEqual(
            response.droppedMarkets, 1,
            "The unreadable row must be COUNTED. A silent drop is how 64 markets became 0 without "
            + "anything in the app saying so."
        )
    }

    /// The counter is not decoration: a reader-facing zero and an unreadable
    /// sixty-four are different facts and the app must be able to tell them
    /// apart. Nothing puts this number on a screen (standing notice 34).
    func testACleanPayloadCountsNoDrops() throws {
        XCTAssertEqual(try decodeFixture().droppedMarkets, 0)
    }

    // MARK: - The served total survives

    /// `total_markets` is the server's own count. It must not be quietly
    /// recomputed from what decoded, or a future decode failure looks like a
    /// league with nothing on it.
    func testTheServedTotalIsTheServersNotOurs() throws {
        let response = try decodeFixture()
        let decoded = response.sections.values.reduce(0) { $0 + $1.count }
        XCTAssertEqual(response.totalMarkets, 64, "total_markets stopped being the served number.")
        XCTAssertLessThan(
            decoded, response.totalMarkets,
            "This fixture is a SLICE; if it now decodes to the full served total the fixture was "
            + "regenerated, and with it the null-probability specimens this file depends on."
        )
    }
}
