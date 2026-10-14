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
/// — the match line and every card — until the reader asks for the newer one
/// ("Refresh"). New data never moves or rewrites a card under a reader's eyes.
/// One exception, deliberately (v159): a live projection that stops being
/// current leaves the held card too; a forecast never outlives its validity
/// because the reader happened to be looking.

/// The match line the reader keeps on top.
struct NFLReaderHeader9483: Equatable {
    /// "BUF 20–7 LAR · Q3 5:47", "SEA vs DEN · Pregame".
    let match: String
    /// "Win chances 86% · 14%", "Bills won".
    let chances: String
}

/// What the reader shows, given what was held and what is live now.
enum NFLCardReaderHold9483 {
    /// The held cards, with v159 applied: an expired live projection leaves.
    static func displayed(held: [NFLEventCard9483], live: [NFLEventCard9483]) -> [NFLEventCard9483] {
        let liveFinish = live.lazy.compactMap { card -> NFLFinishCard9483? in
            if case .finish(let finish) = card { return finish } else { return nil }
        }.first
        return held.map { card in
            guard case .finish(let finish) = card, finish.projectedNow != nil,
                  liveFinish?.projectedNow == nil else { return card }
            return .finish(NFLFinishCard9483(phase: finish.phase, pregame: finish.pregame,
                                             projectedNow: nil, final: finish.final))
        }
    }

    /// Whether a refresh would change anything the reader is looking at.
    static func hasUpdate(held: [NFLEventCard9483], heldHeader: NFLReaderHeader9483?,
                          live: [NFLEventCard9483], liveHeader: NFLReaderHeader9483) -> Bool {
        displayed(held: held, live: live) != live || heldHeader != liveHeader
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
    /// The original row behind a selected line, for exact details.
    let row: (String) -> GameMarketPlayerProp?

    @State private var heldCards: [NFLEventCard9483] = []
    @State private var heldHeader: NFLReaderHeader9483?
    /// The card on screen. Seeded at init so the first layout already asks for
    /// the card the reader was opened on (v107's rail: SwiftUI reports the
    /// LEADING card before the requested one is seated, so position reports
    /// are ignored until the requested card has actually landed).
    @State private var visible: String?
    @State private var seated = false

    init(liveCards: [NFLEventCard9483], liveHeader: NFLReaderHeader9483,
         awayName: String, homeName: String, awayColor: Color, homeColor: Color,
         state: NFLCardDeckState9483, row: @escaping (String) -> GameMarketPlayerProp?) {
        self.liveCards = liveCards
        self.liveHeader = liveHeader
        self.awayName = awayName
        self.homeName = homeName
        self.awayColor = awayColor
        self.homeColor = homeColor
        self.state = state
        self.row = row
        _visible = State(initialValue: state.openCardID)
    }

    private var cards: [NFLEventCard9483] {
        heldCards.isEmpty ? liveCards : NFLCardReaderHold9483.displayed(held: heldCards, live: liveCards)
    }
    private var header: NFLReaderHeader9483 { heldHeader ?? liveHeader }
    private var position: Int { cards.firstIndex { $0.id == visible } ?? 0 }

    var body: some View {
        GeometryReader { geo in
            VStack(spacing: 0) {
                top
                Divider()
                rail(width: geo.size.width)
                Divider()
                bottom
            }
        }
        .background(Color.systemBackground)
        .onAppear {
            heldCards = liveCards
            heldHeader = liveHeader
        }
        .sheet(item: Binding(
            get: { state.detailsRowID.map(IdentifiedRow.init) },
            set: { state.detailsRowID = $0?.id })) { item in
            NFLRowDetails9483(prop: row(item.id))
        }
    }

    private struct IdentifiedRow: Identifiable { let id: String }

    private var top: some View {
        VStack(alignment: .leading, spacing: 4) {
            Button { state.close() } label: {
                Label("Back to the game", systemImage: "chevron.left")
                    .font(.callout.weight(.semibold))
                    .frame(minHeight: 44)
            }
            Text(header.match)
                .font(.subheadline.weight(.bold))
            HStack(alignment: .firstTextBaseline) {
                Text(header.chances)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer(minLength: 8)
                if NFLCardReaderHold9483.hasUpdate(held: heldCards, heldHeader: heldHeader,
                                                   live: liveCards, liveHeader: liveHeader) {
                    Button("Refresh") {
                        heldCards = liveCards
                        heldHeader = liveHeader
                    }
                    .font(.caption.weight(.bold))
                    .frame(minHeight: 44)
                    .accessibilityLabel("New game update. Refresh the cards")
                    .accessibilityHint("Keeps this card open and shows the newest numbers")
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 18)
        .padding(.bottom, 8)
        .accessibilityElement(children: .contain)
    }

    private func rail(width: CGFloat) -> some View {
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
                        .frame(width: max(240, width - 44))
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
            .accessibilityLabel("Game story cards")
        }
    }

    private var bottom: some View {
        HStack {
            Button { step(-1) } label: {
                Image(systemName: "chevron.left").frame(width: 44, height: 44)
            }
            .disabled(position == 0)
            .accessibilityLabel("Previous card")
            Spacer(minLength: 4)
            VStack(spacing: 4) {
                Text(cards.indices.contains(position) ? cards[position].title : "")
                    .font(.subheadline.weight(.bold))
                    .lineLimit(1)
                Text("\(position + 1) of \(cards.count)\(cards.count > 1 ? " · Swipe to explore" : "")")
                    .font(.caption)
                    .foregroundStyle(.secondary)
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
            Button { step(1) } label: {
                Image(systemName: "chevron.right").frame(width: 44, height: 44)
            }
            .disabled(position >= cards.count - 1)
            .accessibilityLabel("Next card")
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 8)
    }

    private func step(_ delta: Int) {
        let next = position + delta
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
                            LabeledContent("Pre-game chance", value: formatProbability(mark))
                        }
                        if let price = prop.overProbability {
                            LabeledContent("Latest quote", value: formatProbability(price))
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
