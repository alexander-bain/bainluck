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
    ///
    /// #4250 — this set and the browser's `CLUB_TYPE_SUFFIXES` in
    /// `frontend/lib/teamShortName.ts` are ONE rule with two spellings, and
    /// they had drifted apart in both directions: the browser was missing
    /// `afc` and printed "Sunderland AFC" as **"AFC"**, and this set was
    /// missing four words the browser measured. They are now compared by
    /// `frontend/__tests__/teamDesignatorParityAcrossClients.test.ts`, which
    /// reds if a token is added to one client and not the other.
    private static let designators: Set<String> = [
        // Club-type suffixes and prefixes used worldwide.
        "fc", "sc", "cf", "ac", "afc", "cfc", "sk", "if", "ik", "fk", "bk",
        "aik", "sv", "tsv", "vfb", "vfl", "bsc", "cd", "ca", "as", "sd", "ud",
        "rc", "ssc", "psv", "hk", "il", "ff", "gif", "bif", "fsv", "spvgg",
        "kv", "rkc", "nec", "az", "sl", "cs", "ec", "se", "ad", "ce", "cp",
        "gd",
        // #4250, measured as TRAILING tokens on production 2026-09-09 (counts
        // are distinct multi-word `events` team names, both sides).
        "wfc", // 8   Arsenal WFC, Manchester City WFC
        "sad", // 8   Portimonense SAD (the Iberian legal suffix)
        "lfc", // 2   Liverpool LFC
        "pfk", // 2   Neftçi PFK
        "nps", // 2   Volos NPS
        // #4271. The Italian society initials, siblings of `ac`, `as` and `ssc`
        // above, which this set had always lacked. They were unreachable until
        // #4250 added `calcio`: before it, `short("SS Scafatese Calcio")`
        // returned "Calcio" and the badge never saw the leading token; after
        // it, `short` correctly returns the whole name and `glyphs` skipped
        // nothing, so the badge read `SSS`. Measured over the whole production
        // population 2026-09-09: **zero** distinct `events` team names END in
        // either token, so both can only ever act as the leading skip and can
        // never refuse a shortening. The browser reaches both by its
        // `length <= 2` clause, so its set is unchanged and parity holds.
        "ss", // SS Scafatese Calcio (Società Sportiva)
        "us", // US Sassuolo Calcio (Unione Sportiva)
        // English generic club words.
        "united", "city", "town", "county", "club", "athletic", "atletico",
        "rovers", "wanderers", "albion",
        // #4250, the four the browser measured and this set lacked.
        "state", // 33
        "calcio", // 4
        "academy", // 2
        "sporting", // 1
        // Reserve, age-group and gender variants.
        "ii", "iii", "iv", "b", "w", "women", "res", "u19", "u20", "u21", "u23",
        // Person suffixes.
        "jr", "sr",
    ]

    /// The clubs whose label is chosen by hand instead of derived from the name.
    ///
    /// #4627 — the photographed defect is the NAME slot, not the badge. On the
    /// Champions League page Alex shot on 2026-09-09 the nav title read
    /// `SLB 1 - Germain 6`, the hero read **"Germain Win"** and both chart axes
    /// read `GERMAIN`: four labels on one screen and not one of them says Paris
    /// Saint-Germain. The rule above is right for `<place> <nickname>` and wrong
    /// for a compound whose distinctive part is three words, where the last word
    /// is a fragment rather than a name anybody uses.
    ///
    /// ALEX RULED A LIST, NOT A RULE (2026-09-12, option B of
    /// `alex-inbox/native-127-what-should-the-app-call-paris-saint-germain.md`):
    /// *"'PSG Win': the crest letters for Paris Saint-Germain, as an explicit
    /// short-name entry (not a rule change that turns the Lakers into 'LAL
    /// Win')"*. The automatic candidate — reuse the badge's own three-distinctive-
    /// token fork, which already prints `PSG` correctly — counts "Los Angeles
    /// Lakers" as three distinctive tokens too, so the hero would read "LAL Win".
    /// Three letters are a stamp on a crest and gibberish in a sentence, and no
    /// test on the string alone separates "Germain is a fragment" from "Lakers is
    /// the name". So this is a hand-kept list and it is meant to stay small;
    /// abbreviation data for every club (#3353) is the real answer and is option
    /// C, deliberately deferred.
    ///
    /// THE KEY IS A NORMALISED NAME, NOT A SPELLING, because the same club is
    /// stored several ways and every one of them reaches a reader. Measured over
    /// 60 days of `events` on 2026-09-12, this club alone has **three** live
    /// spellings — "Paris Saint-Germain FC" (14 events), "Paris Saint-Germain"
    /// (9) and "Paris Saint Germain" (9) — and they render as three different
    /// labels today: the full name, "Saint-Germain" and "Germain". One entry
    /// covers all three, which is the half of this defect nobody had named: the
    /// badge has been spelling-independent since #4539 and the label was not, so
    /// the same club read two ways on two pages while both crests said `PSG`.
    /// INTERNAL, not private, so `TeamShortNameTests` can assert the two things
    /// that are invisible from outside and would otherwise rot silently: that no
    /// two clubs claim the same label, and that every key is already in the
    /// normalised form `handPickedKey` produces. A key written as "Paris
    /// Saint-Germain" would be unreachable — a dead entry that every test using
    /// only `short` would pass over.
    static let handPickedLabels: [String: String] = [
        "paris saint germain": "PSG",
    ]

    /// Three-glyph strings that may never appear on a crest, whatever produces
    /// them.
    ///
    /// #4539 — a BACKSTOP, not the fix. The structural cases are removed by
    /// filtering non-distinctive tokens out before counting them (see
    /// `distinctiveTokens`); this catches what is left when three genuinely
    /// distinctive words happen to spell something. Kept explicit and short: a
    /// badge is three uppercase letters, so a substring matcher would be all
    /// false positives.
    ///
    /// This is the browser's `UNSHIPPABLE_BADGES` (`frontend/lib/teamShortName.ts`)
    /// and the two are compared out of source by
    /// `frontend/__tests__/teamDesignatorParityAcrossClients.test.ts`, exactly
    /// as the designator set above is — a transcribed copy that nothing checks
    /// is the third implementation this file exists to prevent.
    private static let unshippableBadges: Set<String> = [
        "ass", "fag", "fuc", "fuk", "cum", "coc", "cok", "cnt", "kkk",
        "nig", "sht", "tit", "twa", "wtf", "jiz", "pis", "sex", "hoe",
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

    /// Is this one competitor written as TWO surnames — a doubles pair?
    ///
    /// #4626, inheriting #3110. The browser has had this test since #3110 and
    /// this file never got it, so the two clients named DIFFERENT players: the
    /// site badges "Siniakova / Townsend" `SIN` and the iPhone badged `TOW`,
    /// because `short` below simply took the last word. "Milutinovic / Van de
    /// Peer" reached the doubles surface reading **`PEE`** during the US Open,
    /// and "Aboian / La Serna J" drew the single glyph **`J`**.
    ///
    /// THE SEPARATOR THAT MEANS "AND" IS A SPACED SLASH, and that is the whole
    /// test — the browser's `isDoublesPair`, same rule, same spelling. An
    /// UNSPACED slash is part of ONE entity's own name and is deliberately not
    /// matched: "Bodo/Glimt" (a club), "Scranton/Wilkes-Barre RailRiders", and
    /// the pairs ESPN writes without spaces ("Krawietz/Puetz") already survive
    /// because a name with no whitespace has no last word to fall off.
    ///
    /// Re-measured for this fix on production 2026-09-10, every distinct side
    /// carrying a spaced slash on an event in the last 30 days: **388 names**,
    /// and of the 300 sampled **297 badge a different player today than the
    /// site does**. All of them are two-part; none has three.
    static func isDoublesPair(_ name: String) -> Bool {
        name.contains(" / ")
    }

    /// The short display label for a team name.
    ///
    /// Returns the input unchanged when there is nothing to shorten, so a caller
    /// never has to supply its own fallback for the empty or single-word case.
    static func short(_ name: String) -> String {
        // #4626 — a pair is returned WHOLE, which is #3110's decision and the
        // browser's behaviour (`teamShortName` line 401). The guard belongs
        // HERE rather than at the badge, because `short` also drives the pair
        // LABELS: without it the app prints one half of a pair as if it were
        // the competitor's whole name, and the doubles final reads as a singles
        // match between two people who were not playing singles.
        if isDoublesPair(name) { return name }
        // #4627 — a hand-picked label is final. It is read BEFORE the rule and
        // not as a repair afterwards, so what a reader sees does not depend on
        // which of the club's spellings the row happens to carry.
        if let picked = handPickedLabels[handPickedKey(name)] { return picked }
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
    ///
    /// 3. **#4539 — a name whose distinctive part is three or more words takes
    ///    their INITIALS.** Both refinements above operate on the label `short`
    ///    hands back, and `short` has already chosen the last word by then, so
    ///    neither can help when the last word is a fragment of a compound rather
    ///    than a name anybody uses: **"Paris Saint Germain" → "Germain" → `GER`**,
    ///    photographed on the browser's Discover card 2026-09-09 12:40 PT (#4466)
    ///    and reached by this function through exactly the same route. The stored
    ///    spelling is an INPUT and both are live, so the second spelling drew a
    ///    second wrong badge an hour later: "Paris Saint-Germain" → "Saint-Germain"
    ///    → `SAI`. Splitting hyphens like spaces is what makes the two agree.
    ///
    /// See `distinctiveTokens` for why this is not a bare word count.
    static func abbreviation(_ name: String) -> String {
        // The shipped rule, still the answer for every two-part name — and the
        // fallback whenever the fork below declines. "Ipswich Town" is `IPS`,
        // "Boston Celtics" is `CEL`, "Altrincham FC" is `ALT`.
        let shipped = glyphs(ofLabel: short(name))
        // #3110 pinned the doubles tile at three glyphs of the FIRST surname, and
        // that decision is not this function's to reopen — a pair is not a
        // compound name, it is two names. `short` returns a pair unchanged, so
        // routing it through the fork would badge "Siniakova / Townsend" as `ST`
        // off two "distinctive" tokens.
        //
        // #4626 — this now reads `isDoublesPair` rather than re-spelling the
        // separator inline. It was the ONLY place in this file that knew what a
        // pair looks like, which is exactly why `short` did not: one rule that
        // exists in one function guards one caller.
        if isDoublesPair(name) { return shipped }
        let distinctive = distinctiveTokens(name)
        guard distinctive.count >= 3 else { return shipped }
        // The initial is the token's first GLYPH, not its first character. A
        // token can open with punctuation the split does not separate on, and
        // `charAt(0)` then puts it on the badge: "Atalanta (1st Leg)" draws
        // **`A(L`** on the browser, which is a bracket on a crest and breaks
        // this file's own three-real-glyphs invariant
        // (`testTheBadgeIsAlwaysThreeRealGlyphs`). Measured 2026-09-09 over the
        // whole production population: 33 distinct names draw a browser badge
        // carrying a character that is neither a letter nor a digit, including
        // the real clubs "Bradford (Park Avenue) AFC" (`B(A`) and "Loyola (Chi)
        // Ramblers" (`L(R`). The browser is wrong here and is deliberately not
        // copied — filed as #4625.
        let initials = String(
            distinctive.compactMap { $0.first(where: { $0.isLetter || $0.isNumber }) }.prefix(3)
        ).uppercased()
        // The residue the token filter cannot reach: a three-part PERSON name is
        // all-distinctive by construction ("Ana Sofia Sanchez" → `ASS`), and no
        // filter that keeps "Paris Saint Germain" working can tell the two apart
        // from the string alone. The surname is the right badge for a person
        // anyway, so reverting to the shipped value is the correct answer rather
        // than a censor. The test is "do not INTRODUCE one", not "never emit
        // one" — names that already paint one by the untouched last-word rule
        // are #4537's, on the browser's evidence, and are not silently
        // re-lettered here.
        if unshippableBadges.contains(initials.lowercased()),
           !unshippableBadges.contains(shipped.lowercased()) {
            return shipped
        }
        return initials
    }

    /// The tokens of a name that identify the CLUB, in order.
    ///
    /// #4539. IT IS NOT A BARE WORD COUNT, AND THAT IS THE WHOLE DESIGN. The
    /// browser measured a first version of this fork that took initials of every
    /// token once a name had three parts, over the whole production population
    /// (19,675 distinct multi-part `events` team names, 2026-09-09): it
    /// introduced 33 badges that were not there before and that nobody may ship
    /// — "Warrington Town FC" → `WTF` and eleven more `<W> Town FC`, "FC Akhmat
    /// Grozny" → `FAG`, "Al Sadd SC" → `ASS`. Every one is a club-type or article
    /// token being counted as if it identified somebody, and filtering them out
    /// FIRST removes the whole class structurally rather than by blocklist:
    /// "Warrington Town FC" keeps `WAR`, "Al Sadd SC" keeps `SAD`, while "Paris
    /// Saint Germain" — three tokens that all identify the club — becomes `PSG`.
    ///
    /// THE PREDICATE IS THE BROWSER'S, REACHED THROUGH THIS FILE'S OWN SET. The
    /// browser's `isNonDistinctiveTrailingWord` is `length <= 2`, its
    /// `CLUB_TYPE_SUFFIXES`, a squad marker, a bare number or a roman numeral.
    /// The clauses below are those, with `designators` standing in for
    /// `CLUB_TYPE_SUFFIXES` — which is sound, and checked, because
    /// `teamDesignatorParityAcrossClients.test.ts` already asserts containment
    /// BOTH ways: every browser suffix is in `designators`, and every member of
    /// `designators` satisfies the browser's predicate. Transcribing the
    /// browser's set into Swift would be a third implementation; borrowing this
    /// file's own set makes the two agree by the guard that already exists.
    ///
    /// Alphanumerics are ASCII-only, matching the browser's `[^A-Za-z0-9]` strip,
    /// so a three-character token carrying two accents counts as short on both
    /// clients rather than on one.
    private static func distinctiveTokens(_ name: String) -> [String] {
        name.components(separatedBy: tokenSeparators)
            .filter { !$0.isEmpty && !isNonDistinctiveToken($0) }
    }

    /// Whitespace plus every dash, so that "Paris Saint-Germain" and "Paris
    /// Saint Germain" — both live on production the same afternoon — split into
    /// the same three tokens and paint the same badge.
    private static let tokenSeparators: CharacterSet = {
        var set = CharacterSet.whitespacesAndNewlines
        set.insert(charactersIn: "-")                                     // U+002D
        set.insert(charactersIn: Unicode.Scalar(0x2010)!...Unicode.Scalar(0x2015)!)
        return set
    }()

    /// The lookup key for `handPickedLabels`: one club, one key, however the row
    /// spells it.
    ///
    /// #4627. Three normalisations, each one paying for a spelling that is live
    /// on production today:
    ///
    /// 1. **Split on dashes as well as whitespace**, borrowing `tokenSeparators`
    ///    from the badge, so "Paris Saint-Germain" and "Paris Saint Germain" are
    ///    one club and not two.
    /// 2. **Drop everything that is not a letter or a digit**, so "1. FC …" and
    ///    "Crimson (W)" key on their words rather than on their punctuation.
    /// 3. **Drop TRAILING designators, but never below two tokens.** "Paris
    ///    Saint-Germain FC" must reach the same entry as "Paris Saint-Germain",
    ///    and the floor is what stops that from merging clubs that a designator
    ///    is the only thing distinguishing: "Manchester United" → `manchester
    ///    united` (not `manchester`, which "Manchester City" would also become),
    ///    "Arsenal W" → `arsenal w` (the women's side keeps its own key),
    ///    "Sunderland AFC" → `sunderland afc`. Stripping is a loop rather than
    ///    one step because both suffixes of "Manchester United FC" are in the
    ///    set, and it stops at the floor.
    ///
    /// Every name in the population runs through this, so it may not be
    /// expensive to be wrong in: a key that matches nothing costs one dictionary
    /// miss and the rule below decides, exactly as it did before.
    ///
    /// INTERNAL for the same reason the table above is. The two-token floor is
    /// unobservable through `short` while the list holds one club — remove it and
    /// every label in the population is byte-identical — so a test that could only
    /// call `short` would be asserting nothing about the clause that stops
    /// "Manchester United" and "Manchester City" becoming one key.
    static func handPickedKey(_ name: String) -> String {
        var tokens = name
            .components(separatedBy: tokenSeparators)
            .map { String($0.filter { $0.isLetter || $0.isNumber }) }
            .filter { !$0.isEmpty }
        while tokens.count >= 3, isDesignator(tokens[tokens.count - 1]) {
            tokens.removeLast()
        }
        return tokens.joined(separator: " ").lowercased()
    }

    /// Is this token incapable of identifying the club on its own?
    ///
    /// Distinct from `isDesignator`, which asks whether a TRAILING word may be a
    /// label all by itself. This one is the browser's rule and is used only by
    /// the badge fork — widening `isDesignator` instead would move `short`, and
    /// the name a reader sees is not what #4539 is about.
    private static func isNonDistinctiveToken<S: StringProtocol>(_ token: S) -> Bool {
        let bare = String(token.filter { $0.isASCII && ($0.isLetter || $0.isNumber) })
        if bare.count <= 2 { return true }
        let lower = bare.lowercased()
        if designators.contains(lower) { return true }
        if lower.allSatisfy(\.isNumber) { return true }                   // 1846
        if lower.first == "u", lower.count == 3,
           lower.dropFirst().allSatisfy(\.isNumber) { return true }       // U20
        if lower.allSatisfy({ $0 == "i" }) { return true }                // III
        return false
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
    ///
    /// #4539 — WHY THE LABELS DECIDE THIS AND NOT ONLY THE BADGES. Growing on
    /// "the two badges are equal" was sufficient while both sides ran one rule.
    /// The initials fork breaks that, because it can move ONE side of a derby off
    /// the word the two clubs share while the other side keeps it — and two
    /// badges that now differ are never grown, so the collision stops being
    /// detected instead of being repaired:
    ///
    ///     FK Septemvri Sofia v PFC Levski Sofia               SEP/LEV → SOF/PLS
    ///     FK Partizan Belgrade v FK Crvena Zvezda Belgrade    PAR/ZVE → BEL/CZB
    ///     Chartres Metropole Handball v Montpellier Handball  MET/MON → CMH/HAN
    ///     AD San Carlos v Inter San Carlos                    SAN/INT → CAR/ISC
    ///
    /// The away side of each keeps a badge naming the CITY — or, worse, the SPORT
    /// — that both sides share, which is #3430's photographed defect surviving in
    /// exactly the derbies #3430 was filed about. `TeamShortNamePairTests` caught
    /// it: 79 of its rows moved when the fork went in on the badges alone.
    ///
    /// The signal was never the badges. It is that `short` returns the same LABEL
    /// for both names, which is what says the two clubs share their distinctive
    /// tail; the badges were only ever a proxy for it, and the fork is what pulled
    /// the proxy off the thing it proxied. Testing the labels directly restores
    /// all 114 of #3430's rescues byte-identical and leaves the fork to the pairs
    /// whose labels already differ — which is every pair the fork exists for.
    static func abbreviationPair(
        away: String,
        home: String,
        awayServed: String? = nil,
        homeServed: String? = nil
    ) -> (away: String, home: String) {
        let awayAbbr = served(awayServed)
        let homeAbbr = served(homeServed)
        let a = awayAbbr ?? abbreviation(away)
        let h = homeAbbr ?? abbreviation(home)
        // A served pair still wins wherever it discriminates, exactly as before:
        // growth is only ever reached for labels we derived ourselves.
        let derived = awayAbbr == nil && homeAbbr == nil
        guard a == h || (derived && short(away) == short(home)) else { return (a, h) }
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
