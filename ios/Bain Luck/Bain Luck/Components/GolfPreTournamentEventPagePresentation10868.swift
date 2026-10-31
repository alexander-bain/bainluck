import SwiftUI

// #10868 — the pre-tournament golf page: an archived tournament-winner market
// read before play, with no score, round, finish, projection or result. A fan
// sees the owner's eyebrow, title and archive context with a compact About
// control; the followed golfers' readouts for the exact selected hour — each
// golfer's own figure with its own date, or the owner's "not recorded" words —
// over the named, shape-keyed "Chance to win" history; then the owner's
// 24-hour movement card; and the entry to every original. The history and the
// movement card open full size as the same Views with the same inputs, and the
// golfer chooser is the accepted chooser content the host already presents.
//
// Presentation only, from the approved pre-tournament golf page reference —
// its page, chooser and source-facts components and their styles, with
// `golfJourney.css` — and the golf native-ready composition record. Their
// capture loader, admission checks, frame and cohort election, ceiling
// rounding, hour list, stepping, reducer, colour slots, label spreading, trace
// names, change arithmetic, movement ranking and scale, chooser modes, bands
// and paging, percentage and clock formatting, sheets and focus memory are NOT
// ported. The leaves are the actual accepted Views and types:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor: its runs and
//     gaps, hollow and filled marks, inspection ring, direct name labels, Auto
//     or full range, any-hour inspection, earlier/later and its controls;
//   • `VolleyballFieldReadoutsPresentation10868` — the readouts, exactly as
//     accepted: while an hour is inspected each golfer shows only that hour's
//     own slot, and a readout highlights only through the history's own live
//     choose action;
//   • `GolfBeforeMovementPresentation10868` — the 24-hour movement card, on its
//     own before-phase gate, pinning through the owner's choose action;
//   • `FieldContenderChooserPresentation10868` — the golfer chooser content,
//     under the owner's own chooser hierarchy (below);
//   • `OriginalMarketCatalogueView9483` / `OriginalMarketDetailsView9483` —
//     every original and the held original's Details;
//   • `GolfEventPageCard10868`, `GolfEventPageCardFrame10868`, the golf page's
//     arrangement rule, `FieldEventPageReaderHeader10868`,
//     `FieldEventPageAbout10868` with its content view,
//     `FieldEventPageOriginals10868`, the field page's hold helpers, the
//     history presentation copy and the finite, never-shorter full-size height.
//
// Why not the golf page itself: its stories always mount a finish card, with
// absence words when there is no finish, and this page has no finish or
// contender card at all; its full-size history keeps the page height; it has
// no selected-hour readouts over the history; and it has no originals,
// Details or About content.
//
// This page carries no phase of its own and claims none. The movement card is
// mounted only while its own input says it is before the event; nothing here
// infers a phase from a clock, a price or a boundary.
//
// Readouts and key: while no golfer carries key context, a presentation copy
// of the history hides the shared key, so the readouts and the slots the
// readouts leave out are not shown twice. The copy keeps every series, run,
// mark, label point, readout, inspection, mark-key word, action, range and
// plot field; only its height, expand control and key visibility differ, and
// the owner's history input is never changed. With key context the owner's key
// stays, and that unchanged shared key still shows every resolved slot.
//
// Heights: the page uses the history's own plot height; full size uses the
// owner's full-size height only when it is finite, positive and taller.
//
// Chooser hierarchy: when the owner supplies it, the chooser shows the owner's
// modes, the bands the owner finds relevant, and the current page words with
// Previous and Next — never one button per group. Each control names one exact
// group id of the owner's full group list and acts through the chooser's own
// `chooseGroup(id:)`, under the chooser's own control-id rule; nothing here
// parses an id, counts a page, sorts or ranks. The shared chooser then draws a
// presentation copy whose browse groups are only those whose id is the selected
// group's or one of the chooser's own control ids, so it resolves the selection,
// a missing or duplicated group and every id collision exactly as from the full
// list. Every other chooser field, and the owner's input, are unchanged.
//
// Actions: on the page, in the chooser, the catalogue and Details, each action
// calls the owner's interaction hook once, then the owner's exact callback with
// its exact value. Full-size content keeps the exact callbacks with no hook.
// Without a callback there is no control and no hook call; building or reading
// the view calls nothing.
//
// Layout: with no mounted movement card and no All-props action the stories
// column has nothing to show, so the anchor stands alone at the full width and
// no empty column is reserved — decided only from those two facts, never from
// rows, numbers, dates or a phase; a mounted movement card with no rows still
// counts, with the owner's own words. Otherwise a compact width or an
// accessibility size stacks the anchor above the stories, and a regular or
// unspecified width places them side by side while both keep their minimum
// widths, otherwise stacks. The host owns the scroll,
// navigation, sheets, Back/Done, focus, reader paging, the selected hour, the
// cohort, the pin, the highlight, the range choice, ranking and every update.
// This view keeps no state, runs no timer and presents nothing of its own.
//
// Host binding still owed — not available at this base: an owner that admits
// the market's originals by exact identity, the followed cohort with stable
// tints and shapes, the qualified hourly runs through the selected hour with
// first-captured marks and label points, the selected-hour readouts, the
// range, the any-hour inspection and earlier/later targets, the exact 24-hour
// pairs with their words and scale, the chooser catalogue, groups and pin, the
// originals and About text, and maps every callback.

