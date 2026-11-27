import Foundation

/// Selected Discover A (#9642): seat related questions together without
/// hiding a lone fourth member or making every standalone market a group.
enum DiscoverGroupRows {
    static let showsEveryRowUpTo = 4
    static let collapsedSeatCount = 3

    static func showsEveryRow(itemCount: Int, expanded: Bool) -> Bool {
        expanded || itemCount <= showsEveryRowUpTo
    }

    static func visibleCount(itemCount: Int, expanded: Bool) -> Int {
        let count = max(0, itemCount)
        return showsEveryRow(itemCount: count, expanded: expanded) ? count : collapsedSeatCount
    }

    /// Even a short theme group can open full member cards. Short comparison
    /// groups already show all their rows and need no extra control.
    static func canExpand(itemCount: Int, kind: String?) -> Bool {
        itemCount > 0 && (kind != "comparison" || itemCount > showsEveryRowUpTo)
    }

    /// #10877: the footer names what the members are, as web's
    /// `bundleExpandLabel` does — all markets say markets, all games say games,
    /// and a mix gets no noun rather than a wrong one. `memberTypes` is each
    /// member's served `FeedItem.type`.
    static func footerTitle(memberTypes: [String], kind: String?, expanded: Bool) -> String? {
        let itemCount = memberTypes.count
        guard !expanded, canExpand(itemCount: itemCount, kind: kind) else { return nil }
        guard itemCount > showsEveryRowUpTo else { return "Expand" }
        if memberTypes.allSatisfy({ $0 == "futures" }) { return "All \(itemCount) markets" }
        if memberTypes.allSatisfy({ $0 == "event" }) { return "All \(itemCount) games" }
        return "See all \(itemCount)"
    }

    /// #9925: the collection row's words, as web's `CollectionEntryLink` reads
    /// them. The name is the collection's own, never the card's header.
    static func collectionTitle(for ref: FeedThemeCollectionRef) -> String {
        "View the \(ref.name) collection"
    }

    /// The page's full count, not the card's preview count.
    static func collectionCountLabel(for ref: FeedThemeCollectionRef) -> String {
        "\(ref.collectionCount) \(ref.collectionCount == 1 ? "market" : "markets")"
    }

    /// The existing hub route, keyed by the server's slug alone.
    static func collectionRoute(for ref: FeedThemeCollectionRef) -> Route {
        .containerHub(slug: ref.slug, name: ref.name)
    }

    /// Reuse the card's existing date/threshold rule, never the maximum price.
    static func markedRung(in points: [FeedDiscoverThresholdPoint]) -> FeedDiscoverThresholdPoint? {
        let priced = points.filter { $0.probability != nil }
            .sorted { ($0.value ?? 0) < ($1.value ?? 0) }
        return heatMapBetterThanEvenRung(priced)
    }

    private struct HeatmapLadderRow {
        let key: String
        let label: String
        let probability: Double?
        let movement: Double?
        let sortValue: Double
        let source: String?
        let dateIso: String?
    }

    private static let utcCalendar: Calendar = {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return cal
    }()

    static func utcDayString(_ date: Date) -> String {
        let comps = utcCalendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", comps.year ?? 0, comps.month ?? 1, comps.day ?? 1)
    }

    private static func isIsoDateString(_ raw: String?) -> Bool {
        guard let raw else { return false }
        let bytes = Array(raw.utf8)
        guard bytes.count == 10, bytes[4] == 45, bytes[7] == 45 else { return false }
        for (idx, b) in bytes.enumerated() where idx != 4 && idx != 7 {
            if b < 48 || b > 57 { return false }
        }
        return true
    }

    private static func startsWithBeforeWord(_ label: String) -> Bool {
        let trimmed = label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard trimmed.hasPrefix("before") else { return false }
        if trimmed.count == 6 { return true }
        let next = trimmed[trimmed.index(trimmed.startIndex, offsetBy: 6)]
        return !(next.isLetter || next.isNumber || next == "_")
    }

    private static func isDateLadder(_ points: [FeedDiscoverThresholdPoint]) -> Bool {
        !points.isEmpty && points.allSatisfy { $0.source == "date_bucket" }
    }

