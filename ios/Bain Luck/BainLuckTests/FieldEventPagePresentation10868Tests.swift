import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the generic FIELD event screen composed from the accepted leaves.
///
/// PREPARED / NOT RUN. The view is SwiftUI and is not rasterised here. What is
/// asserted is the composition only: which actual leaf Views the page mounts at
/// each phase, that each receives the owner's input unchanged, the story
/// stream's card-to-leaf wiring, the stream's activation hook before each card
/// action, the owner's interaction hook before each page, catalogue and Details
/// action (and never for full-size content, stream cards or passive reads), the
/// full-size history without its expand control and with the owner's scale
/// unchanged, the About and All props entries, and the arrangement candidates.
/// Each leaf's own rules stay with its own tests; nothing here claims a rendered
/// fit, a native runtime, VoiceOver behaviour or a production mount.
///
/// The base input is the field screen's own production adapters run on the
/// retained REAL chess board and `/history` (`FieldEventAdapterFixtures10868`);
/// every variant built from it below is CONSTRUCTED and names the one field it
/// changes.
@MainActor
final class FieldEventPagePresentation10868Tests: XCTestCase {
    private typealias Screen = FieldEventPagePresentation10868
    private typealias Model = FieldEventPageModel10868
    private typealias F = FieldEventAdapterFixtures10868

    /// Records every callback and hook, in order.
    private final class Log {
        var events: [String] = []
    }

    private func built() throws -> FieldEventPageHost10868.Built {
        FieldEventPageHost10868.build(field: try F.market(F.chessBefore), history: try F.history(F.chessHistory),
                                      now: F.chessCapture.asDate!, calendar: F.pacific, locale: F.enUS)
    }

    private func base() throws -> FieldEventPageInput10868 { try built().input }

    /// CONSTRUCTED: the same input with only the named parts replaced.
    private func with(_ input: FieldEventPageInput10868,
                      phase: FieldOutlookPhase10868? = nil,
                      stories: [FieldEventPageStory10868]? = nil,
                      about: FieldEventPageAbout10868?? = nil,
                      copy: FieldEventPageCopy10868? = nil) -> FieldEventPageInput10868 {
        FieldEventPageInput10868(
            phase: phase ?? input.phase, reader: input.reader, headline: input.headline, history: input.history,
            field: input.field, movement: input.movement, stream: input.stream,
            stories: stories ?? input.stories, about: about ?? input.about, copy: copy ?? input.copy)
    }

    // MARK: Mounting

    func testTheChessPageMountsTheHeadlineTheAnchorAndBothStories() throws {
        let input = try base()
        let model = Model(input)
        XCTAssertEqual(model.headline, input.headline)
        XCTAssertEqual(model.field, input.field)
        XCTAssertEqual(model.movement, input.movement)
        XCTAssertTrue(FieldEventPageCard10868.allCases.allSatisfy(model.isMounted))
        XCTAssertTrue(model.readerShows(.history))
    }

    func testALeafFromAnotherPhaseIsNeverCoercedOntoThePage() throws {
        let input = try base()
        // CONSTRUCTED: only the page phase changed to during.
        let during = Model(with(input, phase: .during))
        XCTAssertNil(during.headline, "a before headline is not a during headline")
        XCTAssertNil(during.field)
        XCTAssertNil(during.movement)
        XCTAssertTrue(during.isMounted(.history))
        XCTAssertFalse(during.readerShows(.field))
        XCTAssertNil(during.story("field"))
        // CONSTRUCTED: only the page phase changed to final.
        let final = Model(with(input, phase: .final))
        XCTAssertNil(final.headline)
        XCTAssertNil(final.field)
        XCTAssertNil(final.movement)
    }

    func testAStreamIdNamesExactlyOneMountedStoryOrNothing() throws {
        let input = try base()
        let model = Model(input)
        XCTAssertEqual(model.story("field")?.card, .field)
        XCTAssertEqual(model.story("movement")?.card, .movement)
        XCTAssertNil(model.story("history"))
        XCTAssertNil(model.story("unknown"))
        // CONSTRUCTED: only the story links changed — a duplicated id, and a link to the anchor.
        let duplicated = Model(with(input, stories: [
            FieldEventPageStory10868(cardID: "field", card: .field),
            FieldEventPageStory10868(cardID: "field", card: .movement),
            FieldEventPageStory10868(cardID: "chart", card: .history),
        ]))
        XCTAssertNil(duplicated.story("field"), "never a neighbour")
        XCTAssertNil(duplicated.story("chart"))
    }

