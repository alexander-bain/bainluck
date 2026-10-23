import SwiftUI

/// #9483 — a card opened full size on the phone (design ref #10868 v107,
/// with v157/v158's held reading and v159's forecast expiry).
///
/// - A compact match and chance line on top, so the reader never loses the
///   game while reading a card.
/// - The cards side by side, snapping, each one scrolling on its own, with
///   the neighbour peeking, a count and arrows.
/// - Exact details for a selected line, over the card.
/// - Back returns to the page, on the card it was opened from.
///
/// HELD WHILE READING: what was on screen when the card opened stays on screen
/// — the match line, every card, and the original rows its Details show —
/// until the reader asks for the newer one ("Refresh"), which replaces all
/// three together. New data never moves or rewrites a card, or the Details
/// behind it, under a reader's eyes. One exception, deliberately (v159): a
/// number that stops being current leaves the held card too — a live
/// projection past its capture gap, a pregame price past its observation
/// bound. A forecast never outlives its validity because the reader happened
/// to be looking.

/// The match line the reader keeps on top.
struct NFLReaderHeader9483: Equatable {
    /// "BUF 20–7 LAR · Q3 5:47", "SEA vs DEN · Pregame", "PHI 7–27 CHI · Final".
    let match: String
    /// "Win chances · BUF 86% · LAR 14%"; empty after the final, where the
    /// score already says who won.
    let chances: String
}

/// What the reader shows, given what was held and what is live now.
enum NFLCardReaderHold9483 {
    /// The held cards, with v159 applied: an expired live projection leaves,
    /// and so does a pregame price no longer observed at `now`.
    static func displayed(held: [NFLEventCard9483], live: [NFLEventCard9483],
                          now: Date = Date()) -> [NFLEventCard9483] {
        let liveFinish = live.lazy.compactMap { card -> NFLFinishCard9483? in
            if case .finish(let finish) = card { return finish } else { return nil }
        }.first
        return held.map { card in
            guard case .finish(let finish) = card, finish.projectedNow != nil,
                  liveFinish?.projectedNow == nil else { return card.current(at: now) }
            return .finish(finish.withoutProjectedNow)
        }
    }

    /// Whether a refresh would change anything the reader is looking at,
    /// Details included.
    static func hasUpdate(held: [NFLEventCard9483], heldHeader: NFLReaderHeader9483?,
                          live: [NFLEventCard9483], liveHeader: NFLReaderHeader9483,
                          heldRows: [String: GameMarketPlayerProp] = [:],
                          liveRows: [String: GameMarketPlayerProp] = [:],
                          now: Date = Date()) -> Bool {
        displayed(held: held, live: live, now: now) != live.map { $0.current(at: now) }
            || heldHeader != liveHeader || heldRows != liveRows
    }

    /// The card on screen after Refresh replaces the cards `old` with `new`
    /// (design supplement of 10/14). The same card when it survived; when it
    /// did not, deliberately the nearest card that did — the next one in the
    /// old order, else the previous one, else the first new card — never an
    /// id no card carries. Nil only when no card is left.
    static func reconciled(visible: String?, old: [String], new: [String]) -> String? {
        if let visible, new.contains(visible) { return visible }
        let start = visible.flatMap { old.firstIndex(of: $0) } ?? 0
        let after = old.indices.filter { $0 > start }
        let before = old.indices.filter { $0 < start }.reversed()
        for index in after + before where new.contains(old[index]) { return old[index] }
        return new.first
    }

    /// The served option behind an NBA ladder line, frozen inside the card
    /// that shows it — so Details read what the held card holds, never the
    /// live matrix, until Refresh.
    static func ladderDetail(_ optionKey: String, in cards: [NFLEventCard9483]) -> NBALadderCard9483.Detail? {
        for card in cards {
            guard case .ladder(let ladder) = card,
                  let point = ladder.points.first(where: { $0.optionKey == optionKey }) else { continue }
            return point.detail
        }
        return nil
    }

    /// The original rows the cards' lines point at, by row id — what Details
    /// shows, and what the reader holds beside the cards.
    static func rows(for cards: [NFLEventCard9483],
                     in props: [GameMarketPlayerProp]) -> [String: GameMarketPlayerProp] {
        let ids = Set(cards.flatMap { card -> [String] in
            guard case .milestone(let milestone) = card else { return [] }
            return milestone.rungs.map(\.rowID)
        })
        var rows: [String: GameMarketPlayerProp] = [:]
        for prop in props where ids.contains(prop.id) && rows[prop.id] == nil { rows[prop.id] = prop }
        return rows
    }
}

struct NFLCardReader9483: View {
    let liveCards: [NFLEventCard9483]
    let liveHeader: NFLReaderHeader9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    /// The original rows behind the cards' lines, live (`NFLCardReaderHold9483.rows`).
    let liveRows: [String: GameMarketPlayerProp]

