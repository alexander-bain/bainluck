import Foundation

@main struct RunReaderChecks {
@MainActor static func main() {
let tests = FoldedBlendPreview10090Tests()
do {
    try tests.testFoldedHeadlineChartAndClockUseSameAdmission()
    try tests.testDrawAwayIsTheServedValueIncludingNull()
    try tests.testFullMembershipAndEveryRevisionMustMatchAndBeCovered()
    try tests.testUnknownMalformedAndPartialFoldedMetadataNeverFallsBackToSingleton()
    try tests.testFloorWithdrawsBeforeQuoteAndCannotBeForgottenByReset()
    try tests.testMalformedFloorClearsButWrongEventDoesNot()
    try tests.testReconnectAndExpiryNeverRenewAReplayedSequence()
    try tests.testRevokeMustNameTheOriginAndReplayCannotResurrectIt()
    try tests.testSingletonContinuesToWorkButCannotMasqueradeAsFolded()
    try tests.testAMembershipChangeRetiresTheRemovedRowsFloorWithoutForgettingIt()
    try tests.testAnotherOriginsEpochNeverFencesTheReplacementOrigin()
    try tests.testASingletonsAcceptedIdentityStillFencesTheFoldAfterAReset()
    try tests.testARowThatLeavesAndReturnsKeepsItsFenceAndFloor()
    try tests.testResetAndAnUnchangedMembershipRenewNothing()
    try tests.testAFoldCollapsingToThePagesRowContinuesOnItsOwnLedger()
    try tests.testOnlyAProvenSyntheticPinCanYieldToTheActualObservation()
    try tests.testActualChartReplacesOnlyMatchingPinAndRestoresItWithoutPreview()
    try tests.testV2IndependentEpochsAndSharedSurfaceAdmission()
    try tests.testV2CannotLoseSiblingOrAdvanceFencesOnPartialValidation()
    try tests.testV2RetirementRecomposesSiblingAndCannotResurrect()
    try tests.testV2SiblingActivityAndReconnectCannotExtendLease()
    try tests.testV2NewSessionMayOmitQuietPriorOriginButPreservesItsFence()
    try tests.testV2OpenSessionAndDowngradeFences()
    try tests.testV2MalformedAuthorityNeverDecodesOrFallsBack()
    try tests.testV2ColdBaseWithdrawalPreservesSiblingDeadline()
    try tests.testV2UpgradeRetainsPriorV1OriginFence()
    try tests.testV2AuthoritativeMembershipChangeAdmitsTheNewFoldAndRefusesTheOld()
    try tests.testMembershipChangeCarriesTheSingletonFenceAndPrunesLegacyFloors()
    try tests.testTheRemovedOriginsScalarEpochLeavesWithItAndTheSurvivorsStays()
    try tests.testSingletonAuthorityOutlivesTheDisplayAndFencesTheFoldItJoins()
    try tests.testARowThatReturnsAfterAMembershipFlapGetsItsEvidenceBack()
    try tests.testRetiredEvidenceIsNeverEvictedAndCapacityRefusesInsteadOfForgetting()
    try tests.testAFoldDownToThePageRowResumesItsSingletonUnderItsOwnFence()
    try tests.testAV1OriginThatLeavesAndReturnsKeepsItsOrderAsAFence()
    try tests.testAnElectionChangeInsideAnUnchangedMembershipResumesOnTheFreshStream()
    try tests.testNewerV1AuthorityMergesIntoARestoredFenceBeforeV2Validation()
    try tests.testRowsThatLeaveTogetherAreAllRetainedAndCanExceedCapacityPlusOne()
    try tests.testASuccessfulV2MigrationConsumesTheLegacyOrderAndKeepsTheOriginPending()
} catch {
    ReaderChecks.failures += 1
    print("Unexpected error: \(error)")
}
print("Source reader checks: \(ReaderChecks.assertions) assertions, \(ReaderChecks.failures) failures")
exit(ReaderChecks.failures == 0 && ReaderChecks.assertions >= 100 ? 0 : 1)

}
}
