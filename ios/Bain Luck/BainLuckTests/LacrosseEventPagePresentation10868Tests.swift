import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the lacrosse match screen (`lacrosse-match`) composed from the
/// shared leaves, the accepted rugby comparison and its selectable
/// actual-quarter leaf.
///
/// PREPARED / NOT RUN. The view is SwiftUI and is not rasterised here. What is
/// asserted is the composition: which actual leaf each phase mounts and with
/// which exact owner input; the before-play and live isolation of every later
/// quote, score, period, report and result in every reachable visible and
/// spoken output; the exact phase-admitted payload of every action; the 701
/// retained minute closes with their runs and real gaps; the independent
/// pre-match chances; exact-minute inspection; the equal-size dated
/// comparison and the key it stands in for; the plot height rule; the exact
/// score identity; the selectable quarters, independent of the history; true
/// zero against an unknown count; verbatim original rules; held identities;
/// the full-size readers; the callbacks and the once-only hold. Each shared
/// leaf's own rules stay with its own tests; nothing here claims a compile, a
/// rendered fit at 375×667 or 393×852, VoiceOver behaviour, a production
/// binding or route readiness.
///
/// ARCHIVED raw values (prototype `lacrosseMatch.json`, sha256 b70e369d…5ee2):
/// Notre Dame vs Syracuse, May 23 2026, Kalshi event
/// KXNCAAMLAXGAME-26MAY23SYRNOT, ESPN competition 401870923, teams 87
/// (Notre Dame Fighting Irish) and 183 (Syracuse Orange); listed start
/// 2026-05-23T18:55:00Z, which is not the actual faceoff;
/// - the 701 admitted positive-volume minute closes, verbatim (minute end,
///   close in cents, volume): Notre Dame 317 (188 before the listing),
///   Syracuse 384 (251 before); both pre-match closes end at 1779562440 —
///   Notre Dame 70%, Syracuse 36%, independent markets summing to 106%; last
///   closes Notre Dame 99% at 1779575220, Syracuse 1% at 1779574380; the
///   archive starts the previous day, not at market inception;
/// - final 15–7; quarter goals 4/3/2/6 and 3/1/3/0 from the scoreboard row
///   bound by exact ids — `scoreboard.events` row 0 is Princeton–Duke;
/// - each market's verbatim `title`, `yes_sub_title`, `rules_primary` and
///   `rules_secondary`; contract results Notre Dame yes, Syracuse no.
///
/// CONSTRUCTED (owner inputs, not retained facts): every label, figure text,
/// PDT clock line, caption, state word, About, source and report text, tint,
/// scope, identity and action id; the minute coordinate; the match window;
/// the cumulative-score words; the goal scale ceiling; the plot heights; the
/// other props in the arbitrary catalogue; and the whole DURING frame — there
/// is no live specimen, so the live phase stays applicable but
/// evidence-missing, and its one-hour probability cutoff and its first two
/// quarters are a labelled construction with no claimed synchronization.
@MainActor
final class LacrosseEventPagePresentation10868Tests: XCTestCase {

    private typealias Phase = LacrosseEventPagePhase10868

    // MARK: Teams

    private enum Team: String, CaseIterable {
        case notreDame = "not"
        case syracuse = "syr"
    }

    private static let notreDameTint = Color(red: 0.15, green: 0.39, blue: 0.92)
    private static let syracuseTint = Color(red: 0.05, green: 0.58, blue: 0.53)

    private static func name(_ team: Team) -> String { team == .notreDame ? "Notre Dame" : "Syracuse" }
    private static func tint(_ team: Team) -> Color { team == .notreDame ? notreDameTint : syracuseTint }
    private static func shape(_ team: Team) -> FieldHistoryShape10868 { team == .notreDame ? .circle : .diamond }

    /// ARCHIVED market tickers.
    private static func ticker(_ team: Team) -> String {
        team == .notreDame ? "KXNCAAMLAXGAME-26MAY23SYRNOT-NOT" : "KXNCAAMLAXGAME-26MAY23SYRNOT-SYR"
    }

    // MARK: The 701 retained minute closes

    private struct Close: Equatable {
        let at: Int
        let cents: Int
        let volume: String
    }

    /// ARCHIVED: the listing, 2026-05-23T18:55:00Z — never the faceoff.
    private static let listedStart = 1779562500
    /// ARCHIVED: both teams' last positive-volume minute strictly before it.
    private static let baselineAt = 1779562440
    /// CONSTRUCTED: the live frame's cutoff, one hour after the listing.
    private static let liveCutoff = 1779566100
    /// ARCHIVED last closes.
    private static let notreDameLastAt = 1779575220
    private static let syracuseLastAt = 1779574380
    /// ARCHIVED: the earliest retained minute (Syracuse, the previous day).
    private static let firstAt = 1779477000
    /// ARCHIVED: the markets opened 2026-05-18T15:48Z.
    private static let marketOpen = 1779119280
    /// May 23 00:00 PDT, the start of match day in Pacific time.
    private static let matchDay = 1779519600

    /// ARCHIVED, verbatim: `minute end:close in cents:volume`, every admitted
    /// positive-volume unique minute close in minute order.
    private static let notreDameRaw = """
        1779479040:74:19.91 1779480780:74:5.33 1779482100:70:200.00 1779483300:73:3.42 1779486120:72:21.79 1779487140:74:3.31
        1779489840:69:48.00 1779490080:69:9.00 1779493440:74:740.00 1779498780:75:13.16 1779500940:74:5.00 1779501780:74:13.27
        1779503640:69:50.00 1779505440:74:369.46 1779507000:72:27.53 1779507120:71:69.02 1779507720:71:6.90 1779510540:71:34.51
        1779512400:71:44.59 1779515640:71:13.80 1779516180:71:6.20 1779518340:72:54.48 1779518520:71:3.80 1779527340:71:13.80
        1779531060:71:0.32 1779534120:71:20.74 1779535860:71:34.51 1779536160:71:13.80 1779539040:63:400.00 1779539340:69:15.00
        1779539460:68:4.31 1779539580:68:404.69 1779539700:69:35.46 1779540660:69:2.83 1779540720:68:14.00 1779540960:68:76.00
        1779541020:68:55.00 1779541080:68:14.00 1779541920:69:14.18 1779542160:69:2.83 1779542880:68:70.30 1779543300:69:28.36
        1779543540:68:25.00 1779543960:68:232.00 1779544020:68:31.00 1779544980:69:75.17 1779545520:69:35.46 1779545640:69:35.46
        1779545760:69:14.15 1779545820:63:503.00 1779545880:69:14.17 1779546000:69:141.84 1779546120:63:11.00 1779546180:63:106.00
        1779546360:68:25.00 1779546600:69:14.18 1779546840:68:10.06 1779546960:67:51.55 1779547020:67:487.45 1779547140:68:126.57
        1779547200:68:28.76 1779547500:60:1377.03 1779548100:68:316.44 1779548280:68:511.00 1779548400:68:14.00 1779548580:67:87.33
        1779548700:69:69.50 1779548940:69:14.18 1779549240:68:369.64 1779549420:68:64.72 1779549480:68:71.91 1779549540:68:236.73
        1779549600:67:73.71 1779549660:69:8.00 1779549900:69:53.25 1779549960:69:42.55 1779550020:69:141.84 1779550080:67:62.18
        1779550200:69:86.81 1779550260:67:10.23 1779550680:67:25.00 1779550920:69:26.09 1779551040:68:15.00 1779551460:68:14.38
        1779551520:68:1.43 1779551700:68:78.67 1779551760:68:11.21 1779551880:68:14.38 1779552000:67:38.94 1779552060:67:17.31
        1779552120:67:155.00 1779552180:67:66.00 1779552240:69:3.54 1779552360:69:7.09 1779552420:69:63.64 1779552480:67:26.00
        1779552960:67:70.00 1779553020:69:7.09 1779553140:67:28.38 1779553200:67:13.00 1779553260:67:181.00 1779553320:71:5510.50
        1779553440:68:3.02 1779553500:67:152.83 1779553980:70:21.33 1779554160:70:69.95 1779554400:70:20.98 1779554640:71:136.00
        1779554700:71:416.28 1779554760:72:0.29 1779555060:73:133.32 1779555180:74:277.70 1779555660:70:17.00 1779555720:72:108.96
        1779555780:70:5.40 1779556020:72:0.13 1779556080:72:10.62 1779557220:71:0.13 1779557460:71:41.40 1779557640:71:133.03
        1779557700:71:220.86 1779557760:67:29.73 1779557880:67:43.07 1779557940:69:82.27 1779558000:69:34.50 1779558060:67:361.97
        1779558120:70:350.61 1779558180:70:575.34 1779558300:70:20.98 1779558420:69:67.36 1779558480:67:3.00 1779558540:67:100.00
        1779558600:70:352.41 1779558660:69:31.20 1779558720:70:981.58 1779558900:68:3.53 1779558960:68:76.22 1779559020:68:1.43
        1779559080:68:21.57 1779559140:69:218.32 1779559200:71:4862.14 1779559320:63:271.05 1779559380:68:8.02 1779559440:68:7.19
        1779559560:70:123.06 1779559620:70:27.42 1779559680:70:182.68 1779559860:70:69.25 1779559920:70:35.67 1779559980:70:79.79
        1779560100:70:89.54 1779560160:70:495.22 1779560220:70:562.94 1779560280:68:12.00 1779560340:69:808.13 1779560400:69:211.01
        1779560460:68:339.06 1779560520:68:124.46 1779560580:69:340.27 1779560700:68:207.27 1779560760:66:214.45 1779560820:68:157.01
        1779560880:68:245.85 1779560940:68:298.11 1779561000:67:69.60 1779561060:71:46.92 1779561120:72:541.95 1779561180:70:65.69
        1779561240:71:136.93 1779561300:71:49.58 1779561360:71:71.23 1779561420:67:22.46 1779561480:72:480.85 1779561540:68:28.70
        1779561600:68:72.70 1779561660:68:476.67 1779561720:68:307.69 1779561780:68:817.02 1779561840:68:377.89 1779561900:67:161.02
        1779561960:71:68.69 1779562020:68:94.00 1779562140:68:122.08 1779562200:70:139.80 1779562260:70:282.90 1779562320:71:1486.43
        1779562380:66:112.57 1779562440:70:909.73 1779562500:67:216.55 1779562560:68:496.79 1779562620:70:558.85 1779562680:65:261.46
        1779562740:72:200.61 1779562800:62:25.25 1779562860:72:240.17 1779562920:72:274.95 1779562980:76:161.94 1779563040:84:716.68
        1779563100:83:302.34 1779563160:79:66.53 1779563220:85:82.86 1779563460:87:6.60 1779563520:83:316.99 1779563580:84:170.68
        1779563640:85:291.09 1779563700:82:1308.10 1779563760:88:119.00 1779563820:91:33.03 1779563880:84:246.24 1779563940:83:274.95
        1779564000:82:486.13 1779564060:70:457.15 1779564120:75:283.72 1779564180:76:1835.29 1779564240:76:1303.99 1779564300:76:712.78
        1779564360:80:3.43 1779564420:74:27.61 1779564480:70:12.64 1779564540:75:185.12 1779564660:70:35.31 1779564720:68:420.05
        1779564780:74:749.87 1779564840:72:195.00 1779564900:80:362.62 1779564960:77:50.18 1779565020:76:12.94 1779565080:77:301.87
        1779565140:79:90.01 1779565260:80:32.00 1779565320:73:610.26 1779565380:81:462.87 1779565500:72:106.20 1779565560:75:5.00
        1779565620:78:96.00 1779565680:76:12.64 1779565740:69:86.29 1779565860:73:13.44 1779565980:74:17.91 1779566040:75:0.39
        1779566100:82:644.47 1779566160:85:233.23 1779566340:84:63.00 1779566460:86:0.39 1779566520:85:62.00 1779566640:77:17.89
        1779566760:82:61.35 1779567000:86:57.74 1779567060:80:8.00 1779567180:86:8.00 1779567300:86:17.21 1779567360:80:1160.63
        1779567420:88:196.46 1779567480:91:33.00 1779567960:85:123.00 1779568020:81:12.65 1779568140:90:16.00 1779568200:95:388.84
        1779568380:95:5.04 1779568440:95:21.04 1779568620:83:334.45 1779568680:81:97.62 1779568740:82:987.13 1779568800:76:3.76
        1779568860:77:220.70 1779568920:77:118.14 1779568980:81:183.30 1779569040:79:164.50 1779569100:80:59.67 1779569220:86:16.10
        1779569280:91:260.53 1779569340:98:732.24 1779569400:91:39.24 1779569460:97:505.02 1779569520:93:765.35 1779569580:97:133.76
        1779569700:97:9.01 1779569880:97:5.00 1779569940:99:20.67 1779570000:97:753.86 1779570060:98:1.01 1779570180:98:111.41
        1779570240:97:24.00 1779570300:99:797.99 1779570480:99:156.10 1779570660:99:226.62 1779570720:99:0.13 1779570900:99:151.84
        1779571020:99:71.46 1779571080:99:79.93 1779571140:99:5561.07 1779571200:99:109.33 1779571260:99:116.79 1779571320:99:14.38
        1779571620:99:10.35 1779571740:99:54.65 1779571800:99:44.57 1779571860:99:21.57 1779572100:99:71.91 1779572160:99:13.16
        1779572220:99:21.79 1779572400:99:32.39 1779572460:99:43.67 1779573000:99:397.38 1779573120:99:725.42 1779573300:99:5.67
        1779573840:99:14.18 1779573900:99:387.75 1779573960:99:32.84 1779574020:99:147.00 1779574140:99:54.81 1779574260:99:27.60
        1779574380:99:1349.77 1779574680:99:49.40 1779574980:99:339.99 1779575100:99:761.39 1779575220:99:49.04
        """

    private static let syracuseRaw = """
        1779477000:33:58.60 1779477300:33:145.06 1779480660:33:148.77 1779482100:34:850.53 1779483060:33:55.07 1779483300:30:3.42
        1779484740:33:14.47 1779485340:38:12.84 1779486120:31:21.79 1779490080:34:14.19 1779491520:33:57.89 1779491760:33:144.72
        1779493980:32:5.96 1779496020:32:29.83 1779497580:33:237.74 1779499560:32:14.91 1779500340:33:28.94 1779501120:32:57.27
        1779501180:32:89.49 1779502800:32:20.88 1779502920:33:146.01 1779505440:32:1.00 1779506820:36:59.59 1779506880:37:132.24
        1779507120:31:69.02 1779507240:37:52.00 1779507300:37:39.00 1779507780:38:449.92 1779508260:31:71.25 1779508620:36:54.53
        1779509220:36:16.80 1779509940:36:64.00 1779510180:36:13.29 1779511740:36:186.10 1779511980:35:68.32 1779512220:36:67.97
        1779512820:36:265.86 1779512880:36:3.24 1779513780:36:198.01 1779514620:36:238.94 1779514740:36:53.92 1779515160:36:130.27
        1779519540:36:34.56 1779520980:36:398.80 1779522600:36:5.45 1779525060:36:181.00 1779527160:36:11.96 1779528660:36:74.44
        1779528900:39:453.70 1779533160:37:64.71 1779533820:38:127.34 1779534180:38:131.91 1779537540:39:364.73 1779538560:39:123.39
        1779539040:55:1080.70 1779539160:34:12.00 1779539580:36:178.25 1779540060:34:7.00 1779540720:35:14.18 1779540960:35:76.51
        1779541020:35:54.65 1779541080:35:13.66 1779542280:36:26.58 1779542700:36:26.05 1779542880:38:147.22 1779543540:40:25.00
        1779543960:40:232.00 1779544020:39:41.62 1779544320:41:46.89 1779544740:41:23.42 1779544980:39:7.37 1779545040:34:146.89
        1779545160:40:47.98 1779545520:38:64.00 1779545820:73:3842.78 1779546120:43:45.89 1779546180:43:112.36 1779546660:33:377.09
        1779546840:41:235.37 1779546960:34:37.00 1779547020:34:17.11 1779547260:34:28.11 1779547320:34:14.05 1779547500:34:318.11
        1779547680:34:22.49 1779547740:34:70.28 1779547800:34:14.05 1779547980:34:28.11 1779548040:34:28.11 1779548100:34:28.11
        1779548160:41:83.57 1779548280:34:9.00 1779548400:34:136.55 1779548520:34:356.24 1779548580:34:28.11 1779548640:34:59.03
        1779548700:30:92.34 1779549060:34:28.11 1779549120:34:86.02 1779549180:34:295.17 1779549240:34:104.01 1779549420:37:2.58
        1779549480:37:133.57 1779549540:37:103.54 1779549600:36:156.71 1779549720:37:78.43 1779549960:37:23.29 1779550020:38:128.90
        1779550080:37:51.77 1779550200:37:52.71 1779550260:37:49.18 1779550680:36:818.01 1779550860:36:83.39 1779550920:36:52.26
        1779551040:35:13.66 1779551280:36:316.29 1779551340:36:26.58 1779551400:36:26.58 1779551460:35:26.00 1779551640:36:269.93
        1779551880:36:163.87 1779551940:36:24.99 1779552000:36:10.62 1779552060:36:13.29 1779552120:36:304.41 1779552180:36:66.46
        1779552360:35:136.64 1779552420:36:67.93 1779552480:36:26.58 1779552780:35:4.00 1779552840:35:54.65 1779552900:35:40.58
        1779552960:36:174.39 1779553140:36:13.29 1779553200:36:13.29 1779553260:36:390.82 1779553320:35:491.91 1779553380:35:106.57
        1779553440:35:187.52 1779553500:35:2.40 1779553860:33:44.14 1779553920:32:59.27 1779553980:33:72.36 1779554280:33:28.68
        1779554340:33:148.91 1779554460:33:42.83 1779554580:33:86.82 1779554700:33:728.38 1779554760:32:2.98 1779555180:34:1442.69
        1779555240:33:5.78 1779555360:34:57.72 1779555540:34:56.22 1779555600:34:11.24 1779555660:34:28.62 1779555780:33:5.78
        1779555840:34:19.67 1779555900:34:106.82 1779555960:34:2.75 1779556080:34:8.43 1779556140:34:177.10 1779556200:34:42.16
        1779556320:34:28.11 1779556380:34:337.00 1779556440:34:56.22 1779556740:34:4.21 1779556800:34:140.56 1779556860:33:56.63
        1779556920:33:13.00 1779556980:34:352.03 1779557160:34:42.16 1779557220:34:28.11 1779557400:34:25.30 1779557460:34:70.28
        1779557520:34:16.86 1779557580:34:27.00 1779557640:36:1398.63 1779557760:35:2.73 1779557820:35:8.19 1779557880:36:53.53
        1779557940:36:277.29 1779558000:36:26.58 1779558060:36:25.00 1779558180:33:20.26 1779558240:33:28.94 1779558300:36:414.39
        1779558420:36:103.86 1779558480:36:2.65 1779558540:37:233.91 1779558600:36:240.91 1779558660:36:65.39 1779558720:36:451.82
        1779558780:33:28.94 1779558900:36:26.58 1779558960:37:432.28 1779559020:37:113.69 1779559080:37:258.85 1779559140:37:157.32
        1779559200:36:157.43 1779559260:36:177.74 1779559380:36:745.82 1779559440:35:407.42 1779559500:32:780.82 1779559560:32:196.62
        1779559620:35:3372.29 1779559680:34:708.86 1779559740:34:665.92 1779559800:34:782.33 1779559920:32:320.04 1779559980:34:684.24
        1779560040:34:455.43 1779560100:35:886.36 1779560160:36:3213.92 1779560220:34:1292.25 1779560280:35:70.05 1779560340:35:175.91
        1779560400:36:746.82 1779560460:35:213.15 1779560520:36:419.21 1779560580:36:117.28 1779560640:35:1290.57 1779560700:35:1192.21
        1779560760:36:649.74 1779560820:36:276.40 1779560880:36:2530.32 1779560940:36:99.83 1779561000:36:2599.50 1779561060:37:744.44
        1779561120:36:248.10 1779561180:36:248.66 1779561240:36:360.70 1779561300:35:254.86 1779561360:35:789.86 1779561420:30:25.79
        1779561480:35:707.77 1779561540:35:50.34 1779561600:35:51.92 1779561660:35:1259.21 1779561720:35:567.66 1779561780:35:815.28
        1779561840:36:813.57 1779561900:36:391.24 1779561960:35:192.52 1779562020:34:707.36 1779562080:34:143.30 1779562140:35:178.80
        1779562200:36:498.96 1779562260:36:385.85 1779562320:36:2207.81 1779562380:37:456.09 1779562440:36:685.88 1779562500:37:211.63
        1779562560:36:165.68 1779562620:33:820.14 1779562680:41:1454.78 1779562740:37:479.18 1779562800:37:220.18 1779562860:30:545.26
        1779562920:33:361.24 1779562980:27:836.93 1779563040:24:576.51 1779563100:32:1239.91 1779563160:24:110.73 1779563220:20:828.33
        1779563280:21:137.53 1779563340:20:22.62 1779563400:12:869.69 1779563460:16:152.57 1779563520:55:3976.23 1779563580:19:178.50
        1779563640:22:183.19 1779563700:23:691.95 1779563760:11:691.51 1779563820:14:963.88 1779563880:21:696.70 1779563940:22:902.23
        1779564000:23:917.12 1779564060:32:769.28 1779564120:34:273.03 1779564180:30:1409.37 1779564240:29:2027.50 1779564300:28:1030.33
        1779564360:31:462.01 1779564420:32:238.02 1779564480:33:191.36 1779564540:35:225.78 1779564600:35:393.47 1779564660:36:1287.81
        1779564720:37:236.12 1779564780:26:1777.37 1779564840:26:1272.16 1779564900:28:537.33 1779564960:34:110.40 1779565080:34:211.12
        1779565140:29:65.28 1779565200:30:232.95 1779565260:24:277.66 1779565320:23:1518.08 1779565380:27:162.94 1779565440:23:49.50
        1779565500:32:142.27 1779565560:29:31.45 1779565620:33:355.17 1779565680:33:62.80 1779565740:29:40.70 1779565800:32:123.90
        1779565860:33:66.21 1779565920:30:52.03 1779566040:31:15.08 1779566100:22:1339.93 1779566160:16:51.23 1779566220:18:293.24
        1779566280:25:168.74 1779566340:13:322.94 1779566400:14:145.87 1779566460:16:205.92 1779566520:24:266.65 1779566580:29:97.39
        1779566640:26:786.94 1779566700:24:308.58 1779566760:20:120.79 1779566820:20:27.35 1779566880:19:256.18 1779567000:17:8.00
        1779567060:20:79.10 1779567120:19:74.70 1779567180:18:34.26 1779567240:19:255.03 1779567300:18:60.53 1779567360:21:73.00
        1779567420:13:655.43 1779567480:13:280.36 1779567540:18:63.19 1779567600:21:265.40 1779567660:7:19.69 1779567780:13:306.71
        1779567840:18:534.74 1779567900:18:219.12 1779567960:20:437.74 1779568020:17:230.51 1779568080:19:128.33 1779568140:20:980.86
        1779568200:5:476.98 1779568260:15:709.96 1779568320:12:247.42 1779568380:11:15.69 1779568440:10:314.00 1779568500:12:142.50
        1779568560:17:456.88 1779568620:19:119.32 1779568680:20:214.01 1779568740:31:3340.46 1779568800:30:1127.72 1779568860:33:542.93
        1779568920:28:720.46 1779568980:21:313.61 1779569040:23:617.94 1779569100:26:179.27 1779569160:22:354.51 1779569220:14:73.04
        1779569280:10:1281.68 1779569340:7:277.44 1779569400:11:248.77 1779569460:8:773.60 1779569520:2:1268.52 1779569580:3:334.47
        1779569640:2:41.11 1779569700:9:252.50 1779569820:3:41.78 1779569880:1:535.86 1779569940:5:77.03 1779570000:7:1630.53
        1779570060:1:298.89 1779570120:4:13.29 1779570180:4:25.00 1779570240:1:1037.80 1779570360:1:935.19 1779570540:1:2500.00
        1779570780:1:46.75 1779571260:1:354.42 1779571440:1:93.51 1779572100:1:93.51 1779572940:1:187.03 1779574380:1:258.11
        """

