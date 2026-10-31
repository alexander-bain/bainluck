import CryptoKit
import SwiftUI
import XCTest
#if canImport(UIKit)
import UIKit
#endif
@testable import Bain_Luck

// #10868 — esports page (`esports`). Prepared model and interaction checks;
// NOT RUN (no build, simulator, XCTest or typecheck grant for this package).
//
// RETAINED FIXTURE: Nice Try vs Flame Hard, Counter-Strike 2, FOX Legacy Cup
// Group B, best of one, Dust2 — event 15322123, from the approved
// `esportsWinnerHistory.json` (source sha256 422f44d4…), `esportsEvidence.json`
// and `esportsFinalScore.json`. `retainedBlend` holds the 143 admitted blend
// observations as `timestamp home away`: the home column is the source text
// verbatim (every aggregate row strictly before the 17:41 terminal witness with
// a probability strictly inside 0–1; the terminal 100% row is excluded). The
// away column is the already verified binary blend's own second series (the
// source's verified full-event winner scope with exactly two outcomes), written
// out once, exactly in decimal, by the test author when this fixture was cut;
// the product receives both series and computes no complement. The original
// Polymarket sides are NEVER complemented: `retainedFlameHard` and
// `retainedNiceTryWinner` are their own consensus observations, verbatim. The
// listed 16:15 start is the source's verified start. Actual start, finish,
// projection and map timeline are absent. The raw feed still says suspended;
// the separate Scores24 scoreboard reports 13–1 rounds and 1–0 maps.
//
// PHASE-ADMITTED OWNER FIXTURES. Before the match: the 102 pre-start blend
// observations, the originals at their pre-match readings, no report. During:
// the same plus the blend observations through a CONSTRUCTED in-play cut
// (16:45Z, `constructedLiveCut`) and the one original with in-play
// observations up to that cut; no report, score, settlement or actual. Both
// are CONSTRUCTED frames over genuine retained rows, labelled so by the page
// notice, and never count as genuine phase coverage. At the final everything,
// with the reported result kept apart from probabilities and from each
// contract's own settlement. Inputs that hand a later fact to an earlier phase
// are named hostile controls. Clock words are CONSTRUCTED UTC copy; real
// binding must localize through the existing owner formatter.
//
// PREPARED ROSTER (NOT RUN): see the `func test…` list; each name states the
// obligation it checks.

