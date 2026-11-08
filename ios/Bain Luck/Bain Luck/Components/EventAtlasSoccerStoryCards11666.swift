import SwiftUI

/// #11666 Menu Items 13a–b — Native Event-page Atlas Soccer story cards (`soccer_*`):
/// - **13a (`BothTeamsToScoreCard`, `id: "soccer:bothTeamsToScore"`)**:
///   Full-game Both Teams to Score (`Yes` / `No`) across pregame, live, and final.
///   Never complements `No = 1 - Yes` or normalizes `Yes + No` to 100%; shows both
///   teams' actual goals during play and final goals after full-time without turning
///   in-play goals into a 100% probability or a self-graded settlement.
/// - **13b (`FirstTeamToScoreCard`, `id: "soccer:firstTeamToScore"`, & `HalvesCard`, `id: "soccer:halves"`)**:
///   1. First Team to Score (`Home`, `Away`, and served `No goal` / `Neither`) with
///      in-play observed score checkpoints (`scoreHistory` observation times, never
///      inferred goal times or settlements).
///   2. Half-by-Half Breakdown (`1st Half` and `2nd Half` 3-way `Home` / `Draw` / `Away`
///      with reported half goals from `StoredLineScore` when available).
extension EventAtlasSoccerCards11666 {

    private static func validOpenChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    // MARK: - 13a. Both Teams to Score ("Both teams to score")

    nonisolated enum BTTSRole: String, Equatable, Sendable {
        case yes
        case no
    }

    nonisolated struct BTTSLeg: Equatable, Identifiable, Sendable {
        var id: String { "soccer-btts:\(role.rawValue)" }
        let role: BTTSRole
        let label: String
        let rawOutcomeLabel: String
        let quotedChance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let pregameObservedAt: String?
        let result: OutcomeVerdict?
        let source: String?

        func current(at now: Date, phase: NBALadderCard9483.Phase) -> BTTSLeg {
            guard phase != .after else { return self }
            let hasPrice = phase == .before ? (quotedChance != nil || pregameChance != nil) : (quotedChance != nil)
            guard hasPrice, !NFLMilestoneCard9483.isRecent(observedAt, now: now) else {
                return self
            }
            return BTTSLeg(
                role: role,
                label: label,
                rawOutcomeLabel: rawOutcomeLabel,
                quotedChance: nil,
                pregameChance: phase == .before ? nil : pregameChance,
                observedAt: observedAt,
                pregameObservedAt: pregameObservedAt,
                result: result,
                source: source
            )
        }
    }

    nonisolated enum BTTSScoringSummary: Equatable, Sendable {
        case live(homeShort: String, homeGoals: Int, awayShort: String, awayGoals: Int)
        case final(homeShort: String, homeGoals: Int, awayShort: String, awayGoals: Int)
        case unavailable

        var summaryText: String {
            switch self {
            case .live(let homeShort, let homeGoals, let awayShort, let awayGoals):
                let homeState = homeGoals > 0 ? "Has scored" : "Yet to score"
                let awayState = awayGoals > 0 ? "Has scored" : "Yet to score"
                return "Goals so far: \(homeShort) \(homeGoals) (\(homeState)) · \(awayShort) \(awayGoals) (\(awayState))"
            case .final(let homeShort, let homeGoals, let awayShort, let awayGoals):
                return "Final goals: \(homeShort) \(homeGoals) – \(awayGoals) \(awayShort)"
            case .unavailable:
                return "Actual goals unavailable"
            }
        }
    }

    nonisolated struct BothTeamsToScoreCard: Equatable, Identifiable, Sendable {
        var id: String { "soccer:bothTeamsToScore" }
        let phase: NBALadderCard9483.Phase
        let legs: [BTTSLeg]
        let scoring: BTTSScoringSummary?
        let marketTitle: String
        let source: String?
        let sourceCount: Int

        var title: String {
            phase == .after ? "Full-time both teams to score" : "Both teams to score"
        }

        var reason: String {
            if phase == .after {
                return "Independent Yes and No outcomes graded against 90-minute goals"
            }
            return "Whether both clubs score at least once in 90 minutes · Yes and No are independent quotes"
        }

        func current(at now: Date) -> BothTeamsToScoreCard {
            guard phase != .after else { return self }
            let aged = legs.map { $0.current(at: now, phase: phase) }
            guard aged != legs else { return self }
            return BothTeamsToScoreCard(
                phase: phase,
                legs: aged,
                scoring: scoring,
                marketTitle: marketTitle,
                source: source,
                sourceCount: sourceCount
            )
        }
    }

    static func classifyBTTSRole(_ label: String) -> BTTSRole? {
        let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.range(of: #"^yes(?:\b|\s*\()"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .yes
        }
        if trimmed.range(of: #"^no(?:\b|\s*\()"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .no
        }
        return nil
    }

    static func isFullGameBTTSMarketName(_ name: String) -> Bool {
        let lower = name.lowercased()
        guard lower.range(of: #"\b(?:both\s+teams?\s+to\s+score|btts)\b"#, options: .regularExpression) != nil else {
            return false
        }
        if lower.range(of: #"\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|half[-\s]?time)\b"#, options: .regularExpression) != nil {
            return false
        }
        if lower.range(
            of: #"\b(?:and\s+over|and\s+under|over\/under|o\/u|result\s+and|winner\s+and|to\s+win\s+and|match\s+result|half\s*\/\s*full)\b"#,
            options: .regularExpression
        ) != nil {
            return false
        }
        return true
    }

    @MainActor
    static func buildBothTeamsToScoreCard(
        matrix: EventQuestionMatrix?,
        otherMarkets: [GameMarketOther],
        status: String?,
        commenceTime: Date?,
        homeShort: String,
        awayShort: String,
        homeScore: Int?,
        awayScore: Int?,
        now: Date = Date()
    ) -> BothTeamsToScoreCard? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after

