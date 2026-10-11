import Foundation

/// The canonical ceremony routes supported by the existing awards producer.
nonisolated enum WatchAwardsCeremony: String, CaseIterable, Identifiable, Sendable {
    case oscars, emmys, grammys, tonys
    var id: String { rawValue }
    var key: String { "event:awards:\(rawValue)" }
    var name: String {
        switch self {
        case .oscars: return "The Oscars"
        case .emmys: return "The Emmys"
        case .grammys: return "The Grammys"
        case .tonys: return "The Tony Awards"
        }
    }
    func accepts(key candidate: String) -> Bool {
        if candidate == key { return true }
        guard candidate.hasPrefix(key + "-") else { return false }
        let year = candidate.dropFirst(key.count + 1)
        return year.utf8.count == 4 && year.hasPrefix("20")
            && year.utf8.allSatisfy { (48...57).contains($0) }
    }
}

nonisolated struct WatchAwardsCategory: Identifiable, Equatable, Sendable {
    let id: Int
    let name: String
    /// Ceremony settlement is not proof of this category's winner.
    let resultUnconfirmed: Bool
}

nonisolated struct WatchAwardsPage: Equatable, Sendable {
    let key: String
    let name: String
    let categories: [WatchAwardsCategory]
    let isSaved: Bool
    let hasUnavailableCategories: Bool
}

nonisolated enum WatchAwardsError: Error { case invalid, unavailable, busy }

nonisolated enum WatchAwardsDecoder {
    private struct Slot<T: Decodable>: Decodable {
        let value: T?
        init(from decoder: Decoder) throws { value = try? T(from: decoder) }
    }
    private struct Event: Decodable { let key: String; let domain: String; let name: String }
    private struct Cache: Decodable { let availability: String; let quality: String }
    private struct Section: Decodable { let type: String; let marketIds: [Int] }
    private struct Child: Decodable {
        let marketId: Int
        let marketName: String
        let settled: Bool?
        let kind: String?
    }
    private struct Envelope: Decodable {
        let event: Event
        let cache: Cache
        let sections: [Slot<Section>]
        let children: [Slot<Child>]
    }

    static func decode(_ data: Data, ceremony: WatchAwardsCeremony,
                       requestedKey: String) throws -> WatchAwardsPage {
        guard data.count <= 2 * 1024 * 1024, ceremony.accepts(key: requestedKey) else {
            throw WatchAwardsError.invalid
        }
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let value = try decoder.decode(Envelope.self, from: data)
        guard value.event.domain == "awards", ceremony.accepts(key: value.event.key),
              requestedKey == ceremony.key || value.event.key == requestedKey,
              validName(value.event.name),
              ["full", "partial", "degraded"].contains(value.cache.quality) else {
            throw WatchAwardsError.invalid
        }
        guard ["live", "stale_ok"].contains(value.cache.availability) else {
            throw WatchAwardsError.unavailable
        }
        // Identity is the producer's category market ID. Conflicting duplicates
        // cannot authorize a destination; names and marquee winners never do.
        let children = Dictionary(grouping: value.children.compactMap(\.value), by: \.marketId)
        var omitted = value.cache.quality != "full"
            || value.children.contains { $0.value == nil }
        var categories: [WatchAwardsCategory] = []
        var seen = Set<Int>()
        for slot in value.sections {
            guard let section = slot.value else { omitted = true; continue }
            guard section.type == "categories" else { continue }
            for id in section.marketIds {
                guard seen.insert(id).inserted else { omitted = true; continue }
                guard id > 0, let matches = children[id], matches.count == 1,
                      let child = matches.first, child.kind == nil,
                      validName(child.marketName), categories.count < 64 else {
                    omitted = true; continue
                }
                categories.append(.init(id: id, name: child.marketName,
                                        resultUnconfirmed: child.settled != false))
            }
        }
        return .init(key: value.event.key, name: value.event.name, categories: categories,
                     isSaved: value.cache.availability == "stale_ok",
                     hasUnavailableCategories: omitted)
    }

    private static func validName(_ name: String) -> Bool {
        !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && name.utf8.count <= 2048
    }
}
