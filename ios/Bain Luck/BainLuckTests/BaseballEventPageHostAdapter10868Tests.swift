import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game screen's host glue: the pure builder the host
/// view runs on every body pass, on the RETAINED REAL bodies
/// (`BaseballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The host view itself (sheets, Done, the hold before each mode) is SwiftUI
/// state and is not driven here; what is pinned is that its input comes only
/// from the passed values, that another event's history is never drawn, and
/// that every held selection reaches its story unchanged. The mount into
/// `EventDetailView` is a proposal and is not exercised.
@MainActor
final class BaseballEventPageHostAdapter10868Tests: XCTestCase {
    private typealias F = BaseballRetained10868
    private typealias Host = BaseballEventPageHost10868

    func testOnlyMLBGamesTakeTheScreenAndEachPresentedModeHasItsOwnIdentity() throws {
        XCTAssertTrue(Host.applies(try F.finalEvent()))
        XCTAssertFalse(Host.applies(try F.detail(F.edited(F.finalDetail, setting: ["sport": "soccer_epl"]))))
        XCTAssertEqual(Host.Presented(mode: .page).id, "page")
        XCTAssertEqual(Host.Presented(mode: .reader(.history)).id, "reader.history")
        XCTAssertEqual(Host.Presented(mode: .reader(.series)).id, "reader.series")
        XCTAssertEqual(Host.Presented(mode: .reader(.extraInnings)).id, "reader.extraInnings")
        XCTAssertEqual(Host.Presented(mode: .catalogue).id, "catalogue")
        XCTAssertEqual(Host.Presented(mode: .original).id, "original")
    }

    func testTheInputIsBuiltFromThePassedValuesAloneAndTheMatchingHistoryIsDrawn() throws {
        let event = try F.finalEvent()
        let history = try F.history(F.finalHistory)
        func build() throws -> Host.Built {
            Host.build(event: event, history: history, markets: try F.markets(), related: try F.related(),
                       probabilityObservedAt: nil, now: F.finalNow, calendar: F.pacific, locale: F.locale)
        }
        let first = try build()
        XCTAssertEqual(first.input, try build().input, "the same values build the same page")
        XCTAssertEqual(first.input.history, BaseballHistoryAdapter10868.history(
            history, event: event, phase: .final, host: F.historyHost(F.finalNow)))
        XCTAssertEqual(first.originals.catalogue?.scope, "mlb:15321836:final:originals")
        XCTAssertEqual(first.originals.tint, BaseballGamePageAdapter10868.tints(event).home)
    }

    /// CONSTRUCTED: the final history subset with only `event_id` changed.
    func testAnotherEventsHistoryOrNoneLeavesOnlyTheChartSlotUnavailable() throws {
        let event = try F.finalEvent()
        let foreign = try F.history(F.edited(F.finalHistory, setting: ["event_id": 1]))
        let unavailable = BaseballHistoryAdapter10868.unavailable(event: event, phase: .final)
        for history in [foreign, nil] as [EventHistoryResponse?] {
            let built = Host.build(event: event, history: history, markets: try F.markets(), related: try F.related(),
                                   probabilityObservedAt: nil, now: F.finalNow, calendar: F.pacific, locale: F.locale)
            XCTAssertEqual(built.input.history, unavailable)
            XCTAssertEqual(built.input.stream.cards.count, 4, "the stories still compose")
            XCTAssertNotNil(built.input.copy.allPropsLabel, "All props is still reachable")
        }
    }

    func testEveryHeldSelectionReachesItsStoryUnchanged() throws {
        let markets = try F.markets()
        let related = try F.related()
        let series = try XCTUnwrap(MLBSeriesCard11284.build(related.seriesQuestionMatrix, eventID: F.eventID))
        let question = series.questions[1].questionKey
        let option = series.questions[1].options[0].optionKey
        let reading = Host.Reading(
            story: .series,
            selections: BaseballStoriesAdapter10868.Selections(
                strikeout: "Hunter Brown: Strikeouts O/U 8.5-Over", total: "o:244311410",
                seriesQuestion: question, seriesOption: option),
            selection: nil, readerOpen: true, wide: true)
        let input = Host.build(event: try F.finalEvent(), history: nil, markets: markets, related: related,
                               probabilityObservedAt: nil, now: F.finalNow, reading: reading,
                               calendar: F.pacific, locale: F.locale).input

        XCTAssertEqual(input.stream.primary?.id, "series")
        XCTAssertTrue(input.stream.readerOpen)
        XCTAssertTrue(input.stream.wide)
        XCTAssertEqual(input.strikeouts?.selectedRowID, "Hunter Brown: Strikeouts O/U 8.5-Over")
        guard case .finalTargets(let totals)? = input.totals else { return XCTFail("final targets") }
        XCTAssertEqual(totals.selectedOptionKey, "o:244311410")
        XCTAssertEqual(input.series?.selectedQuestionKey, question)
        XCTAssertEqual(input.series?.selectedOptionKey, option)

        // During play the same held run line is the held milestone.
        let live = Host.build(event: try F.liveEvent(), history: nil, markets: markets, related: related,
                              probabilityObservedAt: F.liveObservedAt, now: F.liveNow, reading: reading,
                              calendar: F.pacific, locale: F.locale).input
        guard case .milestones(let milestones)? = live.totals else { return XCTFail("run milestones") }
        XCTAssertEqual(milestones.selectedMilestoneID, "o:244311410")
        XCTAssertEqual(live.stream.primary?.id, "series")
    }

    /// CONSTRUCTED: the live `/game-markets` body carrying the retained live
    /// extra-innings row; the admission is the owner's reading of that row's
    /// own served values.
    func testTheExtraInningsAdmissionReachesItsStoryItsHeldOutcomeAndItsDetails() throws {
        let admission = try F.liveExtraAdmission()
        func build(_ admissions: [BaseballExtraInningsAdmission10868], held: String? = nil) throws -> Host.Built {
            Host.build(event: try F.liveEvent(), history: nil, markets: try F.liveExtraMarkets(),
                       related: try F.related(), extraInnings: admissions, probabilityObservedAt: nil,
                       now: F.extraNow,
                       reading: Host.Reading(selections: BaseballStoriesAdapter10868.Selections(extraInnings: held)),
                       calendar: F.pacific, locale: F.locale)
        }
        let admitted = try build([admission]).input
        let story = try XCTUnwrap(admitted.extraInnings)
        let option = try XCTUnwrap(story.options.first)
        XCTAssertEqual(option.pregame.text, formatProbability(0.11))
        XCTAssertEqual(option.recorded.text, formatProbability(0.16))
        XCTAssertEqual(story.selectedID, option.id)

        // Details resolves the exact original the page holds, readings named.
        let details = try XCTUnwrap(BaseballStoriesAdapter10868.original(option.id, in: admitted))
        XCTAssertEqual(details, option.original)

        // No admission: the same production outcome, each chance in its own words.
        let bare = try XCTUnwrap(try build([]).input.extraInnings?.options.first)
        XCTAssertEqual(bare.id, option.id)
        XCTAssertEqual(bare.pregame, .unavailable("Pregame chance unavailable"))
        XCTAssertEqual(bare.recorded, .unavailable("In-game chance unavailable"))

        // A held outcome is passed through unchanged, even one no longer carried.
        XCTAssertEqual(try build([admission], held: "withdrawn-outcome").input.extraInnings?.selectedID,
                       "withdrawn-outcome")
        XCTAssertNil(BaseballStoriesAdapter10868.original("withdrawn-outcome", in: admitted))
    }
}
