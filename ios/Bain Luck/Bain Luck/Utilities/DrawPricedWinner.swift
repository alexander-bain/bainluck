import Foundation

/// What a match surface may print when the winner market has THREE outcomes.
///
/// #5271. Every probability the event page draws for a match came from one
/// pair, and the pair is `home` and `1 − home`. On a two-outcome sport that is
/// exactly right, and the app leans on it hard — `routes/feed.py` derives
/// `current_odds.away_probability` as `round(1.0 - current_home_prob, 6)`, and
/// `renderedDuelPercents` is built on the two summing to one.
///
/// `1 − P(home)` is **"the home team does not win"**. In soccer that is *away
/// win **or** draw*, so the figure printed under the away crest silently
/// absorbs the entire draw probability.
///
/// Photographed on production 2026-09-11 (event `15304603`, Al-Faisaly KSA FC
/// v Al-Ittihad, live 0–2). One screen, one source — `win_probability_sources`
/// held `{"kalshi": {"value": 0.01}}` and nothing else:
///
/// | where | Al-Ittihad | Tie | Al-Faisaly |
/// |---|---|---|---|
/// | hero, top of page | **99%** | — | 1% |
/// | Other Markets card, same page | **93%** | 5% | 1% |
///
/// The reader scrolls two cards and the favourite loses six points. Alex found
/// the same 99% a third time in the goal-margin map's header. Mid-game at 0–2
/// the draw is nearly dead so the error is ~6pp; **pre-match a league draw
/// prices around 20–30%**, and every scheduled soccer fixture the app renders
/// is affected.
///
/// ═══ WHY THIS WITHHOLDS RATHER THAN CORRECTS ═══
///
/// The obvious fix — print the away team's real price — has nowhere to read one
/// from. Measured 2026-09-11 before this shipped:
///
///  * the event payload carries no draw and no independent away price: the away
///    field IS the complement;
///  * `win_prob_snapshots.draw_probability` exists, is served on the history
///    payload this view already fetches, and is **NULL on all 3,084,750 rows** —
///    no writer has ever set it;
///  * the three-way groups on `game-markets` are not fit to print (#5328): of
///    29 sampled soccer events only 13 served a tie group at all, and of four
///    read in full one live match was "priced" at 99% draw and two summed to
///    0.87 and 1.04.
///
/// So the honest move is the one this codebase already makes wherever it cannot
/// state a number — `SportVocab.totalRange`'s `nil`, `EventOutcome.undecided`,
/// `formatProbabilityOrDash` — *a number in the wrong unit is worse than an
/// absent one, because it looks sourced.* The away slot is withheld.
///
/// ═══ WHAT THIS DOES NOT FIX, AND MUST NOT BE READ AS FIXING ═══
///
/// The home price this keeps is the blend, and on soccer the blend is itself
/// draw-dropped whenever the books are in it (#1011). Measured the same day
/// over recent soccer events carrying both sources, `betting` sat **10–21pp
/// above** the Kalshi three-way home price on 8 of 8 sampled — Flamengo 0.856
/// against 0.650, Atletico Mineiro 0.849 against 0.685 — which is a `betting`
/// source normalised two ways with the draw discarded, at weight 3.0 against
/// Kalshi's 0.8.
///
/// That is a DATA defect and it is #1011's. This type fixes the RENDER defect
/// only: a client inventing an away price out of a complement. The two are
/// independent, and the issue's acceptance test — hero and match-winner card
/// agreeing on one screen — is only reachable once #1011 lands too.
enum DrawPricedWinner {

    /// Whether this sport's match-winner market prices a draw as a third
    /// outcome. Declared per sport in `SportVocab`, never inferred from a key.
    static func sportPricesADraw(_ sportKey: String?) -> Bool {
        SportVocab.forSport(sportKey).winnerMarketPricesADraw
    }

    /// The two win probabilities a two-slot surface may print, or `nil` where
    /// it may print no probabilities at all.
    ///
    /// A `nil` `away` inside a non-nil result is the whole point: it means *the
    /// home number stands and the away slot is withheld*, which is a different
    /// answer from "this surface has no numbers" and the callers draw them
    /// differently.
    ///
    /// - Parameter away: the away figure the caller would otherwise have
    ///   printed — the served `current_odds.away_probability`, or a locally
    ///   derived `1 − home`. It is IGNORED on a draw-priced sport; the
    ///   parameter stays so that two-way callers keep passing the served value
    ///   rather than re-deriving one, which is the trap `duelPercents`
    ///   documents.
    /// - Returns: `nil` when there is no home price, and — preserving today's
    ///   behaviour exactly — when a two-way sport holds no away price either.
    static func printablePair(
        away: Double?,
        home: Double?,
        sport sportKey: String?
    ) -> (away: Double?, home: Double)? {
        guard let home else { return nil }
        if sportPricesADraw(sportKey) { return (away: nil, home: home) }
        guard let away else { return nil }
        return (away: away, home: home)
    }

    /// The ONE side a single-number headline may name, and its probability.
    ///
    /// `MarketMapView`'s map header names the favourite — the side above 50% —
    /// and on a draw-priced sport that choice reaches for the complement every
    /// time the home team is the underdog, which is how Alex found
    /// `Al-Ittihad 99%` sitting above a match its own card priced at 93%.
    ///
    /// A draw-priced sport therefore always names HOME, favourite or not. A
    /// headline that names the underdog is honest; one that names the wrong
    /// number is not.
    static func headlineSide(
        away: Double?,
        home: Double?,
        sport sportKey: String?
    ) -> (isHome: Bool, probability: Double)? {
        guard let pair = printablePair(away: away, home: home, sport: sportKey) else { return nil }
        guard let away = pair.away else { return (isHome: true, probability: pair.home) }
        let homeIsFavoured = pair.home > 0.5
        return (isHome: homeIsFavoured, probability: homeIsFavoured ? pair.home : away)
    }

    /// Who the hero's "since open" caption names, and the move it states.
    ///
    /// #1830 — the caption used to be a bare unlabelled `-27%` computed on
    /// HOME, printed under an away-first `87 – 13` hero, so Alex read the Red
    /// Sox as FALLING 27 while they had gone 60 → 87. The fix was to name the
    /// team and report the RISER, always as a gain: because `away == 1 − home`
    /// exactly, "home fell 27" and "away rose 27" are the same fact.
    ///
    /// **That equivalence is exactly what a draw breaks.** Home shedding five
    /// points does not hand them to the away side; the draw can take any part
    /// of them. So a draw-priced sport names HOME and signs the number, which
    /// is still no bare figure — #1830's defect was the missing subject, not
    /// the minus sign.
    ///
    /// - Parameter homeDelta: home now minus home at open, as a probability.
    /// - Returns: which side to name, and the whole points to print WITH the
    ///   sign the caption should show (never negative on a two-way sport).
    static func trendSubject(
        homeDelta: Double,
        sport sportKey: String?
    ) -> (isHome: Bool, signedPoints: Int) {
        let points = Int((abs(homeDelta) * 100).rounded())
        if sportPricesADraw(sportKey) {
            return (isHome: true, signedPoints: homeDelta < 0 ? -points : points)
        }
        return (isHome: homeDelta > 0, signedPoints: points)
    }
}
