import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the volleyball championship field page as a composition of the
/// accepted history, catalogue and Details leaves around two small Views: the
/// history-resolved readouts and the recorded-endpoint card.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition: the history's own resolved readouts, runs, gaps, scales,
/// any-hour inspection and earlier/later availability; the readouts' slots and
/// choose payloads; the presentation copy that hides only the duplicate key;
/// the endpoint card's exact binding to one point of its own series, its
/// owner change words and its payloads; plot heights; every original's
/// identity and verbatim rules; the reachable text and every hand-off payload;
/// held omission and exact restoration; the full-size readers; once-only holds;
/// and the arrangement candidates. Nothing here claims a compile, a rendered
/// fit, VoiceOver, a native runtime or a live volleyball route.
///
/// ARCHIVED, from `volleyball-capture.json` (sha256 343b5a6d…f233f898): event
/// KXNCAAWV-26, captured 2026-10-15T21:32:37.641089Z, window 1791417600000 ..
/// 1792098000000 ms; all 49 originals' tickers, venue outcome names, titles
/// (the predicates), primary rules and the shared secondary rules, verbatim;
/// the 65 qualified positive-volume hourly closes (Nebraska 48, Pittsburgh 12,
/// Wisconsin 5) as (hour end ms, cents, volume). The other 46 originals have no
/// history. Every record is active with an empty result.
///
/// CONSTRUCTED: every display string, UTC clock word (from each close's own
/// hour end), figure, label, tint, shape, scope, id, action id, point id, run,
/// heading, About sentence, the history domain (hours from the window start),
/// readout intents and held inspections, the first/last change words (checked
/// here against the retained closes), the Details words and every rejected,
/// withdrawn, omitted, foreign, future, duplicate and bad-payload case.
///
/// NO PHASE. The archive establishes no season start, sporting period, live
/// state, current chance or result, so no fixture claims one and no phase
/// cutoff is fabricated. The text guard below proves that archived chances are
/// never advertised as pre-season, current or settled values, with positive
/// bad controls; the payload guard proves every hand-off carries its own
/// original and an admitted hour, with borrowed, foreign and future controls.
@MainActor
final class VolleyballFieldEventPagePresentation10868Tests: XCTestCase {
    private typealias Tests = VolleyballFieldEventPagePresentation10868Tests
    private typealias Originals = OriginalMarketDetails9483
    private typealias Trade = (at: Int, cents: Int, volume: Double)

    private struct Team {
        let key: String
        let name: String
        let predicate: String
        let primary: String
    }

    // MARK: Retained (ARCHIVED)

    private static let eventTicker = "KXNCAAWV-26"
    private static let capturedAt = 1792099957641
    private static let windowFrom = 1791417600000
    private static let windowThrough = 1792098000000
    private static let hour = 3_600_000

    /// Verbatim, shared by all 49 originals (`rules_secondary`).
    private static let secondaryRules = "This market resolves based on the NCAA Division I women's indoor volleyball national championship for the 2026 season.\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the NCAA. All trademarks, logos, and brand names are the property of their respective owners."

    /// All 49 originals in capture order: ticker, venue outcome name, title (the
    /// predicate) and primary rules, verbatim.
    private static let teams: [Team] = [
        Team(key: "KXNCAAWV-26-NEB", name: "Nebraska", predicate: "Nebraska wins the 2026 NCAA women's volleyball championship",
             primary: "If Nebraska women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-PITT", name: "Pittsburgh", predicate: "Pittsburgh wins the 2026 NCAA women's volleyball championship",
             primary: "If Pittsburgh women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-UK", name: "Kentucky", predicate: "Kentucky wins the 2026 NCAA women's volleyball championship",
             primary: "If Kentucky women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-STAN", name: "Stanford", predicate: "Stanford wins the 2026 NCAA women's volleyball championship",
             primary: "If Stanford women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-LOU", name: "Louisville", predicate: "Louisville wins the 2026 NCAA women's volleyball championship",
             primary: "If Louisville women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-WIS", name: "Wisconsin", predicate: "Wisconsin wins the 2026 NCAA women's volleyball championship",
             primary: "If Wisconsin women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-ASU", name: "Arizona State", predicate: "Arizona State wins the 2026 NCAA women's volleyball championship",
             primary: "If Arizona State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-SMU", name: "SMU", predicate: "SMU wins the 2026 NCAA women's volleyball championship",
             primary: "If SMU women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-TEX", name: "Texas", predicate: "Texas wins the 2026 NCAA women's volleyball championship",
             primary: "If Texas women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-FLA", name: "Florida", predicate: "Florida wins the 2026 NCAA women's volleyball championship",
             primary: "If Florida women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-TCU", name: "TCU", predicate: "TCU wins the 2026 NCAA women's volleyball championship",
             primary: "If TCU women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-PSU", name: "Penn State", predicate: "Penn State wins the 2026 NCAA women's volleyball championship",
             primary: "If Penn State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-MINN", name: "Minnesota", predicate: "Minnesota wins the 2026 NCAA women's volleyball championship",
             primary: "If Minnesota women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-PUR", name: "Purdue", predicate: "Purdue wins the 2026 NCAA women's volleyball championship",
             primary: "If Purdue women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-CREI", name: "Creighton", predicate: "Creighton wins the 2026 NCAA women's volleyball championship",
             primary: "If Creighton women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-USC", name: "Southern California", predicate: "Southern California wins the 2026 NCAA women's volleyball championship",
             primary: "If Southern California women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-TENN", name: "Tennessee", predicate: "Tennessee wins the 2026 NCAA women's volleyball championship",
             primary: "If Tennessee women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-UNC", name: "North Carolina", predicate: "North Carolina wins the 2026 NCAA women's volleyball championship",
             primary: "If North Carolina women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-TAMU", name: "Texas A&M", predicate: "Texas A&M wins the 2026 NCAA women's volleyball championship",
             primary: "If Texas A&M women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-BAY", name: "Baylor", predicate: "Baylor wins the 2026 NCAA women's volleyball championship",
             primary: "If Baylor women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-IND", name: "Indiana", predicate: "Indiana wins the 2026 NCAA women's volleyball championship",
             primary: "If Indiana women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-KU", name: "Kansas", predicate: "Kansas wins the 2026 NCAA women's volleyball championship",
             primary: "If Kansas women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-COLO", name: "Colorado", predicate: "Colorado wins the 2026 NCAA women's volleyball championship",
             primary: "If Colorado women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-ORE", name: "Oregon", predicate: "Oregon wins the 2026 NCAA women's volleyball championship",
             primary: "If Oregon women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-GT", name: "Georgia Tech", predicate: "Georgia Tech wins the 2026 NCAA women's volleyball championship",
             primary: "If Georgia Tech women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-TLSA", name: "Tulsa", predicate: "Tulsa wins the 2026 NCAA women's volleyball championship",
             primary: "If Tulsa women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-UCLA", name: "UCLA", predicate: "UCLA wins the 2026 NCAA women's volleyball championship",
             primary: "If UCLA women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-FSU", name: "Florida State", predicate: "Florida State wins the 2026 NCAA women's volleyball championship",
             primary: "If Florida State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-CP", name: "Cal Poly", predicate: "Cal Poly wins the 2026 NCAA women's volleyball championship",
             primary: "If Cal Poly women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-BALL", name: "Ball State", predicate: "Ball State wins the 2026 NCAA women's volleyball championship",
             primary: "If Ball State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-MICH", name: "Michigan", predicate: "Michigan wins the 2026 NCAA women's volleyball championship",
             primary: "If Michigan women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-ISU", name: "Iowa State", predicate: "Iowa State wins the 2026 NCAA women's volleyball championship",
             primary: "If Iowa State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-MIA", name: "Miami (FL)", predicate: "Miami (FL) wins the 2026 NCAA women's volleyball championship",
             primary: "If Miami (FL) women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-UTEP", name: "UTEP", predicate: "UTEP wins the 2026 NCAA women's volleyball championship",
             primary: "If UTEP women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-USU", name: "Utah State", predicate: "Utah State wins the 2026 NCAA women's volleyball championship",
             primary: "If Utah State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-UNI", name: "Northern Iowa", predicate: "Northern Iowa wins the 2026 NCAA women's volleyball championship",
             primary: "If Northern Iowa women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-XAV", name: "Xavier", predicate: "Xavier wins the 2026 NCAA women's volleyball championship",
             primary: "If Xavier women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-RICE", name: "Rice", predicate: "Rice wins the 2026 NCAA women's volleyball championship",
             primary: "If Rice women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-WKU", name: "Western Kentucky", predicate: "Western Kentucky wins the 2026 NCAA women's volleyball championship",
             primary: "If Western Kentucky women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-KSU", name: "Kansas State", predicate: "Kansas State wins the 2026 NCAA women's volleyball championship",
             primary: "If Kansas State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-MARQ", name: "Marquette", predicate: "Marquette wins the 2026 NCAA women's volleyball championship",
             primary: "If Marquette women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-USD", name: "San Diego", predicate: "San Diego wins the 2026 NCAA women's volleyball championship",
             primary: "If San Diego women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-SDST", name: "South Dakota State", predicate: "South Dakota State wins the 2026 NCAA women's volleyball championship",
             primary: "If South Dakota State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-ARIZ", name: "Arizona", predicate: "Arizona wins the 2026 NCAA women's volleyball championship",
             primary: "If Arizona women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-NOVA", name: "Villanova", predicate: "Villanova wins the 2026 NCAA women's volleyball championship",
             primary: "If Villanova women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-UTAH", name: "Utah", predicate: "Utah wins the 2026 NCAA women's volleyball championship",
             primary: "If Utah women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-PEPP", name: "Pepperdine", predicate: "Pepperdine wins the 2026 NCAA women's volleyball championship",
             primary: "If Pepperdine women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-TXST", name: "Texas State", predicate: "Texas State wins the 2026 NCAA women's volleyball championship",
             primary: "If Texas State women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
        Team(key: "KXNCAAWV-26-USF", name: "South Florida", predicate: "South Florida wins the 2026 NCAA women's volleyball championship",
             primary: "If South Florida women's volleyball team wins the 2026 NCAA Division I women's indoor volleyball national championship in the 2026 NCAA Division I women's volleyball season, then the market resolves to Yes."),
    ]

    /// Nebraska: 48 qualified positive-volume hourly closes (hour end ms, cents, volume).
    private static let nebraskaTrades: [Trade] = [
        (1791421200000, 43, 4.5), (1791424800000, 44, 54.72), (1791432000000, 45, 17.15),
        (1791439200000, 45, 42.79), (1791468000000, 45, 0.75), (1791500400000, 45, 21.39),
        (1791543600000, 45, 44.93), (1791561600000, 45, 10.89), (1791594000000, 45, 2.1),
        (1791604800000, 45, 10.69), (1791662400000, 48, 208.46), (1791666000000, 48, 56.48),
        (1791673200000, 49, 7.88), (1791676800000, 49, 1.18), (1791680400000, 49, 21.91),
        (1791691200000, 49, 11.82), (1791694800000, 33, 104.67), (1791702000000, 42, 2.28),
        (1791709200000, 32, 10.05), (1791723600000, 42, 56.87), (1791727200000, 31, 33.77),
        (1791730800000, 41, 6.98), (1791734400000, 29, 1.18), (1791741600000, 47, 4.17),
        (1791752400000, 37, 7.62), (1791763200000, 48, 406.91), (1791766800000, 47, 12.0),
        (1791774000000, 47, 68.25), (1791777600000, 48, 140.85), (1791781200000, 47, 52.32),
        (1791792000000, 27, 50.4), (1791817200000, 42, 22.88), (1791824400000, 47, 18.77),
        (1791828000000, 43, 24.85), (1791831600000, 48, 101.63), (1791842400000, 48, 50.59),
        (1791846000000, 48, 110.55), (1791849600000, 48, 2.01), (1791853200000, 38, 48.24),
        (1791856800000, 44, 4.1), (1791864000000, 46, 10.47), (1791914400000, 40, 11.41),
        (1791921600000, 46, 210.16), (1791928800000, 48, 415.76), (1791946800000, 48, 20.1),
        (1792011600000, 49, 998.65), (1792069200000, 48, 17.11), (1792076400000, 49, 1.98),
    ]

    /// Pittsburgh: 12 qualified positive-volume hourly closes (hour end ms, cents, volume).
    private static let pittsburghTrades: [Trade] = [
        (1791417600000, 40, 11.99), (1791428400000, 40, 28.71), (1791493200000, 13, 23.58),
        (1791511200000, 40, 479.63), (1791529200000, 40, 7.19), (1791558000000, 40, 100.0),
        (1791561600000, 29, 24.49), (1791597600000, 39, 9.83), (1791662400000, 26, 2.67),
        (1791741600000, 39, 4.95), (1791777600000, 25, 7.19), (1791867600000, 25, 65.7),
    ]

    /// Wisconsin: 5 qualified positive-volume hourly closes (hour end ms, cents, volume).
    private static let wisconsinTrades: [Trade] = [
        (1791417600000, 4, 4.15), (1791496800000, 14, 35.06), (1791529200000, 14, 20.43),
        (1791763200000, 3, 35.06), (1792011600000, 3, 102.87),
    ]

    // MARK: Owner fixtures (CONSTRUCTED)

    private struct Sampled {
        let team: Team
        let trades: [Trade]
        let shape: FieldHistoryShape10868
        let tint: Color
    }

    private static func team(_ key: String) -> Team { teams.first { $0.key == key }! }

    private static let nebraska = Sampled(team: team("KXNCAAWV-26-NEB"), trades: nebraskaTrades, shape: .circle, tint: .blue)
    private static let pittsburgh = Sampled(team: team("KXNCAAWV-26-PITT"), trades: pittsburghTrades, shape: .diamond, tint: .orange)
    private static let wisconsin = Sampled(team: team("KXNCAAWV-26-WIS"), trades: wisconsinTrades, shape: .square, tint: .purple)
    private static let sampled = [nebraska, pittsburgh, wisconsin]
    private static let scope = "kalshi:KXNCAAWV-26:capture"

    /// The owner's change words, checked against the retained closes below.
    private static let changeWords = ["KXNCAAWV-26-NEB": "+6", "KXNCAAWV-26-PITT": "−15", "KXNCAAWV-26-WIS": "−1"]

    private static let clockFormatter: DateFormatter = formatter("MMM d, h:mm a")
    private static let dayFormatter: DateFormatter = formatter("MMM d")
    private static let timeFormatter: DateFormatter = formatter("h:mm a")

    private static func formatter(_ format: String) -> DateFormatter {
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "UTC")
        formatter.dateFormat = format
        return formatter
    }

