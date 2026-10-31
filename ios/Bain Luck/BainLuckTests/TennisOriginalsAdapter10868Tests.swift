import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's adapter, part four ("All props", the
/// original catalogue and its Details), on REAL served `/game-markets` bodies
/// decoded exactly as the app decodes them (`.convertFromSnakeCase`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED bodies, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/accessible-chart-inspection-v90/raw/`:
///
/// - `liveMarkets` — a REDUCED VERBATIM SUBSET of `tennis-15327807-game-markets.json`
///   (23,309 bytes, sha256 b2e25ae1e2ecdb36c64129172b1b206f1129a87b1235a5fffb1425446c6371bf).
///   Every top-level key, in source order, is the source's bytes, except
///   `outcome_market_ids`, `outcome_revision_at` and `outcome_observed_at`,
///   emptied to {} (no adapter here reads them). `totals` (2), `spreads` (2),
///   `other` (8) and all 7 matrix questions are whole.
/// - `finalMarkets` — a REDUCED VERBATIM SUBSET of `tennis-15327291-game-markets.json`
///   (32,615 bytes, sha256 8b2973395e82cdaec8ebafd106bc996a96c94cca96b11e1421c472df2697e367):
///   the same three keys emptied, and `game_question_matrix.questions` 2 of 11
///   kept, in source order: m:65129355, m:65129363. `totals` (3), `spreads` (3)
///   and `other` (12) are whole: All props lists them.
///   Generated and checked by `/tmp/cli-10868-tennis/make_market_subsets.py`
///   (outside the repo): every kept element is a verbatim substring of its
///   source and the parsed subset equals the selected elements key by key.
/// - the events — `TennisMatchPageAdapter10868Tests.liveDetail` / `.finalDetail`,
///   byte for byte (sha256 there).
///
/// WHAT THE BODIES SAY. Live: every matrix question serves `subject: null` and
/// `predicate: null`; the match winner, first-set winner, set handicap and game
/// spread options carry a `pregame_pin` comparison baseline (10:17Z); the four
/// exact-score options say `no_pregame_pin`; the two total-games options are
/// labelled "Over" by the matrix while the served `totals` rows name the same
/// outcome ids "Under" with an `over_probability` — a served contradiction the
/// catalogue answers by printing no price for the Under leg (gotcha #17), and
/// that this adapter does not resolve (owner: backend `/game-markets` totals).
/// Final: every row is settled by its venue (`clob_authoritative` or
/// `api_settlement`), and no option serves a pin (`not_quoted`, no
/// `pregame_reading`).
///
/// CONSTRUCTED here, each named where used and changing only the keys it names:
/// the reader's calendar and `now`; a pre-start detail (`status: scheduled`,
/// `commence_time` 13:00Z); a suspended detail (`status: suspended`).
@MainActor
final class TennisOriginalsAdapter10868Tests: XCTestCase {
    private typealias O = TennisOriginalsAdapter10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Details = OriginalMarketDetails9483

    // MARK: - Fixture helpers (shared with the page-input and host tests)

    static func live() throws -> GameMarketsResponse {
        try Fixtures.decoder().decode(GameMarketsResponse.self, from: Data(liveMarkets.utf8))
    }

    static func finished() throws -> GameMarketsResponse {
        try Fixtures.decoder().decode(GameMarketsResponse.self, from: Data(finalMarkets.utf8))
    }

