import SwiftUI

/// Direction 199 & Rulings 200-B, 197, 194-A — Single unified value model and
/// resolver for every sport and state on the event page (`#12472` / `#12538`).
///
/// Key invariants:
/// 1. **Never returns `nil`**: `resolve(...)` produces a `Model` for every sport
///    and state (including all 23 former fallback cases: missing final scores,
///    missing live/pregame odds, opening-only quotes, 2-way or extra-time soccer,
///    MMA draws/no-contests, venue-settled/closed rows, postponed/suspended/canceled
///    games, NHL before/after, tennis before/after, boxing, cricket, rugby, esports,
///    and unknown sport keys).
/// 2. **One column-and-row structure**:
///    - `before`: `Proj. · Chance` (`Chance` on non-point-total sports such as tennis/MMA/boxing)
///    - `during`: `<Score slot> · Proj. · Now` + segmented bar + one grey line
///      under the bar (`"Pregame  <Fav> <X>% · projected <A>–<B>"`, from `prematch_odds`
///      only — never `opening_odds` — omitting missing halves and hiding when both are missing).
///      Never a `Pregame` column during a game; never team records during a game.
///    - `after`: `[Set columns] · Pregame · Final`, winner ticked (`✓`), **no bar**.
/// 3. **Missing values leave their cell empty (`""`)** without changing the column layout.
/// 4. **Never prints** `"opening"`, `"opened"`, `"stale"`, `"Settled"`, `"3 venues"`,
///    `"Current win chance"`, or `"Projection before"`, and never repeats a label twice.
enum EventSportHeadlines12472 {

    nonisolated enum Phase: String, Equatable, Sendable, CaseIterable {
        case before
        case during
        case after
    }

    nonisolated enum Kind: Equatable, Sendable {
        case nflBeforeGame
        case nflDuringGame
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
        case nhlBeforeGame
        case nhlDuringGame
        case nhlAfterGame
        case mlbBeforeGame
        case mlbDuringGame
        case mlbAfterGame
        case mmaBeforeGame
        case mmaDuringGame
        case mmaAfterGame
        case tennisBeforeGame
        case tennisDuringGame
        case tennisAfterGame
        case otherBeforeGame
        case otherDuringGame
        case otherAfterGame

        nonisolated var phase: Phase {
            switch self {
            case .nflBeforeGame, .nbaBeforeGame, .ncaafBeforeGame, .ncaabBeforeGame,
                 .soccerBeforeGame, .nhlBeforeGame, .mlbBeforeGame, .mmaBeforeGame,
                 .tennisBeforeGame, .otherBeforeGame:
                return .before
            case .nflDuringGame, .nbaDuringGame, .ncaafDuringGame, .ncaabDuringGame,
                 .soccerDuringGame, .nhlDuringGame, .mlbDuringGame, .mmaDuringGame,
                 .tennisDuringGame, .otherDuringGame:
                return .during
            case .nflAfterGame, .nbaAfterGame, .ncaafAfterGame, .ncaabAfterGame,
                 .soccerAfterGame, .nhlAfterGame, .mlbAfterGame, .mmaAfterGame,
                 .tennisAfterGame, .otherAfterGame:
                return .after
            }
        }

        nonisolated var accessibilityIdentifier: String {
            switch self {
            case .nflBeforeGame: return "event-headline-12472-nfl-before"
            case .nflDuringGame: return "event-headline-12472-nfl-during"
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
            case .nhlBeforeGame: return "event-headline-12472-nhl-before"
            case .nhlDuringGame: return "event-headline-12472-nhl-during"
            case .nhlAfterGame: return "event-headline-12472-nhl-after"
            case .mlbBeforeGame: return "event-headline-12472-mlb-before"
            case .mlbDuringGame: return "event-headline-12472-mlb-during"
            case .mlbAfterGame: return "event-headline-12472-mlb-after"
            case .mmaBeforeGame: return "event-headline-12472-mma-before"
            case .mmaDuringGame: return "event-headline-12472-mma-during"
            case .mmaAfterGame: return "event-headline-12472-mma-after"
            case .tennisBeforeGame: return "event-headline-12472-tennis-before"
            case .tennisDuringGame: return "event-headline-12472-tennis-during"
            case .tennisAfterGame: return "event-headline-12472-tennis-after"
            case .otherBeforeGame: return "event-headline-12472-other-before"
            case .otherDuringGame: return "event-headline-12472-other-during"
            case .otherAfterGame: return "event-headline-12472-other-after"
            }
        }
    }

    // MARK: - Unified Column & Row Specs

    nonisolated enum ColumnRole: Equatable, Sendable {
        case setScore(index: Int)
        case gamePoints
        case score
        case projected
        case chance
        case now
        case pregame
        case finalResult
    }

    nonisolated struct ColumnSpec: Equatable, Sendable {
        let role: ColumnRole
        let header: String
    }

    nonisolated enum RowRole: Equatable, Sendable {
        case away
        case home
        case draw
    }

    nonisolated struct CompetitorRow: Equatable, Sendable {
        let role: RowRole
        let fullName: String
        let opponentFullName: String
        let shortName: String
        let logoURL: String?
        let record: String?
        /// 1-to-1 aligned with `Model.columns`. Missing values are empty string `""`.
        let cells: [String]
        let rawProbability: Double?
        /// `true` ticks the winner (`✓`) in `Final`, `false` dims the loser, `nil` is neutral.
        let won: Bool?
        /// Per-column emphasis flags for set scores (e.g. won/current tennis set).
        var emphasizedColumns: Set<Int> = []
        /// Optional per-column tiebreak superscripts (e.g. `7` with superscript `"7"` / `6` with `"4"`).
        var cellSuperscripts: [Int: String] = [:]
        var abbreviation: String? = nil
        var opponentAbbreviation: String? = nil
    }

    nonisolated struct TennisSetColumn: Equatable, Sendable {
        let header: String
        let awayValue: String
        let homeValue: String
        var awayTiebreak: String? = nil
        var homeTiebreak: String? = nil
        let awayEmphasized: Bool
        let homeEmphasized: Bool

        var hasTiebreakSuperscript: Bool {
            awayTiebreak != nil || homeTiebreak != nil
        }
    }

    nonisolated struct TennisScoreFirstModel: Equatable, Sendable {
        let setColumns: [TennisSetColumn]
        let pointsColumn: (away: String, home: String)?
        var pointsHeader: String = "Pts"
        var isTiebreakPoints: Bool = false
        let pregameHeader: String?
        let nowHeader: String

        static func == (lhs: TennisScoreFirstModel, rhs: TennisScoreFirstModel) -> Bool {
            lhs.setColumns == rhs.setColumns
                && lhs.pointsColumn?.away == rhs.pointsColumn?.away
                && lhs.pointsColumn?.home == rhs.pointsColumn?.home
                && lhs.pointsHeader == rhs.pointsHeader
                && lhs.isTiebreakPoints == rhs.isTiebreakPoints
                && lhs.pregameHeader == rhs.pregameHeader
                && lhs.nowHeader == rhs.nowHeader
        }
    }

    nonisolated enum BottomBar: Equatable, Sendable {
        case twoWay(awayShare: Double, homeShare: Double, pregameAwayMarker: Double?)
        case threeWay(homeShare: Double, drawShare: Double, awayShare: Double)
    }

    // MARK: - Compatibility Header Projections (for existing unit tests)

    nonisolated struct PregameColumnHeaders: Equatable, Sendable {
        let projected: String?
        let chance: String
    }

    nonisolated struct LiveColumnHeaders: Equatable, Sendable {
        let score: String?
        var projected: String? = nil
        let pregame: String?
        let now: String

        var hasAny: Bool {
            score != nil || projected != nil || pregame != nil || !now.isEmpty
        }
    }

    nonisolated struct LivePregameSummary: Equatable, Sendable {
        enum SegmentInk: Equatable, Sendable {
            case quietLead
            case quiet
            case awayTeam
            case homeTeam
            case drawOutcome
        }

        struct Segment: Equatable, Sendable {
            let text: String
            let ink: SegmentInk
        }

        let leadWord: String
        let bodyText: String
        var segments: [Segment]

        init(leadWord: String, bodyText: String, segments: [Segment]? = nil) {
            self.leadWord = leadWord
            self.bodyText = bodyText
            self.segments = segments ?? [
                Segment(text: leadWord, ink: .quietLead),
                Segment(text: "  \(bodyText)", ink: .quiet),
            ]
        }

        var fullText: String {
            "\(leadWord)  \(bodyText)"
        }
    }

    nonisolated struct FinalColumnHeaders: Equatable, Sendable {
        let pregame: String?
        let finalLabel: String
    }

