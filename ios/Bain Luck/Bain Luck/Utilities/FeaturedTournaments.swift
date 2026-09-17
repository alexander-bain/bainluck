import Foundation

/// A tournament that has its own hub screen, promoted so a person can reach it
/// without knowing it exists.
///
/// This used to be a `private` list inside `LeaguesView`, which meant Browse was
/// the only surface that could offer one. Search — where a person who wants the
/// US Open actually goes first — could not see the list at all.
nonisolated struct FeaturedTournament: Identifiable, Equatable, Sendable {
    /// The API slug, e.g. `us-open` for `/api/tournaments/us-open`.
    let slug: String
    let title: String
    /// What to say while this edition is actually being played.
    let liveSubtitle: String
    /// What to say before it starts and after it is over — every other week of
    /// the year. The hub is worth reaching then too; it just has no live match
    /// to offer, so the card must not promise one.
    let restingSubtitle: String
    /// ISO-8601 instant after which no match of this edition can still be in
    /// progress. `nil` means we do not know when it ends, and a hub we cannot
    /// date NEVER claims to be live — see `subtitle(asOf:)`.
    let liveThrough: String?
    let icon: String
    /// Other names for the same tournament. Matched exactly like the title is:
    /// every token of an alias must be present in the query.
    let aliases: [String]

    init(
        slug: String,
        title: String,
        liveSubtitle: String,
        restingSubtitle: String,
        liveThrough: String? = nil,
        icon: String,
        aliases: [String] = []
    ) {
        self.slug = slug
        self.title = title
        self.liveSubtitle = liveSubtitle
        self.restingSubtitle = restingSubtitle
        self.liveThrough = liveThrough
        self.icon = icon
        self.aliases = aliases
    }

    var id: String { slug }

    /// The line to print under the title.
    ///
    /// The whole point of this being a function of the clock is that the card is
    /// drawn 50 weeks a year when the tournament is not on. A single stored
    /// string cannot be true in both states, and the one we shipped chose the
    /// two-week state: on 2026-09-16, three days after Zverev won the title,
    /// Browse's first card and the top row of a search for "us open" both read
    /// "Live matches, results, title odds" — directly above the app's own event
    /// rows, every one of them stamped FINAL.
    ///
    /// Every failure of this function is an UNDERSTATEMENT and never a lie: an
    /// absent date, a date that does not parse, and a date nobody remembered to
    /// bump all land on `restingSubtitle`, which is true whether or not a match
    /// is on. That asymmetry is the reason the window is an end rather than a
    /// range — a stale end says "results" during a live tournament, where a
    /// stale subtitle said "live" at a finished one.
    ///
    /// Not observed for changes: `now` is read when the view body runs, so a
    /// card already on screen when the final ends keeps its wording until the
    /// next render. That is a day-scale line on a static list, not a score.
    func subtitle(asOf now: Date = Date()) -> String {
        isBeingPlayed(asOf: now) ? liveSubtitle : restingSubtitle
    }

    /// Whether this edition is still being played, as of `now`.
    ///
    /// **This is the one clock rule, and every caller that needs the FACT must
    /// come through here** — a caller that instead compares rendered subtitles,
    /// or re-parses `liveThrough` against its own `now`, is a second detector of
    /// one rule, which is how two surfaces come to disagree about whether a
    /// tournament is on. `subtitle(asOf:)` is the first such caller; ux/1304's
    /// Browse ordering (a featured hub leads only while its edition is being
    /// played) is the second, and is why this is named rather than inlined.
    ///
    /// `FeaturedHubSubtitleGoesThroughTheClock`'s `UNCLOCKED_TELLS` forbids
    /// `liveSubtitle`/`restingSubtitle` outside this catalog for exactly that
    /// reason. **Grep for `isBeingPlayed` before writing a third one.**
    ///
    /// Fails to `false` on an absent, unparsable or un-bumped date — the same
    /// understatement `subtitle(asOf:)` is built on, and for the same reason:
    /// a hub wrongly called finished sits lower in a list and keeps its results,
    /// where a hub wrongly called live leads the tab three days after its final.
    func isBeingPlayed(asOf now: Date = Date()) -> Bool {
        guard let end = parseFlexibleDate(liveThrough), now <= end else { return false }
        return true
    }
}

