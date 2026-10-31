import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's adapter, part four ("All props", the
/// original catalogue and its Details), on a REAL served `/game-markets` body
/// decoded exactly as the app decodes it (`.convertFromSnakeCase`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED body, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///
/// - `mmaMarkets` — a REDUCED VERBATIM SUBSET of
///   `atlas-v6/raw/mma-15318681-game-markets.json` (sha256
///   8995ff44a52654a31ff09a824d6d7dfbdf0fda914799644856a30286cc6ffa27). Every
///   top-level key, in source order, is the source's bytes, except:
///     `game_question_matrix.questions`  10 of 17 kept, in source order:
///         m:63254893, m:63254894, m:63634393, m:63786874, m:63786875,
///         m:63786880, m:63786882, m:63786883, m:63900810, m:63900818
///     `outcome_market_ids`, `outcome_revision_at`, `outcome_observed_at`
///         emptied to {} (no adapter here reads them).
///   `totals` (3 of 3) and `other` (28 of 28) are whole: All props lists them.
///   Generated and checked by `/tmp/cli-10868-combat/make_subsets.py` (outside
///   the repo): every kept element is a verbatim substring of its source and the
///   parsed subset equals the selected elements key by key.
/// - the event — `CombatBoutPageAdapter10868Tests.mmaDetail` / `.boxingDetail`
///   and `.boxingMarkets`, byte for byte (sha256 there).
///
/// WHAT THE BODY SAYS. Every row is already settled by its venue (`is_winner`
/// with `resolution_source: api_settlement`); every matrix option is a result
/// (`value_state: result`) with no `pregame_reading` (the body predates #11125)
/// and every question serves `subject: null` and `predicate: null`.
///
/// THE TWO ROUND-TOTAL UNDERS (markets 63254895 and 63455521, no Over twin in
/// the catalogue) are served `is_winner: false` beside `over_probability: 0.0`.
/// A totals row's grade is on its Over's axis (`events.py`
/// `_settled_over_verdict`, #6239), so that `false` is the Over's, not these
/// Unders' own result. This is a difference of axis, not evidence that the
/// venue graded anything wrongly. The shared originals adapter shows each Under
/// as not yet confirmed, and never inverts the boolean or reads the finish.
///
/// CONSTRUCTED here, each named where used and changing only the keys it names:
/// the reader's calendar and `now`; `status: completed`; a pre-start detail
/// (`status: scheduled`); a live detail (`status: live`); one `other` row's
/// price, clock and settlement fields; one matrix option's `pregame_reading`.
@MainActor
final class CombatOriginalsAdapter10868Tests: XCTestCase {
    private typealias O = CombatOriginalsAdapter10868
    private typealias Fixtures = CombatBoutPageAdapter10868Tests
    private typealias Details = OriginalMarketDetails9483

    // MARK: - Fixture helpers (shared with the story and host tests)

    static func markets(_ json: String = CombatOriginalsAdapter10868Tests.mmaMarkets) throws -> GameMarketsResponse {
        try Fixtures.decoder().decode(GameMarketsResponse.self, from: Data(json.utf8))
    }

    static func object(_ json: String) throws -> [String: Any] {
        try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
    }

    static func decoded(_ body: [String: Any]) throws -> GameMarketsResponse {
        try Fixtures.decoder().decode(GameMarketsResponse.self, from: try JSONSerialization.data(withJSONObject: body))
    }

    /// CONSTRUCTED: `other[index]` with the named keys replaced (`NSNull()` is JSON null).
    static func editingOther(_ index: Int, _ setting: [String: Any]) throws -> GameMarketsResponse {
        var body = try object(mmaMarkets)
        var rows = try XCTUnwrap(body["other"] as? [[String: Any]])
        for (key, value) in setting { rows[index][key] = value }
        body["other"] = rows
        return try decoded(body)
    }

