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
    /// finished cards when a pre-match reading exists.
    nonisolated static func pregameBarNotch(
        prematch: PrematchReading?,
        isLive: Bool,
        isFinished: Bool,
        isSuspended: Bool
    ) -> Double? {
        guard !isSuspended, isLive || isFinished, let prematch else { return nil }
        let sum = prematch.awayProbability + prematch.homeProbability
        guard sum.isFinite, sum > 0 else { return nil }
        let share = prematch.awayProbability / sum
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

    /// Compact single-line finished pregame projected score (`"Projected 21–24"`,
    /// or `"Projected (90 min) 1–2"` on regulation soccer), in away–home card order.
    nonisolated static func finalContextText(_ comparison: FinalForecastComparison11296.Comparison) -> String {
        let prefix = comparison.label == FinalForecastComparison11296.label90Min
            ? "Projected (90 min)"
            : "Projected"
        return "\(prefix) \(comparison.away)\u{2013}\(comparison.home)"
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
/// bar on compact game cards (#12616, Decision 161-B).
struct CompactProjectedContextLine12616: View {
    let text: String
    let spokenText: String
    let accessibilityId: String

    @ScaledMetric(relativeTo: .caption) private var fontSize: CGFloat = 12.5

    var body: some View {
        Text(text)
            .font(.system(size: min(fontSize, 20), weight: .regular).monospacedDigit())
            .foregroundStyle(DS.textSecondaryReadable)
            .lineLimit(1)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spokenText)
            .accessibilityIdentifier(accessibilityId)
    }
}
