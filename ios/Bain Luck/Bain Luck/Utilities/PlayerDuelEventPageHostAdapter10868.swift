import SwiftUI

/// #10868 — THE PLAYER-DUEL SCREEN'S HOST GLUE AND ADMISSION.
///
/// PILLARS: FORMATTING / TRUTH. SHIP: the player-duel native page composes its
/// game probability anchor, player comparison, contract-value reader and exact
/// original Details without mixing their meanings.
///
/// HELD PRESENTATION, NOT A DELIVERED PAGE. No production owner supplies a
/// player-duel bundle at this base, and nothing here pretends to: there is no
/// supplier, flag, route or mount in this file. With `supplied` nil the host
/// draws nothing and `applies` is false. Which events get this screen, and
/// whether a release switch gates it, are Native's calls (routing and
/// `ReleaseSurfaces` are read-only here).
///
/// What an owner must supply (`Supplied`), all typed with existing types:
///   - the event and phase it built the bundle for — another event's or
///     another phase's bundle is no bundle (`admit`);
///   - the game words, card words and About;
///   - the anchor: its own game-winner history as a `FieldHistoryInput10868`
///     (independent per-side closes over the approved full range; never the
///     duel's outright chances, never a blend or complement); nil draws the
///     existing unavailable slot;
///   - the accepted leaves' own inputs: `PlayerDuelInput10868` (outright
///     chances or their words, counts and results each independently
///     admitted) and `PlayerDuelValueInput10868` (cents values in their own
///     DTO);
///   - its All props: an existing `OriginalMarketDetails9483.Catalogue`, every
///     associated original it admits, each carrying its own mode, readings,
///     grade and About exactly as that owner resolved it — a genuine
///     probability original with its comparison and marks, a half-payout
///     contract with an explicit missing outright chance and owner-labelled
///     value rows (never a `.comparison`, a placement or a historical quote,
///     whose labels are fixed to chance words) — plus labels and words;
///   - the exact catalogue identity each leaf original id opens (`routes`), as
///     that owner proved it. No route is inferred from a label, an id's shape
///     or a position.
///
/// What the host owns: only the screen's reading state — the mode shown, the
/// held original selection (applied to BOTH leaves through their own
/// `selectedOriginalID`), the held catalogue selection, and whether a reader
/// is open. It reads no view model, opens no network, subscribes to nothing,
/// runs no timer, ranks nothing, holds no chart state (no window, scale,
/// inspection, cursor or clock) and never classifies, filters, relabels or
/// prices an original. The catalogue scope is the owner's; the host compares
/// it and never builds one.
///
/// Chart routing (`anchorDisplay`): expand is page-owned and opens the
/// full-size history; with an owner handler every other action reaches the
/// owner exactly once, after the hold; with none, a private display copy keeps
/// the expand live and draws every other action disabled; the full-size
/// history drops only its expand slot. Inspection choices and plot positions
/// reach the owner exactly when the owner supplies a handler. Owner handlers
/// never reach the host's unavailable slot.
///
/// OPEN, NOT PAID HERE: the seven owner inputs (duel association and
/// pairing; independent full-range game-winner history and its chart
/// handlers; dated contract-value endpoints; cents words; clocked player
/// actuals; NBA game and card words; a served half-payout unit marker so the
/// catalogue owner can build All props); the player-threshold obligation,
/// which these two cards do not cover; full-range rendering and performance;
/// real live delivery; compile, XCTest, fit, VoiceOver, portraits, mount,
/// independent review, Integrator and TestFlight acceptance.
enum PlayerDuelEventPageAdapter10868 {
    typealias Details = OriginalMarketDetails9483

    /// Everything an owner admits for one event's player-duel page.
    struct Supplied: Equatable {
        /// The event the bundle was built for.
        let eventID: Int
        /// The phase the bundle was built for.
        let phase: HockeyJourneyPagePhase10868
        let header: PlayerDuelPageHeader10868
        /// The owner's game-winner history; nil draws the unavailable slot.
        var anchor: FieldHistoryInput10868? = nil
        var duel: PlayerDuelInput10868? = nil
        var value: PlayerDuelValueInput10868? = nil
        let cards: PlayerDuelPageCardWords10868
        var about: PlayerDuelPageAbout10868? = nil
        /// Every associated original the owner admits, in its order, unchanged.
        var catalogue: Details.Catalogue? = nil
        var catalogueLabels: [Details.Identity: String] = [:]
        /// Nil: no All props section.
        var catalogueWords: PlayerDuelPageCatalogueWords10868? = nil
        /// Leaf original id → the exact catalogue identity it opens.
        var routes: [String: Details.Identity] = [:]
    }

