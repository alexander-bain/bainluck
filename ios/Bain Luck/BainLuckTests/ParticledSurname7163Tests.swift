import XCTest
@testable import Bain_Luck

/// #7163 — a person's surname keeps the particles that govern it.
///
/// `short` ended `return String(last)` and took no sport, so **"Alex de Minaur"
/// rendered "Minaur"** — the object of a nobiliary particle, printed without the
/// particle, which is not the player's name and is not anybody's name.
/// ux/1356 photographed it on the browser's event hero, fixed the browser
/// (`dc20ddf8f`, `NAME_PARTICLES` + `particledSurnameStart`) and routed the
/// Swift twin here under notice 41. The payload was never wrong:
/// `home_team: "de Minaur"`, `sport: "tennis_other"`.
///
/// THE GATE IS THE FIX'S SAFETY ARGUMENT, so half this file tests the gate
/// rather than the rule. ux measured the ungated form over the whole production
/// name population: **56.3% of 2,797 multi-word soccer names** would shorten
/// differently, and "Tigres de la UANL" would read "de la UANL". A club can
/// never reach the walk, and a caller that does not know its sport gets today's
/// label to the character — the two properties asserted last.
final class ParticledSurname7163Tests: XCTestCase {

    // MARK: - The reported defect

    /// The issue's own name, in both spellings production carries.
    func testTheReportedNameKeepsItsParticle() {
        XCTAssertEqual(TeamShortName.short("Alex de Minaur", sportKey: "tennis_other"), "de Minaur")
        XCTAssertEqual(TeamShortName.short("de Minaur", sportKey: "tennis_other"), "de Minaur")
    }

    /// One specimen per particle ux measured as a real penultimate token, so the
    /// nine measured entries are exercised rather than listed.
    func testEveryMeasuredParticleIsExercised() {
        let cases: [(String, String, String)] = [
            ("Alex de Minaur", "tennis_other", "de Minaur"),
            ("Tim van Rijthoven", "tennis_other", "van Rijthoven"),
            ("Santiago De la Fuente", "tennis_other", "De la Fuente"),
            ("Anna von der Schulenburg", "tennis_wta", "von der Schulenburg"),
            ("Alexander Huertas del Pino", "tennis_other", "del Pino"),
            ("Kilian von Deichmann", "tennis_other", "von Deichmann"),
            ("Christiaan le Roux", "tennis_other", "le Roux"),
            ("Joao dos Santos", "mma_mixed_martial_arts", "dos Santos"),
            ("Rogerio Dutra da Silva", "tennis_other", "da Silva"),
        ]
        for (name, sport, expected) in cases {
            XCTAssertEqual(TeamShortName.short(name, sportKey: sport), expected, name)
        }
    }

    /// The particles STACK, which is why the walk is a loop. Stopping after one
    /// step hands back "de Zandschulp" — the same defect one token along.
    func testTheWalkCrossesStackedParticles() {
        XCTAssertEqual(
            TeamShortName.short("Botic van de Zandschulp", sportKey: "tennis_other"),
            "van de Zandschulp"
        )
        XCTAssertEqual(
            TeamShortName.short("Hans Meyer auf der Heide", sportKey: "tennis_other"),
            "auf der Heide"
        )
        XCTAssertEqual(
            TeamShortName.short("Maria de las Casas", sportKey: "tennis_wta"),
            "de las Casas"
        )
    }

    /// Case-insensitive, because production stores both spellings. The cost is
    /// named in the source: a FIRST name that spells a particle returns the
    /// whole name, which is less short and still a string the person is called.
    func testMatchingIsCaseInsensitiveAndItsCostIsPinned() {
        XCTAssertEqual(
            TeamShortName.short("Botic Van de Zandschulp", sportKey: "tennis_other"),
            "Van de Zandschulp"
        )
        // The accepted cost, asserted so a later reader sees it was chosen.
        XCTAssertEqual(TeamShortName.short("Van Johnson", sportKey: "boxing_boxing"), "Van Johnson")
    }

