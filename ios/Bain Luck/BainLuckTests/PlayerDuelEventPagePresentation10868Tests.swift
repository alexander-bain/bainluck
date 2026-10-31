import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the player-duel page presentation (`PlayerDuelEventPagePresentation10868`,
/// `PlayerDuelPageModel10868`). PREPARED, NOT RUN: written and Swift-parsed
/// only; never compiled or executed.
///
/// What is asserted is the page model's rules and the leaf wiring the View
/// builds — which leaves mount, the reader order and return words, the About
/// and value-link rules, the two private display copies of the owner's anchor
/// and the callbacks each leaf receives. Nothing here rasterises a View or
/// claims a rendered fit, an interaction or accessibility.
///
/// Fixtures are `PlayerDuelEventPageFixtures10868` (see
/// `PlayerDuelEventPageHostAdapter10868Tests.swift` for the REAL / CONSTRUCTED
/// labels). Every page input here is a CONSTRUCTED identity-mechanics control
/// over retained NHL events and archived NBA values — never a real page,
/// production, full-range or live evidence.
@MainActor
final class PlayerDuelEventPagePresentation10868Tests: XCTestCase {
    private typealias F = PlayerDuelEventPageFixtures10868
    private typealias A = PlayerDuelEventPageAdapter10868
    private typealias Model = PlayerDuelPageModel10868

    private func pageInput(_ supplied: A.Supplied? = nil, held: A.Held = A.Held()) throws -> PlayerDuelPageInput10868 {
        try XCTUnwrap(A.build(event: try F.finalEvent(), supplied: supplied ?? F.finalSupplied(), now: F.now, held: held))
    }

    /// CONSTRUCTED: a page input whose offered duel is for another phase.
    private func mismatched() throws -> PlayerDuelPageInput10868 {
        let base = try pageInput()
        return PlayerDuelPageInput10868(
            phase: .final, header: base.header, anchor: base.anchor, anchorIsOwners: true,
            duel: F.duel(.before), duelOffered: true, value: base.value, stream: base.stream,
            cards: base.cards, about: base.about, catalogue: base.catalogue,
            catalogueLabels: base.catalogueLabels, catalogueWords: base.catalogueWords)
    }

    // MARK: Mounting and reader order

    func testReaderCardsFollowTheApprovedOrder() throws {
        XCTAssertEqual(Model(try pageInput()).readerCards, [.history, .duel, .value])
        XCTAssertEqual(Model(try pageInput(F.finalSupplied(value: nil))).readerCards, [.history, .duel])
        // CONSTRUCTED: an incomplete pair is not offered, so only the history and value readers remain.
        XCTAssertEqual(Model(try pageInput(F.finalSupplied(duel: F.duel(.final, sides: [F.champagnie()])))).readerCards,
                       [.history, .value])
    }

    func testTheDuelIsMountedOnlyAtThePagesOwnPhase() throws {
        let model = Model(try mismatched())
        XCTAssertNil(model.duel)
        XCTAssertFalse(model.showsStream)
        XCTAssertEqual(model.readerContent(.duel), .unavailable(.duel, name: "Threes head-to-head"))
    }

    func testReaderNeighboursFollowTheOrderAndNeverWrap() throws {
        let model = Model(try pageInput())
        XCTAssertNil(model.neighbours(.history).previous)
        XCTAssertEqual(model.neighbours(.history).next, .duel)
        XCTAssertEqual(model.neighbours(.value).previous, .duel)
        XCTAssertNil(model.neighbours(.value).next)
        XCTAssertEqual(model.name(.history), "Game win probability")
        XCTAssertEqual(model.name(.value), "Market value history")
    }

    func testAWithdrawnCardNamesItselfAndNoOtherCard() throws {
        let model = Model(try pageInput(F.finalSupplied(duel: nil, value: nil)))
        XCTAssertEqual(model.readerContent(.history), .card(.history))
        XCTAssertEqual(model.readerContent(.duel), .unavailable(.duel, name: "Threes head-to-head"))
        XCTAssertEqual(model.readerContent(.value), .unavailable(.value, name: "Market value history"))
    }

    func testCloseWordsArePageChrome() {
        XCTAssertEqual(Model.closeLabel(.reader(.history)), "Back to game")
        XCTAssertEqual(Model.closeLabel(.reader(.value)), "Back to game")
        XCTAssertEqual(Model.closeLabel(.original), "Done")
        XCTAssertEqual(Model.closeLabel(.about), "Done")
        XCTAssertEqual(Model.closeLabel(.page), "Done")
    }

    // MARK: Page controls

    func testAboutEntryOnlyOnThePageAndTheHistoryReader() throws {
        let model = Model(try pageInput())
        XCTAssertTrue(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.history), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .reader(.duel), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .reader(.value), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .original, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .about, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: false), "no opener, no entry")
    }

    func testTheValueLinkNeedsAValueInputOwnerWordsAndAnOpener() throws {
        XCTAssertTrue(Model(try pageInput()).valueLinkAvailable(canOpen: true))
        XCTAssertFalse(Model(try pageInput()).valueLinkAvailable(canOpen: false))
        XCTAssertFalse(Model(try pageInput(F.finalSupplied(value: nil))).valueLinkAvailable(canOpen: true))
    }

    /// CONSTRUCTED: the same bundle with the owner's value-link words removed.
    private func withoutLinkWords(_ supplied: A.Supplied) -> A.Supplied {
        var words = supplied.cards
        words.valueLink = nil
        return A.Supplied(eventID: supplied.eventID, phase: supplied.phase, header: supplied.header,
                          anchor: supplied.anchor, duel: supplied.duel, value: supplied.value, cards: words,
                          about: supplied.about, catalogue: supplied.catalogue,
                          catalogueLabels: supplied.catalogueLabels, catalogueWords: supplied.catalogueWords,
                          routes: supplied.routes)
    }

    func testTheValueLinkSitsInTheDuelCardOrOnThePageOrNowhereAndOpensTheValueReader() throws {
        var opened: [PlayerDuelPageCard10868] = []
        var session = A.Session()
        let opener: (PlayerDuelPageCard10868) -> Void = { card in
            opened.append(card)
            session.openReader(card)
        }
        // CONSTRUCTED: one player withdrawn, so no duel is offered.
        let single = F.duel(.final, sides: [F.champagnie()])

        // WHEN the duel is offered: its in-card link only — no duplicate on the page.
        let withDuel = PlayerDuelEventPagePresentation10868(input: try pageInput(), onOpenReader: opener)
        XCTAssertEqual(Model(withDuel.input).valueLinkPlacement(canOpen: true), .inDuelCard)
        XCTAssertNil(withDuel.valueLinkAction(at: .onPage, activation: nil))
        try XCTUnwrap(withDuel.valueLinkAction(at: .inDuelCard, activation: nil))()
        XCTAssertEqual(opened, [.value])
        XCTAssertEqual(session.mode, .reader(.value))
        session.close()
        opened = []

        // WHEN a value input exists but no duel is offered: the same owner link directly on the page.
        let noDuel = PlayerDuelEventPagePresentation10868(input: try pageInput(F.finalSupplied(duel: single)),
                                                          onOpenReader: opener)
        XCTAssertNil(Model(noDuel.input).duel)
        XCTAssertEqual(Model(noDuel.input).valueLinkPlacement(canOpen: true), .onPage)
        XCTAssertNil(noDuel.valueLinkAction(at: .inDuelCard, activation: nil))
        try XCTUnwrap(noDuel.valueLinkAction(at: .onPage, activation: nil))()
        XCTAssertEqual(opened, [.value])
        XCTAssertEqual(session.mode, .reader(.value), "it opens the value reader")
        XCTAssertTrue(noDuel.input.stream.cards.isEmpty, "an optional reader entry, never a new stream card")
        session.close()
        opened = []

        // WHEN the value input, the owner's link words or the opener is absent: no control at all.
        let absent = [
            PlayerDuelEventPagePresentation10868(input: try pageInput(F.finalSupplied(duel: single, value: nil)),
                                                 onOpenReader: opener),
            PlayerDuelEventPagePresentation10868(input: try pageInput(F.finalSupplied(value: nil)), onOpenReader: opener),
            PlayerDuelEventPagePresentation10868(input: try pageInput(withoutLinkWords(F.finalSupplied(duel: single))),
                                                 onOpenReader: opener),
            PlayerDuelEventPagePresentation10868(input: try pageInput(withoutLinkWords(F.finalSupplied()))),
            PlayerDuelEventPagePresentation10868(input: try pageInput(F.finalSupplied(duel: single))),
        ]
        for page in absent {
            XCTAssertEqual(Model(page.input).valueLinkPlacement(canOpen: page.onOpenReader != nil), .absent)
            XCTAssertNil(page.valueLinkAction(at: .onPage, activation: nil))
            XCTAssertNil(page.valueLinkAction(at: .inDuelCard, activation: nil))
            XCTAssertNil(page.valueLinkAction(at: .absent, activation: nil))
        }
        XCTAssertEqual(opened, [])
        XCTAssertNil(session.mode)
    }

    func testTheCatalogueAndStreamAppearOnlyWithTheirOwnerInputs() throws {
        let model = Model(try pageInput())
        XCTAssertTrue(model.showsCatalogue)
        XCTAssertTrue(model.showsStream)
        var supplied = F.finalSupplied()
        supplied.catalogueWords = nil
        XCTAssertFalse(Model(try pageInput(supplied)).showsCatalogue)
    }

    // MARK: Private display copies (guards against silently dropped owner fields)

    func testTheReaderCopyRemovesOnlyTheExpandSlot() {
        let owner = F.anchor()
        let copy = Model.readerAnchor(owner)
        XCTAssertNil(copy.expand)
        XCTAssertEqual(copy, F.anchor(expand: nil), "every other field — including each non-default var — is the owner's")
        XCTAssertEqual(copy.layout, .focused)
        XCTAssertEqual(copy.probabilityLowerBound, 0.2)
        XCTAssertEqual(copy.probabilityRangeExplanation, "Zoomed probability range · 20–100%")
        XCTAssertEqual(copy.inspectionRingShape, .triangle)
        XCTAssertEqual(copy.showsKey, false)
        XCTAssertNotNil(copy.selectedReadout)
        XCTAssertNotNil(copy.plotAbsence)
    }

    func testTheExpandOnlyCopyKeepsEveryOwnerFieldAndDisablesOnlyTheOtherActions() {
        let owner = F.anchor()
        let copy = Model.expandOnlyAnchor(owner)
        // Non-action fields, field for field.
        XCTAssertEqual(copy.title, owner.title)
        XCTAssertEqual(copy.caption, owner.caption)
        XCTAssertEqual(copy.selection, owner.selection)
        XCTAssertEqual(copy.domain, owner.domain)
        XCTAssertEqual(copy.ceiling, owner.ceiling)
        XCTAssertEqual(copy.yTicks, owner.yTicks)
        XCTAssertEqual(copy.xTicks, owner.xTicks)
        XCTAssertEqual(copy.guides, owner.guides)
        XCTAssertEqual(copy.breaks, owner.breaks)
        XCTAssertEqual(copy.readout, owner.readout)
        XCTAssertEqual(copy.markKey, owner.markKey)
        XCTAssertEqual(copy.comparisonExplanation, owner.comparisonExplanation)
        XCTAssertEqual(copy.notes, owner.notes)
        XCTAssertEqual(copy.summary, owner.summary)
        XCTAssertEqual(copy.plotHeight, owner.plotHeight)
        XCTAssertEqual(copy.unboundReadingWords, owner.unboundReadingWords)
        XCTAssertEqual(copy.plotUnavailableWords, owner.plotUnavailableWords)
        XCTAssertEqual(copy.inspection, owner.inspection)
        XCTAssertEqual(copy.layout, owner.layout)
        XCTAssertEqual(copy.probabilityLowerBound, owner.probabilityLowerBound)
        XCTAssertEqual(copy.probabilityRangeExplanation, owner.probabilityRangeExplanation)
        XCTAssertEqual(copy.selectedReadout, owner.selectedReadout)
        XCTAssertEqual(copy.inspectionRingShape, owner.inspectionRingShape)
        XCTAssertEqual(copy.plotAbsence, owner.plotAbsence)
        XCTAssertEqual(copy.showsKey, owner.showsKey)
        // The expand slot is the owner's, unchanged.
        XCTAssertEqual(copy.expand, owner.expand)
        // Every series field, apart from its choose action's availability.
        XCTAssertEqual(copy.series.count, owner.series.count)
        for (shown, own) in zip(copy.series, owner.series) {
            XCTAssertEqual(shown.id, own.id)
            XCTAssertEqual(shown.name, own.name)
            XCTAssertEqual(shown.shape, own.shape)
            XCTAssertEqual(shown.tint, own.tint)
            XCTAssertEqual(shown.runs, own.runs)
            XCTAssertEqual(shown.links, own.links)
            XCTAssertEqual(shown.labelPointID, own.labelPointID)
            XCTAssertEqual(shown.before, own.before)
            XCTAssertEqual(shown.recorded, own.recorded)
            XCTAssertEqual(shown.absentWords, own.absentWords)
            XCTAssertEqual(shown.keyContext, own.keyContext)
            XCTAssertNotNil(shown.keyContext, "a non-default keyContext survives")
            XCTAssertEqual(shown.choose?.id, own.choose?.id)
            XCTAssertEqual(shown.choose?.label, own.choose?.label)
            XCTAssertEqual(shown.choose?.spokenLabel, own.choose?.spokenLabel)
            XCTAssertEqual(shown.choose?.isAvailable, false)
        }
        // Windows keep their group, order and held choice.
        XCTAssertEqual(copy.windows?.groupLabel, owner.windows?.groupLabel)
        XCTAssertEqual(copy.windows?.choices.map(\.isSelected), owner.windows?.choices.map(\.isSelected))
        // The same actions in the same order and words; only expand stays available.
        let shownActions = FieldHistoryGeometry10868.actions(copy)
        let ownActions = FieldHistoryGeometry10868.actions(owner)
        XCTAssertEqual(shownActions.map(\.id), ownActions.map(\.id))
        XCTAssertEqual(shownActions.map(\.label), ownActions.map(\.label))
        XCTAssertEqual(shownActions.map(\.spokenLabel), ownActions.map(\.spokenLabel))
        for action in shownActions {
            XCTAssertEqual(action.isAvailable, action.id == F.expandAction.id, action.id)
        }
    }

    // MARK: Leaf wiring

    func testWithoutHostRoutesTheAnchorIsTheOwnersAndStatic() throws {
        let page = PlayerDuelEventPagePresentation10868(input: try pageInput())
        let shown = page.historyContent(reader: false)
        XCTAssertEqual(shown.input, F.anchor())
        XCTAssertNil(shown.onAction)
        XCTAssertNil(shown.onInspectionChoice)
        XCTAssertNil(shown.onPlotPosition)
        let reader = page.historyContent(reader: true)
        XCTAssertNil(reader.input.expand)
        XCTAssertNil(reader.onAction)
    }

    func testTheHostsRoutedAnchorIsDrawnAsGiven() throws {
        let input = try pageInput()
        let spy = F.Spy()
        let routed = A.anchorDisplay(input, reader: false, controls: F.controls(spy), hold: { spy.hold() },
                                     openHistory: { spy.open() })
        let page = PlayerDuelEventPagePresentation10868(input: input, pageAnchor: routed)
        let shown = page.historyContent(reader: false)
        XCTAssertEqual(shown.input, routed.input)
        try XCTUnwrap(shown.onAction)("constructed:scale")
        XCTAssertEqual(spy.events, ["hold", "owner:constructed:scale"])
    }

    func testLeavesGetDetailsOnlyWhenTheHostOffersThem() throws {
        let input = try pageInput(held: A.Held(selectedOriginalID: F.champagnieOriginal))
        let none = PlayerDuelEventPagePresentation10868(input: input)
        XCTAssertNil(none.duelContent()?.onDetails)
        XCTAssertNil(none.valueContent()?.onDetails)
        XCTAssertNil(none.duelContent()?.onSelect)
        var opened: [String] = []
        let offered = PlayerDuelEventPagePresentation10868(input: input,
                                                           onDuelDetails: { opened.append("duel:\($0)") },
                                                           onValueDetails: { opened.append("value:\($0)") })
        try XCTUnwrap(offered.duelContent()?.onDetails)(F.champagnieOriginal)
        try XCTUnwrap(offered.valueContent()?.onDetails)(F.champagnieOriginal)
        XCTAssertEqual(opened, ["duel:\(F.champagnieOriginal)", "value:\(F.champagnieOriginal)"])
        XCTAssertEqual(offered.duelContent()?.input, input.duel)
        XCTAssertEqual(offered.valueContent()?.input, input.value)
    }

    func testAStreamCardActionAsksTheStreamFirst() throws {
        let input = try pageInput()
        var events: [String] = []
        let ref = StoryStreamPresentation10868.CardRef(scope: input.stream.scope, id: PlayerDuelPageCard10868.duel.rawValue)
        let activation = StoryStreamCardActivation10868(
            card: ref, intents: [.interaction(scope: ref.scope, card: ref)],
            send: { intent in events.append(intent == .interaction(scope: ref.scope, card: ref) ? "interaction" : "other") })
        let page = PlayerDuelEventPagePresentation10868(input: input, onDuelSelect: { events.append("select:\($0)") })
        try XCTUnwrap(page.duelContent(activation: activation)?.onSelect)(F.anunobyOriginal)
        XCTAssertEqual(events, ["interaction", "select:\(F.anunobyOriginal)"])
    }

    func testDetailsAreTheExistingViewWithNoRecordedHistory() throws {
        let selection = OriginalMarketDetails9483.Selection(scope: F.scope, identity: F.champagnieIdentity)
        let page = PlayerDuelEventPagePresentation10868(input: try pageInput(), mode: .original, selection: selection)
        let details = page.originalDetailsContent()
        XCTAssertNil(details.recorded)
        XCTAssertNil(details.onHistory)
        XCTAssertEqual(details.catalogue, F.catalogue())
        XCTAssertEqual(details.selection, selection)
    }

    /// Copy pin only: the stable id strings a focus-return owner would rely on.
    func testAccessibilityIdentifiersCarryExactCards() {
        XCTAssertEqual(PlayerDuelPageAccessibilityID10868.card(.duel), "playerDuelPage10868.card.duel")
        XCTAssertEqual(PlayerDuelPageAccessibilityID10868.reader(.value), "playerDuelPage10868.reader.value")
        XCTAssertEqual(PlayerDuelPageAccessibilityID10868.pager(.history), "playerDuelPage10868.pager.history")
    }
}
