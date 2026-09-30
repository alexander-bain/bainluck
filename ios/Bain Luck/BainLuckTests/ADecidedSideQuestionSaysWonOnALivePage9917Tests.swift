import XCTest
@testable import Bain_Luck

/// #9917: **during a live game, a side question that is already answered says
/// `Won` / `Lost` instead of drawing a live bar and an invented `0%`.**
///
/// The specimen is production. native's D48 walk on master `96a12e9348`,
/// 2026-09-30 12:59 PM PDT, iPhone simulator: live Phillies at Braves
/// (`15321782`), Bottom 6th, 1–1. Additional Markets drew
/// `run scored in the first inning? — Yes ▓▓▓ 100% / No 0%` and
/// `First Inning Run — Yes ▓▓▓ 99%`, two hours after the first inning ended.
/// The payload already carried the grade (`is_winner` + `resolution_source`) on
/// every one of those rows, and the "No" leg's price was `null`.
///
/// The web card fixed its half in #6138 / #8067; this is the same rule, read
/// through `OutcomeVerdict.verdict`, which is the one Swift copy of it.
final class ADecidedSideQuestionSaysWonOnALivePage9917Tests: XCTestCase {

    // MARK: - The specimen, live

    func testTheAnsweredFirstInningQuestionSaysWonMidGame() throws {
        let view = Self.card(status: "live")
        XCTAssertEqual(
            view.treatment(for: try Self.entry(Self.pmQuestion, "Yes", in: view)),
            .verdict(.won),
            "Polymarket graded 'Yes' (clob_authoritative) and the card still drew a live 100% bar in the 6th"
        )
        XCTAssertEqual(
            view.treatment(for: try Self.entry(Self.kalshiQuestion, "Yes", in: view)),
            .verdict(.won),
            "Kalshi graded 'Yes' (api_settlement) and the card still drew a live 99% bar"
        )
    }

    /// The losing leg is `null`-priced and `is_winner: false`. On a game that is
    /// not over only an authoritative WON may cross (a defaulted `false` must
    /// never print `Lost` on a leg still open, #4788), so this row gets no
    /// verdict — and it must not get the `0%` that `?? 0` used to invent either.
    func testTheUnpricedLosingLegPrintsNoNumberMidGame() throws {
        let view = Self.card(status: "live")
        let no = try Self.entry(Self.pmQuestion, "No", in: view)
        XCTAssertFalse(no.priced, "a wire null price was collapsed into a number again")
        XCTAssertEqual(view.treatment(for: no), .noPrice)
    }

    func testOnceTheGameIsFinalTheLosingLegSaysLost() throws {
        let view = Self.card(status: "completed")
        XCTAssertEqual(view.treatment(for: try Self.entry(Self.pmQuestion, "No", in: view)), .verdict(.lost))
        XCTAssertEqual(view.treatment(for: try Self.entry(Self.pmQuestion, "Yes", in: view)), .verdict(.won))
    }

    func testTheAnswerLeadsItsCard() throws {
        let view = Self.card(status: "live")
        let item = try XCTUnwrap(view.categories.flatMap(\.items).first { $0.name == Self.pmQuestion })
        XCTAssertEqual(view.sortedOutcomes(item.outcomes).map(\.label), ["Yes", "No"])

        // The rank is the grade, not the price: a graded winner nobody priced
        // still leads a priced loser once the game is final.
        let final = SpecialEventMarketsView(
            markets: Self.rows("""
            [
              {"market_name": "Q?: A vs. B", "outcome_name": "Yes", "observed_at": null,
               "probability": null, "source": "polymarket", "is_winner": true, "resolution_source": "api_settlement"},
              {"market_name": "Q?: A vs. B", "outcome_name": "No", "observed_at": null,
               "probability": 0.02, "source": "polymarket", "is_winner": false, "resolution_source": "api_settlement"}
            ]
            """),
            eventStatus: "completed",
            commenceTime: Self.firstPitch
        )
        let graded = try XCTUnwrap(final.categories.flatMap(\.items).first)
        XCTAssertEqual(final.sortedOutcomes(graded.outcomes).map(\.label), ["Yes", "No"])
    }