/// How the page places the anchor and the stories.
nonisolated enum GolfPreTournamentEventPageArrangement10868: Equatable {
    /// The stories column has nothing to show: the anchor alone, full width.
    case anchorAlone
    case stacked
    case sideBySide
}

/// What the host's container is showing, chosen by the host.
nonisolated enum GolfPreTournamentEventPageMode10868: Equatable {
    /// The tournament screen body.
    case page
    /// One card's full-size content: the history or the movement card.
    case reader(GolfEventPageCard10868)
    /// The golfer chooser content.
    case chooser
    /// Every original.
    case catalogue
    /// The held original's Details.
    case original
    /// The owner's About.
    case about
}

/// The owner's words for the screen.
nonisolated struct GolfPreTournamentEventPageCopy10868: Equatable {
    /// The owner's eyebrow; nil draws none.
    let eyebrow: String?
    let title: String
    /// The owner's archive context; nil draws none.
    let context: String?
    /// The About control's spoken label; nil draws no control.
    let aboutLabel: String?
    let aboutHint: String?
    /// Spoken name of the readouts.
    let readoutsLabel: String
    /// Spoken name of the stories group.
    let storiesLabel: String
    /// The entry to every original; nil draws none.
    let allPropsLabel: String?
}

nonisolated struct GolfPreTournamentEventPageInput10868: Equatable {
    let copy: GolfPreTournamentEventPageCopy10868
    /// The compact words above full-size, chooser, catalogue and About content.
    let reader: FieldEventPageReaderHeader10868
    let history: FieldHistoryInput10868
    /// The owner's full-size plot height; used only when finite, positive and taller.
    var readerPlotHeight: CGFloat? = nil
    /// The 24-hour movement card; mounted only with its own before phase.
    let movement: GolfBeforeMovementInput10868?
    let movementFrame: GolfEventPageCardFrame10868
    let chooser: FieldChooserInput10868?
    let about: FieldEventPageAbout10868?
    /// The owner's chooser hierarchy; nil keeps the chooser's own group list.
    var chooserNavigation: GolfPreTournamentChooserNavigation10868? = nil
}

/// One owner control that selects one exact existing browse group.
nonisolated struct GolfPreTournamentChooserTarget10868: Equatable {
    /// The owner's words on the control ("Top chances", "A–D", "Next").
    let label: String
    /// Spoken instead of `label` when supplied ("Next golfers").
    var spokenLabel: String? = nil
    /// The owner's count words beside a band; nil draws none.
    var countText: String? = nil
    /// The exact id of one group in the owner's full browse list — never parsed or built here.
    let groupID: String
    /// The owner's current mode or band.
    var isSelected: Bool = false
}

