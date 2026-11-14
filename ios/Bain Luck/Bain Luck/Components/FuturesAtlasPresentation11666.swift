import Foundation
import SwiftUI

/// #11666 (Item 17, Decide 91-C) — Native Title-Race / Futures Page Presentation (`F1`, `F2`, `F4`).
///
/// Implements the approved Title-Race / Futures Page header, market-shape-adaptive body, and
/// venue-free attribution (`docs/designs/futures-page-2026-11.md`) and carries the non-sport /
/// special-event futures categories (`horse_racing`, `olympics`, `poker`, `entertainment`,
/// `economics`, `weather`) behind `ReleaseSurfaces.isEventPageAtlasEnabled()`:
///
/// - **F1 (`HeaderModel` & `DetailsSheetModel`)**:
///   - Category + market-state eyebrow (`"Politics · Open"`, `"Politics · Settled"`, etc.).
///   - Selected / leading outcome headline:
///     - Open + fresh (`!isStale`): whole-number percentage (`#11990`), 24h movement badge, and
///       `"Opening chance N%"` (`#8313`).
///     - Open + stale (`> 30 min`) or missing quote: `"No recent probability"` (`Decide 10-C`), never
///       substituting an older quote as live.
///     - Settled (`market.status == "resolved"`): Decide `80-A` / `#698` / `#10955` verdict
///       (`"✓ Won"` / `"✗ Lost"` / `"Result not confirmed"`) with `"Opening chance N%"` context —
///       never printing a terminal `100%` or `0%` as a live chance.
///   - Scheduled resolution (`CalendarDeadline.format`) and recorded price timestamp
///     (`FuturesPriceAge.pricesAsOf`).
///   - `(i)` Market & Provenance Details native sheet (`FuturesAtlasDetailsSheetView11666`).
///
/// - **F2 (`MarketShape` & `BodyModel`)**:
///   1. `.twoWayDuel`: Two-sided comparison card (`outcomes.count == 2`, `mutuallyExclusive != false`)
///      with opening vs current/settled columns and a proportional two-sided bar.
///   2. `.mutuallyExclusiveField`: Top-3 named leaders (`outcomes.count > 2`, `mutuallyExclusive != false`)
///      with `"Showing top 3 of N"` (`#3721`), opening/movement context, and `"All outcomes · N"`
///      searchable full-field sheet.
///   3. `.participationField`: Independent qualification / participation field (`mutuallyExclusive == false`)
///      with explicit `"Independent chances · do not add to 100%"` badge, `"Showing top 6 of N"` (`#3721`),
///      unnormalized chances, Decide `80-A` settlement (`ungradeable_result` -> `"Result not confirmed"`,
///      never `"Lost"`), and searchable full-field sheet.
///   4. `.quantityLadder`: Unconnected threshold profile (`Above N` / `Over N` / `N+` rungs) ordered by
///      numeric threshold without normalization, monotonic repair, or invented actual values.
///   5. `.singleLegPredicate`: Single supplied outcome card (`outcomes.count == 1`), never inventing
///      a synthetic second leg.
///
/// - **Chart Agreement (`chartExpectation`)**:
///   - Mounts `EvolutionChartView` with a `VerifiedTitleChartExpectation` that follows the reader's
///     selected outcome (`header.selectedOutcomeId`) and withholds `heroProbability` (`nil`) when the
///     headline reads `"No recent probability"` (`Decide 10-C`).
///
/// - **F4 (`narrativeCopy` & `AttributionModel`)**:
///   - Venue-free narrative copy + attribution-only footer via `SourceLabels.attribution(for:)` and
///     `SourceLabels.sportsbookChips(for:)` — never venue price-comparison rows.
enum FuturesAtlasPresentation11666 {

    // MARK: - Market Shape (F2)

    enum MarketShape: String, Equatable {
        case twoWayDuel
        case mutuallyExclusiveField
        case participationField
        case quantityLadder
        case singleLegPredicate
    }

    // MARK: - Row & Header Display Values (170-A, 188 & Decide 80-A)

    enum RowDisplayValue: Equatable {
        case chance(
            percent: Int,
            formattedText: String,
            rawProbability: Double,
            moveText: String?,
            isUp: Bool?,
            asOfText: String? = nil
        )
        case noRecentProbability(lastRecordedText: String?)
        case won
        case lost
        case resultUnconfirmed(lastRecordedText: String?)

        var primaryLabel: String {
            switch self {
            case .chance(_, let formattedText, _, _, _, _):
                return formattedText
            case .noRecentProbability:
                return EventAtlasStates11666.noRecentPrice
            case .won:
                return EventAtlasStates11666.wonWithCheck
            case .lost:
                return EventAtlasStates11666.lostWithCross
            case .resultUnconfirmed:
                return EventAtlasStates11666.resultNotConfirmed
            }
        }

        var asOfText: String? {
            if case .chance(_, _, _, _, _, let asOf) = self {
                return asOf
            }
            return nil
        }

        var isWon: Bool {
            if case .won = self { return true }
            return false
        }
    }

    struct ContenderRow: Equatable, Identifiable {
        let id: Int
        let rank: Int
        let name: String
        let openingText: String?
        let displayValue: RowDisplayValue
        let thresholdValue: Double?
    }

    // MARK: - Header & Provenance Sheet Models (F1)

    struct HeaderModel: Equatable {
        let eyebrow: String
        let categoryName: String
        let stateLabel: String
        let isResolved: Bool
        let marketTitle: String
        let selectedOutcomeId: Int?
        let selectedOutcomeName: String?
        let primaryDisplay: RowDisplayValue
        let openingChanceText: String?
        let recordedAtText: String?
        let scheduledResolutionText: String?
        let sourcePill: String?
    }

    struct DetailsSheetModel: Equatable {
        let outcomeName: String
        let marketTitle: String
        let openingChanceValue: String
        let openingChanceNote: String
        let currentOrSettlementLabel: String
        let currentOrSettlementValue: String
        let currentOrSettlementNote: String
        let scheduledResolutionValue: String
        let scheduledResolutionNote: String
        let attributionSummary: String?
        let attributionChips: [String]
        let settlementRules: String
    }

    // MARK: - Body & Attribution Models (F2 & F4)

    struct BodyModel: Equatable {
        let shape: MarketShape
        let domainContext: String?
        let sectionTitle: String
        let sliceCaption: String?
        let subtitleBadge: String?
        let primaryRows: [ContenderRow]
        let allRows: [ContenderRow]
        let remainingCount: Int
    }

    struct AttributionModel: Equatable {
        let summary: String
        let chips: [String]
    }

    struct PagePresentation: Equatable {
        let header: HeaderModel
        let narrativeCopy: String?
        let body: BodyModel
        let detailsSheet: DetailsSheetModel
        let attribution: AttributionModel?
    }

    // MARK: - Public Builder

    /// Decision 170-A & Ruling 188: readings older than 30 minutes keep their number
    /// and display `"As of 1:29 PM"` (`"As of Nov 12, 4:52 PM"` across calendar days);
    /// there is no hard hiding limit for old priced numbers.
    nonisolated static let staleThresholdSeconds: TimeInterval = 30 * 60

    nonisolated static func outcomeObservationDate(_ outcome: FuturesOutcome) -> Date? {
        (outcome.observedAt ?? outcome.lastUpdated)?.asDate
    }

    nonisolated static func isOutcomeStale(_ outcome: FuturesOutcome, now: Date) -> Bool {
        guard let date = outcomeObservationDate(outcome) else {
            return false
        }
        return now.timeIntervalSince(date) > staleThresholdSeconds
    }

