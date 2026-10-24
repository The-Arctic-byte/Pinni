import Foundation

/// One interaction, logged by the app and uploaded in batches (contract: event.schema.json).
struct Event: Codable, Hashable, Identifiable, Sendable {
    enum Kind: String, Codable, Sendable {
        case onboardingAnswer, profileEdit
        case open, dwell, skip, like, dislike, notForMe, reject, share, save
        case followPlace, unfollowPlace, joinChannel, leaveChannel, postToChannel
        case report, flagWrong, confirm
        case zoom, mapTap, placeChipTap, notificationOpen
    }

    struct Context: Codable, Hashable, Sendable {
        enum Screen: String, Codable, Sendable {
            case onboarding, map, news, story, community, profile, notification
        }

        var screen: Screen?
        var scale: Scale?
        var position: Int?
    }

    let id: String
    let userId: String
    let type: Kind
    var storyId: String?
    var channelId: String?
    var placeId: String?
    var value: Double?
    /// Type-specific payload, e.g. an onboarding question and its answer.
    var detail: [String: JSONValue]?
    var context: Context?
    let occurredAt: Date
}
