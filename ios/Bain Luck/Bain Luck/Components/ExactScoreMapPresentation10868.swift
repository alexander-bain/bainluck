import SwiftUI

// #10868 — the soccer exact-score map across a match's lifecycle: every listed
// exact score's pregame chance as one dense map per scope (full match, first
// half), the selected score's pregame chance beside an independently admitted
// current chance during play, and beside that original's own result after it.
//
// Presentation only, extracted from the approved native reference
// (native-soccer-score-composition `ExactScoreLifecycleMap9483.swift` +
// `ExactScoreLifecycleReader9483.swift`, lifecycle model
// `ExactScoreLifecycle9483.swift`, phase composition ADOPTION.md; browser
// context `ExactScoreGridCard.tsx`). Home goals run down the rows and away
// goals across the columns, with the teams named. Cell shading is the
// original's PREGAME chance on the scope's own pregame scale — never a
// current quote, never a projected final.
//
// Every scope, axis value, original, coordinate, order, figure, clock, scale,
// legend line, word, current reading, result and actual score arrives resolved
// by the owner and is shown verbatim. This layer never parses a title, a date
// or a fixture, never formats, rounds, ranks, sorts, normalizes or completes
// chances, never derives currentness, never matches a result to a scoreboard,
// never picks a favourite, a most-likely score or an initial selection, and
// never shows a settled price as a chance. A missing result is never a loss.
// One scope never lends a status or result to another.
//
// Validation here protects geometry and action identity only: a reading the
// scale cannot place is hatched rather than clamped, and a duplicated identity
// or coordinate gets no action rather than a guess. Every original stays
// reachable: placed ones on the map and through Previous/Next, the rest
// (non-grid, malformed or ambiguous coordinates) as named choices.
//
// Selection, Details, Back, focus and scope choice stay with the host: the view
// keeps no selected state, no sheet and no subscription. With no callback,
// content is shown without a button and no tap is asked for.
//
// Host binding still owed — not available at this base. An owner must supply:
//   • the scopes (opaque identity, label, ordered home-goal rows and away-goal
//     columns, the pregame scale's bounds and formatted ticks) and the actual
//     score context per scope once admitted,
//   • per original: its exact identity, full label, grid coordinate or non-grid
//     classification, the pregame reading admitted at the owner's cutoff (raw
//     value, formatted figure, visible clock/source) or its own unavailable
//     words, during play an independently admitted current reading or its own
//     unavailable / withheld words, and the owner-resolved result,
// and for the card: the phase, headline, axis titles, legend lines, words and
// the exact scope / original selection.

/// One admitted chance. `probability` drives shading only; `text` is what the
/// reader sees.
nonisolated struct ExactScoreMapObservation10868: Equatable {
    let probability: Double
    /// The owner's figure ("4%").
    let text: String
    /// Visible and spoken provenance: clock and source ("Polymarket · Oct 10, 4:32 PM PT").
    let detail: String
}

/// The owner's pregame reading, already admitted at its own cutoff.
nonisolated enum ExactScoreMapPregame10868: Equatable {
    case recorded(ExactScoreMapObservation10868)
    /// Missing, or withheld because it was recorded after the cutoff
    /// ("Pregame chance unavailable").
    case unavailable(String)

    var observation: ExactScoreMapObservation10868? {
        if case .recorded(let observation) = self { return observation }
        return nil
    }
}

/// The owner's in-game reading for one original, currentness applied.
nonisolated enum ExactScoreMapCurrent10868: Equatable {
    /// An independently admitted, current recorded observation.
    case recorded(ExactScoreMapObservation10868)
    /// No current reading ("Current chance unavailable").
    case unavailable(String)
    /// A reading exists but is not admitted as current ("No update since 5:12 PM").
    case withheld(String)
}

/// The owner-resolved result of one original. There is no Bool, so an absent
/// result can never read as lost.
nonisolated enum ExactScoreMapResult10868: Equatable {
    /// "Won"
    case won(String)
    /// "Lost"
    case lost(String)
    /// Any other admitted settlement ("Void").
    case other(String)
    /// No admitted result — pending, missing or conflicting ("Unconfirmed").
    case unconfirmed(String)

    var text: String {
        switch self {
        case .won(let text), .lost(let text), .other(let text), .unconfirmed(let text): text
        }
    }

    var isAdmitted: Bool {
        if case .unconfirmed = self { return false }
        return true
    }

    var isWon: Bool {
        if case .won = self { return true }
        return false
    }

    /// The ✓ / ✕ beside an admitted win or loss. Other and unconfirmed results
    /// have none, so unknown never reads as a loss.
    var mark: ExactScoreMapResultMark10868? {
        switch self {
        case .won: .won
        case .lost: .lost
        case .other, .unconfirmed: nil
        }
    }
}

nonisolated enum ExactScoreMapResultMark10868: Equatable {
    case won
    case lost
}

/// Where an original sits: an owner-supplied grid coordinate, or not on the
/// grid at all ("Any Other Score").
nonisolated enum ExactScoreMapPlacement10868: Equatable {
    case grid(home: Int, away: Int)
    case nonGrid
}

/// One listed original exact-score outcome.
nonisolated struct ExactScoreMapOriginal10868: Equatable {
    /// Opaque original identity, passed back exactly.
    let id: String
    /// The full outcome label ("Hull City AFC 2 - 2 Everton FC").
    let label: String
    let placement: ExactScoreMapPlacement10868
    let pregame: ExactScoreMapPregame10868
    /// Read only during play.
    let current: ExactScoreMapCurrent10868
    /// Read during play once admitted, and after the final.
    let result: ExactScoreMapResult10868
}

/// One goal count on an axis: the value coordinates name, and its label.
nonisolated struct ExactScoreMapGoal10868: Equatable {
    let value: Int
    let text: String
}

/// Separately admitted actual score context — never a grade input.
nonisolated struct ExactScoreMapActual10868: Equatable {
    /// "Final score"
    let title: String
    /// "Hull City 2–2 Everton"
    let text: String
}

nonisolated struct ExactScoreMapTick10868: Equatable {
    /// Raw probability, in the same units as the scale bounds.
    let value: Double
    /// The owner's label ("10%").
    let text: String
}

/// A scope's pregame shading scale: raw bounds plus the owner's formatted ticks.
nonisolated struct ExactScoreMapScale10868: Equatable {
    let lower: Double
    let upper: Double
    let ticks: [ExactScoreMapTick10868]

    /// A probability scale: finite, nonempty and inside 0...1. Anything else
    /// shades nothing — the bounds are never clamped or normalized.
    var isValid: Bool {
        lower.isFinite && upper.isFinite && lower >= 0 && upper <= 1 && upper > lower
    }
}

/// One market of exact scores ("Full match", "First half").
nonisolated struct ExactScoreMapScope10868: Equatable {
    /// Opaque owner identity, passed back exactly.
    let id: String
    let label: String
    /// Home goals, top to bottom.
    let rows: [ExactScoreMapGoal10868]
    /// Away goals, left to right.
    let columns: [ExactScoreMapGoal10868]
    /// Every listed original, in the owner's order — never sorted or filtered here.
    let originals: [ExactScoreMapOriginal10868]
    let scale: ExactScoreMapScale10868
    /// Shown during play and after the final, when the owner admits it.
    let actual: ExactScoreMapActual10868?
}

nonisolated enum ExactScoreMapPhase10868: Equatable {
    case before
    case during
    case final
}

/// The owner's key lines. Each is shown only when the map uses its channel.
nonisolated struct ExactScoreMapLegend10868: Equatable {
    /// "Pregame chance · darker is higher" — always shown with the scale.
    let scaleTitle: String
    /// "Hatched: outside the pregame scale"
    let offScale: String
    /// "Dashed: not separately listed"
    let notListed: String
    /// "—: no pregame chance"
    let unavailable: String
    /// "Dark outline: confirmed result"
    let result: String
    /// "Corner marks: selected score"
    let selection: String
}

/// The caller's words, chosen explicitly — never parsed from a label.
nonisolated struct ExactScoreMapWords10868: Equatable {
    /// "Pregame chance"
    let pregameTitle: String
    /// "Current chance"
    let currentTitle: String
    /// "Half result" — a result admitted during play.
    let liveResultTitle: String
    /// "Final result"
    let finalResultTitle: String
    /// "Selected market unavailable."
    let scopeUnavailable: String
    /// "Choose a score to compare."
    let noSelection: String
    /// "Selected score unavailable."
    let selectionUnavailable: String
    /// "View first listed score" — the owner's explicit recovery.
    let recoverSelection: String
    /// "Score map unavailable. Every listed score is below."
    let mapUnavailable: String
    /// "Pregame scale unavailable. Cells are not shaded."
    let scaleUnavailable: String
    /// "Swipe the map sideways to see every column."
    let panHint: String
    /// "Not separately listed" — spoken for a coordinate with no original.
    let notListed: String
    /// "—" — a listed cell with no pregame reading, or an ambiguous coordinate.
    let unavailableMark: String
    /// "Other listed outcomes"
    let otherChoicesTitle: String
    /// "Previous score"
    let previous: String
    /// "Next score"
    let next: String
    /// "Details"
    let details: String
    /// "Selected"
    let selectedSpoken: String
    /// "Shows this market's scores"
    let selectScopeHint: String
    /// "Shows this score's chances"
    let selectHint: String
    /// "Opens the original market"
    let detailsHint: String
}

nonisolated enum ExactScoreMapScopeSelection10868: Equatable {
    case unselected
    case selected(ExactScoreMapScope10868)
    /// No scope carries the selected id.
    case missing(String)
    /// More than one scope carries the selected id.
    case duplicate(String)

    var scope: ExactScoreMapScope10868? {
        if case .selected(let scope) = self { return scope }
        return nil
    }
}

nonisolated enum ExactScoreMapOriginalSelection10868: Equatable {
    case unselected
    case selected(ExactScoreMapOriginal10868)
    /// No original of the scope carries the selected id (withdrawn or foreign).
    case missing(String)
    /// More than one original of the scope carries the selected id.
    case duplicate(String)

    var original: ExactScoreMapOriginal10868? {
        if case .selected(let original) = self { return original }
        return nil
    }
}

nonisolated struct ExactScoreMapPosition10868: Equatable, Hashable {
    let row: Int
    let column: Int
}

/// What occupies one grid coordinate.
nonisolated enum ExactScoreMapSlot10868: Equatable {
    /// Exactly one original names this coordinate.
    case original(ExactScoreMapOriginal10868)
    /// No original names it: it is not separately listed — never zero, never a result.
    case notListed
    /// More than one original names it — nothing is chosen.
    case ambiguous
}

/// How a cell is shaded.
nonisolated enum ExactScoreMapFill10868: Equatable {
    /// Position on the pregame scale, 0...1. Zero is a real quoted zero.
    case intensity(Double)
    /// A recorded reading the scale cannot place — hatched, never clamped.
    case offScale
    /// No reading, or no valid scale.
    case blank
}

/// One drawn coordinate.
nonisolated struct ExactScoreMapCell10868: Equatable {
    let position: ExactScoreMapPosition10868
    let slot: ExactScoreMapSlot10868
    /// The owner's pregame figure, the unavailable mark, or nothing.
    let text: String
    let fill: ExactScoreMapFill10868
    /// A confirmed winning original, once results may be shown.
    let showsResult: Bool
    let isSelected: Bool

    var isDashed: Bool { slot == .notListed }
}

/// What sits in one comparison slot of the selected summary.
nonisolated enum ExactScoreMapReading10868: Equatable {
    case figure(ExactScoreMapObservation10868)
    case words(String)
    case result(ExactScoreMapResult10868)
}

nonisolated struct ExactScoreMapComparison10868: Equatable {
    let title: String
    let reading: ExactScoreMapReading10868
}

nonisolated enum ExactScoreMapAction10868: Equatable {
    case selectScope(String)
    case selectOriginal(scopeID: String, originalID: String)
    case details(scopeID: String, originalID: String)
    case recover
}

/// Which owner key lines the drawn map needs.
nonisolated struct ExactScoreMapKeyUse10868: Equatable {
    let offScale: Bool
    let notListed: Bool
    let unavailable: Bool
    let result: Bool
    let selection: Bool
}

