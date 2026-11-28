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
    let unflooredPercent: Int?
    let runnerUpLabel: String?
    let deltaLabel: String?
    let swingLabel: String?
    let periodLabel: String?
    let secondaryProbability: Double?
    let secondaryRenderedPercent: Int?
    let secondaryUnflooredPercent: Int?
    let primaryBarLabel: String?
    let secondaryBarLabel: String?
    let observedAt: String?
    let sourceMark: SourceMark?
    let settledOut: Bool?

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
        case unflooredPercent
        case unflooredPercentSnake = "unfloored_percent"
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
        case secondaryUnflooredPercent
        case secondaryUnflooredPercentSnake = "secondary_unfloored_percent"
        case primaryBarLabel
        case primaryBarLabelSnake = "primary_bar_label"
        case secondaryBarLabel
        case secondaryBarLabelSnake = "secondary_bar_label"
        case observedAt
        case observedAtSnake = "observed_at"
        case sourceMark
        case sourceMarkSnake = "source_mark"
        case settledOut
        case settledOutSnake = "settled_out"
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
        unflooredPercent: Int? = nil,
        runnerUpLabel: String? = nil,
        deltaLabel: String? = nil,
        swingLabel: String? = nil,
        periodLabel: String? = nil,
        secondaryProbability: Double? = nil,
        secondaryRenderedPercent: Int? = nil,
        secondaryUnflooredPercent: Int? = nil,
        primaryBarLabel: String? = nil,
        secondaryBarLabel: String? = nil,
        observedAt: String? = nil,
        sourceMark: SourceMark? = nil,
        settledOut: Bool? = nil
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
        self.unflooredPercent = unflooredPercent
        self.runnerUpLabel = runnerUpLabel
        self.deltaLabel = deltaLabel
        self.swingLabel = swingLabel
        self.periodLabel = periodLabel
        self.secondaryProbability = secondaryProbability
        self.secondaryRenderedPercent = secondaryRenderedPercent
        self.secondaryUnflooredPercent = secondaryUnflooredPercent
        self.primaryBarLabel = primaryBarLabel
        self.secondaryBarLabel = secondaryBarLabel
        self.observedAt = observedAt
        self.sourceMark = sourceMark
        self.settledOut = settledOut
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
        unflooredPercent = (try? c.decodeIfPresent(Int.self, forKey: .unflooredPercent))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .unflooredPercentSnake))
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
        secondaryUnflooredPercent = (try? c.decodeIfPresent(Int.self, forKey: .secondaryUnflooredPercent))
            ?? (try? c.decodeIfPresent(Int.self, forKey: .secondaryUnflooredPercentSnake))
        primaryBarLabel = (try? c.decodeIfPresent(String.self, forKey: .primaryBarLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .primaryBarLabelSnake))
        secondaryBarLabel = (try? c.decodeIfPresent(String.self, forKey: .secondaryBarLabel))
            ?? (try? c.decodeIfPresent(String.self, forKey: .secondaryBarLabelSnake))
        observedAt = (try? c.decodeIfPresent(String.self, forKey: .observedAt))
            ?? (try? c.decodeIfPresent(String.self, forKey: .observedAtSnake))
        sourceMark = (try? c.decodeIfPresent(SourceMark.self, forKey: .sourceMark))
            ?? (try? c.decodeIfPresent(SourceMark.self, forKey: .sourceMarkSnake))
        settledOut = (try? c.decodeIfPresent(Bool.self, forKey: .settledOut))
            ?? (try? c.decodeIfPresent(Bool.self, forKey: .settledOutSnake))
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
    let unpricedOutcomes: [MachineryOutcomeVisual]
    let machineryCard: MachineryCardContract?
    let kitCard: KitCardEnvelope366B?
    let kitCardSpec: KitV1CardSpec?
    let hasUnknownLookFallback: Bool
    let pairedMetricSet: PairedMetricSet?

    private enum CodingKeys: String, CodingKey {
        case kicker, tag, subtitle, footer, order, presentation, rows
        case unpricedOutcomes
        case unpricedOutcomesSnake = "unpriced_outcomes"
        case contextLine
        case contextLineSnake = "context_line"
        case completeGroup
        case completeGroupSnake = "complete_group"
        case countLine
        case countLineSnake = "count_line"
        case machineryCard
        case machineryCardSnake = "machinery_card"
        case kitCard
        case kitCardSnake = "kit_card"
        case kitSpec
        case kitSpecSnake = "kit_spec"
        case pairedMetricSet
        case pairedMetricSetSnake = "paired_metric_set"
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
        rows: [FeedRoundupRow],
        machineryCard: MachineryCardContract? = nil,
        kitCard: KitCardEnvelope366B? = nil,
        kitCardSpec: KitV1CardSpec? = nil,
        hasUnknownLookFallback: Bool = false,
        pairedMetricSet: PairedMetricSet? = nil,
        unpricedOutcomes: [MachineryOutcomeVisual] = []
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
        self.unpricedOutcomes = unpricedOutcomes.map { $0.asUnpriced441A() }
        self.machineryCard = machineryCard
        self.kitCard = kitCard
        self.kitCardSpec = kitCardSpec
        self.hasUnknownLookFallback = hasUnknownLookFallback
        self.pairedMetricSet = pairedMetricSet
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
        let decodedUnpriced = (try? c.decodeIfPresent([MachineryOutcomeVisual].self, forKey: .unpricedOutcomes))
            ?? (try? c.decodeIfPresent([MachineryOutcomeVisual].self, forKey: .unpricedOutcomesSnake))
            ?? []
        unpricedOutcomes = decodedUnpriced.map { $0.asUnpriced441A() }
        let hasMachineryPayload = (c.contains(.machineryCard) && ((try? c.decodeNil(forKey: .machineryCard)) == false))
            || (c.contains(.machineryCardSnake) && ((try? c.decodeNil(forKey: .machineryCardSnake)) == false))
        let hasKitPayload = (c.contains(.kitCard) && ((try? c.decodeNil(forKey: .kitCard)) == false))
            || (c.contains(.kitCardSnake) && ((try? c.decodeNil(forKey: .kitCardSnake)) == false))
            || (c.contains(.kitSpec) && ((try? c.decodeNil(forKey: .kitSpec)) == false))
            || (c.contains(.kitSpecSnake) && ((try? c.decodeNil(forKey: .kitSpecSnake)) == false))
        machineryCard = (try? c.decodeIfPresent(MachineryCardContract.self, forKey: .machineryCard))
            ?? (try? c.decodeIfPresent(MachineryCardContract.self, forKey: .machineryCardSnake))
        kitCard = (try? c.decodeIfPresent(KitCardEnvelope366B.self, forKey: .kitCard))
            ?? (try? c.decodeIfPresent(KitCardEnvelope366B.self, forKey: .kitCardSnake))
            ?? (try? c.decodeIfPresent(KitCardEnvelope366B.self, forKey: .kitSpec))
            ?? (try? c.decodeIfPresent(KitCardEnvelope366B.self, forKey: .kitSpecSnake))
        if KitCardStandInSwitch366B.isEnabled {
            kitCardSpec = (try? c.decodeIfPresent(KitV1CardSpec.self, forKey: .kitCard))
                ?? (try? c.decodeIfPresent(KitV1CardSpec.self, forKey: .kitCardSnake))
                ?? (try? c.decodeIfPresent(KitV1CardSpec.self, forKey: .kitSpec))
                ?? (try? c.decodeIfPresent(KitV1CardSpec.self, forKey: .kitSpecSnake))
        } else {
            kitCardSpec = nil
        }
        hasUnknownLookFallback = ((machineryCard == nil) && hasMachineryPayload) || ((kitCard == nil) && hasKitPayload)
        pairedMetricSet = (try? c.decodeIfPresent(PairedMetricSet.self, forKey: .pairedMetricSet))
            ?? (try? c.decodeIfPresent(PairedMetricSet.self, forKey: .pairedMetricSetSnake))
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
    let rawProbability: Double
    let marker: String?
    let digits: String
    let fill: Double
    let secondary: DiscoverRoundupSecondaryBarModel?
    let observedAt: String?
    let showsRowAgeMark: Bool
    let sourceMark: SourceMark?
    var renderedPercent: Int? = nil
    var divisionDisplay: MachineryOutcomeDisplay441A? = nil

    var formattedPercentText: String {
        if let divisionDisplay {
            return divisionDisplay.label
        }
        return "\(marker ?? "")\(digits)%"
    }

    var spokenPercentText: String {
        spokenProbabilityText(formattedPercentText)
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

    var hasAnySourceMark: Bool {
        rows.contains { $0.sourceMark?.draws == true }
    }

    var accessibilitySummary: String {
        let rowSpeech = rows
            .map { "\($0.label), \($0.spokenPercentText)" }
            .joined(separator: "; ")
        if let countLine {
            return "\(title). \(rowSpeech). \(countLine). \(footer)"
        }
        return "\(title). \(rowSpeech). \(footer)"
    }

    static func fallbackFooter(for ref: FeedThemeCollectionRef) -> String {
        ref.collectionCount > 1 ? "See all \(ref.collectionCount) in \(ref.name)" : "Open \(ref.name)"
    }

    static func build(
        title: String?,
        contract: FeedRoundupContract?,
        fallbackKicker: String? = nil,
        fallbackFooter: String? = nil,
        allowFlexibleRowCount: Bool = false,
        now: Date = Date()
    ) -> DiscoverRoundupCardModel? {
        guard let contract else { return nil }
        let headline = trimmed(title)
        let rawKicker = trimmed(contract.kicker)
        let kicker = rawKicker.isEmpty ? trimmed(fallbackKicker) : rawKicker
        let rawFooter = trimmed(contract.footer)
        let footer = rawFooter.isEmpty ? trimmed(fallbackFooter) : rawFooter
        guard !headline.isEmpty, !kicker.isEmpty, !footer.isEmpty else { return nil }

        let upperKicker = kicker.uppercased()
        let isYardstickPair = upperKicker == "FOR SCALE"
        let isTwoRowPair = isYardstickPair || upperKicker.hasPrefix("HEAD TO HEAD")
        let isWeekEvents = upperKicker.hasSuffix("THIS WEEK") || upperKicker.hasSuffix("THIS WEEKEND")
        let isCompleteGroup = contract.completeGroup == true
        let isStrip = trimmed(contract.presentation).lowercased() == "strip"

        let hasDivisionState = !contract.unpricedOutcomes.isEmpty || contract.rows.contains { $0.settledOut != nil }
        let minRows = allowFlexibleRowCount ? 1 : ((isTwoRowPair || isWeekEvents) ? 2 : 3)
        let baseMaxRows = allowFlexibleRowCount ? 8 : (isTwoRowPair ? 2 : isWeekEvents ? 4 : isCompleteGroup ? 8 : 5)
        let maxRows = hasDivisionState ? max(baseMaxRows, 4) : baseMaxRows
        let served = allowFlexibleRowCount ? Array(contract.rows.prefix(maxRows)) : contract.rows
        let unpricedSlots = max(0, maxRows - served.count)
        let appendedUnpriced = hasDivisionState ? Array(contract.unpricedOutcomes.prefix(unpricedSlots)) : []
        let combinedCount = served.count + appendedUnpriced.count
        guard combinedCount >= minRows, combinedCount <= maxRows else { return nil }

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

        // Direction 228 (#12885): numerical scale rows always run in ascending
        // numerical order, never by probability. Otherwise explicit `order: "probability"`
        // sorts highest-first and dynamic candidate producers preserve canonical order.
        let normalizedOrder = trimmed(contract.order).lowercased()
        if validated.allSatisfy({ $0.kind == .market }),
           let scaleKeys = NumericalMarketScaleOrder228.scaleKeys(
               for: validated.map(\.label),
               orderHint: contract.order,
               totalOutcomeCount: validated.count
           ) {
            let keyed = Array(zip(validated, scaleKeys))
            validated = keyed.sorted { lhs, rhs in
                if lhs.1 != rhs.1 { return lhs.1 < rhs.1 }
                return lhs.0.index < rhs.0.index
            }.map(\.0)
        } else if normalizedOrder == "probability" {
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

        let builtPricedRows: [DiscoverRoundupRowModel] = zip(validated.indices, validated).map { idx, item in
            let divisionDisplay: MachineryOutcomeDisplay441A? = item.row.settledOut.map {
                MachineryOutcomeDisplay441A.describe(
                    probability: item.row.probability,
                    renderedPercent: item.row.renderedPercent,
                    unflooredPercent: item.row.unflooredPercent,
                    settledOut: $0
                )
            }
            let baseParts = probabilityParts(
                probability: item.row.probability,
                renderedPercent: item.row.unflooredPercent ?? item.row.renderedPercent
            )
            let parts: (marker: String?, digits: String) = (divisionDisplay?.state == .subOnePercent)
                ? ("<", "1")
                : baseParts
            let resolvedFill: Double = {
                if let divisionDisplay {
                    switch divisionDisplay.state {
                    case .eliminated, .noRecentProbability:
                        return 0.0
                    case .subOnePercent:
                        return 0.02
                    case .live:
                        return min(1.0, max(0.0, item.row.probability))
                    }
                }
                return min(1.0, max(0.0, item.row.probability))
            }()
            let secondary: DiscoverRoundupSecondaryBarModel? = {
                guard let secProb = item.row.secondaryProbability else { return nil }
                let secParts = probabilityParts(
                    probability: secProb,
                    renderedPercent: item.row.secondaryUnflooredPercent ?? item.row.secondaryRenderedPercent
                )
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
                rawProbability: item.row.probability,
                marker: parts.marker,
                digits: parts.digits,
                fill: resolvedFill,
                secondary: secondary,
                observedAt: stamps[idx],
                showsRowAgeMark: !allOld && staleFlags[idx],
                sourceMark: item.row.sourceMark,
                renderedPercent: item.row.renderedPercent,
                divisionDisplay: divisionDisplay
            )
        }

        let builtUnpricedRows: [DiscoverRoundupRowModel] = appendedUnpriced.enumerated().map { idx, item in
            let rowLabel = trimmed(item.name).isEmpty ? "Contender" : trimmed(item.name)
            return DiscoverRoundupRowModel(
                id: "unpriced:\(item.marketId ?? 0):\(item.outcomeId):\(idx):\(rowLabel.lowercased())",
                targetId: max(1, item.marketId ?? (idx + 1)),
                kind: .market,
                cadence: .futures,
                label: rowLabel,
                opponentLabel: nil,
                dateLabel: nil,
                detailCallout: nil,
                rawProbability: 0.0,
                marker: nil,
                digits: "",
                fill: 0.0,
                secondary: nil,
                observedAt: nil,
                showsRowAgeMark: false,
                sourceMark: nil,
                renderedPercent: nil,
                divisionDisplay: item.display441A
            )
        }
        let builtRows = builtPricedRows + builtUnpricedRows

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

    static func probabilityText(probability: Double, renderedPercent: Int?) -> String {
        let parts = probabilityParts(probability: probability, renderedPercent: renderedPercent)
        return "\(parts.marker ?? "")\(parts.digits)%"
    }

    static func probabilityParts(probability: Double, renderedPercent: Int?) -> (marker: String?, digits: String) {
        let clamped = min(1.0, max(0.0, probability))
        if clamped > 0.0 && clamped < 0.01 {
            return ("<", "1")
        }
        if clamped > 0.99 && clamped < 1.0 {
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
