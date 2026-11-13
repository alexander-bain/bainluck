import SwiftUI

/// #12616 (Decision 161-B, "chance first") — pure column grammar, scheduled
/// sportsbook projection admission, live tenths duel formatting, optional
/// three-way soccer draw row, and compact context-line formatting for
/// `EventCardView`.
enum CompactGameCard12616 {

    /// The two column headers above the team rows (`medium` context on the left,
    /// `large` primary answer on the right). A blank column draws no header.
    nonisolated struct ColumnHeaders: Equatable, Sendable {
        let medium: String?
        let large: String?

        var hasAny: Bool { medium != nil || large != nil }
    }

    /// Column headers for each game state under 161-B:
    /// - Before (`isScheduled`): `Projected` (medium) · `Chance` (large)
    /// - During (`isLive && !isSuspended`): `Score` (medium) · `Now` (large)
    /// - After (`isFinished`): `Pregame` (medium) · `Final` (large)
    /// - Suspended-and-started (`isSuspended`): neither (`No result reported`)
    nonisolated static func columnHeaders(
        isScheduled: Bool,
        isLive: Bool,
        isFinished: Bool,
        isSuspended: Bool,
        hasProjectedBefore: Bool,
        hasCurrentChance: Bool,
        hasPrematchChance: Bool,
        hasScore: Bool
    ) -> ColumnHeaders {
        if isSuspended {
            return ColumnHeaders(medium: nil, large: nil)
        }
        if isLive {
            return ColumnHeaders(
                medium: hasScore ? "Score" : nil,
                large: hasCurrentChance ? "Now" : nil
            )
        }
        if isFinished {
            return ColumnHeaders(
                medium: hasPrematchChance ? "Pregame" : nil,
                large: hasScore ? "Final" : nil
            )
        }
        if isScheduled {
            return ColumnHeaders(
                medium: hasProjectedBefore ? "Projected" : nil,
                large: hasCurrentChance ? "Chance" : nil
            )
        }
        return ColumnHeaders(medium: nil, large: nil)
    }

    // MARK: - Live streaming tenths ("Now", 161-B)

    /// Formats a single probability to tenths (`"64.2%"`), respecting the
    /// standing live rule that a live number never prints `0%`/`0.0%` or
    /// `100%`/`100.0%` (`"<1%"` below 1%, `">99%"` above 99%).
    nonisolated static func formatSingleLiveTenths(_ value: Double?) -> String? {
        guard let value, value.isFinite else { return nil }
        let pct = value * 100
        if pct < 1 { return "<1%" }
        if pct > 99 { return ">99%" }
        let tenths = min(990, max(10, Int(((value * 10000) / 10).rounded())))
        return String(format: "%.1f%%", Double(tenths) / 10.0)
    }

    /// Formats a two-sided live duel to tenths (`[away, home]`), anchoring the
    /// favourite so complement pairs in `[1%, 99%]` always sum to `100.0%`
    /// (`1000` tenths), while honouring `<1%` / `>99%` and withholding away on
    /// two-way complement soccer payloads (#5363).
    nonisolated static func liveTenthsStrings(
        away: Double?,
        home: Double?,
        awayIsWithheld: Bool
    ) -> (away: String?, home: String?) {
        if awayIsWithheld {
            return (away: nil, home: formatSingleLiveTenths(home))
        }
        guard let away, let home, away.isFinite, home.isFinite else {
            return (
                away: formatSingleLiveTenths(away),
                home: formatSingleLiveTenths(home)
            )
        }
        let awayPct = away * 100
        let homePct = home * 100
        if awayPct < 1 || awayPct > 99 || homePct < 1 || homePct > 99 {
            return (
                away: formatSingleLiveTenths(away),
                home: formatSingleLiveTenths(home)
            )
        }
        guard isComplementPair([away, home]) else {
            return (
                away: formatSingleLiveTenths(away),
                home: formatSingleLiveTenths(home)
            )
        }
        let total = away + home
        if away >= home {
            let favTenths = min(990, max(10, Int((((away / total) * 10000) / 10).rounded())))
            let dogTenths = 1000 - favTenths
            return (
                away: String(format: "%.1f%%", Double(favTenths) / 10.0),
                home: String(format: "%.1f%%", Double(dogTenths) / 10.0)
            )
        } else {
            let favTenths = min(990, max(10, Int((((home / total) * 10000) / 10).rounded())))
            let dogTenths = 1000 - favTenths
            return (
                away: String(format: "%.1f%%", Double(dogTenths) / 10.0),
                home: String(format: "%.1f%%", Double(favTenths) / 10.0)
            )
        }
    }

