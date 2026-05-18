import Foundation

// MARK: - Golf Leaderboard Models

/// Live golf leaderboard response with event status and player probabilities.
nonisolated struct GolfLeaderboardResponse: Decodable, Sendable {
    let status: String // "live" or "no_event"
    let eventName: String?
    let currentRound: Int?
    let lastUpdated: String?
    let tour: String?
    let playerCount: Int?
    let hasSnapshot: Bool?
    let players: [GolfLeaderboardPlayer]
    let message: String?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        status = try container.decode(String.self, forKey: .status)
        eventName = try container.decodeIfPresent(String.self, forKey: .eventName)
        currentRound = try container.decodeIfPresent(Int.self, forKey: .currentRound)
        lastUpdated = try container.decodeIfPresent(String.self, forKey: .lastUpdated)
        tour = try container.decodeIfPresent(String.self, forKey: .tour)
        playerCount = try container.decodeIfPresent(Int.self, forKey: .playerCount)
        hasSnapshot = try container.decodeIfPresent(Bool.self, forKey: .hasSnapshot)
        players = (try? container.decodeIfPresent([GolfLeaderboardPlayer].self, forKey: .players)) ?? []
        message = try container.decodeIfPresent(String.self, forKey: .message)
    }

    private enum CodingKeys: String, CodingKey {
        case status, eventName, currentRound, lastUpdated, tour, playerCount, hasSnapshot, players, message
    }
}

/// Player row on a live golf leaderboard.
nonisolated struct GolfLeaderboardPlayer: Decodable, Sendable, Identifiable {
    let position: String
    let name: String
    let score: String
    let totalScoreRaw: Int?
    let today: String
    let todayRaw: Int?
    let thru: String
    let hole: String
    let winProb: Double
    let winProbChange: Double?
    let positionChange: Int?
    let top5Prob: Double?
    let top10Prob: Double?
    let makeCutProb: Double?
    let currentRound: Int?

    var id: String { name }
}

// MARK: - Golf Landing Page Models

/// Golf landing response with tournaments, movers, current event, and schedule.
nonisolated struct GolfLandingResponse: Decodable, Sendable {
    let tournaments: [GolfTournamentData]
    let biggestMovers: [GolfMoverData]
    let currentEvent: GolfCurrentEventData?
    let totalTournaments: Int?
    let pgaSchedule: [GolfScheduleEntry]?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        tournaments = (try? container.decodeIfPresent([GolfTournamentData].self, forKey: .tournaments)) ?? []
        biggestMovers = (try? container.decodeIfPresent([GolfMoverData].self, forKey: .biggestMovers)) ?? []
        currentEvent = try container.decodeIfPresent(GolfCurrentEventData.self, forKey: .currentEvent)
        totalTournaments = try container.decodeIfPresent(Int.self, forKey: .totalTournaments)
        pgaSchedule = try container.decodeIfPresent([GolfScheduleEntry].self, forKey: .pgaSchedule)
    }

    private enum CodingKeys: String, CodingKey {
        case tournaments, biggestMovers, currentEvent, totalTournaments, pgaSchedule
    }
}

