import SwiftUI

// #10868 — THE BASEBALL GAME SCREEN'S FIFTH STORY: EXTRA INNINGS.
//
// PILLARS: FORMATTING / TRUTH. SHIP: on an MLB event page the extra-innings
// story compares the venue's earlier chance of extra innings with a
// separately clocked chance recorded during play — two equally readable
// figures, each with its own label and its own clock line, on one shared
// zero-based scale — beside the venue's own result for its contract, and says
// plainly that the inning result itself is unavailable.
//
// The approved route has five story families (prototype
// `baseballCardContext.ts::baseballStoryFamilies`: strikeouts / extra /
// home-runs / totals / series; `Atlas.tsx::BaseballStories` draws `extra`
// through `TemporalCard`), and the production final deck deals all five
// (`MLBFinalDeck11284`). The production extra-innings view
// (`MLBExtraInningsCardView11284`) needs the deck's shared state object
// (`NFLCardDeckState9483`, Native-owned) and prints the venue result only, so
// this is a small owned composition instead. It draws, never decides:
//
//   - which outcomes, their order, labels, venues, exact originals and venue
//     results are the production card's (`MLBExtraInningsCard11284`, passed in
//     unchanged inside the story);
//   - each chance, its figure, its clock line, the change words and the scale
//     ceiling are the adapter's (`BaseballExtraInningsAdapter10868`), from the
//     owner's admitted readings only;
//   - the shared geometry is the home-run comparison's
//     (`MLBHomeRunComparison11284.railFraction`, `.axisLabels`, `.marker`) and
//     the heading is the MLB cards' own (`MLBStoryHeading11284`).
//
// The two marks are separate observations: the hollow one is the pregame
// chance (it has no clock of its own and may be an opening price — said, never
// hidden), the filled one is a recorded in-game chance at its own clock. They
// are never interpolated, complemented or put on one clock; the connector
// between them is a comparison aid, not a history. A recorded chance is
// history in every phase — never "current" and never a settlement — and no
// inning result is inferred from either chance or from the score.
//
// Controls: with `onSelect` and more than one outcome, each outcome is a
// 44-point control handing back its exact `original.id`; with `onDetails`, a
// Details control hands back the selected outcome's `original.id`. With no
// callback nothing pretends to act. A held outcome the card no longer carries
// draws the withdrawn words and borrows no neighbour's figures. No state, no
// timer, no animation.

/// One chance slot: an admitted chance with its own words, or the slot's
/// own absence words.
nonisolated enum BaseballExtraInningsChance10868: Equatable {
    /// `probability` places the mark only; `text` is printed verbatim,
    /// `provenance` is the chance's own clock line, `spoken` its words.
    case value(probability: Double, text: String, provenance: String, spoken: String)
    case unavailable(String)

    var text: String {
        switch self {
        case .value(_, let text, _, _): text
        case .unavailable(let words): words
        }
    }

    var probability: Double? {
        if case .value(let probability, _, _, _) = self { return probability }
        return nil
    }

    var spoken: String {
        switch self {
        case .value(_, _, _, let spoken): spoken
        case .unavailable(let words): words
        }
    }
}

/// One outcome of the venue's extra-innings market, as the story shows it.
struct BaseballExtraInningsOption10868: Equatable {
    /// The exact production original identity (`MLBExtraInningsCard11284.Outcome.original.id`).
    let id: String
    /// The served outcome name, verbatim.
    let label: String
    /// The venue's reader name; nil names none.
    let venue: String?
    /// The venue's own grade of its contract — never an inning result.
    let venueResult: MLBVenueResult11284
    /// The pregame chance (hollow), or its words.
    let pregame: BaseballExtraInningsChance10868
    /// The recorded in-game chance (filled), or its words.
    let recorded: BaseballExtraInningsChance10868
    /// "Up 5.0 points since pregame"; nil unless both chances are admitted.
    let change: String?
    /// The exact original for Details, with the admitted readings named.
    let original: MLBOriginal11284
}

/// The fifth story's whole input.
struct BaseballExtraInningsStory10868: Equatable {
    /// The production card, unchanged.
    let card: MLBExtraInningsCard11284
    /// One per card outcome, in the card's order.
    let options: [BaseballExtraInningsOption10868]
    /// The host's held outcome (`original.id`), else the adapter's default.
    let selectedID: String?
    /// The one zero-based scale both marks share.
    let ceiling: Double
    let color: Color
}

