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
                            .background(Color.gray.opacity(0.15))
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
        TeamShortName.short(homeTeam)
    }

    private var awayShort: String {
        TeamShortName.short(awayTeam)
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

    /// #3273. This was a private fourth copy of period formatting, and on real
    /// data every branch of it was wrong or dead:
    ///
    /// - `p.count > 2` returned the string UNTOUCHED, and ESPN's period embeds the
    ///   clock (`"14:54 - 1st Quarter"`). Joined to `clock` by `timeDisplay`, the
    ///   card read **"14:54 - 1st Quarter · 14:54"** — the clock printed twice.
    ///   Measured 2026-09-05: 144,376 of 175,274 `espn_snapshots` rows carrying
    ///   both (82.4%) have `period` starting with the exact `game_clock`.
    /// - The `Int(p)` arm below it was unreachable: all 175,274 of those rows are
    ///   longer than two characters, so it has never run in production.
    ///
    /// Delegates to the one parser, which yields `"Q1 · 14:54"`.
    private func formatPeriod(_ period: String?) -> String? {
        guard let p = period, !p.isEmpty else { return nil }
        let normalized = PeriodLabel.normalize(p)
        return normalized.isEmpty ? nil : normalized
    }
}
