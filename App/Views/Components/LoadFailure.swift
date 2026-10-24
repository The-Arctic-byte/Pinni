import SwiftUI

/// Shown when the feed cannot be loaded. The same failure covers the map and the news list.
struct LoadFailure: View {
    let message: String
    let retry: () async -> Void

    var body: some View {
        ContentUnavailableView {
            Label("Couldn’t load news", systemImage: "exclamationmark.triangle")
        } description: {
            Text(message)
        } actions: {
            Button("Try again") {
                Task { await retry() }
            }
        }
    }
}
