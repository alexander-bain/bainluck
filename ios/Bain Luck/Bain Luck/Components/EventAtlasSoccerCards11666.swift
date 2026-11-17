import SwiftUI

/// #11666 Step E6c — Native Event-page Atlas Soccer story cards (`soccer_*`),
/// mirroring web `#11974` Step E6c (`frontend/lib/soccerEventCards.ts`), gated behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`:
/// 1. Three-way match outcome (`ThreeWayCard`, `id: "soccer:threeWay"`):
///    Home / Draw / Away on a shared 0–100% probability scale (`"A draw is a real third outcome"`
///    before full-time; `"Full-time three-way result"` after). Refuses any market that does not
///    explicitly supply all three legs — never invents a draw from `1 - home - away`. Under
///    Ruling 49-A, complete one-winner fields scale both ways when the raw total is ≥ 90%,
///    partial fields never scale, and unblended multi-source probabilities are withheld.
/// 2. Exact-score landscape (`ExactScoreCard`, `id: "soccer:exactScore"`):
///    2D discrete score grid (`homeGoals` across × `awayGoals` down) built from supplied
///    Exact Score / Correct Score outcomes without inventing missing cells as 0% or normalizing.
/// 3. Goal expectations (`NBALadderCard9483`, `family: .total`, `unit: "goals"`):
///    full-game goal thresholds from `game_question_matrix` / `gameMarkets.totals`.
nonisolated enum EventAtlasSoccerCards11666 {

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        guard atlasEnabled, let sportKey else { return false }
        return sportKey.hasPrefix("soccer_")
    }

    private static func openChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    /// Ruling 49-A: one-winner fields scale both ways only when all three legs are present
    /// and the raw total is >= 90%. Partial fields or fields totaling < 90% withhold all leg numbers.
    /// Decide 80-A (`#12274`, `#12449`): on a fallback `GameMarketOther` row, the market's
    /// resolution status is not served beside the row, so `OutcomeVerdict` is asked as
    /// for an open market (`marketResolved: false`): only an authoritative win becomes
    /// `.won`, and a row grade never mints `.lost`.
    nonisolated static func otherRowVerdict(
        _ row: GameMarketOther,
        finished: Bool
    ) -> OutcomeVerdict? {
        guard finished else { return nil }
        return OutcomeVerdict.verdict(
            isWinner: row.isWinner,
            resolutionSource: row.resolutionSource,
            marketResolved: false
        ) == .won ? .won : nil
    }

    static func scaleThreeWayField(
        home: Double?,
        draw: Double?,
        away: Double?
    ) -> (home: Double?, draw: Double?, away: Double?, rawSum: Double?) {
        guard let h = openChance(home),
              let d = openChance(draw),
              let a = openChance(away) else {
            return (nil, nil, nil, nil)
        }
        let sum = h + d + a
        guard sum >= 0.90 else {
            return (nil, nil, nil, sum)
        }
        return (h / sum, d / sum, a / sum, sum)
    }

    // MARK: - 1. Three-Way Match Outcome ("A draw is a real third outcome")

    nonisolated enum ThreeWayRole: String, Equatable, Sendable {
        case home
        case draw
        case away
    }

    nonisolated struct ThreeWayLeg: Equatable, Identifiable, Sendable {
        var id: String { "soccer-3way:\(role.rawValue)" }
        let role: ThreeWayRole
        let label: String
        let rawOutcomeLabel: String
        let quotedChance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let pregameObservedAt: String?
        let result: OutcomeVerdict?
        let source: String?
    }

    nonisolated struct ThreeWayCard: Equatable, Identifiable, Sendable {
        var id: String { "soccer:threeWay" }
        let phase: NBALadderCard9483.Phase
        let legs: [ThreeWayLeg]
        let marketTitle: String
        let source: String?
        let sourceCount: Int
        let quotedSum: Double?

        var title: String {
            if phase == .after {
                if legs.first(where: { $0.role == .draw })?.result == .won {
                    return "Finished level — a draw was the third outcome"
                }
                return "Full-time three-way result"
            }
            return "A draw is a real third outcome"
        }

        var reason: String {
            if phase == .after {
                return "90-minute Home, Draw, and Away outcomes graded independently"
            }
            return "Home, draw and away are three real outcomes"
        }

        func current(at now: Date) -> ThreeWayCard {
            guard phase != .after else { return self }
            let anyQuoteStale = legs.contains { leg in
                leg.quotedChance != nil && !NFLMilestoneCard9483.isRecent(leg.observedAt, now: now)
            }
            guard anyQuoteStale else { return self }
            let aged = legs.map { leg in
                ThreeWayLeg(
                    role: leg.role,
                    label: leg.label,
                    rawOutcomeLabel: leg.rawOutcomeLabel,
                    quotedChance: nil,
                    pregameChance: phase == .before ? nil : leg.pregameChance,
                    observedAt: leg.observedAt,
                    pregameObservedAt: leg.pregameObservedAt,
                    result: leg.result,
                    source: leg.source
                )
            }
            return ThreeWayCard(
                phase: phase,
                legs: aged,
                marketTitle: marketTitle,
                source: source,
                sourceCount: sourceCount,
                quotedSum: phase == .before ? nil : quotedSum
            )
        }
    }

    // MARK: - Soccer Club Side Resolution

    private static let clubAffixPattern: NSRegularExpression? = try? NSRegularExpression(
        pattern: #"\b(?:fc|afc|cf|sc|ac|sv|bv|vfb|vfl|rb|tsg|fsv|bsc|ud|cd|rcd|rc|fk|sk|nk|if|bk|ik|\d{2,4})\b"#,
        options: [.caseInsensitive]
    )

    static func stripSoccerClubAffixes(_ value: String) -> String {
        let range = NSRange(value.startIndex..<value.endIndex, in: value)
        let stripped = clubAffixPattern?.stringByReplacingMatches(in: value, options: [], range: range, withTemplate: " ") ?? value
        return stripped
            .replacingOccurrences(of: ".", with: " ")
            .replacingOccurrences(of: ",", with: " ")
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    private static func tokenContains(_ text: String, target: String) -> Bool {
        let a = text.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        let b = target.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
        guard !a.isEmpty, !b.isEmpty else { return false }
        if a == b { return true }
        let aTokens = Set(a.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 })
        let bTokens = Set(b.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { $0.count >= 3 })
        guard !aTokens.isEmpty, !bTokens.isEmpty else { return false }
        return aTokens.isSubset(of: bTokens) || bTokens.isSubset(of: aTokens)
    }

    static func resolveSoccerSide(
        candidate: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> ThreeWayRole? {
        let c = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !c.isEmpty else { return nil }
        let lower = c.lowercased()
        if lower == homeTeam.lowercased() || lower == homeShort.lowercased() { return .home }
        if lower == awayTeam.lowercased() || lower == awayShort.lowercased() { return .away }

        let rawHome = tokenContains(c, target: homeTeam) || tokenContains(c, target: homeShort)
        let rawAway = tokenContains(c, target: awayTeam) || tokenContains(c, target: awayShort)
        if rawHome && !rawAway { return .home }
        if rawAway && !rawHome { return .away }
        if rawHome && rawAway { return nil }

        let strippedC = stripSoccerClubAffixes(c)
        let strippedHome = stripSoccerClubAffixes(homeTeam)
        let strippedHomeShort = stripSoccerClubAffixes(homeShort)
        let strippedAway = stripSoccerClubAffixes(awayTeam)
        let strippedAwayShort = stripSoccerClubAffixes(awayShort)
        guard !strippedC.isEmpty else { return nil }

        let sHome = tokenContains(strippedC, target: strippedHome) || tokenContains(strippedC, target: strippedHomeShort)
        let sAway = tokenContains(strippedC, target: strippedAway) || tokenContains(strippedC, target: strippedAwayShort)
        if sHome && !sAway { return .home }
        if sAway && !sHome { return .away }
        return nil
    }

    static func classifyThreeWayRole(
        outcomeLabel: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> ThreeWayRole? {
        let trimmed = outcomeLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.range(of: #"^(?:draw|tie)(?:\b|\s*\()"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .draw
        }
        let cleaned = trimmed.replacingOccurrences(
            of: #"\s+wins$"#,
            with: "",
            options: [.regularExpression, .caseInsensitive]
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        return resolveSoccerSide(
            candidate: cleaned,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort
        )
    }

    private static func isDisqualifiedThreeWayMarketName(_ name: String) -> Bool {
        let lower = name.lowercased()
        if lower.range(of: #"\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|half[-\s]?time)\b"#, options: .regularExpression) != nil {
            return true
        }
        return lower.range(
            of: #"\b(?:corner|corners|card|cards|shot|shots|goalscorer|first\s+team\s+to\s+score|last\s+team\s+to\s+score|both\s+teams\s+to\s+score|btts|exact\s+score|correct\s+score|advance|qualify|tiebreaker|over\/under|o\/u|spread|handicap)\b"#,
            options: .regularExpression
        ) != nil
    }

    @MainActor
    static func buildThreeWayCard(
        matrix: EventQuestionMatrix?,
        otherMarkets: [GameMarketOther],
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        now: Date = Date()
    ) -> ThreeWayCard? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after

        struct Candidate {
            let marketTitle: String
            let source: String?
            let legsByRole: [ThreeWayRole: ThreeWayLeg]
            let score: Int
        }

        var candidates: [Candidate] = []

        // 1. Check game_question_matrix questions
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let title = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard !title.isEmpty, !isDisqualifiedThreeWayMarketName(title) else { continue }
            if let periodKey = q.period?.key, periodKey != "full_game" { continue }
            guard q.options.count == 3 else { continue }

            var legsByRole: [ThreeWayRole: ThreeWayLeg] = [:]
            for o in q.options {
                guard let role = classifyThreeWayRole(
                    outcomeLabel: o.label,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ), legsByRole[role] == nil else { break }

                let quoted = !finished && NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                    ? openChance(o.published.quotedValue)
                    : nil
                let pin = NBALadderCard9483.pin(o)
                let settledReading: (probability: Double, at: String)? = {
                    guard let r = o.pregameReading, r.state == "available", r.basis == "pregame_pin",
                          let outId = r.outcomeId, o.contributorOutcomeIds == [outId],
                          let prob = r.probability, prob.isFinite, prob > 0, prob < 1,
                          let at = r.observedAt, !at.isEmpty else { return nil }
                    return (prob, at)
                }()
                let pregameChance = finished ? settledReading?.probability : pin?.probability
                let pregameAt = finished ? settledReading?.at : pin?.at
                let verdict: OutcomeVerdict? = finished
                    ? (o.result?.isWinner == true ? .won : o.result?.isWinner == false ? .lost : nil)
                    : nil

                legsByRole[role] = ThreeWayLeg(
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
                let allLegs = [ThreeWayRole.home, .draw, .away].compactMap { legsByRole[$0] }
                let pricedCount = allLegs.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settledCount = allLegs.filter { $0.result != nil }.count
                let score = pricedCount * 10 + settledCount * 5 + (allLegs.first?.pregameChance != nil ? 3 : 0)
                candidates.append(
                    Candidate(
                        marketTitle: title,
                        source: allLegs.compactMap(\.source).first,
                        legsByRole: legsByRole,
                        score: score
                    )
                )
            }
        }

        // 2. Check gameMarkets.other grouped by marketId / source + marketName
        var byMarketKey: [String: (title: String, rows: [GameMarketOther])] = [:]
        var marketKeyOrder: [String] = []
        for row in otherMarkets {
            let mname = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !mname.isEmpty, !isDisqualifiedThreeWayMarketName(mname) else { continue }
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
            guard let group = byMarketKey[key], group.rows.count == 3 else { continue }
            var legsByRole: [ThreeWayRole: ThreeWayLeg] = [:]
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
                let quotedChance = !finished && recent ? openChance(row.probability) : nil
                let pregameChance: Double? = currentPhase == .before
                    ? (recent ? openChance(row.probability) : nil)
                    : openChance(row.pregameMark)
                let verdict = otherRowVerdict(row, finished: finished)

                legsByRole[role] = ThreeWayLeg(
                    role: role,
                    label: role == .home ? homeShort : role == .away ? awayShort : "Draw",
                    rawOutcomeLabel: outLabel,
                    quotedChance: quotedChance,
                    pregameChance: pregameChance,
                    observedAt: observedAt,
                    pregameObservedAt: nil,
                    result: verdict,
                    source: row.source
                )
            }

            if legsByRole.count == 3 {
                // Decide 80-A (#12449): a loss may print on the other legs of this 3-way
                // one-winner market only when the market's winner is venue-confirmed (.won).
                let hasConfirmedWinner = legsByRole.values.filter { $0.result == .won }.count == 1
                if hasConfirmedWinner {
                    for row in group.rows {
                        let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                        guard let role = classifyThreeWayRole(
                            outcomeLabel: outLabel,
                            homeTeam: homeTeam,
                            awayTeam: awayTeam,
                            homeShort: homeShort,
                            awayShort: awayShort
                        ), let existing = legsByRole[role], existing.result == nil,
                        row.isWinner == false,
                        OutcomeVerdict.isAuthoritative(row.resolutionSource) else { continue }
                        legsByRole[role] = ThreeWayLeg(
                            role: existing.role,
                            label: existing.label,
                            rawOutcomeLabel: existing.rawOutcomeLabel,
                            quotedChance: existing.quotedChance,
                            pregameChance: existing.pregameChance,
                            observedAt: existing.observedAt,
                            pregameObservedAt: existing.pregameObservedAt,
                            result: .lost,
                            source: existing.source
                        )
                    }
                }
                let allLegs = [ThreeWayRole.home, .draw, .away].compactMap { legsByRole[$0] }
                let pricedCount = allLegs.filter { $0.quotedChance != nil || $0.pregameChance != nil }.count
                let settledCount = allLegs.filter { $0.result != nil }.count
                candidates.append(
                    Candidate(
                        marketTitle: group.title,
                        source: allLegs.compactMap(\.source).first,
                        legsByRole: legsByRole,
                        score: pricedCount * 10 + settledCount * 5
                    )
                )
            }
        }

        guard !candidates.isEmpty else { return nil }
        candidates.sort { $0.score > $1.score }

        var seenSources = Set<String>()
        var deduped: [Candidate] = []
        for c in candidates {
            if let s = c.source {
                if seenSources.contains(s) { continue }
                seenSources.insert(s)
            }
            deduped.append(c)
        }

        let blended = deduped.first { $0.source == "blended" || $0.source == "blend" }
        let multiUnblended = blended == nil && deduped.count > 1
        guard let best = blended ?? deduped.first,
              let homeLeg = best.legsByRole[.home],
              let drawLeg = best.legsByRole[.draw],
              let awayLeg = best.legsByRole[.away] else { return nil }

        let sourceCount = blended != nil ? 1 : max(1, deduped.count)
        let rawLegs = [homeLeg, drawLeg, awayLeg]
        let scaledQuoted = scaleThreeWayField(
            home: homeLeg.quotedChance,
            draw: drawLeg.quotedChance,
            away: awayLeg.quotedChance
        )
        let scaledPregame = scaleThreeWayField(
            home: homeLeg.pregameChance,
            draw: drawLeg.pregameChance,
            away: awayLeg.pregameChance
        )

        func scaledChance(
            _ role: ThreeWayRole,
            from tuple: (home: Double?, draw: Double?, away: Double?, rawSum: Double?)
        ) -> Double? {
            switch role {
            case .home: return tuple.home
            case .draw: return tuple.draw
            case .away: return tuple.away
            }
        }

        let legs: [ThreeWayLeg] = multiUnblended
            ? rawLegs.map { leg in
                var verdicts = Set<OutcomeVerdict>()
                for c in deduped {
                    if let v = c.legsByRole[leg.role]?.result {
                        verdicts.insert(v)
                    }
                }
                let agreed: OutcomeVerdict? = (verdicts.contains(.won) && verdicts.contains(.lost))
                    ? nil
                    : verdicts.contains(.won) ? .won : verdicts.contains(.lost) ? .lost : nil
                return ThreeWayLeg(
                    role: leg.role,
                    label: leg.label,
                    rawOutcomeLabel: leg.rawOutcomeLabel,
                    quotedChance: nil,
                    pregameChance: nil,
                    observedAt: leg.observedAt,
                    pregameObservedAt: leg.pregameObservedAt,
                    result: agreed,
                    source: nil
                )
            }
            : rawLegs.map { leg in
                ThreeWayLeg(
                    role: leg.role,
                    label: leg.label,
                    rawOutcomeLabel: leg.rawOutcomeLabel,
                    quotedChance: scaledChance(leg.role, from: scaledQuoted),
                    pregameChance: scaledChance(leg.role, from: scaledPregame),
                    observedAt: leg.observedAt,
                    pregameObservedAt: leg.pregameObservedAt,
                    result: leg.result,
                    source: leg.source
                )
            }

        let anyCandidateSettled = deduped.contains { cand in
            [ThreeWayRole.home, .draw, .away].contains { cand.legsByRole[$0]?.result != nil }
        }
        let anyRawPrice = rawLegs.contains { $0.quotedChance != nil || $0.pregameChance != nil }
        let hasAnySignal = finished
            ? (legs.contains { $0.result != nil || $0.pregameChance != nil } || (multiUnblended && anyCandidateSettled))
            : anyRawPrice
        guard hasAnySignal else { return nil }

        let quotedSum: Double? = multiUnblended ? nil : (scaledQuoted.rawSum ?? scaledPregame.rawSum)

        return ThreeWayCard(
            phase: currentPhase,
            legs: legs,
            marketTitle: best.marketTitle,
            source: multiUnblended ? nil : best.source,
            sourceCount: sourceCount,
            quotedSum: quotedSum
        )
    }

    // MARK: - 2. Exact-Score Landscape ("The exact-score landscape")

    nonisolated enum ParsedExactScore: Equatable, Sendable {
        case score(homeGoals: Int, awayGoals: Int)
        case other
    }

    nonisolated struct ExactScoreCell: Equatable, Identifiable, Sendable {
        var id: String { "soccer-exact:\(key)" }
        let key: String
        let homeGoals: Int
        let awayGoals: Int
        let outcomeLabel: String
        var quotedChance: Double? = nil
        let chance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let result: OutcomeVerdict?
        let source: String?
        let marketTitle: String
    }

    nonisolated struct ExactScoreOtherCell: Equatable, Identifiable, Sendable {
        var id: String { "soccer-exact:other" }
        var key: String { "other" }
        let outcomeLabel: String
        var quotedChance: Double? = nil
        let chance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let result: OutcomeVerdict?
        let source: String?
        let marketTitle: String
    }

    nonisolated struct ExactScoreCard: Equatable, Identifiable, Sendable {
        var id: String { "soccer:exactScore" }
        let phase: NBALadderCard9483.Phase
        let homeTeam: String
        let awayTeam: String
        let homeShort: String
        let awayShort: String
        let maxGoals: Int
        let maxChance: Double
        let cells: [ExactScoreCell]
        let otherCell: ExactScoreOtherCell?
        let defaultSelectedKey: String
        let marketTitle: String
        let source: String?
        let sourceCount: Int

        var title: String { "The exact-score landscape" }

        func current(at now: Date) -> ExactScoreCard {
            guard phase != .after else { return self }
            let anyCellStale = cells.contains { cell in
                cell.quotedChance != nil
                    && !NFLMilestoneCard9483.isRecent(cell.observedAt, now: now)
            }
            let otherStale: Bool = {
                guard let other = otherCell else { return false }
                return other.quotedChance != nil
                    && !NFLMilestoneCard9483.isRecent(other.observedAt, now: now)
            }()
            guard anyCellStale || otherStale else { return self }

            let agedCells = cells.map { cell -> ExactScoreCell in
                let quoteStale = cell.quotedChance != nil
                    && !NFLMilestoneCard9483.isRecent(cell.observedAt, now: now)
                let nextQuoted = quoteStale ? nil : cell.quotedChance
                let nextPregame = (phase == .before && quoteStale) ? nil : cell.pregameChance
                let nextChance = nextQuoted ?? nextPregame
                return ExactScoreCell(
                    key: cell.key,
                    homeGoals: cell.homeGoals,
                    awayGoals: cell.awayGoals,
                    outcomeLabel: cell.outcomeLabel,
                    quotedChance: nextQuoted,
                    chance: nextChance,
                    pregameChance: nextPregame,
                    observedAt: cell.observedAt,
                    result: cell.result,
                    source: cell.source,
                    marketTitle: cell.marketTitle
                )
            }
            let agedOther: ExactScoreOtherCell? = otherCell.map { other in
                let quoteStale = other.quotedChance != nil
                    && !NFLMilestoneCard9483.isRecent(other.observedAt, now: now)
                let nextQuoted = quoteStale ? nil : other.quotedChance
                let nextPregame = (phase == .before && quoteStale) ? nil : other.pregameChance
                let nextChance = nextQuoted ?? nextPregame
                return ExactScoreOtherCell(
                    outcomeLabel: other.outcomeLabel,
                    quotedChance: nextQuoted,
                    chance: nextChance,
                    pregameChance: nextPregame,
                    observedAt: other.observedAt,
                    result: other.result,
                    source: other.source,
                    marketTitle: other.marketTitle
                )
            }
            let sortedCells = agedCells.sorted { a, b in
                let aChance = a.chance ?? -1.0
                let bChance = b.chance ?? -1.0
                if aChance != bChance { return aChance > bChance }
                if a.awayGoals != b.awayGoals { return a.awayGoals < b.awayGoals }
                return a.homeGoals < b.homeGoals
            }
            let nextMaxChance = sortedCells.reduce(0.05) { max($0, $1.chance ?? 0.0) }
            let highestCell = sortedCells.first(where: { $0.chance != nil })
            let nextDefaultKey = highestCell?.key
                ?? (agedOther?.chance != nil ? "other" : nil)
                ?? sortedCells.first?.key
                ?? defaultSelectedKey
            return ExactScoreCard(
                phase: phase,
                homeTeam: homeTeam,
                awayTeam: awayTeam,
                homeShort: homeShort,
                awayShort: awayShort,
                maxGoals: maxGoals,
                maxChance: nextMaxChance,
                cells: sortedCells,
                otherCell: agedOther,
                defaultSelectedKey: nextDefaultKey,
                marketTitle: marketTitle,
                source: source,
                sourceCount: sourceCount
            )
        }
    }

    static func parseExactScoreOutcome(
        outcomeLabel: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> ParsedExactScore? {
        let trimmed = outcomeLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return nil }
        if trimmed.range(of: #"^(?:any\s+other(?:\s+score)?|other)$"#, options: [.regularExpression, .caseInsensitive]) != nil {
            return .other
        }

        func regexCaptures(_ pattern: String, in text: String) -> [String]? {
            guard let rx = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
                  let m = rx.firstMatch(in: text, options: [], range: NSRange(text.startIndex..<text.endIndex, in: text))
            else { return nil }
            return (1..<m.numberOfRanges).compactMap { idx -> String? in
                guard let r = Range(m.range(at: idx), in: text) else { return nil }
                return String(text[r])
            }
        }

        // 1. "Draw 0-0" or "Tie 1 - 1"
        if let caps = regexCaptures(#"^(?:draw|tie)\s+(\d+)\s*[-–:]\s*(\d+)$"#, in: trimmed),
           caps.count == 2, let a = Int(caps[0]), let b = Int(caps[1]), a == b {
            return .score(homeGoals: a, awayGoals: b)
        }

        // 2. "<Team> wins 3-2"
        if let caps = regexCaptures(#"^(.+?)\s+wins\s+(\d+)\s*[-–:]\s*(\d+)$"#, in: trimmed),
           caps.count == 3, let g1 = Int(caps[1]), let g2 = Int(caps[2]),
           let side = resolveSoccerSide(candidate: caps[0], homeTeam: homeTeam, awayTeam: awayTeam, homeShort: homeShort, awayShort: awayShort) {
            return side == .home ? .score(homeGoals: g1, awayGoals: g2) : .score(homeGoals: g2, awayGoals: g1)
        }

        // 3. "<TeamA> 3 - 2 <TeamB>"
        if let caps = regexCaptures(#"^(.+?)\s+(\d+)\s*[-–:]\s*(\d+)\s+(.+)$"#, in: trimmed),
           caps.count == 4, let gLeft = Int(caps[1]), let gRight = Int(caps[2]),
           let leftSide = resolveSoccerSide(candidate: caps[0], homeTeam: homeTeam, awayTeam: awayTeam, homeShort: homeShort, awayShort: awayShort),
           let rightSide = resolveSoccerSide(candidate: caps[3], homeTeam: homeTeam, awayTeam: awayTeam, homeShort: homeShort, awayShort: awayShort) {
            if leftSide == .home && rightSide == .away {
                return .score(homeGoals: gLeft, awayGoals: gRight)
            }
            if leftSide == .away && rightSide == .home {
                return .score(homeGoals: gRight, awayGoals: gLeft)
            }
        }

        // 4. Bare "1 - 1" / "2-0"
        if let caps = regexCaptures(#"^(\d+)\s*[-–:]\s*(\d+)$"#, in: trimmed),
           caps.count == 2, let h = Int(caps[0]), let a = Int(caps[1]) {
            return .score(homeGoals: h, awayGoals: a)
        }

        return nil
    }

    private static func isExactScoreMarketTitle(_ title: String) -> Bool {
        let lower = title.lowercased()
        if lower.range(of: #"\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|half[-\s]?time)\b"#, options: .regularExpression) != nil {
            return false
        }
        return lower.range(of: #"\b(?:exact\s+score|correct\s+score)\b"#, options: .regularExpression) != nil
    }

    @MainActor
    static func buildExactScoreCard(
        matrix: EventQuestionMatrix?,
        otherMarkets: [GameMarketOther],
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        now: Date = Date()
    ) -> ExactScoreCard? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after

        struct CandidateGrid {
            let marketTitle: String
            let source: String?
            let cellsByKey: [String: ExactScoreCell]
            let otherCell: ExactScoreOtherCell?
            let score: Int
        }

        var candidates: [CandidateGrid] = []

        // 1. Check game_question_matrix questions (10238.v1)
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let title = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard isExactScoreMarketTitle(title) else { continue }
            if let periodKey = q.period?.key, periodKey != "full_game" { continue }
            var cellsByKey: [String: ExactScoreCell] = [:]
            var otherCell: ExactScoreOtherCell?

            for o in q.options {
                guard let parsed = parseExactScoreOutcome(
                    outcomeLabel: o.label,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ) else { continue }

                let quoted = !finished && NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                    ? openChance(o.published.quotedValue)
                    : nil
                let pin = NBALadderCard9483.pin(o)
                let settledReading: (probability: Double, at: String)? = {
                    guard let r = o.pregameReading, r.state == "available", r.basis == "pregame_pin",
                          let outId = r.outcomeId, o.contributorOutcomeIds == [outId],
                          let prob = r.probability, prob.isFinite, prob > 0, prob < 1,
                          let at = r.observedAt, !at.isEmpty else { return nil }
                    return (prob, at)
                }()
                let pregame = finished ? settledReading?.probability : pin?.probability
                let pregameAt = finished ? settledReading?.at : pin?.at
                let chance = finished ? pregame : (quoted ?? pregame)
                let verdict: OutcomeVerdict? = finished
                    ? (o.result?.isWinner == true ? .won : o.result?.isWinner == false ? .lost : nil)
                    : nil

                if case .other = parsed {
                    guard otherCell == nil else { continue }
                    otherCell = ExactScoreOtherCell(
                        outcomeLabel: o.label,
                        quotedChance: quoted,
                        chance: chance,
                        pregameChance: pregame,
                        observedAt: o.published.observedAt ?? pregameAt,
                        result: verdict,
                        source: o.published.source,
                        marketTitle: title
                    )
                    continue
                }

                guard case .score(let hGoals, let aGoals) = parsed,
                      hGoals <= 6, aGoals <= 6 else { continue }
                let cellKey = "\(hGoals)-\(aGoals)"
                guard cellsByKey[cellKey] == nil else { continue }

                cellsByKey[cellKey] = ExactScoreCell(
                    key: cellKey,
                    homeGoals: hGoals,
                    awayGoals: aGoals,
                    outcomeLabel: o.label,
                    quotedChance: quoted,
                    chance: chance,
                    pregameChance: pregame,
                    observedAt: o.published.observedAt ?? pregameAt,
                    result: verdict,
                    source: o.published.source,
                    marketTitle: title
                )
            }

            if cellsByKey.count >= 4 {
                let cells = cellsByKey.values.sorted { a, b in
                    if a.awayGoals != b.awayGoals { return a.awayGoals < b.awayGoals }
                    return a.homeGoals < b.homeGoals
                }
                let pricedCount = cells.filter { $0.chance != nil }.count + (otherCell?.chance != nil ? 1 : 0)
                let wonCount = cells.filter { $0.result == .won }.count + (otherCell?.result == .won ? 1 : 0)
                let resolvedSource = cells.compactMap(\.source).first ?? otherCell?.source
                candidates.append(
                    CandidateGrid(
                        marketTitle: title,
                        source: resolvedSource,
                        cellsByKey: cellsByKey,
                        otherCell: otherCell,
                        score: pricedCount * 10 + wonCount * 20 + cells.count
                    )
                )
            }
        }

        // 2. Also check gameMarkets.other grouped by marketId / source + marketName
        var byMarketKey: [String: (title: String, rows: [GameMarketOther])] = [:]
        var marketKeyOrder: [String] = []
        for row in otherMarkets {
            let mname = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard isExactScoreMarketTitle(mname) else { continue }
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
            guard let group = byMarketKey[key] else { continue }
            var cellsByKey: [String: ExactScoreCell] = [:]
            var otherCell: ExactScoreOtherCell?

            for row in group.rows {
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let parsed = parseExactScoreOutcome(
                    outcomeLabel: outLabel,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ) else { continue }

                let observedAt = row.observedAt
                let recent = NFLMilestoneCard9483.isRecent(observedAt, now: now)
                let quoted = !finished && recent ? openChance(row.probability) : nil
                let pregame: Double? = currentPhase == .before
                    ? (recent ? openChance(row.probability) : nil)
                    : openChance(row.pregameMark)
                let chance = finished ? pregame : (quoted ?? pregame)
                let verdict = otherRowVerdict(row, finished: finished)

                if case .other = parsed {
                    guard otherCell == nil else { continue }
                    otherCell = ExactScoreOtherCell(
                        outcomeLabel: outLabel,
                        quotedChance: quoted,
                        chance: chance,
                        pregameChance: pregame,
                        observedAt: observedAt,
                        result: verdict,
                        source: row.source,
                        marketTitle: group.title
                    )
                    continue
                }

                guard case .score(let hGoals, let aGoals) = parsed,
                      hGoals <= 6, aGoals <= 6 else { continue }

                let cellKey = "\(hGoals)-\(aGoals)"
                guard cellsByKey[cellKey] == nil else { continue }

                cellsByKey[cellKey] = ExactScoreCell(
                    key: cellKey,
                    homeGoals: hGoals,
                    awayGoals: aGoals,
                    outcomeLabel: outLabel,
                    quotedChance: quoted,
                    chance: chance,
                    pregameChance: pregame,
                    observedAt: observedAt,
                    result: verdict,
                    source: row.source,
                    marketTitle: group.title
                )
            }

            if cellsByKey.count >= 4 {
                let cells = cellsByKey.values.sorted { a, b in
                    if a.awayGoals != b.awayGoals { return a.awayGoals < b.awayGoals }
                    return a.homeGoals < b.homeGoals
                }
                let pricedCount = cells.filter { $0.chance != nil }.count + (otherCell?.chance != nil ? 1 : 0)
                let wonCount = cells.filter { $0.result == .won }.count + (otherCell?.result == .won ? 1 : 0)
                let resolvedSource = cells.compactMap(\.source).first ?? otherCell?.source
                candidates.append(
                    CandidateGrid(
                        marketTitle: group.title,
                        source: resolvedSource,
                        cellsByKey: cellsByKey,
                        otherCell: otherCell,
                        score: pricedCount * 10 + wonCount * 20 + cells.count
                    )
                )
            }
        }

        guard !candidates.isEmpty else { return nil }
        candidates.sort { $0.score > $1.score }

        var seenSources = Set<String>()
        var deduped: [CandidateGrid] = []
        for c in candidates {
            if let s = c.source {
                if seenSources.contains(s) { continue }
                seenSources.insert(s)
            }
            deduped.append(c)
        }

        let blended = deduped.first { $0.source == "blended" || $0.source == "blend" }
        let multiUnblended = blended == nil && deduped.count > 1
        guard let best = blended ?? deduped.first else { return nil }
        let sourceCount = blended != nil ? 1 : max(1, deduped.count)

        let rawCells = best.cellsByKey.values.sorted { a, b in
            if a.awayGoals != b.awayGoals { return a.awayGoals < b.awayGoals }
            return a.homeGoals < b.homeGoals
        }
        let unsortedCells: [ExactScoreCell] = multiUnblended
            ? rawCells.map { c in
                var verdicts = Set<OutcomeVerdict>()
                for cand in deduped {
                    if let v = cand.cellsByKey[c.key]?.result {
                        verdicts.insert(v)
                    }
                }
                let agreed: OutcomeVerdict? = (verdicts.contains(.won) && verdicts.contains(.lost))
                    ? nil
                    : verdicts.contains(.won) ? .won : verdicts.contains(.lost) ? .lost : nil
                return ExactScoreCell(
                    key: c.key,
                    homeGoals: c.homeGoals,
                    awayGoals: c.awayGoals,
                    outcomeLabel: c.outcomeLabel,
                    chance: nil,
                    pregameChance: nil,
                    observedAt: c.observedAt,
                    result: agreed,
                    source: nil,
                    marketTitle: c.marketTitle
                )
            }
            : rawCells

        let cells = unsortedCells.sorted { a, b in
            let aWon = finished && a.result == .won ? 1 : 0
            let bWon = finished && b.result == .won ? 1 : 0
            if aWon != bWon { return aWon > bWon }
            let aChance = a.chance ?? -1.0
            let bChance = b.chance ?? -1.0
            if aChance != bChance { return aChance > bChance }
            if a.awayGoals != b.awayGoals { return a.awayGoals < b.awayGoals }
            return a.homeGoals < b.homeGoals
        }

        let anyCandidateSettled = deduped.contains { cand in
            cand.cellsByKey.values.contains { $0.result != nil } || cand.otherCell?.result != nil
        }
        let resolvedOtherCell: ExactScoreOtherCell? = {
            guard let rawOther = best.otherCell else { return nil }
            if !multiUnblended { return rawOther }
            var verdicts = Set<OutcomeVerdict>()
            for cand in deduped {
                if let v = cand.otherCell?.result {
                    verdicts.insert(v)
                }
            }
            let agreed: OutcomeVerdict? = (verdicts.contains(.won) && verdicts.contains(.lost))
                ? nil
                : verdicts.contains(.won) ? .won : verdicts.contains(.lost) ? .lost : nil
            return ExactScoreOtherCell(
                outcomeLabel: rawOther.outcomeLabel,
                chance: nil,
                pregameChance: nil,
                observedAt: rawOther.observedAt,
                result: agreed,
                source: nil,
                marketTitle: rawOther.marketTitle
            )
        }()

        guard cells.contains(where: { $0.chance != nil || $0.result != nil })
            || resolvedOtherCell?.chance != nil
            || resolvedOtherCell?.result != nil
            || (finished && multiUnblended && anyCandidateSettled) else { return nil }

        let maxCoord = cells.reduce(3) { max($0, max($1.homeGoals, $1.awayGoals)) }
        let maxGoals = min(6, max(3, maxCoord))
        let maxChance = cells.reduce(0.05) { max($0, $1.chance ?? 0.0) }
        let winnerCell = finished ? cells.first(where: { $0.result == .won }) : nil
        let otherWon = finished && resolvedOtherCell?.result == .won
        let highestCell = cells.first(where: { $0.chance != nil })
        let defaultSelectedKey = winnerCell?.key
            ?? (otherWon ? "other" : nil)
            ?? highestCell?.key
            ?? (resolvedOtherCell?.chance != nil ? "other" : nil)
            ?? cells[0].key

        return ExactScoreCard(
            phase: currentPhase,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            maxGoals: maxGoals,
            maxChance: maxChance,
            cells: cells,
            otherCell: resolvedOtherCell,
            defaultSelectedKey: defaultSelectedKey,
            marketTitle: best.marketTitle,
            source: multiUnblended ? nil : best.source,
            sourceCount: sourceCount
        )
    }

    // MARK: - 3. Goal Expectations Ladder (`unit: "goals"`, `startWord: "kickoff"`)

    @MainActor
    static func buildGoalTotalCard(_ input: NBALadderCard9483.Input) -> NBALadderCard9483? {
        guard var card = EventAtlasNhlCards11666.buildGoalTotalsCard(input) else { return nil }
        card.unit = "goals"
        card.startWord = "kickoff"
        return card
    }

    // MARK: - Complete Soccer Deck in Fixed Slot Order

    @MainActor
    static func cards(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled(),
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        homeScore: Int?,
        awayScore: Int?,
        gameMarkets: GameMarketsResponse?,
        boxScoreData: EventBoxScoreData? = nil,
        scoreHistory: [ScoreHistoryPoint]? = nil,
        now: Date = Date()
    ) -> [NFLEventCard9483] {
        guard applies(sportKey: sportKey, atlasEnabled: atlasEnabled),
              let gm = gameMarkets else { return [] }

        let others = gm.other ?? []
        let threeWay = buildThreeWayCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            now: now
        )
        let bothTeams = buildBothTeamsToScoreCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            status: status,
            commenceTime: commenceTime,
            homeShort: homeShort,
            awayShort: awayShort,
            homeScore: homeScore,
            awayScore: awayScore,
            now: now
        )
        let firstTeam = buildFirstTeamToScoreCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            scoreHistory: scoreHistory,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            now: now
        )
        let halves = buildHalvesCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            boxScoreData: boxScoreData,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            now: now
        )
        let exactScore = buildExactScoreCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            now: now
        )
        let ladderInput = NBALadderCard9483.Input(
            matrix: gm.gameQuestionMatrix,
            status: status,
            commenceTime: commenceTime,
            homeScore: homeScore,
            awayScore: awayScore,
            pregameProjection: nil,
            homeShort: homeShort,
            awayShort: awayShort,
            now: now
        )
        let total = buildGoalTotalCard(ladderInput)

        var deck: [NFLEventCard9483] = []
        if let threeWay { deck.append(.soccerThreeWay(threeWay)) }
        if let bothTeams { deck.append(.soccerBothTeams(bothTeams)) }
        if let firstTeam { deck.append(.soccerFirstTeam(firstTeam)) }
        if let halves { deck.append(.soccerHalves(halves)) }
        if let exactScore { deck.append(.soccerExactScore(exactScore)) }
        if let total { deck.append(.ladder(total)) }
        return deck
    }

    // MARK: - Mark-Grammar Keys & Shared Details Sheet Models

    static func threeWayMarkKey(for card: ThreeWayCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
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

    static func exactScoreMarkKey(for card: ExactScoreCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        if card.phase == .during && (card.cells.contains(where: { $0.quotedChance != nil }) || card.otherCell?.quotedChance != nil) {
            items.append(Item(glyph: .filledCircle, label: "Recorded"))
        }
        if card.cells.contains(where: { $0.result != nil }) || card.otherCell?.result != nil {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func detailsModel(
        for leg: ThreeWayLeg,
        card: ThreeWayCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = leg.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let res = leg.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.resultNotConfirmed
        } else if let quoted = leg.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregameText {
            primaryLabel = "Pregame baseline"
            primaryValue = pregameText
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
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(
                source: resolvedSource,
                sourceCount: nil
            )
        }
        let rawSumText = card.quotedSum.map { "Raw 3-way sum \(Int(($0 * 100.0).rounded()))%" }
        return EventAtlasDetailsSheetModel11666(
            id: leg.id,
            outcomeTitle: leg.rawOutcomeLabel,
            marketTitle: card.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: rawSumText,
            statusLabel: "Raw quotes",
            sourceLabel: sourceLabel
        )
    }

    static func detailsModel(
        for cell: ExactScoreCell,
        card: ExactScoreCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = cell.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let res = cell.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.resultNotConfirmed
        } else if let quoted = cell.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregameText {
            primaryLabel = "Pregame baseline"
            primaryValue = pregameText
        } else if let chance = cell.chance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(chance)
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(cell.observedAt)
        let resolvedSource = cell.source ?? card.source
        let sourceLabel: String?
        if resolvedSource == nil && card.sourceCount > 1 {
            sourceLabel = "\(card.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(
                source: resolvedSource,
                sourceCount: nil
            )
        }
        return EventAtlasDetailsSheetModel11666(
            id: cell.id,
            outcomeTitle: "\(card.homeShort) \(cell.homeGoals) – \(cell.awayGoals) \(card.awayShort)",
            marketTitle: cell.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }

    static func detailsModel(
        for otherCell: ExactScoreOtherCell,
        card: ExactScoreCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = otherCell.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let res = otherCell.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.resultNotConfirmed
        } else if let quoted = otherCell.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregameText {
            primaryLabel = "Pregame baseline"
            primaryValue = pregameText
        } else if let chance = otherCell.chance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(chance)
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(otherCell.observedAt)
        let resolvedSource = otherCell.source ?? card.source
        let sourceLabel: String?
        if resolvedSource == nil && card.sourceCount > 1 {
            sourceLabel = "\(card.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(
                source: resolvedSource,
                sourceCount: nil
            )
        }
        return EventAtlasDetailsSheetModel11666(
            id: otherCell.id,
            outcomeTitle: "Any other score",
            marketTitle: otherCell.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }
    nonisolated struct ThreeWayBarReading: Equatable, Sendable {
        let away: Double
        let draw: Double
        let home: Double
        let notch: Double?
    }

    /// #12616 (187-A) — resolves the game-page three-way soccer bar inputs when
    /// all three legs carry a display chance, so `ProbabilityBar` draws
    /// `[Away | Draw | Home]` with the draw in the middle.
    static func threeWayBarReading(for card: ThreeWayCard) -> ThreeWayBarReading? {
        func displayChance(_ role: ThreeWayRole) -> Double? {
            guard let leg = card.legs.first(where: { $0.role == role }) else { return nil }
            return card.phase == .after ? leg.pregameChance : (leg.quotedChance ?? leg.pregameChance)
        }
        guard let away = displayChance(.away),
              let draw = displayChance(.draw),
              let home = displayChance(.home),
              away > 0, draw > 0, home > 0 else { return nil }

        let notch: Double?
        if card.phase != .before,
           let preAway = card.legs.first(where: { $0.role == .away })?.pregameChance,
           let preDraw = card.legs.first(where: { $0.role == .draw })?.pregameChance,
           let preHome = card.legs.first(where: { $0.role == .home })?.pregameChance {
            let sum = preAway + preDraw + preHome
            let share = sum > 0 ? (preAway / sum) : 0
            notch = (share > 0 && share < 1) ? share : nil
        } else {
            notch = nil
        }
        return ThreeWayBarReading(away: away, draw: draw, home: home, notch: notch)
    }
}

