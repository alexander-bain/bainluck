import SwiftUI

// #10868 — the golf tournament screen: one golf-reading presentation composed
// from the accepted native leaves. A fan sees the tournament's title and about
// entry, the owner's reading status with its Pause / Resume-updates control,
// the named "Chance to win" history front and centre, the selected golfer's
// finish expectations below it, and — before the first tee only — the
// pre-tournament contenders and "What changed?" cards. Each story card opens
// its own full-size content, and the golfer chooser is the same chooser
// content the host already presents.
//
// Presentation only, composed from the approved `GolfReadingReplay.tsx`,
// `GolfBeforeMovement.tsx` and `golfReadingReplay.css` / `golfJourney.css`
// (`.gj-hero`, `.gr-reading-status`, `.gbc-stories`, `.gbm-*`, `.gj-wide`,
// large-text variants) with their chart, finish, before-card and chooser
// mounts. The reference's replay timers, arrival simulation, hold reducer,
// period/scale/cohort election, comparison/pair election, sort by change,
// scale ceiling, movement formatting, source loaders and its own sheets are
// NOT ported. The leaves are the actual accepted Views:
//
//   • `FieldProbabilityHistoryPresentation10868` — the anchor;
//   • `GolfFinishExpectationPresentation10868` — finish expectations;
//   • `FieldOutlookBarsPresentation10868` — "Who starts strongest?", the
//     owner's before-tournament chances on one zero-based scale;
//   • `FieldContenderChooserPresentation10868` — the golfer chooser content.
//
// "What changed?" is the one bounded presentation built here, because the
// inherited signed-change card (`FieldMovementPresentation10868`) has no card
// before the event and its gate is not this file's to move. It keeps the
// actual `.before` phase and draws each golfer's signed percentage-point
// change from a shared zero-change line, beside equal Earlier / Later chances
// and the owner's two recorded times. Every rule behind it is the inherited
// movement card's own: the chooser's exact identity resolver, the owner's one
// pair per golfer, the tied endpoints, the raw change, the owner's change
// words, ticks and scale, and the shared bar geometry — drawn on the finish
// strips' half-mark inset so a change of exactly ±scale is a whole mark, with
// the measured axis labels (`FieldExpectationsAxisLayout10868`) on that same
// span. Nothing here elects a
// pair, a cohort, a first/latest clock, a scale or a formatted delta, ranks a
// golfer or smooths a value; a rounded pair of equal figures still draws its
// small raw change with the owner's words. Tapping a row pins that exact
// golfer through the host's own choose action — never an endpoint open.
//
// The host supplies each leaf's own immutable input, already admitted for the
// same snapshot; this layer groups them and never re-elects, reformats, copies
// or filters an observation, a name, a chance or a result. The page phase is
// the owner's explicit golf-reading phase (Before / recorded round / Final).
// A leaf whose own phase is not the page's is not mounted — never coerced to
// appear: the before cards appear only at Before and only with their own
// `.before` phase, and finish expectations only with the page's own phase, so
// a Final input's results never reach a Before page. Without an admissible
// finish, the finish card keeps the owner's absence words.
//
// The reading status is the owner's: its title, its held / pending words and
// at most one Pause or Resume-updates action with the owner's eligibility and
// words, handed back through the host's own history action callback. Nothing
// here holds, counts, times or resumes a reading, or calls a replay live.
// Without a callback the words stay and the action is not drawn.
//
// The full-size history is the same history input with its expanded layout
// and without its expand control; every series, selection, readout, range and
// other control is unchanged.
//
// Phone stacks the anchor above the stories; a regular or unspecified size
// class (a Mac window) places them side by side while both columns keep their
// minimum widths, otherwise it stacks too, and accessibility sizes always stack. Every leaf keeps its own plot
// heights, scaled type, missing states and accessibility.
//
// The host owns the scroll, navigation, sheets, Back/Done, focus, the selected
// golfer, the held reading and its resumption. This view keeps no state, runs
// no timer or animation, holds no subscription and presents no sheet or
// navigation of its own. Each mode below is content the host's existing
// container shows; every callback is the host's own closure handed to the leaf
// unchanged. With no callback, nothing pretends to act.
//
// Host binding still owed — not available at this base: an owner that admits,
// for one tournament snapshot, the history input, the selected golfer's finish
// slots and results, the before chances, the pre-tournament pair per displayed
// golfer with its scale and times, the chooser catalogue and selection, the
// page phase, status and words, and maps every callback to its existing
// controls. Before-phase child inputs must not carry later observations or
// chooser results; the history's observations and the chooser's result words
// are not filtered here.

