import Charts
import Combine
import SwiftUI

/// #9483 — the NFL page's visual cards (design ref #10868 native v107):
/// one renderer per family, drawn compact in the deck under the chart and
/// full size in the reader (`NFLCardReader9483`). Compact and full size read
/// the same card value and the same selection, so opening a card never
/// changes what it says (v110).

// MARK: - Selection shared by compact and full size

/// The reader's state, owned by the page so it survives the deck → reader →
/// deck round trip and a size-class rebuild: which card is open, and which
/// original row each milestone card has selected.
@MainActor
final class NFLCardDeckState9483: ObservableObject {
    /// The card open full size, or nil.
    @Published var openCardID: String?
    /// The card the reader returns focus to when it closes.
    @Published private(set) var returnCardID: String?
    /// Selected original row per milestone card. A row that is no longer
    /// served selects nothing — never a neighbouring line (v110).
    @Published private var selectedRow: [String: String] = [:]
    /// The original row whose exact details are showing, or nil.
    @Published var detailsRowID: String?

    func open(_ cardID: String) {
        returnCardID = cardID
        openCardID = cardID
    }

    func close() {
        detailsRowID = nil
        openCardID = nil
    }

    func selectedIndex(in card: NFLMilestoneCard9483) -> Int? {
        guard let row = selectedRow[card.id] else { return card.defaultRung }
        return card.rungs.firstIndex { $0.rowID == row }
    }

    func move(in card: NFLMilestoneCard9483, by delta: Int) {
        guard let current = selectedIndex(in: card), card.rungs.indices.contains(current + delta) else { return }
        selectedRow[card.id] = card.rungs[current + delta].rowID
    }

    /// NBA ladders: the selected option, by the producer's option key. An
    /// option no longer on the card selects nothing, never a neighbour.
    func selectedIndex(in card: NBALadderCard9483) -> Int? {
        guard let option = selectedRow[card.id] else { return card.defaultIndex }
        return card.points.firstIndex { $0.optionKey == option }
    }

    func move(in card: NBALadderCard9483, by delta: Int) {
        guard let current = selectedIndex(in: card), card.points.indices.contains(current + delta) else { return }
        selectedRow[card.id] = card.points[current + delta].optionKey
    }

    // MARK: Final MLB stories (#11284)

    /// The key a final MLB card has selected in one of its slots — a target
    /// row, a run line's option, a series question or option — by the card's
    /// own `selectionSlot`, which names its event. Nil means the card's
    /// default; a key the card no longer carries selects nothing, never a
    /// neighbour (the card resolves it, v110's rule).
    func mlbSelection(_ slot: String) -> String? { selectedRow[slot] }

    func selectMLB(_ key: String, slot: String) {
        if selectedRow[slot] != key { selectedRow[slot] = key }
    }

    // MARK: NBA story stream (v445 + W1–W3)

    /// The compact NBA stream's applied/pending order, active card and hold,
    /// for ONE event. Nil until that event's stream begins. Written only
    /// through the guarded methods below, never during a body read.
    @Published private(set) var nbaStreamState: NBAStoryStreamPolicy9483.State?

    /// What the shelf showed, and what the reader did on it, while this
    /// event's deck was still loading and its stream had not begun (N4).
    struct NBABeforeBegin: Equatable {
        let eventID: Int
        /// The order the shelf shows (the latest plan received); the reader
        /// shows the same one.
        var orderedIDs: [String] = []
        /// The reader held the shelf (browsed, opened a card).
        var held = false
        /// The card they browsed to or opened.
        var chosenID: String?
    }

    /// Nil once the stream begins or the page's event changes.
    @Published private(set) var nbaBeforeBegin: NBABeforeBegin?

