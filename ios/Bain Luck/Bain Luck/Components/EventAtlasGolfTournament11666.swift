import Charts
import SwiftUI

/// #11666 (Items 14a–b, 91-C) — Native Golf Tournament Atlas presentation:
///   1. Tournament Win-Probability Journey card with `Auto` / `Full` (`0–100%`) scale toggle
///      and selectable contender chips.
///   2. Selected Golfer's Finish Expectations (`GolfFinishExpectationPresentation10868`)
///      with 4 slots (`Win / Top 5 / Top 10 / Top 20`) plus the optional 5th `"Make cut"`
///      slot when the tournament holds a Make-the-Cut market — each slot reading only its
///      own market's unclamped price, timestamp, and venue grade.
///   3. Contender Chooser with `Chances` / `Movement` / `All` modes and surname bands
///      (`A–F`, `G–L`, `M–R`, `S–Z`).
///   4. Round Leaders & Top Finishers card (`roundTopGroups`) and Closing-Round
///      strokes-against-par card (`ClosingRoundCard`).
enum EventAtlasGolfTournament11666 {
    static let palette: [Color] = [
        Color(red: 0.05, green: 0.45, blue: 0.42),
        Color(red: 0.14, green: 0.39, blue: 0.78),
        Color(red: 0.78, green: 0.38, blue: 0.08),
        Color(red: 0.56, green: 0.24, blue: 0.68),
        Color(red: 0.74, green: 0.19, blue: 0.32),
        Color(red: 0.22, green: 0.52, blue: 0.24),
    ]

    // MARK: - Chooser Mode & Surname Band

    nonisolated enum ChooserMode: String, CaseIterable, Equatable, Sendable {
        case chances = "Chances"
        case movement = "Movement"
        case all = "All"
    }

    nonisolated enum SurnameBand: String, CaseIterable, Equatable, Sendable {
        case all = "All"
        case aToF = "A–F"
        case gToL = "G–L"
        case mToR = "M–R"
        case sToZ = "S–Z"

        func contains(golferName: String) -> Bool {
            guard self != .all else { return true }
            let surname = EventAtlasGolfTournament11666.surnameSortKey(golferName)
            guard let first = surname.uppercased().first else { return false }
            switch self {
            case .all: return true
            case .aToF: return first >= "A" && first <= "F"
            case .gToL: return first >= "G" && first <= "L"
            case .mToR: return first >= "M" && first <= "R"
            case .sToZ: return first >= "S" && first <= "Z"
            }
        }
    }

    // MARK: - Held Atlas Data

    nonisolated struct TournamentAtlasData: Equatable, Sendable {
        var winnerMarket: FuturesMarketDetail? = nil
        var winnerTimeline: ProbabilityTimelineResponse? = nil
        var top5Market: FuturesMarketDetail? = nil
        var top10Market: FuturesMarketDetail? = nil
        var top20Market: FuturesMarketDetail? = nil
        var makeCutMarket: FuturesMarketDetail? = nil
        var closingRound: ClosingRoundCard? = nil
        var hasMakeCutMarket: Bool = false
        var failedMarketSlots: Set<String> = []
        var winnerTimelineFailed: Bool = false

        static func == (lhs: Self, rhs: Self) -> Bool {
            lhs.winnerMarket?.id == rhs.winnerMarket?.id
                && lhs.winnerMarket?.updatedAt == rhs.winnerMarket?.updatedAt
                && lhs.winnerTimeline?.marketId == rhs.winnerTimeline?.marketId
                && lhs.winnerTimeline?.timeline.count == rhs.winnerTimeline?.timeline.count
                && lhs.top5Market?.id == rhs.top5Market?.id
                && lhs.top10Market?.id == rhs.top10Market?.id
                && lhs.top20Market?.id == rhs.top20Market?.id
                && lhs.makeCutMarket?.id == rhs.makeCutMarket?.id
                && lhs.closingRound == rhs.closingRound
                && lhs.hasMakeCutMarket == rhs.hasMakeCutMarket
                && lhs.failedMarketSlots == rhs.failedMarketSlots
                && lhs.winnerTimelineFailed == rhs.winnerTimelineFailed
        }
    }

    // MARK: - Closing Round Card Model

    nonisolated struct ClosingRoundRow: Equatable, Identifiable, Sendable {
        let id: String
        let golferName: String
        let strokesToPar: Int
        let preTournamentWinChance: Double?
        let finishLabel: String?
        let verdict: OutcomeVerdict?
    }

    nonisolated struct ClosingRoundCard: Equatable, Sendable {
        let tournamentName: String
        let rows: [ClosingRoundRow]

        var minStrokes: Int { rows.map(\.strokesToPar).min() ?? -10 }
        var maxStrokes: Int { rows.map(\.strokesToPar).max() ?? 5 }

        func selectedRow(named golferName: String?) -> ClosingRoundRow? {
            guard let golferName else { return rows.first }
            let target = EventAtlasGolfTournament11666.normalizeGolferName(golferName)
            let matches = rows.filter { EventAtlasGolfTournament11666.normalizeGolferName($0.golferName) == target }
            return matches.count == 1 ? matches[0] : nil
        }

        static func formatStrokes(_ strokes: Int) -> String {
            if strokes == 0 { return "E" }
            return strokes > 0 ? "+\(strokes)" : "\(strokes)"
        }
    }

    // MARK: - Details Sheet Item

    nonisolated struct FinishDetailsSheetItem: Identifiable, Equatable, Sendable {
        let id: String
        let finishTitle: String
        let golferName: String
        let marketName: String
        let phase: GolfFinishPhase10868
        let beforePercent: String?
        let recordedPercent: String?
        var beforeMissingText: String = "Not recorded"
        var recordedMissingText: String = "No recent probability"
        var deltaText: String? = nil
        let resultText: String?
        let observedTimestampPT: String?
        let sourceAttribution: String?
    }

    // MARK: - Pure Builders & Helpers