    private func host(_ now: String) -> O.Host {
        O.Host(now: now.asDate!, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    private func clock(_ stamp: String, _ host: O.Host) -> String {
        TennisMatchPageAdapter10868.clockWords(stamp.asDate!, host: host.words)
    }

    private func build(_ event: EventDetail, _ markets: GameMarketsResponse?, _ now: String,
                       selection: Details.Selection? = nil) -> TennisEventPageOriginals10868 {
        O.originals(event, markets: markets, host: host(now), tint: .blue, selection: selection)
    }

    /// Catalogue positions (served order): totals, spreads, then other.
    private let underLow = 0, underHigh = 1, setHandicap = 2, gameSpread = 3
    private let setOneVanDeZandschulp = 4, setOneFils = 5, matchVanDeZandschulp = 6, matchFils = 7
    private let exactVanDeZandschulpStraight = 8, exactFilsThree = 9, exactVanDeZandschulpThree = 10
    private let exactFilsStraight = 11

    private let liveSides = [
        "245152784", "245152786", "245152788", "245201950", "245152776", "245152775", "245152774",
        "245152773", "245059341", "245059339", "245059340", "245059338",
    ]
    private let liveMarketIDs = [
        "65197799", "65197800", "65197801", "65212323", "65197795", "65197795", "65197794", "65197794",
        "65176060", "65176060", "65176060", "65176060",
    ]
    private let finalSides = [
        "244929349", "244876655", "244876657", "244876662", "244876660", "244973047", "244894423",
        "244894424", "244873262", "244873263", "244929344", "244929343", "244929341", "244929342",
        "244894447", "244894448", "244894446", "244894445",
    ]

    // MARK: - Fixtures

    func testTheSubsetsDecodeWithEveryRowAndAMatrixThatNamesNoSubject() throws {
        let live = try Self.live()
        XCTAssertEqual(live.eventId, 15327807)
        XCTAssertEqual(live.totals?.count, 2)
        XCTAssertEqual(live.spreads?.count, 2)
        XCTAssertEqual(live.other?.count, 8)
        let matrix = try XCTUnwrap(O.matrix(live))
        XCTAssertEqual(matrix.questions.count, 7)
        XCTAssertTrue(matrix.questions.allSatisfy { $0.subject == nil && $0.predicate == nil },
                      "no production owner says which story a tennis market belongs to")
        XCTAssertEqual(QuestionCatalog9483.sourceOutcomeCount(live), 12)
        let finished = try Self.finished()
        XCTAssertEqual(finished.totals?.count, 3)
        XCTAssertEqual(finished.spreads?.count, 3)
        XCTAssertEqual(finished.other?.count, 12)
        XCTAssertEqual(O.matrix(finished)?.questions.count, 2)
    }

    // MARK: - During (the retained live state)

    func testDuringListsEveryServedOriginalOnceInCatalogueOrderByItsServedIds() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let built = build(event, try Self.live(), Fixtures.liveReadAt)
        let catalogue = try XCTUnwrap(built.catalogue)
        XCTAssertEqual(catalogue.scope, "tennis:15327807:during:originals")
        XCTAssertEqual(catalogue.originals.count, 12)
        XCTAssertEqual(catalogue.originals.map(\.identity.side), liveSides)
        XCTAssertEqual(catalogue.originals.map(\.identity.market), liveMarketIDs)
        XCTAssertEqual(catalogue.originals.map(\.identity.source),
                       Array(repeating: "polymarket", count: 8) + Array(repeating: "kalshi", count: 4))
        XCTAssertEqual(Set(catalogue.originals.map(\.identity)).count, 12, "once each")
        XCTAssertEqual(built.heading, "All props")
        XCTAssertEqual(built.context, "12 originals")
        XCTAssertEqual(built.labels[catalogue.originals[setHandicap].identity],
                       "Set Handicap: Arthur Fils (-1.5) vs Botic van de Zandschulp (+1.5) · Botic van de Zandschulp")
        XCTAssertEqual(built.labels[catalogue.originals[exactFilsThree].identity],
                       "Arthur Fils vs Botic Van de Zandschulp: Exact Match Score · Arthur Fils wins 2-1")
        XCTAssertEqual(built.labels[catalogue.originals[underLow].identity], "Fils vs. Zandschulp: Match O/U 22.5 · Under")
        XCTAssertNil(built.recorded)
    }

    func testDuringEachOriginalsOwnPinIsItsPreMatchChanceAndNoPinSaysWhy() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let reader = host(Fixtures.liveReadAt)
        let originals = try XCTUnwrap(build(event, try Self.live(), Fixtures.liveReadAt).catalogue).originals
        func pinned(_ text: String, _ value: Double, _ at: String) -> Details.Reading {
            .value(text, placement: value,
                   provenance: "Last recorded before start · \(clock(at, reader)) · Polymarket")
        }
        XCTAssertEqual(originals[setHandicap].pregame, pinned("44%", 0.435, "2026-10-12T10:17:14.911446+00:00"))
        XCTAssertEqual(originals[gameSpread].pregame, pinned("55%", 0.55, "2026-10-12T10:17:14.950625+00:00"))
        XCTAssertEqual(originals[setOneVanDeZandschulp].pregame, pinned("28%", 0.28, "2026-10-12T10:17:14.835808+00:00"))
        XCTAssertEqual(originals[setOneFils].pregame, pinned("72%", 0.72, "2026-10-12T10:17:14.835808+00:00"))
        XCTAssertEqual(originals[matchVanDeZandschulp].pregame, pinned("22%", 0.22, "2026-10-12T10:17:15.022760+00:00"))
        XCTAssertEqual(originals[matchFils].pregame, pinned("79%", 0.785, "2026-10-12T10:17:15.022760+00:00"))
        for index in [exactVanDeZandschulpStraight, exactFilsThree, exactVanDeZandschulpThree, exactFilsStraight] {
            XCTAssertEqual(originals[index].pregame, .missing("Pre-match chance not recorded"),
                           "the server says no pre-match pin was recorded")
        }
        for index in [underLow, underHigh] {
            XCTAssertEqual(originals[index].pregame, .missing("Pre-match chance unavailable"),
                           "a complement leg's pin is not served; it is not said to be unrecorded")
        }
        XCTAssertTrue(originals.allSatisfy { $0.mode == .comparison(.current) && $0.grade == nil })
    }

