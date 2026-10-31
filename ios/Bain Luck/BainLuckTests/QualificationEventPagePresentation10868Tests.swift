import SwiftUI
import XCTest
@testable import Bain_Luck

/// #10868 — the `lacrosse-field` qualification props with no recorded prices:
/// the independent-qualification unavailable presentation, over the retained
/// capture of all 46 country qualification contracts.
///
/// PREPARED, NOT RUN. Only `xcrun swiftc -parse` was run on this file.
///
/// RETAINED DATA (evidence only, never an app binding): `qualification-
/// capture.json` (sha256 d4cfba4793549a5c4a630a1e9df9ce13539dd3e1db74978f2cca91c68fe5c81a)
/// under the approved `totals-final-forecast-binding-20261024/prototype/src/`.
/// Event KXSOLAXQUAL-28, "Which countries will qualify for LA28 men's
/// lacrosse?", mutuallyExclusive false, historyPoints 0, captured
/// 2026-10-15T22:06:40.887298+00:00. Every contract below is copied verbatim
/// from its `sourceRecord` in capture order — ticker, event_ticker,
/// yes_sub_title, title, rules_primary, status, result, volume_fp,
/// last_price_dollars — and all 46 share the one verbatim `rules_secondary`.
/// Each tuple can be matched against the capture on its own.
///
/// The owner words below are the approved native "Quiet" copy; the capture
/// time is the HOST's formatted words, passed through unchanged. The owner's
/// alphabetical order and the no-trade admission are the owner's: the fixture
/// orders and admits here, and the presentation only follows. The test-side
/// `retainedNoTrade` keeps the inherited model check (exact zero fields and
/// refusal after a trade, a grade, a status or an identity change) as a
/// receipt; it is not product source and nothing in the app calls it.
///
/// NOT claimed: native compilation or execution, rendered appearance, the
/// inherited eight overview/catalogue renders, presented sheets, Done, focus,
/// VoiceOver, phone/iPad/Mac reflow on a device, mounted app integration or a
/// host production-data binding. The hosted measurements below prove sizes
/// and that laying out calls nothing — not a visual acceptance.
@MainActor
final class QualificationEventPagePresentation10868Tests: XCTestCase {
    typealias Details = OriginalMarketDetails9483
    typealias Model = QualificationEventPageModel10868
    typealias Page = QualificationEventPagePresentation10868
    typealias Input = QualificationEventPageInput10868
    typealias Mode = QualificationEventPageMode10868
    typealias Notice = QualificationEventPageNotice10868
    typealias Link = QualificationEventPagePageLink10868
    typealias Window = QualificationEventPageWindow10868
    typealias Row = LadderOriginalProbabilityDetails9483.Row

    // MARK: Retained capture, verbatim

    struct Contract: Equatable {
        let ticker: String
        let eventTicker: String
        let name: String
        let predicate: String
        let primary: String
        let status: String
        let result: String
        let volume: String
        let lastPrice: String
    }

    static func c(_ ticker: String, _ eventTicker: String, _ name: String, _ predicate: String,
                  _ primary: String, _ status: String, _ result: String, _ volume: String,
                  _ lastPrice: String) -> Contract {
        Contract(ticker: ticker, eventTicker: eventTicker, name: name, predicate: predicate, primary: primary,
                 status: status, result: result, volume: volume, lastPrice: lastPrice)
    }

    static let event = "KXSOLAXQUAL-28"
    static let eventName = "Which countries will qualify for LA28 men's lacrosse?"
    static let mutuallyExclusive = false
    static let capturedAt = "2026-10-15T22:06:40.887298+00:00"
    static let historyPoints = 0

    /// The one `rules_secondary` every contract carries, verbatim.
    static let secondaryRule = "Qualification means that the country’s National Olympic Committee (NOC) receives and accepts a place in the Men’s Lacrosse competition at the Los Angeles 2028 Olympic Games.\n\nKalshi is not affiliated, associated, authorized, endorsed by, or in any way officially connected with the International Olympic Committee, World Lacrosse, or Los Angeles 2028 Organizing Committee. All trademarks, logos, and brand names are the property of their respective owners."

