import SwiftUI

struct MyStuffView: View {
    var body: some View {
        NavigationStack {
            VStack(spacing: 16) {
                Spacer()

                Image(systemName: "person.crop.circle")
                    .font(.system(size: 56))
                    .foregroundStyle(.secondary)

                Text("My Stuff")
                    .font(.title2)
                    .fontWeight(.semibold)

                Text("Follow your teams, track your games, and see personalized odds — all in one place.")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal, 40)

                Text("Coming Soon")
                    .font(.caption)
                    .fontWeight(.medium)
                    .foregroundStyle(.blue)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 6)
                    .background(Color.blue.opacity(0.1))
                    .clipShape(Capsule())

                Text("Sign-in and team following are on the way.")
                    .font(.caption)
                    .foregroundStyle(.tertiary)

                Spacer()
            }
            .navigationTitle("My Stuff")
            #if os(iOS)
            .navigationBarTitleDisplayMode(.large)
            #endif
        }
    }
}