    func testDuringAFreshQuoteAfterTheStartIsTheCurrentChance() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let reader = host(Fixtures.liveReadAt)
        let originals = try XCTUnwrap(build(event, try Self.live(), Fixtures.liveReadAt).catalogue).originals
        XCTAssertEqual(originals[setHandicap].later, .value(
            ">99%", placement: 0.9995,
            provenance: "Recorded \(clock("2026-10-12T12:01:17.024578+00:00", reader)) · Polymarket"))
        XCTAssertEqual(originals[setOneFils].later, .value(
            "<1%", placement: 0.0005,
            provenance: "Recorded \(clock("2026-10-12T11:59:14.942512+00:00", reader)) · Polymarket"))
        XCTAssertEqual(originals[exactFilsStraight].later, .value(
            "1%", placement: 0.01, provenance: "Recorded \(clock("2026-10-12T11:55:06.745445+00:00", reader)) · Kalshi"),
            "29 minutes old is still recent")
        XCTAssertNil(originals[setHandicap].about.historicalQuote)
        // The Under leg carries its Over line's price, never its own.
        XCTAssertEqual(originals[underLow].later, .missing(AllMarketsCatalogView9483.unavailablePrice))
        XCTAssertEqual(originals[setHandicap].about, Details.About(
            source: "Polymarket", rules: .unavailable("Rules unavailable"),
            provenance: [Details.Row(label: "Market ID", value: "65197801"),
                         Details.Row(label: "Outcome ID", value: "245152788")],
            historicalQuote: nil))
    }

    func testAStaleQuoteIsTheHistoricalQuoteNeverTheCurrentChance() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let late = host(Fixtures.staleReadAt)
        let originals = try XCTUnwrap(build(event, try Self.live(), Fixtures.staleReadAt).catalogue).originals
        XCTAssertEqual(originals[setHandicap].later, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertEqual(originals[setHandicap].about.historicalQuote, Details.HistoricalQuote(
            text: ">99%", recorded: "\(clock("2026-10-12T12:01:17.024578+00:00", late)) · Polymarket"))
        XCTAssertEqual(originals[underLow].later, .missing(AllMarketsCatalogView9483.noRecentPrice))
        XCTAssertNil(originals[underLow].about.historicalQuote, "no price of its own, so no quote to keep")
    }

    func testASuspendedMatchHasNoCurrentChanceAndKeepsTheQuoteAsHistory() throws {
        // CONSTRUCTED: the detail's `status: suspended`.
        let event = try Fixtures.edited(Fixtures.liveDetail, ["status": "suspended"])
        let reader = host(Fixtures.liveReadAt)
        let original = try XCTUnwrap(build(event, try Self.live(), Fixtures.liveReadAt).catalogue).originals[gameSpread]
        XCTAssertEqual(original.later, .missing("Current chance unavailable"))
        XCTAssertEqual(original.about.historicalQuote, Details.HistoricalQuote(
            text: "87%", recorded: "\(clock("2026-10-12T12:18:15.628011+00:00", reader)) · Polymarket"))
        XCTAssertEqual(original.pregame.figure, .value("55%"), "the pin is the pin in every during state")
    }

    // MARK: - Before (constructed)

    func testBeforeTheStartTheCataloguePriceOnItsOwnRecentClockIsThePreMatchChance() throws {
        // CONSTRUCTED: the detail's `status: scheduled` and `commence_time` 13:00Z, read at 12:24:30Z.
        let event = try Fixtures.edited(Fixtures.liveDetail, ["status": "scheduled",
                                                              "commence_time": "2026-10-12T13:00:00+00:00"])
        let reader = host(Fixtures.liveReadAt)
        let built = O.originals(event, markets: try Self.live(), host: reader, tint: .blue)
        let catalogue = try XCTUnwrap(built.catalogue)
        XCTAssertEqual(catalogue.scope, "tennis:15327807:before:originals")
        let originals = catalogue.originals
        XCTAssertTrue(originals.allSatisfy { $0.mode == .pregame && $0.later == nil && $0.grade == nil })
        XCTAssertEqual(originals[gameSpread].pregame, .value(
            "87%", placement: 0.87,
            provenance: "Recorded \(clock("2026-10-12T12:18:15.628011+00:00", reader)) · Polymarket"))
        XCTAssertEqual(originals[underLow].pregame, .missing(AllMarketsCatalogView9483.unavailablePrice),
                       "the Under leg carries no price of its own; nothing is complemented")
    }

    // MARK: - Final (retained)

    func testTheFinalGradesEachOriginalByItsOwnServedSettlement() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let built = build(event, try Self.finished(), Fixtures.finalReadAt)
        let catalogue = try XCTUnwrap(built.catalogue)
        XCTAssertEqual(catalogue.scope, "tennis:15327291:final:originals")
        XCTAssertEqual(catalogue.originals.count, 18)
        XCTAssertEqual(catalogue.originals.map(\.identity.side), finalSides)
        XCTAssertEqual(built.context, "18 originals")
        let won = Details.Grade(words: "Won", provenance: "Settled by Polymarket")
        let lost = Details.Grade(words: "Lost", provenance: "Settled by Polymarket")
        let wonKalshi = Details.Grade(words: "Won", provenance: "Settled by Kalshi")
        let lostKalshi = Details.Grade(words: "Lost", provenance: "Settled by Kalshi")
        XCTAssertEqual(catalogue.originals.map(\.grade), [
            won, won, won,                                  // total games 21.5 / 22.5 / 23.5 · Over
            won, won, won,                                  // set handicaps and the game spread
            wonKalshi, lostKalshi,                          // match winner
            won, lost,                                      // completed match · Yes / No
            won, lost,                                      // set 2 winner
            won, lost,                                      // set 1 winner
            wonKalshi, lostKalshi, lostKalshi, lostKalshi,  // exact set finishes
        ])
        XCTAssertTrue(catalogue.originals.allSatisfy { $0.mode == .result && $0.later == nil })
        XCTAssertTrue(catalogue.originals.allSatisfy { $0.pregame == .missing("Pre-match chance unavailable") },
                      "a settled option serves no pin; it is not said to be unrecorded, and never 0% or 100%")
        XCTAssertEqual(built.labels[catalogue.originals[14].identity],
                       "Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score · Alejandro Davidovich Fokina wins 2-1")
    }

    // MARK: - Nothing served

    func testNoMarketsServesNoCatalogueSoAllPropsSaysSo() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let built = build(event, nil, Fixtures.liveReadAt)
        XCTAssertNil(built.catalogue)
        XCTAssertNil(built.context)
        XCTAssertTrue(built.labels.isEmpty)
        XCTAssertEqual(built.emptyWords, "No retained originals for this match")
        XCTAssertEqual(built.heading, "All props")
    }

    func testTheHeldSelectionPassesThroughUnchanged() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let held = Details.Selection(scope: "tennis:15327807:during:originals",
                                     identity: Details.Identity(source: "polymarket", market: "65197801", side: "245152788"))
        let built = build(event, try Self.live(), Fixtures.liveReadAt, selection: held)
        XCTAssertEqual(built.selection, held)
        XCTAssertEqual(Details.original(in: built.catalogue, selection: held)?.outcome, "Botic van de Zandschulp")
    }

    // MARK: - Retained bodies (reduced verbatim subsets)

    static let liveMarkets = ##"""
{"event_id":15327807,
"home_team":"Arthur Fils",
"away_team":"Botic van de Zandschulp",
"home_score":0,
"away_score":1,
"score_source":"espn",
"score_observed_at":"2026-10-12T12:20:44.471140+00:00",
"status":"live",
"totals":[
{"threshold":22.5,"over_probability":0.465,"source":"polymarket","market_type":"game_total","market_name":"Fils vs. Zandschulp: Match O/U 22.5","outcome_name":"Under","observed_at":"2026-10-12T12:23:57.848353+00:00","contributor_outcome_ids":[245152784],"is_winner":null,"resolution_source":null,"movement":-0.01,"period":null,"_market_id":65197799,"_external_id":"0xa7fd4cc530a883d5c3246baa8284696c935d8649ce02241c4a18a023d67aa988"},
{"threshold":23.5,"over_probability":0.45,"source":"polymarket","market_type":"game_total","market_name":"Fils vs. Zandschulp: Match O/U 23.5","outcome_name":"Under","observed_at":"2026-10-12T12:24:01.665942+00:00","contributor_outcome_ids":[245152786],"is_winner":null,"resolution_source":null,"movement":-0.055,"period":null,"_market_id":65197800,"_external_id":"0x640f378707fe030b677dc74ea2e0a85bd2acbc1a3b6ce84e5c399e7ee9a25e89"}
],
"player_props":[],
"team_totals":[],
"spreads":[
{"market_name":"Set Handicap: Arthur Fils (-1.5) vs Botic van de Zandschulp (+1.5)","outcome_name":"Botic van de Zandschulp","observed_at":"2026-10-12T12:01:17.024578+00:00","contributor_outcome_ids":[245152788],"threshold":null,"probability":0.9995,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":65197801},
{"market_name":"Game Spread: Arthur Fils (-4.5) vs Botic van de Zandschulp (+4.5)","outcome_name":"Botic van de Zandschulp","observed_at":"2026-10-12T12:18:15.628011+00:00","contributor_outcome_ids":[245201950],"threshold":null,"probability":0.87,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":65212323}
],
"period_markets":[],
"closed_period_markets":[],
"matchups":[],
"other":[
{"market_name":"Set 1 Winner: Arthur Fils vs Botic van de Zandschulp","outcome_name":"Botic van de Zandschulp","observed_at":"2026-10-12T11:59:24.344917+00:00","contributor_outcome_ids":[245152776],"probability":0.999,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":65197795},
{"market_name":"Set 1 Winner: Arthur Fils vs Botic van de Zandschulp","outcome_name":"Arthur Fils","observed_at":"2026-10-12T11:59:14.942512+00:00","contributor_outcome_ids":[245152775],"probability":0.0005,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":65197795},
{"market_name":"Shanghai Rolex Masters: Arthur Fils vs Botic van de Zandschulp","outcome_name":"Botic van de Zandschulp","observed_at":"2026-10-12T12:24:01.645538+00:00","contributor_outcome_ids":[245152774],"probability":0.74,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":65197794},
{"market_name":"Shanghai Rolex Masters: Arthur Fils vs Botic van de Zandschulp","outcome_name":"Arthur Fils","observed_at":"2026-10-12T12:23:57.067532+00:00","contributor_outcome_ids":[245152773],"probability":0.255,"source":"polymarket","is_winner":null,"resolution_source":null,"_market_id":65197794},
{"market_name":"Arthur Fils vs Botic Van de Zandschulp: Exact Match Score","outcome_name":"Botic Van de Zandschulp wins 2-0","observed_at":"2026-10-12T12:23:56.174931+00:00","contributor_outcome_ids":[245059341],"probability":0.6667,"source":"kalshi","is_winner":null,"resolution_source":null,"_market_id":65176060},
{"market_name":"Arthur Fils vs Botic Van de Zandschulp: Exact Match Score","outcome_name":"Arthur Fils wins 2-1","observed_at":"2026-10-12T12:23:56.174931+00:00","contributor_outcome_ids":[245059339],"probability":0.2438,"source":"kalshi","is_winner":null,"resolution_source":null,"_market_id":65176060},
{"market_name":"Arthur Fils vs Botic Van de Zandschulp: Exact Match Score","outcome_name":"Botic Van de Zandschulp wins 2-1","observed_at":"2026-10-12T12:23:56.174931+00:00","contributor_outcome_ids":[245059340],"probability":0.0796,"source":"kalshi","is_winner":null,"resolution_source":null,"_market_id":65176060},
{"market_name":"Arthur Fils vs Botic Van de Zandschulp: Exact Match Score","outcome_name":"Arthur Fils wins 2-0","observed_at":"2026-10-12T11:55:06.745445+00:00","contributor_outcome_ids":[245059338],"probability":0.01,"source":"kalshi","is_winner":null,"resolution_source":null,"_market_id":65176060}
],
"pace":null,
"props_script":[],
"during_player_props":null,
"after_player_props":null,
"game_question_matrix":{"contract":"10238.v1","display_scope":"game","questions":[
{"question_key":"m:65197799","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Fils vs. Zandschulp: Match O/U 22.5","market_name":"Fils vs. Zandschulp: Match O/U 22.5","source_array":"totals","quantity":null,"period":{"key":"full_game","label":"Game"},"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"untyped","reason":"untyped_unit"},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245152784","label":"Over","side":"category","market_ids":[65197799],"contributor_outcome_ids":[245152784],"published":{"value":0.465,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T12:23:57.848353+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197799,"outcome_id":245152784,"leg_side":"under","raw_probability":0.535,"observed_at":"2026-10-12T12:23:57.848353+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"unavailable","reason":"leg_is_complement","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[{"option_key":"o:245152783","outcome_id":245152783,"label":"Over","side":null,"value_state":"unavailable"}],"option_counts":{"declared":null,"loaded":2,"returned":1,"missing_identified":1},"complete":false,"source_totals":[{"source":"polymarket","raw_sum":0.535,"legs":1}]},
{"question_key":"m:65197800","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Fils vs. Zandschulp: Match O/U 23.5","market_name":"Fils vs. Zandschulp: Match O/U 23.5","source_array":"totals","quantity":null,"period":{"key":"full_game","label":"Game"},"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"untyped","reason":"untyped_unit"},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245152786","label":"Over","side":"category","market_ids":[65197800],"contributor_outcome_ids":[245152786],"published":{"value":0.45,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T12:24:01.665942+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197800,"outcome_id":245152786,"leg_side":"under","raw_probability":0.55,"observed_at":"2026-10-12T12:24:01.665942+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"unavailable","reason":"leg_is_complement","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[{"option_key":"o:245152785","outcome_id":245152785,"label":"Over","side":null,"value_state":"unavailable"}],"option_counts":{"declared":null,"loaded":2,"returned":1,"missing_identified":1},"complete":false,"source_totals":[{"source":"polymarket","raw_sum":0.55,"legs":1}]},
{"question_key":"m:65197801","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Set Handicap: Arthur Fils (-1.5) vs Botic van de Zandschulp (+1.5)","market_name":"Set Handicap: Arthur Fils (-1.5) vs Botic van de Zandschulp (+1.5)","source_array":"spreads","quantity":null,"period":{"key":"full_game","label":"Game"},"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"untyped","reason":"untyped_unit"},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245152788","label":"Botic van de Zandschulp","side":"away","market_ids":[65197801],"contributor_outcome_ids":[245152788],"published":{"value":0.9995,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T12:01:17.024578+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197801,"outcome_id":245152788,"leg_side":"away","raw_probability":0.9995,"observed_at":"2026-10-12T12:01:17.024578+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"comparable","reason":null,"baseline":{"probability":0.435,"observed_at":"2026-10-12T10:17:14.911446+00:00","basis":"pregame_pin"},"latest":{"probability":0.9995,"observed_at":"2026-10-12T12:01:17.024578+00:00"},"delta_points":56.5}}],"missing_options":[{"option_key":"o:245152787","outcome_id":245152787,"label":"Arthur Fils","side":"home","value_state":"unavailable"}],"option_counts":{"declared":null,"loaded":2,"returned":1,"missing_identified":1},"complete":false,"source_totals":[{"source":"polymarket","raw_sum":0.9995,"legs":1}]},
{"question_key":"m:65212323","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Game Spread: Arthur Fils (-4.5) vs Botic van de Zandschulp (+4.5)","market_name":"Game Spread: Arthur Fils (-4.5) vs Botic van de Zandschulp (+4.5)","source_array":"spreads","quantity":null,"period":{"key":"full_game","label":"Game"},"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"untyped","reason":"untyped_unit"},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245201950","label":"Botic van de Zandschulp","side":"away","market_ids":[65212323],"contributor_outcome_ids":[245201950],"published":{"value":0.87,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T12:18:15.628011+00:00"},"source_evidence":[{"source":"polymarket","market_id":65212323,"outcome_id":245201950,"leg_side":"away","raw_probability":0.87,"observed_at":"2026-10-12T12:18:15.628011+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"comparable","reason":null,"baseline":{"probability":0.55,"observed_at":"2026-10-12T10:17:14.950625+00:00","basis":"pregame_pin"},"latest":{"probability":0.87,"observed_at":"2026-10-12T12:18:15.628011+00:00"},"delta_points":32.0}}],"missing_options":[{"option_key":"o:245201949","outcome_id":245201949,"label":"Arthur Fils","side":"home","value_state":"unpriced"}],"option_counts":{"declared":null,"loaded":2,"returned":1,"missing_identified":1},"complete":false,"source_totals":[{"source":"polymarket","raw_sum":0.87,"legs":1}]},
{"question_key":"m:65176060","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Arthur Fils vs Botic Van de Zandschulp: Exact Match Score","market_name":"Arthur Fils vs Botic Van de Zandschulp: Exact Match Score","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245059341","label":"Botic Van de Zandschulp wins 2-0","side":"category","market_ids":[65176060],"contributor_outcome_ids":[245059341],"published":{"value":0.6667,"value_state":"quoted","basis":"published_source_display","source":"kalshi","observed_at":"2026-10-12T12:23:56.174931+00:00"},"source_evidence":[{"source":"kalshi","market_id":65176060,"outcome_id":245059341,"leg_side":"category","raw_probability":0.67,"observed_at":"2026-10-12T12:23:56.174931+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"unavailable","reason":"no_pregame_pin","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:245059339","label":"Arthur Fils wins 2-1","side":"category","market_ids":[65176060],"contributor_outcome_ids":[245059339],"published":{"value":0.2438,"value_state":"quoted","basis":"published_source_display","source":"kalshi","observed_at":"2026-10-12T12:23:56.174931+00:00"},"source_evidence":[{"source":"kalshi","market_id":65176060,"outcome_id":245059339,"leg_side":"category","raw_probability":0.245,"observed_at":"2026-10-12T12:23:56.174931+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"unavailable","reason":"no_pregame_pin","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:245059340","label":"Botic Van de Zandschulp wins 2-1","side":"category","market_ids":[65176060],"contributor_outcome_ids":[245059340],"published":{"value":0.0796,"value_state":"quoted","basis":"published_source_display","source":"kalshi","observed_at":"2026-10-12T12:23:56.174931+00:00"},"source_evidence":[{"source":"kalshi","market_id":65176060,"outcome_id":245059340,"leg_side":"category","raw_probability":0.08,"observed_at":"2026-10-12T12:23:56.174931+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"unavailable","reason":"no_pregame_pin","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:245059338","label":"Arthur Fils wins 2-0","side":"category","market_ids":[65176060],"contributor_outcome_ids":[245059338],"published":{"value":0.01,"value_state":"quoted","basis":"published_source_display","source":"kalshi","observed_at":"2026-10-12T11:55:06.745445+00:00"},"source_evidence":[{"source":"kalshi","market_id":65176060,"outcome_id":245059338,"leg_side":"category","raw_probability":0.01,"observed_at":"2026-10-12T11:55:06.745445+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"unavailable","reason":"no_pregame_pin","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":4,"loaded":4,"returned":4,"missing_identified":0},"complete":true,"source_totals":[{"source":"kalshi","raw_sum":1.005,"legs":4}]},
{"question_key":"m:65197794","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Shanghai Rolex Masters: Arthur Fils vs Botic van de Zandschulp","market_name":"Shanghai Rolex Masters: Arthur Fils vs Botic van de Zandschulp","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245152774","label":"Botic van de Zandschulp","side":"away","market_ids":[65197794],"contributor_outcome_ids":[245152774],"published":{"value":0.74,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T12:24:01.645538+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197794,"outcome_id":245152774,"leg_side":"away","raw_probability":0.74,"observed_at":"2026-10-12T12:24:01.645538+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"comparable","reason":null,"baseline":{"probability":0.22,"observed_at":"2026-10-12T10:17:15.022760+00:00","basis":"pregame_pin"},"latest":{"probability":0.74,"observed_at":"2026-10-12T12:24:01.645538+00:00"},"delta_points":52.0}},{"option_key":"o:245152773","label":"Arthur Fils","side":"home","market_ids":[65197794],"contributor_outcome_ids":[245152773],"published":{"value":0.255,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T12:23:57.067532+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197794,"outcome_id":245152773,"leg_side":"home","raw_probability":0.255,"observed_at":"2026-10-12T12:23:57.067532+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"comparable","reason":null,"baseline":{"probability":0.785,"observed_at":"2026-10-12T10:17:15.022760+00:00","basis":"pregame_pin"},"latest":{"probability":0.255,"observed_at":"2026-10-12T12:23:57.067532+00:00"},"delta_points":-53.0}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":0.995,"legs":2}]},
{"question_key":"m:65197795","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Set 1 Winner: Arthur Fils vs Botic van de Zandschulp","market_name":"Set 1 Winner: Arthur Fils vs Botic van de Zandschulp","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"open","market_status":"open"},"options":[{"option_key":"o:245152776","label":"Botic van de Zandschulp","side":"away","market_ids":[65197795],"contributor_outcome_ids":[245152776],"published":{"value":0.999,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T11:59:24.344917+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197795,"outcome_id":245152776,"leg_side":"away","raw_probability":0.999,"observed_at":"2026-10-12T11:59:24.344917+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"comparable","reason":null,"baseline":{"probability":0.28,"observed_at":"2026-10-12T10:17:14.835808+00:00","basis":"pregame_pin"},"latest":{"probability":0.999,"observed_at":"2026-10-12T11:59:24.344917+00:00"},"delta_points":71.9}},{"option_key":"o:245152775","label":"Arthur Fils","side":"home","market_ids":[65197795],"contributor_outcome_ids":[245152775],"published":{"value":0.0005,"value_state":"quoted","basis":"published_source_display","source":"polymarket","observed_at":"2026-10-12T11:59:14.942512+00:00"},"source_evidence":[{"source":"polymarket","market_id":65197795,"outcome_id":245152775,"leg_side":"home","raw_probability":0.0005,"observed_at":"2026-10-12T11:59:14.942512+00:00"}],"result":{"state":"open","evidence_kind":"none"},"comparison":{"state":"comparable","reason":null,"baseline":{"probability":0.72,"observed_at":"2026-10-12T10:17:14.835808+00:00","basis":"pregame_pin"},"latest":{"probability":0.0005,"observed_at":"2026-10-12T11:59:14.942512+00:00"},"delta_points":-72.0}}],"missing_options":[],"option_counts":{"declared":null,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"polymarket","raw_sum":0.9995,"legs":2}]}
],"series_markets_count":null,"coverage":{"scope":"rows_served_by_this_response","questions":7,"options":12,"by_kind":{"count_threshold":0,"signed_handicap":0,"rank_predicate":0},"untyped":{"untyped_period":0,"untyped_unit":4,"untyped_subject":0,"untyped_predicate":0},"build_errors":0}},
"stream_market_ids":[65176056,65176060,65190255,65197794,65197795,65197796,65197797,65197798,65197799,65197800,65197801,65212323,65317203,65317205],
"outcome_market_ids":{},
"outcome_revision_at":{},
"outcome_observed_at":{},
"open_winner_quote":null,
"closed_winner_market_ids":[],
"cache":{"generation":3,"created_at":"2026-10-12T12:24:06.199179+00:00","quality":"full","availability":"live","lifecycle_watermark":"2026-10-12T11:05:41.741305+00:00","quality_reasons":[],"source_status":"live","build_id":"v5667"}}
"""##

    static let finalMarkets = ##"""
{"event_id":15327291,
"home_team":"Alejandro Davidovich Fokina",
"away_team":"Frances Tiafoe",
"home_score":2,
"away_score":1,
"score_source":"espn",
"score_observed_at":"2026-10-11T17:06:47.950466+00:00",
"status":"completed",
"totals":[
{"threshold":21.5,"over_probability":1.0,"source":"polymarket","market_type":"game_total","market_name":"Fokina vs. Tiafoe: Match O/U 21.5","outcome_name":"Over","observed_at":"2026-10-11T14:06:15.499070+00:00","contributor_outcome_ids":[244929349],"is_winner":true,"resolution_source":"clob_authoritative","movement":0.374,"period":null,"_market_id":65138607,"_external_id":"0x29771440856d87a051957685d8f4811366cbc4ebdf1a4356b9a36a4faa253110"},
{"threshold":22.5,"over_probability":1.0,"source":"polymarket","market_type":"game_total","market_name":"Fokina vs. Tiafoe: Match O/U 22.5","outcome_name":"Over","observed_at":"2026-10-11T14:54:06.778032+00:00","contributor_outcome_ids":[244876655],"is_winner":true,"resolution_source":"clob_authoritative","movement":0.4745,"period":null,"_market_id":65123147,"_external_id":"0xb2122c728db698a1ea1ec445f7bf855bb499fc5fe2bbb9d3fd852e8351260ec6"},
{"threshold":23.5,"over_probability":1.0,"source":"polymarket","market_type":"game_total","market_name":"Fokina vs. Tiafoe: Match O/U 23.5","outcome_name":"Over","observed_at":"2026-10-11T14:54:06.778032+00:00","contributor_outcome_ids":[244876657],"is_winner":true,"resolution_source":"clob_authoritative","movement":0.5445,"period":null,"_market_id":65123148,"_external_id":"0x083e0b7729c83e94070bdb7fd4676d3db2a21e7da52470276d8ba88e33342f1a"}
],
"player_props":[],
"team_totals":[],
"spreads":[
{"market_name":"Set Handicap: Frances Tiafoe (-1.5) vs Alejandro Davidovich Fokina (+1.5)","outcome_name":"Alejandro Davidovich Fokina","observed_at":"2026-10-11T14:06:15.499070+00:00","contributor_outcome_ids":[244876662],"threshold":null,"probability":0.9995,"source":"polymarket","is_winner":true,"resolution_source":"clob_authoritative","_market_id":65123150},
{"market_name":"Set Handicap: Alejandro Davidovich Fokina (-1.5) vs Frances Tiafoe (+1.5)","outcome_name":"Frances Tiafoe","observed_at":"2026-10-11T14:54:06.778032+00:00","contributor_outcome_ids":[244876660],"threshold":null,"probability":0.9995,"source":"polymarket","is_winner":true,"resolution_source":"clob_authoritative","_market_id":65123149},
{"market_name":"Game Spread: Frances Tiafoe (-0.5) vs Alejandro Davidovich Fokina (+0.5)","outcome_name":"Alejandro Davidovich Fokina","observed_at":"2026-10-11T16:20:15.999040+00:00","contributor_outcome_ids":[244973047],"threshold":null,"probability":0.9995,"source":"polymarket","is_winner":true,"resolution_source":"clob_authoritative","_market_id":65149801}
],
"period_markets":[],
"closed_period_markets":[],
"matchups":[],
"other":[
{"market_name":"Davidovich Fokina vs Tiafoe","outcome_name":"Alejandro Davidovich Fokina","observed_at":"2026-10-11T15:21:26.099516+00:00","contributor_outcome_ids":[244894423],"probability":1.0,"source":"kalshi","is_winner":true,"resolution_source":"api_settlement","_market_id":65129355},
{"market_name":"Davidovich Fokina vs Tiafoe","outcome_name":"Frances Tiafoe","observed_at":"2026-10-11T15:21:26.099516+00:00","contributor_outcome_ids":[244894424],"probability":null,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","_market_id":65129355},
{"market_name":"Shanghai Rolex Masters: Completed Match: Alejandro Davidovich Fokina vs Frances Tiafoe","outcome_name":"Yes","observed_at":"2026-10-11T14:54:06.778032+00:00","contributor_outcome_ids":[244873262],"probability":0.999,"source":"polymarket","is_winner":true,"resolution_source":"clob_authoritative","_market_id":65121632},
{"market_name":"Shanghai Rolex Masters: Completed Match: Alejandro Davidovich Fokina vs Frances Tiafoe","outcome_name":"No","observed_at":"2026-10-11T16:20:15.999040+00:00","contributor_outcome_ids":[244873263],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":65121632},
{"market_name":"Set 2 Winner: Alejandro Davidovich Fokina vs Frances Tiafoe","outcome_name":"Frances Tiafoe","observed_at":"2026-10-11T14:54:06.778032+00:00","contributor_outcome_ids":[244929344],"probability":0.9995,"source":"polymarket","is_winner":true,"resolution_source":"clob_authoritative","_market_id":65138604},
{"market_name":"Set 2 Winner: Alejandro Davidovich Fokina vs Frances Tiafoe","outcome_name":"Alejandro Davidovich Fokina","observed_at":"2026-10-11T16:20:15.999040+00:00","contributor_outcome_ids":[244929343],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":65138604},
{"market_name":"Set 1 Winner: Alejandro Davidovich Fokina vs Frances Tiafoe","outcome_name":"Alejandro Davidovich Fokina","observed_at":"2026-10-11T14:06:15.499070+00:00","contributor_outcome_ids":[244929341],"probability":0.9995,"source":"polymarket","is_winner":true,"resolution_source":"clob_authoritative","_market_id":65138603},
{"market_name":"Set 1 Winner: Alejandro Davidovich Fokina vs Frances Tiafoe","outcome_name":"Frances Tiafoe","observed_at":"2026-10-11T14:54:06.778032+00:00","contributor_outcome_ids":[244929342],"probability":null,"source":"polymarket","is_winner":false,"resolution_source":"api_settlement","_market_id":65138603},
{"market_name":"Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score","outcome_name":"Alejandro Davidovich Fokina wins 2-1","observed_at":"2026-10-11T15:21:26.099516+00:00","contributor_outcome_ids":[244894447],"probability":1.0,"source":"kalshi","is_winner":true,"resolution_source":"api_settlement","_market_id":65129363},
{"market_name":"Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score","outcome_name":"Frances Tiafoe wins 2-1","observed_at":"2026-10-11T15:21:26.099516+00:00","contributor_outcome_ids":[244894448],"probability":null,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","_market_id":65129363},
{"market_name":"Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score","outcome_name":"Frances Tiafoe wins 2-0","observed_at":"2026-10-11T15:21:26.099516+00:00","contributor_outcome_ids":[244894446],"probability":null,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","_market_id":65129363},
{"market_name":"Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score","outcome_name":"Alejandro Davidovich Fokina wins 2-0","observed_at":"2026-10-11T15:21:26.099516+00:00","contributor_outcome_ids":[244894445],"probability":null,"source":"kalshi","is_winner":false,"resolution_source":"api_settlement","_market_id":65129363}
],
"pace":null,
"props_script":[],
"during_player_props":null,
"after_player_props":null,
"game_question_matrix":{"contract":"10238.v1","display_scope":"game","questions":[
{"question_key":"m:65129355","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Davidovich Fokina vs Tiafoe","market_name":"Davidovich Fokina vs Tiafoe","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:244894423","label":"Alejandro Davidovich Fokina","side":"home","market_ids":[65129355],"contributor_outcome_ids":[244894423],"published":{"value":null,"value_state":"result","basis":"result","source":"kalshi","observed_at":"2026-10-11T15:21:26.099516+00:00"},"source_evidence":[{"source":"kalshi","market_id":65129355,"outcome_id":244894423,"leg_side":"home","raw_probability":1.0,"observed_at":"2026-10-11T15:21:26.099516+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:244894424","label":"Frances Tiafoe","side":"away","market_ids":[65129355],"contributor_outcome_ids":[244894424],"published":{"value":null,"value_state":"result","basis":"result","source":"kalshi","observed_at":"2026-10-11T15:21:26.099516+00:00"},"source_evidence":[{"source":"kalshi","market_id":65129355,"outcome_id":244894424,"leg_side":"away","raw_probability":0.0,"observed_at":"2026-10-11T15:21:26.099516+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":2,"loaded":2,"returned":2,"missing_identified":0},"complete":true,"source_totals":[{"source":"kalshi","raw_sum":1.0,"legs":2}]},
{"question_key":"m:65129363","proposition_key":null,"display_scope":"game","kind":"named_options","label":"Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score","market_name":"Alejandro Davidovich Fokina vs Frances Tiafoe: Exact Match Score","source_array":"other","quantity":null,"period":null,"subject":null,"predicate":null,"complement_question_key":null,"typing":{"state":"typed","reason":null},"lifecycle":{"state":"settled","market_status":"resolved"},"options":[{"option_key":"o:244894447","label":"Alejandro Davidovich Fokina wins 2-1","side":"category","market_ids":[65129363],"contributor_outcome_ids":[244894447],"published":{"value":null,"value_state":"result","basis":"result","source":"kalshi","observed_at":"2026-10-11T15:21:26.099516+00:00"},"source_evidence":[{"source":"kalshi","market_id":65129363,"outcome_id":244894447,"leg_side":"category","raw_probability":1.0,"observed_at":"2026-10-11T15:21:26.099516+00:00"}],"result":{"state":"won","evidence_kind":"settled_grade_fields"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:244894448","label":"Frances Tiafoe wins 2-1","side":"category","market_ids":[65129363],"contributor_outcome_ids":[244894448],"published":{"value":null,"value_state":"result","basis":"result","source":"kalshi","observed_at":"2026-10-11T15:21:26.099516+00:00"},"source_evidence":[{"source":"kalshi","market_id":65129363,"outcome_id":244894448,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-11T15:21:26.099516+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:244894446","label":"Frances Tiafoe wins 2-0","side":"category","market_ids":[65129363],"contributor_outcome_ids":[244894446],"published":{"value":null,"value_state":"result","basis":"result","source":"kalshi","observed_at":"2026-10-11T15:21:26.099516+00:00"},"source_evidence":[{"source":"kalshi","market_id":65129363,"outcome_id":244894446,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-11T15:21:26.099516+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}},{"option_key":"o:244894445","label":"Alejandro Davidovich Fokina wins 2-0","side":"category","market_ids":[65129363],"contributor_outcome_ids":[244894445],"published":{"value":null,"value_state":"result","basis":"result","source":"kalshi","observed_at":"2026-10-11T15:21:26.099516+00:00"},"source_evidence":[{"source":"kalshi","market_id":65129363,"outcome_id":244894445,"leg_side":"category","raw_probability":0.0,"observed_at":"2026-10-11T15:21:26.099516+00:00"}],"result":{"state":"lost","evidence_kind":"verdict_is_provable"},"comparison":{"state":"unavailable","reason":"not_quoted","baseline":null,"latest":null,"delta_points":null}}],"missing_options":[],"option_counts":{"declared":4,"loaded":4,"returned":4,"missing_identified":0},"complete":true,"source_totals":[{"source":"kalshi","raw_sum":1.0,"legs":4}]}
],"series_markets_count":null,"coverage":{"scope":"rows_served_by_this_response","questions":11,"options":18,"by_kind":{"count_threshold":0,"signed_handicap":0,"rank_predicate":0},"untyped":{"untyped_period":0,"untyped_unit":6,"untyped_subject":0,"untyped_predicate":0},"build_errors":0}},
"stream_market_ids":[65121630,65121631,65121632,65123146,65123147,65123148,65123149,65123150,65129355,65129363,65138603,65138604,65138606,65138607,65144791,65149801,65162173],
"outcome_market_ids":{},
"outcome_revision_at":{},
"outcome_observed_at":{},
"open_winner_quote":null,
"closed_winner_market_ids":[65121631,65121632,65123146,65123147,65123148,65123149,65123150,65129355,65129363,65138603,65138604,65138606,65138607,65144791,65149801,65162173],
"cache":{"generation":3,"created_at":"2026-10-11T17:07:14.154602+00:00","quality":"full","availability":"live","lifecycle_watermark":"2026-10-11T16:29:57.389792+00:00","quality_reasons":[],"source_status":"completed","build_id":"v5643"}}
"""##
}
