import SwiftUI

/// #9483 — the selected line's comparison, drawn above a player's milestone
/// chart (design ref player-milestone-comparison-20261026): the target and its
/// stat first, then the pregame chance large and labelled, then — once the
/// host says the game is final — the stat's final actual at the same size,
/// with the server's own grade of the line on a separate row.
///
/// Stateless. The host resolves the selection (`NFLCardDeckState9483`) and the
/// final flag; this view resolves only the row it is handed and never falls
/// back to another line, rung or player.
///
/// Every chance on `NFLMilestoneCard9483` is a PREGAME number — the current
/// price before kickoff, the server's pregame mark once play starts. The card
/// carries no in-play chance, so during play the comparison says the current
/// chance is unavailable instead of relabelling the pregame one. A full
/// live comparison needs a live binding the card does not have yet.
struct PlayerMilestoneComparison9483: View {
    let card: NFLMilestoneCard9483
    /// The original row (`Rung.rowID`) the host has selected, or nil.
    let selectedRowID: String?
    /// The host's final flag. The final layout follows it, never the card's
    /// own fields: an actual or a grade on its own does not make a game final.
    let isFinal: Bool
    let color: Color

    @Environment(\.dynamicTypeSize) private var size
    /// Both compared figures share one scaled size, so neither reads as the
    /// footnote of the other.
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = Self.figurePointSize

    /// The figures' size at the default text size (Design: at least 26pt).
    static let figurePointSize: CGFloat = 28

    var body: some View {
        let readout = Self.readout(card: card, selectedRowID: selectedRowID, isFinal: isFinal)
        VStack(alignment: .leading, spacing: 10) {
            Text(readout.targetText)
                .font(.headline)
                .foregroundStyle(readout.selection.isLine ? Color.primary : Color.secondary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityLabel(readout.targetSpoken)
                .accessibilityAddTraits(.isHeader)
            columns(readout)
            if let result = readout.resultText {
                // The server's grade of the line, apart from the stat: an
                // actual past the line is not a grade.
                Text("Line result · \(Text(result).fontWeight(.semibold).foregroundStyle(.primary))")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .ignore)
                    .accessibilityLabel(readout.resultSpoken ?? result)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// Side by side at ordinary sizes; stacked at accessibility sizes so the
    /// figures and words keep their size and wrap between words.
    @ViewBuilder private func columns(_ readout: Readout) -> some View {
        if Self.stacks(at: size) {
            VStack(alignment: .leading, spacing: 12) { comparisonColumns(readout) }
        } else {
            HStack(alignment: .top, spacing: 16) { comparisonColumns(readout) }
        }
    }

    @ViewBuilder private func comparisonColumns(_ readout: Readout) -> some View {
        pregameColumn(readout)
        switch readout.layout {
        case .pregameOnly:
            EmptyView()
        case .pregameAndUnavailableCurrent:
            currentColumn(readout)
        case .pregameAndFinal:
            actualColumn(readout)
        }
    }

    private func pregameColumn(_ readout: Readout) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            // The chart's hollow pregame marker, named in words as well.
            HStack(spacing: 4) {
                Image(systemName: "circle")
                    .font(.caption2.weight(.bold))
                    .accessibilityHidden(true)
                Text("Pregame")
                    .font(.subheadline.weight(.semibold))
            }
            .foregroundStyle(color)
            Text(readout.pregameFigureText)
                .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                .foregroundStyle(readout.pregame.isFigure ? color : Color.secondary)
                .fixedSize()
            Text(readout.pregameCaption)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(readout.pregameSpoken)
    }

    /// During play: the slot a current chance would take, said to be empty.
    /// No marker — the chart draws no current dot either.
    private func currentColumn(_ readout: Readout) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(Readout.currentLabelText)
                .font(.subheadline.weight(.semibold))
            Text(Readout.currentFigureText)
                .font(.headline)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(Readout.currentSpoken)
    }

    private func actualColumn(_ readout: Readout) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            // The chart draws the final as a rule on the stat axis.
            HStack(spacing: 6) {
                Rectangle()
                    .fill(Color.primary)
                    .frame(width: 2, height: 12)
                    .accessibilityHidden(true)
                Text("Final actual")
                    .font(.subheadline.weight(.semibold))
            }
            Text(readout.actualFigureText ?? absentProbabilityMarker)
                .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                .foregroundStyle(readout.actual?.isFigure == true ? Color.primary : Color.secondary)
                .fixedSize()
            Text(readout.actualCaption ?? "")
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(readout.actualSpoken ?? "")
    }

    static func stacks(at size: DynamicTypeSize) -> Bool { size.isAccessibilitySize }
}

// MARK: - What the comparison says

extension PlayerMilestoneComparison9483 {
    /// The comparison as words, decided once from the card, the selected row
    /// and the host's final flag. Each absence keeps its own wording: no line
    /// selected, a selected line not on the card in this update, a line with no
    /// pregame number, a final with no actual, and an ungraded line never
    /// read as zero, a loss or a neighbour's number.
    struct Readout: Equatable {
        enum Selection: Equatable {
            /// The selected row, resolved on this card.
            case line(NFLMilestoneCard9483.Rung)
            /// The host selected nothing.
            case none
            /// The host's row is not on this card in this update (the venue may
            /// still offer it, or it is another card's row). Not a withdrawal.
            case unavailable

