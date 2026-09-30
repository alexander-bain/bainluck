import XCTest
@testable import Bain_Luck

/// #5634 — a national team whose name is more than one word is never shortened,
/// on the iPhone as on the site (web PR #9180).
///
/// WHAT THE READER SAW: `/events/15195324`, UEFA Nations League, Czech Republic
/// 1 – 2 Croatia, Final, 2026-09-26. The site's finished-card strip read
/// **"REPUBLIC — CROATIA"**. `TeamShortName.short` takes the same last word, so
/// every card that asks `shortPair` without a sport printed "Republic" too — and
/// "Zealand", "Korea" for BOTH Koreas, "Arabia", "Leone".
///
/// Expected labels are the input names themselves, never computed from the
/// function under test. The badge rows pin the crest letters as they already
/// were: the label changes, the badge does not.
final class TeamShortNameCountry5634Tests: XCTestCase {

    // MARK: - The label keeps the whole country

    func testTheSpecimenReadsCzechRepublicNotRepublic() {
        XCTAssertEqual(TeamShortName.short("Czech Republic"), "Czech Republic")
        let pair = TeamShortName.shortPair(away: "Czech Republic", home: "Croatia")
        XCTAssertEqual(pair.away, "Czech Republic")
        XCTAssertEqual(pair.home, "Croatia")
    }

    func testMultiWordCountriesAreNeverShortenedWhateverTheSport() {
        let names = [
            "New Zealand", "South Korea", "North Korea", "Korea Republic",
            "Saudi Arabia", "Sierra Leone", "Costa Rica", "United States",
            "Northern Ireland", "South Africa", "Sri Lanka", "Papua New Guinea",
            "Trinidad and Tobago", "Republic of Ireland", "West Indies",
        ]
        for name in names {
            for sport in [nil, "soccer_uefa_nations_league", "rugbyunion_world_cup", "cricket_test_match"] {
                XCTAssertEqual(TeamShortName.short(name, sportKey: sport), name, "\(name) / \(sport ?? "nil")")
            }
        }
    }

    func testBothKoreasStopReadingAsTheSameWord() {
        let pair = TeamShortName.shortPair(away: "South Korea", home: "North Korea")
        XCTAssertEqual(pair.away, "South Korea")
        XCTAssertEqual(pair.home, "North Korea")
    }

    /// The venues' spellings reach their entries: accents, "&", a dotted "St."
    func testTheKeyFoldsAccentsAmpersandsAndPunctuation() {
        for name in ["Côte d'Ivoire", "Bosnia & Herzegovina", "St. Lucia", "São Tomé and Príncipe", "DR Congo"] {
            XCTAssertEqual(TeamShortName.short(name), name, name)
        }
    }

    /// Every entry is already in the form `countryKey` produces — an entry
    /// written any other way could never match and would rot silently.
    func testEveryEntryIsWrittenInKeyForm() {
        for entry in TeamShortName.multiWordCountries {
            XCTAssertEqual(TeamShortName.countryKey(entry), entry, entry)
        }
    }

    // MARK: - Nothing else moves

    /// The entry is the WHOLE name, never a word inside one: a club that merely
    /// contains a country keeps the rule it had.
    func testOnlyTheWholeNameMatches() {
        XCTAssertEqual(TeamShortName.short("Los Angeles Lakers"), "Lakers")
        XCTAssertEqual(TeamShortName.short("New Zealand Breakers"), "Breakers")
        XCTAssertEqual(TeamShortName.short("South Africa Rhinos"), "Rhinos")
        XCTAssertFalse(TeamShortName.isMultiWordCountry("Republic"))
        XCTAssertFalse(TeamShortName.isMultiWordCountry("Croatia"))
    }

    /// The crest letters are the badges they already were (the site's
    /// `shortNameByRule` does the same): "Czech Republic" keeps `REP`.
    func testTheBadgeIsNotReLettered() {
        XCTAssertEqual(TeamShortName.abbreviation("Czech Republic"), "REP")
        XCTAssertEqual(TeamShortName.abbreviation("New Zealand"), "ZEA")
        XCTAssertEqual(TeamShortName.abbreviation("Saudi Arabia"), "ARA")
        let specimen = TeamShortName.abbreviationPair(away: "Czech Republic", home: "Croatia")
        XCTAssertEqual(specimen.away, "REP")
        XCTAssertEqual(specimen.home, "CRO")
        // The derby still grows off the shared word, from the width it always did.
        let koreas = TeamShortName.abbreviationPair(away: "South Korea", home: "North Korea")
        XCTAssertEqual(koreas.away, "SOU")
        XCTAssertEqual(koreas.home, "NOR")
    }
}