    /// The applied order for the page's reader (W1, W3): the applied ids'
    /// present cards, in applied order. Present cards not yet applied are
    /// pending and withheld. Before any stream begins, the shelf's own order
    /// for this event (N4); otherwise its own fallback.
    func appliedNBAOrder(eventID: Int, fallback cards: [NFLEventCard9483]) -> [NFLEventCard9483] {
        let present = Dictionary(cards.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        if let stream = nbaStreamState, stream.eventID == eventID {
            return stream.appliedIDs.compactMap { present[$0] }
        }
        guard let before = nbaBeforeBegin, before.eventID == eventID, !before.orderedIDs.isEmpty else { return cards }
        let ordered = before.orderedIDs.compactMap { present[$0] }
        return ordered + cards.filter { !before.orderedIDs.contains($0.id) }
    }

    /// Starts `plan`'s event's stream. The same event keeps its state; any
    /// other starts fresh, without the previous event's ladder selections.
    /// A hold or a card chosen on this event's shelf before it began carries
    /// over: the stream begins held, on that card when the plan has it (N4).
    func beginNBAStream(_ plan: NBAStoryStreamPolicy9483.Plan) {
        if let stream = nbaStreamState, stream.eventID == plan.eventID { return }
        if nbaStreamState != nil { clearNBALadderSelections() }
        var stream = NBAStoryStreamPolicy9483.State(plan: plan)
        if let before = nbaBeforeBegin, before.eventID == plan.eventID {
            if before.held { stream.hold() }
            if let chosen = before.chosenID { stream.focus(chosen, present: Set(plan.orderedIDs)) }
        }
        nbaBeforeBegin = nil
        nbaStreamState = stream
    }

    /// The page's event changed: the old event's reader/Details close, and
    /// its stream and ladder selections are discarded.
    func resetNBAStream() {
        close()
        clearNBALadderSelections()
        nbaStreamState = nil
        nbaBeforeBegin = nil
    }

    /// A producer/clock update for the running stream: pending only (W1).
    /// Before any stream begins, the order the shelf now shows (N4); with
    /// another event's stream running, nothing.
    func receiveNBAPlan(_ plan: NBAStoryStreamPolicy9483.Plan) {
        if nbaStreamState == nil {
            updateBeforeBegin(eventID: plan.eventID) { $0.orderedIDs = plan.orderedIDs }
        } else {
            updateNBAStream(eventID: plan.eventID) { $0.receive(plan) }
        }
    }

    func applyNBAPending(eventID: Int) {
        updateNBAStream(eventID: eventID) { $0.applyPending() }
    }

    func holdNBAStream(eventID: Int) {
        if nbaStreamState == nil {
            updateBeforeBegin(eventID: eventID) { $0.held = true }
        } else {
            updateNBAStream(eventID: eventID) { $0.hold() }
        }
    }

    func resumeNBAStream(eventID: Int) {
        updateNBAStream(eventID: eventID) { $0.resume() }
    }

    /// The one automatic boundary (W2): receive the plan made at the wake's
    /// own `now`, apply pending, then move to the next card, wrapping.
    func advanceNBAStream(_ plan: NBAStoryStreamPolicy9483.Plan, present: Set<String>) {
        updateNBAStream(eventID: plan.eventID) { stream in
            guard !stream.held, stream.receive(plan) else { return }
            stream.applyPending()
            stream.next(present: present, wrap: true)
        }
    }

    /// Manual browsing landed on a card: it becomes active and the stream
    /// holds. Before the stream begins, a card on the shelf is remembered as
    /// chosen, and held, for the begin (N4).
    func focusNBAStream(eventID: Int, cardID: String, present: Set<String>) {
        if nbaStreamState == nil {
            guard present.contains(cardID) else { return }
            updateBeforeBegin(eventID: eventID) {
                $0.held = true
                $0.chosenID = cardID
            }
        } else {
            updateNBAStream(eventID: eventID) { $0.focus(cardID, present: present) }
        }
    }

    /// The reader opens a card from the shelf. It becomes the active one
    /// first, so Back from a reader whose card has since left the deck lands
    /// on that card's held slot (W1 keeps a slot only for the active id).
    func openNBACard(eventID: Int, cardID: String, present: Set<String>) {
        holdNBAStream(eventID: eventID)
        focusNBAStream(eventID: eventID, cardID: cardID, present: present)
        open(cardID)
    }

    /// "See this line": selects `optionKey` on `card` only when the card is
    /// applied on this event's stream — or, before it begins, on this event's
    /// shelf (N4) — and the option is on it. A stale event or an absent
    /// option writes nothing — never a neighbour.
    @discardableResult
    func select(optionKey: String, in card: NBALadderCard9483, eventID: Int) -> Bool {
        let shown: Bool
        if let stream = nbaStreamState {
            shown = stream.eventID == eventID && stream.appliedIDs.contains(card.id)
        } else {
            shown = nbaBeforeBegin.map { $0.eventID == eventID && $0.orderedIDs.contains(card.id) } ?? false
        }
        guard shown, card.points.contains(where: { $0.optionKey == optionKey }) else { return false }
        selectedRow[card.id] = optionKey
        return true
    }

    private func updateNBAStream(eventID: Int, _ change: (inout NBAStoryStreamPolicy9483.State) -> Void) {
        guard var stream = nbaStreamState, stream.eventID == eventID else { return }
        change(&stream)
        if stream != nbaStreamState { nbaStreamState = stream }
    }

    /// Another event's record is replaced, never carried.
    private func updateBeforeBegin(eventID: Int, _ change: (inout NBABeforeBegin) -> Void) {
        var before = nbaBeforeBegin.flatMap { $0.eventID == eventID ? $0 : nil } ?? NBABeforeBegin(eventID: eventID)
        change(&before)
        if before != nbaBeforeBegin { nbaBeforeBegin = before }
    }

    /// The ladder families' selections ("total", "margin"); player rows stay.
    private func clearNBALadderSelections() {
        for family in [NBALadderCard9483.Family.total, .margin] {
            selectedRow[family.rawValue] = nil
        }
    }
}

// MARK: - Projected finish

struct NFLFinishCardView9483: View {
    let card: NFLFinishCard9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    var expanded = false
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    /// The line the chart draws each team's name on, at the top of its band.
    @ScaledMetric(relativeTo: .caption) private var trackNameLine: CGFloat = 16