@MainActor
final class EsportsEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = EsportsEventPagePresentation10868Tests
    private typealias Page = EsportsEventPagePresentation10868
    private typealias Model = EsportsEventPageModel10868
    private typealias Details = OriginalMarketDetails9483
    private typealias Phase = RugbyMatchEventPagePhase10868
    private typealias Card = EsportsEventPageCard10868

    // MARK: - Retained data

    private static let retainedBlend = """
2026-09-30T18:33:00+00:00 0.74 0.26
2026-09-30T18:58:00+00:00 0.71 0.29
2026-09-30T19:21:00+00:00 0.815 0.185
2026-09-30T19:59:00+00:00 0.65 0.35
2026-09-30T20:07:00+00:00 0.775 0.225
2026-09-30T20:17:00+00:00 0.81 0.19
2026-09-30T20:35:00+00:00 0.805 0.195
2026-09-30T20:52:00+00:00 0.8 0.2
2026-09-30T21:11:00+00:00 0.805 0.195
2026-09-30T21:26:00+00:00 0.795 0.205
2026-09-30T22:00:00+00:00 0.785 0.215
2026-09-30T22:11:00+00:00 0.8 0.2
2026-09-30T22:29:00+00:00 0.79 0.21
2026-09-30T23:05:00+00:00 0.785 0.215
2026-09-30T23:31:00+00:00 0.815 0.185
2026-09-30T23:49:00+00:00 0.82 0.18
2026-10-01T00:00:00+00:00 0.7725 0.2275
2026-10-01T00:11:00+00:00 0.7775 0.2225
2026-10-01T00:31:00+00:00 0.77 0.23
2026-10-01T00:47:00+00:00 0.7625 0.2375
2026-10-01T01:15:00+00:00 0.765 0.235
2026-10-01T01:36:00+00:00 0.7875 0.2125
2026-10-01T01:59:00+00:00 0.7675 0.2325
2026-10-01T02:12:00+00:00 0.735 0.265
2026-10-01T02:23:00+00:00 0.7475 0.2525
2026-10-01T02:42:00+00:00 0.74 0.26
2026-10-01T03:12:00+00:00 0.745 0.255
2026-10-01T03:46:00+00:00 0.735 0.265
2026-10-01T03:58:00+00:00 0.7675 0.2325
2026-10-01T04:13:00+00:00 0.7725 0.2275
2026-10-01T04:23:00+00:00 0.77 0.23
2026-10-01T04:51:00+00:00 0.7775 0.2225
2026-10-01T05:02:00+00:00 0.785 0.215
2026-10-01T05:15:00+00:00 0.79 0.21
2026-10-01T05:33:00+00:00 0.7825 0.2175
2026-10-01T05:45:00+00:00 0.7975 0.2025
2026-10-01T06:10:00+00:00 0.7775 0.2225
2026-10-01T06:29:00+00:00 0.7875 0.2125
2026-10-01T06:45:00+00:00 0.7775 0.2225
2026-10-01T07:04:00+00:00 0.765 0.235
2026-10-01T07:40:00+00:00 0.7025 0.2975
2026-10-01T09:14:00+00:00 0.765 0.235
2026-10-01T09:47:00+00:00 0.77 0.23
2026-10-01T10:03:00+00:00 0.7725 0.2275
2026-10-01T10:24:00+00:00 0.7675 0.2325
2026-10-01T10:36:00+00:00 0.7675 0.2325
2026-10-01T10:38:00+00:00 0.77 0.23
2026-10-01T10:40:00+00:00 0.7675 0.2325
2026-10-01T10:48:00+00:00 0.765 0.235
2026-10-01T11:08:00+00:00 0.765 0.235
2026-10-01T11:45:00+00:00 0.765 0.235
2026-10-01T11:50:00+00:00 0.7675 0.2325
2026-10-01T11:51:00+00:00 0.765 0.235
2026-10-01T11:52:00+00:00 0.7675 0.2325
2026-10-01T11:57:00+00:00 0.765 0.235
2026-10-01T12:14:00+00:00 0.765 0.235
2026-10-01T12:20:00+00:00 0.7675 0.2325
2026-10-01T12:23:00+00:00 0.765 0.235
2026-10-01T12:27:00+00:00 0.7675 0.2325
2026-10-01T12:34:00+00:00 0.7675 0.2325
2026-10-01T12:45:00+00:00 0.7675 0.2325
2026-10-01T12:52:00+00:00 0.7625 0.2375
2026-10-01T13:01:00+00:00 0.765 0.235
2026-10-01T13:09:00+00:00 0.7675 0.2325
2026-10-01T13:18:00+00:00 0.7675 0.2325
2026-10-01T13:34:00+00:00 0.7675 0.2325
2026-10-01T13:50:00+00:00 0.7675 0.2325
2026-10-01T13:55:00+00:00 0.7675 0.2325
2026-10-01T14:16:00+00:00 0.7675 0.2325
2026-10-01T14:23:00+00:00 0.775 0.225
2026-10-01T14:29:00+00:00 0.7775 0.2225
2026-10-01T14:34:00+00:00 0.7825 0.2175
2026-10-01T14:44:00+00:00 0.7875 0.2125
2026-10-01T14:45:00+00:00 0.795 0.205
2026-10-01T14:46:00+00:00 0.7975 0.2025
2026-10-01T14:47:00+00:00 0.7925 0.2075
2026-10-01T14:48:00+00:00 0.79 0.21
2026-10-01T14:51:00+00:00 0.795 0.205
2026-10-01T14:52:00+00:00 0.7975 0.2025
2026-10-01T15:00:00+00:00 0.7975 0.2025
2026-10-01T15:04:00+00:00 0.8025 0.1975
2026-10-01T15:06:00+00:00 0.795 0.205
2026-10-01T15:08:00+00:00 0.7925 0.2075
2026-10-01T15:09:00+00:00 0.7925 0.2075
2026-10-01T15:10:00+00:00 0.78 0.22
2026-10-01T15:13:00+00:00 0.7875 0.2125
2026-10-01T15:14:00+00:00 0.7825 0.2175
2026-10-01T15:15:00+00:00 0.7925 0.2075
2026-10-01T15:18:00+00:00 0.79 0.21
2026-10-01T15:19:00+00:00 0.795 0.205
2026-10-01T15:22:00+00:00 0.7925 0.2075
2026-10-01T15:30:00+00:00 0.795 0.205
2026-10-01T15:39:00+00:00 0.7925 0.2075
2026-10-01T15:41:00+00:00 0.795 0.205
2026-10-01T15:43:00+00:00 0.7975 0.2025
2026-10-01T15:53:00+00:00 0.7925 0.2075
2026-10-01T15:58:00+00:00 0.795 0.205
2026-10-01T16:04:00+00:00 0.7925 0.2075
2026-10-01T16:06:00+00:00 0.7925 0.2075
2026-10-01T16:07:00+00:00 0.79 0.21
2026-10-01T16:10:00+00:00 0.785 0.215
2026-10-01T16:12:00+00:00 0.7875 0.2125
2026-10-01T16:15:00+00:00 0.7725 0.2275
2026-10-01T16:16:00+00:00 0.79 0.21
2026-10-01T16:17:00+00:00 0.7875 0.2125
2026-10-01T16:26:00+00:00 0.7975 0.2025
2026-10-01T16:30:00+00:00 0.8 0.2
2026-10-01T16:31:00+00:00 0.7975 0.2025
2026-10-01T16:32:00+00:00 0.795 0.205
2026-10-01T16:36:00+00:00 0.795 0.205
2026-10-01T16:39:00+00:00 0.7775 0.2225
2026-10-01T16:40:00+00:00 0.78 0.22
2026-10-01T16:41:00+00:00 0.8 0.2
2026-10-01T16:42:00+00:00 0.795 0.205
2026-10-01T16:43:00+00:00 0.8 0.2
2026-10-01T16:44:00+00:00 0.8 0.2
2026-10-01T16:45:00+00:00 0.7975 0.2025
2026-10-01T16:46:00+00:00 0.795 0.205
2026-10-01T16:47:00+00:00 0.8025 0.1975
2026-10-01T16:48:00+00:00 0.7825 0.2175
2026-10-01T16:49:00+00:00 0.7875 0.2125
2026-10-01T16:50:00+00:00 0.7825 0.2175
2026-10-01T16:55:00+00:00 0.7875 0.2125
2026-10-01T16:57:00+00:00 0.895 0.105
2026-10-01T16:58:00+00:00 0.8925 0.1075
2026-10-01T17:00:00+00:00 0.895 0.105
2026-10-01T17:02:00+00:00 0.9375 0.0625
2026-10-01T17:03:00+00:00 0.95 0.05
2026-10-01T17:04:00+00:00 0.955 0.045
2026-10-01T17:05:00+00:00 0.96 0.04
2026-10-01T17:06:00+00:00 0.9625 0.0375
2026-10-01T17:07:00+00:00 0.9525 0.0475
2026-10-01T17:08:00+00:00 0.95725 0.04275
2026-10-01T17:09:00+00:00 0.96075 0.03925
2026-10-01T17:10:00+00:00 0.95075 0.04925
2026-10-01T17:13:00+00:00 0.95825 0.04175
2026-10-01T17:14:00+00:00 0.965 0.035
2026-10-01T17:15:00+00:00 0.959 0.041
2026-10-01T17:16:00+00:00 0.96075 0.03925
2026-10-01T17:17:00+00:00 0.997 0.003
2026-10-01T17:24:00+00:00 0.9945 0.0055
2026-10-01T17:28:00+00:00 0.99 0.01
2026-10-01T17:40:00+00:00 0.999 0.001
"""

    /// SHA-256 of the 143 `timestamp home` lines joined by newlines, computed
    /// from the source text when the fixture was cut.
    private static let retainedBlendHomeSHA256 = "6ebfee1f81acc40adab4199671870a0bbe9266ab79dec415eef60b43f2052513"
    private static let retainedStart = "2026-10-01T16:15:00+00:00"
    private static let retainedTerminal = "2026-10-01T17:41:00+00:00"

    /// Flame Hard's own 106 Polymarket consensus observations, `timestamp probability`.
    private static let retainedFlameHard = """
2026-09-30T23:50:26.787111+00:00 0.27
2026-10-01T00:36:47.612859+00:00 0.26
2026-10-01T07:49:15.546848+00:00 0.235
2026-10-01T11:25:21.591182+00:00 0.235
2026-10-01T13:15:43.504422+00:00 0.235
2026-10-01T13:17:43.470063+00:00 0.235
2026-10-01T13:19:43.459524+00:00 0.235
2026-10-01T13:21:43.460488+00:00 0.235
2026-10-01T13:23:43.469182+00:00 0.235
2026-10-01T13:25:43.524794+00:00 0.235
2026-10-01T13:27:43.494007+00:00 0.235
2026-10-01T13:29:43.577499+00:00 0.235
2026-10-01T13:31:43.529340+00:00 0.235
2026-10-01T13:33:43.519945+00:00 0.235
2026-10-01T13:35:43.490823+00:00 0.235
2026-10-01T13:37:43.579778+00:00 0.235
2026-10-01T13:39:43.569047+00:00 0.235
2026-10-01T13:41:43.510706+00:00 0.235
2026-10-01T13:43:43.557059+00:00 0.235
2026-10-01T13:45:43.545748+00:00 0.235
2026-10-01T13:47:43.504248+00:00 0.235
2026-10-01T13:49:43.589868+00:00 0.235
2026-10-01T13:53:43.471535+00:00 0.235
2026-10-01T13:55:43.497463+00:00 0.235
2026-10-01T13:57:43.484381+00:00 0.235
2026-10-01T14:01:43.825663+00:00 0.235
2026-10-01T14:03:43.763827+00:00 0.235
2026-10-01T14:05:43.902411+00:00 0.235
2026-10-01T14:07:43.810669+00:00 0.235
2026-10-01T14:09:43.792090+00:00 0.235
2026-10-01T14:13:43.844458+00:00 0.235
2026-10-01T14:15:21.840192+00:00 0.235
2026-10-01T14:15:43.896960+00:00 0.235
2026-10-01T14:17:43.899479+00:00 0.235
2026-10-01T14:19:43.917211+00:00 0.235
2026-10-01T14:21:44.259337+00:00 0.235
2026-10-01T14:23:44.206081+00:00 0.235
2026-10-01T14:25:44.244741+00:00 0.235
2026-10-01T14:27:44.314549+00:00 0.235
2026-10-01T14:29:44.230829+00:00 0.235
2026-10-01T14:31:44.245916+00:00 0.235
2026-10-01T14:33:44.295828+00:00 0.235
2026-10-01T14:35:44.238660+00:00 0.235
2026-10-01T14:37:51.553793+00:00 0.235
2026-10-01T14:39:44.291649+00:00 0.235
2026-10-01T14:41:44.188597+00:00 0.235
2026-10-01T14:42:43.437760+00:00 0.235
2026-10-01T14:43:44.283546+00:00 0.235
2026-10-01T14:45:44.330544+00:00 0.225
2026-10-01T14:47:44.232003+00:00 0.225
2026-10-01T14:49:44.257050+00:00 0.225
2026-10-01T14:51:44.302778+00:00 0.215
2026-10-01T14:53:44.240793+00:00 0.215
2026-10-01T14:55:44.245155+00:00 0.215
2026-10-01T14:57:44.381801+00:00 0.215
2026-10-01T14:59:44.405034+00:00 0.215
2026-10-01T15:03:44.177764+00:00 0.215
2026-10-01T15:05:44.229406+00:00 0.215
2026-10-01T15:07:44.280545+00:00 0.215
2026-10-01T15:09:44.325695+00:00 0.215
2026-10-01T15:11:44.316797+00:00 0.23
2026-10-01T15:13:44.257229+00:00 0.23
2026-10-01T15:15:44.310636+00:00 0.23
2026-10-01T15:17:44.260398+00:00 0.22
2026-10-01T15:19:44.262120+00:00 0.22
2026-10-01T15:21:44.272369+00:00 0.22
2026-10-01T15:23:44.267817+00:00 0.22
2026-10-01T15:25:44.242161+00:00 0.22
2026-10-01T15:27:44.301224+00:00 0.22
2026-10-01T15:29:44.232214+00:00 0.22
2026-10-01T15:33:44.152640+00:00 0.22
2026-10-01T15:35:44.287621+00:00 0.22
2026-10-01T15:37:44.256666+00:00 0.215
2026-10-01T15:39:44.440393+00:00 0.215
2026-10-01T15:41:44.346734+00:00 0.215
2026-10-01T15:43:44.237805+00:00 0.215
2026-10-01T15:45:44.504288+00:00 0.215
2026-10-01T15:49:44.337452+00:00 0.215
2026-10-01T15:53:44.152051+00:00 0.215
2026-10-01T15:57:44.154961+00:00 0.22
2026-10-01T16:02:06.013150+00:00 0.215
2026-10-01T16:06:06.050891+00:00 0.215
2026-10-01T16:14:06.135805+00:00 0.22
2026-10-01T16:18:06.259023+00:00 0.215
2026-10-01T16:22:06.113267+00:00 0.215
2026-10-01T16:26:06.104345+00:00 0.215
2026-10-01T16:30:06.166823+00:00 0.215
2026-10-01T16:34:06.349179+00:00 0.215
2026-10-01T16:38:06.039043+00:00 0.215
2026-10-01T16:42:06.186233+00:00 0.215
2026-10-01T16:46:06.146295+00:00 0.215
2026-10-01T16:50:06.142695+00:00 0.215
2026-10-01T16:54:06.219059+00:00 0.23
2026-10-01T16:58:06.069604+00:00 0.14
2026-10-01T17:02:06.129965+00:00 0.065
2026-10-01T17:06:06.164386+00:00 0.065
2026-10-01T17:10:06.184265+00:00 0.035
2026-10-01T17:14:06.198728+00:00 0.0435
2026-10-01T17:18:06.216656+00:00 0.0065
2026-10-01T17:22:06.194587+00:00 0.0005
2026-10-01T17:26:06.270146+00:00 0.0005
2026-10-01T17:30:06.272047+00:00 0.0005
2026-10-01T17:34:06.230002+00:00 0.0005
2026-10-01T17:38:06.226567+00:00 0.0005
2026-10-01T18:23:22.214353+00:00 0.0005
2026-10-01T19:30:24.380590+00:00 0.0
"""

    /// Nice Try's own four Polymarket consensus observations in the winner market.
    private static let retainedNiceTryWinner = """
2026-09-30T23:50:26.787111+00:00 0.73
2026-10-01T00:36:47.612859+00:00 0.74
2026-10-01T07:49:15.546848+00:00 0.765
2026-10-01T14:42:43.437760+00:00 0.765
"""

    /// One retained original row, verbatim from `esportsEvidence.json`.
    private struct RetainedOriginal {
        let market: String
        let marketName: String
        let outcomeID: String
        let outcomeName: String
        let key: String
        let category: String
        let isWinner: Bool?
        let resolutionSource: String?
        let observedAt: String
        let probability: String?
        let observations: String
    }

    private static let handicapMarketName = "Map 1 Rounds Handicap: Nice Try (-6.5) vs Flame Hard (+6.5)"
    private static let winnerMarketName = "Counter-Strike: Flame Hard vs Nice Try (BO1) - FOX Legacy Cup Group B"

    private static let marginRow = RetainedOriginal(
        market: "63664403", marketName: handicapMarketName, outcomeID: "239843452", outcomeName: "Nice Try",
        key: "esports-15322123-game-markets.json:spreads:0", category: "spreads", isWinner: nil, resolutionSource: nil,
        observedAt: "2026-10-01T20:54:25.506498+00:00", probability: "1.0",
        observations: "2026-10-01T20:54:25.506498+00:00 1.0")
    private static let niceTryRow = RetainedOriginal(
        market: "63403921", marketName: winnerMarketName, outcomeID: "239325962", outcomeName: "Nice Try",
        key: "esports-15322123-game-markets.json:other:0", category: "other", isWinner: nil, resolutionSource: nil,
        observedAt: "2026-10-01T17:17:19.958391+00:00", probability: "0.999", observations: retainedNiceTryWinner)
    private static let flameHardRow = RetainedOriginal(
        market: "63403921", marketName: winnerMarketName, outcomeID: "239325963", outcomeName: "Flame Hard",
        key: "esports-15322123-game-markets.json:other:1", category: "other", isWinner: false,
        resolutionSource: "api_settlement", observedAt: "2026-10-01T19:30:24.380590+00:00", probability: nil,
        observations: retainedFlameHard)
    private static let handicapRow = RetainedOriginal(
        market: "63403921", marketName: winnerMarketName, outcomeID: "239843454", outcomeName: handicapMarketName,
        key: "esports-15322123-game-markets.json:other:2", category: "other", isWinner: nil, resolutionSource: nil,
        observedAt: "2026-10-01T20:54:25.506498+00:00", probability: "1.0",
        observations: "2026-10-01T20:54:25.506498+00:00 1.0")
    private static let retainedOriginals = [marginRow, niceTryRow, flameHardRow, handicapRow]

    /// Both retained detail captures carry `description: null`: no rules text exists.
    private static let retainedDetailHashes = [
        "esports-63403921-detail.json": "6297b1544bdf035fa0c52aec7e6ba1272ce685b3a1598dbb8d3538a4f7c6d3b3",
        "esports-63664403-detail.json": "c8f8b946cbe377d804429842bb2ada49c1063875c6a2ee22f1b946f2f41a0e1d",
    ]

    /// `esportsFinalScore.json`: the provider lists Flame Hard first.
    private struct RetainedReport {
        let providerOrder: [String]
        let mapsWon: [Int]
        let mapNumber: Int
        let mapName: String
        let roundsWon: [Int]
        let status: String
        let actualStartAt: String?
        let completedAt: String?
        let publisher: String
        let sha256: String
    }

    private static let retainedReport = RetainedReport(
        providerOrder: ["Flame Hard", "Nice Try"], mapsWon: [0, 1], mapNumber: 1, mapName: "Dust2", roundsWon: [1, 13],
        status: "finished", actualStartAt: nil, completedAt: nil, publisher: "Scores24",
        sha256: "e5a5ec1f2adc9bdcf5b0ae552038a073e1b724822b7752d55ce5f6c5af2b3a46")

    // MARK: - Parsing

    private struct Observation: Equatable {
        let text: String
        let at: Int
        let home: String
        let away: String
    }

    private struct Quote: Equatable {
        let text: String
        let at: Int
        let probability: String
    }

    /// Whole UTC seconds of an ISO-8601 instant; any fraction is dropped.
    private static func epoch(_ text: String) -> Int {
        var trimmed = text
        if let dot = trimmed.firstIndex(of: "."), let plus = trimmed.lastIndex(of: "+") {
            trimmed.removeSubrange(dot..<plus)
        }
        return Int(ISO8601DateFormatter().date(from: trimmed)!.timeIntervalSince1970)
    }

    private static let blend: [Observation] = retainedBlend.split(separator: "\n").map { line in
        let parts = line.split(separator: " ").map(String.init)
        return Observation(text: parts[0], at: epoch(parts[0]), home: parts[1], away: parts[2])
    }

    private static func quotes(_ text: String) -> [Quote] {
        text.split(separator: "\n").map { line in
            let parts = line.split(separator: " ").map(String.init)
            return Quote(text: parts[0], at: epoch(parts[0]), probability: parts[1])
        }
    }

    private static let start = epoch(retainedStart)
    private static let terminal = epoch(retainedTerminal)
    private static let constructedLiveCut = epoch("2026-10-01T16:45:00+00:00")
    private static var baseline: Observation { blend.last { $0.at < start }! }

    private static func admitted(_ phase: Phase) -> [Observation] {
        switch phase {
        case .before: blend.filter { $0.at < start }
        case .during: blend.filter { $0.at <= constructedLiveCut }
        case .final: blend
        }
    }

    /// Owner runs: a gap longer than five minutes starts a new run.
    private static func runs(_ observations: [Observation]) -> [[Observation]] {
        var runs: [[Observation]] = []
        for observation in observations {
            if let last = runs.last?.last, observation.at - last.at <= 300 {
                runs[runs.count - 1].append(observation)
            } else {
                runs.append([observation])
            }
        }
        return runs
    }

    /// Constructed UTC clock words.
    private static func clock(_ at: Int, seconds: Bool = false) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = seconds ? "MMM d, HH:mm:ss 'UTC'" : "MMM d, HH:mm 'UTC'"
        return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(at)))
    }

    /// The fixture owner's figure: at most one decimal, half up, no ".0".
    private static func percent(_ raw: String) -> String {
        var value = Decimal(string: raw)! * 100
        var rounded = Decimal()
        NSDecimalRound(&rounded, &value, 1, .plain)
        return NSDecimalNumber(decimal: rounded).stringValue + "%"
    }

    private static func sha256(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    // MARK: - Teams and history

    private struct Team {
        let key: String
        let name: String
        let seriesID: String
        let shape: FieldHistoryShape10868
        let keyShape: FieldHeadlineKeyShape10868
        let tint: Color
        let home: Bool

        func value(_ observation: Observation) -> String { home ? observation.home : observation.away }
    }

    private static let niceTry = Team(key: "NT", name: "Nice Try", seriesID: "blend:nice-try", shape: .circle,
                                      keyShape: .circle, tint: .blue, home: true)
    private static let flameHard = Team(key: "FH", name: "Flame Hard", seriesID: "blend:flame-hard", shape: .diamond,
                                        keyShape: .diamond, tint: .orange, home: false)
    private static let teams = [niceTry, flameHard]

    private static func pointID(_ team: Team, _ at: Int) -> String { "\(team.key)@\(at)" }

    private static func action(_ id: String, _ label: String, available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: available)
    }

    /// The owner's history for a phase, inspecting the exact observation at
    /// `inspecting` (default: the last admitted observation).
    private static func history(_ phase: Phase, inspecting: Int? = nil, observations: [Observation]? = nil,
                                plotHeight: CGFloat = 240,
                                selection: FieldHistoryOriginalSelection10868 = .none,
                                selections: [String: FieldHistorySelection10868]? = nil,
                                before: [String: FieldHistoryReading10868] = [:]) -> FieldHistoryInput10868 {
        let shown = observations ?? admitted(phase)
        let inspectedAt = inspecting ?? shown.last!.at
        let inspected = shown.first { $0.at == inspectedAt }
        let baseline = shown.last { $0.at < start }
        func series(_ team: Team) -> FieldHistorySeries10868 {
            let drawn = Tests.runs(shown).enumerated().map { index, run in
                FieldHistoryRun10868(id: "\(team.key)-run-\(index)", points: run.map {
                    FieldHistoryPoint10868(id: pointID(team, $0.at), x: Double($0.at), probability: Double(team.value($0))!,
                                           style: $0.at < start ? .hollow : .filled)
                })
            }
            let bound: FieldHistoryReading10868? = baseline.map {
                FieldHistoryReading10868.observation(pointID: pointID(team, $0.at), figure: percent(team.value($0)),
                                                     provenance: clock($0.at) + " · blend")
            }
            let ownBefore: FieldHistoryReading10868 = before[team.seriesID]
                ?? bound ?? FieldHistoryReading10868.absent(words: "No pre-match chance recorded")
            let recorded: FieldHistoryReading10868 = inspected.map {
                FieldHistoryReading10868.observation(pointID: pointID(team, $0.at), figure: percent(team.value($0)),
                                                     provenance: clock($0.at) + " · blend")
            } ?? FieldHistoryReading10868.absent(words: "Not recorded at this moment")
            return FieldHistorySeries10868(id: team.seriesID, name: team.name, shape: team.shape, tint: team.tint,
                                           runs: drawn, links: [], labelPointID: nil, before: ownBefore, recorded: recorded,
                                           absentWords: nil, choose: nil)
        }
        let held = selections ?? Dictionary(uniqueKeysWithValues: teams.map { team in
            (team.seriesID, inspected.map { FieldHistorySelection10868.point(id: pointID(team, $0.at), spoken: percent(team.value($0))) }
                ?? FieldHistorySelection10868.absent(words: "Not recorded at this moment"))
        })
        let lower = Double(shown.first!.at), upper = Double(shown.last!.at)
        var xTicks = [FieldHistoryTick10868(value: lower, lines: ["Sep 30", "18:33 UTC"])]
        var guides: [FieldHistoryGuide10868] = []
        if Double(start) >= lower && Double(start) <= upper {
            xTicks.append(FieldHistoryTick10868(value: Double(start), lines: ["Oct 1", "16:15 UTC"]))
            guides.append(FieldHistoryGuide10868(id: "start", x: Double(start), label: "Start"))
        }
        return FieldHistoryInput10868(
            title: "Chance to win", caption: phase == .final ? "Recorded · full journey" : "Recorded so far",
            series: teams.map(series(_:)), selection: selection,
            domain: FieldHistoryDomain10868(lower: lower, upper: upper), ceiling: 1,
            yTicks: [0, 0.25, 0.5, 0.75, 1].map { FieldHistoryTick10868(value: $0, lines: ["\(Int($0 * 100))%"]) },
            xTicks: xTicks, guides: guides, breaks: [],
            readout: .beforeAndInspected(beforeLabel: "Last pre-match",
                                         inspectedLabel: inspectedAt < start ? "Inspected pre-match" : "Recorded after start"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: pre-match", filled: "Filled: after start"),
            comparisonExplanation: nil,
            notes: ["Admitted blend observations only. Gaps longer than five minutes stay blank.",
                    "Constructed UTC clock words."],
            summary: "Nice Try and Flame Hard recorded win chances.", plotHeight: plotHeight,
            unboundReadingWords: "Not bound to this observation", plotUnavailableWords: nil,
            windows: nil, scale: nil, moreOriginals: nil, details: nil,
            expand: action("history.expand", "Full history"), inspect: nil,
            previous: action("history.previous", "Earlier observation"),
            next: action("history.next", "Later observation", available: inspectedAt < shown.last!.at),
            inspection: FieldHistoryInspection10868(
                x: Double(inspectedAt), caption: "Inspected " + clock(inspectedAt), selections: held, choices: [],
                choicePresentation: .buttons(groupLabel: "Observations"),
                note: "Only admitted blend observations are shown."))
    }

    // MARK: - Headline

    private static let headlineScope = "bainluck-blend|15322123|winner"

    private static func ref(_ team: Team, scope: String = Tests.headlineScope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "bainluck-blend", marketID: "15322123-winner", outcomeID: team.key)
    }

    private static func reading(_ label: String, _ text: String, _ detail: String) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail))
    }

    private static func beforeReading(_ team: Team) -> FieldChooserReading10868 {
        reading("Last pre-match", percent(team.value(baseline)), clock(baseline.at) + " · Bain Luck blend")
    }

    private static func laterReading(_ team: Team, _ phase: Phase) -> FieldChooserReading10868 {
        let last = admitted(phase).last!
        return reading("Recorded after start", percent(team.value(last)), clock(last.at) + " · Bain Luck blend")
    }

    private static func finish(_ team: Team) -> FieldFinishPlace10868 {
        team.home
            ? FieldFinishPlace10868(ref: ref(team), reading: reading("Reported result", "13 rounds", "Won the match · Scores24 · Oct 1, 2026"))
            : FieldFinishPlace10868(ref: ref(team), reading: reading("Reported result", "1 round", "Lost the match · Scores24 · Oct 1, 2026"))
    }

    private static func state(_ phase: Phase) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            FieldHeadlineState10868(figure: "BO1", unit: nil, caption: "Scheduled start", detail: "Oct 1, 16:15 UTC",
                                    spoken: "Best of one. Scheduled start Oct 1, 16:15 UTC.", progress: nil)
        case .during:
            FieldHeadlineState10868(figure: "In play", unit: nil, caption: "Constructed in-play frame",
                                    detail: "Recorded through Oct 1, 16:45 UTC",
                                    spoken: "Constructed in-play frame, recorded through Oct 1, 16:45 UTC.", progress: nil)
        case .final:
            FieldHeadlineState10868(figure: "13–1", unit: "rounds", caption: "Nice Try won · Map 1 · Dust2",
                                    detail: "1–0 maps · reported by Scores24 · Oct 1, 2026",
                                    spoken: "Nice Try won 13–1 rounds on Map 1, Dust2, and the match 1–0 in maps, reported by Scores24.",
                                    progress: nil)
        }
    }

    private static func leafPhase(_ phase: Phase) -> FieldOutlookPhase10868 {
        switch phase {
        case .before: .before
        case .during: .during
        case .final: .final
        }
    }

    /// `hostileFinishes: true` hands the reported result to any phase.
    private static func headline(_ phase: Phase, leaf: FieldOutlookPhase10868? = nil,
                                 hostileFinishes: Bool = false) -> FieldHeadlineInput10868 {
        let catalogue = teams.map { team in
            FieldChooserOriginal10868(
                ref: ref(team), name: team.name,
                plan: phase == .before ? .single(beforeReading(team))
                    : .comparison(before: beforeReading(team), later: laterReading(team, phase)),
                preview: FieldChooserPreview10868(history: nil, absence: "History is on the chart"),
                movement: nil, clock: nil, result: nil, browseStatus: "Recorded history available", accent: team.tint)
        }
        let pairs = teams.map { team in
            FieldMovementPair10868(
                ref: ref(team),
                before: FieldMovementObservation10868(probability: Double(team.value(baseline))!, reading: beforeReading(team)),
                later: phase == .before ? nil
                    : FieldMovementObservation10868(probability: Double(team.value(admitted(phase).last!))!,
                                                    reading: laterReading(team, phase)),
                movement: nil, observation: phase == .before ? nil : pointID(team, admitted(phase).last!.at))
        }
        return FieldHeadlineInput10868(
            scope: headlineScope, catalogue: catalogue,
            displayed: teams.map { FieldHeadlineSlot10868(ref: ref($0), name: $0.name, compactName: nil, keyShape: $0.keyShape) },
            pairs: pairs, finishes: phase == .final || hostileFinishes ? teams.map(finish(_:)) : [],
            state: state(phase), phase: leaf ?? leafPhase(phase),
            copy: FieldHeadlineCopy10868(
                eyebrow: "Counter-Strike 2 · FOX Legacy Cup Group B", title: "Nice Try vs Flame Hard",
                graphicLabel: "Pre-match and recorded win chances", beforeLabel: "Last pre-match",
                recordedLabel: "Recorded after start", beforeUnavailable: "Not recorded before the match",
                recordedUnavailable: "No recorded chance", finishLabel: "Reported result",
                finishUnavailable: "Result not reported", empty: "No teams in this update",
                aboutLabel: "Match result and probability sources", aboutHint: "Opens the match Info",
                openHint: "Shows this team on the chart"),
            unavailableWords: "Team unavailable in this update")
    }

    // MARK: - Originals

    private static let originalsScope = "polymarket|15322123|originals"

    private static func identity(_ row: RetainedOriginal) -> Details.Identity {
        Details.Identity(source: "polymarket", market: row.market, side: row.outcomeID)
    }

    private static func selection(_ row: RetainedOriginal, scope: String = Tests.originalsScope) -> Details.Selection {
        Details.Selection(scope: scope, identity: identity(row))
    }

    /// The fixture owner's pre-match election: the last own observation
    /// strictly before the verified start, with a unique timestamp.
    private static func preMatch(_ row: RetainedOriginal) -> Quote? {
        let before = quotes(row.observations).filter { $0.at < start }
        guard let last = before.last, before.filter({ $0.text == last.text }).count == 1 else { return nil }
        return last
    }

    private static func inPlay(_ row: RetainedOriginal) -> Quote? {
        quotes(row.observations).last { $0.at >= start && $0.at <= constructedLiveCut }
    }

    private static func ownReading(_ quote: Quote) -> Details.Reading {
        .value(percent(quote.probability), placement: Double(quote.probability), provenance: clock(quote.at, seconds: true) + " · Polymarket")
    }

    private static let rulesWords = "No rules text was retained for this market."

    /// `hostile: true` hands final settlement and quotes to an earlier phase.
    private static func original(_ row: RetainedOriginal, _ phase: Phase, hostile: Bool = false) -> Details.Original {
        let pregame = preMatch(row).map(ownReading) ?? Details.Reading.missing("No pre-match chance recorded")
        let final = phase == .final || hostile
        var mode = Details.Mode.pregame
        var later: Details.Reading?
        var grade: Details.Grade?
        var quote: Details.HistoricalQuote?
        if final {
            if row.isWinner == false, row.resolutionSource == "api_settlement" {
                mode = .result
                grade = Details.Grade(words: "Lost", provenance: "Contract settlement recorded by the market source · time unknown")
            } else if row.market == marginRow.market {
                mode = .comparison(.recorded)
                later = Details.Reading.missing("No recent probability update")
            }
            if let probability = row.probability {
                quote = Details.HistoricalQuote(text: percent(probability), recorded: clock(epoch(row.observedAt), seconds: true))
            }
        } else if phase == .during, row.market == niceTryRow.market, row.outcomeName != handicapMarketName {
            mode = .comparison(.recorded)
            later = inPlay(row).map(ownReading) ?? Details.Reading.missing("No in-play observation recorded")
        }
        return Details.Original(
            identity: identity(row), title: row.marketName, outcome: row.outcomeName, mode: mode, pregame: pregame,
            later: later, grade: grade,
            about: Details.About(source: "Polymarket", rules: .unavailable(rulesWords),
                                 provenance: [Details.Row(label: "Market id", value: row.market),
                                              Details.Row(label: "Outcome id", value: row.outcomeID),
                                              Details.Row(label: "Retained key", value: row.key)],
                                 historicalQuote: quote),
            beforeLabel: "Pre-match chance")
    }

    private static func originals(_ phase: Phase, selection: Details.Selection? = nil, list: [Details.Original]? = nil,
                                  scope: String = Tests.originalsScope, hostile: Bool = false) -> RugbyMatchEventPageOriginals10868 {
        RugbyMatchEventPageOriginals10868(
            catalogue: Details.Catalogue(scope: scope, originals: list ?? retainedOriginals.map { original($0, phase, hostile: hostile) }),
            selection: selection, heading: "All 4 original outcomes",
            context: "Polymarket · each outcome keeps its own observations and rules",
            emptyWords: "No original outcomes in this update", unavailableChoice: "Unavailable in this update", tint: .blue)
    }

    // MARK: - Stories

    private static let sourcesID = "polymarket-sources"
    private static let reportID = "scores24-report"
    private static let winnerSource = EsportsStorySource10868(sourceID: sourcesID, label: "Polymarket sources and results")
    private static let explanation = "Each original Polymarket side keeps its own pre-match observation. The headline shows the separate Bain Luck blend. Reported rounds do not settle these props."

    private static func side(_ row: RetainedOriginal, _ team: Team, report: Bool) -> EsportsWinnerSide10868 {
        EsportsWinnerSide10868(
            selection: selection(row), name: team.name, tint: team.tint,
            report: !report ? nil : team.home
                ? EsportsSideReport10868(outcome: "Won match", figure: "13", unit: "rounds")
                : EsportsSideReport10868(outcome: "Lost match", figure: "1", unit: "round"))
    }

    /// The ordinary story carries reports at the final only; `hostile: true`
    /// hands them to any phase.
    private static func winner(_ phase: Phase, hostile: Bool = false, sides: [EsportsWinnerSide10868]? = nil,
                               related: [EsportsRelatedOriginal10868]? = nil,
                               source: EsportsStorySource10868? = Tests.winnerSource) -> EsportsWinnerStory10868 {
        let reports = phase == .final || hostile
        return EsportsWinnerStory10868(
            sides: sides ?? [side(niceTryRow, niceTry, report: reports), side(flameHardRow, flameHard, report: reports)],
            related: related ?? [EsportsRelatedOriginal10868(selection: selection(handicapRow), label: "Separate handicap prop")],
            source: source,
            copy: EsportsWinnerCopy10868(
                eyebrow: "Polymarket · 3 outcomes", title: "Match winner", graphicLabel: "Pre-match expectation · match winner",
                sideUnavailable: "Not in this update", selectionMissing: "The selected outcome is not in this update",
                explanation: explanation, reportCaption: reports ? "Reported final · Map 1 Dust2 · Scores24" : nil,
                resultUnavailable: "Match result unavailable", settlementLabel: "Contract result",
                settlementUnconfirmed: "Not confirmed", relatedHeading: "Also in this market",
                selectHint: "Shows this outcome's Details", detailsLabel: "Details", expandLabel: "Expand match winner"))
    }

    private static func margin(_ phase: Phase, hostile: Bool = false, actual: Int? = 12, blocks: Int = 14, minimum: Int = 7,
                               actualFigure: String? = "12") -> EsportsMarginStory10868 {
        let final = phase == .final || hostile
        return EsportsMarginStory10868(
            selection: selection(marginRow),
            scale: EsportsMarginScale10868(blocks: blocks, minimum: minimum, actual: final ? actual : nil),
            source: winnerSource,
            copy: EsportsMarginCopy10868(
                eyebrow: "Polymarket · Map 1 winning margin", title: "Nice Try by 7+ rounds",
                graphicLabel: "Winning margin against the minimum", originalUnavailable: "This prop is not in this update",
                selectionMissing: "The selected outcome is not in this update", minimumMarker: "7+ needed",
                scaleStart: "0", scaleEnd: "\(blocks)",
                blockMeaning: "Each mark represents one round of winning margin, not the order rounds were played.",
                offScale: "Margin outside the shown scale", actualLabel: "Actual winning margin",
                actualFigure: final ? actualFigure : nil, actualUnit: final ? "rounds" : nil,
                actualMarker: final ? "12 actual" : nil, actualUnavailable: "Actual margin not reported",
                delta: final ? "7 needed · 5 beyond the minimum" : nil,
                score: final ? "Nice Try 13–1 Flame Hard · Dust2" : nil,
                resultLabel: "Prop result", resultUnconfirmed: "Prop result unconfirmed",
                resultDetail: "The reported score clears the required margin. The prop's own settlement has not been confirmed.",
                reportSource: final ? "Reported by Scores24" : nil, selectHint: "Shows this outcome's Details",
                detailsLabel: "Details", expandLabel: "Expand winning margin"))
    }

    // MARK: - Page input

    private static func sources(_ phase: Phase) -> [RugbyMatchEventPageSource10868] {
        var documents = [RugbyMatchEventPageSource10868(id: sourcesID, title: "Polymarket · sources & results", sections: [
            RugbyMatchEventPageSection10868(title: "Original sides", paragraphs: [explanation]),
            RugbyMatchEventPageSection10868(title: "Contract results", paragraphs: [
                "Each contract keeps its own settlement record. A reported match result does not settle a prop."]),
        ])]
        if phase == .final {
            documents.append(RugbyMatchEventPageSource10868(id: reportID, title: "Reported match result", sections: [
                RugbyMatchEventPageSection10868(title: "Scores24", paragraphs: [
                    "Scores24 reports Nice Try beat Flame Hard 13–1 rounds on Dust2, winning the best-of-one match 1–0 maps.",
                    "The archived feed still says Suspended. The actual start and finish times are unavailable."]),
            ]))
        }
        return documents
    }

    private static func about(_ phase: Phase) -> RugbyMatchEventPageAbout10868 {
        RugbyMatchEventPageAbout10868(title: "About this match", sections: [
            RugbyMatchEventPageSection10868(title: "Win chances",
                                            paragraphs: ["The headline and chart show the Bain Luck blend. Gaps longer than five minutes stay blank."]),
            RugbyMatchEventPageSection10868(title: "Original markets", paragraphs: [explanation], sourceID: sourcesID),
        ])
    }

    private static let matchCopy = RugbyMatchEventPageCopy10868(
        headlineUnavailable: "Match chances unavailable for this phase", readerUnavailable: "This card is not available now",
        sourceUnavailable: "Source unavailable", sourceLabel: "Source details", catalogueLabel: "All 4 original outcomes",
        comparisonLabel: "Pre-match and recorded chances")

    private static let pageCopy = EsportsEventPageCopy10868(
        storiesLabel: "Match stories", storyUnavailable: "This story is not available now",
        heldOriginalUnavailable: "The selected outcome is not in this update", backLabel: "Back to match",
        previousLabel: "Previous", nextLabel: "Next", historyName: "Chance to win", winnerName: "Match winner",
        marginName: "Map 1 winning margin")

    private static func notice(_ phase: Phase) -> String? {
        switch phase {
        case .before: "Constructed before-match frame from retained history · not a live capture"
        case .during: "Constructed in-play frame cut at Oct 1, 16:45 UTC · not a live capture"
        case .final: nil
        }
    }

    private static func readerHeader(_ phase: Phase) -> RugbyMatchEventPageReaderHeader10868 {
        RugbyMatchEventPageReaderHeader10868(
            title: "Nice Try vs Flame Hard",
            state: phase == .final ? "Reported final · 13–1 rounds" : phase == .during ? "Constructed in-play frame" : "Before the match")
    }

    private static let storyLinks = [
        EsportsEventPageStory10868(cardID: "winner-card", card: .winner, reason: "Original pre-match expectations"),
        EsportsEventPageStory10868(cardID: "margin-card", card: .margin, reason: "The winning margin against the line"),
    ]

    private static func stream(winnerFirst: Bool = true) -> StoryStreamPresentation10868 {
        let scope = "esports:15322123:stories"
        let winnerCard = StoryStreamPresentation10868.Card(id: "winner-card", name: "Match winner")
        let marginCard = StoryStreamPresentation10868.Card(id: "margin-card", name: "Map 1 winning margin")
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Match stories",
            cards: winnerFirst ? [winnerCard, marginCard] : [marginCard, winnerCard],
            primary: StoryStreamPresentation10868.CardRef(scope: scope, id: winnerFirst ? "winner-card" : "margin-card"),
            companion: nil, companionLabel: nil, wide: false, position: "1 of 2", status: nil,
            dwellFraction: nil, playback: nil, previous: nil, next: nil, readerOpen: false)
    }

    private static func input(_ phase: Phase, history: FieldHistoryInput10868? = nil, headline: FieldHeadlineInput10868? = nil,
                              winner: EsportsWinnerStory10868? = nil, margin: EsportsMarginStory10868? = nil,
                              withoutWinner: Bool = false, withoutMargin: Bool = false, hostile: Bool = false,
                              stream: StoryStreamPresentation10868? = nil, stories: [EsportsEventPageStory10868]? = nil,
                              readerOrder: [Card]? = nil, readerHeight: CGFloat? = 302,
                              sources: [RugbyMatchEventPageSource10868]? = nil) -> EsportsEventPageInput10868 {
        EsportsEventPageInput10868(
            phase: phase, notice: notice(phase), headline: headline ?? Tests.headline(phase, hostileFinishes: hostile),
            reader: readerHeader(phase), history: history ?? Tests.history(phase), readerPlotHeight: readerHeight,
            winner: withoutWinner ? nil : (winner ?? Tests.winner(phase, hostile: hostile)),
            margin: withoutMargin ? nil : (margin ?? Tests.margin(phase, hostile: hostile)),
            stream: stream, stories: stories ?? storyLinks, readerOrder: readerOrder, about: about(phase),
            sources: sources ?? Tests.sources(phase), matchCopy: matchCopy, copy: pageCopy)
    }

    // MARK: - Reading helpers

    private static func spoken(_ slots: [FieldHistoryReadoutSlot10868]) -> [String] {
        slots.map(FieldHistoryGeometry10868.spokenSlot)
    }

    private static func storyTexts(_ input: EsportsEventPageInput10868, _ originals: RugbyMatchEventPageOriginals10868) -> [String] {
        let model = Model(input)
        var texts: [String] = []
        if let winner = model.winnerModel(originals) {
            texts += winner.sides.map { winner.spoken($0) }
            texts += winner.related.map { winner.spoken($0) }
            texts += [winner.reportCaption, winner.selectionWords].compactMap { $0 }
            for plan in winner.sides {
                texts += plan.readings.map(\.spoken)
                texts += [plan.report?.outcome, plan.report?.figure, plan.report?.unit, plan.settlement?.spoken].compactMap { $0 }
            }
        }
        if let margin = model.marginModel(originals) {
            texts += margin.roles.map(\.spoken)
            texts += [margin.delta, margin.score, margin.actualMarker, margin.selectionWords, margin.spokenGraphic].compactMap { $0 }
        }
        if let headline = model.headline {
            let leaf = FieldHeadlineModel10868(headline)
            texts += leaf.competitors.map(leaf.competitorSummary)
        }
        return texts
    }

    private static let finalOnly = ["13 rounds", "1 round", "Won match", "Lost match", "Won the match", "Lost the match",
                                    "12 actual", "12 rounds", "Contract result", "Prop result", "13–1", "Reported final",
                                    "5 beyond", "99.9%", "100%", "Lost"]

    private static func leaks(_ texts: [String], _ forbidden: [String]) -> [String] {
        texts.filter { text in forbidden.contains { text.contains($0) } }
    }

    // MARK: - Retained receipt

    func testTheRetainedBlendIsAll143AdmittedObservationsUnderTheSourceContract() {
        XCTAssertEqual(Self.blend.count, 143)
        let homeLines = Self.blend.map { "\($0.text) \($0.home)" }.joined(separator: "\n")
        XCTAssertEqual(Self.sha256(homeLines), Self.retainedBlendHomeSHA256, "the home column is the retained source text")
        XCTAssertTrue(zip(Self.blend, Self.blend.dropFirst()).allSatisfy { $0.at < $1.at }, "strictly increasing, no duplicate instant")
        XCTAssertTrue(Self.blend.allSatisfy { $0.at < Self.terminal }, "the terminal witness and anything later stay out")
        for observation in Self.blend {
            let home = Decimal(string: observation.home)!, away = Decimal(string: observation.away)!
            XCTAssertTrue(home > 0 && home < 1 && away > 0 && away < 1, "no manufactured 0% or 100% endpoint: \(observation.text)")
            XCTAssertEqual(home + away, 1, "the verified binary blend's own pair: \(observation.text)")
        }
        let before = Self.blend.filter { $0.at < Self.start }
        XCTAssertEqual(before.count, 102)
        XCTAssertEqual(Self.blend.count - before.count + 1, 42, "around the start: 41 after it plus the baseline")
        XCTAssertEqual([Self.baseline.text, Self.baseline.home, Self.baseline.away],
                       ["2026-10-01T16:12:00+00:00", "0.7875", "0.2125"])
        XCTAssertEqual([Self.blend.last!.text, Self.blend.last!.home, Self.blend.last!.away],
                       ["2026-10-01T17:40:00+00:00", "0.999", "0.001"])
        XCTAssertEqual([Self.percent(Self.baseline.home), Self.percent(Self.baseline.away)], ["78.8%", "21.3%"])
        XCTAssertEqual([Self.percent("0.999"), Self.percent("0.001")], ["99.9%", "0.1%"])
        let runs = Self.runs(Self.blend)
        XCTAssertEqual(runs.count, 71, "every gap longer than five minutes starts a new run")
        XCTAssertEqual(runs.map(\.count).reduce(0, +), 143)
        XCTAssertTrue(runs.allSatisfy { run in zip(run, run.dropFirst()).allSatisfy { $1.at - $0.at <= 300 } })
        XCTAssertTrue(zip(runs, runs.dropFirst()).allSatisfy { $1.first!.at - $0.last!.at > 300 })
    }

    func testTheRetainedOriginalsAndReportMatchTheirRawTuples() throws {
        XCTAssertEqual(Self.retainedOriginals.map(\.market), ["63664403", "63403921", "63403921", "63403921"])
        XCTAssertEqual(Self.retainedOriginals.map(\.outcomeID), ["239843452", "239325962", "239325963", "239843454"])
        XCTAssertEqual(Set(Self.retainedOriginals.map { Self.identity($0) }).count, 4, "four distinct exact identities")
        XCTAssertEqual(Self.retainedOriginals.map(\.category), ["spreads", "other", "other", "other"])
        XCTAssertEqual(Self.retainedOriginals.map(\.isWinner), [nil, nil, false, nil])
        XCTAssertEqual(Self.flameHardRow.resolutionSource, "api_settlement")
        XCTAssertNil(Self.niceTryRow.resolutionSource, "the reported winner's own contract is not settled by the scoreboard")
        let niceTry = Self.quotes(Self.retainedNiceTryWinner)
        XCTAssertEqual(niceTry.count, 4)
        let niceTryPre = try XCTUnwrap(Self.preMatch(Self.niceTryRow))
        XCTAssertEqual([niceTryPre.text, niceTryPre.probability], ["2026-10-01T14:42:43.437760+00:00", "0.765"])
        XCTAssertEqual(niceTry[2].probability, niceTry[3].probability, "an equal value at an earlier observation keeps its own date")
        XCTAssertNotEqual(niceTry[2].text, niceTry[3].text)
        let flame = Self.quotes(Self.retainedFlameHard)
        XCTAssertEqual(flame.count, 106)
        XCTAssertEqual(flame.filter { $0.at < Self.start }.count, 83)
        let flamePre = try XCTUnwrap(Self.preMatch(Self.flameHardRow))
        XCTAssertEqual([flamePre.text, flamePre.probability], ["2026-10-01T16:14:06.135805+00:00", "0.22"])
        let flameLive = try XCTUnwrap(Self.inPlay(Self.flameHardRow))
        XCTAssertEqual([flameLive.text, flameLive.probability], ["2026-10-01T16:42:06.186233+00:00", "0.215"])
        XCTAssertEqual(flame.filter { $0.at >= Self.start && $0.at <= Self.constructedLiveCut }.count, 7)
        XCTAssertNil(Self.preMatch(Self.marginRow), "the margin prop has no pre-match observation")
        XCTAssertNil(Self.preMatch(Self.handicapRow), "the nested handicap has no pre-match observation")
        XCTAssertEqual([Self.percent(niceTryPre.probability), Self.percent(flamePre.probability)], ["76.5%", "22%"])
        XCTAssertEqual(Self.handicapRow.outcomeName, Self.marginRow.marketName, "the nested handicap names the margin market's line")
        XCTAssertNotEqual(Self.identity(Self.handicapRow), Self.identity(Self.marginRow), "…but keeps its own identity")
        XCTAssertEqual(Self.retainedDetailHashes.count, 2)
        // The report: rounds, not maps; provider order is Flame Hard first.
        let report = Self.retainedReport
        let niceTryIndex = try XCTUnwrap(report.providerOrder.firstIndex(of: "Nice Try"))
        let flameIndex = try XCTUnwrap(report.providerOrder.firstIndex(of: "Flame Hard"))
        XCTAssertEqual([report.roundsWon[niceTryIndex], report.roundsWon[flameIndex]], [13, 1])
        XCTAssertEqual([report.mapsWon[niceTryIndex], report.mapsWon[flameIndex]], [1, 0])
        XCTAssertEqual([report.mapNumber, report.roundsWon[niceTryIndex] - report.roundsWon[flameIndex]], [1, 12],
                       "the owner's actual margin agrees with the separately reported rounds")
        XCTAssertNil(report.actualStartAt)
        XCTAssertNil(report.completedAt)
        XCTAssertEqual([report.status, report.publisher, report.mapName], ["finished", "Scores24", "Dust2"])
    }

    // MARK: - History

    func testTheHistoryDrawsTwoSolidSeriesWithShapeIdentityHollowBeforeAndFilledAfter() throws {
        let page = Page(input: Self.input(.final))
        let history = page.historyContent(reader: false).input
        XCTAssertEqual(history.series.map(\.name), ["Nice Try", "Flame Hard"])
        XCTAssertEqual(history.series.map(\.shape), [.circle, .diamond])
        XCTAssertEqual(history.series.map { $0.runs.count }, [71, 71])
        XCTAssertEqual(history.series.map { $0.runs.flatMap(\.points).count }, [143, 143])
        for series in history.series {
            for point in series.runs.flatMap(\.points) {
                XCTAssertEqual(point.style, point.x < Double(Self.start) ? .hollow : .filled)
            }
        }
        XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.hollow, in: history))
        XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.filled, in: history))
        XCTAssertEqual([history.markKey.hollow, history.markKey.filled], ["Hollow: pre-match", "Filled: after start"])
        XCTAssertEqual(history.domain.upper, Double(Self.blend.last!.at), "no extension to the terminal witness or a 100% end")
        XCTAssertEqual(history.guides.map(\.label), ["Start"])
        // Before the match only hollow marks are drawn, so only that key shows.
        let before = Page(input: Self.input(.before)).historyContent(reader: false).input
        XCTAssertTrue(FieldHistoryGeometry10868.drawsStyle(.hollow, in: before))
        XCTAssertFalse(FieldHistoryGeometry10868.drawsStyle(.filled, in: before))
        XCTAssertEqual(before.guides, [], "the start lies outside the before-match domain")
        XCTAssertEqual(before.series.map { $0.runs.flatMap(\.points).count }, [102, 102])
        let during = Page(input: Self.input(.during)).historyContent(reader: false).input
        XCTAssertEqual(during.series.map { $0.runs.flatMap(\.points).count }, [117, 117])
        XCTAssertEqual(during.domain.upper, Double(Self.constructedLiveCut))
    }

    func testTheFullHistoryIsTheSameInputAtAnEqualOrTallerFiniteHeight() {
        let page = Page(input: Self.input(.final), mode: .reader(.history))
        let inline = Page(input: Self.input(.final)).historyContent(reader: false).input
        let full = page.historyContent(reader: true).input
        XCTAssertEqual(full.series, inline.series)
        XCTAssertEqual(full.inspection, inline.inspection)
        XCTAssertEqual(full.xTicks, inline.xTicks, "the owner's readable calendar labels are unchanged")
        XCTAssertEqual(full.previous, inline.previous)
        XCTAssertEqual(full.next, inline.next)
        XCTAssertNil(full.expand, "full size has no expand control")
        XCTAssertEqual([inline.plotHeight, full.plotHeight], [240, 302])
        for owner: CGFloat? in [nil, 0, -10, .infinity, .nan, 120] {
            let shorter = Page(input: Self.input(.final, readerHeight: owner)).historyContent(reader: true).input
            XCTAssertEqual(shorter.plotHeight, 240, "an unusable or shorter owner height keeps the inline height")
        }
        XCTAssertEqual(Model(Self.input(.final, readerHeight: 390)).readerHistory.plotHeight, 390)
    }

    // MARK: - Headline and comparison

    func testBothNamedChancesLeadWithTheirOwnRolesAndDatesInEveryPhase() throws {
        for phase in Phase.allCases {
            let headline = try XCTUnwrap(Model(Self.input(phase)).headline, "\(phase)")
            let leaf = FieldHeadlineModel10868(headline)
            XCTAssertEqual(leaf.competitors.map(\.slot.name), ["Nice Try", "Flame Hard"])
            XCTAssertEqual(leaf.competitors.map(leaf.keyShape), [.circle, .diamond])
            XCTAssertEqual(leaf.keyIsHollow, phase == .before)
            let figures = leaf.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }
            let details = leaf.competitors.map { $0.metrics.compactMap(FieldChaseModel10868.detail) }
            switch phase {
            case .before:
                XCTAssertEqual(figures, [["78.8%"], ["21.3%"]])
            case .during:
                XCTAssertEqual(figures, [["78.8%", "79.8%"], ["21.3%", "20.3%"]])
                XCTAssertEqual(details[0], ["Oct 1, 16:12 UTC · Bain Luck blend", "Oct 1, 16:45 UTC · Bain Luck blend"])
            case .final:
                XCTAssertEqual(figures, [["78.8%", "13 rounds"], ["21.3%", "1 round"]])
                XCTAssertEqual(leaf.competitors.map { $0.metrics.map(FieldChaseModel10868.label) },
                               [["Last pre-match", "Reported result"], ["Last pre-match", "Reported result"]])
            }
        }
        // A headline from another phase is not coerced.
        let mismatched = Self.input(.final, headline: Self.headline(.final, leaf: .during))
        XCTAssertNil(Model(mismatched).headline)
        XCTAssertNil(Page(input: mismatched).headlineContent())
    }

    func testTheComparisonShowsEqualScaledFiguresWithTheirOwnDatesInlineAndFullSize() {
        XCTAssertEqual(RugbyMatchEventPageModel10868.comparisonFigureSize, 26)
        let input = Self.input(.final)
        let inline = Page(input: input).comparisonContent(reader: false)
        let full = Page(input: input, mode: .reader(.history)).comparisonContent(reader: true)
        XCTAssertEqual(inline.label, "Pre-match and recorded chances")
        let expected = [
            ["Last pre-match 78.8%, Oct 1, 16:12 UTC · blend", "Recorded after start 99.9%, Oct 1, 17:40 UTC · blend"],
            ["Last pre-match 21.3%, Oct 1, 16:12 UTC · blend", "Recorded after start 0.1%, Oct 1, 17:40 UTC · blend"],
        ]
        XCTAssertEqual(inline.entries.map { Self.spoken($0.slots) }, expected)
        XCTAssertEqual(full.entries.map { Self.spoken($0.slots) }, expected, "the same readouts full size")
        XCTAssertEqual(inline.history, Model(input).presentedHistory, "it reads the exact copy the anchor draws")
        XCTAssertEqual(full.history, Model(input).readerHistory)
    }

    func testTheBaselineItselfCollapsesTheDuplicatePairWhileEqualValuesKeepTheirDates() throws {
        // Inspecting the baseline observation itself: one pre-match slot.
        let atBaseline = Self.input(.final, history: Self.history(.final, inspecting: Self.baseline.at))
        XCTAssertTrue(Model.collapsesBaseline(atBaseline.history))
        XCTAssertEqual(Model(atBaseline).presentedHistory.readout, .singleBefore(label: "Last pre-match"))
        let collapsed = Page(input: atBaseline).comparisonContent(reader: false)
        XCTAssertEqual(collapsed.entries.map { Self.spoken($0.slots) },
                       [["Last pre-match 78.8%, Oct 1, 16:12 UTC · blend"], ["Last pre-match 21.3%, Oct 1, 16:12 UTC · blend"]])
        XCTAssertEqual(atBaseline.history.readout, .beforeAndInspected(beforeLabel: "Last pre-match", inspectedLabel: "Inspected pre-match"),
                       "the owner's input is never changed")
        // The same 78.75% at a different observation keeps both slots and dates.
        for twin in ["2026-10-01T15:13:00+00:00", "2026-10-01T16:17:00+00:00"] {
            let at = Self.epoch(twin)
            XCTAssertEqual(Self.blend.first { $0.at == at }?.home, "0.7875")
            let input = Self.input(.final, history: Self.history(.final, inspecting: at))
            XCTAssertFalse(Model.collapsesBaseline(input.history), twin)
            let slots = Page(input: input).comparisonContent(reader: false).entries[0].slots
            XCTAssertEqual(slots.count, 2)
            XCTAssertEqual(Self.spoken(slots)[1],
                           (at < Self.start ? "Inspected pre-match" : "Recorded after start") + " 78.8%, \(Self.clock(at)) · blend")
        }
    }

    func testAnOmittedChangedDuplicatedOrForeignObservationStaysUnavailableUntilTheExactOneReturns() throws {
        let inspected = Self.epoch("2026-10-01T16:30:00+00:00")
        let ids = Self.teams.map { Self.pointID($0, inspected) }
        // Omitted from this arrival: the held id names no point.
        let omitted = Self.blend.filter { $0.at != inspected }
        var input = Self.input(.final, history: Self.history(.final, inspecting: inspected, observations: omitted,
                                                             selections: [Self.niceTry.seriesID: .point(id: ids[0], spoken: "80%"),
                                                                          Self.flameHard.seriesID: .point(id: ids[1], spoken: "20%")]))
        var slots = Page(input: input).comparisonContent(reader: false).entries.map { Self.spoken($0.slots)[1] }
        XCTAssertEqual(slots, ["Recorded after start: Not bound to this observation", "Recorded after start: Not bound to this observation"])
        XCTAssertFalse(Model.collapsesBaseline(input.history))
        // Foreign: the selection is keyed to another original.
        input = Self.input(.final, history: Self.history(.final, inspecting: inspected,
                                                         selections: ["foreign": .point(id: ids[0], spoken: "80%")]))
        slots = Page(input: input).comparisonContent(reader: false).entries.map { Self.spoken($0.slots)[1] }
        XCTAssertEqual(slots, ["Recorded after start: Not bound to this observation", "Recorded after start: Not bound to this observation"])
        // Duplicated: the same id twice in one series binds nothing.
        var duplicated = Self.history(.final, inspecting: inspected)
        let series = duplicated.series.map { series -> FieldHistorySeries10868 in
            let copy = series.runs.flatMap(\.points).first { $0.id.hasSuffix("@\(inspected)") }!
            return FieldHistorySeries10868(id: series.id, name: series.name, shape: series.shape, tint: series.tint,
                                           runs: series.runs + [FieldHistoryRun10868(id: "dup", points: [copy])], links: [],
                                           labelPointID: nil, before: series.before, recorded: series.recorded,
                                           absentWords: nil, choose: nil)
        }
        duplicated = Model.baselineCopy(FieldHistoryInput10868(
            title: duplicated.title, caption: duplicated.caption, series: series, selection: duplicated.selection,
            domain: duplicated.domain, ceiling: duplicated.ceiling, yTicks: duplicated.yTicks, xTicks: duplicated.xTicks,
            guides: duplicated.guides, breaks: duplicated.breaks, readout: duplicated.readout, markKey: duplicated.markKey,
            comparisonExplanation: nil, notes: duplicated.notes, summary: duplicated.summary, plotHeight: 240,
            unboundReadingWords: duplicated.unboundReadingWords, plotUnavailableWords: nil, windows: nil, scale: nil,
            moreOriginals: nil, details: nil, expand: duplicated.expand, inspect: nil, previous: duplicated.previous,
            next: duplicated.next, inspection: duplicated.inspection))
        slots = Page(input: Self.input(.final, history: duplicated)).comparisonContent(reader: false).entries.map { Self.spoken($0.slots)[1] }
        XCTAssertEqual(slots, ["Recorded after start: Not bound to this observation", "Recorded after start: Not bound to this observation"])
        // Wrong original selected: the owner's words, never a neighbour.
        let wrong = Self.input(.final, history: Self.history(.final, selection: .series(id: "blend:other-event", missingWords: "Not in this match")))
        XCTAssertEqual(FieldHistoryGeometry10868.selectionWords(Model(wrong).presentedHistory), "Not in this match")
        // The exact observation returns: its own figure again.
        input = Self.input(.final, history: Self.history(.final, inspecting: inspected))
        slots = Page(input: input).comparisonContent(reader: false).entries.map { Self.spoken($0.slots)[1] }
        XCTAssertEqual(slots, ["Recorded after start 80%, Oct 1, 16:30 UTC · blend", "Recorded after start 20%, Oct 1, 16:30 UTC · blend"])
    }

    func testAMissingBaselineStaysUnavailableAndNeverCollapses() {
        let history = Self.history(.final, inspecting: Self.baseline.at,
                                   before: [Self.niceTry.seriesID: .absent(words: "No pre-match chance recorded")])
        let input = Self.input(.final, history: history)
        XCTAssertFalse(Model.collapsesBaseline(history), "a missing baseline is never the inspected observation")
        let first = Page(input: input).comparisonContent(reader: false).entries[0]
        XCTAssertEqual(Self.spoken(first.slots), ["Last pre-match: No pre-match chance recorded",
                                                   "Inspected pre-match 78.8%, Oct 1, 16:12 UTC · blend"])
    }

    // MARK: - Winner story

    func testTheWinnerStoryShowsEachOriginalPreMatchRingWithItsOwnDateBesideItsSeparateResult() throws {
        let model = try XCTUnwrap(Model(Self.input(.final)).winnerModel(Self.originals(.final)))
        let sides = model.sides
        XCTAssertEqual(sides.map(\.side.name), ["Nice Try", "Flame Hard"])
        XCTAssertEqual(sides.map(\.ring), [0.765, 0.22], "each ring is that original's own pre-match placement")
        XCTAssertEqual(sides.map { $0.readings.map(\.role) }, [[.before], [.before]])
        XCTAssertEqual(sides.map { $0.readings.first?.label }, ["Pre-match chance", "Pre-match chance"])
        XCTAssertEqual(sides.map { $0.readings.first?.text }, ["76.5%", "22%"])
        XCTAssertEqual(sides.map { $0.readings.first?.provenance },
                       ["Oct 1, 14:42:43 UTC · Polymarket", "Oct 1, 16:14:06 UTC · Polymarket"], "independent dates")
        XCTAssertEqual(sides.map { $0.report?.outcome }, ["Won match", "Lost match"])
        XCTAssertEqual(sides.map { $0.report?.figure }, ["13", "1"])
        XCTAssertEqual(sides.map { $0.report?.unit }, ["rounds", "round"], "rounds, never maps")
        XCTAssertEqual(sides.map { $0.settlement?.text }, ["Not confirmed", "Lost"])
        XCTAssertEqual(sides.map { $0.settlement?.isValue }, [false, true])
        XCTAssertEqual(model.reportCaption, "Reported final · Map 1 Dust2 · Scores24")
        XCTAssertEqual(model.copy.explanation, Self.explanation, "the visible words on why originals differ from the blend")
        XCTAssertEqual(model.spoken(sides[0]),
                       "Nice Try. Pre-match chance, 76.5%, Oct 1, 14:42:43 UTC · Polymarket. Won match 13 rounds. Contract result, Not confirmed")
        // Original sides are never complemented: 76.5% and 22% stay 98.5%.
        XCTAssertEqual(sides.compactMap(\.ring).reduce(0, +), 0.985, accuracy: 1e-12)
    }

    func testTheReportedResultNeverOverwritesAProbabilityOrAContractSettlement() throws {
        let originals = Self.originals(.final)
        let model = try XCTUnwrap(Model(Self.input(.final)).winnerModel(originals))
        XCTAssertEqual(model.sides[0].ring, 0.765, "the reported winner's ring keeps its pre-match chance, never certainty")
        let content = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: Self.selection(Self.niceTryRow)))
        XCTAssertNil(content.result, "a null original is_winner does not become a winner because the scoreboard reports one")
        // A hostile report on the losing side changes neither its settlement nor its ring.
        let hostileSides = [Self.side(Self.niceTryRow, Self.niceTry, report: true),
                            EsportsWinnerSide10868(selection: Self.selection(Self.flameHardRow), name: "Flame Hard", tint: .orange,
                                                   report: EsportsSideReport10868(outcome: "Won match", figure: "13", unit: "rounds"))]
        let hostile = try XCTUnwrap(Model(Self.input(.final, winner: Self.winner(.final, sides: hostileSides))).winnerModel(originals))
        XCTAssertEqual(hostile.sides[1].settlement?.text, "Lost", "the contract's own grade, not the report")
        XCTAssertEqual(hostile.sides[1].ring, 0.22)
        // The headline's blend is never copied into an original.
        XCTAssertFalse(model.sides.contains { $0.readings.contains { $0.text == "78.8%" || $0.text == "21.3%" } })
    }

    func testAllFourOriginalsKeepExactIdentitiesPredicatesSourceAndRulesThroughCardAndDetails() throws {
        var log: [Details.Selection] = []
        let originals = Self.originals(.final)
        let page = Page(input: Self.input(.final), originals: originals, onOriginalSelect: { log.append($0) },
                        onOriginalDetails: { log.append($0) })
        let winner = try XCTUnwrap(page.pageWinnerContent())
        for plan in winner.model.sides {
            EsportsWinnerModel10868.choice(plan.side.selection, resolves: plan.resolves, onSelect: winner.onSelect)?()
        }
        for row in winner.model.related {
            EsportsWinnerModel10868.choice(row.related.selection, resolves: row.content != nil, onSelect: winner.onSelect)?()
        }
        let margin = try XCTUnwrap(page.pageMarginContent())
        margin.model.choice(margin.onSelect)?()
        XCTAssertEqual(log, [Self.selection(Self.niceTryRow), Self.selection(Self.flameHardRow),
                             Self.selection(Self.handicapRow), Self.selection(Self.marginRow)])
        XCTAssertEqual(Set(log.map(\.identity)).count, 4)
        // Each handed-back selection opens exactly its own Details.
        for (row, held) in zip([Self.niceTryRow, Self.flameHardRow, Self.handicapRow, Self.marginRow], log) {
            let content = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: held))
            XCTAssertEqual(content.title, row.marketName)
            XCTAssertEqual(content.outcome, row.outcomeName, "the full predicate, verbatim")
            XCTAssertEqual(content.rules, .unavailable(Self.rulesWords), "no rules text was retained; none is invented")
            XCTAssertTrue(content.about.contains { $0.label == "Source" && $0.value == "Polymarket" })
            XCTAssertTrue(content.about.contains { $0.label == "Outcome id" && $0.value == row.outcomeID })
            XCTAssertTrue(content.about.contains { $0.label == "Retained key" && $0.value == row.key })
        }
        XCTAssertEqual(winner.model.related.first?.content?.outcome, Self.handicapMarketName, "the nested handicap is reachable")
        XCTAssertEqual(winner.model.related.first?.readings.first?.text, "No pre-match chance recorded")
        // Card → Details round trip with the held selection, then the Details mode.
        log.removeAll()
        let held = Page(input: Self.input(.final), originals: Self.originals(.final, selection: Self.selection(Self.handicapRow)),
                        onOriginalDetails: { log.append($0) })
        let card = try XCTUnwrap(held.pageWinnerContent())
        card.model.detailsAction(card.onDetails)?()
        XCTAssertEqual(log, [Self.selection(Self.handicapRow)])
        let details = try XCTUnwrap(Page(input: Self.input(.final), mode: .original,
                                         originals: Self.originals(.final, selection: log[0])).match(.original).originalDetailsContent())
        XCTAssertEqual(details.selection, Self.selection(Self.handicapRow))
        // The catalogue mode reaches all four.
        let catalogue = try XCTUnwrap(Page(input: Self.input(.final), mode: .catalogue, originals: originals).match(.catalogue).catalogueContent())
        XCTAssertEqual(catalogue.catalogue?.originals.map(\.identity), Self.retainedOriginals.map { Self.identity($0) })
    }

    func testUnknownForeignDuplicateOrWithdrawnSelectionsBorrowNoNeighbour() throws {
        let foreign = Self.selection(Self.niceTryRow, scope: "polymarket|other-event|originals")
        let unknown = Details.Selection(scope: Self.originalsScope,
                                        identity: Details.Identity(source: "polymarket", market: "63403921", side: "999"))
        for odd in [foreign, unknown] {
            let sides = [EsportsWinnerSide10868(selection: odd, name: "Nice Try", tint: .blue),
                         Self.side(Self.flameHardRow, Self.flameHard, report: true)]
            let model = try XCTUnwrap(Model(Self.input(.final, winner: Self.winner(.final, sides: sides))).winnerModel(Self.originals(.final)))
            XCTAssertFalse(model.sides[0].resolves)
            XCTAssertEqual(model.sides[0].readings, [])
            XCTAssertNil(model.sides[0].ring)
            XCTAssertNil(model.sides[0].report)
            XCTAssertNil(EsportsWinnerModel10868.choice(odd, resolves: model.sides[0].resolves, onSelect: { _ in XCTFail() }))
            XCTAssertEqual(model.spoken(model.sides[0]), "Nice Try. Not in this update")
            XCTAssertEqual(model.sides[1].ring, 0.22, "the neighbour keeps only its own reading")
        }
        // Withdrawn from this arrival.
        let withdrawn = Self.originals(.final, selection: Self.selection(Self.niceTryRow),
                                       list: Self.retainedOriginals.filter { $0.outcomeID != Self.niceTryRow.outcomeID }.map { Self.original($0, .final) })
        let model = try XCTUnwrap(Model(Self.input(.final)).winnerModel(withdrawn))
        XCTAssertFalse(model.sides[0].resolves)
        XCTAssertEqual(model.selectionWords, "The selected outcome is not in this update")
        XCTAssertFalse(model.sides.contains(where: \.isSelected), "nothing else is marked in its place")
        XCTAssertNil(model.heldSelection)
        XCTAssertTrue(Model.heldOriginalIsUnavailable(withdrawn))
        // Duplicated in the catalogue.
        let doubled = Self.originals(.final, list: Self.retainedOriginals.map { Self.original($0, .final) } + [Self.original(Self.niceTryRow, .final)])
        XCTAssertFalse(try XCTUnwrap(Model(Self.input(.final)).winnerModel(doubled)).sides[0].resolves)
        // Repeated on the card.
        let repeated = [Self.side(Self.niceTryRow, Self.niceTry, report: true), Self.side(Self.niceTryRow, Self.niceTry, report: true)]
        let twice = try XCTUnwrap(Model(Self.input(.final, winner: Self.winner(.final, sides: repeated))).winnerModel(Self.originals(.final)))
        XCTAssertEqual(twice.sides.map(\.resolves), [false, false])
        // The exact identity returns: selected again.
        let restored = try XCTUnwrap(Model(Self.input(.final)).winnerModel(Self.originals(.final, selection: Self.selection(Self.niceTryRow))))
        XCTAssertEqual(restored.sides.map(\.isSelected), [true, false])
        XCTAssertNil(restored.selectionWords)
        XCTAssertFalse(Model.heldOriginalIsUnavailable(Self.originals(.final, selection: Self.selection(Self.niceTryRow))))
    }

    // MARK: - Margin story

    func testTheMarginStoryShowsActualBlocksAgainstTheMinimumWithExplicitRoles() throws {
        let model = try XCTUnwrap(Model(Self.input(.final)).marginModel(Self.originals(.final)))
        XCTAssertTrue(model.resolves)
        XCTAssertEqual(model.content?.outcome, "Nice Try")
        XCTAssertEqual(model.content?.title, Self.handicapMarketName)
        XCTAssertEqual(model.blocks.count, 14)
        XCTAssertEqual(model.blocks.filter(\.isFilled).count, 12)
        XCTAssertEqual(model.blocks.filter(\.meetsMinimum).map(\.index), Array(7..<14))
        XCTAssertEqual(model.blocks.map(\.index), Array(0..<14), "one block per round of margin, not a timeline")
        XCTAssertEqual(model.minimumFraction, 0.5)
        XCTAssertEqual(try XCTUnwrap(model.actualFraction), 12.0 / 14.0, accuracy: 1e-12)
        XCTAssertEqual(model.roles.map(\.role), [.before, .later, .actual, .result])
        XCTAssertEqual(model.roles.map(\.spoken), [
            "Pre-match chance, No pre-match chance recorded",
            "Recorded chance, No recent probability update",
            "Actual winning margin, 12 rounds, Reported by Scores24",
            "Prop result, Prop result unconfirmed, The reported score clears the required margin. The prop's own settlement has not been confirmed.",
        ])
        XCTAssertEqual(model.actual, .reported(figure: "12", unit: "rounds"))
        XCTAssertEqual([model.delta, model.score, model.actualMarker],
                       ["7 needed · 5 beyond the minimum", "Nice Try 13–1 Flame Hard · Dust2", "12 actual"])
        XCTAssertFalse(model.isOffScale)
        XCTAssertTrue(model.spokenGraphic.contains("not the order rounds were played"))
        let rect = CGRect(x: 0, y: 0, width: 280, height: 26)
        let widths = (0..<14).compactMap { EsportsMarginGeometry10868.blockRect($0, count: 14, in: rect, gap: 3)?.width }
        XCTAssertEqual(Set(widths).count, 1, "every block is the same unit")
        XCTAssertNil(EsportsMarginGeometry10868.blockRect(14, count: 14, in: rect, gap: 3))
    }

    func testTheMarginTakesOnlyTheOwnersNumbersAndNeverParsesTheLine() throws {
        let originals = Self.originals(.final)
        // The owner's actual, even when it disagrees with the reported words.
        let nine = try XCTUnwrap(Model(Self.input(.final, margin: Self.margin(.final, actual: 9))).marginModel(originals))
        XCTAssertEqual(nine.blocks.filter(\.isFilled).count, 9, "nothing is derived from the score or the line")
        // Off the owner's scale: words, no fill, no marker.
        let off = try XCTUnwrap(Model(Self.input(.final, margin: Self.margin(.final, actual: 15))).marginModel(originals))
        XCTAssertTrue(off.isOffScale)
        XCTAssertEqual(off.blocks.filter(\.isFilled).count, 0)
        XCTAssertNil(off.actualFraction)
        XCTAssertEqual(off.actual, .unavailable("Actual margin not reported"))
        XCTAssertNil(off.delta)
        // An unusable scale draws nothing.
        for (blocks, minimum) in [(0, 0), (14, 20), (14, -1)] {
            let bad = try XCTUnwrap(Model(Self.input(.final, margin: Self.margin(.final, blocks: blocks, minimum: minimum))).marginModel(originals))
            XCTAssertTrue(bad.isOffScale)
            XCTAssertEqual(bad.blocks, [])
            XCTAssertNil(bad.minimumFraction)
        }
        // A missing actual figure or value stays unavailable.
        let noFigure = try XCTUnwrap(Model(Self.input(.final, margin: Self.margin(.final, actualFigure: nil))).marginModel(originals))
        XCTAssertEqual(noFigure.actual, .unavailable("Actual margin not reported"))
        let noValue = try XCTUnwrap(Model(Self.input(.final, margin: Self.margin(.final, actual: nil))).marginModel(originals))
        XCTAssertEqual(noValue.actual, .unavailable("Actual margin not reported"))
        XCTAssertEqual(noValue.blocks.filter(\.isFilled).count, 0)
        // The original does not resolve: the owner's words only.
        let gone = Self.originals(.final, list: Self.retainedOriginals.filter { $0.market != Self.marginRow.market }.map { Self.original($0, .final) })
        let missing = try XCTUnwrap(Model(Self.input(.final)).marginModel(gone))
        XCTAssertFalse(missing.resolves)
        XCTAssertEqual(missing.readings, [])
        XCTAssertNil(missing.result)
        XCTAssertNil(missing.choice { _ in XCTFail() })
    }

    // MARK: - Phases

    func testEachPhaseShowsOnlyItsAdmittedStoryParts() throws {
        for phase in [Phase.before, .during] {
            let input = Self.input(phase)
            let originals = Self.originals(phase)
            let winner = try XCTUnwrap(Model(input).winnerModel(originals))
            XCTAssertTrue(winner.sides.allSatisfy { $0.report == nil && $0.settlement == nil }, "\(phase)")
            XCTAssertNil(winner.reportCaption)
            let margin = try XCTUnwrap(Model(input).marginModel(originals))
            XCTAssertNil(margin.actual)
            XCTAssertNil(margin.result)
            XCTAssertNil(margin.actualFraction)
            XCTAssertEqual(margin.blocks.filter(\.isFilled).count, 0)
            XCTAssertEqual(Self.leaks(Self.storyTexts(input, originals), Self.finalOnly), [], "\(phase)")
        }
        let during = try XCTUnwrap(Model(Self.input(.during)).winnerModel(Self.originals(.during)))
        XCTAssertEqual(during.sides.map { $0.readings.map(\.spoken) }, [
            ["Pre-match chance, 76.5%, Oct 1, 14:42:43 UTC · Polymarket", "Recorded chance, No in-play observation recorded"],
            ["Pre-match chance, 22%, Oct 1, 16:14:06 UTC · Polymarket", "Recorded chance, 21.5%, Oct 1, 16:42:06 UTC · Polymarket"],
        ])
        let before = try XCTUnwrap(Model(Self.input(.before)).winnerModel(Self.originals(.before)))
        XCTAssertEqual(before.sides.map { $0.readings.count }, [1, 1])
        let final = try XCTUnwrap(Model(Self.input(.final)).marginModel(Self.originals(.final)))
        XCTAssertNotNil(final.actual)
    }

    func testHostileLaterFactsHandedToAnEarlierPhaseStayHidden() throws {
        for phase in [Phase.before, .during] {
            let input = Self.input(phase, hostile: true)
            let originals = Self.originals(phase, hostile: true)
            XCTAssertNotNil(input.winner?.sides.first?.report, "control: the hostile input does carry a report")
            XCTAssertNotNil(input.margin?.scale.actual, "control: the hostile input does carry an actual")
            let winner = try XCTUnwrap(Model(input).winnerModel(originals))
            XCTAssertTrue(winner.sides.allSatisfy { $0.report == nil && $0.settlement == nil })
            XCTAssertTrue(winner.sides.allSatisfy { $0.readings.count <= (phase == .before ? 1 : 2) })
            let margin = try XCTUnwrap(Model(input).marginModel(originals))
            XCTAssertNil(margin.actual)
            XCTAssertNil(margin.result)
            XCTAssertNil(margin.delta)
            XCTAssertEqual(margin.blocks.filter(\.isFilled).count, 0)
            let headline = FieldHeadlineModel10868(try XCTUnwrap(Model(input).headline))
            XCTAssertFalse(headline.competitors.contains { $0.metrics.contains { FieldChaseModel10868.figure($0) == "13 rounds" } })
            XCTAssertEqual(Self.leaks(Self.storyTexts(input, originals), Self.finalOnly), [], "\(phase)")
        }
    }

    func testThePhaseLeakGuardCatchesTheLeakItWasWrittenFor() throws {
        let final = Self.input(.final)
        XCTAssertFalse(Self.leaks(Self.storyTexts(final, Self.originals(.final)), Self.finalOnly).isEmpty,
                       "positive control: the final surfaces do carry the final facts")
    }

    func testConstructedFramesAreLabelledAndNeverStandInForGenuineCoverage() {
        XCTAssertEqual(Self.input(.before).notice, "Constructed before-match frame from retained history · not a live capture")
        XCTAssertTrue(Self.input(.during).notice?.hasPrefix("Constructed in-play frame") ?? false)
        XCTAssertNil(Self.input(.final).notice, "only the retained final is genuine evidence")
        XCTAssertEqual(Self.admitted(.during).last?.at, Self.constructedLiveCut, "the in-play frame stops at the constructed cut")
        XCTAssertEqual(Model(Self.input(.during)).match.notice, Self.input(.during).notice, "the accepted page shows it unchanged")
    }

    // MARK: - Holds and callbacks

    func testEveryPageActionHoldsOnceThenHandsBackItsExactValue() throws {
        var log: [String] = []
        let originals = Self.originals(.final, selection: Self.selection(Self.niceTryRow))
        let page = Page(input: Self.input(.final), originals: originals,
                        onAbout: { log.append("about") }, onSource: { log.append("source:\($0)") },
                        onCatalogue: { log.append("catalogue") },
                        onOriginalSelect: { log.append("select:\($0.identity.side)") },
                        onOriginalDetails: { log.append("details:\($0.identity.side)") },
                        onHeadlineOpen: { log.append("open:\($0.ref.outcomeID)") },
                        onHistoryAction: { log.append("history:\($0)") },
                        onHistoryInspectionChoice: { log.append("choice:\($0)") },
                        onHistoryPlotPosition: { log.append("position:\($0)") },
                        onCardOpen: { log.append("card:\($0.rawValue)") },
                        onReaderIntent: { _ in log.append("reader") },
                        onInteraction: { log.append("hold") })
        let winner = try XCTUnwrap(page.pageWinnerContent())
        let margin = try XCTUnwrap(page.pageMarginContent())
        _ = (page.headlineContent(), page.historyContent(reader: false), page.chooserContent(), page.catalogueAction)
        XCTAssertEqual(log, [], "building and reading the page calls nothing")
        page.headlineContent()?.onAbout?()
        page.historyContent(reader: false).onAction?("history.expand")
        page.historyContent(reader: false).onPlotPosition?(42)
        winner.onExpand?()
        EsportsWinnerModel10868.choice(winner.model.sides[1].side.selection, resolves: true, onSelect: winner.onSelect)?()
        winner.model.detailsAction(winner.onDetails)?()
        winner.onSource?()
        margin.model.choice(margin.onSelect)?()
        margin.onExpand?()
        page.chooserContent()?.onSelect?(Self.selection(Self.marginRow))
        page.catalogueAction?()
        XCTAssertEqual(log, ["hold", "about", "hold", "history:history.expand", "hold", "position:42.0",
                             "hold", "card:winner", "hold", "select:239325963", "hold", "details:239325962",
                             "hold", "source:polymarket-sources", "hold", "select:239843452", "hold", "card:margin",
                             "hold", "select:239843452", "hold", "catalogue"])
    }

    func testFullSizeContentAndInfoKeepTheExactCallbacksWithNoHold() throws {
        var log: [String] = []
        let originals = Self.originals(.final, selection: Self.selection(Self.marginRow))
        func page(_ mode: EsportsEventPageMode10868) -> Page {
            Page(input: Self.input(.final), mode: mode, originals: originals,
                 onAbout: { log.append("about") }, onSource: { log.append("source:\($0)") },
                 onOriginalSelect: { log.append("select:\($0.identity.side)") },
                 onOriginalDetails: { log.append("details:\($0.identity.side)") },
                 onOriginalHistory: { _ in log.append("originalHistory") },
                 onHistoryAction: { log.append("history:\($0)") },
                 onReaderIntent: { log.append("reader:\($0)") },
                 onInteraction: { log.append("hold") })
        }
        let winner = try XCTUnwrap(page(.reader(.winner)).readerWinnerContent())
        XCTAssertNil(winner.onExpand, "full size has no expand")
        EsportsWinnerModel10868.choice(winner.model.sides[0].side.selection, resolves: true, onSelect: winner.onSelect)?()
        winner.onSource?()
        let margin = try XCTUnwrap(page(.reader(.margin)).readerMarginContent())
        margin.model.detailsAction(margin.onDetails)?()
        page(.reader(.history)).historyContent(reader: true).onAction?("history.next")
        page(.reader(.history)).readerAboutAction?()
        page(.about).match(.about).aboutContent()?.onSource?(Self.sourcesID)
        XCTAssertEqual(log, ["select:239325962", "source:polymarket-sources", "details:239843452", "history:history.next",
                             "about", "source:polymarket-sources"])
        log.removeAll()
        // The catalogue and Details content hold first, like the page.
        page(.catalogue).match(.catalogue).catalogueContent()?.onSelect?(Self.selection(Self.handicapRow))
        XCTAssertEqual(log, ["hold", "select:239843454"])
    }

    func testAStoryInTheStreamHoldsThroughItsOwnActivationOnly() throws {
        var log: [String] = []
        let stream = Self.stream()
        let input = Self.input(.final, stream: stream)
        let page = Page(input: input, originals: Self.originals(.final), onSource: { log.append("source:\($0)") },
                        onOriginalSelect: { log.append("select:\($0.identity.side)") }, onInteraction: { log.append("hold") })
        XCTAssertNil(page.pageWinnerContent(), "with a stream the stories live in it")
        XCTAssertNil(page.pageMarginContent())
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "winner-card")
        let activation = StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction = intent { log.append("activate") } else { log.append("other") }
        }
        let card = try XCTUnwrap(page.streamWinnerContent(activation: activation))
        XCTAssertNil(card.onExpand, "the stream offers its own open")
        EsportsWinnerModel10868.choice(card.model.sides[0].side.selection, resolves: true, onSelect: card.onSelect)?()
        card.onSource?()
        XCTAssertEqual(log, ["activate", "select:239325962", "activate", "source:polymarket-sources"])
        XCTAssertEqual(Model(input).storyLink("winner-card")?.card, .winner)
        XCTAssertEqual(Model(input).storyLink("margin-card")?.card, .margin)
        XCTAssertNil(Model(input).storyLink("unknown-card"))
        let doubled = Self.input(.final, stream: stream, stories: Self.storyLinks + [Self.storyLinks[0]])
        XCTAssertNil(Model(doubled).storyLink("winner-card"), "two links for one card id name no story")
        XCTAssertNil(Model(Self.input(.final, withoutMargin: true, stream: stream)).storyLink("margin-card"))
    }

    func testAbsentCallbacksOfferNoControlAndTheHookAloneDoesNothing() throws {
        var log: [String] = []
        let page = Page(input: Self.input(.final), originals: Self.originals(.final, selection: Self.selection(Self.niceTryRow)),
                        onInteraction: { log.append("hold") })
        XCTAssertNil(page.headlineContent()?.onAbout)
        XCTAssertNil(page.headlineContent()?.onOpen)
        XCTAssertNil(page.historyContent(reader: false).onAction)
        let winner = try XCTUnwrap(page.pageWinnerContent())
        XCTAssertNil(winner.onExpand)
        XCTAssertNil(winner.onSelect)
        XCTAssertNil(winner.onSource)
        XCTAssertNil(winner.model.detailsAction(winner.onDetails))
        XCTAssertNil(EsportsWinnerModel10868.choice(winner.model.sides[0].side.selection, resolves: true, onSelect: winner.onSelect))
        let margin = try XCTUnwrap(page.pageMarginContent())
        XCTAssertNil(margin.model.choice(margin.onSelect), "the original is static content without a callback")
        XCTAssertNil(page.chooserContent()?.onSelect)
        XCTAssertNil(page.catalogueAction)
        XCTAssertNil(page.readerAboutAction)
        XCTAssertFalse(page.readerControls(.winner).canGoBack)
        XCTAssertEqual(log, [])
    }

    func testAStorySourceOpensOnlyAnExactOwnerDocument() throws {
        var opened: [String] = []
        func card(_ sources: [RugbyMatchEventPageSource10868], label: String = "Polymarket sources and results") -> EsportsWinnerCard10868? {
            let story = Self.winner(.final, source: EsportsStorySource10868(sourceID: Self.sourcesID, label: label))
            return Page(input: Self.input(.final, winner: story, sources: sources), originals: Self.originals(.final),
                        onSource: { opened.append($0) }).pageWinnerContent()
        }
        let exact = try XCTUnwrap(card(Self.sources(.final)))
        XCTAssertEqual(exact.sourceLabel, "Polymarket sources and results")
        exact.onSource?()
        XCTAssertEqual(opened, [Self.sourcesID])
        let doubled = Self.sources(.final) + [Self.sources(.final)[0]]
        XCTAssertNil(try XCTUnwrap(card(doubled)).onSource, "two documents for one id open nothing")
        XCTAssertNil(try XCTUnwrap(card([])).onSource)
        XCTAssertNil(try XCTUnwrap(card(Self.sources(.final), label: " ")).onSource)
        XCTAssertNil(try XCTUnwrap(card(Self.sources(.final), label: " ")).sourceLabel)
    }

    // MARK: - Reader order (Design E2)

    private static func controls(_ page: Page, _ card: Card) -> [Card?] {
        let controls = page.readerControls(card)
        return [controls.previous, controls.next]
    }

    func testTheDefaultReaderOrderIsTheReferenceOrder() {
        let page = Page(input: Self.input(.final), onReaderIntent: { _ in })
        XCTAssertEqual(Model(Self.input(.final)).readerSequence, [.history, .winner, .margin])
        XCTAssertEqual(Self.controls(page, .history), [nil, .winner])
        XCTAssertEqual(Self.controls(page, .winner), [.history, .margin])
        XCTAssertEqual(Self.controls(page, .margin), [.winner, nil])
        XCTAssertEqual(Model(Self.input(.final)).cardName(.margin), "Map 1 winning margin")
        // Without an owner order the mounted cards keep the page's order.
        let noWinner = Page(input: Self.input(.final, withoutWinner: true), onReaderIntent: { _ in })
        XCTAssertEqual(Self.controls(noWinner, .history), [nil, .margin])
    }

    func testTheOwnersReaderOrderDrivesNeighbourLabelsAndPayloads() {
        var intents: [EsportsReaderIntent10868] = []
        let input = Self.input(.final, readerOrder: [.history, .margin, .winner])
        let page = Page(input: input, mode: .reader(.margin), onReaderIntent: { intents.append($0) })
        XCTAssertEqual(Self.controls(page, .history), [nil, .margin])
        XCTAssertEqual(Self.controls(page, .margin), [.history, .winner])
        XCTAssertEqual(Self.controls(page, .winner), [.margin, nil])
        let controls = page.readerControls(.margin)
        XCTAssertEqual([controls.previous.map(Model(input).cardName), controls.next.map(Model(input).cardName)],
                       ["Chance to win", "Match winner"])
        Page.bind(page.onReaderIntent, .previous(controls.previous!))?()
        Page.bind(page.onReaderIntent, .next(controls.next!))?()
        Page.bind(page.onReaderIntent, .back)?()
        XCTAssertEqual(intents, [.previous(.history), .next(.winner), .back])
    }

    func testAHeldReaderOrderIsIndependentOfAReRankedStream() {
        let held: [Card] = [.history, .winner, .margin]
        for stream in [Self.stream(winnerFirst: true), Self.stream(winnerFirst: false)] {
            let page = Page(input: Self.input(.final, stream: stream, readerOrder: held), onReaderIntent: { _ in })
            XCTAssertEqual(Self.controls(page, .winner), [.history, .margin], "arrivals that re-rank the stream move nothing")
        }
        let ranked = Page(input: Self.input(.final, stream: Self.stream(winnerFirst: false), readerOrder: [.margin, .winner, .history]),
                          onReaderIntent: { _ in })
        XCTAssertEqual(Self.controls(ranked, .margin), [nil, .winner])
        XCTAssertEqual(Self.controls(ranked, .history), [.winner, nil])
    }

    func testAnExplicitEmptyReaderOrderOffersNoNeighbour() {
        let page = Page(input: Self.input(.final, readerOrder: []), onReaderIntent: { _ in })
        for card in Card.allCases {
            XCTAssertEqual(Self.controls(page, card), [nil, nil])
            XCTAssertTrue(page.readerControls(card).canGoBack, "Back stays the owner's")
        }
    }

    func testAnAbsentOrUnmountedEntryOffersNoNeighbourAndNothingJumps() {
        // Winner is listed but not mounted: nothing skips past it.
        let unmounted = Page(input: Self.input(.final, withoutWinner: true, readerOrder: [.history, .winner, .margin]),
                             onReaderIntent: { _ in })
        XCTAssertEqual(Self.controls(unmounted, .history), [nil, nil])
        XCTAssertEqual(Self.controls(unmounted, .margin), [nil, nil])
        XCTAssertFalse(unmounted.readerControls(.winner).canGoBack, "an unmounted card has no full-size controls")
        // Margin is mounted but absent from the owner's order.
        let absent = Page(input: Self.input(.final, readerOrder: [.history, .winner]), onReaderIntent: { _ in })
        XCTAssertEqual(Self.controls(absent, .margin), [nil, nil])
        XCTAssertTrue(absent.readerControls(.margin).canGoBack)
        XCTAssertEqual(Self.controls(absent, .winner), [.history, nil])
    }

    func testADuplicatedReaderEntryIsAmbiguousAndInventsNoNeighbour() {
        let page = Page(input: Self.input(.final, readerOrder: [.history, .winner, .winner, .margin]), onReaderIntent: { _ in })
        XCTAssertEqual(Self.controls(page, .winner), [nil, nil])
        XCTAssertEqual(Self.controls(page, .history), [nil, nil], "the next entry is ambiguous")
        XCTAssertEqual(Self.controls(page, .margin), [nil, nil])
        XCTAssertNil(Model.uniqueIndex(of: .winner, in: [.history, .winner, .winner, .margin]))
        XCTAssertEqual(Model.uniqueIndex(of: .margin, in: [.history, .winner, .winner, .margin]), 3)
    }

    func testTheReaderShowsTheSameViewsAndOwnerWordsForAnUnmountedCard() throws {
        let model = Model(Self.input(.final))
        let page = Page(input: Self.input(.final), mode: .reader(.winner), originals: Self.originals(.final))
        XCTAssertEqual(page.readerWinnerContent()?.model, model.winnerModel(Self.originals(.final)))
        XCTAssertEqual(page.readerMarginContent()?.model, model.marginModel(Self.originals(.final)))
        XCTAssertNil(Page(input: Self.input(.final, withoutMargin: true)).readerMarginContent())
        XCTAssertFalse(Model(Self.input(.final, withoutMargin: true)).isMounted(.margin))
        XCTAssertEqual(Self.matchCopy.readerUnavailable, "This card is not available now")
    }

    // MARK: - Layout and targets (Design E1)

    func testLayoutPlansStackOnPhonesAndAccessibilitySizes() {
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(RugbyMatchEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertTrue(Model.sidesStack(accessibilitySize: true))
        XCTAssertFalse(Model.sidesStack(accessibilitySize: false))
        XCTAssertEqual(Model.readingOrder, [.headline, .notice, .anchor, .stories, .originals, .catalogue])
        XCTAssertGreaterThan(Model.sortPriority(.headline), Model.sortPriority(.stories))
        XCTAssertGreaterThan(Model.sortPriority(.stories), Model.sortPriority(.originals))
    }

    func testEveryControlTargetIsAtLeastTheMinimumAtSmallDefaultAndAccessibilitySizes() throws {
        XCTAssertEqual(Model.minimumTarget, 44)
        XCTAssertEqual(Model.targetHeight(.nan), 44)
        XCTAssertEqual(Model.targetHeight(-1), 44)
        #if canImport(UIKit)
        let metrics = UIFontMetrics(forTextStyle: .body)
        func scaled(_ size: UIContentSizeCategory) -> CGFloat {
            metrics.scaledValue(for: 44, compatibleWith: UITraitCollection(preferredContentSizeCategory: size))
        }
        let small = scaled(.extraSmall), standard = scaled(.large), accessibility = scaled(.accessibilityExtraExtraExtraLarge)
        XCTAssertLessThan(small, 44, "control: the body-scaled metric alone shrinks below the minimum")
        XCTAssertEqual(Model.targetHeight(small), 44)
        XCTAssertEqual(Model.targetHeight(standard), max(44, standard))
        XCTAssertEqual(Model.targetHeight(accessibility), accessibility)
        XCTAssertGreaterThan(accessibility, 44)
        #endif
        // The margin original is a control exactly while it resolves and a callback exists.
        var log: [String] = []
        let margin = try XCTUnwrap(Page(input: Self.input(.final), originals: Self.originals(.final),
                                        onOriginalSelect: { log.append("select:\($0.identity.side)") },
                                        onInteraction: { log.append("hold") }).pageMarginContent())
        XCTAssertEqual(margin.model.content?.outcome, "Nice Try", "the control's label is the original's own outcome words")
        XCTAssertTrue(margin.model.resolves)
        margin.model.choice(margin.onSelect)?()
        XCTAssertEqual(log, ["hold", "select:239843452"], "one hold, then the exact selection")
        let still = try XCTUnwrap(Page(input: Self.input(.final), originals: Self.originals(.final)).pageMarginContent())
        XCTAssertNil(still.model.choice(still.onSelect), "without a callback the same label is static content")
    }
}
