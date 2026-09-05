import Foundation

// MARK: - Tournament hub (`GET /api/tournaments/{slug}`)
//
// The web hub's payload, decoded for the phone. It is a big response — 903 KB
// raw / 86 KB gzipped for `us-open` on 2026-09-03 — and its largest member
// (`grids`, 404 KB) is deliberately NOT modelled here, because nothing on the
// phone screen draws it. `JSONDecoder` still parses the whole tree; declaring
// fewer keys saves the allocation, not the parse.
//
// The per-row `trend` series inside `boards` (most of its 136 KB) WAS in that
// same list until the RACE chart landed (#2911): the phone now draws it, so it
// is modelled. It is the one member here whose cost is worth restating — 36
// contenders × ~30 daily points on the men's board — and `RaceChart.series`
// keeps only the top three, so the allocation survives exactly as long as the
// decode.
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
    /// When the main draw begins, as the register published it —
    /// `2026-08-30T11:00:00-04:00`. The RACE chart's `Draw` window is anchored
    /// on this and on nothing else; see `RaceChart.windowStarts`.
    let mainDrawStartsAt: String?
    let slate: TournamentHubSlate?
    let results: TournamentHubResults?
    let boards: [TournamentHubBoard]
    /// Draw grids keyed by draw slug. Modelled as an opaque COUNT, not a shape —
    /// see `TournamentHubOpaqueEntry`.
    let bracket: [String: [TournamentHubOpaqueEntry]]
    let eventLinks: TournamentHubEventLinks?
    let broadcasts: [TournamentHubBroadcast]
    /// The curated questions — "Will Sinner actually play?" (#3043). Five
    /// entries for `us-open` today; the register caps it, not the client.
    let props: [TournamentHubProp]

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        slug = try c.decodeIfPresent(String.self, forKey: .slug)
        title = try c.decodeIfPresent(String.self, forKey: .title)
        subtitle = try c.decodeIfPresent(String.self, forKey: .subtitle)
        season = try c.decodeIfPresent(String.self, forKey: .season)
        generatedAt = try c.decodeIfPresent(String.self, forKey: .generatedAt)
        drawReleased = try c.decodeIfPresent(Bool.self, forKey: .drawReleased)
        mainDrawLabel = try c.decodeIfPresent(String.self, forKey: .mainDrawLabel)
        mainDrawStartsAt = try c.decodeIfPresent(String.self, forKey: .mainDrawStartsAt)
        slate = try c.decodeIfPresent(TournamentHubSlate.self, forKey: .slate)
        results = try c.decodeIfPresent(TournamentHubResults.self, forKey: .results)
        boards = (try? c.decodeIfPresent([TournamentHubBoard].self, forKey: .boards)) ?? []
        bracket = (try? c.decodeIfPresent([String: [TournamentHubOpaqueEntry]].self, forKey: .bracket)) ?? [:]
        eventLinks = try? c.decodeIfPresent(TournamentHubEventLinks.self, forKey: .eventLinks)
        broadcasts = (try? c.decodeIfPresent([TournamentHubBroadcast].self, forKey: .broadcasts)) ?? []
        props = (try? c.decodeIfPresent([TournamentHubProp].self, forKey: .props)) ?? []
    }

    private enum CodingKeys: String, CodingKey {
        case slug, title, subtitle, season, generatedAt, drawReleased, mainDrawLabel
        case mainDrawStartsAt, slate, results, boards, bracket, eventLinks, broadcasts
        case props
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
    /// The provider's own round name. Either field may be the one that says
    /// "Qualifying 2nd Round", which is what dates the chart's `Quals` window.
    let sourceRound: String?
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
        sourceRound = try c.decodeIfPresent(String.self, forKey: .sourceRound)
        players = (try? c.decodeIfPresent([TournamentHubResultPlayer].self, forKey: .players)) ?? []
        winnerEntityKey = try c.decodeIfPresent(String.self, forKey: .winnerEntityKey)
        score = try c.decodeIfPresent(String.self, forKey: .score)
        completion = try c.decodeIfPresent(String.self, forKey: .completion)
        completedAt = try c.decodeIfPresent(String.self, forKey: .completedAt)
        espnCompetitionId = try c.decodeIfPresent(String.self, forKey: .espnCompetitionId)
    }

    private enum CodingKeys: String, CodingKey {
        case matchupKey, drawLabel, round, sourceRound, players, winnerEntityKey
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
    /// One reading per DAY this contender was priced — the RACE chart's line
    /// (#2911). Sparse on purpose: a day with no reading is absent from the
    /// array and stays a gap on the chart, never interpolated or carried
    /// forward.
    let trend: [TournamentHubTrendPoint]?
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
        // Tolerant, like `image`: one malformed point must not cost the row its
        // price, its name and its place on the board. A chart that cannot be
        // drawn is a missing chart; a row that fails to decode is a missing
        // contender, which is the worse failure by a distance.
        trend = (try? c.decodeIfPresent([TournamentHubTrendPoint].self, forKey: .trend)) ?? nil
        sourceCount = try c.decodeIfPresent(Int.self, forKey: .sourceCount)
    }

    private enum CodingKeys: String, CodingKey {
        case entityKey, displayName, seed, country, image
        case state, probability, rank, trendDelta, trend, sourceCount
    }
}

