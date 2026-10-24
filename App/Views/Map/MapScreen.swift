import MapKit
import SwiftUI

/// The map at four geographic scales, relative to where the reader lives (`ReaderScale`), with a news panel:
/// on iPhone a native sheet that is never dismissed (Flighty style), on Mac an inspector.
/// Area stories are a circle, never a pin, and the circle opens the story. Point pins that would
/// overlap at the current zoom are grouped; tapping a group narrows the panel's list to it.
struct MapScreen: View {
    @Environment(AppModel.self) private var model
    @State private var position: MapCameraPosition = .automatic
    @State private var scale: Scale = .area
    @State private var cameraDistance: Double = 7_000
    /// Stories pushed in the panel; the last one is the open story on the map.
    @State private var path: [String] = []
    /// Story ids of a tapped group pin; the panel lists only these until "Show all".
    @State private var groupFilter: [String]?
    /// Story id of the area circle the map itself has selected.
    @State private var areaSelection: String?
    @State private var sheetDetent: PresentationDetent = .resting
    @State private var showsInspector = true

    var body: some View {
        if case .failed(let message) = model.state {
            LoadFailure(message: message) { await model.load() }
        } else {
            content
        }
    }

    @ViewBuilder
    private var content: some View {
        #if os(iOS)
        map
            .sheet(isPresented: showsSheet) {
                panel
                    .presentationDetents([.collapsed, .resting, .medium, .large], selection: $sheetDetent)
                    .presentationDragIndicator(.visible)
                    .presentationBackgroundInteraction(.enabled(upThrough: .medium))
                    .interactiveDismissDisabled()
            }
        #else
        map
            .inspector(isPresented: $showsInspector) {
                panel
                    .inspectorColumnWidth(min: 320, ideal: 380, max: 480)
            }
            .toolbar {
                ToolbarItem {
                    Button("Story list", systemImage: "sidebar.trailing") { showsInspector.toggle() }
                }
            }
        #endif
    }

    #if os(iOS)
    /// The sheet stays up for good once onboarding is done (it would block the onboarding cover otherwise).
    private var showsSheet: Binding<Bool> {
        Binding(get: { model.hasCompletedOnboarding }, set: { _ in })
    }
    #endif

    private var panel: some View {
        MapPanel(
            title: panelTitle,
            entries: panelEntries,
            isGroup: groupFilter != nil,
            path: $path,
            onShowAll: { groupFilter = nil }
        )
    }

