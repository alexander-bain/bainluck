import Foundation

/// The single implementation of team name → short display label.
///
/// #3374. Every surface that shows a competitor in less room than its full name
/// took the LAST WORD of that name, hand-rolled as `split(separator: " ").last`
/// in 39 places across 15 files on this target. For most of American sport the
/// last word is the mascot and the rule is fine — "Baltimore Orioles" →
/// "Orioles". For a club named after its league designator it is not:
/// **"Charlotte FC" → "FC"**, photographed on the live Discover card on
/// 2026-09-05.
///
/// The same rule serves individual competitors, where the failure is the person
/// suffix: two golf leaderboards took a golfer's last word, so "Davis Love III"
/// read `III`. Those two were found by the ratchet below rather than by the
/// author — which is the argument for a scan that discovers over a list.
///
/// Measured over all 5,559 distinct names in `teams`: **1,901 (34.2%) collapse
/// onto a label shared with at least one other team, and `FC` alone absorbs
/// 102 of them.** The rest of the worst offenders are the same shape — `W`
/// (30 women's sides), `Jr` (23 boxers), `B` and `II` (37 reserve sides), `SC`,
/// `CF`, `City`, `United`, `Town`. A label reading "FC" or "W" or "Jr" is not a
/// short name; it names nothing at all.
///
/// The rule below is deliberately narrow: **the last word names the team unless
/// that word is a designator, in which case the full name is shown instead.**
/// It does not try to make every label unique — "Tigers" is shared by Auburn,
/// Clemson and Detroit and is still what a reader calls them. It only refuses
/// to print a word that designates a *kind of club* rather than a team.
///
/// Diffed over the whole population: 385 names change, every one of them from a
/// designator to a real name, and the output vocabulary is closed — the only
/// labels that are still bare designators are `AIK` and `Wanderers`, which are
/// the entire names of those two clubs.
///
/// Enforced by `frontend/__tests__/ios/teamShortNameSingleSource.test.ts`, which
/// DISCOVERS re-implementations rather than listing consumers — the lesson of
/// #3273, where #1832's ratchet named its two consumers by hand and so could not
/// see the two new copies that grew where it was not looking.
enum TeamShortName {

    /// Words that designate a *kind of club* or a *variant of a side* rather
    /// than naming a team. Lowercased, with trailing punctuation stripped.
    private static let designators: Set<String> = [
        // Club-type suffixes and prefixes used worldwide.
        "fc", "sc", "cf", "ac", "afc", "cfc", "sk", "if", "ik", "fk", "bk",
        "aik", "sv", "tsv", "vfb", "vfl", "bsc", "cd", "ca", "as", "sd", "ud",
        "rc", "ssc", "psv", "hk", "il", "ff", "gif", "bif", "fsv", "spvgg",
        "kv", "rkc", "nec", "az", "sl", "cs", "ec", "se", "ad", "ce", "cp",
        "gd",
        // English generic club words.
        "united", "city", "town", "county", "club", "athletic", "atletico",
        "rovers", "wanderers", "albion",
        // Reserve, age-group and gender variants.
        "ii", "iii", "iv", "b", "w", "women", "res", "u19", "u20", "u21", "u23",
        // Person suffixes.
        "jr", "sr",
    ]

    /// A founding year ("1. FC Heidenheim 1846") names a team no better than
    /// "FC" does, and the shipped rule printed it as the whole label.
    ///
    /// Parentheses are in the trim set because the women's marker is written
    /// both ways in `teams`: "Argentina W" and "Harvard Crimson (W)". Trimming
    /// only `.` and `,` saw the first and missed the second, so three women's
    /// sides still rendered with `(W)` as their entire label.
    private static func isDesignator<S: StringProtocol>(_ token: S) -> Bool {
        let t = token.trimmingCharacters(in: CharacterSet(charactersIn: "().,")).lowercased()
        if designators.contains(t) { return true }
        return t.count <= 4 && !t.isEmpty && t.allSatisfy(\.isNumber)
    }

