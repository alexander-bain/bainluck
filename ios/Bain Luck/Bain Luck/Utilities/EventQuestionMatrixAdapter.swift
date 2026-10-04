import Foundation

/// #10238: presentation of already typed Game / Series questions. No names
/// are parsed, no side/price/baseline is synthesized, and game phase is not an
/// input: an open Series must stay open after its associated game finishes.
/// Native owns the subsequent shared-shell mount and runtime acceptance.
nonisolated enum EventQuestionMatrixAdapter {
    struct RowID: Hashable, Sendable {
        let scope: QuestionMatrixScope
        let questionKey: String
    }

    enum Value: Equatable, Sendable {
        case quoted(Double)
        case won
        case lost
        case unavailable
    }

    struct Option: Equatable, Identifiable, Sendable {
        var id: QuestionMatrixSelection { selection }
        let selection: QuestionMatrixSelection
        let label: String
        let side: String?
        let value: Value
        let observedAt: String?
        let basis: String?
        let result: QuestionMatrixResult?
    }

    struct Row: Equatable, Identifiable, Sendable {
        let id: RowID
        let kind: QuestionMatrixKind
        let label: String
        let quantity: QuestionMatrixQuantity?
        let period: QuestionMatrixPeriod?
        let subject: QuestionMatrixSubject?
        let predicate: QuestionMatrixPredicate?
        let lifecycle: QuestionMatrixLifecycle?
        let options: [Option]
        let missingOptions: [QuestionMatrixMissingOption]
        let offersMoreOptions: Bool
        let complete: Bool?
        let optionCounts: QuestionMatrixOptionCounts?
        let sourceTotals: [QuestionMatrixSourceTotal]
    }

    /// Comparison is deliberately absent from Row/Option. R5 permits the
    /// served delta beside comparison.latest only, not the published value
    /// (which may have a different display basis).
    struct Comparison: Equatable, Sendable {
        let baseline: Double
        let baselineObservedAt: String
        let latest: Double
        let latestObservedAt: String
        let points: Double
        var caption: String { QuestionMatrixComparison.caption }
    }

    struct Source: Equatable, Sendable {
        /// Missing outcome identity earns no selectable source target.
        let selection: QuestionMatrixSelection?
        let source: String?
        let marketID: Int?
        let outcomeID: Int?
        let side: String?
        let probability: Double?
        let observedAt: String?
    }

    struct Detail: Equatable, Sendable {
        let row: Row
        let option: Option
        let sources: [Source]
        let selectedSource: Source?
        let comparison: Comparison?
    }

    enum DetailResolution: Equatable, Sendable {
        case available(Detail)
        case unavailable(QuestionMatrixSelection.Reason)
    }

    /// Source order and named options stay intact. A caller supplies the
    /// scope of the endpoint it read; an explicitly different scope refuses.
    /// There is no zip, binary complement, sorting by probability or cap.
    static func rows(in matrix: EventQuestionMatrix?, scope: QuestionMatrixScope) -> [Row] {
        guard let matrix, matrix.displayScope == nil || matrix.displayScope == scope.rawValue else { return [] }
        return matrix.questions.compactMap { question in
            guard question.displayScope == nil || question.displayScope == scope.rawValue else { return nil }
            // Options a reader cannot tell apart are not a question we can
            // show. Production served every Polymarket team total as
            // "Over" / "Over" with one shared result (event 15323083).
            guard !hasIndistinguishableOptions(question) else { return nil }
            return row(question, scope: scope)
        }
    }

    static func hasIndistinguishableOptions(_ question: QuestionMatrixQuestion) -> Bool {
        let labels = question.options.map { $0.label.trimmingCharacters(in: .whitespaces).lowercased() }
        return Set(labels).count != labels.count
    }

    /// Resolve against the latest payload using the existing selection
    /// contract. A missing selected source never silently selects a sibling.
    static func detail(for selection: QuestionMatrixSelection, in matrix: EventQuestionMatrix?) -> DetailResolution {
        switch selection.resolve(in: matrix) {
        case .unavailable(let reason):
            return .unavailable(reason)
        case .available(let question, let option, let selectedEvidence):
            let sources = (option.sourceEvidence ?? []).map {
                source($0, option: option, question: question, scope: selection.scope)
            }
            let selectedSource = selectedEvidence.map {
                source($0, option: option, question: question, scope: selection.scope)
            }
            return .available(Detail(
                row: row(question, scope: selection.scope),
                option: presentation(option, question: question, scope: selection.scope),
                sources: sources,
                selectedSource: selectedSource,
                // A chosen raw contributor is not comparison.latest. Do not
                // carry a blended/published comparison into its source detail.
                comparison: selection.outcomeId == nil ? comparison(option) : nil
            ))
        }
    }

    private static func row(_ question: QuestionMatrixQuestion, scope: QuestionMatrixScope) -> Row {
        Row(
            id: RowID(scope: scope, questionKey: question.questionKey),
            kind: question.columnKind,
            label: question.label,
            quantity: question.quantity,
            period: question.period,
            subject: question.subject,
            predicate: question.predicate,
            lifecycle: question.lifecycle,
            options: question.options.map { presentation($0, question: question, scope: scope) },
            missingOptions: question.missingOptions ?? [],
            offersMoreOptions: question.offersMoreOptions,
            complete: question.complete,
            optionCounts: question.optionCounts,
            sourceTotals: question.sourceTotals ?? []
        )
    }

    private static func presentation(
        _ option: QuestionMatrixOption, question: QuestionMatrixQuestion, scope: QuestionMatrixScope
    ) -> Option {
        let value: Value
        if let quote = option.published.quotedValue {
            value = .quoted(quote)
        } else if option.published.valueState == "result", let winner = option.result?.isWinner {
            value = winner ? .won : .lost
        } else {
            value = .unavailable
        }
        return Option(
            selection: QuestionMatrixSelection(scope: scope, questionKey: question.questionKey, optionKey: option.optionKey),
            label: option.label,
            side: option.side,
            value: value,
            observedAt: option.published.observedAt,
            basis: option.published.basis,
            result: option.result
        )
    }

    private static func source(
        _ evidence: QuestionMatrixSourceEvidence, option: QuestionMatrixOption,
        question: QuestionMatrixQuestion, scope: QuestionMatrixScope
    ) -> Source {
        // Unblended equivalents may disclose their individual raw quotes,
        // without inventing one main answer. Refused/unpriced/result values
        // do not regain a current quote merely by opening source detail.
        let quotesAllowed = ["quoted", "unblended_equivalents"].contains(option.published.valueState)
        return Source(
            selection: evidence.outcomeId.map {
                QuestionMatrixSelection(scope: scope, questionKey: question.questionKey, optionKey: option.optionKey, outcomeId: $0)
            },
            source: evidence.source,
            marketID: evidence.marketId,
            outcomeID: evidence.outcomeId,
            side: evidence.legSide,
            probability: quotesAllowed ? probability(evidence.rawProbability) : nil,
            observedAt: evidence.observedAt
        )
    }

    private static func comparison(_ option: QuestionMatrixOption) -> Comparison? {
        guard option.published.quotedValue != nil,
              let c = option.comparison, c.state == "comparable",
              let baseline = c.baseline, baseline.basis == "pregame_pin",
              let before = probability(baseline.probability),
              let beforeTime = baseline.observedAt, !beforeTime.isEmpty,
              let latest = c.latest, let after = probability(latest.probability),
              let afterTime = latest.observedAt, !afterTime.isEmpty,
              let points = c.deltaPoints, points.isFinite else { return nil }
        return Comparison(
            baseline: before, baselineObservedAt: beforeTime,
            latest: after, latestObservedAt: afterTime, points: points
        )
    }

    private static func probability(_ value: Double?) -> Double? {
        guard let value, value.isFinite, (0...1).contains(value) else { return nil }
        return value
    }
}
