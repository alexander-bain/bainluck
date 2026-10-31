import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen's adapter, part one (phase, the two
/// fighters' headline, the reader heading and the About), on REAL served
/// bodies decoded exactly as the app decodes them (`APIClient`: `JSONDecoder`
/// with `.convertFromSnakeCase`, no date strategy).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// RETAINED bodies, under `artifacts/discovery-containers-release-plan/event-page-design-20261011/`,
/// embedded BYTE FOR BYTE (the first test re-hashes each):
///
/// - `mmaDetail` — `atlas-v6/raw/mma-15318681-detail.json` (4,063 bytes, sha256
///   4ffc852aab725878d908716dbc3d67b535960c10875ee17380278aa290604aa1). UFC 332,
///   Ateba Gautier (home) vs Roman Kopylov (away), listed 2026-10-04T00:20Z,
///   served `status: suspended`, no score, no `prematch_odds`, hero source
///   `blend` observed 00:42:55Z, `venue_settled: false`.
/// - `boxingDetail` — `atlas-v6/raw/boxing-15318202-detail.json` (3,512 bytes,
///   sha256 506a74dbecc9192f7e4fba5d7eb1db28685f0345e944cceac7bbf3d9b36be516).
///   Ryusei Matsumoto (home) vs Russell Acosta (away), listed
///   2026-09-27T08:00Z, `status: suspended`, hero source `opening`, no hero clock.
/// - `boxingMarkets` — `atlas-v6/raw/boxing-15318202-game-markets.json` (632
///   bytes, sha256 c5cdc324d9edf66803e88453f03d9dd62f1e46a100379176eefc6ab7764c26ad):
///   every array empty.
///
/// Both retained bouts read DURING by the app's own rule (suspended after the
/// start), so the real phase here is during. CONSTRUCTED here, each named where
/// used and changing only the key(s) it names: the reader's calendar (Pacific,
/// en_US) and `now`; a before variant (`commence_time` moved to 01:00Z, read at
/// 00:43Z); a live variant (`status: live`); final variants (`status:
/// completed`, then also `hero_settled_result: away`); a draw-priced sport key;
/// an ESPN stoppage period; an NHL sport key for `applies`. Clock words are
/// compared with the adapter's own clock words, never hard-coded.
@MainActor
final class CombatBoutPageAdapter10868Tests: XCTestCase {
    private typealias A = CombatBoutPageAdapter10868

    static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()
    static let locale = Locale(identifier: "en_US")
    /// A week after the bout, around the bodies' capture.
    static let readAt = "2026-10-11T05:00:00Z"

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

    // MARK: - Fixtures

