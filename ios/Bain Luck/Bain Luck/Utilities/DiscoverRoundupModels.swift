import Foundation

// MARK: - Discover Round-Up Contract & Presentation Model (Item 3 / #10357 / #12288)
//
// Decodes `data.roundup` emitted by `compose_roundup_feed_item` and all 11 candidate
// producers under `backend/data/discover/candidates/` (`tech_ai_race`,
// `cross_domain_yardsticks`, `big_movers_today`, `ceremony_award_categories`,
// `headliners_and_hosts`, `long_shot_movers`, `league_award_ladders`,
// `league_division_races`, `opening_weekend_slate`, `team_active_streaks`,
// `window_events_upsets`), plus dual-bar ceremony rows and 3-up schedule strips.

nonisolated struct FeedRoundupRow: Decodable, Equatable, Sendable {
    let marketId: Int?
    let eventId: Int?
    let outcomeId: Int?
    let genericId: Int?
    let memberType: String?
    let label: String
    let opponentLabel: String?
    let dateLabel: String?
    let probability: Double
    let renderedPercent: Int?
    let runnerUpLabel: String?
    let deltaLabel: String?
    let swingLabel: String?
    let periodLabel: String?
    let secondaryProbability: Double?
    let secondaryRenderedPercent: Int?
    let primaryBarLabel: String?
    let secondaryBarLabel: String?
    let observedAt: String?

    private enum CodingKeys: String, CodingKey {
        case marketId
        case marketIdSnake = "market_id"
        case eventId
        case eventIdSnake = "event_id"
        case outcomeId
        case outcomeIdSnake = "outcome_id"
        case id
        case memberType
        case memberTypeSnake = "member_type"
        case label
        case opponentLabel
        case opponentLabelSnake = "opponent_label"
        case dateLabel
        case dateLabelSnake = "date_label"
        case probability
        case renderedPercent
        case renderedPercentSnake = "rendered_percent"
        case runnerUpLabel
        case runnerUpLabelSnake = "runner_up_label"
        case deltaLabel
        case deltaLabelSnake = "delta_label"
        case swingLabel
        case swingLabelSnake = "swing_label"
        case periodLabel
        case periodLabelSnake = "period_label"
        case secondaryProbability
        case secondaryProbabilitySnake = "secondary_probability"
        case secondaryRenderedPercent
        case secondaryRenderedPercentSnake = "secondary_rendered_percent"
        case primaryBarLabel
        case primaryBarLabelSnake = "primary_bar_label"
        case secondaryBarLabel
        case secondaryBarLabelSnake = "secondary_bar_label"
        case observedAt
        case observedAtSnake = "observed_at"
    }

    init(
        marketId: Int? = nil,
        eventId: Int? = nil,
        outcomeId: Int? = nil,
        genericId: Int? = nil,
        memberType: String? = nil,
        label: String,
        opponentLabel: String? = nil,
        dateLabel: String? = nil,
        probability: Double,
        renderedPercent: Int? = nil,
        runnerUpLabel: String? = nil,
        deltaLabel: String? = nil,
        swingLabel: String? = nil,
        periodLabel: String? = nil,
        secondaryProbability: Double? = nil,
        secondaryRenderedPercent: Int? = nil,
        primaryBarLabel: String? = nil,
        secondaryBarLabel: String? = nil,
        observedAt: String? = nil
    ) {
        self.marketId = marketId
        self.eventId = eventId
        self.outcomeId = outcomeId
        self.genericId = genericId
        self.memberType = memberType
        self.label = label
        self.opponentLabel = opponentLabel
        self.dateLabel = dateLabel
        self.probability = probability
        self.renderedPercent = renderedPercent
        self.runnerUpLabel = runnerUpLabel
        self.deltaLabel = deltaLabel
        self.swingLabel = swingLabel
        self.periodLabel = periodLabel
        self.secondaryProbability = secondaryProbability
        self.secondaryRenderedPercent = secondaryRenderedPercent
        self.primaryBarLabel = primaryBarLabel
        self.secondaryBarLabel = secondaryBarLabel
        self.observedAt = observedAt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        marketId = (try? c.decodeIfPresent(Int.self, forKey: .marketId))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .marketIdSnake))
        eventId = (try? c.decodeIfPresent(Int.self, forKey: .eventId))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .eventIdSnake))
        outcomeId = (try? c.decodeIfPresent(Int.self, forKey: .outcomeId))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .outcomeIdSnake))
        genericId = try? c.decodeIfPresent(Int.self, forKey: .id)
        memberType = (try? c.decodeIfPresent(String.self, forKey: .memberType))
            ?? (try? c.decodeIfPresent(String.self, forKey: .memberTypeSnake))
        label = (try? c.decodeIfPresent(String.self, forKey: .label)) ?? ""
        opponentLabel = (try? c.decodeIfPresent(String.self, forKey: .opponentLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .opponentLabelSnake))
        dateLabel = (try? c.decodeIfPresent(String.self, forKey: .dateLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .dateLabelSnake))
        probability = try c.decode(Double.self, forKey: .probability)
        renderedPercent = (try? c.decodeIfPresent(Int.self, forKey: .renderedPercent))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .renderedPercentSnake))
        runnerUpLabel = (try? c.decodeIfPresent(String.self, forKey: .runnerUpLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .runnerUpLabelSnake))
        deltaLabel = (try? c.decodeIfPresent(String.self, forKey: .deltaLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .deltaLabelSnake))
        swingLabel = (try? c.decodeIfPresent(String.self, forKey: .swingLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .swingLabelSnake))
        periodLabel = (try? c.decodeIfPresent(String.self, forKey: .periodLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .periodLabelSnake))
        secondaryProbability = (try? c.decodeIfPresent(Double.self, forKey: .secondaryProbability))
            ?? (try? c.decodeIfPresent(Double.self, forKey: .secondaryProbabilitySnake))
        secondaryRenderedPercent = (try? c.decodeIfPresent(Int.self, forKey: .secondaryRenderedPercent))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .secondaryRenderedPercentSnake))
        primaryBarLabel = (try? c.decodeIfPresent(String.self, forKey: .primaryBarLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .primaryBarLabelSnake))
        secondaryBarLabel = (try? c.decodeIfPresent(String.self, forKey: .secondaryBarLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .secondaryBarLabelSnake))
        observedAt = (try? c.decodeIfPresent(String.self, forKey: .observedAt))
            ?? (try? c.decodeIfPresent(String.self, forKey: .observedAtSnake))
    }
}

