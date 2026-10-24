import SwiftUI

extension Category {
    /// Category colour from the asset catalog, named for the category. Used on the map only.
    /// Transport and technology stay the same in the dark: system yellow and gray are too light for a white symbol.
    var mapColor: Color {
        switch self {
        case .safety: .safety
        case .politics: .politics
        case .society: .society
        case .economy: .economy
        case .work: .work
        case .shopping: .shopping
        case .sport: .sport
        case .culture: .culture
        case .cityLife: .cityLife
        case .transport: .transport
        case .education: .education
        case .housing: .housing
        case .health: .health
        case .environment: .environment
        case .technology: .technology
        case .world: .world
        }
    }

    /// SF Symbol stand-in until the licensed Thiings topic images are added (A1).
    var symbolName: String {
        switch self {
        case .economy: "chart.line.uptrend.xyaxis"
        case .society: "person.3"
        case .politics: "building.columns"
        case .shopping: "bag"
        case .sport: "figure.run"
        case .safety: "shield.lefthalf.filled"
        case .culture: "theatermasks"
        case .transport: "bus"
        case .education: "graduationcap"
        case .housing: "house"
        case .health: "cross.case"
        case .work: "briefcase"
        case .environment: "leaf"
        case .technology: "cpu"
        case .world: "globe.europe.africa"
        case .cityLife: "building.2"
        }
    }

    var title: LocalizedStringResource {
        switch self {
        case .economy: "Economy"
        case .society: "Society"
        case .politics: "Politics"
        case .shopping: "Shopping"
        case .sport: "Sport"
        case .safety: "Safety"
        case .culture: "Culture"
        case .transport: "Transport"
        case .education: "Education"
        case .housing: "Housing"
        case .health: "Health"
        case .work: "Work"
        case .environment: "Environment"
        case .technology: "Technology"
        case .world: "World"
        case .cityLife: "City life"
        }
    }
}

extension String {
    /// Layout direction for content written in this language code (e.g. "fa" → right to left).
    var contentLayoutDirection: LayoutDirection {
        Locale.Language(identifier: self).characterDirection == .rightToLeft ? .rightToLeft : .leftToRight
    }
}
