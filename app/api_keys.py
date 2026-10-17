"""User-owned API keys. Raw secrets are returned only once, never persisted."""
import hashlib
import hmac
import re
import secrets
from datetime import datetime, timedelta, timezone

from app.models import ApiKey, SessionLocal


def _now():
    # Store UTC values without timezone metadata for SQLite compatibility.
    return datetime.now(timezone.utc).replace(tzinfo=None)


def create_key(user_id, name, scope='read', days=90):
    name = name.strip()
    if not 1 <= len(name) <= 80 or scope not in {'read', 'read_write'}:
        raise ValueError('Invalid key name or scope')
    if not isinstance(days, int) or not 1 <= days <= 365:
        raise ValueError('Key expiry must be between 1 and 365 days')

    db = SessionLocal()
    try:
        active = db.query(ApiKey).filter(
            ApiKey.userID == user_id, ApiKey.revokedAt.is_(None),
            ApiKey.expiresAt > _now()
        ).count()
        if active >= 20:
            raise ValueError('Maximum 20 active API keys per user')
        raw = 'smk_' + secrets.token_urlsafe(32)
        now = _now()
        record = ApiKey(
            userID=user_id, name=name, scope=scope,
            keyHash=hashlib.sha256(raw.encode('utf-8')).hexdigest(),
            keyPrefix=raw[:12], createdAt=now,
            expiresAt=now + timedelta(days=days),
        )
        db.add(record)
        db.commit()
        return raw, record.id
    finally:
        db.close()


def lookup_key(raw, method):
    if not re.fullmatch(r'smk_[A-Za-z0-9_-]{43}', raw):
        return None
    digest = hashlib.sha256(raw.encode('utf-8')).hexdigest()
    db = SessionLocal()
    try:
        key = db.query(ApiKey).filter(ApiKey.keyHash == digest).first()
        if not key or not hmac.compare_digest(key.keyHash, digest):
            return None
        if key.revokedAt or key.expiresAt <= _now():
            return None
        if method not in ('GET', 'HEAD', 'OPTIONS') and key.scope != 'read_write':
            return None
        if not key.lastUsedAt or _now() - key.lastUsedAt > timedelta(hours=1):
            key.lastUsedAt = _now()
            db.commit()
        return key.userID
    finally:
        db.close()


def list_keys(user_id):
    db = SessionLocal()
    try:
        return [{
            'id': k.id, 'name': k.name, 'prefix': k.keyPrefix,
            'scope': k.scope, 'created': k.createdAt.isoformat(),
            'expires': k.expiresAt.isoformat(),
            'last_used': k.lastUsedAt.isoformat() if k.lastUsedAt else None,
            'revoked': bool(k.revokedAt),
        } for k in db.query(ApiKey).filter(ApiKey.userID == user_id)
                               .order_by(ApiKey.createdAt.desc()).all()]
    finally:
        db.close()


def revoke_key(user_id, key_id):
    db = SessionLocal()
    try:
        key = db.query(ApiKey).filter(
            ApiKey.userID == user_id, ApiKey.id == key_id
        ).first()
        if not key:
            return False
        if not key.revokedAt:
            key.revokedAt = _now()
            db.commit()
        return True
    finally:
        db.close()