nonisolated enum BaseballExtraInningsWords10868 {
    static let kicker = "Extra innings"
    static let venueMarket = "venue market"
    static let title = "Could the game go to extra innings?"
    static let note = "Inning result unavailable · this is the earlier market outlook"
    static let pregameLabel = "Pregame chance"
    static let recordedLabel = "Recorded in game"
    static let venueResult = "Venue result:"
    static let withdrawn = "This outcome isn’t available in this update."
    static let details = "Details"
    static let detailsHint = "Shows this outcome’s exact original"
    static let key = "Hollow: pregame chance · Filled: recorded in game · one shared scale"
    static let outcomes = "Extra innings outcomes"
}

nonisolated enum BaseballExtraInningsAccessibilityID10868 {
    static let card = "baseballExtraInnings10868.card"
    static let comparison = "baseballExtraInnings10868.comparison"
    static let details = "baseballExtraInnings10868.details"
    static let withdrawn = "baseballExtraInnings10868.withdrawn"
    static func outcome(_ id: String) -> String { "baseballExtraInnings10868.outcome.\(id)" }
}

/// What the leaf shows, resolved once per story.
struct BaseballExtraInningsModel10868: Equatable {
    let story: BaseballExtraInningsStory10868

    /// The held outcome: exactly one option with that id, else none — never a neighbour.
    var selected: BaseballExtraInningsOption10868? {
        guard let id = story.selectedID else { return nil }
        let matches = story.options.filter { $0.id == id }
        return matches.count == 1 ? matches.first : nil
    }

    /// A chooser only when the host can act and there is a choice to make.
    func showsChooser(canSelect: Bool) -> Bool {
        canSelect && story.options.count > 1
    }

    /// "Extra innings · Kalshi", or "Extra innings · venue market" when the
    /// outcomes name no single venue.
    var kicker: String {
        let venues = Set(story.options.compactMap(\.venue))
        guard venues.count == 1, let venue = venues.first else {
            return "\(BaseballExtraInningsWords10868.kicker) · \(BaseballExtraInningsWords10868.venueMarket)"
        }
        return "\(BaseballExtraInningsWords10868.kicker) · \(venue)"
    }

    /// Where a chance sits on the story's one scale; nil draws no mark.
    func fraction(_ chance: BaseballExtraInningsChance10868) -> Double? {
        chance.probability.flatMap { MLBHomeRunComparison11284.railFraction($0, ceiling: story.ceiling) }
    }

    var axis: (lower: String, upper: String) {
        MLBHomeRunComparison11284.axisLabels(ceiling: story.ceiling)
    }

    /// Every word of one outcome's comparison, in reading order.
    func spoken(_ option: BaseballExtraInningsOption10868) -> String {
        var parts = [option.label, option.pregame.spoken, option.recorded.spoken]
        if let change = option.change { parts.append(change) }
        parts.append("\(BaseballExtraInningsWords10868.venueResult) \(option.venueResult.label)")
        parts.append(BaseballExtraInningsWords10868.note)
        return parts.joined(separator: ". ")
    }
}

struct BaseballExtraInningsPresentation10868: View {
    let story: BaseballExtraInningsStory10868
    /// The full-size reader also draws the scale key.
    var expanded = false
    /// An outcome's `original.id`. Nil: no chooser.
    var onSelect: ((String) -> Void)? = nil
    /// The selected outcome's `original.id`. Nil: no Details control.
    var onDetails: ((String) -> Void)? = nil

    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 28
    @ScaledMetric(relativeTo: .body) private var controlSize: CGFloat = 44

