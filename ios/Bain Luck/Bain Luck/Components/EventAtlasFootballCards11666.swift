import Charts
import Foundation
import SwiftUI

/// #11666 (Menu Items 12a–c, Decide 91 C) — Native NFL story cards behind
/// `ReleaseSurfaces.isEventPageAtlasEnabled()`:
/// - **12a (`PeriodWinnersCard`)**: Quarter-by-quarter regulation period winners
///   (`Q1`–`Q4`, excluding overtime) with `○` pregame chances, `●` live quotes
///   (aged after 30 minutes to `"No recent probability"`), reported quarter points
///   from `StoredLineScore` (`boxScoreData`), and venue settlement verdicts
///   (`✓ Won`, `✗ Lost`, `"Result not confirmed"`).
/// - **12b (`PairedMilestonesCard`)**: Side-by-side Away vs. Home team count
///   milestone ladders for Team Sacks (`"Pressure on the passer"`) and Team Field
///   Goals (`"The kicking game"`), preserving independent team slots at each
///   threshold without borrowing or flat-ladder fabrication.
/// - **12c (`CombinedYardsCard`)**: `"Rushing + Receiving Yards"` combined
///   milestone ladder paired with the signed Ground + Air yardage split
///   (`AdditiveStatSplit`), preserving negative yardage (e.g. `"−2 yards"`)
///   backward from a zero origin and printing `"Ground and air split unavailable"`
///   / `"Actual so far unavailable"` whenever component actuals are not served.
enum EventAtlasFootballCards11666 {

    /// Live quote freshness window (30 minutes, matching `QuestionCatalog9483.livePriceMaxAge`).
    nonisolated static let liveQuoteMaxAgeSeconds: TimeInterval = 30 * 60

    static func applies(
        sportKey: String?,
        atlasEnabled: Bool = ReleaseSurfaces.isEventPageAtlasEnabled()
    ) -> Bool {
        atlasEnabled && NFLRecognizablePage9483.isNFL(sportKey: sportKey)
    }

    // MARK: - Shared Phase & Verdict Types

    nonisolated enum Phase: String, Equatable, Sendable {
        case before
        case during
        case after

        static func resolve(status: String?, commenceTime: Date?, now: Date) -> Phase {
            if EventState.isFinished(status) {
                return .after
            }
            if status == "live" || status == "in_progress" {
                return .during
            }
            if let commenceTime, now >= commenceTime {
                return .during
            }
            return .before
        }
    }

    nonisolated enum Side: String, CaseIterable, Equatable, Sendable {
        case away
        case home
        case tie
    }

    nonisolated enum Verdict: Equatable, Sendable {
        case won
        case lost
        case unconfirmed
    }

    // MARK: - 12a: Quarter-by-Quarter Period Winners (Q1–Q4)

    nonisolated enum RegulationQuarter: Int, CaseIterable, Equatable, Identifiable, Sendable {
        case q1 = 1
        case q2 = 2
        case q3 = 3
        case q4 = 4

        var id: String { code }

        var code: String {
            switch self {
            case .q1: return "Q1"
            case .q2: return "Q2"
            case .q3: return "Q3"
            case .q4: return "Q4"
            }
        }

        var spokenTitle: String {
            switch self {
            case .q1: return "First quarter"
            case .q2: return "Second quarter"
            case .q3: return "Third quarter"
            case .q4: return "Fourth quarter"
            }
        }
    }

    nonisolated struct PeriodWinnerLeg: Equatable, Identifiable, Sendable {
        let id: String
        let quarter: RegulationQuarter
        let side: Side
        let label: String
        let pregameChance: Double?
        let liveChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: Verdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date, phase: Phase) -> PeriodWinnerLeg {
            guard phase != .after else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasFootballCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard pregameChance != nil else { return self }
                return PeriodWinnerLeg(
                    id: id,
                    quarter: quarter,
                    side: side,
                    label: label,
                    pregameChance: nil,
                    liveChance: nil,
                    observedAt: observedAt,
                    isStaleLive: isStaleLive,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .during:
                guard liveChance != nil || !isStaleLive else { return self }
                return PeriodWinnerLeg(
                    id: id,
                    quarter: quarter,
                    side: side,
                    label: label,
                    pregameChance: pregameChance,
                    liveChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .after:
                return self
            }
        }
    }

    nonisolated struct QuarterWinnerPanel: Equatable, Identifiable, Sendable {
        var id: String { quarter.id }
        let quarter: RegulationQuarter
        let awayScore: Int?
        let homeScore: Int?
        let legs: [PeriodWinnerLeg]

        func current(at now: Date, phase: Phase) -> QuarterWinnerPanel {
            QuarterWinnerPanel(
                quarter: quarter,
                awayScore: awayScore,
                homeScore: homeScore,
                legs: legs.map { $0.current(at: now, phase: phase) }
            )
        }
    }

    nonisolated struct PeriodWinnersCard: Equatable, Identifiable, Sendable {
        static let cardID = "nfl:period-winners"
        var id: String { Self.cardID }
        var title: String { "Quarter by quarter" }
        let eyebrow: String
        let subtitle: String
        let phase: Phase
        let awayShort: String
        let homeShort: String
        let panels: [QuarterWinnerPanel]

        func current(at now: Date) -> PeriodWinnersCard {
            PeriodWinnersCard(
                eyebrow: eyebrow,
                subtitle: subtitle,
                phase: phase,
                awayShort: awayShort,
                homeShort: homeShort,
                panels: panels.map { $0.current(at: now, phase: phase) }
            )
        }
    }

    // MARK: - 12b: Paired Team Count Milestones (Team Sacks & Team Field Goals)

    nonisolated enum TeamStatFamily: String, CaseIterable, Equatable, Identifiable, Sendable {
        case sacks = "sacks"
        case fieldGoals = "field-goals"

        var id: String { rawValue }

        var cardID: String { "nfl:paired-milestones:\(rawValue)" }

        var eyebrow: String {
            switch self {
            case .sacks: return "TEAM SACKS"
            case .fieldGoals: return "TEAM FIELD GOALS"
            }
        }

        var title: String {
            switch self {
            case .sacks: return "Pressure on the passer"
            case .fieldGoals: return "The kicking game"
            }
        }

        var statWords: String {
            switch self {
            case .sacks: return "Team Sacks"
            case .fieldGoals: return "Team Field Goals"
            }
        }

        var unitPlural: String {
            switch self {
            case .sacks: return "sacks"
            case .fieldGoals: return "field goals"
            }
        }

        var unitSingular: String {
            switch self {
            case .sacks: return "sack"
            case .fieldGoals: return "field goal"
            }
        }

        func formatCount(_ value: Double) -> String {
            let rounded = Int(value.rounded())
            let word = rounded == 1 ? unitSingular : unitPlural
            return "\(rounded) \(word)"
        }
    }

