import Foundation

// Synthetic wire-shape mutations, not captured production awards results.
// Calls the actual proposed decoder and existing native OutcomeVerdict policy.
@main struct QuestionChecks {
    @MainActor static func main() async throws {
        func row(_ id: Int, _ probability: Any = NSNull(), winner: Any = NSNull(), source: Any = NSNull()) -> [String: Any] {
            ["id": id, "name": "Exact supplied nominee", "probability": probability,
             "is_winner": winner, "resolution_source": source,
             "last_updated": "2026-10-09T18:00:00Z", "price_changed_at": "2026-10-09T17:00:00Z"]
        }
        func decode(_ rows: [Any], status: String = "open", id: Int = 42,
                    question: String = "Will this film receive a Best Picture nomination?") throws -> WatchQuestionDetail {
            let data = try JSONSerialization.data(withJSONObject: ["id": id, "name": question,
                "status": status, "outcomes": rows, "resolution_date": "2027-03-01T00:00:00Z"])
            return try WatchQuestionDetailDecoder.decode(data, expectedID: 42)
        }
        let missing = try decode([row(1), row(2, 0), row(3, 1), row(4, 0.999), row(5, 0.001)])
        precondition(missing.question.contains("nomination"))
        let tapped = WatchQuestionDetailDestination(id: 42, question: "  Original full nomination question?  ")
        let pendingHeading = tapped.heading(detail: nil)
        precondition(pendingHeading.text == "Original full nomination question?" && pendingHeading.retained)
        let updatedHeading = tapped.heading(detail: missing)
        precondition(updatedHeading.text == missing.question && !updatedHeading.retained)
        let wrongIdentity = WatchQuestionDetailDestination(id: 43, question: "A different award question?")
        let refusedHeading = wrongIdentity.heading(detail: missing)
        precondition(refusedHeading.text == "A different award question?" && refusedHeading.retained)
        let blankHeading = WatchQuestionDetailDestination(id: 42, question: " ").heading(detail: nil)
        precondition(blankHeading.text == "Question" && blankHeading.retained)
        precondition(missing.outcomes.map(\.reading) == ["Chance unavailable", "Chance 0%", "Chance 100%", "Chance >99%", "Chance <1%"])
        precondition(missing.outcomes.allSatisfy { $0.result == nil && $0.clock == "Chance observation time unavailable" })
        let invalid = try decode([row(1, -0.1), "broken", row(2, 1.1), row(2, 0.5)])
        precondition(invalid.outcomes.map(\.id) == [1] && invalid.hasOmittedOutcomes)
        precondition(invalid.outcomes.allSatisfy { $0.probability == nil })
        // Ambiguous identities never select the first chance or grade by wire order.
        let duplicates = [row(8, 0.9), row(7, 0.2), row(8, 0.1), row(3, 0.6)]
        let refused = try decode(duplicates)
        precondition(refused.outcomes.map(\.id) == [7, 3] && refused.hasOmittedOutcomes)
        let reversedDuplicates = try decode([duplicates[2], duplicates[1], duplicates[0], duplicates[3]])
        precondition(reversedDuplicates == refused)
        let contradictoryGrade = try decode([row(8, winner: true, source: "api_settlement"),
            row(8, winner: false, source: "api_settlement"), row(7, winner: true, source: "api_settlement")], status: "resolved")
        precondition(contradictoryGrade.outcomes.map(\.id) == [7])
        precondition(contradictoryGrade.outcomes[0].result == "Won" && contradictoryGrade.hasOmittedOutcomes)
        var malformedDuplicate = row(8, 0.1)
        malformedDuplicate["name"] = 123
        let malformedCollision = try decode([row(8, 0.9), malformedDuplicate, row(3, 0.6)])
        precondition(malformedCollision.outcomes.map(\.id) == [3] && malformedCollision.hasOmittedOutcomes)
        let allAmbiguous = try decode([row(8, 0.9), row(8, 0.9)])
        precondition(allAmbiguous.outcomes.isEmpty && allAmbiguous.hasOmittedOutcomes)
        let defaultFalse = try decode([row(1, 0, winner: false)], status: "resolved")
        precondition(defaultFalse.outcomes[0].result == nil && defaultFalse.outcomes[0].resultUnavailable)
        let graded = try decode([row(1, 0.5, winner: true, source: "api_settlement"),
                                 row(2, 0.5, winner: false, source: "api_settlement")], status: "resolved")
        precondition(graded.outcomes.map(\.result) == ["Won", "Lost"])
        precondition(graded.outcomes.allSatisfy { $0.probability == nil && $0.clock == "Result time unavailable" })
        let early = try decode([row(1, 0.5, winner: true, source: "api_settlement"), row(2, 0.5, winner: false, source: "api_settlement")])
        precondition(early.outcomes[0].result == "Won" && early.outcomes[1].result == nil)
        let retracted = try decode([row(1, 1, winner: true, source: "ungradeable_result")], status: "resolved")
        precondition(retracted.outcomes[0].result == nil)
        let closed = try decode([row(1, 1)], status: "closed")
        precondition(closed.outcomes[0].probability == nil && closed.outcomes[0].resultUnavailable)
        do { _ = try decode([], id: 43); preconditionFailure("wrong market accepted") } catch {}
        do { _ = try decode([], question: " "); preconditionFailure("empty question accepted") } catch {}
        let empty = try decode([])
        precondition(empty.outcomes.isEmpty)
        try await StoreChecks.run()
        print("Question decoder/presentation and loader scenarios PASS")
    }
}
