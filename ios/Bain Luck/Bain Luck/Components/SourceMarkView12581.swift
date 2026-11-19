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
    /// Optional team or competitor name when the card shows two sides (#12989 follow-up).
    let subject: String?
    /// True when the tapped number is a finished game's pregame reading (#12989 follow-up).
    let isPregame: Bool
    /// The font size of the number the ring follows; the ring is 0.7 of it.
    let numberSize: CGFloat
    /// Compact dense-list mode keeps row height tight while expanding hit area via `.contentShape`.
    var compactRow: Bool = false
    /// True when the row prints one decimal place ("4.6%"), so the sheet's headline and source prices print tenths too.
    var showsTenths: Bool = false

    @State private var open = false

    /// The ring's share of the number's type size (Alex's ruling: about 0.7).
    static let ringScale: CGFloat = 0.7

    init?(
        _ mark: SourceMark?,
        number: Double? = nil,
        subject: String? = nil,
        isPregame: Bool = false,
        numberSize: CGFloat,
        compactRow: Bool = false,
        showsTenths: Bool = false
    ) {
        guard let mark, mark.draws else { return nil }
        self.mark = mark
        self.number = number
        self.subject = subject
        self.isPregame = isPregame
        self.numberSize = numberSize
        self.compactRow = compactRow
        self.showsTenths = showsTenths
    }

    var body: some View {
        Button { open = true } label: {
            Image(systemName: "info.circle")
                .font(.system(size: numberSize * Self.ringScale))
                .foregroundStyle(Color.secondary.opacity(0.55))
                // A 44pt tap target around a ring that stays quiet (compact rows keep
                // visual height tight and extend hit testing via negative inset).
                .frame(minWidth: compactRow ? 22 : 28, minHeight: compactRow ? 20 : 44)
                .contentShape(Rectangle().inset(by: compactRow ? -10 : 0))
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Where this number comes from")
        .accessibilityIdentifier("source-mark-12581")
        .sheet(isPresented: $open) {
            SourceMarkSheet(
                mark: mark,
                number: number,
                subject: subject,
                isPregame: isPregame,
                showsTenths: showsTenths
            )
            .presentationDetents([.medium, .large])
        }
    }
}

/// The sheet: the number the reader tapped, large and whole (or with tenths when the
/// row prints tenths); one row per source the server listed, in its order, with the
/// source's name, its price at matching precision and how old that price is (no age
/// when the server sent no observation time); then one line of method. A settled
/// number says "Official result" first.
struct SourceMarkSheet: View {
    let mark: SourceMark
    var number: Double? = nil
    var subject: String? = nil
    var isPregame: Bool = false
    var showsTenths: Bool = false
    var now: Date = Date()
    @Environment(\.dismiss) private var dismiss

    static let title = "Where this number comes from"

    static func formatSheetProbability(_ probability: Double, showsTenths: Bool) -> String {
        guard showsTenths else {
            return formatProbability(probability)
        }
        let pct = probability * 100
        if pct > 0 && pct < 0.05 { return "<0.1%" }
        if pct > 99.95 && pct < 100 { return ">99.9%" }
        return String(format: "%.1f%%", pct)
    }

    static func contextLine(subject: String?, isPregame: Bool) -> String? {
        let trimmed = subject?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        if !trimmed.isEmpty && isPregame { return "\(trimmed) · Pregame" }
        if !trimmed.isEmpty { return trimmed }
        if isPregame { return "Pregame" }
        return nil
    }

    /// When one unscaled venue stands behind the tapped number and its rounded
    /// price equals the headline, state the venue once ("From Kalshi", "From
    /// Sportsbooks (12) · 4m ago") instead of repeating both the venue and the
    /// percentage across a row and a possessive footer.
    static func singleUnscaledAttribution(
        _ mark: SourceMark,
        headline: String?,
        showsTenths: Bool = false,
        now: Date = Date()
    ) -> String? {
        guard (mark.state == .single || mark.state == .blend),
              mark.sources.count == 1,
              Self.settledLine(mark, now: now) == nil,
              mark.method?.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty != false,
              let headline,
              let only = Self.lines(mark, showsTenths: showsTenths, now: now).first,
              only.price == headline else {
            return nil
        }
        if let age = only.age {
            return "From \(only.name) · \(age)"
        }
        return "From \(only.name)"
    }

