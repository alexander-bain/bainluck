import SwiftUI

// #10868 — the player-duel screen (`player-duel`): one native presentation
// composed from the accepted leaves. A fan sees, in this order: the owner's
// eyebrow, game words and About entry; the game-winner win-probability
// history as the anchor; the player head-to-head card in the story stream;
// and the owner's "All props" catalogue. The history and the duel open as
// full-size content made of the same Views; the contract-value card is an
// optional full-size reader only, reached by the owner's value link — inside
// the duel card, or directly on the page when no duel is offered — or by the
// readers' Previous / Next buttons; an original's Details and About are two
// more content modes. Horizontal card swiping is NOT implemented or claimed:
// only the pager buttons move between readers. The native sheet swipe-down
// dismisses the whole sheet to the game (the host keeps the reader's
// choices); Done on nested Details or About restores the same reader.
//
// PILLARS: FORMATTING / TRUTH. SHIP: the player-duel native page composes its
// game probability anchor, player comparison, contract-value reader and exact
// original Details without mixing their meanings.
//
// Presentation only, composed from the approved `PlayerDuelMatch.tsx`
// (totals-final-forecast-binding-20261024) and its `duelStoryOrder.ts`. The
// reference's fixture loaders, phase toggle, replay controls, session state,
// sheets and focus restoration are NOT ported. The leaves are the accepted
// Views, unchanged:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor: the owner's
//     game-winner history, its own earlier readings, never the duel's
//     outright chances;
//   • `PlayerDuelPresentation10868` — the head-to-head card (package 21);
//   • `PlayerDuelValuePresentation10868` — the contract-value card, in its
//     own cents DTO, never ranked as a win probability (package 21);
//   • `StoryStreamPresentationView10868` — the controlled story stream;
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     the owner's All props and the selected original's Details.
//
// Every word, figure, mode, reading, grade and provenance row arrives resolved
// by the owner and is shown verbatim. Nothing here parses a price, classifies
// an original, infers a unit, filters a catalogue, reads a clock, complements
// or normalizes a chance, or turns a count into a result. All props is a
// mixed catalogue passed through as typed: a genuine probability original
// keeps its owner's modes, readings and marks; a half-payout contract keeps
// the owner's explicit missing outright chance and its owner-labelled value
// rows. The page enforces neither by inspecting a row.
//
// Return context stays with the host (`PlayerDuelEventPageAdapter10868.Session`):
// Details or About opened from a full-size card returns to that same card on
// Done; "Back to game" closes the card. Open content whose admitted input is
// withdrawn shows its own explicit unavailable reading and a working Back —
// never a blank sheet, never another story or original.
//
// The only edits made to an owner value are the two private display copies
// of the anchor (`PlayerDuelPageModel10868.readerAnchor` and
// `.expandOnlyAnchor`), which change an action's presence or availability
// and nothing else, so a control the host cannot act on is never an enabled
// no-op.
//
// HELD PRESENTATION, NOT A DELIVERED PAGE. No production owner supplies the
// player-duel bundle at this base; seven owner inputs are missing (duel
// association and pairing; independent full-range game-winner history;
// dated contract-value endpoints; cents words; clocked player actuals; NBA
// game and card words; a served half-payout unit marker for All props). The
// player-threshold obligation is NOT covered by these two cards and stays
// open. Nothing here mounts the page, adds a route or flag, or supplies data.

/// The page's full-size cards, in the approved reader order.
nonisolated enum PlayerDuelPageCard10868: String, CaseIterable, Equatable {
    case history
    case duel
    case value
}

/// What the presentation shows.
nonisolated enum PlayerDuelPageMode10868: Equatable {
    case page
    /// One card at full size.
    case reader(PlayerDuelPageCard10868)
    /// The held original's Details.
    case original
    case about
}

/// The owner's game words above the anchor.
nonisolated struct PlayerDuelPageHeader10868: Equatable {
    /// "NBA · GAME 1 · JUN 3"; nil draws none.
    let eyebrow: String?
    /// "Knicks 105–95 Spurs".
    let title: String
    /// "Knicks won · Final".
    let state: String
    /// The owner's delivery words ("Refresh failed"); nil draws none.
    var quality: String? = nil
    /// The About entry's spoken label; nil offers no About entry.
    var aboutLabel: String? = nil
}

