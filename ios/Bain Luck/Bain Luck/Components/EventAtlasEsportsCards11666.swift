import Foundation
import SwiftUI

/// #11666 / #10868 — Event Atlas Esports Story Cards (Menu Item 16c).
///
/// Surfaces native story cards on Esports match pages (`esports_csgo`, `esports_lol`,
/// `esports_dota2`, `esports_valorant`, etc.) when `ReleaseSurfaces.isEventPageAtlasEnabled()`
/// is active:
///
/// 1. **Match Winner Story (`EsportsWinnerCard10868`)**: Before the match starts
///    (`.before`), shows each team's current reading from the last 30 minutes
///    (aging after 30 minutes to `"No recent probability"`, per Decide 10-C);
///    during play (`.during`), shows the fixed `pregameMark` reference ring
///    beside each team's live reading (aged after 30 minutes to
///    `"No recent probability"`); at the final (`.final`), pairs the pre-match
///    expectation with the separately reported score (`Won match` / `Lost match`
///    and maps/rounds count) and the original contract's own venue-confirmed
///    grade (`✓ Won`, `✗ Lost`, or `"Result not confirmed"` when unsettled).
/// 2. **Map / Round Margin Story (`EsportsMarginCard10868`)**: When `GameMarketsResponse`
///    carries a map or round handicap/spread market, renders a one-block-per-unit
///    margin graphic against the required minimum threshold and, at the final,
///    fills the reported actual winning margin beside the contract's own grade.
enum EventAtlasEsportsCards11666 {

    nonisolated static let liveQuoteMaxAgeSeconds: TimeInterval = 30 * 60

    // MARK: - Sport Gating & Title Format