    private static func decode(_ raw: String) -> [Close] {
        raw.split(whereSeparator: { $0 == " " || $0 == "\n" }).compactMap { token -> Close? in
            let parts = token.split(separator: ":")
            guard parts.count == 3, let at = Int(parts[0]), let cents = Int(parts[1]) else { return nil }
            return Close(at: at, cents: cents, volume: String(parts[2]))
        }
    }

    private static let notreDameCloses = decode(notreDameRaw)
    private static let syracuseCloses = decode(syracuseRaw)
    private static let missingClose = Close(at: 0, cents: 0, volume: "")

    private static func closes(_ team: Team) -> [Close] { team == .notreDame ? notreDameCloses : syracuseCloses }
    private static func close(_ team: Team, at: Int) -> Close? { closes(team).first { $0.at == at } }
    private static func baseline(_ team: Team) -> Close { close(team, at: baselineAt) ?? missingClose }
    private static func liveClose(_ team: Team) -> Close { close(team, at: liveCutoff) ?? missingClose }
    private static func lastClose(_ team: Team) -> Close { closes(team).last ?? missingClose }

    /// CONSTRUCTED owner words (Pacific time) for the ARCHIVED minutes named here.
    private static let clocks: [Int: String] = [
        1779477000: "May 22, 12:10 PM PDT",
        1779559560: "May 23, 11:06 AM PDT",
        1779562440: "May 23, 11:54 AM PDT",
        1779562800: "May 23, 12:00 PM PDT",
        1779563280: "May 23, 12:08 PM PDT",
        1779566100: "May 23, 12:55 PM PDT",
        1779574380: "May 23, 3:13 PM PDT",
        1779575220: "May 23, 3:27 PM PDT",
    ]

    private static func clock(_ at: Int) -> String { clocks[at] ?? "Recorded minute" }

    private static let baselineProvenance = "May 23, 11:54 AM PDT · last trade before the listed start"

    /// CONSTRUCTED owner coordinate: minutes from the listing.
    private static func x(_ at: Int) -> Double { Double(at - listedStart) / 60 }
    private static func pointID(_ team: Team, _ at: Int) -> String { "\(team.rawValue).\(at)" }
    private static func figure(_ close: Close) -> String { "\(close.cents)%" }
    private static func probability(_ close: Close) -> Double { Double(close.cents) / 100 }