/// The owner's About content.
nonisolated struct PlayerDuelPageAbout10868: Equatable {
    let title: String
    let paragraphs: [String]
}

/// The owner's words for the stream and the readers. Stat-specific, so never
/// page chrome.
nonisolated struct PlayerDuelPageCardWords10868: Equatable {
    /// "PLAYER PROPS".
    let streamHeading: String
    var streamEyebrow: String? = nil
    /// "Game win probability".
    let historyName: String
    /// "Threes head-to-head".
    let duelName: String
    /// "Market value history".
    let valueName: String
    /// "Market history & tie terms"; nil offers no link to the value reader.
    var valueLink: String? = nil
}

/// The owner's words for its All props catalogue.
nonisolated struct PlayerDuelPageCatalogueWords10868: Equatable {
    /// "All props in this capture".
    let heading: String
    /// "4 markets"; nil draws none.
    var context: String? = nil
    /// Shown when the owner's catalogue is absent or empty.
    let emptyWords: String
    /// The label for an original with no readable title of its own.
    let unavailableChoice: String
}

/// The anchor as the history View receives it: the input to draw and the
/// routed callbacks. A nil callback is no control.
struct PlayerDuelPageAnchorDisplay10868 {
    let input: FieldHistoryInput10868
    var onAction: ((String) -> Void)? = nil
    var onInspectionChoice: ((String) -> Void)? = nil
    var onPlotPosition: ((Double) -> Void)? = nil
}

/// The page input after admission: every value the owner supplied for this
/// event and phase, the held original selection applied to both leaves.
struct PlayerDuelPageInput10868: Equatable {
    let phase: HockeyJourneyPagePhase10868
    let header: PlayerDuelPageHeader10868
    /// The owner's anchor exactly as supplied, or the unavailable slot.
    let anchor: FieldHistoryInput10868
    /// True only when `anchor` is the owner's own input; owner chart handlers
    /// never reach the unavailable slot.
    let anchorIsOwners: Bool
    let duel: PlayerDuelInput10868?
    /// The approved stream rule (`duelStoryOrder.ts`): a resolved pair, before
    /// play or with every player's count supplied.
    let duelOffered: Bool
    let value: PlayerDuelValueInput10868?
    let stream: StoryStreamPresentation10868
    let cards: PlayerDuelPageCardWords10868
    let about: PlayerDuelPageAbout10868?
    /// The owner's catalogue, passed through unchanged; its scope is the owner's.
    let catalogue: OriginalMarketDetails9483.Catalogue?
    let catalogueLabels: [OriginalMarketDetails9483.Identity: String]
    /// Nil: no All props section.
    let catalogueWords: PlayerDuelPageCatalogueWords10868?
}

// MARK: - Page model

/// Which leaves the page mounts, resolved once per input. Pure.
struct PlayerDuelPageModel10868 {
    let input: PlayerDuelPageInput10868

    init(_ input: PlayerDuelPageInput10868) {
        self.input = input
    }

    /// Page chrome from the approved reference, and the explicit words for
    /// open content whose admitted input was withdrawn.
    enum Words {
        static let backToGame = "Back to game"
        static let done = "Done"
        static let readerUnavailable = "This card isn’t available for this game state."
        static let aboutUnavailable = "About isn’t available for this game state."
        static let contentUnavailable = "This content isn’t available right now."
    }

    /// What an open full-size card shows.
    enum ReaderContent: Equatable {
        /// The card itself, from its admitted input.
        case card(PlayerDuelPageCard10868)
        /// The open card lost its admitted input: that same card's name, the
        /// unavailable words and Back. Never another card or original.
        case unavailable(PlayerDuelPageCard10868, name: String)
    }

    /// The duel, offered and at the page's own phase. Otherwise none.
    var duel: PlayerDuelInput10868? {
        guard input.duelOffered, let duel = input.duel, duel.phase == input.phase.contributionPhase else { return nil }
        return duel
    }

    var value: PlayerDuelValueInput10868? { input.value }

