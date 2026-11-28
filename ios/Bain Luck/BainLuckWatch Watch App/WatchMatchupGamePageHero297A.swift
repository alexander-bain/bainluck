import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#endif
#if DEBUG && canImport(Bain_Luck)
@testable import Bain_Luck
#endif

/// Ruling 297: A (#12641) — Watch game page in the Matchup look for 1.0.7
/// (Looks 1A Scheduled, 1B Live, 1C Final at 41 mm `176x215 pt` and 45 mm `198x242 pt`).
///
/// Pure model so iOS unit tests, macOS builds, and watchOS simulator/device builds
/// all verify the exact rules with zero duplicated business logic.
nonisolated struct WatchMatchupGameHeroModel297A: Equatable, Sendable {
    enum Stage: String, Equatable, Sendable {
        case before
        case during
        case after
        case closedUnverified
    }

    struct Side: Equatable, Sendable {
        let abbreviation: String
        let shortName: String
        let teamID: Int?
        let crestPNG: Data?
        let fillHex: String
        let inkHex: String
        let barHex: String
        let currentPercentText: String?
        let currentShare: Double?
        let score: Int?
        let pregameText: String?
        let isWinner: Bool
        let isLoser: Bool
    }

    let stage: Stage
    let topBadgeText: String
    let isLive: Bool
    let isThreeWaySoccer: Bool
    let isTiedFinal: Bool
    let away: Side
    let home: Side
    let drawPercentText: String?
    let drawShare: Double?
    let drawPregameText: String?
    let centerScoreText: String?
    let liveScoreExplanation: String?
    let finalScoreUnavailable: Bool
    let probabilityUnavailableText: String?
    let bottomSummaryText: String?
    let scoreAsOfText: String?
    let probabilityAsOfText: String?

    var showsProbabilityBar: Bool {
        (stage == .before || stage == .during) && probabilityUnavailableText == nil && home.currentShare != nil
    }

    static func build(
        from game: WatchSelectedGame,
        now: Date = Date(),
        timeZone: TimeZone = .current,
        crestForTeamID: (Int) -> Data? = { WatchMatchupCrests217.data(teamID: $0) }
    ) -> WatchMatchupGameHeroModel297A {
        let shortPair = TeamShortName.shortPair(
            away: game.awayTeam,
            home: game.homeTeam,
            sportKey: game.sportKey
        )
        let derivedAbbrs = TeamShortName.abbreviationPair(
            away: game.awayTeam,
            home: game.homeTeam,
            awayServed: game.awayCompactIdentity?.abbreviation,
            homeServed: game.homeCompactIdentity?.abbreviation,
            sportKey: game.sportKey
        )
        let awayAbbr = (game.awayCompactIdentity?.isValid == true)
            ? game.awayCompactIdentity!.abbreviation
            : derivedAbbrs.away
        let homeAbbr = (game.homeCompactIdentity?.isValid == true)
            ? game.homeCompactIdentity!.abbreviation
            : derivedAbbrs.home

        let bgPair = ProbabilityBarPalette.pair(
            awayHex: game.awayPrimaryColor,
            homeHex: game.homePrimaryColor,
            awaySecondaryHex: game.awaySecondaryColor
        )
        let inkPair = TeamTextContrast.darkSurfaceColorHexes(
            awayHex: game.awayPrimaryColor,
            homeHex: game.homePrimaryColor,
            awaySecondaryHex: game.awaySecondaryColor,
            homeSecondaryHex: game.homeSecondaryColor
        )
        let awayTextInk = Self.readableHeroInkHex(inkPair.away, overFillHex: bgPair.away)
        let homeTextInk = Self.readableHeroInkHex(inkPair.home, overFillHex: bgPair.home)

        let awayCrest = game.awayCompactIdentity.flatMap { crestForTeamID($0.teamID) }
        let homeCrest = game.homeCompactIdentity.flatMap { crestForTeamID($0.teamID) }

        let drawSport = game.sportKey.map { DrawPricedWinner.sportPricesADraw($0) } ?? false
        let isThreeWay = drawSport || game.drawProbability != nil || game.prematchDrawProbability != nil

        let scoreAsOf = Self.asOfLine(prefix: "Score", observedAt: game.scoreObservedAt, now: now, timeZone: timeZone)
        let probAsOf = Self.asOfLine(prefix: "Chance", observedAt: game.probabilityObservedAt, now: now, timeZone: timeZone)

        // MARK: - Closed (unverified)
        if game.isClosed {
            let validScores = Self.validScorePair(away: game.awayScore, home: game.homeScore)
            return WatchMatchupGameHeroModel297A(
                stage: .closedUnverified,
                topBadgeText: "CLOSED",
                isLive: false,
                isThreeWaySoccer: isThreeWay,
                isTiedFinal: false,
                away: Side(
                    abbreviation: awayAbbr, shortName: shortPair.away,
                    teamID: game.awayCompactIdentity?.teamID, crestPNG: awayCrest,
                    fillHex: bgPair.away, inkHex: awayTextInk, barHex: inkPair.away,
                    currentPercentText: nil, currentShare: nil,
                    score: validScores?.away ?? game.awayScore,
                    pregameText: nil, isWinner: false, isLoser: false
                ),
                home: Side(
                    abbreviation: homeAbbr, shortName: shortPair.home,
                    teamID: game.homeCompactIdentity?.teamID, crestPNG: homeCrest,
                    fillHex: bgPair.home, inkHex: homeTextInk, barHex: inkPair.home,
                    currentPercentText: nil, currentShare: nil,
                    score: validScores?.home ?? game.homeScore,
                    pregameText: nil, isWinner: false, isLoser: false
                ),
                drawPercentText: nil,
                drawShare: nil,
                drawPregameText: nil,
                centerScoreText: validScores.map { "\($0.away)\u{2013}\($0.home)" },
                liveScoreExplanation: nil,
                finalScoreUnavailable: validScores == nil,
                probabilityUnavailableText: nil,
                bottomSummaryText: "Closed \u{00B7} result unverified",
                scoreAsOfText: scoreAsOf,
                probabilityAsOfText: nil
            )
        }

        // MARK: - Final (Look 1C — Ruling 209: Pregame N%, never Closed N%, no bar)
        if game.isFinal {
            let validScores = Self.validScorePair(away: game.awayScore, home: game.homeScore)
            let awayWon = validScores.map { $0.away > $0.home } ?? false
            let homeWon = validScores.map { $0.home > $0.away } ?? false
            let tiedFinal = validScores.map { $0.away == $0.home } ?? false
            let pregamePair = game.pregameRenderedPercents
            let drawPregamePct = renderedPercent(game.prematchDrawProbability)
            let awayPregameText = pregamePair.away.flatMap { pct in
                ExternalSurfaceProbabilityFormat.openWholePercent(pct, probability: game.prematchAwayProbability)
            }.map { "Pregame \($0)" }
            let homePregameText = pregamePair.home.flatMap { pct in
                ExternalSurfaceProbabilityFormat.openWholePercent(pct, probability: game.prematchHomeProbability)
            }.map { "Pregame \($0)" }
            let drawPregameText = drawPregamePct.flatMap { pct in
                ExternalSurfaceProbabilityFormat.openWholePercent(pct, probability: game.prematchDrawProbability)
            }.map { "Pregame Draw \($0)" }
            return WatchMatchupGameHeroModel297A(
                stage: .after,
                topBadgeText: "FINAL",
                isLive: false,
                isThreeWaySoccer: isThreeWay,
                isTiedFinal: tiedFinal,
                away: Side(
                    abbreviation: awayAbbr, shortName: shortPair.away,
                    teamID: game.awayCompactIdentity?.teamID, crestPNG: awayCrest,
                    fillHex: bgPair.away, inkHex: awayTextInk, barHex: inkPair.away,
                    currentPercentText: nil, currentShare: nil,
                    score: validScores?.away ?? game.awayScore.flatMap { $0 >= 0 ? $0 : nil },
                    pregameText: awayPregameText,
                    isWinner: awayWon,
                    isLoser: homeWon
                ),
                home: Side(
                    abbreviation: homeAbbr, shortName: shortPair.home,
                    teamID: game.homeCompactIdentity?.teamID, crestPNG: homeCrest,
                    fillHex: bgPair.home, inkHex: homeTextInk, barHex: inkPair.home,
                    currentPercentText: nil, currentShare: nil,
                    score: validScores?.home ?? game.homeScore.flatMap { $0 >= 0 ? $0 : nil },
                    pregameText: homePregameText,
                    isWinner: homeWon,
                    isLoser: awayWon
                ),
                drawPercentText: nil,
                drawShare: nil,
                drawPregameText: drawPregameText,
                centerScoreText: validScores.map { "\($0.away)\u{2013}\($0.home)" },
                liveScoreExplanation: nil,
                finalScoreUnavailable: validScores == nil,
                probabilityUnavailableText: nil,
                bottomSummaryText: nil,
                scoreAsOfText: nil,
                probabilityAsOfText: nil
            )
        }

        // MARK: - Before (Look 1A) or During (Look 1B)
        let isLive = game.isLive
        let stage: Stage = isLive ? .during : .before

        let validHomeScore = game.homeScore.flatMap { $0 >= 0 ? $0 : nil }
        let validAwayScore = game.awayScore.flatMap { $0 >= 0 ? $0 : nil }
        let centerScoreText: String? = {
            guard isLive || (validAwayScore != nil && validHomeScore != nil) else { return nil }
            if let a = validAwayScore, let h = validHomeScore {
                return "\(a)\u{2013}\(h)"
            }
            return nil
        }()
        let liveScoreExplanation: String? = {
            guard isLive else { return nil }
            if validAwayScore == nil && validHomeScore == nil { return "Score unavailable" }
            if validAwayScore == nil || validHomeScore == nil { return "One score unavailable" }
            return nil
        }()

        // Whole-number current chances (no manufacturing away on 3-way soccer).
        let chances = Self.resolveCurrentChances(game: game, isThreeWay: isThreeWay)

        let topBadge: String = {
            if isLive {
                if let clock = game.liveClockText?.trimmingCharacters(in: .whitespacesAndNewlines), !clock.isEmpty {
                    return clock
                }
                return "Live"
            }
            if let start = game.commenceTime {
                return Self.scheduledBadgeClock(start, now: now, timeZone: timeZone)
            }
            return "Scheduled \u{00B7} time unavailable"
        }()

        let bottomText: String? = {
            guard stage == .before, let probObs = game.probabilityObservedAt else { return nil }
            if now.timeIntervalSince(probObs) <= WatchRectangularReading.liveAgeThresholdSeconds,
               let compact = WatchObservationAge(observedAt: probObs, now: now).compactText {
                return "As of \(compact)"
            }
            return "As of \(Self.clockText(probObs, timeZone: timeZone))"
        }()

        return WatchMatchupGameHeroModel297A(
            stage: stage,
            topBadgeText: topBadge,
            isLive: isLive,
            isThreeWaySoccer: isThreeWay,
            isTiedFinal: false,
            away: Side(
                abbreviation: awayAbbr, shortName: shortPair.away,
                teamID: game.awayCompactIdentity?.teamID, crestPNG: awayCrest,
                fillHex: bgPair.away, inkHex: awayTextInk, barHex: inkPair.away,
                currentPercentText: chances.awayText, currentShare: chances.awayShare,
                score: validAwayScore, pregameText: nil, isWinner: false, isLoser: false
            ),
            home: Side(
                abbreviation: homeAbbr, shortName: shortPair.home,
                teamID: game.homeCompactIdentity?.teamID, crestPNG: homeCrest,
                fillHex: bgPair.home, inkHex: homeTextInk, barHex: inkPair.home,
                currentPercentText: chances.homeText, currentShare: chances.homeShare,
                score: validHomeScore, pregameText: nil, isWinner: false, isLoser: false
            ),
            drawPercentText: chances.drawText,
            drawShare: chances.drawShare,
            drawPregameText: nil,
            centerScoreText: centerScoreText,
            liveScoreExplanation: liveScoreExplanation,
            finalScoreUnavailable: false,
            probabilityUnavailableText: chances.homeText == nil ? ExternalSurfaceProbabilityFormat.missingProbabilityText : nil,
            bottomSummaryText: bottomText,
            scoreAsOfText: (isLive || validAwayScore != nil || validHomeScore != nil) ? scoreAsOf : nil,
            probabilityAsOfText: (stage == .during && chances.homeText != nil) ? probAsOf : nil
        )
    }

    private struct ResolvedChances {
        let awayText: String?
        let awayShare: Double?
        let drawText: String?
        let drawShare: Double?
        let homeText: String?
        let homeShare: Double?
    }

    private static func resolveCurrentChances(game: WatchSelectedGame, isThreeWay: Bool) -> ResolvedChances {
        guard game.showsForecast, let homeP = game.homeProbability else {
            return ResolvedChances(awayText: nil, awayShare: nil, drawText: nil, drawShare: nil, homeText: nil, homeShare: nil)
        }
        let trimmedSport = game.sportKey?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let hasSport = !trimmedSport.isEmpty
        if isThreeWay {
            // Keep 3-way parity with WatchWristTileModel12616 / DrawPricedWinner:
            // never surface an unverified away percentage when drawProbability is absent.
            let hasExplicitDraw = game.drawProbability != nil
            let homePct = game.homeRenderedPercent
            let awayPct = hasExplicitDraw ? renderedPercent(game.awayProbability) : nil
            let drawPct = renderedPercent(game.drawProbability)
            let homeShare = min(max(homeP, 0), 1)
            let drawShare = game.drawProbability.map { min(max($0, 0), 1) }
            let awayShare = hasExplicitDraw ? game.awayProbability.map { min(max($0, 0), 1) } : nil
            return ResolvedChances(
                awayText: awayPct.flatMap { ExternalSurfaceProbabilityFormat.openWholePercent($0, probability: game.awayProbability) },
                awayShare: awayShare,
                drawText: drawPct.flatMap { ExternalSurfaceProbabilityFormat.openWholePercent($0, probability: game.drawProbability) },
                drawShare: drawShare,
                homeText: homePct.flatMap { ExternalSurfaceProbabilityFormat.openWholePercent($0, probability: homeP) },
                homeShare: homeShare
            )
        }
        // Unknown/unclassified sport with no draw reading: match WatchWristTileModel12616
        // and WatchSelectedGame.homeRenderedPercent (scalar home%, never assume 2-way duel).
        guard hasSport else {
            return ResolvedChances(
                awayText: nil,
                awayShare: nil,
                drawText: nil,
                drawShare: nil,
                homeText: game.homeRenderedPercent.flatMap { ExternalSurfaceProbabilityFormat.openWholePercent($0, probability: homeP) },
                homeShare: min(max(homeP, 0), 1)
            )
        }
        // Two-way non-draw market: keep served pair honest and never invent away from nil.
        let pair = renderedDuelPercents(away: game.awayProbability, home: homeP)
        return ResolvedChances(
            awayText: pair[0].flatMap { ExternalSurfaceProbabilityFormat.openWholePercent($0, probability: game.awayProbability) },
            awayShare: game.awayProbability.map { min(max($0, 0), 1) },
            drawText: nil,
            drawShare: nil,
            homeText: pair[1].flatMap { ExternalSurfaceProbabilityFormat.openWholePercent($0, probability: homeP) },
            homeShare: min(max(homeP, 0), 1)
        )
    }

    private static func validScorePair(away: Int?, home: Int?) -> (away: Int, home: Int)? {
        guard let away, let home, away >= 0, home >= 0 else { return nil }
        return (away, home)
    }

    private static func scheduledBadgeClock(_ start: Date, now: Date, timeZone: TimeZone) -> String {
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = timeZone
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        if cal.isDate(start, inSameDayAs: now) {
            f.dateFormat = "h:mm a"
            return "Today \u{00B7} \(f.string(from: start))"
        }
        f.dateFormat = "EEE h:mm a"
        return f.string(from: start)
    }

    private static func clockText(_ date: Date, timeZone: TimeZone) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = timeZone
        f.dateFormat = "h:mm a"
        return f.string(from: date)
    }

    private static func asOfLine(prefix: String, observedAt: Date?, now: Date, timeZone: TimeZone) -> String? {
        guard let observedAt else { return nil }
        if now.timeIntervalSince(observedAt) <= WatchRectangularReading.liveAgeThresholdSeconds,
           let compact = WatchObservationAge(observedAt: observedAt, now: now).compactText {
            return "\(prefix) as of \(compact)"
        }
        return "\(prefix) as of \(clockText(observedAt, timeZone: timeZone))"
    }

    /// Relative luminance of the hero scrim-composited team field (`0.54` black
    /// scrim over `fillHex`, the midpoint of `diagonalSplitBackground`).
    static func scrimSurfaceLuminance(fillHex: String) -> Double {
        guard let rgb = ProbabilityBarPalette.rgb(fillHex) else {
            return TeamTextContrast.darkSurfaceLuminance
        }
        let retain = 1.0 - 0.54
        func linearChannel(_ v: Int) -> Double {
            let srgb = (Double(v) / 255.0) * retain
            return srgb <= 0.04045 ? srgb / 12.92 : pow((srgb + 0.055) / 1.055, 2.4)
        }
        return 0.2126 * linearChannel(rgb.r) + 0.7152 * linearChannel(rgb.g) + 0.0722 * linearChannel(rgb.b)
    }

    /// Ensures percentage text ink satisfies `TeamTextContrast.minimumRatio`
    /// (`3.0:1`) directly against its own scrim-darkened team field; promotes
    /// failing inks (e.g. Arsenal red on dark red) to `"#FFFFFF"`.
    static func readableHeroInkHex(_ candidateHex: String, overFillHex fillHex: String) -> String {
        let surfaceL = scrimSurfaceLuminance(fillHex: fillHex)
        if let ratio = TeamTextContrast.contrast(candidateHex, againstSurfaceLuminance: surfaceL),
           ratio >= TeamTextContrast.minimumRatio {
            return candidateHex
        }
        return "#FFFFFF"
    }
}

