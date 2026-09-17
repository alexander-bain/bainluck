import Foundation

/// The one league-market section vocabulary, and the labels and icons that go
/// with it.
///
/// **#888 — THE SAME FIVE STRINGS WERE WRITTEN TWICE AND BOTH COPIES WERE
/// WRONG.** `LeagueGridView` and `SportCategoryView` each carried their own
/// `sectionOrder` / `sectionLabels` literal, both reading
/// `["series", "awards", "playoff_props", "season_stats", "novelty"]` against an
/// API that emits `futures · series · matches · awards · props · season_stats ·
/// more_markets` (`backend/app/routes/league_futures.py:2380`). Two of the five
/// keys could never match, and `more_markets` — the classifier's DEFAULT return
/// (`:1523`), the biggest bucket on nearly every league — was never read by
/// either view.
///
/// It survived because `sections[key]` MISSES SILENTLY: an absent key and an
/// empty section render identically. No empty state, no count, nothing that
/// says content was skipped. Fixing one view and not the other would have left
/// exactly that condition in place on the golf, tennis and category surfaces,
/// so the vocabulary lives here and the views read it.
///
/// `LeagueGridSectionKeysMatchTheAPI888Tests` pins this against the API's key
/// set in both directions, and scans the sources so a third copy cannot appear.
enum LeagueMarketSections {

    /// Render order. Membership is the contract; the order is a product choice.
    static let order = ["series", "awards", "props", "season_stats", "more_markets"]

    static let labels: [String: String] = [
        "series": "Playoff Series",
        "awards": "Awards",
        // Not "Playoff Props", which is what the dead key was labelled: NCAAF's
        // 31 are not playoff props, and most leagues carrying this section are
        // not in a playoff at all.
        "props": "Props",
        "season_stats": "Season Stats",
        "more_markets": "More Markets",
    ]

    static let icons: [String: String] = [
        "series": "sportscourt.fill",
        "awards": "trophy.fill",
        "props": "chart.bar.fill",
        "season_stats": "chart.line.uptrend.xyaxis",
        "more_markets": "sparkles",
    ]

    /// Sections the API can emit that no league surface draws.
    ///
    /// Neither is populated for a team league and the API omits empty sections.
    /// Adding to this set is a decision; the guard test makes it hard to make by
    /// accident, because an API section that is neither rendered nor named here
    /// fails.
    static let deliberatelyNotRendered: Set<String> = ["futures", "matches"]

    /// The label a header prints. The fallback exists so a section the server
    /// adds tomorrow is legible rather than absent — `key.capitalized` turns
    /// `more_markets` into `More_markets`, which is ugly and VISIBLE, and
    /// visible is the whole point after a defect that was neither.
    static func label(for key: String) -> String {
        labels[key] ?? key.replacingOccurrences(of: "_", with: " ").capitalized
    }

    static func icon(for key: String) -> String {
        icons[key] ?? "list.bullet"
    }
}
