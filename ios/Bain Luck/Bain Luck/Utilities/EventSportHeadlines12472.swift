import SwiftUI

/// #12472 — Pure value model and formatting rules for the event-page headlines
/// Alex rated "amazing" on Sheets 1–3, with his Thu Nov 12 / Fri Nov 13 rulings
/// and Fable's single-`Pregame`-header rule (`#12668` / `#12684`) applied:
///
/// 1. **NFL before a game (`americanfootball_nfl`)**:
///    - Plain grey context line (`NFL · Sun 1:00 PM · CBS` or `<1h` countdown),
///      no capsule, no `"as of"`, no `"3 venues"`.
///    - Feed pulse (`EkgHeartbeatView`) + source mark (`ⓘ`) on the top-right.
///    - Two team rows with crest, short name + plain record, admitted pregame
///      projected score (`Proj. · Chance` columns), and team-colored win chance:
///      whole `%` by default, tenths **only if** the number streams.
///    - Segmented team-colored probability bar; no betting-line strip, no `"opened"`.
///
/// 2. **NBA during a game (`basketball_nba`)**:
///    - Live capsule (`LIVE · <clock>`) + plain grey `NBA` on the top-left;
///      feed pulse (`EkgHeartbeatView`) + source mark (`ⓘ`) on the top-right
///      in place of `"1m ago"`.
///    - Three right-aligned columns (`Score`, `Pregame`, `Now`, matching `#12684`)
///      above two team rows with crest, short name, live projected score **once**,
///      live score, bare grey pregame percentage (`"49%"` / `"51%"`), and
///      team-colored streaming tenths.
///    - Segmented team-colored probability bar with pregame notch.
///
/// 3. **Soccer before a match (`soccer_*`)**:
///    - Plain grey context line (`Premier League · Sun 8:30 AM` or `<1h` countdown)
///      + feed pulse (`EkgHeartbeatView`) + source mark (`ⓘ`).
///    - World-soccer matchup row (`Home` crest + club on left, `90' Reg.` center,
///      `Away` club + crest on right).
///    - Three outcome boxes (`[Home Win] [Draw] [Away Win]`) from explicit 3-way
///      probabilities (never derived from `1 - home`), whole `%` unless streaming.
///    - Three-way segmented `[Home | Draw | Away]` bar.
///
/// 4. **Soccer after a match (`soccer_*`)**:
///    - Plain grey context line (`Liga MX · Final · Nov 10`), never `"Settled"`.
///    - World-soccer matchup row with dark full-time score pill (`2 – 1`).
///    - Three graded boxes (`✓ Won` / `—` / `Lost`, or `—` / `✓ Draw` / `—` on a
///      level finish per `#4915`).
///    - When explicit 3-way pregame odds exist, **one** `"Pregame"` header above
///      three bare percentage cells (`"64%"` · `"21%"` · `"15%"`), never repeating
///      `"Pregame"` in each box and never saying `"Opened"`.
///
/// 5. **NHL during a game (`icehockey_nhl`)**:
///    - Live capsule (`LIVE · <clock>`) + plain grey `NHL` on the top-left;
///      feed pulse (`EkgHeartbeatView`) + source mark (`ⓘ`) on the top-right.
///    - Right-aligned `Score · Pregame · Now` column headers above two team rows
///      with crest, short name + stacked record (`18-14-3`), live goals, bare
///      pregame `%`, and club-colored streaming tenths + bar with pregame notch.
enum EventSportHeadlines12472 {

