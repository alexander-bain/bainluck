import SwiftUI

// #10868 — the timed-field screen: one native presentation for a field of
// named contenders timed against the clock, before the event day and at the
// reported final, assembled from the accepted shared leaves. A fan sees, in
// this order: the headline (the owner's eyebrow, title, date and status
// words, the info control, at the final the reported actual time and
// standing, and the owner's dated chance context — each contender's own
// earlier and recorded chance under its own role and date); the owner's dated
// view choices; the anchored chance history of the selected contender and the
// owner's featured peers; then the owner's story stream (or the cards
// directly) — at the final the actual finish-gap card with the owner's bounded
// finisher windows, and in every applicable phase the before-event expectations
// card — and the all-originals entry. The history and each card open as
// full-size content made of the same Views and inputs; the contender chooser,
// every original in the owner's bounded catalogue windows, the held original's
// Details with its recorded history, that original side's own full-size
// history and the owner's Info are further content modes.
//
// PILLARS: FORMATTING / TRUTH / DISCOVER. SHIP: fans compare dated chances,
// inspect an exact original outcome and explore actual finish gaps beside
// earlier expectations without losing held selections.
//
// REUSE DECISION. No accepted page expresses this screen whole. The field page
// (`FieldEventPagePresentation10868`) fixes its card set to the field outlook
// and movement leaves, keys its headline with three shapes and has no actual
// timed finish, no independent finisher selection and no original-side
// readers; the horse-racing page's final card is the placing-based finish
// comparison, with no timed gaps and no before-event expectations card; the
// golf, volleyball, rugby and ceremony pages are closed to their own leaves
// and card sets. So only this generic composition is new. Every child is the
// actual accepted View, unchanged:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor, its full-size
//     copy (the match page's `presentationCopy` / `readerPlotHeight`, the
//     ceremony page's exact-trade `collapsedHistory`) and the held original
//     side's own history;
//   • `TimedFinishComparisonPresentation10868` — the final finish-gap card;
//   • `PreEventProbabilityShiftPresentation10868` — the expectations card;
//   • `FieldContenderChooserPresentation10868` — the contender chooser with the
//     owner's featured cohort and bounded windows;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     every original in the owner's bounded window and the held original's
//     Details with its own recorded history, rules, source and result;
//   • `CeremonyHeadlineView10868`, `CeremonyChoiceGroupView10868`,
//     `CeremonySideChoicesView10868` and the ceremony originals contract
//     (`CeremonyEventPageOriginals10868`, `CeremonySideHistory10868`) — the
//     accepted generic headline words, owner choices, exact side choices and
//     phase-admitted originals bundle;
//   • `CeremonyComparisonGeometry10868` — the accepted dated-reading rule for
//     the headline's chance context; `CeremonyIdentityGlyph10868` and
//     `FieldHistoryGeometry10868.markPath` — each contender's own history
//     shape beside its name and slots;
//   • `StoryStreamPresentationView10868` and `RugbyMatchEventPageSectionsContent10868`.
//
// Nothing here contains a sport name, specimen name, identifier, date or
// value. The reference's capture loader, cohort election, baseline cutoff,
// scale ladder, gap arithmetic, ranking, placing words, formatters, session
// state, dialogs and focus return are NOT ported.
//
// PHASE ADMISSION. The page's phase is the owner's explicit
// `RugbyMatchEventPagePhase10868`, never read from a trade, a clock, a grade or
// a result. Every independently supplied bundle carries its own owner phase —
// the headline, the page chrome (notice, dated views, reader header, stream,
// card links, reader order and Info), the history, the finish card, the
// expectations card and the originals bundle with its side history — and each
// is read only while it matches the page. A bundle for another phase lends
// nothing: its slot shows the owner's page-independent unavailable words with
// no content and no action, while Back stays available. The info control
// needs both the admitted headline (its label) and the admitted chrome (its
// Info). Nothing is filtered by date or grade here.
//
// CARDS. The history is present in every phase. The finish card is present at
// the final only; earlier it is withheld entirely. The expectations card is
// present in every phase and is never silently dropped: before the event day
// and at the final it is the accepted leaf, and during the event (where the leaf
// has no live state) it is the owner's explicit unavailable words.
//
// DATED READINGS. The headline's chance context uses the accepted dated
// reading rule: a value only with a readable observation id, figure and date
// and a valid 0...1 placement, otherwise the owner's words; one coherent exact
// trade shows once. Reported actuals are words, never a chance.
//
// SELECTIONS. The history's selected contender and the finish card's selected
// finisher are independent owner inputs; a finisher with no linked original
// stays selectable and borrows none. Unknown, foreign or duplicated references
// never borrow a neighbour — each child keeps its own resolver.
//
// INTERACTION. On the page — the info control, the view choices, the history's
// actions, inspection choices and plot taps, a directly mounted card's expand,
// finisher, window, original and expectation actions, and the all-originals
// entry — and in the chooser, catalogue and Details content, the action calls
// the owner's interaction hook once, then the owner's exact callback with its
// exact value. A card inside the owner's stream calls the stream's activation
// hook instead, never the page hook as well. Full-size content, the side
// history and the Info keep the exact callbacks. Building or reading the view
// calls nothing. Without a callback there is no control and no hook call.
//
// READER ORDER. Full-size Previous and Next follow the owner's immutable reader
// order exactly as given: the neighbour is the adjacent entry while both cards
// are present and each is listed once. Nothing skips, sorts or remembers.
//
// LAYOUT. Phone and accessibility sizes stack; a regular or unspecified width
// places the history beside the cards while both keep their minimum widths.
// Every control drawn here keeps at least the minimum target at every text
// size; nothing shrinks or drops.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, routing,
// every held selection, window and inspection, arrivals, holds and
// subscriptions. This view keeps no state and runs no timer or animation.
//
// Host binding still owed: no timed-field input adapter exists at this base.
// Every bundle above is an unbound owner channel (named in the handback).

// MARK: - Cards, modes, intents

/// One card the page can show full size, in the page's order. `history` is the anchor.
nonisolated enum TimedFieldEventPageCard10868: String, Hashable, CaseIterable {
    case history
    /// The actual finish gaps; at the final only.
    case finish
    /// The before-event expectations.
    case expectations
}

/// What the host's container is showing, chosen by the host.
nonisolated enum TimedFieldEventPageMode10868: Equatable {
    case page
    case reader(TimedFieldEventPageCard10868)
    /// The contender chooser.
    case chooser
    /// Every original in the owner's bounded window.
    case catalogue
    /// The held original's Details.
    case original
    /// The held original side's own full-size history.
    case sideHistory
    /// The owner's Info.
    case about
}

/// Full-size content's own controls, handed back exactly.
nonisolated enum TimedFieldReaderIntent10868: Equatable {
    case back
    case previous(TimedFieldEventPageCard10868)
    case next(TimedFieldEventPageCard10868)
}

