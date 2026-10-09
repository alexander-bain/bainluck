import Foundation

/// This edition is the producer's postseason root, not a round or series.
nonisolated struct WatchMLBCollection: Decodable, Identifiable, Sendable, Equatable {
    let type: String
    let id: Int
    let name: String
    let slug: String
    let state: String
    let revision: Int
    let edition: Edition
    let gameCount: Int
    let questionCount: Int
    let destination: Destination

    nonisolated struct Edition: Decodable, Sendable, Equatable {
        let kind: String
        let league: String
        let season: Int
        var expectedSlug: String? {
            guard kind == "mlb_postseason", league == "mlb", (1903...9999).contains(season) else { return nil }
            return "mlb-\(season)-postseason"
        }
    }
    nonisolated struct Destination: Decodable, Sendable, Equatable {
        let kind: String
        let id: Int?
        let slug: String?
        let api: String
    }
    func isValid(season: Int) -> Bool {
        type == "collection" && state == "published" && id > 0 && revision > 0
            && !name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
            && edition.season == season && edition.expectedSlug == slug
            && gameCount >= 0 && questionCount >= 0 && (gameCount > 0 || questionCount > 0)
            && destination.kind == "container" && destination.slug == slug
            && destination.api == "/api/containers/\(slug)"
    }
}

nonisolated struct WatchMLBGame: Identifiable, Sendable, Equatable {
    let id: Int
    let home: String
    let away: String
    let stateText: String
    let scheduledStart: Date?
    let startContext: String?
}

/// Published child names are reader labels only. The current producer defines
/// no distinct MLB round/series edition, so this type deliberately has no route.
nonisolated struct WatchMLBChildLabel: Identifiable, Sendable, Equatable {
    let id: Int
    let name: String
}

nonisolated struct WatchMLBMembership: Sendable {
    enum Availability: Sendable, Equatable { case published, empty, unavailable }
    let availability: Availability
    let revision: Int?
    let games: [WatchMLBGame]
    let children: [WatchMLBChildLabel]
    let hasOtherEntries: Bool
    var published: Bool { availability == .published }
}

nonisolated enum WatchMLBCollectionError: Error { case invalid, serviceBusy }

