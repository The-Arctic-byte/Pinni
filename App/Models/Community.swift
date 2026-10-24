import Foundation

struct Channel: Codable, Hashable, Identifiable, Sendable {
    enum Kind: String, Codable, Sendable {
        case topic, place, language, community
    }

    let id: String
    let kind: Kind
    let name: LocalizedText
    let description: LocalizedText
    let categories: [Category]
    let placeId: String?
    let language: String?
    let memberCount: Int
    let createdAt: Date
}

/// A channel that similar people follow.
struct ChannelSuggestion: Codable, Hashable, Identifiable, Sendable {
    let channelId: String
    let score: Double
    /// Only present when at least 20.
    let similarMembers: Int?
    let reason: LocalizedText

    var id: String { channelId }
}

struct ChannelPost: Codable, Hashable, Identifiable, Sendable {
    let id: String
    let channelId: String
    let authorId: String
    let storyId: String?
    let text: String?
    let likes: Int?
    let createdAt: Date
}

struct Report: Codable, Hashable, Identifiable, Sendable {
    enum Kind: String, Codable, Sendable {
        case newsTip, problem
    }

    enum Status: String, Codable, Sendable {
        case sent, inReview, published, edited, rejected, editorLead
    }

    let id: String
    let kind: Kind
    let reporterId: String
    let storyId: String?
    let category: Category
    let sensitive: Bool
    let text: String
    let location: Location?
    let status: Status
    let editorNote: String?
    let resultStoryId: String?
    let reach: Int?
    let createdAt: Date
    let updatedAt: Date
}

struct AppNotification: Codable, Hashable, Identifiable, Sendable {
    enum Kind: String, Codable, Sendable {
        case reportPublished, reportRejected, reportEditorLead, mustSee, forYou, channelPost
    }

    let id: String
    let userId: String
    let kind: Kind
    let title: LocalizedText
    let body: LocalizedText
    let storyId: String?
    let reportId: String?
    let channelId: String?
    let createdAt: Date
    let readAt: Date?
}

struct User: Codable, Hashable, Identifiable, Sendable {
    let id: String
    let role: Role
    let displayName: String?
    let verifiedVia: String?
    let createdAt: Date
}
