import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the golf chart's golfer-chooser content as a stateless leaf.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to: exact scoped identity resolution for every section and
/// the selected cue, the action each control carries, owner-controlled
/// expansion and groups, the display plan's independent readings, the shared
/// preview frame and its path breaks, the card arrangement decision and the
/// spoken summaries. Nothing here claims a rendered fit, a native runtime,
/// VoiceOver behaviour or a held-update qualification.
///
/// ARCHIVED raw values come from the Baycurrent Classic winner market 64266833
/// (datagolf, external id datagolf:pga:527:win), as retained in
/// `shipping-adoption-20261027/FIELD-CHOOSER-RETAINED-CASES.json`
/// (sha256 9091fbea…ecc8f): 155 original outcome ids and names, 13 with raw
/// history in this capture and 142 without. History observations come from
/// `FIELD-HISTORY-RETAINED-CASES.json` (sha256 2ef025c5…6158):
///   Michael Brennan     241857512  before 0.026017 @2026-10-06T13:08:40Z;
///                       R4 0.161117 @10-11T00:02:37Z, 0.137681 @03:27:57Z,
///                       1.0 @06:41:26Z (first 100% record); final 1, -16
///   Xander Schauffele   242242520  before 0.086583 @10-06T13:08:40Z;
///                       0.0 @2026-10-11T06:06:55Z (a real zero); final T4
///   Keith Mitchell      242242559  before 0.012733 @10-06T13:08:40Z;
///                       0.469608 @2026-10-11T03:27:57Z; final T2
///   Michael Thorbjornsen 242242545 no history in this capture; its metadata
///                       probability 0.025133 / opening 0.02525 are NOT readings
///
/// CONSTRUCTED owner-resolved inputs (this leaf does not resolve them): the
/// scope string, the six band groups (the packet's fixture-only recomputation
/// of the prototype's surname heuristic, incl. two compound-name exceptions —
/// not provider sort-name evidence), every label, figure text, PT clock line,
/// provenance, movement and result word, the featured/More membership, the
/// selected/pinned identity and its words, expansion and group state, the
/// frame (hours from 2026-10-08T00:00Z, domain 0…79, zero-based ceiling 0.5),
/// segment and gap assignment, the emphasized observation, withdrawn,
/// duplicate, blank and out-of-scope cases, and every measured width.
final class FieldContenderChooserPresentation10868Tests: XCTestCase {

    // MARK: Fixtures

    /// CONSTRUCTED opaque scope.
    private static let scope = "datagolf|64266833|week"

    private static let brennan = "241857512"
    private static let schauffele = "242242520"
    private static let mitchell = "242242559"
    private static let thorbjornsen = "242242545"
    private static let vanRooyen = "241857586"
    private static let dumontDeChassart = "241857585"

    /// ARCHIVED: all 155 originals of market 64266833 in packet order —
    /// (outcome id, name, raw history in this capture).
    private static let field: [(id: String, name: String, history: Bool)] = [
        ("242242520", "Xander Schauffele", true),
        ("242242522", "Wyndham Clark", true),
        ("242242527", "Collin Morikawa", true),
        ("242242528", "Justin Thomas", true),
        ("242242532", "Ryan Gerard", true),
        ("242242534", "Hideki Matsuyama", true),
        ("241857513", "Doug Ghim", true),
        ("242242535", "Min Woo Lee", true),
        ("242242537", "Adam Scott", true),
        ("241857514", "Maverick McNealy", true),
        ("242242539", "Jacob Bridgeman", true),
        ("241857512", "Michael Brennan", true),
        ("242242545", "Michael Thorbjornsen", false),
        ("242242546", "Sungjae Im", false),
        ("242242542", "Kurt Kitayama", false),
        ("241857515", "Matt Wallace", false),
        ("241857522", "Johnny Keefer", false),
        ("242242549", "Keegan Bradley", false),
        ("241857519", "Kevin Yu", false),
        ("241857517", "Jackson Suber", false),
        ("242242554", "Rickie Fowler", false),
        ("242242553", "Alex Smalley", false),
        ("242242555", "Keita Nakajima", false),
        ("242242557", "Ryo Hisatsune", false),
        ("242242559", "Keith Mitchell", true),
        ("241857545", "Steven Fisk", false),
        ("241857538", "Zach Bauchou", false),
        ("241857527", "Max Homa", false),
        ("241857524", "Kristoffer Ventura", false),
        ("242242563", "Jordan Spieth", false),
        ("241857518", "Jordan Smith", false),
        ("242242564", "Michael Kim", false),
        ("241857534", "Max Greyserman", false),
        ("241857520", "Davis Thompson", false),
        ("242242568", "Brian Harman", false),
        ("241857521", "Mac Meissner", false),
        ("241857531", "Kevin Roy", false),
        ("241857548", "Stephan Jaeger", false),
        ("241857549", "Lee Hodges", false),
        ("241857530", "Pierceson Coody", false),
        ("241857525", "Beau Hossler", false),
        ("242242573", "Ricky Castillo", false),
        ("242242578", "Sahith Theegala", false),
        ("241857533", "Ben Kohles", false),
        ("241857543", "Christiaan Bezuidenhout", false),
        ("241857540", "Billy Horschel", false),
        ("241857536", "Rasmus Neergaard-Petersen", false),
        ("241857556", "Taylor Moore", false),
        ("241857544", "John Parry", false),
        ("241857542", "Nick Taylor", false),
        ("241857550", "Matt McCarty", false),
        ("241857571", "Takumi Kanaya", false),
        ("241857562", "Aldrich Potgieter", false),
        ("242242596", "Nico Echavarria", false),
        ("241857551", "Chandler Phillips", false),
        ("242242594", "Taylor Pendrith", false),
        ("241857567", "Tony Finau", false),
        ("241857561", "Denny McCarthy", false),
        ("241857576", "Patrick Rodgers", false),
        ("242242598", "Jinichiro Kozuma", false),
        ("242242604", "Hiroshi Iwata", false),
        ("241857577", "Andrew Putnam", false),
        ("241857591", "David Lipsky", false),
        ("242242600", "Yusaku Hosono", false),
        ("241857574", "Tom Hoge", false),
        ("242242602", "Sang-hee Lee", false),
        ("242242609", "Aguri Iwasaki", false),
        ("242242613", "Kosuke Sunagawa", false),
        ("242242616", "Yoshinori Fujimoto", false),
        ("242242611", "Ren Yonezawa", false),
        ("242242614", "Tomohiro Ishizaka", false),
        ("242242618", "Koshin Nagasaki", false),
        ("241857553", "Patrick Fishburn", false),
        ("241857622", "Brendon Todd", false),
        ("241857612", "C.T. Pan", false),
        ("241857564", "Hayden Springer", false),
        ("241857566", "Jesper Svensson", false),
        ("241857582", "Luke Clanton", false),
        ("241857589", "Kevin Streelman", false),
        ("241857587", "Ben Silverman", false),
        ("241857595", "Adam Svensson", false),
        ("241857625", "David Lingmerth", false),
        ("241857559", "Sudarshan Yellamaraju", false),
        ("241857539", "Emiliano Grillo", false),
        ("241857541", "Mackenzie Hughes", false),
        ("241857554", "Max McGreevy", false),
        ("241857573", "John VanDerLaan", false),
        ("241857575", "Mark Hubbard", false),
        ("241857594", "Joe Highsmith", false),
        ("241857617", "Nick Dunlap", false),
        ("241857586", "Erik Van Rooyen", false),
        ("241857606", "Alejandro Tosti", false),
        ("241857628", "Zach J. Johnson", false),
        ("241857526", "Chris Kirk", false),
        ("241857607", "Dylan Wu", false),
        ("241857569", "Isaiah Salinda", false),
        ("241857572", "Chandler Blanchet", false),
        ("241857581", "Davis Chatfield", false),
        ("241857603", "Harry Higgs", false),
        ("241857511", "Ben James", false),
        ("241857529", "Harry Hall", false),
        ("241857532", "Rasmus Hojgaard", false),
        ("241857535", "Neal Shipley", false),
        ("241857537", "Zecheng Dou", false),
        ("241857546", "Matthieu Pavon", false),
        ("241857547", "William Mouw", false),
        ("241857552", "Austin Smotherman", false),
        ("241857565", "Joel Dahmen", false),
        ("241857570", "Gordon Sargent", false),
        ("241857579", "Lucas Glover", false),
        ("241857580", "Pontus Nyholm", false),
        ("241857583", "Garrick Higgo", false),
        ("241857584", "Tyler Duncan", false),
        ("241857592", "Hank Lebioda", false),
        ("241857593", "David Skinns", false),
        ("241857600", "Danny Walker", false),
        ("241857602", "Peter Malnati", false),
        ("241857609", "Rafael Campos", false),
        ("241857613", "Patton Kizzire", false),
        ("241857614", "Vince Whaley", false),
        ("241857615", "Michael Thompson", false),
        ("241857619", "Boston Bracken", false),
        ("241857620", "Christo Lamprecht", false),
        ("241857621", "Carson Lundell", false),
        ("241857626", "Rhett Rasmussen", false),
        ("241857629", "Bowen Mauss", false),
        ("241857599", "Davis Riley", false),
        ("241857510", "Jackson Koivun", false),
        ("241857597", "Aaron Wise", false),
        ("241857616", "Kensei Hirata", false),
        ("241857623", "Matt Snyder", false),
        ("241857598", "Kihei Akina", false),
        ("241857578", "A.J. Ewart", false),
        ("241857596", "Ben Martin", false),
        ("241857516", "Marco Penge", false),
        ("241857523", "Eric Cole", false),
        ("241857528", "Rico Hoey", false),
        ("241857555", "Haotong Li", false),
        ("241857557", "David Ford", false),
        ("241857558", "Trace Crowe", false),
        ("241857563", "Zac Blair", false),
        ("241857585", "Adrien Dumont De Chassart", false),
        ("241857588", "Justin Lower", false),
        ("241857590", "Paul Peterson", false),
        ("241857604", "Jimmy Stanger", false),
        ("241857605", "Brice Garnett", false),
        ("241857608", "Jeffrey Kang", false),
        ("241857618", "Marcelo Rozo", false),
        ("241857601", "Will Gordon", false),
        ("241857568", "Chad Ramey", false),
        ("241857610", "Adam Schenk", false),
        ("241857611", "Cam Davis", false),
        ("241857560", "Seamus Power", false),
        ("241857627", "Seonghyeon An", false),
        ("241857624", "Tyson Shelley", false),
    ]

    /// CONSTRUCTED owner groups: the packet's six fixture-only band memberships
    /// in their recorded order (not provider sort-name evidence).
    private static let bands: [(id: String, label: String, members: [String])] = [
        ("constructed:band:0", "A–C", ["241857598", "241857627", "241857538", "241857543", "241857563", "241857572", "241857619", "242242549", "241857512", "242242539", "241857609", "242242573", "241857581", "241857582", "242242522", "241857523", "241857530", "241857558"]),
        ("constructed:band:1", "D–G", ["241857565", "241857611", "241857537", "241857585", "241857584", "241857617", "242242596", "241857578", "241857567", "241857553", "241857545", "241857557", "242242554", "242242616", "241857605", "242242532", "241857513", "241857579", "241857601", "241857534", "241857539"]),
        ("constructed:band:2", "H–L", ["241857529", "242242568", "241857583", "241857603", "241857594", "241857616", "242242557", "241857549", "241857528", "241857574", "241857532", "241857527", "241857540", "242242600", "241857525", "241857575", "241857541", "242242546", "242242614", "242242609", "242242604", "241857548", "241857511", "241857628", "241857571", "241857608", "241857522", "242242564", "241857526", "242242542", "241857613", "241857533", "241857510", "242242598", "241857620", "241857592", "242242535", "242242602", "241857555", "241857625", "241857591", "241857588", "241857621"]),
        ("constructed:band:3", "M–P", ["241857602", "241857596", "242242534", "241857629", "241857561", "241857550", "241857554", "241857514", "241857521", "242242559", "241857556", "242242527", "241857547", "242242618", "242242555", "241857536", "241857580", "241857612", "241857544", "241857546", "242242594", "241857516", "241857590", "241857551", "241857562", "241857560", "241857577"]),
        ("constructed:band:4", "Q–S", ["241857568", "241857626", "241857599", "241857576", "241857531", "241857618", "241857569", "241857570", "242242520", "241857610", "242242537", "241857624", "241857535", "241857587", "241857593", "242242553", "241857518", "241857552", "241857623", "242242563", "241857564", "241857604", "241857589", "241857517", "242242613", "241857595", "241857566"]),
        ("constructed:band:5", "T–Z", ["241857542", "242242578", "242242528", "241857520", "241857615", "242242545", "241857622", "241857606", "241857586", "241857573", "241857524", "241857600", "241857515", "241857614", "241857597", "241857607", "241857559", "242242611", "241857519"]),
    ]

    private static func ref(_ id: String, scope: String = FieldContenderChooserPresentation10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "datagolf", marketID: "64266833", outcomeID: id)
    }

    private static func name(_ id: String) -> String { field.first { $0.id == id }!.name }

    private static func p(_ hours: Double, _ probability: Double) -> FieldChooserPoint10868 {
        FieldChooserPoint10868(time: hours, probability: probability)
    }

    private static let beforeLabel = "Before tournament"
    private static let laterLabel = "Last in Round 4"
    private static let beforeDetail = "Oct 6, 6:08 AM PT · DataGolf"
    private static let noBefore = "Not recorded before the tournament"
    private static let noLater = "No recorded history in this view"
    private static let noHistory = "No captured history"
    private static let historyAvailable = "Recorded history available"
    private static let historyUnavailable = "History unavailable in this view"
    private static let kept = "Kept in view"
    private static let unavailable = "Golfer unavailable in this update"

    private static func reading(_ label: String, _ text: String, _ detail: String) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail))
    }

    private static func missing(_ label: String, _ words: String) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: label, value: .missing(words))
    }

    /// CONSTRUCTED from ARCHIVED Brennan records; the 1.0 record lies above the
    /// constructed 0.5 ceiling and must break the line, not clip.
    private static let brennanHistory = FieldChooserHistory10868(
        segments: [
            [p(0.0342, 0.024326), p(0.1870, 0.026065), p(3.7774, 0.027172)],
            [p(24.0317, 0.019567), p(24.1068, 0.020507), p(27.7816, 0.023996)],
            [p(48.0256, 0.033625), p(51.7007, 0.02315)],
            [p(72.0438, 0.161117), p(72.1188, 0.16231), p(75.4661, 0.137681), p(78.6906, 1.0)],
        ],
        emphasis: p(75.4661, 0.137681),
        beforeReference: 0.026017,
        gaps: [
            FieldChooserGap10868(start: 3.7774, end: 24.0317),
            FieldChooserGap10868(start: 27.7816, end: 48.0256),
            FieldChooserGap10868(start: 51.7007, end: 72.0438),
        ]
    )

    private static let schauffeleHistory = FieldChooserHistory10868(
        segments: [[p(72.0438, 0.019508), p(72.1188, 0.020276), p(75.0406, 0.025383), p(78.1155, 0.0)]],
        emphasis: p(78.1155, 0.0),
        beforeReference: 0.086583,
        gaps: []
    )

    private static let mitchellHistory = FieldChooserHistory10868(
        segments: [[p(72.0438, 0.074947), p(72.1188, 0.073789), p(75.4661, 0.469608)]],
        emphasis: p(75.4661, 0.469608),
        beforeReference: 0.012733,
        gaps: []
    )

    private static func record(_ id: String) -> FieldChooserOriginal10868 {
        let original = ref(id)
        switch id {
        case brennan:
            return FieldChooserOriginal10868(
                ref: original, name: name(id),
                plan: .comparison(
                    before: reading(beforeLabel, "2.6%", beforeDetail),
                    later: reading(laterLabel, "13.8%", "Oct 10, 8:27 PM PT · DataGolf")
                ),
                preview: FieldChooserPreview10868(history: brennanHistory, absence: noHistory),
                movement: "Up 11.2 pts vs before tournament",
                clock: "Oct 10, 8:27 PM PT",
                result: FieldChooserResult10868(title: "Final result", words: "Won"),
                browseStatus: historyAvailable
            )
        case schauffele:
            return FieldChooserOriginal10868(
                ref: original, name: name(id),
                plan: .comparison(
                    before: reading(beforeLabel, "8.7%", beforeDetail),
                    later: reading(laterLabel, "0%", "Oct 10, 11:06 PM PT · DataGolf")
                ),
                preview: FieldChooserPreview10868(history: schauffeleHistory, absence: noHistory),
                movement: "Down 8.7 pts vs before tournament",
                clock: "Oct 10, 11:06 PM PT",
                result: FieldChooserResult10868(title: "Final result", words: "T4"),
                browseStatus: historyAvailable
            )
        case mitchell:
            return FieldChooserOriginal10868(
                ref: original, name: name(id),
                plan: .comparison(
                    before: reading(beforeLabel, "1.3%", beforeDetail),
                    later: reading(laterLabel, "47%", "Oct 10, 8:27 PM PT · DataGolf")
                ),
                preview: FieldChooserPreview10868(history: mitchellHistory, absence: noHistory),
                movement: "Up 45.7 pts vs before tournament",
                clock: "Oct 10, 8:27 PM PT",
                result: nil,
                browseStatus: historyAvailable
            )
        default:
            let hasHistory = field.first { $0.id == id }!.history
            return FieldChooserOriginal10868(
                ref: original, name: name(id),
                plan: .comparison(before: missing(beforeLabel, noBefore), later: missing(laterLabel, noLater)),
                preview: FieldChooserPreview10868(history: nil, absence: noHistory),
                movement: nil,
                clock: nil,
                result: nil,
                browseStatus: hasHistory ? historyAvailable : historyUnavailable
            )
        }
    }

    private static let catalogue: [FieldChooserOriginal10868] = field.map { record($0.id) }

    private static let frame = FieldChooserFrame10868(
        start: 0, end: 79, ceiling: 0.5,
        key: "Week history · same time & scale",
        referenceKey: "Dashed line: before tournament",
        scale: "0–50% chance",
        provenance: "DataGolf-derived recorded history"
    )

    private static func groups() -> [FieldChooserGroup10868] {
        bands.map { band in
            FieldChooserGroup10868(id: band.id, label: band.label, countText: "\(band.members.count)", refs: band.members.map { ref($0) })
        }
    }

    private static func browse(
        expanded: Bool = true,
        selected: String? = "constructed:band:0",
        groups: [FieldChooserGroup10868] = FieldContenderChooserPresentation10868Tests.groups(),
        id: String = "browse"
    ) -> FieldChooserBrowse10868 {
        FieldChooserBrowse10868(
            id: id,
            title: "Browse all 155 golfers",
            expanded: expanded,
            note: "By last name · a golfer stays selectable when history is missing.",
            groupsLabel: "Last-name groups",
            groups: groups,
            selectedGroupID: selected,
            noGroupWords: "Choose a group to see its golfers.",
            groupUnavailableWords: "This group is unavailable in this update.",
            emptyGroupWords: "No golfers in this group."
        )
    }

    private static func more(expanded: Bool = true, refs: [FieldChooserOriginalRef10868]? = nil, id: String = "more") -> FieldChooserMore10868 {
        FieldChooserMore10868(
            id: id,
            title: "More with recorded history · 3",
            expanded: expanded,
            refs: refs ?? [ref(mitchell), ref(brennan), ref("241857513")],
            emptyWords: "No more golfers with recorded history."
        )
    }

    private static let featuredRefs = [ref(thorbjornsen), ref(brennan), ref(schauffele)]

    private static func input(
        catalogue: [FieldChooserOriginal10868] = FieldContenderChooserPresentation10868Tests.catalogue,
        featured: [FieldChooserOriginalRef10868] = FieldContenderChooserPresentation10868Tests.featuredRefs,
        more: FieldChooserMore10868? = FieldContenderChooserPresentation10868Tests.more(),
        browse: FieldChooserBrowse10868? = FieldContenderChooserPresentation10868Tests.browse(),
        frame: FieldChooserFrame10868? = FieldContenderChooserPresentation10868Tests.frame,
        selected: FieldChooserOriginalRef10868? = FieldContenderChooserPresentation10868Tests.ref(FieldContenderChooserPresentation10868Tests.thorbjornsen),
        selectedWords: String = FieldContenderChooserPresentation10868Tests.kept
    ) -> FieldChooserInput10868 {
        FieldChooserInput10868(
            scope: scope,
            intro: "Pick one to keep. We suggest the other two.",
            featured: FieldChooserFeatured10868(title: "In your chart", badge: "3 maximum", refs: featured, emptyWords: "No golfers in your chart."),
            context: "Week · 13 of 155 golfers have history in this view. Values are separately timed estimates.",
            more: more,
            browse: browse,
            catalogue: catalogue,
            frame: frame,
            selected: selected.map {
                FieldChooserSelected10868(ref: $0, words: selectedWords, unavailableWords: "Your golfer is unavailable in this update.")
            },
            unavailableWords: unavailable,
            chooseHint: "Keeps this golfer in the chart"
        )
    }

    private static func model(_ input: FieldChooserInput10868 = FieldContenderChooserPresentation10868Tests.input()) -> FieldChooserModel10868 {
        FieldChooserModel10868(input)
    }

    private static func groupInput(_ id: String) -> FieldChooserInput10868 { input(browse: browse(selected: id)) }

    // MARK: The packet itself

    func testThePacketHas155DistinctOriginals13WithHistory() {
        XCTAssertEqual(Self.field.count, 155)
        XCTAssertEqual(Set(Self.field.map(\.id)).count, 155)
        XCTAssertEqual(Self.field.filter(\.history).count, 13)
        XCTAssertEqual(Self.field.filter { !$0.history }.count, 142)
    }

    // MARK: Complete field

    func testEveryOriginalIsReachableExactlyOnceThroughTheOwnerGroupsAndChoosable() {
        var reached: [String] = []
        for band in Self.bands {
            let model = Self.model(Self.groupInput(band.id))
            for row in model.groupRows {
                let original = try? XCTUnwrap(row.resolution.original)
                XCTAssertEqual(original?.ref, row.ref)
                XCTAssertEqual(model.chooseAction(row, canChoose: true), .choose(row.ref))
                reached.append(row.ref.outcomeID)
            }
        }
        XCTAssertEqual(reached.count, 155)
        XCTAssertEqual(Set(reached), Set(Self.field.map(\.id)))
    }

    func testAGroupListsEveryMemberInTheOwnersOrderWithNoCap() {
        let band = Self.bands[2]
        XCTAssertEqual(band.members.count, 43)
        let rows = Self.model(Self.groupInput(band.id)).groupRows
        XCTAssertEqual(rows.map(\.ref.outcomeID), band.members)
    }

    func testOwnerBandLabelsKeepTheCompoundNamesInTheirOwnersGroupsAndWhole() {
        let tz = Self.model(Self.groupInput("constructed:band:5"))
        XCTAssertTrue(tz.groupRows.contains { $0.ref.outcomeID == Self.vanRooyen })
        XCTAssertEqual(tz.resolve(Self.ref(Self.vanRooyen)).original?.name, "Erik Van Rooyen")
        let dg = Self.model(Self.groupInput("constructed:band:1"))
        XCTAssertTrue(dg.groupRows.contains { $0.ref.outcomeID == Self.dumontDeChassart })
        XCTAssertEqual(dg.resolve(Self.ref(Self.dumontDeChassart)).original?.name, "Adrien Dumont De Chassart")
        guard case .group(let group)? = dg.groupSelection else { return XCTFail("D–G should resolve") }
        XCTAssertEqual(group.label, "D–G")
        XCTAssertEqual(group.countText, "21")
    }

    func testRepeatedReferencesAcrossSectionsResolveOneCanonicalRecord() {
        let model = Self.model(Self.groupInput("constructed:band:0"))
        let featured = model.featuredRows.first { $0.ref.outcomeID == Self.brennan }?.resolution.original
        let more = model.moreRows.first { $0.ref.outcomeID == Self.brennan }?.resolution.original
        let browse = model.groupRows.first { $0.ref.outcomeID == Self.brennan }?.resolution.original
        XCTAssertNotNil(featured)
        XCTAssertEqual(featured, more)
        XCTAssertEqual(featured, browse)
        XCTAssertEqual(Self.input().catalogue.filter { $0.ref.outcomeID == Self.brennan }.count, 1)
    }

    func testTheCatalogueIsNeitherSortedNorDeduplicatedNorCapped() {
        let model = Self.model()
        XCTAssertEqual(model.input.catalogue.map(\.ref.outcomeID), Self.field.map(\.id))
        XCTAssertEqual(model.featuredRows.map(\.ref.outcomeID), [Self.thorbjornsen, Self.brennan, Self.schauffele])
    }

    // MARK: No-history original

    func testANoHistoryOriginalStaysChoosableWithNoInventedChanceOrPreview() {
        let model = Self.model()
        let row = model.featuredRows[0]
        let original = try? XCTUnwrap(row.resolution.original)
        XCTAssertEqual(original?.name, "Michael Thorbjornsen")
        XCTAssertEqual(model.chooseAction(row, canChoose: true), .choose(Self.ref(Self.thorbjornsen)))
        XCTAssertEqual(original?.plan.readings.map(\.value), [.missing(Self.noBefore), .missing(Self.noLater)])
        XCTAssertNil(original.flatMap { model.plot($0) })
        let summary = original.map { model.cardSummary($0) } ?? ""
        XCTAssertTrue(summary.contains(Self.noHistory))
        XCTAssertFalse(summary.contains("2.5"))
    }

    func testANoHistoryBrowseRowSaysSoAndStillChooses() {
        let model = Self.model(Self.input(selected: nil))
        let rows = Self.model(Self.groupInput("constructed:band:5")).groupRows
        let row = try? XCTUnwrap(rows.first { $0.ref.outcomeID == Self.thorbjornsen })
        XCTAssertEqual(row.flatMap { $0.resolution.original }.map { model.browseSummary($0) }, Self.historyUnavailable)
        XCTAssertEqual(row.flatMap { model.chooseAction($0, canChoose: true) }, .choose(Self.ref(Self.thorbjornsen)))
    }

    // MARK: Selection

    func testTheSelectedOriginalCarriesTheOwnersWordsAndOnlyIt() {
        let model = Self.model()
        let selected = Self.record(Self.thorbjornsen)
        XCTAssertTrue(model.isSelected(selected))
        XCTAssertEqual(model.selectedWords(selected), Self.kept)
        XCTAssertEqual(model.browseSummary(selected), Self.kept)
        XCTAssertTrue(model.cardSummary(selected).hasPrefix(Self.kept))
        for id in [Self.brennan, Self.schauffele, Self.mitchell] {
            XCTAssertFalse(model.isSelected(Self.record(id)))
            XCTAssertNil(model.selectedWords(Self.record(id)))
        }
        XCTAssertNil(model.selectionNotice)
    }

    func testTheOwnersUnpinnedWordsAreShownVerbatim() {
        let model = Self.model(Self.input(selected: Self.ref(Self.brennan), selectedWords: "In focus"))
        XCTAssertEqual(model.selectedWords(Self.record(Self.brennan)), "In focus")
        XCTAssertNil(model.selectedWords(Self.record(Self.thorbjornsen)))
    }

    func testAnUnresolvedSelectionShowsTheOwnersNoticeAndSelectsNoNeighbour() {
        for bad in [Self.ref("999999999"), Self.ref(Self.brennan, scope: "other"), Self.ref("")] {
            let model = Self.model(Self.input(selected: bad))
            XCTAssertNil(model.selectedRef)
            XCTAssertEqual(model.selectionNotice, "Your golfer is unavailable in this update.")
            XCTAssertFalse(Self.catalogue.contains { model.isSelected($0) })
        }
    }

    func testChoosingHandsBackTheExactCatalogueIdentityAndNeverRepins() {
        let model = Self.model()
        var chosen: [FieldChooserOriginalRef10868] = []
        let action = model.chooseAction(model.featuredRows[1], canChoose: true)
        action?.perform(onChoose: { chosen.append($0) }, onControl: { _ in XCTFail("no control") })
        XCTAssertEqual(chosen, [Self.ref(Self.brennan)])
        XCTAssertEqual(model.selectedRef, Self.ref(Self.thorbjornsen))
    }

    // MARK: Identity failures

    func testOutOfScopeWithdrawnDuplicateAndBlankReferencesAreUnavailableAndNeighboursKeepTheirs() {
        var catalogue = Self.catalogue
        catalogue.append(Self.record(Self.schauffele))
        catalogue.removeAll { $0.ref.outcomeID == Self.mitchell }
        let blank = FieldChooserOriginal10868(
            ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "datagolf", marketID: " ", outcomeID: "1"),
            name: "Blank market", plan: .single(Self.missing(Self.beforeLabel, Self.noBefore)),
            preview: FieldChooserPreview10868(history: nil, absence: Self.noHistory),
            movement: nil, clock: nil, result: nil, browseStatus: Self.historyUnavailable
        )
        catalogue.append(blank)
        let featured = [
            Self.ref(Self.brennan, scope: "another-week"),
            Self.ref(Self.mitchell),
            Self.ref(Self.schauffele),
            blank.ref,
            Self.ref(Self.brennan),
        ]
        let model = Self.model(Self.input(catalogue: catalogue, featured: featured, selected: nil))
        let rows = model.featuredRows
        XCTAssertEqual(rows.count, 5)
        XCTAssertEqual(rows[0].resolution, .unavailable)
        XCTAssertEqual(rows[1].resolution, .unavailable)
        XCTAssertEqual(rows[2].resolution, .unavailable)
        XCTAssertEqual(rows[3].resolution, .unavailable)
        XCTAssertEqual(rows[4].resolution.original?.ref, Self.ref(Self.brennan))
        XCTAssertEqual(rows.map { model.chooseAction($0, canChoose: true) }, [nil, nil, nil, nil, .choose(Self.ref(Self.brennan))])
    }

    func testADuplicatedSelectedIdentityIsNeverSelected() {
        let catalogue = Self.catalogue + [Self.record(Self.thorbjornsen)]
        let model = Self.model(Self.input(catalogue: catalogue))
        XCTAssertNil(model.selectedRef)
        XCTAssertNotNil(model.selectionNotice)
    }

    // MARK: Expansion and groups

    func testMoreRowsAppearOnlyWhileTheHostHasThemExpanded() {
        XCTAssertTrue(Self.model(Self.input(more: Self.more(expanded: false))).moreRows.isEmpty)
        XCTAssertEqual(Self.model().moreRows.map(\.ref.outcomeID), [Self.mitchell, Self.brennan, "241857513"])
    }

    func testControlsHandBackTheOwnersExactIDs() {
        let model = Self.model()
        XCTAssertEqual(model.moreAction(canControl: true), .control(.toggleMore(id: "more")))
        XCTAssertEqual(model.browseAction(canControl: true), .control(.toggleBrowse(id: "browse")))
        let groups = Self.groups()
        XCTAssertEqual(model.groupAction(groups[3], canControl: true), .control(.chooseGroup(id: "constructed:band:3")))
        var controls: [FieldChooserControl10868] = []
        model.groupAction(groups[3], canControl: true)?.perform(onChoose: { _ in XCTFail("no choose") }, onControl: { controls.append($0) })
        XCTAssertEqual(controls, [.chooseGroup(id: "constructed:band:3")])
    }

    func testNoCallbackMeansStaticContentEverywhere() {
        let model = Self.model()
        XCTAssertNil(model.moreAction(canControl: false))
        XCTAssertNil(model.browseAction(canControl: false))
        XCTAssertTrue(Self.groups().allSatisfy { model.groupAction($0, canControl: false) == nil })
        XCTAssertTrue((model.featuredRows + model.moreRows + model.groupRows).allSatisfy { model.chooseAction($0, canChoose: false) == nil })
        XCTAssertEqual(model.groupRows.count, 18)
    }

    func testDuplicateAndBlankGroupIDsStayStaticAndValidGroupsKeepTheirActions() {
        var groups = Self.groups()
        groups[1] = FieldChooserGroup10868(id: groups[0].id, label: groups[1].label, countText: nil, refs: groups[1].refs)
        groups[2] = FieldChooserGroup10868(id: "  ", label: groups[2].label, countText: nil, refs: groups[2].refs)
        let model = Self.model(Self.input(browse: Self.browse(selected: groups[0].id, groups: groups)))
        XCTAssertNil(model.groupAction(groups[0], canControl: true))
        XCTAssertNil(model.groupAction(groups[1], canControl: true))
        XCTAssertNil(model.groupAction(groups[2], canControl: true))
        XCTAssertEqual(model.groupAction(groups[3], canControl: true), .control(.chooseGroup(id: groups[3].id)))
        XCTAssertEqual(model.groupSelection, .unavailable("This group is unavailable in this update."))
        XCTAssertTrue(model.groupRows.isEmpty)
    }

    func testAControlIDSharedByMoreAndBrowseLeavesBothStatic() {
        let model = Self.model(Self.input(more: Self.more(id: "same"), browse: Self.browse(id: "same")))
        XCTAssertNil(model.moreAction(canControl: true))
        XCTAssertNil(model.browseAction(canControl: true))
        XCTAssertEqual(model.groupAction(Self.groups()[0], canControl: true), .control(.chooseGroup(id: "constructed:band:0")))
    }

    func testNoChosenGroupShowsTheOwnersWordsAndChoosesNoBand() {
        let model = Self.model(Self.input(browse: Self.browse(selected: nil)))
        XCTAssertEqual(model.groupSelection, .notChosen("Choose a group to see its golfers."))
        XCTAssertTrue(model.groupRows.isEmpty)
        XCTAssertFalse(Self.groups().contains { model.isSelectedGroup($0) })
    }

    func testAnUnknownChosenGroupShowsTheOwnersUnavailableWords() {
        let model = Self.model(Self.input(browse: Self.browse(selected: "constructed:band:9")))
        XCTAssertEqual(model.groupSelection, .unavailable("This group is unavailable in this update."))
    }

    func testAnEmptyResolvedGroupHasNoRows() {
        let empty = FieldChooserGroup10868(id: "empty", label: "X", countText: "0", refs: [])
        let model = Self.model(Self.input(browse: Self.browse(selected: "empty", groups: Self.groups() + [empty])))
        XCTAssertEqual(model.groupSelection, .group(empty))
        XCTAssertTrue(model.groupRows.isEmpty)
    }

    func testACollapsedBrowseHasNoGroupState() {
        let model = Self.model(Self.input(browse: Self.browse(expanded: false)))
        XCTAssertNil(model.groupSelection)
        XCTAssertTrue(model.groupRows.isEmpty)
        XCTAssertEqual(model.browseAction(canControl: true), .control(.toggleBrowse(id: "browse")))
    }

    // MARK: Display plans

    func testAOneSlotPlanPrintsOneDatedBeforeReading() {
        let plan = FieldChooserDisplayPlan10868.single(Self.reading("Last recorded", "2.6%", Self.beforeDetail))
        XCTAssertEqual(plan.readings.count, 1)
        XCTAssertEqual(FieldChooserModel10868.spoken(plan.readings[0]), "Last recorded: 2.6%, Oct 6, 6:08 AM PT · DataGolf")
    }

    func testAComparisonKeepsEachReadingsOwnClockAndSource() {
        let brennan = Self.record(Self.brennan)
        XCTAssertEqual(brennan.plan.readings.map(FieldChooserModel10868.spoken), [
            "Before tournament: 2.6%, Oct 6, 6:08 AM PT · DataGolf",
            "Last in Round 4: 13.8%, Oct 10, 8:27 PM PT · DataGolf",
        ])
    }

    func testEqualFiguresWithDifferentProvenanceAreBothShown() {
        let plan = FieldChooserDisplayPlan10868.comparison(
            before: Self.reading(Self.beforeLabel, "2.6%", Self.beforeDetail),
            later: Self.reading("Last recorded", "2.6%", "Oct 11, 3:08 PM PT · DataGolf")
        )
        XCTAssertEqual(plan.readings.count, 2)
        XCTAssertNotEqual(plan.readings[0], plan.readings[1])
    }

    func testARealZeroIsAValueAndAbsentIsWords() {
        let schauffele = Self.record(Self.schauffele)
        XCTAssertEqual(schauffele.plan.readings[1].value, .recorded(text: "0%", detail: "Oct 10, 11:06 PM PT · DataGolf"))
        let plot = Self.model().plot(schauffele)
        XCTAssertEqual(plot?.emphasis?.y, 1)
        let absentBefore = FieldChooserDisplayPlan10868.comparison(
            before: Self.missing(Self.beforeLabel, Self.noBefore),
            later: Self.reading(Self.laterLabel, "0%", "Oct 10, 11:06 PM PT · DataGolf")
        )
        XCTAssertEqual(absentBefore.readings.map(\.value), [
            .missing(Self.noBefore), .recorded(text: "0%", detail: "Oct 10, 11:06 PM PT · DataGolf"),
        ])
    }

    func testAFinalResultStaysSeparateFromTheHistoricalReadings() {
        let model = Self.model(Self.input(selected: nil))
        let brennan = Self.record(Self.brennan)
        XCTAssertEqual(brennan.plan.readings.map(\.value), [
            .recorded(text: "2.6%", detail: Self.beforeDetail),
            .recorded(text: "13.8%", detail: "Oct 10, 8:27 PM PT · DataGolf"),
        ])
        XCTAssertEqual(model.cardSummary(brennan), [
            "Before tournament: 2.6%, Oct 6, 6:08 AM PT · DataGolf",
            "Last in Round 4: 13.8%, Oct 10, 8:27 PM PT · DataGolf",
            "Up 11.2 pts vs before tournament",
            "Oct 10, 8:27 PM PT",
            "Final result: Won",
        ].joined(separator: ". "))
        XCTAssertFalse(model.cardSummary(brennan).contains("100%"))
    }

    // MARK: Shared frame

    func testEveryPreviewSharesOneFrameAndZeroBasedCeiling() {
        let model = Self.model()
        let brennan = try? XCTUnwrap(model.plot(Self.record(Self.brennan)))
        let mitchell = try? XCTUnwrap(model.plot(Self.record(Self.mitchell)))
        let schauffele = try? XCTUnwrap(model.plot(Self.record(Self.schauffele)))
        // Same clock in two rows → same x; each y reads the one 0.5 ceiling.
        XCTAssertEqual(brennan?.emphasis?.x, mitchell?.emphasis?.x)
        XCTAssertEqual(brennan?.emphasis?.y ?? 0, 1 - 0.137681 / 0.5, accuracy: 1e-12)
        XCTAssertEqual(mitchell?.emphasis?.y ?? 0, 1 - 0.469608 / 0.5, accuracy: 1e-12)
        XCTAssertEqual(schauffele?.reference ?? 0, 1 - 0.086583 / 0.5, accuracy: 1e-12)
        XCTAssertEqual(brennan?.reference ?? 0, 1 - 0.026017 / 0.5, accuracy: 1e-12)
    }

    func testAPreviewDoesNotRescaleWhenTheVisibleCohortChanges() {
        let wide = Self.model()
        let narrow = Self.model(Self.input(featured: [Self.ref(Self.brennan)], more: nil))
        XCTAssertEqual(wide.plot(Self.record(Self.brennan)), narrow.plot(Self.record(Self.brennan)))
    }

    func testAPointAboveTheCeilingBreaksTheLineInsteadOfClipping() {
        let plot = Self.model().plot(Self.record(Self.brennan))
        XCTAssertEqual(plot?.runs.map(\.count), [3, 3, 2, 3])
        XCTAssertTrue(plot?.runs.joined().allSatisfy { $0.y >= 0 && $0.y <= 1 } ?? false)
        XCTAssertEqual(plot?.gaps.count, 3)
    }

    func testInvalidFutureAndNonFinitePointsBreakThePathAndIsolatedPointsStay() {
        let history = FieldChooserHistory10868(
            segments: [[
                Self.p(1, 0.1), Self.p(2, 0.11), Self.p(.nan, 0.1),
                Self.p(3, 0.12), Self.p(90, 0.1), Self.p(4, -0.01),
                Self.p(5, 0.2), Self.p(6, 0.21),
            ]],
            emphasis: nil, beforeReference: nil, gaps: []
        )
        let plot = FieldChooserGeometry10868.plot(history, in: Self.frame)
        XCTAssertEqual(plot?.runs.map(\.count), [2, 1, 2])
        XCTAssertEqual(plot?.runs[1].first?.x ?? 0, 3.0 / 79.0, accuracy: 1e-12)
    }

    func testSeparateOwnerSegmentsNeverJoin() {
        let history = FieldChooserHistory10868(segments: [[Self.p(1, 0.1)], [Self.p(2, 0.1)]], emphasis: nil, beforeReference: nil, gaps: [])
        XCTAssertEqual(FieldChooserGeometry10868.plot(history, in: Self.frame)?.runs.map(\.count), [1, 1])
    }

    func testTheEmphasisIsTheOwnersExactObservationNotTheLatest() {
        let brennan = Self.model().plot(Self.record(Self.brennan))
        XCTAssertEqual(brennan?.emphasis?.x ?? 0, 75.4661 / 79.0, accuracy: 1e-12)
        // CONSTRUCTED: the owner emphasizes the round's first record, not its last.
        let history = FieldChooserHistory10868(
            segments: [[Self.p(72.0438, 0.161117), Self.p(75.4661, 0.137681)]],
            emphasis: Self.p(72.0438, 0.161117), beforeReference: nil, gaps: []
        )
        let plot = FieldChooserGeometry10868.plot(history, in: Self.frame)
        XCTAssertEqual(plot?.emphasis, plot?.runs.first?.first)
        XCTAssertNotEqual(plot?.emphasis, plot?.runs.last?.last)
    }

    func testGapsOutsideTheDomainOrBackwardsAreNotDrawn() {
        let gaps = [
            FieldChooserGap10868(start: 10, end: 20),
            FieldChooserGap10868(start: 20, end: 10),
            FieldChooserGap10868(start: -5, end: 3),
            FieldChooserGap10868(start: 70, end: 80),
        ]
        let history = FieldChooserHistory10868(segments: [[Self.p(1, 0.1)]], emphasis: nil, beforeReference: nil, gaps: gaps)
        let plot = FieldChooserGeometry10868.plot(history, in: Self.frame)
        XCTAssertEqual(plot?.gaps.count, 1)
        XCTAssertEqual(plot?.gaps.first ?? 0, 15.0 / 79.0, accuracy: 1e-12)
    }

    func testAReferenceWithNoObservationShowsTheAbsenceWords() {
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref.outcomeID == Self.mitchell }!
        let old = catalogue[index]
        catalogue[index] = FieldChooserOriginal10868(
            ref: old.ref, name: old.name, plan: old.plan,
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(segments: [[Self.p(100, 0.1)]], emphasis: nil, beforeReference: 0.012733, gaps: []),
                absence: Self.noHistory
            ),
            movement: nil, clock: nil, result: nil, browseStatus: Self.historyAvailable
        )
        let model = Self.model(Self.input(catalogue: catalogue))
        XCTAssertNil(model.plot(catalogue[index]))
        XCTAssertTrue(model.cardSummary(catalogue[index]).hasSuffix(Self.noHistory))
    }

    func testAnInvalidFrameDrawsNoPreviewAndNoKey() {
        for frame in [
            FieldChooserFrame10868(start: 5, end: 5, ceiling: 0.5, key: "k", referenceKey: nil, scale: "s", provenance: "p"),
            FieldChooserFrame10868(start: 0, end: 79, ceiling: 0, key: "k", referenceKey: nil, scale: "s", provenance: "p"),
            FieldChooserFrame10868(start: 0, end: 79, ceiling: 1.5, key: "k", referenceKey: nil, scale: "s", provenance: "p"),
            FieldChooserFrame10868(start: 0, end: .infinity, ceiling: 0.5, key: "k", referenceKey: nil, scale: "s", provenance: "p"),
        ] {
            let model = Self.model(Self.input(frame: frame))
            XCTAssertNil(model.visibleFrame)
            XCTAssertNil(model.plot(Self.record(Self.brennan)))
        }
        XCTAssertNil(Self.model(Self.input(frame: nil)).plot(Self.record(Self.brennan)))
    }

    func testAnEdgeMarkStaysWholeInsideTheInset() {
        let size = CGSize(width: 120, height: 50)
        let corner = FieldChooserGeometry10868.position(FieldChooserUnitPoint10868(x: 1, y: 0), in: size, inset: 4)
        XCTAssertEqual(corner, CGPoint(x: 116, y: 4))
        let origin = FieldChooserGeometry10868.position(FieldChooserUnitPoint10868(x: 0, y: 1), in: size, inset: 4)
        XCTAssertEqual(origin, CGPoint(x: 4, y: 46))
    }

    // MARK: Card arrangement (CONSTRUCTED measured widths)

    private func arrangement(screen: CGFloat, readings: CGFloat, preview: CGFloat, ax: Bool = false) -> FieldChooserArrangement10868 {
        // 16 pt host margins each side and 12 pt card padding each side.
        FieldChooserGeometry10868.cardArrangement(
            available: screen - 32 - 24, readingsWidth: readings, previewMinimum: preview, spacing: 12, forceStack: ax
        )
    }

    func testDefaultTextKeepsReadingsBesideThePreviewAt320To393AndWide() {
        for screen: CGFloat in [320, 375, 393, 768] {
            XCTAssertEqual(arrangement(screen: screen, readings: 150, preview: 96), .sideBySide, "\(screen)")
        }
    }

    func testLargerTextStacksBeforeAnythingShrinks() {
        XCTAssertEqual(arrangement(screen: 320, readings: 190, preview: 120), .stacked)
        XCTAssertEqual(arrangement(screen: 375, readings: 190, preview: 120), .stacked)
        XCTAssertEqual(arrangement(screen: 393, readings: 190, preview: 120), .sideBySide)
    }

    func testAccessibilitySizesAlwaysStack() {
        for screen: CGFloat in [320, 375, 393, 1024] {
            XCTAssertEqual(arrangement(screen: screen, readings: 120, preview: 96, ax: true), .stacked)
        }
    }

    func testUnmeasurableWidthsStackAndAnUnboundedProposalSitsSideBySide() {
        XCTAssertEqual(FieldChooserGeometry10868.cardArrangement(available: 300, readingsWidth: .infinity, previewMinimum: 96, spacing: 12, forceStack: false), .stacked)
        XCTAssertEqual(FieldChooserGeometry10868.cardArrangement(available: nil, readingsWidth: 150, previewMinimum: 96, spacing: 12, forceStack: false), .sideBySide)
    }

    // MARK: Spoken text

    func testLongNamesAreSpokenWhole() {
        let model = Self.model(Self.groupInput("constructed:band:2"))
        let longest = Self.field.max { $0.name.count < $1.name.count }!
        XCTAssertEqual(longest.name.count, 25)
        let original = model.resolve(Self.ref(longest.id)).original
        XCTAssertEqual(original?.name, longest.name)
    }

    func testAMissingRowIsSpokenWithTheOwnersWordsNotANeighbour() {
        let model = Self.model(Self.input(featured: [Self.ref("123")], selected: nil))
        XCTAssertEqual(model.featuredRows.first?.resolution, .unavailable)
        XCTAssertEqual(model.input.unavailableWords, Self.unavailable)
    }

    // MARK: Reference key (CONSTRUCTED keys on the shared frame)

    private static func keyedFrame(_ referenceKey: String?) -> FieldChooserFrame10868 {
        FieldChooserFrame10868(
            start: frame.start, end: frame.end, ceiling: frame.ceiling,
            key: frame.key, referenceKey: referenceKey, scale: frame.scale, provenance: frame.provenance
        )
    }

    /// Nil, empty, spaces, a tab, a newline and mixed whitespace.
    private static let unexplainedKeys: [String?] = [nil, "", "   ", "\t", "\n", " \t\n \r\n "]

    func testAnUnexplainedReferenceKeyDrawsNoDashedReferenceAndKeepsTheWholeHistory() {
        guard let keyed = Self.model().plot(Self.record(Self.brennan)) else { return XCTFail("keyed Brennan plot") }
        XCTAssertEqual(keyed.reference ?? 0, 1 - 0.026017 / 0.5, accuracy: 1e-12)
        let unreferenced = FieldChooserPlot10868(runs: keyed.runs, emphasis: keyed.emphasis, reference: nil, gaps: keyed.gaps)
        for key in Self.unexplainedKeys {
            let label = String(reflecting: key)
            let model = Self.model(Self.input(frame: Self.keyedFrame(key)))
            let plot = model.plot(Self.record(Self.brennan))
            XCTAssertNotNil(plot, label)
            XCTAssertNil(plot?.reference, label)
            XCTAssertEqual(plot, unreferenced, label)
            XCTAssertEqual(plot?.runs.map(\.count), [3, 3, 2, 3], label)
            XCTAssertEqual(plot?.emphasis?.x ?? 0, 75.4661 / 79.0, accuracy: 1e-12, label)
            XCTAssertEqual(plot?.gaps.count, 3, label)
            XCTAssertNil(model.plot(Self.record(Self.schauffele))?.reference, label)
            XCTAssertNotNil(model.plot(Self.record(Self.schauffele))?.emphasis, label)
        }
    }

    func testTheKeyShowsNoReferenceRowForAnUnexplainedKeyAndKeepsTheFrameWords() {
        for key in Self.unexplainedKeys {
            let label = String(reflecting: key)
            let visible = Self.model(Self.input(frame: Self.keyedFrame(key))).visibleFrame
            XCTAssertEqual(visible?.key, Self.frame.key, label)
            XCTAssertEqual(visible?.provenance, Self.frame.provenance, label)
            XCTAssertNil(visible?.explainedReferenceKey, label)
        }
    }

    func testANonblankReferenceKeyKeepsItsExactWordsAndTheReference() {
        for key in ["Dashed line: before tournament", "Dashed line:\nbefore tournament", "  Before tournament\t\n"] {
            let model = Self.model(Self.input(frame: Self.keyedFrame(key)))
            XCTAssertEqual(model.visibleFrame?.explainedReferenceKey, key)
            XCTAssertEqual(model.plot(Self.record(Self.brennan))?.reference ?? 0, 1 - 0.026017 / 0.5, accuracy: 1e-12)
            XCTAssertEqual(model.plot(Self.record(Self.schauffele))?.reference ?? 0, 1 - 0.086583 / 0.5, accuracy: 1e-12)
            XCTAssertEqual(model.plot(Self.record(Self.brennan))?.runs, Self.model().plot(Self.record(Self.brennan))?.runs)
        }
    }

    func testAHistoryWithNoReferenceDrawsNoneWhateverTheKey() {
        let history = FieldChooserHistory10868(
            segments: Self.brennanHistory.segments, emphasis: Self.brennanHistory.emphasis,
            beforeReference: nil, gaps: Self.brennanHistory.gaps
        )
        for key in Self.unexplainedKeys + ["Dashed line: before tournament"] {
            let label = String(reflecting: key)
            let plot = FieldChooserGeometry10868.plot(history, in: Self.keyedFrame(key))
            XCTAssertNil(plot?.reference, label)
            XCTAssertEqual(plot?.runs.map(\.count), [3, 3, 2, 3], label)
            XCTAssertNotNil(plot?.emphasis, label)
            XCTAssertEqual(plot?.gaps.count, 3, label)
        }
    }

    func testReferenceYStaysACoordinateHelperWhileThePlotConsumesTheKey() {
        let unkeyed = Self.keyedFrame(nil)
        XCTAssertEqual(FieldChooserGeometry10868.referenceY(0.026017, in: unkeyed) ?? 0, 1 - 0.026017 / 0.5, accuracy: 1e-12)
        XCTAssertNil(FieldChooserGeometry10868.plot(Self.brennanHistory, in: unkeyed)?.reference)
    }

    func testAnUnexplainedKeyLeavesReferenceOnlyAbsenceAndEveryOriginalChoosable() {
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref.outcomeID == Self.mitchell }!
        let old = catalogue[index]
        catalogue[index] = FieldChooserOriginal10868(
            ref: old.ref, name: old.name, plan: old.plan,
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(segments: [[Self.p(100, 0.1)]], emphasis: nil, beforeReference: 0.012733, gaps: []),
                absence: Self.noHistory
            ),
            movement: nil, clock: nil, result: nil, browseStatus: Self.historyAvailable
        )
        for key in Self.unexplainedKeys {
            let label = String(reflecting: key)
            let frame = Self.keyedFrame(key)
            let referenceOnly = Self.model(Self.input(catalogue: catalogue, frame: frame))
            XCTAssertNil(referenceOnly.plot(catalogue[index]), label)
            XCTAssertTrue(referenceOnly.cardSummary(catalogue[index]).hasSuffix(Self.noHistory), label)

            let model = Self.model(Self.input(frame: frame))
            let first = model.featuredRows[0]
            XCTAssertEqual(first.ref, Self.ref(Self.thorbjornsen), label)
            XCTAssertNil(first.resolution.original.flatMap { model.plot($0) }, label)
            XCTAssertEqual(model.chooseAction(first, canChoose: true), .choose(Self.ref(Self.thorbjornsen)), label)
            XCTAssertEqual(model.selectedRef, Self.ref(Self.thorbjornsen), label)

            var reached: [String] = []
            for band in Self.bands {
                let grouped = Self.model(Self.input(browse: Self.browse(selected: band.id), frame: frame))
                for row in grouped.groupRows {
                    XCTAssertEqual(grouped.chooseAction(row, canChoose: true), .choose(row.ref), label)
                    reached.append(row.ref.outcomeID)
                }
            }
            XCTAssertEqual(reached.count, 155, label)
            XCTAssertEqual(Set(reached), Set(Self.field.map(\.id)), label)
        }
    }
}

/// #10868 — the weather-range "Before the day began" card as outlook bars on
/// the field chooser's own model.
///
/// As above, nothing is rasterised. What is asserted is the rules the view
/// defers to: the chooser's scoped resolver for every bar, the selected
/// original and its neighbours, the raw before chance tied to its own
/// formatted reading, the shared scale, the phase gate on the result and the
/// spoken summaries. No rendered fit, native runtime, VoiceOver behaviour or
/// held-update qualification is claimed.
///
/// ARCHIVED raw values come from Polymarket event 1186943 (KLGA daily high,
/// October 16, 2026), as retained in
/// `shipping-adoption-20261027/WEATHER-RANGE-OUTLOOK-RETAINED-CASES.json`
/// (sha256 f0cb47c1…64e2a8): 11 range markets and their 22 independent Yes/No
/// outcome tokens, each token's last pre-day sample (`baseline.p`, `.t`), its
/// raw CLOB winner flag, and a later-quote control sampled after the day.
/// The eleven Yes baselines sum to 1.0205. The approved five displayed Yes
/// originals are markets 5680546…5680550 (0.0555 / 0.23 / 0.425 / 0.25 /
/// 0.0495), on a 0…0.5 scale, with 5680548 Yes (74-75°F) selected.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope
/// string, every name ("74-75°F · Yes"), short axis label, reading label,
/// figure text (prepared with the reference `probabilityLabel.ts`, so 0.0495
/// prints "5%"), PT clock line and source word, the result words read from
/// the raw winner flags, the card copy and phase, the scale words and tick
/// labels, the traversal order, the hostile later/movement/station inputs,
/// and every withdrawn, duplicate, blank, foreign and long-label case. The
/// NWS 75.2°F station maximum appears only as a hostile string; it never
/// grades an original.
final class FieldOutlookBars10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Row = (
        market: String, side: String, outcome: String, label: String,
        before: Double, figure: String, clock: String, winner: Bool,
        later: Double, laterFigure: String, laterClock: String
    )

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:weather:1186943:range-outlook"

    /// ARCHIVED ids, labels, baselines and winner flags in the packet's market
    /// order; figures and PT clocks CONSTRUCTED from them.
    private static let rows: [Row] = [
        ("5680542", "Yes", "8913365083547058840727648558007260174176426214539964433076390904943107112394", "63°F or below", 0.001, "0.1%", "Oct 15, 8:00:24 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:23 PM PT"),
        ("5680542", "No", "67143910402456435176578359128729756115174394812031754735508727643398464506662", "63°F or below", 0.999, "99.9%", "Oct 15, 8:00:26 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:24 PM PT"),
        ("5680543", "Yes", "21435336294206529333936969966675079269275336661376130928308328232499909515391", "64-65°F", 0.0005, "0.1%", "Oct 15, 8:00:39 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:30 PM PT"),
        ("5680543", "No", "48052455767302060707788102938270415116722038376468308401484694477735066651219", "64-65°F", 0.9995, ">99.9%", "Oct 15, 8:00:28 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:25 PM PT"),
        ("5680544", "Yes", "107185634455894843610821566880080305468286254817220973775097065618207888752080", "66-67°F", 0.0025, "0.3%", "Oct 15, 8:00:32 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:27 PM PT"),
        ("5680544", "No", "115375096568369311164990277104328957168943720891530048218212965811147823644840", "66-67°F", 0.9975, "99.8%", "Oct 15, 8:00:27 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:24 PM PT"),
        ("5680545", "Yes", "22967642455827047245443771889541595907465471141356386761611041695657210518526", "68-69°F", 0.0045, "0.5%", "Oct 15, 8:00:29 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:25 PM PT"),
        ("5680545", "No", "111537624900846583946658455929539667688050754968556058471851612149659391288540", "68-69°F", 0.9955, "99.6%", "Oct 15, 8:00:23 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:22 PM PT"),
        ("5680546", "Yes", "30208396863628859266853401360725945315246332277999808492807567061425111095221", "70-71°F", 0.0555, "5.6%", "Oct 15, 8:00:29 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:26 PM PT"),
        ("5680546", "No", "55998474664018695178236956222472451286538263762519786120813722164777651946447", "70-71°F", 0.9445, "94.5%", "Oct 15, 8:00:37 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:29 PM PT"),
        ("5680547", "Yes", "42036490969657814030627686441430315859255282297966320641421618604860015683758", "72-73°F", 0.23, "23%", "Oct 15, 8:00:31 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:26 PM PT"),
        ("5680547", "No", "78761077488813221723830555306140100365304550954782607751025590225868446872439", "72-73°F", 0.77, "77%", "Oct 15, 8:00:26 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:24 PM PT"),
        ("5680548", "Yes", "97348811011973241846205943545597316259341369137822213272638970018898274192104", "74-75°F", 0.425, "42.5%", "Oct 15, 8:00:24 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:23 PM PT"),
        ("5680548", "No", "28807578185858778284793037276021658713791873585944870616198704837627433997315", "74-75°F", 0.575, "57.5%", "Oct 15, 8:00:35 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:28 PM PT"),
        ("5680549", "Yes", "62146049061772800442104405416602150380256265203802495142118020885435023782389", "76-77°F", 0.25, "25%", "Oct 15, 8:00:33 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:27 PM PT"),
        ("5680549", "No", "108307178477820030136628870794100368956919345679782937733831167636973962051916", "76-77°F", 0.75, "75%", "Oct 15, 8:00:39 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:30 PM PT"),
        ("5680550", "Yes", "21314677505606064787348766190871059866661422817349009784997764731054747568592", "78-79°F", 0.0495, "5%", "Oct 15, 8:00:38 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:30 PM PT"),
        ("5680550", "No", "27892904031490668791126455162520384280106755558205528849525683031242904636615", "78-79°F", 0.9505, "95.1%", "Oct 15, 8:00:38 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:30 PM PT"),
        ("5680551", "Yes", "96821810520797185036939183674087082483401017115855467226269310242027501278307", "80-81°F", 0.0015, "0.2%", "Oct 15, 8:00:31 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:26 PM PT"),
        ("5680551", "No", "54280296140785189409090952621928778327442017227711905048188438819366865032300", "80-81°F", 0.9985, "99.9%", "Oct 15, 8:00:37 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:29 PM PT"),
        ("5680552", "Yes", "29814975981391780694220300609647509354017812743734941224964105916454287716710", "82°F or higher", 0.0005, "0.1%", "Oct 15, 8:00:40 PM PT", false, 0.0005, "0.1%", "Oct 16, 10:00:31 PM PT"),
        ("5680552", "No", "22622594704289114994972145212761010706883868125649760533252652075898736439602", "82°F or higher", 0.9995, ">99.9%", "Oct 15, 8:00:35 PM PT", true, 0.9995, ">99.9%", "Oct 16, 10:00:28 PM PT"),
    ]

    private static let markets = ["5680542", "5680543", "5680544", "5680545", "5680546", "5680547",
                                  "5680548", "5680549", "5680550", "5680551", "5680552"]
    private static let displayedMarkets = ["5680546", "5680547", "5680548", "5680549", "5680550"]
    /// CONSTRUCTED compact labels, written out — never derived from the full label.
    private static let shortLabels = ["70-71°", "72-73°", "74-75°", "76-77°", "78-79°"]

    private static let beforeLabel = "Before the day"
    private static let source = "Polymarket"
    private static let selectedWords = "Selected"
    private static let unavailable = "Range unavailable in this update"
    private static let missingChance = "Not shown on this scale"
    private static let offScale = "Above the 50% scale"
    private static let outside = "Your range is outside the five shown."
    private static let unknownResult = "Result unconfirmed"

    private static func row(_ market: String, _ side: String = "Yes") -> Row {
        rows.first { $0.market == market && $0.side == side }!
    }

    private static func ref(_ market: String, _ side: String = "Yes", scope: String = FieldOutlookBars10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: row(market, side).outcome)
    }

    private static func ref(_ row: Row) -> FieldChooserOriginalRef10868 { ref(row.market, row.side) }

    private static func name(_ row: Row) -> String { "\(row.label) · \(row.side)" }

    private static func beforeReading(_ row: Row) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: beforeLabel, value: .recorded(text: row.figure, detail: "\(row.clock) · \(source)"))
    }

    /// CONSTRUCTED words from the ARCHIVED raw winner flag of this exact token
    /// only: a Yes keeps the approved card's "Resolved Yes/No"; a No says its
    /// own "Won/Lost" and is never complemented into its range's Yes result.
    private static func result(_ row: Row) -> FieldChooserResult10868 {
        let words = row.side == "Yes" ? (row.winner ? "Resolved Yes" : "Resolved No") : (row.winner ? "Won" : "Lost")
        return FieldChooserResult10868(title: "Original \(row.side)", words: words)
    }

    /// Every record carries its result in every phase; only the card's phase gate may show it.
    private static func record(_ row: Row) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(row), name: name(row),
            plan: .single(beforeReading(row)),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil,
            result: result(row),
            browseStatus: "Recorded outcome"
        )
    }

    /// CONSTRUCTED hostile record: a later quote, movement, a later clock, a
    /// preview and a station measurement ride along with the same before reading.
    private static func hostile(_ row: Row) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(row), name: name(row),
            plan: .comparison(
                before: beforeReading(row),
                later: FieldChooserReading10868(label: "Last captured", value: .recorded(text: row.laterFigure, detail: "\(row.laterClock) · \(source)"))
            ),
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(segments: [[FieldChooserPoint10868(time: 1, probability: row.later)]],
                                                  emphasis: FieldChooserPoint10868(time: 1, probability: row.later),
                                                  beforeReference: row.before, gaps: []),
                absence: "No history in this card"
            ),
            movement: "Moved 57.4 pts after the day began",
            clock: row.laterClock,
            result: result(row),
            browseStatus: "NWS station high 75.2°F"
        )
    }

    private static let catalogue: [FieldChooserOriginal10868] = rows.map(record)

    private static func slot(_ market: String, _ side: String = "Yes", short: String, label: String? = nil) -> FieldOutlookSlot10868 {
        FieldOutlookSlot10868(ref: ref(market, side), label: label ?? row(market, side).label, shortLabel: short)
    }

    private static let displayed: [FieldOutlookSlot10868] = zip(displayedMarkets, shortLabels).map { slot($0, short: $1) }

    private static let traversal: [FieldChooserOriginalRef10868] = markets.map { ref($0) }

    private static func chance(_ row: Row) -> FieldOutlookBeforeChance10868 {
        FieldOutlookBeforeChance10868(ref: ref(row), probability: row.before, reading: beforeReading(row))
    }

    /// All 22 independent associations, Yes and No alike.
    private static let chances: [FieldOutlookBeforeChance10868] = rows.map(chance)

    private static let scale = FieldOutlookScale10868(
        ceiling: 0.5,
        ticks: [FieldOutlookTick10868(probability: 0, label: "0%"),
                FieldOutlookTick10868(probability: 0.25, label: "25%"),
                FieldOutlookTick10868(probability: 0.5, label: "50%")],
        words: "0–50% chance · each range on its own, not normalized"
    )

    private static let copy = FieldOutlookCopy10868(
        title: "Before the day began",
        note: "Five ranges · last chance before Oct 16",
        graphicLabel: "Before-day chance for five temperature ranges",
        missingChance: missingChance,
        offScale: offScale,
        outsideDisplayed: outside,
        previousLabel: "Previous temperature range",
        nextLabel: "Next temperature range",
        details: "Original outcomes & rules",
        detailsHint: "Opens this exact original",
        resultUnknown: unknownResult
    )

    private static func input(
        catalogue: [FieldChooserOriginal10868] = FieldOutlookBars10868Tests.catalogue,
        selected: FieldChooserOriginalRef10868? = FieldOutlookBars10868Tests.ref("5680548"),
        displayed: [FieldOutlookSlot10868] = FieldOutlookBars10868Tests.displayed,
        traversal: [FieldChooserOriginalRef10868] = FieldOutlookBars10868Tests.traversal,
        chances: [FieldOutlookBeforeChance10868] = FieldOutlookBars10868Tests.chances,
        scale: FieldOutlookScale10868 = FieldOutlookBars10868Tests.scale,
        phase: FieldOutlookPhase10868 = .before
    ) -> FieldOutlookInput10868 {
        FieldOutlookInput10868(
            scope: scope,
            catalogue: catalogue,
            selected: selected.map {
                FieldChooserSelected10868(ref: $0, words: selectedWords, unavailableWords: "Your range is unavailable in this update.")
            },
            displayed: displayed,
            traversal: traversal,
            chances: chances,
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: unavailable,
            chooseHint: "Shows this range’s before-day chance"
        )
    }

    private static func model(_ input: FieldOutlookInput10868 = FieldOutlookBars10868Tests.input()) -> FieldOutlookModel10868 {
        FieldOutlookModel10868(input)
    }

    /// Every line the view shows or speaks, from the same helpers it calls.
    private static func everyLine(_ model: FieldOutlookModel10868) -> [String] {
        let copy = model.input.copy
        var lines = [copy.title, copy.graphicLabel, model.input.scale.words, copy.previousLabel, copy.nextLabel, copy.details]
        lines += [copy.note, copy.detailsHint].compactMap { $0 }
        lines += model.ticks.map(\.label)
        for bar in model.bars {
            lines += [bar.slot.label, bar.slot.shortLabel, model.barSummary(bar), model.hint(model.barAction(bar, canChoose: true))]
            lines += [model.figure(bar), model.stateWords(bar), bar.resolution.original?.name].compactMap { $0 }
        }
        lines += [model.notice, model.selectedOriginal?.name, model.selectedOriginal.flatMap { model.field.selectedWords($0) },
                  model.detailsSpokenLabel, model.neighbour(.previous)?.name, model.neighbour(.next)?.name].compactMap { $0 }
        if let reading = model.selectedReading {
            lines.append(FieldChooserModel10868.spoken(reading))
            lines += [FieldOutlookModel10868.detailLine(reading)].compactMap { $0 }
        }
        switch model.resultLine {
        case .result(let result)?: lines += [result.title, result.words]
        case .unknown(let words)?: lines.append(words)
        case nil: break
        }
        return lines
    }

    private static func raw(_ chance: FieldOutlookChance10868) -> Double? {
        if case .value(let probability, _) = chance { return probability }
        return nil
    }

    // MARK: The packet itself

    func testTheRetainedEventKeeps22IndependentOriginalsOverElevenRanges() {
        XCTAssertEqual(Self.rows.count, 22)
        XCTAssertEqual(Set(Self.rows.map(\.market)), Set(Self.markets))
        XCTAssertEqual(Self.rows.filter { $0.side == "Yes" }.count, 11)
        let refs = Self.catalogue.map(\.ref)
        XCTAssertEqual(Set(refs).count, 22)
        XCTAssertTrue(refs.allSatisfy { $0.isComplete && $0.scope == Self.scope })
        XCTAssertEqual(Self.rows.filter { $0.side == "Yes" }.map(\.before).reduce(0, +), 1.0205, accuracy: 1e-9)

        let model = Self.model()
        for record in Self.catalogue {
            XCTAssertEqual(model.field.resolve(record.ref), .original(record))
        }
        // Raw token winner flags are fixture inputs, not renderer inference.
        XCTAssertTrue(Self.row("5680548").winner)
        XCTAssertFalse(Self.row("5680548", "No").winner)
    }

    // MARK: The five bars

    func testFiveDisplayedBarsKeepTheOwnersOrderRawChancesAndOwnClocks() {
        let model = Self.model()
        let bars = model.bars
        XCTAssertEqual(bars.map(\.slot.ref), Self.displayedMarkets.map { Self.ref($0) })
        XCTAssertEqual(bars.map(\.slot.shortLabel), Self.shortLabels)
        XCTAssertEqual(bars.map { model.figure($0) }, ["5.6%", "23%", "42.5%", "25%", "5%"])

        let raw = [0.0555, 0.23, 0.425, 0.25, 0.0495]
        for (bar, probability) in zip(bars, raw) {
            guard case .value(let value, let fraction) = bar.chance else {
                XCTFail("\(bar.slot.label) has no value")
                continue
            }
            XCTAssertEqual(value, probability)
            XCTAssertEqual(fraction, probability / 0.5, accuracy: 1e-12)
            XCTAssertNil(model.stateWords(bar))
        }

        let clocks = bars.compactMap { $0.resolution.original.flatMap { FieldOutlookModel10868.detailLine(FieldOutlookModel10868.beforeReading($0.plan)) } }
        // The clock line is the owner's detail verbatim; the label is not repeated.
        XCTAssertEqual(clocks, [
            "Oct 15, 8:00:29 PM PT · Polymarket",
            "Oct 15, 8:00:31 PM PT · Polymarket",
            "Oct 15, 8:00:24 PM PT · Polymarket",
            "Oct 15, 8:00:33 PM PT · Polymarket",
            "Oct 15, 8:00:38 PM PT · Polymarket",
        ])
        XCTAssertEqual(model.selectedReading.flatMap(FieldOutlookModel10868.detailLine), "Oct 15, 8:00:24 PM PT · Polymarket")
        XCTAssertNil(FieldOutlookModel10868.detailLine(FieldChooserReading10868(label: Self.beforeLabel, value: .missing("Not recorded before the day"))))
        XCTAssertEqual(model.ticks, [
            FieldOutlookPlacedTick10868(label: "0%", fraction: 0),
            FieldOutlookPlacedTick10868(label: "25%", fraction: 0.5),
            FieldOutlookPlacedTick10868(label: "50%", fraction: 1),
        ])
    }

    func testBarsAreNeverNormalizedComplementedOrSummedAndNoKeepsItsOwnChance() {
        let model = Self.model()
        XCTAssertEqual(model.bars.compactMap { Self.raw($0.chance) }.reduce(0, +), 1.01, accuracy: 1e-9)

        // Showing all 22 originals leaves the five exactly as they were.
        let others = Self.rows.filter { !($0.side == "Yes" && Self.displayedMarkets.contains($0.market)) }
        let everything = Self.model(Self.input(displayed: Self.displayed + others.map { Self.slot($0.market, $0.side, short: $0.label) }))
        XCTAssertEqual(everything.bars.count, 22)
        XCTAssertEqual(Array(everything.bars.prefix(5)).map(\.chance), model.bars.map(\.chance))

        // 74-75°F No keeps its own 57.5%: above the 0.5 ceiling, so no fill — never 1 − 42.5%.
        let no = Self.model(Self.input(displayed: [Self.slot("5680548", "No", short: "74-75° No")]))
        XCTAssertEqual(no.bars[0].chance, .offScale)
        XCTAssertEqual(no.figure(no.bars[0]), "57.5%")
        XCTAssertEqual(no.stateWords(no.bars[0]), Self.offScale)

        // Without its own association a No has no value; its Yes lends it nothing.
        var chances = Self.chances
        chances.removeAll { $0.ref == Self.ref("5680547", "No") }
        let unitScale = FieldOutlookScale10868(ceiling: 1, ticks: [], words: "0–100% chance")
        let orphan = Self.model(Self.input(displayed: [Self.slot("5680547", "No", short: "72-73° No")], chances: chances, scale: unitScale))
        XCTAssertEqual(orphan.bars[0].chance, .unavailable)
        XCTAssertEqual(orphan.figure(orphan.bars[0]), "77%")
        XCTAssertEqual(orphan.stateWords(orphan.bars[0]), Self.missingChance)
        let own = Self.model(Self.input(displayed: [Self.slot("5680547", "No", short: "72-73° No")], scale: unitScale))
        XCTAssertEqual(own.bars[0].chance, .value(probability: 0.77, fraction: 0.77))
    }

    // MARK: Phases

    func testEveryPhaseDrawsTheSameBeforeBarsAndOnlyTheFinalShowsTheSelectedResult() {
        let phases: [FieldOutlookPhase10868] = [.before, .during, .final]
        let models = phases.map { Self.model(Self.input(phase: $0)) }
        for model in models {
            XCTAssertEqual(model.bars, models[0].bars)
            XCTAssertEqual(model.selectedReading, Self.beforeReading(Self.row("5680548")))
        }
        XCTAssertNil(models[0].resultLine)
        XCTAssertNil(models[1].resultLine)
        XCTAssertEqual(models[2].resultLine, .result(FieldChooserResult10868(title: "Original Yes", words: "Resolved Yes")))
        for model in models.prefix(2) {
            XCTAssertFalse(Self.everyLine(model).contains { $0.contains("Resolved") })
        }

        // Another selected original keeps its own result, not the winner's.
        let other = Self.model(Self.input(selected: Self.ref("5680547"), phase: .final))
        XCTAssertEqual(other.resultLine, .result(FieldChooserResult10868(title: "Original Yes", words: "Resolved No")))
        XCTAssertEqual(other.bars, models[0].bars)

        // Unknown is not a loss, and no 0% or 100% endpoint is invented.
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref == Self.ref("5680548") }!
        let old = catalogue[index]
        catalogue[index] = FieldChooserOriginal10868(ref: old.ref, name: old.name, plan: old.plan, preview: old.preview,
                                                     movement: nil, clock: nil, result: nil, browseStatus: old.browseStatus)
        let unknown = Self.model(Self.input(catalogue: catalogue, phase: .final))
        XCTAssertEqual(unknown.resultLine, .unknown(Self.unknownResult))
        for phase in [FieldOutlookPhase10868.before, .during] {
            XCTAssertNil(Self.model(Self.input(catalogue: catalogue, phase: phase)).resultLine, "\(phase)")
        }
        XCTAssertEqual(unknown.bars.map(\.chance), models[0].bars.map(\.chance))
        XCTAssertFalse(Self.everyLine(unknown).contains { $0.contains("100%") || $0.contains("Resolved") })
    }

    func testASelectedNoShowsItsOwnTokenResultOnlyAtTheFinal() {
        // 74-75°F No: raw winner false → its own Lost. 72-73°F No: raw winner true → its own Won.
        for (market, words) in [("5680548", "Lost"), ("5680547", "Won")] {
            let ref = Self.ref(market, "No")
            XCTAssertEqual(Self.row(market, "No").winner, words == "Won")
            for phase in [FieldOutlookPhase10868.before, .during, .final] {
                let label = "\(market) No \(phase)"
                let model = Self.model(Self.input(selected: ref, phase: phase))
                XCTAssertEqual(model.field.selectedRef, ref, label)
                XCTAssertEqual(model.selectedReading, Self.beforeReading(Self.row(market, "No")), label)
                let lines = Self.everyLine(model)
                if phase == .final {
                    XCTAssertEqual(model.resultLine, .result(FieldChooserResult10868(title: "Original No", words: words)), label)
                } else {
                    XCTAssertNil(model.resultLine, label)
                    XCTAssertFalse(lines.contains { $0.contains("Won") || $0.contains("Lost") }, label)
                }
                XCTAssertFalse(lines.contains { $0.contains("Resolved") }, label)
            }
        }
    }

    func testLaterQuotesMovementPreviewAndTheStationReadingNeverReachTheCard() {
        let hostile = Self.rows.map(Self.hostile)
        let leaks = ["Last captured", "Oct 16, 10:00", "Moved 57.4", "75.2", "NWS", ">99.9%"]
        for phase in [FieldOutlookPhase10868.before, .during, .final] {
            let label = "\(phase)"
            let model = Self.model(Self.input(catalogue: hostile, phase: phase))
            let plain = Self.model(Self.input(phase: phase))
            XCTAssertEqual(model.bars.map(\.chance), plain.bars.map(\.chance), label)
            XCTAssertEqual(model.bars.map { model.figure($0) }, plain.bars.map { plain.figure($0) }, label)
            XCTAssertEqual(model.selectedReading, Self.beforeReading(Self.row("5680548")), label)
            let lines = Self.everyLine(model)
            for leak in leaks {
                XCTAssertFalse(lines.contains { $0.contains(leak) }, "\(label): \(leak)")
            }
            XCTAssertEqual(lines.contains { $0.contains("Resolved") }, phase == .final, label)
        }
    }

    // MARK: Selection

    func testASelectionOutsideTheBarsStaysSelectedWithANoticeAndOpensExactly() {
        let inside = Self.model()
        XCTAssertNil(inside.notice)
        XCTAssertEqual(inside.bars.filter(inside.isSelected).map(\.slot.ref), [Self.ref("5680548")])

        let outsideRef = Self.ref("5680544")
        let outside = Self.model(Self.input(selected: outsideRef))
        XCTAssertEqual(outside.field.selectedRef, outsideRef)
        XCTAssertTrue(outside.isSelectedOutsideDisplayed)
        XCTAssertEqual(outside.notice, Self.outside)
        XCTAssertFalse(outside.bars.contains(where: outside.isSelected))
        XCTAssertEqual(outside.selectedReading, Self.beforeReading(Self.row("5680544")))
        XCTAssertEqual(outside.detailsRef(canOpen: true), outsideRef)

        // The No of a shown range is its own original: outside, never swapped to its Yes bar.
        let noRef = Self.ref("5680548", "No")
        let no = Self.model(Self.input(selected: noRef))
        XCTAssertEqual(no.field.selectedRef, noRef)
        XCTAssertEqual(no.notice, Self.outside)
        XCTAssertFalse(no.bars.contains(where: no.isSelected))
        XCTAssertEqual(no.selectedReading, Self.beforeReading(Self.row("5680548", "No")))
        XCTAssertEqual(no.detailsRef(canOpen: true), noRef)

        // An unresolved selection shows the owner's words and selects nothing.
        let missing = FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5680548", outcomeID: "constructed-withdrawn")
        let gone = Self.model(Self.input(selected: missing))
        XCTAssertEqual(gone.notice, "Your range is unavailable in this update.")
        XCTAssertNil(gone.selectedOriginal)
        XCTAssertNil(gone.selectedReading)
        XCTAssertNil(gone.detailsRef(canOpen: true))
        XCTAssertNil(gone.stepAction(.next, canChoose: true))
        XCTAssertFalse(gone.bars.contains(where: gone.isSelected))
    }

    func testPreviousAndNextFollowTheOwnersOrderAndStopAtItsEnds() {
        let model = Self.model()
        XCTAssertEqual(model.neighbour(.previous)?.ref, Self.ref("5680547"))
        XCTAssertEqual(model.neighbour(.next)?.ref, Self.ref("5680549"))
        XCTAssertEqual(model.stepAction(.previous, canChoose: true), .choose(Self.ref("5680547")))
        XCTAssertEqual(model.stepAction(.next, canChoose: true), .choose(Self.ref("5680549")))
        XCTAssertNil(model.stepAction(.next, canChoose: false))

        let first = Self.model(Self.input(selected: Self.ref("5680542")))
        XCTAssertNil(first.neighbour(.previous))
        XCTAssertEqual(first.neighbour(.next)?.ref, Self.ref("5680543"))
        let last = Self.model(Self.input(selected: Self.ref("5680552")))
        XCTAssertEqual(last.neighbour(.previous)?.ref, Self.ref("5680551"))
        XCTAssertNil(last.neighbour(.next))

        // An original outside the owner's order has no neighbours; no nearest one is elected.
        let no = Self.model(Self.input(selected: Self.ref("5680548", "No")))
        XCTAssertNil(no.neighbour(.previous))
        XCTAssertNil(no.neighbour(.next))
    }

    func testANeighbourThatCannotResolveStopsThatStepWithoutSkippingAhead() {
        var catalogue = Self.catalogue
        catalogue.removeAll { $0.ref == Self.ref("5680549") }
        let withdrawn = Self.model(Self.input(catalogue: catalogue))
        XCTAssertNil(withdrawn.neighbour(.next))
        XCTAssertNil(withdrawn.stepAction(.next, canChoose: true))
        XCTAssertEqual(withdrawn.neighbour(.previous)?.ref, Self.ref("5680547"))

        let next = Self.markets.firstIndex(of: "5680549")!
        let broken: [FieldChooserOriginalRef10868] = [
            Self.ref("5680549", scope: "constructed:weather:other"),
            FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: " ", outcomeID: Self.row("5680549").outcome),
            FieldChooserOriginalRef10868(scope: Self.scope, source: "", marketID: "5680549", outcomeID: Self.row("5680549").outcome),
        ]
        for neighbour in broken {
            var traversal = Self.traversal
            traversal[next] = neighbour
            let model = Self.model(Self.input(traversal: traversal))
            XCTAssertNil(model.neighbour(.next), "\(neighbour)")
            XCTAssertEqual(model.neighbour(.previous)?.ref, Self.ref("5680547"))
        }

        // A neighbour listed twice is ambiguous; a selection listed twice has no neighbours.
        let doubledNeighbour = Self.model(Self.input(traversal: Self.traversal + [Self.ref("5680549")]))
        XCTAssertNil(doubledNeighbour.neighbour(.next))
        XCTAssertEqual(doubledNeighbour.neighbour(.previous)?.ref, Self.ref("5680547"))
        let doubledSelection = Self.model(Self.input(traversal: Self.traversal + [Self.ref("5680548")]))
        XCTAssertNil(doubledSelection.neighbour(.previous))
        XCTAssertNil(doubledSelection.neighbour(.next))
    }

    // MARK: Callbacks

    func testCallbacksHandBackExactIdentitiesAndNoCallbackIsStatic() {
        let model = Self.model()
        var chosen: [FieldChooserOriginalRef10868] = []
        for bar in model.bars {
            let action = model.barAction(bar, canChoose: true)
            XCTAssertEqual(action, .choose(bar.slot.ref))
            XCTAssertEqual(model.hint(action), "Shows this range’s before-day chance")
            action?.perform(onChoose: { chosen.append($0) }, onControl: nil)
            XCTAssertNil(model.barAction(bar, canChoose: false))
            XCTAssertEqual(model.hint(model.barAction(bar, canChoose: false)), "")
        }
        XCTAssertEqual(chosen, Self.displayed.map(\.ref))

        model.stepAction(.previous, canChoose: true)?.perform(onChoose: { chosen.append($0) }, onControl: nil)
        XCTAssertEqual(chosen.last, Self.ref("5680547"))

        XCTAssertEqual(model.detailsRef(canOpen: true), Self.ref("5680548"))
        XCTAssertNil(model.detailsRef(canOpen: false))
        XCTAssertEqual(model.detailsSpokenLabel, "Original outcomes & rules, 74-75°F · Yes")
    }

    // MARK: Identity failures

    func testDuplicateForeignBlankAndWithdrawnSlotsKeepTheirNamedUnavailableSlot() {
        let withdrawnRef = FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5680552", outcomeID: "constructed-withdrawn")
        let displayed = Self.displayed + [
            Self.displayed[1],
            FieldOutlookSlot10868(ref: Self.ref("5680551", scope: "constructed:weather:other"), label: "80-81°F", shortLabel: "80-81°"),
            FieldOutlookSlot10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: " ", marketID: "5680545", outcomeID: Self.row("5680545").outcome),
                                  label: "68-69°F", shortLabel: "68-69°"),
            FieldOutlookSlot10868(ref: withdrawnRef, label: "82°F or higher", shortLabel: "82°+"),
            FieldOutlookSlot10868(ref: withdrawnRef, label: "  ", shortLabel: ""),
        ]
        let model = Self.model(Self.input(displayed: displayed))
        let bars = model.bars
        XCTAssertEqual(bars.count, 10)
        for index in [1, 5, 6, 7, 8, 9] {
            let bar = bars[index]
            XCTAssertEqual(bar.resolution, .unavailable, "\(index)")
            XCTAssertEqual(bar.chance, .unavailable, "\(index)")
            XCTAssertNil(model.figure(bar), "\(index)")
            XCTAssertEqual(model.stateWords(bar), Self.unavailable, "\(index)")
            XCTAssertNil(model.barAction(bar, canChoose: true), "\(index)")
            XCTAssertFalse(model.isSelected(bar), "\(index)")
        }
        XCTAssertEqual(model.barSummary(bars[6]), "80-81°F. \(Self.unavailable)")
        XCTAssertEqual(model.barSummary(bars[9]), Self.unavailable)
        for index in [0, 2, 3, 4] {
            XCTAssertNotNil(Self.raw(bars[index].chance), "\(index)")
            XCTAssertEqual(model.barAction(bars[index], canChoose: true), .choose(bars[index].slot.ref))
        }
        XCTAssertTrue(model.isSelected(bars[2]))

        // A catalogue identity carried twice is unavailable — the chooser's own rule.
        let doubled = Self.model(Self.input(catalogue: Self.catalogue + [Self.record(Self.row("5680549"))]))
        XCTAssertEqual(doubled.bars[3].resolution, .unavailable)
        XCTAssertNil(doubled.barAction(doubled.bars[3], canChoose: true))
        XCTAssertEqual(doubled.bars[2].chance, model.bars[2].chance)
    }

    func testDuplicateForeignMismatchedAndUnlistedChancesBorrowNothing() {
        var chances = Self.chances
        // 72-73°F Yes listed twice — even identically — is never resolved to the first.
        chances.append(Self.chance(Self.row("5680547")))
        // 76-77°F Yes: only a foreign-scope association.
        let own = chances.firstIndex { $0.ref == Self.ref("5680549") }!
        chances[own] = FieldOutlookBeforeChance10868(ref: Self.ref("5680549", scope: "constructed:weather:other"),
                                                     probability: 0.25, reading: Self.beforeReading(Self.row("5680549")))
        // 70-71°F Yes: the association is a LATER observation's reading.
        let early = chances.firstIndex { $0.ref == Self.ref("5680546") }!
        let row = Self.row("5680546")
        chances[early] = FieldOutlookBeforeChance10868(
            ref: Self.ref("5680546"), probability: row.later,
            reading: FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: row.laterFigure, detail: "\(row.laterClock) · \(Self.source)"))
        )
        // An association for an original that is not shown changes nothing.
        chances.append(FieldOutlookBeforeChance10868(ref: Self.ref("5680551"), probability: 0.4, reading: Self.beforeReading(Self.row("5680551"))))

        let model = Self.model(Self.input(chances: chances))
        let bars = model.bars
        XCTAssertEqual(bars.map(\.chance), [
            .unavailable,
            .unavailable,
            .value(probability: 0.425, fraction: 0.85),
            .unavailable,
            .value(probability: 0.0495, fraction: 0.099),
        ])
        XCTAssertEqual(bars.map { model.figure($0) }, ["5.6%", "23%", "42.5%", "25%", "5%"])
        for index in [0, 1, 3] {
            XCTAssertEqual(model.stateWords(bars[index]), Self.missingChance)
            // A missing chance never disables a qualified original.
            XCTAssertEqual(model.barAction(bars[index], canChoose: true), .choose(bars[index].slot.ref))
        }

        // The raw value is taken as supplied; the figure is never parsed into it.
        var tied = Self.chances
        let selected = tied.firstIndex { $0.ref == Self.ref("5680548") }!
        tied[selected] = FieldOutlookBeforeChance10868(ref: Self.ref("5680548"), probability: 0.3, reading: Self.beforeReading(Self.row("5680548")))
        let given = Self.model(Self.input(chances: tied))
        XCTAssertEqual(given.bars[2].chance, .value(probability: 0.3, fraction: 0.6))
        XCTAssertEqual(given.figure(given.bars[2]), "42.5%")
    }

    // MARK: Scale

    func testARealZeroIsAZeroMarkAndInvalidOrOffScaleValuesDrawNoFill() {
        func chance(_ probability: Double, scale: FieldOutlookScale10868 = FieldOutlookBars10868Tests.scale) -> FieldOutlookChance10868 {
            var chances = Self.chances
            let index = chances.firstIndex { $0.ref == Self.ref("5680548") }!
            chances[index] = FieldOutlookBeforeChance10868(ref: Self.ref("5680548"), probability: probability, reading: Self.beforeReading(Self.row("5680548")))
            return Self.model(Self.input(chances: chances, scale: scale)).bars[2].chance
        }
        XCTAssertEqual(chance(0), .value(probability: 0, fraction: 0))
        XCTAssertEqual(chance(0).fraction, 0)
        XCTAssertEqual(chance(0.5), .value(probability: 0.5, fraction: 1))
        XCTAssertEqual(chance(0.6), .offScale)
        XCTAssertEqual(chance(1), .offScale)
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.01] {
            XCTAssertEqual(chance(bad), .unavailable, "\(bad)")
        }
        XCTAssertNil(FieldOutlookGeometry10868.fraction(0.6, ceiling: 0.5))
        XCTAssertNil(FieldOutlookGeometry10868.fraction(-0.01, ceiling: 0.5))
        XCTAssertEqual(FieldOutlookGeometry10868.fraction(0.25, ceiling: 0.5), 0.5)

        for ceiling in [0, -0.5, 1.5, Double.nan, .infinity] {
            let invalid = FieldOutlookScale10868(ceiling: ceiling, ticks: Self.scale.ticks, words: Self.scale.words)
            let model = Self.model(Self.input(scale: invalid))
            XCTAssertTrue(model.bars.allSatisfy { $0.chance == .unavailable }, "\(ceiling)")
            XCTAssertEqual(model.ticks, [], "\(ceiling)")
            XCTAssertTrue(model.bars.allSatisfy { model.barAction($0, canChoose: true) != nil }, "\(ceiling)")
        }
    }

    func testTicksAndBarsShareOneScaleInEveryOrientation() {
        let scale = FieldOutlookScale10868(
            ceiling: 0.5,
            ticks: [FieldOutlookTick10868(probability: 0.5, label: "50%"),
                    FieldOutlookTick10868(probability: 0.75, label: "75%"),
                    FieldOutlookTick10868(probability: .nan, label: "?"),
                    FieldOutlookTick10868(probability: -0.1, label: "-10%"),
                    FieldOutlookTick10868(probability: 0, label: "0%")],
            words: Self.scale.words
        )
        let model = Self.model(Self.input(scale: scale))
        XCTAssertEqual(model.ticks, [FieldOutlookPlacedTick10868(label: "50%", fraction: 1), FieldOutlookPlacedTick10868(label: "0%", fraction: 0)])

        XCTAssertEqual(FieldOutlookGeometry10868.orientations(accessibilitySize: true), [.horizontal])
        XCTAssertEqual(FieldOutlookGeometry10868.orientations(accessibilitySize: false), [.vertical, .horizontal])

        // Vertical heights and horizontal widths are the same fraction of the one ceiling.
        let fractions = model.bars.map { $0.chance.fraction ?? -1 }
        for (fraction, expected) in zip(fractions, [0.111, 0.46, 0.85, 0.5, 0.099]) {
            XCTAssertEqual(fraction, expected, accuracy: 1e-12)
        }
    }

    // MARK: Drawing plan (the helper both bar Canvases call)

    func testTheBarDrawingPlanKeepsTinyFillsExactAndOutlinesOnlyADrawableInset() {
        let track = CGSize(width: 264, height: 14)
        // ARCHIVED 0.0005 on the 0…0.5 scale: a 0.264 pt fill, exact, with no inset outline.
        let tiny = FieldOutlookGeometry10868.fraction(0.0005, ceiling: 0.5)!
        let tinyPlan = FieldOutlookGeometry10868.markPlan(fraction: tiny, in: track, orientation: .horizontal, selected: true)
        XCTAssertEqual(tinyPlan.fill?.width ?? -1, 0.264, accuracy: 1e-9)
        XCTAssertEqual(tinyPlan.fill?.minX, 0)
        XCTAssertNil(tinyPlan.outline)
        XCTAssertNil(tinyPlan.zeroMark)
        // Any fill up to 2 pt has no drawable 1 pt inset.
        for width in [0.5, 1.9] {
            let plan = FieldOutlookGeometry10868.markPlan(fraction: width / 264, in: track, orientation: .horizontal, selected: true)
            XCTAssertEqual(plan.fill?.width ?? -1, CGFloat(width), accuracy: 1e-9)
            XCTAssertNil(plan.outline, "\(width)")
        }
        let exactlyTwo = FieldOutlookGeometry10868.markPlan(fraction: 0.25, in: CGSize(width: 8, height: 14), orientation: .horizontal, selected: true)
        XCTAssertEqual(exactlyTwo.fill, CGRect(x: 0, y: 0, width: 2, height: 14))
        XCTAssertNil(exactlyTwo.outline)

        // A normal selected fill keeps its exact width and an outline 1 pt inside it.
        let selected = FieldOutlookGeometry10868.markPlan(fraction: 0.85, in: track, orientation: .horizontal, selected: true)
        XCTAssertEqual(selected.fill, CGRect(x: 0, y: 0, width: 264 * 0.85, height: 14))
        XCTAssertEqual(selected.outline, CGRect(x: 1, y: 1, width: 264 * 0.85 - 2, height: 12))
        let plain = FieldOutlookGeometry10868.markPlan(fraction: 0.85, in: track, orientation: .horizontal, selected: false)
        XCTAssertEqual(plain.fill, selected.fill)
        XCTAssertNil(plain.outline)

        // A real 0% is a zero mark, not a fill, selected or not.
        let zero = FieldOutlookGeometry10868.markPlan(fraction: 0, in: track, orientation: .horizontal, selected: true)
        XCTAssertEqual(zero, FieldOutlookMarkPlan10868(fill: nil, zeroMark: CGRect(x: 0, y: 0, width: 3, height: 14), outline: nil))

        // Vertical bars use the same plan from the bottom edge.
        let column = CGSize(width: 28, height: 120)
        let vertical = FieldOutlookGeometry10868.markPlan(fraction: 0.85, in: column, orientation: .vertical, selected: true)
        XCTAssertEqual(vertical.fill?.height ?? -1, 102, accuracy: 1e-9)
        XCTAssertEqual(vertical.fill?.maxY ?? -1, 120, accuracy: 1e-9)
        XCTAssertNotNil(vertical.outline)
        let tinyColumn = FieldOutlookGeometry10868.markPlan(fraction: tiny, in: column, orientation: .vertical, selected: true)
        XCTAssertEqual(tinyColumn.fill?.height ?? -1, 0.12, accuracy: 1e-9)
        XCTAssertNil(tinyColumn.outline)
        XCTAssertEqual(FieldOutlookGeometry10868.markPlan(fraction: 0, in: column, orientation: .vertical, selected: false).zeroMark,
                       CGRect(x: 0, y: 117, width: 28, height: 3))

        // Nothing for a missing, off-scale or invalid fraction, or an undrawable size.
        for fraction in [nil, Double.nan, -0.1, 1.2] {
            XCTAssertEqual(FieldOutlookGeometry10868.markPlan(fraction: fraction, in: track, orientation: .horizontal, selected: true), .empty, "\(String(describing: fraction))")
        }
        for size in [CGSize(width: 0, height: 14), CGSize(width: -10, height: 14), CGSize(width: 264, height: 0),
                     CGSize(width: CGFloat.nan, height: 14), CGSize(width: CGFloat.infinity, height: 14)] {
            XCTAssertEqual(FieldOutlookGeometry10868.markPlan(fraction: 0.85, in: size, orientation: .horizontal, selected: true), .empty, "\(size)")
        }

        // The bars feed it their own fraction: off-scale and unavailable draw nothing.
        let offScale = Self.model(Self.input(displayed: [Self.slot("5680548", "No", short: "74-75° No")])).bars[0]
        XCTAssertEqual(FieldOutlookGeometry10868.markPlan(fraction: offScale.chance.fraction, in: track, orientation: .horizontal, selected: false), .empty)
    }

    // MARK: Spoken text

    func testLongLabelsAndEveryReadingAreSpokenWhole() {
        let long = "Will the highest temperature in New York City be between 74-75°F on October 16?"
        let displayed = [Self.slot("5680548", short: long, label: long)]
        let model = Self.model(Self.input(displayed: displayed))
        let bar = model.bars[0]
        XCTAssertEqual(bar.slot.label, long)
        XCTAssertEqual(bar.slot.shortLabel, long)
        XCTAssertEqual(model.barSummary(bar), "Selected. Before the day: 42.5%, Oct 15, 8:00:24 PM PT · Polymarket")

        let other = Self.model().bars[3]
        XCTAssertEqual(Self.model().barSummary(other), "Before the day: 25%, Oct 15, 8:00:33 PM PT · Polymarket")

        let offScale = Self.model(Self.input(displayed: [Self.slot("5680548", "No", short: "74-75° No")]))
        XCTAssertEqual(offScale.barSummary(offScale.bars[0]), "Before the day: 57.5%, Oct 15, 8:00:35 PM PT · Polymarket. \(Self.offScale)")
    }
}

// MARK: - #10868 field movement — "By noon, the outlook shifted"

/// The weather-range probability-change card, on the chooser's own resolver.
///
/// ARCHIVED raw values come from Polymarket event 1186943 (KLGA daily high,
/// October 16, 2026), as retained in
/// `shipping-adoption-20261027/WEATHER-RANGE-MOVEMENT-RETAINED-CASES.json`
/// (sha256 b78d62b0…9eb9a2ed): 11 range markets and their 22 independent Yes/No
/// outcome tokens, each token's own before sample (`before.p`), its own sample
/// recorded by noon (`recorded_by_noon.p`), a day-end control and its raw CLOB
/// winner flag. The approved displayed order is 72-73°F, 76-77°F, 70-71°F Yes
/// (0.23 → 0.345, 0.25 → 0.149, 0.0555 → 0.093) on a −15…+15 pp scale.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope
/// string, every name, short label, reading label, figure text (prepared with
/// the reference `probabilityLabel.ts`), PT clock line (from each sample's own
/// archived time) and source word, the movement words (the reference's
/// `toFixed(1)` + " pp"), the opaque observation keys, the card copy, phase,
/// scale words and tick labels, the hostile day-end/preview/movement/clock/
/// result/station inputs, and every withdrawn, duplicate, blank, foreign,
/// missing-endpoint and long-label case. The NWS 75.2°F station maximum
/// appears only as a hostile string.
final class FieldMovementCard10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Row = (
        market: String, side: String, outcome: String, label: String,
        before: Double, beforeFigure: String, beforeClock: String,
        noon: Double, noonFigure: String, noonClock: String,
        movement: String, winner: Bool,
        dayEnd: Double, dayEndFigure: String, dayEndClock: String
    )

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:weather:1186943:noon-movement"

    /// ARCHIVED ids, labels, raw samples and winner flags in the packet's
    /// market order; figures, PT clocks and movement words CONSTRUCTED from them.
    private static let rows: [Row] = [
        ("5680542", "Yes", "8913365083547058840727648558007260174176426214539964433076390904943107112394", "63°F or below", 0.001, "0.1%", "Oct 15, 8:00:24 PM PT", 0.0005, "0.1%", "Oct 16, 8:00:28 AM PT", "-0.1 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:23 PM PT"),
        ("5680542", "No", "67143910402456435176578359128729756115174394812031754735508727643398464506662", "63°F or below", 0.999, "99.9%", "Oct 15, 8:00:26 PM PT", 0.9995, ">99.9%", "Oct 16, 8:00:29 AM PT", "+0.1 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:24 PM PT"),
        ("5680543", "Yes", "21435336294206529333936969966675079269275336661376130928308328232499909515391", "64-65°F", 0.0005, "0.1%", "Oct 15, 8:00:39 PM PT", 0.0005, "0.1%", "Oct 16, 8:00:43 AM PT", "0.0 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:39 PM PT"),
        ("5680543", "No", "48052455767302060707788102938270415116722038376468308401484694477735066651219", "64-65°F", 0.9995, ">99.9%", "Oct 15, 8:00:28 PM PT", 0.9995, ">99.9%", "Oct 16, 8:00:32 AM PT", "0.0 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:27 PM PT"),
        ("5680544", "Yes", "107185634455894843610821566880080305468286254817220973775097065618207888752080", "66-67°F", 0.0025, "0.3%", "Oct 15, 8:00:32 PM PT", 0.004, "0.4%", "Oct 16, 8:00:36 AM PT", "+0.1 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:31 PM PT"),
        ("5680544", "No", "115375096568369311164990277104328957168943720891530048218212965811147823644840", "66-67°F", 0.9975, "99.8%", "Oct 15, 8:00:27 PM PT", 0.996, "99.6%", "Oct 16, 8:00:31 AM PT", "-0.2 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:26 PM PT"),
        ("5680545", "Yes", "22967642455827047245443771889541595907465471141356386761611041695657210518526", "68-69°F", 0.0045, "0.5%", "Oct 15, 8:00:29 PM PT", 0.003, "0.3%", "Oct 16, 8:00:33 AM PT", "-0.1 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:28 PM PT"),
        ("5680545", "No", "111537624900846583946658455929539667688050754968556058471851612149659391288540", "68-69°F", 0.9955, "99.6%", "Oct 15, 8:00:23 PM PT", 0.997, "99.7%", "Oct 16, 8:00:27 AM PT", "+0.1 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:21 PM PT"),
        ("5680546", "Yes", "30208396863628859266853401360725945315246332277999808492807567061425111095221", "70-71°F", 0.0555, "5.6%", "Oct 15, 8:00:29 PM PT", 0.093, "9.3%", "Oct 16, 8:00:33 AM PT", "+3.8 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:28 PM PT"),
        ("5680546", "No", "55998474664018695178236956222472451286538263762519786120813722164777651946447", "70-71°F", 0.9445, "94.5%", "Oct 15, 8:00:37 PM PT", 0.907, "90.7%", "Oct 16, 8:00:41 AM PT", "-3.7 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:36 PM PT"),
        ("5680547", "Yes", "42036490969657814030627686441430315859255282297966320641421618604860015683758", "72-73°F", 0.23, "23%", "Oct 15, 8:00:31 PM PT", 0.345, "34.5%", "Oct 16, 8:00:34 AM PT", "+11.5 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:29 PM PT"),
        ("5680547", "No", "78761077488813221723830555306140100365304550954782607751025590225868446872439", "72-73°F", 0.77, "77%", "Oct 15, 8:00:26 PM PT", 0.655, "65.5%", "Oct 16, 8:00:30 AM PT", "-11.5 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:24 PM PT"),
        ("5680548", "Yes", "97348811011973241846205943545597316259341369137822213272638970018898274192104", "74-75°F", 0.425, "42.5%", "Oct 15, 8:00:24 PM PT", 0.395, "39.5%", "Oct 16, 8:00:28 AM PT", "-3.0 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:23 PM PT"),
        ("5680548", "No", "28807578185858778284793037276021658713791873585944870616198704837627433997315", "74-75°F", 0.575, "57.5%", "Oct 15, 8:00:35 PM PT", 0.605, "60.5%", "Oct 16, 8:00:38 AM PT", "+3.0 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:34 PM PT"),
        ("5680549", "Yes", "62146049061772800442104405416602150380256265203802495142118020885435023782389", "76-77°F", 0.25, "25%", "Oct 15, 8:00:33 PM PT", 0.149, "14.9%", "Oct 16, 8:00:36 AM PT", "-10.1 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:31 PM PT"),
        ("5680549", "No", "108307178477820030136628870794100368956919345679782937733831167636973962051916", "76-77°F", 0.75, "75%", "Oct 15, 8:00:39 PM PT", 0.808, "80.8%", "Oct 16, 8:00:43 AM PT", "+5.8 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:38 PM PT"),
        ("5680550", "Yes", "21314677505606064787348766190871059866661422817349009784997764731054747568592", "78-79°F", 0.0495, "5%", "Oct 15, 8:00:38 PM PT", 0.018, "1.8%", "Oct 16, 8:00:42 AM PT", "-3.1 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:37 PM PT"),
        ("5680550", "No", "27892904031490668791126455162520384280106755558205528849525683031242904636615", "78-79°F", 0.9505, "95.1%", "Oct 15, 8:00:38 PM PT", 0.982, "98.2%", "Oct 16, 8:00:42 AM PT", "+3.1 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:37 PM PT"),
        ("5680551", "Yes", "96821810520797185036939183674087082483401017115855467226269310242027501278307", "80-81°F", 0.0015, "0.2%", "Oct 15, 8:00:31 PM PT", 0.0025, "0.3%", "Oct 16, 8:00:34 AM PT", "+0.1 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:30 PM PT"),
        ("5680551", "No", "54280296140785189409090952621928778327442017227711905048188438819366865032300", "80-81°F", 0.9985, "99.9%", "Oct 15, 8:00:37 PM PT", 0.9975, "99.8%", "Oct 16, 8:00:40 AM PT", "-0.1 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:36 PM PT"),
        ("5680552", "Yes", "29814975981391780694220300609647509354017812743734941224964105916454287716710", "82°F or higher", 0.0005, "0.1%", "Oct 15, 8:00:40 PM PT", 0.0005, "0.1%", "Oct 16, 8:00:44 AM PT", "0.0 pp", false, 0.0005, "0.1%", "Oct 16, 8:00:40 PM PT"),
        ("5680552", "No", "22622594704289114994972145212761010706883868125649760533252652075898736439602", "82°F or higher", 0.9995, ">99.9%", "Oct 15, 8:00:35 PM PT", 0.9995, ">99.9%", "Oct 16, 8:00:38 AM PT", "0.0 pp", true, 0.9995, ">99.9%", "Oct 16, 8:00:34 PM PT"),
    ]

    private static let markets = ["5680542", "5680543", "5680544", "5680545", "5680546", "5680547",
                                  "5680548", "5680549", "5680550", "5680551", "5680552"]
    /// The approved displayed order, as owner input — never sorted here.
    private static let displayedMarkets = ["5680547", "5680549", "5680546"]
    /// CONSTRUCTED compact labels, written out — never derived from the full label.
    private static let shortLabels = ["72-73°", "76-77°", "70-71°"]

    private static let beforeLabel = "Before the day"
    private static let laterLabel = "Captured by noon"
    private static let source = "Polymarket"
    private static let unavailable = "Range unavailable in this update"
    private static let endpointUnavailable = "Not recorded for this comparison"
    private static let changeUnavailable = "Change unavailable"
    private static let offScale = "Beyond the ±15 pp scale"
    private static let openHint = "Opens this exact original at its recorded time"

    private static func row(_ market: String, _ side: String = "Yes") -> Row {
        rows.first { $0.market == market && $0.side == side }!
    }

    private static func ref(_ market: String, _ side: String = "Yes", scope: String = FieldMovementCard10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: row(market, side).outcome)
    }

    private static func ref(_ row: Row) -> FieldChooserOriginalRef10868 { ref(row.market, row.side) }

    private static func name(_ row: Row) -> String { "\(row.label) · \(row.side)" }

    private static func beforeReading(_ row: Row) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: beforeLabel, value: .recorded(text: row.beforeFigure, detail: "\(row.beforeClock) · \(source)"))
    }

    private static func noonReading(_ row: Row) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: laterLabel, value: .recorded(text: row.noonFigure, detail: "\(row.noonClock) · \(source)"))
    }

    /// CONSTRUCTED hostile day-end reading — a later quote, never the card's.
    private static func dayEndReading(_ row: Row) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Recorded through Oct 16", value: .recorded(text: row.dayEndFigure, detail: "\(row.dayEndClock) · \(source)"))
    }

    private static func result(_ row: Row) -> FieldChooserResult10868 {
        let words = row.side == "Yes" ? (row.winner ? "Resolved Yes" : "Resolved No") : (row.winner ? "Won" : "Lost")
        return FieldChooserResult10868(title: "Original \(row.side)", words: words)
    }

    /// Every record carries its result; the card never reads it.
    private static func record(_ row: Row, plan: FieldChooserDisplayPlan10868? = nil) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(row), name: name(row),
            plan: plan ?? .comparison(before: beforeReading(row), later: noonReading(row)),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil,
            result: result(row),
            browseStatus: "Recorded outcome"
        )
    }

    /// CONSTRUCTED hostile record: the same noon comparison plan with a
    /// day-end preview, movement words, a day-end clock, its result and a
    /// station measurement riding along.
    private static func hostile(_ row: Row) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(row), name: name(row),
            plan: .comparison(before: beforeReading(row), later: noonReading(row)),
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(segments: [[FieldChooserPoint10868(time: 1, probability: row.dayEnd)]],
                                                  emphasis: FieldChooserPoint10868(time: 1, probability: row.dayEnd),
                                                  beforeReference: row.before, gaps: []),
                absence: "No history in this card"
            ),
            movement: "Moved 57.4 pts after the day began",
            clock: row.dayEndClock,
            result: result(row),
            browseStatus: "NWS station high 75.2°F"
        )
    }

    private static let catalogue: [FieldChooserOriginal10868] = rows.map { record($0) }

    private static func observationKey(_ row: Row) -> String { "constructed-observation:\(row.outcome):noon" }

    private static func pair(_ row: Row) -> FieldMovementPair10868 {
        FieldMovementPair10868(
            ref: ref(row),
            before: FieldMovementObservation10868(probability: row.before, reading: beforeReading(row)),
            later: FieldMovementObservation10868(probability: row.noon, reading: noonReading(row)),
            movement: row.movement,
            observation: observationKey(row)
        )
    }

    /// All 22 independent associations, Yes and No alike.
    private static let pairs: [FieldMovementPair10868] = rows.map(pair)

    private static func slot(_ market: String, _ side: String = "Yes", short: String, label: String? = nil) -> FieldOutlookSlot10868 {
        FieldOutlookSlot10868(ref: ref(market, side), label: label ?? row(market, side).label, shortLabel: short)
    }

    private static let displayed: [FieldOutlookSlot10868] = zip(displayedMarkets, shortLabels).map { slot($0, short: $1) }

    private static let scale = FieldMovementScale10868(
        limit: 0.15,
        ticks: [FieldMovementTick10868(change: -0.15, label: "-15 pp"),
                FieldMovementTick10868(change: 0, label: "0"),
                FieldMovementTick10868(change: 0.15, label: "+15 pp")],
        words: "−15 to +15 percentage points · each range on its own"
    )

    private static let copy = FieldMovementCopy10868(
        title: "By noon, the outlook shifted",
        note: "Before day → captured by noon · percentage points",
        graphicLabel: "Change in chance for three temperature ranges",
        beforeLabel: beforeLabel,
        laterLabel: laterLabel,
        endpointUnavailable: endpointUnavailable,
        changeUnavailable: changeUnavailable,
        offScale: offScale,
        openLabel: "Original · exact times",
        openHint: openHint
    )

    private static func input(
        catalogue: [FieldChooserOriginal10868] = FieldMovementCard10868Tests.catalogue,
        displayed: [FieldOutlookSlot10868] = FieldMovementCard10868Tests.displayed,
        pairs: [FieldMovementPair10868] = FieldMovementCard10868Tests.pairs,
        scale: FieldMovementScale10868 = FieldMovementCard10868Tests.scale,
        phase: FieldOutlookPhase10868 = .during
    ) -> FieldMovementInput10868 {
        FieldMovementInput10868(
            scope: scope,
            catalogue: catalogue,
            displayed: displayed,
            pairs: pairs,
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: unavailable
        )
    }

    private static func model(_ input: FieldMovementInput10868 = FieldMovementCard10868Tests.input()) -> FieldMovementModel10868 {
        FieldMovementModel10868(input)
    }

    /// One original's catalogue record with its plan replaced.
    private static func catalogue(replacing market: String, _ side: String = "Yes", plan: FieldChooserDisplayPlan10868) -> [FieldChooserOriginal10868] {
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref == ref(market, side) }!
        catalogue[index] = record(row(market, side), plan: plan)
        return catalogue
    }

    /// One original's association replaced; nil removes it.
    private static func pairs(replacing market: String, _ side: String = "Yes", with replacement: FieldMovementPair10868?) -> [FieldMovementPair10868] {
        var pairs = Self.pairs
        let index = pairs.firstIndex { $0.ref == ref(market, side) }!
        if let replacement { pairs[index] = replacement } else { pairs.remove(at: index) }
        return pairs
    }

    private static func figure(_ endpoint: FieldMovementEndpoint10868?) -> String? {
        guard case .reading(let reading)? = endpoint, case .recorded(let text, _) = reading.value else { return nil }
        return text
    }

    private static func raw(_ change: FieldMovementChange10868) -> Double? {
        if case .value(let change, _) = change { return change }
        return nil
    }

    /// Every line the view shows or speaks, from the same helpers it calls.
    private static func everyLine(_ model: FieldMovementModel10868) -> [String] {
        guard model.isShown else { return [] }
        let copy = model.input.copy
        var lines = [copy.title, copy.graphicLabel, model.input.scale.words, copy.openLabel, model.graphicSummary]
        lines += [copy.note, copy.openHint].compactMap { $0 }
        lines += model.ticks.map(\.label)
        for row in model.rows {
            lines += [row.slot.label, row.slot.shortLabel, model.rowSummary(row), model.hint(model.openAction(row, canOpen: true))]
            lines += [model.movementWords(row), model.stateWords(row), row.resolution.original?.name].compactMap { $0 }
            for endpoint in [row.before, row.later].compactMap({ $0 }) {
                lines.append(FieldMovementModel10868.spoken(endpoint))
                if case .reading(let reading) = endpoint {
                    lines += [FieldOutlookModel10868.detailLine(reading)].compactMap { $0 }
                }
            }
        }
        return lines
    }

    // MARK: The three retained ranges

    func testTheThreeRetainedRangesKeepTheOwnersOrderOwnClocksAndSignedPlaces() {
        XCTAssertEqual(Self.rows.count, 22)
        XCTAssertEqual(Set(Self.catalogue.map(\.ref)).count, 22)
        let model = Self.model()
        for record in Self.catalogue {
            XCTAssertEqual(model.field.resolve(record.ref), .original(record))
        }

        let rows = model.rows
        XCTAssertEqual(rows.map(\.slot.ref), Self.displayedMarkets.map { Self.ref($0) })
        XCTAssertEqual(rows.map(\.slot.shortLabel), Self.shortLabels)
        XCTAssertEqual(rows.map { Self.figure($0.before) }, ["23%", "25%", "5.6%"])
        XCTAssertEqual(rows.map { Self.figure($0.later) }, ["34.5%", "14.9%", "9.3%"])
        for (row, market) in zip(rows, Self.displayedMarkets) {
            XCTAssertEqual(row.before, .reading(Self.beforeReading(Self.row(market))))
            XCTAssertEqual(row.later, .reading(Self.noonReading(Self.row(market))))
        }

        // Each endpoint keeps its own clock; nothing shares one time.
        let clocks = rows.map { row -> [String?] in
            [row.before, row.later].map { endpoint in
                guard case .reading(let reading)? = endpoint else { return nil }
                return FieldOutlookModel10868.detailLine(reading)
            }
        }
        XCTAssertEqual(clocks, [
            ["Oct 15, 8:00:31 PM PT · Polymarket", "Oct 16, 8:00:34 AM PT · Polymarket"],
            ["Oct 15, 8:00:33 PM PT · Polymarket", "Oct 16, 8:00:36 AM PT · Polymarket"],
            ["Oct 15, 8:00:29 PM PT · Polymarket", "Oct 16, 8:00:33 AM PT · Polymarket"],
        ])

        // Raw later − raw before places the bar; the words are the owner's.
        let expected: [(change: Double, fraction: Double)] = [(0.115, 0.115 / 0.15), (-0.101, -0.101 / 0.15), (0.0375, 0.25)]
        for (row, value) in zip(rows, expected) {
            guard case .value(let change, let fraction) = row.change else {
                XCTFail("\(row.slot.label) has no change")
                continue
            }
            XCTAssertEqual(change, value.change, accuracy: 1e-12)
            XCTAssertEqual(fraction, value.fraction, accuracy: 1e-12)
            XCTAssertNil(model.stateWords(row))
        }
        XCTAssertEqual(rows.map { model.movementWords($0) }, ["+11.5 pp", "-10.1 pp", "+3.8 pp"])
        XCTAssertEqual(model.ticks, [
            FieldOutlookPlacedTick10868(label: "-15 pp", fraction: -1),
            FieldOutlookPlacedTick10868(label: "0", fraction: 0),
            FieldOutlookPlacedTick10868(label: "+15 pp", fraction: 1),
        ])
    }

    // MARK: Phases

    func testDuringAndFinalShowTheSameNoonComparisonAndBeforeShowsNoCard() {
        let before = Self.model(Self.input(phase: .before))
        XCTAssertFalse(before.isShown)
        XCTAssertEqual(before.rows, [])
        XCTAssertEqual(before.graphicSummary, "")
        XCTAssertEqual(Self.everyLine(before), [])

        let during = Self.model(Self.input(phase: .during))
        let final = Self.model(Self.input(phase: .final))
        XCTAssertTrue(during.isShown)
        XCTAssertTrue(final.isShown)
        XCTAssertEqual(final.rows, during.rows)
        XCTAssertEqual(final.rows.map { final.rowSummary($0) }, during.rows.map { during.rowSummary($0) })
        XCTAssertEqual(final.graphicSummary, during.graphicSummary)
        XCTAssertEqual(final.rows.map { final.openAction($0, canOpen: true) }, during.rows.map { during.openAction($0, canOpen: true) })
        // The final keeps the noon figures — never the day-end ones, never a result.
        XCTAssertEqual(final.rows.map { Self.figure($0.later) }, ["34.5%", "14.9%", "9.3%"])
        for leak in ["Resolved", "Won", "Lost"] {
            XCTAssertFalse(Self.everyLine(final).contains { $0.contains(leak) }, leak)
        }
    }

    func testResultsDayEndPreviewMovementClockAndStationNeverReachTheCard() {
        let hostile = Self.rows.map(Self.hostile)
        let dayEndClocks = Self.displayedMarkets.map { Self.row($0).dayEndClock }
        let leaks = ["Moved 57.4", "75.2", "NWS", "Resolved", "Won", "Lost", "Recorded through"] + dayEndClocks
        for phase in [FieldOutlookPhase10868.during, .final] {
            let label = "\(phase)"
            let model = Self.model(Self.input(catalogue: hostile, phase: phase))
            let plain = Self.model(Self.input(phase: phase))
            XCTAssertEqual(model.rows.map(\.change), plain.rows.map(\.change), label)
            XCTAssertEqual(model.rows.map(\.before), plain.rows.map(\.before), label)
            XCTAssertEqual(model.rows.map(\.later), plain.rows.map(\.later), label)
            let lines = Self.everyLine(model)
            for leak in leaks {
                XCTAssertFalse(lines.contains { $0.contains(leak) }, "\(label): \(leak)")
            }
        }

        // A plan whose later reading is the day-end quote is not this pair's:
        // that endpoint, the bar, the words and the key all stay away.
        let dayEnd = Self.row("5680547")
        let swapped = Self.model(Self.input(
            catalogue: Self.catalogue(replacing: "5680547", plan: .comparison(before: Self.beforeReading(dayEnd), later: Self.dayEndReading(dayEnd))),
            phase: .final
        ))
        let row = swapped.rows[0]
        XCTAssertEqual(row.before, .reading(Self.beforeReading(dayEnd)))
        XCTAssertEqual(row.later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable))
        XCTAssertEqual(row.change, .unavailable)
        XCTAssertNil(swapped.movementWords(row))
        XCTAssertEqual(swapped.stateWords(row), Self.changeUnavailable)
        XCTAssertEqual(swapped.openAction(row, canOpen: true), FieldMovementOpen10868(ref: Self.ref("5680547"), observation: nil))
        XCTAssertFalse(Self.everyLine(swapped).contains { $0.contains(dayEnd.dayEndClock) })
        XCTAssertEqual(Array(swapped.rows.dropFirst()), Array(Self.model(Self.input(phase: .final)).rows.dropFirst()))

        // An association carrying the day-end quote mismatches the noon plan the same way.
        let laterPair = FieldMovementPair10868(
            ref: Self.ref("5680547"),
            before: FieldMovementObservation10868(probability: dayEnd.before, reading: Self.beforeReading(dayEnd)),
            later: FieldMovementObservation10868(probability: dayEnd.dayEnd, reading: Self.dayEndReading(dayEnd)),
            movement: "-23.0 pp",
            observation: "constructed-observation:day-end"
        )
        let mismatched = Self.model(Self.input(pairs: Self.pairs(replacing: "5680547", with: laterPair), phase: .final))
        XCTAssertEqual(mismatched.rows[0].later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable))
        XCTAssertEqual(mismatched.rows[0].change, .unavailable)
        XCTAssertNil(mismatched.movementWords(mismatched.rows[0]))
        XCTAssertEqual(mismatched.openAction(mismatched.rows[0], canOpen: true)?.observation, nil)
        XCTAssertFalse(Self.everyLine(mismatched).contains { $0.contains("-23.0") || $0.contains("day-end") })
    }

    // MARK: Independent originals

    func testEveryNoKeepsItsOwnEndpointsAndIsNeverComplemented() {
        let nos = zip(Self.displayedMarkets, Self.shortLabels).map { Self.slot($0, "No", short: "\($1) No") }
        let model = Self.model(Self.input(displayed: nos))
        let rows = model.rows
        XCTAssertEqual(rows.map { Self.figure($0.before) }, ["77%", "75%", "94.5%"])
        XCTAssertEqual(rows.map { Self.figure($0.later) }, ["65.5%", "80.8%", "90.7%"])
        XCTAssertEqual(rows.map { model.movementWords($0) }, ["-11.5 pp", "+5.8 pp", "-3.7 pp"])
        for (row, expected) in zip(rows, [-0.115, 0.058, -0.0375]) {
            XCTAssertEqual(Self.raw(row.change) ?? .nan, expected, accuracy: 1e-12, row.slot.label)
        }
        // 76-77°F: Yes fell 10.1 pp, its own No rose 5.8 pp — never the mirror image.
        let yes = Self.model().rows[1]
        XCTAssertNotEqual((Self.raw(yes.change) ?? 0) + (Self.raw(rows[1].change) ?? 0), 0, accuracy: 1e-6)

        // Without its own association a No has nothing; its Yes lends it nothing.
        let orphan = Self.model(Self.input(displayed: [nos[0]], pairs: Self.pairs(replacing: "5680547", "No", with: nil)))
        let row = orphan.rows[0]
        XCTAssertEqual(row.before, .unavailable(label: Self.beforeLabel, words: Self.endpointUnavailable))
        XCTAssertEqual(row.later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable))
        XCTAssertEqual(row.change, .unavailable)
        XCTAssertNil(orphan.movementWords(row))
        XCTAssertEqual(orphan.openAction(row, canOpen: true), FieldMovementOpen10868(ref: Self.ref("5680547", "No"), observation: nil))
        XCTAssertNotNil(orphan.pair(for: Self.ref("5680547")))
    }

    // MARK: Identity failures

    func testUnresolvedAndRepeatedSlotsKeepTheirNamedUnavailableSlot() {
        let withdrawnRef = FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5680552", outcomeID: "constructed-withdrawn")
        let displayed = Self.displayed + [
            Self.displayed[0],
            FieldOutlookSlot10868(ref: Self.ref("5680551", scope: "constructed:weather:other"), label: "80-81°F", shortLabel: "80-81°"),
            FieldOutlookSlot10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: " ", marketID: "5680545", outcomeID: Self.row("5680545").outcome),
                                  label: "68-69°F", shortLabel: "68-69°"),
            FieldOutlookSlot10868(ref: withdrawnRef, label: "82°F or higher", shortLabel: "82°+"),
            FieldOutlookSlot10868(ref: withdrawnRef, label: "  ", shortLabel: ""),
        ]
        let model = Self.model(Self.input(displayed: displayed))
        let rows = model.rows
        XCTAssertEqual(rows.count, 8)
        XCTAssertEqual(rows.map(\.slot), displayed)
        for index in [0, 3, 4, 5, 6, 7] {
            let row = rows[index]
            XCTAssertEqual(row.resolution, .unavailable, "\(index)")
            XCTAssertNil(row.before, "\(index)")
            XCTAssertNil(row.later, "\(index)")
            XCTAssertEqual(row.change, .unavailable, "\(index)")
            XCTAssertNil(model.movementWords(row), "\(index)")
            XCTAssertEqual(model.stateWords(row), Self.unavailable, "\(index)")
            XCTAssertNil(model.openAction(row, canOpen: true), "\(index)")
        }
        XCTAssertEqual(model.rowSummary(rows[4]), "80-81°F. \(Self.unavailable)")
        XCTAssertEqual(model.rowSummary(rows[7]), Self.unavailable)
        for index in [1, 2] {
            XCTAssertNotNil(Self.raw(rows[index].change), "\(index)")
            XCTAssertEqual(model.openAction(rows[index], canOpen: true)?.ref, rows[index].slot.ref)
        }
        XCTAssertEqual(model.graphicSummary,
                       "72-73°F: \(Self.unavailable); 76-77°F: -10.1 pp; 70-71°F: +3.8 pp; 72-73°F: \(Self.unavailable); "
                       + "80-81°F: \(Self.unavailable); 68-69°F: \(Self.unavailable); 82°F or higher: \(Self.unavailable); \(Self.unavailable)")

        // A catalogue identity carried twice is unavailable — the chooser's own rule.
        let doubled = Self.model(Self.input(catalogue: Self.catalogue + [Self.record(Self.row("5680549"))]))
        XCTAssertEqual(doubled.rows[1].resolution, .unavailable)
        XCTAssertNil(doubled.openAction(doubled.rows[1], canOpen: true))
        XCTAssertEqual(doubled.rows[0], Self.model().rows[0])
    }

    func testDuplicateForeignBlankMismatchedAndUnlistedPairsBorrowNothing() {
        var pairs = Self.pairs
        // 72-73°F Yes listed twice — even identically — is never resolved to the first.
        pairs.append(Self.pair(Self.row("5680547")))
        // 76-77°F Yes: only a foreign-scope association, then only a blank-source one.
        let foreign = Self.pair(Self.row("5680549"))
        pairs = pairs.map { $0.ref == Self.ref("5680549") ? FieldMovementPair10868(
            ref: Self.ref("5680549", scope: "constructed:weather:other"), before: foreign.before, later: foreign.later,
            movement: foreign.movement, observation: foreign.observation) : $0 }
        // An association for an original that is not shown changes nothing.
        pairs.append(FieldMovementPair10868(ref: Self.ref("5680551"), before: nil, later: nil, movement: "+40.0 pp", observation: "constructed-unlisted"))

        let model = Self.model(Self.input(pairs: pairs))
        for index in [0, 1] {
            let row = model.rows[index]
            XCTAssertEqual(row.before, .unavailable(label: Self.beforeLabel, words: Self.endpointUnavailable), "\(index)")
            XCTAssertEqual(row.later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable), "\(index)")
            XCTAssertEqual(row.change, .unavailable, "\(index)")
            XCTAssertNil(model.movementWords(row), "\(index)")
            XCTAssertEqual(model.stateWords(row), Self.changeUnavailable, "\(index)")
            // The exact original stays openable; no key is borrowed.
            XCTAssertEqual(model.openAction(row, canOpen: true), FieldMovementOpen10868(ref: row.slot.ref, observation: nil), "\(index)")
        }
        XCTAssertEqual(model.rows[2], Self.model().rows[2])
        XCTAssertFalse(Self.everyLine(model).contains { $0.contains("+40.0") || $0.contains("unlisted") })

        let blankSource = FieldMovementPair10868(
            ref: FieldChooserOriginalRef10868(scope: Self.scope, source: " ", marketID: "5680549", outcomeID: Self.row("5680549").outcome),
            before: foreign.before, later: foreign.later, movement: foreign.movement, observation: foreign.observation)
        let blank = Self.model(Self.input(pairs: Self.pairs(replacing: "5680549", with: blankSource)))
        XCTAssertEqual(blank.rows[1].change, .unavailable)
        XCTAssertEqual(blank.rows[1].later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable))

        // Blank movement words: both figures stay tied, but no bar and no words are invented.
        let quiet = Self.pair(Self.row("5680546"))
        let wordless = Self.model(Self.input(pairs: Self.pairs(replacing: "5680546", with: FieldMovementPair10868(
            ref: quiet.ref, before: quiet.before, later: quiet.later, movement: "  ", observation: quiet.observation))))
        XCTAssertEqual(wordless.rows[2].before, Self.model().rows[2].before)
        XCTAssertEqual(wordless.rows[2].later, Self.model().rows[2].later)
        XCTAssertEqual(wordless.rows[2].change, .unavailable)
        XCTAssertNil(wordless.movementWords(wordless.rows[2]))
        XCTAssertEqual(wordless.stateWords(wordless.rows[2]), Self.changeUnavailable)

        // The raw values are taken as supplied; the figures are never parsed and the words never recomputed.
        let given = Self.row("5680547")
        let tied = FieldMovementPair10868(
            ref: Self.ref("5680547"),
            before: FieldMovementObservation10868(probability: 0.2, reading: Self.beforeReading(given)),
            later: FieldMovementObservation10868(probability: given.noon, reading: Self.noonReading(given)),
            movement: given.movement, observation: Self.observationKey(given))
        let supplied = Self.model(Self.input(pairs: Self.pairs(replacing: "5680547", with: tied)))
        XCTAssertEqual(Self.raw(supplied.rows[0].change) ?? .nan, 0.145, accuracy: 1e-12)
        XCTAssertEqual(Self.figure(supplied.rows[0].before), "23%")
        XCTAssertEqual(supplied.movementWords(supplied.rows[0]), "+11.5 pp")
    }

    // MARK: Missing endpoints and zero

    func testAMissingEndpointKeepsTheOtherAndATrueZeroIsAValue() {
        let row = Self.row("5680547")

        // A single plan keeps its genuine before; no later, no movement is invented.
        let single = Self.model(Self.input(catalogue: Self.catalogue(replacing: "5680547", plan: .single(Self.beforeReading(row))))).rows[0]
        XCTAssertEqual(single.before, .reading(Self.beforeReading(row)))
        XCTAssertEqual(single.later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable))
        XCTAssertEqual(single.change, .unavailable)

        // The owner's absence words for the later endpoint are shown as they are.
        let notByNoon = FieldChooserReading10868(label: Self.laterLabel, value: .missing("Not recorded by noon"))
        let noLater = Self.model(Self.input(catalogue: Self.catalogue(replacing: "5680547", plan: .comparison(before: Self.beforeReading(row), later: notByNoon))))
        XCTAssertEqual(noLater.rows[0].before, .reading(Self.beforeReading(row)))
        XCTAssertEqual(noLater.rows[0].later, .reading(notByNoon))
        XCTAssertEqual(noLater.rows[0].change, .unavailable)
        XCTAssertEqual(noLater.openAction(noLater.rows[0], canOpen: true)?.observation, nil)

        // A missing before keeps the tied later figure and its key.
        let notBefore = FieldChooserReading10868(label: Self.beforeLabel, value: .missing("Not recorded before the day"))
        let laterOnly = FieldMovementPair10868(ref: Self.ref(row), before: nil,
                                               later: FieldMovementObservation10868(probability: row.noon, reading: Self.noonReading(row)),
                                               movement: nil, observation: Self.observationKey(row))
        let noBefore = Self.model(Self.input(
            catalogue: Self.catalogue(replacing: "5680547", plan: .comparison(before: notBefore, later: Self.noonReading(row))),
            pairs: Self.pairs(replacing: "5680547", with: laterOnly)
        ))
        XCTAssertEqual(noBefore.rows[0].before, .reading(notBefore))
        XCTAssertEqual(noBefore.rows[0].later, .reading(Self.noonReading(row)))
        XCTAssertEqual(noBefore.rows[0].change, .unavailable)
        XCTAssertEqual(noBefore.openAction(noBefore.rows[0], canOpen: true)?.observation, Self.observationKey(row))

        // An association with only its before tie keeps that figure alone.
        let beforeOnly = FieldMovementPair10868(ref: Self.ref(row),
                                                before: FieldMovementObservation10868(probability: row.before, reading: Self.beforeReading(row)),
                                                later: nil, movement: row.movement, observation: Self.observationKey(row))
        let half = Self.model(Self.input(pairs: Self.pairs(replacing: "5680547", with: beforeOnly))).rows[0]
        XCTAssertEqual(half.before, .reading(Self.beforeReading(row)))
        XCTAssertEqual(half.later, .unavailable(label: Self.laterLabel, words: Self.endpointUnavailable))
        XCTAssertEqual(half.change, .unavailable)

        // ARCHIVED unchanged pairs (0.0005 → 0.0005) are a real 0: a neutral zero mark, never missing.
        let unchanged = Self.model(Self.input(displayed: [Self.slot("5680543", short: "64-65°"), Self.slot("5680552", short: "82°+")]))
        for row in unchanged.rows {
            XCTAssertEqual(row.change, .value(change: 0, fraction: 0), row.slot.label)
            XCTAssertEqual(unchanged.movementWords(row), "0.0 pp")
            XCTAssertNil(unchanged.stateWords(row))
            let plan = FieldMovementGeometry10868.markPlan(fraction: row.change.fraction, in: CGSize(width: 32, height: 140), orientation: .vertical)
            XCTAssertNotNil(plan.zeroMark)
            XCTAssertNil(plan.fill)
        }

        // A real 0% endpoint is a value too.
        let zero = FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: "0%", detail: "\(row.beforeClock) · \(Self.source)"))
        let fromZero = FieldMovementPair10868(ref: Self.ref(row),
                                              before: FieldMovementObservation10868(probability: 0, reading: zero),
                                              later: FieldMovementObservation10868(probability: row.noon, reading: Self.noonReading(row)),
                                              movement: "+34.5 pp", observation: Self.observationKey(row))
        let fromNothing = Self.model(Self.input(
            catalogue: Self.catalogue(replacing: "5680547", plan: .comparison(before: zero, later: Self.noonReading(row))),
            pairs: Self.pairs(replacing: "5680547", with: fromZero),
            scale: FieldMovementScale10868(limit: 0.5, ticks: [], words: "−50 to +50 percentage points")
        ))
        XCTAssertEqual(Self.figure(fromNothing.rows[0].before), "0%")
        XCTAssertEqual(fromNothing.rows[0].change, .value(change: 0.345, fraction: 0.69))
    }

    // MARK: Scale

    func testInvalidNonFiniteAndOffScaleChangesDrawNoBar() {
        let row = Self.row("5680547")
        func change(before: Double, later: Double) -> FieldMovementRow10868 {
            let pair = FieldMovementPair10868(
                ref: Self.ref(row),
                before: FieldMovementObservation10868(probability: before, reading: Self.beforeReading(row)),
                later: FieldMovementObservation10868(probability: later, reading: Self.noonReading(row)),
                movement: row.movement, observation: Self.observationKey(row))
            return Self.model(Self.input(pairs: Self.pairs(replacing: "5680547", with: pair))).rows[0]
        }
        for bad in [Double.nan, .infinity, -.infinity, -0.01, 1.01] {
            for candidate in [change(before: bad, later: row.noon), change(before: row.before, later: bad)] {
                XCTAssertEqual(candidate.change, .unavailable, "\(bad)")
                // The owner's tied figures stay; only the bar is withheld.
                XCTAssertEqual(Self.figure(candidate.before), "23%")
                XCTAssertEqual(Self.figure(candidate.later), "34.5%")
            }
        }

        // Beyond the owner's limit: no fill, the words and the off-scale words; never clamped.
        let narrow = FieldMovementScale10868(limit: 0.1, ticks: Self.scale.ticks, words: "−10 to +10 percentage points")
        let model = Self.model(Self.input(scale: narrow))
        XCTAssertEqual(model.rows[0].change, .offScale(rising: true))
        XCTAssertEqual(model.rows[1].change, .offScale(rising: false))
        XCTAssertEqual(Self.raw(model.rows[2].change) ?? .nan, 0.0375, accuracy: 1e-12)
        XCTAssertEqual(model.rows[2].change.fraction ?? .nan, 0.375, accuracy: 1e-12)
        XCTAssertEqual(model.rows.map { model.movementWords($0) }, ["+11.5 pp", "-10.1 pp", "+3.8 pp"])
        XCTAssertEqual(model.rows.map { model.stateWords($0) }, [Self.offScale, Self.offScale, nil])
        XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: model.rows[0].change.fraction, in: CGSize(width: 32, height: 140), orientation: .vertical), .empty)
        // Ticks beyond the limit are dropped, in the owner's order.
        XCTAssertEqual(model.ticks, [FieldOutlookPlacedTick10868(label: "0", fraction: 0)])

        for limit in [0, -0.15, 1.5, Double.nan, .infinity] {
            let invalid = Self.model(Self.input(scale: FieldMovementScale10868(limit: limit, ticks: Self.scale.ticks, words: Self.scale.words)))
            XCTAssertTrue(invalid.rows.allSatisfy { $0.change == .unavailable }, "\(limit)")
            XCTAssertEqual(invalid.ticks, [], "\(limit)")
            XCTAssertTrue(invalid.rows.allSatisfy { invalid.openAction($0, canOpen: true) != nil }, "\(limit)")
        }

        let scale = FieldMovementScale10868(
            limit: 0.15,
            ticks: [FieldMovementTick10868(change: 0.15, label: "+15 pp"),
                    FieldMovementTick10868(change: .nan, label: "?"),
                    FieldMovementTick10868(change: -0.2, label: "-20 pp"),
                    FieldMovementTick10868(change: 0, label: "0")],
            words: Self.scale.words
        )
        XCTAssertEqual(Self.model(Self.input(scale: scale)).ticks,
                       [FieldOutlookPlacedTick10868(label: "+15 pp", fraction: 1), FieldOutlookPlacedTick10868(label: "0", fraction: 0)])
        XCTAssertNil(FieldMovementGeometry10868.fraction(0.16, limit: 0.15))
        XCTAssertNil(FieldMovementGeometry10868.fraction(-0.16, limit: 0.15))
        XCTAssertNil(FieldMovementGeometry10868.fraction(.nan, limit: 0.15))
        XCTAssertEqual(FieldMovementGeometry10868.fraction(-0.075, limit: 0.15), -0.5)
    }

    // MARK: Open

    func testOpenHandsBackTheExactOriginalAndOpaqueObservationAndNoCallbackIsStatic() {
        let model = Self.model()
        var opened: [FieldMovementOpen10868] = []
        for (row, market) in zip(model.rows, Self.displayedMarkets) {
            let opening = model.openAction(row, canOpen: true)
            XCTAssertEqual(opening, FieldMovementOpen10868(ref: Self.ref(market), observation: Self.observationKey(Self.row(market))))
            XCTAssertEqual(model.hint(opening), Self.openHint)
            if let opening { opened.append(opening) }
            XCTAssertNil(model.openAction(row, canOpen: false))
            XCTAssertEqual(model.hint(model.openAction(row, canOpen: false)), "")
        }
        XCTAssertEqual(opened.map(\.ref), Self.displayed.map(\.ref))

        // A blank key is no key; the exact original still opens.
        let quiet = Self.pair(Self.row("5680549"))
        let keyless = Self.model(Self.input(pairs: Self.pairs(replacing: "5680549", with: FieldMovementPair10868(
            ref: quiet.ref, before: quiet.before, later: quiet.later, movement: quiet.movement, observation: " "))))
        XCTAssertEqual(keyless.openAction(keyless.rows[1], canOpen: true), FieldMovementOpen10868(ref: Self.ref("5680549"), observation: nil))
        XCTAssertEqual(keyless.rows[1].change, Self.model().rows[1].change)
    }

    // MARK: Spoken text

    func testSpokenRowsKeepWholeLabelsEveryEndpointFigureAndClock() {
        let model = Self.model()
        XCTAssertEqual(model.rowSummary(model.rows[0]),
                       "Before the day: 23%, Oct 15, 8:00:31 PM PT · Polymarket. Captured by noon: 34.5%, Oct 16, 8:00:34 AM PT · Polymarket. +11.5 pp")
        XCTAssertEqual(model.rowSummary(model.rows[1]),
                       "Before the day: 25%, Oct 15, 8:00:33 PM PT · Polymarket. Captured by noon: 14.9%, Oct 16, 8:00:36 AM PT · Polymarket. -10.1 pp")
        XCTAssertEqual(model.graphicSummary, "72-73°F: +11.5 pp; 76-77°F: -10.1 pp; 70-71°F: +3.8 pp")

        let long = "Will the highest temperature in New York City be between 72-73°F on October 16?"
        let whole = Self.model(Self.input(displayed: [Self.slot("5680547", short: long, label: long)]))
        XCTAssertEqual(whole.rows[0].slot.label, long)
        XCTAssertEqual(whole.rows[0].slot.shortLabel, long)
        XCTAssertEqual(whole.graphicSummary, "\(long): +11.5 pp")

        let single = Self.model(Self.input(catalogue: Self.catalogue(replacing: "5680547", plan: .single(Self.beforeReading(Self.row("5680547"))))))
        XCTAssertEqual(single.rowSummary(single.rows[0]),
                       "Before the day: 23%, Oct 15, 8:00:31 PM PT · Polymarket. Captured by noon: \(Self.endpointUnavailable). \(Self.changeUnavailable)")

        let narrow = Self.model(Self.input(scale: FieldMovementScale10868(limit: 0.1, ticks: [], words: "−10 to +10 percentage points")))
        XCTAssertTrue(narrow.rowSummary(narrow.rows[0]).hasSuffix("+11.5 pp. \(Self.offScale)"))
    }

    // MARK: Drawing plan (the helper both bar Canvases call)

    func testTheSignedDrawingPlanSharesOneScaleInBothOrientations() {
        let column = CGSize(width: 32, height: 140)
        let rising = FieldMovementGeometry10868.markPlan(fraction: 0.115 / 0.15, in: column, orientation: .vertical)
        XCTAssertEqual(rising.fill?.maxY ?? -1, 70, accuracy: 1e-9)
        XCTAssertEqual(rising.fill?.height ?? -1, 70 * 0.115 / 0.15, accuracy: 1e-9)
        XCTAssertNil(rising.zeroMark)
        let falling = FieldMovementGeometry10868.markPlan(fraction: -0.101 / 0.15, in: column, orientation: .vertical)
        XCTAssertEqual(falling.fill?.minY ?? -1, 70, accuracy: 1e-9)
        XCTAssertEqual(falling.fill?.height ?? -1, 70 * 0.101 / 0.15, accuracy: 1e-9)

        let track = CGSize(width: 264, height: 16)
        XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: 0.25, in: track, orientation: .horizontal),
                       FieldMovementMarkPlan10868(fill: CGRect(x: 132, y: 0, width: 33, height: 16), zeroMark: nil))
        let left = FieldMovementGeometry10868.markPlan(fraction: -0.101 / 0.15, in: track, orientation: .horizontal)
        XCTAssertEqual(left.fill?.maxX ?? -1, 132, accuracy: 1e-9)
        XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: 1, in: track, orientation: .horizontal).fill,
                       CGRect(x: 132, y: 0, width: 132, height: 16))
        XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: -1, in: column, orientation: .vertical).fill,
                       CGRect(x: 0, y: 70, width: 32, height: 70))

        // An unchanged pair is a neutral mark across the zero axis in both orientations.
        XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: 0, in: column, orientation: .vertical),
                       FieldMovementMarkPlan10868(fill: nil, zeroMark: CGRect(x: 0, y: 68.5, width: 32, height: 3)))
        XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: 0, in: track, orientation: .horizontal),
                       FieldMovementMarkPlan10868(fill: nil, zeroMark: CGRect(x: 130.5, y: 0, width: 3, height: 16)))

        // Ticks and bars sit on the same axis: zero in the middle, ±limit at the edges.
        XCTAssertEqual(FieldMovementGeometry10868.unit(0, orientation: .vertical), 0.5)
        XCTAssertEqual(FieldMovementGeometry10868.unit(1, orientation: .vertical), 0)
        XCTAssertEqual(FieldMovementGeometry10868.unit(-1, orientation: .vertical), 1)
        XCTAssertEqual(FieldMovementGeometry10868.unit(-1, orientation: .horizontal), 0)
        XCTAssertEqual(FieldMovementGeometry10868.unit(1, orientation: .horizontal), 1)
        XCTAssertEqual(FieldOutlookGeometry10868.orientations(accessibilitySize: true), [.horizontal])
        XCTAssertEqual(FieldOutlookGeometry10868.orientations(accessibilitySize: false), [.vertical, .horizontal])

        // Nothing for a missing, off-scale or invalid fraction, or an undrawable size.
        for fraction in [nil, Double.nan, -1.2, 1.2] {
            XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: fraction, in: track, orientation: .horizontal), .empty, "\(String(describing: fraction))")
        }
        for size in [CGSize(width: 0, height: 16), CGSize(width: -10, height: 16), CGSize(width: 264, height: 0),
                     CGSize(width: CGFloat.nan, height: 16), CGSize(width: CGFloat.infinity, height: 16)] {
            XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: 0.5, in: size, orientation: .horizontal), .empty, "\(size)")
        }
    }
}

// MARK: A1 — a change on the scale's limit is the limit, not off-scale

extension FieldMovementCard10868Tests {
    /// 72-73°F Yes alone, re-tied to CONSTRUCTED raw endpoints and figures on
    /// its own clocks, through the real model.
    private static func boundaryModel(before: Double, beforeFigure: String, later: Double, laterFigure: String, movement: String) -> FieldMovementModel10868 {
        let row = Self.row("5680547")
        let earlier = FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: beforeFigure, detail: "\(row.beforeClock) · \(Self.source)"))
        let recorded = FieldChooserReading10868(label: Self.laterLabel, value: .recorded(text: laterFigure, detail: "\(row.noonClock) · \(Self.source)"))
        let pair = FieldMovementPair10868(
            ref: Self.ref(row),
            before: FieldMovementObservation10868(probability: before, reading: earlier),
            later: FieldMovementObservation10868(probability: later, reading: recorded),
            movement: movement, observation: Self.observationKey(row))
        return Self.model(Self.input(
            catalogue: Self.catalogue(replacing: "5680547", plan: .comparison(before: earlier, later: recorded)),
            displayed: [Self.slot("5680547", short: "72-73°")],
            pairs: Self.pairs(replacing: "5680547", with: pair)
        ))
    }

    func testAChangeOnTheScaleLimitDrawsItsFullBarBothWaysInBothOrientations() {
        // In binary, 0.65 − 0.5 is 0.15000000000000002: just past the 0.15 limit.
        let rise = 0.65 - 0.5
        let fall = 0.5 - 0.65
        XCTAssertGreaterThan(rise, Self.scale.limit)
        XCTAssertLessThan(fall, -Self.scale.limit)

        let column = CGSize(width: 32, height: 140)
        let track = CGSize(width: 264, height: 16)
        func check(_ model: FieldMovementModel10868, change: Double, fraction: Double, words: String,
                   figures: [String], vertical: CGRect, horizontal: CGRect) {
            let row = model.rows[0]
            // The raw change is kept exactly; only its place sits on the edge.
            XCTAssertEqual(row.change, .value(change: change, fraction: fraction), words)
            XCTAssertEqual(Self.raw(row.change), change, words)
            XCTAssertEqual(Self.figure(row.before), figures[0], words)
            XCTAssertEqual(Self.figure(row.later), figures[1], words)
            XCTAssertEqual(model.movementWords(row), words)
            XCTAssertNil(model.stateWords(row), words)
            XCTAssertEqual(model.graphicSummary, "72-73°F: \(words)")
            XCTAssertEqual(model.rowSummary(row),
                           "Before the day: \(figures[0]), Oct 15, 8:00:31 PM PT · Polymarket. "
                           + "Captured by noon: \(figures[1]), Oct 16, 8:00:34 AM PT · Polymarket. \(words)")
            XCTAssertFalse(Self.everyLine(model).contains(Self.offScale), words)
            // The full half-bar in both orientations, from the same helper both Canvases call.
            XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: row.change.fraction, in: column, orientation: .vertical),
                           FieldMovementMarkPlan10868(fill: vertical, zeroMark: nil), words)
            XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: row.change.fraction, in: track, orientation: .horizontal),
                           FieldMovementMarkPlan10868(fill: horizontal, zeroMark: nil), words)
            // During and final are the same card.
            let final = Self.model(FieldMovementInput10868(
                scope: model.input.scope, catalogue: model.input.catalogue, displayed: model.input.displayed,
                pairs: model.input.pairs, scale: model.input.scale, phase: .final, copy: model.input.copy,
                unavailableWords: model.input.unavailableWords))
            XCTAssertEqual(final.rows, model.rows, words)
        }

        check(Self.boundaryModel(before: 0.5, beforeFigure: "50%", later: 0.65, laterFigure: "65%", movement: "+15.0 pp"),
              change: rise, fraction: 1, words: "+15.0 pp", figures: ["50%", "65%"],
              vertical: CGRect(x: 0, y: 0, width: 32, height: 70), horizontal: CGRect(x: 132, y: 0, width: 132, height: 16))
        check(Self.boundaryModel(before: 0.65, beforeFigure: "65%", later: 0.5, laterFigure: "50%", movement: "-15.0 pp"),
              change: fall, fraction: -1, words: "-15.0 pp", figures: ["65%", "50%"],
              vertical: CGRect(x: 0, y: 70, width: 32, height: 70), horizontal: CGRect(x: 0, y: 0, width: 132, height: 16))

        // Owner ticks carrying the same roundoff sit on the edges too.
        let roundoffTicks = FieldMovementScale10868(
            limit: 0.15,
            ticks: [FieldMovementTick10868(change: fall, label: "-15 pp"), FieldMovementTick10868(change: rise, label: "+15 pp")],
            words: Self.scale.words
        )
        XCTAssertEqual(Self.model(Self.input(scale: roundoffTicks)).ticks,
                       [FieldOutlookPlacedTick10868(label: "-15 pp", fraction: -1), FieldOutlookPlacedTick10868(label: "+15 pp", fraction: 1)])
    }

    func testAChangeGenuinelyPastTheLimitStaysOffScaleWithNoBar() {
        let column = CGSize(width: 32, height: 140)
        let track = CGSize(width: 264, height: 16)
        let cases: [(before: Double, beforeFigure: String, later: Double, laterFigure: String, words: String, rising: Bool)] = [
            (0.5, "50%", 0.650001, "65%", "+15.0 pp", true),
            (0.5, "50%", 0.66, "66%", "+16.0 pp", true),
            (0.650001, "65%", 0.5, "50%", "-15.0 pp", false),
            (0.66, "66%", 0.5, "50%", "-16.0 pp", false),
        ]
        for c in cases {
            let model = Self.boundaryModel(before: c.before, beforeFigure: c.beforeFigure, later: c.later, laterFigure: c.laterFigure, movement: c.words)
            let row = model.rows[0]
            XCTAssertEqual(row.change, .offScale(rising: c.rising), c.words)
            XCTAssertNil(row.change.fraction, c.words)
            XCTAssertEqual([Self.figure(row.before), Self.figure(row.later)], [c.beforeFigure, c.laterFigure], c.words)
            XCTAssertEqual(model.movementWords(row), c.words)
            XCTAssertEqual(model.stateWords(row), Self.offScale, c.words)
            XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: row.change.fraction, in: column, orientation: .vertical), .empty, c.words)
            XCTAssertEqual(FieldMovementGeometry10868.markPlan(fraction: row.change.fraction, in: track, orientation: .horizontal), .empty, c.words)
        }

        // The edge absorbs roundoff only: a few ulps of 1.0 past it is off-scale.
        XCTAssertEqual(FieldMovementGeometry10868.fraction(0.65 - 0.5, limit: 0.15), 1)
        XCTAssertEqual(FieldMovementGeometry10868.fraction(0.5 - 0.65, limit: 0.15), -1)
        XCTAssertEqual(FieldMovementGeometry10868.fraction(0.15 + Double.ulpOfOne, limit: 0.15), 1)
        XCTAssertEqual(FieldMovementGeometry10868.fraction(-(0.15 + Double.ulpOfOne), limit: 0.15), -1)
        XCTAssertNil(FieldMovementGeometry10868.fraction(0.15 + 4 * Double.ulpOfOne, limit: 0.15))
        XCTAssertNil(FieldMovementGeometry10868.fraction(-(0.15 + 4 * Double.ulpOfOne), limit: 0.15))
        XCTAssertNil(FieldMovementGeometry10868.fraction(0.150001, limit: 0.15))
        XCTAssertNil(FieldMovementGeometry10868.fraction(0.15 + 1e-12, limit: 0.15))
        XCTAssertLessThanOrEqual(FieldMovementGeometry10868.boundarySlack, 1e-15)
        // Inside the limit the fraction is unchanged.
        XCTAssertEqual(FieldMovementGeometry10868.fraction(0.15, limit: 0.15), 1)
        XCTAssertEqual(FieldMovementGeometry10868.fraction(-0.075, limit: 0.15), -0.5)
        // Invalid scales and non-finite changes stay none, slack or not.
        for limit in [0, -0.15, 1.5, Double.nan, .infinity] {
            XCTAssertNil(FieldMovementGeometry10868.fraction(0.15, limit: limit), "\(limit)")
        }
        for bad in [Double.nan, .infinity, -.infinity] {
            XCTAssertNil(FieldMovementGeometry10868.fraction(bad, limit: 0.15), "\(bad)")
        }
    }
}

// MARK: - #10868 field finish — "How the race finished"

/// The horse-racing final card — reported finish beside each runner's own
/// before-schedule win chance — on the outlook's own model.
///
/// ARCHIVED raw values come from Polymarket event 71992 (2025 Lexus Melbourne
/// Cup winner), as retained in
/// `shipping-adoption-20261027/FIELD-FINISH-CHANCES-RETAINED-CASES.json`
/// (sha256 836a6fa7…baa1) and reconciled with the reference `horseRacing.json`:
/// 25 original Yes contracts (24 named horses and Other) with their market and
/// token ids, each token's own last eligible trade strictly before the
/// SCHEDULED start 1762228800000 (3 p.m. AEDT; no actual start or finish is
/// established), its raw settled flag and one later trade, and the reported
/// places from Sporting Life: Half Yours 1, Goodie Two Shoes 2, Middle Earth 3,
/// River of Stars 4, Al Riffa 7. Goodie Two Shoes has no pre-schedule trade.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope
/// string, the displayed order and membership, every reading label, figure text
/// (prepared with the reference `probabilityLabel.ts`), PT clock line (from each
/// sample's own archived time), source word, the ordinal strings ("1st") written
/// from the archived places, the 0–50% scale and tick labels, the card copy and
/// phase, the hostile later-quote/settlement/actual-time inputs, the independent
/// No control (no No baseline is archived — it is never a complement), and
/// every withdrawn, duplicate, blank, foreign, zero, off-scale and long-name
/// case. Label widths are CONSTRUCTED measurements: native arithmetic here is
/// not a rendered fit.
final class FieldFinishComparison10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Row = (
        market: String, outcome: String, name: String, place: Int?,
        before: Double?, beforeFigure: String?, beforeClock: String?,
        settledYes: Bool, later: Double?, laterFigure: String?, laterClock: String?
    )

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:horse:melbourne-2025:finish-comparison"

    /// ARCHIVED ids, names, places, raw before and later samples and settled
    /// flags in the packet's market order; figures and PT clocks CONSTRUCTED from them.
    private static let rows: [Row] = [
        ("662191", "57986679774335388133999647094392352514476136337135153515757455827253718312981", "Al Riffa", 7, 0.1799999755, "18%", "Nov 3, 7:58:15 PM PT", false, 0.001, "0.1%", "Nov 3, 8:20:47 PM PT"),
        ("662192", "113285107801566711995009877410924953217978700575424591899117357579524379690867", "Buckaroo", nil, 0.1, "10%", "Nov 3, 6:12:39 PM PT", false, 0.006, "0.6%", "Nov 4, 12:11:13 AM PT"),
        ("662193", "111090264486914949846533632578112327337783987841051248754496969338292123536717", "Arapaho", nil, 0.0329999897, "3.3%", "Nov 3, 2:07:21 PM PT", false, 0.006, "0.6%", "Nov 4, 12:10:27 AM PT"),
        ("662194", "107546051111436135685055156636001831645754158576631464788189145509007611675320", "Vauban", nil, 0.0599999724, "6%", "Nov 3, 3:13:47 PM PT", false, 0.01, "1%", "Nov 3, 8:10:49 PM PT"),
        ("662195", "59674665675836959453882795156337277528550496355723774975072103890473235932836", "Chevalier Rose", nil, 0.027272722, "2.7%", "Nov 3, 6:13:35 PM PT", false, 0.027272722, "2.7%", "Nov 3, 6:13:35 PM PT"),
        ("662196", "25725437831074678423490397064490021440429923664509089196555853373102112388330", "Presage Nocturne", nil, 0.1799999928, "18%", "Nov 3, 7:46:51 PM PT", false, 0.001, "0.1%", "Nov 3, 8:30:47 PM PT"),
        ("662197", "74843938302865599862063666695217741490016555496773514307818592792240000928333", "Middle Earth", 3, 0.499, "49.9%", "Nov 3, 7:59:47 PM PT", false, 0.001, "0.1%", "Nov 3, 8:22:47 PM PT"),
        ("662198", "13113163042313577145708943975044192057100708280612377647951730600455871479585", "Meydaan", nil, 0.063636344, "6.4%", "Nov 3, 3:44:51 PM PT", false, 0.063636344, "6.4%", "Nov 3, 3:44:51 PM PT"),
        ("662199", "97480348126590838362617386014257588711186978838069764968566009852574664034567", "Absurde", nil, 0.072493317, "7.2%", "Nov 3, 4:21:35 PM PT", false, 0.072493317, "7.2%", "Nov 3, 4:21:35 PM PT"),
        ("662200", "375186778815734304345730069235686431240361309160446624259421274499006781275", "Flatten The Curve", nil, 0.3391304071, "33.9%", "Nov 3, 7:58:39 PM PT", false, 0.3391304071, "33.9%", "Nov 3, 7:58:39 PM PT"),
        ("662201", "10900416325570154129494151497164426775568191416541912675703544181495693346905", "Land Legend", nil, 0.02, "2%", "Nov 3, 6:13:45 PM PT", false, 0.005, "0.5%", "Nov 3, 8:07:29 PM PT"),
        ("662202", "686824202935314908280785473103008133207553129640562591947884419657216228702", "Smokin' Romans", nil, 0.0216368726, "2.2%", "Nov 3, 5:25:41 PM PT", false, 0.0013880792, "0.1%", "Nov 3, 11:52:15 PM PT"),
        ("662203", "17342647096488067499822463159574381828789083066083862701166158036721531186569", "Changingoftheguard", nil, 0.02, "2%", "Nov 3, 5:25:13 PM PT", false, 0.004, "0.4%", "Nov 3, 8:07:29 PM PT"),
        ("662204", "25817391886130435082519288683632920424871337238882052012012538546231063342274", "Half Yours", 1, 0.15, "15%", "Nov 3, 7:55:27 PM PT", true, 0.9970686952, "99.7%", "Nov 3, 10:44:19 PM PT"),
        ("662205", "15114041415477185935972663488938003841062738530739056163993776273285076108489", "More Felons", nil, nil, nil, nil, false, nil, nil, nil),
        ("662206", "12534475480858023244704199796918108714324013000764120310650980859399100692888", "Onesmoothoperator", nil, 0.04, "4%", "Nov 3, 6:12:15 PM PT", false, 0.01, "1%", "Nov 3, 8:11:31 PM PT"),
        ("662207", "96540194242414249780789780913018612473946307312007668640937940779482626465630", "Furthur", nil, 0.04, "4%", "Nov 3, 6:13:17 PM PT", false, 0.001, "0.1%", "Nov 3, 8:07:29 PM PT"),
        ("662208", "15116209406430902347185062989570467180367046547432458428494147872328545807137", "Parchment Party", nil, nil, nil, nil, false, nil, nil, nil),
        ("662209", "25547328935575042147028677226641525493494267937881748312307973650811165675769", "Athabascan", nil, 0.02, "2%", "Nov 3, 6:14:23 PM PT", false, 0.005, "0.5%", "Nov 3, 8:07:29 PM PT"),
        ("662210", "36334436956299351962097154215232967719263417388440408122368961615827627065447", "Goodie Two Shoes", 2, nil, nil, nil, false, 0.001, "0.1%", "Nov 3, 8:07:29 PM PT"),
        ("662211", "50191686820356648645687875295137083035915357751907606522771078225324583781899", "River of Stars", 4, 0.3899999774, "39%", "Nov 3, 7:59:39 PM PT", false, 0.3899999774, "39%", "Nov 3, 7:59:39 PM PT"),
        ("662212", "19447474296282586526511107609766841115319860724157142589892055882921436858148", "Royal Supremacy", nil, 0.0440674894, "4.4%", "Nov 3, 7:43:53 PM PT", false, 0.0440674894, "4.4%", "Nov 3, 7:43:53 PM PT"),
        ("662213", "81676736247955457557539194578388216667357469616432663953702769533110581233751", "Torranzino", nil, nil, nil, nil, false, 0.018, "1.8%", "Nov 3, 8:06:41 PM PT"),
        ("662214", "18675162556371127958651657711181806350152657104353033359071870912861399133444", "Valiant King", nil, 0.1099999982, "11%", "Nov 3, 7:21:53 PM PT", false, 0.001, "0.1%", "Nov 3, 8:20:47 PM PT"),
        ("662215", "103597130243570171173308783430831479350333076951839794228787635078539674108601", "Other", nil, nil, nil, nil, false, nil, nil, nil),
    ]

    /// The owner's display plan: only the reported finishes, in recorded result
    /// order, with CONSTRUCTED ordinal words — never sorted or filtered here.
    private static let reported: [(market: String, ordinal: String)] = [
        ("662204", "1st"), ("662210", "2nd"), ("662197", "3rd"), ("662211", "4th"), ("662191", "7th"),
    ]
    private static let displayedMarkets = reported.map { $0.market }

    private static let beforeLabel = "Before scheduled start"
    private static let noBefore = "Pre-race chance not recorded"
    private static let source = "Polymarket"
    private static let finishLabel = "Reported finish"
    private static let finishSource = "Sporting Life"
    private static let unavailable = "Runner unavailable in this update"
    private static let finishUnavailable = "Finish not confirmed for this runner"
    private static let chanceUnavailable = "Not shown on this scale"
    private static let offScale = "Above the 50% scale"
    private static let outside = "Your runner is not among the reported finishes shown."
    private static let openHint = "Opens this runner's recorded history"
    private static let openPrompt = "Tap a horse for its history."

    private static func row(_ market: String) -> Row {
        rows.first { $0.market == market }!
    }

    private static func ref(_ market: String, scope: String = FieldFinishComparison10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: row(market).outcome)
    }

    private static func ref(_ row: Row) -> FieldChooserOriginalRef10868 { ref(row.market) }

    private static func beforeReading(_ row: Row) -> FieldChooserReading10868 {
        guard let figure = row.beforeFigure, let clock = row.beforeClock else {
            return FieldChooserReading10868(label: beforeLabel, value: .missing(noBefore))
        }
        return FieldChooserReading10868(label: beforeLabel, value: .recorded(text: figure, detail: "\(clock) · \(source)"))
    }

    /// Every record carries its settled result; the card never reads it.
    private static func record(_ row: Row, plan: FieldChooserDisplayPlan10868? = nil) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(row), name: row.name,
            plan: plan ?? .single(beforeReading(row)),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil,
            result: FieldChooserResult10868(title: "Original Yes", words: row.settledYes ? "Resolved Yes" : "Resolved No"),
            browseStatus: "Winner prop"
        )
    }

    /// CONSTRUCTED hostile record: a later quote as a comparison plan and a
    /// preview, settlement words, and raw actual-time strings riding along.
    private static func hostile(_ row: Row) -> FieldChooserOriginal10868 {
        let later = row.laterFigure.map {
            FieldChooserReading10868(label: "After scheduled start", value: .recorded(text: $0, detail: "\(row.laterClock ?? "") · \(source)"))
        }
        return FieldChooserOriginal10868(
            ref: ref(row), name: row.name,
            plan: later.map { FieldChooserDisplayPlan10868.comparison(before: beforeReading(row), later: $0) } ?? .single(beforeReading(row)),
            preview: FieldChooserPreview10868(
                history: row.later.map { p in
                    FieldChooserHistory10868(segments: [[FieldChooserPoint10868(time: 1, probability: p)]],
                                             emphasis: FieldChooserPoint10868(time: 1, probability: p),
                                             beforeReference: row.before, gaps: [])
                },
                absence: "No history in this card"
            ),
            movement: "Actual start 3:00:42 PM AEDT · Actual finish 3:04:05 PM AEDT",
            clock: row.laterClock,
            result: FieldChooserResult10868(title: "Original Yes", words: row.settledYes ? "Settled Yes · Won" : "Settled No"),
            browseStatus: row.settledYes ? "Resolved Yes" : "Resolved No"
        )
    }

    private static let catalogue: [FieldChooserOriginal10868] = rows.map { record($0) }

    private static func chance(_ row: Row) -> FieldOutlookBeforeChance10868? {
        row.before.map { FieldOutlookBeforeChance10868(ref: ref(row), probability: $0, reading: beforeReading(row)) }
    }

    /// Every archived before chance, displayed or not.
    private static let chances: [FieldOutlookBeforeChance10868] = rows.compactMap(chance)

    private static func finish(_ market: String, _ ordinal: String) -> FieldFinishPlace10868 {
        FieldFinishPlace10868(ref: ref(market), reading: FieldChooserReading10868(label: finishLabel, value: .recorded(text: ordinal, detail: finishSource)))
    }

    /// Only the owner-reported finishes.
    private static let finishes: [FieldFinishPlace10868] = reported.map { finish($0.market, $0.ordinal) }

    private static func slot(_ market: String) -> FieldFinishSlot10868 {
        FieldFinishSlot10868(ref: ref(market), name: row(market).name)
    }

    private static let displayed: [FieldFinishSlot10868] = displayedMarkets.map(slot)

    private static let scale = FieldOutlookScale10868(
        ceiling: 0.5,
        ticks: [FieldOutlookTick10868(probability: 0, label: "0%"),
                FieldOutlookTick10868(probability: 0.25, label: "25%"),
                FieldOutlookTick10868(probability: 0.5, label: "50%")],
        words: "0–50%"
    )

    private static let copy = FieldFinishCopy10868(
        title: "How the race finished",
        context: "Before scheduled start · recorded at different times",
        scaleLabel: "Pre-race win chance",
        graphicLabel: "Reported finish and pre-race win chance for five runners",
        finishLabel: finishLabel,
        finishUnit: "finish",
        finishUnavailable: finishUnavailable,
        chanceUnavailable: chanceUnavailable,
        offScale: offScale,
        outsideDisplayed: outside,
        empty: "No finishing positions captured.",
        count: "5 reported finishes",
        openPrompt: openPrompt,
        openHint: openHint
    )

    private static func input(
        catalogue: [FieldChooserOriginal10868] = FieldFinishComparison10868Tests.catalogue,
        selected: FieldChooserSelected10868? = nil,
        displayed: [FieldFinishSlot10868] = FieldFinishComparison10868Tests.displayed,
        finishes: [FieldFinishPlace10868] = FieldFinishComparison10868Tests.finishes,
        chances: [FieldOutlookBeforeChance10868] = FieldFinishComparison10868Tests.chances,
        scale: FieldOutlookScale10868 = FieldFinishComparison10868Tests.scale,
        phase: FieldOutlookPhase10868 = .final
    ) -> FieldFinishInput10868 {
        FieldFinishInput10868(
            scope: scope,
            catalogue: catalogue,
            selected: selected,
            displayed: displayed,
            finishes: finishes,
            chances: chances,
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: unavailable
        )
    }

    private static func model(_ input: FieldFinishInput10868 = FieldFinishComparison10868Tests.input()) -> FieldFinishModel10868 {
        FieldFinishModel10868(input)
    }

    /// One original's catalogue record with its plan replaced.
    private static func catalogue(replacing market: String, plan: FieldChooserDisplayPlan10868) -> [FieldChooserOriginal10868] {
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref == ref(market) }!
        catalogue[index] = record(row(market), plan: plan)
        return catalogue
    }

    /// One original's chance replaced (or added); nil removes it.
    private static func chances(replacing market: String, with replacement: FieldOutlookBeforeChance10868?) -> [FieldOutlookBeforeChance10868] {
        var chances = Self.chances.filter { $0.ref != ref(market) }
        if let replacement { chances.append(replacement) }
        return chances
    }

    /// One original's finish replaced (or added); nil removes it.
    private static func finishes(replacing market: String, with replacement: FieldFinishPlace10868?) -> [FieldFinishPlace10868] {
        var finishes = Self.finishes
        if let index = finishes.firstIndex(where: { $0.ref == ref(market) }) { finishes.remove(at: index) }
        if let replacement { finishes.append(replacement) }
        return finishes
    }

    /// A CONSTRUCTED before reading and raw chance for one runner, tied to each other.
    private static func retied(_ market: String, probability: Double, figure: String) -> (catalogue: [FieldChooserOriginal10868], chances: [FieldOutlookBeforeChance10868]) {
        let reading = FieldChooserReading10868(label: beforeLabel, value: .recorded(text: figure, detail: "\(row(market).beforeClock ?? "Nov 3, 7:59:00 PM PT") · \(source)"))
        return (
            catalogue(replacing: market, plan: .single(reading)),
            chances(replacing: market, with: FieldOutlookBeforeChance10868(ref: ref(market), probability: probability, reading: reading))
        )
    }

    private static func raw(_ chance: FieldOutlookChance10868) -> Double? {
        if case .value(let probability, _) = chance { return probability }
        return nil
    }

    /// The strip plan the row's Canvas draws on a CONSTRUCTED 300 × 16 pt strip.
    private static let strip = CGSize(width: 300, height: 16)
    private static let inset: CGFloat = 6
    private static let diameter: CGFloat = 10

    private static func plan(_ row: FieldFinishRow10868, _ model: FieldFinishModel10868, width: CGFloat = 300) -> FieldFinishStripPlan10868? {
        FieldFinishGeometry10868.stripPlan(fraction: row.chance.fraction, ticks: model.ticks.map(\.fraction),
                                           in: CGSize(width: width, height: strip.height), inset: inset, dotDiameter: diameter)
    }

    /// Every line the view shows or speaks, from the same helpers it calls.
    private static func everyLine(_ model: FieldFinishModel10868) -> [String] {
        guard model.isShown else { return [] }
        let copy = model.input.copy
        var lines = [copy.title, copy.scaleLabel, copy.graphicLabel, copy.empty, model.input.scale.words]
        lines += [copy.context, copy.count, model.openPrompt(canOpen: true), model.notice, model.selectedOutside?.name].compactMap { $0 }
        lines += model.ticks.map(\.label)
        for row in model.rows {
            lines += [row.slot.name, model.rowSummary(row), model.hint(model.openAction(row, canOpen: true))]
            lines += [row.resolution.original?.name, model.figure(row), model.dotLabel(row), model.stateWords(row),
                      FieldFinishModel10868.ordinal(row.finish), FieldFinishModel10868.finishWords(row.finish)].compactMap { $0 }
            if FieldFinishModel10868.ordinal(row.finish) != nil { lines.append(copy.finishUnit) }
        }
        return lines
    }

    // MARK: The retained race

    func testFiveReportedFinishesKeepTheOwnersOrderOwnChancesAndAll25Originals() {
        XCTAssertEqual(Self.rows.count, 25)
        XCTAssertEqual(Set(Self.catalogue.map(\.ref)).count, 25)
        let model = Self.model()
        // Every canonical original resolves, shown or not.
        for record in Self.catalogue {
            XCTAssertEqual(model.field.resolve(record.ref), .original(record))
        }

        let rows = model.rows
        XCTAssertEqual(rows.map(\.slot.ref), Self.displayedMarkets.map { Self.ref($0) })
        XCTAssertEqual(rows.compactMap { $0.resolution.original?.name },
                       ["Half Yours", "Goodie Two Shoes", "Middle Earth", "River of Stars", "Al Riffa"])
        // The owner's ordinals, written from the archived places, tied by identity.
        XCTAssertEqual(Self.displayedMarkets.map { Self.row($0).place }, [1, 2, 3, 4, 7])
        XCTAssertEqual(rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["1st", "2nd", "3rd", "4th", "7th"])
        for row in rows {
            XCTAssertNil(FieldFinishModel10868.finishWords(row.finish))
        }

        // Each runner's own raw before chance on the one 0–50% scale; nothing summed or normalized.
        XCTAssertEqual(rows.map { Self.raw($0.chance) }, [0.15, nil, 0.499, 0.3899999774, 0.1799999755])
        let fractions: [Double?] = [0.3, nil, 0.998, 0.7799999548, 0.359999951]
        for (row, fraction) in zip(rows, fractions) {
            if let fraction {
                XCTAssertEqual(row.chance.fraction ?? -1, fraction, accuracy: 1e-12)
            } else {
                XCTAssertNil(row.chance.fraction)
            }
        }
        XCTAssertEqual(rows.map { model.dotLabel($0) }, ["15%", nil, "49.9%", "39%", "18%"])
        XCTAssertEqual(rows.map { model.figure($0) }, ["15%", Self.noBefore, "49.9%", "39%", "18%"])
        XCTAssertEqual(rows.map { model.stateWords($0) }, [nil, nil, nil, nil, nil])
        XCTAssertEqual(model.ticks, [
            FieldOutlookPlacedTick10868(label: "0%", fraction: 0),
            FieldOutlookPlacedTick10868(label: "25%", fraction: 0.5),
            FieldOutlookPlacedTick10868(label: "50%", fraction: 1),
        ])

        // The 20 unshown originals stay in the catalogue; no row is made for them.
        let unshown = Self.catalogue.filter { !Self.displayedMarkets.contains($0.ref.marketID) }
        XCTAssertEqual(unshown.count, 20)
        XCTAssertTrue(unshown.contains { $0.name == "Other" })
        XCTAssertNil(model.notice)
        XCTAssertNil(model.selectedOutside)
    }

    // MARK: Phase

    func testOnlyTheFinalShowsTheCardEvenWhenFinishesRideInThePacket() {
        let selected = FieldChooserSelected10868(ref: Self.ref("662200"), words: "Selected", unavailableWords: "Your runner is unavailable")
        for phase in [FieldOutlookPhase10868.before, .during] {
            let model = Self.model(Self.input(selected: selected, phase: phase))
            XCTAssertFalse(model.isShown, "\(phase)")
            XCTAssertEqual(model.rows, [], "\(phase)")
            XCTAssertEqual(model.ticks, [], "\(phase)")
            XCTAssertNil(model.notice, "\(phase)")
            XCTAssertNil(model.selectedOutside, "\(phase)")
            XCTAssertNil(model.outsideAction(canOpen: true), "\(phase)")
            XCTAssertNil(model.openPrompt(canOpen: true), "\(phase)")
            XCTAssertEqual(Self.everyLine(model), [], "\(phase)")
        }
        let final = Self.model(Self.input(selected: selected, phase: .final))
        XCTAssertTrue(final.isShown)
        XCTAssertEqual(final.rows.count, 5)
        XCTAssertEqual(final.notice, Self.outside)
    }

    // MARK: Hostile inputs

    func testLaterQuotesSettlementAndRawActualTimesNeverReachTheCard() {
        let plain = Self.model()
        let hostile = Self.model(Self.input(catalogue: Self.rows.map(Self.hostile)))
        XCTAssertEqual(hostile.rows.map(\.chance), plain.rows.map(\.chance))
        XCTAssertEqual(hostile.rows.map(\.finish), plain.rows.map(\.finish))
        XCTAssertEqual(hostile.rows.map { hostile.rowSummary($0) }, plain.rows.map { plain.rowSummary($0) })
        XCTAssertEqual(hostile.rows.map { hostile.figure($0) }, plain.rows.map { plain.figure($0) })

        let laterClocks = Self.displayedMarkets.compactMap { market -> String? in
            let row = Self.row(market)
            return row.laterClock == row.beforeClock ? nil : row.laterClock
        }
        XCTAssertEqual(laterClocks.count, 4)
        let leaks = ["Resolved", "Settled", "Won", "Actual start", "Actual finish", "After scheduled start", "99.7%"] + laterClocks
        for model in [plain, hostile] {
            let lines = Self.everyLine(model)
            for leak in leaks {
                XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
            }
        }

        // An association carrying the later quote is not the before reading: no dot, nothing borrowed.
        let half = Self.row("662204")
        let laterReading = FieldChooserReading10868(label: "After scheduled start", value: .recorded(text: "99.7%", detail: "\(half.laterClock!) · \(Self.source)"))
        let swapped = Self.model(Self.input(chances: Self.chances(replacing: "662204",
            with: FieldOutlookBeforeChance10868(ref: Self.ref("662204"), probability: half.later!, reading: laterReading))))
        XCTAssertEqual(swapped.rows[0].chance, .unavailable)
        XCTAssertNil(swapped.dotLabel(swapped.rows[0]))
        XCTAssertEqual(swapped.figure(swapped.rows[0]), "15%")
        XCTAssertEqual(swapped.stateWords(swapped.rows[0]), Self.chanceUnavailable)
        XCTAssertFalse(Self.everyLine(swapped).contains { $0.contains("99.7%") || $0.contains(half.laterClock!) })
        XCTAssertEqual(Array(swapped.rows.dropFirst()), Array(plain.rows.dropFirst()))
    }

    // MARK: Reported finish is the owner's

    func testAReportedFinishStaysIndependentOfResultChanceAndPosition() {
        // No owner finish for the settled-Yes original: its words, never "1st".
        let unreported = Self.model(Self.input(finishes: Self.finishes(replacing: "662204", with: nil)))
        let row = unreported.rows[0]
        XCTAssertEqual(row.finish, .unavailable(label: Self.finishLabel, words: Self.finishUnavailable))
        XCTAssertNil(FieldFinishModel10868.ordinal(row.finish))
        XCTAssertEqual(FieldFinishModel10868.finishWords(row.finish), Self.finishUnavailable)
        XCTAssertEqual(row.chance, Self.model().rows[0].chance)
        XCTAssertFalse(Self.everyLine(unreported).contains { $0.contains("1st") })

        // Results that contradict the finishes change nothing.
        var contradicted = Self.catalogue
        for (index, record) in contradicted.enumerated() {
            let words = record.ref.marketID == "662191" ? "Won" : "Resolved No"
            contradicted[index] = FieldChooserOriginal10868(
                ref: record.ref, name: record.name, plan: record.plan, preview: record.preview,
                movement: nil, clock: nil, result: FieldChooserResult10868(title: "Original Yes", words: words),
                browseStatus: record.browseStatus)
        }
        let model = Self.model(Self.input(catalogue: contradicted))
        XCTAssertEqual(model.rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["1st", "2nd", "3rd", "4th", "7th"])

        // The highest chance (Middle Earth, 49.9%) keeps its own 3rd; the owner's
        // reversed order is followed, never re-sorted by place or chance.
        let reversed = Self.model(Self.input(displayed: Array(Self.displayed.reversed())))
        XCTAssertEqual(reversed.rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["7th", "4th", "3rd", "2nd", "1st"])
        XCTAssertEqual(reversed.rows.map { Self.raw($0.chance) }, [0.1799999755, 0.3899999774, 0.499, nil, 0.15])

        // The owner's own absence words are shown as they are.
        let words = "Finishing position not captured"
        let missing = Self.model(Self.input(finishes: Self.finishes(replacing: "662210",
            with: FieldFinishPlace10868(ref: Self.ref("662210"), reading: FieldChooserReading10868(label: Self.finishLabel, value: .missing(words))))))
        XCTAssertEqual(FieldFinishModel10868.finishWords(missing.rows[1].finish), words)
        XCTAssertNil(FieldFinishModel10868.ordinal(missing.rows[1].finish))
    }

    // MARK: Missing finish, missing chance, real zero

    func testMissingFinishMissingChanceAndARealZeroStayDistinct() {
        let model = Self.model()
        // Goodie Two Shoes: a reported finish with no pre-schedule chance.
        let goodie = model.rows[1]
        XCTAssertEqual(FieldFinishModel10868.ordinal(goodie.finish), "2nd")
        XCTAssertEqual(goodie.chance, .unavailable)
        XCTAssertNil(model.dotLabel(goodie))
        XCTAssertEqual(model.figure(goodie), Self.noBefore)
        XCTAssertNil(model.stateWords(goodie))
        XCTAssertNil(Self.plan(goodie, model)?.dot)

        // A recorded figure with no association keeps its figure and finish, draws no dot.
        let untied = Self.model(Self.input(chances: Self.chances(replacing: "662211", with: nil)))
        XCTAssertEqual(untied.rows[3].chance, .unavailable)
        XCTAssertEqual(untied.figure(untied.rows[3]), "39%")
        XCTAssertEqual(untied.stateWords(untied.rows[3]), Self.chanceUnavailable)
        XCTAssertEqual(FieldFinishModel10868.ordinal(untied.rows[3].finish), "4th")

        // A real 0% is a dot at zero, labelled.
        let zero = Self.retied("662191", probability: 0, figure: "0%")
        let zeroModel = Self.model(Self.input(catalogue: zero.catalogue, chances: zero.chances))
        let riffa = zeroModel.rows[4]
        XCTAssertEqual(riffa.chance, .value(probability: 0, fraction: 0))
        XCTAssertEqual(zeroModel.dotLabel(riffa), "0%")
        XCTAssertNil(zeroModel.stateWords(riffa))
        XCTAssertEqual(Self.plan(riffa, zeroModel)?.dot, CGRect(x: 1, y: 6, width: 10, height: 10))
        XCTAssertEqual(FieldFinishModel10868.ordinal(riffa.finish), "7th")
    }

    // MARK: Identity failures

    func testUnresolvedAndRepeatedSlotsKeepTheirNamesAndNeighboursKeepTheirs() {
        let plain = Self.model().rows
        let foreign = FieldFinishSlot10868(ref: Self.ref("662210", scope: "constructed:horse:other-race"), name: "Goodie Two Shoes")
        let blank = FieldFinishSlot10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "662204", outcomeID: "  "), name: "Blank runner")
        let withdrawn = FieldFinishSlot10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "662299", outcomeID: "constructed-withdrawn"), name: "Withdrawn runner")
        let nameless = FieldFinishSlot10868(ref: withdrawn.ref, name: " ")
        let displayed = [Self.slot("662204"), foreign, blank, withdrawn, Self.slot("662197"), Self.slot("662197"), Self.slot("662211"), nameless]
        let model = Self.model(Self.input(displayed: displayed))
        let rows = model.rows
        XCTAssertEqual(rows.count, displayed.count)
        XCTAssertEqual(rows[0], plain[0])
        XCTAssertEqual(rows[6], plain[3])
        for index in [1, 2, 3, 4, 5, 7] {
            let row = rows[index]
            XCTAssertEqual(row.resolution, .unavailable, "\(index)")
            XCTAssertNil(row.finish, "\(index)")
            XCTAssertEqual(row.chance, .unavailable, "\(index)")
            XCTAssertNil(model.dotLabel(row), "\(index)")
            XCTAssertNil(model.openAction(row, canOpen: true), "\(index)")
        }
        XCTAssertEqual(model.rowSummary(rows[1]), "Goodie Two Shoes. \(Self.unavailable)")
        XCTAssertEqual(model.rowSummary(rows[4]), "Middle Earth. \(Self.unavailable)")
        XCTAssertEqual(model.rowSummary(rows[7]), Self.unavailable)

        // A record carried twice in the catalogue is no identity; neighbours keep theirs.
        let duplicated = Self.model(Self.input(catalogue: Self.catalogue + [Self.record(Self.row("662191"))]))
        XCTAssertEqual(duplicated.rows[4].resolution, .unavailable)
        XCTAssertNil(duplicated.rows[4].finish)
        XCTAssertEqual(Array(duplicated.rows.prefix(4)), Array(plain.prefix(4)))
    }

    func testDuplicateForeignBlankAndMismatchedAssociationsBorrowNothing() {
        let plain = Self.model().rows
        let unavailableFinish = FieldMovementEndpoint10868.unavailable(label: Self.finishLabel, words: Self.finishUnavailable)

        // Two identical finish associations for one original are none.
        let twice = Self.model(Self.input(finishes: Self.finishes + [Self.finish("662204", "1st")]))
        XCTAssertEqual(twice.rows[0].finish, unavailableFinish)
        XCTAssertEqual(Array(twice.rows.dropFirst()), Array(plain.dropFirst()))

        // A finish for another scope, a blank ordinal, and one for an unshown original borrow nothing.
        let foreign = FieldFinishPlace10868(ref: Self.ref("662197", scope: "constructed:horse:other-race"),
                                            reading: FieldChooserReading10868(label: Self.finishLabel, value: .recorded(text: "3rd", detail: Self.finishSource)))
        let blank = FieldFinishPlace10868(ref: Self.ref("662211"), reading: FieldChooserReading10868(label: Self.finishLabel, value: .recorded(text: " ", detail: Self.finishSource)))
        var finishes = Self.finishes(replacing: "662197", with: foreign)
        finishes = finishes.filter { $0.ref != Self.ref("662211") } + [blank, Self.finish("662200", "5th")]
        let model = Self.model(Self.input(finishes: finishes))
        XCTAssertEqual(model.rows[2].finish, unavailableFinish)
        XCTAssertEqual(model.rows[3].finish, unavailableFinish)
        XCTAssertEqual([model.rows[0], model.rows[1], model.rows[4]], [plain[0], plain[1], plain[4]])
        XCTAssertFalse(Self.everyLine(model).contains { $0.contains("5th") })

        // Duplicate, mismatched and differing chance associations draw no dot.
        let half = Self.chance(Self.row("662204"))!
        let riffaReading = Self.beforeReading(Self.row("662191"))
        var chances = Self.chances + [half]
        chances = chances.filter { $0.ref != Self.ref("662211") }
            + [FieldOutlookBeforeChance10868(ref: Self.ref("662211"), probability: 0.3899999774, reading: riffaReading)]
        chances += [FieldOutlookBeforeChance10868(ref: Self.ref("662191"), probability: 0.2, reading: riffaReading)]
        let bad = Self.model(Self.input(chances: chances))
        for index in [0, 3, 4] {
            XCTAssertEqual(bad.rows[index].chance, .unavailable, "\(index)")
            XCTAssertEqual(bad.stateWords(bad.rows[index]), Self.chanceUnavailable, "\(index)")
            XCTAssertEqual(bad.rows[index].finish, plain[index].finish, "\(index)")
        }
        XCTAssertEqual([bad.rows[1], bad.rows[2]], [plain[1], plain[2]])
    }

    // MARK: Independence and selection

    func testChancesAreNeverNormalizedComplementedOrSelectedAutomatically() {
        // A CONSTRUCTED independent No for the winner's market keeps its own value.
        let noRef = FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "662204", outcomeID: "constructed-no-token:662204")
        let noReading = FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: "40%", detail: "Nov 3, 7:55:27 PM PT · constructed"))
        let no = FieldChooserOriginal10868(
            ref: noRef, name: "Half Yours · No", plan: .single(noReading),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "Constructed control")
        let displayed = [Self.slot("662204"), FieldFinishSlot10868(ref: noRef, name: "Half Yours · No")]
        let tied = Self.model(Self.input(
            catalogue: Self.catalogue + [no], displayed: displayed,
            chances: Self.chances + [FieldOutlookBeforeChance10868(ref: noRef, probability: 0.4, reading: noReading)]))
        XCTAssertEqual(tied.rows[0].chance, Self.model().rows[0].chance)
        XCTAssertEqual(Self.raw(tied.rows[1].chance), 0.4)
        XCTAssertEqual(tied.rows[1].chance.fraction ?? -1, 0.8, accuracy: 1e-12)
        XCTAssertEqual(tied.rows[1].finish, .unavailable(label: Self.finishLabel, words: Self.finishUnavailable))
        // Without its own association the No borrows nothing from the Yes — never 85%.
        let untied = Self.model(Self.input(catalogue: Self.catalogue + [no], displayed: displayed))
        XCTAssertEqual(untied.rows[1].chance, .unavailable)
        XCTAssertEqual(untied.figure(untied.rows[1]), "40%")
        XCTAssertFalse(Self.everyLine(untied).contains { $0.contains("85%") })

        // A selection outside the rows keeps its identity and notice; no row is selected.
        let flatten = FieldChooserSelected10868(ref: Self.ref("662200"), words: "Selected", unavailableWords: "Your runner is unavailable")
        let outside = Self.model(Self.input(selected: flatten))
        XCTAssertEqual(outside.notice, Self.outside)
        XCTAssertEqual(outside.selectedOutside?.ref, Self.ref("662200"))
        XCTAssertEqual(outside.outsideAction(canOpen: true), Self.ref("662200"))
        XCTAssertNil(outside.outsideAction(canOpen: false))
        XCTAssertFalse(outside.rows.contains { outside.isSelected($0) })

        // A selected row carries the owner's words first.
        let riffa = FieldChooserSelected10868(ref: Self.ref("662191"), words: "Selected", unavailableWords: "Your runner is unavailable")
        let inside = Self.model(Self.input(selected: riffa))
        XCTAssertEqual(inside.rows.map { inside.isSelected($0) }, [false, false, false, false, true])
        XCTAssertNil(inside.notice)
        XCTAssertNil(inside.selectedOutside)
        XCTAssertEqual(inside.rowSummary(inside.rows[4]),
                       "Selected. Reported finish: 7th, Sporting Life. Before scheduled start: 18%, Nov 3, 7:58:15 PM PT · Polymarket")

        // An unresolved selection shows its words and selects nobody.
        let gone = FieldChooserSelected10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "662299", outcomeID: "constructed-withdrawn"),
                                             words: "Selected", unavailableWords: "Your runner is unavailable")
        let unresolved = Self.model(Self.input(selected: gone))
        XCTAssertEqual(unresolved.notice, "Your runner is unavailable")
        XCTAssertNil(unresolved.selectedOutside)
        XCTAssertFalse(unresolved.rows.contains { unresolved.isSelected($0) })
    }

    // MARK: Open

    func testOpenHandsBackTheExactOriginalAndNoCallbackIsStatic() {
        let model = Self.model()
        XCTAssertEqual(model.rows.compactMap { model.openAction($0, canOpen: true) }, Self.displayed.map(\.ref))
        for row in model.rows {
            XCTAssertEqual(model.hint(model.openAction(row, canOpen: true)), Self.openHint)
            XCTAssertNil(model.openAction(row, canOpen: false))
            XCTAssertEqual(model.hint(model.openAction(row, canOpen: false)), "")
        }
        XCTAssertEqual(model.openPrompt(canOpen: true), Self.openPrompt)
        XCTAssertNil(model.openPrompt(canOpen: false))

        // Nothing opens when no row resolves, so no prompt either.
        let none = Self.model(Self.input(displayed: [FieldFinishSlot10868(ref: Self.ref("662204", scope: "elsewhere"), name: "Half Yours")]))
        XCTAssertNil(none.openPrompt(canOpen: true))
        XCTAssertNil(none.openAction(none.rows[0], canOpen: true))
        XCTAssertEqual(none.hint(nil), "")
    }

    // MARK: One shared scale

    func testOneSharedScalePlacesEveryDotExactlyWithoutClamping() {
        let model = Self.model()
        XCTAssertEqual(FieldFinishGeometry10868.x(of: 0, width: 300, inset: 6), 6)
        XCTAssertEqual(FieldFinishGeometry10868.x(of: 1, width: 300, inset: 6), 294)
        for row in model.rows {
            guard let fraction = row.chance.fraction else {
                XCTAssertNil(Self.plan(row, model)?.dot, row.slot.name)
                continue
            }
            let plan = Self.plan(row, model)
            let x = FieldFinishGeometry10868.x(of: fraction, width: 300, inset: 6)!
            XCTAssertEqual(plan?.dot?.midX ?? -1, x, accuracy: 1e-9, row.slot.name)
            XCTAssertEqual(plan?.dot?.midY ?? -1, 11, accuracy: 1e-9, row.slot.name)
            XCTAssertEqual(plan?.dot?.width, 10, row.slot.name)
            XCTAssertEqual(plan?.baselineY, 11)
            XCTAssertEqual(plan?.tickXs, [6, 6, 150, 294])
        }
        XCTAssertEqual(Self.plan(model.rows[0], model)?.dot?.midX ?? -1, 92.4, accuracy: 1e-9)
        XCTAssertEqual(Self.plan(model.rows[2], model)?.dot?.midX ?? -1, 6 + 288 * 0.998, accuracy: 1e-9)

        // Exactly the ceiling is a whole dot at the end.
        let atCeiling = Self.retied("662197", probability: 0.5, figure: "50%")
        let full = Self.model(Self.input(catalogue: atCeiling.catalogue, chances: atCeiling.chances))
        XCTAssertEqual(full.rows[2].chance, .value(probability: 0.5, fraction: 1))
        XCTAssertEqual(Self.plan(full.rows[2], full)?.dot, CGRect(x: 289, y: 6, width: 10, height: 10))

        // Above the ceiling: the runner's own figure and words, a strip with no dot.
        let above = Self.retied("662197", probability: 0.52, figure: "52%")
        let off = Self.model(Self.input(catalogue: above.catalogue, chances: above.chances))
        XCTAssertEqual(off.rows[2].chance, .offScale)
        XCTAssertNil(off.dotLabel(off.rows[2]))
        XCTAssertEqual(off.figure(off.rows[2]), "52%")
        XCTAssertEqual(off.stateWords(off.rows[2]), Self.offScale)
        XCTAssertNotNil(Self.plan(off.rows[2], off))
        XCTAssertNil(Self.plan(off.rows[2], off)?.dot)

        // Invalid raw values draw nothing.
        for bad in [1.2, -0.1, Double.nan, .infinity] {
            let tied = Self.retied("662197", probability: bad, figure: "49.9%")
            let invalid = Self.model(Self.input(catalogue: tied.catalogue, chances: tied.chances))
            XCTAssertEqual(invalid.rows[2].chance, .unavailable, "\(bad)")
            XCTAssertEqual(invalid.stateWords(invalid.rows[2]), Self.chanceUnavailable, "\(bad)")
        }
        // An invalid scale places no dot and no tick.
        for bound in [0, -0.5, 1.5, Double.nan] {
            let invalid = Self.model(Self.input(scale: FieldOutlookScale10868(ceiling: bound, ticks: Self.scale.ticks, words: "0–50%")))
            XCTAssertTrue(invalid.rows.allSatisfy { $0.chance == .unavailable }, "\(bound)")
            XCTAssertEqual(invalid.ticks, [], "\(bound)")
        }
        // Positions are never clamped; sizes that cannot be drawn draw nothing.
        for fraction in [1.2, -0.1, Double.nan] {
            XCTAssertNil(FieldFinishGeometry10868.x(of: fraction, width: 300, inset: 6), "\(fraction)")
        }
        for size in [CGSize(width: 12, height: 16), CGSize(width: CGFloat.nan, height: 16), CGSize(width: 300, height: 9)] {
            XCTAssertNil(FieldFinishGeometry10868.stripPlan(fraction: 0.3, ticks: [], in: size, inset: 6, dotDiameter: 10), "\(size)")
        }
    }

    // MARK: Measured labels and narrow / AX plans

    func testMeasuredFiguresStayInsideTheStripWithoutMovingTheDot() {
        XCTAssertEqual(FieldFinishGeometry10868.labelOrigin(markX: 92.4, labelWidth: 50, width: 300) ?? -1, 67.4, accuracy: 1e-9)
        XCTAssertEqual(FieldFinishGeometry10868.labelOrigin(markX: 6, labelWidth: 50, width: 300), 0)
        XCTAssertEqual(FieldFinishGeometry10868.labelOrigin(markX: 294, labelWidth: 50, width: 300), 250)
        XCTAssertEqual(FieldFinishGeometry10868.labelOrigin(markX: 294, labelWidth: 300, width: 300), 0)
        // Wider than the strip: its own line, whole.
        XCTAssertNil(FieldFinishGeometry10868.labelOrigin(markX: 150, labelWidth: 301, width: 300))

        // Every displayed dot at CONSTRUCTED 320/375/393/wide strip widths and
        // standard/AX figure widths: the figure stays inside and over its dot,
        // and the dot is where the shared scale puts it.
        let model = Self.model()
        for width: CGFloat in [288, 343, 361, 600] {
            for labelWidth: CGFloat in [44, 96] {
                for row in model.rows {
                    guard let fraction = row.chance.fraction,
                          let markX = FieldFinishGeometry10868.x(of: fraction, width: width, inset: 6),
                          let origin = FieldFinishGeometry10868.labelOrigin(markX: markX, labelWidth: labelWidth, width: width)
                    else { continue }
                    let label = "\(row.slot.name) @ \(width)/\(labelWidth)"
                    XCTAssertGreaterThanOrEqual(origin, 0, label)
                    XCTAssertLessThanOrEqual(origin + labelWidth, width, label)
                    XCTAssertLessThanOrEqual(origin, markX, label)
                    XCTAssertGreaterThanOrEqual(origin + labelWidth, markX, label)
                    XCTAssertEqual(Self.plan(row, model, width: width)?.dot?.midX ?? -1, markX, accuracy: 1e-9, label)
                }
            }
        }
        XCTAssertTrue(FieldFinishGeometry10868.stacksFinishUnit(accessibilitySize: true))
        XCTAssertFalse(FieldFinishGeometry10868.stacksFinishUnit(accessibilitySize: false))
    }

    // MARK: Spoken text

    func testSpokenRowsKeepWholeNamesOrdinalsFiguresAndOwnClocks() {
        let model = Self.model()
        XCTAssertEqual(model.rowSummary(model.rows[0]),
                       "Reported finish: 1st, Sporting Life. Before scheduled start: 15%, Nov 3, 7:55:27 PM PT · Polymarket")
        XCTAssertEqual(model.rowSummary(model.rows[1]),
                       "Reported finish: 2nd, Sporting Life. Before scheduled start: \(Self.noBefore)")
        XCTAssertEqual(model.rowSummary(model.rows[2]),
                       "Reported finish: 3rd, Sporting Life. Before scheduled start: 49.9%, Nov 3, 7:59:47 PM PT · Polymarket")

        let unreported = Self.model(Self.input(finishes: Self.finishes(replacing: "662211", with: nil)))
        XCTAssertEqual(unreported.rowSummary(unreported.rows[3]),
                       "Reported finish: \(Self.finishUnavailable). Before scheduled start: 39%, Nov 3, 7:59:39 PM PT · Polymarket")

        let above = Self.retied("662197", probability: 0.52, figure: "52%")
        let off = Self.model(Self.input(catalogue: above.catalogue, chances: above.chances))
        XCTAssertEqual(off.rowSummary(off.rows[2]),
                       "Reported finish: 3rd, Sporting Life. Before scheduled start: 52%, Nov 3, 7:59:47 PM PT · Polymarket. \(Self.offScale)")

        // A long full name is kept whole — in the row and in an unavailable slot.
        let long = "Will Goodie Two Shoes win the 2025 Lexus Melbourne Cup?"
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref == Self.ref("662210") }!
        let goodie = catalogue[index]
        catalogue[index] = FieldChooserOriginal10868(ref: goodie.ref, name: long, plan: goodie.plan, preview: goodie.preview,
                                                     movement: nil, clock: nil, result: goodie.result, browseStatus: goodie.browseStatus)
        let whole = Self.model(Self.input(catalogue: catalogue))
        XCTAssertEqual(whole.rows[1].resolution.original?.name, long)
        let slot = Self.model(Self.input(displayed: [FieldFinishSlot10868(ref: Self.ref("662210", scope: "elsewhere"), name: long)]))
        XCTAssertEqual(slot.rowSummary(slot.rows[0]), "\(long). \(Self.unavailable)")
    }
}

// MARK: - #10868 field chase — "Leclerc's chase"

/// The racing-live chase card — a reported gap shrinking beside the
/// challenger's own pre-race and recorded win chances — on the movement card's
/// own model.
///
/// ARCHIVED raw values come from the 2026 Singapore Grand Prix, as retained in
/// `shipping-adoption-20261027/RACING-CHASE-RETAINED-CASES.json`
/// (sha256 088993dc…a1d4) and reconciled with the reference
/// `racingLiveCapture.json` / `racingEvidence.json` trade rules: Polymarket
/// winner contracts for Charles Leclerc (market 5229402), Max Verstappen
/// (5229406) and Lewis Hamilton (5229411) with their Yes token ids; Leclerc's
/// pre-race trade 0.1399999999 at 2026-10-11T11:59:46Z (start 12:00:00Z); the
/// three timestamped lap reports — lap 46 gap 15 s reported 13:20:49Z, lap 52
/// 9.1 s at 13:30:26Z, lap 58 9 s at 13:40:53Z — and Leclerc's own last trade
/// before each report: 0.0829999984 at 13:20:28Z, 0.1612595359 at 13:30:12Z,
/// 0.001 at 13:40:33Z. A report's publication time is not a lap crossing; the
/// trade and report clocks stay separate. The neighbours' pre-race trades are
/// Verstappen 0.6499999935 at 11:59:31Z and Hamilton 0.16 at 11:59:19Z.
/// Leclerc's archived final (2nd, contract lost) is used only as a hostile
/// control the live card must never show.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope
/// string, every label, figure text (prepared with the reference
/// `probabilityLabel.ts` and its `toFixed(1)` gap figures), PT clock line (from
/// each sample's own archived time), source word, the headline and eyebrow
/// words, the 46–58 lap and 0–20 s axis with tick labels, the run grouping and
/// highlighted report per moment, the card copy and phase, the hostile
/// later/final inputs, the No control, and every withdrawn, duplicate, blank,
/// foreign, zero, invalid, out-of-range and long-name case. Label sizes are
/// CONSTRUCTED measurements: native arithmetic here is not a rendered fit.
final class FieldChaseCard10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Stage = (
        id: String, lap: Double, seconds: Double, gapFigure: String, reportClock: String,
        recorded: Double, recordedFigure: String, tradeClock: String, headline: String, eyebrow: String
    )

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:f1:singapore-2026:chase"

    /// ARCHIVED ids and names.
    private static let leclerc = (market: "5229402", outcome: "92443082174901362958213182894863948289679800011664028904195269564952495193793", name: "Charles Leclerc")
    private static let verstappen = (market: "5229406", outcome: "105026689771335810478914327541724319323338915766526076386906176141135574302746", name: "Max Verstappen")
    private static let hamilton = (market: "5229411", outcome: "9518453683994039663103190001640433279731056992400699084747973794695685716810", name: "Lewis Hamilton")

    /// ARCHIVED report ids, laps, gaps, report times and Leclerc's own last trade
    /// before each report; figures, PT clocks and owner words CONSTRUCTED from them.
    private static let stages: [Stage] = [
        ("block-6acb8cf28f08ac9a3440593b", 46, 15, "15.0", "Oct 11, 6:20:49 AM PT", 0.0829999984, "8.3%", "Oct 11, 6:20:28 AM PT", "15 seconds behind", "Leclerc chasing Verstappen"),
        ("block-6acb8f1e8f084a13d13c940d", 52, 9.1, "9.1", "Oct 11, 6:30:26 AM PT", 0.1612595359, "16.1%", "Oct 11, 6:30:12 AM PT", "5.9 seconds closer", "Leclerc chasing Verstappen · since lap 46"),
        ("block-6acb91b58f084a13d13c9417", 58, 9, "9.0", "Oct 11, 6:40:53 AM PT", 0.001, "0.1%", "Oct 11, 6:40:33 AM PT", "6.0 seconds closer", "Leclerc chasing Verstappen · since lap 46"),
    ]

    /// ARCHIVED pre-race trade, figure and PT clock CONSTRUCTED from it.
    private static let before = (p: 0.1399999999, figure: "14%", clock: "Oct 11, 4:59:46 AM PT")

    private static let tradeSource = "Polymarket trade"
    private static let reportSource = "Guardian lap report"
    private static let beforeLabel = "Pre-race win"
    private static let recordedLabel = "Recorded win"
    private static let beforeUnavailable = "Not recorded"
    private static let recordedUnavailable = "No recent probability"
    private static let gapUnavailable = "Gap not reported in this update"
    private static let pointUnavailable = "Not shown on this scale"
    private static let unavailable = "Driver unavailable in this update"
    private static let openHint = "Opens this driver's recorded win history"

    private static func ref(_ market: String, _ outcome: String, scope: String = FieldChaseCard10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: outcome)
    }

    private static let leclercRef = ref(leclerc.market, leclerc.outcome)

    private static let beforeReading = FieldChooserReading10868(
        label: beforeLabel, value: .recorded(text: before.figure, detail: "\(before.clock) · \(tradeSource)"))

    private static func recordedReading(_ stage: Stage) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: recordedLabel, value: .recorded(text: stage.recordedFigure, detail: "\(stage.tradeClock) · \(tradeSource)"))
    }

    /// Leclerc's record for one moment: its own pre-race and recorded readings.
    private static func leclercRecord(_ stage: Stage, plan: FieldChooserDisplayPlan10868? = nil, name: String = FieldChaseCard10868Tests.leclerc.name) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: leclercRef, name: name,
            plan: plan ?? .comparison(before: beforeReading, later: recordedReading(stage)),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "Race winner"
        )
    }

    /// A neighbour with its own ARCHIVED pre-race trade only.
    private static func neighbour(_ market: String, _ outcome: String, _ name: String, _ figure: String, _ clock: String) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(market, outcome), name: name,
            plan: .single(FieldChooserReading10868(label: beforeLabel, value: .recorded(text: figure, detail: "\(clock) · \(tradeSource)"))),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "Race winner"
        )
    }

    private static let neighbours = [
        neighbour(verstappen.market, verstappen.outcome, verstappen.name, "65%", "Oct 11, 4:59:31 AM PT"),
        neighbour(hamilton.market, hamilton.outcome, hamilton.name, "16%", "Oct 11, 4:59:19 AM PT"),
    ]

    private static func catalogue(_ stage: Stage) -> [FieldChooserOriginal10868] {
        [neighbours[0], leclercRecord(stage), neighbours[1]]
    }

    private static func pair(_ stage: Stage, recorded: Double? = nil, ref: FieldChooserOriginalRef10868 = FieldChaseCard10868Tests.leclercRef) -> FieldMovementPair10868 {
        FieldMovementPair10868(
            ref: ref,
            before: FieldMovementObservation10868(probability: before.p, reading: beforeReading),
            later: FieldMovementObservation10868(probability: recorded ?? stage.recorded, reading: recordedReading(stage)),
            movement: "constructed movement words never shown", observation: "constructed-observation-key"
        )
    }

    private static func report(_ stage: Stage) -> FieldChaseReport10868 {
        FieldChaseReport10868(id: stage.id, lap: stage.lap, seconds: stage.seconds, reading: FieldChooserReading10868(
            label: "Lap \(Int(stage.lap))", value: .recorded(text: "\(stage.gapFigure) sec", detail: "Reported \(stage.reportClock) · \(reportSource)")))
    }

    private static let axis = FieldChaseAxis10868(
        lapLower: 46, lapUpper: 58,
        lapTicks: [FieldChaseTick10868(value: 46, label: "L46"), FieldChaseTick10868(value: 52, label: "L52"), FieldChaseTick10868(value: 58, label: "L58")],
        secondsLower: 0, secondsUpper: 20,
        secondsTicks: [FieldChaseTick10868(value: 0, label: "0s"), FieldChaseTick10868(value: 10, label: "10s"), FieldChaseTick10868(value: 20, label: "20s")]
    )

    /// The owner's gap story at one moment: only reports up to that moment.
    private static func gap(_ index: Int, runs: [[FieldChaseReport10868]]? = nil, highlighted: String? = nil, axis: FieldChaseAxis10868 = FieldChaseCard10868Tests.axis) -> FieldChaseGap10868 {
        let stage = stages[index]
        return FieldChaseGap10868(
            headline: stage.headline,
            current: FieldChooserReading10868(label: "Reported gap · lap \(Int(stage.lap))",
                                              value: .recorded(text: stage.gapFigure, detail: "Reported \(stage.reportClock) · \(reportSource)")),
            runs: runs ?? [stages[0...index].map { Self.report($0) }],
            highlighted: highlighted ?? stage.id,
            axis: axis
        )
    }

    private static func copy(_ index: Int) -> FieldChaseCopy10868 {
        FieldChaseCopy10868(
            eyebrow: stages[index].eyebrow,
            currentUnit: "sec",
            gapUnavailable: gapUnavailable,
            graphicLabel: "Reported gap behind Verstappen, seconds, zero to twenty. Smaller means closer.",
            caption: "Gap behind the leader · smaller is closer. Only reported laps are shown.",
            pointUnavailable: pointUnavailable,
            highlightWords: "This report",
            chancesLabel: "Pre-race and recorded win chances",
            beforeLabel: beforeLabel,
            recordedLabel: recordedLabel,
            beforeUnavailable: beforeUnavailable,
            recordedUnavailable: recordedUnavailable,
            openLabel: "Leclerc's win history",
            openHint: openHint
        )
    }

    private static func input(
        _ index: Int = 1,
        catalogue: [FieldChooserOriginal10868]? = nil,
        challenger: FieldFinishSlot10868? = nil,
        pairs: [FieldMovementPair10868]? = nil,
        gap: FieldChaseGap10868? = nil,
        withoutGap: Bool = false,
        phase: FieldOutlookPhase10868 = .during
    ) -> FieldChaseInput10868 {
        let stage = stages[index]
        return FieldChaseInput10868(
            scope: scope,
            catalogue: catalogue ?? Self.catalogue(stage),
            challenger: challenger ?? FieldFinishSlot10868(ref: leclercRef, name: leclerc.name),
            pairs: pairs ?? [pair(stage)],
            gap: withoutGap ? nil : (gap ?? Self.gap(index)),
            phase: phase,
            copy: copy(index),
            unavailableWords: unavailable
        )
    }

    private static func model(_ input: FieldChaseInput10868 = FieldChaseCard10868Tests.input()) -> FieldChaseModel10868 {
        FieldChaseModel10868(input)
    }

    /// Every line the view shows or speaks, from the same helpers it calls.
    private static func everyLine(_ model: FieldChaseModel10868) -> [String] {
        guard model.isShown else { return [] }
        let copy = model.input.copy
        var lines = [model.eyebrow, model.headline, model.gapWords, model.gapSummary, model.challenger?.name,
                     model.unavailable.flatMap { $0.name }, model.unavailable.map { $0.words }, model.openSpokenLabel].compactMap { $0 }
        if let current = model.current {
            lines.append(current.label)
            switch current.value {
            case .recorded(let text, let detail): lines += [text, copy.currentUnit, detail]
            case .missing(let words): lines.append(words)
            }
        }
        for endpoint in model.readouts {
            lines += [FieldChaseModel10868.label(endpoint), FieldChaseModel10868.figure(endpoint),
                      FieldChaseModel10868.words(endpoint), FieldChaseModel10868.detail(endpoint)].compactMap { $0 }
        }
        lines.append(model.chanceSummary)
        if model.showsPlot {
            lines += [copy.graphicLabel, model.graphicSummary] + model.lapTicks.map(\.label) + model.secondsTicks.map(\.label)
            lines += [copy.caption].compactMap { $0 }
        }
        let opening = model.openAction(canOpen: true)
        if opening != nil { lines += [copy.openLabel, model.hint(opening)] }
        return lines
    }

    private static func raw(_ model: FieldChaseModel10868) -> [Double?] {
        let pair = model.movement.pair(for: leclercRef)
        return [pair?.before?.probability, pair?.later?.probability]
    }

    /// The plan the plot Canvas draws on a CONSTRUCTED 300 × 170 pt canvas with
    /// CONSTRUCTED label sizes (16 × 13 seconds labels, 22 × 13 lap labels).
    private static func plan(_ model: FieldChaseModel10868, size: CGSize = CGSize(width: 300, height: 170),
                             seconds: CGSize = CGSize(width: 16, height: 13), laps: CGSize = CGSize(width: 22, height: 13)) -> FieldChasePlotPlan10868? {
        FieldChaseGeometry10868.plotPlan(
            size: size, runs: model.placedRuns, highlighted: model.highlightedID,
            secondsTicks: model.secondsTicks.map { FieldChaseMeasuredTick10868(unit: $0.unit, size: seconds) },
            lapTicks: model.lapTicks.map { FieldChaseMeasuredTick10868(unit: $0.unit, size: laps) },
            dotDiameter: 10, spacing: 6)
    }

    // MARK: The three retained reports

    func testThreeRealReportsKeepTheirOwnGapsAndRecordedChancesOnSeparateClocks() {
        let recordedRaw: [Double] = [0.0829999984, 0.1612595359, 0.001]
        let figures = ["8.3%", "16.1%", "0.1%"]
        let tradeClocks = ["Oct 11, 6:20:28 AM PT", "Oct 11, 6:30:12 AM PT", "Oct 11, 6:40:33 AM PT"]
        let reportClocks = ["Oct 11, 6:20:49 AM PT", "Oct 11, 6:30:26 AM PT", "Oct 11, 6:40:53 AM PT"]
        let headlines = ["15 seconds behind", "5.9 seconds closer", "6.0 seconds closer"]
        let gaps = ["15.0", "9.1", "9.0"]
        for index in 0..<3 {
            let label = "lap \(Int(Self.stages[index].lap))"
            let model = Self.model(Self.input(index))
            XCTAssertTrue(model.isShown, label)
            XCTAssertEqual(model.challenger?.ref, Self.leclercRef, label)
            XCTAssertEqual(Self.raw(model), [Self.before.p, recordedRaw[index]], label)

            // Both own chances at the same rank, each with its own trade clock.
            let readouts = model.readouts
            XCTAssertEqual(readouts.map(FieldChaseModel10868.label), [Self.beforeLabel, Self.recordedLabel], label)
            XCTAssertEqual(readouts.map(FieldChaseModel10868.figure), ["14%", figures[index]], label)
            XCTAssertEqual(readouts.map(FieldChaseModel10868.words), [nil, nil], label)
            XCTAssertEqual(readouts.map(FieldChaseModel10868.detail),
                           ["Oct 11, 4:59:46 AM PT · Polymarket trade", "\(tradeClocks[index]) · Polymarket trade"], label)

            // The report's own clock is the gap's; never the trade's, and the trade's is never the report's.
            XCTAssertEqual(model.headline, headlines[index], label)
            XCTAssertEqual(model.current?.value, .recorded(text: gaps[index], detail: "Reported \(reportClocks[index]) · Guardian lap report"), label)
            XCTAssertFalse(readouts.compactMap(FieldChaseModel10868.detail).contains { $0.contains(reportClocks[index]) }, label)
            XCTAssertFalse((model.gapSummary ?? "").contains(tradeClocks[index]), label)
            XCTAssertNotEqual(tradeClocks[index], reportClocks[index], label)

            // Exactly the reports up to this moment, highlighted at this one.
            XCTAssertEqual(model.reports.map(\.id), Self.stages[0...index].map { $0.id }, label)
            XCTAssertEqual(model.highlightedID, Self.stages[index].id, label)
            XCTAssertEqual(model.placedRuns.map { $0.map(\.id) }, [Self.stages[0...index].map { $0.id }], label)
        }

        // The chance rises then collapses while the reported gap only narrows:
        // nothing ties one to the other.
        XCTAssertEqual(Self.stages.map { $0.seconds }, [15, 9.1, 9])
        XCTAssertLessThan(recordedRaw[0], recordedRaw[1])
        XCTAssertGreaterThan(recordedRaw[1], recordedRaw[2])
    }

    // MARK: No later report, settlement or final in an earlier moment

    func testAnEarlierMomentShowsNoLaterReportSettledOrFinalData() {
        // CONSTRUCTED hostile record: the archived final (2nd, contract lost),
        // later quotes as preview and movement words, and the last clock.
        let lastTrade = Self.stages[2]
        let hostile = FieldChooserOriginal10868(
            ref: Self.leclercRef, name: Self.leclerc.name,
            plan: .comparison(before: Self.beforeReading, later: Self.recordedReading(Self.stages[0])),
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(segments: [[FieldChooserPoint10868(time: 1, probability: 0.1612595359),
                                                              FieldChooserPoint10868(time: 2, probability: 0.001)]],
                                                  emphasis: FieldChooserPoint10868(time: 2, probability: 0.001), beforeReference: 0.1399999999, gaps: []),
                absence: "No history in this card"),
            movement: "Down 13.9 pp vs pre-race",
            clock: lastTrade.tradeClock,
            result: FieldChooserResult10868(title: "Final classification", words: "2nd · Contract lost"),
            browseStatus: "Finished 2nd"
        )
        let lap46 = Self.model(Self.input(0, catalogue: [Self.neighbours[0], hostile, Self.neighbours[1]]))
        XCTAssertEqual(lap46.readouts.map(FieldChaseModel10868.figure), ["14%", "8.3%"])
        XCTAssertEqual(lap46.reports.count, 1)
        let lines = Self.everyLine(lap46)
        let leaks = ["Lap 52", "Lap 58", "9.1", "9.0 sec", "16.1%", "0.1%", "6:30", "6:40", "seconds closer", "since lap",
                     "2nd", "lost", "Final", "13.9", "Won"]
        for leak in leaks {
            XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
        }
        // A lone report is a point, never a line.
        let plan = Self.plan(lap46)
        XCTAssertEqual(plan?.dots.count, 1)
        XCTAssertEqual(plan?.lines, [])
        XCTAssertNotNil(plan?.highlight)
    }

    // MARK: Phase

    func testBeforeAndFinalShowNoChaseCardEvenWithThePayloadRidingAlong() {
        for phase in [FieldOutlookPhase10868.before, .final] {
            let model = Self.model(Self.input(2, phase: phase))
            XCTAssertFalse(model.isShown, "\(phase)")
            XCTAssertNil(model.row, "\(phase)")
            XCTAssertNil(model.challenger, "\(phase)")
            XCTAssertNil(model.unavailable.map { $0.words }, "\(phase)")
            XCTAssertEqual(model.readouts, [], "\(phase)")
            XCTAssertNil(model.gap, "\(phase)")
            XCTAssertNil(model.eyebrow, "\(phase)")
            XCTAssertNil(model.headline, "\(phase)")
            XCTAssertNil(model.current, "\(phase)")
            XCTAssertNil(model.gapWords, "\(phase)")
            XCTAssertFalse(model.showsPlot, "\(phase)")
            XCTAssertEqual(model.placedRuns, [], "\(phase)")
            XCTAssertEqual(model.lapTicks, [], "\(phase)")
            XCTAssertNil(model.openAction(canOpen: true), "\(phase)")
            XCTAssertEqual(Self.everyLine(model), [], "\(phase)")
        }
        // Without a gap story the before/final card still says nothing.
        XCTAssertNil(Self.model(Self.input(withoutGap: true, phase: .final)).gapWords)
        XCTAssertTrue(Self.model(Self.input(2)).isShown)
    }

    // MARK: Withheld recorded chance

    func testAWithheldRecordedChanceSaysNoRecentProbabilityAndKeepsPreRaceAndTheGap() {
        let plain = Self.model()
        let stage = Self.stages[1]
        let keptBefore = FieldMovementEndpoint10868.reading(Self.beforeReading)
        let withheld = FieldMovementEndpoint10868.unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)

        // The owner's own absence words, as they are.
        let missing = FieldChooserReading10868(label: Self.recordedLabel, value: .missing(Self.recordedUnavailable))
        let owner = Self.model(Self.input(
            catalogue: [Self.neighbours[0], Self.leclercRecord(stage, plan: .comparison(before: Self.beforeReading, later: missing)), Self.neighbours[1]],
            pairs: [FieldMovementPair10868(ref: Self.leclercRef, before: Self.pair(stage).before, later: nil, movement: nil, observation: nil)]))
        XCTAssertEqual(owner.readouts, [keptBefore, .reading(missing)])

        // A single plan, an untied later association, or an invalid raw value: the copy's words, no number.
        let single = Self.model(Self.input(catalogue: [Self.neighbours[0], Self.leclercRecord(stage, plan: .single(Self.beforeReading)), Self.neighbours[1]]))
        let untied = Self.model(Self.input(pairs: [FieldMovementPair10868(
            ref: Self.leclercRef, before: Self.pair(stage).before,
            later: FieldMovementObservation10868(probability: Self.stages[0].recorded, reading: Self.recordedReading(Self.stages[0])),
            movement: nil, observation: nil)]))
        var cases = [single, untied]
        for bad in [1.2, -0.1, Double.nan, .infinity] {
            cases.append(Self.model(Self.input(pairs: [Self.pair(stage, recorded: bad)])))
        }
        for (index, model) in cases.enumerated() {
            XCTAssertEqual(model.readouts, [keptBefore, withheld], "\(index)")
            XCTAssertEqual(model.readouts.map(FieldChaseModel10868.figure), ["14%", nil], "\(index)")
            XCTAssertEqual(FieldChaseModel10868.words(model.readouts[1]), Self.recordedUnavailable, "\(index)")
            XCTAssertNil(FieldChaseModel10868.detail(model.readouts[1]), "\(index)")
            // The actual gap stays independently visible.
            XCTAssertEqual(model.headline, plain.headline, "\(index)")
            XCTAssertEqual(model.current, plain.current, "\(index)")
            XCTAssertEqual(model.placedRuns, plain.placedRuns, "\(index)")
            XCTAssertFalse(Self.everyLine(model).contains { $0.contains("16.1%") || $0.contains("6:30:12") }, "\(index)")
        }
        XCTAssertEqual(Self.model().readouts.map(FieldChaseModel10868.figure), ["14%", "16.1%"])
    }

    // MARK: Missing gap

    func testAMissingGapKeepsBothOwnChancesAndTheOwnersAbsenceWords() {
        let plain = Self.model()
        let none = Self.model(Self.input(withoutGap: true))
        XCTAssertEqual(none.gapWords, Self.gapUnavailable)
        XCTAssertEqual(none.gapSummary, Self.gapUnavailable)
        XCTAssertNil(none.headline)
        XCTAssertNil(none.current)
        XCTAssertFalse(none.showsPlot)
        XCTAssertEqual(none.placedRuns, [])
        XCTAssertEqual(none.graphicSummary, "")
        XCTAssertEqual(none.readouts, plain.readouts)
        XCTAssertEqual(none.chanceSummary, plain.chanceSummary)
        XCTAssertEqual(none.openAction(canOpen: true), Self.leclercRef)
        XCTAssertFalse(Self.everyLine(none).contains { $0.contains("seconds closer") || $0.contains(" sec") })

        // The latest report without a gap keeps the owner's words; earlier reports still draw.
        let words = "Gap not in this report"
        let current = FieldChooserReading10868(label: "Reported gap · lap 52", value: .missing(words))
        let lapOnly = FieldChaseReport10868(id: Self.stages[1].id, lap: 52, seconds: nil,
                                            reading: FieldChooserReading10868(label: "Lap 52", value: .missing(words)))
        let partial = Self.model(Self.input(gap: FieldChaseGap10868(
            headline: "Gap at lap 52 not reported", current: current,
            runs: [[Self.report(Self.stages[0]), lapOnly]], highlighted: Self.stages[1].id, axis: Self.axis)))
        XCTAssertEqual(partial.gapSummary, "Reported gap · lap 52: \(words)")
        XCTAssertEqual(partial.placedRuns.map { $0.map(\.id) }, [[Self.stages[0].id]])
        XCTAssertNil(partial.highlightedID)
        XCTAssertNil(partial.pointWords(lapOnly))
        XCTAssertEqual(partial.readouts, plain.readouts)
    }

    // MARK: Real zero and missing

    func testARealZeroIsANumberAndAMissingChanceOrGapIsNeverZero() {
        let stage = Self.stages[1]
        // CONSTRUCTED: a recorded 0 tied to its own "0%" reading.
        let zeroReading = FieldChooserReading10868(label: Self.recordedLabel, value: .recorded(text: "0%", detail: "\(stage.tradeClock) · \(Self.tradeSource)"))
        let zero = Self.model(Self.input(
            catalogue: [Self.neighbours[0], Self.leclercRecord(stage, plan: .comparison(before: Self.beforeReading, later: zeroReading)), Self.neighbours[1]],
            pairs: [FieldMovementPair10868(ref: Self.leclercRef, before: Self.pair(stage).before,
                                           later: FieldMovementObservation10868(probability: 0, reading: zeroReading), movement: nil, observation: nil)]))
        XCTAssertEqual(zero.readouts.map(FieldChaseModel10868.figure), ["14%", "0%"])

        // CONSTRUCTED: no pre-race association, and the owner's own pre-race absence words.
        let unpaired = Self.model(Self.input(pairs: [FieldMovementPair10868(ref: Self.leclercRef, before: nil, later: Self.pair(stage).later, movement: nil, observation: nil)]))
        XCTAssertEqual(unpaired.readouts.first, .unavailable(label: Self.beforeLabel, words: Self.beforeUnavailable))
        let ownWords = FieldChooserReading10868(label: Self.beforeLabel, value: .missing("Not traded before the start"))
        let absent = Self.model(Self.input(
            catalogue: [Self.neighbours[0], Self.leclercRecord(stage, plan: .comparison(before: ownWords, later: Self.recordedReading(stage))), Self.neighbours[1]]))
        XCTAssertEqual(absent.readouts.first, .reading(ownWords))
        for model in [unpaired, absent] {
            XCTAssertEqual(FieldChaseModel10868.figure(model.readouts[1]), "16.1%")
            XCTAssertFalse(Self.everyLine(model).contains("0%"))
            XCTAssertFalse(model.chanceSummary.contains(": 0%"))
        }

        // A 0 s gap is a placed point on the zero line; a missing gap is not placed.
        let caught = FieldChaseReport10868(id: "constructed:caught", lap: 58, seconds: 0,
                                           reading: FieldChooserReading10868(label: "Lap 58", value: .recorded(text: "0.0 sec", detail: "constructed")))
        let gone = FieldChaseReport10868(id: "constructed:nogap", lap: 58, seconds: nil,
                                         reading: FieldChooserReading10868(label: "Lap 58", value: .recorded(text: "— sec", detail: "constructed")))
        XCTAssertEqual(FieldChaseGeometry10868.unit(caught, axis: Self.axis), FieldChooserUnitPoint10868(x: 1, y: 1))
        XCTAssertNil(FieldChaseGeometry10868.unit(gone, axis: Self.axis))
        let model = Self.model(Self.input(gap: Self.gap(1, runs: [[Self.report(Self.stages[0]), gone]])))
        XCTAssertEqual(model.pointWords(gone), Self.pointUnavailable)
    }

    // MARK: Identity

    func testExactChallengerIdentityAndUnresolvedDuplicateForeignWithdrawnBorrowNothing() {
        let plain = Self.model()
        let stage = Self.stages[1]
        let foreign = FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "constructed:f1:other-race"), name: Self.leclerc.name)
        let withdrawn = FieldFinishSlot10868(ref: Self.ref("5229499", "constructed-withdrawn"), name: "Withdrawn driver")
        let blank = FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, "  "), name: " ")
        var cases: [(String, FieldChaseModel10868)] = [
            ("foreign", Self.model(Self.input(challenger: foreign))),
            ("withdrawn", Self.model(Self.input(challenger: withdrawn))),
            ("blank", Self.model(Self.input(challenger: blank))),
            ("duplicate record", Self.model(Self.input(catalogue: Self.catalogue(stage) + [Self.leclercRecord(stage)]))),
        ]
        cases.append(("foreign pair only", Self.model(Self.input(challenger: foreign, pairs: [Self.pair(stage, ref: foreign.ref)]))))
        for (label, model) in cases {
            XCTAssertNil(model.challenger, label)
            XCTAssertEqual(model.readouts, [], label)
            XCTAssertEqual(model.chanceSummary, "", label)
            XCTAssertNil(model.openAction(canOpen: true), label)
            XCTAssertNil(model.openSpokenLabel, label)
            XCTAssertEqual(model.unavailable.map { $0.words }, Self.unavailable, label)
            // The physical gap is independent of the chance identity.
            XCTAssertEqual(model.headline, plain.headline, label)
            XCTAssertEqual(model.placedRuns, plain.placedRuns, label)
            XCTAssertFalse(Self.everyLine(model).contains { $0.contains("14%") || $0.contains("16.1%") }, label)
        }
        XCTAssertEqual(cases[0].1.unavailable.flatMap { $0.name }, Self.leclerc.name)
        XCTAssertNil(cases[2].1.unavailable.flatMap { $0.name })

        // Two identical associations for the challenger are none.
        let twice = Self.model(Self.input(pairs: [Self.pair(stage), Self.pair(stage)]))
        XCTAssertEqual(twice.readouts, [.unavailable(label: Self.beforeLabel, words: Self.beforeUnavailable),
                                        .unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)])
        // Leclerc's readings carried on a neighbour's association are never borrowed.
        let elsewhere = Self.model(Self.input(pairs: [Self.pair(stage, ref: Self.ref(Self.verstappen.market, Self.verstappen.outcome))]))
        XCTAssertEqual(elsewhere.readouts, twice.readouts)
        // Valid neighbours keep resolving whatever happens to the challenger.
        let duplicated = cases[3].1
        for record in Self.neighbours {
            XCTAssertEqual(duplicated.field.resolve(record.ref), .original(record))
            XCTAssertEqual(plain.field.resolve(record.ref), .original(record))
        }
    }

    // MARK: Independence

    func testChancesAreNeverComplementedNormalizedOrTakenFromANeighbour() {
        let stage = Self.stages[1]
        // A CONSTRUCTED independent No for Leclerc's market: only its own association counts.
        let noRef = Self.ref(Self.leclerc.market, "constructed-no-token:5229402")
        let noReading = FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: "80%", detail: "constructed"))
        let no = FieldChooserOriginal10868(
            ref: noRef, name: "Charles Leclerc · No", plan: .single(noReading),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "Constructed control")
        let slot = FieldFinishSlot10868(ref: noRef, name: "Charles Leclerc · No")
        let untied = Self.model(Self.input(catalogue: Self.catalogue(stage) + [no], challenger: slot))
        XCTAssertEqual(untied.readouts, [.unavailable(label: Self.beforeLabel, words: Self.beforeUnavailable),
                                         .unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)])
        for complement in ["86%", "83.9%", "80%"] {
            XCTAssertFalse(Self.everyLine(untied).contains { $0.contains(complement) }, complement)
        }
        let own = Self.model(Self.input(catalogue: Self.catalogue(stage) + [no], challenger: slot,
            pairs: [Self.pair(stage), FieldMovementPair10868(ref: noRef, before: FieldMovementObservation10868(probability: 0.8, reading: noReading), later: nil, movement: nil, observation: nil)]))
        XCTAssertEqual(own.readouts.map(FieldChaseModel10868.figure), ["80%", nil])
        // The Yes keeps its own raw values; nothing sums the two.
        XCTAssertEqual(Self.raw(own), [Self.before.p, stage.recorded])
        // The pair's change words and observation key never reach the card.
        XCTAssertFalse(Self.everyLine(Self.model()).contains { $0.contains("constructed movement") || $0.contains("constructed-observation") })
    }

    // MARK: One coordinate

    func testOneSecondsAndLapCoordinatePlacesReportsWithoutBridgingOrClamping() {
        let model = Self.model(Self.input(2))
        let units = model.placedRuns.flatMap { $0 }.map(\.unit)
        XCTAssertEqual(units.map(\.x), [0, 0.5, 1])
        XCTAssertEqual(units[0].y, 0.25, accuracy: 1e-12)
        XCTAssertEqual(units[1].y, 0.545, accuracy: 1e-12)
        XCTAssertEqual(units[2].y, 0.55, accuracy: 1e-12)
        XCTAssertEqual(model.secondsTicks, [FieldChasePlacedTick10868(label: "0s", unit: 1),
                                            FieldChasePlacedTick10868(label: "10s", unit: 0.5),
                                            FieldChasePlacedTick10868(label: "20s", unit: 0)])
        XCTAssertEqual(model.lapTicks.map(\.unit), [0, 0.5, 1])

        // The domain's edges are placed exactly.
        let edge = { (lap: Double, seconds: Double) in
            FieldChaseReport10868(id: "constructed:\(lap):\(seconds)", lap: lap, seconds: seconds,
                                  reading: FieldChooserReading10868(label: "Lap", value: .recorded(text: "\(seconds) sec", detail: "constructed")))
        }
        XCTAssertEqual(FieldChaseGeometry10868.unit(edge(46, 20), axis: Self.axis), FieldChooserUnitPoint10868(x: 0, y: 0))
        XCTAssertEqual(FieldChaseGeometry10868.unit(edge(58, 0), axis: Self.axis), FieldChooserUnitPoint10868(x: 1, y: 1))

        // Out-of-domain, invalid or worded reports break the run — never bridged or clamped.
        let words = FieldChaseReport10868(id: "constructed:words", lap: 50, seconds: 12,
                                          reading: FieldChooserReading10868(label: "Lap 50", value: .missing("Gap not reported")))
        let bad = [edge(50, 21), edge(50, -1), edge(50, .nan), edge(60, 10), edge(.infinity, 10), words]
        let first = Self.report(Self.stages[0])
        let second = Self.report(Self.stages[1])
        let third = Self.report(Self.stages[2])
        for report in bad {
            let runs = FieldChaseGeometry10868.runs([[first, report, second, third]], axis: Self.axis)
            XCTAssertEqual(runs.map { $0.map(\.id) }, [[first.id], [second.id, third.id]], report.id)
            XCTAssertNil(FieldChaseGeometry10868.unit(report, axis: Self.axis), report.id)
        }
        let broken = Self.model(Self.input(2, gap: Self.gap(2, runs: [[first, edge(50, 21), second, third]])))
        XCTAssertEqual(broken.pointWords(edge(50, 21)), Self.pointUnavailable)
        XCTAssertEqual(Self.plan(broken)?.lines.map(\.count), [2])
        XCTAssertEqual(Self.plan(broken)?.dots.count, 3)

        // Separate owner runs never join.
        let apart = FieldChaseGeometry10868.runs([[first], [second]], axis: Self.axis)
        XCTAssertEqual(apart.map { $0.map(\.id) }, [[first.id], [second.id]])
        // An invalid domain places nothing and draws no plot.
        let invalidAxes = [
            FieldChaseAxis10868(lapLower: 58, lapUpper: 46, lapTicks: [], secondsLower: 0, secondsUpper: 20, secondsTicks: []),
            FieldChaseAxis10868(lapLower: 46, lapUpper: 58, lapTicks: [], secondsLower: -5, secondsUpper: 20, secondsTicks: []),
            FieldChaseAxis10868(lapLower: 46, lapUpper: .nan, lapTicks: [], secondsLower: 0, secondsUpper: 20, secondsTicks: []),
        ]
        for axis in invalidAxes {
            let invalid = Self.model(Self.input(gap: Self.gap(1, axis: axis)))
            XCTAssertFalse(invalid.showsPlot)
            XCTAssertEqual(invalid.placedRuns, [])
            XCTAssertNil(invalid.highlightedID)
            XCTAssertEqual(invalid.headline, Self.stages[1].headline)
        }
    }

    // MARK: Owner order and highlight

    func testOwnerOrderIsKeptAndOnlyTheOwnersUniquePlacedReportIsHighlighted() {
        let reports = Self.stages.map(Self.report)
        // Reversed owner order is drawn as given, never sorted.
        let reversed = Self.model(Self.input(2, gap: Self.gap(2, runs: [Array(reports.reversed())])))
        XCTAssertEqual(reversed.placedRuns.flatMap { $0 }.map(\.unit.x), [1, 0.5, 0])
        XCTAssertEqual(reversed.graphicSummary.components(separatedBy: "; ").map { String($0.prefix(6)) }, ["Lap 58", "Lap 52", "Lap 46"])

        // A duplicated report is drawn twice (never deduplicated) and highlights nothing.
        let duplicate = Self.model(Self.input(2, gap: Self.gap(2, runs: [reports + [reports[2]]])))
        XCTAssertEqual(Self.plan(duplicate)?.dots.count, 4)
        XCTAssertNil(duplicate.highlightedID)
        XCTAssertNil(Self.plan(duplicate)?.highlight)
        XCTAssertFalse(duplicate.graphicSummary.contains("This report"))

        // A highlight on an unplaced, unknown or blank id emphasizes nothing.
        let unplaced = FieldChaseReport10868(id: "constructed:unplaced", lap: 55, seconds: 25,
                                             reading: FieldChooserReading10868(label: "Lap 55", value: .recorded(text: "25.0 sec", detail: "constructed")))
        for id in ["constructed:unplaced", "constructed:unknown", " "] {
            let model = Self.model(Self.input(2, gap: Self.gap(2, runs: [reports + [unplaced]], highlighted: id)))
            XCTAssertNil(model.highlightedID, id)
            XCTAssertNil(Self.plan(model)?.highlight, id)
        }
        // The owner's exact id, carried once and placed, is the one ring.
        let middle = Self.model(Self.input(2, gap: Self.gap(2, highlighted: Self.stages[1].id)))
        XCTAssertEqual(middle.highlightedID, Self.stages[1].id)
        let plan = Self.plan(middle)
        XCTAssertEqual(plan?.highlight?.midX ?? -1, plan?.dots[1].midX ?? -2, accuracy: 1e-9)
        XCTAssertEqual(plan?.highlight?.midY ?? -1, plan?.dots[1].midY ?? -2, accuracy: 1e-9)
    }

    // MARK: Plot plan and readout plans

    func testThePlotPlanSharesOneInsetForMarksGridAndLabelsAtCommonWidths() {
        let model = Self.model(Self.input(2))
        guard let plan = Self.plan(model) else { return XCTFail("plan") }
        XCTAssertEqual(plan.plot, CGRect(x: 22, y: 0, width: 278, height: 151))
        XCTAssertEqual(plan.inset, 8)
        XCTAssertEqual(plan.gridYs, [143, 75.5, 8])
        XCTAssertEqual(plan.lapMarks, [30, 161, 292])
        XCTAssertEqual(plan.dots.map(\.midX), [30, 161, 292])
        XCTAssertEqual(plan.dots[0].midY, 8 + 135 * 0.25, accuracy: 1e-9)
        XCTAssertEqual(plan.dots[1].midY, 8 + 135 * 0.545, accuracy: 1e-9)
        XCTAssertEqual(plan.dots[2].midY, 8 + 135 * 0.55, accuracy: 1e-9)
        XCTAssertEqual(plan.lines.map(\.count), [3])
        XCTAssertEqual(plan.secondsLabels, [CGRect(x: 0, y: 136.5, width: 16, height: 13),
                                            CGRect(x: 0, y: 69, width: 16, height: 13),
                                            CGRect(x: 0, y: 1.5, width: 16, height: 13)])
        XCTAssertEqual(plan.lapLabels, [CGRect(x: 22, y: 157, width: 22, height: 13),
                                        CGRect(x: 150, y: 157, width: 22, height: 13),
                                        CGRect(x: 278, y: 157, width: 22, height: 13)])
        XCTAssertEqual(plan.highlight, plan.dots[2].insetBy(dx: -2, dy: -2))

        // CONSTRUCTED 320/375/393/wide canvases with standard and AX label sizes:
        // every label inside the canvas, every dot whole inside the plot, the
        // gridline and dot for one value on one coordinate, lap labels apart.
        for width: CGFloat in [288, 343, 361, 600] {
            for (seconds, laps, height) in [(CGSize(width: 16, height: 13), CGSize(width: 22, height: 13), CGFloat(170)),
                                            (CGSize(width: 44, height: 34), CGSize(width: 58, height: 34), CGFloat(420))] {
                let label = "\(width)/\(seconds.width)"
                guard let plan = Self.plan(model, size: CGSize(width: width, height: height), seconds: seconds, laps: laps) else {
                    XCTFail(label); continue
                }
                let canvas = CGRect(x: 0, y: 0, width: width, height: height)
                for rect in (plan.secondsLabels + plan.lapLabels).compactMap({ $0 }) {
                    XCTAssertTrue(canvas.contains(rect), label)
                }
                for dot in plan.dots + [plan.highlight].compactMap({ $0 }) {
                    XCTAssertTrue(plan.plot.contains(dot), label)
                }
                let placed = plan.lapLabels.compactMap { $0 }
                for (left, right) in zip(placed, placed.dropFirst()) {
                    XCTAssertGreaterThanOrEqual(right.minX, left.maxX + 6, label)
                }
                XCTAssertEqual(plan.lapLabels.compactMap { $0 }.count, 3, label)
                // A 20 s report would sit exactly on the 20s gridline.
                let top = FieldChaseGeometry10868.plotPlan(
                    size: CGSize(width: width, height: height),
                    runs: [[FieldChasePlaced10868(id: "constructed:20", unit: FieldChooserUnitPoint10868(x: 0.5, y: 0))]],
                    highlighted: nil,
                    secondsTicks: model.secondsTicks.map { FieldChaseMeasuredTick10868(unit: $0.unit, size: seconds) },
                    lapTicks: model.lapTicks.map { FieldChaseMeasuredTick10868(unit: $0.unit, size: laps) },
                    dotDiameter: 10, spacing: 6)
                XCTAssertEqual(top?.dots.first?.midY ?? -1, plan.gridYs[2], accuracy: 1e-9, label)
            }
        }

        // Crowded lap labels are left out in owner order — the marks and dots never move.
        guard let crowded = Self.plan(model, laps: CGSize(width: 140, height: 13)) else { return XCTFail("crowded") }
        XCTAssertEqual(crowded.lapLabels.map { $0 != nil }, [true, false, false])
        XCTAssertEqual(crowded.lapMarks, plan.lapMarks)
        XCTAssertEqual(crowded.dots, plan.dots)
        // A label wider than the plot gets no place.
        XCTAssertEqual(Self.plan(model, laps: CGSize(width: 300, height: 13))?.lapLabels, [nil, nil, nil])
        // A size that cannot be drawn draws nothing.
        XCTAssertNil(Self.plan(model, size: CGSize(width: 30, height: 170)))
        XCTAssertNil(Self.plan(model, size: CGSize(width: 300, height: 20)))
        XCTAssertNil(Self.plan(model, size: CGSize(width: CGFloat.nan, height: 170)))

        // The readouts stack at accessibility sizes, side by side otherwise.
        XCTAssertTrue(FieldChaseGeometry10868.stacksReadouts(accessibilitySize: true))
        XCTAssertFalse(FieldChaseGeometry10868.stacksReadouts(accessibilitySize: false))
    }

    // MARK: Spoken text

    func testSpokenSummariesKeepWholeNamesEveryReportAndOwnClocks() {
        let model = Self.model()
        XCTAssertEqual(model.chanceSummary,
                       "Pre-race win: 14%, Oct 11, 4:59:46 AM PT · Polymarket trade. Recorded win: 16.1%, Oct 11, 6:30:12 AM PT · Polymarket trade")
        XCTAssertEqual(model.gapSummary, "Reported gap · lap 52: 9.1 sec, Reported Oct 11, 6:30:26 AM PT · Guardian lap report")
        XCTAssertEqual(model.graphicSummary,
                       "Lap 46: 15.0 sec, Reported Oct 11, 6:20:49 AM PT · Guardian lap report; "
                       + "Lap 52: 9.1 sec, Reported Oct 11, 6:30:26 AM PT · Guardian lap report. This report")

        let withheld = Self.model(Self.input(2, pairs: [Self.pair(Self.stages[2], recorded: .nan)]))
        XCTAssertEqual(withheld.chanceSummary,
                       "Pre-race win: 14%, Oct 11, 4:59:46 AM PT · Polymarket trade. Recorded win: No recent probability")

        let offScale = FieldChaseReport10868(id: "constructed:off", lap: 55, seconds: 25,
                                             reading: FieldChooserReading10868(label: "Lap 55", value: .recorded(text: "25.0 sec", detail: "constructed")))
        let off = Self.model(Self.input(gap: Self.gap(1, runs: [[Self.report(Self.stages[0]), offScale]], highlighted: "none")))
        XCTAssertEqual(off.graphicSummary,
                       "Lap 46: 15.0 sec, Reported Oct 11, 6:20:49 AM PT · Guardian lap report; Lap 55: 25.0 sec, constructed. \(Self.pointUnavailable)")

        // A long full name is kept whole, resolved or not.
        let long = "Charles Marc Hervé Perceval Leclerc (Scuderia Ferrari HP)"
        let stage = Self.stages[1]
        let whole = Self.model(Self.input(catalogue: [Self.neighbours[0], Self.leclercRecord(stage, name: long), Self.neighbours[1]]))
        XCTAssertEqual(whole.challenger?.name, long)
        XCTAssertEqual(whole.openSpokenLabel, "Leclerc's win history, \(long)")
        let gone = Self.model(Self.input(challenger: FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "elsewhere"), name: long)))
        XCTAssertEqual(gone.unavailable.flatMap { $0.name }, long)
    }

    // MARK: Open

    func testOpenHandsBackTheExactChallengerAndNoCallbackIsStatic() {
        let model = Self.model()
        let opening = model.openAction(canOpen: true)
        XCTAssertEqual(opening, Self.leclercRef)
        XCTAssertEqual(model.hint(opening), Self.openHint)
        XCTAssertEqual(model.openSpokenLabel, "Leclerc's win history, Charles Leclerc")
        XCTAssertNil(model.openAction(canOpen: false))
        XCTAssertEqual(model.hint(model.openAction(canOpen: false)), "")

        // Nothing opens for a challenger that does not resolve.
        let foreign = Self.model(Self.input(challenger: FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "elsewhere"), name: Self.leclerc.name)))
        XCTAssertNil(foreign.openAction(canOpen: true))
        XCTAssertEqual(foreign.hint(nil), "")
        XCTAssertFalse(Self.everyLine(foreign).contains(Self.openHint))
    }

    // MARK: Readable plot or report list

    func testTheViewListsTheReportsWhenMeasuredLabelsLeaveNoReadablePlot() {
        let model = Self.model(Self.input(2))
        let standardSeconds = Array(repeating: CGSize(width: 16, height: 13), count: model.secondsTicks.count)
        let standardLaps = Array(repeating: CGSize(width: 22, height: 13), count: model.lapTicks.count)
        func plan(width: CGFloat, height: CGFloat = 170, seconds: [CGSize], laps: [CGSize]) -> FieldChasePlotPlan10868? {
            FieldChaseGeometry10868.plotPlan(
                size: CGSize(width: width, height: height), runs: model.placedRuns, highlighted: model.highlightedID,
                secondsTicks: zip(model.secondsTicks, seconds).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1) },
                lapTicks: zip(model.lapTicks, laps).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1) },
                dotDiameter: 10, spacing: 6)
        }
        func shows(_ width: CGFloat, height: CGFloat = 170, seconds: [CGSize], laps: [CGSize]) -> Bool {
            FieldChaseGeometry10868.showsLabelledPlot(width: width, secondsLabels: seconds, lapLabels: laps, height: height, dotDiameter: 10, spacing: 6)
        }

        // The retained three-report graphic is the labelled plot at every common width.
        XCTAssertEqual(FieldChaseGeometry10868.labelledPlotWidth(secondsLabels: standardSeconds, lapLabels: standardLaps, height: 170, dotDiameter: 10, spacing: 6), 45)
        for width: CGFloat in [288, 343, 361, 600] {
            XCTAssertTrue(shows(width, seconds: standardSeconds, laps: standardLaps), "\(width)")
            XCTAssertTrue(plan(width: width, seconds: standardSeconds, laps: standardLaps).map(FieldChaseGeometry10868.isReadable) ?? false, "\(width)")
        }

        // CONSTRUCTED: seconds labels so wide the gutter leaves no marks rect.
        let giant = Array(repeating: CGSize(width: 280, height: 13), count: 3)
        XCTAssertNil(plan(width: 300, seconds: giant, laps: standardLaps))
        XCTAssertEqual(FieldChaseGeometry10868.labelledPlotWidth(secondsLabels: giant, lapLabels: standardLaps, height: 170, dotDiameter: 10, spacing: 6), 309)
        XCTAssertFalse(shows(300, seconds: giant, laps: standardLaps))

        // CONSTRUCTED: a plan exists but every lap label is left out — never a bare plot.
        let wide = Array(repeating: CGSize(width: 300, height: 13), count: 3)
        let bare = plan(width: 300, seconds: standardSeconds, laps: wide)
        XCTAssertNotNil(bare)
        XCTAssertEqual(bare?.lapLabels, [nil, nil, nil])
        XCTAssertFalse(bare.map(FieldChaseGeometry10868.isReadable) ?? true)
        XCTAssertFalse(shows(300, seconds: standardSeconds, laps: wide))

        // Crowded labels keep the plot while at least one lap label is placed.
        let crowded = Array(repeating: CGSize(width: 140, height: 13), count: 3)
        XCTAssertTrue(plan(width: 300, seconds: standardSeconds, laps: crowded).map(FieldChaseGeometry10868.isReadable) ?? false)
        XCTAssertTrue(shows(300, seconds: standardSeconds, laps: crowded))

        // Labels too tall for the height, or an axis with no owner ticks: the list at any width.
        let tall = Array(repeating: CGSize(width: 22, height: 160), count: 3)
        XCTAssertNil(FieldChaseGeometry10868.labelledPlotWidth(secondsLabels: standardSeconds, lapLabels: tall, height: 170, dotDiameter: 10, spacing: 6))
        XCTAssertFalse(shows(10_000, seconds: standardSeconds, laps: tall))
        XCTAssertNil(FieldChaseGeometry10868.labelledPlotWidth(secondsLabels: standardSeconds, lapLabels: [], height: 170, dotDiameter: 10, spacing: 6))
        XCTAssertNil(FieldChaseGeometry10868.labelledPlotWidth(secondsLabels: [], lapLabels: standardLaps, height: 170, dotDiameter: 10, spacing: 6))
        let unticked = FieldChaseAxis10868(lapLower: 46, lapUpper: 58, lapTicks: [], secondsLower: 0, secondsUpper: 20, secondsTicks: Self.axis.secondsTicks)
        XCTAssertEqual(Self.model(Self.input(gap: Self.gap(1, axis: unticked))).lapTicks, [])

        // Wherever the layout offers the plot, the plan it draws is readable.
        let cases: [([CGSize], [CGSize], CGFloat)] = [
            (standardSeconds, standardLaps, 170),
            (Array(repeating: CGSize(width: 44, height: 34), count: 3), Array(repeating: CGSize(width: 58, height: 34), count: 3), 420),
            (standardSeconds, crowded, 170),
            (Array(repeating: CGSize(width: 100, height: 13), count: 3), standardLaps, 170),
        ]
        for (seconds, laps, height) in cases {
            guard let width = FieldChaseGeometry10868.labelledPlotWidth(secondsLabels: seconds, lapLabels: laps, height: height, dotDiameter: 10, spacing: 6) else {
                XCTFail("\(seconds[0])"); continue
            }
            XCTAssertTrue(plan(width: width, height: height, seconds: seconds, laps: laps).map(FieldChaseGeometry10868.isReadable) ?? false, "\(seconds[0])/\(laps[0])")
        }

        // The list carries the owner's own readings in the owner's order, the
        // highlight on the exact report and the unplaced words.
        XCTAssertEqual(model.reports.map { $0.reading.label }, ["Lap 46", "Lap 52", "Lap 58"])
        XCTAssertEqual(model.reports.map { model.isHighlighted($0) }, [false, false, true])
        XCTAssertEqual(model.reports.map { FieldOutlookModel10868.detailLine($0.reading) },
                       ["Reported Oct 11, 6:20:49 AM PT · Guardian lap report", "Reported Oct 11, 6:30:26 AM PT · Guardian lap report",
                        "Reported Oct 11, 6:40:53 AM PT · Guardian lap report"])
        XCTAssertEqual(model.reports.map { model.pointWords($0) }, [nil, nil, nil])
        let duplicate = Self.model(Self.input(2, gap: Self.gap(2, runs: [Self.stages.map(Self.report) + [Self.report(Self.stages[2])]])))
        XCTAssertFalse(duplicate.reports.contains { duplicate.isHighlighted($0) })
    }

    // MARK: Finite graphic layout

    func testTheGraphicLayoutChoosesThePlotOrTheListAtFiniteSizes() {
        let model = Self.model(Self.input(2))
        let standardSeconds = Array(repeating: CGSize(width: 16, height: 13), count: model.secondsTicks.count)
        let standardLaps = Array(repeating: CGSize(width: 22, height: 13), count: model.lapTicks.count)
        let listSize = CGSize(width: 343, height: 212)
        func choice(_ width: CGFloat?, height: CGFloat = 170, seconds: [CGSize], laps: [CGSize]) -> FieldChaseGraphicChoice10868 {
            FieldChaseGeometry10868.graphicChoice(proposedWidth: width, secondsLabels: seconds, lapLabels: laps, height: height, dotDiameter: 10, spacing: 6)
        }
        func size(_ choice: FieldChaseGraphicChoice10868, _ width: CGFloat?, height: CGFloat = 170, list: CGSize = listSize) -> CGSize {
            FieldChaseGeometry10868.graphicSize(choice, proposedWidth: width, plotHeight: height, listSize: list)
        }
        func isFinite(_ size: CGSize) -> Bool {
            size.width.isFinite && size.height.isFinite && size.width >= 0 && size.height >= 0
        }
        let offers: [CGFloat?] = [nil, 0, 1, 44, 288, 300, 343, 361, 600, 10_000, CGFloat.infinity, CGFloat.nan]

        // Ordinary: the retained graphic is the plot at the offered width,
        // at its narrowest readable width when offered none, and the plan the
        // Canvas draws there is readable.
        for width: CGFloat in [288, 343, 361, 600] {
            XCTAssertEqual(choice(width, seconds: standardSeconds, laps: standardLaps), .plot(width: width))
            XCTAssertEqual(size(.plot(width: width), width), CGSize(width: width, height: 170))
        }
        XCTAssertEqual(choice(nil, seconds: standardSeconds, laps: standardLaps), .plot(width: 45))
        XCTAssertEqual(choice(.infinity, seconds: standardSeconds, laps: standardLaps), .plot(width: 45))
        XCTAssertEqual(size(.plot(width: 45), nil), CGSize(width: 45, height: 170))
        XCTAssertEqual(choice(44, seconds: standardSeconds, laps: standardLaps), .list)

        // Narrow: a gutter that leaves no marks rect lists the reports at the
        // natural list size; wide enough, the plot returns.
        let giant = Array(repeating: CGSize(width: 280, height: 13), count: 3)
        XCTAssertEqual(choice(300, seconds: giant, laps: standardLaps), .list)
        XCTAssertEqual(size(.list, 300), listSize)
        XCTAssertEqual(choice(309, seconds: giant, laps: standardLaps), .plot(width: 309))

        // Every lap label left out: the list, never a bare plot.
        let wide = Array(repeating: CGSize(width: 300, height: 13), count: 3)
        XCTAssertEqual(choice(300, seconds: standardSeconds, laps: wide), .list)

        // Absent axis ticks, labels too tall for the plot, and an unbounded or
        // invalid probe: the list at every offer, at a finite size — never an
        // infinite width and never the plot's marks.
        let tall = Array(repeating: CGSize(width: 22, height: 160), count: 3)
        let taller = Array(repeating: CGSize(width: 22, height: 171), count: 3)
        let unbounded = Array(repeating: CGSize(width: CGFloat.infinity, height: 13), count: 3)
        let invalid = Array(repeating: CGSize(width: CGFloat.nan, height: 13), count: 3)
        let listOnly: [([CGSize], [CGSize], CGFloat)] = [
            (standardSeconds, [], 170), ([], standardLaps, 170), ([], [], 170),
            (standardSeconds, tall, 170), (taller, standardLaps, 170),
            (standardSeconds, unbounded, 170), (unbounded, standardLaps, 170), (invalid, standardLaps, 170),
            (standardSeconds, standardLaps, .infinity), (standardSeconds, standardLaps, .nan),
        ]
        for (seconds, laps, height) in listOnly {
            for width in offers {
                XCTAssertEqual(choice(width, height: height, seconds: seconds, laps: laps), .list, "\(String(describing: width))")
                XCTAssertTrue(isFinite(size(.list, width, height: height)), "\(String(describing: width))")
            }
        }

        // Both returned sizes stay finite for every offer, even when a
        // measurement is not.
        for width in offers {
            for chosen in [choice(width, seconds: standardSeconds, laps: standardLaps), choice(width, seconds: giant, laps: standardLaps)] {
                XCTAssertTrue(isFinite(size(chosen, width)), "\(String(describing: width))")
            }
            XCTAssertTrue(isFinite(size(.list, width, list: CGSize(width: CGFloat.infinity, height: CGFloat.infinity))))
            XCTAssertTrue(isFinite(size(.list, width, list: CGSize(width: CGFloat.nan, height: -1))))
            XCTAssertTrue(isFinite(size(.plot(width: .infinity), width, height: .infinity)))
        }
        XCTAssertEqual(size(.list, 300, list: CGSize(width: CGFloat.infinity, height: 212)), CGSize(width: 300, height: 212))
        XCTAssertEqual(size(.list, nil, list: CGSize(width: CGFloat.infinity, height: CGFloat.infinity)), .zero)

        // Wherever the layout chooses the plot, the plan the Canvas draws at
        // that width is readable.
        for width in offers {
            guard case .plot(let chosen) = choice(width, seconds: standardSeconds, laps: standardLaps) else { continue }
            let plan = FieldChaseGeometry10868.plotPlan(
                size: CGSize(width: chosen, height: 170), runs: model.placedRuns, highlighted: model.highlightedID,
                secondsTicks: zip(model.secondsTicks, standardSeconds).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1) },
                lapTicks: zip(model.lapTicks, standardLaps).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1) },
                dotDiameter: 10, spacing: 6)
            XCTAssertTrue(plan.map(FieldChaseGeometry10868.isReadable) ?? false, "\(chosen)")
        }

        // The plan refuses an unbounded size outright: no marks without a finite plot.
        XCTAssertNil(FieldChaseGeometry10868.plotPlan(
            size: CGSize(width: CGFloat.infinity, height: 170), runs: model.placedRuns, highlighted: model.highlightedID,
            secondsTicks: zip(model.secondsTicks, standardSeconds).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1) },
            lapTicks: zip(model.lapTicks, standardLaps).map { FieldChaseMeasuredTick10868(unit: $0.unit, size: $1) },
            dotDiameter: 10, spacing: 6))
    }
}

// MARK: - #10868 field expectations — "How expectations shifted"

/// The racing-live expectations card — three drivers' own pre-race and
/// recorded win chances, hollow and filled, on one shared probability scale —
/// on the movement card's own model.
///
/// ARCHIVED raw values come from the 2026 Singapore Grand Prix, as retained in
/// `shipping-adoption-20261027/RACING-EXPECTATIONS-RETAINED-CASES.json`
/// (sha256 04c85de1…4449) and reconciled with the reference
/// `racingLiveCapture.json` / `racingEvidence.json` trade rules: the 75
/// canonical originals (winner, podium, fastest-lap and matchup contracts) with
/// their market and Yes token ids; the owner's three displayed winner contracts
/// — Max Verstappen (5229406), Charles Leclerc (5229402), Lewis Hamilton
/// (5229411) — with their own pre-race trades (0.6499999935 at 11:59:31Z,
/// 0.1399999999 at 11:59:46Z, 0.16 at 11:59:19Z; start 12:00:00Z) and their own
/// last eligible trade before each lap report (lap 46 reported 13:20:49Z, lap
/// 52 at 13:30:26Z, lap 58 at 13:40:53Z): Verstappen 0.95 at 13:19:58Z, 0.909 at
/// 13:29:48Z, 0.999 at 13:40:19Z; Leclerc 0.0829999984 at 13:20:28Z,
/// 0.1612595359 at 13:30:12Z, 0.001 at 13:40:33Z; Hamilton 0.002 at 13:19:40Z,
/// 0.002 at 13:30:03Z and NO qualifying quote at lap 58 — his last captured
/// trade, 0.001 at 13:35:12Z, is more than five minutes old and is used only as
/// a hostile control. The shown values sum past 1 (1.035 at lap 46) and stay as
/// they are. Verstappen's archived win and the three final positions are used
/// only as hostile controls the live card must never show. The five-minute rule
/// is the reference replay's provenance, not a native policy: the owner
/// supplies admitted endpoints.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope
/// string, every label, figure text (prepared with the reference
/// `probabilityLabel.ts`), movement word (its `pp` of the archived raw change),
/// PT clock line (from each sample's own archived time), source word,
/// observation key, the 0/50/100% scale and its words, the card copy and phase,
/// the other canonical records' plans, the hostile later/final inputs, the No
/// control, and every withdrawn, duplicate, repeated, blank, foreign, zero,
/// equal, invalid, off-scale and long-name case. Track and label sizes are
/// CONSTRUCTED measurements: native arithmetic here is not a rendered fit.
final class FieldExpectationsCard10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Chance = (p: Double, figure: String, clock: String)
    private typealias Recorded = (p: Double, figure: String, clock: String, movement: String)
    private typealias Driver = (market: String, outcome: String, name: String, before: Chance, recorded: [Recorded?])

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:f1:singapore-2026:expectations"

    /// ARCHIVED lap reports; PT clocks CONSTRUCTED from them. Never a trade clock.
    private static let laps = [46, 52, 58]
    private static let reportClocks = ["Oct 11, 6:20:49 AM PT", "Oct 11, 6:30:26 AM PT", "Oct 11, 6:40:53 AM PT"]

    /// ARCHIVED ids, names and raw values; figures, PT clocks and movement words CONSTRUCTED from them.
    private static let verstappen: Driver = (
        "5229406", "105026689771335810478914327541724319323338915766526076386906176141135574302746", "Max Verstappen",
        (0.6499999935, "65%", "Oct 11, 4:59:31 AM PT"),
        [(0.95, "95%", "Oct 11, 6:19:58 AM PT", "+30.0 pp"),
         (0.909, "90.9%", "Oct 11, 6:29:48 AM PT", "+25.9 pp"),
         (0.999, "99.9%", "Oct 11, 6:40:19 AM PT", "+34.9 pp")]
    )
    private static let leclerc: Driver = (
        "5229402", "92443082174901362958213182894863948289679800011664028904195269564952495193793", "Charles Leclerc",
        (0.1399999999, "14%", "Oct 11, 4:59:46 AM PT"),
        [(0.0829999984, "8.3%", "Oct 11, 6:20:28 AM PT", "-5.7 pp"),
         (0.1612595359, "16.1%", "Oct 11, 6:30:12 AM PT", "+2.1 pp"),
         (0.001, "0.1%", "Oct 11, 6:40:33 AM PT", "-13.9 pp")]
    )
    private static let hamilton: Driver = (
        "5229411", "9518453683994039663103190001640433279731056992400699084747973794695685716810", "Lewis Hamilton",
        (0.16, "16%", "Oct 11, 4:59:19 AM PT"),
        [(0.002, "0.2%", "Oct 11, 6:19:40 AM PT", "-15.8 pp"),
         (0.002, "0.2%", "Oct 11, 6:30:03 AM PT", "-15.8 pp"),
         nil]
    )

    /// The owner's displayed order — not the catalogue's (Verstappen, Hamilton, Leclerc).
    private static let drivers = [verstappen, leclerc, hamilton]

    /// ARCHIVED hostile control: Hamilton's last captured trade before lap 58, more than five minutes old.
    private static let hamiltonStale = (p: 0.001, figure: "0.1%", clock: "Oct 11, 6:35:12 AM PT")

    private static let tradeSource = "Polymarket trade"
    private static let beforeLabel = "Pre-race win"
    private static let recordedLabel = "Recorded win"
    private static let beforeUnavailable = "Not recorded"
    private static let recordedUnavailable = "No recent probability"
    private static let offScale = "Above this scale"
    private static let unavailable = "Driver unavailable in this update"
    private static let openHint = "Opens this driver's recorded win history"

    private static func ref(_ market: String, _ outcome: String, scope: String = FieldExpectationsCard10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: outcome)
    }

    private static func ref(_ driver: Driver) -> FieldChooserOriginalRef10868 {
        ref(driver.market, driver.outcome)
    }

    private static func slot(_ driver: Driver) -> FieldFinishSlot10868 {
        FieldFinishSlot10868(ref: ref(driver), name: driver.name)
    }

    private static func beforeReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: beforeLabel, value: .recorded(text: driver.before.figure, detail: "\(driver.before.clock) · \(tradeSource)"))
    }

    /// The driver's own recorded reading at a report, or the owner's absence
    /// words when it has no qualifying quote there.
    private static func recordedReading(_ driver: Driver, _ stage: Int) -> FieldChooserReading10868 {
        guard let recorded = driver.recorded[stage] else {
            return FieldChooserReading10868(label: recordedLabel, value: .missing(recordedUnavailable))
        }
        return FieldChooserReading10868(label: recordedLabel, value: .recorded(text: recorded.figure, detail: "\(recorded.clock) · \(tradeSource)"))
    }

    private static func record(_ driver: Driver, _ stage: Int, plan: FieldChooserDisplayPlan10868? = nil, name: String? = nil) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(driver), name: name ?? driver.name,
            plan: plan ?? .comparison(before: beforeReading(driver), later: recordedReading(driver, stage)),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "Race winner"
        )
    }

    /// The owner's association at a report: no later observation, movement or
    /// key where there is no qualifying quote.
    private static func pair(_ driver: Driver, _ stage: Int, recorded: Double? = nil, ref: FieldChooserOriginalRef10868? = nil) -> FieldMovementPair10868 {
        let later = driver.recorded[stage]
        return FieldMovementPair10868(
            ref: ref ?? Self.ref(driver),
            before: FieldMovementObservation10868(probability: driver.before.p, reading: beforeReading(driver)),
            later: later.map { FieldMovementObservation10868(probability: recorded ?? $0.p, reading: recordedReading(driver, stage)) },
            movement: later?.movement,
            observation: later.map { _ in "constructed:\(driver.market):lap\(laps[stage])" }
        )
    }

    /// ARCHIVED canonical catalogue, in its own order: market, Yes token, name
    /// and the pre-race figure CONSTRUCTED from its archived baseline (nil: no
    /// baseline in the capture).
    private static let canonical: [(market: String, outcome: String, name: String, before: String?)] = [
        ("5229406", "105026689771335810478914327541724319323338915766526076386906176141135574302746", "Max Verstappen", "65%"),
        ("5229411", "9518453683994039663103190001640433279731056992400699084747973794695685716810", "Lewis Hamilton", "16%"),
        ("5229402", "92443082174901362958213182894863948289679800011664028904195269564952495193793", "Charles Leclerc", "14%"),
        ("5229405", "5696133373196488147875236821860681766749634665413742392928884679633318673226", "Kimi Antonelli", "8%"),
        ("5229404", "50434279802004157692776355100568844573677746234993201217816404234694902233906", "Lando Norris", "2.5%"),
        ("5229413", "92166685409924243611608345305761239418833259618841446683252071008964493612883", "Oscar Piastri", "1.3%"),
        ("5229414", "56718796378955317111468916340265911522929583552165139147928588786823433132601", "George Russell", "1%"),
        ("5229408", "112114148297929537173847598641186061156229360765636408243334062234430064452907", "Carlos Sainz Jr.", "0.1%"),
        ("5229416", "5925247658760843939848257679933962433517180533220416892662406179964839647949", "Isack Hadjar", "0.2%"),
        ("5229398", "24946613243542045093782896030972508052414682034023350754030313581675845916465", "Fernando Alonso", nil),
        ("5229417", "59218091277618579146661875012717821529527136170610280346022356243553006480870", "Liam Lawson", "0.1%"),
        ("5229409", "46633357118097927706875836765976613273002880284113105333660319153040915921433", "Nico Hulkenberg", nil),
        ("5229410", "37377009617262886055248856685172953678066728775153467706615477067585995032236", "Valtteri Bottas", nil),
        ("5229412", "22577247696951783128672169989438357120216379084843314121733136822205330394386", "Oliver Bearman", nil),
        ("5229415", "35806167495708067688142660894515436986537444155410197985851888007006540375369", "Arvid Lindblad", nil),
        ("5229418", "17728978960408046070104397306363646944957497115347892906141065161648077901163", "Lance Stroll", nil),
        ("5229419", "80737513999194638178280916250352918609409177325807266190011527655594912137851", "Yuki Tsunoda", nil),
        ("5229399", "20899351361659882916278870698966147459616666433222997076649183873101393641787", "Alexander Albon", nil),
        ("5229400", "2835735619366113132331629458875618026032260678708439186410341002678206064734", "Gabriel Bortoleto", nil),
        ("5229401", "83652434777062733522317823357052014621993834306632156362686898553393933523458", "Sergio Perez", nil),
        ("5229403", "110900142078134549566830658584183223162291771163731239731531646173931267218149", "Esteban Ocon", nil),
        ("5229407", "4367879003640045686956388825375902266684763445371199130205596602619739253591", "Franco Colapinto", nil),
        ("5229397", "28558391061191296576456870322949545965070312914289181555918414954825561771030", "Pierre Gasly", nil),
        ("5229633", "110857599143644098992681976807171712355534104947335334189871164576023031815555", "Max Verstappen", "82%"),
        ("5229629", "81777712267167882804825483696208495691212603231475789493999361725169140070707", "Charles Leclerc", "66.7%"),
        ("5229638", "107223488373792995670853625575479347904333591818058137730381400388579385546848", "Lewis Hamilton", "61%"),
        ("5229632", "93588786206279515298378425874328319850883491696258124247716491516547375534226", "Kimi Antonelli", "48%"),
        ("5229631", "91266558960626318800007488387086012785670848799467791981959112065990484864616", "Lando Norris", "29%"),
        ("5229640", "91254622187005296521266595966212220061366684245037347501894715001919789190753", "Oscar Piastri", "17%"),
        ("5229641", "48577678514819085078699880361241457992337880684158047380851450932928459872200", "George Russell", "6.4%"),
        ("5229646", "20389784775884582247749385164360943880067183172628624763938264759036675697715", "Yuki Tsunoda", nil),
        ("5229643", "73022736280294057069609534442862001943197948167325502370815577406169725034775", "Isack Hadjar", "2.1%"),
        ("5229624", "87453145948323530683093142170131029583090664604716403936211065150093975501602", "Pierre Gasly", "1.7%"),
        ("5229644", "33230546474917362926564085275893645857309224237479558353480796418752326055304", "Liam Lawson", "1.8%"),
        ("5229642", "74418053695910050098251154274261102238652619962310301587320294136005596880377", "Arvid Lindblad", nil),
        ("5229625", "18387701778833574956754249887029772709271827126644156983285721399815810792992", "Fernando Alonso", nil),
        ("5229634", "96209521069947352832106981216115838872905539746697545272969446534824159185351", "Franco Colapinto", nil),
        ("5229627", "5536126596058197620947728468486185325150227529245357066692180534751937918211", "Gabriel Bortoleto", nil),
        ("5229635", "21099583028461586672480695290502304110814989010954493894314247689103698679827", "Carlos Sainz Jr.", nil),
        ("5229630", "107579886745075038202250809930504945630616058165883684791018285923144296900320", "Esteban Ocon", nil),
        ("5229637", "70829314418231113229603197020787104655220492519845789616173317634590446065261", "Valtteri Bottas", nil),
        ("5229626", "36958804519639427780282363944661840022193973378862741937678054521049286386807", "Alexander Albon", nil),
        ("5229628", "38920286751886432926911405748215593390993793890929458803986070911095534135866", "Sergio Perez", nil),
        ("5229645", "99035375931778084321615410336433575315218165292425804029498168493607815844379", "Lance Stroll", nil),
        ("5229636", "40753676215478901061354185338534230390231681673691988568754789894877991728635", "Nico Hulkenberg", nil),
        ("5229639", "38393213436151514371775514758695461422541031352103503278188888358162116834906", "Oliver Bearman", nil),
        ("5229621", "33331488134321289504801551659522059050212493202921720814700311861082309692009", "Hamilton — Hamilton vs Piastri", nil),
        ("5229612", "7090122560978114151159241097823824193070045048886498702882654777211320166186", "Leclerc — Leclerc vs Russell", nil),
        ("5229617", "4068713068528441296831042056180611328829965381921185174724790408885477085376", "Norris — Norris vs Russell", nil),
        ("5229600", "110909128388621583528027995078471646758296891348314740700292566482823861330730", "Alonso — Alonso vs Stroll", "75%"),
        ("5229604", "30828121593085071903092865373527569539214466840198501035754721592064994702046", "Leclerc — Leclerc vs Hamilton", nil),
        ("5229618", "24814557986804912717525396491551950567731074765190854754056431039942873350501", "Verstappen — Verstappen vs Hamilton", nil),
        ("5229488", "2591374099559395253718883338821225955484795878731663629478621088184458436077", "Max Verstappen", "35%"),
        ("5229493", "26128000172307458556562604682667588959839117017600094179451615450544110291374", "Lewis Hamilton", "19%"),
        ("5229484", "113074849230542221111579369802690109874785517423609665045620204211923938532132", "Charles Leclerc", "15.9%"),
        ("5229496", "69091165673113707821952123449217252259896209513255365069454973665287428858566", "George Russell", "10.9%"),
        ("5229486", "71566812110811182468394622972187711783186293932959978471601123622936149006437", "Lando Norris", "4.9%"),
        ("5229487", "28225730157221911414837039362281622918871472023499900047141665660095870686215", "Kimi Antonelli", "13.7%"),
        ("5229498", "103483603311016169319312114776012863628659744762203324695647183613843329932112", "Isack Hadjar", "5.7%"),
        ("5229495", "113870944931080893581151995561608716268501303475993539576096255854502955492276", "Oscar Piastri", "3.9%"),
        ("5229489", "70884389017472998068956496869243231034693127519617203467418865835880820482785", "Franco Colapinto", "0.1%"),
        ("5229500", "36969303612488996956507685417579522699141402648309540215688732939831194740051", "Lance Stroll", "1.5%"),
        ("5229483", "22167621134500002236758899645184473355570659819263985906614787813786691721030", "Sergio Perez", "1.5%"),
        ("5229481", "82841373926297244567961403070618059268118839274372150642644645777215454102840", "Alexander Albon", "0.1%"),
        ("5229492", "50033331166900902238496754075390446021588636997182535677811844195072697881149", "Valtteri Bottas", "1.5%"),
        ("5229479", "63270863974452993271524558641066072795614556815649198640620203389325503101307", "Pierre Gasly", "0.1%"),
        ("5229480", "76147060615984389286618572057004607834846979634815560653181983737717442789749", "Fernando Alonso", "0.1%"),
        ("5229485", "52260232229041890478485638214731562331576098956208366313921603249471215791478", "Esteban Ocon", "0.1%"),
        ("5229491", "109578030417969707247021105786855642324572377718130068164229332475006938294977", "Nico Hulkenberg", "0.1%"),
        ("5229497", "61734884068413260382961879435677743258460901995938169786243728043635825118834", "Arvid Lindblad", "0.1%"),
        ("5229499", "75065405456029042574706141909485482536573163465452073348782299937074328910578", "Liam Lawson", "0.1%"),
        ("5229494", "3573637962077248432080539224215115931395302546255227719914533046680829117401", "Oliver Bearman", "0.1%"),
        ("5229490", "19530433398265004109975999830689410930998548542652494070320878237863685366147", "Carlos Sainz Jr.", "0.1%"),
        ("5229501", "22290850904385371225730409519828833030822513237562163307339926592219044659462", "Yuki Tsunoda", "1%"),
        ("5229482", "98309314565714537847497666396177854204578598906954404335647963267440860619564", "Gabriel Bortoleto", "0.1%"),
    ]

    /// Every canonical original: the three displayed drivers at this report,
    /// every other one with its own pre-race reading or absence words.
    private static func catalogue(_ stage: Int) -> [FieldChooserOriginal10868] {
        canonical.map { entry in
            if let driver = drivers.first(where: { $0.market == entry.market && $0.outcome == entry.outcome }) {
                return record(driver, stage)
            }
            let value = entry.before.map { FieldChooserValue10868.recorded(text: $0, detail: "constructed clock · \(tradeSource)") }
                ?? .missing(beforeUnavailable)
            return FieldChooserOriginal10868(
                ref: ref(entry.market, entry.outcome), name: entry.name,
                plan: .single(FieldChooserReading10868(label: beforeLabel, value: value)),
                preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
                movement: nil, clock: nil, result: nil, browseStatus: "Canonical original"
            )
        }
    }

    /// One catalogue with the driver's record replaced.
    private static func catalogue(_ stage: Int, replacing driver: Driver, with record: FieldChooserOriginal10868) -> [FieldChooserOriginal10868] {
        catalogue(stage).map { $0.ref == ref(driver) ? record : $0 }
    }

    private static let scale = FieldOutlookScale10868(
        ceiling: 1,
        ticks: [FieldOutlookTick10868(probability: 0, label: "0%"),
                FieldOutlookTick10868(probability: 0.5, label: "50%"),
                FieldOutlookTick10868(probability: 1, label: "100%")],
        words: "Win probability · 0% to 100%"
    )

    private static let copy = FieldExpectationsCopy10868(
        eyebrow: "Pre-race → recorded chance",
        title: "How expectations shifted",
        context: "Recorded at different times",
        key: "Hollow = pre-race · solid = recorded",
        graphicLabel: "Pre-race and recorded win chances on one 0 to 100 percent scale",
        beforeLabel: beforeLabel,
        recordedLabel: recordedLabel,
        beforeUnavailable: beforeUnavailable,
        recordedUnavailable: recordedUnavailable,
        offScale: offScale,
        openLabel: "Win history",
        openHint: openHint
    )

    private static func input(
        _ stage: Int = 1,
        catalogue: [FieldChooserOriginal10868]? = nil,
        displayed: [FieldFinishSlot10868]? = nil,
        pairs: [FieldMovementPair10868]? = nil,
        scale: FieldOutlookScale10868 = FieldExpectationsCard10868Tests.scale,
        phase: FieldOutlookPhase10868 = .during
    ) -> FieldExpectationsInput10868 {
        FieldExpectationsInput10868(
            scope: scope,
            catalogue: catalogue ?? Self.catalogue(stage),
            displayed: displayed ?? drivers.map { slot($0) },
            pairs: pairs ?? drivers.map { pair($0, stage) },
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: unavailable
        )
    }

    private static func model(_ input: FieldExpectationsInput10868 = FieldExpectationsCard10868Tests.input()) -> FieldExpectationsModel10868 {
        FieldExpectationsModel10868(input)
    }

    private static func row(_ model: FieldExpectationsModel10868, _ driver: Driver) -> FieldExpectationsRow10868? {
        model.rows.first { $0.slot.ref == ref(driver) }
    }

    /// Every line one row shows or speaks, from the same helpers the view calls.
    private static func rowLines(_ model: FieldExpectationsModel10868, _ row: FieldExpectationsRow10868) -> [String] {
        var lines = [row.resolution.original?.name ?? FieldMovementModel10868.readable(row.slot.name)].compactMap { $0 }
        for endpoint in model.readouts(row) {
            lines += [FieldChaseModel10868.label(endpoint), FieldChaseModel10868.figure(endpoint),
                      FieldChaseModel10868.words(endpoint), FieldChaseModel10868.detail(endpoint)].compactMap { $0 }
        }
        lines += [model.movementWords(row), model.stateWords(row)].compactMap { $0 }
        lines.append(model.rowSummary(row))
        let opening = model.openAction(row, canOpen: true)
        if opening != nil { lines += [model.input.copy.openLabel, model.hint(opening)] }
        return lines
    }

    /// Every line the card shows or speaks.
    private static func everyLine(_ model: FieldExpectationsModel10868) -> [String] {
        guard model.isShown else { return [] }
        var lines = [model.eyebrow, model.input.copy.title, model.context, model.key, model.input.copy.graphicLabel].compactMap { $0 }
        if model.showsTracks { lines += [model.input.scale.words] + model.ticks.map(\.label) }
        for row in model.rows { lines += rowLines(model, row) }
        return lines
    }

    private static func raw(_ model: FieldExpectationsModel10868, _ driver: Driver) -> [Double?] {
        let pair = model.movement.pair(for: ref(driver))
        return [pair?.before?.probability, pair?.later?.probability]
    }

    /// The plan the track Canvas draws on a CONSTRUCTED 343 × 20 pt track with a
    /// 14 pt hollow mark (inset 8, so x = 8 + 327 × fraction).
    private static func track(_ model: FieldExpectationsModel10868, _ row: FieldExpectationsRow10868,
                              width: CGFloat = 343, height: CGFloat = 20, mark: CGFloat = 14) -> FieldExpectationsTrackPlan10868? {
        FieldExpectationsGeometry10868.trackPlan(
            before: row.before.fraction, recorded: row.recorded.fraction, ticks: model.ticks.map(\.fraction),
            in: CGSize(width: width, height: height), markDiameter: mark, lineWidth: 3)
    }

    private static let bothWithheld: [FieldMovementEndpoint10868] = [
        .unavailable(label: beforeLabel, words: beforeUnavailable),
        .unavailable(label: recordedLabel, words: recordedUnavailable),
    ]

    // MARK: Three drivers at three reports

    func testThreeDriversAtThreeReportsKeepTheirOwnValuesClocksAndIdentity() {
        for stage in 0..<3 {
            let model = Self.model(Self.input(stage))
            XCTAssertTrue(model.isShown)
            XCTAssertEqual(model.rows.map(\.slot.ref), Self.drivers.map { Self.ref($0) }, "lap \(Self.laps[stage])")
            for driver in Self.drivers {
                let label = "\(driver.name) lap \(Self.laps[stage])"
                guard let row = Self.row(model, driver) else { XCTFail(label); continue }
                XCTAssertEqual(row.resolution.original?.ref, Self.ref(driver), label)
                XCTAssertEqual(row.resolution.original?.name, driver.name, label)

                // Both own chances, labelled, at the same rank, each with its own clock.
                let readouts = model.readouts(row)
                XCTAssertEqual(readouts.map(FieldChaseModel10868.label), [Self.beforeLabel, Self.recordedLabel], label)
                XCTAssertEqual(FieldChaseModel10868.figure(readouts[0]), driver.before.figure, label)
                XCTAssertEqual(FieldChaseModel10868.detail(readouts[0]), "\(driver.before.clock) · Polymarket trade", label)
                XCTAssertEqual(row.before, .value(probability: driver.before.p, fraction: driver.before.p), label)
                if let recorded = driver.recorded[stage] {
                    XCTAssertEqual(FieldChaseModel10868.figure(readouts[1]), recorded.figure, label)
                    XCTAssertEqual(FieldChaseModel10868.detail(readouts[1]), "\(recorded.clock) · Polymarket trade", label)
                    XCTAssertEqual(row.recorded, .value(probability: recorded.p, fraction: recorded.p), label)
                    XCTAssertEqual(model.movementWords(row), recorded.movement, label)
                    XCTAssertEqual(Self.raw(model, driver), [driver.before.p, recorded.p], label)
                    XCTAssertNotEqual(recorded.clock, driver.before.clock, label)
                } else {
                    // Hamilton at lap 58: no qualifying quote — the owner's words, no mark, no movement.
                    XCTAssertEqual(readouts[1], .reading(FieldChooserReading10868(label: Self.recordedLabel, value: .missing(Self.recordedUnavailable))), label)
                    XCTAssertEqual(row.recorded, .unavailable, label)
                    XCTAssertNil(model.movementWords(row), label)
                    XCTAssertEqual(Self.raw(model, driver), [driver.before.p, nil], label)
                }
                XCTAssertNil(model.stateWords(row), label)

                // A lap report's publication time is never a trade clock.
                let lines = Self.rowLines(model, row)
                for clock in Self.reportClocks {
                    XCTAssertFalse(lines.contains { $0.contains(clock) }, "\(label) \(clock)")
                }
            }
        }
        XCTAssertNil(Self.hamilton.recorded[2])
        XCTAssertEqual(Self.drivers.compactMap { $0.recorded[2] }.count, 2)
    }

    // MARK: The canonical catalogue

    func testEveryCanonicalOriginalStaysAndOnlyTheOwnersThreeAreShown() {
        let model = Self.model()
        let catalogue = Self.catalogue(1)
        XCTAssertEqual(catalogue.count, 75)
        XCTAssertEqual(Set(catalogue.map(\.ref)).count, 75)
        XCTAssertEqual(model.input.catalogue, catalogue)

        // Every canonical original resolves to itself exactly: none filtered, capped or merged.
        for record in catalogue {
            XCTAssertEqual(model.field.resolve(record.ref), .original(record), record.name)
        }

        // Only the owner's three refs are rows, in the owner's order — not the catalogue's.
        XCTAssertEqual(model.rows.count, 3)
        XCTAssertEqual(model.rows.compactMap { $0.resolution.original?.name }, ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])
        XCTAssertEqual(catalogue.prefix(3).map(\.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc"])

        // A name is not an identity: Verstappen's podium and fastest-lap contracts
        // stay separate originals, resolvable and not shown.
        let namesakes = Self.canonical.filter { $0.name == Self.verstappen.name }
        XCTAssertEqual(namesakes.map { $0.market }, ["5229406", "5229633", "5229488"])
        for entry in namesakes.dropFirst() {
            let other = Self.ref(entry.market, entry.outcome)
            XCTAssertNotEqual(other, Self.ref(Self.verstappen))
            XCTAssertNotNil(model.field.resolve(other).original)
            XCTAssertFalse(model.rows.contains { $0.slot.ref == other })
        }

        // A different owner selection of three changes the rows, never the catalogue.
        let others = Array(catalogue[3...5])
        let elsewhere = Self.model(Self.input(displayed: others.map { FieldFinishSlot10868(ref: $0.ref, name: $0.name) }))
        XCTAssertEqual(elsewhere.rows.compactMap { $0.resolution.original?.ref }, others.map(\.ref))
        for record in catalogue {
            XCTAssertEqual(elsewhere.field.resolve(record.ref), .original(record), record.name)
        }
    }

    // MARK: Independence

    func testChancesAreNeverNormalizedComplementedOrPutOnASharedClock() {
        // The shown raw values sum past 1 and stay exactly as they are.
        let sums = (0..<3).map { stage in Self.drivers.compactMap { $0.recorded[stage]?.p }.reduce(0, +) }
        XCTAssertGreaterThan(sums[0], 1)
        XCTAssertGreaterThan(sums[1], 1)
        for stage in 0..<3 {
            let model = Self.model(Self.input(stage))
            for driver in Self.drivers {
                XCTAssertEqual(Self.raw(model, driver), [driver.before.p, driver.recorded[stage]?.p], driver.name)
                XCTAssertEqual(Self.row(model, driver)?.recorded.fraction, driver.recorded[stage]?.p, driver.name)
            }
            // Each driver's recorded clock is its own.
            let clocks = Self.drivers.compactMap { $0.recorded[stage]?.clock }
            XCTAssertEqual(Set(clocks).count, clocks.count)
        }

        // Leclerc's chance collapsed to 0.001 at lap 58 while his reported gap
        // improved: nothing here makes the two agree.
        let lap58 = Self.model(Self.input(2))
        XCTAssertEqual(Self.row(lap58, Self.leclerc)?.recorded, .value(probability: 0.001, fraction: 0.001))
        XCTAssertEqual(Self.row(lap58, Self.leclerc).flatMap(lap58.movementWords), "-13.9 pp")

        // A CONSTRUCTED independent No for Leclerc's market: only its own association counts.
        let noRef = Self.ref(Self.leclerc.market, "constructed-no-token:5229402")
        let noReading = FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: "86%", detail: "constructed"))
        let no = FieldChooserOriginal10868(
            ref: noRef, name: "Charles Leclerc · No", plan: .single(noReading),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "Constructed control")
        let untied = Self.model(Self.input(catalogue: Self.catalogue(1) + [no], displayed: [FieldFinishSlot10868(ref: noRef, name: no.name)]))
        guard let noRow = untied.rows.first else { return XCTFail("No row") }
        XCTAssertEqual(untied.readouts(noRow), Self.bothWithheld)
        XCTAssertEqual(noRow.before, .unavailable)
        XCTAssertEqual(noRow.recorded, .unavailable)
        XCTAssertFalse(untied.showsTrack(noRow))
        for complement in ["86%", "83.9%", "14%", "16.1%"] {
            XCTAssertFalse(Self.rowLines(untied, noRow).contains { $0.contains(complement) }, complement)
        }

        // Changing one driver's association leaves its neighbours exactly as they were.
        let plain = Self.model()
        var pairs = Self.drivers.map { Self.pair($0, 1) }
        pairs[1] = Self.pair(Self.leclerc, 1, recorded: .nan)
        let changed = Self.model(Self.input(pairs: pairs))
        XCTAssertEqual(Self.row(changed, Self.verstappen), Self.row(plain, Self.verstappen))
        XCTAssertEqual(Self.row(changed, Self.hamilton), Self.row(plain, Self.hamilton))
        XCTAssertNotEqual(Self.row(changed, Self.leclerc), Self.row(plain, Self.leclerc))
    }

    // MARK: Hamilton at lap 58

    func testHamiltonAtLap58KeepsHisBaselineWithNoRecentProbabilityAndNoLaterMark() {
        let model = Self.model(Self.input(2))
        guard let row = Self.row(model, Self.hamilton) else { return XCTFail("Hamilton") }
        let words = FieldChooserReading10868(label: Self.recordedLabel, value: .missing(Self.recordedUnavailable))
        XCTAssertEqual(model.readouts(row), [.reading(Self.beforeReading(Self.hamilton)), .reading(words)])
        XCTAssertEqual(row.before, .value(probability: 0.16, fraction: 0.16))
        XCTAssertEqual(row.recorded, .unavailable)
        XCTAssertNil(model.movementWords(row))
        XCTAssertTrue(model.showsTrack(row))
        guard let plan = Self.track(model, row) else { return XCTFail("plan") }
        XCTAssertEqual(plan.before?.midX ?? -1, 8 + 327 * 0.16, accuracy: 1e-9)
        XCTAssertNil(plan.recorded)
        XCTAssertNil(plan.connector)
        XCTAssertEqual(model.rowSummary(row), "Pre-race win: 16%, Oct 11, 4:59:19 AM PT · Polymarket trade. Recorded win: No recent probability")

        // CONSTRUCTED hostile owner input: the stale 0.001 trade carried as a
        // later observation with movement words and a key. It ties nothing, so
        // nothing of it shows.
        let staleReading = FieldChooserReading10868(
            label: Self.recordedLabel, value: .recorded(text: Self.hamiltonStale.figure, detail: "\(Self.hamiltonStale.clock) · Polymarket trade"))
        var pairs = Self.drivers.map { Self.pair($0, 2) }
        pairs[2] = FieldMovementPair10868(
            ref: Self.ref(Self.hamilton), before: pairs[2].before,
            later: FieldMovementObservation10868(probability: Self.hamiltonStale.p, reading: staleReading),
            movement: "-15.9 pp", observation: "constructed:stale")
        let hostile = Self.model(Self.input(2, pairs: pairs))
        guard let hostileRow = Self.row(hostile, Self.hamilton) else { return XCTFail("hostile") }
        XCTAssertEqual(hostileRow, row)
        XCTAssertNil(hostile.movementWords(hostileRow))
        XCTAssertEqual(hostile.openAction(hostileRow, canOpen: true), FieldMovementOpen10868(ref: Self.ref(Self.hamilton), observation: nil))
        let lines = Self.rowLines(hostile, hostileRow)
        for leak in ["0.1%", "6:35:12", "-15.9", "constructed:stale"] {
            XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
        }

        // The owner's single plan says the same with the copy's words.
        let single = Self.model(Self.input(2, catalogue: Self.catalogue(2, replacing: Self.hamilton,
            with: Self.record(Self.hamilton, 2, plan: .single(Self.beforeReading(Self.hamilton))))))
        guard let singleRow = Self.row(single, Self.hamilton) else { return XCTFail("single") }
        XCTAssertEqual(single.readouts(singleRow), [.reading(Self.beforeReading(Self.hamilton)),
                                                    .unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)])
        XCTAssertEqual(singleRow.before, row.before)
        XCTAssertNil(Self.track(single, singleRow)?.recorded)

        // His neighbours at lap 58 keep both of their own marks and connectors.
        for driver in [Self.verstappen, Self.leclerc] {
            guard let neighbour = Self.row(model, driver), let plan = Self.track(model, neighbour) else { XCTFail(driver.name); continue }
            XCTAssertNotNil(plan.before, driver.name)
            XCTAssertNotNil(plan.recorded, driver.name)
            XCTAssertNotNil(plan.connector, driver.name)
        }
    }

    // MARK: Failed or withdrawn recorded input

    func testAFailedOrWithdrawnRecordedInputSaysNoRecentProbabilityAndKeepsEveryOtherEndpoint() {
        let plain = Self.model()
        let keptBefore = FieldMovementEndpoint10868.reading(Self.beforeReading(Self.leclerc))
        let withheld = FieldMovementEndpoint10868.unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)
        let before = Self.pair(Self.leclerc, 1).before

        // An earlier quote left on the association (it does not tie the plan's
        // reading), a withdrawn observation, or a raw value that is not a probability.
        var cases: [(String, FieldMovementPair10868)] = [
            ("stale", FieldMovementPair10868(
                ref: Self.ref(Self.leclerc), before: before,
                later: FieldMovementObservation10868(probability: 0.0829999984, reading: Self.recordedReading(Self.leclerc, 0)),
                movement: "-5.7 pp", observation: "constructed:lap46")),
            ("withdrawn", FieldMovementPair10868(ref: Self.ref(Self.leclerc), before: before, later: nil, movement: "+2.1 pp", observation: "constructed:gone")),
        ]
        for bad in [1.2, -0.1, Double.nan, .infinity] {
            cases.append(("\(bad)", Self.pair(Self.leclerc, 1, recorded: bad)))
        }
        for (label, leclercPair) in cases {
            let model = Self.model(Self.input(pairs: [Self.pair(Self.verstappen, 1), leclercPair, Self.pair(Self.hamilton, 1)]))
            guard let row = Self.row(model, Self.leclerc) else { XCTFail(label); continue }
            XCTAssertEqual(model.readouts(row), [keptBefore, withheld], label)
            XCTAssertEqual(row.before, .value(probability: 0.1399999999, fraction: 0.1399999999), label)
            XCTAssertEqual(row.recorded, .unavailable, label)
            XCTAssertNil(model.movementWords(row), label)
            XCTAssertEqual(model.openAction(row, canOpen: true), FieldMovementOpen10868(ref: Self.ref(Self.leclerc), observation: nil), label)
            let plan = Self.track(model, row)
            XCTAssertNotNil(plan?.before, label)
            XCTAssertNil(plan?.recorded, label)
            XCTAssertNil(plan?.connector, label)
            XCTAssertFalse(Self.rowLines(model, row).contains {
                $0.contains("16.1%") || $0.contains("8.3%") || $0.contains("6:30:12") || $0.contains("6:20:28")
            }, label)
            // The neighbours keep everything.
            XCTAssertEqual(Self.row(model, Self.verstappen), Self.row(plain, Self.verstappen), label)
            XCTAssertEqual(Self.row(model, Self.hamilton), Self.row(plain, Self.hamilton), label)
        }

        // The owner's own words for a failed update are shown as they are.
        let failed = FieldChooserReading10868(label: Self.recordedLabel, value: .missing("No recent probability · update failed"))
        let owner = Self.model(Self.input(
            catalogue: Self.catalogue(1, replacing: Self.leclerc,
                                      with: Self.record(Self.leclerc, 1, plan: .comparison(before: Self.beforeReading(Self.leclerc), later: failed))),
            pairs: [Self.pair(Self.verstappen, 1), cases[1].1, Self.pair(Self.hamilton, 1)]))
        guard let ownerRow = Self.row(owner, Self.leclerc) else { return XCTFail("owner") }
        XCTAssertEqual(owner.readouts(ownerRow), [keptBefore, .reading(failed)])
        XCTAssertEqual(ownerRow.recorded, .unavailable)
        XCTAssertNil(owner.movementWords(ownerRow))
    }

    // MARK: Phase

    func testBeforeAndFinalShowNoExpectationsCardEvenWithThePayloadRidingAlong() {
        for phase in [FieldOutlookPhase10868.before, .final] {
            let model = Self.model(Self.input(2, phase: phase))
            XCTAssertFalse(model.isShown, "\(phase)")
            XCTAssertEqual(model.rows, [], "\(phase)")
            XCTAssertNil(model.eyebrow, "\(phase)")
            XCTAssertNil(model.context, "\(phase)")
            XCTAssertNil(model.key, "\(phase)")
            XCTAssertFalse(model.showsTracks, "\(phase)")
            XCTAssertEqual(model.ticks, [], "\(phase)")
            XCTAssertEqual(Self.everyLine(model), [], "\(phase)")
        }
        XCTAssertTrue(Self.model(Self.input(2)).isShown)
        // The movement rules alone would still give rows at the final; this card's own phase rule hides them.
        XCTAssertFalse(Self.model(Self.input(2, phase: .final)).movement.rows.isEmpty)
    }

    // MARK: No later quote, result or final in an earlier report

    func testAnEarlierReportShowsNoLaterQuoteResultOrFinalData() {
        // CONSTRUCTED hostile records: the archived final win and positions as
        // results, later quotes as previews, movement words and clocks.
        let finals = ["Max Verstappen": "1st · Won", "Charles Leclerc": "2nd · Lost", "Lewis Hamilton": "6th · Lost"]
        let hostile = Self.catalogue(0).map { record -> FieldChooserOriginal10868 in
            guard let driver = Self.drivers.first(where: { Self.ref($0) == record.ref }), let later = driver.recorded[1] else { return record }
            return FieldChooserOriginal10868(
                ref: record.ref, name: record.name, plan: record.plan,
                preview: FieldChooserPreview10868(
                    history: FieldChooserHistory10868(segments: [[FieldChooserPoint10868(time: 1, probability: later.p)]],
                                                      emphasis: FieldChooserPoint10868(time: 1, probability: later.p),
                                                      beforeReference: driver.before.p, gaps: []),
                    absence: "No history in this card"),
                movement: "\(later.movement) vs pre-race",
                clock: later.clock,
                result: FieldChooserResult10868(title: "Final classification", words: finals[driver.name] ?? ""),
                browseStatus: "Finished"
            )
        }
        let lap46 = Self.model(Self.input(0, catalogue: hostile))
        XCTAssertEqual(lap46.rows.map { FieldChaseModel10868.figure(lap46.readouts($0)[1]) }, ["95%", "8.3%", "0.2%"])
        XCTAssertEqual(lap46.rows.map { lap46.movementWords($0) }, ["+30.0 pp", "-5.7 pp", "-15.8 pp"])
        let lines = Self.everyLine(lap46)
        let leaks = ["90.9%", "99.9%", "16.1%", "0.1%", "6:29:48", "6:30:12", "6:30:03", "6:40", "+25.9", "+2.1",
                     "1st", "2nd", "6th", "Won", "Lost", "Final", "vs pre-race"]
        for leak in leaks {
            XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
        }
    }

    // MARK: Identity

    func testForeignBlankRepeatedDuplicateAndWithdrawnSlotsBorrowNothingAndNeighboursKeepTheirs() {
        let plain = Self.model()
        let foreign = FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "constructed:f1:other-race"), name: Self.leclerc.name)
        let withdrawn = FieldFinishSlot10868(ref: Self.ref("5229499", "constructed-withdrawn"), name: "Withdrawn driver")
        let blank = FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, "  "), name: " ")
        let first = Self.slot(Self.verstappen)
        let middle = Self.slot(Self.leclerc)
        let last = Self.slot(Self.hamilton)
        let cases: [(String, FieldExpectationsInput10868)] = [
            ("foreign", Self.input(displayed: [first, foreign, last])),
            ("withdrawn", Self.input(displayed: [first, withdrawn, last])),
            ("blank", Self.input(displayed: [first, blank, last])),
            ("duplicate record", Self.input(catalogue: Self.catalogue(1) + [Self.record(Self.leclerc, 1)])),
            ("repeated slot", Self.input(displayed: [first, middle, middle, last])),
            ("foreign pair only", Self.input(displayed: [first, foreign, last],
                                             pairs: [Self.pair(Self.verstappen, 1), Self.pair(Self.leclerc, 1, ref: foreign.ref), Self.pair(Self.hamilton, 1)])),
        ]
        for (label, input) in cases {
            let model = Self.model(input)
            let unresolved = model.rows.filter { $0.slot.ref != first.ref && $0.slot.ref != last.ref }
            XCTAssertFalse(unresolved.isEmpty, label)
            for row in unresolved {
                XCTAssertNil(row.resolution.original, label)
                XCTAssertEqual(model.readouts(row), [], label)
                XCTAssertEqual(row.before, .unavailable, label)
                XCTAssertEqual(row.recorded, .unavailable, label)
                XCTAssertNil(model.movementWords(row), label)
                XCTAssertEqual(model.stateWords(row), Self.unavailable, label)
                XCTAssertFalse(model.showsTrack(row), label)
                XCTAssertNil(model.openAction(row, canOpen: true), label)
                XCTAssertFalse(Self.rowLines(model, row).contains { $0.contains("14%") || $0.contains("16.1%") }, label)
            }
            // Valid neighbours keep exactly their own rows.
            XCTAssertEqual(Self.row(model, Self.verstappen), Self.row(plain, Self.verstappen), label)
            XCTAssertEqual(Self.row(model, Self.hamilton), Self.row(plain, Self.hamilton), label)
        }

        // The owner's name is kept beside the unavailable words; a blank name is not printed.
        let foreignModel = Self.model(cases[0].1)
        XCTAssertEqual(foreignModel.rowSummary(foreignModel.rows[1]), "Charles Leclerc. \(Self.unavailable)")
        let blankModel = Self.model(cases[2].1)
        XCTAssertEqual(blankModel.rowSummary(blankModel.rows[1]), Self.unavailable)

        // Two identical associations for one driver are none.
        let twice = Self.model(Self.input(pairs: [Self.pair(Self.verstappen, 1), Self.pair(Self.leclerc, 1), Self.pair(Self.leclerc, 1), Self.pair(Self.hamilton, 1)]))
        guard let twiceRow = Self.row(twice, Self.leclerc) else { return XCTFail("twice") }
        XCTAssertEqual(twice.readouts(twiceRow), Self.bothWithheld)
        XCTAssertFalse(twice.showsTrack(twiceRow))

        // Leclerc's readings carried on Verstappen's association are never borrowed by either.
        let borrowed = Self.model(Self.input(pairs: [Self.pair(Self.leclerc, 1, ref: Self.ref(Self.verstappen)), Self.pair(Self.hamilton, 1)]))
        XCTAssertEqual(Self.row(borrowed, Self.verstappen).map(borrowed.readouts), Self.bothWithheld)
        XCTAssertEqual(Self.row(borrowed, Self.leclerc).map(borrowed.readouts), Self.bothWithheld)
        XCTAssertEqual(Self.row(borrowed, Self.hamilton), Self.row(plain, Self.hamilton))
    }

    // MARK: Open

    func testOpenHandsBackTheExactOriginalAndObservationAndNoCallbackIsStatic() {
        let model = Self.model()
        for driver in Self.drivers {
            guard let row = Self.row(model, driver) else { XCTFail(driver.name); continue }
            let opening = model.openAction(row, canOpen: true)
            XCTAssertEqual(opening, FieldMovementOpen10868(ref: Self.ref(driver), observation: "constructed:\(driver.market):lap52"), driver.name)
            XCTAssertEqual(model.hint(opening), Self.openHint, driver.name)
            XCTAssertNil(model.openAction(row, canOpen: false), driver.name)
            XCTAssertEqual(model.hint(model.openAction(row, canOpen: false)), "", driver.name)
        }

        // At lap 58 Hamilton opens his exact original with no observation key: no recorded figure is shown.
        let lap58 = Self.model(Self.input(2))
        XCTAssertEqual(Self.row(lap58, Self.hamilton).flatMap { lap58.openAction($0, canOpen: true) },
                       FieldMovementOpen10868(ref: Self.ref(Self.hamilton), observation: nil))

        // A blank key is none.
        var pairs = Self.drivers.map { Self.pair($0, 1) }
        pairs[0] = FieldMovementPair10868(ref: pairs[0].ref, before: pairs[0].before, later: pairs[0].later, movement: pairs[0].movement, observation: "  ")
        let blankKey = Self.model(Self.input(pairs: pairs))
        XCTAssertEqual(Self.row(blankKey, Self.verstappen).flatMap { blankKey.openAction($0, canOpen: true) },
                       FieldMovementOpen10868(ref: Self.ref(Self.verstappen), observation: nil))

        // Nothing opens for a slot that does not resolve, and no hint is spoken.
        let foreign = Self.model(Self.input(displayed: [FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "elsewhere"), name: Self.leclerc.name)]))
        XCTAssertNil(foreign.rows.first.flatMap { foreign.openAction($0, canOpen: true) })
        XCTAssertFalse(Self.everyLine(foreign).contains(Self.openHint))
    }

    // MARK: One probability coordinate

    func testOneAffineProbabilityCoordinatePlacesZeroInteriorAndOneExactly() {
        let model = Self.model(Self.input(2))
        XCTAssertEqual(model.ticks, [FieldOutlookPlacedTick10868(label: "0%", fraction: 0),
                                     FieldOutlookPlacedTick10868(label: "50%", fraction: 0.5),
                                     FieldOutlookPlacedTick10868(label: "100%", fraction: 1)])

        // Every driver's marks and the ticks share x = 8 + 327 × p on a 343 pt track.
        for driver in Self.drivers {
            guard let row = Self.row(model, driver), let plan = Self.track(model, row) else { XCTFail(driver.name); continue }
            XCTAssertEqual(plan.zeroX, 8, driver.name)
            XCTAssertEqual(plan.ceilingX, 335, driver.name)
            XCTAssertEqual(plan.tickXs, [8, 8, 171.5, 335], driver.name)
            XCTAssertEqual(plan.centerY, 10, driver.name)
            XCTAssertEqual(plan.before?.midX ?? -1, 8 + 327 * CGFloat(driver.before.p), accuracy: 1e-9, driver.name)
            XCTAssertEqual(plan.before?.size, CGSize(width: 14, height: 14), driver.name)
            if let recorded = driver.recorded[2] {
                XCTAssertEqual(plan.recorded?.midX ?? -1, 8 + 327 * CGFloat(recorded.p), accuracy: 1e-9, driver.name)
                XCTAssertEqual(plan.recorded?.size, CGSize(width: 7, height: 7), driver.name)
                XCTAssertEqual(plan.recorded?.midY, plan.before?.midY, driver.name)
                let span = [plan.before?.midX ?? 0, plan.recorded?.midX ?? 0]
                XCTAssertEqual(plan.connector?.minX ?? -1, span.min() ?? -2, accuracy: 1e-9, driver.name)
                XCTAssertEqual(plan.connector?.maxX ?? -1, span.max() ?? -2, accuracy: 1e-9, driver.name)
            }
        }

        // CONSTRUCTED genuine 0% and 100%: whole marks at the exact ends, inset, never moved.
        let edges = FieldExpectationsGeometry10868.trackPlan(before: 0, recorded: 1, ticks: [], in: CGSize(width: 343, height: 20), markDiameter: 14, lineWidth: 3)
        XCTAssertEqual(edges?.before, CGRect(x: 1, y: 3, width: 14, height: 14))
        XCTAssertEqual(edges?.recorded, CGRect(x: 331.5, y: 6.5, width: 7, height: 7))
        XCTAssertEqual(edges?.connector, CGRect(x: 8, y: 8.5, width: 327, height: 3))
        let bounds = CGRect(x: 0, y: 0, width: 343, height: 20)
        for rect in [edges?.before, edges?.recorded].compactMap({ $0 }) {
            XCTAssertTrue(bounds.contains(rect))
        }

        // Through the model: a real 0 tied to its own "0%" is a placed mark at zero, not an absence.
        let zeroReading = FieldChooserReading10868(label: Self.recordedLabel, value: .recorded(text: "0%", detail: "Oct 11, 6:30:12 AM PT · Polymarket trade"))
        var pairs = Self.drivers.map { Self.pair($0, 1) }
        pairs[1] = FieldMovementPair10868(ref: Self.ref(Self.leclerc), before: pairs[1].before,
                                          later: FieldMovementObservation10868(probability: 0, reading: zeroReading),
                                          movement: "-14.0 pp", observation: "constructed:zero")
        let zero = Self.model(Self.input(
            catalogue: Self.catalogue(1, replacing: Self.leclerc,
                                      with: Self.record(Self.leclerc, 1, plan: .comparison(before: Self.beforeReading(Self.leclerc), later: zeroReading))),
            pairs: pairs))
        guard let zeroRow = Self.row(zero, Self.leclerc) else { return XCTFail("zero") }
        XCTAssertEqual(zeroRow.recorded, .value(probability: 0, fraction: 0))
        XCTAssertEqual(FieldChaseModel10868.figure(zero.readouts(zeroRow)[1]), "0%")
        XCTAssertEqual(Self.track(zero, zeroRow)?.recorded?.midX, 8)

        // At common widths and accessibility mark sizes the same rule holds and every mark stays whole.
        for width: CGFloat in [288, 343, 361, 600] {
            for mark: CGFloat in [14, 28] {
                let inset = mark / 2 + 1
                let size = CGSize(width: width, height: mark * 20 / 14)
                guard let plan = FieldExpectationsGeometry10868.trackPlan(before: 0, recorded: 1, ticks: [0.5], in: size, markDiameter: mark, lineWidth: 3) else {
                    XCTFail("\(width)/\(mark)"); continue
                }
                XCTAssertEqual(FieldExpectationsGeometry10868.inset(markDiameter: mark), inset)
                XCTAssertEqual(plan.tickXs, [inset, inset + (width - 2 * inset) / 2], "\(width)/\(mark)")
                XCTAssertEqual(plan.before?.midX, inset, "\(width)/\(mark)")
                XCTAssertEqual(plan.recorded?.midX, width - inset, "\(width)/\(mark)")
                let canvas = CGRect(origin: .zero, size: size)
                for rect in [plan.before, plan.recorded].compactMap({ $0 }) {
                    XCTAssertTrue(canvas.contains(rect), "\(width)/\(mark)")
                }
            }
        }
    }

    // MARK: Equal values

    func testEqualValuesAreConcentricMarksAtOneCoordinateWithNoConnector() {
        // CONSTRUCTED: Leclerc's recorded chance equal to his pre-race chance, tied to its own reading.
        let equalReading = FieldChooserReading10868(label: Self.recordedLabel, value: .recorded(text: "14%", detail: "Oct 11, 6:30:12 AM PT · Polymarket trade"))
        var pairs = Self.drivers.map { Self.pair($0, 1) }
        pairs[1] = FieldMovementPair10868(ref: Self.ref(Self.leclerc), before: pairs[1].before,
                                          later: FieldMovementObservation10868(probability: 0.1399999999, reading: equalReading),
                                          movement: "+0.0 pp", observation: "constructed:equal")
        let model = Self.model(Self.input(
            catalogue: Self.catalogue(1, replacing: Self.leclerc,
                                      with: Self.record(Self.leclerc, 1, plan: .comparison(before: Self.beforeReading(Self.leclerc), later: equalReading))),
            pairs: pairs))
        guard let row = Self.row(model, Self.leclerc), let plan = Self.track(model, row),
              let ring = plan.before, let dot = plan.recorded
        else { return XCTFail("equal") }
        XCTAssertEqual(row.before.fraction, row.recorded.fraction)
        XCTAssertEqual(ring.midX, dot.midX)
        XCTAssertEqual(ring.midY, dot.midY)
        // The filled mark sits inside the hollow ring's 2 pt stroke with a gap:
        // two distinct marks, neither displaced.
        XCTAssertTrue(ring.insetBy(dx: 3, dy: 3).contains(dot))
        XCTAssertLessThan(dot.width, ring.width)
        XCTAssertNil(plan.connector)
        XCTAssertEqual(model.movementWords(row), "+0.0 pp")

        for mark: CGFloat in [14, 20, 28] {
            guard let plan = FieldExpectationsGeometry10868.trackPlan(before: 0.5, recorded: 0.5, ticks: [], in: CGSize(width: 343, height: mark * 2), markDiameter: mark, lineWidth: 3),
                  let ring = plan.before, let dot = plan.recorded
            else { XCTFail("\(mark)"); continue }
            XCTAssertEqual(ring.midX, dot.midX, "\(mark)")
            XCTAssertEqual(ring.midY, dot.midY, "\(mark)")
            XCTAssertTrue(ring.insetBy(dx: 3, dy: 3).contains(dot), "\(mark)")
            XCTAssertNil(plan.connector, "\(mark)")
        }
    }

    // MARK: One endpoint missing

    func testOneMissingEndpointDrawsNoConnectorAndNothingFromZero() {
        // CONSTRUCTED: no pre-race association for Leclerc; his recorded chance stays.
        let noBefore = FieldMovementPair10868(ref: Self.ref(Self.leclerc), before: nil, later: Self.pair(Self.leclerc, 1).later,
                                              movement: "+2.1 pp", observation: "constructed:no-before")
        let model = Self.model(Self.input(pairs: [Self.pair(Self.verstappen, 1), noBefore, Self.pair(Self.hamilton, 1)]))
        guard let row = Self.row(model, Self.leclerc), let plan = Self.track(model, row) else { return XCTFail("no before") }
        XCTAssertEqual(model.readouts(row), [.unavailable(label: Self.beforeLabel, words: Self.beforeUnavailable),
                                             .reading(Self.recordedReading(Self.leclerc, 1))])
        XCTAssertEqual(row.before, .unavailable)
        XCTAssertEqual(row.recorded, .value(probability: 0.1612595359, fraction: 0.1612595359))
        XCTAssertNil(model.movementWords(row))
        XCTAssertNil(plan.before)
        XCTAssertEqual(plan.recorded?.midX ?? -1, 8 + 327 * 0.1612595359, accuracy: 1e-9)
        XCTAssertNil(plan.connector)

        // Whichever side is missing, there is no connector and no mark at zero.
        let cases: [(Double?, Double?)] = [(nil, 0.3), (0.3, nil), (nil, nil)]
        for (before, recorded) in cases {
            let plan = FieldExpectationsGeometry10868.trackPlan(before: before, recorded: recorded, ticks: [], in: CGSize(width: 343, height: 20), markDiameter: 14, lineWidth: 3)
            XCTAssertNil(plan?.connector, "\(String(describing: before))/\(String(describing: recorded))")
            XCTAssertEqual(plan?.before == nil, before == nil)
            XCTAssertEqual(plan?.recorded == nil, recorded == nil)
            for mark in [plan?.before, plan?.recorded].compactMap({ $0 }) {
                XCTAssertEqual(mark.midX, 8 + 327 * 0.3, accuracy: 1e-9)
            }
        }

        // Neither chance tied: the row draws no track at all; the copy's words carry it.
        let none = Self.model(Self.input(pairs: [Self.pair(Self.verstappen, 1), Self.pair(Self.hamilton, 1)]))
        guard let noneRow = Self.row(none, Self.leclerc) else { return XCTFail("none") }
        XCTAssertEqual(none.readouts(noneRow), Self.bothWithheld)
        XCTAssertFalse(none.showsTrack(noneRow))
    }

    // MARK: Off-scale and invalid

    func testInvalidOrOffScaleValuesAreNeverClamped() {
        // CONSTRUCTED 0–50% scale: Verstappen's 65% and 95% are above it.
        let half = FieldOutlookScale10868(
            ceiling: 0.5,
            ticks: [FieldOutlookTick10868(probability: 0, label: "0%"), FieldOutlookTick10868(probability: 0.25, label: "25%"),
                    FieldOutlookTick10868(probability: 0.5, label: "50%")],
            words: "Win probability · 0% to 50%")
        let model = Self.model(Self.input(0, scale: half))
        guard let above = Self.row(model, Self.verstappen), let inside = Self.row(model, Self.leclerc) else { return XCTFail("rows") }
        XCTAssertEqual(above.before, .offScale)
        XCTAssertEqual(above.recorded, .offScale)
        XCTAssertEqual(model.readouts(above).map(FieldChaseModel10868.figure), ["65%", "95%"])
        XCTAssertEqual(model.stateWords(above), Self.offScale)
        XCTAssertEqual(model.movementWords(above), "+30.0 pp")
        XCTAssertTrue(model.showsTrack(above))
        let abovePlan = Self.track(model, above)
        XCTAssertNil(abovePlan?.before)
        XCTAssertNil(abovePlan?.recorded)
        XCTAssertNil(abovePlan?.connector)
        XCTAssertTrue(model.rowSummary(above).hasSuffix("+30.0 pp. \(Self.offScale)"))
        XCTAssertEqual(inside.before.fraction, 0.1399999999 / 0.5)
        XCTAssertEqual(inside.recorded.fraction, 0.0829999984 / 0.5)
        XCTAssertNil(model.stateWords(inside))
        XCTAssertEqual(model.ticks.map(\.fraction), [0, 0.5, 1])

        // One chance above the scale and one on it: only the placed mark, no connector toward the edge.
        let high = FieldChooserReading10868(label: Self.recordedLabel, value: .recorded(text: "70%", detail: "constructed · Polymarket trade"))
        var pairs = Self.drivers.map { Self.pair($0, 0) }
        pairs[2] = FieldMovementPair10868(ref: Self.ref(Self.hamilton), before: pairs[2].before,
                                          later: FieldMovementObservation10868(probability: 0.7, reading: high), movement: "+54.0 pp", observation: nil)
        let mixed = Self.model(Self.input(0, catalogue: Self.catalogue(0, replacing: Self.hamilton,
            with: Self.record(Self.hamilton, 0, plan: .comparison(before: Self.beforeReading(Self.hamilton), later: high))), pairs: pairs, scale: half))
        guard let mixedRow = Self.row(mixed, Self.hamilton), let mixedPlan = Self.track(mixed, mixedRow) else { return XCTFail("mixed") }
        XCTAssertEqual(mixedRow.before, .value(probability: 0.16, fraction: 0.32))
        XCTAssertEqual(mixedRow.recorded, .offScale)
        XCTAssertNotNil(mixedPlan.before)
        XCTAssertNil(mixedPlan.recorded)
        XCTAssertNil(mixedPlan.connector)
        XCTAssertEqual(mixed.stateWords(mixedRow), Self.offScale)
        XCTAssertEqual(FieldChaseModel10868.figure(mixed.readouts(mixedRow)[1]), "70%")

        // An invalid scale, or one with no readable words, draws no track; the figures stay.
        let invalid = [FieldOutlookScale10868(ceiling: 0, ticks: Self.scale.ticks, words: Self.scale.words),
                       FieldOutlookScale10868(ceiling: 1.5, ticks: Self.scale.ticks, words: Self.scale.words),
                       FieldOutlookScale10868(ceiling: .nan, ticks: Self.scale.ticks, words: Self.scale.words),
                       FieldOutlookScale10868(ceiling: 1, ticks: Self.scale.ticks, words: "  ")]
        for (index, scale) in invalid.enumerated() {
            let model = Self.model(Self.input(scale: scale))
            XCTAssertFalse(model.showsTracks, "\(index)")
            XCTAssertEqual(model.ticks, [], "\(index)")
            for driver in Self.drivers {
                guard let row = Self.row(model, driver) else { XCTFail("\(index)"); continue }
                XCTAssertFalse(model.showsTrack(row), "\(index)")
                XCTAssertEqual(model.readouts(row).map(FieldChaseModel10868.figure), [driver.before.figure, driver.recorded[1]?.figure], "\(index)")
                XCTAssertNil(model.stateWords(row), "\(index)")
            }
            XCTAssertFalse(Self.everyLine(model).contains(scale.words), "\(index)")
        }

        // Fractions outside 0...1 are never placed or clamped; a size that cannot be drawn draws nothing.
        for bad in [1.2, -0.1, Double.nan, .infinity] {
            let plan = FieldExpectationsGeometry10868.trackPlan(before: bad, recorded: 0.5, ticks: [bad], in: CGSize(width: 343, height: 20), markDiameter: 14, lineWidth: 3)
            XCTAssertNil(plan?.before, "\(bad)")
            XCTAssertNil(plan?.connector, "\(bad)")
            XCTAssertEqual(plan?.tickXs, [8], "\(bad)")
        }
        let unusable: [(CGSize, CGFloat, CGFloat)] = [
            (CGSize(width: 16, height: 20), 14, 3), (CGSize(width: 343, height: 13), 14, 3),
            (CGSize(width: CGFloat.nan, height: 20), 14, 3), (CGSize(width: CGFloat.infinity, height: 20), 14, 3),
            (CGSize(width: 343, height: 20), 0, 3), (CGSize(width: 343, height: 20), 14, 0),
        ]
        for (size, mark, line) in unusable {
            XCTAssertNil(FieldExpectationsGeometry10868.trackPlan(before: 0.5, recorded: 0.6, ticks: [], in: size, markDiameter: mark, lineWidth: line), "\(size)/\(mark)/\(line)")
        }
    }

    // MARK: Axis labels and readout plans

    func testTheAxisPlacesMeasuredLabelsOnTheTrackInsetAtCommonWidthsAndAccessibilitySizes() {
        let model = Self.model()
        let units = model.ticks.map(\.fraction)
        XCTAssertEqual(units, [0, 0.5, 1])
        func labels(_ width: CGFloat, _ sizes: [CGSize], inset: CGFloat = 8, order: [Double]? = nil) -> [CGRect?] {
            FieldExpectationsGeometry10868.axisLabels(zip(order ?? units, sizes).map { FieldChaseMeasuredTick10868(unit: $0, size: $1) },
                                                      width: width, inset: inset, spacing: 6)
        }
        // CONSTRUCTED caption2 sizes for "0%", "50%", "100%" at a standard size and at AX5.
        let standard = [CGSize(width: 14, height: 13), CGSize(width: 21, height: 13), CGSize(width: 28, height: 13)]
        let large = [CGSize(width: 40, height: 34), CGSize(width: 60, height: 34), CGSize(width: 80, height: 34)]

        // Centred on its mark while that keeps it inside, else slid inward just enough.
        let placed = labels(343, standard)
        XCTAssertEqual(placed, [CGRect(x: 1, y: 0, width: 14, height: 13),
                                CGRect(x: 161, y: 0, width: 21, height: 13),
                                CGRect(x: 315, y: 0, width: 28, height: 13)])

        for width: CGFloat in [288, 343, 361, 600] {
            for (sizes, mark) in [(standard, CGFloat(14)), (large, CGFloat(28))] {
                let label = "\(width)/\(mark)"
                let inset = FieldExpectationsGeometry10868.inset(markDiameter: mark)
                let rects = labels(width, sizes, inset: inset)
                let shown = rects.compactMap { $0 }
                XCTAssertEqual(shown.count, 3, label)
                for rect in shown {
                    XCTAssertGreaterThanOrEqual(rect.minX, 0, label)
                    XCTAssertLessThanOrEqual(rect.maxX, width, label)
                }
                let ordered = shown.sorted { $0.minX < $1.minX }
                for (left, right) in zip(ordered, ordered.dropFirst()) {
                    XCTAssertGreaterThanOrEqual(right.minX, left.maxX + 6, label)
                }
                // The middle label is centred on the very x the track's 50% tick uses.
                let tick = FieldExpectationsGeometry10868.trackPlan(before: nil, recorded: nil, ticks: [0.5], in: CGSize(width: width, height: mark * 2),
                                                                    markDiameter: mark, lineWidth: 3)?.tickXs.last
                XCTAssertEqual(rects[1]?.midX ?? -1, tick ?? -2, accuracy: 1e-9, label)
                XCTAssertEqual(FieldExpectationsGeometry10868.axisHeight(rects), sizes[0].height, label)
            }
        }

        // Crowded: a label with no room beside one already placed is left out, in the owner's order.
        let crowded = Array(repeating: CGSize(width: 130, height: 13), count: 3)
        XCTAssertEqual(labels(288, crowded).map { $0 != nil }, [true, false, true])
        XCTAssertEqual(labels(288, crowded, order: [0.5, 0, 1]).map { $0 != nil }, [true, false, false])

        // A label wider than the axis, or an invalid measurement, gets no place;
        // none placed is zero tall, and the scale words still stay.
        XCTAssertEqual(labels(288, Array(repeating: CGSize(width: 300, height: 13), count: 3)), [nil, nil, nil])
        XCTAssertEqual(labels(343, Array(repeating: CGSize(width: CGFloat.nan, height: 13), count: 3)), [nil, nil, nil])
        XCTAssertEqual(labels(343, Array(repeating: CGSize(width: 14, height: CGFloat.infinity), count: 3)), [nil, nil, nil])
        XCTAssertEqual(FieldExpectationsGeometry10868.axisHeight([nil, nil, nil]), 0)
        XCTAssertTrue(model.showsTracks)
        XCTAssertEqual(model.input.scale.words, "Win probability · 0% to 100%")

        // The axis reports a finite width for every offer.
        for proposed: CGFloat? in [nil, 0, 343, .infinity, .nan] {
            let width = FieldExpectationsGeometry10868.axisWidth(proposed: proposed, labels: standard + [CGSize(width: CGFloat.infinity, height: 13)], inset: 8, spacing: 6)
            XCTAssertTrue(width.isFinite && width >= 0, "\(String(describing: proposed))")
        }
        XCTAssertEqual(FieldExpectationsGeometry10868.axisWidth(proposed: 343, labels: standard, inset: 8, spacing: 6), 343)
        XCTAssertEqual(FieldExpectationsGeometry10868.axisWidth(proposed: nil, labels: standard, inset: 8, spacing: 6), 91)
        XCTAssertEqual(FieldExpectationsGeometry10868.axisWidth(proposed: nil, labels: standard, inset: .infinity, spacing: 6), 0)

        // The heading and both readouts stack at accessibility sizes, side by side otherwise.
        XCTAssertTrue(FieldChaseGeometry10868.stacksReadouts(accessibilitySize: true))
        XCTAssertFalse(FieldChaseGeometry10868.stacksReadouts(accessibilitySize: false))
        XCTAssertEqual(FieldExpectationsGeometry10868.recordedDiameter(markDiameter: 14), 7)
    }

    // MARK: Spoken text

    func testSpokenRowsKeepWholeNamesOwnClocksAndMovementWords() {
        let model = Self.model()
        XCTAssertEqual(model.rows.map(model.rowSummary), [
            "Pre-race win: 65%, Oct 11, 4:59:31 AM PT · Polymarket trade. Recorded win: 90.9%, Oct 11, 6:29:48 AM PT · Polymarket trade. +25.9 pp",
            "Pre-race win: 14%, Oct 11, 4:59:46 AM PT · Polymarket trade. Recorded win: 16.1%, Oct 11, 6:30:12 AM PT · Polymarket trade. +2.1 pp",
            "Pre-race win: 16%, Oct 11, 4:59:19 AM PT · Polymarket trade. Recorded win: 0.2%, Oct 11, 6:30:03 AM PT · Polymarket trade. -15.8 pp",
        ])

        // The card's words are the owner's, verbatim.
        XCTAssertEqual(model.eyebrow, "Pre-race → recorded chance")
        XCTAssertEqual(model.context, "Recorded at different times")
        XCTAssertEqual(model.key, "Hollow = pre-race · solid = recorded")

        // A long full name is kept whole, resolved or not.
        let long = "Charles Marc Hervé Perceval Leclerc (Scuderia Ferrari HP)"
        let whole = Self.model(Self.input(catalogue: Self.catalogue(1, replacing: Self.leclerc, with: Self.record(Self.leclerc, 1, name: long))))
        XCTAssertEqual(Self.row(whole, Self.leclerc)?.resolution.original?.name, long)
        let gone = Self.model(Self.input(displayed: [FieldFinishSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "elsewhere"), name: long)]))
        XCTAssertEqual(gone.rows.first.map(gone.rowSummary), "\(long). \(Self.unavailable)")
    }
}

// MARK: - #10868 field phase headline — "Singapore Grand Prix"

/// The racing-live headline in all three phases — each displayed driver's own
/// pre-race chance; beside it the recorded chance during the race or the
/// reported finish after it — with the owner's heading and race state, on the
/// movement and finish cards' own models.
///
/// ARCHIVED raw values come from the 2026 Singapore Grand Prix, as retained in
/// `shipping-adoption-20261027/FIELD-PHASE-HEADLINE-RETAINED-CASES.json`
/// (sha256 78476122…9c59) and reconciled with the reference
/// `racingLiveCapture.json` / `racingEvidence.json` trade rules: the 75
/// canonical originals with their market and exact selected-outcome token ids
/// (69 Yes outcomes and 6 named head-to-head outcomes); the owner's three
/// displayed winner contracts, each on its own Yes outcome — Max Verstappen
/// (5229406), Charles Leclerc (5229402), Lewis Hamilton (5229411) — with their
/// own pre-race trades
/// (0.6499999935 at 11:59:31Z, 0.1399999999 at 11:59:46Z, 0.16 at 11:59:19Z;
/// verified start 12:00:00Z), which are also the reference's last before-window
/// readings; their own last eligible trade before each lap report (lap 46
/// reported 13:20:49Z, lap 52 at 13:30:26Z, lap 58 at 13:40:53Z, 62 laps):
/// Verstappen 0.95 at 13:19:58Z, 0.909 at 13:29:48Z, 0.999 at 13:40:19Z; Leclerc
/// 0.0829999984 at 13:20:28Z, 0.1612595359 at 13:30:12Z, 0.001 at 13:40:33Z;
/// Hamilton 0.002 at 13:19:40Z, 0.002 at 13:30:03Z and NO qualifying quote at
/// lap 58 (his last captured trade, 0.001 at 13:35:12Z, is a hostile control);
/// the reported gaps (15, 9.1, 9 seconds); and the ESPN final classification
/// (event 600057445, captured 2026-10-12T07:47:00Z): Verstappen 1st, Leclerc
/// 2nd, Hamilton 6th. The last-lap report's publication (13:46:18Z) is not a
/// finish time. Settled 1/0/0 quotes, opening probabilities (0.335, 0.1,
/// 0.105) and contract Won/Lost results are used only as hostile controls the
/// headline must never show.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope
/// string, the compact labels, the key shapes (Verstappen circle, Leclerc
/// diamond, Hamilton square — the approved `RacingLive.tsx` chart's own marks
/// for these three drivers), every label, figure text (prepared with the
/// reference `probabilityLabel.ts`), ordinal, PT clock line (from each sample's
/// own archived time), source word, observation key, phase, eyebrow, title,
/// state copy and progress, the card copy, the other canonical records' plans,
/// the hostile later/final inputs, the No control, and every withdrawn,
/// duplicate, repeated, blank, foreign, zero, invalid and long-name case.
/// Figure widths are CONSTRUCTED measurements: native arithmetic here is not a
/// rendered fit.
final class FieldPhaseHeadline10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Chance = (p: Double, figure: String, clock: String)
    private typealias Driver = (market: String, outcome: String, name: String, compact: String, shape: FieldHeadlineKeyShape10868,
                                before: Chance, recorded: [Chance?], place: String)

    /// The owner's actual moment: before the start, one of the three lap reports, or the final.
    private enum Moment: Equatable {
        case before
        case lap(Int)
        case final

        var phase: FieldOutlookPhase10868 {
            switch self {
            case .before: .before
            case .lap: .during
            case .final: .final
            }
        }
    }

    private static let moments: [Moment] = [.before, .lap(0), .lap(1), .lap(2), .final]

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:f1:singapore-2026:phase-headline"

    /// ARCHIVED lap reports and gaps; PT clocks and gap words CONSTRUCTED from them. Never a trade clock.
    private static let laps = [46, 52, 58]
    private static let reportClocks = ["Oct 11, 6:20:49 AM PT", "Oct 11, 6:30:26 AM PT", "Oct 11, 6:40:53 AM PT"]
    private static let gaps = ["15.0", "9.1", "9.0"]
    /// ARCHIVED last-lap publication, CONSTRUCTED PT: never a finish time.
    private static let lastLapPublished = "6:46:18"

    /// ARCHIVED ids, names, raw values and places; compact labels, figures, PT clocks and ordinals CONSTRUCTED from them;
    /// key shapes are the approved chart's own marks for each driver, carried by the owner with the driver.
    private static let verstappen: Driver = (
        "5229406", "105026689771335810478914327541724319323338915766526076386906176141135574302746", "Max Verstappen", "Verstappen", .circle,
        (0.6499999935, "65%", "Oct 11, 4:59:31 AM PT"),
        [(0.95, "95%", "Oct 11, 6:19:58 AM PT"),
         (0.909, "90.9%", "Oct 11, 6:29:48 AM PT"),
         (0.999, "99.9%", "Oct 11, 6:40:19 AM PT")],
        "1st"
    )
    private static let leclerc: Driver = (
        "5229402", "92443082174901362958213182894863948289679800011664028904195269564952495193793", "Charles Leclerc", "Leclerc", .diamond,
        (0.1399999999, "14%", "Oct 11, 4:59:46 AM PT"),
        [(0.0829999984, "8.3%", "Oct 11, 6:20:28 AM PT"),
         (0.1612595359, "16.1%", "Oct 11, 6:30:12 AM PT"),
         (0.001, "0.1%", "Oct 11, 6:40:33 AM PT")],
        "2nd"
    )
    private static let hamilton: Driver = (
        "5229411", "9518453683994039663103190001640433279731056992400699084747973794695685716810", "Lewis Hamilton", "Hamilton", .square,
        (0.16, "16%", "Oct 11, 4:59:19 AM PT"),
        [(0.002, "0.2%", "Oct 11, 6:19:40 AM PT"),
         (0.002, "0.2%", "Oct 11, 6:30:03 AM PT"),
         nil],
        "6th"
    )

    /// The owner's displayed order — not the catalogue's (Verstappen, Hamilton, Leclerc).
    private static let drivers = [verstappen, leclerc, hamilton]

    /// ARCHIVED hostile control: Hamilton's last captured trade before lap 58, more than five minutes old.
    private static let hamiltonStale: Chance = (0.001, "0.1%", "Oct 11, 6:35:12 AM PT")

    /// ARCHIVED hostile final controls, in the displayed order: settled quote, opening probability, contract result.
    private static let settled: [(p: Double, figure: String)] = [(1.0, "100%"), (0.0, "0%"), (0.0, "0%")]
    private static let opening: [(p: Double, figure: String)] = [(0.335, "33.5%"), (0.1, "10%"), (0.105, "10.5%")]
    private static let results = ["Won", "Lost", "Lost"]

    private static let tradeSource = "Polymarket trade"
    private static let classification = "ESPN classification · captured Oct 12, 12:47 AM PT"
    private static let beforeLabel = "Pre-race win"
    private static let recordedLabel = "Recorded win"
    private static let finishLabel = "Actual finish"
    private static let notRecorded = "Not recorded"
    private static let recordedUnavailable = "No recent probability"
    private static let finishUnavailable = "Finish not reported"
    private static let unavailable = "Driver unavailable in this update"
    private static let aboutLabel = "About this race"
    private static let aboutHint = "Opens how this race was recorded"
    private static let openHint = "Opens this driver's win history"

    private static func ref(_ market: String, _ outcome: String, scope: String = FieldPhaseHeadline10868Tests.scope) -> FieldChooserOriginalRef10868 {
        FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: market, outcomeID: outcome)
    }

    private static func ref(_ driver: Driver) -> FieldChooserOriginalRef10868 {
        ref(driver.market, driver.outcome)
    }

    private static func slot(_ driver: Driver, compact: String? = nil) -> FieldHeadlineSlot10868 {
        FieldHeadlineSlot10868(ref: ref(driver), name: driver.name, compactName: compact ?? driver.compact, keyShape: driver.shape)
    }

    private static func beforeReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: beforeLabel, value: .recorded(text: driver.before.figure, detail: "\(driver.before.clock) · \(tradeSource)"))
    }

    /// The driver's own recorded reading at a report, or the owner's absence
    /// words when it has no qualifying quote there.
    private static func recordedReading(_ driver: Driver, _ stage: Int) -> FieldChooserReading10868 {
        guard let recorded = driver.recorded[stage] else {
            return FieldChooserReading10868(label: recordedLabel, value: .missing(recordedUnavailable))
        }
        return FieldChooserReading10868(label: recordedLabel, value: .recorded(text: recorded.figure, detail: "\(recorded.clock) · \(tradeSource)"))
    }

    private static func finishReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: finishLabel, value: .recorded(text: driver.place, detail: classification))
    }

    /// The owner's plan at a moment: the before reading alone, or beside the recorded reading during the race.
    private static func plan(_ driver: Driver, _ moment: Moment) -> FieldChooserDisplayPlan10868 {
        if case .lap(let stage) = moment {
            return .comparison(before: beforeReading(driver), later: recordedReading(driver, stage))
        }
        return .single(beforeReading(driver))
    }

    private static func record(_ driver: Driver, _ moment: Moment, plan: FieldChooserDisplayPlan10868? = nil, name: String? = nil,
                               result: FieldChooserResult10868? = nil) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(driver), name: name ?? driver.name,
            plan: plan ?? Self.plan(driver, moment),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: result, browseStatus: "Race winner"
        )
    }

    /// The owner's association at a moment: the before observation always; a
    /// later observation and key only at a lap report with a qualifying quote.
    private static func pair(_ driver: Driver, _ moment: Moment, recorded: Double? = nil, ref: FieldChooserOriginalRef10868? = nil) -> FieldMovementPair10868 {
        var later: Chance?
        var stage = 0
        if case .lap(let index) = moment {
            stage = index
            later = driver.recorded[index]
        }
        return FieldMovementPair10868(
            ref: ref ?? Self.ref(driver),
            before: FieldMovementObservation10868(probability: driver.before.p, reading: beforeReading(driver)),
            later: later.map { FieldMovementObservation10868(probability: recorded ?? $0.p, reading: recordedReading(driver, stage)) },
            movement: later.map { _ in "constructed movement words" },
            observation: later.map { _ in "constructed:\(driver.market):lap\(laps[stage])" }
        )
    }

    private static func finish(_ driver: Driver, ref: FieldChooserOriginalRef10868? = nil) -> FieldFinishPlace10868 {
        FieldFinishPlace10868(ref: ref ?? Self.ref(driver), reading: finishReading(driver))
    }

    private static let canonical: [(market: String, outcome: String, name: String, before: String?)] = [
        ("5229406", "105026689771335810478914327541724319323338915766526076386906176141135574302746", "Max Verstappen", "65%"),
        ("5229411", "9518453683994039663103190001640433279731056992400699084747973794695685716810", "Lewis Hamilton", "16%"),
        ("5229402", "92443082174901362958213182894863948289679800011664028904195269564952495193793", "Charles Leclerc", "14%"),
        ("5229405", "5696133373196488147875236821860681766749634665413742392928884679633318673226", "Kimi Antonelli", "8%"),
        ("5229404", "50434279802004157692776355100568844573677746234993201217816404234694902233906", "Lando Norris", "2.5%"),
        ("5229413", "92166685409924243611608345305761239418833259618841446683252071008964493612883", "Oscar Piastri", "1.3%"),
        ("5229414", "56718796378955317111468916340265911522929583552165139147928588786823433132601", "George Russell", "1%"),
        ("5229408", "112114148297929537173847598641186061156229360765636408243334062234430064452907", "Carlos Sainz Jr.", "0.1%"),
        ("5229416", "5925247658760843939848257679933962433517180533220416892662406179964839647949", "Isack Hadjar", "0.2%"),
        ("5229398", "24946613243542045093782896030972508052414682034023350754030313581675845916465", "Fernando Alonso", nil),
        ("5229417", "59218091277618579146661875012717821529527136170610280346022356243553006480870", "Liam Lawson", "0.1%"),
        ("5229409", "46633357118097927706875836765976613273002880284113105333660319153040915921433", "Nico Hulkenberg", nil),
        ("5229410", "37377009617262886055248856685172953678066728775153467706615477067585995032236", "Valtteri Bottas", nil),
        ("5229412", "22577247696951783128672169989438357120216379084843314121733136822205330394386", "Oliver Bearman", nil),
        ("5229415", "35806167495708067688142660894515436986537444155410197985851888007006540375369", "Arvid Lindblad", nil),
        ("5229418", "17728978960408046070104397306363646944957497115347892906141065161648077901163", "Lance Stroll", nil),
        ("5229419", "80737513999194638178280916250352918609409177325807266190011527655594912137851", "Yuki Tsunoda", nil),
        ("5229399", "20899351361659882916278870698966147459616666433222997076649183873101393641787", "Alexander Albon", nil),
        ("5229400", "2835735619366113132331629458875618026032260678708439186410341002678206064734", "Gabriel Bortoleto", nil),
        ("5229401", "83652434777062733522317823357052014621993834306632156362686898553393933523458", "Sergio Perez", nil),
        ("5229403", "110900142078134549566830658584183223162291771163731239731531646173931267218149", "Esteban Ocon", nil),
        ("5229407", "4367879003640045686956388825375902266684763445371199130205596602619739253591", "Franco Colapinto", nil),
        ("5229397", "28558391061191296576456870322949545965070312914289181555918414954825561771030", "Pierre Gasly", nil),
        ("5229633", "110857599143644098992681976807171712355534104947335334189871164576023031815555", "Max Verstappen", "82%"),
        ("5229629", "81777712267167882804825483696208495691212603231475789493999361725169140070707", "Charles Leclerc", "66.7%"),
        ("5229638", "107223488373792995670853625575479347904333591818058137730381400388579385546848", "Lewis Hamilton", "61%"),
        ("5229632", "93588786206279515298378425874328319850883491696258124247716491516547375534226", "Kimi Antonelli", "48%"),
        ("5229631", "91266558960626318800007488387086012785670848799467791981959112065990484864616", "Lando Norris", "29%"),
        ("5229640", "91254622187005296521266595966212220061366684245037347501894715001919789190753", "Oscar Piastri", "17%"),
        ("5229641", "48577678514819085078699880361241457992337880684158047380851450932928459872200", "George Russell", "6.4%"),
        ("5229646", "20389784775884582247749385164360943880067183172628624763938264759036675697715", "Yuki Tsunoda", nil),
        ("5229643", "73022736280294057069609534442862001943197948167325502370815577406169725034775", "Isack Hadjar", "2.1%"),
        ("5229624", "87453145948323530683093142170131029583090664604716403936211065150093975501602", "Pierre Gasly", "1.7%"),
        ("5229644", "33230546474917362926564085275893645857309224237479558353480796418752326055304", "Liam Lawson", "1.8%"),
        ("5229642", "74418053695910050098251154274261102238652619962310301587320294136005596880377", "Arvid Lindblad", nil),
        ("5229625", "18387701778833574956754249887029772709271827126644156983285721399815810792992", "Fernando Alonso", nil),
        ("5229634", "96209521069947352832106981216115838872905539746697545272969446534824159185351", "Franco Colapinto", nil),
        ("5229627", "5536126596058197620947728468486185325150227529245357066692180534751937918211", "Gabriel Bortoleto", nil),
        ("5229635", "21099583028461586672480695290502304110814989010954493894314247689103698679827", "Carlos Sainz Jr.", nil),
        ("5229630", "107579886745075038202250809930504945630616058165883684791018285923144296900320", "Esteban Ocon", nil),
        ("5229637", "70829314418231113229603197020787104655220492519845789616173317634590446065261", "Valtteri Bottas", nil),
        ("5229626", "36958804519639427780282363944661840022193973378862741937678054521049286386807", "Alexander Albon", nil),
        ("5229628", "38920286751886432926911405748215593390993793890929458803986070911095534135866", "Sergio Perez", nil),
        ("5229645", "99035375931778084321615410336433575315218165292425804029498168493607815844379", "Lance Stroll", nil),
        ("5229636", "40753676215478901061354185338534230390231681673691988568754789894877991728635", "Nico Hulkenberg", nil),
        ("5229639", "38393213436151514371775514758695461422541031352103503278188888358162116834906", "Oliver Bearman", nil),
        ("5229621", "33331488134321289504801551659522059050212493202921720814700311861082309692009", "Hamilton — Hamilton vs Piastri", nil),
        ("5229612", "7090122560978114151159241097823824193070045048886498702882654777211320166186", "Leclerc — Leclerc vs Russell", nil),
        ("5229617", "4068713068528441296831042056180611328829965381921185174724790408885477085376", "Norris — Norris vs Russell", nil),
        ("5229600", "110909128388621583528027995078471646758296891348314740700292566482823861330730", "Alonso — Alonso vs Stroll", "75%"),
        ("5229604", "30828121593085071903092865373527569539214466840198501035754721592064994702046", "Leclerc — Leclerc vs Hamilton", nil),
        ("5229618", "24814557986804912717525396491551950567731074765190854754056431039942873350501", "Verstappen — Verstappen vs Hamilton", nil),
        ("5229488", "2591374099559395253718883338821225955484795878731663629478621088184458436077", "Max Verstappen", "35%"),
        ("5229493", "26128000172307458556562604682667588959839117017600094179451615450544110291374", "Lewis Hamilton", "19%"),
        ("5229484", "113074849230542221111579369802690109874785517423609665045620204211923938532132", "Charles Leclerc", "15.9%"),
        ("5229496", "69091165673113707821952123449217252259896209513255365069454973665287428858566", "George Russell", "10.9%"),
        ("5229486", "71566812110811182468394622972187711783186293932959978471601123622936149006437", "Lando Norris", "4.9%"),
        ("5229487", "28225730157221911414837039362281622918871472023499900047141665660095870686215", "Kimi Antonelli", "13.7%"),
        ("5229498", "103483603311016169319312114776012863628659744762203324695647183613843329932112", "Isack Hadjar", "5.7%"),
        ("5229495", "113870944931080893581151995561608716268501303475993539576096255854502955492276", "Oscar Piastri", "3.9%"),
        ("5229489", "70884389017472998068956496869243231034693127519617203467418865835880820482785", "Franco Colapinto", "0.1%"),
        ("5229500", "36969303612488996956507685417579522699141402648309540215688732939831194740051", "Lance Stroll", "1.5%"),
        ("5229483", "22167621134500002236758899645184473355570659819263985906614787813786691721030", "Sergio Perez", "1.5%"),
        ("5229481", "82841373926297244567961403070618059268118839274372150642644645777215454102840", "Alexander Albon", "0.1%"),
        ("5229492", "50033331166900902238496754075390446021588636997182535677811844195072697881149", "Valtteri Bottas", "1.5%"),
        ("5229479", "63270863974452993271524558641066072795614556815649198640620203389325503101307", "Pierre Gasly", "0.1%"),
        ("5229480", "76147060615984389286618572057004607834846979634815560653181983737717442789749", "Fernando Alonso", "0.1%"),
        ("5229485", "52260232229041890478485638214731562331576098956208366313921603249471215791478", "Esteban Ocon", "0.1%"),
        ("5229491", "109578030417969707247021105786855642324572377718130068164229332475006938294977", "Nico Hulkenberg", "0.1%"),
        ("5229497", "61734884068413260382961879435677743258460901995938169786243728043635825118834", "Arvid Lindblad", "0.1%"),
        ("5229499", "75065405456029042574706141909485482536573163465452073348782299937074328910578", "Liam Lawson", "0.1%"),
        ("5229494", "3573637962077248432080539224215115931395302546255227719914533046680829117401", "Oliver Bearman", "0.1%"),
        ("5229490", "19530433398265004109975999830689410930998548542652494070320878237863685366147", "Carlos Sainz Jr.", "0.1%"),
        ("5229501", "22290850904385371225730409519828833030822513237562163307339926592219044659462", "Yuki Tsunoda", "1%"),
        ("5229482", "98309314565714537847497666396177854204578598906954404335647963267440860619564", "Gabriel Bortoleto", "0.1%"),
    ]

    /// Every canonical original: the three displayed drivers at this moment,
    /// every other one with its own pre-race reading or absence words.
    private static func catalogue(_ moment: Moment) -> [FieldChooserOriginal10868] {
        canonical.map { entry in
            if let driver = drivers.first(where: { $0.market == entry.market && $0.outcome == entry.outcome }) {
                return record(driver, moment)
            }
            let value = entry.before.map { FieldChooserValue10868.recorded(text: $0, detail: "constructed clock · \(tradeSource)") }
                ?? .missing(notRecorded)
            return FieldChooserOriginal10868(
                ref: ref(entry.market, entry.outcome), name: entry.name,
                plan: .single(FieldChooserReading10868(label: beforeLabel, value: value)),
                preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
                movement: nil, clock: nil, result: nil, browseStatus: "Canonical original"
            )
        }
    }

    /// One catalogue with the driver's record replaced.
    private static func catalogue(_ moment: Moment, replacing driver: Driver, with record: FieldChooserOriginal10868) -> [FieldChooserOriginal10868] {
        catalogue(moment).map { $0.ref == ref(driver) ? record : $0 }
    }

    private static func state(_ moment: Moment, progress: FieldHeadlineProgress10868? = nil) -> FieldHeadlineState10868 {
        switch moment {
        case .before:
            return FieldHeadlineState10868(
                figure: "62 laps", unit: nil, caption: "Scheduled start", detail: "Oct 11, 5:00 AM PT",
                spoken: "62 laps. Scheduled start Oct 11, 5:00 AM PT", progress: progress)
        case .lap(let stage):
            return FieldHeadlineState10868(
                figure: "Lap \(laps[stage])", unit: "/ 62", caption: "Verstappen leads", detail: "Leclerc +\(gaps[stage])s",
                spoken: "Lap \(laps[stage]) of 62, reported \(reportClocks[stage]). Verstappen leads; Leclerc \(gaps[stage]) seconds behind",
                progress: progress ?? FieldHeadlineProgress10868(completed: Double(laps[stage]), total: 62))
        case .final:
            return FieldHeadlineState10868(
                figure: "62 laps", unit: nil, caption: "Race complete", detail: "Final classification · Oct 11, 2026",
                spoken: "62 laps. Race complete. Final classification, Oct 11, 2026",
                progress: progress ?? FieldHeadlineProgress10868(completed: 62, total: 62))
        }
    }

    private static func copy(_ moment: Moment, title: String? = "Singapore Grand Prix", aboutLabel: String = FieldPhaseHeadline10868Tests.aboutLabel) -> FieldHeadlineCopy10868 {
        let (eyebrow, graphic): (String, String) = switch moment {
        case .before: ("Formula 1 · Before the start", "Pre-race win chances")
        case .lap: ("Formula 1 · Recorded probabilities", "Pre-race and recorded win chances")
        case .final: ("Formula 1 · Final classification", "Pre-race chances and actual finishes")
        }
        return FieldHeadlineCopy10868(
            eyebrow: eyebrow, title: title, graphicLabel: graphic,
            beforeLabel: beforeLabel, recordedLabel: recordedLabel,
            beforeUnavailable: notRecorded, recordedUnavailable: recordedUnavailable,
            finishLabel: finishLabel, finishUnavailable: finishUnavailable,
            empty: "No drivers in this update",
            aboutLabel: aboutLabel, aboutHint: aboutHint, openHint: openHint
        )
    }

    /// The finishes ride along in every moment; only the final reads them.
    private static func input(
        _ moment: Moment = .lap(1),
        catalogue: [FieldChooserOriginal10868]? = nil,
        displayed: [FieldHeadlineSlot10868]? = nil,
        pairs: [FieldMovementPair10868]? = nil,
        finishes: [FieldFinishPlace10868]? = nil,
        state: FieldHeadlineState10868?? = nil,
        copy: FieldHeadlineCopy10868? = nil
    ) -> FieldHeadlineInput10868 {
        FieldHeadlineInput10868(
            scope: scope,
            catalogue: catalogue ?? Self.catalogue(moment),
            displayed: displayed ?? drivers.map { slot($0) },
            pairs: pairs ?? drivers.map { pair($0, moment) },
            finishes: finishes ?? drivers.map { finish($0) },
            state: state ?? Self.state(moment),
            phase: moment.phase,
            copy: copy ?? Self.copy(moment),
            unavailableWords: unavailable
        )
    }

    private static func model(_ input: FieldHeadlineInput10868 = FieldPhaseHeadline10868Tests.input()) -> FieldHeadlineModel10868 {
        FieldHeadlineModel10868(input)
    }

    private static func competitor(_ model: FieldHeadlineModel10868, _ driver: Driver) -> FieldHeadlineCompetitor10868? {
        model.competitors.first { $0.slot.ref == ref(driver) }
    }

    /// What one competitor visibly prints, from the same helpers the view calls.
    private static func visibleLines(_ model: FieldHeadlineModel10868, _ competitor: FieldHeadlineCompetitor10868) -> [String] {
        guard let original = competitor.resolution.original else {
            return [FieldMovementModel10868.readable(competitor.slot.name), model.input.unavailableWords].compactMap { $0 }
        }
        var lines = [original.name, model.compactName(competitor)].compactMap { $0 }
        for endpoint in competitor.metrics {
            lines += [FieldChaseModel10868.label(endpoint), FieldChaseModel10868.figure(endpoint), FieldChaseModel10868.words(endpoint)].compactMap { $0 }
        }
        return lines
    }

    /// Every line one competitor shows or speaks.
    private static func competitorLines(_ model: FieldHeadlineModel10868, _ competitor: FieldHeadlineCompetitor10868) -> [String] {
        var lines = visibleLines(model, competitor) + [model.competitorSummary(competitor)]
        let opening = model.openAction(competitor, canOpen: true)
        if opening != nil { lines.append(model.hint(opening)) }
        if let key = opening?.observation { lines.append(key) }
        return lines
    }

    private static func stateLines(_ model: FieldHeadlineModel10868) -> [String] {
        guard let state = model.state else { return [] }
        return [state.figure, state.unit, state.caption, state.detail, model.stateSummary].compactMap { $0 }
    }

    /// Every line the headline shows or speaks, with both callbacks.
    private static func everyLine(_ model: FieldHeadlineModel10868) -> [String] {
        var lines = [model.eyebrow, model.title, model.aboutLabel(canAbout: true), model.aboutHint(canAbout: true), model.input.copy.graphicLabel].compactMap { $0 }
        for competitor in model.competitors { lines += competitorLines(model, competitor) }
        return lines + stateLines(model)
    }

    private static func figures(_ competitor: FieldHeadlineCompetitor10868?) -> [String?] {
        competitor?.metrics.map(FieldChaseModel10868.figure) ?? []
    }


    // MARK: Three phases

    func testEveryPhaseShowsTheOwnersThreeDriversWithTheirOwnChancesAndClocks() {
        for moment in Self.moments {
            let model = Self.model(Self.input(moment))
            XCTAssertEqual(model.competitors.map(\.slot.ref), Self.drivers.map { Self.ref($0) }, "\(moment)")
            for driver in Self.drivers {
                let label = "\(driver.name) \(moment)"
                guard let competitor = Self.competitor(model, driver) else { XCTFail(label); continue }
                XCTAssertEqual(competitor.resolution.original?.ref, Self.ref(driver), label)
                XCTAssertEqual(competitor.resolution.original?.name, driver.name, label)
                let before = FieldMovementEndpoint10868.reading(Self.beforeReading(driver))
                switch moment {
                case .before:
                    // Exactly one labelled pre-race chance: no second before figure.
                    XCTAssertEqual(competitor.metrics, [before], label)
                case .lap(let stage):
                    XCTAssertEqual(competitor.metrics, [before, .reading(Self.recordedReading(driver, stage))], label)
                case .final:
                    XCTAssertEqual(competitor.metrics, [before, .reading(Self.finishReading(driver))], label)
                }
                // The pre-race chance is the same own reading, with its own clock, in every phase.
                XCTAssertEqual(FieldChaseModel10868.label(competitor.metrics[0]), Self.beforeLabel, label)
                XCTAssertEqual(FieldChaseModel10868.figure(competitor.metrics[0]), driver.before.figure, label)
                XCTAssertEqual(FieldChaseModel10868.detail(competitor.metrics[0]), "\(driver.before.clock) · Polymarket trade", label)
            }
        }
        func figures(_ moment: Moment) -> [[String?]] {
            Self.model(Self.input(moment)).competitors.map { Self.figures($0) }
        }
        XCTAssertEqual(figures(.before), [["65%"], ["14%"], ["16%"]])
        XCTAssertEqual(figures(.lap(0)), [["65%", "95%"], ["14%", "8.3%"], ["16%", "0.2%"]])
        XCTAssertEqual(figures(.lap(1)), [["65%", "90.9%"], ["14%", "16.1%"], ["16%", "0.2%"]])
        XCTAssertEqual(figures(.lap(2)), [["65%", "99.9%"], ["14%", "0.1%"], ["16%", nil]])
        XCTAssertEqual(figures(.final), [["65%", "1st"], ["14%", "2nd"], ["16%", "6th"]])

        // The labels say what each figure is, phase by phase.
        let labels = Self.moments.map { Self.model(Self.input($0)).competitors[0].metrics.map(FieldChaseModel10868.label) }
        XCTAssertEqual(labels, [[Self.beforeLabel], [Self.beforeLabel, Self.recordedLabel], [Self.beforeLabel, Self.recordedLabel],
                                [Self.beforeLabel, Self.recordedLabel], [Self.beforeLabel, Self.finishLabel]])
    }

    // MARK: Before

    func testBeforeShowsOnePreRaceChanceEvenWithLaterReadingsAndFinishesRidingAlong() {
        // CONSTRUCTED hostile owner input: lap-58 readings on the plans and the
        // associations, the finishes, contract results and a progress value.
        let hostileCatalogue = Self.drivers.enumerated().reduce(Self.catalogue(.before)) { catalogue, item in
            let (index, driver) = item
            let record = Self.record(driver, .before, plan: Self.plan(driver, .lap(2)), result: FieldChooserResult10868(title: "Final result", words: Self.results[index]))
            return catalogue.map { $0.ref == Self.ref(driver) ? record : $0 }
        }
        let hostile = Self.model(Self.input(
            .before, catalogue: hostileCatalogue, pairs: Self.drivers.map { Self.pair($0, .lap(2)) },
            state: Self.state(.before, progress: FieldHeadlineProgress10868(completed: 0, total: 62))))
        let plain = Self.model(Self.input(.before))
        for driver in Self.drivers {
            guard let competitor = Self.competitor(hostile, driver) else { XCTFail(driver.name); continue }
            XCTAssertEqual(competitor.metrics, [.reading(Self.beforeReading(driver))], driver.name)
            XCTAssertEqual(competitor.metrics, Self.competitor(plain, driver)?.metrics, driver.name)
            XCTAssertEqual(hostile.openAction(competitor, canOpen: true), FieldMovementOpen10868(ref: Self.ref(driver), observation: nil), driver.name)
        }
        XCTAssertNil(hostile.progress)
        let lines = Self.everyLine(hostile)
        for leak in ["95%", "90.9%", "99.9%", "8.3%", "16.1%", "6:19", "6:29", "6:30", "6:40", Self.recordedLabel, Self.finishLabel,
                     "1st", "2nd", "6th", "Won", "Lost", "constructed:", "ESPN"] {
            XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
        }

        // The before figures and clocks are the reference's last before-window
        // readings — the very pre-race readings shown beside the recorded ones.
        let during = Self.model(Self.input(.lap(1)))
        for driver in Self.drivers {
            XCTAssertEqual(Self.competitor(plain, driver)?.metrics.first, Self.competitor(during, driver)?.metrics.first, driver.name)
        }
        XCTAssertEqual(plain.competitors.map(plain.competitorSummary), [
            "Pre-race win: 65%, Oct 11, 4:59:31 AM PT · Polymarket trade",
            "Pre-race win: 14%, Oct 11, 4:59:46 AM PT · Polymarket trade",
            "Pre-race win: 16%, Oct 11, 4:59:19 AM PT · Polymarket trade",
        ])
    }

    // MARK: During

    func testDuringBothChancesShowAndHamiltonAtLap58KeepsHisPreRaceChanceWithNoRecentProbability() {
        let model = Self.model(Self.input(.lap(2)))
        guard let hamilton = Self.competitor(model, Self.hamilton) else { return XCTFail("Hamilton") }
        let words = FieldChooserReading10868(label: Self.recordedLabel, value: .missing(Self.recordedUnavailable))
        XCTAssertEqual(hamilton.metrics, [.reading(Self.beforeReading(Self.hamilton)), .reading(words)])
        XCTAssertEqual(FieldChaseModel10868.words(hamilton.metrics[1]), Self.recordedUnavailable)
        XCTAssertNil(FieldChaseModel10868.figure(hamilton.metrics[1]))
        XCTAssertEqual(model.competitorSummary(hamilton), "Pre-race win: 16%, Oct 11, 4:59:19 AM PT · Polymarket trade. Recorded win: No recent probability")
        XCTAssertEqual(model.openAction(hamilton, canOpen: true), FieldMovementOpen10868(ref: Self.ref(Self.hamilton), observation: nil))
        // The race state of that report stays.
        XCTAssertEqual(model.state?.figure, "Lap 58")
        XCTAssertEqual(model.state?.detail, "Leclerc +9.0s")

        // CONSTRUCTED hostile owner input: the stale 0.001 trade as his later
        // observation, on the association and on the plan. Neither ties it.
        let staleReading = FieldChooserReading10868(
            label: Self.recordedLabel, value: .recorded(text: Self.hamiltonStale.figure, detail: "\(Self.hamiltonStale.clock) · Polymarket trade"))
        var pairs = Self.drivers.map { Self.pair($0, .lap(2)) }
        pairs[2] = FieldMovementPair10868(
            ref: Self.ref(Self.hamilton), before: pairs[2].before,
            later: FieldMovementObservation10868(probability: Self.hamiltonStale.p, reading: staleReading),
            movement: "-15.9 pp", observation: "constructed:stale")
        let onPair = Self.model(Self.input(.lap(2), pairs: pairs))
        XCTAssertEqual(Self.competitor(onPair, Self.hamilton)?.metrics, hamilton.metrics)
        let onPlan = Self.model(Self.input(.lap(2), catalogue: Self.catalogue(.lap(2), replacing: Self.hamilton, with: Self.record(
            Self.hamilton, .lap(2), plan: .comparison(before: Self.beforeReading(Self.hamilton), later: staleReading)))))
        XCTAssertEqual(Self.competitor(onPlan, Self.hamilton)?.metrics,
                       [.reading(Self.beforeReading(Self.hamilton)), .unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)])
        for hostile in [onPair, onPlan] {
            guard let row = Self.competitor(hostile, Self.hamilton) else { XCTFail("hostile"); continue }
            XCTAssertEqual(hostile.openAction(row, canOpen: true), FieldMovementOpen10868(ref: Self.ref(Self.hamilton), observation: nil))
            let lines = Self.competitorLines(hostile, row)
            for leak in ["0.1%", "6:35:12", "-15.9", "constructed:stale"] {
                XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
            }
        }

        // His neighbours at lap 58 keep both of their own figures at the same rank.
        XCTAssertEqual(Self.figures(Self.competitor(model, Self.verstappen)), ["65%", "99.9%"])
        XCTAssertEqual(Self.figures(Self.competitor(model, Self.leclerc)), ["14%", "0.1%"])
    }

    // MARK: Failed, withdrawn, missing and zero

    func testAFailedWithdrawnOrMissingInputAndAGenuineZeroStayDistinct() {
        let plain = Self.model()
        let keptBefore = FieldMovementEndpoint10868.reading(Self.beforeReading(Self.leclerc))
        let withheld = FieldMovementEndpoint10868.unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)
        let before = Self.pair(Self.leclerc, .lap(1)).before

        // An earlier quote left on the association, a withdrawn observation, or a
        // raw value that is not a probability: the copy's words, no number.
        var cases: [(String, FieldMovementPair10868)] = [
            ("stale", FieldMovementPair10868(
                ref: Self.ref(Self.leclerc), before: before,
                later: FieldMovementObservation10868(probability: 0.0829999984, reading: Self.recordedReading(Self.leclerc, 0)),
                movement: nil, observation: "constructed:lap46")),
            ("withdrawn", FieldMovementPair10868(ref: Self.ref(Self.leclerc), before: before, later: nil, movement: nil, observation: "constructed:gone")),
        ]
        for bad in [1.2, -0.1, Double.nan, .infinity] {
            cases.append(("\(bad)", Self.pair(Self.leclerc, .lap(1), recorded: bad)))
        }
        for (label, leclercPair) in cases {
            let model = Self.model(Self.input(pairs: [Self.pair(Self.verstappen, .lap(1)), leclercPair, Self.pair(Self.hamilton, .lap(1))]))
            guard let competitor = Self.competitor(model, Self.leclerc) else { XCTFail(label); continue }
            XCTAssertEqual(competitor.metrics, [keptBefore, withheld], label)
            XCTAssertEqual(model.openAction(competitor, canOpen: true), FieldMovementOpen10868(ref: Self.ref(Self.leclerc), observation: nil), label)
            XCTAssertFalse(Self.competitorLines(model, competitor).contains {
                $0.contains("16.1%") || $0.contains("8.3%") || $0.contains("6:30:12") || $0.contains("6:20:28")
            }, label)
            XCTAssertEqual(Self.competitor(model, Self.verstappen), Self.competitor(plain, Self.verstappen), label)
            XCTAssertEqual(Self.competitor(model, Self.hamilton), Self.competitor(plain, Self.hamilton), label)
            XCTAssertEqual(model.state, plain.state, label)
        }

        // A pre-race chance the owner has no observation for: the owner's own
        // words as they are, or — untied — the copy's words. The other figure stays.
        let ownWords = FieldChooserReading10868(label: Self.beforeLabel, value: .missing("Not recorded before the start"))
        let noBaseline = Self.model(Self.input(catalogue: Self.catalogue(.lap(1), replacing: Self.leclerc, with: Self.record(
            Self.leclerc, .lap(1), plan: .comparison(before: ownWords, later: Self.recordedReading(Self.leclerc, 1))))))
        XCTAssertEqual(Self.competitor(noBaseline, Self.leclerc)?.metrics, [.reading(ownWords), .reading(Self.recordedReading(Self.leclerc, 1))])
        var untiedPairs = Self.drivers.map { Self.pair($0, .lap(1)) }
        untiedPairs[1] = FieldMovementPair10868(ref: untiedPairs[1].ref, before: nil, later: untiedPairs[1].later, movement: nil, observation: untiedPairs[1].observation)
        let untied = Self.model(Self.input(pairs: untiedPairs))
        XCTAssertEqual(Self.competitor(untied, Self.leclerc)?.metrics,
                       [.unavailable(label: Self.beforeLabel, words: Self.notRecorded), .reading(Self.recordedReading(Self.leclerc, 1))])

        // CONSTRUCTED genuine 0%: a figure, never words and never a missing value.
        let zeroReading = FieldChooserReading10868(label: Self.recordedLabel, value: .recorded(text: "0%", detail: "constructed clock · Polymarket trade"))
        var zeroPairs = Self.drivers.map { Self.pair($0, .lap(1)) }
        zeroPairs[1] = FieldMovementPair10868(ref: zeroPairs[1].ref, before: zeroPairs[1].before,
                                              later: FieldMovementObservation10868(probability: 0, reading: zeroReading), movement: nil, observation: "constructed:zero")
        let zero = Self.model(Self.input(
            catalogue: Self.catalogue(.lap(1), replacing: Self.leclerc, with: Self.record(
                Self.leclerc, .lap(1), plan: .comparison(before: Self.beforeReading(Self.leclerc), later: zeroReading))),
            pairs: zeroPairs))
        guard let zeroRow = Self.competitor(zero, Self.leclerc) else { return XCTFail("zero") }
        XCTAssertEqual(Self.figures(zeroRow), ["14%", "0%"])
        XCTAssertNil(FieldChaseModel10868.words(zeroRow.metrics[1]))
        XCTAssertEqual(zero.openAction(zeroRow, canOpen: true)?.observation, "constructed:zero")

        // A withdrawn driver (no catalogue record) keeps the owner's name beside the unavailable words.
        let withdrawn = FieldHeadlineSlot10868(ref: Self.ref("5229499", "constructed-withdrawn"), name: "Withdrawn driver", compactName: "Withdrawn")
        let gone = Self.model(Self.input(displayed: [Self.slot(Self.verstappen), withdrawn, Self.slot(Self.hamilton)]))
        XCTAssertEqual(gone.competitors[1].metrics, [])
        XCTAssertEqual(gone.competitorSummary(gone.competitors[1]), "Withdrawn driver. \(Self.unavailable)")
        XCTAssertNil(gone.compactName(gone.competitors[1]))

        // A missing finish: the copy's words, or the owner's own absence words; the pre-race chance stays.
        let noFinish = Self.model(Self.input(.final, finishes: [Self.finish(Self.verstappen), Self.finish(Self.hamilton)]))
        XCTAssertEqual(Self.competitor(noFinish, Self.leclerc)?.metrics,
                       [keptBefore, .unavailable(label: Self.finishLabel, words: Self.finishUnavailable)])
        let notClassified = FieldChooserReading10868(label: Self.finishLabel, value: .missing("Not classified"))
        let ownFinishWords = Self.model(Self.input(.final, finishes: [Self.finish(Self.verstappen),
            FieldFinishPlace10868(ref: Self.ref(Self.leclerc), reading: notClassified), Self.finish(Self.hamilton)]))
        XCTAssertEqual(Self.competitor(ownFinishWords, Self.leclerc)?.metrics, [keptBefore, .reading(notClassified)])
        XCTAssertEqual(Self.competitor(ownFinishWords, Self.hamilton)?.metrics.last, .reading(Self.finishReading(Self.hamilton)))
    }

    // MARK: Final

    func testTheFinalKeepsThePreRaceChanceBesideThePhysicalFinishAndNeverASettledQuoteOrResult() {
        // CONSTRUCTED hostile owner input: the archived settled quotes as later
        // readings on the plans and the associations with keys, the contract
        // results, and the opening probabilities as previews and movement words.
        func settledReading(_ index: Int) -> FieldChooserReading10868 {
            FieldChooserReading10868(label: Self.recordedLabel, value: .recorded(text: Self.settled[index].figure, detail: "Settled Oct 11 · Polymarket"))
        }
        var hostileCatalogue = Self.catalogue(.final)
        for (index, driver) in Self.drivers.enumerated() {
            let record = FieldChooserOriginal10868(
                ref: Self.ref(driver), name: driver.name,
                plan: .comparison(before: Self.beforeReading(driver), later: settledReading(index)),
                preview: FieldChooserPreview10868(
                    history: FieldChooserHistory10868(segments: [[FieldChooserPoint10868(time: 1, probability: Self.settled[index].p)]],
                                                      emphasis: nil, beforeReference: Self.opening[index].p, gaps: []),
                    absence: "No history in this card"),
                movement: "Opened \(Self.opening[index].figure)", clock: "Settled Oct 11",
                result: FieldChooserResult10868(title: "Market result", words: Self.results[index]),
                browseStatus: "Settled"
            )
            hostileCatalogue = hostileCatalogue.map { $0.ref == record.ref ? record : $0 }
        }
        let hostilePairs = Self.drivers.enumerated().map { index, driver in
            FieldMovementPair10868(
                ref: Self.ref(driver),
                before: FieldMovementObservation10868(probability: driver.before.p, reading: Self.beforeReading(driver)),
                later: FieldMovementObservation10868(probability: Self.settled[index].p, reading: settledReading(index)),
                movement: "settled movement", observation: "constructed:settled:\(driver.market)")
        }
        let hostile = Self.model(Self.input(.final, catalogue: hostileCatalogue, pairs: hostilePairs))
        let plain = Self.model(Self.input(.final))
        for driver in Self.drivers {
            guard let competitor = Self.competitor(hostile, driver) else { XCTFail(driver.name); continue }
            XCTAssertEqual(competitor.metrics, [.reading(Self.beforeReading(driver)), .reading(Self.finishReading(driver))], driver.name)
            XCTAssertEqual(competitor.metrics, Self.competitor(plain, driver)?.metrics, driver.name)
            XCTAssertEqual(hostile.openAction(competitor, canOpen: true), FieldMovementOpen10868(ref: Self.ref(driver), observation: nil), driver.name)
        }
        let lines = Self.everyLine(hostile)
        XCTAssertFalse(lines.contains("100%"))
        XCTAssertFalse(lines.contains("0%"))
        for leak in ["Settled", "settled", "Won", "Lost", "Market result", "33.5%", "10.5%", "Opened", Self.recordedLabel,
                     Self.lastLapPublished, "6:46"] {
            XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
        }

        // The finish is the owner's physical ordinal with its own source, spoken whole.
        XCTAssertEqual(plain.competitors.map(plain.competitorSummary), [
            "Pre-race win: 65%, Oct 11, 4:59:31 AM PT · Polymarket trade. Actual finish: 1st, \(Self.classification)",
            "Pre-race win: 14%, Oct 11, 4:59:46 AM PT · Polymarket trade. Actual finish: 2nd, \(Self.classification)",
            "Pre-race win: 16%, Oct 11, 4:59:19 AM PT · Polymarket trade. Actual finish: 6th, \(Self.classification)",
        ])
        // The pre-race reminder is the very reading shown before the start.
        let beforeStart = Self.model(Self.input(.before))
        for driver in Self.drivers {
            XCTAssertEqual(Self.competitor(plain, driver)?.metrics.first, Self.competitor(beforeStart, driver)?.metrics.first, driver.name)
        }
    }

    func testAFinishIsNeverReadFromTheChanceTheOrderOrTheResult() {
        // The owner's order moves the drivers; each keeps its own finish and chance.
        let reordered = Self.model(Self.input(.final, displayed: [Self.slot(Self.hamilton), Self.slot(Self.verstappen), Self.slot(Self.leclerc)]))
        XCTAssertEqual(reordered.competitors.map { Self.figures($0) }, [["16%", "6th"], ["65%", "1st"], ["14%", "2nd"]])

        // Contract results with no finish associations are never a finish.
        let resultsOnly = Self.drivers.enumerated().reduce(Self.catalogue(.final)) { catalogue, item in
            let record = Self.record(item.element, .final, result: FieldChooserResult10868(title: "Market result", words: Self.results[item.offset]))
            return catalogue.map { $0.ref == record.ref ? record : $0 }
        }
        let noFinishes = Self.model(Self.input(.final, catalogue: resultsOnly, finishes: []))
        for competitor in noFinishes.competitors {
            XCTAssertEqual(competitor.metrics.last, .unavailable(label: Self.finishLabel, words: Self.finishUnavailable))
        }
        XCTAssertFalse(Self.everyLine(noFinishes).contains { $0.contains("Won") || $0.contains("1st") })

        // Verstappen's finish carried on Hamilton's ref makes two for Hamilton —
        // none — and none for Verstappen; Leclerc keeps his own.
        let carried = Self.model(Self.input(.final, finishes: [Self.finish(Self.verstappen, ref: Self.ref(Self.hamilton)), Self.finish(Self.leclerc), Self.finish(Self.hamilton)]))
        let unavailable = FieldMovementEndpoint10868.unavailable(label: Self.finishLabel, words: Self.finishUnavailable)
        XCTAssertEqual(Self.competitor(carried, Self.verstappen)?.metrics.last, unavailable)
        XCTAssertEqual(Self.competitor(carried, Self.hamilton)?.metrics.last, unavailable)
        XCTAssertEqual(Self.competitor(carried, Self.leclerc)?.metrics.last, .reading(Self.finishReading(Self.leclerc)))

        // A blank ordinal, two identical associations, or one on a foreign scope are none.
        let blank = FieldFinishPlace10868(ref: Self.ref(Self.leclerc), reading: FieldChooserReading10868(label: Self.finishLabel, value: .recorded(text: "  ", detail: Self.classification)))
        let foreign = Self.finish(Self.leclerc, ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "constructed:f1:other-race"))
        for (label, leclercFinishes) in [("blank", [blank]), ("twice", [Self.finish(Self.leclerc), Self.finish(Self.leclerc)]), ("foreign", [foreign])] {
            let model = Self.model(Self.input(.final, finishes: [Self.finish(Self.verstappen)] + leclercFinishes + [Self.finish(Self.hamilton)]))
            XCTAssertEqual(Self.competitor(model, Self.leclerc)?.metrics,
                           [.reading(Self.beforeReading(Self.leclerc)), unavailable], label)
            XCTAssertEqual(Self.competitor(model, Self.verstappen)?.metrics.last, .reading(Self.finishReading(Self.verstappen)), label)
        }

        // The finish does not depend on the chances: with every association withheld it stays.
        let noChances = Self.model(Self.input(.final, pairs: []))
        XCTAssertEqual(noChances.competitors.map { $0.metrics }, Self.drivers.map { driver -> [FieldMovementEndpoint10868] in
            [.unavailable(label: Self.beforeLabel, words: Self.notRecorded), .reading(Self.finishReading(driver))]
        })
    }

    // MARK: The canonical catalogue

    func testEveryCanonicalOriginalStaysAndNothingIsNormalizedOrComplemented() {
        for moment in Self.moments {
            let model = Self.model(Self.input(moment))
            let catalogue = Self.catalogue(moment)
            XCTAssertEqual(catalogue.count, 75, "\(moment)")
            XCTAssertEqual(Set(catalogue.map(\.ref)).count, 75, "\(moment)")
            XCTAssertEqual(model.input.catalogue, catalogue, "\(moment)")
            for record in catalogue {
                XCTAssertEqual(model.field.resolve(record.ref), .original(record), "\(record.name) \(moment)")
            }
            XCTAssertEqual(model.competitors.compactMap { $0.resolution.original?.name }, ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"], "\(moment)")
        }
        XCTAssertEqual(Self.catalogue(.final).prefix(3).map(\.name), ["Max Verstappen", "Lewis Hamilton", "Charles Leclerc"])

        // A name is not an identity: Verstappen's podium and fastest-lap contracts stay separate and unshown.
        let model = Self.model()
        let namesakes = Self.canonical.filter { $0.name == Self.verstappen.name }
        XCTAssertEqual(namesakes.map { $0.market }, ["5229406", "5229633", "5229488"])
        for entry in namesakes.dropFirst() {
            let other = Self.ref(entry.market, entry.outcome)
            XCTAssertNotNil(model.field.resolve(other).original)
            XCTAssertFalse(model.competitors.contains { $0.slot.ref == other })
        }

        // The shown raw values sum past 1 at laps 46 and 52 and stay exactly as they are.
        for stage in 0..<3 {
            let lap = Self.model(Self.input(.lap(stage)))
            for driver in Self.drivers {
                let pair = lap.movement.pair(for: Self.ref(driver))
                XCTAssertEqual(pair?.before?.probability, driver.before.p, driver.name)
                XCTAssertEqual(pair?.later?.probability, driver.recorded[stage]?.p, driver.name)
            }
        }
        XCTAssertGreaterThan(Self.drivers.compactMap { $0.recorded[0]?.p }.reduce(0, +), 1)
        XCTAssertGreaterThan(Self.drivers.compactMap { $0.recorded[1]?.p }.reduce(0, +), 1)
        XCTAssertLessThan(Self.drivers.map { $0.before.p }.reduce(0, +), 1)

        // CONSTRUCTED No control: its own 40% stays 40%, never Verstappen's 35% complement.
        let noRef = Self.ref(Self.verstappen.market, "constructed-no")
        let noReading = FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: "40%", detail: "constructed clock · Polymarket trade"))
        let noRecord = FieldChooserOriginal10868(
            ref: noRef, name: "Max Verstappen — No", plan: .comparison(before: noReading, later: FieldChooserReading10868(label: Self.recordedLabel, value: .missing(Self.recordedUnavailable))),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil, browseStatus: "No side")
        let withNo = Self.model(Self.input(
            catalogue: Self.catalogue(.lap(1)) + [noRecord],
            displayed: [Self.slot(Self.verstappen), FieldHeadlineSlot10868(ref: noRef, name: "Max Verstappen — No", compactName: nil)],
            pairs: [Self.pair(Self.verstappen, .lap(1)), FieldMovementPair10868(ref: noRef, before: FieldMovementObservation10868(probability: 0.4, reading: noReading), later: nil, movement: nil, observation: nil)]))
        XCTAssertEqual(withNo.competitors.map { Self.figures($0) }, [["65%", "90.9%"], ["40%", nil]])
        XCTAssertFalse(Self.everyLine(withNo).contains { $0.contains("35%") || $0.contains("9.1%") })

        // A different owner selection changes the drivers, never the catalogue.
        let others = Array(Self.catalogue(.lap(1))[3...5])
        let elsewhere = Self.model(Self.input(displayed: others.map { FieldHeadlineSlot10868(ref: $0.ref, name: $0.name, compactName: nil) }))
        XCTAssertEqual(elsewhere.competitors.compactMap { $0.resolution.original?.ref }, others.map(\.ref))
        XCTAssertEqual(elsewhere.input.catalogue.count, 75)
    }

    // MARK: Identity

    func testForeignBlankRepeatedDuplicateAndWithdrawnSlotsBorrowNothingAndNeighboursKeepTheirs() {
        let foreign = FieldHeadlineSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "constructed:f1:other-race"), name: Self.leclerc.name, compactName: Self.leclerc.compact)
        let withdrawn = FieldHeadlineSlot10868(ref: Self.ref("5229499", "constructed-withdrawn"), name: "Withdrawn driver", compactName: nil)
        let blank = FieldHeadlineSlot10868(ref: Self.ref(Self.leclerc.market, "  "), name: " ", compactName: " ")
        let first = Self.slot(Self.verstappen)
        let middle = Self.slot(Self.leclerc)
        let last = Self.slot(Self.hamilton)
        for moment in [Moment.before, .lap(1), .final] {
            let plain = Self.model(Self.input(moment))
            let cases: [(String, FieldHeadlineInput10868)] = [
                ("foreign", Self.input(moment, displayed: [first, foreign, last])),
                ("withdrawn", Self.input(moment, displayed: [first, withdrawn, last])),
                ("blank", Self.input(moment, displayed: [first, blank, last])),
                ("duplicate record", Self.input(moment, catalogue: Self.catalogue(moment) + [Self.record(Self.leclerc, moment)])),
                ("repeated slot", Self.input(moment, displayed: [first, middle, middle, last])),
                ("foreign associations only", Self.input(moment, displayed: [first, foreign, last],
                    pairs: [Self.pair(Self.verstappen, moment), Self.pair(Self.leclerc, moment, ref: foreign.ref), Self.pair(Self.hamilton, moment)],
                    finishes: [Self.finish(Self.verstappen), Self.finish(Self.leclerc, ref: foreign.ref), Self.finish(Self.hamilton)])),
            ]
            for (name, input) in cases {
                let label = "\(name) \(moment)"
                let model = Self.model(input)
                let unresolved = model.competitors.filter { $0.slot.ref != first.ref && $0.slot.ref != last.ref }
                XCTAssertFalse(unresolved.isEmpty, label)
                for competitor in unresolved {
                    XCTAssertNil(competitor.resolution.original, label)
                    XCTAssertEqual(competitor.metrics, [], label)
                    XCTAssertNil(model.compactName(competitor), label)
                    XCTAssertNil(model.openAction(competitor, canOpen: true), label)
                    XCTAssertFalse(Self.competitorLines(model, competitor).contains {
                        $0.contains("14%") || $0.contains("16.1%") || $0.contains("2nd") || $0.contains(Self.openHint)
                    }, label)
                }
                XCTAssertEqual(Self.competitor(model, Self.verstappen), Self.competitor(plain, Self.verstappen), label)
                XCTAssertEqual(Self.competitor(model, Self.hamilton), Self.competitor(plain, Self.hamilton), label)
            }
            let foreignModel = Self.model(cases[0].1)
            XCTAssertEqual(foreignModel.competitorSummary(foreignModel.competitors[1]), "Charles Leclerc. \(Self.unavailable)", "\(moment)")
            let blankModel = Self.model(cases[2].1)
            XCTAssertEqual(blankModel.competitorSummary(blankModel.competitors[1]), Self.unavailable, "\(moment)")
        }

        // Two identical associations for one driver are none; at the final his
        // separately reported finish stays.
        let twicePairs = [Self.pair(Self.verstappen, .lap(1)), Self.pair(Self.leclerc, .lap(1)), Self.pair(Self.leclerc, .lap(1)), Self.pair(Self.hamilton, .lap(1))]
        let twice = Self.model(Self.input(pairs: twicePairs))
        XCTAssertEqual(Self.competitor(twice, Self.leclerc)?.metrics, [.unavailable(label: Self.beforeLabel, words: Self.notRecorded),
                                                                     .unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)])
        let twiceFinal = Self.model(Self.input(.final, pairs: [Self.pair(Self.leclerc, .final), Self.pair(Self.leclerc, .final)]))
        XCTAssertEqual(Self.competitor(twiceFinal, Self.leclerc)?.metrics, [.unavailable(label: Self.beforeLabel, words: Self.notRecorded),
                                                                          .reading(Self.finishReading(Self.leclerc))])

        // Leclerc's readings carried on Verstappen's association are borrowed by neither.
        let borrowed = Self.model(Self.input(pairs: [Self.pair(Self.leclerc, .lap(1), ref: Self.ref(Self.verstappen)), Self.pair(Self.hamilton, .lap(1))]))
        let withheld: [FieldMovementEndpoint10868] = [.unavailable(label: Self.beforeLabel, words: Self.notRecorded),
                                                      .unavailable(label: Self.recordedLabel, words: Self.recordedUnavailable)]
        XCTAssertEqual(Self.competitor(borrowed, Self.verstappen)?.metrics, withheld)
        XCTAssertEqual(Self.competitor(borrowed, Self.leclerc)?.metrics, withheld)
        XCTAssertEqual(Self.competitor(borrowed, Self.hamilton), Self.competitor(Self.model(), Self.hamilton))
    }

    // MARK: Race state

    func testTheRaceStateAndDateStayTheOwnersAndIndependentOfTheChances() {
        let chanceWords = Self.drivers.flatMap { driver in
            [driver.before.figure, driver.before.clock] + driver.recorded.compactMap { $0 }.flatMap { [$0.figure, $0.clock] }
        }
        for moment in Self.moments {
            let model = Self.model(Self.input(moment))
            XCTAssertEqual(model.state, Self.state(moment), "\(moment)")
            // The state never carries a chance or a chance's clock, and no driver speaks a report clock.
            let state = Self.stateLines(model)
            for word in chanceWords where word.contains("PT") || word.contains("%") {
                XCTAssertFalse(state.contains { $0.contains(word) }, "\(moment) \(word)")
            }
            for competitor in model.competitors {
                for clock in Self.reportClocks {
                    XCTAssertFalse(Self.competitorLines(model, competitor).contains { $0.contains(clock) }, "\(moment) \(clock)")
                }
            }
            // Withholding every chance leaves the state as it is.
            XCTAssertEqual(Self.model(Self.input(moment, pairs: [])).state, model.state, "\(moment)")
            XCTAssertEqual(Self.model(Self.input(moment, pairs: [])).stateSummary, model.stateSummary, "\(moment)")
            // A last-lap publication is never a finish time.
            XCTAssertFalse(Self.everyLine(model).contains { $0.contains(Self.lastLapPublished) }, "\(moment)")
        }

        // Each report's own clock is spoken with its lap, not with any chance.
        for stage in 0..<3 {
            let lap = Self.model(Self.input(.lap(stage)))
            XCTAssertEqual(lap.stateSummary, "Lap \(Self.laps[stage]) of 62, reported \(Self.reportClocks[stage]). Verstappen leads; Leclerc \(Self.gaps[stage]) seconds behind")
            XCTAssertEqual(lap.progress, FieldHeadlineProgress10868(completed: Double(Self.laps[stage]), total: 62))
        }

        // The final keeps its date; progress is complete.
        let final = Self.model(Self.input(.final))
        XCTAssertEqual(final.state?.detail, "Final classification · Oct 11, 2026")
        XCTAssertEqual(final.progress, FieldHeadlineProgress10868(completed: 62, total: 62))

        // Before the start the scheduled laps are state, not progress — even when the owner sends one.
        let before = Self.model(Self.input(.before, state: Self.state(.before, progress: FieldHeadlineProgress10868(completed: 0, total: 62))))
        XCTAssertNil(before.progress)
        XCTAssertEqual(before.state?.detail, "Oct 11, 5:00 AM PT")

        // Invalid progress draws none; the rest of the state stays.
        for bad in [FieldHeadlineProgress10868(completed: 63, total: 62), FieldHeadlineProgress10868(completed: -1, total: 62),
                    FieldHeadlineProgress10868(completed: .nan, total: 62), FieldHeadlineProgress10868(completed: 0, total: 0),
                    FieldHeadlineProgress10868(completed: 1, total: .infinity)] {
            let model = Self.model(Self.input(.lap(1), state: Self.state(.lap(1), progress: bad)))
            XCTAssertNil(model.progress, "\(bad)")
            XCTAssertEqual(model.state?.figure, "Lap 52", "\(bad)")
        }

        // No state: nothing printed or spoken. Blank spoken words: the visible lines, whole.
        let none = Self.model(Self.input(state: .some(nil)))
        XCTAssertNil(none.state)
        XCTAssertNil(none.stateSummary)
        XCTAssertEqual(Self.stateLines(none), [])
        let silent = FieldHeadlineState10868(figure: "Lap 52", unit: "/ 62", caption: "Verstappen leads", detail: "Leclerc +9.1s", spoken: " ", progress: nil)
        XCTAssertEqual(Self.model(Self.input(state: silent)).stateSummary, "Lap 52. / 62. Verstappen leads. Leclerc +9.1s")
    }

    // MARK: Heading and actions

    func testAboutAndOpenAreExactRealCallbacksAndStaticWithoutThem() {
        let model = Self.model()
        XCTAssertEqual(model.eyebrow, "Formula 1 · Recorded probabilities")
        XCTAssertEqual(model.title, "Singapore Grand Prix")
        XCTAssertEqual(model.aboutLabel(canAbout: true), Self.aboutLabel)
        XCTAssertEqual(model.aboutHint(canAbout: true), Self.aboutHint)
        XCTAssertNil(model.aboutLabel(canAbout: false))
        XCTAssertEqual(model.aboutHint(canAbout: false), "")

        // The host already shows the event title: the caller omits it; the phase eyebrow stays.
        let hosted = Self.model(Self.input(copy: Self.copy(.lap(1), title: nil)))
        XCTAssertNil(hosted.title)
        XCTAssertEqual(hosted.eyebrow, "Formula 1 · Recorded probabilities")
        XCTAssertNil(Self.model(Self.input(copy: Self.copy(.lap(1), title: "  "))).title)

        // Blank About words: no control even with a callback.
        let blankAbout = Self.model(Self.input(copy: Self.copy(.lap(1), aboutLabel: " ")))
        XCTAssertNil(blankAbout.aboutLabel(canAbout: true))
        XCTAssertEqual(blankAbout.aboutHint(canAbout: true), "")

        // During the race: the exact original and its recorded observation key.
        for driver in Self.drivers {
            guard let competitor = Self.competitor(model, driver) else { XCTFail(driver.name); continue }
            let opening = model.openAction(competitor, canOpen: true)
            XCTAssertEqual(opening, FieldMovementOpen10868(ref: Self.ref(driver), observation: "constructed:\(driver.market):lap52"), driver.name)
            XCTAssertEqual(model.hint(opening), Self.openHint, driver.name)
            XCTAssertNil(model.openAction(competitor, canOpen: false), driver.name)
            XCTAssertEqual(model.hint(nil), "", driver.name)
        }
        // Before the start and at the final: the exact original, no later observation.
        for moment in [Moment.before, .final] {
            let other = Self.model(Self.input(moment, pairs: Self.drivers.map { Self.pair($0, .lap(1)) }))
            XCTAssertEqual(other.competitors.map { other.openAction($0, canOpen: true) },
                           Self.drivers.map { driver -> FieldMovementOpen10868? in FieldMovementOpen10868(ref: Self.ref(driver), observation: nil) }, "\(moment)")
        }
        // A blank key is none.
        var pairs = Self.drivers.map { Self.pair($0, .lap(1)) }
        pairs[0] = FieldMovementPair10868(ref: pairs[0].ref, before: pairs[0].before, later: pairs[0].later, movement: nil, observation: "  ")
        let blankKey = Self.model(Self.input(pairs: pairs))
        XCTAssertEqual(Self.competitor(blankKey, Self.verstappen).flatMap { blankKey.openAction($0, canOpen: true) },
                       FieldMovementOpen10868(ref: Self.ref(Self.verstappen), observation: nil))
    }

    // MARK: Arrangement

    func testColumnsWhileEveryWholeFigureFitsItsShareElseRowsAndAlwaysRowsAtAccessibilitySizes() {
        func arrangement(_ width: CGFloat, _ figures: [CGFloat], count: Int = 3, accessibility: Bool = false) -> FieldHeadlineArrangement10868 {
            FieldHeadlineGeometry10868.arrangement(available: width, count: count, figureWidths: figures, spacing: 12, accessibilitySize: accessibility)
        }
        // Equal shares with 12 pt between three columns.
        XCTAssertEqual(FieldHeadlineGeometry10868.columnWidth(available: 288, count: 3, spacing: 12), 88)
        XCTAssertEqual(FieldHeadlineGeometry10868.columnWidth(available: 375, count: 3, spacing: 12), 117)
        XCTAssertEqual(FieldHeadlineGeometry10868.columnWidth(available: 343, count: 1, spacing: 12), 343)
        XCTAssertEqual(FieldHeadlineGeometry10868.columnWidth(available: 343, count: 3, spacing: 12) ?? 0, 319.0 / 3, accuracy: 1e-9)
        let bads: [(CGFloat, Int, CGFloat)] = [(343, 0, 12), (343, 3, -1), (.nan, 3, 12), (.infinity, 3, 12), (20, 3, 12)]
        for bad in bads {
            XCTAssertNil(FieldHeadlineGeometry10868.columnWidth(available: bad.0, count: bad.1, spacing: bad.2), "\(bad)")
        }

        // CONSTRUCTED widest-figure widths: "90.9%" at a standard size (74 pt) and at
        // the largest non-accessibility size (99 pt).
        let standard: [CGFloat] = [52, 74, 46, 66, 49, 52]
        let larger = standard.map { $0 * 99 / 74 }
        for width: CGFloat in [288, 320, 343, 375, 393, 600] {
            XCTAssertEqual(arrangement(width, standard), .columns, "\(width)")
            XCTAssertEqual(arrangement(width, larger), width < 343 ? .rows : .columns, "\(width)")
            // Accessibility sizes are rows at every width.
            XCTAssertEqual(arrangement(width, standard, accessibility: true), .rows, "\(width)")
        }
        // Exactly the share fits; a hair more is rows. Nothing shrinks.
        XCTAssertEqual(arrangement(288, [88]), .columns)
        XCTAssertEqual(arrangement(288, [88.01]), .rows)
        // An unmeasurable figure is never assumed to fit; words alone keep columns.
        XCTAssertEqual(arrangement(600, [74, .nan]), .rows)
        XCTAssertEqual(arrangement(600, [74, .infinity]), .rows)
        XCTAssertEqual(arrangement(600, [-1]), .rows)
        XCTAssertEqual(arrangement(343, []), .columns)
        XCTAssertEqual(arrangement(343, standard, count: 0), .rows)
        // A larger owner cohort narrows each share: the same figures become rows.
        XCTAssertEqual(arrangement(343, standard, count: 4), .columns)
        XCTAssertEqual(arrangement(343, standard, count: 5), .rows)

        // The width the drivers are laid out at is always finite.
        XCTAssertEqual(FieldHeadlineGeometry10868.width(proposed: 343, count: 3, figureWidths: standard, spacing: 12), 343)
        XCTAssertEqual(FieldHeadlineGeometry10868.width(proposed: nil, count: 3, figureWidths: standard, spacing: 12), 246)
        for proposed: CGFloat? in [nil, .infinity, .nan, -5] {
            let width = FieldHeadlineGeometry10868.width(proposed: proposed, count: 3, figureWidths: standard + [.infinity, .nan], spacing: 12)
            XCTAssertEqual(width, 246, "\(String(describing: proposed))")
        }
        XCTAssertEqual(FieldHeadlineGeometry10868.width(proposed: nil, count: 3, figureWidths: standard, spacing: .infinity), 0)
        XCTAssertEqual(FieldHeadlineGeometry10868.width(proposed: nil, count: 0, figureWidths: [], spacing: 12), 0)

        // The arrangement measures exactly the figures the drivers draw, in order — words are not figures.
        XCTAssertEqual(Self.model(Self.input(.lap(2))).figures, ["65%", "99.9%", "14%", "0.1%", "16%"])
        XCTAssertEqual(Self.model(Self.input(.final)).figures, ["65%", "1st", "14%", "2nd", "16%", "6th"])
        XCTAssertEqual(Self.model(Self.input(.before)).figures, ["65%", "14%", "16%"])
        // The state lines stack at accessibility sizes.
        XCTAssertTrue(FieldChaseGeometry10868.stacksReadouts(accessibilitySize: true))
        XCTAssertFalse(FieldChaseGeometry10868.stacksReadouts(accessibilitySize: false))
    }

    // MARK: Names and spoken text

    func testWholeNamesCompactLabelsAndSpokenSummariesKeepTheOwnersWordsAndOwnClocks() {
        let model = Self.model()
        XCTAssertEqual(model.competitors.map(model.competitorSummary), [
            "Pre-race win: 65%, Oct 11, 4:59:31 AM PT · Polymarket trade. Recorded win: 90.9%, Oct 11, 6:29:48 AM PT · Polymarket trade",
            "Pre-race win: 14%, Oct 11, 4:59:46 AM PT · Polymarket trade. Recorded win: 16.1%, Oct 11, 6:30:12 AM PT · Polymarket trade",
            "Pre-race win: 16%, Oct 11, 4:59:19 AM PT · Polymarket trade. Recorded win: 0.2%, Oct 11, 6:30:03 AM PT · Polymarket trade",
        ])
        // The compact label is the owner's, never derived; the whole name is always the spoken name.
        XCTAssertEqual(model.competitors.map(model.compactName), ["Verstappen", "Leclerc", "Hamilton"])
        XCTAssertEqual(model.competitors.compactMap { $0.resolution.original?.name }, ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])
        for compact: String? in [nil, " ", "Charles Leclerc"] {
            let other = Self.model(Self.input(displayed: [Self.slot(Self.verstappen), FieldHeadlineSlot10868(ref: Self.ref(Self.leclerc), name: Self.leclerc.name, compactName: compact), Self.slot(Self.hamilton)]))
            XCTAssertNil(other.compactName(other.competitors[1]), "\(String(describing: compact))")
            XCTAssertEqual(other.competitors[1].metrics, Self.competitor(model, Self.leclerc)?.metrics)
        }

        // No source or clock paragraph is printed under the headline: clocks and sources are spoken only.
        for moment in Self.moments {
            let shown = Self.model(Self.input(moment))
            for competitor in shown.competitors {
                XCTAssertFalse(Self.visibleLines(shown, competitor).contains { $0.contains("PT") || $0.contains("Polymarket") || $0.contains("ESPN") }, "\(moment)")
            }
        }

        // A long full name is kept whole, resolved or not.
        let long = "Charles Marc Hervé Perceval Leclerc (Scuderia Ferrari HP)"
        let whole = Self.model(Self.input(catalogue: Self.catalogue(.lap(1), replacing: Self.leclerc, with: Self.record(Self.leclerc, .lap(1), name: long))))
        XCTAssertEqual(Self.competitor(whole, Self.leclerc)?.resolution.original?.name, long)
        XCTAssertEqual(Self.competitor(whole, Self.leclerc).flatMap(whole.compactName), "Leclerc")
        let gone = Self.model(Self.input(displayed: [FieldHeadlineSlot10868(ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "elsewhere"), name: long, compactName: "Leclerc")]))
        XCTAssertEqual(gone.competitors.first.map(gone.competitorSummary), "\(long). \(Self.unavailable)")

        // No drivers: none, and the owner's words.
        let empty = Self.model(Self.input(displayed: []))
        XCTAssertEqual(empty.competitors, [])
        XCTAssertEqual(empty.figures, [])
        XCTAssertEqual(empty.input.copy.empty, "No drivers in this update")
    }

    // MARK: Identity key

    func testTheThreeRealDriversKeepTheirOwnersCircleDiamondAndSquareInEveryPhase() {
        for moment in Self.moments {
            let model = Self.model(Self.input(moment))
            XCTAssertEqual(model.competitors.map(model.keyShape), [.circle, .diamond, .square], "\(moment)")
            XCTAssertEqual(Self.competitor(model, Self.verstappen).map(model.keyShape), .circle, "\(moment)")
            XCTAssertEqual(Self.competitor(model, Self.leclerc).map(model.keyShape), .diamond, "\(moment)")
            XCTAssertEqual(Self.competitor(model, Self.hamilton).map(model.keyShape), .square, "\(moment)")

            // An omitted shape is the ordinary circle, and the shape is presentation only:
            // every figure, word, spoken line and action is the same either way.
            let circles = Self.model(Self.input(moment, displayed: Self.drivers.map {
                FieldHeadlineSlot10868(ref: Self.ref($0), name: $0.name, compactName: $0.compact)
            }))
            XCTAssertEqual(circles.competitors.map(circles.keyShape), [.circle, .circle, .circle], "\(moment)")
            XCTAssertEqual(circles.competitors.map(\.metrics), model.competitors.map(\.metrics), "\(moment)")
            XCTAssertEqual(circles.figures, model.figures, "\(moment)")
            XCTAssertEqual(Self.everyLine(circles), Self.everyLine(model), "\(moment)")
            XCTAssertEqual(circles.competitors.map { circles.openAction($0, canOpen: true) },
                           model.competitors.map { model.openAction($0, canOpen: true) }, "\(moment)")
            XCTAssertEqual(circles.keyIsHollow, model.keyIsHollow, "\(moment)")
        }
    }

    func testAReorderedOrChangedCohortCarriesEachOwnersShapeWithItsOriginal() {
        func shapes(_ input: FieldHeadlineInput10868) -> [FieldHeadlineKeyShape10868] {
            let model = Self.model(input)
            return model.competitors.map(model.keyShape)
        }
        for moment in Self.moments {
            // Reordered: each driver keeps its own shape; nothing rotates with the position.
            XCTAssertEqual(shapes(Self.input(moment, displayed: [Self.hamilton, Self.leclerc, Self.verstappen].map { Self.slot($0) })),
                           [.square, .diamond, .circle], "\(moment)")
            XCTAssertEqual(shapes(Self.input(moment, displayed: [Self.leclerc, Self.hamilton, Self.verstappen].map { Self.slot($0) })),
                           [.diamond, .square, .circle], "\(moment)")
            // A smaller cohort: the first slot does not become a circle.
            XCTAssertEqual(shapes(Self.input(moment, displayed: [Self.leclerc, Self.hamilton].map { Self.slot($0) })), [.diamond, .square], "\(moment)")
            XCTAssertEqual(shapes(Self.input(moment, displayed: [Self.slot(Self.hamilton)])), [.square], "\(moment)")
        }

        // Whatever the owner supplies is drawn as supplied — repeats included — and changes no figure.
        let supplied: [[FieldHeadlineKeyShape10868]] = [[.square, .circle, .diamond], [.diamond, .diamond, .diamond], [.square, .square, .circle]]
        for keys in supplied {
            let displayed = zip(Self.drivers, keys).map { driver, key in
                FieldHeadlineSlot10868(ref: Self.ref(driver), name: driver.name, compactName: driver.compact, keyShape: key)
            }
            XCTAssertEqual(shapes(Self.input(displayed: displayed)), keys)
            XCTAssertEqual(Self.model(Self.input(displayed: displayed)).competitors.map(\.metrics), Self.model().competitors.map(\.metrics))
        }

        // Never from the name, the compact label, the catalogue order or the finish: Leclerc
        // renamed "Max Verstappen", labelled "Verstappen", listed first in the catalogue and
        // reported 1st at the final is still the owner's diamond.
        let renamed = Self.record(Self.leclerc, .final, name: Self.verstappen.name)
        let catalogue = [renamed] + Self.catalogue(.final).filter { $0.ref != Self.ref(Self.leclerc) }
        let first = FieldFinishPlace10868(
            ref: Self.ref(Self.leclerc),
            reading: FieldChooserReading10868(label: Self.finishLabel, value: .recorded(text: "1st", detail: Self.classification)))
        let hostile = Self.model(Self.input(.final, catalogue: catalogue, displayed: [Self.slot(Self.leclerc, compact: "Verstappen")], finishes: [first]))
        XCTAssertEqual(hostile.competitors.first?.resolution.original?.name, Self.verstappen.name)
        XCTAssertEqual(hostile.competitors.map(hostile.keyShape), [.diamond])

        // A slot that does not resolve keeps its own supplied shape and neighbours keep theirs;
        // the view draws no key without a resolved original.
        let foreign = FieldHeadlineSlot10868(
            ref: Self.ref(Self.leclerc.market, Self.leclerc.outcome, scope: "constructed:f1:other-race"),
            name: Self.leclerc.name, compactName: Self.leclerc.compact, keyShape: .diamond)
        let mixed = Self.model(Self.input(displayed: [Self.slot(Self.verstappen), foreign, Self.slot(Self.hamilton)]))
        XCTAssertNil(mixed.competitors[1].resolution.original)
        XCTAssertEqual(mixed.competitors.map(mixed.keyShape), [.circle, .diamond, .square])
        XCTAssertEqual(mixed.competitors[2].metrics, Self.competitor(Self.model(), Self.hamilton)?.metrics)
    }

    func testTheKeyIsHollowBeforeTheStartAndFilledDuringAndAfterTheRace() {
        let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: 10) ?? 0
        let frame = CGSize(width: side, height: side)
        for moment in Self.moments {
            let model = Self.model(Self.input(moment))
            XCTAssertEqual(model.keyIsHollow, moment == .before, "\(moment)")
            for competitor in model.competitors {
                let shape = model.keyShape(competitor)
                guard let plan = FieldHeadlineGeometry10868.keyPlan(shape, hollow: model.keyIsHollow, in: frame, diameter: 10, lineWidth: 2) else {
                    XCTFail("\(moment) \(shape)")
                    continue
                }
                XCTAssertEqual(plan.shape, shape, "\(moment)")
                XCTAssertEqual(plan.hollow, moment == .before, "\(moment)")
                XCTAssertEqual(plan.outline == nil, moment != .before, "\(moment)")
                XCTAssertEqual(plan.stroke == nil, moment != .before, "\(moment)")
            }
        }

        // The owner's phase alone decides: later readings and finishes riding along before the
        // start keep it hollow; a final with no finishes or state, or a lap with no progress, stays filled.
        let before = Self.model(Self.input(.before, pairs: Self.drivers.map { Self.pair($0, .lap(2)) }))
        XCTAssertTrue(before.keyIsHollow)
        XCTAssertFalse(Self.model(Self.input(.final, finishes: [], state: .some(nil))).keyIsHollow)
        XCTAssertFalse(Self.model(Self.input(.lap(0), state: .some(nil))).keyIsHollow)
    }

    func testANeutralRecordedKeyIsNeverHollowAndTheDefaultKeepsThePhaseConvention() {
        // Default: unchanged for every existing owner.
        XCTAssertEqual(Self.input(.before).keyTreatment, .phaseDefault)
        XCTAssertTrue(Self.model(Self.input(.before)).keyIsHollow)
        XCTAssertFalse(Self.model(Self.input(.lap(1))).keyIsHollow)
        XCTAssertFalse(Self.model(Self.input(.final)).keyIsHollow)
        // An owner with no qualified pre-event baseline: neutral in every phase, mixed and absent slots included.
        for moment: Moment in [.before, .lap(1), .final] {
            var neutral = Self.input(moment)
            neutral.keyTreatment = .neutralRecorded
            XCTAssertFalse(Self.model(neutral).keyIsHollow, "\(moment)")
            // Display meaning only: the phase, readings and identities are the default input's.
            var restored = neutral
            restored.keyTreatment = .phaseDefault
            XCTAssertEqual(restored, Self.input(moment), "\(moment)")
            XCTAssertEqual(Self.model(neutral).competitors.map(\.metrics),
                           Self.model(Self.input(moment)).competitors.map(\.metrics), "\(moment)")
        }
        // CONSTRUCTED: one displayed slot that names no catalogue original.
        var mixed = Self.input(.before, displayed: [Self.slot(Self.drivers[0]), FieldHeadlineSlot10868(
            ref: Self.ref("absent-market", "absent-outcome"), name: "Absent driver", compactName: nil, keyShape: .square)])
        mixed.keyTreatment = .neutralRecorded
        XCTAssertFalse(Self.model(mixed).keyIsHollow)
        var absent = Self.input(.before, displayed: [])
        absent.keyTreatment = .neutralRecorded
        XCTAssertFalse(Self.model(absent).keyIsHollow)
    }

    func testTheKeyPlanDrawsThreeDistinctShapesAtTheReferenceProportionsInsideOneFrame() {
        // The reference `HistoryTeamMark`: a circle of radius r, a diamond reaching 1.2 r, a square of side 1.6 r.
        let extents: [(FieldHeadlineKeyShape10868, CGFloat)] = [(.circle, 1), (.diamond, 1.2), (.square, 0.8)]
        for diameter: CGFloat in [10, 13, 17, 23, 31] {
            guard let side = FieldHeadlineGeometry10868.keyFrameSide(diameter: diameter) else {
                XCTFail("\(diameter)")
                continue
            }
            // One frame for every shape, sized by the widest (the diamond), so the names line up.
            XCTAssertEqual(side, diameter * 1.2, accuracy: 1e-9)
            for size in [CGSize(width: side, height: side), CGSize(width: side + 30, height: side + 8)] {
                let canvas = CGRect(origin: .zero, size: size)
                for hollow in [true, false] {
                    var plans: [FieldHeadlineKeyPlan10868] = []
                    for (shape, ratio) in extents {
                        guard let plan = FieldHeadlineGeometry10868.keyPlan(shape, hollow: hollow, in: size, diameter: diameter, lineWidth: 2) else {
                            XCTFail("\(diameter) \(size) \(shape) \(hollow)")
                            continue
                        }
                        let bounds = plan.bounds
                        XCTAssertTrue([bounds.minX, bounds.minY, bounds.width, bounds.height].allSatisfy(\.isFinite))
                        XCTAssertEqual(bounds.width, diameter * ratio, accuracy: 1e-9)
                        XCTAssertEqual(bounds.height, diameter * ratio, accuracy: 1e-9)
                        XCTAssertEqual(bounds.midX, size.width / 2, accuracy: 1e-9)
                        XCTAssertEqual(bounds.midY, size.height / 2, accuracy: 1e-9)
                        XCTAssertTrue(canvas.contains(bounds), "\(shape)")
                        // The drawn fill is exactly the shape's extent.
                        let drawn = plan.fill.boundingRect
                        XCTAssertEqual(drawn.minX, bounds.minX, accuracy: 1e-6)
                        XCTAssertEqual(drawn.maxX, bounds.maxX, accuracy: 1e-6)
                        XCTAssertEqual(drawn.minY, bounds.minY, accuracy: 1e-6)
                        XCTAssertEqual(drawn.maxY, bounds.maxY, accuracy: 1e-6)
                        if hollow, let outline = plan.outline, let stroke = plan.stroke {
                            let inset: CGFloat = shape == .diamond ? 2.squareRoot() : 1
                            XCTAssertEqual(outline.minX, bounds.minX + inset, accuracy: 1e-9)
                            XCTAssertEqual(outline.width, bounds.width - 2 * inset, accuracy: 1e-9)
                            XCTAssertEqual(outline.midY, bounds.midY, accuracy: 1e-9)
                            // The outline's outer edge, as the view strokes it, is the shape's own edge: never outside it.
                            let edge = stroke.strokedPath(StrokeStyle(lineWidth: plan.lineWidth)).boundingRect
                            XCTAssertEqual(edge.minX, bounds.minX, accuracy: 0.01, "\(shape)")
                            XCTAssertEqual(edge.maxX, bounds.maxX, accuracy: 0.01, "\(shape)")
                            XCTAssertEqual(edge.minY, bounds.minY, accuracy: 0.01, "\(shape)")
                            XCTAssertEqual(edge.maxY, bounds.maxY, accuracy: 0.01, "\(shape)")
                        } else {
                            XCTAssertFalse(hollow, "\(shape)")
                            XCTAssertNil(plan.outline)
                            XCTAssertNil(plan.stroke)
                        }
                        plans.append(plan)
                    }
                    // Three distinct shapes from the exact paths the view fills: probe points that only
                    // the square, only the diamond, and the circle and square (not the diamond) contain.
                    guard plans.count == 3 else { continue }
                    let c = CGPoint(x: size.width / 2, y: size.height / 2)
                    let r = diameter / 2
                    let probes: [(CGPoint, [Bool])] = [
                        (c, [true, true, true]),
                        (CGPoint(x: c.x + 0.75 * r, y: c.y + 0.75 * r), [false, false, true]),
                        (CGPoint(x: c.x, y: c.y - 1.1 * r), [false, true, false]),
                        (CGPoint(x: c.x + 0.68 * r, y: c.y + 0.68 * r), [true, false, true]),
                    ]
                    for (point, expected) in probes {
                        XCTAssertEqual(plans.map { $0.fill.contains(point) }, expected, "\(diameter) \(point)")
                    }
                    XCTAssertEqual(Set(plans.map(\.shape)).count, 3)
                    XCTAssertNotEqual(plans[0].fill, plans[1].fill)
                    XCTAssertNotEqual(plans[1].fill, plans[2].fill)
                    XCTAssertNotEqual(plans[0].fill, plans[2].fill)
                }
            }
        }
    }

    func testTheKeyPlanDrawsNothingForAnUndrawableDiameterLineOrFrame() {
        let frame = CGSize(width: 12, height: 12)
        for shape in FieldHeadlineKeyShape10868.allCases {
            for bad: CGFloat in [0, -10, .nan, .infinity, -.infinity, .greatestFiniteMagnitude] {
                XCTAssertNil(FieldHeadlineGeometry10868.keyFrameSide(diameter: bad), "\(bad)")
                XCTAssertNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: false, in: frame, diameter: bad, lineWidth: 2), "\(shape) \(bad)")
                XCTAssertNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: true, in: frame, diameter: 10, lineWidth: bad), "\(shape) \(bad)")
                XCTAssertNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: false, in: frame, diameter: 10, lineWidth: bad), "\(shape) \(bad)")
            }
            // A frame that cannot hold the widest shape draws none — never a clipped or shrunken key.
            for size in [CGSize(width: 11.9, height: 12), CGSize(width: 12, height: 11.9), .zero,
                         CGSize(width: CGFloat.nan, height: 12), CGSize(width: 12, height: CGFloat.infinity)] {
                XCTAssertNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: false, in: size, diameter: 10, lineWidth: 2), "\(shape) \(size)")
            }
            // A finite line too wide to inset — up to the largest finite value — leaves no hollow plan, never a non-finite one.
            for wide: CGFloat in [.greatestFiniteMagnitude, .greatestFiniteMagnitude / 2, 1e300] {
                XCTAssertNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: true, in: frame, diameter: 10, lineWidth: wide), "\(shape) \(wide)")
            }
            // A line too wide to leave a hollow key an inside draws none; the same line on a filled key is fine.
            XCTAssertNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: true, in: frame, diameter: 10, lineWidth: 5), "\(shape)")
            XCTAssertNotNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: false, in: frame, diameter: 10, lineWidth: 5), "\(shape)")
            XCTAssertNotNil(FieldHeadlineGeometry10868.keyPlan(shape, hollow: true, in: frame, diameter: 10, lineWidth: 2), "\(shape)")
        }
    }
}

// MARK: - #10868 racing win/podium required-card cases
// PREPARED / NOT RUN. Exact retained 22 pairs and 75 canonical original refs;
// words/phase/selection/formatting below simulate the owner contract, not an app
// adapter. No fixture loading, matching or lifecycle policy in the product view.

final class FieldRacingWinPodiumPresentation10868Tests: XCTestCase {
    private static let scope = "constructed:f1:singapore-2026:win-podium"
    private struct PairCase {
        let id: String
        let name: String
        let winIndex: Int
        let podiumIndex: Int
        let winValue: Double?
        let winText: String?
        let winDetail: String?
        let podiumValue: Double?
        let podiumText: String?
        let podiumDetail: String?
        let winResult: String
        let podiumResult: String
        let finish: String
    }
    private static let canonical: [(FieldChooserOriginalRef10868, String)] = [
        (.init(scope: scope, source: "polymarket", marketID: "5229406", outcomeID: "105026689771335810478914327541724319323338915766526076386906176141135574302746"), "Max Verstappen"),
        (.init(scope: scope, source: "polymarket", marketID: "5229411", outcomeID: "9518453683994039663103190001640433279731056992400699084747973794695685716810"), "Lewis Hamilton"),
        (.init(scope: scope, source: "polymarket", marketID: "5229402", outcomeID: "92443082174901362958213182894863948289679800011664028904195269564952495193793"), "Charles Leclerc"),
        (.init(scope: scope, source: "polymarket", marketID: "5229405", outcomeID: "5696133373196488147875236821860681766749634665413742392928884679633318673226"), "Kimi Antonelli"),
        (.init(scope: scope, source: "polymarket", marketID: "5229404", outcomeID: "50434279802004157692776355100568844573677746234993201217816404234694902233906"), "Lando Norris"),
        (.init(scope: scope, source: "polymarket", marketID: "5229413", outcomeID: "92166685409924243611608345305761239418833259618841446683252071008964493612883"), "Oscar Piastri"),
        (.init(scope: scope, source: "polymarket", marketID: "5229414", outcomeID: "56718796378955317111468916340265911522929583552165139147928588786823433132601"), "George Russell"),
        (.init(scope: scope, source: "polymarket", marketID: "5229408", outcomeID: "112114148297929537173847598641186061156229360765636408243334062234430064452907"), "Carlos Sainz Jr."),
        (.init(scope: scope, source: "polymarket", marketID: "5229416", outcomeID: "5925247658760843939848257679933962433517180533220416892662406179964839647949"), "Isack Hadjar"),
        (.init(scope: scope, source: "polymarket", marketID: "5229398", outcomeID: "24946613243542045093782896030972508052414682034023350754030313581675845916465"), "Fernando Alonso"),
        (.init(scope: scope, source: "polymarket", marketID: "5229417", outcomeID: "59218091277618579146661875012717821529527136170610280346022356243553006480870"), "Liam Lawson"),
        (.init(scope: scope, source: "polymarket", marketID: "5229409", outcomeID: "46633357118097927706875836765976613273002880284113105333660319153040915921433"), "Nico Hulkenberg"),
        (.init(scope: scope, source: "polymarket", marketID: "5229410", outcomeID: "37377009617262886055248856685172953678066728775153467706615477067585995032236"), "Valtteri Bottas"),
        (.init(scope: scope, source: "polymarket", marketID: "5229412", outcomeID: "22577247696951783128672169989438357120216379084843314121733136822205330394386"), "Oliver Bearman"),
        (.init(scope: scope, source: "polymarket", marketID: "5229415", outcomeID: "35806167495708067688142660894515436986537444155410197985851888007006540375369"), "Arvid Lindblad"),
        (.init(scope: scope, source: "polymarket", marketID: "5229418", outcomeID: "17728978960408046070104397306363646944957497115347892906141065161648077901163"), "Lance Stroll"),
        (.init(scope: scope, source: "polymarket", marketID: "5229419", outcomeID: "80737513999194638178280916250352918609409177325807266190011527655594912137851"), "Yuki Tsunoda"),
        (.init(scope: scope, source: "polymarket", marketID: "5229399", outcomeID: "20899351361659882916278870698966147459616666433222997076649183873101393641787"), "Alexander Albon"),
        (.init(scope: scope, source: "polymarket", marketID: "5229400", outcomeID: "2835735619366113132331629458875618026032260678708439186410341002678206064734"), "Gabriel Bortoleto"),
        (.init(scope: scope, source: "polymarket", marketID: "5229401", outcomeID: "83652434777062733522317823357052014621993834306632156362686898553393933523458"), "Sergio Perez"),
        (.init(scope: scope, source: "polymarket", marketID: "5229403", outcomeID: "110900142078134549566830658584183223162291771163731239731531646173931267218149"), "Esteban Ocon"),
        (.init(scope: scope, source: "polymarket", marketID: "5229407", outcomeID: "4367879003640045686956388825375902266684763445371199130205596602619739253591"), "Franco Colapinto"),
        (.init(scope: scope, source: "polymarket", marketID: "5229397", outcomeID: "28558391061191296576456870322949545965070312914289181555918414954825561771030"), "Pierre Gasly"),
        (.init(scope: scope, source: "polymarket", marketID: "5229633", outcomeID: "110857599143644098992681976807171712355534104947335334189871164576023031815555"), "Max Verstappen"),
        (.init(scope: scope, source: "polymarket", marketID: "5229629", outcomeID: "81777712267167882804825483696208495691212603231475789493999361725169140070707"), "Charles Leclerc"),
        (.init(scope: scope, source: "polymarket", marketID: "5229638", outcomeID: "107223488373792995670853625575479347904333591818058137730381400388579385546848"), "Lewis Hamilton"),
        (.init(scope: scope, source: "polymarket", marketID: "5229632", outcomeID: "93588786206279515298378425874328319850883491696258124247716491516547375534226"), "Kimi Antonelli"),
        (.init(scope: scope, source: "polymarket", marketID: "5229631", outcomeID: "91266558960626318800007488387086012785670848799467791981959112065990484864616"), "Lando Norris"),
        (.init(scope: scope, source: "polymarket", marketID: "5229640", outcomeID: "91254622187005296521266595966212220061366684245037347501894715001919789190753"), "Oscar Piastri"),
        (.init(scope: scope, source: "polymarket", marketID: "5229641", outcomeID: "48577678514819085078699880361241457992337880684158047380851450932928459872200"), "George Russell"),
        (.init(scope: scope, source: "polymarket", marketID: "5229646", outcomeID: "20389784775884582247749385164360943880067183172628624763938264759036675697715"), "Yuki Tsunoda"),
        (.init(scope: scope, source: "polymarket", marketID: "5229643", outcomeID: "73022736280294057069609534442862001943197948167325502370815577406169725034775"), "Isack Hadjar"),
        (.init(scope: scope, source: "polymarket", marketID: "5229624", outcomeID: "87453145948323530683093142170131029583090664604716403936211065150093975501602"), "Pierre Gasly"),
        (.init(scope: scope, source: "polymarket", marketID: "5229644", outcomeID: "33230546474917362926564085275893645857309224237479558353480796418752326055304"), "Liam Lawson"),
        (.init(scope: scope, source: "polymarket", marketID: "5229642", outcomeID: "74418053695910050098251154274261102238652619962310301587320294136005596880377"), "Arvid Lindblad"),
        (.init(scope: scope, source: "polymarket", marketID: "5229625", outcomeID: "18387701778833574956754249887029772709271827126644156983285721399815810792992"), "Fernando Alonso"),
        (.init(scope: scope, source: "polymarket", marketID: "5229634", outcomeID: "96209521069947352832106981216115838872905539746697545272969446534824159185351"), "Franco Colapinto"),
        (.init(scope: scope, source: "polymarket", marketID: "5229627", outcomeID: "5536126596058197620947728468486185325150227529245357066692180534751937918211"), "Gabriel Bortoleto"),
        (.init(scope: scope, source: "polymarket", marketID: "5229635", outcomeID: "21099583028461586672480695290502304110814989010954493894314247689103698679827"), "Carlos Sainz Jr."),
        (.init(scope: scope, source: "polymarket", marketID: "5229630", outcomeID: "107579886745075038202250809930504945630616058165883684791018285923144296900320"), "Esteban Ocon"),
        (.init(scope: scope, source: "polymarket", marketID: "5229637", outcomeID: "70829314418231113229603197020787104655220492519845789616173317634590446065261"), "Valtteri Bottas"),
        (.init(scope: scope, source: "polymarket", marketID: "5229626", outcomeID: "36958804519639427780282363944661840022193973378862741937678054521049286386807"), "Alexander Albon"),
        (.init(scope: scope, source: "polymarket", marketID: "5229628", outcomeID: "38920286751886432926911405748215593390993793890929458803986070911095534135866"), "Sergio Perez"),
        (.init(scope: scope, source: "polymarket", marketID: "5229645", outcomeID: "99035375931778084321615410336433575315218165292425804029498168493607815844379"), "Lance Stroll"),
        (.init(scope: scope, source: "polymarket", marketID: "5229636", outcomeID: "40753676215478901061354185338534230390231681673691988568754789894877991728635"), "Nico Hulkenberg"),
        (.init(scope: scope, source: "polymarket", marketID: "5229639", outcomeID: "38393213436151514371775514758695461422541031352103503278188888358162116834906"), "Oliver Bearman"),
        (.init(scope: scope, source: "polymarket", marketID: "5229621", outcomeID: "33331488134321289504801551659522059050212493202921720814700311861082309692009"), "Hamilton — Hamilton vs Piastri"),
        (.init(scope: scope, source: "polymarket", marketID: "5229612", outcomeID: "7090122560978114151159241097823824193070045048886498702882654777211320166186"), "Leclerc — Leclerc vs Russell"),
        (.init(scope: scope, source: "polymarket", marketID: "5229617", outcomeID: "4068713068528441296831042056180611328829965381921185174724790408885477085376"), "Norris — Norris vs Russell"),
        (.init(scope: scope, source: "polymarket", marketID: "5229600", outcomeID: "110909128388621583528027995078471646758296891348314740700292566482823861330730"), "Alonso — Alonso vs Stroll"),
        (.init(scope: scope, source: "polymarket", marketID: "5229604", outcomeID: "30828121593085071903092865373527569539214466840198501035754721592064994702046"), "Leclerc — Leclerc vs Hamilton"),
        (.init(scope: scope, source: "polymarket", marketID: "5229618", outcomeID: "24814557986804912717525396491551950567731074765190854754056431039942873350501"), "Verstappen — Verstappen vs Hamilton"),
        (.init(scope: scope, source: "polymarket", marketID: "5229488", outcomeID: "2591374099559395253718883338821225955484795878731663629478621088184458436077"), "Max Verstappen"),
        (.init(scope: scope, source: "polymarket", marketID: "5229493", outcomeID: "26128000172307458556562604682667588959839117017600094179451615450544110291374"), "Lewis Hamilton"),
        (.init(scope: scope, source: "polymarket", marketID: "5229484", outcomeID: "113074849230542221111579369802690109874785517423609665045620204211923938532132"), "Charles Leclerc"),
        (.init(scope: scope, source: "polymarket", marketID: "5229496", outcomeID: "69091165673113707821952123449217252259896209513255365069454973665287428858566"), "George Russell"),
        (.init(scope: scope, source: "polymarket", marketID: "5229486", outcomeID: "71566812110811182468394622972187711783186293932959978471601123622936149006437"), "Lando Norris"),
        (.init(scope: scope, source: "polymarket", marketID: "5229487", outcomeID: "28225730157221911414837039362281622918871472023499900047141665660095870686215"), "Kimi Antonelli"),
        (.init(scope: scope, source: "polymarket", marketID: "5229498", outcomeID: "103483603311016169319312114776012863628659744762203324695647183613843329932112"), "Isack Hadjar"),
        (.init(scope: scope, source: "polymarket", marketID: "5229495", outcomeID: "113870944931080893581151995561608716268501303475993539576096255854502955492276"), "Oscar Piastri"),
        (.init(scope: scope, source: "polymarket", marketID: "5229489", outcomeID: "70884389017472998068956496869243231034693127519617203467418865835880820482785"), "Franco Colapinto"),
        (.init(scope: scope, source: "polymarket", marketID: "5229500", outcomeID: "36969303612488996956507685417579522699141402648309540215688732939831194740051"), "Lance Stroll"),
        (.init(scope: scope, source: "polymarket", marketID: "5229483", outcomeID: "22167621134500002236758899645184473355570659819263985906614787813786691721030"), "Sergio Perez"),
        (.init(scope: scope, source: "polymarket", marketID: "5229481", outcomeID: "82841373926297244567961403070618059268118839274372150642644645777215454102840"), "Alexander Albon"),
        (.init(scope: scope, source: "polymarket", marketID: "5229492", outcomeID: "50033331166900902238496754075390446021588636997182535677811844195072697881149"), "Valtteri Bottas"),
        (.init(scope: scope, source: "polymarket", marketID: "5229479", outcomeID: "63270863974452993271524558641066072795614556815649198640620203389325503101307"), "Pierre Gasly"),
        (.init(scope: scope, source: "polymarket", marketID: "5229480", outcomeID: "76147060615984389286618572057004607834846979634815560653181983737717442789749"), "Fernando Alonso"),
        (.init(scope: scope, source: "polymarket", marketID: "5229485", outcomeID: "52260232229041890478485638214731562331576098956208366313921603249471215791478"), "Esteban Ocon"),
        (.init(scope: scope, source: "polymarket", marketID: "5229491", outcomeID: "109578030417969707247021105786855642324572377718130068164229332475006938294977"), "Nico Hulkenberg"),
        (.init(scope: scope, source: "polymarket", marketID: "5229497", outcomeID: "61734884068413260382961879435677743258460901995938169786243728043635825118834"), "Arvid Lindblad"),
        (.init(scope: scope, source: "polymarket", marketID: "5229499", outcomeID: "75065405456029042574706141909485482536573163465452073348782299937074328910578"), "Liam Lawson"),
        (.init(scope: scope, source: "polymarket", marketID: "5229494", outcomeID: "3573637962077248432080539224215115931395302546255227719914533046680829117401"), "Oliver Bearman"),
        (.init(scope: scope, source: "polymarket", marketID: "5229490", outcomeID: "19530433398265004109975999830689410930998548542652494070320878237863685366147"), "Carlos Sainz Jr."),
        (.init(scope: scope, source: "polymarket", marketID: "5229501", outcomeID: "22290850904385371225730409519828833030822513237562163307339926592219044659462"), "Yuki Tsunoda"),
        (.init(scope: scope, source: "polymarket", marketID: "5229482", outcomeID: "98309314565714537847497666396177854204578598906954404335647963267440860619564"), "Gabriel Bortoleto"),
    ]
    private static let cases: [PairCase] = [
        .init(id: "4665", name: "Max Verstappen", winIndex: 0, podiumIndex: 23, winValue: 0.6499999935, winText: "65%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:59:31+00:00", podiumValue: 0.8199999967, podiumText: "82%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T11:57:07+00:00", winResult: "Won", podiumResult: "Won", finish: "1st"),
        .init(id: "5498", name: "Charles Leclerc", winIndex: 2, podiumIndex: 24, winValue: 0.1399999999, winText: "14%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:59:46+00:00", podiumValue: 0.6666666667, podiumText: "66.7%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T11:59:00+00:00", winResult: "Lost", podiumResult: "Won", finish: "2nd"),
        .init(id: "868", name: "Lewis Hamilton", winIndex: 1, podiumIndex: 25, winValue: 0.16, winText: "16%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:59:19+00:00", podiumValue: 0.609999986, podiumText: "61%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T11:58:06+00:00", winResult: "Lost", podiumResult: "Lost", finish: "6th"),
        .init(id: "5829", name: "Kimi Antonelli", winIndex: 3, podiumIndex: 26, winValue: 0.08, winText: "8%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:59:09+00:00", podiumValue: 0.4799998464, podiumText: "48%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T11:59:15+00:00", winResult: "Lost", podiumResult: "Won", finish: "3rd"),
        .init(id: "5579", name: "Lando Norris", winIndex: 4, podiumIndex: 27, winValue: 0.025, winText: "2.5%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:52:54+00:00", podiumValue: 0.2899999884, podiumText: "29%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T11:49:21+00:00", winResult: "Lost", podiumResult: "Lost", finish: "4th"),
        .init(id: "5752", name: "Oscar Piastri", winIndex: 5, podiumIndex: 28, winValue: 0.013192724, winText: "1.3%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:05:15+00:00", podiumValue: 0.1699999997, podiumText: "17%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T08:32:21+00:00", winResult: "Lost", podiumResult: "Lost", finish: "5th"),
        .init(id: "5503", name: "George Russell", winIndex: 6, podiumIndex: 29, winValue: 0.01, winText: "1%", winDetail: "Polymarket selected-side trade · 2026-10-11T11:53:07+00:00", podiumValue: 0.0636363633, podiumText: "6.4%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T11:59:19+00:00", winResult: "Lost", podiumResult: "Lost", finish: "9th"),
        .init(id: "5790", name: "Isack Hadjar", winIndex: 8, podiumIndex: 31, winValue: 0.002, winText: "0.2%", winDetail: "Polymarket selected-side trade · 2026-10-11T06:57:53+00:00", podiumValue: 0.021, podiumText: "2.1%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T06:16:29+00:00", winResult: "Lost", podiumResult: "Lost", finish: "10th"),
        .init(id: "5741", name: "Liam Lawson", winIndex: 10, podiumIndex: 33, winValue: 0.001, winText: "0.1%", winDetail: "Polymarket selected-side trade · 2026-10-10T15:24:43+00:00", podiumValue: 0.018, podiumText: "1.8%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T10:01:27+00:00", winResult: "Lost", podiumResult: "Lost", finish: "7th"),
        .init(id: "5501", name: "Pierre Gasly", winIndex: 22, podiumIndex: 32, winValue: nil, winText: nil, winDetail: nil, podiumValue: 0.0169999999, podiumText: "1.7%", podiumDetail: "Polymarket selected-side trade · 2026-10-11T10:42:08+00:00", winResult: "Lost", podiumResult: "Lost", finish: "11th"),
        .init(id: "5592", name: "Alexander Albon", winIndex: 17, podiumIndex: 41, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "18th"),
        .init(id: "5855", name: "Arvid Lindblad", winIndex: 14, podiumIndex: 34, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "15th"),
        .init(id: "4686", name: "Carlos Sainz Jr.", winIndex: 7, podiumIndex: 38, winValue: 0.001, winText: "0.1%", winDetail: "Polymarket selected-side trade · 2026-10-10T22:52:03+00:00", podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "14th"),
        .init(id: "4678", name: "Esteban Ocon", winIndex: 20, podiumIndex: 39, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "13th"),
        .init(id: "348", name: "Fernando Alonso", winIndex: 9, podiumIndex: 35, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "16th"),
        .init(id: "5823", name: "Franco Colapinto", winIndex: 21, podiumIndex: 36, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "21st"),
        .init(id: "5835", name: "Gabriel Bortoleto", winIndex: 18, podiumIndex: 37, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "22nd"),
        .init(id: "4775", name: "Lance Stroll", winIndex: 15, podiumIndex: 43, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "20th"),
        .init(id: "4396", name: "Nico Hulkenberg", winIndex: 11, podiumIndex: 44, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "8th"),
        .init(id: "5789", name: "Oliver Bearman", winIndex: 13, podiumIndex: 45, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "12th"),
        .init(id: "4472", name: "Sergio Perez", winIndex: 19, podiumIndex: 42, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "17th"),
        .init(id: "4520", name: "Valtteri Bottas", winIndex: 12, podiumIndex: 40, winValue: nil, winText: nil, winDetail: nil, podiumValue: nil, podiumText: nil, podiumDetail: nil, winResult: "Lost", podiumResult: "Lost", finish: "19th"),
    ]

    private static let copy = FieldPodiumCopy10868(
        title: "Win and podium chances", explanation: "Podium means finishing in the top three.",
        beforeContext: "Pre-race chances", duringContext: "Pre-race chances · No recent update",
        finalContext: "Pre-race chances and reported finish", winLabel: "Win", podiumLabel: "Finish top 3",
        beforeLabel: "Pre-race", pairUnavailable: "Driver pairing unavailable in this update",
        chanceUnavailable: "Pre-race chance unavailable", noSelection: "Choose a driver",
        outsideWindow: "Selected driver is outside this group", finishLabel: "Reported finish",
        finishUnavailable: "Finish not confirmed", resultLabel: "Prop result", resultUnknown: "Result unconfirmed",
        previousLabel: "Previous driver", nextLabel: "Next driver", chooseHint: "Show this driver's two chances",
        originalHint: "Open this exact original prop", aboutLabel: "About the pre-race comparison",
        aboutHint: "Read observation sources and times")
    private static let scale = FieldOutlookScale10868(ceiling: 1,
        ticks: [.init(probability: 0, label: "0%"), .init(probability: 0.5, label: "50%"), .init(probability: 1, label: "100%")],
        words: "0–100% pre-race chance")
    private static let phases: [FieldOutlookPhase10868] = [.before, .during, .final]

    private static func before(_ text: String?, _ detail: String?) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Pre-race", value: text.map { .recorded(text: $0, detail: detail ?? "") }
            ?? .missing("No pre-race trade recorded"))
    }
    private static func original(_ ref: FieldChooserOriginalRef10868, name: String,
                                 before: FieldChooserReading10868, result: String?) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(ref: ref, name: name,
            plan: .comparison(before: before, later: .init(label: "LATER CONTROL", value: .recorded(text: "100% SETTLED CONTROL", detail: "LATER CLOCK CONTROL"))),
            preview: .init(history: nil, absence: "History supplied separately"), movement: "LATER MOVEMENT CONTROL",
            clock: "LATER CLOCK CONTROL", result: result.map { .init(title: "Prop result", words: $0) },
            browseStatus: "Original prop")
    }
    private static var catalogue: [FieldChooserOriginal10868] {
        canonical.enumerated().map { index, item in
            if let p = cases.first(where: { $0.winIndex == index }) {
                return original(item.0, name: item.1, before: before(p.winText, p.winDetail), result: p.winResult)
            }
            if let p = cases.first(where: { $0.podiumIndex == index }) {
                return original(item.0, name: item.1, before: before(p.podiumText, p.podiumDetail), result: p.podiumResult)
            }
            // Retain the unrelated originals, including six named head-to-head
            // sides. Their chances are outside this paired-card fixture.
            return original(item.0, name: item.1, before: before(nil, nil), result: nil)
        }
    }
    private static var pairs: [FieldPodiumPair10868] {
        cases.map { .init(id: $0.id, name: $0.name, win: canonical[$0.winIndex].0, podium: canonical[$0.podiumIndex].0) }
    }
    private static func slot(_ pair: FieldPodiumPair10868) -> FieldPodiumSlot10868 {
        .init(pairID: pair.id, name: pair.name, compactName: nil)
    }
    private static var chances: [FieldOutlookBeforeChance10868] {
        cases.flatMap { p -> [FieldOutlookBeforeChance10868] in
            var out: [FieldOutlookBeforeChance10868] = []
            if let value = p.winValue { out.append(.init(ref: canonical[p.winIndex].0, probability: value, reading: before(p.winText, p.winDetail))) }
            if let value = p.podiumValue { out.append(.init(ref: canonical[p.podiumIndex].0, probability: value, reading: before(p.podiumText, p.podiumDetail))) }
            return out
        }
    }
    private static var finishes: [FieldFinishPlace10868] {
        cases.map { .init(ref: canonical[$0.winIndex].0, reading: .init(label: "Reported finish", value: .recorded(text: $0.finish,
            detail: "ESPN classification captured Oct 12 · Exact finish time not supplied"))) }
    }
    private static func input(_ phase: FieldOutlookPhase10868 = .during,
                              catalogue: [FieldChooserOriginal10868]? = nil, pairs: [FieldPodiumPair10868]? = nil,
                              displayed: [FieldPodiumSlot10868]? = nil, selected: String? = "5829",
                              previous: String? = "868", next: String? = "5579",
                              chances: [FieldOutlookBeforeChance10868]? = nil, finishes: [FieldFinishPlace10868]? = nil,
                              scale: FieldOutlookScale10868? = nil) -> FieldPodiumInput10868 {
        .init(scope: scope, catalogue: catalogue ?? Self.catalogue, pairs: pairs ?? Self.pairs,
              displayed: displayed ?? Array(Self.pairs.prefix(5)).map(slot), selectedID: selected,
              previousID: previous, nextID: next, chances: chances ?? Self.chances,
              finishes: finishes ?? Self.finishes, scale: scale ?? Self.scale, phase: phase,
              winTint: .blue, podiumTint: .orange, copy: copy)
    }
    private static func figure(_ endpoint: FieldPodiumEndpoint10868?) -> String? {
        endpoint.flatMap { FieldChaseModel10868.figure($0.reading) }
    }

    func testAllRetainedPairsKeepTheFullCatalogueAndTheirOwnBaselinesAcrossAllThreePhases() {
        XCTAssertEqual(Self.canonical.count, 75)
        XCTAssertEqual(Set(Self.canonical.map(\.0)).count, 75)
        XCTAssertEqual(Self.pairs.count, 22)
        XCTAssertEqual(Self.chances.count, 20)
        for phase in Self.phases {
            for p in Self.cases {
                let model = FieldPodiumModel10868(Self.input(phase, selected: p.id))
                XCTAssertEqual(model.input.catalogue.map(\.ref), Self.canonical.map(\.0))
                XCTAssertEqual(model.input.catalogue.map(\.name), Self.canonical.map(\.1))
                XCTAssertEqual(model.input.pairs, Self.pairs)
                XCTAssertEqual(model.selected?.win?.ref, Self.canonical[p.winIndex].0)
                XCTAssertEqual(model.selected?.podium?.ref, Self.canonical[p.podiumIndex].0)
                XCTAssertEqual(model.selected?.win?.chance.fraction, p.winValue)
                XCTAssertEqual(model.selected?.podium?.chance.fraction, p.podiumValue)
                XCTAssertEqual(Self.figure(model.selected?.win), p.winText)
                XCTAssertEqual(Self.figure(model.selected?.podium), p.podiumText)
                XCTAssertEqual(model.input.catalogue.count, 75)
                if phase == .final {
                    XCTAssertEqual(FieldFinishModel10868.ordinal(model.selectedFinish), p.finish)
                    XCTAssertEqual(model.result(model.selected?.win)?.words, p.winResult)
                    XCTAssertEqual(model.result(model.selected?.podium)?.words, p.podiumResult)
                } else {
                    XCTAssertNil(model.selectedFinish)
                    XCTAssertNil(model.result(model.selected?.win))
                    XCTAssertNil(model.result(model.selected?.podium))
                }
            }
        }
    }

    func testAntonellisEightAndFortyEightHaveDifferentOwnClocksAndIndependentFinalResults() {
        let final = FieldPodiumModel10868(Self.input(.final))
        guard let selected = final.selected else { return XCTFail("Antonelli selection") }
        XCTAssertEqual(selected.pair?.name, "Kimi Antonelli")
        XCTAssertEqual(Self.figure(selected.win), "8%")
        XCTAssertEqual(Self.figure(selected.podium), "48%")
        XCTAssertTrue(final.summary(selected).contains("11:59:09"))
        XCTAssertTrue(final.summary(selected).contains("11:59:15"))
        XCTAssertTrue(final.summary(selected).contains("Polymarket"))
        XCTAssertEqual(FieldFinishModel10868.ordinal(final.selectedFinish), "3rd")
        XCTAssertEqual(final.result(selected.win)?.words, "Lost")
        XCTAssertEqual(final.result(selected.podium)?.words, "Won")
        XCTAssertNotEqual(selected.win?.ref, selected.podium?.ref)
    }

    func testGaslyAndSainzKeepTheirOneSidedGapsWithoutBorrowingTheOtherChance() {
        for phase in Self.phases {
            let gasly = FieldPodiumModel10868(Self.input(phase, selected: "5501"))
            let sainz = FieldPodiumModel10868(Self.input(phase, selected: "4686"))
            XCTAssertNil(Self.figure(gasly.selected?.win))
            XCTAssertNotNil(Self.figure(gasly.selected?.podium))
            XCTAssertNotNil(Self.figure(sainz.selected?.win))
            XCTAssertNil(Self.figure(sainz.selected?.podium))
            XCTAssertEqual(gasly.selected?.win?.chance, .unavailable)
            XCTAssertEqual(sainz.selected?.podium?.chance, .unavailable)
            XCTAssertEqual(FieldChaseModel10868.words(gasly.selected!.win!.reading), "No pre-race trade recorded")
            XCTAssertNotNil(gasly.originalAction(gasly.selected?.win, canOpen: true))
            XCTAssertNotNil(sainz.originalAction(sainz.selected?.podium, canOpen: true))
        }
        XCTAssertEqual(Self.cases.filter { $0.winValue != nil }.count, 10)
        XCTAssertEqual(Self.cases.filter { $0.podiumValue != nil }.count, 10)
    }

    func testLaterQuoteMovementAndSettledProbabilityNeverBecomeThisCardsEarlierChances() {
        for phase in Self.phases {
            let model = FieldPodiumModel10868(Self.input(phase, displayed: Self.pairs.map(Self.slot)))
            XCTAssertEqual(model.rows.count, 22) // owner may supply more than five
            for row in model.rows {
                let summary = model.summary(row)
                XCTAssertTrue(summary.contains("Pre-race"))
                XCTAssertFalse(summary.contains("LATER"))
                XCTAssertFalse(summary.contains("SETTLED"))
                XCTAssertFalse(summary.contains("Won"))
                XCTAssertFalse(summary.contains("Lost"))
            }
        }
        XCTAssertEqual(FieldPodiumModel10868(Self.input(.before)).context, Self.copy.beforeContext)
        XCTAssertEqual(FieldPodiumModel10868(Self.input(.during)).context, Self.copy.duringContext)
        XCTAssertEqual(FieldPodiumModel10868(Self.input(.final)).context, Self.copy.finalContext)
    }

    func testGenuineZeroOneAndCoincidentMarksStayAtTheirExactOwnPositions() {
        let pair = Self.pairs[3]
        for values: (Double, Double, String, String) in [(0, 1, "0%", "100%"), (0.48, 0.48, "48%", "48%"), (0, 0, "0%", "0%")] {
            let w = Self.before(values.2, "Own earlier win clock"), p = Self.before(values.3, "Own earlier podium clock")
            let catalogue = Self.catalogue.filter { $0.ref != pair.win && $0.ref != pair.podium } + [
                Self.original(pair.win, name: pair.name, before: w, result: nil), Self.original(pair.podium, name: pair.name, before: p, result: nil)]
            let model = FieldPodiumModel10868(Self.input(catalogue: catalogue, chances: [
                .init(ref: pair.win, probability: values.0, reading: w), .init(ref: pair.podium, probability: values.1, reading: p)]))
            XCTAssertEqual(Self.figure(model.selected?.win), values.2)
            XCTAssertEqual(Self.figure(model.selected?.podium), values.3)
            guard let plan = FieldPodiumGeometry10868.plan(win: model.selected?.win?.chance.fraction,
                podium: model.selected?.podium?.chance.fraction, size: .init(width: 240, height: 24), inset: 8, diameter: 10),
                let a = plan.win, let b = plan.podium, let line = plan.connector else { XCTFail("Qualified marks"); continue }
            XCTAssertEqual(a.x, CGFloat(8 + 224 * values.0), accuracy: 1e-9)
            XCTAssertEqual(b.x, CGFloat(8 + 224 * values.1), accuracy: 1e-9)
            XCTAssertEqual(line.width, abs(a.x - b.x), accuracy: 1e-9)
            if values.0 == values.1 { XCTAssertEqual(a, b); XCTAssertEqual(line.width, 0) }
        }
    }

    func testInvalidOrContradictoryNumericTiesHideOnlyTheirOwnEndpointAndRetainTheOriginalAction() {
        let own = Self.chances.first { $0.ref == Self.pairs[3].win }!
        var controls: [[FieldOutlookBeforeChance10868]] = []
        let rest = Self.chances.filter { $0.ref != own.ref }
        controls.append(rest)
        controls.append(rest + [own, own])
        for bad: Double in [.nan, .infinity, -.infinity, -0.01, 1.01] {
            controls.append(rest + [.init(ref: own.ref, probability: bad, reading: own.reading)])
        }
        controls.append(rest + [.init(ref: own.ref, probability: own.probability,
            reading: .init(label: own.reading.label, value: .recorded(text: "8%", detail: "Wrong observation clock")))])
        controls.append(rest + [.init(ref: own.ref, probability: own.probability,
            reading: .init(label: "Pre-race", value: .missing("Withdrawn before start")))])
        let foreign = FieldChooserOriginalRef10868(scope: "other-race", source: own.ref.source, marketID: own.ref.marketID, outcomeID: own.ref.outcomeID)
        controls.append(rest + [.init(ref: foreign, probability: own.probability, reading: own.reading)])
        for ties in controls {
            let model = FieldPodiumModel10868(Self.input(chances: ties))
            XCTAssertEqual(model.selected?.win?.chance, .unavailable)
            XCTAssertNil(Self.figure(model.selected?.win))
            XCTAssertEqual(Self.figure(model.selected?.podium), "48%")
            XCTAssertEqual(model.originalAction(model.selected?.win, canOpen: true), own.ref)
            let plan = FieldPodiumGeometry10868.plan(win: model.selected?.win?.chance.fraction,
                podium: model.selected?.podium?.chance.fraction, size: .init(width: 240, height: 24), inset: 8, diameter: 10)
            XCTAssertNil(plan?.win); XCTAssertNil(plan?.connector); XCTAssertNotNil(plan?.podium)
        }
        let withdrawn = Self.before(nil, nil)
        let catalogue = Self.catalogue.map { $0.ref == own.ref ? Self.original(own.ref, name: $0.name, before: withdrawn, result: nil) : $0 }
        let model = FieldPodiumModel10868(Self.input(catalogue: catalogue))
        XCTAssertNil(Self.figure(model.selected?.win))
        XCTAssertEqual(model.selected?.win?.chance, .unavailable)
    }

    func testExactOriginalResolutionRejectsMissingDuplicateIncompleteAndForeignIdentitiesLocally() {
        let pair = Self.pairs[3]
        let win = Self.catalogue.first { $0.ref == pair.win }!
        let missing = Self.catalogue.filter { $0.ref != pair.win }
        for catalogue in [missing, Self.catalogue + [win]] {
            let model = FieldPodiumModel10868(Self.input(catalogue: catalogue))
            XCTAssertNil(model.selected?.win?.original)
            XCTAssertNil(model.originalAction(model.selected?.win, canOpen: true))
            XCTAssertEqual(Self.figure(model.selected?.podium), "48%")
            XCTAssertEqual(model.rows[0].win?.chance.fraction, Self.cases[0].winValue)
        }
        for ref in [FieldChooserOriginalRef10868(scope: "other-race", source: pair.win.source, marketID: pair.win.marketID, outcomeID: pair.win.outcomeID),
                    FieldChooserOriginalRef10868(scope: Self.scope, source: pair.win.source, marketID: "", outcomeID: pair.win.outcomeID)] {
            let changed = FieldPodiumPair10868(id: pair.id, name: "Max Verstappen", win: ref, podium: pair.podium)
            let model = FieldPodiumModel10868(Self.input(pairs: Self.pairs.map { $0.id == pair.id ? changed : $0 }))
            XCTAssertNil(model.selected?.win?.original)
            XCTAssertEqual(model.selected?.podium?.ref, pair.podium)
            XCTAssertEqual(Self.figure(model.selected?.podium), "48%")
        }
    }

    func testAmbiguousPairAndWindowReferencesDoNotCorruptValidNeighbours() {
        let pair = Self.pairs[3]
        let duplicate = FieldPodiumModel10868(Self.input(pairs: Self.pairs + [pair]))
        XCTAssertNil(duplicate.selected)
        XCTAssertNil(duplicate.rows[3].pair)
        XCTAssertEqual(duplicate.rows[0].pair, Self.pairs[0])
        let same = FieldPodiumPair10868(id: pair.id, name: pair.name, win: pair.win, podium: pair.win)
        XCTAssertNil(FieldPodiumModel10868(Self.input(pairs: Self.pairs.map { $0.id == pair.id ? same : $0 })).selected)
        let slots = [Self.slot(Self.pairs[0]), Self.slot(pair), Self.slot(pair), Self.slot(Self.pairs[4])]
        let repeated = FieldPodiumModel10868(Self.input(displayed: slots))
        XCTAssertEqual(repeated.rows.count, 4)
        XCTAssertNil(repeated.rows[1].pair); XCTAssertNil(repeated.rows[2].pair)
        XCTAssertNotNil(repeated.rows[0].pair); XCTAssertNotNil(repeated.rows[3].pair)
        XCTAssertNil(repeated.rowChoice(repeated.rows[1], canChoose: true))
        XCTAssertEqual(repeated.selected?.pair, pair) // held selection does not depend on window duplication
    }

    func testEveryPairRemainsReachableWithExactOwnerTargetsAndStaticContentHasNoAction() {
        let model = FieldPodiumModel10868(Self.input(displayed: [Self.slot(Self.pairs[0])]))
        XCTAssertTrue(model.selectionOutsideWindow)
        XCTAssertEqual(model.selected?.pair, Self.pairs[3])
        for pair in Self.pairs where pair.id != model.input.selectedID {
            XCTAssertEqual(model.chooseID(pair.id, canChoose: true), pair.id)
            XCTAssertNil(model.chooseID(pair.id, canChoose: false))
        }
        XCTAssertNil(model.chooseID(model.input.selectedID, canChoose: true))
        XCTAssertNil(model.chooseID("not-a-driver", canChoose: true))
        XCTAssertNil(model.chooseID(nil, canChoose: true))
        XCTAssertEqual(model.chooseID(model.input.previousID, canChoose: true), "868")
        XCTAssertEqual(model.chooseID(model.input.nextID, canChoose: true), "5579")
        XCTAssertEqual(model.rowChoice(model.rows[0], canChoose: true), "4665")
        XCTAssertNil(model.rowChoice(model.rows[0], canChoose: false))
        XCTAssertEqual(model.originalAction(model.selected?.win, canOpen: true), Self.pairs[3].win)
        XCTAssertEqual(model.originalAction(model.selected?.podium, canOpen: true), Self.pairs[3].podium)
        XCTAssertNil(model.originalAction(model.selected?.podium, canOpen: false))
        XCTAssertNil(FieldPodiumModel10868(Self.input(selected: nil)).selected)
        XCTAssertNil(FieldPodiumModel10868(Self.input(selected: "unknown")).selected)
    }

    func testPhysicalFinishAndEachOriginalGradeAreIndependentAndUnknownNeverBecomesLost() {
        let pair = Self.pairs[3]
        let alternate = FieldFinishPlace10868(ref: pair.win, reading: .init(label: "Reported finish", value: .recorded(text: "17th", detail: "Independent physical classification control")))
        let changed = FieldPodiumModel10868(Self.input(.final, finishes: [alternate]))
        XCTAssertEqual(FieldFinishModel10868.ordinal(changed.selectedFinish), "17th")
        XCTAssertEqual(changed.result(changed.selected?.win)?.words, "Lost")
        XCTAssertEqual(changed.result(changed.selected?.podium)?.words, "Won")
        for finishes in [[], [alternate, alternate], [.init(ref: pair.podium, reading: alternate.reading)]] as [[FieldFinishPlace10868]] {
            let model = FieldPodiumModel10868(Self.input(.final, finishes: finishes))
            XCTAssertNil(FieldFinishModel10868.ordinal(model.selectedFinish))
            XCTAssertEqual(FieldFinishModel10868.finishWords(model.selectedFinish), Self.copy.finishUnavailable)
            XCTAssertEqual(model.result(model.selected?.podium)?.words, "Won")
        }
        let catalogue = Self.catalogue.map { $0.ref == pair.win ? Self.original($0.ref, name: $0.name,
            before: FieldOutlookModel10868.beforeReading($0.plan), result: nil) : $0 }
        let noGrade = FieldPodiumModel10868(Self.input(.final, catalogue: catalogue))
        XCTAssertEqual(noGrade.result(noGrade.selected?.win)?.words, "Result unconfirmed")
        XCTAssertEqual(FieldFinishModel10868.ordinal(noGrade.selectedFinish), "3rd")
        XCTAssertEqual(Self.figure(noGrade.selected?.win), "8%")
    }

    func testUndrawableAxisKeepsTheSameReadableValuesAndActionsWithNoFabricatedScale() {
        for scale in [FieldOutlookScale10868(ceiling: 0.5, ticks: Self.scale.ticks, words: Self.scale.words),
                      FieldOutlookScale10868(ceiling: 1, ticks: [], words: Self.scale.words),
                      FieldOutlookScale10868(ceiling: 1, ticks: Self.scale.ticks + [Self.scale.ticks[0]], words: Self.scale.words),
                      FieldOutlookScale10868(ceiling: 1, ticks: Self.scale.ticks, words: " ")] {
            let model = FieldPodiumModel10868(Self.input(scale: scale))
            XCTAssertFalse(model.canDraw); XCTAssertTrue(model.ticks.isEmpty)
            XCTAssertEqual(Self.figure(model.selected?.win), "8%")
            XCTAssertEqual(Self.figure(model.selected?.podium), "48%")
            XCTAssertEqual(model.originalAction(model.selected?.podium, canOpen: true), Self.pairs[3].podium)
            XCTAssertEqual(model.rows.count, 5)
        }
        let model = FieldPodiumModel10868(Self.input())
        XCTAssertTrue(model.canDraw)
        XCTAssertEqual(model.ticks.map(\.label), ["0%", "100%", "50%"])
    }

    func testGeometryUsedByTheViewRejectsInvalidEndpointsAndFramesWithoutMovingValidMarks() {
        let size = CGSize(width: 240, height: 24)
        for bad: Double in [.nan, .infinity, -.infinity, -0.1, 1.1] {
            let plan = FieldPodiumGeometry10868.plan(win: bad, podium: 0.48, size: size, inset: 8, diameter: 10)
            XCTAssertNil(plan?.win); XCTAssertNil(plan?.connector)
            XCTAssertEqual(plan?.podium?.x ?? -1, 115.52, accuracy: 1e-9)
        }
        for size in [.zero, CGSize(width: 16, height: 24), .init(width: 240, height: 11),
                     .init(width: CGFloat.nan, height: 24), .init(width: 240, height: CGFloat.infinity)] {
            XCTAssertNil(FieldPodiumGeometry10868.plan(win: 0.08, podium: 0.48, size: size, inset: 8, diameter: 10))
        }
        let none = FieldPodiumGeometry10868.plan(win: nil, podium: nil, size: size, inset: 8, diameter: 10)
        XCTAssertNotNil(none); XCTAssertNil(none?.win); XCTAssertNil(none?.podium); XCTAssertNil(none?.connector)
    }
}

// MARK: - #10868 racing final — "The race, resolved"
// PREPARED / NOT RUN. The racing-live final "Expectation and finish" card on the
// existing shared FieldFinishComparisonPresentation10868 — no new view, alias,
// formatter, loader, matching or lifecycle policy. Words, phase, selection and
// formatting below simulate the owner contract, not an app adapter.

/// ARCHIVED raw values come from the Singapore Grand Prix packet retained in
/// `shipping-adoption-20261027/RACING-FINAL-FINISH-REUSE-RETAINED-CASES.json`
/// (sha256 958d54b6…8923): all 75 canonical originals (23 winner, 23 podium,
/// 6 head-to-head sides, 23 fastest lap) with their market and outcome ids, each
/// original's own pre-race baseline (last captured selected-side trade within
/// 24 h before the verified start) or none, and the three owner-displayed winner
/// contracts with their ESPN classification places: Max Verstappen 1st, Charles
/// Leclerc 2nd, Lewis Hamilton 6th, captured 2026-10-12T07:47:00Z with no exact
/// finish time established. Their final raw 1/0/0 quotes, opening 0.335/0.1/0.105
/// and Won/Lost/Lost contract grades are retained only as hostile controls. The
/// last-lap report was published 2026-10-11T13:46:18Z; a publication is not a
/// finish time.
///
/// CONSTRUCTED owner inputs (this leaf does not resolve them): the scope, the
/// displayed order, every label and word (from the approved `RacingLive.tsx`
/// `FinishStory` where it has them: "The race, resolved", "Pre-race win",
/// "Actual finish", "Not recorded"), figure text prepared with the reference
/// `probabilityLabel.ts`, the clock lines quoting each sample's own archived
/// time, the ordinals written from the archived places, the 0–100% scale with
/// 0/50/100% ticks, the phase and selection, and every hostile, zero, withdrawn,
/// duplicate, blank, foreign and tie case. Per Root's disposition the reference's
/// per-row "Race winner" badge is not reproduced: every row, first place
/// included, carries one ordinal with the owner's unit.
final class FieldRacingFinishReuse10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Original = (
        key: String, family: String, market: String, outcome: String, name: String, selected: String,
        before: Double?, beforeFigure: String?, beforeAt: String?
    )

    /// One owner-displayed driver: the archived place, the owner's ordinal and
    /// the ARCHIVED hostile controls with CONSTRUCTED figures.
    private typealias Driver = (
        key: String, place: Int, ordinal: String, contractWon: Bool,
        final: Double, finalFigure: String, opening: Double, openingFigure: String
    )

    /// CONSTRUCTED opaque scope.
    private static let scope = "constructed:f1:singapore-2026:final-finish"

    /// ARCHIVED ids, names, selected sides and raw baselines in the packet's
    /// order; figures CONSTRUCTED with the reference `probabilityLabel.ts`.
    private static let originals: [Original] = [
        ("field-63989371.json:0", "winner", "5229406", "105026689771335810478914327541724319323338915766526076386906176141135574302746", "Max Verstappen", "Yes", 0.6499999935, "65%", "2026-10-11T11:59:31+00:00"),
        ("field-63989371.json:1", "winner", "5229411", "9518453683994039663103190001640433279731056992400699084747973794695685716810", "Lewis Hamilton", "Yes", 0.16, "16%", "2026-10-11T11:59:19+00:00"),
        ("field-63989371.json:2", "winner", "5229402", "92443082174901362958213182894863948289679800011664028904195269564952495193793", "Charles Leclerc", "Yes", 0.1399999999, "14%", "2026-10-11T11:59:46+00:00"),
        ("field-63989371.json:3", "winner", "5229405", "5696133373196488147875236821860681766749634665413742392928884679633318673226", "Kimi Antonelli", "Yes", 0.08, "8%", "2026-10-11T11:59:09+00:00"),
        ("field-63989371.json:4", "winner", "5229404", "50434279802004157692776355100568844573677746234993201217816404234694902233906", "Lando Norris", "Yes", 0.025, "2.5%", "2026-10-11T11:52:54+00:00"),
        ("field-63989371.json:5", "winner", "5229413", "92166685409924243611608345305761239418833259618841446683252071008964493612883", "Oscar Piastri", "Yes", 0.013192724, "1.3%", "2026-10-11T11:05:15+00:00"),
        ("field-63989371.json:6", "winner", "5229414", "56718796378955317111468916340265911522929583552165139147928588786823433132601", "George Russell", "Yes", 0.01, "1%", "2026-10-11T11:53:07+00:00"),
        ("field-63989371.json:7", "winner", "5229408", "112114148297929537173847598641186061156229360765636408243334062234430064452907", "Carlos Sainz Jr.", "Yes", 0.001, "0.1%", "2026-10-10T22:52:03+00:00"),
        ("field-63989371.json:8", "winner", "5229416", "5925247658760843939848257679933962433517180533220416892662406179964839647949", "Isack Hadjar", "Yes", 0.002, "0.2%", "2026-10-11T06:57:53+00:00"),
        ("field-63989371.json:9", "winner", "5229398", "24946613243542045093782896030972508052414682034023350754030313581675845916465", "Fernando Alonso", "Yes", nil, nil, nil),
        ("field-63989371.json:10", "winner", "5229417", "59218091277618579146661875012717821529527136170610280346022356243553006480870", "Liam Lawson", "Yes", 0.001, "0.1%", "2026-10-10T15:24:43+00:00"),
        ("field-63989371.json:11", "winner", "5229409", "46633357118097927706875836765976613273002880284113105333660319153040915921433", "Nico Hulkenberg", "Yes", nil, nil, nil),
        ("field-63989371.json:12", "winner", "5229410", "37377009617262886055248856685172953678066728775153467706615477067585995032236", "Valtteri Bottas", "Yes", nil, nil, nil),
        ("field-63989371.json:13", "winner", "5229412", "22577247696951783128672169989438357120216379084843314121733136822205330394386", "Oliver Bearman", "Yes", nil, nil, nil),
        ("field-63989371.json:14", "winner", "5229415", "35806167495708067688142660894515436986537444155410197985851888007006540375369", "Arvid Lindblad", "Yes", nil, nil, nil),
        ("field-63989371.json:15", "winner", "5229418", "17728978960408046070104397306363646944957497115347892906141065161648077901163", "Lance Stroll", "Yes", nil, nil, nil),
        ("field-63989371.json:16", "winner", "5229419", "80737513999194638178280916250352918609409177325807266190011527655594912137851", "Yuki Tsunoda", "Yes", nil, nil, nil),
        ("field-63989371.json:17", "winner", "5229399", "20899351361659882916278870698966147459616666433222997076649183873101393641787", "Alexander Albon", "Yes", nil, nil, nil),
        ("field-63989371.json:18", "winner", "5229400", "2835735619366113132331629458875618026032260678708439186410341002678206064734", "Gabriel Bortoleto", "Yes", nil, nil, nil),
        ("field-63989371.json:19", "winner", "5229401", "83652434777062733522317823357052014621993834306632156362686898553393933523458", "Sergio Perez", "Yes", nil, nil, nil),
        ("field-63989371.json:20", "winner", "5229403", "110900142078134549566830658584183223162291771163731239731531646173931267218149", "Esteban Ocon", "Yes", nil, nil, nil),
        ("field-63989371.json:21", "winner", "5229407", "4367879003640045686956388825375902266684763445371199130205596602619739253591", "Franco Colapinto", "Yes", nil, nil, nil),
        ("field-63989371.json:22", "winner", "5229397", "28558391061191296576456870322949545965070312914289181555918414954825561771030", "Pierre Gasly", "Yes", nil, nil, nil),
        ("field-63989361.json:0", "podium", "5229633", "110857599143644098992681976807171712355534104947335334189871164576023031815555", "Max Verstappen", "Yes", 0.8199999967, "82%", "2026-10-11T11:57:07+00:00"),
        ("field-63989361.json:1", "podium", "5229629", "81777712267167882804825483696208495691212603231475789493999361725169140070707", "Charles Leclerc", "Yes", 0.6666666667, "66.7%", "2026-10-11T11:59:00+00:00"),
        ("field-63989361.json:2", "podium", "5229638", "107223488373792995670853625575479347904333591818058137730381400388579385546848", "Lewis Hamilton", "Yes", 0.609999986, "61%", "2026-10-11T11:58:06+00:00"),
        ("field-63989361.json:3", "podium", "5229632", "93588786206279515298378425874328319850883491696258124247716491516547375534226", "Kimi Antonelli", "Yes", 0.4799998464, "48%", "2026-10-11T11:59:15+00:00"),
        ("field-63989361.json:4", "podium", "5229631", "91266558960626318800007488387086012785670848799467791981959112065990484864616", "Lando Norris", "Yes", 0.2899999884, "29%", "2026-10-11T11:49:21+00:00"),
        ("field-63989361.json:5", "podium", "5229640", "91254622187005296521266595966212220061366684245037347501894715001919789190753", "Oscar Piastri", "Yes", 0.1699999997, "17%", "2026-10-11T08:32:21+00:00"),
        ("field-63989361.json:6", "podium", "5229641", "48577678514819085078699880361241457992337880684158047380851450932928459872200", "George Russell", "Yes", 0.0636363633, "6.4%", "2026-10-11T11:59:19+00:00"),
        ("field-63989361.json:7", "podium", "5229646", "20389784775884582247749385164360943880067183172628624763938264759036675697715", "Yuki Tsunoda", "Yes", nil, nil, nil),
        ("field-63989361.json:8", "podium", "5229643", "73022736280294057069609534442862001943197948167325502370815577406169725034775", "Isack Hadjar", "Yes", 0.021, "2.1%", "2026-10-11T06:16:29+00:00"),
        ("field-63989361.json:9", "podium", "5229624", "87453145948323530683093142170131029583090664604716403936211065150093975501602", "Pierre Gasly", "Yes", 0.0169999999, "1.7%", "2026-10-11T10:42:08+00:00"),
        ("field-63989361.json:10", "podium", "5229644", "33230546474917362926564085275893645857309224237479558353480796418752326055304", "Liam Lawson", "Yes", 0.018, "1.8%", "2026-10-11T10:01:27+00:00"),
        ("field-63989361.json:11", "podium", "5229642", "74418053695910050098251154274261102238652619962310301587320294136005596880377", "Arvid Lindblad", "Yes", nil, nil, nil),
        ("field-63989361.json:12", "podium", "5229625", "18387701778833574956754249887029772709271827126644156983285721399815810792992", "Fernando Alonso", "Yes", nil, nil, nil),
        ("field-63989361.json:13", "podium", "5229634", "96209521069947352832106981216115838872905539746697545272969446534824159185351", "Franco Colapinto", "Yes", nil, nil, nil),
        ("field-63989361.json:14", "podium", "5229627", "5536126596058197620947728468486185325150227529245357066692180534751937918211", "Gabriel Bortoleto", "Yes", nil, nil, nil),
        ("field-63989361.json:15", "podium", "5229635", "21099583028461586672480695290502304110814989010954493894314247689103698679827", "Carlos Sainz Jr.", "Yes", nil, nil, nil),
        ("field-63989361.json:16", "podium", "5229630", "107579886745075038202250809930504945630616058165883684791018285923144296900320", "Esteban Ocon", "Yes", nil, nil, nil),
        ("field-63989361.json:17", "podium", "5229637", "70829314418231113229603197020787104655220492519845789616173317634590446065261", "Valtteri Bottas", "Yes", nil, nil, nil),
        ("field-63989361.json:18", "podium", "5229626", "36958804519639427780282363944661840022193973378862741937678054521049286386807", "Alexander Albon", "Yes", nil, nil, nil),
        ("field-63989361.json:19", "podium", "5229628", "38920286751886432926911405748215593390993793890929458803986070911095534135866", "Sergio Perez", "Yes", nil, nil, nil),
        ("field-63989361.json:20", "podium", "5229645", "99035375931778084321615410336433575315218165292425804029498168493607815844379", "Lance Stroll", "Yes", nil, nil, nil),
        ("field-63989361.json:21", "podium", "5229636", "40753676215478901061354185338534230390231681673691988568754789894877991728635", "Nico Hulkenberg", "Yes", nil, nil, nil),
        ("field-63989361.json:22", "podium", "5229639", "38393213436151514371775514758695461422541031352103503278188888358162116834906", "Oliver Bearman", "Yes", nil, nil, nil),
        ("field-63989363.json:0", "matchup", "5229621", "33331488134321289504801551659522059050212493202921720814700311861082309692009", "Hamilton — Hamilton vs Piastri", "Hamilton", nil, nil, nil),
        ("field-63989363.json:1", "matchup", "5229612", "7090122560978114151159241097823824193070045048886498702882654777211320166186", "Leclerc — Leclerc vs Russell", "Leclerc", nil, nil, nil),
        ("field-63989363.json:2", "matchup", "5229617", "4068713068528441296831042056180611328829965381921185174724790408885477085376", "Norris — Norris vs Russell", "Norris", nil, nil, nil),
        ("field-63989363.json:3", "matchup", "5229600", "110909128388621583528027995078471646758296891348314740700292566482823861330730", "Alonso — Alonso vs Stroll", "Alonso", 0.75, "75%", "2026-10-11T11:17:33+00:00"),
        ("field-63989363.json:4", "matchup", "5229604", "30828121593085071903092865373527569539214466840198501035754721592064994702046", "Leclerc — Leclerc vs Hamilton", "Leclerc", nil, nil, nil),
        ("field-63989363.json:5", "matchup", "5229618", "24814557986804912717525396491551950567731074765190854754056431039942873350501", "Verstappen — Verstappen vs Hamilton", "Verstappen", nil, nil, nil),
        ("field-63989365.json:0", "fastest", "5229488", "2591374099559395253718883338821225955484795878731663629478621088184458436077", "Max Verstappen", "Yes", 0.3499999825, "35%", "2026-10-11T11:51:31+00:00"),
        ("field-63989365.json:1", "fastest", "5229493", "26128000172307458556562604682667588959839117017600094179451615450544110291374", "Lewis Hamilton", "Yes", 0.19, "19%", "2026-10-11T11:56:28+00:00"),
        ("field-63989365.json:2", "fastest", "5229484", "113074849230542221111579369802690109874785517423609665045620204211923938532132", "Charles Leclerc", "Yes", 0.1590457256, "15.9%", "2026-10-11T11:40:12+00:00"),
        ("field-63989365.json:3", "fastest", "5229496", "69091165673113707821952123449217252259896209513255365069454973665287428858566", "George Russell", "Yes", 0.1089999991, "10.9%", "2026-10-11T09:59:36+00:00"),
        ("field-63989365.json:4", "fastest", "5229486", "71566812110811182468394622972187711783186293932959978471601123622936149006437", "Lando Norris", "Yes", 0.0489999998, "4.9%", "2026-10-11T11:55:13+00:00"),
        ("field-63989365.json:5", "fastest", "5229487", "28225730157221911414837039362281622918871472023499900047141665660095870686215", "Kimi Antonelli", "Yes", 0.1370268125, "13.7%", "2026-10-11T11:56:57+00:00"),
        ("field-63989365.json:6", "fastest", "5229498", "103483603311016169319312114776012863628659744762203324695647183613843329932112", "Isack Hadjar", "Yes", 0.057, "5.7%", "2026-10-11T09:38:18+00:00"),
        ("field-63989365.json:7", "fastest", "5229495", "113870944931080893581151995561608716268501303475993539576096255854502955492276", "Oscar Piastri", "Yes", 0.039, "3.9%", "2026-10-11T11:55:19+00:00"),
        ("field-63989365.json:8", "fastest", "5229489", "70884389017472998068956496869243231034693127519617203467418865835880820482785", "Franco Colapinto", "Yes", 0.001, "0.1%", "2026-10-11T11:43:23+00:00"),
        ("field-63989365.json:9", "fastest", "5229500", "36969303612488996956507685417579522699141402648309540215688732939831194740051", "Lance Stroll", "Yes", 0.015, "1.5%", "2026-10-10T23:47:51+00:00"),
        ("field-63989365.json:10", "fastest", "5229483", "22167621134500002236758899645184473355570659819263985906614787813786691721030", "Sergio Perez", "Yes", 0.015, "1.5%", "2026-10-10T23:44:49+00:00"),
        ("field-63989365.json:11", "fastest", "5229481", "82841373926297244567961403070618059268118839274372150642644645777215454102840", "Alexander Albon", "Yes", 0.001, "0.1%", "2026-10-10T16:02:49+00:00"),
        ("field-63989365.json:12", "fastest", "5229492", "50033331166900902238496754075390446021588636997182535677811844195072697881149", "Valtteri Bottas", "Yes", 0.015, "1.5%", "2026-10-10T23:49:52+00:00"),
        ("field-63989365.json:13", "fastest", "5229479", "63270863974452993271524558641066072795614556815649198640620203389325503101307", "Pierre Gasly", "Yes", 0.001, "0.1%", "2026-10-10T22:03:45+00:00"),
        ("field-63989365.json:14", "fastest", "5229480", "76147060615984389286618572057004607834846979634815560653181983737717442789749", "Fernando Alonso", "Yes", 0.001, "0.1%", "2026-10-11T01:20:56+00:00"),
        ("field-63989365.json:15", "fastest", "5229485", "52260232229041890478485638214731562331576098956208366313921603249471215791478", "Esteban Ocon", "Yes", 0.001, "0.1%", "2026-10-10T22:06:54+00:00"),
        ("field-63989365.json:16", "fastest", "5229491", "109578030417969707247021105786855642324572377718130068164229332475006938294977", "Nico Hulkenberg", "Yes", 0.001, "0.1%", "2026-10-10T22:05:51+00:00"),
        ("field-63989365.json:17", "fastest", "5229497", "61734884068413260382961879435677743258460901995938169786243728043635825118834", "Arvid Lindblad", "Yes", 0.001, "0.1%", "2026-10-10T22:06:55+00:00"),
        ("field-63989365.json:18", "fastest", "5229499", "75065405456029042574706141909485482536573163465452073348782299937074328910578", "Liam Lawson", "Yes", 0.001, "0.1%", "2026-10-10T22:03:46+00:00"),
        ("field-63989365.json:19", "fastest", "5229494", "3573637962077248432080539224215115931395302546255227719914533046680829117401", "Oliver Bearman", "Yes", 0.001, "0.1%", "2026-10-10T22:05:52+00:00"),
        ("field-63989365.json:20", "fastest", "5229490", "19530433398265004109975999830689410930998548542652494070320878237863685366147", "Carlos Sainz Jr.", "Yes", 0.001, "0.1%", "2026-10-10T16:02:49+00:00"),
        ("field-63989365.json:21", "fastest", "5229501", "22290850904385371225730409519828833030822513237562163307339926592219044659462", "Yuki Tsunoda", "Yes", 0.01, "1%", "2026-10-10T20:55:31+00:00"),
        ("field-63989365.json:22", "fastest", "5229482", "98309314565714537847497666396177854204578598906954404335647963267440860619564", "Gabriel Bortoleto", "Yes", 0.001, "0.1%", "2026-10-10T22:05:49+00:00"),
    ]

    private static let verstappen = "field-63989371.json:0"
    private static let leclerc = "field-63989371.json:2"
    private static let hamilton = "field-63989371.json:1"
    private static let antonelli = "field-63989371.json:3"
    private static let verstappenPodium = "field-63989361.json:0"
    private static let leclercPodium = "field-63989361.json:1"
    private static let verstappenFastest = "field-63989365.json:0"

    /// The owner's displayed rows, in the owner's order.
    private static let drivers: [Driver] = [
        (verstappen, 1, "1st", true, 1.0, "100%", 0.335, "33.5%"),
        (leclerc, 2, "2nd", false, 0.0, "0%", 0.1, "10%"),
        (hamilton, 6, "6th", false, 0.0, "0%", 0.105, "10.5%"),
    ]

    private static let notRecorded = "Not recorded"
    private static let finishLabel = "Actual finish"
    /// The owner's classification words: the capture is named, never a finish clock.
    private static let finishDetail = "ESPN classification captured Oct 12 · Exact finish time not supplied"
    private static let classificationCapturedAt = "2026-10-12T07:47:00.388539+00:00"
    private static let lastLapPublishedAt = "2026-10-11T13:46:18.000Z"
    private static let unavailable = "Driver unavailable in this update"
    private static let finishUnavailable = "Finish not confirmed"
    private static let chanceUnavailable = "Pre-race chance unavailable"
    private static let offScale = "Above the 100% scale"
    private static let outside = "Selected driver is outside this group"
    private static let selectionGone = "Selected driver unavailable"
    private static let openHint = "Open this exact original prop"
    private static let openPrompt = "Tap a driver for their history."

    private static func beforeLabel(_ family: String) -> String {
        switch family {
        case "winner": return "Pre-race win"
        case "podium": return "Pre-race podium"
        case "fastest": return "Pre-race fastest lap"
        default: return "Pre-race head-to-head"
        }
    }

    private static func original(_ key: String) -> Original {
        originals.first { $0.key == key }!
    }

    private static func ref(_ key: String, scope: String = FieldRacingFinishReuse10868Tests.scope) -> FieldChooserOriginalRef10868 {
        let item = original(key)
        return FieldChooserOriginalRef10868(scope: scope, source: "polymarket", marketID: item.market, outcomeID: item.outcome)
    }

    private static func beforeReading(_ original: Original) -> FieldChooserReading10868 {
        guard let figure = original.beforeFigure, let at = original.beforeAt else {
            return FieldChooserReading10868(label: beforeLabel(original.family), value: .missing(notRecorded))
        }
        return FieldChooserReading10868(label: beforeLabel(original.family),
                                        value: .recorded(text: figure, detail: "Polymarket selected-side trade · \(at)"))
    }

    private static func record(_ original: Original, plan: FieldChooserDisplayPlan10868? = nil,
                               name: String? = nil, result: String? = nil) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: ref(original.key), name: name ?? original.name,
            plan: plan ?? .single(beforeReading(original)),
            preview: FieldChooserPreview10868(history: nil, absence: "History supplied separately"),
            movement: nil, clock: nil,
            result: result.map { FieldChooserResult10868(title: "Prop result", words: $0) },
            browseStatus: "Original prop"
        )
    }

    private static let catalogue: [FieldChooserOriginal10868] = originals.map { record($0) }

    private static func settledReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Final settled quote", value: .recorded(text: driver.finalFigure, detail: "SETTLED CONTROL"))
    }

    private static func openingReading(_ driver: Driver) -> FieldChooserReading10868 {
        FieldChooserReading10868(label: "Opening quote", value: .recorded(text: driver.openingFigure, detail: "OPENING CONTROL"))
    }

    /// CONSTRUCTED hostile records for the displayed drivers: the settled 1/0
    /// quote as a later reading and preview, the opening quote as movement and
    /// reference, the last-lap publication as a clock, and the contract grade.
    private static func hostile(_ original: Original) -> FieldChooserOriginal10868 {
        guard let driver = drivers.first(where: { $0.key == original.key }) else { return record(original) }
        return FieldChooserOriginal10868(
            ref: ref(original.key), name: original.name,
            plan: .comparison(before: beforeReading(original), later: settledReading(driver)),
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(
                    segments: [[FieldChooserPoint10868(time: 0, probability: driver.opening),
                                FieldChooserPoint10868(time: 1, probability: driver.final)]],
                    emphasis: FieldChooserPoint10868(time: 1, probability: driver.final),
                    beforeReference: driver.opening, gaps: []),
                absence: "History supplied separately"),
            movement: "OPENING CONTROL \(driver.openingFigure)",
            clock: "LAST-LAP CONTROL \(lastLapPublishedAt)",
            result: FieldChooserResult10868(title: "Prop result", words: driver.contractWon ? "Won" : "Lost"),
            browseStatus: driver.contractWon ? "Won" : "Lost"
        )
    }

    private static let hostileCatalogue: [FieldChooserOriginal10868] = originals.map { hostile($0) }

    private static func chance(_ original: Original) -> FieldOutlookBeforeChance10868? {
        original.before.map { FieldOutlookBeforeChance10868(ref: ref(original.key), probability: $0, reading: beforeReading(original)) }
    }

    /// Every archived baseline, displayed or not.
    private static let chances: [FieldOutlookBeforeChance10868] = originals.compactMap { chance($0) }

    private static func finish(_ key: String, _ ordinal: String, scope: String = FieldRacingFinishReuse10868Tests.scope) -> FieldFinishPlace10868 {
        FieldFinishPlace10868(ref: ref(key, scope: scope),
                              reading: FieldChooserReading10868(label: finishLabel, value: .recorded(text: ordinal, detail: finishDetail)))
    }

    /// Only the owner-admitted classification places of the displayed drivers.
    private static let finishes: [FieldFinishPlace10868] = drivers.map { finish($0.key, $0.ordinal) }

    private static func slot(_ key: String) -> FieldFinishSlot10868 {
        FieldFinishSlot10868(ref: ref(key), name: original(key).name)
    }

    private static let displayedKeys: [String] = drivers.map { $0.key }
    private static let displayed: [FieldFinishSlot10868] = displayedKeys.map { slot($0) }

    private static let scale = FieldOutlookScale10868(
        ceiling: 1,
        ticks: [FieldOutlookTick10868(probability: 0, label: "0%"),
                FieldOutlookTick10868(probability: 0.5, label: "50%"),
                FieldOutlookTick10868(probability: 1, label: "100%")],
        words: "0–100%"
    )

    private static let copy = FieldFinishCopy10868(
        title: "The race, resolved",
        context: "Win chance before the start · finish from the classification",
        scaleLabel: "Pre-race win chance",
        graphicLabel: "Pre-race chances and actual finishes",
        finishLabel: finishLabel,
        finishUnit: "finish",
        finishUnavailable: finishUnavailable,
        chanceUnavailable: chanceUnavailable,
        offScale: offScale,
        outsideDisplayed: outside,
        empty: "No finishing positions captured",
        count: nil,
        openPrompt: openPrompt,
        openHint: openHint
    )

    private static func selected(_ key: String, scope: String = FieldRacingFinishReuse10868Tests.scope) -> FieldChooserSelected10868 {
        FieldChooserSelected10868(ref: ref(key, scope: scope), words: "In focus", unavailableWords: selectionGone)
    }

    private static func input(
        catalogue: [FieldChooserOriginal10868] = FieldRacingFinishReuse10868Tests.catalogue,
        selected: FieldChooserSelected10868? = nil,
        displayed: [FieldFinishSlot10868] = FieldRacingFinishReuse10868Tests.displayed,
        finishes: [FieldFinishPlace10868] = FieldRacingFinishReuse10868Tests.finishes,
        chances: [FieldOutlookBeforeChance10868] = FieldRacingFinishReuse10868Tests.chances,
        scale: FieldOutlookScale10868 = FieldRacingFinishReuse10868Tests.scale,
        phase: FieldOutlookPhase10868 = .final
    ) -> FieldFinishInput10868 {
        FieldFinishInput10868(
            scope: scope,
            catalogue: catalogue,
            selected: selected,
            displayed: displayed,
            finishes: finishes,
            chances: chances,
            scale: scale,
            phase: phase,
            copy: copy,
            unavailableWords: unavailable
        )
    }

    private static func model(_ input: FieldFinishInput10868 = FieldRacingFinishReuse10868Tests.input()) -> FieldFinishModel10868 {
        FieldFinishModel10868(input)
    }

    /// One original's catalogue record replaced.
    private static func catalogue(replacing key: String, with replacement: FieldChooserOriginal10868) -> [FieldChooserOriginal10868] {
        var catalogue = Self.catalogue
        let index = catalogue.firstIndex { $0.ref == ref(key) }!
        catalogue[index] = replacement
        return catalogue
    }

    /// One original's chance replaced (or added); nil removes it.
    private static func chances(replacing key: String, with replacement: FieldOutlookBeforeChance10868?) -> [FieldOutlookBeforeChance10868] {
        var chances = Self.chances.filter { $0.ref != ref(key) }
        if let replacement { chances.append(replacement) }
        return chances
    }

    /// One original's finish replaced (or added); nil removes it.
    private static func finishes(replacing key: String, with replacement: FieldFinishPlace10868?) -> [FieldFinishPlace10868] {
        var finishes = Self.finishes.filter { $0.ref != ref(key) }
        if let replacement { finishes.append(replacement) }
        return finishes
    }

    /// A CONSTRUCTED before reading and raw chance for one driver, tied to each
    /// other and keeping that driver's own archived clock.
    private static func retied(_ key: String, probability: Double, figure: String) -> (catalogue: [FieldChooserOriginal10868], chances: [FieldOutlookBeforeChance10868]) {
        let item = original(key)
        let reading = FieldChooserReading10868(label: beforeLabel(item.family),
                                               value: .recorded(text: figure, detail: "Polymarket selected-side trade · \(item.beforeAt!)"))
        return (
            catalogue(replacing: key, with: record(item, plan: .single(reading))),
            chances(replacing: key, with: FieldOutlookBeforeChance10868(ref: ref(key), probability: probability, reading: reading))
        )
    }

    private static func raw(_ chance: FieldOutlookChance10868) -> Double? {
        if case .value(let probability, _) = chance { return probability }
        return nil
    }

    /// The strip plan the row's Canvas draws on a CONSTRUCTED 300 × 16 pt strip.
    private static let inset: CGFloat = 6
    private static let diameter: CGFloat = 10

    private static func plan(_ row: FieldFinishRow10868, _ model: FieldFinishModel10868, width: CGFloat = 300) -> FieldFinishStripPlan10868? {
        FieldFinishGeometry10868.stripPlan(fraction: row.chance.fraction, ticks: model.ticks.map(\.fraction),
                                           in: CGSize(width: width, height: 16), inset: inset, dotDiameter: diameter)
    }

    /// Every line the view shows or speaks, from the same helpers it calls.
    private static func everyLine(_ model: FieldFinishModel10868) -> [String] {
        guard model.isShown else { return [] }
        let copy = model.input.copy
        var lines = [copy.title, copy.scaleLabel, copy.graphicLabel, copy.empty, model.input.scale.words]
        lines += [copy.context, copy.count, model.openPrompt(canOpen: true), model.notice, model.selectedOutside?.name].compactMap { $0 }
        lines += model.ticks.map(\.label)
        for row in model.rows {
            lines += [row.slot.name, model.rowSummary(row), model.hint(model.openAction(row, canOpen: true))]
            lines += [row.resolution.original?.name, model.figure(row), model.dotLabel(row), model.stateWords(row),
                      FieldFinishModel10868.ordinal(row.finish), FieldFinishModel10868.finishWords(row.finish)].compactMap { $0 }
            if FieldFinishModel10868.ordinal(row.finish) != nil { lines.append(copy.finishUnit) }
        }
        return lines
    }

    // MARK: The retained race

    func testAll75CanonicalOriginalsResolveAndOnlyTheOwnersThreeDriversAreRows() {
        XCTAssertEqual(Self.originals.count, 75)
        XCTAssertEqual(Set(Self.originals.map { $0.key }).count, 75)
        XCTAssertEqual(Set(Self.catalogue.map(\.ref)).count, 75)
        XCTAssertEqual(Self.originals.filter { $0.family == "winner" }.count, 23)
        XCTAssertEqual(Self.originals.filter { $0.family == "podium" }.count, 23)
        XCTAssertEqual(Self.originals.filter { $0.family == "matchup" }.count, 6)
        XCTAssertEqual(Self.originals.filter { $0.family == "fastest" }.count, 23)
        XCTAssertEqual(Self.chances.count, 44)

        let model = Self.model()
        // Every canonical original resolves by its exact ref, shown or not.
        for record in Self.catalogue {
            XCTAssertEqual(model.field.resolve(record.ref), .original(record), record.name)
        }

        let rows = model.rows
        XCTAssertEqual(rows.map(\.slot.ref), [
            FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229406",
                                         outcomeID: "105026689771335810478914327541724319323338915766526076386906176141135574302746"),
            FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229402",
                                         outcomeID: "92443082174901362958213182894863948289679800011664028904195269564952495193793"),
            FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229411",
                                         outcomeID: "9518453683994039663103190001640433279731056992400699084747973794695685716810"),
        ])
        XCTAssertEqual(rows.compactMap { $0.resolution.original?.name }, ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])

        // Each driver's same-named podium and fastest-lap originals stay their own identities and make no row.
        for name in ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"] {
            let same = Self.catalogue.filter { $0.name == name }
            XCTAssertEqual(same.count, 3, name)
            XCTAssertEqual(Set(same.map(\.ref)).count, 3, name)
            XCTAssertEqual(rows.filter { $0.resolution.original?.name == name }.count, 1, name)
        }
        let unshown = Self.catalogue.filter { record in !rows.contains { $0.slot.ref == record.ref } }
        XCTAssertEqual(unshown.count, 72)
        XCTAssertTrue(unshown.contains { $0.name == "Verstappen — Verstappen vs Hamilton" })
        XCTAssertNil(model.notice)
        XCTAssertNil(model.selectedOutside)
    }

    func testEachDriverShowsTheirOwnPreRaceChanceBesideTheirPhysicalFinish() {
        let model = Self.model()
        let rows = model.rows
        XCTAssertEqual(Self.drivers.map { $0.place }, [1, 2, 6])
        XCTAssertEqual(rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["1st", "2nd", "6th"])
        XCTAssertEqual(rows.map { FieldFinishModel10868.finishWords($0.finish) }, [nil, nil, nil])

        // Each driver's own raw baseline on the one 0–100% scale; nothing summed or normalized.
        let baselines = [0.6499999935, 0.1399999999, 0.16]
        XCTAssertEqual(rows.map { Self.raw($0.chance) }, [0.6499999935, 0.1399999999, 0.16])
        for (row, baseline) in zip(rows, baselines) {
            XCTAssertEqual(row.chance.fraction ?? -1, baseline, accuracy: 1e-12, row.slot.name)
            let plan = Self.plan(row, model)
            XCTAssertEqual(plan?.dot?.midX ?? -1, 6 + 288 * CGFloat(baseline), accuracy: 1e-9, row.slot.name)
            XCTAssertEqual(plan?.dot?.midY ?? -1, 11, accuracy: 1e-9, row.slot.name)
            XCTAssertEqual(plan?.dot?.width, 10, row.slot.name)
            XCTAssertEqual(plan?.tickXs, [6, 6, 150, 294], row.slot.name)
        }
        XCTAssertEqual(rows.map { model.dotLabel($0) }, ["65%", "14%", "16%"])
        XCTAssertEqual(rows.map { model.figure($0) }, ["65%", "14%", "16%"])
        XCTAssertEqual(rows.map { model.stateWords($0) }, [nil, nil, nil])
        XCTAssertEqual(model.ticks, [
            FieldOutlookPlacedTick10868(label: "0%", fraction: 0),
            FieldOutlookPlacedTick10868(label: "50%", fraction: 0.5),
            FieldOutlookPlacedTick10868(label: "100%", fraction: 1),
        ])

        // The owner's order is followed, never re-sorted by place or chance.
        let reversed = Self.model(Self.input(displayed: Array(Self.displayed.reversed())))
        XCTAssertEqual(reversed.rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["6th", "2nd", "1st"])
        XCTAssertEqual(reversed.rows.map { Self.raw($0.chance) }, [0.16, 0.1399999999, 0.6499999935])

        // One ordinal with the owner's unit on every row, first place included; no winner badge.
        XCTAssertEqual(model.input.copy.finishUnit, "finish")
        let lines = Self.everyLine(model)
        XCTAssertEqual(lines.filter { $0 == "finish" }.count, 3)
        XCTAssertFalse(lines.contains { $0.contains("Race winner") })
    }

    // MARK: Phase

    func testBeforeAndDuringDrawNoRowsWordsOrActionsEvenWithHostileFinishFields() {
        for selection in [Self.selected(Self.antonelli), Self.selected(Self.leclerc)] {
            for phase in [FieldOutlookPhase10868.before, .during] {
                for catalogue in [Self.catalogue, Self.hostileCatalogue] {
                    let model = Self.model(Self.input(catalogue: catalogue, selected: selection, phase: phase))
                    XCTAssertFalse(model.isShown, "\(phase)")
                    XCTAssertEqual(model.rows, [], "\(phase)")
                    XCTAssertEqual(model.ticks, [], "\(phase)")
                    XCTAssertNil(model.notice, "\(phase)")
                    XCTAssertNil(model.selectedOutside, "\(phase)")
                    XCTAssertNil(model.outsideAction(canOpen: true), "\(phase)")
                    XCTAssertNil(model.openPrompt(canOpen: true), "\(phase)")
                    XCTAssertEqual(Self.everyLine(model), [], "\(phase)")
                }
            }
        }
        let final = Self.model(Self.input(selected: Self.selected(Self.antonelli)))
        XCTAssertTrue(final.isShown)
        XCTAssertEqual(final.rows.count, 3)
        XCTAssertEqual(final.notice, Self.outside)
    }

    // MARK: Hostile inputs

    func testFinishAndChanceIgnoreContractGradesSettledQuotesAndOpeningValues() {
        let plain = Self.model()
        let hostile = Self.model(Self.input(catalogue: Self.hostileCatalogue))
        // The control stays hostile: each displayed original's plan differs from its plain plan.
        XCTAssertEqual(hostile.rows.count, Self.drivers.count)
        XCTAssertEqual(plain.rows.count, Self.drivers.count)
        for (index, driver) in Self.drivers.enumerated() {
            let name = Self.original(driver.key).name
            let hostilePlan = hostile.rows[index].resolution.original?.plan
            let plainPlan = plain.rows[index].resolution.original?.plan
            XCTAssertNotNil(hostilePlan, name)
            XCTAssertNotNil(plainPlan, name)
            XCTAssertNotEqual(hostilePlan, plainPlan, name)
        }
        XCTAssertEqual(hostile.rows.map(\.chance), plain.rows.map(\.chance))
        XCTAssertEqual(hostile.rows.map(\.finish), plain.rows.map(\.finish))
        XCTAssertEqual(hostile.rows.map { hostile.figure($0) }, ["65%", "14%", "16%"])
        XCTAssertEqual(hostile.rows.map { hostile.rowSummary($0) }, plain.rows.map { plain.rowSummary($0) })
        let leaks = ["Won", "Lost", "Prop result", "Final settled quote", "SETTLED CONTROL", "Opening quote",
                     "OPENING CONTROL", "LAST-LAP CONTROL", "33.5%", "10.5%", Self.lastLapPublishedAt]
        for model in [plain, hostile] {
            let lines = Self.everyLine(model)
            for leak in leaks {
                XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
            }
        }

        // The physical place is not the contract grade: regraded contracts change no ordinal,
        // and the contract winner with no admitted place shows the owner's words, never "1st".
        let regraded = Self.catalogue.map { record -> FieldChooserOriginal10868 in
            guard Self.displayedKeys.contains(where: { Self.ref($0) == record.ref }) else { return record }
            return FieldChooserOriginal10868(
                ref: record.ref, name: record.name, plan: record.plan, preview: record.preview,
                movement: nil, clock: nil,
                result: FieldChooserResult10868(title: "Prop result", words: record.ref == Self.ref(Self.leclerc) ? "Won" : "Lost"),
                browseStatus: record.browseStatus)
        }
        XCTAssertEqual(Self.model(Self.input(catalogue: regraded)).rows.map { FieldFinishModel10868.ordinal($0.finish) },
                       ["1st", "2nd", "6th"])
        let unplaced = Self.model(Self.input(catalogue: Self.hostileCatalogue,
                                             finishes: Self.finishes(replacing: Self.verstappen, with: nil)))
        XCTAssertEqual(unplaced.rows[0].finish, .unavailable(label: Self.finishLabel, words: Self.finishUnavailable))
        XCTAssertNil(FieldFinishModel10868.ordinal(unplaced.rows[0].finish))
        XCTAssertFalse(Self.everyLine(unplaced).contains { $0.contains("1st") })
        XCTAssertEqual(unplaced.rows[0].chance, plain.rows[0].chance)

        // A settled 1/0 or opening value tied to its own reading is never the earlier chance —
        // alone, or beside the true baseline (two associations are none; neither is picked).
        for (index, driver) in Self.drivers.enumerated() {
            let item = Self.original(driver.key)
            for (reading, value) in [(Self.settledReading(driver), driver.final), (Self.openingReading(driver), driver.opening)] {
                let association = FieldOutlookBeforeChance10868(ref: Self.ref(driver.key), probability: value, reading: reading)
                for chances in [Self.chances(replacing: driver.key, with: association), Self.chances + [association]] {
                    let swapped = Self.model(Self.input(catalogue: Self.hostileCatalogue, chances: chances))
                    let row = swapped.rows[index]
                    XCTAssertEqual(row.chance, .unavailable, "\(item.name) \(reading.label)")
                    XCTAssertNil(swapped.dotLabel(row), item.name)
                    XCTAssertNil(Self.plan(row, swapped)?.dot, item.name)
                    XCTAssertEqual(swapped.figure(row), item.beforeFigure, item.name)
                    XCTAssertEqual(swapped.stateWords(row), Self.chanceUnavailable, item.name)
                    XCTAssertEqual(row.finish, plain.rows[index].finish, item.name)
                    for other in plain.rows.indices where other != index {
                        // Same hostile catalogue, so a neighbour keeps its hostile record whole;
                        // its presentation still matches the plain one.
                        XCTAssertEqual(swapped.rows[other], hostile.rows[other], "\(item.name) → \(other)")
                        XCTAssertEqual(swapped.rows[other].chance, plain.rows[other].chance, "\(item.name) → \(other)")
                        XCTAssertEqual(swapped.rows[other].finish, plain.rows[other].finish, "\(item.name) → \(other)")
                        XCTAssertEqual(swapped.figure(swapped.rows[other]), plain.figure(plain.rows[other]), "\(item.name) → \(other)")
                        XCTAssertEqual(swapped.rowSummary(swapped.rows[other]), plain.rowSummary(plain.rows[other]), "\(item.name) → \(other)")
                    }
                    XCTAssertFalse(Self.everyLine(swapped).contains { $0.contains("SETTLED CONTROL") || $0.contains("OPENING CONTROL") })
                }
            }
        }
    }

    // MARK: Zero, missing chance, missing finish

    func testGenuineZeroMissingChanceAndMissingFinishStayDistinct() {
        let plain = Self.model()

        // A real 0% is a labelled dot at zero, with Hamilton's own clock and finish.
        let zero = Self.retied(Self.hamilton, probability: 0, figure: "0%")
        let zeroModel = Self.model(Self.input(catalogue: zero.catalogue, chances: zero.chances))
        let zeroRow = zeroModel.rows[2]
        XCTAssertEqual(zeroRow.chance, .value(probability: 0, fraction: 0))
        XCTAssertEqual(zeroModel.dotLabel(zeroRow), "0%")
        XCTAssertNil(zeroModel.stateWords(zeroRow))
        XCTAssertEqual(Self.plan(zeroRow, zeroModel)?.dot, CGRect(x: 1, y: 6, width: 10, height: 10))
        XCTAssertEqual(FieldFinishModel10868.ordinal(zeroRow.finish), "6th")
        XCTAssertEqual(zeroModel.rowSummary(zeroRow),
                       "Actual finish: 6th, \(Self.finishDetail). Pre-race win: 0%, Polymarket selected-side trade · 2026-10-11T11:59:19+00:00")

        // A missing earlier chance: the owner's words, no dot, no "unavailable" words, its finish kept.
        let leclerc = Self.original(Self.leclerc)
        let missingPlan = FieldChooserDisplayPlan10868.single(
            FieldChooserReading10868(label: "Pre-race win", value: .missing(Self.notRecorded)))
        let missing = Self.model(Self.input(
            catalogue: Self.catalogue(replacing: Self.leclerc, with: Self.record(leclerc, plan: missingPlan)),
            chances: Self.chances(replacing: Self.leclerc, with: nil)))
        let missingRow = missing.rows[1]
        XCTAssertEqual(missingRow.chance, .unavailable)
        XCTAssertEqual(missing.figure(missingRow), Self.notRecorded)
        XCTAssertNil(missing.dotLabel(missingRow))
        XCTAssertNil(missing.stateWords(missingRow))
        XCTAssertNil(Self.plan(missingRow, missing)?.dot)
        XCTAssertEqual(FieldFinishModel10868.ordinal(missingRow.finish), "2nd")
        XCTAssertEqual(missing.rowSummary(missingRow), "Actual finish: 2nd, \(Self.finishDetail). Pre-race win: \(Self.notRecorded)")

        // A recorded figure with no association keeps its figure and finish, draws no dot.
        let untied = Self.model(Self.input(chances: Self.chances(replacing: Self.verstappen, with: nil)))
        XCTAssertEqual(untied.rows[0].chance, .unavailable)
        XCTAssertEqual(untied.figure(untied.rows[0]), "65%")
        XCTAssertEqual(untied.stateWords(untied.rows[0]), Self.chanceUnavailable)
        XCTAssertEqual(FieldFinishModel10868.ordinal(untied.rows[0].finish), "1st")

        // A missing finish keeps the chance and shows the copy's words; the owner's own words show as they are.
        let unplaced = Self.model(Self.input(finishes: Self.finishes(replacing: Self.hamilton, with: nil)))
        XCTAssertEqual(unplaced.rows[2].finish, .unavailable(label: Self.finishLabel, words: Self.finishUnavailable))
        XCTAssertEqual(FieldFinishModel10868.finishWords(unplaced.rows[2].finish), Self.finishUnavailable)
        XCTAssertEqual(unplaced.rows[2].chance, plain.rows[2].chance)
        XCTAssertEqual(unplaced.dotLabel(unplaced.rows[2]), "16%")
        let words = "Classification not captured"
        let owned = Self.model(Self.input(finishes: Self.finishes(replacing: Self.leclerc, with: FieldFinishPlace10868(
            ref: Self.ref(Self.leclerc), reading: FieldChooserReading10868(label: Self.finishLabel, value: .missing(words))))))
        XCTAssertEqual(FieldFinishModel10868.finishWords(owned.rows[1].finish), words)
        XCTAssertNil(FieldFinishModel10868.ordinal(owned.rows[1].finish))

        // The four states never collapse into each other.
        XCTAssertNotEqual(zeroRow.chance, missingRow.chance)
        XCTAssertNotEqual(missing.figure(missingRow), untied.figure(untied.rows[0]))
        XCTAssertNotEqual(missing.stateWords(missingRow), untied.stateWords(untied.rows[0]))
        XCTAssertNotEqual(unplaced.rows[2].finish, plain.rows[2].finish)
    }

    // MARK: Finish associations

    func testMalformedMissingDuplicateAndForeignFinishesBorrowNothing() {
        let plain = Self.model().rows
        let unavailableFinish = FieldMovementEndpoint10868.unavailable(label: Self.finishLabel, words: Self.finishUnavailable)

        // Two identical, or two differing, associations for one original are none.
        let twice = Self.model(Self.input(finishes: Self.finishes + [Self.finish(Self.verstappen, "1st")]))
        XCTAssertEqual(twice.rows[0].finish, unavailableFinish)
        XCTAssertEqual(Array(twice.rows.dropFirst()), Array(plain.dropFirst()))
        let differing = Self.model(Self.input(finishes: Self.finishes + [Self.finish(Self.leclerc, "3rd")]))
        XCTAssertEqual(differing.rows[1].finish, unavailableFinish)
        XCTAssertFalse(Self.everyLine(differing).contains { $0 == "2nd" || $0 == "3rd" })
        XCTAssertEqual([differing.rows[0], differing.rows[2]], [plain[0], plain[2]])

        // A foreign-scope place, a blank ordinal, blank absence words and a place tied to
        // Leclerc's same-named podium original borrow nothing.
        var finishes = Self.finishes(replacing: Self.leclerc, with: Self.finish(Self.leclerc, "2nd", scope: "constructed:f1:other-race"))
        finishes = finishes.filter { $0.ref != Self.ref(Self.hamilton) }
            + [FieldFinishPlace10868(ref: Self.ref(Self.hamilton),
                                     reading: FieldChooserReading10868(label: Self.finishLabel, value: .recorded(text: " ", detail: Self.finishDetail)))]
        finishes.append(Self.finish(Self.leclercPodium, "2nd"))
        let model = Self.model(Self.input(finishes: finishes))
        XCTAssertEqual(model.rows[1].finish, unavailableFinish)
        XCTAssertEqual(model.rows[2].finish, unavailableFinish)
        XCTAssertEqual(model.rows[0], plain[0])
        XCTAssertFalse(Self.everyLine(model).contains { $0 == "2nd" || $0 == "6th" })
        let blankWords = Self.model(Self.input(finishes: Self.finishes(replacing: Self.hamilton, with: FieldFinishPlace10868(
            ref: Self.ref(Self.hamilton), reading: FieldChooserReading10868(label: Self.finishLabel, value: .missing("  "))))))
        XCTAssertEqual(blankWords.rows[2].finish, unavailableFinish)

        // The podium original shown as its own row keeps its own baseline and its own (absent) place.
        let podium = Self.model(Self.input(displayed: [Self.slot(Self.leclerc), Self.slot(Self.leclercPodium)]))
        XCTAssertEqual(podium.rows[0].finish, plain[1].finish)
        XCTAssertEqual(podium.rows[1].finish, unavailableFinish)
        XCTAssertEqual(Self.raw(podium.rows[1].chance), 0.6666666667)
        XCTAssertEqual(podium.figure(podium.rows[1]), "66.7%")
        XCTAssertEqual(podium.rowSummary(podium.rows[1]),
                       "Actual finish: \(Self.finishUnavailable). Pre-race podium: 66.7%, Polymarket selected-side trade · 2026-10-11T11:59:00+00:00")
    }

    // MARK: Chance associations

    func testInvalidMismatchedAndForeignChanceTiesDrawNothingAndNeighboursKeepTheirs() {
        let plain = Self.model().rows

        for bad in [1.01, -0.01, Double.nan, .infinity, -.infinity] {
            let tied = Self.retied(Self.leclerc, probability: bad, figure: "14%")
            let invalid = Self.model(Self.input(catalogue: tied.catalogue, chances: tied.chances))
            XCTAssertEqual(invalid.rows[1].chance, .unavailable, "\(bad)")
            XCTAssertEqual(invalid.stateWords(invalid.rows[1]), Self.chanceUnavailable, "\(bad)")
            XCTAssertEqual(invalid.figure(invalid.rows[1]), "14%", "\(bad)")
            XCTAssertEqual(invalid.rows[1].finish, plain[1].finish, "\(bad)")
            XCTAssertEqual([invalid.rows[0], invalid.rows[2]], [plain[0], plain[2]], "\(bad)")
        }

        // Verstappen's raw value tied to a reading with Leclerc's clock is not his reading.
        let mismatched = FieldChooserReading10868(label: "Pre-race win",
                                                  value: .recorded(text: "65%", detail: "Polymarket selected-side trade · 2026-10-11T11:59:46+00:00"))
        let clock = Self.model(Self.input(chances: Self.chances(replacing: Self.verstappen,
            with: FieldOutlookBeforeChance10868(ref: Self.ref(Self.verstappen), probability: 0.6499999935, reading: mismatched))))
        XCTAssertEqual(clock.rows[0].chance, .unavailable)
        XCTAssertEqual(Array(clock.rows.dropFirst()), Array(plain.dropFirst()))

        // A foreign-scope association and one for a withdrawn ref borrow nothing.
        let hamilton = Self.chance(Self.original(Self.hamilton))!
        let foreign = FieldOutlookBeforeChance10868(ref: Self.ref(Self.hamilton, scope: "constructed:f1:other-race"),
                                                    probability: hamilton.probability, reading: hamilton.reading)
        let withdrawn = FieldOutlookBeforeChance10868(
            ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229411", outcomeID: "constructed-withdrawn"),
            probability: 0.5, reading: hamilton.reading)
        let elsewhere = Self.model(Self.input(chances: Self.chances(replacing: Self.hamilton, with: foreign) + [withdrawn]))
        XCTAssertEqual(elsewhere.rows[2].chance, .unavailable)
        XCTAssertEqual(elsewhere.stateWords(elsewhere.rows[2]), Self.chanceUnavailable)
        XCTAssertEqual(Array(elsewhere.rows.prefix(2)), Array(plain.prefix(2)))

        // An invalid scale places no dot and no tick; every finish stays.
        for bound in [0, -0.5, 1.5, Double.nan] {
            let invalid = Self.model(Self.input(scale: FieldOutlookScale10868(ceiling: bound, ticks: Self.scale.ticks, words: "0–100%")))
            XCTAssertTrue(invalid.rows.allSatisfy { $0.chance == .unavailable }, "\(bound)")
            XCTAssertEqual(invalid.ticks, [], "\(bound)")
            XCTAssertEqual(invalid.rows.map(\.finish), plain.map(\.finish), "\(bound)")
        }
    }

    func testOwnerReportedTiesAndEqualChancesKeepEachDriversOwnValues() {
        // CONSTRUCTED equal raw chances: two dots at one x, each with its own figure and clock.
        let tie = Self.retied(Self.leclerc, probability: 0.16, figure: "16%")
        let equal = Self.model(Self.input(catalogue: tie.catalogue, chances: tie.chances))
        XCTAssertEqual(Self.raw(equal.rows[1].chance), 0.16)
        XCTAssertEqual(Self.raw(equal.rows[2].chance), 0.16)
        XCTAssertEqual(Self.plan(equal.rows[1], equal)?.dot, Self.plan(equal.rows[2], equal)?.dot)
        XCTAssertTrue(equal.rowSummary(equal.rows[1]).hasSuffix("2026-10-11T11:59:46+00:00"))
        XCTAssertTrue(equal.rowSummary(equal.rows[2]).hasSuffix("2026-10-11T11:59:19+00:00"))
        XCTAssertEqual(equal.rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["1st", "2nd", "6th"])

        // CONSTRUCTED shared ordinal on two originals: each keeps its own, in the owner's order.
        let shared = Self.model(Self.input(finishes: Self.finishes(replacing: Self.leclerc, with: Self.finish(Self.leclerc, "1st"))))
        XCTAssertEqual(shared.rows.map { FieldFinishModel10868.ordinal($0.finish) }, ["1st", "1st", "6th"])
        XCTAssertEqual(shared.rows.compactMap { $0.resolution.original?.name }, ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])
        XCTAssertEqual(shared.rows.map(\.chance), Self.model().rows.map(\.chance))
    }

    // MARK: Identity failures

    func testUnresolvedRepeatedAndWithdrawnDriverSlotsKeepNamesAndNeighboursKeepTheirs() {
        let plain = Self.model().rows
        let foreign = FieldFinishSlot10868(ref: Self.ref(Self.leclerc, scope: "constructed:f1:other-race"), name: "Charles Leclerc")
        let blank = FieldFinishSlot10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229406", outcomeID: " "),
                                         name: "Blank driver")
        let withdrawn = FieldFinishSlot10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229499",
                                                                               outcomeID: "constructed-withdrawn"), name: "Withdrawn driver")
        let nameless = FieldFinishSlot10868(ref: withdrawn.ref, name: " ")
        let displayed = [Self.slot(Self.verstappen), foreign, blank, withdrawn, Self.slot(Self.hamilton), Self.slot(Self.hamilton),
                         Self.slot(Self.leclerc), nameless]
        let model = Self.model(Self.input(displayed: displayed))
        let rows = model.rows
        XCTAssertEqual(rows.count, displayed.count)
        XCTAssertEqual(rows[0], plain[0])
        XCTAssertEqual(rows[6], plain[1])
        for index in [1, 2, 3, 4, 5, 7] {
            let row = rows[index]
            XCTAssertEqual(row.resolution, .unavailable, "\(index)")
            XCTAssertNil(row.finish, "\(index)")
            XCTAssertEqual(row.chance, .unavailable, "\(index)")
            XCTAssertNil(model.dotLabel(row), "\(index)")
            XCTAssertNil(model.openAction(row, canOpen: true), "\(index)")
        }
        XCTAssertEqual(model.rowSummary(rows[1]), "Charles Leclerc. \(Self.unavailable)")
        XCTAssertEqual(model.rowSummary(rows[4]), "Lewis Hamilton. \(Self.unavailable)")
        XCTAssertEqual(model.rowSummary(rows[7]), Self.unavailable)
        XCTAssertFalse(Self.everyLine(model).contains("6th"))

        // A record carried twice in the catalogue is no identity; neighbours keep theirs.
        let duplicated = Self.model(Self.input(catalogue: Self.catalogue + [Self.record(Self.original(Self.hamilton))]))
        XCTAssertEqual(duplicated.rows[2].resolution, .unavailable)
        XCTAssertNil(duplicated.rows[2].finish)
        XCTAssertEqual(Array(duplicated.rows.prefix(2)), Array(plain.prefix(2)))
    }

    // MARK: Spoken text and clocks

    func testSpokenRowsKeepWholeNamesOwnPreRaceClocksAndCaptureWordsNotAFinishTime() {
        let model = Self.model()
        XCTAssertEqual(model.input.copy.graphicLabel, "Pre-race chances and actual finishes")
        let summaries = model.rows.map { model.rowSummary($0) }
        XCTAssertEqual(summaries, [
            "Actual finish: 1st, \(Self.finishDetail). Pre-race win: 65%, Polymarket selected-side trade · 2026-10-11T11:59:31+00:00",
            "Actual finish: 2nd, \(Self.finishDetail). Pre-race win: 14%, Polymarket selected-side trade · 2026-10-11T11:59:46+00:00",
            "Actual finish: 6th, \(Self.finishDetail). Pre-race win: 16%, Polymarket selected-side trade · 2026-10-11T11:59:19+00:00",
        ])
        // Each row speaks only its own clock.
        let clocks = ["11:59:31", "11:59:46", "11:59:19"]
        for (index, summary) in summaries.enumerated() {
            for (other, clock) in clocks.enumerated() {
                XCTAssertEqual(summary.contains(clock), index == other, "\(index) / \(clock)")
            }
        }
        // The full names are the accessible labels.
        XCTAssertEqual(model.rows.compactMap { $0.resolution.original?.name }, ["Max Verstappen", "Charles Leclerc", "Lewis Hamilton"])

        // Classification capture and last-lap publication never become a finish time.
        let lines = Self.everyLine(model)
        for leak in [Self.lastLapPublishedAt, "13:46", "Lap 62", Self.classificationCapturedAt, "07:47", "Finished at"] {
            XCTAssertFalse(lines.contains { $0.contains(leak) }, leak)
        }
        XCTAssertTrue(summaries.allSatisfy { $0.contains("Exact finish time not supplied") })

        // A long full name is kept whole — in the row and in an unavailable slot.
        let long = "Lewis Carl Davidson Hamilton — Scuderia Ferrari HP, Singapore Grand Prix winner contract"
        let hamilton = Self.original(Self.hamilton)
        let whole = Self.model(Self.input(catalogue: Self.catalogue(replacing: Self.hamilton, with: Self.record(hamilton, name: long))))
        XCTAssertEqual(whole.rows[2].resolution.original?.name, long)
        XCTAssertEqual(whole.rowSummary(whole.rows[2]), summaries[2])
        let slot = Self.model(Self.input(displayed: [FieldFinishSlot10868(ref: Self.ref(Self.hamilton, scope: "elsewhere"), name: long)]))
        XCTAssertEqual(slot.rowSummary(slot.rows[0]), "\(long). \(Self.unavailable)")
    }

    // MARK: Open

    @MainActor
    func testOpenHandsTheExactOriginalToTheRealCallbackAndNoCallbackIsStatic() {
        let input = Self.input(selected: Self.selected(Self.verstappenPodium))
        var opened: [FieldChooserOriginalRef10868] = []
        let view = FieldFinishComparisonPresentation10868(input: input, onOpenHistory: { opened.append($0) })
        XCTAssertEqual(view.input, input)
        let model = FieldFinishModel10868(view.input)
        let canOpen = view.onOpenHistory != nil
        XCTAssertTrue(canOpen)
        for row in model.rows {
            let action = model.openAction(row, canOpen: canOpen)
            XCTAssertEqual(model.hint(action), Self.openHint)
            if let action { view.onOpenHistory?(action) }
        }
        if let outside = model.outsideAction(canOpen: canOpen) { view.onOpenHistory?(outside) }
        XCTAssertEqual(opened, Self.displayedKeys.map { Self.ref($0) } + [Self.ref(Self.verstappenPodium)])
        XCTAssertNotEqual(opened.last, Self.ref(Self.verstappen))
        XCTAssertEqual(model.openPrompt(canOpen: canOpen), Self.openPrompt)

        // With no callback nothing pretends to act.
        let still = FieldFinishComparisonPresentation10868(input: input)
        XCTAssertNil(still.onOpenHistory)
        for row in model.rows {
            XCTAssertNil(model.openAction(row, canOpen: false))
            XCTAssertEqual(model.hint(model.openAction(row, canOpen: false)), "")
        }
        XCTAssertNil(model.outsideAction(canOpen: false))
        XCTAssertNil(model.openPrompt(canOpen: false))

        // An unresolved row never opens, and with no row resolving there is no prompt.
        let none = Self.model(Self.input(displayed: [FieldFinishSlot10868(ref: Self.ref(Self.verstappen, scope: "elsewhere"), name: "Max Verstappen")]))
        XCTAssertNil(none.openAction(none.rows[0], canOpen: true))
        XCTAssertNil(none.openPrompt(canOpen: true))
        XCTAssertEqual(none.hint(nil), "")
    }

    // MARK: Selection

    func testHeldSelectionFollowsTheDriversIdentityAndAnOutsideSelectionKeepsItsExactOriginal() {
        // Held on Leclerc: the selected cue follows his identity through the owner's reorder.
        let held = Self.selected(Self.leclerc)
        let inside = Self.model(Self.input(selected: held))
        XCTAssertEqual(inside.rows.map { inside.isSelected($0) }, [false, true, false])
        XCTAssertNil(inside.notice)
        XCTAssertNil(inside.selectedOutside)
        XCTAssertEqual(inside.rowSummary(inside.rows[1]),
                       "In focus. Actual finish: 2nd, \(Self.finishDetail). Pre-race win: 14%, Polymarket selected-side trade · 2026-10-11T11:59:46+00:00")
        let rotated = Self.model(Self.input(selected: held, displayed: [Self.slot(Self.leclerc), Self.slot(Self.hamilton), Self.slot(Self.verstappen)]))
        XCTAssertEqual(rotated.rows.map { rotated.isSelected($0) }, [true, false, false])
        XCTAssertEqual(rotated.rows[0], inside.rows[1])
        // The same held selection survives the phase change to the final.
        XCTAssertEqual(Self.model(Self.input(selected: held, phase: .during)).rows, [])
        XCTAssertEqual(Self.model(Self.input(selected: held, phase: .final)).rows.map { inside.isSelected($0) }, [false, true, false])

        // Verstappen's same-named podium and fastest-lap originals, and Antonelli, sit outside the
        // rows: kept by exact identity, never replaced by the plotted Verstappen winner row.
        for key in [Self.verstappenPodium, Self.verstappenFastest, Self.antonelli] {
            let outside = Self.model(Self.input(selected: Self.selected(key)))
            XCTAssertEqual(outside.notice, Self.outside, key)
            XCTAssertEqual(outside.selectedOutside, Self.catalogue.first(where: { $0.ref == Self.ref(key) }), key)
            XCTAssertEqual(outside.outsideAction(canOpen: true), Self.ref(key), key)
            XCTAssertNil(outside.outsideAction(canOpen: false), key)
            XCTAssertFalse(outside.rows.contains { outside.isSelected($0) }, key)
            XCTAssertEqual(outside.rows.map { outside.rowSummary($0) }, Self.model().rows.map { Self.model().rowSummary($0) }, key)
        }

        // An unresolved selection shows its words and selects nobody.
        for gone in [Self.selected(Self.leclerc, scope: "constructed:f1:other-race"),
                     FieldChooserSelected10868(ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "polymarket", marketID: "5229402",
                                                                                outcomeID: "constructed-withdrawn"),
                                               words: "In focus", unavailableWords: Self.selectionGone)] {
            let unresolved = Self.model(Self.input(selected: gone))
            XCTAssertEqual(unresolved.notice, Self.selectionGone)
            XCTAssertNil(unresolved.selectedOutside)
            XCTAssertFalse(unresolved.rows.contains { unresolved.isSelected($0) })
        }
        let duplicated = Self.model(Self.input(catalogue: Self.catalogue + [Self.record(Self.original(Self.leclerc))], selected: held))
        XCTAssertEqual(duplicated.notice, Self.selectionGone)
        XCTAssertEqual(duplicated.rows[1].resolution, .unavailable)
    }
}

// MARK: - #10868 field before-chance choices — "The shape of the field"

/// The golf outlook's field-comparison card as a stateless leaf on the outlook model.
///
/// The view is SwiftUI and is not rasterised here. What is asserted is the
/// rules it defers to — the outlook's resolver, before-reading tie, scale
/// states, selection notice, choose action and spoken summary as this card
/// consumes them — plus the strip and column helpers the view draws with.
/// Nothing here claims a rendered fit, a native runtime, interaction,
/// VoiceOver behaviour or a qualification.
///
/// RETAINED records come from the DP World India Championship capture
/// (`datagolf:euro:2026140`, captured 2026-10-12T23:29:57Z, start 2026-10-15),
/// `shipping-adoption-20261027/GOLF-OUTLOOK-FIVE-FINISH-RETAINED-CASES.json`
/// (sha256 5ea50120…3f4a): every one of the 190 golfers and 950 original
/// records, one line each, in the packet's own golfer and finish order — golfer,
/// finish, owner selection id, original record id, stored probability, untimed
/// opening probability, the record's own stored update clock and the packet's
/// reference figure, all verbatim ("-" is null). The figures were produced by
/// the approved reference, never by this app. The six leaders are the pinned
/// reference export retained in `GOLF-OUTLOOK-FIELD-CHOICES-RETAINED-CASES.json`
/// (sha256 f1ee2487…8d80); that roster and order are the owner's admission,
/// not a native ranking rule.
///
/// The capture is pre-tournament only. The stored update clock is not a
/// provider generation time and the untimed opening is never a baseline.
/// CONSTRUCTED owner inputs: the before label and its detail wording around the
/// verbatim clock, the scale (0–100%, ticks and words), every card word, the
/// selection and its words, and every later reading, movement, preview, result,
/// during/final phase, hostile tie, 100% value and off-scale ceiling below.
final class FieldBeforeChanceChoices10868Tests: XCTestCase {

    // MARK: Fixtures

    private typealias Record = FieldBeforeChoicesRetainedRecord10868

    private static let scope = "constructed:datagolf:euro:2026140:forecast-profile"
    private static let finishes = ["Win", "Top 5", "Top 10", "Top 20", "Make cut"]
    /// The packet's own absence figure for every missing record.
    private static let missingWords = "Unavailable"
    private static let beforeLabel = "Before tournament"
    private static let unavailable = "Golfer unavailable in this update"
    private static let missingChance = "Not shown on this scale"
    private static let offScale = "Above this scale"
    /// Quantity-neutral: a held original may be another finish of a shown golfer.
    private static let outside = "Your selection is outside this group."
    private static let selectionGone = "Your golfer is unavailable in this update"
    private static let selectedWords = "In focus"
    private static let chooseHint = "Shows this golfer's finish outlook"
    private static let chanceLabel = "Chance to win · pre-tournament"
    private static let prompt = "Pick a golfer to explore their finish outlook."

    /// RETAINED verbatim from the pinned leaders export: name, owner selection
    /// id, raw stored probability, reference figure and stored update clock.
    private static let leaders: [(name: String, selection: String, raw: Double, figure: String, clock: String)] = [
        ("Rory McIlroy", "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352440", 0.1271, "12.7%", "2026-10-12T23:11:05.501054+00:00"),
        ("Tommy Fleetwood", "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352441", 0.067167, "6.7%", "2026-10-12T23:11:05.501054+00:00"),
        ("Min Woo Lee", "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352442", 0.0669, "6.7%", "2026-10-12T23:11:05.501054+00:00"),
        ("Eugenio Chacarra", "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904631", 0.0544, "5.4%", "2026-10-12T23:11:05.501054+00:00"),
        ("Robert MacIntyre", "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352443", 0.048083, "4.8%", "2026-10-12T23:11:05.501054+00:00"),
        ("Shane Lowry", "constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904630", 0.045817, "4.6%", "2026-10-12T23:11:05.501054+00:00"),
    ]

    /// CONSTRUCTED 0–100% scale.
    private static let scale = FieldOutlookScale10868(
        ceiling: 1,
        ticks: [
            FieldOutlookTick10868(probability: 0, label: "0%"),
            FieldOutlookTick10868(probability: 0.25, label: "25%"),
            FieldOutlookTick10868(probability: 0.5, label: "50%"),
            FieldOutlookTick10868(probability: 0.75, label: "75%"),
            FieldOutlookTick10868(probability: 1, label: "100%"),
        ],
        words: "0–100% chance to win · each golfer's own estimate"
    )

    private static let outlookCopy = FieldOutlookCopy10868(
        title: "The shape of the field",
        note: "DataGolf model · stored before the tournament",
        graphicLabel: "Pre-tournament win chances",
        missingChance: missingChance,
        offScale: offScale,
        outsideDisplayed: outside,
        previousLabel: "Previous golfer",
        nextLabel: "Next golfer",
        details: "Original outcomes & rules",
        detailsHint: nil,
        resultUnknown: "Result unconfirmed"
    )

    private static func retained() throws -> [Record] {
        try fieldBeforeChoicesRetainedTable.split(separator: "\n").map { line throws -> Record in
            let split = line.split(separator: "\t", omittingEmptySubsequences: false).map(String.init)
            let fields = try XCTUnwrap(split.count == 8 ? split : nil, String(line))
            func number(_ field: String) throws -> Double? {
                if field == "-" { return nil }
                return try XCTUnwrap(Double(field), field)
            }
            let parts = fields[2].split(separator: "|", omittingEmptySubsequences: false).map(String.init)
            let exact = try XCTUnwrap(parts.count == 4 ? parts : nil, fields[2])
            return Record(
                golfer: fields[0], label: fields[1], selection: fields[2], rawID: fields[3],
                probability: try number(fields[4]), opening: try number(fields[5]),
                lastUpdated: fields[6], figure: fields[7],
                ref: FieldChooserOriginalRef10868(scope: exact[0], source: exact[1], marketID: exact[2], outcomeID: exact[3])
            )
        }
    }

    private static func wins(_ all: [Record]) -> [Record] { all.filter { $0.label == "Win" } }

    private static func win(_ all: [Record], _ golfer: String) throws -> Record {
        try XCTUnwrap(wins(all).first { $0.golfer == golfer }, golfer)
    }

    private static func record(_ all: [Record], _ golfer: String, _ finish: String) throws -> Record {
        try XCTUnwrap(all.first { $0.golfer == golfer && $0.label == finish }, "\(golfer) \(finish)")
    }

    private static func leaderRecords(_ all: [Record]) throws -> [Record] {
        try leaders.map { try win(all, $0.name) }
    }

    /// CONSTRUCTED wording around the record's own verbatim stored clock.
    private static func detail(_ record: Record) -> String {
        "stored update \(record.lastUpdated) · DataGolf model estimate"
    }

    private static func reading(_ record: Record) -> FieldChooserReading10868 {
        FieldChooserReading10868(
            label: beforeLabel,
            value: record.probability == nil ? .missing(record.figure) : .recorded(text: record.figure, detail: detail(record))
        )
    }

    /// The spoken reading, written out rather than read back from the model.
    private static func spoken(_ record: Record) -> String {
        record.probability == nil ? "\(beforeLabel): \(record.figure)" : "\(beforeLabel): \(record.figure), \(detail(record))"
    }

    private static func original(_ record: Record) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: record.ref, name: record.golfer,
            plan: .single(reading(record)),
            preview: FieldChooserPreview10868(history: nil, absence: "No history in this card"),
            movement: nil, clock: nil, result: nil,
            browseStatus: record.label
        )
    }

    /// CONSTRUCTED hostile record: a later reading, movement, a preview, a later
    /// clock and a result ride along with the same before reading.
    private static func hostile(_ record: Record) -> FieldChooserOriginal10868 {
        FieldChooserOriginal10868(
            ref: record.ref, name: record.golfer,
            plan: .comparison(before: reading(record), later: laterReading),
            preview: FieldChooserPreview10868(
                history: FieldChooserHistory10868(
                    segments: [[FieldChooserPoint10868(time: 1, probability: 0.31)]],
                    emphasis: FieldChooserPoint10868(time: 1, probability: 0.31),
                    beforeReference: record.probability, gaps: []
                ),
                absence: "No history in this card"
            ),
            movement: "Up 18.3 pts since the start",
            clock: "Oct 16, 2:10 PM PT",
            result: FieldChooserResult10868(title: "Final result", words: "Won"),
            browseStatus: "Recorded in Round 2"
        )
    }

    private static let laterReading = FieldChooserReading10868(
        label: "Recorded in Round 2", value: .recorded(text: "31.0%", detail: "Oct 16, 2:10 PM PT · DataGolf")
    )

    private static func tie(_ record: Record) -> FieldOutlookBeforeChance10868? {
        record.probability.map { FieldOutlookBeforeChance10868(ref: record.ref, probability: $0, reading: reading(record)) }
    }

    private static func slot(_ record: Record) -> FieldOutlookSlot10868 {
        FieldOutlookSlot10868(ref: record.ref, label: record.golfer, shortLabel: record.golfer)
    }

    private static func selected(_ ref: FieldChooserOriginalRef10868) -> FieldChooserSelected10868 {
        FieldChooserSelected10868(ref: ref, words: selectedWords, unavailableWords: selectionGone)
    }

    /// The whole canonical catalogue and every finite tie of every finish, unless replaced.
    private static func input(
        _ all: [Record],
        displayed: [FieldOutlookSlot10868],
        catalogue: [FieldChooserOriginal10868]? = nil,
        chances: [FieldOutlookBeforeChance10868]? = nil,
        selected: FieldChooserSelected10868? = nil,
        scale: FieldOutlookScale10868 = FieldBeforeChanceChoices10868Tests.scale,
        phase: FieldOutlookPhase10868 = .before,
        prompt: String? = FieldBeforeChanceChoices10868Tests.prompt
    ) -> FieldBeforeChoicesInput10868 {
        FieldBeforeChoicesInput10868(
            outlook: FieldOutlookInput10868(
                scope: Self.scope,
                catalogue: catalogue ?? all.map(original),
                selected: selected,
                displayed: displayed,
                traversal: [],
                chances: chances ?? all.compactMap(tie),
                scale: scale,
                phase: phase,
                copy: outlookCopy,
                unavailableWords: unavailable,
                chooseHint: chooseHint
            ),
            copy: FieldBeforeChoicesCopy10868(eyebrow: "Six leading captured win estimates", chanceLabel: chanceLabel, choosePrompt: prompt)
        )
    }

    private static func model(_ input: FieldBeforeChoicesInput10868) -> FieldBeforeChoicesModel10868 {
        FieldBeforeChoicesModel10868(input)
    }

    private static func leadersModel(_ all: [Record], selected: FieldChooserSelected10868? = nil) throws -> FieldBeforeChoicesModel10868 {
        let shown = try leaderRecords(all)
        return model(input(all, displayed: shown.map(slot), selected: selected))
    }

    /// What a card shows and does, for comparing neighbours across inputs.
    private static func shown(_ model: FieldBeforeChoicesModel10868, _ card: FieldOutlookBar10868) -> String {
        [
            card.slot.label,
            "\(card.chance)",
            model.outlook.figure(card) ?? "-",
            model.outlook.stateWords(card) ?? "-",
            model.outlook.barSummary(card),
            "\(String(describing: model.outlook.barAction(card, canChoose: true)))",
        ].joined(separator: " | ")
    }

    // MARK: Retained packet

    func testRetainedPacketKeepsEveryOriginalAndEveryOwnerWinChoice() throws {
        let all = try Self.retained()
        XCTAssertEqual(all.count, 950)
        XCTAssertEqual(Set(all.map(\.golfer)).count, 190)
        XCTAssertEqual(Set(all.map(\.selection)).count, 950)
        XCTAssertEqual(Set(all.map(\.rawID)).count, 950)
        XCTAssertEqual(Set(all.map(\.ref)).count, 950)
        for record in all {
            XCTAssertEqual(record.ref.scope, Self.scope, record.selection)
            XCTAssertEqual(record.ref.source, "datagolf", record.selection)
            XCTAssertEqual(record.ref.outcomeID, record.rawID, record.selection)
        }
        for label in Self.finishes {
            let finish = all.filter { $0.label == label }
            XCTAssertEqual(finish.count, 190, label)
            XCTAssertEqual(finish.filter { $0.probability != nil }.count, 144, label)
            XCTAssertEqual(finish.filter { $0.probability == nil }.count, 46, label)
        }
        let wins = Self.wins(all)
        XCTAssertEqual(Set(wins.map(\.golfer)).count, 190, "one win original per golfer")
        XCTAssertEqual(wins.filter { $0.probability == 0 }.map(\.golfer), ["Shubham Jaglan", "Subash Tamang"])
        XCTAssertEqual(Set(all.filter { $0.probability == nil }.map(\.figure)), [Self.missingWords])

        // Every canonical original stays in the card's catalogue and resolves to itself.
        let leaders = try Self.leaderRecords(all)
        let model = Self.model(Self.input(all, displayed: leaders.map(Self.slot)))
        XCTAssertEqual(model.input.outlook.catalogue.count, 950)
        for record in all {
            XCTAssertEqual(model.field.resolve(record.ref), .original(Self.original(record)), record.selection)
        }
    }

    func testEveryRetainedWinOriginalIsAChoiceWithItsOwnChanceFigureAndClock() throws {
        let all = try Self.retained()
        let wins = Self.wins(all)
        // The owner's window may be the whole field.
        let model = Self.model(Self.input(all, displayed: wins.map(Self.slot)))
        let cards = model.cards
        XCTAssertEqual(cards.count, 190, "no cap")
        XCTAssertEqual(cards.map(\.slot.ref), wins.map(\.ref), "the owner's order")
        var placed = 0, missing = 0, zeros = 0
        for (card, record) in zip(cards, wins) {
            let name = record.golfer
            XCTAssertEqual(card.resolution, .original(Self.original(record)), name)
            XCTAssertEqual(model.outlook.figure(card), record.figure, name)
            XCTAssertNil(model.outlook.stateWords(card), name)
            XCTAssertEqual(model.outlook.barSummary(card), Self.spoken(record), name)
            XCTAssertEqual(model.outlook.barAction(card, canChoose: true), .choose(record.ref), "a missing chance never makes a golfer unchoosable: \(name)")
            if let probability = record.probability {
                placed += 1
                if probability == 0 { zeros += 1 }
                XCTAssertEqual(card.chance, .value(probability: probability, fraction: probability), name)
                XCTAssertTrue(model.isRecorded(card), name)
            } else {
                missing += 1
                XCTAssertEqual(card.chance, .unavailable, "missing is never zero: \(name)")
                XCTAssertFalse(model.isRecorded(card), name)
            }
        }
        XCTAssertEqual([placed, missing, zeros], [144, 46, 2])
        XCTAssertFalse(cards.contains { $0.slot.ref.marketID != "65391342" }, "only the owner's displayed win originals")
        XCTAssertNil(model.outlook.notice)
        XCTAssertNil(model.selectedOutside)
    }

    func testSixRetainedLeadersShowTheirOwnFiguresIdsAndClocks() throws {
        let all = try Self.retained()
        let records = try Self.leaderRecords(all)
        // Fixture reconciliation: the export's six are the packet's own win records.
        for (leader, record) in zip(Self.leaders, records) {
            XCTAssertEqual(record.selection, leader.selection, leader.name)
            XCTAssertEqual(record.probability, leader.raw, leader.name)
            XCTAssertEqual(record.figure, leader.figure, leader.name)
            XCTAssertEqual(record.lastUpdated, leader.clock, leader.name)
        }
        XCTAssertEqual(Array(Self.wins(all).filter { $0.probability != nil }.prefix(6)).map(\.golfer), Self.leaders.map { $0.name },
                       "the reference's leaders are its first six finite win records — reference admission, not a native rule")

        let rory = records[0]
        let model = try Self.leadersModel(all, selected: Self.selected(rory.ref))
        let cards = model.cards
        XCTAssertEqual(cards.map(\.slot.ref.outcomeID), ["246352440", "246352441", "246352442", "245904631", "246352443", "245904630"])
        XCTAssertEqual(cards.map(\.slot.label), Self.leaders.map { $0.name })
        XCTAssertEqual(cards.map { model.outlook.figure($0) }, ["12.7%", "6.7%", "6.7%", "5.4%", "4.8%", "4.6%"])
        XCTAssertEqual(cards.map(\.chance), [
            .value(probability: 0.1271, fraction: 0.1271),
            .value(probability: 0.067167, fraction: 0.067167),
            .value(probability: 0.0669, fraction: 0.0669),
            .value(probability: 0.0544, fraction: 0.0544),
            .value(probability: 0.048083, fraction: 0.048083),
            .value(probability: 0.045817, fraction: 0.045817),
        ])
        // Fleetwood and Lee share a figure and keep their own raw places.
        XCTAssertNotEqual(cards[1].chance, cards[2].chance)
        // Chacarra's untimed opening (0.04145) is never a baseline or a mark.
        XCTAssertEqual(records[3].opening, 0.04145)
        XCTAssertEqual(cards[3].chance.fraction, 0.0544)

        XCTAssertEqual(cards.map { model.outlook.isSelected($0) }, [true, false, false, false, false, false])
        XCTAssertEqual(model.outlook.barSummary(cards[0]),
                       "In focus. Before tournament: 12.7%, stored update 2026-10-12T23:11:05.501054+00:00 · DataGolf model estimate")
        XCTAssertEqual(model.outlook.barSummary(cards[5]),
                       "Before tournament: 4.6%, stored update 2026-10-12T23:11:05.501054+00:00 · DataGolf model estimate")
        XCTAssertEqual(Array(cards.dropFirst()).map { model.outlook.barSummary($0) }, Array(records.dropFirst()).map(Self.spoken))
        XCTAssertNil(model.outlook.notice)
        XCTAssertNil(model.selectedOutside)
        XCTAssertTrue(model.showsScale)
        XCTAssertEqual(model.ticks.map(\.label), ["0%", "25%", "50%", "75%", "100%"])
        XCTAssertEqual(model.ticks.map(\.fraction), [0, 0.25, 0.5, 0.75, 1])
    }

    // MARK: Values

    func testGenuineZeroTinyAndConstructedHundredSitAtTheirOwnPlaces() throws {
        let all = try Self.retained()
        let jaglan = try Self.win(all, "Shubham Jaglan")
        let tamang = try Self.win(all, "Subash Tamang")
        let willett = try Self.win(all, "Danny Willett")
        // CONSTRUCTED: a genuine 100% on Rory's exact original.
        let rory = try Self.win(all, "Rory McIlroy")
        let hundred = Record(golfer: rory.golfer, label: rory.label, selection: rory.selection, rawID: rory.rawID,
                             probability: 1, opening: nil, lastUpdated: rory.lastUpdated, figure: "100%", ref: rory.ref)
        let shown = [jaglan, tamang, willett, hundred]
        let catalogue = all.map { $0.ref == rory.ref ? Self.original(hundred) : Self.original($0) }
        let chances = all.compactMap { $0.ref == rory.ref ? Self.tie(hundred) : Self.tie($0) }
        let model = Self.model(Self.input(all, displayed: shown.map(Self.slot), catalogue: catalogue, chances: chances))
        let cards = model.cards
        XCTAssertEqual(cards.map(\.chance), [
            .value(probability: 0, fraction: 0),
            .value(probability: 0, fraction: 0),
            .value(probability: 0.000967, fraction: 0.000967),
            .value(probability: 1, fraction: 1),
        ])
        XCTAssertEqual(cards.map { model.outlook.figure($0) }, ["0%", "0%", "<0.1%", "100%"], "verbatim, never formatted")
        XCTAssertEqual(cards.map { model.outlook.stateWords($0) }, [nil, nil, nil, nil])

        let size = CGSize(width: 300, height: 12)
        let inset: CGFloat = 7
        let zero = try XCTUnwrap(FieldFinishGeometry10868.stripPlan(fraction: cards[0].chance.fraction, ticks: [], in: size, inset: inset, dotDiameter: 12))
        let zeroDot = try XCTUnwrap(zero.dot, "a real zero is a hollow endpoint")
        XCTAssertEqual(zeroDot.midX, zero.zeroX)
        XCTAssertGreaterThanOrEqual(zeroDot.minX, 0)
        XCTAssertNil(FieldBeforeChoicesGeometry10868.prefix(zero, lineWidth: 7), "no prefix at zero")
        let full = try XCTUnwrap(FieldFinishGeometry10868.stripPlan(fraction: cards[3].chance.fraction, ticks: [], in: size, inset: inset, dotDiameter: 12))
        let fullDot = try XCTUnwrap(full.dot)
        XCTAssertEqual(fullDot.midX, full.ceilingX)
        XCTAssertLessThanOrEqual(fullDot.maxX, size.width)
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.prefix(full, lineWidth: 7),
                       CGRect(x: full.zeroX, y: full.baselineY - 3.5, width: full.ceilingX - full.zeroX, height: 7))
    }

    func testMissingInvalidMismatchedForeignAndDuplicateTiesDrawNothingAndKeepNeighbours() throws {
        let all = try Self.retained()
        let leaders = try Self.leaderRecords(all)
        let fleetwood = leaders[1]
        let baseline = try Self.leadersModel(all)
        let fleetwoodTie = try XCTUnwrap(Self.tie(fleetwood))
        let others = all.filter { $0.ref != fleetwood.ref }.compactMap(Self.tie)
        func reading(label: String = Self.beforeLabel, text: String = "6.7%", detail: String? = nil) -> FieldChooserReading10868 {
            FieldChooserReading10868(label: label, value: .recorded(text: text, detail: detail ?? Self.detail(fleetwood)))
        }
        let foreign = FieldChooserOriginalRef10868(scope: "constructed:datagolf:euro:2026139:forecast-profile", source: "datagolf",
                                                   marketID: fleetwood.ref.marketID, outcomeID: fleetwood.ref.outcomeID)
        let top5 = try Self.record(all, "Tommy Fleetwood", "Top 5")
        let hostileTies: [(String, [FieldOutlookBeforeChance10868])] = [
            ("no tie", []),
            ("NaN", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: .nan, reading: reading())]),
            ("infinite", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: .infinity, reading: reading())]),
            ("negative", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: -0.067167, reading: reading())]),
            ("above one", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: 1.067167, reading: reading())]),
            ("mismatched figure", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: 0.067167, reading: reading(text: "6.8%"))]),
            ("mismatched clock", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: 0.067167,
                                                                reading: reading(detail: "stored update 2026-10-12T19:09:40.403188+00:00 · DataGolf model estimate"))]),
            ("mismatched label", [FieldOutlookBeforeChance10868(ref: fleetwood.ref, probability: 0.067167, reading: reading(label: "Opening"))]),
            ("foreign scope", [FieldOutlookBeforeChance10868(ref: foreign, probability: 0.067167, reading: reading())]),
            ("another finish's tie", [FieldOutlookBeforeChance10868(ref: top5.ref, probability: 0.067167, reading: reading())]),
            ("duplicate identical", [fleetwoodTie, fleetwoodTie]),
        ]
        for (name, ties) in hostileTies {
            let model = Self.model(Self.input(all, displayed: leaders.map(Self.slot), chances: others + ties))
            let cards = model.cards
            XCTAssertEqual(cards[1].resolution, .original(Self.original(fleetwood)), name)
            XCTAssertEqual(cards[1].chance, .unavailable, name)
            XCTAssertEqual(model.outlook.figure(cards[1]), "6.7%", "the golfer's own figure stays: \(name)")
            XCTAssertEqual(model.outlook.stateWords(cards[1]), Self.missingChance, name)
            XCTAssertEqual(model.outlook.barSummary(cards[1]), "\(Self.spoken(fleetwood)). \(Self.missingChance)", name)
            XCTAssertEqual(model.outlook.barAction(cards[1], canChoose: true), .choose(fleetwood.ref), name)
            for index in [0, 2, 3, 4, 5] {
                XCTAssertEqual(Self.shown(model, cards[index]), Self.shown(baseline, baseline.cards[index]), "\(name): neighbour \(index)")
            }
        }

        // A golfer whose before estimate is missing keeps its absence words, even beside a stray tie.
        let noren = try Self.win(all, "Alex Noren")
        XCTAssertNil(noren.probability)
        let stray = FieldOutlookBeforeChance10868(ref: noren.ref, probability: 0.05,
                                                  reading: FieldChooserReading10868(label: Self.beforeLabel, value: .recorded(text: "5%", detail: Self.detail(noren))))
        let withNoren = Self.model(Self.input(all, displayed: (leaders + [noren]).map(Self.slot), chances: all.compactMap(Self.tie) + [stray]))
        let card = try XCTUnwrap(withNoren.cards.last)
        XCTAssertEqual(card.chance, .unavailable)
        XCTAssertNotEqual(card.chance, .value(probability: 0, fraction: 0), "missing is never drawn as zero")
        XCTAssertEqual(withNoren.outlook.figure(card), Self.missingWords)
        XCTAssertFalse(withNoren.isRecorded(card))
        XCTAssertNil(withNoren.outlook.stateWords(card))
        XCTAssertEqual(withNoren.outlook.barSummary(card), "Before tournament: Unavailable")
    }

    func testAboveTheCeilingOrWithoutAValidScaleNoMarkIsDrawn() throws {
        let all = try Self.retained()
        let leaders = try Self.leaderRecords(all)
        // CONSTRUCTED 0–10% ceiling: only Rory's 12.7% is above it.
        let narrow = FieldOutlookScale10868(ceiling: 0.1, ticks: [FieldOutlookTick10868(probability: 0, label: "0%"),
                                                                    FieldOutlookTick10868(probability: 0.1, label: "10%"),
                                                                    FieldOutlookTick10868(probability: 0.25, label: "25%")],
                                            words: "0–10% chance to win")
        let model = Self.model(Self.input(all, displayed: leaders.map(Self.slot), scale: narrow))
        let cards = model.cards
        XCTAssertEqual(cards[0].chance, .offScale)
        XCTAssertEqual(model.outlook.figure(cards[0]), "12.7%")
        XCTAssertEqual(model.outlook.stateWords(cards[0]), Self.offScale)
        XCTAssertEqual(model.outlook.barAction(cards[0], canChoose: true), .choose(leaders[0].ref))
        let empty = try XCTUnwrap(FieldFinishGeometry10868.stripPlan(fraction: cards[0].chance.fraction, ticks: [], in: CGSize(width: 300, height: 12), inset: 7, dotDiameter: 12))
        XCTAssertNil(empty.dot)
        XCTAssertNil(FieldBeforeChoicesGeometry10868.prefix(empty, lineWidth: 7))
        for (card, record) in zip(cards.dropFirst(), leaders.dropFirst()) {
            let probability = try XCTUnwrap(record.probability)
            XCTAssertEqual(card.chance, .value(probability: probability, fraction: probability / 0.1), record.golfer)
            XCTAssertNil(model.outlook.stateWords(card), record.golfer)
        }
        XCTAssertEqual(model.ticks.map(\.label), ["0%", "10%"], "a tick off the scale is not placed")

        for invalid in [FieldOutlookScale10868(ceiling: 0, ticks: Self.scale.ticks, words: Self.scale.words),
                        FieldOutlookScale10868(ceiling: 1.5, ticks: Self.scale.ticks, words: Self.scale.words),
                        FieldOutlookScale10868(ceiling: .nan, ticks: Self.scale.ticks, words: Self.scale.words)] {
            let broken = Self.model(Self.input(all, displayed: leaders.map(Self.slot), scale: invalid))
            XCTAssertFalse(broken.showsScale)
            XCTAssertEqual(broken.ticks, [])
            XCTAssertEqual(broken.cards.map(\.chance), Array(repeating: FieldOutlookChance10868.unavailable, count: 6))
            XCTAssertEqual(broken.cards.map { broken.outlook.figure($0) }, ["12.7%", "6.7%", "6.7%", "5.4%", "4.8%", "4.6%"])
        }
        let wordless = Self.model(Self.input(all, displayed: leaders.map(Self.slot),
                                             scale: FieldOutlookScale10868(ceiling: 1, ticks: Self.scale.ticks, words: " ")))
        XCTAssertFalse(wordless.showsScale, "never tick labels without the owner's scale words")
        XCTAssertEqual(wordless.ticks, [])
    }

    // MARK: Identity

    func testRepeatedForeignAndIncompleteSlotsKeepTheirLabelsAndNeighbours() throws {
        let all = try Self.retained()
        let leaders = try Self.leaderRecords(all)
        let baseline = try Self.leadersModel(all)
        let fleetwood = leaders[1]

        let repeated = Self.model(Self.input(all, displayed: leaders.map(Self.slot) + [Self.slot(fleetwood)]))
        for index in [1, 6] {
            let card = repeated.cards[index]
            XCTAssertEqual(card.resolution, .unavailable, "a displayed golfer listed twice is ambiguous")
            XCTAssertEqual(card.chance, .unavailable)
            XCTAssertNil(repeated.outlook.figure(card))
            XCTAssertEqual(repeated.outlook.stateWords(card), Self.unavailable)
            XCTAssertNil(repeated.outlook.barAction(card, canChoose: true))
            XCTAssertEqual(repeated.outlook.barSummary(card), "Tommy Fleetwood. \(Self.unavailable)")
        }
        for index in [0, 2, 3, 4, 5] {
            XCTAssertEqual(Self.shown(repeated, repeated.cards[index]), Self.shown(baseline, baseline.cards[index]), "neighbour \(index)")
        }

        let foreign = FieldOutlookSlot10868(
            ref: FieldChooserOriginalRef10868(scope: "constructed:datagolf:euro:2026139:forecast-profile", source: "datagolf",
                                              marketID: fleetwood.ref.marketID, outcomeID: fleetwood.ref.outcomeID),
            label: "Tommy Fleetwood", shortLabel: "Tommy Fleetwood")
        let incomplete = FieldOutlookSlot10868(
            ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "datagolf", marketID: fleetwood.ref.marketID, outcomeID: " "),
            label: "Tommy Fleetwood", shortLabel: "Tommy Fleetwood")
        let withdrawn = FieldOutlookSlot10868(
            ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "datagolf", marketID: "65391342", outcomeID: "constructed-withdrawn"),
            label: "Constructed withdrawn golfer", shortLabel: "Constructed withdrawn golfer")
        for bad in [foreign, incomplete, withdrawn] {
            var displayed = leaders.map(Self.slot)
            displayed[1] = bad
            let model = Self.model(Self.input(all, displayed: displayed))
            XCTAssertEqual(model.cards[1].resolution, .unavailable, bad.label)
            XCTAssertNil(model.outlook.barAction(model.cards[1], canChoose: true), bad.label)
            XCTAssertEqual(model.outlook.barSummary(model.cards[1]), "\(bad.label). \(Self.unavailable)")
            for index in [0, 2, 3, 4, 5] {
                XCTAssertEqual(Self.shown(model, model.cards[index]), Self.shown(baseline, baseline.cards[index]), "\(bad.label): neighbour \(index)")
            }
        }

        // A catalogue carrying Lowry's record twice resolves neither copy.
        let lowry = leaders[5]
        let duplicated = Self.model(Self.input(all, displayed: leaders.map(Self.slot), catalogue: all.map(Self.original) + [Self.original(lowry)]))
        XCTAssertEqual(duplicated.cards[5].resolution, .unavailable)
        XCTAssertNil(duplicated.outlook.barAction(duplicated.cards[5], canChoose: true))
        XCTAssertEqual(Self.shown(duplicated, duplicated.cards[0]), Self.shown(baseline, baseline.cards[0]))
    }

    func testSelectionAbsentUnresolvedOrOutsideTheShownGolfersIsNeverALeader() throws {
        let all = try Self.retained()
        let leaders = try Self.leaderRecords(all)
        let baseline = try Self.leadersModel(all)
        XCTAssertNil(baseline.outlook.notice)
        XCTAssertNil(baseline.selectedOutside)
        XCTAssertFalse(baseline.cards.contains { baseline.outlook.isSelected($0) })

        // Outside the six: a mid-field golfer, a golfer with no estimate, and
        // Rory's own Top 5 original — the same name is never matched to his win card.
        let outsiders = try [Self.win(all, "Aaron Rai"), Self.win(all, "Alex Noren"), Self.record(all, "Rory McIlroy", "Top 5")]
        for record in outsiders {
            let model = try Self.leadersModel(all, selected: Self.selected(record.ref))
            XCTAssertEqual(model.outlook.notice, Self.outside, record.selection)
            // Static context only: the exact held original, its whole name and
            // the selected cue. It is not a card, so it has no chance, strip,
            // quantity label or action to show.
            let held = try XCTUnwrap(model.selectedOutside, record.selection)
            XCTAssertEqual(held, Self.original(record), record.selection)
            XCTAssertEqual(held.ref, record.ref)
            XCTAssertEqual(held.name, record.golfer)
            XCTAssertTrue(model.field.isSelected(held))
            let words = try XCTUnwrap(model.selectedOutsideWords, record.selection)
            XCTAssertEqual(words, Self.selectedWords)
            XCTAssertFalse(words.contains(Self.chanceLabel), record.selection)
            XCTAssertFalse(words.contains(Self.beforeLabel), record.selection)
            // The owner's six stay exactly as admitted: same refs, figures and
            // controls; the outsider never joins, rewrites or stands in.
            XCTAssertEqual(model.cards.map(\.slot.ref), leaders.map(\.ref), record.selection)
            XCTAssertFalse(model.cards.contains { $0.slot.ref == record.ref }, record.selection)
            XCTAssertFalse(model.cards.contains { model.outlook.isSelected($0) }, "no leader stands in: \(record.selection)")
            XCTAssertEqual(model.cards.map { Self.shown(model, $0) }, baseline.cards.map { Self.shown(baseline, $0) }, record.selection)
            XCTAssertEqual(model.choosePrompt(canChoose: true), Self.prompt, "the prompt comes from the six alone")
        }

        // Rory's Top 5 chance is never printed as a win chance: his win card
        // keeps 12.7%, and no compared card carries the held Top 5 figure.
        let roryTop5 = try Self.record(all, "Rory McIlroy", "Top 5")
        XCTAssertEqual(roryTop5.figure, "35.2%")
        XCTAssertNotEqual(roryTop5.ref, leaders[0].ref)
        let heldTop5 = try Self.leadersModel(all, selected: Self.selected(roryTop5.ref))
        XCTAssertEqual(heldTop5.cards.count, 6)
        XCTAssertEqual(heldTop5.cards[0].slot.ref, leaders[0].ref)
        XCTAssertEqual(heldTop5.outlook.figure(heldTop5.cards[0]), "12.7%")
        XCTAssertFalse(heldTop5.cards.contains { heldTop5.outlook.figure($0) == roryTop5.figure })
        XCTAssertFalse(heldTop5.outlook.isSelected(heldTop5.cards[0]), "his win card is not the held Top 5")

        // Unresolved selections show the owner's words and select nobody.
        let rory = leaders[0]
        let gone: [FieldChooserSelected10868] = [
            Self.selected(FieldChooserOriginalRef10868(scope: "constructed:datagolf:euro:2026139:forecast-profile", source: "datagolf",
                                                       marketID: rory.ref.marketID, outcomeID: rory.ref.outcomeID)),
            Self.selected(FieldChooserOriginalRef10868(scope: Self.scope, source: "datagolf", marketID: "65391342", outcomeID: "constructed-withdrawn")),
        ]
        for selection in gone {
            let model = try Self.leadersModel(all, selected: selection)
            XCTAssertEqual(model.outlook.notice, Self.selectionGone)
            XCTAssertNil(model.selectedOutside)
            XCTAssertFalse(model.cards.contains { model.outlook.isSelected($0) })
        }
        let duplicated = Self.model(Self.input(all, displayed: leaders.map(Self.slot),
                                               catalogue: all.map(Self.original) + [Self.original(rory)], selected: Self.selected(rory.ref)))
        XCTAssertEqual(duplicated.outlook.notice, Self.selectionGone)
        XCTAssertNil(duplicated.selectedOutside)
        XCTAssertEqual(duplicated.cards[0].resolution, .unavailable)
        XCTAssertFalse(duplicated.cards.contains { duplicated.outlook.isSelected($0) })
    }

    // MARK: Choose

    func testChoosingHandsBackTheExactOriginalAndNothingActsWithoutACallback() throws {
        let all = try Self.retained()
        let leaders = try Self.leaderRecords(all)
        let model = try Self.leadersModel(all)
        var chosen: [FieldChooserOriginalRef10868] = []
        for (card, record) in zip(model.cards, leaders) {
            let action = try XCTUnwrap(model.outlook.barAction(card, canChoose: true), record.golfer)
            XCTAssertEqual(model.outlook.hint(action), Self.chooseHint)
            action.perform(onChoose: { chosen.append($0) }, onControl: { _ in XCTFail("no control on this card") })
            XCTAssertNil(model.outlook.barAction(card, canChoose: false), record.golfer)
            XCTAssertEqual(model.outlook.hint(nil), "")
        }
        XCTAssertEqual(chosen, leaders.map(\.ref), "each card hands back its own exact original, once")
        XCTAssertEqual(model.choosePrompt(canChoose: true), Self.prompt)
        XCTAssertNil(model.choosePrompt(canChoose: false), "no callback, no prompt")
        XCTAssertNil(Self.model(Self.input(all, displayed: leaders.map(Self.slot), prompt: " ")).choosePrompt(canChoose: true))
        XCTAssertNil(Self.model(Self.input(all, displayed: leaders.map(Self.slot), prompt: nil)).choosePrompt(canChoose: true))

        // Nothing resolves: nothing chooses and no prompt.
        let gone = FieldOutlookSlot10868(
            ref: FieldChooserOriginalRef10868(scope: Self.scope, source: "datagolf", marketID: "65391342", outcomeID: "constructed-withdrawn"),
            label: "Constructed withdrawn golfer", shortLabel: "Constructed withdrawn golfer")
        let unresolved = Self.model(Self.input(all, displayed: [gone]))
        XCTAssertNil(unresolved.outlook.barAction(unresolved.cards[0], canChoose: true))
        XCTAssertNil(unresolved.choosePrompt(canChoose: true))
        XCTAssertNil(Self.model(Self.input(all, displayed: [])).choosePrompt(canChoose: true))

        // A selection held outside an unresolved or empty window is static
        // context: it is kept by identity, but nothing chooses and no prompt shows.
        let held = try [Self.win(all, "Aaron Rai"), Self.record(all, "Rory McIlroy", "Top 5")]
        let windows: [[FieldOutlookSlot10868]] = [[gone], []]
        for record in held {
            for displayed in windows {
                let outside = Self.model(Self.input(all, displayed: displayed, selected: Self.selected(record.ref)))
                XCTAssertEqual(outside.selectedOutside, Self.original(record), record.selection)
                XCTAssertEqual(outside.outlook.notice, Self.outside)
                XCTAssertNil(outside.choosePrompt(canChoose: true), "no fake prompt: \(record.selection)")
                XCTAssertNil(outside.choosePrompt(canChoose: false))
                XCTAssertTrue(outside.cards.allSatisfy { outside.outlook.barAction($0, canChoose: true) == nil })
                XCTAssertEqual(outside.cards.count, displayed.count)
            }
        }
    }

    func testOwnerWindowsBeyondSixAndReorderedCohortsKeepTheOwnerOrder() throws {
        let all = try Self.retained()
        let wins = Self.wins(all)
        let leaders = try Self.leaderRecords(all)
        let missing = wins.filter { $0.probability == nil }
        let roryTop5 = try Self.record(all, "Rory McIlroy", "Top 5")
        let roryMakeCut = try Self.record(all, "Rory McIlroy", "Make cut")
        let windows: [[Record]] = [
            Array(wins.prefix(12)),
            Array(leaders.reversed()),
            [leaders[3], missing[0], leaders[0], missing[1], leaders[5]],
            // The owner may display any original; it is never swapped for the same golfer's win.
            [roryTop5, leaders[0], roryMakeCut],
        ]
        for window in windows {
            let model = Self.model(Self.input(all, displayed: window.map(Self.slot)))
            XCTAssertEqual(model.cards.count, window.count)
            XCTAssertEqual(model.cards.map(\.slot.ref), window.map(\.ref))
            XCTAssertEqual(model.cards.map { model.outlook.figure($0) }, window.map(\.figure))
            XCTAssertEqual(model.cards.map(\.chance), window.map { $0.probability.map { FieldOutlookChance10868.value(probability: $0, fraction: $0) } ?? FieldOutlookChance10868.unavailable })
            XCTAssertEqual(model.cards.map { model.outlook.barSummary($0) }, window.map(Self.spoken))
            XCTAssertEqual(model.cards.map { model.outlook.barAction($0, canChoose: true) }, window.map { Optional(FieldChooserAction10868.choose($0.ref)) })
        }
    }

    // MARK: Phases

    func testLaterReadingsMovementPreviewsAndResultsNeverReachTheCard() throws {
        let all = try Self.retained()
        let leaders = try Self.leaderRecords(all)
        let leaderRefs = Set(leaders.map(\.ref))
        let baseline = try Self.leadersModel(all)
        let catalogue = all.map { leaderRefs.contains($0.ref) ? Self.hostile($0) : Self.original($0) }
        // CONSTRUCTED during and final phases; the capture is pre-tournament only.
        for phase in [FieldOutlookPhase10868.before, .during, .final] {
            let model = Self.model(Self.input(all, displayed: leaders.map(Self.slot), catalogue: catalogue,
                                              selected: Self.selected(leaders[0].ref), phase: phase))
            let selectedBaseline = try Self.leadersModel(all, selected: Self.selected(leaders[0].ref))
            XCTAssertEqual(model.cards.map(\.chance), baseline.cards.map(\.chance), "\(phase)")
            XCTAssertEqual(model.cards.map { model.outlook.figure($0) }, baseline.cards.map { baseline.outlook.figure($0) }, "\(phase)")
            XCTAssertEqual(model.cards.map { model.outlook.barSummary($0) }, selectedBaseline.cards.map { selectedBaseline.outlook.barSummary($0) }, "\(phase)")
            for card in model.cards {
                let summary = model.outlook.barSummary(card)
                for leak in ["31.0%", "Round 2", "Up 18.3", "Won", "Final result", "Oct 16"] {
                    XCTAssertFalse(summary.contains(leak), "\(phase): \(leak) in \(summary)")
                }
                XCTAssertNotEqual(model.outlook.figure(card), "31.0%", "\(phase)")
            }
        }

        // A tie carrying the later reading is not the before reading.
        let rory = leaders[0]
        let laterTie = FieldOutlookBeforeChance10868(ref: rory.ref, probability: 0.31, reading: Self.laterReading)
        let model = Self.model(Self.input(all, displayed: leaders.map(Self.slot), catalogue: catalogue,
                                          chances: all.filter { $0.ref != rory.ref }.compactMap(Self.tie) + [laterTie], phase: .during))
        XCTAssertEqual(model.cards[0].chance, .unavailable)
        XCTAssertEqual(model.outlook.figure(model.cards[0]), "12.7%")
        XCTAssertEqual(model.outlook.stateWords(model.cards[0]), Self.missingChance)
    }

    // MARK: Geometry and layout helpers

    func testStripPlanPlacesEveryEndpointAndPrefixOnTheSharedInset() throws {
        let size = CGSize(width: 300, height: 12)
        let inset: CGFloat = 7
        for fraction in [0, 0.000967, 0.045817, 0.1271, 0.5, 1] {
            let plan = try XCTUnwrap(FieldFinishGeometry10868.stripPlan(fraction: fraction, ticks: [], in: size, inset: inset, dotDiameter: 12))
            let x = try XCTUnwrap(FieldFinishGeometry10868.x(of: fraction, width: size.width, inset: inset))
            let dot = try XCTUnwrap(plan.dot)
            XCTAssertEqual(dot.midX, x, accuracy: 1e-9, "\(fraction)")
            XCTAssertEqual(dot.midY, plan.baselineY, accuracy: 1e-9)
            XCTAssertEqual(plan.baselineY, 6, "an endpoint-high strip centres its line")
            XCTAssertGreaterThanOrEqual(dot.minX, 0)
            XCTAssertLessThanOrEqual(dot.maxX, size.width)
            XCTAssertEqual(plan.zeroX, inset)
            XCTAssertEqual(plan.ceilingX, size.width - inset)
            if fraction == 0 {
                XCTAssertNil(FieldBeforeChoicesGeometry10868.prefix(plan, lineWidth: 7))
            } else {
                let prefix = try XCTUnwrap(FieldBeforeChoicesGeometry10868.prefix(plan, lineWidth: 7), "\(fraction)")
                XCTAssertEqual(prefix.minX, plan.zeroX)
                XCTAssertEqual(prefix.maxX, dot.midX, accuracy: 1e-9)
                XCTAssertEqual(prefix.height, 7)
                XCTAssertEqual(prefix.midY, plan.baselineY, accuracy: 1e-9)
            }
        }
        // Equal values share one place; nothing for missing or invalid values or lines.
        XCTAssertEqual(FieldFinishGeometry10868.stripPlan(fraction: 0.0669, ticks: [], in: size, inset: inset, dotDiameter: 12)?.dot,
                       FieldFinishGeometry10868.stripPlan(fraction: 0.0669, ticks: [], in: size, inset: inset, dotDiameter: 12)?.dot)
        for fraction in [nil, -0.01, 1.01, .nan] as [Double?] {
            let plan = try XCTUnwrap(FieldFinishGeometry10868.stripPlan(fraction: fraction, ticks: [], in: size, inset: inset, dotDiameter: 12))
            XCTAssertNil(plan.dot, "\(String(describing: fraction))")
            XCTAssertNil(FieldBeforeChoicesGeometry10868.prefix(plan, lineWidth: 7))
        }
        let placed = try XCTUnwrap(FieldFinishGeometry10868.stripPlan(fraction: 0.5, ticks: [], in: size, inset: inset, dotDiameter: 12))
        for width in [0, -1, .nan, .infinity] as [CGFloat] {
            XCTAssertNil(FieldBeforeChoicesGeometry10868.prefix(placed, lineWidth: width))
        }

        // The owner's tick labels on the same inset: the end labels slide inward to stay whole.
        let labels = FieldExpectationsGeometry10868.axisLabels(
            [0, 0.25, 0.5, 0.75, 1].map { FieldChaseMeasuredTick10868(unit: $0, size: CGSize(width: 26, height: 13)) },
            width: size.width, inset: inset, spacing: 6)
        XCTAssertEqual(labels.compactMap { $0 }.count, 5)
        XCTAssertEqual(labels.first??.minX, 0)
        XCTAssertEqual(labels.last??.maxX, size.width)
    }

    func testColumnPlanGroupsEveryCardOnceInOwnerOrder() throws {
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.columnCandidates(accessibilitySize: false), [2, 1])
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.columnCandidates(accessibilitySize: true), [1])
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.columnMinimum, 260)
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.lines(Array(0..<6), columns: 2), [[0, 1], [2, 3], [4, 5]])
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.lines(Array(0..<7), columns: 2), [[0, 1], [2, 3], [4, 5], [6]])
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.lines(Array(0..<3), columns: 1), [[0], [1], [2]])
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.lines([Int](), columns: 2), [])
        XCTAssertEqual(FieldBeforeChoicesGeometry10868.lines(Array(0..<3), columns: 0), [])

        let all = try Self.retained()
        let wins = Self.wins(all)
        let cards = Self.model(Self.input(all, displayed: wins.map(Self.slot))).cards
        for accessibilitySize in [false, true] {
            for columns in FieldBeforeChoicesGeometry10868.columnCandidates(accessibilitySize: accessibilitySize) {
                let lines = FieldBeforeChoicesGeometry10868.lines(cards, columns: columns)
                XCTAssertEqual(lines.flatMap { $0 }, cards, "every card once, in the owner's order")
                XCTAssertTrue(lines.dropLast().allSatisfy { $0.count == columns })
                XCTAssertTrue(lines.allSatisfy { !$0.isEmpty && $0.count <= columns })
            }
        }
    }

    func testAccessibilityIdentifiersNameTheExactOriginal() {
        XCTAssertEqual(FieldBeforeChoicesAccessibilityID10868.cards, "fieldBeforeChoices10868.cards")
        XCTAssertEqual(FieldBeforeChoicesAccessibilityID10868.outside, "fieldBeforeChoices10868.outside")
        XCTAssertEqual(FieldBeforeChoicesAccessibilityID10868.card("246352440"), "fieldBeforeChoices10868.card.246352440")
    }
}

private struct FieldBeforeChoicesRetainedRecord10868: Equatable {
    let golfer: String
    let label: String
    let selection: String
    let rawID: String
    let probability: Double?
    let opening: Double?
    let lastUpdated: String
    let figure: String
    let ref: FieldChooserOriginalRef10868
}

private let fieldBeforeChoicesRetainedTable = #"""
Rory McIlroy	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352440	246352440	0.1271	0.1271	2026-10-12T23:11:05.501054+00:00	12.7%
Rory McIlroy	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352498	246352498	0.351696	0.351696	2026-10-12T23:11:06.747890+00:00	35.2%
Rory McIlroy	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352556	246352556	0.498592	0.498592	2026-10-12T23:11:07.952964+00:00	49.9%
Rory McIlroy	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352614	246352614	0.665303	0.665303	2026-10-12T23:11:09.073291+00:00	66.5%
Rory McIlroy	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352672	246352672	0.896383	0.896383	2026-10-12T23:11:10.724619+00:00	89.6%
Tommy Fleetwood	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352441	246352441	0.067167	0.067167	2026-10-12T23:11:05.501054+00:00	6.7%
Tommy Fleetwood	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352499	246352499	0.249126	0.249126	2026-10-12T23:11:06.747890+00:00	24.9%
Tommy Fleetwood	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352557	246352557	0.394375	0.394375	2026-10-12T23:11:07.952964+00:00	39.4%
Tommy Fleetwood	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352615	246352615	0.578978	0.578978	2026-10-12T23:11:09.073291+00:00	57.9%
Tommy Fleetwood	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352673	246352673	0.87105	0.87105	2026-10-12T23:11:10.724619+00:00	87.1%
Min Woo Lee	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352442	246352442	0.0669	0.0669	2026-10-12T23:11:05.501054+00:00	6.7%
Min Woo Lee	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352500	246352500	0.23476	0.23476	2026-10-12T23:11:06.747890+00:00	23.5%
Min Woo Lee	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352558	246352558	0.367897	0.367897	2026-10-12T23:11:07.952964+00:00	36.8%
Min Woo Lee	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352616	246352616	0.543127	0.543127	2026-10-12T23:11:09.073291+00:00	54.3%
Min Woo Lee	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352674	246352674	0.850983	0.850983	2026-10-12T23:11:10.724619+00:00	85.1%
Eugenio Chacarra	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904631	245904631	0.0544	0.04145	2026-10-12T23:11:05.501054+00:00	5.4%
Eugenio Chacarra	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904763	245904763	0.213013	0.165032	2026-10-12T23:11:06.747890+00:00	21.3%
Eugenio Chacarra	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904895	245904895	0.349389	0.279395	2026-10-12T23:11:07.952964+00:00	34.9%
Eugenio Chacarra	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905027	245905027	0.533627	0.449587	2026-10-12T23:11:09.073291+00:00	53.4%
Eugenio Chacarra	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905159	245905159	0.852633	0.816833	2026-10-12T23:11:10.724619+00:00	85.3%
Robert MacIntyre	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352443	246352443	0.048083	0.048083	2026-10-12T23:11:05.501054+00:00	4.8%
Robert MacIntyre	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352501	246352501	0.190861	0.190861	2026-10-12T23:11:06.747890+00:00	19.1%
Robert MacIntyre	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352559	246352559	0.318564	0.318564	2026-10-12T23:11:07.952964+00:00	31.9%
Robert MacIntyre	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352617	246352617	0.497194	0.497194	2026-10-12T23:11:09.073291+00:00	49.7%
Robert MacIntyre	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352675	246352675	0.833067	0.833067	2026-10-12T23:11:10.724619+00:00	83.3%
Shane Lowry	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904630	245904630	0.045817	0.051233	2026-10-12T23:11:05.501054+00:00	4.6%
Shane Lowry	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904762	245904762	0.187908	0.190185	2026-10-12T23:11:06.747890+00:00	18.8%
Shane Lowry	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904894	245904894	0.317185	0.311706	2026-10-12T23:11:07.952964+00:00	31.7%
Shane Lowry	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905026	245905026	0.497302	0.479704	2026-10-12T23:11:09.073291+00:00	49.7%
Shane Lowry	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905158	245905158	0.83745	0.829517	2026-10-12T23:11:10.724619+00:00	83.7%
Aaron Rai	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352444	246352444	0.0249	0.0249	2026-10-12T23:11:05.501054+00:00	2.5%
Aaron Rai	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352502	246352502	0.125473	0.125473	2026-10-12T23:11:06.747890+00:00	12.5%
Aaron Rai	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352560	246352560	0.23238	0.23238	2026-10-12T23:11:07.952964+00:00	23.2%
Aaron Rai	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352618	246352618	0.403445	0.403445	2026-10-12T23:11:09.073291+00:00	40.3%
Aaron Rai	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352676	246352676	0.797767	0.797767	2026-10-12T23:11:10.724619+00:00	79.8%
Patrick Reed	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904633	245904633	0.023733	0.028017	2026-10-12T23:11:05.501054+00:00	2.4%
Patrick Reed	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904765	245904765	0.120682	0.126477	2026-10-12T23:11:06.747890+00:00	12.1%
Patrick Reed	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904897	245904897	0.228126	0.230918	2026-10-12T23:11:07.952964+00:00	22.8%
Patrick Reed	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905029	245905029	0.399542	0.396019	2026-10-12T23:11:09.073291+00:00	40%
Patrick Reed	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905161	245905161	0.796867	0.791817	2026-10-12T23:11:10.724619+00:00	79.7%
Jacob Skov Olesen	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904641	245904641	0.022867	0.0191	2026-10-12T23:11:05.501054+00:00	2.3%
Jacob Skov Olesen	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904773	245904773	0.108299	0.092519	2026-10-12T23:11:06.747890+00:00	10.8%
Jacob Skov Olesen	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904905	245904905	0.202846	0.173173	2026-10-12T23:11:07.952964+00:00	20.3%
Jacob Skov Olesen	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905037	245905037	0.360308	0.310331	2026-10-12T23:11:09.073291+00:00	36%
Jacob Skov Olesen	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905169	245905169	0.768517	0.72795	2026-10-12T23:11:10.724619+00:00	76.9%
Angel Ayora	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904643	245904643	0.022733	0.018933	2026-10-12T23:11:05.501054+00:00	2.3%
Angel Ayora	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904775	245904775	0.109575	0.089908	2026-10-12T23:11:06.747890+00:00	11%
Angel Ayora	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904907	245904907	0.202328	0.167647	2026-10-12T23:11:07.952964+00:00	20.2%
Angel Ayora	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905039	245905039	0.354438	0.300218	2026-10-12T23:11:09.073291+00:00	35.4%
Angel Ayora	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905171	245905171	0.757467	0.721133	2026-10-12T23:11:10.724619+00:00	75.7%
Casey Jarvis	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352445	246352445	0.022017	0.022017	2026-10-12T23:11:05.501054+00:00	2.2%
Casey Jarvis	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352503	246352503	0.10605	0.10605	2026-10-12T23:11:06.747890+00:00	10.6%
Casey Jarvis	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352561	246352561	0.198485	0.198485	2026-10-12T23:11:07.952964+00:00	19.8%
Casey Jarvis	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352619	246352619	0.348835	0.348835	2026-10-12T23:11:09.073291+00:00	34.9%
Casey Jarvis	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352677	246352677	0.755683	0.755683	2026-10-12T23:11:10.724619+00:00	75.6%
Tom McKibbin	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904634	245904634	0.0215	0.024517	2026-10-12T23:11:05.501054+00:00	2.2%
Tom McKibbin	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904766	245904766	0.110461	0.114142	2026-10-12T23:11:06.747890+00:00	11%
Tom McKibbin	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904898	245904898	0.210467	0.208236	2026-10-12T23:11:07.952964+00:00	21%
Tom McKibbin	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905030	245905030	0.378313	0.361263	2026-10-12T23:11:09.073291+00:00	37.8%
Tom McKibbin	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905162	245905162	0.784167	0.7698	2026-10-12T23:11:10.724619+00:00	78.4%
Justin Rose	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904639	245904639	0.018783	0.02005	2026-10-12T23:11:05.501054+00:00	1.9%
Justin Rose	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904771	245904771	0.09264	0.087758	2026-10-12T23:11:06.747890+00:00	9.3%
Justin Rose	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904903	245904903	0.174705	0.162257	2026-10-12T23:11:07.952964+00:00	17.5%
Justin Rose	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905035	245905035	0.316737	0.291933	2026-10-12T23:11:09.073291+00:00	31.7%
Justin Rose	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905167	245905167	0.729017	0.7054	2026-10-12T23:11:10.724619+00:00	72.9%
Daniel Hillier	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904635	245904635	0.018567	0.022567	2026-10-12T23:11:05.501054+00:00	1.9%
Daniel Hillier	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904767	245904767	0.095654	0.101502	2026-10-12T23:11:06.747890+00:00	9.6%
Daniel Hillier	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904899	245904899	0.183838	0.186678	2026-10-12T23:11:07.952964+00:00	18.4%
Daniel Hillier	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905031	245905031	0.333481	0.331676	2026-10-12T23:11:09.073291+00:00	33.3%
Daniel Hillier	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905163	245905163	0.74435	0.747017	2026-10-12T23:11:10.724619+00:00	74.4%
Ryan Fox	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352446	246352446	0.0185	0.0185	2026-10-12T23:11:05.501054+00:00	1.9%
Ryan Fox	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352504	246352504	0.096403	0.096403	2026-10-12T23:11:06.747890+00:00	9.6%
Ryan Fox	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352562	246352562	0.185214	0.185214	2026-10-12T23:11:07.952964+00:00	18.5%
Ryan Fox	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352620	246352620	0.339236	0.339236	2026-10-12T23:11:09.073291+00:00	33.9%
Ryan Fox	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352678	246352678	0.753833	0.753833	2026-10-12T23:11:10.724619+00:00	75.4%
Oliver Lindell	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904645	245904645	0.018317	0.01785	2026-10-12T23:11:05.501054+00:00	1.8%
Oliver Lindell	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904777	245904777	0.09444	0.087133	2026-10-12T23:11:06.747890+00:00	9.4%
Oliver Lindell	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904909	245904909	0.18507	0.165196	2026-10-12T23:11:07.952964+00:00	18.5%
Oliver Lindell	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905041	245905041	0.339455	0.302347	2026-10-12T23:11:09.073291+00:00	33.9%
Oliver Lindell	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905173	245905173	0.756483	0.735367	2026-10-12T23:11:10.724619+00:00	75.6%
Ewen Ferguson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904644	245904644	0.015667	0.018483	2026-10-12T23:11:05.501054+00:00	1.6%
Ewen Ferguson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904776	245904776	0.086561	0.089063	2026-10-12T23:11:06.747890+00:00	8.7%
Ewen Ferguson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904908	245904908	0.171444	0.167641	2026-10-12T23:11:07.952964+00:00	17.1%
Ewen Ferguson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905040	245905040	0.320031	0.305089	2026-10-12T23:11:09.073291+00:00	32%
Ewen Ferguson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905172	245905172	0.742683	0.724667	2026-10-12T23:11:10.724619+00:00	74.3%
Antoine Rozner	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904649	245904649	0.015533	0.013933	2026-10-12T23:11:05.501054+00:00	1.6%
Antoine Rozner	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904781	245904781	0.083854	0.06924	2026-10-12T23:11:06.747890+00:00	8.4%
Antoine Rozner	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904913	245904913	0.166477	0.136073	2026-10-12T23:11:07.952964+00:00	16.6%
Antoine Rozner	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905045	245905045	0.310612	0.259914	2026-10-12T23:11:09.073291+00:00	31.1%
Antoine Rozner	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905177	245905177	0.7365	0.695033	2026-10-12T23:11:10.724619+00:00	73.7%
Thomas Detry	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904640	245904640	0.01445	0.0199	2026-10-12T23:11:05.501054+00:00	1.4%
Thomas Detry	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904772	245904772	0.076624	0.093458	2026-10-12T23:11:06.747890+00:00	7.7%
Thomas Detry	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904904	245904904	0.155081	0.176453	2026-10-12T23:11:07.952964+00:00	15.5%
Thomas Detry	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905036	245905036	0.298551	0.315686	2026-10-12T23:11:09.073291+00:00	29.9%
Thomas Detry	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905168	245905168	0.72475	0.7311	2026-10-12T23:11:10.724619+00:00	72.5%
Bernd Wiesberger	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904667	245904667	0.013417	0.0074	2026-10-12T23:11:05.501054+00:00	1.3%
Bernd Wiesberger	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904799	245904799	0.073145	0.044859	2026-10-12T23:11:06.747890+00:00	7.3%
Bernd Wiesberger	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904931	245904931	0.150714	0.094456	2026-10-12T23:11:07.952964+00:00	15.1%
Bernd Wiesberger	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905063	245905063	0.293956	0.199618	2026-10-12T23:11:09.073291+00:00	29.4%
Bernd Wiesberger	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905195	245905195	0.725767	0.649067	2026-10-12T23:11:10.724619+00:00	72.6%
Martin Couvra	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904673	245904673	0.01115	0.006383	2026-10-12T23:11:05.501054+00:00	1.1%
Martin Couvra	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904805	245904805	0.063377	0.036799	2026-10-12T23:11:06.747890+00:00	6.3%
Martin Couvra	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904937	245904937	0.1313	0.079674	2026-10-12T23:11:07.952964+00:00	13.1%
Martin Couvra	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905069	245905069	0.257306	0.170268	2026-10-12T23:11:09.073291+00:00	25.7%
Martin Couvra	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905201	245905201	0.69605	0.601467	2026-10-12T23:11:10.724619+00:00	69.6%
Joakim Lagergren	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904654	245904654	0.0106	0.01015	2026-10-12T23:11:05.501054+00:00	1.1%
Joakim Lagergren	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904786	245904786	0.059633	0.052113	2026-10-12T23:11:06.747890+00:00	6%
Joakim Lagergren	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904918	245904918	0.122221	0.104873	2026-10-12T23:11:07.952964+00:00	12.2%
Joakim Lagergren	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905050	245905050	0.242253	0.208616	2026-10-12T23:11:09.073291+00:00	24.2%
Joakim Lagergren	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905182	245905182	0.673417	0.626367	2026-10-12T23:11:10.724619+00:00	67.3%
Byeong Hun An	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352447	246352447	0.010533	0.010533	2026-10-12T23:11:05.501054+00:00	1.1%
Byeong Hun An	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352505	246352505	0.061933	0.061933	2026-10-12T23:11:06.747890+00:00	6.2%
Byeong Hun An	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352563	246352563	0.126827	0.126827	2026-10-12T23:11:07.952964+00:00	12.7%
Byeong Hun An	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352621	246352621	0.2497	0.2497	2026-10-12T23:11:09.073291+00:00	25%
Byeong Hun An	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352679	246352679	0.680767	0.680767	2026-10-12T23:11:10.724619+00:00	68.1%
Niklas Norgaard	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904655	245904655	0.010483	0.0101	2026-10-12T23:11:05.501054+00:00	1%
Niklas Norgaard	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904787	245904787	0.059822	0.054837	2026-10-12T23:11:06.747890+00:00	6%
Niklas Norgaard	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904919	245904919	0.123471	0.110336	2026-10-12T23:11:07.952964+00:00	12.3%
Niklas Norgaard	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905051	245905051	0.246567	0.216599	2026-10-12T23:11:09.073291+00:00	24.7%
Niklas Norgaard	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905183	245905183	0.67845	0.654567	2026-10-12T23:11:10.724619+00:00	67.8%
Francesco Laporta	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904659	245904659	0.010233	0.009	2026-10-12T23:11:05.501054+00:00	1%
Francesco Laporta	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904791	245904791	0.059516	0.046556	2026-10-12T23:11:06.747890+00:00	6%
Francesco Laporta	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904923	245904923	0.12595	0.098999	2026-10-12T23:11:07.952964+00:00	12.6%
Francesco Laporta	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905055	245905055	0.252359	0.201704	2026-10-12T23:11:09.073291+00:00	25.2%
Francesco Laporta	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905187	245905187	0.689217	0.642517	2026-10-12T23:11:10.724619+00:00	68.9%
Jayden Schaper	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904656	245904656	0.0088	0.009933	2026-10-12T23:11:05.501054+00:00	0.9%
Jayden Schaper	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904788	245904788	0.055263	0.054303	2026-10-12T23:11:06.747890+00:00	5.5%
Jayden Schaper	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904920	245904920	0.118259	0.114146	2026-10-12T23:11:07.952964+00:00	11.8%
Jayden Schaper	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905052	245905052	0.242755	0.228377	2026-10-12T23:11:09.073291+00:00	24.3%
Jayden Schaper	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905184	245905184	0.6869	0.665083	2026-10-12T23:11:10.724619+00:00	68.7%
Joost Luiten	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904666	245904666	0.008383	0.007667	2026-10-12T23:11:05.501054+00:00	0.8%
Joost Luiten	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904798	245904798	0.050411	0.04266	2026-10-12T23:11:06.747890+00:00	5%
Joost Luiten	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904930	245904930	0.109637	0.089612	2026-10-12T23:11:07.952964+00:00	11%
Joost Luiten	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905062	245905062	0.227479	0.185792	2026-10-12T23:11:09.073291+00:00	22.7%
Joost Luiten	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905194	245905194	0.671333	0.631367	2026-10-12T23:11:10.724619+00:00	67.1%
Nathan Kimsey	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904670	245904670	0.008317	0.0067	2026-10-12T23:11:05.501054+00:00	0.8%
Nathan Kimsey	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904802	245904802	0.049251	0.039138	2026-10-12T23:11:06.747890+00:00	4.9%
Nathan Kimsey	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904934	245904934	0.106656	0.083394	2026-10-12T23:11:07.952964+00:00	10.7%
Nathan Kimsey	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905066	245905066	0.220278	0.176158	2026-10-12T23:11:09.073291+00:00	22%
Nathan Kimsey	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905198	245905198	0.659283	0.603817	2026-10-12T23:11:10.724619+00:00	65.9%
Tom Vaillant	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904679	245904679	0.00805	0.006	2026-10-12T23:11:05.501054+00:00	0.8%
Tom Vaillant	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904811	245904811	0.048283	0.036491	2026-10-12T23:11:06.747890+00:00	4.8%
Tom Vaillant	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904943	245904943	0.10543	0.077658	2026-10-12T23:11:07.952964+00:00	10.5%
Tom Vaillant	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905075	245905075	0.217733	0.166384	2026-10-12T23:11:09.073291+00:00	21.8%
Tom Vaillant	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905207	245905207	0.656133	0.5924	2026-10-12T23:11:10.724619+00:00	65.6%
Adrian Meronk	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904653	245904653	0.007133	0.01045	2026-10-12T23:11:05.501054+00:00	0.7%
Adrian Meronk	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904785	245904785	0.045585	0.055394	2026-10-12T23:11:06.747890+00:00	4.6%
Adrian Meronk	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904917	245904917	0.097358	0.112865	2026-10-12T23:11:07.952964+00:00	9.7%
Adrian Meronk	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905049	245905049	0.208042	0.2251	2026-10-12T23:11:09.073291+00:00	20.8%
Adrian Meronk	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905181	245905181	0.64735	0.665683	2026-10-12T23:11:10.724619+00:00	64.7%
Laurie Canter	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352448	246352448	0.006983	0.006983	2026-10-12T23:11:05.501054+00:00	0.7%
Laurie Canter	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352506	246352506	0.045368	0.045368	2026-10-12T23:11:06.747890+00:00	4.5%
Laurie Canter	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352564	246352564	0.098055	0.098055	2026-10-12T23:11:07.952964+00:00	9.8%
Laurie Canter	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352622	246352622	0.207328	0.207328	2026-10-12T23:11:09.073291+00:00	20.7%
Laurie Canter	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352680	246352680	0.649417	0.649417	2026-10-12T23:11:10.724619+00:00	64.9%
JC Ritchie	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904676	245904676	0.006817	0.006167	2026-10-12T23:11:05.501054+00:00	0.7%
JC Ritchie	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904808	245904808	0.042643	0.036672	2026-10-12T23:11:06.747890+00:00	4.3%
JC Ritchie	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904940	245904940	0.091979	0.07866	2026-10-12T23:11:07.952964+00:00	9.2%
JC Ritchie	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905072	245905072	0.195218	0.170432	2026-10-12T23:11:09.073291+00:00	19.5%
JC Ritchie	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905204	245905204	0.631933	0.595317	2026-10-12T23:11:10.724619+00:00	63.2%
Angel Hidalgo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904674	245904674	0.006683	0.006317	2026-10-12T23:11:05.501054+00:00	0.7%
Angel Hidalgo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904806	245904806	0.043224	0.037014	2026-10-12T23:11:06.747890+00:00	4.3%
Angel Hidalgo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904938	245904938	0.095744	0.079488	2026-10-12T23:11:07.952964+00:00	9.6%
Angel Hidalgo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905070	245905070	0.203442	0.168417	2026-10-12T23:11:09.073291+00:00	20.3%
Angel Hidalgo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905202	245905202	0.64315	0.596517	2026-10-12T23:11:10.724619+00:00	64.3%
Andy Sullivan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904668	245904668	0.006417	0.007117	2026-10-12T23:11:05.501054+00:00	0.6%
Andy Sullivan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904800	245904800	0.041048	0.038782	2026-10-12T23:11:06.747890+00:00	4.1%
Andy Sullivan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904932	245904932	0.091148	0.083705	2026-10-12T23:11:07.952964+00:00	9.1%
Andy Sullivan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905064	245905064	0.197509	0.177281	2026-10-12T23:11:09.073291+00:00	19.8%
Andy Sullivan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905196	245905196	0.640367	0.610083	2026-10-12T23:11:10.724619+00:00	64%
Ugo Coussaud	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904675	245904675	0.006133	0.00625	2026-10-12T23:11:05.501054+00:00	0.6%
Ugo Coussaud	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904807	245904807	0.041074	0.038215	2026-10-12T23:11:06.747890+00:00	4.1%
Ugo Coussaud	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904939	245904939	0.091471	0.084625	2026-10-12T23:11:07.952964+00:00	9.1%
Ugo Coussaud	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905071	245905071	0.193465	0.176221	2026-10-12T23:11:09.073291+00:00	19.3%
Ugo Coussaud	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905203	245905203	0.6315	0.615983	2026-10-12T23:11:10.724619+00:00	63.2%
Romain Langasque	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904695	245904695	0.005767	0.003917	2026-10-12T23:11:05.501054+00:00	0.6%
Romain Langasque	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904827	245904827	0.037682	0.025568	2026-10-12T23:11:06.747890+00:00	3.8%
Romain Langasque	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904959	245904959	0.085318	0.060362	2026-10-12T23:11:07.952964+00:00	8.5%
Romain Langasque	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905091	245905091	0.188263	0.136801	2026-10-12T23:11:09.073291+00:00	18.8%
Romain Langasque	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905223	245905223	0.633517	0.5623	2026-10-12T23:11:10.724619+00:00	63.4%
Guido Migliozzi	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904658	245904658	0.005483	0.009383	2026-10-12T23:11:05.501054+00:00	0.5%
Guido Migliozzi	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904790	245904790	0.034661	0.05377	2026-10-12T23:11:06.747890+00:00	3.5%
Guido Migliozzi	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904922	245904922	0.079052	0.111158	2026-10-12T23:11:07.952964+00:00	7.9%
Guido Migliozzi	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905054	245905054	0.176065	0.222757	2026-10-12T23:11:09.073291+00:00	17.6%
Guido Migliozzi	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905186	245905186	0.61635	0.660167	2026-10-12T23:11:10.724619+00:00	61.6%
Julien Guerrier	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904687	245904687	0.00545	0.004733	2026-10-12T23:11:05.501054+00:00	0.5%
Julien Guerrier	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904819	245904819	0.035372	0.030512	2026-10-12T23:11:06.747890+00:00	3.5%
Julien Guerrier	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904951	245904951	0.07976	0.069593	2026-10-12T23:11:07.952964+00:00	8%
Julien Guerrier	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905083	245905083	0.174217	0.154835	2026-10-12T23:11:09.073291+00:00	17.4%
Julien Guerrier	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905215	245905215	0.6143	0.579433	2026-10-12T23:11:10.724619+00:00	61.4%
Joel Girrbach	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904698	245904698	0.00525	0.003567	2026-10-12T23:11:05.501054+00:00	0.5%
Joel Girrbach	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904830	245904830	0.034085	0.02383	2026-10-12T23:11:06.747890+00:00	3.4%
Joel Girrbach	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904962	245904962	0.078699	0.054898	2026-10-12T23:11:07.952964+00:00	7.9%
Joel Girrbach	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905094	245905094	0.179008	0.129457	2026-10-12T23:11:09.073291+00:00	17.9%
Joel Girrbach	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905226	245905226	0.61815	0.5501	2026-10-12T23:11:10.724619+00:00	61.8%
Freddy Schott	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904680	245904680	0.0052	0.006	2026-10-12T23:11:05.501054+00:00	0.5%
Freddy Schott	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904812	245904812	0.032621	0.034674	2026-10-12T23:11:06.747890+00:00	3.3%
Freddy Schott	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904944	245904944	0.072798	0.072777	2026-10-12T23:11:07.952964+00:00	7.3%
Freddy Schott	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905076	245905076	0.157959	0.150543	2026-10-12T23:11:09.073291+00:00	15.8%
Freddy Schott	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905208	245905208	0.578283	0.5596	2026-10-12T23:11:10.724619+00:00	57.8%
Davis Bryant	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904669	245904669	0.005167	0.006817	2026-10-12T23:11:05.501054+00:00	0.5%
Davis Bryant	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904801	245904801	0.036724	0.043038	2026-10-12T23:11:06.747890+00:00	3.7%
Davis Bryant	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904933	245904933	0.085053	0.092463	2026-10-12T23:11:07.952964+00:00	8.5%
Davis Bryant	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905065	245905065	0.191317	0.196304	2026-10-12T23:11:09.073291+00:00	19.1%
Davis Bryant	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905197	245905197	0.63745	0.6463	2026-10-12T23:11:10.724619+00:00	63.7%
Gregorio De Leo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904681	245904681	0.00515	0.00575	2026-10-12T23:11:05.501054+00:00	0.5%
Gregorio De Leo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904813	245904813	0.033124	0.035011	2026-10-12T23:11:06.747890+00:00	3.3%
Gregorio De Leo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904945	245904945	0.075336	0.077252	2026-10-12T23:11:07.952964+00:00	7.5%
Gregorio De Leo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905077	245905077	0.167665	0.16552	2026-10-12T23:11:09.073291+00:00	16.8%
Gregorio De Leo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905209	245905209	0.606017	0.607833	2026-10-12T23:11:10.724619+00:00	60.6%
Manuel Elvira	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904690	245904690	0.004967	0.0045	2026-10-12T23:11:05.501054+00:00	0.5%
Manuel Elvira	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904822	245904822	0.034986	0.029297	2026-10-12T23:11:06.747890+00:00	3.5%
Manuel Elvira	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904954	245904954	0.0784	0.064583	2026-10-12T23:11:07.952964+00:00	7.8%
Manuel Elvira	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905086	245905086	0.173839	0.142435	2026-10-12T23:11:09.073291+00:00	17.4%
Manuel Elvira	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905218	245905218	0.6149	0.576917	2026-10-12T23:11:10.724619+00:00	61.5%
Dan Bradbury	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904682	245904682	0.004717	0.005467	2026-10-12T23:11:05.501054+00:00	0.5%
Dan Bradbury	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904814	245904814	0.030762	0.032815	2026-10-12T23:11:06.747890+00:00	3.1%
Dan Bradbury	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904946	245904946	0.07201	0.070452	2026-10-12T23:11:07.952964+00:00	7.2%
Dan Bradbury	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905078	245905078	0.160747	0.147684	2026-10-12T23:11:09.073291+00:00	16.1%
Dan Bradbury	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905210	245905210	0.593217	0.567467	2026-10-12T23:11:10.724619+00:00	59.3%
David Ravetto	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904678	245904678	0.004567	0.006067	2026-10-12T23:11:05.501054+00:00	0.5%
David Ravetto	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904810	245904810	0.030315	0.03734	2026-10-12T23:11:06.747890+00:00	3%
David Ravetto	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904942	245904942	0.06915	0.08064	2026-10-12T23:11:07.952964+00:00	6.9%
David Ravetto	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905074	245905074	0.15718	0.172769	2026-10-12T23:11:09.073291+00:00	15.7%
David Ravetto	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905206	245905206	0.591433	0.614767	2026-10-12T23:11:10.724619+00:00	59.1%
Ignacio Elvira Mijares	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904693	245904693	0.00435	0.0042	2026-10-12T23:11:05.501054+00:00	0.4%
Ignacio Elvira Mijares	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904825	245904825	0.033871	0.028417	2026-10-12T23:11:06.747890+00:00	3.4%
Ignacio Elvira Mijares	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904957	245904957	0.077069	0.065125	2026-10-12T23:11:07.952964+00:00	7.7%
Ignacio Elvira Mijares	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905089	245905089	0.172742	0.144765	2026-10-12T23:11:09.073291+00:00	17.3%
Ignacio Elvira Mijares	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905221	245905221	0.618117	0.572033	2026-10-12T23:11:10.724619+00:00	61.8%
Todd Clements	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904694	245904694	0.00425	0.004167	2026-10-12T23:11:05.501054+00:00	0.4%
Todd Clements	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904826	245904826	0.029684	0.028008	2026-10-12T23:11:06.747890+00:00	3%
Todd Clements	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904958	245904958	0.067421	0.063191	2026-10-12T23:11:07.952964+00:00	6.7%
Todd Clements	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905090	245905090	0.154699	0.141554	2026-10-12T23:11:09.073291+00:00	15.5%
Todd Clements	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905222	245905222	0.593383	0.56785	2026-10-12T23:11:10.724619+00:00	59.3%
Yuto Katsuragawa	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904700	245904700	0.0042	0.0035	2026-10-12T23:11:05.501054+00:00	0.4%
Yuto Katsuragawa	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904832	245904832	0.027476	0.021857	2026-10-12T23:11:06.747890+00:00	2.7%
Yuto Katsuragawa	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904964	245904964	0.064482	0.050818	2026-10-12T23:11:07.952964+00:00	6.4%
Yuto Katsuragawa	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905096	245905096	0.14983	0.119611	2026-10-12T23:11:09.073291+00:00	15%
Yuto Katsuragawa	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905228	245905228	0.58035	0.526217	2026-10-12T23:11:10.724619+00:00	58%
David Law	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904686	245904686	0.004167	0.005017	2026-10-12T23:11:05.501054+00:00	0.4%
David Law	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904818	245904818	0.02932	0.034389	2026-10-12T23:11:06.747890+00:00	2.9%
David Law	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904950	245904950	0.066346	0.076111	2026-10-12T23:11:07.952964+00:00	6.6%
David Law	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905082	245905082	0.152194	0.16431	2026-10-12T23:11:09.073291+00:00	15.2%
David Law	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905214	245905214	0.589167	0.60525	2026-10-12T23:11:10.724619+00:00	58.9%
Maximilian Steinlechner	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904688	245904688	0.004133	0.004717	2026-10-12T23:11:05.501054+00:00	0.4%
Maximilian Steinlechner	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904820	245904820	0.02974	0.028982	2026-10-12T23:11:06.747890+00:00	3%
Maximilian Steinlechner	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904952	245904952	0.067853	0.063289	2026-10-12T23:11:07.952964+00:00	6.8%
Maximilian Steinlechner	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905084	245905084	0.155395	0.140889	2026-10-12T23:11:09.073291+00:00	15.5%
Maximilian Steinlechner	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905216	245905216	0.5889	0.56935	2026-10-12T23:11:10.724619+00:00	58.9%
Marcus Armitage	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904683	245904683	0.004083	0.005367	2026-10-12T23:11:05.501054+00:00	0.4%
Marcus Armitage	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904815	245904815	0.02811	0.035889	2026-10-12T23:11:06.747890+00:00	2.8%
Marcus Armitage	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904947	245904947	0.065999	0.077866	2026-10-12T23:11:07.952964+00:00	6.6%
Marcus Armitage	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905079	245905079	0.152824	0.169932	2026-10-12T23:11:09.073291+00:00	15.3%
Marcus Armitage	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905211	245905211	0.591517	0.603567	2026-10-12T23:11:10.724619+00:00	59.2%
Darius Van Driel	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904713	245904713	0.00385	0.002483	2026-10-12T23:11:05.501054+00:00	0.4%
Darius Van Driel	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904845	245904845	0.028768	0.017355	2026-10-12T23:11:06.747890+00:00	2.9%
Darius Van Driel	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904977	245904977	0.068758	0.042375	2026-10-12T23:11:07.952964+00:00	6.9%
Darius Van Driel	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905109	245905109	0.156971	0.103984	2026-10-12T23:11:09.073291+00:00	15.7%
Darius Van Driel	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905241	245905241	0.595383	0.514	2026-10-12T23:11:10.724619+00:00	59.5%
Frederic LaCroix	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904697	245904697	0.003733	0.0038	2026-10-12T23:11:05.501054+00:00	0.4%
Frederic LaCroix	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904829	245904829	0.027684	0.024143	2026-10-12T23:11:06.747890+00:00	2.8%
Frederic LaCroix	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904961	245904961	0.065324	0.055611	2026-10-12T23:11:07.952964+00:00	6.5%
Frederic LaCroix	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905093	245905093	0.15111	0.129327	2026-10-12T23:11:09.073291+00:00	15.1%
Frederic LaCroix	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905225	245905225	0.58355	0.560483	2026-10-12T23:11:10.724619+00:00	58.4%
Oihan Guillamoundeguy	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904691	245904691	0.003717	0.0045	2026-10-12T23:11:05.501054+00:00	0.4%
Oihan Guillamoundeguy	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904823	245904823	0.026176	0.028072	2026-10-12T23:11:06.747890+00:00	2.6%
Oihan Guillamoundeguy	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904955	245904955	0.061618	0.062525	2026-10-12T23:11:07.952964+00:00	6.2%
Oihan Guillamoundeguy	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905087	245905087	0.141802	0.137618	2026-10-12T23:11:09.073291+00:00	14.2%
Oihan Guillamoundeguy	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905219	245905219	0.56925	0.561983	2026-10-12T23:11:10.724619+00:00	56.9%
Andreas Halvorsen	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352449	246352449	0.0037	0.0037	2026-10-12T23:11:05.501054+00:00	0.4%
Andreas Halvorsen	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352507	246352507	0.028037	0.028037	2026-10-12T23:11:06.747890+00:00	2.8%
Andreas Halvorsen	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352565	246352565	0.0633	0.0633	2026-10-12T23:11:07.952964+00:00	6.3%
Andreas Halvorsen	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352623	246352623	0.142762	0.142762	2026-10-12T23:11:09.073291+00:00	14.3%
Andreas Halvorsen	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352681	246352681	0.5659	0.5659	2026-10-12T23:11:10.724619+00:00	56.6%
Matteo Manassero	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904701	245904701	0.003667	0.003483	2026-10-12T23:11:05.501054+00:00	0.4%
Matteo Manassero	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904833	245904833	0.027616	0.024407	2026-10-12T23:11:06.747890+00:00	2.8%
Matteo Manassero	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904965	245904965	0.065174	0.057222	2026-10-12T23:11:07.952964+00:00	6.5%
Matteo Manassero	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905097	245905097	0.153962	0.13498	2026-10-12T23:11:09.073291+00:00	15.4%
Matteo Manassero	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905229	245905229	0.602017	0.568267	2026-10-12T23:11:10.724619+00:00	60.2%
Thriston Lawrence	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904716	245904716	0.003283	0.00235	2026-10-12T23:11:05.501054+00:00	0.3%
Thriston Lawrence	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904848	245904848	0.022301	0.016265	2026-10-12T23:11:06.747890+00:00	2.2%
Thriston Lawrence	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904980	245904980	0.05278	0.038221	2026-10-12T23:11:07.952964+00:00	5.3%
Thriston Lawrence	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905112	245905112	0.126215	0.09373	2026-10-12T23:11:09.073291+00:00	12.6%
Thriston Lawrence	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905244	245905244	0.548517	0.502417	2026-10-12T23:11:10.724619+00:00	54.9%
Johannes Veerman	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904706	245904706	0.003283	0.002883	2026-10-12T23:11:05.501054+00:00	0.3%
Johannes Veerman	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904838	245904838	0.021666	0.019983	2026-10-12T23:11:06.747890+00:00	2.2%
Johannes Veerman	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904970	245904970	0.05031	0.046957	2026-10-12T23:11:07.952964+00:00	5%
Johannes Veerman	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905102	245905102	0.118544	0.109025	2026-10-12T23:11:09.073291+00:00	11.9%
Johannes Veerman	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905234	245905234	0.535883	0.5097	2026-10-12T23:11:10.724619+00:00	53.6%
Adrian Otaegui	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904704	245904704	0.003217	0.00295	2026-10-12T23:11:05.501054+00:00	0.3%
Adrian Otaegui	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904836	245904836	0.027726	0.019095	2026-10-12T23:11:06.747890+00:00	2.8%
Adrian Otaegui	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904968	245904968	0.065284	0.045546	2026-10-12T23:11:07.952964+00:00	6.5%
Adrian Otaegui	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905100	245905100	0.155329	0.10729	2026-10-12T23:11:09.073291+00:00	15.5%
Adrian Otaegui	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905232	245905232	0.599117	0.513833	2026-10-12T23:11:10.724619+00:00	59.9%
Filippo Celli	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904692	245904692	0.003117	0.004317	2026-10-12T23:11:05.501054+00:00	0.3%
Filippo Celli	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904824	245904824	0.023359	0.025659	2026-10-12T23:11:06.747890+00:00	2.3%
Filippo Celli	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904956	245904956	0.056206	0.058168	2026-10-12T23:11:07.952964+00:00	5.6%
Filippo Celli	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905088	245905088	0.133819	0.131169	2026-10-12T23:11:09.073291+00:00	13.4%
Filippo Celli	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905220	245905220	0.555967	0.547683	2026-10-12T23:11:10.724619+00:00	55.6%
Rocco Repetto Taylor	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352450	246352450	0.003017	0.003017	2026-10-12T23:11:05.501054+00:00	0.3%
Rocco Repetto Taylor	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352508	246352508	0.018782	0.018782	2026-10-12T23:11:06.747890+00:00	1.9%
Rocco Repetto Taylor	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352566	246352566	0.044828	0.044828	2026-10-12T23:11:07.952964+00:00	4.5%
Rocco Repetto Taylor	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352624	246352624	0.104544	0.104544	2026-10-12T23:11:09.073291+00:00	10.5%
Rocco Repetto Taylor	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352682	246352682	0.4991	0.4991	2026-10-12T23:11:10.724619+00:00	49.9%
Niklas Lemke	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904732	245904732	0.003	0.001217	2026-10-12T23:11:05.501054+00:00	0.3%
Niklas Lemke	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904864	245904864	0.019745	0.010222	2026-10-12T23:11:06.747890+00:00	2%
Niklas Lemke	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904996	245904996	0.047953	0.025972	2026-10-12T23:11:07.952964+00:00	4.8%
Niklas Lemke	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905128	245905128	0.117085	0.06541	2026-10-12T23:11:09.073291+00:00	11.7%
Niklas Lemke	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905260	245905260	0.534583	0.422433	2026-10-12T23:11:10.724619+00:00	53.5%
Felix Mory	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352451	246352451	0.002817	0.002817	2026-10-12T23:11:05.501054+00:00	0.3%
Felix Mory	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352509	246352509	0.0175	0.0175	2026-10-12T23:11:06.747890+00:00	1.8%
Felix Mory	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352567	246352567	0.041294	0.041294	2026-10-12T23:11:07.952964+00:00	4.1%
Felix Mory	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352625	246352625	0.101867	0.101867	2026-10-12T23:11:09.073291+00:00	10.2%
Felix Mory	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352683	246352683	0.505583	0.505583	2026-10-12T23:11:10.724619+00:00	50.6%
Kota Kaneko	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352452	246352452	0.002767	0.002767	2026-10-12T23:11:05.501054+00:00	0.3%
Kota Kaneko	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352510	246352510	0.023007	0.023007	2026-10-12T23:11:06.747890+00:00	2.3%
Kota Kaneko	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352568	246352568	0.057126	0.057126	2026-10-12T23:11:07.952964+00:00	5.7%
Kota Kaneko	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352626	246352626	0.139049	0.139049	2026-10-12T23:11:09.073291+00:00	13.9%
Kota Kaneko	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352684	246352684	0.57955	0.57955	2026-10-12T23:11:10.724619+00:00	58%
Sean Crocker	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904719	245904719	0.002683	0.002167	2026-10-12T23:11:05.501054+00:00	0.3%
Sean Crocker	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904851	245904851	0.021835	0.01597	2026-10-12T23:11:06.747890+00:00	2.2%
Sean Crocker	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904983	245904983	0.053001	0.037562	2026-10-12T23:11:07.952964+00:00	5.3%
Sean Crocker	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905115	245905115	0.130352	0.089801	2026-10-12T23:11:09.073291+00:00	13%
Sean Crocker	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905247	245905247	0.555317	0.4848	2026-10-12T23:11:10.724619+00:00	55.5%
Sebastian Soderberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904708	245904708	0.002617	0.0028	2026-10-12T23:11:05.501054+00:00	0.3%
Sebastian Soderberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904840	245904840	0.019013	0.020418	2026-10-12T23:11:06.747890+00:00	1.9%
Sebastian Soderberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904972	245904972	0.046127	0.048136	2026-10-12T23:11:07.952964+00:00	4.6%
Sebastian Soderberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905104	245905104	0.112257	0.110804	2026-10-12T23:11:09.073291+00:00	11.2%
Sebastian Soderberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905236	245905236	0.5237	0.52425	2026-10-12T23:11:10.724619+00:00	52.4%
Nicolai Von Dellingshausen	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904718	245904718	0.002517	0.0022	2026-10-12T23:11:05.501054+00:00	0.3%
Nicolai Von Dellingshausen	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904850	245904850	0.019093	0.016477	2026-10-12T23:11:06.747890+00:00	1.9%
Nicolai Von Dellingshausen	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904982	245904982	0.045335	0.039934	2026-10-12T23:11:07.952964+00:00	4.5%
Nicolai Von Dellingshausen	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905114	245905114	0.113436	0.094757	2026-10-12T23:11:09.073291+00:00	11.3%
Nicolai Von Dellingshausen	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905246	245905246	0.527633	0.491667	2026-10-12T23:11:10.724619+00:00	52.8%
Marcus Kinhult	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352453	246352453	0.0024	0.0024	2026-10-12T23:11:05.501054+00:00	0.2%
Marcus Kinhult	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352511	246352511	0.018876	0.018876	2026-10-12T23:11:06.747890+00:00	1.9%
Marcus Kinhult	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352569	246352569	0.045944	0.045944	2026-10-12T23:11:07.952964+00:00	4.6%
Marcus Kinhult	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352627	246352627	0.113828	0.113828	2026-10-12T23:11:09.073291+00:00	11.4%
Marcus Kinhult	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352685	246352685	0.532183	0.532183	2026-10-12T23:11:10.724619+00:00	53.2%
Daniel Rodrigues	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904709	245904709	0.002383	0.002733	2026-10-12T23:11:05.501054+00:00	0.2%
Daniel Rodrigues	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904841	245904841	0.013958	0.017295	2026-10-12T23:11:06.747890+00:00	1.4%
Daniel Rodrigues	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904973	245904973	0.035434	0.040719	2026-10-12T23:11:07.952964+00:00	3.5%
Daniel Rodrigues	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905105	245905105	0.090609	0.097818	2026-10-12T23:11:09.073291+00:00	9.1%
Daniel Rodrigues	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905237	245905237	0.489367	0.502033	2026-10-12T23:11:10.724619+00:00	48.9%
Brandon Robinson Thompson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904710	245904710	0.002167	0.002683	2026-10-12T23:11:05.501054+00:00	0.2%
Brandon Robinson Thompson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904842	245904842	0.018498	0.017908	2026-10-12T23:11:06.747890+00:00	1.8%
Brandon Robinson Thompson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904974	245904974	0.04447	0.042024	2026-10-12T23:11:07.952964+00:00	4.4%
Brandon Robinson Thompson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905106	245905106	0.112047	0.098266	2026-10-12T23:11:09.073291+00:00	11.2%
Brandon Robinson Thompson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905238	245905238	0.529333	0.496167	2026-10-12T23:11:10.724619+00:00	52.9%
Jorge Campillo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904717	245904717	0.001983	0.002267	2026-10-12T23:11:05.501054+00:00	0.2%
Jorge Campillo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904849	245904849	0.017555	0.017137	2026-10-12T23:11:06.747890+00:00	1.8%
Jorge Campillo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904981	245904981	0.044821	0.042012	2026-10-12T23:11:07.952964+00:00	4.5%
Jorge Campillo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905113	245905113	0.113016	0.103475	2026-10-12T23:11:09.073291+00:00	11.3%
Jorge Campillo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905245	245905245	0.537633	0.507833	2026-10-12T23:11:10.724619+00:00	53.8%
Anirban Lahiri	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352454	246352454	0.001933	0.001933	2026-10-12T23:11:05.501054+00:00	0.2%
Anirban Lahiri	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352512	246352512	0.014551	0.014551	2026-10-12T23:11:06.747890+00:00	1.5%
Anirban Lahiri	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352570	246352570	0.03544	0.03544	2026-10-12T23:11:07.952964+00:00	3.5%
Anirban Lahiri	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352628	246352628	0.089762	0.089762	2026-10-12T23:11:09.073291+00:00	9%
Anirban Lahiri	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352686	246352686	0.475333	0.475333	2026-10-12T23:11:10.724619+00:00	47.5%
Eddie Pepperell	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904712	245904712	0.001933	0.002567	2026-10-12T23:11:05.501054+00:00	0.2%
Eddie Pepperell	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904844	245904844	0.01725	0.019121	2026-10-12T23:11:06.747890+00:00	1.7%
Eddie Pepperell	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904976	245904976	0.043049	0.04524	2026-10-12T23:11:07.952964+00:00	4.3%
Eddie Pepperell	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905108	245905108	0.108751	0.110302	2026-10-12T23:11:09.073291+00:00	10.9%
Eddie Pepperell	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905240	245905240	0.534283	0.533017	2026-10-12T23:11:10.724619+00:00	53.4%
Quim Vidal	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904727	245904727	0.001917	0.001483	2026-10-12T23:11:05.501054+00:00	0.2%
Quim Vidal	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904859	245904859	0.013864	0.010804	2026-10-12T23:11:06.747890+00:00	1.4%
Quim Vidal	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904991	245904991	0.033742	0.027653	2026-10-12T23:11:07.952964+00:00	3.4%
Quim Vidal	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905123	245905123	0.085744	0.067447	2026-10-12T23:11:09.073291+00:00	8.6%
Quim Vidal	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905255	245905255	0.476467	0.436933	2026-10-12T23:11:10.724619+00:00	47.6%
Jason Scrivener	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904725	245904725	0.001917	0.001533	2026-10-12T23:11:05.501054+00:00	0.2%
Jason Scrivener	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904857	245904857	0.014442	0.01304	2026-10-12T23:11:06.747890+00:00	1.4%
Jason Scrivener	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904989	245904989	0.037729	0.032671	2026-10-12T23:11:07.952964+00:00	3.8%
Jason Scrivener	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905121	245905121	0.096087	0.083857	2026-10-12T23:11:09.073291+00:00	9.6%
Jason Scrivener	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905253	245905253	0.513567	0.487217	2026-10-12T23:11:10.724619+00:00	51.4%
Grant Forrest	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904743	245904743	0.001883	0.000833	2026-10-12T23:11:05.501054+00:00	0.2%
Grant Forrest	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904875	245904875	0.014801	0.006287	2026-10-12T23:11:06.747890+00:00	1.5%
Grant Forrest	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905007	245905007	0.035881	0.016273	2026-10-12T23:11:07.952964+00:00	3.6%
Grant Forrest	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905139	245905139	0.091251	0.044779	2026-10-12T23:11:09.073291+00:00	9.1%
Grant Forrest	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905271	245905271	0.485333	0.36525	2026-10-12T23:11:10.724619+00:00	48.5%
Euan Walker	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352455	246352455	0.001833	0.001833	2026-10-12T23:11:05.501054+00:00	0.2%
Euan Walker	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352513	246352513	0.014952	0.014952	2026-10-12T23:11:06.747890+00:00	1.5%
Euan Walker	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352571	246352571	0.038123	0.038123	2026-10-12T23:11:07.952964+00:00	3.8%
Euan Walker	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352629	246352629	0.098529	0.098529	2026-10-12T23:11:09.073291+00:00	9.9%
Euan Walker	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352687	246352687	0.51695	0.51695	2026-10-12T23:11:10.724619+00:00	51.7%
Ricardo Gouveia	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904711	245904711	0.001833	0.002617	2026-10-12T23:11:05.501054+00:00	0.2%
Ricardo Gouveia	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904843	245904843	0.0156	0.017994	2026-10-12T23:11:06.747890+00:00	1.6%
Ricardo Gouveia	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904975	245904975	0.038436	0.04219	2026-10-12T23:11:07.952964+00:00	3.8%
Ricardo Gouveia	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905107	245905107	0.094628	0.099911	2026-10-12T23:11:09.073291+00:00	9.5%
Ricardo Gouveia	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905239	245905239	0.494467	0.49875	2026-10-12T23:11:10.724619+00:00	49.4%
Ross Fisher	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904702	245904702	0.001767	0.003467	2026-10-12T23:11:05.501054+00:00	0.2%
Ross Fisher	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904834	245904834	0.014393	0.022761	2026-10-12T23:11:06.747890+00:00	1.4%
Ross Fisher	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904966	245904966	0.036916	0.052196	2026-10-12T23:11:07.952964+00:00	3.7%
Ross Fisher	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905098	245905098	0.09411	0.119435	2026-10-12T23:11:09.073291+00:00	9.4%
Ross Fisher	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905230	245905230	0.49705	0.541217	2026-10-12T23:11:10.724619+00:00	49.7%
Michael Hollick	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904714	245904714	0.001767	0.002367	2026-10-12T23:11:05.501054+00:00	0.2%
Michael Hollick	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904846	245904846	0.014155	0.016907	2026-10-12T23:11:06.747890+00:00	1.4%
Michael Hollick	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904978	245904978	0.036345	0.039834	2026-10-12T23:11:07.952964+00:00	3.6%
Michael Hollick	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905110	245905110	0.093526	0.096601	2026-10-12T23:11:09.073291+00:00	9.4%
Michael Hollick	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905242	245905242	0.495183	0.489417	2026-10-12T23:11:10.724619+00:00	49.5%
Rikuya Hoshino	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904726	245904726	0.001717	0.0015	2026-10-12T23:11:05.501054+00:00	0.2%
Rikuya Hoshino	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904858	245904858	0.012593	0.013243	2026-10-12T23:11:06.747890+00:00	1.3%
Rikuya Hoshino	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904990	245904990	0.033242	0.033968	2026-10-12T23:11:07.952964+00:00	3.3%
Rikuya Hoshino	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905122	245905122	0.088129	0.085972	2026-10-12T23:11:09.073291+00:00	8.8%
Rikuya Hoshino	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905254	245905254	0.488833	0.49045	2026-10-12T23:11:10.724619+00:00	48.9%
Kiradech Aphibarnrat	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904740	245904740	0.001683	0.001	2026-10-12T23:11:05.501054+00:00	0.2%
Kiradech Aphibarnrat	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904872	245904872	0.013275	0.008864	2026-10-12T23:11:06.747890+00:00	1.3%
Kiradech Aphibarnrat	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905004	245905004	0.034873	0.023638	2026-10-12T23:11:07.952964+00:00	3.5%
Kiradech Aphibarnrat	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905136	245905136	0.088254	0.063082	2026-10-12T23:11:09.073291+00:00	8.8%
Kiradech Aphibarnrat	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905268	245905268	0.486183	0.433283	2026-10-12T23:11:10.724619+00:00	48.6%
Cameron Adam	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352456	246352456	0.001683	0.001683	2026-10-12T23:11:05.501054+00:00	0.2%
Cameron Adam	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352514	246352514	0.012837	0.012837	2026-10-12T23:11:06.747890+00:00	1.3%
Cameron Adam	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352572	246352572	0.032222	0.032222	2026-10-12T23:11:07.952964+00:00	3.2%
Cameron Adam	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352630	246352630	0.081851	0.081851	2026-10-12T23:11:09.073291+00:00	8.2%
Cameron Adam	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352688	246352688	0.465133	0.465133	2026-10-12T23:11:10.724619+00:00	46.5%
Ivan Cantero Gutierrez	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904722	245904722	0.001633	0.0019	2026-10-12T23:11:05.501054+00:00	0.2%
Ivan Cantero Gutierrez	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904854	245904854	0.012875	0.013299	2026-10-12T23:11:06.747890+00:00	1.3%
Ivan Cantero Gutierrez	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904986	245904986	0.033313	0.030943	2026-10-12T23:11:07.952964+00:00	3.3%
Ivan Cantero Gutierrez	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905118	245905118	0.085331	0.078215	2026-10-12T23:11:09.073291+00:00	8.5%
Ivan Cantero Gutierrez	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905250	245905250	0.472867	0.450483	2026-10-12T23:11:10.724619+00:00	47.3%
Scott Jamieson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352457	246352457	0.001617	0.001617	2026-10-12T23:11:05.501054+00:00	0.2%
Scott Jamieson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352515	246352515	0.012958	0.012958	2026-10-12T23:11:06.747890+00:00	1.3%
Scott Jamieson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352573	246352573	0.033822	0.033822	2026-10-12T23:11:07.952964+00:00	3.4%
Scott Jamieson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352631	246352631	0.086415	0.086415	2026-10-12T23:11:09.073291+00:00	8.6%
Scott Jamieson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352689	246352689	0.48625	0.48625	2026-10-12T23:11:10.724619+00:00	48.6%
Stefano Mazzoli	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904734	245904734	0.001617	0.001133	2026-10-12T23:11:05.501054+00:00	0.2%
Stefano Mazzoli	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904866	245904866	0.013017	0.00938	2026-10-12T23:11:06.747890+00:00	1.3%
Stefano Mazzoli	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904998	245904998	0.033304	0.023377	2026-10-12T23:11:07.952964+00:00	3.3%
Stefano Mazzoli	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905130	245905130	0.087677	0.058113	2026-10-12T23:11:09.073291+00:00	8.8%
Stefano Mazzoli	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905262	245905262	0.486483	0.400067	2026-10-12T23:11:10.724619+00:00	48.6%
Renato Paratore	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904724	245904724	0.001517	0.00155	2026-10-12T23:11:05.501054+00:00	0.2%
Renato Paratore	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904856	245904856	0.011784	0.012101	2026-10-12T23:11:06.747890+00:00	1.2%
Renato Paratore	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904988	245904988	0.029505	0.029959	2026-10-12T23:11:07.952964+00:00	3%
Renato Paratore	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905120	245905120	0.077616	0.074319	2026-10-12T23:11:09.073291+00:00	7.8%
Renato Paratore	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905252	245905252	0.464017	0.4587	2026-10-12T23:11:10.724619+00:00	46.4%
Ben Schmidt	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904729	245904729	0.001517	0.00145	2026-10-12T23:11:05.501054+00:00	0.2%
Ben Schmidt	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904861	245904861	0.013372	0.011456	2026-10-12T23:11:06.747890+00:00	1.3%
Ben Schmidt	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904993	245904993	0.032945	0.028746	2026-10-12T23:11:07.952964+00:00	3.3%
Ben Schmidt	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905125	245905125	0.083536	0.071799	2026-10-12T23:11:09.073291+00:00	8.4%
Ben Schmidt	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905257	245905257	0.47545	0.435383	2026-10-12T23:11:10.724619+00:00	47.5%
Elvis Smylie	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904715	245904715	0.001467	0.002367	2026-10-12T23:11:05.501054+00:00	0.1%
Elvis Smylie	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904847	245904847	0.013238	0.01582	2026-10-12T23:11:06.747890+00:00	1.3%
Elvis Smylie	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904979	245904979	0.03503	0.037297	2026-10-12T23:11:07.952964+00:00	3.5%
Elvis Smylie	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905111	245905111	0.089542	0.090707	2026-10-12T23:11:09.073291+00:00	9%
Elvis Smylie	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905243	245905243	0.494033	0.49255	2026-10-12T23:11:10.724619+00:00	49.4%
Dylan Frittelli	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904733	245904733	0.00145	0.001217	2026-10-12T23:11:05.501054+00:00	0.1%
Dylan Frittelli	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904865	245904865	0.011123	0.009565	2026-10-12T23:11:06.747890+00:00	1.1%
Dylan Frittelli	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904997	245904997	0.02788	0.023235	2026-10-12T23:11:07.952964+00:00	2.8%
Dylan Frittelli	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905129	245905129	0.072097	0.060147	2026-10-12T23:11:09.073291+00:00	7.2%
Dylan Frittelli	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905261	245905261	0.448417	0.4159	2026-10-12T23:11:10.724619+00:00	44.8%
Jens Dantorp	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904739	245904739	0.001383	0.001033	2026-10-12T23:11:05.501054+00:00	0.1%
Jens Dantorp	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904871	245904871	0.012735	0.008532	2026-10-12T23:11:06.747890+00:00	1.3%
Jens Dantorp	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905003	245905003	0.032848	0.021959	2026-10-12T23:11:07.952964+00:00	3.3%
Jens Dantorp	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905135	245905135	0.085075	0.059352	2026-10-12T23:11:09.073291+00:00	8.5%
Jens Dantorp	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905267	245905267	0.47925	0.429317	2026-10-12T23:11:10.724619+00:00	47.9%
Tobias Jonsson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352458	246352458	0.001267	0.001267	2026-10-12T23:11:05.501054+00:00	0.1%
Tobias Jonsson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352516	246352516	0.009385	0.009385	2026-10-12T23:11:06.747890+00:00	0.9%
Tobias Jonsson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352574	246352574	0.025343	0.025343	2026-10-12T23:11:07.952964+00:00	2.5%
Tobias Jonsson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352632	246352632	0.066312	0.066312	2026-10-12T23:11:09.073291+00:00	6.6%
Tobias Jonsson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352690	246352690	0.430617	0.430617	2026-10-12T23:11:10.724619+00:00	43.1%
Rafa Cabrera Bello	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904735	245904735	0.001133	0.001117	2026-10-12T23:11:05.501054+00:00	0.1%
Rafa Cabrera Bello	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904867	245904867	0.008761	0.009415	2026-10-12T23:11:06.747890+00:00	0.9%
Rafa Cabrera Bello	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904999	245904999	0.022725	0.023744	2026-10-12T23:11:07.952964+00:00	2.3%
Rafa Cabrera Bello	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905131	245905131	0.061085	0.061997	2026-10-12T23:11:09.073291+00:00	6.1%
Rafa Cabrera Bello	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905263	245905263	0.421317	0.42725	2026-10-12T23:11:10.724619+00:00	42.1%
Albin Bergstrom	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352459	246352459	0.001067	0.001067	2026-10-12T23:11:05.501054+00:00	0.1%
Albin Bergstrom	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352517	246352517	0.009029	0.009029	2026-10-12T23:11:06.747890+00:00	0.9%
Albin Bergstrom	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352575	246352575	0.023097	0.023097	2026-10-12T23:11:07.952964+00:00	2.3%
Albin Bergstrom	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352633	246352633	0.062457	0.062457	2026-10-12T23:11:09.073291+00:00	6.2%
Albin Bergstrom	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352691	246352691	0.420233	0.420233	2026-10-12T23:11:10.724619+00:00	42%
Hugo Townsend	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352460	246352460	0.001033	0.001033	2026-10-12T23:11:05.501054+00:00	0.1%
Hugo Townsend	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352518	246352518	0.008106	0.008106	2026-10-12T23:11:06.747890+00:00	0.8%
Hugo Townsend	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352576	246352576	0.02202	0.02202	2026-10-12T23:11:07.952964+00:00	2.2%
Hugo Townsend	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352634	246352634	0.058898	0.058898	2026-10-12T23:11:09.073291+00:00	5.9%
Hugo Townsend	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352692	246352692	0.4084	0.4084	2026-10-12T23:11:10.724619+00:00	40.8%
Pablo Larrazabal	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904745	245904745	0.001	0.0007	2026-10-12T23:11:05.501054+00:00	0.1%
Pablo Larrazabal	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904877	245904877	0.010292	0.008024	2026-10-12T23:11:06.747890+00:00	1%
Pablo Larrazabal	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905009	245905009	0.02783	0.02112	2026-10-12T23:11:07.952964+00:00	2.8%
Pablo Larrazabal	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905141	245905141	0.077976	0.055295	2026-10-12T23:11:09.073291+00:00	7.8%
Pablo Larrazabal	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905273	245905273	0.4696	0.401033	2026-10-12T23:11:10.724619+00:00	47%
Danny Willett	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904730	245904730	0.000967	0.0014	2026-10-12T23:11:05.501054+00:00	<0.1%
Danny Willett	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904862	245904862	0.008874	0.011237	2026-10-12T23:11:06.747890+00:00	0.9%
Danny Willett	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904994	245904994	0.023306	0.029053	2026-10-12T23:11:07.952964+00:00	2.3%
Danny Willett	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905126	245905126	0.063677	0.074663	2026-10-12T23:11:09.073291+00:00	6.4%
Danny Willett	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905258	245905258	0.432917	0.45445	2026-10-12T23:11:10.724619+00:00	43.3%
Jordan Gumberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904741	245904741	0.000967	0.001	2026-10-12T23:11:05.501054+00:00	<0.1%
Jordan Gumberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904873	245904873	0.007162	0.007327	2026-10-12T23:11:06.747890+00:00	0.7%
Jordan Gumberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905005	245905005	0.019184	0.018185	2026-10-12T23:11:07.952964+00:00	1.9%
Jordan Gumberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905137	245905137	0.051956	0.047579	2026-10-12T23:11:09.073291+00:00	5.2%
Jordan Gumberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905269	245905269	0.3893	0.372567	2026-10-12T23:11:10.724619+00:00	38.9%
Marcel Siem	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904744	245904744	0.00095	0.000767	2026-10-12T23:11:05.501054+00:00	<0.1%
Marcel Siem	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904876	245904876	0.007853	0.006524	2026-10-12T23:11:06.747890+00:00	0.8%
Marcel Siem	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905008	245905008	0.019472	0.017103	2026-10-12T23:11:07.952964+00:00	1.9%
Marcel Siem	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905140	245905140	0.052122	0.045231	2026-10-12T23:11:09.073291+00:00	5.2%
Marcel Siem	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905272	245905272	0.386117	0.371817	2026-10-12T23:11:10.724619+00:00	38.6%
Jack Senior	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904738	245904738	0.00095	0.00105	2026-10-12T23:11:05.501054+00:00	<0.1%
Jack Senior	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904870	245904870	0.007972	0.009501	2026-10-12T23:11:06.747890+00:00	0.8%
Jack Senior	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905002	245905002	0.022691	0.024657	2026-10-12T23:11:07.952964+00:00	2.3%
Jack Senior	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905134	245905134	0.06294	0.064513	2026-10-12T23:11:09.073291+00:00	6.3%
Jack Senior	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905266	245905266	0.432633	0.4259	2026-10-12T23:11:10.724619+00:00	43.3%
Veer Ahlawat	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352461	246352461	0.00095	0.00095	2026-10-12T23:11:05.501054+00:00	<0.1%
Veer Ahlawat	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352519	246352519	0.006857	0.006857	2026-10-12T23:11:06.747890+00:00	0.7%
Veer Ahlawat	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352577	246352577	0.019083	0.019083	2026-10-12T23:11:07.952964+00:00	1.9%
Veer Ahlawat	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352635	246352635	0.054782	0.054782	2026-10-12T23:11:09.073291+00:00	5.5%
Veer Ahlawat	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352693	246352693	0.40625	0.40625	2026-10-12T23:11:10.724619+00:00	40.6%
Yurav Premlall	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904721	245904721	0.000867	0.00195	2026-10-12T23:11:05.501054+00:00	<0.1%
Yurav Premlall	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904853	245904853	0.007758	0.013825	2026-10-12T23:11:06.747890+00:00	0.8%
Yurav Premlall	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904985	245904985	0.021476	0.033153	2026-10-12T23:11:07.952964+00:00	2.1%
Yurav Premlall	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905117	245905117	0.061829	0.084631	2026-10-12T23:11:09.073291+00:00	6.2%
Yurav Premlall	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905249	245905249	0.429717	0.481533	2026-10-12T23:11:10.724619+00:00	43%
Daniel Young	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352462	246352462	0.000833	0.000833	2026-10-12T23:11:05.501054+00:00	<0.1%
Daniel Young	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352520	246352520	0.007498	0.007498	2026-10-12T23:11:06.747890+00:00	0.7%
Daniel Young	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352578	246352578	0.020486	0.020486	2026-10-12T23:11:07.952964+00:00	2%
Daniel Young	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352636	246352636	0.05906	0.05906	2026-10-12T23:11:09.073291+00:00	5.9%
Daniel Young	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352694	246352694	0.416433	0.416433	2026-10-12T23:11:10.724619+00:00	41.6%
Junghwan Lee	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352463	246352463	0.000783	0.000783	2026-10-12T23:11:05.501054+00:00	<0.1%
Junghwan Lee	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352521	246352521	0.006227	0.006227	2026-10-12T23:11:06.747890+00:00	0.6%
Junghwan Lee	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352579	246352579	0.017676	0.017676	2026-10-12T23:11:07.952964+00:00	1.8%
Junghwan Lee	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352637	246352637	0.050664	0.050664	2026-10-12T23:11:09.073291+00:00	5.1%
Junghwan Lee	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352695	246352695	0.394933	0.394933	2026-10-12T23:11:10.724619+00:00	39.5%
Yuvraj Singh Sandhu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352464	246352464	0.000783	0.000783	2026-10-12T23:11:05.501054+00:00	<0.1%
Yuvraj Singh Sandhu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352522	246352522	0.007051	0.007051	2026-10-12T23:11:06.747890+00:00	0.7%
Yuvraj Singh Sandhu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352580	246352580	0.019385	0.019385	2026-10-12T23:11:07.952964+00:00	1.9%
Yuvraj Singh Sandhu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352638	246352638	0.054996	0.054996	2026-10-12T23:11:09.073291+00:00	5.5%
Yuvraj Singh Sandhu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352696	246352696	0.408533	0.408533	2026-10-12T23:11:10.724619+00:00	40.9%
Richard Sterne	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904747	245904747	0.000767	0.00045	2026-10-12T23:11:05.501054+00:00	<0.1%
Richard Sterne	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904879	245904879	0.006821	0.004633	2026-10-12T23:11:06.747890+00:00	0.7%
Richard Sterne	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905011	245905011	0.018211	0.013393	2026-10-12T23:11:07.952964+00:00	1.8%
Richard Sterne	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905143	245905143	0.050171	0.039476	2026-10-12T23:11:09.073291+00:00	5%
Richard Sterne	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905275	245905275	0.39765	0.359417	2026-10-12T23:11:10.724619+00:00	39.8%
Zander Lombard	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352465	246352465	0.000733	0.000733	2026-10-12T23:11:05.501054+00:00	<0.1%
Zander Lombard	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352523	246352523	0.005792	0.005792	2026-10-12T23:11:06.747890+00:00	0.6%
Zander Lombard	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352581	246352581	0.015231	0.015231	2026-10-12T23:11:07.952964+00:00	1.5%
Zander Lombard	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352639	246352639	0.044419	0.044419	2026-10-12T23:11:09.073291+00:00	4.4%
Zander Lombard	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352697	246352697	0.371683	0.371683	2026-10-12T23:11:10.724619+00:00	37.2%
Sebastian Garcia Rodriguez	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904731	245904731	0.000633	0.001283	2026-10-12T23:11:05.501054+00:00	<0.1%
Sebastian Garcia Rodriguez	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904863	245904863	0.006316	0.00862	2026-10-12T23:11:06.747890+00:00	0.6%
Sebastian Garcia Rodriguez	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904995	245904995	0.017587	0.022792	2026-10-12T23:11:07.952964+00:00	1.8%
Sebastian Garcia Rodriguez	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905127	245905127	0.050005	0.057551	2026-10-12T23:11:09.073291+00:00	5%
Sebastian Garcia Rodriguez	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905259	245905259	0.38915	0.41085	2026-10-12T23:11:10.724619+00:00	38.9%
Gaganjeet Bhullar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352466	246352466	0.000633	0.000633	2026-10-12T23:11:05.501054+00:00	<0.1%
Gaganjeet Bhullar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352524	246352524	0.005499	0.005499	2026-10-12T23:11:06.747890+00:00	0.5%
Gaganjeet Bhullar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352582	246352582	0.015048	0.015048	2026-10-12T23:11:07.952964+00:00	1.5%
Gaganjeet Bhullar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352640	246352640	0.044568	0.044568	2026-10-12T23:11:09.073291+00:00	4.5%
Gaganjeet Bhullar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352698	246352698	0.35735	0.35735	2026-10-12T23:11:10.724619+00:00	35.7%
Luke Donald	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352467	246352467	0.000583	0.000583	2026-10-12T23:11:05.501054+00:00	<0.1%
Luke Donald	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352525	246352525	0.005684	0.005684	2026-10-12T23:11:06.747890+00:00	0.6%
Luke Donald	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352583	246352583	0.015558	0.015558	2026-10-12T23:11:07.952964+00:00	1.6%
Luke Donald	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352641	246352641	0.046964	0.046964	2026-10-12T23:11:09.073291+00:00	4.7%
Luke Donald	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352699	246352699	0.39245	0.39245	2026-10-12T23:11:10.724619+00:00	39.2%
Khalin H Joshi	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352468	246352468	0.00055	0.00055	2026-10-12T23:11:05.501054+00:00	<0.1%
Khalin H Joshi	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352526	246352526	0.003752	0.003752	2026-10-12T23:11:06.747890+00:00	0.4%
Khalin H Joshi	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352584	246352584	0.01104	0.01104	2026-10-12T23:11:07.952964+00:00	1.1%
Khalin H Joshi	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352642	246352642	0.034616	0.034616	2026-10-12T23:11:09.073291+00:00	3.5%
Khalin H Joshi	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352700	246352700	0.339533	0.339533	2026-10-12T23:11:10.724619+00:00	34%
Shaurya Bhattacharya	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352469	246352469	0.0005	0.0005	2026-10-12T23:11:05.501054+00:00	<0.1%
Shaurya Bhattacharya	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352527	246352527	0.004559	0.004559	2026-10-12T23:11:06.747890+00:00	0.5%
Shaurya Bhattacharya	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352585	246352585	0.012316	0.012316	2026-10-12T23:11:07.952964+00:00	1.2%
Shaurya Bhattacharya	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352643	246352643	0.035675	0.035675	2026-10-12T23:11:09.073291+00:00	3.6%
Shaurya Bhattacharya	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352701	246352701	0.349217	0.349217	2026-10-12T23:11:10.724619+00:00	34.9%
Karandeep Kochhar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352470	246352470	0.000433	0.000433	2026-10-12T23:11:05.501054+00:00	<0.1%
Karandeep Kochhar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352528	246352528	0.003853	0.003853	2026-10-12T23:11:06.747890+00:00	0.4%
Karandeep Kochhar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352586	246352586	0.010431	0.010431	2026-10-12T23:11:07.952964+00:00	1%
Karandeep Kochhar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352644	246352644	0.031351	0.031351	2026-10-12T23:11:09.073291+00:00	3.1%
Karandeep Kochhar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352702	246352702	0.3302	0.3302	2026-10-12T23:11:10.724619+00:00	33%
Anthony Quayle	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352471	246352471	0.000417	0.000417	2026-10-12T23:11:05.501054+00:00	<0.1%
Anthony Quayle	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352529	246352529	0.003178	0.003178	2026-10-12T23:11:06.747890+00:00	0.3%
Anthony Quayle	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352587	246352587	0.009059	0.009059	2026-10-12T23:11:07.952964+00:00	0.9%
Anthony Quayle	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352645	246352645	0.028636	0.028636	2026-10-12T23:11:09.073291+00:00	2.9%
Anthony Quayle	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352703	246352703	0.310483	0.310483	2026-10-12T23:11:10.724619+00:00	31%
Shubhankar Sharma	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352472	246352472	0.000383	0.000383	2026-10-12T23:11:05.501054+00:00	<0.1%
Shubhankar Sharma	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352530	246352530	0.003972	0.003972	2026-10-12T23:11:06.747890+00:00	0.4%
Shubhankar Sharma	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352588	246352588	0.012081	0.012081	2026-10-12T23:11:07.952964+00:00	1.2%
Shubhankar Sharma	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352646	246352646	0.034549	0.034549	2026-10-12T23:11:09.073291+00:00	3.5%
Shubhankar Sharma	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352704	246352704	0.345817	0.345817	2026-10-12T23:11:10.724619+00:00	34.6%
Ryan Peake	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352473	246352473	0.000367	0.000367	2026-10-12T23:11:05.501054+00:00	<0.1%
Ryan Peake	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352531	246352531	0.003429	0.003429	2026-10-12T23:11:06.747890+00:00	0.3%
Ryan Peake	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352589	246352589	0.010212	0.010212	2026-10-12T23:11:07.952964+00:00	1%
Ryan Peake	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352647	246352647	0.028998	0.028998	2026-10-12T23:11:09.073291+00:00	2.9%
Ryan Peake	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352705	246352705	0.315867	0.315867	2026-10-12T23:11:10.724619+00:00	31.6%
Jeong Weon Ko	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904753	245904753	0.00035	0.000183	2026-10-12T23:11:05.501054+00:00	<0.1%
Jeong Weon Ko	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904885	245904885	0.00272	0.001893	2026-10-12T23:11:06.747890+00:00	0.3%
Jeong Weon Ko	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905017	245905017	0.007551	0.006145	2026-10-12T23:11:07.952964+00:00	0.8%
Jeong Weon Ko	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905149	245905149	0.021783	0.018329	2026-10-12T23:11:09.073291+00:00	2.2%
Jeong Weon Ko	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905281	245905281	0.2707	0.256633	2026-10-12T23:11:10.724619+00:00	27.1%
James Morrison	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904748	245904748	0.000317	0.000417	2026-10-12T23:11:05.501054+00:00	<0.1%
James Morrison	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904880	245904880	0.003667	0.004102	2026-10-12T23:11:06.747890+00:00	0.4%
James Morrison	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905012	245905012	0.011313	0.011861	2026-10-12T23:11:07.952964+00:00	1.1%
James Morrison	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905144	245905144	0.034577	0.034241	2026-10-12T23:11:09.073291+00:00	3.5%
James Morrison	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905276	245905276	0.35795	0.359633	2026-10-12T23:11:10.724619+00:00	35.8%
Matthew Baldwin	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352474	246352474	0.000233	0.000233	2026-10-12T23:11:05.501054+00:00	<0.1%
Matthew Baldwin	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352532	246352532	0.002265	0.002265	2026-10-12T23:11:06.747890+00:00	0.2%
Matthew Baldwin	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352590	246352590	0.006926	0.006926	2026-10-12T23:11:07.952964+00:00	0.7%
Matthew Baldwin	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352648	246352648	0.022391	0.022391	2026-10-12T23:11:09.073291+00:00	2.2%
Matthew Baldwin	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352706	246352706	0.289933	0.289933	2026-10-12T23:11:10.724619+00:00	29%
Dylan Naidoo	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904752	245904752	0.0002	0.00025	2026-10-12T23:11:05.501054+00:00	<0.1%
Dylan Naidoo	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904884	245904884	0.002109	0.00275	2026-10-12T23:11:06.747890+00:00	0.2%
Dylan Naidoo	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905016	245905016	0.006158	0.007537	2026-10-12T23:11:07.952964+00:00	0.6%
Dylan Naidoo	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905148	245905148	0.020476	0.022551	2026-10-12T23:11:09.073291+00:00	2%
Dylan Naidoo	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905280	245905280	0.2782	0.281317	2026-10-12T23:11:10.724619+00:00	27.8%
Joshua Berry	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352475	246352475	0.000183	0.000183	2026-10-12T23:11:05.501054+00:00	<0.1%
Joshua Berry	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352533	246352533	0.001148	0.001148	2026-10-12T23:11:06.747890+00:00	0.1%
Joshua Berry	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352591	246352591	0.003486	0.003486	2026-10-12T23:11:07.952964+00:00	0.3%
Joshua Berry	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352649	246352649	0.011137	0.011137	2026-10-12T23:11:09.073291+00:00	1.1%
Joshua Berry	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352707	246352707	0.217867	0.217867	2026-10-12T23:11:10.724619+00:00	21.8%
Saptak Talwar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352476	246352476	0.000167	0.000167	2026-10-12T23:11:05.501054+00:00	<0.1%
Saptak Talwar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352534	246352534	0.002249	0.002249	2026-10-12T23:11:06.747890+00:00	0.2%
Saptak Talwar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352592	246352592	0.007107	0.007107	2026-10-12T23:11:07.952964+00:00	0.7%
Saptak Talwar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352650	246352650	0.022512	0.022512	2026-10-12T23:11:09.073291+00:00	2.3%
Saptak Talwar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352708	246352708	0.290667	0.290667	2026-10-12T23:11:10.724619+00:00	29.1%
Honey Baisoya	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352477	246352477	0.000133	0.000133	2026-10-12T23:11:05.501054+00:00	<0.1%
Honey Baisoya	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352535	246352535	0.000721	0.000721	2026-10-12T23:11:06.747890+00:00	<0.1%
Honey Baisoya	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352593	246352593	0.002336	0.002336	2026-10-12T23:11:07.952964+00:00	0.2%
Honey Baisoya	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352651	246352651	0.007006	0.007006	2026-10-12T23:11:09.073291+00:00	0.7%
Honey Baisoya	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352709	246352709	0.1586	0.1586	2026-10-12T23:11:10.724619+00:00	15.9%
Ryggs Johnston	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904754	245904754	0.000117	0.00015	2026-10-12T23:11:05.501054+00:00	<0.1%
Ryggs Johnston	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904886	245904886	0.001694	0.001917	2026-10-12T23:11:06.747890+00:00	0.2%
Ryggs Johnston	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905018	245905018	0.004942	0.005013	2026-10-12T23:11:07.952964+00:00	0.5%
Ryggs Johnston	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905150	245905150	0.016375	0.014793	2026-10-12T23:11:09.073291+00:00	1.6%
Ryggs Johnston	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905282	245905282	0.249533	0.228817	2026-10-12T23:11:10.724619+00:00	25%
Rashid Khan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352479	246352479	0.0001	0.0001	2026-10-12T23:11:05.501054+00:00	<0.1%
Rashid Khan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352537	246352537	0.000944	0.000944	2026-10-12T23:11:06.747890+00:00	<0.1%
Rashid Khan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352595	246352595	0.003313	0.003313	2026-10-12T23:11:07.952964+00:00	0.3%
Rashid Khan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352653	246352653	0.010602	0.010602	2026-10-12T23:11:09.073291+00:00	1.1%
Rashid Khan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352711	246352711	0.20485	0.20485	2026-10-12T23:11:10.724619+00:00	20.5%
Manu Gandas	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352478	246352478	0.0001	0.0001	2026-10-12T23:11:05.501054+00:00	<0.1%
Manu Gandas	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352536	246352536	0.001027	0.001027	2026-10-12T23:11:06.747890+00:00	0.1%
Manu Gandas	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352594	246352594	0.003442	0.003442	2026-10-12T23:11:07.952964+00:00	0.3%
Manu Gandas	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352652	246352652	0.011722	0.011722	2026-10-12T23:11:09.073291+00:00	1.2%
Manu Gandas	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352710	246352710	0.217733	0.217733	2026-10-12T23:11:10.724619+00:00	21.8%
Angad Cheema	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352480	246352480	8.3e-05	8.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Angad Cheema	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352538	246352538	0.001342	0.001342	2026-10-12T23:11:06.747890+00:00	0.1%
Angad Cheema	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352596	246352596	0.004195	0.004195	2026-10-12T23:11:07.952964+00:00	0.4%
Angad Cheema	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352654	246352654	0.014509	0.014509	2026-10-12T23:11:09.073291+00:00	1.5%
Angad Cheema	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352712	246352712	0.235817	0.235817	2026-10-12T23:11:10.724619+00:00	23.6%
Dhruv Sheoran	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352481	246352481	6.7e-05	6.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Dhruv Sheoran	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352539	246352539	0.000711	0.000711	2026-10-12T23:11:06.747890+00:00	<0.1%
Dhruv Sheoran	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352597	246352597	0.002336	0.002336	2026-10-12T23:11:07.952964+00:00	0.2%
Dhruv Sheoran	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352655	246352655	0.008559	0.008559	2026-10-12T23:11:09.073291+00:00	0.9%
Dhruv Sheoran	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352713	246352713	0.19225	0.19225	2026-10-12T23:11:10.724619+00:00	19.2%
Amardip Malik	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352482	246352482	5e-05	5e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Amardip Malik	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352540	246352540	0.000623	0.000623	2026-10-12T23:11:06.747890+00:00	<0.1%
Amardip Malik	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352598	246352598	0.002052	0.002052	2026-10-12T23:11:07.952964+00:00	0.2%
Amardip Malik	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352656	246352656	0.008313	0.008313	2026-10-12T23:11:09.073291+00:00	0.8%
Amardip Malik	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352714	246352714	0.194567	0.194567	2026-10-12T23:11:10.724619+00:00	19.5%
Kshitij Naveed Kaul	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352483	246352483	5e-05	5e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Kshitij Naveed Kaul	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352541	246352541	0.000692	0.000692	2026-10-12T23:11:06.747890+00:00	<0.1%
Kshitij Naveed Kaul	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352599	246352599	0.002327	0.002327	2026-10-12T23:11:07.952964+00:00	0.2%
Kshitij Naveed Kaul	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352657	246352657	0.007373	0.007373	2026-10-12T23:11:09.073291+00:00	0.7%
Kshitij Naveed Kaul	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352715	246352715	0.177383	0.177383	2026-10-12T23:11:10.724619+00:00	17.7%
Jamal Hossain	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352486	246352486	3.3e-05	3.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Jamal Hossain	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352544	246352544	0.000426	0.000426	2026-10-12T23:11:06.747890+00:00	<0.1%
Jamal Hossain	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352602	246352602	0.001292	0.001292	2026-10-12T23:11:07.952964+00:00	0.1%
Jamal Hossain	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352660	246352660	0.005236	0.005236	2026-10-12T23:11:09.073291+00:00	0.5%
Jamal Hossain	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352718	246352718	0.148933	0.148933	2026-10-12T23:11:10.724619+00:00	14.9%
Ajeetesh Sandhu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352484	246352484	3.3e-05	3.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Ajeetesh Sandhu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352542	246352542	0.000766	0.000766	2026-10-12T23:11:06.747890+00:00	<0.1%
Ajeetesh Sandhu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352600	246352600	0.003037	0.003037	2026-10-12T23:11:07.952964+00:00	0.3%
Ajeetesh Sandhu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352658	246352658	0.011067	0.011067	2026-10-12T23:11:09.073291+00:00	1.1%
Ajeetesh Sandhu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352716	246352716	0.22465	0.22465	2026-10-12T23:11:10.724619+00:00	22.5%
Kartik Singh	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352485	246352485	3.3e-05	3.3e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Kartik Singh	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352543	246352543	0.000195	0.000195	2026-10-12T23:11:06.747890+00:00	<0.1%
Kartik Singh	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352601	246352601	0.000745	0.000745	2026-10-12T23:11:07.952964+00:00	<0.1%
Kartik Singh	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352659	246352659	0.002921	0.002921	2026-10-12T23:11:09.073291+00:00	0.3%
Kartik Singh	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352717	246352717	0.1067	0.1067	2026-10-12T23:11:10.724619+00:00	10.7%
Akshay Sharma	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352487	246352487	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Akshay Sharma	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352545	246352545	0.000216	0.000216	2026-10-12T23:11:06.747890+00:00	<0.1%
Akshay Sharma	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352603	246352603	0.000892	0.000892	2026-10-12T23:11:07.952964+00:00	<0.1%
Akshay Sharma	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352661	246352661	0.004323	0.004323	2026-10-12T23:11:09.073291+00:00	0.4%
Akshay Sharma	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352719	246352719	0.141383	0.141383	2026-10-12T23:11:10.724619+00:00	14.1%
Mohd Azhar	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352489	246352489	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Mohd Azhar	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352547	246352547	0.000529	0.000529	2026-10-12T23:11:06.747890+00:00	<0.1%
Mohd Azhar	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352605	246352605	0.002044	0.002044	2026-10-12T23:11:07.952964+00:00	0.2%
Mohd Azhar	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352663	246352663	0.007204	0.007204	2026-10-12T23:11:09.073291+00:00	0.7%
Mohd Azhar	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352721	246352721	0.170867	0.170867	2026-10-12T23:11:10.724619+00:00	17.1%
Anshul Kabthiyal	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352490	246352490	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Anshul Kabthiyal	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352548	246352548	0.000235	0.000235	2026-10-12T23:11:06.747890+00:00	<0.1%
Anshul Kabthiyal	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352606	246352606	0.000898	0.000898	2026-10-12T23:11:07.952964+00:00	<0.1%
Anshul Kabthiyal	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352664	246352664	0.003496	0.003496	2026-10-12T23:11:09.073291+00:00	0.3%
Anshul Kabthiyal	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352722	246352722	0.1166	0.1166	2026-10-12T23:11:10.724619+00:00	11.7%
Om Prakash Chouhan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352491	246352491	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Om Prakash Chouhan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352549	246352549	0.000278	0.000278	2026-10-12T23:11:06.747890+00:00	<0.1%
Om Prakash Chouhan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352607	246352607	0.000965	0.000965	2026-10-12T23:11:07.952964+00:00	<0.1%
Om Prakash Chouhan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352665	246352665	0.003826	0.003826	2026-10-12T23:11:09.073291+00:00	0.4%
Om Prakash Chouhan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352723	246352723	0.133017	0.133017	2026-10-12T23:11:10.724619+00:00	13.3%
Viraj Madappa	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352492	246352492	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Viraj Madappa	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352550	246352550	0.000272	0.000272	2026-10-12T23:11:06.747890+00:00	<0.1%
Viraj Madappa	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352608	246352608	0.000784	0.000784	2026-10-12T23:11:07.952964+00:00	<0.1%
Viraj Madappa	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352666	246352666	0.003015	0.003015	2026-10-12T23:11:09.073291+00:00	0.3%
Viraj Madappa	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352724	246352724	0.1053	0.1053	2026-10-12T23:11:10.724619+00:00	10.5%
Manoj S	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352493	246352493	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Manoj S	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352551	246352551	0.000874	0.000874	2026-10-12T23:11:06.747890+00:00	<0.1%
Manoj S	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352609	246352609	0.003093	0.003093	2026-10-12T23:11:07.952964+00:00	0.3%
Manoj S	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352667	246352667	0.010483	0.010483	2026-10-12T23:11:09.073291+00:00	1%
Manoj S	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352725	246352725	0.194233	0.194233	2026-10-12T23:11:10.724619+00:00	19.4%
Shiv Kapur	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352494	246352494	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Shiv Kapur	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352552	246352552	0.000386	0.000386	2026-10-12T23:11:06.747890+00:00	<0.1%
Shiv Kapur	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352610	246352610	0.001508	0.001508	2026-10-12T23:11:07.952964+00:00	0.2%
Shiv Kapur	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352668	246352668	0.005788	0.005788	2026-10-12T23:11:09.073291+00:00	0.6%
Shiv Kapur	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352726	246352726	0.141917	0.141917	2026-10-12T23:11:10.724619+00:00	14.2%
Vishesh Sharma	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352495	246352495	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Vishesh Sharma	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352553	246352553	0.000534	0.000534	2026-10-12T23:11:06.747890+00:00	<0.1%
Vishesh Sharma	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352611	246352611	0.001822	0.001822	2026-10-12T23:11:07.952964+00:00	0.2%
Vishesh Sharma	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352669	246352669	0.005462	0.005462	2026-10-12T23:11:09.073291+00:00	0.5%
Vishesh Sharma	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352727	246352727	0.141333	0.141333	2026-10-12T23:11:10.724619+00:00	14.1%
Stepan Danek	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352488	246352488	1.7e-05	1.7e-05	2026-10-12T23:11:05.501054+00:00	<0.1%
Stepan Danek	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352546	246352546	0.000264	0.000264	2026-10-12T23:11:06.747890+00:00	<0.1%
Stepan Danek	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352604	246352604	0.000772	0.000772	2026-10-12T23:11:07.952964+00:00	<0.1%
Stepan Danek	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352662	246352662	0.002903	0.002903	2026-10-12T23:11:09.073291+00:00	0.3%
Stepan Danek	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352720	246352720	0.100767	0.100767	2026-10-12T23:11:10.724619+00:00	10.1%
Shubham Jaglan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352496	246352496	0	-	2026-10-12T23:11:05.501054+00:00	0%
Shubham Jaglan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352554	246352554	0.000164	0.000164	2026-10-12T23:11:06.747890+00:00	<0.1%
Shubham Jaglan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352612	246352612	0.000543	0.000543	2026-10-12T23:11:07.952964+00:00	<0.1%
Shubham Jaglan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352670	246352670	0.002049	0.002049	2026-10-12T23:11:09.073291+00:00	0.2%
Shubham Jaglan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352728	246352728	0.095883	0.095883	2026-10-12T23:11:10.724619+00:00	9.6%
Subash Tamang	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|246352497	246352497	0	-	2026-10-12T23:11:05.501054+00:00	0%
Subash Tamang	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|246352555	246352555	7.3e-05	7.3e-05	2026-10-12T23:11:06.747890+00:00	<0.1%
Subash Tamang	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|246352613	246352613	0.000413	0.000413	2026-10-12T23:11:07.952964+00:00	<0.1%
Subash Tamang	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|246352671	246352671	0.001823	0.001823	2026-10-12T23:11:09.073291+00:00	0.2%
Subash Tamang	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|246352729	246352729	0.087483	0.087483	2026-10-12T23:11:10.724619+00:00	8.7%
Alex Noren	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904632	245904632	-	0.0283	2026-10-12T19:09:44.432467+00:00	Unavailable
Alex Noren	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904764	245904764	-	0.129657	2026-10-12T19:09:46.711391+00:00	Unavailable
Alex Noren	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904896	245904896	-	0.230104	2026-10-12T19:09:47.805511+00:00	Unavailable
Alex Noren	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905028	245905028	-	0.391612	2026-10-12T19:09:49.369336+00:00	Unavailable
Alex Noren	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905160	245905160	-	0.78065	2026-10-12T19:09:51.639944+00:00	Unavailable
Mikael Lindberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904663	245904663	-	0.008033	2026-10-12T19:09:44.432467+00:00	Unavailable
Mikael Lindberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904795	245904795	-	0.045575	2026-10-12T19:09:46.711391+00:00	Unavailable
Mikael Lindberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904927	245904927	-	0.091028	2026-10-12T19:09:47.805511+00:00	Unavailable
Mikael Lindberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905059	245905059	-	0.183749	2026-10-12T19:09:49.369336+00:00	Unavailable
Mikael Lindberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905191	245905191	-	0.6029	2026-10-12T19:09:51.639944+00:00	Unavailable
Hennie Du Plessis	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904672	245904672	-	0.00655	2026-10-12T19:09:44.432467+00:00	Unavailable
Hennie Du Plessis	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904804	245904804	-	0.037743	2026-10-12T19:09:46.711391+00:00	Unavailable
Hennie Du Plessis	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904936	245904936	-	0.079987	2026-10-12T19:09:47.805511+00:00	Unavailable
Hennie Du Plessis	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905068	245905068	-	0.172117	2026-10-12T19:09:49.369336+00:00	Unavailable
Hennie Du Plessis	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905200	245905200	-	0.603433	2026-10-12T19:09:51.639944+00:00	Unavailable
Yanhan Zhou	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904707	245904707	-	0.00285	2026-10-12T19:09:44.432467+00:00	Unavailable
Yanhan Zhou	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904839	245904839	-	0.017785	2026-10-12T19:09:46.711391+00:00	Unavailable
Yanhan Zhou	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904971	245904971	-	0.040819	2026-10-12T19:09:47.805511+00:00	Unavailable
Yanhan Zhou	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905103	245905103	-	0.095003	2026-10-12T19:09:49.369336+00:00	Unavailable
Yanhan Zhou	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905235	245905235	-	0.48675	2026-10-12T19:09:51.639944+00:00	Unavailable
Ashun Wu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904728	245904728	-	0.001483	2026-10-12T19:09:44.432467+00:00	Unavailable
Ashun Wu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904860	245904860	-	0.01128	2026-10-12T19:09:46.711391+00:00	Unavailable
Ashun Wu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904992	245904992	-	0.030338	2026-10-12T19:09:47.805511+00:00	Unavailable
Ashun Wu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905124	245905124	-	0.079653	2026-10-12T19:09:49.369336+00:00	Unavailable
Ashun Wu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905256	245905256	-	0.4618	2026-10-12T19:09:51.639944+00:00	Unavailable
Alejandro Rodriguez Andreu	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904758	245904758	-	3.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Alejandro Rodriguez Andreu	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904890	245904890	-	0.000424	2026-10-12T19:09:46.711391+00:00	Unavailable
Alejandro Rodriguez Andreu	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905022	245905022	-	0.00156	2026-10-12T19:09:47.805511+00:00	Unavailable
Alejandro Rodriguez Andreu	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905154	245905154	-	0.005008	2026-10-12T19:09:49.369336+00:00	Unavailable
Alejandro Rodriguez Andreu	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905286	245905286	-	0.13615	2026-10-12T19:09:51.639944+00:00	Unavailable
Jose Luis Ballester	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904647	245904647	-	0.017333	2026-10-12T19:09:44.432467+00:00	Unavailable
Jose Luis Ballester	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904779	245904779	-	0.081861	2026-10-12T19:09:46.711391+00:00	Unavailable
Jose Luis Ballester	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904911	245904911	-	0.152616	2026-10-12T19:09:47.805511+00:00	Unavailable
Jose Luis Ballester	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905043	245905043	-	0.277925	2026-10-12T19:09:49.369336+00:00	Unavailable
Jose Luis Ballester	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905175	245905175	-	0.691467	2026-10-12T19:09:51.639944+00:00	Unavailable
Joe Dean	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904652	245904652	-	0.0117	2026-10-12T19:09:44.432467+00:00	Unavailable
Joe Dean	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904784	245904784	-	0.059781	2026-10-12T19:09:46.711391+00:00	Unavailable
Joe Dean	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904916	245904916	-	0.118362	2026-10-12T19:09:47.805511+00:00	Unavailable
Joe Dean	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905048	245905048	-	0.233003	2026-10-12T19:09:49.369336+00:00	Unavailable
Joe Dean	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905180	245905180	-	0.670283	2026-10-12T19:09:51.639944+00:00	Unavailable
Marco Penge	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904638	245904638	-	0.020267	2026-10-12T19:09:44.432467+00:00	Unavailable
Marco Penge	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904770	245904770	-	0.08799	2026-10-12T19:09:46.711391+00:00	Unavailable
Marco Penge	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904902	245904902	-	0.159816	2026-10-12T19:09:47.805511+00:00	Unavailable
Marco Penge	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905034	245905034	-	0.284603	2026-10-12T19:09:49.369336+00:00	Unavailable
Marco Penge	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905166	245905166	-	0.693767	2026-10-12T19:09:51.639944+00:00	Unavailable
Ludvig Aberg	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904629	245904629	-	0.113067	2026-10-12T19:09:44.432467+00:00	Unavailable
Ludvig Aberg	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904761	245904761	-	0.316914	2026-10-12T19:09:46.711391+00:00	Unavailable
Ludvig Aberg	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904893	245904893	-	0.457692	2026-10-12T19:09:47.805511+00:00	Unavailable
Ludvig Aberg	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905025	245905025	-	0.623582	2026-10-12T19:09:49.369336+00:00	Unavailable
Ludvig Aberg	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905157	245905157	-	0.881983	2026-10-12T19:09:51.639944+00:00	Unavailable
David Puig	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904636	245904636	-	0.021483	2026-10-12T19:09:44.432467+00:00	Unavailable
David Puig	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904768	245904768	-	0.097941	2026-10-12T19:09:46.711391+00:00	Unavailable
David Puig	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904900	245904900	-	0.180376	2026-10-12T19:09:47.805511+00:00	Unavailable
David Puig	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905032	245905032	-	0.320618	2026-10-12T19:09:49.369336+00:00	Unavailable
David Puig	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905164	245905164	-	0.737583	2026-10-12T19:09:51.639944+00:00	Unavailable
Matthew Jordan	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904648	245904648	-	0.014017	2026-10-12T19:09:44.432467+00:00	Unavailable
Matthew Jordan	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904780	245904780	-	0.068797	2026-10-12T19:09:46.711391+00:00	Unavailable
Matthew Jordan	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904912	245904912	-	0.136191	2026-10-12T19:09:47.805511+00:00	Unavailable
Matthew Jordan	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905044	245905044	-	0.25805	2026-10-12T19:09:49.369336+00:00	Unavailable
Matthew Jordan	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905176	245905176	-	0.6844	2026-10-12T19:09:51.639944+00:00	Unavailable
Sam Bairstow	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904651	245904651	-	0.01285	2026-10-12T19:09:44.432467+00:00	Unavailable
Sam Bairstow	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904783	245904783	-	0.066885	2026-10-12T19:09:46.711391+00:00	Unavailable
Sam Bairstow	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904915	245904915	-	0.131723	2026-10-12T19:09:47.805511+00:00	Unavailable
Sam Bairstow	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905047	245905047	-	0.251185	2026-10-12T19:09:49.369336+00:00	Unavailable
Sam Bairstow	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905179	245905179	-	0.685817	2026-10-12T19:09:51.639944+00:00	Unavailable
Calum Hill	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904657	245904657	-	0.009817	2026-10-12T19:09:44.432467+00:00	Unavailable
Calum Hill	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904789	245904789	-	0.052447	2026-10-12T19:09:46.711391+00:00	Unavailable
Calum Hill	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904921	245904921	-	0.107047	2026-10-12T19:09:47.805511+00:00	Unavailable
Calum Hill	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905053	245905053	-	0.21096	2026-10-12T19:09:49.369336+00:00	Unavailable
Calum Hill	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905185	245905185	-	0.641517	2026-10-12T19:09:51.639944+00:00	Unavailable
Thomas Rosenmueller	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904661	245904661	-	0.008417	2026-10-12T19:09:44.432467+00:00	Unavailable
Thomas Rosenmueller	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904793	245904793	-	0.04833	2026-10-12T19:09:46.711391+00:00	Unavailable
Thomas Rosenmueller	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904925	245904925	-	0.10139	2026-10-12T19:09:47.805511+00:00	Unavailable
Thomas Rosenmueller	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905057	245905057	-	0.204384	2026-10-12T19:09:49.369336+00:00	Unavailable
Thomas Rosenmueller	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905189	245905189	-	0.6435	2026-10-12T19:09:51.639944+00:00	Unavailable
Richard Mansell	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904662	245904662	-	0.008117	2026-10-12T19:09:44.432467+00:00	Unavailable
Richard Mansell	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904794	245904794	-	0.041166	2026-10-12T19:09:46.711391+00:00	Unavailable
Richard Mansell	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904926	245904926	-	0.084768	2026-10-12T19:09:47.805511+00:00	Unavailable
Richard Mansell	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905058	245905058	-	0.174981	2026-10-12T19:09:49.369336+00:00	Unavailable
Richard Mansell	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905190	245905190	-	0.6053	2026-10-12T19:09:51.639944+00:00	Unavailable
MJ Daffue	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904664	245904664	-	0.007867	2026-10-12T19:09:44.432467+00:00	Unavailable
MJ Daffue	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904796	245904796	-	0.043698	2026-10-12T19:09:46.711391+00:00	Unavailable
MJ Daffue	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904928	245904928	-	0.088705	2026-10-12T19:09:47.805511+00:00	Unavailable
MJ Daffue	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905060	245905060	-	0.181476	2026-10-12T19:09:49.369336+00:00	Unavailable
MJ Daffue	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905192	245905192	-	0.6023	2026-10-12T19:09:51.639944+00:00	Unavailable
Dan Brown	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904665	245904665	-	0.007833	2026-10-12T19:09:44.432467+00:00	Unavailable
Dan Brown	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904797	245904797	-	0.045591	2026-10-12T19:09:46.711391+00:00	Unavailable
Dan Brown	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904929	245904929	-	0.095907	2026-10-12T19:09:47.805511+00:00	Unavailable
Dan Brown	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905061	245905061	-	0.198971	2026-10-12T19:09:49.369336+00:00	Unavailable
Dan Brown	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905193	245905193	-	0.638017	2026-10-12T19:09:51.639944+00:00	Unavailable
Jeff Winther	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904671	245904671	-	0.006667	2026-10-12T19:09:44.432467+00:00	Unavailable
Jeff Winther	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904803	245904803	-	0.039909	2026-10-12T19:09:46.711391+00:00	Unavailable
Jeff Winther	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904935	245904935	-	0.085543	2026-10-12T19:09:47.805511+00:00	Unavailable
Jeff Winther	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905067	245905067	-	0.1827	2026-10-12T19:09:49.369336+00:00	Unavailable
Jeff Winther	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905199	245905199	-	0.627983	2026-10-12T19:09:51.639944+00:00	Unavailable
Alejandro Del Rey	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904677	245904677	-	0.006067	2026-10-12T19:09:44.432467+00:00	Unavailable
Alejandro Del Rey	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904809	245904809	-	0.036032	2026-10-12T19:09:46.711391+00:00	Unavailable
Alejandro Del Rey	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904941	245904941	-	0.07582	2026-10-12T19:09:47.805511+00:00	Unavailable
Alejandro Del Rey	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905073	245905073	-	0.157319	2026-10-12T19:09:49.369336+00:00	Unavailable
Alejandro Del Rey	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905205	245905205	-	0.5757	2026-10-12T19:09:51.639944+00:00	Unavailable
Paul Waring	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904684	245904684	-	0.0051	2026-10-12T19:09:44.432467+00:00	Unavailable
Paul Waring	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904816	245904816	-	0.02954	2026-10-12T19:09:46.711391+00:00	Unavailable
Paul Waring	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904948	245904948	-	0.063441	2026-10-12T19:09:47.805511+00:00	Unavailable
Paul Waring	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905080	245905080	-	0.13832	2026-10-12T19:09:49.369336+00:00	Unavailable
Paul Waring	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905212	245905212	-	0.54925	2026-10-12T19:09:51.639944+00:00	Unavailable
Brandon Stone	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904685	245904685	-	0.005083	2026-10-12T19:09:44.432467+00:00	Unavailable
Brandon Stone	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904817	245904817	-	0.03411	2026-10-12T19:09:46.711391+00:00	Unavailable
Brandon Stone	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904949	245904949	-	0.074531	2026-10-12T19:09:47.805511+00:00	Unavailable
Brandon Stone	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905081	245905081	-	0.159968	2026-10-12T19:09:49.369336+00:00	Unavailable
Brandon Stone	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905213	245905213	-	0.58685	2026-10-12T19:09:51.639944+00:00	Unavailable
Kazuma Kobori	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904689	245904689	-	0.0046	2026-10-12T19:09:44.432467+00:00	Unavailable
Kazuma Kobori	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904821	245904821	-	0.029274	2026-10-12T19:09:46.711391+00:00	Unavailable
Kazuma Kobori	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904953	245904953	-	0.067133	2026-10-12T19:09:47.805511+00:00	Unavailable
Kazuma Kobori	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905085	245905085	-	0.153313	2026-10-12T19:09:49.369336+00:00	Unavailable
Kazuma Kobori	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905217	245905217	-	0.592917	2026-10-12T19:09:51.639944+00:00	Unavailable
Bubba Watson	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904696	245904696	-	0.003867	2026-10-12T19:09:44.432467+00:00	Unavailable
Bubba Watson	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904828	245904828	-	0.025109	2026-10-12T19:09:46.711391+00:00	Unavailable
Bubba Watson	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904960	245904960	-	0.055701	2026-10-12T19:09:47.805511+00:00	Unavailable
Bubba Watson	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905092	245905092	-	0.127368	2026-10-12T19:09:49.369336+00:00	Unavailable
Bubba Watson	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905224	245905224	-	0.544917	2026-10-12T19:09:51.639944+00:00	Unavailable
Marcus Helligkilde	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904703	245904703	-	0.003417	2026-10-12T19:09:44.432467+00:00	Unavailable
Marcus Helligkilde	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904835	245904835	-	0.023702	2026-10-12T19:09:46.711391+00:00	Unavailable
Marcus Helligkilde	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904967	245904967	-	0.053001	2026-10-12T19:09:47.805511+00:00	Unavailable
Marcus Helligkilde	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905099	245905099	-	0.117436	2026-10-12T19:09:49.369336+00:00	Unavailable
Marcus Helligkilde	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905231	245905231	-	0.525783	2026-10-12T19:09:51.639944+00:00	Unavailable
Jeremy Paul	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904705	245904705	-	0.002917	2026-10-12T19:09:44.432467+00:00	Unavailable
Jeremy Paul	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904837	245904837	-	0.019604	2026-10-12T19:09:46.711391+00:00	Unavailable
Jeremy Paul	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904969	245904969	-	0.045138	2026-10-12T19:09:47.805511+00:00	Unavailable
Jeremy Paul	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905101	245905101	-	0.10779	2026-10-12T19:09:49.369336+00:00	Unavailable
Jeremy Paul	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905233	245905233	-	0.5117	2026-10-12T19:09:51.639944+00:00	Unavailable
Connor Syme	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904720	245904720	-	0.002	2026-10-12T19:09:44.432467+00:00	Unavailable
Connor Syme	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904852	245904852	-	0.014168	2026-10-12T19:09:46.711391+00:00	Unavailable
Connor Syme	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904984	245904984	-	0.035695	2026-10-12T19:09:47.805511+00:00	Unavailable
Connor Syme	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905116	245905116	-	0.087214	2026-10-12T19:09:49.369336+00:00	Unavailable
Connor Syme	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905248	245905248	-	0.473467	2026-10-12T19:09:51.639944+00:00	Unavailable
Alfredo Garcia-Heredia	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904736	245904736	-	0.0011	2026-10-12T19:09:44.432467+00:00	Unavailable
Alfredo Garcia-Heredia	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904868	245904868	-	0.007167	2026-10-12T19:09:46.711391+00:00	Unavailable
Alfredo Garcia-Heredia	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905000	245905000	-	0.018183	2026-10-12T19:09:47.805511+00:00	Unavailable
Alfredo Garcia-Heredia	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905132	245905132	-	0.048178	2026-10-12T19:09:49.369336+00:00	Unavailable
Alfredo Garcia-Heredia	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905264	245905264	-	0.3769	2026-10-12T19:09:51.639944+00:00	Unavailable
Michael Stewart	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904746	245904746	-	0.0006	2026-10-12T19:09:44.432467+00:00	Unavailable
Michael Stewart	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904878	245904878	-	0.005017	2026-10-12T19:09:46.711391+00:00	Unavailable
Michael Stewart	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905010	245905010	-	0.013368	2026-10-12T19:09:47.805511+00:00	Unavailable
Michael Stewart	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905142	245905142	-	0.038265	2026-10-12T19:09:49.369336+00:00	Unavailable
Michael Stewart	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905274	245905274	-	0.356567	2026-10-12T19:09:51.639944+00:00	Unavailable
Sergio Jimenez Romero	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904749	245904749	-	0.00035	2026-10-12T19:09:44.432467+00:00	Unavailable
Sergio Jimenez Romero	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904881	245904881	-	0.003787	2026-10-12T19:09:46.711391+00:00	Unavailable
Sergio Jimenez Romero	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905013	245905013	-	0.010282	2026-10-12T19:09:47.805511+00:00	Unavailable
Sergio Jimenez Romero	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905145	245905145	-	0.027939	2026-10-12T19:09:49.369336+00:00	Unavailable
Sergio Jimenez Romero	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905277	245905277	-	0.2934	2026-10-12T19:09:51.639944+00:00	Unavailable
David Micheluzzi	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904750	245904750	-	0.000317	2026-10-12T19:09:44.432467+00:00	Unavailable
David Micheluzzi	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904882	245904882	-	0.002544	2026-10-12T19:09:46.711391+00:00	Unavailable
David Micheluzzi	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905014	245905014	-	0.007094	2026-10-12T19:09:47.805511+00:00	Unavailable
David Micheluzzi	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905146	245905146	-	0.023587	2026-10-12T19:09:49.369336+00:00	Unavailable
David Micheluzzi	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905278	245905278	-	0.2816	2026-10-12T19:09:51.639944+00:00	Unavailable
Thomas Aiken	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904751	245904751	-	0.0003	2026-10-12T19:09:44.432467+00:00	Unavailable
Thomas Aiken	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904883	245904883	-	0.003504	2026-10-12T19:09:46.711391+00:00	Unavailable
Thomas Aiken	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905015	245905015	-	0.010077	2026-10-12T19:09:47.805511+00:00	Unavailable
Thomas Aiken	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905147	245905147	-	0.030867	2026-10-12T19:09:49.369336+00:00	Unavailable
Thomas Aiken	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905279	245905279	-	0.3157	2026-10-12T19:09:51.639944+00:00	Unavailable
Ockie Strydom	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904755	245904755	-	0.000133	2026-10-12T19:09:44.432467+00:00	Unavailable
Ockie Strydom	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904887	245904887	-	0.001336	2026-10-12T19:09:46.711391+00:00	Unavailable
Ockie Strydom	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905019	245905019	-	0.003697	2026-10-12T19:09:47.805511+00:00	Unavailable
Ockie Strydom	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905151	245905151	-	0.011372	2026-10-12T19:09:49.369336+00:00	Unavailable
Ockie Strydom	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905283	245905283	-	0.210567	2026-10-12T19:09:51.639944+00:00	Unavailable
Juan Salama	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904756	245904756	-	8.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Juan Salama	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904888	245904888	-	0.000693	2026-10-12T19:09:46.711391+00:00	Unavailable
Juan Salama	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905020	245905020	-	0.002037	2026-10-12T19:09:47.805511+00:00	Unavailable
Juan Salama	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905152	245905152	-	0.006062	2026-10-12T19:09:49.369336+00:00	Unavailable
Juan Salama	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905284	245905284	-	0.145583	2026-10-12T19:09:51.639944+00:00	Unavailable
Gonzalo Banos Ramos	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904757	245904757	-	8.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Gonzalo Banos Ramos	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904889	245904889	-	0.000553	2026-10-12T19:09:46.711391+00:00	Unavailable
Gonzalo Banos Ramos	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905021	245905021	-	0.001552	2026-10-12T19:09:47.805511+00:00	Unavailable
Gonzalo Banos Ramos	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905153	245905153	-	0.004908	2026-10-12T19:09:49.369336+00:00	Unavailable
Gonzalo Banos Ramos	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905285	245905285	-	0.132217	2026-10-12T19:09:51.639944+00:00	Unavailable
Daniel Gavins	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904759	245904759	-	3.3e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Daniel Gavins	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904891	245904891	-	0.000293	2026-10-12T19:09:46.711391+00:00	Unavailable
Daniel Gavins	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905023	245905023	-	0.000899	2026-10-12T19:09:47.805511+00:00	Unavailable
Daniel Gavins	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905155	245905155	-	0.003677	2026-10-12T19:09:49.369336+00:00	Unavailable
Daniel Gavins	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905287	245905287	-	0.122383	2026-10-12T19:09:51.639944+00:00	Unavailable
Sebastian Desoisa	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904760	245904760	-	1.7e-05	2026-10-12T19:09:44.432467+00:00	Unavailable
Sebastian Desoisa	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904892	245904892	-	0.00029	2026-10-12T19:09:46.711391+00:00	Unavailable
Sebastian Desoisa	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905024	245905024	-	0.001016	2026-10-12T19:09:47.805511+00:00	Unavailable
Sebastian Desoisa	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905156	245905156	-	0.003455	2026-10-12T19:09:49.369336+00:00	Unavailable
Sebastian Desoisa	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905288	245905288	-	0.109933	2026-10-12T19:09:51.639944+00:00	Unavailable
Wenyi Ding	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904742	245904742	-	0.000967	2026-10-12T19:09:44.432467+00:00	Unavailable
Wenyi Ding	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904874	245904874	-	0.00819	2026-10-12T19:09:46.711391+00:00	Unavailable
Wenyi Ding	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905006	245905006	-	0.020904	2026-10-12T19:09:47.805511+00:00	Unavailable
Wenyi Ding	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905138	245905138	-	0.055924	2026-10-12T19:09:49.369336+00:00	Unavailable
Wenyi Ding	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905270	245905270	-	0.4108	2026-10-12T19:09:51.639944+00:00	Unavailable
Sami Valimaki	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904660	245904660	-	0.008983	2026-10-12T19:09:44.432467+00:00	Unavailable
Sami Valimaki	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904792	245904792	-	0.049031	2026-10-12T19:09:46.711391+00:00	Unavailable
Sami Valimaki	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904924	245904924	-	0.099887	2026-10-12T19:09:47.805511+00:00	Unavailable
Sami Valimaki	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905056	245905056	-	0.202335	2026-10-12T19:09:49.369336+00:00	Unavailable
Sami Valimaki	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905188	245905188	-	0.628167	2026-10-12T19:09:51.639944+00:00	Unavailable
Victor Perez	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904642	245904642	-	0.019	2026-10-12T19:09:44.432467+00:00	Unavailable
Victor Perez	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904774	245904774	-	0.092361	2026-10-12T19:09:46.711391+00:00	Unavailable
Victor Perez	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904906	245904906	-	0.175374	2026-10-12T19:09:47.805511+00:00	Unavailable
Victor Perez	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905038	245905038	-	0.316319	2026-10-12T19:09:49.369336+00:00	Unavailable
Victor Perez	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905170	245905170	-	0.735817	2026-10-12T19:09:51.639944+00:00	Unavailable
Sergio Garcia	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904646	245904646	-	0.017833	2026-10-12T19:09:44.432467+00:00	Unavailable
Sergio Garcia	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904778	245904778	-	0.082572	2026-10-12T19:09:46.711391+00:00	Unavailable
Sergio Garcia	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904910	245904910	-	0.153286	2026-10-12T19:09:47.805511+00:00	Unavailable
Sergio Garcia	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905042	245905042	-	0.279331	2026-10-12T19:09:49.369336+00:00	Unavailable
Sergio Garcia	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905174	245905174	-	0.6957	2026-10-12T19:09:51.639944+00:00	Unavailable
Francesco Molinari	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904699	245904699	-	0.003533	2026-10-12T19:09:44.432467+00:00	Unavailable
Francesco Molinari	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904831	245904831	-	0.024189	2026-10-12T19:09:46.711391+00:00	Unavailable
Francesco Molinari	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904963	245904963	-	0.056466	2026-10-12T19:09:47.805511+00:00	Unavailable
Francesco Molinari	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905095	245905095	-	0.131929	2026-10-12T19:09:49.369336+00:00	Unavailable
Francesco Molinari	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905227	245905227	-	0.57155	2026-10-12T19:09:51.639944+00:00	Unavailable
Jacques Kruyswijk	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904737	245904737	-	0.001067	2026-10-12T19:09:44.432467+00:00	Unavailable
Jacques Kruyswijk	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904869	245904869	-	0.009338	2026-10-12T19:09:46.711391+00:00	Unavailable
Jacques Kruyswijk	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245905001	245905001	-	0.023005	2026-10-12T19:09:47.805511+00:00	Unavailable
Jacques Kruyswijk	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905133	245905133	-	0.063096	2026-10-12T19:09:49.369336+00:00	Unavailable
Jacques Kruyswijk	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905265	245905265	-	0.4488	2026-10-12T19:09:51.639944+00:00	Unavailable
Luke List	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904723	245904723	-	0.001667	2026-10-12T19:09:44.432467+00:00	Unavailable
Luke List	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904855	245904855	-	0.010765	2026-10-12T19:09:46.711391+00:00	Unavailable
Luke List	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904987	245904987	-	0.025368	2026-10-12T19:09:47.805511+00:00	Unavailable
Luke List	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905119	245905119	-	0.062314	2026-10-12T19:09:49.369336+00:00	Unavailable
Luke List	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905251	245905251	-	0.411333	2026-10-12T19:09:51.639944+00:00	Unavailable
Tyrrell Hatton	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904637	245904637	-	0.020883	2026-10-12T19:09:44.432467+00:00	Unavailable
Tyrrell Hatton	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904769	245904769	-	0.097079	2026-10-12T19:09:46.711391+00:00	Unavailable
Tyrrell Hatton	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904901	245904901	-	0.176277	2026-10-12T19:09:47.805511+00:00	Unavailable
Tyrrell Hatton	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905033	245905033	-	0.313891	2026-10-12T19:09:49.369336+00:00	Unavailable
Tyrrell Hatton	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905165	245905165	-	0.730883	2026-10-12T19:09:51.639944+00:00	Unavailable
Nicolai Hojgaard	Win	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391342|245904650	245904650	-	0.012917	2026-10-12T19:09:44.432467+00:00	Unavailable
Nicolai Hojgaard	Top 5	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391343|245904782	245904782	-	0.062987	2026-10-12T19:09:46.711391+00:00	Unavailable
Nicolai Hojgaard	Top 10	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391344|245904914	245904914	-	0.122432	2026-10-12T19:09:47.805511+00:00	Unavailable
Nicolai Hojgaard	Top 20	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391345|245905046	245905046	-	0.231002	2026-10-12T19:09:49.369336+00:00	Unavailable
Nicolai Hojgaard	Make cut	constructed:datagolf:euro:2026140:forecast-profile|datagolf|65391346|245905178	245905178	-	0.650267	2026-10-12T19:09:51.639944+00:00	Unavailable
"""#
