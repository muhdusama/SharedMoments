"""Video derivatives and Live Photo pairs: entirely synthetic media."""
import json
from datetime import datetime
from pathlib import Path

import pytest
from app.db_queries import create_item, create_item_share, delete_item
from app.media_playback import validate_pairs, persist_pairs, live_photos_for
from app.models import SessionLocal, LivePhotoPair


def test_validate_pair_rejects_unattached_and_duplicate_media():
    assert validate_pairs([{'still':'img.jpg','motion':'img.mov'}], 'img.jpg;img.mov') == [('img.jpg','img.mov')]
    with pytest.raises(ValueError):
        validate_pairs([{'still':'foreign.jpg','motion':'img.mov'}], 'img.jpg;img.mov')
    with pytest.raises(ValueError):
        validate_pairs([{'still':'img.jpg','motion':'img.jpg'}], 'img.jpg;img.mov')
    with pytest.raises(ValueError):
        validate_pairs([{'still':'img.jpg','motion':'img.mov'}]*2, 'img.jpg;img.mov')


def test_live_photo_pair_is_saved_rendered_and_cleans_up(admin_client):
    payload = json.dumps([{'still':'synthetic.jpg', 'motion':'synthetic.mov'}])
    response = admin_client.post('/api/v2/items', data={
        'title':'Synthetic Live Photo', 'content':'Test only', 'contentType':'galleryStartWithImage',
        'listType':'1', 'contentURL':'synthetic.jpg;synthetic.mov',
        'livePhotoPairs':payload,
    })
    assert response.status_code == 201
    from app.db_queries import get_items_by_type
    new = [item.id for item, user in get_items_by_type(1)
           if item.title == 'Synthetic Live Photo']
    assert len(new) == 1
    item_id = new[0]
    try:
        assert live_photos_for(item_id) == {'synthetic.jpg':'synthetic.mov'}
        gallery = admin_client.get(f'/gallery/{item_id}')
        assert gallery.status_code == 200
        assert b'/api/v2/media/play/synthetic.mov' in gallery.data
        assert b'motion_photos_on' in gallery.data
        assert gallery.data.count(b'data-video=') == 1
    finally:
        delete_item(item_id)
    db = SessionLocal()
    try:
        assert db.query(LivePhotoPair).filter_by(itemID=item_id).count() == 0
    finally:
        db.close()


def test_invalid_pair_rejects_before_creating_item(admin_client):
    response = admin_client.post('/api/v2/items', data={
        'title':'Should not exist', 'contentType':'text', 'listType':'1',
        'contentURL':'', 'livePhotoPairs':'[{"still":"fake.jpg","motion":"fake.mov"}]',
    })
    assert response.status_code == 400


@pytest.fixture
def mocked_video(monkeypatch, tmp_path):
    from app import media_playback
    video = tmp_path / 'synthetic.mov'
    video.write_bytes(b'synthetic original QuickTime bytes')
    monkeypatch.setattr(media_playback, '_find_media_folder', lambda name: str(tmp_path))
    monkeypatch.setattr(media_playback, '__file__', str(tmp_path / 'media_playback.py'))
    monkeypatch.setattr(media_playback, '_ffmpeg', lambda: '/synthetic/ffmpeg')
    calls = []

    def fake_ffmpeg(args, **_kwargs):
        calls.append(args)
        Path(args[-1]).write_bytes(b'synthetic H.264 MP4')
        return type('Result', (), {'returncode':0})()

    monkeypatch.setattr(media_playback.subprocess, 'run', fake_ffmpeg)
    return video, calls


def test_compatible_video_cached_original_unchanged_and_authenticated(
        client, adult_client, mocked_video):
    original, calls = mocked_video
    unchanged = original.read_bytes()
    route = '/api/v2/media/play/synthetic.mov'
    assert client.get(route).status_code == 302
    good = adult_client.get(route)
    assert good.status_code == 200
    assert good.mimetype == 'video/mp4'
    assert good.data == b'synthetic H.264 MP4'
    assert adult_client.get(route, headers={'Range':'bytes=0-3'}).status_code == 206
    assert adult_client.get(route).status_code == 200
    assert len(calls) == 1
    assert calls[0][calls[0].index('-c:v')+1] == 'libx264'
    assert original.read_bytes() == unchanged
    from app.media_playback import media_source
    from werkzeug.exceptions import BadRequest
    with adult_client.application.test_request_context():
        with pytest.raises(BadRequest):
            media_source('../secret.mov')


def test_shared_video_requires_authorised_share(admin_client, client, mocked_video):
    item_id = create_item('Synthetic video', 'Test', 'video-mov', 1,
                          'synthetic.mov', 2, datetime(2026, 1, 2))
    try:
        shared = create_item_share(item_id, 2, password='synthetic-pass')
        token = shared['token']
        route = f'/s/{token}/media/play/synthetic.mov'
        assert client.get(route).status_code == 403
        assert client.get(f'/s/{token}/media/play/unrelated.mov').status_code == 403
        assert client.post(f'/s/{token}/verify', data={'password':'synthetic-pass'}).status_code == 302
        good = client.get(route)
        assert good.status_code == 200 and good.mimetype == 'video/mp4'
        assert client.get(f'/s/{token}/media/play/unrelated.mov').status_code == 404
        assert client.get('/s/invalid/media/play/synthetic.mov').status_code == 404
    finally:
        delete_item(item_id)