nonisolated struct FeedRoundupContract: Decodable, Equatable, Sendable {
    let kicker: String
    let tag: String?
    let subtitle: String?
    let completeGroup: Bool?
    let footer: String
    let countLine: String?
    let order: String?
    let presentation: String?
    let rows: [FeedRoundupRow]

    private enum CodingKeys: String, CodingKey {
        case kicker, tag, subtitle, footer, order, presentation, rows
        case contextLine
        case contextLineSnake = "context_line"
        case completeGroup
        case completeGroupSnake = "complete_group"
        case countLine
        case countLineSnake = "count_line"
    }

    init(
        kicker: String,
        tag: String? = nil,
        subtitle: String? = nil,
        completeGroup: Bool? = nil,
        footer: String,
        countLine: String? = nil,
        order: String? = nil,
        presentation: String? = nil,
        rows: [FeedRoundupRow]
    ) {
        self.kicker = kicker
        self.tag = tag
        self.subtitle = subtitle
        self.completeGroup = completeGroup
        self.footer = footer
        self.countLine = countLine
        self.order = order
        self.presentation = presentation
        self.rows = rows
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        kicker = (try? c.decodeIfPresent(String.self, forKey: .kicker)) ?? ""
        tag = try? c.decodeIfPresent(String.self, forKey: .tag)
        let directSubtitle = try? c.decodeIfPresent(String.self, forKey: .subtitle)
        let contextLine = (try? c.decodeIfPresent(String.self, forKey: .contextLine))
            ?? (try? c.decodeIfPresent(String.self, forKey: .contextLineSnake))
        subtitle = Self.nonEmpty(directSubtitle) ?? Self.nonEmpty(contextLine)
        completeGroup = (try? c.decodeIfPresent(Bool.self, forKey: .completeGroup))
            ?? (try? c.decodeIfPresent(Bool.self, forKey: .completeGroupSnake))
        footer = (try? c.decodeIfPresent(String.self, forKey: .footer)) ?? ""
        countLine = (try? c.decodeIfPresent(String.self, forKey: .countLine))
            ?? (try? c.decodeIfPresent(String.self, forKey: .countLineSnake))
        order = try? c.decodeIfPresent(String.self, forKey: .order)
        presentation = try? c.decodeIfPresent(String.self, forKey: .presentation)
        rows = (try? c.decodeIfPresent([FeedRoundupRow].self, forKey: .rows)) ?? []
    }

    private static func nonEmpty(_ text: String?) -> String? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }
}

