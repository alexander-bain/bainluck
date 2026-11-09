import Foundation
import SwiftUI

/// #11666 (Item 16d-3, Decide 91-C) — Native Horse Racing, Olympics, Poker, Ceremony,
/// Earnings & Weather Atlas Story Cards:
///   1. **Primary Event / Field Outlook Card (`FieldPhaseHeadlinePresentation10868` + `FieldOutlookBarsPresentation10868`)**:
///      - **Horse Racing (`horse_racing*`, `horseracing*`)**, **Olympics (`olympics*`, `*_olympics`)**,
///        **Poker (`poker*`, `wsop*`, `wpt*`)**, **Ceremony / Awards (`entertainment*`, `ceremony*`, `awards*`)**,
///        **Earnings / Economics (`economics*`, `earnings*`, `finance*`)**, and **Weather (`weather*`, `climate*`)**:
///        Displays all outcomes (2–6 runners, contenders, nominees, or binary sides) from a single primary
///        market on an unscaled 0–100% scale.
///      - **Decide 10-C House Rule**:
///        - `.before`: Shows ONLY the live reading (`probability`) from the last 30 minutes
///          (`isStale ? nil : latest`), labelled `"Current chance"`, and ages it after 30 minutes
///          to `"No recent probability"`. Never uses `pregameMark` before event start.
///        - `.during`: Shows `pregameMark` (`"Opening chance"`) as the fixed reference beside
///          the live reading (`"Live chance"`, aged after 30 minutes to `"No recent probability"`).
///        - `.final`: Shows `pregameMark` (`"Opening chance"`) beside the Decide 80-A
///          venue-confirmed contract grade (`"✓ Won"` only when authoritatively settled, else
///          `"Result not confirmed"`; a row grade never mints `"✗ Lost"`).
///   2. **Threshold, Line & Total Story Card (`FieldPhaseHeadlinePresentation10868`)**:
///      - Surfaces spreads, totals, and threshold/bracket markets (race margins, medal/point totals,
///        earnings thresholds, temperature/rainfall brackets) with Decide 10-C and Decide 80-A rules.
enum EventAtlasSpecialEventCards11666 {

    /// 30-minute live-quote staleness window per Decide 10-C.
    nonisolated static let staleThresholdSeconds: TimeInterval = 30 * 60

    // MARK: - Sport / Category Gating

    nonisolated enum EventKind: String, Equatable, Sendable {
        case horseRacing
        case olympics
        case poker
        case ceremony
        case earnings
        case weather

        var badgeTitle: String {
            switch self {
            case .horseRacing: return "Horse Racing"
            case .olympics: return "Olympics"
            case .poker: return "Poker"
            case .ceremony: return "Ceremony & Awards"
            case .earnings: return "Earnings & Economics"
            case .weather: return "Weather"
            }
        }

        var outlookEyebrow: String {
            switch self {
            case .horseRacing: return "HORSE RACING · RACE OUTLOOK"
            case .olympics: return "OLYMPICS · MEDAL & EVENT OUTLOOK"
            case .poker: return "POKER · TABLE OUTLOOK"
            case .ceremony: return "CEREMONY · AWARD OUTLOOK"
            case .earnings: return "EARNINGS · RELEASE OUTLOOK"
            case .weather: return "WEATHER · FORECAST OUTLOOK"
            }
        }

        var thresholdEyebrow: String {
            switch self {
            case .horseRacing: return "HORSE RACING · WINNING MARGIN & TOTALS"
            case .olympics: return "OLYMPICS · LINE & TOTALS"
            case .poker: return "POKER · HAND & STACK TOTALS"
            case .ceremony: return "CEREMONY · CATEGORY TOTALS"
            case .earnings: return "EARNINGS · THRESHOLD & GUIDANCE"
            case .weather: return "WEATHER · TEMPERATURE & PRECIPITATION"
            }
        }
    }

    private static let horseRacingPrefixes: [String] = [
        "horse_racing",
        "horseracing",
        "equestrian"
    ]

