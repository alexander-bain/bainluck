import Foundation

/// #10238 §11 — what a reader picked in a Game or Series question matrix, and
/// whether the current payload still serves it.
///
/// A selection is the server's identity and nothing else: the scope, the
/// `question_key`, the `option_key`, and (when one source was chosen) that
/// source's `outcome_id`. Never a position, label, price or clock. When the
/// question, the option or the chosen source leaves the payload while detail
/// is open, the selection reads `unavailable` — it never jumps to a sibling,
/// another source, or the same market in the other scope (rider R6).
nonisolated struct QuestionMatrixSelection: Hashable, Sendable {
    let scope: QuestionMatrixScope
    let questionKey: String
    let optionKey: String
    var outcomeId: Int? = nil

    enum Resolution: Equatable, Sendable {
        case available(question: QuestionMatrixQuestion, option: QuestionMatrixOption,
                       evidence: QuestionMatrixSourceEvidence?)
        case unavailable(Reason)
    }

    enum Reason: String, Equatable, Sendable {
        /// No matrix of this scope in the payload (absent, null or unreadable).
        case noMatrix
        /// The matrix belongs to the other scope.
        case wrongScope
        case questionGone
        /// The option is gone, or now listed only as a missing leg.
        case optionGone
        /// The chosen source no longer contributes to this option.
        case sourceGone
    }

    /// Resolves against the matrix of this selection's own scope — the caller
    /// passes `gameQuestionMatrix` for `.game` and `seriesQuestionMatrix` for
    /// `.series`; a mismatched payload is refused rather than read.
    func resolve(in matrix: EventQuestionMatrix?) -> Resolution {
        guard let matrix else { return .unavailable(.noMatrix) }
        if let declared = matrix.displayScope, declared != scope.rawValue { return .unavailable(.wrongScope) }
        guard let question = matrix.question(questionKey) else { return .unavailable(.questionGone) }
        if let declared = question.displayScope, declared != scope.rawValue { return .unavailable(.wrongScope) }
        guard let option = question.option(optionKey) else { return .unavailable(.optionGone) }
        guard let outcomeId else { return .available(question: question, option: option, evidence: nil) }
        guard let evidence = (option.sourceEvidence ?? []).first(where: { $0.outcomeId == outcomeId }) else {
            return .unavailable(.sourceGone)
        }
        return .available(question: question, option: option, evidence: evidence)
    }
}
