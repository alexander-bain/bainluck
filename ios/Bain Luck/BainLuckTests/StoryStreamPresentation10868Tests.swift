import SwiftUI
import XCTest
@testable import Bain_Luck

/// Prepared, not executed. The five reference frames below are the retained
/// real-game metadata (STORY-STREAM-REFERENCE-CASES.json, sha256 bf940371…):
/// scope, card ids, full names and the approved editorial order, unchanged.
/// Every held / paused / pending / reordered / withdrawn / Reduce Motion
/// state is a CONSTRUCTED owner input — the owner's decision, not evidence of
/// a live game or of production state. No reference reducer is ported.
///
/// NOT_RUN here: native rendering, layout fit, gestures, VoiceOver.
@MainActor
final class StoryStreamPresentation10868Tests: XCTestCase {
    typealias Presentation = StoryStreamPresentation10868
    typealias Ref = StoryStreamPresentation10868.CardRef

    private struct Frame {
        let route: String
        let phase: String
        let scope: String
        let cards: [(id: String, name: String)]
        let approvedOrder: [String]
    }

    private static let teamCards = [(id: "sacks", name: "Quarterback pressure"),
                                    (id: "field-goals", name: "The kicking game")]
    private static let duelCards = [(id: "duel", name: "Threes head-to-head"),
                                    (id: "movement", name: "Market value history")]
    private static let frames = [
        Frame(route: "nfl-team-stats", phase: "Before", scope: "team404:Before", cards: teamCards,
              approvedOrder: ["field-goals", "sacks"]),
        Frame(route: "nfl-team-stats", phase: "During", scope: "team404:During", cards: teamCards,
              approvedOrder: ["field-goals", "sacks"]),
        Frame(route: "nfl-team-stats", phase: "Final", scope: "team404:Final", cards: teamCards,
              approvedOrder: ["field-goals", "sacks"]),
        Frame(route: "player-duel", phase: "before", scope: "player-duel-stream:before", cards: duelCards,
              approvedOrder: ["duel"]),
        Frame(route: "player-duel", phase: "final", scope: "player-duel-stream:final", cards: duelCards,
              approvedOrder: ["duel"]),
    ]

    private final class Recorder {
        var intents: [Presentation.Intent] = []
        func send(_ intent: Presentation.Intent) { intents.append(intent) }
    }

    /// The owner's constructed input for one frame: displaying `primary`, with
    /// the owner's exact Previous/Next targets. Words are the owner's.
    private func presentation(_ frame: Frame, primary: String?, previous: String? = nil, next: String? = nil,
                              companion: String? = nil, wide: Bool = false,
                              playback: Presentation.Playback? = nil) -> Presentation {
        Presentation(scope: frame.scope, eyebrow: "Team milestones", heading: "Explore the story",
                     cards: frame.cards.map { Presentation.Card(id: $0.id, name: $0.name) },
                     primary: primary.map { Ref(scope: frame.scope, id: $0) },
                     companion: companion.map { Ref(scope: frame.scope, id: $0) },
                     companionLabel: "Up next", wide: wide, position: nil, status: nil, pending: nil,
                     nextHint: nil, basis: nil, dwellFraction: nil, playback: playback,
                     previous: previous.map { Ref(scope: frame.scope, id: $0) },
                     next: next.map { Ref(scope: frame.scope, id: $0) })
    }

    // 1
    func testEachReferenceFrameShowsExactlyTheOwnersDisplayedCard() {
        for frame in Self.frames {
            for id in frame.approvedOrder {
                let resolved = presentation(frame, primary: id).resolve(reduceMotion: false, actionable: true)
                let name = frame.cards.first { $0.id == id }!.name
                XCTAssertEqual(resolved.primary, .card(Ref(scope: frame.scope, id: id),
                                                       Presentation.Card(id: id, name: name)), frame.scope)
                XCTAssertNil(resolved.companion, "no companion is elected from the card list: \(frame.scope)")
                XCTAssertNil(resolved.previous)
                XCTAssertNil(resolved.next)
            }
        }
    }

    // 2
    func testCardListOrderNeverChangesTheDisplayedCard() {
        let frame = Self.frames[2]
        var input = presentation(frame, primary: "sacks")
        let before = input.resolve(reduceMotion: false, actionable: true)
        input.cards.reverse()
        input.cards.append(Presentation.Card(id: "extra", name: "Unrelated"))
        let after = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(before.primary, after.primary)
        XCTAssertEqual(after.primary?.card?.name, "Quarterback pressure")
    }

