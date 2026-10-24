import Foundation

/// Stories that would overlap on the map at the current zoom, shown as one pin.
struct PinGroup: Identifiable, Sendable {
    /// Highest relevance first; the first one is drawn.
    let members: [FeedItem]
    let coordinate: Coordinate

    var id: String { members[0].storyId }
    var lead: FeedItem { members[0] }
    var isGroup: Bool { members.count > 1 }
}

enum PinGrouping {
    /// Pins closer than this share of the camera distance overlap on screen.
    static let overlapFactor = 0.08

    /// Greedy grouping: each pin, in relevance order, joins the first group whose lead is close enough.
    static func groups(_ pins: [(item: FeedItem, coordinate: Coordinate)], cameraDistance: Double) -> [PinGroup] {
        let threshold = cameraDistance * overlapFactor
        var groups: [(members: [FeedItem], coordinate: Coordinate)] = []
        for pin in pins.sorted(by: { $0.item.relevance > $1.item.relevance }) {
            if let index = groups.firstIndex(where: { meters(from: $0.coordinate, to: pin.coordinate) < threshold }) {
                groups[index].members.append(pin.item)
            } else {
                groups.append(([pin.item], pin.coordinate))
            }
        }
        return groups.map { PinGroup(members: $0.members, coordinate: $0.coordinate) }
    }

    /// Great-circle distance.
    static func meters(from a: Coordinate, to b: Coordinate) -> Double {
        let r = 6_371_000.0
        let dLat = (b.lat - a.lat) * .pi / 180
        let dLon = (b.lon - a.lon) * .pi / 180
        let h = sin(dLat / 2) * sin(dLat / 2) + cos(a.lat * .pi / 180) * cos(b.lat * .pi / 180) * sin(dLon / 2) * sin(dLon / 2)
        return 2 * r * asin(min(1, sqrt(h)))
    }
}
