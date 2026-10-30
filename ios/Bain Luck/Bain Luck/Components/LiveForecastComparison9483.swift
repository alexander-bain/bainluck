import Charts
import SwiftUI

/// #9483 — before and during a game, each team's earlier projected final
/// beside its current one, at one readable size, on one points scale for
/// both teams (design ref `forecast-shift-visual-20261026/phone-after.png`,
/// `phone-large.png`, `tablet-after.png`).
///
/// An outlined square is the earlier forecast, a filled square the current
/// one. The thin line between them compares two quantities; it is not a
/// forecast history. These are projected final points, never chances and
/// never the actual score, which stays in the page's headline.
///
/// Presentation only. `NFLFinishCard9483` owns admission, the phase, the
/// earlier pair's basis, the current projection's expiry and every word;
/// `NFLFinishCardView9483` owns the points formatting and the axis domain;
/// `deltaPointsNumber` owns the change's magnitude. This view adds no
/// formatter, rounding rule, clock, source, publisher or retained state, and
/// never reads `final`.
///
/// It draws a card before or during play (`applies`). A finished card draws
/// nothing, so the host keeps its final renderer.
///
/// Mount (Native, later): in `NFLEventCardView9483`'s `.finish` case, draw
/// this when `applies(finish)`, the final sibling when that one applies, and
/// `NFLFinishCardView9483` otherwise. The host keeps passing the held card
/// through its existing `withoutProjectedNow` withdrawal; this view never
/// keeps a current projection the card no longer carries.
struct LiveForecastComparison9483: View {
    let card: NFLFinishCard9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    var expanded = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    /// The narrowest a team panel may be beside the other one.
    @ScaledMetric(relativeTo: .body) private var panelWidth: CGFloat = 285
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12

    /// One team's numbers. The plot positions are the card's values,
    /// unrounded; the printed text comes from the existing helpers.
    nonisolated struct Side: Equatable, Identifiable {
        let isHome: Bool
        let name: String
        let earlier: Double
        /// The current projection, or nil: before play, and while live when
        /// the card has none. Never the earlier value or a final.
        let current: Double?
        var id: Bool { isHome }
    }

    /// The current projection's label: the word the existing card prints.
    static let currentLabel = "Projected now"

    /// The scale's name, said once for both tracks.
    static let scaleCaption = "Projected final points · same scale for both teams"

    /// Before or during play, with every number it would draw a real number.
    /// A finished card, or one carrying a value no axis can hold, draws
    /// nothing — no mark is ever made up from a missing or invalid number.
    static func applies(_ card: NFLFinishCard9483) -> Bool {
        guard card.phase != .after, card.pregame.away.isFinite, card.pregame.home.isFinite else { return false }
        guard card.phase == .during, let now = card.projectedNow else { return true }
        return now.away.isFinite && now.home.isFinite
    }

    /// Away first, then home — the existing card's order. Empty unless
    /// `applies`. Before play the card's one pair is the only number; a
    /// current projection is read only while live.
    static func sides(_ card: NFLFinishCard9483, awayName: String, homeName: String) -> [Side] {
        guard applies(card) else { return [] }
        let now = card.phase == .during ? card.projectedNow : nil
        return [Side(isHome: false, name: awayName, earlier: card.pregame.away, current: now?.away),
                Side(isHome: true, name: homeName, earlier: card.pregame.home, current: now?.home)]
    }

    /// The earlier forecast as the existing card prints it.
    static func earlierText(_ card: NFLFinishCard9483, _ side: Side) -> String {
        NFLFinishCardView9483.pregameText(side.earlier, whole: card.printsPregameWhole)
    }

    static func currentText(_ side: Side) -> String? {
        side.current.map(NFLFinishCardView9483.points)
    }

    /// How the current projection compares with the earlier one, from the
    /// exact difference of the two values. A real difference too small for
    /// one decimal is never called unchanged.
    static func changeText(from earlier: Double, to current: Double) -> String {
        let difference = current - earlier
        guard difference != 0 else { return "Unchanged" }
        let direction = difference > 0 ? "higher" : "lower"
        let magnitude = deltaPointsNumber(difference)
        let zero = deltaPointsNumber(0)
        return magnitude == zero ? "Less than 0.1 points \(direction)" : "\(magnitude) points \(direction)"
    }