nonisolated enum WatchMLBCollectionDecoder {
    private struct Slot<T: Decodable>: Decodable {
        let value: T?
        init(from decoder: Decoder) throws { value = try? T(from: decoder) }
    }
    private struct Index: Decodable { let collections: [Slot<WatchMLBCollection>] }
    private struct Header: Decodable { let id: Int; let slug: String }
    private struct Child: Decodable {
        let id: Int
        let name: String
        let slug: String
        let publicationState: String
        // Deliberately not decoded as a supported destination. A nonnull URL
        // without a known independent MLB edition cannot authorize navigation.
    }
    private struct Card: Decodable {
        let id: Int
        let homeTeam: String?
        let awayTeam: String?
        let status: String?
        let sport: String?
        let commenceTime: String?
        let startIsTbd: Bool?
        let startedWithoutResult: Bool?
    }
    private struct Member: Decodable {
        let type: String
        let id: Int
        let containerId: Int
        let destination: WatchMLBCollection.Destination?
        let card: Card?
        enum CodingKeys: String, CodingKey { case type, id, containerId, destination, card }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            type = try c.decode(String.self, forKey: .type)
            id = try c.decode(Int.self, forKey: .id)
            containerId = try c.decode(Int.self, forKey: .containerId)
            destination = try c.decodeIfPresent(WatchMLBCollection.Destination.self, forKey: .destination)
            card = type == "event" ? try c.decode(Card.self, forKey: .card) : nil
        }
        var game: WatchMLBGame? {
            guard type == "event", id > 0, let card, card.id == id, card.sport == "baseball_mlb",
                  destination?.kind == "event", destination?.id == id,
                  destination?.api == "/api/events/\(id)",
                  let rawHome = card.homeTeam, let rawAway = card.awayTeam else { return nil }
            let home = rawHome.trimmingCharacters(in: .whitespacesAndNewlines)
            let away = rawAway.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !home.isEmpty, !away.isEmpty else { return nil }
            let state: String
            switch card.status {
            case "scheduled": state = card.startedWithoutResult == true ? "Waiting for an update" : "Scheduled"
            case "live", "in_progress": state = "Live"
            case "completed", "final": state = "Final"
            case "closed": state = "Closed"
            case "postponed": state = "Postponed"
            case "cancelled", "canceled": state = "Cancelled"
            case "suspended": state = "Suspended"
            default: state = "Game state unknown"
            }
            let showStart = card.status == "scheduled" && card.startedWithoutResult == false
            let date = showStart && card.startIsTbd == false ? parseDate(card.commenceTime) : nil
            let context = !showStart ? nil : card.startIsTbd == true ? "Start to be determined"
                : date == nil ? "Start time unavailable" : "Scheduled start"
            return WatchMLBGame(id: id, home: home, away: away, stateText: state,
                                scheduledStart: date, startContext: context)
        }
        private func parseDate(_ value: String?) -> Date? {
            guard let value else { return nil }
            let formatter = ISO8601DateFormatter()
            formatter.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            return formatter.date(from: value) ?? ISO8601DateFormatter().date(from: value)
        }
    }
    private struct Section: Decodable { let members: [Slot<Member>] }
    private struct Hub: Decodable {
        let state: String
        let slug: String
        let revision: Int?
        let edition: WatchMLBCollection.Edition?
        let container: Header?
        let sections: [Section]
        let children: [Slot<Child>]
        let withheldCount: Int
        enum CodingKeys: String, CodingKey { case state, slug, revision, edition, container, sections, children, withheldCount }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            state = try c.decode(String.self, forKey: .state)
            slug = try c.decode(String.self, forKey: .slug)
            revision = try c.decodeIfPresent(Int.self, forKey: .revision)
            edition = try c.decodeIfPresent(WatchMLBCollection.Edition.self, forKey: .edition)
            container = try c.decodeIfPresent(Header.self, forKey: .container)
            // Never decode stale injected rows for empty/withdrawn/unknown states.
            sections = state == "published" ? try c.decode([Section].self, forKey: .sections) : []
            children = state == "published" ? try c.decode([Slot<Child>].self, forKey: .children) : []
            withheldCount = try c.decodeIfPresent(Int.self, forKey: .withheldCount) ?? 0
        }
    }
    private static func decoder() -> JSONDecoder {
        let result = JSONDecoder()
        result.keyDecodingStrategy = .convertFromSnakeCase
        return result
    }
    static func collections(_ data: Data, season: Int) throws -> [WatchMLBCollection] {
        let index = try decoder().decode(Index.self, from: data)
        var seen = Set<String>()
        return index.collections.compactMap(\.value).filter {
            $0.isValid(season: season) && seen.insert($0.slug).inserted
        }
    }
    static func membership(_ data: Data, collection: WatchMLBCollection) throws -> WatchMLBMembership {
        guard collection.isValid(season: collection.edition.season) else { throw WatchMLBCollectionError.invalid }
        let hub = try decoder().decode(Hub.self, from: data)
        guard hub.slug == collection.slug else { throw WatchMLBCollectionError.invalid }
        guard ["published", "empty"].contains(hub.state) else {
            return WatchMLBMembership(availability: .unavailable, revision: nil, games: [], children: [], hasOtherEntries: false)
        }
        guard let revision = hub.revision, revision >= collection.revision,
              hub.edition == collection.edition, hub.container?.id == collection.id,
              hub.container?.slug == collection.slug, hub.withheldCount >= 0 else { throw WatchMLBCollectionError.invalid }
        guard hub.state == "published" else {
            return WatchMLBMembership(availability: .empty, revision: revision, games: [], children: [], hasOtherEntries: false)
        }
        var seenGames = Set<Int>(), seenChildren = Set<Int>(), seenSlugs: Set<String> = [collection.slug]
        var other = hub.withheldCount > 0
        var games: [WatchMLBGame] = [], children: [WatchMLBChildLabel] = []
        for section in hub.sections {
            for slot in section.members {
                guard let member = slot.value, member.containerId == collection.id,
                      let game = member.game, seenGames.insert(game.id).inserted else { other = true; continue }
                games.append(game)
            }
        }
        for slot in hub.children {
            other = true // No child is an actionable route in this contract version.
            guard let child = slot.value, child.publicationState == "published", child.id > 0,
                  child.id != collection.id, !child.slug.isEmpty,
                  !child.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
                  seenChildren.insert(child.id).inserted, seenSlugs.insert(child.slug).inserted else { continue }
            children.append(WatchMLBChildLabel(id: child.id, name: child.name))
        }
        return WatchMLBMembership(availability: .published, revision: revision, games: games,
                                  children: children, hasOtherEntries: other)
    }
    static func season(asOf now: Date) -> Int {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar.component(.year, from: now)
    }
}
