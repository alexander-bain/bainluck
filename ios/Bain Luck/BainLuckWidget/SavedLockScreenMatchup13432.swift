import Foundation
import SwiftUI
import WidgetKit
#if DEBUG && canImport(Bain_Luck) && !BAINLUCK_WIDGET_EXTENSION
@testable import Bain_Luck
#endif

/// #13432 — Resolved state for the iPhone double-wide (`accessoryRectangular`)
/// Lock Screen widget on a saved game, sharing `WatchMatchupReading217` and
/// `WatchMatchupComplication217` directly with the Apple Watch rectangle.
nonisolated enum SavedLockScreenRectangleState13432: Equatable, Sendable {
    case matchup(WatchMatchupReading217)
    case postFinalEnded(title: String)
    case fallbackText
}

nonisolated enum SavedLockScreenMatchupAdapter13432 {
    static func resolve(
        event: SavedWidgetEventDetail10875,
        reading: SavedWidgetReading10875,
        art: SavedWidgetArt12466,
        logos: SavedWidgetLogos12466.Pair,
        side: SavedWidgetGameSide10875?,
        isOffline: Bool,
        now: Date,
        timeZone: TimeZone = .current
    ) -> SavedLockScreenRectangleState13432 {
        // Venue-settled / closed-no-winner / suspended games keep SavedRectangular10875's exact text layout.
        guard !EventState.showsVenueSettledVerdict(
                event.status,
                venueSettled: event.venueSettled,
                commenceTime: art.commenceTime,
                now: now
              ),
              !EventState.showsVenueClosedNoWinner(
                event.status,
                venueSettled: event.venueSettled,
                venueClosedNoWinner: event.venueClosedNoWinner,
                commenceTime: art.commenceTime,
                now: now
              ),
              !EventState.isSuspendedAndStarted(event.status, commenceTime: art.commenceTime, now: now)
        else {
            return .fallbackText
        }

        let awayLogo = logos.away.flatMap { WatchMatchupCrests217.complicationCGImage(from: $0) != nil ? $0 : nil }
        let homeLogo = logos.home.flatMap { WatchMatchupCrests217.complicationCGImage(from: $0) != nil ? $0 : nil }

        func buildSide(
            short: String,
            primaryHex: String?,
            secondaryHex: String?,
            logo: Data?,
            score: Int?,
            isWinner: Bool
        ) -> WatchMatchupReading217.Side {
            WatchMatchupReading217.Side(
                abbreviation: short,
                inkHex: WatchMatchupReading217.ink(primary: primaryHex, secondary: secondaryHex),
                crestPNG: logo,
                score: score,
                isWinner: isWinner
            )
        }

        // 1. Finished games: show final Matchup with pregame % for up to 3 hours, then clear "Game ended".
        if EventState.isFinished(event.status) {
            let finalObservedAt = SavedWidgetDetailDecoding10875.date(event.scoreObservedAt)
                ?? SavedWidgetDetailDecoding10875.date(event.heroProbabilityObservedAt)
            if let finalObservedAt,
               finalObservedAt.timeIntervalSinceReferenceDate.isFinite,
               now.timeIntervalSince(finalObservedAt) >= WatchMatchupReading217.finalHoldSeconds {
                return .postFinalEnded(title: reading.shortSubject)
            }
            guard reading.phase == .result,
                  let awayScore = event.awayScore, let homeScore = event.homeScore,
                  awayScore >= 0, homeScore >= 0 else {
                return .fallbackText
            }
            let matchup = "\(event.awayTeam) at \(event.homeTeam)"
            if homeScore == awayScore {
                guard let drawPre = renderedPercent(event.prematchOdds?.drawProbability),
                      (0...100).contains(drawPre),
                      let drawText = ExternalSurfaceProbabilityFormat.openWholePercent(
                        drawPre,
                        probability: event.prematchOdds?.drawProbability
                      ) else {
                    return .fallbackText
                }
                return .matchup(
                    WatchMatchupReading217(
                        stage: .after,
                        away: buildSide(short: art.away.short, primaryHex: art.away.primaryHex, secondaryHex: art.away.secondaryHex, logo: awayLogo, score: awayScore, isWinner: false),
                        home: buildSide(short: art.home.short, primaryHex: art.home.primaryHex, secondaryHex: art.home.secondaryHex, logo: homeLogo, score: homeScore, isWinner: false),
                        bigText: drawText,
                        bigOwnerLabel: "Draw",
                        bigIsHome: true,
                        smallLine: "Pregame · Final",
                        accessibilityText: "Final. \(matchup), \(awayScore)–\(homeScore). Draw had \(drawText) pregame. Open your game in Bain Luck."
                    )
                )
            }
            let homeWon = homeScore > awayScore
            guard let pct = homeWon ? art.pregameChances?.homePercent : art.pregameChances?.awayPercent,
                  (0...100).contains(pct),
                  let pregameText = (homeWon ? art.pregameChances?.homeText : art.pregameChances?.awayText)
                    ?? ExternalSurfaceProbabilityFormat.openWholePercent(
                        pct,
                        probability: homeWon ? event.prematchOdds?.homeProbability : event.prematchOdds?.awayProbability
                    ) else {
                return .fallbackText
            }
            let winnerAbbr = homeWon ? art.home.short : art.away.short
            let winnerName = homeWon ? event.homeTeam : event.awayTeam
            let loserName = homeWon ? event.awayTeam : event.homeTeam
            return .matchup(
                WatchMatchupReading217(
                    stage: .after,
                    away: buildSide(short: art.away.short, primaryHex: art.away.primaryHex, secondaryHex: art.away.secondaryHex, logo: awayLogo, score: awayScore, isWinner: !homeWon),
                    home: buildSide(short: art.home.short, primaryHex: art.home.primaryHex, secondaryHex: art.home.secondaryHex, logo: homeLogo, score: homeScore, isWinner: homeWon),
                    bigText: pregameText,
                    bigOwnerLabel: winnerAbbr,
                    bigIsHome: homeWon,
                    smallLine: "Pregame · Final",
                    accessibilityText: "Final. \(winnerName) \(max(homeScore, awayScore)), \(loserName) \(min(homeScore, awayScore)). \(winnerName) had \(pregameText) pregame. Open your game in Bain Luck."
                )
            )
        }

        // 2. Priced live / upcoming / aged games (opening line keeps caption-based SavedRectangular10875).
        guard reading.phase == .current || reading.phase == .lastRecorded,
              let odds = event.currentOdds,
              let homeProb = odds.homeProbability,
              homeProb.isFinite else {
            return .fallbackText
        }

        let isLive = art.isLive
        let isThreeWaySport = DrawPricedWinner.sportPricesADraw(event.sport) || odds.drawProbability != nil
        if side == .away, isThreeWaySport, odds.drawProbability == nil {
            // #5271 honesty: never invent an away percentage from 1 - home when draw is withheld.
            return .fallbackText
        }

        let observedAt = reading.observedAt
        let when: String
        if isLive {
            let isAged = isOffline || reading.phase == .lastRecorded
                || (observedAt.map { now.timeIntervalSince($0) > WatchRectangularReading.liveAgeThresholdSeconds } ?? true)
            if isAged, let observedAt {
                when = "As of \(WatchRectangularReading.asOfClock(observedAt, timeZone: timeZone))"
            } else if isAged {
                when = "Live"
            } else {
                when = art.liveBadgeText ?? "Live"
            }
        } else {
            if let start = art.commenceTime, start <= now {
                guard let observedAt else { return .fallbackText }
                when = "As of \(WatchRectangularReading.asOfClock(observedAt, timeZone: timeZone))"
            } else if isOffline || reading.phase == .lastRecorded {
                when = observedAt.map { "As of \(WatchRectangularReading.asOfClock($0, timeZone: timeZone))" } ?? "Pregame"
            } else if let start = art.commenceTime {
                when = WatchRectangularReading.upcomingStartClock(start, now: now, timeZone: timeZone)
            } else {
                when = "Pregame"
            }
        }

        let validScores: (away: Int, home: Int)? = {
            guard isLive, let s = art.scores, s.away >= 0, s.home >= 0 else { return nil }
            return (s.away, s.home)
        }()

        // Compute integer percentages via exact shared hero/contract rules.
        let homePercentInt: Int?
        let drawPercentInt: Int?
        let awayPercentInt: Int?
        if isThreeWaySport, let drawP = odds.drawProbability, drawP.isFinite, let awayP = odds.awayProbability, awayP.isFinite {
            let percents = renderedCardPercents([homeProb, drawP, awayP])
            homePercentInt = percents[0]
            drawPercentInt = percents[1]
            awayPercentInt = percents[2]
        } else if isThreeWaySport {
            homePercentInt = renderedPercent(homeProb)
            drawPercentInt = nil
            awayPercentInt = nil
        } else {
            let awayP = odds.awayProbability.flatMap { $0.isFinite ? $0 : nil } ?? (1.0 - homeProb)
            let hero = SavedWidgetReadingRules10875.HeroPair(
                away: awayP,
                home: homeProb,
                awayRenderedPercent: odds.awayRenderedPercent,
                homeRenderedPercent: odds.homeRenderedPercent,
                isOpeningLine: false
            )
            let pair = SavedWidgetReadingRules10875.heroPairPercents(hero, away: awayP, home: homeProb)
            homePercentInt = pair.home
            drawPercentInt = nil
            awayPercentInt = pair.away
        }

        guard let homePct = homePercentInt, (0...100).contains(homePct) else {
            return .fallbackText
        }

        let threeWay: WatchMatchupReading217.ThreeWay?
        let bigText: String
        let bigIsHome: Bool
        let ownerAbbr: String
        let ownerName: String

        let effectiveAwayProb = isThreeWaySport
            ? odds.awayProbability
            : (odds.awayProbability.flatMap { $0.isFinite ? $0 : nil } ?? (1.0 - homeProb))
        if side == nil, isThreeWaySport, let drawPct = drawPercentInt, let awayPct = awayPercentInt {
            let out = WatchMatchupReading217.resolveOutcomePresentation(
                homePercent: homePct,
                homeName: event.homeTeam,
                awayName: event.awayTeam,
                homeAbbreviation: art.home.short,
                awayAbbreviation: art.away.short,
                isThreeWay: true,
                drawPercent: drawPct,
                awayPercent: awayPct,
                homeSubOne: ExternalSurfaceProbabilityFormat.isSubOne(homeProb),
                homeAboveNinetyNine: ExternalSurfaceProbabilityFormat.isAboveNinetyNine(homeProb),
                drawSubOne: ExternalSurfaceProbabilityFormat.isSubOne(odds.drawProbability),
                drawAboveNinetyNine: ExternalSurfaceProbabilityFormat.isAboveNinetyNine(odds.drawProbability),
                awaySubOne: ExternalSurfaceProbabilityFormat.isSubOne(odds.awayProbability),
                awayAboveNinetyNine: ExternalSurfaceProbabilityFormat.isAboveNinetyNine(odds.awayProbability)
            )
            threeWay = out.threeWay
            bigText = out.bigText
            bigIsHome = out.bigIsHome
            ownerAbbr = out.ownerAbbr
            ownerName = out.ownerName
        } else if side == .away, let awayPct = awayPercentInt {
            threeWay = nil
            bigText = ExternalSurfaceProbabilityFormat.openWholePercent(
                awayPct,
                probability: effectiveAwayProb
            ) ?? ExternalSurfaceProbabilityFormat.missingProbabilityText
            bigIsHome = false
            ownerAbbr = art.away.short
            ownerName = event.awayTeam
        } else if side == .home || isThreeWaySport {
            threeWay = nil
            bigText = ExternalSurfaceProbabilityFormat.openWholePercent(
                homePct,
                probability: homeProb
            ) ?? ExternalSurfaceProbabilityFormat.missingProbabilityText
            bigIsHome = true
            ownerAbbr = art.home.short
            ownerName = event.homeTeam
        } else {
            let out = WatchMatchupReading217.resolveOutcomePresentation(
                homePercent: homePct,
                homeName: event.homeTeam,
                awayName: event.awayTeam,
                homeAbbreviation: art.home.short,
                awayAbbreviation: art.away.short,
                isThreeWay: false,
                drawPercent: nil,
                awayPercent: awayPercentInt,
                homeSubOne: ExternalSurfaceProbabilityFormat.isSubOne(homeProb),
                homeAboveNinetyNine: ExternalSurfaceProbabilityFormat.isAboveNinetyNine(homeProb),
                awaySubOne: ExternalSurfaceProbabilityFormat.isSubOne(effectiveAwayProb),
                awayAboveNinetyNine: ExternalSurfaceProbabilityFormat.isAboveNinetyNine(effectiveAwayProb)
            )
            threeWay = nil
            bigText = out.bigText
            bigIsHome = out.bigIsHome
            ownerAbbr = out.ownerAbbr
            ownerName = out.ownerName
        }

        let smallLine = when
        let matchup = "\(event.awayTeam) at \(event.homeTeam)"
        let scorePart = validScores.map { " \(event.awayTeam) \($0.away), \(event.homeTeam) \($0.home)." } ?? ""
        let speech: String = {
            if let tw = threeWay {
                return "\(matchup).\(scorePart) \(event.homeTeam) \(tw.homeText), Draw \(tw.drawText), \(event.awayTeam) \(tw.awayText). \(when). Open your game in Bain Luck."
            }
            return "\(matchup).\(scorePart) \(ownerName) \(bigText) to win. \(when). Open your game in Bain Luck."
        }()

        return .matchup(
            WatchMatchupReading217(
                stage: isLive ? .during : .before,
                away: buildSide(short: art.away.short, primaryHex: art.away.primaryHex, secondaryHex: art.away.secondaryHex, logo: awayLogo, score: validScores?.away, isWinner: false),
                home: buildSide(short: art.home.short, primaryHex: art.home.primaryHex, secondaryHex: art.home.secondaryHex, logo: homeLogo, score: validScores?.home, isWinner: false),
                bigText: bigText,
                bigOwnerLabel: ownerAbbr,
                bigIsHome: bigIsHome,
                smallLine: smallLine,
                accessibilityText: speech,
                threeWay: threeWay
            )
        )
    }

    /// Timeline entries for iOS `accessoryRectangular` so the `"As of"` boundary (121s),
    /// kickoff/midnight changes, and 3-hour post-final step-aside update on schedule without a network fetch.
    static func timelineDates(
        content: SavedWidgetContent10875,
        selection: SavedWidgetSelection10875?,
        now: Date,
        timeZone: TimeZone = .current
    ) -> [Date] {
        var dates = SavedWidgetTimeline10875.entryDates(content, selection: selection, now: now)
        guard case .detail(.game(let event), _) = content else { return dates }

        if EventState.isFinished(event.status) {
            if let finalObs = SavedWidgetDetailDecoding10875.date(event.scoreObservedAt)
                ?? SavedWidgetDetailDecoding10875.date(event.heroProbabilityObservedAt) {
                let step = finalObs.addingTimeInterval(WatchMatchupReading217.finalHoldSeconds)
                if step > now { dates.append(step) }
            }
        } else if event.status == "live" {
            if let obs = SavedWidgetDetailDecoding10875.date(event.heroProbabilityObservedAt) {
                let ageSwitch = obs.addingTimeInterval(WatchRectangularReading.liveAgeThresholdSeconds + 1)
                if ageSwitch > now { dates.append(ageSwitch) }
            }
        } else if let start = SavedWidgetDetailDecoding10875.date(event.commenceTime), start > now {
            var cal = Calendar(identifier: .gregorian)
            cal.timeZone = timeZone
            if !cal.isDate(start, inSameDayAs: now),
               let tomorrow = cal.date(byAdding: .day, value: 1, to: cal.startOfDay(for: now)),
               tomorrow > now, tomorrow < start {
                dates.append(tomorrow)
            }
            let startDay = cal.startOfDay(for: start)
            if startDay > now, startDay < start {
                dates.append(startDay)
            }
            dates.append(start)
        }
        return Array(Set(dates)).sorted()
    }
}

