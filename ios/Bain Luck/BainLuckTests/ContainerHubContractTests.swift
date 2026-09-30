import XCTest
@testable import Bain_Luck

final class ContainerHubContractTests: XCTestCase {
    func testNFLIdentityRevisionAndOrderComeFromHydratedContract() throws {
        let r = try ContainerHubFixture.decode()
        XCTAssertEqual(r.slug, "nfl-2026-week-5")
        XCTAssertEqual(r.revision, 4)
        XCTAssertEqual(r.edition?.kind, "nfl_week")
        XCTAssertEqual(r.edition?.season, 2026)
        XCTAssertEqual(r.edition?.stage, "Regular Season")
        XCTAssertEqual(r.edition?.week, 5)
        XCTAssertEqual(r.sections.map(\.sectionClass), ["match_winner", "prop"])
        XCTAssertEqual(r.sections.flatMap(\.members).map(\.memberId), [502, 501, 9101, 9102, 9103])
        XCTAssertEqual(r.sections.first?.members.first?.questionIds, [9102])
        XCTAssertEqual(r.memberCount, 5)
        XCTAssertTrue(ContainerHubPresentation(response: r).isPartial)
        XCTAssertEqual(r.withheld.first?.id, 599)
        XCTAssertEqual(r.withheld.first?.reason, "row_missing")
    }

    func testMLBFinalAndScheduledCardsRetainTheirServedState() throws {
        let r = try ContainerHubFixture.decode("representative_mlb_postseason")
        XCTAssertEqual(r.edition?.kind, "mlb_postseason")
        XCTAssertEqual(r.edition?.league, "mlb")
        XCTAssertEqual(r.revision, 11)
        let members = r.sections.flatMap(\.members)
        guard case .event(let final) = members[0].card,
              case .event(let scheduled) = members[1].card else { return XCTFail("Both event cards must decode") }
        XCTAssertEqual(final.status, "completed")
        XCTAssertNotNil(final.homeScore)
        XCTAssertEqual(scheduled.status, "scheduled")
        XCTAssertFalse(ContainerHubPresentation(response: r).isPartial)
        XCTAssertEqual(members.map(\.memberId), [801, 802, 9201, 9202])
    }

    func testTerminalAndUnknownStatesCannotLeakPublishedMembers() throws {
        for state in ["withdrawn", "unpublished", "empty", "unavailable", "complete", "partial", "new_state"] {
            let r = try ContainerHubFixture.decode { $0["state"] = state }
            XCTAssertTrue(r.sections.isEmpty, state)
            XCTAssertTrue(r.children.isEmpty, state)
            XCTAssertNotNil(ContainerHubPresentation(response: r).note, state)
            if state != "empty" { XCTAssertNil(ContainerHubPresentation(response: r).title, state) }
            if ["complete", "partial", "new_state"].contains(state) { XCTAssertEqual(r.state, .unpublished) }
        }
    }

    func testMissingPublishedSectionsIsAnErrorNotAnEmptyHub() throws {
        XCTAssertThrowsError(try ContainerHubFixture.decode { $0.removeValue(forKey: "sections") })
        XCTAssertThrowsError(try ContainerHubFixture.decode { $0.removeValue(forKey: "revision") })
    }

    func testMalformedMemberDoesNotEraseHealthySiblings() throws {
        let r = try ContainerHubFixture.decode { object in
            ContainerHubFixture.mutateMember(&object) { $0["card"] = ["id": 502] }
        }
        XCTAssertEqual(r.sections[0].members.map(\.memberId), [501, 9101, 9102])
        XCTAssertEqual(r.sections[0].unavailableCount, 1)
        XCTAssertTrue(ContainerHubPresentation(response: r).isPartial)
    }

    func testCardAndDestinationIdentityMustAgree() throws {
        for mutation in ["card", "destination"] {
            let r = try ContainerHubFixture.decode { object in
                ContainerHubFixture.mutateMember(&object) { member in
                    var value = member[mutation] as! [String: Any]
                    value["id"] = 999
                    member[mutation] = value
                }
            }
            XCTAssertEqual(r.sections[0].members.map(\.memberId), [501, 9101, 9102], mutation)
            XCTAssertEqual(r.sections[0].unavailableCount, 1, mutation)
        }
    }

    func testExternalOrWrongAPIDestinationCannotBecomeAnOrdinaryRoute() throws {
        let r = try ContainerHubFixture.decode { object in
            ContainerHubFixture.mutateMember(&object) { member in
                var destination = member["destination"] as! [String: Any]
                destination["api"] = "https://example.com/api/events/502"
                member["destination"] = destination
            }
        }
        XCTAssertFalse(r.sections[0].members.contains { $0.memberId == 502 })
    }

