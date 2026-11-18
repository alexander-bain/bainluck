import Foundation
import SwiftUI

/// #12616 (Ruling 190-C, 191-A, 182-A, 187-A, 161-B) — Pure presentation & eligibility model
/// for the Discover single-game card (`NativeEventDiscoverCard`).
///
/// Rulings 190-C + 191-A (Alex, Nov 13):
/// - Before kickoff (`scheduled`): compact card (`Size M`), no `Pregame` column, projected final shown.
/// - During and after a game (`live` or `finished`, when not suspended / closed-no-winner):
///   picture card (`191-A`) with the tall win-chance chart panel under the competitor rows
///   (connected win-chance line, `50%` reference line, labelled ends).
enum DiscoverSingleGameCard190C {

    /// Ruling 191-A selected the chart panel under the rows for in-progress and finished games.
    nonisolated static let defaultPictureVariant191Adopted = true

    // MARK: - 190-C / 191-A Eligibility

    /// #12824 — strips win-chance fields from `currentOdds` when the feed item's
    /// hero source is `"opening"` while retaining score projections.
    nonisolated private static func sanitizedEventForCurrentChance(_ event: FeedEventData) -> FeedEventData {
        guard event.heroProbabilitySource == OpeningLineHero.openingSource,
              var odds = event.currentOdds else {
            return event
        }
        var copy = event
        odds.homeProbability = nil
        odds.awayProbability = nil
        odds.drawProbability = nil
        odds.homeRenderedPercent = nil
        odds.awayRenderedPercent = nil
        copy.currentOdds = odds
        return copy
    }

    /// Maximum percentage-point move (`0...100`) between pregame/opening and current
    /// win probability while the game can still be graded (`nil` once finished/suspended
    /// or when either reading is absent).
    nonisolated static func swingPoints(
        event rawEvent: FeedEventData,
        prematch: PrematchReading?
    ) -> Double? {
        let event = sanitizedEventForCurrentChance(rawEvent)
        guard EventState.canStillBeGraded(
            event.status, commenceTime: event.commenceTime?.asDate),
              let reading = prematch,
              let curHome = CompactGameCard12616.usableProbability(event.currentOdds?.homeProbability) else {
            return nil
        }

        var maxDelta = abs(curHome - reading.homeProbability) * 100.0

        if !CompactGameCard12616.currentAwayIsWithheld(event),
           !CompactGameCard12616.prematchAwayIsWithheld(event),
           let curAway = CompactGameCard12616.usableProbability(event.currentOdds?.awayProbability) {
            maxDelta = max(maxDelta, abs(curAway - reading.awayProbability) * 100.0)
        }

        if CompactGameCard12616.hasExplicitThreeWayCurrent(event),
           CompactGameCard12616.hasExplicitThreeWayPrematch(event),
           let curDraw = CompactGameCard12616.usableProbability(event.currentOdds?.drawProbability),
           let preDraw = CompactGameCard12616.usableProbability(event.prematchOdds?.drawProbability) {
            maxDelta = max(maxDelta, abs(curDraw - preDraw) * 100.0)
        }

        return maxDelta.isFinite ? maxDelta : nil
    }

    /// Earlier 190-C pre-191 eligibility helper (live or >= 5-point pregame move).
    nonisolated static func qualifiesForPicture190C(
        event: FeedEventData,
        prematch: PrematchReading?
    ) -> Bool {
        let isSuspended = EventState.isSuspendedAndStarted(
            event.status, commenceTime: event.commenceTime?.asDate)
        if event.status == "live" && !isSuspended {
            return true
        }
        if let swing = swingPoints(event: event, prematch: prematch) {
            return swing >= 5.0 - 1e-9
        }
        return false
    }

