import Foundation

/// The places a reader can tap instead of the scale picker: their neighbourhood (when they gave one),
/// their city, Finland, their home country, the EU and the world.
/// A chip leaves out stories that already belong to a smaller chip inside it, so Finland does not repeat Oulu.
struct PlaceChips {
    let places: [String: Place]
    /// Chip place ids, narrowest first.
    let ids: [String]

    init(places: [String: Place], homeAreaId: String?, homeCityId: String, homeCountryCode: String?) {
        self.places = places
        let homeCountry = homeCountryCode.flatMap { code in
            places.values.first { $0.kind == .country && $0.countryCode == code }?.id
        }
        let candidates = [homeAreaId, homeCityId, ReaderScale.homeCountryId, homeCountry, "eu", "world"]
        var ids: [String] = []
        for id in candidates.compactMap({ $0 }) where places[id] != nil && !ids.contains(id) {
            ids.append(id)
        }
        self.ids = ids
    }

    /// Whether a story belongs under a chip: it is in that place and not in a smaller chip inside it.
    func contains(_ chipId: String, storyPlaceId: String) -> Bool {
        let chain = places.chain(from: storyPlaceId)
        guard chain.contains(chipId) else { return false }
        let narrower = ids.filter { $0 != chipId && places.chain(from: $0).contains(chipId) }
        return !narrower.contains { chain.contains($0) }
    }
}
