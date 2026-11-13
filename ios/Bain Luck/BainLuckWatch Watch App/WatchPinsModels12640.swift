import Foundation
#if canImport(Bain_Luck)
@testable import Bain_Luck
#endif

nonisolated enum WatchPinsDateParser12640 {
    static func parse(_ raw: String?) -> Date? {
        guard let raw, !raw.isEmpty else { return nil }
        let fractional = ISO8601DateFormatter()
        fractional.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = fractional.date(from: raw) { return d }
        let plain = ISO8601DateFormatter()
        plain.formatOptions = [.withInternetDateTime]
        return plain.date(from: raw)
    }

    static func encode(_ date: Date?) -> String? {
        guard let date else { return nil }
        let formatter = ISO8601DateFormatter()
        formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        return formatter.string(from: date)
    }
}

nonisolated enum WatchPinsPercent12640 {
    struct Formatted: Equatable, Sendable {
        let display: String
        let rounded: Int
        let subOne: Bool
        let aboveNinetyNine: Bool
    }

    /// Open market outcomes never print "0%" or "100%".
    static func format(_ probability: Double?) -> Formatted? {
        guard let probability, probability.isFinite, probability > 0, probability < 1 else {
            return nil
        }
        if probability < 0.005 {
            return Formatted(display: "<1%", rounded: 1, subOne: true, aboveNinetyNine: false)
        }
        if probability > 0.995 {
            return Formatted(display: ">99%", rounded: 99, subOne: false, aboveNinetyNine: true)
        }
        let rounded = min(99, max(1, Int((probability * 100).rounded())))
        return Formatted(display: "\(rounded)%", rounded: rounded, subOne: false, aboveNinetyNine: false)
    }
}

private nonisolated struct WatchFutureSkipOutcome12640: Decodable {}

nonisolated struct WatchFutureOutcome12640: Codable, Equatable, Sendable, Identifiable {
    let id: Int
    let name: String
    let probability: Double?
    let isWinner: Bool?
    let lastUpdated: Date?
    let observedAt: Date?

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case probability
        case isWinner = "is_winner"
        case lastUpdated = "last_updated"
        case observedAt = "observed_at"
        case priceChangedAt = "price_changed_at"
    }

    init(
        id: Int,
        name: String,
        probability: Double?,
        isWinner: Bool? = nil,
        lastUpdated: Date? = nil,
        observedAt: Date? = nil
    ) {
        self.id = id
        self.name = name
        self.probability = probability
        self.isWinner = isWinner
        self.lastUpdated = lastUpdated
        self.observedAt = observedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let decodedID = try c.decode(Int.self, forKey: .id)
        guard decodedID > 0 else {
            throw DecodingError.dataCorruptedError(forKey: .id, in: c, debugDescription: "Invalid outcome id")
        }
        let decodedName = try c.decode(String.self, forKey: .name).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !decodedName.isEmpty else {
            throw DecodingError.dataCorruptedError(forKey: .name, in: c, debugDescription: "Empty outcome name")
        }
        id = decodedID
        name = decodedName
        let rawProb = try? c.decodeIfPresent(Double.self, forKey: .probability)
        probability = rawProb.flatMap { $0.isFinite ? $0 : nil }
        isWinner = try? c.decodeIfPresent(Bool.self, forKey: .isWinner)
        let rawLast = try? c.decodeIfPresent(String.self, forKey: .lastUpdated)
        let rawChanged = try? c.decodeIfPresent(String.self, forKey: .priceChangedAt)
        let rawObserved = try? c.decodeIfPresent(String.self, forKey: .observedAt)
        lastUpdated = WatchPinsDateParser12640.parse(rawLast ?? rawChanged)
        observedAt = WatchPinsDateParser12640.parse(rawObserved)
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(name, forKey: .name)
        try c.encodeIfPresent(probability, forKey: .probability)
        try c.encodeIfPresent(isWinner, forKey: .isWinner)
        try c.encodeIfPresent(WatchPinsDateParser12640.encode(lastUpdated), forKey: .lastUpdated)
        try c.encodeIfPresent(WatchPinsDateParser12640.encode(observedAt), forKey: .observedAt)
    }

    var formattedProbability: WatchPinsPercent12640.Formatted? {
        WatchPinsPercent12640.format(probability)
    }

    var effectiveObservedAt: Date? {
        observedAt ?? lastUpdated
    }
}

