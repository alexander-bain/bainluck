import SwiftUI

/// #11666 (Item 16a, Decide 91-C) — Native Motorsport / Formula 1 Atlas Presentation:
///   1. **Race Phase Headline (`FieldPhaseHeadlinePresentation10868`)**: Built via
///      `RacingFieldPageAdapter10868.headline` over `FuturesMarketDetail`, showing each
///      displayed driver's named win chance (or `"No recent probability"` when stale, or
///      `"Settled · no current chance"` when resolved) with its own recorded clock and
///      an `"About this race"` disclosure sheet.
///   2. **Field Win-Chance Outlook Bars (`FieldOutlookBarsPresentation10868`)**: Zero-based
///      shared-scale bar comparison across the displayed driver window with `Previous` /
///      `Next` traversal through the full roster and source-provenance Details sheets.
///   3. **Win and Podium Chances (`FieldWinPodiumPresentation10868`)**: Built via
///      `RacingWinPodiumAdapter10868.card` when a podium market and explicit outcome-ID
///      join are supplied.
///   4. **Driver Contender Chooser (`FieldContenderChooserPresentation10868`)**: Featured
///      top contenders, expandable `"More contenders"` list, and surname group browse
///      (`A–F`, `G–L`, `M–R`, `S–Z`).
enum EventAtlasRacingCards11666 {

    // MARK: - Sport & Market Gating

    private static let racingPrefixes: [String] = [
        "f1",
        "formula",
        "motorsport",
        "nascar",
        "indycar",
        "auto_racing",
        "motogp"
    ]

    nonisolated static func isRacingSport(_ raw: String?) -> Bool {
        guard let raw else { return false }
        let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        guard !lower.isEmpty else { return false }
        return racingPrefixes.contains { lower == $0 || lower.hasPrefix($0) }
    }

    nonisolated static func applies(
        sportSub: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && isRacingSport(sportSub)
    }

    nonisolated static func applies(
        market: FuturesMarketDetail,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        guard atlasEnabled, market.mutuallyExclusive == true else { return false }
        if isRacingSport(market.llmSportCategory) || isRacingSport(market.sport) {
            return true
        }
        return false
    }

    // MARK: - Surname Band Grouping

    nonisolated enum SurnameGroup: String, CaseIterable, Equatable, Sendable {
        case aToF = "a-f"
        case gToL = "g-l"
        case mToR = "m-r"
        case sToZ = "s-z"

        var label: String {
            switch self {
            case .aToF: return "A–F"
            case .gToL: return "G–L"
            case .mToR: return "M–R"
            case .sToZ: return "S–Z"
            }
        }

        static func group(for driverName: String) -> SurnameGroup {
            let short = TeamShortName.short(driverName).trimmingCharacters(in: .whitespacesAndNewlines)
            guard let firstChar = short.uppercased().first else { return .aToF }
            if firstChar >= "A" && firstChar <= "F" { return .aToF }
            if firstChar >= "G" && firstChar <= "L" { return .gToL }
            if firstChar >= "M" && firstChar <= "R" { return .mToR }
            return .sToZ
        }
    }

    // MARK: - Field Outlook Input Builder

    static let maxDisplayedBars = 6