/// Golf tournament market data with participating golfers.
nonisolated struct GolfTournamentData: Decodable, Sendable, Identifiable {
    let key: String?
    let name: String
    let slug: String?
    let isMajor: Bool?
    let isTourEvent: Bool?
    let isWomens: Bool?
    let tour: String?
    let tourLabel: String?
    let commenceTime: String?
    let resolutionDate: String?
    let startDate: String?
    let endDate: String?
    let venue: String?
    let location: String?
    let scheduleStatus: String?
    let golfers: [GolfGolferData]

    var id: String { slug ?? name }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = try container.decodeIfPresent(String.self, forKey: .key)
        name = try container.decode(String.self, forKey: .name)
        slug = try container.decodeIfPresent(String.self, forKey: .slug)
        isMajor = try container.decodeIfPresent(Bool.self, forKey: .isMajor)
        isTourEvent = try container.decodeIfPresent(Bool.self, forKey: .isTourEvent)
        isWomens = try container.decodeIfPresent(Bool.self, forKey: .isWomens)
        tour = try container.decodeIfPresent(String.self, forKey: .tour)
        tourLabel = try container.decodeIfPresent(String.self, forKey: .tourLabel)
        commenceTime = try container.decodeIfPresent(String.self, forKey: .commenceTime)
        resolutionDate = try container.decodeIfPresent(String.self, forKey: .resolutionDate)
        startDate = try container.decodeIfPresent(String.self, forKey: .startDate)
        endDate = try container.decodeIfPresent(String.self, forKey: .endDate)
        venue = try container.decodeIfPresent(String.self, forKey: .venue)
        location = try container.decodeIfPresent(String.self, forKey: .location)
        scheduleStatus = try container.decodeIfPresent(String.self, forKey: .scheduleStatus)
        golfers = (try? container.decodeIfPresent([GolfGolferData].self, forKey: .golfers)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case key, name, slug, isMajor, isTourEvent, isWomens, tour, tourLabel
        case commenceTime, resolutionDate, startDate, endDate, venue, location, scheduleStatus, golfers
    }
}

/// Golfer probability row inside a tournament market.
nonisolated struct GolfGolferData: Decodable, Sendable, Identifiable {
    let name: String
    let probability: Double
    let rank: Int?
    let movement24h: Double?
    let openingProbability: Double?
    let americanOdds: String?

    var id: String { name }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        probability = (try? container.decode(Double.self, forKey: .probability)) ?? 0
        rank = try container.decodeIfPresent(Int.self, forKey: .rank)
        movement24h = try container.decodeIfPresent(Double.self, forKey: .movement24h)
        openingProbability = try container.decodeIfPresent(Double.self, forKey: .openingProbability)
        americanOdds = try container.decodeIfPresent(String.self, forKey: .americanOdds)
    }

    private enum CodingKeys: String, CodingKey {
        case name, probability, rank, movement24h = "movement24h", openingProbability, americanOdds
    }
}

/// Summary of the currently active golf event.
nonisolated struct GolfCurrentEventData: Decodable, Sendable {
    let key: String?
    let name: String?
    let slug: String?
    let venue: String?
    let golferCount: Int?
    let leader: String?
    let leaderProbability: Double?
    let topGolfers: [GolfGolferData]?

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        key = try container.decodeIfPresent(String.self, forKey: .key)
        name = try container.decodeIfPresent(String.self, forKey: .name)
        slug = try container.decodeIfPresent(String.self, forKey: .slug)
        venue = try container.decodeIfPresent(String.self, forKey: .venue)
        golferCount = try container.decodeIfPresent(Int.self, forKey: .golferCount)
        leader = try container.decodeIfPresent(String.self, forKey: .leader)
        leaderProbability = try container.decodeIfPresent(Double.self, forKey: .leaderProbability)
        topGolfers = try container.decodeIfPresent([GolfGolferData].self, forKey: .topGolfers)
    }

    private enum CodingKeys: String, CodingKey {
        case key, name, slug, venue, golferCount, leader, leaderProbability, topGolfers
    }
}

/// Golfer with notable movement on the golf landing page.
nonisolated struct GolfMoverData: Decodable, Sendable, Identifiable {
    let name: String
    let tournamentKey: String?
    let tournamentName: String?
    let movement24h: Double?
    let probability: Double?

    var id: String { name + (tournamentKey ?? "") }
}

/// Scheduled golf event shown on the golf landing page.
nonisolated struct GolfScheduleEntry: Decodable, Sendable, Identifiable {
    let eventName: String?
    let course: String?
    let startDate: String?
    let endDate: String?
    let status: String?
    let tour: String?
    let location: String?
    let country: String?

    var id: String { (eventName ?? "") + (startDate ?? "") }
}