    nonisolated enum Kind: Equatable, Sendable {
        case nflBeforeGame
        case nbaDuringGame
        case soccerBeforeGame
        case soccerAfterGame
        case nhlDuringGame
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

    nonisolated enum SoccerBoxTone: Equatable, Sendable {
        case homeClub
        case drawNeutral
        case awayClub
        case wonOutcome
        case lostOutcome
        case mutedDash
    }

    nonisolated struct SoccerThreeWayBox: Equatable, Sendable {
        let role: EventAtlasSoccerCards11666.ThreeWayRole
        let headerLabel: String
        let dotTone: SoccerBoxTone
        let boxTone: SoccerBoxTone
        let mainText: String
        let pregameChanceText: String?
        let rawShare: Double?
    }

    nonisolated struct SoccerThreeWayModel: Equatable, Sendable {
        let centerTagText: String
        let isScorePill: Bool
        let homeBox: SoccerThreeWayBox
        let drawBox: SoccerThreeWayBox
        let awayBox: SoccerThreeWayBox
        /// Single `"Pregame"` header above bare 3-way baseline percentages (never repeated).
        let pregameHeader: String?
        let showsBottomBar: Bool
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
        let plainMetaText: String?
        let commenceTime: String?
        let startIsTbd: Bool?
        let broadcast: String?
        let eventStatus: String?
        let liveBadgeText: String?
        let leagueLabel: String?
        let pregameColumnHeaders: PregameColumnHeaders?
        let liveColumnHeaders: LiveColumnHeaders?
        let away: TeamRowModel
        let home: TeamRowModel
        let pregameAwayMarker: Double?
        let soccerThreeWay: SoccerThreeWayModel?
        let showsEkg: Bool
        let stacksRecordUnderName: Bool
        let sourceMark: SourceMark?
        let confidenceTier: String?
    }

    nonisolated static func kind(
        for event: EventDetail,
        gameMarkets: GameMarketsResponse? = nil,
        now: Date = Date()
    ) -> Kind? {
        if let sport = event.sport, sport.hasPrefix("soccer_") {
            if EventState.isFinished(event.status) {
                guard !EventState.showsVenueSettledVerdict(
                          event.status,
                          venueSettled: event.venueSettled,
                          commenceTime: event.commenceTime?.asDate,
                          now: now
                      ),
                      !EventState.showsVenueClosedNoWinner(
                          event.status,
                          venueSettled: event.venueSettled,
                          venueClosedNoWinner: event.venueClosedNoWinner,
                          commenceTime: event.commenceTime?.asDate,
                          now: now
                      )
                else { return nil }

                let marketSnap = extractSoccerThreeWayMarketSnapshot(
                    event: event,
                    gameMarkets: gameMarkets,
                    finished: true,
                    now: now
                )
                let periodIsNonRegulation = event.finalScorePeriod == "extra_time"
                    || event.finalScorePeriod == "penalties"
                if periodIsNonRegulation && marketSnap?.confirmedWinner == nil {
                    return nil
                }

                guard event.homeScore != nil, event.awayScore != nil else { return nil }
                let hasThreeWayOrSettlementWitness =
                    extractSoccerThreeWayPrematchShares(event: event, marketSnapshot: marketSnap) != nil
                    || marketSnap?.confirmedWinner != nil
                    || event.finalScorePeriod == "regulation"
                    || event.heroSettledResult != nil
                guard hasThreeWayOrSettlementWitness else {
                    return nil
                }
                let outcome = EventOutcome.resolve(
                    status: event.status,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedResult: event.heroSettledResult
                )
                guard outcome != .undecided || marketSnap?.confirmedWinner != nil else {
                    return nil
                }
                return .soccerAfterGame
            }

            if event.status != "live" {
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
                      )
                else { return nil }

                if let odds = event.currentOdds,
                   OpeningLineHero.resolve(odds, for: event).isOpeningLine {
                    return nil
                }

                guard extractSoccerThreeWayOpenShares(
                    event: event,
                    gameMarkets: gameMarkets,
                    now: now
                ) != nil else {
                    return nil
                }
                return .soccerBeforeGame
            }

            return nil
        }

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
        if event.sport == "icehockey_nhl" && event.status == "live" {
            return .nhlDuringGame
        }
        return nil
    }

    nonisolated static func applies(
        to event: EventDetail,
        gameMarkets: GameMarketsResponse? = nil,
        now: Date = Date()
    ) -> Bool {
        kind(for: event, gameMarkets: gameMarkets, now: now) != nil
    }

