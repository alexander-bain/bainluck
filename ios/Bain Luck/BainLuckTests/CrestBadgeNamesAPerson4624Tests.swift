import XCTest
@testable import Bain_Luck

/// #4624 — the crest badge stops taking a PERSON's initials.
///
/// #4466's fork badges a name whose distinctive part is three or more words by
/// their initials. That is right for a compound CLUB name ("Paris Saint
/// Germain" → `PSG`) and wrong for a person's three names: the tennis reader
/// who knows Eloy Mendez Alcantara calls him Alcantara, and the badge read
/// `EMA`. #4466 said in its own comment that no filter can tell the two apart
/// FROM THE STRING, and that is true — both are all-distinctive by
/// construction. The discriminator is the SPORT, which both clients hold and
/// neither was passing to the badge.
///
/// MEASURED THROUGH THE SHIPPING RULE, NOT A MODEL OF IT (2026-09-18,
/// `artifacts-native-233/`): `swiftc` on this file's subject compiled twice,
/// master's copy against this branch's, run over 10,533 distinct competitor
/// names taken from production events — 5,653 individual-sport names (45 days:
/// tennis 4,577 · mma 624 · boxing 419 · motorsport 31 · golf 2) and a 4,880
/// name team-sport control (21 days, every other prefix), both pulled in hash
/// chunks past the 500-row cap and reconciled against their own `COUNT(*)`:
///
///     individual-sport names that move      361 (6.4%), all off initials
///       of those, onto the surname          360
///       onto a first name                     1  ("Jesus Alejandro Ramos Jr")
///     team-sport names that move              0
///     names that move on the nil key          0
///     names newly painting an unshippable     0
///
/// The single exception is pinned below as what it is: `short` hands back the
/// whole name when the last word is a person suffix, which is the two-part
/// weakness master already has ("Davis Love III" → `DAV`) and not this fork's.
final class CrestBadgeNamesAPerson4624Tests: XCTestCase {

    // MARK: - The reported defect

    /// The issue's own table, badged under the sport the fixture is played in.
    func testAThreePartPersonIsBadgedBySurname() {
        XCTAssertEqual(TeamShortName.abbreviation("Eloy Mendez Alcantara", sportKey: "tennis_other"), "ALC")
        XCTAssertEqual(TeamShortName.abbreviation("Constantin Bittoun Kouzmine", sportKey: "tennis_other"), "KOU")
        XCTAssertEqual(TeamShortName.abbreviation("Sherif Ahmed Abdelaziz", sportKey: "tennis_other"), "ABD")
        XCTAssertEqual(TeamShortName.abbreviation("Petr Bar Biryukov", sportKey: "tennis_other"), "BIR")
    }

    /// Live specimens, read off production the day this shipped — one per sport
    /// in the set that has a population, so the set's entries are not four
    /// lines only one of which is exercised.
    func testEverySportInTheSetIsExercisedByAProductionName() {
        // tennis_wta 15314345, live at 14:00Z on 2026-09-18.
        XCTAssertEqual(TeamShortName.abbreviation("Maristany Zuleta de Reales", sportKey: "tennis_wta"), "REA")
        // boxing_boxing 15311875, 2026-09-20.
        XCTAssertEqual(TeamShortName.abbreviation("Sergio Rio Jimenez", sportKey: "boxing_boxing"), "JIM")
        // mma_mixed_martial_arts 15312080, 2026-09-19.
        XCTAssertEqual(TeamShortName.abbreviation("Joo Sang Yoo", sportKey: "mma_mixed_martial_arts"), "YOO")
        // GOLF HAS NO LIVE PERSON POPULATION AND THE ENTRY IS STILL RIGHT, which
        // is worth saying rather than hiding: production carries exactly two
        // golf-keyed names, both from ONE voided row (`golf_other` 15192773),
        // and that row is a Philippine BASKETBALL fixture mis-keyed as golf
        // (filed separately — it is a matching defect, not a badge one). So the
        // only golf name this gate moves is "Phoenix Fuel Masters" `PFM` → `MAS`,
        // pinned below as the entry's measured cost. A golfer is a person for
        // exactly the reason a tennis player is, so the entry stays and is
        // exercised here on a synthetic three-part name.
        XCTAssertEqual(TeamShortName.abbreviation("Ludvig Aberg Svensson", sportKey: "golf_pga"), "SVE")
    }

