"""iOS Shortcuts private draft capture tests with entirely synthetic files."""
from io import BytesIO
from pathlib import Path

import pytest
from app.db_queries import get_items_by_type, delete_item
from app.models import CaptureDraft, SessionLocal


@pytest.fixture
def draft_storage(monkeypatch, tmp_path):
    private = tmp_path / 'private'
    published = tmp_path / 'published'
    private.mkdir()
    published.mkdir()
    monkeypatch.setattr('app.routes.quick_capture._draft_folder', lambda: private)
    monkeypatch.setattr('app.routes.api._get_upload_folder', lambda _ext: str(published))
    return private, published


def _csrf(client):
    assert client.get('/captures').status_code == 200
    with client.session_transaction() as value:
        return {'X-CSRF-Token': value['capture_csrf']}


def _capture(client, csrf, title='Synthetic quick draft', media=b'synthetic jpeg bytes', filename='sample.jpg', **options):
    return client.post('/api/v2/capture/drafts',
        data={'title':title, 'description':'Synthetic only',
              'file':(BytesIO(media),filename), **options},
        content_type='multipart/form-data', headers=csrf)


def test_draft_capture_is_private_until_explicit_publish(
        client, adult_client, admin_client, draft_storage):
    private, public = draft_storage
    assert client.post('/api/v2/capture/drafts').status_code == 302
    assert _capture(admin_client, {}, filename='private.jpg').status_code == 403
    header = _csrf(admin_client)
    sent = _capture(admin_client, header, filename='sample.jpg')
    assert sent.status_code == 201
    draft_id = sent.json['data']['id']
    assert not [item for item,_ in get_items_by_type(1) if item.title=='Synthetic quick draft']
    owner_page = admin_client.get('/captures')
    assert b'Synthetic quick draft' in owner_page.data
    assert b'Synthetic quick draft' not in adult_client.get('/captures').data
    assert adult_client.get(f'/api/v2/capture/drafts/{draft_id}/media').status_code == 404
    assert client.get(f'/api/v2/capture/drafts/{draft_id}/media').status_code == 302
    media = admin_client.get(f'/api/v2/capture/drafts/{draft_id}/media')
    assert media.status_code == 200
    assert media.data == b'synthetic jpeg bytes'
    assert media.headers['Cache-Control'] == 'private, no-store'
    assert admin_client.post(f'/api/v2/capture/drafts/{draft_id}/publish').status_code == 403
    publish = admin_client.post(f'/api/v2/capture/drafts/{draft_id}/publish', headers=header)
    assert publish.status_code == 200
    item_id = publish.json['data']['id']
    assert admin_client.post(f'/api/v2/capture/drafts/{draft_id}/publish',
                             headers=header).json['data']['id'] == item_id
    assert admin_client.get(f'/api/v2/capture/drafts/{draft_id}/media').status_code == 404
    matching = [(item,user) for item,user in get_items_by_type(1) if item.id==item_id]
    assert len(matching) == 1
    assert matching[0][0].createdByUser == 2
    assert matching[0][0].edition == 'couples'  # Current synthetic app edition, not 'all'
    assert (public / matching[0][0].contentURL).read_bytes()==b'synthetic jpeg bytes'
    delete_item(item_id)


def test_capture_draft_edit_and_discard_are_owner_scoped(admin_client, adult_client, draft_storage):
    private, public=draft_storage
    header=_csrf(admin_client)
    draft_id=_capture(admin_client,header).json['data']['id']
    url=f'/api/v2/capture/drafts/{draft_id}'
    assert adult_client.delete(url).status_code == 403
    assert admin_client.patch(url,json={'title':'New synthetic title','description':'Updated'},
                              headers=header).status_code==200
    assert b'New synthetic title' in admin_client.get('/captures').data
    assert admin_client.delete(url,headers=header).status_code==200
    assert not list(private.iterdir())
    assert admin_client.get('/captures').status_code==200


def test_capture_rejects_unapproved_types_empty_files_and_invalid_dates(
        admin_client,draft_storage,monkeypatch):
    header=_csrf(admin_client)
    assert _capture(admin_client,header,filename='file.html').status_code==400
    assert _capture(admin_client,header,media=b'').status_code==400
    assert _capture(admin_client,header,date='2026-13-01').status_code==400
    assert _capture(admin_client,header,description='ignored'*1000).status_code!=500
    monkeypatch.setattr('app.routes.quick_capture.MAX_BYTES', 5)
    assert _capture(admin_client,header,media=b'ten-bytes!').status_code==413


def test_shortcut_can_store_a_video_with_orig_bytes(admin_client,draft_storage):
    private,_=draft_storage
    header=_csrf(admin_client)
    uploaded=_capture(admin_client,header,title='Synthetic motion',filename='frame.MOV',
                     media=b'synthetic movie data')
    assert uploaded.status_code==201
    db=SessionLocal()
    try:
        draft=db.get(CaptureDraft,uploaded.json['data']['id'])
        assert draft.mediaType=='video-mov'
        assert (private/draft.filename).read_bytes()==b'synthetic movie data'
    finally:
        db.close()
