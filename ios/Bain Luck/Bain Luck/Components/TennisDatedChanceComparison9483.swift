import SwiftUI

/// #9483 tennis — the inspected recorded chance and its separately dated
/// earlier one, both competitors, equally readable.
///
/// Design's comparison (2026-10-28, from the v462 reference's
/// Zverev–Shelton reader): both dated pairs print at one figure size, each
/// pair under a full-width line naming what it is and when it was recorded,
/// with a solid key for the inspected reading and a hollow one for the
/// earlier. The v462 reference's "In game" / "Last pre-match" wording stays
/// corrected to "Recorded chance" / "Before scheduled start": a stored start
/// is at best a scheduled one.
///
/// Presentation only. Every value, label, time and row decision comes from
/// `TennisChartReading9483` as it stands — `panelParts`, `separateBaseline`,
/// `heading`, `baselineHeading`, `time`, `labels(for:)` — over the `Shown`
/// and baseline its owner already resolved. Nothing here reads history,
/// chooses a source, takes a complement, rounds, or holds a reading.
enum TennisDatedChanceComparison9483 {
    /// No baseline exists: the earlier pair is absent, and nothing claims a
    /// pre-start reading was recorded.
    static let earlierUnavailableText = "Earlier comparison unavailable"
    /// A competitor's slot where `labels(for:)` printed nothing. Never "0%".
    static let unavailableFigure = "Unavailable"

    enum Key: Equatable {
        /// The inspected reading.
        case solid
        /// The earlier, separately dated reading.
        case hollow
    }

    /// One dated pair as printed. `reading` is the resolved reading itself, so
    /// its event, source and time travel with what is shown.
    struct Pair: Equatable {
        let key: Key
        let reading: TennisChartReading9483.Reading
        let heading: String
        /// `labels(for:)`'s strings; nil where it printed an empty one.
        let home: String?
        let away: String?
    }

    enum Part: Equatable {
        /// The two names, once, over both pairs' columns.
        case names
        case pair(Pair)
        /// A line in place of numbers: a break in the line, a held reading
        /// that is gone, or no earlier comparison.
        case note(String)
        case showLatest
    }

    /// The comparison top to bottom, in `panelParts`' order. "Show latest"
    /// is offered only when the owner offers it AND supplies the action.
    static func parts(shown: TennisChartReading9483.Shown, baseline: TennisChartReading9483.Reading?,
                      scheduledStart: Date?, offersLatest: Bool, canShowLatest: Bool,
                      now: Date = Date(), timeZone: TimeZone = .autoupdatingCurrent,
                      locale: Locale = .autoupdatingCurrent) -> [Part] {
        typealias R = TennisChartReading9483
        var parts: [Part] = []
        for part in R.panelParts(shown: shown, baseline: baseline, offersLatest: offersLatest && canShowLatest) {
            switch part {
            case .names:
                parts.append(.names)
            case .shown(.reading(let reading, _)):
                parts.append(.pair(pair(reading, key: .solid,
                                        heading: R.heading(for: reading, scheduledStart: scheduledStart, now: now,
                                                           timeZone: timeZone, locale: locale))))
            case .shown(.gap(let date)):
                parts.append(.note("No recorded chance at \(R.time(date, now: now, timeZone: timeZone, locale: locale))"))
            case .shown(.unavailable):
                parts.append(.note(R.unavailableText))
            case .baseline(let earlier):
                parts.append(.pair(pair(earlier, key: .hollow,
                                        heading: R.baselineHeading(for: earlier, now: now,
                                                                   timeZone: timeZone, locale: locale))))
            case .showLatest:
                parts.append(.showLatest)
            }
            if case .shown = part, baseline == nil {
                parts.append(.note(earlierUnavailableText))
            }
        }
        return parts
    }

    static func pair(_ reading: TennisChartReading9483.Reading, key: Key, heading: String) -> Pair {
        let printed = TennisChartReading9483.labels(for: reading)
        return Pair(key: key, reading: reading, heading: heading,
                    home: printed.home.isEmpty ? nil : printed.home,
                    away: printed.away.isEmpty ? nil : printed.away)
    }

    /// What a screen reader hears for one pair: its meaning and time, then
    /// each competitor by name with its own value.
    static func spoken(_ pair: Pair, homeName: String, awayName: String) -> String {
        [pair.heading, "\(homeName) \(pair.home ?? unavailableFigure)", "\(awayName) \(pair.away ?? unavailableFigure)"]
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .joined(separator: ", ")
    }
}

/// #9483 tennis — the dated comparison for `TennisReadingPanel9483` to show.
/// The owner resolves `shown`, supplies its series' baseline and scheduled
/// start, decides whether "Show latest" is offered and what it does. This
/// view holds nothing and observes nothing.
struct TennisDatedChanceComparisonView9483: View {
    let shown: TennisChartReading9483.Shown
    let baseline: TennisChartReading9483.Reading?
    let scheduledStart: Date?
    let homeName: String
    let awayName: String
    let homeColor: Color
    let awayColor: Color
    let offersLatest: Bool
    let onShowLatest: (() -> Void)?
    /// Formatting only (today prints a time, another day its date too).
    let now: Date

    @Environment(\.dynamicTypeSize) private var textSize
    /// Both pairs' figures, inspected and earlier alike.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 26