    /// CONSTRUCTED: one matrix option with the named keys replaced.
    static func editingOption(question: String, option: String, _ setting: [String: Any]) throws -> GameMarketsResponse {
        var body = try object(mmaMarkets)
        var matrix = try XCTUnwrap(body["game_question_matrix"] as? [String: Any])
        var questions = try XCTUnwrap(matrix["questions"] as? [[String: Any]])
        let q = try XCTUnwrap(questions.firstIndex { ($0["question_key"] as? String) == question })
        var options = try XCTUnwrap(questions[q]["options"] as? [[String: Any]])
        let o = try XCTUnwrap(options.firstIndex { ($0["option_key"] as? String) == option })
        for (key, value) in setting { options[o][key] = value }
        questions[q]["options"] = options
        matrix["questions"] = questions
        body["game_question_matrix"] = matrix
        return try decoded(body)
    }

    /// CONSTRUCTED: a `pregame_reading` for one option, naming `outcome`.
    static func pin(_ probability: Double, at: String, outcome: Int) -> [String: Any] {
        ["state": "available", "reason": NSNull(), "probability": probability, "observed_at": at,
         "basis": "pregame_pin", "outcome_id": outcome]
    }

    private func host(_ now: String) -> O.Host {
        O.Host(now: now.asDate!, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    private func clock(_ stamp: String, _ host: O.Host) -> String {
        CombatBoutPageAdapter10868.clockWords(stamp.asDate!, host: host.words)
    }

    private func build(_ event: EventDetail, _ markets: GameMarketsResponse?, _ now: String,
                       selection: Details.Selection? = nil) -> CombatEventPageOriginals10868 {
        O.originals(event, markets: markets, host: host(now), tint: .blue, selection: selection)
    }

    /// Catalogue positions of the originals these tests read (served order).
    private let decisionNo = 3, decisionYes = 4, knockoutYes = 9, knockoutNo = 10
    private let submissionNo = 23, submissionYes = 24

    private let sides = [
        "240262502", "238409899", "239081307", "240262515", "240262514", "240655015", "240655014",
        "238409894", "238409895", "240262496", "240262497", "240654996", "240654997", "240262508",
        "240262509", "240655012", "240655013", "240655017", "240655016", "240655021", "240655020",
        "240262510", "240262511", "239735846", "239735845", "240262499", "240262498", "238409897",
        "238409896", "240262513", "240262512",
    ]
    private let marketIDs = [
        "63786877", "63254895", "63455521", "63786883", "63786883", "63900819", "63900819",
        "63254893", "63254893", "63786874", "63786874", "63900810", "63900810", "63786880",
        "63786880", "63900818", "63900818", "63900820", "63900820", "63900822", "63900822",
        "63786881", "63786881", "63634393", "63634393", "63786875", "63786875", "63254894",
        "63254894", "63786882", "63786882",
    ]

    // MARK: - Fixture

    func testTheSubsetDecodesWithEveryRowAndAMatrixThatNamesNoSubject() throws {
        let markets = try Self.markets()
        XCTAssertEqual(markets.eventId, 15318681)
        XCTAssertEqual(markets.totals?.count, 3)
        XCTAssertEqual(markets.other?.count, 28)
        let matrix = try XCTUnwrap(markets.gameQuestionMatrix)
        XCTAssertEqual(matrix.contract, "10238.v1")
        XCTAssertEqual(matrix.questions.count, 10)
        XCTAssertTrue(matrix.questions.allSatisfy { $0.subject == nil && $0.predicate == nil },
                      "no production owner says which story a combat market belongs to")
        XCTAssertTrue(matrix.questions.flatMap(\.options).allSatisfy { $0.pregameReading == nil })
    }

    // MARK: - During (the retained state)

    func testDuringListsEveryServedOriginalOnceInCatalogueOrderByItsServedIds() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let built = build(event, try Self.markets(), Fixtures.readAt)
        let catalogue = try XCTUnwrap(built.catalogue)
        XCTAssertEqual(catalogue.scope, "combat:15318681:during:originals")
        XCTAssertEqual(catalogue.originals.count, 31)
        XCTAssertEqual(catalogue.originals.map(\.identity.side), sides)
        XCTAssertEqual(catalogue.originals.map(\.identity.market), marketIDs)
        XCTAssertTrue(catalogue.originals.allSatisfy { $0.identity.source == "polymarket" })
        XCTAssertEqual(Set(catalogue.originals.map(\.identity)).count, 31, "once each")
        XCTAssertEqual(built.heading, "All props")
        XCTAssertEqual(built.context, "31 originals")
        XCTAssertEqual(built.labels.count, 31)
        XCTAssertEqual(built.labels[catalogue.originals[0].identity], "O/U 0.5 Rounds · Over")
        XCTAssertEqual(built.labels[catalogue.originals[knockoutYes].identity], "Will the fight be won by KO or TKO? · Yes")
        XCTAssertEqual(built.labels[catalogue.originals[knockoutNo].identity], "Will the fight be won by KO or TKO? · No")
        XCTAssertNil(built.controls, "no owner proves combat categories, so every original is listed at once")
        XCTAssertNil(built.recorded)
    }

    func testDuringNoOriginalPrintsAPreMatchChanceWithoutItsOwnPin() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let originals = try XCTUnwrap(build(event, try Self.markets(), Fixtures.readAt).catalogue).originals
        XCTAssertTrue(originals.allSatisfy { $0.pregame == .missing("Pre-match chance not recorded") },
                      "a settled or current price is never relabelled pre-match")
        XCTAssertTrue(originals.allSatisfy { $0.mode == .comparison(.current) && $0.grade == nil })
    }

