"""API key lifecycle and scoped authentication using synthetic test accounts."""

from datetime import datetime, timedelta

from app.api_keys import create_key, lookup_key


def _manage_key(client, name='Test integration', scope='read', days=30):
    assert client.get('/user-settings').status_code == 200
    with client.session_transaction() as sess:
        csrf = sess['api_key_csrf']
    response = client.post(
        '/api/v2/api-keys',
        json={'name': name, 'scope': scope, 'expiry_days': days},
        headers={'X-CSRF-Token': csrf},
    )
    return response, csrf


def test_create_read_revoke_key(admin_client, client):
    from app.models import ApiKey, SessionLocal

    created, csrf = _manage_key(admin_client)
    assert created.status_code == 201
    assert created.headers['Cache-Control'] == 'no-store'
    raw = created.json['data']['key']
    key_id = created.json['data']['id']
    assert raw.startswith('smk_')
    db = SessionLocal()
    try:
        stored = db.get(ApiKey, key_id)
        assert stored.keyHash != raw
        assert raw not in repr(stored.__dict__)
        assert stored.userID == 2
    finally:
        db.close()

    # The one-time secret must never reappear in the list endpoint.
    listed = admin_client.get('/api/v2/api-keys')
    assert listed.status_code == 200
    assert raw not in listed.get_data(as_text=True)
    assert any(item['id'] == key_id for item in listed.json['data']['keys'])
    headers = {'Authorization': f'Bearer {raw}'}
    assert admin_client.get('/api/v2/all-media-urls', headers=headers).status_code == 200
    assert client.get('/api/v2/all-media-urls', headers=headers).status_code == 200
    assert client.get('/api/v2/all-media-urls').status_code == 302
    assert admin_client.post('/api/v2/items', headers=headers, data={}).status_code == 401
    assert admin_client.get('/user-settings', headers=headers).status_code == 403
    assert admin_client.get('/api/v2/api-keys', headers=headers).status_code == 403
    assert admin_client.post('/api/v2/api-keys', headers=headers, json={}).status_code == 403
    assert admin_client.get('/api/v2/all-media-urls', headers={'Authorization': 'Bearer wrong'}).status_code == 401
    assert admin_client.get('/api/v2/all-media-urls', headers={'Authorization': 'Basic wrong'}).status_code == 401

    assert admin_client.post(f'/api/v2/api-keys/{key_id}/revoke',
                             json={}, headers={'X-CSRF-Token': csrf}).status_code == 200
    assert lookup_key(raw, 'GET') is None
    assert admin_client.get('/api/v2/all-media-urls', headers=headers).status_code == 401


def test_read_write_token_uses_existing_role_permissions(adult_client):
    from app.db_queries import get_items_by_type, delete_item

    created, csrf = _manage_key(adult_client, scope='read_write')
    assert created.status_code == 201
    raw = created.json['data']['key']
    headers = {'Authorization': f'Bearer {raw}'}
    response = adult_client.post('/api/v2/items', data={
        'title': 'Synthetic family memory', 'content': 'Test-only',
        'contentType': 'text', 'listType': '1', 'dateCreated': '2026-10-17'
    }, headers=headers)
    assert response.status_code == 201
    items = get_items_by_type(1)
    imported = [post.id for post, _ in items if post.title == 'Synthetic family memory']
    assert len(imported) == 1
    try:
        assert adult_client.get('/api/v2/all-media-urls', headers=headers).status_code == 200
    finally:
        delete_item(imported[0])
        adult_client.post(f'/api/v2/api-keys/{created.json["data"]["id"]}/revoke',
                          json={}, headers={'X-CSRF-Token': csrf})


def test_key_issuance_requires_cookie_and_csrf(admin_client, client):
    response = admin_client.post('/api/v2/api-keys', json={'name': 'Unsafe'})
    assert response.status_code == 403
    response = client.post('/api/v2/api-keys', json={'name': 'Unowned'})
    assert response.status_code in (302, 403)
    response, csrf = _manage_key(admin_client, name='', days=700)
    assert response.status_code == 400
    response, csrf = _manage_key(admin_client, scope='admin')
    assert response.status_code == 400


def test_revocation_is_owner_scoped_and_expiry_is_enforced(admin_client):
    from app.models import ApiKey, SessionLocal

    raw, key_id = create_key(3, 'Other user key', scope='read')
    response, csrf = _manage_key(admin_client)
    owned_id = response.json['data']['id']
    assert admin_client.post(f'/api/v2/api-keys/{key_id}/revoke',
                             json={}, headers={'X-CSRF-Token': csrf}).status_code == 404
    assert lookup_key(raw, 'GET') == 3
    db = SessionLocal()
    try:
        key = db.get(ApiKey, key_id)
        key.expiresAt = datetime.utcnow() - timedelta(days=1)
        db.commit()
    finally:
        db.close()
    assert lookup_key(raw, 'GET') is None
    admin_client.post(f'/api/v2/api-keys/{owned_id}/revoke',
                      json={}, headers={'X-CSRF-Token': csrf})
