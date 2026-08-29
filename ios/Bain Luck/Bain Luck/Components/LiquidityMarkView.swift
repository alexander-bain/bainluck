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

    /// "Traded" rather than "liquid" — Alex's own word is *illiquid*, but that
    /// is the same class of vocabulary as "props/futures", which ruling 7
    /// removed from these surfaces for requiring a sportsbook to parse.
    var label: String? {
        switch self {
        case .thin: return "Thinly traded"
        case .barely: return "Barely traded"
        default: return nil
        }
    }

    var meaning: String? {
        switch self {
        case .thin: return "Treat this as a rough guide."
        case .barely: return "Treat this as little more than a guess."
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
    /// Mirrors `lib/liquidity.REASON_TEXT`.
    static func reasonText(_ reason: String) -> String? {
        switch reason {
        case "no_trades_24h":
            return "nobody has traded it in the last day"
        case "spread_exceeds_price":
            return "the gap between what buyers offer and what sellers want is wider than the number itself"
        default:
            return nil
        }
    }

    /// Said ONCE per surface, never per row. Mirrors
    /// `lib/liquidity.LIQUIDITY_DEFINITION` and
    /// `market_liquidity.LIQUIDITY_DEFINITION`.
    ///
    /// The second half is the load-bearing part: where a venue publishes
    /// nothing to check we cannot mark, so an UNMARKED number has not been
    /// cleared — it has been left alone.
    static let definition = """
        We mark a number when the market behind it is barely being traded — nobody has traded it in \
        the last day, or the gap between what buyers offer and what sellers want is wider than the \
        number itself. A half mark means one of those is true; a hollow mark means both are. Where a \
        venue publishes nothing to check against we cannot mark, so a number with no mark is one we \
        have not been able to question.
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

    /// The whole reveal, in ONE string — verdict, why, and precisely when.
    ///
    /// One string because it has to survive three disclosure paths on this
    /// platform (the tap sheet, the accessibility label, an inline caption) and
    /// a structured value would let two of them drift. Mirrors
    /// `lib/liquidity.liquidityReveal`, sentence for sentence.
    ///
    /// `nil` for `traded` and `unknown`, which is what makes "no mark" the
    /// cheap default rather than a case every caller has to remember.
    static func reveal(
        level: LiquidityLevel,
        reasons: [String],
        observedAt: Date? = nil
    ) -> String? {
        guard level.isMarked, let label = level.label, let meaning = level.meaning else {
            return nil
        }
        let texts = reasons.compactMap(reasonText)
        let because: String
        switch texts.count {
        case 0: because = ""
        case 1: because = " — \(texts[0])"
        default: because = " — \(texts[0]), and \(texts[1])"
        }
        // "Last number" and not "last traded": we do not receive trades, and the
        // timestamp is when a probability last reached us. Over-claiming here is
        // the easy mistake, and it is the one `FRESHNESS_DEFINITION` exists for.
        let last = preciseObservedAt(observedAt).map { " Last number: \($0)." } ?? ""
        return "\(label)\(because). \(meaning)\(last)"
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