    static func changeText(_ side: Side) -> String? {
        side.current.map { changeText(from: side.earlier, to: $0) }
    }

    /// The one points axis both teams share: the existing card's domain over
    /// every number drawn — the earlier pair, and the current one when live.
    static func domain(_ card: NFLFinishCard9483) -> ClosedRange<Double> {
        let values = sides(card, awayName: "", homeName: "").flatMap { side -> [Double] in
            [side.earlier] + (side.current.map { [$0] } ?? [])
        }
        return NFLFinishCardView9483.pointDomain(values, step: card.tickStep)
    }

    /// One labelled tick per gridline step (a touchdown, twenty points).
    static func ticks(_ card: NFLFinishCard9483) -> [Double] {
        let range = domain(card)
        return Array(stride(from: range.lowerBound, through: range.upperBound, by: card.tickStep))
    }

    /// What VoiceOver says for one team, in reading order: its whole name,
    /// the earlier forecast under its own basis, the current projection or
    /// its absence, then the comparison — in the numbers the card prints.
    static func spoken(_ card: NFLFinishCard9483, _ side: Side) -> String {
        var parts = [side.name, "\(card.pregameName) \(earlierText(card, side)) points"]
        if let now = currentText(side), let change = changeText(side) {
            parts += ["\(currentLabel) \(now) points", change]
        } else if let note = card.missingCurrentNote {
            parts.append("\(currentLabel): \(note)")
        }
        return parts.joined(separator: ". ") + "."
    }

    /// The two team panels stack at the largest text sizes; below that they
    /// sit side by side only where both fit whole.
    static func alwaysStacksPanels(_ size: DynamicTypeSize) -> Bool { size >= .xxxLarge }

    /// A team's two figures stack at accessibility sizes; below that they are
    /// two columns where both fit whole.
    static func alwaysStacksFigures(_ size: DynamicTypeSize) -> Bool { size.isAccessibilitySize }

    /// A track holds its marks and one line of tick labels, and grows only
    /// with those labels — never a blank band.
    static func trackHeight(axisFontSize: CGFloat, expanded: Bool) -> CGFloat {
        (expanded ? 36 : 28) + axisFontSize * 1.5 + 10
    }

    var body: some View {
        if Self.applies(card) {
            comparison
        }
    }

    private var teamSides: [Side] { Self.sides(card, awayName: awayName, homeName: homeName) }
    private var axisDomain: ClosedRange<Double> { Self.domain(card) }
    private var axisTicks: [Double] { Self.ticks(card) }
    private var axisFontSize: CGFloat { EventChartTypography.labelSize(scaled: scaledAxisFont) }
    private func color(_ side: Side) -> Color { side.isHome ? homeColor : awayColor }