nonisolated struct ExactScoreMapInput10868: Equatable {
    let phase: ExactScoreMapPhase10868
    /// "How might it finish?"
    let title: String
    /// Owner context copy for this phase.
    let intro: String?
    /// "Hull City" — names the rows when spoken.
    let homeLabel: String
    /// "Everton" — names the columns when spoken.
    let awayLabel: String
    /// "Rows: Hull City goals"
    let rowsTitle: String
    /// "Columns: Everton goals"
    let columnsTitle: String
    /// In the owner's order.
    let scopes: [ExactScoreMapScope10868]
    let selectedScopeID: String?
    /// An original of the selected scope.
    let selectedOriginalID: String?
    let legend: ExactScoreMapLegend10868
    let words: ExactScoreMapWords10868

    // MARK: Selection

    /// Exact id only. A missing or duplicated id gets no substitute scope.
    var scopeSelection: ExactScoreMapScopeSelection10868 {
        guard let selectedScopeID else { return .unselected }
        let matches = scopes.filter { $0.id == selectedScopeID }
        switch matches.count {
        case 1: return .selected(matches[0])
        case 0: return .missing(selectedScopeID)
        default: return .duplicate(selectedScopeID)
        }
    }

    /// Exact id within the scope only. A withdrawn or duplicated id is
    /// unavailable; nothing moves to a neighbour or a winner.
    func originalSelection(in scope: ExactScoreMapScope10868) -> ExactScoreMapOriginalSelection10868 {
        guard let selectedOriginalID else { return .unselected }
        let matches = scope.originals.filter { $0.id == selectedOriginalID }
        switch matches.count {
        case 1: return .selected(matches[0])
        case 0: return .missing(selectedOriginalID)
        default: return .duplicate(selectedOriginalID)
        }
    }

    func isUniqueScope(_ id: String) -> Bool {
        scopes.filter { $0.id == id }.count == 1
    }

    func isUniqueOriginal(_ id: String, in scope: ExactScoreMapScope10868) -> Bool {
        scope.originals.filter { $0.id == id }.count == 1
    }

    /// The originals an action can name, in the owner's order.
    func actionableIDs(in scope: ExactScoreMapScope10868) -> [String] {
        scope.originals.map(\.id).filter { isUniqueOriginal($0, in: scope) }
    }

    // MARK: Grid

    /// Axes that name each goal count once. Otherwise there is no map and every
    /// original is a named choice.
    func hasGrid(_ scope: ExactScoreMapScope10868) -> Bool {
        !scope.rows.isEmpty && !scope.columns.isEmpty
            && Set(scope.rows.map(\.value)).count == scope.rows.count
            && Set(scope.columns.map(\.value)).count == scope.columns.count
    }

    /// The coordinate an original names, when both its goal counts are on the axes.
    func position(_ original: ExactScoreMapOriginal10868, in scope: ExactScoreMapScope10868) -> ExactScoreMapPosition10868? {
        guard hasGrid(scope), case .grid(let home, let away) = original.placement,
              let row = scope.rows.firstIndex(where: { $0.value == home }),
              let column = scope.columns.firstIndex(where: { $0.value == away }) else { return nil }
        return ExactScoreMapPosition10868(row: row, column: column)
    }

    /// The originals naming a coordinate.
    func originals(at position: ExactScoreMapPosition10868, in scope: ExactScoreMapScope10868) -> [ExactScoreMapOriginal10868] {
        scope.originals.filter { self.position($0, in: scope) == position }
    }

    func slot(at position: ExactScoreMapPosition10868, in scope: ExactScoreMapScope10868) -> ExactScoreMapSlot10868 {
        let found = originals(at: position, in: scope)
        switch found.count {
        case 0: return .notListed
        case 1: return .original(found[0])
        default: return .ambiguous
        }
    }

    /// Every original reachable only by name — non-grid, off the axes, sharing
    /// a coordinate, or on a card with no map — in the owner's order.
    func choices(in scope: ExactScoreMapScope10868) -> [ExactScoreMapOriginal10868] {
        scope.originals.filter { original in
            guard let position = self.position(original, in: scope) else { return true }
            return self.originals(at: position, in: scope).count != 1
        }
    }

    /// Every coordinate, row by row, top-left first. Empty when there is no map.
    func cells(_ scope: ExactScoreMapScope10868) -> [ExactScoreMapCell10868] {
        guard hasGrid(scope) else { return [] }
        let selectedID = originalSelection(in: scope).original?.id
        var cells: [ExactScoreMapCell10868] = []
        for row in scope.rows.indices {
            for column in scope.columns.indices {
                let position = ExactScoreMapPosition10868(row: row, column: column)
                let slot = self.slot(at: position, in: scope)
                switch slot {
                case .original(let original):
                    cells.append(ExactScoreMapCell10868(
                        position: position,
                        slot: slot,
                        text: original.pregame.observation?.text ?? words.unavailableMark,
                        fill: ExactScoreMapGeometry10868.fill(original.pregame, scale: scope.scale),
                        showsResult: showsResult(original),
                        isSelected: original.id == selectedID
                    ))
                case .notListed:
                    cells.append(ExactScoreMapCell10868(position: position, slot: slot, text: "", fill: .blank,
                                                        showsResult: false, isSelected: false))
                case .ambiguous:
                    cells.append(ExactScoreMapCell10868(position: position, slot: slot, text: words.unavailableMark,
                                                        fill: .blank, showsResult: false, isSelected: false))
                }
            }
        }
        return cells
    }

    /// Before play nothing is marked, whatever results the owner passed. After
    /// it only a supplied, admitted win is outlined — an actual score never
    /// marks a winner and an unconfirmed original is never marked lost.
    func showsResult(_ original: ExactScoreMapOriginal10868) -> Bool {
        phase != .before && original.result.isWon
    }

    func keyUse(_ scope: ExactScoreMapScope10868) -> ExactScoreMapKeyUse10868 {
        let cells = self.cells(scope)
        return ExactScoreMapKeyUse10868(
            offScale: cells.contains { $0.fill == .offScale },
            notListed: cells.contains { $0.slot == .notListed },
            unavailable: cells.contains { cell in
                switch cell.slot {
                case .original(let original): original.pregame.observation == nil
                case .ambiguous: true
                case .notListed: false
                }
            },
            result: cells.contains(where: \.showsResult),
            selection: cells.contains(where: \.isSelected)
        )
    }

    /// The scope's ticks the scale can place, as (fill fraction, label).
    func scaleKey(_ scope: ExactScoreMapScope10868) -> [(fraction: Double, text: String)] {
        var placed: [(fraction: Double, text: String)] = []
        for tick in scope.scale.ticks {
            guard let fraction = ExactScoreMapGeometry10868.fraction(tick.value, scale: scope.scale),
                  !placed.contains(where: { $0.fraction == fraction }) else { continue }
            placed.append((fraction: fraction, text: tick.text))
        }
        return placed
    }

    // MARK: Phase readings

    /// The selected summary's comparisons. Before play the pregame chance alone
    /// — any supplied current, result or actual is hidden. During play the
    /// pregame chance and either that original's admitted result (its period
    /// already resolved) or its own current reading; never a historical quote as
    /// current. After the final the pregame chance and that original's result;
    /// the current reading is never read.
    func comparisons(_ original: ExactScoreMapOriginal10868) -> [ExactScoreMapComparison10868] {
        let pregame = ExactScoreMapComparison10868(
            title: words.pregameTitle,
            reading: original.pregame.observation.map { .figure($0) } ?? .words(Self.unavailableText(original.pregame))
        )
        switch phase {
        case .before:
            return [pregame]
        case .during:
            if original.result.isAdmitted {
                return [pregame, ExactScoreMapComparison10868(title: words.liveResultTitle, reading: .result(original.result))]
            }
            let current: ExactScoreMapReading10868
            switch original.current {
            case .recorded(let observation): current = .figure(observation)
            case .unavailable(let text), .withheld(let text): current = .words(text)
            }
            return [pregame, ExactScoreMapComparison10868(title: words.currentTitle, reading: current)]
        case .final:
            return [pregame, ExactScoreMapComparison10868(title: words.finalResultTitle, reading: .result(original.result))]
        }
    }

    /// The actual score context, never before play.
    func visibleActual(_ scope: ExactScoreMapScope10868) -> ExactScoreMapActual10868? {
        phase == .before ? nil : scope.actual
    }

    private static func unavailableText(_ pregame: ExactScoreMapPregame10868) -> String {
        if case .unavailable(let text) = pregame { return text }
        return ""
    }

    // MARK: Actions

    func selectScopeAction(_ scope: ExactScoreMapScope10868, canSelect: Bool) -> ExactScoreMapAction10868? {
        guard canSelect, isUniqueScope(scope.id) else { return nil }
        return .selectScope(scope.id)
    }

    /// Only for an original whose identity is unique in a uniquely selected scope.
    func selectAction(_ original: ExactScoreMapOriginal10868, canSelect: Bool) -> ExactScoreMapAction10868? {
        guard canSelect, let scope = scopeSelection.scope, isUniqueOriginal(original.id, in: scope) else { return nil }
        return .selectOriginal(scopeID: scope.id, originalID: original.id)
    }

    /// A tap on the map: only a coordinate held by exactly one actionable original.
    func tapAction(at position: ExactScoreMapPosition10868, canSelect: Bool) -> ExactScoreMapAction10868? {
        guard let scope = scopeSelection.scope, case .original(let original) = slot(at: position, in: scope) else { return nil }
        return selectAction(original, canSelect: canSelect)
    }

    /// The neighbouring actionable original in the owner's order. With nothing
    /// selected yet, Next asks for the owner's first actionable original — a
    /// reader's explicit step, never an automatic one. A withdrawn or ambiguous
    /// selection has no place to step from: only the owner's recovery is offered.
    func stepAction(_ delta: Int, canSelect: Bool) -> ExactScoreMapAction10868? {
        guard canSelect, delta == 1 || delta == -1, let scope = scopeSelection.scope else { return nil }
        let ids = actionableIDs(in: scope)
        switch originalSelection(in: scope) {
        case .selected(let current):
            guard let index = ids.firstIndex(of: current.id), ids.indices.contains(index + delta) else { return nil }
            return .selectOriginal(scopeID: scope.id, originalID: ids[index + delta])
        case .unselected:
            guard delta == 1, let first = ids.first else { return nil }
            return .selectOriginal(scopeID: scope.id, originalID: first)
        case .missing, .duplicate:
            return nil
        }
    }

    /// Previous / Next appear with a resolved selection or none yet — never
    /// beside an unavailable one.
    func showsSteps(canSelect: Bool) -> Bool {
        guard canSelect, let scope = scopeSelection.scope else { return false }
        switch originalSelection(in: scope) {
        case .selected, .unselected: return true
        case .missing, .duplicate: return false
        }
    }

    func detailsAction(canOpen: Bool) -> ExactScoreMapAction10868? {
        guard canOpen, let scope = scopeSelection.scope, let original = originalSelection(in: scope).original else { return nil }
        return .details(scopeID: scope.id, originalID: original.id)
    }

    /// The owner's recovery, offered only while no original is resolved.
    func recoverAction(canRecover: Bool) -> ExactScoreMapAction10868? {
        guard canRecover, let scope = scopeSelection.scope, originalSelection(in: scope).original == nil else { return nil }
        return .recover
    }

    /// The map is adjustable only when a step can name an exact original.
    func isAdjustable(canSelect: Bool) -> Bool {
        stepAction(1, canSelect: canSelect) != nil || stepAction(-1, canSelect: canSelect) != nil
    }

    // MARK: VoiceOver

    var accessibilityHeader: String {
        title
    }

    func accessibilityLabel(_ original: ExactScoreMapOriginal10868, in scope: ExactScoreMapScope10868) -> String {
        "\(original.label), \(scope.label)"
    }

    /// Each comparison named, with its clock and source.
    func spokenComparisons(_ original: ExactScoreMapOriginal10868) -> String {
        comparisons(original).map { comparison in
            switch comparison.reading {
            case .figure(let observation): "\(comparison.title): \(observation.text), \(observation.detail)"
            case .words(let text): "\(comparison.title): \(text)"
            case .result(let result): "\(comparison.title): \(result.text)"
            }
        }
        .joined(separator: "; ")
    }

    /// The selected summary: comparisons, then the separately labelled actual score.
    func accessibilitySummary(_ original: ExactScoreMapOriginal10868, in scope: ExactScoreMapScope10868) -> String {
        var parts = [spokenComparisons(original)]
        if let actual = visibleActual(scope) { parts.append("\(actual.title): \(actual.text)") }
        return parts.joined(separator: ". ")
    }

    /// "Hull City 2, Everton 2"
    func spokenCoordinate(_ position: ExactScoreMapPosition10868, in scope: ExactScoreMapScope10868) -> String {
        guard scope.rows.indices.contains(position.row), scope.columns.indices.contains(position.column) else { return "" }
        return "\(homeLabel) \(scope.rows[position.row].text), \(awayLabel) \(scope.columns[position.column].text)"
    }

    func accessibilityMapLabel(_ scope: ExactScoreMapScope10868) -> String {
        [scope.label, legend.scaleTitle, rowsTitle, columnsTitle].joined(separator: ". ")
    }

    /// The selection's reading, then every coordinate that is not separately
    /// listed and every ambiguous one, so neither reads as a zero.
    func accessibilityMapValue(_ scope: ExactScoreMapScope10868) -> String {
        var parts: [String] = []
        switch originalSelection(in: scope) {
        case .selected(let original):
            parts.append("\(words.selectedSpoken): \(original.label). \(spokenComparisons(original))")
        case .unselected:
            parts.append(words.noSelection)
        case .missing, .duplicate:
            parts.append(words.selectionUnavailable)
        }
        for cell in cells(scope) {
            switch cell.slot {
            case .notListed:
                parts.append("\(spokenCoordinate(cell.position, in: scope)): \(words.notListed)")
            case .ambiguous:
                parts.append("\(spokenCoordinate(cell.position, in: scope)): \(words.unavailableMark)")
            case .original:
                break
            }
        }
        return parts.joined(separator: ". ")
    }
}

/// Every label and cell placed, and the space the map needs.
nonisolated struct ExactScoreMapPlan10868: Equatable {
    /// The row-label column, each label right-aligned in it.
    let gutter: CGFloat
    /// The column-label row.
    let header: CGFloat
    /// Every cell is this square side.
    let cell: CGFloat
    let gridRect: CGRect
    let rowLabelFrames: [CGRect]
    let columnLabelFrames: [CGRect]
    /// Row by row, top-left first.
    let cellFrames: [CGRect]
    let size: CGSize
    /// The map is wider than the space offered: it pans rather than shrinks.
    let requiresPanning: Bool
}

