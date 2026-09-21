import Foundation

/// Reader copy for the accuracy page's **data corrections log** (#7759).
///
/// WHY THIS EXISTS.
///
/// The corrections log is a trust panel: it is the page telling a reader what we
/// got wrong and fixed. On the website those rows read as sentences. In the app
/// they read as commit messages — `CalibrationView` rendered the payload's
/// `title` verbatim, so an iPhone printed
///
///     Polymarket hockey sign-flip
///     Malformed-binary exclusion
///     Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)
///
/// The last one carries our own handoff directory's numbering, at 390pt, on the
/// one panel whose entire subject is whether our numbers can be checked. That is
/// notice 34 (no diagnostic prose on a reader's screen) and the specimen #4067 /
/// CERT-2295 named, arriving on the surface that cert did not cover.
///
/// ── THIS IS A PORT, NOT A COPY DECISION ─────────────────────────────────────
///
/// Every sentence below is web's, from `frontend/lib/calibrationCorrections.ts`
/// (#7729 for the Kalshi row, #7734 for the eight July rows). The words were
/// written and reviewed there against the producer's own `description` for each
/// row, so nothing here is a fresh judgement about what a correction means. This
/// file's whole claim is that the app says what the site says.
///
/// That is also why the map is keyed on the producer's exact string: a title the
/// page has chosen words for is a deliberate, reviewable pair and never a guess.
///
/// ── WHY THE CLIENT AND NOT THE PRODUCER ─────────────────────────────────────
///
/// `precompute_calibration_main` is a `HEAVY_TASK` and its artifact has been
/// stamped `2026-09-15T11:16:10Z` since 2026-09-15 (#6868). A one-word edit
/// upstream would be correct and invisible for an unbounded time. Web reached
/// the same conclusion and fixed it at the render; presentation is the page's.
///
/// ── THE MAP IS THE FIX; THE WITHHOLD IS A FLOOR UNDER IT ────────────────────
///
/// `withheldInternalReference` exists so that the day the producer grows a title
/// nobody mapped, the leak is a missing clause rather than a tracker id on a
/// trust panel. It DROPS a fragment; it never rewrites one (#4113 — the page may
/// remove its own words, it may not invent a reader's).
///
/// It is not a licence to skip the map, because it cannot produce good copy: run
/// on the Kalshi specimen it yields *"…— corrected discriminator"*, which is
/// still jargon in a slot the page controls. `needingCopy` counts exactly the
/// rows running on the floor rather than on chosen words, so the gap is a number
/// a test can pin at zero instead of a thing someone has to notice.
enum CalibrationCorrections {

    /// Reading order for the log (#7763; web's `orderCorrections`, #7599).
    ///
    /// The card leads every entry with its date, in monospace, in a column of its
    /// own — the date is the log's organising fact. It then rendered the payload
    /// array verbatim, and on the served payload twelve of the thirteen entries
    /// are oldest-first and the second one is not: `2026-07-08` sits below
    /// `2026-07-09`. A list that is monotone except for one row does not read as
    /// unordered; it reads as a list that lost a row's place.
    ///
    /// Sorted here rather than upstream for the reason the copy map above is
    /// here: the backend list grows by hand, so re-sorting the rows it publishes
    /// today fixes today and not the next entry appended in the wrong place.
    ///
    /// ── OLDEST FIRST, AND STABLE ────────────────────────────────────────────
    ///
    /// Oldest-first because the list is already 12/13 that way, so preserving the
    /// direction moves exactly ONE row — a claim a screenshot can check by eye.
    /// Reversing the log would move all thirteen and make "is it ordered now?"
    /// unanswerable from a picture.
    ///
    /// **Stable, and Swift will not do that for us.** Web's twin leans on
    /// `Array.prototype.sort`, which ES2019 requires to be stable; `Swift.sort` is
    /// introsort and is explicitly NOT stable. Five entries share `2026-07-09` and
    /// two share `2026-09-12`, so a direct translation could reorder rows this fix
    /// has no opinion about — the same defect, rearranged. Sorting on
    /// `(date, original index)` makes the tie-break the publication order itself,
    /// which is stability by construction rather than by the standard library's
    /// good behaviour.
    ///
    /// Dates compare as text deliberately: they are ISO `YYYY-MM-DD` days, so
    /// lexicographic order IS chronological order and no parse is needed. A parse
    /// would buy nothing and cost the one thing that matters — an unparseable
    /// value would sort unpredictably, where a string compare is deterministic on
    /// any input. An entry with an empty date sorts before every real one, which
    /// is the right way to be wrong: a dateless row in a log the card calls dated
    /// is visible at the top rather than buried where nobody can predict.
    static func ordered(_ corrections: [CalibrationCorrection]) -> [CalibrationCorrection] {
        corrections.enumerated()
            .sorted { lhs, rhs in
                if lhs.element.date != rhs.element.date {
                    return lhs.element.date < rhs.element.date
                }
                return lhs.offset < rhs.offset
            }
            .map(\.element)
    }