/// One story or anchor the host may open full size.
nonisolated enum GolfEventPageCard10868: Hashable, CaseIterable {
    case history
    case finish
    case contenders
    case movement
}

/// What the host's container is showing, chosen by the host.
nonisolated enum GolfEventPageMode10868: Equatable {
    /// The tournament screen body.
    case page
    /// One card's full-size content.
    case reader(GolfEventPageCard10868)
    /// The golfer chooser content.
    case chooser
}

nonisolated enum GolfEventPageArrangement10868: Equatable {
    case stacked
    case sideBySide
}

/// The owner's frame words for one story card.
nonisolated struct GolfEventPageCardFrame10868: Equatable {
    /// "Before the first tee"; nil draws none.
    let eyebrow: String?
    /// Spoken name of the open control ("Expand finish expectations"); nil draws none.
    let openLabel: String?
}

/// The owner's words for the screen.
nonisolated struct GolfEventPageCopy10868: Equatable {
    /// "Recorded replay · Round 1"; nil draws none.
    let eyebrow: String?
    /// "Baycurrent Classic".
    let title: String
    /// "History through Oct 7, 7:01 PM PT"; nil draws none.
    let context: String?
    /// Spoken name of the about entry ("About recorded golf replay"); nil draws none.
    let aboutLabel: String?
    /// Spoken name of the stories group ("Tournament stories").
    let storiesLabel: String
    /// Shown in the finish card when no finish input fits this phase.
    let finishUnavailable: String
}

/// The owner's reading status and its one manual control.
nonisolated struct GolfEventPageStatus10868: Equatable {
    /// "Recorded replay held".
    let title: String
    /// "3 recorded updates waiting"; nil draws none.
    let words: String?
    /// The owner's Pause or Resume-updates action, handed back through the
    /// host's history action callback; its availability is the owner's.
    let action: FieldHistoryAction10868?
}

/// The owner's two recorded times, shown once above the rows.
nonisolated struct GolfBeforeMovementTimes10868: Equatable {
    /// "Oct 5, 10:39 AM PT".
    let earlier: String
    /// "Oct 6, 6:08 AM PT".
    let later: String
}

/// "What changed?": the inherited movement input, the owner's selected golfer
/// and the owner's two recorded times.
nonisolated struct GolfBeforeMovementInput10868: Equatable {
    /// Its phase is the card's own; its displayed order, pairs and scale are the owner's.
    let movement: FieldMovementInput10868
    /// Marked when the owner supplies it; never elected here.
    let selected: FieldChooserOriginalRef10868?
    /// Nil draws none; each endpoint then keeps its own clock line.
    let times: GolfBeforeMovementTimes10868?
}

nonisolated struct GolfEventPageInput10868: Equatable {
    /// The owner's golf-reading phase for the whole screen.
    let phase: GolfFinishPhase10868
    let copy: GolfEventPageCopy10868
    /// Nil draws no status.
    let status: GolfEventPageStatus10868?
    let history: FieldHistoryInput10868
    let finish: GolfFinishExpectationInput10868?
    let finishFrame: GolfEventPageCardFrame10868
    let contenders: FieldOutlookInput10868?
    let contendersFrame: GolfEventPageCardFrame10868
    let movement: GolfBeforeMovementInput10868?
    let movementFrame: GolfEventPageCardFrame10868
    let chooser: FieldChooserInput10868?
}

nonisolated enum GolfEventPageAccessibilityID10868 {
    static let page = "golfEventPage10868.page"
    static let anchor = "golfEventPage10868.anchor"
    static let stories = "golfEventPage10868.stories"
    static let about = "golfEventPage10868.about"
    static let status = "golfEventPage10868.status"
    static let statusAction = "golfEventPage10868.status.action"
    static func card(_ card: GolfEventPageCard10868) -> String { "golfEventPage10868.card.\(card)" }
    static func open(_ card: GolfEventPageCard10868) -> String { "golfEventPage10868.open.\(card)" }
}

