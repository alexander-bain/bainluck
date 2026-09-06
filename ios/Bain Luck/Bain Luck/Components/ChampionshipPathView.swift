import SwiftUI

/// Reports the width the two team cards were actually given, so the row layout
/// can be chosen from a measured number instead of a hoped-for one (#3574/#3580).
private struct ChampionshipCardsWidthKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

struct ChampionshipPathView: View {
    let progression: TeamProgressionResponse
    var homeTeamColor: Color = .blue
    var awayTeamColor: Color = .red

    /// The width of the row of team cards, once laid out. Zero until then, which
    /// `ChampionshipRowLayout.stacksBelowLabel` reads as "stack" — the shape that
    /// is safe when the width is not known.
    @State private var cardsWidth: CGFloat = 0

    /// Whether both teams share the same conference/league
    private var sameConference: Bool {
        guard let homeConf = progression.homeTeam?.conference,
              let awayConf = progression.awayTeam?.conference,
              !homeConf.isEmpty, !awayConf.isEmpty else { return false }
        return homeConf.lowercased() == awayConf.lowercased()
    }

    /// Conference keywords for the opposing conference (used to filter irrelevant rows)
    private var opposingConferenceKeywords: [String] {
        // Common conference abbreviation pairs
        let pairs: [[String]] = [
            ["al", "american league", "american"],
            ["nl", "national league", "national"],
            ["afc", "american football conference"],
            ["nfc", "national football conference"],
            ["eastern", "east"],
            ["western", "west"],
        ]
        guard let homeConf = progression.homeTeam?.conference?.lowercased() else { return [] }
        // Find which group the home conference belongs to
        for group in pairs {
            if group.contains(where: { homeConf.contains($0) }) {
                // Return the OTHER group's keywords (the opposing conference)
                for otherGroup in pairs where otherGroup != group {
                    // Only return the partner pair
                    let idx = pairs.firstIndex(of: group) ?? 0
                    // AL pairs with NL (indices 0,1), AFC with NFC (2,3), East with West (4,5)
                    let partnerIdx = idx % 2 == 0 ? idx + 1 : idx - 1
                    if partnerIdx >= 0, partnerIdx < pairs.count {
                        return pairs[partnerIdx]
                    }
                }
            }
        }
        return []
    }

    /// Filter out stages that reference the opposing conference when both teams share one
    private func filteredStages(for team: TeamProgressionData) -> [ProgressionStageData] {
        guard sameConference, !opposingConferenceKeywords.isEmpty else {
            return team.stages
        }
        return team.stages.filter { stage in
            let lower = stage.label.lowercased()
            // Keep the stage unless its label contains an opposing conference keyword
            return !opposingConferenceKeywords.contains(where: { lower.contains($0) })
        }
    }

    var body: some View {
        let away = progression.awayTeam
        let home = progression.homeTeam

        if away != nil || home != nil {
            VStack(alignment: .leading, spacing: 12) {
                Text("Championship Path")
                    .font(.headline)
                    .fontWeight(.semibold)

                let cardCount = (away == nil ? 0 : 1) + (home == nil ? 0 : 1)
                let contentWidth = ChampionshipRowLayout.teamCardContentWidth(
                    totalWidth: cardsWidth, cardCount: cardCount)

                HStack(alignment: .top, spacing: ChampionshipRowLayout.cardSpacing) {
                    if let away {
                        teamCard(team: away, stages: filteredStages(for: away),
                                 color: awayTeamColor, contentWidth: contentWidth)
                    }
                    if let home {
                        teamCard(team: home, stages: filteredStages(for: home),
                                 color: homeTeamColor, contentWidth: contentWidth)
                    }
                }
                .background(
                    GeometryReader { geo in
                        Color.clear.preference(
                            key: ChampionshipCardsWidthKey.self, value: geo.size.width)
                    }
                )
                .onPreferenceChange(ChampionshipCardsWidthKey.self) { width in
                    cardsWidth = width
                }
            }
            .padding()
            .background(Color.cardBackground)
            .clipShape(RoundedRectangle(cornerRadius: 16))
        }
    }