    // MARK: - Controls: rows that must NOT change

    /// A still-trading two-legged market with no grade keeps its bar.
    func testAnUngradedLivePriceKeepsItsBar() throws {
        let view = SpecialEventMarketsView(
            markets: Self.rows("""
            [
              {"market_name": "Philadelphia vs Atlanta: Extra Innings", "outcome_name": "Yes",
               "observed_at": "2026-09-30T19:58:00+00:00", "probability": 0.08, "source": "kalshi",
               "is_winner": null, "resolution_source": null}
            ]
            """),
            eventStatus: "live",
            commenceTime: Self.firstPitch
        )
        XCTAssertEqual(view.treatment(for: try Self.entry("Philadelphia vs Atlanta: Extra Innings", "Yes", in: view)), .livePrice)
    }

    /// #6595's specimen: a stale container graded the MONEYLINE before first
    /// pitch. That is the game's own question, and on a live page the hero is
    /// answering it differently — so no `Won`; the existing frozen quote stays.
    func testALiveGamesOwnQuestionNeverGetsAVerdict() throws {
        let rows = Self.rows("""
        [
          {"market_name": "New York Yankees vs. Minnesota Twins", "outcome_name": "New York Yankees",
           "observed_at": "2026-09-16T04:08:01.948721+00:00", "probability": 1.0, "source": "polymarket",
           "is_winner": true, "resolution_source": "api_settlement"}
        ]
        """)
        let start = ISO8601DateFormatter().date(from: "2026-09-16T17:40:00Z")
        let live = SpecialEventMarketsView(markets: rows, eventStatus: "live", commenceTime: start)
        let row = try Self.entry("New York Yankees vs. Minnesota Twins", "New York Yankees", in: live)
        XCTAssertTrue(row.gamesOwnQuestion)
        XCTAssertEqual(live.treatment(for: row), .frozenQuote, "a live tied game was crowned by a stale container")

        let final = SpecialEventMarketsView(markets: rows, eventStatus: "completed", commenceTime: start)
        XCTAssertEqual(
            final.treatment(for: try Self.entry("New York Yankees vs. Minnesota Twins", "New York Yankees", in: final)),
            .verdict(.won),
            "once the game is over its own question is answerable and settled means settled"
        )
    }

    func testARetractedGradeIsNeverSaid() throws {
        let view = SpecialEventMarketsView(
            markets: Self.rows("""
            [
              {"market_name": "Will there be a run scored in the first inning?: A vs. B", "outcome_name": "Yes",
               "observed_at": "2026-09-30T19:43:24+00:00", "probability": 1.0, "source": "polymarket",
               "is_winner": true, "resolution_source": "ungradeable_result"}
            ]
            """),
            eventStatus: "completed",
            commenceTime: Self.firstPitch
        )
        let row = try Self.entry("Will there be a run scored in the first inning?: A vs. B", "Yes", in: view)
        XCTAssertEqual(view.treatment(for: row), .frozenQuote)
    }

    // MARK: - The scope test's shape

    func testGamesOwnQuestionIsTheBareMatchupOnly() {
        XCTAssertTrue(SpecialEventMarketsView.isGamesOwnQuestion("New York Yankees vs. Minnesota Twins"))
        XCTAssertTrue(SpecialEventMarketsView.isGamesOwnQuestion("Philadelphia Phillies vs Atlanta Braves"))
        XCTAssertFalse(SpecialEventMarketsView.isGamesOwnQuestion(Self.pmQuestion))
        XCTAssertFalse(SpecialEventMarketsView.isGamesOwnQuestion(Self.kalshiQuestion))
        XCTAssertFalse(SpecialEventMarketsView.isGamesOwnQuestion("Deportivo Alavés vs. Valencia CF - Halftime Result"))
        XCTAssertFalse(SpecialEventMarketsView.isGamesOwnQuestion("A vs B vs C"))
        XCTAssertFalse(SpecialEventMarketsView.isGamesOwnQuestion("Saint-Étienne"))
        XCTAssertTrue(SpecialEventMarketsView.isGamesOwnQuestion("Saint-Étienne vs Lyon"))
        XCTAssertFalse(SpecialEventMarketsView.isGamesOwnQuestion(""))
    }