    /// The owner's handlers for the anchor's controls. Nil (production today):
    /// only the page-owned expand works.
    struct AnchorControls {
        /// Every non-expand action id, exactly as the history View hands it back.
        var onAction: ((String) -> Void)? = nil
        var onInspectionChoice: ((String) -> Void)? = nil
        var onPlotPosition: ((Double) -> Void)? = nil
    }

    /// The host's own reading state, as the builder takes it.
    struct Held: Equatable {
        /// One exact original id, applied to both leaves; nil keeps the owner's.
        var selectedOriginalID: String? = nil
        var readerOpen = false
        var wide = false
    }

    /// The host's open content and held choices, with pure transitions. The
    /// host keeps one in `@State`; its sheet shows `mode`. Return context is
    /// kept here, locally — no app routing or Native navigation is touched:
    ///   - Details or About opened from a full-size card sits over that card;
    ///     Done returns to the SAME card with the same held selections;
    ///   - Details or About opened from the page returns to the page;
    ///   - "Back to game" on a card returns to the page;
    ///   - an interactive dismissal returns to the page, choices kept.
    /// A card whose input is withdrawn stays the held card (its own
    /// unavailable reading is drawn); nothing here moves to a neighbour.
    struct Session: Equatable {
        enum Panel: Equatable {
            case original
            case about
        }

        /// The full-size card open in the sheet, if any.
        var reader: PlayerDuelPageCard10868? = nil
        /// Details or About, over `reader` when one is open, else over the page.
        var panel: Panel? = nil
        /// The exact original held on both leaves.
        var selectedOriginalID: String? = nil
        /// The exact catalogue selection Details shows, inside the owner's scope.
        var catalogueSelection: Details.Selection? = nil

        /// What the sheet shows; nil: the page alone.
        var mode: PlayerDuelPageMode10868? {
            switch panel {
            case .original?: return .original
            case .about?: return .about
            case nil: return reader.map { PlayerDuelPageMode10868.reader($0) }
            }
        }

        var isPresented: Bool { mode != nil }

        /// A card from the page, the stream, the value link or the pager.
        mutating func openReader(_ card: PlayerDuelPageCard10868) {
            reader = card
            panel = nil
        }

        /// Details for an exact selection, over whatever is open.
        mutating func openDetails(_ selection: Details.Selection) {
            catalogueSelection = selection
            panel = .original
        }

        mutating func openAbout() {
            panel = .about
        }

        mutating func select(_ originalID: String) {
            selectedOriginalID = originalID
        }

        /// Done / Back: a panel returns to the card it was opened from (or the
        /// page); a card returns to the page.
        mutating func close() {
            if panel != nil {
                panel = nil
            } else {
                reader = nil
            }
        }

        /// The sheet was dismissed interactively: the page, choices kept.
        mutating func dismiss() {
            panel = nil
            reader = nil
        }
    }

    // MARK: Admission

    /// The bundle, only for this exact event at the page's own phase, with a
    /// duel (if any) built for that same phase. Otherwise nothing — never a
    /// neighbour, never a partial bundle.
    static func admit(_ supplied: Supplied?, event: EventDetail, now: Date) -> Supplied? {
        guard let supplied, supplied.eventID == event.id,
              supplied.phase == HockeyJourneyPageAdapter10868.phase(event, now: now) else { return nil }
        if let duel = supplied.duel, duel.phase != supplied.phase.contributionPhase { return nil }
        return supplied
    }

    // MARK: Held selection