    func testDuringASettledWinnerShowsNoCurrentChanceAndItsUnpricedSideSaysNoRecentUpdate() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let originals = try XCTUnwrap(build(event, try Self.markets(), Fixtures.readAt).catalogue).originals
        let yes = originals[knockoutYes]
        XCTAssertEqual(yes.later, .missing("No current chance"), "a settled 100% is a result, never a chance")
        XCTAssertNil(yes.about.historicalQuote, "and never a saved price")
        XCTAssertEqual(yes.about, Details.About(
            source: "Polymarket", rules: .unavailable("Rules unavailable"),
            provenance: [Details.Row(label: "Market ID", value: "63786874"),
                         Details.Row(label: "Outcome ID", value: "240262496")],
            historicalQuote: nil))
        XCTAssertEqual(originals[knockoutNo].later, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(originals[0].later, .missing("No current chance"), "the O/U 0.5 Over row is settled too")
    }

    // MARK: - Final (constructed)

    func testTheFinalGradesEachOriginalByItsOwnServedSettlement() throws {
        // CONSTRUCTED: the detail's `status: completed`.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["status": "completed"])
        let originals = try XCTUnwrap(build(event, try Self.markets(), Fixtures.readAt).catalogue).originals
        func grade(_ index: Int) -> Details.Grade? { originals[index].grade }
        let won = Details.Grade(words: "Won", provenance: "Settled by Polymarket")
        let lost = Details.Grade(words: "Lost", provenance: "Settled by Polymarket")
        XCTAssertEqual(grade(knockoutYes), won)
        XCTAssertEqual(grade(knockoutNo), lost)
        XCTAssertEqual(grade(submissionYes), lost)
        XCTAssertEqual(grade(submissionNo), won)
        XCTAssertEqual(grade(decisionYes), lost)
        XCTAssertEqual(grade(decisionNo), won)
        XCTAssertTrue(originals.allSatisfy { $0.mode == .result && $0.later == nil })
        XCTAssertTrue(originals.allSatisfy { $0.pregame == .missing("Pre-match chance not recorded") })
        XCTAssertEqual(try XCTUnwrap(build(event, try Self.markets(), Fixtures.readAt).catalogue).scope,
                       "combat:15318681:final:originals")
    }