    // MARK: - Wiring

    /// `treatment` can be right while the row stops asking it. The row body is
    /// the one place a verdict becomes words, so pin that it switches on the
    /// treatment and prints the verdict's label.
    func testTheRowRendersTheVerdictItIsGiven() throws {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("Bain Luck/Components/SpecialEventMarketsView.swift")
        let source = try String(contentsOf: url, encoding: .utf8)
        XCTAssertTrue(source.contains("let rowTreatment = treatment(for: o)"))
        XCTAssertTrue(source.contains("switch rowTreatment {"))
        let verdictCase = try XCTUnwrap(source.range(of: "case .verdict(let v):"))
        XCTAssertTrue(source[verdictCase.upperBound...].prefix(120).contains("Text(v.label)"))
        XCTAssertFalse(source.contains("prob: m.probability ?? 0,\n                            sourceCount: 1,\n                            observedAt: m.observedAt\n                        )"),
                       "a second, verdict-blind row builder is back beside `entry(label:from:)`")
    }

    // MARK: - Fixture

    private static let pmQuestion =
        "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves"
    private static let kalshiQuestion = "Philadelphia vs Atlanta: First Inning Run"
    private static let firstPitch = ISO8601DateFormatter().date(from: "2026-09-30T18:00:00Z")

    /// `GET /api/events/15321782/game-markets` → `other[]`, read 2026-09-30 20:00Z,
    /// verbatim except for trimmed fractional seconds.
    private static let specimen = """
    [
      {"market_name": "Philadelphia Phillies vs. Atlanta Braves", "outcome_name": "Atlanta Braves",
       "observed_at": "2026-09-30T19:59:12+00:00", "contributor_outcome_ids": [237799856],
       "probability": 0.535, "source": "polymarket", "is_winner": null, "resolution_source": null,
       "_market_id": 63045821},
      {"market_name": "Philadelphia Phillies vs. Atlanta Braves", "outcome_name": "Philadelphia Phillies",
       "observed_at": "2026-09-30T20:00:16+00:00", "contributor_outcome_ids": [237799855],
       "probability": 0.465, "source": "polymarket", "is_winner": null, "resolution_source": null,
       "_market_id": 63045821},
      {"market_name": "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves",
       "outcome_name": "Yes", "observed_at": "2026-09-30T19:43:24+00:00", "contributor_outcome_ids": [238235947],
       "probability": 1.0, "source": "polymarket", "is_winner": true, "resolution_source": "clob_authoritative",
       "_market_id": 63194385},
      {"market_name": "Will there be a run scored in the first inning?: Philadelphia Phillies vs. Atlanta Braves",
       "outcome_name": "No", "observed_at": "2026-09-30T19:43:24+00:00", "contributor_outcome_ids": [238235948],
       "probability": null, "source": "polymarket", "is_winner": false, "resolution_source": "api_settlement",
       "_market_id": 63194385},
      {"market_name": "Philadelphia vs Atlanta: First Inning Run", "outcome_name": "Yes",
       "observed_at": "2026-09-30T19:58:11+00:00", "contributor_outcome_ids": [237550061],
       "probability": 0.99, "source": "kalshi", "is_winner": true, "resolution_source": "api_settlement",
       "_market_id": 62972338}
    ]
    """

    private static func card(status: String) -> SpecialEventMarketsView {
        SpecialEventMarketsView(markets: rows(specimen), eventStatus: status, commenceTime: firstPitch)
    }

    private static func entry(
        _ market: String, _ label: String, in view: SpecialEventMarketsView
    ) throws -> SpecialEventMarketsView.OutcomeEntry {
        let item = try XCTUnwrap(
            view.categories.flatMap(\.items).first { $0.name == market },
            "'\(market)' is not on the card"
        )
        return try XCTUnwrap(item.outcomes.first { $0.label == label }, "'\(market)' has no '\(label)' row")
    }

    private static func rows(_ json: String) -> [GameMarketOther] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        // swiftlint:disable:next force_try
        return try! decoder.decode([GameMarketOther].self, from: Data(json.utf8))
    }
}
