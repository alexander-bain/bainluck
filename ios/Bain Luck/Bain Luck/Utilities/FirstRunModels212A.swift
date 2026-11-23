import Foundation

// MARK: - Ruling 212-A — First-Run Onboarding Models (#11934, #13517)

/// One real live card presented inside a first-run two-card pair (`2A` / `2B` / `2C`).
///
/// Follows Fable's Nov 16 changes and Pass 4/5 copy rules:
/// - probability changes always read in `"points"` (never `"pts"` or `%` of `%`),
/// - no internal scaffolding ("CARD A", "Quick tune", "watchlist", "Feed"),
/// - projections are whole numbers only,
/// - always pairs real cards across sports and non-sports worlds.
nonisolated struct FirstRunCard212A: Identifiable, Equatable, Sendable {
    let id: String
    let kicker: String
    let subtitleRight: String?
    let title: String
    let detailLine: String?
    let percent: Int
    let percentLabel: String
    let deltaPoints: Int?
    let accentHex: String
    let sfSymbol: String
    let logoUrl: String?
    let isSports: Bool
    let choiceButtonLabel: String
    let affinityCategory: String
    let workedMeaningLine: String?
    let followedSubject: FollowedSubject295A?

    /// Category / sport SF Symbol icon (replaces truncated letter monograms).
    static func sfSymbol(forCategory category: String, isSports: Bool) -> String {
        let lower = category.lowercased()
        if lower.contains("nfl") || lower.contains("ncaaf") || lower.contains("football") {
            return "football.fill"
        }
        if lower.contains("nba") || lower.contains("ncaab") || lower.contains("basketball") {
            return "basketball.fill"
        }
        if lower.contains("nhl") || lower.contains("hockey") {
            return "hockey.puck.fill"
        }
        if lower.contains("mlb") || lower.contains("baseball") {
            return "baseball.fill"
        }
        if lower.contains("soccer") || lower.contains("epl") || lower.contains("mls") {
            return "soccerball"
        }
        if lower.contains("tennis") {
            return "tennisball.fill"
        }
        if lower.contains("golf") {
            return "figure.golf"
        }
        if lower.contains("entertainment") || lower.contains("oscar") || lower.contains("culture") || lower.contains("grammy") || lower.contains("music") {
            return "film.fill"
        }
        if lower.contains("econ") || lower.contains("fed") || lower.contains("macro") || lower.contains("finance") {
            return "chart.line.uptrend.xyaxis"
        }
        if lower.contains("tech") || lower.contains("ai") || lower.contains("science") {
            return "cpu.fill"
        }
        if lower.contains("weather") || lower.contains("climate") {
            return "cloud.sun.fill"
        }
        if lower.contains("politic") || lower.contains("election") {
            return "building.columns.fill"
        }
        return isSports ? "sportscourt.fill" : "globe"
    }

    /// Plain-English shift copy strictly using `"points"` (never `"pts"`).
    static func shiftText(points delta: Int?, window: String? = nil) -> String? {
        guard let delta, delta != 0 else { return nil }
        let absVal = abs(delta)
        let noun = absVal == 1 ? "point" : "points"
        let arrow = delta > 0 ? "▲ up" : "▼ down"
        if let window, !window.isEmpty {
            return "\(arrow) \(absVal) \(noun) \(window)"
        }
        return "\(arrow) \(absVal) \(noun)"
    }

    /// Worked plain-English odds example shown on Pair 1 ("What N% means").
    static func workedMeaning(percent: Int) -> String {
        let outOfTen = max(1, min(9, Int((Double(percent) / 10.0).rounded())))
        if percent >= 45 && percent <= 55 {
            return "\(percent)% means about a coin flip — roughly \(outOfTen) times in 10."
        }
        return "\(percent)% means about \(outOfTen) times in 10."
    }
}

/// Choice options on each pair screen (`Just A`, `Just B`, `Both of these`, `Neither`).
nonisolated enum FirstRunChoice212A: String, Equatable, CaseIterable, Sendable {
    case top
    case bottom
    case both
    case neither
}

