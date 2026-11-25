import CoreGraphics
import Foundation

/// #10830 — Visual condensation of contiguous single-option `.countThreshold`
/// ladders (`Game odds → Totals`) into a probability distribution curve + grid
/// of tappable tiles, preserving server order, exact labels, prices, detail
/// sheets, searchability, and focus return.
enum EventQuestionMatrixLadderGroup10830 {
    static let minimumRunLength = 3
    static let defaultVisibleTileLimit = 12
    static let twoColumnBreakpointWidth: CGFloat = 340

    struct LadderSignature: Equatable, Hashable, Sendable {
        let periodKey: String?
        let subjectSide: String?
        let subjectLabel: String?
        let quantityKey: String?
        let predicateRelation: String?
    }

    struct Rung: Identifiable, Equatable, Sendable {
        var id: EventQuestionMatrixAdapter.RowID { row.id }
        let row: EventQuestionMatrixAdapter.Row
        let option: EventQuestionMatrixAdapter.Option
        let bound: Double

        /// Server-quoted probability in `[0, 1]`, or `nil` for result/unavailable states.
        var quotedProbability: Double? {
            if case .quoted(let value) = option.value, value.isFinite, (0...1).contains(value) {
                return value
            }
            return nil
        }
    }

    struct ChartPoint: Identifiable, Equatable, Sendable {
        var id: EventQuestionMatrixAdapter.RowID
        let bound: Double
        let probability: Double
    }

    struct LadderGroup: Identifiable, Equatable, Sendable {
        let id: String
        let signature: LadderSignature
        let rungs: [Rung]

        init(signature: LadderSignature, rungs: [Rung]) {
            self.signature = signature
            self.rungs = rungs
            let first = rungs.first?.row.id.questionKey ?? ""
            let last = rungs.last?.row.id.questionKey ?? ""
            self.id = "\(signature.quantityKey ?? "count"):\(first):\(last):\(rungs.count)"
        }

        var representativeRow: EventQuestionMatrixAdapter.Row {
            rungs[0].row
        }

        var periodLabel: String {
            representativeRow.period?.label ?? ""
        }

        var family: String {
            EventQuestionMatrixSection10238.family(representativeRow)
        }

        var xAxisUnitLabel: String? {
            let unit = representativeRow.quantity?.plural?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            guard !unit.isEmpty else { return nil }
            if family == "Totals" || representativeRow.subject?.side == "game" {
                return "Total \(unit)"
            }
            return unit.prefix(1).uppercased() + unit.dropFirst()
        }

        var searchText: String {
            rungs.map { EventQuestionMatrixSection10238.searchText($0.row) }.joined(separator: " ")
        }

        /// Quoted `(bound, probability)` points sorted strictly ascending by `bound`.
        /// Unpriced (`unavailable`) and decided (`won`/`lost`) rungs are omitted from the curve.
        var chartPoints: [ChartPoint] {
            rungs
                .compactMap { rung in
                    rung.quotedProbability.map { ChartPoint(id: rung.id, bound: rung.bound, probability: $0) }
                }
                .sorted { $0.bound < $1.bound }
        }

        func matchingRungs(query: String) -> [Rung] {
            guard !MarketBrowserLogic.terms(query).isEmpty else { return rungs }
            let groups = rungs.map { _ in family }
            let texts = rungs.map { EventQuestionMatrixSection10238.searchText($0.row) }
            let indices = MarketBrowserLogic.matchingIndices(
                groupNames: groups,
                searchTexts: texts,
                query: query,
                selected: nil
            )
            return indices.map { rungs[$0] }
        }

        func visibleRungs(query: String, expanded: Bool) -> [Rung] {
            let matches = matchingRungs(query: query)
            guard MarketBrowserLogic.terms(query).isEmpty else {
                return matches
            }
            if expanded || matches.count <= EventQuestionMatrixLadderGroup10830.defaultVisibleTileLimit {
                return matches
            }
            return Array(matches.prefix(EventQuestionMatrixLadderGroup10830.defaultVisibleTileLimit))
        }
    }

