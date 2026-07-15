import SwiftUI

/// Compact grouped display for playoff progression markets — matches web ProgressionLadder.
///
/// This is the compact **feed** variant. The full per-team / per-prop ladder is now
/// `LadderCardView` (the adopted "2b" design). Both share the `LadderRung` primitive —
/// `LadderRung(stage:)` adapts this view's `[ProgressionStage]` onto it. Migrating the
/// feed's grouped section to `LadderCardView` is the league-screen assembly step (L2-123).
struct ProgressionLadderView: View {
    let entityName: String
    let stages: [ProgressionStage]
    var logoUrl: String? = nil
    var teamColors: TeamColors? = nil
    var onStageClick: ((ProgressionStage) -> Void)? = nil
    var horizontal: Bool = false

    private var sortedStages: [ProgressionStage] {
        stages.prefix(5).map { $0 }
    }

    private var primaryColor: Color {
        if let hex = teamColors?.primary {
            return Color(rgb: hex)
        }
        return .accentColor
    }

    var body: some View {
        if horizontal {
            horizontalLayout
        } else {
            verticalLayout
        }
    }

    // MARK: - Vertical Layout (default)

    private var verticalLayout: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Header
            HStack(spacing: 8) {
                TeamLogoView(
                    url: logoUrl,
                    teamName: entityName,
                    color: primaryColor,
                    size: 28
                )
                Text(entityName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
                Spacer()
                Text("PLAYOFFS")
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
            }

            // Stages as simple rows
            VStack(spacing: 4) {
                ForEach(sortedStages) { stage in
                    stageRow(stage)
                }
            }
        }
        .padding(12)
        .background(Color.cardBackgroundDark)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .leading) {
            if teamColors != nil {
                RoundedRectangle(cornerRadius: 10)
                    .fill(primaryColor)
                    .frame(width: 3)
            }
        }
    }

    // MARK: - Horizontal Layout

    private var horizontalLayout: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                TeamLogoView(
                    url: logoUrl,
                    teamName: entityName,
                    color: primaryColor,
                    size: 22
                )
                Text(entityName)
                    .font(.subheadline)
                    .fontWeight(.medium)
                    .foregroundStyle(.primary)
                    .lineLimit(1)
            }

            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 4) {
                    ForEach(sortedStages) { stage in
                        horizontalStageCell(stage)
                    }
                }
            }
        }
        .padding(12)
        .background(Color.cardBackgroundDark)
        .clipShape(RoundedRectangle(cornerRadius: 10))
        .overlay(alignment: .leading) {
            if teamColors != nil {
                RoundedRectangle(cornerRadius: 10)
                    .fill(primaryColor)
                    .frame(width: 3)
            }
        }
    }

    // MARK: - Stage Row (vertical)

    private func stageRow(_ stage: ProgressionStage) -> some View {
        let prob = stage.probability ?? 0
        let achieved = stage.status == "achieved"
        let eliminated = stage.status == "eliminated"

        return Button {
            onStageClick?(stage)
        } label: {
            HStack(spacing: 6) {
                // Status dot
                Circle()
                    .fill(achieved ? .green : (eliminated ? .red.opacity(0.5) : .secondary.opacity(0.3)))
                    .frame(width: 8, height: 8)

                // Stage name (truncated)
                Text(cleanStageName(stage.label))
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(maxWidth: .infinity, alignment: .leading)

                // Mini probability bar
                GeometryReader { geo in
                    Capsule()
                        .fill(Color.secondary.opacity(0.2))
                        .frame(height: 4)
                        .overlay(alignment: .leading) {
                            Capsule()
                                .fill(achieved ? .green : .secondary.opacity(0.4))
                                .frame(width: geo.size.width * prob, height: 4)
                        }
                }
                .frame(width: 40, height: 4)

                // Probability text
                Text(achieved ? "done" : formatProbability(prob))
                    .font(.system(size: 11, weight: .medium, design: .monospaced))
                    .foregroundStyle(achieved ? .green : probColor(prob))
                    .frame(minWidth: 32, alignment: .trailing)
            }
            .padding(.horizontal, 4)
            .padding(.vertical, 3)
            .background(achieved ? .green.opacity(0.1) : .clear)
            .clipShape(RoundedRectangle(cornerRadius: 4))
            .opacity(eliminated ? 0.4 : 1.0)
        }
        .buttonStyle(.plain)
    }

    // MARK: - Horizontal Stage Cell

    private func horizontalStageCell(_ stage: ProgressionStage) -> some View {
        let prob = stage.probability ?? 0
        let achieved = stage.status == "achieved"

        return Button {
            onStageClick?(stage)
        } label: {
            VStack(spacing: 2) {
                Text(cleanStageName(stage.label))
                    .font(.system(size: 10))
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .frame(maxWidth: 60)
                Text(achieved ? "done" : formatProbability(prob))
                    .font(.system(size: 12, weight: .medium, design: .monospaced))
                    .foregroundStyle(achieved ? .green : probColor(prob))
            }
            .padding(.horizontal, 8)
            .padding(.vertical, 6)
            .background(achieved ? .green.opacity(0.15) : Color.cardBackgroundDark.opacity(0.5))
            .clipShape(RoundedRectangle(cornerRadius: 6))
        }
        .buttonStyle(.plain)
    }

    // MARK: - Helpers

    private func cleanStageName(_ name: String) -> String {
        var result = name
        for prefix in ["Make ", "Win "] {
            if result.hasPrefix(prefix) {
                result = String(result.dropFirst(prefix.count))
            }
        }
        return result
    }

    private func probColor(_ prob: Double) -> Color {
        if prob >= 0.7 { return .green }
        if prob >= 0.4 { return .primary }
        if prob >= 0.15 { return .orange }
        return .red
    }
}

// MARK: - Color extension for RGB string

extension Color {
    init(rgb: String) {
        // Parse "85, 37, 130" format
        let components = rgb.split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .compactMap { Double($0) }
        if components.count >= 3 {
            self.init(
                red: components[0] / 255,
                green: components[1] / 255,
                blue: components[2] / 255
            )
        } else {
            self.init(.blue)
        }
    }
}
