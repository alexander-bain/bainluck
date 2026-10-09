import SwiftUI

struct WatchDiagnosticsView: View {
    @Environment(\.dynamicTypeSize) private var dynamicTypeSize
    @ObservedObject private var telemetry = WatchTelemetry.shared
    var body: some View {
        Form {
            Section {
                Toggle("Share Watch diagnostics", isOn: Binding(
                    get: { telemetry.enabled }, set: { telemetry.setEnabled($0) }))
                    .accessibilityIdentifier("watch.diagnostics.choice")
                if !telemetry.consentSaved {
                    Text("Your choice could not be saved. It applies for this session.")
                        .font(.footnote)
                        .accessibilityIdentifier("watch.diagnostics.persistence-warning")
                }
                Text("Your iPhone must also allow analytics.")
                    .font(.footnote)
                    .accessibilityIdentifier("watch.diagnostics.phone-requirement")
            } header: {
                Text("Your choice")
            }
            Section {
                Text("Shares screen visits, actions and load times as part of your iPhone’s analytics. No game names or search text are included.")
                    .font(.footnote)
                    .accessibilityIdentifier("watch.diagnostics.disclosure")
            } header: {
                Text("What is shared")
            }
            Section {
                Text("Off by default. Turning this off clears unsent Watch diagnostics. Data already sent cannot be recalled here.")
                    .font(.footnote)
                    .accessibilityIdentifier("watch.diagnostics.revocation")
            } header: {
                Text("Turning it off")
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