/// The owner's chooser hierarchy: modes, the relevant bands and bounded pages.
nonisolated struct GolfPreTournamentChooserNavigation10868: Equatable {
    /// Spoken name of the modes ("Explore golfers by").
    let modesLabel: String
    /// The owner's modes, in the owner's order.
    let modes: [GolfPreTournamentChooserTarget10868]
    /// The owner's words for the current mode; nil draws none.
    var context: String? = nil
    /// Spoken name of the bands ("Browse by last name").
    let bandsLabel: String
    /// Only the bands the owner finds relevant now; empty draws none.
    var bands: [GolfPreTournamentChooserTarget10868] = []
    /// The owner's current page words; nil draws none.
    var page: String? = nil
    /// The owner's earlier page; nil draws none.
    var previous: GolfPreTournamentChooserTarget10868? = nil
    /// The owner's later page; nil draws none.
    var next: GolfPreTournamentChooserTarget10868? = nil
}

/// Which part of the hierarchy a view draws: above or below the chooser.
nonisolated enum GolfPreTournamentChooserNavigationPart10868: Equatable {
    /// The modes, the owner's mode words and the relevant bands.
    case controls
    /// Previous, the current page words and Next.
    case pages
}

/// The hierarchy's rules on the owner's full chooser.
nonisolated struct GolfPreTournamentChooserNavigationModel10868: Equatable {
    let navigation: GolfPreTournamentChooserNavigation10868
    /// The owner's chooser with every group, for exact target resolution.
    let chooser: FieldChooserInput10868

    /// The exact control a target hands back: the chooser's own group action
    /// for the one group of the owner's full list carrying the target's id,
    /// only with a callback. A wrong, foreign, blank, duplicated or colliding
    /// id hands back nothing — never a neighbouring group.
    func control(_ target: GolfPreTournamentChooserTarget10868?, canControl: Bool) -> FieldChooserControl10868? {
        guard canControl, let target,
              let group = chooser.browse?.groups.first(where: { $0.id == target.groupID }),
              case .control(let control)? = FieldChooserModel10868(chooser).groupAction(group, canControl: true)
        else { return nil }
        return control
    }

    var context: String? { FieldEventPageModel10868.readable(navigation.context) }
    var page: String? { FieldEventPageModel10868.readable(navigation.page) }

    /// The control's spoken words: the owner's spoken label or label, then its count.
    static func spoken(_ target: GolfPreTournamentChooserTarget10868) -> String {
        ([target.spokenLabel ?? target.label] + [target.countText].compactMap { $0 }).joined(separator: ", ")
    }
}

nonisolated enum GolfPreTournamentAccessibilityID10868 {
    static let page = "golfPreTournament10868.page"
    static let anchor = "golfPreTournament10868.anchor"
    static let stories = "golfPreTournament10868.stories"
    static let about = "golfPreTournament10868.about"
    static let allProps = "golfPreTournament10868.allProps"
    static let readerHeader = "golfPreTournament10868.readerHeader"
    static let readerAbout = "golfPreTournament10868.readerHeader.about"
    static let chooser = "golfPreTournament10868.chooser"
    static let catalogue = "golfPreTournament10868.catalogue"
    static let original = "golfPreTournament10868.original"
    static let aboutContent = "golfPreTournament10868.aboutContent"
    static let chooserModes = "golfPreTournament10868.chooser.modes"
    static let chooserBands = "golfPreTournament10868.chooser.bands"
    static let chooserPage = "golfPreTournament10868.chooser.page"
    static let chooserPrevious = "golfPreTournament10868.chooser.previous"
    static let chooserNext = "golfPreTournament10868.chooser.next"
    static func chooserMode(_ label: String) -> String { "golfPreTournament10868.chooser.mode.\(label)" }
    static func chooserBand(_ label: String) -> String { "golfPreTournament10868.chooser.band.\(label)" }
    static func card(_ card: GolfEventPageCard10868) -> String { "golfPreTournament10868.card.\(card)" }
    static func open(_ card: GolfEventPageCard10868) -> String { "golfPreTournament10868.open.\(card)" }
}

