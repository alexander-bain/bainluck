import SwiftUI

/// #11666 Step E6b — Native Event-page Atlas NHL story cards (`icehockey_nhl`),
/// mirroring web `#11974` Step E6b (`frontend/lib/nhlEventCards.ts`), gated behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`:
/// 1. Goalscorers (`ScoringCard`): `"Who found the net?"` (finished with scorers)
///    or `"Likely goalscorers"` (before/during play), plotting each player's
///    saved pregame 1+ goal chance on a shared probability rail alongside actual
///    goals scored and settlement mark (`✓ Won` / `✗ Lost`). Withholds unblended
///    multi-source probabilities rather than averaging on the client.
/// 2. Goal expectations (`NBALadderCard9483`, `family: .total`, `quantity: "goals"`):
///    full-game goal total lines from `game_question_matrix` (`10238.v1`).
/// 3. Puck-line margin (`NBALadderCard9483`, `family: .margin`, `quantity: "goals"`):
///    full-game signed goal handicap lines from `game_question_matrix` (`10238.v1`).
/// 4. Skater points / assists milestone (`NFLMilestoneCard9483`, `id: "nhl:contributions"`):
///    skater points/assists milestone ladder when ≥ 3 priced thresholds exist.
nonisolated enum EventAtlasNhlCards11666 {

    static let sportKey = "icehockey_nhl"
    static let maxScorers = 4

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && sportKey == Self.sportKey
    }

    // MARK: - 1. Goalscorers Card ("Who found the net?" / "Likely goalscorers")

    nonisolated struct ScorerEntry: Equatable, Identifiable, Sendable {
        let id: String
        let rowId: String
        let player: String
        let pregameChance: Double?
        let observedAt: String?
        let actualGoals: Int?
        let hit: Bool?
        let side: PlayerPropsTeam.Side
        let source: String?
        let sourceCount: Int
        let marketTitle: String
    }

    nonisolated struct ScoringCard: Equatable, Identifiable, Sendable {
        nonisolated enum Story: String, Equatable, Sendable {
            case scored
            case likeliest
        }

        var id: String { "nhl:scoring" }
        let story: Story
        let phase: NBALadderCard9483.Phase
        let entries: [ScorerEntry]
        let scaleCeiling: Double

        var title: String {
            story == .scored ? "Who found the net?" : "Likely goalscorers"
        }

        var reason: String {
            if story == .scored {
                return "Players who scored, alongside their pregame 1+ goal chance"
            }
            return "Highest pregame chances of scoring 1+ goals"
        }

        func current(at now: Date) -> ScoringCard {
            guard phase == .before else { return self }
            var changed = false
            let aged = entries.map { entry -> ScorerEntry in
                guard entry.pregameChance != nil,
                      !NFLMilestoneCard9483.isRecent(entry.observedAt, now: now) else { return entry }
                changed = true
                return ScorerEntry(
                    id: entry.id,
                    rowId: entry.rowId,
                    player: entry.player,
                    pregameChance: nil,
                    observedAt: entry.observedAt,
                    actualGoals: entry.actualGoals,
                    hit: entry.hit,
                    side: entry.side,
                    source: entry.source,
                    sourceCount: entry.sourceCount,
                    marketTitle: entry.marketTitle
                )
            }
            guard changed else { return self }
            return ScoringCard(
                story: story,
                phase: phase,
                entries: aged,
                scaleCeiling: EventAtlasNhlCards11666.computeScoringScaleCeiling(aged)
            )
        }
    }

    static func computeScoringScaleCeiling(_ entries: [ScorerEntry]) -> Double {
        let top = entries.reduce(0.0) { max($0, $1.pregameChance ?? 0.0) }
        return min(1.0, max(0.35, ceil(top * 20.0) / 20.0))
    }

    private static func openChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    @MainActor
    static func phase(
        status: String?,
        commenceTime: Date?,
        now: Date = Date()
    ) -> NBALadderCard9483.Phase {
        if EventState.isFinished(status) { return .after }
        if status == "live" || EventState.hasStarted(commenceTime: commenceTime, now: now) {
            return .during
        }
        return .before
    }

    /// Parses `(player, stat)` from an NHL prop row, matching `parseMlbPropShape`.
    static func parsePropShape(
        _ row: GameMarketPlayerProp,
        homeTeam: String,
        awayTeam: String
    ) -> (player: String, stat: String)? {
        let parts = row.outcomeName.split(separator: ":", maxSplits: 1)
        guard parts.count == 2 else { return nil }
        let player = PropSubject.display(parts[0].trimmingCharacters(in: .whitespacesAndNewlines))
        guard !player.isEmpty else { return nil }
        let rawStat = PlayerPropsStatLabel.display(
            marketName: row.marketName.trimmingCharacters(in: .whitespacesAndNewlines),
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            player: player
        ).trimmingCharacters(in: .whitespacesAndNewlines)
        guard !rawStat.isEmpty else { return nil }
        return (player, rawStat)
    }

    @MainActor
    static func buildScoringCard(
        props: [GameMarketPlayerProp],
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        now: Date = Date()
    ) -> ScoringCard? {
        let currentPhase = phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after

        func rowPregameChance(_ row: GameMarketPlayerProp) -> Double? {
            if currentPhase == .before {
                guard NFLMilestoneCard9483.isRecent(row.observedAt, now: now) else { return nil }
                return openChance(row.overProbability)
            }
            return openChance(row.pregameMark)
        }

        struct PlayerGroup {
            let player: String
            var rows: [GameMarketPlayerProp]
            var sources: Set<String>
            var hits: Set<Bool>
        }

        var byPlayer: [String: PlayerGroup] = [:]
        var playerOrder: [String] = []

        for row in props {
            if row._inverted == true { continue }
            guard let shape = parsePropShape(row, homeTeam: homeTeam, awayTeam: awayTeam) else { continue }
            let statLower = shape.stat.lowercased()
            guard statLower == "goals" || statLower == "goal" else { continue }
            guard !PlayerPropsFamily.isTeamSubject(shape.player, teams: [homeTeam, awayTeam]) else { continue }
            guard row.threshold == 1.0 || row.threshold == 0.5 else { continue }
            guard QuestionCatalog9483.lineSide(QuestionCatalog9483.row(row)) == .over else { continue }

            if byPlayer[shape.player] == nil {
                playerOrder.append(shape.player)
                var sources = Set<String>()
                if let src = row.source, !src.isEmpty { sources.insert(src) }
                var hits = Set<Bool>()
                if finished, let h = row.hit { hits.insert(h) }
                byPlayer[shape.player] = PlayerGroup(
                    player: shape.player,
                    rows: [row],
                    sources: sources,
                    hits: hits
                )
            } else {
                byPlayer[shape.player]?.rows.append(row)
                if let src = row.source, !src.isEmpty {
                    byPlayer[shape.player]?.sources.insert(src)
                }
                if finished, let h = row.hit {
                    byPlayer[shape.player]?.hits.insert(h)
                }
            }
        }

        var all: [ScorerEntry] = []
        for playerKey in playerOrder {
            guard let group = byPlayer[playerKey], let primaryRow = group.rows.first else { continue }
            let blendedRow = group.rows.first { $0.source == "blended" || $0.source == "blend" }
            let pricedRows = group.rows.filter { rowPregameChance($0) != nil }

            let pregameChance: Double?
            let observedAt: String?
            if let blendedRow {
                pregameChance = rowPregameChance(blendedRow)
                observedAt = blendedRow.observedAt ?? primaryRow.observedAt
            } else if group.sources.count <= 1 && pricedRows.count == 1, let singleRow = pricedRows.first {
                pregameChance = rowPregameChance(singleRow)
                observedAt = singleRow.observedAt ?? primaryRow.observedAt
            } else {
                // Withhold unblended multi-source pregame chance rather than averaging on the client.
                pregameChance = nil
                observedAt = primaryRow.observedAt
            }

            let actualRow = finished
                ? group.rows.first { ($0.actual ?? -1).isFinite && ($0.actual ?? -1) >= 0 }
                : nil
            let actualGoals = actualRow?.actual.map { Int($0.rounded()) }

            let hit: Bool?
            if group.hits.contains(true) && group.hits.contains(false) {
                hit = nil
            } else if group.hits.contains(true) {
                hit = true
            } else if group.hits.contains(false) {
                hit = false
            } else {
                hit = nil
            }

            if pregameChance == nil && (actualGoals == nil || actualGoals == 0) {
                continue
            }

            let rId = primaryRow.id
            let sideToken = group.rows.compactMap(\.playerTeam).first { $0 == "home" || $0 == "away" }
            let singleSource = blendedRow?.source ?? (group.sources.count == 1 ? group.sources.first : nil)

            all.append(
                ScorerEntry(
                    id: "nhl-scorer:\(rId)",
                    rowId: rId,
                    player: group.player,
                    pregameChance: pregameChance,
                    observedAt: observedAt,
                    actualGoals: actualGoals,
                    hit: hit,
                    side: PlayerPropsTeam.side(for: sideToken),
                    source: singleSource,
                    sourceCount: max(1, group.sources.count),
                    marketTitle: "\(group.player) · 1+ goals"
                )
            )
        }

        guard !all.isEmpty else { return nil }

        let scorers = all
            .filter { ($0.actualGoals ?? 0) >= 1 }
            .sorted { a, b in
                let ga = a.actualGoals ?? 0
                let gb = b.actualGoals ?? 0
                if gb != ga { return gb > ga }
                let pa = a.pregameChance ?? 1.0
                let pb = b.pregameChance ?? 1.0
                if pa != pb { return pa < pb }
                return a.player < b.player
            }

        if finished && !scorers.isEmpty {
            let chosen = Array(scorers.prefix(maxScorers))
            return ScoringCard(
                story: .scored,
                phase: currentPhase,
                entries: chosen,
                scaleCeiling: computeScoringScaleCeiling(chosen)
            )
        }

        let likeliest = Array(
            all
                .filter { $0.pregameChance != nil }
                .sorted { a, b in
                    let pa = a.pregameChance ?? 0.0
                    let pb = b.pregameChance ?? 0.0
                    if pb != pa { return pb > pa }
                    return a.player < b.player
                }
                .prefix(maxScorers)
        )

        guard !likeliest.isEmpty else { return nil }
        return ScoringCard(
            story: .likeliest,
            phase: currentPhase,
            entries: likeliest,
            scaleCeiling: computeScoringScaleCeiling(likeliest)
        )
    }

    // MARK: - 2 & 3. Goal Totals & Puck-line Margin Ladders

    private static func typedQuestions(_ matrix: EventQuestionMatrix?) -> [QuestionMatrixQuestion] {
        guard let matrix, matrix.contract == NBAEventCards9483.matrixContract,
              matrix.displayScope == nil || matrix.displayScope == QuestionMatrixScope.game.rawValue
        else { return [] }
        return matrix.questions.filter { $0.typing?.state == "typed" }
    }

    @MainActor
    private static func matrixPoint(
        _ question: QuestionMatrixQuestion,
        _ option: QuestionMatrixOption,
        x: Double,
        label: String,
        side: NBALadderCard9483.Side,
        phase: NBALadderCard9483.Phase,
        input: NBALadderCard9483.Input
    ) -> NBALadderCard9483.Point {
        let quoted = option.published.quotedValue
        let observedAt = option.published.observedAt
        let recent = quoted != nil && NFLMilestoneCard9483.isRecent(observedAt, now: input.now)
        let pin = NBALadderCard9483.pin(option)

        let settledReading: (probability: Double, at: String)? = {
            guard let reading = option.pregameReading, reading.state == "available",
                  reading.basis == "pregame_pin",
                  let outcome = reading.outcomeId, option.contributorOutcomeIds == [outcome],
                  let probability = reading.probability, probability.isFinite, probability > 0, probability < 1,
                  let at = reading.observedAt, !at.isEmpty else { return nil }
            return (probability, at)
        }()

        let chance: Double?
        let nowVal: Double?
        switch phase {
        case .before:
            chance = recent ? quoted : nil
            nowVal = nil
        case .during:
            chance = pin?.probability
            nowVal = recent
                && !EventState.isSuspendedAndStarted(input.status, commenceTime: input.commenceTime, now: input.now)
                ? quoted : nil
        case .after:
            // After the final, read ONLY the producer's admitted `pregame_reading` (#11125 contract).
            chance = settledReading?.probability
            nowVal = nil
        }

        let settled = phase == .after
        return NBALadderCard9483.Point(
            optionKey: option.optionKey,
            x: x,
            label: label,
            side: side,
            chance: chance,
            now: nowVal,
            observedAt: observedAt,
            result: settled ? option.result?.isWinner : nil,
            detail: NBALadderCard9483.Detail(
                label: option.label.isEmpty ? label : option.label,
                marketName: question.marketName ?? question.label,
                source: option.published.source,
                quoted: quoted,
                observedAt: observedAt,
                baseline: settled ? settledReading?.probability : pin?.probability,
                baselineObservedAt: settled ? settledReading?.at : pin?.at,
                result: option.result?.isWinner
            )
        )
    }

    @MainActor
    static func buildGoalTotalsCard(_ input: NBALadderCard9483.Input) -> NBALadderCard9483? {
        let currentPhase = phase(status: input.status, commenceTime: input.commenceTime, now: input.now)
        var points: [NBALadderCard9483.Point] = []
        for question in typedQuestions(input.matrix) {
            guard question.kind == QuestionMatrixKind.countThreshold.rawValue,
                  question.quantity?.key == "goals",
                  question.subject?.side == "game",
                  question.period?.key == "full_game",
                  question.predicate?.relation == "ge",
                  let line = question.predicate?.line ?? question.predicate?.bound.map({ $0 - 0.5 }),
                  line.isFinite else { continue }
            let own = question.options.filter { $0.side == "over" }
            guard own.count == 1, let option = own.first else { continue }
            points.append(
                matrixPoint(
                    question,
                    option,
                    x: line,
                    label: "Over \(NBALadderCard9483.number(line)) goals",
                    side: .game,
                    phase: currentPhase,
                    input: input
                )
            )
        }
        var counts: [Double: Int] = [:]
        for p in points { counts[p.x, default: 0] += 1 }
        let kept = points.filter { counts[$0.x] == 1 }.sorted { $0.x < $1.x }
        guard kept.count >= NBAEventCards9483.minimumLadderLines else { return nil }

        let actual: Double? = currentPhase != .before
            ? input.homeScore.flatMap { h in input.awayScore.map { Double(h + $0) } }
            : nil

        return NBALadderCard9483(
            family: .total,
            phase: currentPhase,
            points: kept,
            actual: actual,
            forecast: nil,
            awayShort: input.awayShort,
            homeShort: input.homeShort
        )
    }

    @MainActor
    static func buildPuckLineMarginCard(_ input: NBALadderCard9483.Input) -> NBALadderCard9483? {
        let currentPhase = phase(status: input.status, commenceTime: input.commenceTime, now: input.now)
        var points: [NBALadderCard9483.Point] = []
        for question in typedQuestions(input.matrix) {
            guard question.kind == QuestionMatrixKind.signedHandicap.rawValue,
                  question.quantity?.key == "goals",
                  question.period?.key == "full_game",
                  question.predicate?.relation == "handicap",
                  let line = question.predicate?.line, line.isFinite, line < 0 else { continue }
            let side: NBALadderCard9483.Side
            switch question.subject?.side {
            case "home"?: side = .home
            case "away"?: side = .away
            default: continue
            }
            let own = question.options.filter { $0.side == question.subject?.side }
            guard own.count == 1, let option = own.first else { continue }
            let by = -line
            let team = side == .home ? input.homeShort : input.awayShort
            points.append(
                matrixPoint(
                    question,
                    option,
                    x: side == .home ? by : -by,
                    label: "\(team) by \(Int(by.rounded(.down)) + 1)+",
                    side: side,
                    phase: currentPhase,
                    input: input
                )
            )
        }
        var counts: [Double: Int] = [:]
        for p in points { counts[p.x, default: 0] += 1 }
        let kept = points.filter { counts[$0.x] == 1 }.sorted { $0.x < $1.x }
        guard kept.count >= NBAEventCards9483.minimumLadderLines else { return nil }

        let actual: Double? = currentPhase != .before
            ? input.homeScore.flatMap { h in input.awayScore.map { Double(h - $0) } }
            : nil

        return NBALadderCard9483(
            family: .margin,
            phase: currentPhase,
            points: kept,
            actual: actual,
            forecast: nil,
            awayShort: input.awayShort,
            homeShort: input.homeShort
        )
    }

    // MARK: - 4. Skater Points / Assists Milestone Card

    @MainActor
    static func buildContributionMilestoneCard(
        props: [GameMarketPlayerProp],
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        now: Date = Date()
    ) -> NFLMilestoneCard9483? {
        let currentPhase = phase(status: status, commenceTime: commenceTime, now: now)
        let finished = currentPhase == .after
        let basis: NFLMilestoneCard9483.Basis = currentPhase == .before ? .pregamePrice : .pregameMark

        var ladders: [String: (player: String, stat: String, rows: [GameMarketPlayerProp])] = [:]
        for row in props {
            if row._inverted == true { continue }
            guard let shape = parsePropShape(row, homeTeam: homeTeam, awayTeam: awayTeam) else { continue }
            let statLower = shape.stat.lowercased()
            guard statLower == "points" || statLower == "assists" else { continue }
            guard !PlayerPropsFamily.isTeamSubject(shape.player, teams: [homeTeam, awayTeam]) else { continue }
            let key = "\(shape.player)|\(statLower)"
            var entry = ladders[key] ?? (shape.player, shape.stat, [])
            entry.rows.append(row)
            ladders[key] = entry
        }

        var candidates: [(key: String, card: NFLMilestoneCard9483, pricedCount: Int)] = []
        for (key, ladder) in ladders {
            var rawRungs: [NFLMilestoneCard9483.Rung] = []
            for row in ladder.rows {
                guard let threshold = row.threshold, threshold.isFinite else { continue }
                guard QuestionCatalog9483.lineSide(QuestionCatalog9483.row(row)) == .over else { continue }
                let observedAt = basis == .pregamePrice ? row.observedAt : nil
                var chance = openChance(basis == .pregamePrice ? row.overProbability : row.pregameMark)
                if basis == .pregamePrice && !NFLMilestoneCard9483.isRecent(observedAt, now: now) {
                    chance = nil
                }
                rawRungs.append(
                    NFLMilestoneCard9483.Rung(
                        threshold: threshold,
                        chance: chance,
                        observedAt: observedAt,
                        rowID: row.id,
                        hit: finished ? row.hit : nil
                    )
                )
            }
            var counts: [Double: Int] = [:]
            for r in rawRungs { counts[r.threshold, default: 0] += 1 }
            let rungs = rawRungs.filter { counts[$0.threshold] == 1 }.sorted { $0.threshold < $1.threshold }
            let servedSide = PlayerPropsTeam.side(for: ladder.rows.compactMap(\.playerTeam).first)
            let actualVal = finished
                ? ladder.rows.compactMap(\.actual).first(where: { $0.isFinite })
                : nil
            let headshot = NFLMilestoneCard9483.headshot(of: ladder.rows)

            let card = NFLMilestoneCard9483(
                id: "nhl:contributions",
                player: ladder.player,
                stat: ladder.stat,
                side: servedSide,
                basis: basis,
                rungs: rungs,
                actual: actualVal,
                headshot: headshot
            )
            guard card.profile != nil else { continue }
            candidates.append((key, card, rungs.filter { $0.chance != nil }.count))
        }

        candidates.sort { a, b in
            if a.pricedCount != b.pricedCount { return a.pricedCount > b.pricedCount }
            return a.key < b.key
        }
        return candidates.first?.card
    }

    // MARK: - Complete NHL Deck in Fixed Slot Order

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

        let props = gm.playerProps ?? []
        let scoring = buildScoringCard(
            props: props,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
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
        let totals = buildGoalTotalsCard(ladderInput)
        let margin = buildPuckLineMarginCard(ladderInput)
        let contributions = buildContributionMilestoneCard(
            props: props,
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            now: now
        )

        var deck: [NFLEventCard9483] = []
        if let scoring { deck.append(.nhlScoring(scoring)) }
        if let totals { deck.append(.ladder(totals)) }
        if let margin { deck.append(.ladder(margin)) }
        if let contributions { deck.append(.milestone(contributions)) }
        return deck
    }

    // MARK: - Mark-Grammar Key & Shared Details Sheet Model

    static func scoringMarkKey(for card: ScoringCard) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        if card.entries.contains(where: { $0.actualGoals != nil }) {
            items.append(Item(glyph: .verticalBar, label: "Official final"))
        }
        if card.entries.contains(where: { $0.hit != nil }) {
            items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func detailsModel(
        for entry: ScorerEntry,
        card: ScoringCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = entry.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let hit = entry.hit {
            primaryLabel = "Result"
            let badge = hit ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross
            if let goals = entry.actualGoals {
                primaryValue = "\(badge) · \(goals) \(goals == 1 ? "goal" : "goals")"
            } else {
                primaryValue = badge
            }
        } else if let goals = entry.actualGoals {
            primaryLabel = "Official final"
            primaryValue = "\(goals) \(goals == 1 ? "goal" : "goals")"
        } else if let pregameText {
            primaryLabel = "Pregame chance"
            primaryValue = pregameText
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = SourceAge.preciseStamp(entry.observedAt)
        let sourceLabel = EventAtlasHeadline11666.sourceAttribution(
            source: entry.source,
            sourceCount: entry.sourceCount
        )
        return EventAtlasDetailsSheetModel11666(
            id: entry.id,
            outcomeTitle: "\(entry.player): 1+ goals",
            marketTitle: entry.marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }
}

// MARK: - SwiftUI Card View for NHL Goalscorers

struct EventAtlasNhlScoringCardView11666: View {
    let card: EventAtlasNhlCards11666.ScoringCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("NHL GOALSCORERS")
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
                items: EventAtlasNhlCards11666.scoringMarkKey(for: card)
            )

            VStack(alignment: .leading, spacing: 10) {
                ForEach(card.entries) { entry in
                    rowView(entry)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-nhl-scoring-card-11666")
    }

    private func rowView(_ entry: EventAtlasNhlCards11666.ScorerEntry) -> some View {
        let teamColor = PlayerPropsTeam.color(for: entry.side, home: homeColor, away: awayColor)
        let fraction = entry.pregameChance.map { min(1.0, max(0.0, $0 / max(0.05, card.scaleCeiling))) } ?? 0.0
        let chanceText = entry.pregameChance.map { "\(formatProbability($0)) pregame" }
            ?? (card.phase == .before ? EventAtlasStates11666.noRecentPrice : "Pregame chance unavailable")

        let rowBody = VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(entry.player)
                    .font(.subheadline.weight(.semibold))
                Spacer(minLength: 6)
                if let goals = entry.actualGoals, card.phase == .after {
                    Text("\(goals) \(goals == 1 ? "goal" : "goals")")
                        .font(.caption.weight(.semibold).monospacedDigit())
                        .foregroundStyle(.primary)
                }
                if let hit = entry.hit, card.phase == .after {
                    Text(hit ? EventAtlasStates11666.wonWithCheck : EventAtlasStates11666.lostWithCross)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(hit ? Color.green : Color.secondary)
                }
            }
            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.14))
                        .frame(height: 6)
                    if entry.pregameChance != nil {
                        Capsule()
                            .fill(teamColor.opacity(0.35))
                            .frame(width: max(6, geo.size.width * fraction), height: 6)
                        Circle()
                            .strokeBorder(teamColor, lineWidth: 2)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: 10, height: 10)
                            .offset(x: max(0, min(geo.size.width - 10, geo.size.width * fraction - 5)))
                    }
                }
            }
            .frame(height: 10)
            Text(expanded ? "\(chanceText) · details" : chanceText)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }

        return Group {
            if expanded {
                Button {
                    state.detailsRowID = entry.id
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
