import Combine
import SwiftUI

/// #9483 — the compact NBA story stream (brief v445 + W1–W3): the page's
/// game-story cards in the order the policy ranks them
/// (`NBAStoryStreamPolicy9483`), each with its factual reason, advancing
/// while they are watched and standing still for anyone reading them.
///
/// - ONE horizontal container: it replaces the deck's scroller.
/// - The applied order is the page's (`NFLCardDeckState9483.nbaStreamState`),
///   shared with the reader. A new order waits as pending until Resume,
///   Refresh, or an automatic boundary applies it.
/// - ONE advancement clock: `.task(id: eligibility)`. Any change of an
///   eligibility input cancels the sleep; the next eligible state starts a
///   full interval. No elapsed arithmetic, no catch-up.
/// - A separate freshness wake at the nearest live reason's deadline re-plans
///   so a quiet producer cannot keep an expired reason on screen. It never
///   advances, applies, or touches the advancement clock (W2).
/// - Automatic motion is iOS 18 only. iOS 17, VoiceOver, Reduce Motion,
///   regular width and unproven visibility are manual.
struct NBAStoryStreamView9483: View {
    /// What the page hands the stream.
    struct Page {
        let eventID: Int
        let phase: NBALadderCard9483.Phase
        /// The actual horizontal size class is compact (iPhone, compact iPad
        /// Split View).
        let compact: Bool
        /// The page ScrollView reports its scroll phase (iOS 18).
        let supportsAutomaticScrollObservation: Bool
        let coordinateSpace: String
        let signals: Signals
        /// Every read the deck is built from has arrived for this event. The
        /// stream begins only then: a plan made from a half-loaded deck would
        /// apply one card and withhold the rest as pending behind Refresh.
        /// Until then the shelf shows this event's plan order, manual only.
        let ready: Bool

        /// The page's `ready`: the history the finish card reads has arrived,
        /// and the game markets the ladders read have arrived for THIS event.
        /// No history, no markets, or another event's markets: not ready.
        static func deckReady(history: EventHistoryResponse?, gameMarkets: GameMarketsResponse?,
                              eventID: Int) -> Bool {
            history != nil && gameMarkets?.eventId == eventID
        }
    }

    /// The page's observations that change while it scrolls. The page holds
    /// this in `@State` without observing it, so a scroll phase change
    /// re-renders the stream, never the whole page (#8651's lesson).
    final class Signals: ObservableObject {
        /// The PAGE is being scrolled (not idle).
        @Published var pageIsScrolling = false
        /// The page's unobscured rectangle in `coordinateSpace`: its bounds
        /// less the real top bar and bottom bar. Nil until measured.
        @Published var usableViewport: CGRect?
    }

    /// The share of the stage's real height that must be unobscured.
    static let visibleShare: CGFloat = 0.55
    static let dwell: Duration = .seconds(10)
    /// After a reason's deadline, the wake looks again this much later, so
    /// it sees the quote past `isRecent`'s inclusive bound (W2), and re-arms
    /// at least this far ahead (no spin).
    static let expiryGrace: TimeInterval = 0.5

