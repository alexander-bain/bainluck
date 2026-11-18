import Foundation

// MARK: - Grouping Machinery Models (#12288 · Ruling 227: A · Direction 228)
//
// Pure structural contracts for `GET /api/containers/preview/machinery` and
// `GET /api/containers/{slug}` (`visual_block` + `machinery_card`).
// Zero topic-specific branches: every card and section dispatches strictly on
// `formId` and the served atom shape.

private nonisolated struct MachineryCodingKey: CodingKey {
    var stringValue: String
    var intValue: Int? { nil }

    init(_ string: String) {
        self.stringValue = string
    }

    init?(stringValue: String) {
        self.stringValue = stringValue
    }

    init?(intValue: Int) {
        return nil
    }
}

private extension KeyedDecodingContainer where Key == MachineryCodingKey {
    nonisolated func decodeFirst<T: Decodable>(_ type: T.Type, keys: [String]) -> T? {
        for raw in keys {
            let key = MachineryCodingKey(raw)
            if contains(key), (try? decodeNil(forKey: key)) != true,
               let val = try? decode(T.self, forKey: key) {
                return val
            }
        }
        return nil
    }
}

/// All 8 visual forms emitted by `choose_section_form` in `container_machinery.py`.
nonisolated enum MachineryFormId: String, Codable, CaseIterable, Equatable, Sendable {
    case pairedStageBars = "paired_stage_bars"
    case coinFlipMatchups = "coin_flip_matchups"
    case matchupSlate = "matchup_slate"
    case duelBar = "duel_bar"
    case contenderSpotlight = "contender_spotlight"
    case siblingFieldsGrid = "sibling_fields_grid"
    case benchmarkStrip = "benchmark_strip"
    case probabilityHistoryChart = "probability_history_chart"
}

/// Verified subject art (`team_logo`, `tmdb_poster`, `tmdb_headshot`, `person`, etc.).
/// When `verifiedURL` is `nil`, views draw NO avatar/placeholder letters ("real art or nothing").
nonisolated struct MachinerySubjectArt: Decodable, Equatable, Sendable {
    let url: String?
    let kind: String
    let detail: String
    let accentColor: String

    init(
        url: String? = nil,
        kind: String = "none",
        detail: String = "",
        accentColor: String = ""
    ) {
        self.url = url
        self.kind = kind
        self.detail = detail
        self.accentColor = accentColor
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        let rawURL = c.decodeFirst(String.self, keys: ["url"])?.trimmingCharacters(in: .whitespacesAndNewlines)
        self.url = (rawURL?.isEmpty == false) ? rawURL : nil
        self.kind = c.decodeFirst(String.self, keys: ["kind"]) ?? "none"
        self.detail = c.decodeFirst(String.self, keys: ["detail"]) ?? ""
        self.accentColor = c.decodeFirst(String.self, keys: ["accentColor", "accent_color"]) ?? ""
    }

    var verifiedURL: URL? {
        guard let url, !url.isEmpty,
              let parsed = URL(string: url),
              let scheme = parsed.scheme?.lowercased(),
              scheme == "https" else {
            return nil
        }
        return parsed
    }

    var isPoster: Bool {
        kind == "tmdb_poster"
    }

    var isTeamLogo: Bool {
        kind == "team_logo" || kind == "espn_team_logo"
    }
}