    private var later: NFLFinishCard9483.Pair? { card.final ?? card.projectedNow }
    private var laterLabel: String? {
        card.final != nil ? "Final" : card.projectedNow != nil ? "Projected now" : nil
    }
    private var domain: ClosedRange<Double> {
        Self.pointDomain([card.pregame.away, card.pregame.home] + (later.map { [$0.away, $0.home] } ?? []),
                         step: card.tickStep)
    }

    /// The points axis: half a gridline past the largest number. Football
    /// keeps its zero-based touchdown axis; basketball's 100-plus scores would
    /// crowd the last tenth of a zero-based one, so its axis starts a gridline
    /// below the smallest number.
    static func pointDomain(_ values: [Double], step: Double) -> ClosedRange<Double> {
        let upper = max(2 * step, ((values.max() ?? 0) / step).rounded(.up) * step + step / 2)
        let lower = step <= 7 ? 0 : max(0, ((values.min() ?? 0) / step).rounded(.down) * step - step)
        return lower...upper
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(card.kicker.uppercased())
                .font(.caption.weight(.bold))
                .foregroundStyle(homeColor)
            Text(card.headline(awayName: awayName, homeName: homeName))
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Chart {
                ForEach([false, true], id: \.self) { isHome in
                    let name = isHome ? homeName : awayName
                    let color = isHome ? homeColor : awayColor
                    PointMark(x: .value("Points", isHome ? card.pregame.home : card.pregame.away),
                              y: .value("Team", name))
                        .symbol { Rectangle().stroke(color, lineWidth: 2).frame(width: 9, height: 9) }
                    if let later {
                        PointMark(x: .value("Points", isHome ? later.home : later.away),
                                  y: .value("Team", name))
                            .symbol(card.final != nil ? .cross : .square)
                            .foregroundStyle(color)
                    }
                }
            }
            .chartXScale(domain: domain)
            .chartYScale(domain: [awayName, homeName])
            .chartXAxis {
                AxisMarks(values: pointTicks) { value in
                    NFLStatAxisLabels9483.reservedLabel(value.as(Double.self).map(Self.points) ?? "",
                                                        fontSize: axisFontSize)
                }
            }
            .chartOverlay { proxy in
                GeometryReader { geo in
                    NFLStatAxisLabels9483(values: pointTicks, texts: pointTicks.map(Self.points),
                                          keep: nil, fontSize: axisFontSize,
                                          proxy: proxy, plotFrame: geo[proxy.plotAreaFrame])
                }
            }
            .frame(height: chartHeight)
            .accessibilityHidden(true)
            ForEach([false, true], id: \.self) { isHome in
                // One row when the name and both numbers fit whole; otherwise
                // (large type, narrow phone) the name takes its own line and
                // each number sits above its label, so no name or decimal is
                // ever broken across lines.
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline) {
                        teamName(isHome: isHome)
                        Spacer(minLength: 8)
                        number(pregameText(isHome ? card.pregame.home : card.pregame.away), label: card.pregameLabel)
                        if let later, let laterLabel {
                            number(isHome ? later.home : later.away, label: laterLabel.lowercased())
                                .frame(minWidth: 72, alignment: .trailing)
                        }
                    }
                    VStack(alignment: .leading, spacing: 4) {
                        teamName(isHome: isHome)
                        number(pregameText(isHome ? card.pregame.home : card.pregame.away), label: card.pregameLabel,
                               alignment: .leading)
                        if let later, let laterLabel {
                            number(isHome ? later.home : later.away, label: laterLabel.lowercased(),
                                   alignment: .leading)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            Text(card.key)
                .font(.caption2)
                .foregroundStyle(.secondary)
            // #9483 A3 — live with no current projection: said, so the earlier
            // pair above is never read as the current one.
            if let note = card.missingCurrentNote {
                Text(note)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityText)
    }

    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }
    private var chartHeight: CGFloat {
        Self.chartHeight(expanded: expanded, nameLine: trackNameLine, axisFontSize: axisFontSize)
    }

    /// #11285 — each team's band draws its name at the top and its points
    /// across the middle, so the band's top half holds the name's line and
    /// half a mark: at large sizes the chart grows rather than drawing the
    /// points over the name ("Comm▪an◻ders" at AX5). Default sizes keep 120.
    static func chartHeight(expanded: Bool, nameLine: CGFloat, axisFontSize: CGFloat) -> CGFloat {
        max(expanded ? 220 : 120, 2 * 2 * (nameLine + 8) + 2 * axisFontSize)
    }
    /// One tick per gridline step (a touchdown in football) across the axis.
    private var pointTicks: [Double] {
        Array(stride(from: domain.lowerBound, through: domain.upperBound, by: card.tickStep))
    }

    private func teamName(isHome: Bool) -> some View {
        Text(isHome ? homeName : awayName)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(isHome ? homeColor : awayColor)
            // #11285 — a one-word name too wide for its own line at the
            // largest sizes ("Command…" at AX5) shrinks to fit, never broken.
            .lineLimit(1)
            .minimumScaleFactor(0.8)
    }

    private func number(_ value: Double, label: String,
                        alignment: HorizontalAlignment = .trailing) -> some View {
        number(Self.points(value), label: label, alignment: alignment)
    }

    private func number(_ text: String, label: String,
                        alignment: HorizontalAlignment = .trailing) -> some View {
        VStack(alignment: alignment, spacing: 0) {
            Text(text)
                .font(.headline.monospacedDigit())
                .fixedSize()
            // #11285 — the label wraps in the stacked layout ("pregame
            // proje…" at the largest text size).
            Text(label)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// A projection keeps its half point; a final score is whole.
    static func points(_ value: Double) -> String {
        value.rounded() == value ? String(Int(value)) : String(format: "%.1f", value)
    }

    /// #11296 — the pregame number as printed: whole, as the headline prints
    /// it, on a finished card's qualified pair; otherwise `points`.
    private func pregameText(_ value: Double) -> String {
        Self.pregameText(value, whole: card.printsPregameWhole)
    }

    static func pregameText(_ value: Double, whole: Bool) -> String {
        guard whole, let rounded = Int(exactly: value.rounded()) else { return points(value) }
        return String(rounded)
    }

    private var accessibilityText: String {
        var parts = [card.kicker, card.headline(awayName: awayName, homeName: homeName),
                     "\(card.pregameName) "
                     + "\(awayName) \(pregameText(card.pregame.away)), \(homeName) \(pregameText(card.pregame.home))"]
        if let later, let laterLabel {
            parts.append("\(laterLabel) \(awayName) \(Self.points(later.away)), \(homeName) \(Self.points(later.home))")
        }
        if let note = card.missingCurrentNote { parts.append(note) }
        return parts.joined(separator: ". ")
    }
}

// MARK: - Player milestones

struct NFLMilestoneCardView9483: View {
    let card: NFLMilestoneCard9483
    let color: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var size
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }

    var body: some View {
        let selected = state.selectedIndex(in: card)
        let rung = selected.map { card.rungs[$0] }
        VStack(alignment: .leading, spacing: 10) {
            if size.isAccessibilitySize {
                // #11285 (Design, 0220Z) — at accessibility sizes the name takes
                // the card's whole width under the category and final figure;
                // beside the figure it broke mid-word ("DeVon- / ta" at AX5 on
                // a 393pt phone).
                VStack(alignment: .leading, spacing: 3) {
                    HStack(alignment: .top) {
                        statLabel
                        Spacer(minLength: 4)
                        actualFigure
                    }
                    playerName
                }
            } else {
                HStack(alignment: .top) {
                    // #11285 — a small identity cue beside the name when this
                    // ladder's own rows serve a headshot; loading or failed keeps
                    // a plain circle, so the name never moves. At accessibility
                    // sizes the cue is dropped: its 44pt broke "McCaf-/frey" mid-word
                    // on a 375pt phone at AX5, and the name is the identity.
                    if let headshot = card.headshot {
                        AsyncImage(url: headshot) { phase in
                            if case .success(let image) = phase {
                                image.resizable().scaledToFill()
                            } else {
                                color.opacity(0.15)
                            }
                        }
                        .frame(width: 36, height: 36)
                        .clipShape(Circle())
                        .accessibilityHidden(true)
                    }
                    VStack(alignment: .leading, spacing: 3) {
                        statLabel
                        playerName
                    }
                    Spacer(minLength: 4)
                    actualFigure
                }
            }
            Text(card.caption)
                .font(.caption)
                .foregroundStyle(.secondary)
            if let profile = card.profile {
                chart(profile, selected: rung)
            }
            if card.profile == nil {
                // Every price on the card has stopped being observed: the
                // lines stay, the shape does not.
                Text("No recent probability updates")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, minHeight: expanded ? 120 : 60)
            }
            HStack(spacing: 4) {
                Button { state.move(in: card, by: -1) } label: {
                    Image(systemName: "chevron.left").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 == 0 } ?? true)
                .accessibilityLabel("Previous line")
                if expanded {
                    // Details sheet lives on the full-size reader only; the
                    // compact card opens through its "Open story" control.
                    Button {
                        if let rung { state.detailsRowID = rung.rowID }
                    } label: {
                        readout(rung)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Shows this line's exact quote")
                } else {
                    readout(rung)
                        .accessibilityElement(children: .combine)
                }
                Button { state.move(in: card, by: 1) } label: {
                    Image(systemName: "chevron.right").frame(width: 44, height: 44)
                }
                .disabled(selected.map { $0 >= card.rungs.count - 1 } ?? true)
                .accessibilityLabel("Next line")
            }
        }
    }

    // #11285 — the plotted quantity wraps rather than truncating beside a
    // final figure ("Receiving Yar…" at AX3).
    private var statLabel: some View {
        Text(card.stat)
            .font(.caption)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    // #11061 — a hyphenated name needs a third line at accessibility sizes
    // ("Jaxon / Smith- / Njigba").
    private var playerName: some View {
        Text(card.player)
            .font(.title3.weight(.bold))
            .lineLimit(3)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private var actualFigure: some View {
        if let actual = card.actual {
            VStack(alignment: .trailing, spacing: 0) {
                Text(NFLFinishCardView9483.points(actual))
                    .font(.title.weight(.bold).monospacedDigit())
                    .foregroundStyle(color)
                Text("final")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
    }

    private func readout(_ rung: NFLMilestoneCard9483.Rung?) -> some View {
        VStack(spacing: 2) {
            if let rung {
                Text(rung.chance.map {
                    "\(PlayerPropsFamily.targetLabel(rung.threshold)) · \(formatProbability($0))"
                } ?? "\(PlayerPropsFamily.targetLabel(rung.threshold)) · \(noChance)")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(rung.chance == nil ? Color.secondary : color)
                Text(verdict(rung))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .multilineTextAlignment(.center)
        .frame(maxWidth: .infinity, minHeight: 44)
        .contentShape(Rectangle())
    }

    /// What a line with no number says, by basis: a quote that stopped being
    /// observed, or a line the server served no pregame mark for.
    private var noChance: String {
        card.basis == .pregamePrice ? "No recent probability update" : "No pregame chance"
    }

    private func verdict(_ rung: NFLMilestoneCard9483.Rung) -> String {
        let more = expanded ? " · details" : ""
        switch rung.hit {
        case true?: return "Reached" + more
        case false?: return "Not reached" + more
        case nil:
            if rung.chance == nil { return !expanded ? "" : card.basis == .pregamePrice ? "Last quote in details" : "Details" }
            return (card.basis == .pregamePrice ? "Pregame chance" : "Before kickoff") + more
        }
    }

    private func chart(_ profile: PlayerMilestoneProfile.Profile, selected: NFLMilestoneCard9483.Rung?) -> some View {
        let domain = NFLMilestoneCard9483.statDomain(profile.domain, actual: card.actual)
        return Chart {
            // The final is a rule on the stat axis. Its value is printed large
            // in the card's header, so the rule carries no second label to clip.
            if let actual = card.actual {
                RectangleMark(xStart: .value("Start", domain.lowerBound), xEnd: .value("Final", actual),
                              yStart: .value("Chance", 0), yEnd: .value("Chance", 1))
                    .foregroundStyle(color.opacity(0.07))
                RuleMark(x: .value("Final", actual))
                    .foregroundStyle(color)
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }
            RuleMark(y: .value("Chance", 0.5))
                .foregroundStyle(Color.secondary.opacity(0.35))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            ForEach(card.rungs.filter { $0.chance != nil }) { rung in
                let isSelected = rung.rowID == selected?.rowID
                let chance = rung.chance ?? 0
                RuleMark(x: .value("Line", rung.threshold),
                         yStart: .value("Chance", 0), yEnd: .value("Chance", chance))
                    .foregroundStyle(color.opacity(isSelected ? 0.9 : 0.3))
                    .lineStyle(StrokeStyle(lineWidth: isSelected ? 2 : 1.5))
                PointMark(x: .value("Line", rung.threshold), y: .value("Chance", chance))
                    .symbol {
                        Circle()
                            .strokeBorder(isSelected ? color : Color.secondary, lineWidth: isSelected ? 2.5 : 1.5)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: isSelected ? 13 : 8, height: isSelected ? 13 : 8)
                    }
            }
        }
        .chartXScale(domain: domain)
        .chartYScale(domain: 0...1)
        .chartYAxis {
            AxisMarks(position: .leading, values: [0, 0.5, 1]) { value in
                AxisGridLine().foregroundStyle(Color.secondary.opacity(0.15))
                AxisValueLabel {
                    if let chance = value.as(Double.self) { Text("\(Int((chance * 100).rounded()))%") }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: card.rungs.map(\.threshold)) { value in
                NFLStatAxisLabels9483.reservedLabel(
                    value.as(Double.self).map(PlayerPropsFamily.targetLabel) ?? "", fontSize: axisFontSize)
            }
        }
        // Every quoted line has a tick, priced or not, so a line with no
        // recent price still stands where it is; each label is centred under
        // its own tick and stem. A row too dense for every label keeps the
        // selected line's label first and drops whole labels, never overlaps.
        .chartOverlay { proxy in
            GeometryReader { geo in
                NFLStatAxisLabels9483(values: card.rungs.map(\.threshold),
                                      texts: card.rungs.map { PlayerPropsFamily.targetLabel($0.threshold) },
                                      keep: card.rungs.firstIndex { $0.rowID == selected?.rowID },
                                      fontSize: axisFontSize, proxy: proxy,
                                      plotFrame: geo[proxy.plotAreaFrame], ticks: true)
            }
        }
        .frame(height: expanded ? 240 : 150)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlayerMilestoneProfile.spokenSummary(profile, stat: card.stat)
            + (card.actual.map { ". Final \(NFLFinishCardView9483.points($0))" } ?? ""))
    }
}

// MARK: - Stat-axis labels

/// The cards' stat-axis labels, drawn by us and centred on their ticks — the
/// #8481 rule, for the same reason (`ChartTimeAxisLabels`): on iOS 27 an
/// `AxisValueLabel` hangs RIGHT of its tick whether it is `anchor: .top` or
/// `collisionResolution: .greedy`, so on a 5- or 10-yard ladder every label
/// printed under the NEXT stem ("40+" under the 50+ stem, native's runtime
/// review of PR #11038). The framework keeps an invisible label per tick for
/// the row's height; this view draws the visible one.
struct NFLStatAxisLabels9483: View {
    let values: [Double]
    let texts: [String]
    /// The label kept first when the row cannot hold them all (the selected line).
    let keep: Int?
    let fontSize: CGFloat
    let proxy: ChartProxy
    let plotFrame: CGRect
    var ticks = false

    /// The framework's label, kept for the row's height, never for its ink.
    static func reservedLabel(_ text: String, fontSize: CGFloat) -> some AxisMark {
        AxisValueLabel(anchor: .topTrailing) {
            Text(text).font(.system(size: fontSize)).foregroundStyle(Color.clear)
        }
    }

    /// The width a label's ink takes at `fontSize`, measured in the font it is
    /// drawn in.
    static func labelWidth(_ text: String, fontSize: CGFloat) -> CGFloat {
        #if canImport(UIKit)
        return (text as NSString).size(withAttributes: [.font: UIFont.systemFont(ofSize: fontSize)]).width
        #else
        return CGFloat(text.count) * fontSize * 0.62
        #endif
    }

    /// Which labels are drawn, and where each one's centre sits in plot points.
    ///
    /// Every label is centred on its tick, then moved inward only as far as it
    /// must go to stay inside the plot (`OddsChartView.xAxisLabelCenters`).
    /// Where two would come closer than `xAxisLabelMinGap`, the later one in
    /// priority order is dropped WHOLE — the kept label (the selected line),
    /// then the two ends, then the rest left to right — so no label is ever
    /// printed over another or under a neighbour's stem.
    static func placements(tickPositions: [CGFloat], widths: [CGFloat], plotWidth: CGFloat,
                           keep: Int?) -> [(index: Int, center: CGFloat)] {
        let count = min(tickPositions.count, widths.count)
        guard count > 0 else { return [] }
        let centers = (0..<count).map {
            OddsChartView.xAxisLabelCenters(tickPositions: [tickPositions[$0]], plotWidth: plotWidth,
                                            labelWidth: widths[$0])[0]
        }
        var order = [keep, 0, count - 1].compactMap { $0 }.filter { (0..<count).contains($0) }
        order += (0..<count).filter { !order.contains($0) }
        var kept: [Int] = []
        for index in order where !kept.contains(index) {
            let clear = kept.allSatisfy { other in
                abs(centers[index] - centers[other])
                    >= (widths[index] + widths[other]) / 2 + OddsChartView.xAxisLabelMinGap
            }
            if clear { kept.append(index) }
        }
        return kept.sorted().map { ($0, centers[$0]) }
    }

    var body: some View {
        let count = min(values.count, texts.count)
        let placed: [(index: Int, x: CGFloat)] = (0..<count).compactMap { index in
            proxy.position(forX: values[index]).map { (index, $0) }
        }
        let labelY = plotFrame.maxY + ChartTimeAxisLabels.labelCenterOffset * fontSize / 9
        let shown = Self.placements(tickPositions: placed.map(\.x),
                                    widths: placed.map { Self.labelWidth(texts[$0.index], fontSize: fontSize) },
                                    plotWidth: plotFrame.width, keep: placed.firstIndex { $0.index == keep })
        if ticks {
            ForEach(Array(placed.enumerated()), id: \.offset) { _, item in
                Rectangle()
                    .fill(Color.secondary.opacity(0.6))
                    .frame(width: 1, height: 4)
                    .position(x: plotFrame.minX + item.x, y: plotFrame.maxY + 2)
            }
            .accessibilityHidden(true)
            .allowsHitTesting(false)
        }
        ForEach(shown, id: \.index) { label in
            Text(texts[placed[label.index].index])
                .font(.system(size: fontSize))
                .foregroundStyle(Color.primary)
                .lineLimit(1)
                .fixedSize()
                .position(x: plotFrame.minX + label.center, y: labelY)
                .accessibilityHidden(true)
                .allowsHitTesting(false)
        }
    }
}

// MARK: - One card, either family

struct NFLEventCardView9483: View {
    let card: NFLEventCard9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        Group {
            switch card {
            case .finish(let finish):
                NFLFinishCardView9483(card: finish, awayName: awayName, homeName: homeName,
                                      awayColor: awayColor, homeColor: homeColor, expanded: expanded)
            case .milestone(let milestone):
                NFLMilestoneCardView9483(
                    card: milestone,
                    color: PlayerPropsTeam.color(for: milestone.side, home: homeColor, away: awayColor),
                    state: state, expanded: expanded)
            case .ladder(let ladder):
                NBALadderCardView9483(card: ladder, awayColor: awayColor, homeColor: homeColor,
                                      state: state, expanded: expanded)
            case .mlb(let mlb):
                MLBFinalCardView11284(card: mlb, awayColor: awayColor, homeColor: homeColor,
                                      state: state, expanded: expanded)
            }
        }
        .padding(16)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 16))
        .overlay(RoundedRectangle(cornerRadius: 16).stroke(Color.secondary.opacity(0.15)))
    }
}

// MARK: - The deck under the chart

/// The deck's heading, shared by the deck and the NBA story stream: "Game
/// stories" with its card count at the trailing edge. #11285 — on a 320pt
/// screen at accessibility sizes the row cannot hold both whole and the title
/// broke mid-word ("Game sto-ries"), so there the count goes under the title,
/// which wraps between words. Where both fit, the row is unchanged.
struct GameStoriesHeader9483: View {
    /// Nil prints no count.
    let count: Int?
    var alignment: VerticalAlignment = .center

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: alignment) {
                title
                Spacer()
                countText
            }
            VStack(alignment: .leading, spacing: 2) {
                title
                countText
            }
        }
    }