/// The page's blocks, in VoiceOver's reading order.
nonisolated enum TimedFieldEventPageBlock10868: String, CaseIterable {
    case headline
    case notice
    case choices
    case anchor
    case stories
    case catalogue
}

// MARK: - Owner input

/// The reported actual in the owner's words. Never a chance.
nonisolated struct TimedFieldActual10868: Equatable {
    /// "Reported time".
    let label: String
    /// The exact reported figure, verbatim.
    let figure: String
    /// The unit beside it ("s").
    let unit: String
    /// The owner's standing words (a placing, a rank, a record).
    let standing: String
    /// Fuller spoken words; nil speaks label, figure, unit and standing.
    let spoken: String?
}

/// One contender's dated chance context in the headline.
nonisolated struct TimedFieldChanceContext10868: Equatable {
    /// The whole name, shown and spoken verbatim.
    let name: String
    /// The same shape the history keys this contender with.
    let shape: FieldHistoryShape10868
    let tint: Color
    /// The owner's words for what the chance is of; nil draws none.
    let meaning: String?
    /// The earlier reading (before the event day).
    let earlier: CeremonyDatedReading10868
    /// A separately labelled later reading; nil shows the earlier alone.
    let later: CeremonyDatedReading10868?
}

/// The headline for one phase: the accepted generic headline words (which
/// carry the owner's phase), the reported actual and the chance context.
nonisolated struct TimedFieldHeadline10868: Equatable {
    let copy: CeremonyHeadline10868
    /// Shown on a final page from a final headline only.
    var actual: TimedFieldActual10868? = nil
    /// "Chance · before the event day"; nil draws none.
    var chanceLabel: String? = nil
    var chances: [TimedFieldChanceContext10868] = []
    /// Shown in a slot whose recorded reading is incomplete or invalid.
    let readingUnavailable: String
}

/// The owner's history for one phase.
nonisolated struct TimedFieldHistoryBundle10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// The selected contender and featured peers, exactly as admitted.
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; never shorter than the page's.
    var readerPlotHeight: CGFloat? = nil
}

/// The owner's finish card for one phase, with its bounded finisher windows.
nonisolated struct TimedFieldFinishBundle10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    let finish: TimedFinishInput10868
    /// The owner's finisher windows; nil draws none.
    var windows: CeremonyChoiceGroup10868? = nil
}

/// The owner's bounded window of originals on show in the catalogue.
struct TimedFieldCatalogueWindow10868: Equatable {
    /// A window of the same scope as the bundle's catalogue.
    let catalogue: OriginalMarketDetails9483.Catalogue
    /// The owner's window choices; nil draws none.
    var windows: CeremonyChoiceGroup10868? = nil
    let heading: String
    var context: String? = nil
    let emptyWords: String
    let unavailableChoice: String
    var labels: [OriginalMarketDetails9483.Identity: String] = [:]
}

/// The owner's originals: the accepted phase-admitted originals bundle (its
/// catalogue, held selection, recorded history, side choices, side history
/// and contender chooser) and the catalogue window on show.
struct TimedFieldOriginals10868 {
    let bundle: CeremonyEventPageOriginals10868
    var window: TimedFieldCatalogueWindow10868? = nil
}

/// The owner's link from one stream card id to the card it shows.
nonisolated struct TimedFieldEventPageStory10868: Equatable {
    /// Exactly as in `StoryStreamPresentation10868.cards`.
    let cardID: String
    let card: TimedFieldEventPageCard10868
    /// The owner's words for why this card is here; nil draws none.
    var reason: String? = nil
}

nonisolated struct TimedFieldEventPageCopy10868: Equatable {
    let storiesLabel: String
    /// The page chrome (notice, views, reader header, stream, order, Info) is
    /// for another phase.
    let chromeUnavailable: String
    /// A stream cell whose id names no single present card.
    let storyUnavailable: String
    let headlineUnavailable: String
    /// A full-size card this phase does not present.
    let readerUnavailable: String
    /// The history bundle is for another phase.
    let historyUnavailable: String
    /// The finish card is not admitted for this final.
    let finishUnavailable: String
    /// The expectations card is not admitted for this phase (always during).
    let expectationsUnavailable: String
    /// The originals bundle is for another phase.
    let originalsUnavailable: String
    let heldOriginalUnavailable: String
    let sideHistoryUnavailable: String
    let chooserUnavailable: String
    let catalogueUnavailable: String
    /// "All <count> original props"; nil draws no entry.
    let catalogueLabel: String?
    /// Spoken name of the side choices.
    let sidesLabel: String
    let backLabel: String
    let previousLabel: String
    let nextLabel: String
    let historyName: String
    let finishName: String
    let expectationsName: String
    /// The expand control's spoken prefix ("Expand").
    let expandLabel: String
}

/// The owner's page chrome for one phase: the notice, the dated views, the
/// one-line reader header, the stream with its card links and reader order,
/// and the Info. Read only while its phase equals the page's: a chrome for
/// another phase lends no words, choice, card link, order or Info, and the
/// page shows the page-independent unavailable words with Back kept.
nonisolated struct TimedFieldEventPageChrome10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// "Retained trades replayed"; nil draws none.
    var notice: String? = nil
    /// The owner's dated views; nil draws none.
    var views: CeremonyChoiceGroup10868? = nil
    /// The owner's one-line words above full-size content.
    let reader: RugbyMatchEventPageReaderHeader10868
    /// The owner's stream; nil mounts the cards directly.
    var stream: StoryStreamPresentation10868? = nil
    var stories: [TimedFieldEventPageStory10868] = []
    /// The owner's immutable full-size sequence; nil keeps the page's order.
    var readerOrder: [TimedFieldEventPageCard10868]? = nil
    let about: RugbyMatchEventPageAbout10868?
}

nonisolated struct TimedFieldEventPageInput10868: Equatable {
    let phase: RugbyMatchEventPagePhase10868
    /// Carries its own owner phase (inside its accepted headline words).
    let headline: TimedFieldHeadline10868
    /// Carries its own owner phase.
    let chrome: TimedFieldEventPageChrome10868
    /// Carries its own owner phase.
    let history: TimedFieldHistoryBundle10868
    /// Carries its own owner phase; read at a final page only.
    var finish: TimedFieldFinishBundle10868? = nil
    /// Carries its own owner phase.
    var expectations: PreEventShiftInput10868? = nil
    /// Page-independent words: labels, names and unavailable words only.
    let copy: TimedFieldEventPageCopy10868
}