    let cards: [NFLEventCard9483]
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    let page: Page
    @ObservedObject var signals: Signals

    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.accessibilityVoiceOverEnabled) private var voiceOver
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @AccessibilityFocusState private var focused: String?

    /// Whether at least `visibleShare` of the stage is unobscured; nil when
    /// it cannot be measured (manual only).
    @State private var stageVisible: Bool?
    @State private var stageFrame = StageFrame()
    /// The latest inputs, for the tasks: a running task keeps the view value
    /// it started with, so it reads these instead.
    @State private var latest = Latest()
    /// Set by the freshness wake so the reasons are re-planned at its `now`.
    @State private var freshness = Date.distantPast
    /// iOS 18: a person is dragging or flinging the shelf.
    @State private var browsing = false
    /// iOS 17: the last id the stream itself scrolled to.
    @State private var programmaticTarget: String?

    var body: some View {
        // Re-read each minute so a price that stops being observed loses its
        // number on the page too (the deck's existing reread).
        TimelineView(.periodic(from: .now, by: 60)) { tick in
            let now = max(tick.date, freshness)
            let current = cards.map { $0.current(at: now) }
            let plan = NBAStoryStreamPolicy9483.plan(eventID: page.eventID, phase: page.phase,
                                                    cards: current, now: now)
            content(current, plan: plan)
                .onChange(of: plan, initial: true) { _, plan in state.receiveNBAPlan(plan) }
                .task(id: ExpiryKey(eventID: page.eventID, deadline: plan.nearestExpiry)) {
                    await freshnessWake(eventID: page.eventID, deadline: plan.nearestExpiry)
                }
        }
        .onChange(of: InputsKey(eventID: page.eventID, phase: page.phase, cards: cards, ready: page.ready),
                  initial: true) { _, key in
            latest.eventID = key.eventID
            latest.phase = key.phase
            latest.cards = key.cards
            Self.admit(key, into: state, now: Date())
        }
        .onChange(of: signals.usableViewport) { _, viewport in
            stageVisible = Self.unobscured(stage: stageFrame.value, viewport: viewport)
        }
        .task(id: eligibility) { await advanceAfterDwell(eligibility) }
        // Back from the reader returns focus to the card it was opened from.
        .onChange(of: state.openCardID) { old, new in
            if old != nil, new == nil { focused = state.returnCardID }
        }
    }

    /// The admission the inputs `onChange` runs. A ready page begins this
    /// event's stream with the plan its whole deck makes at `now`. A page
    /// still waiting on a read begins nothing, so the whole deck that follows
    /// is applied when it arrives, not parked as pending behind Refresh.
    static func admit(_ key: InputsKey, into state: NFLCardDeckState9483, now: Date) {
        guard key.ready else { return }
        state.beginNBAStream(NBAStoryStreamPolicy9483.plan(
            eventID: key.eventID, phase: key.phase, cards: key.cards.map { $0.current(at: now) }, now: now))
    }

    // MARK: - Layout

    private func content(_ current: [NFLEventCard9483], plan: NBAStoryStreamPolicy9483.Plan) -> some View {
        let stream = state.nbaStreamState.flatMap { $0.eventID == page.eventID ? $0 : nil }
        let byID = Dictionary(current.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let present = Set(byID.keys)
        // Until this event's stream begins, the plan order (its own fallback).
        let slots = stream?.shelf(present: present) ?? plan.orderedIDs.map { NBAStoryStreamPolicy9483.Slot.card($0) }
        let shown = slots.filter { if case .card = $0 { return true } else { return false } }.count
        let pendingDiffers = stream.map { $0.pendingIDs != $0.appliedIDs } ?? false
        return VStack(alignment: .leading, spacing: 8) {
            GameStoriesHeader9483(count: shown > 0 ? shown : nil, alignment: .firstTextBaseline)
            controls(begun: stream != nil, held: stream?.held ?? false, pendingDiffers: pendingDiffers, count: shown)
            if !slots.isEmpty {
                shelf(slots, byID: byID, reasons: plan.reasons, present: present)
            }
        }
    }

    /// Pause/Resume where automatic motion can run; elsewhere, Refresh when a
    /// newer order is waiting. Fewer than two cards: no motion control.
    @ViewBuilder
    private func controls(begun: Bool, held: Bool, pendingDiffers: Bool, count: Int) -> some View {
        if begun && motionAvailable && count >= 2 {
            Button {
                if held { resume() } else { state.holdNBAStream(eventID: page.eventID) }
            } label: {
                Self.controlLabel(held ? "Resume cards" : "Pause cards")
            }
        } else if pendingDiffers {
            Button { refreshOrder() } label: { Self.controlLabel("Refresh cards") }
        }
    }

    /// A text control whose 44 pt height is part of its label, so the whole
    /// height is the tap target (a frame outside the Button only pads it).
    static func controlLabel(_ title: String) -> some View {
        Text(title)
            .font(.callout.weight(.semibold))
            .frame(minHeight: 44)
            .contentShape(Rectangle())
    }

    private func shelf(_ slots: [NBAStoryStreamPolicy9483.Slot], byID: [String: NFLEventCard9483],
                       reasons: [String: NBAStoryStreamPolicy9483.Reason], present: Set<String>) -> some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                // Not lazy: at most three cards, and a lazy stack takes its
                // height from the cards laid out first, clipping a taller
                // card's controls once the stream advances to it.
                HStack(alignment: .top, spacing: 12) {
                    ForEach(slots) { slot in
                        Group {
                            switch slot {
                            case .card(let id):
                                if let card = byID[id] { cell(card, reason: reasons[id], present: present) }
                            case .unavailable:
                                UnavailableSlot9483(coordinateSpace: page.coordinateSpace, signals: signals,
                                                    refresh: refreshOrder)
                            }
                        }
                        // #11285 — the deck's width rule: at accessibility sizes
                        // on a 320pt screen each card takes the whole width.
                        .containerRelativeFrame(.horizontal) { width, _ in
                            NFLEventCardDeckView9483.cardWidth(width, count: slots.count,
                                                               accessibility: dynamicTypeSize.isAccessibilitySize)
                        }
                        .accessibilityFocused($focused, equals: slot.id)
                        .id(slot.id)
                    }
                }
                // The row is its tallest card's height, and the unavailable
                // slot stretches to it (below).
                .fixedSize(horizontal: false, vertical: true)
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
            .scrollPosition(id: Binding(
                get: { state.nbaStreamState?.eventID == page.eventID ? state.nbaStreamState?.activeID : nil },
                set: { reported in manuallyReported(reported, present: present) }), anchor: .leading)
            .modifier(ShelfScrollPhase9483(browsing: $browsing) {
                state.holdNBAStream(eventID: page.eventID)
            })
            .onGeometryChange(for: CGRect.self) { proxy in
                proxy.frame(in: .named(page.coordinateSpace))
            } action: { frame in
                stageFrame.value = frame
                let visible = Self.unobscured(stage: frame, viewport: signals.usableViewport)
                if visible != stageVisible { stageVisible = visible }
            }
            // #11060 — Back lands on the card it was opened from, on screen,
            // even when a rotation under the reader re-laid the shelf out.
            .onChange(of: state.openCardID) { old, new in
                guard old != nil, new == nil, let back = state.returnCardID else { return }
                programmaticTarget = back
                state.focusNBAStream(eventID: page.eventID, cardID: back, present: present)
                proxy.scrollTo(back, anchor: .leading)
            }
        }
    }

    private func cell(_ card: NFLEventCard9483, reason: NBAStoryStreamPolicy9483.Reason?,
                      present: Set<String>) -> some View {
        VStack(spacing: 6) {
            NFLEventCardView9483(card: card, awayName: awayName, homeName: homeName,
                                 awayColor: awayColor, homeColor: homeColor, state: state)
            if let reason, reason.eventID == page.eventID, reason.cardID == card.id, !reason.text.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text(reason.text)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .accessibilityLabel(reason.accessibilityText)
                    Button { seeLine(reason, present: present) } label: {
                        Text("See this line")
                            .font(.caption.weight(.semibold))
                            .frame(maxWidth: .infinity, minHeight: 44)
                    }
                }
            }
            Button { open(card.id, present: present) } label: {
                Label(NFLEventCardDeckView9483.openerTitle, systemImage: "arrow.up.left.and.arrow.down.right")
                    .font(.caption.weight(.semibold))
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
            .accessibilityLabel(NFLEventCardDeckView9483.openerAccessibilityLabel(card.title))
            .accessibilityIdentifier(NFLEventCardDeckView9483.openerIdentifier)
        }
    }

    // MARK: - Actions

    /// Holds, makes the card active (or, before the stream begins, the card
    /// it begins on), then opens it (`NFLCardDeckState9483.openNBACard`).
    private func open(_ cardID: String, present: Set<String>) {
        state.openNBACard(eventID: page.eventID, cardID: cardID, present: present)
    }

    /// Selects the reason's exact option on the card as it is NOW, then opens
    /// it. A card or option that has gone writes and opens nothing.
    private func seeLine(_ reason: NBAStoryStreamPolicy9483.Reason, present: Set<String>) {
        guard reason.eventID == page.eventID, latest.eventID == page.eventID,
              let card = latest.cards.first(where: { $0.id == reason.cardID }),
              case .ladder(let ladder) = card,
              state.select(optionKey: reason.optionKey, in: ladder, eventID: reason.eventID) else { return }
        open(card.id, present: present)
    }

    private func resume() {
        programmaticTarget = nil
        state.resumeNBAStream(eventID: page.eventID)
        programmaticTarget = state.nbaStreamState?.activeID
    }

    private func refreshOrder() {
        state.applyNBAPending(eventID: page.eventID)
        programmaticTarget = state.nbaStreamState?.activeID
    }

    /// A position the scroll view reports. iOS 18: only while a person is
    /// browsing. iOS 17: any id other than the stream's own last target.
    /// Before the stream begins it is the card the stream begins on (N4).
    private func manuallyReported(_ reported: String?, present: Set<String>) {
        guard let reported else { return }
        if let stream = state.nbaStreamState {
            guard stream.eventID == page.eventID, reported != stream.activeID else { return }
        }
        let manual = page.supportsAutomaticScrollObservation ? browsing : reported != programmaticTarget
        guard manual else { return }
        state.focusNBAStream(eventID: page.eventID, cardID: reported, present: present)
    }

    // MARK: - The advancement clock

    /// Automatic motion is possible in principle here.
    private var motionAvailable: Bool {
        page.supportsAutomaticScrollObservation && page.compact && !voiceOver && !reduceMotion
    }

    /// Every input automatic advancement depends on. Any change cancels the
    /// running sleep (`.task(id:)`).
    struct Eligibility: Hashable {
        let eventID: Int
        let activeID: String?
        let motionAvailable: Bool
        let stageVisible: Bool
        let sceneActive: Bool
        let pageIdle: Bool
        let browsing: Bool
        let readerClosed: Bool
        let held: Bool
        let cardCount: Int

        var eligible: Bool {
            motionAvailable && stageVisible && sceneActive && pageIdle && !browsing
                && readerClosed && !held && cardCount >= 2
        }
    }

    private var eligibility: Eligibility {
        let stream = state.nbaStreamState.flatMap { $0.eventID == page.eventID ? $0 : nil }
        let present = Set(cards.map(\.id))
        return Eligibility(
            eventID: page.eventID, activeID: stream?.activeID, motionAvailable: motionAvailable,
            stageVisible: stageVisible == true, sceneActive: scenePhase == .active,
            pageIdle: !signals.pageIsScrolling, browsing: browsing,
            readerClosed: state.openCardID == nil && state.detailsRowID == nil,
            held: stream?.held ?? true,
            cardCount: stream?.shelf(present: present).count ?? 0)
    }

    /// One full dwell, then: re-check, receive a plan made NOW, apply
    /// pending, advance. Cancellation is cancellation.
    private func advanceAfterDwell(_ token: Eligibility) async {
        guard token.eligible else { return }
        do { try await Task.sleep(for: Self.dwell) } catch { return }
        guard !Task.isCancelled, eligibility == token, latest.eventID == token.eventID,
              let stream = state.nbaStreamState, stream.eventID == token.eventID,
              !stream.held, stream.activeID == token.activeID,
              state.openCardID == nil, state.detailsRowID == nil else { return }
        let now = Date()
        let current = latest.cards.map { $0.current(at: now) }
        let plan = NBAStoryStreamPolicy9483.plan(eventID: token.eventID, phase: latest.phase,
                                                cards: current, now: now)
        withAnimation {
            state.advanceNBAStream(plan, present: Set(current.map(\.id)))
        }
        programmaticTarget = state.nbaStreamState?.activeID
    }

    // MARK: - The freshness wake

    struct ExpiryKey: Hashable {
        let eventID: Int
        let deadline: Date?
    }

    /// Sleeps past the nearest live reason's deadline, then re-plans at a
    /// fresh `now`. Guarded receive takes the plan (pending only). If that
    /// reason still holds, re-arm strictly later. Never advances.
    private func freshnessWake(eventID: Int, deadline: Date?) async {
        guard let deadline else { return }
        var target = deadline
        while true {
            let wait = max(target.timeIntervalSinceNow, 0) + Self.expiryGrace
            do { try await Task.sleep(for: .seconds(wait)) } catch { return }
            guard !Task.isCancelled, latest.eventID == eventID else { return }
            let now = Date()
            let plan = NBAStoryStreamPolicy9483.plan(eventID: eventID, phase: latest.phase,
                                                    cards: latest.cards.map { $0.current(at: now) }, now: now)
            freshness = now
            state.receiveNBAPlan(plan)
            guard plan.reasons.values.contains(where: { $0.expiry == deadline }) else { return }
            target = max(deadline, now) + Self.expiryGrace
        }
    }

    // MARK: - Measured visibility

    /// Whether at least `visibleShare` of the stage's real height lies inside
    /// the usable viewport, both in the page's coordinate space. Nil when
    /// either is unmeasured — manual only.
    static func unobscured(stage: CGRect?, viewport: CGRect?) -> Bool? {
        guard let stage, let viewport, stage.height > 0, viewport.height > 0, viewport.width > 0 else { return nil }
        let overlap = max(0, min(stage.maxY, viewport.maxY) - max(stage.minY, viewport.minY))
        return overlap >= stage.height * visibleShare
    }

    /// Where the unavailable slot's content starts, from the slot's top: centred
    /// in the part of the slot between the bar and the tab bar, and never
    /// outside the slot. Nil while the slot or the viewport is unmeasured, or
    /// no part of the slot is on screen (`unavailableContentOffset` decides).
    /// `nonisolated`: pure, and called from the slot's render-time effect.
    nonisolated static func unavailableContentTop(slot: CGRect?, viewport: CGRect?, content: CGFloat) -> CGFloat? {
        guard let slot, let viewport, slot.height > 0 else { return nil }
        let top = max(slot.minY, viewport.minY), bottom = min(slot.maxY, viewport.maxY)
        guard bottom > top else { return nil }
        let centred = (top + bottom - content) / 2 - slot.minY
        return min(max(0, centred), max(0, slot.height - content))
    }

    /// How far the unavailable slot's content is drawn below the slot's top:
    /// `unavailableContentTop` while part of the slot is on screen. Once no
    /// part is, the edge nearer the screen, where the content already was, so
    /// it leaves and comes back with the slot instead of jumping to the centre
    /// under the bars. Centred in the whole slot while the viewport is
    /// unmeasured; 0 while the content is, when the slot's frame centres it.
    nonisolated static func unavailableContentOffset(slot: CGRect, viewport: CGRect?, content: CGFloat) -> CGFloat {
        guard content > 0 else { return 0 }
        if let top = unavailableContentTop(slot: slot, viewport: viewport, content: content) { return top }
        guard let viewport, slot.height > 0 else { return max(0, (slot.height - content) / 2) }
        return slot.minY >= viewport.maxY ? 0 : max(0, slot.height - content)
    }

    // MARK: - Plain storage

    /// The stage's last frame. A class, so a frame change each scroll frame
    /// re-renders nothing; only the visibility decision is state.
    final class StageFrame {
        var value: CGRect?
    }

    final class Latest {
        var eventID: Int?
        var phase: NBALadderCard9483.Phase = .before
        var cards: [NFLEventCard9483] = []
    }

    struct InputsKey: Equatable {
        let eventID: Int
        let phase: NBALadderCard9483.Phase
        let cards: [NFLEventCard9483]
        let ready: Bool
    }
}