    private var title: some View {
        Text("Game stories")
            .font(.headline)
    }

    @ViewBuilder
    private var countText: some View {
        if let count {
            Text(count == 1 ? "1 card" : "\(count) cards")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }
}

/// The compact cards, side by side, each with an explicit "Open" control —
/// the page scrolls vertically, so a tap on a chart inside a card is never
/// taken as a request to expand it.
struct NFLEventCardDeckView9483: View {
    /// #11285 (Alex, build 65) — the compact card's opener. "Open full size"
    /// promised a screen-filling view the reader does not draw (it keeps the
    /// game context and a neighbouring card's edge); "Open story" (Root 2018Z)
    /// names what it opens. One spelling for the deck and the NBA stream;
    /// VoiceOver says `openerAccessibilityLabel`.
    static let openerTitle = "Open story"
    static func openerAccessibilityLabel(_ cardTitle: String) -> String { "Open \(cardTitle)" }
    static let openerIdentifier = "story-card-open"

    let cards: [NFLEventCard9483]
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    /// The compact NBA story stream, or nil (the default) for the ordinary
    /// deck. When set, the stream REPLACES the deck's scroller — one
    /// horizontal container, never nested.
    var stream: NBAStoryStreamView9483.Page?
    @AccessibilityFocusState private var focused: String?
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// A card's width in the deck: the next card peeks past its edge. #11285 —
    /// on a 320pt screen (Display Zoom) at accessibility sizes a peeking card
    /// cannot hold a whole team name even at its smallest allowed size
    /// ("Commanders" at AX5 needs 238pt; the peeking card leaves 216), so each
    /// card takes the whole width there; the count says there are more. The
    /// NBA story stream's shelf uses the same rule.
    static func cardWidth(_ width: CGFloat, count: Int, accessibility: Bool) -> CGFloat {
        count > 1 && !(accessibility && width < 300) ? width * 0.86 : width
    }

