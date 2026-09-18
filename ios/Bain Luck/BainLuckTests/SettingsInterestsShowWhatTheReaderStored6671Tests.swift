import XCTest
@testable import Bain_Luck

/// #6671 — Settings → Your Interests read `OnboardingSportsData` keys
/// (`football`, `cfb`, `basketball`, `cbb`, `golf`, `aussierules`) while
/// `GET /api/me/preferences` serves the compressed vocabulary (`nfl`,
/// `college_football`, `nba`, `college_basketball`, `golf_pga`/`golf_dp_world`/
/// `golf_lpga`/`golf_liv`). Six tiles read "Nah" for every reader no matter what
/// they had stored, and `cfb`/`cbb` were inert on the WRITE side too — the
/// backend stores an unmapped key verbatim and nothing ever reads it.
///
/// Two vocabularies, both pinned here against
/// `backend/app/routes/user.py` (`SPORT_AFFINITY_MAPPING`,
/// `_expand_sport_affinities`, `_compress_sport_affinities`):
///
///   * WRITE — a tile's `key` must be a key the server expands.
///   * READ  — a tile's `servedKeys` must be categories the server can emit.
///
/// Both halves are now on master: iOS keys the tiles on the served vocabulary,
/// and `SPORT_AFFINITY_MAPPING` carries `"aussierules"` (`user.py:137`), which
/// was the one case iOS could not fix alone. The AFL control that used to live
/// at the bottom of this file asserted the OPPOSITE — and kept passing after the
/// server shipped, because it read the stale fixture below rather than the
/// module. A fixture pinned to a moving module is a guard aimed at itself.
///
/// The two fixtures below were COMPUTED from that module, not read off it by eye
/// (30 write keys, 27 servable categories). Re-derive after any change to
/// `SPORT_AFFINITY_MAPPING` — read the built objects, not an AST re-implementation
/// of how they are built:
///
///     cd backend && python3 -c "
///     from app.routes import user as U
///     print(sorted(U.SPORT_AFFINITY_MAPPING))
///     print(sorted(set(U.SPORT_KEY_TO_CATEGORY.values())))"
@MainActor
final class SettingsInterestsShowWhatTheReaderStored6671Tests: XCTestCase {

    // MARK: - Fixtures

    /// Keys `_expand_sport_affinities` maps to real backend sport keys.
    /// Anything outside this set is passed through verbatim and is inert.
    /// Source: `SPORT_AFFINITY_MAPPING`, `backend/app/routes/user.py`.
    private let serverExpandsTheseWriteKeys: Set<String> = [
        "nfl", "college_football", "nba", "college_basketball",
        "football", "basketball",                      // legacy, still accepted
        "baseball", "hockey", "soccer",
        "golf_pga", "golf_dp_world", "golf_lpga", "golf_liv", "golf",
        "tennis", "mma", "boxing", "cricket", "rugby",
        "aussierules",
        "motorsport", "esports",
        "politics", "entertainment", "crypto", "economics",
        "tech", "weather", "geopolitics", "culture",
    ]

    /// Categories `_compress_sport_affinities` can emit. The legacy spellings
    /// (`football`, `basketball`, `golf`) are absent on purpose: every backend
    /// key they claim is overwritten by a split key when `SPORT_KEY_TO_CATEGORY`
    /// is built, so the server can never serve them back.
    private let serverCanServeTheseCategories: Set<String> = [
        "nfl", "college_football", "nba", "college_basketball",
        "baseball", "hockey", "soccer",
        "golf_pga", "golf_dp_world", "golf_lpga", "golf_liv",
        "tennis", "mma", "boxing", "cricket", "rugby",
        "aussierules",
        "motorsport", "esports",
        "politics", "entertainment", "crypto", "economics",
        "tech", "weather", "geopolitics", "culture",
    ]

    /// The shape `GET /api/me/preferences` returns for a reader who set things
    /// up on the web: all four formerly-dead football/basketball tiles, one golf
    /// tour, and one category iOS has no tile for.
    private let servedPayload: [String: Double] = [
        "nfl": 1.0,
        "college_football": 0.3,
        "nba": 1.0,
        "college_basketball": 0.1,
        "baseball": 1.0,
        "golf_lpga": 0.3,
        "motorsport": 1.0,     // no iOS tile — must survive a save
        "politics": 0.1,
    ]