    nonisolated struct TeamRowModel: Equatable, Sendable {
        let fullName: String
        let opponentFullName: String
        let shortName: String
        let logoURL: String?
        let record: String?
        let projectedText: String?
        let pregameProjectedNumberText: String?
        var liveProjectedNumberText: String? = nil
        let liveScore: Int?
        let pregameChanceText: String?
        let winChanceText: String
        let rawProbability: Double
        var won: Bool? = nil
        var finalResultText: String? = nil
        var secondarySublineText: String? = nil
        var abbreviation: String? = nil
        var opponentAbbreviation: String? = nil
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
        let columns: [ColumnSpec]
        var rows: [CompetitorRow]
        let bottomBar: BottomBar?
        let pregameColumnHeaders: PregameColumnHeaders?
        let liveColumnHeaders: LiveColumnHeaders?
        var finalColumnHeaders: FinalColumnHeaders? = nil
        var tennisScoreFirst: TennisScoreFirstModel? = nil
        var away: TeamRowModel
        var home: TeamRowModel
        let pregameAwayMarker: Double?
        let livePregameSummary: LivePregameSummary?
        let showsEkg: Bool
        let sourceMark: SourceMark?
        let confidenceTier: String?

        init(
            eventId: Int,
            sportKey: String,
            kind: Kind,
            plainMetaText: String?,
            commenceTime: String?,
            startIsTbd: Bool?,
            broadcast: String?,
            eventStatus: String?,
            liveBadgeText: String?,
            leagueLabel: String?,
            columns: [ColumnSpec],
            rows: [CompetitorRow],
            bottomBar: BottomBar?,
            pregameColumnHeaders: PregameColumnHeaders?,
            liveColumnHeaders: LiveColumnHeaders?,
            finalColumnHeaders: FinalColumnHeaders?,
            tennisScoreFirst: TennisScoreFirstModel? = nil,
            away: TeamRowModel,
            home: TeamRowModel,
            pregameAwayMarker: Double?,
            livePregameSummary: LivePregameSummary?,
            showsEkg: Bool,
            sourceMark: SourceMark?,
            confidenceTier: String?
        ) {
            self.eventId = eventId
            self.sportKey = sportKey
            self.kind = kind
            self.plainMetaText = plainMetaText
            self.commenceTime = commenceTime
            self.startIsTbd = startIsTbd
            self.broadcast = broadcast
            self.eventStatus = eventStatus
            self.liveBadgeText = liveBadgeText
            self.leagueLabel = leagueLabel
            self.columns = columns.enumerated().map { idx, col in
                let hasAnyRowValue = rows.contains { row in
                    let hasCellText = idx < row.cells.count && !row.cells[idx].isEmpty
                    let hasWinnerTick = col.role == .finalResult && row.won == true
                    return hasCellText || hasWinnerTick
                }
                return hasAnyRowValue ? col : ColumnSpec(role: col.role, header: "")
            }
            self.rows = rows
            self.bottomBar = bottomBar
            self.pregameColumnHeaders = pregameColumnHeaders
            self.liveColumnHeaders = liveColumnHeaders
            self.finalColumnHeaders = finalColumnHeaders
            self.tennisScoreFirst = tennisScoreFirst
            self.away = away
            self.home = home
            self.pregameAwayMarker = pregameAwayMarker
            self.livePregameSummary = livePregameSummary
            self.showsEkg = showsEkg
            self.sourceMark = sourceMark
            self.confidenceTier = confidenceTier
        }

        var showsBottomBar: Bool {
            bottomBar != nil
        }

        var stacksRecordUnderName: Bool {
            away.record != nil || home.record != nil
        }

        var showsRowDivider: Bool {
            true
        }
    }

    // MARK: - Sport Classification Helpers

    nonisolated static func isSoccerSport(_ sport: String?) -> Bool {
        guard let s = sport?.lowercased(), !s.isEmpty else { return false }
        return s == "soccer" || s.hasPrefix("soccer_")
    }

    nonisolated static func isMMASport(_ sport: String?) -> Bool {
        guard let s = sport?.lowercased(), !s.isEmpty else { return false }
        return s == "mma" || s.hasPrefix("mma_")
    }

    nonisolated static func isBoxingSport(_ sport: String?) -> Bool {
        guard let s = sport?.lowercased(), !s.isEmpty else { return false }
        return s == "boxing" || s.hasPrefix("boxing_")
    }

    nonisolated static func isTennisSport(_ sport: String?) -> Bool {
        guard let s = sport?.lowercased(), !s.isEmpty else { return false }
        return s == "tennis" || s.hasPrefix("tennis_")
    }

    nonisolated static func isNCAAFSport(_ sport: String?) -> Bool {
        guard let s = sport?.lowercased(), !s.isEmpty else { return false }
        return s == "americanfootball_ncaaf" || s == "americanfootball_ncaaf_fcs"
    }

    nonisolated static func ncaafLeagueLabel(for sport: String?) -> String {
        sport?.lowercased() == "americanfootball_ncaaf_fcs" ? "NCAAF FCS" : "NCAAF"
    }

    nonisolated static func isNCAABSport(_ sport: String?) -> Bool {
        guard let s = sport?.lowercased(), !s.isEmpty else { return false }
        return s == "basketball_ncaab" || s == "basketball_wncaab"
    }

    nonisolated static func ncaabLeagueLabel(for sport: String?) -> String {
        sport?.lowercased() == "basketball_wncaab" ? "WNCAAB" : "NCAAB"
    }

    nonisolated static func carriesProjectedScoreColumn(sport: String?) -> Bool {
        if isTennisSport(sport) || isMMASport(sport) || isBoxingSport(sport) {
            return false
        }
        let vocab = SportVocab.forSport(sport)
        return vocab.scoreboardCountsTheUnit && !vocab.unit.isEmpty
    }

    nonisolated static func leagueDisplayLabel(for event: EventDetail) -> String {
        let lower = (event.sport ?? "").lowercased()
        if lower == "americanfootball_nfl" { return "NFL" }
        if lower == "basketball_nba" { return "NBA" }
        if isNCAAFSport(lower) { return ncaafLeagueLabel(for: lower) }
        if isNCAABSport(lower) { return ncaabLeagueLabel(for: lower) }
        if lower == "baseball_mlb" { return "MLB" }
        if lower == "icehockey_nhl" { return "NHL" }
        if isSoccerSport(lower) { return soccerCompetitionName(for: event) }
        if isTennisSport(lower) { return tennisTourLabel(for: event) }
        if isMMASport(lower) {
            if lower.contains("ufc") { return "UFC" }
            if let served = trimmedNonEmpty(event.sportName) { return served }
            return "MMA"
        }
        if isBoxingSport(lower) { return "Boxing" }
        if let served = trimmedNonEmpty(event.sportName) { return served }
        let fallback = sportDisplayName(for: event.sport)
        return fallback.isEmpty ? "Matchup" : fallback
    }

    // MARK: - Non-Optional Kind & Resolver (Zero `nil` Returns)

    nonisolated static func phase(for event: EventDetail, now: Date = Date()) -> Phase {
        let commenceDate = event.commenceTime?.asDate
        if EventState.isFinished(event.status)
            || EventState.showsVenueSettledVerdict(
                event.status,
                venueSettled: event.venueSettled,
                commenceTime: commenceDate,
                now: now
            )
            || EventState.showsVenueClosedNoWinner(
                event.status,
                venueSettled: event.venueSettled,
                venueClosedNoWinner: event.venueClosedNoWinner,
                commenceTime: commenceDate,
                now: now
            ) {
            return .after
        }
        if event.status == "live"
            || EventState.isSuspendedAndStarted(
                event.status,
                commenceTime: commenceDate,
                now: now
            ) {
            return .during
        }
        return .before
    }

    nonisolated static func kind(
        for event: EventDetail,
        gameMarkets: GameMarketsResponse? = nil,
        now: Date = Date()
    ) -> Kind {
        let p = phase(for: event, now: now)
        let lower = (event.sport ?? "").lowercased()
        if lower == "americanfootball_nfl" {
            switch p {
            case .before: return .nflBeforeGame
            case .during: return .nflDuringGame
            case .after: return .nflAfterGame
            }
        }
        if lower == "basketball_nba" {
            switch p {
            case .before: return .nbaBeforeGame
            case .during: return .nbaDuringGame
            case .after: return .nbaAfterGame
            }
        }
        if isNCAAFSport(lower) {
            switch p {
            case .before: return .ncaafBeforeGame
            case .during: return .ncaafDuringGame
            case .after: return .ncaafAfterGame
            }
        }
        if isNCAABSport(lower) {
            switch p {
            case .before: return .ncaabBeforeGame
            case .during: return .ncaabDuringGame
            case .after: return .ncaabAfterGame
            }
        }
        if isSoccerSport(lower) {
            switch p {
            case .before: return .soccerBeforeGame
            case .during: return .soccerDuringGame
            case .after: return .soccerAfterGame
            }
        }
        if lower == "icehockey_nhl" {
            switch p {
            case .before: return .nhlBeforeGame
            case .during: return .nhlDuringGame
            case .after: return .nhlAfterGame
            }
        }
        if lower == "baseball_mlb" {
            switch p {
            case .before: return .mlbBeforeGame
            case .during: return .mlbDuringGame
            case .after: return .mlbAfterGame
            }
        }
        if isMMASport(lower) {
            switch p {
            case .before: return .mmaBeforeGame
            case .during: return .mmaDuringGame
            case .after: return .mmaAfterGame
            }
        }
        if isTennisSport(lower) {
            switch p {
            case .before: return .tennisBeforeGame
            case .during: return .tennisDuringGame
            case .after: return .tennisAfterGame
            }
        }
        switch p {
        case .before: return .otherBeforeGame
        case .during: return .otherDuringGame
        case .after: return .otherAfterGame
        }
    }

    nonisolated static func applies(
        to event: EventDetail,
        gameMarkets: GameMarketsResponse? = nil,
        now: Date = Date()
    ) -> Bool {
        true
    }