    var body: some View {
        if let stream {
            NBAStoryStreamView9483(cards: cards, awayName: awayName, homeName: homeName,
                                   awayColor: awayColor, homeColor: homeColor, state: state,
                                   page: stream, signals: stream.signals)
        } else {
            deck
        }
    }

    private var deck: some View {
        VStack(alignment: .leading, spacing: 8) {
            GameStoriesHeader9483(count: cards.count)
            // Re-read each minute so a pregame price that stops being observed
            // loses its number on the page too, not only in the reader.
            TimelineView(.periodic(from: .now, by: 60)) { tick in
            ScrollViewReader { proxy in
            ScrollView(.horizontal, showsIndicators: false) {
                LazyHStack(alignment: .top, spacing: 12) {
                    ForEach(cards.map { $0.current(at: tick.date) }) { card in
                        VStack(spacing: 6) {
                            NFLEventCardView9483(card: card, awayName: awayName, homeName: homeName,
                                                 awayColor: awayColor, homeColor: homeColor, state: state)
                            Button { state.open(card.id) } label: {
                                Label(Self.openerTitle, systemImage: "arrow.up.left.and.arrow.down.right")
                                    .font(.caption.weight(.semibold))
                                    .frame(maxWidth: .infinity, minHeight: 44)
                            }
                            .accessibilityLabel(Self.openerAccessibilityLabel(card.title))
                            .accessibilityIdentifier(Self.openerIdentifier)
                        }
                        .containerRelativeFrame(.horizontal) { width, _ in
                            Self.cardWidth(width, count: cards.count,
                                           accessibility: dynamicTypeSize.isAccessibilitySize)
                        }
                        .accessibilityFocused($focused, equals: card.id)
                        .id(card.id)
                    }
                }
                .scrollTargetLayout()
            }
            .scrollTargetBehavior(.viewAligned)
            // #11060 — Back lands on the card it was opened from, on screen,
            // even when a rotation under the reader re-laid this deck out.
            .onChange(of: state.openCardID) { old, new in
                guard old != nil, new == nil, let back = state.returnCardID else { return }
                proxy.scrollTo(back, anchor: .leading)
            }
            }
            }
        }
        // Back from the reader returns focus to the card it was opened from.
        .onChange(of: state.openCardID) { old, new in
            if old != nil, new == nil { focused = state.returnCardID }
        }
    }
}
