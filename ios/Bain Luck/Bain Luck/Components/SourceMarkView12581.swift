import SwiftUI

/// #12581 / 137-A — the source mark (Alex, Nov 3, recorded on #11920; the glyph
/// is the ⓘ ring, 139-A, Nov 11): one quiet ⓘ after a number, the same on every
/// row whatever stands behind it. A tap opens "Where this number comes from".
///
/// The decision is the initialiser (the `PriceAgeMarkView` shape): nil when the
/// served mark has nothing to say, so "does this row draw a mark?" is a value a
/// test can assert.
struct SourceMarkButton: View {
    let mark: SourceMark
    /// The number the mark follows, as the row prints it; the sheet repeats it.
    let number: Double?
    /// The font size of the number the ring follows; the ring is 0.7 of it.
    let numberSize: CGFloat

    @State private var open = false

    /// The ring's share of the number's type size (Alex's ruling: about 0.7).
    static let ringScale: CGFloat = 0.7

    init?(_ mark: SourceMark?, number: Double? = nil, numberSize: CGFloat) {
        guard let mark, mark.draws else { return nil }
        self.mark = mark
        self.number = number
        self.numberSize = numberSize
    }

    var body: some View {
        Button { open = true } label: {
            Image(systemName: "info.circle")
                .font(.system(size: numberSize * Self.ringScale))
                .foregroundStyle(Color.secondary.opacity(0.55))
                // A 44pt tap target around a ring that stays quiet.
                .frame(minWidth: 28, minHeight: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Where this number comes from")
        .accessibilityIdentifier("source-mark-12581")
        .sheet(isPresented: $open) {
            SourceMarkSheet(mark: mark, number: number)
                .presentationDetents([.medium, .large])
        }
    }
}

/// The sheet: the number the reader tapped, large and whole; one row per source
/// the server listed, in its order, with the source's name, its price as a whole
/// number and how old that price is (no age when the server sent no observation
/// time); then one line of method. A settled number says "Official result" first.
struct SourceMarkSheet: View {
    let mark: SourceMark
    var number: Double? = nil
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
                 price: source.probability.map { formatProbability($0) },
                 age: SourceAge.format(source.observedAt, now: now))
        }
    }

    /// The tapped number, clamped like the row (`formatProbability`: "<1%" / ">99%").
    static func headline(_ number: Double?) -> String? {
        number.map { formatProbability($0) }
    }

    /// One line of method under the rows. "Bain Luck blend" only where the
    /// server's mark says the number is a blend of more than one source (145-A,
    /// Nov 11: props aren't blended for now, so a prop names its one venue).
    static func method(_ mark: SourceMark) -> String? {
        switch mark.state {
        case .blend where mark.sources.count > 1:
            return "Bain Luck blend, weighted by freshness and depth"
        case .blend, .single:
            return mark.sources.first.map { "\($0.name)'s price" }
        case .settled:
            return nil
        case .none, .unknown:
            return nil
        }
    }

    /// "Official result" and the result as served, for a settled number.
    static func settledLine(_ mark: SourceMark, now: Date = Date()) -> Line? {
        guard mark.state == .settled, let settled = mark.settled else { return nil }
        return Line(name: "Official result", price: settled.result, age: SourceAge.format(settled.at, now: now))
    }

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let headline = Self.headline(number) {
                        Text(headline)
                            .font(.system(size: 44, weight: .bold))
                            .monospacedDigit()
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    rows
                    if let method = Self.method(mark) {
                        Text(method).font(.footnote).foregroundStyle(.secondary)
                    }
                }
                .padding()
            }
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
