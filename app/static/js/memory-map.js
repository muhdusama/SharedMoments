let memoryMapInstance = null;
function mapStatus(message) {
    const status = document.getElementById('memory-map-status');
    if (status) status.textContent = message;
}
function loadMemoryMap() {
    if (memoryMapInstance) return;
    const container = document.getElementById('memory-map-canvas');
    if (!container || typeof L === 'undefined') {
        mapStatus('Map component unavailable');
        return;
    }
    container.hidden = false;
    const points = window.memoryMapPoints || [];
    memoryMapInstance = L.map(container).setView([0, 0], 2);
    // No map requests happen before this explicit action.
    L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
        maxZoom: 18, attribution: '&copy; OpenStreetMap contributors'
    }).addTo(memoryMapInstance);
    const markers = [];
    for (const point of points) {
        const marker = L.circleMarker([point.lat, point.lng], {
            radius: 8, color: point.visibility === 'private' ? '#7a55b4' : '#186b9c',
            fillOpacity: 0.85
        }).addTo(memoryMapInstance);
        const popup = document.createElement('div');
        const title = document.createElement('a');
        title.href = point.url;
        title.textContent = point.title || 'Memory';
        const details = document.createElement('p');
        details.textContent = [point.label, point.trip].filter(Boolean).join(' · ');
        popup.append(title, details);
        marker.bindPopup(popup);
        markers.push(marker);
    }
    if (markers.length) {
        memoryMapInstance.fitBounds(L.featureGroup(markers).getBounds(), {padding:[30,30],maxZoom:12});
    }
    document.getElementById('load-memory-map').hidden = true;
}
function prefillMemoryLocation() {
    const id = Number(document.getElementById('location-item').value);
    const existing = (window.memoryMapPoints || []).find(x => x.item_id === id && x.owner);
    for (const name of ['lat','lng','label','trip']) {
        document.getElementById('location-' + name).value = existing ? (
            name === 'lat' ? existing.lat : name === 'lng' ? existing.lng : existing[name]
        ) : '';
    }
    document.getElementById('location-visibility').value = existing ? existing.visibility : 'private';
}
function useDeviceLocation() {
    // Position is requested only through this explicit user action.
    if (!navigator.geolocation) return mapStatus('Geolocation is unavailable');
    navigator.geolocation.getCurrentPosition(pos => {
        document.getElementById('location-lat').value = pos.coords.latitude;
        document.getElementById('location-lng').value = pos.coords.longitude;
    }, () => mapStatus('Location access was not granted'));
}
async function locationMutation(method) {
    const id = document.getElementById('location-item').value;
    if (!id) return mapStatus('Select a memory');
    const payload = method === 'PUT' ? {
        lat: Number(document.getElementById('location-lat').value),
        lng: Number(document.getElementById('location-lng').value),
        label: document.getElementById('location-label').value,
        trip: document.getElementById('location-trip').value,
        visibility: document.getElementById('location-visibility').value
    } : {};
    if (method === 'PUT' && (!document.getElementById('location-lat').value ||
                              !document.getElementById('location-lng').value)) {
        return mapStatus('Latitude and longitude are required');
    }
    const response = await fetch('/api/v2/memories/' + id + '/location', {
        method, credentials:'same-origin',
        headers:{'Content-Type':'application/json','X-CSRF-Token':window.memoryMapCsrf},
        body:JSON.stringify(payload)
    });
    if (!response.ok) return mapStatus('Unable to change this location');
    location.reload();
}
function saveMemoryLocation() { locationMutation('PUT'); }
function deleteMemoryLocation() {
    if (confirm('Remove this location?')) locationMutation('DELETE');
}
