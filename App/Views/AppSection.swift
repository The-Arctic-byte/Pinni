import SwiftUI

enum AppSection: String, CaseIterable, Identifiable, Hashable {
    case map, news, community, profile

    var id: String { rawValue }

    var title: LocalizedStringResource {
        switch self {
        case .map: "Map"
        case .news: "News"
        case .community: "Community"
        case .profile: "Profile"
        }
    }

    var systemImage: String {
        switch self {
        case .map: "map"
        case .news: "newspaper"
        case .community: "person.2"
        case .profile: "person.crop.circle"
        }
    }

    @ViewBuilder
    var screen: some View {
        switch self {
        case .map: MapScreen()
        case .news: NewsScreen()
        case .community: CommunityScreen()
        case .profile: ProfileScreen()
        }
    }
}