nonisolated enum ExactScoreMapGeometry10868 {
    /// Where a raw value sits on the scale, 0...1. Nil for an invalid scale or a
    /// non-finite or out-of-domain value — never clamped.
    static func fraction(_ value: Double, scale: ExactScoreMapScale10868) -> Double? {
        guard scale.isValid, value.isFinite, value >= scale.lower, value <= scale.upper else { return nil }
        return (value - scale.lower) / (scale.upper - scale.lower)
    }

    static func fill(_ pregame: ExactScoreMapPregame10868, scale: ExactScoreMapScale10868) -> ExactScoreMapFill10868 {
        guard let observation = pregame.observation, scale.isValid else { return .blank }
        return fraction(observation.probability, scale: scale).map { .intensity($0) } ?? .offScale
    }

    /// The map's plan. Every cell is one square, as wide as the widest cell
    /// figure plus padding, as tall as the tallest, never smaller than
    /// `minimumCell`, and wide and tall enough for every axis label — so a
    /// selection, a long figure or larger type never squeezes, wraps or hides
    /// a figure; the map grows and reports that it must pan instead.
    ///
    /// - Parameters:
    ///   - rowLabelSizes: each row label's size including its clearance from the cells.
    ///   - columnLabelSizes: each column label's size including its clearance from the cells.
    ///   - cellLabelSizes: every cell's figure at one-line size, row by row.
    static func plan(available: CGFloat, rowLabelSizes: [CGSize], columnLabelSizes: [CGSize],
                     cellLabelSizes: [CGSize], minimumCell: CGFloat, padding: CGFloat = 4) -> ExactScoreMapPlan10868? {
        let rows = rowLabelSizes.count
        let columns = columnLabelSizes.count
        let sizes = rowLabelSizes + columnLabelSizes + cellLabelSizes
        guard rows > 0, columns > 0, cellLabelSizes.count == rows * columns,
              sizes.allSatisfy({ $0.width.isFinite && $0.height.isFinite && $0.width >= 0 && $0.height >= 0 }),
              minimumCell.isFinite, minimumCell > 0, padding.isFinite, padding >= 0 else { return nil }
        let gutter = rowLabelSizes.map(\.width).max() ?? 0
        let header = columnLabelSizes.map(\.height).max() ?? 0
        let cell = max(minimumCell,
                       (cellLabelSizes.map(\.width).max() ?? 0) + 2 * padding,
                       (cellLabelSizes.map(\.height).max() ?? 0) + 2 * padding,
                       (columnLabelSizes.map(\.width).max() ?? 0) + 2 * padding,
                       rowLabelSizes.map(\.height).max() ?? 0)
        let rowFrames = (0..<rows).map { row in
            CGRect(x: 0, y: header + CGFloat(row) * cell, width: gutter, height: cell)
        }
        let columnFrames = (0..<columns).map { column in
            CGRect(x: gutter + CGFloat(column) * cell, y: 0, width: cell, height: header)
        }
        var cellFrames: [CGRect] = []
        for row in 0..<rows {
            for column in 0..<columns {
                cellFrames.append(CGRect(x: gutter + CGFloat(column) * cell, y: header + CGFloat(row) * cell,
                                         width: cell, height: cell))
            }
        }
        let size = CGSize(width: gutter + CGFloat(columns) * cell, height: header + CGFloat(rows) * cell)
        return ExactScoreMapPlan10868(
            gutter: gutter,
            header: header,
            cell: cell,
            gridRect: CGRect(x: gutter, y: header, width: CGFloat(columns) * cell, height: CGFloat(rows) * cell),
            rowLabelFrames: rowFrames,
            columnLabelFrames: columnFrames,
            cellFrames: cellFrames,
            size: size,
            requiresPanning: available.isFinite && size.width > available
        )
    }

    /// The coordinate under a point in a grid of `size`. Nil outside it.
    static func position(at point: CGPoint, rows: Int, columns: Int, in size: CGSize) -> ExactScoreMapPosition10868? {
        guard rows > 0, columns > 0, size.width > 0, size.height > 0,
              point.x.isFinite, point.y.isFinite,
              point.x >= 0, point.x < size.width, point.y >= 0, point.y < size.height else { return nil }
        let column = Int(point.x / (size.width / CGFloat(columns)))
        let row = Int(point.y / (size.height / CGFloat(rows)))
        guard (0..<rows).contains(row), (0..<columns).contains(column) else { return nil }
        return ExactScoreMapPosition10868(row: row, column: column)
    }

    /// A coordinate's rect in a grid of `size`.
    static func cellRect(_ position: ExactScoreMapPosition10868, rows: Int, columns: Int, in size: CGSize) -> CGRect? {
        guard rows > 0, columns > 0, (0..<rows).contains(position.row), (0..<columns).contains(position.column) else { return nil }
        let width = size.width / CGFloat(columns)
        let height = size.height / CGFloat(rows)
        return CGRect(x: CGFloat(position.column) * width, y: CGFloat(position.row) * height, width: width, height: height)
    }
}

/// The map block: the cell drawing, the cell figures, the column labels and
/// the row labels — in that subview order, so the pinned row labels sit on top.
/// The size it reports is the plan it places.
struct ExactScoreMapGridLayout10868: Layout {
    let rows: Int
    let columns: Int
    let minimumCell: CGFloat
    var padding: CGFloat = 4

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        plan(available: proposal.width ?? .infinity, subviews: subviews)?.size ?? .zero
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let plan = self.plan(available: bounds.width, subviews: subviews) else { return }
        let count = rows * columns
        subviews[0].place(at: CGPoint(x: bounds.minX + plan.gridRect.minX, y: bounds.minY + plan.gridRect.minY),
                          anchor: .topLeading, proposal: ProposedViewSize(plan.gridRect.size))
        for index in 0..<count {
            let frame = plan.cellFrames[index]
            subviews[1 + index].place(at: CGPoint(x: bounds.minX + frame.midX, y: bounds.minY + frame.midY),
                                      anchor: .center, proposal: .unspecified)
        }
        for column in 0..<columns {
            let frame = plan.columnLabelFrames[column]
            subviews[1 + count + column].place(at: CGPoint(x: bounds.minX + frame.midX, y: bounds.minY + frame.maxY),
                                               anchor: .bottom, proposal: .unspecified)
        }
        for row in 0..<rows {
            let frame = plan.rowLabelFrames[row]
            subviews[1 + count + columns + row].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                                      anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(available: CGFloat, subviews: Subviews) -> ExactScoreMapPlan10868? {
        let count = rows * columns
        guard rows > 0, columns > 0, subviews.count == 1 + count + columns + rows else { return nil }
        let cellSizes = (0..<count).map { subviews[1 + $0].sizeThatFits(.unspecified) }
        let columnSizes = (0..<columns).map { subviews[1 + count + $0].sizeThatFits(.unspecified) }
        let rowSizes = (0..<rows).map { subviews[1 + count + columns + $0].sizeThatFits(.unspecified) }
        return ExactScoreMapGeometry10868.plan(available: available, rowLabelSizes: rowSizes,
                                               columnLabelSizes: columnSizes, cellLabelSizes: cellSizes,
                                               minimumCell: minimumCell, padding: padding)
    }
}

/// One cell's drawing, shared by the map and its key. Shading is intensity,
/// the full inset outline is a confirmed result, the corner brackets are the
/// selection and a dashed border is a coordinate with no original — four
/// separate channels, none of them colour alone.
enum ExactScoreMapCellArt10868 {
    static func draw(fill: ExactScoreMapFill10868, dashed: Bool, result: Bool, selected: Bool,
                     in rect: CGRect, context: inout GraphicsContext) {
        let cell = rect.insetBy(dx: 1, dy: 1)
        guard cell.width > 0, cell.height > 0 else { return }
        context.fill(Path(cell), with: .color(DS.cardBg))
        switch fill {
        case .intensity(let fraction):
            context.fill(Path(cell), with: .color(DS.blue.opacity(0.55 * fraction)))
        case .offScale:
            var hatch = Path()
            var x = cell.minX - cell.height
            while x < cell.maxX {
                hatch.move(to: CGPoint(x: x, y: cell.maxY))
                hatch.addLine(to: CGPoint(x: x + cell.height, y: cell.minY))
                x += 6
            }
            context.drawLayer { layer in
                layer.clip(to: Path(cell))
                layer.stroke(hatch, with: .color(DS.blue.opacity(0.6)), lineWidth: 1.5)
            }
        case .blank:
            break
        }
        context.stroke(Path(cell), with: .color(dashed ? DS.textSecondary : DS.border),
                       style: StrokeStyle(lineWidth: 1, dash: dashed ? [3, 3] : []))
        if result {
            context.stroke(Path(cell.insetBy(dx: 4, dy: 4)), with: .color(DS.textPrimary), lineWidth: 2.5)
        }
        if selected {
            let box = cell.insetBy(dx: 1.5, dy: 1.5)
            let arm = min(box.width, box.height) * 0.3
            var corners = Path()
            corners.move(to: CGPoint(x: box.minX, y: box.minY + arm))
            corners.addLine(to: CGPoint(x: box.minX, y: box.minY))
            corners.addLine(to: CGPoint(x: box.minX + arm, y: box.minY))
            corners.move(to: CGPoint(x: box.maxX - arm, y: box.minY))
            corners.addLine(to: CGPoint(x: box.maxX, y: box.minY))
            corners.addLine(to: CGPoint(x: box.maxX, y: box.minY + arm))
            corners.move(to: CGPoint(x: box.maxX, y: box.maxY - arm))
            corners.addLine(to: CGPoint(x: box.maxX, y: box.maxY))
            corners.addLine(to: CGPoint(x: box.maxX - arm, y: box.maxY))
            corners.move(to: CGPoint(x: box.minX + arm, y: box.maxY))
            corners.addLine(to: CGPoint(x: box.minX, y: box.maxY))
            corners.addLine(to: CGPoint(x: box.minX, y: box.maxY - arm))
            context.stroke(corners, with: .color(DS.textPrimary), lineWidth: 3)
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum ExactScoreMapAccessibilityID10868 {
    static let map = "exactScoreMap10868.map"
    static let summary = "exactScoreMap10868.summary"
    static let previous = "exactScoreMap10868.previous"
    static let next = "exactScoreMap10868.next"
    static let details = "exactScoreMap10868.details"
    static let recover = "exactScoreMap10868.recover"
    static func scope(_ id: String) -> String { "exactScoreMap10868.scope.\(id)" }
    static func choice(_ id: String) -> String { "exactScoreMap10868.choice.\(id)" }
}

/// Adjustable only when stepping can name an exact original.
private struct ExactScoreMapAdjustable10868: ViewModifier {
    let enabled: Bool
    let step: (Int) -> Void

    @ViewBuilder
    func body(content: Content) -> some View {
        if enabled {
            content.accessibilityAdjustableAction { direction in
                switch direction {
                case .increment: step(1)
                case .decrement: step(-1)
                @unknown default: break
                }
            }
        } else {
            content
        }
    }
}

struct ExactScoreMapPresentation10868: View {
    let input: ExactScoreMapInput10868
    var onSelectScope: ((String) -> Void)? = nil
    /// (scope id, original id), exactly as supplied.
    var onSelectOriginal: ((String, String) -> Void)? = nil
    /// (scope id, original id), exactly as supplied.
    var onDetails: ((String, String) -> Void)? = nil
    var onRecoverSelection: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var minimumCell: CGFloat = 40
    @ScaledMetric(relativeTo: .caption) private var keySize: CGFloat = 16

    private var canSelectScope: Bool { onSelectScope != nil }
    private var canSelect: Bool { onSelectOriginal != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var canRecover: Bool { onRecoverSelection != nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            header
            if !input.scopes.isEmpty {
                scopeSelectors
            }
            if let scope = input.scopeSelection.scope {
                summary(scope)
                mapSection(scope)
                navigation
                choices(scope)
            } else {
                Text(input.words.scopeUnavailable)
                    .font(.headline)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .buttonStyle(.plain)
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(input.title)
                .font(.title2.bold())
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            if let intro = input.intro {
                Text(intro).font(.subheadline).foregroundStyle(DS.textSecondary)
            }
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Scopes

    private var scopeSelectors: some View {
        FlowLayout(spacing: 8) {
            ForEach(Array(input.scopes.enumerated()), id: \.offset) { _, scope in
                scopeSelector(scope)
            }
        }
    }

    private func scopeSelector(_ scope: ExactScoreMapScope10868) -> some View {
        let selected = input.scopeSelection.scope?.id == scope.id
        let action = input.selectScopeAction(scope, canSelect: canSelectScope)
        return control(action) {
            Text(scope.label)
                .font(.subheadline.weight(selected ? .semibold : .regular))
                .underline(selected)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
                .frame(minWidth: 44, minHeight: 44)
                .overlay(
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(selected ? DS.textPrimary : DS.border, lineWidth: selected ? 2 : 1)
                )
                .contentShape(Rectangle())
        }
        .accessibilityLabel(scope.label)
        .accessibilityHint(action == nil ? "" : input.words.selectScopeHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.scope(scope.id))
    }

    // MARK: Selected summary

    @ViewBuilder
    private func summary(_ scope: ExactScoreMapScope10868) -> some View {
        switch input.originalSelection(in: scope) {
        case .selected(let original):
            VStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 10) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(scope.label).font(.caption.weight(.semibold)).foregroundStyle(DS.textSecondary)
                        Text(original.label).font(.headline).foregroundStyle(DS.textPrimary)
                    }
                    comparisons(input.comparisons(original))
                    if let actual = input.visibleActual(scope) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(actual.title).font(.caption).foregroundStyle(DS.textSecondary)
                            Text(actual.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
                        }
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(input.accessibilityLabel(original, in: scope))
                .accessibilityValue(input.accessibilitySummary(original, in: scope))
                .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.summary)
                if let action = input.detailsAction(canOpen: canOpenDetails) {
                    Button { perform(action) } label: {
                        HStack(spacing: 6) {
                            Text(input.words.details)
                            Image(systemName: "chevron.right").font(.caption).accessibilityHidden(true)
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .accessibilityHint(input.words.detailsHint)
                    .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.details)
                }
            }
        case .unselected:
            unresolved(input.words.noSelection)
        case .missing, .duplicate:
            unresolved(input.words.selectionUnavailable)
        }
    }

    private func unresolved(_ notice: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(notice)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let action = input.recoverAction(canRecover: canRecover) {
                Button(input.words.recoverSelection) { perform(action) }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                    .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.recover)
            }
        }
    }

    /// Two columns at ordinary widths; stacked when they do not fit and always
    /// at accessibility sizes. A pregame and a current chance share one figure size.
    @ViewBuilder
    private func comparisons(_ items: [ExactScoreMapComparison10868]) -> some View {
        if typeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 12) { comparisonColumns(items) }
        } else {
            ViewThatFits(in: .horizontal) {
                HStack(alignment: .top, spacing: 16) { comparisonColumns(items) }
                VStack(alignment: .leading, spacing: 12) { comparisonColumns(items) }
            }
        }
    }