    private var map: some View {
        Map(position: $position, selection: $areaSelection) {
            ForEach(visibleEntries, id: \.item.id) { entry in
                if let location = entry.story.location, location.isArea {
                    MapCircle(center: location.coordinate.clLocation, radius: location.radiusMeters)
                        .foregroundStyle(entry.story.category.mapColor.opacity(0.18))
                        .stroke(entry.story.category.mapColor, style: StrokeStyle(lineWidth: 2, dash: [6, 4]))
                        .tag(entry.story.id)
                    Annotation(coordinate: location.coordinate.clLocation) {
                        Button {
                            open(entry.story.id)
                        } label: {
                            Color.clear.frame(width: 44, height: 44)
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Text(verbatim: entry.story.title.text(for: model.contentLanguage)))
                    } label: {
                        EmptyView()
                    }
                }
            }
            ForEach(groups) { group in
                if let story = model.stories[group.lead.storyId] {
                    Annotation(coordinate: group.coordinate.clLocation, anchor: .bottom) {
                        Button {
                            select(group)
                        } label: {
                            StoryPin(
                                story: story,
                                item: group.lead,
                                label: story.label.text(for: model.contentLanguage),
                                isSelected: highlightedIds.contains(story.id),
                                count: group.members.count
                            )
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel(Text(verbatim: story.title.text(for: model.contentLanguage)))
                    } label: {
                        EmptyView()
                    }
                }
            }
        }
        .mapStyle(.standard(elevation: .realistic, emphasis: .muted, pointsOfInterest: .excludingAll))
        .onMapCameraChange(frequency: .onEnd) { context in
            // The camera also reports while the window lays out (launch, resize, inspector). Changing state
            // right here re-lays out the map, which reports again: AppKit kills that loop with an exception.
            // So the update waits until layout is done, and only real changes count.
            let distance = context.camera.distance
            Task { cameraDidSettle(at: distance) }
        }
        .onChange(of: areaSelection) { _, id in
            if let id { open(id) }
        }
        .onChange(of: path) { old, new in
            if let id = new.last {
                flyIn(to: id)
            } else if let last = old.last, model.stories[last]?.mapObject != nil {
                // Leaving a 3D close-up goes back to the scale the reader was on.
                moveCamera(to: scale, animated: true)
            }
            if new.isEmpty { areaSelection = nil }
        }
        .safeAreaInset(edge: .top) { scalePicker }
        .onChange(of: model.profile?.homePlaceId, initial: true) {
            show(readerScale.startScale, animated: false)
            #if DEBUG
            applyLaunchArguments()
            #endif
        }
    }

    private var scalePicker: some View {
        Picker("Scale", selection: Binding(get: { scale }, set: { show($0, animated: true) })) {
            ForEach(Scale.allCases, id: \.self) { scale in
                Text(scale.title).tag(scale)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .padding(.horizontal)
        .padding(.vertical, 8)
        .frame(maxWidth: 480)
    }

    // MARK: Data

    private var readerScale: ReaderScale {
        ReaderScale(places: model.places, homePlaceId: model.profile?.homePlaceId)
    }

    /// Stories under the current scale for this reader, plus the open story so it stays visible in a close-up.
    private var visibleEntries: [(item: FeedItem, story: Story)] {
        let reader = readerScale
        return model.rankedStories.filter { reader.scale(of: $0.story) == scale || $0.story.id == path.last }
    }

    /// Point stories only. An area (`radiusMeters > 0`) stays a circle and is never grouped into a pin.
    private var groups: [PinGroup] {
        let pins = visibleEntries.compactMap { entry -> (item: FeedItem, coordinate: Coordinate)? in
            guard let location = entry.story.location, !location.isArea else { return nil }
            return (entry.item, location.coordinate)
        }
        return PinGrouping.groups(pins, cameraDistance: cameraDistance)
    }

    private var highlightedIds: Set<String> {
        Set(path.suffix(1) + (groupFilter ?? []))
    }

    private var panelEntries: [(item: FeedItem, story: Story)] {
        if let groupFilter {
            return model.rankedStories.filter { groupFilter.contains($0.story.id) }
        }
        let reader = readerScale
        return model.rankedStories.filter { reader.scale(of: $0.story) == scale }
    }

    private var panelTitle: Text {
        if let groupFilter { return Text("\(groupFilter.count) stories here") }
        switch scale {
        case .area: return Text("In your area")
        case .city:
            let city = model.places[readerScale.homeCityId]?.name.text(for: model.contentLanguage) ?? ""
            return Text("In \(city)")
        case .finland: return Text("In Finland")
        case .world: return Text("In the world")
        }
    }

    private var home: CLLocationCoordinate2D? {
        model.profile?.homePlaceId.flatMap { model.places[$0]?.center }?.clLocation
    }

    // MARK: Actions

    private func show(_ scale: Scale, animated: Bool) {
        self.scale = scale
        path = []
        groupFilter = nil
        areaSelection = nil
        moveCamera(to: scale, animated: animated)
    }

    private func moveCamera(to scale: Scale, animated: Bool) {
        let camera = scale.camera(home: home)
        cameraDistance = camera.distance
        if animated {
            withAnimation(.smooth(duration: 1.2)) { position = .camera(camera) }
        } else {
            position = .camera(camera)
        }
    }

    private func cameraDidSettle(at distance: Double) {
        if abs(distance - cameraDistance) > cameraDistance * 0.05 { cameraDistance = distance }
        // Pinching moves the scale control without moving the camera again; a close-up on a story doesn't.
        let pinched = Scale(cameraDistance: distance)
        if pinched != scale, path.isEmpty, groupFilter == nil { scale = pinched }
    }

    private func select(_ group: PinGroup) {
        guard group.isGroup else {
            open(group.lead.storyId)
            return
        }
        areaSelection = nil
        groupFilter = group.members.map(\.storyId)
        path = []
        revealPanel()
    }

    /// Opens one story in the panel; the map highlights it (and flies in for 3D objects) through `path`.
    private func open(_ id: String) {
        groupFilter = nil
        path = [id]
        revealPanel()
    }

    private func revealPanel() {
        #if os(iOS)
        if sheetDetent == .collapsed { sheetDetent = .resting }
        #else
        showsInspector = true
        #endif
    }

    /// A story with a 3D object flies in close so MapKit's real 3D buildings show around it.
    private func flyIn(to id: String) {
        guard let story = model.stories[id], story.mapObject != nil, let location = story.location else { return }
        withAnimation(.smooth(duration: 1.5)) {
            position = .camera(MapCamera(centerCoordinate: location.coordinate.clLocation, distance: 900, heading: 30, pitch: 70))
        }
    }
}

#if DEBUG
extension MapScreen {
    /// `-mapScale world`, `-mapSelect <story id>` and `-mapPanel medium|large` as launch arguments (screenshots).
    fileprivate func applyLaunchArguments() {
        let defaults = UserDefaults.standard
        if let raw = defaults.string(forKey: "mapScale"), let debugScale = Scale(rawValue: raw) { show(debugScale, animated: false) }
        if let id = defaults.string(forKey: "mapSelect") {
            if let group = groups.first(where: { $0.members.contains { $0.storyId == id } }) {
                select(group)
            } else if model.stories[id]?.location?.isArea == true {
                open(id)
            }
        }
        switch defaults.string(forKey: "mapPanel") {
        case "collapsed": sheetDetent = .collapsed
        case "medium": sheetDetent = .medium
        case "large": sheetDetent = .large
        default: break
        }
    }
}
#endif

extension PresentationDetent {
    /// Smallest height: just the sheet's title and buttons, so the map has the screen.
    static let collapsed = Self.height(110)
    /// Default height, between collapsed and medium: the top stories show and most of the map stays visible.
    static let resting = Self.fraction(0.34)
}

extension Coordinate {
    var clLocation: CLLocationCoordinate2D {
        CLLocationCoordinate2D(latitude: lat, longitude: lon)
    }
}

#Preview {
    MapScreen()
        .environment(AppModel(persona: .sara))
}