        let scoring: BTTSScoringSummary? = {
            guard currentPhase != .before else { return nil }
            guard let h = homeScore, let a = awayScore else { return .unavailable }
            return finished
                ? .final(homeShort: homeShort, homeGoals: h, awayShort: awayShort, awayGoals: a)
                : .live(homeShort: homeShort, homeGoals: h, awayShort: awayShort, awayGoals: a)
        }()

        struct Candidate {
            let marketTitle: String
            let source: String?
            let sourceCount: Int
            let legs: [BTTSLeg]
            let score: Int
        }

        var candidates: [Candidate] = []

        // 1. Check game_question_matrix (10238.v1)
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let title = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !title.isEmpty, isFullGameBTTSMarketName(title) else { continue }
            if let periodKey = q.period?.key, periodKey != "full_game" { continue }
            guard q.options.count == 2 else { continue }

            var legsByRole: [BTTSRole: BTTSLeg] = [:]
            for o in q.options {
                guard let role = classifyBTTSRole(o.label), legsByRole[role] == nil else { break }
                let quoted = !finished && NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                    ? validOpenChance(o.published.quotedValue)
                    : nil
                let pin = NBALadderCard9483.pin(o)
                let settledReading: (probability: Double, at: String)? = {
                    guard let r = o.pregameReading, r.state == "available", r.basis == "pregame_pin",
                          let outId = r.outcomeId, o.contributorOutcomeIds == [outId],
                          let prob = validOpenChance(r.probability),
                          let at = r.observedAt, !at.isEmpty else { return nil }
                    return (prob, at)
                }()
                let pregameChance: Double? = {
                    switch currentPhase {
                    case .before: return quoted
                    case .during: return pin?.probability
                    case .after: return settledReading?.probability
                    }
                }()
                let pregameAt: String? = {
                    switch currentPhase {
                    case .before: return quoted != nil ? o.published.observedAt : nil
                    case .during: return pin?.at
                    case .after: return settledReading?.at
                    }
                }()
                let verdict: OutcomeVerdict? = finished
                    ? (o.result?.isWinner == true ? .won : o.result?.isWinner == false ? .lost : nil)
                    : nil

                legsByRole[role] = BTTSLeg(
                    role: role,
                    label: role == .yes ? "Yes" : "No",
                    rawOutcomeLabel: o.label,
                    quotedChance: quoted,
                    pregameChance: pregameChance,
                    observedAt: o.published.observedAt,
                    pregameObservedAt: pregameAt,
                    result: verdict,
                    source: o.published.source
                )
            }