    /// One source as the sheet prints it.
    struct Line: Equatable {
        let name: String
        let price: String?
        let age: String?
    }

    static func lines(_ mark: SourceMark, showsTenths: Bool = false, now: Date = Date()) -> [Line] {
        mark.sources.map { source in
            Line(name: source.count.map { "\(source.name) (\($0))" } ?? source.name,
                 price: source.probability.map { formatSheetProbability($0, showsTenths: showsTenths) },
                 age: SourceAge.format(source.observedAt, now: now))
        }
    }

    /// The tapped number, matching the row's precision.
    static func headline(_ number: Double?, showsTenths: Bool = false) -> String? {
        number.map { formatSheetProbability($0, showsTenths: showsTenths) }
    }

    /// One line of method under the rows. Multi-source blends and scaled
    /// single-source marks print the server's `method` when present and non-empty;
    /// otherwise multi-source blends print "Bain Luck blend" and one-source marks
    /// name that source ("Kalshi's price", "Sportsbooks' price", 145-A / #12873).
    static func method(_ mark: SourceMark) -> String? {
        let served = mark.method?.trimmingCharacters(in: .whitespacesAndNewlines)
        switch mark.state {
        case .blend where mark.sources.count > 1:
            return (served?.isEmpty == false) ? served : "Bain Luck blend"
        case .blend, .single:
            guard let first = mark.sources.first else { return nil }
            if let served, !served.isEmpty {
                return served
            }
            let name = first.name.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !name.isEmpty else { return nil }
            return name.lowercased().hasSuffix("s") ? "\(name)' price" : "\(name)'s price"
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
        let headlineText = Self.headline(number, showsTenths: showsTenths)
        let contextText = Self.contextLine(subject: subject, isPregame: isPregame)
        let singleAttribution = Self.singleUnscaledAttribution(mark, headline: headlineText, showsTenths: showsTenths, now: now)
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if contextText != nil || headlineText != nil {
                        VStack(alignment: .leading, spacing: 2) {
                            if let contextText {
                                Text(contextText)
                                    .font(.subheadline.weight(.semibold))
                                    .foregroundStyle(.secondary)
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                            if let headlineText {
                                Text(headlineText)
                                    .font(.system(size: 44, weight: .bold))
                                    .monospacedDigit()
                                    .frame(maxWidth: .infinity, alignment: .leading)
                            }
                        }
                    }
                    if let singleAttribution {
                        Text(singleAttribution)
                            .font(.body)
                            .foregroundStyle(.secondary)
                            .padding(.top, 2)
                    } else {
                        rows
                        if let method = Self.method(mark) {
                            Text(method).font(.footnote).foregroundStyle(.secondary)
                        }
                    }
                }
                .padding()
            }
                #if os(iOS)
                .navigationBarTitleDisplayMode(.inline)
                #else
                .navigationTitle(Self.title)
                #endif
                .toolbar {
                    #if os(iOS)
                    ToolbarItem(placement: .principal) {
                        Text(Self.title)
                            .font(.subheadline.weight(.semibold))
                            .lineLimit(1)
                            .minimumScaleFactor(0.72)
                    }
                    #endif
                    ToolbarItem(placement: .confirmationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
    }

    /// The sheet's rows, the settled line first. Plain stacks rather than a
    /// `List`, so the rows are one view a fixture render can photograph.
    var rows: some View {
        let lines = (Self.settledLine(mark, now: now).map { [$0] } ?? []) + Self.lines(mark, showsTenths: showsTenths, now: now)
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