#if os(iOS)
/// Distinct post-final (>3 hours) message on iPhone Lock Screen rectangle so an ended
/// game never looks like "Choose a saved game or market" (#13339 / #13432).
struct SavedLockPostFinalEndedView13432: View {
    let title: String

    var body: some View {
        ViewThatFits(in: .vertical) {
            tier(titleSize: 12, headlineSize: 14, detailSize: 10.5, spacing: 1.5)
            tier(titleSize: 10.5, headlineSize: 12.5, detailSize: 9.5, spacing: 1)
            tier(titleSize: 9.5, headlineSize: 11, detailSize: 8.5, spacing: 0.5)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title). Game ended. Open Bain Luck.")
        .accessibilityIdentifier("lockscreen.matchup.final-ended")
    }

    private func tier(titleSize: CGFloat, headlineSize: CGFloat, detailSize: CGFloat, spacing: CGFloat) -> some View {
        HStack(alignment: .center, spacing: 6) {
            Image(systemName: "exclamationmark.circle")
                .font(.system(size: max(14, headlineSize + 2), weight: .semibold))
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: spacing) {
                Text(title)
                    .font(HeadlineStyleTable199.quietText(.lockScreen, scaledSize: titleSize))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                Text("Game ended")
                    .font(HeadlineStyleTable199.names(.lockScreen, scaledSize: headlineSize))
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
                    .widgetAccentable()
                Text("Open Bain Luck")
                    .font(HeadlineStyleTable199.quietText(.lockScreen, scaledSize: detailSize))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .minimumScaleFactor(0.75)
            }
        }
    }
}

