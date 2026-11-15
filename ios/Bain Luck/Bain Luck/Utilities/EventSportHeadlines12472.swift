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
///
/// 6. **NFL after a game (`americanfootball_nfl`)**:
///    - Plain grey context line (`NFL · Final · Nov 8`), never `"Settled"`.
///    - Two rows (`Away`, `Home`) with right-aligned `Pregame · Final` columns so
///      the pregame chances sit next to each other and the final scores sit next to
///      each other; winner gets green `✓` and bold row styling; admitted pregame
///      projection prints as `"Proj. 21"` (never repeating `"Pregame"`).
///
/// 7. **MLB after a game (`baseball_mlb`)**:
///    - Plain grey context line (`MLB · Final · 9 Innings` or date).
///    - Two rows (`Away`, `Home`) with hairline row divider, right-aligned
///      `Pregame · Final` columns, winner `✓`, record (+ stakes), bare pregame `%`,
///      and final runs.
///
/// 8. **Soccer during a match (`soccer_*`)**:
///    - Live capsule (`LIVE · 64'`) + competition + feed pulse (`EkgHeartbeatView`) + `ⓘ`.
///    - World-soccer matchup row with dark live score pill (`1 – 0`), three
///      club-tinted boxes with streaming tenths (`51.4% · 27.8% · 20.8%`), a single
///      `"Pregame"` header above bare pregame `%` when available, and 3-way bar.
///
/// 9. **MMA (`mma` / `mma_*`)**:
///    - Before, during, and after fight headlines with zero `"Red/Blue Corner"`.
///    - Single `"Pregame"` column header during (`Pregame · Now`) and after
///      (`Pregame · Result`) a fight.
///
/// 10. **Tennis during a match (`tennis_*`) — SCORE-FIRST**:
///    - Live capsule (`LIVE · Set 2`) + tour (`ATP` / `WTA` / `Tennis`) + `EKG` + `ⓘ`.
///    - Score-first table: `Player` (surname) followed immediately by set
///      columns (`S1`, `S2`, … when period scores are served, else `Sets`) and
///      optional clock-parsed game `Pts` pill, then right-aligned
///      `Pregame · Now` columns + 2-way bar.
enum EventSportHeadlines12472 {

    nonisolated enum Phase: Equatable, Sendable {
        case before
        case during
        case after
    }

    nonisolated enum Kind: Equatable, Sendable {
        case nflBeforeGame
        case nflAfterGame
        case nbaBeforeGame
        case nbaDuringGame
        case nbaAfterGame
        case ncaafBeforeGame
        case ncaafDuringGame
        case ncaafAfterGame
        case ncaabBeforeGame
        case ncaabDuringGame
        case ncaabAfterGame
        case soccerBeforeGame
        case soccerDuringGame
        case soccerAfterGame
        case nhlDuringGame
        case mlbBeforeGame
        case mlbDuringGame
        case mlbAfterGame
        case mmaBeforeGame
        case mmaDuringGame
        case mmaAfterGame
        case tennisDuringGame

        nonisolated var phase: Phase {
            switch self {
            case .nflBeforeGame, .nbaBeforeGame, .ncaafBeforeGame, .ncaabBeforeGame, .mlbBeforeGame, .soccerBeforeGame, .mmaBeforeGame:
                return .before
            case .nbaDuringGame, .ncaafDuringGame, .ncaabDuringGame, .mlbDuringGame, .soccerDuringGame, .nhlDuringGame, .mmaDuringGame, .tennisDuringGame:
                return .during
            case .nflAfterGame, .nbaAfterGame, .ncaafAfterGame, .ncaabAfterGame, .soccerAfterGame, .mlbAfterGame, .mmaAfterGame:
                return .after
            }
        }

        nonisolated var accessibilityIdentifier: String {
            switch self {
            case .nflBeforeGame: return "event-headline-12472-nfl-before"
            case .nflAfterGame: return "event-headline-12472-nfl-after"
            case .nbaBeforeGame: return "event-headline-12472-nba-before"
            case .nbaDuringGame: return "event-headline-12472-nba-during"
            case .nbaAfterGame: return "event-headline-12472-nba-after"
            case .ncaafBeforeGame: return "event-headline-12472-ncaaf-before"
            case .ncaafDuringGame: return "event-headline-12472-ncaaf-during"
            case .ncaafAfterGame: return "event-headline-12472-ncaaf-after"
            case .ncaabBeforeGame: return "event-headline-12472-ncaab-before"
            case .ncaabDuringGame: return "event-headline-12472-ncaab-during"
            case .ncaabAfterGame: return "event-headline-12472-ncaab-after"
            case .soccerBeforeGame: return "event-headline-12472-soccer-before"
            case .soccerDuringGame: return "event-headline-12472-soccer-during"
            case .soccerAfterGame: return "event-headline-12472-soccer-after"
            case .nhlDuringGame: return "event-headline-12472-nhl-during"
            case .mlbBeforeGame: return "event-headline-12472-mlb-before"
            case .mlbDuringGame: return "event-headline-12472-mlb-during"
            case .mlbAfterGame: return "event-headline-12472-mlb-after"
            case .mmaBeforeGame: return "event-headline-12472-mma-before"
            case .mmaDuringGame: return "event-headline-12472-mma-during"
            case .mmaAfterGame: return "event-headline-12472-mma-after"
            case .tennisDuringGame: return "event-headline-12472-tennis-during"
            }
        }
    }

