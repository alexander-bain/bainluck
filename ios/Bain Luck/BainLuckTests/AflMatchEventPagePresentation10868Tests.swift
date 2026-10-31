import CryptoKit
import SwiftUI
import XCTest
@testable import Bain_Luck

// #10868 — AFL match page (`afl-match`). Prepared source checks; NOT RUN (no
// build, simulator, XCTest or typecheck grant for this package).
//
// RETAINED FIXTURE: Brisbane Lions vs Fremantle Dockers, Sep 26 2026 — Kalshi
// KXAFLGAME-26SEP260030BRIFRE (two winner contracts) and ESPN 1133711, from the
// approved `aflMatch.json` and `aflScoringCapture.json`. Listed start 04:30Z
// (1790397000) is not a verified kickoff or end. `retainedCloses` holds the 553
// admitted positive-volume minute closes (Brisbane 271, Fremantle 282) as
// `team minute-end-epoch close-cents`; `retainedPlays` holds the 55 scoring
// plays in source order as `id|quarter|clock|type|team|brisbane|fremantle|text`.
// The quarter points, the low minute's candle and both contracts' rules are
// retained verbatim below. These rows were selected from the capture by the
// test author with the reference's own admission rules; NOTHING here ports
// those rules into the product: the owner elects, validates and formats.
//
// PHASE-ADMITTED OWNER FIXTURES. Every ordinary input carries only what its
// phase admits: before play the pre-match chances, the closes strictly before
// the listed start, the originals at their pre-match readings and a before
// About; during play the same plus the recorded closes up to a CONSTRUCTED
// in-play cut (05:00Z, `constructedLiveCut`) — genuine live evidence does not
// exist, so every in-play value is CONSTRUCTED from that cut and is labelled
// so here — with no score, quarter, scoring play, result, report or projected
// final; at the final everything, with the reported actual kept apart from the
// contract settlement and from the historical chances. Inputs that hand a
// later fact to an earlier phase are named hostile controls; they show the
// page's structural phase gates and never authorize a history or prose filter.
// Fixture clock words are CONSTRUCTED UTC copy: real production binding must
// localize through the existing owner formatter.
//
// PREPARED ROSTER (NOT RUN): see the `func test…` list; each name states the
// obligation it checks.

