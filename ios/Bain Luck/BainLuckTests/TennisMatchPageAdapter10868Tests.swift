import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's adapter, part one (phase, the two
/// players' headline, the set score, the reader heading and the About), on
/// REAL served bodies decoded exactly as the app decodes them (`APIClient`:
/// `JSONDecoder` with `.convertFromSnakeCase`, no date strategy).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED bodies, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`,
/// embedded BYTE FOR BYTE (the first test re-hashes each):
///
/// - `liveDetail` — `accessible-chart-inspection-v90/raw/tennis-15327807-detail.json`
///   (5,538 bytes, sha256 74a02fc6b8eddf2ca23cb7844e21cf1bf85cf2816a47db5fd77e857443116f03).
///   ATP Shanghai, Arthur Fils (home) vs Botic van de Zandschulp (away), listed
///   2026-10-12T10:55Z, served `status: live`, sets 0–1 (score observed
///   12:20:44Z), no `prematch_odds`, `opening_odds` 0.7872 / 0.2128, hero
///   source `blend` observed 12:23:57Z with `current_odds` 0.205895 / 0.794105
///   (rendered 21 / 79), `espn` without period or clock. Its served `linescore`
///   (games per set) is not decoded by `EventDetail`.
/// - `finalDetail` — `accessible-chart-inspection-v90/raw/tennis-15327291-detail.json`
///   (4,759 bytes, sha256 04430cd0bd96e90dc02e8faa649e63f64ec49940b3bddfc6d3caccb6081dd374).
///   Alejandro Davidovich Fokina (home) vs Frances Tiafoe (away), `status:
///   completed`, sets 2–1, `hero_settled_result: home`, `prematch_odds` Kalshi
///   0.455 / 0.545 (rendered 45 / 55), hero source `settled` (1.0 / 0.0), a
///   last `current_odds` of 0.6762 / 0.3238.
/// - `usOpenDetail` — `atlas-v6/raw/tennis-15310688-detail.json` (5,879 bytes,
///   sha256 8d9d7e31bc9d751a057f419f0c55878cebd1150fee72ef5576997ed9ada5e4a4).
///   US Open, Alexander Zverev (home) vs Ben Shelton (away), `status:
///   completed`, sets 3–1, `hero_settled_result: home`, `prematch_odds` Kalshi
///   0.59 / 0.41, no `score_observed_at`.
///
/// CONSTRUCTED here, each named where used and changing only the key(s) it
/// names: the reader's calendar (Pacific, en_US) and `now`; interrupted
/// delivery; a before variant (`status: scheduled` and `commence_time` moved
/// after the capture); a suspended variant; final variants without the verdict
/// and score; a draw-priced sport key; an NHL sport key for `applies`. Clock
/// words are compared with the adapter's own clock words, and compact names
/// with `TeamShortName.shortPair`, never hard-coded.
@MainActor
final class TennisMatchPageAdapter10868Tests: XCTestCase {
    private typealias A = TennisMatchPageAdapter10868

    static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    static let locale = Locale(identifier: "en_US")
    /// 33 s after the live hero's own clock (12:23:57Z).
    static let liveReadAt = "2026-10-12T12:24:30Z"
    /// 36 minutes after it: older than `SourceAge.liveStaleAfter`.
    static let staleReadAt = "2026-10-12T13:00:00Z"
    /// The day after both finals' capture.
    static let finalReadAt = "2026-10-13T05:00:00Z"

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func detail(_ json: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    /// A served detail body with the named keys replaced: CONSTRUCTED.
    static func edited(_ json: String, _ setting: [String: Any]) throws -> EventDetail {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        for (key, value) in setting { object[key] = value }
        return try decoder().decode(EventDetail.self, from: try JSONSerialization.data(withJSONObject: object))
    }

    private func host(_ event: EventDetail, _ now: String, interrupted: Bool = false) -> A.Host {
        A.Host(probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, deliveryInterrupted: interrupted,
               now: now.asDate!, calendar: Self.pacific, locale: Self.locale)
    }

    private func figures(_ input: FieldHeadlineInput10868) -> [[String]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }
    }

