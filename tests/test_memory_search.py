"""Synthetic search, access-control and saved-filter regression coverage."""
from datetime import datetime

import pytest
from app.db_queries import create_item, delete_item
from app.models import SessionLocal, SavedMemorySearch


@pytest.fixture
def search_posts(app):
    entries = [
        create_item('Autumn holiday', 'Mountain walk', 'image', 1,
                    'holiday.jpg', 2, datetime(2026, 4, 12), edition='all'),
        create_item('Birthday party', 'Cake together', 'galleryStartWithVideo', 1,
                    'party.mov;pic.jpg', 3, datetime(2026, 6, 2), edition='all'),
        create_item('Not in this edition', 'Secret alternate edition', 'text', 1,
                    '', 2, datetime(2026, 6, 2), edition='friends')
    ]
    yield entries
    db = SessionLocal()
    try:
        db.query(SavedMemorySearch).delete()
        db.commit()
    finally:
        db.close()
    for item in entries:
        delete_item(item)


def _csrf(client):
    response = client.get('/memories/search')
    assert response.status_code == 200
    with client.session_transaction() as s:
        return {'X-CSRF-Token': s['memory_search_csrf']}


def test_search_needs_login_and_home_permission(client, adult_client, monkeypatch):
    assert client.get('/memories/search').status_code == 302
    monkeypatch.setattr('app.routes.memory_search.has_list_permission', lambda *args: False)
    assert adult_client.get('/memories/search').status_code == 403


def test_text_author_date_media_and_edition_filters(child_client, search_posts):
    first, second, hidden = search_posts
    assert b'Autumn holiday' in child_client.get('/memories/search?q=mountain').data
    assert b'Birthday party' not in child_client.get('/memories/search?q=mountain').data
    assert b'Secret alternate edition' not in child_client.get('/memories/search').data
    assert b'Autumn holiday' in child_client.get('/memories/search?media=photo').data
    assert b'Birthday party' not in child_client.get('/memories/search?media=photo').data
    assert b'Birthday party' in child_client.get('/memories/search?media=video').data
    assert b'Autumn holiday' not in child_client.get('/memories/search?media=video').data
    assert b'Birthday party' in child_client.get('/memories/search?author=3').data
    assert b'Autumn holiday' not in child_client.get('/memories/search?author=3').data
    assert b'Autumn holiday' in child_client.get('/memories/search?date_to=2026-04-30').data
    assert b'Birthday party' not in child_client.get('/memories/search?date_to=2026-04-30').data
    assert child_client.get('/memories/search?date_from=bad').status_code == 400
    assert child_client.get('/memories/search?media=unknown').status_code == 400
    assert child_client.get('/memories/search?date_from=2026-12-01&date_to=2026-01-01').status_code == 400


def test_tag_updates_validation_and_cross_edition_denial(adult_client, child_client, search_posts):
    first, second, hidden = search_posts
    headers = _csrf(adult_client)
    endpoint = f'/api/v2/memories/{first}/tags'
    assert adult_client.put(endpoint, json={'tags': ['holidays']}).status_code == 403
    assert adult_client.put(endpoint, json={'tags': ['holidays', 'family']}, headers=headers).status_code == 200
    tagged = adult_client.get('/memories/search?tag=holidays')
    assert b'Autumn holiday' in tagged.data
    assert b'Birthday party' not in tagged.data
    assert child_client.put(endpoint, json={'tags': ['wrong']}).status_code == 403
    assert adult_client.put(f'/api/v2/memories/{hidden}/tags', json={'tags':['hidden']},
                            headers=headers).status_code == 404
    assert adult_client.put(endpoint, json={'tags':['UPPER']}, headers=headers).status_code == 400
    assert adult_client.put(endpoint, json={'tags':['dupe','dupe']}, headers=headers).status_code == 400


def test_saved_searches_are_personal_and_do_not_bypass_visibility(adult_client, child_client, search_posts):
    headers = _csrf(adult_client)
    child_headers = _csrf(child_client)
    response = adult_client.post('/api/v2/memories/saved-searches', json={
        'name': 'Holidays',
        'filters': {'q': 'holiday', 'date_from': '2026-01-01', 'media':'photo'}
    }, headers=headers)
    assert response.status_code == 201
    sid = response.json['data']['id']
    assert b'Holidays' in adult_client.get('/memories/search').data
    assert b'Holidays' not in child_client.get('/memories/search').data
    assert child_client.delete(f'/api/v2/memories/saved-searches/{sid}',
                               json={}, headers=child_headers).status_code == 404
    assert adult_client.delete(f'/api/v2/memories/saved-searches/{sid}',
                               json={}, headers=headers).status_code == 200


def test_escaping_and_pagination(child_client, app):
    id_ = create_item('<script>alert(1)</script>', '<img src=x onerror=alert(1)>',
                      'text', 1, '', 2, datetime(2026, 10, 17), edition='all')
    try:
        page = child_client.get('/memories/search?q=script')
        assert page.status_code == 200
        assert b'&lt;script&gt;' in page.data
        assert b'<script>alert(1)</script>' not in page.data
        assert child_client.get('/memories/search?page=0').status_code == 400
    finally:
        delete_item(id_)