    func isMounted(_ card: PlayerDuelPageCard10868) -> Bool {
        switch card {
        case .history: true
        case .duel: duel != nil
        case .value: value != nil
        }
    }

    /// `duelReaderOrder`: the history, the duel if offered, the value if supplied.
    var readerCards: [PlayerDuelPageCard10868] {
        PlayerDuelPageCard10868.allCases.filter(isMounted)
    }

    func readerShows(_ card: PlayerDuelPageCard10868) -> Bool { isMounted(card) }

    /// The held card, or its own explicit unavailable reading — never blank,
    /// never a neighbour.
    func readerContent(_ card: PlayerDuelPageCard10868) -> ReaderContent {
        readerShows(card) ? .card(card) : .unavailable(card, name: name(card))
    }

    /// Whether the held catalogue selection still opens exactly one original.
    /// The existing Details shows its own unavailable content otherwise.
    func originalAvailable(_ selection: OriginalMarketDetails9483.Selection?) -> Bool {
        OriginalMarketDetails9483.content(catalogue: input.catalogue, selection: selection) != nil
    }

    var aboutContentAvailable: Bool { input.about != nil }

    /// The reader cards either side of `card`, in reader order. No wrap.
    func neighbours(_ card: PlayerDuelPageCard10868) -> (previous: PlayerDuelPageCard10868?, next: PlayerDuelPageCard10868?) {
        let cards = readerCards
        guard let index = cards.firstIndex(of: card) else { return (nil, nil) }
        let previous = index > 0 ? cards[index - 1] : nil
        let next = index + 1 < cards.count ? cards[index + 1] : nil
        return (previous, next)
    }

    func name(_ card: PlayerDuelPageCard10868) -> String {
        switch card {
        case .history: input.cards.historyName
        case .duel: input.cards.duelName
        case .value: input.cards.valueName
        }
    }

    var showsStream: Bool { duel != nil }

