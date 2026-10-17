import os
import json
import requests

DEFAULT_SYSTEM_PROMPT = (
    "You are a warm and personal writing assistant for a memory sharing app. "
    "The user provides bullet points describing a shared experience or memory. "
    "Transform these into a flowing, heartfelt, personal narrative. "
    "Write in the same language as the input. "
    "Keep the tone personal, warm, and authentic. "
    "Do not add information not present in the bullet points. "
    "Return only the final text — no preamble, no explanations, no markdown."
)


def get_system_prompt():
    from app.ai_settings import active_ai_config
    config = active_ai_config()
    if config and config.get('system_prompt'):
        return config['system_prompt']
    return os.environ.get('AI_SYSTEM_PROMPT') or DEFAULT_SYSTEM_PROMPT


def get_active_provider():
    from app.ai_settings import active_ai_config
    config = active_ai_config()
    if config:
        if config['provider'] == 'disabled':
            return None
        return 'openai_compatible' if config['provider'] in ('openai_compatible', 'ollama') else config['provider']
    if os.environ.get('OPENAI_API_KEY'):
        return 'openai'
    if os.environ.get('ANTHROPIC_API_KEY'):
        return 'anthropic'
    if os.environ.get('OLLAMA_BASE_URL'):
        return 'ollama'
    return None


def _stream_openai(text):
    import openai
    client = openai.OpenAI(api_key=os.environ['OPENAI_API_KEY'])
    model = os.environ.get('OPENAI_MODEL', 'gpt-4o-mini')

    stream = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": get_system_prompt()},
            {"role": "user", "content": text},
        ],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def _stream_openai_compatible(text):
    """Use standard Chat Completions at a configured provider, including Ollama /v1."""
    import openai
    from app.ai_settings import active_ai_config
    config = active_ai_config()
    client = openai.OpenAI(
        api_key=config['api_key'],
        base_url=config['base_url'],
        max_retries=0,
        timeout=45.0,
    )
    stream = client.chat.completions.create(
        model=config['model'],
        messages=[
            {'role': 'system', 'content': get_system_prompt()},
            {'role': 'user', 'content': text},
        ],
        stream=True,
    )
    for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def _stream_anthropic(text):
    import anthropic
    client = anthropic.Anthropic(api_key=os.environ['ANTHROPIC_API_KEY'])
    model = os.environ.get('ANTHROPIC_MODEL', 'claude-haiku-4-5')

    with client.messages.stream(
        model=model,
        max_tokens=1024,
        system=get_system_prompt(),
        messages=[{"role": "user", "content": text}],
    ) as stream:
        for chunk in stream.text_stream:
            yield chunk


def _stream_ollama(text):
    base_url = os.environ.get('OLLAMA_BASE_URL', 'http://localhost:11434')
    model = os.environ.get('OLLAMA_MODEL', 'llama3.2')

    response = requests.post(
        f"{base_url}/api/chat",
        json={
            "model": model,
            "messages": [
                {"role": "system", "content": get_system_prompt()},
                {"role": "user", "content": text},
            ],
            "stream": True,
        },
        stream=True,
    )
    response.raise_for_status()

    for line in response.iter_lines():
        if line:
            data = json.loads(line)
            content = data.get("message", {}).get("content", "")
            if content:
                yield content


def stream_ai_response(text):
    try:
        provider = get_active_provider()
    except Exception:
        yield 'data: Error: AI provider configuration is unavailable.\n\n'
        yield 'data: [DONE]\n\n'
        return
    if not provider:
        yield "data: Error: No AI provider configured\n\n"
        yield "data: [DONE]\n\n"
        return

    generators = {
        'openai': _stream_openai,
        'openai_compatible': _stream_openai_compatible,
        'anthropic': _stream_anthropic,
        'ollama': _stream_ollama,
    }

    try:
        for chunk in generators[provider](text):
            yield f"data: {chunk}\n\n"
    except Exception:
        # External provider errors may contain sensitive request headers or URLs.
        yield 'data: Error: AI request failed. Check provider configuration.\n\n'

    yield "data: [DONE]\n\n"
