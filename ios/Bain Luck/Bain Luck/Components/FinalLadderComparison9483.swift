import SwiftUI

/// #9483 — AFTER THE FINAL, THE NBA LADDER'S TWO COMPARISONS (design:
/// `margin-expectations-v99/browser/phone.png`; figure hierarchy from
/// `totals-chart-first-reading-20261024`). Two regions the host mounts on
/// either side of its EXISTING chart:
///
///   - `FinalLadderOverview9483` above it: one sentence saying how the actual
///     finished against the pregame projection, then the existing keyed
///     figures (`NBAScoringFigures9483`, solid = actual, dashed = projection).
///   - `FinalLadderReading9483` below it: the selected line, its pregame
///     chance large with the hollow key, and the producer's result beside it.
///
/// PRESENTATION ONLY. `NBALadderCard9483` owns admission, phase, the drawn
/// chance and the producer's result, and the page owns the selection. Nothing
/// here parses, ages, rebuilds a baseline, infers a grade or picks a line.
/// Only a finished card (`.after`) earns these views; before and during play
/// they draw nothing and the host keeps its existing renderer.
///
///   - PERFORMANCE  `card.actual − card.forecast`, both as served, on the
///                  card's own axis. It is a difference of two admitted stats,
///                  not a probability. On the signed margin axis a positive
///                  difference is the home side beating the projected margin,
///                  which says nothing about who won: Clippers by 1 against a
///                  projected Clippers by 3.5 is the Warriors beating it by 2.5.
///                  The magnitude is the shared move precision
///                  (`deltaPointsNumber`); a nonzero difference it would print
///                  as "0.0" says "<0.1". Missing either value: no sentence,
///                  and the missing one is named, never left as a gap.
///   - CHANCE       `Point.chance` only, through the shared `formatProbability`
///                  (whole percents: v99's 38.5% prints 39%). Never
///                  `Detail.quoted`, `Detail.baseline`, a settled 0/1 or a
///                  sibling's chance. Nil says "Pregame chance unavailable".
///   - RESULT       `Point.result` only: Won / Lost / Result unavailable. Never
///                  read from the score or the chance, and an unknown result
///                  never hides a known chance.
///
/// No clock, timer, retained copy, fetch, local selection or navigation state.
/// No previous/next controls: the host's own controls and chart selection stay
/// where they are. Words are market/prop/line/result.
enum FinalLadderComparison9483 {
    static func applies(_ card: NBALadderCard9483) -> Bool { card.phase == .after }

    /// How the actual finished against the pregame projection, or nil unless
    /// the card is finished and carries both.
    static func performance(_ card: NBALadderCard9483) -> String? {
        guard applies(card), let actual = card.actual, let forecast = card.forecast else { return nil }
        let difference = actual - forecast
        switch card.family {
        case .total:
            guard difference != 0 else { return "Total matched the pregame projection" }
            return "Total finished \(magnitude(difference)) points "
                + "\(difference > 0 ? "above" : "below") the pregame projection"
        case .margin:
            guard difference != 0 else { return "Final margin matched the projected margin" }
            return "\(difference > 0 ? card.homeShort : card.awayShort) beat the projected margin "
                + "by \(magnitude(difference)) points"
        }
    }

    /// The difference's size at the shared move precision. A nonzero
    /// difference never reads as the "0.0" of a match.
    static func magnitude(_ difference: Double) -> String {
        let text = deltaPointsNumber(difference)
        return difference != 0 && text == deltaPointsNumber(0) ? "<0.1" : text
    }

    /// Names the figure a finished card does not carry, or nil when it carries
    /// both.
    static func unavailable(_ card: NBALadderCard9483) -> String? {
        guard applies(card) else { return nil }
        switch (card.actual == nil, card.forecast == nil) {
        case (true, true): return "Actual final and pregame projection unavailable"
        case (true, false): return "Actual final unavailable"
        case (false, true): return "Pregame projection unavailable"
        case (false, false): return nil
        }
    }

    /// The overview as VoiceOver reads it: the sentence, then the figures in
    /// their own existing words, then whatever is unavailable.
    static func overviewSummary(_ card: NBALadderCard9483) -> String {
        guard applies(card) else { return "" }
        let figures = NBAScoringFigures9483.accessibilitySummary(for: card)
        return [performance(card).map { $0 + "." }, figures.isEmpty ? nil : figures,
                unavailable(card).map { $0 + "." }]
            .compactMap { $0 }
            .joined(separator: " ")
    }

    /// The parent's selected line on this finished card, by its exact option
    /// key, or nil. A key the card no longer carries selects nothing — never
    /// the first line or the card's default.
    static func selected(_ card: NBALadderCard9483, key: String?) -> NBALadderCard9483.Point? {
        guard applies(card), let key else { return nil }
        return card.points.first { $0.optionKey == key }
    }

    static func chance(_ point: NBALadderCard9483.Point) -> String? {
        point.chance.map { formatProbability($0) }
    }

    static func result(_ point: NBALadderCard9483.Point) -> String {
        switch point.result {
        case true?: return "Won"
        case false?: return "Lost"
        case nil: return "Result unavailable"
        }
    }

    /// The selected reading as VoiceOver reads it.
    static func readingSummary(_ point: NBALadderCard9483.Point?) -> String {
        guard let point else { return "Selected line unavailable." }
        let chance = chance(point).map { "Pregame chance: \($0)." } ?? "Pregame chance unavailable."
        let result = point.result == nil ? "Result unavailable." : "Result: \(result(point))."
        return "Selected line: \(point.label). \(chance) \(result)"
    }