    nonisolated static func formatAsOf(
        _ date: Date,
        relativeTo now: Date,
        timeZone: TimeZone = .current
    ) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = timeZone
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = timeZone
        if calendar.isDate(date, inSameDayAs: now) {
            formatter.dateFormat = "h:mm a"
        } else if calendar.component(.year, from: date) == calendar.component(.year, from: now) {
            formatter.dateFormat = "MMM d, h:mm a"
        } else {
            formatter.dateFormat = "MMM d, yyyy, h:mm a"
        }
        return "As of \(formatter.string(from: date))"
    }

    nonisolated static func outcomeAsOfText(
        _ outcome: FuturesOutcome,
        now: Date,
        timeZone: TimeZone = .current
    ) -> String? {
        guard let date = outcomeObservationDate(outcome),
              now.timeIntervalSince(date) > staleThresholdSeconds else {
            return nil
        }
        return formatAsOf(date, relativeTo: now, timeZone: timeZone)
    }

    nonisolated static func build(
        market: FuturesMarketDetail,
        selectedOutcomeId: Int? = nil,
        now: Date = Date(),
        timeZone: TimeZone = .current
    ) -> PagePresentation {
        let shape = classifyShape(market: market)
        let percents = renderedPercentsById(for: market, shape: shape)
        let allRows = buildContenderRows(
            market: market,
            shape: shape,
            percents: percents,
            now: now,
            timeZone: timeZone
        )

        let selectedOutcome = resolveSelectedOutcome(
            market: market,
            selectedOutcomeId: selectedOutcomeId,
            allRows: allRows
        )
        let selectedRow = selectedOutcome.flatMap { outcome in
            allRows.first(where: { $0.id == outcome.id })
        } ?? allRows.first

        let header = buildHeader(
            market: market,
            selectedOutcome: selectedOutcome,
            selectedRow: selectedRow
        )
        let body = buildBody(market: market, shape: shape, allRows: allRows)
        let detailsSheet = buildDetailsSheet(
            market: market,
            selectedOutcome: selectedOutcome,
            selectedRow: selectedRow,
            header: header,
            now: now,
            timeZone: timeZone
        )
        let attribution = buildAttribution(market: market)
        let narrative = sanitizeNarrativeCopy(market.hookDescription)

        return PagePresentation(
            header: header,
            narrativeCopy: narrative,
            body: body,
            detailsSheet: detailsSheet,
            attribution: attribution
        )
    }

    // MARK: - Shape Classification (F2)

    nonisolated static func classifyShape(market: FuturesMarketDetail) -> MarketShape {
        let outcomes = market.outcomes
        if outcomes.count <= 1 {
            return .singleLegPredicate
        }
        if isQuantityLadder(outcomes: outcomes, marketName: market.name) {
            return .quantityLadder
        }
        if market.mutuallyExclusive == false {
            return .participationField
        }
        if outcomes.count == 2 {
            return .twoWayDuel
        }
        return .mutuallyExclusiveField
    }

    nonisolated static func isQuantityLadder(outcomes: [FuturesOutcome], marketName: String) -> Bool {
        guard outcomes.count >= 3 else { return false }
        let parsedCount = outcomes.filter { parseThresholdValue(from: $0.name) != nil }.count
        return Double(parsedCount) / Double(outcomes.count) >= 0.6
    }

    nonisolated static func parseThresholdValue(from outcomeName: String) -> Double? {
        let trimmed = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        let patterns = [
            #"(?i)^(?:above|over|under|below|at\s+least|more\s+than|fewer\s+than|less\s+than)\s+(-?\d+(?:\.\d+)?)\b"#,
            #"(?i)^(-?\d+(?:\.\d+)?)\+\s*(?:inches|inch|in\b|points|pts|wins|goals|runs|yards|%|degrees|°)"#,
        ]
        for pattern in patterns {
            guard let regex = try? NSRegularExpression(pattern: pattern) else { continue }
            let range = NSRange(trimmed.startIndex..<trimmed.endIndex, in: trimmed)
            if let match = regex.firstMatch(in: trimmed, range: range),
               match.numberOfRanges > 1,
               let numRange = Range(match.range(at: 1), in: trimmed),
               let value = Double(trimmed[numRange]) {
                return value
            }
        }
        return nil
    }

    // MARK: - Whole-Percent Decision (#11990, #11995, #8097)

    nonisolated static func renderedPercentsById(
        for market: FuturesMarketDetail,
        shape: MarketShape
    ) -> [Int: Int] {
        let outcomes = market.outcomes
        // Decision 6-A (#11995): never normalize independent sets, threshold ladders, or
        // unnormalized server pairs (such as 97% + 2% = 99% on #109085). Only apply
        // half-cent complement rounding when a 2-outcome mutually-exclusive pair sits
        // within 0.005 of 1.000 (e.g. 0.595 + 0.405 = 1.000 -> 60% / 40%, #8097).
        if shape == .twoWayDuel, outcomes.count == 2 {
            let ordered = outcomes.sorted { a, b in
                let lhs = a.probability ?? -1
                let rhs = b.probability ?? -1
                if lhs != rhs { return lhs > rhs }
                return a.id < b.id
            }
            if let p0 = ordered[0].probability, let p1 = ordered[1].probability,
               abs((p0 + p1) - 1.0) < 0.005 {
                let printed = renderedCardPercents([p0, p1])
                var result: [Int: Int] = [:]
                for (idx, outcome) in ordered.enumerated() {
                    if let pct = outcome.renderedPercent ?? printed[idx] {
                        result[outcome.id] = pct
                    }
                }
                return result
            }
        }

        var byId: [Int: Int] = [:]
        for outcome in outcomes {
            if let pct = outcome.renderedPercent ?? renderedPercent(outcome.probability) {
                byId[outcome.id] = pct
            }
        }
        return byId
    }

    // MARK: - Contender Rows Builder (Decide 10-C & Decide 80-A)

    nonisolated static func buildContenderRows(
        market: FuturesMarketDetail,
        shape: MarketShape,
        percents: [Int: Int],
        now: Date,
        timeZone: TimeZone = .current
    ) -> [ContenderRow] {
        let orderedOutcomes: [FuturesOutcome]
        switch shape {
        case .quantityLadder:
            orderedOutcomes = market.outcomes.enumerated().sorted { lhs, rhs in
                let lVal = parseThresholdValue(from: lhs.element.name)
                let rVal = parseThresholdValue(from: rhs.element.name)
                switch (lVal, rVal) {
                case let (l?, r?) where l != r:
                    return l < r
                case (.some, .none):
                    return true
                case (.none, .some):
                    return false
                default:
                    return lhs.offset < rhs.offset
                }
            }.map(\.element)
        case .singleLegPredicate:
            orderedOutcomes = market.outcomes
        case .twoWayDuel, .mutuallyExclusiveField, .participationField:
            orderedOutcomes = market.outcomes.sorted { a, b in
                let lhs = a.probability ?? -1
                let rhs = b.probability ?? -1
                if lhs != rhs { return lhs > rhs }
                let nameCmp = a.name.localizedCompare(b.name)
                if nameCmp != .orderedSame { return nameCmp == .orderedAscending }
                return a.id < b.id
            }
        }

        let isResolved = market.status == "resolved"

        return orderedOutcomes.enumerated().map { index, outcome in
            let openingText = FuturesReadableOpening8313.of(outcome).map { opening in
                "Opening chance \(formatWholePercent(opening * 100))%"
            }
            let threshold = parseThresholdValue(from: outcome.name)
            let displayValue = resolveRowDisplayValue(
                outcome: outcome,
                market: market,
                isResolved: isResolved,
                renderedPercent: percents[outcome.id],
                now: now,
                timeZone: timeZone
            )
            return ContenderRow(
                id: outcome.id,
                rank: index + 1,
                name: outcome.name,
                openingText: openingText,
                displayValue: displayValue,
                thresholdValue: threshold
            )
        }
    }

    nonisolated private static func resolveRowDisplayValue(
        outcome: FuturesOutcome,
        market: FuturesMarketDetail,
        isResolved: Bool,
        renderedPercent: Int?,
        now: Date,
        timeZone: TimeZone
    ) -> RowDisplayValue {
        let rowValue = FuturesDetailRowValue.of(
            outcome,
            marketStatus: market.status,
            marketSource: market.source
        )
        switch rowValue {
        case .verdict(.won):
            return .won
        case .verdict(.lost):
            return .lost
        case .resultUnknown(let lastRecorded):
            let lastText = lastRecorded.map { formatProbability($0, renderedPercent: renderedPercent) }
            return .resultUnconfirmed(lastRecordedText: lastText)
        case .price(let prob):
            if isResolved {
                let lastText = formatProbability(prob, renderedPercent: renderedPercent)
                return .resultUnconfirmed(lastRecordedText: lastText)
            }
            // Decision 170-A & Ruling 188 (#12633): an open outcome whose price was last
            // read more than 30 minutes ago keeps its number and shows `"As of 1:29 PM"`
            // (never `"checked"`, never `"stale"`, and never hidden by an age cutoff).
            let pct = renderedPercent ?? Int((prob * 1000 / 10).rounded())
            let formatted = "\(percentNumber(prob * 100, renderedPercent: renderedPercent))%"
            let moveText = outcome.probabilityChange24h.flatMap { futuresHeroMoveText($0) }
            let isUp = outcome.probabilityChange24h.map { $0 > 0 }
            let asOfText = outcomeAsOfText(outcome, now: now, timeZone: timeZone)
            return .chance(
                percent: pct,
                formattedText: formatted,
                rawProbability: prob,
                moveText: moveText,
                isUp: isUp,
                asOfText: asOfText
            )
        case .none:
            if isResolved {
                return .resultUnconfirmed(lastRecordedText: nil)
            }
            return .noRecentProbability(lastRecordedText: nil)
        }
    }

    // MARK: - Selected Outcome & Header Builder (F1)

    nonisolated private static func resolveSelectedOutcome(
        market: FuturesMarketDetail,
        selectedOutcomeId: Int?,
        allRows: [ContenderRow]
    ) -> FuturesOutcome? {
        if let selectedOutcomeId,
           let matched = market.outcomes.first(where: { $0.id == selectedOutcomeId }) {
            return matched
        }
        // For settled markets, prefer the authoritative winner if present.
        if market.status == "resolved",
           let winnerRow = allRows.first(where: { $0.displayValue.isWon }),
           let winner = market.outcomes.first(where: { $0.id == winnerRow.id }) {
            return winner
        }
        return futuresDetailHeroOutcome(market) ?? market.outcomes.first
    }

    nonisolated private static func buildHeader(
        market: FuturesMarketDetail,
        selectedOutcome: FuturesOutcome?,
        selectedRow: ContenderRow?
    ) -> HeaderModel {
        let rawCategory = market.llmSportCategory ?? market.category ?? market.sport ?? "Market"
        let categoryName = sportCategoryDisplayName(rawCategory)
        let isResolved = market.status == "resolved"
        let stateLabel = isResolved ? "Settled" : "Open"
        let eyebrow = "\(categoryName) · \(stateLabel)"

        let primaryDisplay = selectedRow?.displayValue ?? (
            isResolved ? .resultUnconfirmed(lastRecordedText: nil) : .noRecentProbability(lastRecordedText: nil)
        )
        let openingChanceText = selectedRow?.openingText

        // #12633 (170-A): the headline carries its own `"As of …"` tag when the selected
        // outcome is older than 30 minutes, rather than attributing `FuturesPriceAge.pricesAsOf`
        // (an unrelated sibling's oldest clock) or printing `"Settled <last_updated>"` in the footer.
        let recordedAtText: String? = nil

        let scheduledResolutionText: String? = CalendarDeadline.format(
            market.resolutionDate,
            style: .monthDayYear
        ).map { text in
            "Scheduled resolution \(text)"
        }

        let sourcePill = VerifiedTitlePresentation.heroSourcePill(market, hero: selectedOutcome)

        return HeaderModel(
            eyebrow: eyebrow,
            categoryName: categoryName,
            stateLabel: stateLabel,
            isResolved: isResolved,
            marketTitle: market.name,
            selectedOutcomeId: selectedOutcome?.id,
            selectedOutcomeName: selectedOutcome?.name,
            primaryDisplay: primaryDisplay,
            openingChanceText: openingChanceText,
            recordedAtText: recordedAtText,
            scheduledResolutionText: scheduledResolutionText,
            sourcePill: sourcePill
        )
    }

    // MARK: - Body Builder (F2 & 16d-3 Domain Framing)

    nonisolated static func domainContextLabel(for market: FuturesMarketDetail) -> String? {
        let rawCat = (market.llmSportCategory ?? market.category ?? market.sport ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
            .lowercased()
        let lowerTitle = market.name.lowercased()
        switch rawCat {
        case "horse_racing", "horseracing", "equestrian":
            return "Race Field"
        case "olympics", "winter_olympics", "summer_olympics":
            return "Medal & Podium Outlook"
        case "poker", "wsop":
            return "Bracelet & Table Field"
        case "entertainment", "awards", "oscars":
            return "Ceremony & Release Outlook"
        case "economics", "finance", "macro", "earnings":
            let isEarnings = lowerTitle.contains("earnings")
                || lowerTitle.contains("revenue")
                || lowerTitle.contains("eps")
                || lowerTitle.contains("guidance")
                || lowerTitle.contains("consensus")
            return isEarnings ? "Earnings & Release Outlook" : "Macro & Policy Outlook"
        case "weather", "climate":
            return "Forecast & Threshold Outlook"
        default:
            return nil
        }
    }

    nonisolated private static func buildBody(
        market: FuturesMarketDetail,
        shape: MarketShape,
        allRows: [ContenderRow]
    ) -> BodyModel {
        let domainContext = domainContextLabel(for: market)
        switch shape {
        case .twoWayDuel:
            return BodyModel(
                shape: .twoWayDuel,
                domainContext: domainContext,
                sectionTitle: "Side-by-side comparison",
                sliceCaption: nil,
                subtitleBadge: nil,
                primaryRows: Array(allRows.prefix(2)),
                allRows: allRows,
                remainingCount: 0
            )
        case .mutuallyExclusiveField:
            let primary = Array(allRows.prefix(3))
            let remaining = max(0, allRows.count - primary.count)
            // #3721: never present a slice as the whole field; name `Showing top K of N`.
            let sliceCaption = remaining > 0 ? "Showing top \(primary.count) of \(allRows.count)" : nil
            return BodyModel(
                shape: .mutuallyExclusiveField,
                domainContext: domainContext,
                sectionTitle: "Leading contenders",
                sliceCaption: sliceCaption,
                subtitleBadge: nil,
                primaryRows: primary,
                allRows: allRows,
                remainingCount: remaining
            )
        case .participationField:
            let primary = Array(allRows.prefix(6))
            let remaining = max(0, allRows.count - primary.count)
            let sliceCaption = remaining > 0 ? "Showing top \(primary.count) of \(allRows.count)" : nil
            return BodyModel(
                shape: .participationField,
                domainContext: domainContext,
                sectionTitle: "Qualification field",
                sliceCaption: sliceCaption,
                subtitleBadge: "Independent chances · do not add to 100%",
                primaryRows: primary,
                allRows: allRows,
                remainingCount: remaining
            )
        case .quantityLadder:
            return BodyModel(
                shape: .quantityLadder,
                domainContext: domainContext,
                sectionTitle: "Threshold profile",
                sliceCaption: nil,
                subtitleBadge: "Each threshold is priced on its own · do not add to 100%",
                primaryRows: allRows,
                allRows: allRows,
                remainingCount: 0
            )
        case .singleLegPredicate:
            return BodyModel(
                shape: .singleLegPredicate,
                domainContext: domainContext,
                sectionTitle: "Market outcome",
                sliceCaption: nil,
                subtitleBadge: nil,
                primaryRows: Array(allRows.prefix(1)),
                allRows: allRows,
                remainingCount: 0
            )
        }
    }

    // MARK: - Provenance & Details Sheet Builder (F1)

    nonisolated private static func buildDetailsSheet(
        market: FuturesMarketDetail,
        selectedOutcome: FuturesOutcome?,
        selectedRow: ContenderRow?,
        header: HeaderModel,
        now: Date,
        timeZone: TimeZone
    ) -> DetailsSheetModel {
        let outcomeName = selectedOutcome?.name ?? market.name
        let openingValue: String
        if let selectedOutcome, let opening = FuturesReadableOpening8313.of(selectedOutcome) {
            openingValue = "\(formatWholePercent(opening * 100))%"
        } else {
            openingValue = "Not supplied"
        }

        let currentLabel: String
        let currentValue: String
        let currentNote: String
        if header.isResolved {
            currentLabel = "Settlement"
            currentValue = header.primaryDisplay.primaryLabel
            currentNote = "Authoritative venue result. A result is not another historical probability."
        } else {
            currentLabel = "Current reading"
            currentValue = header.primaryDisplay.primaryLabel
            currentNote = selectedOutcome
                .flatMap(outcomeObservationDate)
                .map { formatAsOf($0, relativeTo: now, timeZone: timeZone) }
                ?? "Observation time not supplied."
        }

        let resolutionValue = CalendarDeadline.format(market.resolutionDate, style: .monthDayYear) ?? "Not supplied"
        let attributionSummary = SourceLabels.attribution(for: market.bookmakers ?? [])
            ?? header.sourcePill
        let attributionChips = SourceLabels.sportsbookChips(for: market.bookmakers ?? [])
        let rules: String
        if let desc = market.description?.trimmingCharacters(in: .whitespacesAndNewlines), !desc.isEmpty {
            rules = desc
        } else {
            rules = "Full venue rules are not supplied in this payload."
        }

        return DetailsSheetModel(
            outcomeName: outcomeName,
            marketTitle: market.name,
            openingChanceValue: openingValue,
            openingChanceNote: "Opening observation time not supplied. This is not a pre-event pin.",
            currentOrSettlementLabel: currentLabel,
            currentOrSettlementValue: currentValue,
            currentOrSettlementNote: currentNote,
            scheduledResolutionValue: resolutionValue,
            scheduledResolutionNote: "Schedule only; does not establish settlement.",
            attributionSummary: attributionSummary,
            attributionChips: attributionChips,
            settlementRules: rules
        )
    }

    // MARK: - Attribution & Narrative Sanitiser (F4)

    nonisolated private static func buildAttribution(market: FuturesMarketDetail) -> AttributionModel? {
        guard let summary = SourceLabels.attribution(for: market.bookmakers ?? []) else {
            return nil
        }
        let chips = SourceLabels.sportsbookChips(for: market.bookmakers ?? [])
        return AttributionModel(summary: summary, chips: chips)
    }

    nonisolated static func sanitizeNarrativeCopy(_ hook: String?) -> String? {
        guard let trimmed = hook?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }

    // MARK: - Chart Agreement Expectation (EvolutionChartView #9387 + Decide 10-C)

    /// Builds the `VerifiedTitleChartExpectation` handed to `EvolutionChartView` on the Atlas
    /// futures page:
    /// - Follows the currently selected or leading headline outcome (`presentation.header.selectedOutcomeId`).
    /// - Withholds `heroProbability` (`nil`) when the headline outcome is stale (`Decide 10-C`:
    ///   `.noRecentProbability`) so a verified-title chart does not claim agreement with a stale
    ///   current probability column.
    nonisolated static func chartExpectation(
        market: FuturesMarketDetail,
        presentation: PagePresentation,
        representation: FuturesRepresentation
    ) -> VerifiedTitleChartExpectation? {
        guard representation != .source else { return nil }
        let selectedOutcome = market.outcomes.first(where: { $0.id == presentation.header.selectedOutcomeId })
            ?? futuresDetailHeroOutcome(market)
        let effectiveProbability: Double?
        if case .noRecentProbability = presentation.header.primaryDisplay {
            effectiveProbability = nil
        } else {
            effectiveProbability = selectedOutcome?.probability
        }
        return VerifiedTitleChartExpectation(
            representation: market.effectiveRepresentation,
            heroOutcomeId: selectedOutcome?.id,
            heroProbability: effectiveProbability,
            heroContributors: selectedOutcome?.contributingSources ?? []
        )
    }

    /// Outcome IDs whose current probability is withheld in the Atlas header/body (`Decide 10-C`
    /// `.noRecentProbability` after 30 minutes, or `Decide 80-A` settled states `.won`, `.lost`,
    /// `.resultUnconfirmed`). Handed to `EvolutionChartView` so its `Prob` leaderboard column
    /// withholds the current probability (`"—"`) for the exact same outcomes across both `.source`
    /// (`108629`) and `.verifiedTitle` markets.
    nonisolated static func withheldCurrentOutcomeIds(
        presentation: PagePresentation
    ) -> Set<Int> {
        var ids = Set<Int>()
        for row in presentation.body.allRows {
            if case .chance = row.displayValue {
                continue
            }
            ids.insert(row.id)
        }
        if let selectedId = presentation.header.selectedOutcomeId {
            if case .chance = presentation.header.primaryDisplay {
                // Fresh open probability
            } else {
                ids.insert(selectedId)
            }
        }
        return ids
    }

    // MARK: - Ruling 192-A First-Screen Headline & Field Link Helpers

    nonisolated static let firstScreenHeadlineLimit192A = 4

    nonisolated static func isPropMarket192A(_ market: FuturesMarketDetail) -> Bool {
        let hay = "\(market.name) \(market.category ?? "") \(market.llmSportCategory ?? "") \(market.externalId ?? "")".lowercased()
        let propWords = [
            "prop", "touchdown", "scorer", "1+ td", "anytime td", "specials",
            "passing yards", "rushing yards", "receiving yards", "rebounds",
            "assists", "strikeouts", "home run", "shots on goal",
        ]
        return propWords.contains { hay.contains($0) }
    }

    nonisolated static func firstScreenHeadlineRows192A(for body: BodyModel) -> [ContenderRow] {
        switch body.shape {
        case .twoWayDuel:
            return Array(body.allRows.prefix(2))
        case .singleLegPredicate:
            return Array(body.allRows.prefix(1))
        case .mutuallyExclusiveField, .participationField, .quantityLadder:
            return Array(body.allRows.prefix(firstScreenHeadlineLimit192A))
        }
    }

    nonisolated static func allFieldLinkLabel192A(
        market: FuturesMarketDetail,
        body: BodyModel
    ) -> String? {
        let headlineRows = firstScreenHeadlineRows192A(for: body)
        guard body.allRows.count > headlineRows.count else { return nil }
        let noun: String
        if isPropMarket192A(market) {
            noun = "props"
        } else if body.shape == .quantityLadder {
            noun = "thresholds"
        } else {
            let cat = (market.llmSportCategory ?? market.category ?? market.sport ?? "").lowercased()
            let title = market.name.lowercased()
            let teamSports: Set<String> = ["football", "basketball", "baseball", "hockey", "soccer"]
            let playerAwardWords = ["mvp", "heisman", "rookie", "coach", "cy young", "hart", "vezina", "ballon", "player"]
            if teamSports.contains(cat) && !playerAwardWords.contains(where: { title.contains($0) }) {
                noun = "teams"
            } else {
                noun = "outcomes"
            }
        }
        return "All \(body.allRows.count) \(noun) ›"
    }

    nonisolated static func chartCardTitle192A(
        market: FuturesMarketDetail,
        shape: MarketShape
    ) -> String {
        let lower = market.name.lowercased()
        if isPropMarket192A(market) {
            if lower.contains("touchdown") { return "Touchdown Chance" }
            return "Prop History"
        }
        if shape == .mutuallyExclusiveField
            && (lower.contains("champion") || lower.contains("winner") || lower.contains("title")) {
            return "Title Odds History"
        }
        return "Odds History"
    }

    nonisolated static func chartFooterCaption192A(
        market: FuturesMarketDetail,
        shape: MarketShape
    ) -> String {
        if isPropMarket192A(market) && shape == .participationField {
            return "Each player graded independently"
        }
        switch shape {
        case .participationField:
            return "Independent chances · time range in full chart"
        case .quantityLadder:
            return "Each threshold priced on its own"
        case .twoWayDuel, .mutuallyExclusiveField, .singleLegPredicate:
            return "Past 7 days · time range in full chart"
        }
    }

    // MARK: - Formatting Helpers

    nonisolated private static func formatWholePercent(_ pct: Double) -> Int {
        Int(pct.rounded())
    }

    nonisolated private static let timestampFormatter: DateFormatter = {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "America/Los_Angeles") ?? .current
        formatter.dateFormat = "MMM d, h:mm a 'PT'"
        return formatter
    }()
}