nonisolated enum TimedFieldEventPageAccessibilityID10868 {
    static let page = "timedFieldEventPage10868.page"
    static let headline = "timedFieldEventPage10868.headline"
    static let headlineUnavailable = "timedFieldEventPage10868.headline.unavailable"
    static let actual = "timedFieldEventPage10868.headline.actual"
    static let chances = "timedFieldEventPage10868.headline.chances"
    static let notice = "timedFieldEventPage10868.notice"
    static let chromeUnavailable = "timedFieldEventPage10868.chrome.unavailable"
    static let views = "timedFieldEventPage10868.views"
    static let anchor = "timedFieldEventPage10868.anchor"
    static let stories = "timedFieldEventPage10868.stories"
    static let storyUnavailable = "timedFieldEventPage10868.story.unavailable"
    static let finishWindows = "timedFieldEventPage10868.finish.windows"
    static let catalogueEntry = "timedFieldEventPage10868.catalogue.entry"
    static let catalogue = "timedFieldEventPage10868.catalogue"
    static let catalogueWindows = "timedFieldEventPage10868.catalogue.windows"
    static let chooser = "timedFieldEventPage10868.chooser"
    static let original = "timedFieldEventPage10868.original"
    static let heldUnavailable = "timedFieldEventPage10868.original.unavailable"
    static let sideHistory = "timedFieldEventPage10868.sideHistory"
    static let catalogueUnavailable = "timedFieldEventPage10868.catalogue.unavailable"
    static let chooserUnavailable = "timedFieldEventPage10868.chooser.unavailable"
    static let originalsUnavailable = "timedFieldEventPage10868.originals.unavailable"
    static let sideHistoryUnavailable = "timedFieldEventPage10868.sideHistory.unavailable"
    static let readerUnavailable = "timedFieldEventPage10868.reader.unavailable"
    static let about = "timedFieldEventPage10868.about"
    static let readerHeader = "timedFieldEventPage10868.readerHeader"
    static let readerInfo = "timedFieldEventPage10868.readerHeader.info"
    static let readerBack = "timedFieldEventPage10868.reader.back"
    static let readerPrevious = "timedFieldEventPage10868.reader.previous"
    static let readerNext = "timedFieldEventPage10868.reader.next"
    static func card(_ card: TimedFieldEventPageCard10868) -> String { "timedFieldEventPage10868.card.\(card.rawValue)" }
    static func expand(_ card: TimedFieldEventPageCard10868) -> String { "timedFieldEventPage10868.expand.\(card.rawValue)" }
    static func unavailable(_ card: TimedFieldEventPageCard10868) -> String {
        "timedFieldEventPage10868.unavailable.\(card.rawValue)"
    }
}

// MARK: - Model

/// Which leaves the page mounts and what each reads, resolved once per input.
/// Plain (main-actor) because the originals contract it admits is.
struct TimedFieldEventPageModel10868: Equatable {
    let input: TimedFieldEventPageInput10868

    init(_ input: TimedFieldEventPageInput10868) {
        self.input = input
    }

    static func readable(_ words: String?) -> String? { RugbyMatchEventPageModel10868.readable(words) }

    // MARK: Headline

    /// The headline at the page's own phase. Otherwise nothing.
    var headline: TimedFieldHeadline10868? {
        input.headline.copy.phase == input.phase ? input.headline : nil
    }

    /// The reported actual: on a final page, from that final headline, with a
    /// readable figure. Words only, never a chance.
    var actual: TimedFieldActual10868? {
        guard input.phase == .final, let actual = headline?.actual, Self.readable(actual.figure) != nil else { return nil }
        return actual
    }

    /// The actual's spoken words: the owner's own, else label, figure, unit
    /// and standing in that order.
    static func spoken(_ actual: TimedFieldActual10868) -> String {
        if let spoken = readable(actual.spoken) { return spoken }
        let figure = [actual.figure, readable(actual.unit)].compactMap { $0 }.joined(separator: " ")
        return [readable(actual.label), figure, readable(actual.standing)].compactMap { $0 }.joined(separator: ", ")
    }

    /// One contender's dated chance slots: the earlier alone, or the earlier
    /// then the later — one coherent exact trade shows once. Each a value
    /// only while qualified (readable id, figure, date and a 0...1 placement).
    static func chanceSlots(_ chance: TimedFieldChanceContext10868, unreadable: String) -> [CeremonyComparisonSlot10868] {
        guard let later = chance.later else {
            return [CeremonyComparisonGeometry10868.slot(chance.earlier, style: .hollow, unreadable: unreadable)]
        }
        return CeremonyComparisonGeometry10868.slots(earlier: chance.earlier, later: later, unreadable: unreadable)
    }

    // MARK: Chrome

    /// The page chrome admitted for this page's phase. Otherwise nothing: no
    /// notice, views, reader header, stream, card link, order or Info.
    var chrome: TimedFieldEventPageChrome10868? {
        input.chrome.phase == input.phase ? input.chrome : nil
    }

    /// The admitted notice with readable words.
    var notice: String? { Self.readable(chrome?.notice) }

    /// The admitted dated views.
    var views: CeremonyChoiceGroup10868? { chrome?.views }

    /// The admitted reader header.
    var readerHeader: RugbyMatchEventPageReaderHeader10868? { chrome?.reader }

    /// The admitted stream.
    var stream: StoryStreamPresentation10868? { chrome?.stream }

    // MARK: Cards

    /// The history admitted for this page's phase. Otherwise nothing.
    var history: TimedFieldHistoryBundle10868? {
        input.history.phase == input.phase ? input.history : nil
    }

    /// The finish card at a final page only, admitted for that final.
    var finish: TimedFieldFinishBundle10868? {
        guard input.phase == .final, let finish = input.finish, finish.phase == .final else { return nil }
        return finish
    }

    /// The expectations input admitted for this page's phase: the leaf's own
    /// phase equals the page's, and never during (the leaf has no live state).
    var expectations: PreEventShiftInput10868? {
        guard input.phase != .during, let expectations = input.expectations,
              expectations.phase == RugbyMatchEventPageModel10868.leafPhase(input.phase) else { return nil }
        return expectations
    }

    /// A card this phase presents. The history and the expectations are
    /// present in every phase (each shows the owner's words when its bundle is
    /// not admitted); the finish is present at the final only.
    func isMounted(_ card: TimedFieldEventPageCard10868) -> Bool {
        switch card {
        case .history, .expectations: true
        case .finish: input.phase == .final
        }
    }

    var mountedCards: [TimedFieldEventPageCard10868] {
        TimedFieldEventPageCard10868.allCases.filter(isMounted)
    }

    /// The owner's words a present card shows in place of a bundle that is
    /// not admitted; nil while its bundle is admitted.
    func unavailableWords(_ card: TimedFieldEventPageCard10868) -> String? {
        switch card {
        case .history: history == nil ? input.copy.historyUnavailable : nil
        case .finish: finish == nil ? input.copy.finishUnavailable : nil
        case .expectations: expectations == nil ? input.copy.expectationsUnavailable : nil
        }
    }

    /// The history on the page: the exact-trade collapse copy at the owner's height.
    var presentedHistory: FieldHistoryInput10868? {
        history.map {
            let copy = CeremonyEventPageModel10868.collapsedHistory($0.history)
            return RugbyMatchEventPageModel10868.presentationCopy(
                copy, plotHeight: copy.plotHeight, expand: copy.expand, showsKey: copy.showsKey)
        }
    }

