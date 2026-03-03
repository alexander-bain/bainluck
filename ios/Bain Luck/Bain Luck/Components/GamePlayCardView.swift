import SwiftUI

/// ESPN-style game play card displayed below the odds chart.
/// Updates as the user scrubs across the chart, showing:
/// - Score (team-colored)
/// - Period and clock
/// - Scoring play description (when hovering over one)
/// - Win probability (when between scoring plays)
struct GamePlayCardView: View {
    let selectedPoint: GamePlayPoint?
    let homeTeam: String
    let awayTeam: String
    var homeTeamColor: Color = .primary
    var awayTeamColor: Color = .primary
    var homeTeamLogo: String?
    var awayTeamLogo: String?
    /// Most recent chart point (shown when not scrubbing)
    var lastPoint: GamePlayPoint?

    private var point: GamePlayPoint? {
        selectedPoint ?? lastPoint
    }

    var body: some View {
        if let point {
            VStack(spacing: 0) {
                Divider()
                    .padding(.bottom, 8)

                HStack(alignment: .top, spacing: 10) {
                    // Time/Period badge
                    if !point.timeDisplay.isEmpty {
                        Text(point.timeDisplay)
                            .font(.caption2)
                            .fontWeight(.medium)
                            .foregroundStyle(.secondary)
                            .padding(.horizontal, 6)
                            .padding(.vertical, 3)
                            .background(Color(.systemGray6))
                            .clipShape(RoundedRectangle(cornerRadius: 4))
                    }

                    // Score
                    if point.hasScore {
                        HStack(spacing: 6) {
                            HStack(spacing: 3) {
                                if let url = homeTeamLogo {
                                    AsyncImage(url: URL(string: url)) { image in
                                        image.resizable().aspectRatio(contentMode: .fit)
                                    } placeholder: {
                                        EmptyView()
                                    }
                                    .frame(width: 14, height: 14)
                                }
                                Text("\(point.homeScore ?? 0)")
                                    .font(.caption)
                                    .fontWeight(.bold)
                                    .monospacedDigit()
                                    .foregroundStyle(homeTeamColor)
                            }
                            Text("-")
                                .font(.caption2)
                                .foregroundStyle(.secondary)
                            HStack(spacing: 3) {
                                Text("\(point.awayScore ?? 0)")
                                    .font(.caption)
                                    .fontWeight(.bold)
                                    .monospacedDigit()
                                    .foregroundStyle(awayTeamColor)
                                if let url = awayTeamLogo {
                                    AsyncImage(url: URL(string: url)) { image in
                                        image.resizable().aspectRatio(contentMode: .fit)
                                    } placeholder: {
                                        EmptyView()
                                    }
                                    .frame(width: 14, height: 14)
                                }
                            }
                        }
                    }

                    // Play description or probability context
                    VStack(alignment: .leading, spacing: 2) {
                        if let play = point.scoringPlay {
                            HStack(spacing: 4) {
                                Circle()
                                    .fill(.red)
                                    .frame(width: 5, height: 5)
                                if let type = play.type {
                                    Text(type)
                                        .font(.caption2)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            Text(play.description ?? play.shortText ?? "")
                                .font(.caption2)
                                .foregroundStyle(.primary)
                                .lineLimit(2)
                        } else {
                            let homeProb = Int((point.homeProb * 100).rounded())
                            let awayProb = Int((point.awayProb * 100).rounded())
                            HStack(spacing: 0) {
                                Text(homeShort)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(" \(homeProb)%")
                                    .font(.caption2)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(homeTeamColor)
                                Text(" — ")
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(awayShort)
                                    .font(.caption2)
                                    .foregroundStyle(.secondary)
                                Text(" \(awayProb)%")
                                    .font(.caption2)
                                    .fontWeight(.semibold)
                                    .foregroundStyle(awayTeamColor)
                            }
                        }
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.top, 8)
        }
    }

    private var homeShort: String {
        homeTeam.split(separator: " ").last.map(String.init) ?? homeTeam
    }

    private var awayShort: String {
        awayTeam.split(separator: " ").last.map(String.init) ?? awayTeam
    }
}

// MARK: - Game Play Point

/// Data model for a single point on the chart with game context.
struct GamePlayPoint {
    let timestamp: String
    let homeProb: Double
    let awayProb: Double
    var homeScore: Int?
    var awayScore: Int?
    var period: String?
    var clock: String?
    var scoringPlay: ScoringPlay?

    var hasScore: Bool {
        homeScore != nil && awayScore != nil
    }

    var timeDisplay: String {
        let periodStr = formatPeriod(period)
        let parts = [periodStr, clock].compactMap { $0?.isEmpty == false ? $0 : nil }
        return parts.joined(separator: " · ")
    }

    private func formatPeriod(_ period: String?) -> String? {
        guard let p = period, !p.isEmpty else { return nil }
        if p.count > 2 { return p }
        if let num = Int(p) {
            return "Q\(num)"
        }
        return p
    }
}
