"""Synthetic location visibility, edition and map-access regression tests."""
from datetime import datetime
import pytest
from app.db_queries import create_item, delete_item
from app.models import SessionLocal, MemoryLocation


@pytest.fixture
def memories(app):
    ids = [
        create_item('Synthetic seaside visit', 'Test', 'image', 1, '', 2, datetime(2026,1,1), edition='all'),
        create_item('Different edition memory', 'Test', 'text', 1, '', 2, datetime(2026,1,2), edition='friends')
    ]
    yield ids
    for id_ in ids:
        delete_item(id_)


def _csrf(client):
    assert client.get('/memories/map').status_code == 200
    with client.session_transaction() as state:
        return {'X-CSRF-Token': state['memory_map_csrf']}


def _put(client, item, headers, **changes):
    return client.put(f'/api/v2/memories/{item}/location', json={
        'lat': 12.1, 'lng': 45.5, 'label': 'Synthetic bay',
        'trip':'Synthetic holiday', 'visibility':'private', **changes
    }, headers=headers)


def test_map_requires_login_and_home_access(client, adult_client, monkeypatch):
    assert client.get('/memories/map').status_code == 302
    monkeypatch.setattr('app.routes.memory_map.has_list_permission', lambda *a: False)
    assert adult_client.get('/memories/map').status_code == 403


def test_location_private_by_default_and_never_leaks_to_other_users(
        admin_client, adult_client, child_client, memories):
    visible, hidden = memories
    own = _csrf(adult_client)
    assert _put(adult_client, visible, own).status_code == 200
    owner_view = adult_client.get('/memories/map')
    assert b'Synthetic bay' in owner_view.data
    assert b'Synthetic holiday' in owner_view.data
    for other in (admin_client, child_client):
        page = other.get('/memories/map')
        assert page.status_code == 200
        assert b'Synthetic bay' not in page.data
        assert b'45.5' not in page.data
    admin_headers = _csrf(admin_client)
    assert _put(admin_client, visible, admin_headers, label='Unsafe overwrite').status_code == 404
    assert _put(adult_client, hidden, own).status_code == 404
    assert _put(adult_client, visible, own, visibility='family').status_code == 200
    assert b'Synthetic bay' in child_client.get('/memories/map').data
    assert b'Synthetic bay' in admin_client.get('/memories/map?trip=holiday').data
    assert b'Synthetic bay' not in admin_client.get('/memories/map?trip=unrelated').data


def test_location_validation_and_child_cannot_edit(admin_client, child_client, memories):
    visible, _ = memories
    token = _csrf(admin_client)
    assert _put(admin_client, visible, {}).status_code == 403
    assert child_client.put(f'/api/v2/memories/{visible}/location',
                            json={'lat':0,'lng':0}).status_code == 403
    for changes in [{'lat': 91}, {'lng':181}, {'lat':'NaN'},
                    {'visibility':'world'}, {'label':'x'*121}]:
        assert _put(admin_client, visible, token, **changes).status_code == 400
    assert _put(admin_client, visible, token, lat=0, lng=0, label='Equator').status_code == 200
    assert b'Equator' in admin_client.get('/memories/map').data
    assert admin_client.delete(f'/api/v2/memories/{visible}/location',
                               json={}, headers=token).status_code == 200
    assert b'Equator' not in admin_client.get('/memories/map').data


def test_location_records_removed_with_memory(admin_client, memories):
    item, _ = memories
    token = _csrf(admin_client)
    assert _put(admin_client, item, token).status_code == 200
    delete_item(item)
    db = SessionLocal()
    try:
        assert db.query(MemoryLocation).filter_by(itemID=item).count() == 0
    finally:
        db.close()


def test_map_is_opt_in_and_xss_safe(adult_client, memories):
    token = _csrf(adult_client)
    visible, _ = memories
    assert _put(adult_client, visible, token,
                label='<script>alert(1)</script>',visibility='family').status_code == 200
    page = adult_client.get('/memories/map')
    assert b'&lt;script&gt;' in page.data
    assert b'Load interactive map' in page.data
    assert b'<div id="memory-map-canvas" hidden' in page.data
    # Only local scripts are loaded; tile requests are initiated by user interaction.
    assert b'vendor/leaflet/leaflet.js' in page.data
    assert b'<script src="https://tile.openstreetmap.org' not in page.data