    nonisolated struct TeamMilestoneSlot: Equatable, Identifiable, Sendable {
        let id: String
        let side: Side
        let teamLabel: String
        let threshold: Int
        let targetLabel: String
        let pregameChance: Double?
        let liveChance: Double?
        let observedAt: Date?
        let isStaleLive: Bool
        let verdict: Verdict?
        let rawSource: String?
        let sourceCount: Int

        func current(at now: Date, phase: Phase) -> TeamMilestoneSlot {
            guard phase != .after else { return self }
            let isStale: Bool = {
                guard let observedAt else { return true }
                return now.timeIntervalSince(observedAt) > EventAtlasFootballCards11666.liveQuoteMaxAgeSeconds
            }()
            guard isStale else { return self }
            switch phase {
            case .before:
                guard pregameChance != nil else { return self }
                return TeamMilestoneSlot(
                    id: id,
                    side: side,
                    teamLabel: teamLabel,
                    threshold: threshold,
                    targetLabel: targetLabel,
                    pregameChance: nil,
                    liveChance: nil,
                    observedAt: observedAt,
                    isStaleLive: isStaleLive,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .during:
                guard liveChance != nil || !isStaleLive else { return self }
                return TeamMilestoneSlot(
                    id: id,
                    side: side,
                    teamLabel: teamLabel,
                    threshold: threshold,
                    targetLabel: targetLabel,
                    pregameChance: pregameChance,
                    liveChance: nil,
                    observedAt: observedAt,
                    isStaleLive: true,
                    verdict: verdict,
                    rawSource: rawSource,
                    sourceCount: sourceCount
                )
            case .after:
                return self
            }
        }
    }

    nonisolated struct PairedMilestoneGroup: Equatable, Identifiable, Sendable {
        var id: String { "threshold-\(threshold)" }
        let threshold: Int
        let targetLabel: String
        let away: TeamMilestoneSlot?
        let home: TeamMilestoneSlot?

        func current(at now: Date, phase: Phase) -> PairedMilestoneGroup {
            PairedMilestoneGroup(
                threshold: threshold,
                targetLabel: targetLabel,
                away: away?.current(at: now, phase: phase),
                home: home?.current(at: now, phase: phase)
            )
        }
    }

    nonisolated struct PairedMilestonesCard: Equatable, Identifiable, Sendable {
        let family: TeamStatFamily
        var id: String { family.cardID }
        var title: String { family.title }
        var eyebrow: String { family.eyebrow }
        let phase: Phase
        let awayShort: String
        let homeShort: String
        let awayActual: Double?
        let homeActual: Double?
        let groups: [PairedMilestoneGroup]

        func current(at now: Date) -> PairedMilestonesCard {
            PairedMilestonesCard(
                family: family,
                phase: phase,
                awayShort: awayShort,
                homeShort: homeShort,
                awayActual: awayActual,
                homeActual: homeActual,
                groups: groups.map { $0.current(at: now, phase: phase) }
            )
        }
    }

    // MARK: - 12c: Combined Ground + Air Yards (Rushing + Receiving Yards)

    nonisolated struct SignedYardageSpan: Equatable, Sendable {
        let start: Double
        let end: Double
    }

    nonisolated struct SignedYardageComponent: Equatable, Identifiable, Sendable {
        let id: String
        let label: String
        let yards: Double
        let formattedYards: String
        let span: SignedYardageSpan
        let isPrimary: Bool
    }

    nonisolated enum YardageSplitState: Equatable, Sendable {
        case hiddenBeforePlay
        case absent(String)
        case totalOnly(totalYards: Double, formattedTotal: String, splitUnavailableMessage: String)
        case decomposed(
            totalYards: Double,
            formattedTotal: String,
            ground: SignedYardageComponent,
            air: SignedYardageComponent
        )
    }

    struct CombinedYardsCard: Equatable, Identifiable {
        var id: String { "nfl:combined-yards:\(milestone.id)" }
        var title: String { "\(milestone.player) · Rushing + Receiving Yards" }
        let eyebrow: String
        let phase: Phase
        let milestone: NFLMilestoneCard9483
        let splitState: YardageSplitState
        let axisDomain: ClosedRange<Double>

        func current(at now: Date) -> CombinedYardsCard {
            CombinedYardsCard(
                eyebrow: eyebrow,
                phase: phase,
                milestone: milestone.current(at: now),
                splitState: splitState,
                axisDomain: axisDomain
            )
        }
    }

    // MARK: - Formatting Helpers

    static func formatSignedYards(_ yards: Double) -> String {
        let rounded = Int(yards.rounded())
        let unit = abs(rounded) == 1 ? "yard" : "yards"
        if rounded < 0 {
            return "−\(abs(rounded)) \(unit)"
        }
        return "\(rounded) \(unit)"
    }

    static func verdictBadgeText(_ verdict: Verdict) -> String {
        switch verdict {
        case .won:
            return EventAtlasStates11666.wonWithCheck
        case .lost:
            return EventAtlasStates11666.lostWithCross
        case .unconfirmed:
            return "Result not confirmed"
        }
    }

    static func milestoneVerdictBadgeText(_ verdict: Verdict) -> String {
        switch verdict {
        case .won:
            return "✓ HIT"
        case .lost:
            return "✗ MISS"
        case .unconfirmed:
            return "Result not confirmed"
        }
    }

    // MARK: - Quarter Parsing & Side Matching (12a)

    static func parseRegulationQuarter(period: String?, marketName: String) -> RegulationQuarter? {
        let p = (period ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let m = marketName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

        // Explicitly reject overtime or half markets.
        let combined = "\(p) \(m)"
        if combined.contains("overtime") || combined.contains("ot ") || combined.hasSuffix(" ot")
            || combined.contains("half") || combined.contains("1h") || combined.contains("2h") {
            return nil
        }

        if p == "q1" || p == "1q" || p == "1st quarter" || p == "first quarter" {
            return .q1
        }
        if p == "q2" || p == "2q" || p == "2nd quarter" || p == "second quarter" {
            return .q2
        }
        if p == "q3" || p == "3q" || p == "3rd quarter" || p == "third quarter" {
            return .q3
        }
        if p == "q4" || p == "4q" || p == "4th quarter" || p == "fourth quarter" {
            return .q4
        }

        if m.contains("1st quarter") || m.contains("first quarter") || m.contains("q1 ") || m.hasPrefix("q1") {
            return .q1
        }
        if m.contains("2nd quarter") || m.contains("second quarter") || m.contains("q2 ") || m.hasPrefix("q2") {
            return .q2
        }
        if m.contains("3rd quarter") || m.contains("third quarter") || m.contains("q3 ") || m.hasPrefix("q3") {
            return .q3
        }
        if m.contains("4th quarter") || m.contains("fourth quarter") || m.contains("q4 ") || m.hasPrefix("q4") {
            return .q4
        }
        return nil
    }

    static func isQuarterWinnerMarket(marketType: String?, marketName: String, threshold: Double?) -> Bool {
        if threshold != nil { return false }
        let mType = (marketType ?? "").trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if mType == "spread" || mType == "spreads" || mType == "total" || mType == "totals" || mType == "team_total" {
            return false
        }
        let lower = marketName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if lower.contains("spread") || lower.contains("total") || lower.contains("over/under")
            || lower.contains("points") || lower.contains("handicap") || lower.contains("margin") {
            return false
        }
        if mType == "moneyline" || mType == "h2h" || mType == "three_way" || mType == "winner" {
            return true
        }
        return lower.contains("winner") || lower.contains("moneyline") || lower.contains("3-way")
            || lower.contains("three-way") || lower.contains("result")
    }

    private static let nflTeamAbbrevKeywords: [String: [String]] = [
        "ari": ["arizona", "cardinals"],
        "atl": ["atlanta", "falcons"],
        "bal": ["baltimore", "ravens"],
        "buf": ["buffalo", "bills"],
        "car": ["carolina", "panthers"],
        "chi": ["chicago", "bears"],
        "cin": ["cincinnati", "bengals"],
        "cle": ["cleveland", "browns"],
        "dal": ["dallas", "cowboys"],
        "den": ["denver", "broncos"],
        "det": ["detroit", "lions"],
        "gb": ["green bay", "packers"],
        "hou": ["houston", "texans"],
        "ind": ["indianapolis", "colts"],
        "jax": ["jacksonville", "jaguars"],
        "kc": ["kansas city", "chiefs"],
        "lac": ["los angeles chargers", "chargers"],
        "lar": ["los angeles rams", "rams"],
        "lv": ["las vegas", "raiders"],
        "mia": ["miami", "dolphins"],
        "min": ["minnesota", "vikings"],
        "ne": ["new england", "patriots"],
        "no": ["new orleans", "saints"],
        "nyg": ["new york giants", "giants"],
        "nyj": ["new york jets", "jets"],
        "phi": ["philadelphia", "eagles"],
        "pit": ["pittsburgh", "steelers"],
        "sea": ["seattle", "seahawks"],
        "sf": ["san francisco", "49ers", "niners"],
        "tb": ["tampa bay", "buccaneers", "bucs"],
        "ten": ["tennessee", "titans"],
        "was": ["washington", "commanders"]
    ]

    static func matchSide(
        outcomeName: String,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> Side? {
        let trimmed = outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        let lower = trimmed.lowercased()
        if lower == "tie" || lower == "draw" || lower == "no winner" || lower == "tied" {
            return .tie
        }
        let hFull = homeTeam.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let aFull = awayTeam.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let hShort = homeShort.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        let aShort = awayShort.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

        if !hFull.isEmpty && (lower == hFull || lower.contains(hFull) || hFull.contains(lower)) {
            if !aFull.isEmpty && (lower == aFull || lower.contains(aFull)) { return nil }
            return .home
        }
        if !aFull.isEmpty && (lower == aFull || lower.contains(aFull) || aFull.contains(lower)) {
            return .away
        }
        if !hShort.isEmpty && (lower == hShort || lower.contains(hShort)) {
            return .home
        }
        if !aShort.isEmpty && (lower == aShort || lower.contains(aShort)) {
            return .away
        }
        if let keywords = nflTeamAbbrevKeywords[lower] {
            if keywords.contains(where: { hFull.contains($0) || hShort.contains($0) }) {
                return .home
            }
            if keywords.contains(where: { aFull.contains($0) || aShort.contains($0) }) {
                return .away
            }
        }
        return nil
    }

    // MARK: - Build 12a: Period Winners Card

    static func buildPeriodWinnersCard(
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        homeScore: Int?,
        awayScore: Int?,
        boxScoreData: EventBoxScoreData?,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date()
    ) -> PeriodWinnersCard? {
        guard let gm = gameMarkets else { return nil }
        let phase = Phase.resolve(status: status, commenceTime: commenceTime, now: now)

        struct RawQuarterOutcome {
            let quarter: RegulationQuarter
            let side: Side
            let probability: Double?
            let pregameMark: Double?
            let observedAt: Date?
            let isWinner: Bool?
            let resolutionSource: String?
            let source: String?
        }

        var rawByQuarterAndSide: [RegulationQuarter: [Side: [RawQuarterOutcome]]] = [:]

        func appendRaw(_ item: RawQuarterOutcome) {
            rawByQuarterAndSide[item.quarter, default: [:]][item.side, default: []].append(item)
        }

        for row in gm.periodMarkets ?? [] {
            guard row._inverted != true,
                  let quarter = parseRegulationQuarter(period: row.period, marketName: row.marketName),
                  isQuarterWinnerMarket(marketType: row.marketType, marketName: row.marketName, threshold: row.threshold),
                  let side = matchSide(
                      outcomeName: row.outcomeName,
                      homeTeam: homeTeam,
                      awayTeam: awayTeam,
                      homeShort: homeShort,
                      awayShort: awayShort
                  ) else {
                continue
            }
            appendRaw(
                RawQuarterOutcome(
                    quarter: quarter,
                    side: side,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    source: row.source
                )
            )
        }

        for closed in gm.closedPeriodMarkets ?? [] {
            let row = closed.row
            guard row._inverted != true,
                  let quarter = parseRegulationQuarter(period: row.period, marketName: row.marketName),
                  isQuarterWinnerMarket(marketType: row.marketType, marketName: row.marketName, threshold: row.threshold),
                  let side = matchSide(
                      outcomeName: row.outcomeName,
                      homeTeam: homeTeam,
                      awayTeam: awayTeam,
                      homeShort: homeShort,
                      awayShort: awayShort
                  ) else {
                continue
            }
            appendRaw(
                RawQuarterOutcome(
                    quarter: quarter,
                    side: side,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    source: row.source
                )
            )
        }

        for row in gm.other ?? [] {
            guard let quarter = parseRegulationQuarter(period: nil, marketName: row.marketName),
                  isQuarterWinnerMarket(marketType: nil, marketName: row.marketName, threshold: nil),
                  let side = matchSide(
                      outcomeName: row.outcomeName,
                      homeTeam: homeTeam,
                      awayTeam: awayTeam,
                      homeShort: homeShort,
                      awayShort: awayShort
                  ) else {
                continue
            }
            appendRaw(
                RawQuarterOutcome(
                    quarter: quarter,
                    side: side,
                    probability: row.probability,
                    pregameMark: row.pregameMark,
                    observedAt: row.observedAt?.asDate,
                    isWinner: row.isWinner,
                    resolutionSource: row.resolutionSource,
                    source: row.source
                )
            )
        }

        guard !rawByQuarterAndSide.isEmpty else { return nil }

        let lineScoreColumns = StoredLineScore.columns(
            homePeriods: boxScoreData?.homePeriodScores,
            awayPeriods: boxScoreData?.awayPeriodScores,
            sportKey: "americanfootball_nfl",
            homeTotal: homeScore,
            awayTotal: awayScore,
            isFinished: phase == .after
        )

        var panels: [QuarterWinnerPanel] = []
        for quarter in RegulationQuarter.allCases {
            guard let sideMap = rawByQuarterAndSide[quarter], !sideMap.isEmpty else { continue }
            let col = lineScoreColumns?.first(where: { $0.label.uppercased() == quarter.code })
            let qAwayScore = col?.away.points
            let qHomeScore = col?.home.points

            var legs: [PeriodWinnerLeg] = []
            for side in [Side.away, .home, .tie] {
                guard let candidates = sideMap[side], !candidates.isEmpty else { continue }
                let first = candidates[0]
                let distinctSources = Set(
                    candidates.compactMap { $0.source?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                        .filter { !$0.isEmpty }
                )
                let sourceCount = max(1, distinctSources.count)
                let rawSource = sourceCount > 1 ? nil : first.source

                let pregameChance: Double? = {
                    switch phase {
                    case .before:
                        guard let obs = first.observedAt,
                              now.timeIntervalSince(obs) <= liveQuoteMaxAgeSeconds else {
                            return nil
                        }
                        return first.probability.flatMap { ($0 > 0 && $0 < 1) ? $0 : nil }
                    case .during, .after:
                        return first.pregameMark.flatMap { ($0 > 0 && $0 < 1) ? $0 : nil }
                    }
                }()

                let (liveChance, isStaleLive): (Double?, Bool) = {
                    guard phase == .during else { return (nil, false) }
                    guard let prob = first.probability, prob >= 0, prob <= 1 else {
                        return (nil, first.observedAt != nil)
                    }
                    if let obs = first.observedAt,
                       now.timeIntervalSince(obs) > liveQuoteMaxAgeSeconds {
                        return (nil, true)
                    }
                    return (prob, false)
                }()

                let verdict: Verdict? = {
                    guard phase == .after else { return nil }
                    let v = OutcomeVerdict.verdict(
                        isWinner: first.isWinner,
                        resolutionSource: first.resolutionSource,
                        marketResolved: false
                    )
                    return v == .won ? .won : .unconfirmed
                }()

                let label: String = {
                    switch side {
                    case .away: return awayShort
                    case .home: return homeShort
                    case .tie: return "Tie"
                    }
                }()

                legs.append(
                    PeriodWinnerLeg(
                        id: "nfl:period-winner:\(quarter.code.lowercased()):\(side.rawValue)",
                        quarter: quarter,
                        side: side,
                        label: label,
                        pregameChance: pregameChance,
                        liveChance: liveChance,
                        observedAt: first.observedAt,
                        isStaleLive: isStaleLive,
                        verdict: verdict,
                        rawSource: rawSource,
                        sourceCount: sourceCount
                    )
                )
            }

            if !legs.isEmpty {
                panels.append(
                    QuarterWinnerPanel(
                        quarter: quarter,
                        awayScore: qAwayScore,
                        homeScore: qHomeScore,
                        legs: legs
                    )
                )
            }
        }

        guard !panels.isEmpty else { return nil }
        return PeriodWinnersCard(
            eyebrow: "PERIOD WINNERS",
            subtitle: "Regulation quarters (Q1–Q4); overtime excluded",
            phase: phase,
            awayShort: awayShort,
            homeShort: homeShort,
            panels: panels
        )
    }

    // MARK: - Build 12b: Paired Team Count Milestones (Team Sacks & Team Field Goals)

    static func classifyTeamStatFamily(marketName: String) -> TeamStatFamily? {
        let lower = marketName.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if lower.contains("team sack") || (lower.contains("sacks") && lower.contains("team")) {
            return .sacks
        }
        if lower.contains("team field goal") || (lower.contains("field goals") && lower.contains("team")) {
            return .fieldGoals
        }
        return nil
    }

    static func parseTeamMilestoneOutcome(
        prop: GameMarketPlayerProp,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String
    ) -> (side: Side, threshold: Int)? {
        guard prop._inverted != true else { return nil }
        let outcome = prop.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        let lowerOutcome = outcome.lowercased()
        if lowerOutcome.contains("under") { return nil }

        // Outcome format is typically "Philadelphia Eagles: 3+" or "Eagles Over 2.5"
        var subjectPart = outcome
        var parsedThreshold: Int?
        if let colonRange = outcome.range(of: ":") {
            subjectPart = String(outcome[..<colonRange.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            let rhs = String(outcome[colonRange.upperBound...]).trimmingCharacters(in: .whitespacesAndNewlines)
            let digits = rhs.replacingOccurrences(of: "+", with: "").trimmingCharacters(in: .whitespacesAndNewlines)
            if let intVal = Int(digits), intVal > 0 {
                parsedThreshold = intVal
            }
        }
        if parsedThreshold == nil, let rawThresh = prop.threshold, rawThresh > 0 {
            // Convert Over 2.5 -> 3+, or integer 3.0 -> 3+
            let roundedUp = rawThresh.rounded(.up)
            let intVal = (rawThresh.truncatingRemainder(dividingBy: 1) == 0) ? Int(rawThresh) : Int(roundedUp)
            if intVal > 0 {
                parsedThreshold = intVal
            }
        }
        guard let threshold = parsedThreshold else { return nil }

        let sideCandidate = prop.playerTeam?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty == false
            ? prop.playerTeam!
            : subjectPart
        guard let side = matchSide(
            outcomeName: sideCandidate,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort
        ), side == .away || side == .home else {
            return nil
        }
        return (side, threshold)
    }

    /// Rejects degenerate flat ladders (#5137: 3+ rungs with identical probabilities).
    private static func isFlatLadder(_ values: [Double]) -> Bool {
        guard values.count >= 3, let first = values.first else { return false }
        return values.allSatisfy { abs($0 - first) < 0.0005 }
    }

    static func buildPairedMilestonesCard(
        family: TeamStatFamily,
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date()
    ) -> PairedMilestonesCard? {
        guard let props = gameMarkets?.playerProps, !props.isEmpty else { return nil }
        let phase = Phase.resolve(status: status, commenceTime: commenceTime, now: now)

        var awayByThreshold: [Int: [GameMarketPlayerProp]] = [:]
        var homeByThreshold: [Int: [GameMarketPlayerProp]] = [:]

        for prop in props {
            guard classifyTeamStatFamily(marketName: prop.marketName) == family,
                  let (side, threshold) = parseTeamMilestoneOutcome(
                      prop: prop,
                      homeTeam: homeTeam,
                      awayTeam: awayTeam,
                      homeShort: homeShort,
                      awayShort: awayShort
                  ) else {
                continue
            }
            if side == .away {
                awayByThreshold[threshold, default: []].append(prop)
            } else if side == .home {
                homeByThreshold[threshold, default: []].append(prop)
            }
        }

        // Require at least one rung on each side so the card is genuinely paired.
        guard !awayByThreshold.isEmpty, !homeByThreshold.isEmpty else { return nil }

        func buildSlot(
            side: Side,
            threshold: Int,
            candidates: [GameMarketPlayerProp]?
        ) -> (slot: TeamMilestoneSlot?, actual: Double?) {
            guard let candidates, let first = candidates.first else { return (nil, nil) }
            let distinctSources = Set(
                candidates.compactMap { $0.source?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() }
                    .filter { !$0.isEmpty }
            )
            let sourceCount = max(1, distinctSources.count)
            let rawSource = sourceCount > 1 ? nil : first.source

            let pregameChance: Double? = {
                switch phase {
                case .before:
                    guard NFLMilestoneCard9483.isRecent(first.observedAt, now: now) else {
                        return nil
                    }
                    return first.overProbability.flatMap { ($0 > 0 && $0 < 1) ? $0 : nil }
                case .during, .after:
                    return first.pregameMark.flatMap { ($0 > 0 && $0 < 1) ? $0 : nil }
                }
            }()

            let observedAt = first.observedAt?.asDate
            let (liveChance, isStaleLive): (Double?, Bool) = {
                guard phase == .during else { return (nil, false) }
                guard let prob = first.overProbability, prob >= 0, prob <= 1 else {
                    return (nil, observedAt != nil)
                }
                if let obs = observedAt, now.timeIntervalSince(obs) > liveQuoteMaxAgeSeconds {
                    return (nil, true)
                }
                return (prob, false)
            }()

            let verdict: Verdict? = {
                guard phase == .after else { return nil }
                let settlementVerdict = OutcomeVerdict.verdict(
                    isWinner: first.isWinner,
                    resolutionSource: first.resolutionSource,
                    marketResolved: false
                )
                if first.resolutionSource != nil || first.isWinner != nil {
                    return settlementVerdict == .won ? .won : .unconfirmed
                }
                if let hit = first.hit {
                    return hit ? .won : .lost
                }
                return .unconfirmed
            }()

            let teamLabel = side == .away ? awayShort : homeShort
            let targetLabel = "\(threshold)+"
            let slot = TeamMilestoneSlot(
                id: "\(family.cardID):\(side.rawValue):\(threshold)",
                side: side,
                teamLabel: teamLabel,
                threshold: threshold,
                targetLabel: targetLabel,
                pregameChance: pregameChance,
                liveChance: liveChance,
                observedAt: observedAt,
                isStaleLive: isStaleLive,
                verdict: verdict,
                rawSource: rawSource,
                sourceCount: sourceCount
            )
            return (slot, first.actual)
        }

        let allThresholds = Set(awayByThreshold.keys).union(homeByThreshold.keys).sorted()
        var rawGroups: [PairedMilestoneGroup] = []
        var awayActual: Double?
        var homeActual: Double?

        for threshold in allThresholds {
            let awayBuilt = buildSlot(side: .away, threshold: threshold, candidates: awayByThreshold[threshold])
            let homeBuilt = buildSlot(side: .home, threshold: threshold, candidates: homeByThreshold[threshold])
            if let a = awayBuilt.actual, awayActual == nil { awayActual = a }
            if let h = homeBuilt.actual, homeActual == nil { homeActual = h }
            rawGroups.append(
                PairedMilestoneGroup(
                    threshold: threshold,
                    targetLabel: "\(threshold)+",
                    away: awayBuilt.slot,
                    home: homeBuilt.slot
                )
            )
        }

        // Refuse flat ladders (#5137) per side: if a side's pregame chances are flat across 3+ rungs, null them out.
        let awayPregames = rawGroups.compactMap { $0.away?.pregameChance }
        let homePregames = rawGroups.compactMap { $0.home?.pregameChance }
        let awayFlat = isFlatLadder(awayPregames)
        let homeFlat = isFlatLadder(homePregames)

        let sanitizedGroups: [PairedMilestoneGroup] = rawGroups.compactMap { group in
            let awaySlot: TeamMilestoneSlot? = group.away.map { slot in
                guard awayFlat else { return slot }
                return TeamMilestoneSlot(
                    id: slot.id,
                    side: slot.side,
                    teamLabel: slot.teamLabel,
                    threshold: slot.threshold,
                    targetLabel: slot.targetLabel,
                    pregameChance: nil,
                    liveChance: slot.liveChance,
                    observedAt: slot.observedAt,
                    isStaleLive: slot.isStaleLive,
                    verdict: slot.verdict,
                    rawSource: slot.rawSource,
                    sourceCount: slot.sourceCount
                )
            }
            let homeSlot: TeamMilestoneSlot? = group.home.map { slot in
                guard homeFlat else { return slot }
                return TeamMilestoneSlot(
                    id: slot.id,
                    side: slot.side,
                    teamLabel: slot.teamLabel,
                    threshold: slot.threshold,
                    targetLabel: slot.targetLabel,
                    pregameChance: nil,
                    liveChance: slot.liveChance,
                    observedAt: slot.observedAt,
                    isStaleLive: slot.isStaleLive,
                    verdict: slot.verdict,
                    rawSource: slot.rawSource,
                    sourceCount: slot.sourceCount
                )
            }
            guard awaySlot != nil || homeSlot != nil else { return nil }
            return PairedMilestoneGroup(
                threshold: group.threshold,
                targetLabel: group.targetLabel,
                away: awaySlot,
                home: homeSlot
            )
        }

        guard !sanitizedGroups.isEmpty else { return nil }
        return PairedMilestonesCard(
            family: family,
            phase: phase,
            awayShort: awayShort,
            homeShort: homeShort,
            awayActual: phase == .before ? nil : awayActual,
            homeActual: phase == .before ? nil : homeActual,
            groups: sanitizedGroups
        )
    }

    // MARK: - Build 12c: Combined Ground + Air Yards Card

    static func isCombinedYardsStat(_ statLabel: String) -> Bool {
        let lower = statLabel.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        return lower == "rushing + receiving yards"
            || lower == "rush + rec yards"
            || lower == "rushing & receiving yards"
            || lower == "combined rushing and receiving yards"
    }

    static func extractPlayerSubject(from prop: GameMarketPlayerProp) -> String? {
        let outcome = prop.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
        if let colon = outcome.range(of: ":") {
            let name = String(outcome[..<colon.lowerBound]).trimmingCharacters(in: .whitespacesAndNewlines)
            if !name.isEmpty { return name }
        }
        return nil
    }

    static func buildCombinedYardsCards(
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date()
    ) -> [CombinedYardsCard] {
        guard let props = gameMarkets?.playerProps, !props.isEmpty else { return [] }
        let phase = Phase.resolve(status: status, commenceTime: commenceTime, now: now)

        let combinedProps = props.filter { prop in
            let subject = extractPlayerSubject(from: prop) ?? ""
            let label = PlayerPropsStatLabel.display(
                marketName: prop.marketName,
                homeTeam: homeTeam,
                awayTeam: awayTeam,
                player: subject
            )
            let familyName = PlayerPropsFamily.name(statLabel: label)
            return isCombinedYardsStat(familyName) || isCombinedYardsStat(label)
        }
        guard !combinedProps.isEmpty else { return [] }

        let milestoneCards = NFLMilestoneCard9483.cards(
            props: combinedProps,
            eventStatus: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            now: now
        ).map { $0.current(at: now) }

        // Look up served component actuals (Rushing Yards & Receiving Yards) for each player when present.
        func componentActuals(for player: String) -> (rushing: Double?, receiving: Double?) {
            var rushing: Double?
            var receiving: Double?
            let normalizedPlayer = player.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            for prop in props {
                guard let actual = prop.actual, actual.isFinite,
                      let subj = extractPlayerSubject(from: prop),
                      subj.lowercased() == normalizedPlayer else {
                    continue
                }
                let label = PlayerPropsStatLabel.display(
                    marketName: prop.marketName,
                    homeTeam: homeTeam,
                    awayTeam: awayTeam,
                    player: subj
                )
                let family = PlayerPropsFamily.name(statLabel: label).lowercased()
                if family == "rushing yards" && rushing == nil {
                    rushing = actual
                } else if family == "receiving yards" && receiving == nil {
                    receiving = actual
                }
            }
            return (rushing, receiving)
        }

        return milestoneCards.map { card in
            let comps = componentActuals(for: card.player)
            return makeCombinedYardsCard(
                milestone: card,
                phase: phase,
                rushingActual: comps.rushing,
                receivingActual: comps.receiving
            )
        }
    }

    static func makeCombinedYardsCard(
        milestone: NFLMilestoneCard9483,
        phase: Phase,
        rushingActual: Double? = nil,
        receivingActual: Double? = nil
    ) -> CombinedYardsCard {
        let thresholds = milestone.rungs.map(\.threshold)
        let baseMin = min(0, thresholds.min() ?? 0)
        let baseMax = max(25, thresholds.max() ?? 100)

        let splitState: YardageSplitState
        var extraPoints: [Double] = [0]

        switch phase {
        case .before:
            splitState = .hiddenBeforePlay
        case .during:
            if let total = milestone.actual, total.isFinite {
                extraPoints.append(total)
                if let rush = rushingActual, let rec = receivingActual,
                   rush.isFinite, rec.isFinite,
                   abs((rush + rec) - total) < 0.01 {
                    extraPoints.append(contentsOf: [rush, rec])
                    let groundComp = SignedYardageComponent(
                        id: "ground",
                        label: "Ground (Rushing)",
                        yards: rush,
                        formattedYards: formatSignedYards(rush),
                        span: SignedYardageSpan(start: 0, end: rush),
                        isPrimary: true
                    )
                    let airComp = SignedYardageComponent(
                        id: "air",
                        label: "Air (Receiving)",
                        yards: rec,
                        formattedYards: formatSignedYards(rec),
                        span: SignedYardageSpan(start: rush, end: rush + rec),
                        isPrimary: false
                    )
                    splitState = .decomposed(
                        totalYards: total,
                        formattedTotal: formatSignedYards(total),
                        ground: groundComp,
                        air: airComp
                    )
                } else {
                    splitState = .totalOnly(
                        totalYards: total,
                        formattedTotal: formatSignedYards(total),
                        splitUnavailableMessage: "Ground and air split unavailable"
                    )
                }
            } else {
                splitState = .absent("Actual so far unavailable")
            }
        case .after:
            if let total = milestone.actual, total.isFinite {
                extraPoints.append(total)
                if let rush = rushingActual, let rec = receivingActual,
                   rush.isFinite, rec.isFinite,
                   abs((rush + rec) - total) < 0.01 {
                    extraPoints.append(contentsOf: [rush, rec])
                    let groundComp = SignedYardageComponent(
                        id: "ground",
                        label: "Ground (Rushing)",
                        yards: rush,
                        formattedYards: formatSignedYards(rush),
                        span: SignedYardageSpan(start: 0, end: rush),
                        isPrimary: true
                    )
                    let airComp = SignedYardageComponent(
                        id: "air",
                        label: "Air (Receiving)",
                        yards: rec,
                        formattedYards: formatSignedYards(rec),
                        span: SignedYardageSpan(start: rush, end: rush + rec),
                        isPrimary: false
                    )
                    splitState = .decomposed(
                        totalYards: total,
                        formattedTotal: formatSignedYards(total),
                        ground: groundComp,
                        air: airComp
                    )
                } else {
                    splitState = .totalOnly(
                        totalYards: total,
                        formattedTotal: formatSignedYards(total),
                        splitUnavailableMessage: "Ground and air split unavailable"
                    )
                }
            } else {
                splitState = .absent("Final actual unavailable")
            }
        }

        let lowerBound = min(baseMin, extraPoints.min() ?? 0)
        let upperBound = max(baseMax, (extraPoints.max() ?? baseMax) + 10)
        let paddedLower = lowerBound < 0 ? lowerBound - 5 : 0

        return CombinedYardsCard(
            eyebrow: "COMBINED YARDS",
            phase: phase,
            milestone: milestone,
            splitState: splitState,
            axisDomain: paddedLower...upperBound
        )
    }

    // MARK: - Mark Keys & Details Sheet Models

    static func periodWinnersMarkKey(
        for card: PeriodWinnersCard
    ) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        var items: [EventAtlasStoryCards11666.MarkKeyItem11666] = [
            .init(glyph: .hollowCircle, label: "Pregame")
        ]
        if card.phase == .during {
            items.append(.init(glyph: .filledCircle, label: "Live"))
        }
        if card.phase == .after || card.panels.contains(where: { $0.legs.contains { $0.verdict != nil } }) {
            items.append(.init(glyph: .hitMissVerdict, label: "✓ Won / ✗ Lost"))
        }
        return items
    }

    static func pairedMilestonesMarkKey(
        for card: PairedMilestonesCard
    ) -> [EventAtlasStoryCards11666.MarkKeyItem11666] {
        var items: [EventAtlasStoryCards11666.MarkKeyItem11666] = [
            .init(glyph: .hollowCircle, label: "Pregame")
        ]
        if card.phase == .during {
            items.append(.init(glyph: .filledCircle, label: "Live"))
        }
        if card.awayActual != nil || card.homeActual != nil {
            items.append(.init(glyph: .verticalBar, label: card.phase == .after ? "Actual final" : "Actual so far"))
        }
        if card.phase == .after {
            items.append(.init(glyph: .hitMissVerdict, label: "✓ HIT / ✗ MISS"))
        }
        return items
    }

    static func detailsModel(
        for leg: PeriodWinnerLeg,
        panel: QuarterWinnerPanel,
        card: PeriodWinnersCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let attribution: String? = {
            if leg.sourceCount > 1, leg.rawSource == nil {
                return "\(leg.sourceCount) sources, not blended"
            }
            return EventAtlasHeadline11666.sourceAttribution(
                source: leg.rawSource,
                sourceCount: leg.sourceCount
            )
        }()
        let pregameText = card.phase == .before ? nil : leg.pregameChance.map { formatProbability($0) }
        let primaryLabel: String
        let primaryValue: String
        if let verdict = leg.verdict {
            primaryLabel = "Result"
            var text = verdictBadgeText(verdict)
            if let away = panel.awayScore, let home = panel.homeScore {
                text += " · \(card.awayShort) \(away) – \(home) \(card.homeShort)"
            }
            primaryValue = text
        } else if let live = leg.liveChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(live)
        } else if leg.isStaleLive {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        } else if card.phase == .before, let pre = leg.pregameChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(pre)
        } else if let pregameText {
            primaryLabel = "Pregame baseline"
            primaryValue = pregameText
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = leg.observedAt.map { EventAtlasChartMarks11666.formatExactTimestampPT($0) }
        return EventAtlasDetailsSheetModel11666(
            id: leg.id,
            outcomeTitle: "\(panel.quarter.spokenTitle) · \(leg.label)",
            marketTitle: "\(card.awayShort) at \(card.homeShort) · \(card.title)",
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: EventAtlasStates11666.independentChancesLabel,
            sourceLabel: attribution
        )
    }

    static func detailsModel(
        for slot: TeamMilestoneSlot,
        card: PairedMilestonesCard
    ) -> EventAtlasDetailsSheetModel11666 {
        let attribution: String? = {
            if slot.sourceCount > 1, slot.rawSource == nil {
                return "\(slot.sourceCount) sources, not blended"
            }
            return EventAtlasHeadline11666.sourceAttribution(
                source: slot.rawSource,
                sourceCount: slot.sourceCount
            )
        }()
        let pregameText = card.phase == .before ? nil : slot.pregameChance.map { formatProbability($0) }
        let actualCount = slot.side == .away ? card.awayActual : card.homeActual
        let primaryLabel: String
        let primaryValue: String
        if let verdict = slot.verdict {
            primaryLabel = "Result"
            if let actualCount {
                primaryValue = "\(milestoneVerdictBadgeText(verdict)) · Final \(card.family.formatCount(actualCount))"
            } else {
                primaryValue = milestoneVerdictBadgeText(verdict)
            }
        } else if let live = slot.liveChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(live)
        } else if slot.isStaleLive {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        } else if card.phase == .before, let pre = slot.pregameChance {
            primaryLabel = "Last quote"
            primaryValue = formatProbability(pre)
        } else if let pregameText {
            primaryLabel = "Pregame baseline"
            primaryValue = pregameText
        } else {
            primaryLabel = "Reading"
            primaryValue = EventAtlasStates11666.noRecentPrice
        }

        let observedText = slot.observedAt.map { EventAtlasChartMarks11666.formatExactTimestampPT($0) }
        return EventAtlasDetailsSheetModel11666(
            id: slot.id,
            outcomeTitle: "\(slot.teamLabel): \(slot.targetLabel) \(card.family.unitPlural)",
            marketTitle: "\(card.awayShort) at \(card.homeShort) · \(card.family.statWords)",
            primaryReadingLabel: primaryLabel,
            primaryReadingValue: primaryValue,
            pregameBaseline: pregameText,
            observedAtText: observedText,
            statusSummary: nil,
            sourceLabel: attribution
        )
    }
    // MARK: - Complete NFL Story Bundle Builder

    static func buildStories(
        sportKey: String?,
        status: String?,
        commenceTime: Date?,
        homeTeam: String,
        awayTeam: String,
        homeShort: String,
        awayShort: String,
        homeScore: Int?,
        awayScore: Int?,
        boxScoreData: EventBoxScoreData?,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date()
    ) -> (
        periodWinners: PeriodWinnersCard?,
        pairedMilestones: [PairedMilestonesCard],
        combinedYards: [CombinedYardsCard]
    ) {
        guard applies(sportKey: sportKey), let gm = gameMarkets else {
            return (nil, [], [])
        }
        let periodWinners = buildPeriodWinnersCard(
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            homeShort: homeShort,
            awayShort: awayShort,
            homeScore: homeScore,
            awayScore: awayScore,
            boxScoreData: boxScoreData,
            gameMarkets: gm,
            now: now
        )
        let pairedMilestones = TeamStatFamily.allCases.compactMap { family in
            buildPairedMilestonesCard(
                family: family,
                status: status,
                commenceTime: commenceTime,
                homeTeam: homeTeam,
                awayTeam: awayTeam,
                homeShort: homeShort,
                awayShort: awayShort,
                gameMarkets: gm,
                now: now
            )
        }
        let combinedYards = buildCombinedYardsCards(
            status: status,
            commenceTime: commenceTime,
            homeTeam: homeTeam,
            awayTeam: awayTeam,
            gameMarkets: gm,
            now: now
        )
        return (periodWinners, pairedMilestones, combinedYards)
    }
}

// MARK: - 12a View: Quarter-by-Quarter Period Winners Card

struct EventAtlasFootballPeriodWinnersCardView11666: View {
    let card: EventAtlasFootballCards11666.PeriodWinnersCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded: Bool = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var columns: [GridItem] {
        if dynamicTypeSize.isAccessibilitySize {
            return [GridItem(.flexible(), spacing: 12)]
        }
        return [
            GridItem(.flexible(), spacing: 12),
            GridItem(.flexible(), spacing: 12)
        ]
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(card.eyebrow)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                Text(card.title)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                Text(card.subtitle)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasFootballCards11666.periodWinnersMarkKey(for: card)
            )

            LazyVGrid(columns: columns, alignment: .leading, spacing: 12) {
                ForEach(card.panels) { panel in
                    quarterPanel(panel)
                }
            }

            Text(EventAtlasStates11666.independentChancesLabel)
                .font(.caption2)
                .foregroundStyle(DS.textSecondaryReadable)
                .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-nfl-period-winners-card-11666")
    }

    private func quarterPanel(_ panel: EventAtlasFootballCards11666.QuarterWinnerPanel) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(alignment: .firstTextBaseline) {
                Text(panel.quarter.code)
                    .font(.subheadline.weight(.bold))
                Spacer(minLength: 4)
                if let away = panel.awayScore, let home = panel.homeScore {
                    Text("\(card.awayShort) \(away) – \(home) \(card.homeShort)")
                        .font(.caption.monospacedDigit().weight(.semibold))
                        .foregroundStyle(DS.textSecondaryReadable)
                } else {
                    Text("Score pending")
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondaryReadable)
                }
            }

            ForEach(panel.legs) { leg in
                legRow(leg, panel: panel)
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 12, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 12, style: .continuous)
                .stroke(Color.secondary.opacity(0.14), lineWidth: 1)
        )
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-nfl-quarter-panel-\(panel.quarter.code.lowercased())")
    }

    private func legColor(_ side: EventAtlasFootballCards11666.Side) -> Color {
        switch side {
        case .away: return awayColor
        case .home: return homeColor
        case .tie: return .secondary
        }
    }

    private func legRow(
        _ leg: EventAtlasFootballCards11666.PeriodWinnerLeg,
        panel: EventAtlasFootballCards11666.QuarterWinnerPanel
    ) -> some View {
        let tint = legColor(leg.side)
        return VStack(alignment: .leading, spacing: 3) {
            HStack(alignment: .center, spacing: 4) {
                Text(leg.label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.primary)
                    .lineLimit(1)

                Spacer(minLength: 4)

                Button {
                    state.detailsRowID = leg.id
                } label: {
                    Image(systemName: "info.circle")
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .frame(width: 24, height: 24)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Details for \(panel.quarter.spokenTitle) \(leg.label)")
                .accessibilityIdentifier("atlas-nfl-period-winner-details-\(leg.id)")
            }

            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if let pre = leg.pregameChance {
                    Text("○ \(formatProbability(pre))")
                        .font(.caption.monospacedDigit())
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: true, vertical: false)
                } else if card.phase == .before {
                    Text(EventAtlasStates11666.noRecentPrice)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondaryReadable)
                } else {
                    Text("○ —")
                        .font(.caption)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .fixedSize(horizontal: true, vertical: false)
                }

                if let live = leg.liveChance {
                    Text("● \(formatProbability(live))")
                        .font(.caption.weight(.semibold).monospacedDigit())
                        .foregroundStyle(tint)
                        .fixedSize(horizontal: true, vertical: false)
                } else if leg.isStaleLive {
                    Text(EventAtlasStates11666.noRecentPrice)
                        .font(.caption2)
                        .foregroundStyle(DS.textSecondaryReadable)
                }

                Spacer(minLength: 2)

                if let verdict = leg.verdict {
                    Text(EventAtlasFootballCards11666.verdictBadgeText(verdict))
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(verdict == .won ? tint : .secondary)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }

            // 0–100% probability track with hollow pregame pin and filled live mark
            GeometryReader { geo in
                let width = max(1, geo.size.width)
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.15))
                        .frame(height: 4)
                    if let pre = leg.pregameChance {
                        Circle()
                            .strokeBorder(tint, lineWidth: 1.5)
                            .background(Circle().fill(Color.cardBackground))
                            .frame(width: 8, height: 8)
                            .offset(x: min(max(0, CGFloat(pre) * width - 4), width - 8))
                    }
                    if let live = leg.liveChance {
                        Circle()
                            .fill(tint)
                            .frame(width: 7, height: 7)
                            .offset(x: min(max(0, CGFloat(live) * width - 3.5), width - 7))
                    }
                }
            }
            .frame(height: 8)
            .accessibilityHidden(true)
        }
    }
}