/// One outcome row inside `duel_bar`, `contender_spotlight`, `sibling_fields_grid`,
/// `benchmark_strip`, or `machinery_card.rows`.
nonisolated struct MachineryOutcomeVisual: Decodable, Equatable, Identifiable, Sendable {
    let outcomeId: Int
    let marketId: Int?
    let name: String
    let probability: Double
    let renderedPercent: Int
    let art: MachinerySubjectArt?

    var id: String { "\(marketId ?? 0):\(outcomeId):\(name)" }

    init(
        outcomeId: Int,
        marketId: Int? = nil,
        name: String,
        probability: Double,
        renderedPercent: Int,
        art: MachinerySubjectArt? = nil
    ) {
        self.outcomeId = outcomeId
        self.marketId = marketId
        self.name = name
        self.probability = probability
        self.renderedPercent = renderedPercent
        self.art = art
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.outcomeId = c.decodeFirst(Int.self, keys: ["outcomeId", "outcome_id", "id"]) ?? 0
        self.marketId = c.decodeFirst(Int.self, keys: ["marketId", "market_id"])
        self.name = c.decodeFirst(String.self, keys: ["name", "label"]) ?? ""
        let prob = c.decodeFirst(Double.self, keys: ["probability"]) ?? 0
        self.probability = prob
        if let pct = c.decodeFirst(Int.self, keys: ["renderedPercent", "rendered_percent"]) {
            self.renderedPercent = pct
        } else {
            self.renderedPercent = Int((prob * 100.0).rounded())
        }
        self.art = c.decodeFirst(MachinerySubjectArt.self, keys: ["art"])
    }
}

/// One event row inside `coin_flip_matchups`, `matchup_slate`, or an event-led `machinery_card`.
nonisolated struct MachineryEventVisualItem: Decodable, Equatable, Identifiable, Sendable {
    let eventId: Int
    let awayTeam: String
    let homeTeam: String
    let awayShort: String
    let homeShort: String
    let awayPct: Int
    let homePct: Int
    let commenceTime: String
    let awayArt: MachinerySubjectArt?
    let homeArt: MachinerySubjectArt?

    var id: Int { eventId }

    init(
        eventId: Int,
        awayTeam: String = "",
        homeTeam: String = "",
        awayShort: String,
        homeShort: String,
        awayPct: Int,
        homePct: Int,
        commenceTime: String = "",
        awayArt: MachinerySubjectArt? = nil,
        homeArt: MachinerySubjectArt? = nil
    ) {
        self.eventId = eventId
        self.awayTeam = awayTeam.isEmpty ? awayShort : awayTeam
        self.homeTeam = homeTeam.isEmpty ? homeShort : homeTeam
        self.awayShort = awayShort
        self.homeShort = homeShort
        self.awayPct = awayPct
        self.homePct = homePct
        self.commenceTime = commenceTime
        self.awayArt = awayArt
        self.homeArt = homeArt
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.eventId = c.decodeFirst(Int.self, keys: ["eventId", "event_id", "id"]) ?? 0
        let aTeam = c.decodeFirst(String.self, keys: ["awayTeam", "away_team"]) ?? ""
        let hTeam = c.decodeFirst(String.self, keys: ["homeTeam", "home_team"]) ?? ""
        let aShort = c.decodeFirst(String.self, keys: ["awayShort", "away_short"]) ?? aTeam
        let hShort = c.decodeFirst(String.self, keys: ["homeShort", "home_short"]) ?? hTeam
        self.awayTeam = aTeam.isEmpty ? aShort : aTeam
        self.homeTeam = hTeam.isEmpty ? hShort : hTeam
        self.awayShort = aShort
        self.homeShort = hShort
        self.awayPct = c.decodeFirst(Int.self, keys: ["awayPct", "away_pct"]) ?? 50
        self.homePct = c.decodeFirst(Int.self, keys: ["homePct", "home_pct"]) ?? 50
        self.commenceTime = c.decodeFirst(String.self, keys: ["commenceTime", "commence_time"]) ?? ""
        self.awayArt = c.decodeFirst(MachinerySubjectArt.self, keys: ["awayArt", "away_art"])
        self.homeArt = c.decodeFirst(MachinerySubjectArt.self, keys: ["homeArt", "home_art"])
    }
}

