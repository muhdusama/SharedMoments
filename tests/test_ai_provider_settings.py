"""AI settings and compatible streaming tests, all with mocked providers."""

import json

import pytest

from app.ai_settings import NAME, active_ai_config, public_ai_config, save_ai_config, validate_base_url
from app.models import SessionLocal, Setting


def clear():
    db = SessionLocal()
    try:
        db.query(Setting).filter(Setting.name == NAME).delete()
        db.commit()
    finally:
        db.close()


def config():
    return {
        'provider': 'openai_compatible',
        'base_url': 'https://api.example.invalid/v1',
        'model': 'synthetic-model',
        'api_key': 'synthetic-key-that-is-not-real',
        'system_prompt': 'Do not invent details.',
    }


def csrf(client):
    assert client.get('/settings').status_code == 200
    response = client.get('/api/v2/ai/config')
    assert response.status_code == 200
    with client.session_transaction() as sess:
        return sess['ai_settings_csrf']


def test_config_is_admin_only_encrypted_and_redacted(admin_client, adult_client):
    clear()
    token = csrf(admin_client)
    payload = config()
    try:
        assert adult_client.get('/api/v2/ai/config').status_code == 403
        assert admin_client.put('/api/v2/ai/config', json=payload).status_code == 403
        response = admin_client.put('/api/v2/ai/config', json=payload,
                                    headers={'X-CSRF-Token': token})
        assert response.status_code == 200
        assert response.json['data']['key_configured'] is True
        assert 'api_key' not in response.get_data(as_text=True)
        assert payload['api_key'] not in response.get_data(as_text=True)
        assert payload['api_key'] not in admin_client.get('/settings').get_data(as_text=True)
        db = SessionLocal()
        try:
            stored = db.query(Setting).filter(Setting.name == NAME).one().value
            assert payload['api_key'] not in stored
            assert json.loads(stored)['secret'].startswith('gAAAA')
        finally:
            db.close()
        assert active_ai_config()['api_key'] == payload['api_key']
        # Never carry a previously saved API credential to another endpoint.
        other_endpoint = {**payload, 'base_url': 'https://other.example.invalid/v1',
                          'api_key': ''}
        assert admin_client.put('/api/v2/ai/config', json=other_endpoint,
                                headers={'X-CSRF-Token': token}).status_code == 400
        assert active_ai_config()['base_url'] == payload['base_url']
        assert admin_client.put('/api/v2/ai/config',
                                json={**payload, 'api_key': ''},
                                headers={'X-CSRF-Token': token}).status_code == 200
        assert active_ai_config()['api_key'] == payload['api_key']
    finally:
        clear()


@pytest.mark.parametrize('url', [
    'http://public.example.invalid/v1', 'ftp://localhost/v1',
    'https://user:pass@example.invalid/v1', 'https://example.invalid/v1?x=1',
    'https://example.invalid/api/v2',
])
def test_non_compatible_or_insecure_urls_are_rejected(url):
    with pytest.raises(ValueError):
        validate_base_url(url)


def test_private_ollama_endpoint_and_env_provider(monkeypatch):
    from app.ai import get_active_provider

    clear()
    try:
        save_ai_config({
            'provider': 'ollama',
            'base_url': 'http://synthetic-model.local:11434/v1',
            'model': 'synthetic-local-model',
            'system_prompt': '',
        })
        assert get_active_provider() == 'openai_compatible'
        assert active_ai_config()['api_key'] == 'ollama'
        save_ai_config({'provider': 'disabled'})
        assert get_active_provider() is None
        save_ai_config({'provider': 'environment'})
        monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-env-key')
        assert get_active_provider() == 'openai'
    finally:
        clear()


def test_compatible_stream_uses_selected_endpoint_without_network(monkeypatch):
    from app.ai import stream_ai_response
    import openai

    clear()
    calls = []

    class SyntheticDelta:
        content = 'Synthetic response'

    class FakeClient:
        def __init__(self, **kwargs):
            calls.append(('client', kwargs['base_url'], kwargs['api_key']))
            self.chat = self
            self.completions = self

        def create(self, **kwargs):
            calls.append(('request', kwargs['model'], kwargs['messages'][0]['content']))
            return [type('Chunk', (), {'choices': [type('Choice', (), {'delta': SyntheticDelta()})()]})()]

    monkeypatch.setattr(openai, 'OpenAI', FakeClient)
    try:
        save_ai_config(config())
        chunks = list(stream_ai_response('This is only synthetic text.'))
        assert 'data: Synthetic response\n\n' in chunks
        assert calls[0] == ('client', 'https://api.example.invalid/v1',
                            'synthetic-key-that-is-not-real')
        assert calls[1] == ('request', 'synthetic-model', 'Do not invent details.')
        assert chunks[-1] == 'data: [DONE]\n\n'
    finally:
        clear()


def test_invalid_provider_and_missing_hosted_key_rejected():
    clear()
    with pytest.raises(ValueError, match='Unsupported'):
        save_ai_config({'provider': 'codex_subscription'})
    with pytest.raises(ValueError, match='API key'):
        save_ai_config({**config(), 'api_key': ''})
    assert public_ai_config()['provider'] == 'environment'