// MARK: - 12b View: Paired Team Count Milestones Card

struct EventAtlasFootballPairedMilestonesCardView11666: View {
    let card: EventAtlasFootballCards11666.PairedMilestonesCard
    let awayColor: Color
    let homeColor: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded: Bool = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(card.eyebrow)
                    .font(.caption2.weight(.semibold))
                    .foregroundStyle(DS.textSecondaryReadable)
                Text(card.title)
                    .font(.headline)
                    .fixedSize(horizontal: false, vertical: true)
                Text("\(card.awayShort) vs \(card.homeShort) · \(card.family.statWords)")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }

            EventAtlasStoryCardMarkKeyView11666(
                items: EventAtlasFootballCards11666.pairedMilestonesMarkKey(for: card)
            )

            if card.awayActual != nil || card.homeActual != nil {
                HStack(spacing: 16) {
                    if let awayActual = card.awayActual {
                        Text("\(card.awayShort): \(card.family.formatCount(awayActual))")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(awayColor)
                    }
                    if let homeActual = card.homeActual {
                        Text("\(card.homeShort): \(card.family.formatCount(homeActual))")
                            .font(.caption.weight(.semibold))
                            .foregroundStyle(homeColor)
                    }
                }
            }

            VStack(alignment: .leading, spacing: 8) {
                ForEach(card.groups) { group in
                    thresholdGroupView(group)
                }
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-nfl-paired-milestones-card-\(card.family.rawValue)-11666")
    }

    private func thresholdGroupView(_ group: EventAtlasFootballCards11666.PairedMilestoneGroup) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("\(group.targetLabel) \(card.family.unitPlural)")
                .font(.caption.weight(.bold))
                .foregroundStyle(DS.textSecondaryReadable)

            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) {
                    slotView(group.away, side: .away, label: card.awayShort, tint: awayColor)
                    slotView(group.home, side: .home, label: card.homeShort, tint: homeColor)
                }
            } else {
                HStack(alignment: .top, spacing: 10) {
                    slotView(group.away, side: .away, label: card.awayShort, tint: awayColor)
                    slotView(group.home, side: .home, label: card.homeShort, tint: homeColor)
                }
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
    }

    private func slotView(
        _ slot: EventAtlasFootballCards11666.TeamMilestoneSlot?,
        side: EventAtlasFootballCards11666.Side,
        label: String,
        tint: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 4) {
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(tint)
                Spacer(minLength: 2)
                if let slot {
                    Button {
                        state.detailsRowID = slot.id
                    } label: {
                        Image(systemName: "info.circle")
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondaryReadable)
                            .frame(width: 28, height: 28)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Details for \(slot.teamLabel) \(slot.targetLabel) \(card.family.unitPlural)")
                    .accessibilityIdentifier("atlas-nfl-team-milestone-details-\(slot.id)")
                }
            }

            if let slot {
                HStack(spacing: 6) {
                    if let pre = slot.pregameChance {
                        Text("○ \(formatProbability(pre))")
                            .font(.caption.monospacedDigit())
                            .foregroundStyle(DS.textSecondaryReadable)
                    } else if card.phase == .before {
                        Text(EventAtlasStates11666.noRecentPrice)
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondaryReadable)
                    } else {
                        Text("○ Unavailable")
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondaryReadable)
                    }

                    if let live = slot.liveChance {
                        Text("● \(formatProbability(live))")
                            .font(.caption.weight(.semibold).monospacedDigit())
                            .foregroundStyle(tint)
                    } else if slot.isStaleLive {
                        Text(EventAtlasStates11666.noRecentPrice)
                            .font(.caption2)
                            .foregroundStyle(DS.textSecondaryReadable)
                    }
                }

                if let verdict = slot.verdict {
                    Text(EventAtlasFootballCards11666.milestoneVerdictBadgeText(verdict))
                        .font(.caption2.weight(.semibold))
                        .foregroundStyle(verdict == .won ? tint : .secondary)
                }
            } else {
                Text("Probability unavailable")
                    .font(.caption2)
                    .foregroundStyle(DS.textSecondaryReadable)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

// MARK: - 12c View: Combined Ground + Air Yards Card

struct EventAtlasFootballCombinedYardsCardView11666: View {
    let card: EventAtlasFootballCards11666.CombinedYardsCard
    let color: Color
    @ObservedObject var state: NFLCardDeckState9483
    var expanded: Bool = false
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            NFLMilestoneCardView9483(
                card: card.milestone,
                color: color,
                state: state,
                expanded: expanded
            )

            if card.splitState != .hiddenBeforePlay {
                Divider()
                splitSection
            }
        }
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-nfl-combined-yards-card-\(card.milestone.id)-11666")
    }

    @ViewBuilder
    private var splitSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("GROUND + AIR SPLIT")
                .font(.caption2.weight(.semibold))
                .foregroundStyle(DS.textSecondaryReadable)

            switch card.splitState {
            case .hiddenBeforePlay:
                EmptyView()

            case .absent(let message):
                Text(message)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)

            case .totalOnly(_, let formattedTotal, let splitUnavailableMessage):
                HStack(alignment: .firstTextBaseline) {
                    Text("Combined")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(formattedTotal)
                        .font(.subheadline.weight(.bold).monospacedDigit())
                        .foregroundStyle(color)
                }
                Text(splitUnavailableMessage)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)

            case .decomposed(_, let formattedTotal, let ground, let air):
                HStack(alignment: .firstTextBaseline) {
                    Text("Combined")
                        .font(.subheadline.weight(.semibold))
                    Spacer()
                    Text(formattedTotal)
                        .font(.subheadline.weight(.bold).monospacedDigit())
                        .foregroundStyle(color)
                }
                componentLane(ground, tint: color)
                componentLane(air, tint: color.opacity(0.65))
            }
        }
        .padding(10)
        .background(Color.secondary.opacity(0.06), in: RoundedRectangle(cornerRadius: 10, style: .continuous))
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier("atlas-nfl-combined-yards-split-\(card.milestone.id)")
    }

    private func componentLane(
        _ component: EventAtlasFootballCards11666.SignedYardageComponent,
        tint: Color
    ) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(component.label)
                    .font(.caption.weight(.medium))
                    .foregroundStyle(DS.textSecondaryReadable)
                Spacer()
                Text(component.formattedYards)
                    .font(.caption.weight(.semibold).monospacedDigit())
                    .foregroundStyle(.primary)
            }

            GeometryReader { geo in
                let width = max(1, geo.size.width)
                let lower = card.axisDomain.lowerBound
                let upper = max(lower + 1, card.axisDomain.upperBound)
                let span = upper - lower
                let zeroX = CGFloat((0 - lower) / span) * width
                let startX = CGFloat((component.span.start - lower) / span) * width
                let endX = CGFloat((component.span.end - lower) / span) * width
                let barMinX = min(startX, endX)
                let barWidth = max(3, abs(endX - startX))

                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.15))
                        .frame(height: 6)

                    // Zero origin mark when negative yardage is in domain
                    if lower < 0 {
                        Rectangle()
                            .fill(Color.primary.opacity(0.45))
                            .frame(width: 1.5, height: 10)
                            .offset(x: min(max(0, zeroX), width - 1.5))
                    }

                    RoundedRectangle(cornerRadius: 3, style: .continuous)
                        .fill(tint)
                        .frame(width: min(barWidth, width), height: 6)
                        .offset(x: min(max(0, barMinX), width - min(barWidth, width)))
                }
            }
            .frame(height: 10)
            .accessibilityHidden(true)
        }
    }
}
