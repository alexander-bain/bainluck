import SwiftUI

// UX-P157 (#2256 / #2257) — the illiquidity mark, native half.
//
// Alex's ruling, 2026-08-28: a SYMBOL carries illiquidity, it GRADES (at least
// two levels, because illiquidity is not uniform), mouse-over reveals PRECISELY
// when the probability was last updated — and, in as many words, *native needs
// a non-hover equivalent (tap/long-press or inline subtext) designed at the same
// time, not later*. That last clause is why this file exists in the same queue
// as the web build rather than in a follow-up.
//
// THE MIRROR PAIR. Same arrangement `SignalBarsView` documents at the top of
// its own file, and the same reason: two drawings of one signal drift.
//
//   glyph + copy  -> frontend/components/LiquidityMark.tsx
//                    frontend/lib/liquidity.ts
//   the GRADE     -> backend/app/utils/market_liquidity.py   (the only owner)
//
// The grade is never computed here. It arrives on the payload as `liquidity`
// plus `liquidity_reasons`, exactly as it arrives on the web, because the
// ingredients are two database columns and a venue's own volume figure — and a
// second client-side opinion about one book is how two surfaces come to
// disagree about one number.
//
// NOT `SignalBarsView`. That glyph is the feed's `confidence_tier`: a BLENDED
// score over sources, movement, volume and agreement, in which volume is one
// weighted input. This is a single un-blended fact about one outcome's own
// book, which is what lets it be honest at the size of a grid cell where a
// blended score could not be.
//
// ═══ WHAT SURFACE CONSUMES IT TODAY, STATED PLAINLY ═══
//
// None yet. Checked 2026-08-28: the native app carries `DiscoverTournamentCard`,
// `TournamentHeroCard`, `TournamentCompactRow` and `TournamentChartView`, all of
// which render the golf-shaped feed payload — there is no native surface for the
// tournament hub's boards, bracket grid, match slate or questions section, so
// there is nothing here yet that receives `liquidity`.
//
// This ships anyway, and the reason is Alex's clause: designing the non-hover
// reveal LATER means designing it against whatever layout arrives first, which
// is how the web and the phone end up with two different answers to one
// question. The rendering contract is settled now, in the same queue that
// settled the web one, and `LiquidityMarkPresentationTests` holds it to the
// same two levels and the same sentence.

// MARK: - Level

/// Mirrors `market_liquidity.LIQUIDITY_*`. There is no fifth.
enum LiquidityLevel: String {
    case traded
    case thin
    case barely
    case unknown

    /// Read a payload value, failing closed.
    ///
    /// Anything unrecognised is `.unknown` and never a mark: a symbol invented
    /// from a value we do not understand is indistinguishable, on the screen,
    /// from one the backend measured.
    static func normalize(_ raw: String?) -> LiquidityLevel {
        guard let raw, let level = LiquidityLevel(rawValue: raw) else { return .unknown }
        return level
    }

    /// Only two of the four draw anything.
    var isMarked: Bool { self == .thin || self == .barely }

    /// What to do with a marked number, and the only place the GRADE survives
    /// in words. Alex's own register, 2026-08-29: *less reliable*.
    ///
    /// The two-word verdict ("Thinly traded") that used to open the reveal went
    /// with the mechanism he cut. The glyph already grades; *less* versus *much
    /// less* is the same ordering in the half of the sentence a reader acts on.
    /// Mirrors `lib/liquidity.LIQUIDITY_MEANING`.
    var meaning: String? {
        switch self {
        case .thin: return "treat it as less reliable"
        case .barely: return "treat it as much less reliable"
        default: return nil
        }
    }

    /// How much of the ring is filled, 0...1. Emptier is thinner, so a reader
    /// gets the ordering right without ever opening the reveal.
    var fill: Double {
        switch self {
        case .thin: return 0.5
        case .barely: return 0.0
        default: return 1.0
        }
    }
}

// MARK: - Copy