    private static let olympicsPrefixes: [String] = [
        "olympics",
        "winter_olympics",
        "summer_olympics",
        "curling_olympics",
        "fieldhockey_olympics",
        "track_and_field",
        "swimming_olympics",
        "gymnastics_olympics"
    ]

    private static let pokerPrefixes: [String] = [
        "poker",
        "wsop",
        "wpt"
    ]

    private static let ceremonyPrefixes: [String] = [
        "ceremony",
        "entertainment",
        "awards",
        "oscars",
        "emmys",
        "grammys",
        "golden_globes"
    ]

    private static let earningsPrefixes: [String] = [
        "earnings",
        "economics",
        "finance",
        "macro"
    ]

    private static let weatherPrefixes: [String] = [
        "weather",
        "climate",
        "hurricane",
        "temperature"
    ]

    nonisolated static func eventKind(sportKey: String?) -> EventKind? {
        guard let raw = sportKey else { return nil }
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !lower.isEmpty else { return nil }

        if horseRacingPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0 + "_") }) {
            return .horseRacing
        }
        if pokerPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0 + "_") }) {
            return .poker
        }
        if ceremonyPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0 + "_") }) {
            return .ceremony
        }
        if earningsPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0 + "_") }) {
            return .earnings
        }
        if weatherPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0 + "_") }) {
            return .weather
        }
        if olympicsPrefixes.contains(where: { lower == $0 || lower.hasPrefix($0 + "_") }) {
            return .olympics
        }
        return nil
    }

    nonisolated static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && eventKind(sportKey: sportKey) != nil
    }

    // MARK: - Domain Models

    nonisolated struct OutcomeRow: Equatable, Identifiable, Sendable {
        let id: String
        let marketID: Int
        let marketTitle: String
        let outcomeName: String
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

    nonisolated struct EventOutlookCard: Equatable, Identifiable, Sendable {
        let id: String
        let eventId: Int
        let marketId: Int
        let title: String
        let eventKind: EventKind
        let phase: FieldOutlookPhase10868
        let scoreSummary: String?
        let rows: [OutcomeRow]
        let headlineInput: FieldHeadlineInput10868
        let outlookInput: FieldOutlookInput10868?
    }

    nonisolated struct ThresholdOrTotalCard: Equatable, Identifiable, Sendable {
        let id: String
        let eventId: Int
        let marketId: Int
        let title: String
        let eventKind: EventKind
        let phase: FieldOutlookPhase10868
        let scoreSummary: String?
        let rows: [OutcomeRow]
        let headlineInput: FieldHeadlineInput10868
    }

    nonisolated enum Card: Equatable, Identifiable, Sendable {
        case eventOutlook(EventOutlookCard)
        case thresholdOrTotal(ThresholdOrTotalCard)

        var id: String {
            switch self {
            case .eventOutlook(let card): return card.id
            case .thresholdOrTotal(let card): return card.id
            }
        }

        var title: String {
            switch self {
            case .eventOutlook(let card): return card.title
            case .thresholdOrTotal(let card): return card.title
            }
        }

        /// Re-evaluates the 30-minute live-quote staleness window at `now` for `.before` and `.during` cards.
        /// Final cards are immutable history and return `self`.
        func current(at now: Date) -> Card {
            switch self {
            case .eventOutlook(let card):
                guard card.phase != .final,
                      let rebuilt = EventAtlasSpecialEventCards11666.buildEventOutlookCard(
                          eventId: card.eventId,
                          scoreSummary: card.scoreSummary,
                          rows: card.rows,
                          eventKind: card.eventKind,
                          phase: card.phase,
                          now: now
                      ) else {
                    return self
                }
                return .eventOutlook(rebuilt)
            case .thresholdOrTotal(let card):
                guard card.phase != .final,
                      let rebuilt = EventAtlasSpecialEventCards11666.buildThresholdOrTotalCard(
                          eventId: card.eventId,
                          scoreSummary: card.scoreSummary,
                          marketId: card.marketId,
                          title: card.title,
                          rows: card.rows,
                          eventKind: card.eventKind,
                          phase: card.phase,
                          now: now
                      ) else {
                    return self
                }
                return .thresholdOrTotal(rebuilt)
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

    /// `GameMarketsResponse` serves probabilities (`probability`, `pregameMark`, `overProbability`)
    /// as unit fractions in `0.0...1.0`. Values outside `0.0...1.0` or non-finite values are rejected.
    nonisolated static func validProbability(_ raw: Double?) -> Double? {
        guard let raw, raw.isFinite, raw >= 0.0, raw <= 1.0 else { return nil }
        return raw
    }

    nonisolated static func isQuoteStale(
        observedAt: Date?,
        now: Date,
        phase: FieldOutlookPhase10868
    ) -> Bool {
        guard phase != .final, let observedAt else { return false }
        return now.timeIntervalSince(observedAt) > staleThresholdSeconds
    }

    /// Decide 10-C chance resolution:
    /// - `.before`: `earlierProb` is the live quote (`isStale ? nil : probability`), never `pregameMark`.
    /// - `.during`: `earlierProb` is `pregameMark` (the fixed opening baseline); `laterProb` is `isStale ? nil : probability`.
    /// - `.final`: `earlierProb` is `pregameMark` (the fixed opening baseline); `laterProb` is `nil` (replaced by contract result).
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
            return (earlier: isStale ? nil : latest, later: nil)
        case .during:
            return (earlier: pregame, later: isStale ? nil : latest)
        case .final:
            return (earlier: pregame, later: nil)
        }
    }

    nonisolated static func formatPercent(_ probability: Double) -> String {
        "\(Int((probability * 100).rounded()))%"
    }

    // MARK: - Venue-Free Provenance Formatting

    nonisolated static func provenanceSourceLabel(_ source: String?) -> String {
        guard let raw = source?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased(),
              !raw.isEmpty else {
            return "Single source"
        }
        if raw == "blend" || raw == "blended" || raw == "combined" || raw.contains(",") || raw.contains("+") {
            return "Blended · 2+ sources"
        }
        return "Single source"
    }

    nonisolated static func readingDetailLine(
        observedAt: Date?,
        source: String?,
        fallback: String
    ) -> String {
        let prov = provenanceSourceLabel(source)
        if let observedAt {
            let formatter = DateFormatter()
            formatter.locale = Locale(identifier: "en_US_POSIX")
            formatter.timeZone = TimeZone(secondsFromGMT: 0)
            formatter.dateFormat = "HH:mm 'UTC'"
            return "\(prov) · \(formatter.string(from: observedAt))"
        }
        return "\(prov) · \(fallback)"
    }

    // MARK: - Score Summary

    nonisolated static func finalScoreSummary(event: EventDetail) -> String? {
        guard let homeScore = event.homeScore,
              let awayScore = event.awayScore else {
            return nil
        }
        let (awayShort, homeShort) = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam
        )
        return "\(homeShort) \(homeScore)–\(awayScore) \(awayShort)"
    }

    // MARK: - Deck Builder

    nonisolated static func buildCards(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date(),
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> [Card] {
        guard atlasEnabled,
              let eventKind = eventKind(sportKey: event.sport),
              let gameMarkets,
              gameMarkets.eventId == event.id else {
            return []
        }

        let phase = resolvePhase(event: event, now: now)

        var cards: [Card] = []

        // 1. Primary Event / Field Outlook Card
        let outcomeRows = extractPrimaryOutcomeRows(event: event, gameMarkets: gameMarkets)
        if !outcomeRows.isEmpty,
           let outlookCard = buildEventOutlookCard(
               event: event,
               rows: outcomeRows,
               eventKind: eventKind,
               phase: phase,
               now: now
           ) {
            cards.append(.eventOutlook(outlookCard))
        }

        // 2. Threshold / Spread / Total Story Cards (up to 2 distinct markets)
        let primaryMarketId = outcomeRows.first?.marketID
        let propGroups = extractThresholdGroups(
            gameMarkets: gameMarkets,
            excludingMarketId: primaryMarketId
        )
        for group in propGroups.prefix(2) {
            if let propCard = buildThresholdOrTotalCard(
                event: event,
                marketId: group.marketId,
                title: group.title,
                rows: group.rows,
                eventKind: eventKind,
                phase: phase,
                now: now
            ) {
                cards.append(.thresholdOrTotal(propCard))
            }
        }

        return cards
    }

    // MARK: - Outcome & Threshold Extraction from GameMarketsResponse

    /// Extracts primary event/field outcome rows grouped strictly by a single `marketId`.
    /// Requires at least 2 distinct outcome rows in that market so single-row fragments or
    /// partial-scope markets never build a primary Event Outlook card.
    nonisolated static func extractPrimaryOutcomeRows(
        event: EventDetail,
        gameMarkets: GameMarketsResponse
    ) -> [OutcomeRow] {
        let eventKind = Self.eventKind(sportKey: event.sport)
        var marketOrder: [Int] = []
        var rowsByMarket: [Int: [OutcomeRow]] = [:]
        var seenNamesByMarket: [Int: Set<String>] = [:]

        for (idx, row) in (gameMarkets.other ?? []).enumerated() {
            guard let marketId = row._marketId ?? row._marketIds?.first else {
                continue
            }
            let marketLower = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            guard !isPartialScopeMarketName(marketLower, eventKind: eventKind),
                  !isThresholdOrTotalName(marketLower) else {
                continue
            }
            let outcomeRaw = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !outcomeRaw.isEmpty else {
                continue
            }
            let normOutcome = outcomeRaw.lowercased()
            if rowsByMarket[marketId] == nil {
                marketOrder.append(marketId)
                rowsByMarket[marketId] = []
                seenNamesByMarket[marketId] = []
            }
            guard !(seenNamesByMarket[marketId]?.contains(normOutcome) ?? false) else {
                continue
            }
            seenNamesByMarket[marketId]?.insert(normOutcome)

            rowsByMarket[marketId]?.append(
                OutcomeRow(
                    id: "special-outcome-\(marketId)-\(idx)",
                    marketID: marketId,
                    marketTitle: row.marketName,
                    outcomeName: outcomeRaw,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            )
        }

        // Require at least 2 outcomes in the same market ID (cap at 6 contenders for clean 390 px layout).
        if let validMarketId = marketOrder.first(where: { id in
            (rowsByMarket[id]?.count ?? 0) >= 2
        }), let rows = rowsByMarket[validMarketId] {
            return Array(rows.prefix(6))
        }

        return []
    }

    nonisolated static func isPartialScopeMarketName(
        _ lower: String,
        eventKind: EventKind? = nil
    ) -> Bool {
        if lower.contains("half")
            || lower.contains("period")
            || lower.contains("first set")
            || lower.contains("first leg")
            || lower.contains("first game")
            || lower.contains("opening lap") {
            return true
        }
        let orderedWords = lower.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
        let words = Set(orderedWords)
        if lower.range(
            of: #"\b(1st|2nd|3rd|4th)\s+(set|leg|game|map|period|heat|lap)\b"#,
            options: .regularExpression
        ) != nil {
            return true
        }
        if lower.range(
            of: #"\b(set|leg|game|map|period|heat|lap)\s*\d+\b"#,
            options: .regularExpression
        ) != nil {
            return true
        }
        if eventKind != .earnings {
            if words.contains("q1")
                || words.contains("q2")
                || words.contains("q3")
                || words.contains("q4") {
                return true
            }
            for idx in 0..<max(0, orderedWords.count - 1) {
                if PeriodLabel.normalize("\(orderedWords[idx + 1]) \(orderedWords[idx])").hasPrefix("Q") {
                    return true
                }
            }
        }
        return false
    }

    nonisolated static func isThresholdOrTotalName(_ lower: String) -> Bool {
        if lower.contains("moneyline") || lower.contains("money line") || lower.contains("winner") {
            return false
        }
        if lower.contains("spread")
            || lower.contains("handicap")
            || lower.contains("margin")
            || lower.contains("total")
            || lower.contains("over/under")
            || lower.contains("threshold")
            || lower.contains("temperature")
            || lower.contains("rainfall")
            || lower.contains("precipitation") {
            return true
        }
        let words = lower.components(separatedBy: CharacterSet.alphanumerics.inverted).filter { !$0.isEmpty }
        return words.contains("line")
    }

    private struct ThresholdGroup {
        let marketId: Int
        let title: String
        let rows: [OutcomeRow]
    }

    nonisolated private static func extractThresholdGroups(
        gameMarkets: GameMarketsResponse,
        excludingMarketId: Int?
    ) -> [ThresholdGroup] {
        var groups: [ThresholdGroup] = []

        if let spreads = gameMarkets.spreads, !spreads.isEmpty {
            let rows: [OutcomeRow] = spreads.prefix(4).enumerated().compactMap { idx, row in
                guard let rowMarketId = row._marketId ?? row._marketIds?.first else { return nil }
                let label: String = {
                    if let t = row.threshold {
                        let outLower = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                        let isOverUnder = outLower.hasPrefix("over") || outLower.hasPrefix("under")
                        let sign = (!isOverUnder && t >= 0) ? "+" : ""
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
                    id: "special-spread-\(rowMarketId)-\(idx)",
                    marketID: rowMarketId,
                    marketTitle: row.marketName,
                    outcomeName: label,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }
            if let first = rows.first {
                let singleMarketRows = rows.filter { $0.marketID == first.marketID }
                groups.append(ThresholdGroup(marketId: first.marketID, title: first.marketTitle, rows: singleMarketRows))
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
                    id: "special-total-\(rowMarketId)-\(idx)",
                    marketID: rowMarketId,
                    marketTitle: row.marketName,
                    outcomeName: label,
                    probability: row.overProbability ?? row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }
            if let first = rows.first {
                let singleMarketRows = rows.filter { $0.marketID == first.marketID }
                groups.append(ThresholdGroup(marketId: first.marketID, title: first.marketTitle, rows: singleMarketRows))
            }
        }

        if groups.isEmpty {
            let thresholdOthers = (gameMarkets.other ?? []).filter { row in
                guard let mid = row._marketId ?? row._marketIds?.first else { return false }
                if let excludingMarketId, mid == excludingMarketId { return false }
                return isThresholdOrTotalName(row.marketName.lowercased())
            }
            let rows: [OutcomeRow] = thresholdOthers.prefix(4).enumerated().compactMap { idx, row in
                guard let rowMarketId = row._marketId ?? row._marketIds?.first else { return nil }
                return OutcomeRow(
                    id: "special-other-prop-\(rowMarketId)-\(idx)",
                    marketID: rowMarketId,
                    marketTitle: row.marketName,
                    outcomeName: row.outcomeName,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    source: row.source,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource
                )
            }
            if let first = rows.first {
                let firstMarketId = first.marketID
                let singleMarketRows = rows.filter { $0.marketID == firstMarketId }
                groups.append(ThresholdGroup(marketId: firstMarketId, title: first.marketTitle, rows: singleMarketRows))
            }
        }

        return groups
    }

    // MARK: - 1. Primary Event / Field Outlook Card Builder

    static func buildEventOutlookCard(
        event: EventDetail,
        rows: [OutcomeRow],
        eventKind: EventKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> EventOutlookCard? {
        buildEventOutlookCard(
            eventId: event.id,
            scoreSummary: finalScoreSummary(event: event),
            rows: rows,
            eventKind: eventKind,
            phase: phase,
            now: now
        )
    }

    static func buildEventOutlookCard(
        eventId: Int,
        scoreSummary: String?,
        rows: [OutcomeRow],
        eventKind: EventKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> EventOutlookCard? {
        guard let first = rows.first else { return nil }
        let marketId = first.marketID
        let scope = "special-outlook-\(eventId)-\(marketId)"
        let shapes: [FieldHeadlineKeyShape10868] = [.circle, .square, .diamond]

        let earlierLabel = phase == .before ? "Current chance" : "Opening chance"
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
                fallback: phase == .before ? "Recorded quote" : "Opening quote"
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

            let shape = shapes[index % shapes.count]
            displayed.append(
                FieldHeadlineSlot10868(
                    ref: ref,
                    name: row.outcomeName,
                    compactName: nil,
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
                let finishDetail = scoreSummary ?? "Official result"
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
                    shortLabel: row.outcomeName
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

        let stateBlock = buildHeadlineState(scoreSummary: scoreSummary, eventKind: eventKind, phase: phase)
        let headlineCopy = FieldHeadlineCopy10868(
            eyebrow: eventKind.outlookEyebrow,
            title: first.marketTitle,
            graphicLabel: "\(eventKind.badgeTitle) outcome outlook",
            beforeLabel: earlierLabel,
            recordedLabel: laterLabel,
            beforeUnavailable: phase == .before ? "No recent probability" : "Not recorded",
            recordedUnavailable: "No recent probability",
            finishLabel: "Contract result",
            finishUnavailable: "Result not confirmed",
            empty: "No outcomes in this update",
            aboutLabel: "About this market",
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
                title: "Outcome comparison",
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

        return EventOutlookCard(
            id: "special-outlook-\(eventId)-\(marketId)",
            eventId: eventId,
            marketId: marketId,
            title: first.marketTitle,
            eventKind: eventKind,
            phase: phase,
            scoreSummary: scoreSummary,
            rows: rows,
            headlineInput: headlineInput,
            outlookInput: outlookInput
        )
    }

    // MARK: - 2. Threshold, Line & Total Story Card Builder

    static func buildThresholdOrTotalCard(
        event: EventDetail,
        marketId: Int,
        title: String,
        rows: [OutcomeRow],
        eventKind: EventKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> ThresholdOrTotalCard? {
        buildThresholdOrTotalCard(
            eventId: event.id,
            scoreSummary: finalScoreSummary(event: event),
            marketId: marketId,
            title: title,
            rows: rows,
            eventKind: eventKind,
            phase: phase,
            now: now
        )
    }

    static func buildThresholdOrTotalCard(
        eventId: Int,
        scoreSummary: String?,
        marketId: Int,
        title: String,
        rows: [OutcomeRow],
        eventKind: EventKind,
        phase: FieldOutlookPhase10868,
        now: Date = Date()
    ) -> ThresholdOrTotalCard? {
        guard !rows.isEmpty else { return nil }
        let scope = "special-prop-\(eventId)-\(marketId)"
        let shapes: [FieldHeadlineKeyShape10868] = [.circle, .square, .diamond]

        let earlierLabel = phase == .before ? "Current chance" : "Opening chance"
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
                fallback: phase == .before ? "Recorded quote" : "Opening quote"
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
                let finishDetail = scoreSummary ?? "Official result"
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

        let headlineCopy = FieldHeadlineCopy10868(
            eyebrow: eventKind.thresholdEyebrow,
            title: title,
            graphicLabel: "\(eventKind.badgeTitle) threshold market",
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

        return ThresholdOrTotalCard(
            id: "special-prop-\(eventId)-\(marketId)",
            eventId: eventId,
            marketId: marketId,
            title: title,
            eventKind: eventKind,
            phase: phase,
            scoreSummary: scoreSummary,
            rows: rows,
            headlineInput: headlineInput
        )
    }

    private nonisolated static func buildHeadlineState(
        scoreSummary: String?,
        eventKind: EventKind,
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
                    caption: "In play · \(eventKind.badgeTitle)",
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
                caption: "Official result",
                detail: "Result not confirmed",
                spoken: "Official result",
                progress: nil
            )
        }
    }
}

// MARK: - SwiftUI Card View

struct EventAtlasSpecialEventCardView11666: View {
    let card: EventAtlasSpecialEventCards11666.Card

    var body: some View {
        switch card {
        case .eventOutlook(let outlookCard):
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
            .accessibilityIdentifier("eventAtlas.specialEvent.outlook.\(outlookCard.marketId)")

        case .thresholdOrTotal(let propCard):
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
                .accessibilityIdentifier("eventAtlas.specialEvent.prop.\(propCard.marketId)")
        }
    }
}
