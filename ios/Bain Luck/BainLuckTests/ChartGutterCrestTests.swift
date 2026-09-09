import XCTest
@testable import Bain_Luck

/// #3988 — the win-probability chart's gutter draws the crest the Sports row draws.
///
/// `OddsChartView` was the THIRD private one-rung avatar ladder on iOS, after the
/// two `#2977` replaced on the Discover surfaces. The gutter's 14pt crest came
/// straight off `homeTeamLogo`:
///
///     if let logo = homeTeamLogo, let url = URL(string: logo) { AsyncImage(…) }
///
/// A nil served url drew nothing, even for a team `espnTeamLogoURL(for:)` names
/// by heart. **Measured on the production feed of 2026-09-08**
/// (`/api/feed?limit=200&event_pct=0.6`, 59 event cards / 118 sides): 95 sides
/// carry no avatar url at all, and 51 of those are teams the ESPN rung resolves —
/// every MLB team on the page. So the gutter sat bare beside a Sports row drawing
/// real crests for the same games.
///
/// It was left out of #2977 on purpose (milder symptom, decoration beside a label
/// that always renders) and ALLOWLISTED BY NAME in
/// `frontend/__tests__/ios/teamAvatarLadderSingleSource.test.ts` so it stayed a
/// recorded decision. This ship empties that allowlist.
///
/// What is pinned here is the LADDER's answer. That the view BODY asks for it —
/// the half that was actually broken, and invisible to XCTest — is asserted by
/// the jest source scan, which runs in CI, which compiles no Swift.
final class ChartGutterCrestTests: XCTestCase {

    private let served = "https://cdn.example.com/crests/dodgers.png"

    // MARK: - The ship

    /// THE SHIP. The 51 sides: no served url, a name the ESPN rung knows.
    func testANamedTeamWithNoServedURLStillGetsACrest() {
        let url = ChartGutterCrest.resolvedURL(
            servedURL: nil, teamName: "Los Angeles Dodgers", sportKey: "baseball_mlb")
        XCTAssertNotNil(url, "the gutter drew nothing for a team the ESPN rung names")
        XCTAssertEqual(url?.absoluteString, espnTeamLogoURL(for: "Los Angeles Dodgers"))
    }

    /// The rung order is the whole rule: a derived crest that outranks a served
    /// one is a worse bug than the blank this replaced.
    func testAServedURLStillWins() {
        XCTAssertEqual(
            ChartGutterCrest.resolvedURL(
                servedURL: served, teamName: "Los Angeles Dodgers", sportKey: "baseball_mlb"
            )?.absoluteString,
            served
        )
    }

    /// An empty string is not a url — it arrives from a payload that has the key
    /// and nothing behind it, and treating it as one blanks the slot.
    func testAnEmptyServedURLFallsThroughRatherThanWinning() {
        XCTAssertEqual(
            ChartGutterCrest.resolvedURL(
                servedURL: "", teamName: "Los Angeles Dodgers", sportKey: "baseball_mlb"
            )?.absoluteString,
            espnTeamLogoURL(for: "Los Angeles Dodgers")
        )
    }

    // MARK: - The inputs the gutter can be handed

    /// `homeTeamName` is `String?` on this view. With no name, both DERIVED rungs
    /// are dictionary lookups that miss on `""`, so there is nothing to draw and
    /// nothing is drawn — no guess, no crash.
    func testNoTeamNameAndNoServedURLMeansNoCrest() {
        XCTAssertNil(ChartGutterCrest.resolvedURL(
            servedURL: nil, teamName: nil, sportKey: "baseball_mlb"))
        XCTAssertNil(ChartGutterCrest.resolvedURL(
            servedURL: nil, teamName: "", sportKey: "baseball_mlb"))
    }

