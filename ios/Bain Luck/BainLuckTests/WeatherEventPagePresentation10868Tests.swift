import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the daily-high page for the existing weather-range route, as a
/// composition of the accepted leaves before, during and after the day.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition the page defers to: the phase gates and the cards each phase
/// mounts with which exact owner input, the focused readout slots the shared
/// history itself resolves (and the compact context reads), the outlook and
/// noon inputs, the station and result channels, the reachable text of every
/// phase, held-original and inspected-sample withdrawal, the full-size readers,
/// the hold ordering of every action and the arrangement candidates. Nothing
/// here claims a compile, a rendered fit, a pinned header, VoiceOver, a native
/// runtime or a live weather route.
///
/// ARCHIVED values, Polymarket event 1186943 (New York daily high, October 16,
/// 2026, station KLGA), from `weatherCapture.json` (sha256 dc8e9e34…b896) and
/// the retained packets `WEATHER-RANGE-OUTLOOK-RETAINED-CASES.json` and
/// `WEATHER-RANGE-MOVEMENT-RETAINED-CASES.json`:
/// - the 11 range markets and their 22 independent Yes/No outcome tokens (ids,
///   labels, predicates, the one shared original rules text);
/// - each token's last sample strictly before the day (`before.p`, `.t`) and
///   its own sample recorded by noon (`recorded_by_noon.p`, `.t`) and raw CLOB
///   winner flag. The 11 Yes baselines sum to 1.0205. The approved outlook
///   shows 70–71…78–79°F Yes (0.0555 / 0.23 / 0.425 / 0.25 / 0.0495) on 0…0.5
///   with 74–75°F Yes selected; the approved noon card shows 72–73, 76–77,
///   70–71°F Yes (0.23 → 0.345, 0.25 → 0.149, 0.0555 → 0.093) on ±15 pp;
/// - representative samples of the default cohort (74–75 circle, 76–77
///   triangle, 72–73 diamond): Oct 15 8, 10 and 11 PM, Oct 16 12 and 1 AM, 10
///   and 11 AM, 12, 1, 3, 4, 10 and 11 PM, and one post-day control (Oct 17
///   12 AM) — with the real 8→10 PM Oct 15 and 1→3 PM Oct 16 gaps;
/// - day start 1792123200, noon 1792166400, day end 1792209600 (the event's New
///   York day); station: 160 observations through noon, captured high 66.2°F
///   (first 9:00 AM ET); 306 through the day, maximum 75.2°F (first 5:10 PM
///   ET) — sub-hourly Celsius-precision facts, never the contract's
///   whole-degree hourly actual and never a grade.
///
/// CONSTRUCTED: every display string, ET clock word (from each sample's own
/// archived time), figure (at most one decimal), movement word, label, tint,
/// scope, id, action id, observation key, stream, story link, ranked id,
/// heading, Info and source sentence, the history domain (hours from the day
/// start), the owner's runs and breaks over the representative samples, the
/// readout intents and focused selected readouts, every held inspection, the
/// result and station words, the recorded Details context, and every rejected,
/// withdrawn, omitted, foreign and duplicate case. The retained capture proves
/// no live update: the BEFORE and DURING pages are constructed snapshots of the
/// archived day, cut at the day start and at noon.
///
/// PHASE-APPROPRIATE OWNER TEXT. The page shows the owner's Info, source,
/// report and original text verbatim and decides nothing about when a fact
/// became known, so each constructed owner supplies only what it could know:
/// before the day no station, later reading or result; during the day no final
/// maximum, no final result and no end-of-day fact; after the day the full
/// rules, provenance and result. The reachable-text guard below checks every
/// header, readout, card, Info, source, original and spoken line, with a final
/// positive control.
@MainActor
final class WeatherEventPagePresentation10868Tests: XCTestCase {
    private typealias Originals = OriginalMarketDetails9483
    private typealias Tests = WeatherEventPagePresentation10868Tests
    private typealias Stream = StoryStreamPresentation10868

    // MARK: Originals (ARCHIVED identities and samples; CONSTRUCTED words)

    private typealias Row = (
        market: String, side: String, outcome: String, label: String,
        before: Double, beforeFigure: String, beforeT: Int, beforeClock: String,
        noon: Double, noonFigure: String, noonT: Int, noonClock: String,
        movement: String, winner: Bool
    )

    private static let rows: [Row] = [
        ("5680542", "Yes", "8913365083547058840727648558007260174176426214539964433076390904943107112394", "63°F or below", 0.001, "0.1%", 1792119624, "Oct 15, 11:00:24 PM ET", 0.0005, "0.1%", 1792162828, "Oct 16, 11:00:28 AM ET", "-0.1 pp", false),
        ("5680542", "No", "67143910402456435176578359128729756115174394812031754735508727643398464506662", "63°F or below", 0.999, "99.9%", 1792119626, "Oct 15, 11:00:26 PM ET", 0.9995, ">99.9%", 1792162829, "Oct 16, 11:00:29 AM ET", "+0.1 pp", true),
        ("5680543", "Yes", "21435336294206529333936969966675079269275336661376130928308328232499909515391", "64-65°F", 0.0005, "0.1%", 1792119639, "Oct 15, 11:00:39 PM ET", 0.0005, "0.1%", 1792162843, "Oct 16, 11:00:43 AM ET", "0.0 pp", false),
        ("5680543", "No", "48052455767302060707788102938270415116722038376468308401484694477735066651219", "64-65°F", 0.9995, ">99.9%", 1792119628, "Oct 15, 11:00:28 PM ET", 0.9995, ">99.9%", 1792162832, "Oct 16, 11:00:32 AM ET", "0.0 pp", true),
        ("5680544", "Yes", "107185634455894843610821566880080305468286254817220973775097065618207888752080", "66-67°F", 0.0025, "0.3%", 1792119632, "Oct 15, 11:00:32 PM ET", 0.004, "0.4%", 1792162836, "Oct 16, 11:00:36 AM ET", "+0.1 pp", false),
        ("5680544", "No", "115375096568369311164990277104328957168943720891530048218212965811147823644840", "66-67°F", 0.9975, "99.8%", 1792119627, "Oct 15, 11:00:27 PM ET", 0.996, "99.6%", 1792162831, "Oct 16, 11:00:31 AM ET", "-0.2 pp", true),
        ("5680545", "Yes", "22967642455827047245443771889541595907465471141356386761611041695657210518526", "68-69°F", 0.0045, "0.5%", 1792119629, "Oct 15, 11:00:29 PM ET", 0.003, "0.3%", 1792162833, "Oct 16, 11:00:33 AM ET", "-0.1 pp", false),
        ("5680545", "No", "111537624900846583946658455929539667688050754968556058471851612149659391288540", "68-69°F", 0.9955, "99.6%", 1792119623, "Oct 15, 11:00:23 PM ET", 0.997, "99.7%", 1792162827, "Oct 16, 11:00:27 AM ET", "+0.1 pp", true),
        ("5680546", "Yes", "30208396863628859266853401360725945315246332277999808492807567061425111095221", "70-71°F", 0.0555, "5.6%", 1792119629, "Oct 15, 11:00:29 PM ET", 0.093, "9.3%", 1792162833, "Oct 16, 11:00:33 AM ET", "+3.8 pp", false),
        ("5680546", "No", "55998474664018695178236956222472451286538263762519786120813722164777651946447", "70-71°F", 0.9445, "94.5%", 1792119637, "Oct 15, 11:00:37 PM ET", 0.907, "90.7%", 1792162841, "Oct 16, 11:00:41 AM ET", "-3.7 pp", true),
        ("5680547", "Yes", "42036490969657814030627686441430315859255282297966320641421618604860015683758", "72-73°F", 0.23, "23%", 1792119631, "Oct 15, 11:00:31 PM ET", 0.345, "34.5%", 1792162834, "Oct 16, 11:00:34 AM ET", "+11.5 pp", false),
        ("5680547", "No", "78761077488813221723830555306140100365304550954782607751025590225868446872439", "72-73°F", 0.77, "77%", 1792119626, "Oct 15, 11:00:26 PM ET", 0.655, "65.5%", 1792162830, "Oct 16, 11:00:30 AM ET", "-11.5 pp", true),
        ("5680548", "Yes", "97348811011973241846205943545597316259341369137822213272638970018898274192104", "74-75°F", 0.425, "42.5%", 1792119624, "Oct 15, 11:00:24 PM ET", 0.395, "39.5%", 1792162828, "Oct 16, 11:00:28 AM ET", "-3.0 pp", true),
        ("5680548", "No", "28807578185858778284793037276021658713791873585944870616198704837627433997315", "74-75°F", 0.575, "57.5%", 1792119635, "Oct 15, 11:00:35 PM ET", 0.605, "60.5%", 1792162838, "Oct 16, 11:00:38 AM ET", "+3.0 pp", false),
        ("5680549", "Yes", "62146049061772800442104405416602150380256265203802495142118020885435023782389", "76-77°F", 0.25, "25%", 1792119633, "Oct 15, 11:00:33 PM ET", 0.149, "14.9%", 1792162836, "Oct 16, 11:00:36 AM ET", "-10.1 pp", false),
        ("5680549", "No", "108307178477820030136628870794100368956919345679782937733831167636973962051916", "76-77°F", 0.75, "75%", 1792119639, "Oct 15, 11:00:39 PM ET", 0.808, "80.8%", 1792162843, "Oct 16, 11:00:43 AM ET", "+5.8 pp", true),
        ("5680550", "Yes", "21314677505606064787348766190871059866661422817349009784997764731054747568592", "78-79°F", 0.0495, "5%", 1792119638, "Oct 15, 11:00:38 PM ET", 0.018, "1.8%", 1792162842, "Oct 16, 11:00:42 AM ET", "-3.1 pp", false),
        ("5680550", "No", "27892904031490668791126455162520384280106755558205528849525683031242904636615", "78-79°F", 0.9505, "95.1%", 1792119638, "Oct 15, 11:00:38 PM ET", 0.982, "98.2%", 1792162842, "Oct 16, 11:00:42 AM ET", "+3.1 pp", true),
        ("5680551", "Yes", "96821810520797185036939183674087082483401017115855467226269310242027501278307", "80-81°F", 0.0015, "0.2%", 1792119631, "Oct 15, 11:00:31 PM ET", 0.0025, "0.3%", 1792162834, "Oct 16, 11:00:34 AM ET", "+0.1 pp", false),
        ("5680551", "No", "54280296140785189409090952621928778327442017227711905048188438819366865032300", "80-81°F", 0.9985, "99.9%", 1792119637, "Oct 15, 11:00:37 PM ET", 0.9975, "99.8%", 1792162840, "Oct 16, 11:00:40 AM ET", "-0.1 pp", true),
        ("5680552", "Yes", "29814975981391780694220300609647509354017812743734941224964105916454287716710", "82°F or higher", 0.0005, "0.1%", 1792119640, "Oct 15, 11:00:40 PM ET", 0.0005, "0.1%", 1792162844, "Oct 16, 11:00:44 AM ET", "0.0 pp", false),
        ("5680552", "No", "22622594704289114994972145212761010706883868125649760533252652075898736439602", "82°F or higher", 0.9995, ">99.9%", 1792119635, "Oct 15, 11:00:35 PM ET", 0.9995, ">99.9%", 1792162838, "Oct 16, 11:00:38 AM ET", "0.0 pp", true),
    ]

    private static let markets = ["5680542", "5680543", "5680544", "5680545", "5680546", "5680547",
                                  "5680548", "5680549", "5680550", "5680551", "5680552"]

    /// ARCHIVED predicates, verbatim.
    private static let predicates: [String: String] = [
        "5680542": "Will the highest temperature in New York City be 63°F or below on October 16?",
        "5680543": "Will the highest temperature in New York City be between 64-65°F on October 16?",
        "5680544": "Will the highest temperature in New York City be between 66-67°F on October 16?",
        "5680545": "Will the highest temperature in New York City be between 68-69°F on October 16?",
        "5680546": "Will the highest temperature in New York City be between 70-71°F on October 16?",
        "5680547": "Will the highest temperature in New York City be between 72-73°F on October 16?",
        "5680548": "Will the highest temperature in New York City be between 74-75°F on October 16?",
        "5680549": "Will the highest temperature in New York City be between 76-77°F on October 16?",
        "5680550": "Will the highest temperature in New York City be between 78-79°F on October 16?",
        "5680551": "Will the highest temperature in New York City be between 80-81°F on October 16?",
        "5680552": "Will the highest temperature in New York City be 82°F or higher on October 16?",
    ]