/// Diagonal two-team color split background + crest discs + probability bar (Looks 1A/1B/1C).
struct WatchMatchupGamePageHeroView297A: View {
    let model: WatchMatchupGameHeroModel297A
    var caseWidth: CGFloat = 186
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    private var isCompact41mm: Bool { caseWidth < 188 }
    private var isCompactFinal: Bool { model.stage == .after && !dynamicTypeSize.isAccessibilitySize }
    private var isCompactScheduled: Bool { model.stage == .before && !dynamicTypeSize.isAccessibilitySize }
    private var crestSize: CGFloat {
        if isCompactFinal {
            return isCompact41mm ? 22 : 26
        }
        if isCompactScheduled {
            return isCompact41mm ? 24 : 28
        }
        return isCompact41mm ? 28 : 32
    }

    var body: some View {
        VStack(alignment: .leading, spacing: isCompactFinal ? 6 : (isCompactScheduled ? 5 : 8)) {
            heroCard
            observationLines
        }
    }

    private var heroCard: some View {
        VStack(spacing: isCompactFinal ? (isCompact41mm ? 3 : 4) : (isCompactScheduled ? (isCompact41mm ? 4 : 6) : (isCompact41mm ? 7 : 9))) {
            topBadgeRow

            if dynamicTypeSize.isAccessibilitySize {
                accessibilityMatchupStack
            } else {
                standardMatchupRow
                if model.stage == .after {
                    finalNumbersRow
                } else if model.stage == .before || model.stage == .during {
                    chancesRow
                }
            }

            if model.showsProbabilityBar {
                splitProbabilityBar
            }

            if let unavailable = model.probabilityUnavailableText,
               model.stage == .before || model.stage == .during {
                Text(unavailable)
                    .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13 : 10.5, weight: .semibold))
                    .foregroundStyle(.white.opacity(0.85))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.game.hero.probability-unavailable")
            }

