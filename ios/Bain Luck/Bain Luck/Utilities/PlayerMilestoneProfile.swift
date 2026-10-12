import Foundation

/// #10868 (Atlas v6, first adoption slice) — a pre-game prop ladder drawn as a
/// MILESTONE PROFILE: every quoted line ("40+", "50+", …) at its true place on
/// the stat's own axis, its chance as a stem and a hollow dot, the line the
/// reader picked drawn larger.
///
/// The atlas's accepted NFL profiles (`atlas-v6/COMPONENT-CONTRACT.md`,
/// "Quantity milestone profile") draw this shape from archived captures. Here it
/// is built from the SAME rungs the target chips already print — the served
/// `threshold` and `over_probability` — so the picture can never say anything
/// the chips under it do not:
///
/// - only priced rungs are drawn; an unpriced rung keeps its chip and gets no
///   dot (#10830's `priced`);
/// - a flat ladder is not a price and gets no picture (#5137,
///   ``PlayerPropsPricing/isPricedLadder(_:)``);
/// - two quotes for one line (two venues) get no picture: the profile has one
///   mark per line, and picking one of the two would be a second price engine;
/// - nothing between the lines is drawn — no curve, no shading, no "likely
///   range". The contract forbids inferring density from milestones.
///
/// Pre-game only. The live and finished ladders keep the rung renderer, which
/// carries the grades (#4959, #4907); a final-stat line and an in-game dot are
/// later slices with their own clocks.
enum PlayerMilestoneProfile {
    /// Fewer priced lines than this is a choice between chips, not a shape.
    static let minimumPricedMilestones = 3

    struct Milestone: Equatable, Identifiable {
        /// The rung's index in the ladder — the same index the target chips and
        /// `selectedTarget` use, so the picked chip and the large dot agree.
        let index: Int
        let threshold: Double
        let probability: Double
        var id: Int { index }
    }

    struct Profile: Equatable {
        /// Ascending by line.
        let milestones: [Milestone]
        /// The stat axis: half a step of padding either side, never below zero
        /// for a ladder that starts at or above zero.
        let domain: ClosedRange<Double>

        /// The x-axis ticks: the quoted lines and nothing between them, so
        /// every axis label is a label some chip prints.
        var axisLines: [Double] { milestones.map(\.threshold) }
    }

    /// nil means "draw the chips only".
    static func profile(thresholds: [Double], probabilities: [Double?]) -> Profile? {
        guard thresholds.count == probabilities.count else { return nil }
        let priced = thresholds.indices.compactMap { index -> Milestone? in
            let threshold = thresholds[index]
            guard let probability = probabilities[index],
                  probability.isFinite, (0...1).contains(probability),
                  threshold.isFinite
            else { return nil }
            return Milestone(index: index, threshold: threshold, probability: probability)
        }
        guard priced.count >= minimumPricedMilestones,
              PlayerPropsPricing.isPricedLadder(priced.map(\.probability))
        else { return nil }

        let lines = priced.map(\.threshold)
        guard Set(lines).count == lines.count,
              let low = lines.min(), let high = lines.max(), high > low
        else { return nil }

        let pad = (high - low) / Double(priced.count - 1) / 2
        let lower = low >= 0 ? max(0, low - pad) : low - pad
        return Profile(
            milestones: priced.sorted { $0.threshold < $1.threshold },
            domain: lower...(high + pad)
        )
    }

    /// What VoiceOver reads for the whole picture: every line and its chance,
    /// in order, with the same numbers the chips print.
    static func spokenSummary(_ profile: Profile, stat: String) -> String {
        let lines = profile.milestones.map {
            "\(PlayerPropsFamily.targetLabel($0.threshold)) \(PlayerPropsPricing.displayPercent($0.probability))%"
        }
        return "\(stat), chance to reach each line: " + lines.joined(separator: ", ")
    }
}
