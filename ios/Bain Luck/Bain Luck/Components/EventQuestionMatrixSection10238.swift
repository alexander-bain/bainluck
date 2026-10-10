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
    @AccessibilityFocusState private var focus: Focus?
    @Environment(\.dynamicTypeSize) private var typeSize
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var rows: [EventQuestionMatrixAdapter.Row] {
        EventQuestionMatrixAdapter.rows(in: matrix, scope: scope)
    }
    private var title: String { scope == .game ? "Game questions" : "Series questions" }

    var body: some View {
        // Keep a reachable fallback while an open question is withdrawn.
        // A never-populated section resolves to no view at all, so the page's
        // stack spends no spacing on it (an always-present empty VStack cost
        // every event page 12pt per section). @State lives on this view's
        // identity, not its content, so selection survives either way.
        if !rows.isEmpty || open != nil || returnSelection != nil {
            VStack(alignment: .leading, spacing: 12) {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityFocused($focus, equals: .heading)
                if rows.isEmpty {
                    Text("Questions are unavailable right now")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                // #10830 — a bounded, searchable window by family (web's
                // compact game-question browser, #10809). An NFL page serves
                // ~200 questions; drawn whole they were ~70,000 pt of scroll.
                // Each card is still `question(_:)`, and selection still
                // resolves against the latest payload.
                MarketBrowserView(
                    label: title,
                    items: rows,
                    group: Self.family,
                    searchText: Self.searchText,
                    pageSize: Self.pageSize,
                    searchPrompt: "questions"
                ) { row in
                    question(row)
                        .padding(.bottom, 10)
                }
            }
            .sheet(item: $open, onDismiss: restoreFocus) { selected in
                detail(selected.id)
            }
        }
    }

    // MARK: - Browsing (#10830)

    /// Question cards are tall, so a page of them is shorter than a page of rows.
    static let pageSize = 8

    /// The family a question is browsed under, read from its typed kind and
    /// its own words. Navigation only: every question keeps its own card and
    /// options, and one the rules do not recognise is "More questions" rather
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
        return "More questions"
    }

    /// What a search over one question reads: its words, its period and every
    /// option's name.
    static func searchText(_ row: EventQuestionMatrixAdapter.Row) -> String {
        ([row.label, row.period?.label ?? ""] + row.options.map(\.label)).joined(separator: " ")
    }

    private func question(_ row: EventQuestionMatrixAdapter.Row) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(row.label)
                .font(.subheadline.weight(.semibold))
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let period = row.period?.label, !period.isEmpty {
                Text(period).font(.caption).foregroundStyle(.secondary)
            }
            // Small named sets (including a three-way draw) sit side by side.
            // Larger sets and accessibility sizes keep full labels in a list.
            if row.options.count <= 3 && !typeSize.isAccessibilitySize {
                HStack(alignment: .top, spacing: 6) {
                    ForEach(row.options) { option in
                        optionButton(option, question: row.label, compact: true)
                    }
                }
            } else {
                VStack(spacing: 6) {
                    ForEach(row.options) { option in
                        optionButton(option, question: row.label, compact: false)
                    }
                }
            }
            if row.options.isEmpty {
                Text("No quoted options right now")
                    .font(.caption).foregroundStyle(.secondary)
            }
            if row.offersMoreOptions {
                // Disclosure of incomplete coverage, not a nonfunctional button.
                Text("Additional options are not shown")
                    .font(.caption).foregroundStyle(.secondary)
            }
        }
        .padding(14)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 14))
    }

    private func optionButton(
        _ option: EventQuestionMatrixAdapter.Option, question: String, compact: Bool
    ) -> some View {
        Button {
            focus = nil
            returnSelection = option.selection
            open = OpenOption(id: option.selection)
        } label: {
            let layout = compact || typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 5))
                : AnyLayout(HStackLayout(alignment: .firstTextBaseline, spacing: 10))
            layout {
                Text(option.label)
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
                if !compact && !typeSize.isAccessibilitySize { Spacer(minLength: 4) }
                Text(valueText(option.value))
                    .font(.subheadline.monospacedDigit().weight(.semibold))
                    .contentTransition(.numericText())
                    .animation(reduceMotion ? nil : .easeOut(duration: 0.2), value: option.value)
            }
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .padding(8)
            .background(Color.secondary.opacity(0.08))
            .clipShape(RoundedRectangle(cornerRadius: 8))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(question), \(option.label), \(valueText(option.value))")
        .accessibilityHint("Shows this exact question and its sources")
        .accessibilityFocused($focus, equals: .option(option.selection))
    }

    private func restoreFocus() {
        if let target = returnSelection,
           rows.contains(where: { $0.options.contains(where: { $0.selection == target }) }) {
            focus = .option(target)
        } else {
            focus = .heading
        }
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
                            if let age = SourceAge.format(resolved.option.observedAt) {
                                Text("Updated \(age)").font(.caption).foregroundStyle(.secondary)
                            }
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
                        Text("This question is unavailable")
                            .font(.headline)
                        Text("Its latest details are no longer available. Close to return to the questions.")
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
                if let age = SourceAge.format(comparison.baselineObservedAt) {
                    Text(age).font(.caption).foregroundStyle(.secondary)
                }
                // The served delta belongs only beside its own Latest value;
                // it never annotates the published hero or a raw source quote.
                Text("Latest: \(exactPercent(comparison.latest)) · \(comparison.points.formatted(.number.sign(strategy: .always()).precision(.fractionLength(0...1)))) \(abs(comparison.points) == 1 ? "point" : "points")")
                if let age = SourceAge.format(comparison.latestObservedAt) {
                    Text(age).font(.caption).foregroundStyle(.secondary)
                }
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
                        if let age = SourceAge.format(source.observedAt) {
                            Text(age).font(.caption).foregroundStyle(.secondary)
                        }
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
}