    /// The short display label for a team name.
    ///
    /// Returns the input unchanged when there is nothing to shorten, so a caller
    /// never has to supply its own fallback for the empty or single-word case.
    static func short(_ name: String) -> String {
        let parts = name.split(separator: " ").filter { !$0.isEmpty }
        guard parts.count > 1 else { return name }
        guard let last = parts.last else { return name }
        // The designator alone names nothing — show the name it qualifies.
        if isDesignator(last) { return parts.joined(separator: " ") }
        return String(last)
    }

    /// The 3-letter uppercase form used on crest placeholders and chart axes.
    ///
    /// Derived from `short` so a club named for its designator gets `CHA` rather
    /// than `FC` — the placeholder had exactly the same defect as the label.
    ///
    /// Two refinements, each measured over the whole population
    /// (`artifacts-native-031/abbr_model.py`):
    ///
    /// 1. **Leading designators are skipped.** `short` returns the full name for
    ///    a designator-ending club, so taking its first three characters put the
    ///    designator back on the badge whenever it sits at the FRONT: "FC
    ///    Schalke 04" drew `FC `, "AD Ceuta FC" drew `AD `. That is the defect
    ///    of #3374 relocated to the other end of the string, and it made 11
    ///    badges worse than the rule it replaced. Never skip so far that only
    ///    designators are left — "Athletic Club" must stay `ATH`, not `CLU`.
    ///
    /// 2. **The three glyphs are alphanumerics, crossing word boundaries.** A
    ///    badge has room for three characters and a space is not one of them:
    ///    "St. Louis City SC" reads `STL` and "D.C. United" reads `DCU`.
    ///
    /// Together these take unusable badges — those that cannot fill three glyphs
    /// — from 371 on the pre-#3374 rule to 56, and regress none.
    static func abbreviation(_ name: String) -> String {
        glyphs(ofLabel: short(name))
    }

    /// The three glyphs of a label that is ALREADY final.
    ///
    /// Split out of `abbreviation` so the pair rule below can badge a label it
    /// has just widened. Calling `abbreviation` on that widened label would run
    /// `short` over it a second time and collapse "White Sox" straight back onto
    /// `SOX`, which is the collision the widening exists to remove.
    private static func glyphs(ofLabel label: String) -> String {
        var parts = label.split(separator: " ").filter { !$0.isEmpty }
        if let firstReal = parts.firstIndex(where: { !isDesignator($0) }) {
            parts = Array(parts[firstReal...])
        }
        let glyphs = parts.joined(separator: " ").filter { $0.isLetter || $0.isNumber }
        return String(glyphs.prefix(3)).uppercased()
    }

    // MARK: - The two competitors of ONE matchup

    /// #3430. Everything above shortens ONE name at a time, and judges the
    /// result on its own: "Tigers" is what a reader calls Clemson, so `short`
    /// returns it and the doc comment above argues — correctly, in isolation —
    /// that sharing a label with Auburn and Detroit is fine.
    ///
    /// It is not fine when the OTHER competitor is also the Tigers. Photographed
    /// on the settled Clemson–LSU page 2026-09-06
    /// (`artifacts-native-033/settled-ncaaf-clemson-lsu-416567.png`): the nav
    /// title read "Tigers 10 - Tigers 51", the hero read **"Tigers Win"**, the
    /// segment rows read `TIG` and `TIG`, and the chart's two y-axis labels both
    /// read `TIGERS`. Four labels, and not one of them says who won. A reader
    /// leaves that page unable to answer the only question it exists to answer.
    ///
    /// The failure is not global ambiguity — it is collision *inside one
    /// matchup*, and it is only visible to something that can see both names at
    /// once. Measured over the 24,016 distinct (away, home) pairs on events in
    /// the last 45 days (`artifacts-native-033/model.py`): **114 pairs collapse
    /// onto one label** — Chicago White Sox vs Boston Red Sox (`Sox`), Dinamo vs
    /// Spartak Moscow (`Moscow`), Cercle vs Club Brugge (`Brugge`), Aris vs PAOK
    /// Thessaloniki. Derbies, overwhelmingly: the games a reader is least willing
    /// to be confused about.
    ///
    /// The rule is to GROW each label leftward a word at a time until the two
    /// differ, which is what a reader already says out loud — "Red Sox" and
    /// "White Sox", not "Sox" twice. It terminates at the full names, which
    /// differ whenever the names do.
    ///
    /// Measured over the same population: colliding labels **114 → 0**, colliding
    /// badges **205 → 91**, and — the direction that matters just as much — the
    /// 23,902 pairs that already read correctly are returned **byte-identical**.
    /// The 91 residual badge collisions are a different defect: two names that
    /// share their first three glyphs ("Corinthians"/"Coritiba" → `COR`) cannot
    /// be separated by three glyphs at all, and want real abbreviation data
    /// (#3353), not a longer label.