    /// The history full size: the same input at the owner's full-size height
    /// (never shorter than the page's), without its own expand control.
    var readerHistory: FieldHistoryInput10868? {
        history.map {
            let copy = CeremonyEventPageModel10868.collapsedHistory($0.history)
            return RugbyMatchEventPageModel10868.presentationCopy(
                copy,
                plotHeight: RugbyMatchEventPageModel10868.readerPlotHeight($0.readerPlotHeight, history: copy.plotHeight),
                expand: nil, showsKey: copy.showsKey)
        }
    }

    // MARK: Reader order

    /// The full-size sequence from the admitted chrome: the owner's order
    /// exactly as supplied, else the present cards in the page's order. With
    /// no admitted chrome there is no sequence, so no Previous or Next.
    var readerSequence: [TimedFieldEventPageCard10868] {
        guard let chrome else { return [] }
        return chrome.readerOrder ?? mountedCards
    }

    /// A card's one position; none when absent or listed more than once.
    static func uniqueIndex(of card: TimedFieldEventPageCard10868, in sequence: [TimedFieldEventPageCard10868]) -> Int? {
        let indices = sequence.indices.filter { sequence[$0] == card }
        return indices.count == 1 ? indices[0] : nil
    }

    /// The card exactly `offset` places away while both are present and each
    /// is listed once. Nothing past either end, and no skipping.
    func neighbour(of card: TimedFieldEventPageCard10868, offset: Int) -> TimedFieldEventPageCard10868? {
        let sequence = readerSequence
        guard isMounted(card), let index = Self.uniqueIndex(of: card, in: sequence) else { return nil }
        let target = index + offset
        guard sequence.indices.contains(target) else { return nil }
        let candidate = sequence[target]
        guard isMounted(candidate), Self.uniqueIndex(of: candidate, in: sequence) != nil else { return nil }
        return candidate
    }

    func cardName(_ card: TimedFieldEventPageCard10868) -> String {
        switch card {
        case .history: input.copy.historyName
        case .finish: input.copy.finishName
        case .expectations: input.copy.expectationsName
        }
    }

    /// The admitted chrome's link a stream card id names: exactly one link,
    /// to a present card other than the anchor.
    func storyLink(_ cardID: String) -> TimedFieldEventPageStory10868? {
        guard let chrome else { return nil }
        let links = chrome.stories.filter { $0.cardID == cardID }
        guard links.count == 1, let link = links.first, link.card != .history, isMounted(link.card) else { return nil }
        return link
    }

    /// The admitted chrome mounts the cards directly (it supplies no stream).
    /// With no admitted chrome, neither the stream nor the direct cards mount.
    var showsCardsDirectly: Bool { chrome != nil && chrome?.stream == nil }

    /// The cards mounted directly on the page under the anchor, in the page's order.
    var directCards: [TimedFieldEventPageCard10868] {
        showsCardsDirectly ? mountedCards.filter { $0 != .history } : []
    }

    // MARK: Info

    /// The admitted chrome's Info, when it carries readable words.
    var about: RugbyMatchEventPageAbout10868? {
        guard let about = chrome?.about,
              Self.readable(about.title) != nil || about.sections.contains(where: RugbyMatchEventPageModel10868.hasWords)
        else { return nil }
        return about
    }

    /// The info control: the admitted Info, the admitted headline's readable
    /// label and a callback.
    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && Self.readable(headline?.copy.aboutLabel) != nil
    }

    // MARK: Originals

    /// The owner's originals only while admitted for this page's phase: the
    /// one value the chooser, catalogue, side choices, Details, recorded
    /// history and side history read. Another phase's bundle lends nothing.
    func admitted(_ originals: TimedFieldOriginals10868?) -> TimedFieldOriginals10868? {
        guard let originals, originals.bundle.phase == input.phase else { return nil }
        return originals
    }

    /// The owner supplied originals, but for another phase.
    func originalsAreForAnotherPhase(_ originals: TimedFieldOriginals10868?) -> Bool {
        originals != nil && admitted(originals) == nil
    }

    /// The held side's own history: inside the admitted bundle, admitted for
    /// this phase and for exactly the held selection.
    func sideHistory(_ originals: TimedFieldOriginals10868?) -> FieldHistoryInput10868? {
        guard let held = admitted(originals), held.bundle.sideHistory?.phase == input.phase else { return nil }
        return CeremonyEventPageModel10868.exactSideHistory(held.bundle)
    }

    /// The window belongs to the bundle's catalogue: the same readable scope,
    /// and every window original is exactly the one bundle original carrying
    /// its identity. Otherwise it lends no card.
    static func windowBelongs(_ window: TimedFieldCatalogueWindow10868,
                              to catalogue: OriginalMarketDetails9483.Catalogue?) -> Bool {
        guard let catalogue, readable(catalogue.scope) != nil, window.catalogue.scope == catalogue.scope else { return false }
        return window.catalogue.originals.allSatisfy { original in
            let matches = catalogue.originals.filter { $0.identity == original.identity }
            return matches.count == 1 && matches[0] == original
        }
    }

    /// The catalogue window on show: inside the admitted bundle and belonging
    /// to its catalogue.
    func catalogueWindow(_ originals: TimedFieldOriginals10868?) -> TimedFieldCatalogueWindow10868? {
        guard let held = admitted(originals), let window = held.window,
              Self.windowBelongs(window, to: held.bundle.catalogue) else { return nil }
        return window
    }

    /// The contender chooser inside the admitted bundle.
    func chooser(_ originals: TimedFieldOriginals10868?) -> FieldChooserInput10868? {
        admitted(originals)?.bundle.chooser
    }

    /// The all-originals entry: readable words, a callback and a window to open.
    func catalogueAvailable(canOpen: Bool, originals: TimedFieldOriginals10868?) -> Bool {
        canOpen && Self.readable(input.copy.catalogueLabel) != nil && catalogueWindow(originals) != nil
    }

    // MARK: Layout and reading order

    static let readingOrder: [TimedFieldEventPageBlock10868] = TimedFieldEventPageBlock10868.allCases

    /// VoiceOver reads the same order in every arrangement.
    static func sortPriority(_ block: TimedFieldEventPageBlock10868) -> Double {
        Double(readingOrder.count - (readingOrder.firstIndex(of: block) ?? readingOrder.count))
    }

    /// Chance slots sit side by side where they fit; accessibility sizes stack.
    static func chanceArrangements(accessibilitySize: Bool) -> [RugbyMatchEventPageArrangement10868] {
        accessibilitySize ? [.stacked] : [.sideBySide, .stacked]
    }
}

// MARK: - Drawing pieces

private struct TimedFieldCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}