/// One step in the three-pair comparison sequence (`2A`, `2B`, `2C`).
nonisolated struct FirstRunPair212A: Identifiable, Equatable, Sendable {
    let id: String
    let promptTitle: String
    let arrivedContextPill: String?
    let topCard: FirstRunCard212A
    let bottomCard: FirstRunCard212A

    /// Builds 3 real pairs mixing sports and non-sports items from the live Discover feed,
    /// falling back gracefully per slot to curated defaults if the feed is sparse or offline.
    static func buildPairs(
        from feedItems: [FeedItem],
        arrivedHeadline: String? = nil
    ) -> [FirstRunPair212A] {
        let nonSports = extractCards(from: feedItems, wantSports: false)
        let sports = extractCards(from: feedItems, wantSports: true)

        let p1Top = sports.indices.contains(0) ? sports[0] : fallbackSportsCard1
        let p1Bot = nonSports.indices.contains(0) ? nonSports[0] : fallbackNonSportsCard1

        let p2Top = sports.indices.contains(1) ? sports[1] : fallbackSportsCard2
        let p2Bot = nonSports.indices.contains(1) ? nonSports[1] : fallbackNonSportsCard2

        // Pair 3 deliberately pairs two non-sports cards ("some pairs are not sports")
        // so non-sports readers immediately see the breadth of Bain Luck.
        let p3Top = nonSports.indices.contains(2) ? nonSports[2] : fallbackNonSportsCard3
        let p3Bot = nonSports.indices.contains(3) ? nonSports[3] : fallbackNonSportsCard4

        let cleanArrived = arrivedHeadline?.trimmingCharacters(in: .whitespacesAndNewlines)
        let pill = (cleanArrived?.isEmpty == false) ? "Started from your link · \(cleanArrived!)" : nil

        return [
            FirstRunPair212A(
                id: "pair-1",
                promptTitle: "Which of these would you check?",
                arrivedContextPill: pill,
                topCard: withWorkedMeaning(p1Top),
                bottomCard: p1Bot
            ),
            FirstRunPair212A(
                id: "pair-2",
                promptTitle: "How about these two?",
                arrivedContextPill: nil,
                topCard: p2Top,
                bottomCard: p2Bot
            ),
            FirstRunPair212A(
                id: "pair-3",
                promptTitle: "And between these two?",
                arrivedContextPill: nil,
                topCard: p3Top,
                bottomCard: p3Bot
            ),
        ]
    }

    private static func withWorkedMeaning(_ card: FirstRunCard212A) -> FirstRunCard212A {
        FirstRunCard212A(
            id: card.id,
            kicker: card.kicker,
            subtitleRight: card.subtitleRight,
            title: card.title,
            detailLine: card.detailLine,
            percent: card.percent,
            percentLabel: card.percentLabel,
            deltaPoints: card.deltaPoints,
            accentHex: card.accentHex,
            sfSymbol: card.sfSymbol,
            logoUrl: card.logoUrl,
            isSports: card.isSports,
            choiceButtonLabel: card.choiceButtonLabel,
            affinityCategory: card.affinityCategory,
            workedMeaningLine: card.workedMeaningLine ?? FirstRunCard212A.workedMeaning(percent: card.percent),
            followedSubject: card.followedSubject
        )
    }

    private static func flattenedItems(from items: [FeedItem]) -> [FeedItem] {
        var flat: [FeedItem] = []
        for item in items {
            if let bundle = item.bundle {
                flat.append(contentsOf: bundle.items)
            } else {
                flat.append(item)
            }
        }
        return flat
    }

    private static func extractCards(from rawItems: [FeedItem], wantSports: Bool) -> [FirstRunCard212A] {
        var out: [FirstRunCard212A] = []
        var seenCategories: Set<String> = []
        let items = flattenedItems(from: rawItems)
        for item in items {
            if let ev = item.event, wantSports {
                guard let prob = ev.currentOdds?.homeProbability ?? ev.openingOdds?.homeProbability else { continue }
                let pct = max(1, min(99, Int((prob * 100.0).rounded())))
                let cat = DiscoverCategory.token(forSport: ev.sport)
                let leagueLabel = sportDisplayName(for: ev.sport)
                let shortNames = TeamShortName.shortPair(away: ev.awayTeam, home: ev.homeTeam, sportKey: ev.sport)
                let shortHome = shortNames.home
                let shortAway = shortNames.away
                let sportTag = leagueLabel.isEmpty ? "Sports" : leagueLabel
                if seenCategories.contains(cat) && out.count < 4 { continue }
                seenCategories.insert(cat)
                let subject = FollowedSubject295A.teamFromEventSide(event: ev, isHome: true)
                let deltaPts: Int? = {
                    guard let pre = ev.prematchOdds?.homeProbability ?? ev.openingOdds?.homeProbability else { return nil }
                    let diff = Int(((prob - pre) * 100.0).rounded())
                    return diff == 0 ? nil : diff
                }()
                var detail: String?
                if let proj = ev.pregameProjection,
                   let awayProj = proj.projectedAwayScore,
                   let homeProj = proj.projectedHomeScore {
                    detail = "Projected: \(shortAway) \(Int(awayProj.rounded())) – \(shortHome) \(Int(homeProj.rounded()))"
                }
                out.append(FirstRunCard212A(
                    id: "ev-\(ev.id)",
                    kicker: sportTag.uppercased(),
                    subtitleRight: ev.status == "live" ? "Live now" : nil,
                    title: "\(shortAway) at \(shortHome)",
                    detailLine: detail,
                    percent: pct,
                    percentLabel: shortHome,
                    deltaPoints: deltaPts,
                    accentHex: ev.homeTeamData?.primaryColor ?? "#047857",
                    sfSymbol: FirstRunCard212A.sfSymbol(forCategory: cat, isSports: true),
                    logoUrl: ev.homeTeamData?.logoSmall ?? ev.homeTeamData?.logoLarge,
                    isSports: true,
                    choiceButtonLabel: "Just \(shortHome)",
                    affinityCategory: cat,
                    workedMeaningLine: nil,
                    followedSubject: subject
                ))
            } else if let fut = item.futures {
                let rawCat = (fut.llmSportCategory ?? fut.sport ?? "").lowercased()
                let sportTok = fut.sport.map { DiscoverCategory.token(forSport: $0) }
                let isSportFut = sportTok.map { DiscoverCategory.sportsFeedbackCategories.contains($0) } ?? false
                guard isSportFut == wantSports else { continue }
                guard let firstOutcome = fut.topOutcomes?.first,
                      let rawProb = firstOutcome.probability else { continue }
                let pct = max(1, min(99, Int((rawProb * 100.0).rounded())))
                let catKey = isSportFut ? (sportTok ?? rawCat) : (rawCat.isEmpty ? "culture" : rawCat)
                if seenCategories.contains(catKey) && out.count < 4 { continue }
                seenCategories.insert(catKey)

                let catDisplay = sportCategoryDisplayName(catKey)
                let deltaPts: Int? = {
                    guard let move = firstOutcome.movement else { return nil }
                    let diff = Int((move * 100.0).rounded())
                    return diff == 0 ? nil : diff
                }()
                let shortBtn = "Just \(catDisplay)"
                out.append(FirstRunCard212A(
                    id: "fut-\(fut.id)",
                    kicker: catDisplay.uppercased(),
                    subtitleRight: firstOutcome.name,
                    title: fut.name,
                    detailLine: fut.hookDescription,
                    percent: pct,
                    percentLabel: "chance",
                    deltaPoints: deltaPts,
                    accentHex: isSportFut ? "#005CC2" : "#7C3AED",
                    sfSymbol: FirstRunCard212A.sfSymbol(forCategory: catKey, isSports: isSportFut),
                    logoUrl: fut.imageUrl,
                    isSports: isSportFut,
                    choiceButtonLabel: shortBtn,
                    affinityCategory: catKey,
                    workedMeaningLine: nil,
                    followedSubject: nil
                ))
            }
            if out.count >= 4 { break }
        }
        return out
    }

    // MARK: - Offline-safe Real-Market Defaults

    static let fallbackSportsCard1 = FirstRunCard212A(
        id: "default-nfl-fut",
        kicker: "NFL SEASON FUTURE",
        subtitleRight: "Division Race",
        title: "Bengals make the NFL Playoffs",
        detailLine: "AFC North contention",
        percent: 44,
        percentLabel: "chance",
        deltaPoints: 4,
        accentHex: "#FB4F14",
        sfSymbol: "football.fill",
        logoUrl: "https://a.espncdn.com/i/teamlogos/nfl/500/scoreboard/cin.png",
        isSports: true,
        choiceButtonLabel: "Just Bengals",
        affinityCategory: "nfl",
        workedMeaningLine: "44% means just under a coin flip — about 4 times in 10.",
        followedSubject: FollowedSubject295A.team(slug: "cincinnati-bengals", teamId: nil, name: "Cincinnati Bengals", sportKey: "americanfootball_nfl")
    )

    static let fallbackNonSportsCard1 = FirstRunCard212A(
        id: "default-oscars",
        kicker: "2027 OSCARS",
        subtitleRight: "Best Picture",
        title: "The Odyssey wins Best Picture",
        detailLine: "Early awards frontrunner",
        percent: 29,
        percentLabel: "to win",
        deltaPoints: nil,
        accentHex: "#B45309",
        sfSymbol: "film.fill",
        logoUrl: nil,
        isSports: false,
        choiceButtonLabel: "Just Oscars",
        affinityCategory: "entertainment",
        workedMeaningLine: nil,
        followedSubject: FollowedSubject295A.set(slug: "machinery-oscars-best-actor-2027", setKind: .container, name: "Oscars 2027")
    )

    static let fallbackSportsCard2 = FirstRunCard212A(
        id: "default-nba",
        kicker: "NBA · TONIGHT",
        subtitleRight: nil,
        title: "Celtics beat Bucks tonight",
        detailLine: "Projected: BOS 116 – MIL 112",
        percent: 61,
        percentLabel: "Celtics",
        deltaPoints: 3,
        accentHex: "#007A33",
        sfSymbol: "basketball.fill",
        logoUrl: "https://a.espncdn.com/i/teamlogos/nba/500/scoreboard/bos.png",
        isSports: true,
        choiceButtonLabel: "Just NBA",
        affinityCategory: "nba",
        workedMeaningLine: nil,
        followedSubject: FollowedSubject295A.team(slug: "boston-celtics", teamId: 100, name: "Boston Celtics", sportKey: "basketball_nba")
    )

    static let fallbackNonSportsCard2 = FirstRunCard212A(
        id: "default-economy",
        kicker: "ECONOMY · FED",
        subtitleRight: "Rate Decision",
        title: "Fed cuts interest rates in December",
        detailLine: "Moved after inflation report",
        percent: 72,
        percentLabel: "chance",
        deltaPoints: 9,
        accentHex: "#005CC2",
        sfSymbol: "chart.line.uptrend.xyaxis",
        logoUrl: nil,
        isSports: false,
        choiceButtonLabel: "Just Economy",
        affinityCategory: "economics",
        workedMeaningLine: nil,
        followedSubject: FollowedSubject295A.set(slug: "machinery-fed-and-macro", setKind: .container, name: "Fed & Macro")
    )

    static let fallbackSportsCard3 = FirstRunCard212A(
        id: "default-cfb",
        kicker: "COLLEGE FOOTBALL",
        subtitleRight: "Playoff Race",
        title: "Ohio State wins the National Title",
        detailLine: "CFP contender field",
        percent: 24,
        percentLabel: "chance",
        deltaPoints: nil,
        accentHex: "#BB0000",
        sfSymbol: "football.fill",
        logoUrl: nil,
        isSports: true,
        choiceButtonLabel: "Just College FB",
        affinityCategory: "college_football",
        workedMeaningLine: nil,
        followedSubject: FollowedSubject295A.team(slug: "ohio-state-buckeyes", teamId: nil, name: "Ohio State Buckeyes", sportKey: "americanfootball_ncaaf")
    )

    static let fallbackNonSportsCard3 = FirstRunCard212A(
        id: "default-tech-ai",
        kicker: "TECH & AI",
        subtitleRight: "Year-End Lead",
        title: "Top AI model leads year-end ranking",
        detailLine: "Tracked across open markets",
        percent: 75,
        percentLabel: "chance",
        deltaPoints: 6,
        accentHex: "#6D28D9",
        sfSymbol: "cpu.fill",
        logoUrl: nil,
        isSports: false,
        choiceButtonLabel: "Just Tech & AI",
        affinityCategory: "tech",
        workedMeaningLine: nil,
        followedSubject: FollowedSubject295A.set(slug: "machinery-ai-math-and-data-centers", setKind: .container, name: "AI Math & Data Centers")
    )

    static let fallbackNonSportsCard4 = FirstRunCard212A(
        id: "default-weather-climate",
        kicker: "WEATHER & CLIMATE",
        subtitleRight: "Global Heat",
        title: "2026 ranks among warmest years on record",
        detailLine: "Global temperature anomaly forecast",
        percent: 88,
        percentLabel: "chance",
        deltaPoints: 2,
        accentHex: "#0284C7",
        sfSymbol: "cloud.sun.fill",
        logoUrl: nil,
        isSports: false,
        choiceButtonLabel: "Just Weather",
        affinityCategory: "weather",
        workedMeaningLine: nil,
        followedSubject: FollowedSubject295A.set(slug: "machinery-earth-quakes-and-storms-2026", setKind: .container, name: "Earth, Quakes & Storms")
    )
}

