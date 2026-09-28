import Foundation

/// THE PAIR THE EVENT HERO PRINTS, AND WHETHER IT IS AN OPENING LINE (#9470,
/// the iPhone half; ux owns the web half).
///
/// The server's hero cascade (`app/utils/hero_probability.py`) ends on
/// `hero_probability_source: "opening"` when no source is left to blend — its
/// own words: "nobody has quoted this since the line was posted". The phone
/// never read that value. It printed `current_odds` under "Win Probability"
/// with confidence bars, so Packers–Bears (14780556, Oct 11) read
/// **40% – 60% · Win Probability** on 2026-09-28 from a sportsbook line last
/// confirmed on Sep 13, the Sunday the sportsbooks pulled every week-6+ NFL
/// line. 27 upcoming NFL games were in that state when latency measured it.
///
/// Two rules, and the second one is why this is not only a caption:
///
/// 1. On an opening hero the pair is named "Opening line", not "Win
///    Probability" with confidence bars, and the since-open caption is dropped
///    (an opening line compared with itself says nothing).
/// 2. The PAIR is the server's `hero_probability` pair, not `current_odds`.
///    `current_odds` is the latest sportsbook median, which on an opening-arm
///    event is a consensus below `BETTING_BOOK_FLOOR` (ruling 051 — the reason
///    the blend fell to the opening at all). Where one or two sportsbooks are
///    still quoting, it has moved off the opening, and a caption saying
///    "Opening line" over it would be a new false claim. The one number is the
///    server's (#3903); on 14780556 the two are the same 0.5996.
///
/// Pre-game only. A live page's `current_odds` is what pushed frames write
/// (`LiveEventPriceReconciliation`), and a finished page takes the verdict
/// branch before this is consulted; the server emits `opening` on neither
/// finished status.
nonisolated struct OpeningLineHero: Equatable, Sendable {
    let awayProbability: Double?
    let homeProbability: Double?
    /// Served whole percents. `nil` on the opening arm: the server rounds
    /// `current_odds`' pair only, so the hero pair is rounded locally as one
    /// pair by the caller's existing fallback (#2085).
    let awayRenderedPercent: Int?
    let homeRenderedPercent: Int?
    let isOpeningLine: Bool

    static let openingSource = "opening"
    static let caption = "Opening line"

    static func resolve(
        currentOdds: CurrentOdds,
        heroSource: String?,
        heroHome: Double?,
        heroAway: Double?,
        status: String?
    ) -> OpeningLineHero {
        if heroSource == openingSource,
           status != "live", !EventState.isFinished(status),
           let home = heroHome, home.isFinite, home > 0, home < 1 {
            return OpeningLineHero(
                awayProbability: heroAway.flatMap { $0.isFinite ? $0 : nil },
                homeProbability: home,
                awayRenderedPercent: nil,
                homeRenderedPercent: nil,
                isOpeningLine: true
            )
        }
        return OpeningLineHero(
            awayProbability: currentOdds.awayProbability,
            homeProbability: currentOdds.homeProbability,
            awayRenderedPercent: currentOdds.awayRenderedPercent,
            homeRenderedPercent: currentOdds.homeRenderedPercent,
            isOpeningLine: false
        )
    }
}