    enum Segment: Identifiable, Equatable, Sendable {
        case row(EventQuestionMatrixAdapter.Row)
        case ladder(LadderGroup)

        var id: String {
            switch self {
            case .row(let row):
                return "row:\(row.id.scope.rawValue):\(row.id.questionKey)"
            case .ladder(let group):
                return "ladder:\(group.id)"
            }
        }

        var family: String {
            switch self {
            case .row(let row):
                return EventQuestionMatrixSection10238.family(row)
            case .ladder(let group):
                return group.family
            }
        }

        var periodLabel: String {
            switch self {
            case .row(let row):
                return row.period?.label ?? ""
            case .ladder(let group):
                return group.periodLabel
            }
        }

        var searchText: String {
            switch self {
            case .row(let row):
                return EventQuestionMatrixSection10238.searchText(row)
            case .ladder(let group):
                return group.searchText
            }
        }

        func visibleRowIDs(expandedLadderIDs: Set<String>, query: String) -> [EventQuestionMatrixAdapter.RowID] {
            switch self {
            case .row(let row):
                return [row.id]
            case .ladder(let group):
                return group.visibleRungs(
                    query: query,
                    expanded: expandedLadderIDs.contains(id) || expandedLadderIDs.contains(group.id)
                ).map(\.id)
            }
        }
    }

    static func columnCount(forWidth width: CGFloat) -> Int {
        width < twoColumnBreakpointWidth ? 2 : 3
    }

    static func segment(_ rows: [EventQuestionMatrixAdapter.Row]) -> [Segment] {
        var result: [Segment] = []
        var runSignature: LadderSignature?
        var runFamily: String?
        var runRungs: [Rung] = []

        func flushRun() {
            guard !runRungs.isEmpty else { return }
            if let runSignature, runRungs.count >= minimumRunLength {
                result.append(.ladder(LadderGroup(signature: runSignature, rungs: runRungs)))
            } else {
                for rung in runRungs {
                    result.append(.row(rung.row))
                }
            }
            runSignature = nil
            runFamily = nil
            runRungs = []
        }

        for row in rows {
            if let rung = eligibleRung(row) {
                let sig = signature(for: row)
                let fam = EventQuestionMatrixSection10238.family(row)
                if runSignature == sig, runFamily == fam {
                    runRungs.append(rung)
                } else {
                    flushRun()
                    runSignature = sig
                    runFamily = fam
                    runRungs = [rung]
                }
            } else {
                flushRun()
                result.append(.row(row))
            }
        }
        flushRun()
        return result
    }

    static func visibleRowIDs(
        forVisibleSegments visibleSegmentIDs: Set<String>,
        segments: [Segment],
        expandedLadderIDs: Set<String>,
        query: String
    ) -> Set<EventQuestionMatrixAdapter.RowID> {
        var ids: Set<EventQuestionMatrixAdapter.RowID> = []
        for segment in segments where visibleSegmentIDs.contains(segment.id) {
            ids.formUnion(segment.visibleRowIDs(expandedLadderIDs: expandedLadderIDs, query: query))
        }
        return ids
    }

    private static func eligibleRung(_ row: EventQuestionMatrixAdapter.Row) -> Rung? {
        guard row.kind == .countThreshold,
              row.options.count == 1,
              let onlyOption = row.options.first,
              !row.offersMoreOptions,
              let bound = row.predicate?.bound,
              bound.isFinite else {
            return nil
        }
        return Rung(row: row, option: onlyOption, bound: bound)
    }

    private static func signature(for row: EventQuestionMatrixAdapter.Row) -> LadderSignature {
        LadderSignature(
            periodKey: row.period?.key,
            subjectSide: row.subject?.side,
            subjectLabel: row.subject?.label,
            quantityKey: row.quantity?.key,
            predicateRelation: row.predicate?.relation
        )
    }
}
