import Foundation

/// #10236 — what the During matrix shows and what a reader has selected in it.
///
/// Pure: every value here is read off the served `during_player_props`. The
/// grid places a row by its typed `predicate.count`, a player by its typed
/// `subject.key`, and pairs an under row with its over cell only through the
/// server's own `complement_question_key`. Nothing is parsed out of a name,
/// sorted by a price or keyed by a position.
enum EventPropsMatrixLayout {
    struct PlayerRow: Equatable, Identifiable {
        var id: String { subjectKey }
        let subjectKey: String
        let label: String
        /// The player's over question at each column count.
        let cells: [Int: DuringPropRow]
    }

    struct Grid: Equatable {
        let stat: DuringPropStat
        /// Every `count_at_least` count any player has, ascending — the
        /// complete set of threshold columns for this stat.
        let columns: [Int]
        /// In the server's row order (first appearance), never re-ranked.
        let players: [PlayerRow]
        /// Questions of this stat with no over cell to live behind (an under
        /// row whose over question is absent). Listed, never dropped.
        let unplaced: [DuringPropRow]
        /// Distinct players of this stat — counted from rows, so a player with
        /// three markets is one player.
        let playerCount: Int
        /// Questions a reader can open from the matrix: every drawn cell plus
        /// every unplaced row. An under row paired behind a drawn over cell is
        /// that question's other side, not a second question — counting rows
        /// printed "42 questions" under 21 numbers (ATL @ LAD, 10/3).
        let questionCount: Int
        /// Questions shown with no current chance (unavailable, not results).
        let unavailableCount: Int
        /// True when any placed cell prints a change, so the legend appears once.
        let showsChange: Bool
    }

    static func grid(_ props: DuringPlayerProps, statKey: String) -> Grid? {
        guard let stat = props.stats.first(where: { $0.statKey == statKey }) else { return nil }
        let rows = props.rows.filter { $0.statKey == statKey }
        guard !rows.isEmpty else { return nil }
        let keys = Set(rows.map(\.questionKey))

        var order: [String] = []
        var labels: [String: String] = [:]
        var cells: [String: [Int: DuringPropRow]] = [:]
        var unplaced: [DuringPropRow] = []
        for row in rows {
            let subject = row.subject.key
            if row.predicate.isAtLeast {
                if labels[subject] == nil { order.append(subject); labels[subject] = row.subject.label }
                cells[subject, default: [:]][row.predicate.count] = row
            } else if !(row.complementQuestionKey.map(keys.contains) ?? false) {
                unplaced.append(row)
            }
        }
        let players = order.map { PlayerRow(subjectKey: $0, label: labels[$0] ?? $0, cells: cells[$0] ?? [:]) }
        let columns = Set(players.flatMap { $0.cells.keys }).sorted()
        let placed = players.flatMap { $0.cells.values }
        return Grid(
            stat: stat,
            columns: columns,
            players: players,
            unplaced: unplaced,
            playerCount: Set(rows.map(\.subject.key)).count,
            questionCount: placed.count + unplaced.count,
            unavailableCount: rows.filter { $0.current.quotedProbability == nil && !$0.current.isActualOnly }.count,
            showsChange: placed.contains { changeText($0) != nil }
        )
    }

    /// The under question the server paired with this over question, if any.
    static func otherSide(of row: DuringPropRow, in props: DuringPlayerProps) -> DuringPropRow? {
        props.rows.first { $0.complementQuestionKey == row.questionKey }
    }

    /// Where VoiceOver lands when the reader closes `open`'s detail.
    enum ReturnFocus: Equatable {
        /// The same question, still drawn (quoted, stale or unavailable).
        case question(EventPropsMatrixSelection.OpenQuestion)
        /// Removed, reclassified, or its statistic left: the section header,
        /// never another threshold, player or a silently paired hidden side.
        case header
        /// The whole matrix withdrew while the detail was open: no cell and
        /// no header exist, so the page owns the destination.
        case matrixWithdrawn
    }

    static func returnFocus(
        after open: EventPropsMatrixSelection.OpenQuestion,
        selection: EventPropsMatrixSelection,
        in props: DuringPlayerProps
    ) -> ReturnFocus {
        if props.rows.isEmpty { return .matrixWithdrawn }
        guard selection.resolvedStat(in: props) == open.statKey,
              let grid = grid(props, statKey: open.statKey) else { return .header }
        let drawnRows = grid.players.flatMap { Array($0.cells.values) } + grid.unplaced
        let stillDrawn = drawnRows.contains { EventPropsMatrixSelection.OpenQuestion($0) == open }
        return stillDrawn ? .question(open) : .header
    }

    /// The legacy `player_props` the matrix does not already draw, for the old
    /// card beneath it — so no count question is listed twice on the page.
    ///
    /// A legacy prop is the matrix's when one of its contributor outcome ids
    /// feeds a typed row; that is the server's own link, never a name match. A
    /// prop carrying no outcome ids cannot be proven typed and stays in the old
    /// card, as does everything when there is no typed payload at all.
    static func untypedPlayerProps(
        _ playerProps: [GameMarketPlayerProp],
        typed props: DuringPlayerProps?
    ) -> [GameMarketPlayerProp] {
        guard let props, !props.rows.isEmpty else { return playerProps }
        let typedOutcomeIds = Set(props.rows.flatMap { $0.contributorOutcomeIds ?? [] })
        return playerProps.filter { prop in
            let ids = prop.contributorOutcomeIds ?? []
            return ids.isEmpty || !ids.contains(where: typedOutcomeIds.contains)
        }
    }

