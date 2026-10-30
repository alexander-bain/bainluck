import SwiftUI

/// #10868 — the shared story-stream presentation that sits beneath the
/// win-probability anchor: the owner's displayed story card(s), a Pause /
/// Resume or Apply-updates control, readable status and pending words, exact
/// Previous/Next, a next-card hint and an "Open full card" entry per card.
///
/// A CONTROLLED view. The owner (Native's page state) decides what is shown
/// and what each control does: ranking, the displayed/received frame, pending
/// order adoption, cadence, visibility and reader holds, routing and focus all
/// stay there. This shell elects nothing — no first/next/latest card, no
/// sorting, no dedup, no queue, no timer — and never substitutes a neighbour
/// for a held card it cannot find. Controls hand back the exact intent and
/// target the owner supplied.
///
/// The card views themselves come from the owner's typed content builder, so
/// each card keeps its own charts, probabilities, results and layout.
nonisolated struct StoryStreamPresentation10868: Equatable, Sendable {
    /// One card in one owner scope (event + phase). Both must match exactly.
    nonisolated struct CardRef: Hashable, Sendable {
        let scope: String
        let id: String
    }

    /// The metadata the owner has for a card. The visual comes from the
    /// content builder; this carries only identity, the full name and whether
    /// the owner still offers it.
    nonisolated struct Card: Equatable, Sendable {
        let id: String
        let name: String
        /// False once the owner has withdrawn the card. A displayed withdrawn
        /// card stays an explicit "no longer available" slot.
        var available: Bool = true
    }

    /// The single playback control the owner offers, if any.
    nonisolated enum Playback: Equatable, Sendable {
        /// Automatic advancement is running; the control requests a hold.
        case pause
        /// Held; the control requests automatic advancement again.
        case resume
        /// Manual: the control requests the owner's waiting order be applied.
        case applyUpdates
    }

    nonisolated enum Direction: Equatable, Sendable {
        case previous, next
    }

    /// What the shell hands back. It requests; the owner decides.
    nonisolated enum Intent: Equatable, Sendable {
        /// A person is interacting with this stream (or with `card` in it).
        /// Sent BEFORE every shell request and by a card's own activation
        /// hook, so the owner can hold before anything else happens.
        case interaction(scope: String, card: CardRef?)
        case pause(scope: String)
        case resume(scope: String)
        case applyUpdates(scope: String)
        case browse(Direction, to: CardRef)
        /// Open the owner's EXISTING full reader on exactly this card.
        case open(CardRef)
    }

    let scope: String
    var eyebrow: String?
    let heading: String
    /// Every card the owner has metadata for, in any order: the shell never
    /// reads position from this array.
    var cards: [Card]
    /// The card the owner is displaying. Nil: the owner displays nothing.
    var primary: CardRef?
    /// The owner's companion, shown beside the primary only in a wide
    /// presentation when both whole cards fit.
    var companion: CardRef?
    var companionLabel: String?
    /// The owner chose the wide presentation.
    var wide: Bool = false
    /// The narrowest a card may be laid out beside another. Not finite and
    /// positive: the two cards stack in one column.
    var companionMinimumWidth: CGFloat = 320
    /// Already-qualified words from the owner, shown as given.
    var position: String?
    var status: String?
    var pending: String?
    var nextHint: String?
    var basis: String?
    /// Decorative reading progress, 0…1, from the owner's own clock.
    var dwellFraction: Double?
    var playback: Playback?
    var previous: CardRef?
    var next: CardRef?
    /// The host's reader owns interaction; shell requests are suppressed.
    var readerOpen: Bool = false

    // MARK: - Resolution (pure)

    nonisolated enum Unavailable: Equatable, Sendable {
        case blank, blankScope, foreignScope, missing, duplicate, withdrawn
        /// The owner's card has no readable name to offer as a target.
        case unnamed
    }

    nonisolated enum Slot: Equatable, Sendable {
        case card(CardRef, Card)
        case unavailable(CardRef, Unavailable)

        var ref: CardRef {
            switch self {
            case .card(let ref, _), .unavailable(let ref, _): ref
            }
        }

        var card: Card? {
            if case .card(_, let card) = self { card } else { nil }
        }
    }

    nonisolated struct Destination: Equatable, Sendable {
        let direction: Direction
        let slot: Slot
        let enabled: Bool
    }

    nonisolated enum Arrangement: Equatable, Sendable {
        /// The primary card alone.
        case single
        /// Side by side when both whole cards fit at `minimumWidth` (always
        /// finite and positive), otherwise stacked.
        case pairedIfFits(minimumWidth: CGFloat)
        /// One readable column (accessibility text sizes).
        case column
    }

    nonisolated struct Resolved: Equatable, Sendable {
        /// Nil when the owner displays no card.
        let primary: Slot?
        let companion: Slot?
        let playback: Playback?
        /// Static words shown under Reduce Motion when no manual control is
        /// offered. Never a control.
        let manualWords: String?
        let previous: Destination?
        let next: Destination?
        let dwell: Double?
        /// The owner supplied a handler, so actions may be drawn at all.
        let actionable: Bool
        /// Drawn actions may fire (no reader open).
        let controlsEnabled: Bool
    }

    static let reducedMotionWords = "Reduced motion · browse at your pace"
    static let emptyWords = "No stories in this order. Every original prop is still in All props."
    static let unavailableWords = "This story card is no longer available. Every original is still in All props."

    /// The exact card `ref` names in this scope, or why there is none. A blank
    /// id, a blank owner or reference scope, another scope, an id the owner has
    /// no card for, an id two cards share, a withdrawn card or a card with no
    /// name: an explicit slot, never a neighbour. Blankness is only tested;
    /// scope and id are still compared exactly as given.
    func slot(_ ref: CardRef) -> Slot {
        guard Self.words(ref.id) != nil else { return .unavailable(ref, .blank) }
        guard hasScope, Self.words(ref.scope) != nil else { return .unavailable(ref, .blankScope) }
        guard ref.scope == scope else { return .unavailable(ref, .foreignScope) }
        let matches = cards.filter { $0.id == ref.id }
        guard matches.count < 2 else { return .unavailable(ref, .duplicate) }
        guard let card = matches.first else { return .unavailable(ref, .missing) }
        guard card.available else { return .unavailable(ref, .withdrawn) }
        return Self.words(card.name) == nil ? .unavailable(ref, .unnamed) : .card(ref, card)
    }

    /// The owner named a scope. Without one the shell sends no request at all.
    var hasScope: Bool { Self.words(scope) != nil }

    func resolve(reduceMotion: Bool, actionable: Bool) -> Resolved {
        let primary = self.primary.map(slot)
        let companion: Slot? = wide && primary != nil
            ? self.companion.flatMap { $0 == self.primary ? nil : slot($0) } : nil
        let enabled = actionable && !readerOpen && hasScope
        // Reduce Motion keeps only a manual or stopping control; it never
        // offers a return to automatic motion.
        let offered = actionable && hasScope && primary != nil ? playback : nil
        let playback = reduceMotion && offered == .resume ? nil : offered
        let manualWords = reduceMotion && hasScope && primary != nil && playback == nil ? Self.reducedMotionWords : nil
        func destination(_ ref: CardRef?, _ direction: Direction) -> Destination? {
            guard actionable, primary != nil, let ref else { return nil }
            let target = self.slot(ref)
            return Destination(direction: direction, slot: target, enabled: enabled && target.card != nil)
        }
        return Resolved(primary: primary, companion: companion, playback: playback, manualWords: manualWords,
                        previous: destination(previous, .previous), next: destination(next, .next),
                        dwell: primary?.card == nil || reduceMotion ? nil : Self.validDwell(dwellFraction),
                        actionable: actionable, controlsEnabled: enabled)
    }

    /// A finite fraction in 0…1, else nothing to draw.
    static func validDwell(_ fraction: Double?) -> Double? {
        guard let fraction, fraction.isFinite, (0...1).contains(fraction) else { return nil }
        return fraction
    }

    /// How the stage lays out its cards. A companion minimum width that is
    /// not finite and positive never reaches a frame: the cards stack.
    static func arrangement(hasCompanion: Bool, accessibilitySize: Bool,
                            companionMinimumWidth: CGFloat) -> Arrangement {
        guard hasCompanion else { return .single }
        guard !accessibilitySize, let minimum = pairingWidth(companionMinimumWidth) else { return .column }
        return .pairedIfFits(minimumWidth: minimum)
    }

    /// A finite, positive width, else nothing to pair at.
    static func pairingWidth(_ width: CGFloat) -> CGFloat? {
        width.isFinite && width > 0 ? width : nil
    }

    // MARK: - Words

    static func words(_ text: String?) -> String? {
        guard let text, !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return nil }
        return text
    }

    static func playbackTitle(_ playback: Playback) -> String {
        switch playback {
        case .pause: "Pause"
        case .resume: "Resume"
        case .applyUpdates: "Apply updates"
        }
    }

    static func playbackSymbol(_ playback: Playback) -> String {
        switch playback {
        case .pause: "pause.fill"
        case .resume: "play.fill"
        case .applyUpdates: "arrow.clockwise"
        }
    }

    static func playbackAccessibilityLabel(_ playback: Playback) -> String {
        switch playback {
        case .pause: "Pause story cards"
        case .resume: "Resume story cards"
        case .applyUpdates: "Apply story updates"
        }
    }

    static func browseAccessibilityLabel(_ direction: Direction, name: String?) -> String {
        let side = direction == .previous ? "Previous" : "Next"
        guard let name else { return "\(side) card unavailable" }
        return "\(side) card: \(name)"
    }

    // MARK: - Requests (pure)

    nonisolated enum Action: Equatable, Sendable {
        case playback
        case browse(Direction)
        case open(CardRef)
    }

    /// The ordered intents one shell control sends: the interaction first, so
    /// the owner can hold, then the request. Empty when the control is not
    /// drawn, is disabled, or names nothing it can act on.
    func intents(for action: Action, resolved: Resolved) -> [Intent] {
        guard resolved.controlsEnabled, hasScope else { return [] }
        let shown = resolved.primary?.card == nil ? nil : resolved.primary?.ref
        switch action {
        case .playback:
            guard let playback = resolved.playback else { return [] }
            let request: Intent = switch playback {
            case .pause: .pause(scope: scope)
            case .resume: .resume(scope: scope)
            case .applyUpdates: .applyUpdates(scope: scope)
            }
            return [.interaction(scope: scope, card: shown), request]
        case .browse(let direction):
            guard let destination = direction == .previous ? resolved.previous : resolved.next,
                  destination.enabled, destination.slot.card != nil else { return [] }
            return [.interaction(scope: scope, card: shown), .browse(direction, to: destination.slot.ref)]
        case .open(let ref):
            guard displayedCard(ref, resolved: resolved) else { return [] }
            return [.interaction(scope: scope, card: ref), .open(ref)]
        }
    }

    /// What a card's own activation hook sends: the interaction only. Not
    /// suppressed by an open reader — it asks for a hold, nothing more.
    func activationIntents(for ref: CardRef, resolved: Resolved) -> [Intent] {
        guard resolved.actionable, hasScope, displayedCard(ref, resolved: resolved) else { return [] }
        return [.interaction(scope: scope, card: ref)]
    }

    private func displayedCard(_ ref: CardRef, resolved: Resolved) -> Bool {
        [resolved.primary, resolved.companion].contains { $0?.card != nil && $0?.ref == ref }
    }
}

