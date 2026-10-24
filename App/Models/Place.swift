import Foundation

struct Place: Codable, Hashable, Identifiable, Sendable {
    enum Kind: String, Codable, Sendable {
        case area, city, country, region, world
    }

    let id: String
    let kind: Kind
    let name: LocalizedText
    let parentId: String?
    let center: Coordinate?
    let countryCode: String?
}
