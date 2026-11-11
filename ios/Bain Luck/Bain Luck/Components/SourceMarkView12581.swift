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
    /// The number the mark follows, exactly as the row prints it ("58.3%",
    /// "86%"); a blend's sheet repeats it in the same precision.
    let figure: String?
    /// The font size of the number the ring follows; the ring is 0.7 of it.
    let numberSize: CGFloat

    @State private var open = false

    /// The ring's share of the number's type size (Alex's ruling: about 0.7).
    static let ringScale: CGFloat = 0.7

    init?(_ mark: SourceMark?, figure: String? = nil, numberSize: CGFloat) {
        guard let mark, mark.draws else { return nil }
        self.mark = mark
        self.figure = figure
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
            SourceMarkSheet(mark: mark, figure: figure)
                .presentationDetents(SourceMarkSheet.isOneVenue(mark) ? [.height(170)] : [.medium, .large])
        }
    }
}

/// "Where this number comes from" (#12581; Alex's second look, Nov 11).
///
/// - **A blend** (more than one source): the tapped number in the row's own
///   precision, one row per source the server listed, in its order, with its
///   price and age (no age when the server sent no observation time), then
///   "Bain Luck blend of these three". The server sends no method yet, so the
///   line claims only what the list shows; "weighted by freshness and depth"
///   was wrong (Builder B: the headline is a weighted median before play and a
///   guarded weighted average during it, never weighted by depth).
/// - **One venue** (a `blend` mark with one source is not a blend): said once,
///   "From Kalshi · 4m ago", with no number repeated.
/// - Settled and capped numbers draw no ⓘ at all (`SourceMark.draws`).
struct SourceMarkSheet: View {
    let mark: SourceMark
    var figure: String? = nil
    var now: Date = Date()
    @Environment(\.dismiss) private var dismiss

    static let title = "Where this number comes from"

    /// One source as the blend sheet prints it.
    struct Line: Equatable {
        let name: String
        let price: String?
        let age: String?
    }

    static func isOneVenue(_ mark: SourceMark) -> Bool {
        mark.state == .blend && mark.sources.count == 1
    }

    static func lines(_ mark: SourceMark, now: Date = Date()) -> [Line] {
        mark.sources.map { source in
            Line(name: source.count.map { "\(source.name) (\($0))" } ?? source.name,
                 price: source.probability.map { "\(Int(($0 * 100).rounded()))%" },
                 age: SourceAge.format(source.observedAt, now: now))
        }
    }

    /// The one-venue sheet's only line: "From Kalshi · 4m ago", or "From Kalshi"
    /// when the server reported no time.
    static func oneVenueLine(_ mark: SourceMark, now: Date = Date()) -> String? {
        guard isOneVenue(mark), let source = mark.sources.first else { return nil }
        let age = SourceAge.format(source.observedAt, now: now)
        return (["From \(source.name)"] + (age.map { [$0] } ?? [])).joined(separator: " · ")
    }

    /// The blend's last line: what the list shows, and nothing it doesn't.
    static func method(_ mark: SourceMark) -> String? {
        guard mark.state == .blend, mark.sources.count > 1 else { return nil }
        let words = [2: "two", 3: "three", 4: "four", 5: "five", 6: "six"]
        return "Bain Luck blend of these \(words[mark.sources.count] ?? String(mark.sources.count))"
    }

    var body: some View {
        NavigationStack {
            ScrollView { content.padding() }
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

    /// Everything under the title bar. Plain stacks rather than a `List`, so a
    /// fixture render can photograph it.
    @ViewBuilder var content: some View {
        if let line = Self.oneVenueLine(mark, now: now) {
            Text(line)
                .font(.body)
                .foregroundStyle(.secondary)
                .frame(maxWidth: .infinity, alignment: .leading)
        } else {
            VStack(alignment: .leading, spacing: 12) {
                if let figure {
                    Text(figure)
                        .font(.system(size: 44, weight: .bold))
                        .monospacedDigit()
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                rows
                if let method = Self.method(mark) {
                    Text(method).font(.footnote).foregroundStyle(.secondary)
                }
            }
        }
    }

    var rows: some View {
        let lines = Self.lines(mark, now: now)
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