    // MARK: Full-size history

    func testTheFullSizeHistoryIsTheSameInputExpandedWithoutItsExpandControl() throws {
        let input = try base()
        let reader = Model(input).readerHistory
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertNil(reader.expand)
        XCTAssertNotNil(input.history.expand)
        // The owner's Auto / Full choice holds in the full-size chart.
        XCTAssertEqual(reader.scale, input.history.scale)
        XCTAssertEqual(reader.ceiling, input.history.ceiling)
        XCTAssertEqual(reader.yTicks, input.history.yTicks)
        XCTAssertEqual(reader.series, input.history.series)
        XCTAssertEqual(reader.domain, input.history.domain)
        XCTAssertEqual(reader.notes, input.history.notes)
        XCTAssertEqual(reader.details, input.history.details)
        XCTAssertEqual(reader.plotAbsence, input.history.plotAbsence)
    }

    // MARK: About and All props

    func testTheAboutAndAllPropsEntriesNeedReadableWordsAndACallback() throws {
        let input = try base()
        let model = Model(input)
        XCTAssertNotNil(model.about)
        XCTAssertTrue(model.aboutAvailable(canOpen: true))
        XCTAssertFalse(model.aboutAvailable(canOpen: false))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.history), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true), "the page has the headline's own control")
        XCTAssertFalse(model.aboutEntry(mode: .catalogue, canOpen: true))
        XCTAssertTrue(model.allPropsAvailable(canOpen: true))
        XCTAssertFalse(model.allPropsAvailable(canOpen: false))
        // CONSTRUCTED: only the About changed to blank words, then to none.
        XCTAssertNil(Model(with(input, about: .some(FieldEventPageAbout10868(title: " ", paragraphs: ["", "\n"])))).about)
        XCTAssertNil(Model(with(input, about: .some(nil))).about)
        // CONSTRUCTED: only the copy changed to no All props label.
        let noLabel = FieldEventPageCopy10868(storiesLabel: input.copy.storiesLabel, storyUnavailable: input.copy.storyUnavailable,
                                              headlineUnavailable: input.copy.headlineUnavailable, allPropsLabel: nil)
        XCTAssertFalse(Model(with(input, copy: noLabel)).allPropsAvailable(canOpen: true))
    }

    func testArrangementsStackOnPhoneAndAtAccessibilitySizes() {
        XCTAssertEqual(Model.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
    }

    // MARK: Leaves receive the owner's input unchanged

    func testEachLeafReceivesTheOwnersInputUnchanged() throws {
        let made = try built()
        let input = made.input
        let view = Screen(input: input, originals: made.originals)
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.historyContent(reader: true).input, Model(input).readerHistory)
        XCTAssertEqual(view.fieldContent()?.input, input.field)
        XCTAssertEqual(view.movementContent()?.input, input.movement)
        XCTAssertEqual(view.catalogueContent()?.catalogue, made.originals.catalogue)
        XCTAssertEqual(view.catalogueContent()?.heading, "All props")
        XCTAssertEqual(view.originalDetailsContent()?.catalogue, made.originals.catalogue)
        XCTAssertEqual(view.aboutContent()?.about, input.about)
        // No originals: neither the catalogue nor Details has content.
        XCTAssertNil(Screen(input: input).catalogueContent())
        XCTAssertNil(Screen(input: input).originalDetailsContent())
    }

    // MARK: Hooks and callbacks

    func testWithoutCallbacksNothingPretendsToAct() throws {
        let view = Screen(input: try base())
        XCTAssertNil(view.headlineContent()?.onAbout)
        XCTAssertNil(view.headlineContent()?.onOpen)
        XCTAssertNil(view.historyContent(reader: false).onAction)
        XCTAssertNil(view.fieldContent()?.onChoose)
        XCTAssertNil(view.fieldContent()?.onOpenOriginal)
        XCTAssertNil(view.movementContent()?.onOpen)
        XCTAssertNil(view.aboutOpener())
    }

    func testAPageActionCallsTheHookOnceThenTheExactCallback() throws {
        let log = Log()
        let view = Screen(
            input: try base(),
            onAbout: { log.events.append("about") },
            onAllProps: { log.events.append("allProps") },
            onHeadlineOpen: { open in log.events.append("open:\(open.ref.outcomeID)") },
            onHistoryAction: { id in log.events.append("action:\(id)") },
            onInteraction: { log.events.append("hook") })
        // Building and reading calls nothing.
        _ = view.headlineContent()
        _ = view.historyContent(reader: false)
        _ = view.historyContent(reader: true)
        XCTAssertEqual(log.events, [])

        view.openAllProps()
        XCTAssertEqual(log.events, ["hook", "allProps"])
        log.events = []
        view.headlineContent()?.onAbout?()
        XCTAssertEqual(log.events, ["hook", "about"])
        log.events = []
        let ref = try XCTUnwrap(view.input.headline.displayed.first).ref
        view.headlineContent()?.onOpen?(FieldMovementOpen10868(ref: ref, observation: nil))
        XCTAssertEqual(log.events, ["hook", "open:\(ref.outcomeID)"])
        log.events = []
        view.historyContent(reader: false).onAction?(FieldEventHistoryAdapter10868.expandActionID)
        XCTAssertEqual(log.events, ["hook", "action:\(FieldEventHistoryAdapter10868.expandActionID)"])
        log.events = []
        // Full-size content keeps the exact callbacks: no hook.
        view.historyContent(reader: true).onAction?(GolfFieldHistoryAdapter10868.scaleActionID)
        XCTAssertEqual(log.events, ["action:\(GolfFieldHistoryAdapter10868.scaleActionID)"])
        log.events = []
        view.openAbout()
        XCTAssertEqual(log.events, ["about"])
    }

    func testAStreamCardRequestsItsActivationThenTheExactCallbackAndNeverTheHook() throws {
        let log = Log()
        let input = try base()
        let view = Screen(
            input: input,
            onFieldChoose: { ref in log.events.append("choose:\(ref.outcomeID)") },
            onFieldOpenOriginal: { ref in log.events.append("original:\(ref.outcomeID)") },
            onMovementOpen: { open in log.events.append("movement:\(open.observation ?? "")") },
            onInteraction: { log.events.append("hook") })
        let card = StoryStreamPresentation10868.CardRef(scope: input.stream.scope, id: "field")
        let activation = StoryStreamCardActivation10868(
            card: card, intents: [.interaction(scope: input.stream.scope, card: card)],
            send: { _ in log.events.append("activation") })
        let ref = try XCTUnwrap(input.field?.displayed.first).ref
        view.fieldContent(activation: activation)?.onChoose?(ref)
        XCTAssertEqual(log.events, ["activation", "choose:\(ref.outcomeID)"])
        log.events = []
        view.fieldContent(activation: activation)?.onOpenOriginal?(ref)
        XCTAssertEqual(log.events, ["activation", "original:\(ref.outcomeID)"])
        log.events = []
        view.movementContent(activation: activation)?.onOpen?(FieldMovementOpen10868(ref: ref, observation: "key"))
        XCTAssertEqual(log.events, ["activation", "movement:key"])
        log.events = []
        // Full-size content: the exact callback, no activation and no hook.
        view.fieldContent()?.onChoose?(ref)
        XCTAssertEqual(log.events, ["choose:\(ref.outcomeID)"])
    }

    func testCatalogueAndDetailsActionsPassTheHookFirst() throws {
        let log = Log()
        let made = try built()
        let view = Screen(
            input: made.input, mode: .catalogue, originals: made.originals,
            onOriginalSelect: { selection in log.events.append("select:\(selection.identity.side)") },
            onOriginalHistory: { _ in log.events.append("history") },
            onInteraction: { log.events.append("hook") })
        let identity = try XCTUnwrap(made.originals.catalogue?.originals.first).identity
        let selection = OriginalMarketDetails9483.Selection(scope: try XCTUnwrap(made.originals.catalogue?.scope),
                                                            identity: identity)
        view.catalogueContent()?.onSelect?(selection)
        XCTAssertEqual(log.events, ["hook", "select:\(identity.side)"])
    }
}