/// One point on a contender's daily trend line.
///
/// `date` is a DAY (`2026-08-05`), not a timestamp, and is kept as the
/// payload's own string: `YYYY-MM-DD` sorts lexicographically exactly as it
/// sorts chronologically, so every window in `RaceChart` compares strings and
/// no part of the chart has to hold an opinion about midnight UTC.
nonisolated struct TournamentHubTrendPoint: Decodable, Sendable {
    let date: String?
    let probability: Double?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        date = try c.decodeIfPresent(String.self, forKey: .date)
        probability = try c.decodeIfPresent(Double.self, forKey: .probability)
    }

    /// Test seam — the decoder is the only other way to build one.
    init(date: String?, probability: Double?) {
        self.date = date
        self.probability = probability
    }

    private enum CodingKeys: String, CodingKey { case date, probability }
}

// MARK: - Props (the curated questions)

/// One curated question — the shape `frontend/lib/tournamentProps.ts` calls a
/// `PropMarket`, decoded for the phone (#3043).
///
/// ═══ WHY `settled` IS MODELLED BEFORE ANY OF THE PRICE TELEMETRY ═══
///
/// The register decides that a question has CLOSED; nothing on the client may
/// infer it (UX-P207, and Alex's standing ruling 2, "settled means settled").
/// The specimen is on the wire today:
///
///     key=sinner-competes   settled=true   settled_answer="No"
///     outcomes[0] = Yes, probability 0.01, still quoted by Kalshi
///
/// A client that decodes `probability` and ignores `settled` prints **"Yes 1%"**
/// as the current answer to a question that was answered **No** on 30 August.
/// Each half is locally true and the composite is the exact failure ruling 2
/// exists to prevent, so `settled` is not an optional nicety here — it is the
/// field that decides what the card is allowed to say.
///
/// The card's own health telemetry (`liquidity_reasons`, `mixed_freshness`,
/// `stale_outcomes`, `freshest_*`) is deliberately NOT modelled: the phone
/// draws none of it, and `age_hours` per printed outcome already carries the
/// only freshness fact the card states.
nonisolated struct TournamentHubProp: Decodable, Sendable, Identifiable {
    let key: String
    /// The question, phrased as a person would ask it.
    let title: String
    /// One clause on why it is interesting, or nil.
    let hook: String?
    let draw: String?
    let source: String?
    let outcomes: [TournamentHubPropOutcome]
    /// The outcome whose probability answers `title`. `nil` is a SUPPORTED
    /// state, not a missing value — it selects the ranked-field rendering.
    let answerEntityKey: String?
    /// How many MARKETS the register declared for this one question. Anything
    /// above 1 is a comparison, and a comparison missing a leg is never live
    /// (CERT-430). Absent reads as 1: treating an old capture as an ordinary
    /// card is the safe direction.
    let legs: Int?
    /// `true`, and only the literal `true`, means the question has closed.
    let settled: Bool?
    /// The result in words — "No". Nil when the register knows only THAT it closed.
    let settledAnswer: String?
    let settledAt: String?
    let priceState: String?
    let ageHours: Double?

    var id: String { key }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        key = try c.decode(String.self, forKey: .key)
        title = try c.decode(String.self, forKey: .title)
        hook = try c.decodeIfPresent(String.self, forKey: .hook)
        draw = try c.decodeIfPresent(String.self, forKey: .draw)
        source = try c.decodeIfPresent(String.self, forKey: .source)
        outcomes = (try? c.decodeIfPresent([TournamentHubPropOutcome].self, forKey: .outcomes)) ?? []
        answerEntityKey = try c.decodeIfPresent(String.self, forKey: .answerEntityKey)
        legs = try c.decodeIfPresent(Int.self, forKey: .legs)
        // NOT `(try? …) ?? false`. A payload that grows `settled: "yes"` one day
        // must fail this decode into `nil` and render OPEN, which a guard
        // catches — rather than quietly deciding every card on the page has
        // closed, or that this one has.
        settled = try? c.decodeIfPresent(Bool.self, forKey: .settled)
        settledAnswer = try c.decodeIfPresent(String.self, forKey: .settledAnswer)
        settledAt = try c.decodeIfPresent(String.self, forKey: .settledAt)
        priceState = try c.decodeIfPresent(String.self, forKey: .priceState)
        ageHours = try c.decodeIfPresent(Double.self, forKey: .ageHours)
    }

    private enum CodingKeys: String, CodingKey {
        case key, title, hook, draw, source, outcomes, answerEntityKey, legs
        case settled, settledAnswer, settledAt, priceState, ageHours
    }
}

/// One row of a question. `probabilityIsLive` is THIS row's own freshness, not
/// the card's: the rule the whole app shares is that a card is as fresh as its
/// oldest printed number, and that rule needs the per-row flag to compute.
nonisolated struct TournamentHubPropOutcome: Decodable, Sendable, Identifiable {
    let entityKey: String
    let displayName: String
    /// 0–1 fraction, or nil when this row has no price at all. Never `?? 0`.
    let probability: Double?
    let probabilityIsLive: Bool?
    let ageHours: Double?
    let priceState: String?
    /// Does this row answer the card's question? Curated, never inferred.
    let isAnswer: Bool?

    var id: String { entityKey }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        entityKey = try c.decode(String.self, forKey: .entityKey)
        displayName = try c.decode(String.self, forKey: .displayName)
        probability = try c.decodeIfPresent(Double.self, forKey: .probability)
        probabilityIsLive = try c.decodeIfPresent(Bool.self, forKey: .probabilityIsLive)
        ageHours = try c.decodeIfPresent(Double.self, forKey: .ageHours)
        priceState = try c.decodeIfPresent(String.self, forKey: .priceState)
        isAnswer = try c.decodeIfPresent(Bool.self, forKey: .isAnswer)
    }

    private enum CodingKeys: String, CodingKey {
        case entityKey, displayName, probability, probabilityIsLive
        case ageHours, priceState, isAnswer
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