    // 3
    func testWideShowsOnlyTheOwnersExplicitCompanion() {
        let frame = Self.frames[1]
        let none = presentation(frame, primary: "field-goals", wide: true).resolve(reduceMotion: false, actionable: true)
        XCTAssertNil(none.companion, "two cards and wide still elect nothing")
        XCTAssertEqual(Presentation.arrangement(hasCompanion: none.companion != nil, accessibilitySize: false,
                                                companionMinimumWidth: 320), .single)

        let pairedInput = presentation(frame, primary: "field-goals", companion: "sacks", wide: true)
        let paired = pairedInput.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(paired.companion?.card?.name, "Quarterback pressure")
        XCTAssertEqual(Presentation.arrangement(hasCompanion: true, accessibilitySize: false,
                                                companionMinimumWidth: pairedInput.companionMinimumWidth),
                       .pairedIfFits(minimumWidth: 320), "the default pairs at 320")
        XCTAssertEqual(Presentation.arrangement(hasCompanion: true, accessibilitySize: true,
                                                companionMinimumWidth: pairedInput.companionMinimumWidth), .column)

        let narrow = presentation(frame, primary: "field-goals", companion: "sacks", wide: false)
            .resolve(reduceMotion: false, actionable: true)
        XCTAssertNil(narrow.companion, "compact presentation never shows the companion")
        let same = presentation(frame, primary: "sacks", companion: "sacks", wide: true)
            .resolve(reduceMotion: false, actionable: true)
        XCTAssertNil(same.companion, "the displayed card is never drawn twice")
    }

    // 4
    func testPlayerDuelMovementIsNotPromotedIntoTheStream() {
        for frame in Self.frames.filter({ $0.route == "player-duel" }) {
            let input = presentation(frame, primary: "duel", wide: true)
            let resolved = input.resolve(reduceMotion: false, actionable: true)
            XCTAssertEqual(resolved.primary?.card?.name, "Threes head-to-head")
            XCTAssertNil(resolved.companion)
            XCTAssertNil(resolved.next, "one admitted card: no Next, and Movement is not a neighbour")
            let movement = Ref(scope: frame.scope, id: "movement")
            XCTAssertEqual(input.intents(for: .open(movement), resolved: resolved), [])
            XCTAssertEqual(input.intents(for: .open(Ref(scope: frame.scope, id: "duel")), resolved: resolved),
                           [.interaction(scope: frame.scope, card: Ref(scope: frame.scope, id: "duel")),
                            .open(Ref(scope: frame.scope, id: "duel"))])
        }
    }

    // 5
    func testBrowseSendsTheOwnersExactTargetAfterTheInteraction() {
        let frame = Self.frames[0]
        let input = presentation(frame, primary: "field-goals", previous: "sacks", next: "sacks")
        let resolved = input.resolve(reduceMotion: false, actionable: true)
        let shown = Ref(scope: frame.scope, id: "field-goals"), target = Ref(scope: frame.scope, id: "sacks")
        XCTAssertEqual(resolved.next?.slot.card?.name, "Quarterback pressure")
        XCTAssertEqual(input.intents(for: .browse(.next), resolved: resolved),
                       [.interaction(scope: frame.scope, card: shown), .browse(.next, to: target)])
        XCTAssertEqual(input.intents(for: .browse(.previous), resolved: resolved),
                       [.interaction(scope: frame.scope, card: shown), .browse(.previous, to: target)])
        XCTAssertEqual(Presentation.browseAccessibilityLabel(.next, name: resolved.next?.slot.card?.name),
                       "Next card: Quarterback pressure")
    }

