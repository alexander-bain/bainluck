import Foundation

// MARK: - Tournament hub (`GET /api/tournaments/{slug}`)
//
// The web hub's payload, decoded for the phone. It is a big response — 903 KB
// raw / 86 KB gzipped for `us-open` on 2026-09-03 — and two of its four largest
// members (`grids`, 404 KB; the per-row `trend` series inside `boards`, most of
// its 136 KB) are deliberately NOT modelled here, because nothing on the phone
// screen draws them. `JSONDecoder` still parses the whole tree; declaring fewer
// keys saves the allocation, not the parse.
//
// Every probability on this endpoint is a 0–1 FRACTION, and a genuinely missing
// price arrives as `null` — never as 0. So every probability below is `Double?`
// and must be rendered with `formatProbabilityOrDash`, never `?? 0`
// (`FormattingUtilities.swift`: "a probability we do not have is not a
// probability of zero"). Four of today's 40 slate matches are unpriced, which is
// exactly the row that would otherwise print a confident "<1%".

/// The whole hub response.
nonisolated struct TournamentHubResponse: Decodable, Sendable {
    let slug: String?
    let title: String?
    let subtitle: String?
    let season: String?
    let generatedAt: String?
    let drawReleased: Bool?
    let mainDrawLabel: String?
    let slate: TournamentHubSlate?
    let results: TournamentHubResults?
    let boards: [TournamentHubBoard]
    /// Draw grids keyed by draw slug. Modelled as an opaque COUNT, not a shape —
    /// see `TournamentHubOpaqueEntry`.
    let bracket: [String: [TournamentHubOpaqueEntry]]
    let eventLinks: TournamentHubEventLinks?
    let broadcasts: [TournamentHubBroadcast]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        slug = try c.decodeIfPresent(String.self, forKey: .slug)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle)
        season = try c.decodeIfPresent(String.self, forKey: .season)
        generatedAt = try c.decodeIfPresent(String.self, forKey: .generatedAt)
        drawReleased = try c.decodeIfPresent(Bool.self, forKey: .drawReleased)
        mainDrawLabel = try c.decodeIfPresent(String.self, forKey: .mainDrawLabel)
        slate = try c.decodeIfPresent(TournamentHubSlate.self, forKey: .slate)
        results = try c.decodeIfPresent(TournamentHubResults.self, forKey: .results)
        boards = (try? c.decodeIfPresent([TournamentHubBoard].self, forKey: .boards)) ?? []
        bracket = (try? c.decodeIfPresent([String: [TournamentHubOpaqueEntry]].self, forKey: .bracket)) ?? [:]
        eventLinks = try? c.decodeIfPresent(TournamentHubEventLinks.self, forKey: .eventLinks)
        broadcasts = (try? c.decodeIfPresent([TournamentHubBroadcast].self, forKey: .broadcasts)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case slug, title, subtitle, season, generatedAt, drawReleased, mainDrawLabel
        case slate, results, boards, bracket, eventLinks, broadcasts
    }
}

/// An element whose SHAPE we do not model, decoded purely so it can be counted.
///
/// `bracket` is `{"mens-singles": [], "womens-singles": []}` on every response
/// measured so far, so its populated shape has never been seen. Modelling a
/// guess and wrapping it in `try?` would be worse than not modelling it: a
/// decode failure would silently become "no bracket", and the screen would tell
/// Alex the draw is unavailable at the exact moment it arrived. Counting is a
/// claim we can always keep.
nonisolated struct TournamentHubOpaqueEntry: Decodable, Sendable {
    init(from decoder: Decoder) throws {}
}

// MARK: - Slate (today's order of play)

nonisolated struct TournamentHubSlate: Decodable, Sendable {
    let matches: [TournamentHubMatch]
    let count: Int?
    let priceState: String?
    let ageHours: Double?
    let newestObservedAt: String?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        matches = (try? c.decodeIfPresent([TournamentHubMatch].self, forKey: .matches)) ?? []
        count = try c.decodeIfPresent(Int.self, forKey: .count)
        priceState = try c.decodeIfPresent(String.self, forKey: .priceState)
        ageHours = try c.decodeIfPresent(Double.self, forKey: .ageHours)
        newestObservedAt = try c.decodeIfPresent(String.self, forKey: .newestObservedAt)
    }

    private enum CodingKeys: String, CodingKey {
        case matches, count, priceState, ageHours, newestObservedAt
    }
}