    private var comparison: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 6) {
                Text(card.kicker.uppercased())
                    .font(.caption.weight(.bold))
                    .foregroundStyle(homeColor)
                Text(card.headline(awayName: awayName, homeName: homeName))
                    .font(.title3.weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(card.kicker). \(card.headline(awayName: awayName, homeName: homeName))")
            .accessibilityAddTraits(.isHeader)
            Text(Self.scaleCaption)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            // #9483 A3 — live with no current projection: said once, legibly,
            // so the earlier numbers below are never read as current. Each
            // team's spoken summary carries it in its own place.
            if let note = card.missingCurrentNote {
                Text(note)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityHidden(true)
            }
            if Self.alwaysStacksPanels(typeSize) {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 28) {
                        ForEach(teamSides) { side in
                            panel(side).frame(minWidth: panelWidth, maxWidth: .infinity, alignment: .leading)
                        }
                    }
                    stacked
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
    }

    private var stacked: some View {
        VStack(alignment: .leading, spacing: 20) {
            ForEach(teamSides) { side in panel(side) }
        }
    }

    private func panel(_ side: Side) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    teamName(side)
                    Spacer(minLength: 8)
                    change(side)
                }
                VStack(alignment: .leading, spacing: 4) {
                    teamName(side)
                    change(side)
                }
            }
            if Self.alwaysStacksFigures(typeSize) {
                VStack(alignment: .leading, spacing: 12) { figures(side) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .liveForecastFigure9483, spacing: 24) { figures(side) }
                    VStack(alignment: .leading, spacing: 12) { figures(side) }
                }
            }
            track(side)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.spoken(card, side))
    }

    /// The full name wraps between words; it is never shrunk or cut.
    private func teamName(_ side: Side) -> some View {
        Text(side.name)
            .font(.headline)
            .foregroundStyle(color(side))
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder private func change(_ side: Side) -> some View {
        if let text = Self.changeText(side) {
            Text(text)
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private func figures(_ side: Side) -> some View {
        figure(card.pregameName, text: Self.earlierText(card, side)) { EarlierMark(color: color(side)) }
        if let now = Self.currentText(side) {
            figure(Self.currentLabel, text: now) { CurrentMark(color: color(side)) }
        }
    }

    private func figure<Mark: View>(_ label: String, text: String, @ViewBuilder mark: () -> Mark) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                mark()
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(text)
                .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                .fixedSize()
                // The guide sits on the number, so a scheduled-start label
                // that wraps to more lines than "Projected now" still leaves
                // the two numbers on one line.
                .alignmentGuide(.liveForecastFigure9483) { $0[.firstTextBaseline] }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// One team's points track on the shared axis.
    private func track(_ side: Side) -> some View {
        let tint = color(side)
        let domain = axisDomain
        let ticks = axisTicks
        return Chart {
            RuleMark(xStart: .value("Points", domain.lowerBound), xEnd: .value("Points", domain.upperBound),
                     y: .value("Position", 1))
                .foregroundStyle(Color.secondary.opacity(0.2))
            if let now = side.current, now != side.earlier {
                RuleMark(xStart: .value("Points", min(now, side.earlier)),
                         xEnd: .value("Points", max(now, side.earlier)),
                         y: .value("Position", 1))
                    .foregroundStyle(tint.opacity(0.6))
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }
            PointMark(x: .value("Points", side.earlier), y: .value("Position", 1))
                .symbol { EarlierMark(color: tint) }
            if let now = side.current {
                PointMark(x: .value("Points", now), y: .value("Position", 1))
                    .symbol { CurrentMark(color: tint) }
            }
        }
        // Padding keeps a mark at zero, or at the axis end, whole.
        .chartXScale(domain: domain, range: .plotDimension(startPadding: 8, endPadding: 8))
        .chartYScale(domain: 0.0...2.0)
        .chartYAxis(.hidden)
        .chartLegend(.hidden)
        .chartXAxis {
            AxisMarks(values: ticks) { value in
                NFLStatAxisLabels9483.reservedLabel(value.as(Double.self).map(NFLFinishCardView9483.points) ?? "",
                                                    fontSize: axisFontSize)
            }
        }
        .chartOverlay { proxy in
            GeometryReader { geo in
                NFLStatAxisLabels9483(values: ticks, texts: ticks.map(NFLFinishCardView9483.points),
                                      keep: nil, fontSize: axisFontSize,
                                      proxy: proxy, plotFrame: geo[proxy.plotAreaFrame], ticks: true)
            }
        }
        .frame(height: Self.trackHeight(axisFontSize: axisFontSize, expanded: expanded))
        .accessibilityHidden(true)
    }

    /// The earlier forecast: an outline, as on the existing card, a little
    /// larger than the filled mark so a coincident current one shows inside it.
    private struct EarlierMark: View {
        let color: Color
        var body: some View {
            Rectangle()
                .fill(Color.cardBackground)
                .overlay(Rectangle().strokeBorder(color, lineWidth: 2))
                .frame(width: 13, height: 13)
                .accessibilityHidden(true)
        }
    }

    /// The current projection: filled, as on the existing card.
    private struct CurrentMark: View {
        let color: Color
        var body: some View {
            Rectangle()
                .fill(color)
                .frame(width: 9, height: 9)
                .accessibilityHidden(true)
        }
    }
}

extension VerticalAlignment {
    /// Lines up a team's earlier and current figures on the numbers'
    /// baseline, whatever height the labels above them wrap to.
    private enum LiveForecastFigure9483: AlignmentID {
        static func defaultValue(in context: ViewDimensions) -> CGFloat { context[.top] }
    }

    fileprivate static let liveForecastFigure9483 = VerticalAlignment(LiveForecastFigure9483.self)
}