    /// Ruling 191-A (replaces the 5-point pregame trigger in 190-C):
    /// - Before a game (`scheduled`): stays compact (`false`).
    /// - Suspended or venue-closed-no-winner: stays compact (`false`).
    /// - Games with zero win-probability readings: stays compact (`false`) rather
    ///   than drawing a blank chart frame.
    /// - Games in progress (`live`) and finished games (`isFinished`) that hold
    ///   win-probability data: carries the `191-A` chart panel under the rows (`true`).
    nonisolated static func qualifiesForPicture191A(
        event rawEvent: FeedEventData,
        prematch: PrematchReading? = nil
    ) -> Bool {
        let event = sanitizedEventForCurrentChance(rawEvent)
        let commence = event.commenceTime?.asDate
        let isSuspended = EventState.isSuspendedAndStarted(event.status, commenceTime: commence)
        let closedNoWinner = EventState.showsVenueClosedNoWinner(
            event.status,
            venueSettled: nil,
            venueClosedNoWinner: event.venueClosedNoWinner,
            commenceTime: commence
        )
        guard !isSuspended, !closedNoWinner else { return false }
        guard event.status == "live" || EventState.isFinished(event.status) else {
            return false
        }
        let resolvedPrematch = prematch
            ?? PrematchReading.resolve(prematch: event.prematchOdds, opening: event.openingOdds)
        let hasAnyWinChanceReading = resolvedPrematch != nil
            || CompactGameCard12616.usableProbability(event.currentOdds?.homeProbability) != nil
            || CompactGameCard12616.usableProbability(event.currentOdds?.awayProbability) != nil
        return hasAnyWinChanceReading
    }

    /// Active layout selector for `NativeEventDiscoverCard`.
    nonisolated static func usesPictureLayout(
        event: FeedEventData,
        prematch: PrematchReading?,
        pictureVariant191Adopted: Bool = defaultPictureVariant191Adopted
    ) -> Bool {
        guard pictureVariant191Adopted else { return false }
        return qualifiesForPicture191A(event: event, prematch: prematch)
    }

    // MARK: - Compact Card Column & Row Models (Atlas Sheet `(a)`)

    nonisolated struct ColumnHeaders: Equatable, Sendable {
        let score: String?
        let pregame: String?
        let primary: String?

        var hasAny: Bool { score != nil || pregame != nil || primary != nil }
    }

    nonisolated enum RowKind: Equatable, Sendable {
        case away
        case draw
        case home
    }

    nonisolated enum PrimaryCell: Equatable, Sendable {
        case probability(String)
        case finalScore(text: String?, won: Bool, isDrawOutcome: Bool)
        case won(String) // legacy
        case settledDash // "—"
        case none
    }

    nonisolated struct RowModel: Equatable, Sendable {
        let kind: RowKind
        let fullName: String
        let shortName: String
        let scoreText: String?
        let pregameText: String?
        let primaryCell: PrimaryCell
        let isWinner: Bool
        let isDimmedAfter: Bool
    }

    nonisolated struct BarSegments: Equatable, Sendable {
        let awayShare: Double
        let drawShare: Double?
        let homeShare: Double
        let awayIsWithheld: Bool
        var pregameNotch: Double? = nil
    }

    nonisolated struct Model: Equatable, Sendable {
        let leagueName: String
        let isLive: Bool
        let isFinished: Bool
        let isSuspended: Bool
        let headers: ColumnHeaders
        let rows: [RowModel]
        let bar: BarSegments?
        var livePregameSummary: EventSportHeadlines12472.LivePregameSummary? = nil
        let scheduledProjectedLine: String?
    }

