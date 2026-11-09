import Foundation
import SwiftUI

/// #11666 / #10868 — Event Atlas Cricket Story Cards (Menu Item 16b).
///
/// Surfaces native story cards on Cricket event pages (`cricket_international_t20`,
/// `cricket_t20`, `cricket_ipl`, `cricket_odi`, `cricket_test_match`, etc.) when
/// `ReleaseSurfaces.eventPageSportsAtlasEnabled` is on:
///
/// 1. **Pregame Outlook (`CricketPregameStoryPresentation10868`)**: Before the first
///    ball (`.before`), displays each original outcome contract (Home, Away, and
///    Draw / Tie when offered) with its independent 0–100% probability rail.
///    Readings older than 30 minutes are withheld as `"No recent probability"`
///    (never `"Pregame chance unavailable"` when a reading existed and aged out).
/// 2. **Outlook Shift & Final Expectations (`CricketOutlookPresentation10868`)**:
///    During play (`.during`), pairs each outcome's fixed pregame baseline mark
///    beside its live reading (aged after 30 minutes to `"No recent probability"`)
///    and whole-point movement (`↑ N points` / `↓ N points` / `No change`).
///    At the final (`.final`), shows each outcome's pregame expectation beside its
///    venue-confirmed match result (`✓ Won`, `✗ Lost`, `No draw / tie`, or
///    `"Result not confirmed"` when unsettled — never fabricating `"Lost"`).
/// 3. **The Chase (`CricketChasePresentation10868`)**: During play and at the final,
///    when `GameMarketsResponse` carries an innings run-chase or team/match run-total
///    target market, pairs the pregame baseline with the live or settled target
///    chance and any reported run-target threshold.
enum EventAtlasCricketCards11666 {

    nonisolated static let liveQuoteMaxAgeSeconds: TimeInterval = 30 * 60

    // MARK: - Sport & Format Gating

