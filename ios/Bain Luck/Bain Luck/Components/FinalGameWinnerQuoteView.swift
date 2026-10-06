import SwiftUI

/// Separate from the result hero and settled prop buckets by construction.
/// #9484: the result is the hero's; this is compact secondary contract context,
/// never a second headline, and it asserts nothing about settlement or timing.
struct FinalGameWinnerQuoteView: View {
    let quote: FinalGameWinnerQuote

    init?(quote: FinalGameWinnerQuote, eventId: Int, eventStatus: String?, closedMarketIds: Set<Int>) {
        guard quote.isPresentable(eventId: eventId, eventStatus: eventStatus,
                                  closedMarketIds: closedMarketIds) else { return nil }
        self.quote = quote
    }

    static let caption = "Last market price. The result is the score above."

    static func header(source: String) -> String {
        (source == "kalshi" ? "Kalshi" : "Polymarket") + " winner market"
    }

    /// The market's own name, only when it says more than the two team names
    /// (Kalshi's "Game 2: …" does; Polymarket's bare matchup repeats the title).
    static func contextName(for quote: FinalGameWinnerQuote) -> String? {
        let name = quote.marketName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return nil }
        let connectors: Set<String> = ["vs", "v", "at", "versus"]
        func words(_ text: String) -> Set<String> {
            Set(text.lowercased().components(separatedBy: CharacterSet.alphanumerics.inverted)
                .filter { !$0.isEmpty })
        }
        let teams = quote.outcomes.reduce(into: Set<String>()) { $0.formUnion(words($1.name)) }
        return words(name).subtracting(connectors).isSubset(of: teams) ? nil : name
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(Self.header(source: quote.source))
                .font(.caption.weight(.semibold))
                .foregroundStyle(DS.textSecondary)
            if let context = Self.contextName(for: quote) {
                Text(context)
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            ForEach(quote.outcomes) { outcome in
                HStack(spacing: 8) {
                    Text(outcome.name)
                        .font(.subheadline)
                    Spacer(minLength: 8)
                    PriceAgeMarkView(observedAt: outcome.observedAt, cadence: .live)
                    // Quotes at the endpoints stay <1%/>99%; only the separate
                    // authoritative result can claim certainty.
                    Text(quote.printableProbabilities[outcome.outcomeId] ?? "—")
                        .font(.subheadline.weight(.semibold))
                        .monospacedDigit()
                }
                .accessibilityElement(children: .combine)
            }
            Text(Self.caption)
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(12)
        .background(DS.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .accessibilityIdentifier("final-game-open-winner-quote")
    }
}