    var showsCatalogue: Bool { input.catalogueWords != nil }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && input.about != nil && Self.readable(input.header.aboutLabel) != nil
    }

    /// The page and the full-size history show the About entry.
    func aboutEntry(mode: PlayerDuelPageMode10868, canOpen: Bool) -> Bool {
        switch mode {
        case .page, .reader(.history): aboutAvailable(canOpen: canOpen)
        case .reader, .original, .about: false
        }
    }

    func valueLinkAvailable(canOpen: Bool) -> Bool {
        canOpen && value != nil && Self.readable(input.cards.valueLink) != nil
    }

    /// Where the owner's optional value-reader link sits — at most one place,
    /// never a ranked story or a new card.
    enum ValueLinkPlacement: Equatable {
        /// Beneath the duel, inside its card (and its full-size reader).
        case inDuelCard
        /// No duel is offered: directly on the page, in the story area before All props.
        case onPage
        /// No value input, no owner words or no opener: no control at all.
        case absent
    }

    func valueLinkPlacement(canOpen: Bool) -> ValueLinkPlacement {
        guard valueLinkAvailable(canOpen: canOpen) else { return .absent }
        return duel != nil ? .inDuelCard : .onPage
    }

    static func closeLabel(_ mode: PlayerDuelPageMode10868) -> String {
        switch mode {
        case .reader: Words.backToGame
        case .page, .original, .about: Words.done
        }
    }

    static func readable(_ text: String?) -> String? {
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }

    // MARK: Private display copies of the owner's anchor

    /// The full-size history: the owner's input with ONLY the expand slot
    /// removed — the reader is already the expanded view, so a live expand
    /// there would be an enabled no-op. Every series, point, clock, domain,
    /// readout, key, layout and other owner action is the owner's, unchanged.
    static func readerAnchor(_ anchor: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        copy(anchor, windows: anchor.windows, scale: anchor.scale, moreOriginals: anchor.moreOriginals,
             details: anchor.details, expand: nil, inspect: anchor.inspect, previous: anchor.previous,
             next: anchor.next, series: anchor.series)
    }

    /// The page anchor when no owner handles its actions: the expand slot is
    /// the owner's, unchanged, and every other action in
    /// `FieldHistoryGeometry10868.actions` — each window choice, scale, more
    /// originals, details, inspect, previous, next and each original's choose
    /// — is drawn disabled (`isAvailable: false`). Nothing else changes.
    static func expandOnlyAnchor(_ anchor: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        let windows = anchor.windows.map { windows in
            FieldHistoryWindows10868(
                groupLabel: windows.groupLabel,
                choices: windows.choices.map {
                    FieldHistoryWindowChoice10868(action: disabled($0.action), isSelected: $0.isSelected)
                })
        }
        let series = anchor.series.map { series in
            FieldHistorySeries10868(
                id: series.id, name: series.name, shape: series.shape, tint: series.tint,
                runs: series.runs, links: series.links, labelPointID: series.labelPointID,
                before: series.before, recorded: series.recorded, absentWords: series.absentWords,
                choose: series.choose.map(disabled), keyContext: series.keyContext)
        }
        return copy(anchor, windows: windows, scale: anchor.scale.map(disabled),
                    moreOriginals: anchor.moreOriginals.map(disabled), details: anchor.details.map(disabled),
                    expand: anchor.expand, inspect: anchor.inspect.map(disabled),
                    previous: anchor.previous.map(disabled), next: anchor.next.map(disabled), series: series)
    }

    /// The same action, drawn disabled: id, words and spoken words unchanged.
    static func disabled(_ action: FieldHistoryAction10868) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: action.id, label: action.label, spokenLabel: action.spokenLabel, isAvailable: false)
    }

    /// The owner's input with only the named action slots and series replaced.
    /// Every other field — including each defaulted `var` — is passed through
    /// explicitly, so none can silently reset.
    private static func copy(_ anchor: FieldHistoryInput10868,
                             windows: FieldHistoryWindows10868?,
                             scale: FieldHistoryAction10868?,
                             moreOriginals: FieldHistoryAction10868?,
                             details: FieldHistoryAction10868?,
                             expand: FieldHistoryAction10868?,
                             inspect: FieldHistoryAction10868?,
                             previous: FieldHistoryAction10868?,
                             next: FieldHistoryAction10868?,
                             series: [FieldHistorySeries10868]) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: anchor.title, caption: anchor.caption, series: series,
            selection: anchor.selection, domain: anchor.domain, ceiling: anchor.ceiling,
            yTicks: anchor.yTicks, xTicks: anchor.xTicks, guides: anchor.guides, breaks: anchor.breaks,
            readout: anchor.readout, markKey: anchor.markKey,
            comparisonExplanation: anchor.comparisonExplanation, notes: anchor.notes,
            summary: anchor.summary, plotHeight: anchor.plotHeight,
            unboundReadingWords: anchor.unboundReadingWords, plotUnavailableWords: anchor.plotUnavailableWords,
            windows: windows, scale: scale, moreOriginals: moreOriginals,
            details: details, expand: expand, inspect: inspect,
            previous: previous, next: next, inspection: anchor.inspection,
            layout: anchor.layout,
            probabilityLowerBound: anchor.probabilityLowerBound,
            probabilityRangeExplanation: anchor.probabilityRangeExplanation,
            selectedReadout: anchor.selectedReadout, inspectionRingShape: anchor.inspectionRingShape,
            plotAbsence: anchor.plotAbsence, showsKey: anchor.showsKey
        )
    }

    /// The arrangements to try, in order — the hockey screen's own rule.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [HockeyJourneyPageArrangement10868] {
        HockeyJourneyPageModel10868.arrangements(sizeClass: sizeClass, accessibilitySize: accessibilitySize)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum PlayerDuelPageAccessibilityID10868 {
    static let page = "playerDuelPage10868.page"
    static let header = "playerDuelPage10868.header"
    static let about = "playerDuelPage10868.about"
    static let anchor = "playerDuelPage10868.anchor"
    static let stories = "playerDuelPage10868.stories"
    static let valueLink = "playerDuelPage10868.valueLink"
    static let catalogue = "playerDuelPage10868.catalogue"
    static let original = "playerDuelPage10868.original"
    static let aboutContent = "playerDuelPage10868.aboutContent"
    static let unavailable = "playerDuelPage10868.unavailable"
    static let back = "playerDuelPage10868.back"
    static func card(_ card: PlayerDuelPageCard10868) -> String { "playerDuelPage10868.card.\(card.rawValue)" }
    static func reader(_ card: PlayerDuelPageCard10868) -> String { "playerDuelPage10868.reader.\(card.rawValue)" }
    static func pager(_ card: PlayerDuelPageCard10868) -> String { "playerDuelPage10868.pager.\(card.rawValue)" }
}