    /// The last `k` words of `name`, floored at the whole name.
    private static func lastWords(_ name: String, _ k: Int) -> String {
        let w = name.split(separator: " ").filter { !$0.isEmpty }
        guard !w.isEmpty else { return name }
        return w.suffix(max(1, k)).joined(separator: " ")
    }

    /// Has growth reached a word that actually names something?
    ///
    /// Stopping the instant the two labels differ can stop on a designator: from
    /// "Guarani FC SP" the two-word window is "FC SP", which distinguishes but
    /// reads exactly as badly as the bare "FC" this file exists to remove. Keep
    /// growing while the window LEADS with a designator — the same skip
    /// `abbreviation` already performs, applied to the other end of the growth.
    private static func namesSomething(_ name: String, _ k: Int) -> Bool {
        let whole = name.split(separator: " ").filter { !$0.isEmpty }.count
        guard let first = lastWords(name, k).split(separator: " ").first else { return true }
        return !isDesignator(first) || k >= whole
    }

    /// Labels for the two competitors of one matchup, guaranteed to differ
    /// whenever the two names differ.
    ///
    /// `awayServed` / `homeServed` are the provider abbreviations where we have
    /// them. They win, as they always have — unless they collide with EACH
    /// OTHER, in which case they are as unreadable as anything we could derive
    /// and the names decide instead. (`teams.abbreviation` is wrong for hundreds
    /// of rows, #3353, so a served pair colliding is not hypothetical.)
    static func shortPair(
        away: String,
        home: String,
        awayServed: String? = nil,
        homeServed: String? = nil
    ) -> (away: String, home: String) {
        let a = served(awayServed) ?? short(away)
        let h = served(homeServed) ?? short(home)
        guard a == h else { return (a, h) }
        return grown(away: away, home: home)
    }

    /// Three-glyph badges for the two competitors of one matchup.
    static func abbreviationPair(
        away: String,
        home: String,
        awayServed: String? = nil,
        homeServed: String? = nil
    ) -> (away: String, home: String) {
        let a = served(awayServed) ?? abbreviation(away)
        let h = served(homeServed) ?? abbreviation(home)
        guard a == h else { return (a, h) }
        let widened = grown(away: away, home: home)
        return (glyphs(ofLabel: widened.away), glyphs(ofLabel: widened.home))
    }

    private static func served(_ value: String?) -> String? {
        guard let v = value?.trimmingCharacters(in: .whitespaces), !v.isEmpty else { return nil }
        return v
    }

    /// Grow both labels leftward until they differ, or until both are whole.
    private static func grown(away: String, home: String) -> (away: String, home: String) {
        let aWords = away.split(separator: " ").filter { !$0.isEmpty }.count
        let hWords = home.split(separator: " ").filter { !$0.isEmpty }.count
        // `short` may already be a whole name (a designator-ending club), so
        // start wide enough that growth never NARROWS what we were showing.
        var k = max(1,
                    short(away).split(separator: " ").filter { !$0.isEmpty }.count,
                    short(home).split(separator: " ").filter { !$0.isEmpty }.count)
        let limit = max(aWords, hWords)
        while k <= limit {
            let a = lastWords(away, k)
            let h = lastWords(home, k)
            if a != h && namesSomething(away, k) && namesSomething(home, k) {
                return (a, h)
            }
            k += 1
        }
        // Identical names: nothing distinguishes them and inventing something
        // would be a lie. Return them whole and let the caller show two equal
        // labels for what is, in the data, one team playing itself.
        return (away, home)
    }
}
