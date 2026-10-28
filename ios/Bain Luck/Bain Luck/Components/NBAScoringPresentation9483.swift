import SwiftUI

/// Presentation only: the production card owns identity, admission and expiry.
/// No fallback to Detail.quoted, no inferred baseline and no local clock policy.
struct NBAScoringChanceComparison9483: View {
    let point: NBALadderCard9483.Point?
    let tint: Color
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 28

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let point {
                // Names the prop these chances describe — the one place the
                // selected line is printed during play.
                Text("\(Text("Selected line · ").font(.subheadline).foregroundStyle(.secondary))\(Text(point.label).font(.headline))")
                    .fixedSize(horizontal: false, vertical: true)
                if typeSize >= .xxxLarge {
                    VStack(alignment: .leading, spacing: 16) { readings(point) }
                } else {
                    HStack(alignment: .top, spacing: 20) { readings(point) }
                }
            } else {
                Text("Selected market unavailable")
                    .font(.headline)
                Text("Your selection is saved. No probability is available for it in this update.")
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(point == nil ? Self.accessibilitySummary(for: point)
                            : "Selected line. " + Self.accessibilitySummary(for: point))
    }

    @ViewBuilder private func readings(_ point: NBALadderCard9483.Point) -> some View {
        reading("Pregame chance", symbol: "circle", value: point.chance)
        reading("Current chance", symbol: "circle.fill", value: point.now)
    }

    private func reading(_ label: String, symbol: String, value: Double?) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Label(label, systemImage: symbol)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            if let value {
                Text(formatProbability(value))
                    .font(.system(size: chanceSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(tint)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Unavailable")
                    .font(.body.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Shared spoken copy for the selected comparison and the chart's marks.
    /// Uses the existing probability formatter; this does not admit values.
    static func accessibilitySummary(for point: NBALadderCard9483.Point?) -> String {
        guard let point else {
            return "Selected market unavailable. Your selection is saved. No probability is available for it in this update."
        }
        let before = point.chance.map { formatProbability($0) } ?? "Unavailable"
        let current = point.now.map { formatProbability($0) } ?? "Unavailable"
        return "\(point.label). Pregame chance: \(before). Current chance: \(current)."
    }
}

/// The actual and the pregame projection as one comparison, each keyed to its
/// chart mark (solid = actual, dashed = pregame projection). The projection is
/// the pregame value only — never a current projection. A missing value is not
/// drawn and not filled.
struct NBAScoringFigures9483: View {
    let card: NBALadderCard9483
    let awayColor: Color
    let homeColor: Color
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28

    /// The chart draws its actual and projection rules with these, so the key
    /// can never disagree with the marks.
    static let actualStroke = StrokeStyle(lineWidth: 2)
    static let forecastStroke = StrokeStyle(lineWidth: 1.5, dash: [4, 3])

    var body: some View {
        Group {
            // Two equal columns at ordinary sizes; the unit or side wraps
            // inside its own column rather than pushing the pair into rows.
            // From XXXL, as the chance pair below, a ~120pt column on a 375
            // deck card could split "projection" mid-word, so they stack.
            if typeSize >= .xxxLarge {
                VStack(alignment: .leading, spacing: 12) { figures }
            } else {
                HStack(alignment: .top, spacing: 16) { figures }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.accessibilitySummary(for: card))
    }

    @ViewBuilder private var figures: some View {
        if let actual = card.actual {
            figure(Self.actualLabel(card.phase), value: actual, stroke: Self.actualStroke, key: .primary)
        }
        if let forecast = card.forecast {
            figure("Pregame projection", value: forecast, stroke: Self.forecastStroke, key: .secondary)
        }
    }

    private func figure(_ label: String, value: Double, stroke: StrokeStyle, key: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 6) {
                NBAStatMarkKey9483()
                    .stroke(key, style: stroke)
                    .frame(width: 6, height: 14)
                    .accessibilityHidden(true)
                Text(label)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            figureText(value)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// One text, so the side ("Knicks by") and unit ("points") stay with
    /// their number and wrap at a space when the column is narrow.
    private func figureText(_ value: Double) -> Text {
        let parts = Self.parts(card, value)
        let lead = Text(parts.lead.isEmpty ? "" : parts.lead + " ")
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(tint(value))
        let figure = Text(parts.figure)
            .font(.system(size: figureSize, weight: .bold).monospacedDigit())
            .foregroundStyle(tint(value))
        let unit = Text(parts.unit.isEmpty ? "" : " " + parts.unit)
            .font(.subheadline)
            .foregroundStyle(.secondary)
        return Text("\(lead)\(figure)\(unit)")
    }

    /// A margin is coloured by the side it favours; a tie and a total stay neutral.
    private func tint(_ value: Double) -> Color {
        guard card.family == .margin, value != 0 else { return .primary }
        return value > 0 ? homeColor : awayColor
    }

    static func actualLabel(_ phase: NBALadderCard9483.Phase) -> String {
        phase == .after ? "Actual final" : "Actual so far"
    }

    static func text(_ card: NBALadderCard9483, _ value: Double) -> String {
        card.words(value) + (card.family == .margin ? "" : " points")
    }

    /// `text` split for display: the side or unit as supporting words around
    /// the large number. Built from the card's own pieces (`number`, the side
    /// names, `words` for a tie), never by parsing `text`; joined with spaces
    /// it is `text` exactly.
    static func parts(_ card: NBALadderCard9483, _ value: Double) -> (lead: String, figure: String, unit: String) {
        guard card.family == .margin else { return ("", NBALadderCard9483.number(value), "points") }
        guard value != 0 else { return ("", card.words(value), "") }
        return ("\(value > 0 ? card.homeShort : card.awayShort) by", NBALadderCard9483.number(abs(value)), "")
    }

    static func accessibilitySummary(for card: NBALadderCard9483) -> String {
        var parts: [String] = []
        if let actual = card.actual { parts.append("\(actualLabel(card.phase)): \(text(card, actual)).") }
        if let forecast = card.forecast { parts.append("Pregame projection: \(text(card, forecast)).") }
        return parts.joined(separator: " ")
    }
}

/// A short vertical rule in the chart's own stroke: the figure's visual key.
struct NBAStatMarkKey9483: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: rect.midX, y: rect.minY))
        path.addLine(to: CGPoint(x: rect.midX, y: rect.maxY))
        return path
    }
}

/// Spoken names for the selected-line controls. They read the card's existing
/// selection only; a selection that is no longer served names no neighbour.
enum NBAScoringLineControls9483 {
    static func stepLabel(_ card: NBALadderCard9483, selected: Int?, by delta: Int) -> String {
        let name = delta < 0 ? "Previous line" : "Next line"
        guard let selected, card.points.indices.contains(selected + delta) else { return name }
        return "\(name): \(card.points[selected + delta].label)"
    }

    static func detailsLabel(_ point: NBALadderCard9483.Point?) -> String {
        guard let point else { return "Selected market unavailable" }
        return "Details and timing for \(point.label)"
    }
}