    private func words(_ input: FieldHeadlineInput10868) -> [[String]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.compactMap(FieldChaseModel10868.words) }
    }

    private func compactNames(_ event: EventDetail) -> (away: String, home: String) {
        TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
    }

    // MARK: - Fixtures

    func testTheEmbeddedBodiesAreTheRetainedBytesAndDecode() throws {
        func sha256(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        XCTAssertEqual(sha256(Self.liveDetail), "74a02fc6b8eddf2ca23cb7844e21cf1bf85cf2816a47db5fd77e857443116f03")
        XCTAssertEqual(sha256(Self.finalDetail), "04430cd0bd96e90dc02e8faa649e63f64ec49940b3bddfc6d3caccb6081dd374")
        XCTAssertEqual(sha256(Self.usOpenDetail), "8d9d7e31bc9d751a057f419f0c55878cebd1150fee72ef5576997ed9ada5e4a4")

        let live = try Self.detail(Self.liveDetail)
        XCTAssertEqual(live.id, 15327807)
        XCTAssertEqual(live.sport, "tennis_atp_shanghai_masters")
        XCTAssertEqual(live.status, "live")
        XCTAssertNil(live.prematchOdds)
        XCTAssertEqual(live.heroProbabilitySource, "blend")
        XCTAssertEqual([live.homeScore, live.awayScore], [0, 1])
        let finished = try Self.detail(Self.finalDetail)
        XCTAssertEqual(finished.status, "completed")
        XCTAssertEqual(finished.heroSettledResult, "home")
        XCTAssertEqual(finished.prematchOdds?.source, "kalshi")
        let usOpen = try Self.detail(Self.usOpenDetail)
        XCTAssertEqual([usOpen.homeScore, usOpen.awayScore], [3, 1])
        XCTAssertNil(usOpen.scoreObservedAt)

        XCTAssertTrue(A.applies(live))
        XCTAssertTrue(A.applies(finished))
        XCTAssertFalse(A.applies(try Self.edited(Self.liveDetail, ["sport": "icehockey_nhl"])))
    }

    func testTennisIsTwoOutcomeByTheAppsOwnDrawRule() throws {
        let live = try Self.detail(Self.liveDetail)
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw(live.sport))
        XCTAssertEqual(SportVocab.forSport(live.sport).scoreboardUnit, "sets")
        XCTAssertEqual(A.players(live).map(\.name), ["Arthur Fils", "Botic van de Zandschulp"])
        XCTAssertEqual(A.players(live).map(\.shape), [.circle, .diamond])
    }

    // MARK: - During (the retained live state)

    func testTheRetainedLiveMatchLeadsWithTheOpeningLineBesideAnAdmittedCurrentChance() throws {
        let event = try Self.detail(Self.liveDetail)
        let reader = host(event, Self.liveReadAt)
        XCTAssertEqual(A.phase(event, now: reader.now), .during)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.displayed.map(\.name), ["Arthur Fils", "Botic van de Zandschulp"])
        XCTAssertEqual(input.displayed.map(\.keyShape), [.circle, .diamond])
        XCTAssertEqual(input.displayed.map(\.ref), [
            FieldChooserOriginalRef10868(scope: "tennis:15327807:winner", source: "event-hero",
                                         marketID: "15327807:winner", outcomeID: "home"),
            FieldChooserOriginalRef10868(scope: "tennis:15327807:winner", source: "event-hero",
                                         marketID: "15327807:winner", outcomeID: "away"),
        ], "opaque presentation identities, never a provider market or outcome id")

        // No `prematch_odds` is served, so the pre-match slot is the opening line, said so.
        XCTAssertEqual(figures(input), [["79%", "21%"], ["21%", "79%"]])
        let observed = try XCTUnwrap(event.heroProbabilityObservedAt?.asDate)
        XCTAssertEqual(input.catalogue[0].plan, .comparison(
            before: FieldChooserReading10868(label: "Opening win chance",
                                             value: .recorded(text: "79%", detail: "Sportsbooks’ opening line")),
            later: FieldChooserReading10868(label: "Current win chance", value: .recorded(
                text: "21%", detail: "Recorded \(A.clockWords(observed, host: reader)) · Bain Luck"))))
        XCTAssertEqual(input.pairs[0].before?.probability, 0.7872)
        XCTAssertEqual(input.pairs[0].later?.probability, 0.205895)
        XCTAssertEqual(input.pairs[1].later?.probability, 0.794105, "the served away price, never a complement")

        // The set score from the app's own fields, home first as the names are,
        // dated by its own capture clock only.
        let scoreClock = try XCTUnwrap(event.scoreObservedAt?.asDate)
        XCTAssertEqual(input.state?.figure, "0–1")
        XCTAssertEqual(input.state?.unit, "sets")
        XCTAssertEqual(input.state?.caption, "Live", "no ESPN period or clock is served")
        XCTAssertEqual(input.state?.detail, "Score recorded \(A.clockWords(scoreClock, host: reader))")
        XCTAssertEqual(input.copy.eyebrow, "ATP")
        XCTAssertEqual(input.copy.title, "Arthur Fils vs Botic van de Zandschulp")

        let names = compactNames(event)
        let header = A.readerHeader(event, host: reader)
        XCTAssertEqual(header.title, "\(names.home) · \(names.away)")
        XCTAssertEqual(header.state, "0–1 sets · Live")
    }

    func testAStaleOrInterruptedLiveQuoteIsNeverTheCurrentChance() throws {
        let event = try Self.detail(Self.liveDetail)
        let stale = A.headline(event, host: host(event, Self.staleReadAt))
        XCTAssertEqual(figures(stale), [["79%"], ["21%"]], "36 minutes old is not current")
        XCTAssertEqual(words(stale), [["Current win chance unavailable"], ["Current win chance unavailable"]])
        XCTAssertNil(stale.pairs[0].later)

        // CONSTRUCTED: interrupted delivery, read 33 s after the quote.
        let interruptedHost = host(event, Self.liveReadAt, interrupted: true)
        let interrupted = A.headline(event, host: interruptedHost)
        XCTAssertEqual(figures(interrupted), [["79%"], ["21%"]])
        XCTAssertEqual(A.notice(host: interruptedHost), "Update interrupted · showing the last recorded chances")
        XCTAssertNil(A.notice(host: host(event, Self.liveReadAt)))

        let names = compactNames(event)
        XCTAssertEqual(A.about(event, host: host(event, Self.staleReadAt)).sections[0].paragraphs, [
            "Opening win chance · \(names.home) 79% · \(names.away) 21%. Sportsbooks’ opening line.",
            "Current win chance unavailable. Recorded readings remain in the history.",
        ])
    }

    func testASuspendedMatchAfterItsStartUsesTheOneSuspendedTreatment() throws {
        // CONSTRUCTED: `status: suspended`.
        let event = try Self.edited(Self.liveDetail, ["status": "suspended"])
        let reader = host(event, Self.liveReadAt)
        XCTAssertEqual(A.phase(event, now: reader.now), .during, "suspended after its start is during, never final")
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.state?.figure, "0–1")
        XCTAssertEqual(input.state?.caption, EventState.suspendedLabel(authorityPeriod: nil))
        XCTAssertEqual(figures(input), [["79%"], ["21%"]], "a suspended match's quote is the last recorded one")
    }

    // MARK: - Before (constructed)

    func testBeforeTheStartTheHeroPairLeadsWithItsOwnClockAndSource() throws {
        // CONSTRUCTED: `status: scheduled` and `commence_time` after the capture.
        let event = try Self.edited(Self.liveDetail, ["status": "scheduled",
                                                      "commence_time": "2026-10-12T13:00:00+00:00"])
        let reader = host(event, Self.liveReadAt)
        XCTAssertEqual(A.phase(event, now: reader.now), .before)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .before)
        let observed = try XCTUnwrap(event.heroProbabilityObservedAt?.asDate)
        XCTAssertEqual(input.catalogue[0].plan, .single(FieldChooserReading10868(
            label: "Current win chance",
            value: .recorded(text: "21%", detail: "Recorded \(A.clockWords(observed, host: reader)) · Bain Luck"))))
        XCTAssertEqual(figures(input), [["21%"], ["79%"]])
        let start = try XCTUnwrap("2026-10-12T13:00:00Z".asDate)
        XCTAssertEqual(input.state?.figure, "Before the match")
        XCTAssertNil(input.state?.unit, "no set score before play")
        XCTAssertEqual(input.state?.caption, "Scheduled start")
        XCTAssertEqual(input.state?.detail, A.clockWords(start, host: reader))

        let names = compactNames(event)
        let header = A.readerHeader(event, host: reader)
        XCTAssertEqual(header.title, "\(names.home) · \(names.away)")
        XCTAssertEqual(header.state, "Current win chance · \(names.home) 21% · \(names.away) 79%")
        XCTAssertEqual(A.about(event, host: reader).sections.map(\.title), ["Chances", "Match result", "History and sources"])
    }

    // MARK: - Final (retained)

    func testTheRetainedFinalLeadsWithThePreMatchChanceBesideWonAndLost() throws {
        let event = try Self.detail(Self.finalDetail)
        let reader = host(event, Self.finalReadAt)
        XCTAssertEqual(A.phase(event, now: reader.now), .final)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(figures(input), [["45%", "Won"], ["55%", "Lost"]],
                       "the settled 100% and the last 68% are never a headline figure")
        XCTAssertEqual(input.catalogue[0].plan, .single(FieldChooserReading10868(
            label: "Pre-match win chance",
            value: .recorded(text: "45%", detail: "Last reading before the start · \(SourceLabels.label(for: "kalshi") ?? "")"))))
        XCTAssertEqual(input.finishes[0].reading, FieldChooserReading10868(
            label: "Match result", value: .recorded(text: "Won", detail: "Recorded on the event")))
        XCTAssertEqual(input.pairs[0].before?.probability, 0.455)
        XCTAssertNil(input.pairs[0].later)

        // The production final tennis headline decides the same values.
        let production = A.finalHeadline(event)
        XCTAssertEqual([production.home.chance, production.away.chance], ["45%", "55%"])
        XCTAssertEqual([production.home.won, production.away.won], [true, false])

        let start = try XCTUnwrap(event.commenceTime?.asDate)
        XCTAssertEqual(input.state?.figure, "2–1")
        XCTAssertEqual(input.state?.unit, "sets")
        XCTAssertEqual(input.state?.caption, "Final · Alejandro Davidovich Fokina won")
        XCTAssertEqual(input.state?.detail, A.dayWords(start, host: reader))

        let names = compactNames(event)
        let header = A.readerHeader(event, host: reader)
        XCTAssertEqual(header.title, "\(names.home) · \(names.away) · Final · 2–1 sets")
        XCTAssertEqual(header.state, "Pre-match win chance · \(names.home) 45% · \(names.away) 55%")

        let about = A.about(event, host: reader)
        XCTAssertEqual(about.title, "About this match")
        XCTAssertEqual(about.sections.map(\.title), ["Chances", "Score", "Match result", "History and sources"])
        let scoreClock = try XCTUnwrap(event.scoreObservedAt?.asDate)
        XCTAssertEqual(about.sections[1].paragraphs, [
            "2–1 sets · Score recorded \(A.clockWords(scoreClock, host: reader)).",
            "Games within each set unavailable.",
        ])
        XCTAssertEqual(about.sections[2].paragraphs, ["Alejandro Davidovich Fokina won, as recorded on the event."])
    }

    func testTheRetainedUSOpenFinalReadsTheSameWayWithoutAScoreClock() throws {
        let event = try Self.detail(Self.usOpenDetail)
        let reader = host(event, Self.finalReadAt)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(figures(input), [["59%", "Won"], ["41%", "Lost"]])
        XCTAssertEqual(input.state?.figure, "3–1")
        XCTAssertEqual(input.state?.caption, "Final · Alexander Zverev won")
        XCTAssertEqual(A.about(event, host: reader).sections[1].paragraphs,
                       ["3–1 sets.", "Games within each set unavailable."])
    }

    func testAFinalWithoutAVerdictOrScoreSaysTheResultIsUnavailable() throws {
        // CONSTRUCTED: `hero_settled_result`, `home_score` and `away_score` removed.
        let event = try Self.edited(Self.finalDetail, ["hero_settled_result": NSNull(),
                                                       "home_score": NSNull(), "away_score": NSNull()])
        let reader = host(event, Self.finalReadAt)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(figures(input), [["45%"], ["55%"]], "unknown is not a loss")
        XCTAssertEqual(words(input), [["Result unavailable"], ["Result unavailable"]])
        XCTAssertEqual(input.state?.figure, "Final")
        XCTAssertNil(input.state?.unit)
        XCTAssertEqual(input.state?.caption, "Result unavailable")
        let about = A.about(event, host: reader)
        XCTAssertEqual(about.sections[1].paragraphs, ["Set score unavailable.", "Games within each set unavailable."])
        XCTAssertEqual(about.sections[2].paragraphs, ["Result unavailable."])
    }

    // MARK: - Pair rule (constructed)

    func testADrawPricedSportKeepsTheHomeFigureAndWithholdsTheAwayOne() throws {
        // CONSTRUCTED: a draw-priced sport key; nothing else changes.
        let event = try Self.edited(Self.liveDetail, ["sport": "soccer_epl"])
        let input = A.headline(event, host: host(event, Self.liveReadAt))
        XCTAssertEqual(figures(input), [["79%", "21%"], []])
        XCTAssertEqual(words(input)[1], ["Win chance unavailable", "Win chance unavailable"])
    }

    // MARK: - About

    func testTheAboutSaysWhichChancesAreShownAndThatNoGamesFigureIsShown() throws {
        let event = try Self.detail(Self.liveDetail)
        let reader = host(event, Self.liveReadAt)
        let about = A.about(event, host: reader)
        XCTAssertEqual(about.sections.map(\.title), ["Chances", "Score", "Match result", "History and sources"])
        let names = compactNames(event)
        XCTAssertEqual(about.sections[0].paragraphs, [
            "Opening win chance · \(names.home) 79% · \(names.away) 21%. Sportsbooks’ opening line.",
        ], "an admitted current chance needs no absence line")
        let scoreClock = try XCTUnwrap(event.scoreObservedAt?.asDate)
        XCTAssertEqual(about.sections[1].paragraphs, [
            "0–1 sets · Score recorded \(A.clockWords(scoreClock, host: reader)).",
            "Games within each set unavailable.",
        ])
        XCTAssertEqual(about.sections[2].paragraphs, ["Result unavailable."])
        XCTAssertEqual(about.sections[3].paragraphs, [A.Words.historyWords])
    }

    // MARK: - Retained bodies (verbatim)

    static let liveDetail = ##"""
{"id":15327807,"external_id":"f11e01ff73395ec9eaee7743f8e46586","sport":"tennis_atp_shanghai_masters","sport_name":"ATP Shanghai Masters","home_team":"Arthur Fils","away_team":"Botic van de Zandschulp","commence_time":"2026-10-12T10:55:00+00:00","start_is_tbd":false,"completed_at":null,"status":"live","started_without_result":false,"home_score":0,"away_score":1,"score_source":"espn","score_observed_at":"2026-10-12T12:20:44.471140+00:00","linescore":{"sets":[[5,7],[3,3]],"source":"espn","away_games":10,"home_games":8,"observed_at":"2026-10-12T12:20:44.471140+00:00"},"home_image_url":"https://upload.wikimedia.org/wikipedia/commons/thumb/8/89/Fils_BOR22_%2852083970501%29.jpg/330px-Fils_BOR22_%2852083970501%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail","away_image_url":"https://upload.wikimedia.org/wikipedia/commons/thumb/1/10/Van_de_Zandschulp_MCM22_%2811%29_%2852036444288%29.jpg/330px-Van_de_Zandschulp_MCM22_%2811%29_%2852036444288%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail","home_flag_url":"https://a.espncdn.com/i/teamlogos/countries/500/fra.png","away_flag_url":"https://a.espncdn.com/i/teamlogos/countries/500/ned.png","metadata":{"gender":"men","level":"professional","league":"ATP","importance":"unknown"},"espn":{"espn_id":"184937","probability_sources":{"betting":0.1928,"polymarket":0.255,"betting_book_count":6.0,"kalshi":0.795}},"win_probability_sources":{"betting":{"value":0.1928,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-12T12:23:41.710307+00:00","evidence_status":"not_applicable"},"polymarket":{"value":0.255,"display_name":"Polymarket","type":"market","color":"#3b82f6","updated_at":"2026-10-12T12:23:57.169564+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031","price_evidence":"unproven"},"betting_book_count":{"value":6.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"},"kalshi":{"value":0.795,"display_name":"Kalshi","type":"market","color":"#22c55e","updated_at":"2026-10-12T05:05:29.894776+00:00","evidence_status":"verified","verified_scope":"full_event_winner","contract_version":"live_blend.admissible_as_blend_speaker@5031"}},"ei":{"score":96,"raw_score":81,"status":"incredible","label":"Incredible","emoji":"🔥","metadata":{"raw_ei":1.6417,"lead_changes":7,"comeback_factor":0.1542,"snapshot_count":176}},"pulse":{"score":96,"raw_score":81,"status":"incredible","label":"Incredible","emoji":"🔥","metadata":{"raw_ei":1.6417,"lead_changes":7,"comeback_factor":0.1542,"snapshot_count":176}},"event_tags":["class:other","ei:must_watch","gender:men","level:professional","sport:tennis","status:live","tier:4"],"current_odds":{"captured_at":"2026-10-12T12:23:41.702013+00:00","home_probability":0.205895,"away_probability":0.794105,"away_rendered_percent":79,"home_rendered_percent":21,"spread":3.5,"over_under":22.5,"projected_home_score":9.5,"projected_away_score":13.0,"bookmaker_count":6},"bookmaker_odds":[{"bookmaker":"betmgm","home_moneyline":340,"away_moneyline":-525,"home_probability":0.2129,"away_probability":0.7871,"captured_at":"2026-10-12T12:23:41.696053+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":351,"away_moneyline":-468,"home_probability":0.212,"away_probability":0.788,"captured_at":"2026-10-12T09:15:10.100922+00:00","spread":4.0,"over_under":21.5,"projected_home_score":8.8,"projected_away_score":12.8},{"bookmaker":"betrivers","home_moneyline":350,"away_moneyline":-530,"home_probability":0.209,"away_probability":0.791,"captured_at":"2026-10-12T12:23:19.621515+00:00","spread":3.5,"over_under":22.5,"projected_home_score":9.5,"projected_away_score":13.0},{"bookmaker":"bovada","home_moneyline":400,"away_moneyline":-550,"home_probability":0.1912,"away_probability":0.8088,"captured_at":"2026-10-12T12:22:24.136862+00:00","spread":3.5,"over_under":22.5,"projected_home_score":9.5,"projected_away_score":13.0},{"bookmaker":"draftkings","home_moneyline":400,"away_moneyline":-549,"home_probability":0.1912,"away_probability":0.8088,"captured_at":"2026-10-12T12:23:19.615527+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanatics","home_moneyline":400,"away_moneyline":-600,"home_probability":0.1892,"away_probability":0.8108,"captured_at":"2026-10-12T12:21:48.243747+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":390,"away_moneyline":-550,"home_probability":0.1943,"away_probability":0.8057,"captured_at":"2026-10-12T12:23:41.702013+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"lowvig","home_moneyline":351,"away_moneyline":-468,"home_probability":0.212,"away_probability":0.788,"captured_at":"2026-10-12T09:15:10.098460+00:00","spread":4.0,"over_under":21.5,"projected_home_score":8.8,"projected_away_score":12.8}],"opening_odds":{"home_probability":0.7872,"away_probability":0.2128,"spread":-4.0,"over_under":21.5,"favorite":"home"},"hero_probability_observed_at":"2026-10-12T12:23:57.169564+00:00","blend_fold_revision":{"15327807":3649,"15327767":1015},"hero_probability":0.205895,"hero_probability_away":0.794105,"hero_probability_source":"blend","hero_sportsbook_count":6,"box_score_data":{"players":null}}
"""##

    static let finalDetail = ##"""
{"id":15327291,"external_id":"bd69690bbcda67d0a8bcaa6f591baa47","sport":"tennis_atp_shanghai_masters","sport_name":"ATP Shanghai Masters","home_team":"Alejandro Davidovich Fokina","away_team":"Frances Tiafoe","commence_time":"2026-10-11T12:50:00+00:00","start_is_tbd":false,"completed_at":"2026-10-11T15:40:42.437702+00:00","status":"completed","started_without_result":false,"home_score":2,"away_score":1,"score_source":"espn","score_observed_at":"2026-10-11T17:06:47.950466+00:00","linescore":{"sets":[[7,6],[4,6],[7,6]],"source":"espn","away_games":18,"home_games":18},"home_image_url":null,"away_image_url":"https://upload.wikimedia.org/wikipedia/commons/thumb/a/a3/FrancesTiafo.jpg/330px-FrancesTiafo.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail","home_flag_url":null,"away_flag_url":"https://a.espncdn.com/i/teamlogos/countries/500/usa.png","metadata":{"gender":"men","level":"professional","league":"ATP","importance":"unknown"},"espn":{"espn_id":"184936","probability_sources":{"betting":0.6762,"betting_book_count":6.0}},"win_probability_sources":{"betting":{"value":0.6762,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-11T15:40:54.690559+00:00","evidence_status":"not_applicable"},"betting_book_count":{"value":6.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":98,"raw_score":91,"status":"incredible","label":"Incredible","emoji":"🔥","metadata":{"raw_ei":2.0657,"lead_changes":11,"comeback_factor":0.1803,"snapshot_count":340}},"pulse":{"score":98,"raw_score":91,"status":"incredible","label":"Incredible","emoji":"🔥","metadata":{"raw_ei":2.0657,"lead_changes":11,"comeback_factor":0.1803,"snapshot_count":340}},"event_tags":["class:other","ei:incredible","gender:men","level:professional","sport:tennis","status:completed","tier:4","timing:weekend"],"current_odds":{"captured_at":"2026-10-11T15:37:41.974854+00:00","home_probability":0.6762,"away_probability":0.3238,"away_rendered_percent":32,"home_rendered_percent":68,"spread":1.5,"over_under":22.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":8},"bookmaker_odds":[{"bookmaker":"betmgm","home_moneyline":-250,"away_moneyline":185,"home_probability":0.6706,"away_probability":0.3294,"captured_at":"2026-10-11T15:36:40.093638+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":102,"away_moneyline":-122,"home_probability":0.4739,"away_probability":0.5261,"captured_at":"2026-10-11T12:49:07.131163+00:00","spread":null,"over_under":22.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betrivers","home_moneyline":-265,"away_moneyline":195,"home_probability":0.6817,"away_probability":0.3183,"captured_at":"2026-10-11T15:37:07.721828+00:00","spread":1.5,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"bovada","home_moneyline":110,"away_moneyline":-130,"home_probability":0.4573,"away_probability":0.5427,"captured_at":"2026-10-11T15:30:04.891918+00:00","spread":1.5,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":-286,"away_moneyline":220,"home_probability":0.7034,"away_probability":0.2966,"captured_at":"2026-10-11T15:37:07.720295+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanatics","home_moneyline":-145,"away_moneyline":115,"home_probability":0.5599,"away_probability":0.4401,"captured_at":"2026-10-11T15:36:40.087192+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-300,"away_moneyline":230,"home_probability":0.7122,"away_probability":0.2878,"captured_at":"2026-10-11T15:37:41.974854+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"lowvig","home_moneyline":102,"away_moneyline":-122,"home_probability":0.4739,"away_probability":0.5261,"captured_at":"2026-10-11T12:49:07.135288+00:00","spread":null,"over_under":22.5,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.4885,"away_probability":0.5115,"spread":-0.5,"over_under":22.5,"favorite":"even"},"prematch_odds":{"home_probability":0.455,"away_probability":0.545,"home_rendered_percent":45,"away_rendered_percent":55,"source":"kalshi"},"hero_probability_observed_at":null,"blend_fold_revision":{"15327291":4807,"15327600":2309},"hero_probability":1.0,"hero_probability_away":0.0,"hero_probability_source":"settled","hero_settled_result":"home","box_score_data":{"players":null}}
"""##

    static let usOpenDetail = ##"""
{"id":15310688,"external_id":"f3cdf500b7ae26bf7f70f24ac0f74d50","sport":"tennis_atp_us_open","sport_name":"ATP US Open","home_team":"Alexander Zverev","away_team":"Ben Shelton","commence_time":"2026-09-13T18:13:40+00:00","start_is_tbd":false,"completed_at":"2026-09-13T21:53:36.535853+00:00","status":"completed","started_without_result":false,"home_score":3,"away_score":1,"linescore":{"sets":[[6,3],[7,6],[5,7],[6,2]],"source":"espn","away_games":18,"home_games":24},"home_image_url":"https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Alexander_Zverev.jpg/330px-Alexander_Zverev.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail","away_image_url":"https://upload.wikimedia.org/wikipedia/commons/thumb/1/1b/Ben_Shelton%2C_media_conference%2C_Swiss_Indoors_Basel_2025_%28cropped%29.jpg/330px-Ben_Shelton%2C_media_conference%2C_Swiss_Indoors_Basel_2025_%28cropped%29.jpg?utm_source=en.wikipedia.org&utm_campaign=api&utm_content=thumbnail","home_flag_url":"https://a.espncdn.com/i/teamlogos/countries/500/ger.png","away_flag_url":"https://a.espncdn.com/i/teamlogos/countries/500/usa.png","metadata":{"gender":"men","level":"professional","league":"ATP","importance":"unknown"},"espn":{"espn_id":"182677","probability_sources":{"betting":0.9689,"betting_book_count":6.0}},"win_probability_sources":{"betting":{"value":0.9689,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-09-13T21:53:40.796789+00:00","evidence_status":"not_applicable"},"betting_book_count":{"value":6.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":65,"raw_score":46,"status":"exciting","label":"Engaging","emoji":"⚡","metadata":{"raw_ei":0.5311,"lead_changes":0,"comeback_factor":0.5665,"snapshot_count":437}},"pulse":{"score":65,"raw_score":46,"status":"exciting","label":"Engaging","emoji":"⚡","metadata":{"raw_ei":0.5311,"lead_changes":0,"comeback_factor":0.5665,"snapshot_count":437}},"event_tags":["audience:national_interest","class:other","competitive_structure:head_to_head","ei:average","gender:men","level:professional","narrative:david_vs_goliath","sport:tennis","stakes:playoff_race","status:completed","tier:2","timing:weekend"],"current_odds":{"captured_at":"2026-09-13T21:51:16.130914+00:00","home_probability":0.9689,"away_probability":0.0311,"away_rendered_percent":3,"home_rendered_percent":97,"spread":-2.3,"over_under":42.9,"projected_home_score":22.6,"projected_away_score":20.4,"bookmaker_count":11},"bookmaker_odds":[{"bookmaker":"betmgm","home_moneyline":-10000,"away_moneyline":3300,"home_probability":0.9712,"away_probability":0.0288,"captured_at":"2026-09-13T21:47:11.498060+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":-143,"away_moneyline":127,"home_probability":0.5719,"away_probability":0.4281,"captured_at":"2026-09-13T18:16:50.674893+00:00","spread":-1.5,"over_under":42.5,"projected_home_score":22.0,"projected_away_score":20.5},{"bookmaker":"betrivers","home_moneyline":-162,"away_moneyline":135,"home_probability":0.5923,"away_probability":0.4077,"captured_at":"2026-09-13T18:00:25.664578+00:00","spread":-1.5,"over_under":43.5,"projected_home_score":22.5,"projected_away_score":21.0},{"bookmaker":"betus","home_moneyline":-155,"away_moneyline":125,"home_probability":0.5776,"away_probability":0.4224,"captured_at":"2026-09-13T18:17:50.805484+00:00","spread":null,"over_under":42.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"bovada","home_moneyline":-100000,"away_moneyline":2800,"home_probability":0.9666,"away_probability":0.0334,"captured_at":"2026-09-13T21:51:16.130914+00:00","spread":-4.5,"over_under":43.5,"projected_home_score":24.0,"projected_away_score":19.5},{"bookmaker":"draftkings","home_moneyline":-50000,"away_moneyline":8100,"home_probability":0.9879,"away_probability":0.0121,"captured_at":"2026-09-13T21:51:16.119863+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanatics","home_moneyline":-5000,"away_moneyline":1400,"home_probability":0.9363,"away_probability":0.0637,"captured_at":"2026-09-13T21:45:20.401904+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-50000,"away_moneyline":10000,"home_probability":0.9902,"away_probability":0.0098,"captured_at":"2026-09-13T21:47:39.886682+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"lowvig","home_moneyline":-143,"away_moneyline":127,"home_probability":0.5719,"away_probability":0.4281,"captured_at":"2026-09-13T18:16:50.677851+00:00","spread":-1.5,"over_under":42.5,"projected_home_score":22.0,"projected_away_score":20.5},{"bookmaker":"mybookieag","home_moneyline":-333,"away_moneyline":225,"home_probability":0.7142,"away_probability":0.2858,"captured_at":"2026-09-13T21:11:36.384264+00:00","spread":-2.5,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"williamhill_us","home_moneyline":-7500,"away_moneyline":1200,"home_probability":0.9277,"away_probability":0.0723,"captured_at":"2026-09-13T21:45:40.307200+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.5758,"away_probability":0.4242,"spread":-1.5,"over_under":42.5,"favorite":"home"},"prematch_odds":{"home_probability":0.59,"away_probability":0.41,"home_rendered_percent":59,"away_rendered_percent":41,"source":"kalshi"},"hero_probability_observed_at":null,"blend_fold_revision":{"15310688":0},"hero_probability":1.0,"hero_probability_away":0.0,"hero_probability_source":"settled","hero_settled_result":"home","box_score_data":{"players":null}}
"""##
}