    /// The colour of the line's own dot on the host's chart (`color(_:)` in
    /// `NBALadderCardView9483`), so the number and its mark agree.
    static func tint(_ point: NBALadderCard9483.Point, away: Color, home: Color) -> Color {
        point.side == .away ? away : home
    }
}

// MARK: - Above the chart

/// The finished card's performance sentence over the existing keyed figures.
/// With neither figure it prints only the unavailable line, never an empty
/// figure row that could read as a projection.
struct FinalLadderOverview9483: View {
    let card: NBALadderCard9483
    let awayColor: Color
    let homeColor: Color

    var body: some View {
        if FinalLadderComparison9483.applies(card) {
            VStack(alignment: .leading, spacing: 10) {
                if let sentence = FinalLadderComparison9483.performance(card) {
                    // Wraps between words at every size; never shrinks.
                    Text(sentence)
                        .font(.title3.weight(.bold))
                        .fixedSize(horizontal: false, vertical: true)
                }
                if card.actual != nil || card.forecast != nil {
                    NBAScoringFigures9483(card: card, awayColor: awayColor, homeColor: homeColor)
                }
                if let missing = FinalLadderComparison9483.unavailable(card) {
                    Text(missing)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(FinalLadderComparison9483.overviewSummary(card))
            .accessibilityAddTraits(.isHeader)
        }
    }
}

// MARK: - Below the chart

/// The parent's selected line: its name, the pregame chance large with the
/// hollow key, and the producer's result. The selection is the parent's
/// (`selectedOptionKey`); this view keeps none of its own.
struct FinalLadderReading9483: View {
    let card: NBALadderCard9483
    let selectedOptionKey: String?
    let awayColor: Color
    let homeColor: Color
    /// Opens the exact original's details, keyed by option. Nil: no control.
    var onDetails: ((String) -> Void)? = nil
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title2) private var chanceSize: CGFloat = 28

    private var point: NBALadderCard9483.Point? {
        FinalLadderComparison9483.selected(card, key: selectedOptionKey)
    }

    /// A Details control exists only for a resolved line with a callback.
    var hasDetailsAction: Bool { point != nil && onDetails != nil }

    /// What the Details control does: the resolved line's own option key.
    func openDetails() {
        guard let point, let onDetails else { return }
        onDetails(point.optionKey)
    }

    var body: some View {
        if FinalLadderComparison9483.applies(card) {
            VStack(alignment: .leading, spacing: 8) {
                Group {
                    if let point {
                        if typeSize.isAccessibilitySize {
                            stacked(point)
                        } else {
                            // Side by side only while the line's name and
                            // result fit whole beside the chance; otherwise
                            // stack, before the line is squeezed.
                            ViewThatFits(in: .horizontal) {
                                sideBySide(point)
                                stacked(point)
                            }
                        }
                    } else {
                        Text("Selected line unavailable")
                            .font(.headline)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(FinalLadderComparison9483.readingSummary(point))
                if let point {
                    details(point)
                }
            }
        }
    }

    /// The chance trailing beside the line. `ViewThatFits` measures it at its
    /// ideal width, so it is chosen only when every label fits on one line.
    private func sideBySide(_ point: NBALadderCard9483.Point) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 16) {
            line(point)
                .frame(maxWidth: .infinity, alignment: .leading)
            chance(point, trailing: true)
        }
    }

    /// The chance, or its absence, leading under the line.
    private func stacked(_ point: NBALadderCard9483.Point) -> some View {
        VStack(alignment: .leading, spacing: 12) {
            line(point)
            chance(point, trailing: false)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// The line's name over its result. The result is its own word, never a
    /// percentage.
    private func line(_ point: NBALadderCard9483.Point) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(point.label)
                .font(.title3.weight(.bold))
                .fixedSize(horizontal: false, vertical: true)
            Text(FinalLadderComparison9483.result(point))
                .font(point.result == nil ? .subheadline : .subheadline.weight(.semibold))
                .foregroundStyle(point.result == nil ? Color.secondary : Color.primary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The pregame chance at the comparison size, keyed hollow like its dot.
    /// The figure is never split or shrunk; the key and the absence wrap
    /// between words when stacked, and stay on one line when trailing.
    @ViewBuilder private func chance(_ point: NBALadderCard9483.Point, trailing: Bool) -> some View {
        if let chance = FinalLadderComparison9483.chance(point) {
            VStack(alignment: trailing ? .trailing : .leading, spacing: 4) {
                Text(chance)
                    .font(.system(size: chanceSize, weight: .bold).monospacedDigit())
                    .foregroundStyle(FinalLadderComparison9483.tint(point, away: awayColor, home: homeColor))
                    .fixedSize()
                Label("Pregame chance", systemImage: "circle")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: trailing, vertical: true)
            }
        } else {
            Text("Pregame chance unavailable")
                .font(.subheadline.weight(.semibold))
                .foregroundStyle(.secondary)
                .multilineTextAlignment(trailing ? .trailing : .leading)
                .fixedSize(horizontal: trailing, vertical: true)
        }
    }

    /// With a callback, a 44pt control for the exact original. Without one,
    /// nothing: the line, result and chance already say the reading, and the
    /// host keeps the original's inspection — no dead control, no footer.
    @ViewBuilder private func details(_ point: NBALadderCard9483.Point) -> some View {
        if hasDetailsAction {
            Button { openDetails() } label: {
                HStack(spacing: 4) {
                    Text("Details & timing")
                    Image(systemName: "chevron.right").imageScale(.small)
                }
                .font(.subheadline)
                .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
                .contentShape(Rectangle())
            }
            .accessibilityLabel(NBAScoringLineControls9483.detailsLabel(point))
            .accessibilityHint("Shows this line's recorded probability and timing")
        }
    }
}