    nonisolated static func normalizeGolferName(_ raw: String) -> String {
        let folded = raw.folding(options: [.diacriticInsensitive, .caseInsensitive], locale: Locale(identifier: "en_US_POSIX"))
        let scalars = folded.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) || $0 == " " }
        return String(String.UnicodeScalarView(scalars))
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
    }

    nonisolated static func surnameSortKey(_ name: String) -> String {
        let parts = name.trimmingCharacters(in: .whitespacesAndNewlines)
            .split(whereSeparator: \.isWhitespace)
            .map(String.init)
        guard let last = parts.last else { return name }
        let suffixes: Set<String> = ["jr", "jr.", "sr", "sr.", "ii", "iii", "iv"]
        if parts.count >= 2, suffixes.contains(last.lowercased()) {
            return parts[parts.count - 2] + " " + parts.dropLast(2).joined(separator: " ")
        }
        return last + " " + parts.dropLast().joined(separator: " ")
    }

    nonisolated static func resolvePhase(
        scheduleStatus: String?,
        commenceTime: String?,
        winnerMarket: FuturesMarketDetail?,
        field: [GolfTournamentFieldRow],
        now: Date = Date()
    ) -> GolfFinishPhase10868 {
        let status = scheduleStatus?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let marketStatus = winnerMarket?.status?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if EventState.isFinished(status)
            || SettledQuote.isSettled(status)
            || EventState.isFinished(marketStatus)
            || SettledQuote.isSettled(marketStatus)
            || field.contains(where: { $0.isWinner == true })
            || (winnerMarket?.outcomes.contains(where: { $0.isWinner != nil }) == true)
        {
            return .final
        }
        if let status, !status.isEmpty, !SettledQuote.isPregame(status) || status == "active" {
            return .recorded
        }
        if let iso = commenceTime ?? winnerMarket?.commenceTime,
           let start = iso.asDate
        {
            return now >= start ? .recorded : .before
        }
        return .before
    }

    nonisolated static func isMarketResolved(_ market: FuturesMarketDetail?) -> Bool {
        guard let market else { return false }
        let st = market.status?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if EventState.isFinished(st) || SettledQuote.isSettled(st) { return true }
        return market.outcomes.contains(where: { $0.isWinner != nil })
    }

    /// Finds an unambiguous 1-to-1 outcome match for `golferName` inside `market`.
    /// Never guesses when 0 or >1 outcomes match the normalized name.
    nonisolated static func findOutcome(
        for golferName: String,
        in market: FuturesMarketDetail?
    ) -> FuturesOutcome? {
        guard let market else { return nil }
        let target = normalizeGolferName(golferName)
        guard !target.isEmpty else { return nil }
        let matches = market.outcomes.filter { normalizeGolferName($0.name) == target }
        return matches.count == 1 ? matches[0] : nil
    }

    private nonisolated static func validChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value >= 0, value <= 1 else { return nil }
        return value
    }

    nonisolated static func formatSourceDisplay(_ raw: String?) -> String {
        guard let raw = raw?.trimmingCharacters(in: .whitespacesAndNewlines), !raw.isEmpty else {
            return "Market source"
        }
        switch raw.lowercased() {
        case "datagolf", "datagolf_model": return "DataGolf model"
        case "kalshi", "polymarket", "odds_api", "sportsbook": return "Market"
        default: return raw.capitalized
        }
    }

    private nonisolated static func buildSlot(
        selection: String,
        name: String,
        color: Color,
        golferName: String,
        phase: GolfFinishPhase10868,
        market: FuturesMarketDetail?,
        fallbackWinRow: GolfTournamentFieldRow? = nil,
        isTournamentSettled: Bool = false,
        loadFailed: Bool = false,
        now: Date
    ) -> GolfFinishSlot10868 {
        if loadFailed {
            return GolfFinishSlot10868(
                selection: selection,
                name: name,
                color: color,
                before: nil,
                recorded: nil,
                beforeMissing: "Couldn’t load market",
                recordedMissing: "Couldn’t load market",
                actual: GolfFinishResult10868(
                    text: phase == .final ? "Couldn’t load market" : "Pending",
                    mark: .unknown
                ),
                deltaText: nil
            )
        }

        let outcome = findOutcome(for: golferName, in: market)
        let observedIso = outcome?.observedAt ?? outcome?.lastUpdated ?? market?.updatedAt
        let recent = market == nil ? true : NFLMilestoneCard9483.isRecent(observedIso, now: now)
        let sourceText = formatSourceDisplay(market?.source)
        let timeText = observedIso?.asDate.map { EventAtlasChartMarks11666.formatExactTimestampPT($0) }

        let detailSuffix: String = {
            if let timeText {
                return "recorded \(timeText) · \(sourceText)"
            }
            return sourceText
        }()

        let beforeObs: GolfFinishObservation10868?
        let recordedObs: GolfFinishObservation10868?
        let beforeMissing: String
        let recordedMissing: String

        switch phase {
        case .before:
            // Before tee-off, never read openingProbability as the current quote.
            let rawProb = validChance(outcome?.probability ?? fallbackWinRow?.probability)
            if let rawProb, recent {
                let text = formatProbability(rawProb)
                beforeObs = GolfFinishObservation10868(
                    probability: rawProb,
                    text: text,
                    accessibilityDetail: detailSuffix
                )
                beforeMissing = "Not recorded"
            } else {
                beforeObs = nil
                beforeMissing = (rawProb != nil && !recent) ? "No recent probability" : "Not recorded"
            }
            recordedObs = nil
            recordedMissing = "Not recorded"

        case .recorded:
            if let openProb = validChance(outcome?.openingProbability ?? fallbackWinRow?.openingProbability) {
                beforeObs = GolfFinishObservation10868(
                    probability: openProb,
                    text: formatProbability(openProb),
                    accessibilityDetail: "Opened · \(sourceText)"
                )
                beforeMissing = "Not recorded"
            } else {
                beforeObs = nil
                beforeMissing = "Not recorded"
            }
            let liveProb = validChance(outcome?.probability ?? fallbackWinRow?.probability)
            if let liveProb, recent {
                recordedObs = GolfFinishObservation10868(
                    probability: liveProb,
                    text: formatProbability(liveProb),
                    accessibilityDetail: detailSuffix
                )
                recordedMissing = "Not recorded"
            } else {
                recordedObs = nil
                recordedMissing = (liveProb != nil && !recent) ? "No recent probability" : "Not recorded"
            }

        case .final:
            if let openProb = validChance(outcome?.openingProbability ?? fallbackWinRow?.openingProbability) {
                beforeObs = GolfFinishObservation10868(
                    probability: openProb,
                    text: formatProbability(openProb),
                    accessibilityDetail: "Opened · \(sourceText)"
                )
            } else {
                beforeObs = nil
            }
            beforeMissing = "Not recorded"
            recordedObs = nil
            recordedMissing = "Not recorded"
        }

        let deltaText: String? = {
            guard phase == .recorded,
                  let openProb = beforeObs?.probability,
                  let liveProb = recordedObs?.probability
            else { return nil }
            if let pts = formatMovementPoints(liveProb - openProb) {
                return "\(pts) since open"
            }
            return "0.0 pts since open"
        }()

        let actual: GolfFinishResult10868 = {
            guard phase == .final else {
                return GolfFinishResult10868(text: "Pending", mark: .unknown)
            }
            let resolved = isMarketResolved(market) || isTournamentSettled
            if let outcome {
                let verdict = OutcomeVerdict.verdict(
                    isWinner: outcome.isWinner,
                    resolutionSource: outcome.resolutionSource,
                    marketResolved: resolved
                )
                switch verdict {
                case .won:
                    return GolfFinishResult10868(text: positiveResultWord(for: selection), mark: .success)
                case .lost:
                    return GolfFinishResult10868(text: negativeResultWord(for: selection), mark: .failure)
                case nil:
                    return GolfFinishResult10868(text: "Result not confirmed", mark: .unknown)
                }
            }
            if let fallbackWinRow, selection == "win", fallbackWinRow.isWinner == true {
                return GolfFinishResult10868(text: "Won", mark: .success)
            }
            return GolfFinishResult10868(text: "Result not confirmed", mark: .unknown)
        }()

        return GolfFinishSlot10868(
            selection: selection,
            name: name,
            color: color,
            before: beforeObs,
            recorded: recordedObs,
            beforeMissing: beforeMissing,
            recordedMissing: recordedMissing,
            actual: actual,
            deltaText: deltaText
        )
    }

    private nonisolated static func positiveResultWord(for selection: String) -> String {
        switch selection {
        case "win": return "Won"
        case "top5": return "Inside Top 5"
        case "top10": return "Inside Top 10"
        case "top20": return "Inside Top 20"
        case "makeCut": return "Made cut"
        default: return "Won"
        }
    }

    private nonisolated static func negativeResultWord(for selection: String) -> String {
        switch selection {
        case "win": return "Not won"
        case "top5": return "Outside Top 5"
        case "top10": return "Outside Top 10"
        case "top20": return "Outside Top 20"
        case "makeCut": return "Missed cut"
        default: return "Not won"
        }
    }

    /// Builds `GolfFinishExpectationInput10868` for `selectedGolferName`.
    /// Includes the 5th `makeCut` slot when `atlasData.makeCutMarket` is present or its market exists in the tournament.
    nonisolated static func buildFinishExpectations(
        selectedGolferName: String,
        presentation: GolfTournamentPresentation,
        atlasData: TournamentAtlasData,
        selectedFinish: String? = nil,
        color: Color = palette[0],
        now: Date = Date()
    ) -> GolfFinishExpectationInput10868 {
        let phase = resolvePhase(
            scheduleStatus: presentation.scheduleStatus,
            commenceTime: presentation.commenceTime,
            winnerMarket: atlasData.winnerMarket,
            field: presentation.field,
            now: now
        )
        let isSettled = phase == .final
        let target = normalizeGolferName(selectedGolferName)
        let fieldMatches = presentation.field.filter { normalizeGolferName($0.name) == target }
        let fallbackWinRow = fieldMatches.count == 1 ? fieldMatches[0] : nil

        let winSlot = buildSlot(
            selection: "win",
            name: "Win",
            color: color,
            golferName: selectedGolferName,
            phase: phase,
            market: atlasData.winnerMarket,
            fallbackWinRow: fallbackWinRow,
            isTournamentSettled: isSettled,
            loadFailed: atlasData.failedMarketSlots.contains("win"),
            now: now
        )
        let top5Slot = buildSlot(
            selection: "top5",
            name: "Top 5",
            color: color,
            golferName: selectedGolferName,
            phase: phase,
            market: atlasData.top5Market,
            isTournamentSettled: isSettled,
            loadFailed: atlasData.failedMarketSlots.contains("top5"),
            now: now
        )
        let top10Slot = buildSlot(
            selection: "top10",
            name: "Top 10",
            color: color,
            golferName: selectedGolferName,
            phase: phase,
            market: atlasData.top10Market,
            isTournamentSettled: isSettled,
            loadFailed: atlasData.failedMarketSlots.contains("top10"),
            now: now
        )
        let top20Slot = buildSlot(
            selection: "top20",
            name: "Top 20",
            color: color,
            golferName: selectedGolferName,
            phase: phase,
            market: atlasData.top20Market,
            isTournamentSettled: isSettled,
            loadFailed: atlasData.failedMarketSlots.contains("top20"),
            now: now
        )
        let shouldIncludeMakeCut = atlasData.makeCutMarket != nil
            || atlasData.hasMakeCutMarket
            || atlasData.failedMarketSlots.contains("makeCut")
        let makeCutSlot: GolfFinishSlot10868? = shouldIncludeMakeCut ? buildSlot(
            selection: "makeCut",
            name: "Make cut",
            color: color,
            golferName: selectedGolferName,
            phase: phase,
            market: atlasData.makeCutMarket,
            isTournamentSettled: isSettled,
            loadFailed: atlasData.failedMarketSlots.contains("makeCut"),
            now: now
        ) : nil

        let contextText: String? = {
            let observedIso = findOutcome(for: selectedGolferName, in: atlasData.winnerMarket)?.observedAt
                ?? findOutcome(for: selectedGolferName, in: atlasData.winnerMarket)?.lastUpdated
                ?? atlasData.winnerMarket?.updatedAt
            let pt = observedIso?.asDate.map { EventAtlasChartMarks11666.formatExactTimestampPT($0) }
            switch phase {
            case .before:
                return pt.map { "Pre-tournament · updated \($0)" } ?? "Pre-tournament expectations"
            case .recorded:
                return pt.map { "In play · latest recorded \($0) · vs open" } ?? "In play · recorded vs opening chance"
            case .final:
                return "Final · opening chances beside confirmed results"
            }
        }()

        let actualSummary: String? = {
            guard phase == .final,
                  let closingRow = atlasData.closingRound?.selectedRow(named: selectedGolferName)
            else { return nil }
            let strokes = ClosingRoundCard.formatStrokes(closingRow.strokesToPar)
            if let finish = closingRow.finishLabel, !finish.isEmpty {
                return "\(finish) · \(strokes)"
            }
            return strokes
        }()

        let allSlots = [winSlot, top5Slot, top10Slot, top20Slot] + (makeCutSlot.map { [$0] } ?? [])
        let anyLoadFailed = !atlasData.failedMarketSlots.isEmpty
        let allEmpty = allSlots.allSatisfy { $0.before == nil && $0.recorded == nil }
        let useOpeningLabels = phase != .before

        return GolfFinishExpectationInput10868(
            win: winSlot,
            top5: top5Slot,
            top10: top10Slot,
            top20: top20Slot,
            phase: phase,
            title: "Finish expectations",
            golferName: selectedGolferName,
            context: contextText,
            actualSummary: actualSummary,
            selected: phase == .recorded ? selectedFinish : nil,
            makeCut: makeCutSlot,
            beforeLabel: useOpeningLabels ? "Opened" : GolfFinishExpectationInput10868.beforeTitle,
            beforeColumnLabel: useOpeningLabels ? "Opened" : "Before",
            finalBarsExplanation: "Bars show opening market chances.",
            missingBaselinesExplanation: (anyLoadFailed && allEmpty)
                ? "Couldn’t load finish markets."
                : (useOpeningLabels ? "Opening chances weren’t recorded." : "Pre-tournament chances weren’t recorded."),
            missingRecordedExplanation: (anyLoadFailed && allEmpty)
                ? "Couldn’t load finish markets."
                : "No recorded finish estimates for this golfer at this moment.",
            finalFootnotePrefix: "Actual finish is separate from each opening chance."
        )
    }

    nonisolated static func buildFinishDetailsItem(
        selection: String,
        golferName: String,
        finishInput: GolfFinishExpectationInput10868,
        atlasData: TournamentAtlasData
    ) -> FinishDetailsSheetItem? {
        guard let slot = finishInput.slots.first(where: { $0.selection == selection }) else { return nil }
        let market: FuturesMarketDetail? = {
            switch selection {
            case "win": return atlasData.winnerMarket
            case "top5": return atlasData.top5Market
            case "top10": return atlasData.top10Market
            case "top20": return atlasData.top20Market
            case "makeCut": return atlasData.makeCutMarket
            default: return nil
            }
        }()
        let outcome = findOutcome(for: golferName, in: market)
        let observedIso = outcome?.observedAt ?? outcome?.lastUpdated ?? market?.updatedAt
        let pt = observedIso?.asDate.map { EventAtlasChartMarks11666.formatExactTimestampPT($0) }
        let sourceAttr: String? = {
            guard let src = market?.source, !src.isEmpty else { return nil }
            return "\(formatSourceDisplay(src)) market"
        }()

        return FinishDetailsSheetItem(
            id: "\(golferName)-\(selection)",
            finishTitle: slot.name,
            golferName: golferName,
            marketName: market?.name ?? "\(slot.name) market",
            phase: finishInput.phase,
            beforePercent: slot.before?.text,
            recordedPercent: slot.recorded?.text,
            beforeMissingText: slot.beforeMissing,
            recordedMissingText: slot.recordedMissing,
            deltaText: slot.deltaText,
            resultText: finishInput.phase == .final ? slot.actual.text : nil,
            observedTimestampPT: pt,
            sourceAttribution: sourceAttr
        )
    }

    // MARK: - Journey Chart Model

    nonisolated struct JourneyPoint: Equatable, Identifiable, Sendable {
        var id: String { "\(golferName)-\(date.timeIntervalSince1970)" }
        let golferName: String
        let date: Date
        let probability: Double
    }

    nonisolated struct JourneyContender: Equatable, Identifiable, Sendable {
        var id: String { name }
        let name: String
        let colorIndex: Int
        let openingProbability: Double?
        let currentProbability: Double?
        let finalVerdict: OutcomeVerdict?
        var loadFailed: Bool = false
        let points: [JourneyPoint]
    }

    /// Computes the `Auto` Y-axis upper bound (`0.20`, `0.30`, `0.50`, `0.75`, `1.00`)
    /// or `1.00` when `fullScale` is true.
    nonisolated static func yAxisCeiling(contenders: [JourneyContender], fullScale: Bool) -> Double {
        if fullScale { return 1.0 }
        let maxPoint = contenders.flatMap { $0.points.map(\.probability) }.max() ?? 0
        let maxCurrent = contenders.compactMap(\.currentProbability).max() ?? 0
        let maxOpen = contenders.compactMap(\.openingProbability).max() ?? 0
        let peak = max(maxPoint, max(maxCurrent, maxOpen))
        if peak <= 0.18 { return 0.20 }
        if peak <= 0.28 { return 0.30 }
        if peak <= 0.45 { return 0.50 }
        if peak <= 0.70 { return 0.75 }
        return 1.0
    }

    nonisolated static func buildJourneyContenders(
        presentation: GolfTournamentPresentation,
        atlasData: TournamentAtlasData,
        selectedGolferName: String?,
        now: Date = Date()
    ) -> [JourneyContender] {
        let phase = resolvePhase(
            scheduleStatus: presentation.scheduleStatus,
            commenceTime: presentation.commenceTime,
            winnerMarket: atlasData.winnerMarket,
            field: presentation.field,
            now: now
        )
        let resolved = isMarketResolved(atlasData.winnerMarket) || phase == .final
        let winFailed = atlasData.failedMarketSlots.contains("win")

        var chosenNames: [String] = Array(presentation.field.prefix(5).map(\.name))
        if let selected = selectedGolferName,
           !chosenNames.contains(where: { normalizeGolferName($0) == normalizeGolferName(selected) }),
           presentation.field.contains(where: { normalizeGolferName($0.name) == normalizeGolferName(selected) })
        {
            chosenNames.append(selected)
        }

        let entries = atlasData.winnerTimeline?.timeline ?? []
        let parsedEntries: [(Date, [String: Double])] = entries.compactMap { entry in
            guard let d = entry.timestamp.asDate else { return nil }
            return (d, entry.outcomes)
        }.sorted { $0.0 < $1.0 }

        return chosenNames.enumerated().map { idx, name in
            let norm = normalizeGolferName(name)
            let fieldRow = presentation.field.first { normalizeGolferName($0.name) == norm }
            let outcome = findOutcome(for: name, in: atlasData.winnerMarket)
            let meta = atlasData.winnerTimeline?.outcomes.first { normalizeGolferName($0.name) == norm }

            let pts: [JourneyPoint] = parsedEntries.compactMap { date, map in
                if let exact = map[name], exact.isFinite, exact >= 0, exact <= 1 {
                    return JourneyPoint(golferName: name, date: date, probability: exact)
                }
                if let matched = map.first(where: { normalizeGolferName($0.key) == norm })?.value,
                   matched.isFinite, matched >= 0, matched <= 1
                {
                    return JourneyPoint(golferName: name, date: date, probability: matched)
                }
                return nil
            }

            let openProb: Double? = {
                guard phase != .before, !winFailed else { return nil }
                return validChance(outcome?.openingProbability ?? meta?.openingProbability ?? fieldRow?.openingProbability)
            }()

            let observedIso = outcome?.observedAt ?? outcome?.lastUpdated ?? meta?.observedAt ?? atlasData.winnerMarket?.updatedAt
            let recent = (atlasData.winnerMarket == nil && meta?.observedAt == nil)
                ? true
                : NFLMilestoneCard9483.isRecent(observedIso, now: now)

            let currentProb: Double? = {
                guard phase != .final, !winFailed else { return nil }
                guard recent else { return nil }
                return validChance(outcome?.probability ?? meta?.currentProbability ?? fieldRow?.probability)
            }()

            let verdict: OutcomeVerdict? = {
                guard phase == .final, !winFailed else { return nil }
                if let outcome {
                    return OutcomeVerdict.verdict(
                        isWinner: outcome.isWinner,
                        resolutionSource: outcome.resolutionSource,
                        marketResolved: resolved
                    )
                }
                if fieldRow?.isWinner == true {
                    return .won
                }
                return nil
            }()

            return JourneyContender(
                name: name,
                colorIndex: idx % palette.count,
                openingProbability: openProb,
                currentProbability: currentProb,
                finalVerdict: verdict,
                loadFailed: winFailed,
                points: pts
            )
        }
    }

    // MARK: - Chooser Filtering & Ordering

    nonisolated static func filterAndSortField(
        field: [GolfTournamentFieldRow],
        mode: ChooserMode,
        band: SurnameBand
    ) -> [GolfTournamentFieldRow] {
        switch mode {
        case .chances:
            return field
        case .movement:
            return field
                .filter { ($0.movement24h ?? 0).isFinite && abs($0.movement24h ?? 0) >= 0.001 }
                .sorted { abs($0.movement24h ?? 0) > abs($1.movement24h ?? 0) }
        case .all:
            return field
                .filter { band.contains(golferName: $0.name) }
                .sorted {
                    surnameSortKey($0.name).localizedCaseInsensitiveCompare(surnameSortKey($1.name)) == .orderedAscending
                }
        }
    }

    nonisolated static func formatMovementPoints(_ delta: Double?) -> String? {
        guard let delta, delta.isFinite, abs(delta) >= 0.001 else { return nil }
        let pts = delta * 100
        let sign = pts > 0 ? "+" : ""
        return String(format: "%@%.1f pts", sign, pts)
    }
}