/// A slot's mark: the contender's own shape, hollow for the earlier reading
/// and filled for the later one — the history's meanings. Decorative.
struct TimedFieldSlotMark10868: View {
    let shape: FieldHistoryShape10868
    let style: FieldHistoryMarkStyle10868
    let tint: Color

    @ScaledMetric(relativeTo: .caption) private var radius: CGFloat = 5

    var body: some View {
        Canvas { context, size in
            let center = CGPoint(x: size.width / 2, y: size.height / 2)
            let path = FieldHistoryGeometry10868.markPath(shape, at: center, radius: radius)
            switch style {
            case .filled: context.fill(path, with: .color(tint))
            case .hollow: context.stroke(path, with: .color(tint), lineWidth: 1.5)
            }
        }
        .frame(width: radius * 3, height: radius * 3)
        .accessibilityHidden(true)
    }
}

/// One dated chance slot: its mark, role, figure and the trade's own date, or
/// the owner's words. Read as one element.
struct TimedFieldChanceSlotView10868: View {
    let slot: CeremonyComparisonSlot10868
    let shape: FieldHistoryShape10868
    let tint: Color

    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = RugbyMatchEventPageModel10868.comparisonFigureSize

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                if slot.isValue {
                    TimedFieldSlotMark10868(shape: shape, style: slot.style, tint: tint)
                }
                Text(slot.role)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if slot.isValue {
                Text(slot.text)
                    .font(.system(size: figureSize, weight: .bold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if let date = slot.date {
                    Text(date)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(slot.text)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(slot.spoken)
    }
}

/// One contender's dated chance context: its identity, whole name, the
/// owner's meaning words and its slots side by side where they fit.
struct TimedFieldChanceContextView10868: View {
    let chance: TimedFieldChanceContext10868
    let unreadable: String

    @Environment(\.dynamicTypeSize) private var typeSize

    var slots: [CeremonyComparisonSlot10868] {
        TimedFieldEventPageModel10868.chanceSlots(chance, unreadable: unreadable)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                CeremonyIdentityGlyph10868(shape: chance.shape, tint: chance.tint)
                Text(chance.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let meaning = TimedFieldEventPageModel10868.readable(chance.meaning) {
                Text(meaning)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if TimedFieldEventPageModel10868.chanceArrangements(accessibilitySize: typeSize.isAccessibilitySize) == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 12) { slotViews }
                    stacked
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityLabel(chance.name)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 8) { slotViews }
    }

    private var slotViews: some View {
        ForEach(Array(slots.enumerated()), id: \.offset) { _, slot in
            TimedFieldChanceSlotView10868(slot: slot, shape: chance.shape, tint: chance.tint)
        }
    }
}

/// The headline: the accepted headline words and info control, the reported
/// actual at the final, then the owner's dated chance context.
struct TimedFieldHeadlineView10868: View {
    let headline: TimedFieldHeadline10868
    /// The reported actual, already admitted for a final page; nil draws none.
    let actual: TimedFieldActual10868?
    var onAbout: (() -> Void)? = nil

    @ScaledMetric(relativeTo: .largeTitle) private var actualSize: CGFloat = 34

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CeremonyHeadlineView10868(headline: headline.copy, onAbout: onAbout)
            if let actual {
                actualBlock(actual)
            }
            if !headline.chances.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    if let label = TimedFieldEventPageModel10868.readable(headline.chanceLabel) {
                        Text(label)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ForEach(Array(headline.chances.enumerated()), id: \.offset) { _, chance in
                        TimedFieldChanceContextView10868(chance: chance, unreadable: headline.readingUnavailable)
                    }
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.chances)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.headline)
    }

    private func actualBlock(_ actual: TimedFieldActual10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if let label = TimedFieldEventPageModel10868.readable(actual.label) {
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
            }
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(actual.figure)
                    .font(.system(size: actualSize, weight: .bold))
                    .foregroundStyle(DS.textPrimary)
                if let unit = TimedFieldEventPageModel10868.readable(actual.unit) {
                    Text(unit)
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                }
            }
            if let standing = TimedFieldEventPageModel10868.readable(actual.standing) {
                Text(standing)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(TimedFieldEventPageModel10868.spoken(actual))
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.actual)
    }
}

/// The expand control above a card mounted directly on the page.
struct TimedFieldExpandRow10868: View {
    let prefix: String
    let name: String
    let action: () -> Void

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        Button(action: action) {
            HStack(spacing: 6) {
                Text(name)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "arrow.up.left.and.arrow.down.right")
                    .font(.subheadline.weight(.semibold))
                    .accessibilityHidden(true)
            }
            .foregroundStyle(DS.blue)
            .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel([prefix, name].compactMap { TimedFieldEventPageModel10868.readable($0) }.joined(separator: " "))
    }
}

/// Where a card body is drawn, which decides its interaction relay.
enum TimedFieldCardPlacement10868 {
    /// Directly on the page: the page hook once, then the exact callback.
    case page
    /// In the owner's stream: the stream's activation once, never the page hook.
    case stream(StoryStreamCardActivation10868)
    /// Full size: the exact callback.
    case reader
}

// MARK: - Page view

