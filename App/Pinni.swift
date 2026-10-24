import SwiftUI

@main struct Pinni: App {
    @State private var model = AppModel(service: DataSource.current.makeService())

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
        }
    }
}