// MARK: - SwiftUI Card Views for Soccer Story Cards

struct EventAtlasSoccerThreeWayCardView11666: View {
    let card: EventAtlasSoccerCards11666.ThreeWayCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("90-MINUTE THREE-WAY")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DS.textSecondaryReadable)
            Text(card.title)
                .font(.headline.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(card.reason)
                .font(.caption)
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: false, vertical: true)
            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasSoccerCards11666.threeWayMarkKey(for: card)
            )
            if let bar = EventAtlasSoccerCards11666.threeWayBarReading(for: card) {
                ProbabilityBar(
                    awayProb: bar.away,
                    homeProb: bar.home,
                    drawProb: bar.draw,
                    awayColor: card.phase == .after ? awayColor.opacity(0.65) : awayColor,
                    homeColor: card.phase == .after ? homeColor.opacity(0.65) : homeColor,
                    height: 6,
                    notchProb: bar.notch
                )
            }
            VStack(alignment: .leading, spacing: 8) {
                ForEach(card.legs) { leg in
                    legRow(leg)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-soccer-three-way-card-11666")
    }

    private func legRow(_ leg: EventAtlasSoccerCards11666.ThreeWayLeg) -> some View {
        let color: Color = leg.role == .home ? homeColor : leg.role == .away ? awayColor : .secondary
        let displayChance = card.phase == .after ? leg.pregameChance : (leg.quotedChance ?? leg.pregameChance)
        let rowBody = HStack(spacing: 8) {
            Text(leg.label)
                .font(.subheadline.weight(.semibold))
                .frame(width: 72, alignment: .leading)
            if let chance = displayChance {
                Text(formatProbability(chance))
                    .font(.subheadline.weight(.bold).monospacedDigit())
                    .foregroundStyle(color)
            } else {
                Text(EventAtlasStates11666.noRecentPrice)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            Spacer(minLength: 4)
            if card.phase == .after {
                if let res = leg.result {
                    Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(res == .won ? DS.greenReadable : DS.textSecondaryReadable)
                } else {
                    Text(EventAtlasStates11666.resultNotConfirmed)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
        }
        return Group {
            if expanded {
                Button {
                    state.detailsRowID = leg.id
                } label: {
                    rowBody.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else {
                rowBody
            }
        }
    }
}

struct EventAtlasSoccerExactScoreCardView11666: View {
    let card: EventAtlasSoccerCards11666.ExactScoreCard
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    private var visibleCells: [EventAtlasSoccerCards11666.ExactScoreCell] {
        expanded ? card.cells : Array(card.cells.prefix(12))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("EXACT SCORE")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DS.textSecondaryReadable)
            Text(card.title)
                .font(.headline.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasSoccerCards11666.exactScoreMarkKey(for: card)
            )
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 74), spacing: 6)], spacing: 6) {
                ForEach(visibleCells) { cell in
                    cellView(cell)
                }
            }
            if let otherCell = card.otherCell {
                otherCellView(otherCell)
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-soccer-exact-score-card-11666")
    }

    private func otherCellView(_ otherCell: EventAtlasSoccerCards11666.ExactScoreOtherCell) -> some View {
        let rowBody = HStack(spacing: 8) {
            Text("Any other score")
                .font(.caption.weight(.semibold))
            Spacer(minLength: 4)
            if let chance = otherCell.chance {
                Text(formatProbability(chance))
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            if card.phase == .after {
                if let res = otherCell.result {
                    Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(res == .won ? DS.greenReadable : DS.textSecondaryReadable)
                } else {
                    Text(EventAtlasStates11666.resultNotConfirmed)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
        }
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))
        .accessibilityIdentifier("atlas-soccer-exact-score-other-cell-11666")

        return Group {
            if expanded {
                Button {
                    state.detailsRowID = otherCell.id
                } label: {
                    rowBody.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else {
                rowBody
            }
        }
    }

    private func cellView(_ cell: EventAtlasSoccerCards11666.ExactScoreCell) -> some View {
        let box = VStack(spacing: 2) {
            Text("\(cell.homeGoals)–\(cell.awayGoals)")
                .font(.caption.weight(.bold).monospacedDigit())
            if let chance = cell.chance {
                Text(formatProbability(chance))
                    .font(.caption2.monospacedDigit())
                    .foregroundStyle(DS.textSecondaryReadable)
            }
            if card.phase == .after {
                if let res = cell.result {
                    Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(res == .won ? DS.greenReadable : DS.textSecondaryReadable)
                } else {
                    Text(EventAtlasStates11666.resultNotConfirmed)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }
        }
        .padding(.vertical, 6)
        .frame(maxWidth: .infinity)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))

        return Group {
            if expanded {
                Button {
                    state.detailsRowID = cell.id
                } label: {
                    box.contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else {
                box
            }
        }
    }
}