nonisolated struct DiscoverRoundupSecondaryBarModel: Equatable, Sendable {
    let marker: String?
    let digits: String
    let fill: Double
    let primaryLabel: String
    let secondaryLabel: String

    var formattedPercentText: String {
        "\(marker ?? "")\(digits)%"
    }
}

nonisolated enum DiscoverRoundupMemberKind: String, Equatable, Sendable {
    case event
    case market
}

nonisolated enum DiscoverRoundupPresentation: String, Equatable, Sendable {
    case rows
    case strip
}

nonisolated struct DiscoverRoundupRowModel: Equatable, Identifiable, Sendable {
    let id: String
    let targetId: Int
    let kind: DiscoverRoundupMemberKind
    let cadence: SourceAge.Cadence
    let label: String
    let opponentLabel: String?
    let dateLabel: String?
    let detailCallout: String?
    let marker: String?
    let digits: String
    let fill: Double
    let secondary: DiscoverRoundupSecondaryBarModel?
    let observedAt: String?
    let showsRowAgeMark: Bool

    var formattedPercentText: String {
        "\(marker ?? "")\(digits)%"
    }

    var spokenPercentText: String {
        switch marker {
        case "<": return "under \(digits)%"
        case ">": return "over \(digits)%"
        default: return "\(digits)%"
        }
    }
}