    private func loadedModel() -> PreferencesViewModel {
        let model = PreferencesViewModel(morningDigestUpdater: { $0 })
        model.apply(loaded: PreferencesResponse(
            homeLocation: nil,
            sportAffinities: servedPayload,
            onboardingCompleted: true,
            favorites: [],
            pushPreferences: nil
        ))
        return model
    }

    // MARK: - The contract itself

    func testEveryTileWritesAKeyTheServerExpands() {
        for item in OnboardingSportsData.allItems {
            XCTAssertTrue(
                serverExpandsTheseWriteKeys.contains(item.key),
                "tile '\(item.name)' writes '\(item.key)', which SPORT_AFFINITY_MAPPING "
                + "does not expand — the tap would be stored verbatim and never read"
            )
        }
    }

    func testEveryTileReadsCategoriesTheServerCanActuallyServe() {
        for item in OnboardingSportsData.allItems {
            XCTAssertFalse(item.servedKeys.isEmpty, "\(item.name) declares no served key")
            for served in item.servedKeys {
                XCTAssertTrue(
                    serverCanServeTheseCategories.contains(served),
                    "tile '\(item.name)' reads '\(served)', which "
                    + "_compress_sport_affinities can never emit — the tile would always read Nah"
                )
            }
        }
    }

    /// The six tiles named in #6671, by the name the reader sees. Fails on the
    /// pre-fix catalog for five of them and is the regression guard for a rename.
    func testTheSixReportedTilesAreNoLongerSpelledTheOldWay() {
        let keysByName = Dictionary(
            uniqueKeysWithValues: OnboardingSportsData.allItems.map { ($0.name, $0.key) }
        )
        XCTAssertEqual(keysByName["NFL"], "nfl")
        XCTAssertEqual(keysByName["College Football"], "college_football")
        XCTAssertEqual(keysByName["NBA"], "nba")
        XCTAssertEqual(keysByName["College Basketball"], "college_basketball")
        XCTAssertEqual(keysByName["Golf"], "golf")
        XCTAssertEqual(
            OnboardingSportsData.allItems.first { $0.name == "Golf" }?.servedKeys,
            ["golf_pga", "golf_dp_world", "golf_lpga", "golf_liv"]
        )
    }

    // MARK: - Reading: the grid shows what the reader stored

    func testASavedPayloadLightsEveryTileTheReaderSet() {
        let model = loadedModel()
        XCTAssertEqual(model.affinityLevel(for: "nfl"), .loveIt)
        XCTAssertEqual(model.affinityLevel(for: "college_football"), .bigMoments)
        XCTAssertEqual(model.affinityLevel(for: "nba"), .loveIt)
        XCTAssertEqual(model.affinityLevel(for: "college_basketball"), .ifWild)
        XCTAssertEqual(model.affinityLevel(for: "baseball"), .loveIt)
        XCTAssertEqual(model.affinityLevel(for: "golf"), .bigMoments)
        XCTAssertEqual(model.affinityLevel(for: "politics"), .ifWild)
    }

    /// The section header counts selected tiles off the same dictionary the grid
    /// reads, so the pre-fix build counted stories the tiles all called "Nah".
    func testTheHeaderCountAgreesWithTheTilesBelowIt() {
        let model = loadedModel()
        let headerCount = model.sportAffinities.filter { $0.value > 0 }.count
        let litTiles = OnboardingSportsData.allItems
            .filter { model.affinityLevel(for: $0.key) != .nah }
            .count
        XCTAssertEqual(headerCount, litTiles)
        XCTAssertEqual(headerCount, 7, "6 sports + politics were stored above zero")
    }

    func testGolfReadsTheStrongestOfItsFourServedTours() {
        let model = PreferencesViewModel(morningDigestUpdater: { $0 })
        model.apply(loaded: PreferencesResponse(
            homeLocation: nil,
            sportAffinities: ["golf_pga": 0.1, "golf_lpga": 1.0, "golf_liv": 0.3],
            onboardingCompleted: true, favorites: [], pushPreferences: nil
        ))
        XCTAssertEqual(model.affinityLevel(for: "golf"), .loveIt)
    }

    func testGolfIsNahWhenNoTourIsServed() {
        let model = PreferencesViewModel(morningDigestUpdater: { $0 })
        model.apply(loaded: PreferencesResponse(
            homeLocation: nil, sportAffinities: ["nfl": 1.0],
            onboardingCompleted: true, favorites: [], pushPreferences: nil
        ))
        XCTAssertEqual(model.affinityLevel(for: "golf"), .nah)
    }

