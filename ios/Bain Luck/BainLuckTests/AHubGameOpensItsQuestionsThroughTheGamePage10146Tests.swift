import XCTest
@testable import Bain_Luck

/// #10146 (Alex, build 34): an NFL week hub no longer expands each game's questions
/// inline ("Related questions (363)"). A game with questions shows one quiet
/// "More on this game" row that opens the same game page its card opens.
final class AHubGameOpensItsQuestionsThroughTheGamePage10146Tests: XCTestCase {
    func testMoreOnGameOpensTheSameGamePageAsTheCard() throws {
        let p = ContainerHubPresentation(response: try ContainerHubFixture.decode())
        for id in [501, 502] {
            let game = try XCTUnwrap(p.members.first { $0.memberId == id })
            XCTAssertFalse(p.relatedQuestions(for: game).isEmpty, "fixture game \(id) carries questions")
            XCTAssertEqual(p.moreOnGameRoute(for: game), .eventDetail(id: id))
        }
    }

    func testAGameWithNoLinkedQuestionsGetsNoRow() throws {
        // 9102 is 502's only question; pointing it at another event leaves 502 with none.
        let r = try ContainerHubFixture.decode { object in
            ContainerHubFixture.mutateMember(&object, member: 3) { $0["event_id"] = 999 }
        }
        let p = ContainerHubPresentation(response: r)
        let game = try XCTUnwrap(p.members.first { $0.memberId == 502 })
        XCTAssertTrue(p.relatedQuestions(for: game).isEmpty)
        XCTAssertNil(p.moreOnGameRoute(for: game))
        let other = try XCTUnwrap(p.members.first { $0.memberId == 501 })
        XCTAssertEqual(p.moreOnGameRoute(for: other), .eventDetail(id: 501), "sibling keeps its row")
    }

    func testAQuestionCardNeverGetsAMoreOnGameRow() throws {
        let p = ContainerHubPresentation(response: try ContainerHubFixture.decode())
        for question in p.members where question.type == "market" {
            XCTAssertNil(p.moreOnGameRoute(for: question), "\(question.memberId)")
        }
    }

    func testOpeningTheRowRemembersTheGameSoBackReturnsToIt() throws {
        let p = ContainerHubPresentation(response: try ContainerHubFixture.decode())
        let game = try XCTUnwrap(p.members.first { $0.memberId == 501 })
        var context = ContainerHubReadingContext()
        context.accept(p)
        context.scrollMemberId = game.id
        context.open(game) // the row and the card both call vm.opened(member)
        context.accept(p)  // Back revalidates the same edition
        XCTAssertEqual(context.selectedMemberId, game.id)
        XCTAssertEqual(context.scrollMemberId, game.id)
    }

    /// The hub view has no inline expansion, no count on the row, and wires the row
    /// through the presentation route and the same opened(member) anchor as the card.
    func testHubViewHasNoInlineExpansionAndNoCount() throws {
        let source = try String(contentsOf: Self.repoFile("ios/Bain Luck/Bain Luck/Views/ContainerHubView.swift"), encoding: .utf8)
        XCTAssertFalse(source.contains("DisclosureGroup"))
        XCTAssertFalse(source.contains("Related questions"))
        XCTAssertTrue(source.contains("Text(\"More on this game\")"))
        XCTAssertFalse(source.contains("More on this game ("), "no count on the row")
        XCTAssertTrue(source.contains("presentation.moreOnGameRoute(for: member)"))
        let row = try XCTUnwrap(source.range(of: "presentation.moreOnGameRoute(for: member)"))
        let tail = String(source[row.upperBound...].prefix(900))
        XCTAssertTrue(tail.contains("vm.opened(member)"), "the row records the game anchor for Back")
    }

    private static func repoFile(_ path: String) -> URL {
        var url = URL(fileURLWithPath: #filePath)
        while url.path != "/" && !FileManager.default.fileExists(atPath: url.appendingPathComponent("ios").path) {
            url.deleteLastPathComponent()
        }
        return url.appendingPathComponent(path)
    }
}
