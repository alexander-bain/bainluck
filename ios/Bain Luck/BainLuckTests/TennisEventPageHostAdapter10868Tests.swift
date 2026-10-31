import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's host glue (`TennisEventPageHost10868`):
/// its pure `build` from the values the page already holds, on the REAL
/// retained bodies — the Fils–van de Zandschulp and Davidovich Fokina–Tiafoe
/// details (`TennisMatchPageAdapter10868Tests`, byte for byte), their histories
/// (`TennisHistoryAdapter10868Tests`) and `/game-markets`
/// (`TennisOriginalsAdapter10868Tests`), reduced verbatim subsets. Source paths,
/// sha256 and what each subset kept are written in those files.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// CONSTRUCTED here: the reader's calendar and `now`; the interrupted delivery
/// flag; the held reading state (a tap position, a held catalogue original).
@MainActor
final class TennisEventPageHostAdapter10868Tests: XCTestCase {
    private typealias Host = TennisEventPageHost10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Details = OriginalMarketDetails9483

    private func build(_ event: EventDetail, history: EventHistoryResponse?, markets: GameMarketsResponse?,
                       now: String, interrupted: Bool = false, reading: Host.Reading = Host.Reading()) -> Host.Built {
        Host.build(event: event, history: history, markets: markets,
                   probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, deliveryInterrupted: interrupted,
                   now: now.asDate!, reading: reading, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    private func historyHost(_ now: String) -> TennisHistoryAdapter10868.Host {
        TennisHistoryAdapter10868.Host(now: now.asDate!, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    // MARK: - The retained live match

    func testTheRetainedLiveMatchComposesFromItsThreeBodiesWithNoStoryStream() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let history = try TennisHistoryAdapter10868Tests.live()
        let built = build(event, history: history, markets: try TennisOriginalsAdapter10868Tests.live(),
                          now: Fixtures.liveReadAt)
        XCTAssertTrue(Host.applies(event))
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertEqual(built.input.history, TennisHistoryAdapter10868.history(
            history, event: event, phase: .during, host: historyHost(Fixtures.liveReadAt)))
        XCTAssertEqual(built.input.history.series[0].runs.count, 1)
        let series = try XCTUnwrap(built.series)
        XCTAssertEqual(series.points.count, 89, "the chart's own drawn rows 510–598, the same as the history")
        XCTAssertEqual(built.input.reading, TennisReadingAdapter10868.reading(
            series, held: nil, event: event, now: Fixtures.liveReadAt.asDate!))
        XCTAssertEqual(built.originals.catalogue?.originals.count, 12)
        XCTAssertEqual(built.input.copy.allPropsLabel, "All 12 original props")
        XCTAssertNil(built.input.stream, "no production owner proves a tennis story, so no stream")
        XCTAssertNil(built.input.sets)
        XCTAssertNil(built.input.totals)
        XCTAssertNil(built.input.exact)
        XCTAssertNil(built.input.handicaps)
        XCTAssertNil(built.input.notice)
        XCTAssertEqual(built.input.headline.state?.figure, "0–1")
    }

    func testAHeldTapIsResolvedOnEveryPassAndShowsOnThePage() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let history = try TennisHistoryAdapter10868Tests.live()
        let first = build(event, history: history, markets: nil, now: Fixtures.liveReadAt)
        let series = try XCTUnwrap(first.series)
        // CONSTRUCTED: a tap at 11:30:20Z.
        let held = TennisReadingAdapter10868.inspect(try XCTUnwrap("2026-10-12T11:30:20Z".asDate).timeIntervalSince1970,
                                                     in: series)
        let next = build(event, history: history, markets: nil, now: Fixtures.liveReadAt, reading: Host.Reading(held: held))
        guard case .reading(let wanted)? = held else { return XCTFail("a tap inside the line holds a reading") }
        XCTAssertEqual(next.input.reading?.shown, TennisChartReading9483.Shown.reading(wanted, held: true))
        XCTAssertEqual(next.input.reading?.offersLatest, true)
        XCTAssertNotNil(TennisEventPageModel10868(next.input).pageReading)
        XCTAssertNil(TennisEventPageModel10868(first.input).pageReading, "nothing held, no page reading")
    }

    func testWithoutAHistoryResponseOnlyTheChartSlotAndTheReadingAreUnavailable() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let markets = try TennisOriginalsAdapter10868Tests.live()
        let withHistory = build(event, history: try TennisHistoryAdapter10868Tests.live(), markets: markets,
                                now: Fixtures.liveReadAt)
        let without = build(event, history: nil, markets: markets, now: Fixtures.liveReadAt)
        XCTAssertEqual(without.input.history.plotAbsence?.title, "History unavailable")
        XCTAssertNil(without.input.history.expand)
        XCTAssertNil(without.input.reading)
        XCTAssertNil(without.series)
        XCTAssertEqual(without.input.headline, withHistory.input.headline)
        XCTAssertEqual(without.input.about, withHistory.input.about)
        XCTAssertEqual(without.originals.catalogue, withHistory.originals.catalogue)
    }

    func testAForeignHistoryLeavesNoPlotSeriesReadingOrControlsAndTheRestOfThePageStays() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let markets = try TennisOriginalsAdapter10868Tests.live()
        let same = build(event, history: try TennisHistoryAdapter10868Tests.live(), markets: markets,
                         now: Fixtures.liveReadAt)
        let own = try XCTUnwrap(same.series)
        // A reading held on this event's own series, then another event's body arrives.
        let held = TennisReadingAdapter10868.inspect(try XCTUnwrap("2026-10-12T11:30:20Z".asDate).timeIntervalSince1970,
                                                     in: own)
        XCTAssertNotNil(held)
        // CONSTRUCTED: the live subset with only its `event_id` changed (`TennisHistoryAdapter10868Tests.foreign`).
        let foreign = build(event, history: try TennisHistoryAdapter10868Tests.foreign(), markets: markets,
                            now: Fixtures.liveReadAt, reading: Host.Reading(held: held))
        XCTAssertEqual(foreign.input.history, TennisHistoryAdapter10868.unavailable(event: event, phase: .during))
        XCTAssertNil(foreign.input.history.expand)
        XCTAssertNil(foreign.input.history.inspect)
        XCTAssertNil(foreign.series)
        XCTAssertNil(foreign.input.reading, "no foreign baseline, held or latest reading")
        XCTAssertNil(TennisEventPageModel10868(foreign.input).pageReading)
        XCTAssertNil(TennisEventPageModel10868(foreign.input).readerReading)
        let controls = Host.readingControls(foreign.series) { _ in XCTFail("no plot-reading control exists") }
        XCTAssertNil(controls.plot)
        XCTAssertNil(controls.latest)

        // Everything that does not read the history is the same page.
        XCTAssertEqual(foreign.input.headline, same.input.headline)
        XCTAssertEqual(foreign.input.reader, same.input.reader)
        XCTAssertEqual(foreign.input.about, same.input.about)
        XCTAssertEqual(foreign.input.copy, same.input.copy)
        XCTAssertEqual(foreign.originals.catalogue, same.originals.catalogue)
    }

