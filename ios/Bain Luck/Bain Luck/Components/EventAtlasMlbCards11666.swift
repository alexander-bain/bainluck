import SwiftUI

/// #11666 Step E6a — Native Event-page Atlas MLB story cards (`baseball_mlb`),
/// gated behind `ReleaseSurfaces.isEventPageAtlasEnabled()`:
/// - Mark-grammar keys (`EventAtlasStoryCardMarkKeyView11666`) for MLB home runs,
///   strikeouts, run totals, extra innings, and series cards.
/// - Shared Atlas verdict vocabulary (`✓ Won`, `✗ Lost`, `Open`, `Pending`,
///   `Not confirmed`) on MLB story card rows and readouts.
/// - Shared `EventAtlasDetailsSheetModel11666` conversion from `MLBOriginal11284`
///   so tapping any MLB story card row in `NFLCardReader9483` presents the
///   unified Atlas details sheet.
/// - Pregame/live/final extra-innings outcome builder that uses served
///   `pregameMark` without client averaging, withholds unblended multi-source
///   probabilities, and grades settled outcomes via `OutcomeVerdict.verdict`.
nonisolated enum EventAtlasMlbCards11666 {

    struct ExtraInningsEntry: Equatable, Identifiable, Sendable {
        let id: String
        let label: String
        let pregameChance: Double?
        let quotedChance: Double?
        let observedAt: String?
        let venueResult: MLBVenueResult11284
        let source: String?
        let sourceCount: Int
        let marketTitle: String
    }

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && sportKey == MLBFinalPage11284.sportKey
    }

    /// Verdict label for an `MLBVenueResult11284` under Atlas (`✓ Won` / `✗ Lost`).
    static func verdictLabel(
        _ result: MLBVenueResult11284,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> String {
        guard atlasEnabled else { return result.label }
        switch result {
        case .won:
            return EventAtlasStates11666.wonWithCheck
        case .lost:
            return EventAtlasStates11666.lostWithCross
        case .open:
            return "Open"
        case .pending:
            return EventAtlasStates11666.pending
        case .notConfirmed:
            return "Not confirmed"
        }
    }

    /// Builds the mark-grammar key items for any `MLBFinalCard11284` slot.
    static func markKey(for card: MLBFinalCard11284) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        typealias Item = EventAtlasStoryCards11666.MarkKeyItem11666
        var items: [Item] = [Item(glyph: .hollowCircle, label: "Pregame")]
        switch card {
        case .homeRuns(let hr):
            if hr.entries.contains(where: { $0.finalCount != nil }) {
                items.append(Item(glyph: .verticalBar, label: "Official final"))
            }
            if hr.story == .homered {
                items.append(Item(glyph: .wonCheck, label: EventAtlasStates11666.wonWithCheck))
            }
        case .strikeouts(let ks):
            if ks.finalCount != nil {
                items.append(Item(glyph: .verticalBar, label: "Official final"))
            }
        case .totals(let totals):
            if totals.actualTotal != nil {
                items.append(Item(glyph: .verticalBar, label: "Actual"))
            }
            if totals.lines.contains(where: { $0.venueResult == .won || $0.venueResult == .lost }) {
                items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
            }
        case .extraInnings(let extra):
            if extra.outcomes.contains(where: { $0.venueResult == .won || $0.venueResult == .lost }) {
                items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
            }
        case .series(let series):
            let hasSettled = series.questions.contains { q in
                q.options.contains { $0.result == .won || $0.result == .lost }
            }
            if hasSettled {
                items.append(Item(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
            }
        }
        return items
    }

    /// Converts an `MLBOriginal11284` into the shared `EventAtlasDetailsSheetModel11666`.
    static func detailsModel(for original: MLBOriginal11284) -> EventAtlasDetailsSheetModel11666 {
        let allFields = original.sections.flatMap(\.fields)
        func fieldValue(_ exactLabel: String) -> String? {
            allFields.first(where: { $0.label.lowercased() == exactLabel.lowercased() })?.value
        }
        func fieldValuePrefix(_ labelPrefix: String) -> String? {
            allFields.first(where: { $0.label.lowercased().hasPrefix(labelPrefix.lowercased()) })?.value
        }

        let venueSettlement = fieldValue("Venue settlement") ?? fieldValue("Venue result")
        let officialFinal = fieldValue("Official final")
        let savedPregame = fieldValue("Saved pregame chance")
            ?? fieldValue("Pregame chance")
            ?? fieldValue("Pregame mark")

        let primaryLabel: String
        let primaryValue: String
        if let venueSettlement, venueSettlement == "Won" || venueSettlement == "Lost" {
            primaryLabel = "Result"
            let badge = venueSettlement == "Won"
                ? EventAtlasStates11666.wonWithCheck
                : EventAtlasStates11666.lostWithCross
            if let officialFinal, officialFinal != "Unavailable" && officialFinal != "Pending" {
                primaryValue = "\(badge) · \(officialFinal)"
            } else {
                primaryValue = badge
            }
        } else if let officialFinal, officialFinal != "Unavailable" && officialFinal != "Pending" {
            primaryLabel = "Official final"
            primaryValue = officialFinal
        } else if let savedPregame, savedPregame != "Unavailable" {
            primaryLabel = "Pregame chance"
            primaryValue = savedPregame
        } else {
            primaryLabel = "Venue result"
            primaryValue = venueSettlement ?? EventAtlasStates11666.noRecentPrice
        }

        let observedText = fieldValue("Saved")
        let rawVenue = fieldValue("Venue")
        let sourceLabel = EventAtlasHeadline11666.sourceAttribution(
            source: rawVenue,
            sourceCount: 1
        )
        let outcomeSide = fieldValue("Original side") ?? original.title

        return EventAtlasDetailsSheetModel11666(
            id: original.id,
            outcomeTitle: outcomeSide,
            marketTitle: original.title,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: savedPregame != "Unavailable" ? savedPregame : nil,
            observedAtText: observedText != "time unavailable" ? observedText : nil,
            statusSummary: fieldValuePrefix("Against "),
            sourceLabel: sourceLabel
        )
    }

    /// Builds Atlas extra-innings entries from `GameMarketOther` rows, matching
    /// web `#11974` Step E6a:
    /// - Uses a blended row (`source == "blended"` or `"blend"`) when served,
    ///   or a single venue's `pregameMark` when only one source is present.
    /// - Withholds `pregameChance` when multiple unblended venues exist for an
    ///   outcome (never averages on the client).
    /// - Grades settled outcomes via `OutcomeVerdict.verdict` (`marketResolved: finished`),
    ///   falling back to `.pending` when venues disagree.
    static func buildExtraInningsEntries(
        rows: [GameMarketOther],
        finished: Bool,
        isBefore: Bool,
        now: Date = Date()
    ) -> [ExtraInningsEntry] {
        let extraRows = rows.filter { MLBExtraInningsCard11284.isExtraInnings($0) }
        guard !extraRows.isEmpty else { return [] }

        var byLabel: [String: [GameMarketOther]] = [:]
        var labelOrder: [String] = []
        for row in extraRows {
            let trimmed = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !trimmed.isEmpty else { continue }
            if byLabel[trimmed] == nil {
                labelOrder.append(trimmed)
            }
            byLabel[trimmed, default: []].append(row)
        }

        var entries: [ExtraInningsEntry] = []
        for label in labelOrder {
            guard let group = byLabel[label], let first = group.first else { continue }
            let sources = Set(group.compactMap(\.source))
            let blendedRow = group.first { $0.source == "blended" || $0.source == "blend" }

            func rowPregame(_ r: GameMarketOther) -> Double? {
                if isBefore {
                    guard NFLMilestoneCard9483.isRecent(r.observedAt, now: now) else { return nil }
                    return MLBOriginal11284.openChance(r.probability)
                }
                return MLBOriginal11284.openChance(r.pregameMark)
            }

            let pricedRows = group.filter { rowPregame($0) != nil }
            let pregameChance: Double?
            let observedAt: String?
            if let blendedRow {
                pregameChance = rowPregame(blendedRow)
                observedAt = blendedRow.observedAt ?? first.observedAt
            } else if sources.count <= 1 && pricedRows.count == 1, let single = pricedRows.first {
                pregameChance = rowPregame(single)
                observedAt = single.observedAt ?? first.observedAt
            } else {
                // Withhold unblended multi-source pregame chance rather than averaging on the client.
                pregameChance = nil
                observedAt = first.observedAt
            }

            let quotedChance: Double? = !finished && NFLMilestoneCard9483.isRecent(first.observedAt, now: now)
                ? (blendedRow.flatMap { MLBOriginal11284.openChance($0.probability) }
                    ?? (sources.count <= 1 ? MLBOriginal11284.openChance(first.probability) : nil))
                : nil

            var verdicts = Set<OutcomeVerdict>()
            for r in group {
                if let v = OutcomeVerdict.verdict(
                    isWinner: r.isWinner,
                    resolutionSource: r.resolutionSource,
                    marketResolved: finished
                ) {
                    verdicts.insert(v)
                }
            }
            let venueResult: MLBVenueResult11284
            if verdicts.contains(.won) && verdicts.contains(.lost) {
                venueResult = .pending
            } else if verdicts.contains(.won) {
                venueResult = .won
            } else if verdicts.contains(.lost) {
                venueResult = .lost
            } else {
                venueResult = finished ? .pending : .open
            }

            let singleSource = blendedRow?.source ?? (sources.count == 1 ? sources.first : nil)
            entries.append(
                ExtraInningsEntry(
                    id: "mlb-extra:\(label.lowercased())",
                    label: label,
                    pregameChance: pregameChance,
                    quotedChance: quotedChance,
                    observedAt: observedAt,
                    venueResult: venueResult,
                    source: singleSource,
                    sourceCount: max(1, sources.count),
                    marketTitle: first.marketName
                )
            )
        }

        let hasSignal = finished
            ? entries.contains { $0.venueResult == .won || $0.venueResult == .lost || $0.pregameChance != nil }
            : entries.contains { $0.pregameChance != nil || $0.quotedChance != nil }
        return hasSignal ? entries : []
    }
}
