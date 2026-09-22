import Foundation

// MARK: - Naming a category the published table is NOT grading (#7532)

/// The Swift twin of `frontend/lib/calibrationCategories.ts` `nicheCatLabel`,
/// and the rule it carries is Alex's, not a formatting preference.
///
/// **L2-103 Item 3b (Alex D5), verbatim from the web file:**
///
/// > a thin sub-league (e.g. `icehockey_sweden_hockey_league`, ~730 outcomes)
/// > must NOT collapse to its parent sport's display name ("Hockey"), because
/// > the parent sport is already graded in the Category Breakdown above — that
/// > made a niche chip read as "Hockey is still coming soon". Prefer the
/// > specific league label.
///
/// ## What the app did instead, measured
///
/// `CalibrationViewModel.nicheDisplayName` normalised the raw league key to its
/// PARENT product category and then looked the parent's display name up, so the
/// sample gate (applied by the server to the RAW key) and the label (applied by
/// the client to the NORMALISED key) were answering about different rows.
///
/// On the payload served 2026-09-20 (`min_category_outcomes` 1000, 109 parked
/// categories) that collapsed **67 of 109** chips onto a parent-category label:
/// 55 × "Soccer", 5 × "Football", 4 × "Tennis", 2 × "Hockey", 1 × "Basketball".
/// The eight a reader actually sees read
/// `Football 847 · Lacrosse NCAA 829 · Chess 809 · Hockey 730 · Football 707 ·
/// Football 682 · Soccer 613 · Football 593` — under a card headed "we don't
/// publish one for any category below 1.0K resolved outcomes", two inches below
/// a table publishing Football 22.7K, Hockey 19.2K and Soccer 58.4K. Four of
/// the eight said "Football", which reads as one category listed four times.
///
/// ## Why the parent name is unreachable here by construction
///
/// This function never consults the parent-category map at all. A key is named
/// by its OWN tokens: a curated opinion if we have one, otherwise the key with
/// a leading sport prefix dropped. There is no branch that can return "Hockey"
/// for a Swedish league, so the defect cannot return by a later edit to the
/// normaliser — which is the part `nicheDisplayName` shared with the table.
///
/// ## Where it deliberately differs from web
///
/// Both surfaces obey the ruling; they do not print byte-identical strings,
/// because each prefers its OWN curated league vocabulary and ours is shorter
/// and more specific in six places. `soccer_spain_la_liga` is "La Liga" here
/// and "Spain La Liga" there; `soccer_uefa_champs_league` is "UCL" here and
/// "UEFA Champs League" there. Six such keys on today's payload, every one of
/// them a specific league label on both sides. Byte parity would mean copying
/// web's 100-entry `LEAGUE_DISPLAY` into this app to inherit its longer names,
/// which is a worse label for a worse reason.
nonisolated func nicheCategoryLabel(_ raw: String) -> String {
    // A curated name is an opinion. Return it verbatim — re-casing an opinion is
    // what turned web's own "NCAAF" into "Ncaaf" before UX-P189. The app's
    // shared vocabulary wins first; the chip-only names below fill the gaps.
    if let curated = leagueAcronyms[raw] ?? nicheLeagueNames[raw] { return curated }

    // #7894 — before tokenizing, because the whole point is that there is no
    // separator to tokenize on. Web consults its `SINGLE_WORD_COMPOUNDS` at
    // exactly this point in `nicheCatLabel`, and the app's copy is shared with
    // the search/badge labeller rather than local to this chip: the two
    // surfaces printed the same wrong word for the same reason.
    if let compound = singleWordCompounds[raw] { return compound }

    let tokens = raw.split(separator: "_").map(String.init).filter { !$0.isEmpty }
    guard !tokens.isEmpty else { return raw }

    // Drop the sport prefix only when something is left to name the row with,
    // and only by MEMBERSHIP of a known sport family — never by position.
    // `track_and_field` keeps its track, `horse_racing` keeps its horse, and
    // `boxing` (one token) keeps itself.
    let named = tokens.count > 1 && sportFamilyDisplayNames[tokens[0]] != nil
        ? Array(tokens.dropFirst())
        : tokens

    return named.enumerated()
        .map { nicheLabelToken($0.element, isFirst: $0.offset == 0) }
        .joined(separator: " ")
}