    /// The golf entry's whole measured cost, stated as a test so nobody has to
    /// take the sentence above on trust.
    func testTheGolfEntrysOnlyLiveNameIsAMiskeyedClub() {
        XCTAssertEqual(TeamShortName.abbreviation("Phoenix Fuel Masters"), "PFM")
        XCTAssertEqual(TeamShortName.abbreviation("Phoenix Fuel Masters", sportKey: "golf_other"), "MAS")
        // And under the sport it is actually played in, nothing moves.
        XCTAssertEqual(TeamShortName.abbreviation("Phoenix Fuel Masters", sportKey: "basketball_other"), "PFM")
    }

    // MARK: - The gate is the SPORT, not the string

    /// The same four names, unchanged, wherever the sport is not a person's or
    /// is not known. This is the half that says the fix is a discriminator and
    /// not a new string rule — delete the gate and these four go red.
    func testTheSameNamesKeepTheirInitialsWhenTheSportIsNotAPersons() {
        for (name, initials) in [("Eloy Mendez Alcantara", "EMA"),
                                 ("Constantin Bittoun Kouzmine", "CBK"),
                                 ("Sherif Ahmed Abdelaziz", "SAA"),
                                 ("Petr Bar Biryukov", "PBB")] {
            XCTAssertEqual(TeamShortName.abbreviation(name), initials, "nil key: \(name)")
            XCTAssertEqual(TeamShortName.abbreviation(name, sportKey: "soccer_epl"), initials, "club sport: \(name)")
            XCTAssertEqual(TeamShortName.abbreviation(name, sportKey: ""), initials, "empty key: \(name)")
        }
    }

    /// A club keeps its badge under EVERY key, including a person's sport. The
    /// fork is what #4466 measured and this change may not reach it.
    func testACompoundClubIsUntouched() {
        for key in [nil, "soccer_france_ligue_one", "tennis_atp", "boxing_boxing"] {
            XCTAssertEqual(TeamShortName.abbreviation("Paris Saint Germain", sportKey: key), "PSG", "key \(key ?? "nil")")
            XCTAssertEqual(TeamShortName.abbreviation("Paris Saint-Germain", sportKey: key), "PSG", "key \(key ?? "nil")")
        }
        // Not hand-picked, three distinctive tokens, and forking on production
        // today: the fork's own subject, under the sports it is played in.
        XCTAssertEqual(TeamShortName.abbreviation("Notre Dame Fighting Irish", sportKey: "americanfootball_ncaaf"), "NDF")
        XCTAssertEqual(TeamShortName.abbreviation("Ferro Carril Oeste", sportKey: "soccer_argentina_primera_division"), "FCO")
    }

    // MARK: - How the key is read

    /// THE MATCH IS THE KEY'S FIRST SEGMENT, NEVER A SUBSTRING. Every production
    /// key is `<sport>_<tour-or-league>`, so the segment IS the sport. A
    /// `contains` would answer for keys nobody listed, and the case is not
    /// hypothetical: England's Boxing Day fixtures are a plausible
    /// `soccer_england_boxing_day_*` key, and under a substring matcher every
    /// club in it would be badged as a person.
    func testTheSportIsTheKeysFirstSegment() {
        XCTAssertTrue(TeamShortName.namesAPerson(sportKey: "tennis_atp_us_open"))
        XCTAssertTrue(TeamShortName.namesAPerson(sportKey: "TENNIS_ATP"))
        XCTAssertTrue(TeamShortName.namesAPerson(sportKey: "mma_mixed_martial_arts"))
        XCTAssertFalse(TeamShortName.namesAPerson(sportKey: "soccer_england_boxing_day_cup"))
        XCTAssertFalse(TeamShortName.namesAPerson(sportKey: "esports_other"))
        XCTAssertFalse(TeamShortName.namesAPerson(sportKey: "basketball_nba"))
        XCTAssertFalse(TeamShortName.namesAPerson(sportKey: nil))
        XCTAssertFalse(TeamShortName.namesAPerson(sportKey: ""))
    }

