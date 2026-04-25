import SwiftUI

// MARK: - Tournament Card Variants

enum TournamentCardStyle {
    case hero       // Large with hero probability (Variant 3)
    case compact    // Compact leaderboard (Variant 1)
    case ultraCompact // Single row (Variant 4)
}

// MARK: - Hero Card (Variant 3 — Preferred)

struct TournamentHeroCard: View {
    let tournament: GolfTournamentData
    let leaderboard: [GolfLeaderboardPlayer]?
    let broadcast: String?

    init(tournament: GolfTournamentData, leaderboard: [GolfLeaderboardPlayer]? = nil, broadcast: String? = nil) {
        self.tournament = tournament
        self.leaderboard = leaderboard
        self.broadcast = broadcast
    }

    private var isLive: Bool { tournament.scheduleStatus == "in-progress" }

    private var leader: (name: String, score: String, hole: String, winProb: Double)? {
        if let lb = leaderboard?.first {
            return (lb.name, lb.score, lb.hole, lb.winProb)
        }
        if let g = tournament.golfers.first {
            return (g.name, "—", "—", g.probability * 100)
        }
        return nil
    }

    private var chasers: [(name: String, score: String, hole: String, winProb: Double)] {
        if let lb = leaderboard {
            return lb.dropFirst().prefix(4).map { ($0.name, $0.score, $0.hole, $0.winProb) }
        }
        return tournament.golfers.dropFirst().prefix(4).map { ($0.name, "—", "—", $0.probability * 100) }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header
            HStack(alignment: .top) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 4) {
                        Text("⛳ \(tournament.tourLabel ?? tournament.tour?.uppercased() ?? "Golf")")
                            .font(.caption2)
                            .foregroundStyle(.secondary)

                        if isLive {
                            LiveBadgeView(label: "Round \(tournament.golfers.first?.rank != nil ? "" : "")\(tournament.scheduleStatus == "in-progress" ? "" : "")")
                        }
                    }
                    Text(tournament.name)
                        .font(.subheadline)
                        .fontWeight(.bold)
                }

                Spacer()

                if let bc = broadcast {
                    Text(bc)
                        .font(.system(size: 10, weight: .semibold))
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 3)
                        .background(Color.systemGray6)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }
            .padding(.horizontal, 16)
            .padding(.top, 14)
            .padding(.bottom, 8)

            // Hero probability
            if let l = leader {
                HStack(spacing: 12) {
                    HStack(alignment: .firstTextBaseline, spacing: 0) {
                        Text(String(format: "%.1f", l.winProb))
                            .font(.system(size: 28, weight: .heavy, design: .rounded))
                            .monospacedDigit()
                        Text("%")
                            .font(.system(size: 16, weight: .semibold))
                    }

                    VStack(alignment: .leading, spacing: 1) {
                        Text(l.name)
                            .font(.subheadline)
                            .fontWeight(.semibold)
                        HStack(spacing: 0) {
                            Text("Leader")
                                .foregroundStyle(.secondary)
                            if isLive {
                                Text(" · \(l.score) · \(l.hole)")
                                    .foregroundStyle(.secondary)
                            }
                        }
                        .font(.caption)
                    }
                }
                .padding(.horizontal, 12)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.systemGray6.opacity(0.7))
                .clipShape(RoundedRectangle(cornerRadius: 8))
                .padding(.horizontal, 16)
                .padding(.bottom, 10)
            }

            // Chasers strip
            if !chasers.isEmpty {
                Divider()
                    .padding(.horizontal, 16)

                HStack(spacing: 0) {
                    ForEach(Array(chasers.enumerated()), id: \.offset) { index, chaser in
                        VStack(spacing: 2) {
                            Text(lastName(chaser.name))
                                .font(.caption2)
                                .fontWeight(.medium)
                                .foregroundStyle(.secondary)
                                .lineLimit(1)
                            Text(String(format: "%.1f%%", chaser.winProb))
                                .font(.subheadline)
                                .fontWeight(.bold)
                                .monospacedDigit()
                            if isLive {
                                Text("\(chaser.score) · \(chaser.hole)")
                                    .font(.system(size: 10))
                                    .foregroundStyle(.tertiary)
                            }
                        }
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 8)

                        if index < chasers.count - 1 {
                            Divider()
                        }
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 8)
            }
        }
        .background(Color.systemBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.barTrack, lineWidth: 0.5)
        )
    }
}

// MARK: - Ultra-Compact Card (Variant 4)

struct TournamentCompactRow: View {
    let tournament: GolfTournamentData

    private var isLive: Bool { tournament.scheduleStatus == "in-progress" }

    var body: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(tournament.name)
                        .font(.subheadline)
                        .fontWeight(.bold)
                        .lineLimit(1)
                    if isLive {
                        LiveBadgeView(label: "R\(tournament.golfers.first?.rank ?? 0)")
                    }
                }
                Text([tournament.venue, formatDateRange(tournament.startDate, tournament.endDate)]
                    .compactMap { $0 }.joined(separator: " · "))
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .lineLimit(1)
            }

            Spacer()

            if let leader = tournament.golfers.first {
                VStack(alignment: .trailing, spacing: 1) {
                    Text(lastName(leader.name))
                        .font(.caption)
                        .fontWeight(.medium)
                        .foregroundStyle(.secondary)
                    Text(String(format: "%.1f%%", leader.probability * 100))
                        .font(.title3)
                        .fontWeight(.heavy)
                        .monospacedDigit()
                }
            } else {
                Text("—")
                    .foregroundStyle(.tertiary)
            }
        }
        .padding(.horizontal, 14)
        .padding(.vertical, 10)
        .background(Color.systemBackground)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(
            RoundedRectangle(cornerRadius: 10)
                .stroke(Color.barTrack, lineWidth: 0.5)
        )
    }
}

// MARK: - Live Badge

private struct LiveBadgeView: View {
    let label: String

    var body: some View {
        HStack(spacing: 4) {
            Circle()
                .fill(Color.red)
                .frame(width: 6, height: 6)
            Text(label.isEmpty ? "LIVE" : label)
                .font(.system(size: 10, weight: .semibold))
                .foregroundStyle(.red)
                .textCase(.uppercase)
        }
    }
}

// MARK: - Helpers

private func lastName(_ name: String) -> String {
    let parts = name.split(separator: " ")
    return parts.count > 1 ? String(parts.last!) : name
}

private func formatDateRange(_ start: String?, _ end: String?) -> String? {
    guard let start else { return nil }
    let formatter = DateFormatter()
    formatter.dateFormat = "yyyy-MM-dd"
    guard let sDate = formatter.date(from: String(start.prefix(10))) else { return nil }

    let display = DateFormatter()
    display.dateFormat = "MMM d"
    let sStr = display.string(from: sDate)

    guard let end, let eDate = formatter.date(from: String(end.prefix(10))) else { return sStr }
    let cal = Calendar.current
    if cal.component(.month, from: sDate) == cal.component(.month, from: eDate) {
        return "\(sStr)–\(cal.component(.day, from: eDate))"
    }
    return "\(sStr)–\(display.string(from: eDate))"
}