    /// ARCHIVED: the one rules text every original carries, paragraph by paragraph.
    private static let rules = [
        "This market will resolve to the temperature range that contains the highest temperature recorded by NOAA at the LaGuardia Airport Station in degrees Fahrenheit on 16 Oct '26.",
        "The resolution source for this market will be information from NOAA, specifically the highest reading under the \"Temp\" column for all times on this day, available here: https://www.weather.gov/wrh/timeseries?site=klga",
        "This market will resolve off of the Hourly Data provided using the \"Show Hourly Data\" button.",
        "If NOAA data for the observation date is unavailable by 11:59 PM ET on the day following the observation date, the Weather Underground Daily Observations table will be used as the resolution source.",
        "In the event that there is no data for the observation date by 11:59 PM ET on the day following the observation date, this market will resolve to the lowest bracket.",
        "To toggle between Fahrenheit and Celsius, click the \"Switch to US Units w/ kts\" button until the relevant table displays °F.",
        "This market will resolve once the first data point for the following date has been published on the resolution source, or by 11:59 PM ET on the day following the observation date, whichever comes first.",
        "The resolution source for this market measures temperatures to whole degrees Fahrenheit (eg, 21°F). Thus, this is the level of precision that will be used when resolving the market.",
        "In the case that the Resolution Source publishes data, sufficient to settle a Market, that is clearly erroneous and the result of technical or operational error, or of unauthorized interference with the Resolution Source or its data, the Market may remain open for a period of up to seven (7) calendar days (ET) from the time of the original release, in anticipation of a correction by the Resolution Source. If the Resolution Source publishes a corrected value within that period, that value will be eligible for resolution. If no corrected value is published within that period, Polymarket will issue a Clarification to determine whether the originally published value may be eligible for resolution, or whether other action is required to preserve the orderly functioning of the Market.",
        "Revisions to temperatures recorded within this market's timeframe will be considered until the first datapoint for the following date has been published, after which any alterations will not be considered.",
    ]

    private static let scope = "constructed:weather:1186943:page"
    private static let dayStart = 1792123200
    private static let noonCutoff = 1792166400
    private static let dayEnd = 1792209600
    private static let baselineLabel = "Last before Oct 16"

    private static func row(_ market: String, _ side: String = "Yes") -> Row {
        rows.first { $0.market == market && $0.side == side }!
    }

