import SwiftUI

struct WatchDiagnosticsView: View {
    @ObservedObject private var telemetry = WatchTelemetry.shared
    var body: some View {
        Form {
            Toggle("Share Watch diagnostics", isOn: Binding(
                get: { telemetry.enabled }, set: { telemetry.setEnabled($0) }))
            Text("Shares screen visits, actions and load times as part of your iPhone’s analytics. Your iPhone must also allow analytics. No game names or search text are included.")
                .font(.footnote)
            Text("Off by default. Turning this off clears unsent Watch diagnostics. Data already sent cannot be recalled here.")
                .font(.footnote)
            if !telemetry.consentSaved {
                Text("Your choice could not be saved. It applies for this session.")
                    .font(.footnote)
            }
        }
        .navigationTitle("Diagnostics")
        .onAppear {
            telemetry.screen(.diagnostics)
            telemetry.content(.diagnostics)
        }
    }
}
