import SwiftUI

/// #12581 / 137-A — the source mark (Alex, Nov 3, recorded on #11920): one quiet
/// ring after a number, no letter, the same on every row whatever stands behind
/// it. A tap opens "Where this number comes from".
///
/// The decision is the initialiser (the `PriceAgeMarkView` shape): nil when the
/// served mark has nothing to say, so "does this row draw a mark?" is a value a
/// test can assert.
struct SourceMarkButton: View {
    let mark: SourceMark
    /// The font size of the number the ring follows; the ring is 0.7 of it.
    let numberSize: CGFloat

    @State private var open = false

    /// The ring's share of the number's type size (Alex's ruling: about 0.7).
    static let ringScale: CGFloat = 0.7

    init?(_ mark: SourceMark?, numberSize: CGFloat) {
        guard let mark, mark.draws else { return nil }
        self.mark = mark
        self.numberSize = numberSize
    }

    var body: some View {
        Button { open = true } label: {
            Circle()
                .strokeBorder(Color.secondary.opacity(0.55), lineWidth: 1)
                .frame(width: numberSize * Self.ringScale, height: numberSize * Self.ringScale)
                // A 44pt tap target around a ring that stays quiet.
                .frame(minWidth: 28, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Where this number comes from")
        .accessibilityIdentifier("source-mark-12581")
        .sheet(isPresented: $open) {
            SourceMarkSheet(mark: mark)
                .presentationDetents([.medium, .large])
        }
    }
}

/// The sheet: one row per source the server listed, in its order, with the
/// source's name, its price as a whole number and how old that price is. A
/// settled number says "Official result" first.
struct SourceMarkSheet: View {
    let mark: SourceMark
    var now: Date = Date()
    @Environment(\.dismiss) private var dismiss

    static let title = "Where this number comes from"

    /// One source as the sheet prints it.
    struct Line: Equatable {
        let name: String
        let price: String?
        let age: String?
    }

    static func lines(_ mark: SourceMark, now: Date = Date()) -> [Line] {
        mark.sources.map { source in
            Line(name: source.count.map { "\(source.name) (\($0))" } ?? source.name,
                 price: source.probability.map { "\(Int(($0 * 100).rounded()))%" },
                 age: SourceAge.format(source.observedAt, now: now))
        }
    }

    /// "Official result" and the result as served, for a settled number.
    static func settledLine(_ mark: SourceMark, now: Date = Date()) -> Line? {
        guard mark.state == .settled, let settled = mark.settled else { return nil }
        return Line(name: "Official result", price: settled.result, age: SourceAge.format(settled.at, now: now))
    }

    var body: some View {
        NavigationStack {
            ScrollView { rows.padding() }
                .navigationTitle(Self.title)
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #endif
                .toolbar {
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
    }

    /// The sheet's rows, the settled line first. Plain stacks rather than a
    /// `List`, so the rows are one view a fixture render can photograph.
    var rows: some View {
        let lines = (Self.settledLine(mark, now: now).map { [$0] } ?? []) + Self.lines(mark, now: now)
        return VStack(alignment: .leading, spacing: 0) {
            ForEach(Array(lines.enumerated()), id: \.offset) { index, line in
                if index > 0 { Divider() }
                row(line).padding(.vertical, 12)
            }
        }
    }

    private func row(_ line: Line) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Text(line.name).font(.body)
            Spacer(minLength: 8)
            if let price = line.price {
                Text(price).font(.body.weight(.semibold)).monospacedDigit()
            }
            if let age = line.age {
                Text(age).font(.caption).foregroundStyle(.secondary).monospacedDigit()
            }
        }
        .accessibilityElement(children: .combine)
    }
}
