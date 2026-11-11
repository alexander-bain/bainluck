import XCTest
@testable import Bain_Luck

/// #11547 — Alex, build 82 & Nov 11: a market, prop or future is never called a
/// "question". Default is "market", "prop" for a player or game prop, "future"
/// for a season-long one; a market title that is itself something a reader would
/// ask ("Will Sinner actually play?") stays as served.
final class HubOtherMarkets11547Tests: XCTestCase {

    // MARK: - Collection Hub

    func testTheSideMarketSectionIsOtherMarkets() {
        XCTAssertEqual(ContainerHubPresentation.sectionTitle("side_question"), "Other markets")
    }

    func testNoHubSectionIsCalledAQuestion() {
        for sectionClass in ["match_winner", "prop", "title", "advancement", "side_question", "doubles", "unknown"] {
            XCTAssertFalse(ContainerHubPresentation.sectionTitle(sectionClass).lowercased().contains("question"), sectionClass)
        }
    }

    // MARK: - Browse Collection Cards

    func testBrowseCollectionCardsCountMarketsNotQuestions() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase

        func makeEntry(games: Int, markets: Int) throws -> ContainerDiscoveryEntry {
            let payload: [String: Any] = [
                "type": "collection", "id": 901, "name": "NFL Week 4",
                "text": "Supplied collection text", "slug": "nfl-2026-week-4",
                "state": "published", "revision": 1,
                "edition": ["kind": "nfl_week", "league": "nfl", "season": 2026,
                            "stage": "Regular Season", "week": 4],
                "status": "upcoming", "game_count": games, "question_count": markets,
                "matched_event_ids": [7],
                "destination": ["kind": "container", "slug": "nfl-2026-week-4",
                                "web": "/collection/nfl-2026-week-4",
                                "api": "/api/containers/nfl-2026-week-4"],
            ]
            let data = try JSONSerialization.data(withJSONObject: payload)
            let collection = try decoder.decode(ContainerHubCollection.self, from: data)
            return ContainerDiscoveryEntry(collection: collection)
        }