/// What the page mounts and draws, resolved once per input.
nonisolated struct GolfPreTournamentEventPageModel10868: Equatable {
    let input: GolfPreTournamentEventPageInput10868

    init(_ input: GolfPreTournamentEventPageInput10868) {
        self.input = input
    }

    /// The movement card, only while its own input is before the event —
    /// never coerced from another phase.
    var movement: GolfBeforeMovementInput10868? {
        guard let movement = input.movement, movement.movement.phase == .before else { return nil }
        return movement
    }

    /// The stories under the anchor: the movement card alone, when mounted.
    /// No finish or contender card, and no absence filler.
    var stories: [GolfEventPageCard10868] {
        movement == nil ? [] : [.movement]
    }

    /// Full-size content exists for the anchor and for a mounted story.
    func readerShows(_ card: GolfEventPageCard10868) -> Bool {
        card == .history || stories.contains(card)
    }

    /// Whether the readouts stand in for the shared key: while no golfer
    /// carries key context. With key context the owner's key stays.
    var hidesSharedKey: Bool {
        input.history.series.allSatisfy { FieldHistoryGeometry10868.keyContext($0) == nil }
    }

    /// The history the page or full size draws, and its readouts read: the
    /// owner's input with only its height, expand control and key visibility
    /// changed. Full size is never shorter than the page, and only a finite,
    /// positive owner height enlarges it.
    func history(reader: Bool) -> FieldHistoryInput10868 {
        let history = input.history
        return VolleyballFieldEventPageModel10868.presentationCopy(
            history,
            plotHeight: reader
                ? RugbyMatchEventPageModel10868.readerPlotHeight(input.readerPlotHeight, history: history.plotHeight)
                : history.plotHeight,
            expand: reader ? nil : history.expand,
            showsKey: hidesSharedKey ? false : history.showsKey)
    }

    /// The card to open, only for a mounted story with readable open words and
    /// a callback. The anchor opens through its own expand action.
    func openAction(_ card: GolfEventPageCard10868, canOpen: Bool) -> GolfEventPageCard10868? {
        guard canOpen, stories.contains(card), FieldEventPageModel10868.readable(input.movementFrame.openLabel) != nil else { return nil }
        return card
    }

    /// The owner's About, when it carries readable words.
    var about: FieldEventPageAbout10868? {
        guard let about = input.about,
              FieldEventPageModel10868.readable(about.title) != nil
                || about.paragraphs.contains(where: { FieldEventPageModel10868.readable($0) != nil })
        else { return nil }
        return about
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && about != nil && FieldEventPageModel10868.readable(input.copy.aboutLabel) != nil
    }

    /// Full-size content's compact heading shows the About entry; the page has its own.
    func aboutEntry(mode: GolfPreTournamentEventPageMode10868, canOpen: Bool) -> Bool {
        guard case .reader = mode else { return false }
        return aboutAvailable(canOpen: canOpen)
    }

    func allPropsAvailable(canOpen: Bool) -> Bool {
        canOpen && FieldEventPageModel10868.readable(input.copy.allPropsLabel) != nil
    }

    /// The owner's chooser hierarchy on the owner's full chooser, while both exist.
    var chooserNavigation: GolfPreTournamentChooserNavigationModel10868? {
        guard let chooser = input.chooser, let navigation = input.chooserNavigation else { return nil }
        return GolfPreTournamentChooserNavigationModel10868(navigation: navigation, chooser: chooser)
    }

    /// The chooser the shared leaf draws. With the owner's hierarchy, a copy
    /// whose browse groups are only those whose id is the selected group's or
    /// one of the chooser's own control ids — the selection, a missing or
    /// duplicated group and every id collision resolve exactly as from the
    /// full list, and no wall of group buttons is drawn. Every other field is
    /// the owner's. Without the hierarchy, the owner's chooser unchanged.
    var chooserPresentation: FieldChooserInput10868? {
        guard let chooser = input.chooser else { return nil }
        guard input.chooserNavigation != nil, let browse = chooser.browse else { return chooser }
        let kept = Set([browse.selectedGroupID, browse.id, chooser.more?.id].compactMap { $0 })
        let shown = FieldChooserBrowse10868(
            id: browse.id, title: browse.title, expanded: browse.expanded, note: browse.note,
            groupsLabel: browse.groupsLabel, groups: browse.groups.filter { kept.contains($0.id) },
            selectedGroupID: browse.selectedGroupID, noGroupWords: browse.noGroupWords,
            groupUnavailableWords: browse.groupUnavailableWords, emptyGroupWords: browse.emptyGroupWords)
        return FieldChooserInput10868(
            scope: chooser.scope, intro: chooser.intro, featured: chooser.featured, context: chooser.context,
            more: chooser.more, browse: shown, catalogue: chooser.catalogue, frame: chooser.frame,
            selected: chooser.selected, unavailableWords: chooser.unavailableWords, chooseHint: chooser.chooseHint)
    }

    /// Whether the stories column has anything to show: the mounted movement
    /// card — even with no paired rows, it keeps the owner's own words — or an
    /// All-props entry that acts. Nothing else is read.
    func hasStories(canOpenAllProps: Bool) -> Bool {
        movement != nil || allPropsAvailable(canOpen: canOpenAllProps)
    }

    /// The arrangements to try, in order: the anchor alone when the stories
    /// column would be empty; otherwise the golf page's own rule — stacked at a
    /// compact width or an accessibility size, else side by side, then stacked.
    func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool,
                      canOpenAllProps: Bool) -> [GolfPreTournamentEventPageArrangement10868] {
        guard hasStories(canOpenAllProps: canOpenAllProps) else { return [.anchorAlone] }
        return GolfEventPageModel10868.arrangements(sizeClass: sizeClass, accessibilitySize: accessibilitySize)
            .map { $0 == GolfEventPageArrangement10868.sideBySide ? GolfPreTournamentEventPageArrangement10868.sideBySide : .stacked }
    }
}