    func testThisEventsSeriesOffersBothPlotReadingControlsAndTheyHoldThroughTheHost() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let built = build(event, history: try TennisHistoryAdapter10868Tests.live(), markets: nil, now: Fixtures.liveReadAt)
        let series = try XCTUnwrap(built.series)
        var holds: [TennisChartReading9483.Held?] = []
        let controls = Host.readingControls(series) { holds.append($0) }
        try XCTUnwrap(controls.plot)(try XCTUnwrap("2026-10-12T11:30:20Z".asDate).timeIntervalSince1970)
        try XCTUnwrap(controls.latest)()
        XCTAssertEqual(holds, [TennisReadingAdapter10868.inspect(try XCTUnwrap("2026-10-12T11:30:20Z".asDate).timeIntervalSince1970,
                                                                 in: series),
                               TennisReadingAdapter10868.latest(in: series)])
    }

    // MARK: - The retained final

    func testTheRetainedFinalComposesWithItsGradedOriginalsAndNoSettlementReading() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let history = try TennisHistoryAdapter10868Tests.finished()
        let built = build(event, history: history, markets: try TennisOriginalsAdapter10868Tests.finished(),
                          now: Fixtures.finalReadAt)
        XCTAssertEqual(built.input.phase, .final)
        XCTAssertEqual(built.input.history, TennisHistoryAdapter10868.history(
            history, event: event, phase: .final, host: historyHost(Fixtures.finalReadAt)))
        XCTAssertEqual(built.originals.catalogue?.originals.count, 18)
        XCTAssertEqual(built.originals.catalogue?.scope, "tennis:15327291:final:originals")
        guard case .reading(let latest, held: false)? = built.input.reading?.shown else {
            return XCTFail("the full-size history shows the latest recorded chance")
        }
        XCTAssertEqual(latest.date, "2026-10-11T15:40:00+00:00".asDate)
        XCTAssertEqual(latest.home, 0.891273, "the settlement 1.0 is the result, never a recorded chance")
        XCTAssertEqual(built.input.headline.state?.caption, "Final · Alejandro Davidovich Fokina won")
    }

    // MARK: - Selection and purity

    func testTheHeldCatalogueSelectionReachesTheOriginals() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let held = Details.Selection(scope: "tennis:15327807:during:originals",
                                     identity: Details.Identity(source: "kalshi", market: "65176060", side: "245059339"))
        let built = build(event, history: nil, markets: try TennisOriginalsAdapter10868Tests.live(),
                          now: Fixtures.liveReadAt, reading: Host.Reading(selection: held))
        XCTAssertEqual(built.originals.selection, held)
        XCTAssertEqual(Details.original(in: built.originals.catalogue, selection: held)?.outcome, "Arthur Fils wins 2-1")
    }

    func testBuildIsPureSoEveryChangedValueReachesTheNextPass() throws {
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let markets = try TennisOriginalsAdapter10868Tests.live()
        let history = try TennisHistoryAdapter10868Tests.live()
        XCTAssertEqual(build(event, history: history, markets: markets, now: Fixtures.liveReadAt).input,
                       build(event, history: history, markets: markets, now: Fixtures.liveReadAt).input)
        let interrupted = build(event, history: history, markets: markets, now: Fixtures.liveReadAt, interrupted: true)
        XCTAssertEqual(interrupted.input.notice, "Update interrupted · showing the last recorded chances")
        XCTAssertFalse(Host.applies(try Fixtures.edited(Fixtures.liveDetail, ["sport": "icehockey_nhl"])))
    }
}