/// One market item inside `duel_bar`, `contender_spotlight`, `sibling_fields_grid`, or `benchmark_strip`.
nonisolated struct MachineryMarketVisualItem: Decodable, Equatable, Identifiable, Sendable {
    let marketId: Int
    let title: String
    let href: String
    let scaleOrdered: Bool
    let leaderOutcomeId: Int?
    let outcomes: [MachineryOutcomeVisual]

    var id: Int { marketId }

    init(
        marketId: Int,
        title: String,
        href: String = "",
        scaleOrdered: Bool = false,
        leaderOutcomeId: Int? = nil,
        outcomes: [MachineryOutcomeVisual]
    ) {
        self.marketId = marketId
        self.title = title
        self.href = href
        self.scaleOrdered = scaleOrdered
        self.leaderOutcomeId = leaderOutcomeId
        self.outcomes = outcomes
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        let mid = c.decodeFirst(Int.self, keys: ["marketId", "market_id", "id"]) ?? 0
        self.marketId = mid
        self.title = c.decodeFirst(String.self, keys: ["title", "name"]) ?? ""
        self.href = c.decodeFirst(String.self, keys: ["href"]) ?? "/futures/\(mid)"
        self.scaleOrdered = c.decodeFirst(Bool.self, keys: ["scaleOrdered", "scale_ordered"]) ?? false
        self.leaderOutcomeId = c.decodeFirst(Int.self, keys: ["leaderOutcomeId", "leader_outcome_id"])
        let rawOutcomes = c.decodeFirst([MachineryOutcomeVisual].self, keys: ["outcomes", "sides"]) ?? []
        self.outcomes = Self.normalizedOutcomes(rawOutcomes, scaleOrdered: self.scaleOrdered)
    }

    /// Enforces Direction 228 ascending numerical order on ladder, range, rate, and count markets.
    static func normalizedOutcomes(
        _ outcomes: [MachineryOutcomeVisual],
        scaleOrdered: Bool
    ) -> [MachineryOutcomeVisual] {
        guard outcomes.count >= 2 else { return outcomes }
        if let ordered = NumericalMarketScaleOrder228.orderedAll(
            outcomes,
            label: \.name,
            probability: { $0.probability }
        ) {
            return ordered.map(\.element)
        }
        return outcomes
    }

    var effectiveScaleOrdered: Bool {
        scaleOrdered || NumericalMarketScaleOrder228.scaleKeys(for: outcomes.map(\.name)) != nil
    }
}

/// Time-series point inside `MachineryHistorySeries`.
nonisolated struct MachineryHistorySeriesPoint: Decodable, Equatable, Sendable {
    let t: String
    let pct: Int

    init(t: String, pct: Int) {
        self.t = t
        self.pct = pct
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.t = c.decodeFirst(String.self, keys: ["t"]) ?? ""
        if let intVal = c.decodeFirst(Int.self, keys: ["pct"]) {
            self.pct = intVal
        } else if let dblVal = c.decodeFirst(Double.self, keys: ["pct"]) {
            self.pct = Int(dblVal.rounded())
        } else {
            self.pct = 0
        }
    }
}

/// One outcome series inside `probability_history_chart` or `mini_chart`.
nonisolated struct MachineryHistorySeries: Decodable, Equatable, Identifiable, Sendable {
    let outcomeId: Int
    let name: String
    let currentPct: Int
    let color: String
    let art: MachinerySubjectArt?
    let points: [MachineryHistorySeriesPoint]

    var id: Int { outcomeId }

    init(
        outcomeId: Int,
        name: String,
        currentPct: Int,
        color: String,
        art: MachinerySubjectArt? = nil,
        points: [MachineryHistorySeriesPoint]
    ) {
        self.outcomeId = outcomeId
        self.name = name
        self.currentPct = currentPct
        self.color = color
        self.art = art
        self.points = points
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.outcomeId = c.decodeFirst(Int.self, keys: ["outcomeId", "outcome_id", "id"]) ?? 0
        self.name = c.decodeFirst(String.self, keys: ["name"]) ?? ""
        self.currentPct = c.decodeFirst(Int.self, keys: ["currentPct", "current_pct"]) ?? 0
        self.color = c.decodeFirst(String.self, keys: ["color"]) ?? "#2563EB"
        self.art = c.decodeFirst(MachinerySubjectArt.self, keys: ["art"])
        self.points = c.decodeFirst([MachineryHistorySeriesPoint].self, keys: ["points"]) ?? []
    }
}

