import SwiftUI

/// #10236 — during a live game, players' chances for one statistic in one
/// grid: a fixed player column, the stat's complete threshold columns browsed
/// sideways, and a tap on any number opening that exact question and its
/// sources. Close returns to the same statistic, row and scroll position,
/// because the matrix stays mounted underneath the sheet.
///
/// Drawn only from the server's typed `during_player_props`
/// (``DuringPlayerProps``); see ``EventPropsMatrixLayout`` for every rule.
struct EventPropsMatrixView: View {
    let props: DuringPlayerProps

    @State private var selection = EventPropsMatrixSelection()

    /// Rows and columns grow with Dynamic Type; the player column is capped so
    /// at least one whole numeric column stays on a 390pt screen at the largest
    /// accessibility size.
    @ScaledMetric(relativeTo: .subheadline) private var rowHeight: CGFloat = 46
    @ScaledMetric(relativeTo: .subheadline) private var cellWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .subheadline) private var nameWidth: CGFloat = 112
    private let maxNameWidth: CGFloat = 150

    var body: some View {
        let statKey = selection.resolvedStat(in: props)
        VStack(alignment: .leading, spacing: 10) {
            Text("Live Player Props")
                .font(.subheadline)
                .fontWeight(.semibold)
                .accessibilityAddTraits(.isHeader)

            if props.stats.count > 1 {
                statPicker(selected: statKey)
            }

            if let statKey, let grid = EventPropsMatrixLayout.grid(props, statKey: statKey) {
                matrix(grid)
                if !grid.unplaced.isEmpty { unplacedList(grid) }
                footer(grid)
            } else {
                Text("No questions for this stat right now")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .sheet(item: $selection.openQuestion) { open in
            EventPropsMatrixDetailView(open: open, props: props)
        }
    }

    // MARK: - Stat picker

    private func statPicker(selected: String?) -> some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 6) {
                ForEach(props.stats) { stat in
                    let isOn = stat.statKey == selected
                    Button {
                        selection.statKey = stat.statKey
                    } label: {
                        Text(stat.label)
                            .font(.caption)
                            .fontWeight(.semibold)
                            .foregroundStyle(isOn ? Color.white : Color.primary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 6)
                            .background(isOn ? Color.blue : Color.secondary.opacity(0.1))
                            .clipShape(Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(isOn ? .isSelected : [])
                }
            }
        }
    }

    // MARK: - Matrix

    private func matrix(_ grid: EventPropsMatrixLayout.Grid) -> some View {
        HStack(alignment: .top, spacing: 0) {
            // Fixed identity column.
            VStack(alignment: .leading, spacing: 4) {
                Text(grid.stat.label)
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                    .frame(height: 22, alignment: .leading)
                ForEach(grid.players) { player in
                    Text(player.label)
                        .font(.subheadline)
                        .lineLimit(2)
                        .minimumScaleFactor(0.85)
                        .frame(width: min(nameWidth, maxNameWidth), height: rowHeight, alignment: .leading)
                        .accessibilityHidden(true)
                }
            }
            .padding(.trailing, 6)

            // Threshold columns, browsed sideways. Keyed by stat so a new stat
            // starts at its first column; the same stat keeps its offset.
            ScrollView(.horizontal, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 4) {
                        ForEach(grid.columns, id: \.self) { count in
                            Text(columnLabel(count, grid: grid))
                                .font(.caption2)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                                .frame(width: cellWidth, height: 22)
                                .accessibilityHidden(true)
                        }
                    }
                    ForEach(grid.players) { player in
                        HStack(spacing: 4) {
                            ForEach(grid.columns, id: \.self) { count in
                                cell(player.cells[count], stat: grid.stat)
                            }
                        }
                    }
                }
            }
            .id(grid.stat.statKey)
        }
    }

    /// The column header is the server's own label for that count's over
    /// question ("2+"), read from the first row that has it.
    private func columnLabel(_ count: Int, grid: EventPropsMatrixLayout.Grid) -> String {
        grid.players.lazy.compactMap { $0.cells[count]?.predicate.label }.first ?? "\(count)+"
    }

    @ViewBuilder
    private func cell(_ row: DuringPropRow?, stat: DuringPropStat) -> some View {
        if let row {
            Button {
                selection.openQuestion = .init(row)
            } label: {
                VStack(spacing: 1) {
                    Text(EventPropsMatrixLayout.cellText(row))
                        .font(.subheadline.monospacedDigit())
                        .fontWeight(row.current.quotedProbability == nil ? .regular : .semibold)
                        .foregroundStyle(row.current.quotedProbability == nil ? Color.secondary : Color.primary)
                    if let change = EventPropsMatrixLayout.changeText(row) {
                        Text(change)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(width: cellWidth, height: rowHeight)
                .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.08)))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(EventPropsMatrixLayout.accessibilityLabel(row, stat: stat))
            .accessibilityHint("Shows this question and its sources")
        } else {
            // Not offered for this player: an empty slot, not a dash — a dash
            // means a question that exists without a current price.
            Color.clear
                .frame(width: cellWidth, height: rowHeight)
                .accessibilityHidden(true)
        }
    }

    // MARK: - Questions with no over cell

    private func unplacedList(_ grid: EventPropsMatrixLayout.Grid) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            ForEach(grid.unplaced) { row in
                Button {
                    selection.openQuestion = .init(row)
                } label: {
                    HStack {
                        Text("\(row.subject.label) · \(EventPropsMatrixLayout.question(row, stat: grid.stat))")
                            .font(.caption)
                        Spacer()
                        Text(EventPropsMatrixLayout.cellText(row))
                            .font(.caption.monospacedDigit())
                            .fontWeight(.semibold)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(EventPropsMatrixLayout.accessibilityLabel(row, stat: grid.stat))
            }
        }
    }

    // MARK: - Footer

    private func footer(_ grid: EventPropsMatrixLayout.Grid) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("\(grid.playerCount) \(grid.playerCount == 1 ? "player" : "players") · \(grid.questionCount) \(grid.questionCount == 1 ? "question" : "questions")")
            if grid.showsChange {
                Text("+/\u{2212} is the change since the pregame price, in points")
            }
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
    }
}

