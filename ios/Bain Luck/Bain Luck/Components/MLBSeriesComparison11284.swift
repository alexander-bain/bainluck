import SwiftUI

/// #11284 — the associated-series card's comparison (design ref #10868,
/// `native-baseball-paired-home-runs/reader-final/renders/full-series-375`):
/// a market selector, and for the chosen market one tile per outcome with an
/// independent 0–100% ring around its pregame chance and the venue's result
/// in words beside a symbol.
///
/// Stateless, and only a drawing of `MLBSeriesCard11284`. The card's builder
/// owns the markets (its `questions`), their order and grouping, every
/// outcome's label, the producer's admitted pregame pin and the producer's
/// result; the host owns which market and outcome are selected (defaults
/// included), update holds, navigation, focus and the original's Details.
///
/// WHAT THE NUMBER IS. `Option.pregame` is the producer's admitted pregame pin
/// (`NBALadderCard9483.pin`). Nothing typed says it was taken before the
/// series began, so it is "Pregame chance" — never "Pre-series", never
/// "Chance before this game", never current. A missing pin is the word
/// Unavailable with no ring at all; an admitted 0 or 1 draws an empty or full
/// ring, which is a value, not an absence.
///
/// EACH RING IS ITS OWN. Outcomes of one market are independent contracts and
/// may sum past 100% (the reference's exact-series four sum to 105%). No ring
/// is normalized, no complement is inferred, and no outcome is regrouped by
/// team from its label.
///
/// SELECTION WITHOUT FALLBACK. A nil market is "Choose a market"; a market the
/// card no longer carries is "unavailable in this update" — neither shows
/// another market's outcomes, and the selector stays. An outcome is looked up
/// only inside the selected market, so the same option key in another market
/// is never selected by it.
struct MLBSeriesComparison11284: View {
    let card: MLBSeriesCard11284
    /// The host's selected market (`question.questionKey`); nil is unselected.
    let selectedQuestionKey: String?
    /// The host's selected outcome within that market (`option.optionKey`);
    /// nil is unselected.
    let selectedOptionKey: String?
    let color: Color
    /// Receives `question.questionKey` unchanged.
    let onSelectMarket: (String) -> Void
    /// Receives the tile's own `(question.questionKey, option.optionKey)`.
    let onSelectOption: (String, String) -> Void
    /// Receives the selected `option.original.id` unchanged. Nil draws no
    /// details control.
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var size
    /// The chance; it never shrinks to fit.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = Self.figurePointSize
    /// Follows smaller text down, but never grows past the default
    /// (`boundedRing`), so a ring always fits a compact phone.
    @ScaledMetric(relativeTo: .title) private var scaledRing: CGFloat = Self.ringPointDiameter
    /// The narrowest a tile may be before the grid falls to one column.
    @ScaledMetric(relativeTo: .body) private var tileMinimum: CGFloat = 150

    /// The chance's size at the default text size (Design: at least 28pt).
    static let figurePointSize: CGFloat = 28
    /// The ring's size at the default text size, and its ceiling at every
    /// size: 120 + 2 × 12 tile padding fits a 320pt viewport's card content.
    static let ringPointDiameter: CGFloat = 120
    /// The decorative ring above a chance printed below it.
    static let belowRingDiameter: CGFloat = 64
    static let tilePadding: CGFloat = 12
    /// The widest chance the shared formatter prints (">99%"), in ems of the
    /// figure's size, rounded up for bold digits and the percent sign.
    static let widestFigureEms: CGFloat = 2.7
    /// No market, outcome or details control is a smaller target than this.
    static let minimumControlHeight: CGFloat = 44
    static let kickerText = "Associated series"
    static let separateText = "Separate from this game"
    static let pregameLabel = "Pregame chance"
    static let resultLabel = "Venue result"
    static let unavailableText = "Unavailable"
    static let selectedText = "Selected"
    static let detailsTitle = "Outcome details"
    static let detailsHintText = "Shows this outcome's exact original"
    static let marketHintText = "Shows this market's outcomes"
    static let optionHintText = "Selects this outcome"

    var presentation: Presentation {
        Self.presentation(card, questionKey: selectedQuestionKey, optionKey: selectedOptionKey)
    }

    var detailsAvailable: Bool { onDetails != nil && presentation.detailsID != nil }

    func select(_ market: MarketChoice) {
        onSelectMarket(market.id)
    }

    func select(_ tile: Tile) {
        onSelectOption(tile.questionKey, tile.optionKey)
    }

    /// Hands back the selected outcome's original ID; with no resolved
    /// outcome nothing is sent.
    func details() {
        guard let id = presentation.detailsID else { return }
        onDetails?(id)
    }