    func testTheEmbeddedBodiesAreTheRetainedBytesAndDecode() throws {
        func sha256(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        XCTAssertEqual(sha256(Self.mmaDetail), "4ffc852aab725878d908716dbc3d67b535960c10875ee17380278aa290604aa1")
        XCTAssertEqual(sha256(Self.boxingDetail), "506a74dbecc9192f7e4fba5d7eb1db28685f0345e944cceac7bbf3d9b36be516")
        XCTAssertEqual(sha256(Self.boxingMarkets), "c5cdc324d9edf66803e88453f03d9dd62f1e46a100379176eefc6ab7764c26ad")

        let mma = try Self.detail(Self.mmaDetail)
        XCTAssertEqual(mma.id, 15318681)
        XCTAssertEqual(mma.sport, "mma_mixed_martial_arts")
        XCTAssertEqual(mma.status, "suspended")
        XCTAssertNil(mma.prematchOdds)
        XCTAssertEqual(mma.heroProbabilitySource, "blend")
        let boxing = try Self.detail(Self.boxingDetail)
        XCTAssertEqual(boxing.sport, "boxing_boxing")
        XCTAssertEqual(boxing.heroProbabilitySource, "opening")
        XCTAssertNil(boxing.heroProbabilityObservedAt)
        let markets = try Self.decoder().decode(GameMarketsResponse.self, from: Data(Self.boxingMarkets.utf8))
        XCTAssertEqual(markets.other?.count, 0)
        XCTAssertTrue(A.applies(mma))
        XCTAssertTrue(A.applies(boxing))
        XCTAssertFalse(A.applies(try Self.edited(Self.mmaDetail, ["sport": "icehockey_nhl"])))
    }

    // MARK: - During (the retained state)

    func testTheRetainedUFCBoutReadsDuringWithTheOpeningLineAndNoInFightChance() throws {
        let event = try Self.detail(Self.mmaDetail)
        let reader = host(event, Self.readAt)
        XCTAssertEqual(A.phase(event, now: reader.now), .during, "suspended after its start is during, never final")
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.displayed.map(\.name), ["Ateba Gautier", "Roman Kopylov"])
        XCTAssertEqual(input.displayed.map(\.keyShape), [.circle, .diamond])
        XCTAssertEqual(input.displayed.map(\.ref), [
            FieldChooserOriginalRef10868(scope: "combat:15318681:winner", source: "event-hero",
                                         marketID: "15318681:winner", outcomeID: "home"),
            FieldChooserOriginalRef10868(scope: "combat:15318681:winner", source: "event-hero",
                                         marketID: "15318681:winner", outcomeID: "away"),
        ], "opaque presentation identities, never a provider market or outcome id")

        // No `prematch_odds` is served, so the pre-fight slot is the opening line, said so.
        XCTAssertEqual(figures(input), [["68%"], ["32%"]])
        XCTAssertEqual(words(input), [["No in-fight chance"], ["No in-fight chance"]])
        XCTAssertEqual(input.catalogue[0].plan, .comparison(
            before: FieldChooserReading10868(label: "Opening line", value: .recorded(text: "68%", detail: "Sportsbooks’ opening line")),
            later: FieldChooserReading10868(label: "In-fight chance", value: .missing("No in-fight chance"))))
        XCTAssertEqual(input.pairs[0].before?.probability, 0.6786)
        XCTAssertNil(input.pairs[0].later, "the suspended bout's 57% is never an in-fight chance")

        // The hero pair exists; it is the last recorded one, and it stays out of the headline.
        let hero = try XCTUnwrap(A.heroPair(event, host: reader))
        XCTAssertEqual(hero.label, "Last recorded chance")
        XCTAssertFalse(hero.isCurrent)
        XCTAssertEqual([hero.home.text, hero.away?.text], ["57%", "43%"])

        XCTAssertEqual(input.state?.figure, EventState.suspendedLabel(authorityPeriod: nil))
        XCTAssertNil(input.state?.progress, "no owner serves a round count")
        XCTAssertEqual(input.copy.eyebrow, "UFC")
        XCTAssertEqual(input.copy.title, "Ateba Gautier vs Roman Kopylov")
    }