/// iOS 18: the shelf's own scroll phase. A person dragging it holds the
/// stream deliberately; iOS 17 detects manual browsing by position instead.
private struct ShelfScrollPhase9483: ViewModifier {
    @Binding var browsing: Bool
    let onInteract: () -> Void

    func body(content: Content) -> some View {
        if #available(iOS 18, *) {
            content.onScrollPhaseChange { _, phase in
                if phase == .interacting {
                    browsing = true
                    onInteract()
                } else if phase == .idle {
                    browsing = false
                }
            }
        } else {
            content
        }
    }
}

/// The held active card left the deck (W1): its place stays, with no stale
/// numbers and no substitute, until an explicit Refresh. It fills the row's
/// height, and its message and Refresh are drawn in the part of it on screen,
/// so a reader who comes back with the slot half under the bar, or scrolls a
/// slot taller than the screen (large text), still sees them. The place
/// follows the page as it scrolls with no state write per scroll frame and no
/// scroll-phase signal (iOS 17 has none): a render-time `visualEffect` offset
/// read from the slot's own frame. Layout never follows it, so the slot's
/// height and the card behind it stay put; state changes only when the
/// content's own height does (text size, width).
private struct UnavailableSlot9483: View {
    let coordinateSpace: String
    @ObservedObject var signals: NBAStoryStreamView9483.Signals
    let refresh: () -> Void
    @State private var contentHeight: CGFloat = 0

