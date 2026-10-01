import SwiftUI

/// #10076 — the header of one Player Props group: the stat name, the grey
/// chance caption ("chance of hitting" / "last quoted chance"), and on a
/// finished game the "Final N" the stat landed on.
///
/// These used to sit in one `HStack`, both `lineLimit(1)` at equal priority, so
/// in the ~155 pt paired column of an iPhone 17 there was room for only one of
/// them and SwiftUI clipped the stat name — tonight's Steelers @ Browns read
/// "PASSING ATTE…" beside a whole "chance of hitting". The name is the fact the
/// rungs below it are about; the caption is boilerplate.
///
/// So: one line when everything fits (the old look, unchanged), otherwise the
/// caption drops to its own line under the name. Nothing is truncated unless the
/// name alone is wider than the column, and then "Final N" still keeps its
/// priority over it (#4959).
struct PropsStatGroupHeader: View {
    let label: String
    let caption: String?
    var finalText: String? = nil

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(spacing: 4) {
                labelText
                captionText
                finalReadout
            }
            VStack(alignment: .leading, spacing: 1) {
                HStack(spacing: 4) {
                    labelText
                    finalReadout
                }
                captionText
            }
        }
    }

    private var labelText: some View {
        Text(label)
            .font(.system(size: 8, weight: .bold))
            .tracking(0.5)
            .foregroundStyle(.tertiary)
            .lineLimit(1)
    }

    @ViewBuilder
    private var captionText: some View {
        if let caption {
            Text(caption)
                .font(.system(size: 8))
                .foregroundStyle(.quaternary)
                .lineLimit(1)
        }
    }

    @ViewBuilder
    private var finalReadout: some View {
        if let finalText {
            Spacer(minLength: 2)
            Text(finalText)
                .font(.system(size: 8, weight: .semibold))
                .monospacedDigit()
                .foregroundStyle(.secondary)
                .lineLimit(1)
                .fixedSize(horizontal: true, vertical: false)
                .layoutPriority(1)
        }
    }
}
