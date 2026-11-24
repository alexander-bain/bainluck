import Charts
import SwiftUI

/// #10396 / #10238: a renderer for one independently delivered Game or Series
/// matrix. The host keeps this view mounted when its optional payload vanishes;
/// selection is resolved against the latest payload, never a saved priced row.
/// Native owns EventDetailView composition, Apple gates and installed acceptance.
struct EventQuestionMatrixSection10238: View {
    let matrix: EventQuestionMatrix?
    let scope: QuestionMatrixScope

    private struct OpenOption: Identifiable {
        let id: QuestionMatrixSelection
    }
    private enum Focus: Hashable {
        case heading
        case option(QuestionMatrixSelection)
    }

    @State private var open: OpenOption?
    @State private var returnSelection: QuestionMatrixSelection?
    /// #10830 — the questions the browser has on screen right now.
    @State private var visibleRowIDs: Set<EventQuestionMatrixAdapter.RowID> = []
    @State private var visibleSegmentIDs: Set<String> = []
    @State private var expandedLadders: Set<String> = []
    @State private var activeQuery = ""
    @State private var measuredWidth: CGFloat = 358
    @AccessibilityFocusState private var focus: Focus?
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// The ladder's label column, so every bar starts at the same x and the
    /// column grows with the reader's text size.
    @ScaledMetric(relativeTo: .subheadline) private var labelColumn: CGFloat = 116
    @ScaledMetric(relativeTo: .subheadline) private var valueColumn: CGFloat = 48

    private var rows: [EventQuestionMatrixAdapter.Row] {
        EventQuestionMatrixAdapter.rows(in: matrix, scope: scope)
    }
    /// Alex 10/10: ordinary sports words, not "questions".
    private var title: String { Self.title(scope) }
    static func title(_ scope: QuestionMatrixScope) -> String {
        scope == .game ? "Game odds" : "Series odds"
    }

