import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the combat event screen (`mma`) as a composition of the accepted
/// leaves before, during and after the fight.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// composition the screen defers to: which actual leaf each phase mounts and
/// with which exact owner input, the phase and bout guards, the story links,
/// the hold ordering of stream cards, disclosure writes and page actions, the
/// full-size history, the About and its source, All props and Details, the
/// owner's category and Show more controls, and the arrangement candidates.
/// The leaves' own rules are their own tests'. Nothing here claims a compile,
/// a rendered fit, a native runtime or a boxing case.
///
/// ARCHIVED values, all event 15318681 (mma), Ateba Gautier vs Roman Kopylov,
/// UFC 332, October 3 in Denver (October 4 UTC); raw feed status suspended,
/// completed_at null; verified start 2026-10-04T00:20:00Z
/// (`combatPregameEvidence.json`):
/// - Bain Luck blend, the approved headline and history anchor
///   (`SpecializedHeadlines.tsx` `CombatHeadline`/`CombatHeadlineFacts`,
///   sha256 faddd299…3b34; `CombatWinnerJourney.tsx`; `combatWinnerHistory.json`,
///   sha256 77a2ad55…7a40): the two-outcome aggregate for this verified
///   two-fighter market. Literal owner pairs from Design's export
///   `COMBAT-REFERENCE-PAIR-VALUES.json`: index 2254 (22:40Z), the baseline
///   2331 (00:18Z, Gautier 0.6724 / Kopylov 0.3276, shown 67.2% / 32.8% with
///   one shared clock) and every row of the around-start window 2332–2347
///   (00:20Z–00:37Z). Kopylov is the complement of the supplied Gautier
///   aggregate, NOT an independent provider quote; the pair is supplied, never
///   computed here or in the page.
/// - Winner contract 63254893 (`combatPregameEvidence.json`, Polymarket):
///   Gautier 238409895 0.685 and Kopylov 238409894 0.315, each last recorded
///   before start at 2026-10-03T23:27:48.847758Z (consensus); contract
///   results Kopylov Won, Gautier Lost (api_settlement). Two independently
///   quoted sides — kept as originals in All props and Details with their own
///   values, clock and identity, never relabelled as the blend.
/// - Method, knockout, round and duration originals, their pre-match values
///   and clocks and contract results: as in the accepted leaf tests
///   (`COMBAT-METHOD-RETAINED-CASES.json`, `COMBAT-FIGHTER-KO-RETAINED-CASES.json`,
///   `COMBAT-ROUND-RETAINED-CASES.json`, `COMBAT-DURATION-RETAINED-CASES.json`),
///   subsets only. The settlement-time 1.0 / 0.0 quotes are not inputs.
/// - Official result (`combatOfficialFinal.json`): Kopylov def. Gautier, TKO
///   (strikes), Round 1, 3:12; absoluteFinishAt null. No finish clock exists.
/// - Final story order and reasons: the reference's own captured result
///   (`combatMomentStories.ts`); the rule that produced them is not ported.
///
/// - Catalogue families (`combatCatalog.ts`, sha256 699a5e4a…b670): methods,
///   rounds, fighterKO, duration — presentation grouping keys only; the
///   reference's visible category row reads raw row categories (31 rows:
///   28 "other", 3 "totals"). The 31 count is the retained total.
///
/// CONSTRUCTED: every display string, PT clock word, provenance line, label,
/// tint, scope, id, action id, About sentence, stream status and reader
/// heading; the blend's display identities (source `bainluck-blend`, scope
/// `mma:15318681:winner:blend`, market token `15318681:winner`, outcome
/// tokens `gautier` / `kopylov`) — opaque presentation identities, never a
/// provider market id or provider selection; the category labels (All,
/// Winner, Finish method, Fighter rounds, Knockout chances, Fight length),
/// their intent ids, selection, count and Show more words; the whole DURING
/// snapshot (the owner admitting "during" at the retained 5:29 PM PT blend
/// row, with no round, fight state or in-fight chance — none is retained); the
/// recorded Details context; the source URL control's id; every
/// foreign-phase, foreign-bout, duplicate, colliding-id and no-Kopylov case.
@MainActor
final class CombatEventPagePresentation10868Tests: XCTestCase {

    // MARK: Identity

    private static let eventID = "15318681"
    /// The independent provider winner market, for All props and Details only.
    private static let winnerMarket = "63254893"
    private static let gautierSide = "238409895"
    private static let kopylovSide = "238409894"

    /// CONSTRUCTED opaque display identities for the owner's blend pair.
    /// Integration binding to a real owner identity remains owed.
    private static let blendScope = "mma:15318681:winner:blend"
    private static let blendSource = "bainluck-blend"
    private static let blendMarket = "15318681:winner"

    private static let gautierTint = Color(red: 0.0, green: 0.36, blue: 0.75)
    private static let kopylovTint = Color(red: 0.85, green: 0.33, blue: 0.10)

    /// The provider originals' own clock (story cards, All props, Details).
    private static let lateDetail = "Last recorded before start · Oct 3, 4:27 PM PT · Polymarket"
    /// The blend baseline's one shared clock, row 2331 at 00:18Z.
    private static let baselineClock = "Oct 3, 5:18 PM PT"
    private static let noCurrent = "No in-fight chance"
    private static let noKopylov = "Not supplied in this update"