// MARK: - SwiftUI Views (F1, F2, F4 + Ruling 192-A First Screen)

struct FuturesAtlasPageView11666: View {
    let market: FuturesMarketDetail
    let marketId: Int
    let shareMessage: String
    let onShare: () -> Void
    let golfTournamentStart: String?
    let golfTournamentEnd: String?
    let chartRefreshToken: Int
    let representation: FuturesRepresentation
    var preloadedTimeline: ProbabilityTimelineResponse? = nil
    var referenceNow: Date? = nil

    @State private var selectedOutcomeId: Int? = nil
    @State private var showDetailsSheet = false
    @State private var showFullFieldSheet = false

    var body: some View {
        let presentation = FuturesAtlasPresentation11666.build(
            market: market,
            selectedOutcomeId: selectedOutcomeId,
            now: referenceNow ?? Date()
        )
        let headlineRows = FuturesAtlasPresentation11666.firstScreenHeadlineRows192A(for: presentation.body)
        let allFieldLabel = FuturesAtlasPresentation11666.allFieldLinkLabel192A(
            market: market,
            body: presentation.body
        )

        VStack(alignment: .leading, spacing: 12) {
            FuturesAtlasHeadlineCard192A(
                market: market,
                header: presentation.header,
                headlineRows: headlineRows,
                allFieldLabel: allFieldLabel,
                timelineOutcomes: preloadedTimeline?.outcomes,
                onOpenDetails: { showDetailsSheet = true },
                onOpenFullField: { showFullFieldSheet = true }
            )
            .contextualTipHero10876(type: "future", id: marketId, scrollSpace: FuturesDetailView.scrollSpace)

            if !market.outcomes.isEmpty {
                EvolutionChartView(
                    marketId: marketId,
                    hours: 168,
                    height: EvolutionChartView.defaultFirstScreenHeight192A,
                    tournamentStart: golfTournamentStart,
                    tournamentEnd: golfTournamentEnd,
                    refreshToken: chartRefreshToken,
                    representation: representation,
                    expectation: FuturesAtlasPresentation11666.chartExpectation(
                        market: market,
                        presentation: presentation,
                        representation: representation
                    ),
                    withheldCurrentOutcomeIds: FuturesAtlasPresentation11666.withheldCurrentOutcomeIds(
                        presentation: presentation
                    ),
                    firstScreenCompact192A: true,
                    chartTitle192A: FuturesAtlasPresentation11666.chartCardTitle192A(
                        market: market,
                        shape: presentation.body.shape
                    ),
                    headlineContenderNames: headlineRows.map(\.name),
                    footerCaption192A: FuturesAtlasPresentation11666.chartFooterCaption192A(
                        market: market,
                        shape: presentation.body.shape
                    ),
                    allFieldButtonLabel: allFieldLabel,
                    onOpenAllField: allFieldLabel != nil ? { showFullFieldSheet = true } : nil,
                    preloadedTimeline: preloadedTimeline,
                    referenceNow: referenceNow
                )
            }

            if let narrative = presentation.narrativeCopy {
                Text(narrative)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .lineSpacing(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(14)
                    .background(DS.cardBg)
                    .clipShape(RoundedRectangle(cornerRadius: 12))
                    .overlay(
                        RoundedRectangle(cornerRadius: 12)
                            .stroke(DS.border, lineWidth: 0.5)
                    )
            }

            if EventAtlasRacingCards11666.applies(market: market) {
                EventAtlasRacingSectionView11666(market: market)
            }
        }
        .padding(.horizontal, 16)
        .padding(.top, 10)
        .sheet(isPresented: $showDetailsSheet) {
            FuturesAtlasDetailsSheetView11666(details: presentation.detailsSheet)
        }
        .sheet(isPresented: $showFullFieldSheet) {
            FuturesAtlasFullFieldSheetView11666(
                marketTitle: market.name,
                subtitleBadge: presentation.body.subtitleBadge,
                rows: presentation.body.allRows,
                selectedOutcomeId: presentation.header.selectedOutcomeId,
                onSelectOutcome: { id in
                    selectedOutcomeId = id
                    showFullFieldSheet = false
                }
            )
        }
    }
}

struct FuturesAtlasHeadlineCard192A: View {
    let market: FuturesMarketDetail
    let header: FuturesAtlasPresentation11666.HeaderModel
    let headlineRows: [FuturesAtlasPresentation11666.ContenderRow]
    let allFieldLabel: String?
    var timelineOutcomes: [TimelineOutcomeMeta]? = nil
    let onOpenDetails: () -> Void
    let onOpenFullField: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var cleanEyebrow: String {
        if header.isResolved {
            return "\(header.categoryName) · Final"
        }
        if FuturesAtlasPresentation11666.isPropMarket192A(market) {
            return "\(header.categoryName) Props"
        }
        if let domain = FuturesAtlasPresentation11666.domainContextLabel(for: market) {
            return "\(header.categoryName) · \(domain)"
        }
        return header.categoryName
    }

