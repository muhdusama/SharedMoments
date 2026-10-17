"""Optional UI-managed SMTP settings, keeping secrets encrypted at rest."""

import base64
import hashlib
import json
import os
import re
from email.utils import parseaddr

from cryptography.fernet import Fernet, InvalidToken

from app.models import SessionLocal, Setting
from config import Config

SETTING_NAME = 'smtp_ui_config'


def _cipher():
    key = base64.urlsafe_b64encode(
        hashlib.sha256(b'sharedmoments-smtp-v1:' + Config.SECRET_KEY.encode('utf-8')).digest()
    )
    return Fernet(key)


def _read_config():
    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.name == SETTING_NAME).first()
        return json.loads(setting.value) if setting and setting.value else None
    finally:
        db.close()


def get_smtp_config():
    saved = _read_config()
    if saved is not None:
        if not saved.get('enabled'):
            return None
        encrypted = saved.get('secret', '')
        try:
            password = _cipher().decrypt(encrypted.encode()).decode() if encrypted else ''
        except InvalidToken as exc:
            raise RuntimeError('SMTP secret cannot be decrypted with the current SECRET_KEY') from exc
        return {
            'host': saved['host'], 'port': int(saved['port']),
            'username': saved.get('username', ''), 'password': password,
            'sender': saved['sender'], 'security': saved['security'],
        }

    host = os.environ.get('SMTP_HOST', '')
    user = os.environ.get('SMTP_USER', '')
    if not host:
        return None
    return {
        'host': host,
        'port': int(os.environ.get('SMTP_PORT', '587')),
        'username': user,
        'password': os.environ.get('SMTP_PASS', ''),
        'sender': os.environ.get('SMTP_FROM', user),
        'security': 'starttls',
    }


def public_smtp_config():
    saved = _read_config()
    if saved is not None:
        return {
            **{key: saved.get(key) for key in ('enabled', 'host', 'port', 'username', 'sender', 'security')},
            'secret_configured': bool(saved.get('secret')),
            'source': 'settings',
        }
    config = get_smtp_config()
    if config:
        return {
            'enabled': True, 'host': config['host'], 'port': config['port'],
            'username': config['username'], 'sender': config['sender'],
            'security': config['security'], 'secret_configured': bool(config['password']),
            'source': 'environment',
        }
    return {
        'enabled': False, 'host': '', 'port': 587, 'username': '',
        'sender': '', 'security': 'starttls', 'secret_configured': False, 'source': 'none',
    }


def save_smtp_config(payload):
    enabled = payload.get('enabled') is True
    host = str(payload.get('host', '')).strip()
    sender = str(payload.get('sender', '')).strip()
    user = str(payload.get('username', '')).strip()
    security = payload.get('security', 'starttls')
    try:
        port = int(payload.get('port', 587))
    except (ValueError, TypeError):
        raise ValueError('Invalid SMTP port')
    if not 1 <= port <= 65535 or security not in {'ssl', 'starttls'}:
        raise ValueError('Invalid SMTP port or security mode')
    if enabled and (
        not 1 <= len(host) <= 253 or not re.fullmatch(r'[A-Za-z0-9.:_-]+', host)
        or parseaddr(sender)[1] != sender or '@' not in sender
    ):
        raise ValueError('SMTP server and a valid sender address are required')
    if len(user) > 255:
        raise ValueError('SMTP username is too long')
    secret = str(payload.get('password') or '')
    if len(secret) > 2048:
        raise ValueError('SMTP password is too long')

    db = SessionLocal()
    try:
        setting = db.query(Setting).filter(Setting.name == SETTING_NAME).first()
        previous = json.loads(setting.value) if setting and setting.value else {}
        if enabled and user and not secret and not previous.get('secret') and os.environ.get('SMTP_PASS'):
            raise ValueError('Please enter the SMTP password when switching from environment configuration')
        stored = {
            'enabled': enabled, 'host': host, 'port': port,
            'username': user, 'sender': sender, 'security': security,
            'secret': (_cipher().encrypt(secret.encode()).decode() if secret
                       else previous.get('secret', '')),
        }
        if setting:
            setting.value = json.dumps(stored)
        else:
            db.add(Setting(name=SETTING_NAME, value=json.dumps(stored),
                           icon='', category='system', edition='all', type='json'))
        db.commit()
    finally:
        db.close()
