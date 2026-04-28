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

    private var homeSeriesProb: Double {
        Self.computeSeriesWinProb(
            teamWinProb: homeWinProb,
            teamWon: homeSeriesWins,
            oppWon: awaySeriesWins,
            gamesToWin: gamesToWin
        )
    }

    private var awaySeriesProb: Double { 1.0 - homeSeriesProb }

    private var stateLabel: String {
        let name = homeTeam.split(separator: " ").last.map(String.init) ?? homeTeam
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
                HStack {
                    Text("Series Probability")
                        .font(.subheadline)
                        .fontWeight(.semibold)
                    Spacer()
                    Text("Best of \(gamesToWin * 2 - 1)")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }

                Text(stateLabel)
                    .font(.caption)
                    .foregroundStyle(.secondary)

                // Win dots
                HStack {
                    HStack(spacing: 4) {
                        Text(homeTeam.split(separator: " ").last.map(String.init) ?? homeTeam)
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
                        Text(awayTeam.split(separator: " ").last.map(String.init) ?? awayTeam)
                            .font(.caption2)
                            .foregroundStyle(awayTeamColor)
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
                .frame(height: 24)
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