/// One unified item in Screen 2D (`"Any cities, schools or subjects you care about?"`).
///
/// Guarantees:
/// - Multi-sport teams from one school (`Brown Bears` NCAAB vs Football vs Women's Basketball)
///   keep separate `id`s and always carry their distinct sport label in `sportOrCategoryLabel`.
/// - Teams, cities, leagues, sets, and non-sports subjects share one uniform selection contract.
nonisolated struct FirstRunSuggestion212A: Identifiable, Equatable, Sendable {
    let id: String
    let name: String
    let sportOrCategoryLabel: String
    let contextLine: String?
    let logoUrl: String?
    let primaryColorHex: String?
    let teamId: Int?
    let sportKey: String?
    let followedSubject: FollowedSubject295A?
    let affinityCategory: String?

    /// Display text for picked chips — appends the sport/category whenever `sportOrCategoryLabel`
    /// is present so two teams from one school (`Brown Bears · NCAAB`, `Brown Bears · Football`)
    /// always read differently.
    var chipDisplayText: String {
        if !sportOrCategoryLabel.isEmpty {
            return "\(name) · \(sportOrCategoryLabel)"
        }
        return name
    }

    var rowSubtitleText: String {
        switch (sportOrCategoryLabel.isEmpty ? nil : sportOrCategoryLabel, contextLine?.isEmpty == false ? contextLine : nil) {
        case let (sport?, ctx?):
            return "\(sport) · \(ctx)"
        case let (sport?, nil):
            return sport
        case let (nil, ctx?):
            return ctx
        case (nil, nil):
            return "Subject"
        }
    }

    /// Expands `/api/me/teams/*` responses into distinct per-(team, sport) suggestions
    /// without collapsing multi-sport teams of the same school.
    static func fromTeamSearchResults(
        _ results: [TeamSearchResult],
        contextHint: String? = nil
    ) -> [FirstRunSuggestion212A] {
        var out: [FirstRunSuggestion212A] = []
        var seenTeamIds: Set<Int> = []
        for result in results {
            let variants = (result.sports ?? []).filter { !($0.sportKey ?? "").isEmpty }
            if variants.count > 1 {
                for variant in variants {
                    guard seenTeamIds.insert(variant.id).inserted else { continue }
                    let label = nonEmpty(variant.sportDisplay) ?? sportDisplayName(for: variant.sportKey)
                    let resolvedLabel = label.isEmpty ? "Team" : label
                    out.append(FirstRunSuggestion212A(
                        id: "team:\(variant.id)",
                        name: result.name,
                        sportOrCategoryLabel: resolvedLabel,
                        contextLine: contextHint ?? result.location,
                        logoUrl: result.logoUrl,
                        primaryColorHex: nil,
                        teamId: variant.id,
                        sportKey: variant.sportKey,
                        followedSubject: FollowedSubject295A.team(
                            slug: "\(variant.id)",
                            teamId: variant.id,
                            name: result.name,
                            sportKey: variant.sportKey,
                            logoUrl: result.logoUrl
                        ),
                        affinityCategory: DiscoverCategory.token(forSport: variant.sportKey)
                    ))
                }
            } else {
                guard seenTeamIds.insert(result.id).inserted else { continue }
                let key = result.sportKey ?? result.sports?.first?.sportKey
                let rawDisplay = nonEmpty(result.sports?.first?.sportDisplay) ?? sportDisplayName(for: key)
                let resolvedLabel = rawDisplay.isEmpty ? "Team" : rawDisplay
                out.append(FirstRunSuggestion212A(
                    id: "team:\(result.id)",
                    name: result.name,
                    sportOrCategoryLabel: resolvedLabel,
                    contextLine: contextHint ?? result.location,
                    logoUrl: result.logoUrl,
                    primaryColorHex: nil,
                    teamId: result.id,
                    sportKey: key,
                    followedSubject: FollowedSubject295A.team(
                        slug: "\(result.id)",
                        teamId: result.id,
                        name: result.name,
                        sportKey: key,
                        logoUrl: result.logoUrl
                    ),
                    affinityCategory: DiscoverCategory.token(forSport: key)
                ))
            }
        }
        return out
    }

    /// Expands `/api/events/search` response (`teams`, `collections`, and matching subjects).
    static func fromEventSearchResponse(
        _ response: SearchResponse,
        query: String
    ) -> [FirstRunSuggestion212A] {
        var out: [FirstRunSuggestion212A] = []

        // 1. Teams from global search (catches clubs that location/team search misses).
        for team in response.teams ?? [] {
            let label = sportDisplayName(for: team.sportKey)
            let resolvedLabel = label.isEmpty ? "Team" : label
            out.append(FirstRunSuggestion212A(
                id: "team:\(team.id)",
                name: team.name,
                sportOrCategoryLabel: resolvedLabel,
                contextLine: nonEmpty(team.record),
                logoUrl: team.logo,
                primaryColorHex: nil,
                teamId: team.id,
                sportKey: team.sportKey,
                followedSubject: FollowedSubject295A.team(
                    slug: nonEmpty(team.slug) ?? "\(team.id)",
                    teamId: team.id,
                    name: team.name,
                    sportKey: team.sportKey,
                    logoUrl: team.logo,
                    primaryColor: nil
                ),
                affinityCategory: DiscoverCategory.token(forSport: team.sportKey)
            ))
        }

        // 2. Curated collections/sets matched by query.
        if let collections = response.collectionDiscovery?.collections {
            for col in collections.prefix(4) {
                let title = nonEmpty(col.name) ?? col.slug
                let count = col.gameCount + col.questionCount
                let countText = count > 0 ? "\(count) items" : nonEmpty(col.text)
                out.append(FirstRunSuggestion212A(
                    id: "set:\(col.slug)",
                    name: title,
                    sportOrCategoryLabel: "Set",
                    contextLine: countText,
                    logoUrl: nil,
                    primaryColorHex: nil,
                    teamId: nil,
                    sportKey: nil,
                    followedSubject: FollowedSubject295A.set(slug: col.slug, setKind: .container, name: title),
                    affinityCategory: nil
                ))
            }
        }

        // 3. Matching curated subjects (politics, awards, economy, weather, tech, chess, TV).
        let q = query.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
        if !q.isEmpty {
            for topic in Self.subjectDirectory where topic.keywords.contains(where: { $0.contains(q) || q.contains($0) }) {
                out.append(topic.suggestion)
            }
        }

        return mergeDeduplicating(out)
    }

    static func mergeDeduplicating(_ lists: [FirstRunSuggestion212A]) -> [FirstRunSuggestion212A] {
        var seen: Set<String> = []
        var out: [FirstRunSuggestion212A] = []
        for item in lists {
            if seen.insert(item.id).inserted {
                out.append(item)
            }
        }
        return out
    }

    static let popularQueries: [String] = [
        "Boston",
        "New York",
        "Texas",
        "Oscars",
        "Economy",
        "Weather",
        "Premier League",
    ]

    struct TopicEntry: Sendable {
        let keywords: [String]
        let suggestion: FirstRunSuggestion212A
    }

    static let subjectDirectory: [TopicEntry] = [
        TopicEntry(
            keywords: ["oscar", "oscars", "movie", "movies", "film", "entertainment", "grammy", "tv"],
            suggestion: FirstRunSuggestion212A(
                id: "set:machinery-oscars-best-actor-2027",
                name: "Oscars & Entertainment",
                sportOrCategoryLabel: "Entertainment · Set",
                contextLine: "Awards & film forecasts",
                logoUrl: nil,
                primaryColorHex: "#B45309",
                teamId: nil,
                sportKey: "entertainment",
                followedSubject: FollowedSubject295A.set(slug: "machinery-oscars-best-actor-2027", setKind: .container, name: "Oscars 2027"),
                affinityCategory: "entertainment"
            )
        ),
        TopicEntry(
            keywords: ["economy", "fed", "inflation", "rates", "cpi", "recession", "economics", "jobs"],
            suggestion: FirstRunSuggestion212A(
                id: "set:machinery-fed-and-macro",
                name: "Fed & Economy",
                sportOrCategoryLabel: "Economics · Set",
                contextLine: "Rates, inflation & jobs",
                logoUrl: nil,
                primaryColorHex: "#005CC2",
                teamId: nil,
                sportKey: "economics",
                followedSubject: FollowedSubject295A.set(slug: "machinery-fed-and-macro", setKind: .container, name: "Fed & Macro"),
                affinityCategory: "economics"
            )
        ),
        TopicEntry(
            keywords: ["weather", "climate", "rain", "storm", "hurricane", "quake", "temperature"],
            suggestion: FirstRunSuggestion212A(
                id: "set:machinery-climate-water-and-energy",
                name: "Weather & Climate",
                sportOrCategoryLabel: "Weather · Set",
                contextLine: "Storms, temperature & energy",
                logoUrl: nil,
                primaryColorHex: "#0284C7",
                teamId: nil,
                sportKey: "weather",
                followedSubject: FollowedSubject295A.set(slug: "machinery-climate-water-and-energy", setKind: .container, name: "Weather & Climate"),
                affinityCategory: "weather"
            )
        ),
        TopicEntry(
            keywords: ["ai", "tech", "openai", "google", "space", "spacex", "science"],
            suggestion: FirstRunSuggestion212A(
                id: "set:machinery-tech-and-space-movers",
                name: "Tech, AI & Space",
                sportOrCategoryLabel: "Tech · Set",
                contextLine: "AI rankings & SpaceX milestones",
                logoUrl: nil,
                primaryColorHex: "#6D28D9",
                teamId: nil,
                sportKey: "tech",
                followedSubject: FollowedSubject295A.set(slug: "machinery-tech-and-space-movers", setKind: .container, name: "Tech & Space Movers"),
                affinityCategory: "tech"
            )
        ),
        TopicEntry(
            keywords: ["politics", "election", "president", "senate", "congress", "house", "governor"],
            suggestion: FirstRunSuggestion212A(
                id: "topic:politics",
                name: "US Politics & Elections",
                sportOrCategoryLabel: "Politics · Subject",
                contextLine: "Elections, policy & Congress",
                logoUrl: nil,
                primaryColorHex: "#DC2626",
                teamId: nil,
                sportKey: "politics",
                followedSubject: FollowedSubject295A.set(slug: "machinery-2028-presidential", setKind: .container, name: "US Politics"),
                affinityCategory: "politics"
            )
        ),
        TopicEntry(
            keywords: ["premier league", "epl", "soccer", "champions league", "arsenal", "liverpool"],
            suggestion: FirstRunSuggestion212A(
                id: "league:soccer_epl",
                name: "Premier League",
                sportOrCategoryLabel: "Soccer · League",
                contextLine: "Fixtures, title race & relegation",
                logoUrl: nil,
                primaryColorHex: "#3D195B",
                teamId: nil,
                sportKey: "soccer_epl",
                followedSubject: FollowedSubject295A.league(slug: "soccer_epl", sportKey: "soccer_epl", name: "Premier League"),
                affinityCategory: "soccer"
            )
        ),
    ]

    private static func nonEmpty(_ value: String?) -> String? {
        guard let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines), !trimmed.isEmpty else {
            return nil
        }
        return trimmed
    }
}

/// First-run persistent state keys shared across Step 1, Step 2, Step 5, and launch deferral.
nonisolated enum FirstRunStorageKeys212A {
    static let onboardedKey = "discover_onboarded"
    static let localInterestsKey = "bainluck_first_run_interests_212a"
    static let earnedSignInDismissedKey = "bainluck_earned_signin_dismissed_212a"
}
