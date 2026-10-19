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
///
/// #11285 (Alex, build 65: "unreadably small") — the three draw in the reader's
/// caption style, not a fixed 8pt that never grew with the text setting. Where
/// even the name and "Final N" cannot share a line (large text in a narrow
/// column), the name wraps on its own lines and "Final N" leads the caption's
/// line, rather than the name being clipped.
struct PropsStatGroupHeader: View {
    let label: String
    let caption: String?
    var finalText: String? = nil

    var body: some View {
        ViewThatFits(in: .horizontal) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                labelText(wraps: false)
                captionText
                finalReadout
            }
            VStack(alignment: .leading, spacing: 1) {
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    labelText(wraps: false)
                    finalReadout
                }
                captionText
            }
            VStack(alignment: .leading, spacing: 1) {
                labelText(wraps: true)
                HStack(alignment: .firstTextBaseline, spacing: 4) {
                    if let finalText { finalValue(finalText) }
                    captionText
                }
            }
        }
    }

    private func labelText(wraps: Bool) -> some View {
        Text(label)
            .font(.caption.weight(.bold))
            .tracking(0.5)
            .foregroundStyle(.secondary)
            .lineLimit(wraps ? nil : 1)
            .fixedSize(horizontal: false, vertical: wraps)
    }

    @ViewBuilder
    private var captionText: some View {
        if let caption {
            Text(caption)
                .font(.caption)
                .foregroundStyle(.tertiary)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder
    private var finalReadout: some View {
        if let finalText {
            Spacer(minLength: 2)
            finalValue(finalText)
                .layoutPriority(1)
        }
    }

    private func finalValue(_ text: String) -> some View {
        Text(text)
            .font(.caption.weight(.semibold))
            .monospacedDigit()
            .foregroundStyle(.secondary)
            .lineLimit(1)
            .fixedSize(horizontal: true, vertical: false)
    }
}
