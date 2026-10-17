"""Optional administrator-managed AI provider configuration (secrets encrypted)."""

import base64
import hashlib
import ipaddress
import json
import os
from urllib.parse import urlsplit

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.exc import SQLAlchemyError

from app.models import SessionLocal, Setting
from config import Config

NAME = 'ai_ui_config'
PROVIDERS = {'environment', 'openai_compatible', 'ollama', 'disabled'}


def _cipher():
    material = b'sharedmoments-ai-v1:' + Config.SECRET_KEY.encode('utf-8')
    return Fernet(base64.urlsafe_b64encode(hashlib.sha256(material).digest()))


def _stored():
    db = SessionLocal()
    try:
        row = db.query(Setting).filter(Setting.name == NAME).first()
        return json.loads(row.value) if row and row.value else None
    except SQLAlchemyError:
        # This module can be imported before the usual startup bootstrap.
        return None
    finally:
        db.close()


def _local_host(host):
    if host in ('localhost', '127.0.0.1', '::1'):
        return True
    try:
        return ipaddress.ip_address(host).is_private
    except ValueError:
        return '.' not in host or host.endswith(('.local', '.home.arpa'))


def validate_base_url(value):
    url = str(value).strip().rstrip('/')
    parts = urlsplit(url)
    if (parts.scheme not in ('http', 'https') or not parts.hostname
            or parts.username or parts.password or parts.query or parts.fragment):
        raise ValueError('Please provide an HTTP(S) OpenAI-compatible base URL')
    if parts.scheme == 'http' and not _local_host(parts.hostname):
        raise ValueError('Plain HTTP is only allowed for loopback or private-LAN models')
    if parts.path not in ('', '/v1', '/v1/'):
        raise ValueError('Base URL must be the API root or /v1')
    return url


def public_ai_config():
    stored = _stored()
    if stored:
        return {
            **{key: stored.get(key) for key in ('provider', 'base_url', 'model', 'system_prompt')},
            'key_configured': bool(stored.get('secret')),
        }
    return {
        'provider': 'environment', 'base_url': '', 'model': '',
        'system_prompt': '', 'key_configured': False,
    }


def save_ai_config(payload):
    provider = str(payload.get('provider', 'environment'))
    if provider not in PROVIDERS:
        raise ValueError('Unsupported AI provider')
    model = str(payload.get('model', '')).strip()
    prompt = str(payload.get('system_prompt', '')).strip()
    base = str(payload.get('base_url', '')).strip()
    secret = str(payload.get('api_key') or '')
    if len(model) > 128 or len(prompt) > 4000 or len(secret) > 2048:
        raise ValueError('AI configuration is too long')
    if provider in {'openai_compatible', 'ollama'}:
        base = validate_base_url(base or (
            'http://localhost:11434/v1' if provider == 'ollama'
            else 'https://api.openai.com/v1'
        ))
        if not model:
            raise ValueError('Model name is required')

    db = SessionLocal()
    try:
        row = db.query(Setting).filter(Setting.name == NAME).first()
        previous = json.loads(row.value) if row and row.value else {}
        retained = (
            previous.get('secret', '')
            if previous.get('provider') == provider and previous.get('base_url') == base
            else ''
        )
        stored_secret = _cipher().encrypt(secret.encode()).decode() if secret else retained
        if provider == 'openai_compatible' and not stored_secret:
            raise ValueError('An API key is required for a hosted OpenAI-compatible provider')
        value = {
            'provider': provider, 'base_url': base, 'model': model,
            'system_prompt': prompt,
            'secret': stored_secret,
        }
        if row:
            row.value = json.dumps(value)
        else:
            db.add(Setting(name=NAME, value=json.dumps(value),
                           icon='', category='system', edition='all', type='json'))
        db.commit()
    finally:
        db.close()


def active_ai_config():
    saved = _stored()
    if not saved or saved.get('provider') == 'environment':
        return None
    if saved['provider'] == 'disabled':
        return {'provider': 'disabled'}
    try:
        key = (_cipher().decrypt(saved['secret'].encode()).decode()
               if saved.get('secret') else '')
    except InvalidToken as exc:
        raise RuntimeError('Stored AI credential cannot be decrypted with this SECRET_KEY') from exc
    return {
        'provider': saved['provider'], 'base_url': saved['base_url'],
        'model': saved['model'], 'api_key': key or 'ollama',
        'system_prompt': saved.get('system_prompt', ''),
    }
