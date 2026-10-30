import SwiftUI

/// #10238 — A SELECTED MARKET'S PREGAME AND LATER CHANCE AS TWO EQUAL FIGURES
/// ON ONE LABELLED PROBABILITY TRACK (design: the hollow-before / solid-later
/// track in `baseball-card-context-v247/browser/extra-innings-phone.png`; the
/// two-figure reading of `binary-side-comparison-20261026/live-phone.png`).
///
/// Two equally prominent percentages lead — a hollow-keyed "Pregame chance" and
/// a solid-keyed "Later chance" — then the served change in words ("Up 5.0
/// percentage points since pregame"), then a horizontal, zero-based probability
/// track that places both. Only the stretch between the two marks is
/// emphasised. It is not a time history, an arrow or a score marker.
///
/// PRESENTATION ONLY, of one already resolved `EventQuestionMatrixAdapter.Detail`
/// — the host resolved it for the exact `QuestionMatrixSelection` on its own
/// latest payload, so admission, same-event scope and aging are the owner's:
///
///   - BOTH CHANCES   `detail.comparison.baseline` / `.latest`, each with its own
///                    `observedAt`, as served. `comparison.latest` is NOT
///                    `detail.option.value`: the published number can carry a
///                    different basis (R5). With published 52%, latest 60% and
///                    baseline 40%, this prints 40% → 60% and 20, never 52 or 12.
///   - THE CHANGE     `comparison.points`, the server's percentage points. Its
///                    sign gives the direction word and `deltaPointsNumber` the
///                    magnitude; nothing is recomputed from either probability or
///                    from a printed percent. A non-zero move under 0.05 prints
///                    "<0.1", never "0.0" or "No change".
///   - PERCENTS       `formatProbability` (whole percents — the browser prints
///                    one decimal; that deviation is the shared formatter's, not
///                    reconciled here), behind the host's own exact-endpoint
///                    guard: a quoted 0 prints 0% and a quoted 1 prints 100%.
///   - THE TRACK      the raw comparison probabilities on the smallest of 0–25%,
///                    0–50% and 0–100% that holds both. The scale is chosen, the
///                    values are never clipped or normalised; a value no scale
///                    can hold draws no track rather than a fabricated position.
///   - TIMES          `SourceAge.preciseStamp` (the reader's local time) and
///                    `SourceAgeText` per chance, never one shared clock. An
///                    unreadable stamp prints "Time unavailable"; the other
///                    chance's time is never borrowed.
///   - NAMES          `detail.row.label`, `detail.row.period?.label` and
///                    `detail.option.label`, verbatim. No player, stat or side is
///                    parsed out of them.
///
/// No comparison, no track: `resolve` answers nil and the host keeps its
/// existing renderer. A raw contributor selection, a won/lost/refused/unpriced
/// value and a finished question without a served comparison never gain a track
/// or a terminal 0/100 journey. Nothing is retained between renders, so a
/// comparison that leaves the payload leaves the screen with it. The adapter
/// cannot yet carry a baseline-only or finished-actual comparison (it needs
/// `latest`); that is the owner contract's to add, not this view's to rebuild.
///
/// ACTION. When the host supplies `onDetails`, a 44-point "Details" control
/// hands it exactly `detail.option.selection`. Without one there is no control.
/// This view keeps no selection state and routes nothing itself.
///
/// Mount (Native, later — not done here): in
/// `EventQuestionMatrixSection10238.detail(_:)` or a card that holds the same
/// qualified Detail, in place of `comparisonSection(comparison)` when `resolve`
/// answers, keeping it as the fallback. Exactly one comparison renderer (this
/// track OR the dial) per detail.
struct MarketChanceMovementTrack10238: View {
    let detail: EventQuestionMatrixAdapter.Detail
    /// The hollow (earlier) mark, its key and its figure.
    let pregameColor: Color
    /// The solid (later) mark, the emphasised stretch, its key and its figure.
    let laterColor: Color
    /// False where the host already prints the market and outcome right above.
    /// VoiceOver hears them either way.
    let showsHeading: Bool
    /// Receives exactly `detail.option.selection`; nil means no control.
    let onDetails: ((QuestionMatrixSelection) -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: two 26-point figures, scaled with text size.
    @ScaledMetric(relativeTo: .title2) private var valueSize: CGFloat = 26
    @ScaledMetric(relativeTo: .headline) private var changeSize: CGFloat = 17

    init(
        detail: EventQuestionMatrixAdapter.Detail,
        pregameColor: Color,
        laterColor: Color,
        showsHeading: Bool = true,
        onDetails: ((QuestionMatrixSelection) -> Void)? = nil
    ) {
        self.detail = detail
        self.pregameColor = pregameColor
        self.laterColor = laterColor
        self.showsHeading = showsHeading
        self.onDetails = onDetails
    }

    static var accessibilityIdentifier: String { "market-chance-movement-track-10238" }

    // MARK: - What it prints

    /// One of the two chances.
    nonisolated struct Reading: Equatable {
        /// "Pregame chance" / "Later chance".
        let label: String
        /// The served probability, which places the mark.
        let probability: Double
        /// The printed percent.
        let text: String
        /// The served stamp, verbatim.
        let observedAt: String
        /// The reader's local time for that stamp; nil when it cannot be read.
        let localTime: String?

        static var timeUnavailableText: String { "Time unavailable" }
        var timeText: String { localTime ?? Self.timeUnavailableText }
        var spoken: String { "\(label) \(text), \(timeText)" }
    }

    nonisolated enum Direction: Equatable {
        case up
        case down
        case none
    }

    /// The served change, as words under the two figures.
    nonisolated struct Change: Equatable {
        let direction: Direction
        /// The unsigned magnitude ("5.0", "<0.1"); nil for no change.
        let magnitude: String?

        /// The bold lead: "Up 5.0", "Down <0.1", "No change".
        var lead: String {
            switch (direction, magnitude) {
            case (.up, let m?): return "Up \(m)"
            case (.down, let m?): return "Down \(m)"
            default: return "No change"
            }
        }

        /// What follows the lead, so "points" can only be read as chance.
        var trailing: String {
            direction == .none ? " since pregame" : " percentage points since pregame"
        }

        /// The whole line, as shown and as spoken.
        var text: String { lead + trailing }
    }

    nonisolated struct Resolved: Equatable {
        /// The market, verbatim.
        let title: String
        /// The served period label, when there is one.
        let period: String?
        /// The selected option's label, verbatim.
        let outcome: String
        /// The exact selection `onDetails` receives.
        let selection: QuestionMatrixSelection
        let pregame: Reading
        let later: Reading
        let change: Change
        /// Nil only when no scale holds both probabilities; the figures still
        /// print and no position is invented.
        let domain: TrackDomain?

        var readings: [Reading] { [pregame, later] }

        /// One VoiceOver stop: the market, the outcome, both named chances with
        /// their own times, then the change.
        var spokenSummary: String {
            ([title] + (period.map { [$0] } ?? []) + [outcome]
                + readings.map(\.spoken) + [change.text])
                .joined(separator: ". ")
        }
    }

    /// How the view arranges itself.
    nonisolated struct Arrangement: Equatable {
        /// The two figures stand one below the other, never side by side.
        let stacksReadings: Bool
        /// The track labels only its two ends, never shrinking a label.
        let compactAxis: Bool
    }

    static var pregameLabel: String { "Pregame chance" }
    static var laterLabel: String { "Later chance" }
    static var disclosureTitle: String { "About this comparison" }
    static var detailsTitle: String { "Details" }
    static var timeUnavailableText: String { Reading.timeUnavailableText }

    /// Accessibility sizes always stack (other sizes stack only when the two
    /// columns do not fit); from xxLarge the track labels only its ends.
    static func arrangement(typeSize: DynamicTypeSize) -> Arrangement {
        Arrangement(stacksReadings: typeSize.isAccessibilitySize,
                    compactAxis: typeSize >= .xxLarge)
    }

    /// The host's exact-endpoint guard (`EventQuestionMatrixSection10238.valueText`)
    /// in front of the shared formatter: an exact quoted endpoint stays a quote.
    static func chanceText(_ probability: Double) -> String {
        if probability == 0 { return "0%" }
        if probability == 1 { return "100%" }
        return formatProbability(probability)
    }

    /// The served points as direction and magnitude. A non-zero move the
    /// shared one-decimal rule would print as "0.0" prints "<0.1".
    static func change(points: Double) -> Change {
        guard points != 0 else { return Change(direction: .none, magnitude: nil) }
        let printed = deltaPointsNumber(points)
        let magnitude = printed == deltaPointsNumber(0) ? "<0.1" : printed
        return Change(direction: points > 0 ? .up : .down, magnitude: magnitude)
    }

    /// The track for this detail, or nil where it declines: no served
    /// comparison, so the host's existing renderer stays.
    static func resolve(_ detail: EventQuestionMatrixAdapter.Detail) -> Resolved? {
        guard let comparison = detail.comparison else { return nil }
        func reading(_ label: String, _ probability: Double, _ observedAt: String) -> Reading {
            Reading(label: label, probability: probability, text: chanceText(probability),
                    observedAt: observedAt, localTime: SourceAge.preciseStamp(observedAt))
        }
        let period = detail.row.period?.label.flatMap { $0.isEmpty ? nil : $0 }
        return Resolved(
            title: detail.row.label,
            period: period,
            outcome: detail.option.label,
            selection: detail.option.selection,
            pregame: reading(pregameLabel, comparison.baseline, comparison.baselineObservedAt),
            later: reading(laterLabel, comparison.latest, comparison.latestObservedAt),
            change: change(points: comparison.points),
            domain: TrackDomain.smallest(containing: comparison.baseline, comparison.latest)
        )
    }

    /// The Details control's spoken name: the action, the market, the outcome.
    static func detailsSpokenLabel(_ resolved: Resolved) -> String {
        "\(detailsTitle), \(resolved.title), \(resolved.outcome)"
    }

    /// Hands the owner exactly the resolved selection, when it asked for it.
    static func performDetails(_ resolved: Resolved, onDetails: ((QuestionMatrixSelection) -> Void)?) {
        onDetails?(resolved.selection)
    }

    // MARK: - The track's scale and geometry

    /// The zero-based scale: the smallest of 0–25%, 0–50% and 0–100% that holds
    /// BOTH raw probabilities. It picks a scale; it never moves a value.
    nonisolated enum TrackDomain: Equatable, CaseIterable {
        case quarter
        case half
        case whole

        /// The top of the scale, in whole percent.
        var upperPercent: Int {
            switch self {
            case .quarter: return 25
            case .half: return 50
            case .whole: return 100
            }
        }

        var upper: Double { Double(upperPercent) / 100 }

        /// Every tick, in whole percent: 0/5/…/25, 0/10/…/50, 0/20/…/100.
        var tickPercents: [Int] {
            let step = upperPercent / 5
            return Array(stride(from: 0, through: upperPercent, by: step))
        }

        /// A scale label. It describes the axis; it is not a quoted chance, so
        /// the endpoint guards of `chanceText` do not apply.
        static func tickLabel(_ percent: Int) -> String { "\(percent)%" }

        /// Nil when either value is not a finite probability in 0...1 — no scale
        /// is stretched or value pulled to zero to make it fit.
        static func smallest(containing values: Double...) -> TrackDomain? {
            guard values.allSatisfy({ $0.isFinite && (0...1).contains($0) }),
                  let top = values.max() else { return nil }
            return allCases.first { top <= $0.upper }
        }
    }

    nonisolated enum TrackGeometry {
        /// The track never grows past this.
        static let maxWidth: CGFloat = 360
        /// The plot's height, which holds the marks; labels sit below it.
        static let plotHeight: CGFloat = 24
        /// Keeps a mark at either end wholly inside the plot: the hollow ring
        /// is 14 points across, so 10 leaves room for its stroke.
        static let inset: CGFloat = 10
        static let pregameMarkDiameter: CGFloat = 14
        static let laterMarkDiameter: CGFloat = 8
        /// Under this plot width every tick label would crowd its neighbours.
        static let fullLabelMinimumWidth: CGFloat = 260

        /// A probability's horizontal place in a plot `width` points wide.
        static func x(_ probability: Double, domain: TrackDomain, width: CGFloat) -> CGFloat {
            inset + CGFloat(probability / domain.upper) * (width - 2 * inset)
        }

        /// The emphasised stretch between the two marks, left to right, or nil
        /// when they share one coordinate (nothing is invented between them).
        static func span(from earlier: Double, to later: Double, domain: TrackDomain,
                         width: CGFloat) -> ClosedRange<CGFloat>? {
            guard earlier != later else { return nil }
            let a = x(earlier, domain: domain, width: width)
            let b = x(later, domain: domain, width: width)
            return min(a, b)...max(a, b)
        }

        /// The ticks that carry a label. Narrow plots and large text keep the
        /// two ends, so the displayed range is always explicit.
        static func labelledTickPercents(_ domain: TrackDomain, width: CGFloat, compact: Bool) -> [Int] {
            guard compact || width < fullLabelMinimumWidth else { return domain.tickPercents }
            return [0, domain.upperPercent]
        }
    }

    private var resolved: Resolved? { Self.resolve(detail) }

    // MARK: - Body

    var body: some View {
        if let resolved {
            let arrangement = Self.arrangement(typeSize: typeSize)
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 12) {
                    if showsHeading {
                        heading(resolved)
                    }
                    readings(resolved, arrangement: arrangement)
                    changeLine(resolved.change)
                    if let domain = resolved.domain {
                        track(resolved, domain: domain, compact: arrangement.compactAxis)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(resolved.spokenSummary)
                .accessibilityIdentifier("\(Self.accessibilityIdentifier)-summary")
                if onDetails != nil {
                    detailsButton(resolved)
                }
                about(resolved)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(Self.accessibilityIdentifier)
        }
    }

    // MARK: - Pieces

    /// The market, its period and the selected option, verbatim. Read by
    /// VoiceOver inside the summary, so not a stop of its own.
    private func heading(_ resolved: Resolved) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(resolved.title)
                .font(.headline)
                .fixedSize(horizontal: false, vertical: true)
            if let period = resolved.period {
                Text(period)
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(resolved.outcome)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The two figures: side by side on one numeric baseline where they fit,
    /// otherwise each under its own label. Labels wrap; figures never shrink.
    @ViewBuilder
    private func readings(_ resolved: Resolved, arrangement: Arrangement) -> some View {
        if arrangement.stacksReadings {
            stackedReadings(resolved)
        } else {
            ViewThatFits(in: .horizontal) {
                columnReadings(resolved)
                stackedReadings(resolved)
            }
        }
    }

    private func columnReadings(_ resolved: Resolved) -> some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
            GridRow(alignment: .bottom) {
                key(resolved.pregame, hollow: true)
                key(resolved.later, hollow: false)
            }
            GridRow(alignment: .firstTextBaseline) {
                figure(resolved.pregame, color: pregameColor)
                figure(resolved.later, color: laterColor)
            }
            GridRow(alignment: .top) {
                age(resolved.pregame)
                age(resolved.later)
            }
        }
    }

    private func stackedReadings(_ resolved: Resolved) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            ForEach([true, false], id: \.self) { isPregame in
                let reading = isPregame ? resolved.pregame : resolved.later
                VStack(alignment: .leading, spacing: 4) {
                    key(reading, hollow: isPregame)
                    figure(reading, color: isPregame ? pregameColor : laterColor)
                    age(reading)
                }
            }
        }
    }

    /// The text key with its mark: hollow for pregame, solid for later. The
    /// words carry the meaning; the mark and colour only repeat it.
    private func key(_ reading: Reading, hollow: Bool) -> some View {
        let color = hollow ? pregameColor : laterColor
        return HStack(alignment: .firstTextBaseline, spacing: 6) {
            Group {
                if hollow {
                    Circle().strokeBorder(color, lineWidth: 2)
                } else {
                    Circle().fill(color)
                }
            }
            .frame(width: 10, height: 10)
            Text(reading.label)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(color)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// A figure, whole: never wrapped, split or scaled down.
    private func figure(_ reading: Reading, color: Color) -> some View {
        Text(reading.text)
            .font(.system(size: valueSize, weight: .bold).monospacedDigit())
            .foregroundStyle(color)
            .fixedSize()
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func age(_ reading: Reading) -> some View {
        SourceAgeText(observedAt: reading.observedAt)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// "Up 5.0 percentage points since pregame", wrapping only between words.
    private func changeLine(_ change: Change) -> some View {
        let lead = Text(change.lead)
            .font(.system(size: changeSize, weight: .semibold).monospacedDigit())
        let trailing = Text(change.trailing)
            .font(.subheadline)
            .foregroundStyle(Color.secondary)
        return Text("\(lead)\(trailing)")
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The bounded, zero-based track. Decorative to VoiceOver: the summary
    /// says everything it shows.
    private func track(_ resolved: Resolved, domain: TrackDomain, compact: Bool) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            GeometryReader { geometry in
                let width = geometry.size.width
                let midY = geometry.size.height / 2
                let at = { (p: Double) -> CGFloat in TrackGeometry.x(p, domain: domain, width: width) }
                ZStack(alignment: .topLeading) {
                    Path { path in
                        path.move(to: CGPoint(x: at(0), y: midY))
                        path.addLine(to: CGPoint(x: at(domain.upper), y: midY))
                    }
                    .stroke(Color.secondary.opacity(0.25), style: StrokeStyle(lineWidth: 2, lineCap: .round))
                    ForEach(domain.tickPercents, id: \.self) { percent in
                        Path { path in
                            let x = at(Double(percent) / 100)
                            path.move(to: CGPoint(x: x, y: midY + 4))
                            path.addLine(to: CGPoint(x: x, y: midY + 8))
                        }
                        .stroke(Color.secondary.opacity(0.5), lineWidth: 1)
                    }
                    if let span = TrackGeometry.span(from: resolved.pregame.probability,
                                                     to: resolved.later.probability,
                                                     domain: domain, width: width) {
                        Path { path in
                            path.move(to: CGPoint(x: span.lowerBound, y: midY))
                            path.addLine(to: CGPoint(x: span.upperBound, y: midY))
                        }
                        .stroke(laterColor, style: StrokeStyle(lineWidth: 4, lineCap: .round))
                    }
                    // Identical chances: the solid mark sits inside the larger
                    // hollow ring at the same coordinate, so both stay visible
                    // without moving either.
                    Circle()
                        .fill(Color.systemBackground)
                        .overlay(Circle().strokeBorder(pregameColor, lineWidth: 2.5))
                        .frame(width: TrackGeometry.pregameMarkDiameter, height: TrackGeometry.pregameMarkDiameter)
                        .position(x: at(resolved.pregame.probability), y: midY)
                    Circle()
                        .fill(laterColor)
                        .frame(width: TrackGeometry.laterMarkDiameter, height: TrackGeometry.laterMarkDiameter)
                        .position(x: at(resolved.later.probability), y: midY)
                }
            }
            .frame(height: TrackGeometry.plotHeight)
            tickLabels(domain, compact: compact)
        }
        .frame(maxWidth: TrackGeometry.maxWidth)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityHidden(true)
    }

    /// The scale's labels under their ticks. The first sits flush left and the
    /// last flush right, so neither runs outside the track. A hidden copy of the
    /// widest label gives the row its height at the reader's text size.
    private func tickLabels(_ domain: TrackDomain, compact: Bool) -> some View {
        Text(verbatim: TrackDomain.tickLabel(domain.upperPercent))
            .hidden()
            .frame(maxWidth: .infinity)
            .overlay { tickLabelRow(domain, compact: compact) }
            .font(.caption2.monospacedDigit())
            .foregroundStyle(.secondary)
    }

    private func tickLabelRow(_ domain: TrackDomain, compact: Bool) -> some View {
        GeometryReader { geometry in
            let width = geometry.size.width
            let labelled = TrackGeometry.labelledTickPercents(domain, width: width, compact: compact)
            ZStack(alignment: .topLeading) {
                ForEach(labelled, id: \.self) { percent in
                    let text = Text(verbatim: TrackDomain.tickLabel(percent))
                    if percent == 0 {
                        text.frame(width: width, alignment: .leading)
                    } else if percent == domain.upperPercent {
                        text.frame(width: width, alignment: .trailing)
                    } else {
                        text.fixedSize()
                            .position(x: TrackGeometry.x(Double(percent) / 100, domain: domain, width: width),
                                      y: geometry.size.height / 2)
                    }
                }
            }
        }
    }

    /// The owner's Details route for exactly this selection.
    private func detailsButton(_ resolved: Resolved) -> some View {
        Button {
            Self.performDetails(resolved, onDetails: onDetails)
        } label: {
            HStack(spacing: 4) {
                Text(Self.detailsTitle)
                    .fixedSize(horizontal: false, vertical: true)
                Image(systemName: "chevron.right")
                    .imageScale(.small)
                    .accessibilityHidden(true)
            }
            .font(.subheadline.weight(.semibold))
            .frame(minWidth: 44, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .foregroundStyle(laterColor)
        .accessibilityLabel(Self.detailsSpokenLabel(resolved))
        .accessibilityIdentifier("\(Self.accessibilityIdentifier)-details")
    }

    /// Each chance's own full local time and age; the change's meaning.
    private func about(_ resolved: Resolved) -> some View {
        DisclosureGroup(Self.disclosureTitle) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach(resolved.readings, id: \.label) { reading in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("\(reading.label): \(reading.text) · \(reading.timeText)")
                            .font(.footnote.monospacedDigit())
                            .fixedSize(horizontal: false, vertical: true)
                        SourceAgeText(observedAt: reading.observedAt)
                    }
                    .accessibilityElement(children: .combine)
                }
                Text("Each chance keeps its own time. The change is the difference between them in percentage points. The later chance can differ from the market's main number.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.top, 6)
        }
        .font(.subheadline)
        .frame(minHeight: 44)
        .accessibilityIdentifier("\(Self.accessibilityIdentifier)-about")
    }
}
