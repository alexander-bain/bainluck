import SwiftUI

nonisolated struct TournamentHeroCard: View {
    let tournament: GolfTournamentData

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(tournament.name)
                        .font(.title3)
                        .fontWeight(.bold)
                        .foregroundStyle(.primary)

                    if let venue = tournament.venue {
                        Text(venue)
                            .font(.subheadline)
                            .foregroundStyle(.secondary)
                    }

                    if let location = tournament.location {
                        Text(location)
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }

                Spacer()

                if tournament.isMajor == true {
                    Text("MAJOR")
                        .font(.system(size: 10, weight: .bold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.yellow.opacity(0.8))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }

            if let dateRange = formattedDateRange {
                Text(dateRange)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if !tournament.golfers.isEmpty {
                Divider()
                VStack(spacing: 6) {
                    ForEach(tournament.golfers.prefix(5)) { golfer in
                        HStack {
                            if let rank = golfer.rank {
                                Text("\(rank)")
                                    .font(.caption2)
                                    .fontWeight(.medium)
                                    .frame(width: 20, alignment: .trailing)
                                    .foregroundStyle(.secondary)
                            }
                            Text(golfer.name)
                                .font(.subheadline)
                                .fontWeight(.medium)
                            Spacer()
                            Text(String(format: "%.1f%%", golfer.probability * 100))
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .foregroundStyle(.blue)
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(Color.systemGray6.opacity(0.7))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    private var formattedDateRange: String? {
        guard let start = tournament.startDate, let end = tournament.endDate else { return nil }
        return "\(start) – \(end)"
    }
}
