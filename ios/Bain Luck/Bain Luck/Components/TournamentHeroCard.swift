import SwiftUI

nonisolated struct TournamentHeroCard: View {
    let tournament: GolfTournamentData

    /// The instant the round strip is read against, captured when the card is
    /// built. Defaulted, so no call site passes it; a guard passes it because
    /// the alternative is asserting against whatever today happens to be, which
    /// is a test that changes its mind four times a tournament (gotcha #44).
    var now: Date = Date()

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 4) {
                    Text(properTitleCase(tournament.name))
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
    ///
    /// Counted in whole calendar days from the day `start_date` NAMES, not in
    /// elapsed hours from the UTC midnight it is written as (#6666). The old
    /// arithmetic subtracted two instants, so west of UTC it rolled over at
    /// 17:00 local: R1 lit the evening before the tournament began, and every
    /// round afterwards changed seven hours early — beside a date range that
    /// was itself a day out, so the two wrongs agreed and neither looked like a
    /// bug. `tournamentRoundNumber` reads the reader's own calendar for "today",
    /// which is the thing a round number is actually about, and holds the rule
    /// where a guard can state the instant it is asking about — inside this
    /// body, `Date()` can only be tested against whatever today happens to be.
    ///
    /// `roundCount` defaults to the four rounds `roundProgressView` draws.
    var currentRound: Int? {
        tournamentRoundNumber(start: tournament.startDate, now: now)
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

    var formattedDateRange: String? {
        // Uses the shared acronym/ISO-aware formatter so full ISO timestamps
        // ("2026-09-24T00:00:00+00:00") render as "Sep 24-27", never raw.
        formatDateRange(start: tournament.startDate, end: tournament.endDate)
    }
}