struct GolfPreTournamentEventPagePresentation10868: View {
    let input: GolfPreTournamentEventPageInput10868
    var mode: GolfPreTournamentEventPageMode10868 = .page
    /// Every original and the held original's Details; nil: neither.
    var originals: FieldEventPageOriginals10868? = nil
    var onAbout: (() -> Void)? = nil
    /// Opens the host's reader on a story card.
    var onOpenCard: ((GolfEventPageCard10868) -> Void)? = nil
    /// Every history action id: a readout's highlight id, range, expand,
    /// earlier/later, the owner's chooser entry and the rest.
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    /// Pinning a golfer, from the movement card or the chooser.
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onChooserControl: ((FieldChooserControl10868) -> Void)? = nil
    var onAllProps: (() -> Void)? = nil
    var onOriginalSelect: ((OriginalMarketDetails9483.Selection) -> Void)? = nil
    var onOriginalHistory: ((OriginalMarketDetails9483.HistoryIntent) -> Void)? = nil
    /// Called once before a page, chooser, catalogue or Details action reaches its owner.
    var onInteraction: (() -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    var model: GolfPreTournamentEventPageModel10868 { GolfPreTournamentEventPageModel10868(input) }

    private func held<Value>(_ action: ((Value) -> Void)?, reader: Bool) -> ((Value) -> Void)? {
        FieldEventPagePresentation10868.held(action, by: reader ? nil : onInteraction)
    }

    // MARK: Leaves — the actual accepted Views with the host's own callbacks

    func aboutOpener() -> (() -> Void)? {
        guard model.aboutAvailable(canOpen: onAbout != nil), let onAbout else { return nil }
        return onAbout
    }

    /// The readouts over the history copy the same content draws.
    func readoutsContent(reader: Bool) -> VolleyballFieldReadoutsPresentation10868 {
        VolleyballFieldReadoutsPresentation10868(
            history: model.history(reader: reader), label: input.copy.readoutsLabel,
            onChoose: held(onHistoryAction, reader: reader))
    }

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        FieldProbabilityHistoryPresentation10868(
            input: model.history(reader: reader),
            onAction: held(onHistoryAction, reader: reader),
            onInspectionChoice: held(onHistoryInspectionChoice, reader: reader),
            onPlotPosition: held(onHistoryPlotPosition, reader: reader))
    }

    /// The same card and input on the page and full size.
    func movementContent(reader: Bool) -> GolfBeforeMovementPresentation10868? {
        model.movement.map { GolfBeforeMovementPresentation10868(input: $0, onChoose: held(onChoose, reader: reader)) }
    }

    func chooserContent() -> FieldContenderChooserPresentation10868? {
        model.chooserPresentation.map {
            FieldContenderChooserPresentation10868(input: $0, onChoose: held(onChoose, reader: false),
                                                   onControl: held(onChooserControl, reader: false))
        }
    }