    /// The two real round-total Unders at the final: their served grade is the
    /// Over's, so each reads not yet confirmed, never Lost and never "sources
    /// disagree". Identity and position are unchanged. The O/U 0.5 Over keeps its
    /// own grade, and the direct Yes/No originals keep theirs.
    func testAtTheFinalAnUnderTotalIsNeverGradedWithItsOversResult() throws {
        // CONSTRUCTED: the detail's `status: completed`.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["status": "completed"])
        let originals = try XCTUnwrap(build(event, try Self.markets(), Fixtures.readAt).catalogue).originals
        let unconfirmed = Details.Grade(words: "Not yet confirmed", provenance: "Result not recorded yet")
        XCTAssertEqual(originals[1].identity, Details.Identity(source: "polymarket", market: "63254895", side: "238409899"))
        XCTAssertEqual(originals[2].identity, Details.Identity(source: "polymarket", market: "63455521", side: "239081307"))
        XCTAssertEqual(originals[1].outcome, "Under")
        XCTAssertEqual(originals[2].outcome, "Under")
        XCTAssertEqual(originals[1].grade, unconfirmed)
        XCTAssertEqual(originals[2].grade, unconfirmed)
        XCTAssertEqual(originals[1].mode, .result)
        XCTAssertEqual(originals[0].grade, Details.Grade(words: "Won", provenance: "Settled by Polymarket"),
                       "the Over's grade is its own")
        XCTAssertEqual(originals[knockoutNo].grade, Details.Grade(words: "Lost", provenance: "Settled by Polymarket"),
                       "a direct No original keeps its own grade")
    }

    // MARK: - The pin (constructed)

    func testThisOriginalsOwnPinIsItsPreMatchChanceAndAnotherOutcomesPinIsNeverBorrowed() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let reader = host(Fixtures.readAt)
        // CONSTRUCTED: option o:240262496's `pregame_reading`, naming its own outcome.
        let own = try Self.editingOption(question: "m:63786874", option: "o:240262496",
                                         ["pregame_reading": Self.pin(0.41, at: "2026-10-04T00:12:00+00:00", outcome: 240262496)])
        let originals = try XCTUnwrap(build(event, own, Fixtures.readAt).catalogue).originals
        XCTAssertEqual(originals[knockoutYes].pregame, .value(
            "41%", placement: 0.41,
            provenance: "Last recorded before start · \(clock("2026-10-04T00:12:00+00:00", reader)) · Polymarket"))
        XCTAssertEqual(originals[knockoutNo].pregame, .missing("Pre-match chance not recorded"))