    private static func ref(_ token: String) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: blendScope, source: blendSource, marketID: blendMarket, outcomeID: token)
    }

    // MARK: Headline (the owner's admitted blend pair)

    private struct Fighter {
        /// CONSTRUCTED outcome token.
        let token: String
        let name: String
        let compact: String
        let shape: FieldHeadlineKeyShape10868
        /// ARCHIVED blend row 2331, literal from Design's export.
        let probability: Double
        /// CONSTRUCTED owner text.
        let text: String
        let official: String
        let tint: Color
    }

    /// The reference's order: Gautier (home, circle), then Kopylov (away, diamond).
    private static let fighters = [
        Fighter(token: "gautier", name: "Ateba Gautier", compact: "Gautier", shape: .circle,
                probability: 0.6724, text: "67.2%", official: "Lost", tint: gautierTint),
        Fighter(token: "kopylov", name: "Roman Kopylov", compact: "Kopylov", shape: .diamond,
                probability: 0.3276, text: "32.8%", official: "Won", tint: kopylovTint),
    ]

    /// The clock only: source words stay out of the headline's chrome.
    private static func beforeReading(_ fighter: Fighter) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Last pre-match chance", value: .recorded(text: fighter.text, detail: baselineClock))
    }

    /// An owner that admits no Kopylov reading: its own words, nothing derived.
    private static let kopylovMissing = FieldChooserReading10868(label: "Last pre-match chance", value: .missing(noKopylov))

    /// The official physical result for the final, in the owner's words —
    /// never a chance, a race ordinal or a contract grade.
    private static func officialReading(_ fighter: Fighter) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Official result",
                                 value: .recorded(text: fighter.official, detail: "TKO (strikes) · Round 1, 3:12 · UFC"))
    }

    private static func headlineState(_ phase: CombatEventPagePhase10868) -> FieldHeadlineState10868 {
        switch phase {
        case .before:
            return FieldHeadlineState10868(figure: "Not started", unit: nil, caption: "Verified start",
                                           detail: "Oct 3, 5:20 PM PT",
                                           spoken: "Not started. Verified start Oct 3, 5:20 PM PT.", progress: nil)
        case .during:
            // CONSTRUCTED: no round or fight state is retained, so none is claimed.
            return FieldHeadlineState10868(figure: "Fight under way", unit: nil, caption: "Round not reported",
                                           detail: nil, spoken: "Fight under way. Round not reported.", progress: nil)
        case .final:
            return FieldHeadlineState10868(figure: "Kopylov won", unit: nil, caption: "TKO (strikes) · Round 1, 3:12",
                                           detail: "Official UFC result · Oct 3, 2026",
                                           spoken: "Kopylov won by TKO (strikes) at 3:12 of Round 1. Official UFC result, October 3, 2026.",
                                           progress: nil)
        }
    }

    /// The finishes ride along in every phase; only the final reads them.
    /// `kopylovAdmitted: false` is an owner that supplies no Kopylov reading.
    private static func headline(_ phase: CombatEventPagePhase10868,
                                 headlinePhase: FieldOutlookPhase10868? = nil,
                                 kopylovAdmitted: Bool = true) -> FieldHeadlineInput10868 {
        func admitted(_ fighter: Fighter) -> Bool { kopylovAdmitted || fighter.token != "kopylov" }
        return FieldHeadlineInput10868(
            scope: blendScope,
            catalogue: fighters.map { fighter in
                FieldChooserOriginal10868(
                    ref: ref(fighter.token), name: fighter.name,
                    plan: .single(admitted(fighter) ? beforeReading(fighter) : kopylovMissing),
                    preview: FieldChooserPreview10868(history: nil, absence: "History in the chart"),
                    movement: nil, clock: admitted(fighter) ? baselineClock : nil, result: nil,
                    browseStatus: admitted(fighter) ? "Last pre-match chance" : noKopylov, accent: fighter.tint)
            },
            displayed: fighters.map {
                FieldHeadlineSlot10868(ref: ref($0.token), name: $0.name, compactName: $0.compact, keyShape: $0.shape)
            },
            pairs: fighters.map {
                FieldMovementPair10868(
                    ref: ref($0.token),
                    before: admitted($0) ? FieldMovementObservation10868(probability: $0.probability, reading: beforeReading($0)) : nil,
                    later: nil, movement: nil, observation: nil)
            },
            finishes: fighters.map { FieldFinishPlace10868(ref: ref($0.token), reading: officialReading($0)) },
            state: headlineState(phase),
            phase: headlinePhase ?? CombatEventPageModel10868.headlinePhase(phase),
            copy: FieldHeadlineCopy10868(
                eyebrow: "UFC 332 · Middleweight", title: "Ateba Gautier · Roman Kopylov",
                graphicLabel: "Pre-match and in-fight win chances", beforeLabel: "Last pre-match chance",
                recordedLabel: "In-fight win", beforeUnavailable: "Not recorded", recordedUnavailable: noCurrent,
                finishLabel: "Official result", finishUnavailable: "Result not reported",
                empty: "No fighters in this update", aboutLabel: "About this fight",
                aboutHint: "Opens pre-match timing, the official result and sources",
                openHint: "Opens this fighter’s history"),
            unavailableWords: "Fighter unavailable in this update")
    }

    private static func figures(_ input: FieldHeadlineInput10868) -> [[String]] {
        FieldHeadlineModel10868(input).competitors.map { $0.metrics.compactMap(FieldChaseModel10868.figure) }
    }

    // MARK: History (the owner's two blend traces)

    /// One ARCHIVED blend row: the original timestamp, the owner's position
    /// in minutes from the verified start, and the owner's literal pair.
    private struct BlendRow {
        let index: Int
        let at: String
        let x: Double
        let gautier: Double
        /// The supplied complement — a literal, never computed here.
        let kopylov: Double
    }

    /// Literal from `COMBAT-REFERENCE-PAIR-VALUES.json`.
    private static let blend: [BlendRow] = [
        BlendRow(index: 2254, at: "2026-10-03T22:40:00+00:00", x: -100, gautier: 0.6729, kopylov: 0.3271),
        BlendRow(index: 2331, at: "2026-10-04T00:18:00+00:00", x: -2, gautier: 0.6724, kopylov: 0.3276),
        BlendRow(index: 2332, at: "2026-10-04T00:20:00+00:00", x: 0, gautier: 0.6724, kopylov: 0.3276),
        BlendRow(index: 2333, at: "2026-10-04T00:21:00+00:00", x: 1, gautier: 0.6724, kopylov: 0.3276),
        BlendRow(index: 2334, at: "2026-10-04T00:22:00+00:00", x: 2, gautier: 0.6767, kopylov: 0.3233),
        BlendRow(index: 2335, at: "2026-10-04T00:23:00+00:00", x: 3, gautier: 0.6767, kopylov: 0.3233),
        BlendRow(index: 2336, at: "2026-10-04T00:24:00+00:00", x: 4, gautier: 0.6806, kopylov: 0.3194),
        BlendRow(index: 2337, at: "2026-10-04T00:25:00+00:00", x: 5, gautier: 0.6757, kopylov: 0.3243),
        BlendRow(index: 2338, at: "2026-10-04T00:26:00+00:00", x: 6, gautier: 0.7485, kopylov: 0.2515),
        BlendRow(index: 2339, at: "2026-10-04T00:27:00+00:00", x: 7, gautier: 0.683, kopylov: 0.317),
        BlendRow(index: 2340, at: "2026-10-04T00:28:00+00:00", x: 8, gautier: 0.5835, kopylov: 0.4165),
        BlendRow(index: 2341, at: "2026-10-04T00:29:00+00:00", x: 9, gautier: 0.5356, kopylov: 0.4644),
        BlendRow(index: 2342, at: "2026-10-04T00:31:00+00:00", x: 11, gautier: 0.5356, kopylov: 0.4644),
        BlendRow(index: 2343, at: "2026-10-04T00:33:00+00:00", x: 13, gautier: 0.5356, kopylov: 0.4644),
        BlendRow(index: 2344, at: "2026-10-04T00:34:00+00:00", x: 14, gautier: 0.5356, kopylov: 0.4644),
        BlendRow(index: 2345, at: "2026-10-04T00:35:00+00:00", x: 15, gautier: 0.5356, kopylov: 0.4644),
        BlendRow(index: 2346, at: "2026-10-04T00:36:00+00:00", x: 16, gautier: 0.6801, kopylov: 0.3199),
        BlendRow(index: 2347, at: "2026-10-04T00:37:00+00:00", x: 17, gautier: 0.5713, kopylov: 0.4287),
    ]

    private enum Trace: String {
        case gautier
        case kopylov
    }

    /// The trace's own literal value and its own point identity; both traces
    /// share the row's position and hollow/filled role.
    private static func point(_ row: BlendRow, _ trace: Trace) -> FieldHistoryPoint10868 {
        FieldHistoryPoint10868(id: "blend.\(row.index).\(trace.rawValue)", x: row.x,
                               probability: trace == .gautier ? row.gautier : row.kopylov,
                               style: row.x < 0 ? .hollow : .filled)
    }

    /// Before: the "Pre-match" window, reduced to two rows — the omitted span
    /// between them stays two runs. During: the around-start window through the
    /// 5:29 PM PT row. Final: the whole around-start window, to its last row.
    /// Both traces break at the same places.
    private static func runs(_ phase: CombatEventPagePhase10868, _ trace: Trace) -> [FieldHistoryRun10868] {
        let name = trace.rawValue
        switch phase {
        case .before:
            return [FieldHistoryRun10868(id: "run.2254.\(name)", points: [point(blend[0], trace)]),
                    FieldHistoryRun10868(id: "run.2331.\(name)", points: [point(blend[1], trace)])]
        case .during:
            return [FieldHistoryRun10868(id: "run.623.\(name)", points: blend[1...11].map { point($0, trace) })]
        case .final:
            return [FieldHistoryRun10868(id: "run.623.\(name)", points: blend[1...].map { point($0, trace) })]
        }
    }

    private static func lastPoint(_ phase: CombatEventPagePhase10868, _ trace: Trace) -> FieldHistoryPoint10868 {
        runs(phase, trace).last!.points.last!
    }

    private static let complementWords = "Kopylov is the complement of the supplied Gautier aggregate, not an independent provider quote."

    private static func xTicks(_ phase: CombatEventPagePhase10868) -> [FieldHistoryTick10868] {
        switch phase {
        case .before: [FieldHistoryTick10868(value: -100, lines: ["3:40 PM"]), FieldHistoryTick10868(value: -2, lines: ["5:18 PM"])]
        case .during: [FieldHistoryTick10868(value: -2, lines: ["5:18 PM"]), FieldHistoryTick10868(value: 9, lines: ["5:29 PM"])]
        case .final: [FieldHistoryTick10868(value: -2, lines: ["5:18 PM"]), FieldHistoryTick10868(value: 17, lines: ["5:37 PM"])]
        }
    }

    private static func action(_ id: String, _ label: String, spoken: String? = nil) -> FieldHistoryAction10868 {
        FieldHistoryAction10868(id: id, label: label, spokenLabel: spoken, isAvailable: true)
    }

    /// `kopylovAdmitted: false` is an owner that supplies no Kopylov series:
    /// its absence words only, and no line derived from Gautier's.
    private static func history(_ phase: CombatEventPagePhase10868, kopylovAdmitted: Bool = true) -> FieldHistoryInput10868 {
        let lastG = lastPoint(phase, .gautier)
        let lastK = lastPoint(phase, .kopylov)
        let lastWords = phase == .during ? "Oct 3, 5:29 PM PT" : "Oct 3, 5:37 PM PT"
        // Literal owner figures for rows 2341 (during) and 2347 (final).
        let lastFigures = phase == .during ? ("53.6%", "46.4%") : ("57.1%", "42.9%")
        let gautier = FieldHistorySeries10868(
            id: "gautier", name: "Ateba Gautier", shape: .circle, tint: gautierTint,
            runs: runs(phase, .gautier), links: [], labelPointID: lastG.id,
            before: .observation(pointID: "blend.2331.gautier", figure: "67.2%",
                                 provenance: "\(baselineClock) · Bain Luck blend · supplied aggregate"),
            recorded: phase == .before
                ? .absent(words: "Not started")
                : .observation(pointID: lastG.id, figure: lastFigures.0, provenance: "Recorded after start · \(lastWords)"),
            absentWords: nil, choose: nil)
        let kopylov = kopylovAdmitted
            ? FieldHistorySeries10868(
                id: "kopylov", name: "Roman Kopylov", shape: .diamond, tint: kopylovTint,
                runs: runs(phase, .kopylov), links: [], labelPointID: lastK.id,
                before: .observation(pointID: "blend.2331.kopylov", figure: "32.8%",
                                     provenance: "\(baselineClock) · Bain Luck blend · complement of the aggregate"),
                recorded: phase == .before
                    ? .absent(words: "Not started")
                    : .observation(pointID: lastK.id, figure: lastFigures.1, provenance: "Recorded after start · \(lastWords)"),
                absentWords: nil, choose: nil)
            : FieldHistorySeries10868(
                id: "kopylov", name: "Roman Kopylov", shape: .diamond, tint: kopylovTint,
                runs: [], links: [], labelPointID: nil,
                before: .absent(words: noKopylov), recorded: .absent(words: noKopylov),
                absentWords: "No Kopylov history in this update", choose: nil)
        let window = ["around": "Around start", "pregame": "Pre-match", "all": "All"]
        let selected = phase == .before ? "pregame" : "around"
        return FieldHistoryInput10868(
            title: "Win probability history", caption: "Bain Luck blend · archived",
            series: [gautier, kopylov], selection: .none,
            domain: FieldHistoryDomain10868(lower: xTicks(phase)[0].value, upper: xTicks(phase)[1].value),
            ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 0.5, lines: ["50%"]),
                     FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: xTicks(phase),
            // The recorded start, only where the window spans it; no finish guide.
            guides: phase == .before ? [] : [FieldHistoryGuide10868(id: "start", x: 0, label: "Start")],
            breaks: [],
            readout: phase == .before
                ? .singleBefore(label: "Last pre-match")
                : .beforeAndInspected(beforeLabel: "Last pre-match", inspectedLabel: "Recorded after start"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: pre-match", filled: "Filled: after start"),
            comparisonExplanation: nil,
            notes: kopylovAdmitted
                ? ["Recorded two-outcome Bain Luck blend · \(complementWords) · times in PT"]
                : ["Bain Luck blend · times in PT"],
            summary: kopylovAdmitted
                ? "Gautier circles and Kopylov diamonds trace the recorded two-outcome Bain Luck blend on a zero to 100% scale. \(complementWords) Hollow marks are pre-match, filled marks after start. Gaps stay blank."
                : "Gautier’s recorded win chance on a zero to 100% scale. No Kopylov history is supplied in this update. Hollow marks are pre-match, filled marks after start. Gaps stay blank.",
            plotHeight: 220,
            unboundReadingWords: "Unavailable", plotUnavailableWords: "History unavailable",
            windows: FieldHistoryWindows10868(
                groupLabel: "Probability history window",
                choices: ["around", "pregame", "all"].map {
                    FieldHistoryWindowChoice10868(action: action("window.\($0)", window[$0]!), isSelected: $0 == selected)
                }),
            scale: nil, moreOriginals: nil, details: nil,
            expand: action("history.expand", "Expand", spoken: "Expand fight win probability history"),
            inspect: nil,
            previous: action("history.previous", "‹", spoken: "Previous combat observation"),
            next: action("history.next", "›", spoken: "Next combat observation"),
            inspection: phase == .before ? nil : FieldHistoryInspection10868(
                x: lastG.x, caption: "Recorded after start · \(lastWords)",
                selections: ["gautier": .point(id: lastG.id, spoken: lastFigures.0),
                             "kopylov": kopylovAdmitted ? .point(id: lastK.id, spoken: lastFigures.1) : .absent(words: noKopylov)],
                choices: [], choicePresentation: .slider(label: "Combat recorded observation"), note: nil))
    }

    // MARK: Story leaves (subsets of the accepted leaf fixtures)

    private static func methodObs(_ p: Double, _ text: String, _ time: String = "4:27 PM PT") -> CombatMethodObservation10868 {
        CombatMethodObservation10868(probability: p, text: text, timeText: time,
                                     detail: "Last recorded before start · Oct 3, \(time) · Polymarket")
    }

    private static func methodOriginal(_ id: String, _ market: String, _ side: String, _ p: Double, _ text: String,
                                       _ result: String, time: String = "4:27 PM PT") -> CombatMethodOriginal10868 {
        CombatMethodOriginal10868(id: id, marketID: market, label: side, before: methodObs(p, text, time),
                                  beforeMissing: "Not recorded before start", current: .unavailable(noCurrent),
                                  result: result == "Won" ? .won("Won") : .lost("Lost"))
    }

    private static let officialLine = "Roman Kopylov def. Ateba Gautier · TKO (strikes) · Round 1, 3:12"
    private static let officialDetail = "UFC results page, captured Oct 13 · finish clock not recorded"

    /// Owner-admitted official context: before (hidden by the leaf) and at the
    /// final. Never during — no result is admitted while the fight is on.
    private static func admitsOfficial(_ phase: CombatEventPagePhase10868) -> Bool { phase != .during }

    private static func methods(_ phase: CombatEventPagePhase10868, as leafPhase: CombatMethodPhase10868? = nil,
                                eventID: String = CombatEventPagePresentation10868Tests.eventID) -> CombatMethodInput10868 {
        CombatMethodInput10868(
            phase: leafPhase ?? CombatEventPageModel10868.methodPhase(phase), eventID: eventID,
            eyebrow: "Polymarket · contract results",
            title: phase == .final ? "How the bout ended" : "How could the fight end?",
            caption: "Pre-match chances · select a tile for its quote time",
            methods: [
                CombatMethod10868(id: "ko-tko", label: "KO / TKO", question: "Will the fight be won by KO or TKO?",
                                  originals: [methodOriginal("240262496", "63786874", "Yes", 0.55, "55%", "Won"),
                                              methodOriginal("240262497", "63786874", "No", 0.45, "45%", "Lost")],
                                  overviewOriginalID: "240262496"),
                CombatMethod10868(id: "submission", label: "Submission", question: "Will the fight be won by submission?",
                                  originals: [methodOriginal("239735845", "63634393", "Yes", 0.105, "10.5%", "Lost"),
                                              methodOriginal("239735846", "63634393", "No", 0.895, "89.5%", "Won")],
                                  overviewOriginalID: "239735845"),
                CombatMethod10868(id: "decision-draw", label: "Decision / draw", question: "Will the fight end in a decision or draw?",
                                  originals: [methodOriginal("240262514", "63786883", "Yes", 0.51, "51%", "Lost", time: "1:03 AM PT"),
                                              methodOriginal("240262515", "63786883", "No", 0.49, "49%", "Won", time: "1:03 AM PT")],
                                  overviewOriginalID: "240262514"),
            ],
            selectedMethodID: phase == .final ? "ko-tko" : nil,
            selectedOriginalID: phase == .final ? "240262496" : nil,
            actual: admitsOfficial(phase) ? CombatMethodActual10868(title: "Official bout result", lines: [officialLine],
                                                                   accessibilityDetail: officialDetail) : nil,
            timing: phase == .final ? CombatMethodTiming10868(originalID: "240262496", title: "Times",
                                                              lines: ["Pre-match recorded Oct 3, 4:27 PM PT"]) : nil)
    }

    private static let knockoutCopy = CombatMethodCopy10868(
        chooseInstruction: "Choose a fighter or side to compare.",
        methodUnavailable: "Selected fighter unavailable in this update.",
        methodSelectedTag: "Fighter selected")

    private static func knockout(_ phase: CombatEventPagePhase10868) -> CombatMethodInput10868 {
        CombatMethodInput10868(
            phase: CombatEventPageModel10868.methodPhase(phase), eventID: eventID,
            eyebrow: "Polymarket · contract results",
            title: phase == .final ? "The knockout few expected" : "Who wins by knockout?",
            caption: "Pre-match chances · select a tile for its quote time",
            methods: [
                CombatMethod10868(id: "ko-kopylov", label: "Roman Kopylov", question: "Will Roman Kopylov win by KO or TKO?",
                                  originals: [methodOriginal("240654996", "63900810", "Yes", 0.125, "12.5%", "Won"),
                                              methodOriginal("240654997", "63900810", "No", 0.875, "87.5%", "Lost")],
                                  overviewOriginalID: "240654996"),
                CombatMethod10868(id: "ko-gautier", label: "Ateba Gautier", question: "Will Ateba Gautier win by KO or TKO?",
                                  originals: [methodOriginal("240262498", "63786875", "Yes", 0.4, "40%", "Lost"),
                                              methodOriginal("240262499", "63786875", "No", 0.6, "60%", "Won")],
                                  overviewOriginalID: "240262498"),
            ],
            selectedMethodID: phase == .final ? "ko-kopylov" : nil,
            selectedOriginalID: phase == .final ? "240654996" : nil,
            actual: admitsOfficial(phase) ? CombatMethodActual10868(title: "Official bout result", lines: [officialLine],
                                                                   accessibilityDetail: officialDetail) : nil,
            timing: nil, copy: knockoutCopy)
    }

    private static func roundOriginal(_ id: String, _ market: String, _ side: String, _ p: Double, _ text: String,
                                      _ result: String, early: Bool = false) -> CombatRoundOriginal10868 {
        let time = early ? "9:42 AM PT" : "4:27 PM PT"
        return CombatRoundOriginal10868(
            id: id, marketID: market, label: side,
            before: CombatRoundObservation10868(probability: p, text: text, detail: "Last recorded before start · Oct 3, \(time) · Polymarket"),
            beforeMissing: "Not recorded before start", current: .unavailable(noCurrent),
            result: result == "Won" ? .won("Won") : .lost("Lost"), resultDetail: nil)
    }

    private static func roundSlot(_ id: String, _ label: String, _ market: String, _ question: String,
                                  _ originals: [CombatRoundOriginal10868]) -> CombatRoundSlot10868 {
        CombatRoundSlot10868(id: id, label: label, state: .market(CombatRoundMarket10868(
            id: market, question: question, originals: originals, overviewOriginalID: originals.first?.id)))
    }

    private static func rounds(_ phase: CombatEventPagePhase10868,
                               eventID: String = CombatEventPagePresentation10868Tests.eventID) -> CombatRoundInput10868 {
        CombatRoundInput10868(
            phase: CombatEventPageModel10868.roundPhase(phase), eventID: eventID,
            eyebrow: "Polymarket · contract results", title: "Which round for each fighter?",
            caption: "Pre-match chance · tracks run from 0 to 100%",
            groups: [
                CombatRoundGroup10868(id: "kopylov", label: "Roman Kopylov", slots: [
                    roundSlot("kopylov-r1", "Round 1", "63900818", "Will Roman Kopylov win in Round 1?",
                              [roundOriginal("240655012", "63900818", "Yes", 0.11, "11%", "Won"),
                               roundOriginal("240655013", "63900818", "No", 0.89, "89%", "Lost")]),
                    roundSlot("kopylov-r2", "Round 2", "63900819", "Will Roman Kopylov win in Round 2?",
                              [roundOriginal("240655014", "63900819", "Yes", 0.1, "10%", "Lost"),
                               roundOriginal("240655015", "63900819", "No", 0.9, "90%", "Won")]),
                ]),
                CombatRoundGroup10868(id: "gautier", label: "Ateba Gautier", slots: [
                    roundSlot("gautier-r1", "Round 1", "63786882", "Will Ateba Gautier win in Round 1?",
                              [roundOriginal("240262512", "63786882", "Yes", 0.205, "20.5%", "Lost", early: true),
                               roundOriginal("240262513", "63786882", "No", 0.795, "79.5%", "Won", early: true)]),
                    CombatRoundSlot10868(id: "gautier-r2", label: "Round 2", state: .noCapturedProp("No captured prop")),
                ]),
            ],
            selectedSlotID: phase == .final ? "kopylov-r1" : nil,
            selectedOriginalID: phase == .final ? "240655012" : nil,
            finish: admitsOfficial(phase) ? CombatRoundFinish10868(title: "Official bout result", lines: [officialLine],
                                                                  accessibilityDetail: officialDetail) : nil,
            timing: nil)
    }

    private static func durationOriginal(_ id: String, _ market: String, _ side: String, window: CombatDurationWindow10868,
                                         _ p: Double, _ text: String, _ result: CombatDurationResult10868,
                                         detail: String? = nil) -> CombatDurationOriginal10868 {
        CombatDurationOriginal10868(
            id: id, marketID: market, label: side, window: window, windowMissing: "Time window unavailable",
            before: CombatDurationObservation10868(probability: p, text: text, timeText: "4:27 PM PT", detail: lateDetail),
            beforeMissing: "Not recorded before start", current: .unavailable(noCurrent), result: result, resultDetail: detail)
    }

    private static let unconfirmedDetail = "The game-prop capture and the market detail disagree on this side."

    private static func duration(_ phase: CombatEventPagePhase10868, as leafPhase: CombatDurationPhase10868? = nil) -> CombatDurationInput10868 {
        CombatDurationInput10868(
            phase: leafPhase ?? CombatEventPageModel10868.durationPhase(phase), eventID: eventID,
            eyebrow: "Polymarket · contract results", title: "How long could the fight last?",
            caption: "Pre-match chances · select a tile for its quote time",
            segments: [CombatDurationSegment10868(id: "r1", shortLabel: "R1", spokenLabel: "Round 1"),
                       CombatDurationSegment10868(id: "r2", shortLabel: "R2", spokenLabel: "Round 2"),
                       CombatDurationSegment10868(id: "r3", shortLabel: "R3", spokenLabel: "Round 3")],
            markets: [
                CombatDurationMarket10868(id: "63254895", label: "Under 1½ rounds", question: "O/U 1.5 Rounds", originals: [
                    durationOriginal("238409899", "63254895", "Under",
                                     window: CombatDurationWindow10868(label: "Under 1½ rounds", start: 0, end: 1.5, finalBell: nil),
                                     0.375, "37.5%", .unconfirmed("Result unconfirmed"), detail: unconfirmedDetail),
                ], overviewOriginalID: "238409899"),
                CombatDurationMarket10868(id: "63786880", label: "Before Round 2", question: "Will the fight end before Round 2?", originals: [
                    durationOriginal("240262508", "63786880", "Yes",
                                     window: CombatDurationWindow10868(label: "Before Round 2", start: 0, end: 1, finalBell: nil),
                                     0.325, "32.5%", .won("Won")),
                    durationOriginal("240262509", "63786880", "No",
                                     window: CombatDurationWindow10868(label: "Round 2 or later", start: 1, end: 3, finalBell: nil),
                                     0.675, "67.5%", .lost("Lost")),
                ], overviewOriginalID: "240262508"),
                CombatDurationMarket10868(id: "63254894", label: "Go the distance", question: "Fight to Go the Distance?", originals: [
                    durationOriginal("238409896", "63254894", "Yes",
                                     window: CombatDurationWindow10868(label: "Reaches final bell", start: 3, end: 3,
                                                                       finalBell: .included("Includes the final bell")),
                                     0.37, "37%", .lost("Lost")),
                    durationOriginal("238409897", "63254894", "No",
                                     window: CombatDurationWindow10868(label: "Ends before final bell", start: 0, end: 3,
                                                                       finalBell: .excluded("Ends before the final bell")),
                                     0.63, "63%", .won("Won")),
                ], overviewOriginalID: "238409896"),
            ],
            selectedMarketID: phase == .final ? "63786880" : nil,
            selectedOriginalID: phase == .final ? "240262508" : nil,
            // No round in progress is retained, so none is observed.
            observed: nil,
            finish: admitsOfficial(phase) ? CombatDurationFinish10868(
                segmentID: "r1", markerWords: "Finished in Round 1", title: "Official bout result",
                lines: [officialLine], accessibilityDetail: officialDetail) : nil,
            timing: nil)
    }

    // MARK: Stream, About and page

    private static func streamScope(_ phase: CombatEventPagePhase10868) -> String { "combat:15318681:\(phase.rawValue)" }

    private static let cardNames = ["methods": "Finish method", "rounds": "Fighter rounds",
                                    "fighterKO": "Knockout chances", "duration": "Fight length"]

    /// The owner's order: the reference's admitted order before a result, its
    /// captured final ranking at the final.
    private static func streamOrder(_ phase: CombatEventPagePhase10868) -> [String] {
        phase == .final ? ["fighterKO", "rounds", "duration", "methods"] : ["methods", "rounds", "fighterKO", "duration"]
    }

    /// `showing` is the owner's displayed primary and companion after it
    /// browsed on; nil shows the first two in its order.
    private static func stream(_ phase: CombatEventPagePhase10868, wide: Bool = false,
                               showing: (String, String)? = nil) -> StoryStreamPresentation10868 {
        let scope = streamScope(phase)
        let order = streamOrder(phase)
        let shown = showing ?? (order[0], order[1])
        let position = (order.firstIndex(of: shown.0) ?? 0) + 1
        func ref(_ id: String) -> StoryStreamPresentation10868.CardRef { .init(scope: scope, id: id) }
        return StoryStreamPresentation10868(
            scope: scope, eyebrow: nil, heading: phase == .final ? "After the fight" : "Fight stories",
            cards: order.map { StoryStreamPresentation10868.Card(id: $0, name: cardNames[$0]!) },
            primary: ref(shown.0), companion: ref(shown.1), companionLabel: "Next", wide: wide,
            position: "\(position) of 4",
            basis: phase == .final ? "Recorded final · ranked from the bout result" : "Recorded fight · captured cards",
            previous: nil, next: ref(shown.1))
    }

    private static func stories(_ phase: CombatEventPagePhase10868) -> [CombatEventPageStory10868] {
        let final = phase == .final
        return [
            CombatEventPageStory10868(cardID: "methods", card: .methods,
                                      reason: final ? "A KO/TKO finish for either fighter had a 55% pre-match chance." : nil),
            CombatEventPageStory10868(cardID: "rounds", card: .rounds,
                                      reason: final ? "Kopylov winning in Round 1 had an 11% pre-match chance." : nil),
            CombatEventPageStory10868(cardID: "fighterKO", card: .knockout,
                                      reason: final ? "Kopylov’s KO/TKO win had a 12.5% pre-match chance." : nil),
            CombatEventPageStory10868(cardID: "duration", card: .duration,
                                      reason: final ? "Ending before Round 2 had a 32.5% pre-match chance." : nil),
        ]
    }

    private static func readerHeader(_ phase: CombatEventPagePhase10868) -> CombatEventPageReaderHeader10868 {
        switch phase {
        case .before: CombatEventPageReaderHeader10868(title: "Gautier · Kopylov · Before the fight", state: "Verified start Oct 3, 5:20 PM PT")
        case .during: CombatEventPageReaderHeader10868(title: "Gautier · Kopylov · Fight under way", state: "Round not reported")
        case .final: CombatEventPageReaderHeader10868(title: "Kopylov won · TKO · R1, 3:12",
                                                      state: "Last pre-match · Gautier 67.2% · Kopylov 32.8%")
        }
    }

    private static let ufcSource = CombatEventPageSource10868(
        id: "ufc-result", label: "Official UFC result",
        url: URL(string: "https://www.ufc.com/news/ufc-332-silva-vs-wang-results")!)

    /// The owner's About for the phase: the official result only once admitted.
    private static func about(_ phase: CombatEventPagePhase10868) -> CombatEventPageAbout10868 {
        let pregame = CombatEventPageAboutSection10868(title: "Pre-match chances", paragraphs: [
            "Gautier 67.2% and Kopylov 32.8% are the last Bain Luck blend observation before the verified start, Oct 3, 5:18 PM PT (2026-10-04T00:18:00Z).",
            complementWords,
            "The original Polymarket winner market separately quoted Gautier 68.5% and Kopylov 31.5%, last recorded Oct 3, 4:27 PM PT. It stays in All props with its own time.",
        ])
        let state = CombatEventPageAboutSection10868(title: "Fight state", paragraphs: [
            "The round and the result are not reported in this update. No in-fight chance is recorded.",
        ])
        let official = CombatEventPageAboutSection10868(title: "Official bout result", paragraphs: [
            "Roman Kopylov defeated Ateba Gautier by TKO (strikes) at 3:12 of Round 1. UFC 332 · October 3, 2026.",
            "3:12 is elapsed time in Round 1, not a clock time. The exact finish time is not recorded, and the chart adds no final point.",
            "The archived feed still listed this bout as suspended. Contract results are reported separately.",
        ], source: ufcSource)
        let history = CombatEventPageAboutSection10868(title: "History and source", paragraphs: [
            "The chart is the recorded two-outcome Bain Luck blend. Gautier’s line is the supplied aggregate; Kopylov’s line is its complement, not an independent provider quote.",
            "Gaps over five minutes stay blank. After-start values do not establish a round, finish time or result. Times are Pacific.",
        ])
        switch phase {
        case .before: return CombatEventPageAbout10868(title: "About this fight", sections: [pregame, history])
        case .during: return CombatEventPageAbout10868(title: "About this fight", sections: [pregame, state, history])
        case .final: return CombatEventPageAbout10868(title: "About this fight", sections: [pregame, official, history])
        }
    }

    private static let copy = CombatEventPageCopy10868(
        storiesLabel: "Fight stories",
        storyUnavailable: "This story isn’t available for this moment. Every original is still in All props.",
        headlineUnavailable: "Fight headline unavailable for this moment",
        allPropsLabel: "All 31 original props")

    /// One coherent snapshot. Each leaf gets its own input; the guards, not the
    /// fixture, hide a foreign one.
    private static func page(_ phase: CombatEventPagePhase10868, wide: Bool = false,
                             headline: FieldHeadlineInput10868? = nil,
                             history: FieldHistoryInput10868? = nil,
                             methods: CombatMethodInput10868?? = nil,
                             rounds: CombatRoundInput10868?? = nil,
                             knockout: CombatMethodInput10868?? = nil,
                             duration: CombatDurationInput10868?? = nil,
                             stream: StoryStreamPresentation10868?? = nil,
                             stories: [CombatEventPageStory10868]? = nil,
                             about: CombatEventPageAbout10868?? = nil) -> CombatEventPageInput10868 {
        CombatEventPageInput10868(
            phase: phase, eventID: eventID, reader: readerHeader(phase),
            headline: headline ?? Self.headline(phase), history: history ?? Self.history(phase),
            methods: methods ?? Self.methods(phase), rounds: rounds ?? Self.rounds(phase),
            knockout: knockout ?? Self.knockout(phase), duration: duration ?? Self.duration(phase),
            stream: stream ?? Self.stream(phase, wide: wide), stories: stories ?? Self.stories(phase),
            about: about ?? Self.about(phase), copy: copy)
    }

    private static func activation(_ stream: StoryStreamPresentation10868, _ id: String,
                                   log: @escaping (String) -> Void) -> StoryStreamCardActivation10868 {
        let resolved = stream.resolve(reduceMotion: false, actionable: true)
        let ref = StoryStreamPresentation10868.CardRef(scope: stream.scope, id: id)
        return StoryStreamCardActivation10868(card: ref, intents: stream.activationIntents(for: ref, resolved: resolved)) { intent in
            if case .interaction(_, let card) = intent { log("hold:\(card?.id ?? "-")") } else { log("other") }
        }
    }

    /// A host-owned disclosure flag whose reads and writes are logged.
    private final class Flag {
        var value = false
    }

    private static func binding(_ flag: Flag, _ name: String, log: @escaping (String) -> Void) -> Binding<Bool> {
        Binding(get: { flag.value }, set: { flag.value = $0; log("write:\(name):\($0)") })
    }

    // MARK: Phases

    func testBeforeTheFightBothFightersLeadWithTheirOwnPreMatchChancesAndEveryLaterInputStaysHidden() {
        let input = Self.page(.before)
        let view = CombatEventPagePresentation10868(input: input)
        XCTAssertEqual(view.mode, .page)
        XCTAssertEqual(view.headlineContent()?.input, input.headline)
        XCTAssertEqual(view.historyContent(reader: false).input, input.history)
        XCTAssertEqual(view.methodsContent()?.input, input.methods)
        XCTAssertEqual(view.roundsContent()?.input, input.rounds)
        XCTAssertEqual(view.knockoutContent()?.input, input.knockout)
        XCTAssertEqual(view.durationContent()?.input, input.duration)

        // The owner's blend pair at its baseline, equal standing, one shared
        // clock, hollow keys; the official result rides on the input and is
        // not read before the fight.
        XCTAssertEqual(Self.figures(input.headline), [["67.2%"], ["32.8%"]])
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertTrue(headline.keyIsHollow)
        XCTAssertNil(headline.progress)
        XCTAssertEqual(headline.competitors.map(\.slot.name), ["Ateba Gautier", "Roman Kopylov"])
        XCTAssertEqual(headline.competitors.map(\.slot.keyShape), [.circle, .diamond])
        XCTAssertFalse(input.headline.finishes.isEmpty)
        XCTAssertEqual(Self.fighters.map(\.probability), [Self.blend[1].gautier, Self.blend[1].kopylov],
                       "the owner's literal pair at row 2331, never derived here")

        // Each card shows only pre-match chances; the official context it was
        // handed stays hidden by its own leaf.
        let methods = input.methods!
        XCTAssertNil(methods.visibleActual)
        XCTAssertNil(methods.currentReading(methods.methods[0].originals[0]))
        XCTAssertNil(methods.result(methods.methods[0].originals[0]))
        XCTAssertEqual(methods.beforeReading(methods.methods[0].originals[0]), .value(Self.methodObs(0.55, "55%")))
        XCTAssertNil(input.rounds!.visibleFinish)
        XCTAssertNil(input.duration!.visibleFinish)
        XCTAssertNil(input.knockout!.visibleActual)

        // The pre-match window holds two retained rows on both traces with the
        // omitted span between them as two runs, no start guide and no point
        // after start.
        let history = input.history
        XCTAssertEqual(history.series[0].runs.map { $0.points.map(\.id) }, [["blend.2254.gautier"], ["blend.2331.gautier"]])
        XCTAssertEqual(history.series[1].runs.map { $0.points.map(\.id) }, [["blend.2254.kopylov"], ["blend.2331.kopylov"]])
        XCTAssertEqual(history.series[0].runs.flatMap(\.points).map(\.probability), [0.6729, 0.6724])
        XCTAssertEqual(history.series[1].runs.flatMap(\.points).map(\.probability), [0.3271, 0.3276])
        XCTAssertTrue(history.series.flatMap(\.runs).flatMap(\.points).allSatisfy { $0.x < 0 && $0.style == .hollow })
        XCTAssertTrue(history.guides.isEmpty)

        // Four cards, in the owner's order, with no reasons before a result.
        XCTAssertEqual(input.stream?.cards.map(\.id), ["methods", "rounds", "fighterKO", "duration"])
        XCTAssertEqual(["methods", "rounds", "fighterKO", "duration"].compactMap { CombatEventPageModel10868(input).storyCard($0) },
                       [.methods, .rounds, .knockout, .duration])
        XCTAssertTrue(input.stories.allSatisfy { $0.reason == nil })
    }

    func testDuringTheFightWithNoRetainedInFightEvidenceEveryLaterChanceStaysWordsAndNothingIsInvented() {
        // CONSTRUCTED phase control: the owner admits "during" at the 5:29 PM PT row.
        let input = Self.page(.during)
        let view = CombatEventPagePresentation10868(input: input)
        XCTAssertNotNil(view.headlineContent())
        XCTAssertNotNil(view.methodsContent())
        XCTAssertNotNil(view.roundsContent())
        XCTAssertNotNil(view.knockoutContent())
        XCTAssertNotNil(view.durationContent())

        // The pre-match baseline stays; the in-fight slot is the owner's words,
        // not a figure — an after-start archived point is not a current chance.
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(Self.figures(input.headline), [["67.2%"], ["32.8%"]])
        for competitor in headline.competitors {
            XCTAssertEqual(competitor.metrics.count, 2)
            XCTAssertEqual(competitor.metrics[1], .unavailable(label: "In-fight win", words: Self.noCurrent))
        }
        XCTAssertFalse(headline.keyIsHollow)
        XCTAssertNil(headline.progress, "no round progress is invented")

        // Every card's in-fight reading is its own unavailable words; no
        // official context, observed round or finish is admitted during play.
        let methods = input.methods!
        XCTAssertEqual(methods.currentReading(methods.methods[0].originals[0]), .missing(Self.noCurrent))
        XCTAssertNil(methods.visibleActual)
        XCTAssertNil(input.knockout!.visibleActual)
        XCTAssertNil(input.rounds!.visibleFinish)
        XCTAssertNil(input.duration!.observed)
        XCTAssertNil(input.duration!.visibleFinish)

        // History: retained rows through the snapshot only on both traces, the
        // recorded start as context, each inspected point bound to its own row.
        let points = input.history.series[0].runs.flatMap(\.points)
        let kopylov = input.history.series[1].runs.flatMap(\.points)
        XCTAssertEqual(points.last?.id, "blend.2341.gautier")
        XCTAssertEqual(points.last?.probability, 0.5356)
        XCTAssertEqual(kopylov.last?.id, "blend.2341.kopylov")
        XCTAssertEqual(kopylov.last?.probability, 0.4644)
        XCTAssertTrue((points + kopylov).allSatisfy { $0.x <= 9 })
        XCTAssertEqual(input.history.guides.map(\.label), ["Start"])
        XCTAssertEqual(input.history.inspection?.selections["gautier"], .point(id: "blend.2341.gautier", spoken: "53.6%"))
        XCTAssertEqual(input.history.inspection?.selections["kopylov"], .point(id: "blend.2341.kopylov", spoken: "46.4%"))
    }

    func testAtTheFinalPreMatchChancesSitBesideTheOfficialResultAndContractGradesStayTheirOwn() {
        let input = Self.page(.final)
        let view = CombatEventPagePresentation10868(input: input)

        // The pre-match baseline reminder beside the reported outcome, never a
        // score, a race ordinal, a projection or a 0/100 quote.
        XCTAssertEqual(Self.figures(input.headline), [["67.2%", "Lost"], ["32.8%", "Won"]])
        let headline = FieldHeadlineModel10868(input.headline)
        XCTAssertEqual(headline.competitors[1].metrics[1], .reading(Self.officialReading(Self.fighters[1])))
        XCTAssertEqual(headline.state?.figure, "Kopylov won")
        XCTAssertEqual(headline.state?.caption, "TKO (strikes) · Round 1, 3:12")
        XCTAssertNil(headline.progress)

        // Each card's selected original keeps its own pre-match chance and its
        // own contract grade; the official result is separate context.
        guard case .final(let ko, .won("Won"))? = view.methodsContent()?.input.comparison
        else { return XCTFail("KO / TKO Yes, its own grade") }
        XCTAssertEqual(ko.id, "240262496")
        XCTAssertEqual(view.methodsContent()?.input.visibleActual?.lines, [Self.officialLine])
        guard case .final(let kopylovKO, .won("Won"))? = view.knockoutContent()?.input.comparison
        else { return XCTFail("Kopylov KO Yes, its own grade") }
        XCTAssertEqual(kopylovKO.id, "240654996")
        XCTAssertEqual(view.knockoutContent()?.input.copy, Self.knockoutCopy)
        XCTAssertEqual(view.methodsContent()?.input.copy, .method)
        guard case .final(let roundOne, .won("Won"))? = view.roundsContent()?.input.comparison
        else { return XCTFail("Kopylov Round 1 Yes, its own grade") }
        XCTAssertEqual(roundOne.id, "240655012")
        guard case .final(let beforeTwo, .won("Won"))? = view.durationContent()?.input.comparison
        else { return XCTFail("Before Round 2 Yes, its own grade") }
        XCTAssertEqual(beforeTwo.id, "240262508")
        // Under 1½ stays unconfirmed although the official finish came in Round 1.
        let under = input.duration!.markets[0].originals[0]
        XCTAssertEqual(input.duration!.result(under), .unconfirmed("Result unconfirmed"))
        XCTAssertEqual(input.duration!.visibleFinish?.segmentID, "r1")
        // Gautier's uncaptured Round 2 stays explicit words.
        XCTAssertEqual(input.rounds!.groups[1].slots[1].state, .noCapturedProp("No captured prop"))

        // The history ends at its last retained row: no 0/100 point, no finish
        // guide, no finish clock built from 3:12.
        let points = input.history.series.flatMap(\.runs).flatMap(\.points)
        XCTAssertEqual(input.history.series.map { $0.runs.last?.points.last?.id }, ["blend.2347.gautier", "blend.2347.kopylov"])
        XCTAssertTrue(points.allSatisfy { $0.probability > 0 && $0.probability < 1 })
        XCTAssertEqual(input.history.guides.map(\.id), ["start"])
        XCTAssertEqual(input.history.domain.upper, 17)

        // The owner's captured final order and reasons, wired one to one.
        XCTAssertEqual(input.stream?.cards.map(\.id), ["fighterKO", "rounds", "duration", "methods"])
        XCTAssertEqual(CombatEventPageModel10868(input).story("fighterKO")?.reason,
                       "Kopylov’s KO/TKO win had a 12.5% pre-match chance.")
    }

    // MARK: Guards

    func testALeafFromAnotherPhaseOrBoutIsNotMountedAndAStoryResolvesOnlyItsOneExactLink() {
        // A final method card on a during page, a before duration card on a
        // final page and another bout's rounds: none is coerced.
        let input = Self.page(.final, headline: Self.headline(.final, headlinePhase: .during),
                              methods: Self.methods(.final, as: .during),
                              rounds: Self.rounds(.final, eventID: "15318682"),
                              duration: Self.duration(.final, as: .before),
                              stories: Self.stories(.final) + [
                                  CombatEventPageStory10868(cardID: "fighterKO", card: .knockout),
                                  CombatEventPageStory10868(cardID: "chart", card: .history),
                              ])
        let model = CombatEventPageModel10868(input)
        let view = CombatEventPagePresentation10868(input: input)
        XCTAssertNil(model.headline)
        XCTAssertNil(view.headlineContent())
        XCTAssertNil(view.methodsContent())
        XCTAssertNil(view.roundsContent())
        XCTAssertNil(view.durationContent())
        XCTAssertNotNil(view.knockoutContent())
        XCTAssertFalse(model.readerShows(.methods))
        XCTAssertTrue(model.readerShows(.history))

        // A card naming an unmounted leaf, a duplicated id, the anchor or an
        // unknown id resolves to nothing — the owner's unavailable words.
        XCTAssertNil(model.story("methods"))
        XCTAssertNil(model.story("rounds"))
        XCTAssertNil(model.story("duration"))
        XCTAssertNil(model.story("fighterKO"), "two links for one id are none")
        XCTAssertNil(model.story("chart"))
        XCTAssertNil(model.story("missing"))

        // A wholly absent stream draws no stories and keeps the hero.
        let quiet = Self.page(.before, stream: .some(nil), stories: [])
        XCTAssertNil(quiet.stream)
        XCTAssertNotNil(CombatEventPagePresentation10868(input: quiet).headlineContent())
    }

    // MARK: Holds

    func testStreamCardActionsAndDisclosureWritesHoldFirstThenReachTheExactOwnerPayloadAndReadsEmitNothing() {
        var log: [String] = []
        let methodFlag = Flag(), roundFlag = Flag(), knockoutFlag = Flag(), durationFlag = Flag()
        func view(_ input: CombatEventPageInput10868, mode: CombatEventPageMode10868 = .page,
                  callbacks: Bool = true) -> CombatEventPagePresentation10868 {
            CombatEventPagePresentation10868(
                input: input, mode: mode,
                onMethodSelect: callbacks ? { log.append("method:\($0.originalID)") } : nil,
                onMethodDetails: callbacks ? { log.append("methodDetails:\($0.originalID)") } : nil,
                methodTimingExpanded: callbacks ? Self.binding(methodFlag, "method") { log.append($0) } : nil,
                onRoundSelect: callbacks ? { log.append("round:\($0.slotID):\($0.originalID)") } : nil,
                onRoundDetails: callbacks ? { log.append("roundDetails:\($0.originalID)") } : nil,
                roundTimingExpanded: callbacks ? Self.binding(roundFlag, "round") { log.append($0) } : nil,
                onKnockoutSelect: callbacks ? { log.append("knockout:\($0.methodID):\($0.originalID)") } : nil,
                onKnockoutDetails: callbacks ? { log.append("knockoutDetails:\($0.originalID)") } : nil,
                knockoutTimingExpanded: callbacks ? Self.binding(knockoutFlag, "knockout") { log.append($0) } : nil,
                onDurationSelect: callbacks ? { log.append("duration:\($0.durationMarketID):\($0.originalID)") } : nil,
                onDurationDetails: callbacks ? { log.append("durationDetails:\($0.originalID)") } : nil,
                durationTimingExpanded: callbacks ? Self.binding(durationFlag, "duration") { log.append($0) } : nil,
                onInteraction: { log.append("pageHold") })
        }

        // The owner's final stream shows knockout beside rounds; after browsing
        // on, it shows methods beside duration. Only displayed cards can hold.
        let input = Self.page(.final, wide: true)
        let browsed = Self.page(.final, wide: true, stream: Self.stream(.final, wide: true, showing: ("methods", "duration")))
        let page = view(input)
        let browsedPage = view(browsed)
        let hooks = [Self.activation(browsed.stream!, "methods") { log.append($0) },
                     Self.activation(input.stream!, "rounds") { log.append($0) },
                     Self.activation(input.stream!, "fighterKO") { log.append($0) },
                     Self.activation(browsed.stream!, "duration") { log.append($0) }]
        XCTAssertTrue(hooks.allSatisfy(\.isAvailable))
        XCTAssertFalse(Self.activation(input.stream!, "methods") { log.append($0) }.isAvailable)

        // Building every card and reading every disclosure asks for nothing.
        let methods = browsedPage.methodsContent(activation: hooks[0])!
        let rounds = page.roundsContent(activation: hooks[1])!
        let knockout = page.knockoutContent(activation: hooks[2])!
        let duration = browsedPage.durationContent(activation: hooks[3])!
        let bindings = [methods.timingExpanded!, rounds.timingExpanded!, knockout.timingExpanded!, duration.timingExpanded!]
        XCTAssertEqual(bindings.map(\.wrappedValue), [false, false, false, false])
        XCTAssertEqual(log, [])

        // In the stream: the card's own hold, then the exact owner payload.
        let koYes = CombatMethodOriginalRef10868(eventID: Self.eventID, methodID: "ko-tko", marketID: "63786874", originalID: "240262496")
        let kopR1 = CombatRoundOriginalRef10868(eventID: Self.eventID, groupID: "kopylov", slotID: "kopylov-r1",
                                                marketID: "63900818", originalID: "240655012")
        let kopKO = CombatMethodOriginalRef10868(eventID: Self.eventID, methodID: "ko-kopylov", marketID: "63900810", originalID: "240654996")
        let beforeR2 = CombatDurationOriginalRef10868(eventID: Self.eventID, durationMarketID: "63786880",
                                                      marketID: "63786880", originalID: "240262508")
        methods.onSelect?(koYes)
        methods.onDetails?(koYes)
        rounds.onSelect?(kopR1)
        knockout.onDetails?(kopKO)
        duration.onSelect?(beforeR2)
        XCTAssertEqual(log, ["hold:methods", "method:240262496", "hold:methods", "methodDetails:240262496",
                             "hold:rounds", "round:kopylov-r1:240655012", "hold:fighterKO", "knockoutDetails:240654996",
                             "hold:duration", "duration:63786880:240262508"])

        // A disclosure write: the hold, then the owner's exact write.
        log = []
        let methodDisclosure = bindings[0], durationDisclosure = bindings[3]
        methodDisclosure.wrappedValue = true
        durationDisclosure.wrappedValue = true
        XCTAssertEqual(log, ["hold:methods", "write:method:true", "hold:duration", "write:duration:true"])
        XCTAssertTrue(methodFlag.value)
        XCTAssertTrue(durationFlag.value)
        XCTAssertFalse(roundFlag.value)
        log = []
        XCTAssertEqual(bindings.map(\.wrappedValue), [true, false, false, true])
        XCTAssertEqual(log, [], "reads emit nothing")

        // Full-size content: the same leaf with the exact callback and binding, no hold.
        view(input, mode: .reader(.knockout)).knockoutContent()?.onSelect?(kopKO)
        let readerDisclosure = view(input, mode: .reader(.rounds)).roundsContent()!.timingExpanded!
        readerDisclosure.wrappedValue = true
        XCTAssertEqual(log, ["knockout:ko-kopylov:240654996", "write:round:true"])

        // Without host callbacks or bindings, nothing acts, even inside the stream.
        log = []
        let quiet = view(input, callbacks: false)
        XCTAssertNil(quiet.methodsContent(activation: hooks[0])?.onSelect)
        XCTAssertNil(quiet.methodsContent(activation: hooks[0])?.timingExpanded)
        XCTAssertNil(quiet.roundsContent(activation: hooks[1])?.onDetails)
        XCTAssertNil(quiet.knockoutContent(activation: hooks[2])?.onSelect)
        XCTAssertNil(quiet.durationContent(activation: hooks[3])?.timingExpanded)
        XCTAssertEqual(log, [], "a stream card never passes through the page hook as well")
    }

    func testThePageHookHoldsOnceBeforeEachPageCatalogueAndDetailsActionAndNeverForReadersOrPassiveReads() {
        var log: [String] = []
        let originals = Self.originals(.final)
        func view(_ mode: CombatEventPageMode10868 = .page, hook: Bool = true) -> CombatEventPagePresentation10868 {
            CombatEventPagePresentation10868(
                input: Self.page(.final), mode: mode, originals: originals,
                onAbout: { log.append("about") },
                onAboutSource: { log.append("source:\($0.id)") },
                onAllProps: { log.append("allProps") },
                onOriginalSelect: { log.append("select:\($0.identity.market):\($0.identity.side)") },
                onOriginalHistory: { log.append("history:\($0.actionID)") },
                onStoryIntent: { _ in log.append("stream") },
                onHeadlineOpen: { log.append("headline:\($0.ref.scope)|\($0.ref.source)|\($0.ref.marketID)|\($0.ref.outcomeID)") },
                onHistoryAction: { log.append("chart:\($0)") },
                onHistoryInspectionChoice: { log.append("inspect:\($0)") },
                onHistoryPlotPosition: { log.append("plot:\($0)") },
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building and reading every page leaf and content mode calls nothing.
        let page = view()
        let headline = page.headlineContent()!
        let anchor = page.historyContent(reader: false)
        let catalogue = view(.catalogue).catalogueContent()!
        let details = view(.original).originalDetailsContent()!
        _ = view(.about).aboutContent()
        _ = view(.reader(.history)).historyContent(reader: true)
        XCTAssertEqual(log, [])

        // Each page action: the hook once, then the exact owner value. A
        // headline open hands back the owner's exact display identity.
        headline.onOpen?(FieldMovementOpen10868(ref: Self.ref("kopylov"), observation: nil))
        headline.onAbout?()
        anchor.onAction?("window.pregame")
        anchor.onAction?("history.expand")
        anchor.onInspectionChoice?("blend.2340.kopylov")
        anchor.onPlotPosition?(6)
        page.openAllProps()
        XCTAssertEqual(log, ["hold", "headline:mma:15318681:winner:blend|bainluck-blend|15318681:winner|kopylov",
                             "hold", "about", "hold", "chart:window.pregame",
                             "hold", "chart:history.expand", "hold", "inspect:blend.2340.kopylov", "hold", "plot:6.0",
                             "hold", "allProps"])

        // Catalogue selection and a Details history intent: the hook once, then the exact value.
        log = []
        let card = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                     labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)[0]
        OriginalMarketCatalogue9483.action(card, onSelect: catalogue.onSelect)?()
        let intent = OriginalMarketDetails9483.HistoryIntent(selection: originals.selection!, entry: .explore, actionID: "constructed.explore")
        details.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "select:63254893:238409895", "hold", "history:constructed.explore"])

        // Already-held full-size content keeps the exact callbacks: no second hold.
        log = []
        view(.reader(.history)).historyContent(reader: true).onAction?("history.next")
        view(.reader(.methods)).openReaderAbout()
        view(.about).aboutContent()?.sourceAction(Self.ufcSource)?()
        XCTAssertEqual(log, ["chart:history.next", "about", "source:ufc-result"])

        // No hook: every page action is the owner's own.
        log = []
        let plain = view(hook: false)
        plain.headlineContent()?.onAbout?()
        plain.historyContent(reader: false).onAction?("window.all")
        plain.openAllProps()
        XCTAssertEqual(log, ["about", "chart:window.all", "allProps"])

        // No callbacks: no action and no hook call.
        log = []
        let bare = CombatEventPagePresentation10868(input: Self.page(.final), originals: originals,
                                                    onInteraction: { log.append("hold") })
        XCTAssertNil(bare.headlineContent()?.onAbout)
        XCTAssertNil(bare.headlineContent()?.onOpen)
        XCTAssertNil(bare.historyContent(reader: false).onAction)
        XCTAssertNil(bare.catalogueContent()?.onSelect)
        XCTAssertNil(bare.originalDetailsContent()?.onHistory)
        bare.openAllProps()
        bare.openReaderAbout()
        XCTAssertEqual(log, [])
    }

    // MARK: Full-size history and readers

    func testTheFullSizeHistoryChangesOnlyItsLayoutAndExpandAndEachReaderIsTheSameLeaf() {
        let input = Self.page(.final)
        let view = CombatEventPagePresentation10868(input: input, mode: .reader(.history))
        let page = input.history
        let reader = view.historyContent(reader: true).input
        XCTAssertEqual(page.layout, .cohortAbove)
        XCTAssertEqual(reader.layout, .expanded)
        XCTAssertNotNil(page.expand)
        XCTAssertNil(reader.expand)

        // Everything else is the owner's, unchanged: restore the two fields and compare whole.
        var restored = reader
        restored.layout = page.layout
        let rebuilt = FieldHistoryInput10868(
            title: restored.title, caption: restored.caption, series: restored.series, selection: restored.selection,
            domain: restored.domain, ceiling: restored.ceiling, yTicks: restored.yTicks, xTicks: restored.xTicks,
            guides: restored.guides, breaks: restored.breaks, readout: restored.readout, markKey: restored.markKey,
            comparisonExplanation: restored.comparisonExplanation, notes: restored.notes, summary: restored.summary,
            plotHeight: restored.plotHeight, unboundReadingWords: restored.unboundReadingWords,
            plotUnavailableWords: restored.plotUnavailableWords, windows: restored.windows, scale: restored.scale,
            moreOriginals: restored.moreOriginals, details: restored.details, expand: page.expand,
            inspect: restored.inspect, previous: restored.previous, next: restored.next,
            inspection: restored.inspection, layout: restored.layout,
            probabilityLowerBound: restored.probabilityLowerBound,
            probabilityRangeExplanation: restored.probabilityRangeExplanation,
            selectedReadout: restored.selectedReadout, inspectionRingShape: restored.inspectionRingShape,
            plotAbsence: restored.plotAbsence, showsKey: restored.showsKey)
        XCTAssertEqual(rebuilt, page)
        // Both traces, their own point ids, readouts and inspection, and the
        // complement words travel unchanged into full size.
        XCTAssertEqual(reader.series.map(\.id), ["gautier", "kopylov"])
        XCTAssertEqual(reader.series, page.series)
        XCTAssertFalse(reader.series[1].runs.isEmpty)
        XCTAssertEqual(reader.inspection, page.inspection)
        XCTAssertEqual(reader.summary, page.summary)
        XCTAssertTrue(reader.summary.contains(Self.complementWords))
        XCTAssertEqual(reader.plotHeight, page.plotHeight)

        // Each offered card's full-size content is the same leaf and input.
        let model = CombatEventPageModel10868(input)
        for card in CombatEventPageCard10868.allCases {
            XCTAssertTrue(model.readerShows(card), card.rawValue)
        }
        XCTAssertEqual(CombatEventPagePresentation10868(input: input, mode: .reader(.methods)).methodsContent()?.input, input.methods)
        XCTAssertEqual(CombatEventPagePresentation10868(input: input, mode: .reader(.knockout)).knockoutContent()?.input, input.knockout)
        XCTAssertEqual(CombatEventPagePresentation10868(input: input, mode: .reader(.rounds)).roundsContent()?.input, input.rounds)
        XCTAssertEqual(CombatEventPagePresentation10868(input: input, mode: .reader(.duration)).durationContent()?.input, input.duration)
    }

    // MARK: About

    func testTheAboutOpensOnlyThroughItsReadableEntriesAndItsSourceHandsTheOwnerTheExactSource() {
        var log: [String] = []
        let final = Self.page(.final)

        // The headline's own control and the readers' compact heading; never the page body.
        let open = CombatEventPagePresentation10868(input: final, onAbout: { log.append("about") })
        XCTAssertNotNil(open.headlineContent()?.onAbout)
        let model = CombatEventPageModel10868(final)
        XCTAssertFalse(model.aboutEntry(mode: .page, canOpen: true))
        XCTAssertTrue(model.aboutEntry(mode: .reader(.duration), canOpen: true))
        XCTAssertFalse(model.aboutEntry(mode: .reader(.duration), canOpen: false))
        XCTAssertFalse(model.aboutEntry(mode: .catalogue, canOpen: true))

        // No readable About, or no callback: no control at all.
        let blank = Self.page(.final, about: .some(CombatEventPageAbout10868(title: " ", sections: [
            CombatEventPageAboutSection10868(title: "", paragraphs: ["  "], source: Self.ufcSource),
        ])))
        XCTAssertNil(CombatEventPagePresentation10868(input: blank, onAbout: { log.append("about") }).headlineContent()?.onAbout)
        XCTAssertNil(CombatEventPagePresentation10868(input: blank, mode: .about).aboutContent())
        XCTAssertNil(CombatEventPagePresentation10868(input: final).headlineContent()?.onAbout)
        XCTAssertEqual(log, [])

        // The phase's own sections: the official result only once admitted.
        XCTAssertEqual(Self.about(.before).sections.map(\.title), ["Pre-match chances", "History and source"])
        XCTAssertEqual(Self.about(.during).sections.map(\.title), ["Pre-match chances", "Fight state", "History and source"])
        XCTAssertEqual(Self.about(.final).sections.map(\.title), ["Pre-match chances", "Official bout result", "History and source"])

        // The source control hands the owner its exact source and opens nothing;
        // without a callback, or without readable words, it is static.
        let content = CombatEventPagePresentation10868(input: final, mode: .about, onAboutSource: { log.append("source:\($0.url.absoluteString)") })
            .aboutContent()!
        XCTAssertEqual(content.about, final.about)
        XCTAssertEqual(log, [])
        content.sourceAction(Self.ufcSource)?()
        XCTAssertEqual(log, ["source:https://www.ufc.com/news/ufc-332-silva-vs-wang-results"])
        XCTAssertNil(CombatEventPagePresentation10868(input: final, mode: .about).aboutContent()?.sourceAction(Self.ufcSource))
        let unnamed = CombatEventPageSource10868(id: "blank", label: " ", url: Self.ufcSource.url)
        XCTAssertNil(content.sourceAction(unnamed))
        XCTAssertNil(content.sourceAction(nil))
    }

    // MARK: All props and Details

    private typealias Originals = OriginalMarketDetails9483

    private static func originalsScope(_ phase: CombatEventPagePhase10868) -> String { "mma:15318681:originals:\(phase.rawValue)" }

    private static func identity(_ market: String, _ side: String) -> Originals.Identity {
        Originals.Identity(source: "polymarket", market: market, side: side)
    }

    /// The winner market's own original clock, kept on its rows.
    private static let winnerTimestamp = Originals.Row(label: "Original timestamp", value: "2026-10-03T23:27:48.847758Z")

    /// One retained original: (market, side, title, outcome, figure text,
    /// placement, contract grade, provenance).
    private typealias OriginalRow = (String, String, String, String, String, Double, String, String)

    /// The owner's "All" page: both winner sides and each story card's final
    /// pick, 6 of the 31 retained originals.
    private static let allRows: [OriginalRow] = [
        ("63254893", gautierSide, "UFC 332: Roman Kopylov vs. Ateba Gautier", "Ateba Gautier", "68.5%", 0.685, "Lost", lateDetail),
        ("63254893", kopylovSide, "UFC 332: Roman Kopylov vs. Ateba Gautier", "Roman Kopylov", "31.5%", 0.315, "Won", lateDetail),
        ("63786874", "240262496", "Will the fight be won by KO or TKO?", "Yes", "55%", 0.55, "Won", lateDetail),
        ("63900810", "240654996", "Will Roman Kopylov win by KO or TKO?", "Yes", "12.5%", 0.125, "Won", lateDetail),
        ("63900818", "240655012", "Will Roman Kopylov win in Round 1?", "Yes", "11%", 0.11, "Won", lateDetail),
        ("63786880", "240262508", "Will the fight end before Round 2?", "Yes", "32.5%", 0.325, "Won", lateDetail),
    ]

    /// The owner's "Finish method" page: all 6 retained finish-method originals.
    private static let methodRows: [OriginalRow] = [
        ("63786874", "240262496", "Will the fight be won by KO or TKO?", "Yes", "55%", 0.55, "Won", lateDetail),
        ("63786874", "240262497", "Will the fight be won by KO or TKO?", "No", "45%", 0.45, "Lost", lateDetail),
        ("63634393", "239735845", "Will the fight be won by submission?", "Yes", "10.5%", 0.105, "Lost", lateDetail),
        ("63634393", "239735846", "Will the fight be won by submission?", "No", "89.5%", 0.895, "Won", lateDetail),
        ("63786883", "240262514", "Will the fight end in a decision or draw?", "Yes", "51%", 0.51, "Lost",
         "Last recorded before start · Oct 3, 1:03 AM PT · Polymarket"),
        ("63786883", "240262515", "Will the fight end in a decision or draw?", "No", "49%", 0.49, "Won",
         "Last recorded before start · Oct 3, 1:03 AM PT · Polymarket"),
    ]

    /// A subset of the 31 retained originals, as the owner admits it for its
    /// current category and page. Pregame readings and contract grades are
    /// each original's own (api_settlement), never the official bout result
    /// and never the blend. The count words describe the supplied rows; the
    /// retained 31 is stated only beside the owner's real Show more.
    private static func originals(_ phase: CombatEventPagePhase10868,
                                  recorded: Originals.RecordedHistory? = nil,
                                  admitting rows: [OriginalRow] = CombatEventPagePresentation10868Tests.allRows,
                                  controls: CombatEventPageCatalogueControls10868? = nil) -> CombatEventPageOriginals10868 {
        let scope = originalsScope(phase)
        return CombatEventPageOriginals10868(
            catalogue: Originals.Catalogue(scope: scope, originals: rows.map { row in
                Originals.Original(
                    identity: identity(row.0, row.1), title: row.2, outcome: row.3,
                    mode: phase == .final ? .result : .pregame,
                    pregame: .value(row.4, placement: row.5, provenance: row.7),
                    later: nil,
                    grade: phase == .final ? Originals.Grade(words: row.6, provenance: "Polymarket settlement") : nil,
                    about: Originals.About(source: "Polymarket", rules: .omitted,
                                           provenance: [Originals.Row(label: "Market ID", value: row.0)]
                                               + (row.0 == winnerMarket ? [winnerTimestamp] : []),
                                           historicalQuote: nil))
            }),
            selection: Originals.Selection(scope: scope, identity: identity(winnerMarket, gautierSide)),
            recorded: recorded,
            labels: [identity(winnerMarket, gautierSide): "Ateba Gautier · Winner",
                     identity(winnerMarket, kopylovSide): "Roman Kopylov · Winner"],
            heading: "All props", context: controls == nil ? "6 originals shown" : "31 retained originals",
            emptyWords: "No retained originals for this fight", unavailableChoice: "Unnamed original",
            tint: gautierTint, controls: controls)
    }

    private static func category(_ id: String, _ label: String, selected: Bool = false,
                                 available: Bool = true) -> CombatEventPageCatalogueCategory10868 {
        CombatEventPageCatalogueCategory10868(
            action: FieldHistoryAction10868(id: id, label: label, spokenLabel: nil, isAvailable: available),
            isSelected: selected)
    }

    /// The owner's six categories. The four family ids are `combatCatalog.ts`'s
    /// keys; All and Winner are the owner's own (the winner market has no family).
    private static let families = [("all", "All"), ("winner", "Winner"), ("methods", "Finish method"),
                                   ("rounds", "Fighter rounds"), ("fighterKO", "Knockout chances"), ("duration", "Fight length")]

    /// "all": 6 shown of 31 retained, with a real Show more. "methods": all 6
    /// finish-method originals, nothing more to show.
    private static func controls(selected: String) -> CombatEventPageCatalogueControls10868 {
        CombatEventPageCatalogueControls10868(
            categoriesLabel: "Fight market category",
            categories: families.map { category("category.\($0.0)", $0.1, selected: $0.0 == selected) },
            more: selected == "all" ? action("catalogue.more", "Show more · 25 remaining",
                                             spoken: "Show more originals, 25 remaining") : nil,
            context: selected == "all" ? "Showing 6 of 31 originals" : "Showing all 6 finish-method originals")
    }

    private static func cards(_ view: OriginalMarketCatalogueView9483) -> [OriginalMarketCatalogue9483.Card] {
        OriginalMarketCatalogue9483.cards(catalogue: view.catalogue, selection: view.selection,
                                          labels: view.labels, unavailableChoice: view.unavailableChoice)
    }

    /// CONSTRUCTED contract input, never history evidence: an owner context
    /// for the held Gautier winner original at the final, with no points and
    /// an explicit plot absence, offering only Explore.
    private static func recordedContext() -> Originals.RecordedHistory {
        let seriesID = "constructed.history.gautier"
        let selection = Originals.Selection(scope: originalsScope(.final), identity: identity(winnerMarket, gautierSide))
        var history = FieldHistoryInput10868(
            title: "Recorded chance", caption: nil,
            series: [FieldHistorySeries10868(
                id: seriesID, name: "Ateba Gautier", shape: .circle, tint: gautierTint, runs: [], links: [], labelPointID: nil,
                before: .absent(words: "Unavailable"), recorded: .absent(words: "Unavailable"), absentWords: nil, choose: nil)],
            selection: .series(id: seriesID, missingWords: "This original isn’t in this history"),
            domain: FieldHistoryDomain10868(lower: -2, upper: 17), ceiling: 1,
            yTicks: [FieldHistoryTick10868(value: 0, lines: ["0%"]), FieldHistoryTick10868(value: 1, lines: ["100%"])],
            xTicks: xTicks(.final), guides: [], breaks: [], readout: .singleBefore(label: "Pre-match"),
            markKey: FieldHistoryMarkKey10868(hollow: "Hollow: pre-match", filled: nil),
            comparisonExplanation: nil, notes: [], summary: "Ateba Gautier: no recorded trades in this context.",
            plotHeight: 132, unboundReadingWords: "Unavailable", plotUnavailableWords: "Original history unavailable",
            windows: nil, scale: nil, moreOriginals: nil, details: nil, expand: nil, inspect: nil,
            previous: nil, next: nil, inspection: nil, layout: .expanded)
        history.showsKey = false
        history.plotAbsence = FieldHistoryPlotAbsence10868(title: "Recorded history not drawn", words: nil)
        return Originals.RecordedHistory(
            selection: selection, mode: .result, seriesID: seriesID,
            availability: "Pre-match chance and contract result below",
            readings: [Originals.RecordedReading(label: "Pre-match chance", marker: .hollow,
                                                 reading: .value("68.5%", placement: nil, provenance: lateDetail))],
            movement: nil, history: history, finishLabel: "Official result",
            finish: .reported(words: "Lost · TKO (strikes), Round 1, 3:12", spoken: nil),
            preview: nil, expand: nil,
            explore: FieldHistoryAction10868(id: "constructed.original.history.explore", label: "Explore history",
                                             spokenLabel: nil, isAvailable: true),
            unmatchedWords: "Recorded history unavailable for this original")
    }

    func testAllPropsAndDetailsMountTheExistingLeavesAndForwardTheOwnersOptionalRecordedHistory() {
        var log: [String] = []
        var received: [Originals.HistoryIntent] = []
        let context = Self.recordedContext()
        let originals = Self.originals(.final, recorded: context)
        func view(_ mode: CombatEventPageMode10868, group: CombatEventPageOriginals10868? = nil,
                  callback: Bool = true) -> CombatEventPagePresentation10868 {
            CombatEventPagePresentation10868(
                input: Self.page(.final), mode: mode, originals: group ?? originals,
                onOriginalHistory: callback ? { received.append($0); log.append("history:\($0.actionID)") } : nil,
                onInteraction: { log.append("hold") })
        }

        // All props: exactly the owner's admitted rows, order, scope and held original.
        let catalogue = view(.catalogue).catalogueContent()!
        XCTAssertEqual(catalogue.catalogue, originals.catalogue)
        XCTAssertEqual(catalogue.selection, originals.selection)
        XCTAssertEqual(catalogue.heading, "All props")
        XCTAssertEqual(catalogue.context, "6 originals shown", "the count words describe the six supplied rows")
        let cards = OriginalMarketCatalogue9483.cards(catalogue: catalogue.catalogue, selection: catalogue.selection,
                                                      labels: catalogue.labels, unavailableChoice: catalogue.unavailableChoice)
        XCTAssertEqual(cards.count, 6)
        XCTAssertEqual(cards.prefix(2).map(\.choice.label), ["Ateba Gautier · Winner", "Roman Kopylov · Winner"])
        XCTAssertEqual(cards.map(\.choice.isSelected), [true, false, false, false, false, false])

        // Each original keeps its own pre-match reading and contract grade.
        let rows = originals.catalogue!.originals
        XCTAssertEqual(rows.map(\.grade?.words), ["Lost", "Won", "Won", "Won", "Won", "Won"])
        XCTAssertEqual(rows.map(\.pregame.placement), [0.685, 0.315, 0.55, 0.125, 0.11, 0.325])
        XCTAssertTrue(Self.originals(.before).catalogue!.originals.allSatisfy { $0.grade == nil && $0.mode == .pregame })

        // Details: the owner's exact context, catalogue and held selection; building calls nothing.
        let details = view(.original).originalDetailsContent()!
        XCTAssertEqual(details.recorded, context)
        XCTAssertEqual(details.catalogue, originals.catalogue)
        XCTAssertEqual(details.selection, originals.selection)
        XCTAssertEqual(log, [])

        // The leaf's own Explore intent: the hook once, then the exact intent.
        guard case .recorded(let shown)? = Originals.recorded(catalogue: details.catalogue, selection: details.selection,
                                                               context: details.recorded, hasCallback: details.onHistory != nil),
              let intent = Originals.intent(.explore, in: shown)
        else { return XCTFail("the constructed context resolves for the held original") }
        XCTAssertFalse(shown.showsPlot, "a constructed context draws no recorded trades")
        details.onHistory?(intent)
        XCTAssertEqual(log, ["hold", "history:constructed.original.history.explore"])
        XCTAssertEqual(received, [intent])

        // No callback: the context still reaches the leaf, no history action, no hold.
        log = []
        let quiet = view(.original, callback: false).originalDetailsContent()!
        XCTAssertEqual(quiet.recorded, context)
        XCTAssertNil(quiet.onHistory)
        // Default: no context, the existing summary-only Details.
        XCTAssertNil(view(.original, group: Self.originals(.final)).originalDetailsContent()?.recorded)
        XCTAssertNil(CombatEventPagePresentation10868(input: Self.page(.final), mode: .original).originalDetailsContent())
        XCTAssertEqual(log, [])

        // The page's entry needs readable words and a callback.
        let unnamed = Self.page(.final)
        XCTAssertFalse(CombatEventPageModel10868(unnamed).allPropsAvailable(canOpen: false))
        XCTAssertTrue(CombatEventPageModel10868(unnamed).allPropsAvailable(canOpen: true))
    }

    // MARK: Arrangement

    func testCompactWideAndAccessibilitySizesChooseTheirArrangementsAndBothFightersKeepEqualStanding() {
        XCTAssertEqual(CombatEventPageModel10868.arrangements(sizeClass: .compact, accessibilitySize: false), [.stacked])
        XCTAssertEqual(CombatEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(CombatEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: false), [.sideBySide, .stacked])
        XCTAssertEqual(CombatEventPageModel10868.arrangements(sizeClass: .regular, accessibilitySize: true), [.stacked])
        XCTAssertEqual(CombatEventPageModel10868.arrangements(sizeClass: nil, accessibilitySize: true), [.stacked])

        // Both fighters reach the headline whole, in the owner's order, with
        // the shapes the history draws; the leaf decides columns or rows.
        let input = Self.page(.final, wide: true)
        XCTAssertEqual(input.headline.displayed.map(\.name), input.history.series.map(\.name))
        XCTAssertEqual(input.headline.displayed.map(\.keyShape), [.circle, .diamond])
        XCTAssertEqual(input.history.series.map(\.shape), [.circle, .diamond])
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 360, count: 2, figureWidths: [64, 64],
                                                              spacing: 16, accessibilitySize: false), .columns)
        XCTAssertEqual(FieldHeadlineGeometry10868.arrangement(available: 360, count: 2, figureWidths: [64, 64],
                                                              spacing: 16, accessibilitySize: true), .rows)
        // The page keeps the owner's plot height and the stream's wide choice.
        XCTAssertEqual(CombatEventPagePresentation10868(input: input).historyContent(reader: false).input.plotHeight, 220)
        XCTAssertEqual(input.stream?.wide, true)
    }

    // MARK: The approved paired reference

    private static func beforeDetail(_ original: FieldChooserOriginal10868) -> String? {
        guard case .single(let reading) = original.plan, case .recorded(_, let detail) = reading.value else { return nil }
        return detail
    }

    func testTheAdmittedBlendPairAnchorsTheHeadlineAndBothTracesWhileTheWinnerOriginalKeepsItsOwnValuesClockAndIdentity() {
        for phase in CombatEventPagePhase10868.allCases {
            let input = Self.page(phase)
            let view = CombatEventPagePresentation10868(input: input)
            XCTAssertEqual(view.headlineContent()?.input, input.headline, phase.rawValue)
            XCTAssertEqual(view.historyContent(reader: false).input, input.history, phase.rawValue)

            // The headline: the owner's literal baseline pair with one shared
            // clock and no source words in its chrome.
            XCTAssertEqual(input.headline.pairs.map { $0.before?.probability }, [0.6724, 0.3276])
            XCTAssertEqual(Self.figures(input.headline).map(\.first), ["67.2%", "32.8%"])
            let details = input.headline.catalogue.map(Self.beforeDetail)
            XCTAssertEqual(details, [Self.baselineClock, Self.baselineClock])
            XCTAssertTrue(details.compactMap { $0 }.allSatisfy { !$0.contains("blend") && !$0.contains("Polymarket") })

            // Opaque display identities, never a provider market or selection.
            XCTAssertEqual(input.headline.displayed.map(\.ref), [Self.ref("gautier"), Self.ref("kopylov")])
            XCTAssertTrue(input.headline.displayed.allSatisfy {
                $0.ref.source == "bainluck-blend" && $0.ref.marketID != Self.winnerMarket
                    && ![Self.gautierSide, Self.kopylovSide].contains($0.ref.outcomeID)
            })

            // Both traces: circle and diamond, the same runs and breaks at the
            // same positions and roles, independent point ids, and each point the
            // owner's literal value for its own row.
            let gautier = input.history.series[0], kopylov = input.history.series[1]
            XCTAssertEqual([gautier.shape, kopylov.shape], [.circle, .diamond])
            XCTAssertEqual(gautier.runs.map { $0.points.map(\.x) }, kopylov.runs.map { $0.points.map(\.x) })
            XCTAssertEqual(gautier.runs.map { $0.points.map(\.style) }, kopylov.runs.map { $0.points.map(\.style) })
            let gPoints = gautier.runs.flatMap(\.points), kPoints = kopylov.runs.flatMap(\.points)
            XCTAssertTrue(Set(gPoints.map(\.id)).isDisjoint(with: kPoints.map(\.id)))
            for (g, k) in zip(gPoints, kPoints) {
                guard let row = Self.blend.first(where: { $0.x == g.x }) else { return XCTFail("row at \(g.x)") }
                XCTAssertEqual(g.probability, row.gautier)
                XCTAssertEqual(k.probability, row.kopylov)
                XCTAssertEqual(g.id, "blend.\(row.index).gautier")
                XCTAssertEqual(k.id, "blend.\(row.index).kopylov")
            }
            // Its baseline readouts name the same row the headline shows.
            XCTAssertEqual(gautier.before, .observation(pointID: "blend.2331.gautier", figure: "67.2%",
                                                        provenance: "Oct 3, 5:18 PM PT · Bain Luck blend · supplied aggregate"))
            XCTAssertEqual(kopylov.before, .observation(pointID: "blend.2331.kopylov", figure: "32.8%",
                                                        provenance: "Oct 3, 5:18 PM PT · Bain Luck blend · complement of the aggregate"))
        }

        // The complement is disclosed in the About, history notes and summary;
        // Kopylov is never called independently quoted.
        let final = Self.page(.final)
        let aboutWords = final.about!.sections.flatMap(\.paragraphs)
        XCTAssertTrue(aboutWords.contains(Self.complementWords))
        XCTAssertTrue(final.history.summary.contains(Self.complementWords))
        XCTAssertTrue(final.history.notes.contains { $0.contains(Self.complementWords) })
        XCTAssertFalse((aboutWords + [final.history.summary] + final.history.notes).contains { $0.contains("independently quoted") })

        // The independent winner market keeps its own 68.5% / 31.5%, its own
        // original clock and its own provider identity in All props and Details.
        let originals = Self.originals(.final)
        let winner = Array(originals.catalogue!.originals.prefix(2))
        XCTAssertEqual(winner.map(\.identity), [Self.identity(Self.winnerMarket, Self.gautierSide),
                                                Self.identity(Self.winnerMarket, Self.kopylovSide)])
        XCTAssertEqual(winner.map(\.pregame.placement), [0.685, 0.315])
        XCTAssertEqual(winner.map(\.about.source), ["Polymarket", "Polymarket"])
        XCTAssertTrue(winner.allSatisfy { $0.about.provenance.contains(Self.winnerTimestamp) })
        XCTAssertFalse(originals.catalogue!.originals.contains { $0.identity.source == Self.blendSource })
        let details = CombatEventPagePresentation10868(input: final, mode: .original, originals: originals).originalDetailsContent()!
        XCTAssertEqual(details.catalogue, originals.catalogue)
        XCTAssertEqual(details.selection, Originals.Selection(scope: Self.originalsScope(.final),
                                                             identity: Self.identity(Self.winnerMarket, Self.gautierSide)))
    }

    func testWithNoOwnerAdmittedKopylovSeriesAbsenceStaysAbsenceAndNoLineOrFigureIsDerived() {
        let headline = Self.headline(.final, kopylovAdmitted: false)
        let history = Self.history(.final, kopylovAdmitted: false)
        let input = Self.page(.final, headline: headline, history: history)
        let view = CombatEventPagePresentation10868(input: input)

        // The page forwards exactly what the owner supplied, page and full size.
        XCTAssertEqual(view.headlineContent()?.input, headline)
        XCTAssertEqual(view.historyContent(reader: false).input, history)
        XCTAssertEqual(CombatEventPagePresentation10868(input: input, mode: .reader(.history))
            .historyContent(reader: true).input.series, history.series)

        // Gautier's supplied aggregate stays; Kopylov is its own absence words.
        XCTAssertEqual(headline.pairs.map { $0.before?.probability }, [0.6724, nil])
        XCTAssertFalse(Self.figures(headline).joined().contains("32.8%"))
        let kopylov = history.series[1]
        XCTAssertEqual(kopylov.runs, [])
        XCTAssertNil(kopylov.labelPointID)
        XCTAssertEqual(kopylov.before, .absent(words: Self.noKopylov))
        XCTAssertEqual(kopylov.recorded, .absent(words: Self.noKopylov))
        XCTAssertEqual(kopylov.absentWords, "No Kopylov history in this update")
        XCTAssertEqual(history.inspection?.selections["kopylov"], .absent(words: Self.noKopylov))
        XCTAssertFalse(history.series.flatMap(\.runs).flatMap(\.points).contains { $0.id.hasSuffix(".kopylov") })
        XCTAssertFalse(history.summary.contains("complement"))

        // The bounded exception never reaches a provider original: each story
        // card side keeps its own independently quoted value.
        XCTAssertEqual(input.knockout!.methods.map { $0.originals.map(\.before?.probability) },
                       [[0.125, 0.875], [0.4, 0.6]])
    }

    // MARK: All props categories and paging

    func testCatalogueCategoriesAndShowMoreHoldOnceThenHandTheOwnerItsExactIntentAndOwnerUpdatesKeepTheHeldOriginal() {
        var log: [String] = []
        let context = Self.recordedContext()
        let all = Self.originals(.final, recorded: context, controls: Self.controls(selected: "all"))
        func view(_ mode: CombatEventPageMode10868, _ group: CombatEventPageOriginals10868,
                  hook: Bool = true, callbacks: Bool = true) -> CombatEventPagePresentation10868 {
            CombatEventPagePresentation10868(
                input: Self.page(.final), mode: mode, originals: group,
                onOriginalSelect: callbacks ? { log.append("select:\($0.identity.market):\($0.identity.side)") } : nil,
                onOriginalHistory: callbacks ? { log.append("history:\($0.actionID)") } : nil,
                onCatalogueCategory: callbacks ? { log.append("category:\($0)") } : nil,
                onCatalogueMore: callbacks ? { log.append("more:\($0)") } : nil,
                onInteraction: hook ? { log.append("hold") } : nil)
        }

        // Building the catalogue, reading its controls and Details calls nothing.
        let catalogue = view(.catalogue, all)
        let mounted = catalogue.catalogueContent()!
        let controls = all.controls!
        let categories = controls.categories.map { catalogue.categoryAction($0) }
        let more = catalogue.moreAction()
        _ = view(.original, all).originalDetailsContent()
        XCTAssertEqual(log, [])

        // Each live control: the hook once, then the owner's exact intent id.
        categories.forEach { $0?() }
        more?()
        XCTAssertEqual(log, ["hold", "category:category.all", "hold", "category:category.winner",
                             "hold", "category:category.methods", "hold", "category:category.rounds",
                             "hold", "category:category.fighterKO", "hold", "category:category.duration",
                             "hold", "more:catalogue.more"])

        // The count words match the six supplied rows; the retained 31 sits
        // beside a real Show more, and no other record is fabricated.
        XCTAssertEqual(Self.cards(mounted).count, 6)
        XCTAssertEqual(controls.context, "Showing 6 of 31 originals")
        XCTAssertEqual(controls.more?.label, "Show more · 25 remaining")
        XCTAssertEqual(mounted.catalogue, all.catalogue)
        XCTAssertEqual(mounted.catalogue?.originals.count, 6)

        // The owner's update to Finish method: its six admitted rows reach the
        // leaf unchanged, the held winner original stays the owner's although
        // this page does not list it, and Details keeps its recorded context.
        log = []
        let methods = Self.originals(.final, recorded: context, admitting: Self.methodRows,
                                     controls: Self.controls(selected: "methods"))
        let updated = view(.catalogue, methods).catalogueContent()!
        XCTAssertEqual(updated.catalogue, methods.catalogue)
        XCTAssertEqual(updated.catalogue?.originals.map(\.identity.market),
                       ["63786874", "63786874", "63634393", "63634393", "63786883", "63786883"])
        XCTAssertEqual(updated.selection, all.selection, "the held original is never cleared or re-elected")
        XCTAssertEqual(Self.cards(updated).map(\.choice.isSelected), [false, false, false, false, false, false])
        XCTAssertEqual(methods.controls?.categories.filter(\.isSelected).map(\.action.label), ["Finish method"])
        XCTAssertNil(methods.controls?.more)
        XCTAssertEqual(methods.controls?.context, "Showing all 6 finish-method originals")
        XCTAssertNil(view(.catalogue, methods).moreAction(), "no Show more without the owner's intent")
        let details = view(.original, methods).originalDetailsContent()!
        XCTAssertEqual(details.recorded, context)
        XCTAssertEqual(details.selection, all.selection)
        XCTAssertEqual(log, [])

        // A card in the updated page still selects through the hook once.
        OriginalMarketCatalogue9483.action(Self.cards(updated)[2], onSelect: updated.onSelect)?()
        XCTAssertEqual(log, ["hold", "select:63634393:239735845"])

        // No owner callbacks: no action and no hook call; the controls stay words.
        log = []
        let quiet = view(.catalogue, all, callbacks: false)
        XCTAssertTrue(controls.categories.allSatisfy { quiet.categoryAction($0) == nil })
        XCTAssertNil(quiet.moreAction())
        XCTAssertEqual(log, [])

        // No hook: the exact owner callbacks.
        let plain = view(.catalogue, all, hook: false)
        plain.categoryAction(controls.categories[2])?()
        plain.moreAction()?()
        XCTAssertEqual(log, ["category:category.methods", "more:catalogue.more"])
    }

    func testCatalogueControlStatesShareOneIdSpaceStayStaticWhenAmbiguousAndWrapOrStackByTypeSize() {
        typealias Model = CombatEventPageModel10868
        let controls = Self.controls(selected: "all")

        // Live only with a callback; static otherwise. Selected is the owner's flag.
        XCTAssertEqual(controls.categories.map { Model.catalogueControlState($0.action, in: controls, hasCallback: true) },
                       Self.families.map { FieldHistoryControlState10868.live(id: "category.\($0.0)") })
        XCTAssertTrue(controls.categories.allSatisfy {
            Model.catalogueControlState($0.action, in: controls, hasCallback: false) == .shownStatic
        })
        XCTAssertEqual(controls.categories.map(\.isSelected), [true, false, false, false, false, false])
        XCTAssertEqual(Model.shownCategories(controls, hasCallback: false).map(\.action.label),
                       ["All", "Winner", "Finish method", "Fighter rounds", "Knockout chances", "Fight length"])
        XCTAssertEqual(Model.catalogueControlState(controls.more, in: controls, hasCallback: true), .live(id: "catalogue.more"))
        XCTAssertEqual(Model.catalogueControlState(controls.more, in: controls, hasCallback: false), .shownStatic)

        // Blank words draw nothing; a blank, shared or unavailable id is static
        // words. A category sharing Show more's id makes both static.
        let hostile = CombatEventPageCatalogueControls10868(
            categoriesLabel: "Fight market category",
            categories: [Self.category("category.all", "All", selected: true),
                         Self.category("category.blank", "  "),
                         Self.category("category.twin", "Finish method"),
                         Self.category("category.twin", "Fighter rounds"),
                         Self.category(" ", "Knockout chances"),
                         Self.category("catalogue.more", "Fight length"),
                         Self.category("category.winner", "Winner", available: false)],
            more: Self.action("catalogue.more", "Show more · 25 remaining"), context: " ")
        let shown = Model.shownCategories(hostile, hasCallback: true)
        XCTAssertEqual(shown.map(\.action.label),
                       ["All", "Finish method", "Fighter rounds", "Knockout chances", "Fight length", "Winner"])
        XCTAssertEqual(shown.map { Model.catalogueControlState($0.action, in: hostile, hasCallback: true) },
                       [.live(id: "category.all"), .shownStatic, .shownStatic, .shownStatic, .shownStatic, .shownStatic])
        XCTAssertEqual(Model.catalogueControlState(hostile.more, in: hostile, hasCallback: true), .shownStatic)
        XCTAssertNil(Model.readable(hostile.context))

        var log: [String] = []
        let view = CombatEventPagePresentation10868(
            input: Self.page(.final), mode: .catalogue, originals: Self.originals(.final, controls: hostile),
            onCatalogueCategory: { log.append("category:\($0)") }, onCatalogueMore: { log.append("more:\($0)") },
            onInteraction: { log.append("hold") })
        hostile.categories.forEach { view.categoryAction($0)?() }
        view.moreAction()?()
        XCTAssertEqual(log, ["hold", "category:category.all"])

        // No controls supplied (existing callers): nothing to act on, and the
        // catalogue is exactly as before.
        let bare = CombatEventPagePresentation10868(input: Self.page(.final), mode: .catalogue,
                                                    originals: Self.originals(.final),
                                                    onCatalogueCategory: { log.append("category:\($0)") },
                                                    onCatalogueMore: { log.append("more:\($0)") },
                                                    onInteraction: { log.append("hold") })
        XCTAssertNil(Self.originals(.final).controls)
        XCTAssertNil(bare.moreAction())
        XCTAssertEqual(bare.catalogueContent()?.catalogue, Self.originals(.final).catalogue)
        XCTAssertEqual(log, ["hold", "category:category.all"])

        // The arrangement the view switches on: an adaptive wrapping grid of
        // equal-width controls, one full-width control per row at accessibility sizes.
        XCTAssertEqual(Model.categoryArrangement(accessibilitySize: false), .wrapping)
        XCTAssertEqual(Model.categoryArrangement(accessibilitySize: true), .stacked)
    }
}