    static func resolveRungDateIso(
        point: FeedDiscoverThresholdPoint,
        distDateIso: String?,
        now: Date = Date()
    ) -> String? {
        if isIsoDateString(distDateIso) {
            return distDateIso
        }
        guard point.source == "date_bucket" || point.unit == "date" else { return nil }
        guard let rawValue = point.value,
              rawValue.isFinite,
              rawValue.rounded() == rawValue else { return nil }
        let v = Int(rawValue)
        let year = v / 10_000
        let month = (v / 100) % 100
        let day = v % 100
        if (2001...2999).contains(year) {
            if month == 0 {
                return startsWithBeforeWord(point.label) ? "\(year)-01-01" : "\(year)-12-31"
            }
            guard (1...12).contains(month) else { return nil }
            let resolvedDay: Int?
            if day == 0 {
                if let monthStart = utcCalendar.date(from: DateComponents(year: year, month: month, day: 1)),
                   let range = utcCalendar.range(of: .day, in: .month, for: monthStart) {
                    resolvedDay = range.count
                } else {
                    resolvedDay = nil
                }
            } else if (1...31).contains(day) {
                resolvedDay = day
            } else {
                resolvedDay = nil
            }
            guard let resolvedDay else { return nil }
            return String(format: "%04d-%02d-%02d", year, month, resolvedDay)
        }
        // Yearless `2000MMDD` sentinel used when date-bucket rungs carry month/day without a year.
        if year == 2000 && (1...12).contains(month) && (1...31).contains(day) {
            let nowYear = utcCalendar.component(.year, from: now)
            var bestYear = nowYear
            var bestDiff = TimeInterval.greatestFiniteMagnitude
            for y in [nowYear - 1, nowYear, nowYear + 1] {
                if let d = utcCalendar.date(from: DateComponents(year: y, month: month, day: day)) {
                    let diff = abs(d.timeIntervalSince(now))
                    if diff < bestDiff {
                        bestDiff = diff
                        bestYear = y
                    }
                }
            }
            return String(format: "%04d-%02d-%02d", bestYear, month, day)
        }
        return nil
    }

    static func distributionDatesByLabel(_ distributionOutcomes: [FeedDiscoverDistributionOutcome]?) -> [String: String] {
        var map: [String: String] = [:]
        for dist in distributionOutcomes ?? [] {
            let key = dist.label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if !key.isEmpty, map[key] == nil, isIsoDateString(dist.date) {
                map[key] = dist.date
            }
        }
        return map
    }

    static func resolveRungDateIso(
        point: FeedDiscoverThresholdPoint,
        distDatesByLabel: [String: String],
        now: Date = Date()
    ) -> String? {
        let key = point.label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let distDateIso = key.isEmpty ? nil : distDatesByLabel[key]
        return resolveRungDateIso(point: point, distDateIso: distDateIso, now: now)
    }

    private static func buildHeatmapRows(for data: FeedFuturesData, now: Date) -> [HeatmapLadderRow] {
        var outcomesByName: [String: FeedFuturesOutcome] = [:]
        for outcome in data.topOutcomes ?? [] {
            let key = outcome.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if outcomesByName[key] == nil {
                outcomesByName[key] = outcome
            }
        }
        let distDatesByLabel = distributionDatesByLabel(data.discoverCard?.distributionOutcomes)

        var orderedKeys: [String] = []
        var byLabel: [String: HeatmapLadderRow] = [:]
        for point in data.discoverCard?.thresholdPoints ?? [] {
            let label = point.label.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !label.isEmpty else { continue }
            let key = label.lowercased()
            let matchedOutcome = outcomesByName[key]
            let existing = byLabel[key]
            if existing == nil {
                orderedKeys.append(key)
            }
            let probability = point.probability ?? matchedOutcome?.probability
            let movement = matchedOutcome?.movement ?? point.movement
            let pointValue = point.value ?? 0
            let sortValue = existing.map { min($0.sortValue, pointValue) } ?? pointValue
            let dateIso = existing?.dateIso ?? resolveRungDateIso(point: point, distDatesByLabel: distDatesByLabel, now: now)

            byLabel[key] = HeatmapLadderRow(
                key: key,
                label: label,
                probability: existing?.probability ?? probability,
                movement: existing?.movement ?? movement,
                sortValue: sortValue,
                source: existing?.source ?? point.source,
                dateIso: dateIso
            )
        }

        // Preserve served array order across ties (Dictionary.values would scramble tie order
        // across launches). When rungs carry resolved calendar dates, compare chronologically
        // so yearless `2000MMDD` sentinels crossing New Year (Dec -> Jan) stay in order.
        return orderedKeys.compactMap { byLabel[$0] }.sorted { lhs, rhs in
            if let lDate = lhs.dateIso, let rDate = rhs.dateIso, lDate != rDate {
                return lDate < rDate
            }
            return lhs.sortValue < rhs.sortValue
        }
    }