// MARK: - Page view

struct PlayerDuelEventPagePresentation10868: View {
    typealias Stream = StoryStreamPresentation10868
    typealias Details = OriginalMarketDetails9483

    let input: PlayerDuelPageInput10868
    var mode: PlayerDuelPageMode10868 = .page
    /// The host's held catalogue selection, inside the owner's scope.
    var selection: Details.Selection? = nil
    /// The page anchor as routed by the host; nil draws the owner's input with no control.
    var pageAnchor: PlayerDuelPageAnchorDisplay10868? = nil
    /// The full-size history as routed by the host; nil draws the reader copy with no control.
    var readerAnchor: PlayerDuelPageAnchorDisplay10868? = nil
    var onStoryIntent: ((Stream.Intent) -> Void)? = nil
    /// Opens one full-size card (the value link and the reader pager).
    var onOpenReader: ((PlayerDuelPageCard10868) -> Void)? = nil
    var onAbout: (() -> Void)? = nil
    /// A catalogue card's exact selection, for the host to hold and route.
    var onOriginalSelect: ((Details.Selection) -> Void)? = nil
    var onDuelSelect: ((String) -> Void)? = nil
    /// Non-nil only when the duel's current selected original routes to exactly one catalogue original.
    var onDuelDetails: ((String) -> Void)? = nil
    var onValueSelect: ((String) -> Void)? = nil
    /// Non-nil only when the value card's current selected original routes to exactly one catalogue original.
    var onValueDetails: ((String) -> Void)? = nil
    /// Caller-supplied portrait for an exact player id; nil draws none.
    var portrait: ((String) -> AnyView)? = nil
    /// The host's Back / Done for the shown mode, offered inside unavailable
    /// content as well as in the host's toolbar. Nil: no in-content Back.
    var onClose: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 360
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: PlayerDuelPageModel10868 { PlayerDuelPageModel10868(input) }

    /// A card's own action, after the stream's activation hook when the card
    /// sits in the stream. No host callback: no action at all.
    static func relay<Value>(_ action: ((Value) -> Void)?,
                             through activation: StoryStreamCardActivation10868?) -> ((Value) -> Void)? {
        guard let action else { return nil }
        guard let activation else { return action }
        return { value in
            activation.request()
            action(value)
        }
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual Views, each with the host's own callbacks

    private var showsAbout: Bool { model.aboutEntry(mode: mode, canOpen: onAbout != nil) }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        let display = (reader ? readerAnchor : pageAnchor)
            ?? PlayerDuelPageAnchorDisplay10868(
                input: reader ? PlayerDuelPageModel10868.readerAnchor(input.anchor) : input.anchor)
        return FieldProbabilityHistoryPresentation10868(
            input: display.input,
            onAction: display.onAction,
            onInspectionChoice: display.onInspectionChoice,
            onPlotPosition: display.onPlotPosition
        )
    }

    /// `activation` is the stream's hook for the card in the stream; nil at full size.
    func duelContent(activation: StoryStreamCardActivation10868? = nil) -> PlayerDuelPresentation10868? {
        model.duel.map {
            PlayerDuelPresentation10868(
                input: $0,
                onSelect: Self.relay(onDuelSelect, through: activation),
                onDetails: Self.relay(onDuelDetails, through: activation),
                portrait: portrait
            )
        }
    }

    func valueContent() -> PlayerDuelValuePresentation10868? {
        model.value.map {
            PlayerDuelValuePresentation10868(input: $0, onSelect: onValueSelect, onDetails: onValueDetails)
        }
    }