    @State private var heldCards: [NFLEventCard9483] = []
    @State private var heldHeader: NFLReaderHeader9483?
    @State private var heldRows: [String: GameMarketPlayerProp]?
    /// The card on screen. Seeded at init so the first layout already asks for
    /// the card the reader was opened on (v107's rail: SwiftUI reports the
    /// LEADING card before the requested one is seated, so position reports
    /// are ignored until the requested card has actually landed).
    @State private var visible: String?
    @State private var seated = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// #11285 — on a 320pt screen (Display Zoom) at accessibility sizes the
    /// reader's own margins broke whole words: inside 18pt margins the match
    /// line's "Commanders" (≈305pt at AX5) read "Comman-/ders", and the
    /// peeking card left its kicker 244pt, so "PROJECTED" (≈249pt) read
    /// "PROJECT-/ED". There the reader gives that width back instead of
    /// shrinking the type: the match line keeps a 6pt margin and each card
    /// takes the rail's whole width (the count says there are more). 375pt
    /// and wider, and every non-accessibility size, are unchanged.
    static func isNarrowAccessibility(width: CGFloat, accessibility: Bool) -> Bool {
        accessibility && width < 340
    }

    /// The match line's horizontal margin.
    static func headerMargin(width: CGFloat, accessibility: Bool) -> CGFloat {
        isNarrowAccessibility(width: width, accessibility: accessibility) ? 6 : 18
    }

    /// A card's width on the rail, inside its 14pt content margins.
    static func cardWidth(_ width: CGFloat, accessibility: Bool) -> CGFloat {
        isNarrowAccessibility(width: width, accessibility: accessibility) ? width - 2 * 14 : max(240, width - 44)
    }

    /// #11285 — the most height the win-chances line may take on a narrow
    /// phone at accessibility sizes, from the reader's height; nil elsewhere.
    /// At 320pt/AX5 Back, the match line and the chances line took ~70% of the
    /// reader, leaving a card only its kicker above the footer (Design,
    /// residual 2). There the chances line scrolls inside this band, under a
    /// match line that keeps the score and state whole and fixed: the type
    /// keeps its size and nothing leaves the reader. 375pt and wider, and
    /// every non-accessibility size, are unchanged.
    static func chancesMaxHeight(width: CGFloat, height: CGFloat, accessibility: Bool) -> CGFloat? {
        isNarrowAccessibility(width: width, accessibility: accessibility) ? (height * 0.12).rounded() : nil
    }

    init(liveCards: [NFLEventCard9483], liveHeader: NFLReaderHeader9483,
         awayName: String, homeName: String, awayColor: Color, homeColor: Color,
         state: NFLCardDeckState9483, liveRows: [String: GameMarketPlayerProp]) {
        self.liveCards = liveCards
        self.liveHeader = liveHeader
        self.awayName = awayName
        self.homeName = homeName
        self.awayColor = awayColor
        self.homeColor = homeColor
        self.state = state
        self.liveRows = liveRows
        _visible = State(initialValue: state.openCardID)
    }

    private func cards(at now: Date) -> [NFLEventCard9483] {
        heldCards.isEmpty ? liveCards.map { $0.current(at: now) }
            : NFLCardReaderHold9483.displayed(held: heldCards, live: liveCards, now: now)
    }
    private var header: NFLReaderHeader9483 { heldHeader ?? liveHeader }
    /// Details read the held rows, never the live ones, until Refresh.
    private var rows: [String: GameMarketPlayerProp] { heldRows ?? liveRows }

    var body: some View {
        // Re-read each minute: a held number past its validity leaves (v159).
        TimelineView(.periodic(from: .now, by: 60)) { tick in
            let cards = cards(at: tick.date)
            GeometryReader { geo in
                VStack(spacing: 0) {
                    top(now: tick.date, width: geo.size.width, height: geo.size.height)
                    Divider()
                    if cards.isEmpty {
                        Text("No game stories right now")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                            .frame(maxWidth: .infinity, maxHeight: .infinity)
                    } else {
                        rail(cards, width: geo.size.width)
                        Divider()
                        bottom(cards)
                    }
                }
            }
        }
        .background(Color.systemBackground)
        .onAppear {
            heldCards = liveCards
            heldHeader = liveHeader
            heldRows = liveRows
        }
        .sheet(item: Binding(
            get: { state.detailsRowID.map(IdentifiedRow.init) },
            set: { state.detailsRowID = $0?.id })) { item in
            // A prop line's original is in the held rows; an NBA ladder
            // line's original is frozen inside its held card, and so is a
            // final MLB story's (#11284).
            if let original = MLBFinalDeck11284.original(item.id, in: heldCards.isEmpty ? liveCards : heldCards) {
                MLBOriginalDetails11284(original: original)
            } else if rows[item.id] == nil,
               let detail = NFLCardReaderHold9483.ladderDetail(item.id, in: heldCards.isEmpty ? liveCards : heldCards) {
                NBAOptionDetails9483(detail: detail)
            } else {
                NFLRowDetails9483(prop: rows[item.id])
            }
        }
    }