    nonisolated enum Format: String, Equatable, Sendable {
        case t20
        case odi
        case test

        var maxOversPerInnings: Int? {
            switch self {
            case .t20: return 20
            case .odi: return 50
            case .test: return nil
            }
        }

        var maxBallsPerInnings: Int? {
            maxOversPerInnings.map { $0 * 6 }
        }
    }

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        guard atlasEnabled, let raw = sportKey?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return false
        }
        let lower = raw.lowercased()
        return lower == "cricket" || lower.hasPrefix("cricket_")
    }

    nonisolated static func resolveFormat(sportKey: String?, event: EventDetail? = nil) -> Format {
        let lower = (sportKey ?? event?.sport ?? "").lowercased()
        if lower.contains("test") {
            return .test
        }
        if lower.contains("odi") || lower.contains("one_day") || lower.contains("world_cup_odi") {
            return .odi
        }
        return .t20
    }

    // MARK: - Lifecycle Phase

    nonisolated enum Phase: String, Equatable, Sendable {
        case before
        case during
        case final

        var headlinePhase: CricketHeadlinePhase10868 {
            switch self {
            case .before: return .before
            case .during: return .during
            case .final: return .completed
            }
        }

        var chasePhase: CricketChasePhase10868 {
            switch self {
            case .before: return .before
            case .during: return .during
            case .final: return .final
            }
        }
    }

    nonisolated static func resolvePhase(event: EventDetail, now: Date) -> Phase {
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

    // MARK: - 1. Outcome Row Record (Shared by Pregame & Outlook Cards)

    nonisolated enum OutcomeRole: String, Equatable, Sendable {
        case home
        case away
        case draw

        var shape: CricketOutlookShape10868 {
            switch self {
            case .home: return .circle
            case .away: return .diamond
            case .draw: return .square
            }
        }
    }

    nonisolated struct OutcomeRowRecord: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: String
        let subject: String
        let role: OutcomeRole
        let beforeChance: Double?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date, phase: Phase) -> OutcomeRowRecord {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasCricketCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard beforeChance != nil || currentChance != nil || !isStaleLive else { return self }
                return OutcomeRowRecord(
                    id: id,
                    marketID: marketID,
                    subject: subject,
                    role: role,
                    beforeChance: nil,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .during:
                guard currentChance != nil || !isStaleLive else { return self }
                return OutcomeRowRecord(
                    id: id,
                    marketID: marketID,
                    subject: subject,
                    role: role,
                    beforeChance: beforeChance,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .final:
                return self
            }
        }

        func toOutlookRow(
            eventID: String,
            phase: Phase,
            homeTint: Color,
            awayTint: Color,
            now: Date
        ) -> CricketOutlookRow10868 {
            let tint: Color = {
                switch role {
                case .home: return homeTint
                case .away: return awayTint
                case .draw: return DS.textSecondary
                }
            }()
            let provenance = EventAtlasCricketCards11666.formatSourceDetail(
                rawSource: rawSource,
                sourceCount: sourceCount,
                observedAt: observedAt,
                isStaleLive: isStaleLive,
                phase: phase,
                now: now
            )

            let beforeDetail = phase == .before
                ? provenance
                : EventAtlasCricketCards11666.formatPregameSourceDetail(
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )

            let beforeReading: CricketOutlookReading10868 = {
                if phase == .before && isStaleLive {
                    return .withheld("No recent probability")
                }
                if let beforeChance {
                    return .observed(
                        CricketOutlookObservation10868(
                            probability: beforeChance,
                            text: EventAtlasCricketCards11666.formatPercent(beforeChance),
                            detail: beforeDetail
                        )
                    )
                }
                let missingWords = role == .draw
                    ? "Draw chance unavailable"
                    : "No pregame chance recorded"
                return .unavailable(missingWords)
            }()

            let comparisonReading: CricketOutlookReading10868 = {
                if phase == .during && isStaleLive {
                    return .withheld("No recent probability")
                }
                if let currentChance {
                    return .observed(
                        CricketOutlookObservation10868(
                            probability: currentChance,
                            text: EventAtlasCricketCards11666.formatPercent(currentChance),
                            detail: provenance
                        )
                    )
                }
                return .unavailable("No in-play probability")
            }()

            let movement: CricketOutlookMovement10868? = {
                guard phase == .during, !isStaleLive,
                      let beforeChance, let currentChance else {
                    return nil
                }
                return EventAtlasCricketCards11666.formatOutlookMovement(
                    before: beforeChance,
                    current: currentChance
                )
            }()

            let finish: CricketOutlookFinish10868? = {
                guard phase == .final else { return nil }
                let outcomeEntry: CricketOutlookFinalEntry10868 = {
                    switch verdict {
                    case .won:
                        return .admitted(
                            CricketOutlookFinalWord10868(
                                text: "✓ Won",
                                symbolName: "checkmark.circle.fill",
                                detail: provenance
                            )
                        )
                    case .lost:
                        let lostText = role == .draw ? "No draw / tie" : "✗ Lost"
                        return .admitted(
                            CricketOutlookFinalWord10868(
                                text: lostText,
                                symbolName: "xmark.circle",
                                detail: provenance
                            )
                        )
                    case .none:
                        return .unavailable("Result not confirmed")
                    }
                }()
                return CricketOutlookFinish10868(outcome: outcomeEntry, grade: nil)
            }()

            let ref = CricketOutlookRef10868(
                event: eventID,
                market: marketID,
                outcome: id
            )

            return CricketOutlookRow10868(
                id: id,
                subject: subject,
                shape: role.shape,
                tint: tint,
                ref: ref,
                before: beforeReading,
                comparison: comparisonReading,
                movement: movement,
                finish: finish
            )
        }
    }

    // MARK: - 2. Pregame Story Card (`.before`)

    nonisolated struct PregameCard: Equatable, Identifiable, Sendable {
        static let cardID = "cricket:pregame"
        var id: String { Self.cardID }
        var title: String { "Pregame outlook" }
        let eventID: String
        let format: Format
        let phase: Phase
        let homeTeam: String
        let awayTeam: String
        let homeColorHex: String?
        let awayColorHex: String?
        let rows: [OutcomeRowRecord]

        func current(at now: Date) -> PregameCard {
            guard phase != .final else { return self }
            return PregameCard(
                eventID: eventID,
                format: format,
                phase: phase,
                homeTeam: homeTeam,
                awayTeam: awayTeam,
                homeColorHex: homeColorHex,
                awayColorHex: awayColorHex,
                rows: rows.map { $0.current(at: now, phase: phase) }
            )
        }

        func presentationInput(now: Date) -> CricketPregameStoryInput10868 {
            let aged = current(at: now)
            let tints = TeamTextContrast.cardColors(awayHex: aged.awayColorHex, homeHex: aged.homeColorHex)
            let outlookRows = aged.rows.map {
                $0.toOutlookRow(
                    eventID: aged.eventID,
                    phase: aged.phase,
                    homeTint: tints.home,
                    awayTint: tints.away,
                    now: now
                )
            }
            return CricketPregameStoryInput10868(
                phase: aged.phase.headlinePhase,
                eyebrow: "Before the first ball",
                title: aged.title,
                beforeLabel: "Pregame chance to win",
                rows: outlookRows,
                notes: ["Each chance is its own reading; they are not adjusted to add up to 100%."]
            )
        }
    }

    // MARK: - 3. Outlook Shift & Final Expectations Card (`.during` / `.final`)

    nonisolated struct OutlookCard: Equatable, Identifiable, Sendable {
        static let cardID = "cricket:outlook"
        var id: String { Self.cardID }
        let eventID: String
        let format: Format
        let phase: Phase
        let homeTeam: String
        let awayTeam: String
        let homeColorHex: String?
        let awayColorHex: String?
        let rows: [OutcomeRowRecord]
        let finalScoreSummary: String?

        var title: String {
            phase == .final ? "Pregame expectations vs result" : "How the outlook changed"
        }

        func current(at now: Date) -> OutlookCard {
            guard phase != .final else { return self }
            return OutlookCard(
                eventID: eventID,
                format: format,
                phase: phase,
                homeTeam: homeTeam,
                awayTeam: awayTeam,
                homeColorHex: homeColorHex,
                awayColorHex: awayColorHex,
                rows: rows.map { $0.current(at: now, phase: phase) },
                finalScoreSummary: finalScoreSummary
            )
        }

        func presentationInput(selectedRowID: String?, now: Date) -> CricketOutlookInput10868 {
            let aged = current(at: now)
            let tints = TeamTextContrast.cardColors(awayHex: aged.awayColorHex, homeHex: aged.homeColorHex)
            let outlookRows = aged.rows.map {
                $0.toOutlookRow(
                    eventID: aged.eventID,
                    phase: aged.phase,
                    homeTint: tints.home,
                    awayTint: tints.away,
                    now: now
                )
            }

            if aged.phase == .final {
                let contextLines = aged.finalScoreSummary.map { [$0] } ?? []
                let frame = CricketOutlookFinalFrame10868(
                    outcomeLabel: "Match",
                    outcomeMissing: "Result not confirmed",
                    gradeLabel: "Original contract",
                    context: contextLines
                )
                return CricketOutlookInput10868(
                    eyebrow: "Pregame expectations → result",
                    title: aged.title,
                    beforeLabel: "Pregame",
                    comparisonLabel: "Current",
                    rows: outlookRows,
                    selectedRowID: selectedRowID,
                    notes: ["Hollow marks are pregame chances. Result labels describe the match, not later chances."],
                    mode: .completed(frame)
                )
            }

            let anyStale = aged.rows.contains(where: \.isStaleLive)
            let eyebrow = anyStale ? "Pregame → last recorded chance" : "Pregame → current chance"
            return CricketOutlookInput10868(
                eyebrow: eyebrow,
                title: aged.title,
                beforeLabel: "Pregame",
                comparisonLabel: "Current",
                rows: outlookRows,
                selectedRowID: selectedRowID,
                notes: ["Changes are percentage points, not runs or wickets."],
                mode: .comparison
            )
        }
    }

    // MARK: - 4. The Chase Card (`CricketChasePresentation10868`)

    nonisolated struct ChaseCard: Equatable, Identifiable, Sendable {
        static let cardID = "cricket:chase"
        var id: String { Self.cardID }
        var title: String { "The chase" }
        let eventID: String
        let marketID: String
        let outcomeID: String
        let format: Format
        let phase: Phase
        let battingSubject: String
        let eyebrow: String
        let headline: String?
        let targetRuns: Double?
        let currentRuns: Double?
        let beforeChance: Double?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int
        let homeColorHex: String?
        let awayColorHex: String?

        func current(at now: Date) -> ChaseCard {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasCricketCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard beforeChance != nil || currentChance != nil || !isStaleLive else { return self }
                return ChaseCard(
                    eventID: eventID,
                    marketID: marketID,
                    outcomeID: outcomeID,
                    format: format,
                    phase: phase,
                    battingSubject: battingSubject,
                    eyebrow: eyebrow,
                    headline: headline,
                    targetRuns: targetRuns,
                    currentRuns: currentRuns,
                    beforeChance: nil,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount,
                    homeColorHex: homeColorHex,
                    awayColorHex: awayColorHex
                )
            case .during:
                guard currentChance != nil || !isStaleLive else { return self }
                return ChaseCard(
                    eventID: eventID,
                    marketID: marketID,
                    outcomeID: outcomeID,
                    format: format,
                    phase: phase,
                    battingSubject: battingSubject,
                    eyebrow: eyebrow,
                    headline: headline,
                    targetRuns: targetRuns,
                    currentRuns: currentRuns,
                    beforeChance: beforeChance,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount,
                    homeColorHex: homeColorHex,
                    awayColorHex: awayColorHex
                )
            case .final:
                return self
            }
        }

        func presentationInput(now: Date) -> CricketChaseInput10868 {
            let aged = current(at: now)
            let provenance = EventAtlasCricketCards11666.formatSourceDetail(
                rawSource: aged.rawSource,
                sourceCount: aged.sourceCount,
                observedAt: aged.observedAt,
                isStaleLive: aged.isStaleLive,
                phase: aged.phase,
                now: now
            )

            let pregameDetail = aged.phase == .before
                ? provenance
                : EventAtlasCricketCards11666.formatPregameSourceDetail(
                    rawSource: aged.rawSource,
                    sourceCount: aged.sourceCount
                )

            let pregameReading: CricketChaseReading10868 = {
                if aged.phase == .before && aged.isStaleLive {
                    return .withheld("No recent probability")
                }
                if let before = aged.beforeChance {
                    return .observed(
                        CricketChaseFigure10868(
                            text: EventAtlasCricketCards11666.formatPercent(before),
                            detail: pregameDetail
                        )
                    )
                }
                return .unavailable("No pregame chance recorded")
            }()

            let comparisonReading: CricketChaseReading10868 = {
                if aged.isStaleLive {
                    return .withheld("No recent probability")
                }
                if let current = aged.currentChance {
                    return .observed(
                        CricketChaseFigure10868(
                            text: EventAtlasCricketCards11666.formatPercent(current),
                            detail: provenance
                        )
                    )
                }
                return .unavailable("Current probability unavailable")
            }()

            let contractResult: CricketChaseContractResult10868 = {
                switch aged.verdict {
                case .won:
                    return .graded(CricketChaseFigure10868(text: "✓ Won", detail: provenance))
                case .lost:
                    return .graded(CricketChaseFigure10868(text: "✗ Lost", detail: provenance))
                case .none:
                    return .unconfirmed("Result not confirmed")
                }
            }()

            let matchResult: CricketChaseMatchResult10868 = {
                switch aged.verdict {
                case .won:
                    return .reported(
                        CricketChaseFigure10868(
                            text: "\(aged.battingSubject) reached target",
                            detail: provenance
                        )
                    )
                case .lost:
                    return .reported(
                        CricketChaseFigure10868(
                            text: "\(aged.battingSubject) fell short of target",
                            detail: provenance
                        )
                    )
                case .none:
                    return .unavailable("Result not confirmed")
                }
            }()

            let actualState: CricketChaseActual10868 = {
                guard let target = aged.targetRuns else {
                    return .unavailable("Live innings score not reported")
                }
                let targetInt = Int(target.rounded())
                let runsQty: CricketChaseQuantity10868 = {
                    if let currentRuns = aged.currentRuns {
                        let runsInt = Int(currentRuns.rounded())
                        return .reported(text: "\(runsInt)", value: Double(runsInt))
                    }
                    return .unknown("Innings runs not reported")
                }()
                return .reported(
                    CricketChaseState10868(
                        battingSubject: aged.battingSubject,
                        context: nil,
                        runs: runsQty,
                        runsCaption: "runs scored",
                        target: .reported(text: "\(targetInt)", value: Double(targetInt)),
                        targetCaption: "runs",
                        wickets: [],
                        wicketsText: "Wickets not reported",
                        oversText: "Overs not reported",
                        reportDetail: provenance
                    )
                )
            }()

            let ref = CricketChaseRef10868(
                event: aged.eventID,
                market: aged.marketID,
                outcome: aged.outcomeID
            )

            return CricketChaseInput10868(
                phase: aged.phase.chasePhase,
                subject: aged.battingSubject,
                eyebrow: aged.eyebrow,
                headline: aged.headline,
                pregameLabel: "Pregame",
                pregame: pregameReading,
                comparisonLabel: "Current win chance",
                comparison: comparisonReading,
                resultLabel: "Final",
                contractResult: contractResult,
                matchResult: matchResult,
                actual: actualState,
                detailsRef: ref,
                notes: ["Target to win is a contract threshold, not a projected finish."]
            )
        }
    }

    // MARK: - Unified Cricket Story Card Enum

    nonisolated enum Card: Equatable, Identifiable, Sendable {
        case pregame(PregameCard)
        case outlook(OutlookCard)
        case chase(ChaseCard)

        var id: String {
            switch self {
            case .pregame(let c): return c.id
            case .outlook(let c): return c.id
            case .chase(let c): return c.id
            }
        }

        var title: String {
            switch self {
            case .pregame(let c): return c.title
            case .outlook(let c): return c.title
            case .chase(let c): return c.title
            }
        }

        func current(at now: Date) -> Card {
            switch self {
            case .pregame(let c): return .pregame(c.current(at: now))
            case .outlook(let c): return .outlook(c.current(at: now))
            case .chase(let c): return .chase(c.current(at: now))
            }
        }
    }

    // MARK: - Normalization & Card Construction

    static func buildCards(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date(),
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> [Card] {
        guard applies(sportKey: event.sport, atlasEnabled: atlasEnabled),
              let gameMarkets else {
            return []
        }

        let phase = resolvePhase(event: event, now: now)
        let format = resolveFormat(sportKey: event.sport, event: event)
        let outcomeRows = extractOutcomeRows(event: event, gameMarkets: gameMarkets, phase: phase, now: now)
        let chaseCard = buildChaseCard(event: event, gameMarkets: gameMarkets, format: format, phase: phase, now: now)

        var cards: [Card] = []
        switch phase {
        case .before:
            if !outcomeRows.isEmpty {
                cards.append(
                    .pregame(
                        PregameCard(
                            eventID: String(event.id),
                            format: format,
                            phase: phase,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeColorHex: event.homeTeamData?.primaryColor,
                            awayColorHex: event.awayTeamData?.primaryColor,
                            rows: outcomeRows
                        )
                    )
                )
            }
            if let chaseCard {
                cards.append(.chase(chaseCard))
            }
        case .during, .final:
            if !outcomeRows.isEmpty {
                let finalSummary: String? = {
                    guard phase == .final,
                          let hScore = event.homeScore,
                          let aScore = event.awayScore else {
                        return nil
                    }
                    return "\(event.homeTeam) \(hScore) · \(event.awayTeam) \(aScore)"
                }()
                cards.append(
                    .outlook(
                        OutlookCard(
                            eventID: String(event.id),
                            format: format,
                            phase: phase,
                            homeTeam: event.homeTeam,
                            awayTeam: event.awayTeam,
                            homeColorHex: event.homeTeamData?.primaryColor,
                            awayColorHex: event.awayTeamData?.primaryColor,
                            rows: outcomeRows,
                            finalScoreSummary: finalSummary
                        )
                    )
                )
            }
            if let chaseCard {
                cards.append(.chase(chaseCard))
            }
        }
        return cards
    }

    // MARK: - Outcome Row Extraction

    private nonisolated static func extractOutcomeRows(
        event: EventDetail,
        gameMarkets: GameMarketsResponse,
        phase: Phase,
        now: Date
    ) -> [OutcomeRowRecord] {
        let homeName = event.homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        let awayName = event.awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !homeName.isEmpty, !awayName.isEmpty else { return [] }

        struct CandidateOutcome {
            let marketID: String
            let role: OutcomeRole
            let beforeChance: Double?
            let currentChance: Double?
            let observedAt: Date?
            let verdict: OutcomeVerdict?
            let rawSource: String?
            let sourceCount: Int
        }

        var byRole: [OutcomeRole: CandidateOutcome] = [:]

        for row in gameMarkets.other ?? [] {
            let marketLower = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard isMatchOutcomeMarketName(marketLower) else { continue }
            let outcomeRaw = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !outcomeRaw.isEmpty else {
                continue
            }
            if outcomeRaw.lowercased() == "no" { continue }

            guard let role = classifyOutcomeRole(
                text: "\(row.marketName) — \(outcomeRaw)",
                outcomeName: outcomeRaw,
                homeTeam: homeName,
                awayTeam: awayName
            ) else {
                continue
            }
            guard byRole[role] == nil else { continue }

            let (beforeVal, currentVal) = resolveChances(
                probability: row.probability,
                pregameMark: row.pregameMark,
                phase: phase
            )
            let verdict: OutcomeVerdict? = phase == .final
                ? OutcomeVerdict.verdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    marketResolved: true
                )
                : nil
            let marketIDValue = row._marketId ?? row._marketIds?.first ?? 0

            byRole[role] = CandidateOutcome(
                marketID: String(marketIDValue),
                role: role,
                beforeChance: beforeVal,
                currentChance: currentVal,
                observedAt: row.observedAt?.asDate,
                verdict: verdict,
                rawSource: row.source,
                sourceCount: 1
            )
        }

        guard !byRole.isEmpty else { return [] }

        let orderedRoles: [OutcomeRole] = [.home, .away, .draw]
        var records: [OutcomeRowRecord] = []
        for role in orderedRoles {
            guard let item = byRole[role] else { continue }
            let subject: String = {
                switch role {
                case .home: return homeName
                case .away: return awayName
                case .draw: return "Draw / tie"
                }
            }()
            let record = OutcomeRowRecord(
                id: "cricket-outcome-\(role.rawValue)",
                marketID: item.marketID,
                subject: subject,
                role: role,
                beforeChance: item.beforeChance,
                currentChance: item.currentChance,
                observedAt: item.observedAt,
                isStaleLive: false,
                verdict: item.verdict,
                rawSource: item.rawSource,
                sourceCount: item.sourceCount
            ).current(at: now, phase: phase)
            records.append(record)
        }
        return records
    }

    private nonisolated static func isMatchOutcomeMarketName(_ lower: String) -> Bool {
        if lower.contains("method")
            || lower.contains("round")
            || lower.contains("total")
            || lower.contains("over/under")
            || lower.contains("runs")
            || lower.contains("chase")
            || lower.contains("top batter")
            || lower.contains("top bowler")
            || lower.contains("toss") {
            return false
        }
        return lower.contains("winner")
            || lower.contains("match result")
            || lower.contains("match odds")
            || lower.contains("moneyline")
            || lower.contains("head to head")
            || lower.contains("outight")
            || lower.contains("who will win")
            || lower.contains("draw")
            || lower.contains("tie")
    }

    private nonisolated static func classifyOutcomeRole(
        text: String,
        outcomeName: String,
        homeTeam: String,
        awayTeam: String
    ) -> OutcomeRole? {
        let outLower = outcomeName.lowercased()
        if outLower == "draw"
            || outLower == "tie"
            || outLower == "draw / tie"
            || outLower == "the draw"
            || outLower.contains("match drawn") {
            return .draw
        }

        let homeLower = homeTeam.lowercased()
        let awayLower = awayTeam.lowercased()
        let cricketSport = "cricket_international_t20"
        let pair = TeamShortName.shortPair(
            away: awayTeam,
            home: homeTeam,
            sportKey: cricketSport
        )
        let homeShort = pair.home.lowercased()
        let awayShort = pair.away.lowercased()

        let outMatchesHome = outLower.contains(homeLower) || (homeShort.count >= 3 && outLower.contains(homeShort))
        let outMatchesAway = outLower.contains(awayLower) || (awayShort.count >= 3 && outLower.contains(awayShort))
        if outMatchesHome && !outMatchesAway { return .home }
        if outMatchesAway && !outMatchesHome { return .away }

        let fullLower = text.lowercased()
        if fullLower.contains("draw") || fullLower.contains("tie") {
            if outLower == "yes" { return .draw }
        }
        let fullMatchesHome = fullLower.contains(homeLower) || (homeShort.count >= 3 && fullLower.contains(homeShort))
        let fullMatchesAway = fullLower.contains(awayLower) || (awayShort.count >= 3 && fullLower.contains(awayShort))
        if fullMatchesHome && !fullMatchesAway { return .home }
        if fullMatchesAway && !fullMatchesHome { return .away }

        return nil
    }

    // MARK: - Chase Card Builder

    private nonisolated static func buildChaseCard(
        event: EventDetail,
        gameMarkets: GameMarketsResponse,
        format: Format,
        phase: Phase,
        now: Date
    ) -> ChaseCard? {
        let homeName = event.homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        let awayName = event.awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)

        // 1. Check `teamTotals` or `totals` for a team-attributed runs target / over threshold
        let totalCandidates = (gameMarkets.teamTotals ?? []) + (gameMarkets.totals ?? [])
        for row in totalCandidates {
            let outLower = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let isUnder = outLower.hasPrefix("under") || outLower == "u"
            let isOver = outLower.hasPrefix("over") || outLower == "o" || !isUnder
            guard isOver else { continue }
            guard let threshold = row.threshold, threshold >= 50 else { continue }
            guard let battingSubject = resolveBattingSubject(
                marketName: row.marketName,
                outcomeName: row.outcomeName,
                homeTeam: homeName,
                awayTeam: awayName
            ) else {
                continue
            }

            let prob: Double? = {
                if let explicit = row.probability { return explicit }
                guard let overProb = row.overProbability else { return nil }
                return isUnder ? max(0.0, min(1.0, 1.0 - overProb)) : overProb
            }()
            let pregame: Double? = {
                guard let mark = row.pregameMark else { return nil }
                if row.probability == nil, row.overProbability != nil, isUnder {
                    return max(0.0, min(1.0, 1.0 - mark))
                }
                return mark
            }()
            let (beforeVal, currentVal) = resolveChances(
                probability: prob,
                pregameMark: pregame,
                phase: phase
            )
            let verdict: OutcomeVerdict? = phase == .final
                ? OutcomeVerdict.verdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    marketResolved: true
                )
                : nil

            let targetInt = Int(threshold.rounded())
            let headline: String? = phase == .during ? "Target \(targetInt) runs" : nil
            let eyebrow: String = {
                switch phase {
                case .before: return "\(battingSubject) · runs target"
                case .during: return "\(battingSubject) · innings chase"
                case .final: return "The chase · final"
                }
            }()
            let marketIDValue = row._marketId ?? row._marketIds?.first ?? 0

            return ChaseCard(
                eventID: String(event.id),
                marketID: String(marketIDValue),
                outcomeID: "chase-\(marketIDValue)",
                format: format,
                phase: phase,
                battingSubject: battingSubject,
                eyebrow: eyebrow,
                headline: headline,
                targetRuns: Double(targetInt),
                currentRuns: nil,
                beforeChance: beforeVal,
                currentChance: currentVal,
                observedAt: row.observedAt?.asDate,
                isStaleLive: false,
                verdict: verdict,
                rawSource: row.source,
                sourceCount: 1,
                homeColorHex: event.homeTeamData?.primaryColor,
                awayColorHex: event.awayTeamData?.primaryColor
            ).current(at: now)
        }

        // 2. Check `other` for an explicit chase / innings runs target market
        for row in gameMarkets.other ?? [] {
            let marketName = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            let marketLower = marketName.lowercased()
            guard marketLower.contains("chase")
                || marketLower.contains("target")
                || marketLower.contains("innings runs")
                || marketLower.contains("total runs") else {
                continue
            }
            let outcomeName = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
            if outcomeName.lowercased() == "no" || outcomeName.lowercased().hasPrefix("under") {
                continue
            }
            guard let battingSubject = resolveBattingSubject(
                marketName: marketName,
                outcomeName: outcomeName,
                homeTeam: homeName,
                awayTeam: awayName
            ) else {
                continue
            }

            let targetRuns = extractRunsThreshold(from: "\(marketName) \(outcomeName)")
            let (beforeVal, currentVal) = resolveChances(
                probability: row.probability,
                pregameMark: row.pregameMark,
                phase: phase
            )
            let verdict: OutcomeVerdict? = phase == .final
                ? OutcomeVerdict.verdict(
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    marketResolved: true
                )
                : nil
            let headline: String? = {
                guard phase == .during else { return nil }
                if let targetRuns {
                    let targetInt = Int(targetRuns.rounded())
                    return "Target \(targetInt) runs"
                }
                return "\(battingSubject) run chase"
            }()
            let eyebrow: String = {
                switch phase {
                case .before: return "\(battingSubject) · runs target"
                case .during: return "\(battingSubject) · second innings"
                case .final: return "The chase · final"
                }
            }()
            let marketIDValue = row._marketId ?? row._marketIds?.first ?? 0

            return ChaseCard(
                eventID: String(event.id),
                marketID: String(marketIDValue),
                outcomeID: "chase-\(marketIDValue)",
                format: format,
                phase: phase,
                battingSubject: battingSubject,
                eyebrow: eyebrow,
                headline: headline,
                targetRuns: targetRuns,
                currentRuns: nil,
                beforeChance: beforeVal,
                currentChance: currentVal,
                observedAt: row.observedAt?.asDate,
                isStaleLive: false,
                verdict: verdict,
                rawSource: row.source,
                sourceCount: 1,
                homeColorHex: event.homeTeamData?.primaryColor,
                awayColorHex: event.awayTeamData?.primaryColor
            ).current(at: now)
        }

        return nil
    }

    private nonisolated static func resolveBattingSubject(
        marketName: String,
        outcomeName: String,
        homeTeam: String,
        awayTeam: String
    ) -> String? {
        let combined = "\(marketName) \(outcomeName)".lowercased()
        let homeLower = homeTeam.lowercased()
        let awayLower = awayTeam.lowercased()
        let cricketSport = "cricket_international_t20"
        let pair = TeamShortName.shortPair(
            away: awayTeam,
            home: homeTeam,
            sportKey: cricketSport
        )
        let homeShort = pair.home.lowercased()
        let awayShort = pair.away.lowercased()

        let matchesAway = combined.contains(awayLower) || (awayShort.count >= 3 && combined.contains(awayShort))
        let matchesHome = combined.contains(homeLower) || (homeShort.count >= 3 && combined.contains(homeShort))
        if matchesAway && !matchesHome {
            return awayTeam
        }
        if matchesHome && !matchesAway {
            return homeTeam
        }
        return nil
    }

    private nonisolated static func extractRunsThreshold(from text: String) -> Double? {
        let pattern = #"(\d{2,3}(?:\.\d+)?)\s*(?:runs?|\+)"#
        if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) {
            let nsRange = NSRange(text.startIndex..<text.endIndex, in: text)
            if let match = regex.firstMatch(in: text, range: nsRange),
               match.numberOfRanges > 1,
               let range = Range(match.range(at: 1), in: text),
               let value = Double(text[range]), value >= 40, value <= 999 {
                return value
            }
        }
        return nil
    }

    // MARK: - Formatting & Chance Helpers

    private nonisolated static func normalizeUnitProbability(_ raw: Double?) -> Double? {
        guard let raw, raw.isFinite else { return nil }
        let unit = raw > 1.0 ? raw / 100.0 : raw
        guard unit >= 0.0, unit <= 1.0 else { return nil }
        return unit
    }

    nonisolated static func resolveChances(
        probability: Double?,
        pregameMark: Double?,
        phase: Phase
    ) -> (before: Double?, current: Double?) {
        let prob = normalizeUnitProbability(probability)
        let pregame = normalizeUnitProbability(pregameMark)
        switch phase {
        case .before:
            return (prob, prob)
        case .during:
            return (pregame, prob)
        case .final:
            return (pregame, nil)
        }
    }

    nonisolated static func formatPregameSourceDetail(
        rawSource: String?,
        sourceCount: Int
    ) -> String {
        let sourceLabel: String = {
            if sourceCount > 1 {
                return "\(sourceCount) sources"
            }
            guard let raw = rawSource?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
                return "Market blend"
            }
            switch raw.lowercased() {
            case "betting", "sportsbook", "the_odds_api": return "Sportsbook blend"
            default: return "Market blend"
            }
        }()
        return "Pregame · \(sourceLabel)"
    }

    nonisolated static func formatPercent(_ unit: Double) -> String {
        "\(Int((unit * 100.0).rounded()))%"
    }

    nonisolated static func formatOutlookMovement(
        before: Double,
        current: Double
    ) -> CricketOutlookMovement10868 {
        let deltaPts = Int(((current - before) * 100.0).rounded())
        if deltaPts == 0 {
            return CricketOutlookMovement10868(
                text: "No change",
                spoken: "No change from pregame"
            )
        }
        let absPts = abs(deltaPts)
        let unit = absPts == 1 ? "point" : "points"
        if deltaPts > 0 {
            return CricketOutlookMovement10868(
                text: "↑ \(absPts) \(unit)",
                spoken: "Up \(absPts) percentage \(unit) from pregame"
            )
        } else {
            return CricketOutlookMovement10868(
                text: "↓ \(absPts) \(unit)",
                spoken: "Down \(absPts) percentage \(unit) from pregame"
            )
        }
    }

    nonisolated static func formatSourceDetail(
        rawSource: String?,
        sourceCount: Int,
        observedAt: Date?,
        isStaleLive: Bool,
        phase: Phase,
        now: Date
    ) -> String {
        let sourceLabel: String = {
            if sourceCount > 1 {
                return "\(sourceCount) sources"
            }
            guard let raw = rawSource?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
                return "Market blend"
            }
            switch raw.lowercased() {
            case "betting", "sportsbook", "the_odds_api": return "Sportsbook blend"
            default: return "Market blend"
            }
        }()

        switch phase {
        case .final:
            return "\(sourceLabel) · Official result"
        case .before, .during:
            if isStaleLive {
                if let observedAt {
                    let minutes = max(1, Int(now.timeIntervalSince(observedAt) / 60))
                    return "\(sourceLabel) · No recent probability (\(minutes)m ago)"
                }
                return "\(sourceLabel) · No recent probability"
            }
            if let observedAt {
                let minutes = max(0, Int(now.timeIntervalSince(observedAt) / 60))
                if minutes <= 1 {
                    return "\(sourceLabel) · Updated just now"
                }
                return "\(sourceLabel) · Updated \(minutes)m ago"
            }
            return "\(sourceLabel) · Live quote"
        }
    }
}