    // 6
    func testPlaybackIntentsAreExactAndInteractionComesFirst() {
        let frame = Self.frames[1]
        let shown = Ref(scope: frame.scope, id: "field-goals")
        let cases: [(Presentation.Playback, Presentation.Intent, String)] = [
            (.pause, .pause(scope: frame.scope), "Pause story cards"),
            (.resume, .resume(scope: frame.scope), "Resume story cards"),
            (.applyUpdates, .applyUpdates(scope: frame.scope), "Apply story updates"),
        ]
        for (playback, request, label) in cases {
            let input = presentation(frame, primary: "field-goals", playback: playback)
            let resolved = input.resolve(reduceMotion: false, actionable: true)
            XCTAssertEqual(input.intents(for: .playback, resolved: resolved),
                           [.interaction(scope: frame.scope, card: shown), request])
            XCTAssertEqual(Presentation.playbackAccessibilityLabel(playback), label)
        }
        XCTAssertEqual([Presentation.Playback.pause, .resume, .applyUpdates].map(Presentation.playbackTitle),
                       ["Pause", "Resume", "Apply updates"], "no vague \"play updates\"")
    }

    // 7
    func testHeldCardThatIsMissingWithdrawnOrForeignStaysExplicit() {
        let frame = Self.frames[2]
        var input = presentation(frame, primary: "field-goals", next: "sacks")
        input.cards = [Presentation.Card(id: "field-goals", name: "The kicking game", available: false),
                       Presentation.Card(id: "sacks", name: "Quarterback pressure")]
        var resolved = input.resolve(reduceMotion: false, actionable: true)
        let held = Ref(scope: frame.scope, id: "field-goals")
        XCTAssertEqual(resolved.primary, .unavailable(held, .withdrawn), "never the neighbour 'sacks'")
        XCTAssertEqual(input.intents(for: .open(held), resolved: resolved), [], "a withdrawn slot cannot open")
        XCTAssertNil(resolved.dwell)

        input.primary = Ref(scope: frame.scope, id: "kicking")
        XCTAssertEqual(input.resolve(reduceMotion: false, actionable: true).primary,
                       .unavailable(Ref(scope: frame.scope, id: "kicking"), .missing))

        input.primary = Ref(scope: "team404:Before", id: "sacks")
        resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.primary, .unavailable(Ref(scope: "team404:Before", id: "sacks"), .foreignScope),
                       "a card from another phase's scope is not this frame's card")
        XCTAssertEqual(input.intents(for: .open(Ref(scope: "team404:Before", id: "sacks")), resolved: resolved), [])
    }

    // 8
    func testDuplicateAndBlankIDsResolveToNoCard() {
        let frame = Self.frames[0]
        var input = presentation(frame, primary: "sacks", next: "field-goals")
        input.cards.append(Presentation.Card(id: "sacks", name: "Quarterback pressure"))
        var resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.primary, .unavailable(Ref(scope: frame.scope, id: "sacks"), .duplicate))

        input = presentation(frame, primary: "field-goals", next: "  ")
        resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.next?.slot, .unavailable(Ref(scope: frame.scope, id: "  "), .blank))
        XCTAssertEqual(resolved.next?.enabled, false)
        XCTAssertEqual(input.intents(for: .browse(.next), resolved: resolved), [])
        XCTAssertEqual(Presentation.browseAccessibilityLabel(.next, name: resolved.next?.slot.card?.name),
                       "Next card unavailable")
    }

    // 9
    func testEmptyAndOneCardStreamsStayCoherent() {
        let frame = Self.frames[3]
        let empty = presentation(frame, primary: nil, next: "duel", playback: .resume)
            .resolve(reduceMotion: true, actionable: true)
        XCTAssertNil(empty.primary)
        XCTAssertNil(empty.playback)
        XCTAssertNil(empty.next)
        XCTAssertNil(empty.manualWords)
        XCTAssertEqual(Presentation.emptyWords,
                       "No stories in this order. Every original prop is still in All props.")

        let one = presentation(frame, primary: "duel").resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(one.primary?.card?.id, "duel")
        XCTAssertNil(one.playback)
        XCTAssertNil(one.previous)
        XCTAssertNil(one.next)
    }

    // 10
    func testCallbackFreeKeepsContentAndWordsButDrawsNoActions() {
        let frame = Self.frames[0]
        var input = presentation(frame, primary: "field-goals", previous: "sacks", next: "sacks",
                                 companion: "sacks", wide: true, playback: .pause)
        input.status = "Cards advance when you’re watching"
        input.dwellFraction = 0.4
        let resolved = input.resolve(reduceMotion: false, actionable: false)
        XCTAssertEqual(resolved.primary?.card?.name, "The kicking game")
        XCTAssertEqual(resolved.companion?.card?.name, "Quarterback pressure")
        XCTAssertNil(resolved.playback)
        XCTAssertNil(resolved.previous)
        XCTAssertNil(resolved.next)
        XCTAssertFalse(resolved.actionable)
        XCTAssertEqual(resolved.dwell, 0.4)
        XCTAssertEqual(input.intents(for: .open(Ref(scope: frame.scope, id: "field-goals")), resolved: resolved), [])
        XCTAssertEqual(input.activationIntents(for: Ref(scope: frame.scope, id: "field-goals"), resolved: resolved), [])
    }

    // 11
    func testPendingWordsAreShownWithoutApplyingAnything() {
        let frame = Self.frames[2]
        var input = presentation(frame, primary: "sacks", next: "field-goals", playback: .resume)
        input.status = "Paused · take your time"
        input.pending = "New stories ready · Resume to apply"
        input.nextHint = "Next in the new order: The kicking game"
        let resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.primary?.card?.id, "sacks", "the displayed card does not move to the new order")
        XCTAssertEqual(Presentation.words(input.pending), "New stories ready · Resume to apply")
        XCTAssertEqual(Presentation.words(input.nextHint), "Next in the new order: The kicking game")
        XCTAssertNil(Presentation.words("   "))
        XCTAssertEqual(resolved.playback, .resume)
    }

    // 12
    func testReaderOpenSuppressesEveryShellRequest() {
        let frame = Self.frames[1]
        var input = presentation(frame, primary: "field-goals", previous: "sacks", next: "sacks",
                                 companion: "sacks", wide: true, playback: .pause)
        input.readerOpen = true
        let resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertTrue(resolved.actionable)
        XCTAssertFalse(resolved.controlsEnabled)
        XCTAssertEqual(resolved.next?.enabled, false)
        let shown = Ref(scope: frame.scope, id: "field-goals")
        for action in [Presentation.Action.playback, .browse(.next), .browse(.previous), .open(shown),
                       .open(Ref(scope: frame.scope, id: "sacks"))] {
            XCTAssertEqual(input.intents(for: action, resolved: resolved), [], "\(action)")
        }
        XCTAssertEqual(input.activationIntents(for: shown, resolved: resolved),
                       [.interaction(scope: frame.scope, card: shown)], "a card may still ask for a hold")
    }

    // 13
    func testReduceMotionOffersOnlyManualOrStoppingControls() {
        let frame = Self.frames[0]
        let resume = presentation(frame, primary: "field-goals", next: "sacks", playback: .resume)
        let reduced = resume.resolve(reduceMotion: true, actionable: true)
        XCTAssertNil(reduced.playback, "no automatic Resume under Reduce Motion")
        XCTAssertEqual(reduced.manualWords, "Reduced motion · browse at your pace")
        XCTAssertEqual(resume.intents(for: .playback, resolved: reduced), [])
        XCTAssertEqual(reduced.next?.enabled, true, "manual browsing stays")

        let apply = presentation(frame, primary: "field-goals", playback: .applyUpdates)
            .resolve(reduceMotion: true, actionable: true)
        XCTAssertEqual(apply.playback, .applyUpdates)
        XCTAssertNil(apply.manualWords)
        let pause = presentation(frame, primary: "field-goals", playback: .pause)
            .resolve(reduceMotion: true, actionable: true)
        XCTAssertEqual(pause.playback, .pause, "a stop request is never hidden")
        let none = presentation(frame, primary: "field-goals").resolve(reduceMotion: true, actionable: true)
        XCTAssertEqual(none.manualWords, "Reduced motion · browse at your pace")
    }

    // 14
    func testDwellIsDrawnOnlyForAFiniteFractionInRangeWithoutReduceMotion() {
        XCTAssertEqual(Presentation.validDwell(0), 0)
        XCTAssertEqual(Presentation.validDwell(1), 1)
        XCTAssertEqual(Presentation.validDwell(0.55), 0.55)
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.01] {
            XCTAssertNil(Presentation.validDwell(bad), "\(bad)")
        }
        XCTAssertNil(Presentation.validDwell(nil))
        var input = presentation(Self.frames[1], primary: "field-goals")
        input.dwellFraction = 0.5
        XCTAssertEqual(input.resolve(reduceMotion: false, actionable: true).dwell, 0.5)
        XCTAssertNil(input.resolve(reduceMotion: true, actionable: true).dwell)
    }

    // 15
    func testCardActivationAsksForAHoldOnItsOwnCardOnly() {
        let frame = Self.frames[2]
        let input = presentation(frame, primary: "field-goals", companion: "sacks", wide: true)
        let resolved = input.resolve(reduceMotion: false, actionable: true)
        let recorder = Recorder()
        let companion = Ref(scope: frame.scope, id: "sacks")
        let activation = StoryStreamCardActivation10868(
            card: companion, intents: input.activationIntents(for: companion, resolved: resolved),
            send: recorder.send)
        XCTAssertTrue(activation.isAvailable)
        XCTAssertEqual(recorder.intents, [], "building the hook sends nothing")
        activation.request()
        XCTAssertEqual(recorder.intents, [.interaction(scope: frame.scope, card: companion)])
        XCTAssertEqual(input.activationIntents(for: Ref(scope: frame.scope, id: "elsewhere"), resolved: resolved), [])
    }

    // 16
    func testTheViewBuildsTheSuppliedCardAndARebuildSendsNothing() {
        let frame = Self.frames[0]
        var input = presentation(frame, primary: "field-goals", previous: "sacks", next: "sacks", playback: .pause)
        input.status = "Cards advance when you’re watching"
        let recorder = Recorder()
        var built: [String] = []
        var hooks: [Ref] = []
        let view = StoryStreamPresentationView10868(input, onIntent: recorder.send) { card, activation in
            let _ = built.append(card.id)
            let _ = hooks.append(activation.card)
            Text(card.name)
        }
        _ = view.body
        _ = view.body
        XCTAssertEqual(recorder.intents, [], "render and rebuild invoke no callback")
        XCTAssertFalse(built.isEmpty)
        XCTAssertEqual(Set(built), ["field-goals"], "the builder receives exactly the displayed card")
        XCTAssertEqual(Set(hooks), [Ref(scope: frame.scope, id: "field-goals")])
    }

    // 17
    func testBlankOwnerOrReferenceScopeResolvesToNoCardAndSendsNothing() {
        let frame = Self.frames[2]
        for blank in ["", "  ", "\n\t"] {
            let unscoped = Frame(route: frame.route, phase: frame.phase, scope: blank, cards: frame.cards,
                                 approvedOrder: frame.approvedOrder)
            var input = presentation(unscoped, primary: "field-goals", next: "sacks",
                                     companion: "sacks", wide: true, playback: .pause)
            input.previous = Ref(scope: frame.scope, id: "sacks")
            let held = Ref(scope: blank, id: "field-goals")
            for reduceMotion in [false, true] {
                let resolved = input.resolve(reduceMotion: reduceMotion, actionable: true)
                XCTAssertEqual(resolved.primary, .unavailable(held, .blankScope), "explicit slot, no neighbour")
                XCTAssertEqual(resolved.companion, .unavailable(Ref(scope: blank, id: "sacks"), .blankScope))
                XCTAssertNil(resolved.playback, "a blank owner scope offers no playback")
                XCTAssertNil(resolved.manualWords)
                XCTAssertFalse(resolved.controlsEnabled)
                XCTAssertEqual(resolved.next?.enabled, false)
                XCTAssertEqual(resolved.previous?.enabled, false)
                for action in [Presentation.Action.playback, .browse(.next), .browse(.previous), .open(held)] {
                    XCTAssertEqual(input.intents(for: action, resolved: resolved), [], "\(action)")
                }
                XCTAssertEqual(input.activationIntents(for: held, resolved: resolved), [])
            }
        }

        // A valid owner scope with a blank reference scope: the reference is blank,
        // not foreign, and it is never an open or browse target.
        var input = presentation(frame, primary: "field-goals", next: "sacks")
        input.next = Ref(scope: " ", id: "sacks")
        var resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.primary?.card?.name, "The kicking game")
        XCTAssertEqual(resolved.next?.slot, .unavailable(Ref(scope: " ", id: "sacks"), .blankScope))
        XCTAssertEqual(input.intents(for: .browse(.next), resolved: resolved), [])
        input.primary = Ref(scope: "", id: "field-goals")
        input.next = Ref(scope: frame.scope, id: "sacks")
        resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.primary, .unavailable(Ref(scope: "", id: "field-goals"), .blankScope))
        XCTAssertEqual(input.intents(for: .open(Ref(scope: "", id: "field-goals")), resolved: resolved), [])
        XCTAssertEqual(input.intents(for: .browse(.next), resolved: resolved),
                       [.interaction(scope: frame.scope, card: nil),
                        .browse(.next, to: Ref(scope: frame.scope, id: "sacks"))],
                       "a valid scope can still browse away from a blank held reference")

        // Blankness is only tested; scope equality stays exact.
        input = presentation(frame, primary: "sacks")
        input.primary = Ref(scope: " \(frame.scope)", id: "sacks")
        XCTAssertEqual(input.resolve(reduceMotion: false, actionable: true).primary,
                       .unavailable(Ref(scope: " \(frame.scope)", id: "sacks"), .foreignScope))
    }

    // 18
    func testBlankCardNameIsNeverAnOpenOrBrowseTarget() {
        let frame = Self.frames[0]
        var input = presentation(frame, primary: "field-goals", previous: "sacks", next: "sacks")
        input.cards = [Presentation.Card(id: "field-goals", name: "The kicking game"),
                       Presentation.Card(id: "sacks", name: " \n")]
        var resolved = input.resolve(reduceMotion: false, actionable: true)
        let unnamed = Ref(scope: frame.scope, id: "sacks")
        XCTAssertEqual(resolved.next?.slot, .unavailable(unnamed, .unnamed))
        XCTAssertEqual(resolved.next?.enabled, false)
        XCTAssertEqual(input.intents(for: .browse(.next), resolved: resolved), [])
        XCTAssertEqual(input.intents(for: .browse(.previous), resolved: resolved), [])
        XCTAssertEqual(Presentation.browseAccessibilityLabel(.next, name: resolved.next?.slot.card?.name),
                       "Next card unavailable")

        // Displayed: an explicit unavailable slot that cannot open, while the
        // owner's valid target can still be browsed to.
        input.primary = unnamed
        input.previous = Ref(scope: frame.scope, id: "field-goals")
        input.next = nil
        input.dwellFraction = 0.5
        resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.primary, .unavailable(unnamed, .unnamed), "never the neighbour 'field-goals'")
        XCTAssertNil(resolved.dwell)
        XCTAssertEqual(input.intents(for: .open(unnamed), resolved: resolved), [])
        XCTAssertEqual(input.activationIntents(for: unnamed, resolved: resolved), [])
        XCTAssertEqual(input.intents(for: .browse(.previous), resolved: resolved),
                       [.interaction(scope: frame.scope, card: nil),
                        .browse(.previous, to: Ref(scope: frame.scope, id: "field-goals"))])
    }

    // 19
    func testInvalidCompanionMinimumWidthStacksInsteadOfReachingAFrame() {
        for bad: CGFloat in [-1, 0, -0.0, .nan, .infinity, -.infinity] {
            XCTAssertNil(Presentation.pairingWidth(bad), "\(bad)")
            XCTAssertEqual(Presentation.arrangement(hasCompanion: true, accessibilitySize: false,
                                                    companionMinimumWidth: bad), .column, "\(bad)")
            XCTAssertEqual(Presentation.arrangement(hasCompanion: true, accessibilitySize: true,
                                                    companionMinimumWidth: bad), .column, "\(bad)")
            XCTAssertEqual(Presentation.arrangement(hasCompanion: false, accessibilitySize: false,
                                                    companionMinimumWidth: bad), .single, "\(bad)")
        }
        for good: CGFloat in [320, 1, 0.5, 480] {
            XCTAssertEqual(Presentation.pairingWidth(good), good)
            XCTAssertEqual(Presentation.arrangement(hasCompanion: true, accessibilitySize: false,
                                                    companionMinimumWidth: good), .pairedIfFits(minimumWidth: good))
        }

        // The owner's explicit companion is still shown; only its layout stacks.
        let frame = Self.frames[1]
        var input = presentation(frame, primary: "field-goals", companion: "sacks", wide: true)
        input.companionMinimumWidth = .nan
        let resolved = input.resolve(reduceMotion: false, actionable: true)
        XCTAssertEqual(resolved.companion?.card?.name, "Quarterback pressure")
        XCTAssertEqual(Presentation.arrangement(hasCompanion: resolved.companion != nil, accessibilitySize: false,
                                                companionMinimumWidth: input.companionMinimumWidth), .column)
    }
}
