import SwiftUI

/// #11284 — the home-run card's paired comparison (design ref #10868,
/// `native-baseball-paired-home-runs`): each player's full name, then their
/// pregame chance of a home run beside their official final count at the same
/// size, then the chance on one probability rail the whole card shares.
///
/// Stateless, and only a drawing of `MLBHomeRunCard11284`. The card's builder
/// owns which players appear, their order, their saved chances, their official
/// finals and the shared ceiling; this view never reranks, joins, infers a
/// count or reformats a chance (`formatProbability` owns the printed number,
/// so the reference's one-decimal labels are not reproduced here).
///
/// The rail encodes probability alone. Its domain is `0...card.scaleCeiling`
/// for every row, and a final count never becomes one of its coordinates.
///
/// With no `onDetails` the rows are compact and inert (the deck). With one,
/// each whole row is a single details button that hands back the entry's
/// original ID unchanged (the reader); the host keeps routing and focus.
struct MLBHomeRunComparison11284: View {
    let card: MLBHomeRunCard11284
    let awayColor: Color
    let homeColor: Color
    /// Receives `entry.original.id`. Nil draws no button and no chevron.
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var size
    /// Both figures of a pair share one scaled size, so neither reads as the
    /// footnote of the other.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = Self.figurePointSize
    /// The narrowest a column may be before the pair stacks.
    @ScaledMetric(relativeTo: .body) private var columnMinimum: CGFloat = 112

    /// The figures' size at the default text size (Design: at least 26pt).
    static let figurePointSize: CGFloat = 28
    /// A details row is never a smaller target than this.
    static let minimumRowHeight: CGFloat = 44
    static let kicker = "Home runs · chance of at least one"
    static let pregameLabel = "Pregame · 1+ HR"
    static let finalLabel = "Final"
    static let unavailableText = "Unavailable"
    static let detailsHintText = "Shows this prop's exact original"

    var isInteractive: Bool { onDetails != nil }
    var detailsHint: String? { isInteractive ? Self.detailsHintText : nil }

    func details(_ row: Row) {
        onDetails?(row.detailsID)
    }

    var body: some View {
        let rows = Self.rows(card)
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 10) {
                MLBStoryHeading11284(kicker: Self.kicker, title: card.headline, reason: card.reason)
                ForEach(Array(rows.enumerated()), id: \.element.id) { index, row in
                    if index > 0 { Divider() }
                    entry(row)
                }
                scaleKey
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder private func entry(_ row: Row) -> some View {
        let color = PlayerPropsTeam.color(for: row.side, home: homeColor, away: awayColor)
        if isInteractive {
            Button { details(row) } label: { content(row, color: color) }
                .buttonStyle(.plain)
                .accessibilityLabel(row.spoken)
                .accessibilityHint(detailsHint ?? "")
        } else {
            content(row, color: color)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(row.spoken)
        }
    }

    private func content(_ row: Row, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline, spacing: 12) {
                Text(row.player)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if isInteractive {
                    Image(systemName: "chevron.right")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .accessibilityHidden(true)
                }
            }
            figures(row, color: color)
            rail(row, color: color)
        }
        .frame(maxWidth: .infinity, minHeight: Self.minimumRowHeight, alignment: .leading)
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    /// Side by side in equal columns at ordinary sizes, so the figures line up
    /// from row to row; stacked at accessibility sizes or when the width runs
    /// out, so numbers keep their size instead of shrinking or clipping.
    @ViewBuilder private func figures(_ row: Row, color: Color) -> some View {
        if Self.stacks(at: size) {
            stacked(row, color: color)
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) {
                    pregameColumn(row, color: color)
                        .frame(minWidth: columnMinimum, maxWidth: .infinity, alignment: .leading)
                    finalColumn(row)
                        .frame(minWidth: columnMinimum, maxWidth: .infinity, alignment: .leading)
                }
                stacked(row, color: color)
            }
        }
    }

    private func stacked(_ row: Row, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            pregameColumn(row, color: color)
            finalColumn(row)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func pregameColumn(_ row: Row, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Self.marker(row.glyph, color: .secondary, side: 8)
                Text(Self.pregameLabel)
            }
            .font(.subheadline)
            .foregroundStyle(.secondary)
            Text(row.pregameText)
                .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                .foregroundStyle(color)
                .lineLimit(1)
                .fixedSize()
        }
    }

    private func finalColumn(_ row: Row) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(Self.finalLabel)
                .font(.subheadline)
                .foregroundStyle(.secondary)
            if let figure = row.finalFigureText {
                Text(figure)
                    .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                    .fixedSize()
            } else {
                // Legible words, not a figure-sized word posing as a number.
                Text(Self.unavailableText)
                    .font(.headline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// A muted full rail, the chance as a coloured segment from zero, and a
    /// hollow mark where the chance sits on the card's shared scale.
    private func rail(_ row: Row, color: Color) -> some View {
        GeometryReader { geometry in
            let inset: CGFloat = 6
            let width = max(0, geometry.size.width - inset * 2)
            let y = geometry.size.height / 2
            Capsule()
                .fill(Color.secondary.opacity(0.2))
                .frame(width: width, height: 3)
                .position(x: inset + width / 2, y: y)
            if let fraction = row.railFraction {
                let filled = width * fraction
                Capsule()
                    .fill(color)
                    .frame(width: filled, height: 3)
                    .position(x: inset + filled / 2, y: y)
                Self.marker(row.glyph, color: color, side: 12)
                    .position(x: inset + filled, y: y)
            }
        }
        .frame(height: 22)
        .accessibilityHidden(true)
    }

    /// The shared scale's two ends and the key, said once for the card.
    private var scaleKey: some View {
        let ends = Self.axisLabels(ceiling: card.scaleCeiling)
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(ends.lower)
                Spacer(minLength: 12)
                Text(ends.upper)
            }
            .font(.caption2.monospacedDigit())
            HStack(spacing: 6) {
                Self.marker(.circle, color: .secondary, side: 10)
                Text("Hollow marks: pregame chance · shared scale")
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Self.scaleSpoken(ceiling: card.scaleCeiling))
    }

    @ViewBuilder static func marker(_ glyph: Glyph, color: Color, side: CGFloat) -> some View {
        switch glyph {
        case .circle:
            Circle()
                .fill(Color.cardBackground)
                .overlay(Circle().strokeBorder(color, lineWidth: 2))
                .frame(width: side, height: side)
        case .diamond:
            Rectangle()
                .fill(Color.cardBackground)
                .overlay(Rectangle().strokeBorder(color, lineWidth: 2))
                .frame(width: side * 0.75, height: side * 0.75)
                .rotationEffect(.degrees(45))
                .frame(width: side, height: side)
        }
    }

    static func stacks(at size: DynamicTypeSize) -> Bool { size.isAccessibilitySize }
}

