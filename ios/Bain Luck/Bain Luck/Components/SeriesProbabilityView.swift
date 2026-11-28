import SwiftUI

struct SeriesProbabilityView: View {
    let homeWinProb: Double
    let homeSeriesWins: Int
    let awaySeriesWins: Int
    var gamesToWin: Int = 4
    let homeTeam: String
    let awayTeam: String
    let homeTeamColor: Color
    let awayTeamColor: Color
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    var homeSeriesProb: Double {
        Self.computeSeriesWinProb(
            teamWinProb: homeWinProb,
            teamWon: homeSeriesWins,
            oppWon: awaySeriesWins,
            gamesToWin: gamesToWin
        )
    }

    var awaySeriesProb: Double { 1.0 - homeSeriesProb }

    /// #3430 — both competitors of one series, so the pair rule decides. Every
    /// sentence below names ONE of them and reports the other's position in the
    /// same breath; a shared label makes "Sox lead 3-2" unreadable.
    private var sides: (away: String, home: String) {
        TeamShortName.shortPair(away: awayTeam, home: homeTeam)
    }

    var stateLabel: String {
        if homeSeriesWins >= gamesToWin {
            return "\(sides.home) win series \(homeSeriesWins)–\(awaySeriesWins)"
        }
        if awaySeriesWins >= gamesToWin {
            return "\(sides.away) win series \(awaySeriesWins)–\(homeSeriesWins)"
        }
        if homeSeriesWins == awaySeriesWins {
            return "Series tied \(homeSeriesWins)–\(awaySeriesWins)"
        }
        if homeSeriesWins > awaySeriesWins {
            return "\(sides.home) lead \(homeSeriesWins)–\(awaySeriesWins)"
        }
        return "\(sides.home) trail \(homeSeriesWins)–\(awaySeriesWins)"
    }

    var isSeriesOver: Bool {
        homeSeriesWins >= gamesToWin || awaySeriesWins >= gamesToWin
    }

