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
                        HStack(spacing: 4) {
                            Image(systemName: "mappin.circle.fill")
                                .font(.system(size: 11))
                                .foregroundStyle(.mint.opacity(0.7))
                            Text(venue)
                                .font(.subheadline)
                                .foregroundStyle(.secondary)
                        }
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

            // Round progress + date range
            HStack(spacing: 10) {
                if let dateRange = formattedDateRange {
                    HStack(spacing: 4) {
                        Image(systemName: "calendar")
                            .font(.system(size: 10))
                        Text(dateRange)
                            .font(.caption)
                    }
                    .foregroundStyle(.secondary)
                }
                Spacer()
                roundProgressView
            }

            if !tournament.golfers.isEmpty {
                Divider()
                VStack(spacing: 6) {
                    ForEach(Array(tournament.golfers.prefix(5).enumerated()), id: \.element.id) { index, golfer in
                        HStack(spacing: 8) {
                            if let rank = golfer.rank {
                                Text("\(rank)")
                                    .font(.caption2)
                                    .fontWeight(.bold)
                                    .frame(width: 20, alignment: .trailing)
                                    .foregroundStyle(index == 0 ? .orange : .secondary)
                            }
                            Text(golfer.name)
                                .font(.subheadline)
                                .fontWeight(index == 0 ? .semibold : .medium)
                            if let movement = golfer.movement24h, abs(movement) >= 0.005 {
                                HStack(spacing: 1) {
                                    Image(systemName: movement > 0 ? "arrow.up" : "arrow.down")
                                        .font(.system(size: 7))
                                    Text(String(format: "%.1f", abs(movement * 100)))
                                        .font(.system(size: 9))
                                }
                                .foregroundStyle(movement > 0 ? .green : .red)
                            }
                            Spacer()
                            Text(String(format: "%.1f%%", golfer.probability * 100))
                                .font(.subheadline)
                                .fontWeight(.semibold)
                                .monospacedDigit()
                                .foregroundStyle(index == 0 ? .blue : .secondary)
                        }
                    }
                }
            }
        }
        .padding(14)
        .background(Color.systemGray6.opacity(0.7))
        .clipShape(RoundedRectangle(cornerRadius: 12))
    }

    // MARK: - Round Progress

    /// Determine the current round number based on tournament dates.
    /// Returns 1-4 based on which day of the tournament we're in, or nil if unknown.
    private var currentRound: Int? {
        guard let startStr = tournament.startDate,
              let startDate = parseSimpleDate(startStr) else { return nil }
        let now = Date()
        let daysSinceStart = Calendar.current.dateComponents([.day], from: startDate, to: now).day ?? 0
        guard daysSinceStart >= 0 && daysSinceStart < 4 else { return nil }
        return daysSinceStart + 1
    }

    @ViewBuilder
    private var roundProgressView: some View {
        if let round = currentRound {
            HStack(spacing: 4) {
                ForEach(1...4, id: \.self) { r in
                    RoundedRectangle(cornerRadius: 2)
                        .fill(r <= round ? Color.mint : Color.secondary.opacity(0.2))
                        .frame(width: 18, height: 4)
                        .overlay(
                            Text("R\(r)")
                                .font(.system(size: 7, weight: .bold))
                                .foregroundStyle(r <= round ? .mint : .secondary.opacity(0.5))
                                .offset(y: -8)
                        )
                }
            }
        }
    }

    private var formattedDateRange: String? {
        guard let start = tournament.startDate, let end = tournament.endDate else { return nil }
        return "\(start) \u{2013} \(end)"
    }

    /// Parse a simple date string like "2026-05-08" or "May 8, 2026".
    private func parseSimpleDate(_ str: String) -> Date? {
        // Try ISO format first
        let isoFormatter = DateFormatter()
        isoFormatter.dateFormat = "yyyy-MM-dd"
        if let d = isoFormatter.date(from: str) { return d }
        // Try natural format
        let naturalFormatter = DateFormatter()
        naturalFormatter.dateFormat = "MMM d, yyyy"
        return naturalFormatter.date(from: str)
    }
}
