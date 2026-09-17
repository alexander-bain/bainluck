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
/// The two fixtures below were COMPUTED from that module's AST, not read off it
/// by eye (29 write keys, 26 servable categories). Re-derive after any change
/// to `SPORT_AFFINITY_MAPPING`:
///
///     cd backend && python3 -c "
///     import ast
///     t = ast.parse(open('app/routes/user.py').read())
///     m = next(ast.literal_eval(n.value) for n in t.body
///              if getattr(getattr(n, 'target', None), 'id', '') == 'SPORT_AFFINITY_MAPPING')
///     print(sorted(m))
///     s = {}
///     for cat, keys in m.items():
///         for k in keys:
///             s.setdefault(k, cat) if cat in {'football','basketball','golf'} else s.__setitem__(k, cat)
///     print(sorted(set(s.values())))"
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
            // AFL is the one known gap and has its own control below.
            if item.key == "aussierules" { continue }
            XCTAssertTrue(
                serverExpandsTheseWriteKeys.contains(item.key),
                "tile '\(item.name)' writes '\(item.key)', which SPORT_AFFINITY_MAPPING "
                + "does not expand — the tap would be stored verbatim and never read"
            )
        }
    }

    func testEveryTileReadsCategoriesTheServerCanActuallyServe() {
        for item in OnboardingSportsData.allItems {
            if item.key == "aussierules" { continue }
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
        for (key, _) in OnboardingSportsData.defaultAffinities where key != "aussierules" {
            XCTAssertTrue(
                serverExpandsTheseWriteKeys.contains(key),
                "onboarding would submit '\(key)', which the server stores verbatim and never reads"
            )
        }
        XCTAssertEqual(OnboardingSportsData.defaultAffinities["nfl"], 1.0)
        XCTAssertEqual(OnboardingSportsData.defaultAffinities["college_football"], 1.0)
        XCTAssertEqual(OnboardingSportsData.defaultAffinities["college_basketball"], 1.0)
    }

    // MARK: - The one gap iOS cannot close

    /// AFL has no entry in SPORT_AFFINITY_MAPPING, so the tile is dead in BOTH
    /// directions no matter what iOS spells it: the tap is stored verbatim, and
    /// `_compress_sport_affinities` skips unknown keys, so the value can never
    /// come back. The backend keys (`aussierules_afl`, `aussierules_other`)
    /// already exist in `sport_keys.py`, so the server fix is one mapping line.
    ///
    /// The round trip below is the real evidence. The fixture assertion is the
    /// reminder: whoever adds the server mapping updates that fixture, and this
    /// control then fails and points at the AFL tile's missing `servedKeys`.
    func testAFLCannotHoldAValueUntilTheServerHasACategoryForIt() {
        XCTAssertFalse(
            serverExpandsTheseWriteKeys.contains("aussierules"),
            "the server now expands aussierules — give the AFL tile its servedKeys and drop this control"
        )

        // The reader taps AFL: the app does send it...
        let model = loadedModel()
        model.setAffinity("aussierules", level: .loveIt)
        XCTAssertEqual(model.affinitySavePayload["aussierules"], 1.0)

        // ...but the next load cannot see it, because compression dropped it.
        let reloaded = PreferencesViewModel(morningDigestUpdater: { $0 })
        reloaded.apply(loaded: PreferencesResponse(
            homeLocation: nil,
            sportAffinities: servedPayload,   // what the server actually serves back
            onboardingCompleted: true, favorites: [], pushPreferences: nil
        ))
        XCTAssertEqual(reloaded.affinityLevel(for: "aussierules"), .nah)
    }
}
