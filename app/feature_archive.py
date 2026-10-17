"""Export and restore metadata owned by the optional memory features.

Archive IDs are references only. Import remaps them to newly created users/items.
API credentials are intentionally never exported.
"""
from datetime import date, datetime
from pathlib import Path

from app import models

FEATURE_MODELS = {
    cls.__tablename__: cls for cls in (
        getattr(models, name, None) for name in (
            'MemoryTag', 'SavedMemorySearch', 'LivePhotoPair', 'MemoryLocation',
            'MemoryComment', 'MemoryReaction', 'CaptureDraft',
        )
    ) if cls is not None
}


def export_feature_rows(db):
    return {
        name: [
            {column.name: (
                value.isoformat() if isinstance(value, (datetime, date)) else value
            ) for column in cls.__table__.columns if column.name != 'id'
             for value in [getattr(row, column.name)]}
            for row in db.query(cls).all()
        ]
        for name, cls in FEATURE_MODELS.items()
    }


def validate_feature_rows(data, users, items, archive_root):
    """Refuse ambiguous references or missing private media before destructive import."""
    if not isinstance(data, dict) or set(data) != set(FEATURE_MODELS):
        raise ValueError('Incomplete feature metadata in backup')
    user_ids = [entry.get('sourceId') for entry in users]
    item_ids = [entry.get('sourceId') for entry in items]
    if (any(not isinstance(x, int) or x < 1 for x in user_ids + item_ids)
            or len(set(user_ids)) != len(user_ids)
            or len(set(item_ids)) != len(item_ids)):
        raise ValueError('Feature backup needs unique original user and memory IDs')
    for name, cls in FEATURE_MODELS.items():
        records = data[name]
        if not isinstance(records, list):
            raise ValueError('Invalid feature backup table')
        allowed = {column.name for column in cls.__table__.columns if column.name != 'id'}
        for row in records:
            if not isinstance(row, dict) or set(row) != allowed:
                raise ValueError('Invalid feature backup record')
            for field in ('itemID', 'publishedItemID'):
                if field in row and row[field] is not None and row[field] not in item_ids:
                    if field == 'publishedItemID':
                        continue  # Published memory may subsequently have been deleted.
                    raise ValueError('Feature backup references a missing memory')
            for field in ('userID', 'createdByUser', 'authorID'):
                if field in row and row[field] not in user_ids:
                    raise ValueError('Feature backup references a missing account')
            if name == 'capture_drafts':
                filename = row['filename']
                if (not isinstance(filename, str) or not filename
                        or Path(filename).name != filename
                        or row['status'] not in ('pending', 'publishing', 'published')):
                    raise ValueError('Unsafe draft filename or status in backup')
                if row['status'] != 'published' and not (
                        archive_root / 'media' / 'capture-drafts' / filename).is_file():
                    raise ValueError('Private draft file is missing from backup')


def wipe_feature_rows(db):
    for cls in reversed(list(FEATURE_MODELS.values())):
        db.query(cls).delete()


def restore_feature_rows(db, data, user_ids, item_ids):
    for name, cls in FEATURE_MODELS.items():
        for row in data[name]:
            values = row.copy()
            for field, mapping in (
                    ('itemID', item_ids), ('userID', user_ids),
                    ('createdByUser', user_ids), ('authorID', user_ids),
                    ('publishedItemID', item_ids)):
                if field in values and values[field] is not None:
                    values[field] = mapping.get(values[field])
                    if values[field] is None and field != 'publishedItemID':
                        raise ValueError('Unable to restore feature ownership')
            if name == 'capture_drafts' and row['publishedItemID'] is not None and values['publishedItemID'] is None:
                values['status'] = 'publishing'
            for column in cls.__table__.columns:
                if column.name in values and isinstance(values[column.name], str):
                    if isinstance(column.type.python_type, type) and issubclass(
                            column.type.python_type, (date, datetime)):
                        values[column.name] = column.type.python_type.fromisoformat(values[column.name])
            db.add(cls(**values))
    db.flush()
