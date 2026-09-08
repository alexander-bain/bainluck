import XCTest
import SwiftUI
@testable import Bain_Luck

/// native/067 (#2977) — the Discover hero draws the crest the Sports row draws.
///
/// On one launch the same game rendered two ways: the Sports tab drew the Los
/// Angeles Dodgers crest, and the Discover hero drew a flat blue square with the
/// letters "DOD" in it. The Sports row goes through `TeamLogoView`, which has a
/// ladder — served url → flag → ESPN-by-name → coloured fallback. The Discover
/// hero and the guess card each had a shorter private one that stopped at the
/// first rung.
///
/// **The population, measured on production before any code was written**
/// (`/api/feed?limit=200&event_pct=0.6`, 2026-09-08 — 59 event cards, 118 sides):
/// 95 sides carry no avatar url at all, and 51 of those are teams the ESPN rung
/// names. So this is not the one bad team the issue described — on that page both
/// sides of most MLB cards were bare, the Cardinals included.
///
/// Two things are pinned here, and the second is the one that was actually broken:
/// the LADDER (which url wins), and the WIRING (that the cards call it). A correct
/// ladder no surface calls is invisible from the outside.
final class TeamAvatarLadderTests: XCTestCase {

    private let dodgersESPN = "https://a.espncdn.com/combiner/i?img=/i/teamlogos/mlb/500/19.png&w=40&h=40&transparent=true"
    private let servedCrest = "https://cdn.example.com/crests/dodgers.png"
    private let servedFace = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Zverev.jpg"

    /// Team names are parameters, never appended into `body`. An earlier draft let
    /// callers override them by adding a second `"home_team"` key, and Foundation
    /// keeps the FIRST of a duplicate pair — so the World Cup test below silently
    /// asserted about the Dodgers and passed against a mutant. Found by M5.
    private func event(home: String = "Los Angeles Dodgers",
                       away: String = "St. Louis Cardinals",
                       _ body: String) throws -> FeedEventData {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        let json = """
        { "id": 1, "home_team": "\(home)", "away_team": "\(away)", \(body) }
        """
        return try dec.decode(FeedEventData.self, from: Data(json.utf8))
    }

    // MARK: - The ship

    func testANameableTeamWithNoServedCrestStillGetsOne() {
        // THE ship. This is the payload 95 of 118 sides actually arrived in: no
        // headshot, no flag, no `team_data` block — nothing but a name.
        let slot = teamAvatarSlot(avatar: .none, teamName: "Los Angeles Dodgers", sportKey: "baseball_mlb")
        XCTAssertEqual(
            slot, .image(url: URL(string: dodgersESPN)!, isPhotograph: false),
            "a bare payload plus a nameable team is a crest, not a letter tile"
        )
    }

    func testEveryRungTheSportsRowHasDiscoverNowHasToo() {
        // The claim "one ladder" is only worth making if the derived rung agrees
        // with the function the Sports row has always used, for teams across all
        // four leagues rather than the one in the issue.
        for name in ["Los Angeles Dodgers", "St. Louis Cardinals", "Boston Red Sox",
                     "Green Bay Packers", "Boston Celtics", "Toronto Maple Leafs"] {
            XCTAssertEqual(
                teamAvatarURL(servedURL: nil, teamName: name),
                espnTeamLogoURL(for: name),
                "\(name): the derived rung must be the Sports row's rung, not a second copy"
            )
            XCTAssertNotNil(espnTeamLogoURL(for: name), "\(name) should be nameable at all")
        }
    }

    func testATeamThatDroppedItsCityIsStillNameable() {
        // Found on the Sports row while photographing this ship, not by reasoning:
        // the A's are now served as "Athletics", the map was keyed only on
        // "oakland athletics", and a club ESPN still publishes drew a letter "A".
        // 2 of the 95 bare sides measured. Both spellings must resolve, because
        // rows carrying the old name have not all been rewritten.
        for name in ["Athletics", "Oakland Athletics"] {
            guard case let .image(url, _) = teamAvatarSlot(avatar: .none, teamName: name) else {
                return XCTFail("\(name) drew a letter tile")
            }
            XCTAssertTrue(url.absoluteString.contains("/mlb/500/11.png"), "\(name) → \(url)")
        }
    }

    // MARK: - What the ladder must NOT do

    func testAServedCrestIsNeverDisplacedByADerivedOne() {
        // The failure mode of adding a rung is that it outranks a picture that was
        // already right. Order is load-bearing.
        let slot = teamAvatarSlot(
            avatar: ParticipantAvatar(url: servedCrest, isPhotograph: false),
            teamName: "Los Angeles Dodgers", sportKey: "baseball_mlb"
        )
        XCTAssertEqual(slot, .image(url: URL(string: servedCrest)!, isPhotograph: false))
    }

    func testAnEmptyStringIsNotAURL() {
        // A payload with the key and nothing behind it. Treated as a url it blanks
        // the slot; treated as absent it falls through to the crest.
        let slot = teamAvatarSlot(
            avatar: ParticipantAvatar(url: "", isPhotograph: false),
            teamName: "Los Angeles Dodgers"
        )
        XCTAssertEqual(slot, .image(url: URL(string: dodgersESPN)!, isPhotograph: false))
    }

