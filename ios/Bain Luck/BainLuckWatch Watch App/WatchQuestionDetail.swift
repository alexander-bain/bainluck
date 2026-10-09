import Foundation

/// The tapped story title remains readable while its exact detail is unavailable.
/// It carries no cached chance or grade into the detail screen.
nonisolated struct WatchQuestionDetailDestination: Identifiable, Sendable, Equatable {
    let id: Int
    let question: String

    func heading(detail: WatchQuestionDetail?) -> (text: String, retained: Bool) {
        if let detail, detail.id == id { return (detail.question, false) }
        let retained = question.trimmingCharacters(in: .whitespacesAndNewlines)
        return (retained.isEmpty ? "Question" : retained, true)
    }
}

/// Exact futures detail, never the ceremony's shortened category child.
/// OutcomeVerdict is the existing shared native policy; Native must make that
/// source available to the Watch target before composing this proposal.
nonisolated struct WatchQuestionDetail: Sendable, Equatable {
    let id: Int
    let question: String
    let outcomes: [Outcome]
    let hasOmittedOutcomes: Bool

    nonisolated struct Outcome: Identifiable, Sendable, Equatable {
        let id: Int
        let name: String
        let probability: Double?
        let result: String?
        let resultUnavailable: Bool

        var reading: String {
            if let result { return "Question result: \(result)" }
            if resultUnavailable { return "Result unconfirmed" }
            guard let probability else { return "Chance unavailable" }
            if probability > 0 && probability < 0.01 { return "Chance <1%" }
            if probability > 0.99 && probability < 1 { return "Chance >99%" }
            return "Chance \(Int((probability * 100).rounded()))%"
        }
        // Detail exposes poll/movement timestamps, not an observation of this
        // exact reported chance or a result. Do not relabel those clocks.
        var clock: String { result != nil || resultUnavailable ? "Result time unavailable" : "Chance observation time unavailable" }
    }
}

nonisolated enum WatchQuestionDetailDecoder {
    enum Invalid: Error { case identity }
    private struct Slot: Decodable {
        private struct Identity: Decodable { let id: Int }
        let id: Int?
        let value: Row?
        init(from decoder: Decoder) throws {
            // Retain identity even when another field makes this row unreadable.
            id = (try? Identity(from: decoder))?.id
            value = try? Row(from: decoder)
        }
    }
    private struct Row: Decodable {
        let id: Int
        let name: String
        let probability: Double?
        let isWinner: Bool?
        let resolutionSource: String?
    }
    private struct Response: Decodable {
        let id: Int
        let name: String
        let status: String?
        let outcomes: [Slot]
    }
    static func decode(_ data: Data, expectedID: Int) throws -> WatchQuestionDetail {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let response = try decoder.decode(Response.self, from: data)
        let question = response.name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard expectedID > 0, response.id == expectedID, !question.isEmpty else { throw Invalid.identity }
        let status = response.status?.lowercased()
        let terminal = ["resolved", "closed", "settled", "finalized", "final"].contains(status ?? "")
        let identityCounts = response.outcomes.reduce(into: [Int: Int]()) { counts, slot in
            if let id = slot.id, id > 0 { counts[id, default: 0] += 1 }
        }
        var omitted = false
        let outcomes = response.outcomes.compactMap { slot -> WatchQuestionDetail.Outcome? in
            guard let row = slot.value, row.id > 0,
                  !row.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  identityCounts[row.id] == 1 else { omitted = true; return nil }
            let source = row.resolutionSource?.trimmingCharacters(in: .whitespacesAndNewlines)
            let result = OutcomeVerdict.verdict(isWinner: row.isWinner,
                resolutionSource: source?.isEmpty == false ? source : nil,
                marketResolved: status == "resolved")?.label
            let probability = row.probability.flatMap { $0.isFinite && (0...1).contains($0) ? $0 : nil }
            return WatchQuestionDetail.Outcome(id: row.id, name: row.name,
                probability: result == nil && !terminal ? probability : nil,
                result: result, resultUnavailable: terminal && result == nil)
        }
        return WatchQuestionDetail(id: response.id, question: question,
                                   outcomes: outcomes, hasOmittedOutcomes: omitted)
    }
}
