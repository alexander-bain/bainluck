import SwiftUI

// #10868 — golf finish expectations: one golfer's Win, Top 5, Top 10 and Top 20
// chances, plus Make cut when the owner supplies it, as independent bars on one
// 0–100% scale, 188pt tall. Hollow dot =
// before the tournament, filled bar = recorded estimate. After the final round
// each finish carries its actual result as a label, never as a probability or a
// 100% bar.
//
// Presentation only, extracted from the approved design
// (golf-native-ready-composition-20261026 `JFinishViews.swift`). Every figure,
// date, source, missing qualifier and result arrives resolved by the owner and
// is shown verbatim. This layer never formats, rounds, normalizes or parses a
// value, never reads a clock or a source policy, never copies a pre-tournament
// reading into the recorded one, and never derives a result from a probability,
// a rank or a score. Finishes overlap (a win is also a Top 5), so the
// probabilities are never compared to each other or made to sum to anything.
// Make cut is never inferred from a rank or another finish.
//
// Selection, hold, Details and the golfer chooser stay with the host: the view
// keeps no selected state, no sheet, no focus and no subscription. With no
// callback, content is shown without a button.
//
// Host mapping still owed — not available at this base. `GolfTournamentFieldRow`
// and `GolfLeaderboardPlayer` carry a current win/top-5/top-10 probability but
// no pre-tournament baseline, no recorded observation time/source and no
// top-20 history, and nothing maps a confirmed finishing position to an
// inside/outside result. An owner must supply, per golfer:
//   • four finish slots, and optionally a Make cut slot, with stable selection
//     ids (e.g. market + outcome id),
//   • an admitted pre-tournament observation and, during play, an admitted
//     recorded observation, each with raw probability, formatted figure and
//     full date/source text,
//   • its own words for each missing reading,
//   • after the final, a confirmed per-finish result (success / failure /
//     unknown) with its text, plus an optional summary ("T9 · −12").
// None of these may be synthesized from current probability, `movement24h`,
// position strings, score or replay data.

/// One admitted reading. `probability` drives geometry only; `text` is what
/// the reader sees.
nonisolated struct GolfFinishObservation10868: Equatable {
    let probability: Double
    let text: String
    /// Full date and source for VoiceOver ("recorded Oct 7, 7:01 PM PT · DataGolf consensus").
    let accessibilityDetail: String
}

nonisolated enum GolfFinishResultMark10868: Equatable {
    case success
    case failure
    case unknown
}

/// The owner's confirmed result for one finish ("Inside", "Not won", "Unknown").
nonisolated struct GolfFinishResult10868: Equatable {
    let text: String
    let mark: GolfFinishResultMark10868
}

/// One finish. Each reading carries its own missing qualifier, so a missing
/// baseline is never explained by the recorded estimate's reason or vice versa.
/// `actual` is shown only in the final phase.
nonisolated struct GolfFinishSlot10868: Equatable {
    let selection: String
    let name: String
    let color: Color
    let before: GolfFinishObservation10868?
    let recorded: GolfFinishObservation10868?
    let beforeMissing: String
    let recordedMissing: String
    let actual: GolfFinishResult10868
}

nonisolated enum GolfFinishPhase10868: Equatable {
    case before
    case recorded
    case final
}

nonisolated enum GolfFinishLayout10868: Equatable {
    /// The bar chart.
    case bars
    /// Before or during play with nothing to plot: an explanation and every finish name.
    case missingEstimates
    /// Final with every baseline absent: every actual result as a tile.
    case resultTiles
}

nonisolated enum GolfFinishReading10868: Equatable {
    case value(String)
    case missing(String)

    var text: String {
        switch self {
        case .value(let text), .missing(let text): text
        }
    }
}

nonisolated enum GolfFinishAction10868: Equatable {
    case select(String)
    case details(String)

    func perform(onSelectFinish: ((String) -> Void)?, onDetails: ((String) -> Void)?) {
        switch self {
        case .select(let selection): onSelectFinish?(selection)
        case .details(let selection): onDetails?(selection)
        }
    }
}