// MARK: - Interactive Wrapper Views

struct EventAtlasCricketCardView11666: View {
    let card: EventAtlasCricketCards11666.Card
    var now: Date = Date()

    var body: some View {
        switch card {
        case .pregame(let pregame):
            EventAtlasCricketPregameCardView11666(card: pregame, now: now)
        case .outlook(let outlook):
            EventAtlasCricketOutlookCardView11666(card: outlook, now: now)
        case .chase(let chase):
            EventAtlasCricketChaseCardView11666(card: chase, now: now)
        }
    }
}

struct EventAtlasCricketPregameCardView11666: View {
    let card: EventAtlasCricketCards11666.PregameCard
    var now: Date = Date()

    var body: some View {
        let input = card.presentationInput(now: now)
        CricketPregameStoryPresentation10868(input: input)
            .padding(16)
            .background(DS.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
            .overlay(
                RoundedRectangle(cornerRadius: 14, style: .continuous)
                    .strokeBorder(DS.border, lineWidth: 1)
            )
    }
}

struct EventAtlasCricketOutlookCardView11666: View {
    let card: EventAtlasCricketCards11666.OutlookCard
    var now: Date = Date()

    @State private var selectedRowID: String?

    var body: some View {
        let input = card.presentationInput(selectedRowID: selectedRowID, now: now)
        CricketOutlookPresentation10868(
            input: input,
            onSelect: { ref in
                selectedRowID = ref.outcome
            }
        )
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }
}

struct EventAtlasCricketChaseCardView11666: View {
    let card: EventAtlasCricketCards11666.ChaseCard
    var now: Date = Date()

    var body: some View {
        let input = card.presentationInput(now: now)
        let tints = TeamTextContrast.cardColors(
            awayHex: card.awayColorHex,
            homeHex: card.homeColorHex
        )
        CricketChasePresentation10868(
            input: input,
            runsTint: tints.home,
            wicketTint: DS.textSecondary
        )
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }
}
