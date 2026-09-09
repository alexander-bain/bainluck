import XCTest
@testable import Bain_Luck

/// native/078, #4135 — DataGolf is a statistical model, and the app called it a
/// sportsbook.
///
/// Photographed on `bainluck://futures/60393473` ("Amgen Irish Open - Winner",
/// `source: "datagolf"`, `bookmakers: ["datagolf_model"]` — measured against
/// production 2026-09-08). The card contradicted itself three lines running:
///
///     Source  ● Datagolf
///     Probabilities from 1 sportsbook
///     [ Datagolf Model ]
///
/// Two defects in one frame. The noun was unconditional — whatever the
/// `bookmakers` array held was counted and called a sportsbook — and the brand
/// was title-cased from the raw key by a `default:` arm that five surfaces each
/// carried a copy of.
///
/// The passthrough is the defect that outlives the key: a `books` source would
/// print "Books" on four screens with no code change, which is exactly the
/// exposure standing notice 33 asks native to close. `SourceLabels` answers it
/// the way `WinProbSourceCatalog` already answers it for
/// `win_probability_sources` — an allowlist, and a key the app cannot name is a
/// key the app does not print.
///
/// These are pure-function tests and CI compiles no Swift, so the call sites are
/// guarded by `frontend/__tests__/ios/appNamesEverySourceItPrints.test.ts`
/// instead. This file proves the resolver; that file proves it is reached.
final class SourceLabelsTests: XCTestCase {

    // MARK: - Market sources

    /// The four sources production actually serves, measured 2026-09-08:
    /// polymarket 693,368 · kalshi 294,987 · datagolf 345 · odds_api 12.
    func testEveryProductionMarketSourceHasAName() {
        XCTAssertEqual(SourceLabels.label(for: "datagolf"), "DataGolf")
        XCTAssertEqual(SourceLabels.label(for: "kalshi"), "Kalshi")
        XCTAssertEqual(SourceLabels.label(for: "polymarket"), "Polymarket")
        XCTAssertEqual(SourceLabels.label(for: "odds_api"), "Sportsbooks")
    }

    /// The bug as the reader met it: the brand is DataGolf, not "Datagolf".
    func testDataGolfIsNotTitleCasedFromItsKey() {
        XCTAssertEqual(SourceLabels.label(for: "datagolf"), "DataGolf")
        XCTAssertNotEqual(SourceLabels.label(for: "datagolf"), "datagolf".capitalized)
    }

    /// The class of bug, not the instance. `capitalized` on any of these would
    /// have produced a plausible-looking word and shipped.
    func testAnUnnameableSourceYieldsNothingRatherThanTheRawKey() {
        for key in ["books", "sportsbook", "bet365", "a_new_venue", "DATAGOLF", ""] {
            XCTAssertNil(
                SourceLabels.label(for: key),
                "\"\(key)\" must not reach a screen — the app names a source or draws none"
            )
        }
        XCTAssertNil(SourceLabels.label(for: nil))
    }

    /// Notice 33 stated as an assertion rather than as a comment: no market
    /// source can ever render the banned supplier word, because the only way to
    /// render anything is to be in the map.
    func testNoMarketSourceCanEverRenderABannedSupplierWord() {
        for key in ["books", "book", "bookmaker", "bookmakers", "odds_api_bookmaker"] {
            XCTAssertNil(SourceLabels.label(for: key))
        }
    }

    // MARK: - The noun follows what the sources ARE

    /// The whole ship, in one assertion: the DataGolf market's own payload no
    /// longer produces the word "sportsbook" anywhere.
    func testTheDataGolfMarketIsNamedAsAModelAndNeverCountedAsASportsbook() {
        let attribution = SourceLabels.attribution(for: ["datagolf_model"])
        XCTAssertEqual(attribution, "Probabilities from the DataGolf model")
        XCTAssertFalse(
            attribution?.lowercased().contains("sportsbook") ?? true,
            "a statistical model must not be counted under the sportsbook noun"
        )
    }