/// Four explicit finishes, then Make cut only when the owner supplies it, in a
/// fixed order — never sorted, matched by name or dropped. Without `makeCut`
/// the input is exactly the original four.
nonisolated struct GolfFinishExpectationInput10868: Equatable {
    let win: GolfFinishSlot10868
    let top5: GolfFinishSlot10868
    let top10: GolfFinishSlot10868
    let top20: GolfFinishSlot10868
    /// The optional fifth finish. Nil is no fifth slot, never an empty one.
    let makeCut: GolfFinishSlot10868?
    let phase: GolfFinishPhase10868
    let title: String?
    let golferName: String?
    /// Phase and time context ("Latest recorded by Oct 7, 7:01 PM PT").
    let context: String?
    /// Final only ("T9 · −12").
    let actualSummary: String?
    /// The owner's selected finish; read only while recorded.
    let selected: String?

    static let beforeTitle = "Before tournament"
    static let recordedTitle = "Recorded estimate"

    /// `makeCut` trails so every four-finish call keeps its original form.
    init(
        win: GolfFinishSlot10868,
        top5: GolfFinishSlot10868,
        top10: GolfFinishSlot10868,
        top20: GolfFinishSlot10868,
        phase: GolfFinishPhase10868,
        title: String?,
        golferName: String?,
        context: String?,
        actualSummary: String?,
        selected: String?,
        makeCut: GolfFinishSlot10868? = nil
    ) {
        self.win = win
        self.top5 = top5
        self.top10 = top10
        self.top20 = top20
        self.makeCut = makeCut
        self.phase = phase
        self.title = title
        self.golferName = golferName
        self.context = context
        self.actualSummary = actualSummary
        self.selected = selected
    }

    var slots: [GolfFinishSlot10868] { [win, top5, top10, top20] + (makeCut.map { [$0] } ?? []) }

    var layout: GolfFinishLayout10868 {
        switch phase {
        case .before:
            slots.allSatisfy { $0.before == nil } ? .missingEstimates : .bars
        case .recorded:
            slots.allSatisfy { $0.before == nil && $0.recorded == nil } ? .missingEstimates : .bars
        case .final:
            // Genuine zero and partial baselines stay on the chart.
            slots.allSatisfy { $0.before == nil } ? .resultTiles : .bars
        }
    }

    /// The bar: the recorded estimate during play, otherwise the pre-tournament reading.
    func plotted(_ slot: GolfFinishSlot10868) -> GolfFinishObservation10868? {
        phase == .recorded ? slot.recorded : slot.before
    }

    /// The hollow dot over a recorded bar.
    func baseline(_ slot: GolfFinishSlot10868) -> GolfFinishObservation10868? {
        phase == .recorded ? slot.before : nil
    }

    /// The selected finish, only while recorded and only on one exact match —
    /// a missing or ambiguous selection gets no substitute.
    var selectedSlot: GolfFinishSlot10868? {
        guard phase == .recorded, let selected else { return nil }
        let matches = slots.filter { $0.selection == selected }
        return matches.count == 1 ? matches[0] : nil
    }

    func isSelected(_ slot: GolfFinishSlot10868) -> Bool {
        selectedSlot?.selection == slot.selection
    }

    func beforeReading(_ slot: GolfFinishSlot10868) -> GolfFinishReading10868 {
        slot.before.map { .value($0.text) } ?? .missing(slot.beforeMissing)
    }

    func recordedReading(_ slot: GolfFinishSlot10868) -> GolfFinishReading10868 {
        slot.recorded.map { .value($0.text) } ?? .missing(slot.recordedMissing)
    }

    /// The sentence above the plot or tiles; nil when the chart speaks for itself.
    var explanation: String? {
        switch (phase, layout) {
        case (.before, .missingEstimates), (_, .resultTiles): "Pre-tournament chances weren’t recorded."
        case (.recorded, .missingEstimates): "No recorded finish estimates for this golfer at this moment."
        case (.final, .bars): "Bars show recorded pre-tournament chances."
        default: nil
        }
    }

    /// Always explains the overlap; asks for a tap only when one does something.
    func footnote(canSelect: Bool, canOpenDetails: Bool) -> String {
        var parts: [String] = []
        if phase == .final { parts.append("Actual finish is separate from each pre-tournament chance.") }
        parts.append("Finishes overlap; winning also counts as \(top5.name).")
        switch (phase, layout) {
        case (.recorded, _) where canSelect: parts.append("Select a finish to compare its chances.")
        case (.final, .resultTiles) where canOpenDetails: parts.append("Tap a finish for details.")
        case (.before, .bars) where canOpenDetails, (.final, .bars) where canOpenDetails:
            parts.append("Tap a bar for its recorded time and source.")
        default: break
        }
        return parts.joined(separator: " ")
    }

    /// What a bar, tile or finish name does; nil means no button is drawn.
    func action(for slot: GolfFinishSlot10868, canSelect: Bool, canOpenDetails: Bool) -> GolfFinishAction10868? {
        switch phase {
        case .recorded: canSelect ? .select(slot.selection) : nil
        case .before, .final: canOpenDetails ? .details(slot.selection) : nil
        }
    }

    /// The explicit "time & source" action under a recorded comparison.
    func sourceAction(canOpenDetails: Bool) -> GolfFinishAction10868? {
        guard canOpenDetails, let slot = selectedSlot else { return nil }
        return .details(slot.selection)
    }

    /// Golfer, title, context and (final) summary, read once.
    var accessibilityHeader: String? {
        let parts = [title, golferName, context, phase == .final ? actualSummary : nil].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: ". ")
    }

    func accessibilityValue(for slot: GolfFinishSlot10868) -> String {
        let before = Self.spoken(slot.before, missing: slot.beforeMissing, title: Self.beforeTitle)
        switch phase {
        case .before:
            return before
        case .recorded:
            return [before, Self.spoken(slot.recorded, missing: slot.recordedMissing, title: Self.recordedTitle)]
                .joined(separator: "; ")
        case .final:
            return [before, "Actual finish: \(slot.actual.text)"].joined(separator: "; ")
        }
    }

    private static func spoken(_ observation: GolfFinishObservation10868?, missing: String, title: String) -> String {
        observation.map { "\(title): \($0.text), \($0.accessibilityDetail)" } ?? "\(title): \(missing)"
    }
}

