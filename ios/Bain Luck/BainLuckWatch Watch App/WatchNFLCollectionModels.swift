import Foundation

/// Published membership and route identity; never a freshness or result claim.
nonisolated struct WatchNFLWeek: Decodable, Identifiable, Sendable, Equatable {
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
        let stage: String?
        let week: Int?

        var expectedSlug: String? {
            guard kind == "nfl_week", league == "nfl", season > 0,
                  let week, (1...99).contains(week) else { return nil }
            let prefix: String
            switch stage {
            case "Regular Season": prefix = ""
            case "Pre Season": prefix = "preseason-"
            case "Post Season": prefix = "postseason-"
            default: return nil
            }
            return "nfl-\(season)-\(prefix)week-\(week)"
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

nonisolated struct WatchNFLGame: Identifiable, Sendable, Equatable {
    let id: Int
    let home: String
    let away: String
    let status: String?
    let scheduledStart: String?
    let startIsTbd: Bool?
    let startedWithoutResult: Bool?
    let authorityNotStarted: Bool?
    let homeScore: Int?
    let awayScore: Int?
    let scoreSource: String?
    let scoreObservedAt: String?
    let heroProbability: Double?
    let heroProbabilitySource: String?
}

/// A published week market identity, not a game-level chance or cached result.
nonisolated struct WatchNFLQuestion: Identifiable, Sendable, Equatable {
    let id: Int
    let name: String
}

nonisolated struct WatchNFLMembership: Sendable {
    let published: Bool
    let revision: Int?
    let games: [WatchNFLGame]
    let hasOtherEntries: Bool
    let questions: [WatchNFLQuestion]

    init(published: Bool, revision: Int?, games: [WatchNFLGame], hasOtherEntries: Bool,
         questions: [WatchNFLQuestion] = []) {
        self.published = published; self.revision = revision; self.games = games
        self.hasOtherEntries = hasOtherEntries; self.questions = questions
    }
}

nonisolated enum WatchNFLDecodeError: Error { case invalid }

nonisolated enum WatchNFLCollectionDecoder {
    private struct Slot<T: Decodable>: Decodable {
        let value: T?
        init(from decoder: Decoder) throws { value = try? T(from: decoder) }
    }
    private struct Index: Decodable { let collections: [Slot<WatchNFLWeek>] }
    private struct Header: Decodable { let id: Int; let slug: String }
    private struct EventCard: Decodable {
        let id: Int
        let homeTeam: String?
        let awayTeam: String?
        let status: String?
        let sport: String?
        let commenceTime: String?
        let startIsTbd: Bool?
        let startedWithoutResult: Bool?
        let authorityNotStarted: Bool?
        let homeScore: Int?
        let awayScore: Int?
        let scoreSource: String?
        let scoreObservedAt: String?
        let heroProbability: Double?
        let heroProbabilitySource: String?

        enum CodingKeys: String, CodingKey {
            case id, homeTeam, awayTeam, status, sport, commenceTime, startIsTbd
            case startedWithoutResult, authorityNotStarted, homeScore, awayScore
            case scoreSource, scoreObservedAt, heroProbability, heroProbabilitySource
        }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            id = try c.decode(Int.self, forKey: .id)
            homeTeam = try c.decodeIfPresent(String.self, forKey: .homeTeam)
            awayTeam = try c.decodeIfPresent(String.self, forKey: .awayTeam)
            sport = try c.decodeIfPresent(String.self, forKey: .sport)
            // Malformed optional presentation fields cannot erase a valid route.
            status = try? c.decode(String.self, forKey: .status)
            commenceTime = try? c.decode(String.self, forKey: .commenceTime)
            startIsTbd = try? c.decode(Bool.self, forKey: .startIsTbd)
            startedWithoutResult = try? c.decode(Bool.self, forKey: .startedWithoutResult)
            authorityNotStarted = try? c.decode(Bool.self, forKey: .authorityNotStarted)
            homeScore = try? c.decode(Int.self, forKey: .homeScore)
            awayScore = try? c.decode(Int.self, forKey: .awayScore)
            scoreSource = try? c.decode(String.self, forKey: .scoreSource)
            scoreObservedAt = try? c.decode(String.self, forKey: .scoreObservedAt)
            heroProbability = try? c.decode(Double.self, forKey: .heroProbability)
            heroProbabilitySource = try? c.decode(String.self, forKey: .heroProbabilitySource)
        }
    }
    private struct QuestionCard: Decodable { let id: Int; let name: String }
    private struct MemberSlot: Decodable {
        private struct Identity: Decodable { let type: String; let id: Int }
        let marketID: Int?
        let value: Member?
        init(from decoder: Decoder) throws {
            let identity = try? Identity(from: decoder)
            marketID = identity?.type == "market" ? identity?.id : nil
            value = try? Member(from: decoder)
        }
    }
    private struct Member: Decodable {
        let type: String
        let id: Int
        let containerId: Int
        let destination: WatchNFLWeek.Destination?
        let card: EventCard?
        let questionCard: QuestionCard?
        enum CodingKeys: String, CodingKey { case type, id, containerId, destination, card }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            type = try c.decode(String.self, forKey: .type)
            id = try c.decode(Int.self, forKey: .id)
            containerId = try c.decode(Int.self, forKey: .containerId)
            destination = try c.decodeIfPresent(WatchNFLWeek.Destination.self, forKey: .destination)
            card = type == "event" ? try c.decode(EventCard.self, forKey: .card) : nil
            questionCard = type == "market" ? try c.decode(QuestionCard.self, forKey: .card) : nil
        }
        var question: WatchNFLQuestion? {
            guard type == "market", id > 0, let questionCard, questionCard.id == id,
                  destination?.kind == "market", destination?.id == id,
                  destination?.api == "/api/futures/\(id)" else { return nil }
            let name = questionCard.name.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty, name.utf8.count <= 2048 else { return nil }
            return WatchNFLQuestion(id: id, name: name)
        }
        var game: WatchNFLGame? {
            guard type == "event", id > 0, let card, card.id == id,
                  card.sport == "americanfootball_nfl",
                  destination?.kind == "event", destination?.id == id,
                  destination?.api == "/api/events/\(id)",
                  let rawHome = card.homeTeam, let rawAway = card.awayTeam else { return nil }
            let home = rawHome.trimmingCharacters(in: .whitespacesAndNewlines)
            let away = rawAway.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !home.isEmpty, !away.isEmpty else { return nil }
            return WatchNFLGame(id: id, home: home, away: away, status: card.status,
                scheduledStart: card.status == "scheduled" && card.startIsTbd == false ? card.commenceTime : nil,
                startIsTbd: card.startIsTbd, startedWithoutResult: card.startedWithoutResult,
                authorityNotStarted: card.authorityNotStarted,
                homeScore: card.homeScore, awayScore: card.awayScore,
                scoreSource: card.scoreSource, scoreObservedAt: card.scoreObservedAt,
                heroProbability: card.heroProbability, heroProbabilitySource: card.heroProbabilitySource)
        }
    }
    private struct Section: Decodable { let members: [MemberSlot] }
    private struct Hub: Decodable {
        let state: String
        let slug: String
        let revision: Int?
        let edition: WatchNFLWeek.Edition?
        let container: Header?
        let sections: [Section]
        let withheldCount: Int
        enum CodingKeys: String, CodingKey { case state, slug, revision, edition, container, sections, withheldCount }
        init(from decoder: Decoder) throws {
            let c = try decoder.container(keyedBy: CodingKeys.self)
            state = try c.decode(String.self, forKey: .state)
            slug = try c.decode(String.self, forKey: .slug)
            revision = try c.decodeIfPresent(Int.self, forKey: .revision)
            edition = try c.decodeIfPresent(WatchNFLWeek.Edition.self, forKey: .edition)
            container = try c.decodeIfPresent(Header.self, forKey: .container)
            // Withdrawal must never expose injected stale members.
            sections = state == "published" ? try c.decode([Section].self, forKey: .sections) : []
            withheldCount = try c.decodeIfPresent(Int.self, forKey: .withheldCount) ?? 0
        }
    }
    private static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
    static func weeks(_ data: Data, season: Int) throws -> [WatchNFLWeek] {
        let index = try decoder().decode(Index.self, from: data)
        var seen = Set<String>()
        return index.collections.compactMap(\.value).filter {
            $0.isValid(season: season) && seen.insert($0.slug).inserted
        }
    }
    static func membership(_ data: Data, week: WatchNFLWeek) throws -> WatchNFLMembership {
        guard week.isValid(season: week.edition.season) else { throw WatchNFLDecodeError.invalid }
        let hub = try decoder().decode(Hub.self, from: data)
        guard hub.slug == week.slug else { throw WatchNFLDecodeError.invalid }
        guard hub.state == "published" else {
            return WatchNFLMembership(published: false, revision: nil, games: [], hasOtherEntries: false)
        }
        guard let revision = hub.revision, revision >= week.revision,
              hub.edition == week.edition, hub.container?.id == week.id,
              hub.container?.slug == week.slug, hub.withheldCount >= 0 else { throw WatchNFLDecodeError.invalid }
        var seen = Set<Int>()
        let questionClaims = hub.sections.flatMap(\.members).reduce(into: [Int: Int]()) { counts, slot in
            if let id = slot.marketID { counts[id, default: 0] += 1 }
        }
        var questions: [WatchNFLQuestion] = []
        var other = hub.withheldCount > 0
        var games: [WatchNFLGame] = []
        for section in hub.sections {
            for slot in section.members {
                guard let member = slot.value, member.containerId == week.id else { other = true; continue }
                if member.type == "market" {
                    guard let question = member.question, questionClaims[question.id] == 1 else { other = true; continue }
                    questions.append(question)
                } else {
                    guard let game = member.game, seen.insert(game.id).inserted else { other = true; continue }
                    games.append(game)
                }
            }
        }
        return WatchNFLMembership(published: true, revision: revision, games: games, hasOtherEntries: other, questions: questions)
    }
    static func season(asOf now: Date) -> Int {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        let year = calendar.component(.year, from: now)
        return calendar.component(.month, from: now) < 3 ? year - 1 : year
    }
}
