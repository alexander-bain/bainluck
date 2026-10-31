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
///     244894447).
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

        // The reader's totals card hands its milestone id to the host unchanged.
        var details: [String] = []
        let reader = TennisEventPagePresentation10868(input: built.input, mode: .reader(.totals), originals: originals,
                                                      onTotalDetails: { details.append($0) })
        try XCTUnwrap(reader.finalTotalsContent()).onDetails?("65123147:over")
        XCTAssertEqual(details, ["65123147:over"])
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
}
