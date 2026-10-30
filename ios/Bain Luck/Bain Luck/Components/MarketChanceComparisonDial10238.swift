import SwiftUI

/// #10238 — A SELECTED MARKET'S PREGAME AND LATER CHANCE AS TWO EQUAL FIGURES
/// AND ONE SMALL DIAL (design: `binary-side-comparison-20261026/live-phone.png`,
/// semicircle semantics `binary-probability-dials-v35/README.md`).
///
/// Two equally prominent percentages lead — a hollow-keyed "Pregame chance" and
/// a solid-keyed "Later chance" — and a 0–100% semicircle under them places
/// both. A short segment between the two marks draws their difference; it is
/// not a history curve, a distribution or a stat projection. The served change
/// sits inside the dial ("Up 20.0 points", "in chance since pregame").
///
/// PRESENTATION ONLY, of one already resolved `EventQuestionMatrixAdapter.Detail`
/// — the host resolved it for the exact `QuestionMatrixSelection` on its own
/// latest payload, so admission, same-event scope and aging are the owner's:
///
///   - BOTH CHANCES   `detail.comparison.baseline` / `.latest`, each with its own
///                    `observedAt`, as served. `comparison.latest` is NOT
///                    `detail.option.value`: the published number can carry a
///                    different basis (R5). With published 52%, latest 60% and
///                    baseline 40%, this prints 40% → 60%, never 52%.
///   - THE CHANGE     `comparison.points`, the server's percentage points. Its
///                    sign gives the direction word and `deltaPointsNumber` the
///                    magnitude; nothing is recomputed from either probability or
///                    from a printed percent. A non-zero move under 0.05 prints
///                    "<0.1", never "0.0" or "No change".
///   - PERCENTS       `formatProbability` (whole percents — the browser prints
///                    one decimal, 71.5%; that deviation is the shared formatter's,
///                    not reconciled here), behind the host's own exact-endpoint
///                    guard: a quoted 0 prints 0% and a quoted 1 prints 100%.
///   - TIMES          `SourceAge.preciseStamp` (the reader's local time) and
///                    `SourceAgeText` per chance, never one shared clock. An
///                    unreadable stamp prints "Time unavailable"; the other
///                    chance's time is never borrowed.
///   - NAMES          `detail.row.label`, `detail.row.period?.label` and
///                    `detail.option.label`, verbatim. No player, stat or side is
///                    parsed out of them.
///
/// No comparison, no dial: `resolve` answers nil and the host keeps its existing
/// renderer. A raw contributor selection, a won/lost/refused/unpriced value and
/// a finished question without a served comparison never gain a dial or a
/// terminal 0/100 journey. Nothing is retained between renders, so a comparison
/// that leaves the payload leaves the screen with it. The adapter cannot yet
/// carry a baseline-only or finished-actual comparison (it needs `latest`); that
/// is the owner contract's to add, not this view's to rebuild.
///
/// ACTION. When the host supplies `onSelect` AND the row is exactly two served
/// options with no missing leg, no "more options" disclosure and `complete` not
/// explicitly false, the two options become 44-point controls. Their labels and
/// selections are the row's own, verbatim; nothing is inferred about over/under
/// or complements. A tap on the unselected side hands its exact selection to the
/// owner, which re-resolves the detail — this view keeps no selected-state copy.
/// Otherwise the selected option's label prints as plain text.
///
/// Mount (Native, later — not done here): in
/// `EventQuestionMatrixSection10238.detail(_:)`, in place of
/// `comparisonSection(comparison)` when `resolve` answers, keeping it as the
/// fallback. Inputs: the `resolved` Detail of that same `.available` case →
/// `detail`; two host colours → `pregameColor` / `laterColor`; the host's
/// `open`-switching closure → `onSelect`. Exactly one comparison renderer per
/// detail.
struct MarketChanceComparisonDial10238: View {
    let detail: EventQuestionMatrixAdapter.Detail
    /// The hollow (earlier) mark, its key and its figure.
    let pregameColor: Color
    /// The solid (later) mark, the difference segment, its key and its figure.
    let laterColor: Color
    /// False where the host already prints the market and outcome right above
    /// (its summary). VoiceOver hears them either way.
    let showsHeading: Bool
    /// The exact sibling selection, only where `SideControl`s are offered.
    let onSelect: ((QuestionMatrixSelection) -> Void)?

    @Environment(\.dynamicTypeSize) private var typeSize
    /// The approved reference: two 26-point figures, scaled with text size.
    @ScaledMetric(relativeTo: .title2) private var valueSize: CGFloat = 26
    @ScaledMetric(relativeTo: .headline) private var changeSize: CGFloat = 17