            if let liveScoreExplanation = model.liveScoreExplanation {
                Text(liveScoreExplanation)
                    .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13 : 10.5, weight: .medium))
                    .foregroundStyle(.white.opacity(0.82))
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier("watch.game.hero.score-unavailable")
            } else if model.finalScoreUnavailable, model.stage == .after || model.stage == .closedUnverified {
                Text("Final score unavailable")
                    .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13 : 10.5, weight: .medium))
                    .foregroundStyle(.white.opacity(0.82))
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let bottom = model.bottomSummaryText {
                Text(bottom)
                    .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13 : (isCompact41mm ? 9.5 : 10), weight: .semibold))
                    .foregroundStyle(.white.opacity(0.86))
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, isCompactScheduled ? 0 : 1)
                    .accessibilityIdentifier("watch.game.hero.bottom")
            }
        }
        .padding(.horizontal, isCompactFinal && isCompact41mm ? 7 : (isCompact41mm ? 8 : 10))
        .padding(.vertical, isCompactFinal ? (isCompact41mm ? 5 : 7) : (isCompactScheduled ? (isCompact41mm ? 6 : 8) : (isCompact41mm ? 9 : 11)))
        .frame(maxWidth: .infinity)
        .background(diagonalSplitBackground)
        .clipShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        .overlay(
            RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(Color.white.opacity(0.14), lineWidth: 1)
        )
    }

    // MARK: - Diagonal Split Background (Look 1A / 1B / 1C)

    private var diagonalSplitBackground: some View {
        ZStack {
            Self.rgbColor("#0C0E13")
            GeometryReader { geo in
                let w = geo.size.width
                let h = geo.size.height
                ZStack {
                    Path { p in
                        p.move(to: .zero)
                        p.addLine(to: CGPoint(x: w * 0.72, y: 0))
                        p.addLine(to: CGPoint(x: w * 0.28, y: h))
                        p.addLine(to: CGPoint(x: 0, y: h))
                        p.closeSubpath()
                    }
                    .fill(Self.rgbColor(model.away.fillHex))

                    Path { p in
                        p.move(to: CGPoint(x: w * 0.72, y: 0))
                        p.addLine(to: CGPoint(x: w, y: 0))
                        p.addLine(to: CGPoint(x: w, y: h))
                        p.addLine(to: CGPoint(x: w * 0.28, y: h))
                        p.closeSubpath()
                    }
                    .fill(Self.rgbColor(model.home.fillHex))

                    // Subtle seam glow + dark contrast scrim so text/crests stay sharp across all team colors.
                    LinearGradient(
                        colors: [Color.black.opacity(0.46), Color.black.opacity(0.62)],
                        startPoint: .top,
                        endPoint: .bottom
                    )
                }
            }
        }
    }

    // MARK: - Top Badge

    private var topBadgeRow: some View {
        HStack(spacing: 4) {
            if model.isLive {
                Circle()
                    .fill(Color.white)
                    .frame(width: 5, height: 5)
            } else if model.stage == .before {
                Image(systemName: "star.fill")
                    .font(.system(size: 8, weight: .bold))
            }
            Text(model.topBadgeText)
                .font(.system(
                    size: dynamicTypeSize.isAccessibilitySize
                        ? 13
                        : (isCompactFinal ? (isCompact41mm ? 9.5 : 10.5) : (isCompact41mm ? 10.5 : 11)),
                    weight: .bold
                ))
                .monospacedDigit()
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(.center)
        }
        .foregroundStyle(Color.white)
        .padding(.horizontal, isCompactFinal ? 7 : 8)
        .padding(.vertical, isCompactFinal ? 1.5 : (isCompactScheduled ? 2 : 3))
        .background(
            Capsule().fill(
                model.isLive
                    ? Self.rgbColor("#DC2626")
                    : Color.black.opacity(0.48)
            )
        )
        .accessibilityIdentifier("watch.game.hero.badge")
    }

    // MARK: - Matchup Row (Crests + Center Score/AT on top, Identities below across full half-width)

    private var standardMatchupRow: some View {
        VStack(spacing: isCompactFinal ? (isCompact41mm ? 2 : 3) : (isCompactScheduled ? (isCompact41mm ? 2 : 3) : (isCompact41mm ? 4 : 5))) {
            HStack(alignment: .center, spacing: 4) {
                crestDisc(model.away, size: crestSize)
                Spacer(minLength: 4)
                centerConnector
                Spacer(minLength: 4)
                crestDisc(model.home, size: crestSize)
            }
            HStack(alignment: .top, spacing: isCompactFinal ? 4 : 6) {
                teamCodeAndName(model.away, alignment: .leading)
                    .frame(maxWidth: .infinity, alignment: .leading)
                teamCodeAndName(model.home, alignment: .trailing)
                    .frame(maxWidth: .infinity, alignment: .trailing)
            }
        }
    }

    private func teamCodeAndName(_ side: WatchMatchupGameHeroModel297A.Side, alignment: HorizontalAlignment) -> some View {
        let textAlign: TextAlignment = alignment == .leading ? .leading : .trailing
        return VStack(alignment: alignment, spacing: isCompactFinal ? 0 : 0.5) {
            Text(side.abbreviation)
                .font(.system(size: isCompactFinal ? (isCompact41mm ? 11.5 : 12.5) : (isCompact41mm ? 12 : 13), weight: .heavy, design: .rounded))
                .foregroundStyle(Color.white)
                .fixedSize(horizontal: true, vertical: false)
            if side.shortName.caseInsensitiveCompare(side.abbreviation) != .orderedSame {
                Text(side.shortName)
                    .font(.system(size: isCompactFinal ? (isCompact41mm ? 9.5 : 10) : (isCompact41mm ? 10 : 10.5), weight: .medium))
                    .foregroundStyle(Color.white.opacity(0.86))
                    .multilineTextAlignment(textAlign)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder
    private var centerConnector: some View {
        if let scoreText = model.centerScoreText {
            Text(scoreText)
                .font(.system(size: isCompactFinal ? (isCompact41mm ? 11 : 12) : (isCompact41mm ? 12 : 13), weight: .heavy, design: .rounded).monospacedDigit())
                .foregroundStyle(Color.white)
                .padding(.horizontal, isCompactFinal ? 6 : 7)
                .padding(.vertical, isCompactFinal ? 2 : 3)
                .background(Capsule().fill(Color.black.opacity(0.58)))
                .fixedSize()
                .accessibilityIdentifier("watch.game.hero.score-pill")
        } else if model.stage == .before {
            Text("AT")
                .font(.system(size: 10, weight: .bold))
                .foregroundStyle(Color.white.opacity(0.78))
                .fixedSize()
        }
    }

    // MARK: - Current Chances (Looks 1A / 1B)

    @ViewBuilder
    private var chancesRow: some View {
        if model.isThreeWaySoccer {
            threeWayChancesRow
        } else if model.away.currentPercentText != nil || model.home.currentPercentText != nil {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                if let awayPct = model.away.currentPercentText {
                    Text(awayPct)
                        .font(.system(size: isCompactScheduled ? (isCompact41mm ? 22 : 26) : (isCompact41mm ? 24 : 28), weight: .black, design: .rounded).monospacedDigit())
                        .foregroundStyle(Self.rgbColor(model.away.inkHex))
                        .minimumScaleFactor(0.75)
                        .lineLimit(1)
                }
                Spacer(minLength: 4)
                if let homePct = model.home.currentPercentText {
                    Text(homePct)
                        .font(.system(size: isCompactScheduled ? (isCompact41mm ? 22 : 26) : (isCompact41mm ? 24 : 28), weight: .black, design: .rounded).monospacedDigit())
                        .foregroundStyle(Self.rgbColor(model.home.inkHex))
                        .minimumScaleFactor(0.75)
                        .lineLimit(1)
                }
            }
            .accessibilityIdentifier("watch.game.hero.chances")
        }
    }

    private var threeWayChancesRow: some View {
        HStack(alignment: .firstTextBaseline, spacing: 4) {
            if let awayPct = model.away.currentPercentText {
                threeWayCell(label: model.away.abbreviation, value: awayPct, ink: Self.rgbColor(model.away.inkHex))
            }
            if let drawPct = model.drawPercentText {
                threeWayCell(label: "Draw", value: drawPct, ink: Color.white.opacity(0.92))
            }
            if let homePct = model.home.currentPercentText {
                threeWayCell(label: model.home.abbreviation, value: homePct, ink: Self.rgbColor(model.home.inkHex))
            }
        }
        .frame(maxWidth: .infinity)
        .accessibilityIdentifier("watch.game.hero.chances-3way")
    }

    private func threeWayCell(label: String, value: String, ink: Color) -> some View {
        VStack(spacing: 1) {
            Text(value)
                .font(.system(size: isCompact41mm ? 16 : 18, weight: .black, design: .rounded).monospacedDigit())
                .foregroundStyle(ink)
                .lineLimit(1)
                .minimumScaleFactor(0.75)
            Text(label)
                .font(.system(size: 9.5, weight: .semibold))
                .foregroundStyle(Color.white.opacity(0.82))
                .lineLimit(1)
        }
        .frame(maxWidth: .infinity)
    }

    // MARK: - Final Scores & Pregame (Look 1C)

    private var finalNumbersRow: some View {
        VStack(spacing: isCompact41mm ? 1 : 2) {
            if model.away.isWinner || model.away.isLoser || model.home.isWinner || model.home.isLoser || model.isTiedFinal {
                HStack(alignment: .center, spacing: 6) {
                    finalOutcomeBadge(model.away)
                        .frame(maxWidth: .infinity, alignment: .leading)
                    finalOutcomeBadge(model.home)
                        .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            if model.away.score != nil || model.home.score != nil {
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Group {
                        if let awayScore = model.away.score {
                            Text("\(awayScore)")
                                .font(.system(size: isCompact41mm ? 19 : 22, weight: .black, design: .rounded).monospacedDigit())
                                .foregroundStyle(model.away.isLoser ? Color.white.opacity(0.75) : Color.white)
                                .lineLimit(1)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Group {
                        if let homeScore = model.home.score {
                            Text("\(homeScore)")
                                .font(.system(size: isCompact41mm ? 19 : 22, weight: .black, design: .rounded).monospacedDigit())
                                .foregroundStyle(model.home.isLoser ? Color.white.opacity(0.75) : Color.white)
                                .lineLimit(1)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            if model.away.pregameText != nil || model.home.pregameText != nil {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    Group {
                        if let awayPre = model.away.pregameText {
                            Text(awayPre)
                                .font(.system(size: isCompact41mm ? 9.5 : 10.5, weight: .semibold).monospacedDigit())
                                .foregroundStyle(Color.white.opacity(0.86))
                                .multilineTextAlignment(.leading)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Group {
                        if let homePre = model.home.pregameText {
                            Text(homePre)
                                .font(.system(size: isCompact41mm ? 9.5 : 10.5, weight: .semibold).monospacedDigit())
                                .foregroundStyle(Color.white.opacity(0.86))
                                .multilineTextAlignment(.trailing)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .trailing)
                }
            }
            if let drawPre = model.drawPregameText, !model.away.isWinner && !model.home.isWinner {
                Text(drawPre)
                    .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13 : (isCompact41mm ? 9.5 : 10), weight: .semibold).monospacedDigit())
                    .foregroundStyle(Color.white.opacity(0.88))
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 1)
            }
        }
        .accessibilityIdentifier("watch.game.hero.final-row")
    }

    @ViewBuilder
    private func finalOutcomeBadge(_ side: WatchMatchupGameHeroModel297A.Side) -> some View {
        if side.isWinner {
            HStack(spacing: 3) {
                Image(systemName: "checkmark")
                    .font(.system(size: 8, weight: .black))
                Text("WON")
                    .font(.system(size: 9, weight: .black))
            }
            .foregroundStyle(Color.black)
            .padding(.horizontal, 5)
            .padding(.vertical, 1.5)
            .background(Capsule().fill(Self.rgbColor("#34D399")))
        } else if side.isLoser {
            Text("LOST")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(Color.white.opacity(0.68))
                .padding(.vertical, 1.5)
        } else if model.isTiedFinal {
            Text("DRAW")
                .font(.system(size: 9, weight: .bold))
                .foregroundStyle(Color.white.opacity(0.82))
                .padding(.vertical, 1.5)
        }
    }

    // MARK: - AX5 Stacked Layout (Zero "...")

    private var accessibilityMatchupStack: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let centerScore = model.centerScoreText {
                Text(centerScore)
                    .font(.system(size: 20, weight: .bold, design: .rounded).monospacedDigit())
                    .foregroundStyle(.white)
                    .padding(.horizontal, 8)
                    .padding(.vertical, 3)
                    .background(Capsule().fill(Color.black.opacity(0.55)))
                    .fixedSize(horizontal: false, vertical: true)
            }
            accessibilitySideRow(model.away)
            accessibilitySideRow(model.home)
            if model.isThreeWaySoccer, let drawPct = model.drawPercentText {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Draw")
                        .font(.system(size: 16, weight: .semibold))
                        .foregroundStyle(.white.opacity(0.85))
                    Text(drawPct)
                        .font(.system(size: 20, weight: .bold, design: .rounded).monospacedDigit())
                        .foregroundStyle(.white)
                }
                .fixedSize(horizontal: false, vertical: true)
            }
            if let drawPre = model.drawPregameText, model.stage == .after, !model.away.isWinner && !model.home.isWinner {
                Text(drawPre)
                    .font(.system(size: 16, weight: .semibold).monospacedDigit())
                    .foregroundStyle(.white.opacity(0.88))
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func accessibilitySideRow(_ side: WatchMatchupGameHeroModel297A.Side) -> some View {
        VStack(alignment: .leading, spacing: 3) {
            HStack(spacing: 6) {
                crestDisc(side, size: 24)
                Text(side.shortName)
                    .font(.system(size: 17, weight: .bold))
                    .foregroundStyle(.white)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if model.stage == .after {
                HStack(spacing: 6) {
                    if let score = side.score {
                        Text("\(score)")
                            .font(.system(size: 22, weight: .black, design: .rounded).monospacedDigit())
                            .foregroundStyle(side.isLoser ? .white.opacity(0.75) : .white)
                    }
                    if side.isWinner {
                        Text("\u{2713} Won")
                            .font(.system(size: 15, weight: .bold))
                            .foregroundStyle(Self.rgbColor("#34D399"))
                    } else if side.isLoser {
                        Text("Lost")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.72))
                    } else if model.isTiedFinal {
                        Text("Draw")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(.white.opacity(0.82))
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                if let pre = side.pregameText {
                    Text(pre)
                        .font(.system(size: 15, weight: .semibold).monospacedDigit())
                        .foregroundStyle(.white.opacity(0.88))
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                if let pct = side.currentPercentText {
                    Text(pct)
                        .font(.system(size: 22, weight: .black, design: .rounded).monospacedDigit())
                        .foregroundStyle(Self.rgbColor(side.inkHex))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let score = side.score {
                    Text("Score \(score)")
                        .font(.system(size: 15, weight: .medium).monospacedDigit())
                        .foregroundStyle(.white.opacity(0.84))
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: - Split Probability Bar (Looks 1A / 1B only; hidden on 1C Final)

    private var splitProbabilityBar: some View {
        let homeShare = model.home.currentShare ?? 0.5
        let drawShare = model.drawShare ?? 0
        let awayShare = model.away.currentShare ?? max(0, 1.0 - homeShare - drawShare)
        let total = max(0.001, awayShare + drawShare + homeShare)
        return GeometryReader { geo in
            let w = geo.size.width
            let awayW = w * (awayShare / total)
            let drawW = w * (drawShare / total)
            let homeW = w * (homeShare / total)
            ZStack(alignment: .leading) {
                HStack(spacing: 1) {
                    RoundedRectangle(cornerRadius: 3.5, style: .continuous)
                        .fill(model.away.currentShare == nil
                              ? Color.white.opacity(0.24)
                              : Self.rgbColor(model.away.barHex))
                        .frame(width: max(4, awayW))
                    if drawShare > 0 {
                        Rectangle()
                            .fill(Color.white.opacity(0.75))
                            .frame(width: max(3, drawW))
                    }
                    RoundedRectangle(cornerRadius: 3.5, style: .continuous)
                        .fill(Self.rgbColor(model.home.barHex))
                        .frame(width: max(4, homeW))
                }
                .clipShape(Capsule())

                Circle()
                    .fill(Color.white)
                    .frame(width: 9, height: 9)
                    .overlay(Circle().stroke(Color.black.opacity(0.45), lineWidth: 1))
                    .offset(x: min(max(0, awayW + drawW - 4.5), max(0, w - 9)))
            }
        }
        .frame(height: 9)
        .padding(.top, 2)
        .accessibilityHidden(true)
    }

    // MARK: - Crest Disc

    @ViewBuilder
    private func crestDisc(_ side: WatchMatchupGameHeroModel297A.Side, size: CGFloat) -> some View {
        ZStack {
            #if canImport(UIKit)
            if let png = side.crestPNG, let image = UIImage(data: png) {
                Circle().fill(Color.white)
                Image(uiImage: image)
                    .resizable()
                    .interpolation(.high)
                    .scaledToFit()
                    .padding(size * 0.14)
            } else {
                monogramDisc(side, size: size)
            }
            #else
            monogramDisc(side, size: size)
            #endif
        }
        .frame(width: size, height: size)
        .accessibilityHidden(true)
    }

    private func monogramDisc(_ side: WatchMatchupGameHeroModel297A.Side, size: CGFloat) -> some View {
        let luminance = TeamTextContrast.relativeLuminance(side.fillHex) ?? 0.0
        let inkColor: Color = luminance > 0.35 ? .black : .white
        return ZStack {
            Circle().fill(Self.rgbColor(side.fillHex))
            Circle().strokeBorder(Color.white.opacity(0.75), lineWidth: 1)
            Text(side.abbreviation)
                .font(.system(size: size * 0.34, weight: .heavy, design: .rounded))
                .foregroundStyle(inkColor)
                .lineLimit(1)
                .minimumScaleFactor(0.5)
                .padding(size * 0.1)
        }
    }

    // MARK: - Observation Lines Below Hero (Strictly Separate Score vs Chance)

    @ViewBuilder
    private var observationLines: some View {
        if model.scoreAsOfText != nil || model.probabilityAsOfText != nil {
            VStack(alignment: .leading, spacing: 2) {
                if let scoreLine = model.scoreAsOfText {
                    Text(scoreLine)
                        .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13.5 : 11, weight: .regular))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.selected.event.score-as-of")
                }
                if let probLine = model.probabilityAsOfText {
                    Text(probLine)
                        .font(.system(size: dynamicTypeSize.isAccessibilitySize ? 13.5 : 11, weight: .regular))
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityIdentifier("watch.pins.selected.event.prob-as-of")
                }
            }
            .padding(.horizontal, 2)
        }
    }

    private static func rgbColor(_ hex: String) -> Color {
        guard let c = ProbabilityBarPalette.rgb(hex) else { return .gray }
        return Color(
            red: Double(c.r) / 255.0,
            green: Double(c.g) / 255.0,
            blue: Double(c.b) / 255.0
        )
    }
}