// MARK: - Top-Level Golf Tournament Atlas View

struct EventAtlasGolfTournamentSection11666: View {
    let presentation: GolfTournamentPresentation
    let atlasData: EventAtlasGolfTournament11666.TournamentAtlasData
    var now: Date = Date()

    @State private var selectedGolferName: String? = nil
    @State private var selectedFinishKey: String? = nil
    @State private var fullScale: Bool = false
    @State private var chooserMode: EventAtlasGolfTournament11666.ChooserMode = .chances
    @State private var surnameBand: EventAtlasGolfTournament11666.SurnameBand = .all
    @State private var selectedRoundNumber: Int? = nil
    @State private var activeDetailsItem: EventAtlasGolfTournament11666.FinishDetailsSheetItem? = nil

    private var effectiveSelectedGolfer: String {
        if let selectedGolferName,
           presentation.field.contains(where: {
               EventAtlasGolfTournament11666.normalizeGolferName($0.name)
                   == EventAtlasGolfTournament11666.normalizeGolferName(selectedGolferName)
           })
        {
            return selectedGolferName
        }
        return presentation.field.first?.name ?? ""
    }

    private var contenders: [EventAtlasGolfTournament11666.JourneyContender] {
        EventAtlasGolfTournament11666.buildJourneyContenders(
            presentation: presentation,
            atlasData: atlasData,
            selectedGolferName: effectiveSelectedGolfer,
            now: now
        )
    }

