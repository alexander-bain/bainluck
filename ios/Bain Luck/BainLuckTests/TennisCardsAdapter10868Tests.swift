import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the tennis match screen's card admission (`TennisCardsAdapter10868`)
/// and its path through the host, the page and the full-size reader, on the
/// REAL retained Davidovich Fokina–Tiafoe final: the detail
/// (`TennisMatchPageAdapter10868Tests.finalDetail`, byte for byte), its history
/// and `/game-markets` (`TennisHistoryAdapter10868Tests.finalHistory`,
/// `TennisOriginalsAdapter10868Tests.finalMarkets`, reduced verbatim subsets).
/// Source paths, sha256 and kept rows are written in those files.
///
/// PREPARED, NOT RUN: written under a source-only hold (no build, no XCTest).
///
/// NO PRODUCTION OWNER SUPPLIES A TENNIS CARD TODAY. Every `Supplied` here is
/// CONSTRUCTED owner proof, labelled where it is built:
///   - the handicap panels name the retained final's three real handicap
///     originals by their served ids (polymarket 65123150 / 244876662, 65123149 /
///     244876660, 65149801 / 244973047); their subject, predicate, condition,
///     actual words, headings and card words are constructed;
///   - the sets, totals and exact card inputs are the composed screen's own
///     constructed fixtures (`TennisEventPagePresentation10868Tests.sets` /
///     `.totals` / `.exact`), and the routes map their leaf ids to real catalogue
///     identities of the same final (set 1 · 65138603 / 244929341, total games
///     22.5 Over · 65123147 / 244876655, exact "wins 2-1" · kalshi 65129363 /
///     244894447);
///   - the Details-availability tests route every shown original of those
///     fixtures to its real catalogue original by served id (final: set 1 and 2
///     winners · 65138603 / 65138604, total games · 65123147, exact match score
///     · kalshi 65129363; live: set 1 winner · 65197795, total games 22.5 / 23.5
///     · 65197799 / 65197800, exact match score · kalshi 65176060), and remove,
///     unroute, mis-side or repeat exactly what each test names.
/// The grades the panels show are the retained body's own served settlement.
@MainActor
final class TennisCardsAdapter10868Tests: XCTestCase {
    private typealias C = TennisCardsAdapter10868
    private typealias Host = TennisEventPageHost10868
    private typealias Fixtures = TennisMatchPageAdapter10868Tests
    private typealias Screen = TennisEventPagePresentation10868Tests
    private typealias Details = OriginalMarketDetails9483

    private let finalScope = "tennis:15327291:final:originals"
    private let setsPlus = Details.Identity(source: "polymarket", market: "65123150", side: "244876662")
    private let tiafoePlus = Details.Identity(source: "polymarket", market: "65123149", side: "244876660")
    private let gamesPlus = Details.Identity(source: "polymarket", market: "65149801", side: "244973047")

    /// CONSTRUCTED owner proof: the three handicap panels of the retained final.
    private func handicaps() -> C.Handicaps {
        func panel(_ identity: Details.Identity, _ subject: String, _ predicate: String,
                   _ condition: String) -> OriginalHandicapCard9483.Panel {
            OriginalHandicapCard9483.Panel(original: identity, subject: subject, predicate: predicate,
                                           condition: condition, actual: .missing("Set count unavailable"),
                                           resultMark: nil, openHint: "Opens the original \(condition) prop.")
        }
        return C.Handicaps(
            groups: [
                OriginalHandicapCard9483.Group(heading: "Win at least one set", panels: [
                    panel(setsPlus, "Davidovich Fokina", "Davidovich Fokina to win at least one set", "+1.5 sets"),
                    panel(tiafoePlus, "Tiafoe", "Tiafoe to win at least one set", "+1.5 sets"),
                ]),
                OriginalHandicapCard9483.Group(heading: "Finish level or ahead on games", panels: [
                    panel(gamesPlus, "Davidovich Fokina", "Davidovich Fokina to finish level or ahead on games",
                          "+0.5 games"),
                ]),
            ],
            words: OriginalHandicapCard9483.Words(
                eyebrow: "HANDICAPS · DIFFERENT UNITS", title: "Set and game handicaps",
                explanationTitle: "How these props work",
                explanation: ["A set handicap counts sets; a game handicap counts games."],
                tapInvitation: "Tap a panel to open its original prop.",
                scopeUnavailable: "Handicap props unavailable in this update",
                panelUnavailable: "Prop unavailable in this update",
                comparisonUnavailable: "Pre-match comparison unavailable for this prop"))
    }

    /// CONSTRUCTED owner proof: all four cards for the final, with routes.
    private func everything() -> C.Supplied {
        C.Supplied(
            eventID: 15327291,
            sets: Screen.sets(.final), totals: Screen.totals(.final), exact: Screen.exact(.final),
            handicaps: handicaps(),
            routes: C.Routes(
                sets: ["65138603:fokina": Details.Identity(source: "polymarket", market: "65138603", side: "244929341")],
                totals: ["65123147:over": Details.Identity(source: "polymarket", market: "65123147", side: "244876655")],
                exact: ["245000002": Details.Identity(source: "kalshi", market: "65129363", side: "244894447")]))
    }

