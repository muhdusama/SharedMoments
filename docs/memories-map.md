# Memories Map

The optional Memories Map lets users associate a Home memory with coordinates, a place label, and a trip or destination. A separate location table stores this data without changing existing memories or photographs. Locations are **private by default**.

## Permissions and privacy

- Users must have **View Home** to access the map. A location's memory must also be visible in the current app edition.
- Users with **Update Home** can add or update a location. Coordinates are private to the person who created the location unless that person explicitly chooses **Family** visibility.
- Even administrators cannot view or overwrite somebody else's private location through this feature. Locations are removed when the parent memory is deleted.
- Shared-link pages and media URLs do not expose coordinates. The app does not automatically extract GPS data from original image EXIF or send it to a geocoding service.
- Using **Use my current position** asks the browser for permission and only fills the form; nothing is saved until **Save location** is pressed.

## Map display

The location list and trip/place filtering work without map tiles. Leaflet 1.9.4 (BSD-2-Clause, license bundled) is served locally. Interactive map tiles are **off by default**.

Pressing **Load interactive map** contacts OpenStreetMap's public tile service. The provider can see which geographic tiles the browser requests, so loading the map exposes the viewed *area* even for an otherwise private location. Users who prefer not to disclose map viewing areas can use the location list and links without loading tiles.

Map points use escaped text content, not HTML concatenation, and are provided only after authentication and per-record privacy checks. No photos, coordinates or account data are embedded into public repository changes or synthetic tests.
