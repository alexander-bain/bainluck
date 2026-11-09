import Foundation
import SwiftUI

/// #11666 (Item 16d-1, Decide 91-C) — Native Rugby & AFL / Aussie Rules Atlas Story Cards:
///   1. **Match Outlook Card (`FieldPhaseHeadlinePresentation10868` + `FieldOutlookBarsPresentation10868`)**:
///      - **Rugby (`rugby_union`, `rugby_league`, `rugby_sevens`, `rugby_*`)**: 3-way match outcome
///        (Home, Away, Draw/Tie — or 2-way when no draw outcome is listed) with unscaled 0–100%
///        probabilities (never normalized or forced to sum to 100%).
///      - **AFL / Aussie Rules (`aussierules_afl`, `aussierules_aflw`, `afl`, `aussierules_*`)**:
///        Both teams' win chances at equal prominence (plus Draw when listed).
///      - **Decide 10-C House Rule**:
///        - `.before`: Shows ONLY the live reading (`probability`) from the last 30 minutes
///          (`isStale ? nil : latest`), labelled `"Current chance"`, and ages it after 30 minutes
///          to `"No recent probability"`. Never uses `pregameMark` before match start.
///        - `.during`: Shows `pregameMark` (`"Pre-match chance"`) as the fixed reference beside
///          the live reading (`"Live chance"`, aged after 30 minutes to `"No recent probability"`).
///        - `.final`: Shows `pregameMark` (`"Pre-match chance"`) beside the Decide 80-A
///          venue-confirmed contract grade (`"✓ Won"` only when authoritatively settled, else
///          `"Result not confirmed"`; a row without its market's status never mints `"✗ Lost"`).
///   2. **Handicap / Line & Total Points Story Card (`FieldPhaseHeadlinePresentation10868`)**:
///      - Surfaces Rugby handicap/total-points and AFL line/margin/total-points markets with
///        Decide 10-C `.before` / `.during` / `.final` rules and Decide 80-A settlement grades.
enum EventAtlasRugbyAflCards11666 {

    /// 30-minute live-quote staleness window per Decide 10-C.
    nonisolated static let staleThresholdSeconds: TimeInterval = 30 * 60

    // MARK: - Sport Gating

    nonisolated enum SportKind: String, Equatable, Sendable {
        case rugby
        case afl

        var badgeTitle: String {
            switch self {
            case .rugby: return "Rugby"
            case .afl: return "Aussie Rules"
            }
        }

        var matchTitle: String {
            switch self {
            case .rugby: return "Match outcome"
            case .afl: return "Match winner"
            }
        }
    }

    private static let rugbyPrefixes: [String] = [
        "rugby_union",
        "rugby_league",
        "rugby_sevens",
        "rugby"
    ]

    private static let aflPrefixes: [String] = [
        "aussierules_afl",
        "aussierules_aflw",
        "aussierules",
        "aussie_rules",
        "afl",
        "aflw"
    ]

