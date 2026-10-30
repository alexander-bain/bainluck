import SwiftUI

// #11449 — the probability region of a soccer headline: home win, Draw and
// away win as three equal named outcomes, each with its primary reading and,
// when the owner supplies one, a comparison reading at the same size.
//
// Presentation only. Every string arrives resolved by the owner and is shown
// verbatim: this layer never chooses pregame versus current versus final,
// never rounds, normalizes, complements or parses a value, and never lets one
// reading — or one reading's missing explanation — stand in for the other.
// Score, result and game state stay in the surrounding header.

/// One named outcome. Each reading carries the owner's own words for its
/// absence: a missing primary ("No recent observation") is not the reason a
/// pre-match baseline is missing, so neither message stands in for the other.
nonisolated struct SoccerOutcomeSlot11449: Equatable {
    let label: String
    let color: Color
    let primary: String?
    let comparison: String?
    let primaryUnavailable: String
    let comparisonUnavailable: String
}

/// What a row of readings is ("Recorded after kickoff") and, separately, its
/// dated source context ("Oct 11, 7:57 AM · Kalshi only").
nonisolated struct SoccerReadingHeading11449: Equatable {
    let title: String
    let context: String?

    var spoken: String { context.map { "\(title): \($0)" } ?? title }
}

nonisolated enum SoccerSlotText11449: Equatable {
    case value(String)
    case unavailable(String)

    var spoken: String {
        switch self {
        case .value(let text), .unavailable(let text): text
        }
    }
}

/// Exactly three explicit outcomes. A comparison heading turns the comparison
/// row on even when every comparison value is missing; no heading, no row.
nonisolated struct SoccerThreeOutcomeHeadlineInput11449: Equatable {
    let home: SoccerOutcomeSlot11449
    let draw: SoccerOutcomeSlot11449
    let away: SoccerOutcomeSlot11449
    let primaryHeading: SoccerReadingHeading11449
    let comparisonHeading: SoccerReadingHeading11449?

    /// Fixed home / Draw / away order — never sorted or matched by label.
    var outcomes: [SoccerOutcomeSlot11449] { [home, draw, away] }

    func primaryText(for outcome: SoccerOutcomeSlot11449) -> SoccerSlotText11449 {
        outcome.primary.map(SoccerSlotText11449.value) ?? .unavailable(outcome.primaryUnavailable)
    }

    /// Nil only when the owner supplied no comparison heading.
    func comparisonText(for outcome: SoccerOutcomeSlot11449) -> SoccerSlotText11449? {
        guard comparisonHeading != nil else { return nil }
        return outcome.comparison.map(SoccerSlotText11449.value) ?? .unavailable(outcome.comparisonUnavailable)
    }

    /// Phase, date and source context, read once ahead of the outcomes.
    var accessibilityContext: String {
        ([primaryHeading] + (comparisonHeading.map { [$0] } ?? []))
            .map(\.spoken)
            .joined(separator: ". ")
    }

    func accessibilityLabel(for outcome: SoccerOutcomeSlot11449) -> String {
        var parts = [outcome.label, "\(primaryHeading.title): \(primaryText(for: outcome).spoken)"]
        if let heading = comparisonHeading, let text = comparisonText(for: outcome) {
            parts.append("\(heading.title): \(text.spoken)")
        }
        return parts.joined(separator: ". ")
    }

    /// VoiceOver order: context, then home, Draw, away.
    var accessibilityElements: [String] {
        [accessibilityContext] + outcomes.map(accessibilityLabel(for:))
    }
}

struct SoccerThreeOutcomeHeadline11449: View {
    let input: SoccerThreeOutcomeHeadlineInput11449
    @Environment(\.dynamicTypeSize) private var typeSize
    @ScaledMetric(relativeTo: .title) private var figureSize: CGFloat = 26

    private var figureFont: Font { .system(size: figureSize, weight: .bold).monospacedDigit() }

    var body: some View {
        Group {
            if typeSize.isAccessibilitySize {
                blocks
            } else {
                // Columns first; full named blocks before anything clips.
                ViewThatFits(in: .horizontal) {
                    columns
                    blocks
                }
            }
        }
        .padding(14)
        .frame(maxWidth: 560, alignment: .leading)
        .background(DS.surface, in: RoundedRectangle(cornerRadius: 14))
        .accessibilityElement(children: .contain)
        .accessibilityChildren {
            VStack {
                ForEach(Array(input.accessibilityElements.enumerated()), id: \.offset) { _, line in
                    Text(line)
                }
            }
        }
    }

    // MARK: Columns — names on top, each reading row under its full-width heading