nonisolated enum GolfFinishGeometry10868 {
    static let plotHeight: CGFloat = 188

    /// Height from the 0% line. Nil for anything outside 0...1 — bad input is
    /// omitted, never clipped to an edge or drawn as zero. A real zero is 0.
    static func markHeight(_ probability: Double, plotHeight: CGFloat = plotHeight) -> CGFloat? {
        guard probability.isFinite, probability >= 0, probability <= 1 else { return nil }
        return CGFloat(probability) * plotHeight
    }

    /// Bars per row, widest first; accessibility sizes start at two.
    static func columnCandidates(isAccessibilitySize: Bool) -> [Int] {
        isAccessibilitySize ? [2, 1] : [4, 2, 1]
    }

    /// The plan for the number of finishes actually shown. Four keeps the
    /// original plan; five tries one row of five, then 3 + 2, never 4 + 1.
    static func columnCandidates(slotCount: Int, isAccessibilitySize: Bool) -> [Int] {
        guard slotCount == 5 else { return columnCandidates(isAccessibilitySize: isAccessibilitySize) }
        return isAccessibilitySize ? [2, 1] : [5, 3, 2, 1]
    }

    static func tileColumns(isAccessibilitySize: Bool) -> Int {
        isAccessibilitySize ? 1 : 2
    }

    static func groups<Item>(_ items: [Item], columns: Int) -> [[Item]] {
        guard columns > 0 else { return [items] }
        return stride(from: 0, to: items.count, by: columns).map {
            Array(items[$0..<min($0 + columns, items.count)])
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum GolfFinishAccessibilityID10868 {
    static func bar(_ selection: String) -> String { "golfFinish10868.bar.\(selection)" }
    static func finish(_ selection: String) -> String { "golfFinish10868.finish.\(selection)" }
    static func result(_ selection: String) -> String { "golfFinish10868.result.\(selection)" }
    static func source(_ selection: String) -> String { "golfFinish10868.source.\(selection)" }
}

struct GolfFinishExpectationPresentation10868: View {
    let input: GolfFinishExpectationInput10868
    var onSelectFinish: ((String) -> Void)? = nil
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    /// Room above the 100% line for a bar's figure, so it never collides with the plot.
    @ScaledMetric(relativeTo: .headline) private var labelReserve: CGFloat = 30
    @ScaledMetric(relativeTo: .caption2) private var axisWidth: CGFloat = 30

    private var canSelect: Bool { onSelectFinish != nil }
    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            switch input.layout {
            case .bars: bars
            case .missingEstimates: missingEstimates
            case .resultTiles: resultTiles
            }
            Text(input.footnote(canSelect: canSelect, canOpenDetails: canOpenDetails))
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
            sourceButton
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header

    @ViewBuilder private var header: some View {
        if let spoken = input.accessibilityHeader {
            VStack(alignment: .leading, spacing: 4) {
                if let title = input.title { Text(title).font(.title2.bold()) }
                if let name = input.golferName { Text(name).font(.headline) }
                if let context = input.context {
                    Text(context).font(.footnote).foregroundStyle(DS.textSecondary)
                }
                if input.phase == .final, let summary = input.actualSummary {
                    Text(summary).font(.title2.bold()).foregroundStyle(DS.blue)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spoken)
            .accessibilityAddTraits(.isHeader)
        }
    }

    // MARK: Chart

    private var bars: some View {
        VStack(alignment: .leading, spacing: 14) {
            if let selected = input.selectedSlot {
                comparison(selected)
            } else if input.phase == .recorded {
                keyRow
            }
            if let explanation = input.explanation {
                Text(explanation)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            // All bars in one row, then fewer per row — the plot never shrinks.
            ViewThatFits(in: .horizontal) {
                ForEach(GolfFinishGeometry10868.columnCandidates(slotCount: input.slots.count, isAccessibilitySize: typeSize.isAccessibilitySize), id: \.self) { count in
                    plotRows(count)
                }
            }
        }
    }

    private func plotRows(_ count: Int) -> some View {
        VStack(alignment: .leading, spacing: 18) {
            ForEach(Array(GolfFinishGeometry10868.groups(input.slots, columns: count).enumerated()), id: \.offset) { _, row in
                HStack(alignment: .top, spacing: 10) {
                    axis
                    HStack(alignment: .top, spacing: 12) {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, slot in
                            column(slot)
                        }
                        // A short last row keeps the same bar width as the rows above it.
                        ForEach(row.count..<max(row.count, count), id: \.self) { _ in
                            Color.clear.frame(height: 0).frame(maxWidth: .infinity).accessibilityHidden(true)
                        }
                    }
                    .background(alignment: .top) { gridlines }
                }
            }
        }
    }

    /// Repeated on every row so a stacked bar is never read without its scale.
    private var axis: some View {
        ZStack {
            Text("100%").frame(maxHeight: .infinity, alignment: .top)
            Text("50%")
            Text("0%").frame(maxHeight: .infinity, alignment: .bottom)
        }
        .font(.caption2)
        .foregroundStyle(DS.textSecondary)
        .fixedSize(horizontal: true, vertical: false)
        .frame(minWidth: axisWidth, alignment: .trailing)
        .frame(height: GolfFinishGeometry10868.plotHeight)
        .padding(.top, labelReserve)
        .accessibilityHidden(true)
    }

    private var gridlines: some View {
        let height = GolfFinishGeometry10868.plotHeight
        return ZStack(alignment: .top) {
            DS.border.frame(height: 1)
            DS.border.frame(height: 1).offset(y: height / 2 - 0.5)
            DS.border.frame(height: 1).offset(y: height - 1)
        }
        .frame(height: height, alignment: .top)
        .padding(.top, labelReserve)
        .accessibilityHidden(true)
    }

    private func column(_ slot: GolfFinishSlot10868) -> some View {
        let action = input.action(for: slot, canSelect: canSelect, canOpenDetails: canOpenDetails)
        return control(action) {
            VStack(spacing: 10) {
                plot(slot)
                Text(slot.name)
                    .underline(input.isSelected(slot))
                    .font(.subheadline.weight(.semibold))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                if input.phase == .recorded {
                    VStack(spacing: 4) {
                        Text("Before").foregroundStyle(DS.textSecondary)
                        Text(input.beforeReading(slot).text).bold()
                    }
                    .font(.footnote)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                }
                if input.phase == .final {
                    resultLabel(slot.actual, font: .caption)
                }
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .top)
            .contentShape(Rectangle())
        }
        .accessibilityLabel(slot.name)
        .accessibilityValue(input.accessibilityValue(for: slot))
        .accessibilityHint(hint(action))
        .accessibilityAddTraits(input.isSelected(slot) ? .isSelected : [])
        .accessibilityIdentifier(GolfFinishAccessibilityID10868.bar(slot.selection))
    }

    /// The figure rides on top of its bar inside the reserved band; a missing
    /// reading is a dashed outline with the owner's words, never a zero bar.
    private func plot(_ slot: GolfFinishSlot10868) -> some View {
        let height = GolfFinishGeometry10868.plotHeight
        return ZStack(alignment: .bottom) {
            if let observation = input.plotted(slot) {
                if let bar = GolfFinishGeometry10868.markHeight(observation.probability) {
                    VStack(spacing: 6) {
                        figure(observation.text)
                        RoundedRectangle(cornerRadius: 5)
                            .fill(slot.color.opacity(0.8))
                            .overlay {
                                if input.isSelected(slot) && bar > 0 {
                                    RoundedRectangle(cornerRadius: 5).strokeBorder(DS.textPrimary, lineWidth: 2)
                                }
                            }
                            .frame(height: bar)
                    }
                    if bar == 0 {
                        slot.color.frame(height: 2)
                    }
                } else {
                    // Malformed coordinate: the owner's figure, no mark.
                    figure(observation.text).frame(height: height)
                }
            } else {
                RoundedRectangle(cornerRadius: 5)
                    .stroke(DS.border, style: StrokeStyle(lineWidth: 1, dash: [3, 3]))
                    .frame(height: height)
                    .overlay {
                        Text(input.phase == .recorded ? slot.recordedMissing : slot.beforeMissing)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(4)
                    }
            }
        }
        .frame(maxWidth: .infinity)
        .frame(height: labelReserve + height, alignment: .bottom)
        .overlay(alignment: .bottom) {
            if let baseline = input.baseline(slot),
               let y = GolfFinishGeometry10868.markHeight(baseline.probability) {
                Circle()
                    .fill(DS.cardBg)
                    .overlay(Circle().stroke(DS.textPrimary, lineWidth: 2))
                    .frame(width: 10, height: 10)
                    .offset(y: 5 - y)
            }
        }
        .accessibilityHidden(true)
    }

    private func figure(_ text: String) -> some View {
        Text(text).font(.headline).monospacedDigit().fixedSize()
    }

    // MARK: Selected comparison

    /// Spoken by the selected bar, so hidden here rather than read twice.
    private func comparison(_ slot: GolfFinishSlot10868) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(slot.name).font(.headline)
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 14) { comparisonValues(slot) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 14) { comparisonValues(slot) }
                    VStack(alignment: .leading, spacing: 14) { comparisonValues(slot) }
                }
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
        .accessibilityHidden(true)
    }

    @ViewBuilder private func comparisonValues(_ slot: GolfFinishSlot10868) -> some View {
        comparisonValue(input.beforeReading(slot), title: GolfFinishExpectationInput10868.beforeTitle, hollow: true)
        comparisonValue(input.recordedReading(slot), title: GolfFinishExpectationInput10868.recordedTitle, hollow: false)
    }

    private func comparisonValue(_ reading: GolfFinishReading10868, title: String, hollow: Bool) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 5) {
                keyMark(hollow: hollow)
                Text(title).font(.caption).foregroundStyle(DS.textSecondary)
            }
            switch reading {
            case .value(let text):
                // The whole figure, `<`/`>` and `%` included, keeps its width, so a narrow
                // row stacks the pair instead of squeezing or splitting a number.
                Text(text).font(.system(size: figureSize, weight: .bold)).monospacedDigit()
                    .fixedSize(horizontal: true, vertical: false)
            case .missing(let text):
                Text(text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private var keyRow: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 16) { key(hollow: true); key(hollow: false) }
            VStack(alignment: .leading, spacing: 8) { key(hollow: true); key(hollow: false) }
        }
        .accessibilityHidden(true)
    }

    private func key(hollow: Bool) -> some View {
        HStack(spacing: 6) {
            keyMark(hollow: hollow)
            Text(hollow ? GolfFinishExpectationInput10868.beforeTitle : GolfFinishExpectationInput10868.recordedTitle)
                .font(.footnote)
                .foregroundStyle(DS.textSecondary)
        }
    }

    @ViewBuilder private func keyMark(hollow: Bool) -> some View {
        if hollow {
            Circle().fill(DS.cardBg).overlay(Circle().stroke(DS.textSecondary, lineWidth: 2)).frame(width: 9, height: 9)
        } else {
            RoundedRectangle(cornerRadius: 1).fill(DS.textSecondary).frame(width: 9, height: 9)
        }
    }

    // MARK: Nothing to plot

    private var missingEstimates: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let explanation = input.explanation {
                Text(explanation)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            LazyVGrid(columns: gridColumns, spacing: 8) {
                ForEach(Array(input.slots.enumerated()), id: \.offset) { _, slot in
                    let action = input.action(for: slot, canSelect: canSelect, canOpenDetails: canOpenDetails)
                    control(action) {
                        Text(slot.name)
                            .font(.subheadline.weight(.semibold))
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 8)
                            .frame(maxWidth: .infinity, minHeight: 44)
                            .overlay(
                                RoundedRectangle(cornerRadius: 9)
                                    .stroke(input.isSelected(slot) ? DS.textPrimary : DS.border, lineWidth: input.isSelected(slot) ? 2 : 1)
                            )
                            .contentShape(Rectangle())
                    }
                    .accessibilityLabel(slot.name)
                    .accessibilityValue(input.accessibilityValue(for: slot))
                    .accessibilityHint(hint(action))
                    .accessibilityAddTraits(input.isSelected(slot) ? .isSelected : [])
                    .accessibilityIdentifier(GolfFinishAccessibilityID10868.finish(slot.selection))
                }
            }
        }
    }

    // MARK: Final, no baselines

    private var resultTiles: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let explanation = input.explanation {
                Text(explanation)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            LazyVGrid(columns: gridColumns, spacing: 10) {
                ForEach(Array(input.slots.enumerated()), id: \.offset) { _, slot in
                    let action = input.action(for: slot, canSelect: canSelect, canOpenDetails: canOpenDetails)
                    control(action) {
                        VStack(alignment: .leading, spacing: 9) {
                            Text(slot.name).font(.subheadline.weight(.semibold))
                            resultLabel(slot.actual, font: .headline)
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(12)
                        .frame(maxWidth: .infinity, minHeight: 76, alignment: .leading)
                        .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
                        .overlay(RoundedRectangle(cornerRadius: 12).stroke(DS.border))
                        .contentShape(Rectangle())
                    }
                    .accessibilityLabel(slot.name)
                    .accessibilityValue(input.accessibilityValue(for: slot))
                    .accessibilityHint(hint(action))
                    .accessibilityIdentifier(GolfFinishAccessibilityID10868.result(slot.selection))
                }
            }
        }
    }

    private var gridColumns: [GridItem] {
        Array(
            repeating: GridItem(.flexible(), spacing: 10, alignment: .top),
            count: GolfFinishGeometry10868.tileColumns(isAccessibilitySize: typeSize.isAccessibilitySize)
        )
    }

    /// A result label, distinct from any probability; unknown is never drawn as a loss.
    @ViewBuilder private func resultLabel(_ result: GolfFinishResult10868, font: Font) -> some View {
        Group {
            switch result.mark {
            case .success:
                Label(result.text, systemImage: "checkmark").foregroundStyle(DS.emeraldDark)
            case .failure:
                Label(result.text, systemImage: "xmark").foregroundStyle(DS.textPrimary)
            case .unknown:
                Text(result.text).foregroundStyle(DS.textSecondary)
            }
        }
        .font(font)
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Source action

    @ViewBuilder private var sourceButton: some View {
        if let action = input.sourceAction(canOpenDetails: canOpenDetails), let slot = input.selectedSlot {
            Button {
                action.perform(onSelectFinish: onSelectFinish, onDetails: onDetails)
            } label: {
                Text("\(slot.name) · time & source")
                    .font(.footnote)
                    .foregroundStyle(DS.blue)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(minHeight: 44, alignment: .leading)
            }
            .accessibilityIdentifier(GolfFinishAccessibilityID10868.source(slot.selection))
        }
    }

    // MARK: Controls

    /// A button only when the owner supplied the callback; otherwise the same
    /// content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: GolfFinishAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                action.perform(onSelectFinish: onSelectFinish, onDetails: onDetails)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }

    private func hint(_ action: GolfFinishAction10868?) -> String {
        switch action {
        case .select: "Selects this finish’s comparison"
        case .details: "Opens this finish’s recorded time and source"
        case nil: ""
        }
    }
}
