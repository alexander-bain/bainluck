import XCTest
@testable import Bain_Luck

/// #9208 — a called-off game says "Canceled" / "Postponed" on the phone, not
/// "No result reported".
///
/// Production 2026-10-02: Orioles @ Yankees (15319530, Sep 27) is `suspended`.
/// `/api/events/search` and `/api/events/15319530` serve `espn.period =
/// "Canceled"`; `/api/teams/new-york-yankees-mlb` serves `stoppage: "Canceled"`
/// and no `espn` block. Web search and the team page said Canceled (ux #10052);
/// every phone surface said "No result reported", because
/// `EventState.suspendedLabel` was a constant nothing could override.
///
/// The allowlist is pinned to web's `authorityStoppageLabel` table by
/// `frontend/__tests__/ios/eventStatusSingleSource.test.ts`; the badge, card and
/// share-card wiring is pinned there too (CI compiles no Swift).
final class SuspendedStoppageWord9208Tests: XCTestCase {

    private static let now = Date(timeIntervalSince1970: 1_790_000_000)

    private static func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    // MARK: - The allowlist

    func testTheThreeAuthorityWordsMapToTheWebLabels() {
        XCTAssertEqual(EventState.authorityStoppageLabel("Canceled"), "Canceled")
        XCTAssertEqual(EventState.authorityStoppageLabel("Cancelled"), "Canceled")
        XCTAssertEqual(EventState.authorityStoppageLabel("Postponed"), "Postponed")
        XCTAssertEqual(EventState.authorityStoppageLabel("  POSTPONED \n"), "Postponed")
    }

    func testALivePeriodLeftOnADarkRowIsNeverAStoppage() {
        // An exact allowlist, not a substring test: these are what a suspended
        // row's period holds when its source went dark mid-game.
        for period in ["End 9th", "Bottom 7th", "5:11 - 1st Quarter", "Halftime",
                       "Delayed", "Rain Delay", "Postponed game 2", "", nil] as [String?] {
            XCTAssertNil(EventState.authorityStoppageLabel(period), "\(period ?? "nil")")
            XCTAssertEqual(EventState.suspendedLabel(authorityPeriod: period),
                           EventState.suspendedLabel)
        }
    }

    func testTheTeamBriefsServerLabelRoundTrips() {
        // The team door's `stoppage` has already been through the server's run
        // of this allowlist; feeding the label back must return it unchanged.
        for label in EventState.authorityStoppageWords.values {
            XCTAssertEqual(EventState.authorityStoppageLabel(label), label)
        }
    }

    // MARK: - The summary lines

    func testTheSummaryOpensWithTheStoppageWord() {
        XCTAssertEqual(
            EventState.suspendedSummary(away: nil, home: nil, authorityPeriod: "Canceled"),
            "Canceled")
        XCTAssertEqual(
            EventState.suspendedSummary(away: nil, home: nil, authorityPeriod: nil),
            "No result reported")
    }

    func testAZeroZeroUnderAStoppageWordIsFillerNotALastScore() {
        // #8960 on web: ESPN publishes 0-0 for both sides of a postponed fixture.
        XCTAssertEqual(
            EventState.suspendedSummary(away: 0, home: 0, authorityPeriod: "Postponed"),
            "Postponed")
        XCTAssertNil(EventState.suspendedCardDetail(
            away: 0, home: 0, date: nil, authorityPeriod: "Postponed"))
        XCTAssertEqual(EventState.suspendedCardDetail(
            away: 0, home: 0, date: "Sep 27", authorityPeriod: "Canceled"), "Sep 27")
    }

    func testARealScoreUnderAStoppageWordStillPrints() {
        // Stopped mid-game: the pair is real.
        XCTAssertEqual(
            EventState.suspendedSummary(away: 2, home: 0, authorityPeriod: "Postponed"),
            "Postponed · last score 2-0")
        XCTAssertEqual(EventState.suspendedCardDetail(
            away: 2, home: 0, date: "Sep 27", authorityPeriod: "Postponed"),
            "last score 2-0 · Sep 27")
    }

    func testWithoutAStoppageWordAZeroZeroIsUnchanged() {
        // The control: the #8960 drop is conditioned on the stoppage word.
        XCTAssertEqual(
            EventState.suspendedSummary(away: 0, home: 0, authorityPeriod: "End 9th"),
            "No result reported · last score 0-0")
        XCTAssertEqual(EventState.suspendedCardDetail(
            away: 0, home: 0, date: "Sep 27", authorityPeriod: nil),
            "last score 0-0 · Sep 27")
    }

    // MARK: - Both doors carry the word to the row

    func testTheSearchRowReadsEspnPeriod() throws {
        // `/api/events/search` 15319530, trimmed.
        let row = try Self.decoder().decode(SearchEvent.self, from: Data("""
        {"id":15319530,"home_team":"New York Yankees","away_team":"Baltimore Orioles",
         "commence_time":"2026-09-27T17:05:00+00:00","status":"suspended",
         "espn":{"espn_id":"401817103","period":"Canceled","broadcast":"MLB.TV, MASN, YES"},
         "stoppage":null}
        """.utf8))
        XCTAssertEqual(row.authorityPeriod, "Canceled")
        XCTAssertEqual(EventState.suspendedLabel(authorityPeriod: row.authorityPeriod), "Canceled")
    }

    func testTheTeamRowReadsTheBriefsStoppage() throws {
        // `/api/teams/new-york-yankees-mlb` recent_events[] 15319530, trimmed:
        // no `espn` block on this door.
        let row = try Self.decoder().decode(SearchEvent.self, from: Data("""
        {"id":15319530,"home_team":"New York Yankees","away_team":"Baltimore Orioles",
         "commence_time":"2026-09-27T17:05:00+00:00","status":"suspended",
         "home_score":null,"away_score":null,"is_home":true,
         "opponent":"Baltimore Orioles","stoppage":"Canceled"}
        """.utf8))
        XCTAssertEqual(row.authorityPeriod, "Canceled")
        XCTAssertEqual(EventState.suspendedLabel(authorityPeriod: row.authorityPeriod), "Canceled")
    }

    func testARowWithNeitherKeepsTheOldLabel() throws {
        let row = try Self.decoder().decode(SearchEvent.self, from: Data("""
        {"id":1,"home_team":"A","away_team":"B","status":"suspended"}
        """.utf8))
        XCTAssertNil(row.authorityPeriod)
        XCTAssertEqual(EventState.suspendedLabel(authorityPeriod: row.authorityPeriod),
                       "No result reported")
    }

    // MARK: - The share image

    func testTheShareEyebrowSaysCanceled() {
        let started = Self.now.addingTimeInterval(-3 * 86_400)
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "suspended", sportName: "MLB", commenceTime: started,
                authorityPeriod: "Canceled", now: Self.now),
            "CANCELED")
        XCTAssertEqual(
            ShareableEventCardView.eyebrow(
                status: "suspended", sportName: "MLB", commenceTime: started,
                authorityPeriod: nil, now: Self.now),
            "NO RESULT REPORTED")
    }
}
