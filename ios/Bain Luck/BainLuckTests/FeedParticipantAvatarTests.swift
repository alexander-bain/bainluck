import XCTest
@testable import Bain_Luck

/// native/006 (#2919 native half) — a US Open card draws the player's face.
///
/// The backend has served `home_image_url` / `away_image_url` / `home_flag_url` /
/// `away_flag_url` on every event since 2026-09-03, and 14 of the 30 event cards in
/// a live `mode=sports` response carry one. The native model decoded none of the
/// four, so the phone drew a coloured "A" where the website drew Alexander Zverev.
///
/// These pin the precedence (`FeedCard.tsx`: served headshot → served flag → the
/// crest the card already had) and, just as importantly, pin that a TEAM card is
/// unchanged — the failure mode of a new avatar source is that it quietly displaces
/// a crest that was already right.
final class FeedParticipantAvatarTests: XCTestCase {

    private func decoder() -> JSONDecoder {
        let dec = JSONDecoder()
        dec.keyDecodingStrategy = .convertFromSnakeCase
        return dec
    }

    private func event(_ body: String) throws -> FeedEventData {
        let json = "{ \"id\": 1, \"home_team\": \"Zverev\", \"away_team\": \"Halys\", \(body) }"
        return try decoder().decode(FeedEventData.self, from: Data(json.utf8))
    }

    private let face = "https://upload.wikimedia.org/wikipedia/commons/thumb/2/2f/Zverev.jpg"
    private let flag = "https://a.espncdn.com/i/teamlogos/countries/500/ger.png"

    // MARK: - Decode

    func testAllFourServedKeysDecode() throws {
        let e = try event("""
        "home_image_url": "\(face)", "away_image_url": null,
        "home_flag_url": "\(flag)", "away_flag_url": null
        """)
        XCTAssertEqual(e.homeImageUrl, face, "the key the phone was missing")
        XCTAssertEqual(e.homeFlagUrl, flag)
        XCTAssertNil(e.awayImageUrl, "a served null is an answer: this player has no photo")
        XCTAssertNil(e.awayFlagUrl)
    }

    // MARK: - Precedence

    func testServedHeadshotWins() throws {
        // Both served: the face is what a person recognises, so the flag loses.
        let e = try event("\"home_image_url\": \"\(face)\", \"home_flag_url\": \"\(flag)\"")
        XCTAssertEqual(e.avatar(home: true).url, face)
    }

    func testServedFlagIsUsedWhenThereIsNoHeadshot() throws {
        // The common case for a qualifier nobody has photographed: a flag still
        // tells you who this is, and it beats a coloured letter.
        let e = try event("\"home_image_url\": null, \"home_flag_url\": \"\(flag)\"")
        XCTAssertEqual(e.avatar(home: true).url, flag)
    }

    func testHomeAndAwaySidesDoNotCross() throws {
        // A one-character slip here puts the wrong player's face on the wrong row,
        // which reads as a matching bug rather than a rendering one.
        let awayFace = "https://example.test/halys.jpg"
        let e = try event("\"home_image_url\": \"\(face)\", \"away_image_url\": \"\(awayFace)\"")
        XCTAssertEqual(e.avatar(home: true).url, face)
        XCTAssertEqual(e.avatar(home: false).url, awayFace)
    }

    // MARK: - The team card must not move

    func testTeamCrestIsUnchangedByTheNewKeys() throws {
        // Team sports get four nulls from the server. The crest the card already
        // drew must still be the crest it draws.
        let crest = "https://a.espncdn.com/i/teamlogos/mlb/500/bos.png"
        let e = try event("""
        "home_image_url": null, "away_image_url": null,
        "home_flag_url": null, "away_flag_url": null,
        "home_team_data": { "id": 7, "name": "Red Sox", "logo_small": "\(crest)" }
        """)
        XCTAssertEqual(e.avatar(home: true).url, crest,
                       "served nulls must never displace a crest that was already right")
    }