// MARK: - What each row says

extension MLBHomeRunComparison11284 {
    /// The hollow mark's shape. A player's shape follows their original ID,
    /// so it never changes with row order or between launches.
    enum Glyph: Equatable { case circle, diamond }

    /// One entry as words and one rail coordinate, decided once from the card.
    struct Row: Equatable, Identifiable {
        let id: String
        /// `entry.original.id`, handed to `onDetails` unchanged.
        let detailsID: String
        let player: String
        let side: PlayerPropsTeam.Side
        let pregameText: String
        /// The chance over the card's ceiling at full precision, or nil when
        /// it cannot be placed. Never derived from the final count.
        let railFraction: Double?
        let glyph: Glyph
        /// "2 HR", or nil when the official final is unavailable (never "0 HR").
        let finalFigureText: String?
        let finalSpoken: String
        let spoken: String
    }

    /// The card's entries in the card's order, one row each; an empty card
    /// draws none.
    static func rows(_ card: MLBHomeRunCard11284) -> [Row] {
        card.entries.map { row($0, ceiling: card.scaleCeiling) }
    }

    static func row(_ entry: MLBHomeRunCard11284.Entry, ceiling: Double) -> Row {
        let pregame = formatProbability(entry.saved)
        let finalSpoken = entry.finalCount.map { "Official final, \($0) home \($0 == 1 ? "run" : "runs")" }
            ?? "Official final unavailable"
        return Row(
            id: entry.id,
            detailsID: entry.original.id,
            player: entry.player,
            side: entry.side,
            pregameText: pregame,
            railFraction: railFraction(entry.saved, ceiling: ceiling),
            glyph: glyph(for: entry.original.id),
            finalFigureText: entry.finalCount.map { "\($0) HR" },
            finalSpoken: finalSpoken,
            spoken: "\(entry.player). Pregame chance of at least one home run, \(pregame). \(finalSpoken).")
    }

    static func railFraction(_ chance: Double, ceiling: Double) -> Double? {
        guard chance.isFinite, ceiling.isFinite, ceiling > 0 else { return nil }
        return min(1, max(0, chance / ceiling))
    }

    /// A fixed function of the ID's bytes — not `hashValue`, which is seeded
    /// per launch.
    static func glyph(for originalID: String) -> Glyph {
        originalID.utf8.reduce(0) { $0 &+ Int($1) } % 2 == 0 ? .circle : .diamond
    }

    /// The rail's two ends: zero and the card's ceiling (a whole percent —
    /// 25%, or the next 5% above the largest chance).
    static func axisLabels(ceiling: Double) -> (lower: String, upper: String) {
        ("0%", "\(Int((ceiling * 100).rounded()))%")
    }

    static func scaleSpoken(ceiling: Double) -> String {
        let ends = axisLabels(ceiling: ceiling)
        return "Hollow marks show each pregame chance on one shared scale from \(ends.lower) to \(ends.upper)"
    }
}