    /// The over-reach control. NFL Super Bowl Winner (market 86832), verbatim
    /// from `/api/futures/86832` on 2026-09-08 — a genuine sportsbook market,
    /// whose sentence must read exactly as it did before this ship.
    func testARealSportsbookMarketStillSaysSportsbooksAndStillCountsThem() {
        let superBowl = [
            "betmgm", "betonlineag", "betrivers", "bovada",
            "draftkings", "espnbet", "fanduel", "lowvig",
        ]
        XCTAssertEqual(
            SourceLabels.attribution(for: superBowl),
            "Probabilities from 8 sportsbooks"
        )
    }

    func testOneSportsbookIsSingular() {
        XCTAssertEqual(
            SourceLabels.attribution(for: ["draftkings"]),
            "Probabilities from 1 sportsbook"
        )
    }

    func testAMixedMarketNamesTheModelAndCountsTheSportsbooks() {
        XCTAssertEqual(
            SourceLabels.attribution(for: ["datagolf_model", "fanduel", "draftkings"]),
            "Probabilities from the DataGolf model and 2 sportsbooks"
        )
    }

    /// Honest emptiness beats an explained emptiness (standing notice 34): with
    /// nothing nameable to attribute, the app draws no line at all rather than a
    /// sentence about why.
    func testNothingNameableDrawsNoSentence() {
        XCTAssertNil(SourceLabels.attribution(for: []))
        XCTAssertNil(SourceLabels.attribution(for: ["some_new_feed", "another_one"]))
    }

    // MARK: - The sentence and the chips cannot disagree

    /// A reader can count the chips. If an unnameable key were dropped from the
    /// chips but still counted in the sentence, the card would say "8
    /// sportsbooks" above seven of them — a new lie in place of the old one.
    func testTheCountInTheSentenceIsAlwaysTheNumberOfChipsDrawn() {
        let cases: [[String]] = [
            ["betmgm", "betonlineag", "betrivers", "bovada", "draftkings", "espnbet", "fanduel", "lowvig"],
            ["draftkings"],
            ["draftkings", "a_venue_we_cannot_name", "fanduel"],
            ["datagolf_model", "fanduel"],
        ]
        for keys in cases {
            let chips = SourceLabels.sportsbookChips(for: keys)
            guard let sentence = SourceLabels.attribution(for: keys) else {
                XCTAssertTrue(chips.isEmpty, "no sentence, so no chips: \(keys)")
                continue
            }
            if chips.isEmpty {
                XCTAssertFalse(sentence.contains("sportsbook"), "no chips, so no count: \(sentence)")
            } else {
                XCTAssertTrue(
                    sentence.contains("\(chips.count) sportsbook"),
                    "\"\(sentence)\" does not match its \(chips.count) chips"
                )
            }
        }
    }

    /// `lowvig` was live on the Super Bowl card and unmapped, so it drew
    /// "Lowvig" — the same passthrough defect on the contributor row.
    func testEverySportsbookOnTheLiveSuperBowlCardIsNamed() {
        let superBowl = [
            "betmgm", "betonlineag", "betrivers", "bovada",
            "draftkings", "espnbet", "fanduel", "lowvig",
        ]
        XCTAssertEqual(
            SourceLabels.sportsbookChips(for: superBowl),
            ["BetMGM", "BetOnline", "BetRivers", "Bovada",
             "DraftKings", "ESPN BET", "FanDuel", "LowVig"]
        )
    }

    /// The model is named in the sentence, so repeating it as a chip would say
    /// the same thing twice; and it is not a sportsbook, so it cannot be one.
    func testAModelIsNotDrawnAsASportsbookChip() {
        XCTAssertEqual(SourceLabels.sportsbookChips(for: ["datagolf_model"]), [])
        XCTAssertFalse(SourceLabels.isSportsbook("datagolf_model"))
        XCTAssertTrue(SourceLabels.isSportsbook("draftkings"))
    }

    func testAnUnnameableContributorIsDroppedRatherThanTitleCased() {
        XCTAssertEqual(
            SourceLabels.sportsbookChips(for: ["draftkings", "some_new_book", "fanduel"]),
            ["DraftKings", "FanDuel"]
        )
    }
}
