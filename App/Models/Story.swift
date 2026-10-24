import Foundation

/// One explained story in all languages. Per-reader ranking lives in `FeedItem` (contract: story.schema.json).
struct Story: Codable, Hashable, Identifiable, Sendable {
    enum Status: String, Codable, Sendable {
        case draft, inReview, published, rejected
    }

    enum Origin: String, Codable, Sendable {
        case agent, community
    }

    enum MapObject: String, Codable, Sendable {
        case stadium, arena, concertHall, campus, shoppingCentre, hospital, station, cityHall
    }

    struct Explanation: Codable, Hashable, Sendable {
        struct Context: Codable, Hashable, Sendable {
            let question: LocalizedText
            let answer: LocalizedText
        }

        struct ActionPlace: Codable, Hashable, Sendable {
            let name: LocalizedText
            let coordinate: Coordinate?
            let url: URL?
        }

        struct TimelineEntry: Codable, Hashable, Sendable {
            let at: Date
            let text: LocalizedText
        }

        let known: [LocalizedText]?
        let happened: LocalizedText?
        let notKnown: LocalizedText?
        let forYou: LocalizedText
        let context: Context?
        let actionPlace: ActionPlace?
        let timeline: [TimelineEntry]?
    }

    struct Original: Codable, Hashable, Sendable {
        let fi: String
        let en: String
    }

    struct WordOfDay: Codable, Hashable, Sendable {
        let word: String
        let meaning: LocalizedText
    }

    struct Source: Codable, Hashable, Sendable {
        let name: String
        let url: URL?
        let publishedAt: Date?
    }

    struct Translation: Codable, Hashable, Sendable {
        let language: String
        let tier: Int
        let reviewedBy: String?
    }

    struct Verification: Codable, Hashable, Sendable {
        let verifiedBy: String
        let verifiedAt: Date
    }

    struct Community: Codable, Hashable, Sendable {
        let reportId: String
        let confirmations: Int
    }

    let id: String
    let status: Status
    let origin: Origin
    let scale: Scale
    let placeId: String
    let location: Location?
    let category: Category
    let tags: [String]?
    let needs: [Need]
    let risk: Risk
    let isOpinion: Bool
    let importance: Double
    let affects: [String]?
    let mapObject: MapObject?
    let label: LocalizedText
    let title: LocalizedText
    let explanation: Explanation
    let originals: [Original]?
    let wordOfDay: WordOfDay?
    let sources: [Source]
    let translations: [Translation]
    let verification: Verification?
    let community: Community?
    let createdAt: Date
    let updatedAt: Date
    let publishedAt: Date?

    func tier(for language: String) -> Int? {
        translations.first { $0.language == language }?.tier
    }
}
