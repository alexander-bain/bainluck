import SwiftUI

/// Reports the width the two team cards were actually given, so the row layout
/// can be chosen from a measured number instead of a hoped-for one (#3574/#3580).
private struct ChampionshipCardsWidthKey: PreferenceKey {
    static let defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) {
        value = max(value, nextValue())
    }
}

/// What the rows of BOTH cards actually want, at the reader's text size (#4328).
///
/// One value for the whole view, not one per card: the reader compares the away
/// team's bars against the home team's, and two bars of different track lengths
/// cannot be compared — which is the same argument that already gives one card
/// one column, applied to the pair. It is also strictly better than what shipped,
/// where an all-clinched card took the 56 pt column while its opponent took 76
/// and their bars came out different lengths.
private struct ChampionshipColumnsKey: PreferenceKey {
    static let defaultValue = ChampionshipColumnWidths.zero
    static func reduce(
        value: inout ChampionshipColumnWidths, nextValue: () -> ChampionshipColumnWidths
    ) {
        value = value.merged(with: nextValue())
    }
}

/// Reports the width `probe` wants when nothing constrains it.
///
/// A `GeometryReader` on the drawn view would report the width it was GIVEN —
/// 80 pt for a label in an 80 pt column, which is the very number under
/// suspicion. So the probe is a hidden, `fixedSize` copy: `fixedSize` refuses the
/// proposal, so what it measures is what the content wants, and `.hidden()` plus
/// living in a `.background` keeps it out of both the drawing and the layout.
private struct NaturalWidthProbe<Probe: View>: View {
    let column: WritableKeyPath<ChampionshipColumnWidths, CGFloat>
    @ViewBuilder let probe: Probe

    var body: some View {
        probe
            .fixedSize(horizontal: true, vertical: false)
            .hidden()
            .background(
                GeometryReader { geo in
                    Color.clear.preference(
                        key: ChampionshipColumnsKey.self, value: widths(geo.size.width))
                }
            )
    }

