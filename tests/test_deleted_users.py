"""Account deletion retains shared history but cannot transfer a former identity."""
from datetime import datetime, timedelta, timezone

import jwt
from sqlalchemy import create_engine

from app.api_keys import create_key, lookup_key
from app.db_queries import get_user_by_email
from app.models import (
    ApiKey, CaptureDraft, MemoryComment, MemoryLocation, MemoryReaction,
    ReminderMute, Role, SavedMemorySearch, SessionLocal, User, UserRole,
)


def test_existing_users_table_gets_additive_tombstone_column(tmp_path):
    from app.models import _ensure_deleted_user_column
    engine = create_engine(f'sqlite:///{tmp_path / "legacy.db"}')
    with engine.begin() as connection:
        connection.exec_driver_sql('CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT)')
        connection.exec_driver_sql("INSERT INTO users (id, email) VALUES (1, 'synthetic@example.invalid')")
    _ensure_deleted_user_column(engine)
    _ensure_deleted_user_column(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql('SELECT id, deletedAt FROM users').one() == (1, None)
    engine.dispose()


def test_deletion_revokes_credentials_and_private_data_without_reusing_identity(
        app, admin_client, monkeypatch, tmp_path):
    from app.routes.quick_capture import _draft_folder

    monkeypatch.setattr('app.routes.quick_capture._draft_folder', lambda: tmp_path)
    db = SessionLocal()
    try:
        user = User(firstName='Synthetic', lastName='Former', email='former@example.invalid')
        user.hash_password('synthetic-password')
        db.add(user)
        db.flush()
        uid = user.id
        adult_role = db.query(Role).filter_by(roleName='Adult').one()
        db.add(UserRole(userID=uid, roleID=adult_role.id))
        from app.models import Item
        family = Item(title='Family history', content='Synthetic shared memory',
                      contentType='text', listType=1, edition='all', createdByUser=uid)
        other = Item(title='Private metadata record', contentType='text',
                     listType=1, edition='all', createdByUser=uid)
        db.add_all((family, other))
        db.flush()
        family_id, other_id = family.id, other.id
        db.add_all((
            MemoryComment(itemID=family_id, authorID=uid, content='Synthetic comment'),
            MemoryReaction(itemID=family_id, userID=uid, kind='heart'),
            MemoryLocation(itemID=family_id, createdByUser=uid, latitude=1, longitude=2,
                           label='Family place', visibility='family'),
            MemoryLocation(itemID=other_id, createdByUser=uid, latitude=3, longitude=4,
                           label='Private place', visibility='private'),
            SavedMemorySearch(userID=uid, name='Private filter', filters='{}'),
            CaptureDraft(userID=uid, title='Private image', description='Synthetic',
                         originalFilename='synthetic.jpg', filename='draft-test.jpg',
                         mediaType='image', status='pending'),
        ))
        db.commit()
    finally:
        db.close()
    (tmp_path / 'draft-test.jpg').write_bytes(b'synthetic only')
    key, _ = create_key(uid, 'Former member integration', scope='read_write')
    old_cookie = jwt.encode({
        'user_id': uid,
        'exp': datetime.now(timezone.utc) + timedelta(days=1)
    }, app.config['SECRET_KEY'], algorithm='HS256')
    former_client = app.test_client()
    former_client.set_cookie('jwt_token', old_cookie)
    assert former_client.get('/home').status_code == 200
    assert lookup_key(key, 'GET') == uid

    try:
        response = admin_client.delete(f'/api/v2/admin/users/{uid}')
        assert response.status_code == 200
        assert former_client.get('/home').status_code == 302
        assert former_client.get('/api/v2/api-keys').status_code == 302
        assert app.test_client().get('/api/v2/all-media-urls',
                  headers={'Authorization': 'Bearer ' + key}).status_code == 401
        assert lookup_key(key, 'GET') is None
        assert get_user_by_email('former@example.invalid') is None
        assert not (tmp_path / 'draft-test.jpg').exists()
        db = SessionLocal()
        try:
            former = db.get(User, uid)
            assert former is not None and former.deletedAt is not None
            assert former.firstName == 'Former member'
            assert former.email is None and former.passwordHash is None
            assert db.query(ApiKey).filter_by(userID=uid).count() == 0
            assert db.query(CaptureDraft).filter_by(userID=uid).count() == 0
            assert db.query(SavedMemorySearch).filter_by(userID=uid).count() == 0
            assert db.query(MemoryLocation).filter_by(createdByUser=uid).count() == 1
            assert db.query(MemoryComment).filter_by(authorID=uid).count() == 1
            assert db.query(MemoryReaction).filter_by(userID=uid).count() == 1
            newcomer = User(firstName='New', email='new-member@example.invalid')
            newcomer.hash_password('another-password')
            db.add(newcomer)
            db.flush()
            assert newcomer.id != uid
            db.rollback()
        finally:
            db.close()
        # The old JWT does not become valid again, even after creating a new account.
        assert former_client.get('/home').status_code == 302
    finally:
        # Isolated synthetic fixture cleanup; do not delete records in production.
        from app.models import Item
        db = SessionLocal()
        try:
            db.query(MemoryLocation).filter(MemoryLocation.itemID.in_([family_id, other_id])).delete(synchronize_session=False)
            db.query(MemoryComment).filter_by(authorID=uid).delete()
            db.query(MemoryReaction).filter_by(userID=uid).delete()
            db.query(ReminderMute).filter_by(user_id=uid).delete()
            db.query(Item).filter(Item.id.in_([family_id, other_id])).delete(synchronize_session=False)
            db.query(UserRole).filter_by(userID=uid).delete()
            db.query(User).filter_by(id=uid).delete()
            db.commit()
        finally:
            db.close()
