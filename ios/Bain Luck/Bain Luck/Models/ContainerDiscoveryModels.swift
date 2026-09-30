import Foundation

/// Optional, additive #9653 Browse payload. Older servers can omit the list;
/// an unknown/malformed card is ignored without erasing valid siblings.
nonisolated struct ContainerDiscoveryResponse: Decodable, Sendable {
    let collections: [ContainerHubCollection]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        collections = try c.decodeIfPresent([Slot].self, forKey: .collections)?.compactMap(\.collection) ?? []
    }

    private enum CodingKeys: String, CodingKey { case collections }
    private nonisolated struct Slot: Decodable, Sendable {
        let collection: ContainerHubCollection?
        init(from decoder: Decoder) throws {
            collection = try? ContainerHubCollection(from: decoder)
        }
    }
}

nonisolated enum ContainerDiscoveryLeague: String, CaseIterable, Hashable, Sendable {
    case nfl, mlb

    /// Matches backend season_windows.season_string for these two leagues.
    /// UTC prevents travel/time-zone settings selecting a different edition.
    func season(asOf now: Date) -> Int {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let year = calendar.component(.year, from: now)
        let month = calendar.component(.month, from: now)
        switch self {
        case .nfl: return month < 3 ? year - 1 : year
        case .mlb: return month >= 11 ? year + 1 : year
        }
    }
}

nonisolated struct ContainerDiscoveryRequest: Sendable {
    let league: ContainerDiscoveryLeague
    let season: Int

    static let path = "/api/containers/discover"
    var query: [String: String] {
        ["league": league.rawValue, "season": String(season), "limit": "20"]
    }

    /// The producer remains the publication authority. These checks refuse a
    /// mismatched/unsupported edition or dead destination instead of guessing.
    func entries(in response: ContainerDiscoveryResponse) -> [ContainerDiscoveryEntry] {
        var seen = Set<String>()
        return response.collections.compactMap { card in
            guard card.canOpen, card.id > 0, card.revision >= 1,
                  !card.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  card.edition.league == league.rawValue, card.edition.season == season,
                  card.gameCount >= 0, card.questionCount >= 0,
                  card.gameCount > 0 || card.questionCount > 0,
                  matchesEdition(card), seen.insert(card.slug).inserted else { return nil }
            return ContainerDiscoveryEntry(collection: card)
        }
    }

    private func matchesEdition(_ card: ContainerHubCollection) -> Bool {
        switch league {
        case .mlb:
            return card.edition.kind == "mlb_postseason" && card.edition.stage == nil
                && card.edition.week == nil && card.slug == "mlb-\(season)-postseason"
        case .nfl:
            guard card.edition.kind == "nfl_week", let week = card.edition.week,
                  (1...99).contains(week) else { return false }
            let prefix: String
            switch card.edition.stage {
            case "Regular Season": prefix = ""
            case "Pre Season": prefix = "preseason-"
            case "Post Season": prefix = "postseason-"
            default: return false
            }
            return card.slug == "nfl-\(season)-\(prefix)week-\(week)"
        }
    }
}

nonisolated struct ContainerDiscoveryEntry: Identifiable, Sendable {
    let collection: ContainerHubCollection
    var id: String { collection.slug }
    var subtitle: String {
        var parts: [String] = []
        if collection.gameCount > 0 {
            parts.append("\(collection.gameCount) \(collection.gameCount == 1 ? "game" : "games")")
        }
        if collection.questionCount > 0 {
            parts.append("\(collection.questionCount) \(collection.questionCount == 1 ? "question" : "questions")")
        }
        return parts.joined(separator: " · ")
    }

    @MainActor var route: Route {
        .containerHub(slug: collection.slug, name: collection.name)
    }
}
