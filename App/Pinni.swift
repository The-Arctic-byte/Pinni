import SwiftUI

@main struct Pinni: App {
    // A first launch is the new user, so onboarding shows. Profile → Mock data switches to Sara or Matti.
    @State private var model = AppModel(service: DataSource.current.makeService())

    var body: some Scene {
        WindowGroup {
            RootView()
                .environment(model)
        }
    }
}