/// League names this CHIP needs and the rest of the app deliberately does not.
///
/// The obvious move was to add these four to `leagueAcronyms`, and the gate
/// refused it: `SearchTeamRowSportLabelTests` went red on
/// `icehockey_sweden_hockey_league` → "SHL", because #5780 ruled the opposite
/// trade for search's Teams rows *in writing* — when the served facet is
/// missing, that row answers COARSE ("Hockey", "Cricket"), since the facet is
/// absent exactly when no result on the page is in that sport and "which sport
/// is this club?" is the reader's question.
///
/// The two surfaces are asking different questions, so they get different
/// answers: a niche CHIP exists to say "this specific league is still
/// accumulating" and is worthless at sport granularity — that is the whole of
/// #7532 — while a team row wants the sport. This map is therefore scoped to
/// the chip rather than shared, and adding an entry here changes nothing
/// anywhere else. Strings are web's `LEAGUE_DISPLAY` values for the same keys.
///
/// #7722 added `aussierules_afl`, and the reason it needs an ENTRY rather than a
/// token is worth keeping: the derivation cannot reach "AFL" from either end.
/// `aussierules` is not in `sportFamilyDisplayNames`, so the prefix is not
/// droppable and both tokens survive; and shouting `afl` in `nicheKeyAcronyms`
/// — where `nrl` already lives, which is why `rugbyleague_nrl` needs no entry:
/// `rugbyleague` IS a known family, so its prefix drops and "NRL" is all that is
/// left — would only turn "Aussierules Afl" into "Aussierules AFL". Adding
/// `aussierules` to the shared family map would fix the prefix and change every
/// Discover badge and search row in the app for one calibration label, which is
/// the trade #5780 already refused in the other direction.
///
/// #7894 amends the last sentence, and it is worth reading as a warning about
/// the sentence rather than about the map. "It would change every search row"
/// was written as a COST; measured, those rows were printing "Aussierules"
/// themselves — the bare key is 162 production futures markets and a reader
/// meets it on the search tab, not only on a parked accuracy chip. The fix is
/// still not a family entry (that would drop `aussierules_afl`'s prefix, which
/// the #7722 guard pins): it is `singleWordCompounds`, a whole-key spelling
/// consulted by both labellers, so neither surface can spell it alone.
private let nicheLeagueNames: [String: String] = [
    "icehockey_sweden_hockey_league": "SHL",
    "icehockey_sweden_allsvenskan": "Allsvenskan",
    "lacrosse_ncaa": "NCAA Lacrosse",
    "lacrosse_pll": "PLL",
    "aussierules_afl": "AFL",
]

/// Tokens printed in capitals that `knownAcronyms` has no reason to carry:
/// they appear only inside calibration payload KEYS, so no display string the
/// rest of the app formats would ever contain them.
///
/// The two-letter entries are the reason this set is local rather than merged
/// into the shared table: `fa` and `ai` are governing-body and subject
/// acronyms in `soccer_fa_cup` and `ai_safety`, and shouting them anywhere a
/// human sentence is being repaired would be wrong. Web makes the same split
/// for the same two tokens.
private let nicheKeyAcronyms: Set<String> = [
    "ai", "bmx", "cfl", "conmebol", "dfb", "efl", "epl", "fa", "fcs", "fifa",
    "nbl", "nrl", "pll", "shl", "spl", "t20", "uefa", "ufl", "xfl",
]

/// Words that stay lowercase inside a title — unless they LEAD, where they are
/// capitalised like any other first word.
///
/// `la` is deliberately absent: `soccer_spain_la_liga` is "Spain La Liga", and
/// "Spain la Liga" is the failure this list must not invert into.
private let nicheTitleSmallWords: Set<String> = [
    "and", "da", "de", "del", "di", "du", "of", "the",
]

private func nicheLabelToken(_ token: String, isFirst: Bool) -> String {
    let lower = token.lowercased()
    if nicheKeyAcronyms.contains(lower) { return lower.uppercased() }
    if !isFirst, nicheTitleSmallWords.contains(lower) { return lower }
    // Everything else goes through the app's one acronym-and-brand-aware
    // formatter, so NFL, NCAAF, MLS, ATP, WTA and the brand table are spelled
    // here exactly as they are spelled on every other surface.
    return toTitleCaseAcronymSafe(token)
}
