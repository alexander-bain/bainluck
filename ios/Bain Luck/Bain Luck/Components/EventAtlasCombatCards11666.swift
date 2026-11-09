import Foundation
import SwiftUI

/// #11666 (Menu Item 15, Decide 91 C) — Native MMA & Boxing story cards behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`:
/// - **`MethodCard`**: How could the fight end (`KO / TKO`, `Submission`, `Decision`, `Draw`),
///   rendered by `CombatMethodPresentation10868`.
/// - **`RoundCard`**: Which round for each fighter (`Round 1`–`Round 3`/`Round 5` for MMA, up to
///   `Round 12` for Boxing), rendered by `CombatRoundPresentation10868`.
/// - **`DurationCard`**: How long could the fight last (`Goes the distance`, `Inside the distance`,
///   and `Over/Under X.5 rounds`), rendered by `CombatDurationPresentation10868`.
///
/// Every card ages live quotes after 30 minutes (`liveQuoteMaxAgeSeconds`) to
/// `"No recent probability"` while preserving the `○` pre-match baseline, and grades
/// finished fights exclusively from venue settlement evidence (`OutcomeVerdict.verdict`).
enum EventAtlasCombatCards11666 {

    /// Live quote freshness window (30 minutes, matching `QuestionCatalog9483.livePriceMaxAge`).
    nonisolated static let liveQuoteMaxAgeSeconds: TimeInterval = 30 * 60