    /// The owner's hierarchy above or below the chooser, with the same held control callback.
    func chooserNavigationContent(_ part: GolfPreTournamentChooserNavigationPart10868) -> GolfPreTournamentChooserNavigationPresentation10868? {
        model.chooserNavigation.map {
            GolfPreTournamentChooserNavigationPresentation10868(model: $0, part: part, onControl: held(onChooserControl, reader: false))
        }
    }

    func aboutContent() -> FieldEventPageAboutContent10868? {
        model.about.map { FieldEventPageAboutContent10868(about: $0) }
    }

    func catalogueContent() -> OriginalMarketCatalogueView9483? {
        originals.map {
            OriginalMarketCatalogueView9483(
                catalogue: $0.catalogue, selection: $0.selection, heading: $0.heading, context: $0.context,
                emptyWords: $0.emptyWords, unavailableChoice: $0.unavailableChoice, labels: $0.labels,
                tint: $0.tint, onSelect: held(onOriginalSelect, reader: false))
        }
    }

    func originalDetailsContent() -> OriginalMarketDetailsView9483? {
        originals.map {
            OriginalMarketDetailsView9483(
                catalogue: $0.catalogue, selection: $0.selection, tint: $0.tint,
                recorded: $0.recorded, onHistory: held(onOriginalHistory, reader: false))
        }
    }

    /// Hands a mounted story to the host, after the hook, only while its open control is drawn.
    func open(_ card: GolfEventPageCard10868) {
        guard let card = model.openAction(card, canOpen: onOpenCard != nil) else { return }
        held(onOpenCard, reader: false)?(card)
    }

    func openPageAbout() {
        FieldEventPagePresentation10868.heldAction(aboutOpener(), by: onInteraction)?()
    }

    /// Full-size content's About: the exact callback.
    func openAbout() {
        aboutOpener()?()
    }

