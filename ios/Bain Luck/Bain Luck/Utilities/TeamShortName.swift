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
        var parts = short(name).split(separator: " ").filter { !$0.isEmpty }
        if let firstReal = parts.firstIndex(where: { !isDesignator($0) }) {
            parts = Array(parts[firstReal...])
        }
        let glyphs = parts.joined(separator: " ").filter { $0.isLetter || $0.isNumber }
        return String(glyphs.prefix(3)).uppercased()
    }
}