/// One question, exactly: its current chance, where it comes from, the
/// pregame comparison when the server proved one, and the other side when the
/// server paired one. A question the server stops carrying reads as
/// unavailable here; the sheet never moves to a sibling.
struct EventPropsMatrixDetailView: View {
    let open: EventPropsMatrixSelection.OpenQuestion
    let props: DuringPlayerProps
    @Environment(\.dismiss) private var dismiss

    private var stat: DuringPropStat? { props.stats.first { $0.statKey == open.statKey } }

    var body: some View {
        NavigationStack {
            List {
                if let row = EventPropsMatrixSelection.resolve(open, in: props) {
                    summary(row)
                    sources(row)
                    if let other = EventPropsMatrixLayout.otherSide(of: row, in: props) {
                        Section("Other side") {
                            HStack {
                                Text(EventPropsMatrixLayout.question(other, stat: stat))
                                Spacer()
                                Text(EventPropsMatrixLayout.cellText(other))
                                    .monospacedDigit()
                                    .fontWeight(.semibold)
                            }
                            .accessibilityElement(children: .combine)
                        }
                    }
                } else {
                    Text("This question isn't being offered right now.")
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle(EventPropsMatrixSelection.resolve(open, in: props)?.subject.label ?? "Player prop")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Close") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }

    private func summary(_ row: DuringPropRow) -> some View {
        Section {
            VStack(alignment: .leading, spacing: 6) {
                Text(EventPropsMatrixLayout.question(row, stat: stat))
                    .font(.headline)
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(EventPropsMatrixLayout.cellText(row))
                        .font(.largeTitle.monospacedDigit())
                        .fontWeight(.bold)
                    if let p = row.current.quotedProbability {
                        Text(EventPropsMatrixLayout.exactPercent(p))
                            .font(.subheadline.monospacedDigit())
                            .foregroundStyle(.secondary)
                    }
                }
                if row.current.isActualOnly, let actual = row.result?.actual {
                    Text("Final: \(actual.formatted(.number.precision(.fractionLength(0...1))))")
                        .font(.subheadline)
                }
                if let basis = EventPropsMatrixLayout.basisText(row) {
                    Text(basis).font(.subheadline).foregroundStyle(.secondary)
                }
                if let age = SourceAge.format(row.current.observedAt) {
                    Text("Updated \(age)").font(.caption).foregroundStyle(.secondary)
                }
            }
            .accessibilityElement(children: .combine)
            if row.current.quotedProbability != nil {
                comparison(row)
            }
        }
    }

    @ViewBuilder
    private func comparison(_ row: DuringPropRow) -> some View {
        if let c = row.comparison, c.isComparable, let base = c.baseline?.probability, base.isFinite,
           let now = row.current.quotedProbability {
            HStack {
                Text("Pregame \(formatProbability(base))")
                Image(systemName: "arrow.right").font(.caption).accessibilityHidden(true)
                Text("now \(formatProbability(now))")
                Spacer()
                if let change = EventPropsMatrixLayout.changeText(row) {
                    Text(change).monospacedDigit().foregroundStyle(.secondary)
                }
            }
            .font(.subheadline)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Pregame \(EventPropsMatrixLayout.exactPercent(base)), now \(EventPropsMatrixLayout.exactPercent(now))")
        } else {
            Text("No pregame comparison")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        }
    }

    private func sources(_ row: DuringPropRow) -> some View {
        Section("Sources") {
            ForEach(Array(row.contributors.enumerated()), id: \.offset) { _, c in
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        if let name = SourceLabels.label(for: c.source) {
                            Text(name).font(.subheadline).fontWeight(.semibold)
                        }
                        if let outcome = c.outcomeName, !outcome.isEmpty {
                            Text(outcome).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    Spacer()
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(EventPropsMatrixLayout.exactPercent(c.probability))
                            .font(.subheadline.monospacedDigit())
                        if let age = SourceAge.format(c.observedAt) {
                            Text(age).font(.caption2).foregroundStyle(.secondary)
                        }
                    }
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}
