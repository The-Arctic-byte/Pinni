import SwiftUI

/// iPhone: four tabs. Mac: sidebar with the same sections; the story inspector comes with A7.
struct RootView: View {
    @Environment(AppModel.self) private var model
    @State private var selection: AppSection = .map

    var body: some View {
        content
            .task { if model.state == .idle { await model.load() } }
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
        TabView(selection: $selection) {
            ForEach(AppSection.allCases) { section in
                Tab(value: section) {
                    section.screen
                } label: {
                    Label(section.title, systemImage: section.systemImage)
                }
            }
        }
        #endif
    }
}

#Preview {
    RootView()
        .environment(AppModel())
}