    nonisolated static func build(
        event rawEvent: FeedEventData,
        prematch: PrematchReading?,
        showsInlinePregame: Bool = true,
        usesPictureLayout: Bool = false
    ) -> Model {
        let event = sanitizedEventForCurrentChance(rawEvent)
        let isLive = event.status == "live"
        let isFinished = EventState.isFinished(event.status)
        let isSuspended = EventState.isSuspendedAndStarted(
            event.status, commenceTime: event.commenceTime?.asDate)
        let isScheduled = !isSuspended && (event.status == "scheduled" || (!isLive && !isFinished))
        let canStillBeGraded = EventState.canStillBeGraded(
            event.status, commenceTime: event.commenceTime?.asDate)
        let outcome = EventOutcome.resolve(
            status: event.status, homeScore: event.homeScore, awayScore: event.awayScore)

        let shortPair = TeamShortName.shortPair(
            away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
        let pregameLabels = CompactGameCard12616.liveSidePregameLabels(
            event: event, prematch: prematch)
        let liveProjectedLabels: (away: String, home: String)? = (isLive && !isSuspended)
            ? CompactGameCard12616.liveProjectedColumnLabels(
                printed: LiveProjectedFinal2920.card(event),
                awayScore: event.awayScore,
                homeScore: event.homeScore
              )
            : nil
        let scheduledProjection = isScheduled ? ScheduledCardProjectedFinal12616.card(event) : nil

        let hasPrematchAny = pregameLabels.away != nil || pregameLabels.home != nil || pregameLabels.draw != nil
        let showPregameColumn: Bool = {
            if isSuspended { return hasPrematchAny }
            if isScheduled || isLive { return false }
            // On Finished, honour `showsInlinePregame` so `.xxxLarge` long single-word names never break mid-word.
            return showsInlinePregame && hasPrematchAny
        }()
        let showLiveProjectedColumn: Bool = isLive && !isSuspended && showsInlinePregame && liveProjectedLabels != nil
        let showScheduledProjectedColumn: Bool = isScheduled && showsInlinePregame && scheduledProjection != nil

        let hasScore = (isLive || isFinished || isSuspended)
            && (event.awayScore != nil || event.homeScore != nil)

        // Current reading (only when `canStillBeGraded` is true — #6010).
        let printableCurrent = canStillBeGraded
            ? DrawPricedWinner.printablePair(
                away: event.currentOdds?.awayProbability,
                home: event.currentOdds?.homeProbability,
                sport: event.sport)
            : nil

        let explicitThreeWayCurrent = canStillBeGraded && CompactGameCard12616.hasExplicitThreeWayCurrent(event)
        let explicitThreeWayPrematch = CompactGameCard12616.hasExplicitThreeWayPrematch(event)
        let awayCurrentWithheld = CompactGameCard12616.currentAwayIsWithheld(event)

        let currentStrings: (away: String?, draw: String?, home: String?) = {
            guard canStillBeGraded else { return (nil, nil, nil) }
            if isLive {
                let tenths = CompactGameCard12616.liveTenthsStrings(
                    away: explicitThreeWayCurrent ? event.currentOdds?.awayProbability : printableCurrent?.away,
                    home: event.currentOdds?.homeProbability,
                    awayIsWithheld: awayCurrentWithheld
                )
                let drawText = explicitThreeWayCurrent
                    ? CompactGameCard12616.formatSingleLiveTenths(event.currentOdds?.drawProbability)
                    : nil
                return (
                    away: awayCurrentWithheld ? absentProbabilityMarker : tenths.away,
                    draw: drawText,
                    home: tenths.home
                )
            }
            if explicitThreeWayCurrent,
               let awayP = CompactGameCard12616.usableProbability(event.currentOdds?.awayProbability),
               let drawP = CompactGameCard12616.usableProbability(event.currentOdds?.drawProbability),
               let homeP = CompactGameCard12616.usableProbability(event.currentOdds?.homeProbability) {
                return (
                    away: formatProbability(awayP, renderedPercent: nil),
                    draw: formatProbability(drawP, renderedPercent: nil),
                    home: formatProbability(homeP, renderedPercent: nil)
                )
            }
            guard let printable = printableCurrent else { return (nil, nil, nil) }
            if let awayP = printable.away {
                let duel = duelPercents(
                    away: awayP,
                    home: printable.home,
                    servedAway: event.currentOdds?.awayRenderedPercent,
                    servedHome: event.currentOdds?.homeRenderedPercent
                )
                return (
                    away: formatProbability(awayP, renderedPercent: duel[0]),
                    draw: nil,
                    home: formatProbability(printable.home, renderedPercent: duel[1])
                )
            } else {
                // #5363 — draw-priced sport without explicit three-way current odds:
                // withhold away rather than printing `1 - home`.
                return (
                    away: absentProbabilityMarker,
                    draw: nil,
                    home: formatProbability(printable.home, renderedPercent: nil)
                )
            }
        }()

        let hasCurrentChance = currentStrings.home != nil

        let headers: ColumnHeaders = {
            if isSuspended {
                return ColumnHeaders(
                    score: hasScore ? "Score" : nil,
                    pregame: showPregameColumn ? "Pregame" : nil,
                    primary: nil
                )
            }
            if isLive {
                return ColumnHeaders(
                    score: hasScore ? "Score" : nil,
                    pregame: showLiveProjectedColumn ? "Proj." : nil,
                    primary: hasCurrentChance ? "Now" : nil
                )
            }
            if isFinished {
                let hasFinalCell = hasScore || outcome != .undecided
                return ColumnHeaders(
                    score: nil,
                    pregame: showPregameColumn ? "Pregame" : nil,
                    primary: hasFinalCell ? "Final" : nil
                )
            }
            return ColumnHeaders(
                score: nil,
                pregame: showScheduledProjectedColumn ? "Proj." : nil,
                primary: hasCurrentChance ? "Chance" : nil
            )
        }()

        // 187-A: Include middle Draw row on soccer when explicit three-way odds exist
        // (or when a draw-priced match finished level).
        let showsDrawRow: Bool = {
            guard !isSuspended, DrawPricedWinner.sportPricesADraw(event.sport) else { return false }
            if canStillBeGraded { return explicitThreeWayCurrent }
            if isFinished {
                return explicitThreeWayPrematch || outcome == .draw
            }
            return false
        }()

        let awayWon = outcome.won(isAway: true)
        let homeWon = outcome.won(isAway: false)
        let drawWon = isFinished && outcome == .draw

        func pregameCellText(_ value: String?, withheld: Bool) -> String? {
            guard showPregameColumn else { return nil }
            if let value { return value }
            return withheld ? absentProbabilityMarker : nil
        }

        let awayPregameWithheld = hasPrematchAny && CompactGameCard12616.prematchAwayIsWithheld(event)

        let awayPrimary: PrimaryCell = {
            if isSuspended { return .none }
            if isFinished {
                let text = hasScore ? event.awayScore.map(String.init) : nil
                if text == nil && !awayWon { return .none }
                return .finalScore(text: text, won: awayWon, isDrawOutcome: outcome == .draw)
            }
            if let text = currentStrings.away {
                return text == absentProbabilityMarker ? .settledDash : .probability(text)
            }
            return .none
        }()

        let homePrimary: PrimaryCell = {
            if isSuspended { return .none }
            if isFinished {
                let text = hasScore ? event.homeScore.map(String.init) : nil
                if text == nil && !homeWon { return .none }
                return .finalScore(text: text, won: homeWon, isDrawOutcome: outcome == .draw)
            }
            if let text = currentStrings.home {
                return .probability(text)
            }
            return .none
        }()

        let awayRow = RowModel(
            kind: .away,
            fullName: event.awayTeam,
            shortName: shortPair.away,
            scoreText: (!isFinished && hasScore) ? event.awayScore.map(String.init) : nil,
            pregameText: showLiveProjectedColumn
                ? liveProjectedLabels?.away
                : (showScheduledProjectedColumn
                    ? scheduledProjection.map { String($0.away) }
                    : pregameCellText(pregameLabels.away, withheld: awayPregameWithheld)),
            primaryCell: awayPrimary,
            isWinner: awayWon,
            isDimmedAfter: isFinished && !awayWon && outcome != .draw
        )

        let homeRow = RowModel(
            kind: .home,
            fullName: event.homeTeam,
            shortName: shortPair.home,
            scoreText: (!isFinished && hasScore) ? event.homeScore.map(String.init) : nil,
            pregameText: showLiveProjectedColumn
                ? liveProjectedLabels?.home
                : (showScheduledProjectedColumn
                    ? scheduledProjection.map { String($0.home) }
                    : pregameCellText(pregameLabels.home, withheld: false)),
            primaryCell: homePrimary,
            isWinner: homeWon,
            isDimmedAfter: isFinished && !homeWon && outcome != .draw
        )

        var rows: [RowModel] = [awayRow]
        if showsDrawRow {
            let drawPrimary: PrimaryCell = {
                if isFinished {
                    return drawWon
                        ? .finalScore(text: nil, won: true, isDrawOutcome: true)
                        : .none
                }
                if let text = currentStrings.draw {
                    return .probability(text)
                }
                return .none
            }()
            rows.append(
                RowModel(
                    kind: .draw,
                    fullName: "Draw",
                    shortName: "Draw",
                    scoreText: nil,
                    pregameText: showPregameColumn ? pregameLabels.draw : nil,
                    primaryCell: drawPrimary,
                    isWinner: drawWon,
                    isDimmedAfter: isFinished && !drawWon
                )
            )
        }
        rows.append(homeRow)

        // Ruling 204-C + 200-B: Segmented probability bar before AND during a game
        // (never after a game), with the tick on the bar carrying the pregame chance
        // during play. On Discover during play (`usesPictureLayout == true`), the
        // 191-A chart panel sits underneath this bar, matching website EventCard183A.
        let bar: BarSegments? = {
            guard !isFinished, !isSuspended else { return nil }
            let prematchThreeWayDraw = CompactGameCard12616.hasExplicitThreeWayPrematch(event)
                ? event.prematchOdds?.drawProbability
                : nil
            let liveNotch = (!awayCurrentWithheld)
                ? CompactGameCard12616.pregameBarNotch(
                    prematch: prematch,
                    prematchDraw: prematchThreeWayDraw,
                    barShowsThreeWayDraw: explicitThreeWayCurrent,
                    sportPricesADraw: DrawPricedWinner.sportPricesADraw(event.sport),
                    isLive: isLive && !isSuspended,
                    isFinished: false,
                    isSuspended: isSuspended
                  )
                : nil
            if explicitThreeWayCurrent,
               let awayP = CompactGameCard12616.usableProbability(event.currentOdds?.awayProbability),
               let drawP = CompactGameCard12616.usableProbability(event.currentOdds?.drawProbability),
               let homeP = CompactGameCard12616.usableProbability(event.currentOdds?.homeProbability) {
                let shares = ProbabilityBar.normalizedShares(
                    awayProb: awayP, homeProb: homeP, drawProb: drawP)
                return BarSegments(
                    awayShare: shares.away,
                    drawShare: shares.draw,
                    homeShare: shares.home,
                    awayIsWithheld: false,
                    pregameNotch: liveNotch
                )
            }
            guard let printable = printableCurrent else { return nil }
            let rawAway = printable.away ?? (1.0 - printable.home)
            let shares = ProbabilityBar.normalizedShares(
                awayProb: rawAway, homeProb: printable.home)
            return BarSegments(
                awayShare: shares.away,
                drawShare: nil,
                homeShare: shares.home,
                awayIsWithheld: printable.away == nil,
                pregameNotch: printable.away == nil ? nil : liveNotch
            )
        }()

        // One layout per state: before a game, `Proj.` is a column (`Proj. · Chance`),
        // never a separate `"Projected: NE 21 – DET 27"` sentence beneath the bar.
        let scheduledProjectedLine: String? = nil

        let livePregameSummary = LivePregameCardSummary213A.resolve(event: event)

        return Model(
            leagueName: event.sportName ?? sportDisplayName(for: event.sport),
            isLive: isLive && !isSuspended,
            isFinished: isFinished,
            isSuspended: isSuspended,
            headers: headers,
            rows: rows,
            bar: bar,
            livePregameSummary: livePregameSummary,
            scheduledProjectedLine: scheduledProjectedLine
        )
    }
}