    // MARK: - Three-way draw row (soccer with explicit drawProbability)

    /// Returns a usable open probability in `(0, 1)`.
    nonisolated static func usableProbability(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    /// True only when a draw-priced sport carries an explicit three-way reading
    /// (`away + draw + home ≈ 1`, with `draw > 0`), so the away figure is a real
    /// three-way away price rather than `1 - home`.
    nonisolated static func hasExplicitThreeWayCurrent(_ event: FeedEventData) -> Bool {
        guard DrawPricedWinner.sportPricesADraw(event.sport),
              let away = usableProbability(event.currentOdds?.awayProbability),
              let draw = usableProbability(event.currentOdds?.drawProbability),
              let home = usableProbability(event.currentOdds?.homeProbability) else {
            return false
        }
        let sum = away + draw + home
        return sum >= 0.95 && sum <= 1.05
    }

    nonisolated static func hasExplicitThreeWayPrematch(_ event: FeedEventData) -> Bool {
        guard DrawPricedWinner.sportPricesADraw(event.sport),
              let away = usableProbability(event.prematchOdds?.awayProbability),
              let draw = usableProbability(event.prematchOdds?.drawProbability),
              let home = usableProbability(event.prematchOdds?.homeProbability) else {
            return false
        }
        let sum = away + draw + home
        return sum >= 0.95 && sum <= 1.05
    }

    /// #5363 / #12616 — whether `current_odds` (`Chance` before, `Now` during,
    /// and the live/scheduled bar) withholds its away figure because the sport
    /// prices a draw and `current_odds` has no explicit three-way reading.
    nonisolated static func currentAwayIsWithheld(_ event: FeedEventData) -> Bool {
        DrawPricedWinner.sportPricesADraw(event.sport)
            && !hasExplicitThreeWayCurrent(event)
    }

    /// #5363 / #12616 — whether the resolved pre-match reading (`Pregame` column
    /// after, suspended pre-match row, and the finished bar) withholds its away
    /// figure because the sport prices a draw and `prematch_odds` has no
    /// explicit three-way reading.
    nonisolated static func prematchAwayIsWithheld(_ event: FeedEventData) -> Bool {
        DrawPricedWinner.sportPricesADraw(event.sport)
            && !hasExplicitThreeWayPrematch(event)
    }

    /// Formatted draw probability when a draw-priced sport carries an explicit
    /// `drawProbability` on the active reading (`Chance` before, `Now` during,
    /// `Pregame` after). Never invents a draw probability from `1 - home`.
    nonisolated static func drawChanceText(
        event: FeedEventData,
        isScheduled: Bool,
        isLive: Bool,
        isFinished: Bool,
        isSuspended: Bool
    ) -> String? {
        guard DrawPricedWinner.sportPricesADraw(event.sport), !isSuspended else { return nil }
        if isLive {
            guard hasExplicitThreeWayCurrent(event),
                  let draw = usableProbability(event.currentOdds?.drawProbability) else { return nil }
            return formatSingleLiveTenths(draw)
        }
        if isScheduled {
            guard hasExplicitThreeWayCurrent(event),
                  let draw = usableProbability(event.currentOdds?.drawProbability) else { return nil }
            return formatProbability(draw, renderedPercent: nil)
        }
        if isFinished {
            guard hasExplicitThreeWayPrematch(event),
                  let draw = usableProbability(event.prematchOdds?.drawProbability) else { return nil }
            return formatProbability(draw, renderedPercent: nil)
        }
        return nil
    }

    // MARK: - Pregame notch on ProbabilityBar

    /// The pregame away share in `(0, 1)` for the 6pt bar's notch on live and
    /// finished cards when a pre-match reading exists. Matches the active bar's
    /// footing:
    /// - Three-way bar (`barShowsThreeWayDraw == true`): divides pure `away` by
    ///   `away + home + draw` (or withholds `nil` on draw-priced sports when
    ///   `prematchDraw` is absent, since a two-way complement cannot separate
    ///   `away` from `draw`).
    /// - Two-way bar (`barShowsThreeWayDraw == false`): places the notch at the
    ///   pregame left-segment boundary `(away + draw) / (away + home + draw)`
    ///   (`away / (away + home)` when `draw == 0`, or `1 - homeShare` when a
    ///   three-way pregame reading sits over a two-way `[not-home | home]` bar).
    nonisolated static func pregameBarNotch(
        prematch: PrematchReading?,
        prematchDraw: Double? = nil,
        barShowsThreeWayDraw: Bool? = nil,
        sportPricesADraw: Bool = false,
        isLive: Bool,
        isFinished: Bool,
        isSuspended: Bool
    ) -> Double? {
        guard !isSuspended, isLive || isFinished, let prematch else { return nil }
        let usableDraw = usableProbability(prematchDraw)
        let threeWayBar = barShowsThreeWayDraw ?? (usableDraw != nil)
        if threeWayBar && sportPricesADraw && usableDraw == nil {
            return nil
        }
        let draw = usableDraw ?? 0
        let sum = prematch.awayProbability + prematch.homeProbability + draw
        guard sum.isFinite, sum > 0 else { return nil }
        let numerator = threeWayBar ? prematch.awayProbability : (prematch.awayProbability + draw)
        let share = numerator / sum
        guard share > 0, share < 1 else { return nil }
        return share
    }

    // MARK: - Quiet grey context line (12.5pt, #6B6B76 / DS.textSecondaryReadable)

    /// Compact single-line live projected score (`"Projected 121–100"`, or
    /// `"Projected (90 min) 1–2"` on regulation soccer), in away–home card order.
    nonisolated static func liveContextText(_ printed: LiveProjectedFinalAdmission2920.Printed) -> String {
        let prefix = printed.admitted.provenance.period == .regulation
            ? "Projected (90 min)"
            : "Projected"
        return "\(prefix) \(printed.away)\u{2013}\(printed.home)"
    }

    /// Combines the optional live projected final and optional pregame starting
    /// chance (`"Projected 118–109 · Pregame 54%–46%"`) into one quiet grey
    /// context line on live cards (#12616, Decision 161-B).
    nonisolated static func combinedLiveContextText(
        projected: LiveProjectedFinalAdmission2920.Printed?,
        pregameClause: String?
    ) -> String? {
        var parts: [String] = []
        if let projected {
            parts.append(liveContextText(projected))
        }
        if let pregameClause, !pregameClause.isEmpty {
            parts.append(pregameClause)
        }
        guard !parts.isEmpty else { return nil }
        return parts.joined(separator: " \u{00B7} ")
    }

    /// Compact single-line finished pregame projected score (`"Projected 21–24"`,
    /// or `"Projected (90 min) 1–2"` on regulation soccer), in away–home card order.
    nonisolated static func finalContextText(_ comparison: FinalForecastComparison11296.Comparison) -> String {
        let prefix = comparison.label == FinalForecastComparison11296.label90Min
            ? "Projected (90 min)"
            : "Projected"
        return "\(prefix) \(comparison.away)\u{2013}\(comparison.home)"
    }

    // MARK: - Ruling 182-A + inline "pregame" beside live win chance

    /// Matches `pregame_records_caption` strings (`"TOR 77-80 · BAL 76-81"`,
    /// `"FLA 12-4-3 · CAR 10-5-2"`) so game cards never print the records bubble.
    nonisolated static func isRecordsCaption(_ text: String?) -> Bool {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty else { return false }
        let pattern = #"^[A-Za-z0-9.\- ]+\s+\d{1,3}-\d{1,3}(?:-\d{1,3})?\s*[\u{00B7}•|]\s*[A-Za-z0-9.\- ]+\s+\d{1,3}-\d{1,3}(?:-\d{1,3})?$"#
        return trimmed.range(of: pattern, options: .regularExpression) != nil
    }

    /// Returns a cleaned reason string when `text` is non-empty and not a team
    /// records caption (`182-A`).
    nonisolated static func sanitizedReason(_ text: String?) -> String? {
        guard let trimmed = text?.trimmingCharacters(in: .whitespacesAndNewlines),
              !trimmed.isEmpty,
              !isRecordsCaption(trimmed) else { return nil }
        return trimmed
    }

    /// Per-row `"54% pregame"` labels (lowercase `"pregame"`, never `"opened"`)
    /// placed beside the live win chance where horizontal room permits. Withholds
    /// the away label on two-way soccer complements (#5363) and includes `draw`
    /// when a three-way pre-match reading is present.
    nonisolated static func liveSidePregameLabels(
        event: FeedEventData,
        prematch: PrematchReading?
    ) -> (away: String?, home: String?, draw: String?) {
        guard let reading = prematch else { return (nil, nil, nil) }
        let awayWithheld = prematchAwayIsWithheld(event)
        let awayText: String? = awayWithheld
            ? nil
            : formatProbability(reading.awayProbability, renderedPercent: reading.percents[0])
                .map { "\($0) pregame" }
        let homeText = "\(formatProbability(reading.homeProbability, renderedPercent: reading.percents[1])) pregame"
        let drawText: String?
        if hasExplicitThreeWayPrematch(event),
           let draw = usableProbability(event.prematchOdds?.drawProbability) {
            drawText = "\(formatProbability(draw, renderedPercent: nil)) pregame"
        } else {
            drawText = nil
        }
        return (away: awayText, home: homeText, draw: drawText)
    }

    /// Whether `"54% pregame"` fits inline beside the live win chance without
    /// squeezing or breaking a single-word team name (`"Timberwolves"`, `.xxxLarge`).
    nonisolated static func liveInlinePregameFits(
        awayShortName: String,
        homeShortName: String,
        typeSize: DynamicTypeSize,
        availableRowWidth: CGFloat = 330
    ) -> Bool {
        guard !typeSize.isAccessibilitySize else { return false }
        let scale: CGFloat
        switch typeSize {
        case .xSmall: scale = 0.88
        case .small: scale = 0.94
        case .medium: scale = 0.97
        case .large: scale = 1.0
        case .xLarge: scale = 1.08
        default: return false // .xxLarge / .xxxLarge drop inline pregame to context fallback
        }
        // Crest (28) + Score (42) + inline pregame (68) + Now (84) + 4 gaps (24) = 246pt at .large.
        let nonNameBudget: CGFloat = 28 + (42 + 68 + 84) * scale + 24
        let availableNameWidth = availableRowWidth - nonNameBudget
        guard availableNameWidth >= 56 else { return false }
        let approxCharWidth = 9.4 * scale
        for shortName in [awayShortName, homeShortName] {
            for word in shortName.split(separator: " ") {
                if CGFloat(word.count) * approxCharWidth > availableNameWidth {
                    return false
                }
            }
        }
        return true
    }
}

private extension String {
    nonisolated func map<T>(_ transform: (String) -> T) -> T {
        transform(self)
    }
}

/// #12616 / #9034 — Web's `cardProjectedFinal` (`frontend/lib/projectedFinalPair.ts`)
/// ported for scheduled native game cards (`Before`: `Projected` medium column).
/// Lives outside `EventCardView.swift` so live/finished cards never read the
/// bare `projectedHomeScore` / `projectedAwayScore` fields (#2920).
enum ScheduledCardProjectedFinal12616 {
    nonisolated struct Pair: Equatable, Sendable {
        let away: Int
        let home: Int
    }

