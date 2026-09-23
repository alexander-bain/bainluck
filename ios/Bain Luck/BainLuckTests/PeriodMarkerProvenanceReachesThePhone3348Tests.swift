import Foundation
import XCTest
@testable import Bain_Luck

/// #3348 — the phone reads the served `period_markers` for the first time, and
/// reads their provenance with them.
///
/// Until this ship `EventHistoryResponse` had no `periodMarkers` field at all
/// (`app/utils/period_markers.py`'s own note: "`ios/**` … decodes no marker at
/// all"). The chart derived every chip from `espn_history` / `win_prob_history`
/// first-seen, which is honest (#6718) but blind to the server's observed
/// football transition tier and to the distinction the server now draws between
/// an instrument's observation and a `commence_time + 45 min` guess.
///
/// THE CONTRACT (codex, 2026-09-22): no estimate silently becomes an observed
/// boundary; preserve `source`, `precision`, `not_before`; a first observed
/// state is not automatically the exact period start; unknown stays unknown.
///
/// SPECIMENS are the two production payloads the delivery was measured on,
/// fetched 2026-09-23 against `/health` commit `0411e045`:
///   * 15196980 (Raiders–Cardinals, NFL preseason 2026-08-13): two markers, both
///     `source: "estimated"`, with `espn_history: []` — nobody saw either.
///   * 15192596 (Blue Jays–Red Sox, MLB 2026-08-13, Alex's #1833 specimen): 31
///     markers, all `source: "win_prob"`, in ESPN's half-inning vocabulary.
/// The marker arrays below are verbatim excerpts of those payloads.
///
/// NATIVE EXECUTION: NOT RUN by the author (no Xcode in the authoring
/// environment). Statically validated only; Native runs this file.
final class PeriodMarkerProvenanceReachesThePhone3348Tests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let d = JSONDecoder()
        d.keyDecodingStrategy = .convertFromSnakeCase
        return d
    }

    /// The smallest `EventHistoryResponse` the decoder accepts, with the served
    /// `period_markers` spliced in verbatim.
    private func payload(periodMarkers: String?) -> Data {
        let markers = periodMarkers.map { ", \"period_markers\": \($0)" } ?? ""
        return Data("""
        {"event_id": 15196980, "home_team": "Las Vegas Raiders", "away_team": "Arizona Cardinals",
         "completed_at": "2026-08-13T01:18:09.569480+00:00", "status": "completed",
         "history": [{"timestamp": "2026-08-13T00:00:00+00:00", "home_probability": 0.42, "away_probability": 0.58}]
         \(markers)}
        """.utf8)
    }

    /// 15196980, verbatim.
    private let estimatedMarkers = """
    [{"timestamp": "2026-08-13T00:00:00+00:00", "period": "1st Quarter", "source": "estimated"},
     {"timestamp": "2026-08-13T00:45:00+00:00", "period": "2nd Quarter", "source": "estimated"}]
    """

    /// 15192596, the first eight of 31, verbatim.
    private let observedInningMarkers = """
    [{"timestamp": "2026-08-13T19:33:13.687672+00:00", "period": "Top 2nd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:35:13.532349+00:00", "period": "Middle 2nd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:37:13.917435+00:00", "period": "Bottom 2nd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:41:13.487936+00:00", "period": "End 2nd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:43:13.487228+00:00", "period": "Top 3rd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:47:41.676129+00:00", "period": "Middle 3rd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:49:41.676129+00:00", "period": "Bottom 3rd", "source": "win_prob"},
     {"timestamp": "2026-08-13T19:53:41.676129+00:00", "period": "End 3rd", "source": "win_prob"}]
    """

    /// The football transition tier's shape (`period_markers.py`, #5140/#6718).
    private let transitionMarkers = """
    [{"timestamp": "2026-09-15T00:54:43+00:00", "period": "2nd Quarter", "source": "espn_state",
      "precision": "boundary_observed", "not_before": "2026-09-15T00:53:43+00:00"},
     {"timestamp": "2026-09-15T02:10:00+00:00", "period": "4th Quarter", "source": "espn_state",
      "precision": "first_seen", "not_before": "2026-09-15T01:58:00+00:00"}]
    """

    // MARK: - Decoding

    func testAPayloadWithoutTheKeyStillDecodes() throws {
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: nil))
        XCTAssertNil(h.periodMarkers)
    }

    func testTheEstimatedSpecimenDecodesWithItsSource() throws {
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: estimatedMarkers))
        let m = try XCTUnwrap(h.periodMarkers)
        XCTAssertEqual(m.count, 2)
        XCTAssertEqual(m.map(\.period), ["1st Quarter", "2nd Quarter"])
        XCTAssertEqual(m.map(\.source), ["estimated", "estimated"])
        XCTAssertTrue(m.allSatisfy(\.isEstimated))
        XCTAssertEqual(m.map(\.precision), [nil, nil])
        XCTAssertEqual(m.map(\.notBefore), [nil, nil])
    }

    func testTheTransitionTierKeepsPrecisionAndNotBefore() throws {
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: transitionMarkers))
        let m = try XCTUnwrap(h.periodMarkers)
        XCTAssertEqual(m.map(\.precision), ["boundary_observed", "first_seen"])
        XCTAssertEqual(m.map(\.notBefore), ["2026-09-15T00:53:43+00:00", "2026-09-15T01:58:00+00:00"])
        XCTAssertFalse(m.contains(where: \.isEstimated))
    }

    /// Gotcha #42 — one bad element must not blank the chart. A marker whose
    /// `timestamp` is a number and whose `source` is an object decodes to nils
    /// and the payload beside it is untouched.
    func testAMalformedMarkerDoesNotTakeThePayloadDown() throws {
        let bad = """
        [{"timestamp": 12345, "period": "1st Quarter", "source": {"tier": 4}},
         {"timestamp": "2026-08-13T00:45:00+00:00", "period": "2nd Quarter", "source": "estimated"}]
        """
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: bad))
        let m = try XCTUnwrap(h.periodMarkers)
        XCTAssertEqual(m.count, 2)
        XCTAssertNil(m[0].timestamp)
        XCTAssertNil(m[0].source)
        XCTAssertFalse(m[0].isEstimated, "a marker with no readable source is not demoted to estimated")
        XCTAssertEqual(m[1].period, "2nd Quarter")
        XCTAssertEqual(h.history.count, 1)
    }

    // MARK: - servedPeriodMarkers (the pure read the chart consumes)

    func testServedMarkersAreNormalisedSortedAndFlagged() throws {
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: estimatedMarkers))
        let served = OddsChartView.servedPeriodMarkers(from: h.periodMarkers, sportKey: "americanfootball_nfl")
        XCTAssertEqual(served.map(\.label), ["Q1", "Q2"])
        XCTAssertEqual(served.map(\.isEstimated), [true, true])
        XCTAssertEqual(served.map(\.provenance.source), ["estimated", "estimated"])
        XCTAssertEqual(served[0].date, "2026-08-13T00:00:00+00:00".asDate)
    }

    func testServedTransitionMarkersCarryTheBracket() throws {
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: transitionMarkers))
        let served = OddsChartView.servedPeriodMarkers(from: h.periodMarkers, sportKey: "americanfootball_nfl")
        XCTAssertEqual(served.map(\.label), ["Q2", "Q4"])
        XCTAssertEqual(served.map(\.provenance.precision), ["boundary_observed", "first_seen"])
        XCTAssertEqual(served.map(\.provenance.notBefore),
                       ["2026-09-15T00:53:43+00:00".asDate, "2026-09-15T01:58:00+00:00".asDate])
        XCTAssertFalse(served.contains(where: \.isEstimated))
    }

    func testAMarkerWithNoTimestampOrLabelIsDroppedNotInvented() {
        let markers = [
            PeriodMarkerPayload(timestamp: nil, period: "1st Quarter", source: "win_prob"),
            PeriodMarkerPayload(timestamp: "2026-08-13T00:45:00+00:00", period: "", source: "win_prob"),
            PeriodMarkerPayload(timestamp: "not a date", period: "2nd Quarter", source: "win_prob"),
            PeriodMarkerPayload(timestamp: "2026-08-13T01:20:00+00:00", period: "3rd Quarter", source: "win_prob"),
        ]
        let served = OddsChartView.servedPeriodMarkers(from: markers, sportKey: "americanfootball_nfl")
        XCTAssertEqual(served.map(\.label), ["Q3"])
    }

    func testNilAndEmptyServeNothing() {
        XCTAssertEqual(OddsChartView.servedPeriodMarkers(from: nil, sportKey: "baseball_mlb"), [])
        XCTAssertEqual(OddsChartView.servedPeriodMarkers(from: [], sportKey: "baseball_mlb"), [])
    }

    // MARK: - Whole-inning identity (codex, n297 frame: `4th` and `4th Inning` as two chips)

    /// The half-inning vocabulary collapses to ONE whole-inning identity per
    /// inning on the chip strip — `Top 2nd`, `Middle 2nd`, `Bottom 2nd` and
    /// `End 2nd` are one chip, `2nd`. (The half is not lost: the scrub readout
    /// prints the raw period string, `GamePlayCardTimeDisplayTests`.)
    func testHalfInningMarkersShareOneWholeInningLabel() throws {
        let h = try decoder().decode(EventHistoryResponse.self, from: payload(periodMarkers: observedInningMarkers))
        let served = OddsChartView.servedPeriodMarkers(from: h.periodMarkers, sportKey: "baseball_mlb")
        XCTAssertEqual(served.map(\.label), ["2nd", "2nd", "2nd", "2nd", "3rd", "3rd", "3rd", "3rd"])
        XCTAssertTrue(served.allSatisfy { $0.provenance.source == "win_prob" && !$0.isEstimated })
    }

    /// THE DEFECT on the n297 frame: ESPN's `End of 4th Inning` lost its prefix
    /// and reached the chip strip as `4th Inning`, a second chip beside `4th`.
    func testInningWithItsNounIsTheSameInning() {
        XCTAssertEqual(PeriodLabel.normalize("Top 4th"), "4th")
        XCTAssertEqual(PeriodLabel.normalize("4th Inning"), "4th")
        XCTAssertEqual(PeriodLabel.normalize("End of 4th Inning"), "4th")
        XCTAssertEqual(PeriodLabel.normalize("Middle 4th"), "4th")
        XCTAssertEqual(PeriodLabel.normalize("11th inning"), "11th")
    }

    /// Controls: nothing else in the vocabulary moves.
    func testOtherVocabularyIsUnchanged() {
        XCTAssertEqual(PeriodLabel.normalize("1st Quarter"), "Q1")
        XCTAssertEqual(PeriodLabel.normalize("End of 1st Quarter"), "Q1")
        XCTAssertEqual(PeriodLabel.normalize("2nd Period"), "P2")
        XCTAssertEqual(PeriodLabel.normalize("1st Half"), "1H")
        XCTAssertEqual(PeriodLabel.normalize("Halftime"), "HT")
        XCTAssertEqual(PeriodLabel.normalize("Final"), "Final")
        XCTAssertEqual(PeriodLabel.normalize("Delayed"), "Delayed")
    }
}