    private static func ref(_ market: String, _ side: String = "Yes", scope: String = Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: row(market, side).outcome)
    }

    private static func name(_ row: Row) -> String { "\(row.label) · \(row.side)" }

    private static func beforeReading(_ row: Row) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: baselineLabel, value: .recorded(text: row.beforeFigure, detail: "\(row.beforeClock) · Polymarket sample"))
    }

    private static func noonReading(_ row: Row) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Captured by noon", value: .recorded(text: row.noonFigure, detail: "\(row.noonClock) · Polymarket sample"))
    }

    /// CONSTRUCTED words from this exact token's own ARCHIVED winner flag; at the final only.
    private static func result(_ row: Row) -> FieldChooserResult10868 {
        let words = row.side == "Yes" ? (row.winner ? "Resolved Yes" : "Resolved No") : (row.winner ? "Won" : "Lost")
        return FieldChooserResult10868(title: "Original \(row.side)", words: words)
    }

    // MARK: Samples (ARCHIVED; CONSTRUCTED figures and clocks)

    private struct Sample {
        let t: Int
        let p: Double
        let figure: String
        let clock: String
    }

    /// Index: 0 Oct 15 8 PM · 1 10 PM · 2 11 PM (the before-day reference) · 3 Oct 16 12 AM · 4 1 AM ·
    /// 5 10 AM · 6 11 AM (the noon sample) · 7 12 PM · 8 1 PM · 9 3 PM · 10 4 PM · 11 10 PM · 12 11 PM ·
    /// 13 Oct 17 12 AM (post-day control).
    private static let samples: [String: [Sample]] = [
        "5680548": [
            Sample(t: 1792108828, p: 0.405, figure: "40.5%", clock: "Oct 15, 8:00:28 PM ET"),
            Sample(t: 1792116021, p: 0.405, figure: "40.5%", clock: "Oct 15, 10:00:21 PM ET"),
            Sample(t: 1792119624, p: 0.425, figure: "42.5%", clock: "Oct 15, 11:00:24 PM ET"),
            Sample(t: 1792123215, p: 0.44, figure: "44%", clock: "Oct 16, 12:00:15 AM ET"),
            Sample(t: 1792126821, p: 0.415, figure: "41.5%", clock: "Oct 16, 1:00:21 AM ET"),
            Sample(t: 1792159235, p: 0.485, figure: "48.5%", clock: "Oct 16, 10:00:35 AM ET"),
            Sample(t: 1792162828, p: 0.395, figure: "39.5%", clock: "Oct 16, 11:00:28 AM ET"),
            Sample(t: 1792166427, p: 0.265, figure: "26.5%", clock: "Oct 16, 12:00:27 PM ET"),
            Sample(t: 1792170027, p: 0.235, figure: "23.5%", clock: "Oct 16, 1:00:27 PM ET"),
            Sample(t: 1792177222, p: 0.15, figure: "15%", clock: "Oct 16, 3:00:22 PM ET"),
            Sample(t: 1792180822, p: 0.3, figure: "30%", clock: "Oct 16, 4:00:22 PM ET"),
            Sample(t: 1792202414, p: 0.9995, figure: ">99.9%", clock: "Oct 16, 10:00:14 PM ET"),
            Sample(t: 1792206023, p: 0.9995, figure: ">99.9%", clock: "Oct 16, 11:00:23 PM ET"),
            Sample(t: 1792209619, p: 0.9995, figure: ">99.9%", clock: "Oct 17, 12:00:19 AM ET"),
        ],
        "5680549": [
            Sample(t: 1792108839, p: 0.268, figure: "26.8%", clock: "Oct 15, 8:00:39 PM ET"),
            Sample(t: 1792116024, p: 0.25, figure: "25%", clock: "Oct 15, 10:00:24 PM ET"),
            Sample(t: 1792119633, p: 0.25, figure: "25%", clock: "Oct 15, 11:00:33 PM ET"),
            Sample(t: 1792123218, p: 0.1975, figure: "19.8%", clock: "Oct 16, 12:00:18 AM ET"),
            Sample(t: 1792126824, p: 0.177, figure: "17.7%", clock: "Oct 16, 1:00:24 AM ET"),
            Sample(t: 1792159240, p: 0.2165, figure: "21.7%", clock: "Oct 16, 10:00:40 AM ET"),
            Sample(t: 1792162836, p: 0.149, figure: "14.9%", clock: "Oct 16, 11:00:36 AM ET"),
            Sample(t: 1792166430, p: 0.116, figure: "11.6%", clock: "Oct 16, 12:00:30 PM ET"),
            Sample(t: 1792170031, p: 0.0615, figure: "6.2%", clock: "Oct 16, 1:00:31 PM ET"),
            Sample(t: 1792177225, p: 0.0185, figure: "1.9%", clock: "Oct 16, 3:00:25 PM ET"),
            Sample(t: 1792180826, p: 0.042, figure: "4.2%", clock: "Oct 16, 4:00:26 PM ET"),
            Sample(t: 1792202417, p: 0.0005, figure: "0.1%", clock: "Oct 16, 10:00:17 PM ET"),
            Sample(t: 1792206031, p: 0.0005, figure: "0.1%", clock: "Oct 16, 11:00:31 PM ET"),
            Sample(t: 1792209623, p: 0.0005, figure: "0.1%", clock: "Oct 17, 12:00:23 AM ET"),
        ],
        "5680547": [
            Sample(t: 1792108836, p: 0.185, figure: "18.5%", clock: "Oct 15, 8:00:36 PM ET"),
            Sample(t: 1792116023, p: 0.21, figure: "21%", clock: "Oct 15, 10:00:23 PM ET"),
            Sample(t: 1792119631, p: 0.23, figure: "23%", clock: "Oct 15, 11:00:31 PM ET"),
            Sample(t: 1792123217, p: 0.29, figure: "29%", clock: "Oct 16, 12:00:17 AM ET"),
            Sample(t: 1792126824, p: 0.315, figure: "31.5%", clock: "Oct 16, 1:00:24 AM ET"),
            Sample(t: 1792159239, p: 0.245, figure: "24.5%", clock: "Oct 16, 10:00:39 AM ET"),
            Sample(t: 1792162834, p: 0.345, figure: "34.5%", clock: "Oct 16, 11:00:34 AM ET"),
            Sample(t: 1792166430, p: 0.38, figure: "38%", clock: "Oct 16, 12:00:30 PM ET"),
            Sample(t: 1792170030, p: 0.53, figure: "53%", clock: "Oct 16, 1:00:30 PM ET"),
            Sample(t: 1792177224, p: 0.57, figure: "57%", clock: "Oct 16, 3:00:24 PM ET"),
            Sample(t: 1792180825, p: 0.655, figure: "65.5%", clock: "Oct 16, 4:00:25 PM ET"),
            Sample(t: 1792202417, p: 0.0005, figure: "0.1%", clock: "Oct 16, 10:00:17 PM ET"),
            Sample(t: 1792206029, p: 0.0005, figure: "0.1%", clock: "Oct 16, 11:00:29 PM ET"),
            Sample(t: 1792209622, p: 0.0005, figure: "0.1%", clock: "Oct 17, 12:00:22 AM ET"),
        ],
    ]

    /// The owner's runs over the representative samples: consecutive stretches only.
    private static let runIndices: [ClosedRange<Int>] = [0...4, 5...6, 7...10, 11...12]

    /// The selected range first, then the reference's two fixed anchors.
    private static let cohort: [(market: String, shape: FieldHistoryShape10868, tint: Color)] = [
        ("5680548", .circle, Color(red: 0.0, green: 0.36, blue: 0.75)),
        ("5680549", .triangle, Color(red: 0.85, green: 0.33, blue: 0.10)),
        ("5680547", .diamond, Color(red: 0.36, green: 0.38, blue: 0.42)),
    ]

    private static func x(_ t: Int) -> Double { Double(t - dayStart) / 3600 }

    /// The archived gaps between consecutive retained samples (indices into `samples`):
    /// Oct 15 8 → 10 PM, and Oct 16 1 → 3 PM.
    private static let archivedGaps: [(before: Int, after: Int)] = [(0, 1), (8, 9)]

    /// The owner's explicit breaks over the archived gaps each phase admits: the Oct 15
    /// 8 → 10 PM gap in every phase, the Oct 16 1 → 3 PM gap after the day only. Both the
    /// cohort history and the original's Details history carry exactly these.
    private static func gapBreaks(_ phase: WeatherEventPagePhase10868) -> [FieldHistoryBreak10868] {
        [FieldHistoryBreak10868(id: "gap.oct15.8pm", lower: -3.9, upper: -2.1, mark: "//")]
            + (phase == .final ? [FieldHistoryBreak10868(id: "gap.oct16.1pm", lower: 13.1, upper: 14.9, mark: "//")] : [])
    }

    /// The owner's admission cut per phase: before the day start, through noon, through the day end.
    private static func cutoff(_ phase: WeatherEventPagePhase10868) -> (Int) -> Bool {
        let limit: Int
        switch phase {
        case .before: return { $0 < Tests.dayStart }
        case .during: limit = Tests.noonCutoff
        case .final: limit = Tests.dayEnd
        }
        return { $0 <= limit }
    }

    private static func pointID(_ market: String, _ index: Int) -> String { "\(market).yes.\(samples[market]![index].t)" }

    private static func sample(_ market: String, _ index: Int) -> Sample { samples[market]![index] }

    private static func observation(_ market: String, _ index: Int, _ words: String) -> FieldHistoryReading10868 {
        let s = sample(market, index)
        return .observation(pointID: pointID(market, index), figure: s.figure, provenance: "\(s.clock) · \(words)")
    }

    // MARK: History

    /// The owner's held inspection, CONSTRUCTED.
    private enum Inspect {
        /// The selected reading IS the before-day reference: one dated slot.
        case same
        /// A distinct earlier sample before the day: inspected before Oct 16.
        case earlier
        /// A sample during the day.
        case during
        /// A time with no sample: the owner's own words, never a neighbour.
        case missing
        /// The inspected sample the owner has withdrawn from its runs.
        case omittedSample
    }

    private static func inspectedIndex(_ inspect: Inspect) -> Int? {
        switch inspect {
        case .same: 2
        case .earlier: 1
        case .during, .omittedSample: 5
        case .missing: nil
        }
    }

    private static func inspectedLabel(_ inspect: Inspect) -> String {
        switch inspect {
        case .same: baselineLabel
        case .earlier: "Inspected before Oct 16"
        case .during, .omittedSample: "Recorded chance"
        case .missing: "Selected time"
        }
    }

    private static func action(_ id: String, _ label: String, spoken: String? = nil,
                               available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: available)
    }

    private static func history(_ phase: WeatherEventPagePhase10868, inspect: Inspect? = nil,
                                withoutSelected: Bool = false) -> FieldHistoryInput10868 {
        let admitted = cutoff(phase)
        let selected = row("5680548").outcome
        let omitted = inspect == .omittedSample ? pointID("5680548", 5) : nil
        let members = withoutSelected ? Array(cohort.dropFirst()) : cohort
        let series = members.map { member -> FieldHistorySeries10868 in
            let market = member.market
            let runs = runIndices.compactMap { range -> FieldHistoryRun10868? in
                let points = range.filter { admitted(sample(market, $0).t) }
                    .map { index -> FieldHistoryPoint10868 in
                        let s = sample(market, index)
                        return FieldHistoryPoint10868(id: pointID(market, index), x: x(s.t), probability: s.p,
                                                      style: s.t < dayStart ? .hollow : .filled)
                    }
                    .filter { $0.id != omitted }
                return points.isEmpty ? nil : FieldHistoryRun10868(id: "run.\(market).\(range.lowerBound)", points: points)
            }
            let recorded: FieldHistoryReading10868
            if let inspect, let index = inspectedIndex(inspect) {
                recorded = observation(market, index, inspect == .same ? "last sample before Oct 16" : "Polymarket sample")
            } else {
                switch phase {
                case .before: recorded = .absent(words: "Current probability unavailable")
                case .during: recorded = observation(market, 6, "Polymarket sample")
                case .final: recorded = observation(market, 12, "Polymarket sample")
                }
            }
            return FieldHistorySeries10868(
                id: row(market).outcome, name: name(row(market)), shape: member.shape, tint: member.tint,
                runs: runs, links: [], labelPointID: runs.last?.points.last?.id,
                before: observation(market, 2, "last sample before Oct 16"), recorded: recorded,
                absentWords: "No samples in this view", choose: action("choose.\(market)", "Show \(row(market).label)"))
        }
        let readout: FieldHistoryReadoutIntent10868
        if let inspect {
            readout = inspect == .same
                ? .singleBefore(label: baselineLabel)
                : .beforeAndInspected(beforeLabel: baselineLabel, inspectedLabel: inspectedLabel(inspect))
        } else {
            readout = phase == .before
                ? .singleBefore(label: baselineLabel)
                : .beforeAndRecorded(beforeLabel: baselineLabel,
                                     recordedLabel: phase == .during ? "Recorded chance" : "Last recorded Oct 16")
        }
        var selections: [String: FieldHistorySelection10868] = [:]
        if let inspect {
            for member in members {
                if let index = inspectedIndex(inspect) {
                    selections[row(member.market).outcome] = .point(id: pointID(member.market, index),
                                                                     spoken: sample(member.market, index).figure)
                } else {
                    selections[row(member.market).outcome] = .absent(words: "Not recorded at this time")
                }
            }
        }
        let inspectedX: Double? = inspect.map { inspect in
            inspectedIndex(inspect).map { x(sample("5680548", $0).t) } ?? 14
        }
        let upper: Double = phase == .before ? 0 : phase == .during ? 12 : 24
        var input = FieldHistoryInput10868(
            title: "Daily high · range chances", caption: "Selected range and two compared ranges",
            series: series, selection: .series(id: selected, missingWords: "Your range is not in this history"),
            domain: FieldHistoryDomain10868(lower: -24, upper: upper), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [FieldHistoryTick10868(value: -24, lines: ["Oct 15", "12 AM"]),
                     FieldHistoryTick10868(value: 0, lines: ["Oct 16", "12 AM"])]
                + (phase == .before ? [] : [FieldHistoryTick10868(value: 12, lines: ["Noon"])])
                + (phase == .final ? [FieldHistoryTick10868(value: 24, lines: ["Oct 17", "12 AM"])] : []),
            guides: phase == .before ? [] : [FieldHistoryGuide10868(id: "day-start", x: 0, label: "Oct 16 begins · midnight in New York")],
            breaks: gapBreaks(phase),
            readout: readout,
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: sampled before Oct 16 began in New York",
                                              filled: "Filled: sampled during Oct 16"),
            comparisonExplanation: nil,
            notes: ["Current probability unavailable · a recorded sample is not a verified trade close",
                    "Each range on its own · not normalized · times in New York"]
                + (phase == .during ? ["This snapshot stops at noon in New York."] : [])
                + (phase == .final ? ["Recorded through the end of Oct 16 · no result point is added."] : []),
            summary: phase == .before
                ? "Three independently sampled range histories on a zero to 100% scale, each sampled before Oct 16 began in New York. These are probabilities, not temperatures."
                : "Three independently sampled range histories on a zero to 100% scale. Hollow marks were sampled before Oct 16 began in New York; filled marks during the day. These are probabilities, not temperatures.",
            plotHeight: 300, unboundReadingWords: "Unavailable", plotUnavailableWords: "History unavailable",
            windows: nil, scale: nil, moreOriginals: nil,
            details: action("history.original", "Original 74-75°F · Yes", spoken: "Open the original 74-75°F Yes at the inspected time"),
            expand: action("history.expand", "Expand", spoken: "Open the daily-high probability history"),
            inspect: nil,
            previous: action("history.previous", "‹", spoken: "Earlier sample"),
            next: action("history.next", "›", spoken: "Later sample"),
            inspection: inspect.map { inspect in
                FieldHistoryInspection10868(
                    x: inspectedX, caption: inspectedIndex(inspect).map { "Inspected \(sample("5680548", $0).clock)" } ?? "Inspected Oct 16, 2:00 PM ET",
                    selections: selections, choices: [], choicePresentation: .slider(label: "Inspect sampled history"),
                    note: "Only exact samples are shown.")
            },
            layout: .focused)
        if let inspect {
            input.selectedReadout = inspect == .same
                ? FieldHistorySelectedReadout10868(beforeLabel: nil, inspectedLabel: baselineLabel)
                : FieldHistorySelectedReadout10868(beforeLabel: baselineLabel, inspectedLabel: inspectedLabel(inspect))
        }
        return input
    }

    // MARK: Cards

    private static func outlookRecord(_ row: Row, phase: WeatherEventPagePhase10868) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(row.market, row.side), name: name(row), plan: .single(beforeReading(row)),
            preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
            movement: nil, clock: nil,
            // Only an owner after the day carries a result.
            result: phase == .final ? result(row) : nil,
            browseStatus: "Recorded outcome")
    }

    private static let outlookShort = ["70-71°", "72-73°", "74-75°", "76-77°", "78-79°"]

    private static func outlook(_ phase: WeatherEventPagePhase10868, catalogue: [FieldChooserOriginal10868]? = nil,
                                selected: String = "5680548") -> FieldOutlookInput10868 {
        FieldOutlookInput10868(
            scope: scope,
            catalogue: catalogue ?? rows.map { outlookRecord($0, phase: phase) },
            selected: FieldChooserSelected10868(ref: ref(selected), words: "Selected",
                                                unavailableWords: "Your range is unavailable in this update."),
            displayed: zip(["5680546", "5680547", "5680548", "5680549", "5680550"], outlookShort).map {
                FieldOutlookSlot10868(ref: ref($0), label: row($0).label, shortLabel: $1)
            },
            traversal: markets.map { ref($0) },
            chances: rows.map { FieldOutlookBeforeChance10868(ref: ref($0.market, $0.side), probability: $0.before, reading: beforeReading($0)) },
            scale: FieldOutlookScale10868(
                ceiling: 0.5,
                ticks: [FieldOutlookTick10868(probability: 0, label: "0%"), FieldOutlookTick10868(probability: 0.25, label: "25%"),
                        FieldOutlookTick10868(probability: 0.5, label: "50%")],
                words: "0–50% chance · each range on its own, not normalized"),
            phase: WeatherEventPageModel10868.leafPhase(phase),
            copy: FieldOutlookCopy10868(
                title: "Before the day began", note: "Five ranges · last chance before Oct 16",
                graphicLabel: "Before-day chance for five temperature ranges", missingChance: "Not shown on this scale",
                offScale: "Above the 50% scale", outsideDisplayed: "Your range is outside the five shown.",
                previousLabel: "Previous temperature range", nextLabel: "Next temperature range",
                details: "Original outcomes & rules", detailsHint: "Opens this exact original",
                resultUnknown: "Result unconfirmed"),
            unavailableWords: "Range unavailable in this update",
            chooseHint: "Shows this range’s before-day chance")
    }

    private static func observationKey(_ row: Row) -> String { "constructed-observation:\(row.market):\(row.side):noon" }

    private static func movement(_ phase: WeatherEventPagePhase10868,
                                 displayed: [(String, String, String)]? = nil) -> FieldMovementInput10868 {
        let shown = displayed ?? [("5680547", "Yes", "72-73°"), ("5680549", "Yes", "76-77°"), ("5680546", "Yes", "70-71°")]
        return FieldMovementInput10868(
            scope: scope,
            catalogue: rows.map {
                FieldChooserOriginal10868(
                    ref: ref($0.market, $0.side), name: name($0),
                    plan: .comparison(before: beforeReading($0), later: noonReading($0)),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: nil, result: nil, browseStatus: "Recorded outcome")
            },
            displayed: shown.map { FieldOutlookSlot10868(ref: ref($0.0, $0.1), label: row($0.0, $0.1).label, shortLabel: $0.2) },
            pairs: rows.map {
                FieldMovementPair10868(
                    ref: ref($0.market, $0.side),
                    before: FieldMovementObservation10868(probability: $0.before, reading: beforeReading($0)),
                    later: FieldMovementObservation10868(probability: $0.noon, reading: noonReading($0)),
                    movement: $0.movement, observation: observationKey($0))
            },
            scale: FieldMovementScale10868(
                limit: 0.15,
                ticks: [FieldMovementTick10868(change: -0.15, label: "-15 pp"), FieldMovementTick10868(change: 0, label: "0"),
                        FieldMovementTick10868(change: 0.15, label: "+15 pp")],
                words: "−15 to +15 percentage points · each range on its own"),
            phase: WeatherEventPageModel10868.leafPhase(phase),
            copy: FieldMovementCopy10868(
                title: "By noon, the outlook shifted", note: "Before the day → captured by noon · percentage points",
                graphicLabel: "Noon change for three temperature ranges", beforeLabel: baselineLabel,
                laterLabel: "Captured by noon", endpointUnavailable: "Not recorded for this comparison",
                changeUnavailable: "Change unavailable", offScale: "Beyond the ±15 pp scale",
                openLabel: "Original · exact times", openHint: "Opens this exact original at its recorded time"),
            unavailableWords: "Range unavailable in this update")
    }

    // MARK: Stream, words and Info

    private static func streamScope(_ phase: WeatherEventPagePhase10868) -> String { "constructed:weather:1186943:\(phase.rawValue)" }

    private static func stream(_ phase: WeatherEventPagePhase10868) -> Stream {
        let scope = streamScope(phase)
        func cardRef(_ id: String) -> Stream.CardRef { .init(scope: scope, id: id) }
        return Stream(
            scope: scope, eyebrow: "THE DAY IN PROBABILITIES", heading: "The day in probabilities",
            cards: [Stream.Card(id: "ranges", name: "Before-day ranges")]
                + (phase == .before ? [] : [Stream.Card(id: "movement", name: "Probability changes")]),
            primary: cardRef("ranges"),
            position: phase == .before ? "1 of 1" : "1 of 2",
            basis: "Recorded day · each probability keeps its own clock",
            previous: nil, next: phase == .before ? nil : cardRef("movement"))
    }

    private static let stories = [
        WeatherEventPageStory10868(cardID: "ranges", card: .ranges),
        WeatherEventPageStory10868(cardID: "movement", card: .movement),
    ]

    private static func contextHeading(_ phase: WeatherEventPagePhase10868) -> String {
        switch phase {
        case .before: "New York · Before Oct 16"
        case .during: "New York · By noon"
        case .final: "New York · 74-75°F resolved"
        }
    }

    private static func header(_ phase: WeatherEventPagePhase10868) -> WeatherEventPageHeader10868 {
        WeatherEventPageHeader10868(
            title: "New York’s daily high", place: "LaGuardia Airport · KLGA",
            date: "Friday, October 16, 2026 · the day runs midnight to midnight in New York",
            status: phase == .before ? "Before the day began" : phase == .during ? "Captured by noon in New York" : "74-75°F resolved",
            selectedMeaning: "74-75°F Yes · the day’s high falls in this range",
            infoLabel: "About this temperature event", infoHint: "Opens timing, sources and the original rules")
    }

    private static func station(_ phase: WeatherEventPagePhase10868) -> WeatherEventPageStationFact10868? {
        let note = "Sub-hourly readings at Celsius precision. Not the contract’s whole-degree hourly table; it settles no range."
        switch phase {
        case .before: return nil
        case .during:
            return WeatherEventPageStationFact10868(label: "Captured high so far", value: "66.2°F",
                                                    detail: "160 NWS station observations through noon · first reached at 9:00 AM ET",
                                                    note: note)
        case .final:
            return WeatherEventPageStationFact10868(label: "Captured station high", value: "75.2°F",
                                                    detail: "306 NWS station observations through the end of Oct 16 · first reached at 5:10 PM ET",
                                                    note: note)
        }
    }

    private static let finalResult = WeatherEventPageResultFact10868(
        label: "Resolved range", words: "74-75°F",
        detail: "Exact CLOB winner flags for each original · separate from the last recorded chance")

    private static let provider = WeatherEventPageLink10868(
        id: "provider", label: "Original provider event",
        url: URL(string: "https://polymarket.com/event/highest-temperature-in-nyc-on-october-16-2026")!)

    private static let rulesSourceID = "rules.5680548"

    /// The owner's Info for what it knows in this phase.
    private static func about(_ phase: WeatherEventPagePhase10868) -> WeatherEventPageAbout10868 {
        var sections = [
            WeatherEventPageSection10868(
                title: "Archived weather event · October 16, 2026",
                paragraphs: ["LaGuardia Airport, New York. All 22 original Yes–No outcomes keep their own source identity and independently sampled histories."]),
            WeatherEventPageSection10868(
                title: "Before the day",
                paragraphs: ["Last independently sampled probability strictly before midnight at the start of October 16 in New York. Not a verified market opening or close. The day runs from midnight to midnight in New York; times are New York time."]),
            WeatherEventPageSection10868(
                title: "Recorded probability history",
                paragraphs: ["Public CLOB price-history observations sampled at requested 60-minute fidelity. No trade-volume or simultaneous-field claim. Each Yes/No token has its own history. Current probability unavailable. Independent ranges are not normalized."]),
        ]
        switch phase {
        case .before:
            break
        case .during:
            sections.append(WeatherEventPageSection10868(
                title: "This snapshot",
                paragraphs: ["This snapshot stops at noon in New York. It does not reveal later history or outcomes."]))
        case .final:
            sections.append(WeatherEventPageSection10868(
                title: "This record",
                paragraphs: ["Recorded history stops at the end of the observation day. A resolved outcome is separate from the last recorded chance; no 100% result point is added."]))
            sections.append(WeatherEventPageSection10868(
                title: "Resolved range and station measurements",
                paragraphs: ["Exact CLOB winner flags confirm 74-75°F Yes. The independently captured NWS station maximum is 75.2°F at sub-hourly Celsius precision. The contract uses a whole-degree Fahrenheit hourly table; this station maximum does not settle the original and is not its exact actual."]))
        }
        sections.append(WeatherEventPageSection10868(
            title: "Original source rules", paragraphs: ["Each original keeps its own rules and identity."],
            link: provider, sourceID: rulesSourceID))
        return WeatherEventPageAbout10868(title: "About this temperature event", sections: sections)
    }

    private static func sources(_ phase: WeatherEventPagePhase10868) -> [WeatherEventPageSource10868] {
        var sections = [
            WeatherEventPageSection10868(title: "Original rules", paragraphs: rules),
            WeatherEventPageSection10868(title: "Identity", paragraphs: ["Event 1186943 · market 5680548 · Yes and No tokens"], link: provider),
        ]
        if phase == .final {
            sections.append(WeatherEventPageSection10868(
                title: "Result source",
                paragraphs: ["Result comes from each exact token’s CLOB winner flag. Independently captured station measurements do not adjudicate this original."]))
        }
        return [WeatherEventPageSource10868(id: rulesSourceID, title: "74-75°F original source", sections: sections)]
    }

    private static func copy(_ phase: WeatherEventPagePhase10868) -> WeatherEventPageCopy10868 {
        WeatherEventPageCopy10868(
            storiesLabel: "The day in probabilities", storyUnavailable: "This card is not available in this update.",
            catalogueLabel: "All 11 ranges · 22 original outcomes", openCardLabel: "Open full card",
            sourceLabel: "Source details & rules", sourceUnavailable: "This source is not available in this update.",
            context: WeatherEventPageContextCopy10868(label: "Selected range probability", heading: contextHeading(phase),
                                                      chartLabel: "Chart", chartSpokenLabel: "Open the daily-high probability history"))
    }

    /// The owner's page parts for one phase, phase-correct by construction;
    /// tests replace single parts for rejected or withdrawn controls.
    private struct Parts {
        var phase: WeatherEventPagePhase10868
        var header: WeatherEventPageHeader10868
        var reader: WeatherEventPageReaderHeader10868
        var history: FieldHistoryInput10868
        var outlook: FieldOutlookInput10868?
        var movement: FieldMovementInput10868?
        var stream: Stream?
        var stories: [WeatherEventPageStory10868]
        var ranked: [String]
        var station: WeatherEventPageStationFact10868?
        var result: WeatherEventPageResultFact10868?
        var about: WeatherEventPageAbout10868?
        var sources: [WeatherEventPageSource10868]
        var copy: WeatherEventPageCopy10868

        var input: WeatherEventPageInput10868 {
            WeatherEventPageInput10868(
                phase: phase, header: header, reader: reader, history: history, outlook: outlook, movement: movement,
                stream: stream, stories: stories, ranked: ranked, station: station, result: result,
                about: about, sources: sources, copy: copy)
        }
    }

    private static func parts(_ phase: WeatherEventPagePhase10868, inspect: Inspect? = nil) -> Parts {
        Parts(
            phase: phase, header: header(phase),
            reader: WeatherEventPageReaderHeader10868(title: contextHeading(phase), state: "74-75°F · Yes"),
            history: history(phase, inspect: inspect),
            outlook: outlook(phase),
            movement: phase == .before ? nil : movement(phase),
            stream: stream(phase), stories: stories,
            ranked: phase == .before ? ["ranges"] : ["ranges", "movement"],
            station: station(phase), result: phase == .final ? finalResult : nil,
            about: about(phase), sources: sources(phase), copy: copy(phase))
    }

    private static func page(_ phase: WeatherEventPagePhase10868, inspect: Inspect? = nil) -> WeatherEventPageInput10868 {
        parts(phase, inspect: inspect).input
    }

    // MARK: Original outcomes

    private static let originalsScope = "constructed:weather:1186943:originals"

    private static func identity(_ market: String, _ side: String) -> Originals.Identity {
        Originals.Identity(source: "polymarket", market: market, side: side)
    }

    private static func pregameReading(_ row: Row) -> Originals.Reading {
        .value(row.beforeFigure, placement: row.before, provenance: "\(row.beforeClock) · last sample before Oct 16")
    }

    private static func recordedContext(_ phase: WeatherEventPagePhase10868) -> Originals.RecordedHistory {
        let selected = row("5680548")
        let seriesID = "constructed.original.history.\(selected.outcome)"
        let admitted = cutoff(phase)
        let runs = runIndices.compactMap { range -> FieldHistoryRun10868? in
            let points = range.filter { admitted(sample("5680548", $0).t) }.map { index -> FieldHistoryPoint10868 in
                let s = sample("5680548", index)
                return FieldHistoryPoint10868(id: "original.\(s.t)", x: x(s.t), probability: s.p,
                                              style: s.t < dayStart ? .hollow : .filled)
            }
            return points.isEmpty ? nil : FieldHistoryRun10868(id: "original.run.\(range.lowerBound)", points: points)
        }
        var history = FieldHistoryInput10868(
            title: "74-75°F · Yes sampled history", caption: nil,
            series: [FieldHistorySeries10868(
                id: seriesID, name: name(selected), shape: .circle, tint: cohort[0].tint, runs: runs, links: [],
                labelPointID: nil, before: .absent(words: "Shown above"), recorded: .absent(words: "Shown above"),
                absentWords: "No samples in this view", choose: nil)],
            selection: .series(id: seriesID, missingWords: "This original isn’t in this history"),
            domain: FieldHistoryDomain10868(lower: -24, upper: phase == .before ? 0 : phase == .during ? 12 : 24), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: [], guides: [], breaks: gapBreaks(phase), readout: .singleBefore(label: baselineLabel),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: before Oct 16", filled: "Filled: during the day"),
            comparisonExplanation: nil, notes: [], summary: "74-75°F Yes: its own independently sampled history; no complementary series or appended result.",
            plotHeight: 160, unboundReadingWords: "Unavailable", plotUnavailableWords: "Original history unavailable",
            windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: nil, inspect: nil,
            previous: nil, next: nil, inspection: nil, layout: .expanded)
        history.showsKey = false
        var readings = [Originals.RecordedReading(label: baselineLabel, marker: .hollow, reading: pregameReading(selected))]
        let mode: Originals.Mode
        switch phase {
        case .before:
            mode = .pregame
        case .during:
            mode = .comparison(.recorded)
            readings.append(Originals.RecordedReading(
                label: "Recorded chance", marker: .solid,
                reading: .value(selected.noonFigure, placement: selected.noon, provenance: "\(selected.noonClock) · Polymarket sample")))
        case .final:
            mode = .result
            let last = sample("5680548", 12)
            readings.append(Originals.RecordedReading(
                label: "Last recorded Oct 16", marker: .solid,
                reading: .value(last.figure, placement: last.p, provenance: "\(last.clock) · Polymarket sample")))
        }
        return Originals.RecordedHistory(
            selection: Originals.Selection(scope: originalsScope, identity: identity("5680548", "Yes")), mode: mode,
            seriesID: seriesID, availability: "Current probability unavailable · recorded samples below",
            readings: readings, movement: nil, history: history,
            finishLabel: "Official hourly high",
            finish: phase == .final ? .unlinked(words: "Not captured · the station maximum does not settle this original") : nil,
            preview: nil, expand: nil,
            explore: action("original.explore", "Explore history"),
            unmatchedWords: "Recorded history unavailable for this original")
    }

    /// All 22 independent originals in the owner's phase: their own pregame
    /// reading, their own noon reading during the day, their own grade after it.
    private static func originals(_ phase: WeatherEventPagePhase10868, omitting: (String, String)? = nil,
                                  ungraded: (String, String)? = nil,
                                  selection: (String, String) = ("5680548", "Yes")) -> WeatherEventPageOriginals10868 {
        let admitted = rows.filter { !($0.market == omitting?.0 && $0.side == omitting?.1) }
        let records = admitted.map { row -> Originals.Original in
            let mode: Originals.Mode
            switch phase {
            case .before: mode = .pregame
            case .during: mode = .comparison(.recorded)
            case .final: mode = .result
            }
            let graded = phase == .final && !(row.market == ungraded?.0 && row.side == ungraded?.1)
            return Originals.Original(
                identity: identity(row.market, row.side), title: predicates[row.market]!, outcome: row.side,
                mode: mode, pregame: pregameReading(row),
                later: phase == .during
                    ? Originals.Reading.value(row.noonFigure, placement: row.noon, provenance: "\(row.noonClock) · Polymarket sample")
                    : nil,
                grade: graded ? Originals.Grade(words: row.winner ? "Won" : "Lost", provenance: "Exact CLOB winner flag") : nil,
                about: Originals.About(
                    source: "Polymarket", rules: .verified(rules),
                    provenance: [Originals.Row(label: "Event", value: "1186943"), Originals.Row(label: "Market", value: row.market),
                                 Originals.Row(label: "Outcome", value: row.side), Originals.Row(label: "Token", value: row.outcome)],
                    historicalQuote: nil),
                beforeLabel: baselineLabel)
        }
        var labels: [Originals.Identity: String] = [:]
        for row in rows { labels[identity(row.market, row.side)] = name(row) }
        return WeatherEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: originalsScope, originals: records),
            selection: Originals.Selection(scope: originalsScope, identity: identity(selection.0, selection.1)),
            recorded: recordedContext(phase), labels: labels,
            heading: "All original outcomes", context: "11 ranges · 22 independent Yes/No originals",
            emptyWords: "No original outcomes in this update", unavailableChoice: "Unnamed original",
            tint: cohort[0].tint)
    }

    // MARK: Reachable text

    private static func historyText(_ history: FieldHistoryInput10868) -> [String] {
        var texts = [history.title, history.summary, history.unboundReadingWords] + history.notes
        texts += [history.caption, history.plotUnavailableWords, history.comparisonExplanation,
                  history.probabilityRangeExplanation, history.plotAbsence?.title, history.plotAbsence?.words,
                  FieldHistoryGeometry10868.selectionWords(history)].compactMap { $0 }
        if FieldHistoryGeometry10868.drawsStyle(.hollow, in: history), let words = history.markKey.hollow { texts.append(words) }
        if FieldHistoryGeometry10868.drawsStyle(.filled, in: history), let words = history.markKey.filled { texts.append(words) }
        texts += history.xTicks.flatMap(\.lines) + history.yTicks.flatMap(\.lines)
        texts += history.guides.map(\.label) + history.breaks.map(\.mark)
        texts.append(FieldHistoryGeometry10868.spokenValue(history))
        switch FieldHistoryGeometry10868.selectedSummary(history) {
        case .none: break
        case .words(let words): texts.append(words)
        case .original(let series, let slots): texts += [series.name] + slots.map(FieldHistoryGeometry10868.spokenSlot)
        }
        for series in history.series {
            texts.append(series.name)
            texts += FieldHistoryGeometry10868.readoutSlots(series, in: history).map(FieldHistoryGeometry10868.spokenSlot)
            texts += [FieldHistoryGeometry10868.keyNote(series, in: history)].compactMap { $0 }
        }
        if let inspection = history.inspection {
            texts += [inspection.caption] + [inspection.note].compactMap { $0 }
            texts += inspection.choices.flatMap { $0.lines + [$0.spoken] }
        }
        texts += FieldHistoryGeometry10868.actions(history).flatMap { [$0.label, $0.spokenLabel].compactMap { $0 } }
        return texts
    }

    private static func outlookText(_ model: FieldOutlookModel10868) -> [String] {
        let copy = model.input.copy
        var texts = [copy.title, copy.graphicLabel, model.input.scale.words, copy.previousLabel, copy.nextLabel, copy.details]
        texts += [copy.note, copy.detailsHint].compactMap { $0 }
        texts += model.ticks.map(\.label)
        for bar in model.bars {
            texts += [bar.slot.label, bar.slot.shortLabel, model.barSummary(bar)]
            texts += [model.figure(bar), model.stateWords(bar), bar.resolution.original?.name].compactMap { $0 }
        }
        texts += [model.notice, model.selectedOriginal?.name, model.detailsSpokenLabel,
                  model.neighbour(.previous)?.name, model.neighbour(.next)?.name].compactMap { $0 }
        if let reading = model.selectedReading {
            texts.append(FieldChooserModel10868.spoken(reading))
            texts += [FieldOutlookModel10868.detailLine(reading)].compactMap { $0 }
        }
        switch model.resultLine {
        case .result(let result)?: texts += [result.title, result.words]
        case .unknown(let words)?: texts.append(words)
        case nil: break
        }
        return texts
    }

    private static func movementText(_ model: FieldMovementModel10868) -> [String] {
        let copy = model.input.copy
        var texts = [copy.title, copy.graphicLabel, model.input.scale.words, copy.openLabel]
        texts += [copy.note, copy.openHint].compactMap { $0 }
        texts += model.ticks.map(\.label)
        texts.append(model.graphicSummary)
        for row in model.rows {
            texts += [row.slot.label, row.slot.shortLabel, model.rowSummary(row)]
            texts += [model.movementWords(row), model.stateWords(row)].compactMap { $0 }
        }
        return texts
    }

    private static func sectionsText(_ title: String, _ sections: [WeatherEventPageSection10868]) -> [String] {
        var texts = [title]
        for section in sections {
            texts += [section.title] + section.paragraphs + [section.sourceID].compactMap { $0 }
            if let link = section.link { texts += [link.id, link.label, link.url.absoluteString] }
        }
        return texts
    }

    private static func originalsText(_ originals: WeatherEventPageOriginals10868) -> [String] {
        guard let catalogue = originals.catalogue else { return [] }
        var texts = [originals.heading, originals.emptyWords, originals.unavailableChoice] + [originals.context].compactMap { $0 }
        texts += originals.labels.values.sorted()
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue, selection: originals.selection,
                                                      labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        texts += cards.map { OriginalMarketChooser9483.spoken($0.choice) }
        for original in catalogue.originals {
            let content = Originals.content(catalogue: catalogue,
                                            selection: Originals.Selection(scope: catalogue.scope, identity: original.identity))
            texts.append(Originals.spoken(content))
            guard let content else { continue }
            texts += [content.title, content.outcome] + content.readings.map(\.label) + content.readings.map(\.text)
            texts += content.readings.compactMap(\.provenance) + content.about.map(\.label) + content.about.map(\.value)
            if case .verified(let paragraphs) = content.rules { texts += paragraphs }
            if let result = content.result { texts += [result.words] + [result.provenance].compactMap { $0 } }
        }
        if case .recorded(let shown)? = Originals.recorded(catalogue: catalogue, selection: originals.selection,
                                                          context: originals.recorded, hasCallback: true) {
            texts += [Originals.spoken(shown), shown.availability] + [Originals.resultSpoken(shown), shown.movement].compactMap { $0 }
            if let finish = shown.finish { texts += [finish.label, finish.words, finish.spoken] }
            texts += historyText(shown.history)
        }
        return texts
    }

    /// Every string a reader can reach on this page in its phase — heading,
    /// facts, anchor (page and full size), context, cards (page and full
    /// size read the same inputs), stream, Info, sources, originals, Details —
    /// through the shared models the views draw from.
    private static func reachable(_ input: WeatherEventPageInput10868,
                                  originals: WeatherEventPageOriginals10868?) -> [String] {
        let model = WeatherEventPageModel10868(input)
        let header = input.header
        var texts = [header.title, header.place, header.date, header.infoLabel]
        texts += [header.status, header.selectedMeaning, header.infoHint, input.notice].compactMap { $0 }
        texts += [input.reader.title] + [input.reader.state].compactMap { $0 }
        if let station = model.station {
            texts += [station.label, station.value] + [station.detail, station.note].compactMap { $0 }
            texts.append(WeatherEventPageFactsPresentation10868.spoken(label: station.label, value: station.value,
                                                                       lines: [station.detail, station.note]))
        }
        if let result = model.result {
            texts += [result.label, result.words] + [result.detail].compactMap { $0 }
            texts.append(WeatherEventPageFactsPresentation10868.spoken(label: result.label, value: result.words,
                                                                       lines: [result.detail]))
        }
        texts += historyText(input.history) + historyText(model.readerHistory)
        let context = input.copy.context
        texts += [model.contextSummary, context.label, context.chartLabel] + [context.heading, context.chartSpokenLabel].compactMap { $0 }
        if let outlook = model.outlook { texts += outlookText(FieldOutlookModel10868(outlook)) }
        if let movement = model.movement { texts += movementText(FieldMovementModel10868(movement)) }
        if let stream = input.stream {
            texts += [stream.heading] + [stream.eyebrow, stream.position, stream.status, stream.pending, stream.nextHint,
                                         stream.basis, stream.companionLabel].compactMap { $0 }
            texts += stream.cards.map(\.name)
        }
        texts += input.stories.compactMap { model.story($0.cardID)?.reason }
        texts += [input.copy.storiesLabel, input.copy.storyUnavailable, input.copy.openCardLabel, input.copy.sourceLabel,
                  input.copy.sourceUnavailable] + [input.copy.catalogueLabel].compactMap { $0 }
        if let about = model.about { texts += sectionsText(about.title, about.sections) }
        for source in input.sources where model.source(source.id) != nil { texts += sectionsText(source.title, source.sections) }
        if let originals { texts += originalsText(originals) }
        return texts
    }

    /// Facts only an owner after the day could know: the final maximum, the
    /// resolved range, every grade and settlement word, end-of-day words and any
    /// Oct 16 afternoon or evening sample.
    private static let finalFacts = ["75.2", "Captured station high", "306 NWS", "Resolved", "resolved", "winner flag",
                                     "Last recorded Oct 16", "end of Oct 16", "Recorded through", "end of the observation day",
                                     "Oct 17", "adjudicate"]
    private static let afternoonClock = "Oct 16, [0-9]{1,2}:[0-9]{2}(:[0-9]{2})? PM"
    /// Facts only an owner during or after the day could know: any station
    /// measurement, any later reading or the noon snapshot, and any Oct 16 sample.
    private static let laterFacts = ["Captured high so far", "66.2", "station observations", "Recorded chance",
                                     "Captured by noon", "By noon", "noon in New York"]
    private static let dayClock = "Oct 16, [0-9]{1,2}:[0-9]{2}"

    private static func carries(_ text: String, _ words: [String], clock: String) -> Bool {
        words.contains { text.contains($0) }
            || text.range(of: clock, options: .regularExpression) != nil
            || text.range(of: #"\b(Won|Lost)\b"#, options: .regularExpression) != nil
    }

    private static func leaks(_ texts: [String], phase: WeatherEventPagePhase10868) -> [String] {
        switch phase {
        case .before: texts.filter { carries($0, finalFacts + laterFacts, clock: dayClock) }
        case .during: texts.filter { carries($0, finalFacts, clock: afternoonClock) }
        case .final: []
        }
    }

    private static func activation(_ stream: Stream, _ id: String, log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = Stream.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log("stream-hold:\(card?.id ?? "-")") } else { log("other") }
        }
    }

    /// Every archived gap one series' drawn lines join, through the shared geometry, named
    /// "earlier→later" by the series' own point ids. Empty when every gap stays open.
    private static func joinedGaps(_ series: FieldHistorySeries10868, in history: FieldHistoryInput10868,
                                   id: (Int) -> String) -> [String] {
        let drawn = FieldHistoryGeometry10868.lines(series, in: history)
        return archivedGaps.compactMap { gap -> String? in
            let earlier = id(gap.before)
            let later = id(gap.after)
            let joined = drawn.contains { line in
                zip(line, line.dropFirst()).contains { pair in pair.0.id == earlier && pair.1.id == later }
            }
            return joined ? "\(earlier)→\(later)" : nil
        }
    }

    /// The same history with its breaks removed: the joined-line control.
    private static func unbroken(_ input: FieldHistoryInput10868) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: input.title, caption: input.caption, series: input.series, selection: input.selection,
            domain: input.domain, ceiling: input.ceiling, yTicks: input.yTicks, xTicks: input.xTicks,
            guides: input.guides, breaks: [], readout: input.readout, markKey: input.markKey,
            comparisonExplanation: input.comparisonExplanation, notes: input.notes, summary: input.summary,
            plotHeight: input.plotHeight, unboundReadingWords: input.unboundReadingWords,
            plotUnavailableWords: input.plotUnavailableWords, windows: input.windows, scale: input.scale,
            moreOriginals: input.moreOriginals, details: input.details, expand: input.expand,
            inspect: input.inspect, previous: input.previous, next: input.next,
            inspection: input.inspection, layout: input.layout,
            probabilityLowerBound: input.probabilityLowerBound,
            probabilityRangeExplanation: input.probabilityRangeExplanation,
            selectedReadout: input.selectedReadout, inspectionRingShape: input.inspectionRingShape,
            plotAbsence: input.plotAbsence, showsKey: input.showsKey)
    }

    private static func points(_ history: FieldHistoryInput10868) -> [FieldHistoryPoint10868] {
        history.series.flatMap { $0.runs.flatMap(\.points) }
    }

    // MARK: - Phase mounts

    func testBeforeTheDayMountsTheAnchorAndOutlookOnlyWithItsOwnBeforeDayReading() {
        let input = Self.page(.before)
        let model = WeatherEventPageModel10868(input)
        XCTAssertTrue(model.isMounted(.history))
        XCTAssertEqual(model.outlook, input.outlook)
        XCTAssertNil(model.movement)
        XCTAssertNil(model.station)
        XCTAssertNil(model.result)
        XCTAssertEqual(input.stream?.cards.map(\.id), ["ranges"])
        XCTAssertEqual(model.rankedSlots, [.story(WeatherEventPageStory10868(cardID: "ranges", card: .ranges))])
        XCTAssertNotNil(WeatherEventPagePresentation10868(input: input).outlookContent())
        XCTAssertNil(WeatherEventPagePresentation10868(input: input).movementContent())

        // Only samples before the day, all hollow; no day-boundary guide yet.
        let points = Self.points(input.history)
        XCTAssertEqual(points.count, 9)
        XCTAssertTrue(points.allSatisfy { $0.x < 0 && $0.style == .hollow })
        XCTAssertEqual(input.history.guides, [])
        XCTAssertEqual(input.history.layout, .focused)

        // The focused readout: one dated before-day reading for the selected range.
        guard case .original(let series, let slots) = model.selectedSummary else { return XCTFail("the selected range leads") }
        XCTAssertEqual(series.name, "74-75°F · Yes")
        XCTAssertEqual(series.shape, .circle)
        XCTAssertEqual(slots, [FieldHistoryReadoutSlot10868(
            label: "Last before Oct 16", display: .figure("42.5%", provenance: "Oct 15, 11:00:24 PM ET · last sample before Oct 16"))])

        // The outlook's selected reading is its before-day one; no result before the final.
        let outlook = FieldOutlookModel10868(model.outlook!)
        XCTAssertEqual(outlook.selectedReading, Self.beforeReading(Self.row("5680548")))
        XCTAssertNil(outlook.resultLine)
    }

    func testDuringTheDayMountsBothCardsTheCapturedHighSoFarAndTheRecordedChance() {
        let input = Self.page(.during)
        let model = WeatherEventPageModel10868(input)
        XCTAssertEqual(model.outlook, input.outlook)
        XCTAssertEqual(model.movement, input.movement)
        XCTAssertTrue(FieldMovementModel10868(model.movement!).isShown)
        XCTAssertEqual(model.station?.label, "Captured high so far")
        XCTAssertEqual(model.station?.value, "66.2°F")
        XCTAssertNil(model.result)
        XCTAssertEqual(model.rankedSlots.count, 2)

        // Samples through noon only; the owner's day-boundary guide.
        let points = Self.points(input.history)
        XCTAssertTrue(points.allSatisfy { $0.x <= 12 })
        XCTAssertEqual(points.filter { $0.style == .filled }.count, 4 * 3)
        XCTAssertEqual(input.history.guides.map(\.x), [0])

        // Before-day reference and the recorded chance, each with its own date.
        guard case .original(_, let slots) = model.selectedSummary else { return XCTFail("the selected range leads") }
        XCTAssertEqual(slots, [
            FieldHistoryReadoutSlot10868(label: "Last before Oct 16",
                                         display: .figure("42.5%", provenance: "Oct 15, 11:00:24 PM ET · last sample before Oct 16")),
            FieldHistoryReadoutSlot10868(label: "Recorded chance",
                                         display: .figure("39.5%", provenance: "Oct 16, 11:00:28 AM ET · Polymarket sample")),
        ])
        XCTAssertTrue(input.history.notes.contains("Current probability unavailable · a recorded sample is not a verified trade close"))
    }

    func testAfterTheDayMountsBothCardsTheResolvedRangeAndTheCapturedStationHighApart() {
        let input = Self.page(.final)
        let model = WeatherEventPageModel10868(input)
        XCTAssertEqual(model.result, Self.finalResult)
        XCTAssertEqual(model.station?.label, "Captured station high")
        XCTAssertEqual(model.station?.value, "75.2°F")
        XCTAssertNotEqual(model.result?.words, model.station?.value)
        XCTAssertNotNil(model.outlook)
        XCTAssertNotNil(model.movement)

        // The outlook's selected original's own result, at the final only.
        XCTAssertEqual(FieldOutlookModel10868(model.outlook!).resultLine,
                       .result(FieldChooserResult10868(title: "Original Yes", words: "Resolved Yes")))
        // The history stops at the day's end: no post-day sample, no result point.
        let points = Self.points(input.history)
        XCTAssertTrue(points.allSatisfy { $0.x <= 24 })
        XCTAssertFalse(points.contains { $0.probability == 1 })
        XCTAssertFalse(points.contains { $0.id == Self.pointID("5680548", 13) })
        guard case .original(_, let slots) = model.selectedSummary else { return XCTFail("the selected range leads") }
        XCTAssertEqual(slots.map(\.label), ["Last before Oct 16", "Last recorded Oct 16"])
        XCTAssertEqual(slots[1].display, .figure(">99.9%", provenance: "Oct 16, 11:00:23 PM ET · Polymarket sample"))
    }

    // MARK: - No later or final leak

    func testEveryReachableBeforeAndLiveTextCarriesNoLaterOrFinalFactWithAFinalPositiveControl() {
        // Positive controls: the scan sees what each later owner adds.
        let finalTexts = Self.reachable(Self.page(.final), originals: Self.originals(.final))
        XCTAssertFalse(Self.leaks(finalTexts, phase: .during).isEmpty)
        for fact in ["75.2°F", "Captured station high", "Resolved range", "Won"] {
            XCTAssertTrue(finalTexts.contains { $0.contains(fact) }, fact)
        }
        XCTAssertTrue(finalTexts.contains { $0.range(of: Self.afternoonClock, options: .regularExpression) != nil })
        let duringTexts = Self.reachable(Self.page(.during), originals: Self.originals(.during))
        XCTAssertFalse(Self.leaks(duringTexts, phase: .before).isEmpty)
        XCTAssertTrue(duringTexts.contains("Captured high so far"))

        // Before and during: every reachable line, page and full size, plus inspected states.
        for phase in [WeatherEventPagePhase10868.before, .during] {
            let inspections: [Inspect?] = phase == .before ? [nil, .same, .earlier] : [nil, .same, .earlier, .during]
            for inspect in inspections {
                let texts = Self.reachable(Self.page(phase, inspect: inspect), originals: Self.originals(phase))
                XCTAssertEqual(Self.leaks(texts, phase: phase), [], "\(phase.rawValue) \(String(describing: inspect))")
            }
            // Info and source are phase-appropriate owner text, verbatim.
            let model = WeatherEventPageModel10868(Self.page(phase))
            XCTAssertEqual(model.about, Self.about(phase))
            XCTAssertFalse(model.about!.sections.contains { $0.title == "Resolved range and station measurements" })
            XCTAssertEqual(model.source(Self.rulesSourceID)?.sections.map(\.title), ["Original rules", "Identity"])
            // Nothing after the phase's own cut is drawn, in the page or full size.
            let limit: Double = phase == .before ? 0 : 12
            XCTAssertTrue(Self.points(model.readerHistory).allSatisfy { $0.x <= limit })
        }
    }

    func testARejectedLaterOrFinalControlNeverMounts() {
        // An owner that wrongly supplies later or final channels early: the phase gates hide them.
        var before = Self.parts(.before)
        before.station = Self.station(.final)
        before.result = Self.finalResult
        before.movement = Self.movement(.during)
        let beforeModel = WeatherEventPageModel10868(before.input)
        XCTAssertNil(beforeModel.station)
        XCTAssertNil(beforeModel.result)
        XCTAssertNil(beforeModel.movement)
        XCTAssertFalse(beforeModel.isMounted(.movement))
        XCTAssertNil(beforeModel.story("movement"))

        var during = Self.parts(.during)
        during.result = Self.finalResult
        XCTAssertNil(WeatherEventPageModel10868(during.input).result)

        // A card input from another phase is not mounted.
        var mismatched = Self.parts(.final)
        mismatched.outlook = Self.outlook(.during)
        mismatched.movement = Self.movement(.during)
        let model = WeatherEventPageModel10868(mismatched.input)
        XCTAssertNil(model.outlook)
        XCTAssertNil(model.movement)
        XCTAssertEqual(model.rankedSlots, [.unavailable("ranges"), .unavailable("movement")])
        XCTAssertFalse(model.readerShows(.ranges))
    }

    // MARK: - Focused readouts

    func testTheFocusedReadoutIsTheHistorysOwnSlotsForSameEarlierDuringAndMissingObservations() {
        func slots(_ input: WeatherEventPageInput10868) -> [FieldHistoryReadoutSlot10868] {
            guard case .original(_, let slots) = FieldHistoryGeometry10868.selectedSummary(input.history) else { return [] }
            return slots
        }
        let baseline = FieldHistoryReadoutSlot10868(
            label: "Last before Oct 16", display: .figure("42.5%", provenance: "Oct 15, 11:00:24 PM ET · last sample before Oct 16"))

        // The selected reading IS the reference: one clearly dated reading.
        let same = Self.page(.during, inspect: .same)
        XCTAssertEqual(slots(same), [baseline])
        // A distinct earlier sample: inspected before the day, beside the separate reference.
        let earlier = Self.page(.during, inspect: .earlier)
        XCTAssertEqual(slots(earlier), [baseline, FieldHistoryReadoutSlot10868(
            label: "Inspected before Oct 16", display: .figure("40.5%", provenance: "Oct 15, 10:00:21 PM ET · Polymarket sample"))])
        // A sample during the day.
        let during = Self.page(.during, inspect: .during)
        XCTAssertEqual(slots(during), [baseline, FieldHistoryReadoutSlot10868(
            label: "Recorded chance", display: .figure("48.5%", provenance: "Oct 16, 10:00:35 AM ET · Polymarket sample"))])
        // No sample at the inspected time: the owner's words, never a neighbour.
        let missing = Self.page(.final, inspect: .missing)
        XCTAssertEqual(slots(missing), [baseline, FieldHistoryReadoutSlot10868(label: "Selected time", display: .words("Not recorded at this time"))])
        XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(missing.history.series[0], in: missing.history))

        // The compact context reads exactly those slots.
        for input in [same, earlier, during, missing] {
            let model = WeatherEventPageModel10868(input)
            XCTAssertEqual(model.selectedSummary, FieldHistoryGeometry10868.selectedSummary(input.history))
            XCTAssertTrue(model.contextSummary.hasPrefix(input.copy.context.heading!))
            for slot in slots(input) {
                XCTAssertTrue(model.contextSummary.contains(FieldHistoryGeometry10868.spokenSlot(slot)))
            }
        }
    }

    // MARK: - Independent originals and exact card inputs

    func testIndependentYesAndNoOriginalsAndRangesAreNeverNormalized() {
        let outlook = FieldOutlookModel10868(Self.outlook(.before))
        let yes = Self.rows.filter { $0.side == "Yes" }.map(\.before)
        XCTAssertEqual(yes.reduce(0, +), 1.0205, accuracy: 1e-9)
        XCTAssertEqual(outlook.input.chances.count, 22)

        // 76–77°F No has its own noon sample, not 1 − Yes.
        let no = FieldMovementModel10868(Self.movement(.during, displayed: [("5680549", "No", "76-77° No")]))
        XCTAssertEqual(no.rows.count, 1)
        XCTAssertEqual(no.rowSummary(no.rows[0]),
                       "Last before Oct 16: 75%, Oct 15, 11:00:39 PM ET · Polymarket sample. Captured by noon: 80.8%, Oct 16, 11:00:43 AM ET · Polymarket sample. +5.8 pp")
        XCTAssertNotEqual(Self.row("5680549", "No").noon, 1 - Self.row("5680549").noon, accuracy: 1e-9)
        if case .value(let change, _) = no.rows[0].change {
            XCTAssertEqual(change, 0.058, accuracy: 1e-9)
        } else {
            XCTFail("the No original places its own change")
        }
    }

    func testTheExactFiveOverviewAndThreeNoonInputsAndTheNoonCardIsUnchangedAtTheFinal() {
        let outlook = FieldOutlookModel10868(Self.outlook(.final))
        XCTAssertEqual(outlook.bars.map(\.slot.label), ["70-71°F", "72-73°F", "74-75°F", "76-77°F", "78-79°F"])
        XCTAssertEqual(outlook.bars.map { bar -> Double? in
            if case .value(let probability, _) = bar.chance { return probability }
            return nil
        }, [0.0555, 0.23, 0.425, 0.25, 0.0495])
        XCTAssertEqual(outlook.bars.compactMap(\.chance.fraction), [0.111, 0.46, 0.85, 0.5, 0.099])
        XCTAssertEqual(outlook.bars.filter(outlook.isSelected).map(\.slot.label), ["74-75°F"])

        let during = Self.movement(.during)
        let final = Self.movement(.final)
        let noon = FieldMovementModel10868(during)
        XCTAssertEqual(noon.rows.map(\.slot.label), ["72-73°F", "76-77°F", "70-71°F"])
        XCTAssertEqual(noon.rows.map { noon.movementWords($0) }, ["+11.5 pp", "-10.1 pp", "+3.8 pp"])
        let changes = noon.rows.compactMap { row -> Double? in
            if case .value(let change, _) = row.change { return change }
            return nil
        }
        XCTAssertEqual(changes.count, 3)
        for (change, expected) in zip(changes, [0.115, -0.101, 0.0375]) {
            XCTAssertEqual(change, expected, accuracy: 1e-9)
        }
        // The final card keeps the noon comparison: only the phase differs.
        let rebuilt = FieldMovementInput10868(scope: final.scope, catalogue: final.catalogue, displayed: final.displayed,
                                              pairs: final.pairs, scale: final.scale, phase: .during, copy: final.copy,
                                              unavailableWords: final.unavailableWords)
        XCTAssertEqual(rebuilt, during)
        XCTAssertEqual(FieldMovementModel10868(final).rows, noon.rows)
        XCTAssertEqual(WeatherEventPageModel10868(Self.page(.final)).movement, final)
    }

    func testNoFuturePointNoFabricatedEndpointAndTheOwnersGapsAreKept() {
        for phase in WeatherEventPagePhase10868.allCases {
            let history = Self.history(phase)
            let lines = history.series.map { series in
                FieldHistoryGeometry10868.lines(series, in: history).map { $0.count }
            }
            switch phase {
            case .before:
                // 8 PM | break | 10 PM → 11 PM.
                XCTAssertEqual(lines, Array(repeating: [2], count: 3))
            case .during:
                XCTAssertEqual(lines, Array(repeating: [4, 2], count: 3))
            case .final:
                // 12 → 1 PM | break | 3 → 4 PM; 10 → 11 PM; nothing after the day.
                XCTAssertEqual(lines, Array(repeating: [4, 2, 2, 2, 2], count: 3))
            }
            // Every drawn point is an archived sample: nothing added, no 0%/100% end.
            let archived = Set(Self.samples.flatMap { market, list in list.map { "\(market).yes.\($0.t)" } })
            XCTAssertTrue(Self.points(history).allSatisfy { archived.contains($0.id) }, phase.rawValue)
            XCTAssertFalse(Self.points(history).contains { $0.probability == 0 || $0.probability == 1 }, phase.rawValue)
            // No cohort line crosses an archived gap; without the breaks, the same check catches the joined line.
            for member in Self.cohort {
                let series = history.series.first { $0.id == Self.row(member.market).outcome }!
                XCTAssertEqual(Self.joinedGaps(series, in: history) { Self.pointID(member.market, $0) }, [], phase.rawValue)
                XCTAssertFalse(Self.joinedGaps(series, in: Self.unbroken(history)) { Self.pointID(member.market, $0) }.isEmpty,
                               phase.rawValue)
            }
        }

        // The original's Details chart: the history `Originals.recorded` actually shows, through the
        // shared geometry. Every retained sample stays a mark; no line crosses an archived gap.
        for phase in WeatherEventPagePhase10868.allCases {
            let originals = Self.originals(phase)
            guard case .recorded(let shown)? = Originals.recorded(catalogue: originals.catalogue, selection: originals.selection,
                                                                  context: originals.recorded, hasCallback: true),
                  let series = shown.history.series.first else {
                XCTFail("the held original shows its recorded history (\(phase.rawValue))")
                continue
            }
            func sampleID(_ index: Int) -> String { "original.\(Self.sample("5680548", index).t)" }
            let retained: [Int] = phase == .before ? [0, 1, 2] : phase == .during ? Array(0...6) : Array(0...12)
            let expected: [[Int]]
            switch phase {
            case .before:
                // 8 PM alone | break | 10 → 11 PM.
                expected = [[1, 2]]
            case .during:
                expected = [[1, 2, 3, 4], [5, 6]]
            case .final:
                // … 12 → 1 PM | break | 3 → 4 PM; 10 → 11 PM.
                expected = [[1, 2, 3, 4], [5, 6], [7, 8], [9, 10], [11, 12]]
            }
            XCTAssertEqual(FieldHistoryGeometry10868.marks(series, in: shown.history).map(\.id), retained.map(sampleID),
                           phase.rawValue)
            XCTAssertEqual(FieldHistoryGeometry10868.lines(series, in: shown.history).map { $0.map(\.id) },
                           expected.map { $0.map(sampleID) }, phase.rawValue)
            XCTAssertEqual(Self.joinedGaps(series, in: shown.history, id: sampleID), [], phase.rawValue)

            // Positive control: the same shown history without its breaks draws the joined line, and the
            // check names exactly the gaps it crosses.
            let joined = Self.unbroken(shown.history)
            let evening = "\(sampleID(0))→\(sampleID(1))"
            let afternoon = "\(sampleID(8))→\(sampleID(9))"
            XCTAssertEqual(Self.joinedGaps(joined.series[0], in: joined, id: sampleID),
                           phase == .final ? [evening, afternoon] : [evening], phase.rawValue)
            let joinedLines = FieldHistoryGeometry10868.lines(joined.series[0], in: joined)
            XCTAssertEqual(joinedLines.first.map { Array($0.prefix(2).map(\.id)) }, [sampleID(0), sampleID(1)], phase.rawValue)
        }
    }

    func testTheStationMeasurementAndTheResultStayIndependentWhileAnEarlierChanceIsInspected() {
        let inputs = [Self.page(.final), Self.page(.final, inspect: .earlier), Self.page(.final, inspect: .missing)]
        let models = inputs.map { WeatherEventPageModel10868($0) }
        for model in models {
            XCTAssertEqual(model.station, models[0].station)
            XCTAssertEqual(model.result, models[0].result)
            XCTAssertEqual(model.outlook, models[0].outlook)
            XCTAssertEqual(model.movement, models[0].movement)
        }
        XCTAssertNotEqual(models[0].selectedSummary, models[1].selectedSummary)
        // A station measurement is never a point or a chance.
        XCTAssertFalse(Self.points(inputs[0].history).contains { abs($0.probability - 0.752) < 1e-9 || abs($0.probability - 0.662) < 1e-9 })
        XCTAssertEqual(WeatherEventPageModel10868(Self.page(.during)).station?.value, "66.2°F")
        XCTAssertEqual(models[0].station?.value, "75.2°F")
        // The resolved range is the owner's settlement words, separate from the station high.
        XCTAssertEqual(models[0].result?.words, "74-75°F")
        XCTAssertNotEqual(models[0].station?.label, models[0].result?.label)
    }

    // MARK: - Withdrawal and restore

    func testAHeldOriginalAndAnInspectedSampleOmittedAndRestoredWhileTheNeighbourSurvives() {
        var log: [String] = []
        let held = Originals.Selection(scope: Self.originalsScope, identity: Self.identity("5680548", "Yes"))
        let neighbour = Originals.Selection(scope: Self.originalsScope, identity: Self.identity("5680548", "No"))
        let input = Self.page(.final, inspect: .during)
        let present = Self.originals(.final)
        let withdrawn = Self.originals(.final, omitting: ("5680548", "Yes"))
        func view(_ mode: WeatherEventPageMode10868, _ originals: WeatherEventPageOriginals10868,
                  _ input: WeatherEventPageInput10868) -> WeatherEventPagePresentation10868 {
            WeatherEventPagePresentation10868(input: input, mode: mode, originals: originals,
                                              onOriginalSelect: { log.append("select:\($0.identity.market):\($0.identity.side)") },
                                              onOriginalHistory: { log.append("history:\($0.actionID)") },
                                              onInteraction: { log.append("hold") })
        }

        // Withdrawn: the held selection stays held and resolves to nothing; no stand-in.
        let gone = view(.original, withdrawn, input).originalDetailsContent()!
        XCTAssertEqual(gone.selection, held)
        XCTAssertNil(Originals.original(in: gone.catalogue, selection: gone.selection))
        XCTAssertNil(Originals.recorded(catalogue: gone.catalogue, selection: gone.selection, context: gone.recorded, hasCallback: true))
        let catalogue = view(.catalogue, withdrawn, input).catalogueContent()!
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                      labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)
        XCTAssertEqual(cards.count, 21)
        XCTAssertFalse(cards.contains { $0.choice.isSelected })
        let neighbourCard = cards.first { $0.choice.selection == neighbour }!
        OriginalMarketCatalogue9483.action(neighbourCard, onSelect: catalogue.onSelect)?()
        XCTAssertEqual(log, ["hold", "select:5680548:No"])

        // The outlook's held range withdrawn: its own words, neighbours keep their bars.
        let thinner = Self.rows.filter { !($0.market == "5680548" && $0.side == "Yes") }.map { Self.outlookRecord($0, phase: .final) }
        let outlookGone = FieldOutlookModel10868(Self.outlook(.final, catalogue: thinner))
        XCTAssertEqual(outlookGone.notice, "Your range is unavailable in this update.")
        XCTAssertNil(outlookGone.selectedOriginal)
        XCTAssertEqual(outlookGone.bars.map { $0.resolution.original != nil }, [true, true, false, true, true])
        XCTAssertNil(outlookGone.resultLine)

        // The history's selected range withdrawn: the owner's words, never a neighbour.
        var historyGone = Self.parts(.final, inspect: .during)
        historyGone.history = Self.history(.final, inspect: .during, withoutSelected: true)
        XCTAssertEqual(WeatherEventPageModel10868(historyGone.input).selectedSummary, .words("Your range is not in this history"))
        XCTAssertTrue(WeatherEventPageModel10868(historyGone.input).contextSummary.contains("Your range is not in this history"))

        // The inspected sample withdrawn: unbound words, not a neighbour's figure.
        let sampleGone = WeatherEventPageModel10868(Self.page(.final, inspect: .omittedSample))
        guard case .original(_, let goneSlots) = sampleGone.selectedSummary else { return XCTFail("the range itself stays") }
        XCTAssertEqual(goneSlots.last, FieldHistoryReadoutSlot10868(label: "Recorded chance", display: .words("Unavailable")))

        // Restored: every one resolves again by its exact identity, page and full size alike.
        log = []
        let back = view(.original, present, input).originalDetailsContent()!
        XCTAssertEqual(Originals.original(in: back.catalogue, selection: back.selection)?.identity, held.identity)
        guard case .recorded(let shown)? = Originals.recorded(catalogue: back.catalogue, selection: back.selection,
                                                              context: back.recorded, hasCallback: true),
              let intent = Originals.intent(.explore, in: shown) else {
            return XCTFail("the restored original resolves its recorded Details")
        }
        back.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "history:original.explore"])
        XCTAssertEqual(FieldOutlookModel10868(Self.outlook(.final)).selectedOriginal?.ref, Self.ref("5680548"))
        let restored = WeatherEventPageModel10868(input)
        guard case .original(let series, let slots) = restored.selectedSummary else { return XCTFail("restored") }
        XCTAssertEqual(series.id, Self.row("5680548").outcome)
        XCTAssertEqual(slots.last?.display, .figure("48.5%", provenance: "Oct 16, 10:00:35 AM ET · Polymarket sample"))
        let reader = view(.reader(.history), present, input).historyContent(reader: true).input
        XCTAssertEqual(reader.inspection, input.history.inspection)
        XCTAssertEqual(reader.selectedReadout, input.history.selectedReadout)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(reader), restored.selectedSummary)
    }

    // MARK: - Full size

    func testFullSizeReadersUseTheSameInputsAndKeepTheFocusedComparison() {
        let input = Self.page(.during, inspect: .earlier)
        let page = input.history
        let reader = WeatherEventPagePresentation10868(input: input, mode: .reader(.history)).historyContent(reader: true).input
        XCTAssertNotNil(page.expand)
        XCTAssertNil(reader.expand)
        XCTAssertEqual(reader.layout, .focused)
        let rebuilt = FieldHistoryInput10868(
            title: reader.title, caption: reader.caption, series: reader.series, selection: reader.selection,
            domain: reader.domain, ceiling: reader.ceiling, yTicks: reader.yTicks, xTicks: reader.xTicks,
            guides: reader.guides, breaks: reader.breaks, readout: reader.readout, markKey: reader.markKey,
            comparisonExplanation: reader.comparisonExplanation, notes: reader.notes, summary: reader.summary,
            plotHeight: reader.plotHeight, unboundReadingWords: reader.unboundReadingWords,
            plotUnavailableWords: reader.plotUnavailableWords, windows: reader.windows, scale: reader.scale,
            moreOriginals: reader.moreOriginals, details: reader.details, expand: page.expand,
            inspect: reader.inspect, previous: reader.previous, next: reader.next,
            inspection: reader.inspection, layout: reader.layout,
            probabilityLowerBound: reader.probabilityLowerBound,
            probabilityRangeExplanation: reader.probabilityRangeExplanation,
            selectedReadout: reader.selectedReadout, inspectionRingShape: reader.inspectionRingShape,
            plotAbsence: reader.plotAbsence, showsKey: reader.showsKey)
        XCTAssertEqual(rebuilt, page)
        XCTAssertEqual(FieldHistoryGeometry10868.selectedSummary(reader), FieldHistoryGeometry10868.selectedSummary(page))

        for card in [WeatherEventPageCard10868.ranges, .movement] {
            let view = WeatherEventPagePresentation10868(input: input, mode: .reader(card))
            XCTAssertTrue(view.model.readerShows(card))
        }
        XCTAssertEqual(WeatherEventPagePresentation10868(input: input, mode: .reader(.ranges)).outlookContent(reader: true)?.input,
                       WeatherEventPagePresentation10868(input: input).outlookContent()?.input)
        XCTAssertEqual(WeatherEventPagePresentation10868(input: input, mode: .reader(.movement)).movementContent(reader: true)?.input,
                       input.movement)
        XCTAssertFalse(WeatherEventPageModel10868(Self.page(.before)).readerShows(.movement))
    }

    // MARK: - Holds

    func testEachActionHoldsOnceAndReachesItsExactPayloadWhileReadersStreamsAndPassiveReadsDoNot() {
        var log: [String] = []
        let input = Self.page(.during)
        let originals = Self.originals(.during)
        func view(_ mode: WeatherEventPageMode10868 = .page, hook: Bool = true) -> WeatherEventPagePresentation10868 {
            WeatherEventPagePresentation10868(
                input: input, mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onSource: { log.append("source:\($0)") },
                onLink: { log.append("link:\($0.id)") },
                onCatalogue: { log.append("catalogue") },
                onOriginalSelect: { log.append("select:\($0.identity.market):\($0.identity.side)") },
                onOriginalHistory: { log.append("history:\($0.actionID)") },
                onHistoryAction: { log.append("chart:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onRangeChoose: { log.append("choose:\($0.marketID)") },
                onRangeOpen: { log.append("open:\($0.marketID)") },
                onMovementOpen: { log.append("movement:\($0.ref.marketID):\($0.observation ?? "none")") },
                onStoryIntent: { _ in log.append("stream") },
                onReaderOpen: { log.append("reader:\($0.rawValue)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf and mode calls nothing.
        let page = view()
        let anchor = page.historyContent(reader: false)
        let outlook = page.outlookContent()!
        let movement = page.movementContent()!
        let context = page.contextContent()
        let catalogue = view(.catalogue).catalogueContent()!
        let details = view(.original).originalDetailsContent()!
        _ = view(.about).aboutContent()
        _ = view(.source(Self.rulesSourceID)).sourceContent(Self.rulesSourceID)
        _ = view(.reader(.history)).historyContent(reader: true)
        _ = view(.reader(.ranges)).outlookContent(reader: true)
        _ = page.model.contextSummary
        _ = page.infoAction
        _ = page.catalogueAction
        _ = page.openCardAction(.movement)
        XCTAssertEqual(log, [])

        // Each page action: the hook once, then the exact payload. The cards'
        // payloads are their own models' actions.
        let outlookModel = FieldOutlookModel10868(outlook.input)
        let movementModel = FieldMovementModel10868(movement.input)
        page.infoAction?()
        anchor.onAction?("history.previous")
        anchor.onAction?("history.original")
        anchor.onPlotPosition?(10)
        context.onChart?()
        outlookModel.stepAction(.next, canChoose: true)?.perform(onChoose: outlook.onChoose, onControl: nil)
        if let ref = outlookModel.detailsRef(canOpen: true) { outlook.onOpenOriginal?(ref) }
        if let open = movementModel.openAction(movementModel.rows[0], canOpen: true) { movement.onOpen?(open) }
        page.openCardAction(.movement)?()
        page.catalogueAction?()
        XCTAssertEqual(log, ["hold", "about", "hold", "chart:history.previous", "hold", "chart:history.original",
                             "hold", "plot:10.0", "hold", "chart:history.expand", "hold", "choose:5680549",
                             "hold", "open:5680548", "hold", "movement:5680547:constructed-observation:5680547:Yes:noon",
                             "hold", "reader:movement", "hold", "catalogue"])

        // A card inside the stream: the stream's activation, never the page hook as well.
        log = []
        let ranges = Self.activation(input.stream!, "ranges") { log.append($0) }
        let inStream = page.outlookContent(activation: ranges)!
        FieldOutlookModel10868(inStream.input).stepAction(.previous, canChoose: true)?.perform(onChoose: inStream.onChoose, onControl: nil)
        XCTAssertEqual(log, ["stream-hold:ranges", "choose:5680547"])

        // Catalogue and Details: the hook once, then the exact value.
        log = []
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                      labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)
        let noCard = cards.first { $0.choice.selection?.identity == Self.identity("5680549", "No") }!
        OriginalMarketCatalogue9483.action(noCard, onSelect: catalogue.onSelect)?()
        details.onHistory?(Originals.HistoryIntent(selection: originals.selection!, entry: .explore, actionID: "original.explore"))
        XCTAssertEqual(log, ["hold", "select:5680549:No", "hold", "history:original.explore"])

        // Already-held full-size content keeps the exact callbacks: no second hold.
        log = []
        view(.reader(.history)).historyContent(reader: true).onAction?("history.next")
        let readerOutlook = view(.reader(.ranges)).outlookContent(reader: true)!
        FieldOutlookModel10868(readerOutlook.input).stepAction(.next, canChoose: true)?.perform(onChoose: readerOutlook.onChoose, onControl: nil)
        let readerMovement = view(.reader(.movement)).movementContent(reader: true)!
        if let open = movementModel.openAction(movementModel.rows[1], canOpen: true) { readerMovement.onOpen?(open) }
        view(.reader(.history)).openReaderAbout()
        let about = view(.about).aboutContent()!
        about.linkAction(Self.provider)?()
        about.sourceAction(Self.rulesSourceID)?()
        view(.source(Self.rulesSourceID)).sourceContent(Self.rulesSourceID)?.linkAction(Self.provider)?()
        XCTAssertEqual(log, ["chart:history.next", "choose:5680549", "movement:5680549:constructed-observation:5680549:Yes:noon",
                             "about", "link:provider", "source:rules.5680548", "link:provider"])

        // No hook: every page action is the owner's own.
        log = []
        let plain = view(hook: false)
        plain.contextContent().onChart?()
        plain.infoAction?()
        XCTAssertEqual(log, ["chart:history.expand", "about"])
    }

    func testAbsentCallbacksDrawNoEnabledControlAndUnresolvedTargetsStayWords() {
        var log: [String] = []
        let input = Self.page(.during)
        let bare = WeatherEventPagePresentation10868(input: input, originals: Self.originals(.during),
                                                     onInteraction: { log.append("hold") })
        XCTAssertNil(bare.infoAction)
        XCTAssertNil(bare.historyContent(reader: false).onAction)
        XCTAssertNil(bare.contextContent().onChart)
        XCTAssertNil(bare.outlookContent()?.onChoose)
        XCTAssertNil(bare.outlookContent()?.onOpenOriginal)
        XCTAssertNil(bare.movementContent()?.onOpen)
        XCTAssertNil(bare.openCardAction(.ranges))
        XCTAssertNil(bare.catalogueAction)
        XCTAssertNil(bare.catalogueContent()?.onSelect)
        XCTAssertNil(bare.originalDetailsContent()?.onHistory)
        XCTAssertNil(bare.aboutContent()?.linkAction(Self.provider))
        XCTAssertNil(bare.aboutContent()?.sourceAction(Self.rulesSourceID))
        bare.openReaderAbout()
        XCTAssertEqual(log, [])

        // A source id that names no single document is words, never a control.
        let model = WeatherEventPageModel10868(input)
        XCTAssertNil(model.source("rules.unknown"))
        XCTAssertNil(model.source(" "))
        var doubled = Self.parts(.during)
        doubled.sources += Self.sources(.during)
        XCTAssertNil(WeatherEventPageModel10868(doubled.input).source(Self.rulesSourceID))
        XCTAssertEqual(WeatherEventPageModel10868(doubled.input).sourceIDs, [])
        let wired = WeatherEventPagePresentation10868(input: doubled.input, onSource: { log.append("source:\($0)") })
        XCTAssertNil(wired.aboutContent()?.sourceAction(Self.rulesSourceID))
        XCTAssertNil(wired.sourceContent(Self.rulesSourceID))

        // Chart only for the history's own live, available expand; Info only in readers.
        XCTAssertEqual(model.contextChartID(canOpen: true), "history.expand")
        XCTAssertNil(model.contextChartID(canOpen: false))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.ranges), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .about, canOpen: true))
        XCTAssertFalse(model.catalogueAvailable(canOpen: true, hasOriginals: false))
        XCTAssertEqual(log, [])
    }

    // MARK: - Originals

    func testAll22OriginalsAreReachableWithTheirOwnPredicatesRulesAndResultsAndUnknownIsNotALoss() {
        let originals = Self.originals(.final, ungraded: ("5680550", "No"))
        let catalogue = originals.catalogue!
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue, selection: originals.selection,
                                                      labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        XCTAssertEqual(cards.count, 22)
        XCTAssertTrue(cards.allSatisfy { $0.choice.isAvailable })
        XCTAssertEqual(cards.filter(\.choice.isSelected).map(\.choice.label), ["74-75°F · Yes"])
        for card in cards {
            let content = card.content!
            let selection = card.choice.selection!
            XCTAssertEqual(content.title, Self.predicates[selection.identity.market])
            XCTAssertEqual(content.outcome, selection.identity.side)
            XCTAssertEqual(content.rules, .verified(Self.rules))
        }
        func graded(_ market: String, _ side: String) -> String? {
            Originals.content(catalogue: catalogue,
                              selection: Originals.Selection(scope: Self.originalsScope, identity: Self.identity(market, side)))?.result?.words
        }
        XCTAssertEqual(graded("5680548", "Yes"), "Won")
        XCTAssertEqual(graded("5680548", "No"), "Lost")
        XCTAssertEqual(graded("5680549", "No"), "Won")
        XCTAssertEqual(graded("5680549", "Yes"), "Lost")
        // An original with no admitted grade is unknown, never a loss.
        XCTAssertEqual(graded("5680550", "No"), Originals.resultUnavailable)
        XCTAssertNotEqual(graded("5680550", "No"), "Lost")

        // The outlook keeps a selection outside its five bars and an unknown result.
        let outside = FieldOutlookModel10868(Self.outlook(.final, selected: "5680552"))
        XCTAssertEqual(outside.notice, "Your range is outside the five shown.")
        var unknown = Self.rows.map { Self.outlookRecord($0, phase: .final) }
        let index = unknown.firstIndex { $0.ref == Self.ref("5680548") }!
        unknown[index] = Self.outlookRecord(Self.row("5680548"), phase: .before)
        XCTAssertEqual(FieldOutlookModel10868(Self.outlook(.final, catalogue: unknown)).resultLine, .unknown("Result unconfirmed"))
    }

    func testRankedCardsAndStoryLinksResolveExactlyWithoutNeighbours() {
        let model = WeatherEventPageModel10868(Self.page(.during))
        XCTAssertEqual(model.rankedSlots, [.story(WeatherEventPageStory10868(cardID: "ranges", card: .ranges)),
                                           .story(WeatherEventPageStory10868(cardID: "movement", card: .movement))])
        var doubled = Self.parts(.during)
        doubled.ranked = ["movement", "ranges", "movement"]
        XCTAssertEqual(WeatherEventPageModel10868(doubled.input).rankedSlots,
                       [.unavailable("movement"), .story(WeatherEventPageStory10868(cardID: "ranges", card: .ranges)),
                        .unavailable("movement")])
        var twinLinks = Self.parts(.during)
        twinLinks.stories += [WeatherEventPageStory10868(cardID: "ranges", card: .movement)]
        XCTAssertNil(WeatherEventPageModel10868(twinLinks.input).story("ranges"))
        XCTAssertNil(model.story("history"))
        XCTAssertNil(model.story("unknown"))
    }

    // MARK: - Arrangement

    func testPhoneWideAndAccessibilityArrangements() {
        XCTAssertEqual(WeatherEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(WeatherEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(WeatherEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(WeatherEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertTrue(WeatherEventPageModel10868.showsContext(.stacked))
        XCTAssertFalse(WeatherEventPageModel10868.showsContext(.sideBySide))
        // The accepted cards' own reflow: labelled horizontal bars at accessibility sizes.
        XCTAssertEqual(FieldOutlookGeometry10868.orientations(accessibilitySize: true), [.horizontal])
        XCTAssertEqual(FieldOutlookGeometry10868.orientations(accessibilitySize: false), [.vertical, .horizontal])
        // The anchor is tall on every arrangement: the owner's plot height, unchanged at full size.
        let input = Self.page(.during)
        XCTAssertEqual(WeatherEventPageModel10868(input).readerHistory.plotHeight, input.history.plotHeight)
        XCTAssertEqual(input.history.plotHeight, 300)
    }
}