    /// The owner's duel with the held original applied through the leaf's own
    /// selection field. Nil keeps the owner's selection.
    static func holding(_ duel: PlayerDuelInput10868, original: String?) -> PlayerDuelInput10868 {
        guard let original else { return duel }
        return PlayerDuelInput10868(phase: duel.phase, eyebrow: duel.eyebrow, title: duel.title,
                                    context: duel.context, payoutRule: duel.payoutRule, sides: duel.sides,
                                    selectedOriginalID: original)
    }

    static func holding(_ value: PlayerDuelValueInput10868, original: String?) -> PlayerDuelValueInput10868 {
        guard let original else { return value }
        return PlayerDuelValueInput10868(eyebrow: value.eyebrow, title: value.title, context: value.context,
                                         quantity: value.quantity, tieRule: value.tieRule, ticks: value.ticks,
                                         rows: value.rows, phaseNote: value.phaseNote, selectedOriginalID: original)
    }

    // MARK: Stream

    /// `duelStoryOrder.ts`: the duel is offered only as a resolved pair at its
    /// own phase, before play or with every player's count supplied. The value
    /// card is never offered here.
    static func offersDuel(_ duel: PlayerDuelInput10868?, phase: HockeyJourneyPagePhase10868) -> Bool {
        guard let duel, duel.phase == phase.contributionPhase, duel.isPairResolved else { return false }
        if phase == .before { return true }
        return duel.sides.allSatisfy { side in
            if case .shots = side.actual { return true }
            return false
        }
    }

    /// The stream's own scope: one per event and phase, as the stream requires.
    /// Not a catalogue scope.
    static func streamScope(_ event: EventDetail, phase: HockeyJourneyPagePhase10868) -> String {
        "player-duel:\(event.id):\(phase)"
    }