    /// An unset preference must stay ABSENT, not become an explicit 0.0 — both
    /// render "Nah", but a stored zero is a claim the reader never made and it
    /// would be PUT back on the next save.
    func testAnUnsetTileStaysAbsentRatherThanBecomingAStoredZero() {
        let model = loadedModel()
        XCTAssertNil(model.sportAffinities["hockey"])
        XCTAssertEqual(model.affinityLevel(for: "hockey"), .nah)
        XCTAssertNil(model.affinitySavePayload["hockey"])
    }

    // MARK: - Writing: one tap changes one thing

    /// The pre-fix save sent the SERVED dict plus the edited tile, so tapping
    /// NFL sent both `nfl` and `football` — and `football` expands onto
    /// College Football as well, moving a tile the reader never touched.
    func testTappingOneTileSendsItOnceAndNeverItsLegacySpelling() {
        let model = loadedModel()
        model.setAffinity("nfl", level: .ifWild)
        let payload = model.affinitySavePayload

        XCTAssertEqual(payload["nfl"], AffinityLevel.ifWild.rawValue)
        XCTAssertNil(payload["football"], "the legacy spelling would re-expand onto College Football")
        XCTAssertNil(payload["basketball"])
        XCTAssertEqual(payload["college_football"], 0.3, "an untouched tile must not move")
    }

    func testASaveKeepsCategoriesThisBuildHasNoTileFor() {
        let model = loadedModel()
        model.setAffinity("nba", level: .nah)
        XCTAssertEqual(
            model.affinitySavePayload["motorsport"], 1.0,
            "PUT replaces rather than merges, so dropping motorsport here erases it"
        )
    }

    /// Golf writes the legacy key (the only one that reaches all four tours) but
    /// reads the split ones, so the served tours must not ride along or the
    /// expansion order decides the answer.
    func testSavingGolfSendsTheLegacyKeyAloneWithoutTheServedTours() {
        let model = loadedModel()
        model.setAffinity("golf", level: .loveIt)
        let payload = model.affinitySavePayload

        XCTAssertEqual(payload["golf"], 1.0)
        for tour in ["golf_pga", "golf_dp_world", "golf_lpga", "golf_liv"] {
            XCTAssertNil(payload[tour], "\(tour) would fight the legacy key on expansion")
        }
    }

    func testTheSavePayloadNeverCarriesAKeyTheGridCannotShow() {
        let model = loadedModel()
        model.setAffinity("tennis", level: .loveIt)
        let tileKeys = Set(OnboardingSportsData.allItems.map(\.key))
        let unowned = Set(model.affinitySavePayload.keys)
            .subtracting(tileKeys)
            .filter { OnboardingSportsData.ownedKeys.contains($0) }
        XCTAssertTrue(unowned.isEmpty, "owned-but-untileable keys leaked into the save: \(unowned)")
    }

    // MARK: - Onboarding writes the same vocabulary

    func testOnboardingDefaultsUseKeysTheServerExpands() {
        for (key, _) in OnboardingSportsData.defaultAffinities {
            XCTAssertTrue(
                serverExpandsTheseWriteKeys.contains(key),
                "onboarding would submit '\(key)', which the server stores verbatim and never reads"
            )
        }
        XCTAssertEqual(OnboardingSportsData.defaultAffinities["nfl"], 1.0)
        XCTAssertEqual(OnboardingSportsData.defaultAffinities["college_football"], 1.0)
        XCTAssertEqual(OnboardingSportsData.defaultAffinities["college_basketball"], 1.0)
    }

    // MARK: - The gap that is now closed