    var body: some View {
        let presentation = self.presentation
        VStack(alignment: .leading, spacing: 12) {
            heading
            selector(presentation)
            Text(presentation.title)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(presentation.titleSpoken)
                .accessibilityAddTraits(.isHeader)
            if let notice = presentation.outcomeNotice {
                Text(notice)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !presentation.tiles.isEmpty {
                grid(presentation.tiles)
            }
            if detailsAvailable {
                Button(Self.detailsTitle) { details() }
                    .font(.callout.weight(.semibold))
                    .frame(minHeight: Self.minimumControlHeight)
                    .accessibilityHint(Self.detailsHintText)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Heading and markets

    private var heading: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(Self.kickerText.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(.secondary)
            Text(Self.separateText)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(Self.kickerText), \(Self.separateText.lowercased())")
    }

    /// Every market, in the card's order, whatever is selected. Full names
    /// wrap; at accessibility sizes the selector is a full-width list.
    @ViewBuilder private func selector(_ presentation: Presentation) -> some View {
        if Self.selectorStacks(at: size) {
            VStack(alignment: .leading, spacing: 6) {
                ForEach(presentation.markets) { market in
                    marketButton(market).frame(maxWidth: .infinity, alignment: .leading)
                }
            }
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(alignment: .top, spacing: 6) {
                    ForEach(presentation.markets) { market in
                        marketButton(market).frame(maxWidth: 220, alignment: .leading)
                    }
                }
            }
        }
    }

    private func marketButton(_ market: MarketChoice) -> some View {
        Button { select(market) } label: {
            Text(market.label)
                .font(.subheadline.weight(.semibold))
                .multilineTextAlignment(.leading)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(maxWidth: .infinity, minHeight: Self.minimumControlHeight, alignment: .leading)
                .background(market.isSelected ? color.opacity(0.14) : Color.secondary.opacity(0.08),
                            in: RoundedRectangle(cornerRadius: 8))
                .overlay(RoundedRectangle(cornerRadius: 8)
                    .stroke(market.isSelected ? color : Color.clear, lineWidth: 1.5))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(market.spoken)
        .accessibilityHint(Self.marketHintText)
        .accessibilityAddTraits(market.isSelected ? .isSelected : [])
    }

    // MARK: Tiles

    /// Two columns where two tiles fit at their minimum width; one column at
    /// XXXL and accessibility sizes, or when the width runs out. A long name
    /// wraps; the chance keeps its size.
    @ViewBuilder private func grid(_ tiles: [Tile]) -> some View {
        if Self.singleColumn(at: size) {
            column(tiles)
        } else {
            ViewThatFits(in: .horizontal) {
                VStack(spacing: 8) {
                    ForEach(Self.pairs(tiles)) { pair in
                        HStack(alignment: .top, spacing: 8) {
                            tile(pair.first)
                                .frame(minWidth: tileMinimum, idealWidth: tileMinimum, maxWidth: .infinity,
                                       alignment: .top)
                            if let second = pair.second {
                                tile(second)
                                    .frame(minWidth: tileMinimum, idealWidth: tileMinimum, maxWidth: .infinity,
                                           alignment: .top)
                            } else {
                                Color.clear
                                    .frame(minWidth: tileMinimum, idealWidth: tileMinimum, maxWidth: .infinity,
                                           maxHeight: 1)
                                    .accessibilityHidden(true)
                            }
                        }
                    }
                }
                column(tiles)
            }
        }
    }

    private func column(_ tiles: [Tile]) -> some View {
        VStack(spacing: 8) {
            ForEach(tiles) { tile($0) }
        }
    }

    private func tile(_ tile: Tile) -> some View {
        Button { select(tile) } label: {
            VStack(alignment: .leading, spacing: 8) {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(tile.label)
                        .font(.headline)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    if tile.isSelected {
                        Text(Self.selectedText)
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(color)
                    }
                }
                Text(Self.pregameLabel)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                chance(tile)
                    .frame(maxWidth: .infinity)
                result(tile)
            }
            .padding(Self.tilePadding)
            .frame(maxWidth: .infinity, minHeight: Self.minimumControlHeight, alignment: .topLeading)
            .background(Self.celebrates(tile.result) ? color.opacity(0.07) : Color.secondary.opacity(0.04),
                        in: RoundedRectangle(cornerRadius: 12))
            .overlay(RoundedRectangle(cornerRadius: 12)
                .stroke(tile.isSelected ? color : Color.secondary.opacity(0.2),
                        lineWidth: tile.isSelected ? 2.5 : 1))
            .contentShape(RoundedRectangle(cornerRadius: 12))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(tile.spoken)
        .accessibilityHint(Self.optionHintText)
        .accessibilityAddTraits(tile.isSelected ? .isSelected : [])
    }

    /// The ring and its chance. The chance sits inside a bounded ring while
    /// its full scaled size fits there; otherwise — and always at
    /// accessibility sizes — it prints below a small decorative ring, wrapping
    /// if it must, never shrunk or clipped. With no admitted chance there is
    /// only the word Unavailable: no ring, and no ring-sized space.
    @ViewBuilder private func chance(_ tile: Tile) -> some View {
        let ring = Self.boundedRing(scaled: scaledRing)
        switch Self.chanceLayout(tile, size: size, figureSize: figureSize, ringDiameter: ring) {
        case .inside:
            ZStack {
                self.ring(tile.ringFraction ?? 0, diameter: ring)
                figure(tile.chanceText ?? "")
                    .lineLimit(1)
                    .fixedSize()
            }
            .frame(maxWidth: .infinity)
        case .below:
            VStack(alignment: .leading, spacing: 6) {
                self.ring(tile.ringFraction ?? 0, diameter: Self.belowRingDiameter)
                figure(tile.chanceText ?? "")
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        case .absent:
            Text(Self.unavailableText)
                .font(.headline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// An independent 0–100% ring, decorative: the words carry the value.
    private func ring(_ fraction: Double, diameter: CGFloat) -> some View {
        let line = Self.ringLineWidth(for: diameter)
        return ZStack {
            Circle()
                .stroke(color.opacity(0.18), lineWidth: line)
            Circle()
                .trim(from: 0, to: CGFloat(fraction))
                .stroke(color, style: StrokeStyle(lineWidth: line, lineCap: .butt))
                .rotationEffect(.degrees(-90))
        }
        .padding(line / 2)
        .frame(width: diameter, height: diameter)
        .accessibilityHidden(true)
    }

    private func figure(_ text: String) -> some View {
        Text(text)
            .font(.system(size: figureSize, weight: .bold).monospacedDigit())
            .foregroundStyle(color)
    }

    /// The venue's result in words beside a symbol, so it never rests on
    /// colour.
    private func result(_ tile: Tile) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: Self.resultSymbol(tile.result))
            Text("\(Self.resultLabel): \(tile.result.label)")
                .fixedSize(horizontal: false, vertical: true)
        }
        .font(.subheadline.weight(tile.result == .won ? .semibold : .regular))
        .foregroundStyle(tile.result == .won ? Color.primary : Color.secondary)
    }

    static func singleColumn(at size: DynamicTypeSize) -> Bool { size >= .xxxLarge }

    static func selectorStacks(at size: DynamicTypeSize) -> Bool { size.isAccessibilitySize }
}

// MARK: - What the card says

extension MLBSeriesComparison11284 {
    /// One market control.
    struct MarketChoice: Equatable, Identifiable {
        /// `question.questionKey`, sent to `onSelectMarket` unchanged.
        let id: String
        let label: String
        let spoken: String
        let isSelected: Bool
    }

    /// One outcome tile of the selected market.
    struct Tile: Equatable, Identifiable {
        let questionKey: String
        let optionKey: String
        let label: String
        /// The admitted pregame pin as the ring's share of a full turn; nil
        /// draws no ring.
        let ringFraction: Double?
        /// The shared formatter's words for the same value; nil when absent.
        let chanceText: String?
        let result: MLBVenueResult11284
        let isSelected: Bool
        let spoken: String
        /// `option.original.id`.
        let originalID: String
        /// Scoped by market, so two markets' equal option keys stay apart.
        var id: String { "\(questionKey)|\(optionKey)" }
    }

    /// The host's market, read without fallback.
    enum MarketSelection: Equatable {
        case unselected
        case unavailable
        case market(MLBSeriesCard11284.Question)
    }

    /// The host's outcome, read only inside the resolved market.
    enum OutcomeSelection: Equatable {
        case unselected
        case unavailable
        case option(MLBSeriesCard11284.Option)
    }

    /// Everything the view draws, decided once from the card and the host's
    /// two keys.
    struct Presentation: Equatable {
        let markets: [MarketChoice]
        let title: String
        let titleSpoken: String
        /// Said only when the host's outcome is not in this market's update.
        let outcomeNotice: String?
        /// The selected market's outcomes in the card's order; empty without
        /// a resolved market.
        let tiles: [Tile]
        /// `option.original.id`, or nil without a resolved outcome.
        let detailsID: String?
    }

    static func market(_ card: MLBSeriesCard11284, questionKey: String?) -> MarketSelection {
        guard let questionKey else { return .unselected }
        return card.questions.first { $0.questionKey == questionKey }.map(MarketSelection.market) ?? .unavailable
    }

    static func outcome(in question: MLBSeriesCard11284.Question, optionKey: String?) -> OutcomeSelection {
        guard let optionKey else { return .unselected }
        return question.options.first { $0.optionKey == optionKey }.map(OutcomeSelection.option) ?? .unavailable
    }

    static func markets(_ card: MLBSeriesCard11284, questionKey: String?) -> [MarketChoice] {
        card.questions.map { question in
            MarketChoice(id: question.questionKey, label: question.label,
                         spoken: "Market, \(question.label)",
                         isSelected: question.questionKey == questionKey)
        }
    }

    /// An admitted chance as a share of the ring; anything outside 0…1 or not
    /// finite draws nothing rather than a clipped arc.
    static func ringFraction(_ chance: Double?) -> Double? {
        guard let chance, chance.isFinite, (0...1).contains(chance) else { return nil }
        return chance
    }

    static func tile(_ question: MLBSeriesCard11284.Question, _ option: MLBSeriesCard11284.Option,
                     selected: Bool) -> Tile {
        let fraction = ringFraction(option.pregame)
        let text = fraction.map { formatProbability($0) }
        let spoken = "\(option.label), in \(question.label). "
            + (text.map { "\(pregameLabel) \($0)." } ?? "\(pregameLabel) unavailable.")
            + " \(resultLabel) \(option.result.label)."
        return Tile(questionKey: question.questionKey, optionKey: option.optionKey, label: option.label,
                    ringFraction: fraction, chanceText: text, result: option.result,
                    isSelected: selected, spoken: spoken, originalID: option.original.id)
    }

    static func presentation(_ card: MLBSeriesCard11284, questionKey: String?, optionKey: String?) -> Presentation {
        let choices = markets(card, questionKey: questionKey)
        switch market(card, questionKey: questionKey) {
        case .unselected:
            return Presentation(markets: choices, title: "Choose a market", titleSpoken: "No market selected",
                                outcomeNotice: nil, tiles: [], detailsID: nil)
        case .unavailable:
            return Presentation(markets: choices, title: "This market is unavailable in this update",
                                titleSpoken: "Selected market unavailable in this update",
                                outcomeNotice: nil, tiles: [], detailsID: nil)
        case .market(let question):
            let resolved = outcome(in: question, optionKey: optionKey)
            var selectedKey: String?
            var detailsID: String?
            var notice: String?
            switch resolved {
            case .option(let option):
                selectedKey = option.optionKey
                detailsID = option.original.id
            case .unavailable:
                notice = "The selected outcome is unavailable in this update"
            case .unselected:
                break
            }
            return Presentation(
                markets: choices, title: question.label, titleSpoken: "Selected market, \(question.label)",
                outcomeNotice: notice,
                tiles: question.options.map { tile(question, $0, selected: $0.optionKey == selectedKey) },
                detailsID: detailsID)
        }
    }

    /// Where a tile's chance goes.
    enum ChanceLayout: Equatable {
        /// Inside the bounded ring.
        case inside
        /// Below a small decorative ring, at full scaled size.
        case below
        /// No admitted chance: the word Unavailable, no ring.
        case absent
    }

    /// The scaled ring, never larger than its default.
    static func boundedRing(scaled: CGFloat) -> CGFloat { min(scaled, ringPointDiameter) }

    static func ringLineWidth(for diameter: CGFloat) -> CGFloat { diameter * 0.075 }

    /// Whether the widest chance at this figure size fits inside the ring's
    /// stroke with a little air.
    static func figureFitsInside(figureSize: CGFloat, ringDiameter: CGFloat) -> Bool {
        figureSize * widestFigureEms <= ringDiameter - 2 * ringLineWidth(for: ringDiameter) - 8
    }

    static func chanceLayout(_ tile: Tile, size: DynamicTypeSize, figureSize: CGFloat,
                             ringDiameter: CGFloat) -> ChanceLayout {
        guard tile.ringFraction != nil, tile.chanceText != nil else { return .absent }
        guard !size.isAccessibilitySize, figureFitsInside(figureSize: figureSize, ringDiameter: ringDiameter)
        else { return .below }
        return .inside
    }

    /// One row of the two-column grid.
    struct Pair: Equatable, Identifiable {
        let first: Tile
        let second: Tile?
        var id: String { first.id }
    }

    /// The tiles two at a time, in order; an odd last tile stands alone.
    static func pairs(_ tiles: [Tile]) -> [Pair] {
        stride(from: 0, to: tiles.count, by: 2).map { index in
            Pair(first: tiles[index], second: index + 1 < tiles.count ? tiles[index + 1] : nil)
        }
    }

    /// A non-colour cue for each result; the five never share a symbol.
    static func resultSymbol(_ result: MLBVenueResult11284) -> String {
        switch result {
        case .won: return "checkmark.circle.fill"
        case .lost: return "xmark.circle"
        case .open: return "circle.dashed"
        case .pending: return "clock"
        case .notConfirmed: return "questionmark.circle"
        }
    }

    /// Only a won outcome is tinted; open and pending are never celebrated.
    static func celebrates(_ result: MLBVenueResult11284) -> Bool { result == .won }
}