    private var selectedGolferColor: Color {
        if let match = contenders.first(where: {
            EventAtlasGolfTournament11666.normalizeGolferName($0.name)
                == EventAtlasGolfTournament11666.normalizeGolferName(effectiveSelectedGolfer)
        }) {
            return EventAtlasGolfTournament11666.palette[match.colorIndex % EventAtlasGolfTournament11666.palette.count]
        }
        return EventAtlasGolfTournament11666.palette[0]
    }

    private var finishInput: GolfFinishExpectationInput10868 {
        EventAtlasGolfTournament11666.buildFinishExpectations(
            selectedGolferName: effectiveSelectedGolfer,
            presentation: presentation,
            atlasData: atlasData,
            selectedFinish: selectedFinishKey,
            color: selectedGolferColor,
            now: now
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            EventAtlasGolfJourneyCardView11666(
                contenders: contenders,
                phase: finishInput.phase,
                selectedGolferName: effectiveSelectedGolfer,
                timelineLoadFailed: atlasData.winnerTimelineFailed,
                fullScale: $fullScale,
                onSelectGolfer: { name in
                    selectedGolferName = name
                }
            )

            if !effectiveSelectedGolfer.isEmpty {
                VStack(alignment: .leading, spacing: 10) {
                    GolfFinishExpectationPresentation10868(
                        input: finishInput,
                        onSelectFinish: { selection in
                            if selectedFinishKey == selection {
                                selectedFinishKey = nil
                            } else {
                                selectedFinishKey = selection
                            }
                        },
                        onDetails: { selection in
                            activeDetailsItem = EventAtlasGolfTournament11666.buildFinishDetailsItem(
                                selection: selection,
                                golferName: effectiveSelectedGolfer,
                                finishInput: finishInput,
                                atlasData: atlasData
                            )
                        }
                    )
                }
                .padding(14)
                .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
                .accessibilityIdentifier("golf.atlas.finishExpectationsCard")
            }

            if let closingRound = atlasData.closingRound,
               finishInput.phase == .final,
               !closingRound.rows.isEmpty
            {
                EventAtlasGolfClosingRoundCardView11666(
                    card: closingRound,
                    selectedGolferName: effectiveSelectedGolfer,
                    onSelectGolfer: { name in
                        selectedGolferName = name
                    }
                )
            }

            if !presentation.roundTopGroups.isEmpty {
                EventAtlasGolfRoundsCardView11666(
                    groups: presentation.roundTopGroups,
                    selectedRound: $selectedRoundNumber,
                    selectedGolferName: effectiveSelectedGolfer,
                    onSelectGolfer: { name in
                        selectedGolferName = name
                    }
                )
            }

            EventAtlasGolfContenderChooserView11666(
                field: presentation.field,
                phase: finishInput.phase,
                selectedGolferName: effectiveSelectedGolfer,
                mode: $chooserMode,
                band: $surnameBand,
                onSelectGolfer: { name in
                    selectedGolferName = name
                }
            )
        }
        .sheet(item: $activeDetailsItem) { item in
            EventAtlasGolfFinishDetailsSheet11666(item: item)
        }
    }
}

