import SwiftUI

/// #12472 — Pure value model and formatting rules for the two event-page
/// headlines Alex rated "amazing" on Sheet 1, with his Thu Nov 12 / Fri Nov 13
/// rulings applied:
///
/// 1. **NFL before a game (`americanfootball_nfl`)**:
///    - Plain grey context line (`NFL · Sun 1:00 PM · CBS` or `<1h` countdown),
///      no capsule, no `"as of"`, no `"3 venues"`.
///    - Feed pulse (`EkgHeartbeatView`) + source mark (`ⓘ`) on the top-right.
///    - Two team rows with crest, short name + plain record, admitted pregame
///      projected score (`Proj. 20.0` / `Proj. 24.5`), and team-colored win
///      chance: whole `%` by default, tenths **only if** the number streams.
///    - Segmented team-colored probability bar; no betting-line strip, no `"opened"`.
///
/// 2. **NBA during a game (`basketball_nba`)**:
///    - Live capsule (`LIVE · <clock>`) + plain grey `NBA` on the top-left;
///      feed pulse (`EkgHeartbeatView`) + source mark (`ⓘ`) on the top-right
///      in place of `"1m ago"`.
///    - Three right-aligned columns (`Score`, `Pregame`, `Now`, matching `#12684`)
///      above two team rows with crest, short name, live projected score **once**
///      (never twice), live score, bare grey pregame percentage (`"49%"` / `"51%"`,
///      never `"opened"`, never repeating `"pregame"` on every row), and
///      team-colored streaming tenths.
///    - Segmented team-colored probability bar with pregame notch.
enum EventSportHeadlines12472 {

    nonisolated enum Kind: Equatable, Sendable {
        case nflBeforeGame
        case nbaDuringGame
    }

    nonisolated struct PregameColumnHeaders: Equatable, Sendable {
        let projected: String
        let chance: String
    }

    nonisolated struct LiveColumnHeaders: Equatable, Sendable {
        let score: String?
        let pregame: String?
        let now: String

        var hasAny: Bool {
            score != nil || pregame != nil || !now.isEmpty
        }
    }

    nonisolated struct TeamRowModel: Equatable, Sendable {
        let fullName: String
        let opponentFullName: String
        let shortName: String
        let logoURL: String?
        let record: String?
        let projectedText: String?
        let pregameProjectedNumberText: String?
        let liveScore: Int?
        let pregameChanceText: String?
        let winChanceText: String
        let rawProbability: Double
    }

    nonisolated struct Model: Equatable, Sendable {
        let eventId: Int
        let sportKey: String
        let kind: Kind
        /// For `.nflBeforeGame`: plain grey `NFL · Sun 1:00 PM · CBS`.
        let plainMetaText: String?
        let commenceTime: String?
        let startIsTbd: Bool?
        let broadcast: String?
        let eventStatus: String?
        /// For `.nbaDuringGame`: `LIVE · Q4 2:14` or `LIVE`.
        let liveBadgeText: String?
        /// For `.nbaDuringGame`: plain grey `NBA` beside the live capsule.
        let leagueLabel: String?
        /// For `.nflBeforeGame` when an admitted pregame projection exists: `Proj. · Chance`.
        let pregameColumnHeaders: PregameColumnHeaders?
        /// For `.nbaDuringGame`: right-aligned `Score · Pregame · Now` column headers.
        let liveColumnHeaders: LiveColumnHeaders?
        let away: TeamRowModel
        let home: TeamRowModel
        /// 0...1 away pregame probability for the notch on `.nbaDuringGame`.
        let pregameAwayMarker: Double?
        let sourceMark: SourceMark?
        let confidenceTier: String?
    }

    nonisolated static func kind(for event: EventDetail, now: Date = Date()) -> Kind? {
        guard EventState.canStillBeGraded(
                  event.status,
                  commenceTime: event.commenceTime?.asDate,
                  now: now
              ),
              !EventState.showsVenueSettledVerdict(
                  event.status,
                  venueSettled: event.venueSettled,
                  commenceTime: event.commenceTime?.asDate,
                  now: now
              ),
              let odds = event.currentOdds
        else { return nil }

        let shown = OpeningLineHero.resolve(odds, for: event)
        guard !shown.isOpeningLine,
              let pair = DrawPricedWinner.printablePair(
                  away: shown.awayProbability,
                  home: shown.homeProbability,
                  sport: event.sport
              ),
              pair.away != nil
        else { return nil }

        if event.sport == "americanfootball_nfl" && event.status != "live" {
            return .nflBeforeGame
        }
        if event.sport == "basketball_nba" && event.status == "live" {
            return .nbaDuringGame
        }
        return nil
    }

