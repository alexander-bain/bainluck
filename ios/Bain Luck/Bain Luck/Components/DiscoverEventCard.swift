import SwiftUI

// MARK: - Event Card

struct NativeEventDiscoverCard: View {
    let event: FeedEventData
    let feedContext: String?
    let expandedContext: String?
    @Binding var navigationPath: NavigationPath
    var onOpen: (() -> Void)? = nil
    var onContextExpand: (() -> Void)? = nil
    var onContextCollapse: (() -> Void)? = nil

    private var awayColor: Color {
        Color(hex: event.awayTeamData?.primaryColor ?? "#64748b")
    }

    private var homeColor: Color {
        Color(hex: event.homeTeamData?.primaryColor ?? "#2563eb")
    }

    private var eyebrow: String {
        if event.status == "live" { return "LIVE" }
        if event.status == "completed" || event.status == "closed" { return "FINAL" }
        return (event.sportName ?? event.sport ?? "SPORTS").uppercased()
    }

    private var statusText: String {
        if event.status == "live" { return event.espn?.period ?? "LIVE" }
        if event.status == "completed" || event.status == "closed" {
            if let a = event.awayScore, let h = event.homeScore {
                return "F \(a)-\(h)"
            }
            return "Final"
        }
        return "vs"
    }

    private var contextText: String? {
        if let feedContext, !feedContext.isEmpty { return feedContext }
        if let label = event.highlight?.label, !label.isEmpty { return label }
        if let ei = event.ei, let score = ei.score, score >= 60, let label = ei.label {
            return "Excitement Index \(score): \(label)"
        }
        if event.status == "live" { return "Live probability is moving now" }
        return nil
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                HStack(spacing: 6) {
                    if event.status == "live" {
                        Circle()
                            .fill(Color.red)
                            .frame(width: 7, height: 7)
                    }
                    Text(eyebrow)
                        .font(.system(size: 10, weight: .heavy))
                        .tracking(0.8)
                }
                .foregroundStyle(event.status == "live" ? .red : .secondary)

                Spacer()

                Text(statusText)
                    .font(.caption.weight(.bold).monospacedDigit())
                    .foregroundStyle(event.status == "live" ? .red : .secondary)
            }

            HStack(alignment: .center, spacing: 10) {
                teamColumn(
                    name: event.awayTeam,
                    logo: event.awayTeamData?.logoSmall,
                    color: awayColor,
                    probability: event.currentOdds?.awayProbability,
                    score: event.awayScore,
                    alignment: .leading
                )

                Text("vs")
                    .font(.caption.weight(.bold))
                    .foregroundStyle(.secondary)
                    .frame(width: 28)

                teamColumn(
                    name: event.homeTeam,
                    logo: event.homeTeamData?.logoSmall,
                    color: homeColor,
                    probability: event.currentOdds?.homeProbability,
                    score: event.homeScore,
                    alignment: .trailing
                )
            }

            if let hp = event.currentOdds?.homeProbability, let ap = event.currentOdds?.awayProbability {
                probabilityBar(awayProbability: ap, homeProbability: hp)
            }

            if let contextText {
                ExpandableNativeContextText(
                    text: contextText,
                    expandedText: expandedContext,
                    font: .caption,
                    onExpand: onContextExpand,
                    onCollapse: onContextCollapse
                )
            }
        }
        .padding(14)
        .background(Color.cardBackground)
        .clipShape(RoundedRectangle(cornerRadius: 18))
        .overlay(RoundedRectangle(cornerRadius: 18).stroke(Color.barTrack.opacity(0.55), lineWidth: 0.5))
        .shadow(color: .black.opacity(0.06), radius: 10, x: 0, y: 4)
        .contentShape(Rectangle())
        .onTapGesture {
            navigationPath.append(Route.eventDetail(id: event.id))
            onOpen?()
        }
    }

    private func teamColumn(
        name: String,
        logo: String?,
        color: Color,
        probability: Double?,
        score: Int?,
        alignment: HorizontalAlignment
    ) -> some View {
        VStack(alignment: alignment, spacing: 7) {
            if let logo, let url = URL(string: logo) {
                AsyncImage(url: url) { img in img.resizable().scaledToFit() } placeholder: { EmptyView() }
                    .frame(width: 42, height: 42)
            } else {
                RoundedRectangle(cornerRadius: 10)
                    .fill(color)
                    .frame(width: 42, height: 42)
                    .overlay(
                        Text(String(name.split(separator: " ").last ?? "").prefix(3).uppercased())
                            .font(.system(size: 10, weight: .heavy))
                            .foregroundStyle(.white)
                    )
            }

            Text(name)
                .font(.subheadline.weight(.bold))
                .lineLimit(3)
                .fixedSize(horizontal: false, vertical: true)
                .multilineTextAlignment(alignment == .trailing ? .trailing : .leading)
                .frame(maxWidth: .infinity, alignment: alignment == .trailing ? .trailing : .leading)

            HStack(spacing: 6) {
                if let probability {
                    Text(formatProbability(probability))
                        .font(.title3.weight(.black).monospacedDigit())
                        .foregroundStyle(color)
                }
                if let score {
                    Text("\(score)")
                        .font(.caption.weight(.heavy).monospacedDigit())
                        .foregroundStyle(.secondary)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.secondary.opacity(0.10))
                        .clipShape(Capsule())
                }
            }
        }
        .frame(maxWidth: .infinity)
    }

    private func probabilityBar(awayProbability: Double, homeProbability: Double) -> some View {
        GeometryReader { geo in
            HStack(spacing: 0) {
                Rectangle()
                    .fill(awayColor)
                    .frame(width: max(3, geo.size.width * awayProbability))
                Rectangle()
                    .fill(homeColor)
                    .frame(width: max(3, geo.size.width * homeProbability))
            }
            .clipShape(Capsule())
        }
        .frame(height: 8)
        .background(Color.barTrack.opacity(0.25), in: Capsule())
    }
}