    /// All 46 contracts in capture order.
    static let contracts: [Contract] = [
        c("KXSOLAXQUAL-28-BRA", "KXSOLAXQUAL-28", "Brazil", "Will Brazil qualify for LA28 men's lacrosse?",
          "If Brazil achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-CAN", "KXSOLAXQUAL-28", "Canada", "Will Canada qualify for LA28 men's lacrosse?",
          "If Canada achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-CHI", "KXSOLAXQUAL-28", "Chile", "Will Chile qualify for LA28 men's lacrosse?",
          "If Chile achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-JAM", "KXSOLAXQUAL-28", "Jamaica", "Will Jamaica qualify for LA28 men's lacrosse?",
          "If Jamaica achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-MEX", "KXSOLAXQUAL-28", "Mexico", "Will Mexico qualify for LA28 men's lacrosse?",
          "If Mexico achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-PUR", "KXSOLAXQUAL-28", "Puerto Rico", "Will Puerto Rico qualify for LA28 men's lacrosse?",
          "If Puerto Rico achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-AUS", "KXSOLAXQUAL-28", "Australia", "Will Australia qualify for LA28 men's lacrosse?",
          "If Australia achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-CHN", "KXSOLAXQUAL-28", "China", "Will China qualify for LA28 men's lacrosse?",
          "If China achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-TPE", "KXSOLAXQUAL-28", "Chinese Taipei", "Will Chinese Taipei qualify for LA28 men's lacrosse?",
          "If Chinese Taipei achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-HKG", "KXSOLAXQUAL-28", "Hong Kong, China", "Will Hong Kong, China qualify for LA28 men's lacrosse?",
          "If Hong Kong, China achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-IND", "KXSOLAXQUAL-28", "India", "Will India qualify for LA28 men's lacrosse?",
          "If India achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-JPN", "KXSOLAXQUAL-28", "Japan", "Will Japan qualify for LA28 men's lacrosse?",
          "If Japan achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-NZL", "KXSOLAXQUAL-28", "New Zealand", "Will New Zealand qualify for LA28 men's lacrosse?",
          "If New Zealand achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-PHI", "KXSOLAXQUAL-28", "Philippines", "Will Philippines qualify for LA28 men's lacrosse?",
          "If Philippines achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-KSA", "KXSOLAXQUAL-28", "Saudi Arabia", "Will Saudi Arabia qualify for LA28 men's lacrosse?",
          "If Saudi Arabia achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-SGP", "KXSOLAXQUAL-28", "Singapore", "Will Singapore qualify for LA28 men's lacrosse?",
          "If Singapore achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-KOR", "KXSOLAXQUAL-28", "South Korea", "Will South Korea qualify for LA28 men's lacrosse?",
          "If South Korea achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-AUT", "KXSOLAXQUAL-28", "Austria", "Will Austria qualify for LA28 men's lacrosse?",
          "If Austria achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-BEL", "KXSOLAXQUAL-28", "Belgium", "Will Belgium qualify for LA28 men's lacrosse?",
          "If Belgium achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-CRO", "KXSOLAXQUAL-28", "Croatia", "Will Croatia qualify for LA28 men's lacrosse?",
          "If Croatia achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-CZE", "KXSOLAXQUAL-28", "Czechia", "Will Czechia qualify for LA28 men's lacrosse?",
          "If Czechia achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-DEN", "KXSOLAXQUAL-28", "Denmark", "Will Denmark qualify for LA28 men's lacrosse?",
          "If Denmark achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-FIN", "KXSOLAXQUAL-28", "Finland", "Will Finland qualify for LA28 men's lacrosse?",
          "If Finland achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-FRA", "KXSOLAXQUAL-28", "France", "Will France qualify for LA28 men's lacrosse?",
          "If France achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-GER", "KXSOLAXQUAL-28", "Germany", "Will Germany qualify for LA28 men's lacrosse?",
          "If Germany achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-GBR", "KXSOLAXQUAL-28", "Great Britain", "Will Great Britain qualify for LA28 men's lacrosse?",
          "If Great Britain achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-GRE", "KXSOLAXQUAL-28", "Greece", "Will Greece qualify for LA28 men's lacrosse?",
          "If Greece achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-HUN", "KXSOLAXQUAL-28", "Hungary", "Will Hungary qualify for LA28 men's lacrosse?",
          "If Hungary achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-IRL", "KXSOLAXQUAL-28", "Ireland", "Will Ireland qualify for LA28 men's lacrosse?",
          "If Ireland achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-ISR", "KXSOLAXQUAL-28", "Israel", "Will Israel qualify for LA28 men's lacrosse?",
          "If Israel achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-ITA", "KXSOLAXQUAL-28", "Italy", "Will Italy qualify for LA28 men's lacrosse?",
          "If Italy achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-LAT", "KXSOLAXQUAL-28", "Latvia", "Will Latvia qualify for LA28 men's lacrosse?",
          "If Latvia achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-NED", "KXSOLAXQUAL-28", "Netherlands", "Will Netherlands qualify for LA28 men's lacrosse?",
          "If Netherlands achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-NOR", "KXSOLAXQUAL-28", "Norway", "Will Norway qualify for LA28 men's lacrosse?",
          "If Norway achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-POL", "KXSOLAXQUAL-28", "Poland", "Will Poland qualify for LA28 men's lacrosse?",
          "If Poland achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-POR", "KXSOLAXQUAL-28", "Portugal", "Will Portugal qualify for LA28 men's lacrosse?",
          "If Portugal achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-SVK", "KXSOLAXQUAL-28", "Slovakia", "Will Slovakia qualify for LA28 men's lacrosse?",
          "If Slovakia achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-ESP", "KXSOLAXQUAL-28", "Spain", "Will Spain qualify for LA28 men's lacrosse?",
          "If Spain achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-SWE", "KXSOLAXQUAL-28", "Sweden", "Will Sweden qualify for LA28 men's lacrosse?",
          "If Sweden achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-SUI", "KXSOLAXQUAL-28", "Switzerland", "Will Switzerland qualify for LA28 men's lacrosse?",
          "If Switzerland achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-TUR", "KXSOLAXQUAL-28", "Türkiye", "Will Türkiye qualify for LA28 men's lacrosse?",
          "If Türkiye achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-CIV", "KXSOLAXQUAL-28", "Côte d’Ivoire", "Will Côte d’Ivoire qualify for LA28 men's lacrosse?",
          "If Côte d’Ivoire achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-GHA", "KXSOLAXQUAL-28", "Ghana", "Will Ghana qualify for LA28 men's lacrosse?",
          "If Ghana achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-KEN", "KXSOLAXQUAL-28", "Kenya", "Will Kenya qualify for LA28 men's lacrosse?",
          "If Kenya achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-RSA", "KXSOLAXQUAL-28", "South Africa", "Will South Africa qualify for LA28 men's lacrosse?",
          "If South Africa achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
        c("KXSOLAXQUAL-28-UGA", "KXSOLAXQUAL-28", "Uganda", "Will Uganda qualify for LA28 men's lacrosse?",
          "If Uganda achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.",
          "active", "", "0.00", "0.0000"),
    ]

    /// TEST-SIDE ONLY — the inherited model check, kept as the receipt that
    /// the retained capture is exactly the no-trade one. Never product source.
    static func retainedNoTrade(_ contracts: [Contract]) -> Bool {
        contracts.count == 46 && Set(contracts.map(\.ticker)).count == 46 && contracts.allSatisfy {
            $0.eventTicker == event && $0.status == "active" && $0.result.isEmpty
                && $0.volume == "0.00" && $0.lastPrice == "0.0000"
        }
    }

    // MARK: Owner fixture

    static let scope = "kalshi:KXSOLAXQUAL-28"
    /// The host's formatted capture time.
    static let captured = "Oct 15, 2026, 3:06 PM PDT"

    static let overview = QualificationEventPageOverview10868(
        eyebrow: "Qualification", title: "LA28 men’s lacrosse", aboutLabel: "About qualification probabilities",
        headline: "No recorded probabilities",
        absence: ["No trades recorded in this capture.", "Pre-event chance · unavailable"],
        meaning: "More than one country can qualify.", allPropsLabel: "Explore all 46 country props",
        aboutHint: "Opens what these props mean")
    static let browse = QualificationEventPageBrowse10868(
        overviewLabel: "Overview", heading: "46 country props",
        context: "No recorded probabilities · alphabetical order", gridLabel: "Country props",
        unavailableChoice: "Country unavailable")
    static let propCopy = QualificationEventPagePropCopy10868(
        headline: "No recorded probability",
        absence: ["No trades recorded in this capture.", "Pre-event chance · unavailable",
                  "Qualification result · unconfirmed"],
        rulesLabel: "Rules", sourceLabel: "Source",
        note: "A zero value without a recorded trade does not establish a 0% chance. Bid and ask fields are not verified probabilities.")
    static let about = FieldEventPageAbout10868(title: "About these qualification props", paragraphs: [
        "More than one country can qualify. Each prop is about one country's qualification; these are not shares of a single winner.",
        "All 46 Kalshi contracts report zero traded volume in the capture from \(captured). No probability history or pre-event chance is available. A zero value without a recorded trade does not establish a 0% chance.",
        "No qualification results, sporting start time, standings or projections are established by these records. The scheduled market close is not the tournament start.",
    ])
    static let entry = "Explore all 46 country props"
    static let invalidatedPage = Notice(title: "This captured state is unavailable.", words: nil)
    static let invalidatedDetails = Notice(
        title: "Details unavailable",
        words: "These recorded details are no longer available. Close to return to the event.")
    static let propUnavailable = Notice(
        title: "Country prop unavailable", words: "Close these details and choose a country from the event.")

    static func identity(_ contract: Contract) -> Details.Identity {
        Details.Identity(source: "kalshi", market: contract.ticker, side: "yes")
    }

    static func selection(_ contract: Contract) -> Details.Selection {
        Details.Selection(scope: scope, identity: identity(contract))
    }

    static func original(_ contract: Contract) -> Details.Original {
        Details.Original(
            identity: identity(contract), title: contract.predicate, outcome: contract.name, mode: .pregame,
            pregame: .missing("unavailable"), later: nil, grade: nil,
            about: Details.About(source: "Kalshi", rules: .verified([contract.primary, secondaryRule]),
                                 provenance: [Row(label: "Contract", value: contract.ticker),
                                              Row(label: "Captured", value: captured)],
                                 historicalQuote: nil))
    }

    static func prop(_ contract: Contract) -> QualificationEventPageProp10868 {
        QualificationEventPageProp10868(
            selection: selection(contract), name: contract.name, predicate: contract.predicate,
            rules: .verified([contract.primary, secondaryRule]), source: "Kalshi",
            provenance: [Row(label: "Contract", value: contract.ticker), Row(label: "Captured", value: captured)])
    }

    /// The owner's alphabetical order, as the owner supplies it.
    static var alphabetical: [Contract] {
        contracts.sorted { $0.name.localizedStandardCompare($1.name) == .orderedAscending }
    }

    static func named(_ name: String) -> Contract {
        contracts.first { $0.name == name }!
    }

    static func input(_ order: [Contract]? = nil, originals: [Details.Original]? = nil,
                      validity: QualificationEventPageValidity10868 = .qualified,
                      selection: Details.Selection? = nil, window: Window? = nil,
                      aboutCatalogueLabel: String? = QualificationEventPagePresentation10868Tests.entry) -> Input {
        let order = order ?? alphabetical
        return Input(
            validity: validity,
            catalogue: Details.Catalogue(scope: scope, originals: originals ?? order.map { original($0) }),
            labels: Dictionary(contracts.map { (identity($0), $0.name) }, uniquingKeysWith: { first, _ in first }),
            selection: selection, overview: overview, browse: browse, prop: propCopy, about: about,
            aboutCatalogueLabel: aboutCatalogueLabel, invalidatedPage: invalidatedPage,
            invalidatedDetails: invalidatedDetails, propUnavailable: propUnavailable, window: window)
    }

    /// Every callback and the hook, recorded in call order.
    final class Log {
        var events: [String] = []
    }

    static func page(_ input: Input, _ mode: Mode, log: Log, hook: Bool = true) -> Page {
        Page(input: input, mode: mode,
             onAbout: { log.events.append("about") },
             onCatalogue: { log.events.append("catalogue") },
             onOverview: { log.events.append("overview") },
             onPage: { log.events.append("page:\($0)") },
             onSelect: { log.events.append(selectEvent($0)) },
             onInteraction: hook ? { log.events.append("hold") } : nil)
    }

    static func selectEvent(_ selection: Details.Selection) -> String {
        "select:\(selection.scope)|\(selection.identity.source)|\(selection.identity.market)|\(selection.identity.side)"
    }

    static func selectEvent(_ contract: Contract) -> String {
        selectEvent(selection(contract))
    }

    /// The actions a page offers, by name.
    static func actions(_ page: Page) -> Set<String> {
        var names: Set<String> = []
        if page.aboutAction() != nil { names.insert("about") }
        if page.allPropsAction() != nil { names.insert("allProps") }
        if page.overviewAction() != nil { names.insert("overview") }
        if page.pageAction(page.model.previous) != nil { names.insert("previous") }
        if page.pageAction(page.model.next) != nil { names.insert("next") }
        if page.model.choices.contains(where: { page.selectAction($0) != nil }) { names.insert("rows") }
        if page.aboutCatalogueAction() != nil { names.insert("aboutCatalogue") }
        return names
    }

    static var headerWords: [String] {
        ["Qualification", "LA28 men’s lacrosse", "No recorded probabilities", "No trades recorded in this capture.",
         "Pre-event chance · unavailable", "More than one country can qualify."]
    }

    static func propWords(_ contract: Contract) -> [String] {
        [contract.name, contract.predicate, "No recorded probability", "No trades recorded in this capture.",
         "Pre-event chance · unavailable", "Qualification result · unconfirmed", "Rules", contract.primary,
         secondaryRule, "Source", "Kalshi", "Contract", contract.ticker, "Captured", captured,
         "A zero value without a recorded trade does not establish a 0% chance. Bid and ask fields are not verified probabilities."]
    }

    static var aboutWords: [String] { [about.title] + about.paragraphs }

    static func measure<V: View>(_ view: V, width: CGFloat, size: DynamicTypeSize) -> CGSize {
        let host = hostForMeasurement(view.frame(width: width).fixedSize(horizontal: false, vertical: true), at: size)
        host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
        host.view.setNeedsLayout()
        host.view.layoutIfNeeded()
        return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
    }

    // MARK: The retained receipt

    func testTheRetainedCaptureKeepsAll46ContractsTheirRulesAndEveryZeroField() {
        XCTAssertEqual(Self.event, "KXSOLAXQUAL-28")
        XCTAssertEqual(Self.eventName, "Which countries will qualify for LA28 men's lacrosse?")
        XCTAssertFalse(Self.mutuallyExclusive, "several countries can qualify")
        XCTAssertEqual(Self.historyPoints, 0)
        XCTAssertEqual(Self.capturedAt, "2026-10-15T22:06:40.887298+00:00")
        XCTAssertEqual(Self.contracts.count, 46)
        XCTAssertEqual(Set(Self.contracts.map(\.ticker)).count, 46)
        XCTAssertEqual(Set(Self.contracts.map(\.name)).count, 46)
        for contract in Self.contracts {
            XCTAssertEqual(contract.eventTicker, Self.event, contract.ticker)
            XCTAssertTrue(contract.ticker.hasPrefix(Self.event + "-"), contract.ticker)
            XCTAssertEqual(contract.status, "active", contract.ticker)
            XCTAssertEqual(contract.result, "", contract.ticker)
            XCTAssertEqual(contract.volume, "0.00", contract.ticker)
            XCTAssertEqual(contract.lastPrice, "0.0000", contract.ticker)
            // Name, predicate and primary rule bind one another in every tuple.
            XCTAssertEqual(contract.predicate, "Will \(contract.name) qualify for LA28 men's lacrosse?")
            XCTAssertEqual(contract.primary,
                           "If \(contract.name) achieves qualification in the Men's Lacrosse competition for the Los Angeles 2028 Olympic Games, then the market resolves to Yes.")
        }
        XCTAssertTrue(Self.secondaryRule.hasPrefix(
            "Qualification means that the country’s National Olympic Committee (NOC) receives and accepts a place in the Men’s Lacrosse competition"))
        XCTAssertTrue(Self.secondaryRule.contains(".\n\nKalshi is not affiliated, associated, authorized, endorsed by"))
        XCTAssertEqual(Self.secondaryRule.count, 456)
        XCTAssertEqual(Self.contracts.first?.ticker, "KXSOLAXQUAL-28-BRA")
        XCTAssertEqual(Self.contracts.last?.ticker, "KXSOLAXQUAL-28-UGA")
        XCTAssertEqual(Self.named("Hong Kong, China").ticker, "KXSOLAXQUAL-28-HKG")
        XCTAssertEqual(Self.named("Côte d’Ivoire").ticker, "KXSOLAXQUAL-28-CIV")
        XCTAssertEqual(Self.named("Türkiye").ticker, "KXSOLAXQUAL-28-TUR")

        // The inherited refusal checks, test-side: one trade, grade, status or
        // identity change and the capture is no longer the no-trade one.
        XCTAssertTrue(Self.retainedNoTrade(Self.contracts))
        let first = Self.contracts[0]
        let rest = Array(Self.contracts.dropFirst())
        let changed = [
            Self.c(first.ticker, first.eventTicker, first.name, first.predicate, first.primary, first.status, first.result, "1.00", first.lastPrice),
            Self.c(first.ticker, first.eventTicker, first.name, first.predicate, first.primary, first.status, "yes", first.volume, first.lastPrice),
            Self.c(first.ticker, first.eventTicker, first.name, first.predicate, first.primary, "settled", first.result, first.volume, first.lastPrice),
            Self.c(first.ticker, "OTHER", first.name, first.predicate, first.primary, first.status, first.result, first.volume, first.lastPrice),
            Self.c(first.ticker, first.eventTicker, first.name, first.predicate, first.primary, first.status, first.result, first.volume, ".5"),
        ]
        for contract in changed {
            XCTAssertFalse(Self.retainedNoTrade([contract] + rest), "\(contract)")
        }
        XCTAssertFalse(Self.retainedNoTrade(rest), "45 contracts")
        XCTAssertFalse(Self.retainedNoTrade([rest[0]] + rest), "a duplicated contract")
    }

    // MARK: Catalogue rows

    func testEveryContractIsARowInTheOwnersOrderAndOpensItsExactIdentity() throws {
        for order in [Self.alphabetical, Self.contracts] {
            let choices = Model(Self.input(order)).choices
            XCTAssertEqual(choices.map(\.label), order.map(\.name), "the owner's order, never re-sorted")
            XCTAssertEqual(choices.map(\.selection), order.map { Optional(Self.selection($0)) })
            XCTAssertTrue(choices.allSatisfy { $0.status == nil && !$0.isSelected })
        }
        let alphabetical = Self.alphabetical
        XCTAssertEqual(alphabetical.first?.name, "Australia")
        XCTAssertEqual(alphabetical.last?.name, "Uganda")

        let log = Log()
        let page = Self.page(Self.input(), .catalogue, log: log)
        let choices = page.model.choices
        XCTAssertEqual(choices.count, 46)
        XCTAssertTrue(log.events.isEmpty, "building and reading call nothing")
        try XCTUnwrap(page.selectAction(choices[0]))()
        try XCTUnwrap(page.selectAction(choices[45]))()
        XCTAssertEqual(log.events, ["hold", Self.selectEvent(alphabetical[0]), "hold", Self.selectEvent(alphabetical[45])])

        let words = page.shownWords()
        for name in ["Hong Kong, China", "Côte d’Ivoire", "Türkiye", "Uganda", "Chinese Taipei"] {
            XCTAssertEqual(words.filter { $0 == name }.count, 1, "\(name) shows whole, once")
        }

        let held = Model(Self.input(selection: Self.selection(Self.named("Uganda")))).choices
        XCTAssertEqual(held.filter(\.isSelected).map(\.label), ["Uganda"])
    }

    // MARK: Each mode's content

    func testEachPropShowsItsPredicateTheAbsenceAndBothRulesVerbatimWithItsOwnSourceAndCapture() {
        for contract in Self.contracts {
            let input = Self.input(selection: Self.selection(contract))
            XCTAssertEqual(Model(input).content(.prop), .prop(Self.prop(contract)), contract.ticker)
            let log = Log()
            let page = Self.page(input, .prop, log: log)
            let words = page.shownWords()
            XCTAssertEqual(words, Self.propWords(contract), contract.ticker)
            XCTAssertTrue(Self.actions(page).isEmpty, contract.ticker)
            XCTAssertTrue(log.events.isEmpty)
            for other in Self.contracts where other != contract {
                XCTAssertFalse(words.contains(other.ticker), "\(contract.ticker) borrows \(other.ticker)")
                XCTAssertFalse(words.contains(other.primary), "\(contract.ticker) borrows \(other.ticker)")
                XCTAssertFalse(words.contains(other.name), "\(contract.ticker) borrows \(other.ticker)")
            }
        }
    }

    func testTheOverviewShowsTheAbsenceTheMeaningAndOneEntryOnly() {
        let log = Log()
        let page = Self.page(Self.input(selection: Self.selection(Self.named("Brazil"))), .overview, log: log)
        XCTAssertEqual(page.model.content(.overview), .overview)
        XCTAssertEqual(page.shownWords(), Self.headerWords + ["Explore all 46 country props"])
        XCTAssertEqual(Self.actions(page), ["about", "allProps"])
        XCTAssertTrue(log.events.isEmpty)
    }

    func testTheCatalogueShowsTheHeadingContextOverviewActionAndEveryRowOnly() {
        let log = Log()
        let page = Self.page(Self.input(), .catalogue, log: log)
        XCTAssertEqual(page.shownWords(),
                       Self.headerWords + ["Overview", "46 country props", "No recorded probabilities · alphabetical order"]
                           + Self.alphabetical.map(\.name))
        XCTAssertEqual(Self.actions(page), ["about", "overview", "rows"])
        XCTAssertTrue(log.events.isEmpty)
    }

    func testTheAboutShowsTheOwnersMeaningAndCaptureWordsWithTheExactCatalogueEntry() throws {
        let log = Log()
        let page = Self.page(Self.input(), .about, log: log)
        XCTAssertEqual(page.model.content(.about), .about)
        XCTAssertEqual(page.shownWords(), Self.aboutWords + [Self.entry])
        XCTAssertEqual(Self.actions(page), ["aboutCatalogue"])
        try XCTUnwrap(page.aboutCatalogueAction())()
        XCTAssertEqual(log.events, ["catalogue"], "the full reader keeps the exact callback, no hold")

        let without = Self.page(Self.input(aboutCatalogueLabel: nil), .about, log: log)
        XCTAssertNil(without.aboutCatalogueAction())
        XCTAssertEqual(without.shownWords(), Self.aboutWords)
    }

    // MARK: Isolation

    func testEachModeShowsOnlyItsOwnContentAndActions() {
        let brazil = Self.named("Brazil")
        let input = Self.input(selection: Self.selection(brazil))
        let expected: [Mode: (words: [String], actions: Set<String>)] = [
            .overview: (Self.headerWords + [Self.overview.allPropsLabel], ["about", "allProps"]),
            .catalogue: (Self.headerWords + ["Overview", "46 country props", "No recorded probabilities · alphabetical order"]
                + Self.alphabetical.map(\.name), ["about", "overview", "rows"]),
            .prop: (Self.propWords(brazil), []),
            .about: (Self.aboutWords + [Self.entry], ["aboutCatalogue"]),
        ]
        for mode in Mode.allCases {
            let page = Self.page(input, mode, log: Log())
            XCTAssertEqual(page.shownWords(), expected[mode]?.words, "\(mode)")
            XCTAssertEqual(Self.actions(page), expected[mode]?.actions, "\(mode)")
        }
        // No mode carries another's details.
        let prop = Set(Self.propWords(brazil)).subtracting(["No trades recorded in this capture.", "Pre-event chance · unavailable"])
        for mode in [Mode.overview, .catalogue, .about] {
            let words = Set(Self.page(input, mode, log: Log()).shownWords())
            XCTAssertTrue(words.isDisjoint(with: prop.subtracting(mode == .catalogue ? ["Brazil"] : Set<String>())), "\(mode)")
            XCTAssertTrue(words.isDisjoint(with: [Self.secondaryRule, brazil.primary, brazil.ticker]), "\(mode)")
        }
        XCTAssertTrue(Set(Self.page(input, .prop, log: Log()).shownWords()).isDisjoint(with: Self.aboutWords))
        XCTAssertTrue(Set(Self.page(input, .about, log: Log()).shownWords()).isDisjoint(with: Self.alphabetical.map(\.name)))
    }

    // MARK: Selections that must not open

    func testUnknownDuplicateForeignAndMissingSelectionsNeverFallThroughToAboutOrANeighbour() {
        let brazil = Self.named("Brazil")
        let neighbours = Self.contracts.filter { $0 != brazil }
        let forbidden = Set(Self.aboutWords + Self.contracts.flatMap { [$0.name, $0.predicate, $0.primary, $0.ticker] }
                            + Model.words(Self.invalidatedDetails))
        let cases: [(String, Input, Model.Unavailable)] = [
            ("omitted", Self.input(selection: nil), .omitted),
            ("unknown", Self.input(selection: Details.Selection(
                scope: Self.scope, identity: Details.Identity(source: "kalshi", market: "KXSOLAXQUAL-28-ZZZ", side: "yes"))), .unresolved),
            ("foreign scope", Self.input(selection: Details.Selection(scope: "kalshi:OTHER", identity: Self.identity(brazil))), .unresolved),
            ("other side", Self.input(selection: Details.Selection(
                scope: Self.scope, identity: Details.Identity(source: "kalshi", market: brazil.ticker, side: "no"))), .unresolved),
            ("blank market", Self.input(selection: Details.Selection(
                scope: Self.scope, identity: Details.Identity(source: "kalshi", market: " ", side: "yes"))), .unresolved),
            ("missing from the frame", Self.input(neighbours, selection: Self.selection(brazil)), .unresolved),
            ("duplicated", Self.input([brazil] + Self.alphabetical, selection: Self.selection(brazil)), .unresolved),
        ]
        for (name, input, reason) in cases {
            let page = Self.page(input, .prop, log: Log())
            XCTAssertEqual(page.model.content(.prop), .propUnavailable(reason), name)
            let words = page.shownWords()
            XCTAssertEqual(words, Model.words(Self.propUnavailable), name)
            XCTAssertTrue(Set(words).isDisjoint(with: forbidden), name)
            XCTAssertTrue(Self.actions(page).isEmpty, name)
        }

        // A duplicated original is unavailable in the grid too; its neighbours keep theirs.
        let log = Log()
        let page = Self.page(Self.input([brazil] + Self.alphabetical), .catalogue, log: log)
        let rows = page.model.choices
        let brazilRows = rows.filter { $0.label == "Brazil" }
        XCTAssertEqual(brazilRows.count, 2)
        XCTAssertTrue(brazilRows.allSatisfy { $0.selection == nil && $0.status == OriginalMarketChooser9483.unavailableStatus })
        XCTAssertTrue(brazilRows.allSatisfy { page.selectAction($0) == nil })
        let others = rows.filter { $0.label != "Brazil" }
        XCTAssertEqual(others.map(\.selection), Self.alphabetical.filter { $0 != brazil }.map { Optional(Self.selection($0)) })
        XCTAssertTrue(others.allSatisfy { page.selectAction($0) != nil })
        XCTAssertTrue(log.events.isEmpty)
    }

    // MARK: Invalidation

    func testInvalidationSuppressesEveryModeAndKeepsOnlyTheOwnersWords() {
        let brazil = Self.named("Brazil")
        let qualified = Self.input(selection: Self.selection(brazil))
        let invalidated = Self.input(validity: .invalidated, selection: Self.selection(brazil))
        var old: Set<String> = []
        for mode in Mode.allCases {
            old.formUnion(Self.page(qualified, mode, log: Log()).shownWords())
        }
        let log = Log()
        for mode in Mode.allCases {
            let page = Self.page(invalidated, mode, log: log)
            let notice = mode == .overview || mode == .catalogue ? Self.invalidatedPage : Self.invalidatedDetails
            XCTAssertEqual(page.model.content(mode), .invalidated(notice), "\(mode)")
            XCTAssertEqual(page.shownWords(), Model.words(notice), "\(mode)")
            XCTAssertTrue(Set(page.shownWords()).isDisjoint(with: old), "\(mode) keeps an old word")
            XCTAssertTrue(Self.actions(page).isEmpty, "\(mode) keeps an old action")
            XCTAssertTrue(page.model.choices.allSatisfy { page.selectAction($0) == nil }, "\(mode)")
        }
        XCTAssertTrue(log.events.isEmpty)
        // Invalidated is not an omitted selection, and an omitted selection is not invalidated.
        XCTAssertNotEqual(Model(invalidated).content(.prop), Model(Self.input(selection: nil)).content(.prop))
        XCTAssertNotEqual(Model.words(Self.invalidatedDetails), Model.words(Self.propUnavailable))
        XCTAssertEqual(Model(Self.input(validity: .invalidated, selection: nil)).content(.prop),
                       .invalidated(Self.invalidatedDetails))
    }

    func testOpeningAboutOrAPropThenInvalidatingShowsNoOldDetailAndRequalifyingRestoresTheExactProp() {
        let hongKong = Self.named("Hong Kong, China")
        let held = Self.selection(hongKong)
        let frames: [QualificationEventPageValidity10868] = [.qualified, .invalidated, .qualified]
        var propWords: [[String]] = []
        var aboutWords: [[String]] = []
        for validity in frames {
            propWords.append(Self.page(Self.input(validity: validity, selection: held), .prop, log: Log()).shownWords())
            aboutWords.append(Self.page(Self.input(validity: validity, selection: held), .about, log: Log()).shownWords())
        }
        XCTAssertEqual(propWords[0], Self.propWords(hongKong))
        XCTAssertEqual(propWords[1], Model.words(Self.invalidatedDetails))
        XCTAssertEqual(propWords[2], propWords[0], "the same exact prop, not a neighbour")
        XCTAssertEqual(aboutWords[0], Self.aboutWords + [Self.entry])
        XCTAssertEqual(aboutWords[1], Model.words(Self.invalidatedDetails))
        XCTAssertEqual(aboutWords[2], aboutWords[0])
        XCTAssertEqual(Model(Self.input(validity: .qualified, selection: held)).content(.prop), .prop(Self.prop(hongKong)))
    }

    // MARK: Held frames

    func testAHeldSelectionOmittedFromAFrameIsUnavailableAndItsRestorationReopensTheSameExactProp() {
        let uganda = Self.named("Uganda")
        let held = Self.selection(uganda)
        let first = Model(Self.input(selection: held)).content(.prop)
        XCTAssertEqual(first, .prop(Self.prop(uganda)))

        // A received frame without that original: unavailable, never the row now at its place.
        let without = Self.alphabetical.filter { $0 != uganda }
        let omitted = Self.page(Self.input(without, selection: held), .prop, log: Log())
        XCTAssertEqual(omitted.model.content(.prop), .propUnavailable(.unresolved))
        XCTAssertEqual(omitted.shownWords(), Model.words(Self.propUnavailable))

        // Restored in another order: the same exact prop.
        XCTAssertEqual(Model(Self.input(Self.contracts, selection: held)).content(.prop), first)

        // The owner drops its held selection, then holds it again.
        XCTAssertEqual(Model(Self.input(selection: nil)).content(.prop), .propUnavailable(.omitted))
        XCTAssertEqual(Model(Self.input(selection: held)).content(.prop), first)
    }

    // MARK: Owner windows

    func testAWindowShowsOnlyTheOwnersRowsAndHandsBackItsExactPageIDs() throws {
        let alphabetical = Self.alphabetical
        let firstSix = Array(alphabetical.prefix(6))
        let window = Window(rows: firstSix.map { Self.identity($0) }, label: "1–6 of 46", previous: nil,
                            next: Link(id: "page-2", label: "Next"))
        let log = Log()
        let page = Self.page(Self.input(window: window), .catalogue, log: log)
        XCTAssertEqual(page.model.choices.map(\.label), firstSix.map(\.name))
        XCTAssertEqual(page.model.choices.map(\.selection), firstSix.map { Optional(Self.selection($0)) })
        XCTAssertNil(page.model.previous)
        XCTAssertNil(page.pageAction(page.model.previous), "no earlier window, no control")
        XCTAssertEqual(Array(page.shownWords().suffix(8)), ["1–6 of 46", "Next"] + firstSix.map(\.name))
        XCTAssertNil(page.pageAction(Link(id: "page-9", label: "Next")), "only the owner's own links act")
        try XCTUnwrap(page.selectAction(page.model.choices[0]))()
        try XCTUnwrap(page.pageAction(page.model.next))()
        XCTAssertEqual(log.events, ["hold", Self.selectEvent(alphabetical[0]), "hold", "page:page-2"],
                       "the first country opens exactly from the first window")

        // The last window, reordered, with an absent and a duplicated row; the
        // held selection lives on the first window.
        let uganda = Self.named("Uganda")
        let southAfrica = Self.named("South Africa")
        let absent = Details.Identity(source: "kalshi", market: "KXSOLAXQUAL-28-ZZZ", side: "yes")
        let last = Window(rows: [Self.identity(uganda), absent, Self.identity(southAfrica), Self.identity(uganda)],
                          label: "43–46 of 46", previous: Link(id: "page-7", label: "Previous"), next: nil)
        let held = Self.selection(alphabetical[0])
        let lastLog = Log()
        let lastPage = Self.page(Self.input(selection: held, window: last), .catalogue, log: lastLog)
        let rows = lastPage.model.choices
        XCTAssertEqual(rows.map(\.label), ["Uganda", "Country unavailable", "South Africa", "Uganda"])
        XCTAssertEqual(rows.map(\.selection), [Self.selection(uganda), nil, Self.selection(southAfrica), Self.selection(uganda)])
        XCTAssertNil(rows[1].status)
        XCTAssertNil(lastPage.selectAction(rows[1]))
        XCTAssertEqual(Array(lastPage.shownWords().suffix(6)),
                       ["Previous", "43–46 of 46", "Uganda", "Country unavailable", "South Africa", "Uganda"])
        try XCTUnwrap(lastPage.selectAction(rows[0]))()
        try XCTUnwrap(lastPage.selectAction(rows[3]))()
        try XCTUnwrap(lastPage.pageAction(lastPage.model.previous))()
        XCTAssertEqual(lastLog.events, ["hold", Self.selectEvent(uganda), "hold", Self.selectEvent(uganda),
                                        "hold", "page:page-7"],
                       "the last country opens exactly from either of its rows")
        XCTAssertEqual(uganda, alphabetical[45])
        XCTAssertEqual(Model(Self.input(selection: held, window: last)).content(.prop), .prop(Self.prop(alphabetical[0])),
                       "the window never limits the held prop")

        // Blank owner words draw no control and no label.
        let blank = Window(rows: [], label: " ", previous: Link(id: " ", label: "Previous"), next: Link(id: "page-2", label: ""))
        let blankModel = Model(Self.input(window: blank))
        XCTAssertNil(blankModel.pageLabel)
        XCTAssertNil(blankModel.previous)
        XCTAssertNil(blankModel.next)
        XCTAssertTrue(blankModel.choices.isEmpty)
    }

    // MARK: Holds and callbacks

    func testOverviewAndCatalogueActionsHoldOnceAndPropAndAboutContentKeepExactCallbacks() throws {
        let brazil = Self.named("Brazil")
        let window = Window(rows: Self.alphabetical.map { Self.identity($0) }, label: "1–46 of 46",
                            previous: Link(id: "p-0", label: "Previous"), next: Link(id: "p-2", label: "Next"))
        let input = Self.input(selection: Self.selection(brazil), window: window)

        let log = Log()
        let overview = Self.page(input, .overview, log: log)
        try XCTUnwrap(overview.aboutAction())()
        try XCTUnwrap(overview.allPropsAction())()
        let catalogue = Self.page(input, .catalogue, log: log)
        try XCTUnwrap(catalogue.aboutAction())()
        try XCTUnwrap(catalogue.overviewAction())()
        try XCTUnwrap(catalogue.pageAction(catalogue.model.previous))()
        try XCTUnwrap(catalogue.pageAction(catalogue.model.next))()
        let brazilRow = try XCTUnwrap(catalogue.model.choices.first { $0.label == "Brazil" })
        XCTAssertTrue(brazilRow.isSelected)
        try XCTUnwrap(catalogue.selectAction(brazilRow))()
        XCTAssertEqual(log.events, ["hold", "about", "hold", "catalogue", "hold", "about", "hold", "overview",
                                    "hold", "page:p-0", "hold", "page:p-2", "hold", Self.selectEvent(brazil)])

        let detail = Log()
        try XCTUnwrap(Self.page(input, .about, log: detail).aboutCatalogueAction())()
        XCTAssertTrue(Self.actions(Self.page(input, .prop, log: detail)).isEmpty)
        XCTAssertEqual(detail.events, ["catalogue"])

        // No hook: every callback is the owner's own.
        let exact = Log()
        try XCTUnwrap(Self.page(input, .overview, log: exact, hook: false).allPropsAction())()
        try XCTUnwrap(Self.page(input, .catalogue, log: exact, hook: false).overviewAction())()
        XCTAssertEqual(exact.events, ["catalogue", "overview"])
    }

    func testWithoutCallbacksNoControlShowsAndNothingIsCalled() {
        var holds = 0
        let window = Window(rows: Self.alphabetical.map { Self.identity($0) }, label: "1–46 of 46",
                            previous: Link(id: "p-0", label: "Previous"), next: Link(id: "p-2", label: "Next"))
        let input = Self.input(selection: Self.selection(Self.named("Brazil")), window: window)
        for mode in Mode.allCases {
            let page = Page(input: input, mode: mode, onInteraction: { holds += 1 })
            XCTAssertTrue(Self.actions(page).isEmpty, "\(mode)")
            XCTAssertTrue(page.model.choices.allSatisfy { page.selectAction($0) == nil }, "\(mode)")
        }
        XCTAssertEqual(Page(input: input, mode: .overview).shownWords(), Self.headerWords)
        XCTAssertEqual(Page(input: input, mode: .catalogue).shownWords(),
                       Self.headerWords + ["46 country props", "No recorded probabilities · alphabetical order", "1–46 of 46"]
                           + Self.alphabetical.map(\.name))
        XCTAssertEqual(Page(input: input, mode: .about).shownWords(), Self.aboutWords)
        XCTAssertEqual(holds, 0)
    }

    // MARK: Truth

    func testNoReadingGradeOrQuoteCarriedByAnOriginalReachesAnyMode() {
        let originals = Self.alphabetical.map { contract -> Details.Original in
            let base = Self.original(contract)
            return Details.Original(
                identity: base.identity, title: base.title, outcome: base.outcome, mode: .comparison(.current),
                pregame: .value("37%", placement: 0.37, provenance: "Recorded Sep 1"),
                later: Details.Reading.value("41%", placement: 0.41, provenance: "Recorded Sep 2"),
                grade: Details.Grade(words: "Resolved Yes", provenance: "Settled Sep 3"),
                about: Details.About(source: base.about.source, rules: base.about.rules, provenance: base.about.provenance,
                                     historicalQuote: Details.HistoricalQuote(text: "12%", recorded: "Sep 4")),
                beforeLabel: "Before the draw")
        }
        let forbidden = ["37%", "41%", "12%", "Resolved Yes", "Recorded Sep", "Settled Sep", "Sep 4", "Before the draw",
                         Details.pregameLabel, Details.Later.current.label, Details.Later.recorded.label,
                         Details.resultLabel, Details.historicalLabel]
        let brazil = Self.named("Brazil")
        let input = Self.input(originals: originals, selection: Self.selection(brazil))
        for mode in Mode.allCases {
            let words = Self.page(input, mode, log: Log()).shownWords()
            for word in forbidden {
                XCTAssertFalse(words.contains { $0.contains(word) }, "\(mode) shows \(word)")
            }
        }
        XCTAssertEqual(Model(input).content(.prop), .prop(Self.prop(brazil)))
    }

    // MARK: Measured layout

    func testLayingOutEveryModeAtPhoneWideAndAccessibilitySizesFitsAndCallsNothing() {
        let log = Log()
        let window = Window(rows: Array(Self.alphabetical.prefix(6)).map { Self.identity($0) }, label: "1–6 of 46",
                            previous: nil, next: Link(id: "page-2", label: "Next"))
        let inputs = [Self.input(selection: Self.selection(Self.named("Hong Kong, China"))),
                      Self.input(selection: Self.selection(Self.named("Uganda")), window: window),
                      Self.input(validity: .invalidated, selection: Self.selection(Self.named("Uganda")))]
        let layouts: [(CGFloat, DynamicTypeSize)] = [(375, .large), (393, .large), (375, .xxxLarge),
                                                     (375, .accessibility3), (1030, .large)]
        for input in inputs {
            for mode in Mode.allCases {
                for (width, size) in layouts {
                    let host = hostForMeasurement(Self.page(input, mode, log: log), at: size)
                    host.view.frame = CGRect(x: 0, y: 0, width: width, height: 2000)
                    host.view.setNeedsLayout()
                    host.view.layoutIfNeeded()
                    let fitted = host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
                    XCTAssertLessThanOrEqual(fitted.width, width + 0.5, "\(mode) \(width) \(size) scrolls sideways")
                    XCTAssertTrue(fitted.height.isFinite && fitted.height > 0, "\(mode) \(width) \(size)")
                }
            }
        }
        XCTAssertTrue(log.events.isEmpty, "laying out calls nothing")
    }

    func testTheMountedGridPlacesTheOwnersColumnsAndEqualRowHeightsAtPhoneWideAndAccessibilitySizes() {
        func fitted(_ width: CGFloat, accessibility: Bool, heights: [CGFloat]) -> CGSize {
            let grid = QualificationEventPageGrid10868(minimumCardWidth: OriginalMarketCatalogue9483.minimumCardWidth,
                                                       spacing: OriginalMarketCatalogue9483.spacing,
                                                       accessibilitySize: accessibility) {
                ForEach(Array(heights.enumerated()), id: \.offset) { _, height in
                    Color.clear.frame(height: height)
                }
            }
            let host = hostForMeasurement(grid, at: accessibility ? .accessibility3 : .large)
            return host.sizeThatFits(in: CGSize(width: width, height: .greatestFiniteMagnitude))
        }
        // Phone width: two columns, each row as tall as its tallest face.
        XCTAssertEqual(fitted(343, accessibility: false, heights: [50, 80]).height, 80, accuracy: 0.5)
        XCTAssertEqual(fitted(343, accessibility: false, heights: [50, 80, 60]).height, 80 + 8 + 60, accuracy: 0.5)
        XCTAssertEqual(fitted(361, accessibility: false, heights: [50, 50]).height, 50, accuracy: 0.5)
        // Accessibility sizes: one column.
        XCTAssertEqual(fitted(343, accessibility: true, heights: [50, 80]).height, 50 + 8 + 80, accuracy: 0.5)
        // Wide: six to a row.
        XCTAssertEqual(fitted(998, accessibility: false, heights: Array(repeating: 50, count: 6)).height, 50, accuracy: 0.5)
        XCTAssertEqual(fitted(998, accessibility: false, heights: Array(repeating: 50, count: 7)).height, 108, accuracy: 0.5)
        // Never wider than offered.
        for width in [CGFloat(343), 361, 998] {
            XCTAssertLessThanOrEqual(fitted(width, accessibility: false, heights: [50, 80, 60]).width, width + 0.5)
        }
    }

    func testRowsAndEntriesAreAtLeast44PointsTallAndLongNamesWrapWhole() {
        XCTAssertEqual(QualificationEventPageRow10868.minimumHeight, 44)
        func columns(_ width: CGFloat, accessibility: Bool) -> OriginalMarketCatalogue9483.Geometry {
            OriginalMarketCatalogue9483.geometry(cards: 46, width: width, intrinsicWidth: 0,
                                                 minimumCardWidth: OriginalMarketCatalogue9483.minimumCardWidth,
                                                 spacing: OriginalMarketCatalogue9483.spacing,
                                                 accessibilitySize: accessibility)
        }
        let phone = columns(343, accessibility: false)
        XCTAssertEqual(phone.columns, 2)
        XCTAssertEqual(columns(343, accessibility: true).columns, 1, "accessibility sizes reflow to one column")
        XCTAssertEqual(columns(998, accessibility: false).columns, 6)

        for size in [DynamicTypeSize.xSmall, .large, .accessibility3, .accessibility5] {
            let width = size.isAccessibilitySize ? 343 : phone.cardWidth
            for name in ["Uganda", "Hong Kong, China", "Côte d’Ivoire"] {
                let card = Self.measure(QualificationEventPageRow10868(label: name), width: width, size: size)
                XCTAssertGreaterThanOrEqual(card.height, 44, "\(name) \(size)")
                XCTAssertLessThanOrEqual(card.width, width + 0.5, "\(name) \(size)")
                let still = Self.measure(QualificationEventPageRow10868(label: name, status: "Unavailable", acts: false),
                                         width: width, size: size)
                XCTAssertGreaterThanOrEqual(still.height, 44, "\(name) \(size)")
            }
            let entry = Self.measure(QualificationEventPageRow10868(label: Self.entry, style: .entry), width: 343, size: size)
            XCTAssertGreaterThanOrEqual(entry.height, 44, "\(size)")
            XCTAssertLessThanOrEqual(entry.width, 343.5, "\(size)")
        }

        // A long name wraps whole rather than truncating: narrower is taller.
        let narrow = Self.measure(QualificationEventPageRow10868(label: "Hong Kong, China"), width: 90, size: .large)
        let wide = Self.measure(QualificationEventPageRow10868(label: "Hong Kong, China"), width: 600, size: .large)
        XCTAssertGreaterThan(narrow.height, wide.height)
    }
}
