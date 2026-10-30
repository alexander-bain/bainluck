import SwiftUI

/// #9483 tennis — the reading panel's two dated pairs as one comparison per
/// player: the reading before the scheduled start and the selected recorded
/// chance at the same weight, each beside its own mark (hollow before, filled
/// recorded), and both on one 0–100% track.
///
/// Design's 2026-10-26 refinement (`live-tennis-reader-comparison-20261026`)
/// gave the earlier figure the recorded figure's 18pt bold; the panel prints
/// it at `.subheadline` under a `.title3` reading. Only the presentation is
/// new. Which pairs appear, and that "Show latest" follows them, is
/// `TennisChartReading9483.panelParts`; every printed number is
/// `labels(for:)`, every mark `home` / `awayValue(for:)`, every heading
/// `heading` / `baselineHeading` / `time`. The host keeps the pin, the scrub
/// and the series, and says whether "Show latest" is offered.
///
/// The track compares two probabilities; it is not a history. Nothing joins
/// the two marks, so no path is drawn across observations the chart has none
/// between.
///
/// Source-prepared only: `TennisReadingPanel9483` still draws the panel, and
/// this view is not mounted, compiled or rendered.
struct TennisProbabilityComparisonPresentation9483: View {
    let shown: TennisChartReading9483.Shown
    /// The series' admitted baseline, as the host reads it (`series.baseline`).
    let baseline: TennisChartReading9483.Reading?
    let scheduledStart: Date?
    let homeName: String
    let awayName: String
    let colors: (away: Color, home: Color)?
    let expanded: Bool
    /// Whether "Show latest" is offered, decided where the pin lives.
    let offersLatest: Bool
    /// The host's explicit choice of the newest observation (`pin.holdLatest(in:)`).
    let onShowLatest: () -> Void

    @Environment(\.dynamicTypeSize) private var textSize
    /// One type for both figures of every player, so neither reads as a
    /// footnote to the other. (Not private: a defaulted private `var` would
    /// make the memberwise init private, and the host builds this view.)
    @ScaledMetric(relativeTo: .callout) var figureSize: CGFloat = 18
    @ScaledMetric(relativeTo: .title3) var expandedFigureSize: CGFloat = 20
    /// Below this each, the two players stack.
    @ScaledMetric(relativeTo: .callout) var panelMinWidth: CGFloat = 150