    /// Resolves the single unified view-value model for every sport and state.
    /// Never returns `nil`.
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
    ) -> Model {
        let resolvedKind = kind(for: event, gameMarkets: gameMarkets, now: now)
        let resolvedPhase = resolvedKind.phase
        let sportKey = event.sport ?? "unknown"
        let league = leagueDisplayLabel(for: event)
        let shortNames = TeamShortName.shortPair(
            away: awayFullName,
            home: homeFullName,
            sportKey: event.sport
        )
        let awayLogo = event.awayTeamData?.logoLarge ?? event.awayTeamData?.logoSmall
        let homeLogo = event.homeTeamData?.logoLarge ?? event.homeTeamData?.logoSmall

        var model: Model
        switch resolvedPhase {
        case .before:
            model = resolveBefore(
                kind: resolvedKind,
                event: event,
                sportKey: sportKey,
                league: league,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                awayLogo: awayLogo,
                homeLogo: homeLogo,
                hasScore: hasScore,
                numberStreams: numberStreams,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                gameMarkets: gameMarkets,
                now: now
            )
        case .during:
            model = resolveDuring(
                kind: resolvedKind,
                event: event,
                sportKey: sportKey,
                league: league,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                awayLogo: awayLogo,
                homeLogo: homeLogo,
                liveStatusText: liveStatusText,
                hasScore: hasScore,
                ladderHome: ladderHome,
                ladderAway: ladderAway,
                gameMarkets: gameMarkets,
                now: now
            )
        case .after:
            model = resolveAfter(
                kind: resolvedKind,
                event: event,
                sportKey: sportKey,
                league: league,
                awayFullName: awayFullName,
                homeFullName: homeFullName,
                shortNames: shortNames,
                awayLogo: awayLogo,
                homeLogo: homeLogo,
                hasScore: hasScore,
                gameMarkets: gameMarkets,
                now: now
            )
        }
        let awayAbbr = event.awayTeamData?.abbreviation
        let homeAbbr = event.homeTeamData?.abbreviation
        model.away.abbreviation = awayAbbr
        model.away.opponentAbbreviation = homeAbbr
        model.home.abbreviation = homeAbbr
        model.home.opponentAbbreviation = awayAbbr
        model.rows = model.rows.map { row in
            var copy = row
            switch row.role {
            case .away:
                copy.abbreviation = awayAbbr
                copy.opponentAbbreviation = homeAbbr
            case .home:
                copy.abbreviation = homeAbbr
                copy.opponentAbbreviation = awayAbbr
            case .draw:
                break
            }
            return copy
        }
        return model
    }

    // MARK: - Phase 1: `before` (`Proj. · Chance`)

    @inline(never)
    nonisolated private static func resolveBefore(
        kind: Kind,
        event: EventDetail,
        sportKey: String,
        league: String,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        awayLogo: String?,
        homeLogo: String?,
        hasScore: Bool,
        numberStreams: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        gameMarkets: GameMarketsResponse?,
        now: Date
    ) -> Model {
        let lowerStatus = (event.status ?? "").lowercased()
        let isPostponed = lowerStatus == "postponed"
        let isCanceled = lowerStatus == "canceled" || lowerStatus == "cancelled"
        let canGrade = !isPostponed && !isCanceled && EventState.canStillBeGraded(
            event.status,
            commenceTime: event.commenceTime?.asDate,
            now: now
        )

        let meta: String = {
            if isPostponed { return "\(league) · Postponed" }
            if isCanceled { return "\(league) · Canceled" }
            return pregameMetaText(league: league, event: event, now: now)
        }()

        let hasProjCol = carriesProjectedScoreColumn(sport: event.sport)
        let columns: [ColumnSpec] = hasProjCol
            ? [.init(role: .projected, header: "Proj."), .init(role: .chance, header: "Chance")]
            : [.init(role: .chance, header: "Chance")]
        let pregameHeaders = PregameColumnHeaders(
            projected: hasProjCol ? "Proj." : nil,
            chance: "Chance"
        )

        let pregameProj = canGrade ? admittedPregameProjectedPair(
            event: event,
            hasScore: hasScore,
            ladderHome: ladderHome,
            ladderAway: ladderAway,
            now: now
        ) : nil
        let awayProjCell = pregameProj?.awayNumber ?? ""
        let homeProjCell = pregameProj?.homeNumber ?? ""

        let awayRecord = trimmedNonEmpty(event.awayTeamData?.record)
        let homeRecord = trimmedNonEmpty(event.homeTeamData?.record)

        // 3-way soccer before match
        if canGrade, isSoccerSport(event.sport),
           let shares = extractSoccerThreeWayOpenShares(event: event, gameMarkets: gameMarkets, now: now) {
            let formatted = soccerThreeWayChanceTexts(
                home: shares.home,
                draw: shares.draw,
                away: shares.away,
                numberStreams: numberStreams
            )
            let confidenceTier = Confidence.fromSources(
                sourceCount: event.winProbabilitySources?.count,
                hasMovement: event.openingOdds?.homeProbability
                    .map { abs(shares.home - $0) > 0.001 } ?? false
            )?.rawValue

            let homeRow = CompetitorRow(
                role: .home,
                fullName: homeFullName,
                opponentFullName: awayFullName,
                shortName: shortNames.home,
                logoURL: homeLogo,
                record: homeRecord,
                cells: hasProjCol ? [homeProjCell, formatted.home] : [formatted.home],
                rawProbability: shares.home,
                won: nil
            )
            let awayRow = CompetitorRow(
                role: .away,
                fullName: awayFullName,
                opponentFullName: homeFullName,
                shortName: shortNames.away,
                logoURL: awayLogo,
                record: awayRecord,
                cells: hasProjCol ? [awayProjCell, formatted.away] : [formatted.away],
                rawProbability: shares.away,
                won: nil
            )
            let drawRow = CompetitorRow(
                role: .draw,
                fullName: "Draw",
                opponentFullName: "",
                shortName: "Draw",
                logoURL: nil,
                record: nil,
                cells: hasProjCol ? ["", formatted.draw] : [formatted.draw],
                rawProbability: shares.draw,
                won: nil
            )

            return Model(
                eventId: event.id,
                sportKey: sportKey,
                kind: kind,
                plainMetaText: meta,
                commenceTime: isPostponed || isCanceled ? nil : event.commenceTime,
                startIsTbd: event.startIsTbd,
                broadcast: trimmedNonEmpty(event.espn?.broadcast),
                eventStatus: event.status,
                liveBadgeText: nil,
                leagueLabel: league,
                columns: columns,
                rows: [homeRow, awayRow, drawRow],
                bottomBar: .threeWay(homeShare: shares.home, drawShare: shares.draw, awayShare: shares.away),
                pregameColumnHeaders: pregameHeaders,
                liveColumnHeaders: nil,
                finalColumnHeaders: nil,
                away: makeCompatTeamRow(awayRow, projNumber: pregameProj?.awayNumber, liveScore: nil, pregameChance: nil, chance: formatted.away, finalText: nil),
                home: makeCompatTeamRow(homeRow, projNumber: pregameProj?.homeNumber, liveScore: nil, pregameChance: nil, chance: formatted.home, finalText: nil),
                pregameAwayMarker: nil,
                livePregameSummary: nil,
                showsEkg: true,
                sourceMark: event.sourceMark,
                confidenceTier: confidenceTier
            )
        }

        // 2-row before game (including missing odds, opening-only withheld, or draw-withheld lone home chance)
        var awayChance = ""
        var homeChance = ""
        var awayProb = 0.0
        var homeProb = 0.0
        var bar: BottomBar? = nil
        var confidenceTier: String? = nil

        if canGrade, let odds = event.currentOdds {
            let shown = OpeningLineHero.resolve(odds, for: event)
            if !shown.isOpeningLine,
               let pair = DrawPricedWinner.printablePair(
                   away: shown.awayProbability,
                   home: shown.homeProbability,
                   sport: event.sport
               ) {
                homeProb = pair.home
                if let away = pair.away {
                    awayProb = away
                    let texts = nflPregameChanceTexts(
                        shown: shown,
                        away: away,
                        home: pair.home,
                        numberStreams: numberStreams
                    )
                    awayChance = texts.away
                    homeChance = texts.home
                    bar = .twoWay(awayShare: away, homeShare: pair.home, pregameAwayMarker: nil)
                } else {
                    // Draw-priced sport with only home win chance served (#5271):
                    // print home chance and leave away cell empty; never invent `1 - home`.
                    homeChance = numberStreams
                        ? EventHeadlineTenths10090.pair(home: pair.home, away: nil).home
                        : formatProbability(pair.home, renderedPercent: shown.homeRenderedPercent)
                }
                confidenceTier = Confidence.fromSources(
                    sourceCount: event.winProbabilitySources?.count,
                    hasMovement: event.openingOdds?.homeProbability
                        .map { abs(pair.home - $0) > 0.001 } ?? false
                )?.rawValue
            }
        }

        let awayRow = CompetitorRow(
            role: .away,
            fullName: awayFullName,
            opponentFullName: homeFullName,
            shortName: shortNames.away,
            logoURL: awayLogo,
            record: awayRecord,
            cells: hasProjCol ? [awayProjCell, awayChance] : [awayChance],
            rawProbability: awayChance.isEmpty ? nil : awayProb,
            won: nil
        )
        let homeRow = CompetitorRow(
            role: .home,
            fullName: homeFullName,
            opponentFullName: awayFullName,
            shortName: shortNames.home,
            logoURL: homeLogo,
            record: homeRecord,
            cells: hasProjCol ? [homeProjCell, homeChance] : [homeChance],
            rawProbability: homeChance.isEmpty ? nil : homeProb,
            won: nil
        )

        return Model(
            eventId: event.id,
            sportKey: sportKey,
            kind: kind,
            plainMetaText: meta,
            commenceTime: isPostponed || isCanceled ? nil : event.commenceTime,
            startIsTbd: event.startIsTbd,
            broadcast: trimmedNonEmpty(event.espn?.broadcast),
            eventStatus: event.status,
            liveBadgeText: nil,
            leagueLabel: league,
            columns: columns,
            rows: [awayRow, homeRow],
            bottomBar: bar,
            pregameColumnHeaders: pregameHeaders,
            liveColumnHeaders: nil,
            finalColumnHeaders: nil,
            away: makeCompatTeamRow(awayRow, projNumber: pregameProj?.awayNumber, liveScore: nil, pregameChance: nil, chance: awayChance, finalText: nil),
            home: makeCompatTeamRow(homeRow, projNumber: pregameProj?.homeNumber, liveScore: nil, pregameChance: nil, chance: homeChance, finalText: nil),
            pregameAwayMarker: nil,
            livePregameSummary: nil,
            showsEkg: canGrade && !homeChance.isEmpty,
            sourceMark: event.sourceMark,
            confidenceTier: confidenceTier
        )
    }

    // MARK: - Phase 2: `during` (`<Score slot> · Proj. · Now` + grey pregame line)

    @inline(never)
    nonisolated private static func resolveDuring(
        kind: Kind,
        event: EventDetail,
        sportKey: String,
        league: String,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        awayLogo: String?,
        homeLogo: String?,
        liveStatusText: String?,
        hasScore: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        gameMarkets: GameMarketsResponse?,
        now: Date
    ) -> Model {
        let isSuspendedStarted = event.status != "live" && EventState.isSuspendedAndStarted(
            event.status,
            commenceTime: event.commenceTime?.asDate,
            now: now
        )
        let isLive = event.status == "live" && !isSuspendedStarted

        let liveBadge: String? = {
            guard isLive else { return nil }
            if isTennisSport(event.sport) {
                return tennisLiveStatusBadge(event: event, liveStatusText: liveStatusText)
            }
            if isSoccerSport(event.sport) {
                let clock = trimmedNonEmpty(liveStatusText) ?? trimmedNonEmpty(event.espn?.gameClock)
                return clock.map { "LIVE · \($0)" } ?? "LIVE"
            }
            let periodStatus = trimmedNonEmpty(liveStatusText)
            return periodStatus.map { "LIVE · \($0)" } ?? "LIVE"
        }()

        let plainMeta: String? = isSuspendedStarted ? "\(league) · Suspended" : nil

        let isTennis = isTennisSport(event.sport)
        let isScoreless = isMMASport(event.sport) || isBoxingSport(event.sport)
        let hasProjCol = carriesProjectedScoreColumn(sport: event.sport)

        let liveProjNumbers = isLive ? admittedLiveProjectedNumberPair(
            event: event,
            hasScore: hasScore,
            ladderHome: ladderHome,
            ladderAway: ladderAway,
            now: now
        ) : nil
        let awayProjCell = liveProjNumbers?.away ?? ""
        let homeProjCell = liveProjNumbers?.home ?? ""

        // Tennis score-slot columns (`S1`, `S2`, … or `Sets` + optional `Pts` / `TB`)
        let tennisScoreSlot: TennisScoreSlotResult? = isTennis
            ? buildTennisScoreSlot(event: event, hasScore: hasScore, includePoints: isLive)
            : nil

        let columns: [ColumnSpec] = {
            if let tennisSlot = tennisScoreSlot {
                return tennisSlot.columns + [.init(role: .now, header: "Now")]
            }
            var cols: [ColumnSpec] = []
            if !isScoreless {
                cols.append(.init(role: .score, header: "Score"))
            }
            if hasProjCol {
                cols.append(.init(role: .projected, header: "Proj."))
            }
            cols.append(.init(role: .now, header: "Now"))
            return cols
        }()

        let compatLiveHeaders = LiveColumnHeaders(
            score: isTennis ? (tennisScoreSlot?.columns.first?.header ?? "Sets") : (isScoreless ? nil : "Score"),
            projected: hasProjCol ? "Proj." : nil,
            pregame: nil,
            now: "Now"
        )

        // 3-way soccer during match
        if isLive, isSoccerSport(event.sport) {
            let marketSnap = extractSoccerThreeWayMarketSnapshot(
                event: event,
                gameMarkets: gameMarkets,
                finished: false,
                now: now
            )
            let openShares: (home: Double, draw: Double, away: Double)? = {
                if let odds = event.currentOdds {
                    let s = EventAtlasSoccerCards11666.scaleThreeWayField(
                        home: odds.homeProbability,
                        draw: odds.drawProbability,
                        away: odds.awayProbability
                    )
                    if let h = s.home, let d = s.draw, let a = s.away { return (h, d, a) }
                }
                return marketSnap?.openShares
            }()

            if let shares = openShares {
                let formatted = soccerThreeWayChanceTexts(
                    home: shares.home,
                    draw: shares.draw,
                    away: shares.away,
                    numberStreams: true
                )
                let pregameShares = extractSoccerThreeWayPrematchShares(
                    event: event,
                    marketSnapshot: marketSnap
                )
                let summary = resolveSoccerLivePregameSummary(
                    event: event,
                    shortNames: shortNames,
                    pregameShares: pregameShares
                )
                let confidenceTier = Confidence.fromSources(
                    sourceCount: event.winProbabilitySources?.count,
                    hasMovement: event.openingOdds?.homeProbability
                        .map { abs(shares.home - $0) > 0.001 } ?? false
                )?.rawValue

                let homeScoreCell = (hasScore && event.homeScore != nil) ? "\(event.homeScore!)" : ""
                let awayScoreCell = (hasScore && event.awayScore != nil) ? "\(event.awayScore!)" : ""

                let homeRow = CompetitorRow(
                    role: .home,
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: homeLogo,
                    record: nil,
                    cells: [homeScoreCell, homeProjCell, formatted.home],
                    rawProbability: shares.home,
                    won: nil
                )
                let awayRow = CompetitorRow(
                    role: .away,
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: awayLogo,
                    record: nil,
                    cells: [awayScoreCell, awayProjCell, formatted.away],
                    rawProbability: shares.away,
                    won: nil
                )
                let drawRow = CompetitorRow(
                    role: .draw,
                    fullName: "Draw",
                    opponentFullName: "",
                    shortName: "Draw",
                    logoURL: nil,
                    record: nil,
                    cells: ["", "", formatted.draw],
                    rawProbability: shares.draw,
                    won: nil
                )

                return Model(
                    eventId: event.id,
                    sportKey: sportKey,
                    kind: kind,
                    plainMetaText: nil,
                    commenceTime: event.commenceTime,
                    startIsTbd: event.startIsTbd,
                    broadcast: trimmedNonEmpty(event.espn?.broadcast),
                    eventStatus: event.status,
                    liveBadgeText: liveBadge,
                    leagueLabel: league,
                    columns: columns,
                    rows: [homeRow, awayRow, drawRow],
                    bottomBar: .threeWay(homeShare: shares.home, drawShare: shares.draw, awayShare: shares.away),
                    pregameColumnHeaders: nil,
                    liveColumnHeaders: compatLiveHeaders,
                    finalColumnHeaders: nil,
                    away: makeCompatTeamRow(awayRow, projNumber: nil, liveProjNumber: liveProjNumbers?.away, liveScore: hasScore ? event.awayScore : nil, pregameChance: nil, chance: formatted.away, finalText: nil),
                    home: makeCompatTeamRow(homeRow, projNumber: nil, liveProjNumber: liveProjNumbers?.home, liveScore: hasScore ? event.homeScore : nil, pregameChance: nil, chance: formatted.home, finalText: nil),
                    pregameAwayMarker: nil,
                    livePregameSummary: summary,
                    showsEkg: true,
                    sourceMark: event.sourceMark,
                    confidenceTier: confidenceTier
                )
            }
        }

        // 2-row during game (all sports, including missing live odds or suspended-in-play)
        var awayNow = ""
        var homeNow = ""
        var awayProb = 0.0
        var homeProb = 0.0
        var pregameMarker: Double? = nil
        var bar: BottomBar? = nil
        var confidenceTier: String? = nil

        if isLive, let odds = event.currentOdds {
            let shown = OpeningLineHero.resolve(odds, for: event)
            if !shown.isOpeningLine,
               let pair = DrawPricedWinner.printablePair(
                   away: shown.awayProbability,
                   home: shown.homeProbability,
                   sport: event.sport
               ) {
                homeProb = pair.home
                if let away = pair.away {
                    awayProb = away
                    let tenths = EventHeadlineTenths10090.pair(home: pair.home, away: away)
                    awayNow = tenths.away ?? ""
                    homeNow = tenths.home
                    let strictPregame = PrematchReading.resolve(prematch: event.prematchOdds, opening: nil)
                    if let strictPregame, !strictPregame.awayIsComplement {
                        pregameMarker = strictPregame.awayProbability
                    }
                    bar = .twoWay(awayShare: away, homeShare: pair.home, pregameAwayMarker: pregameMarker)
                } else {
                    homeNow = EventHeadlineTenths10090.pair(home: pair.home, away: nil).home
                }
                confidenceTier = Confidence.fromSources(
                    sourceCount: event.winProbabilitySources?.count,
                    hasMovement: event.openingOdds?.homeProbability
                        .map { abs(pair.home - $0) > 0.001 } ?? false
                )?.rawValue
            }
        }

        let summary = isLive ? resolveLivePregameSummary(event: event, shortNames: shortNames) : nil

        let awayScoreCell = (!isScoreless && hasScore && event.awayScore != nil) ? "\(event.awayScore!)" : ""
        let homeScoreCell = (!isScoreless && hasScore && event.homeScore != nil) ? "\(event.homeScore!)" : ""

        let awayCells: [String]
        let homeCells: [String]
        let awayEmph: Set<Int>
        let homeEmph: Set<Int>
        let awaySuperscripts: [Int: String]
        let homeSuperscripts: [Int: String]

        if let tennisSlot = tennisScoreSlot {
            awayCells = tennisSlot.awayCells + [awayNow]
            homeCells = tennisSlot.homeCells + [homeNow]
            awayEmph = tennisSlot.awayEmph
            homeEmph = tennisSlot.homeEmph
            awaySuperscripts = tennisSlot.awaySuperscripts
            homeSuperscripts = tennisSlot.homeSuperscripts
        } else {
            var a: [String] = []
            var h: [String] = []
            if !isScoreless {
                a.append(awayScoreCell)
                h.append(homeScoreCell)
            }
            if hasProjCol {
                a.append(awayProjCell)
                h.append(homeProjCell)
            }
            a.append(awayNow)
            h.append(homeNow)
            awayCells = a
            homeCells = h
            awayEmph = []
            homeEmph = []
            awaySuperscripts = [:]
            homeSuperscripts = [:]
        }

        let awayRow = CompetitorRow(
            role: .away,
            fullName: awayFullName,
            opponentFullName: homeFullName,
            shortName: shortNames.away,
            logoURL: awayLogo,
            record: nil,
            cells: awayCells,
            rawProbability: awayNow.isEmpty ? nil : awayProb,
            won: nil,
            emphasizedColumns: awayEmph,
            cellSuperscripts: awaySuperscripts
        )
        let homeRow = CompetitorRow(
            role: .home,
            fullName: homeFullName,
            opponentFullName: awayFullName,
            shortName: shortNames.home,
            logoURL: homeLogo,
            record: nil,
            cells: homeCells,
            rawProbability: homeNow.isEmpty ? nil : homeProb,
            won: nil,
            emphasizedColumns: homeEmph,
            cellSuperscripts: homeSuperscripts
        )

        return Model(
            eventId: event.id,
            sportKey: sportKey,
            kind: kind,
            plainMetaText: plainMeta,
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            broadcast: trimmedNonEmpty(event.espn?.broadcast),
            eventStatus: event.status,
            liveBadgeText: liveBadge,
            leagueLabel: league,
            columns: columns,
            rows: [awayRow, homeRow],
            bottomBar: bar,
            pregameColumnHeaders: nil,
            liveColumnHeaders: compatLiveHeaders,
            finalColumnHeaders: nil,
            tennisScoreFirst: tennisScoreSlot?.scoreFirstModel,
            away: makeCompatTeamRow(awayRow, projNumber: nil, liveProjNumber: liveProjNumbers?.away, liveScore: hasScore ? event.awayScore : nil, pregameChance: nil, chance: awayNow, finalText: nil),
            home: makeCompatTeamRow(homeRow, projNumber: nil, liveProjNumber: liveProjNumbers?.home, liveScore: hasScore ? event.homeScore : nil, pregameChance: nil, chance: homeNow, finalText: nil),
            pregameAwayMarker: pregameMarker,
            livePregameSummary: summary,
            showsEkg: isLive && !homeNow.isEmpty,
            sourceMark: event.sourceMark,
            confidenceTier: confidenceTier
        )
    }

    // MARK: - Phase 3: `after` (`Pregame · Final`, winner ticked, no bar)

    @inline(never)
    nonisolated private static func resolveAfter(
        kind: Kind,
        event: EventDetail,
        sportKey: String,
        league: String,
        awayFullName: String,
        homeFullName: String,
        shortNames: (away: String, home: String),
        awayLogo: String?,
        homeLogo: String?,
        hasScore: Bool,
        gameMarkets: GameMarketsResponse?,
        now: Date
    ) -> Model {
        let commenceDate = event.commenceTime?.asDate
        let isFinished = EventState.isFinished(event.status)
        let isVenueClosedNoWinner = !isFinished && EventState.showsVenueClosedNoWinner(
            event.status,
            venueSettled: event.venueSettled,
            venueClosedNoWinner: event.venueClosedNoWinner,
            commenceTime: commenceDate,
            now: now
        )
        let isVenueSettledOnly = !isFinished && !isVenueClosedNoWinner && EventState.showsVenueSettledVerdict(
            event.status,
            venueSettled: event.venueSettled,
            commenceTime: commenceDate,
            now: now
        )

        let confidenceTier = Confidence.fromSources(
            sourceCount: event.winProbabilitySources?.count,
            hasMovement: false
        )?.rawValue

        // Strict pregame baseline (`prematch_odds` only — never `opening_odds`)
        let strictPregame = PrematchReading.resolve(prematch: event.prematchOdds, opening: nil)

        // 3-way soccer after match
        if isSoccerSport(event.sport), isFinished {
            let marketSnap = extractSoccerThreeWayMarketSnapshot(
                event: event,
                gameMarkets: gameMarkets,
                finished: true,
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

            let resolvedOutcome = EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult
            )
            let nonRegulationFinish: Bool = {
                guard let fp = event.finalScorePeriod?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased() else {
                    return false
                }
                return fp == "extra_time" || fp == "penalties" || fp == "aet" || fp == "pen"
            }()
            let winnerRole: EventAtlasSoccerCards11666.ThreeWayRole? = {
                if let confirmed = marketSnap?.confirmedWinner { return confirmed }
                if nonRegulationFinish && pregameTexts != nil { return nil }
                switch resolvedOutcome {
                case .home: return .home
                case .away: return .away
                case .draw: return .draw
                case .undecided: return nil
                }
            }()

            if pregameTexts != nil || winnerRole == .draw || marketSnap != nil {
                let columns: [ColumnSpec] = [
                    .init(role: .pregame, header: "Pregame"),
                    .init(role: .finalResult, header: "Final"),
                ]
                let finalHeaders = FinalColumnHeaders(pregame: "Pregame", finalLabel: "Final")
                let meta = afterMetaText(league: league, event: event)

                let homeScoreText = event.homeScore.map(String.init) ?? (winnerRole == .home ? "Won" : (winnerRole == .away ? "Lost" : ""))
                let awayScoreText = event.awayScore.map(String.init) ?? (winnerRole == .away ? "Won" : (winnerRole == .home ? "Lost" : ""))
                let drawFinalText: String = {
                    guard let winnerRole else { return "" }
                    // On a draw, `won = true` renders the green `✓` in the Final column
                    // without repeating the row's own `"Draw"` label twice.
                    return winnerRole == .draw ? "" : "\u{2014}"
                }()

                let homeWon: Bool? = winnerRole == nil ? nil : (winnerRole == .home ? true : (winnerRole == .away ? false : nil))
                let awayWon: Bool? = winnerRole == nil ? nil : (winnerRole == .away ? true : (winnerRole == .home ? false : nil))
                let drawWon: Bool? = winnerRole == nil ? nil : (winnerRole == .draw ? true : false)

                let homePre = pregameTexts?.home ?? ""
                let awayPre = pregameTexts?.away ?? ""
                let drawPre = pregameTexts?.draw ?? ""

                let homeRow = CompetitorRow(
                    role: .home,
                    fullName: homeFullName,
                    opponentFullName: awayFullName,
                    shortName: shortNames.home,
                    logoURL: homeLogo,
                    record: nil,
                    cells: [homePre, homeScoreText],
                    rawProbability: pregameShares?.home,
                    won: homeWon
                )
                let awayRow = CompetitorRow(
                    role: .away,
                    fullName: awayFullName,
                    opponentFullName: homeFullName,
                    shortName: shortNames.away,
                    logoURL: awayLogo,
                    record: nil,
                    cells: [awayPre, awayScoreText],
                    rawProbability: pregameShares?.away,
                    won: awayWon
                )
                let drawRow = CompetitorRow(
                    role: .draw,
                    fullName: "Draw",
                    opponentFullName: "",
                    shortName: "Draw",
                    logoURL: nil,
                    record: nil,
                    cells: [drawPre, drawFinalText],
                    rawProbability: pregameShares?.draw,
                    won: drawWon
                )

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
                    columns: columns,
                    rows: [homeRow, awayRow, drawRow],
                    bottomBar: nil,
                    pregameColumnHeaders: nil,
                    liveColumnHeaders: nil,
                    finalColumnHeaders: finalHeaders,
                    away: makeCompatTeamRow(awayRow, projNumber: nil, liveScore: event.awayScore, pregameChance: awayPre.isEmpty ? nil : awayPre, chance: "", finalText: awayScoreText),
                    home: makeCompatTeamRow(homeRow, projNumber: nil, liveScore: event.homeScore, pregameChance: homePre.isEmpty ? nil : homePre, chance: "", finalText: homeScoreText),
                    pregameAwayMarker: nil,
                    livePregameSummary: nil,
                    showsEkg: false,
                    sourceMark: event.sourceMark,
                    confidenceTier: confidenceTier
                )
            }
        }

        // 2-row `after` (including finished tennis with sets, MMA, missing scores, venue-settled, venue-closed)
        var awayPre = ""
        var homePre = ""
        if let strictPregame,
           let pair = DrawPricedWinner.printablePair(
               away: strictPregame.awayProbability,
               home: strictPregame.homeProbability,
               sport: event.sport
           ) {
            if pair.away != nil, let texts = nbaPregameTexts(strictPregame) {
                awayPre = texts.away
                homePre = texts.home
            } else {
                let homePct = strictPregame.percents.count > 1 ? strictPregame.percents[1] : nil
                homePre = formatProbability(pair.home, renderedPercent: homePct)
            }
        }

        let outcome: EventOutcome = isFinished
            ? EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult
            )
            : .undecided

        let isScoreless = isMMASport(event.sport) || isBoxingSport(event.sport)
        let bothScoresPresent = isFinished && !isScoreless && event.awayScore != nil && event.homeScore != nil

        let awayWon: Bool?
        let homeWon: Bool?
        let awayFinalText: String
        let homeFinalText: String
        var extraMetaOutcome: String? = nil

        if isVenueClosedNoWinner {
            awayWon = nil
            homeWon = nil
            awayFinalText = ""
            homeFinalText = ""
        } else if isVenueSettledOnly {
            awayWon = nil
            homeWon = nil
            awayFinalText = ""
            homeFinalText = ""
        } else if bothScoresPresent, let aScore = event.awayScore, let hScore = event.homeScore {
            awayFinalText = "\(aScore)"
            homeFinalText = "\(hScore)"
            switch outcome {
            case .away:
                awayWon = true
                homeWon = false
            case .home:
                awayWon = false
                homeWon = true
            case .draw:
                awayWon = nil
                homeWon = nil
                extraMetaOutcome = "Draw"
            case .undecided:
                awayWon = nil
                homeWon = nil
            }
        } else {
            switch outcome {
            case .away:
                awayWon = true
                homeWon = false
                awayFinalText = "Won"
                homeFinalText = "Lost"
            case .home:
                awayWon = false
                homeWon = true
                awayFinalText = "Lost"
                homeFinalText = "Won"
            case .draw:
                awayWon = nil
                homeWon = nil
                awayFinalText = ""
                homeFinalText = ""
                extraMetaOutcome = "Draw"
            case .undecided:
                awayWon = nil
                homeWon = nil
                awayFinalText = ""
                homeFinalText = ""
            }
        }

        let meta: String = {
            if isVenueClosedNoWinner {
                return "\(league) · Ended · no winner"
            }
            if isVenueSettledOnly {
                if let rawVerdict = trimmedNonEmpty(event.venueSettledResult) {
                    let lower = rawVerdict.lowercased()
                    if lower == "settled by venue" || lower == "ended by venue" || lower == "settled" {
                        return "\(league) · Ended · no result reported"
                    }
                    let safeVerdict = sanitizeBannedWords(rawVerdict)
                    return "\(league) · \(safeVerdict)"
                }
                return "\(league) · Ended · no result reported"
            }
            let base = afterMetaText(league: league, event: event)
            if let extraMetaOutcome {
                return "\(base) · \(extraMetaOutcome)"
            }
            return base
        }()

        // Finished tennis set columns (if period scores or linescore sets exist)
        let tennisFinishedSets: TennisScoreSlotResult? = {
            guard isTennisSport(event.sport), isFinished else { return nil }
            let slot = buildTennisScoreSlot(event: event, hasScore: false, includePoints: false)
            return slot.columns.isEmpty ? nil : slot
        }()

        let columns: [ColumnSpec] = (tennisFinishedSets?.columns ?? []) + [
            .init(role: .pregame, header: "Pregame"),
            .init(role: .finalResult, header: "Final"),
        ]
        let finalHeaders = FinalColumnHeaders(pregame: "Pregame", finalLabel: "Final")

        let awayCells = (tennisFinishedSets?.awayCells ?? []) + [awayPre, awayFinalText]
        let homeCells = (tennisFinishedSets?.homeCells ?? []) + [homePre, homeFinalText]

        let awayRow = CompetitorRow(
            role: .away,
            fullName: awayFullName,
            opponentFullName: homeFullName,
            shortName: shortNames.away,
            logoURL: awayLogo,
            record: nil,
            cells: awayCells,
            rawProbability: strictPregame?.awayProbability,
            won: awayWon,
            emphasizedColumns: tennisFinishedSets?.awayEmph ?? [],
            cellSuperscripts: tennisFinishedSets?.awaySuperscripts ?? [:]
        )
        let homeRow = CompetitorRow(
            role: .home,
            fullName: homeFullName,
            opponentFullName: awayFullName,
            shortName: shortNames.home,
            logoURL: homeLogo,
            record: nil,
            cells: homeCells,
            rawProbability: strictPregame?.homeProbability,
            won: homeWon,
            emphasizedColumns: tennisFinishedSets?.homeEmph ?? [],
            cellSuperscripts: tennisFinishedSets?.homeSuperscripts ?? [:]
        )

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
            columns: columns,
            rows: [awayRow, homeRow],
            bottomBar: nil,
            pregameColumnHeaders: nil,
            liveColumnHeaders: nil,
            finalColumnHeaders: finalHeaders,
            away: makeCompatTeamRow(awayRow, projNumber: nil, liveScore: event.awayScore, pregameChance: awayPre.isEmpty ? nil : awayPre, chance: "", finalText: awayFinalText.isEmpty ? nil : awayFinalText),
            home: makeCompatTeamRow(homeRow, projNumber: nil, liveScore: event.homeScore, pregameChance: homePre.isEmpty ? nil : homePre, chance: "", finalText: homeFinalText.isEmpty ? nil : homeFinalText),
            pregameAwayMarker: nil,
            livePregameSummary: nil,
            showsEkg: false,
            sourceMark: event.sourceMark,
            confidenceTier: confidenceTier
        )
    }

    nonisolated private static func makeCompatTeamRow(
        _ row: CompetitorRow,
        projNumber: String?,
        liveProjNumber: String? = nil,
        liveScore: Int?,
        pregameChance: String?,
        chance: String,
        finalText: String?
    ) -> TeamRowModel {
        TeamRowModel(
            fullName: row.fullName,
            opponentFullName: row.opponentFullName,
            shortName: row.shortName,
            logoURL: row.logoURL,
            record: row.record,
            projectedText: nil,
            pregameProjectedNumberText: projNumber,
            liveProjectedNumberText: liveProjNumber,
            liveScore: liveScore,
            pregameChanceText: pregameChance,
            winChanceText: chance,
            rawProbability: row.rawProbability ?? 0,
            won: row.won,
            finalResultText: finalText,
            secondarySublineText: nil
        )
    }

    nonisolated private static func sanitizeBannedWords(_ raw: String) -> String {
        raw
            .replacingOccurrences(of: "Settled", with: "Ended", options: .caseInsensitive)
            .replacingOccurrences(of: "opening", with: "initial", options: .caseInsensitive)
            .replacingOccurrences(of: "opened", with: "started", options: .caseInsensitive)
            .replacingOccurrences(of: "stale", with: "paused", options: .caseInsensitive)
    }

    // MARK: - Three-Way Soccer Extraction & Formatting

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

    nonisolated static func soccerThreeWayChanceTexts(
        home: Double,
        draw: Double,
        away: Double,
        numberStreams: Bool
    ) -> (home: String, draw: String, away: String) {
        let total = home + draw + away
        guard total.isFinite, total > 0 else {
            return ("", "", "")
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

    // MARK: - Formatting & Projection Helpers

    nonisolated static func nflPregameChanceTexts(
        shown: OpeningLineHero,
        away: Double,
        home: Double,
        numberStreams: Bool
    ) -> (away: String, home: String) {
        if numberStreams {
            let tenths = EventHeadlineTenths10090.pair(home: home, away: away)
            return (away: tenths.away ?? "", home: tenths.home)
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
           EventDetailView.showsBroadcast(
               status: event.status,
               commenceTime: event.commenceTime?.asDate,
               now: now
           ) {
            parts.append(broadcast)
        }
        return parts.joined(separator: " · ")
    }

    nonisolated static func afterMetaText(league: String, event: EventDetail) -> String {
        let lower = (event.sport ?? "").lowercased()
        if lower == "baseball_mlb" {
            let awayInnings = event.boxScoreData?.awayPeriodScores?.compactMap { $0 }.count ?? 0
            let homeInnings = event.boxScoreData?.homePeriodScores?.compactMap { $0 }.count ?? 0
            let playedInnings = max(awayInnings, homeInnings)
            if playedInnings >= 5 {
                return "MLB · Final · \(playedInnings) Innings"
            }
        }
        var parts: [String] = [league]
        if let period = trimmedNonEmpty(event.finalScorePeriod) {
            let lowerPeriod = period.lowercased()
            let normalizedPeriod = PeriodLabel.normalize(period, sport: event.sport)
            if lowerPeriod == "aet" || lowerPeriod == "extra_time" {
                parts.append("Final (AET)")
            } else if lowerPeriod == "pen" || lowerPeriod == "penalties" {
                parts.append("Final (Pen.)")
            } else if normalizedPeriod.hasPrefix("OT") || lowerPeriod == "so" || lowerPeriod == "shootout" {
                parts.append("Final/OT")
            } else {
                parts.append("Final")
            }
        } else {
            parts.append("Final")
        }
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

    nonisolated static func nbaPregameTexts(
        _ pregame: PrematchReading?
    ) -> (away: String, home: String)? {
        guard let pregame else { return nil }
        let awayPct = pregame.percents.count > 0 ? pregame.percents[0] : nil
        let homePct = pregame.percents.count > 1 ? pregame.percents[1] : nil
        return (
            away: formatProbability(pregame.awayProbability, renderedPercent: awayPct),
            home: formatProbability(pregame.homeProbability, renderedPercent: homePct)
        )
    }

    /// Football and basketball projections print as whole numbers (`24`, `28`);
    /// baseball, hockey, and soccer keep one decimal (`4.5`, `3.2`, `1.8`).
    nonisolated static func formatLiveProjectedColumnNumber(
        _ value: Double,
        sportKey: String?
    ) -> String {
        let lower = (sportKey ?? "").lowercased()
        if lower.hasPrefix("americanfootball") || lower.hasPrefix("basketball") {
            return "\(Int(value.rounded()))"
        }
        return String(format: "%.1f", value)
    }

    nonisolated static func admittedPregameProjectedPair(
        event: EventDetail,
        hasScore: Bool,
        ladderHome: Double?,
        ladderAway: Double?,
        now: Date = Date()
    ) -> (awayNumber: String, homeNumber: String)? {
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
            awayNumber: formatLiveProjectedColumnNumber(pair.away, sportKey: event.sport),
            homeNumber: formatLiveProjectedColumnNumber(pair.home, sportKey: event.sport)
        )
    }

    nonisolated static func admittedLiveProjectedNumberPair(
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
            away: formatLiveProjectedColumnNumber(safeAway, sportKey: event.sport),
            home: formatLiveProjectedColumnNumber(safeHome, sportKey: event.sport)
        )
    }

    nonisolated static func qualifiedLivePregameProjectionPair(
        event: EventDetail
    ) -> (away: Int, home: Int)? {
        qualifiedPregameProjectionPair(
            projection: event.pregameProjection,
            sport: event.sport,
            status: event.status,
            commenceTime: event.commenceTime
        )
    }

    nonisolated static func qualifiedPregameProjectionPair(
        projection: PregameProjection?,
        sport: String?,
        status: String?,
        commenceTime: String?
    ) -> (away: Int, home: Int)? {
        guard status == "live",
              let p = projection,
              p.kind == "last_before_scheduled_start",
              p.boundary == "scheduled_start",
              p.source == "sportsbooks",
              p.basis == "consensus_spread_total",
              let format = LiveProjectedFinalAdmission2920.format(forSport: sport),
              p.unit == format.unit.rawValue,
              p.period == format.period.rawValue,
              let books = p.bookmakerCount.flatMap({ Int(exactly: $0) }), books >= 1,
              let earliest = p.earliestCapturedAt?.asDate,
              let latest = p.latestCapturedAt?.asDate,
              let boundary = p.boundaryAt?.asDate,
              earliest <= latest, latest < boundary,
              let home = p.projectedHomeScore, let away = p.projectedAwayScore,
              home.isFinite, away.isFinite, home > 0, away > 0
        else { return nil }

        if let rowStart = commenceTime?.asDate, boundary != rowStart {
            return nil
        }

        let vocab = SportVocab.forSport(sport)
        guard vocab.sportsbookSpreadIsAMargin,
              let roundedHome = Int(exactly: home.rounded()),
              let roundedAway = Int(exactly: away.rounded()),
              roundedHome != roundedAway || vocab.canEndInATie
        else { return nil }

        return (away: roundedAway, home: roundedHome)
    }

    nonisolated static func resolveLivePregameSummary(
        event: EventDetail,
        shortNames: (away: String, home: String)
    ) -> LivePregameSummary? {
        let strictPregame = PrematchReading.resolve(
            prematch: event.prematchOdds,
            opening: nil
        )
        let projPair = qualifiedLivePregameProjectionPair(event: event)

        var chanceInfo: (namedInk: LivePregameSummary.SegmentInk, homeIsFav: Bool, favName: String, favChanceText: String)?
        if let strictPregame,
           let pair = DrawPricedWinner.printablePair(
               away: strictPregame.awayProbability,
               home: strictPregame.homeProbability,
               sport: event.sport
           ),
           let awayP = pair.away {
            let homeP = pair.home
            let homeIsFav: Bool
            if homeP > awayP {
                homeIsFav = true
            } else if awayP > homeP {
                homeIsFav = false
            } else if let projPair, projPair.home != projPair.away {
                homeIsFav = projPair.home > projPair.away
            } else {
                homeIsFav = true
            }
            let favName = homeIsFav ? shortNames.home : shortNames.away
            let favProb = homeIsFav ? homeP : awayP
            let favRendered = homeIsFav
                ? (strictPregame.percents.count > 1 ? strictPregame.percents[1] : nil)
                : (strictPregame.percents.count > 0 ? strictPregame.percents[0] : nil)
            let favChanceText = formatProbability(favProb, renderedPercent: favRendered)
            chanceInfo = (
                namedInk: homeIsFav ? .homeTeam : .awayTeam,
                homeIsFav: homeIsFav,
                favName: favName,
                favChanceText: favChanceText
            )
        } else if let strictPregame,
                  let pair = DrawPricedWinner.printablePair(
                      away: strictPregame.awayProbability,
                      home: strictPregame.homeProbability,
                      sport: event.sport
                  ) {
            let homePct = strictPregame.percents.count > 1 ? strictPregame.percents[1] : nil
            chanceInfo = (
                namedInk: .homeTeam,
                homeIsFav: true,
                favName: shortNames.home,
                favChanceText: formatProbability(pair.home, renderedPercent: homePct)
            )
        }

        return formatLivePregameSummary(chanceInfo: chanceInfo, projPair: projPair, shortNames: shortNames)
    }

    nonisolated private static func resolveSoccerLivePregameSummary(
        event: EventDetail,
        shortNames: (away: String, home: String),
        pregameShares: (home: Double, draw: Double, away: Double)?
    ) -> LivePregameSummary? {
        let projPair = qualifiedLivePregameProjectionPair(event: event)
        var chanceInfo: (namedInk: LivePregameSummary.SegmentInk, homeIsFav: Bool, favName: String, favChanceText: String)?
        if let shares = pregameShares {
            let texts = soccerThreeWayChanceTexts(
                home: shares.home,
                draw: shares.draw,
                away: shares.away,
                numberStreams: false
            )
            if shares.home >= shares.away && shares.home >= shares.draw {
                chanceInfo = (.homeTeam, true, shortNames.home, texts.home)
            } else if shares.away >= shares.home && shares.away >= shares.draw {
                chanceInfo = (.awayTeam, false, shortNames.away, texts.away)
            } else {
                chanceInfo = (.drawOutcome, projPair.map { $0.home >= $0.away } ?? true, "Draw", texts.draw)
            }
        }
        if chanceInfo == nil {
            return resolveLivePregameSummary(event: event, shortNames: shortNames)
        }
        return formatLivePregameSummary(chanceInfo: chanceInfo, projPair: projPair, shortNames: shortNames)
    }

    nonisolated static func formatLivePregameSummary(
        chanceInfo: (namedInk: LivePregameSummary.SegmentInk, homeIsFav: Bool, favName: String, favChanceText: String)?,
        projPair: (away: Int, home: Int)?,
        shortNames: (away: String, home: String)
    ) -> LivePregameSummary? {
        typealias Seg = LivePregameSummary.Segment
        switch (chanceInfo, projPair) {
        case let (chance?, proj?):
            let favScore = chance.homeIsFav ? proj.home : proj.away
            let dogScore = chance.homeIsFav ? proj.away : proj.home
            let favScoreInk: LivePregameSummary.SegmentInk = chance.homeIsFav ? .homeTeam : .awayTeam
            let dogScoreInk: LivePregameSummary.SegmentInk = chance.homeIsFav ? .awayTeam : .homeTeam
            return LivePregameSummary(
                leadWord: "Pregame",
                bodyText: "\(chance.favName) \(chance.favChanceText) · projected \(favScore)\u{2013}\(dogScore)",
                segments: [
                    Seg(text: "Pregame", ink: .quietLead),
                    Seg(text: "  ", ink: .quiet),
                    Seg(text: "\(chance.favName) \(chance.favChanceText)", ink: chance.namedInk),
                    Seg(text: " · projected ", ink: .quiet),
                    Seg(text: "\(favScore)", ink: favScoreInk),
                    Seg(text: "\u{2013}", ink: .quiet),
                    Seg(text: "\(dogScore)", ink: dogScoreInk),
                ]
            )
        case let (chance?, nil):
            return LivePregameSummary(
                leadWord: "Pregame",
                bodyText: "\(chance.favName) \(chance.favChanceText)",
                segments: [
                    Seg(text: "Pregame", ink: .quietLead),
                    Seg(text: "  ", ink: .quiet),
                    Seg(text: "\(chance.favName) \(chance.favChanceText)", ink: chance.namedInk),
                ]
            )
        case let (nil, proj?):
            if proj.home > proj.away {
                return LivePregameSummary(
                    leadWord: "Pregame",
                    bodyText: "projected \(shortNames.home) \(proj.home)\u{2013}\(proj.away)",
                    segments: [
                        Seg(text: "Pregame", ink: .quietLead),
                        Seg(text: "  projected ", ink: .quiet),
                        Seg(text: "\(shortNames.home) \(proj.home)", ink: .homeTeam),
                        Seg(text: "\u{2013}", ink: .quiet),
                        Seg(text: "\(proj.away)", ink: .awayTeam),
                    ]
                )
            } else if proj.away > proj.home {
                return LivePregameSummary(
                    leadWord: "Pregame",
                    bodyText: "projected \(shortNames.away) \(proj.away)\u{2013}\(proj.home)",
                    segments: [
                        Seg(text: "Pregame", ink: .quietLead),
                        Seg(text: "  projected ", ink: .quiet),
                        Seg(text: "\(shortNames.away) \(proj.away)", ink: .awayTeam),
                        Seg(text: "\u{2013}", ink: .quiet),
                        Seg(text: "\(proj.home)", ink: .homeTeam),
                    ]
                )
            } else {
                return LivePregameSummary(
                    leadWord: "Pregame",
                    bodyText: "projected \(proj.home)\u{2013}\(proj.away)",
                    segments: [
                        Seg(text: "Pregame", ink: .quietLead),
                        Seg(text: "  projected ", ink: .quiet),
                        Seg(text: "\(proj.home)", ink: .homeTeam),
                        Seg(text: "\u{2013}", ink: .quiet),
                        Seg(text: "\(proj.away)", ink: .awayTeam),
                    ]
                )
            }
        case (nil, nil):
            return nil
        }
    }

    // MARK: - Tennis Score-Slot Helpers

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
        let isTiebreak = event.linescore?.tiebreak == true
        if let rawPeriod = trimmedNonEmpty(event.espn?.period) {
            let normalized = normalizeTennisSetLabel(rawPeriod)
            let alreadyMentionsTB = normalized.localizedCaseInsensitiveContains("tb")
                || normalized.localizedCaseInsensitiveContains("tiebreak")
            if isTiebreak && !alreadyMentionsTB {
                return "LIVE · \(normalized) · TB"
            }
            return "LIVE · \(normalized)"
        }
        let linescoreSetCount = event.linescore?.sets?.count ?? 0
        let setCount = max(
            linescoreSetCount,
            max(
                event.boxScoreData?.awayPeriodScores?.compactMap { $0 }.count ?? 0,
                event.boxScoreData?.homePeriodScores?.compactMap { $0 }.count ?? 0
            )
        )
        if setCount >= 1 {
            return isTiebreak ? "LIVE · Set \(setCount) · TB" : "LIVE · Set \(setCount)"
        }
        if let status = trimmedNonEmpty(liveStatusText),
           parseTennisGamePointsFromClock(status) == nil {
            return isTiebreak ? "LIVE · \(status) · TB" : "LIVE · \(status)"
        }
        return isTiebreak ? "LIVE · TB" : "LIVE"
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

    nonisolated private static let tennisTiebreakPairRegex: NSRegularExpression? = try? NSRegularExpression(
        pattern: #"^\s*(\d{1,2})\s*[-–:]\s*(\d{1,2})\s*$"#
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

    nonisolated static func parseTennisTiebreakPointsFromClock(
        _ rawClock: String?
    ) -> (away: String, home: String)? {
        guard let rawClock = trimmedNonEmpty(rawClock) else { return nil }
        let nsRange = NSRange(rawClock.startIndex..<rawClock.endIndex, in: rawClock)
        guard let match = tennisTiebreakPairRegex?.firstMatch(in: rawClock, options: [], range: nsRange),
              let firstRange = Range(match.range(at: 1), in: rawClock),
              let secondRange = Range(match.range(at: 2), in: rawClock)
        else { return nil }
        return (away: String(rawClock[firstRange]), home: String(rawClock[secondRange]))
    }

    private struct TennisScoreSlotResult {
        let columns: [ColumnSpec]
        let awayCells: [String]
        let homeCells: [String]
        let awayEmph: Set<Int>
        let homeEmph: Set<Int>
        let awaySuperscripts: [Int: String]
        let homeSuperscripts: [Int: String]
        let scoreFirstModel: TennisScoreFirstModel
    }

    nonisolated private static func buildTennisScoreSlot(
        event: EventDetail,
        hasScore: Bool,
        includePoints: Bool
    ) -> TennisScoreSlotResult {
        let linescoreSets = event.linescore?.sets ?? []
        let linescoreTiebreaks = event.linescore?.tiebreaks ?? []
        let awayPeriods: [Int?]
        let homePeriods: [Int?]
        if !linescoreSets.isEmpty {
            homePeriods = linescoreSets.map { $0.count >= 2 ? $0[0] : nil }
            awayPeriods = linescoreSets.map { $0.count >= 2 ? $0[1] : nil }
        } else {
            awayPeriods = event.boxScoreData?.awayPeriodScores ?? []
            homePeriods = event.boxScoreData?.homePeriodScores ?? []
        }
        let maxSets = max(awayPeriods.count, homePeriods.count)

        var cols: [ColumnSpec] = []
        var awayCells: [String] = []
        var homeCells: [String] = []
        var awayEmph: Set<Int> = []
        var homeEmph: Set<Int> = []
        var awaySuperscripts: [Int: String] = [:]
        var homeSuperscripts: [Int: String] = [:]
        var setColumns: [TennisSetColumn] = []
        var activeSetIsSixAll = false

        if maxSets > 0 {
            var pairs: [(index: Int, away: Int, home: Int, awayTB: String?, homeTB: String?)] = []
            for idx in 0..<maxSets {
                let a = idx < awayPeriods.count ? awayPeriods[idx] : nil
                let h = idx < homePeriods.count ? homePeriods[idx] : nil
                if let a, let h {
                    var awayTB: String? = nil
                    var homeTB: String? = nil
                    if idx < linescoreTiebreaks.count,
                       let tbPair = linescoreTiebreaks[idx],
                       tbPair.count >= 2 {
                        homeTB = "\(tbPair[0])"
                        awayTB = "\(tbPair[1])"
                    }
                    pairs.append((index: idx + 1, away: a, home: h, awayTB: awayTB, homeTB: homeTB))
                }
            }
            if let last = pairs.last, last.away == 6 && last.home == 6 {
                activeSetIsSixAll = true
            }
            for (offset, entry) in pairs.enumerated() {
                let isCurrentSet = includePoints && (offset == pairs.count - 1)
                let aEmph = isCurrentSet || entry.away > entry.home
                let hEmph = isCurrentSet || entry.home > entry.away
                cols.append(.init(role: .setScore(index: entry.index), header: "S\(entry.index)"))
                awayCells.append("\(entry.away)")
                homeCells.append("\(entry.home)")
                if aEmph { awayEmph.insert(offset) }
                if hEmph { homeEmph.insert(offset) }
                if let aTB = entry.awayTB { awaySuperscripts[offset] = aTB }
                if let hTB = entry.homeTB { homeSuperscripts[offset] = hTB }
                setColumns.append(
                    TennisSetColumn(
                        header: "S\(entry.index)",
                        awayValue: "\(entry.away)",
                        homeValue: "\(entry.home)",
                        awayTiebreak: entry.awayTB,
                        homeTiebreak: entry.homeTB,
                        awayEmphasized: aEmph,
                        homeEmphasized: hEmph
                    )
                )
            }
        }

        if cols.isEmpty && includePoints {
            cols.append(.init(role: .setScore(index: 0), header: "Sets"))
            let awaySetsVal = hasScore ? (event.awayScore.map(String.init) ?? "") : ""
            let homeSetsVal = hasScore ? (event.homeScore.map(String.init) ?? "") : ""
            awayCells.append(awaySetsVal)
            homeCells.append(homeSetsVal)
            if hasScore {
                awayEmph.insert(0)
                homeEmph.insert(0)
            }
            if !awaySetsVal.isEmpty && !homeSetsVal.isEmpty {
                setColumns.append(
                    TennisSetColumn(
                        header: "Sets",
                        awayValue: awaySetsVal,
                        homeValue: homeSetsVal,
                        awayEmphasized: true,
                        homeEmphasized: true
                    )
                )
            }
        }

        let resolvedPoints: (pair: (away: String, home: String)?, isTiebreak: Bool) = {
            guard includePoints else { return (pair: nil, isTiebreak: false) }
            if let awayPts = trimmedNonEmpty(event.linescore?.awayPoints),
               let homePts = trimmedNonEmpty(event.linescore?.homePoints) {
                return (pair: (away: awayPts, home: homePts), isTiebreak: event.linescore?.tiebreak == true)
            }
            if let ordinary = parseTennisGamePointsFromClock(event.espn?.gameClock) {
                return (pair: ordinary, isTiebreak: false)
            }
            let periodIndicatesTB = (event.espn?.period?.localizedCaseInsensitiveContains("tiebreak") == true)
                || (event.espn?.period?.localizedCaseInsensitiveContains("tb") == true)
            if (event.linescore?.tiebreak == true || activeSetIsSixAll || periodIndicatesTB),
               let tbPts = parseTennisTiebreakPointsFromClock(event.espn?.gameClock) {
                return (pair: tbPts, isTiebreak: true)
            }
            return (pair: nil, isTiebreak: false)
        }()

        let pointsHeader = resolvedPoints.isTiebreak ? "TB" : "Pts"
        if let pts = resolvedPoints.pair {
            cols.append(.init(role: .gamePoints, header: pointsHeader))
            awayCells.append(pts.away)
            homeCells.append(pts.home)
        }

        let sfModel = TennisScoreFirstModel(
            setColumns: setColumns,
            pointsColumn: resolvedPoints.pair,
            pointsHeader: pointsHeader,
            isTiebreakPoints: resolvedPoints.isTiebreak,
            pregameHeader: nil,
            nowHeader: "Now"
        )

        return TennisScoreSlotResult(
            columns: cols,
            awayCells: awayCells,
            homeCells: homeCells,
            awayEmph: awayEmph,
            homeEmph: homeEmph,
            awaySuperscripts: awaySuperscripts,
            homeSuperscripts: homeSuperscripts,
            scoreFirstModel: sfModel
        )
    }

    nonisolated private static func trimmedNonEmpty(_ text: String?) -> String? {
        guard let text = text?.trimmingCharacters(in: .whitespacesAndNewlines), !text.isEmpty else {
            return nil
        }
        return text
    }
}