    func openAllProps() {
        guard model.allPropsAvailable(canOpen: onAllProps != nil) else { return }
        FieldEventPagePresentation10868.heldAction(onAllProps, by: onInteraction)?()
    }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .chooser: chooserMode
            case .catalogue: catalogueMode
            case .original: originalMode
            case .about: aboutMode
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            heading
            let arrangements = model.arrangements(sizeClass: sizeClass, accessibilitySize: typeSize.isAccessibilitySize,
                                                  canOpenAllProps: onAllProps != nil)
            if arrangements == [.anchorAlone] {
                anchor
            } else if arrangements == [.stacked] {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    sideBySide
                    stacked
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.page)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            anchor
            stories
        }
    }

    private var sideBySide: some View {
        HStack(alignment: .top, spacing: 24) {
            anchor
                .frame(minWidth: anchorMinWidth, maxWidth: .infinity, alignment: .topLeading)
                .layoutPriority(1)
            stories
                .frame(minWidth: storiesMinWidth, maxWidth: .infinity, alignment: .topLeading)
        }
    }

    private var heading: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 6) {
                if let eyebrow = FieldEventPageModel10868.readable(input.copy.eyebrow) {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Text(input.copy.title)
                    .font(.title.bold())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let context = FieldEventPageModel10868.readable(input.copy.context) {
                    Text(context)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutAvailable(canOpen: onAbout != nil) {
                aboutButton(action: openPageAbout, id: GolfPreTournamentAccessibilityID10868.about)
            }
        }
    }

    private var anchor: some View {
        VStack(alignment: .leading, spacing: 14) {
            readoutsContent(reader: false)
            historyContent(reader: false)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(GolfPreTournamentCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 20) {
            if let movement = movementContent(reader: false) {
                VStack(alignment: .leading, spacing: 10) {
                    cardHeading(.movement)
                    movement
                }
                .padding(16)
                .frame(maxWidth: .infinity, alignment: .leading)
                .modifier(GolfPreTournamentCardSurface10868())
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.card(.movement))
            }
            if model.allPropsAvailable(canOpen: onAllProps != nil), let label = input.copy.allPropsLabel {
                Button(action: openAllProps) {
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
                    .frame(minHeight: controlSize)
                    .modifier(GolfPreTournamentCardSurface10868())
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.allProps)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.stories)
    }

    /// The owner's eyebrow and the open control, only while it acts.
    @ViewBuilder private func cardHeading(_ card: GolfEventPageCard10868) -> some View {
        let eyebrow = FieldEventPageModel10868.readable(input.movementFrame.eyebrow)
        let openable = model.openAction(card, canOpen: onOpenCard != nil) != nil
        if eyebrow != nil || openable {
            HStack(alignment: .center, spacing: 8) {
                if let eyebrow {
                    Text(eyebrow)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer(minLength: 8)
                if openable, let label = input.movementFrame.openLabel {
                    Button { open(card) } label: {
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.blue)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(label)
                    .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.open(card))
                }
            }
        }
    }

    private func aboutButton(action: @escaping () -> Void, id: String) -> some View {
        Button(action: action) {
            Image(systemName: "info.circle")
                .font(.title3)
                .foregroundStyle(DS.textPrimary)
                .frame(minWidth: controlSize, minHeight: controlSize)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(input.copy.aboutLabel ?? "")
        .accessibilityHint(input.copy.aboutHint ?? "")
        .accessibilityIdentifier(id)
    }

    // MARK: Full size

    /// The same Views and inputs, full size, under the compact words. A card
    /// this page does not mount has no content.
    @ViewBuilder private func reader(_ card: GolfEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 16) {
                compactHeader
                switch card {
                case .history:
                    readoutsContent(reader: true)
                    historyContent(reader: true)
                case .movement:
                    movementContent(reader: true)
                case .finish, .contenders:
                    EmptyView()
                }
            }
        }
    }

    private var compactHeader: some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text(input.reader.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .accessibilityAddTraits(.isHeader)
                if let state = FieldEventPageModel10868.readable(input.reader.state) {
                    Text(state)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            if model.aboutEntry(mode: mode, canOpen: onAbout != nil) {
                aboutButton(action: openAbout, id: GolfPreTournamentAccessibilityID10868.readerAbout)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.readerHeader)
    }

    // MARK: Chooser, every original, the held original's Details and About

    @ViewBuilder private var chooserMode: some View {
        if let chooser = chooserContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                if let controls = chooserNavigationContent(.controls) {
                    controls
                }
                chooser
                if let pages = chooserNavigationContent(.pages) {
                    pages
                }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.chooser)
        }
    }

    @ViewBuilder private var catalogueMode: some View {
        if let catalogue = catalogueContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                catalogue
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.catalogue)
        }
    }

    @ViewBuilder private var originalMode: some View {
        if let details = originalDetailsContent() {
            details
                .accessibilityElement(children: .contain)
                .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.original)
        }
    }

    @ViewBuilder private var aboutMode: some View {
        if let content = aboutContent() {
            VStack(alignment: .leading, spacing: 12) {
                compactHeader
                content
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.aboutContent)
        }
    }
}

/// The owner's chooser hierarchy: the modes, the owner's mode words and the
/// relevant bands above the chooser; Previous, the page words and Next below
/// it. Every control is a 44-point target that hands the host one exact
/// `chooseGroup(id:)` once, or is static content when it cannot act. The
/// modes and bands wrap and the pages row stacks at accessibility sizes.
struct GolfPreTournamentChooserNavigationPresentation10868: View {
    let model: GolfPreTournamentChooserNavigationModel10868
    let part: GolfPreTournamentChooserNavigationPart10868
    /// The host's chooser control callback; nil: every control is static.
    var onControl: ((FieldChooserControl10868) -> Void)? = nil

    /// Every control's minimum target before Dynamic Type scaling.
    static let minimumTarget: CGFloat = 44

    /// The modes and bands stack, and the pages row stacks, at accessibility sizes.
    static func stacks(accessibilitySize: Bool) -> Bool { accessibilitySize }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = GolfPreTournamentChooserNavigationPresentation10868.minimumTarget

    private var navigation: GolfPreTournamentChooserNavigation10868 { model.navigation }

    /// The exact control a target hands back here, only while it acts.
    func action(_ target: GolfPreTournamentChooserTarget10868?) -> FieldChooserControl10868? {
        model.control(target, canControl: onControl != nil)
    }