/// Public `/api/futures/{id}` reading for a pinned market on Apple Watch (#12640).
nonisolated struct WatchFutureDetail12640: Codable, Equatable, Sendable, Identifiable {
    let id: Int
    let name: String
    let status: String?
    let pricesWithheld: Int?
    let leadOutcomeId: Int?
    let updatedAt: Date?
    let outcomes: [WatchFutureOutcome12640]

    private enum CodingKeys: String, CodingKey {
        case id
        case name
        case status
        case pricesWithheld = "prices_withheld"
        case leadOutcomeId = "lead_outcome_id"
        case updatedAt = "updated_at"
        case outcomes
    }

    init(
        id: Int,
        name: String,
        status: String? = "open",
        pricesWithheld: Int? = 0,
        leadOutcomeId: Int? = nil,
        updatedAt: Date? = nil,
        outcomes: [WatchFutureOutcome12640]
    ) {
        self.id = id
        self.name = name
        self.status = status
        self.pricesWithheld = pricesWithheld
        self.leadOutcomeId = leadOutcomeId
        self.updatedAt = updatedAt
        self.outcomes = outcomes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        let decodedID = try c.decode(Int.self, forKey: .id)
        guard decodedID > 0 else {
            throw DecodingError.dataCorruptedError(forKey: .id, in: c, debugDescription: "Invalid market id")
        }
        let decodedName = try c.decode(String.self, forKey: .name).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !decodedName.isEmpty else {
            throw DecodingError.dataCorruptedError(forKey: .name, in: c, debugDescription: "Empty market name")
        }
        id = decodedID
        name = decodedName
        status = try? c.decodeIfPresent(String.self, forKey: .status)
        pricesWithheld = try? c.decodeIfPresent(Int.self, forKey: .pricesWithheld)
        leadOutcomeId = try? c.decodeIfPresent(Int.self, forKey: .leadOutcomeId)
        updatedAt = WatchPinsDateParser12640.parse(try? c.decodeIfPresent(String.self, forKey: .updatedAt))

        var decodedOutcomes: [WatchFutureOutcome12640] = []
        if var container = try? c.nestedUnkeyedContainer(forKey: .outcomes) {
            while !container.isAtEnd {
                if let leg = try? container.decode(WatchFutureOutcome12640.self) {
                    decodedOutcomes.append(leg)
                } else {
                    _ = try? container.decode(WatchFutureSkipOutcome12640.self)
                }
            }
        }
        outcomes = decodedOutcomes
    }

    func encode(to encoder: Encoder) throws {
        var c = encoder.container(keyedBy: CodingKeys.self)
        try c.encode(id, forKey: .id)
        try c.encode(name, forKey: .name)
        try c.encodeIfPresent(status, forKey: .status)
        try c.encodeIfPresent(pricesWithheld, forKey: .pricesWithheld)
        try c.encodeIfPresent(leadOutcomeId, forKey: .leadOutcomeId)
        try c.encodeIfPresent(WatchPinsDateParser12640.encode(updatedAt), forKey: .updatedAt)
        try c.encode(outcomes, forKey: .outcomes)
    }

    var isOpenForPricing: Bool {
        guard (pricesWithheld ?? 0) <= 0 else { return false }
        let normalized = status?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? "open"
        return normalized == "open" || normalized == "active"
    }

    /// Only outcomes with a real open probability in (0, 1), sorted highest chance first.
    var pricedOutcomes: [WatchFutureOutcome12640] {
        guard isOpenForPricing else { return [] }
        return outcomes
            .filter { $0.formattedProbability != nil }
            .sorted { lhs, rhs in
                let lp = lhs.probability ?? 0
                let rp = rhs.probability ?? 0
                if lp != rp { return lp > rp }
                return lhs.id < rhs.id
            }
    }

    /// Resolves the outcome shown in the pins list and on the Watch face:
    /// 1) the reader's explicit Watch or wire choice if still priced,
    /// 2) the server's `lead_outcome_id` if priced,
    /// 3) the highest-probability priced outcome.
    func resolvedOutcome(chosenOutcomeID: Int?, wireOutcomeID: Int? = nil) -> WatchFutureOutcome12640? {
        let candidates = pricedOutcomes
        guard !candidates.isEmpty else { return nil }
        if let chosenOutcomeID, let match = candidates.first(where: { $0.id == chosenOutcomeID }) {
            return match
        }
        if let wireOutcomeID, let match = candidates.first(where: { $0.id == wireOutcomeID }) {
            return match
        }
        if let leadOutcomeId, let match = candidates.first(where: { $0.id == leadOutcomeId }) {
            return match
        }
        return candidates.first
    }
}