    var body: some View {
        // Value copies for the effect's closure, which is @Sendable and runs
        // off the main actor: no class, no ObservableObject, no self.
        let space = coordinateSpace, viewport = signals.usableViewport, content = contentHeight
        VStack(spacing: 12) {
            Text("This game story is no longer available")
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            Button { refresh() } label: { NBAStoryStreamView9483.controlLabel("Refresh cards") }
        }
        .frame(maxWidth: .infinity)
        .padding(16)
        .onGeometryChange(for: CGFloat.self) { $0.size.height } action: { height in
            if height != contentHeight { contentHeight = height }
        }
        // The slot's minimum (160 + padding) is on this full-height frame, not
        // inside the measurement, so the measured content is the message and
        // Refresh alone and a short visible band can still hold them.
        .frame(minHeight: 192, maxHeight: .infinity, alignment: content > 0 ? .top : .center)
        // The proxy is this frame, the whole slot, as laid out this frame; the
        // offset changes drawing only, so it never feeds back into its input.
        .visualEffect { effect, proxy in
            effect.offset(y: NBAStoryStreamView9483.unavailableContentOffset(
                slot: proxy.frame(in: .named(space)), viewport: viewport, content: content))
        }
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.secondary.opacity(0.15)))
        .accessibilityElement(children: .combine)
    }
}