struct TimedFieldEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868
    typealias Selection = OriginalMarketDetails9483.Selection
    private typealias ID = TimedFieldEventPageAccessibilityID10868
    private typealias Model = TimedFieldEventPageModel10868

    let input: TimedFieldEventPageInput10868
    var mode: TimedFieldEventPageMode10868 = .page
    /// The chooser, catalogue window, Details and side history, read only
    /// while admitted for the page's phase; nil: none.
    var originals: TimedFieldOriginals10868? = nil
    /// Opens the host's container on the owner's Info.
    var onAbout: (() -> Void)? = nil
    /// An Info section's exact external link.
    var onLink: ((RugbyMatchEventPageLink10868) -> Void)? = nil
    /// A dated view's exact id; the page's phase stays the owner's.
    var onView: ((String) -> Void)? = nil
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// A contender chooser row's exact original.
    var onChooserChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// A contender chooser window or disclosure, exactly.
    var onChooserControl: ((FieldChooserControl10868) -> Void)? = nil
    /// A finish row's exact result reference.
    var onFinishChoose: ((TimedFinishResultRef10868) -> Void)? = nil
    /// A finish row's exact linked original.
    var onFinishOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil
    /// A finisher window's exact id.
    var onFinishWindow: ((String) -> Void)? = nil
    /// An expectations endpoint's exact original and observation key.
    var onExpectationOpen: ((FieldMovementOpen10868) -> Void)? = nil
    /// Opens every original in the owner's catalogue window.
    var onCatalogue: (() -> Void)? = nil
    /// A catalogue window's exact id.
    var onCatalogueWindow: ((String) -> Void)? = nil
    /// A catalogue card's exact selection.
    var onCatalogueSelect: ((Selection) -> Void)? = nil
    /// A Details side choice's exact selection.
    var onSide: ((Selection) -> Void)? = nil
    /// A Details history control's exact intent.
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    var onSideHistoryAction: ((String) -> Void)? = nil
    var onSideHistoryInspectionChoice: ((String) -> Void)? = nil
    var onSideHistoryPlotPosition: ((Double) -> Void)? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// Opens the host's reader on a card mounted directly on the page.
    var onCardOpen: ((TimedFieldEventPageCard10868) -> Void)? = nil
    /// Full-size and side-history controls, exactly.
    var onReaderIntent: ((TimedFieldReaderIntent10868) -> Void)? = nil
    /// Called once just before a page, chooser, catalogue or Details action
    /// reaches its owner callback. Never by building the view, by full-size
    /// content, by the side history or Info, or by a stream card.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 420
    @ScaledMetric(relativeTo: .body) private var cardsMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: TimedFieldEventPageModel10868 { TimedFieldEventPageModel10868(input) }

    /// The one originals value every consumer reads.
    var admittedOriginals: TimedFieldOriginals10868? { model.admitted(originals) }

    // MARK: Relays

    static func held<Value>(_ action: ((Value) -> Void)?, by interaction: (() -> Void)?) -> ((Value) -> Void)? {
        RugbyMatchEventPagePresentation10868.held(action, by: interaction)
    }

    static func heldAction(_ action: (() -> Void)?, by interaction: (() -> Void)?) -> (() -> Void)? {
        RugbyMatchEventPagePresentation10868.heldAction(action, by: interaction)
    }

    static func bind(_ action: ((TimedFieldEventPageCard10868) -> Void)?, _ card: TimedFieldEventPageCard10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(card) }
    }

    static func bind(_ action: ((TimedFieldReaderIntent10868) -> Void)?, _ intent: TimedFieldReaderIntent10868) -> (() -> Void)? {
        guard let action else { return nil }
        return { action(intent) }
    }

    /// A card action by placement: the page hook once, the stream's
    /// activation once, or the exact callback full size.
    func relay<Value>(_ action: ((Value) -> Void)?, _ placement: TimedFieldCardPlacement10868) -> ((Value) -> Void)? {
        switch placement {
        case .page: Self.held(action, by: onInteraction)
        case .stream(let activation): EsportsEventPagePresentation10868.relay(action, through: activation)
        case .reader: action
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .chooser: chooserMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .sideHistory: sideHistoryMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves

    /// The page's info control, after the hook.
    var headlineAboutAction: (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return nil }
        return Self.heldAction(onAbout, by: onInteraction)
    }

    /// The headline at the page's phase, with the actual at the final.
    func headlineContent() -> TimedFieldHeadlineView10868? {
        model.headline.map { TimedFieldHeadlineView10868(headline: $0, actual: model.actual, onAbout: headlineAboutAction) }
    }

    /// The admitted chrome's dated views, each after the hook.
    func viewChoicesContent() -> CeremonyChoiceGroupView10868? {
        model.views.map { CeremonyChoiceGroupView10868(group: $0, idStem: "views", onChoose: Self.held(onView, by: onInteraction)) }
    }

    /// The anchor after the hook; full size keeps the exact callbacks. Nil
    /// while the history is not admitted for this phase.
    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868? {
        let hold = reader ? nil : onInteraction
        guard let history = reader ? model.readerHistory : model.presentedHistory else { return nil }
        return FieldProbabilityHistoryPresentation10868(
            input: history,
            onAction: Self.held(onHistoryAction, by: hold),
            onInspectionChoice: Self.held(onHistoryInspectionChoice, by: hold),
            onPlotPosition: Self.held(onHistoryPlotPosition, by: hold))
    }

    /// The finish card at the final, admitted for it.
    func finishContent(_ placement: TimedFieldCardPlacement10868) -> TimedFinishComparisonPresentation10868? {
        model.finish.map {
            TimedFinishComparisonPresentation10868(input: $0.finish, onChooseResult: relay(onFinishChoose, placement),
                                                   onOpenOriginal: relay(onFinishOpenOriginal, placement))
        }
    }

    /// The owner's finisher windows inside the admitted finish card.
    func finishWindowsContent(_ placement: TimedFieldCardPlacement10868) -> CeremonyChoiceGroupView10868? {
        guard let windows = model.finish?.windows else { return nil }
        return CeremonyChoiceGroupView10868(group: windows, idStem: "finishWindows", onChoose: relay(onFinishWindow, placement))
    }

    /// The expectations card, admitted for this phase.
    func expectationsContent(_ placement: TimedFieldCardPlacement10868) -> PreEventProbabilityShiftPresentation10868? {
        model.expectations.map { PreEventProbabilityShiftPresentation10868(input: $0, onOpen: relay(onExpectationOpen, placement)) }
    }

    /// The expand control of a card mounted directly on the page, after the hook.
    func expandAction(_ card: TimedFieldEventPageCard10868) -> (() -> Void)? {
        guard model.showsCardsDirectly, card != .history, model.isMounted(card) else { return nil }
        return Self.heldAction(Self.bind(onCardOpen, card), by: onInteraction)
    }

    /// The contender chooser; rows and windows after the hook.
    func chooserContent() -> FieldContenderChooserPresentation10868? {
        model.chooser(originals).map {
            FieldContenderChooserPresentation10868(input: $0, onChoose: Self.held(onChooserChoose, by: onInteraction),
                                                   onControl: Self.held(onChooserControl, by: onInteraction))
        }
    }

    /// The all-originals entry, after the hook.
    var catalogueAction: (() -> Void)? {
        guard model.catalogueAvailable(canOpen: onCatalogue != nil, originals: originals) else { return nil }
        return Self.heldAction(onCatalogue, by: onInteraction)
    }

    /// Every original in the owner's window, each card after the hook.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        guard let admitted = admittedOriginals, let window = model.catalogueWindow(originals) else { return nil }
        return OriginalMarketCatalogueView9483(
            catalogue: window.catalogue, selection: admitted.bundle.selection, heading: window.heading,
            context: window.context, emptyWords: window.emptyWords, unavailableChoice: window.unavailableChoice,
            labels: window.labels, tint: admitted.bundle.tint, onSelect: Self.held(onCatalogueSelect, by: onInteraction))
    }

    /// The owner's catalogue windows, each after the hook.
    func catalogueWindowsContent() -> CeremonyChoiceGroupView10868? {
        guard let windows = model.catalogueWindow(originals)?.windows else { return nil }
        return CeremonyChoiceGroupView10868(group: windows, idStem: "catalogueWindows",
                                            onChoose: Self.held(onCatalogueWindow, by: onInteraction))
    }

    /// The held original's side choices, each after the hook.
    func sideChoicesContent() -> CeremonySideChoicesView10868? {
        guard let admitted = admittedOriginals, !admitted.bundle.sides.isEmpty else { return nil }
        return CeremonySideChoicesView10868(label: input.copy.sidesLabel, originals: admitted.bundle,
                                            onSide: Self.held(onSide, by: onInteraction))
    }

    /// The existing Details for the held selection, its history after the hook.
    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        admittedOriginals.map {
            OriginalMarketDetailsView9483(catalogue: $0.bundle.catalogue, selection: $0.bundle.selection, tint: $0.bundle.tint,
                                          recorded: $0.bundle.recorded,
                                          onHistory: Self.held(onOriginalHistory, by: onInteraction))
        }
    }

    /// The held side's own full-size history with the exact callbacks.
    func sideHistoryContent() -> FieldProbabilityHistoryPresentation10868? {
        model.sideHistory(originals).map {
            FieldProbabilityHistoryPresentation10868(input: $0, onAction: onSideHistoryAction,
                                                     onInspectionChoice: onSideHistoryInspectionChoice,
                                                     onPlotPosition: onSideHistoryPlotPosition)
        }
    }

    /// The owner's Info with its exact link callback.
    func aboutContent() -> RugbyMatchEventPageSectionsContent10868? {
        model.about.map {
            RugbyMatchEventPageSectionsContent10868(title: $0.title, sections: $0.sections, sourceIDs: [],
                                                    sourceLabel: "", onLink: onLink, onSource: nil)
        }
    }

    /// Full-size content's own controls. Back whenever the host takes reader
    /// intents — whatever the card, phase or chrome — so a reader carried
    /// across a phase change always leaves; Previous and Next only for a
    /// present card's present neighbours.
    func readerControls(_ card: TimedFieldEventPageCard10868) -> (previous: TimedFieldEventPageCard10868?,
                                                                  next: TimedFieldEventPageCard10868?,
                                                                  canGoBack: Bool) {
        guard onReaderIntent != nil else { return (nil, nil, false) }
        guard model.isMounted(card) else { return (nil, nil, true) }
        return (model.neighbour(of: card, offset: -1), model.neighbour(of: card, offset: 1), true)
    }

    /// Full-size content's info control: the exact callback, no hook.
    var readerAboutAction: (() -> Void)? {
        model.aboutAvailable(canOpen: onAbout != nil) ? onAbout : nil
    }

    /// The side history's Back: the exact intent, no hook.
    var sideHistoryBack: (() -> Void)? { Self.bind(onReaderIntent, .back) }
}