    nonisolated static func isCombatSport(sportKey: String?) -> Bool {
        guard let raw = sportKey?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !raw.isEmpty else {
            return false
        }
        return raw == "mma"
            || raw == "ufc"
            || raw == "boxing"
            || raw == "combat"
            || raw.hasPrefix("mma_")
            || raw.hasPrefix("boxing_")
    }

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && isCombatSport(sportKey: sportKey)
    }

    // MARK: - Phase Resolution

    nonisolated enum Phase: String, Equatable, Sendable {
        case before
        case during
        case final

        static func resolve(status: String?, commenceTime: Date?, now: Date) -> Phase {
            if EventState.isFinished(status) {
                return .final
            }
            if status == "live"
                || status == "in_progress"
                || EventState.isSuspendedAndStarted(status, commenceTime: commenceTime, now: now) {
                return .during
            }
            return .before
        }

        var methodPhase: CombatMethodPhase10868 {
            switch self {
            case .before: return .before
            case .during: return .during
            case .final: return .final
            }
        }

        var roundPhase: CombatRoundPhase10868 {
            switch self {
            case .before: return .before
            case .during: return .during
            case .final: return .final
            }
        }

        var durationPhase: CombatDurationPhase10868 {
            switch self {
            case .before: return .before
            case .during: return .during
            case .final: return .final
            }
        }
    }

    // MARK: - 1. Method of Victory Story Card

    nonisolated struct MethodTileRecord: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: String
        let label: String
        let shortLabel: String
        let question: String
        let beforeChance: Double?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date, phase: Phase) -> MethodTileRecord {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasCombatCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard beforeChance != nil || currentChance != nil || !isStaleLive else { return self }
                return MethodTileRecord(
                    id: id,
                    marketID: marketID,
                    label: label,
                    shortLabel: shortLabel,
                    question: question,
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
                return MethodTileRecord(
                    id: id,
                    marketID: marketID,
                    label: label,
                    shortLabel: shortLabel,
                    question: question,
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

        func toPresentationMethod(phase: Phase, now: Date) -> CombatMethod10868 {
            let origID = "\(id)-yes"
            let provenance = EventAtlasCombatCards11666.formatSourceDetail(
                rawSource: rawSource,
                sourceCount: sourceCount,
                observedAt: observedAt,
                isStaleLive: isStaleLive,
                phase: phase,
                now: now
            )
            let beforeObs: CombatMethodObservation10868? = beforeChance.map { prob in
                CombatMethodObservation10868(
                    probability: prob,
                    text: EventAtlasCombatCards11666.formatPercent(prob),
                    timeText: nil,
                    detail: "Before fight · \(provenance)"
                )
            }
            let currentState: CombatMethodCurrent10868 = {
                if isStaleLive {
                    return .withheld("No recent probability · \(provenance)")
                }
                if let currentChance {
                    let movement = EventAtlasCombatCards11666.formatMovement(
                        before: beforeChance,
                        current: currentChance
                    )
                    return .recorded(
                        CombatMethodObservation10868(
                            probability: currentChance,
                            text: EventAtlasCombatCards11666.formatPercent(currentChance),
                            timeText: nil,
                            detail: provenance
                        ),
                        movement: movement
                    )
                }
                return .unavailable("No in-fight chance")
            }()
            let resultState: CombatMethodResult10868 = {
                switch verdict {
                case .won:
                    return .won("✓ Won")
                case .lost:
                    return .lost("✗ Lost")
                case .none:
                    return .unconfirmed("Result not confirmed")
                }
            }()
            let beforeMissingWords = (phase == .before && isStaleLive)
                ? "No recent probability"
                : "No pre-fight chance recorded"
            let original = CombatMethodOriginal10868(
                id: origID,
                marketID: marketID,
                label: "Yes",
                before: beforeObs,
                beforeMissing: beforeMissingWords,
                current: currentState,
                result: resultState
            )
            return CombatMethod10868(
                id: id,
                label: label,
                question: question,
                originals: [original],
                overviewOriginalID: origID
            )
        }
    }

    nonisolated struct MethodCard: Equatable, Identifiable, Sendable {
        static let defaultCardID = "combat:method"
        let id: String
        let eventID: String
        let eyebrow: String
        let title: String
        let caption: String?
        let phase: Phase
        let tiles: [MethodTileRecord]
        let officialFinishSummary: String?
        let scheduledStartSummary: String?

        func current(at now: Date) -> MethodCard {
            guard phase != .final else { return self }
            return MethodCard(
                id: id,
                eventID: eventID,
                eyebrow: eyebrow,
                title: title,
                caption: caption,
                phase: phase,
                tiles: tiles.map { $0.current(at: now, phase: phase) },
                officialFinishSummary: officialFinishSummary,
                scheduledStartSummary: scheduledStartSummary
            )
        }

        func presentationInput(
            selectedMethodID: String?,
            selectedOriginalID: String? = nil,
            now: Date
        ) -> CombatMethodInput10868 {
            let aged = current(at: now)
            let methods = aged.tiles.map { $0.toPresentationMethod(phase: aged.phase, now: now) }
            let resolvedMethodID: String? = {
                if let selectedMethodID, methods.contains(where: { $0.id == selectedMethodID }) {
                    return selectedMethodID
                }
                return methods.first?.id
            }()
            let resolvedOrigID: String? = {
                if let selectedOriginalID { return selectedOriginalID }
                if let resolvedMethodID,
                   let method = methods.first(where: { $0.id == resolvedMethodID }) {
                    return method.overviewOriginalID ?? method.originals.first?.id
                }
                return nil
            }()
            let actual: CombatMethodActual10868? = aged.officialFinishSummary.map { summary in
                CombatMethodActual10868(
                    title: "Official bout result",
                    lines: [summary],
                    accessibilityDetail: summary
                )
            }
            let timing: CombatMethodTiming10868? = {
                guard let summary = aged.scheduledStartSummary,
                      let resolvedOrigID else { return nil }
                return CombatMethodTiming10868(
                    originalID: resolvedOrigID,
                    title: "Bout schedule",
                    lines: [summary, "Walkout time depends on earlier fights on the card."]
                )
            }()
            return CombatMethodInput10868(
                phase: aged.phase.methodPhase,
                eventID: aged.eventID,
                eyebrow: aged.eyebrow,
                title: aged.title,
                caption: aged.caption,
                methods: methods,
                selectedMethodID: resolvedMethodID,
                selectedOriginalID: resolvedOrigID,
                actual: actual,
                timing: timing,
                copy: .method
            )
        }
    }

    // MARK: - 2. Round Betting Story Card

    nonisolated struct RoundSlotRecord: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: String
        let fighterName: String
        let roundNumber: Int
        let roundLabel: String
        let hasMarket: Bool
        let beforeChance: Double?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let isElapsedRound: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date, phase: Phase) -> RoundSlotRecord {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasCombatCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard beforeChance != nil || currentChance != nil || !isStaleLive else { return self }
                return RoundSlotRecord(
                    id: id,
                    marketID: marketID,
                    fighterName: fighterName,
                    roundNumber: roundNumber,
                    roundLabel: roundLabel,
                    hasMarket: hasMarket,
                    beforeChance: nil,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    isElapsedRound: isElapsedRound,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .during:
                guard currentChance != nil || !isStaleLive else { return self }
                return RoundSlotRecord(
                    id: id,
                    marketID: marketID,
                    fighterName: fighterName,
                    roundNumber: roundNumber,
                    roundLabel: roundLabel,
                    hasMarket: hasMarket,
                    beforeChance: beforeChance,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    isElapsedRound: isElapsedRound,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .final:
                return self
            }
        }

        func toPresentationSlot(phase: Phase, now: Date) -> CombatRoundSlot10868 {
            guard hasMarket else {
                return CombatRoundSlot10868(
                    id: id,
                    label: "Round \(roundNumber)",
                    state: .noCapturedProp("No captured prop")
                )
            }
            let origID = "\(id)-yes"
            let provenance = EventAtlasCombatCards11666.formatSourceDetail(
                rawSource: rawSource,
                sourceCount: sourceCount,
                observedAt: observedAt,
                isStaleLive: isStaleLive,
                phase: phase,
                now: now
            )
            let beforeObs: CombatRoundObservation10868? = beforeChance.map { prob in
                CombatRoundObservation10868(
                    probability: prob,
                    text: EventAtlasCombatCards11666.formatPercent(prob),
                    detail: "Before fight · \(provenance)"
                )
            }
            let currentState: CombatRoundCurrent10868 = {
                if isStaleLive {
                    return .withheld("No recent probability · \(provenance)")
                }
                if let currentChance {
                    let movement = EventAtlasCombatCards11666.formatMovement(
                        before: beforeChance,
                        current: currentChance
                    )
                    return .recorded(
                        CombatRoundObservation10868(
                            probability: currentChance,
                            text: EventAtlasCombatCards11666.formatPercent(currentChance),
                            detail: provenance
                        ),
                        movement: movement
                    )
                }
                return .unavailable(isElapsedRound ? "Round completed" : "No in-fight chance")
            }()
            let resultState: CombatRoundResult10868 = {
                switch verdict {
                case .won:
                    return .won("✓ Won")
                case .lost:
                    return .lost("✗ Lost")
                case .none:
                    return .unconfirmed("Result not confirmed")
                }
            }()
            let beforeMissingWords = (phase == .before && isStaleLive)
                ? "No recent probability"
                : "No pre-fight chance recorded"
            let original = CombatRoundOriginal10868(
                id: origID,
                marketID: marketID,
                label: "Yes",
                before: beforeObs,
                beforeMissing: beforeMissingWords,
                current: currentState,
                result: resultState,
                resultDetail: nil
            )
            let market = CombatRoundMarket10868(
                id: marketID,
                question: "\(fighterName) to win in Round \(roundNumber)",
                originals: [original],
                overviewOriginalID: origID
            )
            return CombatRoundSlot10868(
                id: id,
                label: "Round \(roundNumber)",
                state: .market(market)
            )
        }
    }

    nonisolated struct RoundCard: Equatable, Identifiable, Sendable {
        static let cardID = "combat:rounds"
        var id: String { Self.cardID }
        var title: String { "Which round for each fighter?" }
        let eventID: String
        let eyebrow: String
        let caption: String?
        let phase: Phase
        let scheduledRounds: Int
        let currentRound: Int?
        let completedRounds: Int
        let fighterAName: String
        let fighterASlots: [RoundSlotRecord]
        let fighterBName: String
        let fighterBSlots: [RoundSlotRecord]
        let officialFinishSummary: String?
        let scheduledStartSummary: String?

        func current(at now: Date) -> RoundCard {
            guard phase != .final else { return self }
            return RoundCard(
                eventID: eventID,
                eyebrow: eyebrow,
                caption: caption,
                phase: phase,
                scheduledRounds: scheduledRounds,
                currentRound: currentRound,
                completedRounds: completedRounds,
                fighterAName: fighterAName,
                fighterASlots: fighterASlots.map { $0.current(at: now, phase: phase) },
                fighterBName: fighterBName,
                fighterBSlots: fighterBSlots.map { $0.current(at: now, phase: phase) },
                officialFinishSummary: officialFinishSummary,
                scheduledStartSummary: scheduledStartSummary
            )
        }

        func presentationInput(
            selectedSlotID: String?,
            selectedOriginalID: String? = nil,
            now: Date
        ) -> CombatRoundInput10868 {
            let aged = current(at: now)
            let allRecords = aged.fighterASlots + aged.fighterBSlots
            let resolvedSlotID: String? = {
                if let selectedSlotID, allRecords.contains(where: { $0.id == selectedSlotID && $0.hasMarket }) {
                    return selectedSlotID
                }
                return allRecords.first(where: { $0.hasMarket })?.id
            }()
            let resolvedOrigID: String? = {
                if let selectedOriginalID { return selectedOriginalID }
                guard let resolvedSlotID else { return nil }
                return "\(resolvedSlotID)-yes"
            }()
            let groups = [
                CombatRoundGroup10868(
                    id: "fighter-a",
                    label: aged.fighterAName,
                    slots: aged.fighterASlots.map { $0.toPresentationSlot(phase: aged.phase, now: now) }
                ),
                CombatRoundGroup10868(
                    id: "fighter-b",
                    label: aged.fighterBName,
                    slots: aged.fighterBSlots.map { $0.toPresentationSlot(phase: aged.phase, now: now) }
                ),
            ]
            let finish: CombatRoundFinish10868? = aged.officialFinishSummary.map { summary in
                CombatRoundFinish10868(
                    title: "Official bout result",
                    lines: [summary],
                    accessibilityDetail: summary
                )
            }
            let timing: CombatRoundTiming10868? = {
                guard let summary = aged.scheduledStartSummary,
                      let resolvedOrigID else { return nil }
                return CombatRoundTiming10868(
                    originalID: resolvedOrigID,
                    title: "Bout schedule",
                    lines: [summary, "Walkout time depends on earlier fights on the card."]
                )
            }()
            return CombatRoundInput10868(
                phase: aged.phase.roundPhase,
                eventID: aged.eventID,
                eyebrow: aged.eyebrow,
                title: aged.title,
                caption: aged.caption,
                groups: groups,
                selectedSlotID: resolvedSlotID,
                selectedOriginalID: resolvedOrigID,
                finish: finish,
                timing: timing
            )
        }
    }

    // MARK: - 3. Fight Duration / Distance Story Card

    nonisolated struct DurationRowRecord: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: String
        let title: String
        let subtitle: String
        let sideLabel: String
        let windowStart: Double
        let windowEnd: Double
        let includesFinalBell: Bool
        let beforeChance: Double?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date, phase: Phase) -> DurationRowRecord {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasCombatCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard beforeChance != nil || currentChance != nil || !isStaleLive else { return self }
                return DurationRowRecord(
                    id: id,
                    marketID: marketID,
                    title: title,
                    subtitle: subtitle,
                    sideLabel: sideLabel,
                    windowStart: windowStart,
                    windowEnd: windowEnd,
                    includesFinalBell: includesFinalBell,
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
                return DurationRowRecord(
                    id: id,
                    marketID: marketID,
                    title: title,
                    subtitle: subtitle,
                    sideLabel: sideLabel,
                    windowStart: windowStart,
                    windowEnd: windowEnd,
                    includesFinalBell: includesFinalBell,
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

        func toPresentationMarket(phase: Phase, now: Date) -> CombatDurationMarket10868 {
            let origID = "\(id)-orig"
            let provenance = EventAtlasCombatCards11666.formatSourceDetail(
                rawSource: rawSource,
                sourceCount: sourceCount,
                observedAt: observedAt,
                isStaleLive: isStaleLive,
                phase: phase,
                now: now
            )
            let beforeObs: CombatDurationObservation10868? = beforeChance.map { prob in
                CombatDurationObservation10868(
                    probability: prob,
                    text: EventAtlasCombatCards11666.formatPercent(prob),
                    timeText: nil,
                    detail: "Before fight · \(provenance)"
                )
            }
            let currentState: CombatDurationCurrent10868 = {
                if isStaleLive {
                    return .withheld("No recent probability · \(provenance)")
                }
                if let currentChance {
                    let movement = EventAtlasCombatCards11666.formatMovement(
                        before: beforeChance,
                        current: currentChance
                    )
                    return .recorded(
                        CombatDurationObservation10868(
                            probability: currentChance,
                            text: EventAtlasCombatCards11666.formatPercent(currentChance),
                            timeText: nil,
                            detail: provenance
                        ),
                        movement: movement
                    )
                }
                return .unavailable("No in-fight chance")
            }()
            let resultState: CombatDurationResult10868 = {
                switch verdict {
                case .won:
                    return .won("✓ Won")
                case .lost:
                    return .lost("✗ Lost")
                case .none:
                    return .unconfirmed("Result not confirmed")
                }
            }()
            let finalBell: CombatDurationFinalBell10868 = includesFinalBell
                ? .included("Includes the final bell")
                : .excluded("Ends before the final bell")
            let window = CombatDurationWindow10868(
                label: title,
                start: windowStart,
                end: windowEnd,
                finalBell: finalBell
            )
            let beforeMissingWords = (phase == .before && isStaleLive)
                ? "No recent probability"
                : "No pre-fight chance recorded"
            let original = CombatDurationOriginal10868(
                id: origID,
                marketID: marketID,
                label: sideLabel,
                window: window,
                windowMissing: subtitle,
                before: beforeObs,
                beforeMissing: beforeMissingWords,
                current: currentState,
                result: resultState,
                resultDetail: nil
            )
            return CombatDurationMarket10868(
                id: id,
                label: title,
                question: subtitle,
                originals: [original],
                overviewOriginalID: origID
            )
        }
    }

    nonisolated struct DurationCard: Equatable, Identifiable, Sendable {
        static let cardID = "combat:duration"
        var id: String { Self.cardID }
        var title: String { "How long could the fight last?" }
        let eventID: String
        let eyebrow: String
        let caption: String?
        let phase: Phase
        let scheduledRounds: Int
        let currentRound: Int?
        let rows: [DurationRowRecord]
        let officialDurationSummary: String?
        let scheduledStartSummary: String?

        func current(at now: Date) -> DurationCard {
            guard phase != .final else { return self }
            return DurationCard(
                eventID: eventID,
                eyebrow: eyebrow,
                caption: caption,
                phase: phase,
                scheduledRounds: scheduledRounds,
                currentRound: currentRound,
                rows: rows.map { $0.current(at: now, phase: phase) },
                officialDurationSummary: officialDurationSummary,
                scheduledStartSummary: scheduledStartSummary
            )
        }

        func presentationInput(
            selectedMarketID: String?,
            selectedOriginalID: String? = nil,
            now: Date
        ) -> CombatDurationInput10868 {
            let aged = current(at: now)
            let segments = (1...max(1, aged.scheduledRounds)).map { r in
                CombatDurationSegment10868(
                    id: "r\(r)",
                    shortLabel: "R\(r)",
                    spokenLabel: "Round \(r)"
                )
            }
            let markets = aged.rows.map { $0.toPresentationMarket(phase: aged.phase, now: now) }
            let resolvedMarketID: String? = {
                if let selectedMarketID, markets.contains(where: { $0.id == selectedMarketID }) {
                    return selectedMarketID
                }
                return markets.first?.id
            }()
            let resolvedOrigID: String? = {
                if let selectedOriginalID { return selectedOriginalID }
                if let resolvedMarketID,
                   let market = markets.first(where: { $0.id == resolvedMarketID }) {
                    return market.overviewOriginalID ?? market.originals.first?.id
                }
                return nil
            }()
            let observed: CombatDurationObserved10868? = {
                guard aged.phase == .during, let currentRound = aged.currentRound else { return nil }
                return CombatDurationObserved10868(
                    segmentID: "r\(currentRound)",
                    words: "Round \(currentRound) in progress"
                )
            }()
            let finish: CombatDurationFinish10868? = aged.officialDurationSummary.map { summary in
                CombatDurationFinish10868(
                    segmentID: nil,
                    markerWords: summary,
                    title: "Official bout result",
                    lines: [summary],
                    accessibilityDetail: summary
                )
            }
            let timing: CombatDurationTiming10868? = {
                guard let summary = aged.scheduledStartSummary,
                      let resolvedOrigID else { return nil }
                return CombatDurationTiming10868(
                    originalID: resolvedOrigID,
                    title: "Bout schedule",
                    lines: [summary, "Walkout time depends on earlier fights on the card."]
                )
            }()
            return CombatDurationInput10868(
                phase: aged.phase.durationPhase,
                eventID: aged.eventID,
                eyebrow: aged.eyebrow,
                title: aged.title,
                caption: aged.caption,
                segments: segments,
                markets: markets,
                selectedMarketID: resolvedMarketID,
                selectedOriginalID: resolvedOrigID,
                observed: observed,
                finish: finish,
                timing: timing
            )
        }
    }

    // MARK: - Top-Level Deck Builder

    static func buildCards(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date(),
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> [NFLEventCard9483] {
        guard applies(sportKey: event.sport, atlasEnabled: atlasEnabled),
              let gameMarkets,
              gameMarkets.eventId == event.id else {
            return []
        }

        let commenceDate = event.commenceTime?.asDate
        let phase = Phase.resolve(
            status: event.status,
            commenceTime: commenceDate,
            now: now
        )
        let candidates = NormalizedMarket.collect(
            from: gameMarkets,
            eventSettled: phase == .final
        )
        guard !candidates.isEmpty else { return [] }

        let scheduledStartSummary = buildScheduledStartSummary(event: event, phase: phase)
        var cards: [NFLEventCard9483] = []

        if let methodCard = buildMethodCard(
            event: event,
            candidates: candidates,
            phase: phase,
            scheduledStartSummary: scheduledStartSummary,
            now: now
        ) {
            cards.append(.combatMethod(methodCard))
        }

        let roundCard = buildRoundCard(
            event: event,
            candidates: candidates,
            phase: phase,
            scheduledStartSummary: scheduledStartSummary,
            now: now
        )
        if let roundCard {
            cards.append(.combatRounds(roundCard))
        }

        let isBoxing = (event.sport ?? "").lowercased().contains("boxing")
        if let durationCard = buildDurationCard(
            event: event,
            candidates: candidates,
            phase: phase,
            scheduledRounds: roundCard?.scheduledRounds ?? (isBoxing ? 12 : 3),
            scheduledStartSummary: scheduledStartSummary,
            now: now
        ) {
            cards.append(.combatDuration(durationCard))
        }

        return cards
    }

    // MARK: - Internal Market Normalization

    private nonisolated struct NormalizedOutcome: Sendable {
        let name: String
        let probability: Double?
        let openingProbability: Double?
        let verdict: OutcomeVerdict?
    }

    private nonisolated struct NormalizedMarket: Sendable {
        let id: Int
        let title: String
        let marketType: String?
        let isSettled: Bool
        let source: String?
        let sourceCount: Int
        let updatedAt: Date?
        let outcomes: [NormalizedOutcome]

        static func collect(from response: GameMarketsResponse, eventSettled: Bool) -> [NormalizedMarket] {
            var grouped: [String: (
                id: Int,
                title: String,
                marketType: String?,
                source: String?,
                sources: Set<String>,
                updatedAt: Date?,
                outcomes: [NormalizedOutcome]
            )] = [:]
            var order: [String] = []

            func appendOutcome(
                marketID: Int?,
                marketName: String,
                marketType: String?,
                outcomeName: String,
                probability: Double?,
                pregameMark: Double?,
                source: String?,
                observedAt: String?,
                isWinner: Bool?,
                resolutionSource: String?
            ) {
                let trimmedName = marketName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !trimmedName.isEmpty else { return }
                let key = marketID.map { "id:\($0)" } ?? "title:\(trimmedName)"
                if grouped[key] == nil {
                    order.append(key)
                    grouped[key] = (
                        id: marketID ?? (order.count + 1000),
                        title: trimmedName,
                        marketType: marketType,
                        source: source,
                        sources: source.map { [$0] } ?? [],
                        updatedAt: nil,
                        outcomes: []
                    )
                }
                guard var entry = grouped[key] else { return }
                if let src = source, !src.isEmpty {
                    entry.sources.insert(src)
                    if entry.source == nil { entry.source = src }
                }
                if let obsDate = observedAt?.asDate {
                    if let existing = entry.updatedAt {
                        entry.updatedAt = max(existing, obsDate)
                    } else {
                        entry.updatedAt = obsDate
                    }
                }
                // Decide 80-A (#12274, #12449): ask OutcomeVerdict as for an open market
                // (`marketResolved: false`) so only an authoritative win becomes `.won`,
                // and a row grade never mints `.lost`.
                let verdict: OutcomeVerdict? = eventSettled
                    ? (OutcomeVerdict.verdict(
                        isWinner: isWinner,
                        resolutionSource: resolutionSource,
                        marketResolved: false
                    ) == .won ? .won : nil)
                    : nil
                entry.outcomes.append(
                    NormalizedOutcome(
                        name: outcomeName,
                        probability: normalizeUnitProbability(probability),
                        openingProbability: normalizeUnitProbability(pregameMark),
                        verdict: verdict
                    )
                )
                grouped[key] = entry
            }

            for row in response.other ?? [] {
                appendOutcome(
                    marketID: row._marketId ?? row._marketIds?.first,
                    marketName: row.marketName,
                    marketType: nil,
                    outcomeName: row.outcomeName,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }

            for row in response.totals ?? [] {
                let label: String = {
                    if let threshold = row.threshold {
                        return "\(row.outcomeName) \(threshold)"
                    }
                    return row.outcomeName
                }()
                let lowerOutcome = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                let isUnder = lowerOutcome.hasPrefix("under") || lowerOutcome == "u"
                let resolvedProbability: Double? = {
                    if isUnder {
                        if let overProb = row.overProbability, overProb.isFinite {
                            return 1.0 - overProb
                        }
                        return row.probability
                    }
                    return row.overProbability ?? row.probability
                }()
                let resolvedPregameMark: Double? = {
                    if isUnder, row.overProbability != nil {
                        return row.pregameMark.map { 1.0 - $0 }
                    }
                    return row.pregameMark
                }()
                appendOutcome(
                    marketID: row._marketId ?? row._marketIds?.first,
                    marketName: row.marketName,
                    marketType: row.marketType ?? "total_rounds",
                    outcomeName: label,
                    probability: resolvedProbability,
                    pregameMark: resolvedPregameMark,
                    source: row.source,
                    observedAt: row.observedAt,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }

            for row in response.periodMarkets ?? [] {
                appendOutcome(
                    marketID: row._marketId ?? row._marketIds?.first,
                    marketName: row.marketName,
                    marketType: row.marketType,
                    outcomeName: row.outcomeName,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }

            return order.compactMap { key in
                guard let entry = grouped[key] else { return nil }
                return NormalizedMarket(
                    id: entry.id,
                    title: entry.title,
                    marketType: entry.marketType,
                    isSettled: eventSettled,
                    source: entry.source,
                    sourceCount: max(1, entry.sources.count),
                    updatedAt: entry.updatedAt,
                    outcomes: entry.outcomes
                )
            }
        }

        private static func normalizeUnitProbability(_ raw: Double?) -> Double? {
            guard let raw, raw.isFinite else { return nil }
            let unit = raw > 1.0 ? raw / 100.0 : raw
            guard unit >= 0.0, unit <= 1.0 else { return nil }
            return unit
        }
    }

    // MARK: - Method Card Builder

    private nonisolated enum CanonicalMethodBucket: String, CaseIterable, Sendable {
        case koTKO = "ko-tko"
        case submission = "submission"
        case decision = "decision"
        case draw = "draw"

        var label: String {
            switch self {
            case .koTKO: return "KO / TKO"
            case .submission: return "Submission"
            case .decision: return "Decision"
            case .draw: return "Draw"
            }
        }

        var shortLabel: String {
            switch self {
            case .koTKO: return "KO/TKO"
            case .submission: return "Sub"
            case .decision: return "Dec"
            case .draw: return "Draw"
            }
        }

        var question: String {
            switch self {
            case .koTKO: return "Will the fight end by KO, TKO, or DQ?"
            case .submission: return "Will the fight end by submission?"
            case .decision: return "Will the fight be decided on the scorecards?"
            case .draw: return "Will the fight end in a draw?"
            }
        }

        static func classify(
            _ raw: String,
            fighterA: String = "",
            fighterB: String = ""
        ) -> CanonicalMethodBucket? {
            var cleaned = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            let mmaSport = "mma_mixed_martial_arts"
            let shortPair = (!fighterA.isEmpty || !fighterB.isEmpty)
                ? TeamShortName.shortPair(away: fighterB, home: fighterA, sportKey: mmaSport)
                : (away: "", home: "")
            let fighterStrings: [String] = [
                fighterA,
                fighterB,
                shortPair.home,
                shortPair.away
            ]
            for name in fighterStrings {
                let lowerName = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                guard lowerName.count >= 2 else { continue }
                cleaned = cleaned.replacingOccurrences(of: lowerName, with: " ")
            }
            if let byRange = cleaned.range(of: " by ") {
                cleaned = String(cleaned[byRange.upperBound...])
            } else if let viaRange = cleaned.range(of: " via ") {
                cleaned = String(cleaned[viaRange.upperBound...])
            }
            let words = Set(
                cleaned
                    .components(separatedBy: CharacterSet.alphanumerics.inverted)
                    .filter { !$0.isEmpty }
            )
            if !words.isDisjoint(with: ["ko", "tko", "knockout", "stoppage", "dq", "disqualification"]) {
                return .koTKO
            }
            if !words.isDisjoint(with: ["submission", "submissions", "sub", "choke", "armbar", "tap", "tapout", "guillotine", "triangle", "kimura"]) {
                return .submission
            }
            if !words.isDisjoint(with: ["decision", "dec", "points", "unanimous", "split", "majority", "scorecard", "scorecards", "judges"]) {
                return .decision
            }
            if words.contains("draw") {
                return .draw
            }
            return nil
        }
    }

    private nonisolated static func namesFighter(
        _ text: String,
        fighterA: String,
        fighterB: String
    ) -> Bool {
        let lower = text.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !lower.isEmpty else { return false }
        let words = Set(
            lower
                .components(separatedBy: CharacterSet.alphanumerics.inverted)
                .filter { !$0.isEmpty }
        )
        let mmaSport = "mma_mixed_martial_arts"
        let shortPair = (!fighterA.isEmpty || !fighterB.isEmpty)
            ? TeamShortName.shortPair(away: fighterB, home: fighterA, sportKey: mmaSport)
            : (away: "", home: "")
        let candidates: [(full: String, short: String)] = [
            (fighterA, shortPair.home),
            (fighterB, shortPair.away)
        ]
        for candidate in candidates {
            let trimmed = candidate.full.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !trimmed.isEmpty else { continue }
            if lower.contains(trimmed) { return true }
            let shortLower = candidate.short.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if shortLower.count >= 2 && words.contains(shortLower) { return true }
            let tokens = trimmed
                .components(separatedBy: CharacterSet.alphanumerics.inverted)
                .filter { $0.count >= 3 }
            if tokens.contains(where: { words.contains($0) }) { return true }
        }
        return false
    }

    private nonisolated static func isMethodMarket(
        _ market: NormalizedMarket,
        fighterA: String = "",
        fighterB: String = ""
    ) -> Bool {
        if namesFighter(market.title, fighterA: fighterA, fighterB: fighterB) {
            return false
        }
        let typeLower = (market.marketType ?? "").lowercased()
        if typeLower == "method_of_victory"
            || typeLower == "method_of_finish"
            || typeLower == "fight_finish_method"
            || typeLower == "win_method"
            || typeLower == "winning_method" {
            return true
        }
        let titleLower = market.title.lowercased()
        if titleLower.contains("method of victory")
            || titleLower.contains("method of finish")
            || titleLower.contains("how will the fight end")
            || titleLower.contains("winning method")
            || titleLower.contains("won by ko")
            || titleLower.contains("won by tko")
            || titleLower.contains("win by ko")
            || titleLower.contains("by ko or tko")
            || titleLower.contains("by ko/tko")
            || titleLower.contains("won by submission")
            || titleLower.contains("by submission")
            || titleLower.contains("won by decision")
            || titleLower.contains("by decision") {
            return true
        }
        return false
    }

    private nonisolated static func buildMethodCard(
        event: EventDetail,
        candidates: [NormalizedMarket],
        phase: Phase,
        scheduledStartSummary: String?,
        now: Date
    ) -> MethodCard? {
        let fighterAName = event.homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        let fighterBName = event.awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)

        let methodMarkets = candidates.filter {
            isMethodMarket($0, fighterA: fighterAName, fighterB: fighterBName)
        }
        guard !methodMarkets.isEmpty else { return nil }

        struct BucketEntry {
            let marketID: String
            let beforeChance: Double?
            let currentChance: Double?
            let observedAt: Date?
            let verdict: OutcomeVerdict?
            let rawSource: String?
            let sourceCount: Int
        }

        var byBucket: [CanonicalMethodBucket: BucketEntry] = [:]

        for market in methodMarkets {
            for outcome in market.outcomes {
                if namesFighter(outcome.name, fighterA: fighterAName, fighterB: fighterBName) {
                    continue
                }
                let bucket = CanonicalMethodBucket.classify(
                    outcome.name,
                    fighterA: fighterAName,
                    fighterB: fighterBName
                ) ?? (
                    Self.isAffirmativeOutcome(outcome.name)
                        ? CanonicalMethodBucket.classify(
                            market.title,
                            fighterA: fighterAName,
                            fighterB: fighterBName
                        )
                        : nil
                )
                guard let bucket, byBucket[bucket] == nil else { continue }
                guard Self.isAffirmativeOrNamedOutcome(outcome.name) else { continue }

                let resolvedVerdict = phase == .final ? outcome.verdict : nil
                let (beforeVal, currentVal) = Self.resolveChances(
                    outcome: outcome,
                    phase: phase
                )
                let admittedBefore = beforeVal.flatMap { $0 >= 0.0 && $0 <= 1.0 ? $0 : nil }
                let admittedCurrent = currentVal.flatMap { $0 >= 0.0 && $0 <= 1.0 ? $0 : nil }
                guard admittedBefore != nil || admittedCurrent != nil || resolvedVerdict != nil else {
                    continue
                }
                byBucket[bucket] = BucketEntry(
                    marketID: String(market.id),
                    beforeChance: admittedBefore,
                    currentChance: admittedCurrent,
                    observedAt: market.updatedAt,
                    verdict: resolvedVerdict,
                    rawSource: market.source,
                    sourceCount: market.sourceCount
                )
            }
        }

        let isBoxing = (event.sport ?? "").lowercased().contains("boxing")
        let orderedBuckets: [CanonicalMethodBucket] = isBoxing
            ? [.koTKO, .decision, .draw]
            : [.koTKO, .submission, .decision, .draw]

        var tiles: [MethodTileRecord] = []
        for bucket in orderedBuckets {
            guard let entry = byBucket[bucket] else { continue }
            let record = MethodTileRecord(
                id: bucket.rawValue,
                marketID: entry.marketID,
                label: bucket.label,
                shortLabel: bucket.shortLabel,
                question: bucket.question,
                beforeChance: entry.beforeChance,
                currentChance: entry.currentChance,
                observedAt: entry.observedAt,
                isStaleLive: false,
                verdict: entry.verdict,
                rawSource: entry.rawSource,
                sourceCount: entry.sourceCount
            ).current(at: now, phase: phase)
            tiles.append(record)
        }

        guard !tiles.isEmpty else { return nil }

        let officialSummary: String? = {
            guard phase == .final else { return nil }
            if let winnerTile = tiles.first(where: { $0.verdict == .won }) {
                return "Official result: \(winnerTile.label)"
            }
            return nil
        }()

        return MethodCard(
            id: MethodCard.defaultCardID,
            eventID: String(event.id),
            eyebrow: "METHOD OF VICTORY",
            title: "How could the fight end?",
            caption: "Each method is an independent contract.",
            phase: phase,
            tiles: tiles,
            officialFinishSummary: officialSummary,
            scheduledStartSummary: scheduledStartSummary
        )
    }

    // MARK: - Round Card Builder

    private nonisolated static func isRoundMarket(_ market: NormalizedMarket) -> Bool {
        let typeLower = (market.marketType ?? "").lowercased()
        if typeLower == "round_betting"
            || typeLower == "victory_round"
            || typeLower == "round_of_victory"
            || typeLower == "fight_round" {
            return true
        }
        let titleLower = market.title.lowercased()
        if titleLower.contains("round of victory")
            || titleLower.contains("round of finish")
            || titleLower.contains("round betting")
            || titleLower.contains("which round")
            || titleLower.contains("win in round")
            || titleLower.contains("victory in round") {
            return true
        }
        return false
    }

    private nonisolated static func buildRoundCard(
        event: EventDetail,
        candidates: [NormalizedMarket],
        phase: Phase,
        scheduledStartSummary: String?,
        now: Date
    ) -> RoundCard? {
        let roundMarkets = candidates.filter { isRoundMarket($0) }
        guard !roundMarkets.isEmpty else { return nil }

        let fighterAName = event.homeTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        let fighterBName = event.awayTeam.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !fighterAName.isEmpty, !fighterBName.isEmpty else { return nil }

        struct ParsedRoundOutcome {
            let marketID: String
            let isFighterA: Bool
            let roundNumber: Int
            let beforeChance: Double?
            let currentChance: Double?
            let observedAt: Date?
            let verdict: OutcomeVerdict?
            let rawSource: String?
            let sourceCount: Int
        }

        var parsed: [ParsedRoundOutcome] = []
        var maxObservedRound = 0

        for market in roundMarkets {
            for outcome in market.outcomes {
                let combinedText = "\(market.title) — \(outcome.name)"
                guard let roundNumber = Self.extractRoundNumber(from: outcome.name)
                        ?? Self.extractRoundNumber(from: market.title),
                      roundNumber >= 1, roundNumber <= 12 else {
                    continue
                }
                guard Self.isAffirmativeOrNamedOutcome(outcome.name) else { continue }
                guard let isFighterA = Self.matchFighterSide(
                    text: combinedText,
                    fighterA: fighterAName,
                    fighterB: fighterBName
                ) else {
                    continue
                }
                maxObservedRound = max(maxObservedRound, roundNumber)
                let (beforeVal, currentVal) = Self.resolveChances(outcome: outcome, phase: phase)
                let verdict = phase == .final ? outcome.verdict : nil
                parsed.append(
                    ParsedRoundOutcome(
                        marketID: String(market.id),
                        isFighterA: isFighterA,
                        roundNumber: roundNumber,
                        beforeChance: beforeVal,
                        currentChance: currentVal,
                        observedAt: market.updatedAt,
                        verdict: verdict,
                        rawSource: market.source,
                        sourceCount: market.sourceCount
                    )
                )
            }
        }

        guard !parsed.isEmpty else { return nil }

        let isBoxing = (event.sport ?? "").lowercased().contains("boxing")
        let scheduledRounds: Int = {
            if maxObservedRound > 5 {
                if maxObservedRound <= 8 { return 8 }
                if maxObservedRound <= 10 { return 10 }
                return 12
            }
            if maxObservedRound > 3 {
                return 5
            }
            return isBoxing ? max(maxObservedRound, 8) : 3
        }()

        let currentRound: Int? = {
            guard phase == .during else { return nil }
            return Self.extractLiveRound(from: event.espn?.period)
        }()
        let completedRounds: Int = {
            guard let currentRound, currentRound > 1 else { return 0 }
            return currentRound - 1
        }()

        func buildSlots(isFighterA: Bool, fighterName: String) -> [RoundSlotRecord] {
            let prefix = isFighterA ? "a" : "b"
            return (1...scheduledRounds).map { roundNum in
                let match = parsed.first { $0.isFighterA == isFighterA && $0.roundNumber == roundNum }
                let isElapsed = phase == .during && roundNum <= completedRounds
                let record = RoundSlotRecord(
                    id: "\(prefix)-r\(roundNum)",
                    marketID: match?.marketID ?? "unoffered-\(prefix)-r\(roundNum)",
                    fighterName: fighterName,
                    roundNumber: roundNum,
                    roundLabel: "R\(roundNum)",
                    hasMarket: match != nil,
                    beforeChance: match?.beforeChance,
                    currentChance: match?.currentChance,
                    observedAt: match?.observedAt,
                    isStaleLive: false,
                    isElapsedRound: isElapsed,
                    verdict: match?.verdict,
                    rawSource: match?.rawSource,
                    sourceCount: match?.sourceCount ?? 1
                )
                return record.current(at: now, phase: phase)
            }
        }

        let fighterASlots = buildSlots(isFighterA: true, fighterName: fighterAName)
        let fighterBSlots = buildSlots(isFighterA: false, fighterName: fighterBName)

        let officialSummary: String? = {
            guard phase == .final else { return nil }
            if let winSlot = (fighterASlots + fighterBSlots).first(where: { $0.verdict == .won }) {
                return "Official finish: \(winSlot.fighterName) in Round \(winSlot.roundNumber)"
            }
            return nil
        }()

        return RoundCard(
            eventID: String(event.id),
            eyebrow: "ROUND BETTING",
            caption: "Each fighter’s round is an independent market.",
            phase: phase,
            scheduledRounds: scheduledRounds,
            currentRound: currentRound,
            completedRounds: completedRounds,
            fighterAName: fighterAName,
            fighterASlots: fighterASlots,
            fighterBName: fighterBName,
            fighterBSlots: fighterBSlots,
            officialFinishSummary: officialSummary,
            scheduledStartSummary: scheduledStartSummary
        )
    }

    // MARK: - Duration / Distance Card Builder

    private nonisolated static func isDurationMarket(_ market: NormalizedMarket) -> Bool {
        let typeLower = (market.marketType ?? "").lowercased()
        if typeLower == "go_the_distance"
            || typeLower == "fight_to_go_the_distance"
            || typeLower == "total_rounds"
            || typeLower == "over_under_rounds"
            || typeLower == "fight_duration" {
            return true
        }
        let titleLower = market.title.lowercased()
        if titleLower.contains("go the distance")
            || titleLower.contains("goes the distance")
            || titleLower.contains("inside the distance")
            || titleLower.contains("total rounds")
            || titleLower.contains("over/under rounds")
            || (titleLower.contains("rounds") && (titleLower.contains("o/u") || titleLower.contains("over ") || titleLower.contains("under "))) {
            return true
        }
        return false
    }

    private nonisolated static func buildDurationCard(
        event: EventDetail,
        candidates: [NormalizedMarket],
        phase: Phase,
        scheduledRounds: Int,
        scheduledStartSummary: String?,
        now: Date
    ) -> DurationCard? {
        let durationMarkets = candidates.filter { isDurationMarket($0) }
        guard !durationMarkets.isEmpty else { return nil }

        var rows: [DurationRowRecord] = []
        var seenRowIDs = Set<String>()
        let totalRounds = Double(max(1, scheduledRounds))

        for market in durationMarkets {
            let titleLower = market.title.lowercased()
            let isDistanceMarket = (market.marketType ?? "").lowercased().contains("distance")
                || titleLower.contains("distance")

            for outcome in market.outcomes {
                let outcomeLower = outcome.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                let rowSpec: (
                    id: String,
                    title: String,
                    subtitle: String,
                    sideLabel: String,
                    windowStart: Double,
                    windowEnd: Double,
                    includesFinalBell: Bool
                )? = {
                    if isDistanceMarket {
                        if outcomeLower == "yes"
                            || outcomeLower.contains("goes the distance")
                            || outcomeLower.contains("go the distance") {
                            return (
                                "distance-yes",
                                "Goes the distance",
                                "Fight reaches the final bell",
                                "Yes",
                                totalRounds,
                                totalRounds,
                                true
                            )
                        }
                        if outcomeLower == "no"
                            || outcomeLower.contains("inside the distance")
                            || outcomeLower.contains("doesn't go the distance")
                            || outcomeLower.contains("does not go the distance") {
                            return (
                                "distance-no",
                                "Inside the distance",
                                "Fight ends by stoppage before the final bell",
                                "No",
                                0.0,
                                totalRounds,
                                false
                            )
                        }
                    }
                    if let parsedThreshold = Self.extractOverUnderThreshold(
                        outcomeName: outcome.name,
                        marketTitle: market.title
                    ) {
                        let direction = parsedThreshold.direction
                        let threshold = parsedThreshold.threshold
                        let numericValue = min(totalRounds, max(0.0, Double(threshold) ?? (totalRounds / 2.0)))
                        let id = "rounds-\(direction.lowercased())-\(threshold)"
                        let title = "\(direction) \(threshold) rounds"
                        let subtitle = direction == "Over"
                            ? "Fight lasts past the \(threshold)-round mark"
                            : "Fight finishes before the \(threshold)-round mark"
                        let start = direction == "Over" ? numericValue : 0.0
                        let end = direction == "Over" ? totalRounds : numericValue
                        let includesBell = direction == "Over"
                        return (id, title, subtitle, direction, start, end, includesBell)
                    }
                    return nil
                }()

                guard let rowSpec, !seenRowIDs.contains(rowSpec.id) else {
                    continue
                }
                seenRowIDs.insert(rowSpec.id)

                let (beforeVal, currentVal) = Self.resolveChances(outcome: outcome, phase: phase)
                let verdict = phase == .final ? outcome.verdict : nil

                let record = DurationRowRecord(
                    id: rowSpec.id,
                    marketID: String(market.id),
                    title: rowSpec.title,
                    subtitle: rowSpec.subtitle,
                    sideLabel: rowSpec.sideLabel,
                    windowStart: rowSpec.windowStart,
                    windowEnd: rowSpec.windowEnd,
                    includesFinalBell: rowSpec.includesFinalBell,
                    beforeChance: beforeVal,
                    currentChance: currentVal,
                    observedAt: market.updatedAt,
                    isStaleLive: false,
                    verdict: verdict,
                    rawSource: market.source,
                    sourceCount: market.sourceCount
                ).current(at: now, phase: phase)
                rows.append(record)
            }
        }

        guard !rows.isEmpty else { return nil }

        let officialSummary: String? = {
            guard phase == .final else { return nil }
            if let winnerRow = rows.first(where: { $0.verdict == .won }) {
                return "Official duration: \(winnerRow.title)"
            }
            return nil
        }()

        let currentRound: Int? = {
            guard phase == .during else { return nil }
            return Self.extractLiveRound(from: event.espn?.period)
        }()

        return DurationCard(
            eventID: String(event.id),
            eyebrow: "FIGHT DURATION",
            caption: "Shaded rounds show each contract’s time window.",
            phase: phase,
            scheduledRounds: scheduledRounds,
            currentRound: currentRound,
            rows: rows,
            officialDurationSummary: officialSummary,
            scheduledStartSummary: scheduledStartSummary
        )
    }

    // MARK: - Shared Helpers

    nonisolated static func formatPercent(_ unit: Double) -> String {
        "\(Int((unit * 100).rounded()))%"
    }

    nonisolated static func formatMovement(before: Double?, current: Double?) -> String? {
        guard let before, let current else { return nil }
        let deltaPts = (current - before) * 100.0
        let roundedPts = Int(deltaPts.rounded())
        if roundedPts == 0 {
            return "Unchanged vs before fight"
        }
        let sign = roundedPts > 0 ? "+" : "−"
        let unit = abs(roundedPts) == 1 ? "pt" : "pts"
        return "\(sign)\(abs(roundedPts)) \(unit) vs before fight"
    }

    private nonisolated static func resolveChances(
        outcome: NormalizedOutcome,
        phase: Phase
    ) -> (before: Double?, current: Double?) {
        switch phase {
        case .before:
            return (outcome.probability, outcome.probability)
        case .during:
            return (outcome.openingProbability, outcome.probability)
        case .final:
            let baseline = outcome.openingProbability
            return (baseline, outcome.probability ?? baseline)
        }
    }

    private nonisolated static func isAffirmativeOutcome(_ name: String) -> Bool {
        let lower = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return lower == "yes"
    }

    private nonisolated static func isAffirmativeOrNamedOutcome(_ name: String) -> Bool {
        let lower = name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return lower != "no"
    }

    private nonisolated static func extractRoundNumber(from text: String) -> Int? {
        let pattern = #"(?i)\b(?:round|rnd|r)\s*(\d{1,2})\b"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let nsRange = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = regex.firstMatch(in: text, range: nsRange),
              match.numberOfRanges > 1,
              let range = Range(match.range(at: 1), in: text),
              let number = Int(text[range]) else {
            return nil
        }
        return number
    }

    private nonisolated static func extractLiveRound(from gamePeriod: String?) -> Int? {
        guard let raw = gamePeriod?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else {
            return nil
        }
        if let round = extractRoundNumber(from: raw) {
            return round
        }
        let digits = raw.filter(\.isNumber)
        if let num = Int(digits), (1...12).contains(num) {
            return num
        }
        return nil
    }

    private nonisolated static func matchFighterSide(
        text: String,
        fighterA: String,
        fighterB: String
    ) -> Bool? {
        let lower = text.lowercased()
        let aLower = fighterA.lowercased()
        let bLower = fighterB.lowercased()
        let aLast = TeamShortName.short(fighterA, sportKey: "mma_mixed_martial_arts").lowercased()
        let bLast = TeamShortName.short(fighterB, sportKey: "mma_mixed_martial_arts").lowercased()

        let matchesA = lower.contains(aLower) || (aLast.count >= 3 && lower.contains(aLast))
        let matchesB = lower.contains(bLower) || (bLast.count >= 3 && lower.contains(bLast))
        if matchesA && !matchesB { return true }
        if matchesB && !matchesA { return false }

        if let dashRange = lower.range(of: "—") {
            let outcomePart = String(lower[dashRange.upperBound...])
            let outMatchesA = outcomePart.contains(aLower) || (aLast.count >= 3 && outcomePart.contains(aLast))
            let outMatchesB = outcomePart.contains(bLower) || (bLast.count >= 3 && outcomePart.contains(bLast))
            if outMatchesA && !outMatchesB { return true }
            if outMatchesB && !outMatchesA { return false }
        }
        return nil
    }

    private nonisolated static func extractOverUnderThreshold(
        outcomeName: String,
        marketTitle: String
    ) -> (direction: String, threshold: String)? {
        let combined = "\(outcomeName) \(marketTitle)"
        let lowerOutcome = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let direction: String? = {
            if lowerOutcome.hasPrefix("over") || lowerOutcome == "o" { return "Over" }
            if lowerOutcome.hasPrefix("under") || lowerOutcome == "u" { return "Under" }
            return nil
        }()
        guard let direction else { return nil }

        let pattern = #"(\d+(?:\.\d+)?)\s*(?:rounds?|r\b)?"#
        guard let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]) else {
            return nil
        }
        let nsRange = NSRange(combined.startIndex..<combined.endIndex, in: combined)
        let matches = regex.matches(in: combined, range: nsRange)
        for match in matches {
            guard match.numberOfRanges > 1,
                  let range = Range(match.range(at: 1), in: combined) else {
                continue
            }
            let token = String(combined[range])
            if let value = Double(token), value >= 0.5, value <= 12.5 {
                return (direction, token)
            }
        }
        return nil
    }

    private nonisolated static func buildScheduledStartSummary(
        event: EventDetail,
        phase: Phase
    ) -> String? {
        guard phase == .before else { return nil }
        guard let commenceDate = event.commenceTime?.asDate else { return nil }
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/New_York") ?? .current
        formatter.dateFormat = "EEE, MMM d · h:mm a 'ET'"
        let formattedStart = formatter.string(from: commenceDate)
        return "Scheduled start · \(formattedStart)"
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

// MARK: - Interactive Wrapper Views & Details Sheet

struct EventAtlasCombatDetailContext11666: Identifiable, Equatable {
    let id: String
    let cardTitle: String
    let itemTitle: String
    let phase: EventAtlasCombatCards11666.Phase
    let beforeChance: Double?
    let currentChance: Double?
    let isStaleLive: Bool
    let verdict: OutcomeVerdict?
    let sourceDetail: String
}

struct EventAtlasCombatMethodCardView11666: View {
    let card: EventAtlasCombatCards11666.MethodCard
    var now: Date = Date()

    @State private var selectedMethodID: String?
    @State private var selectedOriginalID: String?
    @State private var timingExpanded = false
    @State private var detailContext: EventAtlasCombatDetailContext11666?

    var body: some View {
        let aged = card.current(at: now)
        let input = aged.presentationInput(
            selectedMethodID: selectedMethodID,
            selectedOriginalID: selectedOriginalID,
            now: now
        )
        CombatMethodPresentation10868(
            input: input,
            onSelect: { ref in
                selectedMethodID = ref.methodID
                selectedOriginalID = ref.originalID
            },
            onDetails: { ref in
                selectedMethodID = ref.methodID
                selectedOriginalID = ref.originalID
                if let tile = aged.tiles.first(where: { $0.id == ref.methodID }) {
                    detailContext = EventAtlasCombatDetailContext11666(
                        id: tile.id,
                        cardTitle: aged.title,
                        itemTitle: tile.label,
                        phase: aged.phase,
                        beforeChance: tile.beforeChance,
                        currentChance: tile.currentChance,
                        isStaleLive: tile.isStaleLive,
                        verdict: tile.verdict,
                        sourceDetail: EventAtlasCombatCards11666.formatSourceDetail(
                            rawSource: tile.rawSource,
                            sourceCount: tile.sourceCount,
                            observedAt: tile.observedAt,
                            isStaleLive: tile.isStaleLive,
                            phase: aged.phase,
                            now: now
                        )
                    )
                }
            },
            timingExpanded: $timingExpanded
        )
        .sheet(item: $detailContext) { context in
            EventAtlasCombatDetailsSheet11666(context: context)
        }
    }
}

struct EventAtlasCombatRoundCardView11666: View {
    let card: EventAtlasCombatCards11666.RoundCard
    var now: Date = Date()

    @State private var selectedSlotID: String?
    @State private var selectedOriginalID: String?
    @State private var timingExpanded = false
    @State private var detailContext: EventAtlasCombatDetailContext11666?

    var body: some View {
        let aged = card.current(at: now)
        let input = aged.presentationInput(
            selectedSlotID: selectedSlotID,
            selectedOriginalID: selectedOriginalID,
            now: now
        )
        let allSlots = aged.fighterASlots + aged.fighterBSlots
        CombatRoundPresentation10868(
            input: input,
            onSelect: { ref in
                selectedSlotID = ref.slotID
                selectedOriginalID = ref.originalID
            },
            onDetails: { ref in
                selectedSlotID = ref.slotID
                selectedOriginalID = ref.originalID
                if let slot = allSlots.first(where: { $0.id == ref.slotID }) {
                    detailContext = EventAtlasCombatDetailContext11666(
                        id: slot.id,
                        cardTitle: aged.title,
                        itemTitle: "\(slot.fighterName) · Round \(slot.roundNumber)",
                        phase: aged.phase,
                        beforeChance: slot.beforeChance,
                        currentChance: slot.currentChance,
                        isStaleLive: slot.isStaleLive,
                        verdict: slot.verdict,
                        sourceDetail: EventAtlasCombatCards11666.formatSourceDetail(
                            rawSource: slot.rawSource,
                            sourceCount: slot.sourceCount,
                            observedAt: slot.observedAt,
                            isStaleLive: slot.isStaleLive,
                            phase: aged.phase,
                            now: now
                        )
                    )
                }
            },
            timingExpanded: $timingExpanded
        )
        .sheet(item: $detailContext) { context in
            EventAtlasCombatDetailsSheet11666(context: context)
        }
    }
}

struct EventAtlasCombatDurationCardView11666: View {
    let card: EventAtlasCombatCards11666.DurationCard
    var now: Date = Date()

    @State private var selectedMarketID: String?
    @State private var selectedOriginalID: String?
    @State private var timingExpanded = false
    @State private var detailContext: EventAtlasCombatDetailContext11666?

    var body: some View {
        let aged = card.current(at: now)
        let input = aged.presentationInput(
            selectedMarketID: selectedMarketID,
            selectedOriginalID: selectedOriginalID,
            now: now
        )
        CombatDurationPresentation10868(
            input: input,
            onSelect: { ref in
                selectedMarketID = ref.durationMarketID
                selectedOriginalID = ref.originalID
            },
            onDetails: { ref in
                selectedMarketID = ref.durationMarketID
                selectedOriginalID = ref.originalID
                if let row = aged.rows.first(where: { $0.id == ref.durationMarketID }) {
                    detailContext = EventAtlasCombatDetailContext11666(
                        id: row.id,
                        cardTitle: aged.title,
                        itemTitle: row.title,
                        phase: aged.phase,
                        beforeChance: row.beforeChance,
                        currentChance: row.currentChance,
                        isStaleLive: row.isStaleLive,
                        verdict: row.verdict,
                        sourceDetail: EventAtlasCombatCards11666.formatSourceDetail(
                            rawSource: row.rawSource,
                            sourceCount: row.sourceCount,
                            observedAt: row.observedAt,
                            isStaleLive: row.isStaleLive,
                            phase: aged.phase,
                            now: now
                        )
                    )
                }
            },
            timingExpanded: $timingExpanded
        )
        .sheet(item: $detailContext) { context in
            EventAtlasCombatDetailsSheet11666(context: context)
        }
    }
}

struct EventAtlasCombatDetailsSheet11666: View {
    let context: EventAtlasCombatDetailContext11666
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section(context.cardTitle) {
                    LabeledContent("Outcome", value: context.itemTitle)
                    if let before = context.beforeChance {
                        LabeledContent("○ Before fight", value: "\(Int((before * 100).rounded()))%")
                    } else if context.phase == .before && context.isStaleLive {
                        LabeledContent("○ Before fight", value: "No recent probability")
                    } else {
                        LabeledContent("○ Before fight", value: "Not recorded")
                    }
                    if context.phase == .during {
                        if context.isStaleLive {
                            LabeledContent("● Live", value: "No recent probability")
                        } else if let current = context.currentChance {
                            LabeledContent("● Live", value: "\(Int((current * 100).rounded()))%")
                        } else {
                            LabeledContent("● Live", value: "No recent probability")
                        }
                    }
                    if context.phase == .final {
                        LabeledContent("Official result", value: verdictText(context.verdict))
                    }
                }
                Section("Provenance") {
                    Text(context.sourceDetail)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Market Details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium])
    }

    private func verdictText(_ verdict: OutcomeVerdict?) -> String {
        switch verdict {
        case .won:
            return "✓ Won"
        case .lost:
            return "✗ Lost"
        case .none:
            return "Result not confirmed"
        }
    }
}
