import XCTest
@testable import Bain_Luck

/// #10868 — the baseball game screen's host glue: the pure builder the host
/// view runs on every body pass, on the RETAINED REAL bodies
/// (`BaseballRetained10868`).
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// The host view itself (sheets, Done, which sheet a Details opens in) is
/// SwiftUI state and is not driven here; what is pinned is that its input
/// comes only from the passed values, that another event's history is never
/// drawn, that every held selection reaches its story unchanged, and — through
/// the host's pure `routes` handed to the actual presentation and the actual
/// stream's own intents — that each page action asks for the page's hold
/// exactly once, before it lands, and full-size content asks for none. The
/// mount into `EventDetailView` is a proposal and is not exercised; no stream
/// hold qualification, native runtime or rendered behaviour is claimed.
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

    // MARK: One hold per action

    /// The retained final, built as the host builds each pass.
    private static func final(_ reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        Host.build(event: try F.finalEvent(), history: try F.history(F.finalHistory), markets: try F.markets(),
                   related: try F.related(), probabilityObservedAt: nil, now: F.finalNow, reading: reading,
                   calendar: F.pacific, locale: F.locale)
    }

    /// The host's routes for one pass, each landing logged with its exact
    /// value: the page's hold as "hold", a presented mode by its `Presented`
    /// id, a catalogue selection by its scope and market, a browse by its
    /// card, a story original by its id.
    private static func wired(_ built: Host.Built, log: @escaping (String) -> Void) -> Host.Routes {
        Host.routes(built, hold: { log("hold") },
                    present: { log("present:\(Host.Presented(mode: $0).id)") },
                    select: { log("select:\($0.scope)|\($0.identity.market)") },
                    browse: { log("browse:\($0?.rawValue ?? "-")") },
                    show: { log("original:\($0.id)") })
    }

    /// The actual presentation with the routes wired as the host's `page`
    /// wires them; a story selection is the host's plain write (logged), with
    /// no hold of its own.
    private static func drawn(_ built: Host.Built, _ routes: Host.Routes,
                              mode: BaseballEventPageMode10868 = .page,
                              log: @escaping (String) -> Void) -> BaseballEventPagePresentation10868 {
        BaseballEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onAllProps: routes.allProps,
            onOriginalSelect: routes.originalSelect,
            onOriginalHistory: nil,
            onStoryIntent: routes.storyIntent,
            onHistoryAction: routes.historyAction,
            onHistoryInspectionChoice: nil,
            onHistoryPlotPosition: nil,
            onHomeRunDetails: routes.storyDetails,
            onStrikeoutSelect: { log("strikeoutSelect:\($0)") },
            onStrikeoutDetails: routes.storyDetails,
            onTotalSelect: { log("totalSelect:\($0)") },
            onTotalMilestoneDetails: nil,
            onTotalLineDetails: routes.storyDetails,
            onSeriesMarket: { log("seriesMarket:\($0)") },
            onSeriesOption: { log("seriesOption:\($0):\($1)") },
            onSeriesDetails: routes.storyDetails,
            onExtraInningsSelect: { log("extraSelect:\($0)") },
            onExtraInningsDetails: routes.storyDetails)
    }

    /// The hook the actual stream view hands its displayed card, sending to
    /// the host's route exactly as `StoryStreamPresentationView10868` does.
    private static func activation(_ built: Host.Built, _ card: StoryStreamPresentation10868.CardRef,
                                   routes: Host.Routes) -> StoryStreamCardActivation10868 {
        let stream = built.input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        return StoryStreamCardActivation10868(
            card: card, intents: stream.activationIntents(for: card, resolved: resolved), send: routes.storyIntent)
    }

    func testAPageStoryDetailsHoldsOnceThroughTheStreamAndTheRouteAddsNoSecondHold() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let built = try Self.final()
        let routes = Self.wired(built, log: record)
        let page = Self.drawn(built, routes, log: record)
        let primary = try XCTUnwrap(built.input.stream.primary)
        XCTAssertEqual(primary.id, "homeRuns")
        let homeRuns = try XCTUnwrap(page.homeRunsContent(activation: Self.activation(built, primary, routes: routes)))
        XCTAssertEqual(log, [], "building the routes, the page and the card asks for nothing")

        let homeRun = try XCTUnwrap(built.input.homeRuns?.card.entries.first?.original.id)
        homeRuns.onDetails?(homeRun)
        XCTAssertEqual(log, ["hold", "original:\(homeRun)"])

        // Two actions on one card: one hold each, never two for one.
        log = []
        let held = try Self.final(Host.Reading(story: .strikeouts))
        let heldRoutes = Self.wired(held, log: record)
        let shown = try XCTUnwrap(held.input.stream.primary)
        XCTAssertEqual(shown.id, "strikeouts")
        let ladder = try XCTUnwrap(Self.drawn(held, heldRoutes, log: record)
            .strikeoutsContent(activation: Self.activation(held, shown, routes: heldRoutes)))
        let row = try XCTUnwrap(held.input.strikeouts?.card.targets.first?.rowID)
        let target = try XCTUnwrap(held.input.strikeouts?.card.targets.first?.original.id)
        ladder.onSelect(row)
        ladder.onDetails?(target)
        XCTAssertEqual(log, ["hold", "strikeoutSelect:\(row)", "hold", "original:\(target)"])
    }

    func testThePageStreamsOpenAndBrowseHoldOnceAndTheOpenLandsWithNoSecondHold() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let built = try Self.final()
        let routes = Self.wired(built, log: record)
        let stream = built.input.stream
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let primary = try XCTUnwrap(stream.primary)

        // The intents the actual stream sends for its open: the interaction, then the open.
        let open = stream.intents(for: .open(primary), resolved: resolved)
        XCTAssertEqual(open, [.interaction(scope: stream.scope, card: primary), .open(primary)])
        open.forEach(routes.storyIntent)
        XCTAssertEqual(log, ["hold", "present:reader.homeRuns"])

        log = []
        stream.intents(for: .browse(.next), resolved: resolved).forEach(routes.storyIntent)
        XCTAssertEqual(log, ["hold", "browse:strikeouts"])
    }

    func testFullSizeDetailsShowTheExactOriginalWithNoHold() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let built = try Self.final(Host.Reading(readerOpen: true))
        let routes = Self.wired(built, log: record)
        let homeRun = try XCTUnwrap(built.input.homeRuns?.card.entries.first?.original.id)
        let target = try XCTUnwrap(built.input.strikeouts?.card.targets.first?.original.id)
        guard case .finalTargets(let totals)? = built.input.totals else { return XCTFail("final targets") }
        let line = try XCTUnwrap(totals.card.lines.last?.original.id)
        let outcome = try XCTUnwrap(built.input.series?.card.questions.first?.options.first?.original.id)

        // Full-size content: the same leaves, no activation (`reader(_:)`).
        Self.drawn(built, routes, mode: .reader(.homeRuns), log: record).homeRunsContent()?.onDetails?(homeRun)
        Self.drawn(built, routes, mode: .reader(.strikeouts), log: record)
            .strikeoutsContent(expanded: true)?.onDetails?(target)
        Self.drawn(built, routes, mode: .reader(.totals), log: record)
            .finalTotalsContent(expanded: true)?.onDetails(line)
        Self.drawn(built, routes, mode: .reader(.series), log: record).seriesContent()?.onDetails?(outcome)
        XCTAssertEqual(log, ["original:\(homeRun)", "original:\(target)", "original:\(line)", "original:\(outcome)"])
    }

    func testTheAnchorsFullChartHoldsOnceThenOpensTheFullSizeHistory() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let built = try Self.final()
        let routes = Self.wired(built, log: record)
        let expand = try XCTUnwrap(built.input.history.expand)
        XCTAssertEqual(expand.id, HockeyJourneyHistoryAdapter10868.expandActionID)
        XCTAssertTrue(expand.isAvailable)
        let anchor = Self.drawn(built, routes, log: record).historyContent(reader: false)

        anchor.onAction?(expand.id)
        XCTAssertEqual(log, ["hold", "present:reader.history"])

        // An id the host routes nowhere lands nowhere and holds nothing.
        log = []
        anchor.onAction?("not-an-action")
        XCTAssertEqual(log, [])
    }

    func testAllPropsAndACatalogueSelectionEachHoldOnceBeforeTheyLand() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let built = try Self.final()
        let routes = Self.wired(built, log: record)

        Self.drawn(built, routes, log: record).openAllProps()
        XCTAssertEqual(log, ["hold", "present:catalogue"])

        log = []
        let catalogue = try XCTUnwrap(built.originals.catalogue)
        let first = try XCTUnwrap(catalogue.originals.first)
        let chosen = OriginalMarketDetails9483.Selection(scope: catalogue.scope, identity: first.identity)
        let select = try XCTUnwrap(Self.drawn(built, routes, mode: .catalogue, log: record).catalogueContent()?.onSelect)
        select(chosen)
        XCTAssertEqual(log, ["hold", "select:\(catalogue.scope)|\(first.identity.market)", "present:original"])
    }

    func testBuildingEveryModeAndAnUnresolvedDetailsAskForNothing() throws {
        var log: [String] = []
        let record: (String) -> Void = { log.append($0) }
        let built = try Self.final()
        let routes = Self.wired(built, log: record)
        let modes: [BaseballEventPageMode10868] = [.page, .reader(.history), .reader(.homeRuns), .reader(.strikeouts),
                                                   .reader(.totals), .reader(.series), .catalogue, .original]
        for mode in modes {
            let view = Self.drawn(built, routes, mode: mode, log: record)
            _ = view.historyContent(reader: mode != .page)
            _ = view.homeRunsContent()
            _ = view.strikeoutsContent()
            _ = view.finalTotalsContent()
            _ = view.seriesContent()
            _ = view.catalogueContent()
            _ = view.originalDetailsContent()
        }
        routes.storyDetails("not-an-original")
        XCTAssertEqual(log, [])
    }
}
