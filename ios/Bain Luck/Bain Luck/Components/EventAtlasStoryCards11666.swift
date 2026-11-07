import SwiftUI

/// #11666 (Step E3) — Native event-page atlas story cards: mark-grammar keys,
/// settled winner/verdict badges (`✓ Won`, `✓ HIT` / `✗ MISS`), `"No recent probability"`
/// staleness copy, and shared `EventAtlasDetailsSheet11666` wiring for finish,
/// player milestone, and NBA ladder cards, gated behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`.
nonisolated enum EventAtlasStoryCards11666 {

    /// A single item in a story card's mark-grammar key.
    nonisolated enum MarkGlyph11666: String, Equatable, Sendable {
        case hollowCircle
        case filledCircle
        case hollowSquare
        case filledSquare
        case changeLine
        case verticalBar
        case cross
        case wonCheck
        case hitMissVerdict
    }

    nonisolated struct MarkKeyItem11666: Equatable, Identifiable, Sendable {
        var id: String { "\(glyph.rawValue)-\(label)" }
        let glyph: MarkGlyph11666
        let label: String
    }

    /// Builds the mark-grammar key items for a finish card (`NFLFinishCard9483`).
    static func finishMarkKey(for card: NFLFinishCard9483) -> [MarkKeyItem11666] {
        var items: [MarkKeyItem11666] = [
            MarkKeyItem11666(glyph: .hollowSquare, label: "Pregame")
        ]
        if card.projectedNow != nil && card.final == nil {
            items.append(MarkKeyItem11666(glyph: .filledSquare, label: "Recorded"))
            items.append(MarkKeyItem11666(glyph: .changeLine, label: "Change"))
        }
        if let final = card.final {
            items.append(MarkKeyItem11666(glyph: .cross, label: "Final"))
            if final.home != final.away {
                items.append(MarkKeyItem11666(glyph: .wonCheck, label: "✓ Won"))
            }
        }
        return items
    }

    /// Returns `"✓ Won"` for the winning side on a finished card (nil on ties or unfinished).
    static func finishWinnerBadge(for card: NFLFinishCard9483, isHome: Bool) -> String? {
        guard let final = card.final, final.home != final.away else { return nil }
        let homeWon = final.home > final.away
        return homeWon == isHome ? "✓ Won" : nil
    }

    /// Builds the mark-grammar key items for a player milestone card (`NFLMilestoneCard9483`).
    static func milestoneMarkKey(for card: NFLMilestoneCard9483) -> [MarkKeyItem11666] {
        var items: [MarkKeyItem11666] = [
            MarkKeyItem11666(glyph: .hollowCircle, label: "Pregame")
        ]
        if card.actual != nil {
            items.append(MarkKeyItem11666(glyph: .verticalBar, label: "Actual"))
        }
        if card.rungs.contains(where: { $0.hit != nil }) {
            items.append(MarkKeyItem11666(glyph: .hitMissVerdict, label: "✓ HIT / ✗ MISS"))
        }
        return items
    }

    /// Staleness copy for a milestone rung with `chance == nil`.
    static func milestoneNoChanceLabel(basis: NFLMilestoneCard9483.Basis) -> String {
        basis == .pregamePrice ? "No recent probability" : "No pregame chance"
    }

    /// Verdict label for a milestone rung under Atlas (`✓ HIT` / `✗ MISS`).
    static func milestoneVerdict(
        _ rung: NFLMilestoneCard9483.Rung,
        basis: NFLMilestoneCard9483.Basis,
        expanded: Bool
    ) -> String {
        let more = expanded ? " · details" : ""
        switch rung.hit {
        case true?:
            return "✓ HIT" + more
        case false?:
            return "✗ MISS" + more
        case nil:
            if rung.chance == nil {
                return !expanded ? "" : (basis == .pregamePrice ? "Last quote in details" : "Details")
            }
            return (basis == .pregamePrice ? "Pregame chance" : "Before kickoff") + more
        }
    }

    /// Builds the mark-grammar key items for an NBA ladder card (`NBALadderCard9483`).
    static func ladderMarkKey(for card: NBALadderCard9483) -> [MarkKeyItem11666] {
        var items: [MarkKeyItem11666] = [
            MarkKeyItem11666(glyph: .hollowCircle, label: "Pregame")
        ]
        if card.points.contains(where: { $0.now != nil }) {
            items.append(MarkKeyItem11666(glyph: .filledCircle, label: "Recorded"))
            items.append(MarkKeyItem11666(glyph: .changeLine, label: "Change"))
        }
        if card.actual != nil {
            items.append(MarkKeyItem11666(glyph: .verticalBar, label: "Actual"))
        }
        if card.forecast != nil {
            items.append(MarkKeyItem11666(glyph: .hollowSquare, label: "Projected"))
        }
        if card.points.contains(where: { $0.result != nil }) {
            items.append(MarkKeyItem11666(glyph: .hitMissVerdict, label: "✓ HIT / ✗ MISS"))
        }
        return items
    }

    /// Readout `(main, sub)` for an NBA ladder option under Atlas (`✓ HIT` / `✗ MISS`
    /// and `"No recent probability"`).
    static func ladderReadout(
        _ card: NBALadderCard9483,
        _ point: NBALadderCard9483.Point
    ) -> (main: String, sub: String) {
        let main: String
        if let chance = point.chance {
            main = "\(point.label) · \(formatProbability(chance))"
        } else {
            main = card.phase == .before ? "\(point.label) · No recent probability" : point.label
        }
        var parts: [String] = []
        if point.chance != nil {
            parts.append(card.phase == .before ? "Pregame chance" : "Before tip-off")
        } else if card.phase == .after && card.points.contains(where: { $0.chance != nil }) {
            parts.append("Pregame chance unavailable")
        }
        if let result = point.result {
            parts.append(result ? "✓ HIT" : "✗ MISS")
        }
        if let now = point.now {
            parts.append("now \(formatProbability(now))")
        }
        return (main, parts.joined(separator: " · "))
    }

    // MARK: - Shared Details Sheet Models (#11666 E3)

    /// Builds an `EventAtlasDetailsSheetModel11666` for a finish card (`NFLFinishCard9483`).
    static func detailsModel(
        for finish: NFLFinishCard9483,
        awayName: String,
        homeName: String
    ) -> EventAtlasDetailsSheetModel11666 {
        let pregameText = "\(awayName) \(NFLFinishCardView9483.pregameText(finish.pregame.away, whole: finish.printsPregameWhole)) · \(homeName) \(NFLFinishCardView9483.pregameText(finish.pregame.home, whole: finish.printsPregameWhole))"
        let primaryLabel: String
        let primaryValue: String
        if let final = finish.final {
            primaryLabel = "Final score"
            let winnerSuffix: String
            if final.home != final.away {
                winnerSuffix = " · \(final.home > final.away ? homeName : awayName) ✓ Won"
            } else {
                winnerSuffix = ""
            }
            primaryValue = "\(awayName) \(NFLFinishCardView9483.points(final.away)) – \(homeName) \(NFLFinishCardView9483.points(final.home))\(winnerSuffix)"
        } else if let now = finish.projectedNow {
            primaryLabel = "Projected now"
            primaryValue = "\(awayName) \(NFLFinishCardView9483.points(now.away)) · \(homeName) \(NFLFinishCardView9483.points(now.home))"
        } else {
            primaryLabel = "Projected finish"
            primaryValue = pregameText
        }
        let observedDate = finish.final?.at ?? finish.projectedNow?.at ?? finish.pregame.at
        let observedText = observedDate.map { EventAtlasChartMarks11666.formatExactTimestampPT($0) }
        return EventAtlasDetailsSheetModel11666(
            id: "finish-details",
            outcomeTitle: finish.headline(awayName: awayName, homeName: homeName),
            marketTitle: "\(awayName) at \(homeName) · \(finish.kicker)",
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: finish.missingCurrentNote,
            sourceLabel: nil
        )
    }

    /// Builds an `EventAtlasDetailsSheetModel11666` for a player milestone prop row.
    static func detailsModel(
        for prop: GameMarketPlayerProp?,
        card: NFLMilestoneCard9483? = nil,
        rowID: String
    ) -> EventAtlasDetailsSheetModel11666 {
        let rung = card?.rungs.first(where: { $0.rowID == rowID }) ?? card?.rungs.first
        let hit = prop?.hit ?? rung?.hit
        let pregameProb = rung?.chance ?? prop?.pregameMark
        let pregameText = pregameProb.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let hit {
            primaryLabel = "Result"
            let actualPart = (prop?.actual ?? card?.actual).map { " · Final \(NFLFinishCardView9483.points($0))" } ?? ""
            primaryValue = (hit ? "✓ HIT" : "✗ MISS") + actualPart
        } else if let quote = prop?.overProbability {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(quote)
        } else if let pregameText {
            primaryLabel = "Pregame chance"
            primaryValue = pregameText
        } else {
            primaryLabel = "Reading"
            primaryValue = "No recent probability"
        }

        let outcomeTitle: String
        if let prop {
            outcomeTitle = prop.outcomeName
        } else if let card, let rung {
            outcomeTitle = "\(card.player): \(PlayerPropsFamily.targetLabel(rung.threshold))"
        } else {
            outcomeTitle = "Player milestone"
        }

        let marketTitle: String
        if let prop {
            marketTitle = prop.marketName
        } else if let card {
            marketTitle = "\(card.player) · \(card.stat)"
        } else {
            marketTitle = "Player prop"
        }

        let rawObserved = prop?.observedAt ?? rung?.observedAt
        let observedText = rawObserved.flatMap { SourceAge.preciseStamp($0) }
        let sourceLabel = EventAtlasHeadline11666.sourceAttribution(
            source: prop?.source,
            sourceCount: 1
        )
        return EventAtlasDetailsSheetModel11666(
            id: "milestone-\(rowID)",
            outcomeTitle: outcomeTitle,
            marketTitle: marketTitle,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }

    /// Builds an `EventAtlasDetailsSheetModel11666` for an NBA ladder option detail.
    static func detailsModel(
        for detail: NBALadderCard9483.Detail,
        card: NBALadderCard9483? = nil,
        point: NBALadderCard9483.Point? = nil
    ) -> EventAtlasDetailsSheetModel11666 {
        let baselineProb = detail.baseline ?? (card?.phase == .before ? point?.chance : nil)
        let pregameText = baselineProb.map { prob in
            let stamp = SourceAge.preciseStamp(detail.baselineObservedAt)
            return stamp.map { "\(formatProbability(prob)) · \($0)" } ?? formatProbability(prob)
        }
        let primaryLabel: String
        let primaryValue: String
        if let result = detail.result {
            primaryLabel = "Result"
            let actualPart = card?.actual.map { " · Final \(card?.words($0) ?? "")" } ?? ""
            primaryValue = (result ? "✓ HIT" : "✗ MISS") + actualPart
        } else if let now = point?.now ?? detail.quoted {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(now)
        } else if let baselineProb {
            primaryLabel = "Pregame baseline"
            primaryValue = formatProbability(baselineProb)
        } else {
            primaryLabel = "Reading"
            primaryValue = "No recent probability"
        }

        let observedText = SourceAge.preciseStamp(detail.observedAt)
        let sourceLabel = EventAtlasHeadline11666.sourceAttribution(
            source: detail.source,
            sourceCount: 1
        )
        return EventAtlasDetailsSheetModel11666(
            id: "ladder-\(detail.label)",
            outcomeTitle: detail.label,
            marketTitle: detail.marketName,
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: sourceLabel
        )
    }

    /// Resolves a reader details sheet (`NFLCardReader9483`) for a given `rowID`
    /// when `ReleaseSurfaces.isEventPageAtlasEnabled()` is active, including MLB
    /// story card originals (`#11666` Step E6a).
    static func readerDetailsModel(
        rowID: String,
        cards: [NFLEventCard9483],
        rows: [String: GameMarketPlayerProp],
        awayName: String,
        homeName: String
    ) -> EventAtlasDetailsSheetModel11666? {
        if let mlbOriginal = MLBFinalDeck11284.original(rowID, in: cards) {
            return EventAtlasMlbCards11666.detailsModel(for: mlbOriginal)
        }
        for card in cards {
            if case .nhlScoring(let scoring) = card,
               let entry = scoring.entries.first(where: { $0.id == rowID || $0.rowId == rowID }) {
                return EventAtlasNhlCards11666.detailsModel(for: entry, card: scoring)
            }
        }
        if rowID == "finish" {
            for card in cards {
                if case .finish(let finish) = card {
                    return detailsModel(for: finish, awayName: awayName, homeName: homeName)
                }
            }
        }
        if rows[rowID] == nil,
           let detail = NFLCardReaderHold9483.ladderDetail(rowID, in: cards) {
            var matchedCard: NBALadderCard9483?
            var matchedPoint: NBALadderCard9483.Point?
            for card in cards {
                if case .ladder(let ladder) = card,
                   let pt = ladder.points.first(where: { $0.optionKey == rowID }) {
                    matchedCard = ladder
                    matchedPoint = pt
                    break
                }
            }
            return detailsModel(for: detail, card: matchedCard, point: matchedPoint)
        }
        var matchedMilestone: NFLMilestoneCard9483?
        for card in cards {
            if case .milestone(let milestone) = card,
               milestone.rungs.contains(where: { $0.rowID == rowID }) {
                matchedMilestone = milestone
                break
            }
        }
        return detailsModel(for: rows[rowID], card: matchedMilestone, rowID: rowID)
    }
}

/// Compact mark-grammar key strip rendered at the top of a story card when
/// `ReleaseSurfaces.isEventPageAtlasEnabled()` is active.
struct EventAtlasStoryCardMarkKeyView11666: View {
    let items: [EventAtlasStoryCards11666.MarkKeyItem11666]

    var body: some View {
        HStack(spacing: 10) {
            ForEach(items) { item in
                HStack(spacing: 4) {
                    glyphView(item.glyph)
                        .accessibilityHidden(true)
                    Text(item.label)
                        .font(.caption2)
                        .foregroundStyle(item.glyph == .wonCheck ? Color.green : Color.secondary)
                }
            }
        }
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("atlas-story-card-mark-key-11666")
    }

    @ViewBuilder
    private func glyphView(_ glyph: EventAtlasStoryCards11666.MarkGlyph11666) -> some View {
        switch glyph {
        case .hollowCircle:
            Circle()
                .strokeBorder(Color.secondary, lineWidth: 1.5)
                .frame(width: 7, height: 7)
        case .filledCircle:
            Circle()
                .fill(Color.primary)
                .frame(width: 7, height: 7)
        case .hollowSquare:
            Rectangle()
                .strokeBorder(Color.secondary, lineWidth: 1.5)
                .frame(width: 7, height: 7)
        case .filledSquare:
            Rectangle()
                .fill(Color.primary)
                .frame(width: 7, height: 7)
        case .changeLine:
            Rectangle()
                .fill(Color.secondary)
                .frame(width: 10, height: 1.5)
        case .verticalBar:
            Rectangle()
                .fill(Color.primary)
                .frame(width: 1.5, height: 8)
        case .cross:
            Image(systemName: "plus")
                .font(.system(size: 8, weight: .bold))
                .foregroundStyle(Color.primary)
        case .wonCheck, .hitMissVerdict:
            EmptyView()
        }
    }
}