    private func teamCard(
        team: TeamProgressionData,
        stages: [ProgressionStageData]? = nil,
        color: Color,
        contentWidth: CGFloat = 0
    ) -> some View {
        let displayStages = stages ?? team.stages
        return VStack(alignment: .leading, spacing: 12) {
            // Team header with logo, name, record, conference
            HStack(spacing: 8) {
                if let logoUrl = team.logoUrl, let url = URL(string: logoUrl) {
                    AsyncImage(url: url) { phase in
                        switch phase {
                        case .success(let image):
                            image.resizable().scaledToFit()
                        default:
                            RoundedRectangle(cornerRadius: 8)
                                .fill(color.opacity(0.15))
                                .overlay(
                                    Text(String((team.shortName ?? team.name).prefix(2)))
                                        .font(.system(size: 12, weight: .bold))
                                        .foregroundStyle(color)
                                )
                        }
                    }
                    .frame(width: 40, height: 40)
                } else {
                    RoundedRectangle(cornerRadius: 8)
                        .fill(color.opacity(0.15))
                        .frame(width: 40, height: 40)
                        .overlay(
                            Text(String((team.shortName ?? team.name).prefix(2)))
                                .font(.system(size: 12, weight: .bold))
                                .foregroundStyle(color)
                        )
                }

                VStack(alignment: .leading, spacing: 2) {
                    Text(team.shortName ?? team.name)
                        .font(.subheadline)
                        .fontWeight(.bold)
                    HStack(spacing: 4) {
                        if let record = team.record {
                            Text(record)
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                        }
                        if let conf = team.conference {
                            Text("· \(conf)")
                                .font(.system(size: 10))
                                .foregroundStyle(.secondary)
                        }
                    }
                }
            }

            // Championship Path label
            Text("CHAMPIONSHIP PATH")
                .font(.system(size: 10, weight: .heavy))
                .foregroundStyle(.tertiary)
                .tracking(0.5)

            // Stages. One decision for the whole card, so its bars stay the same
            // length as each other and remain comparable (#3574/#3580).
            let badgeWidth = ChampionshipRowLayout.badgeWidth(for: displayStages)
            let stacked = ChampionshipRowLayout.stacksBelowLabel(
                contentWidth: contentWidth, stages: displayStages)

            ForEach(displayStages, id: \.key) { stage in
                stageRow(stage: stage, color: color, badgeWidth: badgeWidth, stacked: stacked)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(ChampionshipRowLayout.cardPadding)
        .background(Color.secondary.opacity(0.03))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color.barTrack.opacity(0.5), lineWidth: 0.5)
        )
    }

    /// One stage, in whichever of the two shapes its card has room for.
    ///
    /// `stacked` is not a style choice — it is `ChampionshipRowLayout`'s answer
    /// to whether the one-line shape fits. See that type for the arithmetic and
    /// for what the row was doing before (#3574, #3580).
    @ViewBuilder
    private func stageRow(
        stage: ProgressionStageData, color: Color, badgeWidth: CGFloat, stacked: Bool
    ) -> some View {
        if stacked {
            VStack(alignment: .leading, spacing: 4) {
                stageLabel(stage)
                    .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: ChampionshipRowLayout.spacing) {
                    stageBar(stage: stage, color: color)
                    stageBadges(stage: stage, color: color)
                        .frame(width: badgeWidth, alignment: .trailing)
                }
            }
        } else {
            HStack(spacing: ChampionshipRowLayout.spacing) {
                stageLabel(stage)
                    .frame(width: ChampionshipRowLayout.labelWidth, alignment: .leading)
                stageBar(stage: stage, color: color)
                stageBadges(stage: stage, color: color)
                    .frame(width: badgeWidth, alignment: .trailing)
            }
        }
    }

    private func stageLabel(_ stage: ProgressionStageData) -> some View {
        Text(stage.label)
            .font(.caption)
            .foregroundStyle(.secondary)
    }

    private func stageBar(stage: ProgressionStageData, color: Color) -> some View {
        let prob = stage.probability ?? 0
        return GeometryReader { geo in
            ZStack(alignment: .leading) {
                Capsule()
                    .fill(Color.secondary.opacity(0.08))
                Capsule()
                    .fill(ChampionshipRowLayout.isClinched(probability: stage.probability)
                          ? Color.green : color)
                    .frame(width: max(2, geo.size.width * min(1.0, prob)))
            }
        }
        // Deliberately no `minWidth`. The minimum is the *criterion* the layout
        // rule applies before choosing the one-line shape, not a floor the bar
        // enforces on its own: a floor it cannot satisfy would push the badge
        // column out of the card and re-open #3574 from the other side.
        .frame(height: 10)
    }

    private func stageBadges(stage: ProgressionStageData, color: Color) -> some View {
        let prob = stage.probability ?? 0
        let isClinched = ChampionshipRowLayout.isClinched(probability: stage.probability)

        // `lineLimit(1)` is a backstop, not the fix: the column is sized to hold
        // this content, so it should never fire. It is here so that if it ever
        // does — a larger Dynamic Type setting, a longer future string — the
        // failure is a legible ellipsis rather than `clinc` / `hed` (#3574).
        return HStack(spacing: 4) {
            if let trend = stage.trend24h,
               ChampionshipRowLayout.showsTrendBadge(trend: trend) {
                HStack(spacing: 1) {
                    Image(systemName: trend > 0 ? "arrow.up" : "arrow.down")
                        .font(.system(size: 7, weight: .bold))
                    Text(String(format: "%.1f%%", abs(trend * 100)))
                        .font(.system(size: 9, weight: .medium))
                        .lineLimit(1)
                }
                .foregroundStyle(trend > 0 ? .green : .red)
            }

            if isClinched {
                HStack(spacing: 2) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 8, weight: .bold))
                    Text("clinched")
                        .font(.system(size: 10, weight: .medium))
                        .lineLimit(1)
                }
                .foregroundStyle(.green)
            } else {
                Text(formatProb(prob))
                    .font(.caption)
                    .fontWeight(.bold)
                    .monospacedDigit()
                    .lineLimit(1)
                    .foregroundStyle(color)
            }
        }
    }

    private func formatProb(_ p: Double) -> String {
        if p >= 0.995 { return ">99%" }
        if p <= 0.005 { return "<1%" }
        return "\(Int((p * 100).rounded()))%"
    }
}