    /// A person's name with no particle is untouched — the rule must not widen
    /// every individual-sport label, only the ones a particle governs.
    func testAnOrdinarySurnameIsUnchanged() {
        for sport in ["tennis_other", "tennis_wta", "golf", "mma_mixed_martial_arts", "boxing_boxing"] {
            XCTAssertEqual(TeamShortName.short("Tallon Griekspoor", sportKey: sport), "Griekspoor", sport)
            XCTAssertEqual(TeamShortName.short("Jannik Sinner", sportKey: sport), "Sinner", sport)
        }
    }

    // MARK: - The gate

    /// The clause ux measured. Ungated, the walk crosses "la" then "de" and
    /// hands a reader "de la UANL".
    func testAClubCanNeverReachTheWalk() {
        for sport in ["soccer_mexico_ligamx", "soccer_spain_la_liga", "basketball_nba", nil] {
            XCTAssertEqual(TeamShortName.short("Tigres de la UANL", sportKey: sport), "UANL", sport ?? "nil")
            XCTAssertEqual(TeamShortName.short("Deportivo de La Coruna", sportKey: sport), "Coruna", sport ?? "nil")
        }
        // …and the same string under a PERSON's key is the club rule's output
        // no longer, which is what makes the line above a gate and not a
        // coincidence of these two names.
        XCTAssertEqual(TeamShortName.short("Tigres de la UANL", sportKey: "tennis_other"), "de la UANL")
    }

    /// An unknown, empty or absent key is a club key: `namesAPerson` can only be
    /// opened by a caller that positively knows the sport.
    func testAnAbsentOrUnknownKeyKeepsTheShippedLabel() {
        for key in [nil, "", "   ", "unknown_thing", "americanfootball_nfl"] {
            XCTAssertEqual(TeamShortName.short("Alex de Minaur", sportKey: key), "Minaur", key ?? "nil")
        }
    }

    /// The gate is `individualSportPrefixes`, read as the key's first SEGMENT —
    /// so a sport whose NAME merely contains one does not open it.
    func testTheGateReadsTheKeysFirstSegment() {
        // #5634 — not a soccer key: that segment now opens the whole-club rule,
        // which keeps "Alex de Minaur" whole for a reason of its own.
        XCTAssertEqual(TeamShortName.short("Alex de Minaur", sportKey: "aussierules_golf_cup"), "Minaur")
        XCTAssertEqual(TeamShortName.short("Alex de Minaur", sportKey: "TENNIS_ATP"), "de Minaur")
    }

    // MARK: - Order against the rules already in this function

    /// The designator refusal runs FIRST, which is the browser's order: a name
    /// whose tail names nothing is shown whole before the walk can see it, so
    /// the two rules can never compose into a label neither would produce.
    ///
    /// 🪤 THE SPECIMEN THAT MAKES THIS TEST REAL IS NOT THE OBVIOUS ONE. The
    /// mutation battery caught this: with "Juan de la Cruz III" the two orders
    /// agree, because the walk looks at the token BEFORE the last one and that
    /// token is "Cruz" — so the walk declines and the refusal answers either
    /// way. Order is only observable when a particle sits DIRECTLY in front of
    /// a tail that names nobody, which is the Portuguese/Spanish "de Sá" shape:
    /// shipped it is the whole name, and with the walk hoisted it collapses to
    /// "de Sa". Verified byte-for-byte against the browser before pinning.
    func testTheDesignatorRefusalStillWinsUnderAPersonsSport() {
        XCTAssertEqual(
            TeamShortName.short("Joao de Sa", sportKey: "tennis_other"),
            "Joao de Sa"
        )
        XCTAssertEqual(
            TeamShortName.short("Juan de la Cruz III", sportKey: "boxing_boxing"),
            "Juan de la Cruz III"
        )
        XCTAssertEqual(
            TeamShortName.short("Miguel de Souza Jr", sportKey: "mma_mixed_martial_arts"),
            "Miguel de Souza Jr"
        )
    }