    static func buildOutlookInput(
        market: FuturesMarketDetail,
        selectedOutcomeID: Int? = nil,
        host: RacingFieldPageAdapter10868.Host = .init()
    ) -> FieldOutlookInput10868 {
        let phase = RacingFieldPageAdapter10868.phase(market)
        let scope = RacingFieldPageAdapter10868.scope(market, phase: phase)
        let cohort = RacingFieldPageAdapter10868.cohort(market, held: host.cohort)
        let catalogue = RacingFieldPageAdapter10868.catalogue(
            market,
            cohort: cohort,
            phase: phase,
            host: host
        )

        let displayedOutcomes = Array(market.outcomes.prefix(maxDisplayedBars))
        let slots: [FieldOutlookSlot10868] = displayedOutcomes.map { outcome in
            let ref = RacingFieldPageAdapter10868.ref(outcome, in: market, scope: scope)
            let short = surnameLabel(outcome.name)
            return FieldOutlookSlot10868(
                ref: ref,
                label: outcome.name,
                shortLabel: short
            )
        }

        let traversal: [FieldChooserOriginalRef10868] = market.outcomes.map { outcome in
            RacingFieldPageAdapter10868.ref(outcome, in: market, scope: scope)
        }

        var chances: [FieldOutlookBeforeChance10868] = []
        for outcome in market.outcomes {
            let ref = RacingFieldPageAdapter10868.ref(outcome, in: market, scope: scope)
            let beforeRead = RacingFieldPageAdapter10868.beforeReading(
                outcome,
                in: market,
                phase: phase,
                host: host
            )
            if phase == .before,
               case .chance(let probability, _, _) = RacingFieldPageAdapter10868.reading(
                   outcome,
                   in: market,
                   host: host
               ) {
                chances.append(
                    FieldOutlookBeforeChance10868(
                        ref: ref,
                        probability: probability,
                        reading: beforeRead
                    )
                )
            }
        }

        let maxProb = chances.map(\.probability).max() ?? 0.5
        let ceiling = computeScaleCeiling(maxProbability: maxProb)
        let mid = ceiling / 2.0
        let ceilingPct = Int((ceiling * 100).rounded())
        let midPct = Int((mid * 100).rounded())
        let ticks: [FieldOutlookTick10868] = chances.isEmpty
            ? []
            : [
                FieldOutlookTick10868(probability: 0.0, label: "0%"),
                FieldOutlookTick10868(probability: mid, label: "\(midPct)%"),
                FieldOutlookTick10868(probability: ceiling, label: "\(ceilingPct)%")
            ]
        let scaleWords = chances.isEmpty
            ? (phase == .final ? "Settled market · results shown per driver" : "No recent probability on scale")
            : "0–\(ceilingPct)% chance · each driver is an independent outcome"
        let scale = FieldOutlookScale10868(
            ceiling: ceiling,
            ticks: ticks,
            words: scaleWords
        )

        let resolvedSelectedOutcome: FuturesOutcome? = {
            if let selectedOutcomeID {
                return market.outcomes.first(where: { $0.id == selectedOutcomeID })
            }
            return displayedOutcomes.first
        }()
        let selected: FieldChooserSelected10868? = resolvedSelectedOutcome.map { outcome in
            FieldChooserSelected10868(
                ref: RacingFieldPageAdapter10868.ref(outcome, in: market, scope: scope),
                words: phase == .final ? "Settled race winner market" : "Selected driver",
                unavailableWords: RacingFieldPageAdapter10868.Words.unavailable
            )
        }

        let noteText = "\(market.outcomes.count) drivers"

        let copy = FieldOutlookCopy10868(
            title: phase == .final ? "Race winner results" : "Driver win chances",
            note: noteText,
            graphicLabel: phase == .final ? "Settled driver results" : "Recorded driver win chances",
            missingChance: phase == .final
                ? RacingFieldPageAdapter10868.Words.settledNoChance
                : AllMarketsCatalogView9483.noRecentPrice,
            offScale: "Above the \(ceilingPct)% scale",
            outsideDisplayed: "Selected driver is outside the top \(displayedOutcomes.count) bars",
            previousLabel: "Previous driver",
            nextLabel: "Next driver",
            details: "Driver details",
            detailsHint: "Opens recorded timestamp and source details",
            resultUnknown: RacingFieldPageAdapter10868.Words.resultUnknown
        )

        return FieldOutlookInput10868(
            scope: scope,
            catalogue: catalogue,
            selected: selected,
            displayed: slots,
            traversal: traversal,
            chances: chances,
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: RacingFieldPageAdapter10868.Words.unavailable,
            chooseHint: "Selects this driver"
        )
    }

    // MARK: - Contender Chooser Input Builder