/// Shared market lock-screen body (#13160 + #13432 sheet parity) so tests and
/// `SavedLockRectangle12466` render the exact same multi-tier wrapping layout.
struct SavedLockMarketBody13432: View {
    let shortSubject: String
    let outcomeLabel: String?
    let valueText: String?
    let footer: String

    var body: some View {
        ViewThatFits(in: .vertical) {
            tier(subjectSize: 11.5, outcomeSize: 10.5, figureSize: 11.5, footerSize: 9.5, spacing: 1.5)
            tier(subjectSize: 10, outcomeSize: 9.5, figureSize: 10.5, footerSize: 8.5, spacing: 1)
            tier(subjectSize: 9, outcomeSize: 8.5, figureSize: 9.5, footerSize: 8, spacing: 0.5)
            tier(subjectSize: 8, outcomeSize: 8, figureSize: 9, footerSize: 7.5, spacing: 0.5)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func tier(
        subjectSize: CGFloat,
        outcomeSize: CGFloat,
        figureSize: CGFloat,
        footerSize: CGFloat,
        spacing: CGFloat
    ) -> some View {
        VStack(alignment: .leading, spacing: spacing) {
            Text(shortSubject)
                .font(HeadlineStyleTable199.names(.widget, scaledSize: subjectSize))
                .lineLimit(nil)
                .fixedSize(horizontal: false, vertical: true)
                .widgetAccentable()
            if let outcomeLabel, let valueText {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Text(outcomeLabel)
                        .font(HeadlineStyleTable199.names(.widget, scaledSize: outcomeSize))
                        .foregroundStyle(.secondary)
                        .lineLimit(nil)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 2)
                    Text(valueText)
                        .font(HeadlineStyleTable199.secondNumbers(.widget, prominent: true, scaledSize: figureSize))
                        .lineLimit(1)
                        .fixedSize(horizontal: true, vertical: false)
                }
            }
            Text(footer)
                .font(HeadlineStyleTable199.quietText(.widget, scaledSize: footerSize))
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Shared cannot-show / empty-state lock-screen message layout (#13080 + #13194 + #13432).
struct SavedLockMessageTierView13432: View {
    let titleText: Text
    let detailText: Text
    let titleSize: CGFloat?
    let detailSize: CGFloat?
    let spacing: CGFloat

    var body: some View {
        VStack(alignment: .leading, spacing: spacing) {
            Group {
                if let titleSize {
                    titleText.font(HeadlineStyleTable199.names(.widget, scaledSize: titleSize))
                } else {
                    titleText.font(.headline)
                }
            }
            .lineLimit(nil)
            .fixedSize(horizontal: false, vertical: true)

            Group {
                if let detailSize {
                    detailText.font(HeadlineStyleTable199.quietText(.widget, scaledSize: detailSize))
                } else {
                    detailText.font(.caption2)
                }
            }
            .foregroundStyle(.secondary)
            .lineLimit(nil)
            .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct SavedLockMessageRectangleView13432: View {
    let title: String
    let detail: String

    var body: some View {
        ViewThatFits(in: .vertical) {
            SavedLockMessageTierView13432(titleText: Text(title), detailText: Text(detail), titleSize: nil, detailSize: nil, spacing: 1)
            SavedLockMessageTierView13432(titleText: Text(title), detailText: Text(detail), titleSize: 17, detailSize: 12, spacing: 1)
            SavedLockMessageTierView13432(titleText: Text(title), detailText: Text(detail), titleSize: 15, detailSize: 11, spacing: 1)
            SavedLockMessageTierView13432(titleText: Text(title), detailText: Text(detail), titleSize: 12.5, detailSize: 10.5, spacing: 1)
            SavedLockMessageTierView13432(titleText: Text(title), detailText: Text(detail), titleSize: 11, detailSize: 9.5, spacing: 0.5)
            SavedLockMessageTierView13432(titleText: Text(title), detailText: Text(detail), titleSize: 9.5, detailSize: 8.5, spacing: 0.5)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}
#endif