/// One `probability_history_chart` item (section block or card `mini_chart`).
nonisolated struct MachineryHistoryChartItem: Decodable, Equatable, Identifiable, Sendable {
    let marketId: Int
    let title: String
    let href: String
    let scaleOrdered: Bool
    let startIso: String
    let endIso: String
    let yMin: Int
    let yMax: Int
    let maxSwingPp: Int?
    let moved: Bool
    let series: [MachineryHistorySeries]

    var id: Int { marketId }

    init(
        marketId: Int,
        title: String,
        href: String = "",
        scaleOrdered: Bool = false,
        startIso: String = "",
        endIso: String = "",
        yMin: Int = 0,
        yMax: Int = 100,
        maxSwingPp: Int? = nil,
        moved: Bool = true,
        series: [MachineryHistorySeries]
    ) {
        self.marketId = marketId
        self.title = title
        self.href = href
        self.scaleOrdered = scaleOrdered
        self.startIso = startIso
        self.endIso = endIso
        self.yMin = yMin
        self.yMax = yMax
        self.maxSwingPp = maxSwingPp
        self.moved = moved
        self.series = series
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        let mid = c.decodeFirst(Int.self, keys: ["marketId", "market_id", "id"]) ?? 0
        self.marketId = mid
        self.title = c.decodeFirst(String.self, keys: ["title"]) ?? ""
        self.href = c.decodeFirst(String.self, keys: ["href"]) ?? "/futures/\(mid)"
        self.scaleOrdered = c.decodeFirst(Bool.self, keys: ["scaleOrdered", "scale_ordered"]) ?? false
        self.startIso = c.decodeFirst(String.self, keys: ["startIso", "start_iso"]) ?? ""
        self.endIso = c.decodeFirst(String.self, keys: ["endIso", "end_iso"]) ?? ""
        self.yMin = c.decodeFirst(Int.self, keys: ["yMin", "y_min"]) ?? 0
        self.yMax = c.decodeFirst(Int.self, keys: ["yMax", "y_max"]) ?? 100
        self.maxSwingPp = c.decodeFirst(Int.self, keys: ["maxSwingPp", "max_swing_pp"])
        let rawSeries = c.decodeFirst([MachineryHistorySeries].self, keys: ["series"]) ?? []
        if self.scaleOrdered,
           let ordered = NumericalMarketScaleOrder228.orderedAll(
               rawSeries,
               label: \.name,
               probability: { Double($0.currentPct) / 100.0 }
           ) {
            self.series = ordered.map(\.element)
        } else {
            self.series = rawSeries
        }
        if let explicitMoved = c.decodeFirst(Bool.self, keys: ["moved"]) {
            self.moved = explicitMoved
        } else {
            let computedSwing = rawSeries.reduce(0) { best, s in
                let pcts = s.points.map(\.pct)
                guard let lo = pcts.min(), let hi = pcts.max(), pcts.count >= 2 else { return best }
                return max(best, hi - lo)
            }
            self.moved = computedSwing >= 2
        }
    }

    /// Slice 4: flat lines never draw as a chart picture.
    var hasMovingSeries: Bool {
        guard moved, !series.isEmpty else { return false }
        let maxSwing = series.reduce(0) { best, s in
            let pcts = s.points.map(\.pct)
            guard let lo = pcts.min(), let hi = pcts.max(), pcts.count >= 2 else { return best }
            return max(best, hi - lo)
        }
        return maxSwing >= 2
    }
}

