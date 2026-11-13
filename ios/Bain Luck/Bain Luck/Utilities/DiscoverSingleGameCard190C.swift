import Foundation
import SwiftUI

/// #12616 (Ruling 190-C, 182-A, 187-A, 161-B) — Pure presentation & eligibility model
/// for the Discover single-game card (`NativeEventDiscoverCard`).
///
/// Ruling 190-C:
/// - Compact by default (`Size M`, retiring the tall empty hero box).
/// - The version with the win-chance picture is eligible ONLY when the game is live
///   or its win chance has moved 5 or more percentage points since pregame.
/// - While decision 191 (which picture look Alex selects) is pending,
///   `defaultPictureVariant191Adopted` stays `false` so Discover renders the compact
///   card everywhere.
enum DiscoverSingleGameCard190C {

    /// Flips to `true` only when Alex selects a picture variant in decision 191
    /// and that picture variant is built.
    nonisolated static let defaultPictureVariant191Adopted = false

    // MARK: - 190-C Eligibility (Live or >= 5.0 pt swing)

    /// Maximum percentage-point move (`0...100`) between pregame/opening and current
    /// win probability while the game can still be graded (`nil` once finished/suspended
    /// or when either reading is absent).
    nonisolated static func swingPoints(
        event: FeedEventData,
        prematch: PrematchReading?
    ) -> Double? {
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

    /// True under 190-C when the single-game card would earn the win-chance picture:
    /// either the game is live (and not suspended) or its win chance has moved >= 5 points.
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

    /// Active layout selector for `NativeEventDiscoverCard`.
    nonisolated static func usesPictureLayout(
        event: FeedEventData,
        prematch: PrematchReading?,
        pictureVariant191Adopted: Bool = defaultPictureVariant191Adopted
    ) -> Bool {
        pictureVariant191Adopted && qualifiesForPicture190C(event: event, prematch: prematch)
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
        case won(String) // "Won ✓" or "Draw ✓"
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
    }

    nonisolated struct Model: Equatable, Sendable {
        let leagueName: String
        let isLive: Bool
        let isFinished: Bool
        let isSuspended: Bool
        let headers: ColumnHeaders
        let rows: [RowModel]
        let bar: BarSegments?
        let scheduledProjectedLine: String?
    }

    nonisolated static func build(
        event: FeedEventData,
        prematch: PrematchReading?,
        showsInlinePregame: Bool = true
    ) -> Model {
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

        let hasPrematchAny = pregameLabels.away != nil || pregameLabels.home != nil || pregameLabels.draw != nil
        let showPregameColumn: Bool = {
            if isSuspended { return hasPrematchAny }
            if isScheduled { return false }
            // On 3-column states (Live / Finished), honour `showsInlinePregame` so `.xxxLarge`
            // long single-word names never break mid-word.
            return showsInlinePregame && hasPrematchAny
        }()

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
                    pregame: showPregameColumn ? "Pregame" : nil,
                    primary: hasCurrentChance ? "Now" : nil
                )
            }
            if isFinished {
                return ColumnHeaders(
                    score: hasScore ? "Score" : nil,
                    pregame: showPregameColumn ? "Pregame" : nil,
                    primary: "Result"
                )
            }
            return ColumnHeaders(
                score: nil,
                pregame: showPregameColumn ? "Pregame" : nil,
                primary: hasCurrentChance ? "Now" : nil
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
                return awayWon ? .won("Won \u{2713}") : .settledDash
            }
            if let text = currentStrings.away {
                return text == absentProbabilityMarker ? .settledDash : .probability(text)
            }
            return .none
        }()

        let homePrimary: PrimaryCell = {
            if isSuspended { return .none }
            if isFinished {
                return homeWon ? .won("Won \u{2713}") : .settledDash
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
            scoreText: hasScore ? event.awayScore.map(String.init) : nil,
            pregameText: pregameCellText(pregameLabels.away, withheld: awayPregameWithheld),
            primaryCell: awayPrimary,
            isWinner: awayWon,
            isDimmedAfter: isFinished && !awayWon && outcome != .draw
        )

        let homeRow = RowModel(
            kind: .home,
            fullName: event.homeTeam,
            shortName: shortPair.home,
            scoreText: hasScore ? event.homeScore.map(String.init) : nil,
            pregameText: pregameCellText(pregameLabels.home, withheld: false),
            primaryCell: homePrimary,
            isWinner: homeWon,
            isDimmedAfter: isFinished && !homeWon && outcome != .draw
        )

        var rows: [RowModel] = [awayRow]
        if showsDrawRow {
            let drawPrimary: PrimaryCell = {
                if isFinished {
                    return drawWon ? .won("Draw \u{2713}") : .settledDash
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

        // Bar: shown only when `!isFinished && !isSuspended` (Queue #238 + Atlas `(a)` card 4).
        let bar: BarSegments? = {
            guard !isFinished, !isSuspended else { return nil }
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
                    awayIsWithheld: false
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
                awayIsWithheld: printable.away == nil
            )
        }()

        // Scheduled pregame projected score line (when admitted by `ScheduledCardProjectedFinal12616`).
        let scheduledProjectedLine: String? = {
            guard isScheduled, let pair = ScheduledCardProjectedFinal12616.card(event) else {
                return nil
            }
            let badges = NativeEventDiscoverCard.cardBadges(
                away: event.awayTeam, home: event.homeTeam, sportKey: event.sport)
            return "Projected: \(badges.away) \(pair.away) \u{2013} \(badges.home) \(pair.home)"
        }()

        return Model(
            leagueName: event.sportName ?? sportDisplayName(for: event.sport),
            isLive: isLive && !isSuspended,
            isFinished: isFinished,
            isSuspended: isSuspended,
            headers: headers,
            rows: rows,
            bar: bar,
            scheduledProjectedLine: scheduledProjectedLine
        )
    }
}
