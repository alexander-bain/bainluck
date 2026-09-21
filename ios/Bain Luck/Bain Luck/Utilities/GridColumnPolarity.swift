import Foundation

/// Which direction is GOOD news for a grid column (#7780; web's
/// `lib/gridColumnPolarity.ts`, #7745 / PR #7769).
///
/// WHY THIS EXISTS.
///
/// The championship grid paints a 24h move green when it rises and red when it
/// falls. That is right for every column that is a rung toward something a club
/// wants — and exactly backwards for `relegation`, where the number going up is
/// the bad outcome. On the web grid this shipped as a club being congratulated
/// in green for `▲0.3` on its relegation risk while another's `▼0.4` — its risk
/// FALLING — printed in red. The payload was right; the colour editorialised it
/// wrongly. `ChampionshipPathView` carried the identical assumption.
///
/// ── THE KEY, NEVER THE LABEL ────────────────────────────────────────────────
///
/// A renderer asks this type which way is up for the column it is drawing. It
/// does not read `label`, which is a display string that re-words and
/// translates — a classifier keyed on "Relegated" misfiles the day the label
/// becomes "Drop Zone". `ProgressionStageData.key` is structured and comes
/// straight from `league_configs.py` by way of `columns[].key`.
///
/// ── WHAT THE ARROW DOES, AND DOES NOT, DO ───────────────────────────────────
///
/// Only the COLOUR flips. The arrow keeps pointing the way the number moved,
/// because that is a fact about the number and not an opinion about it: a
/// relegation probability that rose gets an up arrow, painted red. Flipping the
/// arrow too would misstate the data to make the colour agree with it.
enum GridColumnPolarity {

    /// Grid columns where a RISING probability is bad news for the row.
    ///
    /// `relegation` is the only one in the whole vocabulary — 26 distinct
    /// key/label pairs across every config in `league_configs.py` — and it
    /// appears in exactly three configs: `epl`, `la-liga`, `bundesliga`. Every
    /// other key (`top_4`, `make_playoffs`, `conference`, `final_four`,
    /// `make_cut`, `championship`, …) is a step toward something good.
    ///
    /// Pinned against web's `ADVERSE_COLUMN_KEYS` by
    /// `frontend/__tests__/ios/gridColumnPolarityParity7780.test.ts`, so a key
    /// added on one surface cannot quietly be missing on the other.
    static let adverseColumnKeys: Set<String> = ["relegation"]

    /// Is a rising probability in this column good news for the row?
    ///
    /// An absent or unrecognised key answers `true`. There is no third colour to
    /// render an unknown in, and the whole measured vocabulary bar one key rises
    /// toward something good, so the default is the majority reading rather than
    /// a refusal.
    static func risingIsGood(_ columnKey: String?) -> Bool {
        guard let columnKey, !columnKey.isEmpty else { return true }
        return !adverseColumnKeys.contains(columnKey)
    }

    /// Is this move good news for the row — the question the colour answers.
    ///
    /// Exists so the two ideas the render needs (which way the number went, and
    /// whether that is good) are combined in ONE place with a name. Written at
    /// the call site it is `(trend > 0) == risingIsGood(key)`, a double negative
    /// that is easy to get backwards and impossible to test on its own.
    ///
    /// A move of exactly zero reads as not-good, which no caller reaches: the
    /// grid gates the badge on `ChampionshipRowLayout.showsTrendBadge` first, so
    /// a zero move draws nothing at all rather than drawing red.
    static func isGoodNews(trend: Double, columnKey: String?) -> Bool {
        trend > 0 ? risingIsGood(columnKey) : !risingIsGood(columnKey)
    }
}