// MARK: - Page layout

extension TimedFieldEventPagePresentation10868 {
    fileprivate var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            headlineSection
            choicesSection
            Group {
                let arrangements = RugbyMatchEventPageModel10868.arrangements(
                    sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize)
                if arrangements == [.stacked] {
                    stackedMain
                } else {
                    ViewThatFits(in: .horizontal) {
                        wideMain
                        stackedMain
                    }
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.page)
    }

    private var headlineSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            Group {
                if let headline = headlineContent() {
                    headline
                } else {
                    ownerWords(input.copy.headlineUnavailable, id: TimedFieldEventPageAccessibilityID10868.headlineUnavailable)
                }
            }
            .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.headline))
            if let notice = model.notice {
                Text(notice)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.notice))
                    .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.notice)
            }
        }
        .accessibilityElement(children: .contain)
    }

    @ViewBuilder private var choicesSection: some View {
        if let views = viewChoicesContent() {
            views
                .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.choices))
                .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.views)
        }
    }

    private var stackedMain: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            secondary
        }
    }

    private var wideMain: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            secondary
                .frame(minWidth: cardsMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var anchor: some View {
        cardBody(.history, placement: .page)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(TimedFieldCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.anchor))
            .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.anchor)
    }

    private var secondary: some View {
        VStack(alignment: .leading, spacing: 16) {
            stories
            if let action = catalogueAction, let label = input.copy.catalogueLabel {
                catalogueEntry(label, action: action)
                    .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.catalogue))
            }
        }
    }

    /// The admitted stream; else the admitted chrome's cards directly, in the
    /// page's order; else (chrome for another phase) the owner's words.
    @ViewBuilder private var stories: some View {
        if let stream = model.stream {
            StoryStreamPresentationView10868(stream, onIntent: onStoryIntent) { card, activation in
                storyCell(card, activation)
            }
            .accessibilityElement(children: .contain)
            .accessibilityLabel(input.copy.storiesLabel)
            .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.stories))
            .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.stories)
        } else if model.showsCardsDirectly {
            ForEach(model.directCards, id: \.self) { card in
                directCard(card)
            }
        } else {
            ownerWords(input.copy.chromeUnavailable, id: TimedFieldEventPageAccessibilityID10868.chromeUnavailable)
                .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.stories))
        }
    }

    /// A card mounted directly on the page: its expand control above the same
    /// body full size shows.
    private func directCard(_ card: TimedFieldEventPageCard10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let expand = expandAction(card) {
                TimedFieldExpandRow10868(prefix: input.copy.expandLabel, name: model.cardName(card), action: expand)
                    .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.expand(card))
            }
            cardBody(card, placement: .page)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(TimedFieldCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilitySortPriority(TimedFieldEventPageModel10868.sortPriority(.stories))
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.card(card))
    }

    /// The card the admitted chrome links to this stream card, or the owner's
    /// words. Never a neighbour.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if let link = model.storyLink(card.id) {
            VStack(alignment: .leading, spacing: 8) {
                if let reason = TimedFieldEventPageModel10868.readable(link.reason) {
                    Text(reason)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                cardBody(link.card, placement: .stream(activation))
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(TimedFieldCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.card(link.card))
        } else {
            Text(input.copy.storyUnavailable)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, minHeight: 120, alignment: .leading)
                .padding(16)
                .modifier(TimedFieldCardSurface10868())
                .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.storyUnavailable)
        }
    }

    /// One card's body, the same Views and inputs in every placement: the
    /// admitted leaf (the finish with its owner windows), or the owner's words.
    @ViewBuilder fileprivate func cardBody(_ card: TimedFieldEventPageCard10868,
                                           placement: TimedFieldCardPlacement10868) -> some View {
        switch card {
        case .history:
            if let history = historyContent(reader: isReader(placement)) {
                history
            } else {
                ownerWords(input.copy.historyUnavailable, id: TimedFieldEventPageAccessibilityID10868.unavailable(.history))
            }
        case .finish:
            if let finish = finishContent(placement) {
                VStack(alignment: .leading, spacing: 12) {
                    finish
                    if let windows = finishWindowsContent(placement) {
                        windows.accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.finishWindows)
                    }
                }
            } else {
                ownerWords(input.copy.finishUnavailable, id: TimedFieldEventPageAccessibilityID10868.unavailable(.finish))
            }
        case .expectations:
            if let expectations = expectationsContent(placement) {
                expectations
            } else {
                ownerWords(input.copy.expectationsUnavailable,
                           id: TimedFieldEventPageAccessibilityID10868.unavailable(.expectations))
            }
        }
    }

    private func isReader(_ placement: TimedFieldCardPlacement10868) -> Bool {
        if case .reader = placement { return true }
        return false
    }

    private func catalogueEntry(_ label: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            HStack(spacing: 8) {
                Text(label)
                    .font(.body.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right")
                    .font(.body.weight(.semibold))
                    .accessibilityHidden(true)
            }
            .foregroundStyle(DS.blue)
            .padding(.horizontal, 16)
            .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
            .modifier(TimedFieldCardSurface10868())
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.catalogueEntry)
    }

    fileprivate func ownerWords(_ words: String, id: String) -> some View {
        Text(words)
            .font(.subheadline)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier(id)
    }
}