nonisolated struct TournamentHubMatch: Decodable, Sendable, Identifiable {
    let matchupKey: String
    let eventId: Int?
    let draw: String?
    let drawLabel: String?
    let round: String?
    let scheduledDate: String?
    /// `"in_progress"` while the match is being played, `"upcoming"` before it.
    let liveState: String?
    /// Free text from the scoreboard — "4th Set", "2nd Set".
    let statusDetail: String?
    let startIsTbd: Bool?
    let priced: Bool?
    let priceState: String?
    let sides: [TournamentHubSide]

    var id: String { matchupKey }
    var isLive: Bool { liveState == "in_progress" }

    /// `"espn:182711"` → `"182711"`.
    ///
    /// The slate's own `event_id` is null on all 40 of today's matches: the hub
    /// resolves ESPN competition ids for the FINISHED list only
    /// (`routes/tournaments.py` feeds `resolve_espn_competition_events` from
    /// `payload["results"]`), so a live match carries an id nobody dereferenced.
    /// The client tries this id against `event_links.by_espn` as a second
    /// channel, which costs one dictionary lookup and starts working the day the
    /// server widens that call.
    var espnCompetitionId: String? {
        guard matchupKey.hasPrefix("espn:") else { return nil }
        let id = String(matchupKey.dropFirst("espn:".count))
        return id.isEmpty ? nil : id
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        matchupKey = try c.decode(String.self, forKey: .matchupKey)
        eventId = try c.decodeIfPresent(Int.self, forKey: .eventId)
        draw = try c.decodeIfPresent(String.self, forKey: .draw)
        drawLabel = try c.decodeIfPresent(String.self, forKey: .drawLabel)
        round = try c.decodeIfPresent(String.self, forKey: .round)
        scheduledDate = try c.decodeIfPresent(String.self, forKey: .scheduledDate)
        liveState = try c.decodeIfPresent(String.self, forKey: .liveState)
        statusDetail = try c.decodeIfPresent(String.self, forKey: .statusDetail)
        startIsTbd = try c.decodeIfPresent(Bool.self, forKey: .startIsTbd)
        priced = try c.decodeIfPresent(Bool.self, forKey: .priced)
        priceState = try c.decodeIfPresent(String.self, forKey: .priceState)
        sides = (try? c.decodeIfPresent([TournamentHubSide].self, forKey: .sides)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case matchupKey, eventId, draw, drawLabel, round, scheduledDate
        case liveState, statusDetail, startIsTbd, priced, priceState, sides
    }
}

nonisolated struct TournamentHubSide: Decodable, Sendable, Identifiable {
    let entityKey: String
    let displayName: String
    let seed: Int?
    let country: String?
    let image: TournamentHubImage?
    /// 0–1 fraction, or nil when this side has no price at all.
    let probability: Double?
    let openingProbability: Double?
    let priceState: String?

    var id: String { entityKey }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityKey = try c.decode(String.self, forKey: .entityKey)
        displayName = try c.decode(String.self, forKey: .displayName)
        seed = try c.decodeIfPresent(Int.self, forKey: .seed)
        country = try c.decodeIfPresent(String.self, forKey: .country)
        image = try? c.decodeIfPresent(TournamentHubImage.self, forKey: .image)
        probability = try c.decodeIfPresent(Double.self, forKey: .probability)
        openingProbability = try c.decodeIfPresent(Double.self, forKey: .openingProbability)
        priceState = try c.decodeIfPresent(String.self, forKey: .priceState)
    }

    private enum CodingKeys: String, CodingKey {
        case entityKey, displayName, seed, country, image
        case probability, openingProbability, priceState
    }
}

/// `flag_url` converts to `flagUrl`, not `flagURL` — the house `.convertFromSnakeCase`
/// strategy uppercases one letter, it does not know acronyms.
nonisolated struct TournamentHubImage: Decodable, Sendable {
    let url: String?
    let flagUrl: String?
}

// MARK: - Results (finished matches)

nonisolated struct TournamentHubResults: Decodable, Sendable {
    let matches: [TournamentHubResult]
    let count: Int?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        matches = (try? c.decodeIfPresent([TournamentHubResult].self, forKey: .matches)) ?? []
        count = try c.decodeIfPresent(Int.self, forKey: .count)
    }

    private enum CodingKeys: String, CodingKey { case matches, count }
}

nonisolated struct TournamentHubResult: Decodable, Sendable, Identifiable {
    let matchupKey: String
    let drawLabel: String?
    let round: String?
    let players: [TournamentHubResultPlayer]
    let winnerEntityKey: String?
    let score: String?
    /// `"final"`, `"retired"`, `"walkover"` — a retirement is not a scoreline.
    let completion: String?
    let completedAt: String?
    let espnCompetitionId: String?

    var id: String { matchupKey }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        matchupKey = try c.decode(String.self, forKey: .matchupKey)
        drawLabel = try c.decodeIfPresent(String.self, forKey: .drawLabel)
        round = try c.decodeIfPresent(String.self, forKey: .round)
        players = (try? c.decodeIfPresent([TournamentHubResultPlayer].self, forKey: .players)) ?? []
        winnerEntityKey = try c.decodeIfPresent(String.self, forKey: .winnerEntityKey)
        score = try c.decodeIfPresent(String.self, forKey: .score)
        completion = try c.decodeIfPresent(String.self, forKey: .completion)
        completedAt = try c.decodeIfPresent(String.self, forKey: .completedAt)
        espnCompetitionId = try c.decodeIfPresent(String.self, forKey: .espnCompetitionId)
    }

    private enum CodingKeys: String, CodingKey {
        case matchupKey, drawLabel, round, players, winnerEntityKey
        case score, completion, completedAt, espnCompetitionId
    }
}