    private static func date(_ at: Int) -> Date { Date(timeIntervalSince1970: Double(at) / 1000) }
    private static func clock(_ at: Int) -> String { clockFormatter.string(from: date(at)) + " UTC" }
    private static func day(_ at: Int) -> String { dayFormatter.string(from: date(at)) }
    private static func time(_ at: Int) -> String { timeFormatter.string(from: date(at)) + " UTC" }
    private static func figure(_ cents: Int) -> String { "\(cents)%" }
    private static func provenance(_ at: Int) -> String { "Hour ending \(clock(at)) · Kalshi" }
    private static func x(_ at: Int) -> Double { Double(at - windowFrom) / Double(hour) }
    private static func pointID(_ team: Sampled, _ at: Int) -> String { "\(team.team.key)@\(at)" }
    private static func trade(_ team: Sampled, _ at: Int) -> Trade? { team.trades.first { $0.at == at } }

    /// Every hour of the window, traded or not.
    private static let hours: [Int] = Array(stride(from: windowFrom, through: windowThrough, by: hour))
    /// Every hour with a trade from any sampled team.
    private static let tradeHours: [Int] = Array(Set(sampled.flatMap { $0.trades.map { $0.at } })).sorted()

    /// The owner's earlier/later targets: real traded hours only.
    private static func earlier(_ at: Int?) -> Int? {
        guard let at else { return tradeHours.last }
        return tradeHours.last { $0 < at }
    }

    private static func later(_ at: Int?) -> Int? {
        guard let at else { return nil }
        return tradeHours.first { $0 > at }
    }

    /// Runs of adjacent traded hours; a missing hour starts a new run.
    private static func runs(_ team: Sampled) -> [FieldHistoryRun10868] {
        var groups: [[Trade]] = []
        for trade in team.trades {
            if let previous = groups.last?.last, trade.at - previous.at == hour {
                groups[groups.count - 1].append(trade)
            } else {
                groups.append([trade])
            }
        }
        return groups.enumerated().map { index, group in
            FieldHistoryRun10868(id: "\(team.team.key).run.\(index)", points: group.map {
                FieldHistoryPoint10868(id: pointID(team, $0.at), x: x($0.at), probability: Double($0.cents) / 100, style: .filled)
            })
        }
    }