    /// …but a served url with no name is still a url, and the gutter must draw it.
    ///
    /// This is the pre-#3988 behaviour and the assertion exists because an earlier
    /// draft of the helper broke it: an early `guard let teamName` looks like a
    /// sensible input check and silently drops a crest we were HANDED, since
    /// `servedURL` is the ladder's first rung and needs no name at all. A fresh
    /// regression dressed as a guard.
    func testAServedURLSurvivesAMissingName() {
        XCTAssertEqual(
            ChartGutterCrest.resolvedURL(
                servedURL: served, teamName: nil, sportKey: "baseball_mlb"
            )?.absoluteString,
            served
        )
    }

    // MARK: - The truncation trap

    /// `isInternationalSport` matches on the FULL sport key. Passing "soccer"
    /// compiles, reads right, and silently blinds the flag rung to every
    /// "..._world_cup" key — the exact mistake #2977's guard was written to catch
    /// on the Discover hero, arriving at a third call site.
    func testTheWholeSportKeyReachesTheFlagRung() {
        let whole = ChartGutterCrest.resolvedURL(
            servedURL: nil, teamName: "Brazil", sportKey: "soccer_fifa_world_cup")
        let truncated = ChartGutterCrest.resolvedURL(
            servedURL: nil, teamName: "Brazil", sportKey: "soccer")
        XCTAssertNotNil(whole)
        XCTAssertNotEqual(
            whole, truncated,
            "the flag rung is unreachable — the call site is passing a truncated key"
        )
        XCTAssertEqual(whole?.absoluteString, flagURL(for: "Brazil", width: 80))
    }

    /// The inverse hazard, and the reason the flag rung sits behind a guard.
    ///
    /// `countryCodes` keys on bare nation words — `"america": "us"`, `"korea":
    /// "kr"` — so a CLUB whose name normalises onto one of them resolves to a
    /// national flag. The feed carries Liga MX and K-League fixtures. The guard
    /// is what stops "América" in a domestic league wearing the Stars and
    /// Stripes; this asserts the third call site inherits it.
    ///
    /// Written against a name the flag dictionary genuinely HAS — an earlier
    /// draft used "Club América", which is not a key, so both sides came back
    /// nil and `XCTAssertNotEqual(nil, nil)` failed the test rather than proving
    /// anything. A guard test aimed at a name the mechanism cannot reach proves
    /// nothing whichever way it lands.
    func testAClubIsNotHandedACountrysFlag() {
        XCTAssertNotNil(flagURL(for: "America", width: 80), "the hazard itself must be real")

        let domestic = ChartGutterCrest.resolvedURL(
            servedURL: nil, teamName: "America", sportKey: "soccer_mexico_ligamx")
        XCTAssertNil(domestic, "a domestic club was handed a national flag")

        // …and the same name in a competition that IS international still gets one.
        XCTAssertEqual(
            ChartGutterCrest.resolvedURL(
                servedURL: nil, teamName: "America", sportKey: "soccer_copa_america"
            )?.absoluteString,
            flagURL(for: "America", width: 80)
        )
    }

    // MARK: - Delegation

    /// The point of the ship: the gutter must not hold an opinion of its own.
    /// Written as a sweep over the inputs that actually reach it so a future
    /// fourth rung added to the shared ladder arrives here for free.
    func testTheGutterAgreesWithTheSharedLadderOnEveryInputItSees() {
        let names = ["Los Angeles Dodgers", "St. Louis Cardinals", "Brazil", "Club América", "HPK", ""]
        let keys: [String?] = ["baseball_mlb", "soccer_fifa_world_cup", "soccer_mexico_ligamx",
                               "icehockey_liiga", nil]
        for name in names {
            for key in keys {
                for servedURL in [nil, "", served] as [String?] {
                    let mine = ChartGutterCrest.resolvedURL(
                        servedURL: servedURL, teamName: name, sportKey: key)
                    let shared = teamAvatarURL(
                        servedURL: servedURL, teamName: name, sportKey: key
                    ).flatMap(URL.init(string:))
                    XCTAssertEqual(
                        mine, shared,
                        "the gutter disagrees with the ladder for \(name) / \(key ?? "nil") / \(servedURL ?? "nil")"
                    )
                }
            }
        }
    }
}