/// Which leaves the page mounts, resolved once per input.
nonisolated struct GolfEventPageModel10868: Equatable {
    let input: GolfEventPageInput10868

    init(_ input: GolfEventPageInput10868) {
        self.input = input
    }

    /// The finish, only when its own phase is the page's.
    var finish: GolfFinishExpectationInput10868? {
        guard let finish = input.finish, finish.phase == input.phase else { return nil }
        return finish
    }

    /// Before the first tee only, with the card's own before phase.
    var contenders: FieldOutlookInput10868? {
        guard input.phase == .before, let contenders = input.contenders, contenders.phase == .before else { return nil }
        return contenders
    }

    /// Before the first tee only, with the card's own before phase.
    var movement: GolfBeforeMovementInput10868? {
        guard input.phase == .before, let movement = input.movement, movement.movement.phase == .before else { return nil }
        return movement
    }

    /// The story cards under the anchor, in the reference's order. The finish
    /// card is always present, with the owner's absence words when needed.
    var stories: [GolfEventPageCard10868] {
        [.finish] + (contenders == nil ? [] : [.contenders]) + (movement == nil ? [] : [.movement])
    }

    /// The anchor's full-size content: the same history in its expanded
    /// layout, without an expand control inside the reader. Every other field
    /// is the owner's, unchanged.
    var readerHistory: FieldHistoryInput10868 {
        let history = input.history
        return FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: history.series,
            selection: history.selection, domain: history.domain, ceiling: history.ceiling,
            yTicks: history.yTicks, xTicks: history.xTicks, guides: history.guides, breaks: history.breaks,
            readout: history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes,
            summary: history.summary, plotHeight: history.plotHeight,
            unboundReadingWords: history.unboundReadingWords, plotUnavailableWords: history.plotUnavailableWords,
            windows: history.windows, scale: history.scale, moreOriginals: history.moreOriginals,
            details: history.details, expand: nil, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection,
            layout: .expanded,
            probabilityLowerBound: history.probabilityLowerBound,
            probabilityRangeExplanation: history.probabilityRangeExplanation,
            selectedReadout: history.selectedReadout, inspectionRingShape: history.inspectionRingShape,
            plotAbsence: history.plotAbsence, showsKey: history.showsKey
        )
    }

    /// Full-size content exists for the anchor and for a story this phase shows.
    func readerShows(_ card: GolfEventPageCard10868) -> Bool {
        card == .history || stories.contains(card)
    }

    func frame(_ card: GolfEventPageCard10868) -> GolfEventPageCardFrame10868? {
        switch card {
        case .history: nil
        case .finish: input.finishFrame
        case .contenders: input.contendersFrame
        case .movement: input.movementFrame
        }
    }

    static func readable(_ words: String?) -> String? {
        guard let words, !words.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return words
    }

    /// The card to open, only for a story shown on this page, with readable
    /// open words and a callback. The anchor opens through its own expand action.
    func openAction(_ card: GolfEventPageCard10868, canOpen: Bool) -> GolfEventPageCard10868? {
        guard canOpen, stories.contains(card), Self.readable(frame(card)?.openLabel) != nil else { return nil }
        return card
    }

    func aboutAvailable(canOpen: Bool) -> Bool {
        canOpen && Self.readable(input.copy.aboutLabel) != nil
    }

    /// The owner's Pause / Resume-updates action, only with a callback,
    /// readable words and an id no history control also hands back — both
    /// reach the host's one history action callback.
    func statusAction(canAct: Bool) -> FieldHistoryAction10868? {
        guard canAct, let action = input.status?.action, !action.id.isEmpty,
              Self.readable(action.label) != nil,
              !FieldHistoryGeometry10868.actions(input.history).contains(where: { $0.id == action.id })
        else { return nil }
        return action
    }

    /// The arrangements to try, in order. Accessibility sizes and a compact
    /// width stack; a regular or unspecified width (a Mac window has no size
    /// class) tries side by side, then stacks — the columns' minimum widths
    /// decide which fits.
    static func arrangements(sizeClass: UserInterfaceSizeClass?, accessibilitySize: Bool) -> [GolfEventPageArrangement10868] {
        sizeClass != .compact && !accessibilitySize ? [.sideBySide, .stacked] : [.stacked]
    }
}

struct GolfEventPagePresentation10868: View {
    let input: GolfEventPageInput10868
    var mode: GolfEventPageMode10868 = .page
    var onAbout: (() -> Void)? = nil
    var onOpenCard: ((GolfEventPageCard10868) -> Void)? = nil
    /// The history's own actions and the status Pause / Resume-updates action.
    var onHistoryAction: ((String) -> Void)? = nil
    var onHistoryInspectionChoice: ((String) -> Void)? = nil
    var onHistoryPlotPosition: ((Double) -> Void)? = nil
    var onSelectFinish: ((String) -> Void)? = nil
    var onFinishDetails: ((String) -> Void)? = nil
    /// Choosing a golfer, from the contenders card, "What changed?" or the chooser.
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil
    var onChooserControl: ((FieldChooserControl10868) -> Void)? = nil
    var onOpenOriginal: ((FieldChooserOriginalRef10868) -> Void)? = nil