    nonisolated enum TitleKind: String, Equatable, Sendable {
        case csgo
        case lol
        case dota2
        case valorant
        case generic

        var defaultScoreUnitSingular: String { "map" }
        var defaultScoreUnitPlural: String { "maps" }
    }

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        guard atlasEnabled,
              let raw = sportKey?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else {
            return false
        }
        let lower = raw.lowercased()
        return lower == "esports" || lower.hasPrefix("esports_")
    }

    nonisolated static func resolveTitleKind(sportKey: String?) -> TitleKind {
        let lower = (sportKey ?? "").lowercased()
        if lower.contains("csgo") || lower.contains("cs2") || lower.contains("counter") {
            return .csgo
        }
        if lower.contains("lol") || lower.contains("league") {
            return .lol
        }
        if lower.contains("dota") {
            return .dota2
        }
        if lower.contains("valorant") {
            return .valorant
        }
        return .generic
    }

    // MARK: - Lifecycle Phase

    nonisolated enum Phase: String, Equatable, Sendable {
        case before
        case during
        case final

        var pagePhase: RugbyMatchEventPagePhase10868 {
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

    // MARK: - 1. Match Winner Story Record

    nonisolated struct WinnerSideRecord: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: String
        let outcomeID: String
        let marketTitle: String
        let teamName: String
        let isHome: Bool
        let pregameChance: Double?
        let pregameObservedAt: Date?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int
        let reportedScore: Int?
        let opponentScore: Int?
        let unitSingular: String
        let unitPlural: String

        func current(at now: Date, phase: Phase) -> WinnerSideRecord {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasEsportsCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                // Decide 10-C house rule (matching #12440 cricket and #12435 combat):
                // before the match starts there is no stored pregameMark; both
                // resolveChances(phase: .before) and current(at:, phase: .before)
                // show only the live reading from the last 30 minutes and age
                // quotes older than 30 minutes to "No recent probability".
                guard pregameChance != nil || currentChance != nil || !isStaleLive else { return self }
                return WinnerSideRecord(
                    id: id,
                    marketID: marketID,
                    outcomeID: outcomeID,
                    marketTitle: marketTitle,
                    teamName: teamName,
                    isHome: isHome,
                    pregameChance: nil,
                    pregameObservedAt: pregameObservedAt,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount,
                    reportedScore: reportedScore,
                    opponentScore: opponentScore,
                    unitSingular: unitSingular,
                    unitPlural: unitPlural
                )
            case .during:
                guard currentChance != nil || !isStaleLive else { return self }
                return WinnerSideRecord(
                    id: id,
                    marketID: marketID,
                    outcomeID: outcomeID,
                    marketTitle: marketTitle,
                    teamName: teamName,
                    isHome: isHome,
                    pregameChance: pregameChance,
                    pregameObservedAt: pregameObservedAt,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount,
                    reportedScore: reportedScore,
                    opponentScore: opponentScore,
                    unitSingular: unitSingular,
                    unitPlural: unitPlural
                )
            case .final:
                return self
            }
        }
    }

    nonisolated struct WinnerCardRecord: Equatable, Identifiable, Sendable {
        let id: String
        let eventID: String
        let phase: Phase
        let title: String
        let eyebrow: String
        let explanation: String?
        let reportCaption: String?
        let sides: [WinnerSideRecord]

        func current(at now: Date) -> WinnerCardRecord {
            guard phase != .final else { return self }
            return WinnerCardRecord(
                id: id,
                eventID: eventID,
                phase: phase,
                title: title,
                eyebrow: eyebrow,
                explanation: explanation,
                reportCaption: reportCaption,
                sides: sides.map { $0.current(at: now, phase: phase) }
            )
        }

        func toWinnerModel(homeTint: Color = DS.blue, awayTint: Color = DS.amber) -> EsportsWinnerModel10868 {
            let scope = "esports:\(eventID):winner"
            var originals: [OriginalMarketDetails9483.Original] = []
            var storySides: [EsportsWinnerSide10868] = []

            for side in sides {
                let sourceKey = side.rawSource?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? "market"
                let identity = OriginalMarketDetails9483.Identity(
                    source: sourceKey.isEmpty ? "market" : sourceKey,
                    market: side.marketID,
                    side: side.outcomeID
                )
                let selection = OriginalMarketDetails9483.Selection(scope: scope, identity: identity)
                let provenance = EventAtlasEsportsCards11666.formatSourceDetail(
                    rawSource: side.rawSource,
                    sourceCount: side.sourceCount,
                    observedAt: side.pregameObservedAt ?? side.observedAt
                )
                let liveProvenance = EventAtlasEsportsCards11666.formatSourceDetail(
                    rawSource: side.rawSource,
                    sourceCount: side.sourceCount,
                    observedAt: side.observedAt
                )

                let pregameReading: OriginalMarketDetails9483.Reading = {
                    if let prob = side.pregameChance {
                        return .value(
                            EventAtlasEsportsCards11666.formatPercent(prob),
                            placement: prob,
                            provenance: provenance
                        )
                    }
                    let missingReason = (phase == .before && side.isStaleLive)
                        ? "No recent probability"
                        : "No pre-match chance recorded"
                    return .missing(missingReason)
                }()

                let mode: OriginalMarketDetails9483.Mode
                let laterReading: OriginalMarketDetails9483.Reading?
                let grade: OriginalMarketDetails9483.Grade?

                switch phase {
                case .before:
                    mode = .pregame
                    laterReading = nil
                    grade = nil
                case .during:
                    mode = .comparison(.current)
                    if let prob = side.currentChance {
                        laterReading = .value(
                            EventAtlasEsportsCards11666.formatPercent(prob),
                            placement: prob,
                            provenance: liveProvenance
                        )
                    } else {
                        let reason = side.isStaleLive
                            ? "No recent probability"
                            : "No in-play observation recorded"
                        laterReading = .missing(reason)
                    }
                    grade = nil
                case .final:
                    laterReading = nil
                    if let verdict = side.verdict {
                        mode = .result
                        grade = OriginalMarketDetails9483.Grade(
                            words: EventAtlasEsportsCards11666.verdictLabel(verdict),
                            provenance: provenance
                        )
                    } else {
                        mode = .pregame
                        grade = nil
                    }
                }

                originals.append(
                    OriginalMarketDetails9483.Original(
                        identity: identity,
                        title: side.marketTitle,
                        outcome: side.teamName,
                        mode: mode,
                        pregame: pregameReading,
                        later: laterReading,
                        grade: grade,
                        about: OriginalMarketDetails9483.About(
                            source: EventAtlasEsportsCards11666.sourceDisplayName(
                                rawSource: side.rawSource,
                                sourceCount: side.sourceCount
                            ),
                            rules: .omitted,
                            provenance: [],
                            historicalQuote: nil
                        ),
                        beforeLabel: phase == .before ? "Current chance" : "Pre-match chance"
                    )
                )

                let report: EsportsSideReport10868? = {
                    guard phase == .final,
                          let myScore = side.reportedScore,
                          let oppScore = side.opponentScore else {
                        return nil
                    }
                    let outcomeWords: String
                    if myScore > oppScore {
                        outcomeWords = "Won match"
                    } else if myScore < oppScore {
                        outcomeWords = "Lost match"
                    } else {
                        outcomeWords = "Tied match"
                    }
                    let unit = myScore == 1 ? side.unitSingular : side.unitPlural
                    return EsportsSideReport10868(
                        outcome: outcomeWords,
                        figure: "\(myScore)",
                        unit: unit
                    )
                }()

                storySides.append(
                    EsportsWinnerSide10868(
                        selection: selection,
                        name: side.teamName,
                        tint: side.isHome ? homeTint : awayTint,
                        report: report
                    )
                )
            }

            let story = EsportsWinnerStory10868(
                sides: storySides,
                related: [],
                source: nil,
                copy: EsportsWinnerCopy10868(
                    eyebrow: eyebrow,
                    title: title,
                    graphicLabel: "Original match-winner expectations by team",
                    sideUnavailable: "Not in this update",
                    selectionMissing: "The selected outcome is not in this update",
                    explanation: explanation,
                    reportCaption: phase == .final ? reportCaption : nil,
                    resultUnavailable: "Reported score unavailable",
                    settlementLabel: "Contract result",
                    settlementUnconfirmed: "Result not confirmed",
                    relatedHeading: nil,
                    selectHint: nil,
                    detailsLabel: nil,
                    expandLabel: "Expand match-winner expectations"
                )
            )

            return EsportsWinnerModel10868(
                story: story,
                catalogue: OriginalMarketDetails9483.Catalogue(scope: scope, originals: originals),
                held: nil,
                phase: phase.pagePhase
            )
        }
    }

    // MARK: - 2. Map / Round Margin Story Record

    nonisolated struct MarginCardRecord: Equatable, Identifiable, Sendable {
        let id: String
        let eventID: String
        let marketID: String
        let outcomeID: String
        let phase: Phase
        let title: String
        let eyebrow: String
        let marketTitle: String
        let outcomeLabel: String
        let unitSingular: String
        let unitPlural: String
        let totalBlocks: Int
        let minimumBlocks: Int
        let actualMargin: Int?
        let scoreSummary: String?
        let pregameChance: Double?
        let pregameObservedAt: Date?
        let currentChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: OutcomeVerdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date) -> MarginCardRecord {
            guard phase != .final else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasEsportsCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                // Decide 10-C house rule (matching #12440 cricket and #12435 combat):
                // before the match starts there is no stored pregameMark; both
                // resolveChances(phase: .before) and current(at:, phase: .before)
                // show only the live reading from the last 30 minutes and age
                // quotes older than 30 minutes to "No recent probability".
                guard pregameChance != nil || currentChance != nil || !isStaleLive else { return self }
                return MarginCardRecord(
                    id: id,
                    eventID: eventID,
                    marketID: marketID,
                    outcomeID: outcomeID,
                    phase: phase,
                    title: title,
                    eyebrow: eyebrow,
                    marketTitle: marketTitle,
                    outcomeLabel: outcomeLabel,
                    unitSingular: unitSingular,
                    unitPlural: unitPlural,
                    totalBlocks: totalBlocks,
                    minimumBlocks: minimumBlocks,
                    actualMargin: actualMargin,
                    scoreSummary: scoreSummary,
                    pregameChance: nil,
                    pregameObservedAt: pregameObservedAt,
                    currentChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .during:
                guard currentChance != nil || !isStaleLive else { return self }
                return MarginCardRecord(
                    id: id,
                    eventID: eventID,
                    marketID: marketID,
                    outcomeID: outcomeID,
                    phase: phase,
                    title: title,
                    eyebrow: eyebrow,
                    marketTitle: marketTitle,
                    outcomeLabel: outcomeLabel,
                    unitSingular: unitSingular,
                    unitPlural: unitPlural,
                    totalBlocks: totalBlocks,
                    minimumBlocks: minimumBlocks,
                    actualMargin: actualMargin,
                    scoreSummary: scoreSummary,
                    pregameChance: pregameChance,
                    pregameObservedAt: pregameObservedAt,
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

        func toMarginModel() -> EsportsMarginModel10868 {
            let scope = "esports:\(eventID):margin:\(marketID)"
            let sourceKey = rawSource?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() ?? "market"
            let identity = OriginalMarketDetails9483.Identity(
                source: sourceKey.isEmpty ? "market" : sourceKey,
                market: marketID,
                side: outcomeID
            )
            let selection = OriginalMarketDetails9483.Selection(scope: scope, identity: identity)
            let provenance = EventAtlasEsportsCards11666.formatSourceDetail(
                rawSource: rawSource,
                sourceCount: sourceCount,
                observedAt: pregameObservedAt ?? observedAt
            )
            let liveProvenance = EventAtlasEsportsCards11666.formatSourceDetail(
                rawSource: rawSource,
                sourceCount: sourceCount,
                observedAt: observedAt
            )

            let pregameReading: OriginalMarketDetails9483.Reading = {
                if let prob = pregameChance {
                    return .value(
                        EventAtlasEsportsCards11666.formatPercent(prob),
                        placement: prob,
                        provenance: provenance
                    )
                }
                let missingReason = (phase == .before && isStaleLive)
                    ? "No recent probability"
                    : "No pre-match chance recorded"
                return .missing(missingReason)
            }()

            let mode: OriginalMarketDetails9483.Mode
            let laterReading: OriginalMarketDetails9483.Reading?
            let grade: OriginalMarketDetails9483.Grade?

            switch phase {
            case .before:
                mode = .pregame
                laterReading = nil
                grade = nil
            case .during:
                mode = .comparison(.current)
                if let prob = currentChance {
                    laterReading = .value(
                        EventAtlasEsportsCards11666.formatPercent(prob),
                        placement: prob,
                        provenance: liveProvenance
                    )
                } else {
                    let reason = isStaleLive
                        ? "No recent probability"
                        : "No in-play observation recorded"
                    laterReading = .missing(reason)
                }
                grade = nil
            case .final:
                laterReading = nil
                if let verdict {
                    mode = .result
                    grade = OriginalMarketDetails9483.Grade(
                        words: EventAtlasEsportsCards11666.verdictLabel(verdict),
                        provenance: provenance
                    )
                } else {
                    mode = .pregame
                    grade = nil
                }
            }

            let original = OriginalMarketDetails9483.Original(
                identity: identity,
                title: marketTitle,
                outcome: outcomeLabel,
                mode: mode,
                pregame: pregameReading,
                later: laterReading,
                grade: grade,
                about: OriginalMarketDetails9483.About(
                    source: EventAtlasEsportsCards11666.sourceDisplayName(
                        rawSource: rawSource,
                        sourceCount: sourceCount
                    ),
                    rules: .omitted,
                    provenance: [],
                    historicalQuote: nil
                ),
                beforeLabel: phase == .before ? "Current chance" : "Pre-match chance"
            )

            let minUnitWord = minimumBlocks == 1 ? unitSingular : unitPlural
            let actualUnitWord = (actualMargin == 1) ? unitSingular : unitPlural
            let deltaWords: String? = {
                guard phase == .final, let actual = actualMargin else { return nil }
                let diff = actual - minimumBlocks
                if diff > 0 {
                    return "\(minimumBlocks) needed · \(diff) beyond the minimum"
                } else if diff == 0 {
                    return "\(minimumBlocks) needed · exact minimum met"
                } else {
                    return "\(minimumBlocks) needed · \(abs(diff)) short of the minimum"
                }
            }()

            let story = EsportsMarginStory10868(
                selection: selection,
                scale: EsportsMarginScale10868(
                    blocks: totalBlocks,
                    minimum: minimumBlocks,
                    actual: phase == .final ? actualMargin : nil
                ),
                source: nil,
                copy: EsportsMarginCopy10868(
                    eyebrow: eyebrow,
                    title: title,
                    graphicLabel: "\(title): \(minimumBlocks) \(minUnitWord) required on a \(totalBlocks)-\(unitSingular) scale",
                    originalUnavailable: "Not in this update",
                    selectionMissing: "The selected outcome is not in this update",
                    minimumMarker: "Minimum \(minimumBlocks) \(minUnitWord)",
                    scaleStart: "0 \(unitPlural)",
                    scaleEnd: "\(totalBlocks) \(unitPlural)",
                    blockMeaning: "Each block is 1 \(unitSingular) of winning margin, not the order \(unitPlural) were played.",
                    offScale: "Margin lies outside the \(totalBlocks)-\(unitSingular) scale",
                    actualLabel: "Actual winning margin",
                    actualFigure: (phase == .final && actualMargin != nil) ? "\(actualMargin!)" : nil,
                    actualUnit: (phase == .final && actualMargin != nil) ? actualUnitWord : nil,
                    actualMarker: (phase == .final && actualMargin != nil) ? "\(actualMargin!) actual" : nil,
                    actualUnavailable: "Actual margin not reported",
                    delta: deltaWords,
                    score: phase == .final ? scoreSummary : nil,
                    resultLabel: "Prop result",
                    resultUnconfirmed: "Result not confirmed",
                    resultDetail: nil,
                    reportSource: nil,
                    selectHint: nil,
                    detailsLabel: nil,
                    expandLabel: "Expand winning margin"
                )
            )

            return EsportsMarginModel10868(
                story: story,
                catalogue: OriginalMarketDetails9483.Catalogue(scope: scope, originals: [original]),
                held: nil,
                phase: phase.pagePhase
            )
        }
    }

    // MARK: - Unified Card Enum

    nonisolated enum Card: Equatable, Identifiable, Sendable {
        case winner(WinnerCardRecord)
        case margin(MarginCardRecord)

        var id: String {
            switch self {
            case .winner(let record): return record.id
            case .margin(let record): return record.id
            }
        }

        var title: String {
            switch self {
            case .winner(let record): return record.title
            case .margin(let record): return record.title
            }
        }

        func current(at now: Date) -> Card {
            switch self {
            case .winner(let record): return .winner(record.current(at: now))
            case .margin(let record): return .margin(record.current(at: now))
            }
        }
    }

    // MARK: - Card Builders

    static func buildCards(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date(),
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> [Card] {
        guard applies(sportKey: event.sport, atlasEnabled: atlasEnabled),
              let gm = gameMarkets,
              gm.eventId == event.id else {
            return []
        }
        let phase = resolvePhase(event: event, now: now)
        let titleKind = resolveTitleKind(sportKey: event.sport)

        var cards: [Card] = []
        if let winnerCard = buildWinnerCard(
            event: event,
            gameMarkets: gm,
            phase: phase,
            titleKind: titleKind,
            now: now
        ) {
            cards.append(.winner(winnerCard))
        }
        if let marginCard = buildMarginCard(
            event: event,
            gameMarkets: gm,
            phase: phase,
            titleKind: titleKind,
            now: now
        ) {
            cards.append(.margin(marginCard))
        }
        return cards
    }

    nonisolated static func buildWinnerCard(
        event: EventDetail,
        gameMarkets: GameMarketsResponse,
        phase: Phase,
        titleKind: TitleKind,
        now: Date
    ) -> WinnerCardRecord? {
        let rows = gameMarkets.other ?? []
        guard let (homeRow, awayRow) = selectWinnerOutcomes(rows: rows, event: event) else {
            return nil
        }

        let (unitSingular, unitPlural) = inferScoreUnits(
            marketName: homeRow.marketName,
            titleKind: titleKind,
            homeScore: event.homeScore,
            awayScore: event.awayScore
        )

        let homeSide = makeWinnerSide(
            row: homeRow,
            teamName: event.homeTeam,
            isHome: true,
            phase: phase,
            reportedScore: event.homeScore,
            opponentScore: event.awayScore,
            unitSingular: unitSingular,
            unitPlural: unitPlural,
            now: now
        )
        let awaySide = makeWinnerSide(
            row: awayRow,
            teamName: event.awayTeam,
            isHome: false,
            phase: phase,
            reportedScore: event.awayScore,
            opponentScore: event.homeScore,
            unitSingular: unitSingular,
            unitPlural: unitPlural,
            now: now
        )

        let eyebrow: String = {
            switch phase {
            case .before: return "Current match-winner contracts"
            case .during: return "Pre-match vs live match-winner contracts"
            case .final: return "Pre-match expectation vs final result"
            }
        }()

        let reportCaption: String? = {
            guard phase == .final,
                  let h = event.homeScore,
                  let a = event.awayScore else {
                return nil
            }
            return "Reported final · \(event.homeTeam) \(h)–\(a) \(event.awayTeam)"
        }()

        let eventIDStr = String(event.id)
        let marketIDStr = homeSide.marketID

        return WinnerCardRecord(
            id: "esports-winner:\(eventIDStr):\(marketIDStr)",
            eventID: eventIDStr,
            phase: phase,
            title: "Match-winner expectations",
            eyebrow: eyebrow,
            explanation: "Each side shows its own original contract reading and timestamp without rescaling.",
            reportCaption: reportCaption,
            sides: [homeSide, awaySide]
        )
    }

    /// Decide 80-A (`#12274`, `#12449`): a `GameMarketOther` / `GameMarketOutcome` row
    /// does not carry its market's resolution status, so `OutcomeVerdict` is asked as
    /// for an open market (`marketResolved: false`): only an authoritative win becomes
    /// `.won`, and a row grade never mints `.lost`.
    nonisolated private static func otherRowVerdict(
        isWinner: Bool?,
        resolutionSource: String?,
        phase: Phase
    ) -> OutcomeVerdict? {
        guard phase == .final else { return nil }
        return OutcomeVerdict.verdict(
            isWinner: isWinner,
            resolutionSource: resolutionSource,
            marketResolved: false
        ) == .won ? .won : nil
    }

    nonisolated private static func makeWinnerSide(
        row: GameMarketOther,
        teamName: String,
        isHome: Bool,
        phase: Phase,
        reportedScore: Int?,
        opponentScore: Int?,
        unitSingular: String,
        unitPlural: String,
        now: Date
    ) -> WinnerSideRecord {
        let observedDate = row.observedAt?.asDate
        let isStale = isQuoteStale(observedAt: observedDate, now: now, phase: phase)
        let (pregame, current) = resolveChances(
            probability: row.probability,
            pregameMark: row.pregameMark,
            phase: phase,
            isStale: isStale
        )
        let verdict = otherRowVerdict(
            isWinner: row.isWinner,
            resolutionSource: row.resolutionSource,
            phase: phase
        )

        let marketIDVal = row._marketId ?? row._marketIds?.first ?? 0
        let outcomeIDVal = isHome ? "home:\(teamName)" : "away:\(teamName)"

        return WinnerSideRecord(
            id: "\(marketIDVal):\(outcomeIDVal)",
            marketID: String(marketIDVal),
            outcomeID: outcomeIDVal,
            marketTitle: row.marketName,
            teamName: teamName,
            isHome: isHome,
            pregameChance: pregame,
            pregameObservedAt: observedDate,
            currentChance: current,
            observedAt: observedDate,
            isStaleLive: isStale && phase != .final,
            verdict: verdict,
            rawSource: row.source,
            sourceCount: 1,
            reportedScore: reportedScore,
            opponentScore: opponentScore,
            unitSingular: unitSingular,
            unitPlural: unitPlural
        )
    }

    nonisolated static func buildMarginCard(
        event: EventDetail,
        gameMarkets: GameMarketsResponse,
        phase: Phase,
        titleKind: TitleKind,
        now: Date
    ) -> MarginCardRecord? {
        guard let candidate = selectMarginCandidate(
            gameMarkets: gameMarkets,
            event: event,
            titleKind: titleKind
        ) else {
            return nil
        }

        let observedDate = candidate.row.observedAt?.asDate
        let isStale = isQuoteStale(observedAt: observedDate, now: now, phase: phase)
        let (pregame, current) = resolveChances(
            probability: candidate.row.probability,
            pregameMark: candidate.row.pregameMark,
            phase: phase,
            isStale: isStale
        )
        let verdict = otherRowVerdict(
            isWinner: candidate.row.isWinner,
            resolutionSource: candidate.row.resolutionSource,
            phase: phase
        )

        let actualMargin: Int? = {
            guard phase == .final,
                  let h = event.homeScore,
                  let a = event.awayScore else {
                return nil
            }
            let rawMargin = candidate.isHomeFavoured ? (h - a) : (a - h)
            let clamped = max(0, rawMargin)
            guard clamped <= candidate.totalBlocks else { return nil }
            return clamped
        }()

        let scoreSummary: String? = {
            guard phase == .final,
                  let h = event.homeScore,
                  let a = event.awayScore else {
                return nil
            }
            return "\(event.homeTeam) \(h)–\(a) \(event.awayTeam)"
        }()

        let eyebrow: String = {
            switch phase {
            case .before: return "Current margin threshold"
            case .during: return "Live margin threshold"
            case .final: return "Required margin vs final score"
            }
        }()

        let eventIDStr = String(event.id)
        let marketIDVal = candidate.row._marketId ?? candidate.row._marketIds?.first ?? 0
        let marketIDStr = String(marketIDVal)
        let outcomeIDStr = "margin:\(candidate.outcomeLabel)"

        return MarginCardRecord(
            id: "esports-margin:\(eventIDStr):\(marketIDStr)",
            eventID: eventIDStr,
            marketID: marketIDStr,
            outcomeID: outcomeIDStr,
            phase: phase,
            title: candidate.cardTitle,
            eyebrow: eyebrow,
            marketTitle: candidate.row.marketName,
            outcomeLabel: candidate.outcomeLabel,
            unitSingular: candidate.unitSingular,
            unitPlural: candidate.unitPlural,
            totalBlocks: candidate.totalBlocks,
            minimumBlocks: candidate.minimumBlocks,
            actualMargin: actualMargin,
            scoreSummary: scoreSummary,
            pregameChance: pregame,
            pregameObservedAt: observedDate,
            currentChance: current,
            observedAt: observedDate,
            isStaleLive: isStale && phase != .final,
            verdict: verdict,
            rawSource: candidate.row.source,
            sourceCount: 1
        )
    }

    // MARK: - Market Election & Parsing Helpers

    nonisolated private static func selectWinnerOutcomes(
        rows: [GameMarketOther],
        event: EventDetail
    ) -> (home: GameMarketOther, away: GameMarketOther)? {
        let homeTarget = normalizeTeam(event.homeTeam)
        let awayTarget = normalizeTeam(event.awayTeam)
        guard !homeTarget.isEmpty, !awayTarget.isEmpty else { return nil }

        var homeCandidate: GameMarketOther?
        var awayCandidate: GameMarketOther?

        for row in rows {
            let lowerMarket = row.marketName.lowercased()
            if lowerMarket.contains("handicap")
                || lowerMarket.contains("spread")
                || lowerMarket.contains("total")
                || lowerMarket.contains("over/under") {
                continue
            }
            let outLower = normalizeTeam(row.outcomeName)
            if outLower.isEmpty || outLower == "no" { continue }

            let matchesHome = (outLower == homeTarget)
                || (outLower.contains(homeTarget) && !outLower.contains(awayTarget))
            let matchesAway = (outLower == awayTarget)
                || (outLower.contains(awayTarget) && !outLower.contains(homeTarget))

            if matchesHome && homeCandidate == nil {
                homeCandidate = row
            } else if matchesAway && awayCandidate == nil {
                awayCandidate = row
            }
            if let h = homeCandidate, let a = awayCandidate {
                return (h, a)
            }
        }
        return nil
    }

    private struct MarginCandidate {
        let row: GameMarketOutcome
        let outcomeLabel: String
        let cardTitle: String
        let isHomeFavoured: Bool
        let minimumBlocks: Int
        let totalBlocks: Int
        let unitSingular: String
        let unitPlural: String
    }

    nonisolated private static func selectMarginCandidate(
        gameMarkets: GameMarketsResponse,
        event: EventDetail,
        titleKind: TitleKind
    ) -> MarginCandidate? {
        let convertedOtherSpreads: [GameMarketOutcome] = (gameMarkets.other ?? []).compactMap { row in
            let lower = "\(row.marketName) \(row.outcomeName)".lowercased()
            guard lower.contains("handicap") || lower.contains("margin") || lower.contains("spread") else {
                return nil
            }
            return GameMarketOutcome(
                _marketId: row._marketId,
                _marketIds: row._marketIds,
                contributorOutcomeIds: row.contributorOutcomeIds,
                marketName: row.marketName,
                outcomeName: row.outcomeName,
                probability: row.probability,
                source: row.source,
                threshold: nil,
                overProbability: nil,
                marketType: "spreads",
                movement: nil,
                period: nil,
                isWinner: row.isWinner,
                resolutionSource: row.resolutionSource,
                observedAt: row.observedAt,
                pregameMark: row.pregameMark
            )
        }
        let spreadRows = (gameMarkets.spreads ?? []) + convertedOtherSpreads

        for row in spreadRows {
            let combinedText = "\(row.outcomeName) \(row.marketName)"
            let handicapValue: Double? = {
                if let threshold = row.threshold, threshold < 0 {
                    return threshold
                }
                return extractNegativeHandicap(from: row.outcomeName)
                    ?? extractNegativeHandicapForTeam(in: row.marketName, teamName: row.outcomeName)
                    ?? extractNegativeHandicap(from: row.marketName)
            }()
            guard let minusHandicap = handicapValue, minusHandicap < 0 else { continue }

            let minimum = Int(floor(abs(minusHandicap))) + 1
            guard minimum >= 1 else { continue }

            let isRounds = combinedText.lowercased().contains("round")
            let unitSingular = isRounds ? "round" : titleKind.defaultScoreUnitSingular
            let unitPlural = isRounds ? "rounds" : titleKind.defaultScoreUnitPlural
            let totalBlocks: Int = {
                if isRounds {
                    return max(14, minimum + 2)
                }
                if combinedText.lowercased().contains("bo5") || minimum >= 3 {
                    return max(3, minimum)
                }
                return max(2, minimum)
            }()
            guard minimum <= totalBlocks else { continue }

            let homeNorm = normalizeTeam(event.homeTeam)
            let awayNorm = normalizeTeam(event.awayTeam)
            let outNorm = normalizeTeam(row.outcomeName)
            let isHome = outNorm.contains(homeNorm) || (!outNorm.contains(awayNorm))
            let teamDisplay = isHome ? event.homeTeam : event.awayTeam
            let formattedHandicap = String(format: "-%.1f", abs(minusHandicap))
            let outcomeDisplay = row.outcomeName.contains("-")
                ? row.outcomeName
                : "\(teamDisplay) (\(formattedHandicap) \(unitPlural))"
            let cardTitle = isRounds ? "Round winning margin" : "Map winning margin"

            return MarginCandidate(
                row: row,
                outcomeLabel: outcomeDisplay,
                cardTitle: cardTitle,
                isHomeFavoured: isHome,
                minimumBlocks: minimum,
                totalBlocks: totalBlocks,
                unitSingular: unitSingular,
                unitPlural: unitPlural
            )
        }
        return nil
    }

    nonisolated private static func extractNegativeHandicap(from text: String) -> Double? {
        let pattern = #"-\d+(?:\.\d+)?"#
        guard let regex = try? NSRegularExpression(pattern: pattern) else { return nil }
        let range = NSRange(text.startIndex..<text.endIndex, in: text)
        guard let match = regex.firstMatch(in: text, range: range),
              let swiftRange = Range(match.range, in: text),
              let value = Double(text[swiftRange]),
              value < 0 else {
            return nil
        }
        return value
    }

    nonisolated private static func extractNegativeHandicapForTeam(in marketName: String, teamName: String) -> Double? {
        let escaped = NSRegularExpression.escapedPattern(for: teamName.trimmingCharacters(in: .whitespacesAndNewlines))
        guard !escaped.isEmpty else { return extractNegativeHandicap(from: marketName) }
        let pattern = "\(escaped)\\s*\\((-\\d+(?:\\.\\d+)?)\\)"
        if let regex = try? NSRegularExpression(pattern: pattern, options: [.caseInsensitive]),
           let match = regex.firstMatch(in: marketName, range: NSRange(marketName.startIndex..<marketName.endIndex, in: marketName)),
           match.numberOfRanges > 1,
           let swiftRange = Range(match.range(at: 1), in: marketName),
           let value = Double(marketName[swiftRange]),
           value < 0 {
            return value
        }
        return nil
    }

    nonisolated private static func inferScoreUnits(
        marketName: String,
        titleKind: TitleKind,
        homeScore: Int?,
        awayScore: Int?
    ) -> (singular: String, plural: String) {
        let lower = marketName.lowercased()
        let maxScore = max(homeScore ?? 0, awayScore ?? 0)
        if lower.contains("bo1") || lower.contains("round") || maxScore > 5 {
            return ("round", "rounds")
        }
        return (titleKind.defaultScoreUnitSingular, titleKind.defaultScoreUnitPlural)
    }

    nonisolated private static func normalizeTeam(_ name: String) -> String {
        name.lowercased().trimmingCharacters(in: .whitespacesAndNewlines)
    }

    nonisolated private static func isQuoteStale(
        observedAt: Date?,
        now: Date,
        phase: Phase
    ) -> Bool {
        guard phase != .final else { return false }
        guard let observedAt else { return false }
        return now.timeIntervalSince(observedAt) > liveQuoteMaxAgeSeconds
    }

    nonisolated private static func normalizeUnitProbability(_ raw: Double?) -> Double? {
        guard let raw, raw.isFinite else { return nil }
        let unit = raw > 1.0 ? raw / 100.0 : raw
        guard unit >= 0.0, unit <= 1.0 else { return nil }
        return unit
    }

    nonisolated static func resolveChances(
        probability: Double?,
        pregameMark: Double?,
        phase: Phase,
        isStale: Bool
    ) -> (pregame: Double?, current: Double?) {
        let opening = normalizeUnitProbability(pregameMark)
        let latest = normalizeUnitProbability(probability)
        switch phase {
        case .before:
            // Decide 10-C house rule (matching #12440 cricket and #12435 combat):
            // before the start there is no stored opening/pregame mark; show only
            // the live reading from the last 30 minutes, otherwise nil
            // ("No recent probability").
            return (isStale ? nil : latest, nil)
        case .during:
            let pre = opening
            let cur = isStale ? nil : latest
            return (pre, cur)
        case .final:
            let pre = opening
            return (pre, nil)
        }
    }

    nonisolated static func formatPercent(_ unit: Double) -> String {
        "\(Int((unit * 100.0).rounded()))%"
    }

    nonisolated static func verdictLabel(_ verdict: OutcomeVerdict) -> String {
        switch verdict {
        case .won: return "✓ Won"
        case .lost: return "✗ Lost"
        }
    }

    // MARK: - Provenance Formatting

    nonisolated static func sourceDisplayName(rawSource: String?, sourceCount: Int) -> String? {
        if sourceCount > 1 {
            return "\(sourceCount) sources"
        }
        guard let rawSource, !rawSource.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        return SourceLabels.label(for: rawSource) ?? "Market data"
    }

    nonisolated static func formatSourceDetail(
        rawSource: String?,
        sourceCount: Int,
        observedAt: Date?
    ) -> String? {
        let sourcePart = sourceDisplayName(rawSource: rawSource, sourceCount: sourceCount)
        let timePart = observedAt.flatMap { date in
            SourceAge.preciseStamp(ISO8601DateFormatter().string(from: date))
        }
        switch (timePart, sourcePart) {
        case (let t?, let s?):
            return "\(t) · \(s)"
        case (let t?, nil):
            return t
        case (nil, let s?):
            return s
        case (nil, nil):
            return nil
        }
    }
}

// MARK: - Card View Wrapper for EventDetailView Deck

struct EventAtlasEsportsCardView11666: View {
    let card: EventAtlasEsportsCards11666.Card
    var awayColor: Color = DS.amber
    var homeColor: Color = DS.blue

    var body: some View {
        Group {
            switch card {
            case .winner(let record):
                EsportsWinnerCard10868(
                    model: record.toWinnerModel(homeTint: homeColor, awayTint: awayColor)
                )
            case .margin(let record):
                EsportsMarginCard10868(
                    model: record.toMarginModel()
                )
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(DS.cardBg, in: RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(DS.border, lineWidth: 1)
        )
    }
}