// MARK: - 1. Tournament Win-Probability Journey Card

struct EventAtlasGolfJourneyCardView11666: View {
    let contenders: [EventAtlasGolfTournament11666.JourneyContender]
    let phase: GolfFinishPhase10868
    let selectedGolferName: String
    var timelineLoadFailed: Bool = false
    @Binding var fullScale: Bool
    let onSelectGolfer: (String) -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var ceiling: Double {
        EventAtlasGolfTournament11666.yAxisCeiling(contenders: contenders, fullScale: fullScale)
    }

    private var hasSeriesPoints: Bool {
        contenders.contains { $0.points.count >= 2 }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Chance to win")
                            .font(.headline)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(phase == .final ? "Tournament win-probability journey · Final" : "Tournament win-probability journey")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    HStack(spacing: 6) {
                        scaleButton(title: "Auto", isFull: false)
                        scaleButton(title: "Full", isFull: true)
                    }
                    .accessibilityIdentifier("golf.atlas.scaleToggle")
                }
            } else {
                HStack(alignment: .firstTextBaseline, spacing: 8) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Chance to win")
                            .font(.headline)
                            .fixedSize(horizontal: false, vertical: true)
                        Text(phase == .final ? "Tournament win-probability journey · Final" : "Tournament win-probability journey")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 4)
                    HStack(spacing: 4) {
                        scaleButton(title: "Auto", isFull: false)
                        scaleButton(title: "Full", isFull: true)
                    }
                    .accessibilityIdentifier("golf.atlas.scaleToggle")
                }
            }

            if hasSeriesPoints {
                Chart {
                    ForEach(contenders) { contender in
                        let isSelected = EventAtlasGolfTournament11666.normalizeGolferName(contender.name)
                            == EventAtlasGolfTournament11666.normalizeGolferName(selectedGolferName)
                        let color = EventAtlasGolfTournament11666.palette[contender.colorIndex % EventAtlasGolfTournament11666.palette.count]
                        ForEach(contender.points) { pt in
                            LineMark(
                                x: .value("Time", pt.date),
                                y: .value("Win chance", min(pt.probability, ceiling)),
                                series: .value("Golfer", contender.name)
                            )
                            .foregroundStyle(color.opacity(isSelected ? 1.0 : 0.45))
                            .lineStyle(StrokeStyle(lineWidth: isSelected ? 2.5 : 1.5))
                        }
                    }
                }
                .chartYScale(domain: 0...ceiling)
                .chartXAxis {
                    AxisMarks(values: .automatic(desiredCount: dynamicTypeSize.isAccessibilitySize ? 2 : 4)) { _ in
                        AxisGridLine()
                        AxisValueLabel(format: .dateTime.month(.abbreviated).day())
                            .font(.caption2)
                    }
                }
                .chartYAxis {
                    AxisMarks(values: [0.0, ceiling / 2.0, ceiling]) { val in
                        AxisGridLine()
                        AxisValueLabel {
                            if let d = val.as(Double.self) {
                                Text("\(Int((d * 100).rounded()))%")
                                    .font(.caption2)
                                    .monospacedDigit()
                            }
                        }
                    }
                }
                .frame(height: 180)
                .accessibilityIdentifier("golf.atlas.journeyChart")
            } else {
                Text(
                    timelineLoadFailed
                        ? "Couldn’t load win-probability history."
                        : "Win-probability history isn’t available for this tournament yet."
                )
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.vertical, 8)
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(contenders) { contender in
                    contenderChip(contender)
                }
            }
        }
        .padding(14)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        .accessibilityIdentifier("golf.atlas.journeyCard")
    }

    private func scaleButton(title: String, isFull: Bool) -> some View {
        let active = fullScale == isFull
        return Button {
            fullScale = isFull
        } label: {
            Text(title)
                .font(.caption.weight(active ? .semibold : .regular))
                .foregroundStyle(active ? Color.primary : Color.secondary)
                .fixedSize(horizontal: true, vertical: false)
                .padding(.horizontal, 10)
                .padding(.vertical, 6)
                .frame(minHeight: 36)
                .background(
                    active ? Color.tertiaryFill : Color.clear,
                    in: Capsule()
                )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func contenderChip(_ contender: EventAtlasGolfTournament11666.JourneyContender) -> some View {
        let isSelected = EventAtlasGolfTournament11666.normalizeGolferName(contender.name)
            == EventAtlasGolfTournament11666.normalizeGolferName(selectedGolferName)
        let color = EventAtlasGolfTournament11666.palette[contender.colorIndex % EventAtlasGolfTournament11666.palette.count]

        Button {
            onSelectGolfer(contender.name)
        } label: {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        HStack(spacing: 8) {
                            Circle()
                                .fill(color)
                                .frame(width: 10, height: 10)
                            Text(contender.name)
                                .font(.subheadline.weight(isSelected ? .bold : .medium))
                                .foregroundStyle(.primary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        contenderTrailingValue(contender)
                    }
                } else {
                    HStack(spacing: 8) {
                        Circle()
                            .fill(color)
                            .frame(width: 10, height: 10)
                        Text(contender.name)
                            .font(.subheadline.weight(isSelected ? .bold : .medium))
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 6)
                        contenderTrailingValue(contender)
                    }
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(
                isSelected ? color.opacity(0.12) : Color.groupedBackground,
                in: RoundedRectangle(cornerRadius: 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(isSelected ? color : Color.clear, lineWidth: 1.5)
            )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func contenderTrailingValue(_ contender: EventAtlasGolfTournament11666.JourneyContender) -> some View {
        HStack(spacing: 8) {
            if contender.loadFailed {
                Text("Couldn’t load market")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                if let open = contender.openingProbability {
                    Text("○ Opened \(formatProbability(open))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                        .fixedSize(horizontal: false, vertical: true)
                }
                if phase == .final {
                    switch contender.finalVerdict {
                    case .won:
                        Text("✓ Won")
                            .font(.subheadline.weight(.semibold))
                            .foregroundStyle(DS.emeraldDark)
                            .fixedSize(horizontal: false, vertical: true)
                    case .lost:
                        Text("✗ Lost")
                            .font(.caption.weight(.medium))
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    case nil:
                        Text("Result not confirmed")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                } else if let current = contender.currentProbability {
                    Text(formatProbability(current))
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(.primary)
                        .monospacedDigit()
                } else {
                    Text("No recent probability")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
    }
}

// MARK: - 2. Closing-Round Strokes-Against-Par Card (Item 14b)

struct EventAtlasGolfClosingRoundCardView11666: View {
    let card: EventAtlasGolfTournament11666.ClosingRoundCard
    let selectedGolferName: String
    let onSelectGolfer: (String) -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var selectedRow: EventAtlasGolfTournament11666.ClosingRoundRow? {
        card.selectedRow(named: selectedGolferName)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Closing round · strokes against par")
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Final field distribution (\(card.rows.count) golfers) on one signed strokes-against-par axis")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let selectedRow {
                selectedComparison(selectedRow)
            }

            strokesPlot
        }
        .padding(14)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        .accessibilityIdentifier("golf.atlas.closingRoundCard")
    }

    @ViewBuilder
    private func selectedComparison(_ row: EventAtlasGolfTournament11666.ClosingRoundRow) -> some View {
        let preText = row.preTournamentWinChance.map { formatProbability($0) } ?? "Not recorded"
        let scoreText = EventAtlasGolfTournament11666.ClosingRoundCard.formatStrokes(row.strokesToPar)
        let finishText = row.finishLabel ?? "Result not confirmed"

        Group {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) {
                    Text(row.golferName)
                        .font(.subheadline.weight(.bold))
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Opening win chance: \(preText)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Reported finish: \(finishText) · \(scoreText)")
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                HStack(alignment: .top, spacing: 16) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(row.golferName)
                            .font(.subheadline.weight(.bold))
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Reported finish: \(finishText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    Spacer(minLength: 4)
                    VStack(alignment: .trailing, spacing: 2) {
                        Text(scoreText)
                            .font(.title3.weight(.bold))
                            .monospacedDigit()
                        Text("○ Opened \(preText)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                            .monospacedDigit()
                    }
                }
            }
        }
        .padding(10)
        .background(Color.groupedBackground, in: RoundedRectangle(cornerRadius: 10))
    }

    private var strokesPlot: some View {
        let minS = min(card.minStrokes, -5)
        let maxS = max(card.maxStrokes, 2)
        let span = Double(max(1, maxS - minS))

        return VStack(alignment: .leading, spacing: 6) {
            GeometryReader { geo in
                let width = max(1, geo.size.width)
                let zeroX = width * CGFloat(Double(0 - minS) / span)
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.barTrack.opacity(0.35))
                        .frame(height: 2)
                        .offset(y: 22)

                    if minS <= 0 && maxS >= 0 {
                        Rectangle()
                            .fill(Color.secondary.opacity(0.45))
                            .frame(width: 1, height: 32)
                            .offset(x: zeroX, y: 6)
                    }

                    ForEach(card.rows) { row in
                        let isSelected = EventAtlasGolfTournament11666.normalizeGolferName(row.golferName)
                            == EventAtlasGolfTournament11666.normalizeGolferName(selectedGolferName)
                        let frac = CGFloat(Double(row.strokesToPar - minS) / span)
                        let xPos = min(max(6, width * frac), width - 6)
                        Circle()
                            .fill(isSelected ? EventAtlasGolfTournament11666.palette[0] : Color.secondary.opacity(0.45))
                            .frame(width: isSelected ? 12 : 7, height: isSelected ? 12 : 7)
                            .overlay(
                                Circle()
                                    .strokeBorder(Color.white, lineWidth: isSelected ? 2 : 0)
                            )
                            .position(x: xPos, y: 22)
                            .onTapGesture {
                                onSelectGolfer(row.golferName)
                            }
                    }
                }
            }
            .frame(height: 44)

            HStack {
                Text(EventAtlasGolfTournament11666.ClosingRoundCard.formatStrokes(minS))
                Spacer()
                if minS < 0 && maxS > 0 {
                    Text("E (Par)")
                    Spacer()
                }
                Text(EventAtlasGolfTournament11666.ClosingRoundCard.formatStrokes(maxS))
            }
            .font(.caption2)
            .foregroundStyle(.secondary)
            .monospacedDigit()
        }
    }
}

// MARK: - 3. Round Leaders & Top Finishers Card (Item 14b)

struct EventAtlasGolfRoundsCardView11666: View {
    let groups: [GolfRoundTopGroup]
    @Binding var selectedRound: Int?
    let selectedGolferName: String
    let onSelectGolfer: (String) -> Void

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var availableRounds: [Int] {
        Array(Set(groups.compactMap(\.round))).sorted()
    }

    private var activeRound: Int? {
        if let selectedRound, availableRounds.contains(selectedRound) {
            return selectedRound
        }
        return availableRounds.first
    }

    private var filteredGroups: [GolfRoundTopGroup] {
        guard let activeRound else { return groups }
        return groups.filter { $0.round == activeRound }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Round leaders & top finishers")
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Round-scoped markets settle per round and never carry into later rounds")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if availableRounds.count > 1 {
                FlowLayout(spacing: 8) {
                    ForEach(availableRounds, id: \.self) { rnd in
                        let active = activeRound == rnd
                        Button {
                            selectedRound = rnd
                        } label: {
                            Text("Round \(rnd)")
                                .font(.caption.weight(active ? .semibold : .regular))
                                .foregroundStyle(active ? Color.primary : Color.secondary)
                                .padding(.horizontal, 12)
                                .padding(.vertical, 6)
                                .frame(minHeight: 36)
                                .background(
                                    active ? Color.tertiaryFill : Color.groupedBackground,
                                    in: Capsule()
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
            }

            ForEach(filteredGroups) { group in
                roundGroupSection(group)
            }
        }
        .padding(14)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        .accessibilityIdentifier("golf.atlas.roundsCard")
    }

    @ViewBuilder
    private func roundGroupSection(_ group: GolfRoundTopGroup) -> some View {
        let isSettled = group.settled == true
        VStack(alignment: .leading, spacing: 8) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 4) {
                    Text(group.round.map { "Round \($0) · \(group.label)" } ?? group.label)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    if isSettled {
                        if let winner = group.gradedWinner, !winner.isEmpty {
                            Text("✓ Won · \(winner)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DS.emeraldDark)
                                .fixedSize(horizontal: false, vertical: true)
                        } else {
                            Text("Round complete · result not confirmed")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            } else {
                HStack(alignment: .firstTextBaseline) {
                    Text(group.round.map { "Round \($0) · \(group.label)" } ?? group.label)
                        .font(.subheadline.weight(.semibold))
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 4)
                    if isSettled {
                        if let winner = group.gradedWinner, !winner.isEmpty {
                            Text("✓ Won · \(winner)")
                                .font(.caption.weight(.semibold))
                                .foregroundStyle(DS.emeraldDark)
                                .fixedSize(horizontal: false, vertical: true)
                        } else {
                            Text("Round complete · result not confirmed")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                }
            }

            ForEach(Array(group.outcomes.prefix(5))) { outcome in
                let isWinner = isSettled && group.gradedWinner.map {
                    EventAtlasGolfTournament11666.normalizeGolferName($0)
                        == EventAtlasGolfTournament11666.normalizeGolferName(outcome.name)
                } == true

                Button {
                    onSelectGolfer(outcome.name)
                } label: {
                    Group {
                        if dynamicTypeSize.isAccessibilitySize {
                            VStack(alignment: .leading, spacing: 4) {
                                Text(outcome.name)
                                    .font(.subheadline.weight(isWinner ? .bold : .regular))
                                    .foregroundStyle(.primary)
                                    .fixedSize(horizontal: false, vertical: true)
                                HStack(spacing: 8) {
                                    if let open = outcome.openingProbability, open > 0, open < 1 {
                                        Text("○ Opened \(formatProbability(open))")
                                            .font(.caption)
                                            .foregroundStyle(.secondary)
                                            .monospacedDigit()
                                    }
                                    if isSettled {
                                        Text(isWinner ? "✓ Won" : (group.gradedWinner != nil ? "—" : "Unconfirmed"))
                                            .font(.caption.weight(isWinner ? .semibold : .regular))
                                            .foregroundStyle(isWinner ? DS.emeraldDark : .secondary)
                                    } else {
                                        Text(formatProbability(outcome.probability))
                                            .font(.subheadline.weight(.semibold))
                                            .foregroundStyle(.primary)
                                            .monospacedDigit()
                                    }
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        } else {
                            HStack(spacing: 8) {
                                Text(outcome.name)
                                    .font(.subheadline.weight(isWinner ? .bold : .regular))
                                    .foregroundStyle(.primary)
                                    .fixedSize(horizontal: false, vertical: true)
                                Spacer(minLength: 4)
                                if let open = outcome.openingProbability, open > 0, open < 1 {
                                    Text("○ Opened \(formatProbability(open))")
                                        .font(.caption)
                                        .foregroundStyle(.secondary)
                                        .monospacedDigit()
                                }
                                if isSettled {
                                    Text(isWinner ? "✓ Won" : (group.gradedWinner != nil ? "—" : "Unconfirmed"))
                                        .font(.caption.weight(isWinner ? .semibold : .regular))
                                        .foregroundStyle(isWinner ? DS.emeraldDark : .secondary)
                                } else {
                                    Text(formatProbability(outcome.probability))
                                        .font(.subheadline.weight(.semibold))
                                        .foregroundStyle(.primary)
                                        .monospacedDigit()
                                }
                            }
                        }
                    }
                    .padding(.vertical, 4)
                    .frame(minHeight: 36)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(10)
        .background(Color.groupedBackground, in: RoundedRectangle(cornerRadius: 10))
    }
}

// MARK: - 4. Contender Chooser Card (Item 14b)

struct EventAtlasGolfContenderChooserView11666: View {
    let field: [GolfTournamentFieldRow]
    let phase: GolfFinishPhase10868
    let selectedGolferName: String
    @Binding var mode: EventAtlasGolfTournament11666.ChooserMode
    @Binding var band: EventAtlasGolfTournament11666.SurnameBand
    let onSelectGolfer: (String) -> Void

    @State private var pageIndex: Int = 0
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private let pageSize = 15

    private var rows: [GolfTournamentFieldRow] {
        EventAtlasGolfTournament11666.filterAndSortField(field: field, mode: mode, band: band)
    }

    private var pageCount: Int {
        max(1, Int(ceil(Double(rows.count) / Double(pageSize))))
    }

    private var clampedPage: Int {
        min(max(0, pageIndex), pageCount - 1)
    }

    private var pagedRows: [GolfTournamentFieldRow] {
        guard !rows.isEmpty else { return [] }
        let start = clampedPage * pageSize
        let end = min(rows.count, start + pageSize)
        return Array(rows[start..<end])
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Choose golfer")
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                Text("Tap any golfer in the field (\(field.count)) to inspect their finish expectations")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }

            FlowLayout(spacing: 6) {
                ForEach(EventAtlasGolfTournament11666.ChooserMode.allCases, id: \.self) { m in
                    let active = mode == m
                    Button {
                        mode = m
                        pageIndex = 0
                    } label: {
                        Text(m.rawValue)
                            .font(.caption.weight(active ? .semibold : .regular))
                            .foregroundStyle(active ? Color.primary : Color.secondary)
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .frame(minHeight: 36)
                            .background(
                                active ? Color.tertiaryFill : Color.groupedBackground,
                                in: Capsule()
                            )
                    }
                    .buttonStyle(.plain)
                }
            }
            .accessibilityIdentifier("golf.atlas.chooserModes")

            if mode == .all && field.count > 12 {
                FlowLayout(spacing: 6) {
                    ForEach(EventAtlasGolfTournament11666.SurnameBand.allCases, id: \.self) { b in
                        let active = band == b
                        Button {
                            band = b
                            pageIndex = 0
                        } label: {
                            Text(b.rawValue)
                                .font(.caption2.weight(active ? .semibold : .regular))
                                .foregroundStyle(active ? Color.primary : Color.secondary)
                                .padding(.horizontal, 10)
                                .padding(.vertical, 5)
                                .frame(minHeight: 32)
                                .background(
                                    active ? Color.tertiaryFill : Color.groupedBackground,
                                    in: Capsule()
                                )
                        }
                        .buttonStyle(.plain)
                    }
                }
                .accessibilityIdentifier("golf.atlas.surnameBands")
            }

            if pagedRows.isEmpty {
                Text(mode == .movement ? "No 24-hour movement recorded for this field." : "No golfers in this surname band.")
                    .font(.footnote)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.vertical, 6)
            } else {
                VStack(spacing: 6) {
                    ForEach(pagedRows) { row in
                        chooserRow(row)
                    }
                }
            }

            if pageCount > 1 {
                HStack {
                    Button {
                        pageIndex = max(0, clampedPage - 1)
                    } label: {
                        Text("Previous")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(clampedPage > 0 ? .blue : .secondary)
                            .frame(minHeight: 36)
                    }
                    .disabled(clampedPage == 0)
                    .buttonStyle(.plain)

                    Spacer()
                    Text("Page \(clampedPage + 1) of \(pageCount)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                    Spacer()

                    Button {
                        pageIndex = min(pageCount - 1, clampedPage + 1)
                    } label: {
                        Text("Next")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(clampedPage < pageCount - 1 ? .blue : .secondary)
                            .frame(minHeight: 36)
                    }
                    .disabled(clampedPage >= pageCount - 1)
                    .buttonStyle(.plain)
                }
            }
        }
        .padding(14)
        .background(Color.cardBackground, in: RoundedRectangle(cornerRadius: 14))
        .accessibilityIdentifier("golf.atlas.chooserCard")
    }

    @ViewBuilder
    private func chooserRow(_ row: GolfTournamentFieldRow) -> some View {
        let isSelected = EventAtlasGolfTournament11666.normalizeGolferName(row.name)
            == EventAtlasGolfTournament11666.normalizeGolferName(selectedGolferName)

        Button {
            onSelectGolfer(row.name)
        } label: {
            Group {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 4) {
                        Text("\(row.position). \(row.name)")
                            .font(.subheadline.weight(isSelected ? .bold : .medium))
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                        chooserRowTrailing(row)
                    }
                } else {
                    HStack(spacing: 8) {
                        Text("\(row.position)")
                            .font(.caption2.weight(.bold))
                            .frame(width: 24, alignment: .trailing)
                            .foregroundStyle(row.position == 1 ? .orange : .secondary)
                            .monospacedDigit()
                        Text(row.name)
                            .font(.subheadline.weight(isSelected ? .bold : .medium))
                            .foregroundStyle(.primary)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 6)
                        chooserRowTrailing(row)
                    }
                }
            }
            .padding(.horizontal, 10)
            .padding(.vertical, 8)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
            .background(
                isSelected ? EventAtlasGolfTournament11666.palette[0].opacity(0.12) : Color.groupedBackground,
                in: RoundedRectangle(cornerRadius: 10)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(isSelected ? EventAtlasGolfTournament11666.palette[0] : Color.clear, lineWidth: 1.5)
            )
        }
        .buttonStyle(.plain)
    }

    @ViewBuilder
    private func chooserRowTrailing(_ row: GolfTournamentFieldRow) -> some View {
        HStack(spacing: 8) {
            if let moveText = EventAtlasGolfTournament11666.formatMovementPoints(row.movement24h) {
                Text(moveText)
                    .font(.caption.weight(.medium))
                    .foregroundStyle((row.movement24h ?? 0) > 0 ? DS.emeraldDark : .red)
                    .monospacedDigit()
            }
            if phase == .final {
                if row.isWinner == true {
                    Text("✓ Won")
                        .font(.subheadline.weight(.semibold))
                        .foregroundStyle(DS.emeraldDark)
                } else if let open = row.openingProbability, open > 0, open < 1 {
                    Text("○ Opened \(formatProbability(open))")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .monospacedDigit()
                } else {
                    Text("—")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(row.probabilityLabel)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(row.position == 1 ? .blue : .primary)
                    .monospacedDigit()
            }
        }
    }
}

// MARK: - 5. Finish Market Details Sheet

struct EventAtlasGolfFinishDetailsSheet11666: View {
    let item: EventAtlasGolfTournament11666.FinishDetailsSheetItem
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            List {
                Section {
                    VStack(alignment: .leading, spacing: 4) {
                        Text(item.golferName)
                            .font(.headline)
                        Text("\(item.finishTitle) · \(item.marketName)")
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }
                    .padding(.vertical, 4)
                }

                Section("Readings") {
                    LabeledContent(
                        item.phase == .before ? "Before tournament" : "Opened",
                        value: item.beforePercent ?? item.beforeMissingText
                    )
                    if item.phase == .recorded {
                        LabeledContent("Recorded estimate", value: item.recordedPercent ?? item.recordedMissingText)
                        if let deltaText = item.deltaText {
                            LabeledContent("Since open", value: deltaText)
                        }
                    }
                    if let resultText = item.resultText {
                        LabeledContent("Confirmed result", value: resultText)
                    }
                }

                Section("Recorded time & source") {
                    LabeledContent("Observed", value: item.observedTimestampPT ?? "Timestamp unavailable")
                    LabeledContent("Source", value: item.sourceAttribution ?? "Source unavailable")
                }
            }
            .navigationTitle("\(item.finishTitle) details")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .presentationDetents([.medium, .large])
    }
}
