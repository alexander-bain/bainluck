import Charts
import SwiftUI

/// #10868 — the picture of a ``PlayerMilestoneProfile``: one stem and one
/// hollow dot per quoted line on the stat's own axis, 0–100% up the side, the
/// picked line larger. Adapted from the Atlas v6 embeddable profile view; the
/// target chips under it stay the control, so this view is read-only and the
/// selection lives where it already did (`PlayerPropsCardView.selectedTargets`).
///
/// Hollow is the atlas's PRE-GAME mark, which is what every one of these is: a
/// pre-game chance. A solid in-game dot and a final-stat rule are not drawn
/// here (see ``PlayerMilestoneProfile``).
struct PlayerMilestoneProfileView: View {
    let profile: PlayerMilestoneProfile.Profile
    let selectedIndex: Int?
    let color: Color
    /// Spoken name of the stat ("Rushing yards").
    let stat: String

    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        Chart {
            RuleMark(y: .value("Chance", 0.5))
                .foregroundStyle(Color.secondary.opacity(0.35))
                .lineStyle(StrokeStyle(lineWidth: 0.5, dash: [3, 3]))
            ForEach(profile.milestones) { milestone in
                let isSelected = milestone.index == selectedIndex
                RuleMark(
                    x: .value("Line", milestone.threshold),
                    yStart: .value("Chance", 0),
                    yEnd: .value("Chance", milestone.probability)
                )
                .foregroundStyle(color.opacity(isSelected ? 0.9 : 0.35))
                .lineStyle(StrokeStyle(lineWidth: isSelected ? 2 : 1.5))
                PointMark(
                    x: .value("Line", milestone.threshold),
                    y: .value("Chance", milestone.probability)
                )
                .symbol {
                    let size: CGFloat = isSelected ? 14 : 9
                    Circle()
                        .strokeBorder(color, lineWidth: isSelected ? 2.5 : 2)
                        .background(Circle().fill(Color.cardBackground))
                        .frame(width: size, height: size)
                }
            }
        }
        .chartXScale(domain: profile.domain)
        .chartYScale(domain: 0...1)
        .chartYAxis {
            AxisMarks(position: .leading, values: [0, 0.5, 1]) { value in
                AxisGridLine()
                    .foregroundStyle(Color.secondary.opacity(0.15))
                AxisValueLabel {
                    if let chance = value.as(Double.self) {
                        Text("\(Int((chance * 100).rounded()))%")
                    }
                }
            }
        }
        .chartXAxis {
            AxisMarks(values: .automatic(desiredCount: 5)) { value in
                AxisTick()
                AxisValueLabel {
                    if let line = value.as(Double.self) {
                        Text(PlayerPropsCardView.formatStatValue(line))
                    }
                }
            }
        }
        // Taller at accessibility sizes so the axis labels keep their room.
        .frame(height: typeSize.isAccessibilitySize ? 200 : 140)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(PlayerMilestoneProfile.spokenSummary(profile, stat: stat))
        .accessibilityIdentifier("props-milestone-profile")
    }
}