    /// AFL was dead in BOTH directions: the tap was stored verbatim because
    /// `SPORT_AFFINITY_MAPPING` had no `aussierules` entry, and
    /// `_compress_sport_affinities` — an exact lookup against the reverse of that
    /// same dict — then skipped it, so the value could never come back.
    ///
    /// The server mapping shipped (`user.py:137`), so this is the round trip the
    /// tile could not previously survive: tap, send, serve back, read the level.
    /// The write key doubles as the served key, which is why the tile needs no
    /// explicit `servedKeys`.
    func testAFLHoldsItsValueThroughTheRoundTripNowTheServerMapsIt() {
        XCTAssertTrue(
            serverExpandsTheseWriteKeys.contains("aussierules"),
            "the AFL tap is stored verbatim again — SPORT_AFFINITY_MAPPING lost its aussierules entry"
        )
        XCTAssertTrue(
            serverCanServeTheseCategories.contains("aussierules"),
            "compression can no longer emit aussierules, so the tile would read Nah forever"
        )
        XCTAssertEqual(
            OnboardingSportsData.allItems.first { $0.name == "AFL" }?.servedKeys,
            ["aussierules"]
        )

        // The reader taps AFL, and the app sends exactly that key...
        let model = loadedModel()
        model.setAffinity("aussierules", level: .loveIt)
        XCTAssertEqual(model.affinitySavePayload["aussierules"], 1.0)

        // ...and the next load reads it back, instead of the "Nah" of #6671.
        let reloaded = PreferencesViewModel(morningDigestUpdater: { $0 })
        reloaded.apply(loaded: PreferencesResponse(
            homeLocation: nil,
            sportAffinities: servedPayload.merging(["aussierules": 1.0]) { _, new in new },
            onboardingCompleted: true, favorites: [], pushPreferences: nil
        ))
        XCTAssertEqual(reloaded.affinityLevel(for: "aussierules"), .loveIt)
    }

    /// The #6671 payload as the SERVER actually builds it, not as a fixture
    /// imagines it: this dictionary is the verbatim output of
    /// `_compress_sport_affinities(_expand_sport_affinities(body))` for a reader
    /// who set all 22 tiles, one distinct level each, run against
    /// `backend/app/routes/user.py` on this tree.
    ///
    /// An all-one-value probe cannot see one tile's value landing on another —
    /// which was the second half of #6671, where a single NFL tap moved College
    /// Football. Distinct levels are what make that observable.
    func testTheRealServedPayloadLightsAllTwentyTwoTilesAtTheLevelTheReaderSet() {
        let served: [String: Double] = [
            "nfl": 1.0, "college_football": 0.3, "nba": 0.1, "college_basketball": 1.0,
            "baseball": 0.3, "hockey": 0.1, "mma": 1.0, "boxing": 0.3,
            "golf_pga": 0.1, "golf_dp_world": 0.1, "golf_lpga": 0.1, "golf_liv": 0.1,
            "tennis": 1.0, "soccer": 0.3, "cricket": 0.1, "rugby": 1.0,
            "aussierules": 0.3,
            "politics": 0.1, "entertainment": 1.0, "crypto": 0.3, "economics": 0.1,
            "tech": 1.0, "weather": 0.3, "geopolitics": 0.1, "culture": 1.0,
        ]
        let expected: [String: AffinityLevel] = [
            "nfl": .loveIt, "college_football": .bigMoments, "nba": .ifWild,
            "college_basketball": .loveIt, "baseball": .bigMoments, "hockey": .ifWild,
            "mma": .loveIt, "boxing": .bigMoments, "golf": .ifWild, "tennis": .loveIt,
            "soccer": .bigMoments, "cricket": .ifWild, "rugby": .loveIt,
            "aussierules": .bigMoments,
            "politics": .ifWild, "entertainment": .loveIt, "crypto": .bigMoments,
            "economics": .ifWild, "tech": .loveIt, "weather": .bigMoments,
            "geopolitics": .ifWild, "culture": .loveIt,
        ]

        let model = PreferencesViewModel(morningDigestUpdater: { $0 })
        model.apply(loaded: PreferencesResponse(
            homeLocation: nil, sportAffinities: served,
            onboardingCompleted: true, favorites: [], pushPreferences: nil
        ))

        XCTAssertEqual(
            expected.count, OnboardingSportsData.allItems.count,
            "a tile was added or removed — extend this payload rather than narrowing it"
        )
        for item in OnboardingSportsData.allItems {
            XCTAssertEqual(
                model.affinityLevel(for: item.key), expected[item.key],
                "tile '\(item.name)' reads \(model.affinityLevel(for: item.key).label) "
                + "from the payload the server actually serves"
            )
        }
        XCTAssertFalse(
            OnboardingSportsData.allItems.contains { model.affinityLevel(for: $0.key) == .nah },
            "#6671 is exactly a tile reading Nah for a reader who set it"
        )
    }
}