    func testTheEmptyStringGuardHoldsOnTheSportsRowsOwnEntryPoint() {
        // `teamAvatarSlot` filters the empty string before the ladder ever sees it,
        // so the test above cannot reach the guard inside `teamAvatarURL` — M2 sat
        // through it untouched. `TeamLogoView` calls `teamAvatarURL` DIRECTLY with
        // whatever `url` it was handed, so that entry point needs its own proof.
        XCTAssertEqual(
            teamAvatarURL(servedURL: "", teamName: "Los Angeles Dodgers"), dodgersESPN,
            "an empty served url must fall through, not win"
        )
    }

    func testADerivedCrestIsNeverTreatedAsAPhotograph() {
        // #2919's regression, re-armed: a portrait fitted into a square slot is a
        // sliver, so `isPhotograph` crops. A crest cropped square loses its edges.
        // Only a SERVED headshot may carry the flag, whatever the caller passed.
        let slot = teamAvatarSlot(
            avatar: ParticipantAvatar(url: nil, isPhotograph: true),
            teamName: "Los Angeles Dodgers"
        )
        XCTAssertEqual(
            slot, .image(url: URL(string: dodgersESPN)!, isPhotograph: false),
            "the ladder derived this url, so nothing about it is a photograph"
        )
    }

    func testAServedHeadshotStaysAPhotograph() {
        let slot = teamAvatarSlot(
            avatar: ParticipantAvatar(url: servedFace, isPhotograph: true),
            teamName: "Alexander Zverev", sportKey: "tennis_atp_us_open"
        )
        XCTAssertEqual(slot, .image(url: URL(string: servedFace)!, isPhotograph: true))
    }

    func testTheFlagRungIsNationalTeamsOnly() {
        // The hazard in reusing this ladder on Discover: club sides outnumber
        // national ones on the feed, and a country flag on Aston Villa is a worse
        // bug than the letter tile it replaced. 44 of the 95 bare sides measured
        // were clubs, fighters and college teams — they must stay tiles.
        XCTAssertEqual(
            teamAvatarSlot(avatar: .none, teamName: "Aston Villa", sportKey: "soccer_uefa_champs_league"),
            .tile, "a club is not a country"
        )
        // Aston Villa alone does not prove the guard — `flagURL` would have
        // returned nil for it anyway, and M3 survived on exactly that. The guard
        // only earns its line against a CLUB WHOSE NAME IS A COUNTRY, and
        // `countryCodes` carries "america" and "korea" while today's feed carries
        // both a Libertadores and a K-League fixture.
        XCTAssertEqual(
            teamAvatarSlot(avatar: .none, teamName: "America", sportKey: "soccer_conmebol_copa_libertadores"),
            .tile, "Club América must not be handed the flag of the United States"
        )
        XCTAssertEqual(
            teamAvatarSlot(avatar: .none, teamName: "Korea", sportKey: "soccer_korea_kleague1"),
            .tile, "a K-League club is a club, whatever its name matches"
        )
        XCTAssertNotEqual(
            teamAvatarSlot(avatar: .none, teamName: "Germany", sportKey: "soccer_fifa_world_cup"),
            .tile, "a national side in a national competition does get its flag"
        )
    }

    func testAnUnnameableTeamFallsToTheTile() {
        // No rung produced anything: the card's own tile is correct here, and the
        // fix must not invent a url for a team ESPN has never heard of.
        for name in ["Fluminense-RJ", "Havant and Waterlooville FC", "Won Il Kwon"] {
            XCTAssertEqual(
                teamAvatarSlot(avatar: .none, teamName: name, sportKey: "soccer_fa_cup"),
                .tile, "\(name) has no crest to find"
            )
        }
    }

    // MARK: - The wiring — the half that was actually broken

    @MainActor
    func testTheDiscoverHeroCallsTheLadderForBothSides() throws {
        // #2977 was never a broken ladder. It was two cards that did not call one.
        // This asserts against the payload shape production actually serves: the
        // event card carries `home_team`/`away_team` and no `*_team_data` block.
        let e = try event("\"sport\": \"baseball_mlb\"")
        let card = NativeEventDiscoverCard(
            event: e, feedContext: nil, expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        )
        XCTAssertEqual(
            card.avatarSlot(home: true),
            .image(url: URL(string: dodgersESPN)!, isPhotograph: false),
            "the home hero drew 'DOD' on this exact payload"
        )
        guard case .image = card.avatarSlot(home: false) else {
            return XCTFail("the away hero must climb the ladder too — a one-sided fix is how the Cardinals looked fine")
        }
    }

    @MainActor
    func testTheHeroPassesTheWholeSportKeyNotItsFirstComponent() throws {
        // The card has its own `sportKey` property meaning "baseball" — the first
        // component only. Passing that instead of `event.sport` compiles, reads
        // right, and silently blinds the flag rung to every "..._world_cup" key.
        let e = try event(home: "Germany", "\"sport\": \"soccer_fifa_world_cup\"")
        let card = NativeEventDiscoverCard(
            event: e, feedContext: nil, expandedContext: nil,
            navigationPath: .constant(NavigationPath())
        )
        XCTAssertNotEqual(
            card.avatarSlot(home: true), .tile,
            "a truncated sport key would have made this a tile"
        )
    }
}