            if let yesLeg = legsByRole[.yes], let noLeg = legsByRole[.no] {
                let ordered = [yesLeg, noLeg]
                let priced = ordered.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settled = ordered.filter { $0.result != nil }.count
                guard priced > 0 || settled > 0 else { continue }
                let distinctSources = Set(ordered.compactMap(\.source))
                candidates.append(
                    Candidate(
                        marketTitle: title,
                        source: distinctSources.count == 1 ? distinctSources.first : nil,
                        sourceCount: max(1, distinctSources.count),
                        legs: ordered,
                        score: priced * 10 + settled * 5 + 3
                    )
                )
            }
        }

        // 2. Check gameMarkets.other
        var byMarketKey: [String: (title: String, rows: [GameMarketOther])] = [:]
        var marketKeyOrder: [String] = []
        for row in otherMarkets {
            let mname = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !mname.isEmpty, isFullGameBTTSMarketName(mname) else { continue }
            let prefix = [row._marketId.map(String.init), row.source].compactMap { $0 }.first
            let key = "\(prefix ?? ""):\(mname)"
            if byMarketKey[key] == nil {
                marketKeyOrder.append(key)
                byMarketKey[key] = (mname, [row])
            } else {
                byMarketKey[key]?.rows.append(row)
            }
        }

        for key in marketKeyOrder {
            guard let group = byMarketKey[key], group.rows.count == 2 else { continue }
            var legsByRole: [BTTSRole: BTTSLeg] = [:]
            for row in group.rows {
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let role = classifyBTTSRole(outLabel), legsByRole[role] == nil else { break }
                let observedAt = row.observedAt
                let recent = NFLMilestoneCard9483.isRecent(observedAt, now: now)
                let quotedChance = !finished && recent ? validOpenChance(row.probability) : nil
                let pregameChance: Double? = currentPhase == .before
                    ? (recent ? validOpenChance(row.probability) : nil)
                    : validOpenChance(row.pregameMark)
                let verdict = OutcomeVerdict.verdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    marketResolved: finished
                )

                legsByRole[role] = BTTSLeg(
                    role: role,
                    label: role == .yes ? "Yes" : "No",
                    rawOutcomeLabel: outLabel,
                    quotedChance: quotedChance,
                    pregameChance: pregameChance,
                    observedAt: observedAt,
                    pregameObservedAt: currentPhase == .before ? observedAt : nil,
                    result: verdict,
                    source: row.source
                )
            }

            if let yesLeg = legsByRole[.yes], let noLeg = legsByRole[.no] {
                let ordered = [yesLeg, noLeg]
                let priced = ordered.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settled = ordered.filter { $0.result != nil }.count
                guard priced > 0 || settled > 0 else { continue }
                let distinctSources = Set(ordered.compactMap(\.source))
                candidates.append(
                    Candidate(
                        marketTitle: group.title,
                        source: distinctSources.count == 1 ? distinctSources.first : nil,
                        sourceCount: max(1, distinctSources.count),
                        legs: ordered,
                        score: priced * 10 + settled * 5
                    )
                )
            }
        }

        guard let best = candidates.max(by: { $0.score < $1.score }) else { return nil }
        return BothTeamsToScoreCard(
            phase: currentPhase,
            legs: best.legs,
            scoring: scoring,
            marketTitle: best.marketTitle,
            source: best.source,
            sourceCount: best.sourceCount
        )
    }

    // MARK: - 13b (Part 1). First Team to Score ("First team to score")

    nonisolated enum FirstTeamRole: String, Equatable, Sendable {
        case home
        case away
        case noGoal
    }

    nonisolated struct FirstTeamLeg: Equatable, Identifiable, Sendable {
        var id: String { "soccer-first-team:\(role.rawValue)" }
        let role: FirstTeamRole
        let label: String
        let rawOutcomeLabel: String
        let quotedChance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let pregameObservedAt: String?
        let result: OutcomeVerdict?
        let source: String?

        func current(at now: Date, phase: NBALadderCard9483.Phase) -> FirstTeamLeg {
            guard phase != .after else { return self }
            let hasPrice = phase == .before ? (quotedChance != nil || pregameChance != nil) : (quotedChance != nil)
            guard hasPrice, !NFLMilestoneCard9483.isRecent(observedAt, now: now) else {
                return self
            }
            return FirstTeamLeg(
                role: role,
                label: label,
                rawOutcomeLabel: rawOutcomeLabel,
                quotedChance: nil,
                pregameChance: phase == .before ? nil : pregameChance,
                observedAt: observedAt,
                pregameObservedAt: pregameObservedAt,
                result: result,
                source: source
            )
        }
    }

    nonisolated struct ScoreCheckpoint: Equatable, Identifiable, Sendable {
        let id: String
        let scoreText: String
        let observedAtText: String
    }

    nonisolated struct FirstTeamToScoreCard: Equatable, Identifiable, Sendable {
        var id: String { "soccer:firstTeamToScore" }
        let phase: NBALadderCard9483.Phase
        let legs: [FirstTeamLeg]
        let checkpoints: [ScoreCheckpoint]
        let marketTitle: String
        let source: String?
        let sourceCount: Int

        var title: String {
            phase == .after ? "Opening goal result" : "First team to score"
        }

        var reason: String {
            if phase == .after {
                return "Each outcome (both clubs and No goal) graded independently by the venue"
            }
            return "Opening goal chances for each club and No goal · independent readings"
        }

        func current(at now: Date) -> FirstTeamToScoreCard {
            guard phase != .after else { return self }
            let aged = legs.map { $0.current(at: now, phase: phase) }
            guard aged != legs else { return self }
            return FirstTeamToScoreCard(
                phase: phase,
                legs: aged,
                checkpoints: checkpoints,
                marketTitle: marketTitle,
                source: source,
                sourceCount: sourceCount
            )
        }
    }

    static func isFullGameFirstTeamMarketName(_ name: String) -> Bool {
        let lower = name.lowercased()
        guard lower.range(of: #"\b(?:first|1st)\s+team\s+to\s+score\b"#, options: .regularExpression) != nil else {
            return false
        }
        if lower.range(of: #"\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|half[-\s]?time|goalscorer|player)\b"#, options: .regularExpression) != nil {
            return false
        }
        return true
    }

    static func classifyFirstTeamRole(
        outcomeLabel: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> FirstTeamRole? {
        let trimmed = outcomeLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.range(
            of: #"^(?:no\s+goal|no\s+goals|neither|none|no\s+score|no\s+team|0\s*[-–:]\s*0)(?:\b|\s*\()"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil {
            return .noGoal
        }
        let cleaned = trimmed.replacingOccurrences(
            of: #"\s+(?:to\s+score\s+first|scores?\s+first)$"#,
            with: "",
            options: [.regularExpression, .caseInsensitive]
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        guard let side = resolveSoccerSide(
            candidate: cleaned,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort
        ) else { return nil }
        switch side {
        case .home: return .home
        case .away: return .away
        case .draw: return nil
        }
    }

    static func buildScoreCheckpoints(
        scoreHistory: [ScoreHistoryPoint]?,
        homeShort: String,
        awayShort: String
    ) -> [ScoreCheckpoint] {
        guard let points = scoreHistory, !points.isEmpty else { return [] }
        var checkpoints: [ScoreCheckpoint] = []
        var lastPair: (Int, Int)?
        for (idx, pt) in points.enumerated() {
            let pair = (pt.homeScore, pt.awayScore)
            if let prev = lastPair, prev == pair { continue }
            lastPair = pair
            let stamp = SourceAge.preciseStamp(pt.timestamp) ?? pt.timestamp
            checkpoints.append(
                ScoreCheckpoint(
                    id: "checkpoint-\(idx)-\(pt.homeScore)-\(pt.awayScore)",
                    scoreText: "\(homeShort) \(pt.homeScore) – \(pt.awayScore) \(awayShort)",
                    observedAtText: stamp
                )
            )
            if checkpoints.count >= 4 { break }
        }
        return checkpoints
    }

    @MainActor
    static func buildFirstTeamToScoreCard(
        matrix: EventQuestionMatrix?,
        otherMarkets: [GameMarketOther],
        scoreHistory: [ScoreHistoryPoint]? = nil,
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        now: Date = Date()
    ) -> FirstTeamToScoreCard? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after
        let liveCheckpoints = currentPhase == .during
            ? buildScoreCheckpoints(scoreHistory: scoreHistory, homeShort: homeShort, awayShort: awayShort)
            : []

        struct Candidate {
            let marketTitle: String
            let source: String?
            let sourceCount: Int
            let legs: [FirstTeamLeg]
            let score: Int
        }

        var candidates: [Candidate] = []
        let roleOrder: [FirstTeamRole] = [.home, .away, .noGoal]

        // 1. Check game_question_matrix (10238.v1)
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let title = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !title.isEmpty, isFullGameFirstTeamMarketName(title) else { continue }
            if let periodKey = q.period?.key, periodKey != "full_game" { continue }
            guard (2...3).contains(q.options.count) else { continue }

            var legsByRole: [FirstTeamRole: FirstTeamLeg] = [:]
            var allMatched = true
            for o in q.options {
                guard let role = classifyFirstTeamRole(
                    outcomeLabel: o.label,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ), legsByRole[role] == nil else {
                    allMatched = false
                    break
                }
                let quoted = !finished && NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                    ? validOpenChance(o.published.quotedValue)
                    : nil
                let pin = NBALadderCard9483.pin(o)
                let settledReading: (probability: Double, at: String)? = {
                    guard let r = o.pregameReading, r.state == "available", r.basis == "pregame_pin",
                          let outId = r.outcomeId, o.contributorOutcomeIds == [outId],
                          let prob = validOpenChance(r.probability),
                          let at = r.observedAt, !at.isEmpty else { return nil }
                    return (prob, at)
                }()
                let pregameChance: Double? = {
                    switch currentPhase {
                    case .before: return quoted
                    case .during: return pin?.probability
                    case .after: return settledReading?.probability
                    }
                }()
                let pregameAt: String? = {
                    switch currentPhase {
                    case .before: return quoted != nil ? o.published.observedAt : nil
                    case .during: return pin?.at
                    case .after: return settledReading?.at
                    }
                }()
                let verdict: OutcomeVerdict? = finished
                    ? (o.result?.isWinner == true ? .won : o.result?.isWinner == false ? .lost : nil)
                    : nil

                let displayLabel: String = {
                    switch role {
                    case .home: return homeShort
                    case .away: return awayShort
                    case .noGoal: return "No goal"
                    }
                }()
                legsByRole[role] = FirstTeamLeg(
                    role: role,
                    label: displayLabel,
                    rawOutcomeLabel: o.label,
                    quotedChance: quoted,
                    pregameChance: pregameChance,
                    observedAt: o.published.observedAt,
                    pregameObservedAt: pregameAt,
                    result: verdict,
                    source: o.published.source
                )
            }

            if allMatched, legsByRole[.home] != nil, legsByRole[.away] != nil {
                let ordered = roleOrder.compactMap { legsByRole[$0] }
                let priced = ordered.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settled = ordered.filter { $0.result != nil }.count
                guard priced > 0 || settled > 0 else { continue }
                let distinctSources = Set(ordered.compactMap(\.source))
                candidates.append(
                    Candidate(
                        marketTitle: title,
                        source: distinctSources.count == 1 ? distinctSources.first : nil,
                        sourceCount: max(1, distinctSources.count),
                        legs: ordered,
                        score: ordered.count * 12 + priced * 10 + settled * 5 + 3
                    )
                )
            }
        }

        // 2. Check gameMarkets.other
        var byMarketKey: [String: (title: String, rows: [GameMarketOther])] = [:]
        var marketKeyOrder: [String] = []
        for row in otherMarkets {
            let mname = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !mname.isEmpty, isFullGameFirstTeamMarketName(mname) else { continue }
            let prefix = [row._marketId.map(String.init), row.source].compactMap { $0 }.first
            let key = "\(prefix ?? ""):\(mname)"
            if byMarketKey[key] == nil {
                marketKeyOrder.append(key)
                byMarketKey[key] = (mname, [row])
            } else {
                byMarketKey[key]?.rows.append(row)
            }
        }

        for key in marketKeyOrder {
            guard let group = byMarketKey[key], (2...3).contains(group.rows.count) else { continue }
            var legsByRole: [FirstTeamRole: FirstTeamLeg] = [:]
            var allMatched = true
            for row in group.rows {
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let role = classifyFirstTeamRole(
                    outcomeLabel: outLabel,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ), legsByRole[role] == nil else {
                    allMatched = false
                    break
                }
                let observedAt = row.observedAt
                let recent = NFLMilestoneCard9483.isRecent(observedAt, now: now)
                let quotedChance = !finished && recent ? validOpenChance(row.probability) : nil
                let pregameChance: Double? = currentPhase == .before
                    ? (recent ? validOpenChance(row.probability) : nil)
                    : validOpenChance(row.pregameMark)
                let verdict = OutcomeVerdict.verdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    marketResolved: finished
                )

                let displayLabel: String = {
                    switch role {
                    case .home: return homeShort
                    case .away: return awayShort
                    case .noGoal: return "No goal"
                    }
                }()
                legsByRole[role] = FirstTeamLeg(
                    role: role,
                    label: displayLabel,
                    rawOutcomeLabel: outLabel,
                    quotedChance: quotedChance,
                    pregameChance: pregameChance,
                    observedAt: observedAt,
                    pregameObservedAt: currentPhase == .before ? observedAt : nil,
                    result: verdict,
                    source: row.source
                )
            }

            if allMatched, legsByRole[.home] != nil, legsByRole[.away] != nil {
                let ordered = roleOrder.compactMap { legsByRole[$0] }
                let priced = ordered.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settled = ordered.filter { $0.result != nil }.count
                guard priced > 0 || settled > 0 else { continue }
                let distinctSources = Set(ordered.compactMap(\.source))
                candidates.append(
                    Candidate(
                        marketTitle: group.title,
                        source: distinctSources.count == 1 ? distinctSources.first : nil,
                        sourceCount: max(1, distinctSources.count),
                        legs: ordered,
                        score: ordered.count * 12 + priced * 10 + settled * 5
                    )
                )
            }
        }

        guard let best = candidates.max(by: { $0.score < $1.score }) else { return nil }
        return FirstTeamToScoreCard(
            phase: currentPhase,
            legs: best.legs,
            checkpoints: liveCheckpoints,
            marketTitle: best.marketTitle,
            source: best.source,
            sourceCount: best.sourceCount
        )
    }

    // MARK: - 13b (Part 2). Half-by-Half Breakdown ("1st Half" & "2nd Half")

    nonisolated enum HalfPeriod: String, CaseIterable, Equatable, Sendable {
        case firstHalf = "1H"
        case secondHalf = "2H"

        var title: String {
            self == .firstHalf ? "1st Half" : "2nd Half"
        }
    }

    nonisolated struct HalfLeg: Equatable, Identifiable, Sendable {
        var id: String { "soccer-half:\(period.rawValue):\(role.rawValue)" }
        let period: HalfPeriod
        let role: ThreeWayRole
        let label: String
        let rawOutcomeLabel: String
        let quotedChance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let pregameObservedAt: String?
        let result: OutcomeVerdict?
        let source: String?

        func current(at now: Date, phase: NBALadderCard9483.Phase) -> HalfLeg {
            guard phase != .after else { return self }
            let hasPrice = phase == .before ? (quotedChance != nil || pregameChance != nil) : (quotedChance != nil)
            guard hasPrice, !NFLMilestoneCard9483.isRecent(observedAt, now: now) else {
                return self
            }
            return HalfLeg(
                period: period,
                role: role,
                label: label,
                rawOutcomeLabel: rawOutcomeLabel,
                quotedChance: nil,
                pregameChance: phase == .before ? nil : pregameChance,
                observedAt: observedAt,
                pregameObservedAt: pregameObservedAt,
                result: result,
                source: source
            )
        }
    }

    nonisolated struct HalfSection: Equatable, Identifiable, Sendable {
        var id: String { "soccer-half:\(period.rawValue)" }
        let period: HalfPeriod
        let legs: [HalfLeg]
        let awayGoals: Int?
        let homeGoals: Int?
        let marketTitle: String
        let source: String?
        let sourceCount: Int

        func current(at now: Date, phase: NBALadderCard9483.Phase) -> HalfSection {
            guard phase != .after else { return self }
            let aged = legs.map { $0.current(at: now, phase: phase) }
            guard aged != legs else { return self }
            return HalfSection(
                period: period,
                legs: aged,
                awayGoals: awayGoals,
                homeGoals: homeGoals,
                marketTitle: marketTitle,
                source: source,
                sourceCount: sourceCount
            )
        }
    }

    nonisolated struct HalvesCard: Equatable, Identifiable, Sendable {
        var id: String { "soccer:halves" }
        let phase: NBALadderCard9483.Phase
        let sections: [HalfSection]
        let awayShort: String
        let homeShort: String

        var title: String {
            phase == .after ? "Half-by-half results" : "Half-by-half expectations"
        }

        var reason: String {
            "1st Half and 2nd Half Home, Draw, and Away outcomes"
        }

        func current(at now: Date) -> HalvesCard {
            guard phase != .after else { return self }
            let aged = sections.map { $0.current(at: now, phase: phase) }
            guard aged != sections else { return self }
            return HalvesCard(
                phase: phase,
                sections: aged,
                awayShort: awayShort,
                homeShort: homeShort
            )
        }
    }

    static func classifyHalfPeriod(marketName: String, periodKey: String? = nil) -> HalfPeriod? {
        let lower = marketName.lowercased()
        // Disqualify non-3-way half markets (totals, spreads, BTTS, corners, cards, team to score)
        if lower.range(
            of: #"\b(?:corner|corners|card|cards|shot|shots|goalscorer|first\s+team\s+to\s+score|last\s+team\s+to\s+score|both\s+teams?\s+to\s+score|btts|exact\s+score|correct\s+score|over\/under|o\/u|total|spread|handicap|draw\s+no\s+bet|double\s+chance)\b"#,
            options: .regularExpression
        ) != nil {
            return nil
        }
        if let key = periodKey?.lowercased() {
            if ["1h", "first_half", "half_1", "1st_half"].contains(key) { return .firstHalf }
            if ["2h", "second_half", "half_2", "2nd_half"].contains(key) { return .secondHalf }
        }
        if lower.range(of: #"\b(?:1st\s+half|first\s+half|half[-\s]?time\s+result|1h\s+result|1h\s+winner|1h\s+3[-\s]?way)\b"#, options: .regularExpression) != nil {
            return .firstHalf
        }
        if lower.range(of: #"\b(?:2nd\s+half|second\s+half|2h\s+result|2h\s+winner|2h\s+3[-\s]?way)\b"#, options: .regularExpression) != nil {
            return .secondHalf
        }
        return nil
    }

    private static func halfScores(from boxScoreData: EventBoxScoreData?) -> [HalfPeriod: (away: Int, home: Int)] {
        guard let homePeriods = boxScoreData?.homePeriodScores,
              let awayPeriods = boxScoreData?.awayPeriodScores else { return [:] }
        var map: [HalfPeriod: (away: Int, home: Int)] = [:]
        if homePeriods.count >= 1, awayPeriods.count >= 1,
           let a = awayPeriods[0], let h = homePeriods[0] {
            map[.firstHalf] = (a, h)
        }
        if homePeriods.count >= 2, awayPeriods.count >= 2,
           let a = awayPeriods[1], let h = homePeriods[1] {
            map[.secondHalf] = (a, h)
        }
        return map
    }

    @MainActor
    static func buildHalvesCard(
        matrix: EventQuestionMatrix?,
        otherMarkets: [GameMarketOther],
        boxScoreData: EventBoxScoreData? = nil,
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        now: Date = Date()
    ) -> HalvesCard? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after
        let reportedHalves = halfScores(from: boxScoreData)

        struct SectionCandidate {
            let section: HalfSection
            let score: Int
        }

        var bestByPeriod: [HalfPeriod: SectionCandidate] = [:]
        let roleOrder: [ThreeWayRole] = [.home, .draw, .away]

        // 1. Check game_question_matrix (10238.v1)
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let title = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !title.isEmpty,
                  let period = classifyHalfPeriod(marketName: title, periodKey: q.period?.key),
                  q.options.count == 3 else { continue }

            var legsByRole: [ThreeWayRole: HalfLeg] = [:]
            for o in q.options {
                guard let role = classifyThreeWayRole(
                    outcomeLabel: o.label,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ), legsByRole[role] == nil else { break }

                let quoted = !finished && NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                    ? validOpenChance(o.published.quotedValue)
                    : nil
                let pin = NBALadderCard9483.pin(o)
                let settledReading: (probability: Double, at: String)? = {
                    guard let r = o.pregameReading, r.state == "available", r.basis == "pregame_pin",
                          let outId = r.outcomeId, o.contributorOutcomeIds == [outId],
                          let prob = validOpenChance(r.probability),
                          let at = r.observedAt, !at.isEmpty else { return nil }
                    return (prob, at)
                }()
                let pregameChance: Double? = {
                    switch currentPhase {
                    case .before: return quoted
                    case .during: return pin?.probability
                    case .after: return settledReading?.probability
                    }
                }()
                let pregameAt: String? = {
                    switch currentPhase {
                    case .before: return quoted != nil ? o.published.observedAt : nil
                    case .during: return pin?.at
                    case .after: return settledReading?.at
                    }
                }()
                let verdict: OutcomeVerdict? = finished
                    ? (o.result?.isWinner == true ? .won : o.result?.isWinner == false ? .lost : nil)
                    : nil

                legsByRole[role] = HalfLeg(
                    period: period,
                    role: role,
                    label: role == .home ? homeShort : role == .away ? awayShort : "Draw",
                    rawOutcomeLabel: o.label,
                    quotedChance: quoted,
                    pregameChance: pregameChance,
                    observedAt: o.published.observedAt,
                    pregameObservedAt: pregameAt,
                    result: verdict,
                    source: o.published.source
                )
            }

            if legsByRole.count == 3 {
                let ordered = roleOrder.compactMap { legsByRole[$0] }
                let priced = ordered.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settled = ordered.filter { $0.result != nil }.count
                guard priced > 0 || settled > 0 else { continue }
                let distinctSources = Set(ordered.compactMap(\.source))
                let goals = reportedHalves[period]
                let section = HalfSection(
                    period: period,
                    legs: ordered,
                    awayGoals: goals?.away,
                    homeGoals: goals?.home,
                    marketTitle: title,
                    source: distinctSources.count == 1 ? distinctSources.first : nil,
                    sourceCount: max(1, distinctSources.count)
                )
                let score = priced * 10 + settled * 5 + 3
                if score > (bestByPeriod[period]?.score ?? -1) {
                    bestByPeriod[period] = SectionCandidate(section: section, score: score)
                }
            }
        }

        // 2. Check gameMarkets.other
        var byMarketKey: [String: (title: String, period: HalfPeriod, rows: [GameMarketOther])] = [:]
        var marketKeyOrder: [String] = []
        for row in otherMarkets {
            let mname = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !mname.isEmpty, let period = classifyHalfPeriod(marketName: mname) else { continue }
            let prefix = [row._marketId.map(String.init), row.source].compactMap { $0 }.first
            let key = "\(prefix ?? ""):\(mname)"
            if byMarketKey[key] == nil {
                marketKeyOrder.append(key)
                byMarketKey[key] = (mname, period, [row])
            } else {
                byMarketKey[key]?.rows.append(row)
            }
        }

        for key in marketKeyOrder {
            guard let group = byMarketKey[key], group.rows.count == 3 else { continue }
            let period = group.period
            var legsByRole: [ThreeWayRole: HalfLeg] = [:]
            for row in group.rows {
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let role = classifyThreeWayRole(
                    outcomeLabel: outLabel,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ), legsByRole[role] == nil else { break }

                let observedAt = row.observedAt
                let recent = NFLMilestoneCard9483.isRecent(observedAt, now: now)
                let quotedChance = !finished && recent ? validOpenChance(row.probability) : nil
                let pregameChance: Double? = currentPhase == .before
                    ? (recent ? validOpenChance(row.probability) : nil)
                    : validOpenChance(row.pregameMark)
                let verdict = OutcomeVerdict.verdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    marketResolved: finished
                )

                legsByRole[role] = HalfLeg(
                    period: period,
                    role: role,
                    label: role == .home ? homeShort : role == .away ? awayShort : "Draw",
                    rawOutcomeLabel: outLabel,
                    quotedChance: quotedChance,
                    pregameChance: pregameChance,
                    observedAt: observedAt,
                    pregameObservedAt: currentPhase == .before ? observedAt : nil,
                    result: verdict,
                    source: row.source
                )
            }

            if legsByRole.count == 3 {
                let ordered = roleOrder.compactMap { legsByRole[$0] }
                let priced = ordered.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settled = ordered.filter { $0.result != nil }.count
                guard priced > 0 || settled > 0 else { continue }
                let distinctSources = Set(ordered.compactMap(\.source))
                let goals = reportedHalves[period]
                let section = HalfSection(
                    period: period,
                    legs: ordered,
                    awayGoals: goals?.away,
                    homeGoals: goals?.home,
                    marketTitle: group.title,
                    source: distinctSources.count == 1 ? distinctSources.first : nil,
                    sourceCount: max(1, distinctSources.count)
                )
                let score = priced * 10 + settled * 5
                if score > (bestByPeriod[period]?.score ?? -1) {
                    bestByPeriod[period] = SectionCandidate(section: section, score: score)
                }
            }
        }

        let orderedSections = HalfPeriod.allCases.compactMap { bestByPeriod[$0]?.section }
        guard !orderedSections.isEmpty else { return nil }
        return HalvesCard(
            phase: currentPhase,
            sections: orderedSections,
            awayShort: awayShort,
            homeShort: homeShort
        )
    }

    // MARK: - Mark Keys & Details Sheet Models for 13a–b

    static func bothTeamsMarkKey(for card: BothTeamsToScoreCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        if card.phase == .during && card.legs.contains(where: { $0.quotedChance != nil }) {
            items.append(Item(glyph: .filledCircle, label: "Recorded"))
        }
        if card.legs.contains(where: { $0.result != nil }) {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func firstTeamMarkKey(for card: FirstTeamToScoreCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        if card.phase == .during && card.legs.contains(where: { $0.quotedChance != nil }) {
            items.append(Item(glyph: .filledCircle, label: "Recorded"))
        }
        if card.legs.contains(where: { $0.result != nil }) {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func halvesMarkKey(for card: HalvesCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        let allLegs = card.sections.flatMap(\.legs)
        if card.phase == .during && allLegs.contains(where: { $0.quotedChance != nil }) {
            items.append(Item(glyph: .filledCircle, label: "Recorded"))
        }
        if allLegs.contains(where: { $0.result != nil }) {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func detailsModel(
        for leg: BTTSLeg,
        card: BothTeamsToScoreCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = card.phase == .before ? nil : leg.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let res = leg.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
        } else if let quoted = leg.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregame = leg.pregameChance {
            primaryLabel = "Pregame baseline"
            primaryValue = formatProbability(pregame)
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(leg.observedAt ?? leg.pregameObservedAt)
        let resolvedSource = leg.source ?? card.source
        let sourceLabel: String?
        if resolvedSource == nil && card.sourceCount > 1 {
            sourceLabel = "\(card.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(source: resolvedSource, sourceCount: nil)
        }
        return EventAtlasDetailsSheetModel11666(
            id: leg.id,
            outcomeTitle: "Both teams to score · \(leg.label)",
            marketTitle: card.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: card.scoring?.summaryText,
            statusLabel: card.phase == .after ? "Final goals" : "Goals so far",
            sourceLabel: sourceLabel
        )
    }

    static func detailsModel(
        for leg: FirstTeamLeg,
        card: FirstTeamToScoreCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = card.phase == .before ? nil : leg.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let res = leg.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
        } else if let quoted = leg.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregame = leg.pregameChance {
            primaryLabel = "Pregame baseline"
            primaryValue = formatProbability(pregame)
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(leg.observedAt ?? leg.pregameObservedAt)
        let resolvedSource = leg.source ?? card.source
        let sourceLabel: String?
        if resolvedSource == nil && card.sourceCount > 1 {
            sourceLabel = "\(card.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(source: resolvedSource, sourceCount: nil)
        }
        return EventAtlasDetailsSheetModel11666(
            id: leg.id,
            outcomeTitle: "First team to score · \(leg.label)",
            marketTitle: card.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }

    static func detailsModel(
        for leg: HalfLeg,
        section: HalfSection,
        card: HalvesCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = card.phase == .before ? nil : leg.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let res = leg.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
        } else if let quoted = leg.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregame = leg.pregameChance {
            primaryLabel = "Pregame baseline"
            primaryValue = formatProbability(pregame)
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(leg.observedAt ?? leg.pregameObservedAt)
        let resolvedSource = leg.source ?? section.source
        let sourceLabel: String?
        if resolvedSource == nil && section.sourceCount > 1 {
            sourceLabel = "\(section.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(source: resolvedSource, sourceCount: nil)
        }
        let halfScoreSummary: String? = {
            guard let a = section.awayGoals, let h = section.homeGoals else { return nil }
            return "\(section.period.title) goals: \(card.homeShort) \(h) – \(a) \(card.awayShort)"
        }()
        return EventAtlasDetailsSheetModel11666(
            id: leg.id,
            outcomeTitle: "\(section.period.title) · \(leg.label)",
            marketTitle: section.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: halfScoreSummary,
            statusLabel: "\(section.period.title) goals",
            sourceLabel: sourceLabel
        )
    }
}

// MARK: - SwiftUI Card Views for 13a–b Soccer Story Cards

struct EventAtlasSoccerBothTeamsCardView11666: View {
    let card: EventAtlasSoccerCards11666.BothTeamsToScoreCard
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("BOTH TEAMS TO SCORE")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(card.title)
                .font(.headline.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(card.reason)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasSoccerCards11666.bothTeamsMarkKey(for: card)
            )
            if let scoring = card.scoring {
                Text(scoring.summaryText)
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("atlas-soccer-btts-scoring-summary-11666")
            }
            VStack(alignment: .leading, spacing: 8) {
                ForEach(card.legs) { leg in
                    legRow(leg)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-soccer-btts-card-11666")
    }

    @ViewBuilder
    private func legReadings(_ leg: EventAtlasSoccerCards11666.BTTSLeg) -> some View {
        let displayChance = card.phase == .after ? leg.pregameChance : (leg.quotedChance ?? leg.pregameChance)
        if card.phase == .during, let pregame = leg.pregameChance, leg.quotedChance != nil {
            Text("○ \(formatProbability(pregame))")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: true, vertical: false)
        }
        if let chance = displayChance {
            let prefix = card.phase == .after ? "○ " : (leg.quotedChance != nil && card.phase == .during ? "● " : "○ ")
            Text("\(prefix)\(formatProbability(chance))")
                .font(.subheadline.weight(.bold).monospacedDigit())
                .foregroundStyle(leg.role == .yes ? Color.primary : Color.secondary)
                .fixedSize(horizontal: true, vertical: false)
        } else {
            Text(EventAtlasStates11666.noRecentPrice)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private func legVerdict(_ leg: EventAtlasSoccerCards11666.BTTSLeg) -> some View {
        if card.phase == .after {
            if let res = leg.result {
                Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(res == .won ? Color.green : Color.secondary)
                    .fixedSize(horizontal: true, vertical: false)
            } else {
                Text(EventAtlasStates11666.pending)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: true, vertical: false)
            }
        }
    }

    private func infoButton(_ leg: EventAtlasSoccerCards11666.BTTSLeg) -> some View {
        Button {
            state.detailsRowID = leg.id
        } label: {
            Image(systemName: "info.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(leg.label) details")
        .accessibilityIdentifier("atlas-soccer-btts-info-\(leg.role.rawValue)-11666")
    }

    @ViewBuilder
    private func legRow(_ leg: EventAtlasSoccerCards11666.BTTSLeg) -> some View {
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(leg.label)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    infoButton(leg)
                }
                HStack(spacing: 8) {
                    legReadings(leg)
                    Spacer(minLength: 4)
                    legVerdict(leg)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        } else {
            HStack(spacing: 8) {
                Text(leg.label)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: 44, alignment: .leading)
                legReadings(leg)
                Spacer(minLength: 4)
                legVerdict(leg)
                infoButton(leg)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        }
    }
}

struct EventAtlasSoccerFirstTeamCardView11666: View {
    let card: EventAtlasSoccerCards11666.FirstTeamToScoreCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("OPENING GOAL")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(card.title)
                .font(.headline.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(card.reason)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasSoccerCards11666.firstTeamMarkKey(for: card)
            )
            VStack(alignment: .leading, spacing: 8) {
                ForEach(card.legs) { leg in
                    legRow(leg)
                }
            }
            if !card.checkpoints.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Observed scores · Observation times, not exact goal times")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    ForEach(card.checkpoints) { cp in
                        HStack {
                            Text(cp.scoreText)
                                .font(.caption2.weight(.semibold).monospacedDigit())
                            Spacer(minLength: 8)
                            Text(cp.observedAtText)
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(.secondary)
                        }
                    }
                }
                .padding(8)
                .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
                .accessibilityIdentifier("atlas-soccer-first-team-checkpoints-11666")
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-soccer-first-team-card-11666")
    }

    @ViewBuilder
    private func legReadings(_ leg: EventAtlasSoccerCards11666.FirstTeamLeg, color: Color) -> some View {
        let displayChance = card.phase == .after ? leg.pregameChance : (leg.quotedChance ?? leg.pregameChance)
        if card.phase == .during, let pregame = leg.pregameChance, leg.quotedChance != nil {
            Text("○ \(formatProbability(pregame))")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: true, vertical: false)
        }
        if let chance = displayChance {
            let prefix = card.phase == .after ? "○ " : (leg.quotedChance != nil && card.phase == .during ? "● " : "○ ")
            Text("\(prefix)\(formatProbability(chance))")
                .font(.subheadline.weight(.bold).monospacedDigit())
                .foregroundStyle(color)
                .fixedSize(horizontal: true, vertical: false)
        } else {
            Text(EventAtlasStates11666.noRecentPrice)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private func legVerdict(_ leg: EventAtlasSoccerCards11666.FirstTeamLeg) -> some View {
        if card.phase == .after {
            if let res = leg.result {
                Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(res == .won ? Color.green : Color.secondary)
                    .fixedSize(horizontal: true, vertical: false)
            } else {
                Text(EventAtlasStates11666.pending)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: true, vertical: false)
            }
        }
    }

    private func infoButton(_ leg: EventAtlasSoccerCards11666.FirstTeamLeg) -> some View {
        Button {
            state.detailsRowID = leg.id
        } label: {
            Image(systemName: "info.circle")
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 28, height: 28)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(leg.label) details")
        .accessibilityIdentifier("atlas-soccer-first-team-info-\(leg.role.rawValue)-11666")
    }

    @ViewBuilder
    private func legRow(_ leg: EventAtlasSoccerCards11666.FirstTeamLeg) -> some View {
        let color: Color = leg.role == .home ? homeColor : leg.role == .away ? awayColor : .secondary
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    Text(leg.label)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    infoButton(leg)
                }
                HStack(spacing: 8) {
                    legReadings(leg, color: color)
                    Spacer(minLength: 4)
                    legVerdict(leg)
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        } else {
            HStack(spacing: 8) {
                Text(leg.label)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: 68, alignment: .leading)
                legReadings(leg, color: color)
                Spacer(minLength: 4)
                legVerdict(leg)
                infoButton(leg)
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        }
    }
}

struct EventAtlasSoccerHalvesCardView11666: View {
    let card: EventAtlasSoccerCards11666.HalvesCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("HALF-BY-HALF")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(.secondary)
            Text(card.title)
                .font(.headline.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(card.reason)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasSoccerCards11666.halvesMarkKey(for: card)
            )
            VStack(alignment: .leading, spacing: 10) {
                ForEach(card.sections) { section in
                    sectionView(section)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-soccer-halves-card-11666")
    }

    private func sectionView(_ section: EventAtlasSoccerCards11666.HalfSection) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(section.period.title)
                    .font(.subheadline.weight(.bold))
                    .fixedSize(horizontal: false, vertical: true)
                Spacer()
                if let a = section.awayGoals, let h = section.homeGoals {
                    Text("\(card.homeShort) \(h) – \(a) \(card.awayShort)")
                        .font(.caption.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            ForEach(section.legs) { leg in
                legRow(leg)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 10))
        .accessibilityIdentifier("atlas-soccer-half-section-\(section.period.rawValue)-11666")
    }

    @ViewBuilder
    private func legReadings(_ leg: EventAtlasSoccerCards11666.HalfLeg, color: Color) -> some View {
        let displayChance = card.phase == .after ? leg.pregameChance : (leg.quotedChance ?? leg.pregameChance)
        if card.phase == .during, let pregame = leg.pregameChance, leg.quotedChance != nil {
            Text("○ \(formatProbability(pregame))")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: true, vertical: false)
        }
        if let chance = displayChance {
            let prefix = card.phase == .after ? "○ " : (leg.quotedChance != nil && card.phase == .during ? "● " : "○ ")
            Text("\(prefix)\(formatProbability(chance))")
                .font(.caption.weight(.bold).monospacedDigit())
                .foregroundStyle(color)
                .fixedSize(horizontal: true, vertical: false)
        } else {
            Text(EventAtlasStates11666.noRecentPrice)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private func legVerdict(_ leg: EventAtlasSoccerCards11666.HalfLeg) -> some View {
        if card.phase == .after {
            if let res = leg.result {
                Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(res == .won ? Color.green : Color.secondary)
                    .fixedSize(horizontal: true, vertical: false)
            } else {
                Text(EventAtlasStates11666.pending)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: true, vertical: false)
            }
        }
    }

    private func infoButton(_ leg: EventAtlasSoccerCards11666.HalfLeg) -> some View {
        Button {
            state.detailsRowID = leg.id
        } label: {
            Image(systemName: "info.circle")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .frame(width: 24, height: 24)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("\(leg.period.title) \(leg.label) details")
        .accessibilityIdentifier("atlas-soccer-half-info-\(leg.period.rawValue)-\(leg.role.rawValue)-11666")
    }

    @ViewBuilder
    private func legRow(_ leg: EventAtlasSoccerCards11666.HalfLeg) -> some View {
        let color: Color = leg.role == .home ? homeColor : leg.role == .away ? awayColor : .secondary
        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 6) {
                    Text(leg.label)
                        .font(.caption.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    infoButton(leg)
                }
                HStack(spacing: 6) {
                    legReadings(leg, color: color)
                    Spacer(minLength: 4)
                    legVerdict(leg)
                }
            }
        } else {
            HStack(spacing: 6) {
                Text(leg.label)
                    .font(.caption.weight(.semibold))
                    .fixedSize(horizontal: true, vertical: false)
                    .frame(minWidth: 64, alignment: .leading)
                legReadings(leg, color: color)
                Spacer(minLength: 4)
                legVerdict(leg)
                infoButton(leg)
            }
        }
    }
}