    nonisolated static func applies(to event: EventDetail, now: Date = Date()) -> Bool {
        kind(for: event, now: now) != nil
    }

    /// Resolves the pure view-value model for `.nflBeforeGame` or `.nbaDuringGame`.
    nonisolated static func resolve(
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        liveStatusText: String?,
        hasScore: Bool,
        numberStreams: Bool,
        ladderHome: Double? = nil,
        ladderAway: Double? = nil,
        now: Date = Date()
    ) -> Model? {
        guard let resolvedKind = kind(for: event, now: now),
              let odds = event.currentOdds
        else { return nil }

        let shown = OpeningLineHero.resolve(odds, for: event)
        guard !shown.isOpeningLine,
              let pair = DrawPricedWinner.printablePair(
                  away: shown.awayProbability,
                  home: shown.homeProbability,
                  sport: event.sport
              ),
              let awayProb = pair.away
        else { return nil }
        let homeProb = pair.home

        let shortNames = TeamShortName.shortPair(
            away: awayFullName,
            home: homeFullName,
            sportKey: event.sport
        )

        let confidenceTier = Confidence.fromSources(
            sourceCount: event.winProbabilitySources?.count,
            hasMovement: event.openingOdds?.homeProbability
                .map { abs(homeProb - $0) > 0.001 } ?? false
        )?.rawValue

        switch resolvedKind {
        case .nflBeforeGame:
            let chances = nflPregameChanceTexts(
                shown: shown,
                away: awayProb,
                home: homeProb,
                numberStreams: numberStreams
            )
            let projections = admittedPregameProjectedPair(
                event: event,
                hasScore: hasScore,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                now: now
            )
            let pregameHeaders = projections != nil
                ? PregameColumnHeaders(projected: "Proj.", chance: "Chance")
                : nil
            let meta = nflPregameMetaText(event: event, now: now)
            return Model(
                eventId: event.id,
                sportKey: "americanfootball_nfl",
                kind: .nflBeforeGame,
                plainMetaText: meta,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: nil,
                pregameColumnHeaders: pregameHeaders,
                liveColumnHeaders: nil,
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: trimmedNonEmpty(event.awayTeamData?.record),
                    projectedText: projections?.away,
                    pregameProjectedNumberText: projections?.awayNumber,
                    liveScore: nil,
                    pregameChanceText: nil,
                    winChanceText: chances.away,
                    rawProbability: awayProb
                ),
                home: TeamRowModel(
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    record: trimmedNonEmpty(event.homeTeamData?.record),
                    projectedText: projections?.home,
                    pregameProjectedNumberText: projections?.homeNumber,
                    liveScore: nil,
                    pregameChanceText: nil,
                    winChanceText: chances.home,
                    rawProbability: homeProb
                ),
                pregameAwayMarker: nil,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )

        case .nbaDuringGame:
            let tenths = EventHeadlineTenths10090.pair(home: homeProb, away: awayProb)
            let pregame = PrematchReading.resolve(
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )
            let pregameTexts = nbaPregameTexts(pregame)
            let liveProjections = admittedLiveProjectedPair(
                event: event,
                hasScore: hasScore,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                now: now
            )
            let periodStatus = trimmedNonEmpty(liveStatusText)
            let liveBadge = periodStatus.map { "LIVE · \($0)" } ?? "LIVE"
            let hasLiveScore = hasScore && (event.awayScore != nil || event.homeScore != nil)
            let columnHeaders = LiveColumnHeaders(
                score: hasLiveScore ? "Score" : nil,
                pregame: pregameTexts != nil ? "Pregame" : nil,
                now: "Now"
            )
            return Model(
                eventId: event.id,
                sportKey: "basketball_nba",
                kind: .nbaDuringGame,
                plainMetaText: nil,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: liveBadge,
                leagueLabel: "NBA",
                pregameColumnHeaders: nil,
                liveColumnHeaders: columnHeaders,
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: nil,
                    projectedText: liveProjections?.away,
                    pregameProjectedNumberText: nil,
                    liveScore: hasScore ? event.awayScore : nil,
                    pregameChanceText: pregameTexts?.away,
                    winChanceText: tenths.away ?? formatProbability(awayProb),
                    rawProbability: awayProb
                ),
                home: TeamRowModel(
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    record: nil,
                    projectedText: liveProjections?.home,
                    pregameProjectedNumberText: nil,
                    liveScore: hasScore ? event.homeScore : nil,
                    pregameChanceText: pregameTexts?.home,
                    winChanceText: tenths.home,
                    rawProbability: homeProb
                ),
                pregameAwayMarker: pregame?.awayProbability,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )
        }
    }

    // MARK: - Pure Formatting Rules

    /// NFL before a game: whole `%` by default; tenths ONLY when `numberStreams` is true.
    nonisolated static func nflPregameChanceTexts(
        shown: OpeningLineHero,
        away: Double,
        home: Double,
        numberStreams: Bool
    ) -> (away: String, home: String) {
        if numberStreams {
            let tenths = EventHeadlineTenths10090.pair(home: home, away: away)
            return (away: tenths.away ?? formatProbability(away), home: tenths.home)
        }
        let duelFallback = complementDisplayPercents(away: away, home: home)
        let bothServed = shown.awayRenderedPercent != nil && shown.homeRenderedPercent != nil
        let awayPct = bothServed ? shown.awayRenderedPercent : duelFallback[0]
        let homePct = bothServed ? shown.homeRenderedPercent : duelFallback[1]
        return (
            away: formatProbability(away, renderedPercent: awayPct),
            home: formatProbability(home, renderedPercent: homePct)
        )
    }

    /// Plain-text pregame meta line (`182-A`): date/time when days or hours away,
    /// countdown inside the last hour, and broadcast where still ahead. Never a capsule,
    /// never `"as of"`, never `"3 venues"`.
    nonisolated static func nflPregameMetaText(event: EventDetail, now: Date = Date()) -> String {
        var parts: [String] = ["NFL"]
        if let timeText = pregameStartText(
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            now: now
        ) {
            parts.append(timeText)
        }
        if let broadcast = trimmedNonEmpty(event.espn?.broadcast),
           !EventState.isFinished(event.status),
           !EventState.isSuspendedAndStarted(
               event.status,
               commenceTime: event.commenceTime?.asDate,
               now: now
           ) {
            parts.append(broadcast)
        }
        return parts.joined(separator: " · ")
    }

    nonisolated static func pregameStartText(
        commenceTime: String?,
        startIsTbd: Bool?,
        now: Date = Date()
    ) -> String? {
        if startIsTbd == true {
            return RelativeTimeText.tbdText(for: commenceTime, relativeDays: false)
        }
        guard let date = commenceTime?.asDate else { return nil }
        let delta = date.timeIntervalSince(now)
        if delta > 0 && delta <= 3600 {
            let mins = max(1, Int(ceil(delta / 60)))
            return "In \(mins)m"
        }
        if Calendar.current.isDate(date, inSameDayAs: now) && delta > 0 {
            return "Today \(date.formatted(.dateTime.hour().minute()))"
        }
        if delta > 0 && delta < 6 * 86_400 {
            let weekday = date.formatted(.dateTime.weekday(.abbreviated))
            let clock = date.formatted(.dateTime.hour().minute())
            return "\(weekday) \(clock)"
        }
        return date.formatted(.dateTime.month(.abbreviated).day().hour().minute())
    }

    /// Bare pregame baseline percentages under the `"Pregame"` column header on
    /// live NBA (`"49%"` / `"51%"`), never `"opened"` and never repeating `"pregame"` twice.
    nonisolated static func nbaPregameTexts(
        _ pregame: PrematchReading?
    ) -> (away: String, home: String)? {
        guard let pregame else { return nil }
        let awayPct = pregame.percents.count > 0 ? pregame.percents[0] : nil
        let homePct = pregame.percents.count > 1 ? pregame.percents[1] : nil
        let awayText = formatProbability(pregame.awayProbability, renderedPercent: awayPct)
        let homeText = formatProbability(pregame.homeProbability, renderedPercent: homePct)
        return (away: awayText, home: homeText)
    }

    /// Admitted pregame projected points per team (`Proj. 20.0` / `Proj. 24.5` and bare
    /// column numbers `20.0` / `24.5`), honoring `#8617`, `#8156` (no level projection on
    /// tie-less sports), and `#5697`.
    nonisolated static func admittedPregameProjectedPair(
        event: EventDetail,
        hasScore: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        now: Date = Date()
    ) -> (away: String, home: String, awayNumber: String, homeNumber: String)? {
        let vocab = SportVocab.forSport(event.sport)
        guard EventState.canStillBeGraded(event.status, commenceTime: event.commenceTime?.asDate, now: now) else {
            return nil
        }
        let underway = event.status == "live"
            || EventState.hasStarted(commenceTime: event.commenceTime?.asDate, now: now)
        guard !underway || hasScore else { return nil }

        let pair: (away: Double, home: Double)
        if vocab.sportsbookSpreadIsAMargin,
           let away = event.currentOdds?.projectedAwayScore,
           let home = event.currentOdds?.projectedHomeScore,
           away.isFinite, home.isFinite, away > 0, home > 0 {
            pair = (away: away, home: home)
        } else if !underway,
                  vocab.scoreboardCountsTheUnit, !vocab.unit.isEmpty,
                  let away = ladderAway, let home = ladderHome,
                  away.isFinite, home.isFinite, away > 0, home > 0 {
            pair = (away: away, home: home)
        } else {
            return nil
        }

        let roundedAway = Int(pair.away.rounded())
        let roundedHome = Int(pair.home.rounded())
        guard vocab.canEndInATie || roundedAway != roundedHome else { return nil }
        return (
            away: formatProjectedScore(pair.away),
            home: formatProjectedScore(pair.home),
            awayNumber: formatProjectedNumber(pair.away),
            homeNumber: formatProjectedNumber(pair.home)
        )
    }

    /// Admitted live projected points per team (`Proj. 103.5` / `Proj. 105.0`),
    /// shown **once** on the team rows and gated by `LiveProjectedFinal2920.page`
    /// plus `#5697` (`hasScore`) and `#2920 W1` score reachability.
    nonisolated static func admittedLiveProjectedPair(
        event: EventDetail,
        hasScore: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        now: Date = Date()
    ) -> (away: String, home: String)? {
        guard hasScore,
              let awayScore = event.awayScore,
              let homeScore = event.homeScore
        else { return nil }

        let vocab = SportVocab.forSport(event.sport)
        let rawPair: (away: Double, home: Double)
        switch LiveProjectedFinal2920.page(event, now: now) {
        case .admitted(let printed):
            rawPair = (away: printed.admitted.away, home: printed.admitted.home)
        case .withheld, .notLive:
            return nil
        case .absent:
            guard vocab.scoreboardCountsTheUnit, !vocab.unit.isEmpty,
                  let away = ladderAway, let home = ladderHome,
                  away.isFinite, home.isFinite, away > 0, home > 0
            else { return nil }
            let rAway = Int(away.rounded())
            let rHome = Int(home.rounded())
            guard vocab.canEndInATie || rAway != rHome,
                  rAway >= awayScore, rHome >= homeScore
            else { return nil }
            rawPair = (away: away, home: home)
        }

        let safeAway = max(rawPair.away, Double(awayScore))
        let safeHome = max(rawPair.home, Double(homeScore))
        return (
            away: formatProjectedScore(safeAway),
            home: formatProjectedScore(safeHome)
        )
    }

    nonisolated static func formatProjectedScore(_ value: Double) -> String {
        String(format: "Proj. %.1f", value)
    }

    nonisolated static func formatProjectedNumber(_ value: Double) -> String {
        String(format: "%.1f", value)
    }

    nonisolated private static func trimmedNonEmpty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return nil
        }
        return text
    }
}