    private var columns: some View {
        VStack(alignment: .leading, spacing: 10) {
            EqualColumns11449(spacing: 12) {
                ForEach(input.outcomes.indices, id: \.self) { i in
                    WholeWordsText11449(text: input.outcomes[i].label, font: .headline)
                }
            }
            heading(input.primaryHeading, wholeWords: true)
            EqualColumns11449(spacing: 12) {
                ForEach(input.outcomes.indices, id: \.self) { i in
                    columnValue(input.primaryText(for: input.outcomes[i]), color: input.outcomes[i].color)
                }
            }
            if let comparison = input.comparisonHeading {
                heading(comparison, wholeWords: true)
                    .padding(.top, 4)
                EqualColumns11449(spacing: 12) {
                    ForEach(input.outcomes.indices, id: \.self) { i in
                        if let text = input.comparisonText(for: input.outcomes[i]) {
                            columnValue(text, color: input.outcomes[i].color)
                        }
                    }
                }
            }
        }
    }

    /// A value stays on one line — if it cannot, the columns do not fit and
    /// the blocks take over. Unavailable prose wraps at body size.
    @ViewBuilder private func columnValue(_ text: SoccerSlotText11449, color: Color) -> some View {
        switch text {
        case .value(let value):
            Text(value)
                .font(figureFont)
                .foregroundStyle(color)
                .fixedSize()
        case .unavailable(let note):
            WholeWordsText11449(text: note, font: .body)
                .foregroundStyle(.secondary)
        }
    }

    // MARK: Blocks — each named outcome keeps its labels and values together

    private var blocks: some View {
        VStack(alignment: .leading, spacing: 16) {
            VStack(alignment: .leading, spacing: 8) {
                heading(input.primaryHeading, wholeWords: false)
                if let comparison = input.comparisonHeading {
                    heading(comparison, wholeWords: false)
                }
            }
            ForEach(input.outcomes.indices, id: \.self) { i in
                let outcome = input.outcomes[i]
                VStack(alignment: .leading, spacing: 8) {
                    Text(outcome.label)
                        .font(.headline)
                        .fixedSize(horizontal: false, vertical: true)
                    blockReading(input.primaryHeading.title, input.primaryText(for: outcome), color: outcome.color)
                    if let comparison = input.comparisonHeading, let text = input.comparisonText(for: outcome) {
                        blockReading(comparison.title, text, color: outcome.color)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    private func blockReading(_ title: String, _ text: SoccerSlotText11449, color: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(title)
                .font(.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            switch text {
            case .value(let value):
                Text(value)
                    .font(figureFont)
                    .foregroundStyle(color)
                    .fixedSize(horizontal: false, vertical: true)
            case .unavailable(let note):
                Text(note)
                    .font(.body)
                    .foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    // MARK: Headings

    @ViewBuilder private func heading(_ heading: SoccerReadingHeading11449, wholeWords: Bool) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            if wholeWords {
                WholeWordsText11449(text: heading.title, font: .subheadline.weight(.semibold))
                if let context = heading.context {
                    WholeWordsText11449(text: context, font: .subheadline)
                        .foregroundStyle(.secondary)
                }
            } else {
                Text(heading.title)
                    .font(.subheadline.weight(.semibold))
                    .fixedSize(horizontal: false, vertical: true)
                if let context = heading.context {
                    Text(context)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// Wraps between words but never inside one: the widest word is the text's
/// ideal width, so a column too narrow for "Wolverhampton" makes the columns
/// layout not fit instead of splitting the name.
private struct WholeWordsText11449: View {
    let text: String
    let font: Font

    var body: some View {
        ZStack(alignment: .topLeading) {
            ForEach(Array(text.split(whereSeparator: \.isWhitespace).enumerated()), id: \.offset) { _, word in
                Text(word).font(font).fixedSize().hidden()
            }
            Text(text)
                .font(font)
                .fixedSize(horizontal: false, vertical: true)
                .frame(idealWidth: 0, maxWidth: .infinity, alignment: .leading)
        }
    }
}

/// Three equal columns. Its ideal width is the widest cell times the count,
/// so `ViewThatFits` rejects it when any one cell would not fit its share.
private struct EqualColumns11449: Layout {
    let spacing: CGFloat

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        guard !subviews.isEmpty else { return .zero }
        let count = CGFloat(subviews.count)
        let gaps = spacing * (count - 1)
        let width: CGFloat
        if let proposed = proposal.width, proposed.isFinite {
            width = proposed
        } else {
            width = (subviews.map { $0.sizeThatFits(.unspecified).width }.max() ?? 0) * count + gaps
        }
        let column = max(0, (width - gaps) / count)
        let height = subviews.map { $0.sizeThatFits(ProposedViewSize(width: column, height: nil)).height }.max() ?? 0
        return CGSize(width: width, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        guard !subviews.isEmpty else { return }
        let count = CGFloat(subviews.count)
        let column = max(0, (bounds.width - spacing * (count - 1)) / count)
        for (i, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + CGFloat(i) * (column + spacing), y: bounds.minY),
                          anchor: .topLeading,
                          proposal: ProposedViewSize(width: column, height: nil))
        }
    }
}
