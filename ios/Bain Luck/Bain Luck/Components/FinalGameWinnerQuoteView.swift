import SwiftUI

/// Separate from the result hero and settled prop buckets by construction.
struct FinalGameWinnerQuoteView: View {
    let quote: FinalGameWinnerQuote

    init?(quote: FinalGameWinnerQuote, eventId: Int, eventStatus: String?, closedMarketIds: Set<Int>) {
        guard quote.isPresentable(eventId: eventId, eventStatus: eventStatus,
                                  closedMarketIds: closedMarketIds) else { return nil }
        self.quote = quote
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Still trading")
                    .font(.headline)
                Spacer()
                Text(quote.source == "kalshi" ? "Kalshi" : "Polymarket")
                    .font(.caption)
                    .foregroundStyle(DS.textSecondary)
            }
            Text("The game is final. This winner market has not settled.")
                .font(.caption)
                .foregroundStyle(DS.textSecondary)
                .fixedSize(horizontal: false, vertical: true)
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
        }
        .padding(16)
        .background(DS.surface)
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .accessibilityIdentifier("final-game-open-winner-quote")
    }
}