    init(shown: TennisChartReading9483.Shown, baseline: TennisChartReading9483.Reading?,
         scheduledStart: Date?, homeName: String, awayName: String, homeColor: Color, awayColor: Color,
         offersLatest: Bool = false, onShowLatest: (() -> Void)? = nil, now: Date = Date()) {
        self.shown = shown
        self.baseline = baseline
        self.scheduledStart = scheduledStart
        self.homeName = homeName
        self.awayName = awayName
        self.homeColor = homeColor
        self.awayColor = awayColor
        self.offersLatest = offersLatest
        self.onShowLatest = onShowLatest
        self.now = now
    }

    private var parts: [TennisDatedChanceComparison9483.Part] {
        TennisDatedChanceComparison9483.parts(shown: shown, baseline: baseline, scheduledStart: scheduledStart,
                                              offersLatest: offersLatest, canShowLatest: onShowLatest != nil,
                                              now: now)
    }

    var body: some View {
        if textSize.isAccessibilitySize {
            content(stacked: true)
        } else {
            // Two columns where both names and figures fit whole side by
            // side; otherwise each competitor's reading on its own lines.
            ViewThatFits(in: .horizontal) {
                content(stacked: false)
                content(stacked: true)
            }
        }
    }

    private func content(stacked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach(Array(parts.enumerated()), id: \.offset) { _, part in
                switch part {
                case .names:
                    if !stacked {
                        TennisEqualColumns9483(spacing: 12) {
                            name(homeName)
                            name(awayName)
                        }
                        .accessibilityHidden(true)
                    }
                case .pair(let pair):
                    self.pair(pair, stacked: stacked)
                case .note(let text):
                    line(Text(text)
                        .font(.subheadline)
                        .foregroundStyle(.secondary))
                case .showLatest:
                    if let onShowLatest {
                        Button(action: onShowLatest) {
                            line(Text(TennisChartReading9483.showLatestText).font(.subheadline))
                                .frame(minHeight: 44)
                                .contentShape(Rectangle())
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// One dated pair: its keyed line, then the two figures. Read as one
    /// element, so the hidden names and the figures are not read again.
    private func pair(_ pair: TennisDatedChanceComparison9483.Pair, stacked: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            line(HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: pair.key == .solid ? "circle.fill" : "circle")
                    .font(.caption2)
                Text(pair.heading)
                    .font(.subheadline)
            }
            .foregroundStyle(.secondary))
            if stacked {
                competitor(homeName, pair.home, homeColor)
                competitor(awayName, pair.away, awayColor)
            } else {
                TennisEqualColumns9483(spacing: 12) {
                    figure(pair.home, homeColor)
                    figure(pair.away, awayColor)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(TennisDatedChanceComparison9483.spoken(pair, homeName: homeName, awayName: awayName))
    }

    /// A full-width line that wraps instead of widening the comparison: it
    /// asks for no width of its own when the columns are measured.
    private func line(_ view: some View) -> some View {
        view
            .fixedSize(horizontal: false, vertical: true)
            .frame(minWidth: 0, idealWidth: 0, maxWidth: .infinity, alignment: .leading)
    }

    private func name(_ text: String) -> some View {
        Text(text)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(.primary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func figure(_ label: String?, _ color: Color) -> some View {
        if let label {
            Text(label)
                .font(.system(size: figureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(color)
                .fixedSize()
        } else {
            Text(TennisDatedChanceComparison9483.unavailableFigure)
                .font(.subheadline)
                .foregroundStyle(.secondary)
                .fixedSize()
        }
    }

    /// A competitor's whole reading on its own lines: name, then figure.
    private func competitor(_ name: String, _ label: String?, _ color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            self.name(name)
            figure(label, color)
        }
    }
}

/// #9483 tennis — two columns of equal width across the comparison, so every
/// row's home and away line up under the names. Measured, each column asks
/// for its widest child's whole width, so `ViewThatFits` stacks the panel
/// before a name or figure would have to squeeze. Children sit on one first
/// text baseline, whatever their type.
private struct TennisEqualColumns9483: Layout {
    var spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let gaps = spacing * CGFloat(max(subviews.count - 1, 0))
        let widest = subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0
        let width = proposal.width ?? widest * CGFloat(subviews.count) + gaps
        return CGSize(width: width, height: placements(width: width, subviews: subviews).height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let laid = placements(width: bounds.width, subviews: subviews)
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + CGFloat(index) * (laid.column + spacing),
                                      y: bounds.minY + laid.offsets[index]),
                          anchor: .topLeading,
                          proposal: ProposedViewSize(width: laid.column, height: nil))
        }
    }

    private func placements(width: CGFloat, subviews: Subviews) -> (column: CGFloat, offsets: [CGFloat], height: CGFloat) {
        guard !subviews.isEmpty else { return (0, [], 0) }
        let column = max(0, (width - spacing * CGFloat(subviews.count - 1)) / CGFloat(subviews.count))
        let dimensions = subviews.map { $0.dimensions(in: ProposedViewSize(width: column, height: nil)) }
        let ascent = dimensions.map { $0[VerticalAlignment.firstTextBaseline] }.max() ?? 0
        let offsets = dimensions.map { ascent - $0[VerticalAlignment.firstTextBaseline] }
        let height = zip(dimensions, offsets).map { $0.height + $1 }.max() ?? 0
        return (column, offsets, height)
    }
}