    // MARK: - Formatting (the view's only words)

    /// The cell's figure: the quoted chance, the server's grade, or the dash.
    static func cellText(_ row: DuringPropRow) -> String {
        if let p = row.current.quotedProbability { return formatProbability(p) }
        if row.current.isActualOnly {
            switch row.result?.hit {
            case true?: return "Hit"
            case false?: return "Miss"
            case nil: return absentProbabilityMarker
            }
        }
        return absentProbabilityMarker
    }

    /// The signed whole-point change since the pregame price, or nil.
    ///
    /// Only the server's `comparable` delta, only on a quoted row, and never a
    /// false zero: a change under one point prints nothing.
    static func changePoints(_ row: DuringPropRow) -> Int? {
        guard row.current.quotedProbability != nil,
              let comparison = row.comparison, comparison.isComparable,
              let delta = comparison.deltaPoints, delta.isFinite, abs(delta) >= 1 else { return nil }
        return Int(delta.rounded())
    }

    static func changeText(_ row: DuringPropRow) -> String? {
        guard let points = changePoints(row) else { return nil }
        return points > 0 ? "+\(points)%" : "\u{2212}\(-points)%"
    }

    /// "2+ hits", "1+ hit", "1 or fewer hits" — the server's label and unit.
    static func question(_ row: DuringPropRow, stat: DuringPropStat?) -> String {
        guard let stat else { return row.predicate.label }
        let unit = row.predicate.isAtLeast && row.predicate.count == 1 ? stat.unitSingular : stat.unit
        return "\(row.predicate.label) \(unit)"
    }

    /// What VoiceOver says for one cell, without leaning on color or symbols.
    static func spokenQuestion(_ row: DuringPropRow, stat: DuringPropStat?) -> String {
        // "1 or more hits" — spoken English takes the plural after "or more".
        let count = row.predicate.count
        let unit = stat?.unit ?? ""
        let words = row.predicate.isAtLeast ? "\(count) or more" : "\(count) or fewer"
        return unit.isEmpty ? words : "\(words) \(unit)"
    }

    static func accessibilityLabel(_ row: DuringPropRow, stat: DuringPropStat?) -> String {
        var parts = [row.subject.label, spokenQuestion(row, stat: stat)]
        if let p = row.current.quotedProbability {
            let pct = formatProbability(p)
                .replacingOccurrences(of: "<", with: "under ")
                .replacingOccurrences(of: ">", with: "over ")
                .replacingOccurrences(of: "%", with: " percent")
            parts.append(pct)
            if let points = changePoints(row) {
                let noun = abs(points) == 1 ? "point" : "points"
                parts.append("\(points > 0 ? "up" : "down") \(abs(points)) \(noun) since pregame")
            }
        } else if row.current.isActualOnly, let hit = row.result?.hit {
            parts.append(hit ? "result: hit" : "result: missed")
        } else {
            parts.append("no current price")
        }
        return parts.joined(separator: ", ")
    }

    /// Detail precision: one decimal, so a quoted 0 reads 0.0% and a 0.4%
    /// quote is not rounded into a different claim.
    static func exactPercent(_ probability: Double?) -> String {
        guard let probability, probability.isFinite else { return absentProbabilityMarker }
        return String(format: "%.1f%%", probability * 100)
    }

    /// Which sources the chance comes from, by name. A source key the app
    /// cannot name is not printed (#4135).
    static func basisText(_ row: DuringPropRow) -> String? {
        guard row.current.quotedProbability != nil else { return nil }
        var names: [String] = []
        for c in row.contributors {
            if let name = SourceLabels.label(for: c.source), !names.contains(name) { names.append(name) }
        }
        switch row.current.basis {
        case "blend_mean":
            return names.count > 1 ? "Average of \(names.joined(separator: " and "))" : "Average of \(row.contributors.count) prices"
        case "single_source":
            return names.first
        default:
            return nil
        }
    }
}

/// The reader's place in the matrix: one statistic and, while the detail is
/// open, one exact question. Keys only — never a price or an index — so a
/// newer payload can re-render underneath without moving either.
nonisolated struct EventPropsMatrixSelection: Equatable {
    struct OpenQuestion: Equatable, Hashable, Identifiable {
        var id: String { questionKey }
        let questionKey: String
        let subjectKey: String
        let statKey: String

        init(_ row: DuringPropRow) {
            questionKey = row.questionKey
            subjectKey = row.subject.key
            statKey = row.statKey
        }
    }

    var statKey: String?
    var openQuestion: OpenQuestion?

    /// The reader opens one exact question. Opening a question on the
    /// default statistic is a choice of that statistic too: pin it, so a newer
    /// payload that reorders the server's stats cannot swap the background
    /// (and the Close destination) out from under the open detail.
    mutating func open(_ row: DuringPropRow) -> OpenQuestion {
        let open = OpenQuestion(row)
        statKey = open.statKey
        openQuestion = open
        return open
    }

    /// The statistic on screen: the reader's choice once made, else the
    /// server's first. A chosen statistic that leaves the payload stays chosen
    /// (and shows nothing) rather than silently switching to another.
    func resolvedStat(in props: DuringPlayerProps) -> String? {
        statKey ?? props.stats.first?.statKey
    }

    /// The open question as it reads now, or nil when the server no longer
    /// carries exactly it. Never a sibling threshold or another player.
    static func resolve(_ open: OpenQuestion, in props: DuringPlayerProps) -> DuringPropRow? {
        props.rows.first {
            $0.questionKey == open.questionKey && $0.subject.key == open.subjectKey && $0.statKey == open.statKey
        }
    }
}