    nonisolated struct PregameColumnHeaders: Equatable, Sendable {
        let projected: String?
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

    nonisolated struct FinalColumnHeaders: Equatable, Sendable {
        let pregame: String?
        let finalLabel: String
    }

    nonisolated struct TennisSetColumn: Equatable, Sendable {
        let header: String
        let awayValue: String
        let homeValue: String
        let awayEmphasized: Bool
        let homeEmphasized: Bool
    }

    nonisolated struct TennisScoreFirstModel: Equatable, Sendable {
        let setColumns: [TennisSetColumn]
        let pointsColumn: (away: String, home: String)?
        let pregameHeader: String?
        let nowHeader: String

        nonisolated static func == (lhs: TennisScoreFirstModel, rhs: TennisScoreFirstModel) -> Bool {
            lhs.setColumns == rhs.setColumns
                && lhs.pointsColumn?.away == rhs.pointsColumn?.away
                && lhs.pointsColumn?.home == rhs.pointsColumn?.home
                && lhs.pregameHeader == rhs.pregameHeader
                && lhs.nowHeader == rhs.nowHeader
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
        var won: Bool? = nil
        var finalResultText: String? = nil
        var secondarySublineText: String? = nil
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
        var finalColumnHeaders: FinalColumnHeaders? = nil
        let away: TeamRowModel
        let home: TeamRowModel
        let pregameAwayMarker: Double?
        let soccerThreeWay: SoccerThreeWayModel?
        var tennisScoreFirst: TennisScoreFirstModel? = nil
        let showsEkg: Bool
        let stacksRecordUnderName: Bool
        var showsBottomBar: Bool = true
        var showsRowDivider: Bool = false
        let sourceMark: SourceMark?
        let confidenceTier: String?
    }

    nonisolated static func isMMASport(_ sport: String?) -> Bool {
        guard let sport = sport?.lowercased(), !sport.isEmpty else { return false }
        return sport == "mma" || sport.hasPrefix("mma_")
    }

    nonisolated static func isTennisSport(_ sport: String?) -> Bool {
        guard let sport = sport?.lowercased(), !sport.isEmpty else { return false }
        return sport == "tennis" || sport.hasPrefix("tennis_")
    }

    nonisolated static func isNCAAFSport(_ sport: String?) -> Bool {
        guard let sport = sport?.lowercased(), !sport.isEmpty else { return false }
        return sport == "americanfootball_ncaaf" || sport == "americanfootball_ncaaf_fcs"
    }

    nonisolated static func ncaafLeagueLabel(for sport: String?) -> String {
        sport?.lowercased() == "americanfootball_ncaaf_fcs" ? "NCAAF FCS" : "NCAAF"
    }

    nonisolated static func isNCAABSport(_ sport: String?) -> Bool {
        guard let sport = sport?.lowercased(), !sport.isEmpty else { return false }
        return sport == "basketball_ncaab" || sport == "basketball_wncaab"
    }

    nonisolated static func ncaabLeagueLabel(for sport: String?) -> String {
        sport?.lowercased() == "basketball_wncaab" ? "WNCAAB" : "NCAAB"
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

            if event.status == "live" {
                guard !EventState.showsVenueSettledVerdict(
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
                return .soccerDuringGame
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

        // Finished two-row headlines (`NFL after`, `MLB after`, `MMA after`).
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

            if event.sport == "americanfootball_nfl" {
                guard event.homeScore != nil, event.awayScore != nil else { return nil }
                return .nflAfterGame
            }
            if event.sport == "basketball_nba" {
                guard event.homeScore != nil, event.awayScore != nil else { return nil }
                return .nbaAfterGame
            }
            if isNCAAFSport(event.sport) {
                guard event.homeScore != nil, event.awayScore != nil else { return nil }
                return .ncaafAfterGame
            }
            if isNCAABSport(event.sport) {
                guard event.homeScore != nil, event.awayScore != nil else { return nil }
                return .ncaabAfterGame
            }
            if event.sport == "baseball_mlb" {
                guard event.homeScore != nil, event.awayScore != nil else { return nil }
                return .mlbAfterGame
            }
            if isMMASport(event.sport) {
                let outcome = EventOutcome.resolve(
                    status: event.status,
                    homeScore: event.homeScore,
                    awayScore: event.awayScore,
                    servedResult: event.heroSettledResult
                )
                guard outcome == .home || outcome == .away else { return nil }
                return .mmaAfterGame
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
        if event.sport == "basketball_nba" {
            return event.status == "live" ? .nbaDuringGame : .nbaBeforeGame
        }
        if isNCAAFSport(event.sport) {
            return event.status == "live" ? .ncaafDuringGame : .ncaafBeforeGame
        }
        if isNCAABSport(event.sport) {
            return event.status == "live" ? .ncaabDuringGame : .ncaabBeforeGame
        }
        if event.sport == "baseball_mlb" {
            return event.status == "live" ? .mlbDuringGame : .mlbBeforeGame
        }
        if event.sport == "icehockey_nhl" && event.status == "live" {
            return .nhlDuringGame
        }
        if isMMASport(event.sport) {
            return event.status == "live" ? .mmaDuringGame : .mmaBeforeGame
        }
        if isTennisSport(event.sport) && event.status == "live" {
            return .tennisDuringGame
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
            return resolveSoccerBefore(
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                numberStreams: numberStreams,
                gameMarkets: gameMarkets,
                now: now
            )
        case .soccerAfterGame:
            return resolveSoccerAfter(
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                gameMarkets: gameMarkets,
                now: now
            )
        case .soccerDuringGame:
            return resolveSoccerDuring(
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                liveStatusText: liveStatusText,
                hasScore: hasScore,
                gameMarkets: gameMarkets,
                now: now
            )
        case .nflAfterGame, .nbaAfterGame, .ncaafAfterGame, .ncaabAfterGame, .mlbAfterGame, .mmaAfterGame:
            return resolveFinishedTwoWay(
                resolvedKind: resolvedKind,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames
            )
        case .nflBeforeGame, .nbaBeforeGame, .nbaDuringGame,
             .ncaafBeforeGame, .ncaafDuringGame,
             .ncaabBeforeGame, .ncaabDuringGame,
             .mlbBeforeGame, .mlbDuringGame,
             .nhlDuringGame, .mmaBeforeGame, .mmaDuringGame, .tennisDuringGame:
            return resolveOpenTwoWay(
                resolvedKind: resolvedKind,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                liveStatusText: liveStatusText,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                now: now
            )
        }
    }

    @inline(never)
    nonisolated private static func resolveSoccerBefore(
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        numberStreams: Bool,
        gameMarkets: GameMarketsResponse?,
        now: Date
    ) -> Model? {
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
    }

    @inline(never)
    nonisolated private static func resolveSoccerAfter(
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        gameMarkets: GameMarketsResponse?,
        now: Date
    ) -> Model? {
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
    }

    @inline(never)
    nonisolated private static func resolveSoccerDuring(
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        liveStatusText: String?,
        hasScore: Bool,
        gameMarkets: GameMarketsResponse?,
        now: Date
    ) -> Model? {
        guard let shares = extractSoccerThreeWayOpenShares(
            event: event,
            gameMarkets: gameMarkets,
            now: now
        ) else { return nil }

        let marketSnap = extractSoccerThreeWayMarketSnapshot(
            event: event,
            gameMarkets: gameMarkets,
            finished: false,
            now: now
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
        let codes = soccerClubCodes(
            event: event,
            awayFullName: awayFullName,
            homeFullName: homeFullName
        )
        let formatted = soccerThreeWayChanceTexts(
            home: shares.home,
            draw: shares.draw,
            away: shares.away,
            numberStreams: true
        )
        let league = soccerCompetitionName(for: event)
        let periodStatus = trimmedNonEmpty(liveStatusText)
        let liveBadge = periodStatus.map { "LIVE · \($0)" } ?? "LIVE"
        let hasLiveScore = hasScore && event.homeScore != nil && event.awayScore != nil
        let centerText = hasLiveScore
            ? "\(event.homeScore ?? 0) \u{2013} \(event.awayScore ?? 0)"
            : "90' Reg."
        let confidenceTier = Confidence.fromSources(
            sourceCount: event.winProbabilitySources?.count,
            hasMovement: pregameShares.map { abs(shares.home - $0.home) > 0.001 } ?? false
        )?.rawValue

        let threeWay = SoccerThreeWayModel(
            centerTagText: centerText,
            isScorePill: hasLiveScore,
            homeBox: SoccerThreeWayBox(
                role: .home,
                headerLabel: "\(codes.home) WIN",
                dotTone: .homeClub,
                boxTone: .homeClub,
                mainText: formatted.home,
                pregameChanceText: pregameTexts?.home,
                rawShare: shares.home
            ),
            drawBox: SoccerThreeWayBox(
                role: .draw,
                headerLabel: "DRAW",
                dotTone: .drawNeutral,
                boxTone: .drawNeutral,
                mainText: formatted.draw,
                pregameChanceText: pregameTexts?.draw,
                rawShare: shares.draw
            ),
            awayBox: SoccerThreeWayBox(
                role: .away,
                headerLabel: "\(codes.away) WIN",
                dotTone: .awayClub,
                boxTone: .awayClub,
                mainText: formatted.away,
                pregameChanceText: pregameTexts?.away,
                rawShare: shares.away
            ),
            pregameHeader: pregameTexts != nil ? "Pregame" : nil,
            showsBottomBar: true
        )

        return Model(
            eventId: event.id,
            sportKey: event.sport ?? "soccer",
            kind: .soccerDuringGame,
            plainMetaText: nil,
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            broadcast: trimmedNonEmpty(event.espn?.broadcast),
            eventStatus: event.status,
            liveBadgeText: liveBadge,
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
                liveScore: hasScore ? event.awayScore : nil,
                pregameChanceText: pregameTexts?.away,
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
                liveScore: hasScore ? event.homeScore : nil,
                pregameChanceText: pregameTexts?.home,
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
    }

    @inline(never)
    nonisolated private static func resolveFinishedTwoWay(
        resolvedKind: Kind,
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String)
    ) -> Model? {
        let pregame = PrematchReading.resolve(
            prematch: event.prematchOdds,
            opening: event.openingOdds
        )
        let pregameTexts = nbaPregameTexts(pregame)
        let confidenceTier = Confidence.fromSources(
            sourceCount: event.winProbabilitySources?.count,
            hasMovement: false
        )?.rawValue
        let outcome = EventOutcome.resolve(
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore,
            servedResult: event.heroSettledResult
        )
        let awayWon: Bool? = {
            switch outcome {
            case .away: return true
            case .home: return false
            case .draw, .undecided: return nil
            }
        }()
        let homeWon: Bool? = {
            switch outcome {
            case .home: return true
            case .away: return false
            case .draw, .undecided: return nil
            }
        }()
        let markHomeProb = pregame?.homeProbability
            ?? (homeWon == true ? 1.0 : homeWon == false ? 0.0 : 0.5)
        let markAwayProb = pregame?.awayProbability
            ?? (awayWon == true ? 1.0 : awayWon == false ? 0.0 : 0.5)

        switch resolvedKind {
        case .nflAfterGame:
            return resolveStandardFinished(
                kind: .nflAfterGame,
                sportKey: "americanfootball_nfl",
                league: "NFL",
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                pregameTexts: pregameTexts,
                awayWon: awayWon,
                homeWon: homeWon,
                markAwayProb: markAwayProb,
                markHomeProb: markHomeProb,
                confidenceTier: confidenceTier
            )

        case .nbaAfterGame:
            return resolveStandardFinished(
                kind: .nbaAfterGame,
                sportKey: "basketball_nba",
                league: "NBA",
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                pregameTexts: pregameTexts,
                awayWon: awayWon,
                homeWon: homeWon,
                markAwayProb: markAwayProb,
                markHomeProb: markHomeProb,
                confidenceTier: confidenceTier
            )

        case .ncaafAfterGame:
            return resolveStandardFinished(
                kind: .ncaafAfterGame,
                sportKey: event.sport ?? "americanfootball_ncaaf",
                league: ncaafLeagueLabel(for: event.sport),
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                pregameTexts: pregameTexts,
                awayWon: awayWon,
                homeWon: homeWon,
                markAwayProb: markAwayProb,
                markHomeProb: markHomeProb,
                confidenceTier: confidenceTier
            )

        case .ncaabAfterGame:
            return resolveStandardFinished(
                kind: .ncaabAfterGame,
                sportKey: event.sport ?? "basketball_ncaab",
                league: ncaabLeagueLabel(for: event.sport),
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                pregameTexts: pregameTexts,
                awayWon: awayWon,
                homeWon: homeWon,
                markAwayProb: markAwayProb,
                markHomeProb: markHomeProb,
                confidenceTier: confidenceTier
            )

        case .mlbAfterGame:
            guard let awayScore = event.awayScore, let homeScore = event.homeScore else {
                return nil
            }
            let stakes = trimmedNonEmpty(event.standingsContext?.stakes)
            let finalProj = stakes == nil ? qualifiedFinalProjectionPair(event: event) : nil
            let awaySubline = finishedSubline(
                record: trimmedNonEmpty(event.awayTeamData?.record),
                extra: stakes ?? finalProj.map { "Proj. \($0.away)" }
            )
            let homeSubline = finishedSubline(
                record: trimmedNonEmpty(event.homeTeamData?.record),
                extra: stakes ?? finalProj.map { "Proj. \($0.home)" }
            )
            let meta = mlbAfterMetaText(event: event)
            return Model(
                eventId: event.id,
                sportKey: "baseball_mlb",
                kind: .mlbAfterGame,
                plainMetaText: meta,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: nil,
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: "MLB",
                pregameColumnHeaders: nil,
                liveColumnHeaders: nil,
                finalColumnHeaders: FinalColumnHeaders(
                    pregame: pregameTexts != nil ? "Pregame" : nil,
                    finalLabel: "Final"
                ),
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: nil,
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: awayScore,
                    pregameChanceText: pregameTexts?.away,
                    winChanceText: pregameTexts?.away ?? "—",
                    rawProbability: markAwayProb,
                    won: awayWon,
                    finalResultText: "\(awayScore)",
                    secondarySublineText: awaySubline
                ),
                home: TeamRowModel(
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    record: nil,
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: homeScore,
                    pregameChanceText: pregameTexts?.home,
                    winChanceText: pregameTexts?.home ?? "—",
                    rawProbability: markHomeProb,
                    won: homeWon,
                    finalResultText: "\(homeScore)",
                    secondarySublineText: homeSubline
                ),
                pregameAwayMarker: nil,
                soccerThreeWay: nil,
                showsEkg: false,
                stacksRecordUnderName: true,
                showsBottomBar: false,
                showsRowDivider: true,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )

        case .mmaAfterGame:
            guard awayWon != nil, homeWon != nil else { return nil }
            let meta = soccerAfterMetaText(league: "MMA", event: event)
            return Model(
                eventId: event.id,
                sportKey: event.sport ?? "mma_mixed_martial_arts",
                kind: .mmaAfterGame,
                plainMetaText: meta,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: nil,
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: "MMA",
                pregameColumnHeaders: nil,
                liveColumnHeaders: nil,
                finalColumnHeaders: FinalColumnHeaders(
                    pregame: pregameTexts != nil ? "Pregame" : nil,
                    finalLabel: "Result"
                ),
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: nil,
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: nil,
                    pregameChanceText: pregameTexts?.away,
                    winChanceText: pregameTexts?.away ?? "—",
                    rawProbability: markAwayProb,
                    won: awayWon,
                    finalResultText: awayWon == true ? "Won" : "Lost",
                    secondarySublineText: trimmedNonEmpty(event.awayTeamData?.record)
                ),
                home: TeamRowModel(
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                    record: nil,
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: nil,
                    pregameChanceText: pregameTexts?.home,
                    winChanceText: pregameTexts?.home ?? "—",
                    rawProbability: markHomeProb,
                    won: homeWon,
                    finalResultText: homeWon == true ? "Won" : "Lost",
                    secondarySublineText: trimmedNonEmpty(event.homeTeamData?.record)
                ),
                pregameAwayMarker: nil,
                soccerThreeWay: nil,
                showsEkg: false,
                stacksRecordUnderName: true,
                showsBottomBar: false,
                showsRowDivider: false,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )

        default:
            return nil
        }
    }

    @inline(never)
    nonisolated private static func resolveStandardFinished(
        kind: Kind,
        sportKey: String,
        league: String,
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        pregameTexts: (away: String, home: String)?,
        awayWon: Bool?,
        homeWon: Bool?,
        markAwayProb: Double,
        markHomeProb: Double,
        confidenceTier: String?,
        showsRowDivider: Bool = false
    ) -> Model? {
        guard let awayScore = event.awayScore, let homeScore = event.homeScore else {
            return nil
        }
        let finalProj = qualifiedFinalProjectionPair(event: event)
        let awaySubline = finishedSubline(
            record: trimmedNonEmpty(event.awayTeamData?.record),
            extra: finalProj.map { "Proj. \($0.away)" }
        )
        let homeSubline = finishedSubline(
            record: trimmedNonEmpty(event.homeTeamData?.record),
            extra: finalProj.map { "Proj. \($0.home)" }
        )
        let meta = soccerAfterMetaText(league: league, event: event)
        return Model(
            eventId: event.id,
            sportKey: sportKey,
            kind: kind,
            plainMetaText: meta,
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            broadcast: nil,
            eventStatus: event.status,
            liveBadgeText: nil,
            leagueLabel: league,
            pregameColumnHeaders: nil,
            liveColumnHeaders: nil,
            finalColumnHeaders: FinalColumnHeaders(
                pregame: pregameTexts != nil ? "Pregame" : nil,
                finalLabel: "Final"
            ),
            away: TeamRowModel(
                fullName: awayFullName,
                opponentFullName: homeFullName,
                shortName: shortNames.away,
                logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                record: nil,
                projectedText: nil,
                pregameProjectedNumberText: nil,
                liveScore: awayScore,
                pregameChanceText: pregameTexts?.away,
                winChanceText: pregameTexts?.away ?? "—",
                rawProbability: markAwayProb,
                won: awayWon,
                finalResultText: "\(awayScore)",
                secondarySublineText: awaySubline
            ),
            home: TeamRowModel(
                fullName: homeFullName,
                opponentFullName: awayFullName,
                shortName: shortNames.home,
                logoURL: event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall,
                record: nil,
                projectedText: nil,
                pregameProjectedNumberText: nil,
                liveScore: homeScore,
                pregameChanceText: pregameTexts?.home,
                winChanceText: pregameTexts?.home ?? "—",
                rawProbability: markHomeProb,
                won: homeWon,
                finalResultText: "\(homeScore)",
                secondarySublineText: homeSubline
            ),
            pregameAwayMarker: nil,
            soccerThreeWay: nil,
            showsEkg: false,
            stacksRecordUnderName: true,
            showsBottomBar: false,
            showsRowDivider: showsRowDivider,
            sourceMark: event.sourceMark,
            confidenceTier: confidenceTier
        )
    }

    @inline(never)
    nonisolated private static func resolveOpenTwoWay(
        resolvedKind: Kind,
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        liveStatusText: String?,
        hasScore: Bool,
        numberStreams: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        now: Date
    ) -> Model? {
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
            return resolveStandardBefore(
                kind: .nflBeforeGame,
                sportKey: "americanfootball_nfl",
                league: "NFL",
                allowsStreamingTenths: true,
                showsChanceHeaderWithoutProjection: false,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                shown: shown,
                awayProb: awayProb,
                homeProb: homeProb,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                confidenceTier: confidenceTier,
                now: now
            )
        case .nbaBeforeGame:
            return resolveStandardBefore(
                kind: .nbaBeforeGame,
                sportKey: "basketball_nba",
                league: "NBA",
                allowsStreamingTenths: false,
                showsChanceHeaderWithoutProjection: true,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                shown: shown,
                awayProb: awayProb,
                homeProb: homeProb,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                confidenceTier: confidenceTier,
                now: now
            )
        case .ncaafBeforeGame:
            return resolveStandardBefore(
                kind: .ncaafBeforeGame,
                sportKey: event.sport ?? "americanfootball_ncaaf",
                league: ncaafLeagueLabel(for: event.sport),
                allowsStreamingTenths: false,
                showsChanceHeaderWithoutProjection: true,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                shown: shown,
                awayProb: awayProb,
                homeProb: homeProb,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                confidenceTier: confidenceTier,
                now: now
            )
        case .ncaabBeforeGame:
            return resolveStandardBefore(
                kind: .ncaabBeforeGame,
                sportKey: event.sport ?? "basketball_ncaab",
                league: ncaabLeagueLabel(for: event.sport),
                allowsStreamingTenths: false,
                showsChanceHeaderWithoutProjection: true,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                shown: shown,
                awayProb: awayProb,
                homeProb: homeProb,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                confidenceTier: confidenceTier,
                now: now
            )
        case .mlbBeforeGame:
            return resolveStandardBefore(
                kind: .mlbBeforeGame,
                sportKey: "baseball_mlb",
                league: "MLB",
                allowsStreamingTenths: false,
                showsChanceHeaderWithoutProjection: true,
                showsRowDivider: true,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                shown: shown,
                awayProb: awayProb,
                homeProb: homeProb,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                confidenceTier: confidenceTier,
                now: now
            )
        case .nbaDuringGame, .ncaafDuringGame, .ncaabDuringGame, .mlbDuringGame, .nhlDuringGame, .mmaDuringGame:
            return resolveLiveStandard(
                resolvedKind: resolvedKind,
                event: event,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                awayProb: awayProb,
                homeProb: homeProb,
                liveStatusText: liveStatusText,
                hasScore: hasScore,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                confidenceTier: confidenceTier,
                now: now
            )
        case .mmaBeforeGame:
            let chances = nflPregameChanceTexts(
                shown: shown,
                away: awayProb,
                home: homeProb,
                numberStreams: numberStreams
            )
            let meta = pregameMetaText(league: "MMA", event: event, now: now)
            return Model(
                eventId: event.id,
                sportKey: event.sport ?? "mma_mixed_martial_arts",
                kind: .mmaBeforeGame,
                plainMetaText: meta,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: "MMA",
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
                    winChanceText: chances.away,
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
                    liveScore: nil,
                    pregameChanceText: nil,
                    winChanceText: chances.home,
                    rawProbability: homeProb
                ),
                pregameAwayMarker: nil,
                soccerThreeWay: nil,
                showsEkg: true,
                stacksRecordUnderName: true,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )
        case .tennisDuringGame:
            let tenths = EventHeadlineTenths10090.pair(home: homeProb, away: awayProb)
            let pregame = PrematchReading.resolve(
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )
            let pregameTexts = nbaPregameTexts(pregame)
            let tour = tennisTourLabel(for: event)
            let liveSetStatus = tennisLiveStatusBadge(
                event: event,
                liveStatusText: liveStatusText
            )
            let scoreFirst = buildTennisScoreFirstModel(
                event: event,
                hasScore: hasScore,
                hasPregame: pregameTexts != nil
            )
            return Model(
                eventId: event.id,
                sportKey: event.sport ?? "tennis_atp",
                kind: .tennisDuringGame,
                plainMetaText: nil,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: liveSetStatus,
                leagueLabel: tour,
                pregameColumnHeaders: nil,
                liveColumnHeaders: nil,
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: nil,
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
                    record: nil,
                    projectedText: nil,
                    pregameProjectedNumberText: nil,
                    liveScore: hasScore ? event.homeScore : nil,
                    pregameChanceText: pregameTexts?.home,
                    winChanceText: tenths.home,
                    rawProbability: homeProb
                ),
                pregameAwayMarker: pregame?.awayProbability,
                soccerThreeWay: nil,
                tennisScoreFirst: scoreFirst,
                showsEkg: true,
                stacksRecordUnderName: false,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )
        default:
            return nil
        }
    }

    @inline(never)
    nonisolated private static func resolveStandardBefore(
        kind: Kind,
        sportKey: String,
        league: String,
        allowsStreamingTenths: Bool,
        showsChanceHeaderWithoutProjection: Bool,
        showsRowDivider: Bool = false,
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        shown: OpeningLineHero,
        awayProb: Double,
        homeProb: Double,
        hasScore: Bool,
        numberStreams: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        confidenceTier: String?,
        now: Date
    ) -> Model {
        let chances = nflPregameChanceTexts(
            shown: shown,
            away: awayProb,
            home: homeProb,
            numberStreams: allowsStreamingTenths && numberStreams
        )
        let projections = admittedPregameProjectedPair(
            event: event,
            hasScore: hasScore,
            ladderHome: ladderHome,
            ladderAway: ladderAway,
            now: now
        )
        let pregameHeaders: PregameColumnHeaders? = {
            if projections != nil {
                return PregameColumnHeaders(projected: "Proj.", chance: "Chance")
            }
            if showsChanceHeaderWithoutProjection {
                return PregameColumnHeaders(projected: nil, chance: "Chance")
            }
            return nil
        }()
        let meta = pregameMetaText(league: league, event: event, now: now)
        return Model(
            eventId: event.id,
            sportKey: sportKey,
            kind: kind,
            plainMetaText: meta,
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            broadcast: trimmedNonEmpty(event.espn?.broadcast),
            eventStatus: event.status,
            liveBadgeText: nil,
            leagueLabel: league,
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
            showsRowDivider: showsRowDivider,
            sourceMark: event.sourceMark,
            confidenceTier: confidenceTier
        )
    }

    @inline(never)
    nonisolated private static func resolveLiveStandard(
        resolvedKind: Kind,
        event: EventDetail,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        awayProb: Double,
        homeProb: Double,
        liveStatusText: String?,
        hasScore: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        confidenceTier: String?,
        now: Date
    ) -> Model? {
        let tenths = EventHeadlineTenths10090.pair(home: homeProb, away: awayProb)
        let pregame = PrematchReading.resolve(
            prematch: event.prematchOdds,
            opening: event.openingOdds
        )
        let pregameTexts = nbaPregameTexts(pregame)
        let periodStatus = trimmedNonEmpty(liveStatusText)
        let liveBadge = periodStatus.map { "LIVE · \($0)" } ?? "LIVE"

        switch resolvedKind {
        case .nbaDuringGame, .ncaafDuringGame, .ncaabDuringGame, .mlbDuringGame:
            let liveSportKey: String = {
                switch resolvedKind {
                case .ncaafDuringGame: return event.sport ?? "americanfootball_ncaaf"
                case .ncaabDuringGame: return event.sport ?? "basketball_ncaab"
                case .mlbDuringGame: return "baseball_mlb"
                default: return "basketball_nba"
                }
            }()
            let liveLeague: String = {
                switch resolvedKind {
                case .ncaafDuringGame: return ncaafLeagueLabel(for: event.sport)
                case .ncaabDuringGame: return ncaabLeagueLabel(for: event.sport)
                case .mlbDuringGame: return "MLB"
                default: return "NBA"
                }
            }()
            let liveProjections = admittedLiveProjectedPair(
                event: event,
                hasScore: hasScore,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                now: now
            )
            let showsStackedRecordWhenProjectionAbsent = resolvedKind != .nbaDuringGame && liveProjections == nil
            let hasLiveScore = hasScore && (event.awayScore != nil || event.homeScore != nil)
            let columnHeaders = LiveColumnHeaders(
                score: hasLiveScore ? "Score" : nil,
                pregame: pregameTexts != nil ? "Pregame" : nil,
                now: "Now"
            )
            return Model(
                eventId: event.id,
                sportKey: liveSportKey,
                kind: resolvedKind,
                plainMetaText: nil,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: liveBadge,
                leagueLabel: liveLeague,
                pregameColumnHeaders: nil,
                liveColumnHeaders: columnHeaders,
                away: TeamRowModel(
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall,
                    record: showsStackedRecordWhenProjectionAbsent ? trimmedNonEmpty(event.awayTeamData?.record) : nil,
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
                    record: showsStackedRecordWhenProjectionAbsent ? trimmedNonEmpty(event.homeTeamData?.record) : nil,
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
                stacksRecordUnderName: showsStackedRecordWhenProjectionAbsent,
                showsRowDivider: resolvedKind == .mlbDuringGame,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )

        case .nhlDuringGame:
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

        case .mmaDuringGame:
            let columnHeaders = LiveColumnHeaders(
                score: nil,
                pregame: pregameTexts != nil ? "Pregame" : nil,
                now: "Now"
            )
            return Model(
                eventId: event.id,
                sportKey: event.sport ?? "mma_mixed_martial_arts",
                kind: .mmaDuringGame,
                plainMetaText: nil,
                commenceTime: event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: liveBadge,
                leagueLabel: "MMA",
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
                    liveScore: nil,
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
                    liveScore: nil,
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

        default:
            return nil
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

    // MARK: - Finished & Tennis Score-First Helpers

    nonisolated private static func qualifiedFinalProjectionPair(
        event: EventDetail
    ) -> (away: Int, home: Int)? {
        guard EventState.isFinished(event.status),
              let homeScore = event.homeScore, let awayScore = event.awayScore,
              homeScore >= 0, awayScore >= 0,
              let p = event.pregameProjection,
              p.kind == "last_before_scheduled_start",
              p.boundary == "scheduled_start",
              p.source == "sportsbooks",
              p.basis == "consensus_spread_total",
              let sportUnit = FinalForecastComparison11296.unit(forSport: event.sport),
              p.unit == sportUnit,
              let actualPeriod = FinalForecastComparison11296.actualPeriod(
                  sport: event.sport,
                  servedFinalScorePeriod: event.finalScorePeriod
              ),
              p.period == actualPeriod.rawValue,
              let books = p.bookmakerCount.flatMap({ Int(exactly: $0) }), books >= 1,
              let earliest = p.earliestCapturedAt?.asDate,
              let latest = p.latestCapturedAt?.asDate,
              let boundary = p.boundaryAt?.asDate,
              earliest <= latest, latest < boundary,
              let home = p.projectedHomeScore, let away = p.projectedAwayScore,
              home.isFinite, away.isFinite, home > 0, away > 0
        else { return nil }

        let vocab = SportVocab.forSport(event.sport)
        guard vocab.sportsbookSpreadIsAMargin,
              let roundedHome = Int(exactly: home.rounded()),
              let roundedAway = Int(exactly: away.rounded()),
              roundedHome != roundedAway || vocab.canEndInATie
        else { return nil }

        return (away: roundedAway, home: roundedHome)
    }

    nonisolated private static func finishedSubline(
        record: String?,
        extra: String?
    ) -> String? {
        let parts = [record, extra].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }

    nonisolated static func mlbAfterMetaText(event: EventDetail) -> String {
        let awayInnings = event.boxScoreData?.awayPeriodScores?.compactMap { $0 }.count ?? 0
        let homeInnings = event.boxScoreData?.homePeriodScores?.compactMap { $0 }.count ?? 0
        let playedInnings = max(awayInnings, homeInnings)
        if playedInnings >= 5 {
            return "MLB · Final · \(playedInnings) Innings"
        }
        return soccerAfterMetaText(league: "MLB", event: event)
    }

    nonisolated static func tennisTourLabel(for event: EventDetail) -> String {
        if let key = event.sport?.lowercased() {
            if key.hasPrefix("tennis_atp") { return "ATP" }
            if key.hasPrefix("tennis_wta") { return "WTA" }
        }
        if let served = trimmedNonEmpty(event.sportName) {
            let upper = served.uppercased()
            if upper.contains("ATP") { return "ATP" }
            if upper.contains("WTA") { return "WTA" }
            return served
        }
        return "Tennis"
    }

    nonisolated static func tennisLiveStatusBadge(
        event: EventDetail,
        liveStatusText: String?
    ) -> String {
        if let rawPeriod = trimmedNonEmpty(event.espn?.period) {
            let normalized = normalizeTennisSetLabel(rawPeriod)
            return "LIVE · \(normalized)"
        }
        let setCount = max(
            event.boxScoreData?.awayPeriodScores?.compactMap { $0 }.count ?? 0,
            event.boxScoreData?.homePeriodScores?.compactMap { $0 }.count ?? 0
        )
        if setCount >= 1 {
            return "LIVE · Set \(setCount)"
        }
        if let status = trimmedNonEmpty(liveStatusText),
           parseTennisGamePointsFromClock(status) == nil {
            return "LIVE · \(status)"
        }
        return "LIVE"
    }

    nonisolated private static func normalizeTennisSetLabel(_ raw: String) -> String {
        let lower = raw.lowercased()
        if lower.hasPrefix("set ") { return raw }
        if lower == "1st" || lower == "1st set" || lower == "s1" || lower == "1" { return "Set 1" }
        if lower == "2nd" || lower == "2nd set" || lower == "s2" || lower == "2" { return "Set 2" }
        if lower == "3rd" || lower == "3rd set" || lower == "s3" || lower == "3" { return "Set 3" }
        if lower == "4th" || lower == "4th set" || lower == "s4" || lower == "4" { return "Set 4" }
        if lower == "5th" || lower == "5th set" || lower == "s5" || lower == "5" { return "Set 5" }
        return raw
    }

    nonisolated private static let tennisPointsPairRegex: NSRegularExpression? = try? NSRegularExpression(
        pattern: #"^\s*(0|15|30|40|Ad|AD)\s*[-–:]\s*(0|15|30|40|Ad|AD)\s*$"#
    )

    nonisolated static func parseTennisGamePointsFromClock(
        _ rawClock: String?
    ) -> (away: String, home: String)? {
        guard let rawClock = trimmedNonEmpty(rawClock) else { return nil }
        let nsRange = NSRange(rawClock.startIndex..<rawClock.endIndex, in: rawClock)
        guard let match = tennisPointsPairRegex?.firstMatch(in: rawClock, options: [], range: nsRange),
              let firstRange = Range(match.range(at: 1), in: rawClock),
              let secondRange = Range(match.range(at: 2), in: rawClock)
        else { return nil }
        let awayPts = String(rawClock[firstRange])
        let homePts = String(rawClock[secondRange])
        return (
            away: awayPts.uppercased() == "AD" ? "Ad" : awayPts,
            home: homePts.uppercased() == "AD" ? "Ad" : homePts
        )
    }

    nonisolated static func buildTennisScoreFirstModel(
        event: EventDetail,
        hasScore: Bool,
        hasPregame: Bool
    ) -> TennisScoreFirstModel {
        let awayPeriods = event.boxScoreData?.awayPeriodScores ?? []
        let homePeriods = event.boxScoreData?.homePeriodScores ?? []
        let maxSets = max(awayPeriods.count, homePeriods.count)

        var setColumns: [TennisSetColumn] = []
        if maxSets > 0 {
            var pairs: [(index: Int, away: Int, home: Int)] = []
            for idx in 0..<maxSets {
                let a = idx < awayPeriods.count ? awayPeriods[idx] : nil
                let h = idx < homePeriods.count ? homePeriods[idx] : nil
                if let a, let h {
                    pairs.append((index: idx + 1, away: a, home: h))
                }
            }
            for (offset, entry) in pairs.enumerated() {
                let isCurrentSet = (offset == pairs.count - 1)
                setColumns.append(
                    TennisSetColumn(
                        header: "S\(entry.index)",
                        awayValue: "\(entry.away)",
                        homeValue: "\(entry.home)",
                        awayEmphasized: isCurrentSet || entry.away > entry.home,
                        homeEmphasized: isCurrentSet || entry.home > entry.away
                    )
                )
            }
        }

        if setColumns.isEmpty, hasScore, (event.awayScore != nil || event.homeScore != nil) {
            let awaySets = event.awayScore
            let homeSets = event.homeScore
            setColumns.append(
                TennisSetColumn(
                    header: "Sets",
                    awayValue: awaySets.map(String.init) ?? "—",
                    homeValue: homeSets.map(String.init) ?? "—",
                    awayEmphasized: true,
                    homeEmphasized: true
                )
            )
        }

        let pointsColumn = parseTennisGamePointsFromClock(event.espn?.gameClock)

        return TennisScoreFirstModel(
            setColumns: setColumns,
            pointsColumn: pointsColumn,
            pregameHeader: hasPregame ? "Pregame" : nil,
            nowHeader: "Now"
        )
    }

    nonisolated private static func trimmedNonEmpty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return nil
        }
        return text
    }
}
