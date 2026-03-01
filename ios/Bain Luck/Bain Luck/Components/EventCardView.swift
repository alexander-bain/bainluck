import SwiftUI

/// Status-aware event card matching the web FeedCard layout.
struct EventCardView: View {
    let event: FeedEventData
    let reason: String?
    var personalizationReasons: [String]? = nil
    var headline: String? = nil

    private var isLive: Bool { event.status == "live" }
    private var isFinished: Bool { event.status == "completed" || event.status == "closed" }
    private var isScheduled: Bool { event.status == "scheduled" || (!isLive && !isFinished) }

    private var awayWon: Bool { isFinished && (event.awayScore ?? 0) > (event.homeScore ?? 0) }
    private var homeWon: Bool { isFinished && (event.homeScore ?? 0) > (event.awayScore ?? 0) }

    private var awayColor: Color { Color(hex: event.awayTeamData?.primaryColor ?? "#6b7280") }
    private var homeColor: Color { Color(hex: event.homeTeamData?.primaryColor ?? "#6b7280") }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            topBar
            teamsAndOdds
            footer
        }
        .padding(.vertical, 6)
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack(spacing: 6) {
            Text(event.sportName ?? sportDisplayName(for: event.sport))
                .font(.caption)
                .foregroundStyle(.secondary)
            StatusBadge(status: event.status)
            if let ei = event.ei ?? event.pulse {
                EIBadgeView(ei: ei, size: .sm)
            }
            if let badge = personalizationBadge {
                badge
            }
            if let headline, !headline.isEmpty {
                Text(headline)
                    .font(.caption2)
                    .fontWeight(.semibold)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(.blue.opacity(0.12))
                    .foregroundStyle(.blue)
                    .clipShape(Capsule())
            }
            Spacer()
            PinButton(type: "event", id: event.id)
            if isScheduled || isFinished {
                RelativeTimeText(dateString: event.commenceTime)
            }
        }
    }

    // MARK: - Personalization Badge

    private var personalizationBadge: AnyView? {
        guard let reasons = personalizationReasons, !reasons.isEmpty else { return nil }
        // Parse first matching reason from "your_team:0.80" format
        for reason in reasons {
            let key = reason.split(separator: ":").first.map(String.init) ?? reason
            switch key {
            case "your_team":
                return AnyView(badgeCapsule(text: "Your Team", color: .blue))
            case "local":
                return AnyView(badgeCapsule(text: "Local", color: .green))
            case "alma_mater":
                return AnyView(badgeCapsule(text: "Alma Mater", color: .purple))
            case "rival_losing":
                return AnyView(badgeCapsule(text: "Rival Losing", color: .orange))
            default:
                continue
            }
        }
        return nil
    }

    private func badgeCapsule(text: String, color: Color) -> some View {
        Text(text)
            .font(.caption2)
            .fontWeight(.semibold)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(color.opacity(0.12))
            .foregroundStyle(color)
            .clipShape(Capsule())
    }

    // MARK: - Teams + Odds (with inline scores)

    private var teamsAndOdds: some View {
        VStack(spacing: 6) {
            // Away team row
            HStack(spacing: 8) {
                TeamLogoView(
                    url: event.awayTeamData?.logoSmall,
                    teamName: event.awayTeam,
                    color: awayColor,
                    size: 24
                )
                Text(event.awayTeam)
                    .font(.subheadline)
                    .fontWeight(awayWon ? .bold : .medium)
                    .foregroundStyle(awayWon ? .primary : (isFinished ? .secondary : .primary))
                    .lineLimit(1)
                if let record = event.awayTeamData?.record, !isFinished {
                    Text(record)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if isLive || isFinished, let score = event.awayScore {
                    Text("\(score)")
                        .font(.subheadline.monospacedDigit())
                        .fontWeight(awayWon ? .bold : .regular)
                        .foregroundStyle(awayWon ? .primary : .secondary)
                }
                if !isFinished {
                    probabilityText(for: .away)
                }
            }

            // Probability bar
            probabilityBar

            // Home team row
            HStack(spacing: 8) {
                TeamLogoView(
                    url: event.homeTeamData?.logoSmall,
                    teamName: event.homeTeam,
                    color: homeColor,
                    size: 24
                )
                Text(event.homeTeam)
                    .font(.subheadline)
                    .fontWeight(homeWon ? .bold : .medium)
                    .foregroundStyle(homeWon ? .primary : (isFinished ? .secondary : .primary))
                    .lineLimit(1)
                if let record = event.homeTeamData?.record, !isFinished {
                    Text(record)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
                if isLive || isFinished, let score = event.homeScore {
                    Text("\(score)")
                        .font(.subheadline.monospacedDigit())
                        .fontWeight(homeWon ? .bold : .regular)
                        .foregroundStyle(homeWon ? .primary : .secondary)
                }
                if !isFinished {
                    probabilityText(for: .home)
                }
            }
        }
    }

    // MARK: - Footer

    @ViewBuilder
    private var footer: some View {
        HStack {
            if let reason, !reason.isEmpty {
                Text(reason)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer()
            if isLive, let opening = event.openingOdds,
               let awayOpen = opening.awayProbability,
               let homeOpen = opening.homeProbability {
                Text("Opened \(formatProbability(awayOpen))/\(formatProbability(homeOpen))")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            } else if isFinished, let opening = event.openingOdds,
                      let awayOpen = opening.awayProbability,
                      let homeOpen = opening.homeProbability {
                Text("Pre-game: \(formatProbability(awayOpen))/\(formatProbability(homeOpen))")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    // MARK: - Helpers

    private enum TeamSide { case home, away }

    @ViewBuilder
    private func probabilityText(for side: TeamSide) -> some View {
        let odds = event.currentOdds
        let prob: Double? = side == .home ? odds?.homeProbability : odds?.awayProbability
        if let prob {
            Text(formatProbability(prob))
                .font(.subheadline)
                .fontWeight(.semibold)
                .foregroundStyle(side == .home ? homeColor : awayColor)
        }
    }

    @ViewBuilder
    private var probabilityBar: some View {
        if isFinished {
            // Finished: show opening odds bar
            if let opening = event.openingOdds,
               let awayProb = opening.awayProbability,
               let homeProb = opening.homeProbability {
                ProbabilityBar(
                    awayProb: awayProb,
                    homeProb: homeProb,
                    awayColor: awayColor.opacity(0.5),
                    homeColor: homeColor.opacity(0.5),
                    height: 6
                )
            }
        } else {
            // Live / Scheduled: show current odds bar
            if let away = event.currentOdds?.awayProbability,
               let home = event.currentOdds?.homeProbability {
                ProbabilityBar(
                    awayProb: away,
                    homeProb: home,
                    awayColor: awayColor,
                    homeColor: homeColor
                )
            }
        }
    }
}
