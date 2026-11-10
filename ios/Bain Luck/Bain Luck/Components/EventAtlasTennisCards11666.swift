import SwiftUI

/// #11666 Step E6d — Native Event-page Atlas Tennis story cards (`tennis_*`),
/// mirroring web `#11974` Step E6d (`frontend/lib/tennisEventCards.ts`), gated
/// behind `ReleaseSurfaces.isEventPageAtlasEnabled()`:
/// 1. Set-by-set path (`SetsCard`, `id: "tennis:sets"`): `"The match, set by set"`
///    (finished) or `"Set-by-set path"` (before/during play), reading `Set N Winner`
///    questions in numeric set order (`1...5`) without inventing unquoted sets.
/// 2. Exact match score in sets (`ExactScoreCard`, `id: "tennis:exactScore"`):
///    `"<Winner> in <two/three/four/five> sets"` (finished with a winning outcome)
///    or `"Exact match score in sets"` (before/during play), preserving supplied
///    set-score outcomes (`2-0`, `2-1`, `3-0`, `3-1`, `3-2`) with their recorded
///    quotes or settlement grades.
/// 3. Total games ladder (`NBALadderCard9483`, `id: "total"`, `family: .total`,
///    `unit: "games"`, `startWord: "first serve"`): full-game total games lines
///    from `game_question_matrix` (`10238.v1`) or `gameMarkets.totals`, with
///    `actual: nil` and `forecast: nil` always enforced (`COMPONENT-CONTRACT.md` §7:
///    "Missing actual/projection stays absent; tennis sets cannot supply games actual").
nonisolated enum EventAtlasTennisCards11666 {

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        guard atlasEnabled, let sportKey else { return false }
        return sportKey.hasPrefix("tennis_")
    }

    private static let validSetScores: Set<String> = [
        "2-0", "2-1", "3-0", "3-1", "3-2"
    ]

    private static func openChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    private static func isServerBlendedSource(_ source: String?) -> Bool {
        guard let s = source?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() else {
            return false
        }
        return s == "blended" || s == "blend"
    }

    static func normalizeSourceKey(_ source: String?) -> String {
        source?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? ""
    }

    static func dedupeCandidatesBySource<T>(
        _ candidates: [T],
        getSource: (T) -> String?
    ) -> [T] {
        var seenNamedSources = Set<String>()
        var deduped: [T] = []
        for c in candidates {
            let src = normalizeSourceKey(getSource(c))
            if !src.isEmpty {
                if seenNamedSources.contains(src) { continue }
                seenNamedSources.insert(src)
            }
            deduped.append(c)
        }
        return deduped
    }

    // MARK: - Player Name Normalization & 4-Tier Side Matching

    static func tennisPlayerShortName(_ fullName: String) -> String {
        let cleaned = fullName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cleaned.isEmpty else { return "" }
        return TeamShortName.short(cleaned, sportKey: "tennis_atp")
    }

    static func normalizePlayerPlain(_ value: String) -> String {
        let folded = value.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .lowercased()
        return folded
            .components(separatedBy: .whitespacesAndNewlines)
            .filter { !$0.isEmpty }
            .joined(separator: " ")
    }

    static func normalizePlayerTokens(_ value: String) -> [String] {
        let folded = value.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
            .lowercased()
        return folded
            .components(separatedBy: CharacterSet.alphanumerics.inverted)
            .filter { $0.count >= 2 }
    }

    private static func containsWholeWordPhrase(_ haystack: String, phrase: String) -> Bool {
        guard !haystack.isEmpty, !phrase.isEmpty, phrase.count >= 3 else { return false }
        return " \(haystack) ".contains(" \(phrase) ")
    }

    static func tennisNameMatchesSide(
        candidate: String,
        playerName: String,
        shortName: String
    ) -> Bool {
        let candNorm = normalizePlayerPlain(candidate)
        let fullNorm = normalizePlayerPlain(playerName)
        guard !candNorm.isEmpty, !fullNorm.isEmpty else { return false }
        if candNorm == fullNorm { return true }
        if containsWholeWordPhrase(candNorm, phrase: fullNorm)
            || containsWholeWordPhrase(fullNorm, phrase: candNorm) {
            return true
        }

        let candTokens = normalizePlayerTokens(candidate)
        let playerTokens = normalizePlayerTokens(playerName)
        let shortTokens = normalizePlayerTokens(shortName)
        if let surname = playerTokens.last, surname.count >= 3, candTokens.contains(surname) {
            return true
        }
        if !shortTokens.isEmpty && shortTokens.allSatisfy({ candTokens.contains($0) }) {
            return true
        }
        return false
    }

    static func matchTennisPlayerSide(
        candidate: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> PlayerPropsTeam.Side? {
        let candNorm = normalizePlayerPlain(candidate)
        let homeNorm = normalizePlayerPlain(homeTeam)
        let awayNorm = normalizePlayerPlain(awayTeam)
        let homeShortNorm = normalizePlayerPlain(homeShort)
        let awayShortNorm = normalizePlayerPlain(awayShort)
        guard !candNorm.isEmpty else { return nil }

        // 1. Exact full-name match
        let exactHome = !homeNorm.isEmpty && candNorm == homeNorm
        let exactAway = !awayNorm.isEmpty && candNorm == awayNorm
        if exactHome != exactAway { return exactHome ? .home : .away }
        if exactHome && exactAway { return nil }

        // 2. Exact short-name match
        let shortHome = !homeShortNorm.isEmpty && candNorm == homeShortNorm
        let shortAway = !awayShortNorm.isEmpty && candNorm == awayShortNorm
        if shortHome != shortAway { return shortHome ? .home : .away }
        if shortHome && shortAway { return nil }

        // 3. Word-bounded full-name phrase match
        let subHome = containsWholeWordPhrase(candNorm, phrase: homeNorm)
            || containsWholeWordPhrase(homeNorm, phrase: candNorm)
        let subAway = containsWholeWordPhrase(candNorm, phrase: awayNorm)
            || containsWholeWordPhrase(awayNorm, phrase: candNorm)
        if subHome != subAway { return subHome ? .home : .away }
        if subHome && subAway { return nil }

        // 4. Token / surname match
        let tokHome = tennisNameMatchesSide(candidate: candidate, playerName: homeTeam, shortName: homeShort)
        let tokAway = tennisNameMatchesSide(candidate: candidate, playerName: awayTeam, shortName: awayShort)
        if tokHome != tokAway { return tokHome ? .home : .away }
        return nil
    }

    static func numberToWord(_ n: Int) -> String {
        switch n {
        case 0: return "zero"
        case 1: return "one"
        case 2: return "two"
        case 3: return "three"
        case 4: return "four"
        case 5: return "five"
        default: return "\(n)"
        }
    }

    private static func capitalizeWord(_ word: String) -> String {
        guard let first = word.first else { return word }
        return String(first).uppercased() + word.dropFirst()
    }

    // MARK: - 1. Set-by-Set Path ("The match, set by set" / "Set-by-set path")

    nonisolated struct SetPlayerOutcome: Equatable, Identifiable, Sendable {
        let id: String
        let setNumber: Int
        let playerName: String
        let shortName: String
        let side: PlayerPropsTeam.Side
        let quotedChance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let pregameObservedAt: String?
        let result: OutcomeVerdict?
        var hasResultConflict: Bool = false
        let source: String?
        let sourceCount: Int
        let marketTitle: String
    }

    nonisolated struct SetStepRow: Equatable, Identifiable, Sendable {
        var id: String { "tennis-set:\(setNumber)" }
        let setNumber: Int
        let label: String
        let marketTitle: String
        let home: SetPlayerOutcome
        let away: SetPlayerOutcome
        let winnerSide: PlayerPropsTeam.Side?
        let winnerName: String?
    }

    nonisolated struct SetsCard: Equatable, Identifiable, Sendable {
        var id: String { "tennis:sets" }
        let phase: NBALadderCard9483.Phase
        let homePlayer: String
        let awayPlayer: String
        let homeShort: String
        let awayShort: String
        let sets: [SetStepRow]

        var title: String {
            phase == .after ? "The match, set by set" : "Set-by-set path"
        }

        var reason: String {
            if phase == .after {
                let anyGraded = sets.contains {
                    $0.home.result != nil || $0.away.result != nil
                        || $0.home.hasResultConflict || $0.away.hasResultConflict
                }
                return anyGraded
                    ? "Each set winner graded independently, alongside its pregame chance"
                    : "Pregame set winner chances in numeric set order"
            }
            return "Set winner chances in numeric set order"
        }

        func current(at now: Date) -> SetsCard {
            guard phase != .after else { return self }
            var changed = false
            func ageLeg(_ leg: SetPlayerOutcome) -> SetPlayerOutcome {
                guard leg.quotedChance != nil || (phase == .before && leg.pregameChance != nil),
                      !NFLMilestoneCard9483.isRecent(leg.observedAt, now: now) else {
                    return leg
                }
                changed = true
                return SetPlayerOutcome(
                    id: leg.id,
                    setNumber: leg.setNumber,
                    playerName: leg.playerName,
                    shortName: leg.shortName,
                    side: leg.side,
                    quotedChance: nil,
                    pregameChance: phase == .before ? nil : leg.pregameChance,
                    observedAt: leg.observedAt,
                    pregameObservedAt: leg.pregameObservedAt,
                    result: leg.result,
                    hasResultConflict: leg.hasResultConflict,
                    source: leg.source,
                    sourceCount: leg.sourceCount,
                    marketTitle: leg.marketTitle
                )
            }
            let agedSets = sets.map { row in
                SetStepRow(
                    setNumber: row.setNumber,
                    label: row.label,
                    marketTitle: row.marketTitle,
                    home: ageLeg(row.home),
                    away: ageLeg(row.away),
                    winnerSide: row.winnerSide,
                    winnerName: row.winnerName
                )
            }
            guard changed else { return self }
            return SetsCard(
                phase: phase,
                homePlayer: homePlayer,
                awayPlayer: awayPlayer,
                homeShort: homeShort,
                awayShort: awayShort,
                sets: agedSets
            )
        }
    }

    static func parseSetWinnerNumber(_ marketName: String) -> Int? {
        let patterns = [
            #"\bSet\s+([1-5])\s+Winner\b"#,
            #"\b([1-5])(?:st|nd|rd|th)\s+Set\s+Winner\b"#
        ]
        for pattern in patterns {
            guard let rx = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
                  let match = rx.firstMatch(
                      in: marketName,
                      options: [],
                      range: NSRange(marketName.startIndex..<marketName.endIndex, in: marketName)
                  ),
                  match.numberOfRanges > 1,
                  let r = Range(match.range(at: 1), in: marketName),
                  let n = Int(marketName[r]),
                  (1...5).contains(n) else { continue }
            return n
        }
        return nil
    }

    private static func matrixOptionVerdict(
        _ option: QuestionMatrixOption,
        finished: Bool
    ) -> (result: OutcomeVerdict?, conflict: Bool) {
        guard finished else { return (nil, false) }
        let evidence = option.sourceEvidence ?? []
        if evidence.count > 1 {
            var sawWon = false
            var sawLost = false
            for ev in evidence {
                let v = OutcomeVerdict.verdict(
                    isWinner: ev.isWinner,
                    resolutionSource: ev.resolutionSource,
                    marketResolved: false
                )
                if v == .won {
                    sawWon = true
                } else if ev.isWinner == false && ev.resolutionSource == "api_settlement" {
                    sawLost = true
                }
            }
            if sawWon && sawLost { return (nil, true) }
        }
        let state = option.result?.state
        let evidenceKind = option.result?.evidenceKind
        if evidenceKind == "ungradeable_result" || state == "disputed" || state == "pending" {
            return (nil, true)
        }
        if state == "won" || option.result?.isWinner == true { return (.won, false) }
        if state == "lost" || option.result?.isWinner == false { return (.lost, false) }
        return (nil, false)
    }

    /// Decide 80-A (`#12274`): on a fallback `GameMarketOther` row, the market's
    /// resolution status is not served beside the row, so `OutcomeVerdict` is
    /// asked as for an open market (`marketResolved: false`): only an
    /// authoritative win becomes `.won`, and a row grade never mints `.lost`.
    private static func otherRowVerdict(
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

    private static func combineCandidateVerdicts(
        _ candidates: [(result: OutcomeVerdict?, conflict: Bool)],
        finished: Bool
    ) -> (result: OutcomeVerdict?, conflict: Bool) {
        let hasConflict = candidates.contains { $0.conflict }
        let hasWon = candidates.contains { $0.result == .won }
        let hasLost = candidates.contains { $0.result == .lost }
        if hasConflict || (hasWon && hasLost) {
            return (nil, true)
        }
        if hasWon { return (.won, false) }
        if hasLost { return (.lost, false) }
        if finished && candidates.count > 1 {
            return (nil, true)
        }
        return (nil, false)
    }

    private static func settledSingleContributorReading(
        _ option: QuestionMatrixOption
    ) -> (probability: Double, at: String)? {
        guard let r = option.pregameReading,
              r.state == "available",
              r.basis == "pregame_pin",
              let outId = r.outcomeId,
              option.contributorOutcomeIds == [outId],
              let prob = r.probability, prob.isFinite, prob > 0, prob < 1,
              let at = r.observedAt, !at.isEmpty else {
            return nil
        }
        return (prob, at)
    }

    private static func resolveSetLegCandidates(
        _ candidates: [SetPlayerOutcome],
        finished: Bool
    ) -> SetPlayerOutcome? {
        guard !candidates.isEmpty else { return nil }
        let deduped = dedupeCandidatesBySource(candidates) { $0.source }
        let blended = deduped.first { isServerBlendedSource($0.source) }
        let multiUnblended = blended == nil && deduped.count > 1
        guard let chosen = blended ?? deduped.first else { return nil }
        let combined = candidates.count > 1
            ? combineCandidateVerdicts(
                candidates.map { (result: $0.result, conflict: $0.hasResultConflict) },
                finished: finished
            )
            : (result: chosen.result, conflict: chosen.hasResultConflict)

        return SetPlayerOutcome(
            id: chosen.id,
            setNumber: chosen.setNumber,
            playerName: chosen.playerName,
            shortName: chosen.shortName,
            side: chosen.side,
            quotedChance: multiUnblended ? nil : chosen.quotedChance,
            pregameChance: multiUnblended ? nil : chosen.pregameChance,
            observedAt: chosen.observedAt,
            pregameObservedAt: chosen.pregameObservedAt,
            result: combined.result,
            hasResultConflict: combined.conflict,
            source: multiUnblended ? nil : chosen.source,
            sourceCount: max(chosen.sourceCount, deduped.count),
            marketTitle: chosen.marketTitle
        )
    }

    @MainActor
    static func buildSetsCard(
        matrix: EventQuestionMatrix?,
        otherMarkets: [GameMarketOther],
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        now: Date = Date()
    ) -> SetsCard? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after
        var bySet: [Int: SetStepRow] = [:]

        func registerSetRow(
            setNumber: Int,
            marketTitle: String,
            homeCandidates: [SetPlayerOutcome],
            awayCandidates: [SetPlayerOutcome]
        ) {
            guard bySet[setNumber] == nil,
                  var home = resolveSetLegCandidates(homeCandidates, finished: finished),
                  var away = resolveSetLegCandidates(awayCandidates, finished: finished) else {
                return
            }

            if home.result == .won && away.result == .won {
                home.hasResultConflict = true
                away.hasResultConflict = true
                home = SetPlayerOutcome(
                    id: home.id, setNumber: home.setNumber, playerName: home.playerName,
                    shortName: home.shortName, side: home.side, quotedChance: home.quotedChance,
                    pregameChance: home.pregameChance, observedAt: home.observedAt,
                    pregameObservedAt: home.pregameObservedAt, result: nil, hasResultConflict: true,
                    source: home.source, sourceCount: home.sourceCount, marketTitle: home.marketTitle
                )
                away = SetPlayerOutcome(
                    id: away.id, setNumber: away.setNumber, playerName: away.playerName,
                    shortName: away.shortName, side: away.side, quotedChance: away.quotedChance,
                    pregameChance: away.pregameChance, observedAt: away.observedAt,
                    pregameObservedAt: away.pregameObservedAt, result: nil, hasResultConflict: true,
                    source: away.source, sourceCount: away.sourceCount, marketTitle: away.marketTitle
                )
            }

            let hasVisible = home.quotedChance != nil || home.pregameChance != nil
                || away.quotedChance != nil || away.pregameChance != nil
                || home.result != nil || away.result != nil
                || home.hasResultConflict || away.hasResultConflict
            guard hasVisible else { return }

            let winnerSide: PlayerPropsTeam.Side?
            if home.result == .won && away.result != .won {
                winnerSide = .home
            } else if away.result == .won && home.result != .won {
                winnerSide = .away
            } else {
                winnerSide = nil
            }
            let winnerName: String? = winnerSide == .home ? homeTeam : winnerSide == .away ? awayTeam : nil

            bySet[setNumber] = SetStepRow(
                setNumber: setNumber,
                label: "Set \(setNumber)",
                marketTitle: marketTitle,
                home: home,
                away: away,
                winnerSide: winnerSide,
                winnerName: winnerName
            )
        }

        // 1. Check game_question_matrix questions
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let mName = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard let setNum = parseSetWinnerNumber(mName) else { continue }
            var homeCandidates: [SetPlayerOutcome] = []
            var awayCandidates: [SetPlayerOutcome] = []
            for o in q.options {
                let rawLabel = o.label.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !rawLabel.isEmpty else { continue }
                let side: PlayerPropsTeam.Side?
                if o.side == "home" {
                    side = .home
                } else if o.side == "away" {
                    side = .away
                } else {
                    side = matchTennisPlayerSide(
                        candidate: rawLabel,
                        homeTeam: homeTeam,
                        awayTeam: awayTeam,
                        homeShort: homeShort,
                        awayShort: awayShort
                    )
                }
                guard let side else { continue }

                let evidenceList = o.sourceEvidence ?? []
                let dedupedEvidence = dedupeCandidatesBySource(evidenceList) { $0.source }
                let distinctEvidenceCount = max(1, dedupedEvidence.count)
                let rawSource = o.published.source
                    ?? (distinctEvidenceCount == 1 ? evidenceList.first?.source : nil)
                let multiEvidenceUnblended = !isServerBlendedSource(rawSource) && distinctEvidenceCount > 1

                let recent = NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                let pin = NBALadderCard9483.pin(o)
                let settledReading = settledSingleContributorReading(o)

                let quotedChance: Double?
                let pregameChance: Double?
                let pregameAt: String?
                if multiEvidenceUnblended {
                    quotedChance = nil
                    pregameChance = nil
                    pregameAt = nil
                } else {
                    switch currentPhase {
                    case .before:
                        let qVal = recent ? openChance(o.published.quotedValue) : nil
                        quotedChance = qVal
                        pregameChance = qVal
                        pregameAt = qVal != nil ? o.published.observedAt : nil
                    case .during:
                        quotedChance = recent ? openChance(o.published.quotedValue) : nil
                        pregameChance = pin?.probability
                        pregameAt = pin?.at
                    case .after:
                        quotedChance = nil
                        pregameChance = settledReading?.probability
                        pregameAt = settledReading?.at
                    }
                }

                let verdict = matrixOptionVerdict(o, finished: finished)
                let item = SetPlayerOutcome(
                    id: o.optionKey.isEmpty ? "tennis:set:\(setNum):\(side == .home ? "home" : "away")" : o.optionKey,
                    setNumber: setNum,
                    playerName: side == .home ? homeTeam : awayTeam,
                    shortName: side == .home ? homeShort : awayShort,
                    side: side,
                    quotedChance: quotedChance,
                    pregameChance: pregameChance,
                    observedAt: o.published.observedAt,
                    pregameObservedAt: pregameAt,
                    result: verdict.result,
                    hasResultConflict: verdict.conflict,
                    source: multiEvidenceUnblended ? nil : rawSource,
                    sourceCount: distinctEvidenceCount,
                    marketTitle: mName
                )
                if side == .home {
                    homeCandidates.append(item)
                } else {
                    awayCandidates.append(item)
                }
            }
            registerSetRow(
                setNumber: setNum,
                marketTitle: mName,
                homeCandidates: homeCandidates,
                awayCandidates: awayCandidates
            )
        }

        // 2. Fallback to otherMarkets grouped by set number
        var otherBySet: [Int: (title: String, rows: [GameMarketOther])] = [:]
        var setOrder: [Int] = []
        for row in otherMarkets {
            let mName = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard let setNum = parseSetWinnerNumber(mName), bySet[setNum] == nil else { continue }
            if otherBySet[setNum] == nil {
                setOrder.append(setNum)
                otherBySet[setNum] = (mName, [row])
            } else {
                otherBySet[setNum]?.rows.append(row)
            }
        }
        for setNum in setOrder {
            guard let group = otherBySet[setNum] else { continue }
            var homeCandidates: [SetPlayerOutcome] = []
            var awayCandidates: [SetPlayerOutcome] = []
            for row in group.rows {
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let side = matchTennisPlayerSide(
                    candidate: outLabel,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ) else { continue }
                let isSettledRow = row.resolutionSource != nil || row.isWinner != nil
                let recent = NFLMilestoneCard9483.isRecent(row.observedAt, now: now)
                let quotedChance: Double?
                let pregameChance: Double?
                switch currentPhase {
                case .before:
                    let qVal = (!isSettledRow && recent) ? openChance(row.probability) : nil
                    quotedChance = qVal
                    pregameChance = qVal
                case .during:
                    quotedChance = (!isSettledRow && recent) ? openChance(row.probability) : nil
                    pregameChance = openChance(row.pregameMark)
                case .after:
                    quotedChance = nil
                    pregameChance = openChance(row.pregameMark)
                }
                let verdict = otherRowVerdict(row, finished: finished)
                let item = SetPlayerOutcome(
                    id: "tennis:set:\(setNum):\(side == .home ? "home" : "away")",
                    setNumber: setNum,
                    playerName: side == .home ? homeTeam : awayTeam,
                    shortName: side == .home ? homeShort : awayShort,
                    side: side,
                    quotedChance: quotedChance,
                    pregameChance: pregameChance,
                    observedAt: row.observedAt,
                    pregameObservedAt: currentPhase == .before && pregameChance != nil ? row.observedAt : nil,
                    result: verdict,
                    hasResultConflict: false,
                    source: row.source,
                    sourceCount: 1,
                    marketTitle: group.title
                )
                if side == .home {
                    homeCandidates.append(item)
                } else {
                    awayCandidates.append(item)
                }
            }
            registerSetRow(
                setNumber: setNum,
                marketTitle: group.title,
                homeCandidates: homeCandidates,
                awayCandidates: awayCandidates
            )
        }

        let sets = bySet.values.sorted { $0.setNumber < $1.setNumber }
        guard !sets.isEmpty else { return nil }
        return SetsCard(
            phase: currentPhase,
            homePlayer: homeTeam,
            awayPlayer: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            sets: sets
        )
    }

    // MARK: - 2. Exact Match Score in Sets ("<Winner> in <N> sets" / "Exact match score in sets")

    nonisolated struct ExactScoreOutcome: Equatable, Identifiable, Sendable {
        let id: String
        let key: String
        let outcomeLabel: String
        let winnerSide: PlayerPropsTeam.Side
        let winnerName: String
        let winnerShort: String
        let winnerSets: Int
        let loserSets: Int
        let scoreLabel: String
        let quotedChance: Double?
        let pregameChance: Double?
        let observedAt: String?
        let pregameObservedAt: String?
        var result: OutcomeVerdict?
        var hasResultConflict: Bool = false
        let source: String?
        let sourceCount: Int
        let marketTitle: String
    }

    nonisolated struct ExactScoreCard: Equatable, Identifiable, Sendable {
        var id: String { "tennis:exactScore" }
        let phase: NBALadderCard9483.Phase
        let marketTitle: String
        let source: String?
        let homePlayer: String
        let awayPlayer: String
        let homeShort: String
        let awayShort: String
        let outcomes: [ExactScoreOutcome]

        var winningOutcome: ExactScoreOutcome? {
            outcomes.first { $0.result == .won && !$0.hasResultConflict }
        }

        var title: String {
            if phase == .after, let win = winningOutcome {
                let totalSets = win.winnerSets + win.loserSets
                return "\(win.winnerShort) in \(EventAtlasTennisCards11666.numberToWord(totalSets)) sets"
            }
            return "Exact match score in sets"
        }

        var reason: String {
            if phase == .after, let win = winningOutcome {
                let wWord = EventAtlasTennisCards11666.capitalizeWord(
                    EventAtlasTennisCards11666.numberToWord(win.winnerSets)
                )
                let lWord = EventAtlasTennisCards11666.numberToWord(win.loserSets)
                return "\(wWord) sets to \(lWord) is the match result"
            }
            return "Exact set-score outcomes keep their recorded quotes"
        }

        func current(at now: Date) -> ExactScoreCard {
            guard phase != .after else { return self }
            var changed = false
            let aged = outcomes.map { o -> ExactScoreOutcome in
                guard o.quotedChance != nil || (phase == .before && o.pregameChance != nil),
                      !NFLMilestoneCard9483.isRecent(o.observedAt, now: now) else {
                    return o
                }
                changed = true
                return ExactScoreOutcome(
                    id: o.id,
                    key: o.key,
                    outcomeLabel: o.outcomeLabel,
                    winnerSide: o.winnerSide,
                    winnerName: o.winnerName,
                    winnerShort: o.winnerShort,
                    winnerSets: o.winnerSets,
                    loserSets: o.loserSets,
                    scoreLabel: o.scoreLabel,
                    quotedChance: nil,
                    pregameChance: phase == .before ? nil : o.pregameChance,
                    observedAt: o.observedAt,
                    pregameObservedAt: o.pregameObservedAt,
                    result: o.result,
                    hasResultConflict: o.hasResultConflict,
                    source: o.source,
                    sourceCount: o.sourceCount,
                    marketTitle: o.marketTitle
                )
            }
            guard changed else { return self }
            return ExactScoreCard(
                phase: phase,
                marketTitle: marketTitle,
                source: source,
                homePlayer: homePlayer,
                awayPlayer: awayPlayer,
                homeShort: homeShort,
                awayShort: awayShort,
                outcomes: aged
            )
        }
    }

    static func isExactMatchScoreMarketName(_ marketName: String) -> Bool {
        marketName.range(
            of: #"\b(?:Exact\s+Match\s+Score|Exact\s+Set\s+Score|Correct\s+Set\s+Score|Set\s+Betting)\b"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil
    }

    static func parseExactSetScoreOutcome(
        outcomeLabel: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> (winnerSide: PlayerPropsTeam.Side, winnerSets: Int, loserSets: Int)? {
        let cleaned = outcomeLabel.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let rx = try? NSRegularExpression(pattern: #"(\d+)\s*[-–:]\s*(\d+)"#),
              let match = rx.firstMatch(
                  in: cleaned,
                  options: [],
                  range: NSRange(cleaned.startIndex..<cleaned.endIndex, in: cleaned)
              ),
              match.numberOfRanges == 3,
              let fullRange = Range(match.range(at: 0), in: cleaned),
              let r1 = Range(match.range(at: 1), in: cleaned),
              let r2 = Range(match.range(at: 2), in: cleaned),
              let a = Int(cleaned[r1]),
              let b = Int(cleaned[r2]) else {
            return nil
        }

        let rawPrefix = String(cleaned[..<fullRange.lowerBound])
        let rawSuffix = String(cleaned[fullRange.upperBound...])
        func cleanPlayerText(_ s: String) -> String {
            s.replacingOccurrences(of: #"\bwins?\b"#, with: "", options: [.regularExpression, .caseInsensitive])
                .replacingOccurrences(of: #"[-–:()]"#, with: " ", options: .regularExpression)
                .trimmingCharacters(in: .whitespacesAndNewlines)
        }
        let prefix = cleanPlayerText(rawPrefix)
        let suffix = cleanPlayerText(rawSuffix)
        let playerText = !prefix.isEmpty ? prefix : suffix
        guard !playerText.isEmpty,
              let matchedSide = matchTennisPlayerSide(
                  candidate: playerText,
                  homeTeam: homeTeam,
                  awayTeam: awayTeam,
                  homeShort: homeShort,
                  awayShort: awayShort
              ) else {
            return nil
        }

        let winnerSets = max(a, b)
        let loserSets = min(a, b)
        let canonical = "\(winnerSets)-\(loserSets)"
        guard validSetScores.contains(canonical) else { return nil }
        return (matchedSide, winnerSets, loserSets)
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

        var matchedMarketTitle: String?
        var candidatesByKey: [String: [ExactScoreOutcome]] = [:]
        var keyOrder: [String] = []

        func addCandidate(_ item: ExactScoreOutcome) {
            if candidatesByKey[item.key] == nil {
                keyOrder.append(item.key)
                candidatesByKey[item.key] = [item]
            } else {
                candidatesByKey[item.key]?.append(item)
            }
        }

        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        for q in gqmQuestions {
            let mName = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
            guard isExactMatchScoreMarketName(mName), q.options.count >= 2 else { continue }
            if matchedMarketTitle == nil { matchedMarketTitle = mName }
            for o in q.options {
                let outLabel = o.label.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let parsed = parseExactSetScoreOutcome(
                    outcomeLabel: outLabel,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ) else { continue }

                let evidenceList = o.sourceEvidence ?? []
                let dedupedEvidence = dedupeCandidatesBySource(evidenceList) { $0.source }
                let distinctEvidenceCount = max(1, dedupedEvidence.count)
                let rawSource = o.published.source
                    ?? (distinctEvidenceCount == 1 ? evidenceList.first?.source : nil)
                let multiEvidenceUnblended = !isServerBlendedSource(rawSource) && distinctEvidenceCount > 1

                let recent = NFLMilestoneCard9483.isRecent(o.published.observedAt, now: now)
                let pin = NBALadderCard9483.pin(o)
                let settledReading = settledSingleContributorReading(o)

                let quotedChance: Double?
                let pregameChance: Double?
                let pregameAt: String?
                if multiEvidenceUnblended {
                    quotedChance = nil
                    pregameChance = nil
                    pregameAt = nil
                } else {
                    switch currentPhase {
                    case .before:
                        let qVal = recent ? openChance(o.published.quotedValue) : nil
                        quotedChance = qVal
                        pregameChance = qVal
                        pregameAt = qVal != nil ? o.published.observedAt : nil
                    case .during:
                        quotedChance = recent ? openChance(o.published.quotedValue) : nil
                        pregameChance = pin?.probability
                        pregameAt = pin?.at
                    case .after:
                        quotedChance = nil
                        pregameChance = settledReading?.probability
                        pregameAt = settledReading?.at
                    }
                }

                let verdict = matrixOptionVerdict(o, finished: finished)
                let sideKey = parsed.winnerSide == .home ? "home" : "away"
                let dedupeKey = "\(sideKey):\(parsed.winnerSets)-\(parsed.loserSets)"
                let wName = parsed.winnerSide == .home ? homeTeam : awayTeam
                let wShort = parsed.winnerSide == .home ? homeShort : awayShort

                addCandidate(
                    ExactScoreOutcome(
                        id: o.optionKey.isEmpty ? "tennis:exact:\(dedupeKey)" : o.optionKey,
                        key: dedupeKey,
                        outcomeLabel: outLabel,
                        winnerSide: parsed.winnerSide,
                        winnerName: wName,
                        winnerShort: wShort,
                        winnerSets: parsed.winnerSets,
                        loserSets: parsed.loserSets,
                        scoreLabel: "\(wShort) \(parsed.winnerSets)–\(parsed.loserSets)",
                        quotedChance: quotedChance,
                        pregameChance: pregameChance,
                        observedAt: o.published.observedAt,
                        pregameObservedAt: pregameAt,
                        result: verdict.result,
                        hasResultConflict: verdict.conflict,
                        source: multiEvidenceUnblended ? nil : rawSource,
                        sourceCount: distinctEvidenceCount,
                        marketTitle: mName
                    )
                )
            }
        }

        if matchedMarketTitle == nil {
            for row in otherMarkets {
                let mName = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard isExactMatchScoreMarketName(mName) else { continue }
                if matchedMarketTitle == nil { matchedMarketTitle = mName }
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let parsed = parseExactSetScoreOutcome(
                    outcomeLabel: outLabel,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    homeShort: homeShort,
                    awayShort: awayShort
                ) else { continue }

                let isSettledRow = row.resolutionSource != nil || row.isWinner != nil
                let recent = NFLMilestoneCard9483.isRecent(row.observedAt, now: now)
                let quotedChance: Double?
                let pregameChance: Double?
                switch currentPhase {
                case .before:
                    let qVal = (!isSettledRow && recent) ? openChance(row.probability) : nil
                    quotedChance = qVal
                    pregameChance = qVal
                case .during:
                    quotedChance = (!isSettledRow && recent) ? openChance(row.probability) : nil
                    pregameChance = openChance(row.pregameMark)
                case .after:
                    quotedChance = nil
                    pregameChance = openChance(row.pregameMark)
                }

                let verdict = otherRowVerdict(row, finished: finished)
                let sideKey = parsed.winnerSide == .home ? "home" : "away"
                let dedupeKey = "\(sideKey):\(parsed.winnerSets)-\(parsed.loserSets)"
                let wName = parsed.winnerSide == .home ? homeTeam : awayTeam
                let wShort = parsed.winnerSide == .home ? homeShort : awayShort

                addCandidate(
                    ExactScoreOutcome(
                        id: "tennis:exact:\(dedupeKey)",
                        key: dedupeKey,
                        outcomeLabel: outLabel,
                        winnerSide: parsed.winnerSide,
                        winnerName: wName,
                        winnerShort: wShort,
                        winnerSets: parsed.winnerSets,
                        loserSets: parsed.loserSets,
                        scoreLabel: "\(wShort) \(parsed.winnerSets)–\(parsed.loserSets)",
                        quotedChance: quotedChance,
                        pregameChance: pregameChance,
                        observedAt: row.observedAt,
                        pregameObservedAt: currentPhase == .before && pregameChance != nil ? row.observedAt : nil,
                        result: verdict,
                        hasResultConflict: false,
                        source: row.source,
                        sourceCount: 1,
                        marketTitle: mName
                    )
                )
            }
        }

        guard let matchedMarketTitle, !candidatesByKey.isEmpty else { return nil }

        var outcomes: [ExactScoreOutcome] = []
        for key in keyOrder {
            guard let candidates = candidatesByKey[key], !candidates.isEmpty else { continue }
            let deduped = dedupeCandidatesBySource(candidates) { $0.source }
            let blended = deduped.first { isServerBlendedSource($0.source) }
            let multiUnblended = blended == nil && deduped.count > 1
            guard let chosen = blended ?? deduped.first else { continue }
            let combined = candidates.count > 1
                ? combineCandidateVerdicts(
                    candidates.map { (result: $0.result, conflict: $0.hasResultConflict) },
                    finished: finished
                )
                : (result: chosen.result, conflict: chosen.hasResultConflict)

            outcomes.append(
                ExactScoreOutcome(
                    id: chosen.id,
                    key: chosen.key,
                    outcomeLabel: chosen.outcomeLabel,
                    winnerSide: chosen.winnerSide,
                    winnerName: chosen.winnerName,
                    winnerShort: chosen.winnerShort,
                    winnerSets: chosen.winnerSets,
                    loserSets: chosen.loserSets,
                    scoreLabel: chosen.scoreLabel,
                    quotedChance: multiUnblended ? nil : chosen.quotedChance,
                    pregameChance: multiUnblended ? nil : chosen.pregameChance,
                    observedAt: chosen.observedAt,
                    pregameObservedAt: chosen.pregameObservedAt,
                    result: combined.result,
                    hasResultConflict: combined.conflict,
                    source: multiUnblended ? nil : chosen.source,
                    sourceCount: max(chosen.sourceCount, deduped.count),
                    marketTitle: chosen.marketTitle
                )
            )
        }

        guard outcomes.count >= 2 else { return nil }

        let wonIndices = outcomes.indices.filter { outcomes[$0].result == .won }
        if wonIndices.count > 1 {
            for idx in wonIndices {
                outcomes[idx].result = nil
                outcomes[idx].hasResultConflict = true
            }
        }

        let hasVisible = outcomes.contains {
            $0.quotedChance != nil || $0.pregameChance != nil
                || $0.result != nil || $0.hasResultConflict
        }
        guard hasVisible else { return nil }

        outcomes.sort { a, b in
            if a.winnerSide != b.winnerSide {
                return a.winnerSide == .home
            }
            if a.winnerSets != b.winnerSets { return a.winnerSets < b.winnerSets }
            return a.loserSets < b.loserSets
        }

        return ExactScoreCard(
            phase: currentPhase,
            marketTitle: matchedMarketTitle,
            source: outcomes.compactMap(\.source).first,
            homePlayer: homeTeam,
            awayPlayer: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            outcomes: outcomes
        )
    }

    // MARK: - 3. Total Games Ladder (`unit: "games"`, `startWord: "first serve"`, `actual: nil`)

    static func parseTotalGamesThreshold(_ marketName: String) -> Double? {
        if marketName.range(
            of: #"\b(?:Set\s+[1-5]|[1-5](?:st|nd|rd|th)\s+Set|Set\s+Handicap|Game\s+Spread|Tiebreak)\b"#,
            options: [.regularExpression, .caseInsensitive]
        ) != nil {
            return nil
        }
        let patterns = [
            #"\bMatch\s+O\/U\s+(\d+(?:\.\d+)?)\b"#,
            #"\bTotal\s+Games[:\s]+(?:O\/U\s+)?(\d+(?:\.\d+)?)\b"#,
            #"\bO\/U\s+(\d+(?:\.\d+)?)\s+Games\b"#
        ]
        for pattern in patterns {
            guard let rx = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
                  let m = rx.firstMatch(
                      in: marketName,
                      options: [],
                      range: NSRange(marketName.startIndex..<marketName.endIndex, in: marketName)
                  ),
                  m.numberOfRanges > 1,
                  let r = Range(m.range(at: 1), in: marketName),
                  let line = Double(marketName[r]),
                  line.isFinite, line >= 10, line <= 65 else { continue }
            return line
        }
        return nil
    }

    @MainActor
    static func buildTotalGamesCard(
        matrix: EventQuestionMatrix?,
        totals: [GameMarketOutcome],
        status: String?,
        commenceTime: Date?,
        homeShort: String,
        awayShort: String,
        now: Date = Date()
    ) -> NBALadderCard9483? {
        let currentPhase = EventAtlasNhlCards11666.phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after
        var byLine: [Double: NBALadderCard9483.Point] = [:]

        // 1. Check typed count_threshold questions in game_question_matrix
        let gqmQuestions = (matrix?.contract == NBAEventCards9483.matrixContract)
            ? (matrix?.questions ?? [])
            : []
        var typedByLine: [Double: [(q: QuestionMatrixQuestion, overOpt: QuestionMatrixOption)]] = [:]
        var typedLineOrder: [Double] = []
        for q in gqmQuestions where q.typing?.state == "typed" {
            guard q.kind == QuestionMatrixKind.countThreshold.rawValue,
                  q.subject?.side == "game",
                  q.period?.key == "full_game",
                  q.predicate?.relation == "ge",
                  let line = q.predicate?.line ?? q.predicate?.bound.map({ $0 - 0.5 }),
                  line.isFinite else { continue }
            guard let overOpt = q.options.first(where: {
                $0.side == "over" || $0.label.trimmingCharacters(in: .whitespacesAndNewlines)
                    .range(of: #"^over\b"#, options: [.regularExpression, .caseInsensitive]) != nil
            }) else { continue }
            if typedByLine[line] == nil {
                typedLineOrder.append(line)
                typedByLine[line] = [(q, overOpt)]
            } else {
                typedByLine[line]?.append((q, overOpt))
            }
        }

        for line in typedLineOrder {
            guard let candidates = typedByLine[line], !candidates.isEmpty else { continue }
            let deduped = dedupeCandidatesBySource(candidates) { $0.overOpt.published.source }
            let blended = deduped.first { isServerBlendedSource($0.overOpt.published.source) }
            let multiUnblended = blended == nil && deduped.count > 1
            guard let chosen = blended ?? deduped.first else { continue }
            let q = chosen.q
            let overOpt = chosen.overOpt

            let recent = NFLMilestoneCard9483.isRecent(overOpt.published.observedAt, now: now)
            let quoted = openChance(overOpt.published.quotedValue)
            let pin = NBALadderCard9483.pin(overOpt)
            let settledReading = settledSingleContributorReading(overOpt)

            let rawChance: Double?
            let rawNow: Double?
            switch currentPhase {
            case .before:
                rawChance = recent ? quoted : nil
                rawNow = nil
            case .during:
                rawChance = pin?.probability
                rawNow = recent ? quoted : nil
            case .after:
                rawChance = settledReading?.probability
                rawNow = nil
            }
            let chance = multiUnblended ? nil : rawChance
            let nowVal = multiUnblended ? nil : rawNow
            let source = multiUnblended ? nil : overOpt.published.source

            let hasWon = candidates.contains { $0.overOpt.result?.isWinner == true }
            let hasLost = candidates.contains { $0.overOpt.result?.isWinner == false }
            let result: Bool? = (finished && !(hasWon && hasLost)) ? overOpt.result?.isWinner : nil
            let label = "Over \(NBALadderCard9483.number(line)) games"

            byLine[line] = NBALadderCard9483.Point(
                optionKey: overOpt.optionKey.isEmpty ? "tennis:total:\(NBALadderCard9483.number(line))" : overOpt.optionKey,
                x: line,
                label: label,
                side: .game,
                chance: chance,
                now: nowVal,
                observedAt: overOpt.published.observedAt,
                result: result,
                detail: NBALadderCard9483.Detail(
                    label: overOpt.label.isEmpty ? label : overOpt.label,
                    marketName: q.marketName ?? q.label,
                    source: source,
                    sourceCount: deduped.count,
                    quoted: multiUnblended ? nil : quoted,
                    observedAt: overOpt.published.observedAt,
                    baseline: multiUnblended ? nil : (finished ? settledReading?.probability : pin?.probability),
                    baselineObservedAt: multiUnblended ? nil : (finished ? settledReading?.at : pin?.at),
                    result: result
                )
            )
        }

        // 2. Fallback to gameMarkets.totals
        if byLine.count < NBAEventCards9483.minimumLadderLines {
            var totalsByLine: [Double: [GameMarketOutcome]] = [:]
            var totalLineOrder: [Double] = []
            for row in totals {
                guard QuestionCatalog9483.lineSide(QuestionCatalog9483.row(row)) == .over else {
                    continue
                }
                let mName = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
                if mName.range(
                    of: #"\b(?:Set\s+[1-5]|[1-5](?:st|nd|rd|th)\s+Set|Set\s+Handicap|Game\s+Spread|Tiebreak)\b"#,
                    options: [.regularExpression, .caseInsensitive]
                ) != nil {
                    continue
                }
                let threshold = row.threshold ?? parseTotalGamesThreshold(mName)
                guard let line = threshold, line.isFinite, line >= 10, line <= 65,
                      byLine[line] == nil else { continue }
                if totalsByLine[line] == nil {
                    totalLineOrder.append(line)
                    totalsByLine[line] = [row]
                } else {
                    totalsByLine[line]?.append(row)
                }
            }

            for line in totalLineOrder {
                guard let candidates = totalsByLine[line], !candidates.isEmpty else { continue }
                let deduped = dedupeCandidatesBySource(candidates) { $0.source }
                let blended = deduped.first { isServerBlendedSource($0.source) }
                let multiUnblended = blended == nil && deduped.count > 1
                guard let chosen = blended ?? deduped.first else { continue }

                let isSettled = chosen.resolutionSource != nil || chosen.isWinner != nil
                let recent = NFLMilestoneCard9483.isRecent(chosen.observedAt, now: now)
                let overProb = openChance(chosen.overProbability ?? chosen.probability)

                let rawChance: Double? = currentPhase == .before
                    ? ((!isSettled && recent) ? overProb : nil)
                    : openChance(chosen.pregameMark)
                let rawNow: Double? = (currentPhase == .during && !isSettled && recent) ? overProb : nil
                let chance = multiUnblended ? nil : rawChance
                let nowVal = multiUnblended ? nil : rawNow
                let source = multiUnblended ? nil : chosen.source

                var sawWon = false
                for c in candidates where finished {
                    let outName = c.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                    let isUnder = outName.range(of: #"^under\b"#, options: [.regularExpression, .caseInsensitive]) != nil
                    let v = OutcomeVerdict.verdict(
                        isWinner: c.isWinner,
                        resolutionSource: c.resolutionSource,
                        marketResolved: false
                    )
                    if !isUnder && v == .won { sawWon = true }
                }
                let result: Bool? = (finished && sawWon) ? true : nil
                let label = "Over \(NBALadderCard9483.number(line)) games"
                let mName = chosen.marketName.trimmingCharacters(in: .whitespacesAndNewlines)

                byLine[line] = NBALadderCard9483.Point(
                    optionKey: "tennis:total:\(NBALadderCard9483.number(line))",
                    x: line,
                    label: label,
                    side: .game,
                    chance: chance,
                    now: nowVal,
                    observedAt: chosen.observedAt,
                    result: result,
                    detail: NBALadderCard9483.Detail(
                        label: label,
                        marketName: mName.isEmpty ? "Match O/U \(NBALadderCard9483.number(line))" : mName,
                        source: source,
                        sourceCount: deduped.count,
                        quoted: nowVal ?? (currentPhase == .before ? chance : nil),
                        observedAt: chosen.observedAt,
                        baseline: chance,
                        baselineObservedAt: nil,
                        result: result
                    )
                )
            }
        }

        let points = byLine.values.sorted { $0.x < $1.x }
        guard points.count >= 2 else { return nil }
        let hasVisible = points.contains { $0.chance != nil || $0.now != nil || $0.result != nil }
        guard hasVisible else { return nil }

        // CRITICAL TRUTH GUARD (`COMPONENT-CONTRACT.md` §7):
        // "Missing actual/projection stays absent; tennis sets cannot supply games actual."
        return NBALadderCard9483(
            family: .total,
            phase: currentPhase,
            points: points,
            actual: nil,
            forecast: nil,
            awayShort: awayShort,
            homeShort: homeShort,
            unit: "games",
            startWord: "first serve"
        )
    }

    // MARK: - Complete Tennis Deck in Fixed Slot Order

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
        now: Date = Date()
    ) -> [NFLEventCard9483] {
        guard applies(sportKey: sportKey, atlasEnabled: atlasEnabled),
              let gm = gameMarkets else { return [] }

        let resolvedHomeShort = (!homeShort.isEmpty && homeShort != homeTeam)
            ? homeShort
            : tennisPlayerShortName(homeTeam)
        let resolvedAwayShort = (!awayShort.isEmpty && awayShort != awayTeam)
            ? awayShort
            : tennisPlayerShortName(awayTeam)

        let others = gm.other ?? []
        let setsCard = buildSetsCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: resolvedHomeShort,
            awayShort: resolvedAwayShort,
            now: now
        )
        let exactScoreCard = buildExactScoreCard(
            matrix: gm.gameQuestionMatrix,
            otherMarkets: others,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: resolvedHomeShort,
            awayShort: resolvedAwayShort,
            now: now
        )
        let totalGamesCard = buildTotalGamesCard(
            matrix: gm.gameQuestionMatrix,
            totals: gm.totals ?? [],
            status: status,
            commenceTime: commenceTime,
            homeShort: resolvedHomeShort,
            awayShort: resolvedAwayShort,
            now: now
        )

        var deck: [NFLEventCard9483] = []
        if let setsCard { deck.append(.tennisSets(setsCard)) }
        if let exactScoreCard { deck.append(.tennisExactScore(exactScoreCard)) }
        if let totalGamesCard { deck.append(.ladder(totalGamesCard)) }
        return deck
    }

    // MARK: - Mark-Grammar Keys & Shared Details Sheet Models

    static func setsMarkKey(for card: SetsCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        if card.phase == .during && card.sets.contains(where: {
            $0.home.quotedChance != nil || $0.away.quotedChance != nil
        }) {
            items.append(Item(glyph: .filledCircle, label: "Recorded"))
        }
        if card.sets.contains(where: { $0.home.result != nil || $0.away.result != nil }) {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func exactScoreMarkKey(for card: ExactScoreCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        if card.phase == .during && card.outcomes.contains(where: { $0.quotedChance != nil }) {
            items.append(Item(glyph: .filledCircle, label: "Recorded"))
        }
        if card.outcomes.contains(where: { $0.result != nil }) {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func detailsModel(
        for leg: SetPlayerOutcome,
        card: SetsCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = leg.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if leg.hasResultConflict {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
        } else if let res = leg.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
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
        let sourceLabel: String?
        if leg.source == nil && leg.sourceCount > 1 {
            sourceLabel = "\(leg.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(
                source: leg.source,
                sourceCount: nil
            )
        }
        return EventAtlasDetailsSheetModel11666(
            id: leg.id,
            outcomeTitle: "Set \(leg.setNumber) · \(leg.playerName)",
            marketTitle: leg.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }

    static func detailsModel(
        for outcome: ExactScoreOutcome,
        card: ExactScoreCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = outcome.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if outcome.hasResultConflict {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
        } else if let res = outcome.result {
            primaryLabel = "Result"
            primaryValue = res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
        } else if card.phase == .after {
            primaryLabel = "Result"
            primaryValue = EventAtlasStates11666.pending
        } else if let quoted = outcome.quotedChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quoted)
        } else if let pregameText {
            primaryLabel = "Pregame baseline"
            primaryValue = pregameText
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(outcome.observedAt ?? outcome.pregameObservedAt)
        let resolvedSource = outcome.source ?? card.source
        let sourceLabel: String?
        if outcome.source == nil && outcome.sourceCount > 1 {
            sourceLabel = "\(outcome.sourceCount) sources, not blended"
        } else {
            sourceLabel = EventAtlasHeadline11666.sourceAttribution(
                source: resolvedSource,
                sourceCount: nil
            )
        }
        return EventAtlasDetailsSheetModel11666(
            id: outcome.id,
            outcomeTitle: outcome.scoreLabel,
            marketTitle: outcome.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }
}

// MARK: - SwiftUI Card Views for Tennis Story Cards

struct EventAtlasTennisSetsCardView11666: View {
    let card: EventAtlasTennisCards11666.SetsCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("SET BY SET")
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
                items: EventAtlasTennisCards11666.setsMarkKey(for: card)
            )
            VStack(alignment: .leading, spacing: 10) {
                ForEach(card.sets) { step in
                    setSection(step)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-tennis-sets-card-11666")
    }

    private func setSection(_ step: EventAtlasTennisCards11666.SetStepRow) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(step.label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                Spacer()
                if let winnerSide = step.winnerSide {
                    let winnerShort = winnerSide == .home ? card.homeShort : card.awayShort
                    Text("\(winnerShort) \(EventAtlasStates11666.wonWithCheck)")
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(Color.green)
                }
            }
            legRow(step.home, color: homeColor)
            legRow(step.away, color: awayColor)
        }
        .padding(8)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 8))
    }

    private func legRow(_ leg: EventAtlasTennisCards11666.SetPlayerOutcome, color: Color) -> some View {
        let displayChance = card.phase == .after ? leg.pregameChance : (leg.quotedChance ?? leg.pregameChance)
        let rowBody = HStack(spacing: 8) {
            Text(leg.shortName)
                .font(.subheadline.weight(.semibold))
                .frame(width: 96, alignment: .leading)
                .lineLimit(1)
            if let chance = displayChance {
                Text(formatProbability(chance))
                    .font(.subheadline.weight(.bold).monospacedDigit())
                    .foregroundStyle(color)
            } else {
                Text(EventAtlasStates11666.noRecentPrice)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 4)
            if card.phase == .after {
                if leg.hasResultConflict {
                    Text(EventAtlasStates11666.pending)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
                } else if let res = leg.result {
                    Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(res == .won ? Color.green : Color.secondary)
                } else {
                    Text(EventAtlasStates11666.pending)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.secondary)
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

struct EventAtlasTennisExactScoreCardView11666: View {
    let card: EventAtlasTennisCards11666.ExactScoreCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("EXACT MATCH SCORE")
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
                items: EventAtlasTennisCards11666.exactScoreMarkKey(for: card)
            )
            LazyVGrid(columns: [GridItem(.adaptive(minimum: 96), spacing: 6)], spacing: 6) {
                ForEach(card.outcomes) { outcome in
                    outcomeTile(outcome)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-tennis-exact-score-card-11666")
    }

    private func outcomeTile(_ outcome: EventAtlasTennisCards11666.ExactScoreOutcome) -> some View {
        let color = outcome.winnerSide == .home ? homeColor : awayColor
        let displayChance = card.phase == .after ? outcome.pregameChance : (outcome.quotedChance ?? outcome.pregameChance)
        let box = VStack(spacing: 3) {
            Text(outcome.scoreLabel)
                .font(.caption.weight(.bold).monospacedDigit())
                .lineLimit(1)
            if let chance = displayChance {
                Text(formatProbability(chance))
                    .font(.caption2.weight(.semibold).monospacedDigit())
                    .foregroundStyle(color)
            } else {
                Text(EventAtlasStates11666.noRecentPrice)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            if card.phase == .after {
                if outcome.hasResultConflict {
                    Text(EventAtlasStates11666.pending)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                } else if let res = outcome.result {
                    Text(res == .won ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(res == .won ? Color.green : Color.secondary)
                } else {
                    Text(EventAtlasStates11666.pending)
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 6)
        .padding(.horizontal, 4)
        .frame(maxWidth: .infinity)
        .background(Color.secondary.opacity(0.08), in: RoundedRectangle(cornerRadius: 8))

        return Group {
            if expanded {
                Button {
                    state.detailsRowID = outcome.id
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
