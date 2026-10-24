import Foundation

/// Stories ranked for one reader. The backend ranks; the app only displays (contract: feed.schema.json).
struct FeedPage: Codable, Hashable, Sendable {
    let userId: String
    let generatedAt: Date
    let scale: Scale?
    let placeId: String?
    /// 0 = general ranking (new user), 1 = fully personal.
    let personalization: Double
    let items: [FeedItem]
    let nextCursor: String?
}

struct FeedItem: Codable, Hashable, Identifiable, Sendable {
    let storyId: String
    let relevance: Double
    let mustSee: Bool
    let isExploration: Bool?
    let reasons: [LocalizedText]

    var id: String { storyId }
}