    nonisolated static func sportKind(sportKey: String?) -> SportKind? {
        guard let raw = sportKey else { return nil }
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !lower.isEmpty else { return nil }
        if rugbyPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0) }) {
            return .rugby
        }
        if aflPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0) }) {
            return .afl
        }
        return nil
    }

    nonisolated static func isRugbyOrAflSport(_ raw: String?) -> Bool {
        sportKind(sportKey: raw) != nil
    }

    nonisolated static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && sportKind(sportKey: sportKey) != nil
    }

    // MARK: - Outcome Roles & Normalized Row

    nonisolated enum OutcomeRole: String, Equatable, Sendable {
        case home
        case away
        case draw
    }

    nonisolated struct OutcomeRow: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: Int
        let marketTitle: String
        let outcomeName: String
        let role: OutcomeRole?
        let probability: Double?
        let pregameMark: Double?
        let source: String?
        let observedAt: Date?
        let isWinner: Bool?
        let resolutionSource: String?
    }

    /// Decide 80-A (`#12274`): on a `GameMarketsResponse` row (`spreads`, `totals`, `other`),
    /// the market's resolution status is not served beside the row, so `OutcomeVerdict` is
    /// asked as for an open market (`marketResolved: false`): only an authoritative win
    /// becomes `.won`, and a row grade never mints `.lost`.
    nonisolated static func otherRowVerdict(
        isWinner: Bool?,
        resolutionSource: String?,
        finished: Bool
    ) -> OutcomeVerdict? {
        guard finished else { return nil }
        return OutcomeVerdict.verdict(
            isWinner: isWinner,
            resolutionSource: resolutionSource,
            marketResolved: false
        ) == .won ? .won : nil
    }

    // MARK: - Card Models

    nonisolated struct MatchOutlookCard: Identifiable, Equatable {
        let id: String
        let eventId: Int
        let marketId: Int
        let title: String
        let sportKind: SportKind
        let phase: FieldOutlookPhase10868
        let scoreSummary: String?
        let rows: [OutcomeRow]
        let headlineInput: FieldHeadlineInput10868
        let outlookInput: FieldOutlookInput10868?

        func current(at now: Date) -> MatchOutlookCard {
            guard phase != .final,
                  let rebuilt = EventAtlasRugbyAflCards11666.buildMatchOutlookCard(
                      eventId: eventId,
                      scoreSummary: scoreSummary,
                      rows: rows,
                      sportKind: sportKind,
                      phase: phase,
                      now: now
                  ) else {
                return self
            }
            return rebuilt
        }
    }

    nonisolated struct MarginOrTotalCard: Identifiable, Equatable {
        let id: String
        let eventId: Int
        let marketId: Int
        let title: String
        let sportKind: SportKind
        let phase: FieldOutlookPhase10868
        let scoreSummary: String?
        let rows: [OutcomeRow]
        let headlineInput: FieldHeadlineInput10868

        func current(at now: Date) -> MarginOrTotalCard {
            guard phase != .final,
                  let rebuilt = EventAtlasRugbyAflCards11666.buildMarginOrTotalCard(
                      eventId: eventId,
                      scoreSummary: scoreSummary,
                      marketId: marketId,
                      marketTitle: title,
                      rows: rows,
                      sportKind: sportKind,
                      phase: phase,
                      now: now
                  ) else {
                return self
            }
            return rebuilt
        }
    }

    nonisolated enum Card: Identifiable, Equatable {
        case matchOutlook(MatchOutlookCard)
        case marginOrTotal(MarginOrTotalCard)

        var id: String {
            switch self {
            case .matchOutlook(let card): return card.id
            case .marginOrTotal(let card): return card.id
            }
        }

        var marketId: Int {
            switch self {
            case .matchOutlook(let card): return card.marketId
            case .marginOrTotal(let card): return card.marketId
            }
        }

        var title: String {
            switch self {
            case .matchOutlook(let card): return card.title
            case .marginOrTotal(let card): return card.title
            }
        }

        func current(at now: Date) -> Card {
            switch self {
            case .matchOutlook(let card): return .matchOutlook(card.current(at: now))
            case .marginOrTotal(let card): return .marginOrTotal(card.current(at: now))
            }
        }
    }

    // MARK: - Phase & Staleness Resolution

    nonisolated static func resolvePhase(
        event: EventDetail,
        now: Date = Date()
    ) -> FieldOutlookPhase10868 {
        if EventState.isFinished(event.status) {
            return .final
        }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(
                event.status,
                commenceTime: event.commenceTime?.asDate,
                now: now
            ) {
            return .during
        }
        return .before
    }

    /// Decide 10-C chance resolution:
    /// - `.before`: Never uses `pregameMark`. Shows ONLY the live reading (`probability`) from the
    ///   last 30 minutes (`isStale ? nil : latest`), aged after 30 minutes to `nil`
    ///   (`"No recent probability"`).
    /// - `.during`: Uses `pregameMark` as the fixed `"Pre-match chance"` reference beside the
    ///   live reading (`isStale ? nil : latest`, aged after 30 minutes to `"No recent probability"`).
    /// - `.final`: Uses `pregameMark` as the fixed `"Pre-match chance"` reference.
    nonisolated static func resolveChances(
        probability: Double?,
        pregameMark: Double?,
        phase: FieldOutlookPhase10868,
        isStale: Bool
    ) -> (earlier: Double?, later: Double?) {
        let pregame = validProbability(pregameMark)
        let latest = validProbability(probability)
        switch phase {
        case .before:
            return (isStale ? nil : latest, nil)
        case .during:
            let current = isStale ? nil : latest
            return (pregame, current)
        case .final:
            return (pregame, nil)
        }
    }

    nonisolated static func validProbability(_ raw: Double?) -> Double? {
        guard let raw, raw.isFinite else { return nil }
        let unit = raw > 1.0 ? raw / 100.0 : raw
        guard unit >= 0.0, unit <= 1.0 else { return nil }
        return unit
    }

    nonisolated static func isQuoteStale(
        observedAt: Date?,
        now: Date,
        phase: FieldOutlookPhase10868
    ) -> Bool {
        guard phase != .final, let observedAt else { return false }
        return now.timeIntervalSince(observedAt) > staleThresholdSeconds
    }

    nonisolated static func formatPercent(_ probability: Double) -> String {
        "\(Int((probability * 100).rounded()))%"
    }

    // MARK: - Deck Builder

    static func buildCards(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date(),
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> [Card] {
        guard let sportKind = sportKind(sportKey: event.sport),
              atlasEnabled,
              let gm = gameMarkets,
              gm.eventId == event.id else {
            return []
        }

        let phase = resolvePhase(event: event, now: now)
        var cards: [Card] = []

        let winnerRows = extractWinnerOutcomeRows(event: event, gameMarkets: gm)
        if !winnerRows.isEmpty,
           let outlookCard = buildMatchOutlookCard(
               event: event,
               rows: winnerRows,
               sportKind: sportKind,
               phase: phase,
               now: now
           ) {
            cards.append(.matchOutlook(outlookCard))
        }

        let propGroups = extractPropGroups(gameMarkets: gm)
        for group in propGroups.prefix(2) {
            if let propCard = buildMarginOrTotalCard(
                event: event,
                marketId: group.marketId,
                marketTitle: group.title,
                rows: group.rows,
                sportKind: sportKind,
                phase: phase,
                now: now
            ) {
                cards.append(.marginOrTotal(propCard))
            }
        }

        return cards
    }

    // MARK: - Outcome & Prop Extraction from GameMarketsResponse

    nonisolated static func extractWinnerOutcomeRows(
        event: EventDetail,
        gameMarkets: GameMarketsResponse
    ) -> [OutcomeRow] {
        let homeName = event.homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        let awayName = event.awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !homeName.isEmpty, !awayName.isEmpty else { return [] }

        var byRole: [OutcomeRole: OutcomeRow] = [:]

        for row in gameMarkets.other ?? [] {
            guard let marketId = row._marketId ?? row._marketIds?.first else {
                continue
            }
            let marketLower = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if isMarginOrTotalName(marketLower) {
                continue
            }
            let outcomeRaw = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !outcomeRaw.isEmpty, outcomeRaw.lowercased() != "no" else {
                continue
            }
            guard let role = classifyOutcomeRole(
                text: "\(row.marketName) — \(outcomeRaw)",
                outcomeName: outcomeRaw,
                homeTeam: homeName,
                awayTeam: awayName
            ), byRole[role] == nil else {
                continue
            }

            let displayName: String = {
                switch role {
                case .home: return homeName
                case .away: return awayName
                case .draw: return "Draw"
                }
            }()

            byRole[role] = OutcomeRow(
                id: "winner-\(role.rawValue)-\(marketId)",
                marketID: marketId,
                marketTitle: row.marketName,
                outcomeName: displayName,
                role: role,
                probability: row.probability,
                pregameMark: row.pregameMark,
                source: row.source,
                observedAt: row.observedAt?.asDate,
                isWinner: row.isWinner,
                resolutionSource: row.resolutionSource
            )
        }

        let orderedRoles: [OutcomeRole] = [.home, .away, .draw]
        return orderedRoles.compactMap { byRole[$0] }
    }

    nonisolated private static func classifyOutcomeRole(
        text: String,
        outcomeName: String,
        homeTeam: String,
        awayTeam: String
    ) -> OutcomeRole? {
        let outLower = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let textLower = text.lowercased()
        if outLower == "draw"
            || outLower == "tie"
            || outLower == "the draw"
            || outLower.contains("draw")
            || outLower.contains("tie") {
            return .draw
        }
        let homeLower = homeTeam.lowercased()
        let awayLower = awayTeam.lowercased()
        let (awayShortRaw, homeShortRaw) = TeamShortName.shortPair(away: awayTeam, home: homeTeam)
        let homeShort = homeShortRaw.lowercased()
        let awayShort = awayShortRaw.lowercased()

        let matchesHome = outLower == homeLower
            || outLower == homeShort
            || (outLower.contains(homeLower) && !outLower.contains(awayLower))
            || (!homeShort.isEmpty && outLower.contains(homeShort) && !outLower.contains(awayShort))
        if matchesHome { return .home }

        let matchesAway = outLower == awayLower
            || outLower == awayShort
            || (outLower.contains(awayLower) && !outLower.contains(homeLower))
            || (!awayShort.isEmpty && outLower.contains(awayShort) && !outLower.contains(homeShort))
        if matchesAway { return .away }

        if textLower.contains(homeLower) && !textLower.contains(awayLower) {
            return .home
        }
        if textLower.contains(awayLower) && !textLower.contains(homeLower) {
            return .away
        }
        return nil
    }

    nonisolated private static func isMarginOrTotalName(_ lower: String) -> Bool {
        lower.contains("spread")
            || lower.contains("handicap")
            || lower.contains("line")
            || lower.contains("margin")
            || lower.contains("total")
            || lower.contains("over/under")
    }

    private struct PropGroup {
        let marketId: Int
        let title: String
        let rows: [OutcomeRow]
    }

    nonisolated private static func extractPropGroups(
        gameMarkets: GameMarketsResponse
    ) -> [PropGroup] {
        var groups: [PropGroup] = []

        if let spreads = gameMarkets.spreads, !spreads.isEmpty {
            let rows: [OutcomeRow] = spreads.prefix(4).enumerated().compactMap { idx, row in
                guard let rowMarketId = row._marketId ?? row._marketIds?.first else { return nil }
                let label: String = {
                    if let t = row.threshold {
                        let sign = t >= 0 ? "+" : ""
                        let formatted = t.truncatingRemainder(dividingBy: 1) == 0
                            ? "\(sign)\(Int(t))"
                            : String(format: "%@%.1f", sign, t)
                        return row.outcomeName.contains(formatted)
                            ? row.outcomeName
                            : "\(row.outcomeName) \(formatted)"
                    }
                    return row.outcomeName
                }()
                return OutcomeRow(
                    id: "spread-\(rowMarketId)-\(idx)",
                    marketID: rowMarketId,
                    marketTitle: row.marketName,
                    outcomeName: label,
                    role: nil,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }
            if let first = rows.first {
                groups.append(PropGroup(marketId: first.marketID, title: first.marketTitle, rows: rows))
            }
        }

        if let totals = gameMarkets.totals, !totals.isEmpty {
            let rows: [OutcomeRow] = totals.prefix(4).enumerated().compactMap { idx, row in
                guard let rowMarketId = row._marketId ?? row._marketIds?.first else { return nil }
                let label: String = {
                    if let t = row.threshold {
                        let formatted = t.truncatingRemainder(dividingBy: 1) == 0
                            ? "\(Int(t))"
                            : String(format: "%.1f", t)
                        return row.outcomeName.contains(formatted)
                            ? row.outcomeName
                            : "\(row.outcomeName) \(formatted)"
                    }
                    return row.outcomeName
                }()
                return OutcomeRow(
                    id: "total-\(rowMarketId)-\(idx)",
                    marketID: rowMarketId,
                    marketTitle: row.marketName,
                    outcomeName: label,
                    role: nil,
                    probability: row.overProbability ?? row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }
            if let first = rows.first {
                groups.append(PropGroup(marketId: first.marketID, title: first.marketTitle, rows: rows))
            }
        }

        if groups.isEmpty {
            let propOthers = (gameMarkets.other ?? []).filter {
                isMarginOrTotalName($0.marketName.lowercased())
            }
            let rows: [OutcomeRow] = propOthers.prefix(4).enumerated().compactMap { idx, row in
                guard let rowMarketId = row._marketId ?? row._marketIds?.first else { return nil }
                return OutcomeRow(
                    id: "other-prop-\(rowMarketId)-\(idx)",
                    marketID: rowMarketId,
                    marketTitle: row.marketName,
                    outcomeName: row.outcomeName,
                    role: nil,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }
            if let first = rows.first {
                groups.append(PropGroup(marketId: first.marketID, title: first.marketTitle, rows: rows))
            }
        }

        return groups
    }

    // MARK: - 1. Match Outlook Card Builder

    static func buildMatchOutlookCard(
        event: EventDetail,
        rows: [OutcomeRow],
        sportKind: SportKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> MatchOutlookCard? {
        buildMatchOutlookCard(
            eventId: event.id,
            scoreSummary: finalScoreSummary(event: event),
            rows: rows,
            sportKind: sportKind,
            phase: phase,
            now: now
        )
    }

    static func buildMatchOutlookCard(
        eventId: Int,
        scoreSummary: String?,
        rows: [OutcomeRow],
        sportKind: SportKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> MatchOutlookCard? {
        guard let first = rows.first else { return nil }
        let marketId = first.marketID
        let scope = "rugby-afl-outlook-\(eventId)-\(marketId)"
        let shapes: [FieldHeadlineKeyShape10868] = [.circle, .square, .diamond]

        let earlierLabel = phase == .before ? "Current chance" : "Pre-match chance"
        let laterLabel = "Live chance"

        var catalogue: [FieldChooserOriginal10868] = []
        var displayed: [FieldHeadlineSlot10868] = []
        var pairs: [FieldMovementPair10868] = []
        var finishes: [FieldFinishPlace10868] = []
        var outlookSlots: [FieldOutlookSlot10868] = []
        var outlookChances: [FieldOutlookBeforeChance10868] = []

        for (index, row) in rows.enumerated() {
            let ref = FieldChooserOriginalRef10868(
                scope: scope,
                source: "market",
                marketID: "\(marketId)",
                outcomeID: row.id
            )
            let isStale = isQuoteStale(observedAt: row.observedAt, now: now, phase: phase)
            let (earlierProb, laterProb) = resolveChances(
                probability: row.probability,
                pregameMark: row.pregameMark,
                phase: phase,
                isStale: isStale
            )

            let earlierDetail = readingDetailLine(
                observedAt: phase == .before ? row.observedAt : nil,
                source: row.source,
                fallback: phase == .before ? "Recorded quote" : "Pre-match quote"
            )
            let laterDetail = readingDetailLine(
                observedAt: row.observedAt,
                source: row.source,
                fallback: "Live quote"
            )

            let earlierReading: FieldChooserReading10868 = {
                if let p = earlierProb {
                    return FieldChooserReading10868(
                        label: earlierLabel,
                        value: .recorded(text: formatPercent(p), detail: earlierDetail)
                    )
                }
                let missingWords = phase == .before ? "No recent probability" : "Not recorded"
                return FieldChooserReading10868(
                    label: earlierLabel,
                    value: .missing(missingWords)
                )
            }()

            let laterReading: FieldChooserReading10868 = {
                if let p = laterProb {
                    return FieldChooserReading10868(
                        label: laterLabel,
                        value: .recorded(text: formatPercent(p), detail: laterDetail)
                    )
                }
                return FieldChooserReading10868(
                    label: laterLabel,
                    value: .missing("No recent probability")
                )
            }()

            let plan: FieldChooserDisplayPlan10868 = phase == .during
                ? .comparison(before: earlierReading, later: laterReading)
                : .single(earlierReading)

            catalogue.append(
                FieldChooserOriginal10868(
                    ref: ref,
                    name: row.outcomeName,
                    plan: plan,
                    preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
                    movement: nil,
                    clock: nil,
                    result: nil,
                    browseStatus: "Recorded history"
                )
            )

            let shortName = TeamShortName.short(row.outcomeName)
            let shape = shapes[index % shapes.count]
            displayed.append(
                FieldHeadlineSlot10868(
                    ref: ref,
                    name: row.outcomeName,
                    compactName: shortName == row.outcomeName ? nil : shortName,
                    keyShape: shape
                )
            )

            let beforeObs = earlierProb.map { p in
                FieldMovementObservation10868(
                    probability: p,
                    reading: earlierReading
                )
            }
            let laterObs = laterProb.map { p in
                FieldMovementObservation10868(
                    probability: p,
                    reading: laterReading
                )
            }

            pairs.append(
                FieldMovementPair10868(
                    ref: ref,
                    before: beforeObs,
                    later: laterObs,
                    movement: nil,
                    observation: laterObs != nil ? "obs-\(row.id)" : nil
                )
            )

            if phase == .final {
                let verdict = otherRowVerdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    finished: true
                )
                let finishDetail = scoreSummary ?? "Final score"
                let finishReading: FieldChooserReading10868 = {
                    if verdict == .won {
                        return FieldChooserReading10868(
                            label: "Contract result",
                            value: .recorded(text: "✓ Won", detail: finishDetail)
                        )
                    }
                    return FieldChooserReading10868(
                        label: "Contract result",
                        value: .missing("Result not confirmed")
                    )
                }()
                finishes.append(FieldFinishPlace10868(ref: ref, reading: finishReading))
            }

            outlookSlots.append(
                FieldOutlookSlot10868(
                    ref: ref,
                    label: row.outcomeName,
                    shortLabel: shortName
                )
            )

            let activeBarProb: Double? = {
                switch phase {
                case .before: return earlierProb
                case .during: return laterProb ?? earlierProb
                case .final: return earlierProb
                }
            }()
            let activeBarReading: FieldChooserReading10868 = phase == .during && laterProb != nil
                ? laterReading
                : earlierReading
            if let activeBarProb {
                outlookChances.append(
                    FieldOutlookBeforeChance10868(
                        ref: ref,
                        probability: activeBarProb,
                        reading: activeBarReading
                    )
                )
            }
        }

        let stateBlock = buildHeadlineState(scoreSummary: scoreSummary, sportKind: sportKind, phase: phase)
        let eyebrow = "\(sportKind.badgeTitle.uppercased()) · \(sportKind.matchTitle.uppercased())"
        let headlineCopy = FieldHeadlineCopy10868(
            eyebrow: eyebrow,
            title: first.marketTitle,
            graphicLabel: "\(sportKind.badgeTitle) match outcome probabilities",
            beforeLabel: earlierLabel,
            recordedLabel: laterLabel,
            beforeUnavailable: phase == .before ? "No recent probability" : "Not recorded",
            recordedUnavailable: "No recent probability",
            finishLabel: "Contract result",
            finishUnavailable: "Result not confirmed",
            empty: "No outcomes in this update",
            aboutLabel: "About this match",
            aboutHint: nil,
            openHint: nil
        )

        let headlineInput = FieldHeadlineInput10868(
            scope: scope,
            catalogue: catalogue,
            displayed: displayed,
            pairs: pairs,
            finishes: finishes,
            state: stateBlock,
            phase: phase,
            copy: headlineCopy,
            unavailableWords: "Outcome unavailable in this update"
        )

        let outlookInput: FieldOutlookInput10868? = {
            guard phase == .before else { return nil }
            let scale = FieldOutlookScale10868(
                ceiling: 1.0,
                ticks: [
                    FieldOutlookTick10868(probability: 0.25, label: "25%"),
                    FieldOutlookTick10868(probability: 0.50, label: "50%"),
                    FieldOutlookTick10868(probability: 0.75, label: "75%"),
                    FieldOutlookTick10868(probability: 1.00, label: "100%")
                ],
                words: "0–100% scale · raw outcome chances"
            )
            let copy = FieldOutlookCopy10868(
                title: sportKind == .rugby ? "3-way outcome comparison" : "Match win comparison",
                note: "Each bar shows that outcome's own recorded chance on a 0–100% scale.",
                graphicLabel: "Outcome win chance bars",
                missingChance: "No recent probability",
                offScale: "Above scale",
                outsideDisplayed: "Outside displayed outcomes",
                previousLabel: "Previous",
                nextLabel: "Next",
                details: "Details",
                detailsHint: nil,
                resultUnknown: "Result not confirmed"
            )
            return FieldOutlookInput10868(
                scope: scope,
                catalogue: catalogue,
                selected: nil,
                displayed: outlookSlots,
                traversal: outlookSlots.map(\.ref),
                chances: outlookChances,
                scale: scale,
                phase: .before,
                copy: copy,
                unavailableWords: "Outcome unavailable in this update",
                chooseHint: nil
            )
        }()

        return MatchOutlookCard(
            id: "rugby-afl-outlook-\(marketId)",
            eventId: eventId,
            marketId: marketId,
            title: first.marketTitle,
            sportKind: sportKind,
            phase: phase,
            scoreSummary: scoreSummary,
            rows: rows,
            headlineInput: headlineInput,
            outlookInput: outlookInput
        )
    }

    // MARK: - 2. Margin / Line & Total Points Card Builder

    static func buildMarginOrTotalCard(
        event: EventDetail,
        marketId: Int,
        marketTitle: String,
        rows: [OutcomeRow],
        sportKind: SportKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> MarginOrTotalCard? {
        buildMarginOrTotalCard(
            eventId: event.id,
            scoreSummary: finalScoreSummary(event: event),
            marketId: marketId,
            marketTitle: marketTitle,
            rows: rows,
            sportKind: sportKind,
            phase: phase,
            now: now
        )
    }

    static func buildMarginOrTotalCard(
        eventId: Int,
        scoreSummary: String?,
        marketId: Int,
        marketTitle: String,
        rows: [OutcomeRow],
        sportKind: SportKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> MarginOrTotalCard? {
        guard !rows.isEmpty else { return nil }
        let scope = "rugby-afl-prop-\(eventId)-\(marketId)"
        let shapes: [FieldHeadlineKeyShape10868] = [.circle, .square, .diamond]

        let earlierLabel = phase == .before ? "Current chance" : "Pre-match chance"
        let laterLabel = "Live chance"

        var catalogue: [FieldChooserOriginal10868] = []
        var displayed: [FieldHeadlineSlot10868] = []
        var pairs: [FieldMovementPair10868] = []
        var finishes: [FieldFinishPlace10868] = []

        for (index, row) in rows.prefix(4).enumerated() {
            let ref = FieldChooserOriginalRef10868(
                scope: scope,
                source: "market",
                marketID: "\(marketId)",
                outcomeID: row.id
            )
            let isStale = isQuoteStale(observedAt: row.observedAt, now: now, phase: phase)
            let (earlierProb, laterProb) = resolveChances(
                probability: row.probability,
                pregameMark: row.pregameMark,
                phase: phase,
                isStale: isStale
            )
            let earlierDetail = readingDetailLine(
                observedAt: phase == .before ? row.observedAt : nil,
                source: row.source,
                fallback: phase == .before ? "Recorded quote" : "Pre-match quote"
            )
            let laterDetail = readingDetailLine(
                observedAt: row.observedAt,
                source: row.source,
                fallback: "Live quote"
            )

            let earlierReading: FieldChooserReading10868 = {
                if let p = earlierProb {
                    return FieldChooserReading10868(
                        label: earlierLabel,
                        value: .recorded(text: formatPercent(p), detail: earlierDetail)
                    )
                }
                let missingWords = phase == .before ? "No recent probability" : "Not recorded"
                return FieldChooserReading10868(
                    label: earlierLabel,
                    value: .missing(missingWords)
                )
            }()

            let laterReading: FieldChooserReading10868 = {
                if let p = laterProb {
                    return FieldChooserReading10868(
                        label: laterLabel,
                        value: .recorded(text: formatPercent(p), detail: laterDetail)
                    )
                }
                return FieldChooserReading10868(
                    label: laterLabel,
                    value: .missing("No recent probability")
                )
            }()

            let plan: FieldChooserDisplayPlan10868 = phase == .during
                ? .comparison(before: earlierReading, later: laterReading)
                : .single(earlierReading)

            catalogue.append(
                FieldChooserOriginal10868(
                    ref: ref,
                    name: row.outcomeName,
                    plan: plan,
                    preview: FieldChooserPreview10868(history: nil, absence: "No captured history"),
                    movement: nil,
                    clock: nil,
                    result: nil,
                    browseStatus: "Recorded history"
                )
            )

            displayed.append(
                FieldHeadlineSlot10868(
                    ref: ref,
                    name: row.outcomeName,
                    compactName: nil,
                    keyShape: shapes[index % shapes.count]
                )
            )

            let beforeObs = earlierProb.map { p in
                FieldMovementObservation10868(
                    probability: p,
                    reading: earlierReading
                )
            }
            let laterObs = laterProb.map { p in
                FieldMovementObservation10868(
                    probability: p,
                    reading: laterReading
                )
            }

            pairs.append(
                FieldMovementPair10868(
                    ref: ref,
                    before: beforeObs,
                    later: laterObs,
                    movement: nil,
                    observation: laterObs != nil ? "obs-\(row.id)" : nil
                )
            )

            if phase == .final {
                let verdict = otherRowVerdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    finished: true
                )
                let finishDetail = scoreSummary ?? "Final score"
                let finishReading: FieldChooserReading10868 = {
                    if verdict == .won {
                        return FieldChooserReading10868(
                            label: "Contract result",
                            value: .recorded(text: "✓ Won", detail: finishDetail)
                        )
                    }
                    return FieldChooserReading10868(
                        label: "Contract result",
                        value: .missing("Result not confirmed")
                    )
                }()
                finishes.append(FieldFinishPlace10868(ref: ref, reading: finishReading))
            }
        }

        let propKindLabel: String = {
            let q = marketTitle.lowercased()
            if q.contains("total") || q.contains("over/under") {
                return "TOTAL POINTS"
            }
            return sportKind == .afl ? "LINE & MARGIN" : "HANDICAP & MARGIN"
        }()

        let headlineCopy = FieldHeadlineCopy10868(
            eyebrow: "\(sportKind.badgeTitle.uppercased()) · \(propKindLabel)",
            title: marketTitle,
            graphicLabel: marketTitle,
            beforeLabel: earlierLabel,
            recordedLabel: laterLabel,
            beforeUnavailable: phase == .before ? "No recent probability" : "Not recorded",
            recordedUnavailable: "No recent probability",
            finishLabel: "Contract result",
            finishUnavailable: "Result not confirmed",
            empty: "No lines in this update",
            aboutLabel: "About this line",
            aboutHint: nil,
            openHint: nil
        )

        let headlineInput = FieldHeadlineInput10868(
            scope: scope,
            catalogue: catalogue,
            displayed: displayed,
            pairs: pairs,
            finishes: finishes,
            state: nil,
            phase: phase,
            copy: headlineCopy,
            unavailableWords: "Line unavailable in this update"
        )

        return MarginOrTotalCard(
            id: "rugby-afl-prop-\(marketId)",
            eventId: eventId,
            marketId: marketId,
            title: marketTitle,
            sportKind: sportKind,
            phase: phase,
            scoreSummary: scoreSummary,
            rows: rows,
            headlineInput: headlineInput
        )
    }

    // MARK: - Formatting Helpers

    nonisolated static func finalScoreSummary(event: EventDetail) -> String? {
        guard let homeScore = event.homeScore, let awayScore = event.awayScore else {
            return nil
        }
        let (away, home) = TeamShortName.shortPair(away: event.awayTeam, home: event.homeTeam)
        return "\(home) \(homeScore)–\(awayScore) \(away)"
    }

    private nonisolated static func readingDetailLine(
        observedAt: Date?,
        source: String?,
        fallback: String
    ) -> String {
        let clockText = observedAt.map { date in
            date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
        }
        let sourceText = SourceLabels.label(for: source)
        let parts = [clockText, sourceText].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? fallback : parts.joined(separator: " · ")
    }

    private nonisolated static func buildHeadlineState(
        scoreSummary: String?,
        sportKind: SportKind,
        phase: FieldOutlookPhase10868
    ) -> FieldHeadlineState10868? {
        switch phase {
        case .before:
            return nil
        case .during:
            if let score = scoreSummary {
                return FieldHeadlineState10868(
                    figure: score,
                    unit: nil,
                    caption: "In play · \(sportKind.badgeTitle)",
                    detail: nil,
                    spoken: "In play, \(score)",
                    progress: nil
                )
            }
            return nil
        case .final:
            if let score = scoreSummary {
                return FieldHeadlineState10868(
                    figure: score,
                    unit: nil,
                    caption: "Final score",
                    detail: nil,
                    spoken: "Final score, \(score)",
                    progress: nil
                )
            }
            return FieldHeadlineState10868(
                figure: "Final",
                unit: nil,
                caption: "Final score",
                detail: "Result not confirmed",
                spoken: "Final score not confirmed",
                progress: nil
            )
        }
    }
}

// MARK: - SwiftUI Card Views

struct EventAtlasRugbyAflCardView11666: View {
    let card: EventAtlasRugbyAflCards11666.Card

    var body: some View {
        switch card {
        case .matchOutlook(let outlookCard):
            VStack(alignment: .leading, spacing: 16) {
                FieldPhaseHeadlinePresentation10868(input: outlookCard.headlineInput)
                if let outlookInput = outlookCard.outlookInput {
                    Divider()
                        .overlay(DS.border)
                    FieldOutlookBarsPresentation10868(input: outlookInput)
                }
            }
            .padding(16)
            .background(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .fill(DS.cardBg)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 16, style: .continuous)
                    .strokeBorder(DS.border, lineWidth: 1)
            )
            .accessibilityIdentifier("eventAtlas.rugbyAfl.matchOutlook.\(outlookCard.marketId)")

        case .marginOrTotal(let propCard):
            FieldPhaseHeadlinePresentation10868(input: propCard.headlineInput)
                .padding(16)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(DS.cardBg)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(DS.border, lineWidth: 1)
                )
                .accessibilityIdentifier("eventAtlas.rugbyAfl.prop.\(propCard.marketId)")
        }
    }
}
