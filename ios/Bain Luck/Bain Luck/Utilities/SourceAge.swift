import Foundation

/// HOW OLD IS THE PRICE BEHIND THIS NUMBER — the native half (#6343).
///
/// ═══ THE MIRROR PAIR ═══
///
/// Same arrangement `LiquidityMarkView` documents at the top of its own file,
/// and the same reason: two drawings of one signal drift.
///
///   the rungs + the bounds -> frontend/lib/sourceAge.ts
///   the chip              -> frontend/components/event/PriceAgeMark.tsx
///   the native chip       -> Components/PriceAgeMarkView.swift
///
/// ═══ WHY THIS EXISTS: THE PHONE COULD NOT SAY IT AT ALL ═══
///
/// 🔴 #6343. `price_observed_at` has been on both futures-card serializers since
/// #5752 (`routes/feed.py`), the web has drawn it since #4970, and
/// `grep -rn price_observed_at ios/` returned **0 hits** — so no native surface
/// could render an age even in principle. Measured against `/api/feed?limit=25`
/// on 2026-09-15 09:5xZ: market `171` ("Canadian Team to Win the Stanley Cup")
/// at **77.7h** and `60856903` (a PGA second-round ladder) at **59.2h** were
/// drawing prices from three and two days earlier, marked `● 3d ago` / `● 2d ago`
/// on the website and completely unmarked on the phone.
///
/// ═══ IT DRAWS NOTHING ALMOST ALL OF THE TIME, AND THAT IS THE FEATURE ═══
///
/// The bound is the cadence that SHOULD have replaced the price, and picking the
/// wrong end of it is the defect #5843 fixed on the web. In the same read above,
/// **14 of the 16** datable cards sat at 0.7h: under the 30-minute live bound all
/// sixteen would have drawn a mark within the hour and the mark would say nothing
/// about the two that matter. Under the futures bound, **2 of 16** draw — and they
/// are the two a reader should see. An age has value exactly when it is surprising.
///
/// ═══ NO SECOND VOCABULARY ON THIS PLATFORM ═══
///
/// The rungs are `formatAgeFromSeconds`' rungs, value for value. Two deliberate
/// divergences from the web, both so the PHONE reads as one product — named here
/// so a later reader does not "correct" them into a third spelling:
///
///  1. **The precise stamp is `Liquidity.preciseObservedAt`**, not a local copy of
///     web's `formatSourceStamp`. The two differ only in field order ("12 Sep,
///     3:51 AM" vs "Sep 12, 3:51 AM") and native already shipped the first one in
///     the illiquidity reveal. It is *called*, not re-implemented, so the platform
///     has exactly one precise-stamp formatter.
///  2. **The reveal stem is "Last number"**, which is what both native surfaces
///     that date a price already say (`Liquidity.reveal`, and
///     `TournamentHubPresentation`'s "Last number 45 hours ago"), rather than
///     web's "Last seen". It is also the more accurate word: we do not receive
///     trades, and the stamp is when a probability last reached us.
///
/// The SHORT rungs ("3d ago") are kept for the chip even though the tournament
/// hub spells its sentence long ("3 days ago"), and that split is the web's own:
/// a dense chip beside a source mark and a full-width prose note are different
/// registers. The hub's note is a sentence; this is a mark.
///
/// ═══ `now` IS AN ARGUMENT ═══
///
/// Gotcha #44. A guard pins "7 hours draws, 5 does not" at a fixed instant rather
/// than building stamps relative to whenever the suite happens to run.
nonisolated enum SourceAge {

    // MARK: - The two bounds

    /// Sportsbook rows and live blocks, restamped every 2 minutes by
    /// `poll_live_prediction_markets`. Mirrors web's `SOURCE_STALE_AFTER_MS`,
    /// which is itself lifted from `BookmakerTable`.
    static let liveStaleAfter: TimeInterval = 30 * 60

    /// The hourly-polled ladders. The backend's own number, not one tuned here:
    /// `utils/tournament_register.py` carries `STALE_PRICE_HOURS = 6.0` and
    /// `tasks/futures_price_refresh.py` cites it by name, so the producer and
    /// both renderers share one definition of stale rather than three.
    /// Mirrors web's `FUTURES_STALE_AFTER_MS`.
    static let futuresStaleAfter: TimeInterval = 6 * 60 * 60

    /// A named pair rather than a raw interval, for web's reason: a caller free
    /// to pass `45 * 60` is a caller free to invent a fourth definition of stale.
    enum Cadence: String, Sendable {
        case live
        case futures

        var staleAfter: TimeInterval {
            switch self {
            case .live: return SourceAge.liveStaleAfter
            case .futures: return SourceAge.futuresStaleAfter
            }
        }
    }

    // MARK: - Reading a stamp

    /// Seconds since `iso` was written, or nil when there is no readable stamp.
    ///
    /// 🔴 ABSENT IS NOT ZERO. A price we have never observed must not read as one
    /// observed a moment ago, so both absences return nil and the caller decides
    /// what to draw (which, for the mark, is nothing). `String.asDate` handles the
    /// stamp with fractional seconds and the one without — production serves both.
    static func ageSeconds(_ iso: String?, now: Date = Date()) -> TimeInterval? {
        guard let iso, let at = iso.asDate else { return nil }
        // Clamped, like web's `sourceAgeMs`: a stamp from the future is a clock
        // disagreement, not a negative age, and flooring it below would wrap.
        return max(0, now.timeIntervalSince(at))
    }

    /// "just now" / "3m ago" / "2h ago" / "yesterday" / "5d ago".
    ///
    /// Value for value with web's `formatAgeFromSeconds`, including the two rungs
    /// that are words rather than numbers. There is no seconds rung, for its
    /// reason: under a minute, "just now" is the honest reading everywhere.
    static func formatAge(seconds: TimeInterval) -> String {
        // Truncation equals floor here because `ageSeconds` clamps at zero.
        let mins = Int(seconds / 60)
        let hours = Int(seconds / 3600)
        let days = Int(seconds / 86_400)

        if mins < 1 { return "just now" }
        if mins < 60 { return "\(mins)m ago" }
        if hours < 24 { return "\(hours)h ago" }
        if days == 1 { return "yesterday" }
        return "\(days)d ago"
    }

    /// The rendered age for a stamp, or nil when it cannot be dated.
    static func format(_ iso: String?, now: Date = Date()) -> String? {
        guard let seconds = ageSeconds(iso, now: now) else { return nil }
        return formatAge(seconds: seconds)
    }

    /// Has this price stopped being replaced?
    ///
    /// FALSE for an undatable stamp, and that is the conservative answer rather
    /// than the convenient one: a price we cannot date is not a price we can call
    /// stale. Mirrors web's `sourceIsStale`, including the strict `>`.
    static func isStale(
        _ iso: String?,
        now: Date = Date(),
        after: TimeInterval
    ) -> Bool {
        guard let seconds = ageSeconds(iso, now: now) else { return false }
        return seconds > after
    }

    // MARK: - The reveal

    /// "12 Sep, 3:51 AM" in the READER's own timezone — delegated, never copied.
    /// See divergence 1 in the header.
    static func preciseStamp(_ iso: String?) -> String? {
        guard let iso, let at = iso.asDate else { return nil }
        return Liquidity.preciseObservedAt(at)
    }

    /// What the tap and VoiceOver say: precisely when, which is Alex's word
    /// (2026-08-29) and the half a relative age cannot carry.
    ///
    /// On the web this sentence is the chip's `title` and the hover does the
    /// disclosing. The phone has no hover, so it is a tap — the same non-hover
    /// equivalent clause that shaped `LiquidityMarkView`, honoured here rather
    /// than left for whichever layout arrives next.
    ///
    /// Nil when the stamp cannot be read, which is also when the chip draws
    /// nothing, so a mark can never appear without its sentence.
    static func reveal(_ iso: String?) -> String? {
        guard let when = preciseStamp(iso) else { return nil }
        return "Last number: \(when)"
    }
}