            var isLine: Bool { if case .line = self { return true } else { return false } }
        }

        enum Chance: Equatable {
            case figure(String)
            /// Before kickoff: the quote stopped being observed.
            case noRecentUpdate
            /// Once play starts: the server served no pregame mark.
            case noPregameChance
            /// No line resolved, so no chance belongs here.
            case noLine

            var isFigure: Bool { if case .figure = self { return true } else { return false } }
        }

        enum Actual: Equatable {
            case figure(String)
            case missing

            var isFigure: Bool { if case .figure = self { return true } else { return false } }
        }

        enum Result: Equatable { case reached, notReached, ungraded }

        enum Layout: Equatable {
            /// Before kickoff: the pregame chance, once.
            case pregameOnly
            /// Play started, not final: the historical pregame chance beside an
            /// unavailable current one.
            case pregameAndUnavailableCurrent
            /// Final: the pregame chance beside the stat's final actual.
            case pregameAndFinal
        }

        let stat: String
        let selection: Selection
        let pregame: Chance
        let layout: Layout
        /// Final layout only.
        let actual: Actual?
        /// Final layout with a resolved line only.
        let result: Result?

        private var target: String? {
            if case .line(let rung) = selection { return PlayerPropsFamily.targetLabel(rung.threshold) }
            return nil
        }

        var targetText: String {
            switch selection {
            case .line: return "\(target ?? "") \(stat)"
            case .none: return "No line selected"
            case .unavailable: return "Selected line unavailable in this update"
            }
        }

        var targetSpoken: String {
            switch selection {
            case .line: return "Selected line, \(targetText)"
            case .none, .unavailable: return targetText
            }
        }

        var pregameFigureText: String {
            if case .figure(let text) = pregame { return text }
            return absentProbabilityMarker
        }

        var pregameCaption: String {
            switch pregame {
            case .figure: return "Chance to reach \(target ?? "")"
            case .noRecentUpdate: return "No recent probability update"
            case .noPregameChance: return "No pregame chance"
            case .noLine: return "No chance to show"
            }
        }

        var pregameSpoken: String {
            switch pregame {
            case .figure(let text): return "Pregame chance to reach \(target ?? ""), \(text)"
            case .noRecentUpdate, .noPregameChance, .noLine: return "Pregame chance, \(pregameCaption.lowercased())"
            }
        }

        /// The current column's words, on screen and spoken. They claim
        /// nothing about the pregame column, which may be empty too.
        static let currentLabelText = "Current"
        static let currentFigureText = "Unavailable"
        static let currentSpoken = "\(currentLabelText) chance, \(currentFigureText.lowercased())"

        var actualFigureText: String? {
            switch actual {
            case .figure(let text)?: return text
            case .missing?: return absentProbabilityMarker
            case nil: return nil
            }
        }

        var actualCaption: String? {
            switch actual {
            case .figure?: return stat
            case .missing?: return "No final \(stat) yet"
            case nil: return nil
            }
        }

        var actualSpoken: String? {
            switch actual {
            case .figure(let text)?: return "Final \(stat), \(text)"
            case .missing?: return "Final \(stat), not available yet"
            case nil: return nil
            }
        }

        var resultText: String? {
            switch result {
            case .reached?: return "Reached"
            case .notReached?: return "Not reached"
            case .ungraded?: return "Not graded yet"
            case nil: return nil
            }
        }

        var resultSpoken: String? { resultText.map { "Line result, \($0.lowercased())" } }
    }

    /// Resolves only `selectedRowID` on `card`: nil selects nothing and an
    /// unknown row is unavailable — neither borrows the default line.
    static func readout(card: NFLMilestoneCard9483, selectedRowID: String?, isFinal: Bool) -> Readout {
        let selection: Readout.Selection
        if let selectedRowID {
            selection = card.rungs.first { $0.rowID == selectedRowID }.map { .line($0) } ?? .unavailable
        } else {
            selection = .none
        }

        let pregame: Readout.Chance
        if case .line(let rung) = selection {
            if let chance = rung.chance {
                pregame = .figure(formatProbability(chance))
            } else {
                pregame = card.basis == .pregamePrice ? .noRecentUpdate : .noPregameChance
            }
        } else {
            pregame = .noLine
        }

        let layout: Readout.Layout = isFinal ? .pregameAndFinal
            : card.basis == .pregameMark ? .pregameAndUnavailableCurrent : .pregameOnly

        var actual: Readout.Actual?
        var result: Readout.Result?
        if isFinal {
            actual = card.actual.map { .figure(NFLFinishCardView9483.points($0)) } ?? .missing
            if case .line(let rung) = selection {
                switch rung.hit {
                case true?: result = .reached
                case false?: result = .notReached
                case nil: result = .ungraded
                }
            }
        }

        return Readout(stat: card.stat, selection: selection, pregame: pregame, layout: layout,
                       actual: actual, result: result)
    }
}
