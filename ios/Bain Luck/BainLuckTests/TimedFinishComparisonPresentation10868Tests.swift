import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the Olympic 500m final card's actual finish gaps beside each
/// skater's own earlier gold chance, as a stateless leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: exact scoped result resolution, the owner's visible
/// group order, one shared gap axis, bar refusals, the selected reading's
/// independent subjects, the actions each control hands back, the compact and
/// accessibility arrangement choices and the spoken summaries. Nothing here
/// claims a rendered fit, a native runtime, VoiceOver behaviour or a
/// held-update qualification.
///
/// ARCHIVED raw values come from Winter Games 2026 Speed Skating Women's 500m
/// (event 200646), as retained in
/// `shipping-adoption-20261027/TIMED-FINISH-RETAINED-CASES.json`
/// (sha256 fe4fdcb1…b84efd): all 29 reported finishers — result id, rank,
/// full name, country, exact reported time string and milliseconds, reported
/// gap and gap seconds — and, for the 17 with a linked gold prop, the
/// Polymarket Yes market id, token id and last retained trade before race day
/// (probability and its own clock). 12 have no linked gold prop, Takagi's
/// bronze among them. Kok 36.49 / 36490 ms, baseline 0.7799999991 at
/// 1771109125; Wójcik and Chen tied 11th at 37.914; Kim 38.010 and Boersma
/// 38.013 stay distinct. The 29 owner group examples (top five reported
/// finishers plus the selected one when not already there) are the owner
/// projection's own selections.
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// scope string, every label and absence word, the standing words ("Gold",
/// "Tied 11th"), gap words (the reported gap plus "s"; "Winner" for Kok), the
/// percent figure text and Milan clock line of each gold reading, the gold
/// originals' scope/source strings, each group's axis upper end (the
/// reference's 0.9-or-next-tenth ceiling) and tick labels, the selected
/// words, and every withdrawn, duplicate, blank, foreign, off-axis and invalid
/// case. Provider token ids stand in for the production outcome identity the
/// owner still has to map.
final class TimedFinishComparisonPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    /// CONSTRUCTED opaque scopes.
    private static let scope = "olympics|200646|report"
    private static let goldScope = "polymarket|200646|gold"

    /// ARCHIVED: (result id, rank, name, country, time, ms, reported gap,
    /// gap seconds, Yes market id, Yes token id, before-race-day p, its clock).
    private static let finishers: [(id: String, rank: Int, name: String, country: String, time: String, ms: Int, reportedGap: String, gap: Double, marketID: String?, tokenID: String?, p: Double?, t: Int?)] = [
        ("0", 1, "Femke Kok", "Netherlands", "36.49", 36490, "", 0.0, "1347941", "8015203451758424254624644018470563478761525048434806320115142348030067468557", 0.7799999991, 1771109125),
        ("1", 2, "Jutta Leerdam", "Netherlands", "37.15", 37150, "+0.66", 0.66, "1347948", "79914460156377571131066368245251308998571925540235970541258802787200179848437", 0.2257564719, 1771107553),
        ("2", 3, "Miho Takagi", "Japan", "37.27", 37270, "+0.78", 0.78, nil, nil, nil, nil),
        ("3", 4, "Serena Pergher", "Italy", "37.30", 37300, "+0.81", 0.81, "1347952", "112764826100350613023415955892958715542256188524722567887553665786815759034589", 0.001, 1771109081),
        ("4", 5, "Erin Jackson", "United States", "37.32", 37320, "+0.83", 0.83, "1347949", "53304661739730347120669901078624402642379665537751793251399570729507588207289", 0.014, 1771107825),
        ("5", 6, "Kaja Ziomek-Nogal", "Poland", "37.39", 37390, "+0.90", 0.9, "1347955", "97791940625327001884259604224033053996905487851083039006363842758707099763010", 0.016, 1771107825),
        ("6", 7, "Béatrice Lamarche", "Canada", "37.53", 37530, "+1.04", 1.04, "1347960", "9308950558874653568417808775837977382512379211364090855641941572083682521316", 0.001, 1771109081),
        ("7", 8, "Sophie Warmuth", "Germany", "37.75", 37750, "+1.26", 1.26, "1347944", "9984284712541184249732166617584326758480231222016162863567347396996572234993", 0.004, 1771109127),
        ("8", 9, "Rio Yamada", "Japan", "37.78", 37780, "+1.29", 1.29, "1347954", "7360852252490635503902163256873444875528123877515272011089620729620308292093", 0.001, 1770948137),
        ("9", 10, "Lee Na-hyun", "South Korea", "37.86", 37860, "+1.37", 1.37, "1347943", "54470245468144884217138371516853294810987211731323940498288448311812758508755", 0.002, 1771109079),
        ("10", 11, "Andżelika Wójcik", "Poland", "37.914", 37914, "+1.42", 1.424, "1347945", "34219849858976950145342334651143152652869502729803539303931285897587276023621", 0.001, 1771109083),
        ("11", 11, "Chen Ying-chu", "Chinese Taipei", "37.914", 37914, "+1.42", 1.424, "1347957", "5264409802799244007835773237536735658553673679612683564394820677313362076225", 0.001, 1771109153),
        ("12", 13, "Yukino Yoshida", "Japan", "37.98", 37980, "+1.49", 1.49, "1347942", "80757224497303745581312684734267598582183119004792363331312432200956841867750", 0.007, 1771108789),
        ("13", 14, "Kim Min-sun", "South Korea", "38.010", 38010, "+1.52", 1.52, "1347950", "59185097511900317797207472791119465676284870440372333737358127870713564592186", 0.002, 1771109149),
        ("14", 15, "Anna Boersma", "Netherlands", "38.013", 38013, "+1.52", 1.523, "1347956", "5730199196272005366858957280272156121753635672685108219725579760286712479376", 0.005, 1771108779),
        ("15", 16, "Tian Ruining", "China", "38.14", 38140, "+1.65", 1.65, "1347958", "108483596313252950585997338627933686840246112149685728601645115544202163432774", 0.001, 1771109079),
        ("16", 17, "Martyna Baran", "Poland", "38.15", 38150, "+1.66", 1.66, "1347953", "58965699085436488888710276609270231808986263341433545921203562032269946965555", 0.001, 1771109083),
        ("17", 18, "Kristina Silaeva", "Kazakhstan", "38.33", 38330, "+1.84", 1.84, "1347951", "94208938346537204255140774934705269587933953284504286976483801855798523496760", 0.001, 1771108949),
        ("18", 19, "Brooklyn McDougall", "Canada", "38.36", 38360, "+1.87", 1.87, nil, nil, nil, nil),
        ("19", 20, "Julie Nistad Samsonsen", "Norway", "38.37", 38370, "+1.88", 1.88, nil, nil, nil, nil),
        ("20", 21, "Carolina Hiller", "Canada", "38.38", 38380, "+1.89", 1.89, nil, nil, nil, nil),
        ("21", 22, "Wang Jingziqian", "China", "38.57", 38570, "+2.08", 2.08, nil, nil, nil, nil),
        ("22", 23, "Fran Vanhoutte", "Belgium", "38.63", 38630, "+2.14", 2.14, nil, nil, nil, nil),
        ("23", 24, "Maybritt Vigl", "Italy", "38.66", 38660, "+2.17", 2.17, nil, nil, nil, nil),
        ("24", 25, "Ellia Smeding", "Great Britain", "38.93", 38930, "+2.44", 2.44, nil, nil, nil, nil),
        ("25", 26, "Nikola Zdráhalová", "Czech Republic", "39.00", 39000, "+2.51", 2.51, nil, nil, nil, nil),
        ("26", 27, "Anna Ostlender", "Germany", "39.02", 39020, "+2.53", 2.53, nil, nil, nil, nil),
        ("27", 28, "Sarah Warren", "United States", "39.19", 39190, "+2.70", 2.7, nil, nil, nil, nil),
        ("28", 29, "Arina Ilyachshenko", "Kazakhstan", "39.38", 39380, "+2.89", 2.89, nil, nil, nil, nil),
    ]

    /// ARCHIVED owner selections, with the CONSTRUCTED axis upper end for each.
    private static let groups: [(selected: String, ids: [String], upper: Double)] = [
        ("0", ["0", "1", "2", "3", "4"], 0.9),
        ("1", ["0", "1", "2", "3", "4"], 0.9),
        ("2", ["0", "1", "2", "3", "4"], 0.9),
        ("3", ["0", "1", "2", "3", "4"], 0.9),
        ("4", ["0", "1", "2", "3", "4"], 0.9),
        ("5", ["0", "1", "2", "3", "4", "5"], 0.9),
        ("6", ["0", "1", "2", "3", "4", "6"], 1.1),
        ("7", ["0", "1", "2", "3", "4", "7"], 1.3),
        ("8", ["0", "1", "2", "3", "4", "8"], 1.3),
        ("9", ["0", "1", "2", "3", "4", "9"], 1.4),
        ("10", ["0", "1", "2", "3", "4", "10"], 1.5),
        ("11", ["0", "1", "2", "3", "4", "11"], 1.5),
        ("12", ["0", "1", "2", "3", "4", "12"], 1.5),
        ("13", ["0", "1", "2", "3", "4", "13"], 1.6),
        ("14", ["0", "1", "2", "3", "4", "14"], 1.6),
        ("15", ["0", "1", "2", "3", "4", "15"], 1.7),
        ("16", ["0", "1", "2", "3", "4", "16"], 1.7),
        ("17", ["0", "1", "2", "3", "4", "17"], 1.9),
        ("18", ["0", "1", "2", "3", "4", "18"], 1.9),
        ("19", ["0", "1", "2", "3", "4", "19"], 1.9),
        ("20", ["0", "1", "2", "3", "4", "20"], 1.9),
        ("21", ["0", "1", "2", "3", "4", "21"], 2.1),
        ("22", ["0", "1", "2", "3", "4", "22"], 2.2),
        ("23", ["0", "1", "2", "3", "4", "23"], 2.2),
        ("24", ["0", "1", "2", "3", "4", "24"], 2.5),
        ("25", ["0", "1", "2", "3", "4", "25"], 2.6),
        ("26", ["0", "1", "2", "3", "4", "26"], 2.6),
        ("27", ["0", "1", "2", "3", "4", "27"], 2.7),
        ("28", ["0", "1", "2", "3", "4", "28"], 2.9),
    ]

    private static func ref(_ id: String, scope: String = scope) -> TimedFinishResultRef10868 {
        TimedFinishResultRef10868(scope: scope, resultID: id)
    }

    /// CONSTRUCTED standing words.
    private static func standing(_ rank: Int, id: String) -> String {
        if ["10", "11"].contains(id) { return "Tied 11th" }
        switch rank {
        case 1: return "Gold"
        case 2: return "Silver"
        case 3: return "Bronze"
        default:
            let suffix = (11...13).contains(rank % 100) ? "th" : [1: "st", 2: "nd", 3: "rd"][rank % 10] ?? "th"
            return "\(rank)\(suffix)"
        }
    }

    /// CONSTRUCTED figure text and Milan clock line for an archived trade.
    private static func goldReading(p: Double?, t: Int?) -> FieldChooserReading10868 {
        let label = "Gold chance before race day"
        guard let p, let t else { return FieldChooserReading10868(label: label, value: .missing("No linked gold prop")) }
        let figure = p < 0.1 ? String(format: "%.1f%%", p * 100) : String(format: "%.0f%%", p * 100)
        let formatter = DateFormatter()
        formatter.locale = Locale(identifier: "en_US_POSIX")
        formatter.timeZone = TimeZone(identifier: "Europe/Rome")
        formatter.dateFormat = "MMM d, h:mm a"
        let clock = formatter.string(from: Date(timeIntervalSince1970: TimeInterval(t)))
        return FieldChooserReading10868(label: label, value: .recorded(text: figure, detail: "\(clock) Milan · Polymarket"))
    }

    private static func result(_ row: (id: String, rank: Int, name: String, country: String, time: String, ms: Int, reportedGap: String, gap: Double, marketID: String?, tokenID: String?, p: Double?, t: Int?)) -> TimedFinishResult10868 {
        TimedFinishResult10868(
            ref: ref(row.id),
            name: row.name,
            detail: row.country,
            time: row.time,
            standing: standing(row.rank, id: row.id),
            gap: TimedFinishGap10868(seconds: row.gap, text: row.reportedGap.isEmpty ? "Winner" : "\(row.reportedGap)s"),
            goldChance: goldReading(p: row.p, t: row.t),
            original: row.marketID.flatMap { market in
                row.tokenID.map { FieldChooserOriginalRef10868(scope: goldScope, source: "polymarket", marketID: market, outcomeID: $0) }
            }
        )
    }

    private static let catalogue: [TimedFinishResult10868] = finishers.map(result)

    private static func finisher(_ id: String) -> (id: String, rank: Int, name: String, country: String, time: String, ms: Int, reportedGap: String, gap: Double, marketID: String?, tokenID: String?, p: Double?, t: Int?) {
        finishers.first { $0.id == id }!
    }

    /// CONSTRUCTED owner axis: 0, half and the upper end.
    private static func axis(_ upper: Double) -> TimedFinishAxis10868 {
        TimedFinishAxis10868(upper: upper, ticks: [0, upper / 2, upper].map {
            TimedFinishTick10868(seconds: $0, label: String(format: "%.2fs", $0))
        })
    }

    private static let copy = TimedFinishCopy10868(
        eyebrow: "ACTUAL RACE · SECONDS",
        title: "Hundredths from a medal",
        timeUnit: "s",
        timeLabel: "Actual time",
        timeSpokenUnit: "seconds",
        standingLabel: "Reported",
        gapLabel: "Time behind gold · shorter is faster",
        graphicLabel: "Actual time behind gold",
        distinction: "Finishing times, not probabilities",
        noGap: "Gap not reported",
        offAxis: "Not drawn on this scale",
        axisUnavailable: "Times listed without the scale",
        empty: "No reported finishers in this view",
        note: "Pergher missed bronze by 0.03s; Jackson by 0.05s.",
        openOriginal: "Explore this skater’s gold history",
        openOriginalHint: "Opens the original gold prop",
        noOriginal: "No linked gold prop for this skater",
        chooseHint: "Shows this skater above"
    )

    private static func input(
        selected id: String? = "0",
        selectedScope: String = scope,
        group: [TimedFinishResultRef10868]? = nil,
        catalogue: [TimedFinishResult10868] = catalogue,
        axis: TimedFinishAxis10868? = axis(0.9)
    ) -> TimedFinishInput10868 {
        TimedFinishInput10868(
            scope: scope,
            catalogue: catalogue,
            selected: id.map { TimedFinishSelected10868(ref: ref($0, scope: selectedScope), words: "Selected", unavailableWords: "This result is unavailable in this update") },
            group: group ?? ["0", "1", "2", "3", "4"].map { ref($0) },
            axis: axis,
            copy: copy,
            unavailableWords: "Result unavailable in this update"
        )
    }

    private func placed(_ bar: TimedFinishBar10868, file: StaticString = #filePath, line: UInt = #line) -> Double? {
        guard case .placed(let fraction) = bar else {
            XCTFail("expected a placed bar, got \(bar)", file: file, line: line)
            return nil
        }
        return fraction
    }

    // MARK: Catalogue

    func testAll29ReportedResultsKeepExactTimesIdentitiesAndSourceLinks() {
        let finishers = Self.finishers
        XCTAssertEqual(finishers.count, 29)
        XCTAssertEqual(Set(finishers.map(\.id)).count, 29)
        XCTAssertEqual(finishers.filter { $0.marketID != nil }.count, 17)
        XCTAssertEqual(finishers.filter { $0.marketID == nil }.count, 12)
        // Market, token and baseline travel together or not at all.
        XCTAssertTrue(finishers.allSatisfy { ($0.marketID == nil) == ($0.tokenID == nil) && ($0.tokenID == nil) == ($0.p == nil) })

        let model = TimedFinishModel10868(Self.input())
        for row in finishers {
            guard let result = model.resolve(Self.ref(row.id)).result else { return XCTFail("\(row.name) did not resolve") }
            XCTAssertEqual(result.name, row.name)
            XCTAssertEqual(result.time, row.time, "the exact reported string is shown verbatim")
            XCTAssertTrue(model.spoken(result).contains("Actual time: \(row.time) seconds"))
            XCTAssertEqual(result.original?.marketID, row.marketID)
            XCTAssertEqual(result.original?.outcomeID, row.tokenID)
        }
        let kok = model.resolve(Self.ref("0")).result
        XCTAssertEqual(kok?.time, "36.49")
        XCTAssertEqual(Self.finisher("0").ms, 36490)
        XCTAssertEqual(Self.finisher("0").p, 0.7799999991)
        XCTAssertEqual(Self.finisher("0").t, 1771109125)
        XCTAssertEqual(kok?.goldChance.value, .recorded(text: "78%", detail: "Feb 14, 11:45 PM Milan · Polymarket"))
    }

    func testOwnerGroupsKeepTopFivePlusTheSelectedOutlierInOrderOnOneAxis() {
        XCTAssertEqual(Self.groups.count, 29)
        for group in Self.groups {
            let refs = group.ids.map { Self.ref($0) }
            let model = TimedFinishModel10868(Self.input(selected: group.selected, group: refs, axis: Self.axis(group.upper)))
            let rows = model.rows
            XCTAssertEqual(rows.map(\.ref), refs, "the owner's order, never sorted or capped")
            XCTAssertEqual(rows.filter { $0.resolution.result.map(model.isSelected) == true }.map(\.ref.resultID), [group.selected])
            for row in rows {
                guard let fraction = placed(row.bar) else { continue }
                XCTAssertEqual(fraction, Self.finisher(row.ref.resultID).gap / group.upper, accuracy: 1e-12, "one shared scale, never per row")
            }
        }
        // An outlier keeps its own bar on the group's axis.
        let outlier = TimedFinishModel10868(Self.input(selected: "28", group: Self.groups[28].ids.map { Self.ref($0) }, axis: Self.axis(2.9)))
        XCTAssertEqual(outlier.rows.count, 6)
        XCTAssertEqual(placed(outlier.rows[5].bar) ?? -1, 2.89 / 2.9, accuracy: 1e-12)
        XCTAssertEqual(outlier.ticks.map(\.label), ["0.00s", "1.45s", "2.90s"])
    }

    // MARK: Subjects

    func testTakagiBronzeAndEveryUnlinkedFinisherKeepAbsenceWordsWithNoInferredChanceOrAction() {
        let model = TimedFinishModel10868(Self.input(selected: "2"))
        let takagi = model.selectedResult
        XCTAssertEqual(takagi?.standing, "Bronze")
        XCTAssertEqual(takagi?.time, "37.27")
        XCTAssertEqual(takagi?.goldChance.value, .missing("No linked gold prop"), "never inferred from a medal")
        XCTAssertNil(model.openAction(canOpen: true))
        XCTAssertEqual(model.noOriginalWords, "No linked gold prop for this skater")
        XCTAssertEqual(model.heroSummary, "Miho Takagi. Actual time: 37.27 seconds. Reported: Bronze. Gold chance before race day: No linked gold prop")
        XCTAssertFalse(model.heroSummary?.contains("0%") ?? true, "missing is words, not zero")

        for row in Self.finishers where row.marketID == nil {
            let unlinked = TimedFinishModel10868(Self.input(selected: row.id))
            XCTAssertEqual(unlinked.selectedResult?.goldChance.value, .missing("No linked gold prop"), row.name)
            XCTAssertNil(unlinked.openAction(canOpen: true), row.name)
        }
    }

    func testTiedEleventhAndThreeMillisecondNeighboursStayDistinct() {
        let model = TimedFinishModel10868(Self.input(selected: "11", group: ["10", "11", "13", "14"].map { Self.ref($0) }, axis: Self.axis(1.6)))
        let rows = model.rows
        let wojcik = rows[0].resolution.result, chen = rows[1].resolution.result
        XCTAssertEqual(wojcik?.name, "Andżelika Wójcik")
        XCTAssertEqual(chen?.name, "Chen Ying-chu")
        XCTAssertEqual(wojcik?.time, "37.914")
        XCTAssertEqual(chen?.time, "37.914")
        XCTAssertEqual(wojcik?.standing, "Tied 11th")
        XCTAssertNotEqual(wojcik?.ref, chen?.ref)
        XCTAssertEqual(model.selectedResult?.name, "Chen Ying-chu", "a tie never swaps the selected skater")
        XCTAssertEqual(model.chooseAction(rows[1], canChoose: true), Self.ref("11"))
        XCTAssertEqual(model.chooseAction(rows[0], canChoose: true), Self.ref("10"))
        // The owner's gap words stay "+1.42s" while the bar uses 1.424 seconds.
        XCTAssertEqual(wojcik.map(model.gapWords), "+1.42s")
        XCTAssertEqual(placed(rows[0].bar) ?? -1, 1.424 / 1.6, accuracy: 1e-12)

        XCTAssertEqual(rows[2].resolution.result?.time, "38.010")
        XCTAssertEqual(rows[3].resolution.result?.time, "38.013")
        XCTAssertEqual(Self.finisher("13").ms, 38010)
        XCTAssertEqual(Self.finisher("14").ms, 38013)
        XCTAssertNotEqual(placed(rows[2].bar), placed(rows[3].bar), "3 ms apart are two bars, never merged")
    }

    func testSecondsAndChancesNeverSubstituteForEachOther() {
        // Takagi is 0.78 s behind gold; Kok's gold chance is 0.78.
        let model = TimedFinishModel10868(Self.input())
        let kok = model.resolve(Self.ref("0")).result!
        let takagi = model.resolve(Self.ref("2")).result!
        XCTAssertEqual(placed(model.bar(kok)) ?? -1, 0, "the winner's bar is her gap, not her chance")
        XCTAssertEqual(placed(model.bar(takagi)) ?? -1, 0.78 / 0.9, accuracy: 1e-12)
        XCTAssertEqual(takagi.goldChance.value, .missing("No linked gold prop"), "a gap never becomes a chance")

        // Changing one subject leaves the other untouched.
        var catalogue = Self.catalogue
        catalogue[0] = TimedFinishResult10868(
            ref: kok.ref, name: kok.name, detail: kok.detail, time: kok.time, standing: kok.standing, gap: kok.gap,
            goldChance: FieldChooserReading10868(label: "Gold chance before race day", value: .recorded(text: "5%", detail: "Constructed")),
            original: kok.original
        )
        let changed = TimedFinishModel10868(Self.input(catalogue: catalogue))
        XCTAssertEqual(changed.bar(changed.resolve(kok.ref).result!), model.bar(kok))
        XCTAssertEqual(changed.selectedResult?.time, "36.49")
        XCTAssertFalse(model.spoken(kok).contains("36.49%"))
        XCTAssertFalse(model.spoken(kok).contains("78 seconds"))
    }

    // MARK: Geometry

    func testARealZeroKeepsItsEndpointAndInvalidGapsOrAxesDrawNoPlausibleBar() {
        let size = CGSize(width: 300, height: 16)
        let zero = TimedFinishGeometry10868.barPlan(fraction: 0, ticks: [0.5, 1], in: size, inset: 6, barHeight: 12, endpointDiameter: 10)
        XCTAssertEqual(zero?.bar.width, 0)
        XCTAssertEqual(zero?.endpoint.midX, 6, "a real zero keeps its zero endpoint")
        XCTAssertEqual(zero?.tickXs, [6, 150, 294])
        let full = TimedFinishGeometry10868.barPlan(fraction: 1, ticks: [], in: size, inset: 6, barHeight: 12, endpointDiameter: 10)
        XCTAssertEqual(full?.endpoint.midX, 294)
        for fraction in [-0.01, 1.01, .nan, .infinity] as [Double] {
            XCTAssertNil(TimedFinishGeometry10868.barPlan(fraction: fraction, ticks: [], in: size, inset: 6, barHeight: 12, endpointDiameter: 10), "\(fraction)")
        }
        XCTAssertNil(TimedFinishGeometry10868.barPlan(fraction: 0.5, ticks: [], in: CGSize(width: 10, height: 16), inset: 6, barHeight: 12, endpointDiameter: 10))
        XCTAssertNil(TimedFinishGeometry10868.barPlan(fraction: 0.5, ticks: [], in: CGSize(width: 300, height: 8), inset: 6, barHeight: 12, endpointDiameter: 10))

        // Constructed hostile gaps on Leerdam's row.
        let leerdam = Self.catalogue[1]
        let hostile: [(Double, TimedFinishBar10868)] = [(-0.1, .offAxis), (.nan, .offAxis), (.infinity, .offAxis), (0.91, .offAxis)]
        for (seconds, expected) in hostile {
            var catalogue = Self.catalogue
            catalogue[1] = TimedFinishResult10868(ref: leerdam.ref, name: leerdam.name, detail: leerdam.detail, time: leerdam.time, standing: leerdam.standing,
                                                  gap: TimedFinishGap10868(seconds: seconds, text: "+0.66s"), goldChance: leerdam.goldChance, original: leerdam.original)
            let model = TimedFinishModel10868(Self.input(catalogue: catalogue))
            XCTAssertEqual(model.rows[1].bar, expected, "\(seconds)")
            XCTAssertEqual(model.gapWords(catalogue[1]), "Not drawn on this scale")
            XCTAssertEqual(model.rows[1].resolution.result?.time, "37.15", "the exact time stays listed")
        }
        var noGap = Self.catalogue
        noGap[1] = TimedFinishResult10868(ref: leerdam.ref, name: leerdam.name, detail: leerdam.detail, time: leerdam.time, standing: leerdam.standing,
                                          gap: nil, goldChance: leerdam.goldChance, original: leerdam.original)
        XCTAssertEqual(TimedFinishModel10868(Self.input(catalogue: noGap)).rows[1].bar, .noGap)

        // An invalid axis draws no bar for anyone; every row stays readable.
        for axis in [nil, TimedFinishAxis10868(upper: 0, ticks: []), TimedFinishAxis10868(upper: .nan, ticks: []), TimedFinishAxis10868(upper: -1, ticks: [])] as [TimedFinishAxis10868?] {
            let model = TimedFinishModel10868(Self.input(axis: axis))
            XCTAssertNil(model.visibleAxis)
            XCTAssertTrue(model.rows.allSatisfy { $0.bar == .noAxis })
            XCTAssertTrue(model.ticks.isEmpty)
            XCTAssertTrue(model.rowSummary(model.rows[2]).contains("Actual time: 37.27 seconds"))
        }
        // Ticks off the axis or without words are left out, never clamped.
        let ticks = TimedFinishModel10868(Self.input(axis: TimedFinishAxis10868(upper: 0.9, ticks: [
            TimedFinishTick10868(seconds: 0, label: "0s"), TimedFinishTick10868(seconds: 1.2, label: "1.2s"),
            TimedFinishTick10868(seconds: -0.1, label: "-0.1s"), TimedFinishTick10868(seconds: 0.45, label: " ")
        ]))).ticks
        XCTAssertEqual(ticks, [TimedFinishPlacedTick10868(fraction: 0, label: "0s")])
    }

    /// CONSTRUCTED measured label sizes: the leaf hands its own tick
    /// fractions and endpoint inset to the shared measured axis layout.
    func testAxisLabelsAreMeasuredOntoTheBarInsetAndCollidingOrOversizedLabelsAreLeftOut() {
        let model = TimedFinishModel10868(Self.input())
        let ticks = model.ticks
        XCTAssertEqual(ticks.map(\.fraction), [0, 0.5, 1])
        XCTAssertEqual(ticks.map(\.label), ["0.00s", "0.45s", "0.90s"])
        let inset = FieldExpectationsGeometry10868.inset(markDiameter: 10)
        XCTAssertEqual(inset, 6, "the same inset the bars' endpoints use")
        func labels(_ size: CGSize, width: CGFloat) -> [CGRect?] {
            FieldExpectationsGeometry10868.axisLabels(ticks.map { FieldChaseMeasuredTick10868(unit: $0.fraction, size: size) }, width: width, inset: inset, spacing: 6)
        }

        // Standard type on a phone row: all three, slid inward at the ends.
        let standard = labels(CGSize(width: 30, height: 13), width: 343)
        XCTAssertEqual(standard, [CGRect(x: 0, y: 0, width: 30, height: 13), CGRect(x: 156.5, y: 0, width: 30, height: 13), CGRect(x: 313, y: 0, width: 30, height: 13)])
        let plan = TimedFinishGeometry10868.barPlan(fraction: 0.5, ticks: [0.5, 1], in: CGSize(width: 343, height: 16), inset: inset, barHeight: 12, endpointDiameter: 10)
        XCTAssertEqual(plan?.endpoint.midX, standard[1]?.midX, "a label centred on its mark sits over the bar at the same x")

        // Dense or accessibility type: the middle label collides and is left out.
        let dense = labels(CGSize(width: 50, height: 22), width: 120)
        XCTAssertEqual(dense, [CGRect(x: 0, y: 0, width: 50, height: 22), nil, CGRect(x: 70, y: 0, width: 50, height: 22)])
        XCTAssertEqual(FieldExpectationsGeometry10868.axisHeight(dense), 22)

        // A label wider than the row is never drawn overlapping; none placed.
        let oversized = labels(CGSize(width: 400, height: 22), width: 343)
        XCTAssertEqual(oversized, [nil, nil, nil])
        XCTAssertEqual(FieldExpectationsGeometry10868.axisHeight(oversized), 0)
        // Leaving labels out never moves a bar.
        XCTAssertEqual(placed(model.rows[2].bar) ?? -1, 0.78 / 0.9, accuracy: 1e-12)
    }

    // MARK: Identity

    func testUnknownForeignDuplicateWithdrawnAndBlankReferencesBorrowNothing() {
        var duplicated = Self.catalogue
        duplicated.append(Self.catalogue[3])
        let withdrawn = Self.catalogue.filter { $0.ref.resultID != "4" }
        let cases: [(String, TimedFinishInput10868)] = [
            ("unknown", Self.input(selected: "99", group: ["0", "99", "1"].map { Self.ref($0) })),
            ("foreign", Self.input(selected: "1", selectedScope: "olympics|200647|report", group: [Self.ref("0"), Self.ref("1", scope: "olympics|200647|report"), Self.ref("2")])),
            ("duplicate", Self.input(selected: "3", group: ["0", "3", "1"].map { Self.ref($0) }, catalogue: duplicated)),
            ("withdrawn", Self.input(selected: "4", group: ["0", "4", "1"].map { Self.ref($0) }, catalogue: withdrawn)),
            ("blank", Self.input(selected: " ", group: ["0", " ", "1"].map { Self.ref($0) }))
        ]
        for (name, input) in cases {
            let model = TimedFinishModel10868(input)
            XCTAssertNil(model.selectedResult, name)
            XCTAssertEqual(model.selectionNotice, "This result is unavailable in this update", name)
            XCTAssertEqual(model.heroSummary, "This result is unavailable in this update", name)
            XCTAssertNil(model.openAction(canOpen: true), name)
            XCTAssertNil(model.noOriginalWords, name)
            let rows = model.rows
            XCTAssertEqual(rows[1].resolution, .unavailable, name)
            XCTAssertEqual(rows[1].bar, .noAxis, name)
            XCTAssertNil(model.chooseAction(rows[1], canChoose: true), name)
            XCTAssertEqual(model.rowSummary(rows[1]), "Result unavailable in this update", name)
            // Neighbours keep their own results; nothing is substituted.
            XCTAssertEqual(rows[0].resolution.result?.name, "Femke Kok", name)
            XCTAssertNotNil(rows[2].resolution.result, name)
            XCTAssertFalse(rows.contains { $0.resolution.result.map(model.isSelected) == true }, name)
        }
        // An empty group shows the owner's words, never a default row.
        XCTAssertTrue(TimedFinishModel10868(Self.input(group: [])).rows.isEmpty)
    }

    // MARK: Actions

    func testCallbacksHandBackExactIdentitiesAndAbsentCallbacksAreStatic() {
        let model = TimedFinishModel10868(Self.input(selected: "1"))
        let rows = model.rows
        for row in rows {
            XCTAssertEqual(model.chooseAction(row, canChoose: true), row.ref)
            XCTAssertNil(model.chooseAction(row, canChoose: false))
        }
        let leerdam = Self.finisher("1")
        XCTAssertEqual(model.openAction(canOpen: true), FieldChooserOriginalRef10868(scope: Self.goldScope, source: "polymarket", marketID: "1347948", outcomeID: leerdam.tokenID!))
        XCTAssertNil(model.openAction(canOpen: false))
        XCTAssertNil(model.noOriginalWords)

        // An incomplete original is not an identity: words, no action.
        var catalogue = Self.catalogue
        let row = catalogue[1]
        catalogue[1] = TimedFinishResult10868(ref: row.ref, name: row.name, detail: row.detail, time: row.time, standing: row.standing, gap: row.gap, goldChance: row.goldChance,
                                              original: FieldChooserOriginalRef10868(scope: Self.goldScope, source: "polymarket", marketID: "1347948", outcomeID: " "))
        let incomplete = TimedFinishModel10868(Self.input(selected: "1", catalogue: catalogue))
        XCTAssertNil(incomplete.openAction(canOpen: true))
        XCTAssertEqual(incomplete.noOriginalWords, "No linked gold prop for this skater")

        var chosen: [TimedFinishResultRef10868] = []
        var opened: [FieldChooserOriginalRef10868] = []
        let live = TimedFinishComparisonPresentation10868(input: Self.input(selected: "1"), onChooseResult: { chosen.append($0) }, onOpenOriginal: { opened.append($0) })
        live.onChooseResult?(Self.ref("13"))
        live.onOpenOriginal?(model.openAction(canOpen: true)!)
        XCTAssertEqual(chosen, [Self.ref("13")])
        XCTAssertEqual(opened.map(\.outcomeID), [leerdam.tokenID!])
        let still = TimedFinishComparisonPresentation10868(input: Self.input(selected: "1"))
        XCTAssertNil(still.onChooseResult)
        XCTAssertNil(still.onOpenOriginal)
    }

    // MARK: Layout and speech

    func testCompactAndAccessibilityArrangementChoices() {
        XCTAssertEqual(TimedFinishGeometry10868.heroArrangement(accessibilitySize: false, chanceIsWords: false), .fitting)
        XCTAssertEqual(TimedFinishGeometry10868.heroArrangement(accessibilitySize: true, chanceIsWords: false), .stacked)
        XCTAssertEqual(TimedFinishGeometry10868.heroArrangement(accessibilitySize: false, chanceIsWords: true), .stacked)
        XCTAssertFalse(TimedFinishGeometry10868.stacksRowHeading(accessibilitySize: false))
        XCTAssertTrue(TimedFinishGeometry10868.stacksRowHeading(accessibilitySize: true))
    }

    func testSpokenSummariesSayActualSecondsReportedStandingAndTheDatedGoldChance() {
        let model = TimedFinishModel10868(Self.input())
        XCTAssertEqual(
            model.rowSummary(model.rows[0]),
            "Selected. Femke Kok. Actual time: 36.49 seconds. Reported: Gold. Gold chance before race day: 78%, Feb 14, 11:45 PM Milan · Polymarket. Winner"
        )
        XCTAssertEqual(
            model.rowSummary(model.rows[3]),
            "Serena Pergher. Actual time: 37.30 seconds. Reported: 4th. Gold chance before race day: 0.1%, Feb 14, 11:44 PM Milan · Polymarket. +0.81s"
        )
        XCTAssertEqual(model.heroSummary, "Femke Kok. Actual time: 36.49 seconds. Reported: Gold. Gold chance before race day: 78%, Feb 14, 11:45 PM Milan · Polymarket")
    }
}
