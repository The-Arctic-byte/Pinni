import MapKit
import SwiftUI

extension Scale {
    var title: LocalizedStringResource {
        switch self {
        case .area: "Area"
        case .city: "City"
        case .finland: "Finland"
        case .world: "World"
        }
    }

    /// Where the camera goes when the reader picks this scale. Area is centred on their home when known.
    func camera(home: CLLocationCoordinate2D?) -> MapCamera {
        switch self {
        case .area:
            MapCamera(centerCoordinate: home ?? .oulu, distance: 7_000, heading: 0, pitch: 60)
        case .city:
            MapCamera(centerCoordinate: .oulu, distance: 25_000, heading: 0, pitch: 45)
        case .finland:
            MapCamera(centerCoordinate: CLLocationCoordinate2D(latitude: 64.6, longitude: 26.0), distance: 2_200_000, heading: 0, pitch: 0)
        case .world:
            MapCamera(centerCoordinate: CLLocationCoordinate2D(latitude: 50.0, longitude: 20.0), distance: 18_000_000, heading: 0, pitch: 0)
        }
    }

    /// The scale a camera distance belongs to, so pinching moves the scale control too.
    init(cameraDistance distance: Double) {
        switch distance {
        case ..<20_000: self = .area
        case ..<300_000: self = .city
        case ..<6_000_000: self = .finland
        default: self = .world
        }
    }
}

extension CLLocationCoordinate2D {
    static let oulu = CLLocationCoordinate2D(latitude: 65.012, longitude: 25.471)
}

extension Story.MapObject {
    /// SF Symbol for the raised 3D tile; Thiings 3D images replace these with A1.
    var symbolName: String {
        switch self {
        case .stadium: "sportscourt.fill"
        case .arena: "hockey.puck.fill"
        case .concertHall: "music.note.house.fill"
        case .campus: "building.columns.fill"
        case .shoppingCentre: "cart.fill"
        case .hospital: "cross.case.fill"
        case .station: "tram.fill"
        case .cityHall: "building.2.fill"
        }
    }
}