    func testTheRetainedBoxingBoutUsesTheSameComponentsWithItsOwnOpeningLine() throws {
        let event = try Self.detail(Self.boxingDetail)
        let reader = host(event, Self.readAt)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .during)
        XCTAssertEqual(input.displayed.map(\.name), ["Ryusei Matsumoto", "Russell Acosta"])
        XCTAssertEqual(figures(input), [["85%"], ["15%"]])
        XCTAssertEqual(words(input), [["No in-fight chance"], ["No in-fight chance"]])
        let hero = try XCTUnwrap(A.heroPair(event, host: reader))
        XCTAssertEqual(hero.label, OpeningLineHero.caption, "an opening-line hero is never current")
        XCTAssertFalse(hero.isCurrent)
        XCTAssertEqual(input.copy.eyebrow, "Boxing")
        XCTAssertEqual(input.state?.figure, EventState.suspendedLabel(authorityPeriod: nil))
    }

    func testAnAuthorityStoppageNamesItselfThroughTheSuspendedTreatment() throws {
        // CONSTRUCTED: `espn` carries a stoppage period.
        let event = try Self.edited(Self.mmaDetail, ["espn": ["period": "Canceled"]])
        XCTAssertEqual(A.headline(event, host: host(event, Self.readAt)).state?.figure, "Canceled")
    }

    // MARK: - Live (constructed)

    func testALiveFightAdmitsOnlyAFreshUninterruptedPairAsTheInFightChance() throws {
        // CONSTRUCTED: `status: live`, read 5 s after the hero's own clock.
        let event = try Self.edited(Self.mmaDetail, ["status": "live"])
        let fresh = host(event, "2026-10-04T00:43:00Z")
        let input = A.headline(event, host: fresh)
        XCTAssertEqual(figures(input), [["68%", "57%"], ["32%", "43%"]])
        let observed = try XCTUnwrap(event.heroProbabilityObservedAt?.asDate)
        XCTAssertEqual(input.pairs[0].later?.reading, FieldChooserReading10868(
            label: "In-fight chance",
            value: .recorded(text: "57%", detail: "Recorded \(A.clockWords(observed, host: fresh)) · Bain Luck")))
        XCTAssertEqual(input.state?.figure, "Live", "no ESPN period or clock is served")

        let interrupted = A.headline(event, host: host(event, "2026-10-04T00:43:00Z", interrupted: true))
        XCTAssertEqual(figures(interrupted), [["68%"], ["32%"]])
        XCTAssertEqual(words(interrupted), [["No in-fight chance"], ["No in-fight chance"]])

        let stale = A.headline(event, host: host(event, "2026-10-04T01:30:00Z"))
        XCTAssertEqual(figures(stale), [["68%"], ["32%"]], "47 minutes old is not current")
    }

    // MARK: - Before (constructed)

    func testBeforeTheStartTheHeroPairLeadsWithItsOwnClockAndSource() throws {
        // CONSTRUCTED: `commence_time` moved after the capture, read at 00:43Z.
        let event = try Self.edited(Self.mmaDetail, ["commence_time": "2026-10-04T01:00:00+00:00"])
        let reader = host(event, "2026-10-04T00:43:00Z")
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .before)
        let observed = try XCTUnwrap(event.heroProbabilityObservedAt?.asDate)
        XCTAssertEqual(input.catalogue[0].plan, .single(FieldChooserReading10868(
            label: "Current chance",
            value: .recorded(text: "57%", detail: "Recorded \(A.clockWords(observed, host: reader)) · Bain Luck"))))
        XCTAssertEqual(figures(input), [["57%"], ["43%"]])
        let start = try XCTUnwrap("2026-10-04T01:00:00Z".asDate)
        XCTAssertEqual(input.state?.figure, "Before the fight")
        XCTAssertEqual(input.state?.caption, "Scheduled start")
        XCTAssertEqual(input.state?.detail, A.clockWords(start, host: reader))

        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let header = A.readerHeader(event, host: reader)
        XCTAssertEqual(header.title, "Ateba Gautier vs Roman Kopylov")
        XCTAssertEqual(header.state, "Current chance · \(names.home) 57% · \(names.away) 43%")
    }

    // MARK: - Final (constructed)

    func testAFinalWithoutAServedVerdictKeepsThePreFightReadingAndSaysTheResultIsUnavailable() throws {
        // CONSTRUCTED: `status: completed`. No score and no `hero_settled_result`.
        let event = try Self.edited(Self.mmaDetail, ["status": "completed"])
        let reader = host(event, Self.readAt)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(input.phase, .final)
        XCTAssertEqual(figures(input), [["68%"], ["32%"]], "a settled contract or 0/100 is never a headline figure")
        XCTAssertEqual(words(input), [["Result unavailable"], ["Result unavailable"]])
        XCTAssertEqual(input.state?.figure, "Final")
        XCTAssertEqual(input.state?.caption, "Result unavailable")
        XCTAssertEqual(A.readerHeader(event, host: reader).title, "Final · Ateba Gautier vs Roman Kopylov")
        XCTAssertEqual(A.about(event, host: reader).sections[1].paragraphs, ["Result unavailable."])
    }

    func testAFinalWithTheServedVerdictNamesWonAndLostAndNoFinishDetail() throws {
        // CONSTRUCTED: `status: completed` and `hero_settled_result: away`.
        let event = try Self.edited(Self.mmaDetail, ["status": "completed", "hero_settled_result": "away"])
        let reader = host(event, Self.readAt)
        let input = A.headline(event, host: reader)
        XCTAssertEqual(figures(input), [["68%", "Lost"], ["32%", "Won"]])
        XCTAssertEqual(input.finishes[1].reading, FieldChooserReading10868(
            label: "Official result", value: .recorded(text: "Won", detail: "Recorded on the event")))
        XCTAssertEqual(input.state?.caption, "Roman Kopylov won")
        XCTAssertEqual(A.readerHeader(event, host: reader).title, "Roman Kopylov won")
        XCTAssertEqual(A.about(event, host: reader).sections[1].paragraphs,
                       ["Roman Kopylov won, as recorded on the event.", "Finish details unavailable."],
                       "no method, round or finish time is on any production field")
    }

    // MARK: - Pair rule (constructed)

    func testADrawPricedSportKeepsTheHomeFigureAndWithholdsTheAwayOne() throws {
        // CONSTRUCTED: a draw-priced sport key; nothing else changes.
        let event = try Self.edited(Self.mmaDetail, ["sport": "soccer_epl"])
        let input = A.headline(event, host: host(event, Self.readAt))
        XCTAssertEqual(figures(input), [["68%"], []])
        XCTAssertEqual(words(input)[1], ["Win chance unavailable", "No in-fight chance"])
    }

    // MARK: - About and notice

    func testTheAboutSaysWhichChancesAreShownAndThatNoInFightChanceIsShown() throws {
        let event = try Self.detail(Self.mmaDetail)
        let reader = host(event, Self.readAt)
        let about = A.about(event, host: reader)
        XCTAssertEqual(about.title, "About this fight")
        XCTAssertEqual(about.sections.map(\.title), ["Chances", "Official result", "History and sources"])
        let names = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        XCTAssertEqual(about.sections[0].paragraphs, [
            "Opening line · \(names.home) 68% · \(names.away) 32%. Sportsbooks’ opening line.",
            "In-fight chance unavailable. Recorded readings remain in the history.",
        ])
        XCTAssertEqual(about.sections[1].paragraphs, ["Result unavailable."])
        XCTAssertTrue(about.sections.allSatisfy { $0.source == nil }, "no source link is served")
        XCTAssertNil(A.notice(host: reader))
        XCTAssertEqual(A.notice(host: host(event, Self.readAt, interrupted: true)),
                       "Update interrupted · showing the last recorded chances")
    }

    /// CONSTRUCTED: `opening_odds: null` (the body serves no `prematch_odds`),
    /// during the bout and then also `status: completed`. The event fields carry
    /// no absence reason, so the About says unavailable, never "not recorded".
    func testAnOmittedPreFightReadingIsUnavailableNeverNotRecorded() throws {
        for setting in [["opening_odds": NSNull()] as [String: Any],
                        ["opening_odds": NSNull(), "status": "completed"]] {
            let event = try Self.edited(Self.mmaDetail, setting)
            XCTAssertNil(A.prematchPair(event))
            let chances = A.about(event, host: host(event, Self.readAt)).sections[0].paragraphs
            XCTAssertEqual(chances.first, "Pre-match chance unavailable.", "\(setting)")
            XCTAssertFalse(chances.contains { $0.contains("not recorded") }, "\(setting)")
        }
    }

    // MARK: - Retained bodies (verbatim)

    static let mmaDetail = ##"""
{"id":15318681,"external_id":"e831957ecc850d7e3b1b0748f33b2db5","sport":"mma_mixed_martial_arts","sport_name":"MMA","home_team":"Ateba Gautier","away_team":"Roman Kopylov","commence_time":"2026-10-04T00:20:00+00:00","start_is_tbd":false,"completed_at":null,"status":"suspended","started_without_result":false,"home_score":null,"away_score":null,"home_image_url":null,"away_image_url":null,"home_flag_url":null,"away_flag_url":null,"metadata":{"gender":"men","level":"professional","league":"UFC","importance":"regular_season"},"espn":{"probability_sources":{"betting":0.5713,"betting_book_count":3.0}},"win_probability_sources":{"betting":{"value":0.5713,"display_name":"Betting Odds","type":"market","color":"#374151","updated_at":"2026-10-04T00:42:55.271003+00:00","evidence_status":"not_applicable"},"betting_book_count":{"value":3.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":32,"raw_score":15,"status":"quiet","label":"Quiet","emoji":"😴","metadata":{"raw_ei":0.0531,"lead_changes":0,"comeback_factor":0.5713,"snapshot_count":41}},"pulse":{"score":32,"raw_score":15,"status":"quiet","label":"Quiet","emoji":"😴","metadata":{"raw_ei":0.0531,"lead_changes":0,"comeback_factor":0.5713,"snapshot_count":41}},"event_tags":["audience:local_interest","class:pro_major","competitive_structure:head_to_head","ei:flat","gender:men","importance:regular_season","league:ufc","level:professional","sport:mma","stakes:playoff_race","tier:2","timing:primetime","timing:weekend"],"current_odds":{"captured_at":"2026-10-04T00:37:03.672381+00:00","home_probability":0.5713,"away_probability":0.4287,"away_rendered_percent":43,"home_rendered_percent":57,"spread":-3.5,"over_under":2.0,"projected_home_score":3.0,"projected_away_score":-0.5,"bookmaker_count":7},"bookmaker_odds":[{"bookmaker":"betmgm","home_moneyline":-165,"away_moneyline":125,"home_probability":0.5835,"away_probability":0.4165,"captured_at":"2026-10-04T00:28:18.312863+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betonlineag","home_moneyline":-236,"away_moneyline":198,"home_probability":0.6767,"away_probability":0.3233,"captured_at":"2026-10-04T00:37:03.666184+00:00","spread":null,"over_under":1.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betrivers","home_moneyline":-165,"away_moneyline":114,"home_probability":0.5713,"away_probability":0.4287,"captured_at":"2026-10-04T00:29:02.888086+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"bovada","home_moneyline":-242,"away_moneyline":205,"home_probability":0.6834,"away_probability":0.3166,"captured_at":"2026-10-04T00:37:03.672381+00:00","spread":-3.5,"over_under":2.5,"projected_home_score":3.0,"projected_away_score":-0.5},{"bookmaker":"draftkings","home_moneyline":-115,"away_moneyline":-115,"home_probability":0.5,"away_probability":0.5,"captured_at":"2026-10-04T00:29:02.895159+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-230,"away_moneyline":190,"home_probability":0.669,"away_probability":0.331,"captured_at":"2026-10-03T23:59:56.808927+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"williamhill_us","home_moneyline":-350,"away_moneyline":250,"home_probability":0.7313,"away_probability":0.2687,"captured_at":"2026-10-04T00:26:53.212426+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.6786,"away_probability":0.3214,"spread":-3.5,"over_under":2.5,"favorite":"home"},"hero_probability_observed_at":"2026-10-04T00:42:55.271003+00:00","blend_fold_revision":{"15318681":1760,"15318406":0,"15315711":1480},"hero_probability":0.5713,"hero_probability_away":0.4287,"hero_probability_source":"blend","hero_sportsbook_count":3,"venue_settled":false,"venue_settled_result":null}
"""##

    static let boxingDetail = ##"""
{"id":15318202,"external_id":"ed83de9dec2bc6e71c94c62c7d85d5ab","sport":"boxing_boxing","sport_name":"Boxing","home_team":"Ryusei Matsumoto","away_team":"Russell Acosta","commence_time":"2026-09-27T08:00:00+00:00","start_is_tbd":false,"completed_at":null,"status":"suspended","started_without_result":false,"home_score":null,"away_score":null,"home_image_url":null,"away_image_url":null,"home_flag_url":null,"away_flag_url":null,"metadata":{"gender":"men","level":"professional","league":"Boxing","importance":"regular_season"},"espn":{"probability_sources":{"betting_book_count":1.0}},"win_probability_sources":{"betting_book_count":{"value":1.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":48,"raw_score":30,"status":"competitive","label":"Average","emoji":"📊","metadata":{"raw_ei":0.2193,"lead_changes":0,"comeback_factor":0.738,"snapshot_count":136}},"pulse":{"score":48,"raw_score":30,"status":"competitive","label":"Average","emoji":"📊","metadata":{"raw_ei":0.2193,"lead_changes":0,"comeback_factor":0.738,"snapshot_count":136}},"event_tags":["audience:local_interest","class:pro_major","competitive_structure:head_to_head","ei:quiet","gender:men","importance:regular_season","league:boxing","level:professional","sport:boxing","tier:3","timing:weekend"],"current_odds":{"captured_at":"2026-09-27T09:10:40.296437+00:00","home_probability":0.854,"away_probability":0.146,"away_rendered_percent":15,"home_rendered_percent":85,"spread":null,"over_under":10.5,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":5},"bookmaker_odds":[{"bookmaker":"betonlineag","home_moneyline":-950,"away_moneyline":550,"home_probability":0.8547,"away_probability":0.1453,"captured_at":"2026-09-27T07:44:05.306598+00:00","spread":null,"over_under":10.5,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"betus","home_moneyline":-850,"away_moneyline":525,"home_probability":0.8483,"away_probability":0.1517,"captured_at":"2026-09-26T13:57:25.449874+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"bovada","home_moneyline":-700,"away_moneyline":425,"home_probability":0.8212,"away_probability":0.1788,"captured_at":"2026-09-24T05:35:58.121137+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":-20000,"away_moneyline":1400,"home_probability":0.9372,"away_probability":0.0628,"captured_at":"2026-09-27T09:10:40.296437+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-750,"away_moneyline":430,"home_probability":0.8238,"away_probability":0.1762,"captured_at":"2026-09-24T05:35:58.111881+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"lowvig","home_moneyline":-950,"away_moneyline":550,"home_probability":0.8547,"away_probability":0.1453,"captured_at":"2026-09-27T07:44:05.308772+00:00","spread":null,"over_under":10.5,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.854,"away_probability":0.146,"spread":null,"over_under":null,"favorite":"home"},"hero_probability_observed_at":null,"blend_fold_revision":{"15318202":0},"hero_probability":0.854,"hero_probability_away":0.146,"hero_probability_source":"opening","venue_settled":false,"venue_settled_result":null}
"""##

    static let boxingMarkets = ##"""
{"event_id":15318202,"home_team":"Ryusei Matsumoto","away_team":"Russell Acosta","home_score":null,"away_score":null,"status":"suspended","totals":[],"player_props":[],"team_totals":[],"spreads":[],"period_markets":[],"matchups":[],"other":[],"pace":null,"props_script":[],"stream_market_ids":[],"outcome_market_ids":{},"outcome_revision_at":{},"outcome_observed_at":{},"open_winner_quote":null,"closed_winner_market_ids":[],"cache":{"generation":3,"created_at":"2026-10-11T05:12:31.958258+00:00","quality":"full","availability":"live","lifecycle_watermark":null,"quality_reasons":[],"source_status":"suspended","build_id":"v5643"}}
"""##
}