    /// A doubles pair is returned WHOLE (#3110/#4626) and the sport must not
    /// change that — the guard is above both rules for the same reason.
    func testADoublesPairIsUntouchedUnderAPersonsSport() {
        XCTAssertEqual(
            TeamShortName.short("Milutinovic / Van de Peer", sportKey: "tennis_other"),
            "Milutinovic / Van de Peer"
        )
    }

    /// A hand-picked label (#4627) is still final under a person's key — it is
    /// read before the rule, so no sport can reopen it.
    func testAHandPickedLabelIsStillFinal() {
        XCTAssertFalse(
            TeamShortName.handPickedLabels.isEmpty,
            "the hand-picked table is empty, so the assertion below proves nothing"
        )
        for (_, label) in TeamShortName.handPickedLabels {
            XCTAssertEqual(TeamShortName.short("Paris Saint Germain", sportKey: "tennis_other"), label)
            break
        }
    }

    // MARK: - The pair

    /// The matchup rule carries the sport, because the two competitors of one
    /// fixture are both people or both clubs (#4624's argument, applied here).
    func testThePairCarriesTheSport() {
        let named = TeamShortName.shortPair(
            away: "Alex de Minaur", home: "Jannik Sinner", sportKey: "tennis_other"
        )
        XCTAssertEqual(named.away, "de Minaur")
        XCTAssertEqual(named.home, "Sinner")
    }

    /// Growth may never NARROW what `short` returned. `grown` starts at the
    /// width of the widest label, and a particled surname is two words wide, so
    /// the sport has to reach it too or the collision path would hand back the
    /// bare "Minaur" this fix exists to remove.
    func testGrowthNeverNarrowsAParticledLabel() {
        // A served pair that collides sends BOTH sides into growth. These two
        // names separate at ONE word ("Sousa"/"Silva"), so growth that starts at
        // one — which is what `grown` does if the sport stops at its door —
        // returns immediately with the bare surnames this fix just widened.
        let grown = TeamShortName.shortPair(
            away: "Ana de Sousa", home: "Luis de Silva",
            awayServed: "SOU", homeServed: "SOU",
            sportKey: "tennis_other"
        )
        XCTAssertEqual(grown.away, "de Sousa")
        XCTAssertEqual(grown.home, "de Silva")
        for (label, name) in [(grown.away, "Ana de Sousa"), (grown.home, "Luis de Silva")] {
            let floor = TeamShortName.short(name, sportKey: "tennis_other")
                .split(separator: " ").count
            XCTAssertGreaterThanOrEqual(
                label.split(separator: " ").count, floor,
                "\(name) grew to \(label), which is narrower than its own short label"
            )
        }
        XCTAssertNotEqual(grown.away, grown.home)
    }

    /// Two people who share a particled surname are still told apart.
    func testAParticledDerbyStillSeparates() {
        let named = TeamShortName.shortPair(
            away: "Joao de Sousa", home: "Maria de Sousa", sportKey: "tennis_other"
        )
        XCTAssertNotEqual(named.away, named.home)
        XCTAssertTrue(named.away.contains("Joao"), named.away)
        XCTAssertTrue(named.home.contains("Maria"), named.home)
    }

    // MARK: - The wiring

    /// THE RULE BEING RIGHT IS HALF THE SHIP; the other half is a view asking it
    /// the right question. `EventNavTitle` is the one reader-facing entry point
    /// on this path that is static and therefore reachable from a test — it is
    /// what the back button, the macOS title bar and VoiceOver read — so the
    /// threading is pinned here rather than asserted only in a screenshot.
    func testTheNavTitleCarriesTheSport() {
        XCTAssertEqual(
            EventNavTitle.scoreless(
                away: "Alex de Minaur", home: "Jannik Sinner", sportKey: "tennis_other"
            ),
            "de Minaur vs Sinner"
        )
        // …and without a sport it is byte-identical to what the title said
        // before this change, which is the contract every unthreaded caller has.
        XCTAssertEqual(
            EventNavTitle.scoreless(away: "Alex de Minaur", home: "Jannik Sinner"),
            "Minaur vs Sinner"
        )
    }