    private var headerTitle: String {
        isSeriesOver ? "Series Result" : "Series Probability"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 2) {
                    Text(headerTitle)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .fixedSize(horizontal: false, vertical: true)
                    Text("Best of \(gamesToWin * 2 - 1)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            } else {
                HStack {
                    Text(headerTitle)
                        .font(.subheadline)
                        .fontWeight(.semibold)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer()
                    Text("Best of \(gamesToWin * 2 - 1)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }

            Text(stateLabel)
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)

            // Win dots
            if dynamicTypeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(spacing: 4) {
                        Text(sides.home)
                            .font(.caption2)
                            .foregroundStyle(homeTeamColor)
                            .fixedSize(horizontal: false, vertical: true)
                        ForEach(0..<gamesToWin, id: \.self) { i in
                            Circle()
                                .strokeBorder(homeTeamColor, lineWidth: 2)
                                .background(Circle().fill(i < homeSeriesWins ? homeTeamColor : .clear))
                                .frame(width: 12, height: 12)
                        }
                    }
                    HStack(spacing: 4) {
                        Text(sides.away)
                            .font(.caption2)
                            .foregroundStyle(awayTeamColor)
                            .fixedSize(horizontal: false, vertical: true)
                        ForEach(0..<gamesToWin, id: \.self) { i in
                            Circle()
                                .strokeBorder(awayTeamColor, lineWidth: 2)
                                .background(Circle().fill(i < awaySeriesWins ? awayTeamColor : .clear))
                                .frame(width: 12, height: 12)
                        }
                    }
                }
            } else {
                HStack {
                    HStack(spacing: 4) {
                        Text(sides.home)
                            .font(.caption2)
                            .foregroundStyle(homeTeamColor)
                            .lineLimit(1)
                        ForEach(0..<gamesToWin, id: \.self) { i in
                            Circle()
                                .strokeBorder(homeTeamColor, lineWidth: 2)
                                .background(Circle().fill(i < homeSeriesWins ? homeTeamColor : .clear))
                                .frame(width: 12, height: 12)
                        }
                    }
                    Spacer()
                    HStack(spacing: 4) {
                        ForEach(0..<gamesToWin, id: \.self) { i in
                            Circle()
                                .strokeBorder(awayTeamColor, lineWidth: 2)
                                .background(Circle().fill(i < awaySeriesWins ? awayTeamColor : .clear))
                                .frame(width: 12, height: 12)
                        }
                        Text(sides.away)
                            .font(.caption2)
                            .foregroundStyle(awayTeamColor)
                            .lineLimit(1)
                    }
                }
            }

            // Probability / clinched bar
            let labels = Self.barLabels(
                homeSeriesProb: homeSeriesProb,
                homeTeam: sides.home,
                awayTeam: sides.away,
                isSeriesOver: isSeriesOver,
                homeClinched: isSeriesOver && homeSeriesWins >= gamesToWin,
                awayClinched: isSeriesOver && awaySeriesWins >= gamesToWin
            )
            GeometryReader { geo in
                if let clinchedLabel = labels.clinched {
                    ZStack {
                        RoundedRectangle(cornerRadius: 10)
                            .fill(homeSeriesWins >= gamesToWin ? homeTeamColor : awayTeamColor)
                        Text(clinchedLabel)
                            .font(.caption2.weight(.bold).monospacedDigit())
                            .foregroundStyle(.white)
                            .lineLimit(1)
                    }
                    .frame(width: geo.size.width)
                } else {
                    let clampedHomeShare = min(max(homeSeriesProb, 0.14), 0.86)
                    HStack(spacing: 0) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 10)
                                .fill(homeTeamColor)
                            Text(labels.home)
                                .font(.caption2.weight(.bold).monospacedDigit())
                                .foregroundStyle(.white)
                                .lineLimit(1)
                        }
                        .frame(width: geo.size.width * clampedHomeShare)
                        ZStack {
                            RoundedRectangle(cornerRadius: 10)
                                .fill(awayTeamColor)
                            Text(labels.away)
                                .font(.caption2.weight(.bold).monospacedDigit())
                                .foregroundStyle(.white)
                                .lineLimit(1)
                        }
                        .frame(width: geo.size.width * (1.0 - clampedHomeShare))
                    }
                }
            }
            .frame(height: dynamicTypeSize.isAccessibilitySize ? 48 : 24)
            .clipShape(RoundedRectangle(cornerRadius: 12))

            if !isSeriesOver {
                Text("Based on \(formatProbability(homeWinProb)) game win probability via negative binomial model")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity)
                    .multilineTextAlignment(.center)
            }
        }
        .padding()
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Negative Binomial & Playoff Series Contract (#13182)

    struct BarLabels: Equatable, Sendable {
        let clinched: String?
        let home: String
        let away: String
    }

    static func barLabels(
        homeSeriesProb: Double,
        homeTeam: String,
        awayTeam: String,
        isSeriesOver: Bool,
        homeClinched: Bool,
        awayClinched: Bool
    ) -> BarLabels {
        if isSeriesOver && homeClinched {
            return BarLabels(clinched: "\(homeTeam) 100%", home: "100%", away: "0%")
        }
        if isSeriesOver && awayClinched {
            return BarLabels(clinched: "\(awayTeam) 100%", home: "0%", away: "100%")
        }
        return BarLabels(
            clinched: nil,
            home: formatProbability(homeSeriesProb),
            away: formatProbability(1.0 - homeSeriesProb)
        )
    }

    private static let playoffRoundTagTokens: Set<String> = [
        "round_1",
        "round_2",
        "conference_semis",
        "conference_finals",
        "nba_finals",
        "stanley_cup",
        "world_series",
        "alcs",
        "nlcs",
        "alds",
        "nlds"
    ]

    static func hasPlayoffSeriesTag(_ tags: [String]) -> Bool {
        for raw in tags {
            let trimmed = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if trimmed == "competitive_structure:series" || trimmed.hasPrefix("competitive_structure:best_of_") {
                return true
            }
            if playoffRoundTagTokens.contains(trimmed) {
                return true
            }
            if let suffix = trimmed.split(separator: ":").last.map(String.init),
               playoffRoundTagTokens.contains(suffix) {
                return true
            }
        }
        return false
    }

    static func resolvedGamesToWin(for event: EventDetail, tags: [String]) -> Int {
        if let bestOf = event.bestOf ?? event.seriesBestOf ?? event.espn?.seriesBestOf,
           bestOf >= 3 {
            return max(1, (bestOf + 1) / 2)
        }
        for raw in tags {
            let lower = raw.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()
            if lower.hasSuffix("best_of_3") { return 2 }
            if lower.hasSuffix("best_of_5") || lower == "alds" || lower == "nlds" || lower.hasSuffix(":alds") || lower.hasSuffix(":nlds") {
                return 3
            }
            if lower.hasSuffix("best_of_7") { return 4 }
        }
        return 4
    }

    private static func comb(_ n: Int, _ k: Int) -> Double {
        if k < 0 || k > n { return 0 }
        if k == 0 || k == n { return 1 }
        var result: Double = 1
        for i in 0..<k {
            result = result * Double(n - i) / Double(i + 1)
        }
        return result
    }

    /// #13182 — requires authoritative series wins (`home_series_wins` / `away_series_wins`
    /// or `espn.series_home_wins` / `espn.series_away_wins`). Withholds (`nil`) whenever
    /// series wins are absent instead of assuming `0–0`, and avoids double-counting a
    /// finished game when `series_wins_include_current_game == true` or the served
    /// series standing has already clinched (`>= gamesToWin`).
    static func resolvedMountInputs(
        for event: EventDetail
    ) -> (homeWinProb: Double, homeSeriesWins: Int, awaySeriesWins: Int, gamesToWin: Int)? {
        guard let tags = event.eventTags, hasPlayoffSeriesTag(tags) else {
            return nil
        }
        guard let rawHomeWins = event.homeSeriesWins ?? event.espn?.seriesHomeWins,
              let rawAwayWins = event.awaySeriesWins ?? event.espn?.seriesAwayWins,
              rawHomeWins >= 0,
              rawAwayWins >= 0 else {
            return nil
        }

        let gamesToWin = resolvedGamesToWin(for: event, tags: tags)
        let winsAlreadyIncludeCurrentGame =
            (event.seriesWinsIncludeCurrentGame ?? event.espn?.seriesWinsIncludeCurrentGame) == true
            || rawHomeWins >= gamesToWin
            || rawAwayWins >= gamesToWin

        if EventState.isFinished(event.status) || event.heroProbabilitySource == "settled" {
            let outcome = EventOutcome.resolve(
                status: event.status,
                homeScore: event.homeScore,
                awayScore: event.awayScore,
                servedResult: event.heroSettledResult
            )
            let homeWins: Int
            let awayWins: Int
            switch outcome {
            case .home:
                homeWins = min(gamesToWin, rawHomeWins + (winsAlreadyIncludeCurrentGame ? 0 : 1))
                awayWins = min(gamesToWin, rawAwayWins)
            case .away:
                homeWins = min(gamesToWin, rawHomeWins)
                awayWins = min(gamesToWin, rawAwayWins + (winsAlreadyIncludeCurrentGame ? 0 : 1))
            case .draw, .undecided:
                if rawHomeWins >= gamesToWin || rawAwayWins >= gamesToWin {
                    homeWins = min(gamesToWin, rawHomeWins)
                    awayWins = min(gamesToWin, rawAwayWins)
                } else {
                    return nil
                }
            }
            if homeWins >= gamesToWin || awayWins >= gamesToWin {
                return (
                    homeWinProb: homeWins >= gamesToWin ? 1.0 : 0.0,
                    homeSeriesWins: homeWins,
                    awaySeriesWins: awayWins,
                    gamesToWin: gamesToWin
                )
            }
            guard let pregameHome = PrematchReading.resolve(
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )?.homeProbability else {
                return nil
            }
            return (
                homeWinProb: pregameHome,
                homeSeriesWins: homeWins,
                awaySeriesWins: awayWins,
                gamesToWin: gamesToWin
            )
        }

        if rawHomeWins >= gamesToWin || rawAwayWins >= gamesToWin {
            return (
                homeWinProb: rawHomeWins >= gamesToWin ? 1.0 : 0.0,
                homeSeriesWins: min(gamesToWin, rawHomeWins),
                awaySeriesWins: min(gamesToWin, rawAwayWins),
                gamesToWin: gamesToWin
            )
        }

        guard event.heroProbabilitySource != OpeningLineHero.openingSource,
              let homeProb = event.currentOdds?.homeProbability else {
            return nil
        }
        return (
            homeWinProb: homeProb,
            homeSeriesWins: rawHomeWins,
            awaySeriesWins: rawAwayWins,
            gamesToWin: gamesToWin
        )
    }

    static func computeSeriesWinProb(teamWinProb: Double, teamWon: Int, oppWon: Int, gamesToWin: Int = 4) -> Double {
        let teamNeeds = gamesToWin - teamWon
        let oppNeeds = gamesToWin - oppWon
        if teamNeeds <= 0 { return 1.0 }
        if oppNeeds <= 0 { return 0.0 }

        let p = max(0, min(1, teamWinProb))
        let totalRemaining = teamNeeds + oppNeeds - 1

        var prob: Double = 0
        for gamesBeforeClinch in (teamNeeds - 1)..<totalRemaining {
            let losses = gamesBeforeClinch - (teamNeeds - 1)
            prob += comb(gamesBeforeClinch, teamNeeds - 1) * pow(p, Double(teamNeeds)) * pow(1 - p, Double(losses))
        }
        return prob
    }
}
