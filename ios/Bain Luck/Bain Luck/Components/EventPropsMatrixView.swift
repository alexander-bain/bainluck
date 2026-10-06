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
    var onDetailPresentationChanged: (Bool) -> Void = { _ in }
    var onMatrixUnavailableDismissed: () -> Void = {}

    @State private var selection = EventPropsMatrixSelection()
    @State private var returnQuestion: EventPropsMatrixSelection.OpenQuestion?
    @AccessibilityFocusState(for: .voiceOver) private var accessibilityFocus: FocusTarget?

    private enum FocusTarget: Hashable {
        case question(EventPropsMatrixSelection.OpenQuestion)
        case header
    }

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
                .accessibilityFocused($accessibilityFocus, equals: .header)

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
        .sheet(item: $selection.openQuestion, onDismiss: restoreQuestionFocus) { open in
            EventPropsMatrixDetailView(open: open, props: props)
        }
    }

    // Capture the exact initiating question independently of sheet state:
    // SwiftUI clears openQuestion before onDismiss runs. Prices and indices
    // never identify the focus destination.
    private func openQuestion(_ row: DuringPropRow) {
        accessibilityFocus = nil
        onDetailPresentationChanged(true)
        returnQuestion = selection.open(row)
    }

    private func restoreQuestionFocus() {
        defer {
            returnQuestion = nil
            onDetailPresentationChanged(false)
        }
        guard let open = returnQuestion else {
            accessibilityFocus = .header
            return
        }
        switch EventPropsMatrixLayout.returnFocus(after: open, selection: selection, in: props) {
        case .question(let question):
            accessibilityFocus = .question(question)
        case .header:
            accessibilityFocus = .header
        case .matrixWithdrawn:
            // The page retains this presentation host with an empty payload
            // until dismissal; it owns the destination once it removes us.
            accessibilityFocus = nil
            onMatrixUnavailableDismissed()
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
                openQuestion(row)
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
            .accessibilityFocused($accessibilityFocus, equals: .question(.init(row)))
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
                    openQuestion(row)
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
                .accessibilityFocused($accessibilityFocus, equals: .question(.init(row)))
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
    @Environment(\.dynamicTypeSize) private var typeSize

    private var stat: DuringPropStat? { props.stats.first { $0.statKey == open.statKey } }

    var body: some View {
        NavigationStack {
            List {
                if let row = EventPropsMatrixSelection.resolve(open, in: props) {
                    summary(row)
                    sources(row)
                    if let other = EventPropsMatrixLayout.otherSide(of: row, in: props) {
                        Section("Other side") {
                            // Stacked at accessibility sizes, like Sources: side
                            // by side at AX5 the question hyphenated "strike-outs".
                            let layout = typeSize.isAccessibilitySize
                                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                                : AnyLayout(HStackLayout())
                            layout {
                                Text(EventPropsMatrixLayout.question(other, stat: stat))
                                if !typeSize.isAccessibilitySize { Spacer() }
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
                // Accessibility sizes stack name over number: side by side at
                // AX5 the source name hyphenated mid-word ("Polymar-ket").
                let layout = typeSize.isAccessibilitySize
                    ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                    : AnyLayout(HStackLayout(alignment: .firstTextBaseline))
                layout {
                    VStack(alignment: .leading, spacing: 2) {
                        if let name = SourceLabels.label(for: c.source) {
                            Text(name).font(.subheadline).fontWeight(.semibold)
                        }
                        if let outcome = c.outcomeName, !outcome.isEmpty {
                            Text(outcome).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !typeSize.isAccessibilitySize { Spacer() }
                    VStack(alignment: typeSize.isAccessibilitySize ? .leading : .trailing, spacing: 2) {
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

// MARK: - After (#10237)

/// #10237 — after a finished game, each player's saved pregame chance for
/// every threshold beside ESPN's official final count, stated once per player,
/// and the server's own Reached / Below mark. Same grid grammar as the During
/// matrix: a fixed player column, threshold columns browsed sideways, a tap
/// opening that exact question. Drawn only from ``AfterPlayerProps``; every
/// word comes from ``PropExpectationActualDisplay``.
enum AfterPropsMatrixLayout {
    struct PlayerRow: Equatable, Identifiable {
        var id: String { subjectKey }
        let subjectKey: String
        let label: String
        /// The player's one final count for this stat (nil when the server
        /// carries none) — drawn in the player column, never per threshold.
        let actual: AfterPropActual?
        let cells: [Int: AfterPropQuestion]
    }

    struct Grid: Equatable {
        let stat: AfterPropStat
        /// The main rows' thresholds only, so a threshold no quoted player
        /// has never draws an empty column.
        let columns: [Int]
        /// Players with at least one saved pregame chance for THIS stat and
        /// period, in server question order (first appearance), never re-ranked.
        let players: [PlayerRow]
        /// Every other player of this stat, same order, behind one counted
        /// disclosure — reachable, never dropped, never given a chance.
        let withoutChance: [PlayerRow]
        let questionCount: Int
    }

    /// Where an opened question sits in the grid now.
    enum Placement: Equatable { case main, withoutChance, absent }

    /// The payload the page may draw, or nil: an unknown contract or an empty
    /// question list keeps whatever the page drew before.
    static func drawable(_ props: AfterPlayerProps?) -> AfterPlayerProps? {
        guard let props, props.isSupported, !props.questions.isEmpty else { return nil }
        return props
    }

    /// v1 emits only `count_at_least` questions; any other shape is not drawn
    /// here (it was never typed for After) rather than guessed into a column.
    static func grid(_ props: AfterPlayerProps, statKey: String) -> Grid? {
        guard let stat = props.stat(statKey) else { return nil }
        let questions = props.questions.filter { $0.statKey == statKey && $0.predicate.isAtLeast }
        guard !questions.isEmpty else { return nil }
        var order: [String] = []
        var labels: [String: String] = [:]
        var actuals: [String: AfterPropActual] = [:]
        var cells: [String: [Int: AfterPropQuestion]] = [:]
        for q in questions {
            let subject = q.subject.key
            if labels[subject] == nil {
                order.append(subject)
                labels[subject] = q.subject.label
                actuals[subject] = props.actual(for: q)
            }
            if cells[subject]?[q.predicate.count] == nil {
                cells[subject, default: [:]][q.predicate.count] = q
            }
        }
        let rows = order.map {
            PlayerRow(subjectKey: $0, label: labels[$0] ?? $0, actual: actuals[$0], cells: cells[$0] ?? [:])
        }
        let quoted = rows.filter { hasSavedChance($0, stat: stat) }
        return Grid(
            stat: stat,
            columns: Set(quoted.flatMap { $0.cells.keys }).sorted(),
            players: quoted,
            withoutChance: rows.filter { !hasSavedChance($0, stat: stat) },
            questionCount: rows.reduce(0) { $0 + $1.cells.count }
        )
    }

    /// A row earns the main grid with one usable saved chance (a finite 0
    /// counts) on a question of the selected stat AND its period. A final
    /// count or a Reached / Below mark never earns it.
    static func hasSavedChance(_ row: PlayerRow, stat: AfterPropStat) -> Bool {
        row.cells.values.contains {
            $0.statKey == stat.statKey && $0.periodKey == stat.periodKey && $0.expectation.savedProbability != nil
        }
    }

    /// The statistic drawn before the reader picks one: the server's first
    /// with a saved chance, else the server's first. A choice always wins.
    static func defaultStat(_ props: AfterPlayerProps) -> String? {
        props.stats.first { grid(props, statKey: $0.statKey).map { !$0.players.isEmpty } ?? false }?.statKey
            ?? props.stats.first?.statKey
    }

    static func placement(of open: EventPropsMatrixSelection.OpenQuestion, in grid: Grid) -> Placement {
        func holds(_ rows: [PlayerRow]) -> Bool {
            rows.contains { $0.cells.values.contains { EventPropsMatrixSelection.OpenQuestion($0) == open } }
        }
        guard grid.stat.statKey == open.statKey else { return .absent }
        if holds(grid.players) { return .main }
        if holds(grid.withoutChance) { return .withoutChance }
        return .absent
    }

    static func disclosureLabel(count: Int, expanded: Bool) -> String {
        "\(expanded ? "Hide" : "Show") \(count) \(count == 1 ? "player" : "players") without a pregame chance"
    }

    /// The legacy `player_props` the After grid does not already draw — the
    /// server's contributor-outcome link, never a name match (as #10236).
    static func untypedPlayerProps(
        _ playerProps: [GameMarketPlayerProp],
        typed props: AfterPlayerProps?
    ) -> [GameMarketPlayerProp] {
        guard let props = drawable(props) else { return playerProps }
        let typedOutcomeIds = Set(props.questions.flatMap { $0.contributorOutcomeIds ?? [] })
        return playerProps.filter { prop in
            let ids = prop.contributorOutcomeIds ?? []
            return ids.isEmpty || !ids.contains(where: typedOutcomeIds.contains)
        }
    }

    /// The question the reader opened, exactly, or nil — never a sibling.
    static func resolve(_ open: EventPropsMatrixSelection.OpenQuestion, in props: AfterPlayerProps) -> AfterPropQuestion? {
        props.questions.first {
            $0.questionKey == open.questionKey && $0.subject.key == open.subjectKey && $0.statKey == open.statKey
        }
    }
}

extension EventPropsMatrixSelection.OpenQuestion {
    init(_ question: AfterPropQuestion) {
        questionKey = question.questionKey
        subjectKey = question.subject.key
        statKey = question.statKey
    }
}

struct AfterPropsMatrixView: View {
    let props: AfterPlayerProps
    var onDetailPresentationChanged: (Bool) -> Void = { _ in }
    var onMatrixUnavailableDismissed: () -> Void = {}

    @State private var statKey: String?
    /// Stats whose players-without-a-chance disclosure the reader opened. It
    /// stays open under the detail sheet so Close lands on the same option.
    @State private var expandedStats: Set<String> = []
    @State private var openQuestion: EventPropsMatrixSelection.OpenQuestion?
    @State private var returnQuestion: EventPropsMatrixSelection.OpenQuestion?
    @AccessibilityFocusState(for: .voiceOver) private var accessibilityFocus: FocusTarget?

    private enum FocusTarget: Hashable {
        case question(EventPropsMatrixSelection.OpenQuestion)
        case header
    }

    @ScaledMetric(relativeTo: .subheadline) private var baseRowHeight: CGFloat = 46
    @ScaledMetric(relativeTo: .caption2) private var headerHeight: CGFloat = 22
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .subheadline) private var cellWidth: CGFloat = 58
    @ScaledMetric(relativeTo: .subheadline) private var nameWidth: CGFloat = 112
    private let maxNameWidth: CGFloat = 150
    /// At accessibility sizes a threshold cell is sized to what it holds — a
    /// saved chance over "Reached"/"Below" — not to the subheadline-scaled
    /// default, which left 150pt for the name and broke "Christian" mid-word.
    @ScaledMetric(relativeTo: .caption2) private var accessibilityCellWidth: CGFloat = 36
    @State private var matrixWidth: CGFloat = 0

    /// Accessibility sizes give each row room for a two-line name over a
    /// two-line count: the count is the fact this grid exists to state, so it
    /// wraps rather than truncating to "2 home…".
    private var rowHeight: CGFloat { typeSize.isAccessibilitySize ? baseRowHeight * 2 : baseRowHeight }
    /// The statistic's name heads the player column on two lines at
    /// accessibility sizes ("Home / Runs"), never "Home…"; the threshold
    /// headers share the height so the rows stay aligned.
    private var columnHeaderHeight: CGFloat { typeSize.isAccessibilitySize ? headerHeight * 2 : headerHeight }
    private var thresholdWidth: CGFloat {
        typeSize.isAccessibilitySize ? min(cellWidth, accessibilityCellWidth) : cellWidth
    }
    /// The player column takes what one whole threshold column leaves, so a
    /// name wraps by word; until the width is known it keeps the default cap.
    private var playerColumnWidth: CGFloat {
        let capped = min(nameWidth, maxNameWidth)
        guard typeSize.isAccessibilitySize, matrixWidth > 0 else { return capped }
        return min(nameWidth, max(capped, matrixWidth - 6 - thresholdWidth))
    }

    /// The reader's chosen statistic, else the server's first one with a
    /// saved chance. A chosen one that leaves stays chosen (and shows nothing)
    /// rather than switching.
    private var resolvedStat: String? { statKey ?? AfterPropsMatrixLayout.defaultStat(props) }

    var body: some View {
        let statKey = resolvedStat
        VStack(alignment: .leading, spacing: 10) {
            Text("Player Props")
                .font(.subheadline)
                .fontWeight(.semibold)
                .accessibilityAddTraits(.isHeader)
                .accessibilityFocused($accessibilityFocus, equals: .header)

            if props.stats.count > 1 {
                statPicker(selected: statKey)
            }

            if let statKey, let grid = AfterPropsMatrixLayout.grid(props, statKey: statKey) {
                if !grid.players.isEmpty { matrix(grid) }
                if !grid.withoutChance.isEmpty { withoutChanceSection(grid) }
                footer(grid)
            } else {
                Text("No questions for this stat")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(16)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16))
        .sheet(item: $openQuestion, onDismiss: restoreQuestionFocus) { open in
            AfterPropsDetailView(open: open, props: props)
        }
    }

    private func open(_ question: AfterPropQuestion) {
        accessibilityFocus = nil
        onDetailPresentationChanged(true)
        let open = EventPropsMatrixSelection.OpenQuestion(question)
        // Opening pins the statistic, so a reordered payload cannot swap the
        // background (and the Close destination) under the open detail.
        statKey = open.statKey
        returnQuestion = open
        openQuestion = open
    }

    private func restoreQuestionFocus() {
        defer {
            returnQuestion = nil
            onDetailPresentationChanged(false)
        }
        guard let open = returnQuestion else {
            accessibilityFocus = .header
            return
        }
        if props.questions.isEmpty {
            accessibilityFocus = nil
            onMatrixUnavailableDismissed()
            return
        }
        let grid = resolvedStat == open.statKey ? AfterPropsMatrixLayout.grid(props, statKey: open.statKey) : nil
        switch grid.map({ AfterPropsMatrixLayout.placement(of: open, in: $0) }) ?? .absent {
        case .main:
            accessibilityFocus = .question(open)
        case .withoutChance:
            // The exact option, with its disclosure open — opened again if a
            // refresh moved the question there while the detail was up.
            if expandedStats.contains(open.statKey) {
                accessibilityFocus = .question(open)
            } else {
                expandedStats.insert(open.statKey)
                DispatchQueue.main.async { accessibilityFocus = .question(open) }
            }
        case .absent:
            accessibilityFocus = .header
        }
    }

    /// At accessibility sizes the pills stack when one row cannot hold them,
    /// so the selected one is never cut at the card's edge.
    @ViewBuilder
    private func statPicker(selected: String?) -> some View {
        if typeSize.isAccessibilitySize {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 6) { statPills(selected: selected) }
                VStack(alignment: .leading, spacing: 6) { statPills(selected: selected) }
            }
        } else {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 6) { statPills(selected: selected) }
            }
        }
    }

    private func statPills(selected: String?) -> some View {
        ForEach(props.stats) { stat in
            let isOn = stat.statKey == selected
            Button {
                statKey = stat.statKey
            } label: {
                Text(stat.label)
                    .font(.caption)
                    .fontWeight(.semibold)
                    .foregroundStyle(isOn ? Color.white : Color.primary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 6)
                    .background(isOn ? Color.blue : Color.secondary.opacity(0.1))
                    .clipShape(Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(isOn ? .isSelected : [])
        }
    }

    private func matrix(_ grid: AfterPropsMatrixLayout.Grid) -> some View {
        HStack(alignment: .top, spacing: 0) {
            VStack(alignment: .leading, spacing: 4) {
                Text(grid.stat.label)
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                    .lineLimit(typeSize.isAccessibilitySize ? 2 : nil)
                    .minimumScaleFactor(typeSize.isAccessibilitySize ? 0.8 : 1)
                    .frame(width: typeSize.isAccessibilitySize ? playerColumnWidth : nil,
                           height: columnHeaderHeight, alignment: .leading)
                ForEach(grid.players) { player in
                    playerCell(player, stat: grid.stat)
                }
            }
            .padding(.trailing, 6)

            ScrollView(.horizontal, showsIndicators: false) {
                VStack(alignment: .leading, spacing: 4) {
                    HStack(spacing: 4) {
                        ForEach(grid.columns, id: \.self) { count in
                            Text(grid.players.lazy.compactMap { $0.cells[count]?.predicate.label }.first ?? "\(count)+")
                                .font(.caption2)
                                .fontWeight(.semibold)
                                .foregroundStyle(.secondary)
                                .frame(width: thresholdWidth, height: columnHeaderHeight)
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
        .onGeometryChange(for: CGFloat.self) { $0.size.width } action: { matrixWidth = $0 }
    }

    /// Name over the player's one final count. The count is spoken here once,
    /// so no cell repeats it.
    private func playerCell(_ player: AfterPropsMatrixLayout.PlayerRow, stat: AfterPropStat) -> some View {
        let actual = PropExpectationActualDisplay.actual(player.actual, stat: stat)
        return VStack(alignment: .leading, spacing: 1) {
            // A long surname ("Cronenworth") fits its line whole by shrinking
            // at accessibility sizes, rather than truncating to "Cronenw…".
            Text(player.label)
                .font(.subheadline)
                .lineLimit(2)
                .minimumScaleFactor(typeSize.isAccessibilitySize ? 0.6 : 0.85)
            Text(actual.countText ?? absentProbabilityMarker)
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
                .lineLimit(2)
                .minimumScaleFactor(0.85)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(width: playerColumnWidth, height: rowHeight, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(actual.countText.map { "\(player.label), final \($0)" } ?? "\(player.label), final count \(actual.stateText.lowercased())")
    }

    @ViewBuilder
    private func cell(_ question: AfterPropQuestion?, stat: AfterPropStat) -> some View {
        if let question {
            let expectation = PropExpectationActualDisplay.expectation(question.expectation)
            let mark = PropExpectationActualDisplay.mark(question, actual: props.actual(for: question))
            Button {
                open(question)
            } label: {
                VStack(spacing: 1) {
                    Text(expectation.valueText ?? absentProbabilityMarker)
                        .font(.subheadline.monospacedDigit())
                        .fontWeight(expectation.valueText == nil ? .regular : .semibold)
                        .foregroundStyle(expectation.valueText == nil ? Color.secondary : Color.primary)
                    if mark != .unknown {
                        Text(PropExpectationActualDisplay.markText(mark))
                            .font(.caption2)
                            .fontWeight(mark == .reached ? .semibold : .regular)
                            .foregroundStyle(mark == .reached ? Color.green : Color.secondary)
                    }
                }
                .lineLimit(1)
                .minimumScaleFactor(0.8)
                .frame(width: thresholdWidth, height: rowHeight)
                .background(RoundedRectangle(cornerRadius: 8)
                    .fill(mark == .reached ? Color.green.opacity(0.12) : Color.secondary.opacity(0.08)))
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(PropExpectationActualDisplay.accessibilityLabel(
                question, actual: props.actual(for: question), stat: stat))
            .accessibilityHint("Shows this question and its sources")
            .accessibilityFocused($accessibilityFocus, equals: .question(.init(question)))
        } else {
            Color.clear
                .frame(width: thresholdWidth, height: rowHeight)
                .accessibilityHidden(true)
        }
    }

    // MARK: - Players without a pregame chance

    /// One counted, collapsed disclosure for every player of this stat with no
    /// saved chance: each keeps its final count once and every question stays
    /// one tap from its exact detail.
    private func withoutChanceSection(_ grid: AfterPropsMatrixLayout.Grid) -> some View {
        let expanded = expandedStats.contains(grid.stat.statKey)
        return VStack(alignment: .leading, spacing: 8) {
            Button {
                if expanded { expandedStats.remove(grid.stat.statKey) } else { expandedStats.insert(grid.stat.statKey) }
            } label: {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text(AfterPropsMatrixLayout.disclosureLabel(count: grid.withoutChance.count, expanded: expanded))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .multilineTextAlignment(.leading)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                    Image(systemName: expanded ? "chevron.up" : "chevron.down")
                        .font(.caption2)
                        .accessibilityHidden(true)
                }
                .foregroundStyle(Color.blue)
                .frame(minHeight: 32)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityIdentifier("after-props-without-chance-disclosure")
            if expanded {
                ForEach(grid.withoutChance) { player in
                    withoutChancePlayer(player, stat: grid.stat)
                }
            }
        }
    }

    private func withoutChancePlayer(_ player: AfterPropsMatrixLayout.PlayerRow, stat: AfterPropStat) -> some View {
        let actual = PropExpectationActualDisplay.actual(player.actual, stat: stat)
        let nameLayout = typeSize.isAccessibilitySize
            ? AnyLayout(VStackLayout(alignment: .leading, spacing: 2))
            : AnyLayout(HStackLayout(alignment: .firstTextBaseline))
        return VStack(alignment: .leading, spacing: 4) {
            nameLayout {
                Text(player.label)
                    .font(.subheadline)
                    .fixedSize(horizontal: false, vertical: true)
                if !typeSize.isAccessibilitySize { Spacer() }
                Text(actual.countText ?? absentProbabilityMarker)
                    .font(.caption.monospacedDigit())
                    .foregroundStyle(.secondary)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(actual.countText.map { "\(player.label), final \($0)" } ?? "\(player.label), final count \(actual.stateText.lowercased())")
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 4) { withoutChanceOptions(player, stat: stat) }
                VStack(alignment: .leading, spacing: 4) { withoutChanceOptions(player, stat: stat) }
            }
        }
    }

    private func withoutChanceOptions(_ player: AfterPropsMatrixLayout.PlayerRow, stat: AfterPropStat) -> some View {
        ForEach(player.cells.keys.sorted(), id: \.self) { count in
            if let question = player.cells[count] {
                let actual = props.actual(for: question)
                let mark = PropExpectationActualDisplay.mark(question, actual: actual)
                let chance = PropExpectationActualDisplay.expectation(question.expectation).valueText
                Button {
                    open(question)
                } label: {
                    HStack(spacing: 4) {
                        Text(PropExpectationActualDisplay.question(question, stat: stat))
                        if let chance { Text(chance).monospacedDigit().fontWeight(.semibold) }
                        if mark != .unknown {
                            Text(PropExpectationActualDisplay.markText(mark))
                                .fontWeight(mark == .reached ? .semibold : .regular)
                                .foregroundStyle(mark == .reached ? Color.green : Color.secondary)
                        }
                    }
                    .font(.caption)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 8)
                        .fill(mark == .reached ? Color.green.opacity(0.12) : Color.secondary.opacity(0.08)))
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(PropExpectationActualDisplay.accessibilityLabel(question, actual: actual, stat: stat))
                .accessibilityHint("Shows this question and its sources")
                .accessibilityFocused($accessibilityFocus, equals: .question(.init(question)))
            }
        }
    }

    private func footer(_ grid: AfterPropsMatrixLayout.Grid) -> some View {
        Text("Pregame chance · final counts from ESPN")
            .font(.caption2)
            .foregroundStyle(.secondary)
    }
}

/// One After question, exactly: the saved pregame chance and where it came
/// from, the player's official final count, and the server's mark. A question
/// the server stops carrying reads as unavailable; the sheet never moves.
struct AfterPropsDetailView: View {
    let open: EventPropsMatrixSelection.OpenQuestion
    let props: AfterPlayerProps
    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize

    private var stat: AfterPropStat? { props.stat(open.statKey) }

    var body: some View {
        NavigationStack {
            List {
                if let question = AfterPropsMatrixLayout.resolve(open, in: props) {
                    summary(question)
                    result(question)
                    if !question.expectation.contributors.isEmpty { sources(question) }
                } else {
                    Text("This question isn't available right now.")
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle(AfterPropsMatrixLayout.resolve(open, in: props)?.subject.label ?? "Player prop")
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

    private func summary(_ question: AfterPropQuestion) -> some View {
        let expectation = PropExpectationActualDisplay.expectation(question.expectation)
        return Section {
            VStack(alignment: .leading, spacing: 6) {
                Text(PropExpectationActualDisplay.question(question, stat: stat))
                    .font(.headline)
                if let value = expectation.valueText {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text(value)
                            .font(.largeTitle.monospacedDigit())
                            .fontWeight(.bold)
                        // The exact value only when it says more than the
                        // headline (0.4% beside <1%), never 6.0% beside 6%.
                        if let exact = PropExpectationActualDisplay.exactDetailText(question.expectation) {
                            Text(exact)
                                .font(.subheadline.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                    Text(expectation.label)
                        .font(.subheadline)
                } else {
                    // No saved chance: say so in words, never a bare dash.
                    Text(expectation.label)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let basis = expectation.basisText {
                    Text(basis).font(.subheadline).foregroundStyle(.secondary)
                }
            }
            .accessibilityElement(children: .combine)
        }
    }

    private func result(_ question: AfterPropQuestion) -> some View {
        let actual = PropExpectationActualDisplay.actual(props.actual(for: question), stat: stat)
        let mark = PropExpectationActualDisplay.mark(question, actual: props.actual(for: question))
        return Section("Result") {
            let layout = typeSize.isAccessibilitySize
                ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                : AnyLayout(HStackLayout(alignment: .firstTextBaseline))
            layout {
                VStack(alignment: .leading, spacing: 2) {
                    Text(actual.countText ?? actual.stateText)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    if let source = actual.sourceLabel {
                        Text(source).font(.caption).foregroundStyle(.secondary)
                    }
                }
                if !typeSize.isAccessibilitySize { Spacer() }
                Text(PropExpectationActualDisplay.markText(mark))
                    .font(.subheadline)
                    .fontWeight(mark == .reached ? .semibold : .regular)
                    .foregroundStyle(mark == .reached ? Color.green : Color.secondary)
            }
            .accessibilityElement(children: .combine)
        }
    }

    private func sources(_ question: AfterPropQuestion) -> some View {
        Section("Sources") {
            ForEach(Array(question.expectation.contributors.enumerated()), id: \.offset) { _, c in
                let layout = typeSize.isAccessibilitySize
                    ? AnyLayout(VStackLayout(alignment: .leading, spacing: 4))
                    : AnyLayout(HStackLayout(alignment: .firstTextBaseline))
                layout {
                    VStack(alignment: .leading, spacing: 2) {
                        if let name = SourceLabels.label(for: c.source) {
                            Text(name).font(.subheadline).fontWeight(.semibold)
                        }
                        if let outcome = c.outcomeName, !outcome.isEmpty {
                            Text(outcome).font(.caption).foregroundStyle(.secondary)
                        }
                    }
                    if !typeSize.isAccessibilitySize { Spacer() }
                    Text(EventPropsMatrixLayout.exactPercent(c.probability))
                        .font(.subheadline.monospacedDigit())
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}