/// Polymorphic `visual_block` attached to each `ContainerHubSection`.
nonisolated struct MachineryVisualBlock: Decodable, Equatable, Sendable {
    let formId: MachineryFormId
    let initialVisibleLimit: Int
    let pairedMetricSet: PairedMetricSet?
    let eventItems: [MachineryEventVisualItem]
    let marketItems: [MachineryMarketVisualItem]
    let historyItems: [MachineryHistoryChartItem]

    var effectiveVisibleLimit: Int {
        min(3, max(1, initialVisibleLimit))
    }

    init(
        formId: MachineryFormId,
        initialVisibleLimit: Int = 3,
        pairedMetricSet: PairedMetricSet? = nil,
        eventItems: [MachineryEventVisualItem] = [],
        marketItems: [MachineryMarketVisualItem] = [],
        historyItems: [MachineryHistoryChartItem] = []
    ) {
        self.formId = formId
        self.initialVisibleLimit = initialVisibleLimit
        self.pairedMetricSet = pairedMetricSet
        self.eventItems = eventItems
        self.marketItems = marketItems
        self.historyItems = historyItems
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        let rawForm = c.decodeFirst(String.self, keys: ["formId", "form_id", "form"]) ?? "sibling_fields_grid"
        let resolvedForm = MachineryFormId(rawValue: rawForm) ?? .siblingFieldsGrid
        self.formId = resolvedForm
        self.initialVisibleLimit = c.decodeFirst(Int.self, keys: ["initialVisibleLimit", "initial_visible_limit"]) ?? 3
        self.pairedMetricSet = c.decodeFirst(PairedMetricSet.self, keys: ["pairedMetricSet", "paired_metric_set"])

        switch resolvedForm {
        case .pairedStageBars:
            self.eventItems = []
            self.marketItems = []
            self.historyItems = []
        case .coinFlipMatchups, .matchupSlate:
            self.eventItems = c.decodeFirst([MachineryEventVisualItem].self, keys: ["items"]) ?? []
            self.marketItems = []
            self.historyItems = []
        case .probabilityHistoryChart:
            self.eventItems = []
            self.marketItems = []
            self.historyItems = (c.decodeFirst([MachineryHistoryChartItem].self, keys: ["items"]) ?? [])
                .filter(\.hasMovingSeries)
        case .duelBar, .contenderSpotlight, .siblingFieldsGrid, .benchmarkStrip:
            self.eventItems = []
            self.marketItems = c.decodeFirst([MachineryMarketVisualItem].self, keys: ["items"]) ?? []
            self.historyItems = []
        }
    }
}