    func testRelatedQuestionsUseBothPresentedIDsAndEventLink() throws {
        let p = ContainerHubPresentation(response: try ContainerHubFixture.decode())
        let bills = try XCTUnwrap(p.members.first { $0.memberId == 501 })
        XCTAssertEqual(p.relatedQuestions(for: bills).map(\.memberId), [9101, 9103])
        let changed = try ContainerHubFixture.decode { object in
            ContainerHubFixture.mutateMember(&object, member: 2) { $0["event_id"] = 999 }
        }
        let mutated = ContainerHubPresentation(response: changed)
        let sameBills = try XCTUnwrap(mutated.members.first { $0.memberId == 501 })
        XCTAssertEqual(mutated.relatedQuestions(for: sameBills).map(\.memberId), [9103])
    }

    func testProducerCollectionCardsDecodeWithoutInventingAnEndpoint() throws {
        let nfl = try XCTUnwrap(ContainerHubFixture.collections("search_by_games").first)
        XCTAssertEqual(nfl.slug, "nfl-2026-week-5")
        XCTAssertEqual(nfl.revision, 4)
        XCTAssertEqual(nfl.destination.api, "/api/containers/nfl-2026-week-5")
        XCTAssertNil(nfl.destination.web)
        XCTAssertTrue(nfl.canOpen)
        let mlb = try XCTUnwrap(ContainerHubFixture.collections("browse_mlb").first)
        XCTAssertEqual(mlb.edition.kind, "mlb_postseason")
        XCTAssertEqual(mlb.destination.api, "/api/containers/mlb-2026-postseason")
        XCTAssertTrue(mlb.canOpen)
    }

    func testOnlyPublishedChildrenWithMatchingDestinationAreOpenable() throws {
        let r = try ContainerHubFixture.decode { object in
            object["children"] = ["published", "withdrawn", "unpublished"].enumerated().map { index, state in
                ["id": index + 100, "name": "Child", "slug": "child-\(index)", "publication_state": state,
                 "destination": ["kind": "container", "slug": "child-\(index)", "api": "/api/containers/child-\(index)", "web": NSNull()]] as [String: Any]
            }
        }
        XCTAssertEqual(ContainerHubPresentation(response: r).children.map(\.slug), ["child-0"])
    }

    func testMemberReturnPreservesAnchorAndRevisionRemovalClearsIt() throws {
        let p = ContainerHubPresentation(response: try ContainerHubFixture.decode())
        let member = try XCTUnwrap(p.members.first { $0.memberId == 9103 })
        var context = ContainerHubReadingContext()
        context.accept(p)
        context.scrollMemberId = member.id
        context.open(member)
        context.accept(p)
        XCTAssertEqual(context.scrollMemberId, "market:9103")
        XCTAssertEqual(context.selectedMemberId, "market:9103")
        XCTAssertEqual(context.identity?.revision, 4)
        let next = try ContainerHubFixture.decode { $0["state"] = "withdrawn"; $0["revision"] = 5 }
        context.accept(ContainerHubPresentation(response: next))
        XCTAssertNil(context.scrollMemberId)
        XCTAssertNil(context.selectedMemberId)
        XCTAssertEqual(context.identity?.revision, 5)
    }

    @MainActor
    func testVenueVerdictReplacesASettledQuestionPriceAndMissingPricesStayMissing() throws {
        let r = try ContainerHubFixture.decode { object in
            ContainerHubFixture.mutateMember(&object, section: 1) { member in
                var card = member["card"] as! [String: Any]
                card["status"] = "resolved"
                var outcomes = card["top_outcomes"] as! [[String: Any]]
                outcomes[0]["is_winner"] = true
                outcomes[0]["resolution_source"] = "api_settlement"
                outcomes[1]["is_winner"] = false
                outcomes[1]["resolution_source"] = "api_settlement"
                outcomes[1]["probability"] = NSNull()
                card["top_outcomes"] = outcomes
                member["card"] = card
            }
        }
        guard case .question(let feed, let search) = r.sections[1].members[0].card else { return XCTFail("Question missing") }
        XCTAssertNil(feed.topOutcomes?[1].probability)
        XCTAssertTrue(ContainerHubPresentation.questionNeedsVerdictRows(search))
        XCTAssertEqual(ContainerHubPresentation.outcomeLabel(search.topOutcomes![0], market: search), "Won")
        XCTAssertEqual(ContainerHubPresentation.outcomeLabel(search.topOutcomes![1], market: search), "Lost")
    }

    func testServicePathRejectsTraversalAndRouteFragments() throws {
        XCTAssertEqual(try ContainerHubService.path(for: "nfl-2026-week-5"), "/api/containers/nfl-2026-week-5")
        for slug in ["", "..", "nfl/2026", "nfl-2026?other=true", "nfl-2026#section"] {
            XCTAssertThrowsError(try ContainerHubService.path(for: slug), slug)
        }
    }
}