    private func contenderColor(for row: FuturesAtlasPresentation11666.ContenderRow, index: Int) -> Color {
        Color(
            hex: EvolutionOutcomeColour.markHex(
                name: row.name,
                outcomes: timelineOutcomes,
                index: index
            )
        )
    }

    private func badgeInitials(for name: String) -> String {
        let core = name
            .components(separatedBy: " · ").first?
            .components(separatedBy: " — ").first?
            .trimmingCharacters(in: .whitespacesAndNewlines) ?? name
        let words = core.split(whereSeparator: \.isWhitespace).map(String.init)
        if words.count >= 2 {
            let a = words[0].prefix(1)
            let b = words[1].prefix(1)
            return "\(a)\(b)".uppercased()
        }
        return String(core.prefix(3)).uppercased()
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .center, spacing: 8) {
                Text(cleanEyebrow)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
                    .lineLimit(1)

                Spacer(minLength: 4)

                if !header.isResolved {
                    EkgTraceShape(beating: header.primaryDisplay.asOfText == nil)
                        .stroke(style: StrokeStyle(lineWidth: 1.5, lineCap: .round, lineJoin: .round))
                        .foregroundStyle(header.primaryDisplay.asOfText == nil ? Color.green : Color.secondary)
                        .frame(width: 26, height: 9)
                        .accessibilityHidden(true)
                }

                Button(action: onOpenDetails) {
                    Image(systemName: "info.circle")
                        .font(.subheadline)
                        .foregroundStyle(DS.textSecondary)
                        .frame(width: 28, height: 28)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Market and provenance details")
            }

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    Text(header.marketTitle)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let allFieldLabel {
                        Button(action: onOpenFullField) {
                            Text(allFieldLabel)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.blue)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("futures-all-field-header-button-192a")
                    }
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    Text(header.marketTitle)
                        .font(.headline.weight(.bold))
                        .foregroundStyle(DS.textPrimary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 6)
                    if let allFieldLabel {
                        Button(action: onOpenFullField) {
                            Text(allFieldLabel)
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(Color.blue)
                                .fixedSize(horizontal: true, vertical: false)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("futures-all-field-header-button-192a")
                    }
                }
            }