    static func stream(scope: String, words: PlayerDuelPageCardWords10868, duelOffered: Bool,
                       readerOpen: Bool, wide: Bool) -> StoryStreamPresentation10868 {
        let duel = StoryStreamPresentation10868.CardRef(scope: scope, id: PlayerDuelPageCard10868.duel.rawValue)
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: words.streamEyebrow, heading: words.streamHeading,
            cards: duelOffered ? [StoryStreamPresentation10868.Card(id: duel.id, name: words.duelName)] : [],
            primary: duelOffered ? duel : nil,
            wide: wide,
            readerOpen: readerOpen)
    }

    /// What a stream intent asks the host to do.
    enum StreamRoute: Equatable {
        case hold
        case openReader(PlayerDuelPageCard10868)
        /// The one-card stream offers no playback or browsing.
        case ignore
    }

    static func route(_ intent: StoryStreamPresentation10868.Intent, scope: String) -> StreamRoute {
        switch intent {
        case .interaction:
            return .hold
        case .open(let ref):
            guard ref.scope == scope, ref.id == PlayerDuelPageCard10868.duel.rawValue else { return .ignore }
            return .openReader(.duel)
        case .browse, .pause, .resume, .applyUpdates:
            return .ignore
        }
    }

    // MARK: Page input

    /// The page input from the passed values alone — pure, so every changed
    /// value reaches the screen on the next pass. Nil without an admitted
    /// bundle: a held presentation draws nothing.
    static func build(event: EventDetail, supplied: Supplied?, now: Date, held: Held = Held()) -> PlayerDuelPageInput10868? {
        guard let admitted = admit(supplied, event: event, now: now) else { return nil }
        let phase = admitted.phase
        let duel = admitted.duel.map { holding($0, original: held.selectedOriginalID) }
        let value = admitted.value.map { holding($0, original: held.selectedOriginalID) }
        let offered = offersDuel(duel, phase: phase)
        return PlayerDuelPageInput10868(
            phase: phase,
            header: admitted.header,
            anchor: admitted.anchor ?? HockeyJourneyHistoryAdapter10868.unavailable(event: event, phase: phase),
            anchorIsOwners: admitted.anchor != nil,
            duel: duel,
            duelOffered: offered,
            value: value,
            stream: stream(scope: streamScope(event, phase: phase), words: admitted.cards, duelOffered: offered,
                           readerOpen: held.readerOpen, wide: held.wide),
            cards: admitted.cards,
            about: admitted.about,
            catalogue: admitted.catalogue,
            catalogueLabels: admitted.catalogueLabels,
            catalogueWords: admitted.catalogueWords)
    }

    // MARK: Details

    /// The catalogue selection an owner route names: exactly one original with
    /// that identity in the owner's catalogue scope, whose Details content
    /// exists (the catalogue chooser's own "opens" rule over
    /// `OriginalMarketDetails9483.original(in:selection:)`). Else nil.
    static func detailsSelection(_ originalID: String?, supplied: Supplied?) -> Details.Selection? {
        guard let originalID, let supplied, let identity = supplied.routes[originalID],
              let catalogue = supplied.catalogue else { return nil }
        let selection = Details.Selection(scope: catalogue.scope, identity: identity)
        return Details.content(catalogue: catalogue, selection: selection) == nil ? nil : selection
    }

    /// A leaf's Details callback for THIS pass: non-nil only when the leaf's
    /// current selected original routes to exactly one catalogue original.
    /// The hold first, then the exact selection.
    static func detailsCallback(_ selectedOriginalID: String?, supplied: Supplied?, hold: (() -> Void)?,
                                open: @escaping (Details.Selection) -> Void) -> ((String) -> Void)? {
        guard detailsSelection(selectedOriginalID, supplied: supplied) != nil else { return nil }
        return { id in
            guard let selection = detailsSelection(id, supplied: supplied) else { return }
            hold?()
            open(selection)
        }
    }

    // MARK: Anchor routing

    /// The anchor the history View receives, with routed callbacks.
    ///
    /// - The page: with an owner action handler, the owner's input unchanged;
    ///   the live expand id opens the full-size history, every other id goes
    ///   to the owner, each exactly once after the hold. With none, and a
    ///   live expand, `PlayerDuelPageModel10868.expandOnlyAnchor` draws every
    ///   other action disabled and the callback acts on the expand id alone.
    ///   With neither, no action callback: every control is static.
    /// - The full-size history (`reader`): `readerAnchor` drops only the
    ///   expand slot; every owner action is forwarded as above, or none.
    /// - Inspection choices and plot positions: forwarded after the hold when
    ///   the owner supplies a handler; otherwise nil.
    /// - The unavailable slot (`anchorIsOwners` false): no owner callback.
    static func anchorDisplay(_ input: PlayerDuelPageInput10868, reader: Bool, controls: AnchorControls?,
                              hold: (() -> Void)?, openHistory: @escaping () -> Void) -> PlayerDuelPageAnchorDisplay10868 {
        let owner = input.anchorIsOwners ? controls : nil
        let base = reader ? PlayerDuelPageModel10868.readerAnchor(input.anchor) : input.anchor
        let inspection: ((String) -> Void)? = owner?.onInspectionChoice.map { send in
            { id in
                hold?()
                send(id)
            }
        }
        let plot: ((Double) -> Void)? = owner?.onPlotPosition.map { send in
            { x in
                hold?()
                send(x)
            }
        }
        let expandID = base.expand.flatMap { FieldHistoryGeometry10868.liveID($0, in: base) }
        if let forward = owner?.onAction {
            return PlayerDuelPageAnchorDisplay10868(
                input: base,
                onAction: { id in
                    hold?()
                    if let expandID, id == expandID {
                        openHistory()
                    } else {
                        forward(id)
                    }
                },
                onInspectionChoice: inspection,
                onPlotPosition: plot)
        }
        guard let expandID else {
            return PlayerDuelPageAnchorDisplay10868(input: base, onAction: nil,
                                                    onInspectionChoice: inspection, onPlotPosition: plot)
        }
        // No owner handler: the expand stays page-owned and working; every
        // other control is drawn disabled, so this guard is never reached by a
        // live control.
        return PlayerDuelPageAnchorDisplay10868(
            input: PlayerDuelPageModel10868.expandOnlyAnchor(base),
            onAction: { id in
                guard id == expandID else { return }
                hold?()
                openHistory()
            },
            onInspectionChoice: inspection,
            onPlotPosition: plot)
    }
}

/// #10868 — what `EventDetailView` WOULD mount for an event whose owner
/// supplies a player-duel bundle. NOT mounted: no route, flag or supplier
/// exists, and adding one is Native's call. With `supplied` nil it draws
/// nothing.
struct PlayerDuelEventPageHost10868: View {
    typealias A = PlayerDuelEventPageAdapter10868

