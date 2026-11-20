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

    private var homeSeriesProb: Double {
        Self.computeSeriesWinProb(
            teamWinProb: homeWinProb,
            teamWon: homeSeriesWins,
            oppWon: awaySeriesWins,
            gamesToWin: gamesToWin
        )
    }

    private var awaySeriesProb: Double { 1.0 - homeSeriesProb }

    /// #3430 — both competitors of one series, so the pair rule decides. Every
    /// sentence below names ONE of them and reports the other's position in the
    /// same breath; a shared label makes "Sox lead 3-2" unreadable.
    private var sides: (away: String, home: String) {
        TeamShortName.shortPair(away: awayTeam, home: homeTeam)
    }

    private var stateLabel: String {
        let name = sides.home
        if homeSeriesWins >= gamesToWin { return "\(name) win series \(homeSeriesWins)-\(awaySeriesWins)" }
        if awaySeriesWins >= gamesToWin { return "\(name) lose series \(homeSeriesWins)-\(awaySeriesWins)" }
        if homeSeriesWins == awaySeriesWins { return "Series tied \(homeSeriesWins)-\(awaySeriesWins)" }
        if homeSeriesWins > awaySeriesWins { return "\(name) lead \(homeSeriesWins)-\(awaySeriesWins)" }
        return "\(name) trail \(homeSeriesWins)-\(awaySeriesWins)"
    }

    private var isSeriesOver: Bool {
        homeSeriesWins >= gamesToWin || awaySeriesWins >= gamesToWin
    }

    var body: some View {
        if isSeriesOver { EmptyView() }
        else {
            VStack(alignment: .leading, spacing: 12) {
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Series Probability")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("Best of \(gamesToWin * 2 - 1)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                } else {
                    HStack {
                        Text("Series Probability")
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        Spacer()
                        Text("Best of \(gamesToWin * 2 - 1)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                }

                Text(stateLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                // Win dots
                if dynamicTypeSize.isAccessibilitySize {
                    VStack(alignment: .leading, spacing: 6) {
                        HStack(spacing: 4) {
                            Text(sides.home)
                                .font(.caption2)
                                .foregroundStyle(homeTeamColor)
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
                        }
                    }
                }

                // Probability bar
                let homePct = Int((homeSeriesProb * 100).rounded())
                let awayPct = 100 - homePct
                GeometryReader { geo in
                    HStack(spacing: 0) {
                        ZStack {
                            RoundedRectangle(cornerRadius: 10)
                                .fill(homeTeamColor)
                            Text("\(homePct)%")
                                .font(.caption2.weight(.bold).monospacedDigit())
                                .foregroundStyle(.white)
                        }
                        .frame(width: geo.size.width * homeSeriesProb)
                        ZStack {
                            RoundedRectangle(cornerRadius: 10)
                                .fill(awayTeamColor)
                            Text("\(awayPct)%")
                                .font(.caption2.weight(.bold).monospacedDigit())
                                .foregroundStyle(.white)
                        }
                        .frame(width: geo.size.width * awaySeriesProb)
                    }
                }
                .frame(height: dynamicTypeSize.isAccessibilitySize ? 48 : 24)
                .clipShape(RoundedRectangle(cornerRadius: 12))

                Text("Based on \(Int((homeWinProb * 100).rounded()))% game win probability via negative binomial model")
                    .font(.system(size: 10))
                    .foregroundStyle(.tertiary)
                    .frame(maxWidth: .infinity)
                    .multilineTextAlignment(.center)
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 12))
        }
    }

    // MARK: - Negative Binomial

    private static func comb(_ n: Int, _ k: Int) -> Double {
        if k < 0 || k > n { return 0 }
        if k == 0 || k == n { return 1 }
        var result: Double = 1
        for i in 0..<k {
            result = result * Double(n - i) / Double(i + 1)
        }
        return result
    }

    static func resolvedMountInputs(
        for event: EventDetail
    ) -> (homeWinProb: Double, homeSeriesWins: Int, awaySeriesWins: Int, gamesToWin: Int)? {
        guard let tags = event.eventTags,
              tags.contains("competitive_structure:series") || tags.contains("competitive_structure:best_of_7") else {
            return nil
        }
        let gamesToWin = 4
        let baseHomeWins = event.espn?.seriesHomeWins ?? 0
        let baseAwayWins = event.espn?.seriesAwayWins ?? 0

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
                homeWins = baseHomeWins + 1
                awayWins = baseAwayWins
            case .away:
                homeWins = baseHomeWins
                awayWins = baseAwayWins + 1
            case .draw, .undecided:
                return nil
            }
            if homeWins >= gamesToWin || awayWins >= gamesToWin {
                return (homeWinProb: outcome == .home ? 1.0 : 0.0, homeSeriesWins: homeWins, awaySeriesWins: awayWins, gamesToWin: gamesToWin)
            }
            guard let pregameHome = PrematchReading.resolve(
                prematch: event.prematchOdds,
                opening: event.openingOdds
            )?.homeProbability else {
                return nil
            }
            return (homeWinProb: pregameHome, homeSeriesWins: homeWins, awaySeriesWins: awayWins, gamesToWin: gamesToWin)
        }

        guard event.heroProbabilitySource != OpeningLineHero.openingSource,
              let homeProb = event.currentOdds?.homeProbability else {
            return nil
        }
        return (homeWinProb: homeProb, homeSeriesWins: baseHomeWins, awaySeriesWins: baseAwayWins, gamesToWin: gamesToWin)
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
