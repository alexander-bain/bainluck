import SwiftUI

struct WatchDiagnosticsView: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ObservedObject private var telemetry = WatchTelemetry.shared
    var body: some View {
        Form {
            Toggle("Share Watch diagnostics", isOn: Binding(
                get: { telemetry.enabled }, set: { telemetry.setEnabled($0) }))
                .accessibilityIdentifier("watch.diagnostics.choice")
            Text("Shares screen visits, actions and load times as part of your iPhone’s analytics. Your iPhone must also allow analytics. No game names or search text are included.")
                .font(.footnote)
                .accessibilityIdentifier("watch.diagnostics.disclosure")
            Text("Off by default. Turning this off clears unsent Watch diagnostics. Data already sent cannot be recalled here.")
                .font(.footnote)
                .accessibilityIdentifier("watch.diagnostics.revocation")
            if !telemetry.consentSaved {
                Text("Your choice could not be saved. It applies for this session.")
                    .font(.footnote)
            }
        }
        .accessibilityIdentifier("watch.diagnostics.form")
        .navigationTitle("Diagnostics")
        #if DEBUG
        .accessibilityValue(WatchUIFixture.current == nil ? "" : String(describing: dynamicTypeSize))
        #endif
        .onAppear {
            telemetry.screen(.diagnostics)
            telemetry.content(.diagnostics)
        }
    }
}