            VStack(spacing: 6) {
                ForEach(Array(headlineRows.enumerated()), id: \.element.id) { idx, row in
                    contenderHeadlineRow(row, index: idx)
                    if idx < headlineRows.count - 1 {
                        Divider()
                            .overlay(DS.border.opacity(0.6))
                    }
                }
            }
            .padding(.top, 2)
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 12)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .stroke(DS.border, lineWidth: 0.75)
        )
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("futures-headline-card-192a")
    }

    @ViewBuilder
    private func contenderHeadlineRow(
        _ row: FuturesAtlasPresentation11666.ContenderRow,
        index: Int
    ) -> some View {
        let color = contenderColor(for: row, index: index)
        let logoURL = timelineOutcomes?.first(where: { $0.name == row.name })?.logoSmall

        if dynamicTypeSize.isAccessibilitySize {
            VStack(alignment: .leading, spacing: 4) {
                HStack(spacing: 8) {
                    contenderMark(name: row.name, logoURL: logoURL, color: color)
                    Text(row.name)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                HStack(spacing: 8) {
                    rowSecondaryContext(row)
                    Spacer()
                    rowPrimaryValue(row, color: color)
                }
            }
            .padding(.vertical, 2)
        } else {
            HStack(spacing: 8) {
                contenderMark(name: row.name, logoURL: logoURL, color: color)
                Text(row.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .lineLimit(1)
                Spacer(minLength: 6)
                rowSecondaryContext(row)
                rowPrimaryValue(row, color: color)
                    .frame(minWidth: 46, alignment: .trailing)
            }
            .padding(.vertical, 2)
        }
    }

    @ViewBuilder
    private func contenderMark(name: String, logoURL: String?, color: Color) -> some View {
        if let logoURL, !logoURL.isEmpty {
            TeamLogoView(
                url: logoURL,
                teamName: name,
                color: color,
                size: 22
            )
        } else {
            Text(badgeInitials(for: name))
                .font(.system(size: 8.5, weight: .bold))
                .foregroundStyle(Color.white)
                .frame(width: 22, height: 22)
                .background(Circle().fill(color))
        }
    }

    @ViewBuilder
    private func rowSecondaryContext(_ row: FuturesAtlasPresentation11666.ContenderRow) -> some View {
        if let asOfText = row.displayValue.asOfText {
            Text(asOfText)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(DS.textMuted)
        } else if case .chance(_, _, _, let moveText?, let isUp?, _) = row.displayValue {
            Text("\(isUp ? "↑" : "↓")\(moveText)")
                .font(.caption2.weight(.medium).monospacedDigit())
                .foregroundStyle(DS.textMuted)
        }
    }

    @ViewBuilder
    private func rowPrimaryValue(
        _ row: FuturesAtlasPresentation11666.ContenderRow,
        color: Color
    ) -> some View {
        switch row.displayValue {
        case .chance:
            Text(row.displayValue.primaryLabel)
                .font(.callout.weight(.bold).monospacedDigit())
                .foregroundStyle(color)
        case .won:
            Text(row.displayValue.primaryLabel)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(DS.emerald)
        case .lost, .noRecentProbability, .resultUnconfirmed:
            Text(row.displayValue.primaryLabel)
                .font(.caption.weight(.medium))
                .foregroundStyle(DS.textSecondary)
        }
    }
}

struct FuturesAtlasHeaderCardView11666: View {
    let header: FuturesAtlasPresentation11666.HeaderModel
    let marketId: Int
    let marketName: String
    let shareMessage: String
    let onShare: () -> Void
    let onOpenDetails: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    Text(header.eyebrow.uppercased())
                        .font(.caption2.weight(.semibold))
                        .tracking(0.6)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    HStack(spacing: 8) {
                        if let pill = header.sourcePill {
                            Text(pill)
                                .font(.caption2.weight(.semibold))
                                .foregroundStyle(DS.textSecondary)
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(DS.trackBg, in: Capsule())
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Button(action: onOpenDetails) {
                            HStack(spacing: 4) {
                                Image(systemName: "info.circle")
                                    .font(.caption.weight(.semibold))
                                Text("Details")
                                    .font(.caption.weight(.semibold))
                            }
                            .foregroundStyle(DS.textSecondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 4)
                            .background(DS.trackBg, in: Capsule())
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Market and provenance details")
                    }
                }
            } else {
                HStack(alignment: .center, spacing: 8) {
                    Text(header.eyebrow.uppercased())
                        .font(.caption2.weight(.semibold))
                        .tracking(0.6)
                        .foregroundStyle(DS.textSecondary)
                        .fixedSize(horizontal: false, vertical: true)

                    Spacer(minLength: 4)

                    if let pill = header.sourcePill {
                        Text(pill)
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .padding(.horizontal, 8)
                            .padding(.vertical, 3)
                            .background(DS.trackBg, in: Capsule())
                    }

                    Button(action: onOpenDetails) {
                        HStack(spacing: 4) {
                            Image(systemName: "info.circle")
                                .font(.caption.weight(.semibold))
                            Text("Details")
                                .font(.caption.weight(.semibold))
                        }
                        .foregroundStyle(DS.textSecondary)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(DS.trackBg, in: Capsule())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Market and provenance details")
                }
            }

            Text(header.marketTitle)
                .font(.title3.weight(.bold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)

            VStack(alignment: .leading, spacing: 4) {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(header.primaryDisplay.primaryLabel)
                                .font(primaryValueFont)
                                .foregroundStyle(primaryValueColor)
                                .monospacedDigit()
                                .fixedSize(horizontal: false, vertical: true)

                            if case .chance(_, _, _, let moveText?, let isUp?, _) = header.primaryDisplay {
                                HStack(spacing: 2) {
                                    Image(systemName: isUp ? "arrow.up" : "arrow.down")
                                        .font(.caption2.weight(.bold))
                                    Text(moveText)
                                        .font(.caption.weight(.semibold))
                                        .monospacedDigit()
                                }
                                .foregroundStyle(isUp ? DS.emerald : DS.danger)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background((isUp ? DS.emerald : DS.danger).opacity(0.12), in: Capsule())
                            }
                        }

                        if let asOfText = header.primaryDisplay.asOfText {
                            Text(asOfText)
                                .font(.caption.monospacedDigit())
                                .foregroundStyle(DS.textMuted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                } else {
                    ViewThatFits(in: .horizontal) {
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Text(header.primaryDisplay.primaryLabel)
                                .font(primaryValueFont)
                                .foregroundStyle(primaryValueColor)
                                .monospacedDigit()
                                .fixedSize(horizontal: true, vertical: true)

                            if case .chance(_, _, _, let moveText?, let isUp?, _) = header.primaryDisplay {
                                HStack(spacing: 2) {
                                    Image(systemName: isUp ? "arrow.up" : "arrow.down")
                                        .font(.caption2.weight(.bold))
                                    Text(moveText)
                                        .font(.caption.weight(.semibold))
                                        .monospacedDigit()
                                }
                                .foregroundStyle(isUp ? DS.emerald : DS.danger)
                                .padding(.horizontal, 6)
                                .padding(.vertical, 2)
                                .background((isUp ? DS.emerald : DS.danger).opacity(0.12), in: Capsule())
                                .fixedSize(horizontal: true, vertical: true)
                            }

                            if let asOfText = header.primaryDisplay.asOfText {
                                Text(asOfText)
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(DS.textMuted)
                                    .fixedSize(horizontal: true, vertical: true)
                            }
                        }

                        VStack(alignment: .leading, spacing: 4) {
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Text(header.primaryDisplay.primaryLabel)
                                    .font(primaryValueFont)
                                    .foregroundStyle(primaryValueColor)
                                    .monospacedDigit()
                                    .fixedSize(horizontal: false, vertical: true)

                                if case .chance(_, _, _, let moveText?, let isUp?, _) = header.primaryDisplay {
                                    HStack(spacing: 2) {
                                        Image(systemName: isUp ? "arrow.up" : "arrow.down")
                                            .font(.caption2.weight(.bold))
                                        Text(moveText)
                                            .font(.caption.weight(.semibold))
                                            .monospacedDigit()
                                    }
                                    .foregroundStyle(isUp ? DS.emerald : DS.danger)
                                    .padding(.horizontal, 6)
                                    .padding(.vertical, 2)
                                    .background((isUp ? DS.emerald : DS.danger).opacity(0.12), in: Capsule())
                                }
                            }

                            if let asOfText = header.primaryDisplay.asOfText {
                                Text(asOfText)
                                    .font(.caption.monospacedDigit())
                                    .foregroundStyle(DS.textMuted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                    }
                }

                if let outcomeName = header.selectedOutcomeName {
                    Text(outcomeName)
                        .font(.headline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let openingText = header.openingChanceText {
                    Text(openingText)
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textMuted)
                }
            }

            Divider()
                .overlay(DS.border)

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    if let recorded = header.recordedAtText {
                        Text(recorded)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(DS.textMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let resolution = header.scheduledResolutionText {
                        Text(resolution)
                            .font(.caption2.monospacedDigit())
                            .foregroundStyle(DS.textSecondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    ShareLink(
                        item: URL(string: futuresShareURL(marketId, style: .nativeCard)) ?? bainLuckFallbackURL,
                        subject: Text(marketName),
                        message: Text(shareMessage)
                    ) {
                        Label("Share", systemImage: "square.and.arrow.up")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(DS.trackBg, in: Capsule())
                    }
                    .recordsShareOpened { onShare() }
                }
            } else {
                HStack(alignment: .center, spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        if let recorded = header.recordedAtText {
                            Text(recorded)
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(DS.textMuted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let resolution = header.scheduledResolutionText {
                            Text(resolution)
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }

                    Spacer(minLength: 4)

                    ShareLink(
                        item: URL(string: futuresShareURL(marketId, style: .nativeCard)) ?? bainLuckFallbackURL,
                        subject: Text(marketName),
                        message: Text(shareMessage)
                    ) {
                        Label("Share", systemImage: "square.and.arrow.up")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                            .padding(.horizontal, 10)
                            .padding(.vertical, 5)
                            .background(DS.trackBg, in: Capsule())
                    }
                    .recordsShareOpened { onShare() }
                }
            }
        }
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(DS.border, lineWidth: 0.75)
        )
    }

    private var primaryValueFont: Font {
        switch header.primaryDisplay {
        case .chance:
            return .system(size: 38, weight: .black, design: .rounded)
        case .won, .lost:
            return .title.weight(.bold)
        case .noRecentProbability, .resultUnconfirmed:
            return .headline.weight(.semibold)
        }
    }

    private var primaryValueColor: Color {
        switch header.primaryDisplay {
        case .chance:
            return DS.textPrimary
        case .won:
            return DS.emerald
        case .lost, .noRecentProbability, .resultUnconfirmed:
            return DS.textSecondary
        }
    }
}

struct FuturesAtlasBodyCardView11666: View {
    let bodyModel: FuturesAtlasPresentation11666.BodyModel
    let selectedOutcomeId: Int?
    let onSelectOutcome: (Int) -> Void
    let onOpenFullField: () -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if let domainContext = bodyModel.domainContext {
                Text(domainContext.uppercased())
                    .font(.caption2.weight(.semibold))
                    .tracking(0.5)
                    .foregroundStyle(DS.textMuted)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) {
                    Text(bodyModel.sectionTitle)
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.textPrimary)
                        .fixedSize(horizontal: false, vertical: true)
                    if let sliceCaption = bodyModel.sliceCaption {
                        Text(sliceCaption)
                            .font(.caption2)
                            .foregroundStyle(DS.textMuted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if bodyModel.allRows.count > bodyModel.primaryRows.count {
                        Button(action: onOpenFullField) {
                            Text("All outcomes · \(bodyModel.allRows.count)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DS.emerald)
                        }
                        .buttonStyle(.plain)
                    }
                }
            } else {
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(bodyModel.sectionTitle)
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.textPrimary)
                        if let sliceCaption = bodyModel.sliceCaption {
                            Text(sliceCaption)
                                .font(.caption2)
                                .foregroundStyle(DS.textMuted)
                        }
                    }
                    Spacer()
                    if bodyModel.allRows.count > bodyModel.primaryRows.count {
                        Button(action: onOpenFullField) {
                            Text("All outcomes · \(bodyModel.allRows.count)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DS.emerald)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            if let badge = bodyModel.subtitleBadge {
                Text(badge)
                    .font(.caption2.weight(.medium))
                    .foregroundStyle(DS.textSecondary)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 4)
                    .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 6))
                    .fixedSize(horizontal: false, vertical: true)
            }

            switch bodyModel.shape {
            case .twoWayDuel:
                duelView
            case .mutuallyExclusiveField, .participationField:
                contenderListView(showRank: true)
            case .quantityLadder:
                contenderListView(showRank: false)
            case .singleLegPredicate:
                contenderListView(showRank: false)
            }

            if bodyModel.remainingCount > 0 {
                Button(action: onOpenFullField) {
                    HStack {
                        Text("\(bodyModel.remainingCount) more outcomes")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.textSecondary)
                        Spacer()
                        Text("Search all \(bodyModel.allRows.count) →")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(DS.emerald)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .background(DS.trackBg, in: RoundedRectangle(cornerRadius: 8))
                }
                .buttonStyle(.plain)
            }
        }
        .padding(16)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 14))
        .overlay(
            RoundedRectangle(cornerRadius: 14)
                .stroke(DS.border, lineWidth: 0.75)
        )
    }

    @ViewBuilder
    private var duelView: some View {
        let rows = bodyModel.primaryRows
        if rows.count == 2 {
            let left = rows[0]
            let right = rows[1]

            VStack(alignment: .leading, spacing: 10) {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 10) {
                        duelSideCard(left, isLeading: true)
                        duelSideCard(right, isLeading: false)
                    }
                } else {
                    HStack(alignment: .top, spacing: 10) {
                        duelSideCard(left, isLeading: true)
                        duelSideCard(right, isLeading: false)
                    }
                }

                if case .chance(_, _, let lProb, _, _, _) = left.displayValue,
                   case .chance(_, _, let rProb, _, _, _) = right.displayValue,
                   (lProb + rProb) > 0 {
                    let total = max(lProb + rProb, 0.0001)
                    GeometryReader { geo in
                        let leftWidth = max(4, geo.size.width * CGFloat(lProb / total))
                        HStack(spacing: 2) {
                            RoundedRectangle(cornerRadius: 3)
                                .fill(DS.emerald)
                                .frame(width: min(leftWidth, geo.size.width))
                            RoundedRectangle(cornerRadius: 3)
                                .fill(DS.blue.opacity(0.65))
                                .frame(maxWidth: .infinity)
                        }
                    }
                    .frame(height: 6)
                }
            }
        } else {
            contenderListView(showRank: false)
        }
    }

    private func duelSideCard(
        _ row: FuturesAtlasPresentation11666.ContenderRow,
        isLeading: Bool
    ) -> some View {
        let isSelected = row.id == selectedOutcomeId
        return Button {
            onSelectOutcome(row.id)
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                Text(row.name)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)

                Text(row.displayValue.primaryLabel)
                    .font(.title3.weight(.bold).monospacedDigit())
                    .foregroundStyle(rowColor(row.displayValue, isLeading: isLeading))
                    .fixedSize(horizontal: false, vertical: true)

                if let asOfText = row.displayValue.asOfText {
                    Text(asOfText)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(DS.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }

                if let opening = row.openingText {
                    Text(opening)
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(DS.textMuted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .background(DS.trackBg)
            .clipShape(RoundedRectangle(cornerRadius: 10))
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .stroke(isSelected ? DS.emerald : DS.border, lineWidth: isSelected ? 1.2 : 0.5)
            )
        }
        .buttonStyle(.plain)
    }

    private func contenderListView(showRank: Bool) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            ForEach(Array(bodyModel.primaryRows.enumerated()), id: \.element.id) { index, row in
                contenderRowView(row, showRank: showRank, isFirst: index == 0)
                if index < bodyModel.primaryRows.count - 1 {
                    Divider()
                        .overlay(DS.border)
                }
            }
        }
    }

    private func contenderRowView(
        _ row: FuturesAtlasPresentation11666.ContenderRow,
        showRank: Bool,
        isFirst: Bool
    ) -> some View {
        let isSelected = row.id == selectedOutcomeId
        return Button {
            onSelectOutcome(row.id)
        } label: {
            VStack(alignment: .leading, spacing: 6) {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 6) {
                            if showRank {
                                Text("#\(row.rank)")
                                    .font(.caption.weight(.semibold).monospacedDigit())
                                    .foregroundStyle(isFirst ? DS.emerald : DS.textMuted)
                            }
                            Text(row.name)
                                .font(.subheadline.weight(isFirst ? .semibold : .medium))
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        Text(row.displayValue.primaryLabel)
                            .font(.subheadline.weight(.bold).monospacedDigit())
                            .foregroundStyle(rowColor(row.displayValue, isLeading: isFirst))
                            .fixedSize(horizontal: false, vertical: true)
                        if let asOfText = row.displayValue.asOfText {
                            Text(asOfText)
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(DS.textMuted)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        if let opening = row.openingText {
                            Text(opening)
                                .font(.caption2.monospacedDigit())
                                .foregroundStyle(DS.textMuted)
                        }
                    }
                } else {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        if showRank {
                            Text("#\(row.rank)")
                                .font(.caption.weight(.semibold).monospacedDigit())
                                .foregroundStyle(isFirst ? DS.emerald : DS.textMuted)
                                .frame(width: 26, alignment: .leading)
                        }
                        VStack(alignment: .leading, spacing: 2) {
                            Text(row.name)
                                .font(.subheadline.weight(isFirst ? .semibold : .medium))
                                .foregroundStyle(DS.textPrimary)
                                .fixedSize(horizontal: false, vertical: true)
                            if let opening = row.openingText {
                                Text(opening)
                                    .font(.caption2.monospacedDigit())
                                    .foregroundStyle(DS.textMuted)
                            }
                        }
                        Spacer(minLength: 6)
                        VStack(alignment: .trailing, spacing: 2) {
                            HStack(alignment: .firstTextBaseline, spacing: 6) {
                                if case .chance(_, _, _, let moveText?, let isUp?, _) = row.displayValue {
                                    Text("\(isUp ? "↑" : "↓")\(moveText)")
                                        .font(.caption2.weight(.semibold).monospacedDigit())
                                        .foregroundStyle(isUp ? DS.emerald : DS.danger)
                                }
                                Text(row.displayValue.primaryLabel)
                                    .font(.subheadline.weight(.bold).monospacedDigit())
                                    .foregroundStyle(rowColor(row.displayValue, isLeading: isFirst))
                            }
                            if let asOfText = row.displayValue.asOfText {
                                Text(asOfText)
                                    .font(.caption2.monospacedDigit())
                                    .foregroundStyle(DS.textMuted)
                                    .fixedSize(horizontal: true, vertical: false)
                            }
                        }
                    }
                }

                if case .chance(_, _, let rawProb, _, _, _) = row.displayValue {
                    DSProbabilityBar(
                        value: rawProb * 100,
                        maxValue: 100,
                        height: 4,
                        color: isSelected || isFirst ? DS.emerald : DS.blue.opacity(0.65)
                    )
                }
            }
            .padding(.vertical, 4)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }

    private func rowColor(
        _ value: FuturesAtlasPresentation11666.RowDisplayValue,
        isLeading: Bool
    ) -> Color {
        switch value {
        case .won:
            return DS.emerald
        case .lost, .noRecentProbability, .resultUnconfirmed:
            return DS.textSecondary
        case .chance:
            return isLeading ? DS.emerald : DS.textPrimary
        }
    }
}

