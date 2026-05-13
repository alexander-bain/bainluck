import SwiftUI

nonisolated struct TournamentCompactRow: View {
    let tournament: GolfTournamentData

    var body: some View {
        HStack(spacing: 10) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 4) {
                    Text(tournament.name)
                        .font(.subheadline)
                        .fontWeight(.medium)
                        .foregroundStyle(.primary)

                    if tournament.isMajor == true {
                        Text("MAJOR")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(.yellow)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.yellow.opacity(0.15))
                            .clipShape(RoundedRectangle(cornerRadius: 3))
                    }

                    if let tour = tournament.tourLabel, !tour.isEmpty {
                        Text(tour)
                            .font(.system(size: 8, weight: .medium))
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 4)
                            .padding(.vertical, 1)
                            .background(Color.secondary.opacity(0.08))
                            .clipShape(RoundedRectangle(cornerRadius: 3))
                    }
                }

                HStack(spacing: 6) {
                    if let venue = tournament.venue {
                        Text(venue)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }

                    if let dateRange = formattedDateRange {
                        Text("\u{00B7}")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                        Text(dateRange)
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }
            }

            Spacer()

            if let leader = tournament.golfers.first {
                VStack(alignment: .trailing, spacing: 1) {
                    Text(leader.name.components(separatedBy: " ").last ?? leader.name)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                    Text(String(format: "%.1f%%", leader.probability * 100))
                        .font(.caption)
                        .fontWeight(.semibold)
                        .monospacedDigit()
                        .foregroundStyle(.blue)
                }
            }

            Image(systemName: "chevron.right")
                .font(.caption2)
                .foregroundStyle(.tertiary)
        }
        .padding(.vertical, 8)
    }

    private var formattedDateRange: String? {
        guard let start = tournament.startDate, let end = tournament.endDate else { return nil }
        return "\(start) \u{2013} \(end)"
    }
}