    /// The page's words for a producer title, keyed on that title exactly.
    ///
    /// Byte-for-byte web's `CORRECTION_TITLE_OVERRIDES`. The pairing is asserted
    /// across the two surfaces by
    /// `frontend/__tests__/ios/correctionsLogCopyParity7759.test.ts`, which reads
    /// both files as source — so a tenth entry added on one side reddens CI
    /// instead of silently diverging, which is the defect this file is.
    static let titleOverrides: [String: String] = [
        "Kalshi player-prop threshold exclusion — corrected discriminator (Queue #186)":
            "Player-prop prices (Kalshi): corrected the test for which prices to drop",
        "Polymarket hockey sign-flip":
            "Hockey player props (Polymarket): over and under prices were the wrong way round, now re-scored",
        "DataGolf survivorship exclusion":
            "Golf: players who withdrew or never teed off are no longer scored",
        "Polymarket no-bid placeholder exclusion":
            "Polymarket prices with no offer behind them, parked near 50%, are no longer scored",
        "Malformed-binary exclusion":
            "Yes-or-no markets that settled with no winner, or with two, are no longer scored",
        "Golf FIELD one-sided-ask placeholder exclusion":
            "Golf: prices that put two players in one event both above 80% to win are no longer scored",
        "Multi-candidate probability normalization":
            "Markets with several candidates now add up to 100%, instead of well over it",
        "Soccer 2-way (draw-omission) historical exclusion":
            "Soccer: older win-or-lose prices left the draw out, so they are no longer scored",
        "Esports match-bundle exclusion":
            "Esports markets that pack a whole match into one question are no longer scored",
    ]

    // A tracker id in the shapes this repo actually writes — `Queue #186`,
    // `#4067`, `CERT-2295`, `L2-74`, `CAL-P114`, `OPS-557`, `q271`.
    //
    // The `\b` on the named prefixes is load-bearing: without it the
    // single-letter arms (`D`, `q`) match mid-word — `3D2`, `Iraq2024` — and the
    // floor would start cutting clauses out of titles carrying no tracker id at
    // all. `#\d{2,}` takes no boundary because `#` is not a word character, so a
    // `\b` in front of it would REQUIRE a word character before the hash and the
    // common shape (a hash after a space) would stop matching. Written as an
    // alternation over the id shapes rather than a bare `#\d+` so a real reader
    // number — a price, a year, a count — is never eaten.
    private static let trackerID =
        #"(?:\b(?:Queue|Issue|CERT|OPS|CAL-P|L2|UX-P|D|q)[\s-]?#?\d+|#\d{2,})"#

    // Anchored to a trailing parenthetical or a trailing dash clause on purpose:
    // an id in the MIDDLE of a sentence cannot be cut without changing what the
    // sentence says, so those are left to the map and counted, not mangled.
    private static let trailingParenthetical =
        try? NSRegularExpression(pattern: #"\s*\((?:[^()]*\s)?"# + trackerID + #"[^()]*\)\s*$"#)
    private static let trailingDashClause =
        try? NSRegularExpression(pattern: #"\s*[—–-]\s*[^—–]*"# + trackerID + #"[^—–]*$"#)
    private static let anyTrackerID = try? NSRegularExpression(pattern: trackerID)

    /// Whether the three patterns above compiled.
    ///
    /// `try?` on a static is the house idiom, and for a DETECTOR a nil pattern
    /// fails open — `carriesInternalReference` would answer "no tracker id here"
    /// for every title and the floor would quietly stop existing. The patterns
    /// are literals, so this can only be false if one is edited into something
    /// invalid; the test asserts it, which turns a silent fail-open into a red.
    static var patternsCompiled: Bool {
        trailingParenthetical != nil && trailingDashClause != nil && anyTrackerID != nil
    }

    /// Does this title still carry something written for our own tracker?
    static func carriesInternalReference(_ title: String) -> Bool {
        guard let re = anyTrackerID else { return false }
        return re.firstMatch(in: title, range: NSRange(title.startIndex..., in: title)) != nil
    }

    /// The title with any trailing tracker fragment withheld.
    ///
    /// Returns the title unchanged when the reference is not in a carrier this
    /// can cut cleanly — that row is a `needingCopy`, and the honest answer is to
    /// say so rather than to guess at a cut.
    static func withheldInternalReference(_ title: String) -> String {
        var cut = title
        for re in [trailingParenthetical, trailingDashClause].compactMap({ $0 }) {
            cut = re.stringByReplacingMatches(
                in: cut, range: NSRange(cut.startIndex..., in: cut), withTemplate: ""
            )
        }
        let trimmed = cut.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? title : trimmed
    }

    /// What the card prints for one correction: the map's words, else the
    /// producer's title with any trailing tracker fragment withheld.
    static func title(_ title: String?) -> String {
        guard let title, !title.isEmpty else { return "" }
        if let override = titleOverrides[title] { return override }
        return carriesInternalReference(title) ? withheldInternalReference(title) : title
    }

    /// Rows whose producer title carries a tracker id and that the map has no
    /// words for — the ones running on the floor rather than on chosen copy.
    ///
    /// Never rendered. It exists so the gap is a number the suite can pin at zero
    /// against the producer's own published titles.
    static func needingCopy(_ corrections: [CalibrationCorrection]) -> Int {
        corrections.filter { c in
            if titleOverrides[c.title] != nil { return false }
            return carriesInternalReference(c.title)
        }.count
    }
}
