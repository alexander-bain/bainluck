import Foundation

/// The one named probability supplied by Discover, with its producer clock.
nonisolated struct WatchDiscoveryReading: Codable, Identifiable, Sendable, Equatable {
    let id: Int
    let question: String
    let outcomeName: String?
    let probability: Double?
    let observedAt: Date?
    let isSettled: Bool
    let winner: String?

    var resultLabel: String? {
        guard isSettled else { return nil }
        return winner.map { "Result: \($0)" } ?? "Settled · Result unavailable"
    }

    func observationLabel(now: Date = Date()) -> String {
        guard let observedAt, observedAt <= now else { return "Observation age unknown" }
        let seconds = Int(now.timeIntervalSince(observedAt))
        if seconds < 60 { return "Observed \(seconds)s ago" }
        if seconds < 3600 { return "Observed \(seconds / 60)m ago" }
        if seconds < 86400 { return "Observed \(seconds / 3600)h ago" }
        return "Observed \(seconds / 86400)d ago"
    }

    var isValid: Bool {
        id > 0 && !question.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && (isSettled || (outcomeName?.isEmpty == false
                && probability.map { $0.isFinite && (0...1).contains($0) } == true))
    }
}

nonisolated enum WatchDiscoveryDecoder {
    private struct Feed: Decodable { let items: [Item] }
    private struct Item: Decodable {
        let reading: WatchDiscoveryReading?
        private enum CodingKeys: String, CodingKey { case type, data }
        init(from decoder: Decoder) throws {
            // An unsupported or malformed sibling does not erase healthy rows.
            guard let container = try? decoder.container(keyedBy: CodingKeys.self),
                  (try? container.decode(String.self, forKey: .type)) == "futures",
                  let data = try? container.decode(Market.self, forKey: .data) else {
                reading = nil
                return
            }
            reading = data.reading
        }
    }
    private struct Market: Decodable {
        let id: Int
        let name: String
        let topOutcomes: [Outcome]?
        let status: String?
        let resolved: Bool?
        let winner: String?
        // Deliberately do not decode resolution_date as settlement authority.
        var reading: WatchDiscoveryReading? {
            let namedWinner = winner?.trimmingCharacters(in: .whitespacesAndNewlines)
            let winner = namedWinner?.isEmpty == false ? namedWinner : nil
            let settled = resolved == true || winner != nil ||
                ["resolved", "closed", "settled", "finalized", "final"].contains(status?.lowercased() ?? "")
            let leader = topOutcomes?.first
            let name = leader?.name.trimmingCharacters(in: .whitespacesAndNewlines)
            let reading = WatchDiscoveryReading(
                id: id, question: self.name.trimmingCharacters(in: .whitespacesAndNewlines),
                outcomeName: name?.isEmpty == false ? name : nil,
                probability: settled ? nil : leader?.probability,
                // A price observation is not a result observation clock.
                observedAt: settled ? nil : leader?.priceObservedAt.flatMap(Self.date),
                isSettled: settled, winner: winner
            )
            return reading.isValid ? reading : nil
        }
        private static func date(_ value: String) -> Date? {
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return formatter.date(from: value) ?? ISO8601DateFormatter().date(from: value)
        }
    }
    private struct Outcome: Decodable {
        let name: String
        let probability: Double?
        let priceObservedAt: String?
    }

    static func decode(_ data: Data) throws -> [WatchDiscoveryReading] {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let feed = try decoder.decode(Feed.self, from: data)
        var seen = Set<Int>()
        return feed.items.compactMap(\.reading).filter { seen.insert($0.id).inserted }.prefix(3).map { $0 }
    }
}