enum Liquidity {
    /// The one clause that says what is wrong, said the way Alex asked for it
    /// on 2026-08-29 — *the number isn't moving* — and never as the arithmetic
    /// that found it. Mirrors `lib/liquidity.REASON_STEM`.
    ///
    /// The wide-book stem deliberately makes no claim about movement: a market
    /// can be quoting an absurd range and still have traded this morning.
    static let noTradesStem = "This number hasn't moved in a while"
    static let wideBookStem = "Barely anybody is trading this market"

    static func reasonStem(_ reason: String) -> String? {
        switch reason {
        case "no_trades_24h": return noTradesStem
        case "spread_exceeds_price": return wideBookStem
        default: return nil
        }
    }

    /// Said ONCE per surface, never per row. Mirrors
    /// `lib/liquidity.LIQUIDITY_DEFINITION` and
    /// `market_liquidity.LIQUIDITY_DEFINITION`.
    ///
    /// The last sentence is the load-bearing part: where a venue publishes
    /// nothing to check we cannot mark, so an UNMARKED number has not been
    /// cleared — it has been left alone.
    static let definition = """
        We mark a number when the market behind it is barely being traded, which usually means it \
        hasn't moved in a while and is less reliable. A half mark means we found one sign of that; \
        a hollow mark means we found both. Where a venue publishes nothing to check against we \
        cannot mark, so a number with no mark is one we have not been able to question.
        """

    /// "27 Aug, 2:14 PM" in the READER's own timezone.
    ///
    /// Alex's constraint is "precisely when", and a relative age is the thing
    /// he already called ambiguous — "32 hours ago" leaves the reader doing
    /// arithmetic against a clock they have to guess at. Mirrors
    /// `lib/liquidity.preciseObservedAt`.
    static func preciseObservedAt(_ observedAt: Date?) -> String? {
        guard let observedAt else { return nil }
        let formatter = DateFormatter()
        formatter.dateFormat = "d MMM, h:mm a"
        return formatter.string(from: observedAt)
    }

    /// The whole reveal, in ONE string — what is wrong, what to do about it,
    /// and precisely when.
    ///
    /// One string because it has to survive three disclosure paths on this
    /// platform (the tap sheet, the accessibility label, an inline caption) and
    /// a structured value would let two of them drift. Mirrors
    /// `lib/liquidity.liquidityReveal`, sentence for sentence.
    ///
    /// ONE REASON, never both — Alex, 2026-08-29, on the version that listed
    /// both: *way too verbose*. The second clause bought the reader nothing,
    /// because the two facts do not lead to two different responses.
    /// `no_trades_24h` wins the tie and every `barely` carries it, so a hollow
    /// mark always reads as "hasn't moved".
    ///
    /// `nil` for `traded` and `unknown`, which is what makes "no mark" the
    /// cheap default rather than a case every caller has to remember.
    static func reveal(
        level: LiquidityLevel,
        reasons: [String],
        observedAt: Date? = nil
    ) -> String? {
        guard level.isMarked, let meaning = level.meaning else { return nil }
        // A payload that lost its reasons still gets a true sentence: the
        // wide-book stem claims only that the market is barely traded, which is
        // what being marked at all already means.
        let stem = reasons.contains("no_trades_24h") ? noTradesStem : wideBookStem
        // "Last number" and not "last traded": we do not receive trades, and the
        // timestamp is when a probability last reached us. Over-claiming here is
        // the easy mistake, and it is the one `FRESHNESS_DEFINITION` exists for.
        let last = preciseObservedAt(observedAt).map { " Last number: \($0)." } ?? ""
        return "\(stem) — \(meaning).\(last)"
    }
}

// MARK: - Glyph

/// A ring that empties as the market thins. Renders nothing when there is
/// nothing to say — the `SignalBarsView` "render-only-where-present" rule.
///
/// Bottom-filled rather than top-filled so it reads as a LEVEL in a container:
/// the same intuition as a battery, and the reason "emptier is thinner" needs
/// no key beside it.
nonisolated struct LiquidityGlyph: View {
    let level: LiquidityLevel
    var size: CGFloat = 10

    var body: some View {
        if level.isMarked {
            ZStack {
                Circle()
                    .strokeBorder(DS.textMuted, lineWidth: size * 0.125)
                if level.fill > 0 {
                    // The bottom half, clipped out of a filled circle. One shape
                    // scaled by `size`, not two hand-tuned drawings that happen
                    // to look alike at the two sizes we use.
                    Circle()
                        .fill(DS.textMuted)
                        .mask(alignment: .bottom) {
                            Rectangle().frame(height: size * level.fill)
                        }
                }
            }
            .frame(width: size, height: size)
        }
    }
}