    private func comparisonColumns(_ items: [ExactScoreMapComparison10868]) -> some View {
        ForEach(Array(items.enumerated()), id: \.offset) { _, item in
            VStack(alignment: .leading, spacing: 2) {
                Text(item.title).font(.caption).foregroundStyle(DS.textSecondary)
                reading(item.reading)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    @ViewBuilder
    private func reading(_ reading: ExactScoreMapReading10868) -> some View {
        switch reading {
        case .figure(let observation):
            Text(observation.text)
                .font(.system(size: figureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: true, vertical: false)
            Text(observation.detail)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .words(let text):
            Text(text)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .result(let result):
            resultLine(result, font: result.isAdmitted ? Font.title3.weight(.semibold) : Font.body)
        }
    }

    private func resultLine(_ result: ExactScoreMapResult10868, font: Font) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            switch result.mark {
            case .won?:
                Image(systemName: "checkmark.circle").accessibilityHidden(true)
            case .lost?:
                Image(systemName: "xmark.circle").accessibilityHidden(true)
            case nil:
                EmptyView()
            }
            Text(result.text).fixedSize(horizontal: false, vertical: true)
        }
        .font(font)
        .foregroundStyle(result.mark == .won ? DS.textPrimary : DS.textSecondary)
    }

    // MARK: Map

    @ViewBuilder
    private func mapSection(_ scope: ExactScoreMapScope10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            VStack(alignment: .leading, spacing: 2) {
                Text(input.rowsTitle)
                Text(input.columnsTitle)
            }
            .font(.subheadline)
            .foregroundStyle(DS.textPrimary)
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityHidden(true)
            if input.hasGrid(scope) {
                let cells = input.cells(scope)
                ViewThatFits(in: .horizontal) {
                    grid(scope, cells: cells)
                    VStack(alignment: .leading, spacing: 4) {
                        ScrollView(.horizontal) {
                            grid(scope, cells: cells)
                        }
                        .scrollBounceBehavior(.basedOnSize, axes: .horizontal)
                        Text(input.words.panHint)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                            .accessibilityHidden(true)
                    }
                }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(input.accessibilityMapLabel(scope))
                .accessibilityValue(input.accessibilityMapValue(scope))
                .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.map)
                .modifier(ExactScoreMapAdjustable10868(enabled: input.isAdjustable(canSelect: canSelect)) { delta in
                    perform(input.stepAction(delta, canSelect: canSelect))
                })
                key(scope)
            } else {
                Text(input.words.mapUnavailable)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func grid(_ scope: ExactScoreMapScope10868, cells: [ExactScoreMapCell10868]) -> some View {
        ExactScoreMapGridLayout10868(rows: scope.rows.count, columns: scope.columns.count, minimumCell: minimumCell) {
            drawing(scope, cells: cells)
            ForEach(Array(cells.enumerated()), id: \.offset) { _, cell in
                Text(cell.text)
                    .font(.caption.weight(.medium))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .lineLimit(1)
                    .fixedSize()
                    .allowsHitTesting(false)
            }
            ForEach(Array(scope.columns.enumerated()), id: \.offset) { _, goal in
                Text(goal.text)
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                    .padding(.bottom, 4)
                    .allowsHitTesting(false)
            }
            ForEach(Array(scope.rows.enumerated()), id: \.offset) { _, goal in
                // Pinned to the leading edge while the cells pan beneath it.
                Text(goal.text)
                    .font(.caption)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                    .padding(.trailing, 6)
                    .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .trailing)
                    .background(DS.cardBg)
                    .allowsHitTesting(false)
                    .visualEffect { content, proxy in
                        content.offset(x: max(0, -proxy.frame(in: .scrollView(axis: .horizontal)).minX))
                    }
            }
        }
    }

    /// One inspection surface: the drawing takes the map's single tap, which
    /// selects only a coordinate held by exactly one actionable original.
    private func drawing(_ scope: ExactScoreMapScope10868, cells: [ExactScoreMapCell10868]) -> some View {
        let rows = scope.rows.count
        let columns = scope.columns.count
        return GeometryReader { geo in
            Canvas { context, size in
                for cell in cells {
                    guard let rect = ExactScoreMapGeometry10868.cellRect(cell.position, rows: rows, columns: columns, in: size) else { continue }
                    ExactScoreMapCellArt10868.draw(fill: cell.fill, dashed: cell.isDashed, result: cell.showsResult,
                                                   selected: cell.isSelected, in: rect, context: &context)
                }
            }
            .contentShape(Rectangle())
            .gesture(SpatialTapGesture().onEnded { value in
                guard let position = ExactScoreMapGeometry10868.position(at: value.location, rows: rows,
                                                                          columns: columns, in: geo.size) else { return }
                perform(input.tapAction(at: position, canSelect: canSelect))
            })
            .allowsHitTesting(canSelect)
        }
    }

    // MARK: Key

    /// The pregame scale, then a line for each channel the map actually uses.
    private func key(_ scope: ExactScoreMapScope10868) -> some View {
        let use = input.keyUse(scope)
        let ticks = input.scaleKey(scope)
        return VStack(alignment: .leading, spacing: 6) {
            Text(input.legend.scaleTitle)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if scope.scale.isValid {
                FlowLayout(spacing: 10) {
                    ForEach(Array(ticks.enumerated()), id: \.offset) { _, tick in
                        HStack(spacing: 4) {
                            sample(fill: .intensity(tick.fraction))
                            Text(tick.text).font(.caption).monospacedDigit().foregroundStyle(DS.textSecondary)
                        }
                    }
                }
            } else {
                Text(input.words.scaleUnavailable)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if use.offScale { keyLine(input.legend.offScale) { sample(fill: .offScale) } }
            if use.notListed { keyLine(input.legend.notListed) { sample(dashed: true) } }
            if use.unavailable { keyLine(input.legend.unavailable) { sampleMark } }
            if use.result { keyLine(input.legend.result) { sample(result: true) } }
            if use.selection { keyLine(input.legend.selection) { sample(selected: true) } }
        }
        .accessibilityElement(children: .combine)
    }

    private func keyLine<Sample: View>(_ text: String, @ViewBuilder sample: () -> Sample) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            sample()
            Text(text)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func sample(fill: ExactScoreMapFill10868 = .blank, dashed: Bool = false,
                        result: Bool = false, selected: Bool = false) -> some View {
        Canvas { context, size in
            ExactScoreMapCellArt10868.draw(fill: fill, dashed: dashed, result: result, selected: selected,
                                           in: CGRect(origin: .zero, size: size), context: &context)
        }
        .frame(width: keySize, height: keySize)
        .accessibilityHidden(true)
    }

    private var sampleMark: some View {
        Text(input.words.unavailableMark)
            .font(.caption.weight(.medium))
            .foregroundStyle(DS.textPrimary)
            .frame(minWidth: keySize, minHeight: keySize)
            .overlay(Rectangle().stroke(DS.border, lineWidth: 1))
            .accessibilityHidden(true)
    }

    // MARK: Previous / Next

    @ViewBuilder
    private var navigation: some View {
        if input.showsSteps(canSelect: canSelect) {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 12) { stepButtons }
                VStack(alignment: .leading, spacing: 8) { stepButtons }
            }
        }
    }

    @ViewBuilder
    private var stepButtons: some View {
        let previous = input.stepAction(-1, canSelect: canSelect)
        let next = input.stepAction(1, canSelect: canSelect)
        Button { perform(previous) } label: {
            stepLabel(input.words.previous, systemImage: "chevron.left", enabled: previous != nil)
        }
        .disabled(previous == nil)
        .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.previous)
        Button { perform(next) } label: {
            stepLabel(input.words.next, systemImage: "chevron.right", enabled: next != nil)
        }
        .disabled(next == nil)
        .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.next)
    }

    private func stepLabel(_ text: String, systemImage: String, enabled: Bool) -> some View {
        Label(text, systemImage: systemImage)
            .font(.subheadline.weight(.semibold))
            .foregroundStyle(enabled ? DS.textPrimary : DS.textMuted)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 12)
            .frame(minWidth: 44, minHeight: 44)
            .overlay(RoundedRectangle(cornerRadius: 10).stroke(DS.border, lineWidth: 1))
            .contentShape(Rectangle())
    }

    // MARK: Named choices

    @ViewBuilder
    private func choices(_ scope: ExactScoreMapScope10868) -> some View {
        let list = input.choices(in: scope)
        if !list.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(input.words.otherChoicesTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(Array(list.enumerated()), id: \.offset) { _, original in
                    choice(original, in: scope)
                }
            }
        }
    }

    private func choice(_ original: ExactScoreMapOriginal10868, in scope: ExactScoreMapScope10868) -> some View {
        let selected = input.originalSelection(in: scope).original?.id == original.id
        let action = input.selectAction(original, canSelect: canSelect)
        let readings = input.comparisons(original)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                Text(original.label)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .underline(selected)
                    .foregroundStyle(DS.textPrimary)
                ForEach(Array(readings.enumerated()), id: \.offset) { _, item in
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Text(item.title).font(.caption).foregroundStyle(DS.textSecondary)
                        choiceReading(item.reading)
                    }
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(selected ? DS.textPrimary : Color.clear, lineWidth: 2)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilityLabel(original, in: scope))
        .accessibilityValue(input.spokenComparisons(original))
        .accessibilityHint(action == nil ? "" : input.words.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(ExactScoreMapAccessibilityID10868.choice(original.id))
    }

    @ViewBuilder
    private func choiceReading(_ reading: ExactScoreMapReading10868) -> some View {
        switch reading {
        case .figure(let observation):
            Text(observation.text).font(.subheadline.weight(.semibold)).monospacedDigit().foregroundStyle(DS.textPrimary)
        case .words(let text):
            Text(text).font(.footnote).foregroundStyle(DS.textSecondary)
        case .result(let result):
            resultLine(result, font: Font.footnote.weight(.semibold))
        }
    }

    // MARK: Controls

    private func perform(_ action: ExactScoreMapAction10868?) {
        switch action {
        case .selectScope(let id)?:
            onSelectScope?(id)
        case .selectOriginal(let scopeID, let originalID)?:
            onSelectOriginal?(scopeID, originalID)
        case .details(let scopeID, let originalID)?:
            onDetails?(scopeID, originalID)
        case .recover?:
            onRecoverSelection?()
        case nil:
            break
        }
    }

    /// A button only when the owner supplied the callback and the identity is
    /// unambiguous; otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: ExactScoreMapAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                perform(action)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - Exact set finishes (tennis, final only)

// #10868 — the tennis "Exact set finishes" card on the final: two named player
// groups, each with that player's finish tiles (2–0, 2–1; 3–0, 3–1, 3–2 when
// three sets win). Every tile shows its original's pre-match chance, the set
// score, two rows of set-count blocks and that original's own result.
//
// Presentation only, from the approved browser reference
// (`TennisScoreOutcomeCard.tsx` + `tennisScoreOutcome.css`, tennis-final
// "Exact set finishes"). It composes the map input above rather than a second
// model: the same exact-match scope, originals, pregame readings, results,
// actual score, phase, exact-id selection, comparisons and actions. The soccer
// map itself and its lifecycle are unchanged.
//
// The owner supplies each player group, which original each finish names, the
// score and unit words, the block counts and their spoken words. This layer
// never parses an outcome label, never looks up a family, never derives a score,
// a winner or a grade from the blocks, and never reads a later quote: the chance
// is the original's pregame reading and the result is its own. A tile's blocks
// count sets won by each player; they are not playing order. The actual match
// score is separate context and never selects or grades a tile.
//
// A tile shows its original only when the identity is exact: a nonblank original
// named by one tile on the card and held by one original of the scope, under a
// nonblank player identity used once. Anything else shows the owner's
// unavailable words and attaches nothing, and every original no tile places
// stays named and reachable below the groups.
//
// Before and during play the card shows nothing. Selection, Details, recovery,
// Back and focus stay with the host; with no callback the content is static and
// no tap is asked for.

/// One block in a set-count row.
nonisolated enum ExactScoreFinishBlock10868: Equatable {
    /// A set won by the finishing player.
    case player
    /// A set won by the opponent.
    case opponent
    case empty
}

/// The owner's block counts for one finish — display geometry only, never a
/// grade or a winner.
nonisolated struct ExactScoreFinishSetCounts10868: Equatable {
    /// Blocks in each row: the sets needed to win (2 or 3).
    let slots: Int
    /// Filled blocks in the finishing player's row.
    let player: Int
    /// Filled blocks in the opponent's row, counted from the leading edge.
    let opponent: Int

    /// The player's row, then the opponent's. Nil unless the counts describe a
    /// finish in a known format: the player holds every slot and the opponent
    /// fewer. Malformed counts draw no blocks — they are never clamped.
    var blocks: [[ExactScoreFinishBlock10868]]? {
        guard (2...3).contains(slots), player == slots, (0..<slots).contains(opponent) else { return nil }
        return [
            (0..<slots).map { _ in ExactScoreFinishBlock10868.player },
            (0..<slots).map { $0 < opponent ? ExactScoreFinishBlock10868.opponent : .empty },
        ]
    }
}

/// One finish tile.
nonisolated struct ExactScoreFinishTile10868: Equatable {
    /// The original this finish names, exactly. Nil when the owner lists no
    /// original for this finish.
    let originalID: String?
    /// "2–0"
    let score: String
    /// "sets"
    let unit: String
    let counts: ExactScoreFinishSetCounts10868
    /// "Alejandro Davidovich Fokina 2 sets, Frances Tiafoe 0 sets" — what the blocks show.
    let countsSpoken: String
}

/// One player's group of finishes, in the owner's order.
nonisolated struct ExactScoreFinishPlayer10868: Equatable {
    /// Opaque owner identity.
    let id: String
    /// The full name, shown verbatim.
    let name: String
    let tiles: [ExactScoreFinishTile10868]
}

/// The card's own words. Everything else comes from the map's words.
nonisolated struct ExactScoreFinishWords10868: Equatable {
    /// "Sets won · best of 3" — the owner's format line, never computed.
    let countsKey: String
    /// "Blocks count sets won by each player; they do not show playing order."
    let countsNote: String
    /// "Set blocks unavailable" — in place of malformed counts.
    let countsUnavailable: String
    /// "Finish unavailable" — a tile whose original cannot be named exactly.
    let finishUnavailable: String
    /// "Tap a finish to compare it." — only when a shown control can act.
    let tapInvitation: String
}

/// What one tile shows.
nonisolated enum ExactScoreFinishTileState10868: Equatable {
    /// Exactly one original, named exactly.
    case placed(ExactScoreMapOriginal10868)
    /// The owner lists no original for this finish (the map's "not listed" words).
    case notListed(String)
    /// The named original is blank, missing, foreign, duplicated or claimed twice,
    /// or the player's identity is not usable.
    case unavailable(String)
}

/// A placed original's final readings, from the map's own comparisons.
nonisolated struct ExactScoreFinishReadings10868: Equatable {
    /// The pregame reading or its unavailable words.
    let chance: ExactScoreMapComparison10868
    /// The original's own result.
    let result: ExactScoreMapComparison10868
}