    func testEmptyStringIsTreatedAsNoImage() throws {
        // An empty string is not a URL. Passing one through would give
        // `TeamLogoView` a non-nil url it can only fail to load, costing a request
        // and landing on initials anyway — worse than falling through immediately.
        let crest = "https://a.espncdn.com/i/teamlogos/mlb/500/bos.png"
        let e = try event("""
        "home_image_url": "", "home_flag_url": "",
        "home_team_data": { "id": 7, "name": "Red Sox", "logo_small": "\(crest)" }
        """)
        XCTAssertEqual(e.avatar(home: true).url, crest)
    }

    // MARK: - Crest vs photograph (the sliver)

    func testOnlyAServedHeadshotIsMarkedAPhotograph() throws {
        // MEASURED on the simulator, 2026-09-03 23:13 PT: the first build that drew
        // faces scaled Zverev's portrait to FIT a 24pt square, producing an ~11pt
        // sliver with letterbox bars beside a 24pt MLB crest. `isPhotograph` is what
        // tells the view to fill-and-crop instead, so it must be true for a
        // headshot and false for everything else.
        let e = try event("\"home_image_url\": \"\(face)\"")
        XCTAssertTrue(e.avatar(home: true).isPhotograph)
    }

    func testAFlagIsNotAPhotograph() throws {
        // A flag is a wide rectangle whose whole area is the information. Cropping
        // it to a square would cut the stripes off — the mirror-image of the
        // sliver bug, and the reason this is not simply "did the server send it?".
        let e = try event("\"home_image_url\": null, \"home_flag_url\": \"\(flag)\"")
        let avatar = e.avatar(home: true)
        XCTAssertEqual(avatar.url, flag)
        XCTAssertFalse(avatar.isPhotograph, "a flag must still be shown whole")
    }

    func testACrestIsNotAPhotograph() throws {
        let crest = "https://a.espncdn.com/i/teamlogos/mlb/500/bos.png"
        let e = try event("\"home_team_data\": { \"id\": 7, \"name\": \"Red Sox\", \"logo_small\": \"\(crest)\" }")
        XCTAssertFalse(e.avatar(home: true).isPhotograph,
                       "cropping a crest to fill would clip the badge")
    }

    func testNoAvatarIsNotAPhotograph() throws {
        XCTAssertFalse(try event("\"status\": \"live\"").avatar(home: true).isPhotograph)
    }

    // MARK: - Absence

    func testEventWithNoneOfTheFourKeysStillDecodesAndFallsThrough() throws {
        // An older cached payload, or a surface that does not send them at all.
        // Nil hands the decision back to TeamLogoView's existing ladder — the
        // pre-change behaviour exactly, not a blank avatar.
        let e = try event("\"status\": \"live\"")
        XCTAssertNil(e.homeImageUrl)
        XCTAssertNil(e.avatar(home: true).url)
        XCTAssertNil(e.avatar(home: false).url)
    }

    func testRealSportsFeedShapeResolvesAFace() throws {
        // The exact shape production served for a US Open card on 2026-09-03,
        // trimmed. This is the row that reads "A" on the phone today.
        let e = try decoder().decode(FeedEventData.self, from: Data("""
        {
          "id": 15301215, "home_team": "Alexander Zverev", "away_team": "Felix Auger-Aliassime",
          "sport": "tennis_atp", "status": "live",
          "home_image_url": "\(face)", "away_image_url": null,
          "home_flag_url": "\(flag)", "away_flag_url": "https://a.espncdn.com/i/teamlogos/countries/500/can.png"
        }
        """.utf8))
        XCTAssertEqual(e.avatar(home: true).url, face, "Zverev gets his face")
        XCTAssertEqual(e.avatar(home: false).url,
                       "https://a.espncdn.com/i/teamlogos/countries/500/can.png",
                       "no headshot served for the other side, so the flag carries the row")
    }
}