    let event: EventDetail
    /// An owner's admitted bundle for this event; nil (production today) draws nothing.
    var supplied: A.Supplied? = nil
    /// The owner's chart handlers; nil keeps only the page-owned expand.
    var anchorControls: A.AnchorControls? = nil
    var now: Date = Date()
    /// The page's existing hold, requested BEFORE any reader action. Appearance
    /// and reads call nothing.
    var onInteraction: (() -> Void)? = nil
    /// Caller-supplied portrait for an exact player id; nil draws none.
    var portrait: ((String) -> AnyView)? = nil

    /// Only an event whose owner supplied an admissible bundle; no sport rule.
    static func applies(_ event: EventDetail, supplied: A.Supplied?, now: Date) -> Bool {
        A.admit(supplied, event: event, now: now) != nil
    }

    @State private var session = A.Session()
    @Environment(\.horizontalSizeClass) private var sizeClass

    var body: some View {
        Group {
            if let input = make() {
                page(input, mode: .page)
            }
        }
        .sheet(isPresented: Binding(get: { session.isPresented },
                                    set: { shown in if !shown { session.dismiss() } })) {
            NavigationStack {
                ScrollView {
                    sheetContent.padding(.horizontal, 16)
                }
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button(PlayerDuelPageModel10868.closeLabel(session.mode ?? .page)) { session.close() }
                    }
                }
            }
        }
    }

    /// The held mode over the current input. A bundle withdrawn while the
    /// sheet is open shows the explicit unavailable words and Back, never a
    /// blank sheet.
    @ViewBuilder private var sheetContent: some View {
        if let mode = session.mode {
            if let current = make() {
                page(current, mode: mode)
            } else {
                PlayerDuelPageUnavailableContent10868(
                    title: nil, words: PlayerDuelPageModel10868.Words.contentUnavailable,
                    backLabel: PlayerDuelPageModel10868.closeLabel(mode), onBack: { session.close() })
            }
        }
    }

    private func make() -> PlayerDuelPageInput10868? {
        A.build(event: event, supplied: supplied, now: now,
                held: A.Held(selectedOriginalID: session.selectedOriginalID, readerOpen: session.isPresented,
                             wide: sizeClass == .regular))
    }

    private func page(_ input: PlayerDuelPageInput10868, mode: PlayerDuelPageMode10868) -> PlayerDuelEventPagePresentation10868 {
        let admitted = A.admit(supplied, event: event, now: now)
        let hold = onInteraction
        return PlayerDuelEventPagePresentation10868(
            input: input,
            mode: mode,
            selection: session.catalogueSelection,
            pageAnchor: A.anchorDisplay(input, reader: false, controls: anchorControls, hold: hold,
                                        openHistory: { session.openReader(.history) }),
            readerAnchor: A.anchorDisplay(input, reader: true, controls: anchorControls, hold: hold,
                                          openHistory: {}),
            onStoryIntent: { intent in handle(intent, scope: input.stream.scope) },
            onOpenReader: { card in
                hold?()
                session.openReader(card)
            },
            onAbout: {
                hold?()
                session.openAbout()
            },
            onOriginalSelect: { chosen in
                hold?()
                session.openDetails(chosen)
            },
            onDuelSelect: { id in
                hold?()
                session.select(id)
            },
            onDuelDetails: A.detailsCallback(input.duel?.selection.side?.originalID, supplied: admitted, hold: hold,
                                             open: { chosen in session.openDetails(chosen) }),
            onValueSelect: { id in
                hold?()
                session.select(id)
            },
            onValueDetails: A.detailsCallback(input.value?.selection.row?.originalID, supplied: admitted, hold: hold,
                                              open: { chosen in session.openDetails(chosen) }),
            portrait: portrait,
            onClose: { session.close() })
    }

    private func handle(_ intent: StoryStreamPresentation10868.Intent, scope: String) {
        switch A.route(intent, scope: scope) {
        case .hold:
            onInteraction?()
        case .openReader(let card):
            onInteraction?()
            session.openReader(card)
        case .ignore:
            break
        }
    }
}