nonisolated struct ExactScoreFinishInput10868: Equatable {
    /// The existing map input: phase, title, intro, the exact-match scope (its
    /// originals non-grid here), the held scope and original, the actual score
    /// and the words.
    let map: ExactScoreMapInput10868
    /// In the owner's order — never sorted by chance or result.
    let players: [ExactScoreFinishPlayer10868]
    let words: ExactScoreFinishWords10868

    /// Final only. Before and during play no finish, chance, result or action exists.
    var isShown: Bool {
        map.phase == .final
    }

    /// The held scope through the map's exact-id selection. Nil before the final
    /// and for a missing, duplicated or blank scope; a valid id is kept verbatim.
    var scope: ExactScoreMapScope10868? {
        guard isShown, let scope = map.scopeSelection.scope, !Self.isBlank(scope.id) else { return nil }
        return scope
    }

    static func isBlank(_ id: String) -> Bool {
        id.allSatisfy(\.isWhitespace)
    }

    /// A player identity that is nonblank and used once on the card.
    func isPlaceable(_ player: ExactScoreFinishPlayer10868) -> Bool {
        !Self.isBlank(player.id) && players.filter { $0.id == player.id }.count == 1
    }

    /// How many tiles on the card name this original.
    func tileCount(naming id: String) -> Int {
        players.reduce(0) { count, player in count + player.tiles.filter { $0.originalID == id }.count }
    }

    /// Nil when the card is not shown.
    func state(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868) -> ExactScoreFinishTileState10868? {
        guard let scope else { return nil }
        guard let id = tile.originalID else { return .notListed(map.words.notListed) }
        let matches = scope.originals.filter { $0.id == id }
        guard isPlaceable(player), !Self.isBlank(id), tileCount(naming: id) == 1, matches.count == 1 else {
            return .unavailable(words.finishUnavailable)
        }
        return .placed(matches[0])
    }

    /// Every original of the scope that no tile places, in the owner's order.
    var unplaced: [ExactScoreMapOriginal10868] {
        guard let scope else { return [] }
        var placed = Set<String>()
        for player in players {
            for tile in player.tiles {
                if case .placed(let original)? = state(tile, of: player) { placed.insert(original.id) }
            }
        }
        return scope.originals.filter { !placed.contains($0.id) }
    }

    /// The held original through the map's exact-id selection. A blank identity
    /// is unavailable, never a selection.
    var selection: ExactScoreMapOriginalSelection10868 {
        guard let scope else { return .unselected }
        let selection = map.originalSelection(in: scope)
        if case .selected(let original) = selection, Self.isBlank(original.id) { return .missing(original.id) }
        return selection
    }

    func isSelected(_ original: ExactScoreMapOriginal10868) -> Bool {
        selection.original?.id == original.id
    }

    func isSelected(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868) -> Bool {
        guard case .placed(let original)? = state(tile, of: player) else { return false }
        return isSelected(original)
    }

    // MARK: Readings

    /// The map's final comparisons: the pregame reading, then the original's own
    /// result. A later quote is never read. Empty when the card is not shown.
    func comparisons(_ original: ExactScoreMapOriginal10868) -> [ExactScoreMapComparison10868] {
        isShown ? map.comparisons(original) : []
    }

    func readings(_ original: ExactScoreMapOriginal10868) -> ExactScoreFinishReadings10868? {
        let items = comparisons(original)
        guard items.count == 2 else { return nil }
        return ExactScoreFinishReadings10868(chance: items[0], result: items[1])
    }

    /// The separately labelled actual score — context, never a grade.
    var visibleActual: ExactScoreMapActual10868? {
        guard let scope else { return nil }
        return map.visibleActual(scope)
    }

    // MARK: Actions

    /// The map's own select action, for a placed tile only.
    func selectAction(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868, canSelect: Bool) -> ExactScoreMapAction10868? {
        guard case .placed(let original)? = state(tile, of: player) else { return nil }
        return map.selectAction(original, canSelect: canSelect)
    }

    /// The map's own select action, for an original of the scope named below the groups.
    /// Membership is the map's exact-id uniqueness, never the whole payload: an ignored
    /// later reading cannot close a unique original, and a foreign or repeated id has no action.
    func choiceAction(_ original: ExactScoreMapOriginal10868, canSelect: Bool) -> ExactScoreMapAction10868? {
        guard scope != nil, !Self.isBlank(original.id) else { return nil }
        return map.selectAction(original, canSelect: canSelect)
    }

    /// The map's own Details action, only for a resolved held original.
    func detailsAction(canOpen: Bool) -> ExactScoreMapAction10868? {
        guard scope != nil, selection.original != nil else { return nil }
        return map.detailsAction(canOpen: canOpen)
    }

    /// The owner's recovery, offered only while no original is resolved.
    func recoverAction(canRecover: Bool) -> ExactScoreMapAction10868? {
        guard scope != nil, canRecover, selection.original == nil else { return nil }
        return .recover
    }

    /// True only when a shown tile or named original carries a real action.
    func showsTapInvitation(canSelect: Bool) -> Bool {
        players.contains { player in
            player.tiles.contains { selectAction($0, of: player, canSelect: canSelect) != nil }
        } || unplaced.contains { choiceAction($0, canSelect: canSelect) != nil }
    }

    // MARK: VoiceOver

    /// A placed tile names its original and scope; any other names the player and finish.
    func accessibilityLabel(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868) -> String {
        guard let scope, let state = state(tile, of: player) else { return "" }
        if case .placed(let original) = state { return map.accessibilityLabel(original, in: scope) }
        return "\(player.name), \(tile.score) \(tile.unit)"
    }

    /// The block counts, then the original's chance with its clock and source, then its own result.
    func accessibilityValue(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868) -> String {
        switch state(tile, of: player) {
        case .placed(let original)?:
            let counts = tile.counts.blocks == nil ? words.countsUnavailable : tile.countsSpoken
            return "\(counts); \(map.spokenComparisons(original))"
        case .notListed(let text)?, .unavailable(let text)?:
            return text
        case nil:
            return ""
        }
    }

    func accessibilitySummary(_ original: ExactScoreMapOriginal10868) -> String {
        guard let scope else { return "" }
        return map.accessibilitySummary(original, in: scope)
    }
}

nonisolated enum ExactScoreFinishArrangement10868: Equatable {
    /// Every tile side by side at an equal width.
    case row
    /// One tile per line, full width.
    case stack
}

nonisolated struct ExactScoreFinishTileWidth10868: Equatable {
    let arrangement: ExactScoreFinishArrangement10868
    /// Every tile's width.
    let width: CGFloat
}

nonisolated struct ExactScoreFinishTilePlan10868: Equatable {
    let arrangement: ExactScoreFinishArrangement10868
    let frames: [CGRect]
    let size: CGSize
}

nonisolated enum ExactScoreFinishGeometry10868 {
    /// Tiles share one row at equal widths only when that share still holds every
    /// tile's widest whole line and a 44 pt target; otherwise they stack at full
    /// width, and always at accessibility sizes. Nil for malformed input.
    static func tileWidth(available: CGFloat, idealWidths: [CGFloat], spacing: CGFloat, minimumTile: CGFloat = 44,
                          accessibilitySize: Bool) -> ExactScoreFinishTileWidth10868? {
        guard !idealWidths.isEmpty, idealWidths.allSatisfy({ $0.isFinite && $0 >= 0 }),
              spacing.isFinite, spacing >= 0, minimumTile.isFinite, minimumTile >= 0,
              !available.isNaN, available >= 0 else { return nil }
        let count = CGFloat(idealWidths.count)
        let widest = max(idealWidths.max() ?? 0, minimumTile)
        guard available.isFinite else {
            return ExactScoreFinishTileWidth10868(arrangement: accessibilitySize ? .stack : .row, width: widest)
        }
        let share = (available - spacing * (count - 1)) / count
        if !accessibilitySize, share >= widest {
            return ExactScoreFinishTileWidth10868(arrangement: .row, width: share)
        }
        return ExactScoreFinishTileWidth10868(arrangement: .stack, width: available)
    }

    /// Frames for tiles of the given width and heights. A row takes its tallest
    /// tile's height for every tile; a stack keeps each height. No tile is
    /// shorter than `minimumTile`.
    static func plan(_ width: ExactScoreFinishTileWidth10868, heights: [CGFloat], spacing: CGFloat,
                     minimumTile: CGFloat = 44) -> ExactScoreFinishTilePlan10868? {
        guard !heights.isEmpty, heights.allSatisfy({ $0.isFinite && $0 >= 0 }),
              width.width.isFinite, width.width >= 0, spacing.isFinite, spacing >= 0,
              minimumTile.isFinite, minimumTile >= 0 else { return nil }
        let count = heights.count
        switch width.arrangement {
        case .row:
            let height = max(heights.max() ?? 0, minimumTile)
            let frames = (0..<count).map { index in
                CGRect(x: CGFloat(index) * (width.width + spacing), y: 0, width: width.width, height: height)
            }
            let size = CGSize(width: CGFloat(count) * width.width + CGFloat(count - 1) * spacing, height: height)
            return ExactScoreFinishTilePlan10868(arrangement: .row, frames: frames, size: size)
        case .stack:
            var frames: [CGRect] = []
            var y: CGFloat = 0
            for height in heights {
                let tile = max(height, minimumTile)
                frames.append(CGRect(x: 0, y: y, width: width.width, height: tile))
                y += tile + spacing
            }
            return ExactScoreFinishTilePlan10868(arrangement: .stack, frames: frames,
                                                 size: CGSize(width: width.width, height: y - spacing))
        }
    }
}