    private static func dateLadderHeadlineRung(
        pricedDateRows: [HeatmapLadderRow],
        heroName: String?,
        now: Date
    ) -> HeatmapLadderRow? {
        let todayIso = utcDayString(now)
        let upcoming = pricedDateRows.filter { $0.dateIso == nil || $0.dateIso! >= todayIso }
        if upcoming.isEmpty {
            return pricedDateRows.first(where: { ($0.probability ?? 0) >= 0.5 })
        }
        if let firstAbove50 = upcoming.first(where: { ($0.probability ?? 0) >= 0.5 }) {
            return firstAbove50
        }
        let heroKey = (heroName ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let pastControlsHeadline = pricedDateRows.contains { row in
            guard let dateIso = row.dateIso, dateIso < todayIso else { return false }
            return (row.probability ?? 0) >= 0.5 || (!heroKey.isEmpty && row.key == heroKey)
        }
        if pastControlsHeadline {
            return upcoming.reduce<HeatmapLadderRow?>(nil) { best, row in
                guard let prob = row.probability else { return best }
                guard let bestProb = best?.probability else { return row }
                return prob > bestProb ? row : best
            }
        }
        return nil
    }

    struct CompactSummary: Equatable {
        let label: String?
        let probability: Double?
        let movement: Double?
        var sourceMark: SourceMark? = nil
        var renderedPercent: Int? = nil
    }

    enum FullCardStyle: Equatable { case heatmap, distribution, comparison, futures }

    /// The same existing-card eligibility as a standalone Discover member.
    static func fullCardStyle(for data: FeedFuturesData) -> FullCardStyle {
        if data.discoverCard?.suggestedFormat == "threshold_heatmap",
           (data.discoverCard?.thresholdPoints ?? []).filter({ $0.probability != nil }).count >= 2 { return .heatmap }
        if data.discoverCard?.suggestedFormat == "outcome_distribution",
           (data.discoverCard?.distributionOutcomes ?? []).filter({ $0.probability != nil }).count >= 4 { return .distribution }
        if data.discoverCard?.suggestedFormat == "cross_source_comparison"
            || (data.topOutcomes?.count ?? 0) >= 4 { return .comparison }
        return .futures
    }

    static func compactSummary(for data: FeedFuturesData, now: Date = Date()) -> CompactSummary {
        let points = (data.discoverCard?.thresholdPoints ?? []).filter { $0.probability != nil }
        if fullCardStyle(for: data) == .heatmap {
            if isDateLadder(points) {
                let pricedDateRows = buildHeatmapRows(for: data, now: now).filter { $0.probability != nil }
                if let rung = dateLadderHeadlineRung(
                    pricedDateRows: pricedDateRows,
                    heroName: data.topOutcomes?.first?.name,
                    now: now
                ) {
                    let matching = data.topOutcomes?.first {
                        $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() == rung.key
                    }
                    return CompactSummary(
                        label: rung.label,
                        probability: rung.probability,
                        movement: matching?.movement ?? rung.movement,
                        sourceMark: data.resolvedSourceMark(for: matching),
                        renderedPercent: matching?.renderedPercent
                    )
                }
            } else if let rung = markedRung(in: points) {
                let matching = data.topOutcomes?.first {
                    $0.name.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                        == rung.label.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
                }
                return CompactSummary(
                    label: rung.label,
                    probability: rung.probability,
                    movement: matching?.movement ?? rung.movement,
                    sourceMark: data.resolvedSourceMark(for: matching),
                    renderedPercent: matching?.renderedPercent
                )
            }
        }
        // Ordinary and all-below-even cards retain their served leader; missing
        // probability stays missing rather than turning into a fabricated zero.
        let leader = data.topOutcomes?.first
        return CompactSummary(
            label: leader?.name,
            probability: leader?.probability,
            movement: leader?.movement,
            sourceMark: data.resolvedSourceMark(for: leader),
            renderedPercent: leader?.renderedPercent
        )
    }
}
