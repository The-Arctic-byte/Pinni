import MapKit
import SwiftUI

/// Placeholder map: pitched camera over the reader's home area with category-coloured pins.
/// Scales, 3D objects, sheet and place chips come with A5–A7.
struct MapScreen: View {
    @Environment(AppModel.self) private var model
    @State private var position: MapCameraPosition = .automatic

    var body: some View {
        Map(position: $position) {
            ForEach(model.rankedStories, id: \.item.id) { entry in
                if let location = entry.story.location {
                    Marker(
                        entry.story.label.text(for: model.contentLanguage),
                        systemImage: entry.story.category.symbolName,
                        coordinate: location.coordinate.clLocation
                    )
                    .tint(entry.story.category.mapColor)
                }
            }
        }
        .mapStyle(.standard(elevation: .realistic, pointsOfInterest: .excludingAll))
        // Move to the reader's home once their profile has loaded, and again when the reader changes.
        .onChange(of: model.profile?.homePlaceId, initial: true) {
            position = .camera(camera)
        }
    }

    private var camera: MapCamera {
        let home = model.profile?.homePlaceId.flatMap { model.places[$0]?.center }
        let center = home?.clLocation ?? CLLocationCoordinate2D(latitude: 65.012, longitude: 25.471)
        return MapCamera(centerCoordinate: center, distance: 9000, heading: 0, pitch: 55)
    }
}

extension Coordinate {
    var clLocation: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}

#Preview {
    MapScreen()
        .environment(AppModel())
}