nonisolated struct DiscoverRoundupCardModel: Equatable, Sendable {
    static let longHeadlineCharThreshold = 44

    let kicker: String
    let title: String
    let subtitle: String?
    let tag: String?
    let footer: String
    let countLine: String?
    let longHeadline: Bool
    let presentation: DiscoverRoundupPresentation
    let rows: [DiscoverRoundupRowModel]
    let cadence: SourceAge.Cadence
    let cardMarkObservedAt: String?

    var accessibilitySummary: String {
        let rowSpeech = rows
            .map { "\($0.label), \($0.spokenPercentText)" }
            .joined(separator: "; ")
        if let countLine {
            return "\(title). \(rowSpeech). \(countLine). \(footer)"
        }
        return "\(title). \(rowSpeech). \(footer)"
    }

    static func build(
        title: String?,
        contract: FeedRoundupContract?,
        now: Date = Date()
    ) -> DiscoverRoundupCardModel? {
        guard let contract else { return nil }
        let headline = trimmed(title)
        let kicker = trimmed(contract.kicker)
        let footer = trimmed(contract.footer)
        guard !headline.isEmpty, !kicker.isEmpty, !footer.isEmpty else { return nil }

        let upperKicker = kicker.uppercased()
        let isYardstickPair = upperKicker == "FOR SCALE"
        let isTwoRowPair = isYardstickPair || upperKicker.hasPrefix("HEAD TO HEAD")
        let isWeekEvents = upperKicker.hasSuffix("THIS WEEK") || upperKicker.hasSuffix("THIS WEEKEND")
        let isCompleteGroup = contract.completeGroup == true
        let isStrip = trimmed(contract.presentation).lowercased() == "strip"

        let minRows = (isTwoRowPair || isWeekEvents) ? 2 : 3
        let maxRows = isTwoRowPair ? 2 : isWeekEvents ? 4 : isCompleteGroup ? 8 : 5
        let served = contract.rows
        guard served.count >= minRows, served.count <= maxRows else { return nil }

        struct ValidatedRow {
            let row: FeedRoundupRow
            let rowIdentity: String
            let targetId: Int
            let kind: DiscoverRoundupMemberKind
            let cadence: SourceAge.Cadence
            let label: String
            let index: Int
        }

        var seenIds = Set<String>()
        var validated: [ValidatedRow] = []
        validated.reserveCapacity(served.count)

        for (index, row) in served.enumerated() {
            let cleanLabel = trimmed(row.label)
            guard !cleanLabel.isEmpty,
                  row.probability.isFinite,
                  row.probability >= 0.0,
                  row.probability <= 1.0 else {
                return nil
            }

            if let sec = row.secondaryProbability {
                guard sec.isFinite, sec >= 0.0, sec <= 1.0 else { return nil }
            }

            let resolvedTarget: (kind: DiscoverRoundupMemberKind, id: Int)? = {
                let hasMarket = row.marketId != nil
                let hasEvent = row.eventId != nil
                if hasMarket && hasEvent { return nil }
                if let mid = row.marketId, mid > 0 {
                    return (.market, mid)
                }
                if let eid = row.eventId, eid > 0 {
                    guard row.outcomeId == nil else { return nil }
                    return (.event, eid)
                }
                if let gid = row.genericId, gid > 0 {
                    let mType = trimmed(row.memberType).lowercased()
                    if mType == "event" {
                        return (.event, gid)
                    }
                    if mType == "futures" || mType == "market" {
                        return (.market, gid)
                    }
                }
                return nil
            }()

            guard let target = resolvedTarget else { return nil }
            if let oid = row.outcomeId, oid <= 0 { return nil }

            let identityKey: String
            if let oid = row.outcomeId {
                identityKey = "\(target.kind.rawValue):\(target.id):outcome:\(oid)"
            } else {
                identityKey = "\(target.kind.rawValue):\(target.id):\(cleanLabel.lowercased())"
            }
            guard !seenIds.contains(identityKey) else { return nil }
            seenIds.insert(identityKey)

            validated.append(
                ValidatedRow(
                    row: row,
                    rowIdentity: identityKey,
                    targetId: target.id,
                    kind: target.kind,
                    cadence: target.kind == .event ? .live : .futures,
                    label: cleanLabel,
                    index: index
                )
            )
        }

        // Explicit `order: "probability"` sorts highest-first; all dynamic candidate
        // producers (movers, closest-race awards/divisions, ceremony categories,
        // box office slates, yardsticks, sequences) preserve their canonical container order.
        if trimmed(contract.order).lowercased() == "probability" {
            validated.sort { lhs, rhs in
                if lhs.row.probability != rhs.row.probability {
                    return lhs.row.probability > rhs.row.probability
                }
                return lhs.index < rhs.index
            }
        }

        let stamps: [String?] = validated.map { nonEmpty($0.row.observedAt) }
        let staleFlags: [Bool] = zip(validated, stamps).map { item, stamp in
            SourceAge.isStale(stamp, now: now, after: item.cadence.staleAfter)
        }
        let allOld = !staleFlags.isEmpty && staleFlags.allSatisfy { $0 }
        let cardCadence: SourceAge.Cadence = validated.contains(where: { $0.cadence == .live }) ? .live : .futures

        let builtRows: [DiscoverRoundupRowModel] = zip(validated.indices, validated).map { idx, item in
            let parts = probabilityParts(probability: item.row.probability, renderedPercent: item.row.renderedPercent)
            let secondary: DiscoverRoundupSecondaryBarModel? = {
                guard let secProb = item.row.secondaryProbability else { return nil }
                let secParts = probabilityParts(probability: secProb, renderedPercent: item.row.secondaryRenderedPercent)
                return DiscoverRoundupSecondaryBarModel(
                    marker: secParts.marker,
                    digits: secParts.digits,
                    fill: min(1.0, max(0.0, secProb)),
                    primaryLabel: nonEmpty(item.row.primaryBarLabel) ?? "Wins",
                    secondaryLabel: nonEmpty(item.row.secondaryBarLabel) ?? "Nominated"
                )
            }()

            let splitPair: (String, String)? = {
                guard let range = item.label.range(of: " · ") else { return nil }
                let left = String(item.label[..<range.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
                let right = String(item.label[range.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
                return (!left.isEmpty && !right.isEmpty) ? (left, right) : nil
            }()

            return DiscoverRoundupRowModel(
                id: item.rowIdentity,
                targetId: item.targetId,
                kind: item.kind,
                cadence: item.cadence,
                label: item.label,
                opponentLabel: nonEmpty(item.row.opponentLabel) ?? splitPair?.0,
                dateLabel: nonEmpty(item.row.dateLabel) ?? splitPair?.1,
                detailCallout: buildDetailCallout(for: item.row),
                marker: parts.marker,
                digits: parts.digits,
                fill: min(1.0, max(0.0, item.row.probability)),
                secondary: secondary,
                observedAt: stamps[idx],
                showsRowAgeMark: !allOld && staleFlags[idx]
            )
        }

        return DiscoverRoundupCardModel(
            kicker: kicker,
            title: headline,
            subtitle: nonEmpty(contract.subtitle),
            tag: nonEmpty(contract.tag),
            footer: footer,
            countLine: nonEmpty(contract.countLine),
            longHeadline: headline.count > longHeadlineCharThreshold,
            presentation: isStrip ? .strip : .rows,
            rows: builtRows,
            cadence: cardCadence,
            cardMarkObservedAt: allOld ? SourceAge.oldestStamp(stamps) : nil
        )
    }

    static func probabilityParts(probability: Double, renderedPercent: Int?) -> (marker: String?, digits: String) {
        let clamped = min(1.0, max(0.0, probability))
        if clamped > 0.0 && clamped < 0.005 {
            return ("<", "1")
        }
        if clamped > 0.995 && clamped < 1.0 {
            return (">", "99")
        }
        let whole = renderedPercent ?? Int((clamped * 100.0).rounded())
        let bounded = min(100, max(0, whole))
        if bounded == 0 && clamped > 0.0 {
            return ("<", "1")
        }
        if bounded == 100 && clamped < 1.0 {
            return (">", "99")
        }
        return (nil, "\(bounded)")
    }

    private static func buildDetailCallout(for row: FeedRoundupRow) -> String? {
        if let period = nonEmpty(row.periodLabel), let swing = nonEmpty(row.swingLabel) {
            return "\(period) · \(swing)"
        }
        if let swing = nonEmpty(row.swingLabel) {
            return swing
        }
        if let delta = nonEmpty(row.deltaLabel) {
            return delta
        }
        if let runnerUp = nonEmpty(row.runnerUpLabel) {
            return "Runner-up · \(runnerUp)"
        }
        if let period = nonEmpty(row.periodLabel) {
            return period
        }
        return nil
    }

    private static func trimmed(_ value: String?) -> String {
        value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    }

    private static func nonEmpty(_ value: String?) -> String? {
        let t = trimmed(value)
        return t.isEmpty ? nil : t
    }
}