    static func buildChooserInput(
        market: FuturesMarketDetail,
        selectedOutcomeID: Int? = nil,
        moreExpanded: Bool = false,
        browseExpanded: Bool = false,
        selectedSurnameGroup: SurnameGroup = .aToF,
        host: RacingFieldPageAdapter10868.Host = .init()
    ) -> FieldChooserInput10868 {
        let phase = RacingFieldPageAdapter10868.phase(market)
        let scope = RacingFieldPageAdapter10868.scope(market, phase: phase)
        let cohort = RacingFieldPageAdapter10868.cohort(market, held: host.cohort)
        let catalogue = RacingFieldPageAdapter10868.catalogue(
            market,
            cohort: cohort,
            phase: phase,
            host: host
        )

        let featuredOutcomes = Array(market.outcomes.prefix(2))
        let moreOutcomes = Array(market.outcomes.dropFirst(2))

        let resolvedSelectedOutcome: FuturesOutcome? = {
            if let selectedOutcomeID {
                return market.outcomes.first(where: { $0.id == selectedOutcomeID })
            }
            return market.outcomes.first
        }()

        let selected: FieldChooserSelected10868? = resolvedSelectedOutcome.map { outcome in
            FieldChooserSelected10868(
                ref: RacingFieldPageAdapter10868.ref(outcome, in: market, scope: scope),
                words: phase == .final ? "Settled race winner market" : "Selected driver",
                unavailableWords: RacingFieldPageAdapter10868.Words.unavailable
            )
        }

        let featured = FieldChooserFeatured10868(
            title: "Leading contenders",
            badge: "\(featuredOutcomes.count) shown",
            refs: featuredOutcomes.map { RacingFieldPageAdapter10868.ref($0, in: market, scope: scope) },
            emptyWords: "No leading contenders in this update"
        )

        let more: FieldChooserMore10868? = moreOutcomes.isEmpty
            ? nil
            : FieldChooserMore10868(
                id: "more",
                title: "More drivers · \(moreOutcomes.count)",
                expanded: moreExpanded,
                refs: moreOutcomes.map { RacingFieldPageAdapter10868.ref($0, in: market, scope: scope) },
                emptyWords: "No additional drivers in this update"
            )

        let groups: [FieldChooserGroup10868] = SurnameGroup.allCases.compactMap { group -> FieldChooserGroup10868? in
            let matching = market.outcomes.filter { SurnameGroup.group(for: $0.name) == group }
            guard !matching.isEmpty else { return nil }
            return FieldChooserGroup10868(
                id: group.rawValue,
                label: group.label,
                countText: "\(matching.count)",
                refs: matching.map { RacingFieldPageAdapter10868.ref($0, in: market, scope: scope) }
            )
        }

        let activeGroupID: String = {
            if groups.contains(where: { $0.id == selectedSurnameGroup.rawValue }) {
                return selectedSurnameGroup.rawValue
            }
            return groups.first?.id ?? SurnameGroup.aToF.rawValue
        }()

        let browse: FieldChooserBrowse10868? = groups.isEmpty
            ? nil
            : FieldChooserBrowse10868(
                id: "browse",
                title: "Browse all \(market.outcomes.count) drivers",
                expanded: browseExpanded,
                note: "By surname · select any driver to inspect their recorded chance.",
                groupsLabel: "Surname range",
                groups: groups,
                selectedGroupID: activeGroupID,
                noGroupWords: "Select a surname group",
                groupUnavailableWords: "Surname group unavailable in this update",
                emptyGroupWords: "No drivers in this surname range"
            )

        let frameLegend = "Recorded win chance"
        let frame = FieldChooserFrame10868(
            start: 0,
            end: 100,
            ceiling: 1.0,
            key: frameLegend,
            referenceKey: nil,
            scale: "0–100% chance",
            provenance: "Recorded probabilities"
        )

        return FieldChooserInput10868(
            scope: scope,
            intro: "Choose a driver",
            featured: featured,
            context: "\(market.outcomes.count) drivers in \(market.name)",
            more: more,
            browse: browse,
            catalogue: catalogue,
            frame: frame,
            selected: selected,
            unavailableWords: RacingFieldPageAdapter10868.Words.unavailable,
            chooseHint: "Selects this driver"
        )
    }

    // MARK: - Details Sheet Item

    nonisolated struct DriverDetailsSheetItem: Identifiable, Equatable, Sendable {
        let id: String
        let driverName: String
        let marketName: String
        let readingLabel: String
        let readingValue: String
        let readingDetail: String?
        let resultWords: String?
    }

