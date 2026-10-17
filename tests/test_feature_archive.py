"""Synthetic feature export and restore regression."""
from datetime import datetime
import pytest

from app.feature_archive import (
    export_feature_rows, restore_feature_rows, validate_feature_rows, wipe_feature_rows,
)
from app.models import Item, SessionLocal
from app import models


def test_metadata_roundtrip_preserves_ownership_and_media(tmp_path, app):
    if not hasattr(models, 'CaptureDraft'):
        pytest.skip('Feature metadata tables supplied by PRs #24–#28')
    from app.models import (
        CaptureDraft, LivePhotoPair, MemoryComment, MemoryLocation,
        MemoryReaction, MemoryTag, SavedMemorySearch,
    )
    archive = tmp_path / 'backup'
    private = archive / 'media' / 'capture-drafts'
    private.mkdir(parents=True)
    (private / 'synthetic.jpg').write_bytes(b'synthetic private media')
    db = SessionLocal()
    old_id = new_id = None
    try:
        original = Item(title='Original synthetic memory', contentType='text',
                        listType=1, createdByUser=2, edition='all')
        relocated = Item(title='Relocated synthetic memory', contentType='text',
                         listType=1, createdByUser=3, edition='all')
        db.add_all((original, relocated))
        db.flush()
        old_id, new_id = original.id, relocated.id
        db.add_all((
            MemoryTag(itemID=old_id, tag='holiday'),
            SavedMemorySearch(userID=2, name='Holidays', filters='{}'),
            LivePhotoPair(itemID=old_id, stillFilename='a.heic', motionFilename='a.mov'),
            MemoryLocation(itemID=old_id, createdByUser=2, latitude=1, longitude=2,
                           visibility='private'),
            MemoryComment(itemID=old_id, authorID=2, content='Synthetic',
                          createdAt=datetime(2026, 10, 17)),
            MemoryReaction(itemID=old_id, userID=2, kind='heart'),
            CaptureDraft(userID=2, title='Draft', description='Synthetic',
                         originalFilename='synthetic.jpg', filename='synthetic.jpg',
                         mediaType='image', status='pending'),
        ))
        db.commit()
        rows = export_feature_rows(db)
        validate_feature_rows(rows, [{'sourceId': 2}], [{'sourceId': old_id}], archive)
        (private / 'synthetic.jpg').unlink()
        with pytest.raises(ValueError, match='missing'):
            validate_feature_rows(rows, [{'sourceId': 2}], [{'sourceId': old_id}], archive)
        (private / 'synthetic.jpg').write_bytes(b'synthetic private media')
        with pytest.raises(ValueError, match='missing account'):
            validate_feature_rows(rows, [{'sourceId': 3}], [{'sourceId': old_id}], archive)

        wipe_feature_rows(db)
        db.commit()
        restore_feature_rows(db, rows, {2: 3}, {old_id: new_id})
        db.commit()
        assert db.query(MemoryTag).filter_by(itemID=new_id, tag='holiday').count() == 1
        assert db.query(LivePhotoPair).filter_by(itemID=new_id).count() == 1
        assert db.query(MemoryLocation).filter_by(itemID=new_id, createdByUser=3).count() == 1
        assert db.query(MemoryComment).filter_by(itemID=new_id, authorID=3).count() == 1
        assert db.query(MemoryReaction).filter_by(itemID=new_id, userID=3).count() == 1
        assert db.query(SavedMemorySearch).filter_by(userID=3).count() == 1
        assert db.query(CaptureDraft).filter_by(userID=3, status='pending').count() == 1
    finally:
        db.rollback()
        wipe_feature_rows(db)
        if old_id is not None:
            db.query(Item).filter(Item.id.in_([old_id, new_id])).delete(synchronize_session=False)
        db.commit()
        db.close()