    var body: some View {
        let model = Self.model(shown: shown, baseline: baseline, scheduledStart: scheduledStart,
                               homeName: homeName, awayName: awayName, offersLatest: offersLatest)
        VStack(alignment: .leading, spacing: expanded ? 8 : 6) {
            key(model)
            if !model.sides.isEmpty { players(model.sides) }
            if model.showsLatest {
                Button(TennisChartReading9483.showLatestText, action: onShowLatest)
                    .font(.caption)
                    .frame(minHeight: 44, alignment: .leading)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - What it shows

    enum Phase: Hashable {
        /// The baseline: the last observation before the scheduled start.
        case earlier
        /// The shown reading: held, scrubbed, or the latest.
        case recorded
    }

    /// One line of the key: a dated heading beside its mark, or a status
    /// (a break, an unavailable reading) that prints no values and has none.
    struct Line: Equatable {
        let phase: Phase?
        let text: String
    }

    struct Figure: Equatable {
        let phase: Phase
        /// Exactly what `labels(for:)` prints for this side.
        let printed: String
        /// `home`, or `awayValue(for:)`; nil draws no mark.
        let position: Double?
    }

    struct Side: Equatable {
        let isHome: Bool
        let name: String
        /// Earlier before recorded. A phase this side prints nothing for is
        /// absent, never filled from the other side.
        let figures: [Figure]
        /// The name, each dated heading with this side's figure under it (or
        /// "unavailable"), and the status if there is one.
        let spoken: String
    }

    struct Model: Equatable {
        let lines: [Line]
        /// Empty where `panelParts` prints no values.
        let sides: [Side]
        let showsLatest: Bool
    }

    /// The `now`, zone and locale the dating helpers take. Nil, as the view
    /// passes it, leaves them their own defaults: no clock is added here.
    struct Dating {
        let now: Date
        let timeZone: TimeZone
        let locale: Locale
    }

    static func model(shown: TennisChartReading9483.Shown, baseline: TennisChartReading9483.Reading?,
                      scheduledStart: Date?, homeName: String, awayName: String, offersLatest: Bool,
                      dating: Dating? = nil) -> Model {
        var earlier: TennisChartReading9483.Reading?
        var recorded: TennisChartReading9483.Reading?
        var status: String?
        var printsValues = false
        var showsLatest = false
        for part in TennisChartReading9483.panelParts(shown: shown, baseline: baseline, offersLatest: offersLatest) {
            switch part {
            case .names: printsValues = true
            case .shown(.reading(let reading, _)): recorded = reading
            case .shown(.gap(let date)): status = "No recorded chance at \(printedTime(date, dating))"
            case .shown(.unavailable): status = TennisChartReading9483.unavailableText
            case .baseline(let reading): earlier = reading
            case .showLatest: showsLatest = true
            }
        }

        var dated: [(phase: Phase, reading: TennisChartReading9483.Reading, heading: String)] = []
        if let earlier { dated.append((.earlier, earlier, baselineHeading(earlier, dating))) }
        if let recorded { dated.append((.recorded, recorded, recordedHeading(recorded, scheduledStart, dating))) }
        var lines = dated.map { Line(phase: $0.phase, text: $0.heading) }
        if let status { lines.append(Line(phase: nil, text: status)) }

        func side(isHome: Bool, name: String) -> Side {
            var figures: [Figure] = []
            var spoken: [String] = []
            for entry in dated {
                let printed = TennisChartReading9483.labels(for: entry.reading)
                let text = isHome ? printed.home : printed.away
                if text.isEmpty {
                    spoken.append("\(entry.heading), unavailable")
                    continue
                }
                figures.append(Figure(phase: entry.phase, printed: text,
                                      position: isHome ? entry.reading.home
                                                       : TennisChartReading9483.awayValue(for: entry.reading)))
                spoken.append("\(entry.heading), \(text)")
            }
            if let status { spoken.append(status) }
            return Side(isHome: isHome, name: name, figures: figures,
                        spoken: "\(name): " + spoken.joined(separator: "; "))
        }

        let sides = printsValues ? [side(isHome: true, name: homeName), side(isHome: false, name: awayName)] : []
        return Model(lines: lines, sides: sides, showsLatest: showsLatest)
    }

    private static func recordedHeading(_ reading: TennisChartReading9483.Reading, _ scheduledStart: Date?,
                                        _ dating: Dating?) -> String {
        guard let dating else { return TennisChartReading9483.heading(for: reading, scheduledStart: scheduledStart) }
        return TennisChartReading9483.heading(for: reading, scheduledStart: scheduledStart, now: dating.now,
                                              timeZone: dating.timeZone, locale: dating.locale)
    }

    private static func baselineHeading(_ reading: TennisChartReading9483.Reading, _ dating: Dating?) -> String {
        guard let dating else { return TennisChartReading9483.baselineHeading(for: reading) }
        return TennisChartReading9483.baselineHeading(for: reading, now: dating.now,
                                                      timeZone: dating.timeZone, locale: dating.locale)
    }

    private static func printedTime(_ date: Date, _ dating: Dating?) -> String {
        guard let dating else { return TennisChartReading9483.time(date) }
        return TennisChartReading9483.time(date, now: dating.now, timeZone: dating.timeZone, locale: dating.locale)
    }

    // MARK: - Marks

    /// The earlier reading's ring is wider than the recorded dot plus both
    /// strokes, so an equal pair reads as a dot inside a ring, never one mark.
    static let ringDiameter: CGFloat = 11
    static let ringLine: CGFloat = 1.5
    static let dotDiameter: CGFloat = 7

    /// Where a probability sits on a track `width` wide: 0 and 1 at the rail's
    /// ends, inset half a ring so neither end mark is clipped. Drawing only;
    /// the printed figure is `labels(for:)`'s, untouched.
    static func markX(_ probability: Double, width: CGFloat) -> CGFloat {
        let rail = max(0, width - ringDiameter)
        return ringDiameter / 2 + rail * CGFloat(min(max(probability, 0), 1))
    }

    @ViewBuilder
    private func mark(_ phase: Phase, color: Color) -> some View {
        switch phase {
        case .earlier:
            Circle()
                .fill(.background)
                .overlay(Circle().strokeBorder(color, lineWidth: Self.ringLine))
                .frame(width: Self.ringDiameter, height: Self.ringDiameter)
                .accessibilityHidden(true)
        case .recorded:
            Circle()
                .fill(color)
                .frame(width: Self.dotDiameter, height: Self.dotDiameter)
                .frame(width: Self.ringDiameter, height: Self.ringDiameter)
                .accessibilityHidden(true)
        }
    }

    // MARK: - Layout

    /// The dated headings once, each beside the mark its figures carry below.
    private func key(_ model: Model) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(Array(model.lines.enumerated()), id: \.offset) { _, line in
                if let phase = line.phase {
                    HStack(alignment: .center, spacing: 6) {
                        mark(phase, color: .secondary)
                        Text(line.text)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                } else {
                    Text(line.text)
                        .font(.subheadline)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        // Each player's own line speaks these headings with its figures.
        .accessibilityHidden(!model.sides.isEmpty)
    }

    /// Two panels side by side where both fit, stacked otherwise and always
    /// at accessibility sizes. No fixed height: the host's scroll carries it.
    @ViewBuilder
    private func players(_ sides: [Side]) -> some View {
        if textSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 10) { panels(sides, minWidth: nil) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) { panels(sides, minWidth: panelMinWidth) }
                VStack(alignment: .leading, spacing: 10) { panels(sides, minWidth: nil) }
            }
        }
    }

    private func panels(_ sides: [Side], minWidth: CGFloat?) -> some View {
        ForEach(sides, id: \.isHome) { side in
            panel(side)
                .frame(minWidth: minWidth, maxWidth: .infinity, alignment: .leading)
        }
    }

    private func color(_ side: Side) -> Color {
        side.isHome ? (colors?.home ?? .blue) : (colors?.away ?? .red)
    }

    /// The full name, the side's figures (side by side where they fit), and
    /// its track. A side with nothing printed keeps its name and no track.
    private func panel(_ side: Side) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(side.name)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.primary)
                .fixedSize(horizontal: false, vertical: true)
            if !side.figures.isEmpty {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .firstTextBaseline, spacing: 12) { figures(side) }
                        .fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 4) { figures(side) }
                }
                track(side)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(side.spoken)
    }

    private func figures(_ side: Side) -> some View {
        ForEach(side.figures, id: \.phase) { figure in
            HStack(alignment: .center, spacing: 4) {
                mark(figure.phase, color: color(side))
                Text(figure.printed)
                    .font(.system(size: expanded ? expandedFigureSize : figureSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(color(side))
            }
        }
    }

    /// One 0–100% rail, the same for both players, with the side's marks in
    /// figure order: the earlier ring first, so an equal recorded dot sits
    /// inside it.
    private func track(_ side: Side) -> some View {
        GeometryReader { geo in
            let mid = geo.size.height / 2
            ZStack {
                Capsule()
                    .fill(.quaternary)
                    .frame(width: max(0, geo.size.width - Self.ringDiameter), height: 2)
                    .position(x: geo.size.width / 2, y: mid)
                ForEach(side.figures, id: \.phase) { figure in
                    if let position = figure.position {
                        mark(figure.phase, color: color(side))
                            .position(x: Self.markX(position, width: geo.size.width), y: mid)
                    }
                }
            }
        }
        .frame(height: Self.ringDiameter + 4)
        .accessibilityHidden(true)
    }
}