/// Handed to each card's view so the card can tell the owner a person is using
/// it (before a chart scrub or a Details tap). It requests; it holds nothing.
struct StoryStreamCardActivation10868 {
    let card: StoryStreamPresentation10868.CardRef
    let intents: [StoryStreamPresentation10868.Intent]
    let send: ((StoryStreamPresentation10868.Intent) -> Void)?

    var isAvailable: Bool { send != nil && !intents.isEmpty }

    func request() {
        guard let send else { return }
        intents.forEach(send)
    }
}

struct StoryStreamPresentationView10868<Content: View>: View {
    typealias Presentation = StoryStreamPresentation10868

    let presentation: Presentation
    let onIntent: ((Presentation.Intent) -> Void)?
    let content: (Presentation.Card, StoryStreamCardActivation10868) -> Content

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    init(_ presentation: Presentation, onIntent: ((Presentation.Intent) -> Void)? = nil,
         @ViewBuilder content: @escaping (Presentation.Card, StoryStreamCardActivation10868) -> Content) {
        self.presentation = presentation
        self.onIntent = onIntent
        self.content = content
    }

    var body: some View {
        let resolved = presentation.resolve(reduceMotion: reduceMotion, actionable: onIntent != nil)
        VStack(alignment: .leading, spacing: 12) {
            header(resolved)
            statusWords(resolved)
            if let dwell = resolved.dwell {
                ProgressView(value: dwell)
                    .progressViewStyle(.linear)
                    .accessibilityHidden(true)
            }
            if let primary = resolved.primary {
                stage(primary, resolved: resolved)
                    .transaction(value: presentation.primary) { if reduceMotion { $0.animation = nil } }
                navigation(primary, resolved: resolved)
                if let hint = Presentation.words(presentation.nextHint) {
                    Text(hint)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                        .multilineTextAlignment(.center)
                        .accessibilityIdentifier("story-stream-10868.next-hint")
                }
            } else {
                Text(Presentation.emptyWords)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(16)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
            }
            if let basis = Presentation.words(presentation.basis) {
                Divider()
                Text(basis)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("story-stream-10868")
    }

    // MARK: - Header and status

    private func header(_ resolved: Presentation.Resolved) -> some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
        return layout {
            VStack(alignment: .leading, spacing: 4) {
                if let eyebrow = Presentation.words(presentation.eyebrow) {
                    Text(eyebrow)
                        .font(.footnote.weight(.semibold))
                        .textCase(.uppercase)
                        .foregroundStyle(.secondary)
                }
                Text(presentation.heading)
                    .font(.title3.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let playback = resolved.playback {
                Button { perform(.playback, resolved) } label: {
                    Label(Presentation.playbackTitle(playback), systemImage: Presentation.playbackSymbol(playback))
                        .font(.callout.weight(.semibold))
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.bordered)
                .disabled(!resolved.controlsEnabled)
                .accessibilityLabel(Presentation.playbackAccessibilityLabel(playback))
                .accessibilityIdentifier("story-stream-10868.playback")
            }
        }
    }

    @ViewBuilder
    private func statusWords(_ resolved: Presentation.Resolved) -> some View {
        let status = Presentation.words(presentation.status) ?? resolved.manualWords
        let pending = Presentation.words(presentation.pending)
        if status != nil || pending != nil {
            VStack(alignment: .leading, spacing: 4) {
                if let status {
                    Text(status)
                        .foregroundStyle(.secondary)
                        .accessibilityIdentifier("story-stream-10868.status")
                }
                if let manual = resolved.manualWords, manual != status {
                    Text(manual).foregroundStyle(.secondary)
                }
                if let pending {
                    Text(pending)
                        .fontWeight(.semibold)
                        .accessibilityIdentifier("story-stream-10868.pending")
                }
            }
            .font(.subheadline)
            .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: - Cards

    @ViewBuilder
    private func stage(_ primary: Presentation.Slot, resolved: Presentation.Resolved) -> some View {
        switch Presentation.arrangement(hasCompanion: resolved.companion != nil,
                                        accessibilitySize: dynamicTypeSize.isAccessibilitySize,
                                        companionMinimumWidth: presentation.companionMinimumWidth) {
        case .single:
            cell(primary, label: nil, resolved: resolved)
        case .column:
            VStack(alignment: .leading, spacing: 16) {
                cell(primary, label: nil, resolved: resolved)
                if let companion = resolved.companion {
                    cell(companion, label: presentation.companionLabel, resolved: resolved)
                }
            }
        case .pairedIfFits(let minimum):
            // Side by side only when both whole cards fit at their minimum
            // width; otherwise the same two cards stack. Never shrunk.
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) {
                    cell(primary, label: nil, resolved: resolved)
                        .frame(minWidth: minimum, idealWidth: minimum, maxWidth: .infinity, alignment: .topLeading)
                    if let companion = resolved.companion {
                        cell(companion, label: presentation.companionLabel, resolved: resolved)
                            .frame(minWidth: minimum, idealWidth: minimum, maxWidth: .infinity, alignment: .topLeading)
                    }
                }
                VStack(alignment: .leading, spacing: 16) {
                    cell(primary, label: nil, resolved: resolved)
                    if let companion = resolved.companion {
                        cell(companion, label: presentation.companionLabel, resolved: resolved)
                    }
                }
            }
        }
    }

    /// One displayed card at its own height (no fixed viewport, no clip),
    /// with its shell-level "Open full card" button below it.
    private func cell(_ slot: Presentation.Slot, label: String?, resolved: Presentation.Resolved) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if let label = Presentation.words(label) {
                Text(label)
                    .font(.footnote.weight(.semibold))
                    .textCase(.uppercase)
                    .foregroundStyle(.secondary)
            }
            switch slot {
            case .card(let ref, let card):
                content(card, StoryStreamCardActivation10868(
                    card: ref, intents: presentation.activationIntents(for: ref, resolved: resolved), send: onIntent))
                if resolved.actionable {
                    Button { perform(.open(ref), resolved) } label: {
                        Label("Open full card", systemImage: "arrow.up.left.and.arrow.down.right")
                            .font(.subheadline.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .contentShape(Rectangle())
                    }
                    .disabled(!resolved.controlsEnabled)
                    .accessibilityLabel("Open full card: \(card.name)")
                    .accessibilityIdentifier("story-stream-10868.open.\(ref.id)")
                }
            case .unavailable:
                Text(Presentation.unavailableWords)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, minHeight: 120)
                    .multilineTextAlignment(.center)
                    .padding(16)
                    .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
                    .accessibilityIdentifier("story-stream-10868.unavailable")
            }
        }
    }

    // MARK: - Navigation

    private func navigation(_ primary: Presentation.Slot, resolved: Presentation.Resolved) -> some View {
        let layout = dynamicTypeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .center, spacing: 8))
            : AnyLayout(HStackLayout(alignment: .center, spacing: 12))
        return layout {
            if let previous = resolved.previous { browseButton(previous, resolved: resolved) }
            VStack(spacing: 4) {
                if let card = primary.card {
                    Text(card.name)
                        .font(.headline)
                        .accessibilityIdentifier("story-stream-10868.name")
                }
                if let position = Presentation.words(presentation.position) {
                    Text(position)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }
            }
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity)
            .accessibilityElement(children: .combine)
            if let next = resolved.next { browseButton(next, resolved: resolved) }
        }
    }

    private func browseButton(_ destination: Presentation.Destination,
                              resolved: Presentation.Resolved) -> some View {
        let isPrevious = destination.direction == .previous
        let name = destination.slot.card?.name
        return Button { perform(.browse(destination.direction), resolved) } label: {
            VStack(alignment: isPrevious ? .leading : .trailing, spacing: 2) {
                Label(isPrevious ? "Previous" : "Next", systemImage: isPrevious ? "chevron.left" : "chevron.right")
                    .font(.subheadline.weight(.semibold))
                Text(name ?? "Unavailable")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(isPrevious ? .leading : .trailing)
            }
            .fixedSize(horizontal: false, vertical: true)
            .frame(minWidth: 44, minHeight: 44)
            .contentShape(Rectangle())
        }
        .disabled(!destination.enabled)
        .accessibilityLabel(Presentation.browseAccessibilityLabel(destination.direction, name: name))
        .accessibilityIdentifier(isPrevious ? "story-stream-10868.previous" : "story-stream-10868.next")
    }

    // MARK: - Actions

    private func perform(_ action: Presentation.Action, _ resolved: Presentation.Resolved) {
        guard let onIntent else { return }
        presentation.intents(for: action, resolved: resolved).forEach(onIntent)
    }
}
