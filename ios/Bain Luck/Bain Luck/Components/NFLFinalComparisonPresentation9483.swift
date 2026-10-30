import Charts
import SwiftUI

/// #9483 — a finished NFL game's final score beside the forecast it is
/// compared with, at one readable size, on one points scale for both teams
/// (design ref `score-forecast-unavailable-20261026/phone-final.png`, native
/// view reference `native-score-forecast-20261026/`).
///
/// Presentation only. `NFLFinishCard9483` owns admission, the pregame basis
/// and every word; `NFLFinishCardView9483` owns the points formatting, the
/// per-side rounding and the axis. This view adds no formatter, rounding rule,
/// clock, publisher or retained state, and never reads `projectedNow`.
///
/// It draws only a finished card with an admitted final (`applies`). Anything
/// else draws nothing, so the host keeps its existing renderer as the
/// fallback; no earlier pair is ever made up here.
///
/// Mount (Native, later): in `NFLEventCardView9483`'s `.finish` case, draw this
/// when `applies(finish)` and `NFLFinishCardView9483` otherwise.
struct NFLFinalComparisonPresentation9483: View {
    let card: NFLFinishCard9483
    let awayName: String
    let homeName: String
    let awayColor: Color
    let homeColor: Color
    var expanded = false
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var trackHeight: CGFloat = 76
    @ScaledMetric(relativeTo: .body) private var panelWidth: CGFloat = 285
    @ScaledMetric(relativeTo: .caption2) private var scaledAxisFont: CGFloat = 12

    /// One team's two numbers. The plot positions are the served values,
    /// unrounded; the printed text comes from the existing helpers.
    nonisolated struct Side: Equatable, Identifiable {
        let isHome: Bool
        let name: String
        let final: Double
        let earlier: Double
        var id: Bool { isHome }
    }

    /// The final's label: the word the existing card prints for it.
    static let finalLabel = "Final"

    /// A finished card with an admitted final. Phase and final are read as the
    /// card holds them; nothing is resolved again.
    static func applies(_ card: NFLFinishCard9483) -> Bool {
        card.phase == .after && card.final != nil
    }

    /// Away first, then home — the existing card's order. Empty unless `applies`.
    static func sides(_ card: NFLFinishCard9483, awayName: String, homeName: String) -> [Side] {
        guard applies(card), let final = card.final else { return [] }
        return [Side(isHome: false, name: awayName, final: final.away, earlier: card.pregame.away),
                Side(isHome: true, name: homeName, final: final.home, earlier: card.pregame.home)]
    }

    /// A final score is whole (`NFLFinishCardView9483.points`).
    static func finalText(_ side: Side) -> String {
        NFLFinishCardView9483.points(side.final)
    }

    /// The forecast as the headline prints it: whole per side on the qualified
    /// scheduled-start pair, its half point on the history point.
    static func earlierText(_ card: NFLFinishCard9483, _ side: Side) -> String {
        NFLFinishCardView9483.pregameText(side.earlier, whole: card.printsPregameWhole)
    }

    /// The one points axis both teams share: the existing card's domain over
    /// all four values.
    static func domain(_ card: NFLFinishCard9483) -> ClosedRange<Double> {
        let final = card.final.map { [$0.away, $0.home] } ?? []
        return NFLFinishCardView9483.pointDomain([card.pregame.away, card.pregame.home] + final,
                                                 step: card.tickStep)
    }

    /// One labelled tick per gridline step (a touchdown in football).
    static func ticks(_ card: NFLFinishCard9483) -> [Double] {
        let range = domain(card)
        return Array(stride(from: range.lowerBound, through: range.upperBound, by: card.tickStep))
    }

    /// What VoiceOver says for one team: its name, its final, and the
    /// forecast under its own basis, in the numbers the card prints.
    static func spoken(_ card: NFLFinishCard9483, _ side: Side) -> String {
        "\(side.name). \(finalLabel) \(finalText(side)). \(card.pregameName) \(earlierText(card, side))."
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
            // Two panels where both fit whole; stacked on a phone and always at
            // the largest text sizes.
            if typeSize >= .xxxLarge {
                stacked
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 28) {
                        ForEach(teamSides) { side in panel(side).frame(minWidth: panelWidth) }
                    }
                    .fixedSize(horizontal: true, vertical: false)
                    stacked
                }
            }
            // The marks are explained in the labels above each number; the key
            // repeats them in the card's own words for a sighted reader.
            Text(card.key)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityHidden(true)
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
            // The full name wraps between words; it is never shrunk or cut.
            Text(side.name)
                .font(.headline)
                .foregroundStyle(color(side))
                .fixedSize(horizontal: false, vertical: true)
            if typeSize >= .xxxLarge {
                VStack(alignment: .leading, spacing: 12) { figures(side) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 24) { figures(side) }
                        .fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 12) { figures(side) }
                }
            }
            track(side)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.spoken(card, side))
    }

    @ViewBuilder private func figures(_ side: Side) -> some View {
        figure(Self.finalLabel, text: Self.finalText(side)) { finalMark(color(side)) }
        figure(card.pregameName, text: Self.earlierText(card, side)) { earlierMark(color(side)) }
    }

    private func figure<Mark: View>(_ label: String, text: String, @ViewBuilder mark: () -> Mark) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                mark()
                    .accessibilityHidden(true)
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(text)
                .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The final: a cross, as on the existing card. Drawn over the forecast's
    /// outline, inside it, so a final equal to its forecast shows both.
    private func finalMark(_ color: Color) -> some View {
        NFLFinalCrossMark9483()
            .stroke(color, style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            .frame(width: 9, height: 9)
    }

    /// The forecast: an outline, as on the existing card, a little larger than
    /// the cross so its edge stays visible around a coincident final.
    private func earlierMark(_ color: Color) -> some View {
        Rectangle()
            .fill(.background)
            .overlay(Rectangle().stroke(color, lineWidth: 2))
            .frame(width: 13, height: 13)
    }

    /// One team's points track on the shared axis. The thin rule between the
    /// two marks compares two quantities; it is not a scoring timeline.
    private func track(_ side: Side) -> some View {
        let tint = color(side)
        let domain = axisDomain
        let ticks = axisTicks
        return Chart {
            RuleMark(xStart: .value("Points", domain.lowerBound), xEnd: .value("Points", domain.upperBound),
                     y: .value("Position", 1))
                .foregroundStyle(Color.secondary.opacity(0.2))
            if side.final != side.earlier {
                RuleMark(xStart: .value("Points", min(side.final, side.earlier)),
                         xEnd: .value("Points", max(side.final, side.earlier)),
                         y: .value("Position", 1))
                    .foregroundStyle(tint.opacity(0.4))
                    .lineStyle(StrokeStyle(lineWidth: 2))
            }
            PointMark(x: .value("Points", side.earlier), y: .value("Position", 1))
                .symbol { earlierMark(tint) }
            PointMark(x: .value("Points", side.final), y: .value("Position", 1))
                .symbol { finalMark(tint) }
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
        .frame(height: expanded ? trackHeight * 1.25 : trackHeight)
        .accessibilityHidden(true)
    }
}

/// The final's cross, the same shape in the label key and on the track.
struct NFLFinalCrossMark9483: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
        path.move(to: CGPoint(x: rect.minX, y: rect.midY))
        path.addLine(to: CGPoint(x: rect.maxX, y: rect.midY))
        return path
    }
}
