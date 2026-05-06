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

    /// "Today 7:00 PM", "Tomorrow 3:30 PM", or "Mar 8 7:00 PM"
    private var formattedDateTimeString: String? {
        guard let dateStr = event.commenceTime, let date = dateStr.asDate else { return nil }
        let calendar = Calendar.current
        let timeFormatter = DateFormatter()
        timeFormatter.dateFormat = "h:mm a"
        let timeStr = timeFormatter.string(from: date)

        if calendar.isDateInToday(date) {
            return "Today \(timeStr)"
        } else if calendar.isDateInTomorrow(date) {
            return "Tomorrow \(timeStr)"
        } else {
            let dateFormatter = DateFormatter()
            dateFormatter.dateFormat = "MMM d"
            return "\(dateFormatter.string(from: date)) \(timeStr)"
        }
    }

    @ViewBuilder
    private var formattedDateTime: some View {
        if let text = formattedDateTimeString {
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    /// "Mar 5" for finished events
    private var formattedDateString: String? {
        guard let dateStr = event.commenceTime, let date = dateStr.asDate else { return nil }
        let calendar = Calendar.current
        let formatter = DateFormatter()
        if calendar.component(.year, from: date) != calendar.component(.year, from: Date()) {
            formatter.dateFormat = "MMM d, yyyy"
        } else {
            formatter.dateFormat = "MMM d"
        }
        return formatter.string(from: date)
    }

    @ViewBuilder
    private var formattedDate: some View {
        if let text = formattedDateString {
            Text(text)
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            topBar
            teamsAndOdds
            footer
        }
        .padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    // MARK: - Top Bar

    private var topBar: some View {
        HStack(spacing: 6) {
            Text(event.sportName ?? sportDisplayName(for: event.sport))
                .font(.caption)
                .foregroundStyle(.secondary)
            StatusBadge(
                status: event.status,
                commenceTime: event.commenceTime,
                gameClock: event.espn?.gameClock,
                period: event.espn?.period
            )
            if !isFinished, let ei = event.ei ?? event.pulse {
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
            if let broadcast = event.espn?.broadcast?.split(separator: ",").first.map(String.init),
               !broadcast.isEmpty, isScheduled || isLive {
                HStack(spacing: 2) {
                    Image(systemName: "tv")
                        .font(.system(size: 8))
                    Text(broadcast.trimmingCharacters(in: .whitespaces))
                        .font(.caption2)
                }
                .foregroundStyle(.secondary)
                .lineLimit(1)
            }
            if isScheduled {
                // Upcoming: Show "Today 7:00 PM" or "Mar 8 7:00 PM"
                formattedDateTime
            } else if isFinished {
                // Finished: Show date only "Mar 5"
                formattedDate
            }
            PinButton(type: "event", id: event.id, compact: true)
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
            teamRow(
                name: event.awayTeam,
                logo: event.awayTeamData?.logoSmall,
                color: awayColor,
                record: event.awayTeamData?.record,
                score: (isLive || isFinished) ? event.awayScore : nil,
                won: awayWon,
                side: .away
            )

            probabilityBar

            teamRow(
                name: event.homeTeam,
                logo: event.homeTeamData?.logoSmall,
                color: homeColor,
                record: event.homeTeamData?.record,
                score: (isLive || isFinished) ? event.homeScore : nil,
                won: homeWon,
                side: .home
            )
        }
    }

    private func teamRow(name: String, logo: String?, color: Color, record: String?, score: Int?, won: Bool, side: TeamSide) -> some View {
        HStack(spacing: 8) {
            TeamLogoView(
                url: logo,
                teamName: name,
                color: color,
                size: isLive ? 28 : 24,
                sportKey: event.sport
            )
            Text(name)
                .font(.subheadline)
                .fontWeight(won ? .bold : .medium)
                .foregroundStyle(won ? .primary : (isFinished ? .secondary : .primary))
                .lineLimit(1)
            if let record, !isFinished {
                Text(record)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if let score {
                Text("\(score)")
                    .font(isLive ? .title3.monospacedDigit() : .subheadline.monospacedDigit())
                    .fontWeight(isLive ? .bold : (won ? .bold : .regular))
                    .foregroundStyle(isLive ? .primary : (won ? .primary : .secondary))
            }
            if isFinished {
                preGameOddsLabel(for: side)
            } else {
                probabilityWithMovement(for: side)
            }
        }
    }

    // MARK: - Footer

    @ViewBuilder
    private var footer: some View {
        HStack(spacing: 6) {
            if let reason, !reason.isEmpty {
                reasonBadge(reason)
            }
            Spacer()
            if isLive, let opening = event.openingOdds,
               let awayOpen = opening.awayProbability,
               let homeOpen = opening.homeProbability {
                Text("Opened \(formatProbability(awayOpen))/\(formatProbability(homeOpen))")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    private func reasonBadge(_ text: String) -> some View {
        let (icon, color) = reasonStyle(text)
        return HStack(spacing: 3) {
            if let icon {
                Image(systemName: icon)
                    .font(.system(size: 9, weight: .semibold))
            }
            Text(text)
                .font(.caption2)
                .fontWeight(.medium)
        }
        .foregroundStyle(color)
        .padding(.horizontal, 6)
        .padding(.vertical, 3)
        .background(color.opacity(0.1))
        .clipShape(Capsule())
    }

    private func reasonStyle(_ text: String) -> (String?, Color) {
        let lower = text.lowercased()
        if lower.contains("upset") || lower.contains("underdog") {
            return ("exclamationmark.triangle.fill", .orange)
        } else if lower.contains("close") || lower.contains("tight") || lower.contains("even") {
            return ("equal.circle.fill", .blue)
        } else if lower.contains("line mov") || lower.contains("shifted") || lower.contains("odds") {
            return ("arrow.up.arrow.down", .purple)
        } else if lower.contains("starting soon") {
            return ("clock.fill", .green)
        } else if lower.contains("lead change") || lower.contains("wild") || lower.contains("exciting") {
            return ("bolt.fill", .yellow)
        }
        return (nil, .secondary)
    }

    // MARK: - Helpers

    private enum TeamSide { case home, away }

    @ViewBuilder
    private func probabilityWithMovement(for side: TeamSide) -> some View {
        let prob: Double? = side == .home ? event.currentOdds?.homeProbability : event.currentOdds?.awayProbability
        let openProb: Double? = side == .home ? event.openingOdds?.homeProbability : event.openingOdds?.awayProbability
        let color = side == .home ? homeColor : awayColor

        if let prob {
            HStack(spacing: 3) {
                if isLive, let openProb {
                    let shift = prob - openProb
                    if abs(shift) > 0.02 {
                        Image(systemName: shift > 0 ? "arrow.up" : "arrow.down")
                            .font(.system(size: 8, weight: .bold))
                            .foregroundStyle(shift > 0 ? Color.green : Color.red)
                    }
                }
                Text(formatProbability(prob))
                    .font(.subheadline)
                    .fontWeight(.semibold)
                    .foregroundStyle(color)
            }
        }
    }

    /// Shows pre-game odds inline for completed games — dimmed, with "was" prefix for clarity
    @ViewBuilder
    private func preGameOddsLabel(for side: TeamSide) -> some View {
        let opening = event.openingOdds
        let prob: Double? = side == .home ? opening?.homeProbability : opening?.awayProbability
        if let prob {
            let wasUnderdog = prob < 0.4
            let wasHeavyFavorite = prob > 0.7
            let won = (side == .home && homeWon) || (side == .away && awayWon)
            let isUpset = won && wasUnderdog

            HStack(spacing: 2) {
                Text(formatProbability(prob))
                    .font(.caption)
                    .fontWeight(.semibold)
                    .monospacedDigit()
            }
            .foregroundStyle(
                isUpset ? .orange :
                (won && wasHeavyFavorite) ? .secondary :
                .secondary.opacity(0.7)
            )
        }
    }

    @ViewBuilder
    private var probabilityBar: some View {
        if isFinished {
            if let opening = event.openingOdds,
               let awayProb = opening.awayProbability,
               let homeProb = opening.homeProbability {
                ProbabilityBar(
                    awayProb: awayProb,
                    homeProb: homeProb,
                    awayColor: awayColor.opacity(0.5),
                    homeColor: homeColor.opacity(0.5),
                    height: 5
                )
            }
        } else if let away = event.currentOdds?.awayProbability,
                  let home = event.currentOdds?.homeProbability {
            ProbabilityBar(
                awayProb: away,
                homeProb: home,
                awayColor: awayColor,
                homeColor: homeColor,
                height: isLive ? 10 : 8,
                animated: isLive,
                glowing: isLive
            )
        }
    }
}