nonisolated struct TournamentHubResultPlayer: Decodable, Sendable, Identifiable {
    let entityKey: String
    let displayName: String
    let seed: Int?
    let isWinner: Bool?
    let image: TournamentHubImage?
    let prematchProbability: Double?

    var id: String { entityKey }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityKey = try c.decode(String.self, forKey: .entityKey)
        displayName = try c.decode(String.self, forKey: .displayName)
        seed = try c.decodeIfPresent(Int.self, forKey: .seed)
        isWinner = try c.decodeIfPresent(Bool.self, forKey: .isWinner)
        image = try? c.decodeIfPresent(TournamentHubImage.self, forKey: .image)
        prematchProbability = try c.decodeIfPresent(Double.self, forKey: .prematchProbability)
    }

    private enum CodingKeys: String, CodingKey {
        case entityKey, displayName, seed, isWinner, image, prematchProbability
    }
}

// MARK: - Boards (who wins the title)

nonisolated struct TournamentHubBoard: Decodable, Sendable, Identifiable {
    let draw: String
    let label: String?
    let rows: [TournamentHubBoardRow]
    let priceState: String?
    let contenders: Int?

    var id: String { draw }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        draw = try c.decode(String.self, forKey: .draw)
        label = try c.decodeIfPresent(String.self, forKey: .label)
        rows = (try? c.decodeIfPresent([TournamentHubBoardRow].self, forKey: .rows)) ?? []
        priceState = try c.decodeIfPresent(String.self, forKey: .priceState)
        contenders = try c.decodeIfPresent(Int.self, forKey: .contenders)
    }

    private enum CodingKeys: String, CodingKey {
        case draw, label, rows, priceState, contenders
    }
}

nonisolated struct TournamentHubBoardRow: Decodable, Sendable, Identifiable {
    let entityKey: String
    let displayName: String
    let seed: Int?
    let country: String?
    let image: TournamentHubImage?
    /// `"live"` while the player is still in the draw.
    let state: String?
    let probability: Double?
    let rank: Int?
    /// Change in the 0–1 fraction over the tournament's tracked window.
    let trendDelta: Double?
    let sourceCount: Int?

    var id: String { entityKey }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityKey = try c.decode(String.self, forKey: .entityKey)
        displayName = try c.decode(String.self, forKey: .displayName)
        seed = try c.decodeIfPresent(Int.self, forKey: .seed)
        country = try c.decodeIfPresent(String.self, forKey: .country)
        image = try? c.decodeIfPresent(TournamentHubImage.self, forKey: .image)
        state = try c.decodeIfPresent(String.self, forKey: .state)
        probability = try c.decodeIfPresent(Double.self, forKey: .probability)
        rank = try c.decodeIfPresent(Int.self, forKey: .rank)
        trendDelta = try c.decodeIfPresent(Double.self, forKey: .trendDelta)
        sourceCount = try c.decodeIfPresent(Int.self, forKey: .sourceCount)
    }

    private enum CodingKeys: String, CodingKey {
        case entityKey, displayName, seed, country, image
        case state, probability, rank, trendDelta, sourceCount
    }
}

// MARK: - Links and broadcasts

nonisolated struct TournamentHubEventLinks: Decodable, Sendable {
    /// ESPN competition id → our `events.id`. 160 entries for `us-open` today,
    /// all of them from the finished list.
    let byEspn: [String: Int]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        byEspn = (try? c.decodeIfPresent([String: Int].self, forKey: .byEspn)) ?? [:]
    }

    private enum CodingKeys: String, CodingKey { case byEspn }
}

nonisolated struct TournamentHubBroadcast: Decodable, Sendable, Identifiable {
    let region: String
    let channels: [String]
    let note: String?

    var id: String { region }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        region = try c.decode(String.self, forKey: .region)
        channels = (try? c.decodeIfPresent([String].self, forKey: .channels)) ?? []
        note = try c.decodeIfPresent(String.self, forKey: .note)
    }

    private enum CodingKeys: String, CodingKey { case region, channels, note }
}