// MARK: - The mark, with its non-hover reveal

/// The tappable mark. Draws the glyph, owns the affordance, and hands the
/// sentence up rather than guessing where it should be drawn.
///
/// THE NON-HOVER EQUIVALENT, which is the half Alex named. Three paths and one
/// sentence:
///
///   • **tap** — toggles the caller's inline caption. Tap again to close.
///   • **long-press** — the same thing without moving focus, for a mark that
///     sits inside a row which is itself a navigation target.
///   • **accessibility label** — VoiceOver reads the sentence directly, so the
///     glyph is never unexplained chrome.
///
/// Inline UNDER the row rather than a popover, and that is a decision rather
/// than a default: a popover on a phone covers the number the reader just asked
/// about, and this sentence is only meaningful while that number is on screen.
nonisolated struct LiquidityMarkView: View {
    /// The payload's `liquidity`.
    let liquidity: String?
    /// The payload's `liquidity_reasons`.
    var reasons: [String] = []
    /// When a probability for this question last reached us.
    var observedAt: Date?
    var size: CGFloat = 10
    /// Called with the reveal sentence on tap or long-press. Omit on a surface
    /// with nowhere to put a caption — the glyph and the VoiceOver label still
    /// work.
    var onReveal: ((String) -> Void)?

    private var level: LiquidityLevel { LiquidityLevel.normalize(liquidity) }

    var body: some View {
        if let sentence = Liquidity.reveal(
            level: level,
            reasons: reasons,
            observedAt: observedAt
        ) {
            LiquidityGlyph(level: level, size: size)
                // A comfortable target around an 10pt glyph. Without it the
                // mark is technically tappable and practically not.
                .contentShape(Rectangle().inset(by: -8))
                .onTapGesture { onReveal?(sentence) }
                .onLongPressGesture(minimumDuration: 0.35) { onReveal?(sentence) }
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(sentence)
                .accessibilityAddTraits(onReveal == nil ? [] : .isButton)
        }
    }
}

/// The caption the tap opens. Kept here rather than left to each caller so the
/// three future surfaces cannot invent three different panels.
nonisolated struct LiquidityRevealCaption: View {
    let sentence: String

    var body: some View {
        Text(sentence)
            .font(.system(size: 11.5))
            .foregroundColor(DS.textSecondary)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.horizontal, 9)
            .padding(.vertical, 7)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(DS.trackBg)
            .clipShape(RoundedRectangle(cornerRadius: 8, style: .continuous))
            .accessibilityHidden(true)  // the mark already announced it
    }
}

#if DEBUG
#Preview {
    struct Demo: View {
        @State private var revealed: String?

        var body: some View {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("Iga Swiatek")
                    Spacer()
                    Text("70%").bold().monospacedDigit()
                }
                HStack(spacing: 6) {
                    Text("Venus Williams")
                    Spacer()
                    LiquidityMarkView(
                        liquidity: "barely",
                        reasons: ["no_trades_24h", "spread_exceeds_price"],
                        observedAt: Date(timeIntervalSince1970: 1_787_000_040),
                        onReveal: { revealed = revealed == $0 ? nil : $0 }
                    )
                    Text("0.8%").bold().monospacedDigit()
                }
                if let revealed {
                    LiquidityRevealCaption(sentence: revealed)
                }
                Divider()
                HStack(spacing: 10) {
                    LiquidityGlyph(level: .thin)
                    LiquidityGlyph(level: .barely)
                    LiquidityGlyph(level: .traded)   // renders nothing
                    LiquidityGlyph(level: .unknown)  // renders nothing
                }
                Text(Liquidity.definition)
                    .font(.system(size: 11))
                    .foregroundColor(DS.textMuted)
            }
            .padding()
        }
    }
    return Demo()
}
#endif