    @Environment(\.horizontalSizeClass) private var sizeClass
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .body) private var anchorMinWidth: CGFloat = 460
    @ScaledMetric(relativeTo: .body) private var storiesMinWidth: CGFloat = 340
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private var model: GolfEventPageModel10868 { GolfEventPageModel10868(input) }

    var body: some View {
        Group {
            switch mode {
            case .page: page
            case .reader(let card): reader(card)
            case .chooser: chooserContent()
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Leaves — the actual accepted Views, each with the host's own callbacks

    func historyContent(reader: Bool) -> FieldProbabilityHistoryPresentation10868 {
        FieldProbabilityHistoryPresentation10868(
            input: reader ? model.readerHistory : input.history,
            onAction: onHistoryAction,
            onInspectionChoice: onHistoryInspectionChoice,
            onPlotPosition: onHistoryPlotPosition
        )
    }

    func finishContent() -> GolfFinishExpectationPresentation10868? {
        model.finish.map {
            GolfFinishExpectationPresentation10868(input: $0, onSelectFinish: onSelectFinish, onDetails: onFinishDetails)
        }
    }

    func contendersContent() -> FieldOutlookBarsPresentation10868? {
        model.contenders.map {
            FieldOutlookBarsPresentation10868(input: $0, onChoose: onChoose, onOpenOriginal: onOpenOriginal)
        }
    }

    func movementContent() -> GolfBeforeMovementPresentation10868? {
        model.movement.map { GolfBeforeMovementPresentation10868(input: $0, onChoose: onChoose) }
    }

    func chooserContent() -> FieldContenderChooserPresentation10868? {
        input.chooser.map { FieldContenderChooserPresentation10868(input: $0, onChoose: onChoose, onControl: onChooserControl) }
    }

    /// Hands the card to the host, only when its open control is drawn.
    func open(_ card: GolfEventPageCard10868) {
        guard let card = model.openAction(card, canOpen: onOpenCard != nil) else { return }
        onOpenCard?(card)
    }

    func openAbout() {
        guard model.aboutAvailable(canOpen: onAbout != nil) else { return }
        onAbout?()
    }

    /// Hands the owner's status action id back, only while it is drawn and available.
    func actOnStatus() {
        guard let action = model.statusAction(canAct: onHistoryAction != nil), action.isAvailable else { return }
        onHistoryAction?(action.id)
    }

    // MARK: Page

    private var page: some View {
        VStack(alignment: .leading, spacing: 20) {
            heading
            let arrangements = GolfEventPageModel10868.arrangements(
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
        .accessibilityIdentifier(GolfEventPageAccessibilityID10868.page)
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
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .top, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    if let eyebrow = GolfEventPageModel10868.readable(input.copy.eyebrow) {
                        Text(eyebrow)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                    }
                    Text(input.copy.title)
                        .font(.title.bold())
                        .foregroundStyle(DS.textPrimary)
                        .accessibilityAddTraits(.isHeader)
                }
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
                if model.aboutAvailable(canOpen: onAbout != nil), let label = input.copy.aboutLabel {
                    Button(action: openAbout) {
                        Image(systemName: "info.circle")
                            .font(.title3)
                            .foregroundStyle(DS.textPrimary)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(label)
                    .accessibilityIdentifier(GolfEventPageAccessibilityID10868.about)
                }
            }
            status(compact: false)
            if let context = GolfEventPageModel10868.readable(input.copy.context) {
                Text(context)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// The owner's status words and its one Pause / Resume-updates control.
    @ViewBuilder private func status(compact: Bool) -> some View {
        if let status = input.status {
            let action = model.statusAction(canAct: onHistoryAction != nil)
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
                : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
            layout {
                VStack(alignment: .leading, spacing: compact ? 2 : 4) {
                    Text(status.title)
                        .font(compact ? .footnote.weight(.semibold) : .subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let words = GolfEventPageModel10868.readable(status.words) {
                        Text(words)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityElement(children: .combine)
                if let action {
                    Button(action: actOnStatus) {
                        Text(action.label)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.blue)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 12)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .background(RoundedRectangle(cornerRadius: 10).fill(DS.cardBg))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(DS.border, lineWidth: 1))
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(!action.isAvailable)
                    .opacity(action.isAvailable ? 1 : 0.4)
                    .accessibilityLabel(action.spokenLabel ?? action.label)
                    .accessibilityIdentifier(GolfEventPageAccessibilityID10868.statusAction)
                }
            }
            .padding(.vertical, compact ? 0 : 12)
            .overlay(alignment: .bottom) {
                if !compact { Rectangle().fill(DS.border).frame(height: 1) }
            }
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(GolfEventPageAccessibilityID10868.status)
        }
    }

    private var anchor: some View {
        historyContent(reader: false)
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .modifier(GolfEventPageCardSurface10868())
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(GolfEventPageAccessibilityID10868.anchor)
    }

    private var stories: some View {
        VStack(alignment: .leading, spacing: 20) {
            ForEach(model.stories, id: \.self) { card in
                storyCard(card)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(input.copy.storiesLabel)
        .accessibilityIdentifier(GolfEventPageAccessibilityID10868.stories)
    }

    private func storyCard(_ card: GolfEventPageCard10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            cardHeading(card)
            cardContent(card)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .modifier(GolfEventPageCardSurface10868())
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(GolfEventPageAccessibilityID10868.card(card))
    }

    @ViewBuilder private func cardHeading(_ card: GolfEventPageCard10868) -> some View {
        let eyebrow = GolfEventPageModel10868.readable(model.frame(card)?.eyebrow)
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
                if openable, let label = model.frame(card)?.openLabel {
                    Button { open(card) } label: {
                        Image(systemName: "arrow.up.right")
                            .font(.body.weight(.semibold))
                            .foregroundStyle(DS.blue)
                            .frame(minWidth: controlSize, minHeight: controlSize)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel(label)
                    .accessibilityIdentifier(GolfEventPageAccessibilityID10868.open(card))
                }
            }
        }
    }

    // MARK: Content shared by the page and the reader

    @ViewBuilder private func cardContent(_ card: GolfEventPageCard10868) -> some View {
        switch card {
        case .history:
            historyContent(reader: true)
        case .finish:
            if let finish = finishContent() {
                finish
            } else {
                Text(input.copy.finishUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        case .contenders:
            contendersContent()
        case .movement:
            movementContent()
        }
    }

    /// The same leaf and input, full size, for the host's existing reader,
    /// under the owner's compact status. A card this phase does not show has
    /// no content.
    @ViewBuilder private func reader(_ card: GolfEventPageCard10868) -> some View {
        if model.readerShows(card) {
            VStack(alignment: .leading, spacing: 12) {
                status(compact: true)
                cardContent(card)
            }
        }
    }
}

/// The reference's white card on the page surface.
private struct GolfEventPageCardSurface10868: ViewModifier {
    func body(content: Content) -> some View {
        content
            .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 20, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(DS.border, lineWidth: 1))
    }
}

// MARK: - "What changed?" — the before-only signed-change card

nonisolated enum GolfBeforeMovementAccessibilityID10868 {
    static let times = "golfBeforeMovement10868.times"
    static func row(_ outcomeID: String) -> String { "golfBeforeMovement10868.row.\(outcomeID)" }
}

/// The card's rows on the inherited movement card's own rules.
nonisolated struct GolfBeforeMovementModel10868: Equatable {
    let input: GolfBeforeMovementInput10868
    /// The inherited rules: the chooser's resolver, the owner's one pair per
    /// golfer, tied endpoints, the raw change, words and ticks. Its card gate
    /// (no card before the event) is left as it is and not read here.
    let movement: FieldMovementModel10868

    init(_ input: GolfBeforeMovementInput10868) {
        self.input = input
        movement = FieldMovementModel10868(input.movement)
    }

    /// Before the first tee only — never coerced from another phase.
    var isShown: Bool { input.movement.phase == .before }

    /// One row per displayed slot, in the owner's order. A slot repeated in
    /// the displayed list, or one that does not resolve, borrows nothing.
    var rows: [FieldMovementRow10868] {
        guard isShown else { return [] }
        var counts: [FieldChooserOriginalRef10868: Int] = [:]
        for slot in input.movement.displayed { counts[slot.ref, default: 0] += 1 }
        let copy = input.movement.copy
        return input.movement.displayed.map { slot in
            let resolution: FieldChooserResolution10868 = (counts[slot.ref] ?? 0) > 1 ? .unavailable : movement.field.resolve(slot.ref)
            guard let original = resolution.original else {
                return FieldMovementRow10868(slot: slot, resolution: resolution, before: nil, later: nil, change: .unavailable)
            }
            let pair = movement.pair(for: original.ref)
            return FieldMovementRow10868(
                slot: slot,
                resolution: resolution,
                before: movement.endpoint(FieldOutlookModel10868.beforeReading(original.plan), tie: pair?.before, label: copy.beforeLabel),
                later: movement.endpoint(FieldMovementModel10868.laterReading(original.plan), tie: pair?.later, label: copy.laterLabel),
                change: movement.change(original.plan, pair)
            )
        }
    }

    /// The exact golfer a row pins, only with a callback.
    func chooseRef(_ row: FieldMovementRow10868, canChoose: Bool) -> FieldChooserOriginalRef10868? {
        guard canChoose else { return nil }
        return row.resolution.original?.ref
    }

    func isSelected(_ row: FieldMovementRow10868) -> Bool {
        guard let selected = input.selected, let ref = row.resolution.original?.ref else { return false }
        return ref == selected
    }

    /// Where the later mark sits along the track, 0...1 from the leading edge,
    /// on the shared geometry; none without a placed change.
    static func markPosition(_ change: FieldMovementChange10868) -> Double? {
        guard let fraction = change.fraction, fraction.isFinite, fraction >= -1, fraction <= 1 else { return nil }
        return FieldMovementGeometry10868.unit(fraction, orientation: .horizontal)
    }

    /// A row's padding, so the card-wide axis lands on the rows' track span.
    static let rowPadding: CGFloat = 12

    /// Half the later mark and a hair — the finish strips' own inset — so a
    /// mark at exactly ±scale stays whole.
    static func inset(markSize: CGFloat) -> CGFloat {
        FieldExpectationsGeometry10868.inset(markDiameter: markSize)
    }

    /// The owner's ticks as 0...1 places for the measured axis labels.
    static func axisUnits(_ ticks: [FieldOutlookPlacedTick10868]) -> [Double] {
        ticks.map { FieldMovementGeometry10868.unit($0.fraction, orientation: .horizontal) }
    }

    /// The one plan the track Canvas draws: line, ticks, zero, the shared
    /// mark plan's fill and the later mark, all on the same inset span the
    /// axis labels use. The raw change is drawn as it is — never clamped or
    /// widened. Nil for a size that cannot hold a whole mark.
    static func trackPlan(change: FieldMovementChange10868, ticks: [Double], in size: CGSize,
                          markSize: CGFloat, bandHeight: CGFloat) -> GolfBeforeMovementTrackPlan10868? {
        let inset = Self.inset(markSize: markSize)
        guard size.height.isFinite, markSize.isFinite, markSize > 0, size.height >= markSize,
              bandHeight.isFinite, bandHeight > 0,
              let start = FieldFinishGeometry10868.x(of: 0, width: size.width, inset: inset),
              let end = FieldFinishGeometry10868.x(of: 1, width: size.width, inset: inset),
              let zero = FieldFinishGeometry10868.x(of: 0.5, width: size.width, inset: inset)
        else { return nil }
        let centerY = size.height / 2
        let band = CGSize(width: end - start, height: min(bandHeight, size.height))
        let marks = FieldMovementGeometry10868.markPlan(fraction: change.fraction, in: band, orientation: .horizontal)
        let dx = start, dy = centerY - band.height / 2
        let dot = markPosition(change).flatMap { FieldFinishGeometry10868.x(of: $0, width: size.width, inset: inset) }.map {
            CGRect(x: $0 - markSize / 2, y: centerY - markSize / 2, width: markSize, height: markSize)
        }
        return GolfBeforeMovementTrackPlan10868(
            centerY: centerY,
            startX: start,
            endX: end,
            zeroX: zero,
            tickXs: ticks.filter { $0 != 0 }.compactMap {
                FieldFinishGeometry10868.x(of: FieldMovementGeometry10868.unit($0, orientation: .horizontal), width: size.width, inset: inset)
            },
            fill: marks.fill?.offsetBy(dx: dx, dy: dy),
            zeroMark: marks.zeroMark?.offsetBy(dx: dx, dy: dy),
            dot: dot
        )
    }
}

/// Where the track Canvas draws, in its own coordinates.
nonisolated struct GolfBeforeMovementTrackPlan10868: Equatable {
    let centerY: CGFloat
    /// −scale and +scale, inset by half a mark.
    let startX: CGFloat
    let endX: CGFloat
    let zeroX: CGFloat
    /// The owner's non-zero ticks.
    let tickXs: [CGFloat]
    let fill: CGRect?
    let zeroMark: CGRect?
    /// The later mark; nil without a placed change.
    let dot: CGRect?
}

struct GolfBeforeMovementPresentation10868: View {
    let input: GolfBeforeMovementInput10868
    var onChoose: ((FieldChooserOriginalRef10868) -> Void)?
    private let model: GolfBeforeMovementModel10868

    init(input: GolfBeforeMovementInput10868, onChoose: ((FieldChooserOriginalRef10868) -> Void)? = nil) {
        self.input = input
        self.onChoose = onChoose
        self.model = GolfBeforeMovementModel10868(input)
    }

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var trackHeight: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var markSize: CGFloat = 10
    private var rowPadding: CGFloat { GolfBeforeMovementModel10868.rowPadding }

    private var copy: FieldMovementCopy10868 { input.movement.copy }

    var body: some View {
        if model.isShown {
            VStack(alignment: .leading, spacing: 12) {
                Text(copy.title)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let note = GolfEventPageModel10868.readable(copy.note) {
                    ownerWords(note)
                }
                if let times = input.times {
                    timesRow(times)
                }
                let rows = model.rows
                if !rows.isEmpty {
                    if input.movement.scale.isValid {
                        axis
                    }
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                            self.row(row)
                        }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    /// "Earlier <time> → Later <time>", stacked at accessibility sizes.
    private func timesRow(_ times: GolfBeforeMovementTimes10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
        return layout {
            time(copy.beforeLabel, times.earlier)
            if !typeSize.isAccessibilitySize {
                Image(systemName: "arrow.right")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .accessibilityHidden(true)
            }
            time(copy.laterLabel, times.later)
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier(GolfBeforeMovementAccessibilityID10868.times)
    }

    private func time(_ label: String, _ clock: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
            Text(clock)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The owner's measured tick labels on the tracks' own inset span — a
    /// crowded label is left out, never overlapped — and the scale in words.
    /// Decorative: every row speaks its own reading.
    private var axis: some View {
        let ticks = movement.ticks
        return VStack(alignment: .leading, spacing: 2) {
            if !ticks.isEmpty {
                FieldExpectationsAxisLayout10868(
                    units: GolfBeforeMovementModel10868.axisUnits(ticks),
                    inset: rowPadding + GolfBeforeMovementModel10868.inset(markSize: markSize),
                    spacing: 6
                ) {
                    ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                        Text(tick.label)
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondary)
                            .frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .topLeading)
                            .clipped()
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityHidden(true)
            }
            Text(input.movement.scale.words)
                .font(.caption2)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private var movement: FieldMovementModel10868 { model.movement }

    // MARK: Rows

    @ViewBuilder private func row(_ row: FieldMovementRow10868) -> some View {
        let id = GolfBeforeMovementAccessibilityID10868.row(row.slot.ref.outcomeID)
        if let original = row.resolution.original {
            let choice = model.chooseRef(row, canChoose: onChoose != nil)
            let selected = model.isSelected(row)
            control(row, choice) {
                VStack(alignment: .leading, spacing: 8) {
                    heading(row)
                    if let words = movement.stateWords(row) {
                        ownerWords(words)
                    }
                    endpoints(row)
                    track(row, accent: original.accent ?? DS.blue)
                }
                .padding(rowPadding)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .overlay(RoundedRectangle(cornerRadius: 12)
                    .strokeBorder(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1))
                .contentShape(Rectangle())
            }
            .accessibilityLabel(original.name)
            .accessibilityValue(movement.rowSummary(row))
            .accessibilityHint(choice == nil ? "" : (copy.openHint ?? ""))
            .accessibilityAddTraits(selected ? .isSelected : [])
            .accessibilityIdentifier(id)
        } else {
            VStack(alignment: .leading, spacing: 2) {
                if !row.slot.label.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
                    Text(row.slot.label)
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                ownerWords(input.movement.unavailableWords)
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(RoundedRectangle(cornerRadius: 12).strokeBorder(DS.border, style: StrokeStyle(lineWidth: 1, dash: [4, 3])))
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(movement.rowSummary(row))
            .accessibilityIdentifier(id)
        }
    }

    /// The golfer's whole label and the owner's change words.
    private func heading(_ row: FieldMovementRow10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 8))
        return layout {
            Text(row.slot.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if !typeSize.isAccessibilitySize { Spacer(minLength: 8) }
            if let words = movement.movementWords(row) {
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// Both endpoints at the same size, stacked at accessibility sizes. Each
    /// keeps its own clock line unless the owner's two times head the card.
    private func endpoints(_ row: FieldMovementRow10868) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 10))
            : AnyLayout(HStackLayout(alignment: .top, spacing: 12))
        return layout {
            if let before = row.before { endpoint(before) }
            if let later = row.later { endpoint(later) }
        }
    }

    private func endpoint(_ endpoint: FieldMovementEndpoint10868) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            switch endpoint {
            case .reading(let reading):
                Text(reading.label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                switch reading.value {
                case .recorded(let text, _):
                    Text(text)
                        .font(.system(size: figureSize, weight: .semibold))
                        .monospacedDigit()
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize()
                case .missing(let words):
                    Text(words)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if input.times == nil, let line = FieldOutlookModel10868.detailLine(reading) {
                    Text(line)
                        .font(.caption)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            case .unavailable(let label, let words):
                Text(label)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(words)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// One signed change from the shared zero-change line: the owner's ticks,
    /// the shared mark plan's fill and a whole mark at the later value, all
    /// from the inset plan. Off-scale draws only an edge mark; an unavailable
    /// change draws no mark.
    private func track(_ row: FieldMovementRow10868, accent: Color) -> some View {
        let ticks = movement.ticks.map(\.fraction)
        let change = row.change
        let mark = markSize
        let lineColor = DS.border
        let axisColor = DS.textSecondary
        return Canvas { context, size in
            guard let plan = GolfBeforeMovementModel10868.trackPlan(
                change: change, ticks: ticks, in: size, markSize: mark, bandHeight: 4)
            else { return }
            let mid = plan.centerY
            func vertical(_ x: CGFloat, _ halfHeight: CGFloat) -> Path {
                var path = Path()
                path.move(to: CGPoint(x: x, y: mid - halfHeight))
                path.addLine(to: CGPoint(x: x, y: mid + halfHeight))
                return path
            }
            var track = Path()
            track.move(to: CGPoint(x: plan.startX, y: mid))
            track.addLine(to: CGPoint(x: plan.endX, y: mid))
            context.stroke(track, with: .color(lineColor), lineWidth: 1)
            for x in plan.tickXs {
                context.stroke(vertical(x, size.height / 4), with: .color(lineColor), lineWidth: 1)
            }
            context.stroke(vertical(plan.zeroX, size.height / 2), with: .color(axisColor), lineWidth: 1.5)
            if let zero = plan.zeroMark { context.fill(Path(zero), with: .color(accent)) }
            if let fill = plan.fill { context.fill(Path(fill), with: .color(accent)) }
            if let dot = plan.dot { context.fill(Path(ellipseIn: dot), with: .color(accent)) }
        }
        .frame(height: trackHeight)
        .overlay(alignment: edgeAlignment(row.change)) { edgeMark(row.change) }
        .accessibilityHidden(true)
    }

    private func edgeAlignment(_ change: FieldMovementChange10868) -> Alignment {
        guard case .offScale(let rising) = change else { return .center }
        return rising ? .trailing : .leading
    }

    /// A change beyond the scale: a mark at the edge it points past, never a clamped fill.
    @ViewBuilder private func edgeMark(_ change: FieldMovementChange10868) -> some View {
        if case .offScale(let rising) = change {
            Image(systemName: rising ? "arrow.right.to.line" : "arrow.left.to.line")
                .font(.caption2.weight(.bold))
                .foregroundStyle(DS.textSecondary)
                .accessibilityHidden(true)
        }
    }

    // MARK: Shared pieces

    private func ownerWords(_ words: String) -> some View {
        Text(words)
            .font(.caption)
            .foregroundStyle(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// Pins the exact golfer through the host's own choose action.
    func choose(_ row: FieldMovementRow10868) {
        guard let ref = model.chooseRef(row, canChoose: onChoose != nil) else { return }
        onChoose?(ref)
    }

    @ViewBuilder
    private func control<Content: View>(_ row: FieldMovementRow10868, _ choice: FieldChooserOriginalRef10868?,
                                        @ViewBuilder content: () -> Content) -> some View {
        if choice != nil {
            Button {
                choose(row)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}