    /// Hands the target's exact control to the host, only while it acts.
    func choose(_ target: GolfPreTournamentChooserTarget10868?) {
        guard let control = action(target), let onControl else { return }
        onControl(control)
    }

    var body: some View {
        switch part {
        case .controls: controls
        case .pages: pages
        }
    }

    private var controls: some View {
        VStack(alignment: .leading, spacing: 10) {
            if !navigation.modes.isEmpty {
                targets(navigation.modes, label: navigation.modesLabel,
                        id: GolfPreTournamentAccessibilityID10868.chooserMode,
                        groupID: GolfPreTournamentAccessibilityID10868.chooserModes)
            }
            if let context = model.context {
                Text(context)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !navigation.bands.isEmpty {
                targets(navigation.bands, label: navigation.bandsLabel,
                        id: GolfPreTournamentAccessibilityID10868.chooserBand,
                        groupID: GolfPreTournamentAccessibilityID10868.chooserBands)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder private func targets(_ targets: [GolfPreTournamentChooserTarget10868], label: String,
                                      id: @escaping (String) -> String, groupID: String) -> some View {
        let buttons = ForEach(Array(targets.enumerated()), id: \.offset) { _, target in
            self.target(target, id: id(target.label))
        }
        Group {
            if Self.stacks(accessibilitySize: typeSize.isAccessibilitySize) {
                VStack(alignment: .leading, spacing: 8) { buttons }
            } else {
                FlowLayout(spacing: 8) { buttons }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(label)
        .accessibilityIdentifier(groupID)
    }

    private func target(_ target: GolfPreTournamentChooserTarget10868, id: String) -> some View {
        control(target) {
            HStack(spacing: 6) {
                if target.isSelected {
                    Image(systemName: "checkmark").font(.caption2.weight(.bold))
                }
                Text(target.label)
                    .font(.subheadline.weight(target.isSelected ? .semibold : .regular))
                    .fixedSize(horizontal: false, vertical: true)
                if let count = target.countText {
                    Text(count).font(.caption).foregroundStyle(DS.textSecondary)
                }
            }
            .foregroundStyle(target.isSelected ? DS.blue : DS.textPrimary)
            .padding(.horizontal, 12)
            .frame(minWidth: controlSize, minHeight: controlSize)
            .overlay(RoundedRectangle(cornerRadius: 10)
                .strokeBorder(target.isSelected ? DS.blue : DS.border, lineWidth: target.isSelected ? 2 : 1))
            .contentShape(Rectangle())
        }
        .accessibilityLabel(GolfPreTournamentChooserNavigationModel10868.spoken(target))
        .accessibilityAddTraits(target.isSelected ? .isSelected : [])
        .accessibilityIdentifier(id)
    }

    private var pages: some View {
        let layout = Self.stacks(accessibilitySize: typeSize.isAccessibilitySize)
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
        return layout {
            if let previous = navigation.previous {
                pageControl(previous, id: GolfPreTournamentAccessibilityID10868.chooserPrevious)
            }
            if let page = model.page {
                Text(page)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity)
                    .accessibilityIdentifier(GolfPreTournamentAccessibilityID10868.chooserPage)
            }
            if let next = navigation.next {
                pageControl(next, id: GolfPreTournamentAccessibilityID10868.chooserNext)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func pageControl(_ target: GolfPreTournamentChooserTarget10868, id: String) -> some View {
        control(target) {
            Text(target.label)
                .font(.body.weight(.semibold))
                .foregroundStyle(action(target) == nil ? DS.textSecondary : DS.blue)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
                .frame(minWidth: controlSize, minHeight: controlSize)
                .contentShape(Rectangle())
        }
        .accessibilityLabel(GolfPreTournamentChooserNavigationModel10868.spoken(target))
        .accessibilityIdentifier(id)
    }

    /// A button only while the target acts; otherwise static content.
    @ViewBuilder private func control<Content: View>(_ target: GolfPreTournamentChooserTarget10868,
                                                     @ViewBuilder content: () -> Content) -> some View {
        if action(target) != nil {
            Button { choose(target) } label: { content() }
                .buttonStyle(.plain)
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

/// The reference's white card on the page surface.
private struct GolfPreTournamentCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}
