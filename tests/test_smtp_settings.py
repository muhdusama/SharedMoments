"""SMTP settings, encryption and delivery tests. Never connect to a real server."""

import json

from app.models import SessionLocal, Setting
from app.mail_settings import (
    SETTING_NAME, get_smtp_config, public_smtp_config, save_smtp_config,
)


def sample():
    return {
        'enabled': True, 'host': 'smtp.example.invalid', 'port': 587,
        'username': 'synthetic@example.invalid', 'password': 'synthetic-long-password',
        'sender': 'noreply@example.invalid', 'security': 'starttls',
    }


def clear():
    db = SessionLocal()
    try:
        db.query(Setting).filter(Setting.name == SETTING_NAME).delete()
        db.commit()
    finally:
        db.close()


def csrf(client):
    assert client.get('/settings').status_code == 200
    with client.session_transaction() as sess:
        return sess['smtp_settings_csrf']


def test_smtp_configuration_encrypted_and_redacted(admin_client, adult_client, monkeypatch):
    clear()
    token = csrf(admin_client)
    data = sample()
    try:
        assert adult_client.get('/api/v2/smtp/config').status_code == 403
        assert admin_client.put('/api/v2/smtp/config', json=data).status_code == 403
        response = admin_client.put(
            '/api/v2/smtp/config', json=data,
            headers={'X-CSRF-Token': token},
        )
        assert response.status_code == 200
        assert response.json['data']['secret_configured'] is True
        assert 'password' not in response.get_data(as_text=True)
        db = SessionLocal()
        try:
            saved = db.query(Setting).filter(Setting.name == SETTING_NAME).one()
            assert data['password'] not in saved.value
            assert json.loads(saved.value)['secret'].startswith('gAAAA')
        finally:
            db.close()
        assert get_smtp_config()['password'] == data['password']
        assert data['password'] not in admin_client.get('/api/v2/smtp/config').get_data(as_text=True)
        assert data['password'] not in admin_client.get('/settings').get_data(as_text=True)
        # Empty password must preserve the encrypted secret.
        assert admin_client.put('/api/v2/smtp/config', json={**data, 'password': ''},
                                headers={'X-CSRF-Token': token}).status_code == 200
        assert get_smtp_config()['password'] == data['password']
    finally:
        clear()


def test_invalid_smtp_configuration_fails_closed(admin_client):
    clear()
    token = csrf(admin_client)
    for change in (
        {'port': 0}, {'port': 70000}, {'security': 'none'},
        {'host': 'host\nInjected'}, {'sender': 'invalid-address'},
    ):
        result = admin_client.put('/api/v2/smtp/config',
                                  json={**sample(), **change},
                                  headers={'X-CSRF-Token': token})
        assert result.status_code == 400
    assert public_smtp_config()['source'] in ('none', 'environment')


def test_delivery_uses_tls_and_is_disabled_when_requested(monkeypatch):
    from app.notifications import send_email_notification

    events = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            events.append(('connect', host, port, timeout, bool(context)))

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self, context=None):
            events.append(('starttls', bool(context)))

        def login(self, name, password):
            events.append(('login', name, password == 'synthetic-long-password'))

        def send_message(self, message):
            events.append(('send', message['To'], message['From']))

    monkeypatch.setattr('smtplib.SMTP', FakeSMTP)
    monkeypatch.setattr('smtplib.SMTP_SSL', FakeSMTP)
    clear()
    try:
        save_smtp_config(sample())
        assert send_email_notification('recipient@example.invalid', 'Test', 'Synthetic only')
        assert ('starttls', True) in events
        assert ('login', 'synthetic@example.invalid', True) in events
        assert ('send', 'recipient@example.invalid', 'noreply@example.invalid') in events

        events.clear()
        save_smtp_config({**sample(), 'security': 'ssl', 'port': 465, 'password': ''})
        assert send_email_notification('recipient@example.invalid', 'Test', 'Synthetic only')
        assert ('connect', 'smtp.example.invalid', 465, 15, True) in events
        assert not any(event[0] == 'starttls' for event in events)

        events.clear()
        save_smtp_config({**sample(), 'enabled': False, 'password': ''})
        assert not send_email_notification('recipient@example.invalid', 'Test', 'Synthetic only')
        assert not events
    finally:
        clear()


def test_test_email_is_explicit_and_self_addressed(admin_client, monkeypatch):
    from app import notifications

    sends = []
    monkeypatch.setattr(notifications, 'send_email_notification', lambda to, subject, body: sends.append(to) or True)
    token = csrf(admin_client)
    assert admin_client.post('/api/v2/smtp/test', json={}).status_code == 403
    assert sends == []
    response = admin_client.post('/api/v2/smtp/test', json={'to': 'someone-else@example.invalid'},
                                 headers={'X-CSRF-Token': token})
    assert response.status_code == 200
    assert sends == ['admin@test.com']