    private typealias Words = BaseballExtraInningsWords10868
    private var model: BaseballExtraInningsModel10868 { BaseballExtraInningsModel10868(story: story) }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            MLBStoryHeading11284(kicker: model.kicker, title: Words.title, reason: Words.note)
            if model.showsChooser(canSelect: onSelect != nil) {
                chooser
            }
            if let option = model.selected {
                if !model.showsChooser(canSelect: onSelect != nil) {
                    Text(option.label)
                        .font(.headline)
                        .foregroundStyle(DS.textPrimary)
                }
                comparison(option)
                rail(option)
                scale
                Text("\(Words.venueResult) \(option.venueResult.label)")
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(option.venueResult == .won ? DS.textPrimary : DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                if let onDetails {
                    Button { onDetails(option.id) } label: {
                        HStack(spacing: 6) {
                            Text(Words.details)
                            Image(systemName: "chevron.right")
                                .font(.caption)
                                .accessibilityHidden(true)
                        }
                        .font(.subheadline.weight(.semibold))
                        .frame(minHeight: controlSize)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(DS.blue)
                    .accessibilityHint(Words.detailsHint)
                    .accessibilityIdentifier(BaseballExtraInningsAccessibilityID10868.details)
                }
            } else {
                Text(Words.withdrawn)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityIdentifier(BaseballExtraInningsAccessibilityID10868.withdrawn)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .contain)
        .accessibilityIdentifier(BaseballExtraInningsAccessibilityID10868.card)
    }

    // MARK: Outcomes

    private var chooser: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 8) { chooserButtons }
            VStack(alignment: .leading, spacing: 8) { chooserButtons }
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel(Words.outcomes)
    }

    @ViewBuilder private var chooserButtons: some View {
        ForEach(story.options, id: \.id) { option in
            let isSelected = option.id == model.selected?.id
            Button { onSelect?(option.id) } label: {
                Text(option.label)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .padding(.horizontal, 14)
                    .frame(minHeight: controlSize)
                    .background(isSelected ? story.color.opacity(0.15) : Color.clear, in: Capsule())
                    .overlay(Capsule().stroke(isSelected ? story.color : DS.border, lineWidth: 1))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(isSelected ? .isSelected : [])
            .accessibilityIdentifier(BaseballExtraInningsAccessibilityID10868.outcome(option.id))
        }
    }

    // MARK: The comparison

    @ViewBuilder private func comparison(_ option: BaseballExtraInningsOption10868) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 10) { slots(option) }
            } else {
                ViewThatFits(in: .horizontal) {
                    HStack(alignment: .top, spacing: 20) { slots(option) }
                    VStack(alignment: .leading, spacing: 10) { slots(option) }
                }
            }
            if let change = option.change {
                Text(change)
                    .font(.subheadline.weight(.semibold))
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(model.spoken(option))
        .accessibilityIdentifier(BaseballExtraInningsAccessibilityID10868.comparison)
    }

    @ViewBuilder private func slots(_ option: BaseballExtraInningsOption10868) -> some View {
        slot(Words.pregameLabel, option.pregame, hollow: true)
        slot(Words.recordedLabel, option.recorded, hollow: false)
    }

    private func slot(_ label: String, _ chance: BaseballExtraInningsChance10868, hollow: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 6) {
                mark(hollow: hollow, side: 10)
                Text(label)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            switch chance {
            case .value(_, let text, let provenance, _):
                Text(text)
                    .font(.system(size: figureSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(DS.textPrimary)
                    .fixedSize()
                Text(provenance)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            case .unavailable(let words):
                Text(words)
                    .font(.subheadline)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    @ViewBuilder private func mark(hollow: Bool, side: CGFloat) -> some View {
        if hollow {
            MLBHomeRunComparison11284.marker(.circle, color: story.color, side: side)
        } else {
            Circle()
                .fill(story.color)
                .frame(width: side, height: side)
        }
    }

    // MARK: The shared scale

    /// A muted rail, a connector between two placed marks only, the hollow
    /// pregame mark and the smaller filled recorded mark on top, so equal
    /// values stay two visible marks.
    private func rail(_ option: BaseballExtraInningsOption10868) -> some View {
        let before = model.fraction(option.pregame)
        let later = model.fraction(option.recorded)
        return GeometryReader { geometry in
            let inset: CGFloat = 9
            let width = max(0, geometry.size.width - inset * 2)
            let y = geometry.size.height / 2
            Capsule()
                .fill(Color.secondary.opacity(0.2))
                .frame(width: width, height: 3)
                .position(x: inset + width / 2, y: y)
            if let before, let later {
                let left = inset + width * min(before, later)
                let span = width * abs(later - before)
                Capsule()
                    .fill(story.color.opacity(0.6))
                    .frame(width: span, height: 3)
                    .position(x: left + span / 2, y: y)
            }
            if let before {
                MLBHomeRunComparison11284.marker(.circle, color: story.color, side: 16)
                    .position(x: inset + width * before, y: y)
            }
            if let later {
                Circle()
                    .fill(story.color)
                    .frame(width: 8, height: 8)
                    .position(x: inset + width * later, y: y)
            }
        }
        .frame(height: 24)
        .accessibilityHidden(true)
    }

    private var scale: some View {
        let ends = model.axis
        return VStack(alignment: .leading, spacing: 4) {
            HStack {
                Text(ends.lower)
                Spacer(minLength: 12)
                Text(ends.upper)
            }
            .font(.caption2.monospacedDigit())
            if expanded {
                Text(Words.key)
                    .font(.caption2)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .foregroundStyle(DS.textSecondary)
        .accessibilityHidden(true)
    }
}