    static func buildDriverDetails(
        ref: FieldChooserOriginalRef10868,
        market: FuturesMarketDetail,
        host: RacingFieldPageAdapter10868.Host = .init()
    ) -> DriverDetailsSheetItem? {
        guard let outcomeID = Int(ref.outcomeID),
              let outcome = market.outcomes.first(where: { $0.id == outcomeID }) else {
            return nil
        }
        let phase = RacingFieldPageAdapter10868.phase(market)
        let reading = RacingFieldPageAdapter10868.beforeReading(
            outcome,
            in: market,
            phase: phase,
            host: host
        )
        let result = RacingFieldPageAdapter10868.result(
            outcome,
            in: market,
            phase: phase,
            host: host
        )
        let valueText: String
        let detailText: String?
        switch reading.value {
        case .recorded(let text, let detail):
            valueText = text
            detailText = detail
        case .missing(let words):
            valueText = words
            detailText = nil
        }
        return DriverDetailsSheetItem(
            id: "\(market.id):\(outcome.id)",
            driverName: outcome.name,
            marketName: market.name,
            readingLabel: reading.label,
            readingValue: valueText,
            readingDetail: detailText,
            resultWords: result?.words
        )
    }

    // MARK: - Helpers

    nonisolated static func surnameLabel(_ fullName: String) -> String {
        TeamShortName.short(fullName)
    }

    nonisolated static func computeScaleCeiling(maxProbability: Double) -> Double {
        guard maxProbability.isFinite, maxProbability > 0 else { return 0.50 }
        let rungs: [Double] = [0.20, 0.30, 0.40, 0.50, 0.60, 0.75, 1.00]
        for rung in rungs where maxProbability <= rung {
            return rung
        }
        return 1.00
    }
}

// MARK: - Section View Mounted in FuturesDetailView

struct EventAtlasRacingSectionView11666: View {
    let market: FuturesMarketDetail
    var podium: RacingWinPodiumAdapter10868.Podium? = nil
    var now: Date = Date()

    @State private var selectedOutcomeID: Int? = nil
    @State private var heldCohortIDs: [Int]? = nil
    @State private var selectedPodiumPairID: String? = nil
    @State private var moreExpanded: Bool = false
    @State private var browseExpanded: Bool = false
    @State private var selectedSurnameGroup: EventAtlasRacingCards11666.SurnameGroup = .aToF
    @State private var showAboutSheet: Bool = false
    @State private var activeDriverDetails: EventAtlasRacingCards11666.DriverDetailsSheetItem? = nil

    private var host: RacingFieldPageAdapter10868.Host {
        RacingFieldPageAdapter10868.Host(
            now: now,
            cohort: heldCohortIDs
        )
    }

    private var headlineInput: FieldHeadlineInput10868 {
        RacingFieldPageAdapter10868.headline(market, host: host)
    }

    private var outlookInput: FieldOutlookInput10868 {
        EventAtlasRacingCards11666.buildOutlookInput(
            market: market,
            selectedOutcomeID: selectedOutcomeID,
            host: host
        )
    }

    private var chooserInput: FieldChooserInput10868 {
        EventAtlasRacingCards11666.buildChooserInput(
            market: market,
            selectedOutcomeID: selectedOutcomeID,
            moreExpanded: moreExpanded,
            browseExpanded: browseExpanded,
            selectedSurnameGroup: selectedSurnameGroup,
            host: host
        )
    }

