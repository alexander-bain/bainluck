import Foundation

/// Ruling 183-A / #12616 — maps `SearchEvent` rows from `/api/events/search`
/// (Size M on `SearchView`) and `/api/teams/{slug}` (Size S on `TeamDetailView`)
/// onto `FeedEventData` so every surface renders the one unified `EventCardView`.
enum SearchEventCardAdapter183A {

    /// Maps an event from `/api/events/search` onto `FeedEventData` for Size M `EventCardView`.
    static func fromSearchResult(
        _ event: SearchEvent,
        sportDisplayName: String?
    ) -> FeedEventData {
        let isOpeningLine = event.heroProbabilitySource == OpeningLineHero.openingSource
        let resolvedCurrentOdds: CurrentOdds? = {
            if var current = event.currentOdds {
                if isOpeningLine {
                    // The old serializer's snapshot stamp dates the book rows, not the win chance.
                    current.homeProbability = nil
                    current.awayProbability = nil
                    current.drawProbability = nil
                    current.homeRenderedPercent = nil
                    current.awayRenderedPercent = nil
                }
                return current
            }
            // #4967 — search rows without `current_odds` still serve `hero_probability` /
            // `hero_probability_away`. Populate `CurrentOdds` when gradable so the card
            // renders the server's blended probability (`EventCardView.currentAwayIsWithheld`
            // enforces #5363 on draw-priced sports).
            guard !isOpeningLine, EventState.canStillBeGraded(
                event.status,
                commenceTime: event.commenceTime?.asDate
            ), event.heroProbability != nil || event.heroProbabilityAway != nil else {
                return nil
            }
            return CurrentOdds(
                capturedAt: nil,
                homeProbability: event.heroProbability,
                awayProbability: event.heroProbabilityAway,
                homeRenderedPercent: nil,
                awayRenderedPercent: nil,
                spread: nil,
                homeSpread: nil,
                overUnder: nil,
                projectedHomeScore: nil,
                projectedAwayScore: nil,
                bookmakerCount: nil
            )
        }()

        let resolvedESPN: ESPNData? = resolveESPN(event)

        return FeedEventData(
            id: event.id,
            externalId: event.externalId,
            sport: event.sport ?? event.sportKey,
            sportName: sportDisplayName ?? event.sportName,
            homeTeam: event.homeTeam,
            awayTeam: event.awayTeam,
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore,
            blendFoldRevision: nil,
            heroProbabilitySource: event.heroProbabilitySource,
            heroProbabilityObservedAt: nil,
            currentOdds: resolvedCurrentOdds,
            openingOdds: event.openingOdds,
            prematchOdds: event.prematchOdds,
            pregameProjection: event.pregameProjection,
            finalScorePeriod: event.finalScorePeriod,
            highlight: event.highlight,
            homeTeamData: event.homeTeamData,
            awayTeamData: event.awayTeamData,
            metadata: event.metadata,
            espn: resolvedESPN,
            ei: event.ei,
            pulse: event.pulse,
            winProbabilitySources: event.winProbabilitySources,
            confidenceTier: nil,
            confidenceScore: nil,
            homeImageUrl: event.homeImageUrl,
            awayImageUrl: event.awayImageUrl,
            homeFlagUrl: event.homeFlagUrl,
            awayFlagUrl: event.awayFlagUrl,
            endedAt: nil,
            discoverMarqueeFinal: nil,
            venueClosedNoWinner: event.venueClosedNoWinner,
            sourceMark: isOpeningLine ? nil : event.sourceMark,
            awaySourceMark: isOpeningLine ? nil : event.awaySourceMark,
            pregameSourceMark: event.pregameSourceMark,
            awayPregameSourceMark: event.awayPregameSourceMark
        )
    }

