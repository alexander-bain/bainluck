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
        VStack(alignment: .leading, spacing: 12) {
            // Keep a reachable fallback while an open question is withdrawn.
            // A never-populated optional section otherwise occupies no space.
            if !rows.isEmpty || open != nil || returnSelection != nil {
                Text(title)
                    .font(.subheadline.weight(.semibold))
                    .accessibilityAddTraits(.isHeader)
                    .accessibilityFocused($focus, equals: .heading)
                if rows.isEmpty {
                    Text("Questions are unavailable right now")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
                ForEach(rows) { row in
                    question(row)
                }
            }
        }
        .sheet(item: $open, onDismiss: restoreFocus) { selected in
            detail(selected.id)
        }
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
                        Text(resolved.row.label).font(.headline)
                        if let period = resolved.row.period?.label, !period.isEmpty {
                            Text(period).font(.subheadline).foregroundStyle(.secondary)
                        }
                        Text(resolved.option.label).font(.subheadline)
                        Text(valueText(resolved.option.value))
                            .font(.largeTitle.monospacedDigit().weight(.semibold))
                        if case .quoted(let probability) = resolved.option.value {
                            Text(exactPercent(probability))
                                .font(.caption).foregroundStyle(.secondary)
                        }
                        if let age = SourceAge.format(resolved.option.observedAt) {
                            Text("Observed \(age)").font(.caption).foregroundStyle(.secondary)
                        }
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
                ToolbarItem(placement: .confirmationAction) {
                    Button("Close") { open = nil }
                }
            }
        }
    }

    private func comparisonSection(_ comparison: EventQuestionMatrixAdapter.Comparison) -> some View {
        Section(comparison.caption) {
            VStack(alignment: .leading, spacing: 8) {
                Text("Before: \(exactPercent(comparison.baseline))")
                if let age = SourceAge.format(comparison.baselineObservedAt) {
                    Text("Observed \(age)").font(.caption).foregroundStyle(.secondary)
                }
                // The served delta belongs only beside its own Latest value;
                // it never annotates the published hero or a raw source quote.
                Text("Latest: \(exactPercent(comparison.latest)) · \(comparison.points.formatted(.number.sign(strategy: .always()).precision(.fractionLength(0...1)))) pp")
                if let age = SourceAge.format(comparison.latestObservedAt) {
                    Text("Observed \(age)").font(.caption).foregroundStyle(.secondary)
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
                VStack(alignment: .leading, spacing: 4) {
                    Text(SourceLabels.label(for: source.source) ?? "Source")
                        .font(.subheadline.weight(.semibold))
                    if let side = source.side, !side.isEmpty {
                        Text("Raw source · \(side)").font(.caption).foregroundStyle(.secondary)
                    } else {
                        Text("Raw source").font(.caption).foregroundStyle(.secondary)
                    }
                    if let probability = source.probability {
                        Text(exactPercent(probability)).font(.subheadline.monospacedDigit())
                    } else {
                        Text("Unavailable").foregroundStyle(.secondary)
                    }
                    if let age = SourceAge.format(source.observedAt) {
                        Text("Observed \(age)").font(.caption).foregroundStyle(.secondary)
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
