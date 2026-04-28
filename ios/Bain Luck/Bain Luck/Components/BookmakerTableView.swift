import SwiftUI

struct BookmakerTableView: View {
    let bookmakers: [BookmakerOdds]
    let homeTeam: String
    let awayTeam: String
    let homeColor: Color
    let awayColor: Color

    var body: some View {
        VStack(spacing: 0) {
            // Header row
            HStack(spacing: 6) {
                Text("Sportsbook")
                    .frame(width: 90, alignment: .leading)
                Spacer()
                Text(String(awayTeam.split(separator: " ").last ?? ""))
                    .frame(width: 40, alignment: .trailing)
                Text(String(homeTeam.split(separator: " ").last ?? ""))
                    .frame(width: 40, alignment: .trailing)
            }
            .font(.system(size: 10, weight: .semibold))
            .foregroundStyle(.secondary)
            .padding(.horizontal, 12)
            .padding(.vertical, 6)

            Divider()

            ForEach(bookmakers.prefix(10), id: \.bookmaker) { bm in
                let awayProb = bm.awayProbability ?? bm.awayMoneyline.map { moneylineToProbability($0) }
                let homeProb = bm.homeProbability ?? bm.homeMoneyline.map { moneylineToProbability($0) }

                HStack(spacing: 6) {
                    Text(bm.bookmaker ?? "Unknown")
                        .font(.caption)
                        .lineLimit(1)
                        .frame(width: 90, alignment: .leading)

                    if let ap = awayProb, let hp = homeProb {
                        ProbabilityBar(
                            awayProb: ap, homeProb: hp,
                            awayColor: awayColor, homeColor: homeColor,
                            height: 6
                        )

                        Text(formatProbability(ap))
                            .font(.caption2.monospacedDigit())
                            .frame(width: 40, alignment: .trailing)
                        Text(formatProbability(hp))
                            .font(.caption2.monospacedDigit())
                            .frame(width: 40, alignment: .trailing)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 4)
            }

            // Consensus row
            let allAway = bookmakers.compactMap { $0.awayProbability ?? $0.awayMoneyline.map { moneylineToProbability($0) } }
            let allHome = bookmakers.compactMap { $0.homeProbability ?? $0.homeMoneyline.map { moneylineToProbability($0) } }
            if !allAway.isEmpty {
                Divider()
                let avgAway = allAway.reduce(0, +) / Double(allAway.count)
                let avgHome = allHome.reduce(0, +) / Double(allHome.count)
                HStack(spacing: 6) {
                    Text("Consensus")
                        .font(.caption)
                        .fontWeight(.semibold)
                        .frame(width: 90, alignment: .leading)

                    ProbabilityBar(
                        awayProb: avgAway, homeProb: avgHome,
                        awayColor: awayColor, homeColor: homeColor,
                        height: 6
                    )

                    Text(formatProbability(avgAway))
                        .font(.caption2.weight(.semibold).monospacedDigit())
                        .frame(width: 40, alignment: .trailing)
                    Text(formatProbability(avgHome))
                        .font(.caption2.weight(.semibold).monospacedDigit())
                        .frame(width: 40, alignment: .trailing)
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 6)
            }
        }
        .padding(.vertical, 4)
    }
}