/// Compact Discover card contract (`data.roundup.machinery_card`).
nonisolated struct MachineryCardContract: Decodable, Equatable, Identifiable, Sendable {
    let slug: String
    let formId: MachineryFormId
    let kicker: String
    let title: String
    let subtitle: String
    let footer: String
    let scaleOrdered: Bool
    let sectionCount: Int
    let destinationHref: String
    let eventRows: [MachineryEventVisualItem]
    let outcomeRows: [MachineryOutcomeVisual]
    let miniChart: MachineryHistoryChartItem?

    var id: String { slug }

    var isEventCard: Bool {
        formId == .coinFlipMatchups || formId == .matchupSlate
    }

    init(
        slug: String,
        formId: MachineryFormId,
        kicker: String,
        title: String,
        subtitle: String = "",
        footer: String = "",
        scaleOrdered: Bool = false,
        sectionCount: Int = 1,
        destinationHref: String = "",
        eventRows: [MachineryEventVisualItem] = [],
        outcomeRows: [MachineryOutcomeVisual] = [],
        miniChart: MachineryHistoryChartItem? = nil
    ) {
        self.slug = slug
        self.formId = formId
        self.kicker = kicker
        self.title = title
        self.subtitle = subtitle
        self.footer = footer
        self.scaleOrdered = scaleOrdered
        self.sectionCount = sectionCount
        self.destinationHref = destinationHref.isEmpty ? "/collections/\(slug)" : destinationHref
        self.eventRows = Array(eventRows.prefix(3))
        self.outcomeRows = Array(MachineryMarketVisualItem.normalizedOutcomes(outcomeRows, scaleOrdered: scaleOrdered).prefix(3))
        self.miniChart = (miniChart?.hasMovingSeries == true) ? miniChart : nil
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        let decodedSlug = c.decodeFirst(String.self, keys: ["slug"]) ?? ""
        self.slug = decodedSlug
        let rawForm = c.decodeFirst(String.self, keys: ["formId", "form_id"]) ?? "sibling_fields_grid"
        let resolvedForm = MachineryFormId(rawValue: rawForm) ?? .siblingFieldsGrid
        self.formId = resolvedForm
        self.kicker = c.decodeFirst(String.self, keys: ["kicker"]) ?? "ROUND-UP"
        self.title = c.decodeFirst(String.self, keys: ["title"]) ?? ""
        self.subtitle = c.decodeFirst(String.self, keys: ["subtitle"]) ?? ""
        self.footer = c.decodeFirst(String.self, keys: ["footer"]) ?? ""
        let rawScaleOrdered = c.decodeFirst(Bool.self, keys: ["scaleOrdered", "scale_ordered"]) ?? false
        self.sectionCount = c.decodeFirst(Int.self, keys: ["sectionCount", "section_count"]) ?? 1
        self.destinationHref = c.decodeFirst(String.self, keys: ["destinationHref", "destination_href"]) ?? "/collections/\(decodedSlug)"

        if resolvedForm == .coinFlipMatchups || resolvedForm == .matchupSlate {
            let evs = c.decodeFirst([MachineryEventVisualItem].self, keys: ["rows"]) ?? []
            self.eventRows = Array(evs.prefix(3))
            self.outcomeRows = []
            self.scaleOrdered = false
        } else {
            let outs = c.decodeFirst([MachineryOutcomeVisual].self, keys: ["rows"]) ?? []
            let normalized = MachineryMarketVisualItem.normalizedOutcomes(outs, scaleOrdered: rawScaleOrdered)
            self.eventRows = []
            self.outcomeRows = Array(normalized.prefix(3))
            self.scaleOrdered = rawScaleOrdered || NumericalMarketScaleOrder228.scaleKeys(for: outs.map(\.name)) != nil
        }

        if let chart = c.decodeFirst(MachineryHistoryChartItem.self, keys: ["miniChart", "mini_chart"]),
           chart.hasMovingSeries {
            self.miniChart = chart
        } else {
            self.miniChart = nil
        }
    }
}

// MARK: - Admin Preview Endpoint Envelope (`GET /api/containers/preview/machinery`)

nonisolated struct MachineryPreviewDefinition: Decodable, Equatable, Sendable {
    let slug: String
    let name: String
    let category: String
    let kicker: String
    let footer: String

    init(slug: String, name: String, category: String = "", kicker: String = "", footer: String = "") {
        self.slug = slug
        self.name = name
        self.category = category
        self.kicker = kicker
        self.footer = footer
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.slug = c.decodeFirst(String.self, keys: ["slug"]) ?? ""
        self.name = c.decodeFirst(String.self, keys: ["name"]) ?? ""
        self.category = c.decodeFirst(String.self, keys: ["category"]) ?? ""
        self.kicker = c.decodeFirst(String.self, keys: ["kicker"]) ?? ""
        self.footer = c.decodeFirst(String.self, keys: ["footer"]) ?? ""
    }
}