    private static func action(_ id: String, _ label: String, spoken: String? = nil, available: Bool = true) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: available)
    }

    private enum Moment: Equatable {
        /// Each team's own last recorded trade, independently dated.
        case lastRecorded
        /// One exact hour, traded or not.
        case hour(Int)

        var at: Int? {
            if case .hour(let at) = self { return at }
            return nil
        }
    }

    private static func caption(_ moment: Moment) -> String {
        moment.at.map { "Recorded hour · \(clock($0))" } ?? "Last recorded trades · dates differ"
    }

    /// The owner's history for one moment. `borrowLatest` is a deliberately bad
    /// owner that binds a team's latest close to another hour.
    private static func history(_ moment: Moment = .lastRecorded, fullScale: Bool = false,
                                selected: Sampled? = Tests.nebraska, teams chosen: [Sampled] = Tests.sampled,
                                keyContext: Bool = false, borrowLatest: Sampled? = nil) -> FieldHistoryInput10868 {
        var selections: [String: FieldHistorySelection10868] = [:]
        let series = chosen.map { team -> FieldHistorySeries10868 in
            let last = team.trades.last!
            let latest = FieldHistoryReading10868.observation(pointID: pointID(team, last.at), figure: figure(last.cents),
                                                              provenance: provenance(last.at))
            var recorded = FieldHistoryReading10868.absent(words: "No trade in this hour")
            if let at = moment.at {
                if team.team.key == borrowLatest?.team.key {
                    recorded = latest
                    selections[team.team.key] = .point(id: pointID(team, last.at), spoken: figure(last.cents))
                } else if let trade = Self.trade(team, at) {
                    recorded = .observation(pointID: pointID(team, at), figure: figure(trade.cents), provenance: provenance(at))
                    selections[team.team.key] = .point(id: pointID(team, at), spoken: figure(trade.cents))
                } else {
                    selections[team.team.key] = .absent(words: "No trade in this hour")
                }
            }
            var built = FieldHistorySeries10868(
                id: team.team.key, name: team.team.name, shape: team.shape, tint: team.tint, runs: runs(team),
                links: [], labelPointID: nil, before: latest, recorded: recorded,
                absentWords: "No trades in this window",
                choose: action("highlight.\(team.team.key)", "Highlight \(team.team.name)"))
            if keyContext, team.team.key == chosen.first?.team.key {
                built.keyContext = FieldHistoryKeyContext10868(label: "Sample", words: "Sampled for this history", spoken: nil)
            }
            return built
        }
        let ceiling = fullScale ? 1.0 : 0.5
        let at = moment.at
        return FieldHistoryInput10868(
            title: "Championship win chance",
            caption: caption(moment),
            series: series,
            selection: selected.map { FieldHistoryOriginalSelection10868.series(id: $0.team.key, missingWords: "This team isn’t in this history") }
                ?? FieldHistoryOriginalSelection10868.none,
            domain: FieldHistoryDomain10868(lower: 0, upper: x(windowThrough)), ceiling: ceiling,
            yTicks: zip([0, ceiling / 2, ceiling], fullScale ? ["0%", "50%", "100%"] : ["0%", "25%", "50%"])
                .map { FieldHistoryTick10868(value: $0.0, lines: [$0.1]) },
            xTicks: [windowFrom, windowFrom + 96 * hour, windowThrough].map { FieldHistoryTick10868(value: x($0), lines: [day($0)]) },
            guides: [], breaks: [],
            readout: at == nil
                ? .singleBefore(label: "Last recorded trade")
                : .beforeAndInspected(beforeLabel: "Last recorded trade", inspectedLabel: "Selected hour"),
            markKey: FieldHistoryMarkKey10868(hollow: nil, filled: "Filled: an hour’s last recorded trade"),
            comparisonExplanation: nil,
            notes: ["Lines join adjacent traded hours only; a gap means no recorded trade in that hour.",
                    "Three sampled teams · not a full-field ranking."],
            summary: "Three sampled team histories. Nebraska circles, Pittsburgh diamonds, Wisconsin squares. All trajectories are solid. No trades means a gap.",
            plotHeight: 302, unboundReadingWords: "Unavailable", plotUnavailableWords: "History unavailable",
            windows: nil,
            scale: fullScale ? action("scale.close", "Use closer scale") : action("scale.full", "Show 0–100%"),
            moreOriginals: nil, details: nil,
            expand: action("history.expand", "Expand chart", spoken: "Open the championship win history full size"),
            inspect: at == nil ? nil : action("history.latest", "Last recorded trades"),
            previous: action("hour.earlier", "‹", spoken: "Earlier hour with a trade", available: earlier(at) != nil),
            next: action("hour.later", "›", spoken: "Later hour with a trade", available: later(at) != nil),
            inspection: FieldHistoryInspection10868(
                x: at.map { x($0) }, caption: caption(moment), selections: selections,
                choices: hours.map {
                    FieldHistoryInspectionChoice10868(id: "hour.\($0)", lines: [day($0), time($0)], spoken: clock($0), isSelected: $0 == at)
                },
                choicePresentation: .slider(label: "Explore any hour"),
                note: "Selecting an hour never carries an older probability forward."),
            layout: .cohortAbove)
    }

    private static func slot(_ team: Sampled) -> VolleyballFieldEndpointSlot10868 {
        VolleyballFieldEndpointSlot10868(seriesID: team.team.key, name: team.team.name)
    }

    private static func reading(_ team: Sampled, _ endpoint: VolleyballFieldEndpoint10868, at: Int? = nil,
                                boundTo owner: Sampled? = nil) -> VolleyballFieldEndpointReading10868 {
        let trade = at.flatMap { Self.trade(team, $0) } ?? (endpoint == .first ? team.trades.first! : team.trades.last!)
        return VolleyballFieldEndpointReading10868(
            seriesID: team.team.key, endpoint: endpoint,
            reading: .observation(pointID: pointID(owner ?? team, trade.at), figure: figure(trade.cents), provenance: provenance(trade.at)))
    }

    private static let endpointCopy = VolleyballFieldEndpointsCopy10868(
        eyebrow: "RECORDED EXPECTATIONS", title: "Who gained ground?",
        intro: "First to last captured trade · three sampled teams",
        firstLabel: "Earlier", lastLabel: "Later", endpointUnavailable: "Not recorded in this capture",
        offScale: "Above this scale", graphicLabel: "Changes across the captured championship history",
        note: "Bars compare dated trades, not a continuous path. These are not pre-season or current chances.",
        openHint: "Opens the history at this trade’s hour", expandLabel: "Expand championship chance changes")

    private static func endpoints(displayed: [VolleyballFieldEndpointSlot10868]? = nil,
                                  readings: [VolleyballFieldEndpointReading10868]? = nil,
                                  copy: VolleyballFieldEndpointsCopy10868 = Tests.endpointCopy) -> VolleyballFieldEndpointsInput10868 {
        VolleyballFieldEndpointsInput10868(
            displayed: displayed ?? sampled.map(slot),
            readings: readings ?? sampled.flatMap { [reading($0, .first), reading($0, .last)] },
            changes: sampled.map {
                VolleyballFieldEndpointChange10868(seriesID: $0.team.key, figure: changeWords[$0.team.key]!, unit: "percentage points", spoken: nil)
            },
            scale: FieldOutlookScale10868(ceiling: 0.5, ticks: [FieldOutlookTick10868(probability: 0, label: "0%"),
                                                               FieldOutlookTick10868(probability: 0.5, label: "50% chance")],
                                          words: "One shared probability scale · 0–50%"),
            copy: copy,
            unavailableWords: "Team unavailable in this update")
    }

    private static let about = FieldEventPageAbout10868(title: "About these recorded chances", paragraphs: [
        "Kalshi championship-winner contracts. This archive contains 65 positive-volume hourly trade closes for Nebraska, Pittsburgh and Wisconsin, Oct 8 – Oct 15. The three were sampled for this history; they are not a full-field ranking.",
        "These are separate historical trades, not current chances or a production blend. A mark is an hour’s last trade; Nebraska uses circles, Pittsburgh diamonds and Wisconsin squares in solid trajectories. Filled marks identify recorded observations; no pre-season baseline is known here. Connecting lines require adjacent traded hours. Missing hourly trades stay blank. Selecting an hour never carries an older probability forward. The arrows jump to an hour with a trade from any sampled team; the slider explores every hour, including empty ones.",
        "The “Who gained ground?” card compares each sampled team’s first and last qualified trade in this capture. Its bar is net change on a shared probability scale, not the path between them. Dates differ by team. Percentage-point change is not relative percent growth, and the sample does not establish full-field ranking.",
        "No verified season-start baseline, score, standings, match period or projected final was supplied. Market opening and scheduled closure are not sporting start times. “Last recorded” is not “before the competition”.",
        "All 49 original team props remain available. Current probabilities stay unavailable because recent trading has not been verified.",
    ])

    private static let copy = VolleyballFieldEventPageCopy10868(
        readoutsLabel: "Sampled team readouts", aboutLabel: "About this championship history",
        aboutHint: "Opens how these recorded chances were captured", allPropsLabel: "Explore all 49 team props",
        readerUnavailable: "This card is not available in this update.")

    /// The owner's page parts; tests replace single parts for controls.
    private struct Parts {
        var header: VolleyballFieldEventPageHeader10868
        var reader: FieldEventPageReaderHeader10868
        var history: FieldHistoryInput10868
        var readerPlotHeight: CGFloat?
        var accessibilityPlotHeight: CGFloat?
        var endpoints: VolleyballFieldEndpointsInput10868?
        var about: FieldEventPageAbout10868?
        var copy: VolleyballFieldEventPageCopy10868

        var input: VolleyballFieldEventPageInput10868 {
            VolleyballFieldEventPageInput10868(
                header: header, reader: reader, history: history, readerPlotHeight: readerPlotHeight,
                accessibilityPlotHeight: accessibilityPlotHeight, endpoints: endpoints, about: about, copy: copy)
        }
    }

    private static func parts(_ moment: Moment = .lastRecorded, fullScale: Bool = false) -> Parts {
        Parts(
            header: VolleyballFieldEventPageHeader10868(title: "Women’s volleyball", subtitle: "2026 NCAA championship",
                                                        context: "Recorded history · no current chance"),
            reader: FieldEventPageReaderHeader10868(title: "NCAA women’s volleyball", state: "Recorded history · no current chance"),
            history: history(moment, fullScale: fullScale),
            readerPlotHeight: 370, accessibilityPlotHeight: 390,
            endpoints: endpoints(), about: about, copy: copy)
    }

    private static func page(_ moment: Moment = .lastRecorded, fullScale: Bool = false) -> VolleyballFieldEventPageInput10868 {
        parts(moment, fullScale: fullScale).input
    }

    // MARK: Originals

    private static func identity(_ team: Team) -> Originals.Identity {
        Originals.Identity(source: "kalshi", market: team.key, side: "Yes")
    }

    private static func original(_ team: Team) -> Originals.Original {
        let quote = sampled.first { $0.team.key == team.key }.map { sampled -> Originals.HistoricalQuote in
            let last = sampled.trades.last!
            return Originals.HistoricalQuote(text: figure(last.cents), recorded: "\(provenance(last.at)) · not a current chance")
        }
        return Originals.Original(
            identity: identity(team), title: team.predicate, outcome: team.name, mode: .pregame,
            pregame: .missing("Unavailable · no pre-event baseline captured"), later: nil, grade: nil,
            about: Originals.About(
                source: "Kalshi", rules: .verified([team.primary, secondaryRules]),
                provenance: [Originals.Row(label: "Event", value: eventTicker), Originals.Row(label: "Market", value: team.key),
                             Originals.Row(label: "Captured", value: "Oct 15, 9:32 PM UTC")],
                historicalQuote: quote),
            beforeLabel: "Pre-event chance")
    }

    private static func originals(selection: Team? = nil, omitting: String? = nil,
                                  replacing: Originals.Original? = nil) -> FieldEventPageOriginals10868 {
        var list = teams.filter { $0.key != omitting }.map(original)
        if let replacing, let index = list.firstIndex(where: { $0.identity == replacing.identity }) { list[index] = replacing }
        return FieldEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: scope, originals: list),
            selection: selection.map { Originals.Selection(scope: scope, identity: identity($0)) },
            heading: "All 49 team props",
            context: "Each prop is that team winning the championship. Current probability unavailable; original quotes are in Details.",
            emptyWords: "No team props in this update", unavailableChoice: "Team prop", tint: .blue)
    }

    // MARK: Reachable text

    private static func historyText(_ history: FieldHistoryInput10868) -> [String] {
        var texts = [history.title, history.summary, history.unboundReadingWords] + history.notes
        texts += [history.caption, history.plotUnavailableWords, history.comparisonExplanation,
                  FieldHistoryGeometry10868.selectionWords(history)].compactMap { $0 }
        if FieldHistoryGeometry10868.drawsStyle(.hollow, in: history), let words = history.markKey.hollow { texts.append(words) }
        if FieldHistoryGeometry10868.drawsStyle(.filled, in: history), let words = history.markKey.filled { texts.append(words) }
        texts += history.xTicks.flatMap(\.lines) + history.yTicks.flatMap(\.lines)
        texts.append(FieldHistoryGeometry10868.spokenValue(history))
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

    private static func readoutsText(_ readouts: VolleyballFieldReadoutsPresentation10868) -> [String] {
        [readouts.label] + readouts.entries.flatMap { entry in
            [VolleyballFieldReadoutsPresentation10868.spoken(entry)] + entry.slots.flatMap(slotText)
                + [entry.series.choose?.label, entry.series.choose?.spokenLabel].compactMap { $0 }
        }
    }

    private static func slotText(_ slot: FieldHistoryReadoutSlot10868) -> [String] {
        switch slot.display {
        case .figure(let figure, let provenance): return [slot.label, figure, provenance]
        case .words(let words): return [slot.label, words]
        }
    }

    private static func endpointsText(_ card: VolleyballFieldEndpointsPresentation10868) -> [String] {
        let model = card.model
        let copy = card.input.copy
        var texts = [copy.title, copy.graphicLabel, copy.expandLabel, card.input.scale.words]
            + [copy.eyebrow, copy.intro, copy.note, copy.openHint].compactMap { $0 }
        texts += model.ticks.map(\.label)
        for row in model.rows {
            texts.append(model.rowSummary(row))
            texts += row.sides.flatMap { [model.endpointSummary(row, $0)] + slotText($0.slot) }
            if let change = model.change(row) {
                texts += [change.figure, VolleyballFieldEndpointsModel10868.spoken(change)] + [change.unit].compactMap { $0 }
            }
            texts += [model.stateWords(row)].compactMap { $0 }
        }
        return texts
    }

    private static func originalsText(_ originals: FieldEventPageOriginals10868) -> [String] {
        guard let catalogue = originals.catalogue else { return [] }
        var texts = [originals.heading, originals.emptyWords, originals.unavailableChoice] + [originals.context].compactMap { $0 }
        let choices = OriginalMarketChooser9483.choices(catalogue: catalogue, selection: originals.selection,
                                                        labels: originals.labels, unavailableChoice: originals.unavailableChoice)
        texts += choices.map(OriginalMarketChooser9483.spoken)
        for original in catalogue.originals {
            let content = Originals.content(catalogue: catalogue,
                                            selection: Originals.Selection(scope: catalogue.scope, identity: original.identity))
            texts.append(Originals.spoken(content))
            guard let content else { continue }
            // A reading's label is drawn with its own figure or words.
            texts += [content.title, content.outcome] + content.readings.map { "\($0.label): \($0.text)" }
            texts += content.readings.compactMap(\.provenance) + content.about.map(\.label) + content.about.map(\.value)
            if case .verified(let paragraphs) = content.rules { texts += paragraphs }
            if let result = content.result { texts += [result.words] + [result.provenance].compactMap { $0 } }
        }
        return texts
    }

    /// Every string a reader can reach: header, readouts and history page and
    /// full size, the endpoint card, reader words, About and every original.
    private static func reachable(_ input: VolleyballFieldEventPageInput10868,
                                  originals: FieldEventPageOriginals10868?) -> [String] {
        let pageView = VolleyballFieldEventPagePresentation10868(input: input)
        var texts = [input.header.title, input.reader.title]
            + [input.header.subtitle, input.header.context, input.header.notice, input.reader.state].compactMap { $0 }
        texts += [input.copy.aboutLabel, input.copy.readerUnavailable] + [input.copy.aboutHint, input.copy.allPropsLabel].compactMap { $0 }
        for accessibilitySize in [false, true] {
            for reader in [false, true] {
                texts += readoutsText(pageView.readoutsContent(reader: reader, accessibilitySize: accessibilitySize))
                texts += historyText(pageView.historyContent(reader: reader, accessibilitySize: accessibilitySize).input)
            }
        }
        if let card = pageView.endpointsContent(reader: false) { texts += endpointsText(card) }
        if let about = VolleyballFieldEventPageModel10868(input).about { texts += [about.title] + about.paragraphs }
        if let originals { texts += originalsText(originals) }
        return texts
    }

    // MARK: Guards

    private static let forbiddenClaim = #"(?i)(pre-?season|season[- ]start|pregame|pre-event|before the (competition|season|tournament)|\bcurrent\b|\blive\b|\bnow\b|\bsettled\b|\bfinal\b|\bresult\b|\bwon\b|\bchampion\b)"#
    private static let negation = #"(?i)(\bnot\b|\bno\b|\bnever\b|\bunavailable\b|\bwithout\b|isn’t|isn't)"#

    private static func matches(_ text: String, _ pattern: String) -> Bool {
        text.range(of: pattern, options: .regularExpression) != nil
    }

    /// Advertising claims: a figure under a pre-season, current or settled
    /// label, or a sentence that names one without negating it.
    private static func claims(_ input: VolleyballFieldEventPageInput10868, originals: FieldEventPageOriginals10868?) -> [String] {
        var found: [String] = []
        let pageView = VolleyballFieldEventPagePresentation10868(input: input)
        var figureLabels: [String] = []
        for reader in [false, true] {
            figureLabels += pageView.readoutsContent(reader: reader, accessibilitySize: false).entries
                .flatMap(\.slots).filter { if case .figure = $0.display { return true }; return false }.map(\.label)
        }
        if let card = pageView.endpointsContent(reader: false) {
            figureLabels += card.model.rows.flatMap(\.sides).filter { $0.point != nil }.map(\.slot.label)
        }
        if let catalogue = originals?.catalogue {
            for original in catalogue.originals {
                if case .comparison(.current) = original.mode { found.append("current mode: \(original.identity.market)") }
                if original.mode == .result || original.grade != nil { found.append("settled: \(original.identity.market)") }
                let content = Originals.content(catalogue: catalogue, selection: Originals.Selection(scope: catalogue.scope, identity: original.identity))
                figureLabels += content?.readings.filter(\.isValue).map(\.label) ?? []
            }
        }
        found += figureLabels.filter { matches($0, forbiddenClaim) }.map { "figure under: \($0)" }
        for text in reachable(input, originals: originals) {
            for sentence in text.components(separatedBy: ". ") where matches(sentence, forbiddenClaim) && !matches(sentence, negation) {
                found.append("claim: \(sentence)")
            }
        }
        return found
    }

    /// A payload names its own original and a retained hour inside the window,
    /// never after the capture.
    private static func openViolations(_ open: VolleyballFieldEndpointOpen10868) -> [String] {
        guard let team = sampled.first(where: { $0.team.key == open.seriesID }) else { return ["foreign series \(open.seriesID)"] }
        guard let trade = team.trades.first(where: { pointID(team, $0.at) == open.pointID }) else {
            return ["foreign or unknown point \(open.pointID)"]
        }
        guard trade.at >= windowFrom, trade.at <= windowThrough, trade.at <= capturedAt else { return ["future point \(open.pointID)"] }
        return []
    }

    private static func payloadViolations(_ input: VolleyballFieldEventPageInput10868) -> [String] {
        var found: [String] = []
        let history = input.history
        for series in history.series where series.choose?.id != "highlight.\(series.id)" {
            found.append("choose names another series: \(series.id)")
        }
        if let inspection = history.inspection, let x = inspection.x {
            for series in history.series {
                if case .point(let id, _)? = inspection.selections[series.id],
                   FieldHistoryGeometry10868.uniquePoint(id, in: series)?.x != x {
                    found.append("borrowed: \(series.id) \(id)")
                }
            }
        }
        let pageView = VolleyballFieldEventPagePresentation10868(input: input)
        for entry in pageView.readoutsContent(reader: false, accessibilitySize: false).entries {
            guard let team = sampled.first(where: { $0.team.key == entry.series.id }) else { continue }
            for slot in entry.slots {
                guard case .figure(let figure, let provenance) = slot.display else { continue }
                if !team.trades.contains(where: { Self.figure($0.cents) == figure && Self.provenance($0.at) == provenance }) {
                    found.append("figure not its own: \(entry.series.id) \(figure)")
                }
            }
        }
        if let card = pageView.endpointsContent(reader: false) {
            for row in card.model.rows {
                for side in row.sides {
                    guard let open = card.model.openAction(row, side, canOpen: true) else { continue }
                    if open.seriesID != row.series?.id { found.append("open names another row") }
                    found += openViolations(open)
                }
            }
        }
        return found
    }

    private static func figureSlot(_ label: String, _ team: Sampled, _ at: Int) -> FieldHistoryReadoutSlot10868 {
        FieldHistoryReadoutSlot10868(label: label, display: .figure(figure(trade(team, at)!.cents), provenance: provenance(at)))
    }

    private static func slots(_ history: FieldHistoryInput10868, _ team: Sampled) -> [FieldHistoryReadoutSlot10868] {
        guard let series = history.series.first(where: { $0.id == team.team.key }) else { return [] }
        return FieldHistoryGeometry10868.readoutSlots(series, in: history)
    }

    private static func row(_ card: VolleyballFieldEndpointsPresentation10868, _ team: Sampled) -> VolleyballFieldEndpointRow10868? {
        card.model.rows.first { $0.slot.seriesID == team.team.key }
    }

    /// The owner's history with only its series or readout replaced, for bad controls.
    private static func rebuilt(_ history: FieldHistoryInput10868, series: [FieldHistorySeries10868]? = nil,
                                readout: FieldHistoryReadoutIntent10868? = nil) -> FieldHistoryInput10868 {
        FieldHistoryInput10868(
            title: history.title, caption: history.caption, series: series ?? history.series, selection: history.selection,
            domain: history.domain, ceiling: history.ceiling, yTicks: history.yTicks, xTicks: history.xTicks,
            guides: history.guides, breaks: history.breaks, readout: readout ?? history.readout, markKey: history.markKey,
            comparisonExplanation: history.comparisonExplanation, notes: history.notes, summary: history.summary,
            plotHeight: history.plotHeight, unboundReadingWords: history.unboundReadingWords,
            plotUnavailableWords: history.plotUnavailableWords, windows: history.windows, scale: history.scale,
            moreOriginals: history.moreOriginals, details: history.details, expand: history.expand, inspect: history.inspect,
            previous: history.previous, next: history.next, inspection: history.inspection, layout: history.layout)
    }

    /// The first hour of the window no sampled team traded.
    private static var emptyHour: Int { hours.first { !tradeHours.contains($0) }! }

    // MARK: - Retained receipt

    func testAll49OriginalsKeepTheirVerbatimRulesAndOnlyThreeOfThemCarryThe65RetainedCloses() {
        XCTAssertEqual(Self.teams.count, 49)
        XCTAssertEqual(Set(Self.teams.map(\.key)).count, 49)
        XCTAssertTrue(Self.teams.allSatisfy { $0.key.hasPrefix(Self.eventTicker + "-") })
        XCTAssertTrue(Self.teams.allSatisfy { $0.primary.hasPrefix("If \($0.name) women's volleyball team wins") })
        XCTAssertTrue(Self.teams.allSatisfy { $0.predicate.hasPrefix($0.name + " wins") })
        // 65 qualified closes: 48 + 12 + 5, strictly later, on the hour, inside the window, positive volume, whole cents.
        XCTAssertEqual(Self.sampled.map { $0.trades.count }, [48, 12, 5])
        XCTAssertEqual(Self.sampled.reduce(0) { $0 + $1.trades.count }, 65)
        for team in Self.sampled {
            XCTAssertTrue(zip(team.trades, team.trades.dropFirst()).allSatisfy { $0.at < $1.at }, team.team.name)
            XCTAssertTrue(team.trades.allSatisfy { ($0.at - Self.windowFrom) % Self.hour == 0 })
            XCTAssertTrue(team.trades.allSatisfy { $0.at >= Self.windowFrom && $0.at <= Self.windowThrough && $0.at < Self.capturedAt })
            XCTAssertTrue(team.trades.allSatisfy { $0.volume > 0 && (0...100).contains($0.cents) })
        }
        XCTAssertEqual(Self.hours.count, 190)
        XCTAssertEqual(Self.tradeHours.count, 57)
        // The other 46 originals have no history, and none is invented.
        let sampledKeys = Set(Self.sampled.map(\.team.key))
        XCTAssertEqual(Self.teams.filter { !sampledKeys.contains($0.key) }.count, 46)
        XCTAssertEqual(Self.history().series.map(\.id), Self.sampled.map(\.team.key))
        // Every original is in the catalogue with its own predicate, outcome name and both rules verbatim.
        let originals = Self.originals()
        let catalogue = originals.catalogue!
        XCTAssertEqual(catalogue.originals.count, 49)
        for team in Self.teams {
            let content = Originals.content(catalogue: catalogue, selection: Originals.Selection(scope: Self.scope, identity: Self.identity(team)))
            XCTAssertEqual(content?.title, team.predicate)
            XCTAssertEqual(content?.outcome, team.name)
            XCTAssertEqual(content?.rules, .verified([team.primary, Self.secondaryRules]), team.key)
            let quote = catalogue.originals.first { $0.identity == Self.identity(team) }?.about.historicalQuote
            XCTAssertEqual(quote != nil, sampledKeys.contains(team.key), team.key)
        }
        // A current probability stays unavailable: no original admits one.
        XCTAssertTrue(catalogue.originals.allSatisfy { $0.mode == .pregame && $0.later == nil && $0.grade == nil })
        XCTAssertTrue(catalogue.originals.allSatisfy { Originals.content(catalogue: catalogue, selection: Originals.Selection(scope: Self.scope, identity: $0.identity))?.readings.allSatisfy { !$0.isValue } == true })
        XCTAssertEqual(OriginalMarketChooser9483.choices(catalogue: catalogue, selection: nil, labels: [:], unavailableChoice: "Team prop").count, 49)
    }

    func testEachTeamsFirstAndLastRecordedTradeKeepTheirOwnClocksAndTheOwnersChangeWords() {
        XCTAssertEqual(Self.sampled.map { [$0.trades.first!.at, $0.trades.first!.cents, $0.trades.last!.at, $0.trades.last!.cents] }, [
            [1791421200000, 43, 1792076400000, 49], [1791417600000, 40, 1791867600000, 25], [1791417600000, 4, 1792011600000, 3],
        ])
        // The owner's words agree with the retained closes (this check's own arithmetic, never the product's).
        for team in Self.sampled {
            let change = team.trades.last!.cents - team.trades.first!.cents
            XCTAssertEqual(Self.changeWords[team.team.key], change > 0 ? "+\(change)" : "−\(-change)")
        }
        let card = VolleyballFieldEventPagePresentation10868(input: Self.page()).endpointsContent(reader: false)!
        XCTAssertEqual(card.model.rows.map(\.slot.seriesID), Self.sampled.map(\.team.key))
        for team in Self.sampled {
            let row = Self.row(card, team)!
            XCTAssertEqual(row.first?.slot, Self.figureSlot("Earlier", team, team.trades.first!.at))
            XCTAssertEqual(row.last?.slot, Self.figureSlot("Later", team, team.trades.last!.at))
            XCTAssertEqual(row.first?.point?.probability, Double(team.trades.first!.cents) / 100)
            XCTAssertEqual(row.last?.point?.probability, Double(team.trades.last!.cents) / 100)
            XCTAssertEqual(row.last?.chance, .value(probability: Double(team.trades.last!.cents) / 100,
                                                   fraction: Double(team.trades.last!.cents) / 100 / 0.5))
            XCTAssertEqual(card.model.change(row)?.figure, Self.changeWords[team.team.key])
            XCTAssertEqual(card.model.endpointSummary(row, row.last!),
                           "\(team.team.name). Later \(Self.figure(team.trades.last!.cents)), \(Self.provenance(team.trades.last!.at))")
        }
        // Three latest trades, three dates: never one simultaneous snapshot.
        XCTAssertEqual(Set(card.model.rows.compactMap { $0.last?.slot }.map(FieldHistoryGeometry10868.spokenSlot)).count, 3)
        XCTAssertEqual(Set(Self.sampled.map { $0.trades.last!.at }).count, 3)
        // Change words appear only beside two shown figures.
        let halfTied = VolleyballFieldEndpointsModel10868(
            input: Self.endpoints(readings: [Self.reading(Self.nebraska, .first)]), history: Self.history())
        XCTAssertNil(halfTied.change(halfTied.rows[0]))
        XCTAssertEqual(halfTied.rows[0].last?.slot.display, .words("Not recorded in this capture"))
        // The connector joins the two placed marks only; it is not a path.
        let plan = VolleyballFieldEndpointsGeometry10868.trackPlan(first: 0.86, last: 0.98, ticks: [1], in: CGSize(width: 300, height: 30),
                                                                   radius: 5, outline: 1.5, connectorWidth: 5)!
        XCTAssertEqual(plan.connector!.minX, plan.first!.x, accuracy: 1e-9)
        XCTAssertEqual(plan.connector!.maxX, plan.last!.x, accuracy: 1e-9)
        XCTAssertNil(VolleyballFieldEndpointsGeometry10868.trackPlan(first: 0.86, last: nil, ticks: [], in: CGSize(width: 300, height: 30),
                                                                     radius: 5, outline: 1.5, connectorWidth: 5)?.connector)
    }

    // MARK: - History

    func testOnlyAdjacentTradedHoursJoinAndAnEmptyHourStaysAGapWithNoCarryForward() {
        let history = Self.history()
        for series in history.series {
            for run in series.runs {
                XCTAssertTrue(zip(run.points, run.points.dropFirst()).allSatisfy { $1.x - $0.x == 1 }, run.id)
            }
            XCTAssertTrue(zip(series.runs, series.runs.dropFirst()).allSatisfy { $1.points.first!.x - $0.points.last!.x >= 2 })
            XCTAssertTrue(series.runs.flatMap(\.points).allSatisfy { $0.style == .filled })
        }
        XCTAssertEqual(history.series.flatMap(\.runs).flatMap(\.points).count, 65)
        // An hour no team traded: every inspected slot is words, no ring, nothing carried forward.
        let empty = Self.history(.hour(Self.emptyHour))
        for team in Self.sampled {
            XCTAssertEqual(Self.slots(empty, team).last, FieldHistoryReadoutSlot10868(label: "Selected hour", display: .words("No trade in this hour")))
            let series = empty.series.first { $0.id == team.team.key }!
            XCTAssertNil(FieldHistoryGeometry10868.inspectedPoint(series, in: empty))
        }
        // An hour only Nebraska traded: its own close; the others keep words, not their previous close.
        let onlyNebraska = Self.nebraskaTrades.map { $0.at }.first { at in Self.pittsburgh.trades.allSatisfy { $0.at != at } && Self.wisconsin.trades.allSatisfy { $0.at != at } }!
        let sparse = Self.history(.hour(onlyNebraska))
        XCTAssertEqual(Self.slots(sparse, Self.nebraska).last, Self.figureSlot("Selected hour", Self.nebraska, onlyNebraska))
        XCTAssertEqual(Self.slots(sparse, Self.pittsburgh).last?.display, .words("No trade in this hour"))
        XCTAssertEqual(Self.slots(sparse, Self.wisconsin).last?.display, .words("No trade in this hour"))
    }

    func testTheCloseAndFullScalesChangeOnlyTheCeilingAndNeverTheRawCoordinates() {
        let close = Self.history()
        let full = Self.history(fullScale: true)
        XCTAssertEqual(close.ceiling, 0.5)
        XCTAssertEqual(full.ceiling, 1)
        XCTAssertEqual(close.series, full.series)
        XCTAssertEqual(close.domain, full.domain)
        XCTAssertEqual(close.scale?.label, "Show 0–100%")
        XCTAssertEqual(full.scale?.label, "Use closer scale")
        XCTAssertEqual(close.yTicks.flatMap(\.lines), ["0%", "25%", "50%"])
        XCTAssertEqual(full.yTicks.flatMap(\.lines), ["0%", "50%", "100%"])
        // Every retained close fits the close scale: none is clipped by it.
        XCTAssertTrue(close.series.flatMap(\.runs).flatMap(\.points).allSatisfy { FieldHistoryGeometry10868.isPlaceable($0, in: close) })
        // The page carries the owner's choice to full size; the endpoint card keeps its own absolute scale.
        let page = VolleyballFieldEventPagePresentation10868(input: Self.page(fullScale: true), mode: .reader(.history))
        XCTAssertEqual(page.historyContent(reader: true, accessibilitySize: false).input.ceiling, 1)
        XCTAssertEqual(page.endpointsContent(reader: true)?.input.scale.ceiling, 0.5)
    }

    func testTheAnyHourSliderOffersEveryHourWhileEarlierAndLaterReachOnlyTradedHoursAndStopAtTheEnds() {
        let latest = Self.history()
        XCTAssertEqual(latest.inspection?.choices.count, 190)
        XCTAssertTrue(latest.inspection!.choices.contains { $0.id == "hour.\(Self.emptyHour)" })
        XCTAssertEqual(latest.inspection?.choicePresentation, .slider(label: "Explore any hour"))
        // Last recorded mode: Earlier opens the latest traded hour; Later is disabled.
        XCTAssertEqual(Self.earlier(nil), 1792076400000)
        XCTAssertNil(Self.later(nil))
        XCTAssertEqual(FieldHistoryGeometry10868.adjustableID(latest.previous, hasCallback: true, in: latest), "hour.earlier")
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(latest.next, hasCallback: true, in: latest))
        // The first traded hour: Earlier disabled. The last: Later disabled.
        let first = Self.history(.hour(Self.tradeHours.first!))
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(first.previous, hasCallback: true, in: first))
        XCTAssertEqual(FieldHistoryGeometry10868.adjustableID(first.next, hasCallback: true, in: first), "hour.later")
        let last = Self.history(.hour(Self.tradeHours.last!))
        XCTAssertNil(FieldHistoryGeometry10868.adjustableID(last.next, hasCallback: true, in: last))
        // From an empty hour both jump to real traded hours, never to another empty one.
        let empty = Self.history(.hour(Self.emptyHour))
        XCTAssertNotNil(FieldHistoryGeometry10868.adjustableID(empty.previous, hasCallback: true, in: empty))
        XCTAssertTrue([Self.earlier(Self.emptyHour), Self.later(Self.emptyHour)].compactMap { $0 }.allSatisfy { Self.tradeHours.contains($0) })
        for at in Self.hours {
            XCTAssertTrue([Self.earlier(at), Self.later(at)].compactMap { $0 }.allSatisfy { Self.tradeHours.contains($0) })
        }
        XCTAssertEqual(empty.inspection?.choices.filter(\.isSelected).map(\.id), ["hour.\(Self.emptyHour)"])
    }

    func testTheSameObservationStaysOneDateWhileEqualValuesAtDistinctHoursKeepTheirOwnDates() {
        // Nebraska's last trade inspected: both slots are that one observation with its one date.
        let lastHour = Self.nebraskaTrades.last!.at
        let same = Self.history(.hour(lastHour))
        XCTAssertEqual(Self.slots(same, Self.nebraska), [
            Self.figureSlot("Last recorded trade", Self.nebraska, lastHour), Self.figureSlot("Selected hour", Self.nebraska, lastHour),
        ])
        XCTAssertEqual(Self.slots(same, Self.pittsburgh).last?.display, .words("No trade in this hour"))
        // Equal 45% closes at two hours stay two dated observations.
        let firstEqual = Self.slots(Self.history(.hour(1791432000000)), Self.nebraska).last
        let secondEqual = Self.slots(Self.history(.hour(1791439200000)), Self.nebraska).last
        XCTAssertEqual(firstEqual, Self.figureSlot("Selected hour", Self.nebraska, 1791432000000))
        XCTAssertEqual(secondEqual, Self.figureSlot("Selected hour", Self.nebraska, 1791439200000))
        XCTAssertNotEqual(firstEqual, secondEqual)
        // One hour two teams traded: each keeps its own independent close.
        let shared = Self.history(.hour(1791561600000))
        XCTAssertEqual(Self.slots(shared, Self.nebraska).last?.display, .figure("45%", provenance: Self.provenance(1791561600000)))
        XCTAssertEqual(Self.slots(shared, Self.pittsburgh).last?.display, .figure("29%", provenance: Self.provenance(1791561600000)))
    }

    // MARK: - Readouts and the presentation copy

    func testReadoutsAreTheHistorysOwnSlotsAtOneFigureSizeAndHighlightOnlyThroughItsLiveChooseAction() {
        XCTAssertEqual(VolleyballFieldEventPageModel10868.figureSize, 26)
        for moment in [Moment.lastRecorded, .hour(Self.emptyHour), .hour(1791561600000)] {
            let input = Self.page(moment)
            let pageView = VolleyballFieldEventPagePresentation10868(input: input, onHistoryAction: { _ in })
            let readerView = VolleyballFieldEventPagePresentation10868(input: input, mode: .reader(.history), onHistoryAction: { _ in })
            let inline = pageView.readoutsContent(reader: false, accessibilitySize: false)
            let full = readerView.readoutsContent(reader: true, accessibilitySize: false)
            XCTAssertEqual(inline.entries.map(\.slots), full.entries.map(\.slots))
            XCTAssertEqual(inline.history, pageView.historyContent(reader: false, accessibilitySize: false).input)
            XCTAssertEqual(full.history, readerView.historyContent(reader: true, accessibilitySize: false).input)
            XCTAssertEqual(inline.label, "Sampled team readouts")
            XCTAssertEqual(inline.entries.map(\.series), input.history.series)
            XCTAssertEqual(inline.entries.map(\.series.shape), [.circle, .diamond, .square])
            for (entry, team) in zip(inline.entries, Self.sampled) {
                XCTAssertEqual(entry.slots, Self.slots(input.history, team))
                XCTAssertEqual(VolleyballFieldReadoutsPresentation10868.chooseID(entry), "highlight.\(team.team.key)")
            }
            XCTAssertEqual(inline.entries.map(\.isSelected), [true, false, false])
        }
        // Last recorded: one slot each, each with its own date.
        let latest = VolleyballFieldEventPagePresentation10868(input: Self.page()).readoutsContent(reader: false, accessibilitySize: false)
        XCTAssertEqual(latest.entries.map(\.slots), Self.sampled.map { [Self.figureSlot("Last recorded trade", $0, $0.trades.last!.at)] })
        XCTAssertEqual(VolleyballFieldReadoutsPresentation10868.spoken(latest.entries[0]),
                       "Nebraska. Last recorded trade 49%, \(Self.provenance(1792076400000))")
        XCTAssertEqual(VolleyballFieldReadoutsPresentation10868.figures(latest.entries), ["49%", "25%", "3%"])
        // No callback: the history's own rule makes the readout static, with no id.
        XCTAssertTrue(latest.entries.allSatisfy { $0.choose == .shownStatic && VolleyballFieldReadoutsPresentation10868.chooseID($0) == nil })
        // At an hour no team traded, only each team's own last recorded figure is shown.
        let empty = VolleyballFieldEventPagePresentation10868(input: Self.page(.hour(Self.emptyHour)), onHistoryAction: { _ in })
            .readoutsContent(reader: false, accessibilitySize: false)
        XCTAssertEqual(VolleyballFieldReadoutsPresentation10868.figures(empty.entries), ["49%", "25%", "3%"])
    }

    func testThePresentationCopyHidesOnlyTheDuplicateKeyAndTheOwnersHistoryStaysWhole() {
        let owner = Self.history(.hour(1791561600000))
        let input = Self.page(.hour(1791561600000))
        let model = VolleyballFieldEventPageModel10868(input)
        XCTAssertTrue(model.hidesSharedKey)
        XCTAssertEqual(input.history, owner)
        XCTAssertTrue(owner.showsKey)
        let presented = model.history(reader: false, accessibilitySize: false)
        XCTAssertFalse(presented.showsKey)
        var restored = presented
        restored.showsKey = true
        XCTAssertEqual(restored, owner)
        var full = model.history(reader: true, accessibilitySize: false)
        full.showsKey = true
        XCTAssertEqual(full, VolleyballFieldEventPageModel10868.presentationCopy(owner, plotHeight: 370, expand: nil, showsKey: true))
        XCTAssertEqual(FieldHistoryGeometry10868.actions(presented), FieldHistoryGeometry10868.actions(owner))
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(owner), [.selectionWords, .key])
        XCTAssertEqual(FieldHistoryGeometry10868.blocksAbovePlot(presented), [.selectionWords])
        XCTAssertEqual(FieldHistoryGeometry10868.drawsStyle(.filled, in: presented), true)
        // Key context is more than readouts: the key stays.
        var keyed = Self.parts()
        keyed.history = Self.history(keyContext: true)
        let keyedModel = VolleyballFieldEventPageModel10868(keyed.input)
        XCTAssertFalse(keyedModel.hidesSharedKey)
        XCTAssertEqual(keyedModel.history(reader: false, accessibilitySize: false), keyed.history)
        // An owner that hides its own key keeps it hidden.
        var hidden = Self.parts()
        hidden.history.showsKey = false
        XCTAssertFalse(VolleyballFieldEventPageModel10868(hidden.input).history(reader: true, accessibilitySize: true).showsKey)
    }

    func testPlotHeightsArePageFullSizeAndAccessibilityAndFullSizeIsNeverShorterThanThePage() {
        typealias Model = VolleyballFieldEventPageModel10868
        XCTAssertEqual(Model.plotHeight(page: 302, reader: 370, accessibility: 390, isReader: false, accessibilitySize: false), 302)
        XCTAssertEqual(Model.plotHeight(page: 302, reader: 370, accessibility: 390, isReader: true, accessibilitySize: false), 370)
        XCTAssertEqual(Model.plotHeight(page: 302, reader: 370, accessibility: 390, isReader: false, accessibilitySize: true), 390)
        XCTAssertEqual(Model.plotHeight(page: 302, reader: 370, accessibility: 390, isReader: true, accessibilitySize: true), 390)
        // A smaller positive owner height never shortens full size.
        XCTAssertEqual(Model.plotHeight(page: 302, reader: 150, accessibility: nil, isReader: true, accessibilitySize: false), 302)
        XCTAssertEqual(Model.plotHeight(page: 302, reader: 370, accessibility: 200, isReader: true, accessibilitySize: true), 370)
        for invalid: CGFloat? in [nil, 0, -1, .nan, .infinity] {
            XCTAssertEqual(Model.plotHeight(page: 302, reader: invalid, accessibility: invalid, isReader: true, accessibilitySize: true), 302)
        }
        for owner: CGFloat? in [nil, 150, 302, 370, -1, .nan] {
            for accessibility: CGFloat? in [nil, 200, 390] {
                for size in [false, true] {
                    XCTAssertGreaterThanOrEqual(
                        Model.plotHeight(page: 302, reader: owner, accessibility: accessibility, isReader: true, accessibilitySize: size),
                        Model.plotHeight(page: 302, reader: owner, accessibility: accessibility, isReader: false, accessibilitySize: size))
                }
            }
        }
        // The composed contents carry them; the owner's input keeps its own.
        let input = Self.page()
        let pageView = VolleyballFieldEventPagePresentation10868(input: input)
        XCTAssertEqual(pageView.historyContent(reader: false, accessibilitySize: false).input.plotHeight, 302)
        XCTAssertEqual(pageView.historyContent(reader: true, accessibilitySize: false).input.plotHeight, 370)
        XCTAssertEqual(pageView.historyContent(reader: false, accessibilitySize: true).input.plotHeight, 390)
        XCTAssertEqual(pageView.readoutsContent(reader: true, accessibilitySize: true).history.plotHeight, 390)
        XCTAssertEqual(input.history.plotHeight, 302)
        var shorter = Self.parts()
        shorter.readerPlotHeight = 150
        XCTAssertEqual(VolleyballFieldEventPagePresentation10868(input: shorter.input).historyContent(reader: true, accessibilitySize: false).input.plotHeight, 302)
    }

    // MARK: - Identity

    func testArbitraryDuplicateForeignFutureOrWithdrawnEndpointReferencesNeverBorrowANeighbour() {
        let history = Self.history()
        // Arbitrary order is kept; a duplicate or unknown id keeps the owner's name and borrows nothing.
        let unknown = VolleyballFieldEndpointSlot10868(seriesID: "KXNCAAWV-26-UNKNOWN", name: "Kentucky")
        let model = VolleyballFieldEndpointsModel10868(
            input: Self.endpoints(displayed: [Self.slot(Self.wisconsin), Self.slot(Self.nebraska), Self.slot(Self.pittsburgh), Self.slot(Self.pittsburgh), unknown]),
            history: history)
        XCTAssertEqual(model.rows.map(\.slot.seriesID), ["KXNCAAWV-26-WIS", "KXNCAAWV-26-NEB", "KXNCAAWV-26-PITT", "KXNCAAWV-26-PITT", "KXNCAAWV-26-UNKNOWN"])
        XCTAssertEqual(model.rows.map { $0.series != nil }, [true, true, false, false, false])
        XCTAssertEqual(model.rows.map { model.stateWords($0) }, [nil, nil, "Team unavailable in this update", "Team unavailable in this update", "Team unavailable in this update"])
        XCTAssertEqual(model.rowSummary(model.rows[4]), "Kentucky. Team unavailable in this update")
        XCTAssertEqual(model.rows[0].last?.slot, Self.figureSlot("Later", Self.wisconsin, Self.wisconsinTrades.last!.at))
        // A foreign point, an independent figure, a duplicated reading or a point outside the window: words, no mark, no open.
        let future = VolleyballFieldEndpointReading10868(seriesID: Self.nebraska.team.key, endpoint: .last,
                                                         reading: .observation(pointID: Self.pointID(Self.nebraska, Self.windowThrough + Self.hour), figure: "49%", provenance: "Later"))
        let cases: [[VolleyballFieldEndpointReading10868]] = [
            [Self.reading(Self.pittsburgh, .last, boundTo: Self.nebraska)],
            [VolleyballFieldEndpointReading10868(seriesID: Self.pittsburgh.team.key, endpoint: .last, reading: .independent(figure: "25%", provenance: "Later"))],
            [Self.reading(Self.pittsburgh, .last), Self.reading(Self.pittsburgh, .last)],
            [future],
        ]
        for readings in cases {
            let team = readings[0].seriesID == Self.nebraska.team.key ? Self.nebraska : Self.pittsburgh
            let neighbours = [Self.reading(Self.wisconsin, .first), Self.reading(Self.wisconsin, .last)]
            let bad = VolleyballFieldEndpointsModel10868(input: Self.endpoints(readings: readings + [Self.reading(team, .first)] + neighbours),
                                                         history: history)
            let row = bad.rows.first { $0.slot.seriesID == team.team.key }!
            XCTAssertEqual(row.last?.slot.display, .words("Not recorded in this capture"))
            XCTAssertNil(row.last?.point)
            XCTAssertEqual(row.last?.chance, .unavailable)
            XCTAssertNil(bad.openAction(row, row.last!, canOpen: true))
            XCTAssertNil(bad.change(row))
            // Its own first endpoint and its neighbours keep theirs.
            XCTAssertNotNil(row.first?.point)
            XCTAssertNotNil(bad.rows.first { $0.slot.seriesID == Self.wisconsin.team.key }?.first?.point)
        }
        // A withdrawn series: its row is unavailable; the others keep their figures.
        let withdrawn = VolleyballFieldEndpointsModel10868(input: Self.endpoints(), history: Self.history(teams: [Self.nebraska, Self.pittsburgh]))
        XCTAssertNil(withdrawn.rows[2].series)
        XCTAssertNotNil(withdrawn.rows[1].last?.point)
        // A shared series id names nobody.
        let shared = Self.history(teams: [Self.nebraska, Self.nebraska, Self.pittsburgh])
        XCTAssertNil(VolleyballFieldEndpointsModel10868(input: Self.endpoints(), history: shared).rows[0].series)
    }

    func testHeldHighlightHourAndOriginalAreOmittedWhenWithdrawnAndRestoredOnlyByExactIdentity() {
        // The held highlight names a withdrawn team: the history's own words, nobody marked.
        let withdrawn = Self.history(selected: Self.wisconsin, teams: [Self.nebraska, Self.pittsburgh])
        XCTAssertEqual(FieldHistoryGeometry10868.selectionWords(withdrawn), "This team isn’t in this history")
        var parts = Self.parts()
        parts.history = withdrawn
        let omitted = VolleyballFieldEventPagePresentation10868(input: parts.input).readoutsContent(reader: false, accessibilitySize: false)
        XCTAssertEqual(omitted.entries.map(\.isSelected), [false, false])
        // Restored by its exact id only.
        parts.history = Self.history(selected: Self.wisconsin)
        let restored = VolleyballFieldEventPagePresentation10868(input: parts.input).readoutsContent(reader: false, accessibilitySize: false)
        XCTAssertEqual(restored.entries.map(\.isSelected), [false, false, true])
        // The held hour is the owner's, unchanged on the page and full size.
        let held = Self.page(.hour(1791561600000))
        let pageView = VolleyballFieldEventPagePresentation10868(input: held)
        XCTAssertEqual(pageView.historyContent(reader: false, accessibilitySize: false).input.inspection,
                       pageView.historyContent(reader: true, accessibilitySize: false).input.inspection)
        XCTAssertEqual(pageView.historyContent(reader: true, accessibilitySize: false).input.inspection?.x, Self.x(1791561600000))
        // The held original withdrawn: no Details, never a neighbour; restored by exact identity.
        let kentucky = Self.team("KXNCAAWV-26-UK")
        let gone = Self.originals(selection: kentucky, omitting: kentucky.key)
        XCTAssertNil(Originals.content(catalogue: gone.catalogue, selection: gone.selection))
        XCTAssertEqual(gone.catalogue?.originals.count, 48)
        let back = Self.originals(selection: kentucky)
        XCTAssertEqual(Originals.content(catalogue: back.catalogue, selection: back.selection)?.outcome, "Kentucky")
        let foreign = Originals.Selection(scope: "another scope", identity: Self.identity(kentucky))
        XCTAssertNil(Originals.content(catalogue: back.catalogue, selection: foreign))
    }

    // MARK: - Actions

    func testEveryActionHandsBackItsExactPayloadHoldsOnceAndFullSizeAndPassiveReadsDoNot() {
        var log: [String] = []
        let input = Self.page()
        let originals = Self.originals(selection: Self.nebraska.team)
        func view(_ mode: FieldEventPageMode10868 = .page, hook: Bool = true) -> VolleyballFieldEventPagePresentation10868 {
            VolleyballFieldEventPagePresentation10868(
                input: input, mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onAllProps: { log.append("all") },
                onOriginalSelect: { log.append("select:\($0.identity.market)") },
                onOriginalHistory: { log.append("history:\($0.actionID)") },
                onHistoryAction: { log.append("chart:\($0)") },
                onHistoryInspectionChoice: { log.append("choice:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onEndpointOpen: { log.append("open:\($0.seriesID):\($0.pointID)") },
                onReaderOpen: { log.append("reader:\($0.rawValue)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every leaf and mode calls nothing.
        let page = view()
        let readouts = page.readoutsContent(reader: false, accessibilitySize: false)
        let history = page.historyContent(reader: false, accessibilitySize: false)
        let card = page.endpointsContent(reader: false)!
        _ = readouts.entries
        _ = card.model.rows
        _ = view(.reader(.history)).historyContent(reader: true, accessibilitySize: true)
        _ = view(.reader(.movement)).endpointsContent(reader: true)
        _ = view(.catalogue).catalogueContent()
        _ = view(.original).originalDetailsContent()
        _ = view(.about).aboutContent()
        XCTAssertEqual(log, [])

        // Each page action: the hook once, then the exact payload.
        readouts.onChoose?(VolleyballFieldReadoutsPresentation10868.chooseID(readouts.entries[1])!)
        history.onAction?("scale.full")
        history.onInspectionChoice?("hour.\(Self.emptyHour)")
        history.onPlotPosition?(12)
        let lastRow = Self.row(card, Self.nebraska)!
        card.onOpen?(card.model.openAction(lastRow, lastRow.last!, canOpen: true)!)
        card.onExpand?()
        page.openPageAbout()
        page.openAllProps()
        let selection = Originals.Selection(scope: Self.scope, identity: Self.identity(Self.team("KXNCAAWV-26-UK")))
        view(.catalogue).catalogueContent()?.onSelect?(selection)
        view(.original).originalDetailsContent()?.onHistory?(Originals.HistoryIntent(selection: selection, entry: .expand, actionID: "details.expand"))
        XCTAssertEqual(log, [
            "hold", "chart:highlight.KXNCAAWV-26-PITT",
            "hold", "chart:scale.full",
            "hold", "choice:hour.\(Self.emptyHour)",
            "hold", "plot:12.0",
            "hold", "open:KXNCAAWV-26-NEB:KXNCAAWV-26-NEB@1792076400000",
            "hold", "reader:movement",
            "hold", "about",
            "hold", "all",
            "hold", "select:KXNCAAWV-26-UK",
            "hold", "history:details.expand",
        ])

        // Full-size content keeps the exact callbacks: no hold, and no full-size entry inside itself.
        log = []
        view(.reader(.history)).historyContent(reader: true, accessibilitySize: false).onAction?("hour.later")
        let fullReadouts = view(.reader(.history)).readoutsContent(reader: true, accessibilitySize: false)
        fullReadouts.onChoose?(VolleyballFieldReadoutsPresentation10868.chooseID(fullReadouts.entries[2])!)
        let fullCard = view(.reader(.movement)).endpointsContent(reader: true)!
        XCTAssertNil(fullCard.onExpand)
        let firstRow = Self.row(fullCard, Self.wisconsin)!
        fullCard.onOpen?(fullCard.model.openAction(firstRow, firstRow.first!, canOpen: true)!)
        view(.reader(.history)).openAbout()
        XCTAssertEqual(log, ["chart:hour.later", "chart:highlight.KXNCAAWV-26-WIS",
                             "open:KXNCAAWV-26-WIS:KXNCAAWV-26-WIS@1791417600000", "about"])

        // No hook: every page action is the owner's own.
        log = []
        view(hook: false).historyContent(reader: false, accessibilitySize: false).onAction?("history.expand")
        XCTAssertEqual(log, ["chart:history.expand"])

        // Absent callbacks: no control and no hook call.
        log = []
        let bare = VolleyballFieldEventPagePresentation10868(input: input, originals: originals, onInteraction: { log.append("hold") })
        XCTAssertNil(bare.readoutsContent(reader: false, accessibilitySize: false).onChoose)
        XCTAssertNil(bare.historyContent(reader: false, accessibilitySize: false).onAction)
        XCTAssertNil(bare.endpointsContent(reader: false)?.onOpen)
        XCTAssertNil(bare.endpointsContent(reader: false)?.onExpand)
        XCTAssertNil(bare.catalogueContent()?.onSelect)
        XCTAssertNil(bare.originalDetailsContent()?.onHistory)
        XCTAssertNil(bare.aboutOpener())
        bare.openPageAbout()
        bare.openAllProps()
        XCTAssertEqual(log, [])
    }

    func testEveryPayloadCarriesItsOwnOriginalAndARetainedHourAndBorrowedForeignOrFutureKeysAreCaught() {
        for moment in [Moment.lastRecorded, .hour(Self.emptyHour), .hour(1791561600000), .hour(Self.nebraskaTrades.last!.at)] {
            XCTAssertEqual(Self.payloadViolations(Self.page(moment)), [], "\(moment)")
        }
        // A borrowed latest value: Pittsburgh's last close shown at an hour it did not trade.
        var borrowed = Self.parts(.hour(Self.emptyHour))
        borrowed.history = Self.history(.hour(Self.emptyHour), borrowLatest: Self.pittsburgh)
        XCTAssertEqual(Self.payloadViolations(borrowed.input), ["borrowed: KXNCAAWV-26-PITT KXNCAAWV-26-PITT@1791867600000"])
        // Foreign and future keys are caught.
        XCTAssertEqual(Self.openViolations(VolleyballFieldEndpointOpen10868(seriesID: "KXNCAAWV-26-PITT", pointID: "KXNCAAWV-26-NEB@1792076400000")),
                       ["foreign or unknown point KXNCAAWV-26-NEB@1792076400000"])
        XCTAssertEqual(Self.openViolations(VolleyballFieldEndpointOpen10868(seriesID: "KXNCAAWV-26-UK", pointID: "KXNCAAWV-26-UK@1791417600000")),
                       ["foreign series KXNCAAWV-26-UK"])
        XCTAssertFalse(Self.openViolations(VolleyballFieldEndpointOpen10868(seriesID: "KXNCAAWV-26-NEB",
                                                                            pointID: "KXNCAAWV-26-NEB@\(Self.windowThrough + Self.hour)")).isEmpty)
        // The product itself never hands back a foreign point.
        let foreign = VolleyballFieldEndpointsModel10868(
            input: Self.endpoints(readings: [Self.reading(Self.pittsburgh, .first), Self.reading(Self.pittsburgh, .last, boundTo: Self.nebraska)]),
            history: Self.history())
        let row = foreign.rows.first { $0.slot.seriesID == Self.pittsburgh.team.key }!
        XCTAssertEqual(row.sides.compactMap { foreign.openAction(row, $0, canOpen: true) },
                       [VolleyballFieldEndpointOpen10868(seriesID: "KXNCAAWV-26-PITT", pointID: "KXNCAAWV-26-PITT@1791417600000")])
        // A choose id that names another team is caught.
        var crossed = Self.parts()
        let owned = crossed.history.series
        crossed.history = Self.rebuilt(crossed.history, series: owned.enumerated().map { index, series in
            FieldHistorySeries10868(id: series.id, name: series.name, shape: series.shape, tint: series.tint, runs: series.runs,
                                    links: series.links, labelPointID: series.labelPointID, before: series.before,
                                    recorded: series.recorded, absentWords: series.absentWords,
                                    choose: owned[(index + 1) % owned.count].choose)
        })
        XCTAssertEqual(Self.payloadViolations(crossed.input).filter { $0.hasPrefix("choose names another series") }.count, 3)
    }

    func testArchivedChancesAreNeverAdvertisedAsPreSeasonCurrentOrSettledValues() {
        for moment in [Moment.lastRecorded, .hour(Self.emptyHour), .hour(1791561600000)] {
            XCTAssertEqual(Self.claims(Self.page(moment), originals: Self.originals(selection: Self.nebraska.team)), [], "\(moment)")
        }
        // Positive controls: each advertising shape is caught.
        var currentReadout = Self.parts()
        currentReadout.history = Self.rebuilt(Self.history(), readout: .singleBefore(label: "Current chance"))
        XCTAssertTrue(Self.claims(currentReadout.input, originals: nil).contains("figure under: Current chance"))
        var preSeason = Self.parts()
        preSeason.endpoints = Self.endpoints(copy: VolleyballFieldEndpointsCopy10868(
            eyebrow: nil, title: "Who gained ground?", intro: nil, firstLabel: "Pre-season", lastLabel: "Later",
            endpointUnavailable: "Not recorded in this capture", offScale: "Above this scale", graphicLabel: "Changes",
            note: nil, openHint: nil, expandLabel: "Expand"))
        XCTAssertTrue(Self.claims(preSeason.input, originals: nil).contains("figure under: Pre-season"))
        let nebraska = Self.nebraska.team
        let current = Originals.Original(
            identity: Self.identity(nebraska), title: nebraska.predicate, outcome: nebraska.name, mode: .comparison(.current),
            pregame: .missing("Unavailable"), later: .value("49%", placement: 0.49, provenance: Self.provenance(1792076400000)),
            grade: nil, about: Originals.About(source: "Kalshi", rules: .verified([nebraska.primary]), provenance: [], historicalQuote: nil))
        let currentClaims = Self.claims(Self.page(), originals: Self.originals(replacing: current))
        XCTAssertTrue(currentClaims.contains("current mode: KXNCAAWV-26-NEB"))
        XCTAssertTrue(currentClaims.contains("figure under: Current chance"))
        let settled = Originals.Original(
            identity: Self.identity(nebraska), title: nebraska.predicate, outcome: nebraska.name, mode: .result,
            pregame: .missing("Unavailable"), later: nil, grade: Originals.Grade(words: "Won", provenance: nil),
            about: Originals.About(source: "Kalshi", rules: .verified([nebraska.primary]), provenance: [], historicalQuote: nil))
        XCTAssertTrue(Self.claims(Self.page(), originals: Self.originals(replacing: settled)).contains("settled: KXNCAAWV-26-NEB"))
        var settledWords = Self.parts()
        settledWords.header = VolleyballFieldEventPageHeader10868(title: "Women’s volleyball", subtitle: nil, context: "Final · Nebraska won")
        XCTAssertTrue(Self.claims(settledWords.input, originals: nil).contains("claim: Final · Nebraska won"))
        // The negated sentences are explicit about what these chances are not.
        XCTAssertTrue(Self.about.paragraphs[1].contains("not current chances"))
        XCTAssertTrue(Self.endpointCopy.note!.contains("not pre-season or current chances"))
    }

    // MARK: - Full size and arrangement

    func testFullSizeReadersUseTheSameViewsAndInputsAndAnUnshownCardKeepsTheOwnersWords() {
        let input = Self.page(.hour(1791561600000))
        let model = VolleyballFieldEventPageModel10868(input)
        let pageView = VolleyballFieldEventPagePresentation10868(input: input, onReaderOpen: { _ in })
        let reader = VolleyballFieldEventPagePresentation10868(input: input, mode: .reader(.history), onReaderOpen: { _ in })
        let inline = pageView.historyContent(reader: false, accessibilitySize: false).input
        let full = reader.historyContent(reader: true, accessibilitySize: false).input
        XCTAssertNil(full.expand)
        XCTAssertNotNil(inline.expand)
        XCTAssertEqual(full.series, inline.series)
        XCTAssertEqual(full.inspection, inline.inspection)
        XCTAssertEqual(full.readout, inline.readout)
        XCTAssertEqual(full.layout, inline.layout)
        XCTAssertEqual(full.selection, inline.selection)
        XCTAssertEqual(full.scale, inline.scale)
        let inlineCard = pageView.endpointsContent(reader: false)!
        let fullCard = VolleyballFieldEventPagePresentation10868(input: input, mode: .reader(.movement), onReaderOpen: { _ in }).endpointsContent(reader: true)!
        XCTAssertEqual(inlineCard.input, fullCard.input)
        XCTAssertEqual(inlineCard.history, fullCard.history)
        XCTAssertEqual(inlineCard.model.rows, fullCard.model.rows)
        XCTAssertNotNil(inlineCard.onExpand)
        XCTAssertNil(fullCard.onExpand)
        // Only the history and the endpoint card exist full size on this route.
        XCTAssertTrue(model.isMounted(.history))
        XCTAssertTrue(model.isMounted(.movement))
        XCTAssertFalse(model.isMounted(.field))
        var noCard = Self.parts()
        noCard.endpoints = nil
        XCTAssertFalse(VolleyballFieldEventPageModel10868(noCard.input).isMounted(.movement))
        XCTAssertNil(VolleyballFieldEventPagePresentation10868(input: noCard.input).endpointsContent(reader: false))
        // The About entry is full-size only; the page has its own control.
        XCTAssertTrue(model.aboutEntry(mode: .reader(.history), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .reader(.history), canOpen: false))
        var silent = Self.parts()
        silent.about = FieldEventPageAbout10868(title: " ", paragraphs: ["", "  "])
        XCTAssertNil(VolleyballFieldEventPageModel10868(silent.input).about)
        XCTAssertTrue(model.allPropsAvailable(canOpen: true))
        XCTAssertFalse(model.allPropsAvailable(canOpen: false))
    }

    func testPhoneWideAndAccessibilityArrangementsReflowWithoutShrinkingFiguresOrTheChart() {
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(FieldEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(VolleyballFieldEventPageModel10868.slotArrangements(accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(VolleyballFieldEventPageModel10868.slotArrangements(accessibilitySize: true), [.stacked])
        // Readouts: columns while every measured figure fits an equal share, else rows; rows at accessibility sizes.
        let spacing = VolleyballFieldReadoutsPresentation10868.spacing
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 360, count: 3, figureWidths: [80, 80, 80], spacing: spacing,
                                                             accessibilitySize: false), .columns)
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 240, count: 3, figureWidths: [80, 80, 80], spacing: spacing,
                                                             accessibilitySize: false), .rows)
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 900, count: 3, figureWidths: [80, 80, 80], spacing: spacing,
                                                             accessibilitySize: true), .rows)
        // The chart is never compressed by an arrangement: heights come from the owner only.
        XCTAssertEqual(VolleyballFieldEventPageModel10868(Self.page()).history(reader: false, accessibilitySize: false).plotHeight, 302)
        XCTAssertEqual(VolleyballFieldEventPageModel10868(Self.page()).history(reader: true, accessibilitySize: true).plotHeight, 390)
    }
}