    /// The set itself, pinned by value. It is one half of a cross-client
    /// contract (`teamDesignatorParityAcrossClients.test.ts` compares it against
    /// the browser's `INDIVIDUAL_SPORT_PREFIXES` out of source), so a silent
    /// widening here is a silent divergence there.
    func testTheSetIsTheFourSportsThatWereMeasured() {
        XCTAssertEqual(TeamShortName.individualSportPrefixes, ["tennis", "golf", "mma", "boxing"])
    }

    // MARK: - What the person branch may never do

    /// A surname that spells one of the three letters nobody may ship keeps the
    /// initials. The badge is the only thing this change can make WORSE, and it
    /// is the same backstop the fork already carries, read the other way round.
    func testASurnameThatSpellsAnUnshippableBadgeKeepsTheInitials() {
        // "Assis" is a real Brazilian surname; `short` gives it, `glyphs` cuts it
        // to the three letters the set refuses.
        XCTAssertEqual(TeamShortName.abbreviation("Juan Carlos Assis", sportKey: "tennis_other"), "JCA")
        // The control: the same shape with a shippable surname does revert.
        XCTAssertEqual(TeamShortName.abbreviation("Juan Carlos Alves", sportKey: "tennis_other"), "ALV")
    }

    /// A doubles pair is two names, not a compound one, and #3110 pinned its
    /// tile at three glyphs of the FIRST surname. A person's sport is exactly
    /// where every pair lives, so the pair guard has to survive this gate.
    func testADoublesPairIsUntouchedUnderAPersonsSport() {
        XCTAssertEqual(
            TeamShortName.abbreviation("Siniakova / Townsend", sportKey: "tennis_wta"),
            TeamShortName.abbreviation("Siniakova / Townsend")
        )
        XCTAssertEqual(TeamShortName.abbreviation("Cervantes / Molchanov", sportKey: "tennis_atp"), "CER")
    }

    /// THE ONE NAME IN 361 THAT DOES NOT LAND ON THE SURNAME, pinned as itself.
    /// `short` returns the whole name when the last word is a person suffix, so
    /// the badge is the FIRST name. That is master's answer for the two-part
    /// version of the same shape ("Davis Love III" → `DAV`, unchanged by this
    /// diff and asserted here beside it), so it is a pre-existing weakness this
    /// fork never owned — recorded, filed, and deliberately not widened into.
    func testAPersonSuffixStillBadgesTheFirstName() {
        XCTAssertEqual(TeamShortName.abbreviation("Jesus Alejandro Ramos Jr", sportKey: "boxing_boxing"), "JES")
        XCTAssertEqual(TeamShortName.abbreviation("Davis Love III", sportKey: "golf_pga"), "DAV")
        XCTAssertEqual(TeamShortName.abbreviation("Davis Love III"), "DAV")
    }

    /// A hyphenated surname is ONE surname and its badge is the first three
    /// glyphs of the whole of it — eight of the 361 take this path and all eight
    /// are right.
    func testAHyphenatedSurnameBadgesTheWholeSurname() {
        XCTAssertEqual(TeamShortName.abbreviation("Felix Auger-Aliassime", sportKey: "tennis_atp"), "AUG")
        XCTAssertEqual(TeamShortName.abbreviation("Waldo Cortes-Acosta", sportKey: "mma_mixed_martial_arts"), "COR")
    }

    // MARK: - The pair, and the matchup

    /// One key describes the MATCHUP: both competitors of one fixture are
    /// people or both are clubs. A pair that asked per side could badge one side
    /// of a tennis match by the club rule.
    func testThePairJudgesBothSidesByTheOneSport() {
        let tennis = TeamShortName.abbreviationPair(
            away: "Eloy Mendez Alcantara",
            home: "Juan Sebastian Osorio",
            sportKey: "tennis_other"
        )
        XCTAssertEqual(tennis.away, "ALC")
        XCTAssertEqual(tennis.home, "OSO")

        let unsaid = TeamShortName.abbreviationPair(
            away: "Eloy Mendez Alcantara",
            home: "Juan Sebastian Osorio"
        )
        XCTAssertEqual(unsaid.away, "EMA")
        XCTAssertEqual(unsaid.home, "JSO")
    }

