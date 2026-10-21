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
    try tests.testOnlyAProvenSyntheticPinCanYieldToTheActualObservation()
    try tests.testActualChartReplacesOnlyMatchingPinAndRestoresItWithoutPreview()
} catch {
    ReaderChecks.failures += 1
    print("Unexpected error: \(error)")
}
print("Source reader checks: \(ReaderChecks.assertions) assertions, \(ReaderChecks.failures) failures")
exit(ReaderChecks.failures == 0 && ReaderChecks.assertions >= 40 ? 0 : 1)

}
}