    private func refresh() {
        let next = NFLCardReaderHold9483.reconciled(visible: visible, old: heldCards.map(\.id),
                                                    new: liveCards.map(\.id))
        heldCards = liveCards
        heldHeader = liveHeader
        heldRows = liveRows
        // The open card left the deck: move to the nearest card that stayed,
        // so the count and the dots name a card that is on screen. With no
        // card left the reader stays open on its empty state until Back.
        guard next != visible else { return }
        seated = true
        visible = next
        if let next { state.openCardID = next }
    }

    private struct IdentifiedRow: Identifiable { let id: String }

    /// What the rail's card frames and order depend on (#11060). Since
    /// #11285 a card's width also follows the type size on a narrow phone,
    /// so the generation carries the width the frame actually uses.
    struct RailGeneration: Equatable {
        let width: CGFloat
        let cardWidth: CGFloat
        let order: [String]
    }

    static func railGeneration(width: CGFloat, accessibility: Bool, order: [String]) -> RailGeneration {
        RailGeneration(width: width, cardWidth: cardWidth(width, accessibility: accessibility), order: order)
    }

    /// One row of controls — a short Back and, when there is one, Refresh —
    /// then one match summary. At accessibility sizes the text stays large;
    /// it is the repetition that goes, not the type size.
    private func top(now: Date, width: CGFloat, height: CGFloat) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .center) {
                Button { state.close() } label: {
                    Label("Back", systemImage: "chevron.left")
                        .font(.callout.weight(.semibold))
                        .frame(minHeight: 44)
                }
                .accessibilityLabel("Back to the game")
                Spacer(minLength: 8)
                if NFLCardReaderHold9483.hasUpdate(held: heldCards, heldHeader: heldHeader,
                                                   live: liveCards, liveHeader: liveHeader,
                                                   heldRows: heldRows ?? liveRows, liveRows: liveRows,
                                                   now: now) {
                    Button("Refresh", action: refresh)
                        .font(.callout.weight(.bold))
                        .frame(minHeight: 44)
                        .accessibilityLabel("New game update. Refresh the cards")
                        .accessibilityHint("Keeps this card open and shows the newest numbers")
                }
            }
            // #11061 — wrap, never truncate: at accessibility sizes a clipped
            // chances line hid the second team's number.
            Text(header.match)
                .font(.subheadline.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            if !header.chances.isEmpty {
                if let band = Self.chancesMaxHeight(width: width, height: height,
                                                    accessibility: dynamicTypeSize.isAccessibilitySize) {
                    // Whole when it fits the band; otherwise it scrolls there,
                    // its indicator flashed so the rest reads as reachable.
                    ViewThatFits(in: .vertical) {
                        chancesLine
                        ScrollView(.vertical) {
                            chancesLine.frame(maxWidth: .infinity, alignment: .leading)
                        }
                        // The band is its cap, never the stack's leftover: a
                        // flexible scroller here let the reader's VStack
                        // squeeze it to 0pt and the chances vanished (lane1 R1).
                        .frame(height: band)
                        .scrollIndicators(.visible)
                        .scrollIndicatorsFlash(onAppear: true)
                    }
                    .frame(maxHeight: band)
                } else {
                    chancesLine
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, Self.headerMargin(width: width, accessibility: dynamicTypeSize.isAccessibilitySize))
        .padding(.bottom, 8)
        .accessibilityElement(children: .contain)
    }

    private var chancesLine: some View {
        Text(header.chances)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    private func rail(_ cards: [NFLEventCard9483], width: CGFloat) -> some View {
        ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 12) {
                    ForEach(cards) { card in
                        ScrollView(.vertical) {
                            NFLEventCardView9483(card: card, awayName: awayName, homeName: homeName,
                                                 awayColor: awayColor, homeColor: homeColor,
                                                 state: state, expanded: true)
                                .padding(.vertical, 16)
                        }
                        .frame(width: Self.cardWidth(width, accessibility: dynamicTypeSize.isAccessibilitySize))
                        .id(card.id)
                        .accessibilityHidden(card.id != visible)
                    }
                }
                .scrollTargetLayout()
            }
            .contentMargins(.horizontal, 14, for: .scrollContent)
            .scrollTargetBehavior(.viewAligned)
            .scrollPosition(id: Binding(
                get: { visible },
                set: { reported in
                    guard let reported else { return }
                    if seated { visible = reported; state.openCardID = reported }
                    else if reported == visible { seated = true }
                }))
            .onAppear {
                if let visible { proxy.scrollTo(visible, anchor: .leading) }
                // A single-card reader, or one opened on the first card, has
                // nothing to seat.
                if visible == nil || visible == cards.first?.id { seated = true }
            }
            .task {
                // One layout later, in case the first scroll ran before the
                // requested card had geometry.
                if !seated, let visible {
                    proxy.scrollTo(visible, anchor: .leading)
                    seated = true
                }
            }
            // #11060 — a rotation or width change resizes every card, and a
            // Refresh can reorder them; the old offset then lands on another
            // card while `visible` (count, dots, focus) still names this one.
            // A text-size change on a narrow phone resizes them too (#11285).
            // Re-seat on the width+card width+order generation and ignore the
            // reports the re-layout makes until the card has landed again.
            .onChange(of: Self.railGeneration(width: width, accessibility: dynamicTypeSize.isAccessibilitySize,
                                              order: cards.map(\.id))) { _, _ in
                guard let visible else { return }
                seated = false
                proxy.scrollTo(visible, anchor: .leading)
                Task { @MainActor in
                    proxy.scrollTo(visible, anchor: .leading)
                    seated = true
                }
            }
            .accessibilityLabel("Game story cards")
            .accessibilityHint(cards.count > 1 ? "Swipe left or right with three fingers for another card" : "")
        }
    }

    /// A compact footer: previous, "2 of 2", next. The card names itself, so
    /// the footer does not repeat its title.
    private func bottom(_ cards: [NFLEventCard9483]) -> some View {
        let position = cards.firstIndex { $0.id == visible } ?? 0
        return HStack {
            Button { step(-1, in: cards) } label: {
                Image(systemName: "chevron.left").frame(width: 44, height: 44)
            }
            .disabled(position == 0)
            .accessibilityLabel("Previous card")
            Spacer(minLength: 4)
            VStack(spacing: 4) {
                Text("\(position + 1) of \(cards.count)")
                    .font(.subheadline.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.secondary)
                    .accessibilityLabel("Card \(position + 1) of \(cards.count)")
                    // Read before the arrows, which sit higher on screen.
                    .accessibilitySortPriority(1)
                HStack(spacing: 6) {
                    ForEach(cards) { card in
                        Capsule()
                            .fill(card.id == visible ? homeColor : Color.secondary.opacity(0.2))
                            .frame(width: card.id == visible ? 18 : 5, height: 5)
                    }
                }
                .accessibilityHidden(true)
            }
            .multilineTextAlignment(.center)
            Spacer(minLength: 4)
            Button { step(1, in: cards) } label: {
                Image(systemName: "chevron.right").frame(width: 44, height: 44)
            }
            .disabled(position >= cards.count - 1)
            .accessibilityLabel("Next card")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
        .accessibilityElement(children: .contain)
    }

    private func step(_ delta: Int, in cards: [NFLEventCard9483]) {
        let next = (cards.firstIndex { $0.id == visible } ?? 0) + delta
        guard cards.indices.contains(next) else { return }
        seated = true
        withAnimation { visible = cards[next].id }
        state.openCardID = cards[next].id
    }
}