    /// Hollow before the listing, filled after it — the reference's marks.
    private static func point(_ team: Team, _ close: Close) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: pointID(team, close.at), x: x(close.at), probability: probability(close),
                               style: close.at < listedStart ? .hollow : .filled)
    }

    // MARK: History

    private enum Window {
        case all
        case match
    }

    /// What the owner admits for a phase: before play only minutes strictly
    /// before the listing; the CONSTRUCTED live frame through its cutoff; at
    /// the final every retained minute. `match` keeps the hour before the
    /// listing onward.
    private static func admitted(_ team: Team, _ phase: Phase, _ window: Window) -> [Close] {
        closes(team).filter { close in
            let inPhase: Bool
            switch phase {
            case .before: inPhase = close.at < listedStart
            case .during: inPhase = close.at <= liveCutoff
            case .final: inPhase = true
            }
            return inPhase && (window == .all || close.at >= listedStart - 3600)
        }
    }

    /// The owner's runs: only adjacent traded minutes share a run, so every
    /// real gap stays a gap. Nothing is filled.
    private static func runs(_ team: Team, _ frame: [Close]) -> [FieldHistoryRun10868] {
        var groups: [[Close]] = []
        for close in frame {
            if let last = groups.last?.last, close.at - last.at == 60 {
                groups[groups.count - 1].append(close)
            } else {
                groups.append([close])
            }
        }
        return groups.map { group in
            FieldHistoryRun10868(id: "run.\(pointID(team, group[0].at))", points: group.map { point(team, $0) })
        }
    }

    private static let noTradeHere = "No trade in this minute"
    private static let unbound = "Not recorded at this minute"
    private static let noTrades = "No retained trades in this view"

    private static func action(_ id: String, _ label: String) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: true)
    }

    private static func observation(_ team: Team, _ close: Close, provenance: String? = nil) -> FieldHistoryReading10868 {
        .observation(pointID: pointID(team, close.at), figure: figure(close), provenance: provenance ?? clock(close.at))
    }

    /// The owner's default recorded observation per phase: the pre-match
    /// close before play, the live cutoff close during, the last close after.
    private static func defaultRecorded(_ team: Team, _ phase: Phase) -> Close {
        switch phase {
        case .before: baseline(team)
        case .during: liveClose(team)
        case .final: lastClose(team)
        }
    }

    private static let yTicks: [FieldHistoryTick10868] = [
        FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.25, lines: ["25%"]),
        FieldHistoryTick10868(value: 0.5, lines: ["50%"]), FieldHistoryTick10868(value: 0.75, lines: ["75%"]),
        FieldHistoryTick10868(value: 1, lines: ["100%"]),
    ]

    private static let listedGuide = FieldHistoryGuide10868(id: "listed", x: 0, label: "Listed start · not the faceoff")

    /// `inspect`: the owner's held inspection at one exact minute, where each
    /// team shows its own close or the owner's no-trade words. The pre-match
    /// minute itself is the same observation as the pre-match reading, so the
    /// owner collapses it to one slot; any other minute keeps both slots.
    private static func history(_ phase: Phase, window: Window? = nil, inspect: Int? = nil, omit: Set<String> = [],
                                absent: Bool = false, plotHeight: CGFloat = 302, choose: Bool = false,
                                keyContext: FieldHistoryKeyContext10868? = nil) -> FieldHistoryInput10868 {
        let shown = window ?? (phase == .final ? .match : .all)
        var frames: [Team: [Close]] = [:]
        for team in Team.allCases {
            frames[team] = admitted(team, phase, shown).filter { !omit.contains(pointID(team, $0.at)) }
        }
        func series(_ team: Team) -> FieldHistorySeries10868 {
            let frame = frames[team] ?? []
            let last = defaultRecorded(team, phase)
            var recorded = observation(team, last)
            if let inspect, let hit = frame.first(where: { $0.at == inspect }) {
                recorded = observation(team, hit)
            }
            var built = FieldHistorySeries10868(
                id: team.rawValue, name: name(team), shape: shape(team), tint: tint(team),
                runs: runs(team, frame), links: [], labelPointID: pointID(team, last.at),
                before: observation(team, baseline(team), provenance: baselineProvenance), recorded: recorded,
                absentWords: frame.isEmpty ? noTrades : nil,
                choose: choose ? action("choose.\(team.rawValue)", "Show \(name(team))") : nil)
            if team == .syracuse { built.keyContext = keyContext }
            return built
        }
        let readout: FieldHistoryReadoutIntent10868
        if let inspect {
            readout = inspect == baselineAt
                ? .singleBefore(label: "Pre-match chance · inspected")
                : .beforeAndInspected(beforeLabel: "Pre-match", inspectedLabel: "Inspected")
        } else {
            switch phase {
            case .before: readout = .singleBefore(label: "Pre-match chance")
            case .during: readout = .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Recorded · constructed live")
            case .final: readout = .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Last recorded")
            }
        }
        var inspection: FieldHistoryInspection10868?
        if let inspect {
            var selections: [String: FieldHistorySelection10868] = [:]
            for team in Team.allCases {
                if let hit = frames[team]?.first(where: { $0.at == inspect }) {
                    selections[team.rawValue] = .point(id: pointID(team, inspect), spoken: figure(hit))
                } else {
                    selections[team.rawValue] = .absent(words: noTradeHere)
                }
            }
            inspection = FieldHistoryInspection10868(
                x: x(inspect), caption: "Inspected \(clock(inspect))", selections: selections, choices: [],
                choicePresentation: .buttons(groupLabel: "Recorded minutes"),
                note: "Only trades in this exact minute are shown.")
        }
        let lower: Double = shown == .match ? -60 : x(firstAt)
        let startWords = shown == .match ? ["May 23", "10:55 AM"] : ["May 22", "12:10 PM"]
        let upper: Double
        let endWords: [String]
        switch phase {
        case .before:
            upper = 0
            endWords = ["May 23", "11:55 AM"]
        case .during:
            upper = x(liveCutoff)
            endWords = ["May 23", "12:55 PM"]
        case .final:
            upper = x(notreDameLastAt)
            endWords = ["May 23", "3:27 PM"]
        }
        let windows = FieldHistoryWindows10868(groupLabel: "History period", choices: [
            FieldHistoryWindowChoice10868(action: action("window.match", "Around the match"), isSelected: shown == .match),
            FieldHistoryWindowChoice10868(action: action("window.all", "All captured trades"), isSelected: shown == .all),
        ])
        let caption: String
        switch phase {
        case .before: caption = "Last trades before the listed start · Pacific time"
        case .during: caption = "Recorded trades through the constructed live frame · Pacific time"
        case .final: caption = "Recorded trades · Pacific time"
        }
        return FieldHistoryInput10868(
            title: "Win probability history", caption: caption,
            series: [series(.notreDame), series(.syracuse)], selection: .none,
            domain: FieldHistoryDomain10868(lower: lower, upper: upper), ceiling: 1,
            yTicks: yTicks,
            xTicks: [FieldHistoryTick10868(value: lower, lines: startWords), FieldHistoryTick10868(value: upper, lines: endWords)],
            guides: [listedGuide], breaks: [], readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: before the listed start", filled: "Filled: after the listed start"),
            comparisonExplanation: nil,
            notes: ["Lines join adjacent traded minutes only; gaps mean no recorded trades.",
                    "Each line is an independent market; the two need not total 100%."],
            summary: "Notre Dame circles, Syracuse diamonds. Independent recorded probabilities, zero to 100 percent. Lines join adjacent traded minutes only.",
            plotHeight: plotHeight, unboundReadingWords: unbound, plotUnavailableWords: nil,
            windows: windows, scale: nil, moreOriginals: nil, details: nil,
            expand: action("history.expand", "Open the probability history full size"),
            inspect: inspect == nil ? nil : action("history.latest", "Return to last recorded trades"),
            previous: action("history.previous", "Previous trade minute"),
            next: action("history.next", "Next trade minute"),
            inspection: inspection,
            plotAbsence: absent
                ? FieldHistoryPlotAbsence10868(title: "Probability history unavailable",
                                               words: "No admitted trades in this update; the actual quarters stay.")
                : nil)
    }

    /// The same input with other series — every other field the owner's.
    private static func replacingSeries(_ input: FieldHistoryInput10868,
                                        _ series: [FieldHistorySeries10868]) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: input.title, caption: input.caption, series: series, selection: input.selection,
            domain: input.domain, ceiling: input.ceiling, yTicks: input.yTicks, xTicks: input.xTicks,
            guides: input.guides, breaks: input.breaks, readout: input.readout, markKey: input.markKey,
            comparisonExplanation: input.comparisonExplanation, notes: input.notes, summary: input.summary,
            plotHeight: input.plotHeight, unboundReadingWords: input.unboundReadingWords,
            plotUnavailableWords: input.plotUnavailableWords, windows: input.windows, scale: input.scale,
            moreOriginals: input.moreOriginals, details: input.details, expand: input.expand, inspect: input.inspect,
            previous: input.previous, next: input.next, inspection: input.inspection, layout: input.layout,
            probabilityLowerBound: input.probabilityLowerBound,
            probabilityRangeExplanation: input.probabilityRangeExplanation, selectedReadout: input.selectedReadout,
            inspectionRingShape: input.inspectionRingShape, plotAbsence: input.plotAbsence, showsKey: input.showsKey)
    }

    /// One series with other runs — every other field the owner's.
    private static func withRuns(_ series: FieldHistorySeries10868, _ runs: [FieldHistoryRun10868]) -> FieldHistorySeries10868 {
        FieldHistorySeries10868(
            id: series.id, name: series.name, shape: series.shape, tint: series.tint, runs: runs, links: series.links,
            labelPointID: series.labelPointID, before: series.before, recorded: series.recorded,
            absentWords: series.absentWords, choose: series.choose, keyContext: series.keyContext)
    }

    /// The same input with another readout intent or key visibility — every
    /// other field the owner's.
    private static func variant(_ input: FieldHistoryInput10868, readout: FieldHistoryReadoutIntent10868? = nil,
                                showsKey: Bool? = nil) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: input.title, caption: input.caption, series: input.series, selection: input.selection,
            domain: input.domain, ceiling: input.ceiling, yTicks: input.yTicks, xTicks: input.xTicks,
            guides: input.guides, breaks: input.breaks, readout: readout ?? input.readout, markKey: input.markKey,
            comparisonExplanation: input.comparisonExplanation, notes: input.notes, summary: input.summary,
            plotHeight: input.plotHeight, unboundReadingWords: input.unboundReadingWords,
            plotUnavailableWords: input.plotUnavailableWords, windows: input.windows, scale: input.scale,
            moreOriginals: input.moreOriginals, details: input.details, expand: input.expand, inspect: input.inspect,
            previous: input.previous, next: input.next, inspection: input.inspection, layout: input.layout,
            probabilityLowerBound: input.probabilityLowerBound,
            probabilityRangeExplanation: input.probabilityRangeExplanation, selectedReadout: input.selectedReadout,
            inspectionRingShape: input.inspectionRingShape, plotAbsence: input.plotAbsence,
            showsKey: showsKey ?? input.showsKey)
    }

    /// A CONSTRUCTED ambiguous update: the Syracuse series listed twice.
    private static func duplicated(_ input: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        replacingSeries(input, input.series + input.series.filter { $0.id == Team.syracuse.rawValue })
    }

    // MARK: Headline

    private static let headlineScope = "constructed.scope.lacrosse.match"

    private static func ref(_ team: Team) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: headlineScope, source: "kalshi", marketID: ticker(team), outcomeID: team.rawValue)
    }

    private static func slot(_ team: Team) -> FieldHeadlineSlot10868 {
        FieldHeadlineSlot10868(ref: ref(team), name: name(team), compactName: nil,
                               keyShape: team == .notreDame ? .circle : .diamond)
    }

    private static func preMatch(_ team: Team) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Pre-match chance",
                                 value: .recorded(text: figure(baseline(team)), detail: baselineProvenance))
    }

    /// CONSTRUCTED live reading: each team's close at the live cutoff.
    private static func liveRecorded(_ team: Team) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Recorded chance · constructed live",
                                 value: .recorded(text: figure(liveClose(team)), detail: clock(liveCutoff)))
    }

    private static func plan(_ team: Team, _ phase: Phase) -> FieldChooserDisplayPlan10868 {
        phase == .during ? .comparison(before: preMatch(team), later: liveRecorded(team)) : .single(preMatch(team))
    }

    /// `observation`: an owner key override for Notre Dame (the bad control).
    private static func pair(_ team: Team, _ phase: Phase, observation: String? = nil) -> FieldMovementPair10868 {
        FieldMovementPair10868(
            ref: ref(team),
            before: FieldMovementObservation10868(probability: probability(baseline(team)), reading: preMatch(team)),
            later: phase == .during
                ? FieldMovementObservation10868(probability: probability(liveClose(team)), reading: liveRecorded(team)) : nil,
            movement: nil,
            observation: observation ?? (phase == .during ? pointID(team, liveCutoff) : nil))
    }

    /// ARCHIVED final goals, as the owner's actual figure.
    private static func finalGoals(_ team: Team) -> String { team == .notreDame ? "15" : "7" }

    private static func finish(_ team: Team) -> FieldFinishPlace10868 {
        FieldFinishPlace10868(ref: ref(team), reading: FieldChooserReading10868(
            label: "Actual goals", value: .recorded(text: finalGoals(team), detail: "Final · ESPN match record")))
    }

    private static func state(_ phase: Phase) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            FieldHeadlineState10868(
                figure: "Before match", unit: nil, caption: "Listed 11:55 AM PDT · not the faceoff",
                detail: "May 23 · NCAA semifinal",
                spoken: "Before match. Listed 11:55 AM PDT, not the faceoff. May 23, NCAA semifinal.", progress: nil)
        case .during:
            FieldHeadlineState10868(
                figure: "7–4", unit: "after Q2", caption: "Constructed live example",
                detail: "Later quarters are not part of this frame",
                spoken: "Constructed live example. 7 to 4 after the second quarter. Later quarters are not part of this frame.",
                progress: nil)
        case .final:
            FieldHeadlineState10868(
                figure: "15–7", unit: nil, caption: "Notre Dame won · Final", detail: "ESPN match record · May 23",
                spoken: "Final. Notre Dame won 15 to 7. ESPN match record, May 23.", progress: nil)
        }
    }

    /// The finishes ride along in every phase; only the final reads them.
    private static func headline(_ phase: Phase, headlinePhase: FieldOutlookPhase10868? = nil,
                                 displayed: [FieldHeadlineSlot10868]? = nil,
                                 notreDameObservation: String? = nil) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: headlineScope,
            catalogue: Team.allCases.map { team in
                FieldChooserOriginal10868(
                    ref: ref(team), name: name(team), plan: plan(team, phase),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: nil, result: nil, browseStatus: "Recorded trades", accent: tint(team))
            },
            displayed: displayed ?? Team.allCases.map(slot),
            pairs: Team.allCases.map { pair($0, phase, observation: $0 == .notreDame ? notreDameObservation : nil) },
            finishes: Team.allCases.map(finish),
            state: state(phase),
            phase: headlinePhase ?? LacrosseEventPageModel10868.headlinePhase(phase),
            copy: FieldHeadlineCopy10868(
                eyebrow: "Lacrosse · NCAA semifinal · May 23", title: "Notre Dame vs Syracuse",
                graphicLabel: "Pre-match and recorded win chances", beforeLabel: "Pre-match chance",
                recordedLabel: "Recorded chance", beforeUnavailable: "Pre-match chance unavailable",
                recordedUnavailable: "No recorded chance", finishLabel: "Actual goals",
                finishUnavailable: "Goals not reported", empty: "No teams in this update",
                aboutLabel: "About this lacrosse match", aboutHint: "Opens dates and sources",
                openHint: "Opens this team’s history"),
            unavailableWords: "Team unavailable in this update")
    }

    // MARK: Actual quarters

    /// ARCHIVED (the bound scoreboard row): goals per quarter.
    private static let quarterGoals: [(notreDame: Int, syracuse: Int)] = [(4, 3), (3, 1), (2, 3), (6, 0)]
    /// CONSTRUCTED owner words: the cumulative actual score after each quarter.
    private static let cumulative: [(notreDame: String, syracuse: String)] = [("4", "3"), ("7", "4"), ("9", "7"), ("15", "7")]
    private static let ordinals = ["first", "second", "third", "fourth"]
    private static let heldMissing = "The held quarter is not in this update"

    private static func goals(_ count: Int) -> LacrosseEventPagePeriodGoals10868 {
        .reported(text: "\(count)", spoken: count == 1 ? "1 goal" : "\(count) goals", value: Double(count))
    }

    private static func period(_ index: Int) -> LacrosseEventPagePeriod10868 {
        let score = quarterGoals[index]
        let total = cumulative[index]
        let ordinal = ordinals[index]
        return LacrosseEventPagePeriod10868(
            id: "q\(index + 1)", label: "Q\(index + 1)", spokenLabel: "\(ordinal.capitalized) quarter",
            first: goals(score.notreDame), second: goals(score.syracuse), readoutLabel: "After Q\(index + 1)",
            readout: LacrosseEventPagePeriodReadout10868(
                first: total.notreDame, second: total.syracuse,
                spoken: "After the \(ordinal) quarter: Notre Dame \(total.notreDame), Syracuse \(total.syracuse)"))
    }

    /// One period with other fields; the rest unchanged.
    private static func revised(_ base: LacrosseEventPagePeriod10868, id: String? = nil,
                               second: LacrosseEventPagePeriodGoals10868? = nil, keepsReadout: Bool = true) -> LacrosseEventPagePeriod10868 {
        LacrosseEventPagePeriod10868(id: id ?? base.id, label: base.label, spokenLabel: base.spokenLabel, first: base.first,
                                   second: second ?? base.second, readoutLabel: base.readoutLabel,
                                   readout: keepsReadout ? base.readout : nil)
    }

    private static let firstTeam = LacrosseEventPagePeriodTeam10868(id: "not", name: "Notre Dame", shape: .circle, tint: notreDameTint)
    private static let secondTeam = LacrosseEventPagePeriodTeam10868(id: "syr", name: "Syracuse", shape: .diamond, tint: syracuseTint)

    /// The final's four quarters held at Q4; the CONSTRUCTED live frame's
    /// first two held at Q2, with its own eyebrow, title, notes and report
    /// label — none describes a finished match.
    private static func periods(_ phase: Phase, periods: [LacrosseEventPagePeriod10868]? = nil,
                                 selection: LacrosseEventPagePeriodSelection10868? = nil,
                                 ceiling: Double = 6) -> LacrosseEventPagePeriodInput10868 {
        let live = phase == .during
        return LacrosseEventPagePeriodInput10868(
            phase: phase,
            eyebrow: live ? "Actual goals · constructed live example" : "Actual goals · by quarter",
            title: live ? "Quarters so far" : "A 6–0 finish",
            keyLabel: "Actual goals", first: firstTeam, second: secondTeam,
            periods: periods ?? (live ? (0..<2).map(period) : (0..<4).map(period)),
            scale: LacrosseEventPagePeriodScale10868(ceiling: ceiling, words: "Goals in each quarter · 0–6 scale"),
            selection: selection ?? .period(id: live ? "q2" : "q4", missingWords: heldMissing),
            notDrawn: "Beyond the shared goal scale; not drawn", empty: "No quarters reported yet",
            readoutPrompt: "Choose a quarter to see the score after it",
            readoutUnavailable: "Score after this quarter not reported",
            chooseHint: "Shows the actual score after this quarter",
            caption: live ? nil : "After Q3: Notre Dame 9–7 Syracuse. Q4: 6–0.",
            notes: live
                ? ["Constructed live example: later quarters are not part of this frame.",
                   "No quarter is assigned to a probability time."]
                : ["Bars are goals within each quarter; the readout is the cumulative actual score after the chosen quarter.",
                   "No quarter is assigned to a probability time."],
            reportLabel: live ? "Report so far" : "Quarter scores & source",
            expandLabel: "Open the quarter scores full size")
    }

    // MARK: Text, copy and page

    private static func about(_ phase: Phase) -> LacrosseEventPageText10868 {
        var sections = [
            LacrosseEventPageSection10868(title: "Dates", paragraphs: [
                "The listed start, May 23, 11:55 AM PDT, is not the actual faceoff. Actual faceoff and quarter-end times are unavailable.",
            ]),
            LacrosseEventPageSection10868(title: "Chances", paragraphs: [
                "Before match is the last positive-volume traded minute strictly before the listed start; both contracts traded in the minute ending 11:54 AM PDT, at 70% and 36%.",
                "These are independent market probabilities, not a normalized blend: together they make 106%.",
            ]),
            LacrosseEventPageSection10868(title: "Archive", paragraphs: [
                "The requested archive begins the previous day, not at market inception. Gaps remain gaps; no trade is filled in.",
            ]),
        ]
        if phase == .during {
            sections.append(LacrosseEventPageSection10868(title: "Constructed live example", paragraphs: [
                "This live frame is constructed: its probability cutoff and its quarters are not synchronized.",
            ]))
        }
        return LacrosseEventPageText10868(title: "About this lacrosse match", sections: sections)
    }

    private static func source() -> LacrosseEventPageText10868 {
        LacrosseEventPageText10868(title: "History & source details", sections: [
            LacrosseEventPageSection10868(title: nil, paragraphs: [
                "Only positive-volume traded minutes are drawn; times are minute ends, not exact trades or scoring times.",
                "Each original keeps its own settlement, postponement and declared-tie rules; last trades are not settlement observations.",
            ]),
        ])
    }

    /// Before play: no result. The CONSTRUCTED live frame: only its two
    /// admitted quarters and no link out. The final: the record with its link.
    private static func report(_ phase: Phase) -> LacrosseEventPageText10868 {
        switch phase {
        case .before:
            LacrosseEventPageText10868(title: "Match report", sections: [
                LacrosseEventPageSection10868(title: nil, paragraphs: [
                    "A retrospective before-play reconstruction; no result is shown in this phase.",
                ]),
            ])
        case .during:
            LacrosseEventPageText10868(title: "Quarters so far · constructed live example", sections: [
                LacrosseEventPageSection10868(title: nil, paragraphs: [
                    "Constructed live example: Notre Dame leads Syracuse 7–4 after two quarters, 4–3 and 3–1. Later quarters are not part of this frame.",
                ]),
            ])
        case .final:
            LacrosseEventPageText10868(title: "Notre Dame 15–7 Syracuse", sections: [
                LacrosseEventPageSection10868(title: nil, paragraphs: [
                    "The match record reports Notre Dame 15–Syracuse 7. Quarter totals: Notre Dame 4, 3, 2, 6; Syracuse 3, 1, 3, 0.",
                    "The two-goal Q3 lead and the six-goal Q4 shutout follow those actual totals. No live scoreboard replay or shot timing is claimed.",
                ]),
            ], link: LacrosseEventPageLink10868(id: "record.link", label: "ESPN match record"))
        }
    }

    private static func reader(_ phase: Phase) -> LacrosseEventPageReaderHeader10868 {
        switch phase {
        case .before: LacrosseEventPageReaderHeader10868(title: "Notre Dame vs Syracuse · Before match", state: "NCAA semifinal · May 23")
        case .during: LacrosseEventPageReaderHeader10868(title: "Notre Dame vs Syracuse · Constructed live example", state: "NCAA semifinal · May 23")
        case .final: LacrosseEventPageReaderHeader10868(title: "Notre Dame vs Syracuse · Final 15–7", state: "NCAA semifinal · May 23")
        }
    }

    private static let copy = LacrosseEventPageCopy10868(
        headlineUnavailable: "Match chances unavailable in this update.",
        comparisonLabel: "Win chances, each with its own date",
        sourceLabel: "History & source details", allPropsLabel: "All 2 captured markets",
        periodsUnavailable: "Quarter scores unavailable")

    /// CONSTRUCTED owner heights: standard, and enlarged at accessibility sizes.
    private static let ownerHeights = LacrosseEventPageHistoryHeights10868(standard: 302, enlarged: 380)

    /// Every input is supplied in every phase — the final's quarters before
    /// play too — so only the page phase and each leaf's own phase decide.
    private static func page(_ phase: Phase, history: FieldHistoryInput10868? = nil,
                             headline: FieldHeadlineInput10868? = nil, periods: LacrosseEventPagePeriodInput10868? = nil,
                             withoutQuarters: Bool = false, heights: LacrosseEventPageHistoryHeights10868? = nil,
                             withoutHeights: Bool = false) -> LacrosseEventPageInput10868 {
        LacrosseEventPageInput10868(
            phase: phase, reader: reader(phase), headline: headline ?? Self.headline(phase),
            notice: "Archived history · no current probability",
            history: history ?? Self.history(phase),
            historyHeights: withoutHeights ? nil : (heights ?? ownerHeights),
            periods: withoutQuarters ? nil : (periods ?? Self.periods(phase == .before ? .final : phase)),
            about: about(phase), source: source(), report: report(phase), copy: copy)
    }

    // MARK: Originals

    private static let originalsScope = "constructed.scope.lacrosse.originals"

    private static func identity(_ team: Team) -> OriginalMarketDetails9483.Identity {
        OriginalMarketDetails9483.Identity(source: "kalshi", market: ticker(team), side: "Yes")
    }

    private static func selection(_ team: Team) -> OriginalMarketDetails9483.Selection {
        OriginalMarketDetails9483.Selection(scope: originalsScope, identity: identity(team))
    }

    /// ARCHIVED, verbatim: each market's `rules_primary`.
    private static let rulesPrimaryNotreDame = "If Notre Dame wins the Syracuse vs Notre Dame men's college lacrosse game originally scheduled for May 23, 2026, then the market resolves to Yes."
    private static let rulesPrimarySyracuse = "If Syracuse wins the Syracuse vs Notre Dame men's college lacrosse game originally scheduled for May 23, 2026, then the market resolves to Yes."
    /// ARCHIVED, verbatim: the `rules_secondary` both markets carry.
    private static let rulesSecondary = "The following market refers to the team who wins the Syracuse vs Notre Dame men's college lacrosse game originally scheduled for May 23, 2026. If this game is postponed/delayed and played within 14 days of the originally scheduled start time, the market will remain open and close after the rescheduled game has finished. If a postponed/cancelled game is not played or is rescheduled further than 14 days out, the market will resolve to a fair price for each team in accordance with the rules. If the game is declared a tie, the market will resolve to 50/50 for both teams."
    /// ARCHIVED `markets[].title`, the same for both markets.
    private static let marketTitle = "Syracuse vs Notre Dame Winner?"

    private static func rulesPrimary(_ team: Team) -> String {
        team == .notreDame ? rulesPrimaryNotreDame : rulesPrimarySyracuse
    }

    private static func mode(_ phase: Phase) -> OriginalMarketDetails9483.Mode {
        switch phase {
        case .before: .pregame
        case .during: .comparison(.recorded)
        case .final: .result
        }
    }

    /// `grade: false` is an owner without that contract's own result.
    private static func original(_ team: Team, _ phase: Phase, grade: Bool = true,
                                 blankTitle: Bool = false) -> OriginalMarketDetails9483.Original {
        let pre = baseline(team)
        let live = liveClose(team)
        let last = lastClose(team)
        var original = OriginalMarketDetails9483.Original(
            identity: identity(team), title: blankTitle ? " " : marketTitle, outcome: name(team), mode: mode(phase),
            pregame: .value(figure(pre), placement: probability(pre), provenance: baselineProvenance),
            later: phase == .during
                ? .value(figure(live), placement: probability(live), provenance: "\(clock(liveCutoff)) · constructed live frame")
                : nil,
            grade: phase == .final && grade
                ? OriginalMarketDetails9483.Grade(words: team == .notreDame ? "Won" : "Lost",
                                                  provenance: "Contract finalized May 23, 3:35 PM PDT")
                : nil,
            about: OriginalMarketDetails9483.About(
                source: "Kalshi", rules: .verified([rulesPrimary(team), rulesSecondary]),
                provenance: [OriginalMarketDetails9483.Row(label: "Listed start", value: "May 23, 11:55 AM PDT · not the faceoff"),
                             OriginalMarketDetails9483.Row(label: "Market", value: ticker(team))],
                historicalQuote: phase == .final
                    ? OriginalMarketDetails9483.HistoricalQuote(text: figure(last), recorded: clock(last.at)) : nil))
        original.beforeLabel = "Pre-match chance"
        return original
    }

    private static func catalogue(_ phase: Phase,
                                  originals: [OriginalMarketDetails9483.Original]? = nil) -> OriginalMarketDetails9483.Catalogue {
        OriginalMarketDetails9483.Catalogue(scope: originalsScope,
                                            originals: originals ?? Team.allCases.map { original($0, phase) })
    }

    /// The held original's reader: the same runs and gaps the main history
    /// draws for it, in the mini composition the Details host.
    private static func recordedContext(_ team: Team, _ phase: Phase) -> OriginalMarketDetails9483.RecordedHistory {
        let frame = admitted(team, phase, .all)
        let last = defaultRecorded(team, phase)
        let upper: Double
        switch phase {
        case .before: upper = 0
        case .during: upper = x(liveCutoff)
        case .final: upper = x(notreDameLastAt)
        }
        let mini = FieldHistoryInput10868(
            title: "\(name(team)) to win · recorded history", caption: "Recorded trades · Pacific time",
            series: [FieldHistorySeries10868(
                id: team.rawValue, name: name(team), shape: shape(team), tint: tint(team), runs: runs(team, frame),
                links: [], labelPointID: nil, before: observation(team, baseline(team), provenance: baselineProvenance),
                recorded: observation(team, last), absentWords: frame.isEmpty ? noTrades : nil, choose: nil)],
            selection: .series(id: team.rawValue, missingWords: "Market history unavailable"),
            domain: FieldHistoryDomain10868(lower: x(firstAt), upper: upper), ceiling: 1, yTicks: yTicks, xTicks: [],
            guides: [listedGuide], breaks: [],
            readout: phase == .before
                ? .singleBefore(label: "Pre-match chance")
                : .beforeAndRecorded(beforeLabel: "Pre-match", recordedLabel: "Last recorded"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: before the listed start", filled: "Filled: after the listed start"),
            comparisonExplanation: nil, notes: [], summary: "\(name(team)) recorded probabilities. Gaps mean no trades.",
            plotHeight: 180, unboundReadingWords: unbound, plotUnavailableWords: nil, windows: nil, scale: nil,
            moreOriginals: nil, details: nil, expand: nil, inspect: nil, previous: nil, next: nil, inspection: nil,
            layout: .expanded, showsKey: false)
        var readings = [OriginalMarketDetails9483.RecordedReading(
            label: "Pre-match chance", marker: .hollow,
            reading: .value(figure(baseline(team)), placement: probability(baseline(team)), provenance: baselineProvenance))]
        if phase != .before {
            readings.append(OriginalMarketDetails9483.RecordedReading(
                label: phase == .during ? "Recorded · constructed live" : "Last recorded", marker: .solid,
                reading: .value(figure(last), placement: probability(last), provenance: clock(last.at))))
        }
        return OriginalMarketDetails9483.RecordedHistory(
            selection: selection(team), mode: mode(phase), seriesID: team.rawValue,
            availability: "Current probability unavailable · recorded history below", readings: readings,
            movement: nil, history: mini, finishLabel: "Actual goals",
            finish: phase == .final ? .reported(words: "\(finalGoals(team)) goals", spoken: "Actual goals \(finalGoals(team))") : nil,
            preview: nil, expand: action("original.history.expand", "Open this market’s history full size"),
            explore: action("original.history.explore", "Explore this market’s history"),
            unmatchedWords: "Recorded history unavailable for this market")
    }

    private static func originals(_ phase: Phase, selected: Team? = .notreDame,
                                  catalogue: OriginalMarketDetails9483.Catalogue? = nil,
                                  recorded: Bool = true) -> LacrosseEventPageOriginals10868 {
        LacrosseEventPageOriginals10868(
            catalogue: catalogue ?? Self.catalogue(phase), selection: selected.map(selection),
            recorded: recorded ? selected.map { recordedContext($0, phase) } : nil,
            labels: [identity(.notreDame): "Notre Dame to win", identity(.syracuse): "Syracuse to win"],
            heading: "Original markets", context: "2 captured markets",
            emptyWords: "No captured markets for this match", unavailableChoice: "Market unavailable", tint: notreDameTint)
    }

    private static func content(_ catalogue: OriginalMarketDetails9483.Catalogue?, _ team: Team) -> OriginalMarketDetails9483.Content? {
        OriginalMarketDetails9483.content(catalogue: catalogue, selection: selection(team))
    }

    private static func choices(_ originals: LacrosseEventPageOriginals10868) -> [OriginalMarketChooser9483.Choice] {
        OriginalMarketChooser9483.choices(catalogue: originals.catalogue, selection: originals.selection,
                                          labels: originals.labels, unavailableChoice: originals.unavailableChoice)
    }

    private static func slots(_ input: FieldHistoryInput10868) -> [[FieldHistoryReadoutSlot10868]] {
        input.series.map { FieldHistoryGeometry10868.readoutSlots($0, in: input) }
    }

    private static func allPoints(_ input: FieldHistoryInput10868) -> [FieldHistoryPoint10868] {
        input.series.flatMap { $0.runs.flatMap(\.points) }
    }

    // MARK: Retained score record (test-side identity check)

    private struct RetainedPeriod {
        let period: Int?
        let value: Double?
        let display: String
    }

    private struct RetainedCompetitor {
        let id: String
        let name: String
        let score: String
        let winner: Bool
        let linescores: [RetainedPeriod]
    }

    private struct RetainedCompetition {
        let id: String
        let date: String
        let completed: Bool
        let status: String
        let competitors: [RetainedCompetitor]
    }

    private struct RetainedEvent {
        let id: String
        let date: String
        let competitions: [RetainedCompetition]
    }

    /// Scoreboard linescores carry period, value and display value.
    private static func scored(_ values: [Int]) -> [RetainedPeriod] {
        values.enumerated().map { RetainedPeriod(period: $0.offset + 1, value: Double($0.element), display: "\($0.element)") }
    }

    /// Header linescores carry display values only.
    private static func displayed(_ values: [String]) -> [RetainedPeriod] {
        values.map { RetainedPeriod(period: nil, value: nil, display: $0) }
    }

    /// ARCHIVED `scoreboard.events`, in the retained order: row 0 is ANOTHER game.
    private static let scoreboardEvents: [RetainedEvent] = [
        RetainedEvent(id: "401870924", date: "2026-05-23T16:00Z", competitions: [
            RetainedCompetition(id: "401870924", date: "2026-05-23T16:00Z", completed: true, status: "STATUS_FINAL", competitors: [
                RetainedCompetitor(id: "163", name: "Princeton Tigers", score: "14", winner: true, linescores: scored([3, 3, 5, 3])),
                RetainedCompetitor(id: "150", name: "Duke Blue Devils", score: "7", winner: false, linescores: scored([2, 2, 2, 1])),
            ]),
        ]),
        RetainedEvent(id: "401870923", date: "2026-05-23T18:55Z", competitions: [
            RetainedCompetition(id: "401870923", date: "2026-05-23T18:55Z", completed: true, status: "STATUS_FINAL", competitors: [
                RetainedCompetitor(id: "87", name: "Notre Dame Fighting Irish", score: "15", winner: true, linescores: scored([4, 3, 2, 6])),
                RetainedCompetitor(id: "183", name: "Syracuse Orange", score: "7", winner: false, linescores: scored([3, 1, 3, 0])),
            ]),
        ]),
    ]

    /// ARCHIVED `header.competitions[0]` (header id 401870923).
    private static let header = RetainedCompetition(
        id: "401870923", date: "2026-05-23T18:55Z", completed: true, status: "STATUS_FINAL", competitors: [
            RetainedCompetitor(id: "87", name: "Notre Dame Fighting Irish", score: "15", winner: true,
                               linescores: displayed(["4", "3", "2", "6"])),
            RetainedCompetitor(id: "183", name: "Syracuse Orange", score: "7", winner: false,
                               linescores: displayed(["3", "1", "3", "0"])),
        ])

    /// The TEST-SIDE retained-input check, not a production parser: the exact
    /// competition and team ids, the header and the scoreboard row agreeing,
    /// four unique non-negative whole periods that sum to the final. Never an
    /// array position, never a neighbour's score.
    private static func boundQuarterGoals(_ events: [RetainedEvent], header: RetainedCompetition,
                                          competition: String, teams: [String]) -> [[Int]]? {
        guard header.id == competition, header.completed, header.status == "STATUS_FINAL" else { return nil }
        let rows = events.filter { $0.id == competition }
        guard rows.count == 1, rows[0].competitions.count == 1 else { return nil }
        let row = rows[0].competitions[0]
        guard row.id == header.id, row.date == header.date, rows[0].date == header.date,
              row.completed, row.status == "STATUS_FINAL" else { return nil }
        var bound: [[Int]] = []
        for team in teams {
            let inHeader = header.competitors.filter { $0.id == team }
            let inRow = row.competitors.filter { $0.id == team }
            guard inHeader.count == 1, inRow.count == 1 else { return nil }
            let headerTeam = inHeader[0]
            let rowTeam = inRow[0]
            guard headerTeam.name == rowTeam.name, headerTeam.score == rowTeam.score, headerTeam.winner == rowTeam.winner,
                  rowTeam.linescores.count == 4, headerTeam.linescores.map(\.display) == rowTeam.linescores.map(\.display),
                  let final = Int(rowTeam.score) else { return nil }
            var goals: [Int] = []
            for period in 1...4 {
                let matches = rowTeam.linescores.filter { $0.period == period }
                guard matches.count == 1, let value = matches[0].value, value >= 0, value == value.rounded(),
                      Int(matches[0].display) == Int(value) else { return nil }
                goals.append(Int(value))
            }
            guard goals.reduce(0, +) == final else { return nil }
            bound.append(goals)
        }
        return bound
    }

    // MARK: Reachable outputs

    /// A phrase as a whole token: no letter or digit directly before or after
    /// it, so "1%" is never found in "21%" or "100%".
    private static func mentions(_ output: String, _ fact: String) -> Bool {
        let pattern = "(?<![\\p{L}\\p{N}])" + NSRegularExpression.escapedPattern(for: fact) + "(?![\\p{L}\\p{N}])"
        return output.range(of: pattern, options: .regularExpression) != nil
    }

    /// A goal count read as a count: never inside a longer number, a
    /// percentage, a decimal or a clock — so "7" goals never matches "70%",
    /// "0.7", "7:04" or "11:57".
    private static func mentionsCount(_ output: String, _ count: String) -> Bool {
        let pattern = "(?<![\\p{N}])(?<![\\p{N}][.:])" + NSRegularExpression.escapedPattern(for: count)
            + "(?![\\p{N}%])(?![.:][\\p{N}])"
        return output.range(of: pattern, options: .regularExpression) != nil
    }

    /// Every word a reader can see or hear from one page input, collected
    /// through the same Views in every content mode with every text callback
    /// supplied: reader heading, copy, notice, the headline (page and above the
    /// full-size quarters), the comparison and history (page and full size),
    /// the quarters (page and full size, every admitted period's readout as if
    /// chosen), About, source and report content with any link, and every
    /// original's chooser, Details, About rows, rules, recorded reader and speech.
    private static func reachableOutputs(_ input: LacrosseEventPageInput10868,
                                         _ originals: LacrosseEventPageOriginals10868) -> [String] {
        let model = LacrosseEventPageModel10868(input)
        var outputs: [String] = [input.reader.title, input.copy.headlineUnavailable, input.copy.comparisonLabel]
        outputs += [input.reader.state, input.copy.sourceLabel, input.copy.allPropsLabel, model.notice,
                    model.periodsUnavailable].compactMap { $0 }
        let modes: [LacrosseEventPageMode10868] = [.page, .fullHistory, .fullPeriods, .catalogue, .original, .about, .source, .report]
        for mode in modes {
            let view = LacrosseEventPagePresentation10868(input: input, mode: mode, originals: originals,
                                                          onAbout: {}, onSource: {}, onReport: {}, onLink: { _ in },
                                                          onPeriodChoose: { _ in })
            for headline in [view.headlineContent(), view.headlineContent(reader: true)].compactMap({ $0 }) {
                outputs += headlineOutputs(headline.input)
            }
            for reader in [false, true] {
                for enlarged in [false, true] {
                    if let comparison = view.comparisonContent(reader: reader, enlarged: enlarged) {
                        outputs += comparisonOutputs(comparison)
                    }
                    outputs += historyOutputs(view.historyContent(reader: reader, enlarged: enlarged).input)
                }
            }
            for periods in [view.periodsContent(reader: false), view.periodsContent(reader: true)].compactMap({ $0 }) {
                outputs += quarterOutputs(periods)
            }
            for content in [view.aboutContent(), view.sourceContent(), view.reportContent()].compactMap({ $0 }) {
                outputs += [content.text.title] + content.text.sections.flatMap { [$0.title].compactMap { $0 } + $0.paragraphs }
                outputs += [content.link?.label].compactMap { $0 }
            }
        }
        outputs += [originals.heading, originals.emptyWords] + [originals.context].compactMap { $0 }
        outputs += choices(originals).map(OriginalMarketChooser9483.spoken)
        if let catalogue = originals.catalogue {
            for original in catalogue.originals {
                let selection = OriginalMarketDetails9483.Selection(scope: catalogue.scope, identity: original.identity)
                guard let content = OriginalMarketDetails9483.content(catalogue: catalogue, selection: selection) else { continue }
                outputs += [content.title, content.outcome, OriginalMarketDetails9483.spoken(content)]
                outputs += content.readings.flatMap { [$0.label, $0.text] + [$0.provenance].compactMap { $0 } }
                if let result = content.result { outputs += [result.words] + [result.provenance].compactMap { $0 } }
                outputs += content.about.flatMap { [$0.label, $0.value] }
                if case .verified(let paragraphs) = content.rules { outputs += paragraphs }
            }
        }
        if case .recorded(let shown)? = OriginalMarketDetails9483.recorded(
            catalogue: originals.catalogue, selection: originals.selection, context: originals.recorded, hasCallback: true) {
            outputs += [shown.availability, OriginalMarketDetails9483.spoken(shown)]
            outputs += [OriginalMarketDetails9483.resultSpoken(shown), shown.finish?.words, shown.finish?.spoken].compactMap { $0 }
            outputs += shown.content.readings.flatMap { [$0.label, $0.text] + [$0.provenance].compactMap { $0 } }
            outputs += historyOutputs(shown.history)
        }
        return outputs
    }

    private static func headlineOutputs(_ headline: FieldHeadlineInput10868) -> [String] {
        let model = FieldHeadlineModel10868(headline)
        var outputs = model.competitors.map(model.competitorSummary)
        outputs += model.competitors.flatMap { $0.metrics.compactMap(FieldChaseModel10868.figure) }
        outputs += [model.eyebrow, model.title, model.stateSummary, model.aboutLabel(canAbout: true)].compactMap { $0 }
        if let state = model.state { outputs += [state.figure] + [state.unit, state.caption, state.detail].compactMap { $0 } }
        outputs += [headline.copy.graphicLabel, headline.copy.empty] + [headline.copy.aboutHint, headline.copy.openHint].compactMap { $0 }
        return outputs
    }

    /// The comparison's drawn and spoken words, through its own reads.
    private static func comparisonOutputs(_ view: RugbyMatchEventPageComparisonPresentation10868) -> [String] {
        var outputs = [view.label]
        for entry in view.entries {
            outputs += [entry.series.name, RugbyMatchEventPageComparisonPresentation10868.spoken(entry)]
            outputs += [entry.note].compactMap { $0 }
            outputs += entry.slots.map(FieldHistoryGeometry10868.spokenSlot)
        }
        return outputs + RugbyMatchEventPageComparisonPresentation10868.figures(view.entries)
    }

    private static func historyOutputs(_ input: FieldHistoryInput10868) -> [String] {
        var outputs = [input.title, input.summary, input.unboundReadingWords]
        outputs += [input.caption, input.plotUnavailableWords, input.windows?.groupLabel,
                    input.markKey.hollow, input.markKey.filled, input.plotAbsence?.title, input.plotAbsence?.words,
                    FieldHistoryGeometry10868.selectionWords(input)].compactMap { $0 }
        outputs += input.notes + input.xTicks.flatMap(\.lines) + input.yTicks.flatMap(\.lines)
        outputs += input.guides.map(\.label) + input.breaks.map(\.mark)
        outputs += FieldHistoryGeometry10868.actions(input).flatMap { [$0.label] + [$0.spokenLabel].compactMap { $0 } }
        for series in input.series {
            outputs += [series.name] + [FieldHistoryGeometry10868.absentWords(series, in: input),
                                        FieldHistoryGeometry10868.keyNote(series, in: input)].compactMap { $0 }
            outputs += FieldHistoryGeometry10868.readoutSlots(series, in: input).map(FieldHistoryGeometry10868.spokenSlot)
            if let context = FieldHistoryGeometry10868.keyContext(series) {
                outputs.append(FieldHistoryGeometry10868.spokenKeyContext(context))
            }
        }
        outputs.append(FieldHistoryGeometry10868.spokenValue(input))
        if let inspection = input.inspection { outputs += [inspection.caption] + [inspection.note].compactMap { $0 } }
        return outputs
    }

    /// The quarter leaf's drawn and spoken words, through its own gated reads,
    /// with every admitted period's readout as if chosen.
    private static func quarterOutputs(_ view: LacrosseEventPagePeriodGoalsPresentation10868) -> [String] {
        let periods = view.input
        guard periods.isShown else { return [] }
        var outputs = [periods.title, periods.keyLabel, periods.first.name, periods.second.name, periods.expandLabel]
        outputs += [periods.eyebrow, periods.accessibilityHeader, periods.accessibilityKey, periods.visibleScaleWords,
                    periods.visibleCaption, periods.readoutHeading, periods.readoutWords, periods.accessibilityReadout,
                    periods.chooseHint, view.reportLabel].compactMap { $0 }
        if periods.visiblePeriods.isEmpty { outputs.append(periods.empty) }
        for (index, period) in periods.visiblePeriods.enumerated() {
            outputs += [period.label, period.readoutLabel, periods.accessibilityPeriod(period)]
            outputs += [period.spokenLabel, period.first.figure, period.second.figure, period.first.unknownWords,
                        period.second.unknownWords, periods.accessibilityID(at: index)].compactMap { $0 }
            if let readout = period.readout { outputs += [readout.first, readout.second, readout.spoken] }
            if periods.periodShowsNotDrawn(period) { outputs.append(periods.notDrawn) }
        }
        return outputs + periods.visibleNotes
    }

    // MARK: Action payloads

    /// Every payload a reader's actions hand back, through the page's own
    /// callbacks: each headline open, each live history action, inspection
    /// choice, the cursor and the far domain edge a tap can reach, each
    /// series' bound reading, label and inspected keys, each period choice,
    /// each chooser selection and each Details history intent.
    private static func payloads(_ input: LacrosseEventPageInput10868,
                                 _ originals: LacrosseEventPageOriginals10868) -> [String] {
        var log: [String] = []
        let view = LacrosseEventPagePresentation10868(
            input: input, originals: originals,
            onOriginalSelect: { log.append("select:\($0.identity.market)") },
            onOriginalHistory: { log.append("details:\($0.actionID):\($0.selection.identity.market)") },
            onHeadlineOpen: { log.append("open:\($0.ref.outcomeID):\($0.observation ?? "none")") },
            onHistoryAction: { log.append("history:\($0)") },
            onHistoryInspectionChoice: { log.append("choice:\($0)") },
            onHistoryPlotPosition: { log.append("plot:\($0)") },
            onPeriodChoose: { log.append("quarter:\($0)") })
        if let headline = view.headlineContent() {
            let model = FieldHeadlineModel10868(headline.input)
            for competitor in model.competitors {
                if let opening = model.openAction(competitor, canOpen: true) { headline.onOpen?(opening) }
            }
        }
        let history = view.historyContent(reader: false)
        for action in FieldHistoryGeometry10868.actions(history.input) {
            if let id = FieldHistoryGeometry10868.liveID(action, in: history.input) { history.onAction?(id) }
        }
        if let inspection = history.input.inspection {
            for choice in inspection.choices {
                if let id = FieldHistoryGeometry10868.liveChoiceID(choice, among: inspection.choices) { history.onInspectionChoice?(id) }
            }
            for (seriesID, selected) in inspection.selections.sorted(by: { $0.key < $1.key }) {
                if case .point(let id, _) = selected { log.append("inspected:\(seriesID):\(id)") }
            }
        }
        if let cursor = FieldHistoryGeometry10868.cursor(history.input) { history.onPlotPosition?(cursor) }
        history.onPlotPosition?(history.input.domain.upper)
        for series in history.input.series {
            for reading in [series.before, series.recorded] {
                if case .observation(let id, _, _) = reading { log.append("reading:\(series.id):\(id)") }
            }
            if let label = series.labelPointID { log.append("label:\(series.id):\(label)") }
        }
        if let periods = view.periodsContent(reader: false) {
            for index in periods.input.visiblePeriods.indices { periods.choose(at: index) }
        }
        if let chooser = view.chooserContent() {
            for choice in OriginalMarketChooser9483.choices(catalogue: chooser.catalogue, selection: chooser.selection,
                                                            labels: chooser.labels, unavailableChoice: chooser.unavailableChoice) {
                if let selection = choice.selection { chooser.onSelect?(selection) }
            }
        }
        if case .recorded(let shown)? = OriginalMarketDetails9483.recorded(
            catalogue: originals.catalogue, selection: originals.selection, context: originals.recorded, hasCallback: true) {
            for entry in [OriginalMarketDetails9483.HistoryEntry.preview, .expand, .explore] {
                if let intent = OriginalMarketDetails9483.intent(entry, in: shown) {
                    view.originalDetailsContent()?.onHistory?(intent)
                }
            }
        }
        return log
    }

    /// Every minute key a payload names.
    private static func epochs(in text: String) -> [Int] {
        guard let regex = try? NSRegularExpression(pattern: "1779[0-9]{6}") else { return [] }
        let range = NSRange(text.startIndex..., in: text)
        return regex.matches(in: text, range: range).compactMap { match in
            Range(match.range, in: text).flatMap { Int(text[$0]) }
        }
    }

    /// The payloads that name a time beyond what the phase admits: a minute
    /// key at or after the listing before play, after the live cutoff during
    /// play, or a plot position past the phase's domain edge.
    private static func violations(_ payloads: [String], phase: Phase) -> [String] {
        let bound: Int
        let boundX: Double
        switch phase {
        case .before:
            bound = listedStart - 1
            boundX = 0
        case .during:
            bound = liveCutoff
            boundX = x(liveCutoff)
        case .final:
            bound = Int.max
            boundX = .infinity
        }
        return payloads.filter { payload in
            if epochs(in: payload).contains(where: { $0 > bound }) { return true }
            if payload.hasPrefix("plot:"), let value = Double(payload.dropFirst(5)), value > boundX { return true }
            return false
        }
    }

    // MARK: Phases

    func testBeforePlayMountsTheChancesAndHistoryWithNoQuartersReportOrResult() {
        let input = Self.page(.before)
        let model = LacrosseEventPageModel10868(input)
        XCTAssertEqual(model.headline, input.headline)
        XCTAssertNil(model.periods)
        XCTAssertNil(model.periodsUnavailable)
        XCTAssertTrue(model.readerShows(.fullHistory))
        XCTAssertFalse(model.readerShows(.fullPeriods))

        // The before input still carries the final's quarters and finishes:
        // the phase gating, not their absence, keeps them off.
        XCTAssertEqual(input.periods?.phase, .final)
        XCTAssertEqual(input.periods?.periods.count, 4)
        XCTAssertEqual(input.headline.finishes.count, 2)
        // A quarter input naming the before phase draws and speaks nothing either.
        let beforeQuarters = Self.periods(.before)
        XCTAssertFalse(beforeQuarters.isShown)
        XCTAssertEqual(beforeQuarters.visiblePeriods, [])
        XCTAssertNil(beforeQuarters.readoutHeading)
        XCTAssertNil(beforeQuarters.accessibilityHeader)
        XCTAssertNil(beforeQuarters.accessibilityReadout)
        XCTAssertNil(beforeQuarters.visibleCaption)
        XCTAssertEqual(beforeQuarters.visibleNotes, [])
        XCTAssertEqual(beforeQuarters.accessibilityPeriod(Self.period(0)), "")
        XCTAssertNil(beforeQuarters.chooseID(at: 0, canChoose: true))
        XCTAssertNil(beforeQuarters.barFraction(Self.goals(4)))
        XCTAssertNil(LacrosseEventPageModel10868(Self.page(.before, periods: beforeQuarters)).periods)
        let view = LacrosseEventPagePresentation10868(input: input, onPeriodsExpand: {}, onPeriodChoose: { _ in })
        XCTAssertNil(view.periodsContent(reader: false))
        XCTAssertNil(view.periodsContent(reader: true))

        // Each team's own pre-match chance, at equal prominence with its own date.
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.competitors.map(\.metrics),
                       [[.reading(Self.preMatch(.notreDame))], [.reading(Self.preMatch(.syracuse))]])
        XCTAssertEqual(headline.figures, ["70%", "36%"])
        XCTAssertTrue(headline.keyIsHollow)

        // Only minutes strictly before the listing, hollow; each readout is that
        // team's pre-match observation.
        let points = Self.allPoints(input.history)
        XCTAssertEqual(points.count, 188 + 251)
        XCTAssertTrue(points.allSatisfy { $0.x < 0 && $0.style == .hollow })
        XCTAssertEqual(Self.slots(input.history), [
            [FieldHistoryReadoutSlot10868(label: "Pre-match chance", display: .figure("70%", provenance: Self.baselineProvenance))],
            [FieldHistoryReadoutSlot10868(label: "Pre-match chance", display: .figure("36%", provenance: Self.baselineProvenance))],
        ])

        // Details: the pregame reading only, no result.
        let catalogue = Self.originals(.before).catalogue
        for team in Team.allCases {
            XCTAssertNil(Self.content(catalogue, team)?.result)
            XCTAssertEqual(Self.content(catalogue, team)?.readings.map(\.text), [Self.figure(Self.baseline(team))])
        }
    }

    func testBeforeAndLiveCarryNoLaterFactInAnyReachableOutput() {
        // Final facts: the final score either way, the Q3 standing and Q4
        // story, the later quarters, the final-day quotes and their clocks,
        // the settlement time, both results and the final words.
        let finalFacts = ["15–7", "9–7", "6–0", "Q3", "Q4", "99%", "1%", "3:27 PM", "3:13 PM", "3:35 PM",
                          "Won", "Lost", "won", "Final", "ESPN match record"]
        // Final goal counts, read only as counts.
        let finalCounts = ["15", "7"]
        // The CONSTRUCTED live frame's own admitted state: later than before play.
        let liveFacts = ["7–4", "Q1", "Q2", "82%", "22%", "12:55 PM", "constructed live example"]

        // Positive controls: the same collector reaches every final fact at
        // the final and every live fact during play, so the scans below cannot
        // pass by reading nothing.
        let finalOutputs = Self.reachableOutputs(Self.page(.final), Self.originals(.final))
        for fact in finalFacts {
            XCTAssertTrue(finalOutputs.contains { Self.mentions($0, fact) }, "the collector reaches “\(fact)” at the final")
        }
        for count in finalCounts {
            XCTAssertTrue(finalOutputs.contains { Self.mentionsCount($0, count) }, "the collector reaches the count \(count) at the final")
        }
        let liveOutputs = Self.reachableOutputs(Self.page(.during), Self.originals(.during))
        for fact in liveFacts {
            XCTAssertTrue(liveOutputs.contains { Self.mentions($0, fact) }, "the collector reaches “\(fact)” during play")
        }

        // Meaning-aware tokens: a probability, a decimal or a clock is never a count.
        XCTAssertFalse(Self.mentionsCount("70%", "7"))
        XCTAssertFalse(Self.mentionsCount("75%", "7"))
        XCTAssertFalse(Self.mentionsCount("0.7", "7"))
        XCTAssertFalse(Self.mentionsCount("May 22, 7:04 PM PDT", "7"))
        XCTAssertFalse(Self.mentionsCount("May 23, 11:57 AM PDT", "7"))
        XCTAssertFalse(Self.mentionsCount("May 23, 11:15 AM PDT", "15"))
        XCTAssertTrue(Self.mentionsCount("Actual goals: 7, Final · ESPN match record", "7"))
        XCTAssertTrue(Self.mentionsCount("Notre Dame 15. Syracuse 7.", "7"))
        XCTAssertFalse(Self.mentions("100%", "1%"))
        XCTAssertFalse(Self.mentions("21%", "1%"))
        XCTAssertTrue(Self.mentions("Last recorded 1%, May 23, 3:13 PM PDT", "1%"))
        XCTAssertFalse(Self.mentions("NCAA semifinal", "Final"))

        // Before play: none of them anywhere a reader can reach.
        let beforeInput = Self.page(.before)
        XCTAssertEqual(beforeInput.periods?.phase, .final)
        let before = Self.reachableOutputs(beforeInput, Self.originals(.before))
        XCTAssertGreaterThan(before.count, 100)
        for words in ["70%", "36%", "Pre-match chance", "Listed start · not the faceoff", Self.rulesSecondary,
                      "Win chances, each with its own date"] {
            XCTAssertTrue(before.contains { $0.contains(words) }, "before play shows “\(words)”")
        }
        for output in before {
            for fact in finalFacts + liveFacts {
                XCTAssertFalse(Self.mentions(output, fact), "“\(fact)” reached before play: \(output)")
            }
            for count in finalCounts {
                XCTAssertFalse(Self.mentionsCount(output, count), "the count \(count) reached before play: \(output)")
            }
        }

        // During play: only the admitted state, with the final's finishes
        // riding along unread; no final fact anywhere.
        let duringInput = Self.page(.during)
        XCTAssertEqual(duringInput.headline.finishes.count, 2)
        let during = Self.reachableOutputs(duringInput, Self.originals(.during))
        for words in ["7–4", "After Q2", "82%", "22%", "Constructed live example", "Report so far"] {
            XCTAssertTrue(during.contains { $0.contains(words) }, "the live frame shows “\(words)”")
        }
        for output in during {
            for fact in finalFacts {
                XCTAssertFalse(Self.mentions(output, fact), "“\(fact)” reached the live frame: \(output)")
            }
            XCTAssertFalse(Self.mentionsCount(output, "15"), "the final count reached the live frame: \(output)")
        }
    }

    func testDuringPlayTheConstructedLiveFrameShowsOnlyItsAdmittedStateLabelledAsConstructed() {
        let input = Self.page(.during)
        let model = LacrosseEventPageModel10868(input)
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.figures, ["70%", "82%", "36%", "22%"])
        XCTAssertEqual(headline.state?.caption, "Constructed live example")
        XCTAssertFalse(headline.keyIsHollow)

        // Only minutes through the constructed cutoff.
        let points = Self.allPoints(input.history)
        XCTAssertEqual(points.count, 241 + 310)
        XCTAssertTrue(points.allSatisfy { $0.x <= Self.x(Self.liveCutoff) })
        XCTAssertEqual(Self.slots(input.history).map { $0.map(\.display) }, [
            [.figure("70%", provenance: Self.baselineProvenance), .figure("82%", provenance: "May 23, 12:55 PM PDT")],
            [.figure("36%", provenance: Self.baselineProvenance), .figure("22%", provenance: "May 23, 12:55 PM PDT")],
        ])

        // The first two quarters, held at Q2; no story caption yet.
        let periods = model.periods
        XCTAssertEqual(periods?.visiblePeriods.map(\.id), ["q1", "q2"])
        XCTAssertEqual(periods?.readoutHeading, "After Q2")
        XCTAssertEqual(periods?.shownReadout?.first, "7")
        XCTAssertEqual(periods?.shownReadout?.second, "4")
        XCTAssertNil(periods?.visibleCaption)
        XCTAssertEqual(periods?.eyebrow, "Actual goals · constructed live example")
        XCTAssertTrue(input.reader.title.contains("Constructed live example"))
        XCTAssertTrue(input.about?.sections.contains { $0.title == "Constructed live example" } ?? false)

        // Details: the pre-match reading beside the constructed recorded reading, no result.
        let catalogue = Self.originals(.during).catalogue
        XCTAssertEqual(Self.content(catalogue, .notreDame)?.readings.map(\.text), ["70%", "82%"])
        XCTAssertNil(Self.content(catalogue, .notreDame)?.result)
    }

    func testAtTheFinalTheActualGoalsSitBesideBothPreMatchChancesAndTheQuartersAreSelectable() {
        let input = Self.page(.final)
        let model = LacrosseEventPageModel10868(input)
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.figures, ["70%", "15", "36%", "7"])
        XCTAssertEqual(headline.competitors.map { $0.metrics.map(FieldMovementModel10868.spoken) }, [
            ["Pre-match chance: 70%, \(Self.baselineProvenance)", "Actual goals: 15, Final · ESPN match record"],
            ["Pre-match chance: 36%, \(Self.baselineProvenance)", "Actual goals: 7, Final · ESPN match record"],
        ])
        XCTAssertEqual(headline.state?.figure, "15–7")

        // The match window by default; every retained minute in the all window.
        XCTAssertEqual(Self.allPoints(input.history).count, 182 + 191)
        XCTAssertEqual(Self.allPoints(Self.history(.final, window: .all)).count, 701)
        XCTAssertEqual(Self.slots(input.history).map { $0.map(\.display) }, [
            [.figure("70%", provenance: Self.baselineProvenance), .figure("99%", provenance: "May 23, 3:27 PM PDT")],
            [.figure("36%", provenance: Self.baselineProvenance), .figure("1%", provenance: "May 23, 3:13 PM PDT")],
        ])

        // Four quarters, held at Q4 with the final cumulative score.
        let periods = model.periods
        XCTAssertEqual(periods?.visiblePeriods.map(\.label), ["Q1", "Q2", "Q3", "Q4"])
        XCTAssertEqual(periods?.selectedIndex, 3)
        XCTAssertEqual(periods?.shownReadout, LacrosseEventPagePeriodReadout10868(
            first: "15", second: "7", spoken: "After the fourth quarter: Notre Dame 15, Syracuse 7"))
        XCTAssertEqual(periods?.title, "A 6–0 finish")
        XCTAssertEqual(periods?.visibleCaption, "After Q3: Notre Dame 9–7 Syracuse. Q4: 6–0.")
        XCTAssertTrue(model.readerShows(.fullPeriods))
        XCTAssertNotNil(LacrosseEventPagePresentation10868(input: input, onPeriodChoose: { _ in }).periodsContent(reader: false))

        // Each contract's own result; the last quote explicitly historical.
        let catalogue = Self.originals(.final).catalogue
        XCTAssertEqual(Self.content(catalogue, .notreDame)?.result?.words, "Won")
        XCTAssertEqual(Self.content(catalogue, .syracuse)?.result?.words, "Lost")
        XCTAssertTrue(Self.content(catalogue, .notreDame)?.about.contains { $0.value == "99%, recorded May 23, 3:27 PM PDT" } ?? false)
    }

    // MARK: Retained history

    func testAll701RetainedClosesKeepTheirMinutesRunsAndGapsWithNoSyntheticEndpoint() {
        let notreDame = Self.notreDameCloses
        let syracuse = Self.syracuseCloses
        XCTAssertEqual(notreDame.count, 317)
        XCTAssertEqual(syracuse.count, 384)
        XCTAssertEqual(notreDame.count + syracuse.count, 701)
        XCTAssertEqual(notreDame.filter { $0.at < Self.listedStart }.count, 188)
        XCTAssertEqual(syracuse.filter { $0.at < Self.listedStart }.count, 251)
        for closes in [notreDame, syracuse] {
            XCTAssertTrue(zip(closes, closes.dropFirst()).allSatisfy { $0.at < $1.at }, "unique minutes, in order")
            XCTAssertTrue(closes.allSatisfy { $0.at % 60 == 0 }, "minute ends only")
            XCTAssertTrue(closes.allSatisfy { (0...100).contains($0.cents) })
            XCTAssertTrue(closes.allSatisfy { (Double($0.volume) ?? 0) > 0 }, "positive volume only")
        }

        // Both pre-match closes end in the same minute: 70% and 36%, 106% together.
        XCTAssertEqual(notreDame.last { $0.at < Self.listedStart }, Close(at: 1779562440, cents: 70, volume: "909.73"))
        XCTAssertEqual(syracuse.last { $0.at < Self.listedStart }, Close(at: 1779562440, cents: 36, volume: "685.88"))
        XCTAssertEqual(Self.baseline(.notreDame).cents + Self.baseline(.syracuse).cents, 106)
        // The last closes, each its own minute.
        XCTAssertEqual(notreDame.last, Close(at: Self.notreDameLastAt, cents: 99, volume: "49.04"))
        XCTAssertEqual(syracuse.last, Close(at: Self.syracuseLastAt, cents: 1, volume: "258.11"))
        // The archive starts the previous day, after the markets opened — not at inception.
        XCTAssertEqual(syracuse.first?.at, Self.firstAt)
        XCTAssertEqual(notreDame.first?.at, 1779479040)
        XCTAssertLessThan(Self.firstAt, Self.matchDay)
        XCTAssertGreaterThan(Self.firstAt, Self.marketOpen)

        // Runs join adjacent minutes only; every real gap stays a gap; nothing
        // past the last close; no 0 or 100 endpoint; no break or fill.
        let history = Self.history(.final, window: .all)
        for team in Team.allCases {
            guard let series = history.series.first(where: { $0.id == team.rawValue }) else { return XCTFail("\(team)") }
            let points = series.runs.flatMap(\.points)
            XCTAssertEqual(points.map(\.id), Self.closes(team).map { Self.pointID(team, $0.at) })
            for run in series.runs {
                XCTAssertTrue(zip(run.points, run.points.dropFirst()).allSatisfy { $1.x - $0.x == 1 })
            }
            for (earlier, later) in zip(series.runs, series.runs.dropFirst()) {
                XCTAssertGreaterThan((later.points.first?.x ?? 0) - (earlier.points.last?.x ?? 0), 1, "a real gap stays a gap")
            }
            XCTAssertTrue(points.allSatisfy { $0.probability > 0 && $0.probability < 1 })
            XCTAssertEqual(points.last?.x, Self.x(Self.lastClose(team).at))
        }
        XCTAssertEqual(history.series.map(\.runs.count), [135, 125])
        XCTAssertEqual(history.breaks, [])

        // The same runs in the full-size reader and in each original's reader.
        let reader = LacrosseEventPageModel10868(Self.page(.final, history: history)).readerHistory(enlarged: false)
        XCTAssertEqual(reader.series.map(\.runs), history.series.map(\.runs))
        for team in Team.allCases {
            XCTAssertEqual(Self.recordedContext(team, .final).history.series.first?.runs,
                           history.series.first { $0.id == team.rawValue }?.runs)
        }
        // A missing companion minute is never filled.
        XCTAssertNil(Self.close(.syracuse, at: Self.notreDameLastAt))
        XCTAssertFalse(Self.allPoints(history).contains { $0.id == Self.pointID(.syracuse, Self.notreDameLastAt) })
    }

    func testThePreMatchChancesStayIndependentObservationsThatSumTo106() {
        let headline = Self.headline(.before)
        XCTAssertEqual(FieldHeadlineModel10868(headline).figures, ["70%", "36%"])
        XCTAssertEqual(headline.pairs.map { $0.before?.probability }, [0.70, 0.36])
        let sum = headline.pairs.compactMap { $0.before?.probability }.reduce(0, +)
        XCTAssertEqual(sum, 1.06, accuracy: 1e-9, "independent markets, never normalized")
        XCTAssertEqual(LacrosseEventPageModel10868(Self.page(.before)).headline, headline, "the page passes them unchanged")

        // The same minute, two separate observations — never merged.
        let history = Self.history(.final)
        let pinned = history.series.map { series -> FieldHistoryPoint10868? in
            guard case .observation(let id, _, _) = series.before else { return nil }
            return FieldHistoryGeometry10868.uniquePoint(id, in: series)
        }
        XCTAssertEqual(pinned.map { $0?.id }, ["not.1779562440", "syr.1779562440"])
        XCTAssertEqual(pinned.map { $0?.x }, [-1, -1])
        XCTAssertEqual(pinned.map { $0?.probability }, [0.70, 0.36])

        // A missing Syracuse history never borrows Notre Dame's chance.
        let withoutSyracuse = Self.history(.final, omit: Set(Self.syracuseCloses.map { Self.pointID(.syracuse, $0.at) }))
        let slots = Self.slots(withoutSyracuse)
        XCTAssertEqual(slots[0].first?.display, .figure("70%", provenance: Self.baselineProvenance))
        XCTAssertEqual(slots[1].map(\.display), [.words(Self.unbound), .words(Self.unbound)])
        XCTAssertEqual(FieldHistoryGeometry10868.absentWords(withoutSyracuse.series[1], in: withoutSyracuse), Self.noTrades)
    }

    func testAnInspectedMinuteShowsOnlyItsOwnObservationsAndAMissingCompanionStaysMissing() {
        // Notre Dame's last close: Syracuse did not trade in that minute.
        let last = Self.history(.final, window: .all, inspect: Self.notreDameLastAt)
        XCTAssertEqual(last.inspection?.selections["not"], .point(id: "not.1779575220", spoken: "99%"))
        XCTAssertEqual(last.inspection?.selections["syr"], .absent(words: Self.noTradeHere))
        XCTAssertEqual(Self.slots(last).map { $0.map(\.display) }, [
            [.figure("70%", provenance: Self.baselineProvenance), .figure("99%", provenance: "May 23, 3:27 PM PDT")],
            [.figure("36%", provenance: Self.baselineProvenance), .words(Self.noTradeHere)],
        ])
        XCTAssertTrue(FieldHistoryGeometry10868.spokenValue(last).contains("Syracuse: \(Self.noTradeHere)"))
        XCTAssertEqual(FieldHistoryGeometry10868.cursor(last), 212)

        // A minute only Syracuse traded, inside the constructed live frame.
        let syracuseOnly = Self.history(.during, inspect: 1779563280)
        XCTAssertEqual(syracuseOnly.inspection?.selections["not"], .absent(words: Self.noTradeHere))
        guard case .point(let id, _)? = syracuseOnly.inspection?.selections["syr"] else {
            return XCTFail("Syracuse traded at 12:08 PM")
        }
        XCTAssertEqual(id, "syr.1779563280")

        // An exact on-the-hour minute both traded: two figures, one clock each.
        XCTAssertEqual(Self.close(.notreDame, at: 1779562800)?.cents, 62)
        XCTAssertEqual(Self.close(.syracuse, at: 1779562800)?.cents, 37)
        let hour = Self.history(.final, inspect: 1779562800)
        XCTAssertEqual(Self.slots(hour).map { $0.last?.display }, [
            .figure("62%", provenance: "May 23, 12:00 PM PDT"), .figure("37%", provenance: "May 23, 12:00 PM PDT"),
        ])
    }

    func testOneObservationCollapsesOnlyByOwnerIntentAndEqualValuesAtOtherMinutesStayDated() {
        // The pre-match minute itself: the owner's intent shows one dated slot.
        let same = Self.history(.final, inspect: Self.baselineAt)
        XCTAssertEqual(same.readout, .singleBefore(label: "Pre-match chance · inspected"))
        XCTAssertEqual(Self.slots(same)[0], [FieldHistoryReadoutSlot10868(
            label: "Pre-match chance · inspected", display: .figure("70%", provenance: Self.baselineProvenance))])

        // An equal 70% at 11:06 AM is a different observation: two slots, each dated.
        XCTAssertEqual(Self.close(.notreDame, at: 1779559560)?.cents, 70)
        let equal = Self.history(.final, inspect: 1779559560)
        XCTAssertEqual(Self.slots(equal)[0], [
            FieldHistoryReadoutSlot10868(label: "Pre-match", display: .figure("70%", provenance: Self.baselineProvenance)),
            FieldHistoryReadoutSlot10868(label: "Inspected", display: .figure("70%", provenance: "May 23, 11:06 AM PDT")),
        ])
        // The comparison draws the same slots, so the equal figures stay separately dated there too.
        let comparison = LacrosseEventPagePresentation10868(input: Self.page(.final, history: equal)).comparisonContent(reader: false)
        XCTAssertNotNil(comparison)
        XCTAssertEqual(comparison?.entries.first?.slots, Self.slots(equal)[0])
        XCTAssertEqual(Array(RugbyMatchEventPageComparisonPresentation10868.figures(comparison?.entries ?? []).prefix(2)), ["70%", "70%"])
        let sameComparison = LacrosseEventPagePresentation10868(input: Self.page(.final, history: same)).comparisonContent(reader: true)
        XCTAssertEqual(sameComparison?.entries.map(\.slots.count), [1, 1])
    }

    // MARK: Identity

    func testTheRetainedScoreBindsTheExactCompetitionAndTeamsNeverTheFirstRow() {
        // Row 0 is another game.
        XCTAssertEqual(Self.scoreboardEvents.first?.id, "401870924")
        XCTAssertEqual(Self.scoreboardEvents.first?.competitions.first?.competitors.map(\.name),
                       ["Princeton Tigers", "Duke Blue Devils"])

        // Bound by exact competition and team ids, with the header agreeing.
        let bound = Self.boundQuarterGoals(Self.scoreboardEvents, header: Self.header, competition: "401870923", teams: ["87", "183"])
        XCTAssertEqual(bound, [[4, 3, 2, 6], [3, 1, 3, 0]])
        XCTAssertEqual(bound?.map { $0.reduce(0, +) }, [15, 7])

        // The page's quarters are exactly the bound values, and the owner's
        // cumulative words are their running sums.
        XCTAssertEqual(Self.quarterGoals.map { $0.notreDame }, bound?.first)
        XCTAssertEqual(Self.quarterGoals.map { $0.syracuse }, bound?.last)
        var running = (0, 0)
        for (index, goals) in Self.quarterGoals.enumerated() {
            running = (running.0 + goals.notreDame, running.1 + goals.syracuse)
            XCTAssertEqual(Self.cumulative[index].notreDame, "\(running.0)")
            XCTAssertEqual(Self.cumulative[index].syracuse, "\(running.1)")
        }
        XCTAssertEqual(Self.cumulative.map { "\($0.notreDame)–\($0.syracuse)" }, ["4–3", "7–4", "9–7", "15–7"])
        XCTAssertEqual(Self.quarterGoals[3].notreDame, 6)
        XCTAssertEqual(Self.quarterGoals[3].syracuse, 0)
        XCTAssertEqual(Self.periods(.final).visiblePeriods.map { $0.first.value }, [4, 3, 2, 6])
        XCTAssertEqual(Self.periods(.final).visiblePeriods.map { $0.second.value }, [3, 1, 3, 0])

        // Positional binding would copy a neighbour; Duke's final even equals Syracuse's.
        let firstRow = Self.scoreboardEvents[0].competitions[0]
        let positional = firstRow.competitors.map { $0.linescores.compactMap(\.value).map { Int($0) } }
        XCTAssertEqual(positional, [[3, 3, 5, 3], [2, 2, 2, 1]])
        XCTAssertNotEqual(positional, bound ?? [])
        XCTAssertEqual(firstRow.competitors[1].score, "7")

        // Wrong competition, foreign teams, a repeated row or a disagreeing header: no binding.
        XCTAssertNil(Self.boundQuarterGoals(Self.scoreboardEvents, header: Self.header, competition: "401870924", teams: ["87", "183"]))
        XCTAssertNil(Self.boundQuarterGoals(Self.scoreboardEvents, header: Self.header, competition: "401870923", teams: ["163", "150"]))
        XCTAssertNil(Self.boundQuarterGoals(Self.scoreboardEvents + [Self.scoreboardEvents[1]], header: Self.header,
                                            competition: "401870923", teams: ["87", "183"]))
        let disagreeing = RetainedCompetition(
            id: Self.header.id, date: Self.header.date, completed: true, status: "STATUS_FINAL",
            competitors: [Self.header.competitors[0],
                          RetainedCompetitor(id: "183", name: "Syracuse Orange", score: "8", winner: false,
                                             linescores: Self.header.competitors[1].linescores)])
        XCTAssertNil(Self.boundQuarterGoals(Self.scoreboardEvents, header: disagreeing, competition: "401870923", teams: ["87", "183"]))
        XCTAssertEqual(Self.header.competitors.map(\.id), ["87", "183"])
    }

    // MARK: Quarters

    func testChoosingAQuarterShowsItsCumulativeScoreAndMovesNothingElse() {
        var log: [String] = []
        let input = Self.page(.final, history: Self.history(.final, inspect: 1779559560))
        let originals = Self.originals(.final)
        let view = LacrosseEventPagePresentation10868(
            input: input, originals: originals,
            onHistoryAction: { log.append("history:\($0)") },
            onHistoryInspectionChoice: { log.append("choice:\($0)") },
            onHistoryPlotPosition: { log.append("plot:\($0)") },
            onPeriodChoose: { log.append("quarter:\($0)") },
            onInteraction: { log.append("hold") })

        // Choosing hands back the exact period id, after the hold, and nothing else.
        view.periodsContent(reader: false)?.choose(at: 1)
        XCTAssertEqual(log, ["hold", "quarter:q2"])

        // The owner applies it: only the quarter input changes. The history
        // cursor, the held original and the final headline are untouched.
        let chosen = Self.page(.final, history: input.history,
                               periods: Self.periods(.final, selection: .period(id: "q2", missingWords: Self.heldMissing)))
        XCTAssertEqual(chosen.history, input.history)
        XCTAssertEqual(LacrosseEventPageModel10868(chosen).history(enlarged: false).inspection,
                       LacrosseEventPageModel10868(input).history(enlarged: false).inspection)
        XCTAssertEqual(chosen.headline, input.headline)
        XCTAssertEqual(FieldHeadlineModel10868(chosen.headline).state?.figure, "15–7")
        XCTAssertEqual(Self.originals(.final).selection, originals.selection)
        let periods = LacrosseEventPageModel10868(chosen).periods
        XCTAssertEqual(periods?.readoutHeading, "After Q2")
        XCTAssertEqual(periods?.shownReadout, LacrosseEventPagePeriodReadout10868(
            first: "7", second: "4", spoken: "After the second quarter: Notre Dame 7, Syracuse 4"))
        XCTAssertEqual(periods?.isSelected(at: 1), true)
        XCTAssertEqual(periods?.isSelected(at: 3), false)

        // Probability actions never choose a quarter.
        log = []
        let anchor = view.historyContent(reader: false)
        anchor.onAction?("history.previous")
        anchor.onPlotPosition?(-49)
        anchor.onInspectionChoice?("minute.1779559560")
        XCTAssertEqual(log, ["hold", "history:history.previous", "hold", "plot:-49.0", "hold", "choice:minute.1779559560"])
        XCTAssertFalse(log.contains { $0.hasPrefix("quarter:") })

        // The full-size quarters keep the exact callback, without a hold.
        log = []
        let reader = LacrosseEventPagePresentation10868(input: input, mode: .fullPeriods,
                                                        onPeriodChoose: { log.append("quarter:\($0)") },
                                                        onInteraction: { log.append("hold") })
        reader.periodsContent(reader: true)?.choose(at: 2)
        XCTAssertEqual(log, ["quarter:q3"])
    }

    func testATrueZeroIsAFigureAndAMissingCountIsNeverZero() {
        let final = Self.periods(.final)
        let fourth = final.visiblePeriods[3]
        XCTAssertEqual(fourth.second.figure, "0")
        XCTAssertEqual(final.barFraction(fourth.second), 0)
        XCTAssertFalse(final.showsNotDrawn(fourth.second))
        XCTAssertEqual(final.barFraction(fourth.first), 1)
        XCTAssertEqual(final.accessibilityPeriod(fourth), "Notre Dame 6 goals. Syracuse 0 goals")
        XCTAssertEqual(SquashGameScoresGeometry10868.barHeight(0, maxHeight: 108), 0)
        XCTAssertEqual(final.accessibilityPeriod(final.visiblePeriods[1]), "Notre Dame 3 goals. Syracuse 1 goal")

        // An unreported count keeps the owner's words: no figure, no bar, no
        // zero; the neighbours keep theirs.
        var periods = (0..<4).map(Self.period)
        periods[2] = Self.revised(periods[2], second: .unknown("Not reported"), keepsReadout: false)
        let missing = Self.periods(.final, periods: periods, selection: .period(id: "q3", missingWords: Self.heldMissing))
        let third = missing.visiblePeriods[2]
        XCTAssertNil(third.second.figure)
        XCTAssertNil(third.second.value)
        XCTAssertNil(missing.barFraction(third.second))
        XCTAssertFalse(missing.showsNotDrawn(third.second))
        XCTAssertEqual(missing.accessibilityPeriod(third), "Notre Dame 2 goals. Syracuse: Not reported")
        XCTAssertEqual(missing.barFraction(missing.visiblePeriods[1].second), 1.0 / 6)
        XCTAssertEqual(missing.barFraction(missing.visiblePeriods[3].second), 0)
        // The held period without a cumulative score keeps the owner's words.
        XCTAssertEqual(missing.readoutHeading, "After Q3")
        XCTAssertNil(missing.shownReadout)
        XCTAssertEqual(missing.readoutWords, "Score after this quarter not reported")
        XCTAssertEqual(missing.accessibilityReadout, "After Q3. Score after this quarter not reported")

        // A figure beyond the owner scale keeps its figure and says so: never clamped.
        let tight = Self.periods(.final, ceiling: 5)
        XCTAssertNil(tight.barFraction(tight.visiblePeriods[3].first))
        XCTAssertTrue(tight.showsNotDrawn(tight.visiblePeriods[3].first))
        XCTAssertTrue(tight.accessibilityPeriod(tight.visiblePeriods[3]).hasSuffix("Beyond the shared goal scale; not drawn"))
        XCTAssertEqual(tight.barFraction(tight.visiblePeriods[0].first), 4.0 / 5)
        // An unusable scale draws no bar; every figure stays.
        let invalid = Self.periods(.final, ceiling: 0)
        XCTAssertNil(invalid.barFraction(invalid.visiblePeriods[0].first))
        XCTAssertEqual(invalid.visiblePeriods[0].first.figure, "4")
    }

    func testActualQuartersSurviveAMissingAbsentOrAmbiguousHistory() {
        let expected = Self.periods(.final)
        let everything = Set(Self.notreDameCloses.map { Self.pointID(.notreDame, $0.at) }
            + Self.syracuseCloses.map { Self.pointID(.syracuse, $0.at) })
        let histories = [
            Self.history(.final, absent: true),
            Self.history(.final, omit: everything),
            Self.duplicated(Self.history(.final)),
        ]
        for history in histories {
            let input = Self.page(.final, history: history)
            let model = LacrosseEventPageModel10868(input)
            XCTAssertEqual(model.periods, expected)
            XCTAssertEqual(model.periods?.shownReadout?.first, "15")
            XCTAssertEqual(FieldHeadlineModel10868(input.headline).figures, ["70%", "15", "36%", "7"])
            let view = LacrosseEventPagePresentation10868(input: input, onPeriodChoose: { _ in })
            XCTAssertEqual(view.periodsContent(reader: false)?.input, expected)
            XCTAssertEqual(view.periodsContent(reader: true)?.input, expected)
            XCTAssertEqual(Self.content(Self.originals(.final).catalogue, .notreDame)?.result?.words, "Won")
        }
        // The explicit absence keeps its words: no plot and no zero.
        let absent = Self.history(.final, absent: true)
        XCTAssertFalse(FieldHistoryGeometry10868.showsPlot(absent))
        XCTAssertEqual(Self.slots(absent)[0].map(\.display), [.words(Self.unbound), .words(Self.unbound)])

        // The reverse: missing quarters keep the history and show the owner's words.
        let noQuarters = LacrosseEventPageModel10868(Self.page(.final, withoutQuarters: true))
        XCTAssertNil(noQuarters.periods)
        XCTAssertEqual(noQuarters.periodsUnavailable, "Quarter scores unavailable")
        XCTAssertEqual(noQuarters.input.history, Self.history(.final))
        XCTAssertFalse(noQuarters.readerShows(.fullPeriods))
        XCTAssertNil(LacrosseEventPageModel10868(Self.page(.before, withoutQuarters: true)).periodsUnavailable)
    }

    func testArbitraryDuplicateForeignAndWithdrawnIdentitiesBorrowNothing() {
        // Arbitrary owner period ids and labels, including a CONSTRUCTED extra period.
        var log: [String] = []
        let overtime = LacrosseEventPagePeriod10868(
            id: "ot.1", label: "OT", spokenLabel: "Overtime", first: Self.goals(1), second: Self.goals(0),
            readoutLabel: "After overtime",
            readout: LacrosseEventPagePeriodReadout10868(first: "16", second: "7", spoken: "Constructed: after overtime"))
        let arbitrary = Self.periods(.final, periods: (0..<4).map(Self.period) + [overtime],
                                      selection: .period(id: "ot.1", missingWords: Self.heldMissing))
        let leaf = LacrosseEventPagePeriodGoalsPresentation10868(input: arbitrary, onChoose: { log.append($0) })
        XCTAssertEqual(arbitrary.selectedIndex, 4)
        for index in arbitrary.visiblePeriods.indices { leaf.choose(at: index) }
        XCTAssertEqual(log, ["q1", "q2", "q3", "q4", "ot.1"])

        // A repeated and an empty id: readable, never choosable or held; neighbours keep working.
        var periods = (0..<4).map(Self.period)
        periods[2] = Self.revised(periods[2], id: "q2")
        periods[3] = Self.revised(periods[3], id: "")
        let repeated = Self.periods(.final, periods: periods, selection: .period(id: "q2", missingWords: Self.heldMissing))
        XCTAssertEqual((0..<4).map { repeated.chooseID(at: $0, canChoose: true) }, ["q1", nil, nil, nil])
        XCTAssertNil(repeated.selectedIndex)
        XCTAssertEqual(repeated.readoutHeading, Self.heldMissing)
        XCTAssertNil(repeated.shownReadout)
        XCTAssertTrue(repeated.visiblePeriods.allSatisfy { !repeated.accessibilityPeriod($0).isEmpty })
        XCTAssertEqual(Set((0..<4).compactMap { repeated.accessibilityID(at: $0) }).count, 4)

        // A withdrawn held period: its owner's words, never a neighbour.
        let withdrawn = Self.periods(.final, periods: [0, 1, 3].map(Self.period),
                                      selection: .period(id: "q3", missingWords: Self.heldMissing))
        XCTAssertNil(withdrawn.selectedIndex)
        XCTAssertEqual(withdrawn.readoutHeading, Self.heldMissing)
        XCTAssertFalse(withdrawn.visiblePeriods.indices.contains { withdrawn.isSelected(at: $0) })
        // Nothing held: the owner's prompt.
        XCTAssertEqual(Self.periods(.final, selection: .none).readoutHeading, "Choose a quarter to see the score after it")
        // No callback: every period readable, none acts.
        XCTAssertNil(Self.periods(.final).chooseID(at: 0, canChoose: false))
        LacrosseEventPagePeriodGoalsPresentation10868(input: Self.periods(.final)).choose(at: 0)

        // History: a repeated Syracuse series binds no reading; Notre Dame keeps its own.
        let doubled = Self.slots(Self.duplicated(Self.history(.final)))
        XCTAssertEqual(doubled[0].first?.display, .figure("70%", provenance: Self.baselineProvenance))
        XCTAssertEqual(doubled[1].map(\.display), [.words(Self.unbound), .words(Self.unbound)])
        XCTAssertEqual(doubled[2].map(\.display), [.words(Self.unbound), .words(Self.unbound)])

        // Headline: a repeated or foreign slot borrows no figure.
        let repeatedSlots = FieldHeadlineModel10868(Self.headline(
            .final, displayed: [Self.slot(.notreDame), Self.slot(.notreDame), Self.slot(.syracuse)]))
        XCTAssertEqual(repeatedSlots.competitors.map(\.metrics.count), [0, 0, 2])
        XCTAssertEqual(repeatedSlots.figures, ["36%", "7"])
        let foreign = FieldHeadlineSlot10868(
            ref: FieldChooserOriginalRef10868(scope: "constructed.scope.other", source: "kalshi",
                                              marketID: Self.ticker(.notreDame), outcomeID: "not"),
            name: "Notre Dame", compactName: nil, keyShape: .circle)
        let foreignSlots = FieldHeadlineModel10868(Self.headline(.final, displayed: [foreign, Self.slot(.syracuse)]))
        XCTAssertEqual(foreignSlots.competitors.map(\.metrics.count), [0, 2])
        XCTAssertEqual(foreignSlots.competitorSummary(foreignSlots.competitors[0]), "Notre Dame. Team unavailable in this update")

        // An arbitrary catalogue: the two captured winner contracts and any other props the owner admits.
        let props = ["total-goals", "first-goal", "margin"].map { key -> OriginalMarketDetails9483.Original in
            OriginalMarketDetails9483.Original(
                identity: OriginalMarketDetails9483.Identity(source: "constructed", market: "constructed.market.\(key)", side: "Yes"),
                title: "Constructed prop \(key)", outcome: "Yes", mode: .result,
                pregame: .missing("No pre-match reading"), later: nil, grade: nil,
                about: OriginalMarketDetails9483.About(source: nil, rules: .omitted, provenance: [], historicalQuote: nil))
        }
        let wide = Self.catalogue(.final, originals: Team.allCases.map { Self.original($0, .final) } + props)
        let wideChoices = Self.choices(Self.originals(.final, catalogue: wide))
        XCTAssertEqual(wideChoices.count, 5)
        XCTAssertTrue(wideChoices.allSatisfy { $0.selection != nil })
        // A foreign scope opens nothing, never the first original.
        let foreignSelection = OriginalMarketDetails9483.Selection(scope: "constructed.scope.other", identity: Self.identity(.notreDame))
        XCTAssertNil(OriginalMarketDetails9483.content(catalogue: wide, selection: foreignSelection))
        // A repeated identity or a withdrawn title: no control; the valid neighbour keeps working.
        let ambiguous = Self.originals(.final, catalogue: Self.catalogue(.final, originals: [
            Self.original(.notreDame, .final), Self.original(.notreDame, .final), Self.original(.syracuse, .final),
        ]))
        XCTAssertEqual(Self.choices(ambiguous).map { $0.selection != nil }, [false, false, true])
        let retired = Self.originals(.final, catalogue: Self.catalogue(.final, originals: [
            Self.original(.notreDame, .final, blankTitle: true), Self.original(.syracuse, .final),
        ]))
        XCTAssertEqual(Self.choices(retired).map { $0.selection != nil }, [false, true])
    }

    // MARK: Rules, payloads and held identities

    func testOriginalRulesArePrimaryAndSecondaryVerbatimAndResultsStandApartFromActuals() {
        // The retained texts, exactly (receipt: lacrosseMatch.json sha256 b70e369d…).
        XCTAssertEqual(Self.rulesPrimaryNotreDame.utf8.count, 145)
        XCTAssertEqual(Self.rulesPrimarySyracuse.utf8.count, 143)
        XCTAssertEqual(Self.rulesSecondary.utf8.count, 573)
        XCTAssertEqual(Self.rulesPrimaryNotreDame,
                       "If Notre Dame wins the Syracuse vs Notre Dame men's college lacrosse game originally scheduled for May 23, 2026, then the market resolves to Yes.")
        XCTAssertEqual(Self.rulesPrimarySyracuse,
                       "If Syracuse wins the Syracuse vs Notre Dame men's college lacrosse game originally scheduled for May 23, 2026, then the market resolves to Yes.")
        XCTAssertTrue(Self.rulesSecondary.hasPrefix("The following market refers to the team who wins the Syracuse vs Notre Dame men's college lacrosse game originally scheduled for May 23, 2026."))
        XCTAssertTrue(Self.rulesSecondary.contains("If this game is postponed/delayed and played within 14 days of the originally scheduled start time, the market will remain open and close after the rescheduled game has finished."))
        XCTAssertTrue(Self.rulesSecondary.contains("the market will resolve to a fair price for each team in accordance with the rules."))
        XCTAssertTrue(Self.rulesSecondary.hasSuffix("If the game is declared a tie, the market will resolve to 50/50 for both teams."))

        // Every original, in every phase: primary then secondary, verbatim and
        // verified; the market's own title and outcome.
        let retained: Set<String> = [Self.rulesPrimaryNotreDame, Self.rulesPrimarySyracuse, Self.rulesSecondary]
        for phase in Phase.allCases {
            let catalogue = Self.catalogue(phase)
            for team in Team.allCases {
                let content = Self.content(catalogue, team)
                XCTAssertEqual(content?.rules, .verified([Self.rulesPrimary(team), Self.rulesSecondary]))
                XCTAssertEqual(content?.title, "Syracuse vs Notre Dame Winner?")
                XCTAssertEqual(content?.outcome, Self.name(team))
            }
            for original in catalogue.originals {
                guard case .verified(let paragraphs) = original.about.rules else { continue }
                XCTAssertTrue(paragraphs.allSatisfy(retained.contains), "no paraphrase is marked verified")
            }
        }

        // Each contract's own result: an owner without one shows the result
        // unavailable, whatever the separately reported actual score.
        let ungraded = Self.catalogue(.final, originals: [Self.original(.notreDame, .final),
                                                         Self.original(.syracuse, .final, grade: false)])
        XCTAssertEqual(Self.content(ungraded, .notreDame)?.result?.words, "Won")
        XCTAssertEqual(Self.content(ungraded, .syracuse)?.result?.words, OriginalMarketDetails9483.resultUnavailable)
        XCTAssertEqual(LacrosseEventPageModel10868(Self.page(.final)).periods?.shownReadout?.second, "7",
                       "the actual score is a separate fact")
        XCTAssertEqual(Self.content(Self.originals(.final).catalogue, .syracuse)?.result?.words, "Lost")
    }

    func testActionPayloadsCarryOnlyThePhaseAdmittedSubjectTimeAndKey() {
        let finalDefaults = [Self.pointID(.notreDame, Self.notreDameLastAt), Self.pointID(.syracuse, Self.syracuseLastAt)]
        var byPhase: [Phase: [String]] = [:]
        for phase in Phase.allCases {
            let payloads = Self.payloads(Self.page(phase), Self.originals(phase))
            byPhase[phase] = payloads
            XCTAssertEqual(Self.violations(payloads, phase: phase), [], "\(phase) carries only admitted times")
            XCTAssertFalse(payloads.isEmpty)
        }
        let before = byPhase[.before] ?? []
        let during = byPhase[.during] ?? []
        let final = byPhase[.final] ?? []

        // No final default observation before or during play.
        for payload in before + during {
            XCTAssertFalse(finalDefaults.contains { payload.contains($0) }, "a final default reached \(payload)")
        }
        XCTAssertTrue(final.contains("reading:not:not.1779575220"))
        XCTAssertTrue(final.contains("reading:syr:syr.1779574380"))

        // Headline opens: the exact original; its observation key only while
        // the live recorded figure is shown.
        XCTAssertEqual(before.filter { $0.hasPrefix("open:") }, ["open:not:none", "open:syr:none"])
        XCTAssertEqual(during.filter { $0.hasPrefix("open:") }, ["open:not:not.1779566100", "open:syr:syr.1779566100"])
        XCTAssertEqual(final.filter { $0.hasPrefix("open:") }, ["open:not:none", "open:syr:none"])

        // History: the owner's live ids; the far edge a tap can reach is the phase's.
        XCTAssertEqual(before.filter { $0.hasPrefix("history:") }, [
            "history:window.match", "history:window.all", "history:history.expand",
            "history:history.previous", "history:history.next",
        ])
        XCTAssertTrue(before.contains("plot:0.0"))
        XCTAssertTrue(during.contains("plot:60.0"))
        XCTAssertTrue(before.contains("reading:not:not.1779562440"))
        XCTAssertTrue(during.contains("reading:syr:syr.1779566100"))

        // Periods: none before play; only the admitted ones during play.
        XCTAssertEqual(before.filter { $0.hasPrefix("quarter:") }, [])
        XCTAssertEqual(during.filter { $0.hasPrefix("quarter:") }, ["quarter:q1", "quarter:q2"])
        XCTAssertEqual(final.filter { $0.hasPrefix("quarter:") }, ["quarter:q1", "quarter:q2", "quarter:q3", "quarter:q4"])

        // Originals and Details intents: exact subjects, no time.
        for payloads in [before, during, final] {
            XCTAssertEqual(payloads.filter { $0.hasPrefix("select:") }, ["select:\(Self.ticker(.notreDame))", "select:\(Self.ticker(.syracuse))"])
            XCTAssertEqual(payloads.filter { $0.hasPrefix("details:") }, [
                "details:original.history.expand:\(Self.ticker(.notreDame))",
                "details:original.history.explore:\(Self.ticker(.notreDame))",
            ])
        }

        // An inspected live minute hands back its own keys and cursor.
        let inspected = Self.payloads(Self.page(.during, history: Self.history(.during, inspect: 1779563280)), Self.originals(.during))
        XCTAssertTrue(inspected.contains("inspected:syr:syr.1779563280"))
        XCTAssertFalse(inspected.contains { $0.hasPrefix("inspected:not:") })
        XCTAssertTrue(inspected.contains("plot:13.0"))
        XCTAssertEqual(Self.violations(inspected, phase: .during), [])

        // Deliberately bad controls: a final key leaked into the live headline,
        // and a final default observation leaked into a before-play history.
        let leakedOpen = Self.payloads(Self.page(.during, headline: Self.headline(.during, notreDameObservation: finalDefaults[0])),
                                       Self.originals(.during))
        XCTAssertEqual(Self.violations(leakedOpen, phase: .during), ["open:not:not.1779575220"])
        var leakedSeries = Self.history(.before).series
        leakedSeries[0] = FieldHistorySeries10868(
            id: leakedSeries[0].id, name: leakedSeries[0].name, shape: leakedSeries[0].shape, tint: leakedSeries[0].tint,
            runs: leakedSeries[0].runs, links: [], labelPointID: leakedSeries[0].labelPointID, before: leakedSeries[0].before,
            recorded: Self.observation(.notreDame, Self.lastClose(.notreDame)), absentWords: nil, choose: nil)
        let leakedHistory = Self.payloads(Self.page(.before, history: Self.replacingSeries(Self.history(.before), leakedSeries)),
                                          Self.originals(.before))
        XCTAssertEqual(Self.violations(leakedHistory, phase: .before), ["reading:not:not.1779575220"])
        // The checker reads times only: the same leaked key is admitted at the final.
        XCTAssertEqual(Self.violations(leakedOpen, phase: .final), [])
    }

    func testHeldQuarterInspectionAndOriginalSurviveOmissionAndRestoreWithTheirOwnWords() {
        // Quarter: held Q3; an update without Q3 shows the owner's words; restored, Q3 again.
        let held = LacrosseEventPagePeriodSelection10868.period(id: "q3", missingWords: Self.heldMissing)
        let full = Self.periods(.final, selection: held)
        XCTAssertEqual(full.readoutHeading, "After Q3")
        XCTAssertEqual(full.shownReadout?.first, "9")
        XCTAssertEqual(full.shownReadout?.second, "7")
        let omitted = Self.periods(.final, periods: [0, 1, 3].map(Self.period), selection: held)
        XCTAssertEqual(omitted.readoutHeading, Self.heldMissing)
        XCTAssertNil(omitted.shownReadout)
        XCTAssertFalse(omitted.visiblePeriods.indices.contains { omitted.isSelected(at: $0) })
        XCTAssertEqual(Self.periods(.final, selection: held).selectedPeriod?.id, "q3")

        // History: the held inspection at Notre Dame's last close; an update
        // without that point keeps the owner's inspection and shows the
        // unbound words — never a neighbouring minute.
        let inspected = Self.history(.final, window: .all, inspect: Self.notreDameLastAt)
        var series = inspected.series
        series[0] = Self.withRuns(series[0], Self.runs(.notreDame, Array(Self.notreDameCloses.dropLast())))
        let afterOmission = Self.replacingSeries(inspected, series)
        XCTAssertEqual(afterOmission.inspection, inspected.inspection)
        XCTAssertEqual(Self.slots(afterOmission)[0].last?.display, .words(Self.unbound))
        XCTAssertEqual(Self.slots(inspected)[0].last?.display, .figure("99%", provenance: "May 23, 3:27 PM PDT"))
        for mode in [LacrosseEventPageMode10868.page, .fullHistory] {
            let view = LacrosseEventPagePresentation10868(input: Self.page(.final, history: inspected), mode: mode)
            XCTAssertEqual(view.historyContent(reader: mode == .fullHistory).input.inspection, inspected.inspection)
        }

        // Original: held through every mode and phase, never replaced.
        let heldOriginal = Self.selection(.notreDame)
        let modes: [LacrosseEventPageMode10868] = [.page, .fullHistory, .fullPeriods, .catalogue, .original, .about, .source, .report]
        for phase in Phase.allCases {
            for mode in modes {
                let view = LacrosseEventPagePresentation10868(input: Self.page(phase), mode: mode, originals: Self.originals(phase))
                XCTAssertEqual(view.chooserContent()?.selection, heldOriginal)
                XCTAssertEqual(view.catalogueContent()?.selection, heldOriginal)
                XCTAssertEqual(view.originalDetailsContent()?.selection, heldOriginal)
            }
        }
        // An update omits the held original: no Details, no neighbour selected.
        let withoutHeld = Self.catalogue(.final, originals: [Self.original(.syracuse, .final)])
        let afterOriginalOmission = Self.originals(.final, catalogue: withoutHeld)
        XCTAssertNil(Self.content(withoutHeld, .notreDame))
        XCTAssertEqual(Self.choices(afterOriginalOmission).map(\.label), ["Syracuse to win"])
        XCTAssertEqual(Self.choices(afterOriginalOmission).map(\.isSelected), [false])
        XCTAssertEqual(afterOriginalOmission.selection, heldOriginal)
        // Restored: the same exact original opens again.
        XCTAssertEqual(Self.choices(Self.originals(.final)).map(\.isSelected), [true, false])
        XCTAssertEqual(Self.content(Self.originals(.final).catalogue, .notreDame)?.outcome, "Notre Dame")
    }

    // MARK: Callbacks and readers

    func testPageActionsHoldOnceAndFullSizeAndTextContentKeepExactCallbacks() {
        var log: [String] = []
        let input = Self.page(.final)
        let intent = OriginalMarketDetails9483.HistoryIntent(selection: Self.selection(.notreDame), entry: .explore,
                                                             actionID: "original.history.explore")
        func view(_ mode: LacrosseEventPageMode10868 = .page, hook: Bool = true) -> LacrosseEventPagePresentation10868 {
            LacrosseEventPagePresentation10868(
                input: input, mode: mode, originals: Self.originals(.final),
                onAbout: { log.append("about") },
                onSource: { log.append("source") },
                onReport: { log.append("report") },
                onLink: { log.append("link:\($0)") },
                onAllProps: { log.append("allProps") },
                onOriginalSelect: { log.append("original:\($0.identity.market)") },
                onOriginalHistory: { log.append("details:\($0.actionID)") },
                onHeadlineOpen: { log.append("open:\($0.ref.outcomeID)") },
                onHistoryAction: { log.append("history:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\(Int($0))") },
                onPeriodsExpand: { log.append("quarters:expand") },
                onPeriodChoose: { log.append("quarter:\($0)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf calls nothing; the comparison never acts.
        let page = view()
        let headline = page.headlineContent()
        let comparison = page.comparisonContent(reader: false)
        XCTAssertNotNil(comparison, "the final mounts the comparison inline")
        let anchor = page.historyContent(reader: false)
        let periods = page.periodsContent(reader: false)
        let chooser = page.chooserContent()
        _ = comparison?.entries
        _ = page.catalogueContent()
        _ = page.originalDetailsContent()
        _ = page.aboutContent()
        _ = page.sourceContent()
        _ = page.reportContent()
        _ = page.comparisonContent(reader: true)
        _ = page.historyContent(reader: true)
        _ = page.periodsContent(reader: true)
        _ = page.headlineContent(reader: true)
        XCTAssertEqual(log, [])

        // Page, catalogue and Details actions: the hook once, then the exact callback.
        headline?.onAbout?()
        headline?.onOpen?(FieldMovementOpen10868(ref: Self.ref(.notreDame), observation: nil))
        anchor.onAction?("history.expand")
        anchor.onInspectionChoice?("minute.1779559560")
        anchor.onPlotPosition?(-49)
        page.openSource()
        periods?.onExpand?()
        periods?.choose(at: 0)
        periods?.onReport?()
        chooser?.onSelect?(Self.selection(.syracuse))
        page.openAllProps()
        view(.catalogue).catalogueContent()?.onSelect?(Self.selection(.notreDame))
        view(.original).originalDetailsContent()?.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "about", "hold", "open:not", "hold", "history:history.expand",
                             "hold", "inspect:minute.1779559560", "hold", "plot:-49", "hold", "source",
                             "hold", "quarters:expand", "hold", "quarter:q1", "hold", "report",
                             "hold", "original:\(Self.ticker(.syracuse))", "hold", "allProps",
                             "hold", "original:\(Self.ticker(.notreDame))", "hold", "details:original.history.explore"])

        // Full-size and text content: the exact callbacks, no hold.
        log = []
        view(.fullHistory).historyContent(reader: true).onAction?("window.all")
        let fullPeriods = view(.fullPeriods).periodsContent(reader: true)
        XCTAssertEqual(fullPeriods?.input, periods?.input, "the same quarter leaf and input full size")
        XCTAssertNil(fullPeriods?.onExpand, "no nested expand inside the reader")
        fullPeriods?.choose(at: 3)
        fullPeriods?.onReport?()
        view(.fullPeriods).headlineContent(reader: true)?.onOpen?(FieldMovementOpen10868(ref: Self.ref(.syracuse), observation: nil))
        view(.fullPeriods).headlineContent(reader: true)?.onAbout?()
        view(.fullHistory).openReaderAbout()
        let reportText = view(.report).reportContent()
        XCTAssertEqual(reportText?.link, LacrosseEventPageLink10868(id: "record.link", label: "ESPN match record"))
        if let link = reportText?.link { reportText?.onLink?(link.id) }
        XCTAssertEqual(log, ["history:window.all", "quarter:q4", "report", "open:syr", "about", "about", "link:record.link"])
        let model = LacrosseEventPageModel10868(input)
        XCTAssertTrue(model.aboutEntry(mode: .fullHistory, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .fullPeriods, canOpen: true), "the headline above the quarters carries its own About")
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))

        // No owner callback: no control and no hold.
        log = []
        let silent = LacrosseEventPagePresentation10868(input: input, originals: Self.originals(.final),
                                                        onInteraction: { log.append("hold") })
        XCTAssertNil(silent.headlineContent()?.onAbout)
        XCTAssertNil(silent.headlineContent()?.onOpen)
        XCTAssertNil(silent.historyContent(reader: false).onAction)
        XCTAssertNil(silent.historyContent(reader: false).onPlotPosition)
        XCTAssertNil(silent.periodsContent(reader: false)?.onChoose)
        XCTAssertNil(silent.periodsContent(reader: false)?.onExpand)
        XCTAssertNil(silent.periodsContent(reader: false)?.onReport)
        XCTAssertNil(silent.periodsContent(reader: false)?.reportLabel)
        XCTAssertNil(silent.periodsContent(reader: false)?.input.chooseID(at: 0, canChoose: false))
        XCTAssertNil(silent.chooserContent()?.onSelect)
        silent.periodsContent(reader: false)?.choose(at: 0)
        silent.openSource()
        silent.openAllProps()
        silent.openReaderAbout()
        XCTAssertEqual(log, [])

        // A report callback without readable report text draws no report control.
        var noReport = input
        noReport.report = nil
        let unreported = LacrosseEventPagePresentation10868(input: noReport, onReport: { log.append("report") })
        XCTAssertNil(unreported.periodsContent(reader: false)?.onReport)
        XCTAssertNil(unreported.periodsContent(reader: false)?.reportLabel)
        XCTAssertEqual(log, [])

        // No hook: each page callback is the owner's own.
        view(hook: false).openAllProps()
        view(hook: false).periodsContent(reader: false)?.choose(at: 1)
        XCTAssertEqual(log, ["allProps", "quarter:q2"])
    }

    func testFullSizeContentIsTheSameViewsWithTheSameInputs() {
        for phase in Phase.allCases {
            let input = Self.page(phase)
            let model = LacrosseEventPageModel10868(input)
            let view = LacrosseEventPagePresentation10868(input: input, onPeriodChoose: { _ in })
            let inline = view.historyContent(reader: false).input
            let reader = view.historyContent(reader: true).input
            XCTAssertEqual(inline, model.history(enlarged: false))
            XCTAssertEqual(reader, model.readerHistory(enlarged: false))
            XCTAssertEqual(reader.series, inline.series)
            XCTAssertEqual(reader.inspection, inline.inspection)
            XCTAssertEqual(reader.windows, inline.windows)
            XCTAssertEqual(reader.readout, inline.readout)
            XCTAssertEqual(reader.domain, inline.domain)
            // Key: the reader always mounts the comparison, which stands in for
            // the plain key; the page mounts it only at the final, and before
            // play and live keeps the owner's own key.
            XCTAssertFalse(reader.showsKey)
            XCTAssertEqual(inline.showsKey, phase == .final ? false : input.history.showsKey)
            XCTAssertTrue(input.history.showsKey)
            XCTAssertEqual(Self.slots(reader), Self.slots(inline), "the readouts never depend on the mount")
            XCTAssertEqual(reader.plotHeight, inline.plotHeight)
            XCTAssertEqual(reader.layout, .expanded)
            XCTAssertNil(reader.expand)
            XCTAssertEqual(inline.expand, input.history.expand)
            // The comparison: the same View with the same resolved slots wherever it is shown.
            XCTAssertEqual(view.comparisonContent(reader: true)?.history, reader)
            if phase == .final {
                XCTAssertEqual(view.comparisonContent(reader: false)?.history, inline)
                XCTAssertEqual(view.comparisonContent(reader: false)?.entries.map(\.slots),
                               view.comparisonContent(reader: true)?.entries.map(\.slots))
            } else {
                XCTAssertNil(view.comparisonContent(reader: false), "\(phase): the headline already carries the chances inline")
            }
            // The full-size quarters: the same input under the same headline input.
            XCTAssertEqual(view.periodsContent(reader: true)?.input, view.periodsContent(reader: false)?.input)
            XCTAssertEqual(view.headlineContent(reader: true)?.input, view.headlineContent()?.input)
        }
    }

    // MARK: Comparison and key (L1)

    func testTheComparisonShowsEachTeamsDatedReadoutsFromTheSameCopyAndHidesOnlyTheDuplicateKey() {
        for phase in Phase.allCases {
            let input = Self.page(phase)
            let view = LacrosseEventPagePresentation10868(input: input)
            XCTAssertEqual(view.comparisonContent(reader: false) != nil, phase == .final)
            guard let comparison = view.comparisonContent(reader: true) else { return XCTFail("\(phase): full size always mounts it") }
            XCTAssertEqual(comparison.label, "Win chances, each with its own date")
            // Names and shapes are the history's own; the slots are the shared resolver's.
            XCTAssertEqual(comparison.entries.map(\.series.name), ["Notre Dame", "Syracuse"])
            XCTAssertEqual(comparison.entries.map(\.series.shape), [.circle, .diamond])
            XCTAssertEqual(comparison.entries.map(\.slots), Self.slots(comparison.history))
            XCTAssertEqual(comparison.entries.map(\.isSelected), [false, false])
        }
        // Dates: each figure carries its own label and date.
        let final = LacrosseEventPagePresentation10868(input: Self.page(.final)).comparisonContent(reader: false)
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.figures(final?.entries ?? []), ["70%", "99%", "36%", "1%"])
        XCTAssertEqual(final?.entries.map(RugbyMatchEventPageComparisonPresentation10868.spoken), [
            "Notre Dame. Pre-match 70%, \(Self.baselineProvenance). Last recorded 99%, May 23, 3:27 PM PDT",
            "Syracuse. Pre-match 36%, \(Self.baselineProvenance). Last recorded 1%, May 23, 3:13 PM PDT",
        ])
        let before = LacrosseEventPagePresentation10868(input: Self.page(.before)).comparisonContent(reader: true)
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.figures(before?.entries ?? []), ["70%", "36%"])

        // Missing: an exact-minute absence keeps the history's words, never a figure.
        let missingMinute = LacrosseEventPagePresentation10868(
            input: Self.page(.final, history: Self.history(.final, window: .all, inspect: Self.notreDameLastAt)))
            .comparisonContent(reader: false)
        XCTAssertEqual(missingMinute?.entries.last?.slots.last?.display, .words(Self.noTradeHere))
        XCTAssertEqual(RugbyMatchEventPageComparisonPresentation10868.figures(missingMinute?.entries ?? []), ["70%", "99%", "36%"])
        // Missing history: the team keeps its name and the history's absence words.
        let empty = LacrosseEventPagePresentation10868(input: Self.page(
            .final, history: Self.history(.final, omit: Set(Self.syracuseCloses.map { Self.pointID(.syracuse, $0.at) }))))
            .comparisonContent(reader: false)
        XCTAssertEqual(empty?.entries.last?.series.name, "Syracuse")
        XCTAssertEqual(empty?.entries.last?.note, Self.noTrades)
        XCTAssertEqual(empty?.entries.last?.slots.map(\.display), [.words(Self.unbound), .words(Self.unbound)])
        // An exact on-the-hour minute: both figures, one clock each.
        let hour = LacrosseEventPagePresentation10868(input: Self.page(.final, history: Self.history(.final, inspect: 1779562800)))
            .comparisonContent(reader: false)
        XCTAssertEqual(hour?.entries.map { $0.slots.last?.display }, [
            .figure("62%", provenance: "May 23, 12:00 PM PDT"), .figure("37%", provenance: "May 23, 12:00 PM PDT"),
        ])

        // The key: hidden only in the presentation copy, while no series has a
        // choose action or a visible key context. The owner's input is untouched.
        let plain = Self.page(.final)
        let plainModel = LacrosseEventPageModel10868(plain)
        XCTAssertTrue(plain.history.showsKey)
        XCTAssertTrue(plainModel.hidesSharedKey)
        XCTAssertFalse(plainModel.history(enlarged: false).showsKey)
        XCTAssertFalse(plainModel.readerHistory(enlarged: false).showsKey)
        XCTAssertTrue(plainModel.input.history.showsKey, "the owner's input is never changed")
        // The copy keeps every other field: with the owner's own height, layout,
        // expand and key it is the owner's input exactly.
        XCTAssertEqual(LacrosseEventPageModel10868.history(plain.history, plotHeight: plain.history.plotHeight,
                                                            layout: plain.history.layout, expand: plain.history.expand,
                                                            showsKey: plain.history.showsKey), plain.history)
        let copy = plainModel.history(enlarged: false)
        XCTAssertEqual(copy.series, plain.history.series)
        XCTAssertEqual(copy.inspection, plain.history.inspection)
        XCTAssertEqual(copy.markKey, plain.history.markKey)
        XCTAssertEqual(copy.notes, plain.history.notes)
        XCTAssertEqual(FieldHistoryGeometry10868.actions(copy), FieldHistoryGeometry10868.actions(plain.history))

        // A choose action keeps the key, and the action itself stays live.
        let choosing = LacrosseEventPageModel10868(Self.page(.final, history: Self.history(.final, choose: true)))
        XCTAssertFalse(choosing.hidesSharedKey)
        XCTAssertTrue(choosing.history(enlarged: false).showsKey)
        XCTAssertTrue(choosing.readerHistory(enlarged: false).showsKey)
        XCTAssertEqual(FieldHistoryGeometry10868.liveID(Self.action("choose.syr", "Show Syracuse"),
                                                        in: choosing.history(enlarged: false)), "choose.syr")
        // A visible key context keeps the key, and its words stay reachable.
        let context = FieldHistoryKeyContext10868(label: "Contract result", words: "Lost", spoken: nil)
        let withContext = LacrosseEventPageModel10868(Self.page(.final, history: Self.history(.final, keyContext: context)))
        XCTAssertFalse(withContext.hidesSharedKey)
        XCTAssertTrue(withContext.history(enlarged: false).showsKey)
        XCTAssertEqual(FieldHistoryGeometry10868.keyContext(withContext.history(enlarged: false).series[1]), context)
        // A key context with no visible words is not a context: the key may hide.
        let blank = FieldHistoryKeyContext10868(label: "Contract result", words: " ", spoken: nil)
        XCTAssertTrue(LacrosseEventPageModel10868(Self.page(.final, history: Self.history(.final, keyContext: blank))).hidesSharedKey)
    }

    // MARK: Inline mount and key (L3)

    func testTheInlineComparisonMountsOnlyAtTheFinalOrWhileAMinuteIsInspectedAndTheKeyFollowsIt() {
        // Each context: its page input and whether the comparison is mounted inline.
        let contexts: [(name: String, input: LacrosseEventPageInput10868, inline: Bool)] = [
            ("before", Self.page(.before), false),
            ("ordinary during", Self.page(.during), false),
            ("inspected before", Self.page(.before, history: Self.history(.before, inspect: 1779559560)), true),
            ("inspected before at the pre-match minute", Self.page(.before, history: Self.history(.before, inspect: Self.baselineAt)), true),
            ("inspected during", Self.page(.during, history: Self.history(.during, inspect: 1779563280)), true),
            ("final", Self.page(.final), true),
            ("inspected final", Self.page(.final, history: Self.history(.final, inspect: 1779559560)), true),
        ]
        for context in contexts {
            let input = context.input
            let model = LacrosseEventPageModel10868(input)
            let view = LacrosseEventPagePresentation10868(input: input)
            // The mount decision: the explicit phase and the history's own inspection or intent.
            XCTAssertEqual(model.showsComparison(reader: false), context.inline, context.name)
            XCTAssertEqual(model.isInspecting, context.name.hasPrefix("inspected"), context.name)
            XCTAssertTrue(model.showsComparison(reader: true), context.name)
            XCTAssertEqual(view.comparisonContent(reader: false) != nil, context.inline, context.name)

            // The full reader mounts it in every phase, from its own copy, and
            // the plain key gives way to it there.
            let readerCopy = model.readerHistory(enlarged: false)
            guard let reader = view.comparisonContent(reader: true) else { return XCTFail(context.name) }
            XCTAssertEqual(reader.history, readerCopy, context.name)
            XCTAssertEqual(reader.entries.map(\.slots), Self.slots(readerCopy), context.name)
            XCTAssertFalse(readerCopy.showsKey, context.name)

            // Inline the key follows the mount: the owner's own where absent,
            // hidden only where the comparison stands in for it.
            let inlineCopy = model.history(enlarged: false)
            XCTAssertEqual(inlineCopy.showsKey, !context.inline, context.name)
            XCTAssertEqual(view.historyContent(reader: false).input, inlineCopy, context.name)
            if let inline = view.comparisonContent(reader: false) {
                XCTAssertEqual(inline.history, inlineCopy, context.name)
                XCTAssertEqual(inline.entries.map(\.slots), reader.entries.map(\.slots), "\(context.name): same slots wherever shown")
            }
            // Readouts, actions and the owner's input never depend on the mount.
            XCTAssertEqual(Self.slots(inlineCopy), Self.slots(input.history), context.name)
            XCTAssertEqual(Self.slots(readerCopy), Self.slots(input.history), context.name)
            XCTAssertEqual(FieldHistoryGeometry10868.actions(inlineCopy), FieldHistoryGeometry10868.actions(input.history), context.name)
            XCTAssertEqual(inlineCopy.series, input.history.series, context.name)
            XCTAssertEqual(inlineCopy.inspection, input.history.inspection, context.name)
            XCTAssertEqual(model.input, input, context.name)
            XCTAssertTrue(input.history.showsKey, context.name)
        }
        // Where the comparison is absent, the inline copy IS the owner's input.
        XCTAssertEqual(LacrosseEventPageModel10868(Self.page(.before)).history(enlarged: false), Self.page(.before).history)
        XCTAssertEqual(LacrosseEventPageModel10868(Self.page(.during)).history(enlarged: false), Self.page(.during).history)

        // Same observation versus equal values at different minutes, inline before play.
        let sameMinute = LacrosseEventPagePresentation10868(
            input: Self.page(.before, history: Self.history(.before, inspect: Self.baselineAt))).comparisonContent(reader: false)
        XCTAssertEqual(sameMinute?.entries.map(\.slots.count), [1, 1])
        let equalValue = LacrosseEventPagePresentation10868(
            input: Self.page(.before, history: Self.history(.before, inspect: 1779559560))).comparisonContent(reader: false)
        XCTAssertEqual(equalValue?.entries.first?.slots.map(\.display), [
            .figure("70%", provenance: Self.baselineProvenance), .figure("70%", provenance: "May 23, 11:06 AM PDT"),
        ])

        // A readout intent that reads the inspected observation mounts it, even without an inspection.
        let intentOnly = Self.variant(Self.history(.during), readout: .beforeAndInspected(beforeLabel: "Pre-match", inspectedLabel: "Inspected"))
        XCTAssertNil(intentOnly.inspection)
        XCTAssertTrue(LacrosseEventPageModel10868(Self.page(.during, history: intentOnly)).showsComparison(reader: false))

        // A choose action or a visible key context keeps the key wherever the
        // comparison is mounted, so the key is visible in every phase and size.
        let keyContext = FieldHistoryKeyContext10868(label: "Contract result", words: "Lost", spoken: nil)
        for phase in Phase.allCases {
            for history in [Self.history(phase, choose: true), Self.history(phase, keyContext: keyContext)] {
                let model = LacrosseEventPageModel10868(Self.page(phase, history: history))
                XCTAssertFalse(model.hidesSharedKey, "\(phase)")
                XCTAssertTrue(model.history(enlarged: false).showsKey, "\(phase)")
                XCTAssertTrue(model.readerHistory(enlarged: false).showsKey, "\(phase)")
            }
        }
        XCTAssertEqual(FieldHistoryGeometry10868.keyContext(
            LacrosseEventPageModel10868(Self.page(.before, history: Self.history(.before, keyContext: keyContext)))
                .history(enlarged: false).series[1]), keyContext)
        // An owner that hides its key is never forced to show it, and the key
        // is never hidden where the owner shows it and the comparison is absent.
        let hiddenByOwner = LacrosseEventPageModel10868(Self.page(.before, history: Self.variant(Self.history(.before), showsKey: false)))
        XCTAssertFalse(hiddenByOwner.history(enlarged: false).showsKey)
        XCTAssertFalse(hiddenByOwner.readerHistory(enlarged: false).showsKey)
        XCTAssertFalse(hiddenByOwner.showsComparison(reader: false))

        // With the inline key visible before play, its choose control acts once
        // after the hold on the page and exactly in the reader.
        var log: [String] = []
        let choosingBefore = Self.page(.before, history: Self.history(.before, choose: true))
        let page = LacrosseEventPagePresentation10868(input: choosingBefore,
                                                      onHistoryAction: { log.append("history:\($0)") },
                                                      onInteraction: { log.append("hold") })
        XCTAssertNil(page.comparisonContent(reader: false))
        XCTAssertNotNil(page.comparisonContent(reader: true))
        let anchor = page.historyContent(reader: false)
        XCTAssertTrue(anchor.input.showsKey)
        guard let notreDame = anchor.input.series.first else { return XCTFail("the Notre Dame series") }
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(notreDame, hasCallback: true, in: anchor.input), .live(id: "choose.not"))
        XCTAssertEqual(log, [], "deciding the mount and building the comparison call nothing")
        anchor.onAction?("choose.not")
        page.historyContent(reader: true).onAction?("choose.syr")
        XCTAssertEqual(log, ["hold", "history:choose.not", "history:choose.syr"])

        // Absent callbacks: the key stays with a static choose control; nothing acts and nothing holds.
        log = []
        let silent = LacrosseEventPagePresentation10868(input: choosingBefore, onInteraction: { log.append("hold") })
        XCTAssertNil(silent.comparisonContent(reader: false))
        XCTAssertNotNil(silent.comparisonContent(reader: true))
        XCTAssertNil(silent.historyContent(reader: false).onAction)
        XCTAssertNil(silent.historyContent(reader: true).onAction)
        XCTAssertEqual(FieldHistoryGeometry10868.chooseState(notreDame, hasCallback: false,
                                                             in: silent.historyContent(reader: false).input), .shownStatic)
        XCTAssertEqual(log, [])
    }

    // MARK: Plot heights (L2)

    func testPlotHeightsFallBackToTheUsableStandardAndNeverShrinkWhenEnlarged() {
        func heights(_ standard: CGFloat?, _ enlarged: CGFloat?, history: CGFloat = 302) -> (CGFloat, CGFloat) {
            let input = Self.page(.final, history: Self.history(.final, plotHeight: history),
                                  heights: LacrosseEventPageHistoryHeights10868(standard: standard, enlarged: enlarged))
            let model = LacrosseEventPageModel10868(input)
            return (model.plotHeight(enlarged: false), model.plotHeight(enlarged: true))
        }
        func assertHeights(_ value: (CGFloat, CGFloat), _ expected: (CGFloat, CGFloat), _ message: String,
                           file: StaticString = #filePath, line: UInt = #line) {
            XCTAssertEqual(value.0, expected.0, "standard: \(message)", file: file, line: line)
            XCTAssertEqual(value.1, expected.1, "enlarged: \(message)", file: file, line: line)
        }
        assertHeights(heights(302, 380), (302, 380), "valid owner heights")
        assertHeights(heights(nil, 380), (302, 380), "nil standard falls back to the history's own")
        assertHeights(heights(0, 380), (302, 380), "zero standard")
        assertHeights(heights(-10, 380), (302, 380), "negative standard")
        assertHeights(heights(.nan, .infinity), (302, 302), "NaN and infinity")
        assertHeights(heights(302, nil), (302, 302), "nil enlarged keeps the standard")
        assertHeights(heights(302, 0), (302, 302), "zero enlarged")
        assertHeights(heights(302, -5), (302, 302), "negative enlarged")
        assertHeights(heights(302, .nan), (302, 302), "NaN enlarged")
        assertHeights(heights(302, 250), (302, 302), "a smaller enlarged height never shrinks the plot")
        assertHeights(heights(400, 380), (400, 400), "enlarged never below a taller standard")
        assertHeights(heights(.infinity, 380, history: 260), (260, 380), "the history's own usable height backs the standard")

        // No owner heights at all: the history's own, both sizes.
        let none = LacrosseEventPageModel10868(Self.page(.final, withoutHeights: true))
        XCTAssertEqual(none.plotHeight(enlarged: false), 302)
        XCTAssertEqual(none.plotHeight(enlarged: true), 302)
        // Nothing usable anywhere: the history's own value passes unchanged to the
        // shared leaf, which keeps its own rule — no constant is invented here.
        let unusable = LacrosseEventPageModel10868(Self.page(.final, history: Self.history(.final, plotHeight: 0),
                                                             heights: LacrosseEventPageHistoryHeights10868(standard: nil, enlarged: -1)))
        XCTAssertEqual(unusable.plotHeight(enlarged: false), 0)
        XCTAssertEqual(unusable.plotHeight(enlarged: true), 0)
        XCTAssertEqual(FieldHistoryGeometry10868.plotHeight(0), FieldHistoryGeometry10868.referencePlotHeight)

        // Page and reader take the same rule; geometry only.
        let model = LacrosseEventPageModel10868(Self.page(.final))
        for enlarged in [false, true] {
            XCTAssertEqual(model.history(enlarged: enlarged).plotHeight, enlarged ? 380 : 302)
            XCTAssertEqual(model.readerHistory(enlarged: enlarged).plotHeight, model.history(enlarged: enlarged).plotHeight)
            XCTAssertEqual(model.history(enlarged: enlarged).series, Self.page(.final).history.series)
        }
    }

    // MARK: Arrangement

    func testQuarterAndPagePlansReflowFor375_393WideAndAccessibilitySizes() {
        // Phone, page and card padding 16 each side: 375 → 311, 393 → 329.
        func columns(_ width: CGFloat, accessibility: Bool, measured: CGFloat) -> Int {
            SquashGameScoresGeometry10868.columns(count: 4, available: width, spacing: 6, accessibilitySize: accessibility,
                                                  measure: { _, _ in measured })
        }
        XCTAssertEqual(columns(311, accessibility: false, measured: 64), 4)
        XCTAssertEqual(columns(329, accessibility: false, measured: 64), 4)
        XCTAssertEqual(columns(788, accessibility: false, measured: 64), 4)
        XCTAssertEqual(columns(311, accessibility: false, measured: 90), 3)
        XCTAssertEqual(SquashGameScoresGeometry10868.lines(count: 4, columns: 3), [[0, 1, 2], [3]])
        XCTAssertEqual(columns(311, accessibility: true, measured: 120), 2)
        XCTAssertEqual(columns(788, accessibility: true, measured: 120), 2)
        XCTAssertEqual(columns(311, accessibility: true, measured: 200), 1)
        XCTAssertEqual(SquashGameScoresGeometry10868.lines(count: 4, columns: 2), [[0, 1], [2, 3]])

        XCTAssertEqual(LacrosseEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(LacrosseEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(LacrosseEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(LacrosseEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])

        // One non-colour identity per team across headline, history, comparison and quarters.
        let headline = Self.headline(.final)
        XCTAssertEqual(headline.displayed.map(\.name), ["Notre Dame", "Syracuse"])
        XCTAssertEqual(headline.displayed.map(\.keyShape), [.circle, .diamond])
        XCTAssertEqual(Self.history(.final).series.map(\.shape), [.circle, .diamond])
        XCTAssertEqual([Self.periods(.final).first.shape, Self.periods(.final).second.shape], [.circle, .diamond])
        XCTAssertEqual(SquashGameScoresGeometry10868.symbol(.diamond), "diamond.fill")
    }
}