    private func buildFinal(cards: C.Supplied?, reading: Host.Reading = Host.Reading()) throws -> Host.Built {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        return Host.build(event: event, history: try TennisHistoryAdapter10868Tests.finished(),
                          markets: try TennisOriginalsAdapter10868Tests.finished(),
                          probabilityObservedAt: nil, now: Fixtures.finalReadAt.asDate!, cards: cards,
                          reading: reading, calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    // MARK: - Default and identity

    func testNothingSuppliedAdmitsNothingAndTheHostedPageIsUnchanged() throws {
        let event = try Fixtures.detail(Fixtures.finalDetail)
        let none = try buildFinal(cards: nil)
        XCTAssertEqual(C.admit(nil, event: event, phase: .final, originals: none.originals, held: C.Held(),
                               tint: .blue), C.Admitted())
        XCTAssertNil(none.input.sets)
        XCTAssertNil(none.input.totals)
        XCTAssertNil(none.input.exact)
        XCTAssertNil(none.input.handicaps)
        XCTAssertNil(none.input.stream)
        XCTAssertNil(none.cards)
    }

    func testCardsSuppliedForAnotherEventAreNeverAdmitted() throws {
        // CONSTRUCTED: the same cards, said to be built for the live match.
        let owner = everything()
        let foreign = C.Supplied(eventID: 15327807, sets: owner.sets, totals: owner.totals, exact: owner.exact,
                                 handicaps: owner.handicaps, routes: owner.routes)
        let built = try buildFinal(cards: foreign)
        XCTAssertNil(built.input.sets)
        XCTAssertNil(built.input.totals)
        XCTAssertNil(built.input.exact)
        XCTAssertNil(built.input.handicaps)
        XCTAssertNil(built.input.stream)
        XCTAssertNil(built.cards, "no route of another event's cards is kept")
        XCTAssertEqual(built.originals.catalogue?.originals.count, 18, "All props is unaffected")
    }

    // MARK: - Admission on the retained final

    func testTheFinalAdmitsTheOwnersHandicapsOnThePagesOwnCatalogueAndOffersThem() throws {
        let built = try buildFinal(cards: C.Supplied(eventID: 15327291, handicaps: handicaps()))
        let card = try XCTUnwrap(built.input.handicaps)
        XCTAssertEqual(card.input.phase, .final)
        XCTAssertEqual(card.input.catalogue, built.originals.catalogue, "the page's own Details, never a second model")
        XCTAssertNil(card.input.held)
        let stream = try XCTUnwrap(built.input.stream)
        XCTAssertEqual(stream.cards.map(\.id), ["handicaps"])
        XCTAssertEqual(stream.cards.map(\.name), ["Set and game handicaps"])
        XCTAssertEqual(built.input.stories.map(\.card), [.handicaps])

        // Each panel shows its original's own grade from the retained settlement,
        // and a pre-match slot the served final does not fill.
        for panel in OriginalHandicapCard9483.panels(card.input) {
            guard case .shown(let shown)? = OriginalHandicapCard9483.state(panel, in: card.input) else {
                return XCTFail("a graded original shows its result")
            }
            XCTAssertEqual(shown.result.words, "Won")
            XCTAssertEqual(shown.result.provenance, "Settled by Polymarket")
            XCTAssertEqual(shown.chance.text, "Pre-match chance unavailable")
            XCTAssertFalse(shown.chance.isValue)
        }
    }

    func testACardInAnotherPhaseIsNeverOffered() throws {
        // The live match: the final-only handicap card (no during-play opt-in) and
        // a final set card are both supplied for this event.
        let event = try Fixtures.detail(Fixtures.liveDetail)
        let built = Host.build(
            event: event, history: try TennisHistoryAdapter10868Tests.live(),
            markets: try TennisOriginalsAdapter10868Tests.live(),
            probabilityObservedAt: event.heroProbabilityObservedAt?.asDate, now: Fixtures.liveReadAt.asDate!,
            cards: C.Supplied(eventID: 15327807, sets: Screen.sets(.final), handicaps: handicaps()),
            calendar: Fixtures.pacific, locale: Fixtures.locale)
        XCTAssertEqual(built.input.phase, .during)
        XCTAssertNil(built.input.sets, "a final set card is never offered during play")
        XCTAssertNil(built.input.handicaps, "the handicap card shows during play only on its owner's opt-in")
        XCTAssertNil(built.input.stream)
    }

    // MARK: - Held selection and Details, host → page → reader

    func testTheHeldSelectionIsMarkedAndAPanelTapOpensItsExactDetailsFromThePageAndTheReader() throws {
        let held = Details.Selection(scope: finalScope, identity: setsPlus)
        let built = try buildFinal(cards: C.Supplied(eventID: 15327291, handicaps: handicaps()),
                                   reading: Host.Reading(selection: held))
        let card = try XCTUnwrap(built.input.handicaps)
        XCTAssertEqual(card.input.held, held, "the host's held catalogue selection reaches the card")
        let panels = OriginalHandicapCard9483.panels(card.input)
        XCTAssertTrue(OriginalHandicapCard9483.isSelected(panels[0], in: card.input))
        XCTAssertFalse(OriginalHandicapCard9483.isSelected(panels[1], in: card.input))

        var chosen: [Details.Selection] = []
        for mode in [TennisEventPageMode10868.page, .reader(.handicaps)] {
            let screen = TennisEventPagePresentation10868(
                input: built.input, mode: mode, originals: built.originals,
                onHandicapSelect: { chosen.append($0) })
            XCTAssertTrue(TennisEventPageModel10868(built.input).readerShows(.handicaps))
            let view = try XCTUnwrap(screen.handicapsContent())
            let tap = try XCTUnwrap(OriginalHandicapCard9483.action(panels[1], in: view.input, onSelect: view.onSelect))
            tap()
        }
        let tiafoe = Details.Selection(scope: finalScope, identity: tiafoePlus)
        XCTAssertEqual(chosen, [tiafoe, tiafoe], "the panel's exact selection, from the page and from the reader")

        // The host admits it only inside its own catalogue, then holds and opens it.
        XCTAssertEqual(C.handicapSelection(tiafoe, in: built.originals), tiafoe)
        XCTAssertNil(C.handicapSelection(Details.Selection(scope: "tennis:15327807:during:originals", identity: tiafoePlus),
                                         in: built.originals), "another scope is never opened in its place")
        let opened = try buildFinal(cards: C.Supplied(eventID: 15327291, handicaps: handicaps()),
                                    reading: Host.Reading(selection: tiafoe))
        XCTAssertEqual(Details.original(in: opened.originals.catalogue, selection: opened.originals.selection)?.outcome,
                       "Frances Tiafoe")
        XCTAssertNotNil(TennisEventPagePresentation10868(input: opened.input, mode: .original,
                                                         originals: opened.originals).originalDetailsContent())
        XCTAssertEqual(opened.input.handicaps?.input.held, tiafoe)
    }

    func testOwnerRoutesOpenOnlyTheirExactCatalogueOriginal() throws {
        let built = try buildFinal(cards: everything())
        XCTAssertEqual(built.input.stream?.cards.map(\.id), ["sets", "totals", "exact", "handicaps"])
        let originals = built.originals

        let total = Details.Selection(scope: finalScope,
                                      identity: Details.Identity(source: "polymarket", market: "65123147", side: "244876655"))
        XCTAssertEqual(C.totalDetails("65123147:over", supplied: built.cards, originals: originals), total)
        XCTAssertNil(C.totalDetails("65123148:over", supplied: built.cards, originals: originals), "an unrouted id opens nothing")
        XCTAssertEqual(C.setDetails("65138603:fokina", supplied: built.cards, originals: originals)?.identity.market, "65138603")
        XCTAssertNil(C.setDetails("65138604:tiafoe", supplied: built.cards, originals: originals))

        let exact = Details.Selection(scope: finalScope,
                                      identity: Details.Identity(source: "kalshi", market: "65129363", side: "244894447"))
        XCTAssertEqual(C.exactDetails(scopeID: "exact:15327291", originalID: "245000002", mounted: built.input.exact,
                                      supplied: built.cards, originals: originals), exact)
        XCTAssertNil(C.exactDetails(scopeID: "exact:other", originalID: "245000002", mounted: built.input.exact,
                                    supplied: built.cards, originals: originals), "only inside the card's own scope")
        XCTAssertNil(C.selection(Details.Identity(source: "kalshi", market: "65129363", side: "999"), in: originals),
                     "an identity the catalogue does not hold opens nothing")

        // An id that resolves nothing is never OFFERED either: this owner routes
        // one of the four shown set chances, so the set card offers no Details
        // control at all, while the routed totals and exact Details stay offered.
        let controls = Host.detailsControls(built) { _ in }
        XCTAssertNil(controls.sets, "no dead set control for the three unrouted chances")
        XCTAssertNotNil(controls.totals)
        XCTAssertNotNil(controls.exact)
    }

    // MARK: - The host's held choices

    func testTheHostsHeldChoicesApplyOverTheOwnersSelection() throws {
        guard case .thresholds(let live) = C.holding(Screen.totals(.during), milestone: "245152786") else {
            return XCTFail("the thresholds variant stays the thresholds variant")
        }
        XCTAssertEqual(live.profile.selectedMilestoneID, "245152786")
        XCTAssertEqual(C.holding(Screen.totals(.during), milestone: nil), Screen.totals(.during),
                       "nothing held keeps the owner's own selection")

        guard case .final(let tiles) = C.holding(Screen.exact(.final), scope: "exact:15327291", original: "245000004") else {
            return XCTFail("the final tiles stay the final tiles")
        }
        XCTAssertEqual(tiles.map.selectedOriginalID, "245000004")
        XCTAssertEqual(tiles.map.selectedScopeID, "exact:15327291")
        XCTAssertEqual(C.holding(Screen.exact(.during), scope: "exact:15327807", original: "245059339"),
                       Screen.exact(.during), "the lanes hold no selection of their own")

        let built = try buildFinal(cards: everything(),
                                   reading: Host.Reading(cards: C.Held(exactScopeID: "exact:15327291",
                                                                       exactOriginalID: "245000004")))
        guard case .final(let admitted)? = built.input.exact else { return XCTFail("the final exact card is admitted") }
        XCTAssertEqual(admitted.map.selectedOriginalID, "245000004")
    }

    // MARK: - Details availability: what each card OFFERS, page and reader

    private final class Log {
        var lines: [String] = []
    }

    private typealias Control = (name: String, tap: () -> Void)

    private static func pm(_ market: String, _ side: String) -> Details.Identity {
        Details.Identity(source: "polymarket", market: market, side: side)
    }

    private static func kalshi(_ market: String, _ side: String) -> Details.Identity {
        Details.Identity(source: "kalshi", market: market, side: side)
    }

    private static func opened(_ scope: String, _ identity: Details.Identity) -> String {
        "open:\(scope)|\(identity.source):\(identity.market):\(identity.side)"
    }

    private let liveScope = "tennis:15327807:during:originals"

    /// CONSTRUCTED owner proof: every shown original of the final's set, totals
    /// and exact cards routed to its real catalogue original (set 1 · 65138603,
    /// set 2 · 65138604, total games 22.5 · 65123147, exact match score · kalshi
    /// 65129363), each by its served outcome id.
    private func finalRoutes() -> C.Routes {
        C.Routes(
            sets: ["65138603:fokina": Self.pm("65138603", "244929341"), "65138603:tiafoe": Self.pm("65138603", "244929342"),
                   "65138604:fokina": Self.pm("65138604", "244929343"), "65138604:tiafoe": Self.pm("65138604", "244929344")],
            totals: ["65123147:over": Self.pm("65123147", "244876655")],
            exact: ["245000001": Self.kalshi("65129363", "244894445"), "245000002": Self.kalshi("65129363", "244894447"),
                    "245000003": Self.kalshi("65129363", "244894446"), "245000004": Self.kalshi("65129363", "244894448")])
    }

    /// CONSTRUCTED owner proof for the live match: set 1 · 65197795, total
    /// games 22.5 / 23.5 · 65197799 / 65197800, exact match score · kalshi
    /// 65176060, each by its served outcome id.
    private func liveRoutes() -> C.Routes {
        C.Routes(
            sets: ["245152775": Self.pm("65197795", "245152775"), "245152776": Self.pm("65197795", "245152776")],
            totals: ["245152784": Self.pm("65197799", "245152784"), "245152786": Self.pm("65197800", "245152786")],
            exact: ["245059339": Self.kalshi("65176060", "245059339"), "245059341": Self.kalshi("65176060", "245059341"),
                    "245059340": Self.kalshi("65176060", "245059340"), "245059338": Self.kalshi("65176060", "245059338")])
    }

    private func finalCards(_ routes: C.Routes, totals: TennisEventPageTotals10868 = Screen.totals(.final),
                            exact: TennisEventPageExact10868 = Screen.exact(.final)) -> C.Supplied {
        C.Supplied(eventID: 15327291, sets: Screen.sets(.final), totals: totals, exact: exact, routes: routes)
    }

    private func liveCards(_ routes: C.Routes, before: Bool = false,
                           totals: TennisEventPageTotals10868? = nil) -> C.Supplied {
        C.Supplied(eventID: 15327807, sets: Screen.sets(before ? .before : .during),
                   totals: totals ?? Screen.totals(before ? .before : .during),
                   exact: Screen.exact(before ? .before : .during), routes: routes)
    }

    /// The live match during play; `before` is CONSTRUCTED (`status: scheduled`,
    /// `commence_time` 13:00Z, read at 12:24:30Z), as in the history tests.
    private func buildLive(cards: C.Supplied?, reading: Host.Reading = Host.Reading(),
                           before: Bool = false) throws -> Host.Built {
        let event = before
            ? try Fixtures.edited(Fixtures.liveDetail, ["status": "scheduled", "commence_time": "2026-10-12T13:00:00+00:00"])
            : try Fixtures.detail(Fixtures.liveDetail)
        return Host.build(event: event, history: try TennisHistoryAdapter10868Tests.live(),
                          markets: try TennisOriginalsAdapter10868Tests.live(),
                          probabilityObservedAt: event.heroProbabilityObservedAt?.asDate,
                          now: Fixtures.liveReadAt.asDate!, cards: cards, reading: reading,
                          calendar: Fixtures.pacific, locale: Fixtures.locale)
    }

    /// The page (or the reader) exactly as the host wires it: the host's own
    /// Details callbacks for this pass, each open and each page hold logged.
    private func screen(_ built: Host.Built, _ mode: TennisEventPageMode10868, _ log: Log) -> TennisEventPagePresentation10868 {
        let controls = Host.detailsControls(built) { log.lines.append(Self.opened($0.scope, $0.identity)) }
        return TennisEventPagePresentation10868(
            input: built.input, mode: mode, originals: built.originals,
            onSetDetails: controls.sets, onTotalDetails: controls.totals, onExactDetails: controls.exact,
            onInteraction: { log.lines.append("pageHold") })
    }

    /// The stream's hook for the displayed card, its hold logged.
    private func hook(_ built: Host.Built, _ card: TennisEventPageCard10868, _ log: Log) throws -> StoryStreamCardActivation10868 {
        let stream = try XCTUnwrap(built.input.stream)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: card.rawValue)
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let hook = StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, _) = intent { log.lines.append("hold:\(card.rawValue)") }
        }
        XCTAssertTrue(hook.isAvailable, "the card is the one displayed")
        return hook
    }

    private func setControls(_ view: PeriodOutcomeFinalScorePresentation10868?) -> [Control] {
        guard let view else { return [] }
        let can = view.onDetails != nil
        return view.input.periodIndices.flatMap { index in
            view.input.comparison.series.compactMap { one -> Control? in
                guard let action = view.input.detailsAction(one, periodIndex: index, canOpenDetails: can),
                      case .details(let id) = action else { return nil }
                return (name: id, tap: { action.perform(onSelect: nil, onDetails: view.onDetails) })
            }
        }
    }

    private func totalControls(_ action: TotalMilestoneAction10868?, _ callback: ((String) -> Void)?) -> [Control] {
        guard let action, case .details(let id) = action else { return [] }
        return [(name: id, tap: { action.perform(onSelect: nil, onDetails: callback) })]
    }

    private func exactControls(_ actions: [ExactScoreMapAction10868?], _ callback: ((String, String) -> Void)?) -> [Control] {
        actions.compactMap { action -> Control? in
            guard let action, case .details(let scope, let id) = action else { return nil }
            return (name: "\(scope)/\(id)", tap: {
                ExactScoreFinishRouting10868.route(action, onSelectOriginal: nil, onDetails: callback, onRecoverSelection: nil)
            })
        }
    }

    /// The Details controls one shown card DRAWS — each the leaf's own action,
    /// decided by the leaf from its input and the callback the host handed it.
    private func controls(_ card: TennisEventPageCard10868, on screen: TennisEventPagePresentation10868,
                          hook: StoryStreamCardActivation10868?) -> [Control] {
        switch card {
        case .sets:
            return setControls(screen.setsContent(activation: hook))
        case .totals:
            if let line = screen.finalTotalsContent(activation: hook) {
                return totalControls(line.input.detailsAction(canOpenDetails: line.onDetails != nil), line.onDetails)
            }
            if let live = screen.thresholdTotalsContent(activation: hook) {
                return totalControls(live.input.detailsAction(canOpenDetails: live.onDetails != nil), live.onDetails)
            }
            return []
        case .exact:
            if let tiles = screen.finalExactContent(activation: hook) {
                return exactControls([tiles.input.detailsAction(canOpen: tiles.onDetails != nil)], tiles.onDetails)
            }
            if let lanes = screen.laneExactContent(activation: hook) {
                let can = lanes.onDetails != nil
                return exactControls(lanes.input.lanes.map { lanes.input.detailsAction($0, canOpen: can) }
                                     + lanes.input.unplaced.map { lanes.input.detailsAction($0, canOpen: can) },
                                     lanes.onDetails)
            }
            return []
        case .history, .handicaps:
            return []
        }
    }

    /// One card as a person meets it, on the page (in the stream, through its
    /// hook) and in its full-size reader, for one supplied payload and held
    /// state: the Details controls drawn in each, and the log after tapping
    /// `tap` on the page and then in the reader.
    private struct Met {
        let page: [String]
        let reader: [String]
        let log: [String]
    }

    private func meet(_ card: TennisEventPageCard10868, reading: Host.Reading = Host.Reading(), tap: String? = nil,
                      build: (Host.Reading) throws -> Host.Built) throws -> Met {
        let log = Log()
        var onPage = reading
        onPage.story = card
        onPage.readerOpen = false
        var inReader = onPage
        inReader.readerOpen = true
        let pageBuilt = try build(onPage)
        let readerBuilt = try build(inReader)
        XCTAssertTrue(TennisEventPageModel10868(pageBuilt.input).isMounted(card), "the card stays on the page")
        XCTAssertTrue(TennisEventPageModel10868(readerBuilt.input).readerShows(card), "and in its reader")
        let pageHook = try hook(pageBuilt, card, log)
        let page = controls(card, on: screen(pageBuilt, .page, log), hook: pageHook)
        let reader = controls(card, on: screen(readerBuilt, .reader(card), log), hook: nil)
        XCTAssertEqual(log.lines, [], "drawing the page and the reader asks for nothing")
        if let tap {
            page.first { $0.name == tap }?.tap()
            log.lines.append("reader")
            reader.first { $0.name == tap }?.tap()
        }
        return Met(page: page.map { $0.name }, reader: reader.map { $0.name }, log: log.lines)
    }

    // MARK: Offered and exact

    func testEveryShownFinalOriginalThatResolvesOffersDetailsAndOpensExactlyItHeldOnceOnThePageAndUnheldInTheReader() throws {
        let build = { (reading: Host.Reading) in try self.buildFinal(cards: self.finalCards(self.finalRoutes()), reading: reading) }

        let sets = try meet(.sets, tap: "65138604:tiafoe", build: build)
        XCTAssertEqual(sets.page, ["65138603:fokina", "65138603:tiafoe", "65138604:fokina", "65138604:tiafoe"])
        XCTAssertEqual(sets.reader, sets.page)
        let tiafoeSet2 = Self.opened(finalScope, Self.pm("65138604", "244929344"))
        XCTAssertEqual(sets.log, ["hold:sets", tiafoeSet2, "reader", tiafoeSet2],
                       "that chance's own original — never its set's other side — with one hold on the page, none in the reader")

        // The final line variant: Details for the shown milestone.
        let totals = try meet(.totals, tap: "65123147:over", build: build)
        XCTAssertEqual(totals.page, ["65123147:over"])
        XCTAssertEqual(totals.reader, ["65123147:over"])
        let over = Self.opened(finalScope, Self.pm("65123147", "244876655"))
        XCTAssertEqual(totals.log, ["hold:totals", over, "reader", over])

        // The finish tiles: Details for the shown finish, and after the reader
        // holds another finish, for that finish exactly.
        let exact = try meet(.exact, tap: "exact:15327291/245000002", build: build)
        XCTAssertEqual(exact.page, ["exact:15327291/245000002"])
        XCTAssertEqual(exact.reader, exact.page)
        let wins21 = Self.opened(finalScope, Self.kalshi("65129363", "244894447"))
        XCTAssertEqual(exact.log, ["hold:exact", wins21, "reader", wins21])

        let held = try meet(.exact, reading: Host.Reading(cards: C.Held(exactScopeID: "exact:15327291", exactOriginalID: "245000004")),
                            tap: "exact:15327291/245000004", build: build)
        XCTAssertEqual(held.page, ["exact:15327291/245000004"])
        let tiafoe21 = Self.opened(finalScope, Self.kalshi("65129363", "244894448"))
        XCTAssertEqual(held.log, ["hold:exact", tiafoe21, "reader", tiafoe21])
    }

    func testBeforeAndDuringPlayTheThresholdsLanesAndSetsOfferEachResolvedOriginal() throws {
        for before in [false, true] {
            let build = { (reading: Host.Reading) in
                try self.buildLive(cards: self.liveCards(self.liveRoutes(), before: before), reading: reading, before: before)
            }
            let built = try build(Host.Reading())
            XCTAssertEqual(built.input.phase, before ? TennisEventPagePhase10868.before : .during)
            let scope = try XCTUnwrap(built.originals.catalogue?.scope)
            if !before { XCTAssertEqual(scope, liveScope) }

            // The threshold variant: the owner's selected milestone, then the
            // reader's held one — each opens its own original.
            let owner = try meet(.totals, tap: "245152784", build: build)
            XCTAssertEqual(owner.page, ["245152784"])
            XCTAssertEqual(owner.reader, ["245152784"])
            let line225 = Self.opened(scope, Self.pm("65197799", "245152784"))
            XCTAssertEqual(owner.log, ["hold:totals", line225, "reader", line225])
            let held = try meet(.totals, reading: Host.Reading(cards: C.Held(totalMilestoneID: "245152786")),
                                tap: "245152786", build: build)
            XCTAssertEqual(held.page, ["245152786"])
            let line235 = Self.opened(scope, Self.pm("65197800", "245152786"))
            XCTAssertEqual(held.log, ["hold:totals", line235, "reader", line235])

            let lanes = try meet(.exact, tap: "exact:15327807/245059340", build: build)
            XCTAssertEqual(lanes.page, ["exact:15327807/245059339", "exact:15327807/245059341",
                                        "exact:15327807/245059340", "exact:15327807/245059338"])
            XCTAssertEqual(lanes.reader, lanes.page)
            let zandschulp21 = Self.opened(scope, Self.kalshi("65176060", "245059340"))
            XCTAssertEqual(lanes.log, ["hold:exact", zandschulp21, "reader", zandschulp21])

            let sets = try meet(.sets, tap: "245152776", build: build)
            XCTAssertEqual(sets.page, ["245152775", "245152776"])
            XCTAssertEqual(sets.reader, sets.page)
            let zandschulpSet1 = Self.opened(scope, Self.pm("65197795", "245152776"))
            XCTAssertEqual(sets.log, ["hold:sets", zandschulpSet1, "reader", zandschulpSet1])
        }
    }

    // MARK: Never offered

    func testAPartialRouteMapDrawsNoDeadControlKeepsEveryComparisonAndKeepsEveryWorkingRoute() throws {
        // The final: one of four set chances routed (`everything()`).
        let finished = { (reading: Host.Reading) in try self.buildFinal(cards: self.everything(), reading: reading) }
        let sets = try meet(.sets, build: finished)
        XCTAssertEqual(sets.page, [])
        XCTAssertEqual(sets.reader, [])
        let built = try finished(Host.Reading(story: .sets))
        let card = try XCTUnwrap(screen(built, .page, Log()).setsContent())
        XCTAssertEqual(card.input, Screen.sets(.final), "every chance and score is still shown")
        XCTAssertFalse(card.input.notes(canOpenDetails: card.onDetails != nil)
                        .contains("Tap a player for its original outcome and recorded time."),
                       "the card never invites a tap it cannot honour")
        XCTAssertEqual(try meet(.totals, build: finished).page, ["65123147:over"], "a working route on another card stays")
        XCTAssertEqual(try meet(.exact, build: finished).page, ["exact:15327291/245000002"])

        // During and before play: totals route only the 23.5 milestone, lanes
        // three of four finishes.
        var partial = liveRoutes()
        partial.totals["245152784"] = nil
        partial.exact["245059338"] = nil
        for before in [false, true] {
            let live = { (reading: Host.Reading) in
                try self.buildLive(cards: self.liveCards(partial, before: before), reading: reading, before: before)
            }
            XCTAssertEqual(try meet(.totals, build: live).page, [], "the owner's 22.5 selection is unrouted")
            XCTAssertEqual(try meet(.totals, build: live).reader, [])
            XCTAssertEqual(try meet(.totals, reading: Host.Reading(cards: C.Held(totalMilestoneID: "245152786")),
                                    build: live).page, ["245152786"], "the routed milestone keeps its Details")
            let lanes = try meet(.exact, build: live)
            XCTAssertEqual(lanes.page, [])
            XCTAssertEqual(lanes.reader, [])
            let shown = try XCTUnwrap(screen(try live(Host.Reading(story: .exact)), .page, Log()).laneExactContent())
            XCTAssertEqual(shown.input.lanes.count, 4, "every lane is still shown")
            XCTAssertEqual(try meet(.sets, build: live).page, ["245152775", "245152776"])
        }
    }

    func testUnroutedIdsOfferNoDetails() throws {
        // CONSTRUCTED: no routes at all, then routes only for ids no card shows.
        let elsewhere = C.Routes(
            sets: ["65138605:fokina": Self.pm("65138603", "244929341")],
            totals: ["65123148:over": Self.pm("65123147", "244876655")],
            exact: ["245000009": Self.kalshi("65129363", "244894447")])
        for routes in [C.Routes(), elsewhere] {
            let build = { (reading: Host.Reading) in try self.buildFinal(cards: self.finalCards(routes), reading: reading) }
            for card in [TennisEventPageCard10868.sets, .totals, .exact] {
                let met = try meet(card, build: build)
                XCTAssertEqual(met.page, [], "\(card)")
                XCTAssertEqual(met.reader, [], "\(card)")
            }
        }
    }

    func testARouteToAnOriginalTheCatalogueDoesNotHoldOffersNoDetails() throws {
        // CONSTRUCTED: every route names the right market with a side it never served.
        func absent(_ map: [String: Details.Identity]) -> [String: Details.Identity] {
            map.mapValues { Details.Identity(source: $0.source, market: $0.market, side: "999\($0.side)") }
        }
        let full = finalRoutes()
        let missing = C.Routes(sets: absent(full.sets), totals: absent(full.totals), exact: absent(full.exact))
        let build = { (reading: Host.Reading) in try self.buildFinal(cards: self.finalCards(missing), reading: reading) }
        for card in [TennisEventPageCard10868.sets, .totals, .exact] {
            let met = try meet(card, build: build)
            XCTAssertEqual(met.page, [], "\(card)")
            XCTAssertEqual(met.reader, [], "\(card)")
        }

        // One lane's route names nothing the live catalogue holds.
        var oneAbsent = liveRoutes()
        oneAbsent.exact["245059341"] = Self.kalshi("65176060", "999")
        let live = { (reading: Host.Reading) in try self.buildLive(cards: self.liveCards(oneAbsent), reading: reading) }
        XCTAssertEqual(try meet(.exact, build: live).page, [])
        XCTAssertEqual(try meet(.exact, build: live).reader, [])
    }

    func testARouteToAnOriginalTheCatalogueHoldsTwiceOffersNoDetails() throws {
        // CONSTRUCTED: the final's catalogue repeating the routed set-2 Tiafoe,
        // 22.5 Over and "wins 2-1" originals, so none of them is exactly one.
        let twice: Set<Details.Identity> = [Self.pm("65138604", "244929344"), Self.pm("65123147", "244876655"),
                                            Self.kalshi("65129363", "244894447")]
        let build = { (reading: Host.Reading) -> Host.Built in
            let built = try self.buildFinal(cards: self.finalCards(self.finalRoutes()), reading: reading)
            let catalogue = try XCTUnwrap(built.originals.catalogue)
            let o = built.originals
            let doubled = TennisEventPageOriginals10868(
                catalogue: Details.Catalogue(scope: catalogue.scope,
                                             originals: catalogue.originals + catalogue.originals.filter { twice.contains($0.identity) }),
                selection: o.selection, recorded: o.recorded, labels: o.labels, heading: o.heading, context: o.context,
                emptyWords: o.emptyWords, unavailableChoice: o.unavailableChoice, tint: o.tint)
            return Host.Built(input: built.input, originals: doubled, series: built.series, cards: built.cards)
        }
        for card in [TennisEventPageCard10868.sets, .totals, .exact] {
            let met = try meet(card, build: build)
            XCTAssertEqual(met.page, [], "\(card)")
            XCTAssertEqual(met.reader, [], "\(card)")
        }
    }

    func testAHeldChoiceOmittedThenRestoredClosesThenReopensItsOwnDetails() throws {
        // Totals during play: the reader holds 23.5; the owner's next card omits it.
        let holding23 = Host.Reading(cards: C.Held(totalMilestoneID: "245152786"))
        let omitted = { (reading: Host.Reading) in
            try self.buildLive(cards: self.liveCards(self.liveRoutes(), totals: self.omitting("245152786", from: Screen.totals(.during))),
                               reading: reading)
        }
        let gone = try meet(.totals, reading: holding23, build: omitted)
        XCTAssertEqual(gone.page, [], "never the remaining 22.5 in its place")
        XCTAssertEqual(gone.reader, [])
        let restored = { (reading: Host.Reading) in try self.buildLive(cards: self.liveCards(self.liveRoutes()), reading: reading) }
        let back = try meet(.totals, reading: holding23, tap: "245152786", build: restored)
        XCTAssertEqual(back.page, ["245152786"])
        let line235 = Self.opened(liveScope, Self.pm("65197800", "245152786"))
        XCTAssertEqual(back.log, ["hold:totals", line235, "reader", line235])

        // The finish tiles: the reader holds "Tiafoe wins 2-1"; the owner's next card omits it.
        let holding = Host.Reading(cards: C.Held(exactScopeID: "exact:15327291", exactOriginalID: "245000004"))
        let tilesGone = { (reading: Host.Reading) in
            try self.buildFinal(cards: self.finalCards(self.finalRoutes(), exact: self.omitting("245000004", from: Screen.exact(.final))),
                                reading: reading)
        }
        let finishGone = try meet(.exact, reading: holding, build: tilesGone)
        XCTAssertEqual(finishGone.page, [], "never the owner's 2-1 in its place")
        XCTAssertEqual(finishGone.reader, [])
        let tilesBack = { (reading: Host.Reading) in try self.buildFinal(cards: self.finalCards(self.finalRoutes()), reading: reading) }
        let finishBack = try meet(.exact, reading: holding, tap: "exact:15327291/245000004", build: tilesBack)
        XCTAssertEqual(finishBack.page, ["exact:15327291/245000004"])
        let tiafoe21 = Self.opened(finalScope, Self.kalshi("65129363", "244894448"))
        XCTAssertEqual(finishBack.log, ["hold:exact", tiafoe21, "reader", tiafoe21])
    }

    func testAnExactFinishOutsideTheCardsOwnScopeOffersNoDetails() throws {
        let build = { (reading: Host.Reading) in try self.buildFinal(cards: self.finalCards(self.finalRoutes()), reading: reading) }
        // The reader's held finish names the live match's scope.
        let foreign = try meet(.exact, reading: Host.Reading(cards: C.Held(exactScopeID: "exact:15327807", exactOriginalID: "245000002")),
                               build: build)
        XCTAssertEqual(foreign.page, [])
        XCTAssertEqual(foreign.reader, [])

        // An offered callback still opens nothing for a scope that is not the card's own.
        var opened: [Details.Selection] = []
        let controls = Host.detailsControls(try build(Host.Reading())) { opened.append($0) }
        controls.exact?("exact:15327807", "245000002")
        XCTAssertEqual(opened, [])
        controls.exact?("exact:15327291", "245000002")
        XCTAssertEqual(opened, [Details.Selection(scope: finalScope, identity: Self.kalshi("65129363", "244894447"))])
    }

    // MARK: Constructed omissions

    /// The owner's thresholds card with one milestone no longer offered: CONSTRUCTED.
    private func omitting(_ id: String, from totals: TennisEventPageTotals10868) -> TennisEventPageTotals10868 {
        guard case .thresholds(let live) = totals else { return totals }
        let p = live.profile
        return .thresholds(TotalMilestoneThresholdLiveInput10868(
            profile: TotalMilestoneInput10868(
                phase: p.phase, eyebrow: p.eyebrow, title: p.title, chartTitle: p.chartTitle,
                quantityAxisTitle: p.quantityAxisTitle, milestones: p.milestones.filter { $0.id != id },
                selectedMilestoneID: p.selectedMilestoneID, actual: p.actual, projection: p.projection,
                quantityDomain: p.quantityDomain, quantityTicks: p.quantityTicks, chanceTicks: p.chanceTicks,
                timing: p.timing, markStyle: p.markStyle),
            thresholds: live.thresholds.filter { $0.originalID != id }, subtotals: live.subtotals,
            quantitiesShareUnit: live.quantitiesShareUnit, words: live.words, beforePresentation: live.beforePresentation))
    }

    /// The owner's finish tiles with one finish no longer offered: CONSTRUCTED.
    private func omitting(_ id: String, from exact: TennisEventPageExact10868) -> TennisEventPageExact10868 {
        guard case .final(let tiles) = exact else { return exact }
        let map = tiles.map
        let scopes = map.scopes.map { scope in
            ExactScoreMapScope10868(id: scope.id, label: scope.label, rows: scope.rows, columns: scope.columns,
                                    originals: scope.originals.filter { $0.id != id }, scale: scope.scale,
                                    actual: scope.actual)
        }
        return .final(ExactScoreFinishInput10868(
            map: ExactScoreMapInput10868(
                phase: map.phase, title: map.title, intro: map.intro, homeLabel: map.homeLabel, awayLabel: map.awayLabel,
                rowsTitle: map.rowsTitle, columnsTitle: map.columnsTitle, scopes: scopes,
                selectedScopeID: map.selectedScopeID, selectedOriginalID: map.selectedOriginalID,
                legend: map.legend, words: map.words),
            players: tiles.players.map { player in
                ExactScoreFinishPlayer10868(id: player.id, name: player.name,
                                            tiles: player.tiles.filter { $0.originalID != id })
            },
            words: tiles.words))
    }
}
