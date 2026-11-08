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
    let overflowOutcomes: [GolfGolferData]

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
        overflowOutcomes = try container.decodeIfPresent([GolfGolferData].self, forKey: .overflowOutcomes) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case key, name, slug, isMajor, isTourEvent, isWomens, tour, tourLabel
        case commenceTime, resolutionDate, startDate, endDate, venue, location, scheduleStatus, golfers, overflowOutcomes
    }
}

/// Golfer probability row inside a tournament market.
nonisolated struct GolfGolferData: Decodable, Sendable, Identifiable, Equatable {
    let name: String
    let probability: Double
    let renderedPercent: Int?
    let rank: Int?
    let movement24h: Double?
    let openingProbability: Double?
    let americanOdds: Int?
    var isWinner: Bool? = nil
    var won: Bool? = nil

    var id: String { name }

    init(
        name: String,
        probability: Double,
        renderedPercent: Int? = nil,
        rank: Int? = nil,
        movement24h: Double? = nil,
        openingProbability: Double? = nil,
        americanOdds: Int? = nil,
        isWinner: Bool? = nil,
        won: Bool? = nil
    ) {
        self.name = name
        self.probability = probability
        self.renderedPercent = renderedPercent
        self.rank = rank
        self.movement24h = movement24h
        self.openingProbability = openingProbability
        self.americanOdds = americanOdds
        self.isWinner = isWinner
        self.won = won
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        name = try container.decode(String.self, forKey: .name)
        probability = (try? container.decode(Double.self, forKey: .probability)) ?? 0
        renderedPercent = try container.decodeIfPresent(Int.self, forKey: .renderedPercent)
        rank = try container.decodeIfPresent(Int.self, forKey: .rank)
        // Tolerant: a malformed movement value must not erase this golfer or the
        // rest of the field.
        movement24h = try? container.decodeIfPresent(Double.self, forKey: .movement24h)
        openingProbability = try container.decodeIfPresent(Double.self, forKey: .openingProbability)
        americanOdds = try container.decodeIfPresent(Int.self, forKey: .americanOdds)
        isWinner = try? container.decodeIfPresent(Bool.self, forKey: .isWinner)
        won = try? container.decodeIfPresent(Bool.self, forKey: .won)
    }

    private enum CodingKeys: String, CodingKey {
        // `movement_24h` converts to the key `movement24H`, not `movement24h` —
        // the previous raw value here matched nothing. See `TolerantNumeric`.
        case name, probability, renderedPercent, rank, movement24h = "movement24H", openingProbability, americanOdds
        case isWinner, won
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
    /// `movement_24h`. See `TolerantNumeric`. Decode-only today — `biggestMovers`
    /// is parsed but no view reads it, so repairing the key changes no pixel.
    @TolerantNumeric var movement24h: Double?
    let probability: Double?

    var id: String { name + (tournamentKey ?? "") }

    private enum CodingKeys: String, CodingKey {
        case name, tournamentKey, tournamentName
        case movement24h = "movement24H"
        case probability
    }
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

// MARK: - One golf tournament (#1471)

/// `GET /api/golf/tournaments/{slug}` — the destination a golf tournament card
/// leads to.
///
/// ⚠️ **THIS IS NOT `/api/tournaments/{slug}`, AND THE DIFFERENCE IS A BUG ALEX
/// HIT.** That one is the *registered hub* — tennis draws — and it answers
/// `404 {"detail":"No registered tournament 'biltmore-championship-asheville'"}`
/// for every golf slug there is. Routing a golf tournament there is what
/// produced "Couldn't load Biltmore Championship Asheville" on his phone, and
/// why the retry button could not help: the second call is the same 404.
/// Measured 2026-09-16 — `/api/tournaments/us-open` 200, `/api/tournaments/the-open`
/// and `/api/tournaments/biltmore-championship-asheville` both 404, while
/// `/api/golf/tournaments/biltmore-championship-asheville` served 132 golfers.
///
/// The field arrives at the TOP LEVEL, not inside `tournament` — so
/// `tournament.golfers` is empty here and the field is read from `golfers`.
/// Do not "tidy" that by reaching for `tournament.golfers`; it is the shape the
/// server sends.
nonisolated struct GolfTournamentMarketGroup: Decodable, Equatable, Sendable {
    let type: String
    let label: String
    let marketIds: [Int]
    let marketNames: [String]

    init(type: String, label: String, marketIds: [Int], marketNames: [String] = []) {
        self.type = type
        self.label = label
        self.marketIds = marketIds
        self.marketNames = marketNames
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        label = (try? container.decodeIfPresent(String.self, forKey: .label)) ?? type
        marketIds = (try? container.decodeIfPresent([Int].self, forKey: .marketIds)) ?? []
        marketNames = (try? container.decodeIfPresent([String].self, forKey: .marketNames)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case type, label, marketIds, marketNames
    }
}

nonisolated struct GolfRoundTopOutcome: Decodable, Equatable, Identifiable, Sendable {
    let name: String
    let probability: Double
    let openingProbability: Double?

    var id: String { name }
}

nonisolated struct GolfRoundTopGroup: Decodable, Equatable, Identifiable, Sendable {
    let marketId: Int
    let marketName: String
    let round: Int?
    let topN: Int?
    let kind: String
    let label: String
    let source: String?
    let outcomes: [GolfRoundTopOutcome]
    let settled: Bool?
    let gradedWinner: String?

    var id: Int { marketId }
}

nonisolated struct GolfTournamentDetailResponse: Decodable, Sendable {
    let tournament: GolfTournamentData
    let golfers: [GolfGolferData]
    let overflowOutcomes: [GolfGolferData]
    let biggestMovers: [GolfMoverData]
    let evolutionMarketId: Int?
    let markets: [GolfTournamentMarketGroup]
    let roundTopGroups: [GolfRoundTopGroup]

    init(
        tournament: GolfTournamentData,
        golfers: [GolfGolferData],
        overflowOutcomes: [GolfGolferData] = [],
        biggestMovers: [GolfMoverData] = [],
        evolutionMarketId: Int? = nil,
        markets: [GolfTournamentMarketGroup] = [],
        roundTopGroups: [GolfRoundTopGroup] = []
    ) {
        self.tournament = tournament
        self.golfers = golfers
        self.overflowOutcomes = overflowOutcomes
        self.biggestMovers = biggestMovers
        self.evolutionMarketId = evolutionMarketId
        self.markets = markets
        self.roundTopGroups = roundTopGroups
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        tournament = try container.decode(GolfTournamentData.self, forKey: .tournament)
        // Tolerant on everything but the tournament itself: a malformed mover or
        // a field this build has not seen must not blank a page whose subject
        // decoded perfectly well (the per-item tolerance rule of #1471).
        golfers = (try? container.decodeIfPresent([GolfGolferData].self, forKey: .golfers)) ?? []
        overflowOutcomes = try container.decodeIfPresent([GolfGolferData].self, forKey: .overflowOutcomes) ?? []
        biggestMovers = (try? container.decodeIfPresent([GolfMoverData].self, forKey: .biggestMovers)) ?? []
        evolutionMarketId = try? container.decodeIfPresent(Int.self, forKey: .evolutionMarketId)
        markets = (try? container.decodeIfPresent([GolfTournamentMarketGroup].self, forKey: .markets)) ?? []
        roundTopGroups = (try? container.decodeIfPresent([GolfRoundTopGroup].self, forKey: .roundTopGroups)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case tournament, golfers, overflowOutcomes, biggestMovers
        case evolutionMarketId, markets, roundTopGroups
    }
}
