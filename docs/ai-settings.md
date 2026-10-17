# AI writing provider configuration

Administrators can configure the existing AI writing assistant under **Settings → AI writing provider**, without editing environment files.

- **Environment configuration** uses existing OpenAI, Anthropic or Ollama environment variables unchanged.
- **OpenAI-compatible API** uses a configurable HTTPS base URL, model identifier and API key through the Chat Completions interface.
- **Ollama** uses its OpenAI-compatible `/v1` endpoint. Private-LAN HTTP is permitted; public remote HTTP is refused.
- **Disabled** turns AI writing off without deleting the saved configuration.

A custom system prompt is optional. The API credential is encrypted at rest using a key derived from the existing SECRET_KEY, and is never returned through the settings API or rendered into HTML. Saving without a new credential preserves the previously encrypted one. If SECRET_KEY is rotated, re-enter the provider credential.

Only accounts with the Update Setting permission can change this configuration, through a logged-in browser session and CSRF token. When an authorised user invokes the existing writing assistant, the selected draft text is sent to the configured provider. Review the provider's privacy terms before using a hosted endpoint with personal memories.

## ChatGPT and Codex subscriptions

A ChatGPT or Codex subscription is **not** an OpenAI-compatible API key. Do not paste Codex CLI login tokens or ChatGPT browser credentials into the settings form.

OpenAI offers Sign in with ChatGPT and plan-usage sharing in participating third-party apps, where supported. Adding that separate OAuth flow would require appropriate provider authorisation, integration and user consent. This PR does not claim that SharedMoments supports subscription-based inference. Use a separately authorised API key for a compatible provider or a local Ollama instance instead.

The feature reuses the existing OpenAI Python SDK, Flask, SQLite, cryptography and streaming AI endpoint. No new dependencies or services are added.
