import SwiftUI

/// #10830 — both teams' season outcomes in ONE aligned table: a row per stage
/// ("Make Playoffs", "Division", …), a column per team. The native twin of
/// web's `SeasonComparison` (#10809).
///
/// Every cell is drawn by the Championship Path's own pieces —
/// ``ChampionshipRowLayout/display(for:)`` decides priced / clinched /
/// withheld, and ``ChampionshipStageBadges`` prints the number and its 24h
/// move under #4108 (a settled row carries no delta), #7780 (colour follows the
/// news, arrow follows the number) and #8691 (a withheld row prints nothing).
/// So this view decides only the arrangement. Season state is the stage's own,
/// never the game's: a finished game does not settle a season row.
struct SeasonComparisonView: View {
    let away: TeamProgressionData
    let home: TeamProgressionData
    let awayStages: [ProgressionStageData]
    let homeStages: [ProgressionStageData]
    var awayColor: Color = .red
    var homeColor: Color = .blue

    @Environment(\.dynamicTypeSize) private var dynamicTypeSize

    /// One row: the stage label and each team's stage for it, when it has one.
    struct Row: Identifiable {
        let id: String
        let label: String
        let away: ProgressionStageData?
        let home: ProgressionStageData?
    }

    /// The union of both teams' stages, keyed by the structured `key` (labels
    /// re-word), in the order the AWAY team lists them and then any the home
    /// team adds. A stage only one team has keeps an empty cell for the other.
    static func rows(away: [ProgressionStageData], home: [ProgressionStageData]) -> [Row] {
        var order: [String] = []
        for stage in away + home where !order.contains(stage.key) {
            order.append(stage.key)
        }
        return order.map { key in
            let a = away.first { $0.key == key }
            let h = home.first { $0.key == key }
            return Row(id: key, label: (a ?? h)?.label ?? key, away: a, home: h)
        }
    }

    var body: some View {
        let rows = Self.rows(away: awayStages, home: homeStages)
        let stacked = dynamicTypeSize.isAccessibilitySize
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                header(stacked: stacked)
                ForEach(rows) { row in
                    Divider()
                    rowView(row, stacked: stacked)
                }
            }
        }
    }

    // Three equal columns: every cell is `maxWidth: .infinity` with no layout
    // priority, so the HStack splits the row evenly and each team's bar gets a
    // real track (a priority on the label let it take the row, and the bars
    // drew as 2 pt slivers — caught by the render test).
    private func header(stacked: Bool) -> some View {
        HStack(alignment: .bottom, spacing: 12) {
            if !stacked {
                Text("Season outcomes")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            teamHeader(away, color: awayColor)
            teamHeader(home, color: homeColor)
        }
        .padding(.bottom, 10)
    }

    private func teamHeader(_ team: TeamProgressionData, color: Color) -> some View {
        VStack(alignment: .trailing, spacing: 2) {
            Text(team.shortName ?? team.name)
                .font(.subheadline.weight(.bold))
                .foregroundStyle(color)
                .multilineTextAlignment(.trailing)
                .fixedSize(horizontal: false, vertical: true)
            if let record = team.record {
                Text(record)
                    .font(.caption)
                    .monospacedDigit()
                    .foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func rowView(_ row: Row, stacked: Bool) -> some View {
        let cells = HStack(alignment: .top, spacing: 12) {
            if !stacked {
                label(row)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            cell(row.away, color: awayColor)
            cell(row.home, color: homeColor)
        }
        Group {
            if stacked {
                // At the accessibility sizes the label takes its own line and
                // the two teams split the full width beneath it.
                VStack(alignment: .leading, spacing: 6) {
                    label(row)
                    cells
                }
            } else {
                cells
            }
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(accessibilityText(row))
    }

    private func label(_ row: Row) -> some View {
        Text(row.label)
            .font(.subheadline)
            .foregroundStyle(.secondary)
            .fixedSize(horizontal: false, vertical: true)
    }

    @ViewBuilder
    private func cell(_ stage: ProgressionStageData?, color: Color) -> some View {
        VStack(alignment: .trailing, spacing: 4) {
            if let stage {
                ChampionshipStageBadges(stage: stage, color: color)
                if let fraction = ChampionshipRowLayout.display(for: stage).barFraction {
                    GeometryReader { geo in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Color.secondary.opacity(0.08))
                            Capsule()
                                .fill(ChampionshipRowLayout.display(for: stage) == .clinched ? Color.green : color)
                                .frame(width: max(2, geo.size.width * min(1.0, fraction)))
                        }
                    }
                    .frame(height: 5)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .trailing)
    }

    /// "Make Playoffs: Patriots 63%, Raiders 38%". A withheld cell says
    /// nothing, as it prints nothing.
    private func accessibilityText(_ row: Row) -> String {
        func part(_ team: TeamProgressionData, _ stage: ProgressionStageData?) -> String? {
            guard let stage else { return nil }
            let name = team.shortName ?? team.name
            switch ChampionshipRowLayout.display(for: stage) {
            case .clinched: return "\(name) clinched"
            case .priced(let p): return "\(name) \(ChampionshipStageBadges.formatProb(p))"
            case .withheld: return nil
            }
        }
        let parts = [part(away, row.away), part(home, row.home)].compactMap { $0 }
        return parts.isEmpty ? row.label : "\(row.label): \(parts.joined(separator: ", "))"
    }
}