/// One player's tiles: side by side when every tile fits whole, else stacked.
/// The size it reports is the plan it places.
struct ExactScoreFinishTileLayout10868: Layout {
    var spacing: CGFloat = 8
    let accessibilitySize: Bool

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        plan(available: proposal.width ?? .infinity, subviews: subviews)?.size ?? .zero
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let plan = self.plan(available: bounds.width, subviews: subviews) else { return }
        for (index, frame) in plan.frames.enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                  anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(available: CGFloat, subviews: Subviews) -> ExactScoreFinishTilePlan10868? {
        let ideal = subviews.map { $0.sizeThatFits(.unspecified).width }
        guard let width = ExactScoreFinishGeometry10868.tileWidth(available: available, idealWidths: ideal,
                                                                  spacing: spacing, accessibilitySize: accessibilitySize) else { return nil }
        let heights = subviews.map { $0.sizeThatFits(ProposedViewSize(width: width.width, height: nil)).height }
        return ExactScoreFinishGeometry10868.plan(width, heights: heights, spacing: spacing)
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum ExactScoreFinishAccessibilityID10868 {
    static let summary = "exactScoreFinish10868.summary"
    static let details = "exactScoreFinish10868.details"
    static let recover = "exactScoreFinish10868.recover"
    static func tile(_ originalID: String) -> String { "exactScoreFinish10868.tile.\(originalID)" }
    static func slot(player: Int, tile: Int) -> String { "exactScoreFinish10868.slot.\(player).\(tile)" }
    static func choice(_ id: String) -> String { "exactScoreFinish10868.choice.\(id)" }
}

/// The one path from a control's action to the owner's callback, exactly as supplied.
nonisolated enum ExactScoreFinishRouting10868 {
    static func route(_ action: ExactScoreMapAction10868?, onSelectOriginal: ((String, String) -> Void)?,
                      onDetails: ((String, String) -> Void)?, onRecoverSelection: (() -> Void)?) {
        switch action {
        case .selectOriginal(let scopeID, let originalID)?:
            onSelectOriginal?(scopeID, originalID)
        case .details(let scopeID, let originalID)?:
            onDetails?(scopeID, originalID)
        case .recover?:
            onRecoverSelection?()
        case .selectScope?, nil:
            break
        }
    }
}

struct ExactScoreFinishPresentation10868: View {
    let input: ExactScoreFinishInput10868
    /// (scope id, original id), exactly as supplied.
    var onSelectOriginal: ((String, String) -> Void)? = nil
    /// (scope id, original id), exactly as supplied.
    var onDetails: ((String, String) -> Void)? = nil
    var onRecoverSelection: (() -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title3) private var chanceSize: CGFloat = 18
    @ScaledMetric(relativeTo: .title) private var scoreSize: CGFloat = 24
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .caption) private var blockWidth: CGFloat = 14
    @ScaledMetric(relativeTo: .caption) private var blockHeight: CGFloat = 6

    private var canSelect: Bool { onSelectOriginal != nil }
    private var canOpenDetails: Bool { onDetails != nil }
    private var canRecover: Bool { onRecoverSelection != nil }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 14) {
                header
                if let scope = input.scope {
                    actual
                    ForEach(Array(input.players.enumerated()), id: \.offset) { index, player in
                        group(player, index: index)
                    }
                    notes
                    choices(scope)
                    summary(scope)
                } else {
                    Text(input.map.words.scopeUnavailable)
                        .font(.headline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(input.map.title)
                .font(.title2.bold())
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            if let intro = input.map.intro {
                Text(intro).font(.subheadline).foregroundStyle(DS.textSecondary)
            }
            Text(input.words.countsKey).font(.caption).foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var actual: some View {
        if let actual = input.visibleActual {
            VStack(alignment: .leading, spacing: 2) {
                Text(actual.title).font(.caption).foregroundStyle(DS.textSecondary)
                Text(actual.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
        }
    }

    // MARK: Player groups

    private func group(_ player: ExactScoreFinishPlayer10868, index: Int) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(player.name)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            ExactScoreFinishTileLayout10868(accessibilitySize: typeSize.isAccessibilitySize) {
                ForEach(Array(player.tiles.enumerated()), id: \.offset) { tileIndex, tile in
                    self.tile(tile, of: player, playerIndex: index, tileIndex: tileIndex)
                }
            }
        }
    }

    @ViewBuilder
    private func tile(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868,
                      playerIndex: Int, tileIndex: Int) -> some View {
        switch input.state(tile, of: player) {
        case .placed(let original)?:
            placedTile(tile, of: player, original: original)
        case .notListed(let text)?, .unavailable(let text)?:
            chrome(selected: false, dashed: true) {
                VStack(spacing: 8) {
                    score(tile)
                    Text(text)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityLabel(tile, of: player))
            .accessibilityValue(input.accessibilityValue(tile, of: player))
            .accessibilityIdentifier(ExactScoreFinishAccessibilityID10868.slot(player: playerIndex, tile: tileIndex))
        case nil:
            EmptyView()
        }
    }

    private func placedTile(_ tile: ExactScoreFinishTile10868, of player: ExactScoreFinishPlayer10868,
                            original: ExactScoreMapOriginal10868) -> some View {
        let action = input.selectAction(tile, of: player, canSelect: canSelect)
        let selected = input.isSelected(tile, of: player)
        let readings = input.readings(original)
        return control(action) {
            chrome(selected: selected, dashed: false) {
                VStack(spacing: 8) {
                    if let readings { chance(readings.chance) }
                    score(tile)
                    blocks(tile.counts)
                    if let readings { resultLine(readings.result) }
                }
            }
        }
        .accessibilityLabel(input.accessibilityLabel(tile, of: player))
        .accessibilityValue(input.accessibilityValue(tile, of: player))
        .accessibilityHint(action == nil ? "" : input.map.words.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(ExactScoreFinishAccessibilityID10868.tile(original.id))
    }

    /// The tile face. The selection is an outer outline; the result is its own
    /// mark and words inside — two separate channels, neither colour alone.
    private func chrome<Content: View>(selected: Bool, dashed: Bool, @ViewBuilder content: () -> Content) -> some View {
        content()
            .multilineTextAlignment(.center)
            .padding(.vertical, 10)
            .padding(.horizontal, 6)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(dashed ? DS.textSecondary : DS.border, style: StrokeStyle(lineWidth: 1, dash: dashed ? [3, 3] : []))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 15)
                    .stroke(selected ? DS.textPrimary : Color.clear, lineWidth: 2.5)
                    .padding(-3)
            )
            .contentShape(Rectangle())
    }

    @ViewBuilder
    private func chance(_ item: ExactScoreMapComparison10868) -> some View {
        VStack(spacing: 2) {
            switch item.reading {
            case .figure(let observation):
                Text(observation.text)
                    .font(.system(size: chanceSize, weight: .bold))
                    .monospacedDigit()
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: true, vertical: false)
            case .words(let text):
                Text(text)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .result(let result):
                Text(result.text)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Text(item.title)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func score(_ tile: ExactScoreFinishTile10868) -> some View {
        VStack(spacing: 0) {
            Text(tile.score)
                .font(.system(size: scoreSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: true, vertical: false)
            Text(tile.unit)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Two rows of counts: the finishing player's sets, then the opponent's.
    @ViewBuilder
    private func blocks(_ counts: ExactScoreFinishSetCounts10868) -> some View {
        if let rows = counts.blocks {
            VStack(spacing: 4) {
                ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                    HStack(spacing: 3) {
                        ForEach(Array(row.enumerated()), id: \.offset) { _, block in
                            blockMark(block)
                        }
                    }
                }
            }
            .accessibilityHidden(true)
        } else {
            Text(input.words.countsUnavailable)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// Filled for a player's set, grey for the opponent's, an empty outline otherwise.
    private func blockMark(_ block: ExactScoreFinishBlock10868) -> some View {
        let fill: Color
        switch block {
        case .player: fill = DS.blue
        case .opponent: fill = DS.textSecondary
        case .empty: fill = Color.clear
        }
        return RoundedRectangle(cornerRadius: 2)
            .fill(fill)
            .overlay(RoundedRectangle(cornerRadius: 2).stroke(block == .empty ? DS.border : Color.clear, lineWidth: 1))
            .frame(width: blockWidth, height: blockHeight)
    }

    @ViewBuilder
    private func resultLine(_ item: ExactScoreMapComparison10868) -> some View {
        if case .result(let result) = item.reading {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                switch result.mark {
                case .won?:
                    Image(systemName: "checkmark.circle").accessibilityHidden(true)
                case .lost?:
                    Image(systemName: "xmark.circle").accessibilityHidden(true)
                case nil:
                    EmptyView()
                }
                Text(result.text).fixedSize(horizontal: false, vertical: true)
            }
            .font(.footnote.weight(result.isWon ? .bold : .regular))
            .foregroundStyle(result.isWon ? DS.textPrimary : DS.textSecondary)
        }
    }

    // MARK: Notes

    private var notes: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(input.words.countsNote)
            if input.showsTapInvitation(canSelect: canSelect) {
                Text(input.words.tapInvitation)
            }
        }
        .font(.caption)
        .foregroundStyle(DS.textSecondary)
        .fixedSize(horizontal: false, vertical: true)
    }

    // MARK: Named originals

    @ViewBuilder
    private func choices(_ scope: ExactScoreMapScope10868) -> some View {
        let list = input.unplaced
        if !list.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(input.map.words.otherChoicesTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(Array(list.enumerated()), id: \.offset) { _, original in
                    choice(original, in: scope)
                }
            }
        }
    }

    private func choice(_ original: ExactScoreMapOriginal10868, in scope: ExactScoreMapScope10868) -> some View {
        let action = input.choiceAction(original, canSelect: canSelect)
        let selected = input.isSelected(original)
        let readings = input.readings(original)
        return control(action) {
            VStack(alignment: .leading, spacing: 4) {
                Text(original.label)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .underline(selected)
                    .foregroundStyle(DS.textPrimary)
                if let readings {
                    FlowLayout(spacing: 6) {
                        Text(readings.chance.title).font(.caption).foregroundStyle(DS.textSecondary)
                        choiceChance(readings.chance.reading)
                    }
                    resultLine(readings.result)
                }
            }
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(selected ? DS.textPrimary : Color.clear, lineWidth: 2)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.map.accessibilityLabel(original, in: scope))
        .accessibilityValue(input.map.spokenComparisons(original))
        .accessibilityHint(action == nil ? "" : input.map.words.selectHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(ExactScoreFinishAccessibilityID10868.choice(original.id))
    }

    @ViewBuilder
    private func choiceChance(_ reading: ExactScoreMapReading10868) -> some View {
        switch reading {
        case .figure(let observation):
            Text(observation.text).font(.subheadline.weight(.semibold)).monospacedDigit().foregroundStyle(DS.textPrimary)
        case .words(let text):
            Text(text).font(.footnote).foregroundStyle(DS.textSecondary)
        case .result(let result):
            Text(result.text).font(.footnote).foregroundStyle(DS.textSecondary)
        }
    }

    // MARK: Selected summary

    @ViewBuilder
    private func summary(_ scope: ExactScoreMapScope10868) -> some View {
        switch input.selection {
        case .selected(let original):
            VStack(alignment: .leading, spacing: 10) {
                VStack(alignment: .leading, spacing: 10) {
                    Text(original.label).font(.headline).foregroundStyle(DS.textPrimary)
                    ForEach(Array(input.comparisons(original).enumerated()), id: \.offset) { _, item in
                        VStack(alignment: .leading, spacing: 2) {
                            Text(item.title).font(.caption).foregroundStyle(DS.textSecondary)
                            summaryReading(item.reading)
                        }
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(input.map.accessibilityLabel(original, in: scope))
                .accessibilityValue(input.accessibilitySummary(original))
                .accessibilityIdentifier(ExactScoreFinishAccessibilityID10868.summary)
                if let action = input.detailsAction(canOpen: canOpenDetails) {
                    Button { perform(action) } label: {
                        HStack(spacing: 6) {
                            Text(input.map.words.details)
                            Image(systemName: "chevron.right").font(.caption).accessibilityHidden(true)
                        }
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                        .contentShape(Rectangle())
                    }
                    .accessibilityHint(input.map.words.detailsHint)
                    .accessibilityIdentifier(ExactScoreFinishAccessibilityID10868.details)
                }
            }
        case .unselected:
            unresolved(input.map.words.noSelection)
        case .missing, .duplicate:
            unresolved(input.map.words.selectionUnavailable)
        }
    }

    /// The selected original's pregame figure keeps its visible clock and source.
    @ViewBuilder
    private func summaryReading(_ reading: ExactScoreMapReading10868) -> some View {
        switch reading {
        case .figure(let observation):
            Text(observation.text)
                .font(.system(size: figureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: true, vertical: false)
            Text(observation.detail)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .words(let text):
            Text(text)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .result:
            resultLine(ExactScoreMapComparison10868(title: "", reading: reading))
        }
    }

    private func unresolved(_ notice: String) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(notice)
                .font(.headline)
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let action = input.recoverAction(canRecover: canRecover) {
                Button(input.map.words.recoverSelection) { perform(action) }
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .frame(minWidth: 44, minHeight: 44, alignment: .leading)
                    .accessibilityIdentifier(ExactScoreFinishAccessibilityID10868.recover)
            }
        }
    }

    // MARK: Controls

    private func perform(_ action: ExactScoreMapAction10868?) {
        ExactScoreFinishRouting10868.route(action, onSelectOriginal: onSelectOriginal, onDetails: onDetails,
                                           onRecoverSelection: onRecoverSelection)
    }

    /// A button only when the owner supplied the callback and the identity is
    /// exact; otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: ExactScoreMapAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                perform(action)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}

// MARK: - Exact set finishes during play (tennis, live lanes)

// #10868 — the tennis "Exact set finishes" card during play: one compact named
// lane per finish, in the owner's order. Each lane is a short stack of titled
// rows: the original's pre-match chance as a prominent figure with its bar on
// one fixed 0–100% scale; the original's current reading (a figure gets its own
// bar on the same scale) or its own unavailable words; the owner's physical
// availability; and the original's own result under the owner's title.
//
// Presentation only, from the approved browser reference (`LiveTennis.tsx`
// `kind === 'exact'` + `liveTennis.css` `.lt-finish-*`, v272 tennis finish
// comparison). It composes the map input above rather than a second model: the
// same exact-match scope, originals, pregame readings, current readings,
// results, actual score, phase, exact-id selection, comparisons and exact-id
// uniqueness. The soccer map and the final finish tiles are unchanged.
//
// The owner supplies each lane: the original it names, a fallback label, its
// physical availability ("Still possible" / "No longer possible") and a colour.
// This layer never derives availability from a score, a label, a result or a
// chance, never matches a lane to a player, never ranks or sorts, and never
// reads a later quote as current. A ruled-out lane keeps its pre-match chance
// fully legible: the hatch and words say the finish can no longer happen, which
// is not a loss, not a selection, not a zero and not the market's result.
//
// Every row names its own channel with the owner's title, so a reader never
// has to tell pre-match from current, or an unavailable current from the
// finish's availability, by position or by the wording of a reason. A row puts
// its value beside its title only when both fit whole; otherwise the value sits
// below the title within the lane's width and wraps — never shrunk, capped or
// hidden.
//
// The bars use one explicit 0–100% probability scale across the full lane
// width, never the map's cropped shading scale and never a domain that moves
// with the data or the selection. A missing, non-finite or out-of-range
// reading draws no fill and is never clamped; a quoted zero keeps its figure
// and a zero mark.
//
// A lane shows its original only when the identity is exact: a nonblank original
// named by one lane on the card and held by one original of the scope. Anything
// else shows the owner's words and attaches nothing, and every original no lane
// places stays named below the lanes — with its readings and Details only when
// its own identity is exact, otherwise with the owner's unavailable words.
//
// Before play and after the final the card shows nothing; the final finish
// tiles above stay the final's card. Details, Back, focus, held refresh and
// withdrawal stay with the host: with no callback the content is static and no
// tap is asked for.

/// The owner's physical availability for one finish — presentation only, never
/// a grade, a chance or a settlement.
nonisolated enum ExactScoreFinishLaneAvailability10868: Equatable {
    /// "Still possible"
    case open(String)
    /// "No longer possible" — drawn hatched.
    case ruledOut(String)

    var text: String {
        switch self {
        case .open(let text), .ruledOut(let text): text
        }
    }

    var isRuledOut: Bool {
        if case .ruledOut = self { return true }
        return false
    }
}

/// The owner's colour for a lane's figures and bars. A ruled-out lane is drawn
/// in the secondary colour whatever its tone.
nonisolated enum ExactScoreFinishLaneTone10868: Equatable {
    case home
    case away
}

/// One finish lane, in the owner's order.
nonisolated struct ExactScoreFinishLane10868: Equatable {
    /// The original this finish names, exactly. Nil when the owner lists no
    /// original for this finish.
    let originalID: String?
    /// "Fils 2–1" — shown whenever no original can be named exactly.
    let fallbackLabel: String
    let availability: ExactScoreFinishLaneAvailability10868
    let tone: ExactScoreFinishLaneTone10868
}

/// The card's own words. Everything else comes from the map's words.
nonisolated struct ExactScoreFinishLaneWords10868: Equatable {
    /// "EXACT FINISH · SETS"
    let eyebrow: String?
    /// "Pre-match chances · same 0–100% scale"
    let scaleKey: String
    /// "Finish status" — the title beside the owner's availability words.
    let availabilityTitle: String
    /// "Original market result" — the title beside an original's own result.
    let originalResultTitle: String
    /// "Finish unavailable" — a lane, or a named original, whose identity is not exact.
    let laneUnavailable: String
    /// The owner's match-context note ("Fils lost set 1, ruling out 2–0."), never computed.
    let contextNote: String?
}

/// What one lane shows.
nonisolated enum ExactScoreFinishLaneState10868: Equatable {
    /// Exactly one original, named exactly.
    case placed(ExactScoreMapOriginal10868)
    /// The owner lists no original for this finish (the map's "not listed" words).
    case notListed(String)
    /// The named original is blank, missing, foreign, duplicated or claimed twice.
    case unavailable(String)
}

/// One bar on the fixed 0–100% scale.
nonisolated enum ExactScoreFinishLaneBar10868: Equatable {
    /// Position on the scale, 0...1. Zero is a real quoted zero.
    case fill(Double)
    /// No reading the scale can place — no fill, never clamped.
    case noFill
}

/// An original's readings during play, from the map's own comparisons.
nonisolated struct ExactScoreFinishLaneReadings10868: Equatable {
    /// The pregame reading or its unavailable words.
    let chance: ExactScoreMapComparison10868
    /// The independently admitted current reading or its own words — or, once
    /// admitted during play, the original's own result.
    let second: ExactScoreMapComparison10868
    /// The original's own result while it is not admitted, under the owner's
    /// title. Nil once admitted: it is then `second`.
    let pendingResult: ExactScoreMapComparison10868?

    var chanceBar: ExactScoreFinishLaneBar10868 {
        ExactScoreFinishLaneGeometry10868.bar(chance.reading)
    }

    /// A bar for an admitted current figure only.
    var secondBar: ExactScoreFinishLaneBar10868? {
        guard case .figure = second.reading else { return nil }
        return ExactScoreFinishLaneGeometry10868.bar(second.reading)
    }
}

/// What one titled row of a lane shows.
nonisolated enum ExactScoreFinishLaneChannelValue10868: Equatable {
    /// The owner's figure, drawn large.
    case figure(ExactScoreMapObservation10868)
    /// The owner's unavailable words for this channel.
    case words(String)
    /// An original's own result.
    case result(ExactScoreMapResult10868)
    /// The owner's physical availability, with its own mark.
    case availability(ExactScoreFinishLaneAvailability10868)
}

/// One visible row: its title, its value and, for a chance, its bar.
nonisolated struct ExactScoreFinishLaneChannel10868: Equatable {
    /// The owner's title for this channel ("Pre-match chance", "Current chance").
    let title: String
    let value: ExactScoreFinishLaneChannelValue10868
    /// Drawn under the row across the full lane width on the fixed scale. Nil: no bar.
    let bar: ExactScoreFinishLaneBar10868?
    /// The owner's ruled-out availability on this row's bar or mark — never a
    /// result, a selection or a zero.
    let hatched: Bool
}

/// Explicit phase-specific owner copy opts the existing lanes into before play.
/// Nil optional fields remain absent, never replaced by live match context.
nonisolated struct ExactScoreFinishLaneBefore10868: Equatable {
    let title: String
    let intro: String?
    let eyebrow: String?
    let contextNote: String?
}

nonisolated struct ExactScoreFinishLaneInput10868: Equatable {
    /// The existing map input: phase, title, intro, the exact-match scope (its
    /// originals non-grid here), the held scope and original, the actual score
    /// and the words.
    let map: ExactScoreMapInput10868
    /// In the owner's order — never sorted by chance, availability or result.
    let lanes: [ExactScoreFinishLane10868]
    let words: ExactScoreFinishLaneWords10868
    /// Default off; does not rewrite the map's actual phase or its truth inputs.
    var beforePresentation: ExactScoreFinishLaneBefore10868? = nil

    /// During play by default, before only by explicit admission; never final.
    var isShown: Bool {
        map.phase == .during || (map.phase == .before && beforePresentation != nil)
    }

    private var admittedBeforeCopy: ExactScoreFinishLaneBefore10868? {
        map.phase == .before ? beforePresentation : nil
    }

    var displayedTitle: String { admittedBeforeCopy?.title ?? map.title }
    var displayedIntro: String? {
        guard let before = admittedBeforeCopy else { return map.intro }
        return before.intro
    }
    var displayedEyebrow: String? {
        guard let before = admittedBeforeCopy else { return words.eyebrow }
        return before.eyebrow
    }
    var displayedContextNote: String? {
        guard let before = admittedBeforeCopy else { return words.contextNote }
        return before.contextNote
    }

    /// Physical status affects live appearance only. Before keeps the owner's
    /// home/away tone even if retained later fields say the finish was ruled out.
    func dimsForAvailability(_ lane: ExactScoreFinishLane10868) -> Bool {
        map.phase == .during && lane.availability.isRuledOut
    }

    /// The held scope through the map's exact-id selection. Nil outside play and
    /// for a missing, duplicated or blank scope; a valid id is kept verbatim.
    var scope: ExactScoreMapScope10868? {
        guard isShown, let scope = map.scopeSelection.scope, !ExactScoreFinishInput10868.isBlank(scope.id) else { return nil }
        return scope
    }

    /// How many lanes on the card name this original.
    func laneCount(naming id: String) -> Int {
        lanes.filter { $0.originalID == id }.count
    }

    /// Nil when the card is not shown.
    func state(_ lane: ExactScoreFinishLane10868) -> ExactScoreFinishLaneState10868? {
        guard let scope else { return nil }
        guard let id = lane.originalID else { return .notListed(map.words.notListed) }
        let matches = scope.originals.filter { $0.id == id }
        guard !ExactScoreFinishInput10868.isBlank(id), laneCount(naming: id) == 1, matches.count == 1 else {
            return .unavailable(words.laneUnavailable)
        }
        return .placed(matches[0])
    }

    /// Every original of the scope that no lane places, in the owner's order.
    var unplaced: [ExactScoreMapOriginal10868] {
        guard let scope else { return [] }
        var placed = Set<String>()
        for lane in lanes {
            if case .placed(let original)? = state(lane) { placed.insert(original.id) }
        }
        return scope.originals.filter { !placed.contains($0.id) }
    }

    /// The held original through the map's exact-id selection. A blank identity
    /// is unavailable, never a selection.
    var selection: ExactScoreMapOriginalSelection10868 {
        guard let scope else { return .unselected }
        let selection = map.originalSelection(in: scope)
        if case .selected(let original) = selection, ExactScoreFinishInput10868.isBlank(original.id) { return .missing(original.id) }
        return selection
    }

    func isSelected(_ original: ExactScoreMapOriginal10868) -> Bool {
        selection.original?.id == original.id
    }

    /// A nonblank identity held by exactly one original of the shown scope — the
    /// map's exact-id uniqueness, never the whole payload, so a NaN reading
    /// cannot close a real original. Only an exact original shows readings.
    func isExact(_ original: ExactScoreMapOriginal10868) -> Bool {
        guard let scope, !ExactScoreFinishInput10868.isBlank(original.id) else { return false }
        return map.isUniqueOriginal(original.id, in: scope)
    }

    func isSelected(_ lane: ExactScoreFinishLane10868) -> Bool {
        guard case .placed(let original)? = state(lane) else { return false }
        return isSelected(original)
    }

    // MARK: Readings

    /// The map's during-play comparisons: the pregame reading, then the current
    /// reading or, once admitted, the original's own result. A later quote is
    /// never read as current. Empty when the card is not shown.
    func comparisons(_ original: ExactScoreMapOriginal10868) -> [ExactScoreMapComparison10868] {
        isShown ? map.comparisons(original) : []
    }

    /// Nil when the card is not shown or the original's identity is not exact.
    func readings(_ original: ExactScoreMapOriginal10868) -> ExactScoreFinishLaneReadings10868? {
        guard isExact(original) else { return nil }
        let items = comparisons(original)
        guard items.count == 2 else { return nil }
        let pending = original.result.isAdmitted
            ? nil
            : ExactScoreMapComparison10868(title: words.originalResultTitle, reading: .result(original.result))
        return ExactScoreFinishLaneReadings10868(chance: items[0], second: items[1], pendingResult: pending)
    }

    /// An original's titled rows, in order: the pre-match chance and its bar; the
    /// current figure and its own bar on the same scale, or the current words,
    /// or the admitted result; the owner's availability, when a lane supplies
    /// one; the original's own pending result. Empty when the card is not shown
    /// or the original's identity is not exact.
    func channels(_ original: ExactScoreMapOriginal10868,
                  availability: ExactScoreFinishLaneAvailability10868?) -> [ExactScoreFinishLaneChannel10868] {
        if map.phase == .before {
            guard isExact(original), let chance = comparisons(original).first else { return [] }
            // Reuse the map's one safe before comparison; never fabricate the
            // second reading required by the unchanged during-play helper.
            return [ExactScoreFinishLaneChannel10868(
                title: chance.title, value: Self.value(chance.reading),
                bar: ExactScoreFinishLaneGeometry10868.bar(chance.reading), hatched: false)]
        }
        guard let readings = readings(original) else { return [] }
        let ruledOut = availability?.isRuledOut ?? false
        var rows = [
            ExactScoreFinishLaneChannel10868(title: readings.chance.title, value: Self.value(readings.chance.reading),
                                             bar: readings.chanceBar, hatched: ruledOut),
            ExactScoreFinishLaneChannel10868(title: readings.second.title, value: Self.value(readings.second.reading),
                                             bar: readings.secondBar, hatched: ruledOut && readings.secondBar != nil),
        ]
        if let availability {
            rows.append(ExactScoreFinishLaneChannel10868(title: words.availabilityTitle, value: .availability(availability),
                                                         bar: nil, hatched: ruledOut))
        }
        if let pending = readings.pendingResult {
            rows.append(ExactScoreFinishLaneChannel10868(title: pending.title, value: Self.value(pending.reading), bar: nil, hatched: false))
        }
        return rows
    }

    /// A placed lane's rows; any other lane keeps only the owner's availability row.
    func channels(_ lane: ExactScoreFinishLane10868) -> [ExactScoreFinishLaneChannel10868] {
        switch state(lane) {
        case .placed(let original)?:
            return channels(original, availability: lane.availability)
        case .notListed?, .unavailable?:
            guard map.phase == .during else { return [] }
            return [ExactScoreFinishLaneChannel10868(title: words.availabilityTitle, value: .availability(lane.availability),
                                                     bar: nil, hatched: lane.availability.isRuledOut)]
        case nil:
            return []
        }
    }

    private static func value(_ reading: ExactScoreMapReading10868) -> ExactScoreFinishLaneChannelValue10868 {
        switch reading {
        case .figure(let observation): .figure(observation)
        case .words(let text): .words(text)
        case .result(let result): .result(result)
        }
    }

    /// The separately labelled actual score — context, never a chance, an
    /// availability or a grade.
    var visibleActual: ExactScoreMapActual10868? {
        guard map.phase == .during, let scope else { return nil }
        return map.visibleActual(scope)
    }

    // MARK: Actions

    /// The exact original's Details. Membership is the map's exact-id uniqueness,
    /// never the whole payload: an ignored later reading cannot close a unique
    /// original, and a foreign, repeated or blank id has no action. Availability,
    /// a pending result and a missing chance never disable it.
    func detailsAction(_ original: ExactScoreMapOriginal10868, canOpen: Bool) -> ExactScoreMapAction10868? {
        guard canOpen, isExact(original), let scope else { return nil }
        return .details(scopeID: scope.id, originalID: original.id)
    }

    /// A placed lane's Details only.
    func detailsAction(_ lane: ExactScoreFinishLane10868, canOpen: Bool) -> ExactScoreMapAction10868? {
        guard case .placed(let original)? = state(lane) else { return nil }
        return detailsAction(original, canOpen: canOpen)
    }

    // MARK: VoiceOver

    /// A placed lane names its original and scope; any other names the owner's fallback.
    func accessibilityLabel(_ lane: ExactScoreFinishLane10868) -> String {
        guard let scope, let state = state(lane) else { return "" }
        if case .placed(let original) = state { return map.accessibilityLabel(original, in: scope) }
        return lane.fallbackLabel
    }

    /// The chance with its clock and source and the current reading, then the
    /// owner's availability, then the original's own pending result — each titled.
    func accessibilityValue(_ lane: ExactScoreFinishLane10868) -> String {
        let availability = "\(words.availabilityTitle): \(lane.availability.text)"
        switch state(lane) {
        case .placed(let original)?:
            if map.phase == .before { return map.spokenComparisons(original) }
            var parts = [map.spokenComparisons(original), availability]
            if let pending = spokenPending(original) { parts.append(pending) }
            return parts.joined(separator: "; ")
        case .notListed(let text)?, .unavailable(let text)?:
            return map.phase == .before ? text : "\(text); \(availability)"
        case nil:
            return ""
        }
    }

    /// A named original below the lanes: its readings and pending result, no
    /// availability. An original whose identity is not exact says only the
    /// owner's unavailable words.
    func accessibilityValue(_ original: ExactScoreMapOriginal10868) -> String {
        guard scope != nil else { return "" }
        guard isExact(original) else { return words.laneUnavailable }
        var parts = [map.spokenComparisons(original)]
        if let pending = spokenPending(original) { parts.append(pending) }
        return parts.joined(separator: "; ")
    }

    private func spokenPending(_ original: ExactScoreMapOriginal10868) -> String? {
        guard map.phase == .during else { return nil }
        guard let pending = readings(original)?.pendingResult, case .result(let result) = pending.reading else { return nil }
        return "\(pending.title): \(result.text)"
    }
}

nonisolated struct ExactScoreFinishLaneRowPlan10868: Equatable {
    let arrangement: ExactScoreFinishArrangement10868
    let label: CGRect
    let value: CGRect
    let size: CGSize
}

nonisolated enum ExactScoreFinishLaneGeometry10868 {
    /// The one fixed probability scale every lane's bars share.
    static let scale = ExactScoreMapScale10868(lower: 0, upper: 1, ticks: [])

    /// A figure's place on the fixed scale. Words, and a value the scale cannot
    /// place, draw no fill — never clamped.
    static func bar(_ reading: ExactScoreMapReading10868) -> ExactScoreFinishLaneBar10868 {
        guard case .figure(let observation) = reading,
              let fraction = ExactScoreMapGeometry10868.fraction(observation.probability, scale: scale) else { return .noFill }
        return .fill(fraction)
    }

    /// The filled width of a track. Nil for no fill or a malformed track.
    static func fillWidth(_ bar: ExactScoreFinishLaneBar10868, track: CGFloat) -> CGFloat? {
        guard case .fill(let fraction) = bar, track.isFinite, track >= 0 else { return nil }
        return track * CGFloat(fraction)
    }

    /// One titled row. The value sits beside its title, centred on one line,
    /// only when both whole lines fit; otherwise — and always at accessibility
    /// sizes — the value sits below the title, both within `available`, each at
    /// its height wrapped to that width. Nothing is wider than `available`
    /// unless the width is unbounded. Nil for malformed input.
    ///
    /// - Parameters:
    ///   - labelIdeal / valueIdeal: each on one line.
    ///   - labelStackedHeight / valueStackedHeight: each wrapped to `available`.
    static func rowPlan(available: CGFloat, labelIdeal: CGSize, labelStackedHeight: CGFloat, valueIdeal: CGSize,
                        valueStackedHeight: CGFloat, spacing: CGFloat, accessibilitySize: Bool) -> ExactScoreFinishLaneRowPlan10868? {
        guard [labelIdeal, valueIdeal].allSatisfy({ $0.width.isFinite && $0.height.isFinite && $0.width >= 0 && $0.height >= 0 }),
              [labelStackedHeight, valueStackedHeight, spacing].allSatisfy({ $0.isFinite && $0 >= 0 }),
              !available.isNaN, available >= 0 else { return nil }
        let rowWidth = labelIdeal.width + spacing + valueIdeal.width
        if !accessibilitySize, !available.isFinite || rowWidth <= available {
            let width = available.isFinite ? available : rowWidth
            let height = max(labelIdeal.height, valueIdeal.height)
            return ExactScoreFinishLaneRowPlan10868(
                arrangement: .row,
                label: CGRect(x: 0, y: (height - labelIdeal.height) / 2, width: width - spacing - valueIdeal.width, height: labelIdeal.height),
                value: CGRect(x: width - valueIdeal.width, y: (height - valueIdeal.height) / 2, width: valueIdeal.width, height: valueIdeal.height),
                size: CGSize(width: width, height: height)
            )
        }
        guard available.isFinite else {
            let width = max(labelIdeal.width, valueIdeal.width)
            return ExactScoreFinishLaneRowPlan10868(
                arrangement: .stack,
                label: CGRect(x: 0, y: 0, width: width, height: labelIdeal.height),
                value: CGRect(x: 0, y: labelIdeal.height + spacing, width: valueIdeal.width, height: valueIdeal.height),
                size: CGSize(width: width, height: labelIdeal.height + spacing + valueIdeal.height)
            )
        }
        let valueWidth = min(valueIdeal.width, available)
        return ExactScoreFinishLaneRowPlan10868(
            arrangement: .stack,
            label: CGRect(x: 0, y: 0, width: available, height: labelStackedHeight),
            value: CGRect(x: 0, y: labelStackedHeight + spacing, width: valueWidth, height: valueStackedHeight),
            size: CGSize(width: available, height: labelStackedHeight + spacing + valueStackedHeight)
        )
    }
}

/// One titled row: the title, then the value. The size it reports is the plan it places.
struct ExactScoreFinishLaneRowLayout10868: Layout {
    var spacing: CGFloat = 8
    let accessibilitySize: Bool

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        plan(available: proposal.width ?? .infinity, subviews: subviews)?.size ?? .zero
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard let plan = self.plan(available: bounds.width, subviews: subviews) else { return }
        for (index, frame) in [plan.label, plan.value].enumerated() {
            subviews[index].place(at: CGPoint(x: bounds.minX + frame.minX, y: bounds.minY + frame.minY),
                                  anchor: .topLeading, proposal: ProposedViewSize(frame.size))
        }
    }

    private func plan(available: CGFloat, subviews: Subviews) -> ExactScoreFinishLaneRowPlan10868? {
        guard subviews.count == 2 else { return nil }
        let labelIdeal = subviews[0].sizeThatFits(.unspecified)
        let valueIdeal = subviews[1].sizeThatFits(.unspecified)
        let wrapped = ProposedViewSize(width: available, height: nil)
        let labelStacked = available.isFinite ? subviews[0].sizeThatFits(wrapped).height : labelIdeal.height
        let valueStacked = available.isFinite ? subviews[1].sizeThatFits(wrapped).height : valueIdeal.height
        return ExactScoreFinishLaneGeometry10868.rowPlan(available: available, labelIdeal: labelIdeal, labelStackedHeight: labelStacked,
                                                         valueIdeal: valueIdeal, valueStackedHeight: valueStacked,
                                                         spacing: spacing, accessibilitySize: accessibilitySize)
    }
}

/// One bar's drawing. A filled bar is the chance; a hatched fill is the same
/// chance on a finish the owner says can no longer happen; a quoted zero is a
/// leading mark; no placeable reading is a dashed empty track.
enum ExactScoreFinishLaneArt10868 {
    static func hatch(in rect: CGRect, step: CGFloat = 5) -> Path {
        var path = Path()
        guard rect.width > 0, rect.height > 0, step > 0 else { return path }
        var x = rect.minX - rect.height
        while x < rect.maxX {
            path.move(to: CGPoint(x: x, y: rect.maxY))
            path.addLine(to: CGPoint(x: x + rect.height, y: rect.minY))
            x += step
        }
        return path
    }

    static func draw(_ bar: ExactScoreFinishLaneBar10868, hatched: Bool, tone: Color, in rect: CGRect,
                     context: inout GraphicsContext) {
        guard rect.width > 0, rect.height > 0 else { return }
        let radius = rect.height / 2
        let track = Path(roundedRect: rect, cornerRadius: radius)
        guard let width = ExactScoreFinishLaneGeometry10868.fillWidth(bar, track: rect.width) else {
            context.stroke(track, with: .color(DS.textMuted), style: StrokeStyle(lineWidth: 1, dash: [2, 2]))
            return
        }
        context.fill(track, with: .color(DS.trackBg))
        guard width > 0 else {
            context.fill(Path(CGRect(x: rect.minX, y: rect.minY, width: min(2, rect.width), height: rect.height)), with: .color(tone))
            return
        }
        let fill = CGRect(x: rect.minX, y: rect.minY, width: width, height: rect.height)
        let shape = Path(roundedRect: fill, cornerRadius: min(radius, width / 2))
        if hatched {
            context.drawLayer { layer in
                layer.clip(to: shape)
                layer.stroke(hatch(in: fill), with: .color(tone), lineWidth: 1.5)
            }
            context.stroke(shape, with: .color(tone), lineWidth: 1)
        } else {
            context.fill(shape, with: .color(tone))
        }
    }
}

/// Stable ids so the owner can return focus to the exact originating control.
nonisolated enum ExactScoreFinishLaneAccessibilityID10868 {
    static func lane(_ originalID: String) -> String { "exactScoreFinishLane10868.lane.\(originalID)" }
    static func slot(_ index: Int) -> String { "exactScoreFinishLane10868.slot.\(index)" }
    static func choice(_ id: String) -> String { "exactScoreFinishLane10868.choice.\(id)" }
}

struct ExactScoreFinishLanePresentation10868: View {
    let input: ExactScoreFinishLaneInput10868
    /// (scope id, original id), exactly as supplied.
    var onDetails: ((String, String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var figureSize: CGFloat = 22
    @ScaledMetric(relativeTo: .caption) private var barHeight: CGFloat = 6
    @ScaledMetric(relativeTo: .caption) private var markSize: CGFloat = 14

    private var canOpenDetails: Bool { onDetails != nil }

    var body: some View {
        if input.isShown {
            VStack(alignment: .leading, spacing: 12) {
                header
                if let scope = input.scope {
                    actual
                    VStack(alignment: .leading, spacing: 10) {
                        ForEach(Array(input.lanes.enumerated()), id: \.offset) { index, lane in
                            self.lane(lane, index: index)
                        }
                    }
                    if let note = input.displayedContextNote {
                        Text(note)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    choices(scope)
                } else {
                    Text(input.map.words.scopeUnavailable)
                        .font(.headline)
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .buttonStyle(.plain)
        }
    }

    // MARK: Header

    private var header: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let eyebrow = input.displayedEyebrow {
                Text(eyebrow).font(.caption).foregroundStyle(DS.textSecondary)
            }
            Text(input.displayedTitle)
                .font(.title2.bold())
                .foregroundStyle(DS.textPrimary)
                .accessibilityAddTraits(.isHeader)
            if let intro = input.displayedIntro {
                Text(intro).font(.subheadline).foregroundStyle(DS.textSecondary)
            }
            Text(input.words.scaleKey).font(.caption).foregroundStyle(DS.textSecondary)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private var actual: some View {
        if let actual = input.visibleActual {
            VStack(alignment: .leading, spacing: 2) {
                Text(actual.title).font(.caption).foregroundStyle(DS.textSecondary)
                Text(actual.text).font(.subheadline.weight(.semibold)).foregroundStyle(DS.textPrimary)
            }
            .fixedSize(horizontal: false, vertical: true)
            .accessibilityElement(children: .combine)
        }
    }

    // MARK: Lanes

    private func color(_ lane: ExactScoreFinishLane10868) -> Color {
        if input.dimsForAvailability(lane) { return DS.textSecondary }
        switch lane.tone {
        case .home: return DS.blue
        case .away: return DS.emeraldDark
        }
    }

    @ViewBuilder
    private func lane(_ lane: ExactScoreFinishLane10868, index: Int) -> some View {
        switch input.state(lane) {
        case .placed(let original)?:
            placedLane(lane, original: original)
        case .notListed(let text)?, .unavailable(let text)?:
            VStack(alignment: .leading, spacing: 6) {
                Text(lane.fallbackLabel)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                Text(text)
                    .font(.footnote)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                rows(input.channels(lane), tone: color(lane))
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 4)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(input.accessibilityLabel(lane))
            .accessibilityValue(input.accessibilityValue(lane))
            .accessibilityIdentifier(ExactScoreFinishLaneAccessibilityID10868.slot(index))
        case nil:
            EmptyView()
        }
    }

    private func placedLane(_ lane: ExactScoreFinishLane10868, original: ExactScoreMapOriginal10868) -> some View {
        let action = input.detailsAction(lane, canOpen: canOpenDetails)
        let selected = input.isSelected(lane)
        return control(action) {
            VStack(alignment: .leading, spacing: 6) {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(original.label)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    if action != nil {
                        Image(systemName: "chevron.right")
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .accessibilityHidden(true)
                    }
                }
                rows(input.channels(lane), tone: color(lane))
            }
            .padding(.vertical, 6)
            .padding(.horizontal, 4)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(selected ? DS.textPrimary : Color.clear, lineWidth: 2)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.accessibilityLabel(lane))
        .accessibilityValue(input.accessibilityValue(lane))
        .accessibilityHint(action == nil ? "" : input.map.words.detailsHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(ExactScoreFinishLaneAccessibilityID10868.lane(original.id))
    }

    /// Each row: its title, its value beside or below it, and a chance's bar
    /// across the full lane width on the fixed scale.
    private func rows(_ channels: [ExactScoreFinishLaneChannel10868], tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            ForEach(Array(channels.enumerated()), id: \.offset) { _, channel in
                VStack(alignment: .leading, spacing: 3) {
                    ExactScoreFinishLaneRowLayout10868(accessibilitySize: typeSize.isAccessibilitySize) {
                        Text(channel.title)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                        value(channel, tone: tone)
                    }
                    if let bar = channel.bar {
                        self.bar(bar, hatched: channel.hatched, tone: tone)
                    }
                }
            }
        }
    }

    /// Pre-match and current figures share one size. Words and results wrap.
    @ViewBuilder
    private func value(_ channel: ExactScoreFinishLaneChannel10868, tone: Color) -> some View {
        switch channel.value {
        case .figure(let observation):
            Text(observation.text)
                .font(.system(size: figureSize, weight: .bold))
                .monospacedDigit()
                .foregroundStyle(tone)
                .fixedSize(horizontal: false, vertical: true)
        case .words(let text):
            Text(text)
                .font(.footnote.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        case .result(let result):
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                switch result.mark {
                case .won?:
                    Image(systemName: "checkmark.circle").accessibilityHidden(true)
                case .lost?:
                    Image(systemName: "xmark.circle").accessibilityHidden(true)
                case nil:
                    EmptyView()
                }
                Text(result.text).fixedSize(horizontal: false, vertical: true)
            }
            .font(.footnote.weight(result.isWon ? .bold : .regular))
            .foregroundStyle(result.isWon ? DS.textPrimary : DS.textSecondary)
        case .availability(let availability):
            // The owner's words with their own mark: hatched when ruled out, solid
            // otherwise — shape and words, never colour alone.
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Canvas { context, size in
                    ExactScoreFinishLaneArt10868.draw(.fill(1), hatched: channel.hatched, tone: tone,
                                                      in: CGRect(origin: .zero, size: size), context: &context)
                }
                .frame(width: markSize, height: markSize / 2)
                .accessibilityHidden(true)
                Text(availability.text)
                    .font(.footnote.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func bar(_ bar: ExactScoreFinishLaneBar10868, hatched: Bool, tone: Color) -> some View {
        Canvas { context, size in
            ExactScoreFinishLaneArt10868.draw(bar, hatched: hatched, tone: tone, in: CGRect(origin: .zero, size: size), context: &context)
        }
        .frame(maxWidth: .infinity)
        .frame(height: barHeight)
        .accessibilityHidden(true)
    }

    // MARK: Named originals

    @ViewBuilder
    private func choices(_ scope: ExactScoreMapScope10868) -> some View {
        let list = input.unplaced
        if !list.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                Text(input.map.words.otherChoicesTitle)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                ForEach(Array(list.enumerated()), id: \.offset) { _, original in
                    choice(original, in: scope)
                }
            }
        }
    }

    private func choice(_ original: ExactScoreMapOriginal10868, in scope: ExactScoreMapScope10868) -> some View {
        let action = input.detailsAction(original, canOpen: canOpenDetails)
        let selected = input.isSelected(original)
        return control(action) {
            VStack(alignment: .leading, spacing: 6) {
                Text(original.label)
                    .font(.subheadline.weight(selected ? .semibold : .regular))
                    .underline(selected)
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
                if input.isExact(original) {
                    rows(input.channels(original, availability: nil), tone: DS.textPrimary)
                } else {
                    Text(input.words.laneUnavailable)
                        .font(.footnote)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(DS.surface, in: RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(selected ? DS.textPrimary : Color.clear, lineWidth: 2)
            )
            .contentShape(Rectangle())
        }
        .accessibilityLabel(input.map.accessibilityLabel(original, in: scope))
        .accessibilityValue(input.accessibilityValue(original))
        .accessibilityHint(action == nil ? "" : input.map.words.detailsHint)
        .accessibilityAddTraits(selected ? .isSelected : [])
        .accessibilityIdentifier(ExactScoreFinishLaneAccessibilityID10868.choice(original.id))
    }

    // MARK: Controls

    private func perform(_ action: ExactScoreMapAction10868?) {
        ExactScoreFinishRouting10868.route(action, onSelectOriginal: nil, onDetails: onDetails, onRecoverSelection: nil)
    }

    /// A button only when the owner supplied the callback and the identity is
    /// exact; otherwise the same content as one plain accessibility element.
    @ViewBuilder
    private func control<Content: View>(_ action: ExactScoreMapAction10868?, @ViewBuilder content: () -> Content) -> some View {
        if let action {
            Button {
                perform(action)
            } label: {
                content()
            }
        } else {
            content().accessibilityElement(children: .ignore)
        }
    }
}