struct FuturesAtlasAttributionFooterView11666: View {
    let attribution: FuturesAtlasPresentation11666.AttributionModel

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(attribution.summary)
                .font(.caption.weight(.medium))
                .foregroundStyle(DS.textMuted)
                .fixedSize(horizontal: false, vertical: true)

            if !attribution.chips.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 6) {
                        ForEach(Array(attribution.chips.enumerated()), id: \.offset) { _, name in
                            Text(name)
                                .font(.caption2.weight(.medium))
                                .padding(.horizontal, 8)
                                .padding(.vertical, 3)
                                .background(DS.trackBg, in: Capsule())
                                .foregroundStyle(DS.textSecondary)
                        }
                    }
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(14)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(DS.border, lineWidth: 0.5)
        )
    }
}

struct FuturesAtlasDetailsSheetView11666: View {
    let details: FuturesAtlasPresentation11666.DetailsSheetModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 16) {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(details.outcomeName)
                            .font(.headline.weight(.bold))
                            .foregroundStyle(DS.textPrimary)
                        Text(details.marketTitle)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                    }

                    detailRow(
                        title: "Opening chance",
                        value: details.openingChanceValue,
                        note: details.openingChanceNote
                    )
                    detailRow(
                        title: details.currentOrSettlementLabel,
                        value: details.currentOrSettlementValue,
                        note: details.currentOrSettlementNote
                    )
                    detailRow(
                        title: "Scheduled resolution",
                        value: details.scheduledResolutionValue,
                        note: details.scheduledResolutionNote
                    )

                    if let attribution = details.attributionSummary {
                        detailRow(
                            title: "Attribution",
                            value: attribution,
                            note: details.attributionChips.joined(separator: " · ")
                        )
                    }

                    detailRow(
                        title: "Settlement rules",
                        value: details.settlementRules,
                        note: nil
                    )
                }
                .padding(16)
            }
            .background(DS.trackBg)
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
    }

    private func detailRow(title: String, value: String, note: String?) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textMuted)
            Text(value)
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(DS.textPrimary)
                .fixedSize(horizontal: false, vertical: true)
            if let note, !note.isEmpty {
                Text(note)
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(12)
        .background(DS.cardBg)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(DS.border, lineWidth: 0.5)
        )
    }
}

