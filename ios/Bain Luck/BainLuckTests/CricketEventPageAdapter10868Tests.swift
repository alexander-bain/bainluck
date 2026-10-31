import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the cricket Test-match adapter, part one (phase, title, reader
/// heading, the three-original headline and the match About), on REAL served
/// bodies decoded exactly as the app decodes them (`APIClient`: `JSONDecoder`
/// with `.convertFromSnakeCase`, no date strategy).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// NO TEST-MATCH BODY IS RETAINED. Every retained Bain Luck cricket event body is
/// limited-overs (International T20), and the backend notes that the
/// `cricket_test_match` league page holds only blank cards today (events.py,
/// beside `not_a_blank_card`). So the rules are proved on the NEAREST REAL
/// BODIES, labelled as such, under
/// `artifacts/discovery-containers-release-plan/event-page-design-20261011/`:
///
/// - `pakistanSriLanka` — `remaining-sport-evidence-v88/raw/cricket-15327397-detail.json`,
///   BYTE FOR BYTE (sha256 0727a2537814a0212494ea7e8cee521e5c6c1e4e57f94c58df842c851ef8184f;
///   the first test re-hashes it). `GET /api/events/15327397` captured
///   2026-10-12T13:26:17.507911Z: Pakistan v Sri Lanka, International T20,
///   `status: suspended` a day after its listed start, no score, the hero on its
///   opening arm, no `prematch_odds`.
/// - `indiaWestIndies` — the same directory's `cricket-15327398-detail.json`, BYTE
///   FOR BYTE (sha256 792b99ef45d8816322fe018d30cfbd3ea4c2a37e2873ffb0bd9de732db15b4dc),
///   captured 2026-10-12T13:26:17.508313Z: India v West Indies, the same state.
///
/// This screen is the Test-match screen (`CricketEventPageHost10868.applies` is
/// false for these bodies); its rules are applied to them only to prove what each
/// slot says on real served values.
///
/// CONSTRUCTED here, one key each, named where used: `sport` set to
/// `cricket_test_match`; `status` set to `live`, `completed` or `scheduled`. Also
/// constructed: the reader's calendar (Pacific, en_US), `now`, and the host's
/// displayed probability clock (the served `current_odds.captured_at` or another
/// served clock of the same body, passed as a host value). Clock words are
/// compared with the adapter's own clock words, never with hard-coded strings.
@MainActor
final class CricketEventPageAdapter10868Tests: XCTestCase {
    private typealias A = CricketEventPageAdapter10868

    static let pacific: Calendar = {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "America/Los_Angeles")!
        return calendar
    }()

    /// The retained bodies' capture instant.
    static let capturedAt = "2026-10-12T13:26:17.507911+00:00"

    static func host(_ now: String, observedAt: String? = nil) -> CricketEventPageAdapter10868.Host {
        CricketEventPageAdapter10868.Host(probabilityObservedAt: observedAt?.asDate, now: now.asDate!,
                                          calendar: pacific, locale: Locale(identifier: "en_US"))
    }

    static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }

    static func detail(_ json: String) throws -> EventDetail {
        try decoder().decode(EventDetail.self, from: Data(json.utf8))
    }

    /// A served body with ONE key replaced: CONSTRUCTED.
    static func detail(_ json: String, setting key: String, to value: Any) throws -> EventDetail {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(json.utf8)) as? [String: Any])
        object[key] = value
        return try decoder().decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: object))
    }

    private func observed(_ value: Double, _ text: String, _ detail: String) -> CricketOutlookReading10868 {
        .observed(CricketOutlookObservation10868(probability: value, text: text, detail: detail))
    }

    // MARK: - Fixtures

    func testTheEmbeddedBodiesAreTheRetainedBytesAndDecode() throws {
        func sha256(_ text: String) -> String {
            SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
        }
        XCTAssertEqual(sha256(Self.pakistanSriLanka), "0727a2537814a0212494ea7e8cee521e5c6c1e4e57f94c58df842c851ef8184f")
        XCTAssertEqual(sha256(Self.indiaWestIndies), "792b99ef45d8816322fe018d30cfbd3ea4c2a37e2873ffb0bd9de732db15b4dc")

        let event = try Self.detail(Self.pakistanSriLanka)
        XCTAssertEqual(event.id, 15327397)
        XCTAssertEqual(event.sport, "cricket_international_t20")
        XCTAssertEqual(event.status, "suspended")
        XCTAssertNil(event.homeScore, "no cricket score reaches the app")
        XCTAssertNil(event.awayScore)
        XCTAssertEqual(event.heroProbabilitySource, "opening")
        XCTAssertNil(event.heroProbabilityObservedAt)
        XCTAssertEqual(event.currentOdds?.homeProbability, 0.6668)
        XCTAssertEqual(event.currentOdds?.awayProbability, 0.3332)
        XCTAssertEqual(event.openingOdds?.awayProbability, 0.3332)
        XCTAssertNil(event.prematchOdds)
        XCTAssertNil(event.espn?.period, "no cricket match state is served")
        XCTAssertFalse(CricketEventPageHost10868.applies(event), "a limited-overs match is the cricket-t20 route's screen")
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw(event.sport), "the app declares no cricket key draw-priced")
        XCTAssertFalse(DrawPricedWinner.sportPricesADraw("cricket_test_match"),
                       "not even a Test match — so the Test screen's away slot needs producer evidence, not a sport key")
    }

    // MARK: - During play, a stoppage after the start (the retained bodies)

    func testDuringAStoppageTheOpeningLineIsThePregameAndNeverAnInPlayChance() throws {
        let event = try Self.detail(Self.pakistanSriLanka)
        let host = Self.host(Self.capturedAt)
        XCTAssertEqual(A.phase(event, now: host.now), .during, "suspended after its listed start is during play")

        let noResult = EventState.suspendedLabel(authorityPeriod: nil)
        XCTAssertEqual(A.title(event, host: host), CricketEventPageTitle10868(eyebrow: noResult, title: "Pakistan · Sri Lanka"))
        XCTAssertEqual(A.readerHeader(event, host: host),
                       CricketEventPageReaderHeader10868(title: "Pakistan · Sri Lanka", state: "\(noResult) · Score unavailable"))

        let latest = try XCTUnwrap(A.currentPair(event, host: host))
        XCTAssertTrue(latest.isOpeningLine, "the hero's opening arm: a pre-start quote")
        XCTAssertEqual(latest.title, OpeningLineHero.caption)
        XCTAssertNil(latest.currentness)

        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.phase, .during)
        XCTAssertNil(headline.caption)
        XCTAssertEqual(headline.beforeLabel, "Pregame")
        XCTAssertEqual(headline.comparisonLabel, "Current", "no figure is shown, so nothing is called last recorded")
        XCTAssertEqual(headline.state, CricketHeadlineState10868.unavailable("Score unavailable"))
        XCTAssertEqual(headline.rows.map(\.subject), ["Pakistan", "Sri Lanka", "Draw / tie"])
        XCTAssertEqual(headline.rows.map(\.id), ["cricket:15327397:home", "cricket:15327397:away", "cricket:15327397:draw"])
        XCTAssertEqual(headline.rows.map(\.shape), [.circle, .diamond, .square])
        XCTAssertTrue(headline.rows.allSatisfy { $0.ref == nil && $0.movement == nil && $0.finish == nil })

        let home = headline.rows[0], away = headline.rows[1], draw = headline.rows[2]
        // `PrematchReading`'s opening fallback, its own word, no clock.
        XCTAssertEqual(home.before, observed(0.6668, "67%", "Opened"))
        XCTAssertEqual(home.comparison, .unavailable("In-play chance unavailable"))
        // 0.3332 is the remainder after 0.6668: on a screen that lists a draw it
        // would carry the draw, so it is that slot's words, never a figure.
        XCTAssertTrue(isComplementPair([0.3332, 0.6668]))
        XCTAssertEqual(away.before, .unavailable("Win chance unavailable"))
        XCTAssertEqual(away.comparison, .unavailable("In-play chance unavailable"))
        XCTAssertEqual(draw.before, .unavailable("Draw chance unavailable"))
        XCTAssertEqual(draw.comparison, .unavailable("Draw chance unavailable"))
    }

    func testTheSecondRetainedMatchReadsTheSameWay() throws {
        let event = try Self.detail(Self.indiaWestIndies)
        let host = Self.host("2026-10-12T13:26:17.508313+00:00")
        XCTAssertEqual(A.phase(event, now: host.now), .during)
        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.rows.map(\.subject), ["India", "West Indies", "Draw / tie"])
        XCTAssertEqual(headline.rows[0].before, observed(0.7455, "75%", "Opened"))
        XCTAssertEqual(headline.rows[1].before, .unavailable("Win chance unavailable"))
        XCTAssertEqual(headline.rows[0].comparison, .unavailable("In-play chance unavailable"))
        XCTAssertEqual(A.readerHeader(event, host: host).title, "India · West Indies")
    }

    /// CONSTRUCTED: `sport` set to `cricket_test_match`, one key. It changes which
    /// screen applies, and nothing any slot says.
    func testATestMatchKeyChangesOnlyWhichScreenApplies() throws {
        let real = try Self.detail(Self.pakistanSriLanka)
        let test = try Self.detail(Self.pakistanSriLanka, setting: "sport", to: "cricket_test_match")
        let host = Self.host(Self.capturedAt)
        XCTAssertTrue(CricketEventPageHost10868.applies(test))
        XCTAssertEqual(A.headline(test, host: host), A.headline(real, host: host))
        let about = A.about(test, host: host)
        XCTAssertEqual(about.title, "How this match is shown")
        XCTAssertEqual(about.paragraphs.count, 3)
        XCTAssertTrue(about.paragraphs[1].contains("and so is Sri Lanka's: no source shows it is that side's own chance"))
    }

    // MARK: - The away side's own reading

    /// CONSTRUCTED: the retained Pakistan v Sri Lanka body with `sport` set to
    /// `cricket_test_match` and the named channel objects' values replaced; the
    /// edited channel's rendered percents are cleared so no served integer disagrees.
    private func testMatch(current: (home: Double, away: Double)? = nil, opening: (home: Double, away: Double)? = nil,
                           prematch: (home: Double, away: Double)? = nil) throws -> EventDetail {
        var object = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(Self.pakistanSriLanka.utf8)) as? [String: Any])
        object["sport"] = "cricket_test_match"
        if let current, var odds = object["current_odds"] as? [String: Any] {
            odds["home_probability"] = current.home
            odds["away_probability"] = current.away
            odds["home_rendered_percent"] = NSNull()
            odds["away_rendered_percent"] = NSNull()
            object["current_odds"] = odds
        }
        if let opening, var odds = object["opening_odds"] as? [String: Any] {
            odds["home_probability"] = opening.home
            odds["away_probability"] = opening.away
            object["opening_odds"] = odds
        }
        if let prematch {
            // A served pre-match channel naming no source.
            object["prematch_odds"] = ["home_probability": prematch.home, "away_probability": prematch.away,
                                       "source": NSNull()] as [String: Any]
        }
        return try Self.decoder().decode(EventDetail.self, from: JSONSerialization.data(withJSONObject: object))
    }

    func testTheAwaySlotIsUnavailableOnEveryChannelWithoutProducerEvidence() throws {
        let host = Self.host("2026-10-12T13:28:47Z", observedAt: "2026-10-11T15:52:33.190244+00:00")
        let unavailable = CricketOutlookReading10868.unavailable("Win chance unavailable")
        // A non-complement pair (the reference's own 48 / 47) and an invalid one (0.7 + 0.6): a sum test
        // passes both, and neither is producer evidence that the away figure is the away side's own price.
        for pair in [(home: 0.48, away: 0.47), (home: 0.7, away: 0.6)] {
            let current = try testMatch(current: pair)
            XCTAssertEqual(A.currentPair(current, host: host)?.away, unavailable, "current \(pair)")
            let opening = try testMatch(opening: pair)
            XCTAssertEqual(A.pregameReadings(opening).away, unavailable, "opening \(pair)")
            let prematch = try testMatch(prematch: pair)
            XCTAssertEqual(A.pregameReadings(prematch).away, unavailable, "unnamed pre-match channel \(pair)")
        }
        // The retained complement pair: unavailable too.
        let retained = try Self.detail(Self.pakistanSriLanka, setting: "sport", to: "cricket_test_match")
        XCTAssertEqual(A.currentPair(retained, host: host)?.away, unavailable)
        // The home side keeps its own reading.
        if case .observed = A.currentPair(retained, host: host)?.home {} else {
            XCTFail("the home reading stays")
        }
    }

    // MARK: - During live play (constructed status)

    /// CONSTRUCTED: `status` set to `live`, one key; the host's displayed clock is
    /// the served `current_odds.captured_at`, read 2½ minutes later.
    func testDuringLivePlayARecentPairIsTheHomeSidesCurrentChance() throws {
        let event = try Self.detail(Self.pakistanSriLanka, setting: "status", to: "live")
        let observedAt = "2026-10-11T15:52:33.190244+00:00"
        let host = Self.host("2026-10-11T15:55:00+00:00", observedAt: observedAt)
        XCTAssertEqual(A.phase(event, now: host.now), .during)
        XCTAssertEqual(A.title(event, host: host).eyebrow, "Live")

        let headline = A.headline(event, host: host)
        let recorded = "Recorded \(HockeyJourneyPageAdapter10868.clockWords(observedAt.asDate!, host: host.clock))"
        XCTAssertEqual(headline.comparisonLabel, "Current")
        XCTAssertEqual(headline.rows[0].before, observed(0.6668, "67%", "Opened"))
        XCTAssertEqual(headline.rows[0].comparison, observed(0.6668, "67%", recorded),
                       "the hero's own pair and served whole percent")
        XCTAssertEqual(headline.rows[1].comparison, .unavailable("Win chance unavailable"))
        XCTAssertEqual(headline.rows[2].comparison, .unavailable("Draw chance unavailable"))
    }

    /// CONSTRUCTED: `status` set to `live`; the same clock read more than 30
    /// minutes later (`SourceAge.liveStaleAfter`).
    func testAStaleLivePairIsLabelledLastRecorded() throws {
        let event = try Self.detail(Self.pakistanSriLanka, setting: "status", to: "live")
        let observedAt = "2026-10-11T15:52:33.190244+00:00"
        let host = Self.host("2026-10-11T17:00:00+00:00", observedAt: observedAt)
        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.comparisonLabel, "Last recorded")
        XCTAssertEqual(headline.rows[0].comparison.observation?.text, "67%")
    }

    /// CONSTRUCTED: `status` set to `live`; the host's clock is a served clock from
    /// BEFORE the listed 13:00 start (betonlineag's 12:42:47 capture), read at 13:05.
    func testAPairObservedBeforeTheListedStartIsNeverTheInPlayChance() throws {
        let event = try Self.detail(Self.pakistanSriLanka, setting: "status", to: "live")
        let host = Self.host("2026-10-11T13:05:00+00:00", observedAt: "2026-10-11T12:42:47.196772+00:00")
        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.rows[0].comparison, .withheld("In-play chance unavailable"))
        XCTAssertEqual(headline.rows[1].comparison, .withheld("In-play chance unavailable"))
        XCTAssertEqual(headline.comparisonLabel, "Current")
    }

    // MARK: - The final (constructed status)

    /// CONSTRUCTED: `status` set to `completed`, one key. The body serves no
    /// verdict, so no result is known — and unknown is not loss.
    func testAtTheFinalWithNoVerdictEveryResultIsUnavailableNeverALoss() throws {
        let event = try Self.detail(Self.pakistanSriLanka, setting: "status", to: "completed")
        let host = Self.host(Self.capturedAt)
        XCTAssertEqual(A.phase(event, now: host.now), .completed)
        XCTAssertEqual(A.title(event, host: host).eyebrow, "Final")
        XCTAssertEqual(A.readerHeader(event, host: host),
                       CricketEventPageReaderHeader10868(title: "Pakistan · Sri Lanka", state: "Final · Score unavailable"))
        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.phase, .completed)
        XCTAssertEqual(headline.outcomeLabel, "Match")
        XCTAssertEqual(headline.outcomeMissing, "Result unavailable")
        XCTAssertEqual(headline.rows[0].before, observed(0.6668, "67%", "Opened"))
        for row in headline.rows {
            XCTAssertEqual(row.finish, CricketOutlookFinish10868(outcome: .unavailable("Result unavailable"), grade: nil))
            XCTAssertEqual(headline.outcome(row), CricketOutlookFinalEntry10868.unavailable("Result unavailable"))
        }
        let about = A.about(event, host: host)
        XCTAssertEqual(about.paragraphs.count, 4)
        XCTAssertTrue(about.paragraphs[3].contains("0% or 100% is a result, not a chance"))
    }

    func testTheReportedResultWordsAreTheReferencesAndUnknownIsNotLoss() {
        XCTAssertEqual(A.outcomeWords(.home, original: .home), "Winner")
        XCTAssertEqual(A.outcomeWords(.home, original: .away), "Lost")
        XCTAssertEqual(A.outcomeWords(.home, original: .draw), "No draw / tie")
        XCTAssertEqual(A.outcomeWords(.away, original: .away), "Winner")
        XCTAssertEqual(A.outcomeWords(.away, original: .home), "Lost")
        XCTAssertEqual(A.outcomeWords(.away, original: .draw), "No draw / tie")
        for original in A.Original.allCases {
            XCTAssertEqual(A.outcomeWords(.draw, original: original), "Draw", "a draw is a result, and nobody lost")
            XCTAssertNil(A.outcomeWords(.undecided, original: original))
        }
        XCTAssertEqual(A.finish(.away, original: .away), CricketOutlookFinish10868(
            outcome: .admitted(CricketOutlookFinalWord10868(text: "Winner", symbolName: nil, detail: "Final result")),
            grade: nil))
        XCTAssertEqual(A.finish(.undecided, original: .home),
                       CricketOutlookFinish10868(outcome: .unavailable("Result unavailable"), grade: nil))
    }

    // MARK: - Before play (constructed status)

    /// CONSTRUCTED: `status` set to `scheduled`, one key, read before the listed
    /// 13:00 start with no displayed clock.
    func testBeforePlayTheOneSlotIsTheLatestPreMatchReadingCaptionedByWhatItIs() throws {
        let event = try Self.detail(Self.pakistanSriLanka, setting: "status", to: "scheduled")
        let host = Self.host("2026-10-11T12:00:00+00:00")
        XCTAssertEqual(A.phase(event, now: host.now), .before)
        let start = try XCTUnwrap(event.commenceTime?.asDate)
        let day = HockeyJourneyPageAdapter10868.dayWords(start, host: host.clock)
        let time = HockeyJourneyPageAdapter10868.timeWords(start, host: host.clock)
        XCTAssertEqual(A.title(event, host: host).eyebrow, "Before play · \(day), \(time) start")
        XCTAssertEqual(A.readerHeader(event, host: host).state, "Before play · \(day), \(time) start")

        let headline = A.headline(event, host: host)
        XCTAssertEqual(headline.phase, .before)
        XCTAssertEqual(headline.caption, OpeningLineHero.caption, "the hero's opening arm, named as such")
        XCTAssertNil(headline.state)
        XCTAssertEqual(headline.rows[0].before, observed(0.6668, "67%", OpeningLineHero.caption))
        XCTAssertEqual(headline.rows[1].before, .unavailable("Win chance unavailable"))
        XCTAssertEqual(headline.rows[2].before, .unavailable("Draw chance unavailable"))
        XCTAssertEqual(headline.slots, [.pregame], "before play only the pregame slot is shown")
    }

    // MARK: Retained payloads (byte for byte)

    /// `remaining-sport-evidence-v88/raw/cricket-15327397-detail.json` · sha256 0727a2537814a0212494ea7e8cee521e5c6c1e4e57f94c58df842c851ef8184f
    static let pakistanSriLanka = ##"""
{"id":15327397,"external_id":"1212aa43d192423c6c1cda27800c8342","sport":"cricket_international_t20","sport_name":"International Twenty20","home_team":"Pakistan","away_team":"Sri Lanka","commence_time":"2026-10-11T13:00:00+00:00","start_is_tbd":false,"completed_at":null,"status":"suspended","started_without_result":false,"home_score":null,"away_score":null,"metadata":{"gender":"unknown","level":"unknown","league":"Other","importance":"unknown"},"espn":{"probability_sources":{"betting_book_count":1.0}},"win_probability_sources":{"betting_book_count":{"value":1.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":45,"raw_score":39,"status":"competitive","label":"Average","emoji":"📊","metadata":{"raw_ei":0.3778,"lead_changes":0,"comeback_factor":0.6386,"snapshot_count":378}},"pulse":{"score":45,"raw_score":39,"status":"competitive","label":"Average","emoji":"📊","metadata":{"raw_ei":0.3778,"lead_changes":0,"comeback_factor":0.6386,"snapshot_count":378}},"event_tags":["audience:local_interest","class:international","competitive_structure:head_to_head","ei:quiet","league:international_t20","sport:cricket","tier:3","timing:weekend"],"current_odds":{"captured_at":"2026-10-11T15:52:33.190244+00:00","home_probability":0.6668,"away_probability":0.3332,"away_rendered_percent":33,"home_rendered_percent":67,"spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":3},"bookmaker_odds":[{"bookmaker":"betonlineag","home_moneyline":-225,"away_moneyline":189,"home_probability":0.6668,"away_probability":0.3332,"captured_at":"2026-10-11T12:42:47.196772+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":-4000,"away_moneyline":1200,"home_probability":0.9269,"away_probability":0.0731,"captured_at":"2026-10-11T15:37:34.401628+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-20000,"away_moneyline":3000,"home_probability":0.9686,"away_probability":0.0314,"captured_at":"2026-10-11T15:52:33.190244+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.6668,"away_probability":0.3332,"spread":null,"over_under":null,"favorite":"home"},"hero_probability_observed_at":null,"blend_fold_revision":{"15327397":43},"hero_probability":0.6668,"hero_probability_away":0.3332,"hero_probability_source":"opening","venue_settled":false,"venue_settled_result":null}
"""##

    /// `remaining-sport-evidence-v88/raw/cricket-15327398-detail.json` · sha256 792b99ef45d8816322fe018d30cfbd3ea4c2a37e2873ffb0bd9de732db15b4dc
    static let indiaWestIndies = ##"""
{"id":15327398,"external_id":"35d3bfa7ed91441f9c3a617d9a61b31e","sport":"cricket_international_t20","sport_name":"International Twenty20","home_team":"India","away_team":"West Indies","commence_time":"2026-10-11T13:25:00+00:00","start_is_tbd":false,"completed_at":null,"status":"suspended","started_without_result":false,"home_score":null,"away_score":null,"metadata":{"gender":"mixed","level":"unknown","league":"International","importance":"unknown"},"espn":{"probability_sources":{"betting_book_count":2.0}},"win_probability_sources":{"betting_book_count":{"value":2.0,"display_name":"betting_book_count","type":"model","color":"#6b7280","evidence_status":"not_applicable"}},"ei":{"score":75,"raw_score":54,"status":"exciting","label":"Exciting","emoji":"⚡","metadata":{"raw_ei":0.7275,"lead_changes":0,"comeback_factor":0.5721,"snapshot_count":348}},"pulse":{"score":75,"raw_score":54,"status":"exciting","label":"Exciting","emoji":"⚡","metadata":{"raw_ei":0.7275,"lead_changes":0,"comeback_factor":0.5721,"snapshot_count":348}},"event_tags":["audience:national_interest","class:international","competitive_structure:head_to_head","ei:competitive","gender:mixed","league:international_t20","sport:cricket","tier:3","timing:weekend"],"current_odds":{"captured_at":"2026-10-11T16:38:21.284645+00:00","home_probability":0.7455,"away_probability":0.2545,"away_rendered_percent":25,"home_rendered_percent":75,"spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null,"bookmaker_count":3},"bookmaker_odds":[{"bookmaker":"betonlineag","home_moneyline":-350,"away_moneyline":280,"home_probability":0.7472,"away_probability":0.2528,"captured_at":"2026-10-11T13:03:46.817214+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"draftkings","home_moneyline":-1100,"away_moneyline":600,"home_probability":0.8652,"away_probability":0.1348,"captured_at":"2026-10-11T16:38:21.282580+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null},{"bookmaker":"fanduel","home_moneyline":-1150,"away_moneyline":550,"home_probability":0.8567,"away_probability":0.1433,"captured_at":"2026-10-11T16:38:21.284645+00:00","spread":null,"over_under":null,"projected_home_score":null,"projected_away_score":null}],"opening_odds":{"home_probability":0.7455,"away_probability":0.2545,"spread":null,"over_under":null,"favorite":"home"},"hero_probability_observed_at":null,"blend_fold_revision":{"15327398":77},"hero_probability":0.7455,"hero_probability_away":0.2545,"hero_probability_source":"opening","venue_settled":false,"venue_settled_result":null}
"""##
}