@MainActor
final class AflMatchEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = AflMatchEventPagePresentation10868Tests
    private typealias Page = AflMatchEventPagePresentation10868
    private typealias Model = AflMatchEventPageModel10868
    private typealias Details = OriginalMarketDetails9483
    private typealias Phase = AflMatchEventPagePhase10868

    // MARK: - Retained data

    private static let retainedCloses = """
F 1789879800 42
F 1789889820 43
B 1789907280 60
B 1789910160 59
F 1789923480 44
F 1789930980 43
F 1789937340 43
F 1789938960 42
B 1789939020 52
B 1789945500 52
F 1789945500 43
F 1789949520 42
F 1789954800 43
B 1789958040 59
B 1789959540 59
B 1789967700 59
F 1789984980 38
B 1789985040 59
B 1790021340 59
F 1790023200 43
B 1790042760 58
F 1790042940 43
B 1790053860 58
F 1790077560 42
B 1790081100 58
B 1790081160 59
B 1790082960 57
B 1790088780 59
B 1790094600 60
F 1790094660 42
B 1790096820 60
F 1790098320 42
B 1790101260 61
F 1790103240 42
F 1790105220 42
F 1790105280 42
B 1790111040 59
F 1790111760 41
B 1790120220 61
B 1790120280 61
F 1790125140 41
F 1790127060 41
B 1790139540 59
B 1790165280 58
B 1790168100 58
B 1790169000 60
F 1790173560 41
F 1790183220 43
B 1790183880 59
F 1790183880 42
F 1790185680 42
F 1790186340 42
F 1790214300 42
B 1790215800 59
F 1790216400 42
F 1790221740 42
B 1790223780 58
F 1790228400 42
F 1790228460 42
F 1790230500 42
F 1790232900 42
F 1790240460 44
B 1790248020 60
F 1790257740 42
B 1790265300 60
B 1790268360 60
B 1790274540 60
B 1790279100 60
B 1790283960 60
B 1790286540 60
B 1790292900 59
F 1790294220 41
F 1790294460 41
F 1790295000 41
F 1790295540 42
B 1790298120 59
B 1790298540 59
B 1790298780 58
B 1790299440 59
F 1790299920 42
F 1790301600 42
F 1790304060 42
B 1790309700 57
B 1790311260 58
B 1790311860 58
F 1790314320 42
F 1790316300 42
B 1790318100 59
F 1790332200 41
F 1790333100 41
B 1790342460 59
F 1790346180 41
F 1790347500 41
F 1790348100 41
F 1790348340 41
B 1790348760 59
B 1790349300 59
F 1790349540 41
B 1790349720 59
B 1790350260 59
F 1790351460 41
F 1790354040 41
F 1790354700 41
B 1790355240 60
B 1790355420 60
F 1790355660 41
B 1790358000 60
B 1790358780 60
F 1790359200 41
F 1790359560 41
F 1790360460 41
B 1790361120 60
F 1790361540 41
B 1790362620 60
F 1790362920 41
B 1790363100 60
F 1790363940 41
B 1790364420 60
F 1790365260 41
B 1790365440 60
B 1790366160 60
B 1790367360 60
F 1790367960 41
B 1790369280 60
B 1790370960 59
B 1790372100 59
F 1790372520 41
B 1790372820 59
F 1790373540 41
F 1790373720 41
F 1790374740 41
B 1790374800 59
B 1790375100 59
F 1790375280 41
F 1790375640 41
F 1790376120 41
F 1790376240 41
F 1790377860 43
F 1790377920 43
B 1790378100 59
B 1790378220 59
B 1790378460 59
F 1790379120 43
B 1790379480 59
B 1790379960 59
B 1790380080 59
F 1790380740 43
F 1790381040 43
F 1790382120 43
F 1790382480 43
B 1790382600 59
F 1790382720 43
B 1790382780 59
F 1790383500 43
F 1790383680 43
B 1790383740 59
B 1790383800 59
B 1790383980 59
B 1790384220 59
F 1790384280 43
F 1790384640 43
F 1790384700 43
B 1790384760 59
B 1790385300 59
B 1790385360 58
F 1790385420 43
B 1790386140 59
B 1790386260 59
F 1790386440 43
B 1790386560 59
F 1790386680 43
B 1790386800 59
B 1790386860 59
F 1790386980 43
B 1790387100 59
F 1790387280 43
F 1790387400 42
B 1790387520 58
F 1790387580 42
F 1790387640 43
F 1790387700 43
F 1790388000 43
F 1790388300 42
F 1790388480 42
F 1790388780 42
F 1790388840 42
B 1790388960 59
F 1790388960 42
B 1790389080 59
B 1790389140 59
F 1790389140 43
F 1790389380 43
F 1790389500 43
B 1790389620 59
B 1790389740 59
B 1790389860 59
F 1790389860 42
F 1790390160 43
F 1790390220 43
B 1790390280 59
B 1790390460 59
B 1790390580 59
F 1790390640 43
F 1790391300 43
F 1790391360 43
B 1790391480 59
F 1790391540 43
B 1790391600 59
F 1790391600 43
F 1790391660 43
F 1790391840 43
B 1790391960 59
F 1790392140 43
F 1790392260 43
F 1790392440 43
B 1790392680 59
F 1790392860 43
F 1790392980 43
F 1790393040 43
B 1790393100 59
F 1790393220 43
F 1790393340 43
F 1790393400 43
F 1790393460 43
B 1790393700 59
F 1790393700 43
B 1790393880 59
F 1790393880 43
B 1790393940 59
B 1790394000 59
F 1790394060 43
F 1790394120 43
B 1790394180 59
F 1790394180 43
B 1790394360 59
F 1790394360 43
B 1790394480 59
B 1790394600 59
F 1790394600 43
B 1790394720 59
B 1790394780 59
F 1790394780 43
B 1790394840 59
F 1790394840 43
B 1790394900 59
F 1790394960 43
B 1790395020 59
F 1790395020 43
B 1790395140 59
F 1790395140 43
B 1790395260 59
F 1790395260 43
F 1790395500 43
F 1790395560 43
B 1790395620 58
F 1790395620 43
F 1790395680 43
B 1790395860 58
B 1790395920 59
B 1790395980 58
F 1790395980 43
B 1790396040 59
F 1790396040 43
B 1790396100 59
F 1790396220 43
B 1790396280 59
F 1790396280 43
F 1790396340 43
B 1790396400 59
B 1790396460 56
B 1790396520 55
F 1790396520 45
B 1790396580 56
F 1790396580 45
F 1790396640 45
F 1790396760 45
F 1790396820 45
F 1790396880 45
B 1790396940 56
B 1790397000 57
F 1790397000 44
F 1790397060 47
B 1790397120 58
F 1790397180 48
B 1790397240 58
F 1790397240 48
B 1790397360 59
F 1790397360 52
B 1790397540 57
F 1790397540 47
B 1790397660 58
F 1790397660 50
F 1790397780 48
B 1790397840 59
F 1790397840 44
B 1790397900 58
F 1790397900 44
B 1790397960 58
F 1790397960 44
B 1790398020 52
F 1790398020 53
B 1790398080 51
F 1790398080 54
B 1790398200 48
F 1790398200 61
B 1790398260 48
F 1790398260 60
B 1790398320 52
F 1790398320 61
B 1790398380 51
F 1790398380 60
B 1790398440 51
B 1790398500 53
F 1790398500 50
F 1790398560 50
B 1790398620 50
F 1790398620 63
B 1790398680 54
F 1790398680 41
B 1790398740 58
F 1790398740 44
B 1790398800 51
F 1790398800 57
B 1790398860 56
F 1790398860 47
B 1790398920 58
F 1790398920 44
B 1790398980 58
B 1790399040 59
F 1790399040 48
B 1790399100 57
B 1790399160 58
F 1790399160 44
B 1790399220 57
F 1790399220 51
F 1790399280 49
B 1790399340 55
F 1790399340 49
F 1790399400 49
B 1790399460 52
F 1790399460 49
F 1790399520 51
F 1790399580 53
B 1790399640 52
F 1790399640 53
F 1790399700 52
B 1790399760 50
F 1790399760 52
B 1790399820 50
F 1790399820 52
B 1790399880 47
B 1790399940 48
B 1790400000 49
F 1790400000 49
B 1790400060 56
B 1790400120 38
F 1790400120 67
B 1790400180 41
F 1790400180 64
B 1790400240 48
F 1790400240 57
B 1790400300 40
F 1790400300 55
B 1790400360 46
B 1790400420 48
F 1790400420 51
B 1790400480 49
B 1790400540 55
F 1790400540 50
F 1790400600 54
B 1790400660 51
F 1790400660 54
B 1790400720 53
F 1790400780 52
B 1790400840 53
F 1790400840 51
B 1790400900 52
F 1790400900 52
F 1790400960 52
B 1790401080 52
F 1790401080 54
B 1790401140 53
F 1790401200 48
B 1790401260 53
F 1790401260 50
B 1790401320 57
B 1790401380 53
F 1790401380 49
B 1790401440 51
F 1790401440 51
B 1790401560 49
B 1790401620 47
F 1790401620 55
B 1790401680 47
F 1790401680 55
B 1790401740 51
B 1790401800 55
F 1790401800 47
B 1790401860 50
F 1790401860 56
B 1790401920 47
F 1790401920 57
B 1790401980 48
B 1790402100 54
F 1790402100 50
B 1790402220 55
B 1790402280 63
F 1790402280 49
B 1790402340 51
F 1790402340 52
F 1790402400 53
B 1790402460 49
F 1790402460 53
B 1790402520 49
F 1790402520 57
B 1790402640 53
F 1790402640 53
B 1790402700 54
B 1790402760 51
F 1790402760 53
B 1790402820 51
F 1790402820 53
B 1790402880 54
B 1790402940 54
F 1790402940 51
B 1790403000 54
F 1790403000 52
B 1790403060 51
B 1790403120 55
F 1790403120 51
B 1790403180 54
F 1790403180 56
B 1790403240 41
F 1790403240 65
B 1790403300 36
F 1790403300 59
B 1790403360 39
F 1790403360 59
F 1790403420 58
F 1790403480 60
B 1790403540 31
F 1790403540 71
B 1790403600 20
F 1790403600 79
B 1790403720 30
F 1790403720 71
B 1790403780 40
F 1790403780 59
B 1790403840 42
F 1790403840 61
B 1790403900 36
F 1790403900 62
B 1790403960 45
F 1790403960 49
B 1790404020 53
F 1790404020 56
B 1790404080 60
F 1790404080 50
F 1790404140 49
B 1790404200 50
F 1790404200 55
B 1790404260 45
F 1790404260 52
B 1790404320 52
B 1790404380 51
B 1790404440 53
B 1790404560 41
F 1790404560 63
B 1790404620 44
F 1790404620 65
B 1790404680 37
F 1790404680 71
B 1790404740 37
F 1790404740 70
B 1790404800 32
F 1790404800 70
B 1790404860 30
F 1790404860 74
B 1790404920 31
B 1790404980 35
F 1790404980 69
F 1790405040 68
B 1790405100 36
F 1790405100 69
B 1790405160 32
F 1790405160 70
B 1790405220 28
F 1790405220 69
B 1790405280 25
F 1790405280 74
B 1790405340 34
F 1790405340 74
B 1790405400 32
F 1790405400 71
B 1790405460 33
F 1790405460 71
B 1790405520 35
F 1790405520 65
B 1790405580 53
F 1790405580 45
B 1790405640 49
F 1790405640 57
B 1790405700 34
F 1790405700 60
B 1790405760 44
F 1790405760 61
B 1790405820 47
F 1790405820 60
B 1790405880 44
F 1790405880 61
B 1790405940 39
F 1790405940 65
B 1790406000 34
F 1790406000 61
B 1790406060 21
F 1790406060 79
B 1790406120 15
F 1790406120 83
B 1790406180 9
F 1790406180 89
B 1790406240 5
F 1790406240 88
B 1790406300 9
F 1790406300 90
B 1790406360 5
F 1790406360 94
B 1790406420 5
F 1790406420 99
B 1790406480 3
F 1790406480 97
B 1790406540 22
F 1790406540 80
B 1790406600 24
F 1790406600 85
B 1790406660 14
F 1790406660 84
B 1790406720 62
F 1790406720 41
B 1790406780 63
F 1790406780 32
B 1790406840 99
F 1790406840 1
B 1790406900 99
F 1790406900 1
B 1790406960 99
F 1790406960 1
B 1790407020 99
F 1790407020 1
B 1790407140 99
B 1790407200 99
B 1790407320 99
B 1790407380 99
B 1790407440 99
"""

    private static let retainedPlays = """
6314316|1|2:43|Behind|FRE|0|1|P. Voss Behind
6314328|1|3:11|Goal|BRI|6|1|C. Cameron Goal
6314336|1|4:46|Goal|FRE|6|7|J. Treacy Goal
6314393|1|9:50|Behind|BRI|7|7|C. Rayner Behind
6314416|1|11:12|Behind|BRI|8|7|C. McKenna Behind
6314429|1|11:43|Rushed|BRI|9|7|Rushed
6314486|1|15:24|Rushed|FRE|9|8|Rushed
6314498|1|15:58|Behind|FRE|9|9|I. Dudley Behind
6314546|1|18:28|Goal|FRE|9|15|I. Dudley Goal
6314581|1|22:20|Goal|BRI|15|15|O. Allen Goal
6314594|1|23:26|Behind|BRI|16|15|O. Allen Behind
6314632|1|24:17|Behind|FRE|16|16|O. McDonald Behind
6314638|1|25:32|Goal|BRI|22|16|K. Lohmann Goal
6314654|1|26:40|Behind|BRI|23|16|E. Hipwood Behind
6314666|1|27:50|Goal|FRE|23|22|M. Reid Goal
6314724|2|1:06|Goal|FRE|23|28|P. Voss Goal
6314747|2|3:20|Goal|BRI|29|28|C. McKenna Goal
6314765|2|5:10|Goal|FRE|29|34|J. Amiss Goal
6314773|2|6:28|Behind|FRE|29|35|S. Bolton Behind
6314801|2|8:14|Goal|BRI|35|35|L. Ashcroft Goal
6314856|2|11:59|Behind|FRE|35|36|P. Voss Behind
6314888|2|14:10|Goal|FRE|35|42|P. Voss Goal
6314928|2|17:06|Behind|BRI|36|42|E. Hipwood Behind
6314937|2|18:15|Goal|BRI|42|42|S. Draper Goal
6314953|2|20:10|Behind|BRI|43|42|L. Neale Behind
6315026|2|27:14|Behind|FRE|43|43|K. Worner Behind
6315078|3|1:09|Behind|FRE|43|44|J. Treacy Behind
6315119|3|4:05|Goal|FRE|43|50|J. Amiss Goal
6315141|3|6:28|Rushed|FRE|43|51|Rushed
6315166|3|8:06|Rushed|FRE|43|52|Rushed
6315221|3|12:14|Goal|FRE|43|58|I. Dudley Goal
6315263|3|16:21|Goal|BRI|49|58|K. Lohmann Goal
6315279|3|17:31|Behind|FRE|49|59|M. Frederick Behind
6315313|3|19:31|Goal|BRI|55|59|O. Allen Goal
6315327|3|21:21|Behind|FRE|55|60|M. Johnson Behind
6315342|3|22:38|Goal|BRI|61|60|C. Cameron Goal
6315349|3|23:41|Goal|FRE|61|66|H. Young Goal
6315418|3|28:47|Behind|BRI|62|66|L. Morris Behind
6315441|3|30:13|Goal|FRE|62|72|H. Young Goal
6315475|4|2:12|Rushed|FRE|62|73|Rushed
6315527|4|4:47|Behind|BRI|63|73|H. McCluggage Behind
6315556|4|6:52|Behind|BRI|64|73|C. McKenna Behind
6315569|4|7:35|Goal|BRI|70|73|L. Morris Goal
6315585|4|8:54|Behind|FRE|70|74|S. Bolton Behind
6315614|4|10:26|Behind|BRI|71|74|C. McKenna Behind
6315626|4|11:29|Behind|BRI|72|74|C. Rayner Behind
6315673|4|14:24|Behind|FRE|72|75|H. Young Behind
6315680|4|16:27|Goal|FRE|72|81|M. Frederick Goal
6315707|4|19:21|Behind|FRE|72|82|J. Treacy Behind
6315732|4|20:48|Behind|FRE|72|83|M. Johnson Behind
6315743|4|21:49|Goal|FRE|72|89|P. Voss Goal
6315764|4|23:10|Goal|BRI|78|89|C. Cameron Goal
6315774|4|24:29|Goal|BRI|84|89|Z. Bailey Goal
6315813|4|27:59|Goal|BRI|90|89|L. Morris Goal
6315832|4|30:02|Goal|BRI|96|89|L. Morris Goal
"""

    /// ESPN linescores, verbatim: each quarter's points.
    private static let retainedQuarterPoints = (brisbane: [23, 20, 19, 34], fremantle: [22, 21, 29, 17])

    /// Brisbane's low minute's retained candle (`price`, dollars), verbatim.
    private static let retainedLowCandle = (at: 1_790_406_480, open: "0.0600", high: "0.0900", low: "0.0100",
                                            close: "0.0300", mean: "0.0376")

    /// Both contracts' rules, verbatim from `markets.markets[*]`.
    private static let retainedRulesPrimary = [
        "BRI": "If Brisbane Lions wins the Brisbane Lions vs Fremantle Dockers professional AFL game originally scheduled for Sep 26, 2026, then the market resolves to Yes.",
        "FRE": "If Fremantle Dockers wins the Brisbane Lions vs Fremantle Dockers professional AFL game originally scheduled for Sep 26, 2026, then the market resolves to Yes.",
    ]
    private static let retainedRulesSecondary = "The following market refers to the Brisbane Lions vs Fremantle Dockers professional AFL game originally scheduled for Sep 26, 2026. If the game ends in a tie, the markets will resolve to 50/50. If the game is cancelled or rescheduled to over two weeks away, the market will resolve to a fair price in accordance with the rules.\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the Governing League. All trademarks, logos, and brand names are the property of their respective owners."
    private static let retainedTitle = "Brisbane Lions vs Fremantle Dockers winner?"
    /// sha256 of the UTF-8 source strings in `aflMatch.json` (507afc83…).
    private static let retainedRulesHashes = [
        "BRI": "a8397faf3b5b498cbef9978aafe87e091b4f5c43fb5470370fad7fc41a931382",
        "FRE": "f8f3e56a5f34189a7e78be59566f74471402b55b5b474944480a17b74ce16cc1",
        "secondary": "45f96aee0c9766e3f122c45acefb19b6d8c6c60a1af62d686e67413c962c30a7",
        "title": "b9ac02078ca776e8f3fecf7e87d15f1e6c1447231dbce60c3d342b5f63d452f2",
    ]

    private struct Close {
        let team: String
        let at: Int
        let cents: Int
    }

    private struct Play {
        let id: String
        let quarter: Int
        let clock: String
        let kind: String
        let team: String
        let brisbane: Int
        let fremantle: Int
        let text: String

        var margin: Int { brisbane - fremantle }
    }

    private static let closes: [Close] = retainedCloses.split(separator: "\n").compactMap { line in
        let parts = line.split(separator: " ")
        guard parts.count == 3, let at = Int(parts[1]), let cents = Int(parts[2]) else { return nil }
        return Close(team: String(parts[0]), at: at, cents: cents)
    }

    private static let plays: [Play] = retainedPlays.split(separator: "\n").compactMap { line in
        let parts = line.split(separator: "|", omittingEmptySubsequences: false).map(String.init)
        guard parts.count == 8, let quarter = Int(parts[1]), let brisbane = Int(parts[5]), let fremantle = Int(parts[6]) else {
            return nil
        }
        return Play(id: parts[0], quarter: quarter, clock: parts[2], kind: parts[3], team: parts[4],
                    brisbane: brisbane, fremantle: fremantle, text: parts[7])
    }

    private static let listedStart = 1_790_397_000
    /// CONSTRUCTED: the in-play instant the during page is drawn at.
    private static let constructedLiveCut = 1_790_398_800
    private static let lowAt = 1_790_406_480

    // MARK: Teams

    private struct Team {
        let key: String
        let letter: String
        let name: String
        let short: String
        let shape: FieldHeadlineKeyShape10868
        let tint: Color
        let contractYes: Bool

        var ticker: String { "KXAFLGAME-26SEP260030BRIFRE-\(key)" }
    }

    private static let brisbane = Team(key: "BRI", letter: "B", name: "Brisbane Lions", short: "Brisbane", shape: .circle,
                                       tint: Color(red: 0.0, green: 0.36, blue: 0.75), contractYes: true)
    private static let fremantle = Team(key: "FRE", letter: "F", name: "Fremantle Dockers", short: "Fremantle", shape: .diamond,
                                        tint: Color(red: 0.05, green: 0.55, blue: 0.55), contractYes: false)
    private static let teams = [brisbane, fremantle]

    private static func closes(_ team: Team) -> [Close] { closes.filter { $0.team == team.letter } }

    private static func baseline(_ team: Team) -> Close { closes(team).filter { $0.at < listedStart }.last! }

    /// CONSTRUCTED: the team's last recorded close at or before the in-play cut.
    private static func cutClose(_ team: Team) -> Close { closes(team).filter { $0.at <= constructedLiveCut }.last! }

    private static func lastClose(_ team: Team) -> Close { closes(team).last! }

    /// The closes each phase admits; the page never filters them.
    private static func admitted(_ team: Team, _ phase: Phase) -> [Close] {
        switch phase {
        case .before: return closes(team).filter { $0.at < listedStart }
        case .during: return closes(team).filter { $0.at <= constructedLiveCut }
        case .final: return closes(team)
        }
    }

    // MARK: Fixture clock words (CONSTRUCTED UTC copy)

    private static func clock(_ at: Int) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "MMM d, h:mm a"
        return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(at))) + " UTC"
    }

    private static func shortClock(_ at: Int) -> String {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = "h:mm a"
        return formatter.string(from: Date(timeIntervalSince1970: TimeInterval(at))) + " UTC"
    }

    private static func minute(_ at: Int) -> String { "Minute ending \(clock(at)) · Kalshi" }

    private static func figure(_ close: Close) -> String { "\(close.cents)%" }

    // MARK: - History

    private static func pointID(_ team: Team, _ at: Int) -> String { "\(team.key)@\(at)" }

    private static func runs(_ closes: [Close]) -> [[Close]] {
        var runs: [[Close]] = []
        for close in closes {
            if let last = runs.last?.last, close.at - last.at == 60 {
                runs[runs.count - 1].append(close)
            } else {
                runs.append([close])
            }
        }
        return runs
    }

    /// Every admitted minute end of both teams, in order.
    private static func minutes(_ phase: Phase) -> [Int] {
        Array(Set(teams.flatMap { admitted($0, phase).map(\.at) })).sorted()
    }

    /// The owner's history for a phase: its admitted closes only, adjacent
    /// minutes joined, no settled endpoint. `inspecting` is a minute the host
    /// holds; `minutesOverride` is the hostile control that hands another
    /// phase's minutes to this one.
    private static func history(_ phase: Phase, inspecting: Int? = nil, minutesOverride: Phase? = nil) -> FieldHistoryInput10868 {
        let source = minutesOverride ?? phase
        let times = minutes(source)
        func series(_ team: Team) -> FieldHistorySeries10868 {
            let mine = admitted(team, source)
            let base = baseline(team)
            let shown = inspecting.flatMap { at in mine.first { $0.at == at } } ?? mine.last!
            return FieldHistorySeries10868(
                id: team.key, name: team.name, shape: team.shape, tint: team.tint,
                runs: runs(mine).enumerated().map { number, run in
                    FieldHistoryRun10868(id: "\(team.key)#run-\(number)", points: run.map { close in
                        FieldHistoryPoint10868(id: pointID(team, close.at), x: Double(close.at - listedStart),
                                               probability: Double(close.cents) / 100,
                                               style: close.at < listedStart ? .hollow : .filled)
                    })
                },
                links: [], labelPointID: pointID(team, mine.last!.at),
                before: .observation(pointID: pointID(team, base.at), figure: figure(base), provenance: minute(base.at)),
                recorded: .observation(pointID: pointID(team, shown.at), figure: figure(shown), provenance: minute(shown.at)),
                absentWords: "No recorded trades", choose: nil)
        }
        let inspection = inspecting.map { at -> FieldHistoryInspection10868 in
            var selections: [String: FieldHistorySelection10868] = [:]
            for team in teams {
                if let close = admitted(team, source).first(where: { $0.at == at }) {
                    selections[team.key] = .point(id: pointID(team, at), spoken: figure(close))
                } else {
                    selections[team.key] = .absent(words: "No trade in this minute")
                }
            }
            let index = times.firstIndex(of: at) ?? 0
            let choiceTimes = times.indices.contains(index - 1) ? [times[index - 1], at] : [at]
            return FieldHistoryInspection10868(
                x: Double(at - listedStart), caption: "Minute ending \(clock(at)) · close",
                selections: selections,
                choices: choiceTimes.map { time in
                    FieldHistoryInspectionChoice10868(id: "minute@\(time)", lines: [clock(time)], spoken: minute(time),
                                                      isSelected: time == at)
                },
                choicePresentation: .slider(label: "Traded minute"),
                note: "Only trades in this exact minute")
        }
        let readout: FieldHistoryReadoutIntent10868
        if inspecting != nil {
            readout = .beforeAndInspected(beforeLabel: "Pre-match", inspectedLabel: "Minute close")
        } else if phase == .before {
            readout = .singleBefore(label: "Pre-match")
        } else {
            readout = .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Last recorded")
        }
        // The owner's step targets: the admitted minute before and after the
        // held one, or the last and first admitted minutes with nothing held.
        let held = inspecting.flatMap { times.firstIndex(of: $0) }
        let previousTarget = held.map { times.indices.contains($0 - 1) ? times[$0 - 1] : nil } ?? times.last
        let nextTarget = held.map { times.indices.contains($0 + 1) ? times[$0 + 1] : nil } ?? times.first
        let points = teams.flatMap { admitted($0, source) }.map(\.at)
        let lower = Double(points.min()! - listedStart), upper = Double(points.max()! - listedStart)
        return FieldHistoryInput10868(
            title: "Win probability history",
            caption: phase == .before ? "Last trades before listed start" : "Last recorded trades",
            series: teams.map(series), selection: .none,
            domain: FieldHistoryDomain10868(lower: lower, upper: upper), ceiling: 1,
            yTicks: [0, 0.25, 0.5, 0.75, 1].map { FieldHistoryTick10868(value: $0, lines: ["\(Int($0 * 100))%"]) },
            xTicks: [FieldHistoryTick10868(value: lower, lines: [clock(points.min()!)]),
                     FieldHistoryTick10868(value: upper, lines: [clock(points.max()!)])],
            guides: [FieldHistoryGuide10868(id: "listed-start", x: 0, label: "Listed start")],
            breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow · before the listed start",
                                              filled: "Filled · recorded after the listed start"),
            comparisonExplanation: nil,
            notes: ["Only adjacent traded minutes connect. Gaps mean no recorded trades.",
                    "Each point is a minute's close, not an exact trade time."],
            summary: "\(points.count) recorded minute closes for both teams on a 0 to 100% scale.",
            plotHeight: 302, unboundReadingWords: "Not recorded at this minute", plotUnavailableWords: nil,
            windows: FieldHistoryWindows10868(groupLabel: "History window", choices: [
                FieldHistoryWindowChoice10868(action: FieldHistoryAction10868(id: "history.window.match", label: "Around the match",
                                                                              spokenLabel: nil, isAvailable: true), isSelected: false),
                FieldHistoryWindowChoice10868(action: FieldHistoryAction10868(id: "history.window.all", label: "All captured trades",
                                                                              spokenLabel: nil, isAvailable: true), isSelected: true),
            ]),
            scale: nil, moreOriginals: nil,
            details: FieldHistoryAction10868(id: "history.details", label: "History & source details", spokenLabel: nil, isAvailable: true),
            expand: FieldHistoryAction10868(id: "history.expand", label: "Full chart", spokenLabel: "Expand win probability history",
                                            isAvailable: true),
            inspect: nil,
            previous: previousTarget.map {
                FieldHistoryAction10868(id: "history.inspect@\($0)", label: "Previous", spokenLabel: "Previous traded minute", isAvailable: true)
            },
            next: nextTarget.map {
                FieldHistoryAction10868(id: "history.inspect@\($0)", label: "Next", spokenLabel: "Next traded minute", isAvailable: true)
            },
            inspection: inspection)
    }

    // MARK: - Headline

    private static let headlineScope = "kalshi|KXAFLGAME-26SEP260030BRIFRE|winner"

    private static func ref(_ team: Team, scope: String = Tests.headlineScope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "kalshi", marketID: team.ticker, outcomeID: "yes")
    }

    private static func reading(_ label: String, _ text: String, _ detail: String) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail))
    }

    private static func beforeReading(_ team: Team) -> FieldChooserReading10868 {
        reading("Pre-match win chance", figure(baseline(team)), minute(baseline(team).at))
    }

    /// CONSTRUCTED in-play reading: the team's last close at or before the cut.
    private static func cutReading(_ team: Team) -> FieldChooserReading10868 {
        reading("Recorded \(shortClock(cutClose(team).at))", figure(cutClose(team)), minute(cutClose(team).at))
    }

    private static let finalPoints = ["BRI": "96", "FRE": "89"]

    private static func state(_ phase: Phase) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            return FieldHeadlineState10868(figure: "Before match", unit: nil, caption: "Listed start",
                                           detail: clock(listedStart),
                                           spoken: "Before match. Listed start \(clock(listedStart))", progress: nil)
        case .during:
            return FieldHeadlineState10868(figure: "In play", unit: nil, caption: "Score unavailable in this update",
                                           detail: "Chances recorded to \(clock(constructedLiveCut))",
                                           spoken: "In play. Score unavailable in this update.", progress: nil)
        case .final:
            return FieldHeadlineState10868(figure: "Final", unit: nil, caption: "Brisbane won by 7 points",
                                           detail: "Brisbane 96 · Fremantle 89",
                                           spoken: "Final. Brisbane won by 7 points. Brisbane 96, Fremantle 89.", progress: nil)
        }
    }

    private static func headlineCopy(_ phase: Phase) -> FieldHeadlineCopy10868 {
        let eyebrow: String
        switch phase {
        case .before: eyebrow = "AUSTRALIAN FOOTBALL · BEFORE MATCH · SEP 26"
        case .during: eyebrow = "AUSTRALIAN FOOTBALL · IN PLAY · SEP 26"
        case .final: eyebrow = "AUSTRALIAN FOOTBALL · FINAL · SEP 26"
        }
        return FieldHeadlineCopy10868(
            eyebrow: eyebrow, title: "Brisbane Lions vs Fremantle Dockers", graphicLabel: "Teams’ win chances",
            beforeLabel: "Pre-match win chance", recordedLabel: "Recorded", beforeUnavailable: "Pre-match chance unavailable",
            recordedUnavailable: "Current probability unavailable", finishLabel: "Final points",
            finishUnavailable: "Final score not confirmed", empty: "No teams in this update",
            aboutLabel: "About this match", aboutHint: "Opens the timing and source of each figure",
            openHint: "Opens this team’s history")
    }

    private static func catalogue(_ phase: Phase, scope: String = Tests.headlineScope) -> [FieldChooserOriginal10868] {
        teams.map { team in
            FieldChooserOriginal10868(
                ref: ref(team, scope: scope), name: team.short,
                plan: phase == .during ? .comparison(before: beforeReading(team), later: cutReading(team)) : .single(beforeReading(team)),
                preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                movement: nil, clock: nil, result: nil, browseStatus: "Kalshi win chance", accent: team.tint)
        }
    }

    /// The owner's phase-admitted headline. `liveEvidence: false` is the
    /// CONSTRUCTED in-play update with no recorded chance; `supplyingLater` is
    /// the hostile control that hands the in-play reading and the final points
    /// to any phase.
    private static func headline(_ phase: Phase, baseline hasBaseline: Bool = true, liveEvidence: Bool = true,
                                 supplyingLater: Bool = false) -> FieldHeadlineInput10868 {
        let suppliesLater = supplyingLater || (phase == .during && liveEvidence)
        let suppliesFinal = supplyingLater || phase == .final
        var pairs: [FieldMovementPair10868] = []
        var finishes: [FieldFinishPlace10868] = []
        var entries = catalogue(phase)
        if phase == .during && !liveEvidence {
            entries = teams.map { team in
                FieldChooserOriginal10868(
                    ref: ref(team), name: team.short,
                    plan: .comparison(before: beforeReading(team),
                                      later: FieldChooserReading10868(label: "Recorded", value: .missing("Current probability unavailable"))),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: nil, result: nil, browseStatus: "Kalshi win chance", accent: team.tint)
            }
        }
        for team in teams {
            let base = baseline(team)
            pairs.append(FieldMovementPair10868(
                ref: ref(team),
                before: hasBaseline ? FieldMovementObservation10868(probability: Double(base.cents) / 100, reading: beforeReading(team)) : nil,
                later: suppliesLater
                    ? FieldMovementObservation10868(probability: Double(cutClose(team).cents) / 100, reading: cutReading(team)) : nil,
                movement: nil,
                observation: suppliesLater ? pointID(team, cutClose(team).at) : nil))
            if suppliesFinal {
                finishes.append(FieldFinishPlace10868(
                    ref: ref(team), reading: reading("Final points", finalPoints[team.key]!, "Reported final · ESPN match record")))
            }
        }
        return FieldHeadlineInput10868(
            scope: headlineScope, catalogue: entries,
            displayed: teams.map { FieldHeadlineSlot10868(ref: ref($0), name: $0.name, compactName: $0.short, keyShape: $0.shape) },
            pairs: pairs, finishes: finishes, state: state(phase), phase: Model.headlinePhase(phase),
            copy: headlineCopy(phase), unavailableWords: "Team unavailable in this update")
    }

    // MARK: - Chance → result (final)

    private static func chanceCopy() -> HistoricalChanceCopy10868 {
        HistoricalChanceCopy10868(
            eyebrow: "BRISBANE’S CHANCE → RESULT", title: "Brisbane’s chance → result",
            beforeLabel: "Before match", checkpointLabel: "Lowest minute-end chance",
            endpointUnavailable: "Not recorded for this comparison",
            beforeKey: "Outline: last trade before the listed start", checkpointKey: "Filled: a later recorded trade",
            graphicLabel: "Win chances", chanceUnplaced: "Not drawn on this scale", offScale: "Above this scale",
            actualTitle: "ACTUAL RESULT", actualLabel: "Reported final score", actualUnavailable: "Final score not confirmed",
            context: "Each chance is one dated minute close. The score was reported separately.",
            expandLabel: "Open Brisbane’s chance story full size", expandHint: nil,
            detailsLabel: "How to read this story", detailsHint: nil, openHint: "Opens this minute in the history")
    }

    private static func chanceReading(_ kind: HistoricalChanceEndpointKind10868, _ close: Close) -> FieldChooserReading10868 {
        reading(kind == .before ? "Before match" : "Lowest minute-end chance", figure(close), minute(close.at))
    }

    private static var lowClose: Close { closes(brisbane).first { $0.at == lowAt }! }

    /// The owner's final chance-to-result input for Brisbane: the pre-match and
    /// low minute closes with their own keys, and the separately reported actual.
    private static func chance(subject: FieldChooserOriginalRef10868? = nil,
                               checkpointObservation: [HistoricalChanceObservation10868]? = nil,
                               withReadings: Bool = true) -> HistoricalChanceInput10868 {
        let subjectRef = ref(brisbane)
        let base = baseline(brisbane)
        let observations = [
            HistoricalChanceObservation10868(ref: subjectRef, endpoint: .before,
                                             observation: FieldMovementObservation10868(probability: Double(base.cents) / 100,
                                                                                        reading: chanceReading(.before, base)),
                                             key: pointID(brisbane, base.at)),
        ] + (checkpointObservation ?? [
            HistoricalChanceObservation10868(ref: subjectRef, endpoint: .checkpoint,
                                             observation: FieldMovementObservation10868(probability: Double(lowClose.cents) / 100,
                                                                                        reading: chanceReading(.checkpoint, lowClose)),
                                             key: pointID(brisbane, lowAt)),
        ])
        return HistoricalChanceInput10868(
            scope: headlineScope, catalogue: catalogue(.final),
            subject: HistoricalChanceSubject10868(ref: subject ?? subjectRef, name: "Brisbane"),
            readings: withReadings ? [
                HistoricalChanceReading10868(ref: subjectRef, endpoint: .before, reading: chanceReading(.before, base)),
                HistoricalChanceReading10868(ref: subjectRef, endpoint: .checkpoint, reading: chanceReading(.checkpoint, lowClose)),
            ] : [],
            observations: observations,
            actuals: [HistoricalChanceActual10868(
                place: FieldFinishPlace10868(ref: subjectRef, reading: reading("Reported final score", "Brisbane 96–89 Fremantle",
                                                                               "ESPN match record and scoreboard")),
                outcome: "Brisbane won")],
            scale: FieldOutlookScale10868(ceiling: 1, ticks: [
                FieldOutlookTick10868(probability: 0, label: "0%"), FieldOutlookTick10868(probability: 0.5, label: "50%"),
                FieldOutlookTick10868(probability: 1, label: "100%"),
            ], words: "0–100% chance · independent Kalshi minute closes"),
            phase: .final, copy: chanceCopy(), unavailableWords: "Team unavailable in this update")
    }

    // MARK: - Quarter story (final)

    private static func marginWords(_ margin: Int) -> String {
        margin == 0 ? "Level" : (margin > 0 ? "+\(margin)" : "−\(-margin)")
    }

    /// The owner's quarter rows: cumulative scores and Brisbane's margin, as
    /// the owner would supply them (computed here by the test author only).
    private static func quarterRows() -> [AflMatchPeriodRow10868] {
        let ids = ["q1", "half", "q3", "final"]
        let labels = ["Q1", "Half", "Q3", "Final"]
        let scoreLabels = ["After Q1", "Halftime score", "After Q3", "Final score"]
        var b = 0, f = 0
        return (0..<4).map { index in
            b += retainedQuarterPoints.brisbane[index]
            f += retainedQuarterPoints.fremantle[index]
            let margin = b - f
            return AflMatchPeriodRow10868(
                id: ids[index], label: labels[index], lead: Double(margin), leadWords: marginWords(margin),
                leader: margin > 0 ? ref(brisbane) : (margin < 0 ? ref(fremantle) : nil),
                scoreLabel: scoreLabels[index],
                scores: [AflMatchTeamScore10868(ref: ref(brisbane), name: "Brisbane", score: "\(b)"),
                         AflMatchTeamScore10868(ref: ref(fremantle), name: "Fremantle", score: "\(f)")],
                spoken: "\(scoreLabels[index]): Brisbane \(b), Fremantle \(f). Margin \(marginWords(margin)).")
        }
    }

    private static let quarterScale = AussieRulesPointsScale10868(
        lower: -15, upper: 15,
        ticks: [AussieRulesPointsTick10868(value: -10, label: "10 pts"), AussieRulesPointsTick10868(value: 0, label: "Level"),
                AussieRulesPointsTick10868(value: 10, label: "10 pts")],
        label: "Actual margin · points", upperWords: "Brisbane ahead", lowerWords: "Fremantle ahead")

    private static func quarters(rows: [AflMatchPeriodRow10868]? = nil, selected: String? = "final") -> AflMatchPeriodStory10868 {
        AflMatchPeriodStory10868(
            rows: rows ?? quarterRows(), scale: quarterScale, selectedRowID: selected,
            caption: "Brisbane won Q4 34–17, a 17-point swing. Probabilities are dated separately from quarter scores.",
            copy: AflMatchPeriodCopy10868(
                eyebrow: "THE COMEBACK · ACTUAL POINTS", title: "10 down. Won by 7.",
                graphicLabel: "Actual Brisbane margin at each quarter end. Points, not probabilities.",
                rowsEmpty: "Quarter scores unavailable", leadUnavailable: "Margin not reported", offScale: "Beyond this scale",
                selectionPrompt: "Choose a quarter", selectionMissing: "That quarter is not in this update",
                selectHint: "Shows this quarter’s score", expandLabel: "Expand AFL quarter story",
                detailsLabel: "Quarter scores & source"))
    }

    // MARK: - Scoring story (final)

    private static func leadWords(_ margin: Int) -> String {
        margin == 0 ? "Level" : "\(abs(margin)) \(margin > 0 ? "ahead" : "behind")"
    }

    private static func scoringPlays(_ source: [Play] = Tests.plays) -> [AflMatchScoringPlay10868] {
        source.enumerated().map { index, play in
            AflMatchScoringPlay10868(
                id: play.id, lead: Double(play.margin),
                leader: play.margin > 0 ? ref(brisbane) : (play.margin < 0 ? ref(fremantle) : nil),
                mark: play.kind == "Goal" ? .major : .minor,
                period: "Q\(play.quarter)", clock: play.clock, scorer: play.text,
                scores: [AflMatchTeamScore10868(ref: ref(brisbane), name: "Brisbane", score: "\(play.brisbane)"),
                         AflMatchTeamScore10868(ref: ref(fremantle), name: "Fremantle", score: "\(play.fremantle)")],
                leadWords: leadWords(play.margin),
                spoken: "Scoring play \(index + 1) of \(source.count), Q\(play.quarter), \(play.clock), Brisbane \(play.brisbane), Fremantle \(play.fremantle), \(play.text)")
        }
    }

    /// The owner's guides at each quarter's first retained play (found here by the test author).
    private static func guides(_ source: [Play] = Tests.plays) -> [AflMatchScoringGuide10868] {
        (1...4).compactMap { quarter in
            source.first { $0.quarter == quarter }.map { AflMatchScoringGuide10868(playID: $0.id, label: "Q\(quarter)") }
        }
    }

    /// The owner's checkpoints: the low and every later play (elected here by the test author).
    private static func checkpoints() -> [AflMatchScoringCheckpoint10868] {
        let lowIndex = plays.indices.min { plays[$0].margin < plays[$1].margin }!
        return plays[lowIndex...].enumerated().map { offset, play in
            AflMatchScoringCheckpoint10868(
                id: "cp-\(play.id)", playID: play.id,
                label: lowIndex + offset == plays.count - 1 ? "Won by \(play.margin)" : leadWords(play.margin),
                detail: "Q\(play.quarter) · \(play.clock)")
        }
    }

    private static let scoringScale = AussieRulesPointsScale10868(
        lower: -18, upper: 18,
        ticks: [AussieRulesPointsTick10868(value: -18, label: "-18 pts"), AussieRulesPointsTick10868(value: 0, label: "Level"),
                AussieRulesPointsTick10868(value: 18, label: "+18 pts")],
        label: "Brisbane lead · actual points", upperWords: "Brisbane ahead", lowerWords: "Fremantle ahead")

    private static func scoring(plays source: [Play] = Tests.plays, selected: String? = nil,
                                checkpoints marks: [AflMatchScoringCheckpoint10868]? = nil) -> AflMatchScoringStory10868 {
        AflMatchScoringStory10868(
            plays: scoringPlays(source), scale: scoringScale, guides: guides(source), checkpoints: marks ?? checkpoints(),
            selectedPlayID: selected ?? Tests.plays.last!.id, plotHeight: 210, readerPlotHeight: 300,
            copy: AflMatchScoringCopy10868(
                eyebrow: "THE COMEBACK · ACTUAL POINTS", title: "17 down. Four goals. Won.",
                orderLabel: "Scoring plays, in order — not elapsed time",
                graphicLabel: "Actual Brisbane lead across 55 scoring plays in source order, not elapsed time.",
                axisNote: "Points ahead / behind · probabilities have separate clocks",
                playsEmpty: "Scoring history unavailable", selectionPrompt: "Choose a scoring play",
                selectionMissing: "That scoring play is not in this update", selectHint: "Shows this play’s score",
                earlierLabel: "Earlier score", laterLabel: "Later score", checkpointsLabel: "Inspect the four-goal comeback",
                chancesLabel: "Brisbane’s dated chances", periodsLabel: "Quarter-by-quarter summary",
                detailsLabel: "Scoring record & source", expandLabel: "Expand AFL scoring comeback"))
    }

    // MARK: - Page

    private static let report = AussieRulesEventPageSource10868(id: "espn-match-record", label: "ESPN match record",
                                                                hint: "Opens the ESPN match record")

    private static func readerHeader(_ phase: Phase) -> AussieRulesEventPageReaderHeader10868 {
        switch phase {
        case .before: return AussieRulesEventPageReaderHeader10868(title: "Brisbane vs Fremantle", state: "Before match")
        case .during: return AussieRulesEventPageReaderHeader10868(title: "Brisbane vs Fremantle", state: "In play · score unavailable")
        case .final: return AussieRulesEventPageReaderHeader10868(title: "Brisbane vs Fremantle", state: "Final 96–89")
        }
    }

    private static func notice(_ phase: Phase) -> String? {
        switch phase {
        case .before: return "No verified projected score is captured."
        case .during: return "Score unavailable in this update. Recorded chances are not current."
        case .final: return nil
        }
    }

    private static let baselineParagraph = "Before match means the last positive-volume minute ending strictly before the listed Sep 26, 4:30 AM UTC start. Brisbane’s 56% and Fremantle’s 45% were recorded in different minutes. They are independent Kalshi probabilities, not a normalized Bain Luck blend."
    private static let historyParagraph = "Only adjacent traded minutes connect. Gaps remain blank. Minute-end times are not exact trade times. This archive has no current quote and no verified projected score."

    /// The owner's About for the phase: only the facts admitted by then.
    private static func about(_ phase: Phase) -> AussieRulesEventPageAbout10868 {
        let chances = AussieRulesEventPageAboutSection10868(title: "Before-match chances", paragraphs: [baselineParagraph])
        let history = AussieRulesEventPageAboutSection10868(title: "Market history", paragraphs: [historyParagraph])
        switch phase {
        case .before:
            return AussieRulesEventPageAbout10868(title: "About this match", sections: [chances, history])
        case .during:
            return AussieRulesEventPageAbout10868(title: "About this match", sections: [
                chances,
                AussieRulesEventPageAboutSection10868(title: "In-play chances", paragraphs: [
                    "Recorded chances are dated minute closes up to \(clock(constructedLiveCut)), not current probabilities. The score is not available in this update.",
                ]),
                history,
            ])
        case .final:
            return AussieRulesEventPageAbout10868(title: "About this match", sections: [
                chances,
                AussieRulesEventPageAboutSection10868(title: "Actual points", paragraphs: [
                    "ESPN’s match record and scoreboard agree on Brisbane 96–89 Fremantle. Quarter points are 23, 20, 19, 34 versus 22, 21, 29, 17. The margin is Brisbane’s cumulative score minus Fremantle’s: +1, level, −10, +7. A goal is six points; a behind is one.",
                ], source: report),
                AussieRulesEventPageAboutSection10868(title: "Scoring plays", paragraphs: [
                    "The play-by-play record contains 55 scoring plays, ending 96–89. At Q4 21:49 Brisbane trailed 72–89; its last four scoring plays are goals by Cameron, Bailey and Morris twice. Chart spacing counts scoring plays and does not measure elapsed time.",
                ]),
                AussieRulesEventPageAboutSection10868(title: "The low", paragraphs: [
                    "Brisbane’s lowest admitted match-window minute close was 3% at \(clock(lowAt)); the intraminute 1% is not that checkpoint. It is not a verified probability at the end of Q3 or at the decisive goal. Settlement is shown separately from the last recorded probability.",
                ]),
                history,
            ])
        }
    }

    private static func pageCopy(_ phase: Phase) -> AflMatchEventPageCopy10868 {
        AflMatchEventPageCopy10868(
            storiesLabel: "Match stories", storyUnavailable: "This story is not available in this update.",
            headlineUnavailable: "Team chances unavailable for this update", allPropsLabel: "All 2 captured markets",
            heldOriginalUnavailable: "Your selected market is not in this update", backLabel: "Back to match",
            doneLabel: "Done", previousLabel: "Previous card", nextLabel: "Next card",
            historyName: "Win probability history",
            scoringName: phase == .final ? "Four unanswered goals" : "Scoring story",
            periodsName: phase == .final ? "The comeback, quarter by quarter" : "Quarter story")
    }

    private static func stream() -> StoryStreamPresentation10868 {
        let scope = "afl:final:stories"
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: "Match stories",
            cards: [StoryStreamPresentation10868.Card(id: "scoring", name: "Four unanswered goals"),
                    StoryStreamPresentation10868.Card(id: "quarters", name: "The comeback, quarter by quarter")],
            primary: StoryStreamPresentation10868.CardRef(scope: scope, id: "scoring"), companion: nil,
            companionLabel: nil, wide: false, position: "1 of 2", status: nil,
            dwellFraction: nil, playback: nil, previous: nil, next: nil, readerOpen: false)
    }

    private static let storyLinks = [
        AflMatchEventPageStory10868(cardID: "scoring", card: .scoring, reason: "How the four-goal finish unfolded"),
        AflMatchEventPageStory10868(cardID: "quarters", card: .periods, reason: "The margin at each quarter end"),
    ]

    /// The owner's phase-admitted page input. `withFinal: true` is the hostile
    /// control that hands the final stories and chance-to-result to any phase.
    private static func input(_ phase: Phase, headline: FieldHeadlineInput10868? = nil, history: FieldHistoryInput10868? = nil,
                              scoring: AflMatchScoringStory10868? = nil, quarters: AflMatchPeriodStory10868? = nil,
                              chance: HistoricalChanceInput10868? = nil, withFinal: Bool? = nil,
                              stream: StoryStreamPresentation10868? = nil) -> AflMatchEventPageInput10868 {
        let admitsFinal = withFinal ?? (phase == .final)
        return AflMatchEventPageInput10868(
            phase: phase, reader: readerHeader(phase), headline: headline ?? Tests.headline(phase), notice: notice(phase),
            history: history ?? Tests.history(phase), readerPlotHeight: 380,
            scoring: admitsFinal ? (scoring ?? Tests.scoring()) : nil,
            periods: admitsFinal ? (quarters ?? Tests.quarters()) : nil,
            chance: admitsFinal ? (chance ?? Tests.chance()) : nil,
            stream: stream, stories: storyLinks, about: about(phase), copy: pageCopy(phase))
    }

    // MARK: Originals

    private static let originalsScope = "kalshi|KXAFLGAME-26SEP260030BRIFRE|originals"

    private static func identity(_ team: Team) -> Details.Identity {
        Details.Identity(source: "kalshi", market: team.ticker, side: "yes")
    }

    private static func selection(_ team: Team, scope: String = Tests.originalsScope) -> Details.Selection {
        Details.Selection(scope: scope, identity: identity(team))
    }

    /// Each contract at its phase: the pre-match reading; during play the
    /// CONSTRUCTED cut's recorded reading; at the final the contract
    /// settlement, which is not the reported score. Rules verbatim.
    private static func original(_ team: Team, _ phase: Phase) -> Details.Original {
        let base = baseline(team)
        let pregame = Details.Reading.value(figure(base), placement: Double(base.cents) / 100, provenance: minute(base.at))
        let mode: Details.Mode
        var later: Details.Reading?
        var grade: Details.Grade?
        switch phase {
        case .before:
            mode = .pregame
        case .during:
            mode = .comparison(.recorded)
            later = .value(figure(cutClose(team)), placement: Double(cutClose(team).cents) / 100, provenance: minute(cutClose(team).at))
        case .final:
            mode = .result
            grade = Details.Grade(words: team.contractYes ? "Resolved Yes" : "Resolved No",
                                  provenance: "Settled \(clock(1_790_407_906)) · Kalshi")
        }
        return Details.Original(
            identity: identity(team), title: retainedTitle, outcome: team.name, mode: mode, pregame: pregame, later: later,
            grade: grade,
            about: Details.About(source: "Kalshi", rules: .verified([retainedRulesPrimary[team.key]!, retainedRulesSecondary]),
                                 provenance: [Details.Row(label: "Kalshi market", value: team.ticker)], historicalQuote: nil))
    }

    private static let labels: [Details.Identity: String] = [
        Tests.identity(Tests.brisbane): "Brisbane Lions to win",
        Tests.identity(Tests.fremantle): "Fremantle Dockers to win",
    ]

    private static func originals(_ phase: Phase, list: [Details.Original]? = nil,
                                  selection held: Details.Selection? = Tests.selection(Tests.brisbane)) -> AussieRulesEventPageOriginals10868 {
        AussieRulesEventPageOriginals10868(
            catalogue: Details.Catalogue(scope: originalsScope, originals: list ?? teams.map { original($0, phase) }),
            selection: held, labels: labels, heading: "2 captured markets", context: "Kalshi · original winner contracts",
            emptyWords: "No markets supplied in this update", unavailableChoice: "Market unavailable", tint: brisbane.tint)
    }

    // MARK: - Reachable text

    /// Every string a reader can reach from one input through the models the
    /// views draw from: the reader heading, notice and controls; the headline
    /// as drawn and spoken; the page and full-size history; every scoring play,
    /// guide, checkpoint and chance link (each play is reachable by selection);
    /// every quarter row and the chance-to-result leaf; the stream; the About
    /// and its sources; and, with `originals`, every choice, catalogue card,
    /// each original's Details and spoken Details.
    private static func reachableText(_ input: AflMatchEventPageInput10868,
                                      originals: AussieRulesEventPageOriginals10868?) -> [String] {
        let model = Model(input)
        var texts = [input.reader.title, input.copy.storiesLabel, input.copy.backLabel, input.copy.doneLabel]
        texts += [input.reader.state, input.notice, input.copy.allPropsLabel].compactMap { $0 }
        for card in model.mountedCards {
            for offset in [-1, 1] {
                if let neighbour = model.neighbour(of: card, offset: offset) {
                    texts += [offset < 0 ? input.copy.previousLabel : input.copy.nextLabel, model.cardName(neighbour)]
                }
            }
        }
        if let headline = model.headline {
            let leaf = FieldHeadlineModel10868(headline)
            texts += [leaf.eyebrow, leaf.title, leaf.stateSummary, leaf.aboutLabel(canAbout: true), headline.copy.openHint]
                .compactMap { $0 }
            texts += [leaf.aboutHint(canAbout: true), headline.copy.graphicLabel]
            if let state = leaf.state {
                texts += [state.figure, state.unit, state.caption, state.detail, state.spoken].compactMap { $0 }
            }
            for competitor in leaf.competitors {
                texts += [competitor.slot.name, leaf.competitorSummary(competitor)] + [competitor.slot.compactName].compactMap { $0 }
                for endpoint in competitor.metrics {
                    texts.append(FieldChaseModel10868.label(endpoint))
                    texts += [FieldChaseModel10868.figure(endpoint), FieldChaseModel10868.words(endpoint),
                              FieldChaseModel10868.detail(endpoint)].compactMap { $0 }
                }
            }
            for original in headline.catalogue {
                texts += [original.name, original.browseStatus, original.preview.absence].compactMap { $0 }
            }
        } else {
            texts.append(input.copy.headlineUnavailable)
        }
        for history in [input.history, model.readerHistory] {
            texts += historyText(history)
        }
        for scoring in [model.scoringModel, model.readerScoringModel].compactMap({ $0 }) {
            texts += scoringText(scoring)
        }
        if let quarters = model.periodModel {
            texts += quarterText(quarters)
        }
        if let chance = model.chance {
            texts += chanceText(HistoricalChanceModel10868(chance))
        }
        if let stream = input.stream {
            texts.append(stream.heading)
            texts += [stream.eyebrow, stream.companionLabel, stream.position, stream.status, stream.pending,
                      stream.nextHint, stream.basis].compactMap { $0 }
            for card in stream.cards {
                texts.append(card.name)
                if let link = model.storyLink(card.id) {
                    texts += [link.reason].compactMap { $0 }
                } else {
                    texts.append(input.copy.storyUnavailable)
                }
            }
        }
        if let about = model.about {
            texts.append(about.title)
            for section in about.sections {
                texts += [section.title] + section.paragraphs
                if let source = section.source {
                    texts += [source.id, source.label] + [source.hint].compactMap { $0 }
                }
            }
        }
        if let originals {
            texts += originalsText(originals)
            if Model.heldOriginalIsUnavailable(originals) {
                texts.append(input.copy.heldOriginalUnavailable)
            }
        }
        return texts
    }

    private static func historyText(_ history: FieldHistoryInput10868) -> [String] {
        typealias Readout = FieldHistoryGeometry10868
        var texts = [history.title, history.summary, history.unboundReadingWords] + history.notes
        texts += [history.caption, history.markKey.hollow, history.markKey.filled, history.comparisonExplanation,
                  history.plotUnavailableWords, history.windows?.groupLabel, Readout.probabilityRangeExplanation(history),
                  Readout.selectionWords(history), history.plotAbsence?.title, history.plotAbsence?.words].compactMap { $0 }
        texts += (history.yTicks + history.xTicks).flatMap(\.lines)
        texts += history.guides.map(\.label) + history.breaks.map(\.mark)
        texts += Readout.actions(history).flatMap { [$0.label, $0.spokenLabel].compactMap { $0 } }
        for series in history.series {
            texts.append(series.name)
            texts += [series.absentWords].compactMap { $0 }
            for slot in Readout.readoutSlots(series, in: history) + Readout.selectedSlots(series, in: history) {
                texts += [slot.label, Readout.spokenSlot(slot)]
                switch slot.display {
                case .figure(let figure, let provenance): texts += [figure, provenance]
                case .words(let words): texts.append(words)
                }
            }
        }
        if let inspection = history.inspection {
            texts += [inspection.caption] + [inspection.note].compactMap { $0 }
            for choice in inspection.choices {
                texts += choice.lines + [choice.spoken]
            }
            for selection in inspection.selections.values {
                switch selection {
                case .point(_, let spoken): texts.append(spoken)
                case .absent(let words): texts.append(words)
                }
            }
        }
        texts.append(Readout.spokenValue(history))
        return texts
    }

    private static func scoringText(_ model: AflMatchScoringModel10868) -> [String] {
        let copy = model.copy
        var texts = [copy.title, copy.orderLabel, copy.graphicLabel, copy.playsEmpty, copy.selectionMissing,
                     copy.earlierLabel, copy.laterLabel, copy.checkpointsLabel, copy.expandLabel]
        texts += [copy.eyebrow, copy.axisNote, copy.selectionPrompt, copy.selectHint, copy.chancesLabel, copy.periodsLabel,
                  copy.detailsLabel].compactMap { $0 }
        let scale = model.story.scale
        texts += [scale.label] + [scale.upperWords, scale.lowerWords].compactMap { $0 } + model.ticks.map { $0.label }
        for play in model.story.plays {
            texts += [play.period, play.clock, "\(play.period) · \(play.clock)", play.scorer, play.leadWords, play.spoken]
            texts += play.scores.flatMap { [$0.name, $0.score] }
            // The drawn score line: each team's score with the dash between.
            texts.append(play.scores.map(\.score).joined(separator: "–"))
        }
        texts += model.guides.map(\.label)
        for placed in model.checkpoints {
            texts += [placed.checkpoint.label] + [placed.checkpoint.detail].compactMap { $0 }
        }
        if let chance = model.chanceModel {
            texts += [chance.subjectName, chance.subjectWords].compactMap { $0 }
            for side in chance.sides {
                texts += [FieldChaseModel10868.label(side.endpoint), chance.endpointSummary(side)]
                texts += [FieldChaseModel10868.figure(side.endpoint), FieldChaseModel10868.words(side.endpoint),
                          FieldChaseModel10868.detail(side.endpoint)].compactMap { $0 }
            }
        }
        return texts
    }

    private static func quarterText(_ model: AflMatchPeriodModel10868) -> [String] {
        let copy = model.copy
        var texts = [copy.title, copy.graphicLabel, copy.rowsEmpty, copy.selectionMissing, copy.expandLabel]
        texts += [copy.eyebrow, copy.selectionPrompt, copy.selectHint, copy.detailsLabel, model.story.caption].compactMap { $0 }
        let scale = model.story.scale
        texts += [scale.label] + [scale.upperWords, scale.lowerWords].compactMap { $0 } + model.ticks.map { $0.label }
        for bar in model.bars {
            texts += [bar.row.label, bar.row.leadWords, bar.row.scoreLabel, bar.row.spoken]
            texts += bar.row.scores.flatMap { [$0.name, $0.score] } + [model.barWords(bar)].compactMap { $0 }
            texts.append(bar.row.scores.map(\.score).joined(separator: "–"))
        }
        return texts
    }

    private static func chanceText(_ model: HistoricalChanceModel10868) -> [String] {
        guard model.isShown else { return [] }
        let copy = model.input.copy
        var texts = [model.eyebrow, model.title, model.context, model.subjectName, model.subjectWords, model.outcome].compactMap { $0 }
        texts += [copy.beforeKey, copy.checkpointKey, copy.graphicLabel, copy.actualTitle, model.chancesSummary,
                  model.actualSummary, model.summary]
        for side in model.sides {
            texts += [FieldChaseModel10868.label(side.endpoint), model.endpointSummary(side)]
            texts += [FieldChaseModel10868.figure(side.endpoint), FieldChaseModel10868.words(side.endpoint),
                      FieldChaseModel10868.detail(side.endpoint), model.barWords(side)].compactMap { $0 }
        }
        if model.showsPlot {
            texts += [model.input.scale.words] + model.ticks.map(\.label)
        }
        if let actual = model.actual {
            texts.append(FieldChaseModel10868.label(actual))
            texts += [FieldChaseModel10868.figure(actual), FieldChaseModel10868.words(actual),
                      FieldChaseModel10868.detail(actual)].compactMap { $0 }
        }
        return texts
    }

    private static func originalsText(_ originals: AussieRulesEventPageOriginals10868) -> [String] {
        var texts = [originals.heading, originals.emptyWords, originals.unavailableChoice] + [originals.context].compactMap { $0 }
        for choice in OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                                        labels: originals.labels, unavailableChoice: originals.unavailableChoice) {
            texts += [choice.label, OriginalMarketChooser9483.spoken(choice)] + [choice.status].compactMap { $0 }
        }
        let cards = OriginalMarketCatalogue9483.cards(catalogue: originals.catalogue, selection: originals.selection,
                                                      labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        texts += cards.map { OriginalMarketCatalogue9483.spoken($0) }
        var contents = cards.compactMap(\.content)
        let held = Details.content(catalogue: originals.catalogue, selection: originals.selection)
        contents += [held].compactMap { $0 }
        texts.append(Details.spoken(held))
        for original in originals.catalogue?.originals ?? [] {
            let own = Details.content(catalogue: originals.catalogue,
                                      selection: Details.Selection(scope: originals.catalogue?.scope ?? "", identity: original.identity))
            texts.append(Details.spoken(own))
            contents += [own].compactMap { $0 }
        }
        for content in contents {
            texts += [content.title, content.outcome]
            for reading in content.readings {
                texts += [reading.label, reading.text] + [reading.provenance].compactMap { $0 }
            }
            if let result = content.result {
                texts += [result.words] + [result.provenance].compactMap { $0 }
            }
            texts += content.about.flatMap { [$0.label, $0.value] }
            switch content.rules {
            case .verified(let paragraphs): texts += paragraphs
            case .unavailable(let words): texts.append(words)
            case .omitted: break
            }
        }
        return texts
    }

    // MARK: Phase-text patterns

    /// Every score pair the final shows as a pair: each play's score (which
    /// includes every quarter-end cumulative score) and the last quarter's own points.
    private static var scorePairs: [String] {
        let lastQuarter = "\(retainedQuarterPoints.brisbane[3])–\(retainedQuarterPoints.fremantle[3])"
        return Array(Set(plays.map { "\($0.brisbane)–\($0.fremantle)" } + [lastQuarter])).sorted()
    }

    private static var scorerSurnames: [String] {
        Array(Set(plays.filter { $0.text != "Rushed" }.compactMap { play -> String? in
            let words = play.text.split(separator: " ")
            guard words.count >= 3 else { return nil }
            return words.dropFirst().dropLast().joined(separator: " ")
        })).sorted()
    }

    /// A score pair as a whole token: never inside a longer number, a clock or a percentage.
    private static func pairPattern(_ pair: String) -> String {
        let sides = pair.split(separator: "–")
        return "(^|[^0-9.:])\(sides[0])\\s*[–-]\\s*\(sides[1])([^0-9%:]|$)"
    }

    /// Final facts by meaning, all reachable at the final (the positive control).
    private static var finalPositivePatterns: [String] {
        scorePairs.map(pairPattern) + scorerSurnames.map { "\\b\($0)\\b" } + [
            "(^|[^0-9.:])96([^0-9%:]|$)", "(^|[^0-9.:])89([^0-9%:]|$)",
            "\\bgoals?\\b", "\\bbehinds?\\b", "\\brushed\\b", "\\bfinal\\b", "\\bwon\\b", "\\bresolved\\b",
            "\\bsettle(d|ment)\\b", "(^|[^0-9.])99%", "(^|[^0-9.])1%", "(^|[^0-9.])3%", "\\bQ[1-4]\\b", "\\bhalftime\\b",
            "\\bESPN\\b", "match record", "scoreboard", "play-by-play", "\\bpoints\\b", "\\bpts\\b", "\\bahead\\b",
            "\\bcomeback\\b", "\\bunanswered\\b", "\\blowest\\b", "intraminute",
            NSRegularExpression.escapedPattern(for: clock(lowAt)),
            NSRegularExpression.escapedPattern(for: clock(lastClose(brisbane).at)),
            NSRegularExpression.escapedPattern(for: clock(lastClose(fremantle).at)),
        ]
    }

    /// Clock words of every retained close strictly after `instant`.
    private static func clocksAfter(_ instant: Int) -> [String] {
        Array(Set(closes.filter { $0.at > instant }.map { NSRegularExpression.escapedPattern(for: clock($0.at)) })).sorted()
    }

    /// What a before page must not reach: every final fact and every clock after the listed start.
    private static var beforeForbidden: [String] { finalPositivePatterns + clocksAfter(listedStart) + ["\\bin play\\b"] }

    /// What a during page must not reach: every final fact and every clock after the CONSTRUCTED cut.
    private static var duringForbidden: [String] { finalPositivePatterns + clocksAfter(constructedLiveCut) }

    private static func leaks(_ texts: [String], _ patterns: [String]) -> [String] {
        patterns.flatMap { pattern in
            texts.filter { $0.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil }
                .map { "\(pattern) ⟵ \($0)" }
        }
    }

    private static func reaches(_ texts: [String], _ pattern: String) -> Bool {
        texts.contains { $0.range(of: pattern, options: [.regularExpression, .caseInsensitive]) != nil }
    }

    // MARK: - Action payloads

    /// Every payload an action reachable from this input hands its owner,
    /// through the page's own wrappers: headline opens, history actions and
    /// inspection choices (page and full size), original selections and
    /// Details history, play, quarter, checkpoint and chance actions.
    private static func payloads(_ input: AflMatchEventPageInput10868,
                                 originals: AussieRulesEventPageOriginals10868?) -> [String] {
        var log: [String] = []
        func page(_ mode: AflMatchEventPageMode10868) -> Page {
            Page(input: input, mode: mode, originals: originals,
                 onOriginalSelect: { log.append("original:\($0.scope)|\($0.identity.market)") },
                 onHeadlineOpen: { log.append("headline:\($0.ref.marketID)@\($0.observation ?? "none")") },
                 onHistoryAction: { log.append("history.action:\($0)") },
                 onHistoryInspectionChoice: { log.append("history.choice:\($0)") },
                 onPlaySelect: { log.append("play:\($0)") },
                 onPeriodSelect: { log.append("quarter:\($0)") },
                 onChanceOpen: { log.append("chance:\($0.ref.marketID)@\($0.observation ?? "none")") })
        }
        let main = page(.page)
        if let headline = main.headlineContent() {
            let leaf = FieldHeadlineModel10868(headline.input)
            for competitor in leaf.competitors {
                if let opening = leaf.openAction(competitor, canOpen: true) { headline.onOpen?(opening) }
            }
        }
        for history in [main.historyContent(reader: false), page(.reader(.history)).historyContent(reader: true)] {
            for action in FieldHistoryGeometry10868.actions(history.input) where action.isAvailable {
                history.onAction?(action.id)
            }
            for choice in history.input.inspection?.choices ?? [] {
                history.onInspectionChoice?(choice.id)
            }
        }
        if let originals, let chooser = main.chooserContent() {
            for choice in OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                                            labels: originals.labels, unavailableChoice: originals.unavailableChoice) {
                if let selection = choice.selection { chooser.onSelect?(selection) }
            }
        }
        if let card = main.pageScoringContent() {
            for placement in card.model.placements {
                if let id = placement.selectableID { card.onSelect?(id) }
            }
            for placed in card.model.checkpoints {
                if let id = placed.playID { card.onSelect?(id) }
            }
            if let chance = card.model.chanceModel {
                for side in chance.sides {
                    if let opening = chance.openAction(side, canOpen: true) { card.onChanceOpen?(opening) }
                }
            }
        }
        if let card = main.pagePeriodsContent() {
            for bar in card.model.bars {
                if let id = bar.selectableID { card.onSelect?(id) }
            }
            if let chance = card.chance {
                let model = HistoricalChanceModel10868(chance)
                for side in model.sides {
                    if let opening = model.openAction(side, canOpen: true) { card.onChanceOpen?(opening) }
                }
            }
        }
        return log
    }

    /// Every epoch a payload carries.
    private static func epochs(_ payload: String) -> [Int] {
        guard let regex = try? NSRegularExpression(pattern: "@([0-9]{10})") else { return [] }
        let range = NSRange(payload.startIndex..., in: payload)
        return regex.matches(in: payload, range: range).compactMap { match in
            Range(match.range(at: 1), in: payload).flatMap { Int(payload[$0]) }
        }
    }

    /// Payloads carrying a key or time later than the phase admits.
    private static func payloadLeaks(_ payloads: [String], admittedThrough bound: Int) -> [String] {
        payloads.filter { epochs($0).contains { $0 > bound } }
    }

    private static func bound(_ phase: Phase) -> Int {
        switch phase {
        case .before: return listedStart - 1
        case .during: return constructedLiveCut
        case .final: return max(lastClose(brisbane).at, lastClose(fremantle).at)
        }
    }

    // MARK: - Shown words helpers

    private static func shown(_ endpoint: FieldMovementEndpoint10868) -> String {
        let label = FieldChaseModel10868.label(endpoint)
        if let figure = FieldChaseModel10868.figure(endpoint) { return "\(label)=\(figure)" }
        return "\(label): \(FieldChaseModel10868.words(endpoint) ?? "")"
    }

    private static func metrics(_ headline: FieldHeadlineInput10868?) -> [[String]] {
        guard let headline else { return [] }
        return FieldHeadlineModel10868(headline).competitors.map { $0.metrics.map { Tests.shown($0) } }
    }

    private static func words(_ intent: AflMatchReaderIntent10868) -> String {
        switch intent {
        case .previous(let card): return "previous:\(card.rawValue)"
        case .next(let card): return "next:\(card.rawValue)"
        case .open(let card): return "open:\(card.rawValue)"
        case .details(let card): return "details:\(card.rawValue)"
        case .back: return "back"
        case .done: return "done"
        }
    }

    private static func sha256(_ text: String) -> String {
        SHA256.hash(data: Data(text.utf8)).map { String(format: "%02x", $0) }.joined()
    }

    // MARK: - Phases

    func testEachPhaseMountsOnlyItsOwnLeavesAndHidesEveryLaterFact() throws {
        let before = Model(Self.input(.before))
        XCTAssertEqual(Self.metrics(before.headline), [["Pre-match win chance=56%"], ["Pre-match win chance=45%"]])
        XCTAssertNil(before.scoring)
        XCTAssertNil(before.periods)
        XCTAssertNil(before.chance)
        XCTAssertEqual(before.mountedCards, [.history])
        XCTAssertTrue(Self.input(.before).history.series.allSatisfy { series in
            series.runs.flatMap(\.points).allSatisfy { $0.x < 0 && $0.style == .hollow }
        }, "the before history holds only closes strictly before the listed start")

        let during = Model(Self.input(.during))
        XCTAssertEqual(Self.metrics(during.headline), [
            ["Pre-match win chance=56%", "Recorded 5:00 AM UTC=51%"],
            ["Pre-match win chance=45%", "Recorded 5:00 AM UTC=57%"],
        ], "CONSTRUCTED in-play readings, each with its own recorded clock")
        XCTAssertNil(during.scoring)
        XCTAssertNil(during.periods)
        XCTAssertNil(during.chance)
        XCTAssertEqual(during.mountedCards, [.history])
        XCTAssertEqual(Self.input(.during).history.series.flatMap { $0.runs.flatMap(\.points) }.map(\.x).max(),
                       Double(Self.constructedLiveCut - Self.listedStart))

        let finished = Model(Self.input(.final))
        XCTAssertEqual(Self.metrics(finished.headline), [
            ["Pre-match win chance=56%", "Final points=96"], ["Pre-match win chance=45%", "Final points=89"],
        ])
        XCTAssertNotNil(finished.scoring)
        XCTAssertNotNil(finished.periods)
        XCTAssertNotNil(finished.chance)
        XCTAssertEqual(finished.mountedCards, [.history, .scoring, .periods])

        // Hostile controls: final stories, chance-to-result and later headline
        // readings handed to earlier phases are never mounted or shown.
        for phase in [Phase.before, .during] {
            let hostile = Model(Self.input(phase, headline: Self.headline(phase, supplyingLater: true), withFinal: true))
            XCTAssertNotNil(hostile.input.scoring)
            XCTAssertNil(hostile.scoring)
            XCTAssertNil(hostile.periods)
            XCTAssertNil(hostile.chance)
            XCTAssertNil(hostile.scoringModel)
            XCTAssertNil(hostile.readerScoringModel)
            XCTAssertEqual(hostile.mountedCards, [.history])
            XCTAssertFalse(Self.metrics(hostile.headline).flatMap { $0 }.contains { $0.hasPrefix("Final points") })
            let page = Page(input: hostile.input, mode: .reader(.scoring))
            XCTAssertNil(page.readerScoringContent())
            XCTAssertNil(Page(input: hostile.input).pagePeriodsContent())
        }
        // A headline from another phase is not coerced.
        XCTAssertNil(Model(Self.input(.final, headline: Self.headline(.before))).headline)
    }

    func testBothNamedChancesStayIndependentlyTimedAndEquallyReadable() throws {
        let brisbane = Self.baseline(Self.brisbane), fremantle = Self.baseline(Self.fremantle)
        XCTAssertEqual([brisbane.at, brisbane.cents], [1_790_396_940, 56])
        XCTAssertEqual([fremantle.at, fremantle.cents], [1_790_396_880, 45])
        XCTAssertEqual(brisbane.cents + fremantle.cents, 101, "independent closes: never normalized or complemented")
        XCTAssertNotEqual(brisbane.at, fremantle.at)

        let headline = try XCTUnwrap(Model(Self.input(.before)).headline)
        let leaf = FieldHeadlineModel10868(headline)
        XCTAssertEqual(leaf.competitors.map { leaf.competitorSummary($0) }, [
            "Pre-match win chance: 56%, Minute ending Sep 26, 4:29 AM UTC · Kalshi",
            "Pre-match win chance: 45%, Minute ending Sep 26, 4:28 AM UTC · Kalshi",
        ], "each named team's chance keeps its own minute")
        XCTAssertEqual(leaf.competitors.map(\.slot.name), ["Brisbane Lions", "Fremantle Dockers"])
        // Both through the same leaf at the same size; the history keeps each
        // team's own baseline observation.
        let history = Self.input(.before).history
        XCTAssertEqual(history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: history).map(\.display) }, [
            [.figure("56%", provenance: Self.minute(1_790_396_940))],
            [.figure("45%", provenance: Self.minute(1_790_396_880))],
        ])
        // No page text calls them a blend or a simultaneous pair.
        let texts = Self.reachableText(Self.input(.final), originals: Self.originals(.final))
        XCTAssertFalse(texts.contains { $0.contains("blend") && !$0.contains("not a normalized Bain Luck blend") })
        XCTAssertFalse(Self.reaches(texts, "\\b(simultaneous|combined|normalized)\\b(?! Bain Luck blend)"))
    }

    // MARK: - Retained history and the low

    func testTheRetainedHistoryKeepsAll553SparseMinuteClosesWithNoSyntheticEndpoint() {
        XCTAssertEqual(Self.closes.count, 553)
        XCTAssertEqual(Self.closes(Self.brisbane).count, 271)
        XCTAssertEqual(Self.closes(Self.fremantle).count, 282)
        let history = Self.history(.final)
        let points = history.series.map { $0.runs.flatMap(\.points) }
        XCTAssertEqual(points.map(\.count), [271, 282])
        XCTAssertEqual(points.flatMap { $0 }.count, 553)
        // Only adjacent traded minutes connect; every gap starts a new run.
        for series in history.series {
            for run in series.runs {
                XCTAssertTrue(zip(run.points, run.points.dropFirst()).allSatisfy { $1.x - $0.x == 60 })
            }
            for (earlier, later) in zip(series.runs, series.runs.dropFirst()) {
                XCTAssertGreaterThan(later.points[0].x - earlier.points[earlier.points.count - 1].x, 60)
            }
        }
        XCTAssertGreaterThan(history.series.map(\.runs.count).reduce(0, +), 2, "sparse segments, not one line")
        // No synthetic settled 0/100 endpoint: the last points are the last closes.
        XCTAssertFalse(points.flatMap { $0 }.contains { $0.probability == 0 || $0.probability == 1 })
        XCTAssertEqual(points[0].last.map { [$0.x, $0.probability] }, [Double(1_790_407_440 - Self.listedStart), 0.99])
        XCTAssertEqual(points[1].last.map { [$0.x, $0.probability] }, [Double(1_790_407_020 - Self.listedStart), 0.01])
        XCTAssertEqual(history.domain.upper, Double(1_790_407_440 - Self.listedStart))
        XCTAssertEqual(history.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: history).map(\.display) }, [
            [.figure("56%", provenance: Self.minute(1_790_396_940)), .figure("99%", provenance: Self.minute(1_790_407_440))],
            [.figure("45%", provenance: Self.minute(1_790_396_880)), .figure("1%", provenance: Self.minute(1_790_407_020))],
        ])
        // The full-size history is the same input, every point and run unchanged.
        let page = Model(Self.input(.final))
        XCTAssertEqual(page.readerHistory.series, page.input.history.series)
        XCTAssertNil(page.readerHistory.expand)
        XCTAssertEqual(page.readerHistory.plotHeight, 380)
    }

    func testTheLowIsTheThreePercentMinuteCloseNotTheIntraminuteOnePercent() throws {
        XCTAssertEqual(Self.retainedLowCandle.close, "0.0300")
        XCTAssertEqual(Self.retainedLowCandle.low, "0.0100", "the intraminute low is retained and is not the checkpoint")
        let matchWindow = Self.closes(Self.brisbane).filter { $0.at >= Self.listedStart }
        XCTAssertEqual(matchWindow.min { $0.cents < $1.cents }.map { [$0.at, $0.cents] }, [Self.lowAt, 3])
        XCTAssertFalse(Self.closes(Self.brisbane).contains { $0.cents == 1 }, "no Brisbane minute closed at 1%")

        let chance = HistoricalChanceModel10868(Self.chance())
        XCTAssertEqual(chance.sides.map { Self.shown($0.endpoint) }, ["Before match=56%", "Lowest minute-end chance=3%"])
        XCTAssertEqual(chance.sides.map(\.key), [Self.pointID(Self.brisbane, 1_790_396_940), Self.pointID(Self.brisbane, Self.lowAt)])
        XCTAssertEqual(chance.sides.compactMap { FieldChaseModel10868.detail($0.endpoint) },
                       [Self.minute(1_790_396_940), Self.minute(Self.lowAt)])
        // Inspecting the low minute shows its close, never the intraminute low.
        let inspected = Self.history(.final, inspecting: Self.lowAt)
        XCTAssertEqual(FieldHistoryGeometry10868.inspectedDisplay(inspected.series[0], in: inspected),
                       .figure("3%", provenance: Self.minute(Self.lowAt)))
        // No scoring play or quarter carries a chance: the low is not at a goal
        // or the Q3 end.
        let scoring = try XCTUnwrap(Model(Self.input(.final)).scoringModel)
        XCTAssertFalse(Self.reaches(scoring.story.plays.flatMap { [$0.spoken, $0.leadWords, $0.scorer] }, "%"))
        let quarters = try XCTUnwrap(Model(Self.input(.final)).periodModel)
        XCTAssertFalse(Self.reaches(quarters.story.rows.flatMap { [$0.spoken, $0.leadWords] }, "%"))
    }

    // MARK: - Actual points

    func testFourQuartersCarryExactPointsCumulativeScoresAndSignedMargins() throws {
        let model = try XCTUnwrap(Model(Self.input(.final)).periodModel)
        XCTAssertEqual(model.story.rows.map { $0.scores.map(\.score) }, [["23", "22"], ["43", "43"], ["62", "72"], ["96", "89"]])
        XCTAssertEqual(model.story.rows.map(\.lead), [1, 0, -10, 7])
        XCTAssertEqual(model.story.rows.map(\.leadWords), ["+1", "Level", "−10", "+7"])
        XCTAssertEqual(Self.retainedQuarterPoints.brisbane[3] - Self.retainedQuarterPoints.fremantle[3], 17)
        XCTAssertEqual(model.story.caption, "Brisbane won Q4 34–17, a 17-point swing. Probabilities are dated separately from quarter scores.")
        // Four bars on one signed axis with a neutral zero.
        XCTAssertEqual(model.bars.map(\.plan), [
            .bar(zero: 0.5, end: 16.0 / 30.0), .level(zero: 0.5), .bar(zero: 0.5, end: 5.0 / 30.0), .bar(zero: 0.5, end: 22.0 / 30.0),
        ])
        XCTAssertEqual(model.zero, 0.5)
        XCTAssertEqual(model.ticks.map { $0.label }, ["10 pts", "Level", "10 pts"])
        XCTAssertEqual(model.bars.map(\.style.accent), [Self.brisbane.tint, nil, Self.fremantle.tint, Self.brisbane.tint])
        XCTAssertEqual(model.bars.map(\.isSelected), [false, false, false, true])
        guard case .row(let held, let index) = model.selection else { return XCTFail("the held quarter shows") }
        XCTAssertEqual([held.scoreLabel, "\(index)"], ["Final score", "3"])
        // An off-scale or missing margin draws no bar and keeps its words.
        var rows = Self.quarterRows()
        rows[2] = AflMatchPeriodRow10868(id: "q3", label: "Q3", lead: -40, leadWords: "−40", leader: Self.ref(Self.fremantle),
                                          scoreLabel: "After Q3", scores: rows[2].scores, spoken: rows[2].spoken)
        rows[3] = AflMatchPeriodRow10868(id: "final", label: "Final", lead: nil, leadWords: "—", leader: nil,
                                          scoreLabel: "Final score", scores: rows[3].scores, spoken: rows[3].spoken)
        let odd = AflMatchPeriodModel10868(story: Self.quarters(rows: rows), headline: Self.headline(.final))
        XCTAssertEqual(odd.bars.map { odd.barWords($0) }, [nil, nil, "Beyond this scale", "Margin not reported"])
    }

    func testFiftyFivePlaysKeepTheSuppliedOrderAndTheFourGoalRun() throws {
        let model = try XCTUnwrap(Model(Self.input(.final)).scoringModel)
        let plays = model.story.plays
        XCTAssertEqual(plays.count, 55)
        XCTAssertEqual(plays.map(\.id), Self.plays.map(\.id), "exact supplied order")
        XCTAssertEqual([plays[0].period, plays[0].clock, plays[0].scorer, plays[0].scores.map(\.score).joined(separator: "–")],
                       ["Q1", "2:43", "P. Voss Behind", "0–1"])
        XCTAssertEqual(plays[0].leader, Self.ref(Self.fremantle))
        XCTAssertEqual([plays[54].period, plays[54].clock, plays[54].scorer, plays[54].scores.map(\.score).joined(separator: "–")],
                       ["Q4", "30:02", "L. Morris Goal", "96–89"])
        XCTAssertEqual([plays[50].period, plays[50].clock, plays[50].scores.map(\.score).joined(separator: "–"), plays[50].leadWords],
                       ["Q4", "21:49", "72–89", "17 behind"])
        XCTAssertEqual(plays[51...].map(\.scorer), ["C. Cameron Goal", "Z. Bailey Goal", "L. Morris Goal", "L. Morris Goal"])
        XCTAssertTrue(Self.plays[51...].allSatisfy { $0.team == "BRI" && $0.kind == "Goal" })
        XCTAssertEqual(Self.plays[54].margin - Self.plays[50].margin, 24)
        XCTAssertEqual(plays[51...].map(\.mark), [.major, .major, .major, .major])
        // Quarter-first-play guides at their own plays' order positions.
        XCTAssertEqual(model.guides, [
            AflMatchPlacedGuide10868(x: 0, label: "Q1"), AflMatchPlacedGuide10868(x: 15.0 / 54.0, label: "Q2"),
            AflMatchPlacedGuide10868(x: 26.0 / 54.0, label: "Q3"), AflMatchPlacedGuide10868(x: 39.0 / 54.0, label: "Q4"),
        ])
        // The owner's checkpoints: the low, then the four goals.
        XCTAssertEqual(model.checkpoints.map(\.checkpoint.label), ["17 behind", "11 behind", "5 behind", "1 ahead", "Won by 7"])
        XCTAssertEqual(model.checkpoints.map(\.playID), Self.plays[50...].map { Optional($0.id) })
        XCTAssertEqual(model.checkpoints.map(\.isSelected), [false, false, false, false, true])
        guard case .row(let held, let index) = model.selection else { return XCTFail("the held play shows") }
        XCTAssertEqual([held.id, "\(index)"], [Self.plays[54].id, "54"])
        XCTAssertEqual(model.earlierID, Self.plays[53].id)
        XCTAssertNil(model.laterID)
    }

    func testTheStepPlotUsesPlayOrderNeverTimeAndBreaksAtUnplaceablePlays() throws {
        XCTAssertEqual(AflMatchScoringGeometry10868.x(index: 0, count: 55), 0)
        XCTAssertEqual(AflMatchScoringGeometry10868.x(index: 54, count: 55), 1)
        XCTAssertEqual(AflMatchScoringGeometry10868.x(index: 0, count: 1), 0.5)
        XCTAssertNil(AflMatchScoringGeometry10868.x(index: 55, count: 55))
        XCTAssertEqual(AflMatchScoringGeometry10868.index(atFraction: 0.5, count: 55), 27)
        XCTAssertEqual(AflMatchScoringGeometry10868.index(atFraction: -3, count: 55), 0)
        XCTAssertNil(AflMatchScoringGeometry10868.index(atFraction: .nan, count: 55))
        let model = try XCTUnwrap(Model(Self.input(.final)).scoringModel)
        // Equal spacing by order: the long Q4 gap between plays is not elapsed time.
        let xs = model.placements.map(\.x)
        XCTAssertTrue(zip(xs, xs.dropFirst()).allSatisfy { abs(($1 - $0) - 1.0 / 54.0) < 1e-12 })
        XCTAssertEqual(model.placements[50].y, (-17.0 + 18.0) / 36.0)
        XCTAssertEqual(model.segments.count, 1)
        XCTAssertEqual(model.segments[0].count, 1 + 54 * 2, "each later play adds a hold and a step")
        XCTAssertEqual(model.fills.count, 54)
        XCTAssertEqual(model.fills[50].accent, Self.fremantle.tint, "the held step's own leader")
        // A missing or off-scale lead breaks the line; nothing is clamped.
        var source = Self.scoringPlays()
        let off = source[20]
        source[20] = AflMatchScoringPlay10868(id: off.id, lead: 60, leader: off.leader, mark: off.mark, period: off.period,
                                              clock: off.clock, scorer: off.scorer, scores: off.scores, leadWords: off.leadWords,
                                              spoken: off.spoken)
        let missing = source[30]
        source[30] = AflMatchScoringPlay10868(id: missing.id, lead: nil, leader: nil, mark: missing.mark, period: missing.period,
                                              clock: missing.clock, scorer: missing.scorer, scores: missing.scores,
                                              leadWords: missing.leadWords, spoken: missing.spoken)
        let story = Self.scoring()
        let broken = AflMatchScoringModel10868(
            story: AflMatchScoringStory10868(plays: source, scale: story.scale, guides: story.guides, checkpoints: story.checkpoints,
                                             selectedPlayID: story.selectedPlayID, plotHeight: 210, copy: story.copy),
            headline: Self.headline(.final), chance: nil)
        XCTAssertNil(broken.placements[20].y)
        XCTAssertNil(broken.placements[30].y)
        XCTAssertEqual(broken.segments.count, 3)
        XCTAssertEqual(broken.placements.count, 55, "an unplaceable play keeps its position")
    }

    // MARK: - Independence and absence

    func testScoreAndChanceCursorsStayIndependent() throws {
        var log: [String] = []
        let input = Self.input(.final)
        let page = Page(input: input, originals: Self.originals(.final),
                        onHistoryAction: { log.append("history:\($0)") },
                        onHistoryInspectionChoice: { log.append("choice:\($0)") },
                        onPlaySelect: { log.append("play:\($0)") },
                        onPeriodSelect: { log.append("quarter:\($0)") },
                        onChanceOpen: { log.append("chance:\($0.observation ?? "none")") })
        page.pageScoringContent()?.onSelect?(Self.plays[50].id)
        page.pagePeriodsContent()?.onSelect?("q3")
        XCTAssertEqual(log, ["play:\(Self.plays[50].id)", "quarter:q3"], "a score selection hands back only its row")
        // The page's other inputs are untouched by a held play or quarter.
        let held = Self.input(.final, scoring: Self.scoring(selected: Self.plays[50].id), quarters: Self.quarters(selected: "q3"))
        XCTAssertEqual(held.history, input.history)
        XCTAssertEqual(held.headline, input.headline)
        XCTAssertEqual(held.chance, input.chance)
        XCTAssertEqual(Model(held).readerHistory, Model(input).readerHistory)
        // A chance action hands back the exact original and observation key.
        let card = try XCTUnwrap(page.pageScoringContent())
        let chance = try XCTUnwrap(card.model.chanceModel)
        for side in chance.sides {
            if let opening = chance.openAction(side, canOpen: true) { card.onChanceOpen?(opening) }
        }
        XCTAssertEqual(log.suffix(2), ["chance:\(Self.pointID(Self.brisbane, 1_790_396_940))", "chance:\(Self.pointID(Self.brisbane, Self.lowAt))"])
    }

    func testMissingOrInvalidChancesKeepTheActualsAndLabelledDisabledSlots() throws {
        let input = Self.input(.final, chance: Self.chance(withReadings: false))
        let model = Model(input)
        let chance = HistoricalChanceModel10868(try XCTUnwrap(model.chance))
        XCTAssertEqual(chance.sides.map { Self.shown($0.endpoint) },
                       ["Before match: Not recorded for this comparison", "Lowest minute-end chance: Not recorded for this comparison"])
        XCTAssertTrue(chance.sides.allSatisfy { chance.openAction($0, canOpen: true) == nil }, "inspection disabled")
        XCTAssertEqual(chance.actual.map { Self.shown($0) }, "Reported final score=Brisbane 96–89 Fremantle")
        XCTAssertEqual(chance.outcome, "Brisbane won")
        // The actual-points stories stay whole.
        XCTAssertEqual(model.periodModel?.bars.count, 4)
        XCTAssertEqual(model.scoringModel?.placements.count, 55)
        XCTAssertEqual(model.scoringModel?.chanceModel?.sides.map { FieldChaseModel10868.label($0.endpoint) },
                       ["Before match", "Lowest minute-end chance"], "labelled slots stay")
        // A missing pre-match baseline keeps the final points.
        let noBaseline = Model(Self.input(.final, headline: Self.headline(.final, baseline: false)))
        XCTAssertEqual(Self.metrics(noBaseline.headline).map { $0.last }, ["Final points=96", "Final points=89"])
        // An invalid observation (a probability outside 0–1) is unplaced.
        let invalid = HistoricalChanceModel10868(Self.chance(checkpointObservation: [
            HistoricalChanceObservation10868(ref: Self.ref(Self.brisbane), endpoint: .checkpoint,
                                             observation: FieldMovementObservation10868(probability: 3, reading: Self.chanceReading(.checkpoint, Self.lowClose)),
                                             key: Self.pointID(Self.brisbane, Self.lowAt)),
        ]))
        XCTAssertEqual(Self.shown(invalid.sides[1].endpoint), "Lowest minute-end chance: Not recorded for this comparison")
        XCTAssertNotNil(invalid.actual)
    }

    func testAbsentDuplicateForeignAndWithdrawnIdentitiesFailClosedWhileNeighboursWork() throws {
        // A foreign or withdrawn chance subject keeps its name and words, no figure.
        let foreign = HistoricalChanceModel10868(Self.chance(subject: Self.ref(Self.brisbane, scope: "kalshi|OTHER|winner")))
        XCTAssertEqual(foreign.subjectWords, "Team unavailable in this update")
        XCTAssertTrue(foreign.sides.allSatisfy { FieldChaseModel10868.figure($0.endpoint) == nil })
        // A duplicated quarter id is not selectable and a held duplicate is missing.
        var rows = Self.quarterRows()
        rows[1] = AflMatchPeriodRow10868(id: "q1", label: rows[1].label, lead: rows[1].lead, leadWords: rows[1].leadWords,
                                          leader: rows[1].leader, scoreLabel: rows[1].scoreLabel, scores: rows[1].scores,
                                          spoken: rows[1].spoken)
        let quarters = AflMatchPeriodModel10868(story: Self.quarters(rows: rows, selected: "q1"), headline: Self.headline(.final))
        XCTAssertEqual(quarters.bars.map(\.selectableID), [nil, nil, "q3", "final"])
        XCTAssertEqual(quarters.selection, .missing("That quarter is not in this update"))
        // A foreign leader draws the neutral colour; its neighbours keep theirs.
        var plays = Self.scoringPlays()
        let first = plays[0]
        plays[0] = AflMatchScoringPlay10868(id: first.id, lead: first.lead, leader: Self.ref(Self.fremantle, scope: "kalshi|OTHER|winner"),
                                            mark: first.mark, period: first.period, clock: first.clock, scorer: first.scorer,
                                            scores: first.scores, leadWords: first.leadWords, spoken: first.spoken)
        let story = Self.scoring()
        let scoring = AflMatchScoringModel10868(
            story: AflMatchScoringStory10868(plays: plays, scale: story.scale, guides: story.guides,
                                             checkpoints: story.checkpoints + [AflMatchScoringCheckpoint10868(id: "cp-gone", playID: "withdrawn", label: "Gone", detail: nil)],
                                             selectedPlayID: story.selectedPlayID, plotHeight: 210, copy: story.copy),
            headline: Self.headline(.final), chance: nil)
        XCTAssertNil(scoring.placements[0].accent)
        XCTAssertEqual(scoring.placements[1].accent, Self.brisbane.tint)
        XCTAssertNil(scoring.checkpoints.last?.playID, "a checkpoint naming no play keeps its words, no control")
        // A held original from another scope opens nothing and is shown unavailable.
        let originals = Self.originals(.final, selection: Self.selection(Self.brisbane, scope: "kalshi|OTHER|originals"))
        XCTAssertTrue(Model.heldOriginalIsUnavailable(originals))
        XCTAssertFalse(Model.heldOriginalIsUnavailable(Self.originals(.final)))
    }

    func testSameAndDistinctEqualObservationsStayApart() {
        // Brisbane's 99% closes at different minutes are distinct points.
        let history = Self.history(.final)
        let nineNine = history.series[0].runs.flatMap(\.points).filter { $0.probability == 0.99 }
        XCTAssertEqual(nineNine.count, 9)
        XCTAssertEqual(Set(nineNine.map(\.id)).count, 9)
        // An equal figure at another minute does not tie to the checkpoint reading.
        let other = Self.closes(Self.brisbane).first { $0.cents == 3 && $0.at != Self.lowAt }
        let elsewhere = Close(team: "B", at: other?.at ?? Self.lowAt - 60, cents: 3)
        let distinct = HistoricalChanceModel10868(Self.chance(checkpointObservation: [
            HistoricalChanceObservation10868(ref: Self.ref(Self.brisbane), endpoint: .checkpoint,
                                             observation: FieldMovementObservation10868(probability: 0.03, reading: Self.chanceReading(.checkpoint, elsewhere)),
                                             key: Self.pointID(Self.brisbane, elsewhere.at)),
        ]))
        XCTAssertEqual(Self.shown(distinct.sides[1].endpoint), "Lowest minute-end chance: Not recorded for this comparison")
        // Two identical observations are none.
        let same = HistoricalChanceObservation10868(ref: Self.ref(Self.brisbane), endpoint: .checkpoint,
                                                    observation: FieldMovementObservation10868(probability: 0.03, reading: Self.chanceReading(.checkpoint, Self.lowClose)),
                                                    key: Self.pointID(Self.brisbane, Self.lowAt))
        let doubled = HistoricalChanceModel10868(Self.chance(checkpointObservation: [same, same]))
        XCTAssertNil(doubled.sides[1].key)
        // The same observation ties.
        XCTAssertEqual(HistoricalChanceModel10868(Self.chance(checkpointObservation: [same])).sides[1].key,
                       Self.pointID(Self.brisbane, Self.lowAt))
    }

    func testHeldPlayQuarterAndOriginalSurviveOmissionAndRestoreOnlyByExactIdentity() throws {
        let heldPlay = Self.plays[50].id
        let omitted = Self.plays.filter { $0.id != heldPlay }
        let gone = AflMatchScoringModel10868(story: Self.scoring(plays: omitted, selected: heldPlay), headline: Self.headline(.final), chance: nil)
        XCTAssertEqual(gone.selection, .missing("That scoring play is not in this update"))
        XCTAssertNil(gone.earlierID)
        XCTAssertNil(gone.laterID)
        XCTAssertFalse(gone.placements.contains(where: \.isSelected), "no neighbour stands in")
        XCTAssertEqual(gone.placements.count, 54)
        let back = AflMatchScoringModel10868(story: Self.scoring(selected: heldPlay), headline: Self.headline(.final), chance: nil)
        guard case .row(let play, let index) = back.selection else { return XCTFail("the exact play restores") }
        XCTAssertEqual([play.id, "\(index)"], [heldPlay, "50"])
        XCTAssertEqual([back.earlierID, back.laterID], [Self.plays[49].id, Self.plays[51].id])

        let rows = Self.quarterRows()
        let noQ3 = AflMatchPeriodModel10868(story: Self.quarters(rows: rows.filter { $0.id != "q3" }, selected: "q3"), headline: Self.headline(.final))
        XCTAssertEqual(noQ3.selection, .missing("That quarter is not in this update"))
        XCTAssertFalse(noQ3.bars.contains(where: \.isSelected))
        let q3 = AflMatchPeriodModel10868(story: Self.quarters(selected: "q3"), headline: Self.headline(.final))
        guard case .row(let row, _) = q3.selection else { return XCTFail("the exact quarter restores") }
        XCTAssertEqual(row.scores.map(\.score), ["62", "72"])

        let withdrawn = Self.originals(.final, list: [Self.original(Self.fremantle, .final)])
        XCTAssertTrue(Model.heldOriginalIsUnavailable(withdrawn))
        XCTAssertNil(Details.content(catalogue: withdrawn.catalogue, selection: withdrawn.selection))
        let restored = Self.originals(.final)
        XCTAssertEqual(Details.content(catalogue: restored.catalogue, selection: restored.selection)?.outcome, "Brisbane Lions")
    }

    // MARK: - Interaction

    func testThePageHoldsOnceBeforeEachActionNeverPassivelyAndNeverInAReaderOrTheAbout() throws {
        var log: [String] = []
        let input = Self.input(.final)
        let originals = Self.originals(.final)
        func page(_ mode: AflMatchEventPageMode10868) -> Page {
            Page(input: input, mode: mode, originals: originals,
                 onAbout: { log.append("about") }, onSource: { log.append("source:\($0.id)") },
                 onAllProps: { log.append("allProps") },
                 onOriginalSelect: { log.append("original:\($0.identity.market)") },
                 onOriginalHistory: { _ in log.append("originalHistory") },
                 onHeadlineOpen: { log.append("headline:\($0.ref.marketID)") },
                 onHistoryAction: { log.append("history:\($0)") },
                 onHistoryInspectionChoice: { log.append("choice:\($0)") },
                 onHistoryPlotPosition: { log.append("position:\($0)") },
                 onCardOpen: { log.append("open:\($0.rawValue)") },
                 onCardDetails: { log.append("details:\($0.rawValue)") },
                 onPlaySelect: { log.append("play:\($0)") },
                 onPeriodSelect: { log.append("quarter:\($0)") },
                 onChanceOpen: { log.append("chance:\($0.observation ?? "none")") },
                 onReaderIntent: { log.append("reader:\(Tests.words($0))") },
                 onInteraction: { log.append("hold") })
        }
        let main = page(.page)
        _ = (main.headlineContent(), main.historyContent(reader: false), main.pageScoringContent(),
             main.pagePeriodsContent(), main.chooserContent(), main.aboutContent())
        XCTAssertEqual(log, [], "building the page and its leaves calls nothing")
        main.headlineContent()?.onAbout?()
        main.historyContent(reader: false).onAction?("history.expand")
        main.pageScoringContent()?.onSelect?(Self.plays[0].id)
        main.pageScoringContent()?.onExpand?()
        main.pageScoringContent()?.onPeriods?()
        main.pagePeriodsContent()?.onDetails?()
        main.openAllProps()
        XCTAssertEqual(log, ["hold", "about", "hold", "history:history.expand", "hold", "play:\(Self.plays[0].id)",
                             "hold", "open:scoring", "hold", "open:periods", "hold", "details:periods",
                             "hold", "allProps"])
        log.removeAll()
        // Full-size content and the About keep the exact callbacks.
        let reader = page(.reader(.scoring))
        reader.readerScoringContent()?.onSelect?(Self.plays[1].id)
        reader.readerScoringContent()?.onPeriods?()
        reader.readerScoringContent()?.onDetails?()
        reader.historyContent(reader: true).onAction?("history.details")
        page(.about).aboutContent()?.onSource?(Self.report)
        XCTAssertEqual(log, ["play:\(Self.plays[1].id)", "reader:open:periods", "reader:details:scoring",
                             "history:history.details", "source:espn-match-record"])
    }

    func testAStoryInTheStreamHoldsThroughItsOwnActivationOnly() throws {
        var log: [String] = []
        let stream = Self.stream()
        let input = Self.input(.final, stream: stream)
        let page = Page(input: input, onPlaySelect: { log.append("play:\($0)") }, onPeriodSelect: { log.append("quarter:\($0)") },
                        onInteraction: { log.append("hold") })
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: "scoring")
        let activation = StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction = intent { log.append("activate") } else { log.append("other") }
        }
        XCTAssertNil(page.pageScoringContent(), "with a stream the cards live in the stream")
        let card = try XCTUnwrap(page.streamScoringContent(activation: activation))
        XCTAssertNil(card.onExpand, "the stream offers its own open")
        card.onSelect?(Self.plays[2].id)
        XCTAssertEqual(log, ["activate", "play:\(Self.plays[2].id)"])
        XCTAssertEqual(Model(input).storyLink("scoring")?.card, .scoring)
        XCTAssertNil(Model(Self.input(.before, stream: stream)).storyLink("scoring"), "before play no story card mounts")
    }

    func testAbsentCallbacksOfferNoControlAndTheHookAloneDoesNothing() throws {
        var log: [String] = []
        let page = Page(input: Self.input(.final), originals: Self.originals(.final), onInteraction: { log.append("hold") })
        XCTAssertNil(page.headlineContent()?.onOpen)
        XCTAssertNil(page.headlineContent()?.onAbout)
        XCTAssertNil(page.historyContent(reader: false).onAction)
        let scoring = try XCTUnwrap(page.pageScoringContent())
        XCTAssertNil(scoring.onSelect)
        XCTAssertNil(scoring.onExpand)
        XCTAssertNil(scoring.onPeriods)
        XCTAssertNil(scoring.onDetails)
        XCTAssertNil(scoring.onChanceOpen)
        let chance = try XCTUnwrap(scoring.model.chanceModel)
        XCTAssertTrue(chance.sides.allSatisfy { chance.openAction($0, canOpen: false) == nil }, "a slot without a callback does not act")
        XCTAssertNil(page.pagePeriodsContent()?.onSelect)
        XCTAssertNil(page.chooserContent()?.onSelect)
        let controls = page.readerControls(.scoring)
        XCTAssertFalse(controls.canGoBack)
        XCTAssertNil(controls.previous)
        page.openAllProps()
        XCTAssertEqual(log, [])
    }

    func testFullSizeCardsAreTheSameViewsWithTheSameInputsAndReaderIntents() throws {
        var intents: [AflMatchReaderIntent10868] = []
        let input = Self.input(.final)
        let model = Model(input)
        let scoring = try XCTUnwrap(model.scoringModel), full = try XCTUnwrap(model.readerScoringModel)
        XCTAssertEqual(full.story.plays, scoring.story.plays)
        XCTAssertEqual(full.story.selectedPlayID, scoring.story.selectedPlayID)
        XCTAssertEqual(full.story.checkpoints, scoring.story.checkpoints)
        XCTAssertEqual([scoring.story.plotHeight, full.story.plotHeight], [210, 300])
        let page = Page(input: input, mode: .reader(.scoring), onReaderIntent: { intents.append($0) })
        XCTAssertEqual(page.readerScoringContent()?.model.story.plays, scoring.story.plays)
        XCTAssertEqual(page.readerPeriodsContent()?.model, model.periodModel)
        XCTAssertEqual(page.readerPeriodsContent()?.chance, model.chance)
        let controls = page.readerControls(.scoring)
        XCTAssertEqual([controls.previous, controls.next], [.history, .periods])
        XCTAssertTrue(controls.canGoBack)
        XCTAssertEqual([page.readerControls(.history).previous, page.readerControls(.periods).next], [nil, nil])
        Page.bind(page.onReaderIntent, .next(.periods))?()
        Page.bind(page.onReaderIntent, .back)?()
        page.readerScoringContent()?.onDetails?()
        XCTAssertEqual(intents, [.next(.periods), .back, .details(.scoring)])
        // A card the phase does not mount has no full-size content or neighbours.
        let before = Page(input: Self.input(.before), mode: .reader(.scoring), onReaderIntent: { intents.append($0) })
        XCTAssertNil(before.readerScoringContent())
        XCTAssertFalse(before.readerControls(.scoring).canGoBack)
        XCTAssertEqual(Model(Self.input(.before)).neighbour(of: .history, offset: 1), nil)
    }

    func testLayoutPlansForCompactWideAndLargeText() {
        XCTAssertEqual(Model.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.readoutArrangements(accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(Model.readoutArrangements(accessibilitySize: true), [.stacked])
        XCTAssertEqual(Model.readingOrder, [.headline, .notice, .anchor, .cards, .originals, .allProps])
        XCTAssertGreaterThan(Model.sortPriority(.headline), Model.sortPriority(.cards))
        XCTAssertEqual(AflMatchScoringGeometry10868.plotFrame(in: CGSize(width: 300, height: 210), gutter: 44, room: 10),
                       CGRect(x: 44, y: 10, width: 246, height: 190))
        XCTAssertNil(AflMatchScoringGeometry10868.plotFrame(in: CGSize(width: 40, height: 210), gutter: 44, room: 10))
    }

    // MARK: - Live, actual and settlement

    func testNoLiveClaimWithoutLiveEvidence() throws {
        // CONSTRUCTED in-play update with no recorded chance: availability words, no figure.
        let missing = Model(Self.input(.during, headline: Self.headline(.during, liveEvidence: false)))
        XCTAssertEqual(Self.metrics(missing.headline), [
            ["Pre-match win chance=56%", "Recorded: Current probability unavailable"],
            ["Pre-match win chance=45%", "Recorded: Current probability unavailable"],
        ])
        for phase in Phase.allCases {
            let texts = Self.reachableText(Self.input(phase), originals: Self.originals(phase))
            XCTAssertFalse(Self.reaches(texts, "\\blive\\b"), "\(phase)")
            XCTAssertFalse(Self.reaches(texts, "projected final"), "\(phase)")
            XCTAssertFalse(texts.contains("Current chance"), "\(phase)")
        }
        // During play no story, chance-to-result or report is reachable.
        let during = Model(Self.input(.during))
        XCTAssertNil(during.chance)
        XCTAssertFalse(Self.reaches(Self.reachableText(Self.input(.during), originals: nil), "ESPN"))
    }

    func testTheActualFinalStaysApartFromSettlementAndHistoricalChances() throws {
        let model = Model(Self.input(.final))
        let chance = HistoricalChanceModel10868(try XCTUnwrap(model.chance))
        XCTAssertEqual(chance.actual.map { Self.shown($0) }, "Reported final score=Brisbane 96–89 Fremantle")
        XCTAssertEqual(chance.actual.flatMap { FieldChaseModel10868.detail($0) }, "ESPN match record and scoreboard")
        let originals = Self.originals(.final)
        let content = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: originals.selection))
        XCTAssertEqual(content.result?.words, "Resolved Yes")
        XCTAssertEqual(content.result?.provenance, "Settled Sep 26, 7:31 AM UTC · Kalshi")
        XCTAssertFalse(content.readings.contains { $0.text.contains("96") }, "the contract never carries the score")
        // The history's last closes are recordings, never current.
        let history = model.input.history
        XCTAssertEqual(FieldHistoryGeometry10868.readoutSlots(history.series[0], in: history).map(\.label), ["Pre-match", "Last recorded"])
        XCTAssertFalse(Self.reaches(Self.reachableText(model.input, originals: originals), "current probability(?! unavailable)"))
    }

    // MARK: - Phase-admitted reachable text

    func testEachPhaseReachesOnlyItsOwnAdmittedFactsOnEverySurface() {
        let before = Self.reachableText(Self.input(.before), originals: Self.originals(.before))
        let during = Self.reachableText(Self.input(.during), originals: Self.originals(.during))
        let finished = Self.reachableText(Self.input(.final, stream: Self.stream()), originals: Self.originals(.final))
            + Self.reachableText(Self.input(.final), originals: Self.originals(.final))

        XCTAssertEqual(Self.leaks(before, Self.beforeForbidden), [])
        XCTAssertEqual(Self.leaks(during, Self.duringForbidden), [])
        for pattern in ["(^|[^0-9.])56%", "(^|[^0-9.])45%"] {
            XCTAssertTrue(Self.reaches(before, pattern), pattern)
            XCTAssertTrue(Self.reaches(during, pattern), pattern)
        }
        XCTAssertTrue(Self.reaches(during, "(^|[^0-9.])51%"))
        XCTAssertTrue(Self.reaches(during, "(^|[^0-9.])57%"))
        // Positive control: the final reaches every final fact.
        for pattern in Self.finalPositivePatterns {
            XCTAssertTrue(Self.reaches(finished, pattern), pattern)
        }
        XCTAssertTrue(Self.reaches(finished, "(^|[^0-9.])56%"), "the pre-match chances stay at the final")
    }

    func testThePhaseTextGuardCatchesTheLeakItWasWrittenFor() {
        // The leak class Design caught on AFLW and squash: a final About (report,
        // score, scorers) behind Info on an earlier page.
        var leaked = Self.input(.before)
        leaked.about = Self.about(.final)
        let hits = Self.leaks(Self.reachableText(leaked, originals: Self.originals(.before)), Self.beforeForbidden)
        for pattern in ["\\bESPN\\b", Self.pairPattern("96–89"), "\\bMorris\\b", "\\bgoals?\\b", "(^|[^0-9.])3%"] {
            XCTAssertTrue(hits.contains { $0.hasPrefix("\(pattern) ⟵") }, pattern)
        }
        var duringLeak = Self.input(.during)
        duringLeak.about = Self.about(.final)
        XCTAssertFalse(Self.leaks(Self.reachableText(duringLeak, originals: nil), Self.duringForbidden).isEmpty)
        // Meaning-aware: a chance is not a score, and no token matches inside an epoch.
        XCTAssertEqual(Self.leaks(["56%", "Pre-match win chance: 45%", "43%", "62%", "Minute ending Sep 26, 4:29 AM UTC"],
                                  Self.finalPositivePatterns), [])
        XCTAssertEqual(Self.leaks(["1790396940", "BRI@1790407440", "17903968"], Self.finalPositivePatterns), [])
        XCTAssertFalse(Self.leaks(["43–43"], Self.finalPositivePatterns).isEmpty)
        XCTAssertFalse(Self.leaks(["Brisbane 96"], Self.finalPositivePatterns).isEmpty)
    }

    // MARK: - Action payloads

    func testEveryActionPayloadCarriesOnlyItsPhasesAdmittedKeys() {
        for phase in Phase.allCases {
            let payloads = Self.payloads(Self.input(phase), originals: Self.originals(phase))
            XCTAssertFalse(payloads.isEmpty, "\(phase)")
            XCTAssertEqual(Self.payloadLeaks(payloads, admittedThrough: Self.bound(phase)), [], "\(phase)")
            XCTAssertTrue(payloads.allSatisfy { !$0.hasPrefix("original:") || $0.hasPrefix("original:\(Self.originalsScope)|") })
        }
        // Before play the history steps carry pre-start minutes only; the
        // headline open carries no observation.
        let before = Self.payloads(Self.input(.before), originals: Self.originals(.before))
        XCTAssertTrue(before.contains("history.action:history.inspect@\(Self.baseline(Self.brisbane).at)"))
        XCTAssertEqual(before.filter { $0.hasPrefix("headline:") }, [
            "headline:\(Self.brisbane.ticker)@none", "headline:\(Self.fremantle.ticker)@none",
        ])
        XCTAssertFalse(before.contains { $0.hasPrefix("chance:") || $0.hasPrefix("play:") || $0.hasPrefix("quarter:") })
        // During play the headline opens the CONSTRUCTED cut's own keys.
        let during = Self.payloads(Self.input(.during), originals: Self.originals(.during))
        XCTAssertEqual(during.filter { $0.hasPrefix("headline:") }, [
            "headline:\(Self.brisbane.ticker)@\(Self.pointID(Self.brisbane, Self.cutClose(Self.brisbane).at))",
            "headline:\(Self.fremantle.ticker)@\(Self.pointID(Self.fremantle, Self.cutClose(Self.fremantle).at))",
        ])
        // At the final the chance actions carry each endpoint's own key.
        let finished = Self.payloads(Self.input(.final), originals: Self.originals(.final))
        XCTAssertTrue(finished.contains("chance:\(Self.brisbane.ticker)@\(Self.pointID(Self.brisbane, Self.lowAt))"))
        XCTAssertTrue(finished.contains("chance:\(Self.brisbane.ticker)@\(Self.pointID(Self.brisbane, 1_790_396_940))"))
        // An earlier held minute and a missing held original change the payloads exactly.
        let earlier = Self.payloads(Self.input(.before, history: Self.history(.before, inspecting: Self.baseline(Self.fremantle).at)),
                                    originals: Self.originals(.before, list: [Self.original(Self.fremantle, .before)]))
        XCTAssertTrue(earlier.contains("history.choice:minute@\(Self.baseline(Self.fremantle).at)"))
        XCTAssertEqual(Self.payloadLeaks(earlier, admittedThrough: Self.bound(.before)), [])
        XCTAssertEqual(earlier.filter { $0.hasPrefix("original:") }, ["original:\(Self.originalsScope)|\(Self.fremantle.ticker)"])
    }

    func testThePayloadGuardCatchesAFinalKeyUsedBeforePlay() {
        // The horse leak class: a final default position sent before play.
        let hostile = Self.payloads(Self.input(.before, history: Self.history(.before, minutesOverride: .final)),
                                    originals: Self.originals(.before))
        let caught = Self.payloadLeaks(hostile, admittedThrough: Self.bound(.before))
        XCTAssertTrue(caught.contains("history.action:history.inspect@1790407440"))
        XCTAssertFalse(Self.payloadLeaks(["chance:\(Self.brisbane.ticker)@\(Self.pointID(Self.brisbane, Self.lowAt))"],
                                         admittedThrough: Self.bound(.before)).isEmpty)
        XCTAssertFalse(Self.payloadLeaks(["history.choice:minute@\(1_790_407_020)"], admittedThrough: Self.bound(.during)).isEmpty)
        XCTAssertEqual(Self.payloadLeaks(["history.choice:minute@\(Self.constructedLiveCut)"], admittedThrough: Self.bound(.during)), [])
    }

    // MARK: - Rules fidelity

    func testOriginalRulesAreVerbatimRetainedText() throws {
        XCTAssertEqual(Self.sha256(Self.retainedRulesPrimary["BRI"]!), Self.retainedRulesHashes["BRI"])
        XCTAssertEqual(Self.sha256(Self.retainedRulesPrimary["FRE"]!), Self.retainedRulesHashes["FRE"])
        XCTAssertEqual(Self.sha256(Self.retainedRulesSecondary), Self.retainedRulesHashes["secondary"])
        XCTAssertEqual(Self.sha256(Self.retainedTitle), Self.retainedRulesHashes["title"])
        for phase in Phase.allCases {
            let originals = Self.originals(phase)
            for team in Self.teams {
                let content = try XCTUnwrap(Details.content(catalogue: originals.catalogue, selection: Self.selection(team)))
                XCTAssertEqual(content.rules, .verified([Self.retainedRulesPrimary[team.key]!, Self.retainedRulesSecondary]))
                XCTAssertEqual(content.title, Self.retainedTitle)
                XCTAssertEqual(content.outcome, team.name)
            }
        }
    }
}