/// The exact original row behind a line: what the venue quoted, the pregame
/// mark, and the server's grade — each named for what it is, never merged.
struct NFLRowDetails9483: View {
    let prop: GameMarketPlayerProp?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                if let prop {
                    Section {
                        Text(prop.outcomeName).font(.headline)
                        LabeledContent("Market", value: prop.marketName)
                        if let threshold = prop.threshold {
                            LabeledContent("Line", value: PlayerPropsFamily.targetLabel(threshold))
                        }
                    }
                    Section {
                        if let mark = prop.pregameMark {
                            LabeledContent("Pregame baseline", value: formatProbability(mark))
                        }
                        // Always dated: a quote's number without its time
                        // cannot say whether it is current.
                        if let price = prop.overProbability {
                            LabeledContent("Last quote", value: formatProbability(price))
                            LabeledContent("Quoted", value: SourceAge.preciseStamp(prop.observedAt) ?? "Time unknown")
                        }
                        if let name = SourceLabels.label(for: prop.source) {
                            LabeledContent("Venue", value: name)
                        }
                    }
                    if prop.actual != nil || prop.hit != nil {
                        Section("Result") {
                            if let actual = prop.actual {
                                LabeledContent("Final", value: NFLFinishCardView9483.points(actual))
                            }
                            if let hit = prop.hit {
                                LabeledContent("Line", value: hit ? "Reached" : "Not reached")
                            }
                        }
                    }
                } else {
                    Text("This line is no longer offered.")
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Line details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("Done") { dismiss() } }
            }
        }
    }
}
