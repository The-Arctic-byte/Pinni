import SwiftUI

struct CommunityScreen: View {
    var body: some View {
        NavigationStack {
            ContentUnavailableView(
                "Community",
                systemImage: "person.2",
                description: Text("Channels suggested from people like you are coming soon.")
            )
            .navigationTitle(Text("Community"))
        }
    }
}

#Preview {
    CommunityScreen()
}
