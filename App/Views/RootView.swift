import SwiftUI

/// iPhone: Flighty-style — the full-screen map with a native news sheet; Community and Profile open from the sheet.
/// Mac: sidebar with Map, News, Community and Profile; the map has a news inspector.
struct RootView: View {
    @Environment(AppModel.self) private var model
    @State private var selection: AppSection = .map

    var body: some View {
        content
            .task { if model.state == .idle { await model.load() } }
            #if os(macOS)
            .sheet(isPresented: showsOnboarding) { onboarding }
            #else
            .fullScreenCover(isPresented: showsOnboarding) { onboarding }
            #endif
    }

    private var showsOnboarding: Binding<Bool> {
        Binding(get: { !model.hasCompletedOnboarding }, set: { _ in })
    }

    private var onboarding: some View {
        OnboardingView(places: Array(model.places.values)) { answers in
            Task {
                await model.completeOnboarding(with: answers)
                selection = .map
            }
        }
        .interactiveDismissDisabled()
    }

    @ViewBuilder
    private var content: some View {
        #if os(macOS)
        NavigationSplitView {
            List(AppSection.allCases, selection: $selection) { section in
                Label(section.title, systemImage: section.systemImage)
                    .tag(section)
            }
            .navigationSplitViewColumnWidth(min: 180, ideal: 210)
        } detail: {
            selection.screen
        }
        #else
        MapScreen()
        #endif
    }
}

#Preview {
    RootView()
        .environment(AppModel())
}