nonisolated struct MachineryRoundupEnvelope: Decodable, Equatable, Sendable {
    let machineryCard: MachineryCardContract?
    let pairedMetricSet: PairedMetricSet?

    init(machineryCard: MachineryCardContract? = nil, pairedMetricSet: PairedMetricSet? = nil) {
        self.machineryCard = machineryCard
        self.pairedMetricSet = pairedMetricSet
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.machineryCard = c.decodeFirst(MachineryCardContract.self, keys: ["machineryCard", "machinery_card"])
        self.pairedMetricSet = c.decodeFirst(PairedMetricSet.self, keys: ["pairedMetricSet", "paired_metric_set"])
    }
}

nonisolated struct MachineryPreviewFeedItemData: Decodable, Equatable, Sendable {
    let roundup: MachineryRoundupEnvelope?

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.roundup = c.decodeFirst(MachineryRoundupEnvelope.self, keys: ["roundup"])
    }
}

nonisolated struct MachineryPreviewFeedItem: Decodable, Equatable, Sendable {
    let data: MachineryPreviewFeedItemData?
    let roundupContract: MachineryRoundupEnvelope?

    var resolvedRoundup: MachineryRoundupEnvelope? {
        data?.roundup ?? roundupContract
    }

    init(roundup: MachineryRoundupEnvelope?) {
        self.data = nil
        self.roundupContract = roundup
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.data = c.decodeFirst(MachineryPreviewFeedItemData.self, keys: ["data"])
        self.roundupContract = c.decodeFirst(MachineryRoundupEnvelope.self, keys: ["roundupContract", "roundup_contract"])
    }
}

nonisolated struct MachineryPreviewEntry: Decodable, Identifiable, Sendable {
    let slug: String
    let definition: MachineryPreviewDefinition
    let feedItem: MachineryPreviewFeedItem?
    let container: ContainerHubResponse?

    var id: String { slug }

    var displayName: String {
        let short = definition.name.trimmingCharacters(in: .whitespacesAndNewlines)
        if !short.isEmpty, short.count <= 28 {
            return short
        }
        let kicker = definition.kicker.trimmingCharacters(in: .whitespacesAndNewlines)
        if !kicker.isEmpty, kicker.count <= 28 {
            return kicker
        }
        return ""
    }

    var machineryCard: MachineryCardContract? {
        feedItem?.resolvedRoundup?.machineryCard
    }

    var pairedMetricSet: PairedMetricSet? {
        feedItem?.resolvedRoundup?.pairedMetricSet
    }

    init(
        slug: String,
        definition: MachineryPreviewDefinition,
        feedItem: MachineryPreviewFeedItem?,
        container: ContainerHubResponse?
    ) {
        self.slug = slug
        self.definition = definition
        self.feedItem = feedItem
        self.container = container
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.slug = c.decodeFirst(String.self, keys: ["slug"]) ?? ""
        self.definition = c.decodeFirst(MachineryPreviewDefinition.self, keys: ["definition"])
            ?? MachineryPreviewDefinition(slug: self.slug, name: self.slug)
        self.feedItem = c.decodeFirst(MachineryPreviewFeedItem.self, keys: ["feedItem", "feed_item"])
        self.container = c.decodeFirst(ContainerHubResponse.self, keys: ["container"])
    }
}

nonisolated struct MachineryPreviewResponse: Decodable, Sendable {
    let publicSwitchEnabled: Bool
    let count: Int
    let items: [MachineryPreviewEntry]

    init(publicSwitchEnabled: Bool = false, count: Int = 0, items: [MachineryPreviewEntry] = []) {
        self.publicSwitchEnabled = publicSwitchEnabled
        self.count = count
        self.items = items
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: MachineryCodingKey.self)
        self.publicSwitchEnabled = c.decodeFirst(Bool.self, keys: ["publicSwitchEnabled", "public_switch_enabled"]) ?? false
        let decodedItems = c.decodeFirst([MachineryPreviewEntry].self, keys: ["items"]) ?? []
        self.items = decodedItems
        self.count = c.decodeFirst(Int.self, keys: ["count"]) ?? decodedItems.count
    }
}
