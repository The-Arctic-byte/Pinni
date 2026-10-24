import Foundation

extension Scale: Comparable {
    static func < (lhs: Scale, rhs: Scale) -> Bool {
        allCases.firstIndex(of: lhs)! < allCases.firstIndex(of: rhs)!
    }
}

/// Which map scale a story shows under for one reader: where it happens relative to where they live,
/// never smaller than the story's own scale. Kiiminki news is "Area" for a Kiiminki resident and "City" for
/// someone who only said Oulu; Helsinki news is "Finland" for both. Area-scale stories whose place is the
/// city itself stay on Area when the reader gave no neighbourhood, so Oulu centre is not an empty map.
struct ReaderScale {
    /// The app is about Oulu, so a reader who gave no place is treated as living somewhere in Oulu.
    static let defaultCityId = "oulu"
    static let homeCountryId = "finland"

    let places: [String: Place]
    let homeAreaId: String?
    let homeCityId: String

    init(places: [String: Place], homePlaceId: String?) {
        self.places = places
        let home = homePlaceId.flatMap { places[$0] }
        switch home?.kind {
        case .area:
            homeAreaId = home?.id
            homeCityId = home?.parentId ?? Self.defaultCityId
        case .city:
            homeAreaId = nil
            homeCityId = home?.id ?? Self.defaultCityId
        default:
            homeAreaId = nil
            homeCityId = Self.defaultCityId
        }
    }

    /// The scale a reader starts on: their area if they gave one, otherwise their city.
    var startScale: Scale { homeAreaId == nil ? .city : .area }

    func scale(of story: Story) -> Scale {
        let away = distance(to: story.placeId)
        if homeAreaId == nil, story.scale == .area, story.placeId == homeCityId {
            return .area
        }
        return max(story.scale, away)
    }

    /// How far a place is from the reader, as a scale.
    func distance(to placeId: String) -> Scale {
        let chain = ancestors(of: placeId)
        if let homeAreaId, chain.contains(homeAreaId) { return .area }
        if chain.contains(homeCityId) { return .city }
        if chain.contains(Self.homeCountryId) { return .finland }
        return .world
    }

    /// The place and every parent above it.
    private func ancestors(of placeId: String) -> [String] {
        var chain: [String] = []
        var current: String? = placeId
        while let id = current, !chain.contains(id) {
            chain.append(id)
            current = places[id]?.parentId
        }
        return chain
    }
}