/// Pure summary of a fetched game so `BainLuckTests` can verify admission and 4-bucket ordering
/// without importing Watch-only target files.
nonisolated struct WatchPinEventSummary12640: Equatable, Sendable {
    let id: Int
    let isLive: Bool
    let isFinal: Bool
    let showsForecast: Bool
    let homeRenderedPercent: Int?
    let homeScore: Int?
    let awayScore: Int?
    let commenceTime: Date?
    let scoreObservedAt: Date?

    var isAdmittedToWatchPins: Bool {
        if isFinal {
            guard let hs = homeScore, let ascore = awayScore else { return false }
            return hs >= 0 && ascore >= 0
        }
        return showsForecast && homeRenderedPercent != nil
    }
}

nonisolated enum WatchSelectedPinTarget12640: Codable, Equatable, Sendable {
    case event(id: Int)
    case future(marketID: Int, outcomeID: Int?)
}

nonisolated struct WatchPinnedOrderedEntry12640: Equatable, Sendable, Identifiable {
    enum Bucket: Int, Comparable, Sendable {
        case liveGame = 0
        case upcomingGame = 1
        case market = 2
        case finishedGame = 3

        static func < (lhs: Bucket, rhs: Bucket) -> Bool {
            lhs.rawValue < rhs.rawValue
        }
    }

    let wireItem: WatchPinWireItem12640
    let pinIndex: Int
    let bucket: Bucket
    let sortTime: Date?

    var id: String {
        "\(wireItem.kind.rawValue):\(wireItem.id):\(wireItem.outcomeId ?? 0)"
    }
}

nonisolated enum WatchPinsOrdering12640 {
    /// Applies #12640 admission ("nothing without a probability is shown", plus scored finals)
    /// and orders into:
    /// 1) live games first,
    /// 2) upcoming games soonest first,
    /// 3) markets in phone pin order,
    /// 4) finished games most recent first.
    static func rank(
        wireItems: [WatchPinWireItem12640],
        events: [Int: WatchPinEventSummary12640],
        futures: [Int: WatchFutureDetail12640],
        chosenOutcomes: [Int: Int]
    ) -> [WatchPinnedOrderedEntry12640] {
        var entries: [WatchPinnedOrderedEntry12640] = []
        for (index, item) in WatchPinsWire12640.sanitize(wireItems).enumerated() {
            switch item.kind {
            case .event:
                guard let summary = events[item.id], summary.isAdmittedToWatchPins else { continue }
                if summary.isLive {
                    entries.append(WatchPinnedOrderedEntry12640(
                        wireItem: item,
                        pinIndex: index,
                        bucket: .liveGame,
                        sortTime: summary.commenceTime
                    ))
                } else if summary.isFinal {
                    entries.append(WatchPinnedOrderedEntry12640(
                        wireItem: item,
                        pinIndex: index,
                        bucket: .finishedGame,
                        sortTime: summary.commenceTime ?? summary.scoreObservedAt
                    ))
                } else {
                    entries.append(WatchPinnedOrderedEntry12640(
                        wireItem: item,
                        pinIndex: index,
                        bucket: .upcomingGame,
                        sortTime: summary.commenceTime
                    ))
                }
            case .future:
                guard let market = futures[item.id],
                      market.resolvedOutcome(chosenOutcomeID: chosenOutcomes[item.id], wireOutcomeID: item.outcomeId) != nil else {
                    continue
                }
                entries.append(WatchPinnedOrderedEntry12640(
                    wireItem: item,
                    pinIndex: index,
                    bucket: .market,
                    sortTime: nil
                ))
            }
        }

        return entries.sorted { lhs, rhs in
            if lhs.bucket != rhs.bucket {
                return lhs.bucket < rhs.bucket
            }
            switch lhs.bucket {
            case .liveGame, .market:
                return lhs.pinIndex < rhs.pinIndex
            case .upcomingGame:
                switch (lhs.sortTime, rhs.sortTime) {
                case let (lt?, rt?) where lt != rt:
                    return lt < rt
                case (_?, nil):
                    return true
                case (nil, _?):
                    return false
                default:
                    return lhs.pinIndex < rhs.pinIndex
                }
            case .finishedGame:
                switch (lhs.sortTime, rhs.sortTime) {
                case let (lt?, rt?) where lt != rt:
                    return lt > rt
                case (_?, nil):
                    return true
                case (nil, _?):
                    return false
                default:
                    return lhs.pinIndex < rhs.pinIndex
                }
            }
        }
    }
}