    /// The owner's catalogue, unchanged, with the host's select callback.
    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        input.catalogueWords.map {
            OriginalMarketCatalogueView9483(
                catalogue: input.catalogue, selection: selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: input.catalogueLabels,
                tint: DS.blue, onSelect: onOriginalSelect
            )
        }
    }

    /// The existing Details for the held selection. No recorded history: the
    /// recorded-history Details is a probability story.
    func originalDetailsContent() -> OriginalMarketDetailsView9483 {
        OriginalMarketDetailsView9483(catalogue: input.catalogue, selection: selection, tint: DS.blue,
                                      recorded: nil, onHistory: nil)
    }

    func openAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        onAbout?()
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 16) {
            header
            let arrangements = PlayerDuelPageModel10868.arrangements(
                sizeClass: sizeClass,
                accessibilitySize: typeSize.isAccessibilitySize
            )
            if arrangements == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    sideBySide
                    stacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.page)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            secondary
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            secondary
                .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    /// The owner's eyebrow, the About entry, then the game words.
    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            let eyebrow = PlayerDuelPageModel10868.readable(input.header.eyebrow)
            if eyebrow != nil || showsAbout {
                HStack(alignment: .center, spacing: 12) {
                    if let eyebrow {
                        Text(eyebrow)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    } else {
                        Spacer(minLength: 0)
                    }
                    if showsAbout {
                        aboutButton
                    }
                }
            }
            Text(input.header.title)
                .font(.title2.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Text(input.header.state)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let quality = PlayerDuelPageModel10868.readable(input.header.quality) {
                Text(quality)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.header)
    }

    /// The ⓘ entry to the owner's About, spoken with its label.
    @ViewBuilder private var aboutButton: some View {
        if let label = PlayerDuelPageModel10868.readable(input.header.aboutLabel) {
            Button(action: openAbout) {
                Image(systemName: "info.circle")
                    .font(.title3)
                    .foregroundStyle(DS.textPrimary)
                    .frame(minWidth: controlSize, minHeight: controlSize)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(label)
            .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.about)
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(PlayerDuelPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.anchor)
    }

    /// The stream (the duel only) — or, with no duel offered, the owner's
    /// optional value link — then the owner's All props.
    private var secondary: some View {
        VStack(alignment: .leading, spacing: 16) {
            if model.showsStream {
                StoryStreamPresentationView10868(input.stream, onIntent: onStoryIntent) { card, activation in
                    storyCell(card, activation)
                }
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.stories)
            }
            valueLink(at: .onPage, activation: nil)
            if model.showsCatalogue, let catalogue = catalogueContent() {
                catalogue
                    .padding(16)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .modifier(PlayerDuelPageCardSurface10868())
                    .accessibilityElement(children: .contain)
                    .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.catalogue)
            }
        }
    }

    /// The duel card for its own stream id; any other id draws nothing.
    @ViewBuilder private func storyCell(_ card: Stream.Card, _ activation: StoryStreamCardActivation10868) -> some View {
        if card.id == PlayerDuelPageCard10868.duel.rawValue, let duel = duelContent(activation: activation) {
            VStack(alignment: .leading, spacing: 8) {
                duel
                valueLink(at: .inDuelCard, activation: activation)
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(PlayerDuelPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.card(.duel))
        }
    }

    /// The value link's action at `placement`: the host's opener for the value
    /// reader (after the stream's activation hook when in the stream), only
    /// where the model places the link. Elsewhere nil — no control, no duplicate.
    func valueLinkAction(at placement: PlayerDuelPageModel10868.ValueLinkPlacement,
                         activation: StoryStreamCardActivation10868?) -> (() -> Void)? {
        guard placement != .absent, model.valueLinkPlacement(canOpen: onOpenReader != nil) == placement,
              let open = Self.relay(onOpenReader, through: activation) else { return nil }
        return { open(.value) }
    }

    /// The owner's link to the optional value reader, where the model places it.
    @ViewBuilder private func valueLink(at placement: PlayerDuelPageModel10868.ValueLinkPlacement,
                                        activation: StoryStreamCardActivation10868?) -> some View {
        if let action = valueLinkAction(at: placement, activation: activation),
           let label = PlayerDuelPageModel10868.readable(input.cards.valueLink) {
            Button(action: action) {
                HStack(spacing: 6) {
                    Text(label)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Image(systemName: "chevron.right")
                        .font(.subheadline.weight(.semibold))
                        .accessibilityHidden(true)
                }
                .foregroundStyle(DS.blue)
                .frame(minHeight: controlSize)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.valueLink)
        }
    }

    // MARK: Readers

    /// The same leaf and input, full size, under the compact game words, with
    /// the reader order's previous and next cards. A held card whose admitted
    /// input was withdrawn shows its own unavailable reading and Back — never
    /// a blank sheet, never another card.
    @ViewBuilder private func reader(_ card: PlayerDuelPageCard10868) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            compactHeader
            switch model.readerContent(card) {
            case .card:
                switch card {
                case .history:
                    historyContent(reader: true)
                case .duel:
                    if let duel = duelContent() {
                        duel
                        valueLink(at: .inDuelCard, activation: nil)
                    }
                case .value:
                    valueContent()
                }
                pager(card)
            case .unavailable(_, let name):
                PlayerDuelPageUnavailableContent10868(
                    title: name, words: PlayerDuelPageModel10868.Words.readerUnavailable,
                    backLabel: PlayerDuelPageModel10868.Words.backToGame, onBack: onClose)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.reader(card))
    }

    /// Previous and next reader cards in the approved order; nothing to open, no button.
    @ViewBuilder private func pager(_ card: PlayerDuelPageCard10868) -> some View {
        let around = model.neighbours(card)
        if let open = onOpenReader, around.previous != nil || around.next != nil {
            HStack(alignment: .center, spacing: 12) {
                if let previous = around.previous {
                    Button { open(previous) } label: {
                        HStack(spacing: 6) {
                            Image(systemName: "chevron.left").accessibilityHidden(true)
                            Text(model.name(previous)).fixedSize(horizontal: false, vertical: true)
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.pager(previous))
                }
                Spacer(minLength: 0)
                if let next = around.next {
                    Button { open(next) } label: {
                        HStack(spacing: 6) {
                            Text(model.name(next)).fixedSize(horizontal: false, vertical: true)
                            Image(systemName: "chevron.right").accessibilityHidden(true)
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.pager(next))
                }
            }
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.header.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                Text(input.header.state)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if showsAbout {
                aboutButton
            }
        }
    }

    // MARK: The selected original's Details

    /// The existing Details, which shows its own unavailable content when the
    /// held selection no longer opens exactly one original; then a Done too.
    private var originalMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            originalDetailsContent()
            if !model.originalAvailable(selection), let onClose {
                Button(action: onClose) {
                    Text(PlayerDuelPageModel10868.Words.done)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.back)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.original)
    }

    // MARK: About

    /// The owner's About, or its explicit unavailable words and Done.
    private var aboutMode: some View {
        VStack(alignment: .leading, spacing: 12) {
            compactHeader
            if let about = input.about {
                Text(about.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                ForEach(Array(about.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                    Text(paragraph)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
            } else {
                PlayerDuelPageUnavailableContent10868(
                    title: nil, words: PlayerDuelPageModel10868.Words.aboutUnavailable,
                    backLabel: PlayerDuelPageModel10868.Words.done, onBack: onClose)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.aboutContent)
    }
}

/// Open content whose admitted input is gone: its own name (when it has one),
/// the explicit words, and a working Back. Static otherwise; it offers no
/// other story or original.
struct PlayerDuelPageUnavailableContent10868: View {
    let title: String?
    let words: String
    let backLabel: String
    var onBack: (() -> Void)? = nil

    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let title = PlayerDuelPageModel10868.readable(title) {
                Text(title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            Text(words)
                .font(.subheadline)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            if let onBack {
                Button(action: onBack) {
                    Text(backLabel)
                        .font(.body.weight(.semibold))
                        .foregroundStyle(DS.blue)
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.back)
            }
        }
        .frame(maxWidth: .infinity, minHeight: 120, alignment: .topLeading)
        .padding(16)
        .modifier(PlayerDuelPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(PlayerDuelPageAccessibilityID10868.unavailable)
    }
}

/// The reference's white card on the page surface.
private struct PlayerDuelPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
