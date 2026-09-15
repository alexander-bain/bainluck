import SwiftUI

/// THE MARK THAT SAYS A PRICE HAS GONE QUIET — native half of #6343.
///
/// The drawing half of `SourceAge`; read that file's header for the bounds, the
/// vocabulary and the two deliberate divergences from the web. Mirrors
/// `frontend/components/event/PriceAgeMark.tsx`.
///
/// ═══ THE DECISION IS THE INITIALISER, AND THAT IS ON PURPOSE ═══
///
/// `init?` returns nil rather than the view returning `EmptyView`, so "should this
/// draw?" is a value a test can assert instead of a branch buried in a `body` no
/// XCTest can reach. The web component answers the same question by returning
/// `null`; this is that, in the one shape Swift can hold to it. It also means a
/// caller cannot construct a mark with an age it did not earn — there is no other
/// initialiser.
///
/// ═══ IT RENDERS NOTHING IN THREE CASES, AND ONLY TWO OF THEM ARE HERE ═══
///
///  1. **Inside the cadence** — the common case. A price being replaced on
///     schedule is not news.
///  2. **Undatable** — via `SourceAge.isStale` answering false for a stamp it
///     cannot read. An absent price age is not a fresh one and not a stale one;
///     it is a thing we cannot make a claim about.
///  3. **The question is already answered** — NOT here. A settled market's prices
///     are all old, the card already says so once, and "3d ago" on top of that
///     re-states the header while burying the one case this mark exists for: an
///     OPEN question whose price has gone quiet. Staleness is only news while the
///     answer is still open. Web's `SpecialEventMarkets` has the same rule.
///
/// That third one is the caller's because the caller holds the lifecycle, and a
/// settlement opinion computed in here would be a fifth authority beside the four
/// `FeedLifecycle` already reconciles. `FeedFuturesData.discoverPriceAgeMark`
/// below is the Discover card's composition of the two, in one testable place.
nonisolated struct PriceAgeMarkView: View {
    /// The rendered age, already earned. "3d ago".
    let age: String

    /// The precise stamp sentence, for the tap and for VoiceOver. Nil only if the
    /// stamp parsed for the age and not for the reveal, which cannot happen —
    /// both read the same parse — but the render must not be what discovers they
    /// disagreed.
    let sentence: String?

    /// Called with the reveal sentence on tap or long-press. Omit on a surface
    /// with nowhere to put a caption — the chip and the VoiceOver label still
    /// work, which is what keeps the sentence reachable everywhere.
    var onReveal: ((String) -> Void)?

    /// THE WHOLE RULE, and the only way to make one of these.
    ///
    /// Nil when the price is inside its cadence or cannot be dated. `cadence`
    /// defaults to the live bound so a caller that says nothing gets web's
    /// pre-#5843 behaviour; the futures surfaces pass the other one.
    ///
    /// `now` is injectable (gotcha #44) — production passes nothing.
    init?(
        observedAt: String?,
        cadence: SourceAge.Cadence = .live,
        now: Date = Date(),
        onReveal: ((String) -> Void)? = nil
    ) {
        guard SourceAge.isStale(observedAt, now: now, after: cadence.staleAfter),
              let age = SourceAge.format(observedAt, now: now)
        else { return nil }

        self.age = age
        self.sentence = SourceAge.reveal(observedAt)
        self.onReveal = onReveal
    }

    var body: some View {
        HStack(spacing: 4) {
            // A 5px dot, like the web's. Small enough that the chip cannot take a
            // line away from the source mark beside it.
            Circle()
                .fill(DS.textMuted.opacity(0.6))
                .frame(width: 5, height: 5)

            Text(age)
                .font(.system(size: 10))
                .foregroundStyle(DS.textMuted)
                .lineLimit(1)
                // The rungs are bounded ("59m ago", "23h ago"), so this cannot
                // grow without bound — but at a large Dynamic Type setting a card
                // should lose the age before it loses the market's name.
                .layoutPriority(-1)
        }
        .contentShape(Rectangle().inset(by: -8))
        .onTapGesture { sentence.map { onReveal?($0) } }
        .onLongPressGesture(minimumDuration: 0.35) { sentence.map { onReveal?($0) } }
        .accessibilityElement(children: .ignore)
        // "3d ago" alone tells a screen reader nothing about WHAT is three days
        // old. The spoken version carries the subject and the precise stamp.
        .accessibilityLabel(sentence.map { "Price \(age). \($0)" } ?? "Price \(age)")
        .accessibilityAddTraits(onReveal == nil ? [] : .isButton)
    }
}

// MARK: - The Discover card's composition

extension FeedFuturesData {
    /// #6343 — the Discover futures card's WHOLE price-age decision: the settled
    /// suppression and the cadence choice, together, in one expression a guard can
    /// pin.
    ///
    /// 🔴 IT LIVES HERE RATHER THAN INLINE IN THE CARD because a rule spelled in a
    /// `body` is a rule no test can reach: the cadence could silently become
    /// `.live` — #5843's defect, which marks fourteen of sixteen cards and makes
    /// the mark worthless — and every assertion about `SourceAge` would still pass.
    ///
    /// The cadence is `.futures` because these ladders are polled hourly at best
    /// (`poll-polymarket-hourly`, `poll-kalshi`, `refresh-stale-futures-prices`),
    /// so the 30-minute live bound is HALF the cadence and comes on for the back
    /// half of every hour.
    func discoverPriceAgeMark(
        now: Date = Date(),
        onReveal: ((String) -> Void)? = nil
    ) -> PriceAgeMarkView? {
        guard !FeedLifecycle.futuresIsSettled(self, now: now) else { return nil }
        return PriceAgeMarkView(
            observedAt: priceObservedAt,
            cadence: .futures,
            now: now,
            onReveal: onReveal
        )
    }
}

#if DEBUG
#Preview {
    struct Demo: View {
        @State private var revealed: String?

        // The two real specimens from the 2026-09-15 09:5xZ feed read, plus the
        // fourteen that must stay silent.
        private let now = Date(timeIntervalSince1970: 1_789_000_000)
        private func stamp(hoursAgo: Double) -> String {
            ISO8601DateFormatter().string(from: now.addingTimeInterval(-hoursAgo * 3600))
        }

        var body: some View {
            VStack(alignment: .leading, spacing: 14) {
                // Market 171 — Canadian Team to Win the Stanley Cup, 77.7h.
                HStack(spacing: 8) {
                    Text("Kalshi").font(.caption2.weight(.heavy)).foregroundStyle(.blue)
                    Spacer()
                    PriceAgeMarkView(
                        observedAt: stamp(hoursAgo: 77.7),
                        cadence: .futures,
                        now: now,
                        onReveal: { revealed = revealed == $0 ? nil : $0 }
                    )
                }
                if let revealed {
                    LiquidityRevealCaption(sentence: revealed)
                }
                Divider()
                // Silent: inside the 6h futures cadence (the other fourteen).
                PriceAgeMarkView(observedAt: stamp(hoursAgo: 0.7), cadence: .futures, now: now)
                // Silent: undatable.
                PriceAgeMarkView(observedAt: nil, cadence: .futures, now: now)
                // Drawn: the SAME 0.7h price on a live-cadence surface.
                PriceAgeMarkView(observedAt: stamp(hoursAgo: 0.7), cadence: .live, now: now)
            }
            .padding()
        }
    }
    return Demo()
}
#endif