        // CONSTRUCTED: the same reading naming the No outcome instead.
        let foreign = try Self.editingOption(question: "m:63786874", option: "o:240262496",
                                             ["pregame_reading": Self.pin(0.41, at: "2026-10-04T00:12:00+00:00", outcome: 240262497)])
        let refused = try XCTUnwrap(build(event, foreign, Fixtures.readAt).catalogue).originals
        XCTAssertEqual(refused[knockoutYes].pregame, .missing("Pre-match chance not recorded"))
        XCTAssertEqual(refused[knockoutNo].pregame, .missing("Pre-match chance not recorded"))
    }

    // MARK: - Before (constructed)

    func testBeforeTheStartTheCataloguePriceOnItsOwnRecentClockIsThePreMatchChance() throws {
        // CONSTRUCTED: the detail's `status: scheduled`; the KO Yes row unsettled
        // (`is_winner`, `resolution_source` null), priced 0.55 and observed 00:10Z;
        // read at 00:15Z, before the 00:20Z start. Only KO Yes / No are read: the
        // other rows keep their settled, later-dated values.
        let event = try Fixtures.edited(Fixtures.mmaDetail, ["status": "scheduled"])
        let markets = try Self.editingOther(6, ["probability": 0.55, "is_winner": NSNull(), "resolution_source": NSNull(),
                                                "observed_at": "2026-10-04T00:10:00+00:00"])
        let reader = host("2026-10-04T00:15:00Z")
        let originals = try XCTUnwrap(O.originals(event, markets: markets, host: reader, tint: .blue).catalogue).originals
        XCTAssertEqual(originals[knockoutYes].mode, .pregame)
        XCTAssertEqual(originals[knockoutYes].pregame, .value(
            "55%", placement: 0.55, provenance: "Recorded \(clock("2026-10-04T00:10:00+00:00", reader)) · Polymarket"))
        XCTAssertNil(originals[knockoutYes].later)
        XCTAssertEqual(originals[knockoutNo].pregame, .missing(AllMarketsCatalogView9483.unavailablePrice),
                       "the No side carries no price of its own; nothing is complemented")
    }

    // MARK: - In-fight (constructed)

    func testOnlyALiveFreshQuoteAfterTheStartIsTheInFightChance() throws {
        // CONSTRUCTED: the KO Yes row unsettled, priced 0.62 and observed 00:30Z.
        let markets = try Self.editingOther(6, ["probability": 0.62, "is_winner": NSNull(), "resolution_source": NSNull(),
                                                "observed_at": "2026-10-04T00:30:00+00:00"])
        let at = "2026-10-04T00:30:00+00:00"

        // CONSTRUCTED: `status: live`, read at 00:40Z.
        let live = try Fixtures.edited(Fixtures.mmaDetail, ["status": "live"])
        let fresh = host("2026-10-04T00:40:00Z")
        let current = try XCTUnwrap(O.originals(live, markets: markets, host: fresh, tint: .blue).catalogue).originals[knockoutYes]
        XCTAssertEqual(current.later, .value("62%", placement: 0.62, provenance: "Recorded \(clock(at, fresh)) · Polymarket"))
        XCTAssertNil(current.about.historicalQuote)

        // The retained suspended state: the same quote is history, never current.
        let suspended = try Fixtures.detail(Fixtures.mmaDetail)
        let held = try XCTUnwrap(O.originals(suspended, markets: markets, host: fresh, tint: .blue).catalogue).originals[knockoutYes]
        XCTAssertEqual(held.later, .missing("In-fight chance unavailable"))
        XCTAssertEqual(held.about.historicalQuote, Details.HistoricalQuote(text: "62%", recorded: "\(clock(at, fresh)) · Polymarket"))

        // 60 minutes later the quote is no longer recent.
        let late = host("2026-10-04T01:30:00Z")
        let stale = try XCTUnwrap(O.originals(live, markets: markets, host: late, tint: .blue).catalogue).originals[knockoutYes]
        XCTAssertEqual(stale.later, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(stale.about.historicalQuote?.text, "62%")
    }

    func testAQuoteObservedBeforeTheStartIsNeverAnInFightChance() throws {
        // CONSTRUCTED: the KO Yes row unsettled, priced 0.58 and observed 00:10Z; `status: live`, read 00:25Z.
        let markets = try Self.editingOther(6, ["probability": 0.58, "is_winner": NSNull(), "resolution_source": NSNull(),
                                                "observed_at": "2026-10-04T00:10:00+00:00"])
        let live = try Fixtures.edited(Fixtures.mmaDetail, ["status": "live"])
        let original = try XCTUnwrap(O.originals(live, markets: markets, host: host("2026-10-04T00:25:00Z"),
                                                 tint: .blue).catalogue).originals[knockoutYes]
        XCTAssertEqual(original.later, .missing("In-fight chance unavailable"))
        XCTAssertEqual(original.about.historicalQuote?.text, "58%")
    }

    // MARK: - Nothing served

    func testTheRetainedBoxingBoutServesNoOriginalsSoAllPropsSaysSo() throws {
        let event = try Fixtures.detail(Fixtures.boxingDetail)
        let markets = try Self.markets(Fixtures.boxingMarkets)
        for built in [build(event, markets, Fixtures.readAt), build(event, nil, Fixtures.readAt)] {
            XCTAssertNil(built.catalogue)
            XCTAssertNil(built.context)
            XCTAssertTrue(built.labels.isEmpty)
            XCTAssertEqual(built.emptyWords, "No retained originals for this fight")
            XCTAssertEqual(built.heading, "All props")
        }
    }

    func testTheHeldSelectionPassesThroughUnchanged() throws {
        let event = try Fixtures.detail(Fixtures.mmaDetail)
        let held = Details.Selection(scope: "combat:15318681:during:originals",
                                     identity: Details.Identity(source: "polymarket", market: "63786874", side: "240262496"))
        let built = build(event, try Self.markets(), Fixtures.readAt, selection: held)
        XCTAssertEqual(built.selection, held)
        XCTAssertEqual(Details.original(in: built.catalogue, selection: held)?.outcome, "Yes")
    }

    // MARK: - Retained body (reduced verbatim subset)

    static let mmaMarkets = ##"""
{"event_id":15318681,
"home_team":"Ateba Gautier",
"away_team":"Roman Kopylov",
"home_score":null,
"away_score":null,
"status":"suspended",
"totals":[
{"threshold":0.5,"over_probability":1.0,"source":"polymarket","market_type":"game_total","market_name":"O/U 0.5 Rounds","outcome_name":"Over","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262502],"is_winner":true,"resolution_source":"api_settlement","movement":0.175,"period":null,"_market_id":63786877,"_external_id":"0xcac5d1d30692d67f36bb7e983d34ff9c315be0d5462cab80c5abb79221787a09"},
{"threshold":1.5,"over_probability":0.0,"source":"polymarket","market_type":"game_total","market_name":"O/U 1.5 Rounds","outcome_name":"Under","observed_at":"2026-10-04T02:13:40.731794+00:00","contributor_outcome_ids":[238409899],"is_winner":false,"resolution_source":"api_settlement","movement":0.605,"period":null,"_market_id":63254895,"_external_id":"0x93536ea3a8927bfb113f551d6b0a01b2cdbefebc514a30424be4f637c501c20e"},
{"threshold":2.5,"over_probability":0.0,"source":"polymarket","market_type":"game_total","market_name":"O/U 2.5 Rounds","outcome_name":"Under","observed_at":"2026-10-04T01:16:02.902407+00:00","contributor_outcome_ids":[239081307],"is_winner":false,"resolution_source":"api_settlement","movement":0.415,"period":null,"_market_id":63455521,"_external_id":"0x28ba6e4ab27985a9b9aebc166fe452b7dfabd7d2e9e0aca4f5d124d34fbb482e"}
],
"player_props":[],
"team_totals":[],
"spreads":[],
"period_markets":[],
"closed_period_markets":[],
"matchups":[],
"other":[
{"market_name":"Will the fight end in a decision or draw?","outcome_name":"No","observed_at":"2026-10-03T08:03:50.187004+00:00","contributor_outcome_ids":[240262515],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63786883},
{"market_name":"Will the fight end in a decision or draw?","outcome_name":"Yes","observed_at":"2026-10-03T08:03:50.187004+00:00","contributor_outcome_ids":[240262514],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63786883},
{"market_name":"Will Roman Kopylov win in Round 2?","outcome_name":"No","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240655015],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63900819},
{"market_name":"Will Roman Kopylov win in Round 2?","outcome_name":"Yes","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240655014],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63900819},
{"market_name":"UFC 332: Roman Kopylov vs. Ateba Gautier (Middleweight, Main Card)","outcome_name":"Roman Kopylov","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[238409894],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63254893},
{"market_name":"UFC 332: Roman Kopylov vs. Ateba Gautier (Middleweight, Main Card)","outcome_name":"Ateba Gautier","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[238409895],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63254893},
{"market_name":"Will the fight be won by KO or TKO?","outcome_name":"Yes","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262496],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63786874},
{"market_name":"Will the fight be won by KO or TKO?","outcome_name":"No","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262497],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63786874},
{"market_name":"Will Roman Kopylov win by KO or TKO?","outcome_name":"Yes","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240654996],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63900810},
{"market_name":"Will Roman Kopylov win by KO or TKO?","outcome_name":"No","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240654997],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63900810},
{"market_name":"Will the fight end before Round 2?","outcome_name":"Yes","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262508],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63786880},
{"market_name":"Will the fight end before Round 2?","outcome_name":"No","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262509],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63786880},
{"market_name":"Will Roman Kopylov win in Round 1?","outcome_name":"Yes","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240655012],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63900818},
{"market_name":"Will Roman Kopylov win in Round 1?","outcome_name":"No","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240655013],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63900818},
{"market_name":"Will Roman Kopylov win in Round 3?","outcome_name":"No","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240655017],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63900820},
{"market_name":"Will Roman Kopylov win in Round 3?","outcome_name":"Yes","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240655016],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63900820},
{"market_name":"Will Ateba Gautier win in Round 3?","outcome_name":"No","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240655021],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63900822},
{"market_name":"Will Ateba Gautier win in Round 3?","outcome_name":"Yes","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240655020],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63900822},
{"market_name":"Will the fight end before Round 3?","outcome_name":"Yes","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262510],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63786881},
{"market_name":"Will the fight end before Round 3?","outcome_name":"No","observed_at":"2026-10-04T02:34:11.326692+00:00","contributor_outcome_ids":[240262511],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63786881},
{"market_name":"Will the fight be won by submission?","outcome_name":"No","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[239735846],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63634393},
{"market_name":"Will the fight be won by submission?","outcome_name":"Yes","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[239735845],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63634393},
{"market_name":"Will Ateba Gautier win by KO or TKO?","outcome_name":"No","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240262499],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63786875},
{"market_name":"Will Ateba Gautier win by KO or TKO?","outcome_name":"Yes","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[240262498],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63786875},
{"market_name":"Fight to Go the Distance?","outcome_name":"No","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[238409897],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63254894},
{"market_name":"Fight to Go the Distance?","outcome_name":"Yes","observed_at":"2026-10-03T23:27:48.847758+00:00","contributor_outcome_ids":[238409896],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63254894},
{"market_name":"Will Ateba Gautier win in Round 1?","outcome_name":"No","observed_at":"2026-10-03T16:42:41.515378+00:00","contributor_outcome_ids":[240262513],"probability":1.0,"source":"polymarket","is_winner":true,"resolution_source":"api_settlement","_market_id":63786882},
{"market_name":"Will Ateba Gautier win in Round 1?","outcome_name":"Yes","observed_at":"2026-10-03T16:42:41.515378+00:00","contributor_outcome_ids":[240262512],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":63786882}
],
"pace":null,
"props_script":[],
"during_player_props":null,
"after_player_props":null,
"game_question_matrix":{"contract":"10238.v1","display_scope":"game","questions":[
{"question_key":"m:63254893","proposition_key":null,"display_scope":"game","kind":"named_options","label":"UFC 332: Roman Kopylov vs. Ateba Gautier (Middleweight, Main Card)","market_name":"UFC 332: Roman Kopylov vs. Ateba Gautier (Middleweight, Main Card)","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:238409894","label":"Roman Kopylov","side":"away","market_ids":[63254893],"contributor_outcome_ids":[238409894],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63254893,"outcome_id":238409894,"leg_side":"away","raw_probability":1.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:238409895","label":"Ateba Gautier","side":"home","market_ids":[63254893],"contributor_outcome_ids":[238409895],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63254893,"outcome_id":238409895,"leg_side":"home","raw_probability":0.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63254894","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Fight to Go the Distance?","market_name":"Fight to Go the Distance?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:238409897","label":"No","side":"category","market_ids":[63254894],"contributor_outcome_ids":[238409897],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T23:27:48.847758+00:00"},"source_evidence":[{"source":"polymarket","market_id":63254894,"outcome_id":238409897,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-03T23:27:48.847758+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:238409896","label":"Yes","side":"category","market_ids":[63254894],"contributor_outcome_ids":[238409896],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T23:27:48.847758+00:00"},"source_evidence":[{"source":"polymarket","market_id":63254894,"outcome_id":238409896,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-03T23:27:48.847758+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63634393","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will the fight be won by submission?","market_name":"Will the fight be won by submission?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:239735846","label":"No","side":"category","market_ids":[63634393],"contributor_outcome_ids":[239735846],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T23:27:48.847758+00:00"},"source_evidence":[{"source":"polymarket","market_id":63634393,"outcome_id":239735846,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-03T23:27:48.847758+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:239735845","label":"Yes","side":"category","market_ids":[63634393],"contributor_outcome_ids":[239735845],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T23:27:48.847758+00:00"},"source_evidence":[{"source":"polymarket","market_id":63634393,"outcome_id":239735845,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-03T23:27:48.847758+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63786874","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will the fight be won by KO or TKO?","market_name":"Will the fight be won by KO or TKO?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240262496","label":"Yes","side":"category","market_ids":[63786874],"contributor_outcome_ids":[240262496],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786874,"outcome_id":240262496,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240262497","label":"No","side":"category","market_ids":[63786874],"contributor_outcome_ids":[240262497],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786874,"outcome_id":240262497,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63786875","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will Ateba Gautier win by KO or TKO?","market_name":"Will Ateba Gautier win by KO or TKO?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240262499","label":"No","side":"category","market_ids":[63786875],"contributor_outcome_ids":[240262499],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T23:27:48.847758+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786875,"outcome_id":240262499,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-03T23:27:48.847758+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240262498","label":"Yes","side":"category","market_ids":[63786875],"contributor_outcome_ids":[240262498],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T23:27:48.847758+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786875,"outcome_id":240262498,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-03T23:27:48.847758+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63786880","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will the fight end before Round 2?","market_name":"Will the fight end before Round 2?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240262508","label":"Yes","side":"category","market_ids":[63786880],"contributor_outcome_ids":[240262508],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786880,"outcome_id":240262508,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240262509","label":"No","side":"category","market_ids":[63786880],"contributor_outcome_ids":[240262509],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786880,"outcome_id":240262509,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63786882","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will Ateba Gautier win in Round 1?","market_name":"Will Ateba Gautier win in Round 1?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240262513","label":"No","side":"category","market_ids":[63786882],"contributor_outcome_ids":[240262513],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T16:42:41.515378+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786882,"outcome_id":240262513,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-03T16:42:41.515378+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240262512","label":"Yes","side":"category","market_ids":[63786882],"contributor_outcome_ids":[240262512],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T16:42:41.515378+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786882,"outcome_id":240262512,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-03T16:42:41.515378+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63786883","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will the fight end in a decision or draw?","market_name":"Will the fight end in a decision or draw?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240262515","label":"No","side":"category","market_ids":[63786883],"contributor_outcome_ids":[240262515],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T08:03:50.187004+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786883,"outcome_id":240262515,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-03T08:03:50.187004+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240262514","label":"Yes","side":"category","market_ids":[63786883],"contributor_outcome_ids":[240262514],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-03T08:03:50.187004+00:00"},"source_evidence":[{"source":"polymarket","market_id":63786883,"outcome_id":240262514,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-03T08:03:50.187004+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63900810","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will Roman Kopylov win by KO or TKO?","market_name":"Will Roman Kopylov win by KO or TKO?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240654996","label":"Yes","side":"category","market_ids":[63900810],"contributor_outcome_ids":[240654996],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63900810,"outcome_id":240654996,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240654997","label":"No","side":"category","market_ids":[63900810],"contributor_outcome_ids":[240654997],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63900810,"outcome_id":240654997,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]},
{"question_key":"m:63900818","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Will Roman Kopylov win in Round 1?","market_name":"Will Roman Kopylov win in Round 1?","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:240655012","label":"Yes","side":"category","market_ids":[63900818],"contributor_outcome_ids":[240655012],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63900818,"outcome_id":240655012,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:240655013","label":"No","side":"category","market_ids":[63900818],"contributor_outcome_ids":[240655013],"published":{"value":null,"value_state":"result","basis":"result","source":"polymarket","observed_at":"2026-10-04T02:34:11.326692+00:00"},"source_evidence":[{"source":"polymarket","market_id":63900818,"outcome_id":240655013,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-04T02:34:11.326692+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":1.0,"legs":2}]}
],"series_markets_count":null,"coverage":{"scope":"rows_served_by_this_response","questions":17,"options":31,"by_kind":{"count_threshold":0,"signed_handicap":0,"rank_predicate":0},"untyped":{"untyped_period":0,"untyped_unit":3,"untyped_subject":0,"untyped_predicate":0},"build_errors":0}},
"stream_market_ids":[61556133,61620856,63254893,63254894,63254895,63455521,63634393,63786874,63786875,63786877,63786880,63786881,63786882,63786883,63900810,63900818,63900819,63900820,63900822],
"outcome_market_ids":{},
"outcome_revision_at":{},
"outcome_observed_at":{},
"open_winner_quote":null,
"closed_winner_market_ids":[],
"cache":{"generation":3,"created_at":"2026-10-11T04:56:43.678329+00:00","quality":"full","availability":"live","lifecycle_watermark":"2026-10-04T02:34:11.363715+00:00","quality_reasons":[],"source_status":"suspended","build_id":"v5643"}}
"""##
}