/// Tournament hubs promoted to Browse, and offered by Search when a query names one.
///
/// HAND-MAINTAINED, and that is the known limitation rather than the design:
/// `REGISTERED_TOURNAMENTS` lives on the server and is not exposed as a list, so
/// the phone cannot ask which hubs exist or which one is being played this week.
/// A slug listed here stays listed after its final, and that is deliberate — the
/// hub degrades honestly, keeping the results and the finished board, and those
/// are worth reaching. What was NOT honest was the line under the title, which
/// went on promising live matches; `liveThrough` is what ends that, and it is
/// the same hand-maintained fact, only one that rots into an understatement.
/// An API index would still be better. Tracked as a follow-up.
let featuredTournaments: [FeaturedTournament] = [
    FeaturedTournament(
        slug: "us-open",
        title: "US Open",
        liveSubtitle: "Live matches, results, title odds",
        restingSubtitle: "Results and title odds",
        // The 2026 men's final was played on 13 September (`/api/tournaments/us-open`
        // serves no result later than that, and its slate has run empty since).
        // Small margin past midnight in New York for a late finish.
        liveThrough: "2026-09-14T06:00:00+00:00",
        icon: "tennis.racket",
        aliases: ["flushing meadows"]
    ),
]

// MARK: - Naming a hub from its slug

/// The title to show for a hub slug that arrived from a link.
///
/// `Route.tournamentHub` carries a display name because the hub screen shows it
/// as the navigation title while the payload loads and in the error state — so
/// a link has to supply one. The catalog above is the authority when it knows
/// the slug (`us-open` → `US Open`); anything else falls back to the shared
/// acronym-safe title caser, which is what keeps a slug the catalog has not
/// heard of from rendering as "Us Open" (#1938's class of defect). The loaded
/// hub renders the server's own name regardless — this only owns the title bar.
nonisolated func tournamentDisplayName(
    forSlug slug: String,
    in catalog: [FeaturedTournament] = featuredTournaments
) -> String {
    if let known = catalog.first(where: { $0.slug == slug }) { return known.title }
    return toTitleCaseAcronymSafe(slug.replacingOccurrences(of: "-", with: " "))
}

// MARK: - Matching a search query to a hub

/// The tokens of `text`, lowercased, split on everything that is not a letter or digit.
///
/// `"U.S. Open"` → `["u", "s", "open"]`, `"US  Open!"` → `["us", "open"]`.
private func searchTokens(_ text: String) -> [String] {
    text.lowercased()
        .split(whereSeparator: { !$0.isLetter && !$0.isNumber })
        .map(String.init)
}

/// `text` with every non-alphanumeric character removed: `"U.S. Open"` → `"usopen"`.
private func collapsed(_ text: String) -> String {
    text.lowercased().filter { $0.isLetter || $0.isNumber }
}

/// The token spellings of a name that a query may reasonably use.
///
/// A leading article is optional in the way people actually type: nobody searching
/// for The Open Championship types "the", and nobody searching for The Masters
/// types it either. Dropping it is safe because the REST of the name is still
/// required in full — `"open"` alone matches neither form.
private func nameForms(_ name: String) -> [[String]] {
    let tokens = searchTokens(name)
    guard let first = tokens.first else { return [] }
    let articles: Set<String> = ["the", "a", "an"]
    if tokens.count > 1, articles.contains(first) {
        return [tokens, Array(tokens.dropFirst())]
    }
    return [tokens]
}

/// Whether `query` names `name`.
///
/// Two ways to match, and deliberately no third:
///
/// 1. **Every token of the name is a token of the query.** `"us open"` and
///    `"us open tennis"` and `"the us open"` all name the US Open; `"open"` alone
///    does not, and neither does `"us"`. Requiring ALL tokens is what keeps the
///    generic half of a two-word name from matching on its own — otherwise every
///    query containing "open" would offer a tennis hub.
/// 2. **The query, stripped to letters and digits, equals the stripped name.**
///    This is only for punctuation and spacing: `"U.S. Open"`, `"usopen"`,
///    `"us-open"`. It is an equality and not a `contains` on purpose — a substring
///    test matches `"housopener"`, which names nothing.
private func query(_ query: String, names name: String) -> Bool {
    let queryTokens = Set(searchTokens(query))
    guard !queryTokens.isEmpty else { return false }
    let collapsedQuery = collapsed(query)

    for form in nameForms(name) {
        if form.allSatisfy({ queryTokens.contains($0) }) { return true }

        let collapsedName = form.joined()
        if collapsedQuery == collapsedName { return true }
        // "usopen" typed as one word, alongside other terms.
        if queryTokens.contains(collapsedName) { return true }
    }
    return false
}

/// The featured hubs a search query names, in catalog order.
///
/// Returns empty for a query that names no tournament, which is the common case —
/// the caller draws nothing rather than a "no tournaments" row.
func featuredTournaments(
    matching searchQuery: String,
    in catalog: [FeaturedTournament] = featuredTournaments
) -> [FeaturedTournament] {
    catalog.filter { tournament in
        query(searchQuery, names: tournament.title)
            || tournament.aliases.contains { query(searchQuery, names: $0) }
    }
}