    init(
        detail: EventQuestionMatrixAdapter.Detail,
        pregameColor: Color,
        laterColor: Color,
        showsHeading: Bool = true,
        onSelect: ((QuestionMatrixSelection) -> Void)? = nil
    ) {
        self.detail = detail
        self.pregameColor = pregameColor
        self.laterColor = laterColor
        self.showsHeading = showsHeading
        self.onSelect = onSelect
    }

    static var accessibilityIdentifier: String { "market-chance-comparison-dial-10238" }

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

        /// "Oct 3, 10:00 AM" or the words that stand in for an unreadable one.
        static var timeUnavailableText: String { "Time unavailable" }
        var timeText: String { localTime ?? Self.timeUnavailableText }
        var spoken: String { "\(label) \(text), \(timeText)" }
    }

    nonisolated enum Direction: Equatable {
        case up
        case down
        case none
    }

    /// The served change, as words.
    nonisolated struct Change: Equatable {
        let direction: Direction
        /// The unsigned magnitude ("20.0", "<0.1"); nil for no change.
        let magnitude: String?

        /// The dial's figure: "Up 20.0 points", "Down <0.1 points", "No change".
        var text: String {
            switch (direction, magnitude) {
            case (.up, let m?): return "Up \(m) points"
            case (.down, let m?): return "Down \(m) points"
            default: return "No change"
            }
        }

        /// Under the figure, so "points" can only be read as chance.
        static var qualifier: String { "in chance since pregame" }

        var spoken: String {
            switch (direction, magnitude) {
            case (.up, let m?): return "Up \(m) percentage points since pregame"
            case (.down, let m?): return "Down \(m) percentage points since pregame"
            default: return "No change since pregame"
            }
        }

        var symbol: String? {
            switch direction {
            case .up: return "arrow.up"
            case .down: return "arrow.down"
            case .none: return nil
            }
        }
    }

    /// One of the row's two served options, offered as a control.
    nonisolated struct SideControl: Equatable, Identifiable {
        let selection: QuestionMatrixSelection
        /// The option's served label, verbatim.
        let label: String
        let isSelected: Bool
        /// The control's spoken name: the option, then the market.
        let spokenLabel: String
        var id: QuestionMatrixSelection { selection }
    }

    nonisolated struct Resolved: Equatable {
        /// The market, verbatim.
        let title: String
        /// The served period label, when there is one.
        let period: String?
        /// The selected option's label, verbatim.
        let outcome: String
        let selection: QuestionMatrixSelection
        let pregame: Reading
        let later: Reading
        let change: Change
        /// Nil where the row does not fit the two-control shape or the host
        /// supplied no callback.
        let controls: [SideControl]?

        var readings: [Reading] { [pregame, later] }

        /// One VoiceOver stop: the market, the outcome, both named chances with
        /// their own times, then the change.
        var spokenSummary: String {
            ([title] + (period.map { [$0] } ?? []) + [outcome]
                + readings.map(\.spoken) + [change.spoken])
                .joined(separator: ". ")
        }
    }

    /// How the view arranges itself.
    nonisolated struct Arrangement: Equatable {
        /// The two figures stand one below the other, never side by side.
        let stacksReadings: Bool
        /// The change sits inside the dial's hollow; otherwise under the dial,
        /// so a larger text size grows the view and never the bounded dial.
        let changeInsideDial: Bool
    }

    static var pregameLabel: String { "Pregame chance" }
    static var laterLabel: String { "Later chance" }
    static var disclosureTitle: String { "About this comparison" }
    static var timeUnavailableText: String { Reading.timeUnavailableText }

    /// Accessibility sizes always stack (other sizes stack only when the two
    /// columns do not fit); from xxLarge the change moves out of the dial.
    static func arrangement(typeSize: DynamicTypeSize) -> Arrangement {
        Arrangement(stacksReadings: typeSize.isAccessibilitySize,
                    changeInsideDial: typeSize < .xxLarge)
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

    /// The two controls, or nil. Exactly the row's two served options, in served
    /// order, when nothing says the row has more; the selected one is matched by
    /// the full selection identity (scope, question and option).
    static func controls(for detail: EventQuestionMatrixAdapter.Detail, canSelect: Bool) -> [SideControl]? {
        let row = detail.row
        let selected = detail.option.selection
        guard canSelect,
              selected.outcomeId == nil,
              row.options.count == 2,
              row.missingOptions.isEmpty,
              !row.offersMoreOptions,
              row.complete != false,
              row.options.contains(where: { $0.selection == selected })
        else { return nil }
        return row.options.map { option in
            SideControl(selection: option.selection, label: option.label,
                        isSelected: option.selection == selected,
                        spokenLabel: "\(option.label), \(row.label)")
        }
    }

    /// The dial for this detail, or nil where it declines: no served
    /// comparison, so the host's existing renderer stays.
    static func resolve(_ detail: EventQuestionMatrixAdapter.Detail, canSelect: Bool) -> Resolved? {
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
            controls: controls(for: detail, canSelect: canSelect)
        )
    }

    /// Hands the owner exactly this control's selection, and only for the side
    /// not already selected.
    static func perform(_ control: SideControl, onSelect: ((QuestionMatrixSelection) -> Void)?) {
        guard !control.isSelected else { return }
        onSelect?(control.selection)
    }

    // MARK: - The dial's geometry

    /// The semicircle in a 300 × 173 canvas, scaled to the drawn width (at most
    /// 240 points). 0% is the left end, 50% the top, 100% the right end; angles
    /// are SwiftUI's (degrees clockwise from +x on screen, y down).
    nonisolated enum DialGeometry {
        static let canvas = CGSize(width: 300, height: 173)
        static let center = CGPoint(x: 150, y: 138)
        static let radius: CGFloat = 112
        static let maxWidth: CGFloat = 240
        static let ticks: [Double] = [0, 0.5, 1]

        /// 180° at 0%, 270° at 50%, 360° at 100%.
        static func angleDegrees(_ probability: Double) -> Double {
            180 + 180 * probability
        }

        /// A probability's place on the arc, in canvas points.
        static func point(_ probability: Double) -> CGPoint {
            let radians = angleDegrees(probability) * .pi / 180
            return CGPoint(x: center.x + radius * CGFloat(cos(radians)),
                           y: center.y + radius * CGFloat(sin(radians)))
        }

        /// The difference segment from the earlier to the later chance, or nil
        /// when they are identical (no segment is invented between them).
        /// `clockwise` is SwiftUI's flag: false draws a rise over the top.
        static func segment(from earlier: Double, to later: Double)
            -> (start: Double, end: Double, clockwise: Bool)? {
            guard earlier != later else { return nil }
            return (angleDegrees(earlier), angleDegrees(later), later < earlier)
        }
    }

    private var resolved: Resolved? {
        Self.resolve(detail, canSelect: onSelect != nil)
    }

    // MARK: - Body

    var body: some View {
        if let resolved {
            let arrangement = Self.arrangement(typeSize: typeSize)
            VStack(alignment: .leading, spacing: 12) {
                if showsHeading {
                    heading(resolved, showsOutcome: resolved.controls == nil)
                }
                if let controls = resolved.controls {
                    sideControls(controls)
                }
                VStack(alignment: .leading, spacing: 10) {
                    readings(resolved, arrangement: arrangement)
                    dial(resolved, changeInside: arrangement.changeInsideDial)
                    if !arrangement.changeInsideDial {
                        changeBlock(resolved.change, alignment: .leading)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(resolved.spokenSummary)
                .accessibilityIdentifier("\(Self.accessibilityIdentifier)-summary")
                about(resolved)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .contain)
            .accessibilityIdentifier(Self.accessibilityIdentifier)
        }
    }

    // MARK: - Pieces

    /// The market, its period and (without controls) the selected option. Read
    /// by VoiceOver inside the summary, so not a stop of its own.
    private func heading(_ resolved: Resolved, showsOutcome: Bool) -> some View {
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
            if showsOutcome {
                Text(resolved.outcome)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityHidden(true)
    }

    /// The row's two options as equal 44-point controls; stacked at
    /// accessibility sizes. Each is its own VoiceOver stop.
    private func sideControls(_ controls: [SideControl]) -> some View {
        let layout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(spacing: 8))
            : AnyLayout(HStackLayout(spacing: 8))
        return layout {
            ForEach(controls) { control in
                Button {
                    Self.perform(control, onSelect: onSelect)
                } label: {
                    Text(control.label)
                        .font(.subheadline.weight(control.isSelected ? .semibold : .regular))
                        .foregroundStyle(control.isSelected ? Color.primary : Color.secondary)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 10)
                        .padding(.vertical, 8)
                        .frame(maxWidth: .infinity, minHeight: 44)
                        .background(
                            RoundedRectangle(cornerRadius: 10)
                                .fill(control.isSelected ? laterColor.opacity(0.08) : Color.clear)
                        )
                        .overlay(
                            RoundedRectangle(cornerRadius: 10)
                                .stroke(control.isSelected ? laterColor : Color.secondary.opacity(0.3),
                                        lineWidth: control.isSelected ? 1.5 : 1)
                        )
                        .contentShape(RoundedRectangle(cornerRadius: 10))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(control.spokenLabel)
                .accessibilityAddTraits(control.isSelected ? .isSelected : [])
            }
        }
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

    /// A figure, whole and on one line: never wrapped, split or scaled down.
    private func figure(_ reading: Reading, color: Color) -> some View {
        Text(reading.text)
            .font(.system(size: valueSize, weight: .bold).monospacedDigit())
            .foregroundStyle(color)
            .lineLimit(1)
            .fixedSize()
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func age(_ reading: Reading) -> some View {
        SourceAgeText(observedAt: reading.observedAt)
            .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// "Up 20.0 points" whole, the qualifier wrapping under it.
    private func changeBlock(_ change: Change, alignment: HorizontalAlignment) -> some View {
        VStack(alignment: alignment, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if let symbol = change.symbol {
                    Image(systemName: symbol)
                        .font(.system(size: changeSize * 0.85, weight: .semibold))
                }
                Text(change.text)
                    .font(.system(size: changeSize, weight: .semibold).monospacedDigit())
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(Change.qualifier)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .multilineTextAlignment(alignment == .center ? .center : .leading)
    }

    /// The bounded semicircle. Decorative to VoiceOver: the summary says it.
    private func dial(_ resolved: Resolved, changeInside: Bool) -> some View {
        GeometryReader { geometry in
            let scale = geometry.size.width / DialGeometry.canvas.width
            let at = { (p: Double) -> CGPoint in
                let point = DialGeometry.point(p)
                return CGPoint(x: point.x * scale, y: point.y * scale)
            }
            let center = CGPoint(x: DialGeometry.center.x * scale, y: DialGeometry.center.y * scale)
            let radius = DialGeometry.radius * scale
            ZStack(alignment: .topLeading) {
                Path { path in
                    path.addArc(center: center, radius: radius,
                                startAngle: .degrees(180), endAngle: .degrees(360), clockwise: false)
                }
                .stroke(Color.secondary.opacity(0.18), style: StrokeStyle(lineWidth: 7, lineCap: .round))
                ForEach(DialGeometry.ticks, id: \.self) { tick in
                    Circle().fill(Color.secondary).frame(width: 4, height: 4).position(at(tick))
                }
                if let segment = DialGeometry.segment(from: resolved.pregame.probability,
                                                      to: resolved.later.probability) {
                    Path { path in
                        path.addArc(center: center, radius: radius,
                                    startAngle: .degrees(segment.start), endAngle: .degrees(segment.end),
                                    clockwise: segment.clockwise)
                    }
                    .stroke(laterColor.opacity(0.35), style: StrokeStyle(lineWidth: 7, lineCap: .round))
                }
                // Identical chances: the solid mark sits inside the larger
                // hollow ring, so both stay visible without moving either.
                Circle()
                    .fill(Color.systemBackground)
                    .overlay(Circle().strokeBorder(pregameColor, lineWidth: 2.5))
                    .frame(width: 14, height: 14)
                    .position(at(resolved.pregame.probability))
                Circle()
                    .fill(laterColor)
                    .frame(width: 8, height: 8)
                    .position(at(resolved.later.probability))
                Group {
                    Text(verbatim: "0%").position(x: 38 * scale, y: 159 * scale)
                    Text(verbatim: "50%").position(x: 150 * scale, y: 9 * scale)
                    Text(verbatim: "100%").position(x: 262 * scale, y: 159 * scale)
                }
                .font(.caption2)
                .foregroundStyle(.secondary)
                .dynamicTypeSize(...DynamicTypeSize.xxxLarge)
                if changeInside {
                    changeBlock(resolved.change, alignment: .center)
                        .frame(width: 170 * scale)
                        .position(x: 150 * scale, y: 100 * scale)
                }
            }
        }
        .aspectRatio(DialGeometry.canvas.width / DialGeometry.canvas.height, contentMode: .fit)
        .frame(maxWidth: DialGeometry.maxWidth)
        .frame(maxWidth: .infinity)
        .accessibilityHidden(true)
    }

    /// Each chance's own full local time and age; the change's meaning.
    private func about(_ resolved: Resolved) -> some View {
        DisclosureGroup(Self.disclosureTitle) {
            VStack(alignment: .leading, spacing: 8) {
                ForEach([resolved.pregame, resolved.later], id: \.label) { reading in
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