    var body: some View {
        // Keep a reachable fallback while an open question is withdrawn.
        // A never-populated section resolves to no view at all, so the page's
        // stack spends no spacing on it (an always-present empty VStack cost
        // every event page 12pt per section). @State lives on this view's
        // identity, not its content, so selection survives either way.
        if !rows.isEmpty || open != nil || returnSelection != nil {
            VStack(alignment: .leading, spacing: 12) {
                Text(title)
                    .font(.headline)
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityFocused($focus, equals: .heading)
                if rows.isEmpty {
                    Text("Markets are unavailable right now")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                // #10830 — a bounded, searchable window by family (web's
                // compact game-question browser, #10809). An NFL page serves
                // ~200 questions; drawn whole they were ~70,000 pt of scroll.
                // Each question is still `question(_:)`, and selection still
                // resolves against the latest payload. The period ("Game",
                // "1st half") is a heading over its run of lines, said once.
                let segments = EventQuestionMatrixLadderGroup10830.segment(rows)
                MarketBrowserView(
                    label: title,
                    items: segments,
                    group: { $0.family },
                    searchText: { $0.searchText },
                    pageSize: Self.pageSize,
                    searchPrompt: "team or line",
                    visibleIDs: $visibleSegmentIDs,
                    heading: { $0.periodLabel },
                    browseItemCount: rows.count,
                    onQueryChange: { activeQuery = $0 }
                ) { segment in
                    switch segment {
                    case .row(let row):
                        question(row)
                    case .ladder(let group):
                        ladderGroupView(group)
                    }
                }
                .onChange(of: visibleSegmentIDs, initial: true) { _, _ in
                    syncVisibleRowIDs(segments: segments)
                }
                .onChange(of: expandedLadders) { _, _ in
                    syncVisibleRowIDs(segments: segments)
                }
                .onChange(of: activeQuery) { _, _ in
                    syncVisibleRowIDs(segments: segments)
                }
                .onChange(of: rows.map(\.id)) { _, _ in
                    syncVisibleRowIDs(segments: EventQuestionMatrixLadderGroup10830.segment(rows))
                }
            }
            .background(
                GeometryReader { geo in
                    Color.clear.preference(key: LadderWidthKey10830.self, value: geo.size.width)
                }
            )
            .onPreferenceChange(LadderWidthKey10830.self) { width in
                if width > 0 { measuredWidth = width }
            }
            .sheet(item: $open, onDismiss: restoreFocus) { selected in
                detail(selected.id)
            }
        }
    }

    // MARK: - Browsing (#10830)

    /// Alex 10/10: a question is a ladder line now, not a tall card, so a page
    /// holds as many as any other browser's.
    static let pageSize = MarketBrowserLogic.pageSize

    /// The family a question is browsed under, read from its typed kind and
    /// its own words. Navigation only: every question keeps its own card and
    /// options, and one the rules do not recognise is "More markets" rather
    /// than guessed into a family.
    static func family(_ row: EventQuestionMatrixAdapter.Row) -> String {
        let label = row.label.lowercased()
        if label.contains("team total") { return "Team totals" }
        if label.contains("spread") || label.contains("handicap") || row.kind == .signedHandicap {
            return "Spreads"
        }
        if row.kind == .countThreshold || label.contains("o/u") || label.contains("total") {
            return "Totals"
        }
        if label.contains("moneyline") || label.contains("winner") { return "Winners" }
        return "More markets"
    }

    /// What a search over one question reads: its words, its period and every
    /// option's name.
    static func searchText(_ row: EventQuestionMatrixAdapter.Row) -> String {
        ([row.label, row.period?.label ?? ""] + row.options.map(\.label)).joined(separator: " ")
    }

    /// One line of the compact ladder: what the line is called, and the
    /// served option it opens.
    struct ScanLine: Identifiable, Equatable {
        var id: QuestionMatrixSelection { option.selection }
        let label: String
        let option: EventQuestionMatrixAdapter.Option
    }

    /// How a question is scanned (Alex 10/10: threshold at left, bar in the
    /// middle, percent at right — not a tall card that says the line twice).
    ///
    /// A typed threshold with exactly ONE option is one line named by the
    /// question ("24+ points"): its option ("Over 23.5 points") states the
    /// same line again, so it moves to the detail and to VoiceOver instead of
    /// being printed beside it. Every other question keeps its own heading and
    /// one line per served option, named by that option — no option is
    /// renamed into the question's words and no missing side is added.
    static func scan(_ row: EventQuestionMatrixAdapter.Row) -> (heading: String?, lines: [ScanLine]) {
        if row.kind == .countThreshold, row.options.count == 1, let only = row.options.first {
            return (nil, [ScanLine(label: row.label, option: only)])
        }
        return (row.label, row.options.map { ScanLine(label: $0.label, option: $0) })
    }

    private func syncVisibleRowIDs(segments: [EventQuestionMatrixLadderGroup10830.Segment]) {
        visibleRowIDs = EventQuestionMatrixLadderGroup10830.visibleRowIDs(
            forVisibleSegments: visibleSegmentIDs,
            segments: segments,
            expandedLadderIDs: expandedLadders,
            query: activeQuery
        )
    }

    private func question(_ row: EventQuestionMatrixAdapter.Row) -> some View {
        let scan = Self.scan(row)
        return VStack(alignment: .leading, spacing: 0) {
            if let heading = scan.heading {
                Text(heading)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 8)
                    .padding(.bottom, 2)
                    .accessibilityAddTraits(.isHeader)
            }
            ForEach(scan.lines) { line in
                ladderLine(line, question: row.label)
            }
            if row.options.isEmpty {
                Text("No quoted options right now")
                    .font(.footnote).foregroundStyle(.secondary)
                    .padding(.bottom, 6)
            }
            if row.offersMoreOptions {
                // Disclosure of incomplete coverage, not a nonfunctional button.
                Text("Additional options are not shown")
                    .font(.footnote).foregroundStyle(.secondary)
                    .padding(.bottom, 6)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func ladderLine(_ line: ScanLine, question: String) -> some View {
        let option = line.option
        let stacked = typeSize.isAccessibilitySize
        return Button {
            focus = nil
            returnSelection = option.selection
            open = OpenOption(id: option.selection)
        } label: {
            Group {
                if stacked {
                    VStack(alignment: .leading, spacing: 6) {
                        Text(line.label)
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        HStack(spacing: 10) {
                            bar(option.value)
                            Text(valueText(option.value))
                                .font(.subheadline.monospacedDigit().weight(.semibold))
                                .foregroundStyle(.primary)
                                .fixedSize(horizontal: true, vertical: true)
                                .contentTransition(.numericText())
                                .animation(reduceMotion ? nil : .easeOut(duration: 0.2), value: option.value)
                                .frame(minWidth: valueColumn, alignment: .trailing)
                        }
                    }
                } else {
                    HStack(alignment: .center, spacing: 10) {
                        Text(line.label)
                            .font(.subheadline)
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(width: labelColumn, alignment: .leading)
                        HStack(spacing: 10) {
                            bar(option.value)
                            Text(valueText(option.value))
                                .font(.subheadline.monospacedDigit().weight(.semibold))
                                .foregroundStyle(.primary)
                                .fixedSize(horizontal: true, vertical: true)
                                .contentTransition(.numericText())
                                .animation(reduceMotion ? nil : .easeOut(duration: 0.2), value: option.value)
                                .frame(minWidth: valueColumn, alignment: .trailing)
                        }
                    }
                }
            }
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .overlay(alignment: .bottom) {
            Rectangle().fill(Color.barTrack.opacity(0.4)).frame(height: 0.5)
        }
        .accessibilityLabel("\(question), \(option.label), \(valueText(option.value))")
        .accessibilityHint("Shows this exact line and its sources")
        .accessibilityFocused($focus, equals: .option(option.selection))
    }

    /// A quoted line draws its own chance; an unpriced one keeps an empty
    /// track; a decided one draws no bar (a filled bar pictures a live price).
    @ViewBuilder
    private func bar(_ value: EventQuestionMatrixAdapter.Value) -> some View {
        switch value {
        case .quoted(let probability):
            GeometryReader { geo in
                Capsule()
                    .fill(Color.secondary.opacity(0.1))
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(Color.accentColor.opacity(0.6))
                            .frame(width: max(2, geo.size.width * min(max(probability, 0), 1)))
                    }
            }
            .frame(height: 8)
            .accessibilityHidden(true)
        case .unavailable:
            Capsule()
                .fill(Color.secondary.opacity(0.1))
                .frame(maxWidth: .infinity, maxHeight: 8)
                .frame(height: 8)
                .accessibilityHidden(true)
        case .won, .lost:
            Spacer(minLength: 0)
        }
    }

    private func restoreFocus() {
        if let target = Self.focusReturnTarget(
            returnSelection, rows: rows, visibleRowIDs: visibleRowIDs
        ) {
            focus = .option(target)
        } else {
            focus = .heading
        }
    }

    /// The option focus returns to when the detail sheet closes, or nil for the
    /// section heading.
    ///
    /// #10830 — the option has to be in the LATEST payload (withdrawn → the
    /// heading, as before) AND on screen: a refresh can move its question to
    /// another family or past the browser's window, and focusing a row that is
    /// not drawn strands VoiceOver.
    static func focusReturnTarget(
        _ selection: QuestionMatrixSelection?,
        rows: [EventQuestionMatrixAdapter.Row],
        visibleRowIDs: Set<EventQuestionMatrixAdapter.RowID>
    ) -> QuestionMatrixSelection? {
        guard let selection,
              let row = rows.first(where: { $0.options.contains(where: { $0.selection == selection }) }),
              visibleRowIDs.contains(row.id) else { return nil }
        return selection
    }

    private func detail(_ selection: QuestionMatrixSelection) -> some View {
        NavigationStack {
            List {
                switch EventQuestionMatrixAdapter.detail(for: selection, in: matrix) {
                case .available(let resolved):
                    Section {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(resolved.row.label)
                                .font(.headline)
                                .fixedSize(horizontal: false, vertical: true)
                            if let period = resolved.row.period?.label, !period.isEmpty {
                                Text(period).font(.subheadline).foregroundStyle(.secondary)
                            }
                            Text(resolved.option.label).font(.subheadline)
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text(valueText(resolved.option.value))
                                    .font(.largeTitle.monospacedDigit())
                                    .fontWeight(.bold)
                                if case .quoted(let probability) = resolved.option.value,
                                   exactPercent(probability) != valueText(resolved.option.value) {
                                    Text(exactPercent(probability))
                                        .font(.subheadline.monospacedDigit())
                                        .foregroundStyle(.secondary)
                                }
                            }
                            SourceAgeText(observedAt: resolved.option.observedAt, prefix: "Updated")
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityElement(children: .combine)
                        .accessibilityIdentifier("game-series-question-summary")
                    }
                    if let comparison = resolved.comparison {
                        comparisonSection(comparison)
                    }
                    sourceSection(resolved.sources)
                case .unavailable:
                    Section {
                        Text("This market is unavailable")
                            .font(.headline)
                        Text("Its latest details are no longer available. Close to return to the markets.")
                            .font(.subheadline).foregroundStyle(.secondary)
                    }
                }
            }
            .navigationTitle(title)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { open = nil }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func comparisonSection(_ comparison: EventQuestionMatrixAdapter.Comparison) -> some View {
        Section(comparison.caption) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Before: \(exactPercent(comparison.baseline))")
                SourceAgeText(observedAt: comparison.baselineObservedAt)
                // The served delta belongs only beside its own Latest value;
                // it never annotates the published hero or a raw source quote.
                Text("Latest: \(exactPercent(comparison.latest)) · \(comparison.points.formatted(.number.sign(strategy: .always()).precision(.fractionLength(0...1)))) \(abs(comparison.points) == 1 ? "point" : "points")")
                SourceAgeText(observedAt: comparison.latestObservedAt)
            }
            .font(.subheadline.monospacedDigit())
            .accessibilityElement(children: .combine)
        }
    }

    private func sourceSection(_ sources: [EventQuestionMatrixAdapter.Source]) -> some View {
        Section("Sources") {
            if sources.isEmpty {
                Text("Source details unavailable").foregroundStyle(.secondary)
            }
            // Source entries are read-only disclosure; their index is never a
            // selection identity, and current rows are resolved anew each render.
            ForEach(Array(sources.enumerated()), id: \.offset) { _, source in
                let layout = typeSize.isAccessibilitySize
                    ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                    : AnyLayout(HStackLayout(alignment: .firstTextBaseline))
                layout {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(SourceLabels.label(for: source.source) ?? "Source")
                            .font(.subheadline.weight(.semibold))
                        if let side = source.side, !side.isEmpty {
                            Text("Raw source · \(side)").font(.caption).foregroundStyle(.secondary)
                        } else {
                            Text("Raw source").font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !typeSize.isAccessibilitySize { Spacer() }
                    VStack(alignment: typeSize.isAccessibilitySize ? .leading : .trailing, spacing: 2) {
                        if let probability = source.probability {
                            Text(exactPercent(probability)).font(.subheadline.monospacedDigit())
                        } else {
                            Text("Unavailable").foregroundStyle(.secondary)
                        }
                        SourceAgeText(observedAt: source.observedAt)
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
    }

    private func valueText(_ value: EventQuestionMatrixAdapter.Value) -> String {
        switch value {
        case .quoted(let probability):
            // Exact endpoint quotes remain quotes, not synthesized results.
            if probability == 0 { return "0%" }
            if probability == 1 { return "100%" }
            return formatProbability(probability)
        case .won: return "Won"
        case .lost: return "Lost"
        case .unavailable: return "Unavailable"
        }
    }

    private func exactPercent(_ probability: Double) -> String {
        if probability > 0 && probability < 0.00001 { return "<0.001%" }
        if probability < 1 && probability > 0.99999 { return ">99.999%" }
        return probability.formatted(.percent.precision(.fractionLength(0...3)))
    }

    @ViewBuilder
    private func ladderGroupView(_ group: EventQuestionMatrixLadderGroup10830.LadderGroup) -> some View {
        let hasQuery = !MarketBrowserLogic.terms(activeQuery).isEmpty
        let isExpanded = expandedLadders.contains(group.id)
        let shownRungs = group.visibleRungs(query: activeQuery, expanded: isExpanded)
        let chartPoints = group.chartPoints
        let columns = Array(
            repeating: GridItem(.flexible(), spacing: 6),
            count: EventQuestionMatrixLadderGroup10830.columnCount(forWidth: measuredWidth)
        )

        VStack(alignment: .leading, spacing: 8) {
            if !typeSize.isAccessibilitySize, chartPoints.count >= 2 {
                ladderChart(chartPoints, xAxisLabel: group.xAxisUnitLabel)
            }
            if shownRungs.isEmpty && hasQuery {
                Text("No matching lines.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 6)
            } else if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(shownRungs) { rung in
                        ladderLine(ScanLine(label: rung.row.label, option: rung.option), question: rung.row.label)
                    }
                }
            } else {
                LazyVGrid(columns: columns, spacing: 6) {
                    ForEach(shownRungs) { rung in
                        ladderTile(rung)
                    }
                }
            }
            if !hasQuery && group.rungs.count > EventQuestionMatrixLadderGroup10830.defaultVisibleTileLimit {
                let footerLabel = Text("\(shownRungs.count) of \(group.rungs.count) lines")
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                let toggleButton = Button {
                    if isExpanded {
                        expandedLadders.remove(group.id)
                    } else {
                        expandedLadders.insert(group.id)
                    }
                } label: {
                    Text(isExpanded ? "Show fewer" : "Show all \(group.rungs.count) lines")
                        .font(.caption.weight(.semibold))
                        .padding(.horizontal, typeSize.isAccessibilitySize ? 0 : 10)
                        .frame(minHeight: 44)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("ladder-group-toggle")

                if typeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 2) {
                        footerLabel
                        toggleButton
                    }
                } else {
                    HStack {
                        footerLabel
                        Spacer()
                        toggleButton
                    }
                }
            }
        }
        .padding(.vertical, 4)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func ladderChart(_ points: [EventQuestionMatrixLadderGroup10830.ChartPoint], xAxisLabel: String? = nil) -> some View {
        let lower = points.first?.bound ?? 0
        let rawUpper = points.last?.bound ?? lower
        let upper = rawUpper > lower ? rawUpper : lower + 1
        return VStack(spacing: 2) {
            Chart(points) { pt in
                AreaMark(
                    x: .value("Threshold", pt.bound),
                    yStart: .value("Baseline", 0.0),
                    yEnd: .value("Probability", pt.probability * 100.0)
                )
                .foregroundStyle(Color.accentColor.opacity(0.12))
                .interpolationMethod(.linear)

                LineMark(
                    x: .value("Threshold", pt.bound),
                    y: .value("Probability", pt.probability * 100.0)
                )
                .foregroundStyle(Color.accentColor)
                .lineStyle(StrokeStyle(lineWidth: 2, lineCap: .round, lineJoin: .round))
                .interpolationMethod(.linear)

                PointMark(
                    x: .value("Threshold", pt.bound),
                    y: .value("Probability", pt.probability * 100.0)
                )
                .symbolSize(16)
                .foregroundStyle(Color.accentColor)
            }
            .chartYScale(domain: 0...100)
            .chartXScale(domain: lower...upper)
            .chartYAxis {
                AxisMarks(values: [0, 50, 100]) { val in
                    AxisGridLine(stroke: StrokeStyle(lineWidth: 0.3))
                    AxisValueLabel {
                        if let pct = val.as(Int.self) {
                            Text("\(pct)%")
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }
            .chartXAxis {
                AxisMarks(values: .automatic(desiredCount: 4)) { _ in
                    AxisValueLabel()
                        .font(.caption2.monospacedDigit())
                }
            }
            .frame(height: 88)

            if let xAxisLabel, !xAxisLabel.isEmpty {
                Text(xAxisLabel)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .center)
            }
        }
        .accessibilityHidden(true)
    }

    private func ladderTile(_ rung: EventQuestionMatrixLadderGroup10830.Rung) -> some View {
        let option = rung.option
        return Button {
            focus = nil
            returnSelection = option.selection
            open = OpenOption(id: option.selection)
        } label: {
            VStack(alignment: .leading, spacing: 3) {
                Text(rung.row.label)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(valueText(option.value))
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                    .foregroundStyle(.primary)
                    .contentTransition(.numericText())
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.2), value: option.value)
                tileBar(option.value)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 6)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(Color.secondary.opacity(0.06))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .overlay(RoundedRectangle(cornerRadius: 8).stroke(Color.barTrack.opacity(0.45), lineWidth: 0.5))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(rung.row.label), \(option.label), \(valueText(option.value))")
        .accessibilityHint("Shows this exact line and its sources")
        .accessibilityFocused($focus, equals: .option(option.selection))
    }

    @ViewBuilder
    private func tileBar(_ value: EventQuestionMatrixAdapter.Value) -> some View {
        switch value {
        case .quoted(let probability):
            GeometryReader { geo in
                Capsule()
                    .fill(Color.secondary.opacity(0.12))
                    .overlay(alignment: .leading) {
                        Capsule()
                            .fill(Color.accentColor.opacity(0.65))
                            .frame(width: max(2, geo.size.width * min(max(probability, 0), 1)))
                    }
            }
            .frame(height: 3)
            .accessibilityHidden(true)
        case .unavailable:
            Capsule()
                .fill(Color.secondary.opacity(0.12))
                .frame(height: 3)
                .accessibilityHidden(true)
        case .won, .lost:
            Color.clear
                .frame(height: 3)
                .accessibilityHidden(true)
        }
    }
}

private struct LadderWidthKey10830: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}