    /// The scored rung too, because that is the one a live match shows.
    func testTheScoredNavTitleCarriesTheSport() {
        let rungs = EventNavTitle.rungs(
            away: "Alex de Minaur", home: "Jannik Sinner",
            awayScore: 2, homeScore: 1,
            sportKey: "tennis_other"
        )
        XCTAssertTrue(rungs.labelled.text.contains("de Minaur"), rungs.labelled.text)
    }

    // MARK: - The direction of travel

    /// THE PROPERTY THAT BOUNDS THE BLAST RADIUS: for every name, under every
    /// key, the label is either unchanged or a SUFFIX of the name that is
    /// LONGER than the shipped one. It can never shorten a label, never move to
    /// a different part of the string, and never invent a word.
    func testTheRuleOnlyEverWidensAndOnlyEverLeftward() {
        let names = [
            "Alex de Minaur", "de Minaur", "Botic van de Zandschulp", "Tallon Griekspoor",
            "Tigres de la UANL", "Sport Lisboa e Benfica", "Manchester City FC",
            "Paris Saint-Germain", "Juan de la Cruz III", "Milutinovic / Van de Peer",
            "Van Johnson", "Maria de las Casas", "Charlotte FC", "Davis Love III",
            "Rogerio Dutra da Silva", "Atalanta BC", "1. FC Heidenheim 1846",
        ]
        let keys: [String?] = [nil, "", "tennis_other", "tennis_wta", "golf",
                               "mma_mixed_martial_arts", "boxing_boxing",
                               // #5634 — a soccer key has its own club rule now
                               // (`TeamShortNameSoccerWholeClub5634Tests`), so it
                               // cannot stand in for "a club sport" here.
                               "aussierules_afl", "basketball_nba"]
        for name in names {
            let shipped = TeamShortName.short(name)
            for key in keys {
                let label = TeamShortName.short(name, sportKey: key)
                if label == shipped { continue }
                XCTAssertTrue(
                    label.hasSuffix(shipped),
                    "\(name) under \(key ?? "nil"): \(label) is not \(shipped) widened leftward"
                )
                XCTAssertTrue(name.hasSuffix(label), "\(name) under \(key ?? "nil"): \(label) is not a suffix of the name")
                XCTAssertGreaterThan(label.count, shipped.count, "\(name) under \(key ?? "nil")")
            }
        }
    }

    /// And the club half of that property, stated separately because it is the
    /// one a reviewer actually wants: NO name moves on a club key or no key.
    func testNoNameMovesWithoutAPersonsSport() {
        let names = [
            "Alex de Minaur", "Botic van de Zandschulp", "Tigres de la UANL",
            "Sport Lisboa e Benfica", "Manchester City FC", "Paris Saint-Germain",
            "Deportivo de La Coruna", "Real Sociedad de Futbol", "Bayer 04 Leverkusen",
        ]
        for name in names {
            // #5634 — the soccer arm of this control lives in
            // `TeamShortNameSoccerWholeClub5634Tests` (Benfica, UANL, Coruna).
            for key in [nil, "", "aussierules_afl", "americanfootball_nfl", "icehockey_nhl"] {
                XCTAssertEqual(
                    TeamShortName.short(name, sportKey: key),
                    TeamShortName.short(name),
                    "\(name) moved under \(key ?? "nil")"
                )
            }
        }
    }

    // MARK: - Reachability of the set itself

    /// The set is not a list nobody reads: every entry must be lowercase, and
    /// the walk must actually consult it.
    func testTheParticleSetIsWellFormedAndConsulted() {
        XCTAssertEqual(TeamShortName.nameParticles.count, 27)
        for token in TeamShortName.nameParticles {
            XCTAssertEqual(token, token.lowercased(), token)
            XCTAssertFalse(token.isEmpty)
            // Every entry must be REACHABLE — put it in front of a surname
            // under a person's key and the label must carry it.
            XCTAssertEqual(
                TeamShortName.short("Firstname \(token) Surname", sportKey: "tennis_other"),
                "\(token) Surname",
                token
            )
        }
    }
}