struct FuturesAtlasFullFieldSheetView11666: View {
    let marketTitle: String
    let subtitleBadge: String?
    let rows: [FuturesAtlasPresentation11666.ContenderRow]
    let selectedOutcomeId: Int?
    let onSelectOutcome: (Int) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var searchText: String = ""

    private var filteredRows: [FuturesAtlasPresentation11666.ContenderRow] {
        let query = searchText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !query.isEmpty else { return rows }
        return rows.filter { $0.name.localizedCaseInsensitiveContains(query) }
    }

    var body: some View {
        NavigationStack {
            List {
                if let badge = subtitleBadge {
                    Section {
                        Text(badge)
                            .font(.caption)
                            .foregroundStyle(DS.textSecondary)
                    }
                }
                Section("All outcomes · \(filteredRows.count)") {
                    ForEach(filteredRows) { row in
                        Button {
                            onSelectOutcome(row.id)
                        } label: {
                            HStack(alignment: .firstTextBaseline, spacing: 8) {
                                Text("#\(row.rank)")
                                    .font(.caption.weight(.semibold).monospacedDigit())
                                    .foregroundStyle(DS.textMuted)
                                    .frame(width: 28, alignment: .leading)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(row.name)
                                        .font(.subheadline.weight(row.id == selectedOutcomeId ? .semibold : .regular))
                                        .foregroundStyle(DS.textPrimary)
                                    if let opening = row.openingText {
                                        Text(opening)
                                            .font(.caption2.monospacedDigit())
                                            .foregroundStyle(DS.textMuted)
                                    }
                                }
                                Spacer()
                                VStack(alignment: .trailing, spacing: 2) {
                                    Text(row.displayValue.primaryLabel)
                                        .font(.subheadline.weight(.bold).monospacedDigit())
                                        .foregroundStyle(row.displayValue.isWon ? DS.emerald : DS.textPrimary)
                                    if let asOfText = row.displayValue.asOfText {
                                        Text(asOfText)
                                            .font(.caption2.monospacedDigit())
                                            .foregroundStyle(DS.textMuted)
                                    }
                                }
                            }
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            .searchable(text: $searchText, prompt: "Search outcomes")
            .navigationTitle(marketTitle)
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
    }
}