    private func widths(_ width: CGFloat) -> ChampionshipColumnWidths {
        var value = ChampionshipColumnWidths.zero
        value[keyPath: column] = width
        return value
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

    /// What the rows measured at the reader's text size, once laid out (#4328).
    /// Zero until then, and the constants are the floor either way — see
    /// `ChampionshipRowLayout.columns(measured:for:)`.
    @State private var measuredColumns: ChampionshipColumnWidths = .zero

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

                // One column for both cards, and one shape, so every bar on the
                // screen has the same track and the reader can compare them
                // (#3574/#3580). Since #4328 the column is the larger of what
                // shipped and what this reader's text size actually needs.
                let columns = ChampionshipRowLayout.columns(
                    measured: measuredColumns,
                    for: (away.map { filteredStages(for: $0) } ?? [])
                        + (home.map { filteredStages(for: $0) } ?? []))
                let shape = ChampionshipRowLayout.shape(
                    contentWidth: contentWidth, columns: columns)

                HStack(alignment: .top, spacing: ChampionshipRowLayout.cardSpacing) {
                    if let away {
                        teamCard(team: away, stages: filteredStages(for: away),
                                 color: awayTeamColor, columns: columns, shape: shape)
                    }
                    if let home {
                        teamCard(team: home, stages: filteredStages(for: home),
                                 color: homeTeamColor, columns: columns, shape: shape)
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
                .onPreferenceChange(ChampionshipColumnsKey.self) { columns in
                    measuredColumns = columns
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
        columns: ChampionshipColumnWidths,
        shape: ChampionshipRowShape
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
                                    Text(TeamShortName.abbreviation(team.shortName ?? team.name))
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
                            Text(TeamShortName.abbreviation(team.shortName ?? team.name))
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

            // Stages. The columns and the shape were decided once for both cards
            // (see `body`), so every bar on the screen has the same track and
            // stays comparable (#3574/#3580).
            ForEach(displayStages, id: \.key) { stage in
                stageRow(stage: stage, color: color, columns: columns, shape: shape)
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
        stage: ProgressionStageData, color: Color,
        columns: ChampionshipColumnWidths, shape: ChampionshipRowShape
    ) -> some View {
        switch shape {
        case .inline:
            HStack(spacing: ChampionshipRowLayout.spacing) {
                stageLabel(stage)
                    .frame(width: columns.label, alignment: .leading)
                stageBar(stage: stage, color: color)
                stageBadges(stage: stage, color: color)
                    .frame(width: columns.badges, alignment: .trailing)
            }
        case .stacked:
            VStack(alignment: .leading, spacing: 4) {
                stageLabel(stage)
                    .frame(maxWidth: .infinity, alignment: .leading)
                HStack(spacing: ChampionshipRowLayout.spacing) {
                    stageBar(stage: stage, color: color)
                    stageBadges(stage: stage, color: color)
                        .frame(width: columns.badges, alignment: .trailing)
                }
            }
        case .badgesAboveBar:
            // #4328. The badges are given the whole card rather than a column,
            // so `ChampionshipStageBadges` can take its two-line arrangement
            // instead of truncating — and the bar, freed of them, is longer here
            // than it is at default text size.
            VStack(alignment: .leading, spacing: 4) {
                stageLabel(stage)
                    .frame(maxWidth: .infinity, alignment: .leading)
                stageBadges(stage: stage, color: color)
                    .frame(maxWidth: .infinity, alignment: .leading)
                stageBar(stage: stage, color: color)
            }
        }
    }

    private func stageLabel(_ stage: ProgressionStageData) -> some View {
        Text(stage.label)
            .font(.caption)
            .foregroundStyle(.secondary)
            .background(
                NaturalWidthProbe(column: \.label) {
                    Text(stage.label).font(.caption)
                }
            )
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
        ChampionshipStageBadges(stage: stage, color: color)
            .background(
                NaturalWidthProbe(column: \.badges) {
                    ChampionshipStageBadges(stage: stage, color: color)
                }
            )
    }
}

/// The trailing badges of one Championship Path row: an optional trend badge,
/// then either "clinched" or the probability.
///
/// A view of its own rather than a `@ViewBuilder` method so a test can host it
/// and ask what width it actually wants. `ChampionshipRowLayout`'s badge-column
/// constants claim to be measured against this content; without something to
/// measure, "96 pt is enough for `↑91.3% ✓ clinched`" would be an estimate
/// wearing the word measured — and a column one point too narrow is exactly
/// what #3574 was.
///
/// Since #4328 the CARD asks it the same question at run time, at the reader's
/// own text size, through `NaturalWidthProbe` — because the answer is different
/// at each of the twelve, and a `static let` can only hold one of them.
struct ChampionshipStageBadges: View {
    let stage: ProgressionStageData
    var color: Color = .blue

    var body: some View {
        // #4328 — THE BACKSTOP FIRED, AND A BACKSTOP THAT FIRES IS THE DEFECT.
        //
        // `lineLimit(1)` below was written as a promise that a too-narrow column
        // would fail legibly rather than as `clinc` / `hed` (#3574). At
        // accessibility text sizes it kept that promise on the one string a
        // reader cannot lose: the probability rendered `1…`. A legible ellipsis
        // is still no number.
        //
        // So the arrangement gives before the words do. `ViewThatFits` takes the
        // one-line badge wherever it fits — every size up to and including the
        // column it is normally given — and drops to two lines only where the
        // card genuinely cannot hold one (at `.accessibility5` the one-line badge
        // wants 141.33 pt and a phone card has 137.3). The measurement that sizes
        // the column reads the FIRST arm, so nothing about the ordinary render
        // moves; see `NaturalWidthProbe`.
        ViewThatFits(in: .horizontal) {
            badges(AnyLayout(HStackLayout(alignment: .center, spacing: 4)))
            badges(AnyLayout(VStackLayout(alignment: .trailing, spacing: 2)))
        }
    }

    private func badges(_ layout: AnyLayout) -> some View {
        let prob = stage.probability ?? 0
        let isClinched = ChampionshipRowLayout.isClinched(probability: stage.probability)

        return layout {
            // #4108 — a settled row carries no movement. This drew
            // "↑90.9%  ✓ clinched": a 90.9 percentage-POINT 24h move claimed on a
            // stage the same row calls decided, with the probability itself never
            // printed (the `else` below is what would have shown it). Alex read
            // the delta as the probability, which is the obvious reading of a
            // lone percentage — and the true statement was the stranger of the
            // two. `LadderCardView` has suppressed the delta on a clinched row
            // since it shipped; this is the two components agreeing (#4002).
            //
            // Clinched only, because clinched is the only settled state this
            // model has: `ChampionshipRowLayout` knows `isClinched` and nothing
            // else, and a stage at 0.1% is a long shot rather than an
            // elimination. `LadderCardView`'s `eliminated` arm has no counterpart
            // here to keep in step with.
            if !isClinched,
               let trend = stage.trend24h,
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
                // `lineLimit(1)` stays, and it is now genuinely a backstop rather
                // than the thing standing between the reader and the number: the
                // arrangement above gives first, so this only ever fires on a
                // future string nobody has measured. It is also why a row's HEIGHT
                // cannot testify about a too-narrow column, and why every test
                // that guards this measures width (#3574).
                Text(Self.formatProb(prob))
                    .font(.caption)
                    .fontWeight(.bold)
                    .monospacedDigit()
                    .lineLimit(1)
                    .foregroundStyle(color)
            }
        }
    }

    static func formatProb(_ p: Double) -> String {
        if p >= 0.995 { return ">99%" }
        if p <= 0.005 { return "<1%" }
        return "\(Int((p * 100).rounded()))%"
    }
}