    /// A served abbreviation still wins, under a person's sport as everywhere
    /// else — the gate may not reach past the value the API sent.
    func testAServedAbbreviationStillWins() {
        let pair = TeamShortName.abbreviationPair(
            away: "Eloy Mendez Alcantara",
            home: "Juan Sebastian Osorio",
            awayServed: "EMA",
            sportKey: "tennis_other"
        )
        XCTAssertEqual(pair.away, "EMA")
        XCTAssertEqual(pair.home, "OSO")
    }

    /// The circle that draws the badge is `TeamLogoView`, and its `sportKey` has
    /// been a property since the ESPN logo fallback — the badge is what did not
    /// read it. Asserted through the view's own static entry point, which is the
    /// production path and not a paraphrase.
    func testTheCircleAsksWithItsOwnSportKey() {
        XCTAssertEqual(
            TeamLogoView.badge(teamName: "Eloy Mendez Alcantara", opponentName: "Juan Sebastian Osorio", sportKey: "tennis_other"),
            "ALC"
        )
        XCTAssertEqual(
            TeamLogoView.badge(teamName: "Eloy Mendez Alcantara", opponentName: "Juan Sebastian Osorio"),
            "EMA"
        )
    }

    // MARK: - The surface that had the key and did not pass it

    /// The event hero draws both circles and knew the sport all along. This is
    /// an EXISTENCE assertion over the view's source, because the hero is a
    /// `some View` body whose two `TeamLogoView(...)` calls cannot be reached
    /// from a test — and the defect here is an OMISSION, which a ban could not
    /// see.
    func testTheEventHeroPassesItsSport() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()   // BainLuckTests
                .deletingLastPathComponent()   // Bain Luck (project dir)
                .appendingPathComponent("Bain Luck/Views/EventDetailView.swift"),
            encoding: .utf8
        )
        // Stated separately so a moved file reads as "the path is wrong" rather
        // than as the hero having dropped its sport.
        XCTAssertFalse(source.isEmpty, "EventDetailView.swift is not where this test thinks it is")
        let circles = source.components(separatedBy: "TeamLogoView(").dropFirst()
        XCTAssertEqual(circles.count, 2, "the hero's circle count moved; re-read this guard")
        for (index, circle) in circles.enumerated() {
            let call = circle.prefix(while: { $0 != ")" })
            XCTAssertTrue(call.contains("sportKey: event.sport"),
                          "hero circle \(index) draws a badge without telling it the sport")
        }
    }

    /// The circle's OWN body, for the same reason and found the same way: a
    /// mutation that deleted `sportKey:` from `initialsFallback` left every test
    /// above green. `TeamLogoView.badge` is static and directly asserted, so the
    /// RULE is covered — but `initialsFallback` is a `some View` body, so whether
    /// the view actually hands its property to that rule is reachable only from
    /// the source. It is the identical omission the hero had, one layer down: the
    /// property has been on this view since the ESPN logo fallback, and the badge
    /// was the one thing not reading it.
    func testTheCircleBodyPassesItsOwnSportKey() throws {
        let source = try String(
            contentsOf: URL(fileURLWithPath: #filePath)
                .deletingLastPathComponent()   // BainLuckTests
                .deletingLastPathComponent()   // Bain Luck (project dir)
                .appendingPathComponent("Bain Luck/Components/TeamLogoView.swift"),
            encoding: .utf8
        )
        XCTAssertFalse(source.isEmpty, "TeamLogoView.swift is not where this test thinks it is")
        let calls = source.components(separatedBy: "Self.badge(").dropFirst()
        XCTAssertEqual(calls.count, 1, "the circle's badge call count moved; re-read this guard")
        for call in calls {
            XCTAssertTrue(call.prefix(while: { $0 != ")" }).contains("sportKey: sportKey"),
                          "the circle draws its own badge without telling it the sport it holds")
        }
    }
}