    /// Resolves the pure view-value model for the active `#12472` headline kind.
    nonisolated static func resolve(
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        liveStatusText: String?,
        hasScore: Bool,
        numberStreams: Bool,
        ladderHome: Double? = nil,
        ladderAway: Double? = nil,
        gameMarkets: GameMarketsResponse? = nil,
        now: Date = Date()
    ) -> Model? {
        guard let resolvedKind = kind(for: event, gameMarkets: gameMarkets, now: now) else {
            return nil
        }

        let shortNames = TeamShortName.shortPair(
            away: awayFullName,
            home: homeFullName,
            sportKey: event.sport
        )

        switch resolvedKind {
        case .soccerBeforeGame:
            guard let shares = extractSoccerThreeWayOpenShares(
                event: event,
                gameMarkets: gameMarkets,
                now: now
            ) else { return nil }

            let codes = soccerClubCodes(
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName
            )
            let formatted = soccerThreeWayChanceTexts(
                home: shares.home,
                draw: shares.draw,
                away: shares.away,
                numberStreams: numberStreams
            )
            let league = soccerCompetitionName(for: event)
            let meta = pregameMetaText(league: league, event: event, now: now)
            let confidenceTier = Confidence.fromSources(
                sourceCount: event.winProbabilitySources?.count,
                hasMovement: event.openingOdds?.homeProbability
                    .map { abs(shares.home - $0) > 0.001 } ?? false
            )?.rawValue

            let threeWay = SoccerThreeWayModel(
                centerTagText: "90' Reg.",
                isScorePill: false,
                homeBox: SoccerThreeWayBox(
                    role: .home,
                    headerLabel: "\(codes.home) WIN",
                    dotTone: .homeClub,
                    boxTone: .homeClub,
                    mainText: formatted.home,
                    pregameChanceText: nil,
                    rawShare: shares.home
                ),
                drawBox: SoccerThreeWayBox(
                    role: .draw,
                    headerLabel: "DRAW",
                    dotTone: .drawNeutral,
                    boxTone: .drawNeutral,
                    mainText: formatted.draw,
                    pregameChanceText: nil,
                    rawShare: shares.draw
                ),
                awayBox: SoccerThreeWayBox(
                    role: .away,
                    headerLabel: "\(codes.away) WIN",
                    dotTone: .awayClub,
                    boxTone: .awayClub,
                    mainText: formatted.away,
                    pregameChanceText: nil,
                    rawShare: shares.away
                ),
                pregameHeader: nil,
                showsBottomBar: true
            )

            return Model(
                eventId: event.id,
                sportKey: event.sport ?? "soccer",
                kind: .soccerBeforeGame,
                plainMetaText: meta,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: league,
                pregameColumnHeaders: nil,
                liveColumnHeaders: nil,
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: trimmedNonEmpty(event.awayTeamData?.record),
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: nil,
                    pregameChanceText: nil,
                    winChanceText: formatted.away,
                    rawProbability: shares.away
                ),
                home: TeamRowModel(
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    record: trimmedNonEmpty(event.homeTeamData?.record),
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: nil,
                    pregameChanceText: nil,
                    winChanceText: formatted.home,
                    rawProbability: shares.home
                ),
                pregameAwayMarker: nil,
                soccerThreeWay: threeWay,
                showsEkg: true,
                stacksRecordUnderName: false,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )

        case .soccerAfterGame:
            guard let homeScore = event.homeScore,
                  let awayScore = event.awayScore
            else { return nil }

            let marketSnap = extractSoccerThreeWayMarketSnapshot(
                event: event,
                gameMarkets: gameMarkets,
                finished: true,
                now: now
            )
            let resolvedWinnerRole: EventAtlasSoccerCards11666.ThreeWayRole
            if let confirmed = marketSnap?.confirmedWinner {
                resolvedWinnerRole = confirmed
            } else {
                let outcome = EventOutcome.resolve(
                    status: event.status,
                    homeScore: homeScore,
                    awayScore: awayScore,
                    servedResult: event.heroSettledResult
                )
                switch outcome {
                case .home: resolvedWinnerRole = .home
                case .away: resolvedWinnerRole = .away
                case .draw: resolvedWinnerRole = .draw
                case .undecided: return nil
                }
            }

            let codes = soccerClubCodes(
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName
            )
            let pregameShares = extractSoccerThreeWayPrematchShares(
                event: event,
                marketSnapshot: marketSnap
            )
            let pregameTexts = pregameShares.map {
                soccerThreeWayChanceTexts(
                    home: $0.home,
                    draw: $0.draw,
                    away: $0.away,
                    numberStreams: false
                )
            }

            let homeVerdict: (text: String, tone: SoccerBoxTone) = {
                switch resolvedWinnerRole {
                case .home: return ("\u{2713} Won", .wonOutcome)
                case .away: return ("Lost", .lostOutcome)
                case .draw: return ("\u{2014}", .mutedDash)
                }
            }()
            let drawVerdict: (text: String, tone: SoccerBoxTone) = {
                switch resolvedWinnerRole {
                case .draw: return ("\u{2713} Draw", .wonOutcome)
                case .home, .away: return ("\u{2014}", .mutedDash)
                }
            }()
            let awayVerdict: (text: String, tone: SoccerBoxTone) = {
                switch resolvedWinnerRole {
                case .away: return ("\u{2713} Won", .wonOutcome)
                case .home: return ("Lost", .lostOutcome)
                case .draw: return ("\u{2014}", .mutedDash)
                }
            }()

            let league = soccerCompetitionName(for: event)
            let meta = soccerAfterMetaText(league: league, event: event)
            let confidenceTier = Confidence.fromSources(
                sourceCount: event.winProbabilitySources?.count,
                hasMovement: false
            )?.rawValue

            let threeWay = SoccerThreeWayModel(
                centerTagText: "\(homeScore) \u{2013} \(awayScore)",
                isScorePill: true,
                homeBox: SoccerThreeWayBox(
                    role: .home,
                    headerLabel: "\(codes.home) WIN",
                    dotTone: .homeClub,
                    boxTone: homeVerdict.tone,
                    mainText: homeVerdict.text,
                    pregameChanceText: pregameTexts?.home,
                    rawShare: pregameShares?.home
                ),
                drawBox: SoccerThreeWayBox(
                    role: .draw,
                    headerLabel: "DRAW",
                    dotTone: .drawNeutral,
                    boxTone: drawVerdict.tone,
                    mainText: drawVerdict.text,
                    pregameChanceText: pregameTexts?.draw,
                    rawShare: pregameShares?.draw
                ),
                awayBox: SoccerThreeWayBox(
                    role: .away,
                    headerLabel: "\(codes.away) WIN",
                    dotTone: .awayClub,
                    boxTone: awayVerdict.tone,
                    mainText: awayVerdict.text,
                    pregameChanceText: pregameTexts?.away,
                    rawShare: pregameShares?.away
                ),
                pregameHeader: pregameTexts != nil ? "Pregame" : nil,
                showsBottomBar: false
            )

            let markProb = pregameShares?.home
                ?? (resolvedWinnerRole == .home ? 1.0 : resolvedWinnerRole == .away ? 0.0 : 0.5)

            return Model(
                eventId: event.id,
                sportKey: event.sport ?? "soccer",
                kind: .soccerAfterGame,
                plainMetaText: meta,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: nil,
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: league,
                pregameColumnHeaders: nil,
                liveColumnHeaders: nil,
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: trimmedNonEmpty(event.awayTeamData?.record),
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: awayScore,
                    pregameChanceText: pregameTexts?.away,
                    winChanceText: awayVerdict.text,
                    rawProbability: pregameShares?.away ?? 0.5
                ),
                home: TeamRowModel(
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    record: trimmedNonEmpty(event.homeTeamData?.record),
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: homeScore,
                    pregameChanceText: pregameTexts?.home,
                    winChanceText: homeVerdict.text,
                    rawProbability: markProb
                ),
                pregameAwayMarker: nil,
                soccerThreeWay: threeWay,
                showsEkg: false,
                stacksRecordUnderName: false,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )

        case .nflBeforeGame, .nbaDuringGame, .nhlDuringGame:
            guard let odds = event.currentOdds else { return nil }
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
                    leagueLabel: "NFL",
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
                    soccerThreeWay: nil,
                    showsEkg: true,
                    stacksRecordUnderName: pregameHeaders != nil,
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
                    soccerThreeWay: nil,
                    showsEkg: true,
                    stacksRecordUnderName: false,
                    sourceMark: event.sourceMark,
                    confidenceTier: confidenceTier
                )

            case .nhlDuringGame:
                let tenths = EventHeadlineTenths10090.pair(home: homeProb, away: awayProb)
                let pregame = PrematchReading.resolve(
                    prematch: event.prematchOdds,
                    opening: event.openingOdds
                )
                let pregameTexts = nbaPregameTexts(pregame)
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
                    sportKey: "icehockey_nhl",
                    kind: .nhlDuringGame,
                    plainMetaText: nil,
                    commenceTime: event.commenceTime,
                    startIsTbd: event.startIsTbd,
                    broadcast: trimmedNonEmpty(event.espn?.broadcast),
                    eventStatus: event.status,
                    liveBadgeText: liveBadge,
                    leagueLabel: "NHL",
                    pregameColumnHeaders: nil,
                    liveColumnHeaders: columnHeaders,
                    away: TeamRowModel(
                        fullName: awayFullName,
                        opponentFullName: homeFullName,
                        shortName: shortNames.away,
                        logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                        record: trimmedNonEmpty(event.awayTeamData?.record),
                        projectedText: nil,
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
                        record: trimmedNonEmpty(event.homeTeamData?.record),
                        projectedText: nil,
                        pregameProjectedNumberText: nil,
                        liveScore: hasScore ? event.homeScore : nil,
                        pregameChanceText: pregameTexts?.home,
                        winChanceText: tenths.home,
                        rawProbability: homeProb
                    ),
                    pregameAwayMarker: pregame?.awayProbability,
                    soccerThreeWay: nil,
                    showsEkg: true,
                    stacksRecordUnderName: true,
                    sourceMark: event.sourceMark,
                    confidenceTier: confidenceTier
                )

            case .soccerBeforeGame, .soccerAfterGame:
                return nil
            }
        }
    }

    // MARK: - Three-Way Soccer Helpers

    private struct SoccerThreeWayMarketSnapshot {
        let openShares: (home: Double, draw: Double, away: Double)?
        let pregameShares: (home: Double, draw: Double, away: Double)?
        let confirmedWinner: EventAtlasSoccerCards11666.ThreeWayRole?
    }

    nonisolated private static let disqualifiedSoccerThreeWayRegex: NSRegularExpression? = try? NSRegularExpression(
        pattern: #"\b(?:1st\s+half|2nd\s+half|first\s+half|second\s+half|half[-\s]?time|corner|corners|card|cards|shot|shots|goalscorer|first\s+team\s+to\s+score|last\s+team\s+to\s+score|both\s+teams\s+to\s+score|btts|exact\s+score|correct\s+score|advance|qualify|tiebreaker|over\/under|o\/u|spread|handicap)\b"#,
        options: [.caseInsensitive]
    )

    nonisolated private static func isDisqualifiedSoccerThreeWayMarket(_ name: String) -> Bool {
        let range = NSRange(name.startIndex..<name.endIndex, in: name)
        return disqualifiedSoccerThreeWayRegex?.firstMatch(in: name, options: [], range: range) != nil
    }

    nonisolated static func extractSoccerThreeWayOpenShares(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        now: Date = Date()
    ) -> (home: Double, draw: Double, away: Double)? {
        if let odds = event.currentOdds {
            let scaled = EventAtlasSoccerCards11666.scaleThreeWayField(
                home: odds.homeProbability,
                draw: odds.drawProbability,
                away: odds.awayProbability
            )
            if let h = scaled.home, let d = scaled.draw, let a = scaled.away {
                return (home: h, draw: d, away: a)
            }
        }

        return extractSoccerThreeWayMarketSnapshot(
            event: event,
            gameMarkets: gameMarkets,
            finished: false,
            now: now
        )?.openShares
    }

    nonisolated private static func extractSoccerThreeWayPrematchShares(
        event: EventDetail,
        marketSnapshot: SoccerThreeWayMarketSnapshot?
    ) -> (home: Double, draw: Double, away: Double)? {
        if let pre = event.prematchOdds {
            let scaled = EventAtlasSoccerCards11666.scaleThreeWayField(
                home: pre.homeProbability,
                draw: pre.drawProbability,
                away: pre.awayProbability
            )
            if let h = scaled.home, let d = scaled.draw, let a = scaled.away {
                return (home: h, draw: d, away: a)
            }
        }
        return marketSnapshot?.pregameShares
    }

    nonisolated private static func extractSoccerThreeWayMarketSnapshot(
        event: EventDetail,
        gameMarkets: GameMarketsResponse?,
        finished: Bool,
        now: Date
    ) -> SoccerThreeWayMarketSnapshot? {
        guard let gm = gameMarkets, gm.eventId == event.id else { return nil }

        let shortNames = TeamShortName.shortPair(
            away: event.awayTeam,
            home: event.homeTeam,
            sportKey: event.sport
        )

        struct RawLeg {
            let quoted: Double?
            let pregame: Double?
            let won: Bool
            let source: String?
        }

        struct Candidate {
            let source: String?
            let legs: [EventAtlasSoccerCards11666.ThreeWayRole: RawLeg]
            let score: Int
        }

        var candidates: [Candidate] = []

        if gm.gameQuestionMatrix?.contract == "10238.v1",
           let questions = gm.gameQuestionMatrix?.questions {
            for q in questions {
                let title = (q.marketName ?? q.label).trimmingCharacters(in: .whitespacesAndNewlines)
                guard !title.isEmpty, !isDisqualifiedSoccerThreeWayMarket(title) else { continue }
                if let periodKey = q.period?.key, periodKey != "full_game" { continue }
                guard q.options.count == 3 else { continue }

                var legs: [EventAtlasSoccerCards11666.ThreeWayRole: RawLeg] = [:]
                for o in q.options {
                    guard let role = EventAtlasSoccerCards11666.classifyThreeWayRole(
                        outcomeLabel: o.label,
                        homeTeam: event.homeTeam,
                        awayTeam: event.awayTeam,
                        homeShort: shortNames.home,
                        awayShort: shortNames.away
                    ), legs[role] == nil else { break }

                    let quoted: Double? = !finished && isRecentObservation(o.published.observedAt, now: now)
                        ? usableOpenChance(o.published.quotedValue)
                        : nil
                    let pregame: Double? = {
                        guard let r = o.pregameReading, r.state == "available",
                              let p = usableOpenChance(r.probability) else { return nil }
                        if finished {
                            guard r.basis == "pregame_pin",
                                  let outId = r.outcomeId, o.contributorOutcomeIds == [outId],
                                  let at = r.observedAt, !at.isEmpty else { return nil }
                        }
                        return p
                    }()
                    let won = finished && o.result?.isWinner == true
                    legs[role] = RawLeg(
                        quoted: quoted,
                        pregame: pregame,
                        won: won,
                        source: o.published.source
                    )
                }

                if legs.count == 3 {
                    let all = Array(legs.values)
                    let priced = all.filter { $0.quoted != nil || $0.pregame != nil }.count
                    let settled = all.filter(\.won).count
                    candidates.append(
                        Candidate(
                            source: all.compactMap(\.source).first,
                            legs: legs,
                            score: priced * 10 + settled * 5
                        )
                    )
                }
            }
        }

        var byMarketKey: [String: (title: String, rows: [GameMarketOther])] = [:]
        var marketKeyOrder: [String] = []
        for row in gm.other ?? [] {
            let mname = row.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !mname.isEmpty, !isDisqualifiedSoccerThreeWayMarket(mname) else { continue }
            let prefix = [row._marketId.map(String.init), row.source].compactMap { $0 }.first
            let key = "\(prefix ?? ""):\(mname)"
            if byMarketKey[key] == nil {
                marketKeyOrder.append(key)
                byMarketKey[key] = (mname, [row])
            } else {
                byMarketKey[key]?.rows.append(row)
            }
        }

        for key in marketKeyOrder {
            guard let group = byMarketKey[key], group.rows.count == 3 else { continue }
            var legs: [EventAtlasSoccerCards11666.ThreeWayRole: RawLeg] = [:]
            for row in group.rows {
                let outLabel = row.outcomeName.trimmingCharacters(in: .whitespacesAndNewlines)
                guard let role = EventAtlasSoccerCards11666.classifyThreeWayRole(
                    outcomeLabel: outLabel,
                    homeTeam: event.homeTeam,
                    awayTeam: event.awayTeam,
                    homeShort: shortNames.home,
                    awayShort: shortNames.away
                ), legs[role] == nil else { break }

                let recent = isRecentObservation(row.observedAt, now: now)
                let quoted = !finished && recent ? usableOpenChance(row.probability) : nil
                let pregame = finished
                    ? usableOpenChance(row.pregameMark)
                    : (event.status != "live"
                        ? (recent ? usableOpenChance(row.probability) : nil)
                        : usableOpenChance(row.pregameMark))
                let won = EventAtlasSoccerCards11666.otherRowVerdict(row, finished: finished) == .won
                legs[role] = RawLeg(
                    quoted: quoted,
                    pregame: pregame,
                    won: won,
                    source: row.source
                )
            }

            if legs.count == 3 {
                let all = Array(legs.values)
                let priced = all.filter { $0.quoted != nil || $0.pregame != nil }.count
                let settled = all.filter(\.won).count
                candidates.append(
                    Candidate(
                        source: all.compactMap(\.source).first,
                        legs: legs,
                        score: priced * 10 + settled * 5
                    )
                )
            }
        }

        guard !candidates.isEmpty else { return nil }
        candidates.sort { $0.score > $1.score }

        var seenSources = Set<String>()
        var deduped: [Candidate] = []
        for c in candidates {
            if let s = c.source {
                if seenSources.contains(s) { continue }
                seenSources.insert(s)
            }
            deduped.append(c)
        }

        let blended = deduped.first { $0.source == "blended" || $0.source == "blend" }
        let multiUnblended = blended == nil && deduped.count > 1
        guard let best = blended ?? deduped.first,
              let homeLeg = best.legs[.home],
              let drawLeg = best.legs[.draw],
              let awayLeg = best.legs[.away]
        else { return nil }

        let openShares: (home: Double, draw: Double, away: Double)? = {
            guard !multiUnblended else { return nil }
            let s = EventAtlasSoccerCards11666.scaleThreeWayField(
                home: homeLeg.quoted,
                draw: drawLeg.quoted,
                away: awayLeg.quoted
            )
            guard let h = s.home, let d = s.draw, let a = s.away else { return nil }
            return (h, d, a)
        }()

        let pregameShares: (home: Double, draw: Double, away: Double)? = {
            guard !multiUnblended else { return nil }
            let s = EventAtlasSoccerCards11666.scaleThreeWayField(
                home: homeLeg.pregame,
                draw: drawLeg.pregame,
                away: awayLeg.pregame
            )
            guard let h = s.home, let d = s.draw, let a = s.away else { return nil }
            return (h, d, a)
        }()

        let winners = [
            homeLeg.won ? EventAtlasSoccerCards11666.ThreeWayRole.home : nil,
            drawLeg.won ? EventAtlasSoccerCards11666.ThreeWayRole.draw : nil,
            awayLeg.won ? EventAtlasSoccerCards11666.ThreeWayRole.away : nil,
        ].compactMap { $0 }
        let confirmedWinner = winners.count == 1 ? winners.first : nil

        return SoccerThreeWayMarketSnapshot(
            openShares: openShares,
            pregameShares: pregameShares,
            confirmedWinner: confirmedWinner
        )
    }

    nonisolated private static func usableOpenChance(_ value: Double?) -> Double? {
        guard let value, value.isFinite, value > 0, value < 1 else { return nil }
        return value
    }

    nonisolated private static func isRecentObservation(_ iso: String?, now: Date) -> Bool {
        guard let date = iso?.asDate else { return true }
        return now.timeIntervalSince(date) <= 6 * 3600
    }

    nonisolated static func soccerClubCodes(
        event: EventDetail,
        awayFullName: String,
        homeFullName: String
    ) -> (away: String, home: String) {
        let pairBadges = TeamShortName.abbreviationPair(
            away: awayFullName,
            home: homeFullName,
            sportKey: event.sport
        )
        let fallbackAway = TeamShortName.refusingResultWord(
            pairBadges.away,
            name: awayFullName,
            sportKey: event.sport
        ).uppercased()
        let fallbackHome = TeamShortName.refusingResultWord(
            pairBadges.home,
            name: homeFullName,
            sportKey: event.sport
        ).uppercased()

        let servedAway = sanitizeClubCode(event.awayTeamData?.abbreviation)
        let servedHome = sanitizeClubCode(event.homeTeamData?.abbreviation)

        if let a = servedAway, let h = servedHome, a != h {
            return (away: a, home: h)
        }
        let away = servedAway ?? fallbackAway
        let home = servedHome ?? fallbackHome
        if away == home {
            return (away: fallbackAway, home: fallbackHome)
        }
        return (away: away, home: home)
    }

    nonisolated private static func sanitizeClubCode(_ raw: String?) -> String? {
        guard let trimmed = trimmedNonEmpty(raw)?.uppercased(),
              trimmed.count >= 2, trimmed.count <= 5,
              trimmed != "WON", trimmed != "LOST", trimmed != "DRAW"
        else { return nil }
        return trimmed
    }

    nonisolated static func soccerCompetitionName(for event: EventDetail) -> String {
        let friendlyBySportKey: [String: String] = [
            "soccer_epl": "Premier League",
            "soccer_uefa_champs_league": "Champions League",
            "soccer_uefa_europa_league": "Europa League",
            "soccer_uefa_europa_conference_league": "Conference League",
            "soccer_mexico_ligamx": "Liga MX",
            "soccer_spain_la_liga": "La Liga",
            "soccer_germany_bundesliga": "Bundesliga",
            "soccer_italy_serie_a": "Serie A",
            "soccer_france_ligue_one": "Ligue 1",
            "soccer_usa_mls": "MLS",
            "soccer_brazil_campeonato": "Brasileirão",
            "soccer_netherlands_eredivisie": "Eredivisie",
            "soccer_portugal_primeira_liga": "Primeira Liga",
            "soccer_fifa_world_cup": "World Cup",
        ]
        if let key = event.sport?.lowercased(), let friendly = friendlyBySportKey[key] {
            return friendly
        }
        if let served = trimmedNonEmpty(event.sportName) {
            if served.caseInsensitiveCompare("UEFA Champions League") == .orderedSame {
                return "Champions League"
            }
            if served.caseInsensitiveCompare("English Premier League") == .orderedSame {
                return "Premier League"
            }
            return served
        }
        if let rawLeague = trimmedNonEmpty(event.metadata?.league) {
            let cleaned = rawLeague.replacingOccurrences(of: "_", with: " ")
            if !cleaned.isEmpty { return cleaned }
        }
        let fallback = sportDisplayName(for: event.sport)
        return fallback.isEmpty ? "Soccer" : fallback
    }

    /// Formats a normalized 3-way field (`home + draw + away == 1`) as whole `%`
    /// summing to `100%` (or tenths summing to `100.0%` when `numberStreams` is true).
    nonisolated static func soccerThreeWayChanceTexts(
        home: Double,
        draw: Double,
        away: Double,
        numberStreams: Bool
    ) -> (home: String, draw: String, away: String) {
        let total = home + draw + away
        guard total.isFinite, total > 0 else {
            return ("—", "—", "—")
        }
        let shares = [home / total, draw / total, away / total]

        if numberStreams {
            if shares.contains(where: { $0 < 0.0095 || $0 > 0.9905 }) {
                let formatted = shares.map { p -> String in
                    if p < 0.0095 { return "<1%" }
                    if p > 0.9905 { return ">99%" }
                    return String(format: "%.1f%%", p * 100.0)
                }
                return (formatted[0], formatted[1], formatted[2])
            }
            let units = largestRemainderUnits(shares: shares, targetTotal: 1000)
            return (
                String(format: "%.1f%%", Double(units[0]) / 10.0),
                String(format: "%.1f%%", Double(units[1]) / 10.0),
                String(format: "%.1f%%", Double(units[2]) / 10.0)
            )
        } else {
            if shares.contains(where: { $0 < 0.005 || $0 > 0.995 }) {
                let formatted = shares.map { p -> String in
                    if p < 0.005 { return "<1%" }
                    if p > 0.995 { return ">99%" }
                    return "\(Int((p * 100.0).rounded()))%"
                }
                return (formatted[0], formatted[1], formatted[2])
            }
            let units = largestRemainderUnits(shares: shares, targetTotal: 100)
            return ("\(units[0])%", "\(units[1])%", "\(units[2])%")
        }
    }

    nonisolated private static func largestRemainderUnits(
        shares: [Double],
        targetTotal: Int
    ) -> [Int] {
        let scaled = shares.map { max(0.0, $0) * Double(targetTotal) }
        var floors = scaled.map { Int(floor($0)) }
        let remainderNeeded = max(0, targetTotal - floors.reduce(0, +))
        if remainderNeeded > 0 {
            let indicesByRemainder = shares.indices.sorted { i, j in
                let remI = scaled[i] - Double(floors[i])
                let remJ = scaled[j] - Double(floors[j])
                if abs(remI - remJ) > 1e-9 {
                    return remI > remJ
                }
                return i < j
            }
            for idx in indicesByRemainder.prefix(remainderNeeded) {
                floors[idx] += 1
            }
        }
        return floors
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
        pregameMetaText(league: "NFL", event: event, now: now)
    }

    nonisolated static func pregameMetaText(
        league: String,
        event: EventDetail,
        now: Date = Date()
    ) -> String {
        var parts: [String] = [league]
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

    /// Plain-text finished soccer meta line (`Liga MX · Final · Nov 10`), never `"Settled"`.
    nonisolated static func soccerAfterMetaText(league: String, event: EventDetail) -> String {
        var parts: [String] = [league, "Final"]
        if let date = event.completedAt?.asDate ?? event.commenceTime?.asDate {
            parts.append(date.formatted(.dateTime.month(.abbreviated).day()))
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

    /// Bare pregame baseline percentages under the `"Pregame"` column header
    /// (`"49%"` / `"51%"`), never `"opened"` and never repeating `"pregame"`.
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
    /// column numbers `20.0` / `24.5`), honoring `#8617`, `#8156`, and `#5697`.
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