        XCTAssertEqual(try makeEntry(games: 0, markets: 1).subtitle, "1 market")
        XCTAssertEqual(try makeEntry(games: 0, markets: 12).subtitle, "12 markets")
        XCTAssertEqual(try makeEntry(games: 2, markets: 3).subtitle, "2 games · 3 markets")
    }

    // MARK: - Search Game Rows

    func testSearchGameRowsCountMarketsNotQuestions() {
        XCTAssertEqual(RelatedGameListing(eventId: 1, questionCount: 1).label, "1 market on this game")
        XCTAssertEqual(RelatedGameListing(eventId: 1, questionCount: 8).label, "8 markets on this game")
    }

    // MARK: - Finished Game Props

    func testFinishedPropsNamePropsNotQuestions() throws {
        XCTAssertEqual(PropExpectationActualDisplay.unavailableLabel,
                       "No pregame chance was saved for this prop.")

        let json = """
        {"question_key":"q1","actual_key":"a1","subject":{"kind":"player","key":"p1","label":"Aaron Judge"},
         "stat_key":"home_runs","period_key":"first_5",
         "predicate":{"kind":"count_at_least","side":"over","count":1,"label":"1+"},
         "expectation":{"state":"unavailable","reason":"missing","probability":null,"basis":null,
                        "observed_at":null,"contributors":[],"excluded":[]},
         "comparison":null}
        """
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        let prop = try decoder.decode(AfterPropQuestion.self, from: Data(json.utf8))
        let spoken = PropExpectationActualDisplay.accessibilityLabel(prop, actual: nil, stat: nil)
        XCTAssertTrue(spoken.contains("Prop unavailable"), spoken)
        XCTAssertFalse(spoken.lowercased().contains("question"), spoken)
    }

    // MARK: - Tournament Hub

    func testTournamentHubNotesNameMarketsWhileKeepingInterrogativeTitles() throws {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        func present(props: String) throws -> TournamentHubPresentation {
            let json = """
            {"slug":"us-open","title":"US Open","slate":{"matches":[]},
             "results":{"matches":[]},"boards":[],"bracket":{},"props":[\(props)]}
            """
            return TournamentHubPresentation(
                response: try decoder.decode(TournamentHubResponse.self, from: Data(json.utf8)))
        }

        let empty = try present(props: "")
        XCTAssertEqual(empty.propsEmptyNote,
                       "No curated markets on this tournament yet — they appear here as Kalshi and Polymarket open them.")

        let one = { (i: Int) in """
        {"key":"k\(i)","title":"Will Sinner actually play?","answer_entity_key":"k\(i):yes","legs":1,
         "outcomes":[{"entity_key":"k\(i):yes","display_name":"Yes","probability":0.5,
                      "probability_is_live":true,"age_hours":0.1,"is_answer":true}]}
        """ }
        let trimmed = try present(props: (1...9).map(one).joined(separator: ","))
        XCTAssertEqual(trimmed.propsTrimNote, "Showing 6 of 9 markets")
        XCTAssertEqual(trimmed.props.first?.question, "Will Sinner actually play?",
                       "a title that is itself something a reader would ask stays as served")

        let closedIncomplete = try present(props: """
        {"key":"cmp","title":"Who goes further?","legs":2,"settled":true,"settled_answer":"Alcaraz",
         "outcomes":[{"entity_key":"a","display_name":"Carlos Alcaraz","probability":null},
                     {"entity_key":"b","display_name":"Jannik Sinner","probability":0.4,
                      "probability_is_live":false,"age_hours":90}]}
        """)
        XCTAssertEqual(closedIncomplete.props.first?.incompleteNote,
                       "We have no number for Carlos Alcaraz, so this comparison is not complete and the market has closed.")
    }

    // MARK: - Internal Discover Labeling

    func testLabelingDriftRefusalNamesMarketsNotQuestions() {
        let drifted = DiscoverLabelingViewModel.driftRefusalMessage(#"{"detail":"card_drifted"}"#)
        XCTAssertEqual(drifted,
                       "This market re-priced while you were reading it — nothing was recorded. Reload to grade the current card.")
        XCTAssertFalse(drifted.lowercased().contains("question"))
    }

    // MARK: - Source Guard

    func testNoUpdatedSurfaceStringLiteralCallsAMarketAQuestion() throws {
        let appRoot = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("Bain Luck")
        let guardedFiles = [
            "Utilities/ContainerHubPresentation.swift",
            "Models/ContainerDiscoveryModels.swift",
            "Models/SearchModels.swift",
            "Utilities/PropExpectationActualDisplay.swift",
            "Utilities/TournamentHubPresentation.swift",
            "ViewModels/DiscoverLabelingViewModel.swift",
        ]
        let wireKeysAllowed: Set<String> = ["side_question"]

        for relative in guardedFiles {
            let source = try String(contentsOf: appRoot.appendingPathComponent(relative), encoding: .utf8)
            for (index, rawLine) in source.components(separatedBy: .newlines).enumerated() {
                let trimmed = rawLine.trimmingCharacters(in: .whitespaces)
                if trimmed.hasPrefix("//") { continue }
                for literal in Self.printedLiteralSegments(in: rawLine) {
                    if wireKeysAllowed.contains(literal) { continue }
                    XCTAssertFalse(
                        literal.lowercased().contains("question"),
                        "\(relative):\(index + 1) prints 'question' in literal: \"\(literal)\""
                    )
                }
            }
        }
    }

    /// Extracts every literal text segment from a line of Swift code, stepping into
    /// nested string literals inside `\(... )` interpolations while skipping the
    /// Swift identifier tokens themselves (`collection.questionCount`, `question.predicate`).
    private static func printedLiteralSegments(in line: String) -> [String] {
        let chars = Array(line)
        var i = 0
        var segments: [String] = []

        func readString() {
            i += 1 // skip opening "
            var current = ""
            while i < chars.count {
                let ch = chars[i]
                if ch == "\\" && i + 1 < chars.count {
                    if chars[i + 1] == "(" {
                        if !current.isEmpty { segments.append(current); current = "" }
                        i += 2 // skip \(
                        var depth = 1
                        while i < chars.count && depth > 0 {
                            if chars[i] == "\"" {
                                readString()
                                continue
                            }
                            if chars[i] == "(" { depth += 1 }
                            else if chars[i] == ")" { depth -= 1 }
                            i += 1
                        }
                        continue
                    } else {
                        current.append(ch)
                        current.append(chars[i + 1])
                        i += 2
                        continue
                    }
                }
                if ch == "\"" {
                    i += 1
                    break
                }
                current.append(ch)
                i += 1
            }
            if !current.isEmpty { segments.append(current) }
        }

        while i < chars.count {
            if chars[i] == "/" && i + 1 < chars.count && chars[i + 1] == "/" { break }
            if chars[i] == "\"" {
                readString()
            } else {
                i += 1
            }
        }
        return segments
    }
}
