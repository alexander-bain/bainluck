import SwiftUI

struct ChampionshipPathView: View {
    let progression: TeamProgressionResponse
    var homeTeamColor: Color = .blue
    var awayTeamColor: Color = .red

    var body: some View {
        let away = progression.awayTeam
        let home = progression.homeTeam

        if away != nil || home != nil {
            VStack(alignment: .leading, spacing: 12) {
                Text("Championship Path")
                    .font(.headline)
                    .fontWeight(.semibold)

                HStack(alignment: .top, spacing: 12) {
                    if let away {
                        teamPathColumn(team: away, color: awayTeamColor)
                    }
                    if let home {
                        teamPathColumn(team: home, color: homeTeamColor)
                    }
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    private func teamPathColumn(team: TeamProgressionData, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(team.shortName ?? team.name)
                .font(.subheadline)
                .fontWeight(.bold)
                .foregroundStyle(color)

            ForEach(team.stages, id: \.key) { stage in
                stageRow(stage: stage, color: color)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func stageRow(stage: ProgressionStageData, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(stage.label)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Spacer()
                if let trend = stage.trend24h, abs(trend) >= 0.005 {
                    HStack(spacing: 2) {
                        Image(systemName: trend > 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 7, weight: .bold))
                        Text(String(format: "%.1f", abs(trend * 100)))
                            .font(.system(size: 9, weight: .medium))
                    }
                    .foregroundStyle(trend > 0 ? .green : .red)
                }
                if let prob = stage.probability {
                    Text(formatProb(prob))
                        .font(.caption)
                        .fontWeight(.bold)
                        .monospacedDigit()
                        .foregroundStyle(color)
                }
            }

            GeometryReader { geo in
                ZStack(alignment: .leading) {
                    Capsule()
                        .fill(Color.secondary.opacity(0.1))
                    Capsule()
                        .fill(color.opacity(0.6))
                        .frame(width: max(2, geo.size.width * min(1.0, stage.probability ?? 0)))
                }
            }
            .frame(height: 6)
        }
    }

    private func formatProb(_ p: Double) -> String {
        if p >= 0.995 { return ">99%" }
        if p <= 0.005 { return "<1%" }
        return "\(Int((p * 100).rounded()))%"
    }
}