    private var podiumCard: RacingWinPodiumAdapter10868.Card? {
        RacingWinPodiumAdapter10868.card(
            race: market,
            podium: podium,
            selected: selectedPodiumPairID,
            host: host
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            // 1. Race Phase Headline Card
            FieldPhaseHeadlinePresentation10868(
                input: headlineInput,
                onAbout: {
                    showAboutSheet = true
                },
                onOpen: { openEvent in
                    selectDriver(ref: openEvent.ref, openDetails: true)
                }
            )
            .padding(16)
            .background(DS.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(DS.border, lineWidth: 0.5)
            )

            // 2. Field Win-Chance Outlook Bars Card
            FieldOutlookBarsPresentation10868(
                input: outlookInput,
                onChoose: { ref in
                    selectDriver(ref: ref, openDetails: false)
                },
                onOpenOriginal: { ref in
                    selectDriver(ref: ref, openDetails: true)
                }
            )
            .padding(16)
            .background(DS.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(DS.border, lineWidth: 0.5)
            )

            // 3. Optional Win & Podium Comparison Card (when podium market + join are present)
            if let podiumCard {
                FieldWinPodiumPresentation10868(
                    input: podiumCard.input,
                    onChoosePair: { pairID in
                        selectedPodiumPairID = pairID
                    },
                    onOpenOriginal: { ref in
                        selectDriver(ref: ref, openDetails: true)
                    },
                    onAbout: {
                        showAboutSheet = true
                    }
                )
                .padding(16)
                .background(DS.cardBg)
                .clipShape(RoundedRectangle(cornerRadius: 12))
                .overlay(
                    RoundedRectangle(cornerRadius: 12)
                        .stroke(DS.border, lineWidth: 0.5)
                )
            }

            // 4. Driver Contender Chooser Card
            FieldContenderChooserPresentation10868(
                input: chooserInput,
                onChoose: { ref in
                    selectDriver(ref: ref, openDetails: false)
                },
                onControl: { control in
                    switch control {
                    case .toggleMore:
                        moreExpanded.toggle()
                    case .toggleBrowse:
                        browseExpanded.toggle()
                    case .chooseGroup(let groupID):
                        if let group = EventAtlasRacingCards11666.SurnameGroup(rawValue: groupID) {
                            selectedSurnameGroup = group
                        }
                    }
                }
            )
            .padding(16)
            .background(DS.cardBg)
            .clipShape(RoundedRectangle(cornerRadius: 12))
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(DS.border, lineWidth: 0.5)
            )
        }
        .sheet(isPresented: $showAboutSheet) {
            let about = RacingFieldPageAdapter10868.raceAbout(market)
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 14) {
                        Text(about.title)
                            .font(.headline)
                            .foregroundStyle(DS.textPrimary)
                        ForEach(Array(about.paragraphs.enumerated()), id: \.offset) { _, paragraph in
                            Text(paragraph)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .padding(20)
                }
                .navigationTitle("About Race")
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { showAboutSheet = false }
                    }
                }
            }
            .presentationDetents([.medium, .large])
        }
        .sheet(item: $activeDriverDetails) { item in
            NavigationStack {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        Text(item.driverName)
                            .font(.title3.weight(.bold))
                            .foregroundStyle(DS.textPrimary)
                        Text(item.marketName)
                            .font(.subheadline)
                            .foregroundStyle(DS.textSecondary)
                        Divider()
                        HStack {
                            Text(item.readingLabel)
                                .font(.subheadline)
                                .foregroundStyle(DS.textSecondary)
                            Spacer()
                            Text(item.readingValue)
                                .font(.body.weight(.semibold))
                                .foregroundStyle(DS.textPrimary)
                        }
                        if let detail = item.readingDetail, !detail.isEmpty {
                            Text(detail)
                                .font(.caption)
                                .foregroundStyle(DS.textMuted)
                        }
                        if let resultWords = item.resultWords, !resultWords.isEmpty {
                            Divider()
                            HStack {
                                Text(RacingFieldPageAdapter10868.Words.resultTitle)
                                    .font(.subheadline)
                                    .foregroundStyle(DS.textSecondary)
                                Spacer()
                                Text(resultWords)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(DS.textPrimary)
                            }
                        }
                    }
                    .padding(20)
                }
                .navigationTitle("Driver Details")
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { activeDriverDetails = nil }
                    }
                }
            }
            .presentationDetents([.medium])
        }
    }

    private func selectDriver(ref: FieldChooserOriginalRef10868, openDetails: Bool) {
        if let outcomeID = Int(ref.outcomeID) {
            selectedOutcomeID = outcomeID
            let defaultTop = Array(market.outcomes.prefix(RacingFieldPageAdapter10868.defaultCohortSize)).map(\.id)
            if !defaultTop.contains(outcomeID) {
                var updated = Array(defaultTop.prefix(max(0, RacingFieldPageAdapter10868.defaultCohortSize - 1)))
                updated.append(outcomeID)
                heldCohortIDs = updated
            }
        }
        if openDetails {
            activeDriverDetails = EventAtlasRacingCards11666.buildDriverDetails(
                ref: ref,
                market: market,
                host: host
            )
        }
    }
}