// MARK: - Content modes and full size

extension TimedFieldEventPagePresentation10868 {
    fileprivate var chooserMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: TimedFieldEventPageAccessibilityID10868.originalsUnavailable)
            } else if let chooser = chooserContent() {
                chooser
            } else {
                ownerWords(input.copy.chooserUnavailable, id: TimedFieldEventPageAccessibilityID10868.chooserUnavailable)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.chooser)
    }

    fileprivate var catalogueMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: TimedFieldEventPageAccessibilityID10868.originalsUnavailable)
            } else if let catalogue = catalogueContent() {
                if let windows = catalogueWindowsContent() {
                    windows.accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.catalogueWindows)
                }
                catalogue
            } else {
                ownerWords(input.copy.catalogueUnavailable, id: TimedFieldEventPageAccessibilityID10868.catalogueUnavailable)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.catalogue)
    }

    fileprivate var originalMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: TimedFieldEventPageAccessibilityID10868.originalsUnavailable)
            }
            if let sides = sideChoicesContent() {
                sides
            }
            if CeremonyEventPageModel10868.heldOriginalIsUnavailable(admittedOriginals?.bundle) {
                ownerWords(input.copy.heldOriginalUnavailable, id: TimedFieldEventPageAccessibilityID10868.heldUnavailable)
            }
            if let details = originalDetailsContent() {
                details
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.original)
    }

    fileprivate var sideHistoryMode: some View {
        VStack(alignment: .leading, spacing: 16) {
            if let back = sideHistoryBack {
                readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward", action: back,
                             id: TimedFieldEventPageAccessibilityID10868.readerBack)
            }
            if model.originalsAreForAnotherPhase(originals) {
                ownerWords(input.copy.originalsUnavailable, id: TimedFieldEventPageAccessibilityID10868.originalsUnavailable)
            } else if let history = sideHistoryContent() {
                history
            } else {
                ownerWords(input.copy.sideHistoryUnavailable,
                           id: TimedFieldEventPageAccessibilityID10868.sideHistoryUnavailable)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.sideHistory)
    }

    /// The admitted chrome's Info; else the owner's page-independent words.
    @ViewBuilder fileprivate var aboutMode: some View {
        if let about = aboutContent() {
            about.accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.about)
        } else {
            ownerWords(input.copy.chromeUnavailable, id: TimedFieldEventPageAccessibilityID10868.chromeUnavailable)
        }
    }

    /// The same Views and inputs, full size: a lazy section whose header the
    /// host's scroll pins, with the reader controls and the card body beneath.
    /// The controls come first in every branch (Back stays); a card this
    /// phase does not present keeps the owner's words and lends no content.
    @ViewBuilder fileprivate func reader(_ card: TimedFieldEventPageCard10868) -> some View {
        LazyVStack(alignment: .leading, spacing: 16, pinnedViews: [.sectionHeaders]) {
            Section {
                readerNavigation(card)
                if model.isMounted(card) {
                    cardBody(card, placement: .reader)
                } else {
                    ownerWords(input.copy.readerUnavailable, id: TimedFieldEventPageAccessibilityID10868.readerUnavailable)
                }
            } header: {
                compactHeader
                    .padding(.vertical, 8)
                    .background(DS.surface)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.card(card))
    }

    @ViewBuilder private func readerNavigation(_ card: TimedFieldEventPageCard10868) -> some View {
        let controls = readerControls(card)
        if controls.canGoBack {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { readerButtons(controls) }
                VStack(alignment: .leading, spacing: 4) { readerButtons(controls) }
            }
        }
    }

    @ViewBuilder private func readerButtons(_ controls: (previous: TimedFieldEventPageCard10868?,
                                                         next: TimedFieldEventPageCard10868?,
                                                         canGoBack: Bool)) -> some View {
        readerButton(input.copy.backLabel, detail: nil, systemImage: "chevron.backward",
                     action: Self.bind(onReaderIntent, .back), id: TimedFieldEventPageAccessibilityID10868.readerBack)
        if let previous = controls.previous {
            readerButton(input.copy.previousLabel, detail: model.cardName(previous), systemImage: "arrow.left",
                         action: Self.bind(onReaderIntent, .previous(previous)),
                         id: TimedFieldEventPageAccessibilityID10868.readerPrevious)
        }
        if let next = controls.next {
            readerButton(input.copy.nextLabel, detail: model.cardName(next), systemImage: "arrow.right",
                         action: Self.bind(onReaderIntent, .next(next)), id: TimedFieldEventPageAccessibilityID10868.readerNext)
        }
    }

    @ViewBuilder private func readerButton(_ label: String, detail: String?, systemImage: String,
                                           action: (() -> Void)?, id: String) -> some View {
        if let action {
            Button(action: action) {
                HStack(spacing: 6) {
                    Image(systemName: systemImage)
                        .font(.subheadline.weight(.semibold))
                        .accessibilityHidden(true)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(label)
                            .font(.subheadline.weight(.semibold))
                        if let detail = TimedFieldEventPageModel10868.readable(detail) {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(DS.textSecondary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                }
                .foregroundStyle(DS.blue)
                .frame(minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(id)
        }
    }

    /// The admitted chrome's one-line words and the info control; else the
    /// owner's page-independent words.
    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            Group {
                if let header = model.readerHeader {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(header.title)
                            .font(.headline)
                            .foregroundStyle(DS.textPrimary)
                            .accessibilityAddTraits(.isHeader)
                        if let state = TimedFieldEventPageModel10868.readable(header.state) {
                            Text(state)
                                .font(.subheadline)
                                .foregroundStyle(DS.textPrimary)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                } else {
                    ownerWords(input.copy.chromeUnavailable, id: TimedFieldEventPageAccessibilityID10868.chromeUnavailable)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let action = readerAboutAction,
               let label = TimedFieldEventPageModel10868.readable(model.headline?.copy.aboutLabel) {
                Button(action: action) {
                    Image(systemName: "info.circle")
                        .font(.title3)
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: EsportsEventPageModel10868.targetHeight(controlSize),
                               minHeight: EsportsEventPageModel10868.targetHeight(controlSize))
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(label)
                .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.readerInfo)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(TimedFieldEventPageAccessibilityID10868.readerHeader)
    }
}
