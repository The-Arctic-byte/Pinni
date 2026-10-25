import SwiftUI

@main struct Pinni: App {
    #if DEBUG
    // Test builds start as Sara, a member who can send reports; Profile → Mock data switches readers.
    @State private var model = AppModel(service: DataSource.current.makeService(), persona: .sara)
    #else
    @State private var model = AppModel(service: DataSource.current.makeService())
    #endif

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
        }
    }
}