    nonisolated static func card(_ event: FeedEventData) -> Pair? {
        resolve(odds: event.currentOdds, sportKey: event.sport)
    }

    nonisolated static func resolve(odds: CurrentOdds?, sportKey: String?) -> Pair? {
        guard FinalForecastComparison11296.unit(forSport: sportKey) != nil else { return nil }
        let vocab = SportVocab.forSport(sportKey)
        guard vocab.sportsbookSpreadIsAMargin else { return nil }
        guard let odds,
              let home = odds.projectedHomeScore,
              let away = odds.projectedAwayScore,
              home.isFinite, away.isFinite,
              home > 0, away > 0 else { return nil }
        guard let roundedHome = Int(exactly: home.rounded()),
              let roundedAway = Int(exactly: away.rounded()) else { return nil }
        guard roundedHome != roundedAway || vocab.canEndInATie else { return nil }
        return Pair(away: roundedAway, home: roundedHome)
    }
}

/// Quiet `12.5pt` grey context line (`DS.textSecondaryReadable`) under the 6pt
/// bar on compact game cards (#12616, Decision 161-B). Single line whenever it
/// fits; stacks cleanly at large Dynamic Type instead of clipping digits.
struct CompactProjectedContextLine12616: View {
    let text: String
    let spokenText: String
    let accessibilityId: String

    @ScaledMetric(relativeTo: .caption) private var fontSize: CGFloat = 12.5

    private var font: Font {
        .system(size: min(fontSize, 20), weight: .regular).monospacedDigit()
    }

    var body: some View {
        let clauses = text.components(separatedBy: " \u{00B7} ")
        Group {
            if clauses.count == 2 {
                ViewThatFits(in: .horizontal) {
                    Text(text)
                        .font(font)
                        .foregroundStyle(DS.textSecondaryReadable)
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(clauses[0])
                        Text(clauses[1])
                    }
                    .font(font)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                Text(text)
                    .font(font)
                    .foregroundStyle(DS.textSecondaryReadable)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(spokenText)
        .accessibilityIdentifier(accessibilityId)
    }
}