    /// Maps a schedule or recent-results brief from `/api/teams/{slug}` onto `FeedEventData`
    /// for Size S `EventCardView` (`compactScheduleStyle: true`).
    static func fromTeamScheduleBrief(
        _ event: SearchEvent,
        team: TeamPageTeam
    ) -> (feedEvent: FeedEventData, awayReadingIsServerVerified: Bool) {
        let isHome = TeamGameRow.isHome(event, teamName: team.name)
        let resolvedSportKey = event.sport ?? event.sportKey ?? team.sportKey
        let pricesADraw = DrawPricedWinner.sportPricesADraw(resolvedSportKey)

        let pageTeamData = TeamData(
            primaryColor: team.primaryColor,
            secondaryColor: team.secondaryColor,
            logoSmall: team.logoSmall ?? team.logoLarge,
            logoLarge: team.logoLarge ?? team.logoSmall,
            record: team.record,
            standings: nil,
            abbreviation: team.abbreviation
        )

        let homeTeamData = isHome ? (event.homeTeamData ?? pageTeamData) : event.homeTeamData
        let awayTeamData = isHome ? event.awayTeamData : (event.awayTeamData ?? pageTeamData)

        let livePrice = TeamGameRow.livePrice(event)
        let resolvedCurrentOdds: CurrentOdds? = {
            if let existing = event.currentOdds {
                return existing
            }
            guard let livePrice else { return nil }
            let homeProb: Double?
            let awayProb: Double?
            if isHome {
                homeProb = livePrice
                awayProb = pricesADraw ? nil : (1.0 - livePrice)
            } else {
                awayProb = livePrice
                homeProb = pricesADraw ? nil : (1.0 - livePrice)
            }
            return CurrentOdds(
                capturedAt: nil,
                homeProbability: homeProb,
                awayProbability: awayProb,
                homeRenderedPercent: nil,
                awayRenderedPercent: nil,
                spread: nil,
                homeSpread: nil,
                overUnder: nil,
                projectedHomeScore: nil,
                projectedAwayScore: nil,
                bookmakerCount: nil
            )
        }()

        let resolvedPrematchOdds: PrematchOdds? = {
            if let existing = event.prematchOdds {
                return existing
            }
            guard let pre = event.pregameWinProbability,
                  pre.isFinite, (0.0...1.0).contains(pre) else {
                return nil
            }
            let homePre: Double?
            let awayPre: Double?
            if isHome {
                homePre = pre
                awayPre = pricesADraw ? nil : (1.0 - pre)
            } else {
                awayPre = pre
                homePre = pricesADraw ? nil : (1.0 - pre)
            }
            let duel = duelPercents(
                away: awayPre,
                home: homePre,
                servedAway: nil,
                servedHome: nil
            )
            return PrematchOdds(
                homeProbability: homePre,
                awayProbability: awayPre,
                homeRenderedPercent: duel[1],
                awayRenderedPercent: duel[0],
                source: "books"
            )
        }()

        let resolvedESPN: ESPNData? = resolveESPN(event)

        let awayVerified = !isHome && pricesADraw
            && (livePrice != nil || event.pregameWinProbability != nil)

        // `/api/teams/{slug}` (#12926) orients `source_mark` and `pregame_source_mark`
        // to this page's team (`isHome`). Map them onto the matching side without ever
        // synthesizing or complementing an opponent mark (137-A).
        let homeCurrentMark: SourceMark? = isHome ? event.sourceMark : event.awaySourceMark
        let awayCurrentMark: SourceMark? = isHome ? event.awaySourceMark : event.sourceMark
        let homePregameMark: SourceMark? = isHome ? event.pregameSourceMark : event.awayPregameSourceMark
        let awayPregameMark: SourceMark? = isHome ? event.awayPregameSourceMark : event.pregameSourceMark

        let feedEvent = FeedEventData(
            id: event.id,
            externalId: event.externalId,
            sport: resolvedSportKey,
            sportName: event.sportName ?? team.sportName,
            homeTeam: event.homeTeam,
            awayTeam: event.awayTeam,
            commenceTime: event.commenceTime,
            startIsTbd: event.startIsTbd,
            status: event.status,
            homeScore: event.homeScore,
            awayScore: event.awayScore,
            blendFoldRevision: nil,
            heroProbabilitySource: nil,
            heroProbabilityObservedAt: nil,
            currentOdds: resolvedCurrentOdds,
            openingOdds: event.openingOdds,
            prematchOdds: resolvedPrematchOdds,
            pregameProjection: event.pregameProjection,
            finalScorePeriod: event.finalScorePeriod,
            highlight: event.highlight,
            homeTeamData: homeTeamData,
            awayTeamData: awayTeamData,
            metadata: event.metadata,
            espn: resolvedESPN,
            ei: event.ei,
            pulse: event.pulse,
            winProbabilitySources: event.winProbabilitySources,
            confidenceTier: nil,
            confidenceScore: nil,
            homeImageUrl: event.homeImageUrl,
            awayImageUrl: event.awayImageUrl,
            homeFlagUrl: event.homeFlagUrl,
            awayFlagUrl: event.awayFlagUrl,
            endedAt: nil,
            discoverMarqueeFinal: nil,
            venueClosedNoWinner: event.venueClosedNoWinner,
            sourceMark: homeCurrentMark,
            awaySourceMark: awayCurrentMark,
            pregameSourceMark: homePregameMark,
            awayPregameSourceMark: awayPregameMark
        )
        return (feedEvent: feedEvent, awayReadingIsServerVerified: awayVerified)
    }

    private static func resolveESPN(_ event: SearchEvent) -> ESPNData? {
        if let espn = event.espn {
            if espn.period == nil, let authority = event.authorityPeriod {
                return ESPNData(
                    espnId: espn.espnId,
                    gameClock: espn.gameClock,
                    period: authority,
                    broadcast: espn.broadcast,
                    winProbability: espn.winProbability,
                    probabilitySources: espn.probabilitySources,
                    seriesHomeWins: espn.seriesHomeWins,
                    seriesAwayWins: espn.seriesAwayWins
                )
            }
            return espn
        }
        guard let authority = event.authorityPeriod else { return nil }
        return ESPNData(
            espnId: nil,
            gameClock: nil,
            period: authority,
            broadcast: nil,
            winProbability: nil,
            probabilitySources: nil,
            seriesHomeWins: nil,
            seriesAwayWins: nil
        )
    }
}
